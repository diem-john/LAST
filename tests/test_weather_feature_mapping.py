from __future__ import annotations

import pandas as pd
import pytest

from scripts.map_weather_features_to_ieee33 import map_observations


def write_bus_locations(path):
    rows = []
    for bus_id in range(1, 34):
        rows.append({
            "bus_id": bus_id,
            "latitude": 23.5 + bus_id * 0.0001,
            "longitude": 120.4 + bus_id * 0.0001,
        })
    pd.DataFrame(rows).to_csv(path, index=False)


def write_weather(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)


def base_row(**overrides):
    row = {
        "timestamp": "2026-11-12T00:00:00+00:00",
        "source_id": "test_source",
        "variable": "precipitation",
        "value": 1.25,
        "spatial_scope": "point",
        "time_basis": "UTC",
        "temporal_semantics": "historical_observation",
        "latitude": 23.5001,
        "longitude": 120.4001,
    }
    row.update(overrides)
    return row


def test_point_observation_maps_to_one_nearest_asset(tmp_path):
    buses, weather = tmp_path / "buses.csv", tmp_path / "weather.csv"
    write_bus_locations(buses)
    write_weather(weather, [base_row()])
    rows, summary = map_observations(weather, buses)
    assert len(rows) == 1
    assert rows[0]["asset_type"] in {"bus", "branch_sample"}
    assert rows[0]["mapping_method"] == "nearest_source_point_in_epsg3826"
    assert rows[0]["distance_to_source_m"] >= 0
    assert summary["asset_sample_count"] == 65


def test_regional_observation_is_broadcast_without_spatial_downscaling(tmp_path):
    buses, weather = tmp_path / "buses.csv", tmp_path / "weather.csv"
    write_bus_locations(buses)
    write_weather(weather, [base_row(spatial_scope="regional", latitude=None, longitude=None)])
    rows, _ = map_observations(weather, buses)
    assert len(rows) == 65
    assert {row["mapping_method"] for row in rows} == {
        "regional_area_mean_broadcast_no_local_spatial_disaggregation"
    }
    assert all(row["distance_to_source_m"] is None for row in rows)


def test_naive_timestamp_is_rejected_instead_of_assumed_utc(tmp_path):
    buses, weather = tmp_path / "buses.csv", tmp_path / "weather.csv"
    write_bus_locations(buses)
    write_weather(weather, [base_row(timestamp="2026-11-12 08:00:00", time_basis="LST")])
    with pytest.raises(ValueError, match="explicit UTC offset"):
        map_observations(weather, buses)


def test_missing_measurement_remains_null(tmp_path):
    buses, weather = tmp_path / "buses.csv", tmp_path / "weather.csv"
    write_bus_locations(buses)
    write_weather(weather, [base_row(value=None)])
    rows, _ = map_observations(weather, buses)
    assert rows[0]["value"] is None
