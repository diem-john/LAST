# Phase 4A — Automated GIS Acquisition

## What is implemented

The acquisition module is at \`forecasting/geospatial/acquisition.py\`.

Supported adapters:

- \`osmnx\`: OpenStreetMap road graphs and tagged features (buildings, mapped hospitals, etc.).
- \`http\`: exact, explicitly configured HTTP(S) resource URLs.
- \`wfs\`: exact WFS service URL and feature type name.

Government adapters are deliberately disabled in the starter configuration until an exact downloadable resource URL or WFS endpoint/layer has been verified. The code does not guess undocumented endpoints.

## Install optional dependencies

Activate the LAST environment and install:

\`\`\`powershell
conda activate agentic_ai
pip install -r requirements-geospatial.txt
\`\`\`

The main \`requirements.txt\` is intentionally unchanged; geospatial acquisition dependencies are optional.

## Dry run (default; offline and no writes)

From the repository root:

\`\`\`powershell
python -m forecasting.geospatial.acquisition
\`\`\`

Dry run reads the configuration and prints the planned enabled sources. It does not make network requests, create output folders, download files, or modify the manifest.

Select specific sources:

\`\`\`powershell
python -m forecasting.geospatial.acquisition --source osm_chiayi_roads --source osm_chiayi_buildings
\`\`\`

## Live acquisition

Live mode is explicit:

\`\`\`powershell
python -m forecasting.geospatial.acquisition --live
\`\`\`

Only sources with \`"enabled": true\` are run. The initial config enables OSM roads, buildings, and mapped hospital features. These are community-mapped contextual data, not official facility inventories or verified utility assets.

To run only roads:

\`\`\`powershell
python -m forecasting.geospatial.acquisition --live --source osm_chiayi_roads
\`\`\`

## Configure official resources

Edit \`config/geospatial_sources.json\`. Before enabling an official source:

1. Identify the exact official dataset/resource and current release.
2. Confirm its download URL or WFS endpoint and layer identifier from the provider's documentation/catalogue.
3. Record license, source CRS, scale/resolution, coverage, and known limitations.
4. Set \`enabled\` to \`true\` and populate \`download_url\` (HTTP adapter) or \`service_url\` + \`type_name\` (WFS adapter).
5. Keep the landing page URL separate from the actual download/service URL.

No official NLSC, WRA, or NCDR download endpoint is hard-coded until its exact resource has been verified.

## Output and provenance

Acquired files are stored in the configured \`output_dir\`. The manifest is merged at:

\`reports/geospatial/source_manifest.json\`

For each successful acquisition it records provider, title, adapter, retrieval time, source URL, local file paths, byte count, SHA-256 hashes, CRS/scale/license fields when known, coverage, limitations, and adapter-specific details.

Successful downloads are marked \`acquired_unvalidated\`, not \`validated\`. Acquisition is not a substitute for geometry/raster integrity, CRS, candidate coverage, or license validation.

ZIP extraction is opt-in per HTTP source via \`"extract_zip": true\`; archive path traversal is rejected. Original archives are retained.

## Important scientific and operational limits

- OSM coverage is community-contributed and can be incomplete. Verify hospitals/shelters with official registries.
- OSM roads are routing/context proxies, not actual Taipower conductor or cable corridors.
- The current OSM queries retrieve Chiayi County as an initial source area. The final analysis must clip to comparable official urban planning polygons for Taibao, Minxiong, Puzi, and Shuishang.
- Flood potential, DEM, population, and authoritative planning data remain unconfigured until exact official resources are selected.
- Never interpret modeled flood-potential layers as typhoon-specific forecasts.
- The module does not select a study area or generate synthetic IEEE 33-bus coordinates.

## Tests

\`\`\`powershell
python -m pytest tests/test_geospatial_acquisition.py -v
\`\`\`

The tests cover dry-run no-write behavior, disabled sources, manifest merging, SHA-256 calculation, and duplicate source-ID rejection. They do not perform live network downloads.
