from __future__ import annotations

import hashlib
import json
from pathlib import Path

from forecasting.geospatial.acquisition import (
    AcquisitionResult,
    load_config,
    run_acquisition,
    sha256_file,
    update_manifest,
)


def test_dry_run_does_not_create_output_or_manifest(tmp_path: Path) -> None:
    config = {
        "sources": [{
            "source_id": "test_osm",
            "adapter": "osmnx",
            "enabled": True,
            "provider": "test",
            "dataset_title": "Test source",
            "output_dir": "data/geospatial/raw/test",
            "place": "Chiayi County, Taiwan",
            "feature_kind": "roads",
        }]
    }
    results = run_acquisition(config, root=tmp_path, dry_run=True)
    assert len(results) == 1
    assert results[0].status == "planned_dry_run"
    assert not (tmp_path / "data/geospatial/raw/test").exists()
    manifest = tmp_path / "reports/geospatial/source_manifest.json"
    update_manifest(manifest, results, dry_run=True)
    assert not manifest.exists()


def test_disabled_sources_are_skipped() -> None:
    config = {"sources": [{"source_id": "disabled", "adapter": "http", "enabled": False}]}
    assert run_acquisition(config, root=Path("."), dry_run=True) == []


def test_manifest_merges_records_and_preserves_existing(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"sources": [{"theme": "older", "status": "validated"}]}), encoding="utf-8")
    result = AcquisitionResult(
        source_id="new_source", provider="test", dataset_title="New", adapter="http",
        status="acquired_unvalidated",
    )
    update_manifest(manifest, [result], dry_run=False)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert {item.get("theme") for item in payload["sources"]} == {"older", "new_source"}
    assert payload["schema_version"] == "1.1"


def test_sha256_file(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("LAST", encoding="utf-8")
    assert sha256_file(file_path) == hashlib.sha256(b"LAST").hexdigest()


def test_config_load_rejects_duplicate_ids(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"sources": [
        {"source_id": "duplicate"}, {"source_id": "duplicate"}
    ]}), encoding="utf-8")
    try:
        load_config(config_path)
    except ValueError as exc:
        assert "unique" in str(exc)
    else:
        raise AssertionError("Duplicate source IDs should be rejected")
