"""Unit tests for cyclone wind reconstruction, grid exposure, and fragility."""
import numpy as np
import pandas as pd
import pytest

from forecasting.physics.tropical_cyclone_wind import (
    convert_wind_to_ms,
    reconstruct_wind_at_points,
    validate_wind_config,
    willoughby_2006_radial_wind_ms,
)
from grid.ibtracs_wind_exposure import build_synthetic_grid_samples, evaluate_grid_wind_exposure
from grid.ibtracs_fragility import (
    calculate_branch_wind_fragility,
    load_wind_fragility_config,
    pole_failure_probability,
    sample_weather_contingencies,
    select_peak_network_snapshot,
    fit_logistic_pole_fragility,
    pole_failure_probability,
)
from forecasting.physics.tropical_cyclone_wind import prepare_wind_track_parameters


def _wind_config():
    return {
        "source_fields": {
            "wind_column": "wind", "wind_unit": "knots",
            "wind_averaging_period_minutes": 10, "wind_height_m": 10,
        },
        "rmw": {"rmw_km": 30.0, "method": "test"},
        "radial_profile": "willoughby_2006",
        "hemisphere": "north",
        "translation_asymmetry": "miyazaki_1962",
        "model_status": "test",
    }


def _fragility_config():
    return {
        "schema_version": 1, "calibration_status": "uncalibrated_literature_reference",
        "pole_probability_intercept": 0.0001,
        "pole_probability_exponent_per_mph": 0.0421,
        "pole_spacing_m": 50.0, "calibration_note": "test only",
    }


def _case():
    return {
        "branch": [
            {"branch_id": 1, "from_bus": 1, "to_bus": 2, "in_service": True, "status": "closed"},
            {"branch_id": 2, "from_bus": 2, "to_bus": 3, "in_service": True, "status": "closed"},
            {"branch_id": 33, "from_bus": 1, "to_bus": 3, "in_service": False, "status": "normally_open_tie"},
        ],
        "bus": [{"bus_id": 1}, {"bus_id": 2}, {"bus_id": 3}],
        "base": {"slack_bus": 1},
    }


def test_source_wind_semantics_are_required():
    config = _wind_config()
    validate_wind_config(config)
    config["source_fields"]["wind_unit"] = None
    with pytest.raises(ValueError, match="not confirmed"):
        validate_wind_config(config)


def test_explicit_wind_unit_conversion():
    assert convert_wind_to_ms([10], "knots")[0] == pytest.approx(5.1444444)
    assert convert_wind_to_ms([10], "mph")[0] == pytest.approx(4.4704)

def test_additive_15_knot_adjustment_preserves_original_and_missing_values():
    config = _wind_config()
    config["wind_adjustment"] = {"value": 15.0, "unit": "knots"}
    tracks = pd.DataFrame({"wind": [0.0, 10.0, np.nan]})

    result = prepare_wind_track_parameters(tracks, config)

    knot_ms = 0.5144444444444445
    assert result["vmax_source_raw"].iloc[:2].tolist() == [0.0, 10.0]
    assert result["vmax_observed_ms"].iloc[0] == pytest.approx(0.0)
    assert result["vmax_ms"].iloc[0] == pytest.approx(15.0 * knot_ms)
    assert result["vmax_ms"].iloc[1] == pytest.approx(25.0 * knot_ms)
    assert np.isnan(result["vmax_ms"].iloc[2])
    assert result["wind_adjustment_ms"].eq(15.0 * knot_ms).all()


def test_wind_adjustment_rejects_negative_offset():
    config = _wind_config()
    config["wind_adjustment"] = {"value": -15.0, "unit": "knots"}
    with pytest.raises(ValueError, match="nonnegative"):
        prepare_wind_track_parameters(pd.DataFrame({"wind": [0.0]}), config)


def test_willoughby_profile_peaks_at_configured_rmw():
    radii = np.array([5.0, 15.0, 30.0, 60.0, 100.0])
    speeds = willoughby_2006_radial_wind_ms(radii, 40.0, 30.0, 23.5)
    assert int(np.argmax(speeds)) == 2
    assert speeds[2] == pytest.approx(40.0)


def test_translation_asymmetry_adds_wind_downstream():
    common = dict(
        storm_latitude=20.0, storm_longitude=120.0, vmax_ms=40.0, rmw_km=30.0,
        asset_latitudes=[20.0, 20.0], asset_longitudes=[120.5, 119.5],
        translation_speed_kmh=30.0, translation_heading_deg=90.0,
    )
    asymmetric = reconstruct_wind_at_points(**common, asymmetry="miyazaki_1962")
    symmetric = reconstruct_wind_at_points(**common, asymmetry="none")
    assert np.all(asymmetric["wind_speed_asymmetric_ms"] >= symmetric["wind_speed_symmetric_ms"] - 1e-9)
    assert not np.allclose(asymmetric["wind_speed_asymmetric_ms"], symmetric["wind_speed_symmetric_ms"])


def test_grid_samples_include_bus_points_and_active_branch_samples():
    buses = pd.DataFrame({
        "bus_id": [1, 2, 3], "latitude": [23.5, 23.51, 23.52],
        "longitude": [120.4, 120.41, 120.42],
    })
    bus_assets, branch_samples = build_synthetic_grid_samples(
        buses, _case(), samples_per_branch=3
    )
    assert len(bus_assets) == 3
    assert len(branch_samples) == 6
    assert set(branch_samples["branch_id"]) == {1, 2}


def test_grid_wind_exposure_returns_bus_and_branch_rows():
    buses = pd.DataFrame({
        "bus_id": [1, 2, 3], "latitude": [23.5, 23.51, 23.52],
        "longitude": [120.4, 120.41, 120.42],
    })
    bus_assets, branch_samples = build_synthetic_grid_samples(buses, _case(), samples_per_branch=2)
    tracks = pd.DataFrame([{
        "storm_instance_id": "s1", "timestamp_utc": "2020-01-01T00:00:00Z",
        "latitude": 23.5, "longitude": 120.4, "vmax_ms": 40.0, "rmw_km": 30.0,
        "translation_speed_kmh": 20.0, "heading_deg_from_previous": 90.0,
        "wind_model": "test", "wind_model_status": "test",
    }])
    result = evaluate_grid_wind_exposure(tracks, bus_assets, branch_samples, _wind_config())
    assert len(result) == 5
    assert set(result["asset_type"]) == {"bus", "branch"}
    assert result["wind_speed_ms"].ge(0).all()


def test_literature_reference_pole_curve_is_monotonic():
    config = _fragility_config()
    values = [pole_failure_probability(v, config) for v in (10, 20, 30, 40)]
    assert values == sorted(values)


def test_branch_fragility_and_peak_snapshot():
    exposure = pd.DataFrame([
        {"storm_instance_id": "s1", "timestamp_utc": "t1", "asset_type": "branch",
         "branch_id": 1, "wind_speed_ms": 20.0},
        {"storm_instance_id": "s1", "timestamp_utc": "t1", "asset_type": "branch",
         "branch_id": 2, "wind_speed_ms": 30.0},
        {"storm_instance_id": "s1", "timestamp_utc": "t2", "asset_type": "branch",
         "branch_id": 1, "wind_speed_ms": 40.0},
        {"storm_instance_id": "s1", "timestamp_utc": "t2", "asset_type": "branch",
         "branch_id": 2, "wind_speed_ms": 10.0},
    ])
    lengths = pd.DataFrame({
        "branch_id": [1, 2], "from_bus": [1, 2], "to_bus": [2, 3],
        "synthetic_straight_line_length_m": [100.0, 150.0],
    })
    probabilities = calculate_branch_wind_fragility(exposure, lengths, _fragility_config())
    peak = select_peak_network_snapshot(probabilities)
    assert set(peak["timestamp_utc"]) == {"t2"}
    assert peak["branch_failure_probability"].between(0, 1).all()


def test_weather_contingency_sampler_is_reproducible():
    case = {
        "base": {"slack_bus": 1},
        "bus": [{"bus_id": 1}, {"bus_id": 2}, {"bus_id": 3}],
        "branch": [
            {"branch_id": 1, "from_bus": 1, "to_bus": 2, "in_service": True, "status": "closed"},
            {"branch_id": 2, "from_bus": 2, "to_bus": 3, "in_service": True, "status": "closed"},
        ],
    }
    peak = pd.DataFrame([
        {"storm_instance_id": "s1", "timestamp_utc": "t1", "branch_id": 1,
         "branch_failure_probability": 1.0, "network_peak_wind_ms": 40.0,
         "fragility_model_status": "uncalibrated_literature_reference"},
        {"storm_instance_id": "s1", "timestamp_utc": "t1", "branch_id": 2,
         "branch_failure_probability": 0.0, "network_peak_wind_ms": 40.0,
         "fragility_model_status": "uncalibrated_literature_reference"},
    ])
    a, _ = sample_weather_contingencies(peak, case, samples_per_storm=3, seed=7)
    b, _ = sample_weather_contingencies(peak, case, samples_per_storm=3, seed=7)
    assert a == b
    assert all(item["failed_branch_ids"] == [1] for item in a)



def test_local_logistic_fragility_can_be_fitted_from_paired_outcomes():
    winds = np.linspace(10.0, 50.0, 100)
    probabilities = 1.0 / (1.0 + np.exp(-(-8.0 + 0.2 * winds)))
    rng = np.random.default_rng(17)
    failed = rng.binomial(1, probabilities)
    observations = pd.DataFrame({
        "wind_speed_ms": winds,
        "failed": failed,
    })
    fitted = fit_logistic_pole_fragility(observations)
    assert fitted["sample_count"] == 100
    assert fitted["failure_count"] >= 5
    assert fitted["nonfailure_count"] >= 5
    config = {
        "model_type": "logistic_calibrated",
        "calibration_status": "locally_calibrated",
        "pole_logistic_intercept": fitted["pole_logistic_intercept"],
        "pole_logistic_slope_per_ms": fitted["pole_logistic_slope_per_ms"],
    }
    assert pole_failure_probability(40.0, config) > pole_failure_probability(10.0, config)


def test_logistic_fragility_rejects_single_class_labels():
    observations = pd.DataFrame({
        "wind_speed_ms": np.linspace(5.0, 30.0, 30),
        "failed": [0] * 30,
    })
    with pytest.raises(ValueError, match=">=5 failures"):
        fit_logistic_pole_fragility(observations)
