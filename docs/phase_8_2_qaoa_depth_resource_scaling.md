# Phase 8.2 — QAOA Depth and Resource Scaling Analysis

## Objective

Phase 8.2 extends the Phase 8.1 comparison by varying QAOA depth and increasing the number of synthetic repetitions. It compares the original penalty-based X-mixer with the one-hot, excitation-preserving XY-mixer and exact classical enumeration.

The study asks whether deeper circuits improve feasible-sample rates or exact-optimum recovery, and how the additional XY-mixer circuit resources scale with candidate-action count.

## Experimental design

| Dimension | Setting |
|---|---|
| QAOA depths | p = 1, 2, 3 |
| Real outage scenarios | All Phase 7K unique outage states |
| Real seeds | 42–46 (5 per state and depth) |
| Synthetic action counts | 1, 2, 3, 4, 6, 8, 10, 12, 14, 16 |
| Synthetic seeds | 42–61 (20 per size and depth) |
| Shots per sampling call | 2,048 |
| COBYLA maximum iterations | 100 |
| CUDA-Q target | NVIDIA |
| Classical reference | Exact enumeration |

With 26 real outage states, this configuration produces 390 real scenario/seed/depth combinations and 600 synthetic combinations. Both QAOA methods are evaluated for each combination, giving 1,980 method-result rows when all default cases complete.

The random seed is deterministically offset by scenario or synthetic size and QAOA depth to avoid reusing an identical seed across all depth settings.

## Metrics

The comparison output records:

- Feasible-run count and feasible-shot fraction.
- Exact-optimum recovery and absolute objective gap (kW).
- QAOA optimization-plus-sampling runtime, with optimization and sampling components where returned by the kernel.
- Exact classical enumeration runtime.
- Qubit count.
- Primitive gate-call count, single-qubit gate-call count, and two-qubit gate-call count.
- Conservative source-order serial-depth upper bound.
- CUDA-Q target, QAOA depth, seed, and scenario identifier.

## Resource-accounting method and caveats

Resource estimates are derived from the current CUDA-Q kernel source rather than a backend-transpiled circuit.

For the Phase 8 X-mixer, the estimator counts the initial Hadamard layer, per-qubit cost RZ and mixer RX calls, and the CNOT–RZ–CNOT decomposition for each listed ZZ interaction.

For the Phase 8.1 XY-mixer, the estimator counts the initial X on the no-action qubit, per-action cost RZ calls, and 18 primitive gate calls per complete-graph edge per mixer layer. Each edge includes four controlled-X calls.

The reported source_order_depth_upper_bound is a conservative count based on the order of operations in the source kernel. It is **not** a transpiler-reported circuit depth, hardware-native depth, or physical execution duration. Compiler scheduling, gate fusion, target connectivity, and hardware routing are not represented.

## Run

~~~bash
export PYTHONPATH="$(pwd):${PYTHONPATH}"
pytest -q tests/test_qaoa_resource_estimates.py

python scripts/run_phase8_2_depth_resource_benchmark.py \
  --depths 1 2 3 \
  --seeds 42 43 44 45 46 \
  --scaling-seeds 42 43 44 45 46 47 48 49 50 51 52 53 54 55 56 57 58 59 60 61 \
  --scaling-sizes 1 2 3 4 6 8 10 12 14 16 \
  --shots 2048 \
  --max-iterations 100 \
  --cudaq-target nvidia \
  --output-dir reports/ibtracs/phase_8_2
~~~

For a short GPU smoke test:

~~~bash
python scripts/run_phase8_2_depth_resource_benchmark.py \
  --skip-real \
  --scaling-seeds 42 \
  --scaling-sizes 1 2 3 \
  --depths 1 2 \
  --shots 256 \
  --max-iterations 5 \
  --cudaq-target nvidia \
  --output-dir reports/ibtracs/phase_8_2_smoke
~~~

## Outputs

- phase_8_2_comparison.csv: per-run results and resource estimates.
- phase_8_2_summary.csv: grouped results by benchmark type, method, depth, and action count.
- phase_8_2_manifest.json: configuration, resource-accounting definitions, outputs, and limitations.

## Interpretation and limitations

- Exact enumeration remains the classical optimum reference. No quantum advantage or speedup is assumed.
- Synthetic cases are computational stress tests, not additional physical grid states.
- The XY mixer remains a sequential product of pairwise exchange rotations, not an exact exponential of the summed complete-graph mixer Hamiltonian.
- The optimization objective remains nominal IEEE-33 benchmark load. It is not AC-power-flow or operationally validated.
- Resource estimates are source-level gate-call estimates and must not be presented as transpiled or hardware-native circuit metrics.
