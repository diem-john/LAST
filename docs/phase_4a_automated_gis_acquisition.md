# Phase 4A — Automated GIS Acquisition

## What is implemented

The acquisition module is at `forecasting/geospatial/acquisition.py`.

Supported adapters:

- `osmnx`: OpenStreetMap road graphs and tagged features (buildings, mapped hospitals, etc.).
- `http`: exact, explicitly configured HTTP(S) resource URLs.
- `wfs`: exact WFS service URL and feature type name.

Government adapters are deliberately disabled in the starter configuration until an exact downloadable resource URL or WFS endpoint/layer has been verified. The code does not guess undocumented endpoints.

## Install optional dependencies

Activate the LAST environment and install:

```powershell
conda activate agentic_ai
pip install -r requirements-geospatial.txt
```

The main `requirements.txt` is intentionally unchanged; geospatial acquisition dependencies are optional.

## Dry run (default; offline and no writes)

From the repository root:

```powershell
python -m forecasting.geospatial.acquisition
```

Dry run reads the configuration and prints the planned enabled sources. It does not make network requests, create output folders, download files, or modify the manifest.

Select specific sources:

```powershell
python -m forecasting.geospatial.acquisition --source osm_chiayi_roads --source osm_chiayi_buildings
```

## Live acquisition

Live mode is explicit:

```powershell
python -m forecasting.geospatial.acquisition --live
```

Only sources with `"enabled": true` are run. The initial config enables OSM roads, buildings, and mapped hospital features. These are community-mapped contextual data, not official facility inventories or verified utility assets.

To run only roads:

```powershell
python -m forecasting.geospatial.acquisition --live --source osm_chiayi_roads
```

## Configure official resources

Edit `config/geospatial_sources.json`. Before enabling an official source:

1. Identify the exact official dataset/resource and current release.
2. Confirm its download URL or WFS endpoint and layer identifier from the provider's documentation/catalogue.
3. Record license, source CRS, scale/resolution, coverage, and known limitations.
4. Set `enabled` to `true` and populate `download_url` (HTTP adapter) or `service_url` + `type_name` (WFS adapter).
5. Keep the landing page URL separate from the actual download/service URL.

### Official boundary and planning sources researched (2026-11-12)

- NLSC/MOI township-boundary catalogue: `https://data.gov.tw/en/datasets/7441`. The catalogue describes township/town/city/district boundaries, fields including `COUNTYNAME`, `TOWNNAME`, and `TOWNENG`, and Open Government Data License 1.0. Its linked TGOS archive is registered in the config as `nlsc_township_boundaries`, but remains **disabled** because the linked archive filename indicates 2025-03-18 while MOI/NLSC announced a newer administrative-boundary update in August 2026. The TGOS resource also returned HTTP 403 during automated retrieval. Do not activate it until the archive release is reconciled with the August 2026 update and local access is confirmed.
- NLSC download catalogue: `https://maps.nlsc.gov.tw/pro/download.jsp`. It lists official county/city, township, and village boundary archives; verify the specific release date and CRS from the selected archive metadata before use.
- NGIS planning portal: `https://ngis.nlma.gov.tw/`. The national land-use zoning WMTS network service became fee-based for private applicants from 2026-01-01. The public planning map viewer allows visual querying, but a map view is not a downloadable vector dataset. `ngis_urban_planning_zoning` is therefore registered but disabled pending an authorized vector export or county-government GIS release.

The township boundary archive is a candidate source for administrative clipping only; it is **not** an urban-planning polygon. Administrative township boundaries must not be substituted for official urban planning area boundaries in the candidate scoring methodology. The four candidates may contain multiple urban planning districts or non-urban land, so the exact planning polygon coverage must be checked independently.

No official WRA or NCDR download endpoint is enabled until its exact resource has been verified.

## Output and provenance

Acquired files are stored in the configured `output_dir`. The manifest is merged at:

`reports/geospatial/source_manifest.json`

For each successful acquisition it records provider, title, adapter, retrieval time, source URL, local file paths, byte count, SHA-256 hashes, CRS/scale/license fields when known, coverage, limitations, and adapter-specific details.

Successful downloads are marked `acquired_unvalidated`, not `validated`. Acquisition is not a substitute for geometry/raster integrity, CRS, candidate coverage, or license validation.

ZIP extraction is opt-in per HTTP source via `"extract_zip": true`; archive path traversal is rejected. Original archives are retained.

## Important scientific and operational limits

- OSM coverage is community-contributed and can be incomplete. Verify hospitals/shelters with official registries.
- OSM roads are routing/context proxies, not actual Taipower conductor or cable corridors.
- The current OSM queries retrieve Chiayi County as an initial source area. The final analysis must clip to comparable official urban planning polygons for Taibao, Minxiong, Puzi, and Shuishang. Administrative township boundaries are useful for candidate filtering but are not a substitute for urban planning polygons.
- Flood potential, DEM, population, and authoritative planning data remain unconfigured until exact official resources are selected.
- Never interpret modeled flood-potential layers as typhoon-specific forecasts.
- The module does not select a study area or generate synthetic IEEE 33-bus coordinates.

## Tests

```powershell
python -m pytest tests/test_geospatial_acquisition.py -v
```

The tests cover dry-run no-write behavior, disabled sources, manifest merging, SHA-256 calculation, and duplicate source-ID rejection. They do not perform live network downloads.

## Overpass reliability and partial failures

OSM source entries support:

- `retry_attempts` (default 4)
- `retry_initial_delay_seconds` (default 15)
- `retry_max_delay_seconds` (default 90)
- optional `overpass_url` (only set to a verified, reachable endpoint)

Transient capacity/HTTP gateway/timeout errors use exponential backoff. Permanent configuration errors are not retried. Each source is isolated: a failed source is recorded as `acquisition_failed` and the runner continues with the next enabled source. In live mode the manifest is written with both successful and failed outcomes. The CLI returns exit code 2 if any source failed, even if other sources succeeded.

The runner does not automatically switch to an unverified third-party Overpass endpoint. If the default public endpoint remains overloaded, configure a documented alternative or retry later. Avoid repeated rapid requests to public Overpass infrastructure.

## GIS technical validation

After acquiring the OSM files, run:

```powershell
python -m pytest tests/test_geospatial_validation.py -v
python -m forecasting.geospatial.validation
```

The validator checks file existence and SHA-256 hashes, reads vector layers, checks geometry validity and CRS transformation to EPSG:3826, and checks road GraphML node/edge structure and coordinates. It writes `reports/geospatial/validation_report.json` and merges technical validation outcomes into the source manifest.

A `validated` status is limited to technical integrity. It does not certify completeness, positional accuracy, facility operational status, or official utility status. Candidate-level metrics remain blocked until comparable official urban-planning polygons for Taibao, Minxiong, Puzi, and Shuishang are acquired and validated. See `docs/phase_4a_gis_validation.md`.


## Accepted Chiayi candidate administrative boundaries

The project accepts the archived NLSC/MOI `TOWN_MOI_1120317` township boundary dataset (source revision 2023-03-13) as its authoritative **project reference** for administrative candidate boundaries. This is a project ground-truth designation and does not claim the archive is the newest administrative release.

The archive and extracted source files are retained under:

`data/geospatial/raw/nlsc/boundaries/original/`

`data/geospatial/raw/nlsc/boundaries/extracted/`

The four candidate records are identified by stable source IDs:

| Candidate | TOWNID | TOWNCODE |
|---|---|---|
| Taibao City | Q12 | 10010010 |
| Minxiong Township | Q05 | 10010050 |
| Puzi City | Q02 | 10010020 |
| Shuishang Township | Q13 | 10010120 |

Prepare the two-layer GeoPackage from the repository root:

```powershell
python scripts/prepare_chiayi_candidate_boundaries.py
```

The script writes:

- `data/geospatial/processed/chiayi_candidate_boundaries.gpkg`
  - `candidate_boundaries_source_crs`: selected source geometries with the embedded source CRS preserved.
  - `candidate_boundaries_epsg3826`: the same four features transformed to EPSG:3826, with projected area in km².
- `reports/geospatial/chiayi_candidate_boundary_validation.json`: source/output hashes, CRS metadata, feature counts, geometry checks, and candidate areas.

The script selects by `TOWNID`, checks that exactly four unique candidates are present, rejects missing/empty/invalid candidate geometries, transforms with `to_crs(EPSG:3826)`, and reopens both output layers for read-back validation. It never modifies the original source files. It also records the generated product and hash in `reports/geospatial/source_manifest.json`.

The source CRS is represented by the embedded `.prj` WKT (`GCS_TWD97[2020]`). Its automatic EPSG identification may return `None`; this is not a reason to relabel the source coordinates. Preserve the WKT and use the explicit PyProj/GeoPandas transformation to EPSG:3826.

Canonical Chinese candidate names are added as project attributes; original source fields are retained. The source DBF's Chinese text encoding may vary by GDAL/DBF interpretation, so the script requests UTF-8 and records the selected read mode. English names and TOWNIDs are used for deterministic feature selection.

**Scope limit:** these are administrative township boundaries, not urban-planning polygons. Their areas must not be interpreted as urban built-up area, and they do not replace official planning polygons needed for candidate suitability scoring.
