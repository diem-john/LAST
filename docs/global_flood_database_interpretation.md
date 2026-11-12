# Global Flood Database raster interpretation for LAST-FE

## Purpose and source

This note defines how the checked-in Global Flood Database (GFD) event GeoTIFFs may be interpreted in LAST-FE. It is a source-interpretation safeguard, not a flood model or asset-exposure assessment.

The downloaded GeoTIFF product documentation identifies each raster as a maximum observed flood-extent map for a Dartmouth Flood Observatory (DFO) event, derived from Terra/Aqua MODIS observations. The event archive names use:

`DFO_eventID_From_startDate_to_endDate.tif`

The event ID links the raster to the DFO event record. Preserve the complete event identifier and start/end dates as event metadata; do not infer a local grid impact time from the filename alone.

Official references:
- Global Flood Database GeoTIFF Information (Cloud to Street / Dartmouth Flood Observatory; last updated 2021-07-19): https://storage.googleapis.com/gfd_metadata/README_GFD.pdf
- Google Earth Engine catalog: https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1
- Tellman et al. (2021), Nature, DOI: https://doi.org/10.1038/s41586-021-03695-w

## Five-band interpretation

| Band | Product meaning | LAST-FE interpretation |
|---|---|---|
| `flooded` | Maximum observed flood-water extent during the event; 1 = surface water, 0 = no water | Historical event observation, not a forecast or water-depth estimate |
| `duration` / `flood_duration` | Number of composite days classified as water; 3-day MODIS composites are used | Event-duration indicator, not a continuous hourly inundation duration |
| `clear_views` | Number of cloud-free observations during the event | Observation-opportunity / quality context |
| `clear_perc` | Percentage of clear observations among observations for the event | Observation-opportunity / quality context |
| `jrc_perm_water` | JRC Global Surface Water permanent-water layer; 1 = permanent water, 0 = non-water | Keep separate from event flood extent; use to contextualize possible permanent-water detections |

The Earth Engine catalog describes the collection as 913 mapped events from 2000–2018 and lists 30 m band pixel size, while the downloadable GeoTIFF README describes approximately 250 m pixels (0.0022458 degrees). For the checked-in GeoTIFFs, use the actual raster transform, dimensions, and CRS read from each file as the authoritative grid geometry; do not silently assume the Earth Engine catalog's nominal pixel size applies to the downloaded GeoTIFF.

## Important observation limitations

- Maps represent the maximum observed extent during the event period, not a time-resolved flood hydrograph.
- The source README states that 2- or 3-day composites reduce cloud-shadow false detections but can miss rapid or flash floods, increasing false negatives for transient flooding.
- Cloud observation bands must accompany interpretation of the flood mask. A low clear-view opportunity weakens confidence in a zero-valued flood observation.
- A finite `flooded=0` pixel is a product-classified no-water observation; it must not be treated as strong evidence of no flood when observation quality is poor.
- The `jrc_perm_water` band is a separate permanent-water classification. Do not simply count all water in `flooded` as event flood exposure without checking permanent-water context and the product's event classification.
- Product accuracy reported in the README is an overall study-level statistic; it is not a guarantee for every event, pixel, local asset, or Taiwan grid location.

## NaN and valid-pixel handling in this repository

The current integrity reports show:
- GeoTIFFs have no declared NoData value and Rasterio reports an all-valid mask.
- Many pixels are nevertheless NaN (non-finite but unmasked).
- The official product documentation describes the bands and event-generation method but does not specify how NaN pixels in these particular downloaded GeoTIFFs encode spatial coverage or observation eligibility.

Therefore, **do not classify these NaNs as corruption, dry land, flooded land, or confirmed outside-footprint pixels**. Keep three states distinct in downstream processing:
1. finite product value (eligible for interpretation subject to band semantics and observation quality);
2. unmasked non-finite value (unknown/undetermined until its spatial and source encoding is verified);
3. masked/NoData pixel (if present in another source/version).

The current raster audit correctly reports these states separately. Before constructing labels, add a spatial diagnostic that maps finite/NaN patterns across bands and compare it with the source archive's event metadata and any original download-side masks. A raster footprint or bounding-box overlap is not proof that a particular asset was observed or flooded.

## Rules for LAST-FE modelling

1. Treat GFD as historical event-observation data for retrospective validation or carefully designed spatial/event feature extraction. It is not a live flood feed.
2. Do not derive hourly labels, water depth, time-to-inundation, or 30-minute forecasts from these event maximum-extent rasters.
3. Preserve event ID, start/end dates, source file, raster transform/CRS, band names, and quality bands with every derived sample.
4. Never replace NaNs with zero before establishing their meaning.
5. If a candidate pixel is finite and `flooded=1`, retain permanent-water and clear-view context before assigning an event-flood label.
6. If a candidate pixel is finite and `flooded=0`, retain clear-view context; do not treat low-observation pixels as reliable negative labels.
7. Asset-level exposure requires authoritative bus/branch/DER/critical-load coordinates or geometry in the same spatial reference workflow. Electrical topology, event centroids, and raster bounds are not substitutes.
8. Any asset exposure result is an observational intersection, not a switching recommendation or proof of electrical consequence.

## Current repository status and remaining gates

The seven checked-in event rasters have full-pixel quality and integrity reports under `reports/data_audit/quality/`. Those reports count finite and non-finite pixels, but the current repository has no verified grid-asset geometry. Asset-level intersection therefore remains blocked.

Before GFD-derived labels are admitted to a training dataset:
- resolve and document the NaN/coverage semantics from the exact downloaded GeoTIFFs or source-side export;
- inspect the event's clear-view and clear-percentage bands at each candidate pixel;
- account for permanent-water context;
- verify event date and location relevance to the target study region;
- establish asset geometry independently;
- document any spatial resampling and avoid implying finer resolution than the source raster supports.

