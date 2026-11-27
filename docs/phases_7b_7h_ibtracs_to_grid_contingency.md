# Phases 7B–7H — IBTrACS-to-grid weather contingency pipeline

## Scope and status

This implementation connects the existing Phase 7B, 7C, and 7D processing
modules to new Phase 7E–7H research components.

| Phase | Implemented function | Output |
|---|---|---|
| 7B | Normalize per-storm historical track records; validate timestamps/coordinates; derive motion | `reports/ibtracs/ibtracs_tracks.csv` and audit |
| 7C | Select complete tracks intersecting WNP, Taiwan, and Minxiong screens | `reports/ibtracs/regional/` |
| 7D | Calculate observed closest approaches and spatial screening bands | `reports/ibtracs/exposure/` |
| 7E | Reconstruct parametric wind fields at each selected storm observation | `reports/ibtracs/wind/ibtracs_wind_field_track_parameters.csv` |
| 7F | Evaluate wind at synthetic buses and branch sample points | `ibtracs_grid_asset_wind_exposure.csv` |
| 7G | Apply a literature-reference pole fragility function and aggregate to branches | `ibtracs_branch_fragility_probabilities.csv` |
| 7H | Sample storm-peak branch contingencies and report resulting topology | `ibtracs_weather_contingency_scenarios.json` |

Phases 7E–7H are a research prototype. No local wind or asset failure data are
included in the current implementation for calibration, and no operational
readiness or quantum advantage is claimed.

## Critical source-data qualification

The repository's per-storm metadata schema (`year, month, day, hour, grade,
lat, lng, pressure, wind, dir50, long50, short50, dir30, long30, short30,
landfall, intp`) and HDF5 image naming pattern match the Digital Typhoon
Dataset. Digital Typhoon identifies its track/intensity source as JMA-derived.
Its documentation specifies knots for maximum wind, and JMA's maximum sustained
wind convention is a 10-minute mean. The exact release/version of the local
Digital Typhoon copy has not yet been established.

The configured wind unit is therefore `knots`, and the averaging period is
`10` minutes. The model uses a `10 m` surface-wind reference height as an
explicit standard modeling assumption; the inspected metadata schema does not
itself include a height field. This distinction is retained in
`source_fields.wind_height_status`. Confirm the local release and height
convention against the exact archived dataset before treating the pipeline as
fully source-verified.

The `long50/short50` and `long30/short30` fields are not consumed by this
initial model because their geometric meaning and units are not documented in
the repository. They must not be interpreted as wind radii until verified.

## Study wind adjustment

The current study configuration applies an additive **15-knot offset** only to finite numeric wind observations in eligible JMA grades 3, 4, and 5. Grades 2 (tropical depression) and 6 (extratropical cyclone) do not carry an applicable maximum sustained wind value in this field; their zero placeholders are treated as unavailable. The grade and raw source value are preserved. The original source value is retained in
`vmax_source_raw`; the unadjusted converted value is retained in
`vmax_observed_ms`; and the adjusted value used by the wind model is stored in
`vmax_ms` / `vmax_adjusted_ms`. Missing or non-finite observations remain
missing and are not replaced by the offset.

This +15-knot term is a user-selected experimental sensitivity assumption. It
is not a validated physical correction, sensor-bias estimate, or calibrated
adjustment. It increases already-positive eligible observations. Results must
therefore be interpreted as conditional on this assumption and compared against
an unadjusted 0-knot baseline.

The adjustment does not establish the source wind averaging period or reference
height. Those source semantics remain separate configuration requirements.

## Phase 7E — Parametric wind-field reconstruction

The current implementation uses a Willoughby et al. (2006)-style two-region
radial wind profile. It requires maximum sustained wind speed, radius of
maximum wind (RMW), and storm latitude. The configured RMW is currently a
fixed 30 km sensitivity assumption; it is not observed or locally calibrated.
Translation asymmetry is optionally added using a Miyazaki-style exponentially
decaying fraction of storm translation velocity.

The implementation:
- converts the explicitly configured source wind unit to m/s;
- preserves the source averaging period and height as metadata (it does not
  convert between 1-, 3-, or 10-minute wind averages);
- evaluates the radial profile at storm-relative distances;
- adds translation asymmetry using track-derived translation speed and heading;
- does not infer wind from central pressure or use undocumented wind-radius
  fields.

The Willoughby profile parameters follow the published empirical formulation:
for (r<R_m), (V=V_m(r/R_m)^n); outside (R_m), a two-exponential
decay is used. The RMW is a required model input. The selected profile was
developed/evaluated against aircraft observations; regional transfer and the
fixed RMW assumption require sensitivity analysis.

## Phase 7F — Synthetic grid asset exposure

The script evaluates the wind field at:
- all 33 synthetic bus coordinates;
- five equally spaced interior points on every in-service branch's straight
  line between its synthetic endpoint bus coordinates.

For each timestamp and branch, the maximum of the sampled points is retained.
This is a geometric screening approximation. The lines are not surveyed
conductor routes, and the samples are not verified pole locations. No terrain,
surface roughness, topographic speed-up, shielding, or local gust model is
included.

## Phase 7G — Fragility relationship

The reference pole curve implemented is the literature-reported expression

[
P_{pole}(V)=0.0001exp(0.0421 V_{mph})
]

with values clipped to [0,1]. A branch probability is then aggregated as

[
P_{branch}=1-(1-P_{pole})^{N_{pole}}.
]

The number of poles is estimated from the synthetic straight-line branch
length and a configurable assumed pole spacing (default 50 m). Neither the
pole spacing nor the pole count is known for the synthetic Minxiong network.
The formula is not calibrated to Taipower or to the local feeder, and its
underlying study assumptions may not transfer to this network. Treat results
only as sensitivity values. Replace the reference curve and pole counts with
component-specific local data, or fit fragility curves using paired historical
wind exposure and observed outage/damage records. A fitting utility is included:

```bash
python scripts/calibrate_ibtracs_wind_fragility.py \
  --observations data/calibration/pole_wind_damage_observations.csv \
  --asset-class concrete_distribution_pole \
  --pole-spacing-m 50 \
  --output config/ibtracs_wind_fragility_calibrated.json
```

The input CSV must contain `asset_class`, `wind_speed_ms`, and binary
`failed` (0 = observed non-failure, 1 = observed failure). Use actual paired
exposure/outcome records for the same component class and a consistent wind
averaging period and reference height. The fitter requires at least 20
observations, at least five failures, at least five non-failures, and
nonconstant wind speeds. It uses a regularized logistic model. The fitted
coefficients and sample counts are recorded in the output configuration.
This fitting utility does not itself establish external validation; hold out
entire storm events for validation and check calibration before use.

## Phase 7H — Weather-driven contingencies

For each storm, the current v1 implementation selects the timestamp at which
the maximum sampled branch wind across the synthetic network occurs. It then
uses the branch probabilities at that snapshot to draw reproducible Monte
Carlo samples. Each sample is applied to the canonical IEEE 33-bus topology
and reports connected components, slack-connected buses, and de-energized
buses.

This is topology-only. It does not evaluate voltage, thermal limits, protection,
AC power flow, load shedding, switching sequence, BESS support, or restoration
feasibility. Residual dependence between branch failures is not modeled; the
sampling assumes conditional independence given the reconstructed wind field.

## Configuration and execution

First confirm and edit `config/ibtracs_wind_field.json`:

- `source_fields.wind_unit`: currently `knots`, based on Digital Typhoon documentation;
- `source_fields.wind_averaging_period_minutes`: currently `10`, based on the JMA best-track convention;
- `source_fields.wind_height_m`: currently `10` as an explicit standard surface-wind modeling reference assumption, not a height field present in the CSV;
- `source_fields.source_dataset_release`: exact local release remains unverified;
- `rmw.rmw_km`: measured or explicitly selected sensitivity value;
- `wind_adjustment`: currently adds the user-selected `15 knots` to every finite numeric source observation, preserving the raw field and leaving missing values missing. This is an experimental sensitivity assumption, not a validated correction.

The unit and averaging period are supported by the Digital Typhoon/JMA source
identification. The 10 m height is an explicit modeling assumption and should
be confirmed against the exact local archive before formal publication.

After confirming the fields:

```bash
export PYTHONPATH="$(pwd):$PYTHONPATH"
python scripts/run_ibtracs_grid_hazard_pipeline.py
```

The pipeline validates fragility configuration and requires explicit permission
for uncalibrated sensitivity scenarios:

```bash
python scripts/run_ibtracs_grid_hazard_pipeline.py \
  --allow-uncalibrated-sensitivity \
  --samples-per-storm 100 \
  --seed 42
```

The second command is for research sensitivity analysis only. It does not turn
the literature curve into a locally calibrated model.

## Recommended calibration data

To calibrate Phase 7G, assemble a table with at least:
- unique asset/pole/line ID and asset class/material/age;
- accurate asset coordinates and route geometry;
- timestamped observed failure/damage status and failure mode;
- measured or reanalysis-adjusted local 10-m wind speed, averaging period,
  gust/sustained distinction, and uncertainty;
- non-failure observations and exposure windows (to avoid training only on
  failed assets);
- maintenance, vegetation, terrain, and protection covariates where available.

Fit component-specific fragility curves on event-separated training data and
evaluate calibration, discrimination, and confidence intervals on held-out
storms. Avoid using the same storm event in both fitting and validation.

## Scientific references

1. National Institute of Informatics, *Digital Typhoon Dataset* and unit documentation: https://agora.ex.nii.ac.jp/digital-typhoon/dataset/V3/index.html.en and https://agora.ex.nii.ac.jp/digital-typhoon/help/unit.html.en
2. Japan Meteorological Agency, *RSMC Best Track Data Format*: https://www.jma.go.jp/jma/jma-eng/jma-center/rsmc-hp-pub-eg/Besttracks/e_format_bst.html
3. NOAA NCEI, *IBTrACS v04r01 Technical Documentation* (2025):
   https://www.ncei.noaa.gov/sites/default/files/2025-04/IBTrACS_version4r01_Technical_Details.pdf
4. Willoughby, H. E., Darling, R. W. R., and Rahn, M. E. (2006),
   *Parametric Representation of the Primary Hurricane Vortex. Part I:
   Observations and Evaluation of the Holland (1980) Model*, Monthly Weather
   Review, 134, 1102–1120. https://doi.org/10.1175/MWR3106.1
5. Knaff, J. A., Sampson, C. R., Fitzpatrick, P. J., Jin, Y., and Hill, C. M.
   (2011), *Simple Diagnosis of Tropical Cyclone Structure via Pressure
   Gradients*, Weather and Forecasting, 26, 1020–1031.
   https://doi.org/10.1175/WAF-D-11-00013.1
6. *Reconceptualizing Reliability Indices as Metrics to Quantify Distribution
   System Resilience* (2024), Energies, 17(8), 1909. The pole curve is treated
   here as a literature-reference sensitivity function, not local calibration.
7. Qudaisat, M. and Alipour, A. (2026), *Multivariate logistic wind fragility
   functions of overhead distribution poles*, International Journal of
   Disaster Risk Reduction, 134, 105996. This recent work underscores the
   need for component and site characteristics in fragility models.

## Interpretation

The pipeline is an auditable research workflow that turns historical storm
tracks into synthetic network wind-exposure estimates and topology-only
contingency samples. It is not a forecast, utility asset model, validated
fragility model, or operational switching recommendation.


## Phase 7I — Wind and fragility sensitivity analysis

The source-wind eligibility rule is grade-aware. Digital Typhoon/JMA maximum
sustained wind is used only for grades 3, 4, and 5. Grade 2 (tropical depression)
and grade 6 (extratropical cyclone) values are treated as unavailable, not as
measured calm winds. No additive adjustment is applied to ineligible grades.

Run the sensitivity matrix after Phase 7C has generated the complete Minxiong
selected-track CSV:

```bash
export PYTHONPATH="$(pwd):$PYTHONPATH"
pytest -q tests/test_ibtracs_wind_to_contingency.py
python scripts/run_ibtracs_sensitivity_analysis.py \
  --allow-uncalibrated-sensitivity \
  --wind-adjustments-knots 0,15 \
  --rmw-km 20,30,40 \
  --pole-spacing-m 40,50,60 \
  --samples-per-storm 100 \
  --seed 42
```

The default design contains 18 combinations (2 wind offsets × 3 RMW values ×
3 pole-spacing assumptions). The random seed and sample count are held constant
across combinations to support paired comparisons. The runner writes:
- `reports/ibtracs/phase_7i/phase_7i_sensitivity_summary.csv`;
- `reports/ibtracs/phase_7i/phase_7i_branch_risk_ranking.csv`;
- `reports/ibtracs/phase_7i/phase_7i_sensitivity_manifest.json`.

The summary reports expected and sampled failed-branch counts, probability of
any branch failure, mean and 95th-percentile de-energized buses, and connected
components. Branch rankings report mean and maximum peak-event failure
probability for each branch across storms. These remain conditional sensitivity
outputs under an uncalibrated fragility curve and synthetic geometry; they are
not observed failure rates or validated electrical outcomes.

### Grade semantics and source qualification

The Digital Typhoon paper states that maximum sustained wind is recorded only
for grades 3, 4, and 5; grade 2 denotes tropical depression and grade 6 denotes
extratropical cyclone. The local CSV contains zero wind placeholders for grades
2 and 6. These values must not be converted into artificial nonzero wind by
adding a sensitivity offset. The grade-aware filter is therefore applied before
wind-field reconstruction.
