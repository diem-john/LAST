# LAST-Q Phase 1: Bus 6 Topology Restoration and QUBO Baseline

## Purpose

This phase establishes a small, reproducible optimization instance before QAOA is introduced. It uses the canonical electrical case at `data/electrical/ieee33bw_reference.json` and the existing modified IEEE 33-bus benchmark data.

## Bus 6 contingency interpretation

A faulted bus must be isolated from every incident branch. In the current canonical case, Bus 6 is incident to branch 5 (5-6), branch 6 (6-7), and branch 25 (6-26). All three branches are removed from service in the topology model. The failed Bus 6 itself is excluded from the active-bus set.

This produces three pre-restoration components:

1. Source-connected component containing the slack bus.
2. Disconnected section containing Buses 7-18.
3. Disconnected section containing Buses 26-33.

The canonical data contains five normally-open ties:

| Branch | Endpoints | Topology role after Bus 6 outage |
|---|---|---|
| 33 | 21-8 | Source component to Buses 7-18 |
| 34 | 9-15 | Internal to the Buses 7-18 component; closing creates a cycle |
| 35 | 12-22 | Parallel source-to-Buses 7-18 restoration path |
| 36 | 18-33 | Connects the two disconnected components |
| 37 | 25-29 | Source component to Buses 26-33 |

The tie endpoints are taken from the repository's canonical JSON file. They must not be replaced by a different IEEE 33-bus variant without updating the model and tests.

## Initial QUBO

Let each binary variable (x_i) represent closing one normally-open tie. The initial topology problem has three components and therefore requires exactly two selected ties to form a spanning tree.

The cardinality term is:

[
P_{mathrm{count}} = Aleft(sum_i x_i - 2ight)^2
]

A tie internal to an existing component is penalized:

[
P_{mathrm{internal}} = Bx_{34}
]

The two parallel ties between the source component and the Buses 7-18 component cannot both be closed in a radial topology:

[
P_{mathrm{parallel}} = Cx_{33}x_{35}
]

The initial objective is:

[
E(mathbf{x}) =
P_{mathrm{count}} + P_{mathrm{internal}} +
P_{mathrm{parallel}} + sum_i c_i x_i
]

where (c_i) is an optional, externally supplied switching cost. No unsupported switching-cost values are assumed by default.

With three components, exactly two closures, the internal-tie penalty, and the parallel-tie penalty, the five feasible tie sets are:

- {33, 36}
- {33, 37}
- {35, 36}
- {35, 37}
- {36, 37}

These are topology-feasible spanning trees in the reduced component graph. With no supplied switching costs, they are equally optimal; the code intentionally reports all five minimizers rather than inventing a preferred plan.

## Important scope boundary

This QUBO is a **topology-level feasibility formulation**, not a complete grid-restoration optimizer. It does not yet model:

- AC power-flow feasibility after switching.
- Bus voltage or branch thermal limits.
- Protection coordination or fault-current constraints.
- BESS grid-forming capability, power limits, state of charge, or energy duration.
- Load pickup priorities or partial load restoration.
- PV output and weather forecast uncertainty.

A candidate must not be described as an electrically feasible restoration plan until it passes the relevant power-flow and operational checks. The existing backward/forward-sweep solver currently validates the intact radial base case; contingency-aware power-flow integration is a subsequent milestone.

## Run

From the repository root:

```powershell
python -m scripts.run_lastq_classical_baseline
python -m pytest -q tests/test_lastq_reconfiguration.py
```

Output:

`reports/quantum/lastq_bus6_classical_baseline.json`

## Next phase

1. Integrate selected tie configurations with contingency-aware power flow.
2. Add load-restoration variables and explicit critical-load priorities.
3. Add resource constraints for BESS and PV only when their operating assumptions are specified.
4. Convert the validated QUBO to an Ising cost Hamiltonian and implement QAOA in CUDA-Q.
