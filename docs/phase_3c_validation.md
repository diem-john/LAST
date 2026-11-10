# LAST-FE Phase 3C: Physical and raster integrity validation

Branch: `last-fe-foundation`

## Scope

Phase 3C adds diagnostics before forecasting dataset construction. It does not train models, alter source values, impute missing values, clip outliers, resample timestamps, or infer grid-asset exposure.

Run from the repository root:

```powershell
python -m pytest -v
python -m scripts.audit_last_fe_sources --include-rasters
```

## New outputs

- `reports/data_audit/quality/era5_sfc_physical_screening.json`: unit semantics and broad screening-range flags for the ERA5 surface variables found in the source. Ranges are conservative review screens, not universal physical-validity limits.
- `reports/data_audit/quality/*_raster_integrity.json`: full-pixel counts separating masked/NoData pixels, finite unmasked pixels, and unmasked NaN/Inf pixels. Includes raster transform, bounds, CRS, NoData and mask flags.

## ERA5 interpretation safeguards

- Temperature, pressure, wind, cloud, precipitation, and radiation fields are described with expected ERA5 units in `forecasting/data/physical_validation.py`.
- `slhf` is treated as signed accumulated energy; negative values are not automatically flagged as invalid.
- `ssrd`, `strd`, `fdir`, and `tp` are accumulated variables. Do not convert them to hourly rates or fluxes until the original CDS request metadata and accumulation windows are verified.
- Screening flags do not remove records. Review them against the exact source product, forecast step, and extraction metadata before deciding on cleaning rules.
- The fully missing `sst` variable remains unusable. The wave file remains excluded from the current feature candidates because its measured wave fields are entirely missing.

## Raster interpretation safeguards

The previous raster scan found large counts of unmasked non-finite pixels. The new integrity report distinguishes those from pixels masked by raster NoData/mask metadata. A raster with many unmasked NaN/Inf values must not be converted into a flood label raster without investigating the source encoding and product documentation.

The `flooded` band is counted only where its description is exactly `flooded`. Value counts are diagnostics, not proof of event exposure at a LAST asset. Permanent-water band values must remain distinct from event-flood values.

## Grid geometry repository inspection

The `last-fe-foundation` repository tree was inspected recursively for GIS and asset-coordinate artifacts. The repository contains the enhanced IEEE 33-bus benchmark PDF and the operational SOP, but no GeoJSON, Shapefile, GeoPackage, or explicit bus/branch coordinate file was found in the tracked tree.

Therefore:
- No bus, branch, PV, BESS, hospital, or shelter coordinate is invented.
- Raster bounds or centroid proximity are not used as evidence of exposure.
- Asset-level flood intersection remains blocked until authoritative GIS geometry or a documented coordinate table is supplied.
- Electrical topology is not a substitute for geographic geometry.

## Remaining Phase 3C work

1. Run the updated tests and audit locally.
2. Review the new ERA5 screening flags and raster integrity counts.
3. Locate/provide authoritative grid asset geometry before performing spatial intersections.
4. Verify the Global Flood Database product documentation for band semantics, event observation window, and valid-pixel interpretation before deriving flood labels.

A completed audit still does not certify predictive skill or live flood-forecast capability.
