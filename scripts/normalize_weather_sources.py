"""Normalize existing LAST weather files into a source-aware long-form table.

No timestamp is silently reinterpreted. ERA5 valid_time and Giovanni UTC timestamps
are emitted as UTC. NASA POWER timestamps remain naive LST and are not accepted by
the UTC-only asset mapper until explicitly converted using verified metadata.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from forecasting.data.ingestion import load_area_averaged_precipitation, load_nasa_power

ROOT = Path(__file__).resolve().parents[1]
ERA5_FILES = {
    "era5_sfc": ROOT / "data/era5/reanalysis-era5-single-levels-timeseries-sfcnhk6q2bv.csv",
    "era5_wav": ROOT / "data/era5/reanalysis-era5-single-levels-timeseries-wavxnvtuiin.csv",
}
NASA_FILE = ROOT / "data/nasapower/nasapow.csv"
GIOVANNI_FILES = {
    "gldas_noah_3h": (ROOT / "data/imerg/g4.areaAvgTimeSeries.GLDAS_NOAH025_3H_2_0_Rainf_f_tavg.20100101-20261130.119E_22N_121E_23N.csv", "GLDAS_NOAH025_3H"),
    "trmm_3b42_v7": (ROOT / "data/imerg/g4.areaAvgTimeSeries.TRMM_3B42_7_precipitation.20100101-20261130.119E_22N_121E_23N.csv", "TRMM_3B42_V7"),
}
OUTPUT = ROOT / "data/weather/normalized_weather_observations.csv"

# Explicit unit registry for known ERA5 fields. Unknown fields are excluded unless
# a unit is provided through --era5-units-json; values are never unit-guessed.
ERA5_UNITS = {
    "t2m": "K", "2m_temperature": "K",
    "d2m": "K", "2m_dewpoint_temperature": "K",
    "u10": "m s-1", "10m_u_component_of_wind": "m s-1",
    "v10": "m s-1", "10m_v_component_of_wind": "m s-1",
    "sp": "Pa", "surface_pressure": "Pa",
    "msl": "Pa", "mean_sea_level_pressure": "Pa",
    "tp": "m", "total_precipitation": "m",
    "ssrd": "J m-2", "surface_solar_radiation_downwards": "J m-2",
    "strd": "J m-2", "surface_thermal_radiation_downwards": "J m-2",
    "swh": "m", "significant_height_of_combined_wind_waves_and_swell": "m",
    "mwp": "s", "mean_wave_period": "s",
    "mwd": "degree", "mean_wave_direction": "degree",
    "shww": "m", "significant_height_of_wind_waves": "m",
    "mpww": "s", "mean_period_of_wind_waves": "s",
    "mdww": "degree", "mean_direction_of_wind_waves": "degree",
    "shts": "m", "significant_height_of_total_swell": "m",
    "mpts": "s", "mean_period_of_total_swell": "s",
    "mdts": "degree", "mean_direction_of_total_swell": "degree",
}
EXCLUDED_COLUMNS = {
    "valid_time", "time", "date", "latitude", "longitude",
    "number", "expver", "source_id",
}


def _append_rows(rows: list[dict[str, Any]], *, timestamp: Any, source_id: str,
                 variable: str, value: Any, unit: str | None,
                 scope: str, time_basis: str, semantics: str,
                 latitude: Any = None, longitude: Any = None,
                 source_file: str, source_resolution: str,
                 spatial_support: str, source_metadata: str = "") -> None:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    rows.append({
        "timestamp": timestamp,
        "source_id": source_id,
        "variable": variable,
        "value": None if pd.isna(numeric) else float(numeric),
        "unit": unit or "unknown",
        "spatial_scope": scope,
        "time_basis": time_basis,
        "temporal_semantics": semantics,
        "latitude": latitude,
        "longitude": longitude,
        "source_file": source_file,
        "source_temporal_resolution": source_resolution,
        "source_spatial_support": spatial_support,
        "source_metadata": source_metadata,
    })


def normalize_era5(path: Path, source_id: str, unit_overrides: dict[str, str]) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path, low_memory=False)
    required = {"valid_time", "latitude", "longitude"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{source_id}: missing ERA5 columns {sorted(missing)}")
    timestamps = pd.to_datetime(frame["valid_time"], utc=True, errors="coerce")
    if timestamps.isna().any():
        raise ValueError(f"{source_id}: invalid valid_time values")
    variables = [
        column for column in frame.columns
        if column not in EXCLUDED_COLUMNS and pd.to_numeric(frame[column], errors="coerce").notna().any()
    ]
    if not variables:
        raise ValueError(f"{source_id}: no numeric weather variables detected")
    rows: list[dict[str, Any]] = []
    for variable in variables:
        unit = unit_overrides.get(variable, ERA5_UNITS.get(variable))
        if not unit:
            continue
        values = pd.to_numeric(frame[variable], errors="coerce")
        for index, value in values.items():
            _append_rows(
                rows, timestamp=timestamps.iloc[index].isoformat(), source_id=source_id,
                variable=variable, value=value, unit=unit, scope="point",
                time_basis="UTC", semantics="historical_reanalysis",
                latitude=float(frame.iloc[index]["latitude"]),
                longitude=float(frame.iloc[index]["longitude"]),
                source_file=path.name, source_resolution="source timestamp cadence; audit separately",
                spatial_support="ERA5 grid point",
            )
    if not rows:
        raise ValueError(
            f"{source_id}: no recognized variables. Inspect columns and supply explicit "
            "units with --era5-units-json; unknown columns were not guessed."
        )
    return rows


def normalize_nasa(path: Path, *, latitude: float | None, longitude: float | None) -> list[dict[str, Any]]:
    frame, metadata = load_nasa_power(path)
    if latitude is None or longitude is None:
        raise ValueError(
            "NASA POWER needs explicit --nasa-latitude and --nasa-longitude for point mapping. "
            f"Source location metadata: {metadata.get('location')!r}"
        )
    rows: list[dict[str, Any]] = []
    calendar = frame["timestamp_lst"]
    for variable in metadata["measurement_columns"]:
        for index, value in pd.to_numeric(frame[variable], errors="coerce").items():
            _append_rows(
                rows, timestamp=calendar.iloc[index].isoformat(), source_id="nasa_power",
                variable=variable, value=value, unit="source unit not normalized",
                scope="point", time_basis="LST", semantics="historical_observation",
                latitude=latitude, longitude=longitude, source_file=path.name,
                source_resolution="hourly",
                spatial_support="NASA POWER point/grid-cell estimate; location supplied by operator",
                source_metadata=json.dumps({"location": metadata.get("location"), "elevation": metadata.get("elevation")}),
            )
    return rows


def normalize_giovanni(path: Path, source_id: str) -> list[dict[str, Any]]:
    frame, metadata = load_area_averaged_precipitation(path, source_id=source_id)
    source_variable = str(metadata["source_variable"])
    if source_id == "GLDAS_NOAH025_3H":
        unit = "kg m-2 s-1"
        semantics = "historical_model_reanalysis"
        resolution = "3-hourly"
    elif source_id == "TRMM_3B42_V7":
        unit = "mm h-1"
        semantics = "historical_satellite_precipitation_estimate"
        resolution = "3-hourly"
    else:
        raise ValueError(f"Unsupported Giovanni precipitation source: {source_id}")
    rows: list[dict[str, Any]] = []
    metadata_text = json.dumps({
        "title": metadata.get("title"),
        "requested_bbox": metadata.get("requested_bbox"),
        "data_bbox": metadata.get("data_bbox"),
        "fill_value": metadata.get("fill_value"),
    })
    for record in frame.to_dict(orient="records"):
        value = record["value"]
        if pd.notna(value) and metadata.get("fill_value") is not None:
            if float(value) == float(metadata["fill_value"]):
                value = None
        _append_rows(
            rows, timestamp=record["timestamp"].isoformat(), source_id=source_id,
            variable=source_variable, value=value, unit=unit,
            scope="regional", time_basis="UTC", semantics=semantics,
            source_file=path.name, source_resolution=resolution,
            spatial_support="Giovanni area-averaged time series over reported data bounding box",
            source_metadata=metadata_text,
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--nasa-latitude", type=float)
    parser.add_argument("--nasa-longitude", type=float)
    parser.add_argument("--skip-nasa", action="store_true")
    parser.add_argument("--skip-era5", action="store_true")
    parser.add_argument("--skip-precipitation", action="store_true")
    parser.add_argument("--era5-units-json", type=Path)
    args = parser.parse_args()

    unit_overrides = {}
    if args.era5_units_json:
        unit_overrides = json.loads(args.era5_units_json.read_text(encoding="utf-8"))
        if not isinstance(unit_overrides, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in unit_overrides.items()):
            raise ValueError("ERA5 unit override file must be a JSON object of variable-name to unit-string")

    rows: list[dict[str, Any]] = []
    source_counts: dict[str, int] = {}
    if not args.skip_era5:
        for source_id, path in ERA5_FILES.items():
            result = normalize_era5(path, source_id, unit_overrides)
            rows.extend(result)
            source_counts[source_id] = len(result)
    if not args.skip_nasa:
        result = normalize_nasa(NASA_FILE, latitude=args.nasa_latitude, longitude=args.nasa_longitude)
        rows.extend(result)
        source_counts["nasa_power"] = len(result)
    if not args.skip_precipitation:
        for source_id, (path, canonical_id) in GIOVANNI_FILES.items():
            result = normalize_giovanni(path, canonical_id)
            rows.extend(result)
            source_counts[source_id] = len(result)

    output = pd.DataFrame(rows)
    if output.empty:
        raise ValueError("No weather records normalized")
    # Keep NaNs as empty CSV fields; never convert missing observations to zero.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output, index=False, encoding="utf-8-sig")
    summary = {
        "status": "weather_source_normalization_complete",
        "row_count": int(len(output)),
        "source_record_counts": source_counts,
        "sources": sorted(output["source_id"].unique().tolist()),
        "time_basis_counts": output["time_basis"].value_counts(dropna=False).to_dict(),
        "spatial_scope_counts": output["spatial_scope"].value_counts(dropna=False).to_dict(),
        "unknown_unit_variables": sorted(output.loc[output["unit"] == "unknown", "variable"].unique().tolist()),
        "nasa_power_note": "NASA POWER LST is preserved as naive local-solar-time text and is not mapper-ready until explicitly converted using verified time metadata.",
        "missing_value_policy": "Null measurements remain null; no imputation or zero substitution.",
        "limitations": [
            "ERA5 variables without recognized or explicitly overridden units are excluded and listed only through the detected source columns on error/reporting.",
            "NASA POWER requires explicit coordinates and its LST timestamps are not UTC.",
            "GLDAS and TRMM are regional area-averaged series, not point observations.",
            "No forecasts are generated by this normalization step.",
        ],
    }
    summary_path = args.output.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**summary, "output_csv": str(args.output), "summary_json": str(summary_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
