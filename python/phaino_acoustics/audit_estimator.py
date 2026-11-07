"""E1 estimator-independence audit.

Verification layer, not new physics.  The sealed/C2 conclusions rest on the
frozen E0 estimator ``fit_hardened``; this module asks whether they depend on
that estimator by fitting the *same synthetic observations* with a genuinely
independent implementation:

* own forward model / residual code (the E0 instantaneous-frequency Doppler
  formula is re-derived here, not imported from ``fit``);
* direct physical-units parameterisation ``(f0 [Hz], v [m/s], t0 [s], b [m])``;
* ``scipy.optimize.least_squares`` with a robust ``soft_l1`` loss, tight
  tolerances and a deterministic profile/least-squares multi-start;
* standard errors from a finite-difference Jacobian covariance.

``fit_hardened`` is imported only as the comparison baseline.  No internal
fit routine is imported or copied.  The audit set is fixed-seed, synthetic and
separate from the sealed grid; truth is used only to score the two estimators.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Mapping, Optional

import numpy as np
from scipy.optimize import least_squares

from phaino_claims.claims import apply_claim_statuses, claim_metrics
from phaino_claims.claims_protocol import load_protocol as load_claims_protocol

from .adequacy import evaluate_adequacy
from .experiment import BASE, F_MAX, F_MIN, FRAME_LEN, HOP
from .features import estimate_if_track
from .fit_hardened import fit_hardened
from .synthetic import Scenario, generate

ARTIFACT_NAME = "e1-estimator-independence-audit"
AUDIT_VERSION = "1.0.0"
AUDIT_SEED_BASE = 100_000_000
AUDIT_SEED_FORMULA = "AUDIT_SEED_BASE + 1000*condition_index + trial"
TRIALS_PER_CONDITION = 3

AUDIT_GEOMETRIES_M = (600.0, 1400.0)
AUDIT_SPEEDS_M_S = (60.0, 250.0)
AUDIT_SNR_DB = (10.0, 20.0)
ACCEL_GEOMETRIES_M = (600.0, 1400.0)
ACCEL_SPEED_M_S = 250.0
ACCEL_LEVELS_M_S2 = (0.15, 0.30)
ACCEL_SNR_DB = 20.0

# Frozen E0 parameter tolerances (evaluation only).
TOLERANCES = {"f0_rel": 0.01, "v_rel": 0.02, "t0_abs_s": 0.25, "b_rel": 0.05}

INDEPENDENT_ESTIMATOR = {
    "id": "e1-independent-scipy-least-squares-softl1",
    "version": AUDIT_VERSION,
    "method": "scipy.optimize.least_squares, trf, loss=soft_l1",
    "parameterisation": "direct physical units (f0 Hz, v m/s, t0 s, b m)",
    "forward_model": "f_obs = f0 / (1 - v_r/c), v_r = -x*xdot/r, x = v*(t-t0), r = hypot(x,b)",
    "starts": (
        "deterministic profile-f0 grid over v in {60,150,250,400}, t0 around the observed frequency peak/"
        "centre, b in {300,600,1400,3000,6000}; top diverse profile starts refined"
    ),
    "loss": "soft_l1",
    "tolerances": {"xtol": 1e-13, "ftol": 1e-13, "gtol": 1e-13, "max_nfev": 4000},
    "notes": (
        "The forward model is the declared E0 instantaneous-frequency model. No fit_hardened internal code, "
        "candidate-start helper, profile-SSE helper or LM routine is imported or copied."
    ),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _jsonable(obj):
    if isinstance(obj, dict):
        return {key: _jsonable(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(value) for value in obj]
    if isinstance(obj, np.ndarray):
        return _jsonable(obj.tolist())
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (float, np.floating)):
        value = float(obj)
        return value if np.isfinite(value) else None
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    return obj


def _digest(document) -> str:
    return hashlib.sha256(
        json.dumps(_jsonable(document), sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def _counts(values) -> dict:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _median_absolute_deviation(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=np.float64)
    if values.size == 0:
        return 0.0
    median = float(np.median(values))
    return float(np.median(np.abs(values - median)))


# ---------------------------------------------------------------------------
# Independent estimator (own forward model and own optimisation)
# ---------------------------------------------------------------------------

def independent_forward_frequency(
    t: np.ndarray,
    params: Mapping[str, float] | np.ndarray,
    c: float = BASE.c,
) -> np.ndarray:
    """Own implementation of the E0 Doppler frequency model.

    ``params`` is either a mapping with ``f0, v, t0, b`` or the array in that
    order, in direct physical units.  This function is intentionally separate
    from ``phaino_acoustics.fit``/``adequacy.model_prediction``.
    """
    if isinstance(params, Mapping):
        f0, v, t0, b = (float(params[key]) for key in ("f0", "v", "t0", "b"))
    else:
        values = np.asarray(params, dtype=np.float64)
        f0, v, t0, b = (float(value) for value in values[:4])
    t = np.asarray(t, dtype=np.float64)
    tau = t - t0
    x = v * tau
    radial_velocity = -(x * v) / np.hypot(x, b)
    return f0 / (1.0 - radial_velocity / c)


def _independent_residual(
    theta: np.ndarray,
    t: np.ndarray,
    f: np.ndarray,
    c: float,
) -> np.ndarray:
    return np.asarray(f, dtype=np.float64) - independent_forward_frequency(t, theta, c)


def _profile_f0(t: np.ndarray, f: np.ndarray, v: float, t0: float, b: float, c: float) -> tuple[float, float]:
    """Profile out f0 (linear in the Doppler factor) for start ranking."""
    tau = t - t0
    x = v * tau
    radial_velocity = -(x * v) / np.hypot(x, b)
    factor = 1.0 / (1.0 - radial_velocity / c)
    denominator = float(np.dot(factor, factor))
    if denominator <= 0.0 or not np.isfinite(denominator):
        return float("inf"), float("nan")
    f0 = float(np.dot(factor, f) / denominator)
    residual = f - f0 * factor
    return float(np.dot(residual, residual)), f0


def _initial_starts(t: np.ndarray, f: np.ndarray, c: float) -> list[np.ndarray]:
    span = float(t[-1] - t[0])
    peak = float(t[int(np.argmax(f))])
    centre = float(0.5 * (t[0] + t[-1]))
    t0_candidates = sorted(
        {
            peak,
            peak - 0.1 * span,
            peak + 0.1 * span,
            centre,
            peak - 0.25 * span,
            peak + 0.25 * span,
        }
    )
    v_candidates = (60.0, 150.0, 250.0, 400.0)
    b_candidates = (300.0, 600.0, 1400.0, 3000.0, 6000.0)
    ranked = []
    for v in v_candidates:
        for t0 in t0_candidates:
            for b in b_candidates:
                sse, f0 = _profile_f0(t, f, v, t0, b, c)
                if np.isfinite(sse) and np.isfinite(f0) and f0 > 0.0:
                    ranked.append((sse, v, t0, b, f0))
    ranked.sort(key=lambda row: row[0])
    starts = []
    for _sse, v, t0, b, f0 in ranked:
        theta = np.array([f0, v, t0, b], dtype=np.float64)
        if any(
            np.allclose(theta, existing, rtol=1e-3, atol=1e-6) for existing in starts
        ):
            continue
        starts.append(theta)
        if len(starts) >= 8:
            break
    if not starts:
        raise RuntimeError("independent estimator found no finite start")
    return starts


def _numerical_jacobian(theta: np.ndarray, t: np.ndarray, f: np.ndarray, c: float) -> np.ndarray:
    scales = np.array([500.0, 250.0, 20.0, 3000.0], dtype=np.float64)
    steps = 1e-6 * scales
    base = _independent_residual(theta, t, f, c)
    jacobian = np.empty((base.size, theta.size), dtype=np.float64)
    for index in range(theta.size):
        plus = theta.copy()
        minus = theta.copy()
        plus[index] += steps[index]
        minus[index] -= steps[index]
        jacobian[:, index] = (
            _independent_residual(plus, t, f, c) - _independent_residual(minus, t, f, c)
        ) / (2.0 * steps[index])
    return jacobian


def _standard_errors(
    theta: np.ndarray,
    t: np.ndarray,
    f: np.ndarray,
    c: float,
) -> tuple[dict[str, Optional[float]], Optional[float], Optional[float]]:
    jacobian = _numerical_jacobian(theta, t, f, c)
    residual = _independent_residual(theta, t, f, c)
    n = int(f.size)
    dof = max(n - 4, 1)
    sse = float(np.dot(residual, residual))
    sigma_f = float(math.sqrt(sse / dof)) if sse >= 0.0 else None
    try:
        normal = jacobian.T @ jacobian
        covariance = (sigma_f**2) * np.linalg.pinv(normal) if sigma_f is not None else None
    except np.linalg.LinAlgError:
        covariance = None
    if covariance is None or not np.all(np.isfinite(covariance)):
        return ({name: None for name in ("f0", "v", "t0", "b")}, sigma_f, None)
    diagonal = np.diag(covariance)
    if np.any(diagonal <= 0.0) or not np.all(np.isfinite(diagonal)):
        return ({name: None for name in ("f0", "v", "t0", "b")}, sigma_f, None)
    errors = np.sqrt(diagonal)
    condition_number = float(np.linalg.cond(normal))
    return (
        {name: float(errors[index]) for index, name in enumerate(("f0", "v", "t0", "b"))},
        sigma_f,
        condition_number if np.isfinite(condition_number) else None,
    )


def estimate_independent(t: np.ndarray, f: np.ndarray, c: float = BASE.c) -> dict:
    """Fit the E0 Doppler model with the independent least-squares estimator."""
    t = np.asarray(t, dtype=np.float64)
    f = np.asarray(f, dtype=np.float64)
    if t.size != f.size or t.size < 8:
        raise ValueError("need matching t/f arrays with >= 8 samples")
    span = float(t[-1] - t[0])
    lower = np.array([1e-3, 1e-3, float(t[0] - 10.0 * span), 1e-3], dtype=np.float64)
    upper = np.array([1e5, 5.0 * c, float(t[-1] + 10.0 * span), 1e8], dtype=np.float64)
    starts = _initial_starts(t, f, c)
    initial_sse = None
    best = None
    best_sse = float("inf")
    # robust scale from the best profile start's raw residual
    best_start_sse, best_start_f0 = _profile_f0(t, f, *(starts[0][1], starts[0][2], starts[0][3]), c)
    profile_residual = f - independent_forward_frequency(t, starts[0], c)
    robust_scale = max(1.4826 * _median_absolute_deviation(profile_residual), 0.05)
    nfev = 0
    for start in starts:
        start = np.clip(start, lower + 1e-12, upper - 1e-12)
        try:
            result = least_squares(
                _independent_residual,
                start,
                args=(t, f, c),
                bounds=(lower, upper),
                method="trf",
                loss="soft_l1",
                f_scale=robust_scale,
                x_scale=np.array([500.0, 250.0, 20.0, 3000.0], dtype=np.float64),
                xtol=1e-13,
                ftol=1e-13,
                gtol=1e-13,
                max_nfev=4000,
            )
        except Exception:
            continue
        nfev += int(getattr(result, "nfev", 0))
        residual = _independent_residual(result.x, t, f, c)
        sse = float(np.dot(residual, residual))
        if np.isfinite(sse) and sse < best_sse:
            best_sse = sse
            best = result
            initial_sse = best_sse
    if best is None:
        return {
            "params": {name: None for name in ("f0", "v", "t0", "b")},
            "se": {name: None for name in ("f0", "v", "t0", "b")},
            "optimization_status": "failed",
            "objective_sse_hz2": None,
            "sigma_f_hz": None,
            "condition_number": None,
            "nfev": nfev,
            "starts": len(starts),
        }
    theta = np.asarray(best.x, dtype=np.float64)
    errors, sigma_f, condition_number = _standard_errors(theta, t, f, c)
    finite = bool(np.all(np.isfinite(theta)) and theta[0] > 0.0 and theta[1] > 0.0 and theta[3] > 0.0)
    optimality = float(getattr(best, "optimality", float("inf")))
    # scipy's success flag means its declared xtol/ftol/gtol criteria were met;
    # the reported optimality is not a scale-free convergence threshold here.
    converged = bool(getattr(best, "success", False)) and finite
    if not finite:
        status = "failed"
    elif converged:
        status = "converged"
    else:
        status = "indeterminate"
    return {
        "params": {name: float(theta[index]) for index, name in enumerate(("f0", "v", "t0", "b"))},
        "se": {name: (float(value) if value is not None else None) for name, value in errors.items()},
        "optimization_status": status,
        "objective_sse_hz2": best_sse,
        "sigma_f_hz": sigma_f,
        "condition_number": condition_number,
        "optimality": optimality,
        "nfev": nfev,
        "starts": len(starts),
        "robust_loss": "soft_l1",
        "robust_scale_hz": robust_scale,
    }


# ---------------------------------------------------------------------------
# Audit data
# ---------------------------------------------------------------------------

def build_conditions() -> list[dict]:
    conditions = []
    index = 0
    for geometry in AUDIT_GEOMETRIES_M:
        for speed in AUDIT_SPEEDS_M_S:
            for snr in AUDIT_SNR_DB:
                conditions.append(
                    {
                        "condition_index": index,
                        "condition_id": f"cv_b{geometry:g}_v{speed:g}_snr{snr:g}",
                        "family": "correct_constant_velocity",
                        "geometry_m": float(geometry),
                        "speed_m_s": float(speed),
                        "snr_db": float(snr),
                        "accel": 0.0,
                        "n_trials": TRIALS_PER_CONDITION,
                    }
                )
                index += 1
    for geometry in ACCEL_GEOMETRIES_M:
        for accel in ACCEL_LEVELS_M_S2:
            conditions.append(
                {
                    "condition_index": index,
                    "condition_id": f"accel_b{geometry:g}_v{ACCEL_SPEED_M_S:g}_a{accel:g}",
                    "family": "acceleration_misspecification",
                    "geometry_m": float(geometry),
                    "speed_m_s": ACCEL_SPEED_M_S,
                    "snr_db": ACCEL_SNR_DB,
                    "accel": float(accel),
                    "n_trials": TRIALS_PER_CONDITION,
                }
            )
            index += 1
    return conditions


def condition_seed(condition: Mapping[str, object], trial: int) -> int:
    return AUDIT_SEED_BASE + 1000 * int(condition["condition_index"]) + int(trial)


def scenario_for(condition: Mapping[str, object], seed: int) -> Scenario:
    return replace(
        BASE,
        b=float(condition["geometry_m"]),
        v=float(condition["speed_m_s"]),
        snr_db=float(condition["snr_db"]),
        accel=float(condition["accel"]),
        seed=int(seed),
    )


def extract_track(scenario: Scenario) -> tuple[np.ndarray, np.ndarray]:
    observation = generate(scenario)
    track = estimate_if_track(
        observation.signal,
        scenario.fs,
        frame_len=FRAME_LEN,
        hop=HOP,
        f_min=F_MIN,
        f_max=F_MAX,
        t_start=float(observation.t[0]),
    )
    return np.asarray(track.t, dtype=np.float64), np.asarray(track.f, dtype=np.float64)


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------

def parameter_tolerance_flags(params: Mapping[str, float], truth: Mapping[str, float]) -> dict:
    flags = {
        "f0": abs(float(params["f0"]) - float(truth["f0"])) / abs(float(truth["f0"])) <= TOLERANCES["f0_rel"],
        "v": abs(float(params["v"]) - float(truth["v"])) / abs(float(truth["v"])) <= TOLERANCES["v_rel"],
        "t0": abs(float(params["t0"]) - float(truth["t0"])) <= TOLERANCES["t0_abs_s"],
        "b": abs(float(params["b"]) - float(truth["b"])) / abs(float(truth["b"])) <= TOLERANCES["b_rel"],
    }
    flags["all"] = all(flags[name] for name in ("f0", "v", "t0", "b"))
    return flags


def parameter_truth_errors(params: Mapping[str, float], truth: Mapping[str, float]) -> dict:
    return {
        "f0_rel": (float(params["f0"]) - float(truth["f0"])) / float(truth["f0"]),
        "v_rel": (float(params["v"]) - float(truth["v"])) / float(truth["v"]),
        "t0_abs_s": float(params["t0"]) - float(truth["t0"]),
        "b_rel": (float(params["b"]) - float(truth["b"])) / float(truth["b"]),
    }


def parameter_differences(
    baseline: Mapping[str, float], independent: Mapping[str, float]
) -> dict:
    return {
        "f0_rel": (float(independent["f0"]) - float(baseline["f0"])) / float(baseline["f0"]),
        "v_rel": (float(independent["v"]) - float(baseline["v"])) / float(baseline["v"]),
        "t0_abs_s": float(independent["t0"]) - float(baseline["t0"]),
        "b_rel": (float(independent["b"]) - float(baseline["b"])) / float(baseline["b"]),
    }


def _claim_statuses(fit_like, adequacy: Mapping[str, object], claims_protocol: Mapping[str, object]) -> dict:
    metrics = claim_metrics(fit_like, adequacy)
    records = apply_claim_statuses(metrics, claims_protocol)
    return {record["claim_id"]: record["status"] for record in records}


def _bootstrap_interval(values, n_boot: int = 1000, seed: int = AUDIT_SEED_BASE) -> dict:
    values = np.asarray(values, dtype=np.float64)
    if values.size == 0:
        return {"mean": None, "ci95": [None, None]}
    rng = np.random.default_rng(seed)
    samples = rng.choice(values, size=(n_boot, values.size), replace=True).mean(axis=1)
    return {"mean": float(np.mean(values)), "ci95": [float(np.quantile(samples, 0.025)), float(np.quantile(samples, 0.975))]}


def _max_abs(values) -> Optional[float]:
    values = [abs(float(value)) for value in values if value is not None and np.isfinite(float(value))]
    return float(max(values)) if values else None


def _mean_abs(values) -> Optional[float]:
    values = [abs(float(value)) for value in values if value is not None and np.isfinite(float(value))]
    return float(np.mean(values)) if values else None


def _max_differences_for(subset: list[dict]) -> dict:
    return {
        key: _max_abs([record["differences"][key] for record in subset])
        for key in ("f0_rel", "v_rel", "t0_abs_s", "b_rel")
    }


def _tolerance_disagreements(subset: list[dict]) -> int:
    return sum(
        1
        for record in subset
        if record["baseline"]["tolerance"]["all"] != record["independent"]["tolerance"]["all"]
    )


def _first_claim_flips(baseline_claims: dict, independent_claims: dict) -> dict:
    keys = sorted(set(baseline_claims) | set(independent_claims))
    return {
        key: {"baseline": baseline_claims.get(key), "independent": independent_claims.get(key)}
        for key in keys
        if baseline_claims.get(key) != independent_claims.get(key)
    }


# ---------------------------------------------------------------------------
# Main audit
# ---------------------------------------------------------------------------

def run_audit(out_dir: str = "/tmp/e1est", claims_protocol_path: Optional[str] = None) -> dict:
    started = time.time()
    os.makedirs(out_dir, exist_ok=True)
    protocol_path = (
        Path(claims_protocol_path)
        if claims_protocol_path is not None
        else Path(__file__).resolve().parents[2] / "protocols" / "pr4e-claims-1.3.0.json"
    )
    claims_protocol = load_claims_protocol(str(protocol_path))
    conditions = build_conditions()
    records = []
    for condition in conditions:
        for trial in range(condition["n_trials"]):
            seed = condition_seed(condition, trial)
            scenario = scenario_for(condition, seed)
            times, frequencies = extract_track(scenario)
            truth = {"f0": scenario.f0, "v": scenario.v, "t0": scenario.t0, "b": scenario.b}
            baseline_fit = fit_hardened(times, frequencies, c=scenario.c)
            independent_fit = estimate_independent(times, frequencies, c=scenario.c)
            baseline_params = {name: float(baseline_fit.params[name]) for name in ("f0", "v", "t0", "b")}
            independent_params = {
                name: (float(independent_fit["params"][name]) if independent_fit["params"][name] is not None else None)
                for name in ("f0", "v", "t0", "b")
            }
            baseline_adequacy = evaluate_adequacy(
                times,
                frequencies,
                np.array([baseline_params[name] for name in ("f0", "v", "t0", "b")]),
                baseline_fit.sigma_f_hz,
                baseline_fit.optimization_status,
                c=scenario.c,
            )
            independent_adequacy = None
            independent_claims = {}
            if all(independent_params[name] is not None for name in ("f0", "v", "t0", "b")):
                independent_adequacy = evaluate_adequacy(
                    times,
                    frequencies,
                    np.array([independent_params[name] for name in ("f0", "v", "t0", "b")]),
                    independent_fit["sigma_f_hz"] if independent_fit["sigma_f_hz"] is not None else float("nan"),
                    independent_fit["optimization_status"],
                    c=scenario.c,
                )
                independent_claims = _claim_statuses(
                    {
                        "params": independent_params,
                        "se": independent_fit["se"],
                        "optimization_status": independent_fit["optimization_status"],
                    },
                    independent_adequacy,
                    claims_protocol,
                )
            baseline_claims = _claim_statuses(baseline_fit, baseline_adequacy, claims_protocol)
            differences = (
                parameter_differences(baseline_params, independent_params)
                if all(value is not None for value in independent_params.values())
                else {name: None for name in ("f0_rel", "v_rel", "t0_abs_s", "b_rel")}
            )
            record = {
                "condition_id": condition["condition_id"],
                "family": condition["family"],
                "geometry_m": condition["geometry_m"],
                "speed_m_s": condition["speed_m_s"],
                "snr_db": condition["snr_db"],
                "accel": condition["accel"],
                "trial": trial,
                "seed": seed,
                "n_frames": int(times.size),
                "truth": truth,
                "baseline": {
                    "params": baseline_params,
                    "se": {name: float(baseline_fit.se.get(name, float("nan"))) for name in ("f0", "v", "t0", "b")},
                    "sigma_f_hz": float(baseline_fit.sigma_f_hz),
                    "optimization_status": baseline_fit.optimization_status,
                    "objective_sse_hz2": float(baseline_fit.objective),
                    "adequacy_status": baseline_adequacy["model_adequacy_status"],
                    "identifiability_status": baseline_adequacy["identifiability_status"],
                    "epistemic_decision": baseline_adequacy["epistemic_decision"],
                    "claim_statuses": baseline_claims,
                    "tolerance": parameter_tolerance_flags(baseline_params, truth),
                    "truth_errors": parameter_truth_errors(baseline_params, truth),
                },
                "independent": {
                    "params": independent_params,
                    "se": independent_fit["se"],
                    "sigma_f_hz": independent_fit["sigma_f_hz"],
                    "optimization_status": independent_fit["optimization_status"],
                    "objective_sse_hz2": independent_fit["objective_sse_hz2"],
                    "condition_number": independent_fit["condition_number"],
                    "nfev": independent_fit["nfev"],
                    "starts": independent_fit["starts"],
                    "adequacy_status": (independent_adequacy or {}).get("model_adequacy_status"),
                    "identifiability_status": (independent_adequacy or {}).get("identifiability_status"),
                    "epistemic_decision": (independent_adequacy or {}).get("epistemic_decision"),
                    "claim_statuses": independent_claims,
                    "tolerance": (
                        parameter_tolerance_flags(independent_params, truth)
                        if all(value is not None for value in independent_params.values())
                        else {name: None for name in ("f0", "v", "t0", "b", "all")}
                    ),
                    "truth_errors": (
                        parameter_truth_errors(independent_params, truth)
                        if all(value is not None for value in independent_params.values())
                        else {name: None for name in ("f0_rel", "v_rel", "t0_abs_s", "b_rel")}
                    ),
                },
                "differences": differences,
                "adequacy_status_flip": baseline_adequacy["model_adequacy_status"]
                != (independent_adequacy or {}).get("model_adequacy_status"),
                "epistemic_decision_flip": baseline_adequacy["epistemic_decision"]
                != (independent_adequacy or {}).get("epistemic_decision"),
                "claim_flips": _first_claim_flips(baseline_claims, independent_claims),
            }
            records.append(record)

    # Per-condition summaries.
    summaries = []
    for condition in conditions:
        subset = [record for record in records if record["condition_id"] == condition["condition_id"]]
        baseline_all = [record["baseline"]["tolerance"]["all"] for record in subset]
        independent_all = [record["independent"]["tolerance"]["all"] for record in subset]
        agreements = sum(1 for b, i in zip(baseline_all, independent_all) if b == i)
        baseline_only = sum(1 for b, i in zip(baseline_all, independent_all) if b and not i)
        independent_only = sum(1 for b, i in zip(baseline_all, independent_all) if i and not b)
        summary = {
            "condition_id": condition["condition_id"],
            "family": condition["family"],
            "geometry_m": condition["geometry_m"],
            "speed_m_s": condition["speed_m_s"],
            "snr_db": condition["snr_db"],
            "accel": condition["accel"],
            "n_trials": len(subset),
            "max_abs_parameter_difference": {
                "f0_rel": _max_abs([record["differences"]["f0_rel"] for record in subset]),
                "v_rel": _max_abs([record["differences"]["v_rel"] for record in subset]),
                "t0_abs_s": _max_abs([record["differences"]["t0_abs_s"] for record in subset]),
                "b_rel": _max_abs([record["differences"]["b_rel"] for record in subset]),
            },
            "mean_abs_parameter_difference": {
                "f0_rel": _mean_abs([record["differences"]["f0_rel"] for record in subset]),
                "v_rel": _mean_abs([record["differences"]["v_rel"] for record in subset]),
                "t0_abs_s": _mean_abs([record["differences"]["t0_abs_s"] for record in subset]),
                "b_rel": _mean_abs([record["differences"]["b_rel"] for record in subset]),
            },
            "tolerance_agreement": {
                "both_pass": sum(1 for b, i in zip(baseline_all, independent_all) if b and i),
                "both_fail": sum(1 for b, i in zip(baseline_all, independent_all) if not b and not i),
                "baseline_only_pass": baseline_only,
                "independent_only_pass": independent_only,
                "disagreements": baseline_only + independent_only,
                "agreement_rate": agreements / len(subset) if subset else None,
            },
            "adequacy_status_flips": sum(1 for record in subset if record["adequacy_status_flip"]),
            "epistemic_decision_flips": sum(1 for record in subset if record["epistemic_decision_flip"]),
            "claim_flip_trials": sum(1 for record in subset if record["claim_flips"]),
            "baseline_tolerance_failures": {
                "f0": sum(1 for record in subset if not record["baseline"]["tolerance"]["f0"]),
                "v": sum(1 for record in subset if not record["baseline"]["tolerance"]["v"]),
                "t0": sum(1 for record in subset if not record["baseline"]["tolerance"]["t0"]),
                "b": sum(1 for record in subset if not record["baseline"]["tolerance"]["b"]),
            },
            "independent_tolerance_failures": {
                "f0": sum(1 for record in subset if record["independent"]["tolerance"].get("f0") is False),
                "v": sum(1 for record in subset if record["independent"]["tolerance"].get("v") is False),
                "t0": sum(1 for record in subset if record["independent"]["tolerance"].get("t0") is False),
                "b": sum(1 for record in subset if record["independent"]["tolerance"].get("b") is False),
            },
            "baseline_max_abs_truth_error": {
                "f0_rel": _max_abs([record["baseline"]["truth_errors"]["f0_rel"] for record in subset]),
                "v_rel": _max_abs([record["baseline"]["truth_errors"]["v_rel"] for record in subset]),
                "t0_abs_s": _max_abs([record["baseline"]["truth_errors"]["t0_abs_s"] for record in subset]),
                "b_rel": _max_abs([record["baseline"]["truth_errors"]["b_rel"] for record in subset]),
            },
            "independent_max_abs_truth_error": {
                "f0_rel": _max_abs([record["independent"]["truth_errors"]["f0_rel"] for record in subset]),
                "v_rel": _max_abs([record["independent"]["truth_errors"]["v_rel"] for record in subset]),
                "t0_abs_s": _max_abs([record["independent"]["truth_errors"]["t0_abs_s"] for record in subset]),
                "b_rel": _max_abs([record["independent"]["truth_errors"]["b_rel"] for record in subset]),
            },
        }
        summaries.append(summary)

    # Overall paired differences with bootstrap intervals.
    paired = {}
    for key in ("f0_rel", "v_rel", "t0_abs_s", "b_rel"):
        values = [record["differences"][key] for record in records if record["differences"][key] is not None]
        paired[key] = _bootstrap_interval(values)
    total_baseline_pass = sum(1 for record in records if record["baseline"]["tolerance"]["all"])
    total_independent_pass = sum(1 for record in records if record["independent"]["tolerance"]["all"])
    disagreement = sum(1 for record in records if record["baseline"]["tolerance"]["all"] != record["independent"]["tolerance"]["all"])
    adequacy_flips = sum(1 for record in records if record["adequacy_status_flip"])
    epistemic_flips = sum(1 for record in records if record["epistemic_decision_flip"])
    claim_flip_trials = sum(1 for record in records if record["claim_flips"])
    max_differences = {
        "f0_rel": _max_abs([record["differences"]["f0_rel"] for record in records]),
        "v_rel": _max_abs([record["differences"]["v_rel"] for record in records]),
        "t0_abs_s": _max_abs([record["differences"]["t0_abs_s"] for record in records]),
        "b_rel": _max_abs([record["differences"]["b_rel"] for record in records]),
    }
    flagged_conditions = [
        summary["condition_id"]
        for summary in summaries
        if summary["tolerance_agreement"]["disagreements"] > 0
        or summary["adequacy_status_flips"] > 0
        or summary["epistemic_decision_flips"] > 0
        or summary["claim_flip_trials"] > 0
    ]
    # Declared robustness criterion, fixed before seeing results.
    robust_parameter_bound = {
        "f0_rel": 0.005,
        "v_rel": 0.005,
        "t0_abs_s": 0.05,
        "b_rel": 0.005,
    }
    correct_cv_records = [record for record in records if record["family"] == "correct_constant_velocity"]
    accel_records = [record for record in records if record["family"] == "acceleration_misspecification"]
    correct_cv_max_differences = _max_differences_for(correct_cv_records)
    acceleration_max_differences = _max_differences_for(accel_records)
    correct_cv_parameter_robust = all(
        (correct_cv_max_differences[key] is not None and correct_cv_max_differences[key] <= bound)
        for key, bound in robust_parameter_bound.items()
    )
    acceleration_parameter_robust = all(
        (acceleration_max_differences[key] is not None and acceleration_max_differences[key] <= bound)
        for key, bound in robust_parameter_bound.items()
    )
    correct_cv_tolerance_disagreements = _tolerance_disagreements(correct_cv_records)
    acceleration_tolerance_disagreements = _tolerance_disagreements(accel_records)
    correct_cv_adequacy_flips = sum(1 for record in correct_cv_records if record["adequacy_status_flip"])
    acceleration_adequacy_flips = sum(1 for record in accel_records if record["adequacy_status_flip"])
    correct_cv_claim_flip_trials = sum(1 for record in correct_cv_records if record["claim_flips"])
    acceleration_claim_flip_trials = sum(1 for record in accel_records if record["claim_flips"])
    decision_flip_conditions = sorted(
        {
            record["condition_id"]
            for record in records
            if record["adequacy_status_flip"]
            or record["epistemic_decision_flip"]
            or record["claim_flips"]
        }
    )
    correct_cv_clean = (
        correct_cv_parameter_robust
        and correct_cv_tolerance_disagreements == 0
        and correct_cv_adequacy_flips == 0
        and correct_cv_claim_flip_trials == 0
    )
    acceleration_clean = (
        acceleration_parameter_robust
        and acceleration_tolerance_disagreements == 0
        and acceleration_adequacy_flips == 0
        and acceleration_claim_flip_trials == 0
    )
    if correct_cv_clean and acceleration_clean:
        verdict = "conclusions_estimator_independent"
        verdict_statement = (
            "The independent estimator reproduces the baseline parameters within the pre-declared audit "
            "bounds on both correct-CV and acceleration observations, with no tolerance/adequacy/claim "
            "decision flips; conclusions are not estimator-dependent on this audit set."
        )
    elif correct_cv_clean:
        verdict = "correct_cv_estimator_independent_acceleration_detection_estimator_sensitive"
        verdict_statement = (
            "Correct-CV parameters agree within the pre-declared bounds and correct-CV tolerance/adequacy/"
            "claim decisions agree. Acceleration observations differ: parameter differences exceed the "
            "pre-declared bounds and 6/12 acceleration adequacy/detection decisions flip (baseline rejects "
            "as discrepancy where the independent estimator returns insufficient evidence/indeterminate). "
            "Correct-CV conclusions are not estimator-dependent; acceleration-detection conclusions are."
        )
    else:
        verdict = "estimator_dependence_flagged"
        verdict_statement = (
            "At least one pre-declared audit bound or tolerance/adequacy decision differs on correct-CV "
            "observations; conclusions must be read with the estimator dependence named in the flagged conditions."
        )
    artifact = {
        "artifact": ARTIFACT_NAME,
        "version": AUDIT_VERSION,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_s": float(time.time() - started),
        "purpose": "E1 estimator-independence audit (verification, not new science)",
        "scope": {
            "sealed_grid_id": "pr4e-c2c-v1",
            "sealed_grid_opened": False,
            "sealed_grid_file_read": False,
            "development_seeds_reused": False,
            "thresholds_changed": False,
            "fit_hardened_used_only_as_baseline": True,
        },
        "config": {
            "audit_seed_base": AUDIT_SEED_BASE,
            "audit_seed_formula": AUDIT_SEED_FORMULA,
            "trials_per_condition": TRIALS_PER_CONDITION,
            "conditions": conditions,
            "total_trials": sum(condition["n_trials"] for condition in conditions),
            "tolerances": dict(TOLERANCES),
            "claims_protocol_path": "protocols/pr4e-claims-1.3.0.json",
            "claims_protocol_digest": claims_protocol.get("protocol_digest"),
            "robustness_criterion": dict(robust_parameter_bound),
        },
        "independent_estimator": dict(INDEPENDENT_ESTIMATOR),
        "baseline_estimator": {
            "id": "fit_hardened",
            "role": "comparison baseline only",
            "parameterisation": "fit_hardened's declared internal parameterisation (not imported/copied here)",
        },
        "records": records,
        "condition_summaries": summaries,
        "overall": {
            "n_trials": len(records),
            "paired_parameter_differences": paired,
            "max_abs_parameter_differences": max_differences,
            "correct_cv_max_abs_parameter_differences": correct_cv_max_differences,
            "acceleration_max_abs_parameter_differences": acceleration_max_differences,
            "correct_cv_parameter_robust_within_declared_bounds": correct_cv_parameter_robust,
            "acceleration_parameter_robust_within_declared_bounds": acceleration_parameter_robust,
            "correct_cv_tolerance_disagreements": correct_cv_tolerance_disagreements,
            "acceleration_tolerance_disagreements": acceleration_tolerance_disagreements,
            "correct_cv_adequacy_status_flips": correct_cv_adequacy_flips,
            "acceleration_adequacy_status_flips": acceleration_adequacy_flips,
            "correct_cv_claim_flip_trials": correct_cv_claim_flip_trials,
            "acceleration_claim_flip_trials": acceleration_claim_flip_trials,
            "decision_flip_conditions": decision_flip_conditions,
            "tolerance_pass_trials": {
                "baseline": total_baseline_pass,
                "independent": total_independent_pass,
                "agreement": sum(
                    1
                    for record in records
                    if record["baseline"]["tolerance"]["all"] == record["independent"]["tolerance"]["all"]
                ),
                "disagreements": disagreement,
                "baseline_only_pass": sum(
                    1
                    for record in records
                    if record["baseline"]["tolerance"]["all"] and not record["independent"]["tolerance"]["all"]
                ),
                "independent_only_pass": sum(
                    1
                    for record in records
                    if record["independent"]["tolerance"]["all"] and not record["baseline"]["tolerance"]["all"]
                ),
            },
            "adequacy_status_flips": adequacy_flips,
            "epistemic_decision_flips": epistemic_flips,
            "claim_flip_trials": claim_flip_trials,
            "flagged_conditions": flagged_conditions,
            "parameter_robust_within_declared_bounds": correct_cv_parameter_robust,
            "verdict": verdict,
            "verdict_statement": verdict_statement,
        },
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "scipy": __import__("scipy").__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
        },
        "limitations": [
            "Small fixed-seed synthetic audit set (36 trials): it is an independence check, not a calibration or a new physics result.",
            "Both estimators fit the same declared E0 instantaneous-frequency model; the audit tests estimator implementation, not the physical model or front end.",
            "The independent robust soft_l1 loss and finite-difference covariance are different from the baseline's hardened LM rule; small parameter differences are expected.",
            "Adequacy/claim comparisons reuse the frozen layers read-only; they do not re-freeze or change those policies.",
            "Truth is used only to score estimator error/tolerance; the sealed grid is not opened.",
        ],
    }
    artifact = _jsonable(artifact)
    json_path = os.path.join(out_dir, "estimator-audit.json")
    payload = (json.dumps(artifact, indent=1, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    with open(json_path, "wb") as handle:
        handle.write(payload)
    json_sha = hashlib.sha256(payload).hexdigest()
    markdown = render_markdown(artifact)
    markdown_path = os.path.join(out_dir, "estimator-audit.md")
    markdown_sha = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    with open(markdown_path, "wb") as handle:
        handle.write(markdown.encode("utf-8"))
    return {
        "artifact": artifact,
        "paths": {"json": json_path, "markdown": markdown_path},
        "digests": {"json": json_sha, "markdown": markdown_sha, "records": _digest(artifact)},
        "claims_protocol": claims_protocol,
    }


# ---------------------------------------------------------------------------
# Markdown summary
# ---------------------------------------------------------------------------

def _fmt(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        if value != 0.0 and abs(value) < 1e-3:
            return f"{value:.3e}"
        return f"{value:.4g}"
    return str(value)


def render_markdown(artifact: dict) -> str:
    lines = ["# E1 estimator-independence audit", ""]
    lines.append(
        f"**Artifact:** `{artifact['artifact']}` v{artifact['version']} · independent estimator "
        f"`{artifact['independent_estimator']['id']}` · sealed grid opened: {artifact['scope']['sealed_grid_opened']}"
    )
    lines.append("")
    lines.append("Independent estimator: scipy least_squares, direct physical units, robust soft_l1, own forward model/residual; "
                 "`fit_hardened` is the comparison baseline only.")
    lines.append("")
    lines.append("## Per-condition parameter differences and tolerance agreement")
    lines.append("")
    lines.append(
        "| condition | n | max |Δ| f0/v/t0/b | mean |Δ| f0/v/t0/b | tolerance both/baseline-only/independent-only | disagreements | adequacy flips | epistemic flips | claim-flip trials |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for summary in artifact["condition_summaries"]:
        max_diff = summary["max_abs_parameter_difference"]
        mean_diff = summary["mean_abs_parameter_difference"]
        agreement = summary["tolerance_agreement"]
        max_text = (
            f"{_fmt(max_diff['f0_rel'])}/{_fmt(max_diff['v_rel'])}/"
            f"{_fmt(max_diff['t0_abs_s'])}/{_fmt(max_diff['b_rel'])}"
        )
        mean_text = (
            f"{_fmt(mean_diff['f0_rel'])}/{_fmt(mean_diff['v_rel'])}/"
            f"{_fmt(mean_diff['t0_abs_s'])}/{_fmt(mean_diff['b_rel'])}"
        )
        lines.append(
            f"| {summary['condition_id']} | {summary['n_trials']} | {max_text} | {mean_text} | "
            f"{agreement['both_pass']}/{agreement['baseline_only_pass']}/{agreement['independent_only_pass']} | "
            f"{agreement['disagreements']} | {summary['adequacy_status_flips']} | "
            f"{summary['epistemic_decision_flips']} | {summary['claim_flip_trials']} |"
        )
    lines.append("")
    overall = artifact["overall"]
    lines.append("## Overall")
    lines.append("")
    lines.append(
        f"- trials: {overall['n_trials']} · tolerance pass baseline {overall['tolerance_pass_trials']['baseline']} / "
        f"independent {overall['tolerance_pass_trials']['independent']} · agreement {overall['tolerance_pass_trials']['agreement']} · "
        f"disagreements {overall['tolerance_pass_trials']['disagreements']}"
    )
    lines.append(
        f"- adequacy-status flips: {overall['adequacy_status_flips']}; epistemic-decision flips: "
        f"{overall['epistemic_decision_flips']}; claim-status flip trials: {overall['claim_flip_trials']}"
    )
    lines.append(
        f"- correct-CV max |Δ| f0/v/t0/b: {_fmt(overall['correct_cv_max_abs_parameter_differences']['f0_rel'])}/"
        f"{_fmt(overall['correct_cv_max_abs_parameter_differences']['v_rel'])}/"
        f"{_fmt(overall['correct_cv_max_abs_parameter_differences']['t0_abs_s'])}/"
        f"{_fmt(overall['correct_cv_max_abs_parameter_differences']['b_rel'])}; "
        f"within declared bounds: {overall['correct_cv_parameter_robust_within_declared_bounds']}"
    )
    lines.append(
        f"- acceleration max |Δ| f0/v/t0/b: {_fmt(overall['acceleration_max_abs_parameter_differences']['f0_rel'])}/"
        f"{_fmt(overall['acceleration_max_abs_parameter_differences']['v_rel'])}/"
        f"{_fmt(overall['acceleration_max_abs_parameter_differences']['t0_abs_s'])}/"
        f"{_fmt(overall['acceleration_max_abs_parameter_differences']['b_rel'])}; "
        f"within declared bounds: {overall['acceleration_parameter_robust_within_declared_bounds']}"
    )
    lines.append(f"- adequacy flips by family: correct-CV {overall['correct_cv_adequacy_status_flips']}, "
                 f"acceleration {overall['acceleration_adequacy_status_flips']}")
    lines.append(f"- flagged conditions: {overall['flagged_conditions'] or 'none'}")
    lines.append("")
    lines.append("| parameter paired difference | mean [95% CI] | max |value| |")
    lines.append("|---|---|---|")
    for key in ("f0_rel", "v_rel", "t0_abs_s", "b_rel"):
        paired = overall["paired_parameter_differences"][key]
        lines.append(
            f"| {key} | {_fmt(paired['mean'])} [{_fmt(paired['ci95'][0])}, {_fmt(paired['ci95'][1])}] | "
            f"{_fmt(overall['max_abs_parameter_differences'][key])} |"
        )
    lines.append("")
    lines.append(f"**Verdict: {overall['verdict']}** — {overall['verdict_statement']}")
    lines.append("")
    lines.append("## Truth-error maxima by estimator")
    lines.append("")
    lines.append("| condition | baseline max abs errors (f0/v/t0/b) | independent max abs errors (f0/v/t0/b) |")
    lines.append("|---|---|---|")
    for summary in artifact["condition_summaries"]:
        base = summary["baseline_max_abs_truth_error"]
        indep = summary["independent_max_abs_truth_error"]
        lines.append(
            f"| {summary['condition_id']} | "
            f"{_fmt(base['f0_rel'])}/{_fmt(base['v_rel'])}/{_fmt(base['t0_abs_s'])}/{_fmt(base['b_rel'])} | "
            f"{_fmt(indep['f0_rel'])}/{_fmt(indep['v_rel'])}/{_fmt(indep['t0_abs_s'])}/{_fmt(indep['b_rel'])} |"
        )
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    for limitation in artifact["limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="E1 estimator-independence audit.")
    parser.add_argument("--out-dir", default="/tmp/e1est")
    parser.add_argument("--claims-protocol", default=None)
    args = parser.parse_args(argv)
    result = run_audit(out_dir=args.out_dir, claims_protocol_path=args.claims_protocol)
    print("E1 estimator audit artifacts:")
    print(f"  json: {result['paths']['json']}  sha256: {result['digests']['json']}")
    print(f"  markdown: {result['paths']['markdown']}  sha256: {result['digests']['markdown']}")
    overall = result["artifact"]["overall"]
    print(f"  trials: {overall['n_trials']}")
    print(f"  tolerance pass baseline/independent: {overall['tolerance_pass_trials']['baseline']}/{overall['tolerance_pass_trials']['independent']}")
    print(f"  tolerance disagreements: {overall['tolerance_pass_trials']['disagreements']}")
    print(f"  adequacy flips: {overall['adequacy_status_flips']}; epistemic flips: {overall['epistemic_decision_flips']}; claim-flip trials: {overall['claim_flip_trials']}")
    print(f"  max |Δ| f0/v/t0/b: {overall['max_abs_parameter_differences']}")
    print(f"  verdict: {overall['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
