"""Schema-first audit utilities for heterogeneous LAST-FE source files."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
import pandas as pd
import numpy as np


def audit_csv(path: str | Path, *, sample_rows: int = 1000) -> dict[str, Any]:
    """Inspect CSV structure without assigning semantic meaning to columns."""
    source = Path(path)
    header = pd.read_csv(source, nrows=0)
    sample = pd.read_csv(source, nrows=sample_rows, low_memory=False)
    columns: dict[str, Any] = {}
    for name in sample.columns:
        series = sample[name]
        parsed_datetime = pd.to_datetime(series, errors="coerce", utc=True)
        datetime_ratio = float(parsed_datetime.notna().mean()) if len(series) else 0.0
        numeric = pd.to_numeric(series, errors="coerce")
        numeric_ratio = float(numeric.notna().mean()) if len(series) else 0.0
        item: dict[str, Any] = {
            "inferred_dtype": str(series.dtype),
            "sample_non_null": int(series.notna().sum()),
            "sample_null": int(series.isna().sum()),
            "numeric_parse_ratio": numeric_ratio,
            "datetime_parse_ratio_utc": datetime_ratio,
            "sample_values": [None if pd.isna(v) else str(v)[:120] for v in series.dropna().head(5)],
        }
        if numeric_ratio > 0:
            valid = numeric.dropna()
            item["numeric_sample_min"] = float(valid.min())
            item["numeric_sample_max"] = float(valid.max())
        columns[str(name)] = item
    return {
        "path": str(source), "size_bytes": source.stat().st_size,
        "sample_rows_read": int(len(sample)), "columns": columns,
        "note": "Dtype and parse ratios are sample-based; units and semantic roles require source documentation.",
    }


def audit_raster(path: str | Path) -> dict[str, Any]:
    """Inspect raster georeferencing and band metadata; does not infer flood depth."""
    try:
        import rasterio
    except ImportError as exc:
        raise RuntimeError("Raster audit requires optional dependency rasterio") from exc
    source = Path(path)
    with rasterio.open(source) as dataset:
        bands = []
        for index in range(1, dataset.count + 1):
            band = dataset.read(index, masked=True, out_shape=(min(dataset.height, 256), min(dataset.width, 256)))
            compressed = band.compressed()
            finite = compressed[np.isfinite(compressed)]
            bands.append({
                "index": index, "dtype": dataset.dtypes[index - 1],
                "nodata": dataset.nodata, "sample_valid_pixels": int(finite.size),
                "sample_nonfinite_pixels": int(compressed.size - finite.size),
                "sample_min": float(finite.min()) if finite.size else None,
                "sample_max": float(finite.max()) if finite.size else None,
                "description": dataset.descriptions[index - 1],
                "units": dataset.units[index - 1] if dataset.units else None,
            })
        bounds = dataset.bounds
        return {
            "path": str(source), "driver": dataset.driver,
            "width": dataset.width, "height": dataset.height, "band_count": dataset.count,
            "crs": str(dataset.crs) if dataset.crs else None,
            "transform": list(dataset.transform)[:6],
            "bounds": {"left": bounds.left, "bottom": bounds.bottom, "right": bounds.right, "top": bounds.top},
            "resolution": list(dataset.res), "bands": bands,
            "note": "Raster values are not interpreted as depth or asset exposure without product documentation and spatial validation.",
        }


def write_audit_report(report: dict[str, Any], output_path: str | Path) -> None:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def audit_ibtracs_instances(metadata_dir: str | Path, image_dir: str | Path) -> dict[str, Any]:
    """Audit per-instance IBTrACS metadata CSVs against matching image folders.

    CSV filename stem is the instance identifier. Image references are checked
    relative to that instance's image folder; missing files are reported, never
    used as a reason to discard metadata rows.
    """
    metadata_root, image_root = Path(metadata_dir), Path(image_dir)
    metadata_files = sorted(metadata_root.glob("*.csv")) if metadata_root.exists() else []
    image_folders = {p.name for p in image_root.iterdir() if p.is_dir()} if image_root.exists() else set()
    instances: dict[str, Any] = {}
    metadata_ids = {p.stem for p in metadata_files}

    for csv_path in metadata_files:
        instance_id = csv_path.stem
        frame = pd.read_csv(csv_path, low_memory=False)
        instance_image_dir = image_root / instance_id
        file_columns = [c for c in frame.columns if str(c).lower().startswith("file_")]
        references: list[str] = []
        for column in file_columns:
            references.extend(
                str(value).strip()
                for value in frame[column].dropna()
                if str(value).strip() and str(value).strip().lower() not in {"nan", "none"}
            )
        # Preserve order while avoiding repeated checks for repeated references.
        unique_references = list(dict.fromkeys(references))
        missing_references = [
            name for name in unique_references
            if not (instance_image_dir / Path(name).name).is_file()
        ]
        image_files = sorted(p.name for p in instance_image_dir.glob("*.h5")) if instance_image_dir.exists() else []
        instances[instance_id] = {
            "metadata_path": str(csv_path),
            "image_folder": str(instance_image_dir),
            "image_folder_exists": instance_image_dir.is_dir(),
            "metadata_rows": int(len(frame)),
            "columns": [str(c) for c in frame.columns],
            "file_reference_columns": [str(c) for c in file_columns],
            "unique_image_references": int(len(unique_references)),
            "missing_image_references": missing_references,
            "missing_image_reference_count": int(len(missing_references)),
            "image_h5_files_found": int(len(image_files)),
            "unreferenced_image_files": sorted(set(image_files) - set(unique_references)),
        }

    return {
        "metadata_directory": str(metadata_root),
        "image_directory": str(image_root),
        "metadata_instance_count": int(len(metadata_files)),
        "image_folder_count": int(len(image_folders)),
        "metadata_without_image_folder": sorted(metadata_ids - image_folders),
        "image_folders_without_metadata": sorted(image_folders - metadata_ids),
        "instances": instances,
        "note": "Each metadata CSV is one typhoon instance. Its filename stem is matched to the same-named image folder. Missing image references are reported; metadata rows are retained.",
    }
