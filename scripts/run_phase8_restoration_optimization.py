"""Run Phase 8 classical exact and optional CUDA-Q QAOA restoration optimization."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd

from grid.restoration_optimization import (
    build_restoration_qubo,
    evaluate_qubo,
    is_feasible_at_most_one,
    prepare_phase8_scenarios,
    qubo_to_ising,
    solve_classical_exact,
)

ROOT = Path(__file__).resolve().parents[1]


def run_cudaq_qaoa(
    qubo: dict,
    *,
    layers: int = 1,
    shots: int = 2048,
    max_iterations: int = 100,
    seed: int = 42,
    target: str | None = None,
) -> dict:
    """Optimize the QUBO with CUDA-Q QAOA and return the best feasible sample."""
    import numpy as np
    import cudaq

    n = int(qubo["variable_count"])
    if n == 0:
        return {
            "status": "no_candidate_actions", "bitstring": "",
            "selected_tie_branch_ids": [], "qubo_energy": 0.0,
            "restored_load_kw": 0.0, "feasible": True,
            "feasible_shots": 0, "total_shots": 0,
            "runtime_seconds": 0.0, "optimal_expectation": None,
            "optimal_parameters": [],
        }
    if layers < 1 or shots < 1 or max_iterations < 1:
        raise ValueError("layers, shots, and max_iterations must be positive")
    if target:
        cudaq.set_target(target)
    cudaq.set_random_seed(seed)

    ising = qubo_to_ising(qubo)
    linear_z = [float(value) for value in ising["linear_z"]]
    pair_terms = list(ising["quadratic_zz"].items())
    pair_i = [int(pair[0][0]) for pair in pair_terms]
    pair_j = [int(pair[0][1]) for pair in pair_terms]
    pair_coefficients = [float(pair[1]) for pair in pair_terms]

    hamiltonian = None
    for index, coefficient in enumerate(linear_z):
        if abs(coefficient) < 1e-15:
            continue
        term = coefficient * cudaq.spin.z(index)
        hamiltonian = term if hamiltonian is None else hamiltonian + term
    for (i, j), coefficient in ising["quadratic_zz"].items():
        if abs(coefficient) < 1e-15:
            continue
        term = coefficient * cudaq.spin.z(i) * cudaq.spin.z(j)
        hamiltonian = term if hamiltonian is None else hamiltonian + term
    if hamiltonian is None:
        raise ValueError("QUBO produced an empty Ising Hamiltonian")

    @cudaq.kernel
    def qaoa_kernel(
        qubit_count: int,
        layer_count: int,
        z_linear: list[float],
        edge_source: list[int],
        edge_target: list[int],
        zz_coefficients: list[float],
        gammas: list[float],
        betas: list[float],
    ):
        qubits = cudaq.qvector(qubit_count)
        h(qubits)
        for layer in range(layer_count):
            for index in range(qubit_count):
                rz(2.0 * gammas[layer] * z_linear[index], qubits[index])
            for edge in range(len(edge_source)):
                control = edge_source[edge]
                target_qubit = edge_target[edge]
                x.ctrl(qubits[control], qubits[target_qubit])
                rz(2.0 * gammas[layer] * zz_coefficients[edge], qubits[target_qubit])
                x.ctrl(qubits[control], qubits[target_qubit])
            for index in range(qubit_count):
                rx(2.0 * betas[layer], qubits[index])

    parameter_count = 2 * layers
    rng = np.random.default_rng(seed)
    initial = np.concatenate([
        rng.uniform(0.0, 2.0 * np.pi, size=layers),
        rng.uniform(0.0, np.pi, size=layers),
    ]).tolist()
    optimizer = cudaq.optimizers.COBYLA()
    optimizer.max_iterations = max_iterations
    optimizer.initial_parameters = initial

    def objective(parameters):
        gammas = [float(value) for value in parameters[:layers]]
        betas = [float(value) for value in parameters[layers:]]
        return cudaq.observe(
            qaoa_kernel, hamiltonian, n, layers, linear_z,
            pair_i, pair_j, pair_coefficients, gammas, betas
        ).expectation()

    started = time.perf_counter()
    optimal_expectation, optimal_parameters = optimizer.optimize(
        dimensions=parameter_count, function=objective
    )
    optimization_seconds = time.perf_counter() - started

    gammas = [float(value) for value in optimal_parameters[:layers]]
    betas = [float(value) for value in optimal_parameters[layers:]]
    sample_started = time.perf_counter()
    samples = cudaq.sample(
        qaoa_kernel, n, layers, linear_z, pair_i, pair_j,
        pair_coefficients, gammas, betas, shots_count=shots
    )
    sample_seconds = time.perf_counter() - sample_started

    feasible_counts = []
    for bitstring, count in samples.items():
        bits = tuple(int(bit) for bit in str(bitstring))
        if len(bits) != n:
            continue
        if is_feasible_at_most_one(bits):
            feasible_counts.append((evaluate_qubo(bits, qubo), bits, int(count)))
    if not feasible_counts:
        return {
            "status": "no_feasible_sample",
            "bitstring": None, "selected_tie_branch_ids": [],
            "qubo_energy": None, "restored_load_kw": None, "feasible": False,
            "feasible_shots": 0, "total_shots": shots,
            "runtime_seconds": optimization_seconds + sample_seconds,
            "optimization_runtime_seconds": optimization_seconds,
            "sampling_runtime_seconds": sample_seconds,
            "optimal_expectation": float(optimal_expectation),
            "optimal_parameters": [float(value) for value in optimal_parameters],
        }

    best_energy, best_bits, best_count = min(
        feasible_counts, key=lambda item: (item[0], item[1])
    )
    selected = [
        int(qubo["candidate_rows"].iloc[i]["candidate_tie_branch_id"])
        for i, bit in enumerate(best_bits) if bit
    ]
    benefit = sum(value * bit for value, bit in zip(qubo["benefits_kw"], best_bits))
    feasible_shots = sum(item[2] for item in feasible_counts)
    return {
        "status": "sampled_feasible_solution",
        "bitstring": "".join(str(bit) for bit in best_bits),
        "selected_tie_branch_ids": selected,
        "qubo_energy": float(best_energy),
        "restored_load_kw": float(benefit),
        "feasible": True,
        "best_bitstring_count": best_count,
        "feasible_shots": feasible_shots,
        "total_shots": shots,
        "feasible_shot_fraction": feasible_shots / shots,
        "runtime_seconds": optimization_seconds + sample_seconds,
        "optimization_runtime_seconds": optimization_seconds,
        "sampling_runtime_seconds": sample_seconds,
        "optimal_expectation": float(optimal_expectation),
        "optimal_parameters": [float(value) for value in optimal_parameters],
        "target": target or "CUDA-Q default target",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--states", type=Path,
        default=ROOT / "reports/ibtracs/phase_7k/phase_7k_unique_outage_states.csv")
    parser.add_argument("--candidates", type=Path,
        default=ROOT / "reports/ibtracs/phase_7k/phase_7k_restoration_candidates.csv")
    parser.add_argument("--output-dir", type=Path,
        default=ROOT / "reports/ibtracs/phase_8")
    parser.add_argument("--classical-only", action="store_true",
        help="Run the exact classical reference without importing CUDA-Q.")
    parser.add_argument("--qaoa-layers", type=int, default=1)
    parser.add_argument("--qaoa-shots", type=int, default=2048)
    parser.add_argument("--qaoa-max-iterations", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cudaq-target", default=None,
        help="Optional CUDA-Q target, e.g. qpp-cpu or nvidia.")
    parser.add_argument("--penalty-factor", type=float, default=1.0)
    args = parser.parse_args()
    for path in (args.states, args.candidates):
        if not path.exists():
            parser.error(f"Required Phase 7K input does not exist: {path}")

    states = pd.read_csv(args.states)
    candidates = pd.read_csv(args.candidates)
    scenarios = prepare_phase8_scenarios(states, candidates)
    rows = []
    candidate_details = []
    for scenario_index, scenario in enumerate(scenarios):
        state = scenario["state"]
        state_id = str(state["outage_state_id"])
        qubo = build_restoration_qubo(
            scenario["candidates"], penalty_factor=args.penalty_factor
        )
        classical = solve_classical_exact(qubo)
        qaoa = None
        if not args.classical_only and qubo["variable_count"] > 0:
            qaoa = run_cudaq_qaoa(
                qubo, layers=args.qaoa_layers, shots=args.qaoa_shots,
                max_iterations=args.qaoa_max_iterations,
                seed=args.seed + scenario_index, target=args.cudaq_target,
            )
        elif not args.classical_only:
            qaoa = {
                "status": "no_candidate_actions", "bitstring": "",
                "selected_tie_branch_ids": [], "qubo_energy": 0.0,
                "restored_load_kw": 0.0, "feasible": True,
                "feasible_shots": 0, "total_shots": 0, "runtime_seconds": 0.0,
            }

        exact_load = float(classical["restored_load_kw"])
        qaoa_load = None if qaoa is None else qaoa.get("restored_load_kw")
        gap = None if qaoa_load is None else exact_load - float(qaoa_load or 0.0)
        rows.append({
            "outage_state_id": state_id,
            "representative_contingency_id": state.get("representative_contingency_id"),
            "candidate_action_count": int(qubo["variable_count"]),
            "qubit_count": int(qubo["variable_count"]),
            "penalty": float(qubo["penalty"]),
            "classical_status": classical["status"],
            "classical_selected_tie_branch_ids": json.dumps(classical["selected_tie_branch_ids"]),
            "classical_restored_load_kw": exact_load,
            "classical_qubo_energy": classical["qubo_energy"],
            "classical_runtime_seconds": classical["runtime_seconds"],
            "qaoa_status": None if qaoa is None else qaoa["status"],
            "qaoa_selected_tie_branch_ids": None if qaoa is None else json.dumps(qaoa["selected_tie_branch_ids"]),
            "qaoa_restored_load_kw": qaoa_load,
            "qaoa_qubo_energy": None if qaoa is None else qaoa.get("qubo_energy"),
            "qaoa_runtime_seconds": None if qaoa is None else qaoa.get("runtime_seconds"),
            "qaoa_feasible_shot_fraction": None if qaoa is None else qaoa.get("feasible_shot_fraction"),
            "absolute_restored_load_gap_kw": gap,
            "qaoa_matches_classical_optimum": (
                None if qaoa_load is None else abs(exact_load - float(qaoa_load or 0.0)) < 1e-9
            ),
            "optimization_scope": "at_most_one_single_tie_action",
            "electrical_power_flow_validated": False,
        })
        for index, record in enumerate(qubo["candidate_rows"].to_dict("records")):
            candidate_details.append({
                "outage_state_id": state_id,
                "variable_index": index,
                "qubo_variable": f"x{index}",
                "restoration_candidate_id": record["restoration_candidate_id"],
                "candidate_tie_branch_id": int(record["candidate_tie_branch_id"]),
                "restored_load_kw": float(qubo["benefits_kw"][index]),
            })

    args.output_dir.mkdir(parents=True, exist_ok=True)
    result_path = args.output_dir / "phase_8_optimization_comparison.csv"
    detail_path = args.output_dir / "phase_8_candidate_variables.csv"
    manifest_path = args.output_dir / "phase_8_manifest.json"
    pd.DataFrame(rows).to_csv(result_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(candidate_details).to_csv(detail_path, index=False, encoding="utf-8-sig")
    manifest = {
        "status": "phase_8_classical_completed" if args.classical_only else "phase_8_optimization_completed",
        "inputs": {"states": str(args.states), "candidates": str(args.candidates)},
        "design": {
            "objective": "maximize nominal benchmark active load restored (kW)",
            "decision_variables": "one binary variable per Phase 7K single-tie restoration candidate",
            "constraint": "at most one tie action per outage state; all-zero vector means no action",
            "qubo": "E(x) = -sum_i restored_load_kw_i*x_i + P*sum_{i<j}x_i*x_j",
            "penalty": "P = penalty_factor*(sum_i restored_load_kw_i + 1), strictly larger than the sum of benefits",
            "classical_baseline": "exact enumeration of all 2^n bitstrings, filtered by at-most-one constraint",
            "quantum_method": None if args.classical_only else "QAOA with CUDA-Q; p-layer alternating cost and X-mixer unitaries",
            "qaoa_layers": None if args.classical_only else args.qaoa_layers,
            "qaoa_shots": None if args.classical_only else args.qaoa_shots,
            "qaoa_max_iterations": None if args.classical_only else args.qaoa_max_iterations,
            "seed": args.seed,
        },
        "semantics_and_limitations": [
            "This is a first-stage single-action-per-outage-state optimization, not a multi-switch restoration plan.",
            "The objective uses IEEE-33 benchmark nominal bus loads, not measured Minxiong or Taipower customer loads.",
            "QAOA is compared with exact enumeration on the same QUBO; no quantum advantage is assumed.",
            "QAOA results are sampled feasible bitstrings; a finite-shot run may fail to sample a feasible state.",
            "No AC power flow, voltage, thermal, protection, fault-current, radial switching sequence, BESS, or distributed-generation constraints are validated.",
            "Upstream fragility assumptions remain uncalibrated and network geometry remains synthetic.",
        ],
        "outputs": {
            "optimization_comparison": str(result_path),
            "candidate_variables": str(detail_path),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": manifest["status"], "scenario_count": len(rows),
        "candidate_action_count": len(candidate_details),
        "outputs": manifest["outputs"], "manifest": str(manifest_path),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
