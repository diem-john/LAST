# Phase 7C — IBTrACS regional filtering and visualization

## Purpose

This phase derives regional screening products from
\`reports/ibtracs/ibtracs_tracks.csv\`. It does not modify or discard the
complete processed IBTrACS source table.

## Run

From the repository root:

\`\`\`bash
export PYTHONPATH="$(pwd):$PYTHONPATH"
python scripts/filter_visualize_ibtracs_regions.py
\`\`\`

Optional thresholds:

\`\`\`bash
python scripts/filter_visualize_ibtracs_regions.py \\
  --taiwan-radius-km 500 \\
  --minxiong-radius-km 300
\`\`\`

## Selection definitions

- **Western North Pacific:** a storm is selected when at least one observation
  lies inside the screening box (default longitude 100–180°E, latitude 0–60°N).
  The full track is retained. This rectangle is an analysis envelope, not an
  official WMO basin polygon.
- **Taiwan vicinity:** a storm is selected when any observed position lies
  within the configured great-circle radius (default 500 km) of the approximate
  Taiwan reference point (23.7°N, 121.0°E). This is a proximity screen, not
  distance to the coastline or an official administrative boundary.
- **Minxiong synthetic-grid approach:** a storm is selected when any observation
  lies within the configured distance (default 300 km) of its nearest synthetic
  IEEE 33-bus sample point. It does not represent verified Taipower asset or
  branch-corridor exposure.

For all three selections, complete storm tracks are retained once a storm
qualifies. This preserves approach and departure context. Hourly observations
may not capture the exact continuous closest approach.

## Outputs

Default output directory: \`reports/ibtracs/regional/\`

- \`ibtracs_wnp_tracks.csv\`
- \`ibtracs_wnp_storm_summary.csv\`
- \`ibtracs_taiwan_vicinity_tracks.csv\`
- \`ibtracs_taiwan_vicinity_storm_summary.csv\`
- \`ibtracs_minxiong_synthetic_grid_approach_tracks.csv\`
- \`ibtracs_minxiong_synthetic_grid_approach_storm_summary.csv\`
- \`ibtracs_regional_filter_audit.json\`
- \`figures/ibtracs_wnp_tracks.png\`
- \`figures/ibtracs_taiwan_vicinity_tracks.png\`
- \`figures/ibtracs_minxiong_approaches.png\`

Maps are static longitude/latitude plots created locally with Matplotlib. They
do not download or depend on online coastline tiles. Coastlines are therefore
not drawn in this initial reproducible stage.

## Interpretation safeguards

- Wind and pressure remain raw IBTrACS source values; no units are inferred.
- The maps show best-track positions, not forecast tracks.
- The Taiwan reference-point radius and Minxiong threshold are configurable
  exploratory screening parameters, not validated hazard thresholds.
- Synthetic-bus proximity is not physical wind exposure, failure probability,
  or damage estimation.
- This stage does not calculate branch-level outage probabilities or create
  weather-driven LAST-Q contingencies.
