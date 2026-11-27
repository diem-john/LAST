"""Literature-reference wind fragility and weather-driven contingency sampling.

The reference curve is not calibrated to the synthetic Minxiong feeder. It is
only enabled for explicitly labelled sensitivity experiments.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from forecasting.data.ibtracs_regions import haversine_km
from grid.weather_faults import build_branch_contingency


def load_wind_fragility_config(path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("schema_version") != 1:
        raise ValueError("Wind fragility config schema_version must be 1")
    if config.get("calibration_status") not in {
        "uncalibrated_literature_reference", "locally_calibrated"
    }:
        raise ValueError("Unsupported calibration_status")
    if config.get("pole_spacing_m") is None or float(config["pole_spacing_m"]) <= 0:
        raise ValueError("pole_spacing_m must be positive")
    model = config.get("model_type", "exponential_literature_reference")
    if model == "exponential_literature_reference":
        required = ("pole_probability_intercept", "pole_probability_exponent_per_mph")
        if any(config.get(key) is None for key in required):
            raise ValueError(f"Fragility config requires {required}")
    elif model == "logistic_calibrated":
        if config.get("calibration_status") != "locally_calibrated":
            raise ValueError("logistic_calibrated requires calibration_status=locally_calibrated")
        if config.get("pole_logistic_intercept") is None or config.get("pole_logistic_slope_per_ms") is None:
            raise ValueError("Calibrated logistic model requires pole_logistic_intercept and pole_logistic_slope_per_ms")
    else:
        raise ValueError(f"Unsupported fragility model_type: {model}")
    return config


def pole_failure_probability(wind_speed_ms: float, config: dict[str, Any]) -> float:
    """Return pole failure probability from the configured reference or fitted curve."""
    speed = max(0.0, float(wind_speed_ms))
    model = config.get("model_type", "exponential_literature_reference")
    if model == "logistic_calibrated":
        z = float(config["pole_logistic_intercept"]) + float(config["pole_logistic_slope_per_ms"]) * speed
        value = 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, z))))
    else:
        wind_mph = speed / 0.44704
        intercept = float(config["pole_probability_intercept"])
        exponent = float(config["pole_probability_exponent_per_mph"])
        value = intercept * math.exp(min(60.0, exponent * wind_mph))
    return min(1.0, max(0.0, value))


def fit_logistic_pole_fragility(
    observations: pd.DataFrame,
    *,
    wind_column: str = "wind_speed_ms",
    failure_column: str = "failed",
    ridge: float = 1e-4,
    max_iterations: int = 200,
) -> dict[str, Any]:
    """Fit a regularized logistic pole-failure curve from paired exposure/outcome data."""
    missing = {wind_column, failure_column} - set(observations.columns)
    if missing:
        raise ValueError(f"Calibration observations missing columns: {sorted(missing)}")
    frame = observations[[wind_column, failure_column]].copy()
    frame[wind_column] = pd.to_numeric(frame[wind_column], errors="coerce")
    frame[failure_column] = pd.to_numeric(frame[failure_column], errors="coerce")
    frame = frame.dropna()
    if not frame[wind_column].ge(0).all() or not frame[failure_column].isin([0, 1]).all():
        raise ValueError("Calibration requires nonnegative wind_speed_ms and binary failed labels")
    y = frame[failure_column].to_numpy(dtype=float)
    x_wind = frame[wind_column].to_numpy(dtype=float)
    failures = int(y.sum())
    nonfailures = int(len(y) - failures)
    if len(y) < 20 or failures < 5 or nonfailures < 5:
        raise ValueError("Calibration requires >=20 records, >=5 failures, and >=5 non-failures")
    if float(np.std(x_wind)) <= 1e-9:
        raise ValueError("Calibration wind speeds must have nonzero variance")
    design = np.column_stack([np.ones(len(x_wind)), x_wind])
    beta = np.array([math.log((failures + 0.5) / (nonfailures + 0.5)), 0.0])
    penalty = np.diag([0.0, float(ridge)])
    converged = False
    for _ in range(max_iterations):
        logits = np.clip(design @ beta, -40.0, 40.0)
        probability = 1.0 / (1.0 + np.exp(-logits))
        gradient = design.T @ (y - probability) - penalty @ beta
        weights = probability * (1.0 - probability)
        hessian = design.T @ (weights[:, None] * design) + penalty + np.eye(2) * 1e-10
        step = np.linalg.solve(hessian, gradient)
        beta_next = beta + step
        if not np.isfinite(beta_next).all():
            raise ValueError("Logistic fragility fit became non-finite")
        beta = beta_next
        if float(np.linalg.norm(step)) < 1e-8:
            converged = True
            break
    logits = np.clip(design @ beta, -40.0, 40.0)
    probability = 1.0 / (1.0 + np.exp(-logits))
    eps = 1e-12
    log_likelihood = float(np.sum(y * np.log(probability + eps) + (1-y) * np.log(1-probability + eps)))
    return {
        "model_type": "logistic_calibrated",
        "pole_logistic_intercept": float(beta[0]),
        "pole_logistic_slope_per_ms": float(beta[1]),
        "sample_count": int(len(y)),
        "failure_count": failures,
        "nonfailure_count": nonfailures,
        "wind_speed_min_ms": float(x_wind.min()),
        "wind_speed_max_ms": float(x_wind.max()),
        "log_likelihood": log_likelihood,
        "ridge_penalty": float(ridge),
        "converged": bool(converged),
        "fit_method": "regularized_newton_raphson",
    }


def estimate_synthetic_branch_lengths(
    bus_locations: pd.DataFrame, case: dict[str, Any]
) -> pd.DataFrame:
    lookup = bus_locations.set_index("bus_id")
    records = []
    for branch in case["branch"]:
        if not bool(branch.get("in_service", False)):
            continue
        u, v = int(branch["from_bus"]), int(branch["to_bus"])
        a, b = lookup.loc[u], lookup.loc[v]
        length = float(haversine_km(
            [a["latitude"]], [a["longitude"]], b["latitude"], b["longitude"]
        )[0] * 1000.0)
        records.append({
            "branch_id": int(branch["branch_id"]),
            "from_bus": u,
            "to_bus": v,
            "synthetic_straight_line_length_m": length,
        })
    return pd.DataFrame(records)


def calculate_branch_wind_fragility(
    exposure: pd.DataFrame,
    branch_lengths: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    required = {"storm_instance_id", "timestamp_utc", "asset_type", "branch_id", "wind_speed_ms"}
    if missing := required - set(exposure.columns):
        raise ValueError(f"Exposure table missing columns: {sorted(missing)}")
    rows = exposure.loc[exposure["asset_type"] == "branch"].copy()
    if rows.empty:
        raise ValueError("No branch wind exposure rows found")
    rows["branch_id"] = pd.to_numeric(rows["branch_id"], errors="raise").astype(int)
    rows["wind_speed_ms"] = pd.to_numeric(rows["wind_speed_ms"], errors="raise")
    rows = rows.merge(branch_lengths, on="branch_id", how="left", validate="many_to_one")
    if rows["synthetic_straight_line_length_m"].isna().any():
        raise ValueError("Some exposed branches have no synthetic length")
    spacing = float(config["pole_spacing_m"])
    rows["assumed_pole_count"] = np.maximum(
        1, np.ceil(rows["synthetic_straight_line_length_m"] / spacing).astype(int) + 1
    )
    rows["pole_failure_probability"] = rows["wind_speed_ms"].map(
        lambda value: pole_failure_probability(value, config)
    )
    rows["branch_failure_probability"] = 1.0 - np.power(
        1.0 - rows["pole_failure_probability"], rows["assumed_pole_count"]
    )
    rows["fragility_model_status"] = str(config["calibration_status"])
    rows["pole_spacing_assumption_m"] = spacing
    rows["probability_model"] = "independent_pole_failures_aggregated_to_branch"
    rows["calibration_note"] = str(config.get("calibration_note", ""))
    return rows


def select_peak_network_snapshot(probabilities: pd.DataFrame) -> pd.DataFrame:
    """Select one timestamp per storm with the largest branch wind exposure."""
    if probabilities.empty:
        return probabilities.copy()
    maxima = probabilities.groupby(
        ["storm_instance_id", "timestamp_utc"], as_index=False
    )["wind_speed_ms"].max().rename(columns={"wind_speed_ms": "network_peak_wind_ms"})
    maxima = maxima.sort_values(
        ["storm_instance_id", "network_peak_wind_ms", "timestamp_utc"],
        ascending=[True, False, True], kind="stable",
    )
    peak = maxima.drop_duplicates("storm_instance_id", keep="first")
    selected = probabilities.merge(
        peak[["storm_instance_id", "timestamp_utc", "network_peak_wind_ms"]],
        on=["storm_instance_id", "timestamp_utc"], how="inner", validate="many_to_one",
    )
    return selected.sort_values(["storm_instance_id", "branch_id"], kind="stable").reset_index(drop=True)


def sample_weather_contingencies(
    peak_probabilities: pd.DataFrame,
    case: dict[str, Any],
    *,
    samples_per_storm: int = 100,
    seed: int = 42,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if samples_per_storm < 1:
        raise ValueError("samples_per_storm must be at least 1")
    rng = random.Random(seed)
    scenarios: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    for storm_id, group in peak_probabilities.groupby("storm_instance_id", sort=True):
        group = group.sort_values("branch_id", kind="stable")
        timestamp = str(group.iloc[0]["timestamp_utc"])
        probs = [
            (int(row.branch_id), float(row.branch_failure_probability))
            for row in group.itertuples(index=False)
        ]
        network_peak = float(group["network_peak_wind_ms"].iloc[0])
        for sample in range(samples_per_storm):
            failed = [branch for branch, probability in probs if rng.random() < probability]
            contingency = build_branch_contingency(case, failed)
            scenarios.append({
                "scenario_id": f"IBWX-{len(scenarios) + 1:07d}",
                "storm_instance_id": str(storm_id),
                "event_timestamp_utc": timestamp,
                "sample_index": sample,
                "random_seed": int(seed),
                "network_peak_wind_ms": network_peak,
                "failed_branch_ids": failed,
                "failed_branch_count": len(failed),
                "branch_failure_probabilities": [
                    {"branch_id": branch, "probability": probability}
                    for branch, probability in probs
                ],
                "fragility_model_status": str(group["fragility_model_status"].iloc[0]),
                "contingency": contingency,
                "sampling_assumption": "conditional_independent_branch_failures_given_wind_field",
                "topology_only": True,
                "electrical_power_flow_validated": False,
            })
        event_rows.append({
            "storm_instance_id": str(storm_id),
            "event_timestamp_utc": timestamp,
            "network_peak_wind_ms": network_peak,
            "branch_count": int(len(group)),
            "expected_failed_branch_count": float(sum(p for _, p in probs)),
            "max_branch_failure_probability": float(group["branch_failure_probability"].max()),
            "fragility_model_status": str(group["fragility_model_status"].iloc[0]),
        })
    return scenarios, event_rows
