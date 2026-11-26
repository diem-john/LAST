from pathlib import Path

from grid.reconfiguration import (
    enumerate_tie_configurations,
    evaluate_reconfiguration,
    load_case,
)
from quantum.optimization.qubo_formulation import build_tie_restoration_qubo
from quantum.optimization.classical_baseline import (
    run_bus6_classical_baseline,
    solve_qubo_exact,
)

ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = ROOT / "data" / "electrical" / "ieee33bw_reference.json"


def test_bus6_fault_creates_three_components_and_opens_all_incident_branches():
    case = load_case(CASE_PATH)
    active, surviving, components = __import__(
        "grid.reconfiguration", fromlist=["build_post_contingency_network"]
    ).build_post_contingency_network(case, (6,))

    assert 6 not in active
    assert len(components) == 3
    assert {5, 6, 25}.isdisjoint(
        {int(branch["branch_id"]) for branch in surviving}
    )


def test_five_tie_enumeration_finds_five_radial_restoration_states():
    case = load_case(CASE_PATH)
    states = enumerate_tie_configurations(case, (6,))

    assert len(states) == 2 ** 5
    feasible = [row for row in states if row["feasible_topology"]]
    assert len(feasible) == 5
    assert all(row["connected"] and row["radial"] for row in feasible)
    assert all(34 not in row["selected_tie_branch_ids"] for row in feasible)
    assert all(
        not ({33, 35} <= set(row["selected_tie_branch_ids"]))
        for row in feasible
    )


def test_q ubo_has_five_variables_and_zero_energy_for_feasible_states():
    case = load_case(CASE_PATH)
    qubo = build_tie_restoration_qubo(case, faulted_buses=(6,))

    assert len(qubo.variables) == 5
    assert qubo.branch_ids == (33, 34, 35, 36, 37)
    for row in enumerate_tie_configurations(case, (6,)):
        bits = row["decision_bits"]
        energy = qubo.energy(bits)
        if row["feasible_topology"]:
            assert energy == 0.0
        else:
            assert energy > 0.0


def test_exact_classical_qubo_baseline_returns_topologically_feasible_solution():
    case = load_case(CASE_PATH)
    qubo = build_tie_restoration_qubo(case, faulted_buses=(6,))
    result = run_bus6_classical_baseline(case, qubo, faulted_buses=(6,))

    assert result["solution"]["states_evaluated"] == 32
    assert result["solution"]["minimizer_count"] == 5
    assert result["topology_validation_passed"]
    assert not result["electrical_power_flow_validated"]


def test_invalid_tie_selection_is_rejected():
    case = load_case(CASE_PATH)
    try:
        evaluate_reconfiguration(case, (6,), (999,))
    except ValueError as exc:
        assert "Unknown or non-tie" in str(exc)
    else:
        raise AssertionError("Expected unknown tie branch to be rejected")
