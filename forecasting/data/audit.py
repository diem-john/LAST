"""Schema-first audit utilities for heterogeneous LAST-FE source files."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
import pandas as pd


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
            bands.append({
                "index": index, "dtype": dataset.dtypes[index - 1],
                "nodata": dataset.nodata, "sample_valid_pixels": int(compressed.size),
                "sample_min": float(compressed.min()) if compressed.size else None,
                "sample_max": float(compressed.max()) if compressed.size else None,
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
