"""Exact enumeration baseline for the initial LAST-Q tie-restoration QUBO."""
from __future__ import annotations

from itertools import product

from grid.reconfiguration import evaluate_reconfiguration
from quantum.optimization.qubo_formulation import QUBO


def solve_qubo_exact(qubo: QUBO) -> dict:
    """Exhaustively minimize a small QUBO; suitable as a reference baseline."""
    n = len(qubo.variables)
    if n > 24:
        raise ValueError(
            "Exact enumeration is restricted to <=24 variables; "
            "use a scalable classical solver for larger instances"
        )

    best_energy = float("inf")
    best_bits = None
    all_minimizers = []
    for bits in product((0, 1), repeat=n):
        energy = qubo.energy(bits)
        if energy < best_energy - 1e-10:
            best_energy = energy
            best_bits = bits
            all_minimizers = [bits]
        elif abs(energy - best_energy) <= 1e-10:
            all_minimizers.append(bits)

    return {
        "solver": "exact_binary_enumeration",
        "variable_count": n,
        "states_evaluated": 2 ** n,
        "best_energy": best_energy,
        "best_bits": list(best_bits),
        "all_minimizing_bitstrings": [list(bits) for bits in all_minimizers],
        "minimizer_count": len(all_minimizers),
        "selected_branch_ids": [
            qubo.branch_ids[i] for i, bit in enumerate(best_bits) if bit
        ],
    }


def run_bus6_classical_baseline(case: dict, qubo: QUBO, faulted_buses=(6,)) -> dict:
    """Solve the QUBO and independently validate its selected tie topology."""
    solution = solve_qubo_exact(qubo)
    topology = evaluate_reconfiguration(
        case, faulted_buses, solution["selected_branch_ids"]
    )
    feasible_states = 0
    for bits in product((0, 1), repeat=len(qubo.variables)):
        selected = [
            qubo.branch_ids[i] for i, bit in enumerate(bits) if bit
        ]
        result = evaluate_reconfiguration(case, faulted_buses, selected)
        if result["feasible_topology"]:
            feasible_states += 1

    return {
        "experiment": "LAST-Q Bus 6 flood-contingency topology baseline",
        "qubo": qubo.to_dict(),
        "solution": solution,
        "topology_validation": topology,
        "topology_feasible_state_count": feasible_states,
        "topology_validation_passed": topology["feasible_topology"],
        "electrical_power_flow_validated": False,
        "interpretation": (
            "This is a topology-only reference result. It does not establish "
            "voltage, thermal, protection, BESS, or AC power-flow feasibility."
        ),
    }
