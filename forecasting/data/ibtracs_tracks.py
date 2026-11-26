"""Normalize per-storm IBTrACS metadata into chronological tracks.

The repository stores one metadata CSV per storm instance. This module preserves
source fields, records rejected rows separately, and derives kinematic metrics
only from valid timestamp/coordinate pairs. Wind and pressure remain raw values
because the source-unit metadata has not yet been verified.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = {"year", "month", "day", "hour", "lat", "lng"}
EARTH_RADIUS_KM = 6371.0088


def _timestamp_from_components(frame: pd.DataFrame) -> pd.Series:
    components = {
        name: pd.to_numeric(frame[name], errors="coerce")
        for name in ("year", "month", "day", "hour")
    }
    return pd.to_datetime(components, errors="coerce", utc=True)


def _haversine_km(
    lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray
) -> np.ndarray:
    """Vectorized great-circle distance for coordinates in decimal degrees."""
    lat1r, lon1r = np.radians(lat1), np.radians(lon1)
    lat2r, lon2r = np.radians(lat2), np.radians(lon2)
    dlat, dlon = lat2r - lat1r, lon2r - lon1r
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlon / 2.0) ** 2
    a = np.clip(a, 0.0, 1.0)
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def _initial_bearing_deg(
    lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray
) -> np.ndarray:
    """Forward azimuth from point 1 to point 2, clockwise from true north."""
    lat1r, lat2r = np.radians(lat1), np.radians(lat2)
    dlon = np.radians(lon2 - lon1)
    x = np.sin(dlon) * np.cos(lat2r)
    y = np.cos(lat1r) * np.sin(lat2r) - np.sin(lat1r) * np.cos(lat2r) * np.cos(dlon)
    return (np.degrees(np.arctan2(x, y)) + 360.0) % 360.0


def load_synthetic_bus_locations(path: str | Path) -> pd.DataFrame:
    """Load the 33 synthetic bus coordinates used by the Minxiong study case."""
    frame = pd.read_csv(path)
    required = {"bus_id", "latitude", "longitude"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Bus-location CSV missing columns: {sorted(missing)}")
    frame = frame.copy()
    frame["bus_id"] = pd.to_numeric(frame["bus_id"], errors="coerce")
    frame["latitude"] = pd.to_numeric(frame["latitude"], errors="coerce")
    frame["longitude"] = pd.to_numeric(frame["longitude"], errors="coerce")
    if frame[list(required)].isna().any().any():
        raise ValueError("Bus-location CSV contains missing or non-numeric required values")
    if len(frame) != 33 or frame["bus_id"].nunique() != 33:
        raise ValueError("Expected exactly 33 unique synthetic bus locations")
    if not frame["latitude"].between(-90, 90).all() or not frame["longitude"].between(-180, 180).all():
        raise ValueError("Synthetic bus coordinates fall outside valid decimal-degree ranges")
    return frame.sort_values("bus_id").reset_index(drop=True)


def add_synthetic_grid_proximity(
    tracks: pd.DataFrame, bus_locations: pd.DataFrame
) -> pd.DataFrame:
    """Attach nearest synthetic bus and great-circle distance to each track point."""
    result = tracks.copy()
    bus_lat = bus_locations["latitude"].to_numpy(dtype=float)
    bus_lon = bus_locations["longitude"].to_numpy(dtype=float)
    track_lat = result["latitude"].to_numpy(dtype=float)
    track_lon = result["longitude"].to_numpy(dtype=float)

    distances = _haversine_km(
        track_lat[:, None], track_lon[:, None],
        bus_lat[None, :], bus_lon[None, :],
    )
    nearest = np.argmin(distances, axis=1)
    result["nearest_synthetic_bus_id"] = bus_locations["bus_id"].to_numpy()[nearest].astype(int)
    result["nearest_synthetic_bus_distance_km"] = distances[np.arange(len(result)), nearest]
    return result


def _storm_summaries(
    tracks: pd.DataFrame, rejected: pd.DataFrame
) -> list[dict[str, Any]]:
    rejected_counts = (
        rejected.groupby("storm_instance_id").size().to_dict()
        if not rejected.empty else {}
    )
    summaries: list[dict[str, Any]] = []
    for storm_id, group in tracks.groupby("storm_instance_id", sort=True):
        group = group.sort_values(["timestamp_utc", "source_row_number"], kind="stable")
        first = group.iloc[0]
        last = group.iloc[-1]
        record: dict[str, Any] = {
            "storm_instance_id": str(storm_id),
            "source_file": str(first["source_file"]),
            "observation_count": int(len(group)),
            "rejected_row_count": int(rejected_counts.get(storm_id, 0)),
            "duplicate_timestamp_count": int(group["duplicate_timestamp"].sum()),
            "observed_start_utc": first["timestamp_utc"].isoformat(),
            "observed_end_utc": last["timestamp_utc"].isoformat(),
            "latitude_min": float(group["latitude"].min()),
            "latitude_max": float(group["latitude"].max()),
            "longitude_min": float(group["longitude"].min()),
            "longitude_max": float(group["longitude"].max()),
            "maximum_translation_speed_kmh": (
                float(group["translation_speed_kmh"].max())
                if group["translation_speed_kmh"].notna().any() else None
            ),
        }
        if "wind" in group.columns:
            raw_wind = pd.to_numeric(group["wind"], errors="coerce")
            record["maximum_wind_raw"] = float(raw_wind.max()) if raw_wind.notna().any() else None
        if "pressure" in group.columns:
            raw_pressure = pd.to_numeric(group["pressure"], errors="coerce")
            record["minimum_pressure_raw"] = float(raw_pressure.min()) if raw_pressure.notna().any() else None
        if "nearest_synthetic_bus_distance_km" in group.columns:
            nearest_idx = group["nearest_synthetic_bus_distance_km"].idxmin()
            nearest_row = group.loc[nearest_idx]
            record["closest_approach_to_synthetic_grid_km"] = float(
                nearest_row["nearest_synthetic_bus_distance_km"]
            )
            record["closest_approach_time_utc"] = nearest_row["timestamp_utc"].isoformat()
            record["nearest_synthetic_bus_id"] = int(nearest_row["nearest_synthetic_bus_id"])
        summaries.append(record)
    return summaries


def build_ibtracs_tracks(
    metadata_dir: str | Path,
    *,
    bus_locations_csv: str | Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Read all per-storm CSVs and return tracks, rejected rows, summaries, audit."""
    root = Path(metadata_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"IBTrACS metadata directory does not exist: {root}")
    files = sorted(root.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No per-storm metadata CSV files found in {root}")

    valid_frames: list[pd.DataFrame] = []
    rejected_frames: list[pd.DataFrame] = []
    source_columns: set[str] = set()
    for path in files:
        frame = pd.read_csv(path, low_memory=False)
        missing = REQUIRED_COLUMNS - set(frame.columns)
        if missing:
            raise ValueError(f"{path.name}: missing required columns {sorted(missing)}")
        source_columns.update(str(column) for column in frame.columns)
        frame = frame.copy()
        frame["storm_instance_id"] = path.stem
        frame["source_file"] = path.name
        frame["source_row_number"] = np.arange(2, len(frame) + 2, dtype=int)
        frame["timestamp_utc"] = _timestamp_from_components(frame)
        frame["latitude"] = pd.to_numeric(frame["lat"], errors="coerce")
        original_longitude = pd.to_numeric(frame["lng"], errors="coerce")
        longitude_valid = original_longitude.between(-180, 360)
        frame["longitude_normalized_from_0_360"] = (
            original_longitude.gt(180) & original_longitude.le(360)
        )
        frame["longitude"] = original_longitude.where(
            ~frame["longitude_normalized_from_0_360"],
            original_longitude - 360.0,
        )
        coordinate_valid = (
            frame["latitude"].between(-90, 90)
            & longitude_valid
            & frame["longitude"].between(-180, 180)
        )
        timestamp_valid = frame["timestamp_utc"].notna()
        valid = timestamp_valid & coordinate_valid
        reasons = []
        for timestamp_ok, coordinate_ok in zip(timestamp_valid, coordinate_valid):
            reason_parts = []
            if not timestamp_ok:
                reason_parts.append("invalid_timestamp_components")
            if not coordinate_ok:
                reason_parts.append("invalid_or_missing_coordinates")
            reasons.append(";".join(reason_parts))
        frame["rejection_reason"] = reasons
        if (~valid).any():
            rejected_frames.append(frame.loc[~valid].copy())
        if valid.any():
            valid_frames.append(frame.loc[valid].copy())

    if not valid_frames:
        raise ValueError("No valid timestamp/coordinate observations found in IBTrACS metadata")

    tracks = pd.concat(valid_frames, ignore_index=True, sort=False)
    rejected = (
        pd.concat(rejected_frames, ignore_index=True, sort=False)
        if rejected_frames else pd.DataFrame()
    )
    tracks = tracks.sort_values(
        ["storm_instance_id", "timestamp_utc", "source_row_number"],
        kind="stable",
    ).reset_index(drop=True)
    tracks["duplicate_timestamp"] = tracks.duplicated(
        subset=["storm_instance_id", "timestamp_utc"], keep="first"
    )

    grouped = tracks.groupby("storm_instance_id", sort=False)
    previous_latitude = grouped["latitude"].shift(1).to_numpy(dtype=float)
    previous_longitude = grouped["longitude"].shift(1).to_numpy(dtype=float)
    previous_timestamp = grouped["timestamp_utc"].shift(1)
    elapsed_hours = (
        (tracks["timestamp_utc"] - previous_timestamp).dt.total_seconds() / 3600.0
    ).to_numpy(dtype=float)
    has_previous = np.isfinite(previous_latitude) & np.isfinite(previous_longitude)
    valid_segment = has_previous & np.isfinite(elapsed_hours) & (elapsed_hours > 0)

    distance = np.full(len(tracks), np.nan, dtype=float)
    bearing = np.full(len(tracks), np.nan, dtype=float)
    if valid_segment.any():
        current_lat = tracks["latitude"].to_numpy(dtype=float)
        current_lon = tracks["longitude"].to_numpy(dtype=float)
        distance[valid_segment] = _haversine_km(
            previous_latitude[valid_segment], previous_longitude[valid_segment],
            current_lat[valid_segment], current_lon[valid_segment],
        )
        moving = valid_segment & (distance > 0)
        bearing[moving] = _initial_bearing_deg(
            previous_latitude[moving], previous_longitude[moving],
            current_lat[moving], current_lon[moving],
        )
    tracks["elapsed_since_previous_hours"] = elapsed_hours
    tracks["segment_distance_km"] = distance
    tracks["translation_speed_kmh"] = np.where(
        valid_segment, distance / elapsed_hours, np.nan
    )
    tracks["heading_deg_from_previous"] = bearing

    grid_status = "not_requested"
    if bus_locations_csv is not None:
        bus_path = Path(bus_locations_csv)
        if bus_path.is_file():
            buses = load_synthetic_bus_locations(bus_path)
            tracks = add_synthetic_grid_proximity(tracks, buses)
            grid_status = "computed_to_synthetic_bus_points"
        else:
            grid_status = f"skipped_missing_bus_file:{bus_path}"

    summaries = pd.DataFrame(_storm_summaries(tracks, rejected))
    audit = {
        "schema_version": 1,
        "status": "ibtracs_tracks_processed",
        "metadata_directory": str(root),
        "metadata_file_count": len(files),
        "storm_instance_count": int(tracks["storm_instance_id"].nunique()),
        "source_row_count": int(sum(
            len(pd.read_csv(path, usecols=lambda _: True)) for path in files
        )),
        "valid_track_row_count": int(len(tracks)),
        "rejected_row_count": int(len(rejected)),
        "duplicate_timestamp_count": int(tracks["duplicate_timestamp"].sum()),
        "source_columns_union": sorted(source_columns),
        "timestamp_convention": (
            "Constructed from year/month/day/hour and interpreted as UTC, consistent "
            "with the repository's existing IBTrACS quality audit; verify source "
            "documentation before treating this convention as authoritative."
        ),
        "longitude_policy": "Values in (180, 360] are converted to [-180, 0]; original lng is preserved.",
        "wind_pressure_policy": (
            "wind and pressure source fields are preserved as raw values; units are "
            "not inferred and no wind-to-failure conversion is performed."
        ),
        "grid_proximity_status": grid_status,
        "grid_proximity_limitations": (
            "Distances are to synthetic bus sample coordinates, not verified Taipower "
            "assets or conductor corridors."
            if grid_status == "computed_to_synthetic_bus_points" else None
        ),
        "no_imputation": True,
        "no_interpolation": True,
        "storm_summaries": summaries.to_dict(orient="records"),
    }
    return tracks, rejected, summaries, audit


def write_ibtracs_outputs(
    tracks: pd.DataFrame,
    rejected: pd.DataFrame,
    summaries: pd.DataFrame,
    audit: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, str]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    track_path = destination / "ibtracs_tracks.csv"
    rejected_path = destination / "ibtracs_rejected_records.csv"
    summary_path = destination / "ibtracs_storm_summary.csv"
    audit_path = destination / "ibtracs_track_audit.json"

    tracks.to_csv(track_path, index=False, encoding="utf-8-sig")
    rejected.to_csv(rejected_path, index=False, encoding="utf-8-sig")
    summaries.to_csv(summary_path, index=False, encoding="utf-8-sig")
    audit_path.write_text(
        json.dumps(audit, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    return {
        "tracks_csv": str(track_path),
        "rejected_records_csv": str(rejected_path),
        "storm_summary_csv": str(summary_path),
        "audit_json": str(audit_path),
    }
