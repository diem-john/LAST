import pandas as pd
import pytest

from forecasting.data.ibtracs_regions import (
    select_storms_intersecting_bbox,
    select_storms_near_synthetic_grid,
    select_storms_within_reference_radius,
    summarize_selected_storms,
)


@pytest.fixture
def tracks():
    return pd.DataFrame([
        {"storm_instance_id": 1, "latitude": 20.0, "longitude": 130.0,
         "timestamp_utc": "2020-01-01T00:00:00+00:00",
         "nearest_synthetic_bus_distance_km": 500.0},
        {"storm_instance_id": 1, "latitude": 22.0, "longitude": 122.0,
         "timestamp_utc": "2020-01-01T01:00:00+00:00",
         "nearest_synthetic_bus_distance_km": 100.0},
        {"storm_instance_id": 2, "latitude": 35.0, "longitude": 150.0,
         "timestamp_utc": "2020-02-01T00:00:00+00:00",
         "nearest_synthetic_bus_distance_km": 800.0},
        {"storm_instance_id": 3, "latitude": 5.0, "longitude": 90.0,
         "timestamp_utc": "2020-03-01T00:00:00+00:00",
         "nearest_synthetic_bus_distance_km": 1200.0},
    ])


def test_bbox_selects_whole_storm_when_any_point_intersects(tracks):
    selected = select_storms_intersecting_bbox(
        tracks, longitude_min=100, longitude_max=180,
        latitude_min=0, latitude_max=60,
    )
    assert set(selected["storm_instance_id"]) == {1, 2}
    assert len(selected[selected["storm_instance_id"] == 1]) == 2


def test_taiwan_radius_selection_retains_complete_track(tracks):
    selected = select_storms_within_reference_radius(
        tracks, reference_latitude=23.7, reference_longitude=121.0,
        radius_km=200, distance_column="distance_to_taiwan_reference_km",
    )
    assert set(selected["storm_instance_id"]) == {1}
    assert len(selected) == 2
    assert selected["distance_to_taiwan_reference_km"].notna().all()


def test_minxiong_selection_uses_nearest_synthetic_bus_distance(tracks):
    selected = select_storms_near_synthetic_grid(tracks, radius_km=150)
    assert set(selected["storm_instance_id"]) == {1}
    assert len(selected) == 2


def test_missing_grid_distance_column_fails_clearly(tracks):
    with pytest.raises(ValueError, match="rerun IBTrACS processing"):
        select_storms_near_synthetic_grid(
            tracks.drop(columns=["nearest_synthetic_bus_distance_km"]), radius_km=150
        )


def test_summary_reports_storm_and_observation_counts(tracks):
    summary = summarize_selected_storms(tracks)
    assert len(summary) == 3
    storm_one = summary.loc[summary["storm_instance_id"] == 1].iloc[0]
    assert storm_one["observation_count"] == 2
    assert storm_one["observed_start_utc"] == "2020-01-01T00:00:00+00:00"
