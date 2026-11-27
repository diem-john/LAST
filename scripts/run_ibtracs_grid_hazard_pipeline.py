"""Run the complete IBTrACS-to-grid weather contingency research pipeline.

Phases 7B-7D reuse the existing track/regional/exposure modules. Phases 7E-7H
reconstruct parametric winds, evaluate synthetic grid samples, apply a clearly
uncalibrated literature-reference fragility curve, and sample topology-only
contingencies. Source wind semantics must be explicitly configured first.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from forecasting.data.ibtracs_exposure import build_exposure_outputs
from forecasting.data.ibtracs_regions import write_regional_outputs
from forecasting.data.ibtracs_tracks import (
    build_ibtracs_tracks,
    load_synthetic_bus_locations,
    write_ibtracs_outputs,
)
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
from grid.reconfiguration import load_case

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-dir", type=Path, default=ROOT / "data/ibtracs/metadata")
    parser.add_argument("--bus-locations", type=Path, default=ROOT / "reports/geospatial/minxiong_cluster_001_ieee33_bus_locations.csv")
    parser.add_argument("--case", type=Path, default=ROOT / "data/electrical/ieee33bw_reference.json")
    parser.add_argument("--wind-config", type=Path, default=ROOT / "config/ibtracs_wind_field.json")
    parser.add_argument("--fragility-config", type=Path, default=ROOT / "config/ibtracs_wind_fragility.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports/ibtracs")
    parser.add_argument("--taiwan-radius-km", type=float, default=500.0)
    parser.add_argument("--minxiong-radius-km", type=float, default=300.0)
    parser.add_argument("--branch-samples", type=int, default=5)
    parser.add_argument("--samples-per-storm", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--allow-uncalibrated-sensitivity", action="store_true",
                        help="Explicitly permit the uncalibrated literature-reference fragility curve for research sensitivity scenarios.")
    args = parser.parse_args()

    # Validate all external assumptions before writing outputs.
    wind_config = json.loads(args.wind_config.read_text(encoding="utf-8"))
    validate_wind_config(wind_config)
    fragility_config = load_wind_fragility_config(args.fragility_config)
    if fragility_config["calibration_status"] != "locally_calibrated" and not args.allow_uncalibrated_sensitivity:
        parser.error(
            "Fragility is not locally calibrated. Re-run with "
            "--allow-uncalibrated-sensitivity only for explicitly labelled research sensitivity scenarios."
        )

    case = load_case(args.case)
    buses = load_synthetic_bus_locations(args.bus_locations)
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)

    # 7B — normalize source per-storm metadata.
    tracks, rejected, summaries, track_audit = build_ibtracs_tracks(
        args.metadata_dir, bus_locations_csv=args.bus_locations
    )
    write_ibtracs_outputs(tracks, rejected, summaries, track_audit, output)

    # 7C — regional screening. Full tracks retained for qualifying storms.
    regional_dir = output / "regional"
    regional_audit = write_regional_outputs(
        tracks, regional_dir, taiwan_radius_km=args.taiwan_radius_km,
        minxiong_radius_km=args.minxiong_radius_km,
    )
    minxiong_tracks = pd.read_csv(
        regional_dir / "ibtracs_minxiong_synthetic_grid_approach_tracks.csv",
        low_memory=False,
    )

    # 7D — closest observed approaches and spatial screening bins.
    exposure_dir = output / "exposure"
    exposure_audit = build_exposure_outputs(
        tracks, exposure_dir, taiwan_radius_km=args.taiwan_radius_km,
        minxiong_radius_km=args.minxiong_radius_km,
    )

    # 7E — parametric wind-field reconstruction at each selected storm observation.
    wind_dir = output / "wind"
    wind_dir.mkdir(parents=True, exist_ok=True)
    wind_tracks = prepare_wind_track_parameters(minxiong_tracks, wind_config)
    wind_tracks.to_csv(wind_dir / "ibtracs_wind_field_track_parameters.csv",
                       index=False, encoding="utf-8-sig")

    # 7F — evaluate wind at 33 synthetic bus points and branch sample points.
    bus_assets, branch_samples = build_synthetic_grid_samples(
        buses, case, samples_per_branch=args.branch_samples
    )
    asset_exposure = evaluate_grid_wind_exposure(
        wind_tracks, bus_assets, branch_samples, wind_config
    )
    asset_exposure.to_csv(wind_dir / "ibtracs_grid_asset_wind_exposure.csv",
                          index=False, encoding="utf-8-sig")

    # 7G — reference fragility; pole spacing and branch lengths remain assumptions.
    branch_lengths = estimate_synthetic_branch_lengths(buses, case)
    branch_fragility = calculate_branch_wind_fragility(
        asset_exposure, branch_lengths, fragility_config
    )
    fragility_path = wind_dir / "ibtracs_branch_fragility_probabilities.csv"
    branch_fragility.to_csv(fragility_path, index=False, encoding="utf-8-sig")

    # 7H — choose each storm's peak network-wind snapshot and sample contingencies.
    peak = select_peak_network_snapshot(branch_fragility)
    scenarios, event_rows = sample_weather_contingencies(
        peak, case, samples_per_storm=args.samples_per_storm, seed=args.seed
    )
    (wind_dir / "ibtracs_peak_storm_events.csv").write_text(
        pd.DataFrame(event_rows).to_csv(index=False), encoding="utf-8"
    )
    scenario_payload = {
        "schema_version": 1,
        "status": "research_sensitivity_contingencies_generated",
        "scenario_count": len(scenarios),
        "event_count": len(event_rows),
        "samples_per_storm": args.samples_per_storm,
        "random_seed": args.seed,
        "wind_model": wind_tracks["wind_model"].iloc[0] if not wind_tracks.empty else None,
        "wind_model_status": wind_config.get("model_status"),
        "fragility_model_status": fragility_config["calibration_status"],
        "fragility_calibration_note": fragility_config.get("calibration_note", ""),
        "scenario_semantics": "sampled branch contingencies at each storm's maximum synthetic-network wind snapshot",
        "limitations": [
            "Local per-storm metadata provenance, wind units, averaging period, and reference height must be verified; configuration values are user-supplied assumptions.",
            "Wind field uses a parametric Willoughby-style profile with fixed assumed RMW and translation asymmetry; no local wind observations are assimilated.",
            "No terrain, surface roughness, topographic speed-up, rainfall, flooding, or storm-surge coupling is modeled.",
            "Bus coordinates and branch straight-line sample points are synthetic, not verified Taipower assets or conductor corridors.",
            "Pole failure curve is literature-reference and uncalibrated; pole spacing and counts are geometric assumptions.",
            "Conditional independence assumptions omit residual spatial and temporal failure correlation.",
            "Contingencies report topology only; no voltage, thermal, protection, load-flow, or restoration feasibility is validated.",
            "Input tracks are historical best-track observations, not forecasts.",
        ],
        "scenarios": scenarios,
    }
    scenario_path = wind_dir / "ibtracs_weather_contingency_scenarios.json"
    scenario_path.write_text(json.dumps(scenario_payload, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")

    audit = {
        "status": "ibtracs_to_grid_contingency_pipeline_completed",
        "phases": {
            "7B_track_processing": track_audit,
            "7C_regional_screening": regional_audit,
            "7D_closest_approach": exposure_audit,
            "7E_wind_field": {
                "track_observation_count": int(len(wind_tracks)),
                "positive_wind_observation_count": int(wind_tracks["vmax_ms"].notna().sum()),
                "wind_config": wind_config,
                "model": "Willoughby et al. (2006) radial profile plus Miyazaki (1962) translation asymmetry",
            },
            "7F_grid_exposure": {
                "bus_asset_count": int(len(bus_assets)),
                "branch_sample_point_count": int(len(branch_samples)),
                "exposure_record_count": int(len(asset_exposure)),
                "branch_samples_per_branch": int(args.branch_samples),
                "branch_sample_semantics": "maximum wind over equally spaced interior points on synthetic straight-line bus-to-bus segments",
            },
            "7G_fragility": {
                "record_count": int(len(branch_fragility)),
                "fragility_config": fragility_config,
                "status": fragility_config["calibration_status"],
            },
            "7H_contingencies": {
                "event_count": len(event_rows),
                "scenario_count": len(scenarios),
                "samples_per_storm": int(args.samples_per_storm),
                "random_seed": int(args.seed),
            },
        },
        "outputs": {
            "track_wind_parameters": str(wind_dir / "ibtracs_wind_field_track_parameters.csv"),
            "grid_asset_wind_exposure": str(wind_dir / "ibtracs_grid_asset_wind_exposure.csv"),
            "branch_fragility_probabilities": str(fragility_path),
            "peak_storm_events": str(wind_dir / "ibtracs_peak_storm_events.csv"),
            "weather_contingencies": str(scenario_path),
        },
    }
    (wind_dir / "ibtracs_to_grid_contingency_audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": audit["status"],
        "phase_7b_storms": track_audit["storm_instance_count"],
        "phase_7c_minxiong_storms": regional_audit["results"]["minxiong_synthetic_grid_approach"]["storm_count"],
        "phase_7e_wind_observations": int(len(wind_tracks)),
        "phase_7f_asset_exposure_records": int(len(asset_exposure)),
        "phase_7g_fragility_records": int(len(branch_fragility)),
        "phase_7h_events": len(event_rows),
        "phase_7h_scenarios": len(scenarios),
        "fragility_model_status": fragility_config["calibration_status"],
        "scenario_output": str(scenario_path),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
