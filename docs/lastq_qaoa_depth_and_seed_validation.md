# LAST-Q QAOA Circuit-Depth and Multi-Seed Validation

## Scope

This report records the Bus 6 topology-only QAOA experiments performed on the
modified IEEE 33-bus demonstrator. The experiments compare circuit depths
\(p=1,2,3,4\), then validate depths 3 and 4 across four random seeds.

The problem uses five binary variables for normally-open tie switches 33–37.
The current QUBO rewards exactly two closures and penalizes the invalid
topology choices represented by tie 34 and the pair (33, 35). Under the
current zero-switching-cost formulation, the five zero-energy configurations
are the topology-feasible restoration combinations.

This is a five-qubit topology-level demonstrator. It does not establish
AC power-flow feasibility, voltage or thermal compliance, protection
coordination, load-priority optimization, or operational restoration
readiness.

## Experimental configuration

Unless otherwise stated:

- Backend: CUDA-Q `qpp-cpu`
- Qubits: 5
- Final sampling shots: 2,048
- Optimizer: SciPy COBYLA
- Independent initializations: 5
- Maximum objective evaluations per start: 300
- Seed: 7 for the initial depth sweep
- Candidate selection: lowest exact expected QUBO energy, evaluated with
  analytic CUDA-Q expectation before final finite-shot sampling

The evaluation budget applies independently to each start. A selected
candidate can report optimizer success even when one or more other starts
did not converge; these diagnostics must be interpreted separately.

## Initial circuit-depth sweep (seed 7)

| Depth | Selected start | Exact expectation | Optimal-sample probability | Optimization runtime (s) | Selected optimizer success |
|---|---:|---:|---:|---:|---|
| P1 | 2 | 8.749521 | 37.5488% | 0.5063 | Yes |
| P2 | 5 | 9.143982 | 38.8184% | 2.3108 | Yes |
| P3 | 2 | 8.285925 | 42.6270% | 2.7304 | Yes |
| P4 | 2 | 7.880206 | 37.0117% | 4.4087 | Yes |

The initial sweep suggested that P4 had the lowest exact expectation, while
P3 had the highest observed optimal-sample probability. This motivated
multi-seed validation of P3 and P4 rather than selecting a depth from one
seed.

## Multi-seed validation: P3 versus P4

The initial seed 7 results were combined with additional runs using seeds
11, 21, and 42.

| Seed | P3 exact expectation | P3 optimal-sample probability | P3 runtime (s) | P4 exact expectation | P4 optimal-sample probability | P4 runtime (s) |
|---:|---:|---:|---:|---:|---:|---:|
| 7 | 8.285925 | 42.6269% | 2.7304 | 7.880206 | 37.0117% | 4.4087 |
| 11 | 5.829238 | 50.2930% | 3.5482 | 9.255199 | 20.9473% | 3.0768 |
| 21 | 10.526794 | 40.3809% | 2.2967 | 6.950758 | 51.6113% | 2.6458 |
| 42 | 5.701444 | 55.0781% | 2.4583 | 6.571824 | 67.4805% | 3.5544 |

### Summary statistics

Values are mean ± sample standard deviation across the four seeds.

| Metric | P3 (3 layers) | P4 (4 layers) |
|---|---:|---:|
| Exact expectation (lower is better) | 7.5859 ± 2.2932 | 7.6645 ± 1.1945 |
| Optimal-sample probability (higher is better) | 47.09 ± 6.81% | 44.26 ± 19.91% |
| Optimization runtime (seconds) | 2.7584 ± 0.5561 | 3.4214 ± 0.7556 |

For the three additional seeds (11, 21, and 42), all five starts
successfully converged in each P3 run. In the corresponding P4 runs,
`all_starts_successful` was false for all three seeds. For P4 seed 11 and
seed 21, the selected optimizer candidate also reported failure; for seed
42, the selected candidate reported success although not all starts did.

### Interpretation

1. P3 has a slightly lower mean exact expectation than P4 in this four-seed
   sample. The difference is small and should not be treated as decisive.
2. P3 has a higher mean optimal-sample probability and substantially lower
   observed variability in that probability.
3. P3 has a lower mean optimization runtime in these experiments.
4. P4's performance is seed-sensitive: it is weak for seed 11 and strong for
   seed 42. Its deeper circuit did not produce a consistent sampling benefit.
5. P3 had all-start convergence in each of the three additional-seed runs.
   P4 did not. The seed-7 depth-sweep row only reports selected-candidate
   success; it should not be used to infer all-start convergence.

Under this limited experiment, P3 is the preferred provisional configuration
because it provides a better balance of sampling performance, runtime, and
optimizer reliability. P4 remains a useful comparison because it achieved
the lowest exact expectation in the initial seed-7 sweep.

## Metric definitions and reporting notes

- **Exact expectation** is the analytic expectation of the QUBO/Ising
  objective for the selected optimized parameters.
- **Sampled expected energy** is the empirical average QUBO energy over the
  final finite-shot measurement distribution. It is stored in
  `final_sample.expected_qubo_energy`, not at the JSON top level.
- **Optimal-sample probability** is the probability of measuring a
  zero-energy bitstring. In this current formulation, the zero-energy
  solutions correspond to the five topology-feasible combinations, so this
  equals the reported topology-feasible probability.
- **Selected optimizer success** describes only the selected start.
  `all_starts_successful` describes every start and should also be reported.

## Provisional configuration

For the next benchmark stage, use:

| Parameter | Value |
|---|---|
| QAOA depth | 3 |
| Backend reference | `qpp-cpu` |
| Qubits | 5 |
| Starts | 5 |
| Maximum evaluations per start | 300 |
| Final shots | 2,048 |
| Validation seeds | 7, 11, 21, 42 |

## Limitations and next steps

- The search space contains only 32 bitstrings and has an exact classical
  enumeration baseline. No quantum advantage is demonstrated.
- The present QUBO encodes simplified topology constraints only. It is not a
  substitute for electrical feasibility analysis.
- The multi-seed sample is small. More seeds and repeated sampling runs are
  needed before making strong statistical claims.
- Next, benchmark the selected P3 configuration on CPU and GPU using
  identical seeds and settings. Compare exact expectation, empirical
  sampling probability, optimizer convergence, optimization runtime, and
  final sampling runtime.
- Then evaluate shot-count sensitivity and extend the restoration model with
  electrical constraints and load restoration objectives before making
  operational claims.
