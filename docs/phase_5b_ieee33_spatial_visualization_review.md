# Phase 5B — Split Geographic Placement and Abstract Topology Visualization

## Objective
Generate two separate publication-quality figures from the Phase 5A synthetic IEEE 33-bus benchmark. Keep all 33 geographic coordinates and the standard 32-branch radial topology unchanged. The coordinates and abstract branch adjacency were generated independently; overlaying straight lines between them produced dense intersections that could be mistaken for actual feeder routes.

## Inputs
- `data/geospatial/processed/minxiong_cluster_001_ieee33_synthetic.gpkg`: layers `synthetic_bus_locations` and `synthetic_topology_connectors`.
- Frozen `Q05_cluster_001` from `chiayi_analytical_urban_clusters.gpkg`.
- OSM roads from `osm_chiayi_roads_edges.gpkg`.

No bus coordinates, branch endpoints, cluster boundaries, or Phase 5A placement parameters are changed.

## Figure A — Geographic placement
Output: `reports/geospatial/minxiong_cluster_001_ieee33_geographic_placement.png`.
Shows the frozen cluster boundary, contextual OSM roads, and all 33 synthetic bus markers/IDs. It deliberately omits topology connectors. This figure communicates the location of synthetic benchmark points, not electrical connectivity.

## Figure B — Abstract IEEE 33-bus topology
Output: `reports/geospatial/ieee33_abstract_radial_topology.png`.
Shows all 33 bus IDs and 32 standard radial branches using a deterministic breadth-first layered schematic rooted at bus 1. Horizontal position indicates topological depth only. Node positions and edge lengths have no geographic or electrical meaning.

## Additional outputs
- `reports/geospatial/minxiong_cluster_001_ieee33_spatial_review.json`: validation results and figure semantics.
- `reports/geospatial/minxiong_cluster_001_ieee33_branch_review.csv`: branch endpoints and straight-line distances between synthetic geographic coordinates. These are not conductor lengths or impedances.

## Run locally
From the repository root in the `agentic_ai` environment:
```powershell
python scripts/visualize_ieee33_minxiong_placement.py
python -m pytest tests/test_ieee33_spatial_visualization.py -q
```

## Interpretation and limitations
- Bus coordinates are synthetic research locations, not actual Taipower assets, customers, verified loads, or substations. Bus 1 is a geographic slack-reference anchor only.
- OSM roads are context only and are not electrical corridors.
- The abstract topology figure is a schematic of standard IEEE benchmark adjacency.
- The previous 158 nonincident connector crossings are cartographic diagnostics, not an electrical metric. They do not justify relocating buses or changing the benchmark topology.
- No electrical parameterization, power flow, voltage, losses, protection, reliability, islanding, BESS feasibility, or operational feasibility is evaluated.

## Human acceptance checklist
- [ ] Geographic map shows all 33 bus labels clearly within the frozen cluster.
- [ ] Road context is visible but does not overwhelm the bus markers.
- [ ] Abstract topology contains 33 buses and 32 branches.
- [ ] Bus 1 is the root of the schematic.
- [ ] Branch adjacency matches the Phase 5A standard IEEE branch list.
- [ ] Captions distinguish synthetic geographic placement from abstract benchmark topology.

The script sets `decision_status` to `split_figures_generated_human_acceptance_pending`. It does not automatically accept the placement.

## Next gate
After inspecting both figures and confirming the checklist, explicitly accept or request revision. Only then proceed to Phase 5C electrical benchmark parameterization and deterministic power-flow validation.
