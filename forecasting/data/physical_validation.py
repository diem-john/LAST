"""Physical screening diagnostics for ERA5 variables.

Screening ranges are conservative review flags, not universal validity rules.
No values are clipped, imputed, or removed.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

# ERA5 single-level variable semantics for the variables present in LAST.
# The screening bounds are deliberately broad and must be reviewed against
# the exact CDS request metadata before model-specific filtering.
ERA5_VARIABLES: dict[str, dict[str, Any]] = {
    "u100": {"unit": "m s-1", "description": "100 m eastward wind component", "range": (-100.0, 100.0)},
    "v100": {"unit": "m s-1", "description": "100 m northward wind component", "range": (-100.0, 100.0)},
    "fg10": {"unit": "m s-1", "description": "10 m wind gust", "range": (0.0, 150.0)},
    "d2m": {"unit": "K", "description": "2 m dewpoint temperature", "range": (180.0, 340.0)},
    "t2m": {"unit": "K", "description": "2 m air temperature", "range": (180.0, 340.0)},
    "blh": {"unit": "m", "description": "Boundary layer height", "range": (0.0, 10000.0)},
    "cbh": {"unit": "m", "description": "Cloud base height", "range": (0.0, 30000.0)},
    "msl": {"unit": "Pa", "description": "Mean sea-level pressure", "range": (50000.0, 120000.0)},
    "skt": {"unit": "K", "description": "Skin temperature", "range": (180.0, 350.0)},
    "slhf": {"unit": "J m-2", "description": "Surface latent heat flux; signed accumulated energy", "range": None},
    "sp": {"unit": "Pa", "description": "Surface pressure", "range": (50000.0, 120000.0)},
    "ssrd": {"unit": "J m-2", "description": "Surface solar radiation downwards; accumulated energy", "range": (0.0, 5000000.0)},
    "strd": {"unit": "J m-2", "description": "Surface thermal radiation downwards; accumulated energy", "range": (0.0, 5000000.0)},
    "tcc": {"unit": "1", "description": "Total cloud cover", "range": (0.0, 1.0)},
    "tp": {"unit": "m", "description": "Total precipitation; accumulated water depth", "range": (0.0, 0.5)},
    "fdir": {"unit": "J m-2", "description": "Total sky direct solar radiation at surface; accumulated energy", "range": (0.0, 5000000.0)},
    "sst": {"unit": "K", "description": "Sea-surface temperature", "range": (180.0, 350.0)},
}

def audit_era5_physical_frame(frame: pd.DataFrame) -> dict[str, Any]:
    """Report missingness, broad range flags, and unit semantics by ERA5 field."""
    variables: dict[str, Any] = {}
    for name, spec in ERA5_VARIABLES.items():
        if name not in frame.columns:
            variables[name] = {"present": False, "unit": spec["unit"], "note": "Variable absent from input."}
            continue
        values = pd.to_numeric(frame[name], errors="coerce")
        finite = values[np.isfinite(values)]
        low_high = spec["range"]
        below = above = 0
        if low_high is not None and finite.size:
            below = int((finite < low_high[0]).sum())
            above = int((finite > low_high[1]).sum())
        negative_count = int((finite < 0).sum())
        variables[name] = {
            "present": True,
            "unit": spec["unit"],
            "description": spec["description"],
            "rows": int(len(values)),
            "missing_or_unparseable": int(values.isna().sum()),
            "nonfinite": int((values.notna() & ~np.isfinite(values)).sum()),
            "finite_count": int(finite.size),
            "min": float(finite.min()) if finite.size else None,
            "max": float(finite.max()) if finite.size else None,
            "negative_finite_values": negative_count,
            "screening_range": list(low_high) if low_high is not None else None,
            "below_screening_range": below,
            "above_screening_range": above,
            "review_required": bool(below or above),
            "interpretation": (
                "Broad screening range only; review flagged values against source metadata."
                if low_high is not None else
                "Signed accumulated flux; negative values are not automatically invalid."
            ),
        }
    return {
        "source_id": "era5_sfc",
        "row_count": int(len(frame)),
        "variables": variables,
        "policy": "Diagnostics only: no clipping, imputation, unit conversion, or row removal.",
        "important_note": (
            "Accumulated ERA5 variables require the original CDS product, forecast-step, "
            "and accumulation-window metadata before conversion to hourly fluxes or rates."
        ),
    }
