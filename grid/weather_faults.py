"""Weather-driven probabilistic branch-fault scenario generation for LAST-Q.

Consumes the Phase 6B asset-feature CSV. The spatial association inherits the
limitations documented by scripts/map_weather_features_to_ieee33.py: bus points
are synthetic and branch points are straight-line midpoint samples, not surveyed
asset locations or conductor corridors.

Fragility parameters are external configuration and must be calibrated before
probabilities are interpreted as empirical outage probabilities.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

REQUIRED_COLUMNS = {
    "timestamp_utc", "variable", "value", "unit", "asset_type", "asset_id",
    "branch_id", "spatial_scope", "temporal_semantics",
    "sample_location_semantics",
}


def load_fragility_config(path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("schema_version") != 1:
        raise ValueError("Fragility config schema_version must be 1")
    hazards = config.get("hazards")
    if not isinstance(hazards, dict) or not hazards:
        raise ValueError("Fragility config must define at least one hazard")
    for name, spec in hazards.items():
        curve = spec.get("fragility", {})
        midpoint, scale = curve.get("midpoint"), curve.get("scale")
        if not isinstance(midpoint, (int, float)) or not isinstance(scale, (int, float)) or scale <= 0:
            raise ValueError(f"Hazard {name!r} needs numeric fragility midpoint and positive scale")
        if not spec.get("variables"):
            raise ValueError(f"Hazard {name!r} must define source variables")
        if not spec.get("unit_conversions"):
            raise ValueError(f"Hazard {name!r} must define explicit unit conversions")
    return config


def _read_features(path: str | Path, *, include_regional: bool) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Weather asset-feature CSV missing columns: {sorted(missing)}")
        rows = []
        for row in reader:
            if row["asset_type"] != "branch_sample" or not row.get("branch_id"):
                continue
            if row["spatial_scope"] == "regional" and not include_regional:
                continue
            if row["spatial_scope"] not in {"point", "regional"}:
                raise ValueError(f"Unsupported spatial_scope: {row['spatial_scope']!r}")
            try:
                value = float(row["value"])
                branch_id = int(float(row["branch_id"]))
            except (TypeError, ValueError):
                # Null measurements remain absent; they are never converted to zero.
                continue
            if not math.isfinite(value):
                continue
            row["value"] = value
            row["branch_id"] = branch_id
            rows.append(row)
    if not rows:
        raise ValueError("No usable branch weather features found; check mapping output and regional policy")
    return rows


def _convert_value(row: dict[str, Any], hazard: dict[str, Any]) -> float | None:
    variable = str(row["variable"])
    if variable not in set(hazard["variables"]):
        return None
    conversions = hazard["unit_conversions"]
    unit = str(row["unit"]).strip()
    if unit not in conversions:
        raise ValueError(
            f"No explicit unit conversion for {variable!r} unit {unit!r}; "
            "add a verified conversion to the fragility config"
        )
    return float(row["value"]) * float(conversions[unit])


def _logistic_failure_probability(value: float, curve: dict[str, Any]) -> float:
    midpoint, scale = float(curve["midpoint"]), float(curve["scale"])
    z = max(-60.0, min(60.0, (value - midpoint) / scale))
    return 1.0 / (1.0 + math.exp(-z))


def _hazard_observations(rows: Iterable[dict[str, Any]], config: dict[str, Any]) -> dict[tuple[str, str, int], dict[str, float]]:
    """Aggregate features by (timestamp, temporal semantics, branch).

    Duplicate source observations for one hazard use the maximum converted value.
    ERA5 u10/v10 are combined as vector magnitude when both are present.
    """
    hazards = config["hazards"]
    grouped: dict[tuple[str, str, int], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    wind_components: dict[tuple[str, str, int], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        key = (str(row["timestamp_utc"]), str(row["temporal_semantics"]), int(row["branch_id"]))
        variable = str(row["variable"])
        if variable in {"u10", "v10"}:
            if str(row["unit"]).strip() not in {"m s-1", "m/s"}:
                raise ValueError(f"ERA5 {variable} requires m s-1 or m/s, got {row['unit']!r}")
            wind_components[key][variable].append(float(row["value"]))
        for hazard_name, spec in hazards.items():
            converted = _convert_value(row, spec)
            if converted is not None:
                grouped[key][hazard_name].append(converted)
    for key, components in wind_components.items():
        if "wind_speed" not in hazards:
            continue
        if components.get("u10") and components.get("v10"):
            u = max(components["u10"], key=abs)
            v = max(components["v10"], key=abs)
            grouped[key]["wind_speed"].append(math.hypot(u, v))
    return {
        key: {name: max(values) for name, values in items.items() if values}
        for key, items in grouped.items()
    }


def calculate_branch_failure_probabilities(
    mapped_features_csv: str | Path,
    fragility_config: dict[str, Any],
    *,
    include_regional: bool = False,
) -> list[dict[str, Any]]:
    """Calculate per-branch, per-time failure probabilities from mapped features."""
    rows = _read_features(mapped_features_csv, include_regional=include_regional)
    observations = _hazard_observations(rows, fragility_config)
    if not observations:
        raise ValueError(
            "No configured hazard measurements found for branch samples. "
            "Rainfall is not a direct branch-failure driver in this model; "
            "configure a validated derived hazard such as flood_depth first."
        )
    semantics_by_key = {
        (r["timestamp_utc"], r["temporal_semantics"], r["branch_id"]): r for r in rows
    }
    sources_by_key: dict[tuple[str, str, int], set[str]] = defaultdict(set)
    for row in rows:
        key = (row["timestamp_utc"], row["temporal_semantics"], row["branch_id"])
        sources_by_key[key].add(str(row.get("source_id", "unknown")))
    output = []
    for (timestamp, semantics, branch_id), exposures in sorted(observations.items()):
        hazard_probabilities = {}
        for hazard_name, value in exposures.items():
            hazard_probabilities[hazard_name] = _logistic_failure_probability(
                value, fragility_config["hazards"][hazard_name]["fragility"]
            )
        # Conditional independence across hazard mechanisms is an explicit v1 assumption.
        combined = 1.0 - math.prod(1.0 - p for p in hazard_probabilities.values())
        source_row = semantics_by_key[(timestamp, semantics, branch_id)]
        output.append({
            "timestamp_utc": timestamp,
            "temporal_semantics": semantics,
            "branch_id": branch_id,
            "asset_id": source_row["asset_id"],
            "source_ids": sorted(sources_by_key[(timestamp, semantics, branch_id)]),
            "hazard_exposures": exposures,
            "hazard_failure_probabilities": hazard_probabilities,
            "combined_failure_probability": combined,
            "spatial_scope": source_row["spatial_scope"],
            "sample_location_semantics": source_row["sample_location_semantics"],
            "fragility_model_status": fragility_config.get("model_status", "unspecified"),
        })
    return output


def generate_fault_scenarios(
    branch_probabilities: list[dict[str, Any]],
    *,
    samples_per_timestamp: int = 1,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Draw reproducible independent Bernoulli branch outages for each timestamp."""
    if samples_per_timestamp < 1:
        raise ValueError("samples_per_timestamp must be at least 1")
    import random

    rng = random.Random(seed)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in branch_probabilities:
        groups[(row["timestamp_utc"], row["temporal_semantics"])].append(row)
    scenarios = []
    for (timestamp, semantics), assets in sorted(groups.items()):
        assets = sorted(assets, key=lambda item: int(item["branch_id"]))
        for sample_index in range(samples_per_timestamp):
            failed = [
                int(asset["branch_id"]) for asset in assets
                if rng.random() < float(asset["combined_failure_probability"])
            ]
            scenarios.append({
                "scenario_id": f"WX-{len(scenarios) + 1:06d}",
                "timestamp_utc": timestamp,
                "temporal_semantics": semantics,
                "sample_index": sample_index,
                "random_seed": seed,
                "failed_branch_ids": failed,
                "failed_branch_count": len(failed),
                "branch_failure_probabilities": [
                    {"branch_id": int(asset["branch_id"]),
                     "probability": float(asset["combined_failure_probability"])}
                    for asset in assets
                ],
                "fragility_model_status": assets[0]["fragility_model_status"],
                "sampling_assumption": "independent_bernoulli_across_branches_and_hazards",
            })
    return scenarios


def build_branch_contingency(case: dict[str, Any], failed_branch_ids: Iterable[int]) -> dict[str, Any]:
    """Apply branch outages to the canonical case and report resulting components."""
    failed = {int(branch_id) for branch_id in failed_branch_ids}
    known = {int(branch["branch_id"]): branch for branch in case["branch"]}
    unknown = failed - set(known)
    if unknown:
        raise ValueError(f"Unknown branch IDs: {sorted(unknown)}")
    ties = {
        branch_id for branch_id, branch in known.items()
        if str(branch.get("status", "")).startswith("normally_open_tie")
    }
    invalid_ties = failed & ties
    if invalid_ties:
        raise ValueError(f"Fault scenario must not mark normally-open ties as failed: {sorted(invalid_ties)}")
    inactive = {
        branch_id for branch_id in failed if not bool(known[branch_id].get("in_service", False))
    }
    if inactive:
        raise ValueError(f"Fault scenario includes already inactive branches: {sorted(inactive)}")

    active_buses = {int(bus["bus_id"]) for bus in case["bus"]}
    surviving = [
        branch for branch in case["branch"]
        if bool(branch.get("in_service", False))
        and int(branch["branch_id"]) not in failed
    ]
    adjacency = {bus: set() for bus in active_buses}
    for branch in surviving:
        u, v = int(branch["from_bus"]), int(branch["to_bus"])
        adjacency[u].add(v)
        adjacency[v].add(u)
    components = []
    unseen = set(active_buses)
    while unseen:
        root = min(unseen)
        stack, component = [root], set()
        unseen.remove(root)
        while stack:
            node = stack.pop()
            component.add(node)
            for neighbor in adjacency[node] & unseen:
                unseen.remove(neighbor)
                stack.append(neighbor)
        components.append(sorted(component))
    components.sort(key=lambda values: values[0])
    slack = int(case["base"]["slack_bus"])
    slack_component = next(component for component in components if slack in component)
    energized = set(slack_component)
    return {
        "failed_branch_ids": sorted(failed),
        "surviving_closed_branch_ids": sorted(
            int(branch["branch_id"]) for branch in surviving
        ),
        "connected_components": components,
        "component_count": len(components),
        "slack_bus": slack,
        "slack_connected_buses": sorted(energized),
        "deenergized_buses": sorted(active_buses - energized),
        "topology_only": True,
        "electrical_power_flow_validated": False,
    }
