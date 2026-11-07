"""Model-check metrics, tolerance checks, and deterministic cluster intervals.

Metrics are computed per held-out cell and aggregated by geometry. Intervals are derived
by a deterministic cluster bootstrap over held-out cell aggregates, weighted by each cell's
``n_independent_units``. The contract does not contain unit-level records, so the bootstrap
never resamples frames and reports that limitation explicitly.
"""

from __future__ import annotations

import hashlib
import math
import random
from bisect import bisect_right
from typing import Any, Mapping, Sequence

from .artifacts import (
    AcfPoint,
    ActualStats,
    Artifact,
    Cell,
    OPTIONAL_TOLERANCES,
    PredictedStats,
    REQUIRED_TOLERANCES,
)

Z_95 = 1.959963984540054
BOOTSTRAP_REPLICATES = 1000
GEOMETRY_BIN_EDGES = (0.0, 200.0, 400.0, 800.0, 1600.0, 3200.0, 6400.0, 12800.0)
METRIC_NAMES = (
    "error_mean_abs_hz",
    "error_rms_abs_hz",
    "acf_max_abs_diff",
    "acf_lag1_abs_diff",
    "distribution_ks",
    "decision_frr_abs_error_pp",
)


def evaluate_model(
    artifact: Artifact, model: str, bootstrap_replicates: int = BOOTSTRAP_REPLICATES
) -> dict[str, Any]:
    """Per-model held-out calibration, geometry table, tolerance checks and intervals."""
    cells = [
        _cell_metrics(cell, model, artifact.tolerances) for cell in artifact.heldout_cells
    ]
    aggregate = _aggregate(cells)
    intervals = _intervals(cells, model, bootstrap_replicates)
    geometry: dict[str, Any] = {}
    for geometry_bin in geometry_bins():
        label = geometry_bin["label"]
        subset = [
            cell
            for cell in cells
            if geometry_bin["lower"] <= cell["geometry_m"] < geometry_bin["upper"]
        ] if geometry_bin["upper"] is not None else [
            cell for cell in cells if cell["geometry_m"] >= geometry_bin["lower"]
        ]
        if not subset:
            continue
        geometry[label] = {
            **geometry_bin,
            "n_cells": len(subset),
            "n_independent_units": sum(cell["n_independent_units"] for cell in subset),
            "aggregate": _aggregate(subset),
            "intervals": _intervals(subset, model, bootstrap_replicates),
            "passes_all_cells": all(cell["passes_tolerances"] for cell in subset),
            "cells": [cell["cell_id"] for cell in subset],
            "failed_checks": _failed_checks(subset),
        }
    failed_checks = _failed_checks(cells)
    return {
        "model": model,
        "heldout_cell_count": len(cells),
        "n_independent_units": sum(cell["n_independent_units"] for cell in cells),
        "cells": cells,
        "aggregate": aggregate,
        "intervals": intervals,
        "by_geometry": geometry,
        "passes_all_heldout": all(cell["passes_tolerances"] for cell in cells),
        "failed_checks": failed_checks,
        "failed_geometry_bins": sorted(
            label for label, data in geometry.items() if not data["passes_all_cells"]
        ),
    }


def cell_metrics_for_model(
    cell: Cell, model: str, tolerances: Mapping[str, float] | None = None
) -> dict[str, Any]:
    """One cell/model metric row; tolerances default to open-ended checks."""
    effective = dict(tolerances or {})
    effective.setdefault("decision_frr_abs_error_pp", float("inf"))
    effective.setdefault("distribution_ks_max", float("inf"))
    return _cell_metrics(cell, model, effective)


def _cell_metrics(cell: Cell, model: str, tolerances: Mapping[str, float]) -> dict[str, Any]:
    actual = cell.actual
    predicted = cell.predicted[model]
    error_mean = abs(predicted.error_mean_hz - actual.error_mean_hz)
    error_rms = abs(predicted.error_rms_hz - actual.error_rms_hz)
    acf_difference, acf_lags = acf_discrepancy(actual.acf, predicted.acf)
    lag1_difference = acf_difference_at(actual.acf, predicted.acf, 1.0)
    ks = ks_statistic(actual.lb_stats, predicted.lb_stats)
    frr_abs_pp = abs(predicted.frr - actual.frr) * 100.0
    actual_interval = wilson_interval(actual.frr, actual.n_trials)
    difference_interval = None
    if actual_interval is not None:
        difference_interval = (
            (predicted.frr - actual_interval[1]) * 100.0,
            (predicted.frr - actual_interval[0]) * 100.0,
        )
    checks = _tolerance_checks(
        tolerances,
        decision_frr_abs_error_pp=frr_abs_pp,
        distribution_ks=ks,
        error_mean_abs_hz=error_mean,
        error_rms_abs_hz=error_rms,
        acf_max_abs=acf_difference,
    )
    return {
        "cell_id": cell.cell_id,
        "geometry_m": cell.geometry_m,
        "geometry_bin": geometry_bin_label(cell.geometry_m),
        "speed_mps": cell.speed_mps,
        "snr_db": cell.snr_db,
        "split": cell.split,
        "resampling_unit": cell.resampling_unit,
        "n_trials": actual.n_trials,
        "n_independent_units": cell.n_independent_units,
        "fit_scope": cell.fit_scopes.get(model),
        "actual_frr": actual.frr,
        "predicted_frr": predicted.frr,
        "decision_frr_abs_error_pp": frr_abs_pp,
        "actual_frr_wilson_95": list(actual_interval) if actual_interval else None,
        "predicted_minus_actual_pp_interval": list(difference_interval)
        if difference_interval
        else None,
        "error_mean_abs_hz": error_mean,
        "error_rms_abs_hz": error_rms,
        "acf_max_abs_diff": acf_difference,
        "acf_common_lags": acf_lags,
        "acf_lag1_abs_diff": lag1_difference,
        "distribution_ks": ks,
        "lb_actual_n": len(actual.lb_stats),
        "lb_predicted_n": len(predicted.lb_stats),
        "tolerance_checks": checks,
        "passes_tolerances": all(check["pass"] for check in checks.values()),
    }


def _tolerance_checks(
    tolerances: Mapping[str, float],
    *,
    decision_frr_abs_error_pp: float,
    distribution_ks: float,
    error_mean_abs_hz: float,
    error_rms_abs_hz: float,
    acf_max_abs: float | None,
) -> dict[str, Any]:
    checks: dict[str, Any] = {
        "decision_frr_abs_error_pp": {
            "value": decision_frr_abs_error_pp,
            "tolerance": tolerances["decision_frr_abs_error_pp"],
            "pass": decision_frr_abs_error_pp <= tolerances["decision_frr_abs_error_pp"],
        },
        "distribution_ks_max": {
            "value": distribution_ks,
            "tolerance": tolerances["distribution_ks_max"],
            "pass": distribution_ks <= tolerances["distribution_ks_max"],
        },
    }
    if "error_mean_abs_hz" in tolerances:
        checks["error_mean_abs_hz"] = {
            "value": error_mean_abs_hz,
            "tolerance": tolerances["error_mean_abs_hz"],
            "pass": error_mean_abs_hz <= tolerances["error_mean_abs_hz"],
        }
    if "error_rms_abs_hz" in tolerances:
        checks["error_rms_abs_hz"] = {
            "value": error_rms_abs_hz,
            "tolerance": tolerances["error_rms_abs_hz"],
            "pass": error_rms_abs_hz <= tolerances["error_rms_abs_hz"],
        }
    if "acf_max_abs" in tolerances:
        checks["acf_max_abs"] = {
            "value": acf_max_abs,
            "tolerance": tolerances["acf_max_abs"],
            "pass": acf_max_abs is not None and acf_max_abs <= tolerances["acf_max_abs"],
        }
    return checks


def _aggregate(cells: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for metric in METRIC_NAMES:
        values = [cell[metric] for cell in cells if cell[metric] is not None]
        if not values:
            result[metric] = {"mean": None, "max": None, "n": 0}
        else:
            result[metric] = {
                "mean": sum(values) / len(values),
                "max": max(values),
                "n": len(values),
            }
    result["n_cells"] = len(cells)
    result["n_independent_units"] = sum(cell["n_independent_units"] for cell in cells)
    result["pass_count"] = sum(1 for cell in cells if cell["passes_tolerances"])
    result["fail_count"] = len(cells) - result["pass_count"]
    return result


def _failed_checks(cells: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for cell in cells:
        for name, check in cell["tolerance_checks"].items():
            if not check["pass"]:
                failures.append(
                    {
                        "cell_id": cell["cell_id"],
                        "tolerance": name,
                        "value": check["value"],
                        "limit": check["tolerance"],
                    }
                )
    return failures


def _intervals(
    cells: Sequence[Mapping[str, Any]], model: str, replicates: int
) -> dict[str, Any]:
    intervals: dict[str, Any] = {}
    weights = [float(cell["n_independent_units"]) for cell in cells]
    for metric in METRIC_NAMES:
        pairs = [
            (cell[metric], weight)
            for cell, weight in zip(cells, weights)
            if cell[metric] is not None
        ]
        values = [value for value, _ in pairs]
        metric_weights = [weight for _, weight in pairs]
        seed = _stable_seed(f"{model}:{metric}:{len(values)}")
        intervals[metric] = bootstrap_interval(
            values, metric_weights, seed=seed, replicates=replicates
        )
    return {
        "method": "deterministic_cluster_bootstrap_over_cell_aggregates",
        "resampling_basis": "held-out cells, weighted by n_independent_units; frames are never resampled",
        "frame_resampling": False,
        "bootstrap_replicates": replicates,
        "n_clusters": len(cells),
        "n_independent_units": sum(int(weight) for weight in weights),
        "metrics": intervals,
    }


def bootstrap_interval(
    values: Sequence[float],
    weights: Sequence[float],
    *,
    seed: int,
    replicates: int = BOOTSTRAP_REPLICATES,
    z: float = Z_95,
) -> dict[str, Any]:
    """Deterministic weighted cluster bootstrap over cell aggregates.

    Each resample draws ``n`` cells with replacement, probability proportional to the
    cell's independent-unit count. The point and resampled means are weighted by those
    unit counts. Unit-level records are unavailable in the contract, so this is a cluster
    bootstrap over cells, never a frame bootstrap.
    """
    if not values:
        return {
            "point": None,
            "interval": None,
            "n_clusters": 0,
            "n_independent_units": 0,
            "bootstrap_replicates": replicates,
            "seed": seed,
        }
    if len(values) != len(weights):
        raise ValueError("values and weights must have the same length")
    total_units = sum(weights)
    if total_units <= 0:
        raise ValueError("weights must sum to a positive value")
    point = sum(value * weight for value, weight in zip(values, weights)) / total_units
    if len(values) == 1:
        return {
            "point": point,
            "interval": [point, point],
            "n_clusters": 1,
            "n_independent_units": int(total_units),
            "bootstrap_replicates": replicates,
            "seed": seed,
        }
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(replicates):
        indices = rng.choices(range(len(values)), weights=weights, k=len(values))
        selected_weight = sum(weights[index] for index in indices)
        estimate = sum(values[index] * weights[index] for index in indices) / selected_weight
        estimates.append(estimate)
    estimates.sort()
    return {
        "point": point,
        "interval": [_quantile(estimates, 0.025), _quantile(estimates, 0.975)],
        "n_clusters": len(values),
        "n_independent_units": int(total_units),
        "bootstrap_replicates": replicates,
        "seed": seed,
    }


def _quantile(sorted_values: Sequence[float], probability: float) -> float:
    if not sorted_values:
        raise ValueError("cannot take a quantile of no values")
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = probability * (len(sorted_values) - 1)
    lower = int(math.floor(position))
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] * (1.0 - fraction) + sorted_values[upper] * fraction


def _stable_seed(key: str) -> int:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def acf_discrepancy(
    actual: Sequence[AcfPoint], predicted: Sequence[AcfPoint]
) -> tuple[float | None, list[float]]:
    """Max absolute ACF difference on the common lag support (linear interpolation)."""
    if not actual or not predicted:
        return None, []
    actual_lags = [point.lag_s for point in actual]
    predicted_lags = [point.lag_s for point in predicted]
    lower = max(min(actual_lags), min(predicted_lags))
    upper = min(max(actual_lags), max(predicted_lags))
    if upper < lower:
        return None, []
    candidates = sorted(
        {lag for lag in actual_lags + predicted_lags if lower <= lag <= upper}
    )
    if not candidates:
        return None, []
    differences = [
        abs(_interpolate_acf(actual, lag) - _interpolate_acf(predicted, lag))
        for lag in candidates
    ]
    return max(differences), candidates


def acf_difference_at(
    actual: Sequence[AcfPoint], predicted: Sequence[AcfPoint], lag: float
) -> float | None:
    if not actual or not predicted:
        return None
    if lag < min(point.lag_s for point in actual) or lag < min(
        point.lag_s for point in predicted
    ):
        return None
    if lag > max(point.lag_s for point in actual) or lag > max(
        point.lag_s for point in predicted
    ):
        return None
    return abs(_interpolate_acf(actual, lag) - _interpolate_acf(predicted, lag))


def _interpolate_acf(points: Sequence[AcfPoint], lag: float) -> float:
    ordered = sorted(points, key=lambda point: point.lag_s)
    if lag <= ordered[0].lag_s:
        return ordered[0].value
    if lag >= ordered[-1].lag_s:
        return ordered[-1].value
    for left, right in zip(ordered, ordered[1:]):
        if left.lag_s <= lag <= right.lag_s:
            if right.lag_s == left.lag_s:
                return right.value
            fraction = (lag - left.lag_s) / (right.lag_s - left.lag_s)
            return left.value + (right.value - left.value) * fraction
    return ordered[-1].value


def ks_statistic(actual: Sequence[float], predicted: Sequence[float]) -> float:
    """Two-sample empirical-CDF KS statistic (no p-value, no global p99)."""
    if not actual or not predicted:
        raise ValueError("KS needs non-empty actual and predicted samples")
    left = sorted(actual)
    right = sorted(predicted)
    values = sorted(set(left) | set(right))
    maximum = 0.0
    for value in values:
        cdf_left = bisect_right(left, value) / len(left)
        cdf_right = bisect_right(right, value) / len(right)
        maximum = max(maximum, abs(cdf_left - cdf_right))
    return maximum


def wilson_interval(
    proportion: float, total: int, z: float = Z_95
) -> tuple[float, float] | None:
    """Wilson 95% interval for an actual FRR from n independent trials."""
    if total <= 0:
        return None
    proportion = min(1.0, max(0.0, proportion))
    denominator = 1.0 + z * z / total
    centre = (proportion + z * z / (2.0 * total)) / denominator
    half = (
        z
        * math.sqrt(proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total))
        / denominator
    )
    return (max(0.0, centre - half), min(1.0, centre + half))


def geometry_bin_label(value: float) -> str:
    index = bisect_right(GEOMETRY_BIN_EDGES, value) - 1
    if index < 0:
        index = 0
    if index >= len(GEOMETRY_BIN_EDGES) - 1:
        return f"[{GEOMETRY_BIN_EDGES[-1]:g},inf)"
    return f"[{GEOMETRY_BIN_EDGES[index]:g},{GEOMETRY_BIN_EDGES[index + 1]:g})"


def geometry_bins() -> list[dict[str, Any]]:
    bins: list[dict[str, Any]] = []
    for index in range(len(GEOMETRY_BIN_EDGES)):
        lower = GEOMETRY_BIN_EDGES[index]
        upper = GEOMETRY_BIN_EDGES[index + 1] if index + 1 < len(GEOMETRY_BIN_EDGES) else None
        label = f"[{lower:g},inf)" if upper is None else f"[{lower:g},{upper:g})"
        bins.append({"label": label, "lower": lower, "upper": upper})
    return bins


def tolerance_summary(tolerances: Mapping[str, float]) -> dict[str, Any]:
    return {
        "required": list(REQUIRED_TOLERANCES),
        "optional": [key for key in OPTIONAL_TOLERANCES if key in tolerances],
        "unused": sorted(
            key
            for key in tolerances
            if key not in REQUIRED_TOLERANCES and key not in OPTIONAL_TOLERANCES
        ),
        "values": dict(sorted(tolerances.items())),
    }


def model_reference_comparison(
    reference: Any, models: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Descriptive reference-vs-model FRR comparison; no selection."""
    result: list[dict[str, Any]] = []
    for model, metrics in models.items():
        mean_frr = metrics["aggregate"]["decision_frr_abs_error_pp"]
        # The model's predicted FRR is available per cell; use the weighted mean of cells.
        predicted_values = [
            cell["predicted_frr"] for cell in metrics["cells"]
        ]
        predicted_mean = (
            sum(predicted_values) / len(predicted_values) if predicted_values else None
        )
        result.append(
            {
                "model": model,
                "mean_predicted_frr": predicted_mean,
                "reference_minus_predicted_frr": (
                    reference.frr - predicted_mean if predicted_mean is not None else None
                ),
                "decision_abs_error_pp": mean_frr["mean"],
                "interpretation": "descriptive only; not a repaired-candidate comparison and not a selection",
            }
        )
    return result
