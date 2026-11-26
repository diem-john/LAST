"""Filter processed IBTrACS tracks for WNP, Taiwan, and Minxiong screening."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from forecasting.data.ibtracs_regions import write_regional_outputs

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracks", type=Path, default=ROOT / "reports/ibtracs/ibtracs_tracks.csv",
                        help="Processed IBTrACS track CSV.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports/ibtracs/regional",
                        help="Directory for filtered tracks, summaries, maps, and audit JSON.")
    parser.add_argument("--taiwan-radius-km", type=float, default=500.0,
                        help="Exploratory distance threshold from Taiwan reference point.")
    parser.add_argument("--minxiong-radius-km", type=float, default=300.0,
                        help="Distance threshold to nearest synthetic bus point.")
    args = parser.parse_args()
    if not args.tracks.is_file():
        parser.error(f"Processed track CSV not found: {args.tracks}")
    tracks = pd.read_csv(args.tracks, low_memory=False)
    audit = write_regional_outputs(
        tracks, args.output_dir, taiwan_radius_km=args.taiwan_radius_km,
        minxiong_radius_km=args.minxiong_radius_km,
    )
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
