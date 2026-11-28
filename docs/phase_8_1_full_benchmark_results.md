# Phase 8.1 — Full Benchmark Results

## Run configuration

The full Phase 8.1 benchmark was executed on the CUDA-Q NVIDIA target with QAOA depth p=1, 2,048 shots, and up to 100 COBYLA iterations. It evaluated 26 Phase 7K outage states over five seeds and ten synthetic action-count sizes over three seeds. The comparison file contains 320 method-result rows (160 scenario/seed combinations × two methods). The manifest records a wall runtime of 87.20 seconds.

## Real Phase 7K outage states

| Metric | X-mixer penalty | One-hot XY-mixer |
|---|---:|---:|
| Runs | 130 | 130 |
| Feasible runs | 130/130 | 130/130 |
| Exact-optimum matches | 130/130 | 130/130 |
| Mean feasible-shot fraction | 79.589% | 100.000% |
| Mean QAOA runtime | 0.235478 s | 0.217366 s |

Both methods recovered the exact classical optimum in all real scenario/seed runs. The XY-mixer produced only one-hot samples in every run, while the penalty X-mixer had a lower mean feasible-shot fraction. The slightly lower observed XY-mixer mean runtime in this set is empirical and should not be generalized as a speed advantage.

## Synthetic scaling cases

| Candidate actions | X-mixer feasible runs | X-mixer mean feasible-shot fraction | X-mixer exact matches | XY-mixer feasible runs | XY-mixer exact matches |
|---:|---:|---:|---:|---:|---:|
| 1 | 3/3 | 100.000% | 3/3 | 3/3 | 3/3 |
| 2 | 3/3 | 93.945% | 3/3 | 3/3 | 3/3 |
| 3 | 3/3 | 57.601% | 3/3 | 3/3 | 3/3 |
| 4 | 3/3 | 56.462% | 3/3 | 3/3 | 3/3 |
| 6 | 3/3 | 71.891% | 3/3 | 3/3 | 3/3 |
| 8 | 3/3 | 0.846% | 1/3 | 3/3 | 3/3 |
| 10 | 3/3 | 0.212% | 0/3 | 3/3 | 3/3 |
| 12 | 2/3 | 1.294%* | 1/3 | 3/3 | 3/3 |
| 14 | 1/3 | 1.953%* | 1/3 | 3/3 | 3/3 |
| 16 | 0/3 | No feasible samples | 0/3 | 3/3 | 3/3 |

*For sizes 12 and 14, the mean feasible-shot fraction is calculated over the runs that produced at least one feasible sample; the no-feasible-sample runs have no defined feasible-shot fraction. Feasible-run counts show the missing runs explicitly.*

Across all 30 synthetic runs, the X-mixer produced 24 feasible runs and 18 exact-optimum matches, with a mean feasible-shot fraction of 47.809% over runs with a defined fraction. The XY-mixer produced 30 feasible runs, 30 exact-optimum matches, and a 100% feasible-shot fraction.

## Runtime comparison

| Benchmark set | X-mixer mean QAOA runtime | XY-mixer mean QAOA runtime | Exact enumeration mean runtime |
|---|---:|---:|---:|
| Real outage states | 0.235478 s | 0.217366 s | approximately 0.000155 s |
| Synthetic scaling | 0.388328 s | 0.433887 s | approximately 0.001771 s |

The QAOA implementations were slower than exact enumeration in these tested cases. The XY-mixer's principal demonstrated benefit is constraint-preserving sampling and reliable recovery of the exact optimum in this benchmark, not computational speedup.

## Interpretation

1. The one-hot XY-mixer maintained the exactly-one-choice constraint for all sampled outcomes in all 130 real and 30 synthetic runs.
2. The XY-mixer recovered the exact classical optimum in every tested run.
3. The penalty X-mixer's feasible-shot fraction degraded substantially at larger synthetic action counts, and it produced no feasible sample in any of the three 16-action runs.
4. The XY-mixer's complete-graph pairwise construction carries additional gate and qubit costs. Phase 8.2 adds depth variation and source-level resource estimates to quantify this trade-off.
5. These results are limited to synthetic scaling tests and nominal IEEE-33 benchmark load. They do not establish AC power-flow feasibility, operational grid validity, or quantum advantage.

## Reproducibility artifacts

The run generated:
- phase_8_1_comparison.csv
- phase_8_1_summary.csv
- phase_8_1_manifest.json

The run used 26 real outage states × five seeds and ten synthetic sizes × three seeds, with both X-mixer and XY-mixer methods. Synthetic cases are computational stress tests, not additional physical grid states.
