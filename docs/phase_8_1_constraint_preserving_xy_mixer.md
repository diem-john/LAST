# Phase 8.1 — Constraint-Preserving One-Hot XY-Mixer QAOA

## Objective

Phase 8.1 adds a constraint-preserving alternative to the Phase 8 penalty-based X-mixer. The original implementation remains unchanged and is the baseline. The new variant is evaluated against both that baseline and exact classical enumeration.

This is a first-stage single-tie-action comparison. It does not extend the problem to multi-switch restoration.

## One-hot decision encoding

For an outage state with (n) candidate tie actions, allocate (n+1) qubits:

- (x_0): explicit no-action choice;
- (x_i), (i=1,ldots,n): candidate restoration action (i).

The constraint is:

```text
x_0 + x_1 + ... + x_n = 1
```

The initial computational basis state is `|100...0>` (qubit 0 is the no-action choice). The objective is:

```text
minimize E(x) = -sum_(i=1)^n b_i*x_i
```

where (b_i) is the nominal benchmark load (kW) restored by candidate (i). The no-action choice has zero benefit. The one-hot encoding represents exactly one choice, including no action.

## XY mixer and gate construction

The mixer uses a complete graph over the (n+1) choices. For each edge ((i,j)), the circuit applies the pairwise exchange rotation:

```text
U_XY(beta) = exp[-i beta (X_i X_j + Y_i Y_j)/2]
           = RXX(beta) RYY(beta)
```

Each pairwise interaction preserves total excitation number. The implementation decomposes RXX and RYY into gates already used by CUDA-Q kernels: H, S/S-dagger, controlled-X, and RZ. Pair interactions are applied sequentially, so this is a product-form mixer layer; it is not described as an exact single exponential of the summed complete-graph Hamiltonian.

The cost unitary is diagonal. Ignoring its global phase, it is implemented by `RZ(gamma*b_i)` on each action qubit. The no-action qubit has no cost term.

## Comparison protocol

The benchmark script evaluates:

1. **Phase 8 X-mixer:** existing penalty QUBO and standard X-mixer, unchanged.
2. **Phase 8.1 XY-mixer:** one-hot encoding with excitation-preserving pairwise exchange gates.
3. **Exact enumeration:** exact optimum for the same single-action decision set.

The runner reports, per scenario and seed:

- QAOA feasibility and constraint-violation counts;
- feasible-shot fraction;
- restored benchmark load and objective gap;
- exact-optimum agreement;
- qubit count and runtime;
- selected tie-branch identifiers and CUDA-Q target.

The XY method uses one additional qubit because of the explicit no-action option. Report qubit counts and runtime boundaries when comparing methods.

## Run

Run host-side unit tests:

```bash
export PYTHONPATH="$(pwd):${PYTHONPATH}"
pytest -q tests/test_restoration_optimization.py tests/test_constraint_preserving_restoration.py
```

Run the CUDA-Q circuit integration test on the CPU simulator:

```bash
RUN_CUDAQ_INTEGRATION=1 pytest -q tests/test_constraint_preserving_restoration.py
```

Run the real Phase 7K cases and synthetic scaling comparison:

```bash
python scripts/run_phase8_1_xy_mixer_benchmark.py \
  --seeds 42 43 44 \
  --scaling-seeds 42 43 44 \
  --scaling-sizes 1 2 3 4 6 8 10 12 14 16 \
  --qaoa-layers 1 \
  --qaoa-shots 2048 \
  --qaoa-max-iterations 100 \
  --cudaq-target nvidia
```

For a shorter initial smoke run, use `--skip-real` with small scaling sizes, or `--skip-scaling` to run only the Phase 7K cases.

## Outputs

Default output directory: `reports/ibtracs/phase_8_1`

- `phase_8_1_comparison.csv`
- `phase_8_1_summary.csv`
- `phase_8_1_manifest.json`

## Validation gates and limitations

- Host-side tests verify one-hot encoding, no-action behavior, objective mapping, and exact-optimum agreement.
- An opt-in CUDA-Q integration test checks that all sampled outcomes remain one-hot. Run it on the installed CUDA-Q 0.16 environment before treating the circuit as locally validated.
- CI does not claim to execute CUDA-Q because CUDA-Q is not installed in the lightweight GitHub Actions test environment.
- The one-hot invariant is expected from the excitation-preserving decomposition; a passing integration test on the target is the required runtime evidence.
- The XY mixer adds a qubit and uses a complete-graph sequence of pairwise gates. Gate count grows quadratically with the number of choices.
- Synthetic scaling cases are computational stress tests, not additional physical grid states.
- Exact enumeration remains the classical reference. No quantum advantage or speedup is assumed.
- The objective remains nominal IEEE-33 benchmark load. No AC power flow, voltage, thermal, protection, fault-current, switching-sequence, BESS, or distributed-generation constraints are validated.
