"""Topology-level reconfiguration utilities for LAST-Q.

This module deliberately separates graph feasibility from electrical feasibility.
It does not perform AC power flow, voltage, thermal, protection, or BESS checks.
"""
from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy
from typing import Iterable


def load_case(path):
    """Load a canonical LAST electrical case JSON file."""
    import json
    from pathlib import Path

    return json.loads(Path(path).read_text(encoding="utf-8"))


def get_bus_ids(case) -> set[int]:
    return {int(row["bus_id"]) for row in case["bus"]}


def get_normally_open_ties(case) -> list[dict]:
    """Return normally-open tie branches in stable branch-ID order."""
    ties = [
        branch for branch in case["branch"]
        if str(branch.get("status", "")).lower().startswith("normally_open_tie")
        or (not bool(branch.get("in_service", False)) and branch.get("status") != "faulted")
    ]
    return sorted(ties, key=lambda row: int(row["branch_id"]))


def build_post_contingency_network(case, faulted_buses: Iterable[int]):
    """Remove faulted buses and all incident in-service branches.

    Returns active buses, surviving closed branches, and the components before
    any normally-open tie is closed.
    """
    faulted = {int(bus) for bus in faulted_buses}
    all_buses = get_bus_ids(case)
    unknown = faulted - all_buses
    if unknown:
        raise ValueError(f"Unknown faulted bus IDs: {sorted(unknown)}")

    active_buses = all_buses - faulted
    surviving_branches = []
    for branch in case["branch"]:
        if not bool(branch.get("in_service", False)):
            continue
        u, v = int(branch["from_bus"]), int(branch["to_bus"])
        if u in active_buses and v in active_buses:
            surviving_branches.append(branch)

    components = connected_components(active_buses, surviving_branches)
    return active_buses, surviving_branches, components


def connected_components(bus_ids: Iterable[int], branches: Iterable[dict]) -> list[set[int]]:
    """Compute undirected connected components for a bus/branch collection."""
    adjacency = {int(bus): set() for bus in bus_ids}
    for branch in branches:
        u, v = int(branch["from_bus"]), int(branch["to_bus"])
        if u in adjacency and v in adjacency:
            adjacency[u].add(v)
            adjacency[v].add(u)

    components = []
    unseen = set(adjacency)
    while unseen:
        root = min(unseen)
        queue = deque([root])
        component = set()
        unseen.remove(root)
        while queue:
            node = queue.popleft()
            component.add(node)
            for neighbor in adjacency[node]:
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    queue.append(neighbor)
        components.append(component)
    return sorted(components, key=lambda comp: min(comp))


def _component_index(components: list[set[int]]) -> dict[int, int]:
    return {bus: index for index, component in enumerate(components) for bus in component}


def evaluate_reconfiguration(
    case,
    faulted_buses: Iterable[int],
    closed_tie_ids: Iterable[int],
    slack_bus: int | None = None,
) -> dict:
    """Evaluate connectivity and radiality after a contingency and tie closures."""
    faulted = {int(bus) for bus in faulted_buses}
    active_buses, surviving, pre_components = build_post_contingency_network(case, faulted)
    tie_by_id = {int(row["branch_id"]): row for row in get_normally_open_ties(case)}
    selected = {int(branch_id) for branch_id in closed_tie_ids}

    unknown_ties = selected - set(tie_by_id)
    if unknown_ties:
        raise ValueError(f"Unknown or non-tie branch IDs selected: {sorted(unknown_ties)}")

    selected_branches = []
    for branch_id in sorted(selected):
        branch = tie_by_id[branch_id]
        u, v = int(branch["from_bus"]), int(branch["to_bus"])
        if u not in active_buses or v not in active_buses:
            raise ValueError(
                f"Tie {branch_id} is incident to a faulted or inactive bus ({u}, {v})"
            )
        selected_branches.append(branch)

    all_closed = surviving + selected_branches
    components = connected_components(active_buses, all_closed)
    connected = len(components) == 1
    edge_count = len(all_closed)
    radial = connected and edge_count == len(active_buses) - 1

    # A connected undirected graph is a tree exactly when |E| = |V| - 1.
    slack = int(slack_bus if slack_bus is not None else case["base"]["slack_bus"])
    if slack not in active_buses:
        raise ValueError("Slack bus is faulted or inactive")

    adjacency = defaultdict(set)
    for branch in all_closed:
        u, v = int(branch["from_bus"]), int(branch["to_bus"])
        adjacency[u].add(v)
        adjacency[v].add(u)
    energized = set()
    queue = deque([slack])
    energized.add(slack)
    while queue:
        node = queue.popleft()
        for neighbor in adjacency[node]:
            if neighbor not in energized:
                energized.add(neighbor)
                queue.append(neighbor)

    deenergized = active_buses - energized
    return {
        "faulted_buses": sorted(faulted),
        "selected_tie_branch_ids": sorted(selected),
        "pre_contingency_component_count": len(pre_components),
        "pre_contingency_components": [sorted(c) for c in pre_components],
        "post_reconfiguration_component_count": len(components),
        "post_reconfiguration_components": [sorted(c) for c in components],
        "active_bus_count": len(active_buses),
        "closed_branch_count": edge_count,
        "connected_to_slack": not deenergized,
        "connected": connected,
        "radial": radial,
        "feasible_topology": connected and radial,
        "energized_buses": sorted(energized),
        "deenergized_buses": sorted(deenergized),
        "topology_only": True,
        "electrical_power_flow_validated": False,
    }


def enumerate_tie_configurations(case, faulted_buses: Iterable[int]) -> list[dict]:
    """Enumerate every normally-open tie combination and evaluate topology."""
    from itertools import product

    ties = get_normally_open_ties(case)
    results = []
    for bits in product((0, 1), repeat=len(ties)):
        selected = [
            int(tie["branch_id"])
            for tie, bit in zip(ties, bits)
            if bit
        ]
        result = evaluate_reconfiguration(case, faulted_buses, selected)
        result["decision_bits"] = list(bits)
        results.append(result)
    return results
