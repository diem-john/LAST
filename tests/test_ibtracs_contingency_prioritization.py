import pandas as pd

from scripts.run_ibtracs_contingency_prioritization import (
    build_branch_priority,
    build_representative_contingencies,
    rank_storm_events,
)


def _case():
    return {
        "base": {"slack_bus": 1},
        "bus": [{"bus_id": 1}, {"bus_id": 2}, {"bus_id": 3}],
        "branch": [
            {"branch_id": 1, "from_bus": 1, "to_bus": 2, "in_service": True, "status": "closed"},
            {"branch_id": 2, "from_bus": 2, "to_bus": 3, "in_service": True, "status": "closed"},
            {"branch_id": 3, "from_bus": 1, "to_bus": 3, "in_service": False, "status": "normally_open_tie"},
        ],
    }


def test_branch_priority_maps_endpoints_and_measures_rank_stability():
    ranking = pd.DataFrame([
        {"run_id": run, "wind_adjustment_knots": 0, "rmw_km": 20,
         "pole_spacing_m": 40, "branch_id": branch, "mean_peak_failure_probability": probability,
         "max_peak_failure_probability": probability * 2, "storm_event_count": 2}
        for run, values in [(1, [(1, .1), (2, .2)]), (2, [(1, .3), (2, .1)])]
        for branch, probability in values
    ])
    result = build_branch_priority(ranking, _case(), top_k=1)
    assert result.iloc[0]["branch_id"] == 1
    assert result.iloc[0]["from_bus"] == 1
    assert result.iloc[0]["to_bus"] == 2
    assert result.iloc[0]["top10_configuration_fraction"] == 1.0


def test_representative_contingencies_evaluate_topology_impact():
    priority = pd.DataFrame([
        {"branch_id": 1, "from_bus": 1, "to_bus": 2, "mean_peak_failure_probability": .2},
        {"branch_id": 2, "from_bus": 2, "to_bus": 3, "mean_peak_failure_probability": .1},
    ])
    result = build_representative_contingencies(
        priority, _case(), top_k=2, max_failed_branches=2
    )
    assert len(result) == 3
    two_fault = result[result["failed_branch_count"] == 2].iloc[0]
    assert two_fault["deenergized_bus_count"] == 2
    assert two_fault["connected_component_count"] == 3
    assert bool(two_fault["topology_only"])
    assert not bool(two_fault["electrical_power_flow_validated"])


def test_storm_ranking_aggregates_across_parameter_configurations():
    events = pd.DataFrame([
        {"wind_adjustment_knots": 0, "rmw_km": 20, "pole_spacing_m": 40,
         "storm_instance_id": "A", "event_timestamp_utc": "2020-01-01",
         "network_peak_wind_ms": 30, "expected_failed_branch_count": .5,
         "max_branch_failure_probability": .2},
        {"wind_adjustment_knots": 15, "rmw_km": 40, "pole_spacing_m": 60,
         "storm_instance_id": "A", "event_timestamp_utc": "2020-01-01",
         "network_peak_wind_ms": 35, "expected_failed_branch_count": .7,
         "max_branch_failure_probability": .3},
        {"wind_adjustment_knots": 0, "rmw_km": 20, "pole_spacing_m": 40,
         "storm_instance_id": "B", "event_timestamp_utc": "2020-02-01",
         "network_peak_wind_ms": 25, "expected_failed_branch_count": .2,
         "max_branch_failure_probability": .1},
    ])
    result = rank_storm_events(events)
    assert result.iloc[0]["storm_instance_id"] == "A"
    assert result.iloc[0]["configuration_count"] == 2
    assert result.iloc[0]["maximum_expected_failed_branches"] == .7
