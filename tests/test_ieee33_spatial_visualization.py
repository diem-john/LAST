from __future__ import annotations
import importlib.util
from pathlib import Path
import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon
MODULE_PATH=Path(__file__).resolve().parents[1]/"scripts"/"visualize_ieee33_minxiong_placement.py"
SPEC=importlib.util.spec_from_file_location("visualize_ieee33_minxiong_placement",MODULE_PATH)
MODULE=importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)

def test_topology_layout_is_complete_and_rooted_at_bus_one():
    pos=MODULE.topology_layer_positions([1,2,3,4,5],[(1,2),(2,3),(3,4),(2,5)])
    assert set(pos)=={1,2,3,4,5}
    assert pos[1][0]==0 and pos[2][0]==1 and pos[3][0]==2 and pos[4][0]==3 and pos[5][0]==2

def test_topology_layout_rejects_disconnected_graph():
    try: MODULE.topology_layer_positions([1,2,3],[(1,2)])
    except ValueError as exc: assert "connected" in str(exc)
    else: raise AssertionError("Expected disconnected topology to fail")

def test_layer_validation_checks_bus_count_and_cluster_containment():
    cluster=gpd.GeoDataFrame({"cluster_id":["Q05_cluster_001"]},
      geometry=[Polygon([(0,0),(100,0),(100,100),(0,100)])],crs="EPSG:3826")
    buses=gpd.GeoDataFrame({"bus_id":list(range(1,34)),"bus_role":["synthetic"]*33},
      geometry=[Point(10+i,10+i) for i in range(33)],crs="EPSG:3826")
    branches=gpd.GeoDataFrame({"branch_id":list(range(1,33)),"from_bus":list(range(1,33)),
      "to_bus":list(range(2,34))},geometry=[LineString([(i,i),(i+1,i+1)]) for i in range(1,33)],crs="EPSG:3826")
    result=MODULE.validate_layers(cluster,buses,branches)
    assert result["bus_count"]==33 and result["branch_count"]==32
    assert result["all_bus_points_within_cluster"] and result["unique_bus_coordinates"]==33
