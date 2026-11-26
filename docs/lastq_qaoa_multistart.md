# LAST-Q Multi-Start QAOA

The Bus 6 QAOA runner supports deterministic multi-start COBYLA optimization.
Each start receives an independently generated, reproducible initial parameter
vector. The first start retains the historical initialization for a given
seed; later starts use seed + start_index.

Each start is optimized against the analytic Ising expectation. The runner
re-evaluates every optimized candidate with CUDA-Q observe, selects the
candidate with the lowest exact expectation, and only then performs the final
finite-shot CUDA-Q sample evaluation.

## Example

Run five starts with two QAOA layers:

```bash
python -m scripts.run_lastq_qaoa \
    --target qpp-cpu \
    --shots 2048 \
    --layers 2 \
    --max-iterations 300 \
    --starts 5 \
    --seed 7 \
    --output reports/quantum/lastq_bus6_qaoa_cpu_p2_multistart5_seed7.json
```

The max-iterations setting is applied independently to each start. In the
current SciPy COBYLA configuration, its maxiter option acts as an objective
evaluation limit. Thus, five starts with a value of 300 can use up to
approximately 1,500 objective evaluations, plus exact candidate checks.

## Result fields

- multi_start_count: number of independent initializations.
- selected_start_index: one-based index of the selected initialization.
- multi_start_results: per-start initialization, optimized parameters,
  exact expectation, convergence status, evaluation count, and runtime.
- all_starts_successful: whether every COBYLA run reported success.
- objective_evaluations: total objective evaluations across all starts.
- exact_final_expectation: exact expectation of the selected parameters.
- final_sample: finite-shot measurement distribution from the selected
  parameters, including topology-feasible probability.

The selection criterion is the lowest exact expectation, not the best
finite-shot sample. A lower QUBO expectation does not necessarily imply a
higher topology-feasible sampling probability. Compare both metrics across
repeated seeds when evaluating reliability.

This remains a five-qubit topology-only Bus 6 demonstrator. It is not an
AC power-flow or operational grid-restoration validation.
