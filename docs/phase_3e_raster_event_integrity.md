# LAST-FE Phase 3E: Raster event identity and spatial validation

Branch: `last-fe-foundation`

## Objective

Phase 3E follows the Phase 3D coverage audit. It checks whether event GeoTIFFs that share a grid are actually identical in their per-band pixel values and masks. It also retains event-property metadata alongside each raster fingerprint so that identical raster content associated with different event IDs or dates can be reviewed.

## Implementation

New module: `forecasting/data/raster_consistency.py`

New report:

```text
reports/data_audit/quality/raster_collection_consistency.json
```

Run:

```powershell
python -m pytest -v
python -m scripts.audit_last_fe_sources --include-rasters
```

For each raster, the audit:
- Streams every band in bounded windows.
- Computes SHA-256 fingerprints separately for pixel values and raster masks.
- Canonicalizes floating NaN payloads before hashing so equivalent NaN values do not differ solely because of payload bits.
- Records dimensions, CRS, affine transform, bounds, band descriptions, and the sibling event-properties JSON.
- Compares every raster pair and distinguishes same-grid metadata from exact per-band value-and-mask identity.
- Reports event IDs, dates, centroids, and cause fields for review when a pair is compared.

The audit does not reproject, resample, reclassify, delete, merge, or automatically deduplicate any event. A matching footprint or grid is not enough to call two rasters duplicates. An exact duplicate requires matching grid metadata and matching values and masks for every band.

## Interpretation and safeguards

- If two event records have different IDs/dates but exact raster content, treat this as a source-data integrity issue requiring provenance review. Do not count them as independent flood events until resolved.
- If two rasters share the same grid but differ in any band value or mask, they are not exact duplicates under this test.
- Matching content does not establish that the event properties are correct, that the raster is scientifically valid, or that an asset was flooded.
- Event centroids are event metadata only. They are not substituted for bus, branch, PV, BESS, hospital, or shelter coordinates.
- The existing unmasked NaN regions remain unknown. This audit fingerprints their positions but does not determine whether they encode outside-footprint, unobserved, or another product-specific state.
- The Global Flood Database event rasters are historical event products, not time-resolved forecasts. Do not derive hourly inundation labels, flood depth, or time-to-inundation from them.

## Next spatial-validation dependency

Asset-level exposure analysis remains blocked until authoritative grid GIS geometry or a documented coordinate table is available. Once supplied, a separate spatial intersection stage should:
1. Validate the coordinate reference system and geometry provenance.
2. Transform assets into each raster's CRS without modifying source rasters.
3. Sample the event flood, observation-quality, and permanent-water bands together.
4. Preserve unknown/NoData/low-observation-quality states instead of converting them to dry labels.
5. Report event-level evidence and uncertainty without inferring a 30-minute forecast from historical event maps.

Phase 3E is a data-integrity gate, not a flood model or grid-exposure certification.
