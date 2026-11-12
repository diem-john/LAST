"""Prepare the four Chiayi candidate township boundaries from the accepted NLSC source.

Run from the repository root:
    python scripts/prepare_chiayi_candidate_boundaries.py

The source shapefile is never modified. The output GeoPackage contains the
source-CRS and EPSG:3826 analysis layers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "data/geospatial/raw/nlsc/boundaries/extracted/TOWN_MOI_1120317.shp"
DEFAULT_OUTPUT = ROOT / "data/geospatial/processed/chiayi_candidate_boundaries.gpkg"
DEFAULT_REPORT = ROOT / "reports/geospatial/chiayi_candidate_boundary_validation.json"
DEFAULT_MANIFEST = ROOT / "reports/geospatial/source_manifest.json"
TARGET_CRS = "EPSG:3826"
SOURCE_REVISION = "2023-03-13"
SOURCE_DATASET = "TOWN_MOI_1120317"
CANDIDATES = {
    "Q12": {"name_en": "Taibao City", "name_zh": "太保市", "towncode": "10010010"},
    "Q05": {"name_en": "Minxiong Township", "name_zh": "民雄鄉", "towncode": "10010050"},
    "Q02": {"name_en": "Puzi City", "name_zh": "朴子市", "towncode": "10010020"},
    "Q13": {"name_en": "Shuishang Township", "name_zh": "水上鄉", "towncode": "10010120"},
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_source(path: Path) -> tuple[gpd.GeoDataFrame, str]:
    """Read DBF text as UTF-8 first; fall back to GDAL's default if needed."""
    try:
        frame = gpd.read_file(path, encoding="UTF-8")
        encoding_used = "UTF-8"
    except (UnicodeError, ValueError):
        frame = gpd.read_file(path)
        encoding_used = "GDAL default (fallback)"
    return frame, encoding_used


def _geometry_checks(frame: gpd.GeoDataFrame) -> dict[str, Any]:
    geometry = frame.geometry
    return {
        "feature_count": int(len(frame)),
        "geometry_types": sorted(str(value) for value in geometry.geom_type.dropna().unique()),
        "missing_geometry_count": int(geometry.isna().sum()),
        "empty_geometry_count": int(geometry.is_empty.fillna(False).sum()),
        "invalid_geometry_count": int((~geometry.is_valid.fillna(False) & geometry.notna()).sum()),
    }


def prepare(source: Path, output: Path, report_path: Path, manifest_path: Path) -> dict[str, Any]:
    if not source.is_file():
        raise FileNotFoundError(f"Source shapefile not found: {source}")

    source_frame, encoding_used = read_source(source)
    required = {"TOWNID", "TOWNCODE", "COUNTYNAME", "TOWNNAME", "TOWNENG", "COUNTYID", "COUNTYCODE", "geometry"}
    missing_columns = sorted(required.difference(source_frame.columns))
    if missing_columns:
        raise ValueError(f"Source is missing required fields: {missing_columns}")
    if source_frame.crs is None:
        raise ValueError("Source shapefile has no CRS; refusing to assign one implicitly.")

    selected = source_frame[source_frame["TOWNID"].astype(str).isin(CANDIDATES)].copy()
    found = set(selected["TOWNID"].astype(str))
    expected = set(CANDIDATES)
    if found != expected:
        raise ValueError(f"Candidate ID mismatch. Expected {sorted(expected)}, found {sorted(found)}")
    if selected["TOWNID"].astype(str).duplicated().any():
        raise ValueError("Duplicate candidate TOWNID values found.")

    selected["candidate_name_en"] = selected["TOWNID"].astype(str).map(
        {key: value["name_en"] for key, value in CANDIDATES.items()}
    )
    selected["candidate_name_zh"] = selected["TOWNID"].astype(str).map(
        {key: value["name_zh"] for key, value in CANDIDATES.items()}
    )
    selected["source_dataset"] = SOURCE_DATASET
    selected["source_revision"] = SOURCE_REVISION

    source_checks = _geometry_checks(selected)
    if any(source_checks[key] for key in (
        "missing_geometry_count", "empty_geometry_count", "invalid_geometry_count"
    )):
        raise ValueError(f"Candidate source geometry checks failed: {source_checks}")

    # to_crs performs a coordinate transformation using the embedded source WKT.
    # Do not set_crs() here: the source coordinates must not be relabelled.
    projected = selected.to_crs(TARGET_CRS)
    projected_checks = _geometry_checks(projected)
    if any(projected_checks[key] for key in (
        "missing_geometry_count", "empty_geometry_count", "invalid_geometry_count"
    )):
        raise ValueError(f"Projected geometry checks failed: {projected_checks}")

    projected["area_km2"] = projected.geometry.area / 1_000_000.0
    if not projected["area_km2"].map(lambda value: value > 0).all():
        raise ValueError("One or more projected candidate areas are non-positive.")

    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    selected.to_file(output, layer="candidate_boundaries_source_crs", driver="GPKG", index=False)
    projected.to_file(output, layer="candidate_boundaries_epsg3826", driver="GPKG", index=False)

    # Re-open both layers from disk to validate the delivered artifact, not only memory objects.
    source_check = gpd.read_file(output, layer="candidate_boundaries_source_crs")
    projected_check = gpd.read_file(output, layer="candidate_boundaries_epsg3826")
    if len(source_check) != 4 or len(projected_check) != 4:
        raise RuntimeError("GeoPackage read-back did not return exactly four candidates per layer.")
    if projected_check.crs is None or projected_check.crs.to_epsg() != 3826:
        raise RuntimeError(f"Projected layer CRS is not EPSG:3826: {projected_check.crs}")

    areas = {
        row["candidate_name_en"]: round(float(row["area_km2"]), 4)
        for _, row in projected_check.iterrows()
    }
    result: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "path": str(source.relative_to(ROOT)),
            "dataset": SOURCE_DATASET,
            "revision": SOURCE_REVISION,
            "sha256": sha256_file(source),
            "encoding_requested": encoding_used,
            "crs_wkt": source_frame.crs.to_wkt(),
            "epsg_identified_by_pyproj": source_frame.crs.to_epsg(),
            "note": "Source CRS is retained from the embedded .prj. Reprojection uses GeoPandas.to_crs(EPSG:3826); no CRS relabelling is performed.",
        },
        "candidates": [
            {"town_id": town_id, **details}
            for town_id, details in CANDIDATES.items()
        ],
        "output": {
            "path": str(output.relative_to(ROOT)),
            "sha256": sha256_file(output),
            "bytes": output.stat().st_size,
            "layers": {
                "candidate_boundaries_source_crs": {
                    "crs": source_check.crs.to_wkt(),
                    **_geometry_checks(source_check),
                },
                "candidate_boundaries_epsg3826": {
                    "crs": projected_check.crs.to_string(),
                    **_geometry_checks(projected_check),
                    "area_km2": areas,
                },
            },
        },
        "validation": {
            "candidate_count_expected": 4,
            "candidate_count_source_layer": len(source_check),
            "candidate_count_projected_layer": len(projected_check),
            "all_candidate_ids_present": set(source_check["TOWNID"].astype(str)) == expected,
            "source_geometry_valid": source_checks["invalid_geometry_count"] == 0,
            "projected_geometry_valid": projected_checks["invalid_geometry_count"] == 0,
            "projected_crs_epsg3826": projected_check.crs.to_epsg() == 3826,
            "passed": True,
            "limitations": [
                "This product contains administrative township boundaries, not urban-planning polygons.",
                "Area values are administrative polygon areas and must not be used as urban built-up area.",
                "Chinese source DBF text is read as UTF-8 where supported; canonical candidate names are added from the project's approved candidate list. Original source fields are retained.",
                "Technical geometry validation does not establish positional accuracy or current administrative status beyond the project's accepted 2023 source reference.",
            ],
        },
    }
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["processed_products"] = [
            item for item in manifest.get("processed_products", [])
            if item.get("product_id") != "chiayi_candidate_boundaries"
        ]
        manifest["processed_products"].append({
            "product_id": "chiayi_candidate_boundaries",
            "path": str(output.relative_to(ROOT)),
            "sha256": result["output"]["sha256"],
            "validation_report": str(report_path.relative_to(ROOT)),
            "status": "processed_and_technically_validated",
            "candidate_count": 4,
            "crs_layers": {
                "candidate_boundaries_source_crs": "embedded source CRS",
                "candidate_boundaries_epsg3826": TARGET_CRS,
            },
            "generated_at_utc": result["generated_at_utc"],
            "limitations": result["validation"]["limitations"],
        })
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    result = prepare(
        args.source.resolve(), args.output.resolve(),
        args.report.resolve(), args.manifest.resolve(),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\\nCandidate boundary GeoPackage prepared successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
