from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from grid.weather_faults import (
    build_branch_contingency,
    calculate_branch_failure_probabilities,
    generate_fault_scenarios,
    load_fragility_config,
)

ROOT = Path(__file__).resolve().parents[1]


def write_features(path: Path, rows):
    fields = ["timestamp_utc", "source_id", "variable", "value", "unit", "asset_type",
              "asset_id", "bus_id", "branch_id", "spatial_scope", "mapping_method",
              "distance_to_source_m", "time_basis", "temporal_semantics", "sample_location_semantics"]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def row(branch, variable, value, unit="m s-1", **extra):
    result = {
        "timestamp_utc": "2026-11-26T00:00:00+00:00", "source_id": "test", "variable": variable,
        "value": value, "unit": unit, "asset_type": "branch_sample", "asset_id": f"BRANCH_{branch:02d}",
        "bus_id": "", "branch_id": branch, "spatial_scope": "point", "mapping_method": "test",
        "distance_to_source_m": 0, "time_basis": "UTC", "temporal_semantics": "historical_reanalysis",
        "sample_location_semantics": "synthetic_midpoint",
    }
    result.update(extra)
    return result


def test_probabilities_aggregate_wind_vector_and_flood_depth(tmp_path):
    features = tmp_path / "features.csv"
    write_features(features, [
        row(1, "u10", 3), row(1, "v10", 4),
        row(2, "wind_speed", 35),
        row(3, "flood_depth", 0.8, "m"),
    ])
    config = load_fragility_config(ROOT / "config/weather_fragility_demo.json")
    result = calculate_branch_failure_probabilities(features, config)
    assert len(result) == 3
    first = next(item for item in result if item["branch_id"] == 1)
    assert first["hazard_exposures"]["wind_speed"] == 5.0
    assert 0.0 < first["combined_failure_probability"] < 1.0
    third = next(item for item in result if item["branch_id"] == 3)
    assert third["hazard_exposures"]["flood_depth"] == 0.8


def test_regional_features_are_excluded_unless_explicitly_enabled(tmp_path):
    features = tmp_path / "features.csv"
    write_features(features, [row(1, "wind_speed", 40, **{"spatial_scope": "regional"})])
    config = load_fragility_config(ROOT / "config/weather_fragility_demo.json")
    with pytest.raises(ValueError, match="No usable branch"):
        calculate_branch_failure_probabilities(features, config)
    assert calculate_branch_failure_probabilities(features, config, include_regional=True)


def test_unknown_units_fail_loudly(tmp_path):
    features = tmp_path / "features.csv"
    write_features(features, [row(1, "wind_speed", 40, "knots")])
    config = load_fragility_config(ROOT / "config/weather_fragility_demo.json")
    with pytest.raises(ValueError, match="No explicit unit conversion"):
        calculate_branch_failure_probabilities(features, config)


def test_scenario_sampling_is_reproducible_and_probability_extremes_work():
    records = [
        {"timestamp_utc": "t", "temporal_semantics": "forecast", "branch_id": 1,
         "combined_failure_probability": 1.0, "fragility_model_status": "test"},
        {"timestamp_utc": "t", "temporal_semantics": "forecast", "branch_id": 2,
         "combined_failure_probability": 0.0, "fragility_model_status": "test"},
    ]
    first = generate_fault_scenarios(records, samples_per_timestamp=4, seed=19)
    second = generate_fault_scenarios(records, samples_per_timestamp=4, seed=19)
    assert first == second
    assert all(item["failed_branch_ids"] == [1] for item in first)


def mini_case():
    return {
        "base": {"slack_bus": 1},
        "bus": [{"bus_id": bus} for bus in range(1, 6)],
        "branch": [
            {"branch_id": 1, "from_bus": 1, "to_bus": 2, "in_service": True, "status": "closed"},
            {"branch_id": 2, "from_bus": 2, "to_bus": 3, "in_service": True, "status": "closed"},
            {"branch_id": 3, "from_bus": 3, "to_bus": 4, "in_service": True, "status": "closed"},
            {"branch_id": 4, "from_bus": 4, "to_bus": 5, "in_service": True, "status": "closed"},
            {"branch_id": 33, "from_bus": 1, "to_bus": 5, "in_service": False, "status": "normally_open_tie"},
        ],
    }


def test_branch_contingency_removes_edges_and_reports_islands():
    result = build_branch_contingency(mini_case(), [2, 4])
    assert result["failed_branch_ids"] == [2, 4]
    assert result["component_count"] == 3
    assert 1 in result["slack_connected_buses"]
    assert 3 not in result["slack_connected_buses"]
    assert result["topology_only"] is True


def test_unknown_branch_and_tie_failures_are_rejected():
    case = mini_case()
    with pytest.raises(ValueError, match="Unknown branch"):
        build_branch_contingency(case, [999])
    with pytest.raises(ValueError, match="normally-open ties"):
        build_branch_contingency(case, [33])


def test_rainfall_alone_is_not_misrepresented_as_direct_branch_failure(tmp_path):
    features = tmp_path / "features.csv"
    write_features(features, [row(1, "precipitation", 80, "mm h-1")])
    config = load_fragility_config(ROOT / "config/weather_fragility_demo.json")
    with pytest.raises(ValueError, match="Rainfall is not a direct branch-failure driver"):
        calculate_branch_failure_probabilities(features, config)
