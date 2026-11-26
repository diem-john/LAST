"""Tests for IBTrACS closest-approach and spatial exposure screening."""
import pandas as pd
import pytest

from forecasting.data.ibtracs_exposure import (
    build_exposure_outputs,
    classify_minxiong_exposure,
)


def _tracks():
    return pd.DataFrame([
        {
            "storm_instance_id": "storm-a", "timestamp_utc": "2020-01-01T00:00:00Z",
            "latitude": 23.5, "longitude": 120.5,
            "nearest_synthetic_bus_distance_km": 80.0,
            "nearest_synthetic_bus_id": 18, "translation_speed_kmh": 20.0,
            "heading_deg_from_previous": 90.0, "source_row_number": 2,
            "wind": 50, "pressure": 990,
        },
        {
            "storm_instance_id": "storm-a", "timestamp_utc": "2020-01-01T06:00:00Z",
            "latitude": 23.6, "longitude": 120.6,
            "nearest_synthetic_bus_distance_km": 40.0,
            "nearest_synthetic_bus_id": 33, "translation_speed_kmh": 22.0,
            "heading_deg_from_previous": 45.0, "source_row_number": 3,
            "wind": 60, "pressure": 980,
        },
        {
            "storm_instance_id": "storm-b", "timestamp_utc": "2021-08-01T00:00:00Z",
            "latitude": 30.0, "longitude": 130.0,
            "nearest_synthetic_bus_distance_km": 350.0,
            "nearest_synthetic_bus_id": 1, "translation_speed_kmh": None,
            "heading_deg_from_previous": None, "source_row_number": 2,
            "wind": 70, "pressure": 970,
        },
    ])


def test_classification_uses_exploratory_distance_bands():
    closest = pd.DataFrame({
        "storm_instance_id": ["a", "b", "c", "d", "e"],
        "minxiong_distance_km": [20, 75, 150, 250, 350],
    })
    result = classify_minxiong_exposure(closest)
    assert result["screening_band"].astype(str).tolist() == [
        "very_high_proximity", "high_proximity", "moderate_proximity",
        "low_proximity", "outside_screen",
    ]
    assert result["interpretation"].str.contains("not_physical_risk").all()


def test_closest_approach_outputs_are_deterministic_and_audited(tmp_path):
    audit = build_exposure_outputs(_tracks(), tmp_path)
    minxiong = pd.read_csv(tmp_path / "ibtracs_minxiong_closest_approach.csv")
    row = minxiong.loc[minxiong["storm_instance_id"] == "storm-a"].iloc[0]
    assert row["minxiong_distance_km"] == pytest.approx(40.0)
    assert row["minxiong_nearest_synthetic_bus_id"] == 33
    assert row["maximum_wind_raw"] == pytest.approx(60.0)
    assert audit["status"] == "ibtracs_exposure_screening_completed"
    assert audit["minxiong_synthetic_grid"]["storm_count"] == 2
    assert (tmp_path / "ibtracs_exposure_audit.json").is_file()
    assert (tmp_path / "figures/minxiong_closest_approach_map.png").is_file()


def test_taiwan_table_only_contains_storms_within_configured_radius(tmp_path):
    build_exposure_outputs(_tracks(), tmp_path, taiwan_radius_km=500.0)
    taiwan = pd.read_csv(tmp_path / "ibtracs_taiwan_closest_approach.csv")
    assert set(taiwan["storm_instance_id"]) == {"storm-a"}


def test_invalid_threshold_order_is_rejected():
    closest = pd.DataFrame({"minxiong_distance_km": [10.0]})
    with pytest.raises(ValueError, match="strictly increasing"):
        classify_minxiong_exposure(closest, (100.0, 50.0, 200.0, 300.0))


def test_missing_synthetic_grid_distance_is_rejected():
    tracks = _tracks().drop(columns=["nearest_synthetic_bus_distance_km"])
    with pytest.raises(ValueError, match="nearest_synthetic_bus_distance_km"):
        build_exposure_outputs(tracks, "unused")
