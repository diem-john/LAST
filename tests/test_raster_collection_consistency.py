import json

import numpy as np
import pytest

from forecasting.data.raster_consistency import audit_raster_collection_consistency


def test_raster_collection_finds_exact_duplicates_but_not_same_grid_differences(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    names = ["flooded", "duration", "clear_views", "clear_perc", "jrc_perm_water"]
    base = np.array([
        [[1.0, 0.0], [np.nan, 1.0]],
        [[2.0, 0.0], [np.nan, 2.0]],
        [[3.0, 3.0], [np.nan, 3.0]],
        [[80.0, 90.0], [np.nan, 85.0]],
        [[0.0, 1.0], [np.nan, 0.0]],
    ], dtype="float32")

    paths = [
        tmp_path / "event_a" / "event_a.tif",
        tmp_path / "event_b" / "event_b.tif",
        tmp_path / "event_c" / "event_c.tif",
    ]
    properties = [
        {"id": 1, "began": "2001-01-01", "ended": "2001-01-02"},
        {"id": 2, "began": "2002-01-01", "ended": "2002-01-02"},
        {"id": 3, "began": "2003-01-01", "ended": "2003-01-02"},
    ]
    for index, path in enumerate(paths):
        path.parent.mkdir()
        data = base.copy()
        if index == 2:
            data[0, 0, 0] = 0.0
        with rasterio.open(
            path, "w", driver="GTiff", height=2, width=2, count=5,
            dtype="float32", crs="EPSG:4326",
            transform=from_origin(120, 24, 0.1, 0.1),
        ) as dst:
            dst.write(data)
            for band_index, name in enumerate(names, start=1):
                dst.set_band_description(band_index, name)
        (path.parent / f"{path.parent.name}_properties.json").write_text(
            json.dumps(properties[index]), encoding="utf-8"
        )

    report = audit_raster_collection_consistency(paths, window_size=1)
    assert report["raster_count"] == 3
    assert len(report["pairwise_comparisons"]) == 3
    assert len(report["exact_duplicate_pairs"]) == 1
    duplicate = report["exact_duplicate_pairs"][0]
    assert duplicate["event_a"]["id"] == 1
    assert duplicate["event_b"]["id"] == 2
    assert duplicate["event_a"]["began"] != duplicate["event_b"]["began"]
    same_grid_different_data = [
        pair for pair in report["pairwise_comparisons"]
        if {pair["event_a"]["id"], pair["event_b"]["id"]} == {1, 3}
    ][0]
    assert same_grid_different_data["same_grid_and_metadata"] is True
    assert same_grid_different_data["same_band_values_and_masks"] is False
    assert same_grid_different_data["exact_duplicate"] is False
