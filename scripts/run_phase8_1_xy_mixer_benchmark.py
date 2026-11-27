"""Compare Phase 8 X-mixer QAOA, Phase 8.1 one-hot XY-mixer QAOA, and exact enumeration."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grid.restoration_optimization import (  # noqa: E402
    build_restoration_qubo,
    solve_classical_exact,
)
from grid.constraint_preserving_restoration import (  # noqa: E402
    build_one_hot_problem,
    solve_one_hot_exact,
)
from scripts.run_phase8_restoration_optimization import run_cudaq_qaoa  # noqa: E402


def run_cudaq_xy_qaoa(
    problem: dict,
    *,
    layers: int = 1,
    shots: int = 2048,
    max_iterations: int = 100,
    seed: int = 42,
    target: str | None = None,
) -> dict:
    """Run QAOA with a complete-graph, product-form XY mixer.

    The circuit starts in |100...0>, where qubit 0 is no-action. Each mixer
    edge applies RXX(beta)RYY(beta), decomposed into H/CNOT/RZ and
    S-dagger/H/CNOT/RZ/H/S gates. Every factor preserves excitation number.
    """
    import numpy as np
    import cudaq

    if layers < 1 or shots < 1 or max_iterations < 1:
        raise ValueError("layers, shots, and max_iterations must be positive")

    choice_count = int(problem["choice_count"])
    action_count = int(problem["action_count"])
    benefits = [float(v) for v in problem["benefits_kw"]]
    if action_count == 0:
        return {
            "status": "no_candidate_actions", "bitstring": "1",
            "selected_tie_branch_ids": [], "restored_load_kw": 0.0,
            "qubo_energy": 0.0, "feasible": True, "feasible_shots": 0,
            "constraint_violations": 0, "total_shots": 0,
            "feasible_shot_fraction": None, "runtime_seconds": 0.0,
            "optimal_expectation": 0.0, "optimal_parameters": [],
        }
    if max(benefits[1:], default=0.0) <= 0.0:
        return {
            "status": "deterministic_no_action", "bitstring": "1" + "0" * action_count,
            "selected_tie_branch_ids": [], "restored_load_kw": 0.0,
            "qubo_energy": 0.0, "feasible": True, "feasible_shots": 0,
            "constraint_violations": 0, "total_shots": 0,
            "feasible_shot_fraction": None, "runtime_seconds": 0.0,
            "optimal_expectation": 0.0, "optimal_parameters": [],
        }

    if target:
        cudaq.set_target(target)
    cudaq.set_random_seed(seed)

    # H_C = sum_i (b_i / 2) Z_i + constant, with the constant omitted
    # during optimization because it does not affect the minimizing parameters.
    hamiltonian = None
    for index, benefit in enumerate(benefits[1:], start=1):
        if benefit <= 0.0:
            continue
        term = (0.5 * benefit) * cudaq.spin.z(index)
        hamiltonian = term if hamiltonian is None else hamiltonian + term
    if hamiltonian is None:
        raise RuntimeError("Positive restoration benefits produced no cost Hamiltonian")

    edge_source = [int(i) for i, _ in problem["mixer_edges"]]
    edge_target = [int(j) for _, j in problem["mixer_edges"]]

    @cudaq.kernel
    def xy_qaoa_kernel(
        qubit_count: int,
        layer_count: int,
        benefit_values: list[float],
        sources: list[int],
        targets: list[int],
        gammas: list[float],
        betas: list[float],
    ):
        q = cudaq.qvector(qubit_count)
        # Explicit no-action reference state |100...0>.
        x(q[0])
        for layer in range(layer_count):
            # exp(-i gamma H_C): RZ(gamma * b_i) on action qubits.
            for index in range(1, qubit_count):
                rz(gammas[layer] * benefit_values[index], q[index])

            # Product-form complete-graph XY mixer. For each edge:
            # exp(-i beta (XX + YY)/2) = RXX(beta) RYY(beta).
            for edge in range(len(sources)):
                first = sources[edge]
                second = targets[edge]

                # RXX(beta) = (H x H) RZZ(beta) (H x H).
                h(q[first])
                h(q[second])
                x.ctrl(q[first], q[second])
                rz(betas[layer], q[second])
                x.ctrl(q[first], q[second])
                h(q[first])
                h(q[second])

                # RYY(beta) = (S H x S H) RZZ(beta) (H S-dagger x H S-dagger).
                s.adj(q[first])
                s.adj(q[second])
                h(q[first])
                h(q[second])
                x.ctrl(q[first], q[second])
                rz(betas[layer], q[second])
                x.ctrl(q[first], q[second])
                h(q[first])
                h(q[second])
                s(q[first])
                s(q[second])

    rng = np.random.default_rng(seed)
    initial = np.concatenate([
        rng.uniform(-np.pi, np.pi, size=layers),
        rng.uniform(-np.pi, np.pi, size=layers),
    ]).tolist()
    optimizer = cudaq.optimizers.COBYLA()
    optimizer.max_iterations = max_iterations
    optimizer.initial_parameters = initial

    def objective(parameters):
        gammas = [float(v) for v in parameters[:layers]]
        betas = [float(v) for v in parameters[layers:]]
        return cudaq.observe(
            xy_qaoa_kernel, hamiltonian, choice_count, layers, benefits,
            edge_source, edge_target, gammas, betas
        ).expectation()

    started = time.perf_counter()
    optimal_expectation, optimal_parameters = optimizer.optimize(
        dimensions=2 * layers, function=objective
    )
    optimization_seconds = time.perf_counter() - started

    gammas = [float(v) for v in optimal_parameters[:layers]]
    betas = [float(v) for v in optimal_parameters[layers:]]
    sample_started = time.perf_counter()
    samples = cudaq.sample(
        xy_qaoa_kernel, choice_count, layers, benefits,
        edge_source, edge_target, gammas, betas, shots_count=shots
    )
    sampling_seconds = time.perf_counter() - sample_started

    feasible_counts = []
    constraint_violations = 0
    for bitstring, count in samples.items():
        bits = tuple(int(bit) for bit in str(bitstring))
        if len(bits) != choice_count or sum(bits) != 1:
            constraint_violations += int(count)
            continue
        energy = -sum(value * bit for value, bit in zip(benefits, bits))
        feasible_counts.append((float(energy), bits, int(count)))

    feasible_shots = sum(item[2] for item in feasible_counts)
    if not feasible_counts:
        return {
            "status": "no_feasible_sample", "bitstring": None,
            "selected_tie_branch_ids": [], "restored_load_kw": None,
            "qubo_energy": None, "feasible": False, "feasible_shots": 0,
            "constraint_violations": constraint_violations, "total_shots": shots,
            "feasible_shot_fraction": 0.0,
            "runtime_seconds": optimization_seconds + sampling_seconds,
            "optimization_runtime_seconds": optimization_seconds,
            "sampling_runtime_seconds": sampling_seconds,
            "optimal_expectation": float(optimal_expectation) - 0.5 * sum(benefits[1:]),
            "optimal_parameters": [float(v) for v in optimal_parameters],
        }

    best_energy, best_bits, best_count = min(
        feasible_counts, key=lambda item: (item[0], item[1])
    )
    selected = []
    for index, bit in enumerate(best_bits[1:], start=1):
        if bit:
            selected.append(int(problem["candidate_rows"].iloc[index - 1]["candidate_tie_branch_id"]))

    return {
        "status": "sampled_feasible_solution",
        "bitstring": "".join(str(bit) for bit in best_bits),
        "selected_tie_branch_ids": selected,
        "restored_load_kw": float(-best_energy),
        "qubo_energy": float(best_energy),
        "feasible": True,
        "best_bitstring_count": best_count,
        "feasible_shots": feasible_shots,
        "constraint_violations": constraint_violations,
        "total_shots": shots,
        "feasible_shot_fraction": feasible_shots / shots,
        "runtime_seconds": optimization_seconds + sampling_seconds,
        "optimization_runtime_seconds": optimization_seconds,
        "sampling_runtime_seconds": sampling_seconds,
        "optimal_expectation": float(optimal_expectation) - 0.5 * sum(benefits[1:]),
        "optimal_parameters": [float(v) for v in optimal_parameters],
        "target": target or "CUDA-Q default (not explicitly set)",
    }


def _synthetic_candidates(size: int) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "restoration_candidate_id": f"SYNTH-TIE-{i + 1:03d}",
            "candidate_tie_branch_id": 100 + i,
            "restored_load_kw": float(100 + ((i * 137 + 53) % 1901)),
        }
        for i in range(size)
    ])


def _evaluate_pair(candidates, *, seed, scenario_id, benchmark_type, layers, shots, iterations, target):
    penalty_qubo = build_restoration_qubo(candidates)
    exact = solve_classical_exact(penalty_qubo)
    one_hot = build_one_hot_problem(candidates)
    exact_one_hot = solve_one_hot_exact(one_hot)
    if abs(float(exact["restored_load_kw"]) - float(exact_one_hot["restored_load_kw"])) > 1e-9:
        raise AssertionError("Penalty and one-hot exact formulations disagree on the optimum")

    if penalty_qubo["variable_count"]:
        x_result = run_cudaq_qaoa(
            penalty_qubo, layers=layers, shots=shots, max_iterations=iterations,
            seed=seed, target=target,
        )
    else:
        x_result = {
            "status": "no_candidate_actions", "restored_load_kw": 0.0,
            "runtime_seconds": 0.0, "feasible_shot_fraction": None,
            "feasible": True, "constraint_violations": None,
        }

    xy_result = run_cudaq_xy_qaoa(
        one_hot, layers=layers, shots=shots, max_iterations=iterations,
        seed=seed, target=target,
    )
    rows = []
    for method, result, exact_result, qubits in (
        ("x_mixer_penalty", x_result, exact, penalty_qubo["variable_count"]),
        ("xy_mixer_one_hot", xy_result, exact_one_hot, one_hot["choice_count"]),
    ):
        sampled = result.get("restored_load_kw")
        rows.append({
            "benchmark_type": benchmark_type,
            "scenario_id": str(scenario_id),
            "seed": seed,
            "method": method,
            "action_count": int(penalty_qubo["variable_count"]),
            "qubit_count": int(qubits),
            "qaoa_status": result["status"],
            "qaoa_restored_load_kw": sampled,
            "exact_restored_load_kw": float(exact_result["restored_load_kw"]),
            "absolute_objective_gap_kw": (
                None if sampled is None else abs(float(exact_result["restored_load_kw"]) - float(sampled))
            ),
            "matches_exact_optimum": (
                None if sampled is None else abs(float(exact_result["restored_load_kw"]) - float(sampled)) < 1e-9
            ),
            "feasible": result.get("feasible"),
            "feasible_shots": result.get("feasible_shots"),
            "total_shots": result.get("total_shots"),
            "feasible_shot_fraction": result.get("feasible_shot_fraction"),
            "constraint_violations": result.get("constraint_violations"),
            "qaoa_runtime_seconds": result.get("runtime_seconds"),
            "classical_exact_runtime_seconds": exact.get("runtime_seconds"),
            "optimal_expectation": result.get("optimal_expectation"),
            "selected_tie_branch_ids": json.dumps(result.get("selected_tie_branch_ids", [])),
            "cudaq_target": result.get("target", target or "CUDA-Q default"),
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--states", type=Path,
        default=ROOT / "reports/ibtracs/phase_7k/phase_7k_unique_outage_states.csv")
    parser.add_argument("--candidates", type=Path,
        default=ROOT / "reports/ibtracs/phase_7k/phase_7k_restoration_candidates.csv")
    parser.add_argument("--output-dir", type=Path,
        default=ROOT / "reports/ibtracs/phase_8_1")
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 43, 44])
    parser.add_argument("--scaling-seeds", nargs="+", type=int, default=[42, 43, 44])
    parser.add_argument("--scaling-sizes", nargs="+", type=int, default=[1, 2, 3, 4, 6, 8, 10, 12, 14, 16])
    parser.add_argument("--skip-real", action="store_true")
    parser.add_argument("--skip-scaling", action="store_true")
    parser.add_argument("--qaoa-layers", type=int, default=1)
    parser.add_argument("--qaoa-shots", type=int, default=2048)
    parser.add_argument("--qaoa-max-iterations", type=int, default=100)
    parser.add_argument("--cudaq-target", default="nvidia")
    args = parser.parse_args()

    if not args.skip_real:
        for path in (args.states, args.candidates):
            if not path.exists():
                parser.error(f"Required Phase 7K input does not exist: {path}")
    if not args.skip_scaling and not args.scaling_sizes:
        parser.error("Provide at least one scaling size")
    if not args.seeds or not args.scaling_seeds:
        parser.error("Seed lists must not be empty")

    started = time.perf_counter()
    rows = []
    if not args.skip_real:
        states = pd.read_csv(args.states)
        candidates = pd.read_csv(args.candidates)
        for scenario_index, state in enumerate(states.sort_values("outage_state_id", kind="stable").to_dict("records")):
            state_id = str(state["outage_state_id"])
            subset = candidates[candidates["outage_state_id"].astype(str) == state_id].copy()
            for seed in args.seeds:
                rows.extend(_evaluate_pair(
                    subset, seed=seed + scenario_index, scenario_id=state_id,
                    benchmark_type="phase_7k_outage_state", layers=args.qaoa_layers,
                    shots=args.qaoa_shots, iterations=args.qaoa_max_iterations,
                    target=args.cudaq_target,
                ))

    if not args.skip_scaling:
        for size in args.scaling_sizes:
            if size < 1:
                parser.error("All scaling sizes must be positive")
            synthetic = _synthetic_candidates(size)
            for seed in args.scaling_seeds:
                rows.extend(_evaluate_pair(
                    synthetic, seed=seed + size * 1000,
                    scenario_id=f"synthetic_{size}_actions",
                    benchmark_type="synthetic_scaling", layers=args.qaoa_layers,
                    shots=args.qaoa_shots, iterations=args.qaoa_max_iterations,
                    target=args.cudaq_target,
                ))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = pd.DataFrame(rows)
    results_path = args.output_dir / "phase_8_1_comparison.csv"
    summary_path = args.output_dir / "phase_8_1_summary.csv"
    manifest_path = args.output_dir / "phase_8_1_manifest.json"
    results.to_csv(results_path, index=False, encoding="utf-8-sig")
    if not results.empty:
        summary = results.groupby(["benchmark_type", "method"], dropna=False).agg(
            runs=("scenario_id", "count"),
            feasible_runs=("feasible", lambda values: int(values.fillna(False).sum())),
            exact_optimum_matches=("matches_exact_optimum", lambda values: int(values.fillna(False).sum())),
            mean_feasible_shot_fraction=("feasible_shot_fraction", "mean"),
            mean_qaoa_runtime_seconds=("qaoa_runtime_seconds", "mean"),
            total_constraint_violations=("constraint_violations", "sum"),
        ).reset_index()
    else:
        summary = pd.DataFrame()
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    manifest = {
        "status": "phase_8_1_benchmark_completed",
        "formulation": {
            "encoding": "one-hot over no-action plus each single-tie restoration action",
            "no_action_choice_index": 0,
            "initial_state": "|100...0>",
            "constraint": "exactly one excitation",
            "cost": "H_C = -sum_i restored_load_kw_i * x_i; constant omitted during optimization",
            "mixer": "complete-graph product-form XY mixer; each edge applies RXX(beta)RYY(beta)",
            "gate_decomposition": "RXX/RYY synthesized from H, S, CNOT, and RZ gates",
        },
        "configuration": {
            "real_seeds": args.seeds,
            "scaling_seeds": args.scaling_seeds,
            "scaling_sizes_actions": args.scaling_sizes,
            "qaoa_layers": args.qaoa_layers,
            "qaoa_shots": args.qaoa_shots,
            "qaoa_max_iterations": args.qaoa_max_iterations,
            "cudaq_target": args.cudaq_target,
        },
        "outputs": {
            "comparison": str(results_path),
            "summary": str(summary_path),
        },
        "limitations": [
            "The XY mixer is a sequential product of pairwise exchange rotations, not an exact exponential of the complete mixer Hamiltonian in one gate.",
            "The one-hot invariant is expected from the excitation-preserving gate decomposition and must be confirmed by CUDA-Q integration tests on the selected target.",
            "Synthetic scaling instances are computational stress tests, not additional physical grid states.",
            "Exact enumeration remains the classical optimum reference; no quantum advantage is assumed.",
            "The objective remains nominal IEEE-33 benchmark load and is not AC-power-flow or operationally validated.",
        ],
        "wall_runtime_seconds": time.perf_counter() - started,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": manifest["status"], "result_rows": len(results),
        "summary_rows": len(summary), "outputs": manifest["outputs"],
        "manifest": str(manifest_path),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
