from __future__ import annotations

import importlib.util
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "visualize_ieee33_minxiong_placement.py"
SPEC = importlib.util.spec_from_file_location("visualize_ieee33_minxiong_placement", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_nonincident_connector_crossing_is_detected():
    branches = gpd.GeoDataFrame(
        {"branch_id": [1, 2], "from_bus": [1, 3], "to_bus": [2, 4]},
        geometry=[
            LineString([(0, 0), (2, 2)]),
            LineString([(0, 2), (2, 0)]),
        ], crs="EPSG:3826",
    )
    crossings = MODULE.count_nonincident_connector_crossings(branches)
    assert len(crossings) == 1
    assert crossings[0]["intersection_type"] == "nonincident_point_crossing"


def test_shared_endpoint_is_not_flagged_as_nonincident_crossing():
    branches = gpd.GeoDataFrame(
        {"branch_id": [1, 2], "from_bus": [1, 2], "to_bus": [2, 3]},
        geometry=[
            LineString([(0, 0), (1, 1)]),
            LineString([(1, 1), (2, 0)]),
        ], crs="EPSG:3826",
    )
    assert MODULE.count_nonincident_connector_crossings(branches) == []


def test_layer_validation_checks_bus_count_and_cluster_containment():
    cluster = gpd.GeoDataFrame(
        {"cluster_id": ["Q05_cluster_001"]},
        geometry=[Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])],
        crs="EPSG:3826",
    )
    buses = gpd.GeoDataFrame(
        {"bus_id": list(range(1, 34)), "bus_role": ["synthetic"] * 33},
        geometry=[Point(10 + i, 10 + i) for i in range(33)], crs="EPSG:3826",
    )
    branches = gpd.GeoDataFrame(
        {"branch_id": list(range(1, 33)), "from_bus": list(range(1, 33)),
         "to_bus": list(range(2, 34))},
        geometry=[LineString([(i, i), (i + 1, i + 1)]) for i in range(1, 33)],
        crs="EPSG:3826",
    )
    result = MODULE.validate_layers(cluster, buses, branches)
    assert result["bus_count"] == 33
    assert result["branch_count"] == 32
    assert result["all_bus_points_within_cluster"]
    assert result["unique_bus_coordinates"] == 33
