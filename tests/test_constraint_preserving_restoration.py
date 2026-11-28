import itertools
import os

import pandas as pd
import pytest

from grid.constraint_preserving_restoration import (
    build_one_hot_problem,
    evaluate_one_hot_energy,
    is_one_hot,
    solve_one_hot_exact,
)


def _candidates():
    return pd.DataFrame([
        {"restoration_candidate_id": "TIE-34", "candidate_tie_branch_id": 34, "restored_load_kw": 120.0},
        {"restoration_candidate_id": "TIE-35", "candidate_tie_branch_id": 35, "restored_load_kw": 250.0},
        {"restoration_candidate_id": "TIE-36", "candidate_tie_branch_id": 36, "restored_load_kw": 80.0},
    ])


def test_one_hot_problem_includes_no_action_and_stable_candidate_order():
    problem = build_one_hot_problem(_candidates().iloc[[2, 0, 1]])
    assert problem["choice_count"] == 4
    assert problem["action_count"] == 3
    assert problem["benefits_kw"] == [0.0, 120.0, 250.0, 80.0]
    assert problem["initial_bitstring"] == "1000"
    assert problem["candidate_rows"]["candidate_tie_branch_id"].tolist() == [34, 35, 36]


def test_only_one_hot_bitstrings_are_feasible():
    problem = build_one_hot_problem(_candidates())
    feasible = [bits for bits in itertools.product((0, 1), repeat=4) if is_one_hot(bits)]
    assert len(feasible) == 4
    assert all(evaluate_one_hot_energy(bits, problem) <= 0.0 for bits in feasible)
    assert not is_one_hot((0, 0, 0, 0))
    assert not is_one_hot((1, 1, 0, 0))


def test_exact_one_hot_solver_matches_penalty_formulation_optimum():
    from grid.restoration_optimization import build_restoration_qubo, solve_classical_exact

    candidates = _candidates()
    one_hot = solve_one_hot_exact(build_one_hot_problem(candidates))
    penalty = solve_classical_exact(build_restoration_qubo(candidates))
    assert one_hot["selected_tie_branch_ids"] == [35]
    assert one_hot["restored_load_kw"] == penalty["restored_load_kw"] == 250.0
    # Index 0 is no-action; index 2 is Tie 35 after stable sorting by tie ID.
    assert one_hot["bitstring"] == "0010"


def test_no_action_wins_when_all_benefits_are_zero_or_negative():
    candidates = _candidates()
    candidates["restored_load_kw"] = [0.0, -5.0, 0.0]
    problem = build_one_hot_problem(candidates)
    result = solve_one_hot_exact(problem)
    assert result["choice_index"] == 0
    assert result["bitstring"] == "1000"
    assert result["restored_load_kw"] == 0.0


def test_invalid_nonfinite_benefit_is_rejected():
    candidates = _candidates()
    candidates.loc[0, "restored_load_kw"] = float("inf")
    with pytest.raises(ValueError, match="finite"):
        build_one_hot_problem(candidates)


def test_one_hot_energy_rejects_invalid_vectors():
    problem = build_one_hot_problem(_candidates())
    with pytest.raises(ValueError, match="one-hot"):
        evaluate_one_hot_energy((0, 0, 0, 0), problem)
    with pytest.raises(ValueError, match="one-hot"):
        evaluate_one_hot_energy((1, 1, 0, 0), problem)


@pytest.mark.skipif(
    os.environ.get("RUN_CUDAQ_INTEGRATION") != "1",
    reason="Set RUN_CUDAQ_INTEGRATION=1 to execute the CUDA-Q circuit integration test.",
)
def test_cudaq_xy_mixer_samples_remain_one_hot():
    pytest.importorskip("cudaq")
    from scripts.run_phase8_1_xy_mixer_benchmark import run_cudaq_xy_qaoa

    problem = build_one_hot_problem(_candidates())
    result = run_cudaq_xy_qaoa(
        problem, layers=1, shots=256, max_iterations=5, seed=42, target="qpp-cpu"
    )
    assert result["constraint_violations"] == 0
    assert result["feasible_shots"] == 256
    assert result["feasible_shot_fraction"] == 1.0
