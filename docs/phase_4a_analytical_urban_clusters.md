# Phase 4A — Analytical urban-cluster delineation

Official urban-planning vector boundaries are excluded from the Phase 4A prerequisites at the project owner's direction. The accepted NLSC 2023 township polygons remain the administrative reference, **not** urban-planning polygons.

## Run locally

```powershell
git pull --ff-only origin last-fe-foundation
conda activate agentic_ai
pip install -r requirements-geospatial.txt
python scripts/delineate_chiayi_urban_clusters.py
```

Inputs:
- `data/geospatial/processed/chiayi_candidate_boundaries.gpkg` layer `candidate_boundaries_epsg3826`
- `data/geospatial/raw/osm/buildings/osm_chiayi_buildings.gpkg`

Outputs:
- `data/geospatial/processed/chiayi_analytical_urban_clusters.gpkg` layer `analytical_urban_clusters`
- `reports/geospatial/chiayi_urban_cluster_validation.json`

Default algorithm: overlay a globally aligned 250 m grid in EPSG:3826; clip to each township; qualify a cell if at least 3 intersecting polygon building footprints and at least 1.5% union footprint coverage; dissolve touching cells; retain components with area equivalent to at least four full grid cells. The fixed origin and thresholds allow repeatable comparison, but they are exploratory assumptions, not calibrated urban definitions.

Sensitivity checks are required before selecting an urban cluster. Vary cell size, footprint count, coverage, and minimum cluster size; inspect spatial continuity and OSM mapping completeness. Point-tagged buildings are excluded from footprint calculations. The algorithm does **not** validate road-network continuity or critical-infrastructure accessibility; these are separate subsequent stages. Some joined polygons may touch at a single point.

The script fails on missing inputs, missing CRS, invalid candidate set, empty polygon-building input, no derived clusters, or failed output read-back. A township with insufficient mapped buildings is reported as missing/insufficient, not scored zero.

No candidate suitability ranking, statutory urban-planning classification, utility network geometry, or IEEE 33-bus placement is asserted by this output. Do not interpret technical validation as representativeness, completeness, or electrical feasibility.
