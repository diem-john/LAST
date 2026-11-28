"""Phase 8.2: compare QAOA depth, outcomes, runtime, and source-level resources."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grid.constraint_preserving_restoration import (  # noqa: E402
    build_one_hot_problem,
    solve_one_hot_exact,
)
from grid.qaoa_resource_estimates import (  # noqa: E402
    estimate_x_mixer_resources,
    estimate_xy_mixer_resources,
)
from grid.restoration_optimization import (  # noqa: E402
    build_restoration_qubo,
    qubo_to_ising,
    solve_classical_exact,
)
from scripts.run_phase8_1_xy_mixer_benchmark import (  # noqa: E402
    _synthetic_candidates,
    run_cudaq_xy_qaoa,
)
from scripts.run_phase8_restoration_optimization import run_cudaq_qaoa  # noqa: E402


def _evaluate(candidates, *, benchmark_type, scenario_id, seed, depth, shots, iterations, target):
    qubo = build_restoration_qubo(candidates)
    exact_x = solve_classical_exact(qubo)
    one_hot = build_one_hot_problem(candidates)
    exact_xy = solve_one_hot_exact(one_hot)
    if abs(float(exact_x["restored_load_kw"]) - float(exact_xy["restored_load_kw"])) > 1e-9:
        raise AssertionError("X-mixer and XY-mixer exact formulations disagree")

    ising = qubo_to_ising(qubo)
    x_resources = estimate_x_mixer_resources(
        qubo["variable_count"], len(ising["quadratic_zz"]), depth
    )
    xy_resources = estimate_xy_mixer_resources(qubo["variable_count"], depth)

    if qubo["variable_count"]:
        x_result = run_cudaq_qaoa(
            qubo, layers=depth, shots=shots, max_iterations=iterations,
            seed=seed, target=target,
        )
    else:
        x_result = {
            "status": "no_candidate_actions", "restored_load_kw": 0.0,
            "runtime_seconds": 0.0, "feasible": True,
            "feasible_shots": 0, "total_shots": 0,
            "feasible_shot_fraction": None, "constraint_violations": 0,
        }

    xy_result = run_cudaq_xy_qaoa(
        one_hot, layers=depth, shots=shots, max_iterations=iterations,
        seed=seed, target=target,
    )

    rows = []
    for method, result, exact, resources in (
        ("x_mixer_penalty", x_result, exact_x, x_resources),
        ("xy_mixer_one_hot", xy_result, exact_xy, xy_resources),
    ):
        sampled_load = result.get("restored_load_kw")
        exact_load = float(exact["restored_load_kw"])
        feasible_shots = result.get("feasible_shots")
        total_shots = result.get("total_shots")
        violations = result.get("constraint_violations")
        if violations is None and feasible_shots is not None and total_shots is not None:
            violations = max(0, int(total_shots) - int(feasible_shots))
        rows.append({
            "benchmark_type": benchmark_type,
            "scenario_id": str(scenario_id),
            "seed": int(seed),
            "qaoa_layers": int(depth),
            "method": method,
            "action_count": int(qubo["variable_count"]),
            **resources,
            "qaoa_status": result.get("status"),
            "qaoa_restored_load_kw": sampled_load,
            "exact_restored_load_kw": exact_load,
            "absolute_objective_gap_kw": (
                None if sampled_load is None else abs(exact_load - float(sampled_load))
            ),
            "matches_exact_optimum": (
                None if sampled_load is None else abs(exact_load - float(sampled_load)) < 1e-9
            ),
            "feasible": result.get("feasible"),
            "feasible_shots": result.get("feasible_shots"),
            "total_shots": result.get("total_shots"),
            "feasible_shot_fraction": result.get("feasible_shot_fraction"),
            "constraint_violations": violations,
            "qaoa_runtime_seconds": result.get("runtime_seconds"),
            "classical_exact_runtime_seconds": exact_x.get("runtime_seconds"),
            "optimization_runtime_seconds": result.get("optimization_runtime_seconds"),
            "sampling_runtime_seconds": result.get("sampling_runtime_seconds"),
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
        default=ROOT / "reports/ibtracs/phase_8_2")
    parser.add_argument("--depths", nargs="+", type=int, default=[1, 2, 3])
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 43, 44, 45, 46])
    parser.add_argument("--scaling-seeds", nargs="+", type=int, default=list(range(42, 62)))
    parser.add_argument("--scaling-sizes", nargs="+", type=int,
        default=[1, 2, 3, 4, 6, 8, 10, 12, 14, 16])
    parser.add_argument("--skip-real", action="store_true")
    parser.add_argument("--skip-scaling", action="store_true")
    parser.add_argument("--shots", type=int, default=2048)
    parser.add_argument("--max-iterations", type=int, default=100)
    parser.add_argument("--cudaq-target", default="nvidia")
    args = parser.parse_args()

    if any(depth < 1 for depth in args.depths):
        parser.error("All QAOA depths must be positive")
    if args.shots < 1 or args.max_iterations < 1:
        parser.error("shots and max-iterations must be positive")
    if not args.skip_real:
        for path in (args.states, args.candidates):
            if not path.exists():
                parser.error(f"Required Phase 7K input does not exist: {path}")
    if not args.skip_scaling and any(size < 1 for size in args.scaling_sizes):
        parser.error("All scaling sizes must be positive")
    if not args.skip_real and not args.seeds:
        parser.error("Real-case seed list must not be empty")
    if not args.skip_scaling and not args.scaling_seeds:
        parser.error("Scaling seed list must not be empty")

    started = time.perf_counter()
    rows = []
    if not args.skip_real:
        states = pd.read_csv(args.states)
        candidates = pd.read_csv(args.candidates)
        ordered_states = states.sort_values("outage_state_id", kind="stable").to_dict("records")
        for state_index, state in enumerate(ordered_states):
            state_id = str(state["outage_state_id"])
            subset = candidates[candidates["outage_state_id"].astype(str) == state_id].copy()
            for seed in args.seeds:
                for depth in args.depths:
                    run_seed = int(seed + state_index * 1009 + depth * 100000)
                    rows.extend(_evaluate(
                        subset, benchmark_type="phase_7k_outage_state",
                        scenario_id=state_id, seed=run_seed, depth=depth,
                        shots=args.shots, iterations=args.max_iterations,
                        target=args.cudaq_target,
                    ))

    if not args.skip_scaling:
        for size in args.scaling_sizes:
            synthetic = _synthetic_candidates(size)
            for seed in args.scaling_seeds:
                for depth in args.depths:
                    run_seed = int(seed + size * 1000 + depth * 100000)
                    rows.extend(_evaluate(
                        synthetic, benchmark_type="synthetic_scaling",
                        scenario_id=f"synthetic_{size}_actions", seed=run_seed,
                        depth=depth, shots=args.shots,
                        iterations=args.max_iterations, target=args.cudaq_target,
                    ))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = pd.DataFrame(rows)
    comparison_path = args.output_dir / "phase_8_2_comparison.csv"
    summary_path = args.output_dir / "phase_8_2_summary.csv"
    manifest_path = args.output_dir / "phase_8_2_manifest.json"
    results.to_csv(comparison_path, index=False, encoding="utf-8-sig")

    if results.empty:
        summary = pd.DataFrame()
    else:
        summary = results.groupby(
            ["benchmark_type", "method", "qaoa_layers", "action_count"], dropna=False
        ).agg(
            runs=("scenario_id", "count"),
            feasible_runs=("feasible", lambda values: int(values.fillna(False).sum())),
            exact_optimum_matches=("matches_exact_optimum", lambda values: int(values.fillna(False).sum())),
            mean_feasible_shot_fraction=("feasible_shot_fraction", "mean"),
            mean_qaoa_runtime_seconds=("qaoa_runtime_seconds", "mean"),
            median_qaoa_runtime_seconds=("qaoa_runtime_seconds", "median"),
            mean_classical_exact_runtime_seconds=("classical_exact_runtime_seconds", "mean"),
            mean_qubits=("qubit_count", "mean"),
            mean_primitive_gate_count=("primitive_gate_count", "mean"),
            mean_two_qubit_gate_count=("two_qubit_gate_count", "mean"),
            mean_source_order_depth_upper_bound=("source_order_depth_upper_bound", "mean"),
            total_constraint_violations=("constraint_violations", "sum"),
        ).reset_index()
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")

    manifest = {
        "status": "phase_8_2_benchmark_completed",
        "study": "QAOA depth, solution reliability, runtime, and source-level gate-resource scaling",
        "configuration": {
            "depths": args.depths,
            "real_seeds": args.seeds,
            "scaling_seeds": args.scaling_seeds,
            "scaling_sizes_actions": args.scaling_sizes,
            "shots": args.shots,
            "max_iterations": args.max_iterations,
            "cudaq_target": args.cudaq_target,
        },
        "resource_accounting": {
            "basis": "primitive gate calls in the current Python CUDA-Q kernel source",
            "depth_metric": "conservative source-order serial depth upper bound",
            "not_measured": [
                "backend-transpiled circuit depth",
                "hardware-native gate count",
                "physical gate duration",
                "device utilization",
            ],
            "xy_edge_decomposition": "18 primitive calls per complete-graph edge per layer, including four controlled-X gates",
        },
        "outputs": {
            "comparison": str(comparison_path),
            "summary": str(summary_path),
        },
        "limitations": [
            "Synthetic scaling instances are computational stress tests, not additional physical grid states.",
            "Exact enumeration remains the classical optimum reference; no quantum advantage is assumed.",
            "The XY mixer is a sequential product of pairwise exchange rotations, not an exact exponential of the summed complete-graph mixer Hamiltonian.",
            "The objective remains nominal IEEE-33 benchmark load and is not AC-power-flow or operationally validated.",
            "Source-level resource estimates are not backend-transpiled hardware circuit metrics.",
        ],
        "wall_runtime_seconds": time.perf_counter() - started,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": manifest["status"],
        "result_rows": len(results),
        "summary_rows": len(summary),
        "outputs": manifest["outputs"],
        "manifest": str(manifest_path),
        "wall_runtime_seconds": manifest["wall_runtime_seconds"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
