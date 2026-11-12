# Phase 4A — Chiayi County Study-Area Suitability Assessment

**Status:** Methodology defined; quantitative GIS comparison pending source-layer acquisition  
**Repository branch:** last-fe-foundation  
**Network concept:** Chiayi-georeferenced synthetic enhanced IEEE 33-bus distribution benchmark  
**Geographic scope:** Chiayi County, Taiwan  
**Preferred environment:** Urban distribution network

## 1. Purpose and scope

Phase 4A selects one compact urban study area within Chiayi County for the geographic instantiation of the LAST synthetic distribution network.

The IEEE 33-bus benchmark does not provide the actual geographic coordinates of a Taipower feeder. Therefore, the project will create a synthetic, GIS-constrained geographic realization of the electrical benchmark. It must not be represented as an actual Taipower feeder, utility asset inventory, or verified field network.

The county is the regional study boundary. The selected urban planning area (or a clearly documented compact sub-area within it) is the network placement boundary. The 33-bus feeder must not be spread across the entire county.

## 2. Candidate urban areas

The initial candidate set is:

1. Taibao City (太保市)
2. Minxiong Township (民雄鄉)
3. Puzi City (朴子市)
4. Shuishang Township (水上鄉)

These are candidates for measurement, not a pre-ranked shortlist. Taibao is a useful initial candidate because it is the county administrative center, but this alone is not evidence that it is the most suitable urban distribution-network study area.

No candidate is selected until all four have been assessed using comparable geographic data, the same spatial scale, and the same scoring procedure.

## 3. Geographic data acquisition plan

Acquire source layers with coverage for all four candidates. Record provider, dataset title, access URL, retrieval date, publication/update date, license, native CRS, spatial resolution or scale, and any known coverage restrictions.

| Theme | Required data | Proposed source | Use |
|---|---|---|---|
| Administrative boundaries | County, township/city, village | NLSC / Taiwan e-Map | Consistent candidate clipping and administrative context |
| Urban planning | Official urban planning boundaries and zoning | NLSC / National Land Planning Information System | Identify actual planned urban areas and suitable land-use context |
| Roads | Road centerlines, road class, intersections | NLSC Taiwan e-Map | Road density, intersection density, routing proxy |
| Buildings and blocks | Building footprints or blocks | NLSC Taiwan e-Map | Built-up density and urban morphology |
| Population | Small-area population counts/density | Ministry of the Interior / official statistical sources | Urban activity and demand-context proxy |
| Land use | Built-up, residential, commercial, industrial, public-facility classes | NLSC land-use datasets | Urban-use composition and placement constraints |
| Flood potential | Scenario-based inundation extent/depth layers | Water Resources Agency (WRA) | Flood-hazard relevance and exposure diversity |
| Rivers/drainage | Rivers, channels, drainage and water-system layers | NLSC / WRA | Hydrological context; not a substitute for flood maps |
| Elevation | DEM / terrain model | NLSC or other authoritative Taiwan source | Elevation and slope screening |
| Critical facilities | Hospitals, emergency shelters, public facilities | Authoritative government facility registries | Check availability of realistic critical-facility reference points |

### Official source entry points

- NLSC Taiwan e-Maps: https://www.nlsc.gov.tw/en/cp.aspx?n=2149
- NLSC map service and layer catalogue: https://maps.nlsc.gov.tw/pro/009_layer_en.html
- National Land Planning Information Network: https://ngis.nlma.gov.tw/
- WRA flood potential map information: https://www.wra.gov.tw/cp.aspx?n=6244
- Taiwan Government Open Data — Flood Potential Map: https://data.gov.tw/en/datasets/25766
- NCDR disaster potential map portal: https://dmap.ncdr.nat.gov.tw/

The NLSC describes Taiwan e-Map thematic layers including roads, railways, water systems, administrative boundaries, blocks, buildings, landmarks, and control points. The NLSC map catalogue also exposes disaster-potential layers, including multiple flood scenario layers and shelter-related layers. The national planning portal supports querying urban and non-urban land-use zoning and environmental/disaster layers.

WRA flood-potential maps are scenario-based model products. They are appropriate for planning and preparedness analysis, but they are not forecasts of a future typhoon's rainfall process or inundation timing. Record scenario rainfall, depth class, model extent, and product version when using them.

## 4. Suitability criteria and weights

Use a transparent weighted multi-criteria assessment. The weights below are the proposed study design and must be fixed before calculating candidate scores.

| Criterion | Weight | Operational definition |
|---|---:|---|
| Urban built-up intensity | 25% | Built-up footprint or built-up land-use share within the candidate urban boundary |
| Road-network connectivity | 20% | Road length density, intersection density, and connectedness of the routable road graph |
| Critical-infrastructure context | 15% | Verified availability and spatial distribution of hospitals, shelters, and public facilities |
| Flood-hazard relevance | 20% | Coverage by official flood-potential scenarios and diversity of modeled hazard classes |
| Terrain suitability | 10% | Elevation and slope distribution; identify unsuitable or extreme terrain |
| Geographic compactness | 10% | Ability to define a contiguous, compact network placement area with adequate urban coverage |
| **Total** | **100%** | |

### 4.1 Scoring scale

Normalize each criterion to a score between 0 and 1 using a consistent, documented method.

- For positive indicators (e.g. built-up intensity), higher normalized values indicate stronger suitability.
- For negative indicators (e.g. excessive slope or fragmented urban area), use an explicitly inverted or penalty-based normalization.
- For flood relevance, do not simply maximize inundation. Reward the ability to study meaningful variation in exposure while retaining a plausible urban network setting. Extreme hazard exposure is not automatically a better study area.
- For critical facilities, distinguish facility availability from actual asset locations. Public facility points can serve as references for synthetic critical-asset placement only after their identity, status, and location are verified.

For candidate area a:

S(a) = 0.25 U(a) + 0.20 R(a) + 0.15 C(a) + 0.20 F(a) + 0.10 T(a) + 0.10 G(a)

where U is urban built-up intensity, R is road connectivity, C is critical-infrastructure context, F is flood-hazard relevance, T is terrain suitability, and G is geographic compactness.

Do not compute or publish S(a) until all required input layers have passed coverage and quality checks.

### 4.2 Measurement consistency

- Use the same source release and measurement date for all candidates wherever possible.
- Use the same spatial resolution, buffer policy, and normalization method across candidates.
- Use official urban planning polygons as the primary comparison units when available.
- If candidate polygons differ greatly in size, report both raw and area-normalized measures.
- Do not compare a township-wide score for one candidate with a small downtown polygon for another.
- Record missing layers as unavailable; do not silently impute them as zero.
- Include sensitivity analysis for weights (at minimum, compare the proposed weights with equal weights and a flood-priority scenario).
- Preserve raw metrics alongside normalized scores so the ranking can be audited.

## 5. Candidate evaluation protocol

For each of Taibao, Minxiong, Puzi, and Shuishang:

1. Acquire its official urban planning boundary or document the exact alternative boundary source.
2. Validate geometry, CRS, completeness, and date.
3. Clip roads, buildings, land use, population, flood scenarios, terrain, and facilities to a common comparison extent.
4. Calculate raw metrics for all six criteria.
5. Check data completeness and comparability.
6. Normalize all metrics using shared rules.
7. Calculate the weighted score and rank.
8. Run weight sensitivity analysis.
9. Inspect candidate maps to identify obvious boundary/data artifacts.
10. Document the preferred candidate and the runner-up, with reasons.

### Minimum GIS metrics

- Built-up share = built-up land area / comparison polygon area.
- Building density = building footprint area / comparison polygon area, with building count density reported separately if useful.
- Road density = total road-centerline length / comparison polygon area.
- Intersection density = eligible road intersections / comparison polygon area.
- Road connectedness = connected-component and graph connectivity diagnostics for the extracted road network.
- Critical-facility availability = verified facilities by type and their distribution; do not treat counts alone as actual electrical asset locations.
- Flood-scenario coverage = proportion of comparison area represented by official flood layers, plus area by scenario/depth class where metadata permits.
- Terrain suitability = slope and elevation distribution, with explicit thresholds justified by the study.
- Compactness = polygon compactness and fragmentation metrics, supplemented by visual inspection.

## 6. Study-area decision gate

Select one candidate only if:

- Its official boundary or reproducible study polygon is available.
- All core layers have adequate and comparable coverage.
- The candidate has a sufficiently compact urban footprint for a 33-bus synthetic feeder.
- Road and building data support plausible geographic placement.
- Flood and terrain data support the intended hazard-resilience experiments.
- The ranking is not highly unstable under reasonable weight changes, or the instability is explicitly discussed.

If the top candidates are statistically or practically close, prefer the one with better source-data completeness and more reproducible boundaries, not an arbitrary tie-break.

The output of this gate is a selected urban study polygon, a candidate comparison report, and a data provenance manifest.

## 7. Synthetic IEEE 33-bus placement methodology

After selecting the study area, construct the geographic realization while preserving the electrical benchmark.

### 7.1 Electrical topology invariants

- 33 buses.
- 32 fixed branches.
- 3 normally open tie branches.
- Tie 33: Bus 21–8.
- Tie 34: Bus 9–15.
- Tie 35: Bus 25–29.
- Preserve all original electrical impedances, load assignments, and switching states.
- Preserve LAST's established substation, PV, BESS, hospital, shelter, and flood-exposed-bus assignments.
- Do not infer geographic coordinates from bus numbers or electrical connectivity.

### 7.2 Coordinate reference

Use TWD97 / TM2 zone 121 (EPSG:3826) as the proposed working CRS for metric distance and area calculations in Chiayi. Preserve each source layer's native CRS and transform explicitly. Record CRS transformations in metadata.

### 7.3 Placement stages

1. **Study polygon:** Freeze the selected urban boundary and a reproducible placement mask.
2. **Candidate points:** Generate eligible candidate locations from road junctions, public infrastructure access points, and suitable urban locations. Avoid uniform random placement across the county.
3. **Substation anchor:** Select a plausible anchor within the urban area using documented siting constraints. This is a synthetic anchor, not a real substation.
4. **Bus placement:** Assign the remaining bus nodes using topology-aware optimization and reproducible seeds.
5. **Special assets:** Place hospital and shelter nodes near verified facility references where appropriate; place PV/BESS nodes at plausible facility/building/land-use sites. Clearly mark the final bus-to-facility relationship as synthetic.
6. **Branch routing:** Route electrical edges over a road-network-informed corridor graph. Road routes are proxies for plausible utility corridors, not verified pole or cable alignments.
7. **Tie branches:** Generate geographic paths for the three tie edges while retaining their normally open electrical status.
8. **Validation:** Check topology invariants, coordinate validity, polygon containment, branch geometry, route continuity, and reproducibility.

### 7.4 Geographic optimization concept

Minimize:

J = lambda1 C_length + lambda2 C_crossing + lambda3 C_corridor + lambda4 C_compactness + lambda5 C_constraints

where bus coordinates and routed branch geometries are optimized jointly. The terms penalize excessive branch length, unnecessary crossings, deviation from plausible corridors, excessive spatial spread, and violation of placement constraints.

This is a geographic placement objective only. It does not replace electrical power-flow, voltage, protection, or operational feasibility analysis.

## 8. Required outputs

Phase 4A should produce:

- data/geospatial/raw/ — immutable downloaded source layers.
- data/geospatial/processed/ — normalized and clipped comparison layers.
- data/geospatial/synthetic/ — generated bus, branch, and synthetic asset geometries.
- reports/geospatial/source_manifest.json — source metadata and provenance.
- reports/geospatial/candidate_metrics.csv — raw metrics for all four candidates.
- reports/geospatial/candidate_scores.json — normalized scores, weights, and sensitivity results.
- reports/geospatial/study_area_decision.md — selected candidate and rationale.
- reports/geospatial/placement_validation.json — geometry and topology validation results.
- data/geospatial/synthetic/chiayi_ieee33_synthetic.gpkg — final GIS package, after validation.

## 9. Scientific safeguards

1. Describe the output as a **Chiayi-georeferenced synthetic IEEE 33-bus network**.
2. Do not claim the coordinates or routes are actual Taipower infrastructure.
3. Keep the electrical benchmark and geographic realization independently versioned.
4. Do not use proximity to a river as a flood label.
5. Do not interpret missing raster values as dry or safe.
6. Do not interpret historical flood maps as hourly or 30-minute forecasts.
7. Do not treat modeled flood-potential scenarios as observed event inundation.
8. Preserve raw source data, metadata, licenses, and retrieval dates.
9. Make every stochastic placement reproducible with fixed seeds and recorded parameters.
10. Do not claim hospital/shelter service, BESS support, islanding feasibility, or switching feasibility from geographic placement alone.

## 10. Current status and next action

**Completed in this document:** Candidate set, official source entry points, weighted assessment framework, measurement protocol, placement design, outputs, and scientific safeguards.

**Not yet completed:** Download and validation of GIS source layers, quantitative candidate metrics, candidate ranking, final study polygon, and synthetic bus coordinates.

**Next action:** Acquire the official Chiayi County urban planning, road, building, land-use, flood-potential, terrain, population, and critical-facility layers. Then calculate the four-candidate comparison. Do not generate final bus coordinates before the study-area decision gate passes.
