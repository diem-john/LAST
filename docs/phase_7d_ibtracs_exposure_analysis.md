# Phase 7D — IBTrACS closest-approach and exposure screening

## Purpose

Phase 7D converts the complete Phase 7B processed track table into per-storm
closest-observation records and exploratory distance bands for the synthetic
Minxiong IEEE 33-bus study coordinates. It also produces Taiwan-reference
closest-approach records and raw per-storm wind/pressure summaries.

This is a historical, observation-based spatial screening step. It does not
estimate wind at bus locations, asset damage, failure probability, or electrical
service interruption.

## Run

From the repository root:

```bash
export PYTHONPATH="$(pwd):$PYTHONPATH"
python scripts/analyze_ibtracs_exposure.py
```

The default input is `reports/ibtracs/ibtracs_tracks.csv`. The Phase 7B
processor must have been run with synthetic-grid proximity enabled. To select
paths and thresholds:

```bash
python scripts/analyze_ibtracs_exposure.py \
  --tracks reports/ibtracs/ibtracs_tracks.csv \
  --output-dir reports/ibtracs/exposure \
  --taiwan-radius-km 500 \
  --minxiong-radius-km 300 \
  --thresholds-km 50 100 200 300
```

The thresholds are ordered from the innermost to outermost distance band and
must be strictly increasing.

## Calculations

- **Taiwan closest approach:** minimum great-circle distance among observed
  positions to the Phase 7C Taiwan reference point (23.7°N, 121.0°E). Only
  storms whose observed minimum is within the configured Taiwan radius are
  included in the Taiwan closest-approach CSV.
- **Minxiong closest approach:** minimum of the Phase 7B per-observation
  distance to the nearest synthetic bus sample point. The associated observed
  timestamp, storm coordinates, nearest synthetic bus ID, translation speed,
  and heading are retained when available.
- **Distance bands:** defaults are <=50 km, >50–100 km, >100–200 km,
  >200–300 km, and >300 km. The labels are
  `very_high_proximity`, `high_proximity`, `moderate_proximity`,
  `low_proximity`, and `outside_screen`. These names describe distance
  bands only; they are not hazard or risk levels.
- **Intensity summary:** per-storm maximum `wind` and minimum `pressure`
  are calculated as raw source values. Units and agency conventions are not
  inferred. No category conversion is performed.

If multiple observations share the minimum distance, the earliest timestamp
and then lowest source row number are selected deterministically. No temporal
interpolation or imputation is performed.

## Outputs

Default directory: `reports/ibtracs/exposure/`

- `ibtracs_taiwan_closest_approach.csv`
- `ibtracs_minxiong_closest_approach.csv`
- `ibtracs_minxiong_exposure_classification.csv`
- `ibtracs_storm_intensity_summary.csv`
- `ibtracs_exposure_audit.json`
- `figures/minxiong_closest_approach_map.png`
- `figures/storm_exposure_distribution.png`
- `figures/closest_approach_timeline.png`
- `figures/storm_intensity_vs_distance.png` (only when a raw wind field is present)

## Interpretation safeguards and limitations

1. The minima are over discrete best-track observations. Hourly sampling may
   miss the continuous-path closest approach.
2. Minxiong distances are to synthetic bus sample points, not surveyed Taipower
   assets or actual branch/conductor corridors.
3. Taiwan distance is measured to a reference point, not to the coastline or
   an administrative boundary.
4. Distance bands are exploratory screening bins, not physical hazard classes,
   fragility classes, failure probabilities, or damage estimates.
5. Wind and pressure remain raw values. Verify dataset release, agency
   conventions, time semantics, and units before publication or physical
   modeling.
6. No wind-field model, local gust estimate, hydrologic model, infrastructure
   fragility model, or AC power-flow analysis is included.
7. These are historical IBTrACS best-track observations, not forecasts.

## Next scientific step

Before connecting exposure to weather-driven grid contingencies, verify the
IBTrACS source metadata and units, then select and validate a wind-field model
and a fragility relationship appropriate to the infrastructure being
represented. Keep synthetic network assumptions explicit and validate any
resulting scenarios independently before passing them to LAST-Q.
