"""Constraint-preserving one-hot formulation for Phase 8.1.

Choice 0 is the explicit no-action option. Choices 1..n map to the sorted
single-tie restoration candidates. Feasible solutions have Hamming weight 1.
"""
from __future__ import annotations

import math
from itertools import combinations
from typing import Any

import pandas as pd


def build_one_hot_problem(candidates: pd.DataFrame) -> dict[str, Any]:
    """Build the one-hot choice model, including a zero-benefit no-action choice."""
    required = {"restoration_candidate_id", "candidate_tie_branch_id", "restored_load_kw"}
    missing = required - set(candidates.columns)
    if missing:
        raise ValueError(f"Candidate table missing columns: {sorted(missing)}")

    ordered = candidates.sort_values(
        ["candidate_tie_branch_id", "restoration_candidate_id"], kind="stable"
    ).reset_index(drop=True)
    numeric = pd.to_numeric(ordered["restored_load_kw"], errors="raise")
    if numeric.isna().any():
        raise ValueError("restored_load_kw contains missing values")
    if ordered["candidate_tie_branch_id"].duplicated().any():
        raise ValueError("Each outage state may contain only one candidate per tie branch")

    action_benefits = []
    for value in numeric:
        benefit = float(value)
        if not math.isfinite(benefit):
            raise ValueError("restored_load_kw must contain finite values")
        action_benefits.append(max(0.0, benefit))

    # Index 0 is no action; candidate i is stored at choice index i + 1.
    benefits = [0.0, *action_benefits]
    choice_count = len(benefits)
    return {
        "candidate_rows": ordered,
        "action_count": len(action_benefits),
        "choice_count": choice_count,
        "benefits_kw": benefits,
        "no_action_index": 0,
        "initial_bitstring": "1" + "0" * (choice_count - 1),
        "mixer_edges": [(i, j) for i, j in combinations(range(choice_count), 2)],
        "constraint": "exactly_one_choice_including_no_action",
        "objective": "minimize_negative_nominal_load_restored_kw",
    }


def is_one_hot(bits: tuple[int, ...] | list[int]) -> bool:
    return bool(bits) and all(bit in (0, 1) for bit in bits) and sum(bits) == 1


def evaluate_one_hot_energy(
    bits: tuple[int, ...] | list[int], problem: dict[str, Any]
) -> float:
    if len(bits) != problem["choice_count"] or not is_one_hot(bits):
        raise ValueError("Bit vector must be one-hot over no-action and restoration choices")
    return float(-sum(benefit * bit for benefit, bit in zip(problem["benefits_kw"], bits)))


def solve_one_hot_exact(problem: dict[str, Any]) -> dict[str, Any]:
    """Return the exact best one-hot choice; ties prefer the no-action option."""
    benefits = problem["benefits_kw"]
    best_index = 0
    best_energy = 0.0
    for index, benefit in enumerate(benefits[1:], start=1):
        energy = -float(benefit)
        if energy < best_energy - 1e-12:
            best_index, best_energy = index, energy

    bits = tuple(1 if i == best_index else 0 for i in range(len(benefits)))
    selected = []
    if best_index:
        selected = [int(problem["candidate_rows"].iloc[best_index - 1]["candidate_tie_branch_id"])]
    return {
        "status": "optimal_exact",
        "bitstring": "".join(str(bit) for bit in bits),
        "choice_index": best_index,
        "selected_tie_branch_ids": selected,
        "qubo_energy": float(best_energy),
        "restored_load_kw": float(-best_energy),
        "feasible": True,
        "feasible_search_space_size": len(benefits),
        "enumerated_bitstrings": 2 ** len(benefits),
    }
