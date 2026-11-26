# LAST-Q Phase 2: QAOA Implementation

## Purpose

This phase implements a parameterized QAOA circuit for the five-variable Bus 6 tie-restoration QUBO. The circuit is built with NVIDIA CUDA-Q and optimized by a classical SciPy COBYLA loop.

## QUBO-to-Ising mapping

For the QUBO convention

```
E(x) = c + sum_i a_i x_i + sum_(i<j) b_ij x_i x_j
```

use (x_i=(1-Z_i)/2), yielding

```
H_C = C0 + sum_i h_i Z_i + sum_(i<j) J_ij Z_i Z_j
h_i = -a_i/2 - (1/4) * sum_(j != i) b_ij
J_ij = b_ij/4
C0 = c + (1/2) * sum_i a_i + (1/4) * sum_(i<j) b_ij
```

The constant (C0) does not affect the QAOA state evolution and is retained for energy equivalence checks.

## Circuit

For each QAOA layer:

1. Apply the cost unitary for single-qubit (Z_i) terms using (R_Z(2\gamma h_i)).
2. Apply pairwise (Z_i Z_j) terms using CNOT–(R_Z(2\gamma J_{ij}))–CNOT.
3. Apply the transverse-field mixer using (R_X(2\beta)) on each qubit.

The initial state is the uniform superposition prepared by Hadamard gates. CUDA-Q samples the final computational-basis distribution. CUDA-Q's global bitstrings follow qubit allocation order, with qubit 0 represented by the leftmost bit; the decoder uses this convention.

## Classical parameter optimization

The outer loop uses SciPy COBYLA to minimize the shot-estimated expected QUBO energy. The initial implementation exposes:

- QAOA depth (`--layers`)
- shots per objective evaluation (`--shots`)
- maximum COBYLA iterations (`--max-iterations`)
- initial parameter seed (`--seed`)
- CUDA-Q target (`--target`)

The default target is the CUDA-Q environment default. Use `qpp-cpu` for CPU simulation or `nvidia` for the NVIDIA GPU state-vector simulator when the corresponding backend and runtime are installed.

## Run

CPU simulator:

```powershell
python -m scripts.run_lastq_qaoa --target qpp-cpu --shots 2048 --layers 1 --max-iterations 60
```

NVIDIA GPU simulator:

```powershell
python -m scripts.run_lastq_qaoa --target nvidia --shots 2048 --layers 1 --max-iterations 60
```

Output:

`reports/quantum/lastq_bus6_qaoa.json`

## Reported measurements

- Expected sampled QUBO energy.
- Best sampled QUBO energy and bitstring.
- Probability of sampling a topology-feasible state.
- Probability of sampling an exact classical optimum.
- Qubit count, QAOA depth, shots, target, COBYLA iterations, and objective evaluations.

## Scope and limitations

This five-qubit instance is a circuit and workflow demonstrator. It is too small to support claims of quantum advantage or meaningful GPU scaling. The five topology-feasible states are degenerate when no switching costs are supplied, so the QAOA objective is initially to concentrate probability on the feasible minimum-energy subspace.

The output remains a topology-level candidate. It is not an AC power-flow validated restoration plan. The next engineering phase must add contingency-aware power flow and then load-priority/resource constraints before the research claims expand.

## CUDA-Q references

- CUDA-Q 0.16 Python API: https://nvidia.github.io/cuda-quantum/0.16.0/api/languages/python_api.html
- CUDA-Q 0.16 examples: https://nvidia.github.io/cuda-quantum/0.16.0/using/examples/introduction.html
- State-vector simulator targets: https://nvidia.github.io/cuda-quantum/0.15.0/using/backends/sims/svsims.html
