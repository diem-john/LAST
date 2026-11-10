import pandas as pd
import pytest

from forecasting.data.audit import audit_ibtracs_instances


def test_ibtracs_instances_match_metadata_to_image_folder_and_keep_missing_refs(tmp_path):
    metadata_dir = tmp_path / "metadata"
    image_dir = tmp_path / "image"
    metadata_dir.mkdir()
    (image_dir / "storm_A").mkdir(parents=True)
    (image_dir / "storm_B").mkdir(parents=True)

    pd.DataFrame({
        "year": [2010, 2010],
        "file_1": ["present.h5", "missing.h5"],
    }).to_csv(metadata_dir / "storm_A.csv", index=False)
    pd.DataFrame({"year": [2011], "file_1": ["b.h5"]}).to_csv(
        metadata_dir / "storm_B.csv", index=False
    )
    (image_dir / "storm_A" / "present.h5").write_bytes(b"test")

    report = audit_ibtracs_instances(metadata_dir, image_dir)

    assert report["metadata_instance_count"] == 2
    assert report["image_folder_count"] == 2
    assert report["metadata_without_image_folder"] == []
    assert report["image_folders_without_metadata"] == []
    assert report["instances"]["storm_A"]["metadata_rows"] == 2
    assert report["instances"]["storm_A"]["missing_image_references"] == ["missing.h5"]
    assert report["instances"]["storm_A"]["image_h5_files_found"] == 1


def test_ibtracs_audit_reports_missing_folder_and_orphan_folder(tmp_path):
    metadata_dir = tmp_path / "metadata"
    image_dir = tmp_path / "image"
    metadata_dir.mkdir()
    image_dir.mkdir()
    pd.DataFrame({"year": [2012]}).to_csv(metadata_dir / "no_folder.csv", index=False)
    (image_dir / "orphan_folder").mkdir()

    report = audit_ibtracs_instances(metadata_dir, image_dir)

    assert report["metadata_without_image_folder"] == ["no_folder"]
    assert report["image_folders_without_metadata"] == ["orphan_folder"]


def test_raster_audit_excludes_nan_and_infinity(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    import numpy as np
    from rasterio.transform import from_origin
    from forecasting.data.audit import audit_raster

    path = tmp_path / "nonfinite.tif"
    values = np.array([[1.0, 2.0], [np.nan, np.inf]], dtype="float32")
    with rasterio.open(
        path, "w", driver="GTiff", height=2, width=2, count=1,
        dtype="float32", crs="EPSG:4326", transform=from_origin(0, 2, 1, 1),
    ) as dataset:
        dataset.write(values, 1)

    band = audit_raster(path)["bands"][0]
    assert band["sample_valid_pixels"] == 2
    assert band["sample_nonfinite_pixels"] == 2
    assert band["sample_min"] == 1.0
    assert band["sample_max"] == 2.0
