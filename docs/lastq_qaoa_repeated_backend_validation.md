# LAST-Q Repeated CPU/GPU Backend Validation

## Purpose

This protocol measures whether the observed GPU runtime improvement for the
five-qubit Bus 6 QAOA demonstrator is repeatable. It compares CUDA-Q's
\`qpp-cpu\` and \`nvidia\` execution targets. It is a backend-performance study,
not a comparison of quantum and classical algorithms and not evidence of
quantum advantage.

## Fixed experiment configuration

The benchmark defaults to:

| Parameter | Value |
|---|---:|
| QAOA depth | 3 |
| Qubits | 5 |
| Independent starts | 5 |
| COBYLA maximum evaluations per start | 300 |
| Final measurement shots | 2,048 |
| Random seeds | 7, 11, 21, 42 |
| Repetitions per seed/backend | 5 |
| Warm-up runs | 1 per backend |
| CPU target | \`qpp-cpu\` |
| GPU target | \`nvidia\` |

This produces 40 measured runs and two warm-up runs. Warm-ups are excluded
from all reported statistics.

## Running the benchmark

Activate the LAST-Q environment and move to the repository root:

\`\`\`bash
cd ~/projects/LAST
conda activate lastq
\`\`\`

Check that the NVIDIA backend is available:

\`\`\`bash
nvidia-smi
python - <<'PY'
import cudaq
import scipy
print("CUDA-Q:", cudaq.__version__)
print("SciPy:", scipy.__version__)
print("Available NVIDIA target:", cudaq.has_target("nvidia"))
PY
\`\`\`

Run the default 40-run experiment:

\`\`\`bash
python -m scripts.benchmark_lastq_qaoa_backends
\`\`\`

The script alternates CPU/GPU order across paired trials to reduce systematic
timing-order bias. Each trial is launched as a separate runner process and
writes its original QAOA result JSON. The benchmark stops if a trial fails;
inspect the error before restarting.

Optional arguments:

\`\`\`bash
python -m scripts.benchmark_lastq_qaoa_backends --help
\`\`\`

For a short smoke test before the full experiment:

\`\`\`bash
python -m scripts.benchmark_lastq_qaoa_backends \\
    --seeds 7 \\
    --repetitions 1 \\
    --warmups 1
\`\`\`

The smoke test uses the same P3/five-start/300-evaluation/2,048-shot settings,
but its sample size is not sufficient for statistical conclusions.

## Outputs

Each execution creates a timestamped directory under:

\`reports/quantum/backend_validation/\`

It contains:

- \`warmup_cpu_1.json\` and \`warmup_gpu_1.json\`: warm-up outputs, excluded
  from summary statistics.
- One JSON file per measured backend/seed/repetition containing the complete
  QAOA optimizer and final sampling result.
- \`benchmark_records.csv\`: one row per measured run.
- \`benchmark_summary.json\`: configuration, environment metadata, raw records,
  backend summaries, and paired comparisons.

The summary reports mean, sample standard deviation, and median for:
- exact final QUBO expectation;
- sampled expected QUBO energy;
- topology-feasible sampling probability;
- optimization runtime;
- final sampling runtime;
- full subprocess wall time.

It also reports selected optimizer success, all-start convergence rate,
paired GPU/CPU optimization speedup, and paired GPU-minus-CPU differences in
exact expectation and feasible probability.

## Interpretation

- A paired speedup above 1.0 means the GPU optimization runtime was lower
  than the CPU runtime for that seed/repetition pair.
- Report the mean and standard deviation of paired speedups, not only the
  ratio of two aggregate means.
- Compare exact expectation and topology-feasible probability alongside
  runtime. Faster execution alone does not imply better optimization quality.
- Final sampling time is reported separately from optimization time.
- Repetitions use the same seed within each seed/backend group. They are
  repeated timing observations, not 20 independent random initializations.
- The benchmark uses a small five-qubit problem. GPU launch/runtime overhead,
  machine load, thermal state, driver/runtime versions, and target warm-up can
  affect measured results.
- Do not claim quantum advantage. The experiment only compares CPU and GPU
  execution of the same QAOA workflow.

## Recommended reporting

Report the full configuration, software/hardware metadata, number of paired
runs, mean ± sample standard deviation, and all-start convergence rate.
Retain the generated CSV and JSON files as experiment artifacts. If the
results show a stable speedup, describe it as GPU backend acceleration for
this specific five-qubit demonstrator.
