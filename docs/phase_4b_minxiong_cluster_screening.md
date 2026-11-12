# Phase 4B — Minxiong Cluster-Level Spatial Screening

## Purpose and scope

This workflow screens the nine already-derived analytical urban clusters in
Minxiong Township (Q05). It does not regenerate clusters, change the frozen
250 m clustering parameters, compare townships, run sensitivity analysis, or
calculate the original six-criterion weighted suitability score.

The output provides descriptive spatial context for subsequent selection of
one compact cluster for placement of the synthetic enhanced IEEE 33-bus
benchmark. No final cluster is selected by the script.

## Inputs

The script reads these existing GeoPackage layers:

- `data/geospatial/processed/chiayi_analytical_urban_clusters.gpkg`,
  layer `analytical_urban_clusters`; only `town_id == Q05` is used.
- `data/geospatial/raw/osm/roads/osm_chiayi_roads_edges.gpkg`,
  layer `osm_chiayi_roads_edges`.
- `data/geospatial/raw/osm/facilities/osm_chiayi_hospitals.gpkg`,
  layer `osm_chiayi_hospitals`.

All geometries are transformed to EPSG:3826 before metric calculations.
The script validates input presence, CRS, geometry integrity, expected
Minxiong cluster count, unique cluster IDs, and expected road/hospital geometry
types. SHA-256 hashes are recorded in the JSON report.

## Run

From the repository root in the `agentic_ai` environment:

```powershell
python scripts/screen_minxiong_clusters.py
```

Optional path overrides:

```powershell
python scripts/screen_minxiong_clusters.py --clusters <path> --roads <path> --hospitals <path> --output-csv <path> --output-json <path>
```

## Metrics

| Metric | Definition |
|---|---|
| Area | Projected cluster polygon area (km²) |
| Perimeter | Projected perimeter (km) |
| Compactness | (4\pi A/P^2), approaching 1 for a circle |
| Largest component share | Largest polygon component area / total cluster area |
| Intersecting road features | Number of OSM road-line features intersecting the cluster |
| Clipped road length | Sum of road-line lengths clipped to the cluster (km) |
| Road length density | Clipped road length / cluster area (km/km²) |
| Intersecting hospital features | Number of OSM hospital polygons intersecting the cluster |
| Nearest hospital distance | Straight-line polygon-to-polygon distance (km) to the nearest mapped OSM hospital |

Road line features are measured after geometric intersection with each cluster.
Overlapping source features can contribute separately. The hospital distance is
not road-network travel distance.

## Outputs

- `reports/geospatial/minxiong_cluster_screening.csv`: one row per Minxiong cluster.
- `reports/geospatial/minxiong_cluster_screening.json`: metric definitions,
  input hashes, results, and limitations.

## Interpretation safeguards

- OSM road density is a geometric transport-context proxy, not route quality,
  travel-time accessibility, utility-corridor access, or electrical connectivity.
- OSM roads are not Taipower electrical assets.
- OSM hospital features are discovery data; identity, operational status,
  capacity, and completeness are not verified. Zero mapped intersections does
  not mean no healthcare facility exists.
- Compactness can be affected by point-touching components; inspect
  largest-component share and geometry before network placement.
- Flood, terrain, population, and official planning criteria remain unscored.
  Missing criteria are not zero and weights are not redistributed.
- This is within-Minixiong cluster screening, not a township re-ranking.
- The script does not select a final cluster. Review the CSV and spatial map
  before deciding which cluster can host the synthetic benchmark.
- The enhanced IEEE 33-bus system remains a synthetic Chiayi-georeferenced
  benchmark, not an actual Taipower feeder.
