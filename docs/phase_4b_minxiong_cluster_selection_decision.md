# Phase 4B — Minxiong Final Analytical Cluster Selection

**Decision status:** Selected lead analytical cluster for synthetic benchmark placement, subject to remaining data and engineering validation  
**Decision date:** 2026-11-13  
**Township:** Minxiong Township (民雄鄉), Chiayi County, Taiwan  
**Selected cluster:** `Q05_cluster_001`  
**Alternative retained:** `Q05_cluster_002`  
**Additional alternative:** `Q05_cluster_009`  
**Branch:** `last-fe-foundation`

## 1. Decision

Select **`Q05_cluster_001` as the lead analytical urban cluster** for the next LAST study-area refinement and synthetic enhanced IEEE 33-bus benchmark placement workflow.

This is a documented project screening decision, not a complete six-criterion weighted suitability result, a flood-safety certification, a statutory urban boundary, or confirmation of an actual Taipower feeder. The cluster is selected because it offers the strongest combined scale and mapped road-access context among the reviewed candidates, while retaining acceptable historical GFD observation coverage in the available raster sample.

Keep `Q05_cluster_002` as the principal alternative because it has complete raster-grid-center observation coverage and a more balanced area/road-density profile. Keep `Q05_cluster_009` as a compact, high-road-density alternative.

## 2. Evidence basis

### 2.1 Cluster geometry and road context

The frozen Phase 4B cluster screening metrics report:

| Metric | Q05_cluster_001 | Q05_cluster_002 | Q05_cluster_009 |
|---|---:|---:|---:|
| Area (km²) | **1.875** | 1.000 | 0.250 |
| Perimeter (km) | 8.000 | 7.000 | 2.500 |
| Compactness (4πA/P²) | 0.3682 | 0.2565 | **0.5027** |
| Intersecting OSM road features | **312** | 197 | 94 |
| Clipped OSM road length (km) | **33.317** | 20.852 | 8.062 |
| OSM road length density (km/km²) | 17.769 | 20.852 | **32.248** |
| Intersecting mapped OSM hospital polygons | 0 | 0 | 0 |
| Nearest mapped OSM hospital polygon (km) | 3.564 | 3.937 | 6.595 |

Cluster 001 has the largest area, the most intersecting mapped road features, and the greatest total clipped road length. Its compactness is higher than cluster 002's, although lower than cluster 009's. Cluster 009 has the highest road density and compactness but is substantially smaller.

OSM road features are contextual transport/accessibility proxies only. They are not electrical distribution lines, utility corridors, or verified road-network travel times. Zero intersecting OSM hospital polygons does not establish that no healthcare facility exists; OSM completeness is unverified.

### 2.2 Historical Global Flood Database screening

The locally executed screening completed for nine frozen Q05 clusters. The committed CSV contains eight raster records per cluster. Across the records with finite event-band observations:

| Metric | Q05_cluster_001 | Q05_cluster_002 | Q05_cluster_009 |
|---|---:|---:|---:|
| Finite event pixels summed across records | 182 | 105 | 35 |
| Grid-cell-center pixels summed across overlapping records | 196 | 105 | 35 |
| Observation coverage share per overlapping raster record | 92.86% | 100% | 100% |
| Flooded pixels | 0 | 0 | 0 |

All finite event pixels in these available records had `flooded=0`. This means no event-flood pixels were detected in the finite sampled cells of this limited collection. It does **not** mean zero flood risk, no historical flooding, or future safety.

The collection requires a provenance audit before treating its file count as a count of independent events: eight TIFF records are present, but event ID `2516` appears twice in the CSV, with one raster record yielding finite Minxiong observations and another reporting `no_raster_bounds_overlap`. The second record is not counted as an independent flood event. Confirm the two source paths, metadata, and raster hashes in the JSON report before any event-level aggregation or publication.

The GFD pixel size is coarse relative to the 0.25–1.875 km² cluster footprints. Observation coverage is a raster-grid-center diagnostic, not proof of complete satellite observation. Flooded share is conditional on finite values in all four event bands and should be interpreted with clear-view fields. The event collection is not an exhaustive Minxiong flood inventory.

### 2.3 Regional terrain evidence

A manually selected regional slope analysis was obtained through the Taiwan Ministry of the Interior DTM Value-added Application Service after TGOS was inaccessible. The selected area was approximately 5.6951 km². The platform reported:

| Slope class | Gradient | Area share |
|---|---|---:|
| Class 1 | ≤5% | 83.3937% |
| Class 2 | 5–15% | 13.6794% |
| Class 3 | 15–30% | 2.9268% |
| Classes 4–7 | >30% | 0% |

Approximately 97.0731% of the selected regional area was classified at or below 15% slope. This is contextual regional terrain evidence only. The manually selected polygon was not an uploaded Q05 cluster boundary and cannot be attributed as a cluster-specific measurement. The exact DTM product vintage, source grid export, and per-cluster elevation/slope statistics have not been verified in the repository.

## 3. Selection rationale

Cluster 001 is preferred for the initial synthetic benchmark placement study because:

1. **Study-area scale:** at 1.875 km², it is the largest of the nine frozen Minxiong clusters and provides the broadest analytical footprint among the shortlisted candidates.
2. **Mapped access context:** it has 312 intersecting OSM road features and 33.317 km of clipped road length, both the highest absolute values among the shortlist.
3. **Geometry:** its compactness index (0.3682) is better than cluster 002's (0.2565), although cluster 009 is more compact.
4. **Historical raster sample:** it has 182 finite event-pixel observations summed across overlapping raster records, more than the other shortlisted candidates. Its per-record observation coverage is 92.86%, slightly below clusters 002 and 009.
5. **Balanced trade-off:** cluster 002 is retained because of complete observed raster-grid-center coverage; cluster 009 is retained because of its high road density and compactness. Neither offers cluster 001's combination of footprint size and absolute mapped road context.

The zero detected flooded pixels do not distinguish the three shortlisted clusters. Flood evidence is therefore treated as a screening constraint and data-quality context, not as a claim that cluster 001 is safer.

## 4. Six-criterion suitability model disposition

The original weights remain fixed:

| Criterion | Weight | Evidence and disposition |
|---|---:|---|
| Urban built-up intensity | 25% | Frozen OSM-footprint-derived analytical clusters; cluster geometry and area are available |
| Road-network connectivity | 20% | OSM road-feature counts, clipped length, and density available as transport-context proxies; not electrical connectivity |
| Critical-infrastructure context | 15% | Six mapped OSM hospital features acquired at township scale; none intersects the nine clusters; completeness and official status unverified |
| Flood-hazard relevance | 20% | Historical GFD screening completed, but sparse/coarse and non-exhaustive; duplicate event-ID provenance issue remains open |
| Terrain suitability | 10% | Regional manual MOI slope summary available; not cluster-specific; DTM vintage/export and cluster-level metrics unverified |
| Geographic compactness | 10% | Per-cluster area, perimeter, and compactness metrics available |

**No weighted composite score is calculated.** The evidence is not sufficiently comparable or complete for a defensible full six-criterion numerical ranking. Missing or limited evidence is not assigned zero, and weights are not redistributed.

## 5. Decision scope and safeguards

- Use `Q05_cluster_001` as the lead geographic envelope for the next synthetic benchmark placement and spatial-context design work.
- Retain `Q05_cluster_002` as the formal fallback and `Q05_cluster_009` as an additional alternative.
- Do not merge the nine separate clusters into one contiguous urban area.
- Do not represent the selected cluster as an actual Taipower feeder, utility service territory, or verified electrical asset footprint.
- Do not interpret GFD zero detections as proof of flood safety or a future flood probability.
- Do not attribute the manually selected regional MOI slope statistics to the selected cluster.
- OSM roads and hospitals remain incomplete discovery/context layers, not authoritative infrastructure inventories.
- All network placement, islanding, switching, BESS, and operational recommendations remain synthetic/research-only and subject to deterministic electrical feasibility checks and human authorization. The LLM is advisory only.
- Reopen this decision if verified cluster-level terrain/flood evidence or authoritative infrastructure data materially contradicts the current selection.

## 6. Next actions

1. Audit the two raster files carrying event ID `2516` using the JSON event inventory, source paths, and SHA-256 hashes. Resolve whether one is an additional tile/product or duplicate metadata before event-level summaries are used in publications.
2. Proceed with `Q05_cluster_001` as the lead spatial envelope for synthetic IEEE 33-bus placement methodology.
3. Preserve `Q05_cluster_002` and `Q05_cluster_009` for comparative placement checks; this is not a change to the frozen cluster-generation parameters.
4. When feasible, obtain the MOI DTM source/export metadata and compute cluster-level terrain statistics using the frozen polygons. Do not block initial synthetic placement design on this, but keep terrain qualification explicitly provisional.
5. Verify critical facilities from an authoritative source before making claims about service to hospitals or other essential loads.

## 7. Reproducibility references

- Frozen cluster metrics: `reports/geospatial/minxiong_cluster_screening.csv`
- Flood screening output: `reports/geospatial/minxiong_flood_event_screening.csv`
- Flood screening script: `scripts/screen_minxiong_flood_events.py`
- Spatial overview: `reports/geospatial/minxiong_cluster_spatial_overview.png`
- Phase 4A township decision: `docs/phase_4a_candidate_selection_decision.md`
- Phase 4B spatial overview methodology: `docs/phase_4b_minxiong_cluster_spatial_overview.md`
- Phase 4B flood/terrain screening methodology: `docs/phase_4b_minxiong_flood_terrain_screening.md`
