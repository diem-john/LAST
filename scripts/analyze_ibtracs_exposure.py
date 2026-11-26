"""Generate IBTrACS closest-approach and spatial exposure screening products."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from forecasting.data.ibtracs_exposure import build_exposure_outputs

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tracks", type=Path, default=ROOT / "reports/ibtracs/ibtracs_tracks.csv",
        help="Full processed IBTrACS track CSV from Phase 7B (must include synthetic bus proximity).",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "reports/ibtracs/exposure",
        help="Directory for closest-approach tables, screening bands, figures, and audit.",
    )
    parser.add_argument("--taiwan-radius-km", type=float, default=500.0)
    parser.add_argument("--minxiong-radius-km", type=float, default=300.0)
    parser.add_argument(
        "--thresholds-km", type=float, nargs=4, default=(50.0, 100.0, 200.0, 300.0),
        metavar=("VERY_HIGH", "HIGH", "MODERATE", "LOW"),
        help="Four increasing exploratory distance thresholds for Minxiong proximity bands.",
    )
    args = parser.parse_args()
    if not args.tracks.is_file():
        parser.error(f"Processed IBTrACS track CSV not found: {args.tracks}")
    tracks = pd.read_csv(args.tracks, low_memory=False)
    audit = build_exposure_outputs(
        tracks,
        args.output_dir,
        taiwan_radius_km=args.taiwan_radius_km,
        minxiong_radius_km=args.minxiong_radius_km,
        thresholds_km=tuple(args.thresholds_km),
    )
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
