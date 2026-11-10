# SOP-GRID-TY-001
## Extreme Weather and Flood Mitigation for Project LAST: Modified IEEE 33-Bus Distribution Network

| Document attribute | Value |
|---|---|
| Document ID | SOP-GRID-TY-001 |
| Version | 1.1 |
| Status | Research / simulation operating reference |
| Reference benchmark | Dolatabadi et al., *An Enhanced IEEE 33 Bus Benchmark Test System for Distribution System Studies*, IEEE Transactions on Power Systems, 2021 |
| Nominal voltage | 12.66 kV |
| Normal configuration | Radial |
| Intended users | Dispatch operators, power systems engineers, and research personnel |

> **Operational limitation:** This SOP is a research and simulation reference, not an approved utility switching order. It must not be used for field switching until the modified single-line diagram, equipment ratings, protection coordination, grounding, interlocks, and operating procedures have been reviewed and approved by the responsible utility authority.

---

## 1. Purpose and scope

This SOP establishes deterministic operating procedures for Project LAST, an LLM-Augmented SCADA Telemetry decision-support framework for extreme-weather distribution-grid operations.

It addresses:

1. Typhoon-induced photovoltaic (PV) generation reduction.
2. Flood-related infrastructure exposure at Bus 6.
3. Two-sided isolation of the flood-exposed Bus 6.
4. Feasibility assessment for islanding Buses 7–18.
5. Emergency battery energy storage system (BESS) dispatch.
6. Preservation of Hospital Bus 15 and Emergency Shelter Bus 30.
7. Controlled non-critical load shedding.
8. Post-event inspection and grid restoration.

The SOP is intended for ingestion into a local, air-gapped Retrieval-Augmented Generation (RAG) system. The Edge-LLM provides advisory recommendations only. All physical switching and dispatch remain subject to deterministic checks and authorized human confirmation.

## 2. Reference network and project-specific modifications

### 2.1 Published benchmark

Project LAST adopts the enhanced IEEE 33-bus distribution benchmark described by Dolatabadi et al. (2021). The published benchmark specifies:

- 33 buses and a 12.66-kV nominal system.
- 32 fixed branches and three switchable tie branches.
- A normal radial configuration and an alternative meshed configuration.
- Total active demand of 3.715 MW and total reactive demand of 2.3 MVAr.
- A bus-voltage operating range of 0.95–1.05 p.u.
- Switchable branches 33, 34, and 35, connecting buses 21–8, 9–15, and 25–29, respectively.
- In the radial configuration, branches 33, 34, and 35 are open.

The published benchmark identifies DG locations at Buses 18, 22, 25, and 33. Its ESS discussion covers candidate installations at Buses 18, 22, 25, and 33. Project LAST modifies these placements as described below; the project-specific placements must not be attributed to the original benchmark.

### 2.2 Project-specific configuration

| Asset | Bus | Project LAST configuration |
|---|---:|---|
| Main substation | 1 | Primary feeder supply |
| Solar PV | 12 | Distributed renewable generation |
| Solar PV | 24 | Distributed renewable generation |
| Solar PV | 31 | Distributed renewable generation |
| BESS | 18 | 100 kW / 200 kWh |
| BESS | 33 | 100 kW / 200 kWh |
| Hospital | 15 | Critical load |
| Emergency shelter | 30 | Critical load |
| Flood-exposed asset | 6 | River A exposure |

The project-specific PV locations, BESS ratings, critical-load assignments, flood exposure, and additional sectionalizers are modifications introduced by Project LAST.

### 2.3 Additional Bus 6 sectionalizers

Project LAST introduces two additional sectionalizing devices:

- **S5-6:** installed in series with the feeder connection between Buses 5 and 6.
- **S6-7:** installed in series with the feeder connection between Buses 6 and 7.

Both devices are normally closed in the normal radial operating configuration. They are additional project devices and are not the three switchable tie branches identified in the published benchmark.

The modified single-line diagram and equipment data must explicitly represent these devices, their location, ratings, switching capability, status feedback, and protection coordination.

## 3. Hazard scenario

### 3.1 Typhoon-induced PV disturbance

A severe typhoon causes an 80% reduction in PV output at Bus 12 relative to its baseline output:

\[
P_{PV,12}(t)=0.20P_{PV,12,baseline}.
\]

PV generation at Buses 24 and 31 is monitored independently. The Bus 12 reduction triggers a generation-deficit assessment and BESS reserve evaluation. Telemetry quality must be checked to distinguish a physical generation reduction from communication or sensor failure.

### 3.2 River A flood hazard

UP-TCAGP LiPAD three-dimensional flood telemetry indicates that River A is breaching, with a projected inundation depth of 2 m at Bus 6 within 30 minutes.

The 30-minute horizon is a forecast, not a guaranteed failure time. The decision process must consider current and projected depth, inundation probability, rate of rise, forecast confidence, asset exposure, and telemetry freshness.

### 3.3 Combined contingency

The combined hazard introduces reduced renewable generation and potential loss of the normal feeder supply path to Buses 7–18. Hospital Bus 15 is the designated critical load in the affected section. The operator must assess isolation, island feasibility, BESS capability, and critical-load demand before taking action.

## 4. Operational safety and authority

### 4.1 Authority hierarchy

1. Protection system operation and personnel/equipment safety.
2. Authorized dispatch operator decisions.
3. Approved switching orders and utility operating procedures.
4. Validated SCADA and hazard telemetry.
5. AI-generated contextual recommendations.

### 4.2 Prohibited autonomous actions

The Edge-LLM shall not:

- Operate S5-6, S6-7, or any other field device.
- Modify relay protection settings or override interlocks.
- Initiate unsupervised islanding or reconnection.
- Invent bus measurements, BESS ratings, SoC, inverter capabilities, or load demand.
- Declare an island stable without electrical validation.
- Treat a flood forecast as proof of physical equipment failure.
- Infer that BESS nameplate power and energy ratings establish grid-forming capability.

### 4.3 Switching verification

Before switching, the authorized operator must verify device identity, switching and interrupting ratings, approved switching sequence, protection coordination, electrical isolation, possible DER backfeed, status indication, grounding requirements, and personnel safety. The actual switching order and device capabilities must be established by the approved engineering study.

## 5. Standard operating procedures

### SOP-001 — Typhoon and PV disturbance detection

**Trigger:** PV output at Bus 12 decreases by 80% relative to its validated baseline.

**Actions:**

1. Retrieve PV active and reactive power measurements at Buses 12, 24, and 31.
2. Validate the Bus 12 generation reduction and telemetry quality.
3. Assess total available renewable generation.
4. Retrieve BESS SoC and operating status at Buses 18 and 33.
5. Evaluate generation-demand imbalance and available reserves.
6. Notify the dispatch operator and increase monitoring as required.

**Deterministic rule:** IF Bus 12 PV output is 80% below its validated baseline, THEN initiate generation-deficit assessment and retrieve BESS reserve measurements at Buses 18 and 33.

### SOP-002 — Flood monitoring and preventive assessment at Bus 6

**Trigger:** Flood telemetry projects 2 m inundation at Bus 6 within 30 minutes.

**Actions:**

1. Retrieve current and projected flood depth at Bus 6.
2. Retrieve inundation probability, forecast confidence, and time-to-inundation.
3. Check telemetry timestamp, freshness, and sensor validity.
4. Identify the downstream network boundary and critical loads.
5. Notify the dispatch operator.
6. Prepare the approved two-sided isolation procedure.
7. Assess the downstream section's islanding resources and electrical feasibility.

**Deterministic rule:** IF projected Bus 6 inundation reaches 2 m within 30 minutes, THEN classify Bus 6 as a high-priority flood-exposed asset and initiate contingency preparation and preventive isolation assessment.

A forecast alone does not prove equipment failure or independently authorize switching.

### SOP-003 — Two-sided isolation of Bus 6

**Trigger:** Bus 6 is confirmed compromised, or preventive isolation is authorized under the applicable flood-response procedure.

**Actions:**

1. Confirm the affected asset and network boundary.
2. Identify S5-6 and S6-7 on the approved single-line diagram.
3. Verify device status, ratings, switching capability, and the approved switching order.
4. Obtain dispatch authorization.
5. Open S5-6 and S6-7 in the approved sequence.
6. Verify both open positions using available status indications and independent checks as required.
7. Verify that Bus 6 is electrically isolated from both adjacent feeder sections.
8. Check for unintended backfeed from DERs or other sources.
9. Confirm the resulting supply condition of Buses 7–18.
10. Assess the downstream section for intentional island operation.

**Deterministic rule:** IF Bus 6 is confirmed compromised or preventive isolation is authorized, THEN open both S5-6 and S6-7 according to the approved switching procedure to isolate Bus 6 from the upstream and downstream networks.

**Expected topology outcome:** Bus 6 is separated from Buses 5 and 7. Buses 7–18 lose their normal upstream supply path through Bus 6 and become a candidate section for controlled islanding. This outcome does not establish that the section is stable or capable of sustaining load.

### SOP-004 — Controlled islanding assessment for Buses 7–18

**Trigger:** S5-6 and S6-7 are confirmed open and the downstream section has lost its normal main-grid supply.

**Actions:**

1. Confirm the electrical boundary and all connected branches and loads.
2. Retrieve voltage and frequency measurements.
3. Evaluate active and reactive power balance.
4. Assess available PV generation at Bus 12.
5. Retrieve BESS 18 SoC, operating mode, inverter limits, and availability.
6. Verify grid-forming capability if BESS 18 is expected to establish the island voltage/frequency reference.
7. Check protection coordination, grounding, fault-current adequacy, and load pickup requirements.
8. Verify electrical connectivity to Hospital Bus 15.
9. Initiate island operation only under an approved and electrically feasible procedure.

**Deterministic rule:** IF both sectionalizers are open AND BESS 18 is available with verified grid-forming capability AND the downstream section satisfies voltage, frequency, protection, power, and energy constraints, THEN the operator may authorize controlled island operation of Buses 7–18.

### SOP-005 — Hospital preservation using BESS 18

**Trigger:** Hospital Bus 15 is threatened by loss of its normal feeder supply.

**BESS 18 project rating:**

- Maximum rated active discharge power: 100 kW.
- Nominal energy capacity: 200 kWh.

**Actions:**

1. Retrieve Hospital Bus 15 active and reactive demand.
2. Retrieve BESS 18 SoC and operating status.
3. Calculate usable energy above the configured minimum SoC.
4. Verify inverter active/reactive capability and discharge limits.
5. Verify grid-forming capability if island operation requires it.
6. Verify the electrical path between BESS 18 and Hospital Bus 15.
7. Assess voltage, frequency, protection, and load feasibility.
8. Prioritize Hospital Bus 15 within the feasible island capacity.
9. Dispatch only after operator authorization and applicable checks.
10. Continuously monitor remaining energy and critical-load continuity.

**Deterministic rule:** IF Hospital Bus 15 loses normal supply AND BESS 18 is available AND an electrically valid supply path exists, THEN prioritize feasible BESS 18 support for Hospital Bus 15.

BESS 18 shall not be assumed capable of independently supplying the hospital without verifying hospital demand, inverter capability, electrical connectivity, and island constraints.

### SOP-006 — Emergency shelter preservation using BESS 33

**Trigger:** Emergency Shelter Bus 30 loses or is at risk of losing normal supply.

**BESS 33 project rating:**

- Maximum rated active discharge power: 100 kW.
- Nominal energy capacity: 200 kWh.

**Actions:**

1. Retrieve Bus 30 active and reactive demand.
2. Retrieve BESS 33 SoC and operating status.
3. Monitor PV generation at Bus 31.
4. Verify electrical connectivity between BESS 33 and Bus 30.
5. Determine available discharge power and usable energy.
6. Verify inverter and grid-forming capabilities as required.
7. Assess whether an electrically valid supply configuration exists.
8. Dispatch only after authorization and feasibility checks.
9. Monitor voltage, frequency, and remaining energy.

**Deterministic rule:** IF Emergency Shelter Bus 30 loses normal supply AND BESS 33 is available AND an electrically valid supply configuration exists, THEN prioritize feasible BESS 33 support for the shelter.

### SOP-007 — BESS energy management

BESS 18 and BESS 33 are independently monitored and controlled. Their nameplate ratings are:

| Parameter | BESS 18 | BESS 33 |
|---|---:|---:|
| Rated active discharge power | 100 kW | 100 kW |
| Nominal energy capacity | 200 kWh | 200 kWh |

For each BESS:

\[
0 \le P_{discharge,i} \le 100\text{ kW}.
\]

A simplified usable-energy estimate is:

\[
E_{usable,i}=E_{nominal,i}(SoC_i-SoC_{min,i})\eta_{discharge,i}.
\]

SoC and minimum SoC are fractions in this expression. Efficiency, minimum SoC, maximum SoC, reactive capability, ramp limits, and auxiliary consumption must be configured from the selected battery/inverter model. Do not assume unspecified values.

**Deterministic rules:**

- IF requested active discharge exceeds 100 kW, THEN constrain the request to the configured inverter operating limit.
- IF SoC reaches the configured emergency reserve threshold, THEN initiate non-critical load curtailment assessment and reassess critical-load feasibility.
- IF BESS telemetry is missing or stale, THEN mark its availability and energy as unknown; do not assume it is dispatchable.

### SOP-008 — Critical load shedding

**Trigger:** Available generation and feasible BESS discharge cannot support all connected demand within operating limits.

**Actions:**

1. Calculate active and reactive power imbalance.
2. Identify non-critical loads using the approved load-priority schedule.
3. Determine the required curtailment.
4. Preserve Hospital Bus 15 and Emergency Shelter Bus 30 wherever electrically feasible.
5. Execute authorized non-critical load shedding.
6. Monitor voltage, frequency, and BESS reserve.
7. Reassess critical-load continuity.

**Deterministic rule:** IF available island generation plus feasible BESS discharge is insufficient to support connected demand, THEN initiate controlled non-critical load shedding according to the approved priority schedule.

### SOP-009 — Post-flood assessment and restoration

**Trigger:** Flood levels recede and Bus 6 is considered for restoration.

**Actions:**

1. Obtain field inspection results for Bus 6 and associated equipment.
2. Verify equipment integrity, insulation condition, grounding, and absence of hazardous water ingress.
3. Verify protection relay and circuit-breaker functionality.
4. Obtain formal authorization that Bus 6 is safe for energization.
5. Confirm the approved restoration switching sequence.
6. Restore upstream and downstream connections in the approved sequence.
7. Verify the resulting topology and protection status.
8. If a downstream island is energized, verify applicable synchronization conditions before reconnection.
9. Monitor voltage, frequency, and protection behavior after restoration.

**Deterministic rule:** IF Bus 6 has been inspected and declared electrically safe AND protection and switching requirements are satisfied, THEN execute the approved restoration procedure. Reconnect an energized island only after synchronization requirements are verified.

## 6. Voltage, frequency, and feasibility constraints

The published benchmark voltage range is:

\[
0.95\text{ p.u.} \le V_{bus} \le 1.05\text{ p.u.}
\]

This benchmark voltage range is a reference operating constraint. The project must separately establish island frequency limits, inverter protection settings, reactive power capability, and transient acceptance criteria from its selected equipment and operating standards.

An island-feasibility assessment must consider at least:

- Active and reactive power balance.
- Voltage magnitude and frequency.
- BESS active/reactive power capability.
- BESS usable energy and SoC reserve.
- Grid-forming or grid-following mode.
- Network connectivity and branch limits.
- Protection coordination and fault-current adequacy.
- Load pickup and shedding requirements.

## 7. Canonical deterministic rules for RAG retrieval

The following rules are independently retrievable knowledge units. Their identifiers must be retained in document metadata and LLM output citations.

**GRID-001 — PV generation disturbance:** IF Bus 12 PV output is 80% below its validated baseline, THEN initiate generation-deficit assessment and retrieve BESS reserve measurements at Buses 18 and 33.

**GRID-002 — Flood warning:** IF projected Bus 6 inundation reaches 2 m within 30 minutes, THEN classify Bus 6 as a high-priority flood-exposed asset and initiate contingency preparation.

**GRID-003 — Bus 6 two-sided isolation:** IF Bus 6 is confirmed compromised or preventive isolation is authorized, THEN open S5-6 and S6-7 according to the approved switching procedure.

**GRID-004 — Downstream island assessment:** IF S5-6 and S6-7 are confirmed open, THEN assess Buses 7–18 for controlled island operation.

**GRID-005 — Grid-forming requirement:** IF BESS 18 is required to establish the downstream island voltage/frequency reference, THEN verify grid-forming capability, SoC, inverter limits, protection compatibility, and electrical connectivity.

**GRID-006 — Hospital preservation:** IF Hospital Bus 15 loses normal supply, THEN assess BESS 18 support and prioritize feasible critical-load supply.

**GRID-007 — Shelter preservation:** IF Shelter Bus 30 loses normal supply, THEN assess BESS 33 and PV 31 support capability.

**GRID-008 — BESS power limit:** IF requested active discharge exceeds the configured 100-kW rating, THEN constrain the request to the verified inverter operating limit.

**GRID-009 — Emergency reserve:** IF BESS SoC reaches its configured emergency reserve threshold, THEN initiate non-critical load curtailment assessment.

**GRID-010 — Load shedding:** IF available island generation and feasible storage discharge are insufficient, THEN initiate controlled non-critical load shedding.

**GRID-011 — Restoration:** IF Bus 6 is inspected and declared safe, THEN execute the approved restoration procedure and verify synchronization requirements before reconnecting an energized island.

## 8. Edge-LLM decision-support requirements

The local RAG architecture shall use the supplied telemetry, the modified project topology, and retrieved SOP provisions. Each generated recommendation shall include:

1. Severity classification.
2. Detected condition and telemetry timestamp.
3. Affected buses and critical loads.
4. Applicable SOP rule identifiers.
5. Recommended operator actions.
6. Electrical feasibility constraints.
7. Unknown or stale measurements.
8. Required human verification.

The LLM shall not infer electrical feasibility from BESS presence or nameplate ratings alone. Each action recommendation must be traceable to supplied telemetry or retrieved SOP provisions. Missing information must be reported as unknown, not filled by invention.

## 9. Document control

Version 1.1 supersedes Version 1.0 for the Project LAST research configuration. It introduces the radial benchmark baseline, project-specific PV/BESS and critical-load placements, two additional Bus 6 sectionalizers, and custom BESS ratings.

Changes to topology, DER ratings, battery constraints, protection coordination, or critical-load assignments require engineering review and a new controlled revision.

**End of SOP-GRID-TY-001, Version 1.1**

---

## Reference

S. H. Dolatabadi, M. Ghorbanian, P. Siano, and N. D. Hatziargyriou, “An Enhanced IEEE 33 Bus Benchmark Test System for Distribution System Studies,” *IEEE Transactions on Power Systems*, vol. 36, no. 3, pp. 2565–2572, May 2021, doi: 10.1109/TPWRS.2020.3038030.
