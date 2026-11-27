# Phase 7K — Minimal Cut Sets and Restoration Scenario Preparation

## Purpose

Phase 7K converts Phase 7J topology-only representative contingencies into:
1. bus-specific minimal branch-failure cut-set records;
2. unique outage states grouped by their exact slack-disconnected bus sets; and
3. single normally-open tie-switch closure candidates that increase the number of slack-reachable buses.

This is a scenario-preparation stage for later restoration optimization. It does not execute switching or certify an electrically feasible restoration.

## Inputs

- `reports/ibtracs/phase_7j/phase_7j_representative_contingencies.csv`
- `data/electrical/ieee33bw_reference.json`

The benchmark case's nominal bus loads are used only to quantify benchmark load disconnected/restored. They are not real Chiayi or Taipower customer loads.

## Run

```bash
python scripts/run_ibtracs_minimal_cut_sets_restoration.py
```

Optional paths:

```bash
python scripts/run_ibtracs_minimal_cut_sets_restoration.py \
  --contingencies reports/ibtracs/phase_7j/phase_7j_representative_contingencies.csv \
  --case data/electrical/ieee33bw_reference.json \
  --output-dir reports/ibtracs/phase_7k
```

## Outputs

- `phase_7k_minimal_bus_cut_sets.csv`: minimality is assessed per isolated bus, only against the supplied screened contingency family. A branch-failure set is retained for a bus if no strict subset in the input also disconnects that bus.
- `phase_7k_unique_outage_states.csv`: exact slack-disconnected bus sets are deduplicated; one representative contingency is selected using fewest failed branches, then larger marginal risk-score sum, then contingency ID.
- `phase_7k_restoration_candidates.csv`: one normally-open tie closure is proposed when it increases slack-reachable buses for the representative outage state. Reports restored buses and benchmark nominal load.
- `phase_7k_manifest.json`: input/output paths, counts, and interpretation limits.

## Interpretation and limitations

- Minimal cut sets are relative to the Phase 7J screened family (up to three failed branches among the selected top-risk branches); they are not exhaustive cut sets for the complete feeder.
- Unique states are topological equivalence classes, not distinct physical damage mechanisms.
- A tie closure can create a loop or violate protection coordination. This phase does not choose a sectionalizing switch to preserve radiality.
- Load values are the canonical IEEE-33 benchmark values, not measured local loads.
- No AC power flow, voltage, thermal, protection, fault-current, switching-sequence, BESS, or distributed-generation constraints are modeled.
- Upstream fragility remains an uncalibrated literature-reference model, and network geometry remains synthetic.
- The outputs are candidate inputs for Phase 8 optimization, not operational recommendations.

## Phase 8 handoff

Use unique outage states as restoration instances. Treat tie closures as binary candidate actions only after adding explicit operating constraints and validating resulting configurations with an AC power-flow solver. Compare a classical optimizer and QAOA on the same objective, constraints, and instances; do not assume QAOA is superior.
