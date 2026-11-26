"""Storm closest-approach and spatial exposure screening for IBTrACS tracks.

All distances are based on observed best-track positions and synthetic bus points.
They are not continuous-path minima, physical wind exposure, damage, or failure
probabilities. Wind and pressure are retained as raw source values.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from forecasting.data.ibtracs_regions import (
    EARTH_RADIUS_KM,
    TAIWAN_REFERENCE,
    haversine_km,
)

DEFAULT_THRESHOLDS_KM = (50.0, 100.0, 200.0, 300.0)
REQUIRED_COLUMNS = {
    "storm_instance_id", "timestamp_utc", "latitude", "longitude",
    "nearest_synthetic_bus_distance_km",
}


def _validate_tracks(tracks: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED_COLUMNS - set(tracks.columns)
    if missing:
        raise ValueError(f"IBTrACS tracks missing required columns: {sorted(missing)}")
    frame = tracks.copy()
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True, errors="coerce")
    for column in ("latitude", "longitude", "nearest_synthetic_bus_distance_km"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    valid = (
        frame["timestamp_utc"].notna()
        & frame["latitude"].between(-90, 90)
        & frame["longitude"].between(-180, 180)
        & frame["nearest_synthetic_bus_distance_km"].ge(0)
    )
    frame = frame.loc[valid].copy()
    if frame.empty:
        raise ValueError("No valid observations remain after timestamp/coordinate/distance validation")
    frame["storm_instance_id"] = frame["storm_instance_id"].astype(str)
    if "source_row_number" in frame:
        frame["source_row_number"] = pd.to_numeric(frame["source_row_number"], errors="coerce")
    else:
        frame["source_row_number"] = np.arange(len(frame))
    return frame.sort_values(
        ["storm_instance_id", "timestamp_utc", "source_row_number"], kind="stable"
    ).reset_index(drop=True)


def _closest_rows(
    frame: pd.DataFrame, *, distance_column: str, prefix: str
) -> pd.DataFrame:
    ordered = frame.sort_values(
        ["storm_instance_id", distance_column, "timestamp_utc", "source_row_number"],
        kind="stable",
    )
    closest = ordered.drop_duplicates("storm_instance_id", keep="first").copy()
    rename = {
        "timestamp_utc": f"{prefix}_timestamp_utc",
        "latitude": f"{prefix}_latitude",
        "longitude": f"{prefix}_longitude",
        distance_column: f"{prefix}_distance_km",
        "translation_speed_kmh": f"{prefix}_translation_speed_kmh",
        "heading_deg_from_previous": f"{prefix}_heading_deg_from_previous",
        "nearest_synthetic_bus_id": f"{prefix}_nearest_synthetic_bus_id",
    }
    closest = closest.rename(columns={k: v for k, v in rename.items() if k in closest.columns})
    keep = ["storm_instance_id"] + [v for v in rename.values() if v in closest.columns]
    if "wind" in closest.columns:
        keep.append("wind")
    if "pressure" in closest.columns:
        keep.append("pressure")
    return closest[keep].reset_index(drop=True)


def _storm_intensity_summary(frame: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for storm_id, group in frame.groupby("storm_instance_id", sort=True):
        row: dict[str, Any] = {
            "storm_instance_id": storm_id,
            "observation_count": int(len(group)),
            "observed_start_utc": group["timestamp_utc"].min().isoformat(),
            "observed_end_utc": group["timestamp_utc"].max().isoformat(),
        }
        for source, output, operation in (
            ("wind", "maximum_wind_raw", "max"),
            ("pressure", "minimum_pressure_raw", "min"),
        ):
            if source in group:
                values = pd.to_numeric(group[source], errors="coerce")
                value = values.max() if operation == "max" else values.min()
                row[output] = float(value) if pd.notna(value) else None
                row[f"{output}_valid_observation_count"] = int(values.notna().sum())
        records.append(row)
    return pd.DataFrame(records)


def classify_minxiong_exposure(
    closest: pd.DataFrame, thresholds_km: tuple[float, ...] = DEFAULT_THRESHOLDS_KM
) -> pd.DataFrame:
    """Assign exploratory distance bands; these are not hazard/risk categories."""
    thresholds = tuple(float(x) for x in thresholds_km)
    if not thresholds or any(x <= 0 for x in thresholds):
        raise ValueError("At least one positive distance threshold is required")
    if tuple(sorted(set(thresholds))) != thresholds:
        raise ValueError("Distance thresholds must be strictly increasing")
    if "minxiong_distance_km" not in closest:
        raise ValueError("closest table must contain minxiong_distance_km")
    labels = ["very_high_proximity", "high_proximity", "moderate_proximity", "low_proximity"]
    if len(thresholds) != 4:
        labels = [f"within_{threshold:g}_km" for threshold in thresholds]
    values = pd.to_numeric(closest["minxiong_distance_km"], errors="coerce")
    bands = [-np.inf, *thresholds, np.inf]
    categories = [*labels, "outside_screen"]
    result = closest.copy()
    result["screening_band"] = pd.cut(
        values, bins=bands, labels=categories, right=True, include_lowest=True
    ).astype("string")
    result["screening_thresholds_km"] = ",".join(f"{x:g}" for x in thresholds)
    result["interpretation"] = "spatial_proximity_screen_only_not_physical_risk"
    return result


def _write_figures(
    taiwan: pd.DataFrame, minxiong: pd.DataFrame, output_dir: Path
) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[str] = []

    fig, ax = plt.subplots(figsize=(10, 7), constrained_layout=True)
    if not minxiong.empty:
        scatter = ax.scatter(
            minxiong["minxiong_longitude"], minxiong["minxiong_latitude"],
            c=minxiong["minxiong_distance_km"], s=28, alpha=0.8,
        )
        fig.colorbar(scatter, ax=ax, label="Nearest synthetic bus distance (km)")
    ax.scatter(
        [TAIWAN_REFERENCE["longitude"]], [TAIWAN_REFERENCE["latitude"]],
        marker="*", s=150, edgecolors="black", label="Taiwan reference point",
    )
    ax.set(xlabel="Longitude (degrees east)", ylabel="Latitude (degrees north)",
           title="Observed IBTrACS closest approaches to synthetic Minxiong buses")
    ax.grid(True, linestyle=":")
    ax.legend(loc="best")
    path = figure_dir / "minxiong_closest_approach_map.png"
    fig.savefig(path, dpi=220)
    plt.close(fig)
    outputs.append(str(path))

    fig, ax = plt.subplots(figsize=(9, 5), constrained_layout=True)
    if not minxiong.empty:
        order = ["very_high_proximity", "high_proximity", "moderate_proximity",
                 "low_proximity", "outside_screen"]
        counts = minxiong["screening_band"].value_counts().reindex(order, fill_value=0)
        ax.bar(counts.index.astype(str), counts.values)
        ax.tick_params(axis="x", rotation=20)
    ax.set(ylabel="Storm count", title="Minxiong synthetic-grid spatial screening bands")
    ax.grid(axis="y", linestyle=":")
    path = figure_dir / "storm_exposure_distribution.png"
    fig.savefig(path, dpi=220)
    plt.close(fig)
    outputs.append(str(path))

    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    if not minxiong.empty:
        ordered = minxiong.sort_values("minxiong_timestamp_utc")
        ax.scatter(ordered["minxiong_timestamp_utc"], ordered["minxiong_distance_km"], s=25)
    ax.set(xlabel="Observed closest-approach timestamp (UTC)",
           ylabel="Nearest synthetic bus distance (km)",
           title="Minxiong closest-approach chronology")
    ax.grid(True, linestyle=":")
    fig.autofmt_xdate()
    path = figure_dir / "closest_approach_timeline.png"
    fig.savefig(path, dpi=220)
    plt.close(fig)
    outputs.append(str(path))

    if "maximum_wind_raw" in minxiong.columns:
        fig, ax = plt.subplots(figsize=(8, 5), constrained_layout=True)
        ax.scatter(minxiong["minxiong_distance_km"], minxiong["maximum_wind_raw"], alpha=0.75)
        ax.set(xlabel="Closest observed distance to synthetic bus (km)",
               ylabel="Maximum wind (raw source value; unit unverified)",
               title="Raw IBTrACS wind values versus observed grid proximity")
        ax.grid(True, linestyle=":")
        path = figure_dir / "storm_intensity_vs_distance.png"
        fig.savefig(path, dpi=220)
        plt.close(fig)
        outputs.append(str(path))
    return outputs


def build_exposure_outputs(
    tracks: pd.DataFrame,
    output_dir: str | Path,
    *,
    taiwan_radius_km: float = 500.0,
    minxiong_radius_km: float = 300.0,
    thresholds_km: tuple[float, ...] = DEFAULT_THRESHOLDS_KM,
) -> dict[str, Any]:
    """Create closest-observation tables, distance bands, figures, and audit."""
    if taiwan_radius_km <= 0 or minxiong_radius_km <= 0:
        raise ValueError("Regional screening radii must be positive")
    frame = _validate_tracks(tracks)
    frame["distance_to_taiwan_reference_km"] = haversine_km(
        frame["latitude"], frame["longitude"],
        TAIWAN_REFERENCE["latitude"], TAIWAN_REFERENCE["longitude"],
    )

    taiwan_all = _closest_rows(
        frame, distance_column="distance_to_taiwan_reference_km", prefix="taiwan"
    )
    taiwan = taiwan_all.loc[taiwan_all["taiwan_distance_km"] <= taiwan_radius_km].copy()
    minxiong = _closest_rows(
        frame, distance_column="nearest_synthetic_bus_distance_km", prefix="minxiong"
    )
    classified = classify_minxiong_exposure(minxiong, thresholds_km)
    intensity = _storm_intensity_summary(frame)

    # The closest-row tables carry raw wind/pressure only at the closest observation;
    # this summary separately carries per-storm extrema without inferring units.
    minxiong = minxiong.merge(intensity, on="storm_instance_id", how="left")
    classified = classified.merge(intensity, on="storm_instance_id", how="left")
    taiwan = taiwan.merge(intensity, on="storm_instance_id", how="left")

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    files = {
        "taiwan_closest_approach": "ibtracs_taiwan_closest_approach.csv",
        "minxiong_closest_approach": "ibtracs_minxiong_closest_approach.csv",
        "minxiong_exposure_classification": "ibtracs_minxiong_exposure_classification.csv",
        "storm_intensity_summary": "ibtracs_storm_intensity_summary.csv",
    }
    tables = {
        "taiwan_closest_approach": taiwan,
        "minxiong_closest_approach": minxiong,
        "minxiong_exposure_classification": classified,
        "storm_intensity_summary": intensity,
    }
    for key, table in tables.items():
        table.to_csv(destination / files[key], index=False, encoding="utf-8-sig")

    figures = _write_figures(taiwan, classified, destination)
    counts = (
        classified["screening_band"].value_counts(dropna=False).to_dict()
        if not classified.empty else {}
    )
    audit = {
        "schema_version": 1,
        "status": "ibtracs_exposure_screening_completed",
        "input_observation_count": int(len(frame)),
        "input_storm_count": int(frame["storm_instance_id"].nunique()),
        "valid_observation_count": int(len(frame)),
        "invalid_rows_excluded": int(len(tracks) - len(frame)),
        "taiwan_reference": {
            "point": TAIWAN_REFERENCE,
            "selection_radius_km": float(taiwan_radius_km),
            "selected_storm_count": int(taiwan["storm_instance_id"].nunique()),
            "closest_approach_method": "minimum great-circle distance among observed positions; no interpolation",
        },
        "minxiong_synthetic_grid": {
            "selection_radius_km": float(minxiong_radius_km),
            "storm_count": int(minxiong["storm_instance_id"].nunique()),
            "screening_band_counts": {str(k): int(v) for k, v in counts.items()},
            "thresholds_km": list(thresholds_km),
            "closest_approach_method": "minimum per-observation distance to nearest synthetic bus sample point; no interpolation",
            "asset_scope": "synthetic 33-bus sample coordinates, not verified Taipower assets or branch corridors",
        },
        "wind_pressure_policy": "wind and pressure extrema are raw source values; units and agency semantics are not inferred",
        "limitations": [
            "Closest approaches are minima over observed best-track positions; hourly sampling may miss the continuous-path minimum.",
            "Distance bands are exploratory spatial screening labels, not hazard levels, fragility classes, failure probabilities, or damage estimates.",
            "No wind-field model, local gust estimate, branch-corridor exposure, hydrologic model, or infrastructure fragility model is applied.",
            "IBTrACS observations are historical best-track data, not forecasts.",
            "No observations are interpolated or imputed.",
        ],
        "outputs": {**files, "figures": [str(Path(p).relative_to(destination)) for p in figures]},
    }
    (destination / "ibtracs_exposure_audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    return audit
