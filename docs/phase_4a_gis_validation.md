# Phase 4A — GIS Integrity and Spatial Validation

## Purpose

Run a reproducible technical validation pass over acquired OSM GeoPackages and
road GraphML. The validator does not modify acquired source files or calculate
study-area suitability scores.

## Run

From the repository root in the `agentic_ai` environment:

```powershell
python -m pytest tests/test_geospatial_validation.py -v
python -m forecasting.geospatial.validation
```

The default target CRS is EPSG:3826. It can be overridden with
`--target-crs EPSG:3826`. Optional paths can be supplied using `--manifest`,
`--report`, and `--root`.

## Checks

- Acquired file presence, byte size, and SHA-256 comparison with the manifest.
- GeoPackage/vector layer readability and feature counts.
- Geometry types, missing/empty/invalid geometries, source CRS, and coordinate
  transformation to EPSG:3826.
- Road GraphML node/edge counts, node coordinate presence/finiteness, and
  connected-component count.
- Validation outcomes merged into the acquisition manifest.

Outputs:

- `reports/geospatial/validation_report.json`
- Updated `reports/geospatial/source_manifest.json`

## Interpretation and limitations

A source marked `validated` has passed the technical checks applicable to its
file types. This is not a certification of mapping completeness, positional
accuracy, facility operational status, or official utility status.

Road graph component count is descriptive; disconnected components are not
automatically errors. The validator does not infer routing quality.

Candidate-level coverage metrics are deliberately not computed until
comparable official urban-planning polygons for Taibao, Minxiong, Puzi, and
Shuishang have been acquired and validated. No suitability scores or candidate
rankings are generated here.

OSM hospital features remain discovery data requiring identity and operational
status verification. OSM road geometry is not Taipower conductor/cable
geometry. Building footprints may be incomplete.

## Dependencies

Uses the optional Phase 4A geospatial stack: GeoPandas, Shapely, Pyogrio or
Fiona, and NetworkX. These packages are imported when the relevant checks run.
