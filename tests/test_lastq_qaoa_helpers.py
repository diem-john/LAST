from pathlib import Path

import pytest

from grid.reconfiguration import load_case
from quantum.optimization.qubo_formulation import build_tie_restoration_qubo
from quantum.optimization.qaoa_optimizer import (
    decode_bitstring,
    evaluate_sample_counts,
    qubo_to_ising,
    select_best_start_index,
)

ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = ROOT / "data" / "electrical" / "ieee33bw_reference.json"


def test_qubo_to_ising_preserves_energy_for_every_binary_state():
    case = load_case(CASE_PATH)
    qubo = build_tie_restoration_qubo(case, faulted_buses=(6,))
    ising = qubo_to_ising(qubo)
    n = len(qubo.variables)
    for mask in range(2 ** n):
        bits = tuple((mask >> i) & 1 for i in range(n))
        z = tuple(1 - 2 * bit for bit in bits)
        energy = ising["constant"]
        energy += sum(ising["linear"][i] * z[i] for i in range(n))
        energy += sum(
            ising["quadratic"][i][j] * z[i] * z[j]
            for i in range(n) for j in range(i + 1, n)
        )
        assert abs(energy - qubo.energy(bits)) < 1e-9


def test_cudaq_bitstring_decoding_uses_qubit_allocation_order():
    assert decode_bitstring("10010", 5) == (1, 0, 0, 1, 0)


def test_sample_count_summary_calculates_expected_energy_and_optimum():
    case = load_case(CASE_PATH)
    qubo = build_tie_restoration_qubo(case, faulted_buses=(6,))
    counts = {
        "10100": 40,
        "10010": 30,
        "00000": 30,
    }
    summary = evaluate_sample_counts(qubo, counts)
    assert summary["total_shots"] == 100
    assert summary["best_sampled_energy"] == 0.0
    assert summary["best_sampled_bitstring"] == "10010"
    assert summary["expected_qubo_energy"] > 0.0


def test_multistart_selection_uses_lowest_exact_expectation():
    candidates = [
        {"exact_final_expectation": 12.5},
        {"exact_final_expectation": 8.25},
        {"exact_final_expectation": 10.0},
    ]
    assert select_best_start_index(candidates) == 1


def test_multistart_selection_keeps_first_candidate_on_exact_tie():
    candidates = [
        {"exact_final_expectation": 8.25},
        {"exact_final_expectation": 8.25},
        {"exact_final_expectation": 9.0},
    ]
    assert select_best_start_index(candidates) == 0


def test_multistart_selection_rejects_empty_candidate_list():
    with pytest.raises(ValueError, match="At least one"):
        select_best_start_index([])
