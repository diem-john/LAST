"""Parametric tropical-cyclone wind-field reconstruction.

Implements a Willoughby-style radial profile with optional Miyazaki translation
asymmetry. Inputs are source-specific and must be explicitly configured; the
model is a research reconstruction, not an operational forecast.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

EARTH_RADIUS_KM = 6371.0088
KNOT_TO_MS = 0.5144444444444445
MPH_TO_MS = 0.44704


def validate_wind_config(config: dict[str, Any]) -> None:
    source = config.get("source_fields", {})
    required = ("wind_column", "wind_unit", "wind_averaging_period_minutes", "wind_height_m")
    missing = [name for name in required if source.get(name) in (None, "")]
    if missing:
        raise ValueError(
            "Wind source semantics are not confirmed. Set source_fields "
            f"{missing} in config/ibtracs_wind_field.json after checking the dataset provenance."
        )
    if source["wind_unit"] not in {"knots", "m/s", "mph"}:
        raise ValueError("wind_unit must be one of: knots, m/s, mph")
    if float(source["wind_averaging_period_minutes"]) <= 0 or float(source["wind_height_m"]) <= 0:
        raise ValueError("Wind averaging period and measurement height must be positive")
    rmw = config.get("rmw", {})
    if float(rmw.get("rmw_km", 0)) <= 0:
        raise ValueError("rmw.rmw_km must be explicitly set to a positive value")
    if config.get("radial_profile", "willoughby_2006") != "willoughby_2006":
        raise ValueError("Only willoughby_2006 radial profile is currently implemented")


def convert_wind_to_ms(values, unit: str):
    values = np.asarray(values, dtype=float)
    if unit == "knots":
        return values * KNOT_TO_MS
    if unit == "mph":
        return values * MPH_TO_MS
    if unit == "m/s":
        return values.copy()
    raise ValueError(f"Unsupported wind unit: {unit}")


def haversine_distance_and_bearing(
    center_latitude: float, center_longitude: float, latitude, longitude
) -> tuple[np.ndarray, np.ndarray]:
    """Return great-circle radius (km) and initial bearing from center (degrees)."""
    lat1 = math.radians(float(center_latitude))
    lon1 = math.radians(float(center_longitude))
    lat2 = np.radians(np.asarray(latitude, dtype=float))
    lon2 = np.radians(np.asarray(longitude, dtype=float))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + math.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    radius = 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    x = np.sin(dlon) * np.cos(lat2)
    y = math.cos(lat1) * np.sin(lat2) - math.sin(lat1) * np.cos(lat2) * np.cos(dlon)
    bearing = (np.degrees(np.arctan2(x, y)) + 360.0) % 360.0
    return radius, bearing


def willoughby_2006_radial_wind_ms(
    radius_km, vmax_ms: float, rmw_km: float, latitude_deg: float
):
    """Empirical two-region Willoughby et al. (2006) radial wind profile."""
    r = np.asarray(radius_km, dtype=float)
    vmax = float(vmax_ms)
    rmw = float(rmw_km)
    if vmax < 0 or rmw <= 0:
        raise ValueError("vmax_ms must be nonnegative and rmw_km must be positive")
    if vmax == 0:
        return np.zeros_like(r)
    phi = abs(float(latitude_deg))
    log_rmw = math.log(rmw)
    exponent = max(0.1, 2.1340 + 0.0077 * vmax - 0.4522 * log_rmw - 0.0038 * phi)
    x1 = max(1.0, 287.6 - 1.942 * vmax + 7.799 * log_rmw + 1.819 * phi)
    weight = min(1.0, max(0.0, 0.5913 + 0.0029 * vmax - 0.1361 * log_rmw - 0.0042 * phi))
    x2 = 25.0
    inner = vmax * np.power(np.clip(r / rmw, 0.0, None), exponent)
    outer_distance = np.maximum(r - rmw, 0.0)
    outer = vmax * (
        (1.0 - weight) * np.exp(-outer_distance / x1)
        + weight * np.exp(-outer_distance / x2)
    )
    return np.where(r < rmw, inner, outer)


def reconstruct_wind_at_points(
    *,
    storm_latitude: float,
    storm_longitude: float,
    vmax_ms: float,
    rmw_km: float,
    asset_latitudes,
    asset_longitudes,
    translation_speed_kmh: float | None = None,
    translation_heading_deg: float | None = None,
    hemisphere: str = "north",
    asymmetry: str = "miyazaki_1962",
) -> dict[str, np.ndarray]:
    """Evaluate surface wind vectors at point locations around one storm center.

    Tangential circulation is counterclockwise in the Northern Hemisphere and
    clockwise in the Southern Hemisphere. Translation asymmetry is added as a
    Miyazaki-style exponentially decaying fraction of storm translation velocity.
    """
    if hemisphere not in {"north", "south"}:
        raise ValueError("hemisphere must be 'north' or 'south'")
    radius, radial_bearing = haversine_distance_and_bearing(
        storm_latitude, storm_longitude, asset_latitudes, asset_longitudes
    )
    tangential = willoughby_2006_radial_wind_ms(
        radius, vmax_ms, rmw_km, storm_latitude
    )
    tangent_bearing = radial_bearing + (-90.0 if hemisphere == "north" else 90.0)
    tangent_rad = np.radians(tangent_bearing)
    east = tangential * np.sin(tangent_rad)
    north = tangential * np.cos(tangent_rad)

    translation_ms = 0.0
    heading = None
    if translation_speed_kmh is not None and np.isfinite(translation_speed_kmh):
        translation_ms = max(0.0, float(translation_speed_kmh)) / 3.6
    if translation_heading_deg is not None and np.isfinite(translation_heading_deg):
        heading = float(translation_heading_deg) % 360.0
    if asymmetry == "miyazaki_1962" and translation_ms > 0 and heading is not None:
        coefficient = np.exp(-np.pi * radius / 500.0)
        heading_rad = math.radians(heading)
        east = east + coefficient * translation_ms * math.sin(heading_rad)
        north = north + coefficient * translation_ms * math.cos(heading_rad)
    elif asymmetry not in {"none", "miyazaki_1962"}:
        raise ValueError(f"Unsupported translation asymmetry: {asymmetry}")

    speed = np.hypot(east, north)
    direction = (np.degrees(np.arctan2(east, north)) + 360.0) % 360.0
    return {
        "radius_from_storm_center_km": radius,
        "radial_bearing_deg": radial_bearing,
        "wind_speed_symmetric_ms": tangential,
        "wind_speed_asymmetric_ms": speed,
        "wind_direction_to_deg": direction,
    }


def prepare_wind_track_parameters(
    tracks: pd.DataFrame, config: dict[str, Any]
) -> pd.DataFrame:
    """Add configured wind adjustment, explicit-unit Vmax, and RMW.

    The configured additive offset is applied to every finite numeric source
    observation after unit conversion. Missing values remain missing.
    """
    validate_wind_config(config)
    source = config["source_fields"]
    column = str(source["wind_column"])
    if column not in tracks:
        raise ValueError(f"Track table does not contain configured wind column {column!r}")
    frame = tracks.copy()
    raw = pd.to_numeric(frame[column], errors="coerce")
    observed_vmax_ms = convert_wind_to_ms(raw.to_numpy(dtype=float), str(source["wind_unit"]))

    # Digital Typhoon/JMA maximum sustained wind is available for grades 3–5.
    # Grades 2 (tropical depression) and 6 (extratropical cyclone) have no
    # applicable value in this field; their exported zero placeholders must
    # not be treated as measured calm winds or receive an additive offset.
    eligible_grades = source.get("eligible_grade_values")
    grade_column = str(source.get("grade_column", "grade"))
    if eligible_grades is not None:
        if grade_column not in frame:
            raise ValueError(
                f"Track table does not contain configured grade column {grade_column!r}"
            )
        grade_values = pd.to_numeric(frame[grade_column], errors="coerce")
        grade_eligible = grade_values.isin([float(value) for value in eligible_grades])
        observed_vmax_ms = np.where(grade_eligible.to_numpy(), observed_vmax_ms, np.nan)
    else:
        grade_eligible = pd.Series(True, index=frame.index)

    adjustment = config.get("wind_adjustment", {})
    adjustment_value = float(adjustment.get("value", 0.0))
    adjustment_unit = str(adjustment.get("unit", "knots"))
    if not np.isfinite(adjustment_value) or adjustment_value < 0:
        raise ValueError("wind_adjustment.value must be a finite, nonnegative number")
    adjustment_ms = float(convert_wind_to_ms([adjustment_value], adjustment_unit)[0])
    adjustment_applied_ms = np.where(
        grade_eligible.to_numpy() & np.isfinite(observed_vmax_ms),
        adjustment_ms,
        0.0,
    )
    adjusted_vmax_ms = observed_vmax_ms + adjustment_applied_ms
    # Missing, ineligible, zero, and non-finite source observations remain unavailable.
    vmax = np.where(np.isfinite(adjusted_vmax_ms) & (adjusted_vmax_ms > 0), adjusted_vmax_ms, np.nan)

    frame["vmax_source_raw"] = raw
    frame["wind_grade_eligible"] = grade_eligible.to_numpy()
    frame["vmax_observed_ms"] = observed_vmax_ms
    frame["wind_adjustment_value"] = adjustment_value
    frame["wind_adjustment_unit"] = adjustment_unit
    frame["wind_adjustment_ms"] = adjustment_ms
    frame["wind_adjustment_applied_ms"] = adjustment_applied_ms
    frame["vmax_adjusted_ms"] = vmax
    frame["vmax_ms"] = vmax
    frame["rmw_km"] = float(config["rmw"]["rmw_km"])
    frame["wind_unit_source"] = str(source["wind_unit"])
    frame["wind_averaging_period_minutes"] = float(source["wind_averaging_period_minutes"])
    frame["wind_height_m"] = float(source["wind_height_m"])
    frame["rmw_method"] = str(config["rmw"].get("method", "fixed_assumption"))
    frame["wind_model"] = "willoughby_2006_radial_plus_miyazaki_1962_translation"
    frame["wind_model_status"] = str(config.get("model_status", "uncalibrated_research_estimate"))
    return frame
