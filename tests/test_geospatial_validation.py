from __future__ import annotations

import hashlib
import json
from pathlib import Path

import geopandas as gpd
import networkx as nx
from shapely.geometry import Point

from forecasting.geospatial.validation import run_validation, validate_road_graph, validate_vector


def test_validate_vector_checks_crs_geometry_and_transform(tmp_path: Path) -> None:
    path = tmp_path / "points.gpkg"
    gpd.GeoDataFrame({"name": ["A", "B"]},
        geometry=[Point(120.4, 23.5), Point(120.5, 23.6)],
        crs="EPSG:4326").to_file(path, driver="GPKG")
    report = validate_vector(path)
    assert report["technical_valid"] is True
    assert report["layers"][0]["feature_count"] == 2
    assert report["layers"][0]["invalid_geometry_count"] == 0
    assert report["layers"][0]["transform_to_target_crs_ok"] is True


def test_validate_road_graph_checks_coordinates_and_components(tmp_path: Path) -> None:
    path = tmp_path / "roads.graphml"
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node("1", x=120.4, y=23.5)
    graph.add_node("2", x=120.5, y=23.6)
    graph.add_edge("1", "2", length=100.0)
    nx.write_graphml(graph, path)
    report = validate_road_graph(path)
    assert report["technical_valid"] is True
    assert report["node_count"] == 2
    assert report["edge_count"] == 1
    assert report["nodes_missing_xy"] == 0


def test_run_validation_updates_manifest_and_writes_report(tmp_path: Path) -> None:
    path = tmp_path / "points.gpkg"
    gpd.GeoDataFrame({"name": ["A"]}, geometry=[Point(120.4, 23.5)],
                     crs="EPSG:4326").to_file(path, driver="GPKG")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"sources": [{
        "source_id": "sample_points", "status": "acquired_unvalidated",
        "file_paths": ["points.gpkg"], "sha256": {"points.gpkg": digest},
    }]}), encoding="utf-8")
    report = tmp_path / "reports/validation_report.json"
    result = run_validation(manifest, tmp_path, report)
    updated = json.loads(manifest.read_text(encoding="utf-8"))
    assert result["passed_count"] == 1
    assert updated["sources"][0]["status"] == "validated"
    assert report.is_file()
    assert updated["status"] == "acquisition_and_technical_validation_complete"


def test_run_validation_flags_hash_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "points.gpkg"
    gpd.GeoDataFrame({"name": ["A"]}, geometry=[Point(120.4, 23.5)],
                     crs="EPSG:4326").to_file(path, driver="GPKG")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"sources": [{
        "source_id": "sample_points", "status": "acquired_unvalidated",
        "file_paths": ["points.gpkg"], "sha256": {"points.gpkg": "0" * 64},
    }]}), encoding="utf-8")
    result = run_validation(manifest, tmp_path, tmp_path / "validation.json")
    assert result["failed_count"] == 1
    assert "SHA-256 mismatch: points.gpkg" in result["sources"][0]["errors"]
