"""Create a synthetic IEEE 33-bus spatial placement inside Q05_cluster_001.

This creates geographic visualization coordinates only. It does not infer
actual Taipower assets, electrical impedances, feeder routes, load locations,
or operational feasibility. Electrical topology is stored separately from
straight-line map connectors.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
CLUSTERS = ROOT / "data/geospatial/processed/chiayi_analytical_urban_clusters.gpkg"
ROADS = ROOT / "data/geospatial/raw/osm/roads/osm_chiayi_roads_edges.gpkg"
OUT_GPKG = ROOT / "data/geospatial/processed/minxiong_cluster_001_ieee33_synthetic.gpkg"
OUT_CSV = ROOT / "reports/geospatial/minxiong_cluster_001_ieee33_bus_locations.csv"
OUT_JSON = ROOT / "reports/geospatial/minxiong_cluster_001_ieee33_placement.json"
CRS = "EPSG:3826"
CLUSTER_ID = "Q05_cluster_001"

# Standard 33-bus radial benchmark branch set (32 normally-closed branches).
IEEE33_BRANCHES = (
    (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 9),
    (9, 10), (10, 11), (11, 12), (12, 13), (13, 14), (14, 15),
    (15, 16), (16, 17), (17, 18), (2, 19), (19, 20), (20, 21),
    (21, 22), (3, 23), (23, 24), (24, 25), (6, 26), (26, 27),
    (27, 28), (28, 29), (29, 30), (30, 31), (31, 32), (32, 33),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def line_parts(geometry) -> Iterable[LineString]:
    if geometry is None or geometry.is_empty:
        return
    if geometry.geom_type == "LineString":
        if geometry.length > 0:
            yield geometry
    elif geometry.geom_type == "MultiLineString":
        for part in geometry.geoms:
            if part.length > 0:
                yield part
    elif geometry.geom_type == "GeometryCollection":
        for part in geometry.geoms:
            yield from line_parts(part)


def sample_road_candidates(roads: gpd.GeoDataFrame, polygon, spacing_m: float = 60.0) -> list[Point]:
    """Sample deterministic candidate points along clipped OSM road geometries."""
    if spacing_m <= 0:
        raise ValueError("spacing_m must be positive")
    candidates: dict[tuple[int, int], Point] = {}
    for geometry in roads.geometry:
        clipped = geometry.intersection(polygon)
        for line in line_parts(clipped):
            count = max(1, int(math.ceil(line.length / spacing_m)))
            for index in range(count + 1):
                point = line.interpolate(min(index * spacing_m, line.length))
                if polygon.covers(point):
                    key = (round(point.x * 1000), round(point.y * 1000))
                    candidates[key] = point
    if not candidates:
        raise ValueError("No candidate placement points were found on roads inside the selected cluster")
    return [candidates[key] for key in sorted(candidates)]


def select_spread_points(candidates: list[Point], anchor: Point, count: int = 33) -> list[Point]:
    """Greedy farthest-point sampling; stable tie-breaking by candidate order."""
    if count < 1:
        raise ValueError("count must be at least one")
    if len(candidates) < count:
        raise ValueError(f"Need at least {count} unique road candidates; found {len(candidates)}")
    selected_indices: list[int] = []
    first = min(range(len(candidates)), key=lambda i: (candidates[i].distance(anchor), i))
    selected_indices.append(first)
    min_distances = [point.distance(candidates[first]) for point in candidates]
    min_distances[first] = -1.0
    while len(selected_indices) < count:
        next_index = max(range(len(candidates)), key=lambda i: (min_distances[i], -i))
        selected_indices.append(next_index)
        chosen = candidates[next_index]
        for index, point in enumerate(candidates):
            if min_distances[index] >= 0:
                min_distances[index] = min(min_distances[index], point.distance(chosen))
        min_distances[next_index] = -1.0
    return [candidates[index] for index in selected_indices]


def build_placement(cluster_path: Path = CLUSTERS, roads_path: Path = ROADS,
                    output_gpkg: Path = OUT_GPKG, output_csv: Path = OUT_CSV,
                    output_json: Path = OUT_JSON, spacing_m: float = 60.0) -> dict:
    for path, label in ((cluster_path, "cluster"), (roads_path, "roads")):
        if not path.is_file():
            raise FileNotFoundError(f"{label} input not found: {path}")
    clusters = gpd.read_file(cluster_path, layer="analytical_urban_clusters")
    roads = gpd.read_file(roads_path, layer="osm_chiayi_roads_edges")
    for frame, label in ((clusters, "cluster"), (roads, "road")):
        if frame.empty or frame.crs is None:
            raise ValueError(f"{label} layer must be non-empty and have a CRS")
        if frame.geometry.isna().any() or frame.geometry.is_empty.any() or not frame.geometry.is_valid.all():
            raise ValueError(f"{label} layer contains null, empty, or invalid geometries")
    if not {"town_id", "cluster_id"}.issubset(clusters.columns):
        raise ValueError("Cluster layer requires town_id and cluster_id fields")
    selected = clusters.loc[
        (clusters.town_id.astype(str) == "Q05") &
        (clusters.cluster_id.astype(str) == CLUSTER_ID)
    ].copy()
    if len(selected) != 1:
        raise ValueError(f"Expected exactly one frozen {CLUSTER_ID}; found {len(selected)}")
    if not roads.geometry.geom_type.isin(["LineString", "MultiLineString"]).all():
        raise ValueError("OSM roads layer must contain only LineString/MultiLineString geometries")

    polygon = selected.to_crs(CRS).geometry.iloc[0]
    roads = roads.to_crs(CRS)
    clipped_roads = roads.loc[roads.geometry.intersects(polygon)].copy()
    clipped_roads.geometry = clipped_roads.geometry.intersection(polygon)
    clipped_roads = clipped_roads.loc[~clipped_roads.geometry.is_empty].copy()
    if clipped_roads.empty:
        raise ValueError(f"No OSM road geometries intersect {CLUSTER_ID}")

    candidates = sample_road_candidates(clipped_roads, polygon, spacing_m)
    anchor = polygon.centroid
    points = select_spread_points(candidates, anchor, 33)
    bus_rows = []
    for bus_id, point in enumerate(points, start=1):
        lon, lat = gpd.GeoSeries([point], crs=CRS).to_crs("EPSG:4326").iloc[0].coords[0]
        bus_rows.append({
            "bus_id": bus_id,
            "bus_role": "slack_reference" if bus_id == 1 else "synthetic_load_bus",
            "cluster_id": CLUSTER_ID,
            "x_epsg3826_m": float(point.x),
            "y_epsg3826_m": float(point.y),
            "longitude": float(lon),
            "latitude": float(lat),
            "placement_basis": "farthest_point_sampled_on_clipped_osm_road_geometry",
        })
    bus_table = pd.DataFrame(bus_rows)
    bus_gdf = gpd.GeoDataFrame(bus_table, geometry=points, crs=CRS)

    point_by_bus = {row["bus_id"]: point for row, point in zip(bus_rows, points)}
    branch_rows = []
    branch_geometries = []
    for branch_id, (from_bus, to_bus) in enumerate(IEEE33_BRANCHES, start=1):
        line = LineString([point_by_bus[from_bus], point_by_bus[to_bus]])
        branch_geometries.append(line)
        branch_rows.append({
            "branch_id": branch_id,
            "from_bus": from_bus,
            "to_bus": to_bus,
            "topology_source": "standard_ieee_33_bus_radial_branch_list",
            "geometry_semantics": "straight_line_map_connector_not_electrical_asset",
        })
    branch_gdf = gpd.GeoDataFrame(branch_rows, geometry=branch_geometries, crs=CRS)

    output_gpkg.parent.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    if output_gpkg.exists():
        output_gpkg.unlink()
    bus_gdf.to_file(output_gpkg, layer="synthetic_bus_locations", driver="GPKG")
    branch_gdf.to_file(output_gpkg, layer="synthetic_topology_connectors", driver="GPKG", mode="a")
    bus_table.to_csv(output_csv, index=False, encoding="utf-8-sig")

    pair_set = set(IEEE33_BRANCHES)
    node_set = {node for edge in IEEE33_BRANCHES for node in edge}
    report = {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "synthetic_geographic_placement_generated",
        "study_area": {"township": "Minxiong Township (Q05)", "cluster_id": CLUSTER_ID, "crs": CRS},
        "benchmark": {"name": "IEEE 33-bus radial distribution test system", "bus_count": 33,
                      "branch_count": 32, "slack_reference_bus": 1,
                      "topology_edges": [list(edge) for edge in IEEE33_BRANCHES]},
        "placement": {"method": "deterministic greedy farthest-point sampling on clipped OSM road geometry",
                      "candidate_spacing_m": spacing_m, "candidate_count": len(candidates),
                      "bus_1_anchor": "road candidate nearest selected cluster centroid",
                      "bus_ids_2_to_33": "iterative maximum-minimum Euclidean separation among remaining road candidates",
                      "minimum_bus_separation_m": min(
                          points[i].distance(points[j])
                          for i in range(len(points)) for j in range(i + 1, len(points))
                      )},
        "inputs": {"cluster_path": str(cluster_path), "cluster_sha256": sha256_file(cluster_path),
                   "cluster_layer": "analytical_urban_clusters", "roads_path": str(roads_path),
                   "roads_sha256": sha256_file(roads_path), "roads_layer": "osm_chiayi_roads_edges"},
        "outputs": {"gpkg": str(output_gpkg), "bus_csv": str(output_csv)},
        "validation": {"bus_ids_complete_1_to_33": sorted(bus_table.bus_id.tolist()) == list(range(1, 34)),
                       "all_bus_points_within_cluster": all(polygon.covers(point) for point in points),
                       "all_bus_points_on_clipped_road_candidates": True,
                       "branch_count_32": len(IEEE33_BRANCHES) == 32,
                       "topology_nodes_1_to_33": node_set == set(range(1, 34)),
                       "unique_topology_edges": len(pair_set) == 32},
        "limitations": [
            "The benchmark is synthetic and georeferenced for research visualization; it is not an actual Taipower feeder or service territory.",
            "OSM roads are contextual geometry only. Bus placement on road lines does not imply electrical assets, poles, substations, or utility right-of-way.",
            "Bus 1 is a geographic slack-reference anchor only; its coordinate is not a verified substation location.",
            "Bus locations are generated by geometric spacing, not customer/load census, asset inventory, engineering siting, or electrical optimization.",
            "Straight-line map connectors visualize the standard IEEE 33-bus branch topology; they are not conductor routes, cable lengths, impedances, or electrical infrastructure.",
            "No voltage, power-flow, protection, reliability, islanding, BESS, or operational feasibility is validated by this spatial placement script.",
            "The LLM remains advisory only; operational decisions require deterministic engineering validation and authorized operator action.",
        ],
        "decision_status": "initial_synthetic_placement_only_requires_review",
    }
    output_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clusters", type=Path, default=CLUSTERS)
    parser.add_argument("--roads", type=Path, default=ROADS)
    parser.add_argument("--output-gpkg", type=Path, default=OUT_GPKG)
    parser.add_argument("--output-csv", type=Path, default=OUT_CSV)
    parser.add_argument("--output-json", type=Path, default=OUT_JSON)
    parser.add_argument("--candidate-spacing-m", type=float, default=60.0)
    args = parser.parse_args()
    report = build_placement(args.clusters.resolve(), args.roads.resolve(),
                             args.output_gpkg.resolve(), args.output_csv.resolve(),
                             args.output_json.resolve(), args.candidate_spacing_m)
    print(json.dumps({"status": report["status"], "cluster_id": CLUSTER_ID,
                      "bus_count": report["benchmark"]["bus_count"],
                      "branch_count": report["benchmark"]["branch_count"],
                      "candidate_count": report["placement"]["candidate_count"],
                      "minimum_bus_separation_m": report["placement"]["minimum_bus_separation_m"],
                      "gpkg": report["outputs"]["gpkg"], "csv": report["outputs"]["bus_csv"],
                      "decision_status": report["decision_status"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
