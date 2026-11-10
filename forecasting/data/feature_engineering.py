"""Leakage-conscious temporal feature utilities."""
import pandas as pd

def add_precipitation_history(frame: pd.DataFrame, *, value_column: str = "precipitation_rate_mm_hr", windows: tuple[int, ...] = (2, 8, 24)) -> pd.DataFrame:
    """Add trailing rolling summaries; windows count observations, not hours."""
    if value_column not in frame.columns:
        raise ValueError(f"Missing required column: {value_column}")
    result = frame.sort_values("timestamp").copy()
    for window in windows:
        if window < 1:
            raise ValueError("Rolling windows must be positive")
        rolling = result[value_column].rolling(window=window, min_periods=window)
        result[f"precip_mean_{window}obs"] = rolling.mean()
        result[f"precip_max_{window}obs"] = rolling.max()
        result[f"precip_sum_{window}obs"] = rolling.sum()
    return result
