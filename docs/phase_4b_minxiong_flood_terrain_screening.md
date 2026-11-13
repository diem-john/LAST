# Phase 4B — Minxiong Historical Flood and Terrain Screening

## Scope

This phase screens the nine frozen analytical urban clusters in Minxiong Township (Q05). It does not regenerate clusters, alter the 250 m cluster derivation, or change suitability weights. The subsequent cluster selection is documented separately in `docs/phase_4b_minxiong_cluster_selection_decision.md`.

Flood screening uses the Global Flood Database (GFD) event GeoTIFFs checked into `data/globalflooddb/`. The successful local run processed eight raster records for nine clusters. Terrain evidence is available only as a manually selected regional MOI slope summary; no verified cluster-level DEM/DTM raster is checked into the repository.

## Flood screening

Run from the repository root in the `agentic_ai` environment:

```powershell
python scripts/screen_minxiong_flood_events.py
```

Optional paths:

```powershell
python scripts/screen_minxiong_flood_events.py --clusters <path> --flood-dir <path> --output-csv <path> --output-json <path>
```

The script reads the frozen `analytical_urban_clusters` layer, selects exactly the nine Q05 clusters, and scans event rasters one directory below the flood-data directory. It pairs each raster with its event properties JSON in the same directory.

Outputs:

- `reports/geospatial/minxiong_flood_event_screening.csv`: one row per cluster/event pair.
- `reports/geospatial/minxiong_flood_event_screening.json`: event metadata, input hashes, band interpretation, results, and limitations.

### Metrics and interpretation

| Field | Meaning |
|---|---|
| `raster_grid_pixels_in_cluster` | Raster grid-cell centers falling inside the cluster geometry |
| `event_finite_pixels` | Pixels with finite values in all four event bands: flooded, duration, clear_views, clear_perc |
| `event_observation_coverage_share` | Event-finite pixels divided by raster grid pixels inside the cluster |
| `flooded_pixels` | Finite event pixels classified as flooded=1 |
| `flooded_share_of_finite_pixels` | Flooded pixels divided by finite event pixels |
| `mean_flood_duration_composite_days` | Mean duration-band value over finite event pixels |
| `mean_clear_views`, `mean_clear_perc` | Mean observation-quality values over finite event pixels |
| `permanent_water_finite_pixels`, `permanent_water_pixels` | Separate finite-pixel and permanent-water counts from the JRC band |

The GFD bands are not interchangeable:

- `flooded` is maximum observed event flood extent, not water depth.
- `duration` is the number of composite days classified as water, not continuous hourly duration.
- `clear_views` and `clear_perc` describe observation opportunity and must accompany interpretation of the flood mask.
- `jrc_perm_water` is a separate permanent-water classification and is not merged with event flooding.

Unmasked NaNs remain unknown and are excluded from denominators; they are never converted to zero. The coverage share is a raster-grid-center diagnostic, not proof of complete satellite observation. A low coverage share or weak clear-view context makes a zero flooded share inconclusive.

### Executed screening results and event inventory caveat

The successful local run generated eight raster records per cluster. The committed CSV shows event ID `2516` twice: one record has finite Minxiong observations, while another has `no_raster_bounds_overlap`. This is a source-inventory/provenance discrepancy that must be resolved from the JSON event inventory, raster paths, and hashes before counting independent events or publishing event-level summaries. Do not count the duplicate ID as two independent events.

Across the seven raster records with finite observations, all nine clusters have zero detected flooded pixels. The CSV reports the following cumulative pixel diagnostics for the shortlisted clusters:

| Cluster | Finite event pixels summed across records | Grid-center pixels summed across overlapping records | Coverage per overlapping raster record | Flooded pixels |
|---|---:|---:|---:|---:|
| Q05_cluster_001 | 182 | 196 | 92.86% | 0 |
| Q05_cluster_002 | 105 | 105 | 100% | 0 |
| Q05_cluster_009 | 35 | 35 | 100% | 0 |

These are repeated raster observations, not unique spatial pixels. The zero detections apply only to finite pixels in this limited event collection; they do not establish flood safety or absence of historical flooding. The GFD collection is not exhaustive and its pixels are coarse relative to the analytical cluster areas.

The event collection is not an exhaustive Minxiong flood history. Event rasters are retrospective event maxima, not forecasts, return-period maps, hydraulic simulations, or hourly flood labels.

## Terrain data acquisition gate

The MOI DTM Value-added Application Service was accessible when TGOS returned 403. A manually selected regional slope analysis around the Chiayi study region reported a selected area of 5.6951 km², with 83.3937% in slope class 1 (≤5%), 13.6794% in class 2 (5–15%), and 2.9268% in class 3 (15–30%); no selected area was reported in classes 4–7. This is regional context only: the polygon was manually selected, not uploaded from a Q05 cluster, and these percentages must not be represented as cluster-specific metrics. No verified DTM raster/export and no per-cluster elevation/slope statistics are currently checked into the repository. Do not substitute ERA5, a basemap, contour visualization, or a DSM for a terrain elevation raster without documenting the distinction.

A suitable official candidate source is the Taiwan Ministry of the Interior Department of Land Administration's **2026 20 m grid DTM dataset** on the Government Open Data Platform:

- Dataset page: https://data.gov.tw/dataset/178729
- Publisher: Department of Land Administration, Ministry of the Interior
- Grid spacing: 20 m
- Coverage: Taiwan main island and some outlying islands; map sheets may have different production years
- License: Open Government Data License, version 1.0
- Listed: 2026-09-30

Before terrain processing, acquire the relevant Chiayi/Minxiong sheet(s) from the dataset's resource links and record the actual file URL, sheet identifier, production year, coordinate reference system, vertical units/datum, file format, and SHA-256. Verify coverage and elevation values locally. Convert point-grid data to a raster only with a documented interpolation/resampling method; preserve the original downloaded source.

After a verified terrain raster is available, compute per-cluster elevation minimum, median, maximum, interquartile range, and slope distribution. Slope should be derived from the verified DTM using a documented method and projected metric CRS. Report NoData coverage and do not assign zero to missing terrain cells.

## Decision safeguards

- Do not combine the flood metrics into a single risk score without a separately justified method and explicit treatment of event sampling and observation quality.
- Do not interpret the number of flood-positive historical pixels as a probability, return period, or future hazard likelihood.
- Do not calculate or imply a complete six-criterion weighted suitability score while terrain and other criteria remain unavailable.
- Do not rank clusters solely by absence of detected flooding in a sparse or low-quality observation footprint.
- Keep the synthetic enhanced IEEE 33-bus benchmark distinct from actual Taipower feeder infrastructure.
- The script is an analytical screening aid only; it does not select a final cluster.

## Current status

- Frozen nine-cluster geometries: available.
- Historical GFD event raster screening: locally executed; CSV output committed. Eight raster records were processed, with a duplicate event-ID 2516 inventory issue requiring audit.
- Regional MOI DTM slope summary: manually obtained; contextual only, not cluster-specific.
- Verified 20 m DTM/DEM raster for Minxiong and cluster-level terrain statistics: not acquired.
- Lead cluster selection: Q05_cluster_001 selected for the next synthetic benchmark placement stage; Q05_cluster_002 retained as the principal alternative and Q05_cluster_009 as an additional alternative. See the separate decision record.
- No complete six-criterion weighted score is calculated; weights remain unchanged.
