"""Source-aware readers for LAST-FE datasets."""
from __future__ import annotations
import csv
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

def load_generic_csv(path: str | Path, *, source_id: str, **read_csv_kwargs: Any) -> pd.DataFrame:
    """Load other CSVs without guessing their schema; pass inspected pandas options."""
    frame = pd.read_csv(path, **read_csv_kwargs)
    frame["source_id"] = source_id
    return frame
