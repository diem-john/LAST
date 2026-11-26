"""Generate probabilistic branch outage scenarios from Phase 6B weather features."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from grid.reconfiguration import load_case
from grid.weather_faults import (
    build_branch_contingency,
    calculate_branch_failure_probabilities,
    generate_fault_scenarios,
    load_fragility_config,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=ROOT / "reports/environmental/ieee33_weather_asset_features.csv")
    parser.add_argument("--fragility-config", type=Path, default=ROOT / "config/weather_fragility_demo.json")
    parser.add_argument("--case", type=Path, default=ROOT / "data/electrical/ieee33bw_reference.json")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/environmental/weather_fault_scenarios.json")
    parser.add_argument("--samples-per-timestamp", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--include-regional", action="store_true", help="Include regional means broadcast to all synthetic assets")
    args = parser.parse_args()

    config = load_fragility_config(args.fragility_config)
    probabilities = calculate_branch_failure_probabilities(
        args.features, config, include_regional=args.include_regional
    )
    scenarios = generate_fault_scenarios(
        probabilities, samples_per_timestamp=args.samples_per_timestamp, seed=args.seed
    )
    case = load_case(args.case)
    for scenario in scenarios:
        scenario["contingency"] = build_branch_contingency(case, scenario["failed_branch_ids"])
    payload = {
        "schema_version": 1,
        "status": "weather_driven_probabilistic_branch_contingencies_generated",
        "fragility_model_status": config.get("model_status", "unspecified"),
        "fragility_model_note": config.get("calibration_note", ""),
        "scenario_count": len(scenarios),
        "branch_probability_record_count": len(probabilities),
        "samples_per_timestamp": args.samples_per_timestamp,
        "random_seed": args.seed,
        "regional_observations_included": args.include_regional,
        "limitations": [
            "The mapper uses synthetic bus coordinates and branch midpoint samples, not verified electrical asset locations or conductor corridors.",
            "Regional means are broadcast, not spatially downscaled; excluded by default.",
            "Only hazards and units explicitly configured in the fragility JSON contribute.",
            "Global Flood Database event rasters are not interpreted as flood depth by this module.",
            "Branch failures are independently sampled; spatially correlated failures are not yet modeled.",
            "Contingencies are topology-only; voltage, thermal, protection, and AC power-flow feasibility are not evaluated.",
        ],
        "branch_failure_probabilities": probabilities,
        "scenarios": scenarios,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in (
        "status", "fragility_model_status", "scenario_count", "branch_probability_record_count",
        "samples_per_timestamp", "random_seed", "regional_observations_included", "limitations"
    )}, indent=2))
    print(f"Output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
