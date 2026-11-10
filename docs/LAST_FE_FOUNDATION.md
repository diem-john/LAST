# LAST-FE foundation (Phase 1)

## Purpose

LAST-FE is the source-aware historical-data and forecasting layer for Project LAST. Its output is intended to become structured context for the local, air-gapped RAG/LLM advisory application. Forecasting and deterministic grid validation remain outside the LLM.

## Current repository data inventory

- ERA5: two single-level time-series CSV exports. Inspect their schemas before source-specific transformations.
- IBTrACS: each `data/ibtracs/metadata/<instance_id>.csv` represents one typhoon instance and is paired with `data/ibtracs/image/<instance_id>/`. The filename stem is the association key. `data/ibtracs/typhoon_data.csv` is obsolete and must not be used.
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

## Phase 2: schema and raster audit tooling

The branch now includes a schema-first audit utility:

- `forecasting/data/audit.py` samples CSV columns, null counts, parse ratios, sample values, and numeric ranges without assigning unverified units or semantic roles.
- `scripts/audit_last_fe_sources.py` audits ERA5 and NASA POWER sources, audits each IBTrACS instance CSV against its matching image folder, and separately parses the two Giovanni precipitation exports so metadata rows are not mistaken for a CSV header.
- IBTrACS audit reports metadata row counts, `file_*` image references, missing referenced HDF5 files, unreferenced HDF5 files, metadata instances without image folders, and image folders without metadata. Missing images do not cause metadata rows to be discarded.
- Raster sample statistics exclude NaN and infinite values; non-finite sample counts are reported separately.
- Optional Global Flood Database raster inspection reports raster driver, dimensions, CRS, affine transform, bounds, resolution, nodata, and band metadata. Install `rasterio` separately to enable it.
- Reports are written under `reports/data_audit/` by default and are generated locally; they are not committed as data-derived outputs.

Run from the repository root:

    python scripts/audit_last_fe_sources.py

To include raster metadata:

    python -m pip install rasterio
    python scripts/audit_last_fe_sources.py --include-rasters

The audit deliberately does not infer units from column names, assign storm-track fields, or interpret flood raster pixel values as water depth. Review the resulting source reports and authoritative product documentation before implementing source-specific feature transforms. Raster bounds alone do not establish overlap with LAST buses; asset coordinates or authoritative grid GIS geometry are still required for that test.

The GitHub connector could not return the contents of the large ERA5, IBTrACS, and NASA POWER CSV files for direct inspection in this session. Consequently, their actual schemas remain unaudited here; the local audit script is provided to inspect them in the repository environment. No source-specific transformation or spatial-overlap result is claimed yet.


### IBTrACS instance structure and validation

The authoritative repository layout is:

```text
data/ibtracs/
├── metadata/
│   └── <instance_id>.csv
└── image/
    └── <instance_id>/
        └── *.h5
```

Each metadata CSV is one typhoon instance. Its filename stem is matched to the image folder with the same identifier. The CSV may contain one or more `file_*` reference columns. The audit checks referenced files inside that instance folder and reports missing references without dropping metadata records. The image archive may be incomplete in the repository; the audit records that incompleteness rather than assuming the full image collection is present.

Run tests with:

    python -m pytest -v

The raster regression test is skipped automatically when the optional `rasterio` dependency is unavailable. To run it, install rasterio in the project environment.
