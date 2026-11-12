"""Derive reproducible *analytical* built-up clusters; not statutory urban boundaries.

Run: python scripts/delineate_chiayi_urban_clusters.py
Requires existing NLSC candidate GeoPackage and OSM buildings GeoPackage.
No candidate suitability scores or rankings are calculated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
BOUNDARIES = ROOT / "data/geospatial/processed/chiayi_candidate_boundaries.gpkg"
BUILDINGS = ROOT / "data/geospatial/raw/osm/buildings/osm_chiayi_buildings.gpkg"
OUTPUT = ROOT / "data/geospatial/processed/chiayi_analytical_urban_clusters.gpkg"
REPORT = ROOT / "reports/geospatial/chiayi_urban_cluster_validation.json"
CRS = "EPSG:3826"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def delineate(boundaries_path, buildings_path, output_path, report_path,
              cell_m=250, min_footprints=3, min_coverage=0.015,
              min_cells=4):
    if cell_m <= 0 or min_footprints < 1 or not 0 < min_coverage <= 1 or min_cells < 1:
        raise ValueError("Invalid clustering parameters")
    bounds = gpd.read_file(boundaries_path, layer="candidate_boundaries_epsg3826")
    buildings = gpd.read_file(buildings_path)
    if bounds.crs is None or bounds.crs.to_epsg() != 3826:
        raise ValueError("Expected validated candidate boundaries in EPSG:3826")
    if buildings.crs is None:
        raise ValueError("Building dataset has no CRS")
    if len(bounds) != 4 or set(bounds.TOWNID.astype(str)) != {"Q12", "Q05", "Q02", "Q13"}:
        raise ValueError("Expected exactly four approved candidate townships")
    buildings = buildings.to_crs(CRS)
    buildings = buildings[buildings.geometry.notna() & ~buildings.geometry.is_empty & buildings.geometry.is_valid]
    # OSM building-tagged points cannot be interpreted as building footprints.
    buildings = buildings[buildings.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    if buildings.empty:
        raise ValueError("No valid polygon building footprints available")
    if not buildings.index.is_unique:
        buildings = buildings.reset_index(drop=True)
    records = []
    diagnostics = {}
    for _, town in bounds.sort_values("TOWNID").iterrows():
        town_id = str(town.TOWNID)
        polygon = town.geometry
        subset = buildings[buildings.intersects(polygon)]
        # Fixed global grid origin ensures reproducibility and comparable cell alignment.
        minx, miny, maxx, maxy = polygon.bounds
        x0 = int(minx // cell_m)
        y0 = int(miny // cell_m)
        x1 = int(maxx // cell_m) + 1
        y1 = int(maxy // cell_m) + 1
        qualifying = []
        for ix in range(x0, x1):
            for iy in range(y0, y1):
                cell = box(ix * cell_m, iy * cell_m, (ix + 1) * cell_m, (iy + 1) * cell_m)
                clipped = cell.intersection(polygon)
                if clipped.is_empty or clipped.area <= 0:
                    continue
                candidates = subset[subset.intersects(clipped)]
                fragments = [geom.intersection(clipped) for geom in candidates.geometry]
                fragments = [geom for geom in fragments if not geom.is_empty and geom.area > 0]
                if len(fragments) < min_footprints:
                    continue
                # Union avoids double counting overlapping mapped building polygons.
                coverage = unary_union(fragments).area / clipped.area
                if coverage >= min_coverage:
                    qualifying.append(clipped)
        if not qualifying:
            diagnostics[town_id] = {"status": "insufficient_mapped_buildings", "qualifying_cells": 0}
            continue
        merged = unary_union(qualifying)
        components = list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]
        components = sorted(components, key=lambda g: (-g.area, g.bounds))
        retained = []
        for component in components:
            # Cell count is approximated by area; edge cells are clipped at township boundary.
            equivalent_cells = component.area / (cell_m * cell_m)
            if equivalent_cells >= min_cells:
                retained.append(component)
        diagnostics[town_id] = {
            "status": "derived" if retained else "no_cluster_meets_minimum_area",
            "qualifying_cells": len(qualifying),
            "retained_clusters": len(retained),
            "mapped_polygon_buildings_intersecting_township": len(subset),
        }
        for rank, geom in enumerate(retained, 1):
            records.append({
                "town_id": town_id,
                "candidate_name_en": str(town.candidate_name_en),
                "cluster_id": f"{town_id}_cluster_{rank:03d}",
                "area_km2": geom.area / 1e6,
                "geometry": geom,
            })
    if not records:
        raise RuntimeError("No analytical clusters delineated; inspect thresholds and OSM coverage")
    frame = gpd.GeoDataFrame(records, crs=CRS)
    if not frame.geometry.is_valid.all() or frame.geometry.is_empty.any():
        raise RuntimeError("Invalid analytical cluster geometries")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    frame.to_file(output_path, layer="analytical_urban_clusters", driver="GPKG", index=False)
    check = gpd.read_file(output_path, layer="analytical_urban_clusters")
    if len(check) != len(frame) or check.crs.to_epsg() != 3826 or not check.geometry.is_valid.all():
        raise RuntimeError("GeoPackage read-back validation failed")
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "technical_validation_only",
        "inputs": {
            "candidate_boundaries": {"path": str(boundaries_path), "sha256": digest(boundaries_path)},
            "osm_buildings": {"path": str(buildings_path), "sha256": digest(buildings_path)},
        },
        "parameters": {
            "grid_cell_m": cell_m, "min_polygon_footprints_per_cell": min_footprints,
            "min_union_building_coverage": min_coverage,
            "min_cluster_equivalent_full_cells": min_cells,
            "connectivity": "polygon shared edge or vertex via unary_union",
        },
        "candidates": diagnostics,
        "output": {"path": str(output_path), "sha256": digest(output_path),
                   "feature_count": len(check), "crs": CRS},
        "limitations": [
            "Derived OSM building-density clusters, not official urban planning boundaries.",
            "Mapped building completeness is unverified and varies spatially.",
            "No road connectivity, critical facilities, flood or terrain criteria included in delineation.",
            "Clusters are not township rankings or evidence of electrical feasibility.",
            "Touching cells may connect at a single point; inspect geometry before grid placement.",
        ],
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--boundaries", type=Path, default=BOUNDARIES)
    p.add_argument("--buildings", type=Path, default=BUILDINGS)
    p.add_argument("--output", type=Path, default=OUTPUT)
    p.add_argument("--report", type=Path, default=REPORT)
    p.add_argument("--cell-m", type=int, default=250)
    p.add_argument("--min-footprints", type=int, default=3)
    p.add_argument("--min-coverage", type=float, default=0.015)
    p.add_argument("--min-cells", type=int, default=4)
    a = p.parse_args()
    result = delineate(a.boundaries.resolve(), a.buildings.resolve(),
                       a.output.resolve(), a.report.resolve(),
                       a.cell_m, a.min_footprints, a.min_coverage, a.min_cells)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
