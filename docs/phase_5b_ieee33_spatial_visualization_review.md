# Phase 5B — Synthetic IEEE 33-Bus Spatial Visualization and Review

## Objective

Create a reproducible, publication-quality map of the Phase 5A synthetic IEEE 33-bus placement in the frozen Minxiong analytical cluster `Q05_cluster_001`. Generate a machine-readable review report and branch-connector length table to support human inspection before any later electrical modeling.

## Inputs

- `data/geospatial/processed/minxiong_cluster_001_ieee33_synthetic.gpkg`
  - `synthetic_bus_locations`
  - `synthetic_topology_connectors`
- `data/geospatial/processed/chiayi_analytical_urban_clusters.gpkg`, layer `analytical_urban_clusters`
- `data/geospatial/raw/osm/roads/osm_chiayi_roads_edges.gpkg`, layer `osm_chiayi_roads_edges`

The selected cluster and Phase 5A bus coordinates are treated as frozen inputs. This phase does not relocate buses, modify branch endpoints, or change the IEEE 33-bus topology.

## Review procedure

1. Validate 33 unique bus IDs (1–33), 32 topology connectors, declared coordinate reference systems, and containment of every bus point within the selected cluster.
2. Reproject the layers to EPSG:3826 for metric display.
3. Draw the cluster boundary, contextual clipped OSM roads, bus points with IDs, and straight-line topology connectors.
4. Detect geometric intersections between connector pairs that do not share a bus endpoint. These are cartographic flags for visual inspection only.
5. Export a branch table with straight-line connector lengths, explicitly labelled as visualization geometry rather than conductor lengths.
6. Export a JSON report containing validation checks, crossing details, outputs, and limitations.

## Run locally

From the repository root in the `agentic_ai` environment:

```powershell
python scripts/visualize_ieee33_minxiong_placement.py
```

Run focused tests:

```powershell
python -m pytest tests/test_ieee33_spatial_visualization.py -q
```

## Outputs

- `reports/geospatial/minxiong_cluster_001_ieee33_network_map.png` — 300-DPI map.
- `reports/geospatial/minxiong_cluster_001_ieee33_spatial_review.json` — structural checks and nonincident connector-intersection flags.
- `reports/geospatial/minxiong_cluster_001_ieee33_branch_review.csv` — branch endpoint IDs and straight-line map-connector lengths.

## How to interpret the map and diagnostics

- Bus markers are synthetic benchmark locations generated on sampled OSM road geometry. They are not actual electrical assets, customers, or verified load points.
- Bus 1 is a geographic slack-reference anchor only, not a verified substation.
- OSM roads are context only and are not electrical corridors.
- Blue connectors encode abstract IEEE 33-bus topology using straight lines. They are not conductor routes, line lengths, or impedance estimates.
- A nonincident connector crossing is a geometric review flag. It is not an electrical fault or proof of physical conductor crossing.
- The minimum bus separation is descriptive only, not an engineering siting threshold.

## Human acceptance checklist

Review the generated map at full resolution and record the outcome separately:

- [ ] All 33 bus labels are legible and no marker is unintentionally obscured.
- [ ] Bus points appear inside the selected cluster boundary.
- [ ] The spatial distribution is understandable and does not create misleading visual clustering.
- [ ] The topology connectors are visually traceable; dense intersections are reviewed against the branch table.
- [ ] Every nonincident connector crossing reported in the JSON has been visually inspected.
- [ ] Any proposed coordinate correction is justified and versioned; do not silently change the frozen Phase 5A placement.
- [ ] The synthetic nature of the network and visualization-only connector semantics are retained in figures and captions.

Acceptance is a human research-design decision. The script intentionally leaves `decision_status` as `visual_review_required_no_placement_acceptance_inferred`; a successful run does not accept the placement automatically.

## Explicit exclusions

This phase does not infer actual Taipower assets, load locations, substation positions, electrical corridors, or conductor routes. It does not calculate electrical impedances, power flow, voltage, losses, protection, reliability, islanding, BESS feasibility, or operational actions. The LAST LLM remains advisory only; operational decisions require deterministic engineering validation and authorized operator action.

## Next gate

Do not begin electrical parameterization or power-flow analysis until the map and review report have been inspected and the synthetic placement has been explicitly accepted or revised.
