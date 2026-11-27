"""Fit a component-specific wind fragility curve from observed asset outcomes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from grid.ibtracs_fragility import fit_logistic_pole_fragility

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", type=Path, required=True,
                        help="CSV containing paired exposed pole wind speeds and binary failure outcomes.")
    parser.add_argument("--output", type=Path, default=ROOT / "config/ibtracs_wind_fragility_calibrated.json")
    parser.add_argument("--asset-class", required=True,
                        help="Name of the homogeneous component class represented by the observations.")
    parser.add_argument("--pole-spacing-m", type=float, required=True,
                        help="Locally documented/assumed spacing used only to aggregate pole probabilities to branch probabilities.")
    parser.add_argument("--ridge", type=float, default=1e-4)
    args = parser.parse_args()
    if args.pole_spacing_m <= 0:
        parser.error("--pole-spacing-m must be positive")
    frame = pd.read_csv(args.observations, low_memory=False)
    if "asset_class" not in frame:
        parser.error("Calibration CSV must include an asset_class column")
    frame = frame.loc[frame["asset_class"].astype(str) == args.asset_class].copy()
    fitted = fit_logistic_pole_fragility(frame, ridge=args.ridge)
    config = {
        "schema_version": 1,
        "model_type": fitted.pop("model_type"),
        "calibration_status": "locally_calibrated",
        "component_class": args.asset_class,
        "pole_spacing_m": float(args.pole_spacing_m),
        "calibration_note": "Locally fitted logistic curve. Confirm that calibration observations represent the same component class, wind averaging period, reference height, and exposure conditions as the target network. Validate on held-out storm events before scientific deployment.",
        "source_observations": str(args.observations),
        "calibration": fitted,
        **{
            key: value for key, value in fitted.items()
            if key in {"pole_logistic_intercept", "pole_logistic_slope_per_ms"}
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "fragility_curve_fitted",
        "component_class": args.asset_class,
        "sample_count": fitted["sample_count"],
        "failure_count": fitted["failure_count"],
        "nonfailure_count": fitted["nonfailure_count"],
        "converged": fitted["converged"],
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
