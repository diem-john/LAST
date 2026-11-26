"""Regional screening and visualization for processed IBTrACS storm tracks.

Regional selections are storm-level: if any observation enters a region, the
complete track for that storm is retained in the regional output. This preserves
approach and departure context. Taiwan and Minxiong screens are distance-to-
reference-point / synthetic-bus screens, not official hazard boundaries.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

EARTH_RADIUS_KM = 6371.0088
WNP_BOUNDS = {"longitude_min": 100.0, "longitude_max": 180.0,
              "latitude_min": 0.0, "latitude_max": 60.0}
TAIWAN_REFERENCE = {"latitude": 23.7, "longitude": 121.0}
MINXIONG_REFERENCE = {"latitude": 23.55, "longitude": 120.45}


def haversine_km(latitude, longitude, reference_latitude, reference_longitude):
    """Great-circle distances in km from coordinates to one reference point."""
    lat = np.radians(np.asarray(latitude, dtype=float))
    lon = np.radians(np.asarray(longitude, dtype=float))
    ref_lat = np.radians(float(reference_latitude))
    ref_lon = np.radians(float(reference_longitude))
    dlat, dlon = lat - ref_lat, lon - ref_lon
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat) * np.cos(ref_lat) * np.sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def _required_track_columns(tracks: pd.DataFrame) -> None:
    required = {"storm_instance_id", "latitude", "longitude", "timestamp_utc"}
    missing = required - set(tracks.columns)
    if missing:
        raise ValueError(f"IBTrACS tracks missing required columns: {sorted(missing)}")


def select_storms_intersecting_bbox(
    tracks: pd.DataFrame, *, longitude_min: float, longitude_max: float,
    latitude_min: float, latitude_max: float,
) -> pd.DataFrame:
    """Return complete tracks for storms with >=1 observation inside a lon/lat box."""
    _required_track_columns(tracks)
    if longitude_min >= longitude_max or latitude_min >= latitude_max:
        raise ValueError("Bounding-box minima must be smaller than maxima")
    inside = (
        tracks["longitude"].between(longitude_min, longitude_max, inclusive="both")
        & tracks["latitude"].between(latitude_min, latitude_max, inclusive="both")
    )
    selected_ids = tracks.loc[inside, "storm_instance_id"].unique()
    return tracks.loc[tracks["storm_instance_id"].isin(selected_ids)].copy().reset_index(drop=True)


def select_storms_within_reference_radius(
    tracks: pd.DataFrame, *, reference_latitude: float, reference_longitude: float,
    radius_km: float, distance_column: str,
) -> pd.DataFrame:
    """Return complete tracks for storms whose closest observation is within radius."""
    _required_track_columns(tracks)
    if radius_km <= 0:
        raise ValueError("radius_km must be positive")
    result = tracks.copy()
    result[distance_column] = haversine_km(
        result["latitude"], result["longitude"], reference_latitude, reference_longitude
    )
    closest = result.groupby("storm_instance_id")[distance_column].min()
    selected_ids = closest.index[closest <= radius_km]
    return result.loc[result["storm_instance_id"].isin(selected_ids)].copy().reset_index(drop=True)


def select_storms_near_synthetic_grid(tracks: pd.DataFrame, *, radius_km: float) -> pd.DataFrame:
    """Return complete tracks for storms approaching synthetic bus points within radius."""
    _required_track_columns(tracks)
    column = "nearest_synthetic_bus_distance_km"
    if column not in tracks.columns:
        raise ValueError(
            "Track file has no nearest_synthetic_bus_distance_km column; "
            "rerun IBTrACS processing with synthetic-grid proximity enabled."
        )
    if radius_km <= 0:
        raise ValueError("radius_km must be positive")
    distances = pd.to_numeric(tracks[column], errors="coerce")
    closest = distances.groupby(tracks["storm_instance_id"]).min()
    selected_ids = closest.index[closest <= radius_km]
    return tracks.loc[tracks["storm_instance_id"].isin(selected_ids)].copy().reset_index(drop=True)


def summarize_selected_storms(tracks: pd.DataFrame) -> pd.DataFrame:
    """Create compact per-storm summaries for a selected set of complete tracks."""
    _required_track_columns(tracks)
    columns = [
        "storm_instance_id", "observation_count", "observed_start_utc",
        "observed_end_utc", "latitude_min", "latitude_max",
        "longitude_min", "longitude_max",
    ]
    if tracks.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for storm_id, group in tracks.groupby("storm_instance_id", sort=True):
        timestamps = pd.to_datetime(group["timestamp_utc"], utc=True, errors="coerce")
        row: dict[str, Any] = {
            "storm_instance_id": storm_id,
            "observation_count": int(len(group)),
            "observed_start_utc": timestamps.min().isoformat() if timestamps.notna().any() else None,
            "observed_end_utc": timestamps.max().isoformat() if timestamps.notna().any() else None,
            "latitude_min": float(group["latitude"].min()),
            "latitude_max": float(group["latitude"].max()),
            "longitude_min": float(group["longitude"].min()),
            "longitude_max": float(group["longitude"].max()),
        }
        if "nearest_synthetic_bus_distance_km" in group:
            values = pd.to_numeric(group["nearest_synthetic_bus_distance_km"], errors="coerce")
            row["closest_synthetic_bus_distance_km"] = float(values.min()) if values.notna().any() else None
        rows.append(row)
    return pd.DataFrame(rows)


def _plot_tracks(tracks, output_path, *, title, bounds, markers=None) -> None:
    """Write a longitude/latitude track map using Matplotlib without online basemaps."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, 7), constrained_layout=True)
    if not tracks.empty:
        for _, group in tracks.groupby("storm_instance_id", sort=True):
            ordered = group.sort_values("timestamp_utc")
            ax.plot(ordered["longitude"], ordered["latitude"], linewidth=0.75, alpha=0.42)
    if markers:
        for longitude, latitude, label in markers:
            ax.scatter([longitude], [latitude], marker="*", s=115, edgecolors="black",
                       linewidths=0.5, zorder=5, label=label)
        ax.legend(loc="best", fontsize=8)
    lon_min, lon_max, lat_min, lat_max = bounds
    ax.set_xlim(lon_min, lon_max)
    ax.set_ylim(lat_min, lat_max)
    ax.set_xlabel("Longitude (degrees east)")
    ax.set_ylabel("Latitude (degrees north)")
    ax.set_title(title)
    ax.grid(True, linestyle=":", linewidth=0.6, alpha=0.7)
    count = tracks["storm_instance_id"].nunique() if not tracks.empty else 0
    ax.text(0.01, 0.01, f"{count} selected storms", transform=ax.transAxes, fontsize=8, va="bottom")
    fig.savefig(destination, dpi=220)
    plt.close(fig)


def write_regional_outputs(
    tracks: pd.DataFrame, output_dir: str | Path, *,
    taiwan_radius_km: float = 500.0, minxiong_radius_km: float = 300.0,
) -> dict[str, Any]:
    """Filter processed tracks and write CSV summaries, maps, and an audit."""
    _required_track_columns(tracks)
    destination = Path(output_dir)
    figures = destination / "figures"
    figures.mkdir(parents=True, exist_ok=True)

    wnp = select_storms_intersecting_bbox(tracks, **WNP_BOUNDS)
    taiwan = select_storms_within_reference_radius(
        tracks, reference_latitude=TAIWAN_REFERENCE["latitude"],
        reference_longitude=TAIWAN_REFERENCE["longitude"], radius_km=taiwan_radius_km,
        distance_column="distance_to_taiwan_reference_km",
    )
    minxiong = select_storms_near_synthetic_grid(tracks, radius_km=minxiong_radius_km)
    selections = {
        "wnp": wnp,
        "taiwan_vicinity": taiwan,
        "minxiong_synthetic_grid_approach": minxiong,
    }
    for name, frame in selections.items():
        frame.to_csv(destination / f"ibtracs_{name}_tracks.csv", index=False, encoding="utf-8-sig")
        summarize_selected_storms(frame).to_csv(
            destination / f"ibtracs_{name}_storm_summary.csv", index=False, encoding="utf-8-sig"
        )

    _plot_tracks(
        wnp, figures / "ibtracs_wnp_tracks.png",
        title="IBTrACS storms intersecting the Western North Pacific screening box",
        bounds=(100.0, 180.0, 0.0, 60.0),
    )
    _plot_tracks(
        taiwan, figures / "ibtracs_taiwan_vicinity_tracks.png",
        title=f"IBTrACS storms within {taiwan_radius_km:g} km of the Taiwan reference point",
        bounds=(110.0, 135.0, 5.0, 40.0),
        markers=[(TAIWAN_REFERENCE["longitude"], TAIWAN_REFERENCE["latitude"], "Taiwan reference")],
    )
    _plot_tracks(
        minxiong, figures / "ibtracs_minxiong_approaches.png",
        title=f"IBTrACS storms within {minxiong_radius_km:g} km of synthetic Minxiong buses",
        bounds=(110.0, 130.0, 10.0, 35.0),
        markers=[(MINXIONG_REFERENCE["longitude"], MINXIONG_REFERENCE["latitude"], "Minxiong reference")],
    )

    audit: dict[str, Any] = {
        "status": "ibtracs_regional_filtering_completed",
        "source_observation_count": int(len(tracks)),
        "source_storm_count": int(tracks["storm_instance_id"].nunique()),
        "western_north_pacific": {
            "selection": "storm retained if at least one observation lies inside the configured longitude/latitude box; complete tracks retained",
            "bounds": WNP_BOUNDS,
        },
        "taiwan_vicinity": {
            "selection": "storm retained if any observation is within the great-circle radius of the Taiwan reference point; complete tracks retained",
            "reference_point": TAIWAN_REFERENCE, "radius_km": float(taiwan_radius_km),
        },
        "minxiong_synthetic_grid_approach": {
            "selection": "storm retained if any observation is within the threshold of its nearest synthetic bus point; complete tracks retained",
            "radius_km": float(minxiong_radius_km),
            "limitation": "Distances are to synthetic bus sample points, not verified Taipower assets or branch corridors.",
        },
        "results": {
            name: {"storm_count": int(frame["storm_instance_id"].nunique()),
                   "observation_count": int(len(frame))}
            for name, frame in selections.items()
        },
        "limitations": [
            "The WNP rectangle is a configurable screening envelope, not an official basin polygon.",
            "The Taiwan vicinity uses a reference point and radius, not coastline distance or an administrative boundary.",
            "Hourly observations may not capture the exact continuous closest approach between observations.",
            "Maps use longitude/latitude axes and no downloaded coastline basemap.",
            "Wind and pressure remain raw source values; no intensity conversion or damage model is applied.",
        ],
        "outputs": {"figures": [
            "figures/ibtracs_wnp_tracks.png",
            "figures/ibtracs_taiwan_vicinity_tracks.png",
            "figures/ibtracs_minxiong_approaches.png",
        ]},
    }
    (destination / "ibtracs_regional_filter_audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return audit
