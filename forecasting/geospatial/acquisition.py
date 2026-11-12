"""Reproducible geospatial source acquisition for LAST Phase 4A.

Dry-run mode is intentionally offline: it neither makes network requests nor writes files.
Government services require an explicit, verified URL and layer identifier in the config.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import zipfile
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config/geospatial_sources.json"
DEFAULT_MANIFEST = ROOT / "reports/geospatial/source_manifest.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError(f"Unsafe or empty source identifier: {value!r}")
    return cleaned


def _validate_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Only absolute HTTP(S) URLs are supported: {url!r}")


@dataclass
class AcquisitionResult:
    source_id: str
    provider: str
    dataset_title: str
    adapter: str
    status: str
    retrieved_at_utc: str | None = None
    landing_page_url: str | None = None
    download_url: str | None = None
    file_paths: list[str] | None = None
    sha256: dict[str, str] | None = None
    bytes_downloaded: int = 0
    native_crs: str | None = None
    scale_or_resolution: str | None = None
    license: str | None = None
    coverage_description: str | None = None
    limitations: str | None = None
    details: dict[str, Any] | None = None
    error: str | None = None



def _is_transient_service_error(exc: Exception) -> bool:
    """Identify temporary HTTP/service-capacity failures worth retrying."""
    message = str(exc).lower()
    transient_markers = (
        "429", "500", "502", "503", "504", "gateway", "temporarily",
        "capacity", "timeout", "timed out", "connection reset",
        "connection aborted", "remote end closed",
    )
    return isinstance(exc, (requests.Timeout, requests.ConnectionError)) or any(
        marker in message for marker in transient_markers
    )


def _with_exponential_backoff(
    operation: Any, *, attempts: int, initial_delay: float,
    max_delay: float, sleep: Any = time.sleep,
) -> tuple[Any, int]:
    """Run an operation with bounded retries for transient service errors."""
    attempts = max(1, int(attempts))
    delay = max(0.0, float(initial_delay))
    for attempt in range(1, attempts + 1):
        try:
            return operation(), attempt
        except Exception as exc:
            if attempt >= attempts or not _is_transient_service_error(exc):
                raise
            sleep(min(delay, max_delay))
            delay = min(max_delay, max(delay * 2, 0.1))
    raise RuntimeError("Retry loop exited unexpectedly")


class SourceAdapter(ABC):
    def __init__(self, source: dict[str, Any], root: Path, timeout: int = 60):
        self.source = source
        self.root = root
        self.timeout = timeout
        self.source_id = _safe_name(str(source["source_id"]))
        self.output_dir = root / str(source.get("output_dir", f"data/geospatial/raw/{self.source_id}"))

    def planned(self) -> AcquisitionResult:
        return self._result("planned_dry_run", details={"output_dir": str(self.output_dir)})

    def _result(self, status: str, **kwargs: Any) -> AcquisitionResult:
        return AcquisitionResult(
            source_id=self.source_id,
            provider=str(self.source.get("provider", "unspecified")),
            dataset_title=str(self.source.get("dataset_title", self.source_id)),
            adapter=str(self.source["adapter"]),
            status=status,
            landing_page_url=self.source.get("landing_page_url"),
            license=self.source.get("license"),
            native_crs=self.source.get("native_crs"),
            scale_or_resolution=self.source.get("scale_or_resolution"),
            coverage_description=self.source.get("coverage_description"),
            limitations=self.source.get("limitations"),
            **kwargs,
        )

    @abstractmethod
    def acquire(self) -> AcquisitionResult:
        raise NotImplementedError


class HttpDownloadAdapter(SourceAdapter):
    """Download a directly addressable official resource; no URL guessing."""

    def acquire(self) -> AcquisitionResult:
        url = str(self.source["download_url"])
        _validate_http_url(url)
        response = requests.get(url, timeout=self.timeout, stream=True)
        response.raise_for_status()
        filename = _safe_name(str(self.source.get("filename") or Path(urlparse(url).path).name or self.source_id))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        destination = self.output_dir / filename
        temporary = destination.with_suffix(destination.suffix + ".part")
        size = 0
        try:
            with temporary.open("wb") as stream:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        stream.write(chunk)
                        size += len(chunk)
            if size == 0:
                raise ValueError(f"Downloaded resource is empty: {url}")
            temporary.replace(destination)
        finally:
            if temporary.exists():
                temporary.unlink()
        digest = sha256_file(destination)
        files = [destination]
        extracted: list[Path] = []
        if self.source.get("extract_zip", False) and zipfile.is_zipfile(destination):
            extract_dir = self.output_dir / _safe_name(str(self.source.get("extract_dir", destination.stem)))
            extract_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(destination) as archive:
                for member in archive.infolist():
                    target = (extract_dir / member.filename).resolve()
                    if extract_dir.resolve() not in target.parents and target != extract_dir.resolve():
                        raise ValueError(f"Unsafe ZIP member path: {member.filename}")
                archive.extractall(extract_dir)
            extracted = [p for p in extract_dir.rglob("*") if p.is_file()]
            files.extend(extracted)
        hashes = {str(p.relative_to(self.root)): sha256_file(p) for p in files}
        return self._result(
            "acquired_unvalidated",
            retrieved_at_utc=utc_now(),
            download_url=url,
            file_paths=[str(p.relative_to(self.root)) for p in files],
            sha256=hashes,
            bytes_downloaded=size,
            details={
                "http_status": response.status_code,
                "content_type": response.headers.get("Content-Type"),
                "content_length_header": response.headers.get("Content-Length"),
                "archive_extracted": bool(extracted),
                "extracted_file_count": len(extracted),
            },
        )


class WFSAdapter(SourceAdapter):
    """Retrieve a configured WFS layer. URL and typeName must be supplied explicitly."""

    def acquire(self) -> AcquisitionResult:
        base_url = str(self.source["service_url"])
        _validate_http_url(base_url)
        type_name = str(self.source["type_name"])
        version = str(self.source.get("version", "2.0.0"))
        output_format = str(self.source.get("output_format", "application/gml+xml; version=3.2"))
        params = {
            "service": "WFS", "version": version, "request": "GetFeature",
            "typeNames" if version.startswith("2") else "typeName": type_name,
            "outputFormat": output_format,
        }
        if self.source.get("srs_name"):
            params["srsName"] = str(self.source["srs_name"])
        response = requests.get(base_url, params=params, timeout=self.timeout)
        response.raise_for_status()
        content = response.content
        if not content:
            raise ValueError("WFS returned an empty response")
        if b"ExceptionReport" in content[:5000] or b"ServiceException" in content[:5000]:
            raise ValueError("WFS returned an exception document instead of features")
        suffix = str(self.source.get("extension", ".gml"))
        if not suffix.startswith("."):
            suffix = "." + suffix
        self.output_dir.mkdir(parents=True, exist_ok=True)
        destination = self.output_dir / f"{self.source_id}{suffix}"
        destination.write_bytes(content)
        return self._result(
            "acquired_unvalidated",
            retrieved_at_utc=utc_now(),
            download_url=response.url,
            file_paths=[str(destination.relative_to(self.root))],
            sha256={str(destination.relative_to(self.root)): sha256_file(destination)},
            bytes_downloaded=len(content),
            details={"wfs_version": version, "type_name": type_name, "content_type": response.headers.get("Content-Type")},
        )


class OSMnxAdapter(SourceAdapter):
    """Acquire OSM road/building/facility features. OSM is not an official asset register."""

    def acquire(self) -> AcquisitionResult:
        try:
            import osmnx as ox
        except ImportError as exc:
            raise RuntimeError("OSM acquisition requires the optional package: pip install -r requirements-geospatial.txt") from exc

        # Bound Overpass request waits; OSMnx settings are process-global.
        ox.settings.requests_timeout = self.timeout
        if self.source.get("overpass_url"):
            ox.settings.overpass_url = str(self.source["overpass_url"])
        place = str(self.source.get("place", "Chiayi County, Taiwan"))
        retry_attempts = int(self.source.get("retry_attempts", 4))
        retry_initial_delay = float(self.source.get("retry_initial_delay_seconds", 10))
        retry_max_delay = float(self.source.get("retry_max_delay_seconds", 60))
        tags = self.source.get("tags")
        feature_kind = str(self.source.get("feature_kind", "roads"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        outputs: list[Path] = []
        details: dict[str, Any] = {"place": place, "feature_kind": feature_kind, "attribution": "© OpenStreetMap contributors"}
        if feature_kind == "roads":
            graph, attempts_used = _with_exponential_backoff(
                lambda: ox.graph_from_place(
                    place, network_type=str(self.source.get("network_type", "drive")), simplify=True
                ),
                attempts=retry_attempts, initial_delay=retry_initial_delay,
                max_delay=retry_max_delay,
            )
            nodes, edges = ox.graph_to_gdfs(graph)
            details["attempts_used"] = attempts_used
            graph_path = self.output_dir / f"{self.source_id}.graphml"
            edges_path = self.output_dir / f"{self.source_id}_edges.gpkg"
            nodes_path = self.output_dir / f"{self.source_id}_nodes.gpkg"
            ox.save_graphml(graph, graph_path)
            edges.to_file(edges_path, driver="GPKG")
            nodes.to_file(nodes_path, driver="GPKG")
            outputs.extend([graph_path, edges_path, nodes_path])
            details.update({"node_count": len(nodes), "edge_count": len(edges)})
        elif feature_kind == "features":
            if not isinstance(tags, dict) or not tags:
                raise ValueError("OSM feature adapter requires a non-empty 'tags' mapping")
            frame, attempts_used = _with_exponential_backoff(
                lambda: ox.features_from_place(place, tags=tags),
                attempts=retry_attempts, initial_delay=retry_initial_delay,
                max_delay=retry_max_delay,
            )
            details["attempts_used"] = attempts_used
            vector_path = self.output_dir / f"{self.source_id}.gpkg"
            frame.to_file(vector_path, driver="GPKG")
            outputs.append(vector_path)
            details["feature_count"] = len(frame)
            details["tags"] = tags
        else:
            raise ValueError(f"Unsupported OSM feature_kind: {feature_kind}")
        hashes = {str(p.relative_to(self.root)): sha256_file(p) for p in outputs}
        return self._result(
            "acquired_unvalidated",
            retrieved_at_utc=utc_now(),
            download_url="https://www.openstreetmap.org/",
            file_paths=[str(p.relative_to(self.root)) for p in outputs],
            sha256=hashes,
            bytes_downloaded=sum(p.stat().st_size for p in outputs),
            details=details,
        )


ADAPTERS = {
    "http": HttpDownloadAdapter,
    "wfs": WFSAdapter,
    "osmnx": OSMnxAdapter,
}


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        config = json.load(stream)
    if not isinstance(config.get("sources"), list):
        raise ValueError("Config must contain a 'sources' list")
    ids = [item.get("source_id") for item in config["sources"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Source identifiers must be unique")
    return config


def update_manifest(path: Path, results: list[AcquisitionResult], *, dry_run: bool) -> None:
    """Merge acquisition records while preserving existing source metadata."""
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if path.exists():
        with path.open("r", encoding="utf-8") as stream:
            existing = json.load(stream)
    records = {r.get("source_id", r.get("theme", "")): r for r in existing.get("sources", [])}
    for result in results:
        record = asdict(result)
        record["theme"] = result.source_id
        records[result.source_id] = record
    existing.update({
        "schema_version": "1.1",
        "project": existing.get("project", "LAST Phase 4A — Chiayi County study-area suitability assessment"),
        "updated_at_utc": utc_now(),
        "acquisition_mode": "dry_run" if dry_run else "live",
        "sources": list(records.values()),
    })
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_acquisition(
    config: dict[str, Any], *, root: Path, selected: set[str] | None = None,
    dry_run: bool = True, timeout: int = 60,
) -> list[AcquisitionResult]:
    results: list[AcquisitionResult] = []
    for source in config["sources"]:
        source_id = str(source["source_id"])
        if selected and source_id not in selected:
            continue
        if not source.get("enabled", False):
            continue
        adapter_name = str(source["adapter"])
        if adapter_name not in ADAPTERS:
            raise ValueError(f"Unknown adapter {adapter_name!r} for {source_id}")
        adapter = ADAPTERS[adapter_name](source, root, timeout=timeout)
        if dry_run:
            results.append(adapter.planned())
            continue
        try:
            results.append(adapter.acquire())
        except Exception as exc:
            # Record this source's failure and continue with independent sources.
            results.append(adapter._result(
                "acquisition_failed",
                retrieved_at_utc=utc_now(),
                error=f"{type(exc).__name__}: {exc}",
                details={"output_dir": str(adapter.output_dir)},
            ))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source", action="append", dest="sources", help="Source ID; repeat to select multiple")
    parser.add_argument("--live", action="store_true", help="Perform network requests and write downloaded files")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args(argv)
    config = load_config(args.config)
    results = run_acquisition(
        config, root=args.root.resolve(),
        selected=set(args.sources) if args.sources else None,
        dry_run=not args.live, timeout=args.timeout,
    )
    update_manifest(args.manifest if args.manifest.is_absolute() else args.root / args.manifest,
                    results, dry_run=not args.live)
    print(json.dumps([asdict(item) for item in results], indent=2, ensure_ascii=False))
    print(f"Mode: {'LIVE' if args.live else 'DRY RUN (offline; no writes)'}")
    failed = [item for item in results if item.status == "acquisition_failed"]
    if failed:
        print(f"Acquisition failures: {len(failed)}; see the manifest for details.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
