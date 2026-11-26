"""QAOA optimization loop and QUBO-to-Ising conversion for LAST-Q."""
from __future__ import annotations

import math
import random
from typing import Mapping

from quantum.circuits.qaoa_circuit import build_qaoa_sampling_kernel
from quantum.optimization.qubo_formulation import QUBO


def qubo_to_ising(qubo: QUBO) -> dict:
    """Convert E(x) to constant + sum(h_i Z_i) + sum(J_ij Z_i Z_j).

    Uses x_i = (1 - Z_i) / 2 and the QUBO convention documented by QUBO.
    """
    n = len(qubo.variables)
    h = [-0.5 * qubo.linear[i] for i in range(n)]
    j_matrix = [[0.0 for _ in range(n)] for _ in range(n)]
    constant = float(qubo.offset)

    for i in range(n):
        constant += 0.5 * qubo.linear[i]
        for j in range(i + 1, n):
            coefficient = float(qubo.quadratic[i][j])
            if coefficient == 0.0:
                continue
            constant += 0.25 * coefficient
            h[i] -= 0.25 * coefficient
            h[j] -= 0.25 * coefficient
            j_matrix[i][j] = 0.25 * coefficient

    return {
        "constant": float(constant),
        "linear": [float(value) for value in h],
        "quadratic": j_matrix,
        "quadratic_flat": [
            float(j_matrix[i][j]) for i in range(n) for j in range(n)
        ],
        "qubit_count": n,
    }


def decode_bitstring(bitstring: str, qubit_count: int) -> tuple[int, ...]:
    """Decode CUDA-Q's q[0]-leftmost global measurement bitstring."""
    normalized = str(bitstring).replace(" ", "")
    if len(normalized) != qubit_count or any(bit not in "01" for bit in normalized):
        raise ValueError(
            f"Expected a {qubit_count}-bit binary measurement, received {bitstring!r}"
        )
    return tuple(int(bit) for bit in normalized)


def evaluate_sample_counts(qubo: QUBO, counts: Mapping[str, int]) -> dict:
    """Compute sampled QUBO energies and distribution statistics."""
    n = len(qubo.variables)
    total_shots = sum(int(count) for count in counts.values())
    if total_shots <= 0:
        raise ValueError("Sample counts must contain at least one shot")

    distribution = []
    expected_energy = 0.0
    for bitstring, raw_count in counts.items():
        count = int(raw_count)
        if count < 0:
            raise ValueError("Sample counts cannot be negative")
        bits = decode_bitstring(bitstring, n)
        energy = qubo.energy(bits)
        probability = count / total_shots
        expected_energy += probability * energy
        distribution.append({
            "bitstring": str(bitstring),
            "bits": list(bits),
            "count": count,
            "probability": probability,
            "qubo_energy": energy,
            "selected_branch_ids": [
                qubo.branch_ids[i] for i, bit in enumerate(bits) if bit
            ],
        })

    distribution.sort(key=lambda row: (row["qubo_energy"], -row["count"], row["bitstring"]))
    best = distribution[0]
    return {
        "total_shots": total_shots,
        "expected_qubo_energy": float(expected_energy),
        "best_sampled_energy": float(best["qubo_energy"]),
        "best_sampled_bitstring": best["bitstring"],
        "best_sampled_bits": best["bits"],
        "best_sampled_branch_ids": best["selected_branch_ids"],
        "distribution": distribution,
    }


def optimize_qaoa(
    qubo: QUBO,
    layers: int = 1,
    shots: int = 2048,
    max_iterations: int = 60,
    seed: int = 7,
    target: str | None = None,
) -> dict:
    """Run QAOA with a SciPy COBYLA outer loop and CUDA-Q circuit sampling."""
    if layers < 1:
        raise ValueError("QAOA layer count must be at least 1")
    if shots < 1:
        raise ValueError("Shot count must be positive")
    if max_iterations < 1:
        raise ValueError("Maximum optimizer iterations must be positive")

    try:
        import cudaq
    except ImportError as exc:
        raise ImportError(
            "CUDA-Q is not installed in this Python environment. "
            "Use the CUDA-Q environment before running LAST-Q QAOA."
        ) from exc

    try:
        from scipy.optimize import minimize
    except ImportError as exc:
        raise ImportError(
            "SciPy is required for the classical QAOA parameter optimizer."
        ) from exc

    if target:
        if hasattr(cudaq, "has_target") and not cudaq.has_target(target):
            raise RuntimeError(
                f"CUDA-Q target {target!r} is not available on this machine. "
                "Check the installed CUDA-Q backend and GPU runtime."
            )
        cudaq.set_target(target)

    ising = qubo_to_ising(qubo)
    kernel = build_qaoa_sampling_kernel()
    n = len(qubo.variables)
    rng = random.Random(seed)
    initial = [rng.uniform(0.0, 2.0 * math.pi) for _ in range(2 * layers)]

    def sample_parameters(parameters):
        gammas = [float(value) for value in parameters[:layers]]
        betas = [float(value) for value in parameters[layers:]]
        result = cudaq.sample(
            kernel,
            n,
            gammas,
            betas,
            ising["linear"],
            ising["quadratic_flat"],
            shots_count=shots,
        )
        return {str(key): int(result[key]) for key in result}

    evaluation_count = 0

    def objective(parameters):
        nonlocal evaluation_count
        counts = sample_parameters(parameters)
        summary = evaluate_sample_counts(qubo, counts)
        evaluation_count += 1
        return summary["expected_qubo_energy"]

    optimization = minimize(
        objective,
        initial,
        method="COBYLA",
        options={
            "maxiter": int(max_iterations),
            "rhobeg": 0.5,
            "tol": 1e-3,
            "catol": 1e-4,
        },
    )

    optimized_parameters = [float(value) for value in optimization.x]
    final_counts = sample_parameters(optimized_parameters)
    final_summary = evaluate_sample_counts(qubo, final_counts)
    active_target = cudaq.get_target().name if hasattr(cudaq, "get_target") else target

    return {
        "algorithm": "QAOA",
        "backend": "NVIDIA CUDA-Q",
        "target": active_target,
        "qubit_count": n,
        "qaoa_layers": layers,
        "shots_per_evaluation": shots,
        "optimizer": "COBYLA",
        "optimizer_success": bool(optimization.success),
        "optimizer_message": str(optimization.message),
        "optimizer_iterations": int(getattr(optimization, "nit", 0)),
        "objective_evaluations": evaluation_count,
        "initial_parameters": initial,
        "optimized_gammas": optimized_parameters[:layers],
        "optimized_betas": optimized_parameters[layers:],
        "final_sample": final_summary,
        "ising_hamiltonian": ising,
        "seed": seed,
    }
