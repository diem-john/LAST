import pytest

from scripts.run_phase8_robustness_benchmark import build_synthetic_candidates
from grid.restoration_optimization import build_restoration_qubo, solve_classical_exact


def test_synthetic_scaling_candidates_are_deterministic_and_unique():
    first = build_synthetic_candidates(8)
    second = build_synthetic_candidates(8)

    assert first.equals(second)
    assert len(first) == 8
    assert first["candidate_tie_branch_id"].is_unique
    assert (first["restored_load_kw"] > 0).all()


def test_synthetic_scaling_qubo_has_exactly_requested_qubit_count():
    candidates = build_synthetic_candidates(6)
    qubo = build_restoration_qubo(candidates)

    assert qubo["variable_count"] == 6
    assert qubo["penalty"] > sum(qubo["benefits_kw"])
    result = solve_classical_exact(qubo)
    assert result["feasible"]
    assert len(result["bitstring"]) == 6
    assert sum(int(bit) for bit in result["bitstring"]) <= 1


def test_synthetic_candidate_builder_rejects_zero_variables():
    with pytest.raises(ValueError, match="at least 1"):
        build_synthetic_candidates(0)
