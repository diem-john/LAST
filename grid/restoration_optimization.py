"""Phase 8 restoration QUBO construction and classical reference solver.

The initial formulation selects at most one single-tie restoration action per
Phase 7K outage state. This bounded first-stage model is intentionally not a
multi-switch restoration planner and is not electrically validated.
"""
from __future__ import annotations

from itertools import product
from typing import Any

import pandas as pd


def build_restoration_qubo(
    candidates: pd.DataFrame,
    *,
    penalty_factor: float = 1.0,
) -> dict[str, Any]:
    """Build E(x) = -sum(benefit_i*x_i) + P*sum_{i<j}(x_i*x_j)."""
    if penalty_factor < 1.0:
        raise ValueError("penalty_factor must be at least 1.0 to guarantee constraint dominance")
    required = {"restoration_candidate_id", "candidate_tie_branch_id", "restored_load_kw"}
    missing = required - set(candidates.columns)
    if missing:
        raise ValueError(f"Candidate table missing columns: {sorted(missing)}")

    ordered = candidates.sort_values(
        ["candidate_tie_branch_id", "restoration_candidate_id"], kind="stable"
    ).reset_index(drop=True)
    numeric_benefits = pd.to_numeric(ordered["restored_load_kw"], errors="raise")
    if numeric_benefits.isna().any():
        raise ValueError("restored_load_kw contains missing values")
    if ordered["candidate_tie_branch_id"].duplicated().any():
        raise ValueError("Each outage state may contain only one candidate per tie branch")
    benefits = [max(0.0, float(value)) for value in numeric_benefits]
    n = len(ordered)
    penalty = penalty_factor * (sum(benefits) + 1.0)
    linear = [-value for value in benefits]
    quadratic = {(i, j): penalty for i in range(n) for j in range(i + 1, n)}
    return {
        "candidate_rows": ordered,
        "variable_count": n,
        "benefits_kw": benefits,
        "linear": linear,
        "quadratic": quadratic,
        "penalty": penalty,
        "constraint": "at_most_one_tie_action",
        "no_action_bitstring": "0" * n,
    }


def evaluate_qubo(bits: tuple[int, ...] | list[int], qubo: dict[str, Any]) -> float:
    if len(bits) != qubo["variable_count"] or any(bit not in (0, 1) for bit in bits):
        raise ValueError("Bit vector must contain one binary value per QUBO variable")
    energy = sum(a * bit for a, bit in zip(qubo["linear"], bits))
    energy += sum(
        coefficient * bits[i] * bits[j]
        for (i, j), coefficient in qubo["quadratic"].items()
    )
    return float(energy)


def is_feasible_at_most_one(bits: tuple[int, ...] | list[int]) -> bool:
    return sum(bits) <= 1


def solve_classical_exact(qubo: dict[str, Any]) -> dict[str, Any]:
    """Enumerate every binary vector; exact for the small tie-action set."""
    import time

    started = time.perf_counter()
    n = int(qubo["variable_count"])
    best_bits = tuple(0 for _ in range(n))
    best_energy = evaluate_qubo(best_bits, qubo)
    feasible_count = 0
    for bits in product((0, 1), repeat=n):
        if not is_feasible_at_most_one(bits):
            continue
        feasible_count += 1
        energy = evaluate_qubo(bits, qubo)
        if energy < best_energy - 1e-12:
            best_bits, best_energy = bits, energy
    selected = [
        int(qubo["candidate_rows"].iloc[i]["candidate_tie_branch_id"])
        for i, bit in enumerate(best_bits) if bit
    ]
    benefit = sum(value * bit for value, bit in zip(qubo["benefits_kw"], best_bits))
    return {
        "status": "optimal_exact",
        "bitstring": "".join(str(bit) for bit in best_bits),
        "selected_tie_branch_ids": selected,
        "qubo_energy": float(best_energy),
        "restored_load_kw": float(benefit),
        "feasible": True,
        "feasible_search_space_size": feasible_count,
        "enumerated_bitstrings": 2 ** n,
        "runtime_seconds": time.perf_counter() - started,
    }


def qubo_to_ising(qubo: dict[str, Any]) -> dict[str, Any]:
    """Convert binary QUBO coefficients to H = constant + h.Z + J.ZZ."""
    n = int(qubo["variable_count"])
    linear_spin = [-0.5 * float(a) for a in qubo["linear"]]
    pair_spin = {}
    constant = 0.5 * sum(float(a) for a in qubo["linear"])
    for (i, j), coefficient in qubo["quadratic"].items():
        value = float(coefficient)
        constant += value / 4.0
        linear_spin[i] -= value / 4.0
        linear_spin[j] -= value / 4.0
        pair_spin[(i, j)] = value / 4.0
    return {
        "qubit_count": n,
        "constant": constant,
        "linear_z": linear_spin,
        "quadratic_zz": pair_spin,
    }


def prepare_phase8_scenarios(
    states: pd.DataFrame,
    candidates: pd.DataFrame,
) -> list[dict[str, Any]]:
    """Join Phase 7K unique outage states to their single-tie candidates."""
    if "outage_state_id" not in states.columns:
        raise ValueError("Unique outage states require outage_state_id")
    if "outage_state_id" not in candidates.columns:
        raise ValueError("Restoration candidates require outage_state_id")
    scenarios = []
    for state in states.sort_values("outage_state_id", kind="stable").to_dict("records"):
        scenario_id = str(state["outage_state_id"])
        subset = candidates[candidates["outage_state_id"].astype(str) == scenario_id].copy()
        scenarios.append({"state": state, "candidates": subset})
    return scenarios
