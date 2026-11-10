# LAST-FE foundation (Phase 1)

## Purpose

LAST-FE is the source-aware historical-data and forecasting layer for Project LAST. Its output is intended to become structured context for the local, air-gapped RAG/LLM advisory application. Forecasting and deterministic grid validation remain outside the LLM.

## Current repository data inventory

- ERA5: two single-level time-series CSV exports. Inspect their schemas before source-specific transformations.
- IBTrACS: data/ibtracs/typhoon_data.csv. Inspect its schema before storm-track features are engineered.
- NASA POWER: data/nasapower/nasapow.csv. Inspect its schema and units before deriving solar or meteorological features.
- Global Flood Database: event folders contain raster, properties, and license/readme files. Validate CRS, transform, band meaning, nodata, and spatial overlap with grid assets before extracting labels.
- GLDAS Noah 0.25-degree 3-hourly precipitation rate: observed records 2010-01-01 00:00 UTC through 2014-12-31 21:00 UTC.
- TRMM 3B42 v7 0.25-degree 3-hourly precipitation rate: observed records 2009-12-31 22:30 UTC through 2019-12-31 19:30 UTC; fill value -9999.9 is missing.

The rainfall CSVs are stored under data/imerg/ for historical reasons, but neither is a GPM IMERG product. Canonical source IDs are GLDAS_NOAH025_3H and TRMM_3B42_V7. The Giovanni requested date range is not the observed coverage. Source date limits are accepted constraints, not ingestion errors.

## Implemented utilities

- load_area_averaged_precipitation parses Giovanni metadata separately and derives coverage from observed rows.
- normalize_precipitation converts GLDAS kg m-2 s-1 to mm/hr and 3-hour accumulation; TRMM mm/hr is retained and converted to 3-hour accumulation. Unsupported source IDs fail closed.
- validate_time_series reports invalid timestamps, duplicates, and cadence mismatches without imputing records.
- add_precipitation_history creates trailing rolling summaries. Sort chronologically and split train/test chronologically before model fitting to avoid leakage.
- forecast_schema defines a conservative advisory payload with explicit modes and limitations.

## Recommended experiments

1. GLDAS-only historical experiments (2010-2014).
2. TRMM-only historical experiments (2010-2019).
3. Paired-source comparison over 2010-2014. Document timestamp alignment explicitly because TRMM timestamps are offset by 90 minutes from GLDAS.
4. Compare each source against persistence and simple climatological baselines before introducing deep models.

Do not concatenate GLDAS and TRMM as one homogeneous series. Do not claim blending improves performance without ablation evidence.

## Important limits

- Historical rainfall products do not provide current rainfall observations or a live flood forecast.
- LiPAD spatial flood maps alone do not establish time-to-inundation forecasts.
- Global Flood Database event centroids do not prove overlap with grid assets; inspect georeferenced raster coverage first.
- ERA5, IBTrACS, and NASA POWER parsers are intentionally not guessed in this phase. Inspect actual headers, units, time zones, and missing-value conventions first.
- No operational switching, islanding feasibility, BESS dispatch, or protection decision is made by this package. Those require deterministic grid analysis and authorized operator action.

## Local verification

From the repository root:

    python -m pip install -r requirements.txt
    python -m pytest -q

This change adds the data foundation only. It does not claim model training, forecast accuracy, or end-to-end application integration has been completed.