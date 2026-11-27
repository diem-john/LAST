# Phase 8 — Quantum-Classical Restoration Optimization

## Objective

Phase 8 introduces a controlled comparison between an exact classical reference solver and QAOA for selecting a restoration action from the Phase 7K scenario outputs.

The initial formulation is intentionally limited to **at most one single-tie action per outage state**. It is a first optimization baseline, not a full multi-switch restoration planner.

## Decision variables and QUBO

For an outage state with (n) Phase 7K restoration candidates, define (x_i\in\{0,1\}), where (x_i=1) selects candidate tie action (i). The all-zero vector means no action.

Let (b_i) be the benchmark active load (kW) reported as restored by candidate (i). The QUBO is:

[
E(x)=-\sum_{i=1}^{n} b_i x_i + P\sum_{i<j}x_i x_j
]

with:

[
P=\text{penalty\_factor}\left(\sum_i b_i+1\right)
]

The penalty is larger than the sum of all candidate benefits. Therefore, every multi-action vector has energy greater than the no-action vector, enforcing an at-most-one constraint. The objective does not model combined tie closures; it ranks individual restoration actions.

The QUBO is converted to an Ising Hamiltonian using (x_i=(1-Z_i)/2). QAOA alternates the cost unitary and an X-mixer layer. CUDA-Q performs the variational expectation evaluation and sampling. The classical baseline enumerates all (2^n) bitstrings and filters by the same at-most-one constraint.

## Inputs

- `reports/ibtracs/phase_7k/phase_7k_unique_outage_states.csv`
- `reports/ibtracs/phase_7k/phase_7k_restoration_candidates.csv`

The model uses the nominal IEEE-33 benchmark load figures already attached to each Phase 7K candidate. These are not measured Minxiong or Taipower customer loads.

## Run

Classical exact baseline only:

```bash
export PYTHONPATH="$(pwd):${PYTHONPATH}"
python scripts/run_phase8_restoration_optimization.py --classical-only
```

Classical plus CUDA-Q QAOA:

```bash
python scripts/run_phase8_restoration_optimization.py \
  --qaoa-layers 1 \
  --qaoa-shots 2048 \
  --qaoa-max-iterations 100 \
  --seed 42
```

Optional backend selection:

```bash
python scripts/run_phase8_restoration_optimization.py --cudaq-target qpp-cpu
# Or, if the CUDA-Q installation exposes the NVIDIA target:
python scripts/run_phase8_restoration_optimization.py --cudaq-target nvidia
```

Do not infer GPU acceleration from the package version alone; record the selected CUDA-Q target and validate it on the installed system.

## Outputs

- `phase_8_optimization_comparison.csv`: one row per outage state with exact classical and sampled QAOA solution, objective, runtime, feasibility, and load-restoration gap.
- `phase_8_candidate_variables.csv`: candidate-to-QUBO-variable mapping.
- `phase_8_manifest.json`: formulation, parameters, inputs, outputs, and limitations.

## Evaluation protocol

Compare both methods on identical outage states and QUBO coefficients. Report:
- exact classical objective and runtime;
- QAOA optimized expectation, best feasible sampled objective, and runtime;
- feasible-shot fraction and whether the QAOA sample matches the exact optimum;
- absolute restored-load gap in kW;
- QAOA depth, shots, optimizer iterations, target, and seed.

The exact enumeration is a strong baseline because the benchmark contains only a small number of normally-open tie switches. QAOA is a research comparison, not presumed to be faster or better.

## Scope limitations

- At most one tie action is selected per outage state; multi-switch combinations and sequencing are future work.
- No AC power flow, voltage, thermal, protection, fault-current, switching-sequence, radiality under actual switching, BESS, or distributed-generation constraints are validated here.
- The optimization uses benchmark nominal bus loads, not actual local customer loads.
- The upstream wind fragility model remains uncalibrated, and synthetic geometry remains unchanged.
- A QAOA sampled solution is only a candidate for the stated QUBO. It is not an operational switching recommendation.

## Next extension

After this baseline is tested, Phase 8B should formulate multi-switch restoration with explicit radiality and operating constraints, then validate candidate configurations using an AC power-flow solver before any operational interpretation.
