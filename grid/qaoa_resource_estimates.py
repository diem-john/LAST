"""Transparent source-level gate-resource estimates for Phase 8 QAOA kernels.

These are primitive gate-call counts and conservative source-order depth bounds.
They are not backend-transpiled depth, hardware-native gate counts, or timings.
"""
from __future__ import annotations


def _validate_nonnegative(name: str, value: int) -> int:
    value = int(value)
    if value < 0:
        raise ValueError(f"{name} must be nonnegative")
    return value


def _validate_layers(layers: int) -> int:
    layers = int(layers)
    if layers < 1:
        raise ValueError("layers must be positive")
    return layers


def estimate_x_mixer_resources(
    variable_count: int, zz_edge_count: int, layers: int
) -> dict[str, int | str]:
    """Estimate resources for the Phase 8 kernel as currently written.

    The kernel applies n initial H gates. Each layer applies n RZ gates,
    then one CNOT-RZ-CNOT block per listed ZZ edge, then n RX gates.
    """
    n = _validate_nonnegative("variable_count", variable_count)
    edges = _validate_nonnegative("zz_edge_count", zz_edge_count)
    p = _validate_layers(layers)
    single_qubit = n + p * (2 * n + edges)
    two_qubit = 2 * edges * p
    return {
        "qubit_count": n,
        "primitive_gate_count": single_qubit + two_qubit,
        "single_qubit_gate_count": single_qubit,
        "two_qubit_gate_count": two_qubit,
        "source_order_depth_upper_bound": (1 if n else 0) + p * (2 + 3 * edges),
        "resource_estimate_basis": "source_kernel_primitive_gate_calls",
    }


def estimate_xy_mixer_resources(action_count: int, layers: int) -> dict[str, int | str]:
    """Estimate resources for Phase 8.1's complete-graph pairwise XY kernel.

    There are action_count + 1 choices (including no-action), with
    C(choice_count, 2) edges. Each edge applies 18 primitive gate calls,
    including four CNOTs and two RZ rotations.
    """
    n = _validate_nonnegative("action_count", action_count)
    p = _validate_layers(layers)
    qubits = n + 1
    edges = qubits * (qubits - 1) // 2
    initial_gates = 1  # X on the no-action reference qubit
    cost_gates = n * p  # one RZ per action qubit and layer
    mixer_gates = 18 * edges * p
    two_qubit = 4 * edges * p
    single_qubit = initial_gates + cost_gates + (mixer_gates - two_qubit)
    return {
        "qubit_count": qubits,
        "mixer_edge_count": edges,
        "primitive_gate_count": initial_gates + cost_gates + mixer_gates,
        "single_qubit_gate_count": single_qubit,
        "two_qubit_gate_count": two_qubit,
        "source_order_depth_upper_bound": initial_gates + p * (1 + 18 * edges),
        "resource_estimate_basis": "source_kernel_primitive_gate_calls",
    }
