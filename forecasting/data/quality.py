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
    timestamp_timezone: str = "UTC",
) -> dict[str, Any]:
    """Profile all rows of a frame without imputing, resampling, or dropping rows."""
    if timestamp_column not in frame.columns:
        raise ValueError(f"Missing timestamp column: {timestamp_column}")
    if timestamp_timezone.upper() == "UTC":
        parsed = pd.to_datetime(frame[timestamp_column], errors="coerce", utc=True)
    elif timestamp_timezone.upper() == "NAIVE":
        parsed = pd.to_datetime(frame[timestamp_column], errors="coerce")
    else:
        raise ValueError("timestamp_timezone must be 'UTC' or 'NAIVE'")
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
        "observed_start": valid.min().isoformat() if not valid.empty else None,
        "observed_end": valid.max().isoformat() if not valid.empty else None,
        "timestamp_timezone": timestamp_timezone.upper(),
        "cadence": cadence,
        "numeric_columns": numeric,
    }


def audit_precipitation_frame(
    frame: pd.DataFrame, *, source_id: str, fill_value: float | None = None
) -> dict[str, Any]:
    """Full-series quality report for one precipitation source."""
    normalized = normalize_precipitation(frame, source_id=source_id, fill_value=fill_value)
    time_report = validate_time_series(normalized)
    raw_values = pd.to_numeric(frame["value"], errors="coerce")
    if fill_value is not None:
        raw_values = raw_values.mask(raw_values == fill_value)
    raw = _numeric_profile(raw_values)
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



def audit_raster_integrity(path: str | Path, *, window_size: int = 512) -> dict[str, Any]:
    """Separate raster mask/NoData, unmasked non-finite, and finite pixel counts."""
    try:
        import rasterio
        from rasterio.windows import Window
    except ImportError as exc:
        raise RuntimeError("Raster integrity audit requires optional dependency rasterio") from exc

    source = Path(path)
    with rasterio.open(source) as dataset:
        band_reports = []
        for band_index in range(1, dataset.count + 1):
            masked_pixels = finite_pixels = nonfinite_unmasked = 0
            finite_min = finite_max = None
            value_counts: Counter[str] = Counter()
            for row in range(0, dataset.height, window_size):
                height = min(window_size, dataset.height - row)
                for col in range(0, dataset.width, window_size):
                    width = min(window_size, dataset.width - col)
                    window = Window(col, row, width, height)
                    values = dataset.read(band_index, window=window, masked=True)
                    mask = np.ma.getmaskarray(values)
                    raw = np.asarray(values.data)
                    unmasked = raw[~mask]
                    finite = unmasked[np.isfinite(unmasked)]
                    masked_pixels += int(mask.sum())
                    finite_pixels += int(finite.size)
                    nonfinite_unmasked += int(unmasked.size - finite.size)
                    if finite.size:
                        low, high = float(finite.min()), float(finite.max())
                        finite_min = low if finite_min is None else min(finite_min, low)
                        finite_max = high if finite_max is None else max(finite_max, high)
                        if (dataset.descriptions[band_index - 1] or "").strip().lower() == "flooded":
                            values_unique, counts = np.unique(finite, return_counts=True)
                            for value, count in zip(values_unique, counts):
                                value_counts[str(float(value))] += int(count)
            total = dataset.width * dataset.height
            band_reports.append({
                "index": band_index,
                "description": dataset.descriptions[band_index - 1] or None,
                "nodata_value": dataset.nodatavals[band_index - 1],
                "mask_flags": [str(flag) for flag in dataset.mask_flag_enums[band_index - 1]],
                "total_pixels": int(total),
                "masked_or_nodata_pixels": masked_pixels,
                "finite_unmasked_pixels": finite_pixels,
                "nonfinite_unmasked_pixels": nonfinite_unmasked,
                "finite_fraction_of_total": float(finite_pixels / total) if total else None,
                "min_finite": finite_min,
                "max_finite": finite_max,
                "flooded_value_counts": dict(value_counts) if value_counts else None,
            })
        return {
            "path": str(source),
            "width": int(dataset.width),
            "height": int(dataset.height),
            "crs": str(dataset.crs) if dataset.crs else None,
            "transform": list(dataset.transform)[:6],
            "bounds": {
                "left": dataset.bounds.left, "bottom": dataset.bounds.bottom,
                "right": dataset.bounds.right, "top": dataset.bounds.top,
            },
            "bands": band_reports,
            "processing": {"window_size": window_size, "full_pixel_scan": True},
            "interpretation": (
                "Masked/NoData pixels are separated from unmasked NaN/Inf pixels. "
                "Finite pixel counts do not establish flood exposure of grid assets."
            ),
        }


def audit_raster_spatial_coverage(
    path: str | Path,
    *,
    window_size: int = 512,
    overview_rows: int = 16,
    overview_cols: int = 16,
    properties_path: str | Path | None = None,
) -> dict[str, Any]:
    """Map finite/non-finite coverage by band and coarse spatial tile.

    Values are never reclassified. The overview records counts and finite
    fractions only; unmasked NaN/Inf remains an unknown observation state.
    Pairwise overlap is computed from finite masks, not from flood values.
    """
    import json

    try:
        import rasterio
        from rasterio.windows import Window
    except ImportError as exc:
        raise RuntimeError("Spatial raster coverage audit requires optional dependency rasterio") from exc

    if window_size < 1 or overview_rows < 1 or overview_cols < 1:
        raise ValueError("window_size and overview dimensions must be positive")

    source = Path(path)
    props_file = Path(properties_path) if properties_path else next(
        iter(sorted(source.parent.glob("*_properties.json"))), None
    )
    event_properties: dict[str, Any] | None = None
    properties_status = "not_found"
    if props_file is not None and props_file.is_file():
        try:
            event_properties = json.loads(props_file.read_text(encoding="utf-8"))
            properties_status = "loaded"
        except (OSError, json.JSONDecodeError) as exc:
            properties_status = f"unreadable: {exc}"

    with rasterio.open(source) as dataset:
        height, width = dataset.height, dataset.width
        row_edges = np.linspace(0, height, overview_rows + 1, dtype=int)
        col_edges = np.linspace(0, width, overview_cols + 1, dtype=int)
        band_names = [
            (description or f"band_{index}").strip()
            for index, description in enumerate(dataset.descriptions, start=1)
        ]
        global_counts = [
            {"finite": 0, "nonfinite_unmasked": 0, "masked": 0}
            for _ in range(dataset.count)
        ]
        pair_counts = {
            f"{i}:{j}": {"both_finite": 0, "either_finite": 0}
            for i in range(dataset.count) for j in range(i + 1, dataset.count + 1)
        }
        tiles: list[list[dict[str, Any]]] = []

        for tile_row in range(overview_rows):
            tile_cells = []
            r0, r1 = int(row_edges[tile_row]), int(row_edges[tile_row + 1])
            for tile_col in range(overview_cols):
                c0, c1 = int(col_edges[tile_col]), int(col_edges[tile_col + 1])
                tile_counts = [
                    {"finite": 0, "nonfinite_unmasked": 0, "masked": 0}
                    for _ in range(dataset.count)
                ]
                # Process each overview tile in bounded windows.
                for row in range(r0, r1, window_size):
                    win_h = min(window_size, r1 - row)
                    for col in range(c0, c1, window_size):
                        win_w = min(window_size, c1 - col)
                        window = Window(col, row, win_w, win_h)
                        finite_masks = []
                        for band_index in range(1, dataset.count + 1):
                            values = dataset.read(band_index, window=window, masked=True)
                            mask = np.ma.getmaskarray(values)
                            raw = np.asarray(values.data)
                            unmasked = raw[~mask]
                            finite = np.isfinite(unmasked)
                            counts = tile_counts[band_index - 1]
                            counts["masked"] += int(mask.sum())
                            counts["finite"] += int(finite.sum())
                            counts["nonfinite_unmasked"] += int((~finite).sum())
                            finite_mask = (~mask) & np.isfinite(raw)
                            finite_masks.append(finite_mask)
                        for i in range(dataset.count):
                            for j in range(i + 1, dataset.count):
                                both = finite_masks[i] & finite_masks[j]
                                either = finite_masks[i] | finite_masks[j]
                                pair = pair_counts[f"{i + 1}:{j + 1}"]
                                pair["both_finite"] += int(both.sum())
                                pair["either_finite"] += int(either.sum())

                tile_total = max((r1 - r0) * (c1 - c0), 0)
                band_tile_results = []
                for index, counts in enumerate(tile_counts):
                    for key in counts:
                        global_counts[index][key] += counts[key]
                    band_tile_results.append({
                        "band_index": index + 1,
                        "band": band_names[index],
                        **counts,
                        "tile_pixels": tile_total,
                        "finite_fraction": (
                            float(counts["finite"] / tile_total) if tile_total else None
                        ),
                    })
                tile_cells.append({
                    "tile_row": tile_row,
                    "tile_col": tile_col,
                    "pixel_window": {"row_start": r0, "row_end": r1, "col_start": c0, "col_end": c1},
                    "bands": band_tile_results,
                })
            tiles.append(tile_cells)

        pairwise = []
        for key, counts in pair_counts.items():
            i, j = (int(value) for value in key.split(":"))
            union = counts["either_finite"]
            pairwise.append({
                "band_a": {"index": i, "name": band_names[i - 1]},
                "band_b": {"index": j, "name": band_names[j - 1]},
                **counts,
                "finite_mask_jaccard": float(counts["both_finite"] / union) if union else None,
            })

        band_summary = []
        total_pixels = height * width
        for index, counts in enumerate(global_counts):
            band_summary.append({
                "index": index + 1,
                "name": band_names[index],
                **counts,
                "total_pixels": total_pixels,
                "finite_fraction": float(counts["finite"] / total_pixels) if total_pixels else None,
            })

        transform = dataset.transform
        bounds = dataset.bounds
        return {
            "path": str(source),
            "event_properties_path": str(props_file) if props_file else None,
            "event_properties_status": properties_status,
            "event_properties": event_properties,
            "width": width,
            "height": height,
            "crs": str(dataset.crs) if dataset.crs else None,
            "transform": list(transform)[:6],
            "bounds": {
                "left": bounds.left, "bottom": bounds.bottom,
                "right": bounds.right, "top": bounds.top,
            },
            "band_summaries": band_summary,
            "pairwise_finite_mask_overlap": pairwise,
            "spatial_overview": {
                "rows": overview_rows,
                "columns": overview_cols,
                "tiles": tiles,
            },
            "interpretation": (
                "Finite-mask coverage diagnostics only. Unmasked NaN/Inf and masked "
                "pixels remain distinct unknown/NoData states. Pairwise overlap does "
                "not establish observation quality, flood status, or asset exposure."
            ),
            "processing": {
                "window_size": window_size,
                "full_pixel_scan": True,
                "overview_is_aggregate": True,
                "values_reclassified": False,
            },
        }
