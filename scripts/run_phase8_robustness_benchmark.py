"""Run multi-seed Phase 8 reproducibility and synthetic QAOA scaling benchmarks.

The real-data experiment reuses Phase 7K outage states and restoration candidates.
The scaling experiment creates synthetic at-most-one-action QUBOs of increasing
size; it is a computational stress test, not an electrical-grid validation.
"""
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

from grid.restoration_optimization import (  # noqa: E402
    build_restoration_qubo,
    prepare_phase8_scenarios,
    solve_classical_exact,
)
from scripts.run_phase8_restoration_optimization import run_cudaq_qaoa  # noqa: E402


def build_synthetic_candidates(variable_count: int) -> pd.DataFrame:
    """Create deterministic, positive-benefit candidates for scaling tests."""
    if variable_count < 1:
        raise ValueError("variable_count must be at least 1")
    return pd.DataFrame([
        {
            "restoration_candidate_id": f"SYNTH-TIE-{index + 1:03d}",
            "candidate_tie_branch_id": 100 + index,
            "restored_load_kw": float(100 + ((index * 137 + 53) % 1901)),
        }
        for index in range(variable_count)
    ])


def run_real_multiseed(
    states_path: Path,
    candidates_path: Path,
    seeds: list[int],
    *,
    layers: int,
    shots: int,
    max_iterations: int,
    target: str | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    states = pd.read_csv(states_path)
    candidates = pd.read_csv(candidates_path)
    scenarios = prepare_phase8_scenarios(states, candidates)
    exact_by_state = {}

    for scenario in scenarios:
        state_id = str(scenario["state"]["outage_state_id"])
        qubo = build_restoration_qubo(scenario["candidates"])
        exact_by_state[state_id] = solve_classical_exact(qubo)

    rows = []
    for seed in seeds:
        for scenario_index, scenario in enumerate(scenarios):
            state = scenario["state"]
            state_id = str(state["outage_state_id"])
            qubo = build_restoration_qubo(scenario["candidates"])
            exact = exact_by_state[state_id]
            if qubo["variable_count"] == 0:
                qaoa = {
                    "status": "no_candidate_actions",
                    "selected_tie_branch_ids": [],
                    "restored_load_kw": 0.0,
                    "runtime_seconds": 0.0,
                    "feasible_shot_fraction": None,
                }
            else:
                qaoa = run_cudaq_qaoa(
                    qubo,
                    layers=layers,
                    shots=shots,
                    max_iterations=max_iterations,
                    seed=seed + scenario_index,
                    target=target,
                )

            qaoa_load = qaoa.get("restored_load_kw")
            exact_load = float(exact["restored_load_kw"])
            rows.append({
                "seed": seed,
                "outage_state_id": state_id,
                "representative_contingency_id": state.get("representative_contingency_id"),
                "candidate_action_count": int(qubo["variable_count"]),
                "qubit_count": int(qubo["variable_count"]),
                "classical_selected_tie_branch_ids": json.dumps(exact["selected_tie_branch_ids"]),
                "classical_restored_load_kw": exact_load,
                "classical_runtime_seconds": exact["runtime_seconds"],
                "qaoa_status": qaoa["status"],
                "qaoa_selected_tie_branch_ids": json.dumps(qaoa.get("selected_tie_branch_ids", [])),
                "qaoa_restored_load_kw": qaoa_load,
                "qaoa_runtime_seconds": qaoa.get("runtime_seconds"),
                "qaoa_feasible_shot_fraction": qaoa.get("feasible_shot_fraction"),
                "absolute_restored_load_gap_kw": (
                    None if qaoa_load is None else abs(exact_load - float(qaoa_load))
                ),
                "qaoa_matches_classical_optimum": (
                    None if qaoa_load is None
                    else abs(exact_load - float(qaoa_load)) < 1e-9
                ),
                "cudaq_seed": seed + scenario_index,
                "cudaq_target": target or "CUDA-Q default",
            })

    results = pd.DataFrame(rows)
    actionable = results[results["candidate_action_count"] > 0]
    summary_rows = []
    for seed, group in results.groupby("seed", sort=True):
        active = group[group["candidate_action_count"] > 0]
        valid = active[active["qaoa_restored_load_kw"].notna()]
        fractions = active["qaoa_feasible_shot_fraction"].dropna()
        summary_rows.append({
            "seed": int(seed),
            "scenario_count": len(group),
            "actionable_scenario_count": len(active),
            "qaoa_feasible_solution_count": int(active["qaoa_restored_load_kw"].notna().sum()),
            "classical_optimum_matches": int(active["qaoa_matches_classical_optimum"].fillna(False).sum()),
            "optimality_agreement_rate": (
                float(active["qaoa_matches_classical_optimum"].fillna(False).mean())
                if len(active) else None
            ),
            "mean_feasible_shot_fraction": float(fractions.mean()) if len(fractions) else None,
            "mean_qaoa_runtime_seconds": float(valid["qaoa_runtime_seconds"].mean()) if len(valid) else None,
            "mean_classical_runtime_seconds": float(active["classical_runtime_seconds"].mean()) if len(active) else None,
        })

    if actionable.empty:
        raise ValueError("The supplied Phase 7K inputs contain no actionable scenarios")
    return results, pd.DataFrame(summary_rows)


def run_scaling(
    sizes: list[int],
    seeds: list[int],
    *,
    layers: int,
    shots: int,
    max_iterations: int,
    target: str | None,
) -> pd.DataFrame:
    rows = []
    for size in sizes:
        if size < 1:
            raise ValueError("All scaling sizes must be at least 1")
        candidates = build_synthetic_candidates(size)
        qubo = build_restoration_qubo(candidates)
        exact = solve_classical_exact(qubo)
        for seed in seeds:
            qaoa_seed = seed + size * 1000
            qaoa = run_cudaq_qaoa(
                qubo,
                layers=layers,
                shots=shots,
                max_iterations=max_iterations,
                seed=qaoa_seed,
                target=target,
            )
            qaoa_load = qaoa.get("restored_load_kw")
            exact_load = float(exact["restored_load_kw"])
            rows.append({
                "variable_count": size,
                "qubit_count": size,
                "seed": seed,
                "cudaq_seed": qaoa_seed,
                "classical_enumerated_bitstrings": 2 ** size,
                "classical_restored_load_kw": exact_load,
                "classical_runtime_seconds": exact["runtime_seconds"],
                "qaoa_status": qaoa["status"],
                "qaoa_restored_load_kw": qaoa_load,
                "qaoa_runtime_seconds": qaoa.get("runtime_seconds"),
                "qaoa_feasible_shot_fraction": qaoa.get("feasible_shot_fraction"),
                "absolute_restored_load_gap_kw": (
                    None if qaoa_load is None else abs(exact_load - float(qaoa_load))
                ),
                "qaoa_matches_classical_optimum": (
                    None if qaoa_load is None
                    else abs(exact_load - float(qaoa_load)) < 1e-9
                ),
                "cudaq_target": target or "CUDA-Q default",
                "benchmark_type": "synthetic_at_most_one_action",
            })
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--states", type=Path,
        default=ROOT / "reports/ibtracs/phase_7k/phase_7k_unique_outage_states.csv")
    parser.add_argument("--candidates", type=Path,
        default=ROOT / "reports/ibtracs/phase_7k/phase_7k_restoration_candidates.csv")
    parser.add_argument("--output-dir", type=Path,
        default=ROOT / "reports/ibtracs/phase_8_robustness")
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 43, 44, 45, 46])
    parser.add_argument("--scaling-seeds", nargs="+", type=int, default=[42, 43, 44])
    parser.add_argument("--scaling-sizes", nargs="+", type=int,
        default=[1, 2, 3, 4, 6, 8, 10, 12, 14, 16])
    parser.add_argument("--qaoa-layers", type=int, default=1)
    parser.add_argument("--qaoa-shots", type=int, default=2048)
    parser.add_argument("--qaoa-max-iterations", type=int, default=100)
    parser.add_argument("--cudaq-target", default="nvidia")
    args = parser.parse_args()

    for path in (args.states, args.candidates):
        if not path.exists():
            parser.error(f"Required Phase 7K input does not exist: {path}")
    if not args.seeds or not args.scaling_seeds:
        parser.error("At least one real-data seed and one scaling seed are required")
    if any(size < 1 for size in args.scaling_sizes):
        parser.error("Scaling sizes must all be positive")

    started = time.perf_counter()
    real_results, real_summary = run_real_multiseed(
        args.states, args.candidates, args.seeds,
        layers=args.qaoa_layers, shots=args.qaoa_shots,
        max_iterations=args.qaoa_max_iterations, target=args.cudaq_target,
    )
    scaling_results = run_scaling(
        args.scaling_sizes, args.scaling_seeds,
        layers=args.qaoa_layers, shots=args.qaoa_shots,
        max_iterations=args.qaoa_max_iterations, target=args.cudaq_target,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    real_path = args.output_dir / "phase_8_multiseed_results.csv"
    summary_path = args.output_dir / "phase_8_multiseed_summary.csv"
    scaling_path = args.output_dir / "phase_8_scaling_results.csv"
    manifest_path = args.output_dir / "phase_8_robustness_manifest.json"
    real_results.to_csv(real_path, index=False, encoding="utf-8-sig")
    real_summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    scaling_results.to_csv(scaling_path, index=False, encoding="utf-8-sig")

    manifest = {
        "status": "phase_8_robustness_completed",
        "benchmark_scope": {
            "real_data": "Phase 7K outage states and single-tie restoration candidates",
            "scaling": "synthetic at-most-one-action QUBOs; computational stress test only",
        },
        "configuration": {
            "real_data_seeds": args.seeds,
            "scaling_seeds": args.scaling_seeds,
            "scaling_sizes_qubits": args.scaling_sizes,
            "qaoa_layers": args.qaoa_layers,
            "qaoa_shots": args.qaoa_shots,
            "qaoa_max_iterations": args.qaoa_max_iterations,
            "cudaq_target": args.cudaq_target,
        },
        "outputs": {
            "multiseed_results": str(real_path),
            "multiseed_summary": str(summary_path),
            "scaling_results": str(scaling_path),
        },
        "limitations": [
            "Synthetic scaling instances do not represent additional physical grid assets or validated grid states.",
            "Exact enumeration is included only for sizes where 2^n enumeration is computationally manageable.",
            "Runtime comparisons depend on hardware, CUDA-Q version, compilation state, and backend configuration.",
            "No quantum advantage is assumed or established.",
            "The restoration objective remains nominal benchmark load and is not validated by AC power flow or operational constraints.",
        ],
        "wall_runtime_seconds": time.perf_counter() - started,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": manifest["status"],
        "real_seed_runs": len(real_summary),
        "real_scenario_runs": len(real_results),
        "scaling_runs": len(scaling_results),
        "outputs": manifest["outputs"],
        "manifest": str(manifest_path),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
