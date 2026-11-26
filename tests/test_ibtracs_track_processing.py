import numpy as np
import pandas as pd
import pytest

from forecasting.data.ibtracs_tracks import build_ibtracs_tracks, write_ibtracs_outputs


def _write_storm(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)


def test_builds_ordered_tracks_metrics_and_preserves_rejected_rows(tmp_path):
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    _write_storm(metadata / "202001.csv", {
        "year": [2020, 2020, 2020, 2020],
        "month": [1, 1, 1, 1],
        "day": [1, 1, 1, 1],
        "hour": [0, 6, 6, 12],
        "lat": [0.0, 0.0, 0.0, 1.0],
        "lng": [0.0, 1.0, 1.0, 1.0],
        "wind": [20, 30, 30, 40],
        "pressure": [1000, 990, 990, 980],
        "grade": ["TD", "TS", "TS", "TY"],
    })
    _write_storm(metadata / "202002.csv", {
        "year": [2020],
        "month": [1],
        "day": [2],
        "hour": [0],
        "lat": [95.0],
        "lng": [120.0],
        "wind": [25],
        "pressure": [995],
    })

    tracks, rejected, summaries, audit = build_ibtracs_tracks(metadata)

    assert audit["metadata_file_count"] == 2
    assert audit["source_row_count"] == 5
    assert audit["storm_instance_count"] == 1
    assert audit["valid_track_row_count"] == 4
    assert audit["rejected_row_count"] == 1
    assert len(rejected) == 1
    assert rejected.iloc[0]["rejection_reason"] == "invalid_or_missing_coordinates"

    assert tracks["timestamp_utc"].is_monotonic_increasing
    assert tracks["duplicate_timestamp"].sum() == 1
    first_movement = tracks.iloc[1]
    assert first_movement["segment_distance_km"] == pytest.approx(111.195, rel=0.002)
    assert first_movement["translation_speed_kmh"] == pytest.approx(18.5325, rel=0.002)
    assert np.isnan(tracks.iloc[2]["translation_speed_kmh"])
    assert summaries.iloc[0]["maximum_wind_raw"] == 40.0
    assert summaries.iloc[0]["minimum_pressure_raw"] == 980.0


def test_normalizes_0_360_longitude_and_computes_synthetic_grid_proximity(tmp_path):
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    _write_storm(metadata / "202003.csv", {
        "year": [2020],
        "month": [2],
        "day": [1],
        "hour": [0],
        "lat": [23.5],
        "lng": [240.5],
        "wind": [50],
        "pressure": [970],
    })
    buses = tmp_path / "buses.csv"
    bus_rows = [{"bus_id": 1, "latitude": 23.5, "longitude": -119.5}]
    bus_rows.extend(
        {"bus_id": index, "latitude": 40.0 + index / 100, "longitude": 100.0}
        for index in range(2, 34)
    )
    pd.DataFrame(bus_rows).to_csv(buses, index=False)

    tracks, _, summaries, audit = build_ibtracs_tracks(
        metadata, bus_locations_csv=buses
    )

    assert tracks.iloc[0]["longitude"] == pytest.approx(-119.5)
    assert bool(tracks.iloc[0]["longitude_normalized_from_0_360"])
    assert tracks.iloc[0]["nearest_synthetic_bus_id"] == 1
    assert tracks.iloc[0]["nearest_synthetic_bus_distance_km"] == pytest.approx(0.0)
    assert summaries.iloc[0]["closest_approach_to_synthetic_grid_km"] == pytest.approx(0.0)
    assert audit["grid_proximity_status"] == "computed_to_synthetic_bus_points"


def test_rejects_metadata_file_missing_required_track_columns(tmp_path):
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    pd.DataFrame({"year": [2020], "lat": [20.0], "lng": [120.0]}).to_csv(
        metadata / "bad.csv", index=False
    )

    with pytest.raises(ValueError, match="missing required columns"):
        build_ibtracs_tracks(metadata)


def test_writes_tracks_rejected_records_summary_and_audit(tmp_path):
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    _write_storm(metadata / "202004.csv", {
        "year": [2020],
        "month": [3],
        "day": [1],
        "hour": [0],
        "lat": [23.5],
        "lng": [120.5],
    })
    tracks, rejected, summaries, audit = build_ibtracs_tracks(metadata)
    paths = write_ibtracs_outputs(tracks, rejected, summaries, audit, tmp_path / "out")

    assert set(paths) == {"tracks_csv", "rejected_records_csv", "storm_summary_csv", "audit_json"}
    assert all((tmp_path / "out" / name).is_file() for name in (
        "ibtracs_tracks.csv",
        "ibtracs_rejected_records.csv",
        "ibtracs_storm_summary.csv",
        "ibtracs_track_audit.json",
    ))
