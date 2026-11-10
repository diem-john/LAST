"""Typed, conservative JSON contract for LAST-FE advisory outputs."""
from __future__ import annotations
from typing import Any, Literal, TypedDict

class ForecastValue(TypedDict):
    value: float | None
    unit: str
    horizon_minutes: int
    lower_bound: float | None
    upper_bound: float | None
    status: Literal["forecast", "historical_estimate", "unknown"]
    source_ids: list[str]

class GridImpact(TypedDict):
    asset_id: str
    hazard: str
    severity: Literal["low", "moderate", "high", "critical", "unknown"]
    evidence: str
    validation_required: bool

class LASTFEOutput(TypedDict):
    schema_version: str
    generated_at_utc: str
    mode: Literal["historical_analysis", "forecast", "unknown"]
    data_as_of_utc: str | None
    location: dict[str, Any]
    weather: dict[str, ForecastValue]
    solar: dict[str, ForecastValue]
    flood: dict[str, ForecastValue]
    grid_impacts: list[GridImpact]
    limitations: list[str]
    advisory_only: Literal[True]

def empty_output(*, generated_at_utc: str, mode: str = "unknown") -> LASTFEOutput:
    """Create an explicit-unknown payload; never fabricate missing values."""
    if mode not in {"historical_analysis", "forecast", "unknown"}:
        raise ValueError(f"Unsupported mode: {mode}")
    return {
        "schema_version": "1.0.0", "generated_at_utc": generated_at_utc,
        "mode": mode, "data_as_of_utc": None, "location": {}, "weather": {},
        "solar": {}, "flood": {}, "grid_impacts": [],
        "limitations": ["No validated forecast values have been supplied."],
        "advisory_only": True,
    }
