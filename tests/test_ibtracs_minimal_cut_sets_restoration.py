import json

import pandas as pd

from scripts.run_ibtracs_minimal_cut_sets_restoration import (
    build_restoration_candidates,
    build_unique_outage_states,
    derive_minimal_bus_cut_sets,
)


def _case():
    return {
        "base": {"slack_bus": 1},
        "bus": [
            {"bus_id": 1, "p_kw": 0, "q_kvar": 0},
            {"bus_id": 2, "p_kw": 10, "q_kvar": 5},
            {"bus_id": 3, "p_kw": 20, "q_kvar": 10},
            {"bus_id": 4, "p_kw": 30, "q_kvar": 15},
        ],
        "branch": [
            {"branch_id": 1, "from_bus": 1, "to_bus": 2, "in_service": True, "status": "closed"},
            {"branch_id": 2, "from_bus": 2, "to_bus": 3, "in_service": True, "status": "closed"},
            {"branch_id": 3, "from_bus": 3, "to_bus": 4, "in_service": True, "status": "closed"},
            {"branch_id": 4, "from_bus": 1, "to_bus": 4, "in_service": False, "status": "normally_open_tie"},
        ],
    }


def _contingencies():
    return pd.DataFrame([
        {"contingency_id": "single-2", "failed_branch_ids": "[2]",
         "deenergized_bus_ids": "[3, 4]", "failed_branch_count": 1, "mean_branch_risk_sum": .2},
        {"contingency_id": "double-2-3", "failed_branch_ids": "[2, 3]",
         "deenergized_bus_ids": "[3, 4]", "failed_branch_count": 2, "mean_branch_risk_sum": .3},
        {"contingency_id": "single-3", "failed_branch_ids": "[3]",
         "deenergized_bus_ids": "[4]", "failed_branch_count": 1, "mean_branch_risk_sum": .1},
    ])


def test_minimal_cut_sets_are_minimal_per_isolated_bus():
    result = derive_minimal_bus_cut_sets(_contingencies())
    # Branch 2 alone isolates buses 3 and 4; adding branch 3 is redundant for both.
    pairs = { (tuple(json.loads(r.failed_branch_ids)), r.isolated_bus_id)
              for r in result.itertuples() }
    assert ((2,), 3) in pairs
    assert ((2,), 4) in pairs
    assert ((3,), 4) in pairs
    assert ((2, 3), 3) not in pairs
    assert ((2, 3), 4) not in pairs


def test_unique_outage_states_aggregate_equivalent_contingencies_and_load():
    result = build_unique_outage_states(_contingencies(), _case())
    same_state = result[result["deenergized_bus_ids"] == "[3, 4]"].iloc[0]
    assert same_state["equivalent_contingency_count"] == 2
    assert same_state["representative_contingency_id"] == "single-2"
    assert same_state["deenergized_load_kw"] == 50


def test_restoration_candidate_uses_tie_only_if_slack_reach_increases():
    states = build_unique_outage_states(_contingencies(), _case())
    result = build_restoration_candidates(states, _case())
    state = states[states["deenergized_bus_ids"] == "[3, 4]"].iloc[0]
    candidates = result[result["outage_state_id"] == state["outage_state_id"]]
    assert len(candidates) == 1
    candidate = candidates.iloc[0]
    assert candidate["candidate_tie_branch_id"] == 4
    assert candidate["restored_bus_count"] == 2
    assert candidate["restored_load_kw"] == 50
    assert not bool(candidate["power_flow_validated"])
