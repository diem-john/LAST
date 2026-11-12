"""Map the nine frozen Minxiong analytical urban clusters with OSM context.

Run from the repository root:
    python scripts/visualize_minxiong_clusters.py

The map is descriptive. It highlights clusters 001, 002 and 009 as a
preliminary review shortlist, not as selected sites.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[1]
CLUSTERS = ROOT / "data/geospatial/processed/chiayi_analytical_urban_clusters.gpkg"
ROADS = ROOT / "data/geospatial/raw/osm/roads/osm_chiayi_roads_edges.gpkg"
HOSPITALS = ROOT / "data/geospatial/raw/osm/facilities/osm_chiayi_hospitals.gpkg"
METRICS = ROOT / "reports/geospatial/minxiong_cluster_screening.csv"
OUTPUT = ROOT / "reports/geospatial/minxiong_cluster_spatial_overview.png"
CRS = "EPSG:3826"
SHORTLIST = {"Q05_cluster_001", "Q05_cluster_002", "Q05_cluster_009"}


def read_layer(path: Path, layer: str) -> gpd.GeoDataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Required input not found: {path}")
    frame = gpd.read_file(path, layer=layer)
    if frame.empty:
        raise ValueError(f"Layer {layer!r} in {path} is empty")
    if frame.crs is None:
        raise ValueError(f"Layer {layer!r} has no CRS")
    if frame.geometry.isna().any() or frame.geometry.is_empty.any():
        raise ValueError(f"Layer {layer!r} contains empty geometries")
    if not frame.geometry.is_valid.all():
        raise ValueError(f"Layer {layer!r} contains invalid geometries")
    return frame.to_crs(CRS)


def create_map(
    clusters_path: Path = CLUSTERS,
    roads_path: Path = ROADS,
    hospitals_path: Path = HOSPITALS,
    metrics_path: Path = METRICS,
    output_path: Path = OUTPUT,
) -> Path:
    clusters = read_layer(clusters_path, "analytical_urban_clusters")
    roads = read_layer(roads_path, "osm_chiayi_roads_edges")
    hospitals = read_layer(hospitals_path, "osm_chiayi_hospitals")

    required = {"town_id", "cluster_id"}
    if not required.issubset(clusters.columns):
        raise ValueError(f"Cluster layer must contain {sorted(required)}")
    clusters = clusters.loc[clusters["town_id"].astype(str) == "Q05"].copy()
    if len(clusters) != 9:
        raise ValueError(f"Expected nine frozen Minxiong clusters; found {len(clusters)}")
    if not metrics_path.is_file():
        raise FileNotFoundError(
            f"Screening metrics not found: {metrics_path}. "
            "Run scripts/screen_minxiong_clusters.py first."
        )
    metrics = pd.read_csv(metrics_path)
    if "cluster_id" not in metrics.columns:
        raise ValueError("Metrics CSV must contain cluster_id")
    if metrics["cluster_id"].astype(str).duplicated().any():
        raise ValueError("Metrics CSV contains duplicate cluster_id values")

    # The frozen cluster GeoPackage already contains area_km2. Avoid merging
    # the full metrics table, which would create area_km2_x/area_km2_y and
    # make the original field name unavailable. The map only needs to verify
    # that the screening CSV covers exactly the same nine cluster IDs.
    cluster_ids = set(clusters["cluster_id"].astype(str))
    metric_ids = set(metrics["cluster_id"].astype(str))
    if cluster_ids != metric_ids:
        missing_metrics = sorted(cluster_ids - metric_ids)
        unexpected_metrics = sorted(metric_ids - cluster_ids)
        raise ValueError(
            "Screening CSV cluster IDs do not match the frozen cluster layer. "
            f"Missing metrics: {missing_metrics}; unexpected metrics: {unexpected_metrics}"
        )

    # Restrict context layers to the Minxiong extent plus a modest map margin.
    minx, miny, maxx, maxy = clusters.total_bounds
    dx, dy = maxx - minx, maxy - miny
    margin_x, margin_y = dx * 0.10, dy * 0.10
    bounds = (minx - margin_x, miny - margin_y, maxx + margin_x, maxy + margin_y)
    roads = roads.cx[bounds[0]:bounds[2], bounds[1]:bounds[3]]
    hospitals = hospitals.cx[bounds[0]:bounds[2], bounds[1]:bounds[3]]

    fig, ax = plt.subplots(figsize=(13, 10), constrained_layout=True)
    roads.plot(ax=ax, color="#9AA3AA", linewidth=0.42, alpha=0.65, zorder=1)

    other = clusters.loc[~clusters["cluster_id"].isin(SHORTLIST)]
    shortlist = clusters.loc[clusters["cluster_id"].isin(SHORTLIST)]
    if not other.empty:
        other.plot(ax=ax, facecolor="#DCE3E8", edgecolor="#52616B",
                   linewidth=1.1, alpha=0.78, zorder=2)
    candidate_styles = {
        "Q05_cluster_001": ("#F4A261", "001"),
        "Q05_cluster_002": ("#2A9D8F", "002"),
        "Q05_cluster_009": ("#E76F51", "009"),
    }
    for cluster_id, (color, _) in candidate_styles.items():
        part = shortlist.loc[shortlist["cluster_id"] == cluster_id]
        if not part.empty:
            part.plot(ax=ax, facecolor=color, edgecolor="#202A30",
                      linewidth=1.7, alpha=0.88, zorder=3)

    # Label all nine polygons at their representative points (inside geometry).
    for _, row in clusters.iterrows():
        point = row.geometry.representative_point()
        short_id = str(row["cluster_id"]).replace("Q05_cluster_", "")
        ax.annotate(
            short_id, (point.x, point.y), ha="center", va="center",
            fontsize=9, fontweight="bold", color="#17212B", zorder=5,
            bbox={"boxstyle": "round,pad=0.20", "fc": "white", "ec": "none", "alpha": 0.82},
        )

    if not hospitals.empty:
        hospital_points = hospitals.copy()
        hospital_points.geometry = hospital_points.geometry.representative_point()
        hospital_points.plot(ax=ax, color="#6A1B9A", marker="*", markersize=115,
                             edgecolor="white", linewidth=0.6, zorder=6)

    ax.set_xlim(bounds[0], bounds[2])
    ax.set_ylim(bounds[1], bounds[3])
    ax.set_aspect("equal")
    ax.set_xlabel("TWD97 / TM2 zone 121 (metres)")
    ax.set_ylabel("TWD97 / TM2 zone 121 (metres)")
    ax.set_title(
        "LAST Phase 4B — Minxiong Analytical Urban Clusters\n"
        "Preliminary shortlist highlighted; all nine clusters shown",
        fontsize=15, fontweight="bold", pad=14,
    )
    ax.grid(True, linestyle=":", linewidth=0.5, alpha=0.45)

    legend_items = [
        Patch(facecolor="#DCE3E8", edgecolor="#52616B", label="Other Minxiong clusters"),
        Patch(facecolor="#F4A261", edgecolor="#202A30", label="Cluster 001 — largest area / road length"),
        Patch(facecolor="#2A9D8F", edgecolor="#202A30", label="Cluster 002 — area and road-density candidate"),
        Patch(facecolor="#E76F51", edgecolor="#202A30", label="Cluster 009 — highest road-length density"),
        Line2D([0], [0], color="#9AA3AA", linewidth=1.2, label="OSM road features"),
        Line2D([0], [0], marker="*", color="w", markerfacecolor="#6A1B9A",
               markeredgecolor="white", markersize=13, label="Mapped OSM hospital polygon"),
    ]
    ax.legend(handles=legend_items, loc="best", frameon=True, framealpha=0.95, fontsize=8.5)

    fig.text(
        0.01, 0.005,
        "Source: frozen analytical clusters and OSM context layers in the LAST repository. "
        "OSM coverage is unverified; roads are not electrical assets; hospital markers are "
        "mapped OSM features only. Highlighting is a review shortlist, not a site decision. "
        "No flood or terrain screening is represented.",
        ha="left", va="bottom", fontsize=8, wrap=True,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clusters", type=Path, default=CLUSTERS)
    parser.add_argument("--roads", type=Path, default=ROADS)
    parser.add_argument("--hospitals", type=Path, default=HOSPITALS)
    parser.add_argument("--metrics", type=Path, default=METRICS)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = create_map(args.clusters.resolve(), args.roads.resolve(),
                        args.hospitals.resolve(), args.metrics.resolve(),
                        args.output.resolve())
    print(f"Map generated: {result}")
    print("Clusters shown: 9; preliminary shortlist: 001, 002, 009")
    print("Decision status: no final cluster selected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
