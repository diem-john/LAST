"""Full-record data-quality diagnostics for LAST-FE source datasets."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from forecasting.data.preprocessing import normalize_precipitation, validate_time_series


def _numeric_profile(series: pd.Series) -> dict[str, Any]:
    values = pd.to_numeric(series, errors="coerce")
    finite = values[np.isfinite(values)]
    return {
        "rows": int(len(series)),
        "missing_or_unparseable": int(values.isna().sum()),
        "nonfinite": int((values.notna() & ~np.isfinite(values)).sum()),
        "finite_count": int(finite.size),
        "min": float(finite.min()) if finite.size else None,
        "max": float(finite.max()) if finite.size else None,
        "mean": float(finite.mean()) if finite.size else None,
        "std": float(finite.std()) if finite.size > 1 else (0.0 if finite.size == 1 else None),
    }


def audit_frame_quality(
    frame: pd.DataFrame,
    *,
    timestamp_column: str,
    expected_frequency: str | None = None,
    exclude_numeric: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Profile all rows of a frame without imputing, resampling, or dropping rows."""
    if timestamp_column not in frame.columns:
        raise ValueError(f"Missing timestamp column: {timestamp_column}")
    parsed = pd.to_datetime(frame[timestamp_column], errors="coerce", utc=True)
    valid = parsed.dropna().sort_values()
    duplicate_count = int(valid.duplicated().sum())
    unique = valid.drop_duplicates().sort_values()
    deltas = unique.diff().dropna()
    cadence: dict[str, Any] | None = None
    if expected_frequency is not None:
        expected = pd.Timedelta(expected_frequency)
        nonconforming = deltas[deltas != expected]
        cadence = {
            "expected_frequency": expected_frequency,
            "unique_timestamp_count": int(len(unique)),
            "nonconforming_intervals": int(len(nonconforming)),
            "largest_gap": str(deltas.max()) if not deltas.empty else None,
            "smallest_interval": str(deltas.min()) if not deltas.empty else None,
        }
    numeric = {}
    for column in frame.columns:
        if column == timestamp_column or column in exclude_numeric:
            continue
        converted = pd.to_numeric(frame[column], errors="coerce")
        if converted.notna().any() or pd.api.types.is_numeric_dtype(frame[column]):
            numeric[str(column)] = _numeric_profile(frame[column])
    return {
        "row_count": int(len(frame)),
        "timestamp_column": timestamp_column,
        "invalid_timestamps": int(parsed.isna().sum()),
        "duplicate_timestamps": duplicate_count,
        "unique_timestamp_count": int(len(unique)),
        "observed_start_utc": valid.min().isoformat() if not valid.empty else None,
        "observed_end_utc": valid.max().isoformat() if not valid.empty else None,
        "cadence": cadence,
        "numeric_columns": numeric,
    }


def audit_precipitation_frame(
    frame: pd.DataFrame, *, source_id: str, fill_value: float | None = None
) -> dict[str, Any]:
    """Full-series quality report for one precipitation source."""
    normalized = normalize_precipitation(frame, source_id=source_id, fill_value=fill_value)
    time_report = validate_time_series(normalized)
    raw = _numeric_profile(normalized["value"])
    rate = _numeric_profile(normalized["precipitation_rate_mm_hr"])
    accumulation = _numeric_profile(normalized["precipitation_3h_mm"])
    report: dict[str, Any] = {
        "source_id": source_id,
        "row_count": int(len(normalized)),
        "raw_value_profile": raw,
        "precipitation_rate_mm_hr": rate,
        "precipitation_3h_mm": accumulation,
        "original_unit": str(normalized["original_unit"].iloc[0]) if len(normalized) else None,
        "time_series": time_report,
        "timestamp_convention": "UTC",
    }
    if not normalized.empty:
        timestamps = pd.to_datetime(normalized["timestamp"], utc=True, errors="coerce")
        valid = timestamps.dropna()
        report["observed_start_utc"] = valid.min().isoformat() if not valid.empty else None
        report["observed_end_utc"] = valid.max().isoformat() if not valid.empty else None
    return report


def audit_ibtracs_quality(metadata_dir: str | Path) -> dict[str, Any]:
    """Aggregate row-level quality across per-instance IBTrACS metadata CSVs."""
    root = Path(metadata_dir)
    files = sorted(root.glob("*.csv")) if root.exists() else []
    total_rows = 0
    column_rows: dict[str, Counter[str]] = {}
    instances: dict[str, Any] = {}
    for path in files:
        frame = pd.read_csv(path, low_memory=False)
        total_rows += len(frame)
        for column in frame.columns:
            counter = column_rows.setdefault(str(column), Counter())
            counter["rows"] += len(frame)
            counter["missing"] += int(frame[column].isna().sum())
        required = {"year", "month", "day", "hour"}
        if required.issubset(frame.columns):
            timestamp = pd.to_datetime(
                {
                    "year": pd.to_numeric(frame["year"], errors="coerce"),
                    "month": pd.to_numeric(frame["month"], errors="coerce"),
                    "day": pd.to_numeric(frame["day"], errors="coerce"),
                    "hour": pd.to_numeric(frame["hour"], errors="coerce"),
                },
                errors="coerce",
                utc=True,
            )
            invalid = int(timestamp.isna().sum())
            valid = timestamp.dropna().sort_values()
            duplicate = int(valid.duplicated().sum())
            start = valid.min().isoformat() if not valid.empty else None
            end = valid.max().isoformat() if not valid.empty else None
        else:
            invalid, duplicate, start, end = len(frame), 0, None, None
        instances[path.stem] = {
            "rows": int(len(frame)),
            "invalid_timestamps": invalid,
            "duplicate_timestamps": duplicate,
            "observed_start_utc": start,
            "observed_end_utc": end,
        }
    columns = {
        name: {
            "rows": int(counts["rows"]),
            "missing": int(counts["missing"]),
            "missing_fraction": float(counts["missing"] / counts["rows"]) if counts["rows"] else None,
        }
        for name, counts in sorted(column_rows.items())
    }
    return {
        "metadata_instance_count": int(len(files)),
        "total_metadata_rows": int(total_rows),
        "columns": columns,
        "instances": instances,
        "note": "Timestamp construction uses the metadata year/month/day/hour fields as UTC. No rows are imputed or discarded.",
    }


def audit_raster_full(path: str | Path, *, window_size: int = 512) -> dict[str, Any]:
    """Stream every raster pixel to compute finite statistics and flooded-band counts."""
    try:
        import rasterio
        from rasterio.windows import Window
    except ImportError as exc:
        raise RuntimeError("Full raster audit requires optional dependency rasterio") from exc
    source = Path(path)
    with rasterio.open(source) as dataset:
        descriptions = [description or "" for description in dataset.descriptions]
        flooded_indices = [i + 1 for i, description in enumerate(descriptions) if description.strip().lower() == "flooded"]
        accumulators = [
            {"finite": 0, "nonfinite": 0, "min": None, "max": None, "sum": 0.0, "sum_sq": 0.0}
            for _ in range(dataset.count)
        ]
        flooded_values: Counter[str] = Counter()
        for row in range(0, dataset.height, window_size):
            height = min(window_size, dataset.height - row)
            for col in range(0, dataset.width, window_size):
                width = min(window_size, dataset.width - col)
                window = Window(col, row, width, height)
                for band_index in range(1, dataset.count + 1):
                    masked = dataset.read(band_index, window=window, masked=True)
                    raw = masked.compressed()
                    finite = raw[np.isfinite(raw)]
                    acc = accumulators[band_index - 1]
                    acc["finite"] += int(finite.size)
                    acc["nonfinite"] += int(raw.size - finite.size)
                    if finite.size:
                        low, high = float(finite.min()), float(finite.max())
                        acc["min"] = low if acc["min"] is None else min(acc["min"], low)
                        acc["max"] = high if acc["max"] is None else max(acc["max"], high)
                        acc["sum"] += float(finite.sum(dtype=np.float64))
                        acc["sum_sq"] += float(np.square(finite, dtype=np.float64).sum())
                    if band_index in flooded_indices:
                        values, counts = np.unique(finite, return_counts=True)
                        for value, count in zip(values, counts):
                            flooded_values[str(float(value))] += int(count)
        bands = []
        for index, acc in enumerate(accumulators, start=1):
            count = acc["finite"]
            mean = acc["sum"] / count if count else None
            variance = max(acc["sum_sq"] / count - mean * mean, 0.0) if count else None
            bands.append({
                "index": index,
                "description": descriptions[index - 1] or None,
                "finite_pixels": count,
                "nonfinite_unmasked_pixels": acc["nonfinite"],
                "min": acc["min"],
                "max": acc["max"],
                "mean": mean,
                "std": float(np.sqrt(variance)) if variance is not None else None,
            })
        bounds = dataset.bounds
        return {
            "path": str(source),
            "width": dataset.width,
            "height": dataset.height,
            "crs": str(dataset.crs) if dataset.crs else None,
            "bounds": {"left": bounds.left, "bottom": bounds.bottom, "right": bounds.right, "top": bounds.top},
            "flooded_band_indices": flooded_indices,
            "flooded_band_value_counts": dict(flooded_values),
            "bands": bands,
            "asset_intersection_checked": False,
            "asset_intersection_note": "No verified grid asset coordinates or geometry were supplied; bounding-box overlap is not treated as asset exposure.",
            "processing": {"window_size": window_size, "full_pixel_scan": True},
        }
