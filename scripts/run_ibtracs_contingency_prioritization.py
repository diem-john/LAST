"""Build Phase 7J branch and storm priorities and representative contingencies.

Inputs are Phase 7I sensitivity outputs plus the canonical IEEE-33 case. The
script maps synthetic branch IDs to case endpoints, measures ranking stability,
ranks historical storm peak events when the Phase 7I event-level file is
available, and evaluates deterministic top-risk branch combinations as
topology-only contingencies. These combinations are screening scenarios, not
joint-probability samples or operational switching plans.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from grid.reconfiguration import load_case
from grid.weather_faults import build_branch_contingency

ROOT = Path(__file__).resolve().parents[1]


def build_branch_priority(
    ranking: pd.DataFrame, case: dict, *, top_k: int = 10
) -> pd.DataFrame:
    required = {
        "run_id", "wind_adjustment_knots", "rmw_km", "pole_spacing_m",
        "branch_id", "mean_peak_failure_probability", "max_peak_failure_probability",
        "storm_event_count",
    }
    missing = required - set(ranking.columns)
    if missing:
        raise ValueError(f"Branch ranking file missing columns: {sorted(missing)}")
    branch_map = {
        int(row["branch_id"]): row for row in case["branch"]
        if bool(row.get("in_service", False))
    }
    rows = ranking.copy()
    rows["branch_id"] = pd.to_numeric(rows["branch_id"], errors="raise").astype(int)
    unknown = set(rows["branch_id"]) - set(branch_map)
    if unknown:
        raise ValueError(f"Branch ranking contains unknown/inactive branch IDs: {sorted(unknown)}")
    rows["rank_within_run"] = rows.groupby("run_id")[
        "mean_peak_failure_probability"
    ].rank(method="min", ascending=False)
    grouped = rows.groupby("branch_id").agg(
        mean_peak_failure_probability=("mean_peak_failure_probability", "mean"),
        max_peak_failure_probability=("max_peak_failure_probability", "max"),
        mean_rank_across_runs=("rank_within_run", "mean"),
        top10_run_count=("rank_within_run", lambda x: int((x <= min(10, len(x))).sum())),
        configuration_count=("run_id", "nunique"),
        storm_event_count=("storm_event_count", "min"),
    ).reset_index()
    grouped["top10_configuration_fraction"] = (
        grouped["top10_run_count"] / grouped["configuration_count"]
    )
    grouped = grouped.sort_values(
        ["mean_peak_failure_probability", "max_peak_failure_probability", "branch_id"],
        ascending=[False, False, True], kind="stable"
    ).reset_index(drop=True)
    grouped.insert(0, "overall_risk_rank", np.arange(1, len(grouped) + 1))
    grouped["from_bus"] = grouped["branch_id"].map(lambda value: int(branch_map[value]["from_bus"]))
    grouped["to_bus"] = grouped["branch_id"].map(lambda value: int(branch_map[value]["to_bus"]))
    grouped["branch_status"] = grouped["branch_id"].map(lambda value: str(branch_map[value].get("status", "")))
    grouped["top_k_candidate"] = grouped["overall_risk_rank"] <= top_k
    return grouped


def build_representative_contingencies(
    branch_priority: pd.DataFrame,
    case: dict,
    *,
    top_k: int = 10,
    max_failed_branches: int = 3,
) -> pd.DataFrame:
    if top_k < 1 or max_failed_branches < 1:
        raise ValueError("top_k and max_failed_branches must be positive")
    candidates = branch_priority.head(top_k).to_dict(orient="records")
    active_bus_count = len(case["bus"])
    records = []
    for size in range(1, min(max_failed_branches, len(candidates)) + 1):
        for combination in itertools.combinations(candidates, size):
            failed_ids = sorted(int(row["branch_id"]) for row in combination)
            result = build_branch_contingency(case, failed_ids)
            deenergized = result["deenergized_buses"]
            disconnected_count = len(deenergized)
            risk_sum = float(sum(row["mean_peak_failure_probability"] for row in combination))
            risk_max = float(max(row["mean_peak_failure_probability"] for row in combination))
            records.append({
                "contingency_id": f"7J-C{len(records)+1:04d}",
                "failed_branch_ids": json.dumps(failed_ids),
                "failed_branch_count": len(failed_ids),
                "failed_branch_endpoints": json.dumps([
                    {"branch_id": int(row["branch_id"]),
                     "from_bus": int(row["from_bus"]), "to_bus": int(row["to_bus"])}
                    for row in combination
                ]),
                "mean_branch_risk_sum": risk_sum,
                "maximum_component_mean_risk": risk_max,
                "deenergized_bus_count": disconnected_count,
                "deenergized_bus_ids": json.dumps(deenergized),
                "connected_component_count": int(result["component_count"]),
                "slack_connected_bus_count": len(result["slack_connected_buses"]),
                "deenergized_bus_fraction": disconnected_count / active_bus_count,
                "topology_only": True,
                "electrical_power_flow_validated": False,
            })
    frame = pd.DataFrame(records)
    # Separate impact and risk dimensions; priority is transparent and not called a probability.
    frame = frame.sort_values(
        ["deenergized_bus_count", "connected_component_count",
         "mean_branch_risk_sum", "failed_branch_count", "failed_branch_ids"],
        ascending=[False, False, False, True, True], kind="stable"
    ).reset_index(drop=True)
    frame.insert(0, "topology_impact_rank", np.arange(1, len(frame) + 1))
    frame["priority_tier"] = pd.cut(
        frame["topology_impact_rank"],
        bins=[0, max(1, int(np.ceil(len(frame) * 0.1))),
              max(2, int(np.ceil(len(frame) * 0.3))), len(frame)],
        labels=["critical", "high", "screening"],
        include_lowest=True,
        duplicates="drop",
    ).astype(str)
    return frame


def rank_storm_events(events: pd.DataFrame) -> pd.DataFrame:
    required = {
        "wind_adjustment_knots", "rmw_km", "pole_spacing_m",
        "storm_instance_id", "event_timestamp_utc", "network_peak_wind_ms",
        "expected_failed_branch_count", "max_branch_failure_probability",
    }
    missing = required - set(events.columns)
    if missing:
        raise ValueError(f"Event ranking file missing columns: {sorted(missing)}")
    grouped = events.groupby("storm_instance_id").agg(
        event_count=("event_timestamp_utc", "count"),
        mean_peak_wind_ms=("network_peak_wind_ms", "mean"),
        maximum_peak_wind_ms=("network_peak_wind_ms", "max"),
        mean_expected_failed_branches=("expected_failed_branch_count", "mean"),
        maximum_expected_failed_branches=("expected_failed_branch_count", "max"),
        mean_max_branch_probability=("max_branch_failure_probability", "mean"),
        maximum_branch_probability=("max_branch_failure_probability", "max"),
        configuration_count=("rmw_km", "count"),
    ).reset_index()
    grouped = grouped.sort_values(
        ["maximum_expected_failed_branches", "maximum_branch_probability",
         "maximum_peak_wind_ms", "storm_instance_id"],
        ascending=[False, False, False, True], kind="stable"
    ).reset_index(drop=True)
    grouped.insert(0, "storm_priority_rank", np.arange(1, len(grouped) + 1))
    return grouped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branch-ranking", type=Path,
        default=ROOT / "reports/ibtracs/phase_7i/phase_7i_branch_risk_ranking.csv")
    parser.add_argument("--event-ranking", type=Path,
        default=ROOT / "reports/ibtracs/phase_7i/phase_7i_event_ranking.csv")
    parser.add_argument("--case", type=Path,
        default=ROOT / "data/electrical/ieee33bw_reference.json")
    parser.add_argument("--output-dir", type=Path,
        default=ROOT / "reports/ibtracs/phase_7j")
    parser.add_argument("--top-k-branches", type=int, default=10)
    parser.add_argument("--max-failed-branches", type=int, default=3)
    args = parser.parse_args()
    for path in (args.branch_ranking, args.case):
        if not path.exists():
            parser.error(f"Required input does not exist: {path}")
    if args.event_ranking.exists() is False:
        parser.error(
            f"Event-level ranking file not found: {args.event_ranking}. "
            "Rerun the updated Phase 7I sensitivity script to generate it."
        )
    case = load_case(args.case)
    ranking = pd.read_csv(args.branch_ranking)
    events = pd.read_csv(args.event_ranking)
    branch_priority = build_branch_priority(ranking, case, top_k=args.top_k_branches)
    contingencies = build_representative_contingencies(
        branch_priority, case, top_k=args.top_k_branches,
        max_failed_branches=args.max_failed_branches,
    )
    storm_priority = rank_storm_events(events)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    branch_path = args.output_dir / "phase_7j_branch_priority.csv"
    storm_path = args.output_dir / "phase_7j_storm_priority.csv"
    contingency_path = args.output_dir / "phase_7j_representative_contingencies.csv"
    manifest_path = args.output_dir / "phase_7j_manifest.json"
    branch_priority.to_csv(branch_path, index=False, encoding="utf-8-sig")
    storm_priority.to_csv(storm_path, index=False, encoding="utf-8-sig")
    contingencies.to_csv(contingency_path, index=False, encoding="utf-8-sig")
    manifest = {
        "status": "phase_7j_prioritization_completed",
        "inputs": {
            "branch_ranking": str(args.branch_ranking),
            "event_ranking": str(args.event_ranking),
            "case": str(args.case),
        },
        "design": {
            "top_k_branches": args.top_k_branches,
            "max_failed_branches_per_representative_combination": args.max_failed_branches,
            "representative_combination_count": int(len(contingencies)),
            "storm_count": int(len(storm_priority)),
        },
        "semantics": {
            "branch_risk": "mean of per-configuration mean peak-event model probabilities",
            "storm_priority": "ranking of historical peak events aggregated across Phase 7I parameter configurations",
            "representative_contingencies": "deterministic combinations of top-ranked branches; not sampled joint probabilities",
            "topology": "IEEE-33 graph connectivity only",
            "electrical_power_flow_validated": False,
            "fragility_calibration": "uncalibrated literature reference",
            "geometry": "synthetic branch geometry",
        },
        "outputs": {
            "branch_priority": str(branch_path),
            "storm_priority": str(storm_path),
            "representative_contingencies": str(contingency_path),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": manifest["status"],
        "branch_count": int(len(branch_priority)),
        "storm_count": int(len(storm_priority)),
        "representative_contingency_count": int(len(contingencies)),
        "outputs": manifest["outputs"],
        "manifest": str(manifest_path),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
