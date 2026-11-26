"""Run the first LAST-Q QAOA experiment for the Bus 6 contingency."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from grid.reconfiguration import evaluate_reconfiguration, load_case
from quantum.optimization.classical_baseline import solve_qubo_exact
from quantum.optimization.qubo_formulation import build_tie_restoration_qubo
from quantum.optimization.qaoa_optimizer import optimize_qaoa

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASE = ROOT / "data" / "electrical" / "ieee33bw_reference.json"
DEFAULT_OUTPUT = ROOT / "reports" / "quantum" / "lastq_bus6_qaoa.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, default=DEFAULT_CASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--target", type=str, default=None,
                        help="CUDA-Q target, e.g. qpp-cpu or nvidia. Default: CUDA-Q default.")
    parser.add_argument("--shots", type=int, default=2048)
    parser.add_argument("--layers", type=int, default=1)
    parser.add_argument("--max-iterations", type=int, default=60)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    case = load_case(args.case)
    qubo = build_tie_restoration_qubo(case, faulted_buses=(6,))
    exact = solve_qubo_exact(qubo)
    qaoa = optimize_qaoa(
        qubo,
        layers=args.layers,
        shots=args.shots,
        max_iterations=args.max_iterations,
        seed=args.seed,
        target=args.target,
    )

    sampled = qaoa["final_sample"]
    feasible_shots = 0
    feasible_samples = []
    for row in sampled["distribution"]:
        topology = evaluate_reconfiguration(
            case, (6,), row["selected_branch_ids"]
        )
        row["topology_feasible"] = topology["feasible_topology"]
        if topology["feasible_topology"]:
            feasible_shots += row["count"]
            feasible_samples.append(row)

    qaoa["final_sample"]["topology_feasible_shots"] = feasible_shots
    qaoa["final_sample"]["topology_feasible_probability"] = (
        feasible_shots / sampled["total_shots"]
    )
    qaoa["final_sample"]["best_feasible_sample"] = (
        min(feasible_samples, key=lambda row: (row["qubo_energy"], -row["count"]))
        if feasible_samples else None
    )
    qaoa["classical_exact_reference"] = {
        "optimal_energy": exact["best_energy"],
        "minimizer_count": exact["minimizer_count"],
        "optimal_tie_sets": exact["all_minimizing_bitstrings"],
        "states_evaluated": exact["states_evaluated"],
        "sampled_optimum_probability": sum(
            row["probability"] for row in sampled["distribution"]
            if abs(row["qubo_energy"] - exact["best_energy"]) < 1e-9
        ),
    }
    qaoa["experiment_scope"] = (
        "Five-qubit topology-only Bus 6 tie-restoration QUBO. "
        "Not an AC power-flow or operational feasibility result."
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(qaoa, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "qaoa_completed",
        "target": qaoa["target"],
        "qubits": qaoa["qubit_count"],
        "layers": qaoa["qaoa_layers"],
        "optimizer_success": qaoa["optimizer_success"],
        "best_sampled_energy": sampled["best_sampled_energy"],
        "sampled_expected_energy": sampled["expected_qubo_energy"],
        "exact_final_expectation": qaoa["exact_final_expectation"],
        "optimization_runtime_seconds": qaoa["optimization_runtime_seconds"],
        "final_sampling_runtime_seconds": qaoa["final_sampling_runtime_seconds"],
        "topology_feasible_probability": qaoa["final_sample"][
            "topology_feasible_probability"
        ],
        "sampled_optimum_probability": qaoa["classical_exact_reference"][
            "sampled_optimum_probability"
        ],
        "output": str(args.output.resolve()),
    }, indent=2))


if __name__ == "__main__":
    main()
