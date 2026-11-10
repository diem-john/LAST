"""Source-aware readers for LAST-FE datasets."""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

import pandas as pd


def _read_giovanni_metadata(path: Path) -> tuple[dict[str, str], int]:
    metadata: dict[str, str] = {}
    header_line: int | None = None
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        for line_number, row in enumerate(csv.reader(stream), start=1):
            if not row:
                continue
            if row[0].strip().lower() == "time":
                header_line = line_number - 1
                break
            if len(row) >= 2:
                metadata[row[0].strip().rstrip(":")] = row[1].strip()
    if header_line is None:
        raise ValueError(f"Could not locate a 'time' header in {path}")
    return metadata, header_line


def load_area_averaged_precipitation(path: str | Path, *, source_id: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Parse Giovanni metadata separately; derive coverage from observed rows."""
    csv_path = Path(path)
    metadata, header_line = _read_giovanni_metadata(csv_path)
    frame = pd.read_csv(csv_path, skiprows=header_line, skipinitialspace=True)
    if "time" not in frame.columns or len(frame.columns) < 2:
        raise ValueError(f"Expected 'time' and a measurement column in {csv_path}")
    value_columns = [c for c in frame.columns if c != "time"]
    if len(value_columns) != 1:
        raise ValueError(f"Expected exactly one measurement column, found {value_columns}")
    value_column = value_columns[0]
    frame = frame.rename(columns={"time": "timestamp", value_column: "value"})
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame["source_id"] = source_id
    frame["source_variable"] = value_column.strip()
    frame = frame.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    observed = frame["timestamp"].dropna()
    details: dict[str, Any] = {
        "source_id": source_id, "source_file": csv_path.name,
        "source_variable": value_column.strip(), "title": metadata.get("Title"),
        "requested_start": metadata.get("User Start Date"), "requested_end": metadata.get("User End Date"),
        "requested_bbox": metadata.get("User Bounding Box"), "data_bbox": metadata.get("Data Bounding Box"),
        "fill_value": metadata.get(f"Fill Value ({value_column.strip()})"),
        "observed_start": observed.min().isoformat() if not observed.empty else None,
        "observed_end": observed.max().isoformat() if not observed.empty else None,
        "row_count": int(len(frame)),
    }
    return frame, details


def _read_nasa_power_header(path: Path) -> tuple[dict[str, str], int]:
    """Read NASA POWER's -BEGIN HEADER-/-END HEADER- block.

    Returns metadata and the zero-based line index of the CSV column header.
    """
    metadata: dict[str, str] = {}
    in_header = False
    header_line: int | None = None
    parameter_lines: list[str] = []
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_index, raw_line in enumerate(stream):
            line = raw_line.strip()
            if line == "-BEGIN HEADER-":
                in_header = True
                continue
            if line == "-END HEADER-":
                in_header = False
                header_line = line_index + 1
                break
            if not in_header or not line:
                continue
            if line.startswith("Parameter(s):"):
                metadata["parameters"] = ""
            elif re.match(r"^[A-Z0-9_]+\s+", line):
                parameter_lines.append(line)
            elif ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip()] = value.strip()
            else:
                metadata.setdefault("description", line)
    if header_line is None:
        raise ValueError(f"Could not locate '-END HEADER-' in NASA POWER file: {path}")
    metadata["parameter_descriptions"] = parameter_lines
    return metadata, header_line


def load_nasa_power(path: str | Path, *, source_id: str = "nasa_power") -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load NASA POWER hourly data while preserving its local-solar-time convention.

    NASA POWER's YYYY, MO, DY, HR fields are combined into timestamp_lst.
    This timestamp is intentionally timezone-naive: the source declares LST,
    not UTC or a civil timezone. The -999 fill marker is converted to NaN in
    measurement columns, while original calendar fields are retained.
    """
    csv_path = Path(path)
    metadata, header_line = _read_nasa_power_header(csv_path)
    frame = pd.read_csv(csv_path, skiprows=header_line, low_memory=False)
    required = {"YEAR", "MO", "DY", "HR"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"NASA POWER file is missing calendar columns: {missing}")
    for column in frame.columns:
        if column not in required:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
            frame[column] = frame[column].replace(-999, float("nan"))
    timestamp = pd.to_datetime(
        {"year": frame["YEAR"], "month": frame["MO"], "day": frame["DY"], "hour": frame["HR"]},
        errors="coerce",
    )
    frame.insert(0, "timestamp_lst", timestamp)
    frame["source_id"] = source_id
    frame = frame.sort_values("timestamp_lst").reset_index(drop=True)
    valid_timestamps = frame["timestamp_lst"].dropna()
    measurement_columns = [c for c in frame.columns if c not in required | {"timestamp_lst", "source_id"}]
    details: dict[str, Any] = {
        "source_id": source_id,
        "source_file": csv_path.name,
        "temporal_resolution": "hourly",
        "time_convention": "LST (local solar time; timezone not specified by source)",
        "requested_or_reported_date_range": metadata.get("Dates (month/day/year)"),
        "location": metadata.get("Location"),
        "elevation": metadata.get("Elevation from MERRA-2"),
        "missing_value_marker": "-999",
        "parameter_descriptions": metadata.get("parameter_descriptions", []),
        "row_count": int(len(frame)),
        "valid_timestamp_count": int(valid_timestamps.size),
        "observed_start_lst": valid_timestamps.min().isoformat() if not valid_timestamps.empty else None,
        "observed_end_lst": valid_timestamps.max().isoformat() if not valid_timestamps.empty else None,
        "measurement_columns": measurement_columns,
        "missing_measurements": {c: int(frame[c].isna().sum()) for c in measurement_columns},
    }
    return frame, details


def load_generic_csv(path: str | Path, *, source_id: str, **read_csv_kwargs: Any) -> pd.DataFrame:
    """Load other CSVs without guessing their schema; pass inspected pandas options."""
    frame = pd.read_csv(path, **read_csv_kwargs)
    frame["source_id"] = source_id
    return frame
