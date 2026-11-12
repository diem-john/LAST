# Phase 4A Candidate Selection Decision — Minxiong Township

**Decision status:** Selected for Phase 4B study-area development, subject to hazard/terrain qualification  
**Decision date:** 2026-11-12  
**Branch:** `last-fe-foundation`

## Decision

Select **Minxiong Township (民雄鄉; TOWNID Q05)** as the lead candidate for the next LAST study-area development phase. This is a project-level screening decision based on the currently acquired and technically validated evidence. It is not a completed six-criterion weighted suitability ranking, an official planning designation, or confirmation of a real Taipower feeder location.

The 19 analytical urban-cluster polygons are adopted as fixed study-area inputs. Sensitivity analysis is intentionally omitted at the project owner's direction. Their derivation parameters and source hashes remain recorded in `reports/geospatial/chiayi_urban_cluster_validation.json`.

## Evidence used

The executed delineation reported:

| Candidate | Qualifying 250 m cells | Retained clusters | OSM polygon building features intersecting township |
|---|---:|---:|---:|
| Minxiong (Q05) | 114 | 9 | 1,593 |
| Puzi (Q02) | 60 | 5 | 490 |
| Taibao (Q12) | 45 | 3 | 636 |
| Shuishang (Q13) | 28 | 2 | 273 |

Minxiong leads these available built-up proxy indicators: it has the most qualifying cells, retained clusters, and mapped polygon building features intersecting its administrative boundary. These are raw OSM-derived counts, not completeness-adjusted estimates or population/building census measures. OSM mapping density may differ between townships.

The underlying analytical-cluster GeoPackage contains 19 features in EPSG:3826 and is hash-identified in the validation report. The candidate township boundary GeoPackage is the accepted NLSC 2023 administrative reference.

## Criteria disposition

Original suitability weights remain unchanged:

| Criterion | Weight | Current disposition |
|---|---:|---|
| Urban built-up intensity | 25% | Available proxy evidence favours Minxiong; OSM coverage limitation applies |
| Road-network connectivity | 20% | OSM road data technically validated; candidate-cluster-specific metrics not yet computed |
| Critical-infrastructure context | 15% | Six OSM hospital features acquired; candidate-cluster-specific counts and official verification not completed |
| Flood-hazard relevance | 20% | Unavailable; no validated candidate-comparable flood layer in current evidence |
| Terrain suitability | 10% | Unavailable; no validated DEM-derived candidate metrics in current evidence |
| Geographic compactness | 10% | Cluster geometries available; candidate-level compactness metrics not yet calculated |

No weighted score is calculated. Missing criteria are not assigned zero, and the original weights are not redistributed. Consequently, Minxiong is the **selected lead candidate for continued study**, not a demonstrated overall winner under the full six-criterion model.

## Scope and safeguards

1. Proceed with Minxiong's existing derived urban clusters as the spatial envelope for the next analytical phase.
2. Keep the nine Minxiong clusters as distinct candidate components until one compact cluster is selected using the subsequent network-placement criteria; do not merge distant clusters into one synthetic urban network.
3. Use OSM roads only as contextual transport/accessibility data. They are not Taipower electrical lines or verified utility corridors.
4. Treat OSM hospitals as discovery features, not an authoritative critical-facility inventory.
5. Do not infer flood exposure, terrain suitability, electrical service territory, or actual feeder placement from the current selection.
6. The network remains a synthetic, Chiayi-georeferenced enhanced IEEE 33-bus benchmark. It must not be represented as an actual Taipower feeder.
7. If later validated flood or terrain evidence makes Minxiong unsuitable, reopen the selection decision transparently rather than altering the current evidence record.

## Next phase

For Minxiong only, perform cluster-level screening to identify the most coherent compact cluster for synthetic benchmark placement. Use the existing road graph/edges and hospital features to calculate documented spatial context metrics. Keep the other eight Minxiong clusters as alternatives in the record. This is a within-township study-area refinement, not sensitivity analysis or a re-ranking of the four townships.
