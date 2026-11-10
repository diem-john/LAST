"""Unit-aware preprocessing for precipitation source records."""
from __future__ import annotations
import pandas as pd
GLDAS_SOURCE = "GLDAS_NOAH025_3H"
TRMM_SOURCE = "TRMM_3B42_V7"

def normalize_precipitation(frame: pd.DataFrame, *, source_id: str, fill_value: float | None = None) -> pd.DataFrame:
    """Add precipitation rate (mm/hr) and three-hour accumulation (mm)."""
    if "value" not in frame.columns:
        raise ValueError("Input frame must contain a numeric 'value' column")
    result = frame.copy()
    values = pd.to_numeric(result["value"], errors="coerce")
    if fill_value is not None:
        values = values.mask(values == fill_value)
    if source_id == GLDAS_SOURCE:
        result["precipitation_rate_mm_hr"] = values * 3600.0
        result["precipitation_3h_mm"] = values * 10800.0
        result["original_unit"] = "kg m-2 s-1"
    elif source_id == TRMM_SOURCE:
        result["precipitation_rate_mm_hr"] = values
        result["precipitation_3h_mm"] = values * 3.0
        result["original_unit"] = "mm hr-1"
    else:
        raise ValueError(f"Unsupported precipitation source_id: {source_id!r}")
    result["source_id"] = source_id
    result["is_missing"] = result["precipitation_rate_mm_hr"].isna()
    return result

def validate_time_series(frame: pd.DataFrame, *, expected_frequency: str = "3h") -> dict[str, object]:
    """Report timestamp quality without silently imputing or repairing records."""
    if "timestamp" not in frame.columns:
        raise ValueError("Input frame must contain 'timestamp'")
    parsed = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    timestamps = parsed.dropna().sort_values()
    # Duplicate timestamps are reported separately, not double-counted as cadence gaps.
    deltas = timestamps.diff().dropna()
    deltas = deltas[deltas > pd.Timedelta(0)]
    expected = pd.Timedelta(expected_frequency)
    return {
        "rows": int(len(frame)), "invalid_timestamps": int(parsed.isna().sum()),
        "duplicate_timestamps": int(timestamps.duplicated().sum()),
        "observed_start": timestamps.min().isoformat() if not timestamps.empty else None,
        "observed_end": timestamps.max().isoformat() if not timestamps.empty else None,
        "expected_frequency": expected_frequency,
        "nonconforming_intervals": int((deltas != expected).sum()),
    }
