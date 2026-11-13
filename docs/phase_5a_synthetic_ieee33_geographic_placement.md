# Phase 5A — Synthetic IEEE 33-Bus Geographic Placement

## Objective

Generate an initial, reproducible geographic representation of the standard 33-bus radial benchmark inside the selected frozen analytical urban cluster `Q05_cluster_001` in Minxiong Township.

This stage creates **synthetic bus coordinates and a separate topology representation**. It does not identify actual Taipower assets, customer loads, substations, conductors, utility corridors, or service territories.

## Inputs

- Frozen cluster layer: `data/geospatial/processed/chiayi_analytical_urban_clusters.gpkg`, layer `analytical_urban_clusters`.
- OSM road geometry: `data/geospatial/raw/osm/roads/osm_chiayi_roads_edges.gpkg`, layer `osm_chiayi_roads_edges`.
- Selected cluster ID: `Q05_cluster_001`.
- Metric CRS: EPSG:3826 (TWD97 / TM2 zone 121).

The script validates input files, layers, CRS, geometry integrity, and the uniqueness of the selected cluster.

## Placement method

1. Reproject the selected cluster and OSM road layer to EPSG:3826.
2. Clip road geometries to the selected cluster polygon.
3. Sample candidate points along clipped road segments at a configurable 60 m spacing.
4. Place bus 1 at the road candidate nearest the cluster centroid. This is a geographic reference point only, not a real substation.
5. Place buses 2–33 using deterministic greedy farthest-point sampling: repeatedly select the remaining candidate with the greatest minimum Euclidean distance from already selected points.
6. Assign the standard IEEE 33-bus radial branch list independently of geographic placement.
7. Export bus points and topology connectors to separate GeoPackage layers, and export a coordinate CSV and provenance JSON.

The sampling is deterministic for identical input geometry and software behavior. Candidate spacing controls the candidate pool resolution; it is not an electrical design spacing rule. The farthest-point method spreads locations across available road geometry but does not optimize load allocation or electrical performance.

## Standard topology

The benchmark contains 33 buses and 32 radial branches. Branch endpoints are recorded in the JSON report and as attributes in the `synthetic_topology_connectors` layer.

The map connector geometry is a straight line between the coordinates of the endpoint buses. It is solely a visualization of the benchmark's abstract branch adjacency; it must not be interpreted as a conductor path, cable length, impedance, or actual utility infrastructure.

## Outputs

- `data/geospatial/processed/minxiong_cluster_001_ieee33_synthetic.gpkg`
  - `synthetic_bus_locations`: 33 point features with bus ID, role, coordinates, and placement basis.
  - `synthetic_topology_connectors`: 32 line features with from/to bus IDs and explicit visualization-only geometry semantics.
- `reports/geospatial/minxiong_cluster_001_ieee33_bus_locations.csv`: bus coordinates in EPSG:3826 and longitude/latitude.
- `reports/geospatial/minxiong_cluster_001_ieee33_placement.json`: input hashes, placement parameters, topology, validation checks, and limitations.

## Run locally

From the repository root in the `agentic_ai` environment:

```powershell
python scripts/place_ieee33_minxiong_cluster.py
```

Optional candidate spacing and output overrides:

```powershell
python scripts/place_ieee33_minxiong_cluster.py --candidate-spacing-m 60 --output-gpkg <path> --output-csv <path> --output-json <path>
```

Run focused tests:

```powershell
python -m pytest tests/test_ieee33_spatial_placement.py -q
```

## Validation and interpretation

The script checks that 33 bus IDs are present, all selected coordinates lie inside the selected cluster, and the topology has 32 unique branches spanning bus IDs 1–33. Unit tests cover topology cardinality, deterministic point selection, and insufficient candidate handling.

A successful script run is not a substitute for inspecting the generated map and checking the geometry against the source layers. Review the output before accepting it as the study's final synthetic placement.

## Explicit exclusions

- No inference of actual Taipower feeder routes, substations, poles, transformers, customers, or load coordinates.
- No claim that OSM road centerlines represent electrical corridors.
- No electrical line length, impedance, voltage drop, short-circuit, protection, power-flow, reliability, or islanding calculation.
- No BESS sizing, placement optimization, or dispatch.
- No autonomous operational decision-making. The LLM remains advisory only; any operational decision requires deterministic engineering validation and authorized operator action.

## Current status

- Selected study-area cluster: documented in the Phase 4B decision record.
- Placement script and unit tests: committed; local execution by the project owner is required to generate the GeoPackage/CSV/JSON outputs.
- Geographic placement acceptance: pending local execution and visual review.
