# Phase 4A — GIS Source Acquisition Register

**Status:** Source entry points verified; downloadable source files and coverage are not yet validated  
**Branch:** `last-fe-foundation`  
**Candidates:** Taibao, Minxiong, Puzi, Shuishang  
**Working CRS:** TWD97 / TM2 zone 121 (EPSG:3826)

## 1. Acquisition objective

Build a reproducible, comparable GIS source stack for the four candidate urban areas. This register distinguishes an authoritative portal from an actual acquired dataset. A portal being accessible does not establish that a particular layer has been downloaded, that Chiayi coverage exists, or that the layer is suitable for scoring.

Do not calculate candidate scores until the source files, coverage, dates, CRS, resolution/scale, license, and candidate completeness have been checked.

## 2. Verified official source entry points

| Theme | Provider / portal | Entry point | Acquisition status | Notes |
|---|---|---|---|---|
| Administrative boundaries | National Land Surveying and Mapping Center (NLSC), MOI | https://maps.nlsc.gov.tw/pro/download.jsp | Portal verified; file not acquired | Select the current county/city and township boundary release. NLSC's August 2026 notice reports updated administrative boundary data. |
| Roads, buildings, blocks, water systems, landmarks | NLSC Taiwan e-Maps | https://www.nlsc.gov.tw/en/cp.aspx?n=2149 | Portal verified; files not acquired | NLSC identifies SHP/GML thematic data. Confirm exact release, scale, and Chiayi County coverage. |
| Layer catalogue / map services | NLSC | https://maps.nlsc.gov.tw/pro/009_layer_en.html | Catalogue verified; service endpoints not yet resolved | Catalogue lists road/water layers and disaster-potential layers, including flood scenarios and shelters. |
| Urban planning / zoning | National Land Planning Information Network | https://ngis.nlma.gov.tw/ | Portal identified; layer access not validated | Obtain official urban planning boundaries and zoning for each candidate; record planning-area name and legal/version date. |
| Flood potential | Water Resources Agency (WRA), MOEA | https://www.wra.gov.tw/cp.aspx?n=6244 | Information page verified; GIS files not acquired | Identify the current generation and scenario layers covering all four candidates. Preserve depth/scenario attributes and metadata. |
| Flood potential metadata | Taiwan Government Open Data | https://data.gov.tw/en/datasets/25766 | Metadata page verified; target resource not selected | The dataset description states that these are modeled scenarios under stated assumptions, not forecasts of future typhoon rainfall/inundation processes. |
| Disaster-potential layers | National Science and Technology Center for Disaster Reduction (NCDR) | https://dmap.ncdr.nat.gov.tw/ | Portal verified; files not acquired | Portal includes data analysis/download functions. Confirm layer licensing, version, and candidate coverage. |
| Terrain / topographic data | NLSC download portal | https://maps.nlsc.gov.tw/pro/download.jsp | Portal verified; DEM resource not selected | Choose a consistent DEM release/resolution covering all candidates. Do not substitute a basemap image for elevation data. |
| Population | Directorate-General of Budget, Accounting and Statistics / MOI statistical portals | https://www.stat.gov.tw/ | Portal identified; table not selected | Select a consistent small-area population table and reference date. Record whether values are census, household registration, or estimates. |
| Critical facilities | Official health/emergency-management registries; NLSC shelter layers as a discovery source | https://maps.nlsc.gov.tw/pro/009_layer_en.html | Registry dataset not selected | Verify facility identity, operational status, coordinates, and reference date. A map symbol alone is not proof of facility status. |

## 3. Acquisition order

1. Download the current official county/township boundaries and confirm the four candidate polygons.
2. Obtain official urban planning boundaries and zoning. This determines the comparison units; do not substitute whole-township boundaries for urban planning areas without documenting the reason.
3. Obtain NLSC road, building/block, water-system, and landmark layers from the same compatible release where possible.
4. Obtain a common land-use layer and population table/reference year.
5. Obtain WRA flood-potential scenario layers and associated metadata; verify that the same scenario generation covers all four candidates.
6. Obtain a common-resolution DEM and derive slope only after CRS/resolution checks.
7. Obtain authoritative hospital and emergency-shelter registries; cross-check NLSC shelter points rather than treating them as the sole authority.
8. Record every file in `reports/geospatial/source_manifest.json` before processing.

## 4. Required manifest fields

Each acquired layer must record:

- `theme`, `provider`, `dataset_title`, `resource_title`
- `landing_page_url`, `download_url` (actual resource URL, not a guessed endpoint)
- `retrieved_at_utc`, `published_or_updated_at`
- `license`, `native_crs`, `scale_or_resolution`
- `coverage_description`, `file_path`, `file_sha256`
- `status`, `limitations`, `candidate_coverage_checked`

Use `portal_verified_resource_pending` until a concrete resource has been selected. Use `acquired_unvalidated` after download and before QA. Only use `validated` after geometry/raster integrity, coverage, CRS, metadata, and license checks pass.

## 5. Data acceptance checks

- Preserve downloaded files unchanged under `data/geospatial/raw/`.
- Calculate SHA-256 hashes and record exact filenames.
- Check archive integrity and all component files (including shapefile sidecars).
- Check CRS metadata; never assign EPSG:3826 to coordinates without evidence. Reproject from the documented native CRS.
- Check geometry validity, empty geometries, duplicate features, and spatial coverage.
- For rasters, record pixel size, transform, nodata, dimensions, band descriptions, and valid-data footprint.
- Confirm all four candidates are covered by each comparison layer.
- Keep source vintages consistent. If not possible, record the mismatch and exclude the layer from direct scoring until justified.
- Record missing/unavailable layers explicitly; do not impute zero.
- Do not use a web map screenshot, tiled basemap, or unverified third-party export as a substitute for authoritative vector/raster source data.

## 6. Flood-map interpretation constraint

WRA / government flood-potential maps are modeled scenario products. Their scenario rainfall, model assumptions, flood-depth classes, and valid spatial extent must be retained. They can inform pre-disaster planning and comparative hazard context; they must not be described as observed flood events, a typhoon-specific forecast, or a 30-minute inundation prediction.

## 7. Current acquisition decision

No GIS source file has been acquired or validated by this register. Therefore:

- no candidate metrics or weighted scores are available;
- no candidate ranking is justified;
- no final urban study polygon is selected;
- no synthetic IEEE 33-bus bus/branch coordinates should be generated yet.

**Next implementation step:** acquire the exact official resources, populate the manifest, and run source-level QA before implementing the four-candidate metrics pipeline.

## 8. Source notes

- NLSC Taiwan e-Maps describes thematic data including roads, railways, water systems, administrative boundaries, blocks, buildings, landmarks, and control points, with SHP/GML formats.
- NLSC's layer catalogue lists road/water and disaster-potential layers, including flood scenario and shelter-related layers.
- MOI/NLSC announced an August 2026 update to administrative boundary data.
- The government flood-potential dataset description explicitly cautions that modeled flood-potential maps do not simulate the rainfall process and flooding situation of a future typhoon event.

These notes describe portal metadata, not proof that a specific downloadable resource has been acquired.
