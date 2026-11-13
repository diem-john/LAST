# Phase 6B — Weather Feature Mapping to Synthetic IEEE-33 Assets

## Objective
Create a source-aware spatiotemporal mapping layer between normalized environmental observations and the synthetic geographic sample locations for 33 buses and 32 normally-closed IEEE-33 branches.

## Inputs
- Synthetic bus coordinates: `reports/geospatial/minxiong_cluster_001_ieee33_bus_locations.csv`.
- Normalized weather observations: `data/weather/normalized_weather_observations.csv`.
- The normalized weather CSV must contain:
  - `timestamp`: ISO-8601 timestamp with an explicit UTC offset.
  - `source_id`, `variable`, `value`.
  - `spatial_scope`: `point` or `regional`.
  - `time_basis`: source time convention (e.g. UTC, Asia/Taipei, LST).
  - `temporal_semantics`: e.g. `historical_observation`, `forecast`, or `scenario`.
  - `latitude`, `longitude` for point observations; may be blank for regional observations.

## Mapping rules
1. Bus samples use the synthetic coordinates from the Phase 5A bus-location CSV.
2. Branch samples use the midpoint between endpoint bus coordinates for the standard 32-branch radial topology. These are visualization-derived sample locations, not conductor routes or verified electrical assets.
3. Point observations map to the nearest of 65 sample locations in EPSG:3826. The output records distance to the source point.
4. Regional area-mean observations are broadcast unchanged to all 65 sample locations. They are not spatially downscaled and must not be interpreted as local measurements.
5. Missing values remain null. No zero substitution, imputation, or interpolation is performed.
6. Source time convention and temporal semantics are retained. Naive timestamps are rejected; local-solar-time (NASA POWER) data must only be converted after a verified time-zone interpretation. A naive LST timestamp must never be silently labeled UTC.

## Existing source interpretation
- ERA5 surface and wave time series: inspect actual coordinates, variable units, time convention, and grid structure before normalization.
- NASA POWER: source reader records local solar time (LST), not automatically UTC. Preserve the source convention until an explicit conversion is justified.
- GLDAS and TRMM Giovanni area-averaged precipitation: treat as regional area means unless gridded source data is separately acquired.
- Global Flood Database rasters: remain a separate historical event/areal hazard product. They are not rainfall forecasts, flood-depth rasters, or hourly flood labels; do not normalize them into point weather observations without a dedicated raster sampling adapter and event metadata.

## Run
First create the normalized weather CSV using source-specific, audited transformations. Then run:

```powershell
python scripts/map_weather_features_to_ieee33.py
python -m pytest -p no:dash tests/test_weather_feature_mapping.py -v
```

Outputs:
- `reports/environmental/ieee33_weather_asset_features.csv`
- `reports/environmental/ieee33_weather_asset_features.summary.json`

## Limitations
- The 33 bus locations are synthetic geographic samples, not actual Taipower assets.
- Branch midpoint samples lie on straight-line map connectors and do not represent verified electrical corridors.
- Nearest-point assignment is a spatial association, not a physical exposure model.
- Regional means have no local spatial variation.
- Forecast, historical observation, and scenario records must remain distinguishable.
- This phase does not alter the canonical IEEE-33 electrical case, power-flow solver, impedances, ratings, topology, or dispatch state.
- The mapping output is an environmental feature table, not an operational decision or grid-feasibility result.
