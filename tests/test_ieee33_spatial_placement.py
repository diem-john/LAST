from __future__ import annotations

import importlib.util
from pathlib import Path

from shapely.geometry import Point

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "place_ieee33_minxiong_cluster.py"
SPEC = importlib.util.spec_from_file_location("place_ieee33_minxiong_cluster", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_ieee33_topology_has_33_nodes_and_32_unique_branches():
    edges = MODULE.IEEE33_BRANCHES
    nodes = {node for edge in edges for node in edge}
    assert len(edges) == 32
    assert len(set(edges)) == 32
    assert nodes == set(range(1, 34))
    assert (1, 2) in edges


def test_farthest_point_selection_is_deterministic_and_unique():
    candidates = [Point(x, y) for x, y in [
        (0, 0), (10, 0), (20, 0), (30, 0), (40, 0),
        (0, 10), (10, 10), (20, 10), (30, 10), (40, 10),
    ]]
    first = MODULE.select_spread_points(candidates, Point(1, 1), count=5)
    second = MODULE.select_spread_points(candidates, Point(1, 1), count=5)
    assert [(p.x, p.y) for p in first] == [(p.x, p.y) for p in second]
    assert len({(p.x, p.y) for p in first}) == 5


def test_farthest_point_selection_rejects_too_few_candidates():
    candidates = [Point(0, 0), Point(1, 0)]
    try:
        MODULE.select_spread_points(candidates, Point(0, 0), count=3)
    except ValueError as exc:
        assert "Need at least 3" in str(exc)
    else:
        raise AssertionError("Expected insufficient-candidate validation to fail")


def test_ieee33_topology_is_a_connected_acyclic_tree():
    assert MODULE.topology_is_tree(MODULE.IEEE33_BRANCHES)
    assert not MODULE.topology_is_tree(((1, 2), (2, 3), (3, 1)))
    assert not MODULE.topology_is_tree(((1, 2), (3, 4)))
