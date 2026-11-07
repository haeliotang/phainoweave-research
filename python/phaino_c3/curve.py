"""Risk–coverage curves from frozen adequacy statistics (artifact-only)."""

from __future__ import annotations

import math
from typing import Any, Iterable, Optional

import numpy as np


def _ratio(num: float, den: float) -> Optional[float]:
    if den is None or not math.isfinite(den) or den == 0:
        return None
    return abs(float(num)) / abs(float(den))


def severity_components(record: dict[str, Any]) -> dict[str, float]:
    """Per-test normalized severity (lower is better) from one candidate record."""
    adequacy = record.get("adequacy", {}) or {}
    metrics = adequacy.get("key_metrics", {}) or {}
    thresholds = adequacy.get("effective_thresholds", {}) or {}
    parts: dict[str, float] = {}

    auto_m = metrics.get("autocorrelation", {}) or {}
    auto_t = thresholds.get("autocorrelation", {}) or {}
    for key, tkey in (
        ("ljung_box_statistic", "ljung_box_statistic_max"),
        ("max_abs_acf", "max_abs_acf_max"),
    ):
        r = _ratio(auto_m.get(key, 0.0), auto_t.get(tkey, 0.0))
        if r is not None:
            parts[key] = r

    time_m = metrics.get("time_structure", {}) or {}
    time_t = thresholds.get("time_structure", {}) or {}
    for key, tkey in (
        ("corr_time", "abs_corr_time_max"),
        ("quadratic_coefficient_over_sigma_f", "abs_quadratic_coefficient_max"),
        ("max_abs_phase_correlation", "abs_phase_correlation_max"),
    ):
        r = _ratio(time_m.get(key, 0.0), time_t.get(tkey, 0.0))
        if r is not None:
            parts[key] = r

    block = metrics.get("block_prediction", {}) or {}
    if block.get("median_normalized_rmse") is not None:
        # No effective threshold is recorded for block prediction in the sealed
        # artifact; keep it as an unnormalized diagnostic, not part of severity.
        parts["block_median_normalized_rmse_raw"] = float(block["median_normalized_rmse"])

    return parts


def severity(record: dict[str, Any]) -> float:
    parts = severity_components(record)
    ratios = [v for k, v in parts.items() if not k.endswith("_raw")]
    if not ratios:
        return float("inf")
    return max(ratios)


def build_curve(
    trials: Iterable[dict[str, Any]],
    candidate: str,
    mechanism: str = "correct_cv",
    label_key: str = "truth_correct",
) -> dict[str, Any]:
    """Coverage/risk of accepting trials with severity <= t, sweeping t.

    label is 1 for a scientifically correct conclusion (truth within the frozen
    tolerance); risk is the fraction of accepted trials whose label is 0.
    Coverage is accepted / all trials in the stratum (selective prediction).
    """
    rows = []
    for trial in trials:
        if mechanism is not None and trial.get("mechanism") != mechanism:
            continue
        rec = trial.get("candidates", {}).get(candidate)
        if not rec:
            continue
        ev = trial.get("evaluation_only", {}) or {}
        label = bool(ev.get(label_key, False))
        rows.append((severity(rec), label))
    if not rows:
        raise ValueError(f"no trials for candidate={candidate!r} mechanism={mechanism!r}")
    rows.sort(key=lambda x: x[0])
    n = len(rows)
    accepted = 0
    wrong = 0
    points = [{"severity": 0.0, "coverage": 0.0, "risk": None, "accepted": 0, "n": n}]
    last = None
    for sev, label in rows:
        accepted += 1
        wrong += 0 if label else 1
        last = sev
        points.append(
            {
                "severity": sev,
                "coverage": accepted / n,
                "risk": wrong / accepted,
                "accepted": accepted,
                "n": n,
            }
        )
    return {
        "candidate": candidate,
        "mechanism": mechanism,
        "n": n,
        "n_wrong": sum(1 for _, label in rows if not label),
        "points": points,
    }


def _interp_risk(curve: dict[str, Any], coverage: float) -> Optional[float]:
    pts = curve["points"]
    xs = [p["coverage"] for p in pts if p["risk"] is not None]
    ys = [p["risk"] for p in pts if p["risk"] is not None]
    if not xs or coverage <= xs[0]:
        return ys[0] if xs else None
    if coverage >= xs[-1]:
        return ys[-1]
    return float(np.interp(coverage, xs, ys))


def matched_risk(
    curves: dict[str, dict[str, Any]],
    coverages: Iterable[float] = (0.25, 0.5, 0.75, 0.9),
    baseline: Optional[str] = None,
) -> dict[str, Any]:
    grid = [float(c) for c in coverages]
    values = {name: [_interp_risk(curve, c) for c in grid] for name, curve in curves.items()}
    out: dict[str, Any] = {"coverages": grid, "risk": values}
    if baseline:
        out["difference_vs_baseline"] = {
            name: [
                (None if v is None or b is None else v - b)
                for v, b in zip(values[name], values[baseline])
            ]
            for name in curves
        }
    return out


def bootstrap_matched_difference(
    trials: list[dict[str, Any]],
    candidate: str,
    baseline: str,
    mechanism: str = "correct_cv",
    coverages: Iterable[float] = (0.25, 0.5, 0.75, 0.9),
    replicates: int = 500,
    seed: int = 20261105,
) -> dict[str, Any]:
    """Bootstrap over independent trials (not frames) for matched-risk difference."""
    rows = []
    for trial in trials:
        if trial.get("mechanism") != mechanism:
            continue
        if candidate not in trial.get("candidates", {}) or baseline not in trial.get("candidates", {}):
            continue
        rows.append(trial)
    if len(rows) < 3:
        raise ValueError("need at least 3 paired trials for bootstrap")
    rng = np.random.default_rng(seed)
    grid = [float(c) for c in coverages]
    diffs = np.full((replicates, len(grid)), np.nan)
    for b in range(replicates):
        sample = [rows[i] for i in rng.integers(0, len(rows), len(rows))]
        try:
            c_curve = build_curve(sample, candidate, mechanism)
            b_curve = build_curve(sample, baseline, mechanism)
        except ValueError:
            continue
        for j, cov in enumerate(grid):
            rc = _interp_risk(c_curve, cov)
            rb = _interp_risk(b_curve, cov)
            if rc is not None and rb is not None:
                diffs[b, j] = rc - rb
    out = {"coverages": grid, "n_trials": len(rows), "replicates": replicates}
    out["difference"] = {}
    for j, cov in enumerate(grid):
        col = diffs[:, j]
        col = col[np.isfinite(col)]
        if col.size:
            out["difference"][str(cov)] = {
                "mean": float(np.mean(col)),
                "ci95": [float(np.percentile(col, 2.5)), float(np.percentile(col, 97.5))],
                "n_valid_replicates": int(col.size),
            }
        else:
            out["difference"][str(cov)] = None
    return out
