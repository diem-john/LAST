"""Phase 7K: derive minimal bus-isolation cut sets and topology-only restoration candidates.

Inputs are Phase 7J representative contingencies and the canonical IEEE-33 case.
A cut set is minimal *for a particular bus* when no strict subset among the
screened contingencies disconnects that bus. Restoration candidates close one
normally-open tie only when it increases slack-reachable buses. No power-flow,
protection, switching-sequence, or operational feasibility is implied.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _components(case: dict, failed_branch_ids: set[int], closed_ties: set[int] | None = None):
    closed_ties = closed_ties or set()
    adjacency = {int(row["bus_id"]): set() for row in case["bus"]}
    for branch in case["branch"]:
        bid = int(branch["branch_id"])
        active = bool(branch.get("in_service", False)) and bid not in failed_branch_ids
        active = active or bid in closed_ties
        if active:
            u, v = int(branch["from_bus"]), int(branch["to_bus"])
            adjacency[u].add(v)
            adjacency[v].add(u)
    components, seen = [], set()
    for start in sorted(adjacency):
        if start in seen:
            continue
        stack, component = [start], set()
        seen.add(start)
        while stack:
            node = stack.pop()
            component.add(node)
            for nxt in adjacency[node] - seen:
                seen.add(nxt)
                stack.append(nxt)
        components.append(component)
    slack = int(case["base"]["slack_bus"])
    slack_component = next((c for c in components if slack in c), {slack})
    deenergized = sorted(set(adjacency) - slack_component)
    return components, sorted(slack_component), deenergized


def _json_list(value) -> list:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, list):
        raise ValueError("Expected a JSON list in contingency field")
    return parsed


def derive_minimal_bus_cut_sets(contingencies: pd.DataFrame) -> pd.DataFrame:
    required = {"contingency_id", "failed_branch_ids", "deenergized_bus_ids"}
    missing = required - set(contingencies.columns)
    if missing:
        raise ValueError(f"Contingency file missing columns: {sorted(missing)}")
    entries = []
    for row in contingencies.to_dict(orient="records"):
        failed = frozenset(int(x) for x in _json_list(row["failed_branch_ids"]))
        buses = [int(x) for x in _json_list(row["deenergized_bus_ids"])]
        for bus in buses:
            entries.append({
                "contingency_id": str(row["contingency_id"]),
                "failed_branch_ids": json.dumps(sorted(failed)),
                "failed_branch_count": len(failed),
                "isolated_bus_id": bus,
                "deenergized_bus_count": len(buses),
                "topology_only": True,
            })
    frame = pd.DataFrame(entries)
    if frame.empty:
        return pd.DataFrame(columns=[
            "cut_set_id", "contingency_id", "failed_branch_ids",
            "failed_branch_count", "isolated_bus_id", "deenergized_bus_count",
            "topology_only",
        ])
    failed_sets = [frozenset(json.loads(x)) for x in frame["failed_branch_ids"]]
    minimal = []
    for idx, current in enumerate(failed_sets):
        bus = int(frame.iloc[idx]["isolated_bus_id"])
        dominated = any(
            other < current and int(frame.iloc[j]["isolated_bus_id"]) == bus
            for j, other in enumerate(failed_sets)
        )
        minimal.append(not dominated)
    result = frame.loc[minimal].copy().reset_index(drop=True)
    result.insert(0, "cut_set_id", [f"7K-MCS-{i:04d}" for i in range(1, len(result) + 1)])
    return result


def build_unique_outage_states(contingencies: pd.DataFrame, case: dict) -> pd.DataFrame:
    bus_map = {int(row["bus_id"]): row for row in case["bus"]}
    grouped = {}
    for row in contingencies.to_dict(orient="records"):
        buses = sorted(int(x) for x in _json_list(row["deenergized_bus_ids"]))
        key = tuple(buses)
        grouped.setdefault(key, []).append(row)
    rows = []
    for idx, (bus_ids, cases) in enumerate(sorted(grouped.items(), key=lambda item: (len(item[0]), item[0]))):
        representative = min(
            cases,
            key=lambda r: (
                int(r["failed_branch_count"]),
                -float(r.get("mean_branch_risk_sum", 0.0)),
                str(r["contingency_id"]),
            ),
        )
        p_kw = sum(float(bus_map[b].get("p_kw", 0) or 0) for b in bus_ids)
        q_kvar = sum(float(bus_map[b].get("q_kvar", 0) or 0) for b in bus_ids)
        rows.append({
            "outage_state_id": f"7K-STATE-{idx+1:04d}",
            "representative_contingency_id": str(representative["contingency_id"]),
            "representative_failed_branch_ids": json.dumps(sorted(
                int(x) for x in _json_list(representative["failed_branch_ids"])
            )),
            "equivalent_contingency_count": len(cases),
            "deenergized_bus_ids": json.dumps(list(bus_ids)),
            "deenergized_bus_count": len(bus_ids),
            "deenergized_load_kw": p_kw,
            "deenergized_load_kvar": q_kvar,
            "topology_only": True,
            "load_values_from_ieee33_reference_case": True,
        })
    return pd.DataFrame(rows)


def build_restoration_candidates(states: pd.DataFrame, case: dict) -> pd.DataFrame:
    bus_map = {int(row["bus_id"]): row for row in case["bus"]}
    total_p = sum(float(row.get("p_kw", 0) or 0) for row in case["bus"])
    total_q = sum(float(row.get("q_kvar", 0) or 0) for row in case["bus"])
    ties = [b for b in case["branch"]
            if not bool(b.get("in_service", False)) and "tie" in str(b.get("status", "")).lower()]
    rows = []
    for state in states.to_dict(orient="records"):
        failed = set(int(x) for x in json.loads(state["representative_failed_branch_ids"]))
        initial_components, initial_slack, initial_deenergized = _components(case, failed)
        initial_p = total_p - sum(float(bus_map[b].get("p_kw", 0) or 0) for b in initial_deenergized)
        initial_q = total_q - sum(float(bus_map[b].get("q_kvar", 0) or 0) for b in initial_deenergized)
        for tie in ties:
            tie_id = int(tie["branch_id"])
            _, slack_after, deenergized_after = _components(case, failed, {tie_id})
            restored = sorted(set(initial_deenergized) - set(deenergized_after))
            if len(slack_after) <= len(initial_slack):
                continue
            restored_p = sum(float(bus_map[b].get("p_kw", 0) or 0) for b in restored)
            restored_q = sum(float(bus_map[b].get("q_kvar", 0) or 0) for b in restored)
            rows.append({
                "restoration_candidate_id": f"{state['outage_state_id']}-TIE-{tie_id}",
                "outage_state_id": state["outage_state_id"],
                "representative_contingency_id": state["representative_contingency_id"],
                "failed_branch_ids": state["representative_failed_branch_ids"],
                "candidate_tie_branch_id": tie_id,
                "tie_from_bus": int(tie["from_bus"]),
                "tie_to_bus": int(tie["to_bus"]),
                "initial_slack_connected_bus_count": len(initial_slack),
                "restored_bus_ids": json.dumps(restored),
                "restored_bus_count": len(restored),
                "remaining_deenergized_bus_ids": json.dumps(deenergized_after),
                "remaining_deenergized_bus_count": len(deenergized_after),
                "restored_load_kw": restored_p,
                "restored_load_kvar": restored_q,
                "estimated_served_load_after_kw": initial_p + restored_p,
                "estimated_served_load_after_kvar": initial_q + restored_q,
                "component_count_after_tie_close": len(_components(case, failed, {tie_id})[0]),
                "topology_only": True,
                "power_flow_validated": False,
                "protection_and_switching_constraints_validated": False,
            })
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contingencies", type=Path,
        default=ROOT / "reports/ibtracs/phase_7j/phase_7j_representative_contingencies.csv")
    parser.add_argument("--case", type=Path, default=ROOT / "data/electrical/ieee33bw_reference.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports/ibtracs/phase_7k")
    args = parser.parse_args()
    for path in (args.contingencies, args.case):
        if not path.exists():
            parser.error(f"Required input does not exist: {path}")
    contingencies = pd.read_csv(args.contingencies)
    case = json.loads(args.case.read_text(encoding="utf-8"))
    minimal = derive_minimal_bus_cut_sets(contingencies)
    states = build_unique_outage_states(contingencies, case)
    restoration = build_restoration_candidates(states, case)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "minimal_bus_cut_sets": args.output_dir / "phase_7k_minimal_bus_cut_sets.csv",
        "unique_outage_states": args.output_dir / "phase_7k_unique_outage_states.csv",
        "restoration_candidates": args.output_dir / "phase_7k_restoration_candidates.csv",
    }
    minimal.to_csv(outputs["minimal_bus_cut_sets"], index=False, encoding="utf-8-sig")
    states.to_csv(outputs["unique_outage_states"], index=False, encoding="utf-8-sig")
    restoration.to_csv(outputs["restoration_candidates"], index=False, encoding="utf-8-sig")
    manifest = {
        "status": "phase_7k_scenario_preparation_completed",
        "inputs": {"contingencies": str(args.contingencies), "case": str(args.case)},
        "counts": {
            "screened_contingencies": int(len(contingencies)),
            "minimal_bus_cut_set_records": int(len(minimal)),
            "unique_outage_states": int(len(states)),
            "restoration_candidates": int(len(restoration)),
        },
        "semantics": {
            "minimality": "minimal branch-failure set per isolated bus among supplied screened contingencies only",
            "outage_states": "grouped by exact slack-disconnected bus set",
            "restoration_candidates": "single normally-open tie closure retained only if it increases slack-reachable bus count",
            "load": "benchmark IEEE-33 nominal bus loads; not real Chiayi/Taipower customer load",
            "limitations": [
                "topology-only; no AC power-flow validation",
                "no voltage, thermal, protection, fault-current, or switching-sequence constraints",
                "single-tie closure candidates only; no multi-switch sequence search",
                "does not model BESS, distributed generation, or load priorities",
                "synthetic grid mapping and uncalibrated upstream fragility assumptions remain unchanged",
            ],
        },
        "outputs": {key: str(value) for key, value in outputs.items()},
    }
    manifest_path = args.output_dir / "phase_7k_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": manifest["status"], **manifest["counts"],
                      "outputs": manifest["outputs"], "manifest": str(manifest_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
