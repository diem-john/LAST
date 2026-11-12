"""Cross-event raster identity and metadata consistency diagnostics."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np


def _canonical_array_bytes(array: np.ndarray) -> bytes:
    values = np.asarray(array).copy()
    if np.issubdtype(values.dtype, np.floating):
        values[~np.isfinite(values)] = np.nan
    dtype = values.dtype.newbyteorder("<")
    return values.astype(dtype, copy=False).tobytes(order="C")


def _event_properties(raster_path: Path) -> tuple[dict[str, Any] | None, str]:
    candidates = sorted(raster_path.parent.glob("*_properties.json"))
    if not candidates:
        return None, "not_found"
    try:
        return json.loads(candidates[0].read_text(encoding="utf-8")), "loaded"
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"unreadable: {exc}"


def _raster_fingerprint(path: Path, *, window_size: int) -> dict[str, Any]:
    try:
        import rasterio
        from rasterio.windows import Window
    except ImportError as exc:
        raise RuntimeError("Raster consistency audit requires optional dependency rasterio") from exc

    with rasterio.open(path) as dataset:
        geometry = {
            "width": int(dataset.width),
            "height": int(dataset.height),
            "count": int(dataset.count),
            "crs": str(dataset.crs) if dataset.crs else None,
            "transform": [float(value) for value in dataset.transform][:6],
            "bounds": {
                "left": float(dataset.bounds.left),
                "bottom": float(dataset.bounds.bottom),
                "right": float(dataset.bounds.right),
                "top": float(dataset.bounds.top),
            },
            "descriptions": [value or "" for value in dataset.descriptions],
        }
        hashes = [hashlib.sha256() for _ in range(dataset.count)]
        mask_hashes = [hashlib.sha256() for _ in range(dataset.count)]
        for row in range(0, dataset.height, window_size):
            height = min(window_size, dataset.height - row)
            for col in range(0, dataset.width, window_size):
                width = min(window_size, dataset.width - col)
                window = Window(col, row, width, height)
                for index in range(1, dataset.count + 1):
                    masked = dataset.read(index, window=window, masked=True)
                    mask = np.ma.getmaskarray(masked)
                    raw = np.asarray(masked.data)
                    hashes[index - 1].update(_canonical_array_bytes(raw))
                    mask_hashes[index - 1].update(np.asarray(mask, dtype=np.uint8).tobytes(order="C"))
        band_digests = [
            {
                "index": index,
                "name": geometry["descriptions"][index - 1],
                "values_sha256": hashes[index - 1].hexdigest(),
                "mask_sha256": mask_hashes[index - 1].hexdigest(),
            }
            for index in range(1, dataset.count + 1)
        ]
    properties, properties_status = _event_properties(path)
    return {
        "path": str(path),
        "event_properties_status": properties_status,
        "event_properties": properties,
        "geometry": geometry,
        "band_digests": band_digests,
    }


def audit_raster_collection_consistency(
    paths: Iterable[str | Path], *, window_size: int = 512
) -> dict[str, Any]:
    """Fingerprint raster values and masks, then identify exact same-grid duplicates.

    Floating NaN payloads are canonicalized to NaN before hashing. Masks are
    hashed separately. This is an exact value/mask comparison, not a
    geospatial reprojection or a semantic comparison of flood events.
    """
    if window_size < 1:
        raise ValueError("window_size must be positive")
    sources = sorted({Path(path) for path in paths})
    fingerprints = [_raster_fingerprint(path, window_size=window_size) for path in sources]
    pairs = []
    for left_index, left in enumerate(fingerprints):
        for right in fingerprints[left_index + 1:]:
            same_geometry = left["geometry"] == right["geometry"]
            same_band_content = (
                len(left["band_digests"]) == len(right["band_digests"])
                and all(
                    a["name"] == b["name"]
                    and a["values_sha256"] == b["values_sha256"]
                    and a["mask_sha256"] == b["mask_sha256"]
                    for a, b in zip(left["band_digests"], right["band_digests"])
                )
            )
            pairs.append({
                "raster_a": left["path"],
                "raster_b": right["path"],
                "same_grid_and_metadata": same_geometry,
                "same_band_values_and_masks": same_band_content,
                "exact_duplicate": bool(same_geometry and same_band_content),
                "event_a": {
                    key: (left["event_properties"] or {}).get(key)
                    for key in ("id", "began", "ended", "dfo_centroid_x", "dfo_centroid_y", "dfo_main_cause")
                },
                "event_b": {
                    key: (right["event_properties"] or {}).get(key)
                    for key in ("id", "began", "ended", "dfo_centroid_x", "dfo_centroid_y", "dfo_main_cause")
                },
            })
    duplicates = [pair for pair in pairs if pair["exact_duplicate"]]
    return {
        "raster_count": len(fingerprints),
        "window_size": window_size,
        "rasters": fingerprints,
        "pairwise_comparisons": pairs,
        "exact_duplicate_pairs": duplicates,
        "interpretation": (
            "Exact duplicates require matching grid metadata, per-band values, and masks. "
            "Matching footprints alone are not duplicates. Event metadata differences are "
            "reported for review; no event is removed or merged automatically."
        ),
    }
