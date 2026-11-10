# LAST-FE Phase 3B: Full-record data quality and spatial validation

Run from the repository root on `last-fe-foundation`:

```powershell
python -m scripts.audit_last_fe_sources --include-rasters
```

The script retains the existing schema/sample reports and adds full-record quality reports under `reports/data_audit/quality/`.

## Generated quality reports

- `era5_sfc_full_quality.json`: full-record hourly timestamp and numeric-column diagnostics.
- `era5_wav_full_quality.json`: full-record diagnostics; confirms whether wave variables remain absent beyond the initial sample.
- `nasa_power_full_quality.json`: hourly diagnostics while preserving timezone-naive local solar time (LST). LST is not silently converted or relabelled as UTC.
- `gldas_noah_3h_quality.json` and `trmm_3b42_v7_quality.json`: source-specific fill handling, original-unit statistics, normalized precipitation-rate and 3-hour accumulation statistics, duplicate timestamps, and cadence checks.
- `ibtracs_quality.json`: aggregate metadata missingness and per-instance timestamp quality using year/month/day/hour.
- `*_full_raster_quality.json`: streaming full-pixel finite-value statistics and value counts for the band explicitly described as `flooded`.

## Interpretation and safeguards

1. The ERA5 CSVs are loaded in full for quality profiling. The existing `audit_csv` sample report remains available as a compact schema preview.
2. NASA POWER time fields are local solar time (LST) and remain timezone-naive. A later fusion step must define and document a defensible temporal alignment convention.
3. GLDAS Noah and TRMM 3B42 v7 remain separate products. Their timestamp offset must be handled explicitly; do not join by row index or silently shift timestamps.
4. Fill markers are excluded from normalized precipitation statistics. Original source values remain in the ingestion frame.
5. IBTrACS instance metadata is retained; no rows are dropped or imputed by the quality audit.
6. Raster scanning reports full-pixel statistics only. It does not infer flood depth, flood timing, or exposure of any LAST grid asset.
7. Asset-level flood validation is deliberately marked incomplete until verified bus/branch coordinates or authoritative geometries are supplied. Raster bounding-box overlap alone is not evidence of asset exposure.
8. Historical Global Flood Database rasters do not provide live flood forecasts.

## Tests

Run:

```powershell
python -m pytest -v
```

The test suite covers timestamp gaps/duplicates, LST handling, precipitation fill values and units, IBTrACS metadata quality, and full raster pixel accounting when rasterio is installed.

## Expected outcome

A completed run establishes reproducible source-quality diagnostics. It does not automatically certify data as model-ready. Model readiness still depends on reviewing the generated reports, validating spatial representativeness, and defining target-specific train/validation/test splits without temporal leakage.
