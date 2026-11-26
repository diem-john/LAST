from pathlib import Path

import pytest

cudaq = pytest.importorskip("cudaq")

from grid.reconfiguration import load_case
from quantum.circuits.qaoa_circuit import (
    build_qaoa_sampling_kernel,
    build_qaoa_state_kernel,
)
from quantum.optimization.qubo_formulation import build_tie_restoration_qubo
from quantum.optimization.qaoa_optimizer import (
    build_ising_spin_operator,
    evaluate_sample_counts,
    qubo_to_ising,
)

ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = ROOT / "data" / "electrical" / "ieee33bw_reference.json"


def _case_qubo():
    case = load_case(CASE_PATH)
    return case, build_tie_restoration_qubo(case, faulted_buses=(6,))


def test_cudaq_qaoa_sampling_kernel_executes_and_returns_five_bit_samples():
    previous_target = cudaq.get_target().name
    try:
        cudaq.set_target("qpp-cpu")
        _, qubo = _case_qubo()
        ising = qubo_to_ising(qubo)
        result = cudaq.sample(
            build_qaoa_sampling_kernel(),
            len(qubo.variables), [0.35], [0.22],
            ising["linear"], ising["quadratic_flat"], shots_count=128,
        )
        counts = {str(key): int(result[key]) for key in result}
        assert sum(counts.values()) == 128
        assert counts
        assert all(len(bitstring) == len(qubo.variables) for bitstring in counts)
        assert all(set(bitstring) <= {"0", "1"} for bitstring in counts)
    finally:
        cudaq.set_target(previous_target)


def test_exact_observe_matches_large_shot_qubo_energy_estimate():
    previous_target = cudaq.get_target().name
    try:
        cudaq.set_target("qpp-cpu")
        _, qubo = _case_qubo()
        ising = qubo_to_ising(qubo)
        observable = build_ising_spin_operator(ising)
        args = (
            len(qubo.variables), [0.35], [0.22],
            ising["linear"], ising["quadratic_flat"],
        )

        exact = cudaq.observe(
            build_qaoa_state_kernel(), observable, *args
        ).expectation()
        exact = float(exact.real if hasattr(exact, "real") else exact)

        sampled = cudaq.sample(
            build_qaoa_sampling_kernel(), *args, shots_count=16384
        )
        counts = {str(key): int(sampled[key]) for key in sampled}
        sampled_energy = evaluate_sample_counts(qubo, counts)[
            "expected_qubo_energy"
        ]
        assert abs(exact - sampled_energy) < 1.0
    finally:
        cudaq.set_target(previous_target)
