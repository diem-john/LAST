"""Run Phase 7I sensitivity analysis for wind and pole-spacing assumptions.

Uses already screened Minxiong tracks and recomputes Phases 7E-7H for each
combination of wind offset, RMW, and assumed pole spacing. Outputs compact
aggregate tables rather than retaining every Monte Carlo scenario.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd

from forecasting.physics.tropical_cyclone_wind import (
    prepare_wind_track_parameters,
    validate_wind_config,
)
from grid.ibtracs_fragility import (
    calculate_branch_wind_fragility,
    estimate_synthetic_branch_lengths,
    load_wind_fragility_config,
    sample_weather_contingencies,
    select_peak_network_snapshot,
)
from grid.ibtracs_wind_exposure import (
    build_synthetic_grid_samples,
    evaluate_grid_wind_exposure,
)
from forecasting.data.ibtracs_tracks import load_synthetic_bus_locations
from grid.reconfiguration import load_case

ROOT = Path(__file__).resolve().parents[1]


def _csv_floats(value: str) -> list[float]:
    try:
        values = [float(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected comma-separated numeric values") from exc
    if not values or not np.isfinite(values).all() or any(item < 0 for item in values):
        raise argparse.ArgumentTypeError("Values must be finite, nonnegative, and non-empty")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tracks", type=Path,
        default=ROOT / "reports/ibtracs/regional/ibtracs_minxiong_synthetic_grid_approach_tracks.csv",
        help="Complete tracks for storms selected by the Minxiong synthetic-grid screen.",
    )
    parser.add_argument("--bus-locations", type=Path,
                        default=ROOT / "reports/geospatial/minxiong_cluster_001_ieee33_bus_locations.csv")
    parser.add_argument("--case", type=Path, default=ROOT / "data/electrical/ieee33bw_reference.json")
    parser.add_argument("--wind-config", type=Path, default=ROOT / "config/ibtracs_wind_field.json")
    parser.add_argument("--fragility-config", type=Path, default=ROOT / "config/ibtracs_wind_fragility.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports/ibtracs/phase_7i")
    parser.add_argument("--wind-adjustments-knots", type=_csv_floats, default=[0.0, 15.0])
    parser.add_argument("--rmw-km", type=_csv_floats, default=[20.0, 30.0, 40.0])
    parser.add_argument("--pole-spacing-m", type=_csv_floats, default=[40.0, 50.0, 60.0])
    parser.add_argument("--branch-samples", type=int, default=5)
    parser.add_argument("--samples-per-storm", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--allow-uncalibrated-sensitivity", action="store_true")
    args = parser.parse_args()

    if not args.allow_uncalibrated_sensitivity:
        parser.error("Use --allow-uncalibrated-sensitivity to acknowledge the uncalibrated reference fragility curve.")
    if args.samples_per_storm < 1 or args.branch_samples < 1:
        parser.error("samples-per-storm and branch-samples must be positive")
    for path in (args.tracks, args.bus_locations, args.case, args.wind_config, args.fragility_config):
        if not path.exists():
            parser.error(f"Required input does not exist: {path}")

    base_wind_config = json.loads(args.wind_config.read_text(encoding="utf-8"))
    validate_wind_config(base_wind_config)
    source = base_wind_config.get("source_fields", {})
    if not source.get("eligible_grade_values"):
        parser.error("Configure source_fields.eligible_grade_values before running sensitivity analysis.")
    base_fragility_config = load_wind_fragility_config(args.fragility_config)
    if base_fragility_config["calibration_status"] != "locally_calibrated" and not args.allow_uncalibrated_sensitivity:
        parser.error("Uncalibrated fragility requires explicit permission.")

    tracks = pd.read_csv(args.tracks, low_memory=False)
    if tracks.empty:
        parser.error("The selected Minxiong track file is empty.")
    grade_column = str(source.get("grade_column", "grade"))
    if grade_column not in tracks:
        parser.error(f"Track file does not contain grade column {grade_column!r}.")

    eligible_grades = [float(value) for value in source["eligible_grade_values"]]
    grade_values = pd.to_numeric(tracks[grade_column], errors="coerce")
    raw_wind = pd.to_numeric(tracks[str(source["wind_column"])], errors="coerce")
    grade_audit = {
        "total_selected_track_rows": int(len(tracks)),
        "grade_counts": {str(k): int(v) for k, v in grade_values.value_counts(dropna=False).items()},
        "eligible_grade_values": eligible_grades,
        "eligible_grade_rows": int(grade_values.isin(eligible_grades).sum()),
        "ineligible_grade_rows": int((~grade_values.isin(eligible_grades)).sum()),
        "zero_wind_rows": int(raw_wind.eq(0).sum()),
        "zero_wind_by_grade": {
            str(k): int(v) for k, v in grade_values[raw_wind.eq(0)].value_counts(dropna=False).items()
        },
    }

    case = load_case(args.case)
    buses = load_synthetic_bus_locations(args.bus_locations)
    bus_assets, branch_samples = build_synthetic_grid_samples(
        buses, case, samples_per_branch=args.branch_samples
    )
    branch_lengths = estimate_synthetic_branch_lengths(buses, case)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_rows: list[dict] = []
    branch_rows: list[dict] = []
    combinations = [
        (offset, rmw, spacing)
        for offset in args.wind_adjustments_knots
        for rmw in args.rmw_km
        for spacing in args.pole_spacing_m
    ]

    for run_index, (offset, rmw, spacing) in enumerate(combinations, start=1):
        wind_config = copy.deepcopy(base_wind_config)
        wind_config.setdefault("wind_adjustment", {})["value"] = float(offset)
        wind_config["wind_adjustment"]["unit"] = "knots"
        wind_config.setdefault("rmw", {})["rmw_km"] = float(rmw)

        fragility_config = copy.deepcopy(base_fragility_config)
        fragility_config["pole_spacing_m"] = float(spacing)

        wind_tracks = prepare_wind_track_parameters(tracks, wind_config)
        eligible_wind_tracks = int(wind_tracks["vmax_ms"].notna().sum())
        asset_exposure = evaluate_grid_wind_exposure(
            wind_tracks, bus_assets, branch_samples, wind_config
        )
        branch_fragility = calculate_branch_wind_fragility(
            asset_exposure, branch_lengths, fragility_config
        )
        peak = select_peak_network_snapshot(branch_fragility)
        scenarios, event_rows = sample_weather_contingencies(
            peak, case, samples_per_storm=args.samples_per_storm, seed=args.seed
        )
        if not scenarios:
            raise RuntimeError(
                f"No scenarios generated for offset={offset}, RMW={rmw}, spacing={spacing}"
            )

        failed_counts = np.asarray([s["failed_branch_count"] for s in scenarios], dtype=float)
        deenergized_counts = np.asarray([
            len(s["contingency"].get("deenergized_buses", [])) for s in scenarios
        ], dtype=float)
        component_counts = np.asarray([
            int(s["contingency"].get("component_count", 0)) for s in scenarios
        ], dtype=float)
        event_expected = np.asarray(
            [float(row["expected_failed_branch_count"]) for row in event_rows], dtype=float
        )
        summary_rows.append({
            "run_id": run_index,
            "wind_adjustment_knots": float(offset),
            "rmw_km": float(rmw),
            "pole_spacing_m": float(spacing),
            "selected_storm_count": int(tracks["storm_instance_id"].nunique()),
            "eligible_wind_observations": eligible_wind_tracks,
            "asset_exposure_records": int(len(asset_exposure)),
            "branch_fragility_records": int(len(branch_fragility)),
            "peak_events": int(len(event_rows)),
            "monte_carlo_scenarios": int(len(scenarios)),
            "mean_expected_failed_branches_per_event": float(event_expected.mean()),
            "mean_sampled_failed_branches": float(failed_counts.mean()),
            "probability_any_branch_failure": float(np.mean(failed_counts > 0)),
            "mean_deenergized_buses": float(deenergized_counts.mean()),
            "probability_any_deenergized_bus": float(np.mean(deenergized_counts > 0)),
            "p95_deenergized_buses": float(np.quantile(deenergized_counts, 0.95)),
            "mean_connected_components": float(component_counts.mean()),
            "max_branch_failure_probability": float(branch_fragility["branch_failure_probability"].max()),
            "fragility_model_status": str(fragility_config["calibration_status"]),
            "random_seed": int(args.seed),
        })

        branch_peak = peak.groupby("branch_id", as_index=False).agg(
            mean_peak_failure_probability=("branch_failure_probability", "mean"),
            max_peak_failure_probability=("branch_failure_probability", "max"),
            storm_event_count=("storm_instance_id", "nunique"),
        )
        for row in branch_peak.to_dict(orient="records"):
            branch_rows.append({
                "run_id": run_index,
                "wind_adjustment_knots": float(offset),
                "rmw_km": float(rmw),
                "pole_spacing_m": float(spacing),
                **row,
            })
        print(json.dumps({
            "run_id": run_index,
            "total_runs": len(combinations),
            "wind_adjustment_knots": offset,
            "rmw_km": rmw,
            "pole_spacing_m": spacing,
            "eligible_wind_observations": eligible_wind_tracks,
            "events": len(event_rows),
            "scenarios": len(scenarios),
        }))

    summary = pd.DataFrame(summary_rows)
    branch_ranking = pd.DataFrame(branch_rows)
    summary.to_csv(output_dir / "phase_7i_sensitivity_summary.csv", index=False, encoding="utf-8-sig")
    branch_ranking.to_csv(output_dir / "phase_7i_branch_risk_ranking.csv", index=False, encoding="utf-8-sig")
    manifest = {
        "status": "phase_7i_sensitivity_analysis_completed",
        "design": {
            "wind_adjustment_knots": args.wind_adjustments_knots,
            "rmw_km": args.rmw_km,
            "pole_spacing_m": args.pole_spacing_m,
            "combination_count": len(combinations),
            "samples_per_storm": args.samples_per_storm,
            "random_seed": args.seed,
            "branch_samples": args.branch_samples,
        },
        "grade_audit": grade_audit,
        "wind_model_status": base_wind_config.get("model_status"),
        "fragility_model_status": base_fragility_config.get("calibration_status"),
        "interpretation": "Conditional research sensitivity analysis only; not empirical failure probabilities, forecasts, or validated restoration outcomes.",
        "outputs": {
            "summary": str(output_dir / "phase_7i_sensitivity_summary.csv"),
            "branch_ranking": str(output_dir / "phase_7i_branch_risk_ranking.csv"),
        },
    }
    (output_dir / "phase_7i_sensitivity_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": manifest["status"],
        "combinations": len(combinations),
        "summary_output": str(output_dir / "phase_7i_sensitivity_summary.csv"),
        "branch_ranking_output": str(output_dir / "phase_7i_branch_risk_ranking.csv"),
        "manifest_output": str(output_dir / "phase_7i_sensitivity_manifest.json"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
