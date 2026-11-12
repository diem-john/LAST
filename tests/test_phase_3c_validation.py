import numpy as np
import pandas as pd
import pytest

from forecasting.data.physical_validation import audit_era5_physical_frame
from forecasting.data.quality import audit_raster_integrity


def test_era5_screening_flags_out_of_range_but_preserves_signed_flux():
    frame = pd.DataFrame({
        "t2m": [295.0, 400.0],
        "ssrd": [100.0, -1.5],
        "slhf": [-200.0, 50.0],
        "tcc": [0.2, 1.2],
    })
    report = audit_era5_physical_frame(frame)
    assert report["variables"]["t2m"]["above_screening_range"] == 1
    assert report["variables"]["ssrd"]["below_screening_range"] == 1
    assert report["variables"]["slhf"]["negative_finite_values"] == 1
    assert report["variables"]["slhf"]["review_required"] is False
    assert report["variables"]["tcc"]["above_screening_range"] == 1
    assert report["policy"].startswith("Diagnostics only")


def test_raster_integrity_separates_masked_and_unmasked_nonfinite(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    path = tmp_path / "integrity.tif"
    data = np.array([[0.0, 1.0], [np.nan, -9999.0]], dtype="float32")
    with rasterio.open(
        path, "w", driver="GTiff", height=2, width=2, count=1,
        dtype="float32", crs="EPSG:4326",
        transform=from_origin(120, 24, 0.1, 0.1), nodata=-9999.0,
    ) as dst:
        dst.write(data, 1)
        dst.set_band_description(1, "flooded")
    report = audit_raster_integrity(path, window_size=1)
    band = report["bands"][0]
    assert band["total_pixels"] == 4
    assert band["masked_or_nodata_pixels"] == 1
    assert band["finite_unmasked_pixels"] == 2
    assert band["nonfinite_unmasked_pixels"] == 1
    assert band["flooded_value_counts"] == {"0.0": 1, "1.0": 1}


def test_spatial_raster_coverage_maps_tiles_and_band_overlap(tmp_path):
    import json
    from forecasting.data.quality import audit_raster_spatial_coverage

    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    path = tmp_path / "DFO_9999_From_20100101_to_20100103.tif"
    properties = tmp_path / "DFO_9999_properties.json"
    properties.write_text(
        json.dumps({"id": 9999, "began": "2010-01-01", "ended": "2010-01-03"}),
        encoding="utf-8",
    )
    data = np.array([
        [[1.0, 0.0], [np.nan, 1.0]],
        [[np.nan, 1.0], [np.nan, 1.0]],
        [[2.0, 2.0], [np.nan, 2.0]],
        [[100.0, 100.0], [np.nan, 100.0]],
        [[0.0, 0.0], [np.nan, 0.0]],
    ], dtype="float32")
    names = ["flooded", "duration", "clear_views", "clear_perc", "jrc_perm_water"]
    with rasterio.open(
        path, "w", driver="GTiff", height=2, width=2, count=5,
        dtype="float32", crs="EPSG:4326",
        transform=from_origin(120, 24, 0.1, 0.1),
    ) as dst:
        dst.write(data)
        for index, name in enumerate(names, start=1):
            dst.set_band_description(index, name)

    report = audit_raster_spatial_coverage(
        path, window_size=1, overview_rows=2, overview_cols=2
    )
    assert report["event_properties_status"] == "loaded"
    assert report["event_properties"]["id"] == 9999
    assert report["band_summaries"][0]["finite"] == 3
    assert report["band_summaries"][1]["finite"] == 2
    assert report["band_summaries"][1]["nonfinite_unmasked"] == 2
    assert report["pairwise_finite_mask_overlap"][0]["finite_mask_jaccard"] == pytest.approx(2 / 3)
    assert report["spatial_overview"]["tiles"][1][0]["bands"][0]["finite"] == 0
    assert report["processing"]["values_reclassified"] is False
