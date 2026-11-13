# Phase 6B — Source-Specific Weather Normalization

## Objective
Convert existing ERA5, NASA POWER, GLDAS, and TRMM source files into one long-form, source-aware weather table. This stage does not generate forecasts or merge historical flood-event rasters.

## Script
`scripts/normalize_weather_sources.py`

Output:
- `data/weather/normalized_weather_observations.csv`
- `data/weather/normalized_weather_observations.summary.json`

## Source handling
### ERA5 surface and wave time series
- Requires `valid_time`, `latitude`, and `longitude`.
- Uses `valid_time` as UTC.
- Preserves each grid coordinate as a point observation.
- Uses an explicit unit registry for known ERA5 variable identifiers.
- Unknown variables are excluded rather than assigned guessed units. Supply an explicit JSON variable-to-unit mapping with `--era5-units-json` if the variable's unit is verified from the source metadata.

### NASA POWER
- Uses the existing source-aware reader and preserves the source's local-solar-time (LST) convention.
- Requires explicit `--nasa-latitude` and `--nasa-longitude`; coordinates are not inferred from a free-text metadata field.
- Values are retained in source units pending source-parameter verification.
- LST timestamps are not accepted by the UTC-only spatial mapper. Do not simply append a UTC offset. A conversion requires a documented interpretation of the source's LST convention and location.

### GLDAS and TRMM Giovanni area-averaged series
- Uses the existing Giovanni metadata-aware reader.
- Retains UTC timestamps and reported bounding-box metadata.
- Retains GLDAS rainfall flux in `kg m-2 s-1`.
- Retains TRMM 3B42 precipitation rate in `mm h-1`.
- Both are regional area means, not point observations. They must not be spatially downscaled by this script.

## Run
Start with the sources that can be normalized without additional NASA POWER coordinate/time decisions:

```powershell
python scripts/normalize_weather_sources.py --skip-nasa
```

If NASA POWER coordinates are verified from the source request/configuration, include them:

```powershell
python scripts/normalize_weather_sources.py --nasa-latitude <LAT> --nasa-longitude <LON>
```

To provide units for ERA5 fields not in the built-in registry, create a JSON file such as:

```json
{
  "verified_variable_identifier": "verified unit"
}
```

Then pass `--era5-units-json path/to/era5_units.json`.

Map normalized observations to the synthetic 33-bus/32-branch sample locations:

```powershell
python scripts/map_weather_features_to_ieee33.py
```

The mapper preserves the `unit` column. It rejects naive timestamps, so NASA POWER LST records must be converted only after an explicit, documented time interpretation. For an initial mapping run, use `--skip-nasa` during normalization.

## Canonical long-form schema
- `timestamp`: UTC ISO-8601 for ERA5 and Giovanni; naive source LST for NASA POWER.
- `source_id`, `variable`, `value`, `unit`.
- `spatial_scope`: point or regional.
- `time_basis`: UTC or LST.
- `temporal_semantics`: historical reanalysis, historical observation, or satellite precipitation estimate.
- `latitude`, `longitude`: source grid point or explicit NASA POWER point coordinates.
- `source_file`, `source_temporal_resolution`, `source_spatial_support`, `source_metadata`.

## Limitations
- Source-specific units and semantics must be checked against the original dataset documentation before scientific interpretation.
- The ERA5 unit registry is deliberately finite; unrecognized variables are not silently normalized.
- NASA POWER's LST convention is not assumed equivalent to Asia/Taipei civil time.
- GLDAS/TRMM regional averages are not local exposures at each bus.
- Global Flood Database event rasters remain a separate historical areal-hazard product and require their own spatial sampling and event-time design.
- No interpolation, imputation, resampling, forecast generation, or power-system state changes are performed.
