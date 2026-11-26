"""QAOA optimization loop and QUBO-to-Ising conversion for LAST-Q."""
from __future__ import annotations

import math
import random
import time
from typing import Mapping, Sequence

from quantum.circuits.qaoa_circuit import (
    build_qaoa_sampling_kernel,
    build_qaoa_state_kernel,
)
from quantum.optimization.qubo_formulation import QUBO


def qubo_to_ising(qubo: QUBO) -> dict:
    """Convert E(x) to constant + sum(h_i Z_i) + sum(J_ij Z_i Z_j)."""
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


def build_ising_spin_operator(ising: dict):
    """Build the full Ising observable, including its identity offset."""
    try:
        from cudaq import spin
    except ImportError as exc:
        raise ImportError("CUDA-Q is required to build the Ising observable.") from exc
    n = int(ising["qubit_count"])
    if n < 1:
        raise ValueError("The Ising observable requires at least one qubit")
    operator = float(ising["constant"]) * spin.i(0)
    for i, coefficient in enumerate(ising["linear"]):
        if coefficient != 0.0:
            operator += float(coefficient) * spin.z(i)
    for i in range(n):
        for j in range(i + 1, n):
            coefficient = float(ising["quadratic"][i][j])
            if coefficient != 0.0:
                operator += coefficient * spin.z(i) * spin.z(j)
    return operator


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


def select_best_start_index(candidates: Sequence[Mapping]) -> int:
    """Return the zero-based candidate index with the lowest exact expectation."""
    if not candidates:
        raise ValueError("At least one optimized QAOA start is required")
    return min(
        range(len(candidates)),
        key=lambda index: float(candidates[index]["exact_final_expectation"]),
    )


def optimize_qaoa(
    qubo: QUBO,
    layers: int = 1,
    shots: int = 2048,
    max_iterations: int = 60,
    seed: int = 7,
    target: str | None = None,
    starts: int = 1,
) -> dict:
    """Optimize exact Ising expectation from multiple starts, then sample the best.

    max_iterations is the COBYLA maxiter option applied independently to each
    start. In the current SciPy implementation this acts as an objective-
    evaluation limit.
    """
    if layers < 1:
        raise ValueError("QAOA layer count must be at least 1")
    if shots < 1:
        raise ValueError("Shot count must be positive")
    if max_iterations < 1:
        raise ValueError("Maximum optimizer iterations must be positive")
    if starts < 1:
        raise ValueError("QAOA start count must be at least 1")

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

    cudaq.set_random_seed(int(seed))
    ising = qubo_to_ising(qubo)
    observable = build_ising_spin_operator(ising)
    state_kernel = build_qaoa_state_kernel()
    sampling_kernel = build_qaoa_sampling_kernel()
    n = len(qubo.variables)

    candidate_results = []
    total_optimization_seconds = 0.0
    total_candidate_evaluation_seconds = 0.0
    total_objective_evaluations = 0

    for start_index in range(starts):
        # Preserve the historical initialization for the first start.
        # Subsequent starts use independent, reproducible initialization seeds.
        start_seed = int(seed) + start_index
        rng = random.Random(start_seed)
        initial = [
            rng.uniform(0.0, 2.0 * math.pi) for _ in range(2 * layers)
        ]

        def kernel_arguments(parameters):
            gammas = [float(value) for value in parameters[:layers]]
            betas = [float(value) for value in parameters[layers:]]
            return (n, gammas, betas, ising["linear"], ising["quadratic_flat"])

        evaluation_count = 0

        def objective(parameters):
            nonlocal evaluation_count
            result = cudaq.observe(
                state_kernel, observable, *kernel_arguments(parameters)
            )
            evaluation_count += 1
            value = result.expectation()
            return float(value.real if hasattr(value, "real") else value)

        optimization_start = time.perf_counter()
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
        optimization_seconds = time.perf_counter() - optimization_start
        total_optimization_seconds += optimization_seconds
        total_objective_evaluations += evaluation_count

        optimized_parameters = [float(value) for value in optimization.x]
        candidate_arguments = kernel_arguments(optimized_parameters)
        candidate_evaluation_start = time.perf_counter()
        candidate_exact_result = cudaq.observe(
            state_kernel, observable, *candidate_arguments
        )
        candidate_exact_value = candidate_exact_result.expectation()
        candidate_exact_expectation = float(
            candidate_exact_value.real if hasattr(candidate_exact_value, "real")
            else candidate_exact_value
        )
        candidate_evaluation_seconds = (
            time.perf_counter() - candidate_evaluation_start
        )
        total_candidate_evaluation_seconds += candidate_evaluation_seconds

        candidate_results.append({
            "start_index": start_index + 1,
            "initialization_seed": start_seed,
            "initial_parameters": initial,
            "optimized_parameters": optimized_parameters,
            "optimized_gammas": optimized_parameters[:layers],
            "optimized_betas": optimized_parameters[layers:],
            "exact_final_expectation": candidate_exact_expectation,
            "optimizer_success": bool(optimization.success),
            "optimizer_status": (
                int(optimization.status) if hasattr(optimization, "status") else None
            ),
            "optimizer_message": str(optimization.message),
            "optimizer_iterations": (
                int(optimization.nit) if hasattr(optimization, "nit") else None
            ),
            "optimizer_nfev": (
                int(optimization.nfev) if hasattr(optimization, "nfev") else None
            ),
            "objective_evaluations": evaluation_count,
            "optimizer_final_objective": (
                float(optimization.fun) if hasattr(optimization, "fun") else None
            ),
            "optimization_runtime_seconds": optimization_seconds,
            "exact_candidate_evaluation_seconds": candidate_evaluation_seconds,
        })

    selected_index = select_best_start_index(candidate_results)
    selected = candidate_results[selected_index]
    final_arguments = (
        n,
        selected["optimized_gammas"],
        selected["optimized_betas"],
        ising["linear"],
        ising["quadratic_flat"],
    )

    exact_final_start = time.perf_counter()
    exact_final_result = cudaq.observe(state_kernel, observable, *final_arguments)
    exact_final_value = exact_final_result.expectation()
    exact_final_expectation = float(
        exact_final_value.real if hasattr(exact_final_value, "real")
        else exact_final_value
    )
    exact_final_seconds = time.perf_counter() - exact_final_start

    sampling_start = time.perf_counter()
    sampled_result = cudaq.sample(
        sampling_kernel, *final_arguments, shots_count=shots
    )
    final_counts = {str(key): int(sampled_result[key]) for key in sampled_result}
    final_summary = evaluate_sample_counts(qubo, final_counts)
    final_sampling_seconds = time.perf_counter() - sampling_start
    active_target = cudaq.get_target().name if hasattr(cudaq, "get_target") else target

    return {
        "algorithm": "QAOA",
        "backend": "NVIDIA CUDA-Q",
        "optimization_objective": "analytic_ising_expectation",
        "final_evaluation": "finite_shot_computational_basis_sampling",
        "target": active_target,
        "qubit_count": n,
        "qaoa_layers": layers,
        "shots_per_final_evaluation": shots,
        "optimizer": "COBYLA",
        "optimizer_success": selected["optimizer_success"],
        "optimizer_status": selected["optimizer_status"],
        "optimizer_message": selected["optimizer_message"],
        "optimizer_iterations": selected["optimizer_iterations"],
        "optimizer_nfev": selected["optimizer_nfev"],
        "objective_evaluations": total_objective_evaluations,
        "selected_start_objective_evaluations": selected["objective_evaluations"],
        "optimizer_final_objective": selected["optimizer_final_objective"],
        "exact_final_expectation": exact_final_expectation,
        "optimizer_max_constraint_violation": None,
        "optimizer_result_keys": [],
        "optimizer_max_function_evaluations_per_start": int(max_iterations),
        "optimization_runtime_seconds": total_optimization_seconds,
        "exact_candidate_evaluation_runtime_seconds": total_candidate_evaluation_seconds,
        "exact_final_evaluation_seconds": exact_final_seconds,
        "final_sampling_runtime_seconds": final_sampling_seconds,
        "cudaq_random_seed": int(seed),
        "initial_parameters": selected["initial_parameters"],
        "optimized_gammas": selected["optimized_gammas"],
        "optimized_betas": selected["optimized_betas"],
        "multi_start_count": starts,
        "selected_start_index": selected["start_index"],
        "all_starts_successful": all(
            candidate["optimizer_success"] for candidate in candidate_results
        ),
        "multi_start_results": candidate_results,
        "final_sample": final_summary,
        "ising_hamiltonian": ising,
        "seed": seed,
    }
