"""Screen frozen Minxiong clusters against checked-in Global Flood Database events.

This is retrospective raster-observation screening, not a flood forecast,
hydraulic model, or final suitability score. NaN pixels remain unknown.
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
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parents[1]
CLUSTERS = ROOT / "data/geospatial/processed/chiayi_analytical_urban_clusters.gpkg"
FLOOD_DIR = ROOT / "data/globalflooddb"
OUTPUT_CSV = ROOT / "reports/geospatial/minxiong_flood_event_screening.csv"
OUTPUT_JSON = ROOT / "reports/geospatial/minxiong_flood_event_screening.json"
TARGET_CRS = "EPSG:3826"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_clusters(path: Path) -> gpd.GeoDataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Cluster GeoPackage not found: {path}")
    frame = gpd.read_file(path, layer="analytical_urban_clusters")
    if frame.empty or frame.crs is None:
        raise ValueError("Cluster layer must be non-empty and have a CRS")
    if not frame.geometry.is_valid.all() or frame.geometry.is_empty.any():
        raise ValueError("Cluster layer contains invalid or empty geometry")
    required = {"town_id", "cluster_id"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Cluster layer missing fields: {sorted(missing)}")
    frame = frame.loc[frame.town_id.astype(str) == "Q05"].copy()
    if len(frame) != 9 or frame.cluster_id.astype(str).duplicated().any():
        raise ValueError(f"Expected exactly nine unique frozen Q05 clusters; found {len(frame)}")
    return frame.to_crs("EPSG:4326")


def event_metadata(raster_path: Path) -> dict[str, Any]:
    candidates = list(raster_path.parent.glob("*_properties.json"))
    if len(candidates) != 1:
        raise ValueError(f"Expected one event properties JSON beside {raster_path}; found {len(candidates)}")
    return json.loads(candidates[0].read_text(encoding="utf-8"))


def summarize_event_cluster(dataset: rasterio.io.DatasetReader, polygon: Any) -> dict[str, Any]:
    if dataset.crs is None:
        raise ValueError(f"Raster has no CRS: {dataset.name}")
    if dataset.count < 5:
        raise ValueError(f"Expected five GFD bands in {dataset.name}; found {dataset.count}")
    geom = gpd.GeoSeries([polygon], crs="EPSG:4326").to_crs(dataset.crs).iloc[0]
    if not geom.intersects(gpd.GeoSeries.from_bbox(dataset.bounds).iloc[0]):
        return {"raster_grid_pixels_in_cluster": 0, "event_finite_pixels": 0,
                "flooded_pixels": None, "flooded_share_of_finite_pixels": None,
                "event_observation_coverage_share": 0.0,
                "mean_clear_views": None, "mean_clear_perc": None,
                "mean_flood_duration_composite_days": None,
                "permanent_water_finite_pixels": 0, "permanent_water_pixels": None,
                "status": "no_raster_bounds_overlap"}

    window = from_bounds(*geom.bounds, transform=dataset.transform)
    window = window.round_offsets().round_lengths()
    window = window.intersection(rasterio.windows.Window(0, 0, dataset.width, dataset.height))
    if window.width <= 0 or window.height <= 0:
        return {"raster_grid_pixels_in_cluster": 0, "event_finite_pixels": 0,
                "flooded_pixels": None, "flooded_share_of_finite_pixels": None,
                "event_observation_coverage_share": 0.0,
                "mean_clear_views": None, "mean_clear_perc": None,
                "mean_flood_duration_composite_days": None,
                "permanent_water_finite_pixels": 0, "permanent_water_pixels": None,
                "status": "no_raster_grid_overlap"}
    transform = dataset.window_transform(window)
    shape = (int(window.height), int(window.width))
    inside = geometry_mask([geom.__geo_interface__], out_shape=shape,
                           transform=transform, invert=True, all_touched=False)
    arrays = [dataset.read(i, window=window, masked=False).astype("float64") for i in range(1, 6)]
    flooded, duration, clear_views, clear_perc, permanent = arrays
    event_finite = inside & np.isfinite(flooded) & np.isfinite(duration) & np.isfinite(clear_views) & np.isfinite(clear_perc)
    perm_finite = inside & np.isfinite(permanent)
    n_grid = int(inside.sum())
    n_finite = int(event_finite.sum())
    n_flood = int((event_finite & (flooded == 1)).sum())
    n_perm_finite = int(perm_finite.sum())
    n_perm = int((perm_finite & (permanent == 1)).sum())
    def mean_or_none(values: np.ndarray, mask: np.ndarray) -> float | None:
        return float(np.mean(values[mask])) if mask.any() else None
    return {
        "raster_grid_pixels_in_cluster": n_grid,
        "event_finite_pixels": n_finite,
        "event_observation_coverage_share": n_finite / n_grid if n_grid else None,
        "flooded_pixels": n_flood if n_finite else None,
        "flooded_share_of_finite_pixels": n_flood / n_finite if n_finite else None,
        "mean_flood_duration_composite_days": mean_or_none(duration, event_finite),
        "mean_clear_views": mean_or_none(clear_views, event_finite),
        "mean_clear_perc": mean_or_none(clear_perc, event_finite),
        "permanent_water_finite_pixels": n_perm_finite,
        "permanent_water_pixels": n_perm if n_perm_finite else None,
        "status": "observed_pixels_available" if n_finite else "no_finite_event_observations",
    }


def screen(clusters_path: Path = CLUSTERS, flood_dir: Path = FLOOD_DIR,
           output_csv: Path = OUTPUT_CSV, output_json: Path = OUTPUT_JSON) -> dict[str, Any]:
    clusters = load_clusters(clusters_path)
    rasters = sorted(flood_dir.glob("*/*.tif"))
    if not rasters:
        raise FileNotFoundError(f"No event GeoTIFFs found under {flood_dir}")
    rows: list[dict[str, Any]] = []
    event_inputs: list[dict[str, Any]] = []
    for raster_path in rasters:
        metadata = event_metadata(raster_path)
        event_id = metadata.get("id", raster_path.parent.name)
        with rasterio.open(raster_path) as ds:
            if ds.count < 5:
                raise ValueError(f"Expected five GFD bands: {raster_path}")
            event_record = {
                "event_id": event_id, "began": metadata.get("began"),
                "ended": metadata.get("ended"), "cause": metadata.get("dfo_main_cause"),
                "country": metadata.get("dfo_country"), "raster_path": str(raster_path.relative_to(ROOT)),
                "raster_sha256": sha256_file(raster_path), "crs": ds.crs.to_string(),
                "bounds": list(ds.bounds), "pixel_size": list(ds.res),
            }
            event_inputs.append(event_record)
            for _, cluster in clusters.sort_values("cluster_id").iterrows():
                metrics = summarize_event_cluster(ds, cluster.geometry)
                rows.append({
                    "cluster_id": str(cluster.cluster_id), "event_id": event_id,
                    "event_start": metadata.get("began"), "event_end": metadata.get("ended"),
                    "event_cause": metadata.get("dfo_main_cause"), **metrics,
                })
    result = pd.DataFrame(rows).sort_values(["cluster_id", "event_start", "event_id"])
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_csv, index=False, encoding="utf-8-sig")
    report = {
        "schema_version": "1.0",
        "project": "LAST — Minxiong historical flood-event screening",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "historical_event_raster_screening_generated",
        "study_area": {"town_id": "Q05", "township": "Minxiong Township (民雄鄉)",
                       "cluster_count": int(clusters.shape[0]), "cluster_crs": TARGET_CRS},
        "inputs": {
            "clusters": {"path": str(clusters_path), "sha256": sha256_file(clusters_path),
                         "layer": "analytical_urban_clusters"},
            "events": event_inputs,
        },
        "band_interpretation": {
            "flooded": "Maximum observed event flood extent; 1 indicates water, not depth.",
            "duration": "Number of composite days classified as water; not continuous hourly duration.",
            "clear_views": "Cloud-free observation count; quality context.",
            "clear_perc": "Clear-observation percentage; quality context.",
            "jrc_perm_water": "Separate permanent-water classification; not event flood extent.",
        },
        "outputs": {"csv": str(output_csv), "csv_sha256": sha256_file(output_csv),
                    "json": str(output_json)},
        "terrain_status": "not_assessed_no_verified_dem_in_repository",
        "limitations": [
            "Historical event maxima are not flood forecasts, flood depth, return periods, or hydraulic simulations.",
            "Only finite raster pixels are used for event-band summaries; unmasked NaNs remain unknown and are excluded, never converted to zero.",
            "Observation coverage share is the fraction of raster grid-cell centers inside the cluster with finite event-band values; it is not proof of complete satellite observation.",
            "Flooded share is conditional on finite event pixels and must be interpreted with clear_views and clear_perc.",
            "Permanent-water values are summarized separately and are not subtracted from or merged into the event flood mask.",
            "The checked-in event collection is not an exhaustive historical flood inventory for Minxiong.",
            "Terrain/slope is not calculated because no verified DEM/DTM raster is currently checked into the repository.",
            "No six-criterion weighted suitability score or final cluster selection is produced.",
        ],
        "results": result.to_dict(orient="records"),
        "decision_status": "flood_observation_screening_only_terrain_pending_no_final_cluster_selected",
    }
    output_json.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clusters", type=Path, default=CLUSTERS)
    parser.add_argument("--flood-dir", type=Path, default=FLOOD_DIR)
    parser.add_argument("--output-csv", type=Path, default=OUTPUT_CSV)
    parser.add_argument("--output-json", type=Path, default=OUTPUT_JSON)
    args = parser.parse_args()
    report = screen(args.clusters.resolve(), args.flood_dir.resolve(),
                    args.output_csv.resolve(), args.output_json.resolve())
    print(json.dumps({"status": report["status"],
                      "cluster_count": report["study_area"]["cluster_count"],
                      "event_count": len(report["inputs"]["events"]),
                      "csv": report["outputs"]["csv"],
                      "json": report["outputs"]["json"],
                      "decision_status": report["decision_status"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
