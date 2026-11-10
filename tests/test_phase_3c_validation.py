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
