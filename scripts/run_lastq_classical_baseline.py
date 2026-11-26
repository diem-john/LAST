"""Run the first LAST-Q classical QUBO baseline for the Bus 6 contingency."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from grid.reconfiguration import load_case, enumerate_tie_configurations
from quantum.optimization.qubo_formulation import build_tie_restoration_qubo
from quantum.optimization.classical_baseline import run_bus6_classical_baseline

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASE = ROOT / "data" / "electrical" / "ieee33bw_reference.json"
DEFAULT_OUTPUT = ROOT / "reports" / "quantum" / "lastq_bus6_classical_baseline.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, default=DEFAULT_CASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    case = load_case(args.case)
    qubo = build_tie_restoration_qubo(case, faulted_buses=(6,))
    result = run_bus6_classical_baseline(case, qubo, faulted_buses=(6,))
    topology_states = enumerate_tie_configurations(case, faulted_buses=(6,))
    result["full_topology_enumeration"] = {
        "states_evaluated": len(topology_states),
        "feasible_state_count": sum(
            bool(row["feasible_topology"]) for row in topology_states
        ),
        "feasible_tie_sets": [
            row["selected_tie_branch_ids"]
            for row in topology_states if row["feasible_topology"]
        ],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "topology_baseline_complete"
            if result["topology_validation_passed"] else "topology_baseline_failed",
        "variables": qubo.variables,
        "states_evaluated": result["solution"]["states_evaluated"],
        "best_energy": result["solution"]["best_energy"],
        "minimizer_count": result["solution"]["minimizer_count"],
        "selected_tie_branch_ids": result["solution"]["selected_branch_ids"],
        "feasible_topology": result["topology_validation_passed"],
        "electrical_power_flow_validated": False,
        "output": str(args.output.resolve()),
    }, indent=2))


if __name__ == "__main__":
    main()
