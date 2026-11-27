import itertools

import pandas as pd

from grid.restoration_optimization import (
    build_restoration_qubo,
    evaluate_qubo,
    is_feasible_at_most_one,
    qubo_to_ising,
    solve_classical_exact,
)


def _candidates():
    return pd.DataFrame([
        {"restoration_candidate_id": "A-TIE-34", "candidate_tie_branch_id": 34, "restored_load_kw": 120.0},
        {"restoration_candidate_id": "A-TIE-35", "candidate_tie_branch_id": 35, "restored_load_kw": 250.0},
        {"restoration_candidate_id": "A-TIE-36", "candidate_tie_branch_id": 36, "restored_load_kw": 80.0},
    ])


def test_qubo_penalty_enforces_at_most_one_action_and_exact_solver_picks_best():
    qubo = build_restoration_qubo(_candidates())
    assert qubo["penalty"] > sum(qubo["benefits_kw"])
    result = solve_classical_exact(qubo)
    assert result["selected_tie_branch_ids"] == [35]
    assert result["restored_load_kw"] == 250.0
    assert result["feasible"]
    assert result["enumerated_bitstrings"] == 8


def test_all_zero_bitstring_is_valid_no_action():
    qubo = build_restoration_qubo(_candidates())
    bits = (0, 0, 0)
    assert is_feasible_at_most_one(bits)
    assert evaluate_qubo(bits, qubo) == 0.0


def test_multi_action_bitstrings_are_penalized_above_no_action():
    qubo = build_restoration_qubo(_candidates())
    for bits in itertools.product((0, 1), repeat=3):
        if sum(bits) > 1:
            assert evaluate_qubo(bits, qubo) > 0.0


def test_qubo_to_ising_preserves_energy_for_every_basis_state():
    qubo = build_restoration_qubo(_candidates())
    ising = qubo_to_ising(qubo)
    for bits in itertools.product((0, 1), repeat=3):
        z = [1 - 2 * bit for bit in bits]
        energy = ising["constant"]
        energy += sum(h * value for h, value in zip(ising["linear_z"], z))
        energy += sum(
            coefficient * z[i] * z[j]
            for (i, j), coefficient in ising["quadratic_zz"].items()
        )
        assert abs(energy - evaluate_qubo(bits, qubo)) < 1e-9


def test_empty_candidate_set_returns_no_action():
    empty = pd.DataFrame(columns=[
        "restoration_candidate_id", "candidate_tie_branch_id", "restored_load_kw"
    ])
    qubo = build_restoration_qubo(empty)
    result = solve_classical_exact(qubo)
    assert result["bitstring"] == ""
    assert result["selected_tie_branch_ids"] == []
    assert result["restored_load_kw"] == 0.0
