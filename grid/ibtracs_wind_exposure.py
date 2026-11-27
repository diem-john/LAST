"""Evaluate reconstructed cyclone winds at synthetic IEEE-33 grid coordinates."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from forecasting.physics.tropical_cyclone_wind import reconstruct_wind_at_points


def build_synthetic_grid_samples(
    bus_locations: pd.DataFrame,
    case: dict[str, Any],
    *,
    samples_per_branch: int = 5,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return bus points and interior straight-line samples for active branches."""
    if samples_per_branch < 1:
        raise ValueError("samples_per_branch must be at least 1")
    required = {"bus_id", "latitude", "longitude"}
    if missing := required - set(bus_locations.columns):
        raise ValueError(f"Bus coordinates missing columns: {sorted(missing)}")
    buses = bus_locations.copy()
    buses["bus_id"] = pd.to_numeric(buses["bus_id"], errors="raise").astype(int)
    bus_lookup = buses.set_index("bus_id")
    bus_assets = pd.DataFrame({
        "asset_type": "bus",
        "asset_id": buses["bus_id"].map(lambda x: f"BUS_{x:02d}"),
        "bus_id": buses["bus_id"],
        "branch_id": np.nan,
        "sample_index": 0,
        "sample_fraction": 0.0,
        "latitude": pd.to_numeric(buses["latitude"], errors="raise"),
        "longitude": pd.to_numeric(buses["longitude"], errors="raise"),
        "sample_location_semantics": "synthetic_bus_point",
    })
    fractions = np.linspace(0.0, 1.0, samples_per_branch + 2)[1:-1]
    branch_rows = []
    for branch in case["branch"]:
        if not bool(branch.get("in_service", False)):
            continue
        branch_id = int(branch["branch_id"])
        from_bus, to_bus = int(branch["from_bus"]), int(branch["to_bus"])
        if from_bus not in bus_lookup.index or to_bus not in bus_lookup.index:
            raise ValueError(f"Branch {branch_id} references a bus without coordinates")
        a, b = bus_lookup.loc[from_bus], bus_lookup.loc[to_bus]
        for index, fraction in enumerate(fractions, start=1):
            branch_rows.append({
                "asset_type": "branch",
                "asset_id": f"BRANCH_{branch_id:02d}",
                "bus_id": np.nan,
                "branch_id": branch_id,
                "sample_index": index,
                "sample_fraction": float(fraction),
                "latitude": float(a["latitude"] + fraction * (b["latitude"] - a["latitude"])),
                "longitude": float(a["longitude"] + fraction * (b["longitude"] - a["longitude"])),
                "sample_location_semantics": "synthetic_straight_line_branch_sample",
            })
    branch_samples = pd.DataFrame(branch_rows)
    return bus_assets.reset_index(drop=True), branch_samples.reset_index(drop=True)


def evaluate_grid_wind_exposure(
    wind_tracks: pd.DataFrame,
    bus_assets: pd.DataFrame,
    branch_samples: pd.DataFrame,
    wind_config: dict[str, Any],
) -> pd.DataFrame:
    """Create per-observation bus exposure and max-sampled branch exposure rows."""
    required = {
        "storm_instance_id", "timestamp_utc", "latitude", "longitude", "vmax_ms", "rmw_km"
    }
    if missing := required - set(wind_tracks.columns):
        raise ValueError(f"Wind track table missing columns: {sorted(missing)}")
    all_samples = pd.concat([bus_assets, branch_samples], ignore_index=True)
    if all_samples.empty:
        raise ValueError("No synthetic grid asset samples available")
    rows = []
    asymmetry = str(wind_config.get("translation_asymmetry", "miyazaki_1962"))
    hemisphere = str(wind_config.get("hemisphere", "north"))
    for track in wind_tracks.itertuples(index=False):
        vmax = getattr(track, "vmax_ms")
        if pd.isna(vmax) or float(vmax) <= 0:
            continue
        translation = getattr(track, "translation_speed_kmh", np.nan)
        heading = getattr(track, "heading_deg_from_previous", np.nan)
        result = reconstruct_wind_at_points(
            storm_latitude=float(getattr(track, "latitude")),
            storm_longitude=float(getattr(track, "longitude")),
            vmax_ms=float(vmax),
            rmw_km=float(getattr(track, "rmw_km")),
            asset_latitudes=all_samples["latitude"].to_numpy(dtype=float),
            asset_longitudes=all_samples["longitude"].to_numpy(dtype=float),
            translation_speed_kmh=None if pd.isna(translation) else float(translation),
            translation_heading_deg=None if pd.isna(heading) else float(heading),
            hemisphere=hemisphere,
            asymmetry=asymmetry,
        )
        evaluated = all_samples.copy()
        evaluated["wind_speed_symmetric_ms"] = result["wind_speed_symmetric_ms"]
        evaluated["wind_speed_ms"] = result["wind_speed_asymmetric_ms"]
        evaluated["wind_direction_to_deg"] = result["wind_direction_to_deg"]
        evaluated["radius_from_storm_center_km"] = result["radius_from_storm_center_km"]
        evaluated["storm_instance_id"] = str(getattr(track, "storm_instance_id"))
        evaluated["timestamp_utc"] = str(getattr(track, "timestamp_utc"))
        evaluated["storm_latitude"] = float(getattr(track, "latitude"))
        evaluated["storm_longitude"] = float(getattr(track, "longitude"))
        evaluated["vmax_ms"] = float(vmax)
        evaluated["rmw_km"] = float(getattr(track, "rmw_km"))
        evaluated["wind_model"] = str(getattr(track, "wind_model", "willoughby_2006"))
        evaluated["wind_model_status"] = str(getattr(track, "wind_model_status", "uncalibrated"))
        bus_rows = evaluated.loc[evaluated["asset_type"] == "bus"].copy()
        branch_rows = evaluated.loc[evaluated["asset_type"] == "branch"].copy()
        if not branch_rows.empty:
            branch_rows = branch_rows.sort_values(
                ["wind_speed_ms", "sample_index"], ascending=[False, True], kind="stable"
            ).drop_duplicates("branch_id", keep="first")
            branch_rows["sample_location_semantics"] = "maximum_of_synthetic_straight_line_branch_samples"
            branch_rows["sample_count"] = int(branch_samples.groupby("branch_id").size().iloc[0])
        rows.extend(bus_rows.to_dict(orient="records"))
        rows.extend(branch_rows.to_dict(orient="records"))
    if not rows:
        raise ValueError("No valid positive-wind observations were available for grid exposure")
    output = pd.DataFrame(rows)
    output["wind_speed_kmh"] = output["wind_speed_ms"] * 3.6
    return output.sort_values(
        ["storm_instance_id", "timestamp_utc", "asset_type", "asset_id"], kind="stable"
    ).reset_index(drop=True)
