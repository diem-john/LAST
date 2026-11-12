"""Screen the frozen Minxiong analytical urban clusters using OSM context layers.

Run from the repository root:
    python scripts/screen_minxiong_clusters.py

Outputs a per-cluster CSV and a provenance/limitations JSON report. This is
descriptive spatial screening, not a weighted suitability score or site
selection. OSM roads are not electrical assets; OSM hospitals are discovery
features only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLUSTERS = ROOT / "data/geospatial/processed/chiayi_analytical_urban_clusters.gpkg"
ROADS = ROOT / "data/geospatial/raw/osm/roads/osm_chiayi_roads_edges.gpkg"
HOSPITALS = ROOT / "data/geospatial/raw/osm/facilities/osm_chiayi_hospitals.gpkg"
OUTPUT_CSV = ROOT / "reports/geospatial/minxiong_cluster_screening.csv"
OUTPUT_JSON = ROOT / "reports/geospatial/minxiong_cluster_screening.json"
CRS = "EPSG:3826"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_projected(path: Path, layer: str | None, label: str) -> gpd.GeoDataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"{label} input not found: {path}")
    frame = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
    if frame.empty:
        raise ValueError(f"{label} input contains no features")
    if frame.crs is None:
        raise ValueError(f"{label} input has no CRS")
    if frame.geometry.isna().any() or frame.geometry.is_empty.any():
        raise ValueError(f"{label} input contains missing or empty geometries")
    if not frame.geometry.is_valid.all():
        raise ValueError(f"{label} input contains invalid geometries")
    return frame.to_crs(CRS)


def screen_clusters(
    clusters_path: Path = CLUSTERS,
    roads_path: Path = ROADS,
    hospitals_path: Path = HOSPITALS,
    output_csv: Path = OUTPUT_CSV,
    output_json: Path = OUTPUT_JSON,
) -> dict[str, Any]:
    clusters = load_projected(clusters_path, "analytical_urban_clusters", "Cluster")
    roads = load_projected(roads_path, "osm_chiayi_roads_edges", "Road")
    hospitals = load_projected(hospitals_path, "osm_chiayi_hospitals", "Hospital")

    required = {"town_id", "cluster_id"}
    missing = required.difference(clusters.columns)
    if missing:
        raise ValueError(f"Cluster layer is missing required fields: {sorted(missing)}")
    clusters = clusters.loc[clusters["town_id"].astype(str) == "Q05"].copy()
    if len(clusters) != 9:
        raise ValueError(f"Expected the frozen nine Minxiong clusters (Q05); found {len(clusters)}")
    if clusters["cluster_id"].astype(str).duplicated().any():
        raise ValueError("Minxiong cluster_id values must be unique")
    if not roads.geometry.geom_type.isin(["LineString", "MultiLineString"]).all():
        raise ValueError("Road layer must contain only LineString/MultiLineString geometries")
    if not hospitals.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise ValueError("Hospital layer must contain only Polygon/MultiPolygon geometries")

    records: list[dict[str, Any]] = []
    for _, cluster in clusters.sort_values("cluster_id").iterrows():
        polygon = cluster.geometry
        area_m2 = float(polygon.area)
        perimeter_m = float(polygon.length)
        if area_m2 <= 0 or perimeter_m <= 0:
            raise ValueError(f"Cluster {cluster.cluster_id} has non-positive area/perimeter")

        road_candidates = roads.loc[roads.geometry.intersects(polygon)]
        clipped_lengths = [
            float(geom.intersection(polygon).length)
            for geom in road_candidates.geometry
        ]
        road_length_m = float(sum(length for length in clipped_lengths if math.isfinite(length)))
        road_density_km_per_km2 = (road_length_m / 1000.0) / (area_m2 / 1_000_000.0)

        hospital_intersections = hospitals.loc[hospitals.geometry.intersects(polygon)]
        distances = hospitals.geometry.distance(polygon)
        nearest_idx = distances.idxmin()
        nearest_distance_m = float(distances.loc[nearest_idx])
        largest_component_area = max(
            (part.area for part in (list(polygon.geoms) if polygon.geom_type == "MultiPolygon" else [polygon])),
            default=0.0,
        )
        records.append({
            "town_id": "Q05",
            "township": "Minxiong Township (民雄鄉)",
            "cluster_id": str(cluster.cluster_id),
            "area_km2": area_m2 / 1_000_000.0,
            "perimeter_km": perimeter_m / 1000.0,
            "compactness_4piA_over_P2": (4.0 * math.pi * area_m2) / (perimeter_m ** 2),
            "largest_component_area_share": largest_component_area / area_m2,
            "intersecting_osm_road_features": int(len(road_candidates)),
            "clipped_osm_road_length_km": road_length_m / 1000.0,
            "osm_road_length_density_km_per_km2": road_density_km_per_km2,
            "intersecting_osm_hospital_features": int(len(hospital_intersections)),
            "nearest_osm_hospital_polygon_distance_km": nearest_distance_m / 1000.0,
        })

    result = pd.DataFrame.from_records(records).sort_values("cluster_id")
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_csv, index=False, encoding="utf-8-sig")

    inputs = {
        "clusters": {"path": str(clusters_path), "sha256": sha256_file(clusters_path),
                     "layer": "analytical_urban_clusters"},
        "roads": {"path": str(roads_path), "sha256": sha256_file(roads_path),
                  "layer": "osm_chiayi_roads_edges"},
        "hospitals": {"path": str(hospitals_path), "sha256": sha256_file(hospitals_path),
                      "layer": "osm_chiayi_hospitals"},
    }
    report = {
        "schema_version": "1.0",
        "project": "LAST — Minxiong analytical urban-cluster screening",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "descriptive_screening_metrics_generated",
        "study_area": {"town_id": "Q05", "township": "Minxiong Township (民雄鄉)",
                       "cluster_count": int(len(result)), "crs": CRS},
        "inputs": inputs,
        "metric_definitions": {
            "area_km2": "Projected polygon area in EPSG:3826.",
            "perimeter_km": "Projected polygon perimeter in EPSG:3826.",
            "compactness_4piA_over_P2": "4*pi*area/perimeter^2; approaches 1 for a circle.",
            "largest_component_area_share": "Largest polygon component area divided by total cluster area.",
            "clipped_osm_road_length_km": "Sum of OSM road-line lengths after geometric intersection with the cluster; overlapping source features may contribute separately.",
            "osm_road_length_density_km_per_km2": "Clipped OSM road length divided by cluster area.",
            "intersecting_osm_hospital_features": "Count of mapped hospital polygon features intersecting the cluster.",
            "nearest_osm_hospital_polygon_distance_km": "Minimum planar distance from cluster polygon to any mapped hospital polygon.",
        },
        "outputs": {
            "csv": str(output_csv),
            "csv_sha256": sha256_file(output_csv),
            "json": str(output_json),
        },
        "limitations": [
            "OSM road and hospital coverage/completeness are unverified and may vary spatially.",
            "Road length density is a geometric context proxy, not travel-time accessibility, graph routing quality, utility-corridor access, or electrical connectivity.",
            "OSM road features are not Taipower conductors, cables, poles, or verified utility corridors.",
            "OSM hospital features are discovery data; identity, operating status, service capacity, and official inventory status are not verified.",
            "Nearest-hospital distance is straight-line polygon-to-polygon distance, not road-network travel distance.",
            "A hospital count of zero means no mapped OSM hospital polygon intersects the cluster; it does not establish absence of healthcare facilities.",
            "Compactness is sensitive to boundary geometry and point-touching components; inspect largest_component_area_share before selecting a compact site.",
            "No flood, terrain, population, official planning, or six-criterion weighted suitability score is calculated.",
            "These metrics screen the nine frozen Minxiong clusters only; they do not re-rank the four townships or select a final network-placement cluster.",
            "The enhanced IEEE 33-bus network remains a synthetic Chiayi-georeferenced benchmark, not an actual Taipower feeder.",
        ],
        "results": result.to_dict(orient="records"),
        "decision_status": "screening_only_no_final_cluster_selected",
    }
    output_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clusters", type=Path, default=CLUSTERS)
    parser.add_argument("--roads", type=Path, default=ROADS)
    parser.add_argument("--hospitals", type=Path, default=HOSPITALS)
    parser.add_argument("--output-csv", type=Path, default=OUTPUT_CSV)
    parser.add_argument("--output-json", type=Path, default=OUTPUT_JSON)
    args = parser.parse_args()
    report = screen_clusters(args.clusters.resolve(), args.roads.resolve(),
                             args.hospitals.resolve(), args.output_csv.resolve(),
                             args.output_json.resolve())
    print(json.dumps({
        "status": report["status"],
        "cluster_count": report["study_area"]["cluster_count"],
        "csv": report["outputs"]["csv"],
        "json": report["outputs"]["json"],
        "decision_status": report["decision_status"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
