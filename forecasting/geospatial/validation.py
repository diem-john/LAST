"""Technical integrity checks for LAST Phase 4A acquired GIS files."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "reports/geospatial/source_manifest.json"
DEFAULT_REPORT = ROOT / "reports/geospatial/validation_report.json"
TARGET_CRS = "EPSG:3826"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_bounds(bounds: Any) -> bool:
    try:
        return len(bounds) == 4 and all(math.isfinite(float(value)) for value in bounds)
    except (TypeError, ValueError):
        return False


def validate_vector(path: Path, target_crs: str = TARGET_CRS) -> dict[str, Any]:
    import geopandas as gpd

    if path.suffix.lower() == ".gpkg":
        try:
            import pyogrio
            layers = [row[0] for row in pyogrio.list_layers(path)]
        except ImportError:
            import fiona
            layers = list(fiona.listlayers(path))
    else:
        layers = [None]

    reports, errors = [], []
    for layer in layers:
        try:
            frame = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
            geom = frame.geometry
            missing = int(geom.isna().sum())
            empty = int(geom.is_empty.fillna(False).sum())
            invalid = int((~geom.is_valid.fillna(False) & geom.notna()).sum())
            usable = geom.notna() & ~geom.is_empty.fillna(True)
            bounds = frame.loc[usable].total_bounds if bool(usable.any()) else None
            bounds_ok = bounds is not None and _finite_bounds(bounds)
            source_crs = frame.crs.to_string() if frame.crs else None
            transform_ok, transform_error = False, None
            if source_crs and bounds_ok:
                try:
                    transformed = frame.loc[usable].to_crs(target_crs).total_bounds
                    transform_ok = _finite_bounds(transformed)
                    if not transform_ok:
                        transform_error = "Transformed bounds are non-finite"
                except Exception as exc:
                    transform_error = f"{type(exc).__name__}: {exc}"
            else:
                transform_error = "Missing source CRS or usable geometry bounds"
            item = {
                "layer": layer, "feature_count": int(len(frame)),
                "geometry_types": sorted(str(v) for v in geom.geom_type.dropna().unique()),
                "missing_geometry_count": missing, "empty_geometry_count": empty,
                "invalid_geometry_count": invalid, "source_crs": source_crs,
                "bounds_source_crs": [float(v) for v in bounds] if bounds_ok else None,
                "target_crs": target_crs, "transform_to_target_crs_ok": transform_ok,
                "transform_error": transform_error,
                "technical_valid": bool(len(frame) and missing == 0 and empty == 0
                                         and invalid == 0 and source_crs and bounds_ok and transform_ok),
            }
            reports.append(item)
            if not item["technical_valid"]:
                errors.append(f"Layer {layer or '<default>'} failed technical checks")
        except Exception as exc:
            errors.append(f"Layer {layer or '<default>'} read failed: {type(exc).__name__}: {exc}")
    return {"path": str(path), "layers": reports, "errors": errors,
            "technical_valid": bool(reports) and not errors and all(x["technical_valid"] for x in reports)}


def validate_road_graph(path: Path) -> dict[str, Any]:
    import networkx as nx

    graph = nx.read_graphml(path)
    missing_xy, invalid_xy = 0, 0
    for _, attrs in graph.nodes(data=True):
        if "x" not in attrs or "y" not in attrs:
            missing_xy += 1
            continue
        try:
            if not math.isfinite(float(attrs["x"])) or not math.isfinite(float(attrs["y"])):
                invalid_xy += 1
        except (TypeError, ValueError):
            invalid_xy += 1
    components = (nx.number_weakly_connected_components(graph) if graph.is_directed()
                  else nx.number_connected_components(graph))
    valid = bool(graph.number_of_nodes() and graph.number_of_edges()
                 and missing_xy == 0 and invalid_xy == 0)
    return {
        "path": str(path), "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(), "directed": graph.is_directed(),
        "component_count": int(components), "graph_crs_metadata": graph.graph.get("crs"),
        "nodes_missing_xy": missing_xy, "nodes_invalid_xy": invalid_xy,
        "technical_valid": valid,
        "notes": ["Component count is descriptive; disconnected components are not automatically errors.",
                  "Coordinate checks do not establish routing quality."],
    }


def validate_source(record: dict[str, Any], root: Path, target_crs: str) -> dict[str, Any]:
    source_id = str(record.get("source_id", record.get("theme", "unknown")))
    files, errors = [], []
    for relative in record.get("file_paths") or []:
        path = Path(relative)
        if not path.is_absolute():
            path = root / path
        item = {"path": str(relative), "exists": path.is_file(),
                "bytes": path.stat().st_size if path.is_file() else None}
        if not path.is_file():
            errors.append(f"Missing acquired file: {relative}")
        else:
            actual = sha256_file(path)
            expected = (record.get("sha256") or {}).get(str(relative))
            item.update({"expected_sha256": expected, "actual_sha256": actual,
                         "sha256_matches": actual == expected if expected else None})
            if expected and actual != expected:
                errors.append(f"SHA-256 mismatch: {relative}")
            suffix = path.suffix.lower()
            try:
                if suffix in {".gpkg", ".shp", ".geojson"}:
                    item["spatial_validation"] = validate_vector(path, target_crs)
                    errors.extend(item["spatial_validation"]["errors"])
                elif suffix == ".graphml":
                    item["graph_validation"] = validate_road_graph(path)
                    if not item["graph_validation"]["technical_valid"]:
                        errors.append(f"Road graph structural check failed: {relative}")
            except Exception as exc:
                errors.append(f"{relative}: {type(exc).__name__}: {exc}")
        files.append(item)

    valid = bool(files) and not errors and all(item["exists"] for item in files)
    return {
        "source_id": source_id, "acquisition_status": record.get("status"),
        "validation_status": "passed" if valid else "failed",
        "technical_valid": valid, "files": files, "errors": errors,
        "scope_limitations": [
            "Technical validity is not a completeness, positional-accuracy, or official-status certification.",
            "Candidate coverage is not computed until comparable official urban-planning polygons are validated.",
            "OSM roads are not Taipower conductor or cable geometry.",
        ],
    }


def run_validation(manifest_path: Path = DEFAULT_MANIFEST, root: Path = ROOT,
                   report_path: Path = DEFAULT_REPORT, target_crs: str = TARGET_CRS) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = [r for r in manifest.get("sources", [])
               if r.get("source_id") and r.get("status") in
               {"acquired_unvalidated", "validated", "validation_failed"}]
    results = [validate_source(r, root, target_crs) for r in records]
    summary = {
        "schema_version": "1.0", "project": "LAST Phase 4A — GIS acquisition validation",
        "generated_at_utc": utc_now(), "target_crs": target_crs,
        "source_count": len(results),
        "passed_count": sum(r["technical_valid"] for r in results),
        "failed_count": sum(not r["technical_valid"] for r in results),
        "candidate_area_metrics_computed": False,
        "candidate_area_metrics_reason": "Official comparable urban-planning polygons are not yet acquired and validated.",
        "sources": results,
        "interpretation": [
            "Passed means applicable file integrity, geometry, CRS, and graph-structure checks passed.",
            "Missing expected hashes are reported as unavailable, not assumed to match.",
            "No candidate suitability scores or rankings are generated.",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        report_reference = str(report_path.resolve().relative_to(root.resolve()))
    except ValueError:
        report_reference = str(report_path)

    outcomes = {r["source_id"]: r for r in results}
    for record in manifest.get("sources", []):
        key = record.get("source_id", record.get("theme"))
        if key in outcomes:
            outcome = outcomes[key]
            record["validation_status"] = outcome["validation_status"]
            record["validation_report"] = report_reference
            record["validated_at_utc"] = summary["generated_at_utc"]
            record["status"] = "validated" if outcome["technical_valid"] else "validation_failed"
    acquired = [r for r in manifest.get("sources", []) if r.get("source_id")
                and r.get("status") in {"validated", "validation_failed", "acquired_unvalidated"}]
    manifest["status"] = (
        "acquisition_and_technical_validation_complete"
        if acquired and all(r.get("status") == "validated" for r in acquired)
        else "acquisition_complete_validation_incomplete_or_failed"
    )
    manifest["validation_summary"] = {
        "report_path": report_reference, "passed_count": summary["passed_count"],
        "failed_count": summary["failed_count"], "candidate_area_metrics_computed": False,
    }
    manifest["updated_at_utc"] = summary["generated_at_utc"]
    temp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    temp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(manifest_path)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--target-crs", default=TARGET_CRS)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    manifest = args.manifest if args.manifest.is_absolute() else root / args.manifest
    report = args.report if args.report.is_absolute() else root / args.report
    result = run_validation(manifest, root, report, args.target_crs)
    print(json.dumps({k: result[k] for k in ("generated_at_utc", "target_crs",
          "source_count", "passed_count", "failed_count", "candidate_area_metrics_computed")}, indent=2))
    for source in result["sources"]:
        print(f"{source['source_id']}: {source['validation_status']}")
        for error in source["errors"]:
            print(f"  ERROR: {error}")
    return 0 if result["failed_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
