"""Map normalized environmental observations to the synthetic IEEE-33 asset sample points.

Input CSV schema:
timestamp,source_id,variable,value,spatial_scope,time_basis,temporal_semantics,
latitude,longitude
Required fields are listed in REQUIRED_COLUMNS. For regional records, coordinates may
be blank and the same regional observation is attached to every sample point.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUSES = ROOT / "reports/geospatial/minxiong_cluster_001_ieee33_bus_locations.csv"
DEFAULT_WEATHER = ROOT / "data/weather/normalized_weather_observations.csv"
DEFAULT_OUTPUT = ROOT / "reports/environmental/ieee33_weather_asset_features.csv"
CRS_TO_METRIC = Transformer.from_crs("EPSG:4326", "EPSG:3826", always_xy=True)
REQUIRED_COLUMNS = {
    "timestamp", "source_id", "variable", "value", "spatial_scope",
    "time_basis", "temporal_semantics",
}
ALLOWED_SCOPES = {"point", "regional"}


def build_asset_samples(bus_csv: Path) -> pd.DataFrame:
    buses = pd.read_csv(bus_csv)
    required = {"bus_id", "latitude", "longitude"}
    missing = required - set(buses.columns)
    if missing:
        raise ValueError(f"Bus-location CSV missing columns: {sorted(missing)}")
    if len(buses) != 33 or buses["bus_id"].nunique() != 33:
        raise ValueError("Expected exactly 33 unique synthetic bus locations")
    buses = buses.sort_values("bus_id").copy()
    buses["x_m"], buses["y_m"] = CRS_TO_METRIC.transform(
        buses["longitude"].astype(float).to_numpy(),
        buses["latitude"].astype(float).to_numpy(),
    )
    bus_records = []
    for row in buses.itertuples(index=False):
        bus_records.append({
            "asset_type": "bus", "asset_id": f"BUS_{int(row.bus_id):02d}",
            "bus_id": int(row.bus_id), "branch_id": None,
            "latitude": float(row.latitude), "longitude": float(row.longitude),
            "x_m": float(row.x_m), "y_m": float(row.y_m),
            "sample_location_semantics": "synthetic_bus_coordinate_not_verified_electrical_asset",
        })
    by_id = {int(row.bus_id): row for row in buses.itertuples(index=False)}
    branch_records = []
    # Standard IEEE 33-bus normally-closed radial branch list.
    edges = [
        (1,2),(2,3),(3,4),(4,5),(5,6),(6,7),(7,8),(8,9),(9,10),(10,11),
        (11,12),(12,13),(13,14),(14,15),(15,16),(16,17),(17,18),(2,19),
        (19,20),(20,21),(21,22),(3,23),(23,24),(24,25),(6,26),(26,27),
        (27,28),(28,29),(29,30),(30,31),(31,32),(32,33),
    ]
    for branch_id, (left, right) in enumerate(edges, start=1):
        a, b = by_id[left], by_id[right]
        x, y = (float(a.x_m) + float(b.x_m)) / 2, (float(a.y_m) + float(b.y_m)) / 2
        lon, lat = Transformer.from_crs("EPSG:3826", "EPSG:4326", always_xy=True).transform(x, y)
        branch_records.append({
            "asset_type": "branch_sample", "asset_id": f"BRANCH_{branch_id:02d}",
            "bus_id": None, "branch_id": branch_id,
            "latitude": float(lat), "longitude": float(lon), "x_m": x, "y_m": y,
            "sample_location_semantics": "midpoint_of_synthetic_straight_line_connector_not_electrical_corridor",
        })
    return pd.DataFrame(bus_records + branch_records)


def map_observations(weather_csv: Path, bus_csv: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    frame = pd.read_csv(weather_csv, low_memory=False)
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Normalized weather CSV missing columns: {sorted(missing)}")
    frame = frame.copy()
    parsed_timestamps = []
    for raw_timestamp in frame["timestamp"]:
        stamp = pd.Timestamp(raw_timestamp)
        if pd.isna(stamp) or stamp.tzinfo is None:
            raise ValueError(
                "Timestamps must include an explicit UTC offset. Convert source-local/LST "
                "timestamps using verified source timezone metadata before mapping."
            )
        parsed_timestamps.append(stamp.tz_convert("UTC"))
    frame["timestamp"] = parsed_timestamps
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    if not frame["spatial_scope"].isin(ALLOWED_SCOPES).all():
        raise ValueError(f"spatial_scope must be one of {sorted(ALLOWED_SCOPES)}")
    if frame[["source_id", "variable", "time_basis", "temporal_semantics"]].isna().any().any():
        raise ValueError("Source, variable, time_basis, and temporal_semantics must be populated")
    assets = build_asset_samples(bus_csv)
    output: list[dict[str, Any]] = []
    for obs in frame.to_dict(orient="records"):
        scope = obs["spatial_scope"]
        if scope == "point":
            if pd.isna(obs.get("latitude")) or pd.isna(obs.get("longitude")):
                raise ValueError("Point observations require latitude and longitude")
            ox, oy = CRS_TO_METRIC.transform(float(obs["longitude"]), float(obs["latitude"]))
            distances = ((assets["x_m"] - ox) ** 2 + (assets["y_m"] - oy) ** 2) ** 0.5
            nearest_index = distances.idxmin()
            selected = [(assets.loc[nearest_index], float(distances.loc[nearest_index]))]
            method = "nearest_source_point_in_epsg3826"
        else:
            selected = [(asset, None) for _, asset in assets.iterrows()]
            method = "regional_area_mean_broadcast_no_local_spatial_disaggregation"
        for asset, distance in selected:
            output.append({
                "timestamp_utc": obs["timestamp"].isoformat(),
                "source_id": str(obs["source_id"]),
                "variable": str(obs["variable"]),
                "value": None if pd.isna(obs["value"]) else float(obs["value"]),
                "asset_type": asset["asset_type"], "asset_id": asset["asset_id"],
                "bus_id": asset["bus_id"], "branch_id": asset["branch_id"],
                "spatial_scope": scope, "mapping_method": method,
                "distance_to_source_m": distance,
                "time_basis": str(obs["time_basis"]),
                "temporal_semantics": str(obs["temporal_semantics"]),
                "sample_location_semantics": asset["sample_location_semantics"],
            })
    summary = {
        "status": "phase_6b_weather_asset_mapping",
        "input_observation_count": int(len(frame)),
        "output_asset_feature_count": len(output),
        "point_observation_count": int((frame["spatial_scope"] == "point").sum()),
        "regional_observation_count": int((frame["spatial_scope"] == "regional").sum()),
        "asset_sample_count": int(len(assets)),
        "bus_sample_count": int((assets["asset_type"] == "bus").sum()),
        "branch_midpoint_sample_count": int((assets["asset_type"] == "branch_sample").sum()),
        "timestamp_policy": "Input timestamps parsed as UTC; source time_basis retained verbatim. Do not label LST as UTC before normalization.",
        "missing_value_policy": "Missing measurements remain null; no imputation or zero substitution.",
        "limitations": [
            "Synthetic bus coordinates are not verified electrical asset locations.",
            "Branch midpoint samples lie on straight-line visualization connectors, not verified conductor corridors.",
            "Nearest-point mapping is a sampling association, not a physical exposure model.",
            "Regional means are broadcast unchanged and are not spatially downscaled.",
            "Historical observations and forecasts remain distinguishable through temporal_semantics.",
        ],
    }
    return output, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weather", type=Path, default=DEFAULT_WEATHER)
    parser.add_argument("--buses", type=Path, default=DEFAULT_BUSES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_OUTPUT.with_suffix(".summary.json"))
    args = parser.parse_args()
    rows, summary = map_observations(args.weather, args.buses)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.output, index=False, encoding="utf-8-sig")
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**summary, "output_csv": str(args.output), "summary_json": str(args.summary)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
