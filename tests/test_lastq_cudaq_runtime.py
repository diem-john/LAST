from pathlib import Path

import pytest

cudaq = pytest.importorskip("cudaq")

from grid.reconfiguration import load_case
from quantum.circuits.qaoa_circuit import build_qaoa_sampling_kernel
from quantum.optimization.qubo_formulation import build_tie_restoration_qubo
from quantum.optimization.qaoa_optimizer import qubo_to_ising

ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = ROOT / "data" / "electrical" / "ieee33bw_reference.json"


def test_cudaq_qaoa_kernel_executes_and_returns_five_bit_samples():
    previous_target = cudaq.get_target().name
    try:
        cudaq.set_target("qpp-cpu")
        case = load_case(CASE_PATH)
        qubo = build_tie_restoration_qubo(case, faulted_buses=(6,))
        ising = qubo_to_ising(qubo)
        kernel = build_qaoa_sampling_kernel()

        result = cudaq.sample(
            kernel,
            len(qubo.variables),
            [0.35],
            [0.22],
            ising["linear"],
            ising["quadratic_flat"],
            shots_count=128,
        )

        counts = {str(key): int(result[key]) for key in result}
        assert sum(counts.values()) == 128
        assert counts
        assert all(len(bitstring) == len(qubo.variables) for bitstring in counts)
        assert all(set(bitstring) <= {"0", "1"} for bitstring in counts)
    finally:
        cudaq.set_target(previous_target)
