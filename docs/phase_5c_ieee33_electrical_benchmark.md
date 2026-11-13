# Phase 5C — Canonical IEEE 33-Bus Electrical Benchmark and Power-Flow Baseline

## Scope and separation of layers
Phase 5C establishes the canonical Baran–Wu/MATPOWER IEEE 33-bus electrical reference and validates its base radial operating point. It does not infer line impedances from the synthetic Chiayi bus coordinates. The geographic placement is a separate spatial layer; standard benchmark electrical data remain unchanged.

## 5C.1 Canonical reference dataset
Source: MATPOWER `data/case33bw.m`, which identifies the Baran and Wu 1989 network-reconfiguration paper (DOI 10.1109/61.25627). See https://github.com/MATPOWER/matpower/blob/master/data/case33bw.m and https://matpower.org/docs/ref/matpower6.0/case33bw.html.
- 33 buses, 12.66 kV line-to-line base, 10 MVA base.
- Bus 1 is the slack/reference bus; buses 2–33 are PQ loads.
- 3,715 kW and 2,300 kVAr aggregate demand.
- 32 normally closed radial branches and five normally open tie branches.
- Source branch R/X are in ohms; loads are kW/kVAr.
The full transcribed source data are retained in `data/electrical/ieee33bw_reference.json`, including the five open ties.

## 5C.2 Bus loads
The source loads are preserved per bus without scaling. The canonical data records active/reactive demand and voltage limits. The 0.9–1.1 pu limits are reference-case limits, not a claim about Taipower's actual service standards.

## 5C.3 Branch impedances and bases
The source branch resistance/reactance are retained in ohms. Per-unit impedance is calculated as:
`Z_base = V_base,LL^2 / S_base,3phase`, `Z_pu = (R+jX)/Z_base`.
The base values are 12.66 kV and 10 MVA. No GIS distance or OSM road geometry is used to derive R/X.

## 5C.4 Deterministic power flow
The script uses a balanced three-phase equivalent backward/forward-sweep solver. The five normally open tie branches are excluded from the base radial solve. It exports bus voltage/angle, branch current/loss, slack injection, convergence and balance diagnostics.

## 5C.5 Validation
Automated checks validate bus/branch counts, radial connected tree structure, total loads, convergence, voltage limits and active/reactive power balance. The report also compares nominal active losses and minimum voltage against a published IEEE 33-bus base-case table (202.67 kW and 0.9131 pu; minimum at Bus 18), using explicit tolerances. This is a literature-reference comparison, not an independent execution of MATPOWER. For stronger cross-tool validation, run the same source case in MATPOWER or pandapower and compare bus voltages, branch flows and losses. The script's own tests are regression checks, not independent validation. Reference comparison source: https://beei.org/index.php/EEI/article/download/509/346.

## Run
```powershell
python scripts/run_ieee33bw_power_flow.py
python -m pytest tests/test_ieee33_power_flow.py -q
```

Outputs:
- `reports/electrical/ieee33bw_power_flow.json`
- `reports/electrical/ieee33bw_bus_results.csv`
- `reports/electrical/ieee33bw_branch_results.csv`

## Caveats
This is the canonical benchmark electrical model attached to a synthetic geographic point layout. It is not a validated model of a real Chiayi/Taipower feeder. No actual conductor routes, conductor types, transformer impedances, utility protection settings, measured loads, or utility operating limits have been supplied. Do not use this benchmark result for operational switching or dispatch.
