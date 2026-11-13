"""Visualize and audit the synthetic IEEE 33-bus placement for Phase 5B.

The output is a cartographic review aid, not an electrical validation.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
from shapely.geometry import LineString

ROOT = Path(__file__).resolve().parents[1]
PLACEMENT = ROOT / "data/geospatial/processed/minxiong_cluster_001_ieee33_synthetic.gpkg"
CLUSTERS = ROOT / "data/geospatial/processed/chiayi_analytical_urban_clusters.gpkg"
ROADS = ROOT / "data/geospatial/raw/osm/roads/osm_chiayi_roads_edges.gpkg"
OUT_MAP = ROOT / "reports/geospatial/minxiong_cluster_001_ieee33_network_map.png"
OUT_REVIEW = ROOT / "reports/geospatial/minxiong_cluster_001_ieee33_spatial_review.json"
OUT_CSV = ROOT / "reports/geospatial/minxiong_cluster_001_ieee33_branch_review.csv"
CLUSTER_ID = "Q05_cluster_001"
CRS = "EPSG:3826"


def count_nonincident_connector_crossings(branches: gpd.GeoDataFrame) -> list[dict]:
    """Find geometric crossings between connectors with no shared endpoint bus."""
    records = []
    rows = list(branches.iterrows())
    for i, (_, a) in enumerate(rows):
        for _, b in rows[i + 1:]:
            shared = {int(a.from_bus), int(a.to_bus)} & {int(b.from_bus), int(b.to_bus)}
            if shared:
                continue
            intersection = a.geometry.intersection(b.geometry)
            if not intersection.is_empty:
                # A point crossing is reported; collinear overlap is separately flagged.
                if intersection.geom_type == "Point":
                    records.append({
                        "branch_a": int(a.branch_id), "branch_b": int(b.branch_id),
                        "from_a": int(a.from_bus), "to_a": int(a.to_bus),
                        "from_b": int(b.from_bus), "to_b": int(b.to_bus),
                        "intersection_type": "nonincident_point_crossing",
                    })
                elif intersection.geom_type in {"LineString", "MultiLineString"} and intersection.length > 0:
                    records.append({
                        "branch_a": int(a.branch_id), "branch_b": int(b.branch_id),
                        "from_a": int(a.from_bus), "to_a": int(a.to_bus),
                        "from_b": int(b.from_bus), "to_b": int(b.to_bus),
                        "intersection_type": "nonincident_collinear_overlap",
                    })
    return records


def validate_layers(cluster: gpd.GeoDataFrame, buses: gpd.GeoDataFrame,
                    branches: gpd.GeoDataFrame) -> dict:
    if len(cluster) != 1:
        raise ValueError(f"Expected one selected cluster polygon; found {len(cluster)}")
    if len(buses) != 33:
        raise ValueError(f"Expected 33 bus points; found {len(buses)}")
    if len(branches) != 32:
        raise ValueError(f"Expected 32 topology connectors; found {len(branches)}")
    required_bus = {"bus_id", "bus_role"}
    required_branch = {"branch_id", "from_bus", "to_bus"}
    if not required_bus.issubset(buses.columns) or not required_branch.issubset(branches.columns):
        raise ValueError("Placement layers are missing required bus or branch attributes")
    if sorted(buses.bus_id.astype(int).tolist()) != list(range(1, 34)):
        raise ValueError("Bus IDs must be unique and complete from 1 through 33")
    if buses.crs is None or branches.crs is None or cluster.crs is None:
        raise ValueError("All input layers must declare a CRS")
    polygon = cluster.to_crs(CRS).geometry.iloc[0]
    bus_metric = buses.to_crs(CRS)
    within = [bool(polygon.covers(point)) for point in bus_metric.geometry]
    if not all(within):
        raise ValueError("One or more bus points fall outside the selected cluster")
    return {
        "bus_count": len(buses),
        "branch_count": len(branches),
        "bus_ids_complete_1_to_33": True,
        "all_bus_points_within_cluster": all(within),
        "unique_bus_coordinates": int(bus_metric.geometry.nunique()),
        "minimum_pairwise_bus_separation_m": float(min(
            bus_metric.geometry.iloc[i].distance(bus_metric.geometry.iloc[j])
            for i in range(len(bus_metric)) for j in range(i + 1, len(bus_metric))
        )),
    }


def create_review(placement_path: Path = PLACEMENT, cluster_path: Path = CLUSTERS,
                  roads_path: Path = ROADS, output_map: Path = OUT_MAP,
                  output_review: Path = OUT_REVIEW, output_csv: Path = OUT_CSV) -> dict:
    for path in (placement_path, cluster_path, roads_path):
        if not path.is_file():
            raise FileNotFoundError(f"Required Phase 5A/ GIS input not found: {path}")
    buses = gpd.read_file(placement_path, layer="synthetic_bus_locations")
    branches = gpd.read_file(placement_path, layer="synthetic_topology_connectors")
    clusters = gpd.read_file(cluster_path, layer="analytical_urban_clusters")
    selected = clusters.loc[clusters.cluster_id.astype(str) == CLUSTER_ID].copy()
    if len(selected) != 1:
        raise ValueError(f"Expected exactly one frozen cluster {CLUSTER_ID}; found {len(selected)}")
    roads = gpd.read_file(roads_path, layer="osm_chiayi_roads_edges")
    checks = validate_layers(selected, buses, branches)
    polygon = selected.to_crs(CRS)
    bus_metric = buses.to_crs(CRS)
    branch_metric = branches.to_crs(CRS)
    roads_metric = roads.to_crs(CRS)
    roads_clip = roads_metric.loc[roads_metric.geometry.intersects(polygon.geometry.iloc[0])].copy()
    roads_clip.geometry = roads_clip.geometry.intersection(polygon.geometry.iloc[0])
    roads_clip = roads_clip.loc[~roads_clip.geometry.is_empty].copy()

    crossings = count_nonincident_connector_crossings(branch_metric)
    bus_by_id = bus_metric.set_index("bus_id")
    branch_rows = []
    for row in branch_metric.itertuples():
        a, b = bus_by_id.loc[int(row.from_bus)], bus_by_id.loc[int(row.to_bus)]
        branch_rows.append({
            "branch_id": int(row.branch_id), "from_bus": int(row.from_bus),
            "to_bus": int(row.to_bus), "connector_length_m": float(row.geometry.length),
            "straight_line_connector_only": True,
            "geometry_semantics": "not_an_electrical_route_or_conductor_length",
        })
    branch_table = pd.DataFrame(branch_rows)
    output_map.parent.mkdir(parents=True, exist_ok=True)
    output_review.parent.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    branch_table.to_csv(output_csv, index=False, encoding="utf-8-sig")

    fig, ax = plt.subplots(figsize=(12, 10), constrained_layout=True)
    roads_clip.plot(ax=ax, color="#c7cbd1", linewidth=0.45, alpha=0.8, zorder=1)
    polygon.boundary.plot(ax=ax, color="#30343b", linewidth=1.5, zorder=2)
    branch_metric.plot(ax=ax, color="#2878b5", linewidth=1.15, alpha=0.78, zorder=3)
    bus_metric.plot(ax=ax, color="#d1495b", markersize=34, edgecolor="white",
                    linewidth=0.55, zorder=4)
    for row in bus_metric.itertuples():
        ax.annotate(str(int(row.bus_id)), (row.geometry.x, row.geometry.y),
                    xytext=(3, 3), textcoords="offset points", fontsize=7,
                    color="#20242a", zorder=5)
    ax.set_title("Synthetic IEEE 33-Bus Geographic Placement\n"
                 "Q05_cluster_001 | Minxiong Township, Chiayi County", fontsize=14, pad=14)
    ax.set_xlabel("Easting (m) — EPSG:3826")
    ax.set_ylabel("Northing (m) — EPSG:3826")
    ax.set_aspect("equal")
    ax.grid(True, linewidth=0.35, alpha=0.35)
    ax.text(0.01, 0.01,
            "Synthetic benchmark coordinates; OSM roads are contextual only. "
            "Blue lines show abstract topology, not utility routes.",
            transform=ax.transAxes, fontsize=8, va="bottom",
            bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "none"})
    fig.savefig(output_map, dpi=300, bbox_inches="tight")
    plt.close(fig)

    report = {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "phase_5b_spatial_review_generated",
        "study_area": {"cluster_id": CLUSTER_ID, "crs": CRS},
        "validation": checks,
        "connector_geometry_review": {
            "nonincident_crossing_count": len(crossings),
            "nonincident_crossings": crossings,
            "interpretation": "Geometric intersections are cartographic review flags only; they do not imply electrical faults or physical conductor crossings."
        },
        "outputs": {"map": str(output_map), "branch_review_csv": str(output_csv)},
        "limitations": [
            "The 33 bus points are synthetic research coordinates, not actual Taipower assets or verified load locations.",
            "OSM roads provide geographic context only and are not electrical corridors.",
            "Straight-line connectors represent abstract IEEE 33-bus adjacency only; connector lengths are not conductor lengths or electrical impedances.",
            "This phase does not validate voltage, power flow, protection, reliability, islanding, BESS placement, or operational feasibility.",
            "Any crossing flag requires visual review and is not an automatic reason to move a bus or alter the benchmark topology."
        ],
        "decision_status": "visual_review_required_no_placement_acceptance_inferred"
    }
    output_review.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--placement", type=Path, default=PLACEMENT)
    parser.add_argument("--clusters", type=Path, default=CLUSTERS)
    parser.add_argument("--roads", type=Path, default=ROADS)
    parser.add_argument("--output-map", type=Path, default=OUT_MAP)
    parser.add_argument("--output-review", type=Path, default=OUT_REVIEW)
    parser.add_argument("--output-csv", type=Path, default=OUT_CSV)
    args = parser.parse_args()
    report = create_review(args.placement.resolve(), args.clusters.resolve(),
                           args.roads.resolve(), args.output_map.resolve(),
                           args.output_review.resolve(), args.output_csv.resolve())
    print(json.dumps({
        "status": report["status"],
        "cluster_id": CLUSTER_ID,
        "bus_count": report["validation"]["bus_count"],
        "branch_count": report["validation"]["branch_count"],
        "minimum_pairwise_bus_separation_m": report["validation"]["minimum_pairwise_bus_separation_m"],
        "nonincident_crossing_count": report["connector_geometry_review"]["nonincident_crossing_count"],
        "map": report["outputs"]["map"],
        "review_json": str(args.output_review.resolve()),
        "branch_review_csv": report["outputs"]["branch_review_csv"],
        "decision_status": report["decision_status"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
