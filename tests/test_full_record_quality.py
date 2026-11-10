import numpy as np
import pandas as pd
import pytest

from forecasting.data.quality import (
    audit_frame_quality,
    audit_precipitation_frame,
    audit_ibtracs_quality,
    audit_raster_full,
)


def test_full_frame_quality_reports_missing_duplicates_and_cadence():
    frame = pd.DataFrame({
        "valid_time": [
            "2020-01-01 00:00:00",
            "2020-01-01 01:00:00",
            "2020-01-01 01:00:00",
            "2020-01-01 04:00:00",
        ],
        "temperature": [10.0, np.nan, 12.0, 14.0],
    })
    report = audit_frame_quality(frame, timestamp_column="valid_time", expected_frequency="1h")
    assert report["row_count"] == 4
    assert report["duplicate_timestamps"] == 1
    assert report["cadence"]["nonconforming_intervals"] == 1
    assert report["numeric_columns"]["temperature"]["missing_or_unparseable"] == 1


def test_nasa_power_naive_lst_is_not_relabelled_utc():
    frame = pd.DataFrame({
        "timestamp_lst": ["2020-01-01 00:00:00", "2020-01-01 01:00:00"],
        "ALLSKY_SFC_SW_DWN": [0.0, 12.5],
    })
    report = audit_frame_quality(
        frame, timestamp_column="timestamp_lst", expected_frequency="1h",
        timestamp_timezone="NAIVE",
    )
    assert report["timestamp_timezone"] == "NAIVE"
    assert report["observed_start"] == "2020-01-01T00:00:00"


def test_precipitation_quality_applies_fill_value_before_statistics():
    frame = pd.DataFrame({
        "timestamp": ["2010-01-01T00:00:00Z", "2010-01-01T03:00:00Z"],
        "value": [0.001, -9999.9],
    })
    report = audit_precipitation_frame(
        frame, source_id="TRMM_3B42_V7", fill_value=-9999.9
    )
    assert report["raw_value_profile"]["finite_count"] == 1
    assert report["precipitation_rate_mm_hr"]["max"] == pytest.approx(0.001)
    assert report["time_series"]["nonconforming_intervals"] == 0


def test_ibtracs_quality_aggregates_per_instance_metadata(tmp_path):
    pd.DataFrame({
        "year": [2010, 2010],
        "month": [1, 1],
        "day": [1, 1],
        "hour": [0, 3],
        "wind": [40.0, None],
    }).to_csv(tmp_path / "instance_a.csv", index=False)
    report = audit_ibtracs_quality(tmp_path)
    assert report["metadata_instance_count"] == 1
    assert report["total_metadata_rows"] == 2
    assert report["columns"]["wind"]["missing"] == 1
    assert report["instances"]["instance_a"]["invalid_timestamps"] == 0


def test_full_raster_audit_scans_all_pixels(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    path = tmp_path / "flood.tif"
    data = np.array([[0.0, 1.0], [np.nan, 1.0]], dtype="float32")
    with rasterio.open(
        path, "w", driver="GTiff", height=2, width=2, count=1,
        dtype="float32", crs="EPSG:4326", transform=from_origin(120, 24, 0.1, 0.1),
    ) as dst:
        dst.write(data, 1)
        dst.set_band_description(1, "flooded")
    report = audit_raster_full(path, window_size=1)
    assert report["bands"][0]["finite_pixels"] == 3
    assert report["bands"][0]["nonfinite_unmasked_pixels"] == 1
    assert report["flooded_band_value_counts"] == {"0.0": 1, "1.0": 2}
    assert report["asset_intersection_checked"] is False
