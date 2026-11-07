"""Diagnose one frozen E0 trial: reproduce it exactly and record why the fit
stopped where it did.

Why this exists
---------------
The cross-platform E0 report found that trial 57 of ``snr_+5dB`` has the same
parameters to ~1e-9 on every platform, but its convergence decision flips:
``grad_norm`` is 2.97e-12 on macOS arm64 and 1.056e-6 on Linux x86_64 against a
threshold of 1e-6.  Before any convergence rule is changed, the mechanism has
to be measured rather than guessed.  This tool reproduces the exact E0 trial
(same generator, same front end, same seed formula), runs the *frozen* E0 fit
(:func:`phaino_acoustics.fit.fit_doppler`), and records the full termination
evidence: objective, raw gradient, scale-normalized dimensionless gradient,
iteration history, evaluation counts, termination reason, and the platform.

It also evaluates arbitrary parameter vectors (``--params-set name:f0,v,t0,b``)
with the same objective/gradient machinery, so a platform can check whether
*another* platform's final parameters are a stationary point in *its* arithmetic.

What this tool is not
---------------------
It does not change, tune, or replace the frozen E0 estimator.  ``fit.py`` is
untouched.  The instrumented loop here is a faithful copy of
``fit._lm_refine`` plus bookkeeping; a test proves it returns bit-identical
parameters to :func:`fit_doppler` on this platform.  The hardened convergence
rule lives in :mod:`phaino_acoustics.fit_hardened` and is a separate version.

Usage::

    python -m phaino_acoustics.diagnose --condition snr_+5dB --trial 57 \
        --output /tmp/diag.json \
        --params-set macos_arm64:500.07775811833216,249.98033167340995,19.99751522499437,2999.5039534028137 \
        --params-set linux_x64:500.07775815723664,249.9803316750835,19.99751522300237,2999.5039536940826

No file is written except ``--output`` (the parent directory must exist).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from dataclasses import asdict
from typing import Optional

import numpy as np

from .experiment import BASE, FRAME_LEN, HOP, F_MIN, F_MAX, SEED_BASE, build_conditions
from .features import estimate_if_track
from .fit import (
    FitResult,
    _candidate_starts,
    _clip_full,
    _diverse_top,
    _profile_sse,
    _residual_and_jacobian,
    _sse_full,
    fit_doppler,
)
from .synthetic import Scenario, generate

DIAGNOSTIC_VERSION = "1.0.0"

PARAM_ORDER = ("f0", "v", "t0", "b")

# Declared physical scales (same declataration as the hardened rule).  They are
# the order of magnitude of the E0 base geometry, not fitted quantities.
PARAMETER_SCALES = {"f0": 500.0, "v": 250.0, "t0": 20.0, "b": 3000.0}
SCALE_VECTOR = np.array([PARAMETER_SCALES[name] for name in PARAM_ORDER], dtype=np.float64)

# Central finite-difference step for the independent gradient check, as a
# fraction of each declared scale.
FD_RELATIVE_STEP = 1.0e-6

# E0's frozen per-start LM iteration budget (fit.fit_doppler default).
E0_MAX_ITER = 200


# ---------------------------------------------------------------------------
# Exact E0 trial reproduction
# ---------------------------------------------------------------------------

def condition_index(condition: str) -> int:
    """Position of ``condition`` in the frozen E0 sweep (fixes the seed)."""
    names = [cond.name for cond in build_conditions()]
    try:
        return names.index(condition)
    except ValueError:
        raise ValueError(
            f"unknown condition {condition!r}; known: {', '.join(names)}"
        ) from None


def e0_seed(condition: str, trial: int) -> int:
    """The pre-registered E0 seed formula: seed_base + 1000*index + trial."""
    if isinstance(trial, bool) or not isinstance(trial, int) or trial < 0:
        raise ValueError(f"trial must be a non-negative integer, got {trial!r}")
    return SEED_BASE + 1000 * condition_index(condition) + trial


def e0_scenario(condition: str, trial: int) -> tuple[Scenario, int]:
    """The exact E0 ``Scenario`` for ``(condition, trial)`` plus its seed."""
    conditions = build_conditions()
    index = condition_index(condition)
    seed = e0_seed(condition, trial)
    scenario = Scenario(**{**asdict(conditions[index].scenario), "seed": seed})
    return scenario, seed


def e0_observation(condition: str, trial: int):
    """Generate the observation and the model-free IF track exactly as E0 does."""
    scenario, seed = e0_scenario(condition, trial)
    obs = generate(scenario)
    track = estimate_if_track(
        obs.signal,
        scenario.fs,
        frame_len=FRAME_LEN,
        hop=HOP,
        f_min=F_MIN,
        f_max=F_MAX,
        t_start=float(obs.t[0]),
    )
    return scenario, seed, obs, track


# ---------------------------------------------------------------------------
# Instrumented faithful copy of the frozen E0 LM
# ---------------------------------------------------------------------------

def _gradient_quantities(
    t: np.ndarray,
    f: np.ndarray,
    params: np.ndarray,
    c: float,
    scales: np.ndarray = SCALE_VECTOR,
) -> dict:
    """Objective and the three gradient normalizations at ``params``.

    Definitions (declared, used consistently by the diagnostic and the
    hardened rule):

    * ``raw_gradient = J^T r``, where ``r = f - f_hat`` and ``J = d f_hat / d theta``.
      This is ``0.5 * d(SSE)/d(theta)`` and is exactly the Levenberg-Marquardt
      right-hand side ``J^T r``.
    * ``sigma_f^2 = SSE / (n - 4)`` (the fit's residual variance).
    * ``dimensionless_gradient_i = s_i * raw_gradient_i / sigma_f^2`` with
      ``z_i = theta_i / s_i``.  This is ``d(SSE_norm)/dz`` up to a factor of 2;
      the factor is constant and does not affect a stationarity test.
    * ``e0_grad_norm = max_i |raw_gradient_i| / sqrt(SSE * n)`` -- the frozen E0
      statistic (dimensionally inconsistent across parameters; recorded only
      so the E0 decision is reproducible).
    """
    params = np.asarray(params, dtype=np.float64)
    res, jac, predicted = _residual_and_jacobian(t, f, params, c)
    n = int(f.size)
    sse = float(res @ res)
    dof = max(n - 4, 1)
    sigma_f = float(np.sqrt(sse / dof))
    sigma2 = float(sse / dof)
    raw = jac.T @ res
    curvature_diag = np.diag(jac.T @ jac)
    with np.errstate(divide="ignore", invalid="ignore"):
        dimensionless = scales * raw / sigma2 if sigma2 > 0.0 else np.full(4, np.inf)
        e0_grad_norm = float(np.max(np.abs(raw)) / np.sqrt(sse * n)) if sse > 0.0 else float("inf")
        predicted_newton_step = np.where(
            curvature_diag > 0.0, np.abs(raw) / (scales * curvature_diag), np.inf
        )
    return {
        "objective": sse,
        "raw_gradient": raw,
        "dimensionless_gradient": dimensionless,
        "curvature_diag": curvature_diag,
        "predicted_newton_step": predicted_newton_step,
        "e0_grad_norm": e0_grad_norm,
        "sigma_f": sigma_f,
        "rms_hz": float(np.sqrt(sse / n)),
        "predicted": predicted,
        "residual": res,
        "n_points": n,
    }


def _finite_difference_gradient(
    t: np.ndarray,
    f: np.ndarray,
    params: np.ndarray,
    c: float,
    scales: np.ndarray = SCALE_VECTOR,
    relative_step: float = FD_RELATIVE_STEP,
) -> tuple[np.ndarray, np.ndarray]:
    """Central-difference estimate of ``raw_gradient = 0.5 d(SSE)/d(theta)``.

    Returns ``(gradient, steps)``; ``steps = relative_step * s`` in physical
    units.  Recorded as an independent arithmetic path for the analytic
    Jacobian; it is *not* used by any fit.
    """
    params = np.asarray(params, dtype=np.float64)
    grad = np.zeros(4, dtype=np.float64)
    steps = relative_step * scales
    for i in range(4):
        plus = params.copy()
        minus = params.copy()
        plus[i] += steps[i]
        minus[i] -= steps[i]
        sse_plus = _sse_full(t, f, plus, c)
        sse_minus = _sse_full(t, f, minus, c)
        # raw_gradient = J^T r = -0.5 * d(SSE)/d(theta)
        grad[i] = (sse_minus - sse_plus) / (4.0 * steps[i])
    return grad, steps


def _lm_refine_e0_instrumented(
    t: np.ndarray,
    f: np.ndarray,
    c: float,
    x0: np.ndarray,
    t_lo: float,
    t_hi: float,
    max_iter: int = E0_MAX_ITER,
) -> dict:
    """Faithful, instrumented copy of :func:`phaino_acoustics.fit._lm_refine`.

    The arithmetic is copy-pasted from the frozen loop (same order of
    operations, same damping schedule, same clipping, same stopping rule), so
    the returned point must be bit-identical to the frozen fitter.  The extra
    outputs are bookkeeping only: counters, per-iteration history, termination
    reason and gradients.
    """
    span = max(float(t[-1] - t[0]), 1e-12)
    x = _clip_full(np.asarray(x0, dtype=np.float64), t_lo, t_hi, c)
    res, jac, _pred = _residual_and_jacobian(t, f, x, c)
    sse = float(res @ res)
    nfev = 1
    njev = 1
    lam = 1.0e-3
    converged = False
    converged_by: Optional[str] = None
    it = 0
    rel_step = float("inf")
    history: list[dict] = []
    broke_early = False
    termination_reason = "iteration_budget"
    for it in range(1, max_iter + 1):
        if not np.isfinite(sse):
            termination_reason = "numerical_failure"
            broke_early = True
            break
        a = jac.T @ jac
        g = jac.T @ res
        if not (np.all(np.isfinite(a)) and np.all(np.isfinite(g))):
            termination_reason = "numerical_failure"
            broke_early = True
            break
        diag = np.diag(a).copy()
        diag[diag <= 0.0] = 1.0
        improved = False
        for _attempt in range(12):
            try:
                step = np.linalg.solve(a + lam * np.diag(diag), g)
            except np.linalg.LinAlgError:
                lam *= 10.0
                continue
            if not np.all(np.isfinite(step)):
                lam *= 10.0
                continue
            x_new = _clip_full(x + step, t_lo, t_hi, c)
            res_new, jac_new, _ = _residual_and_jacobian(t, f, x_new, c)
            nfev += 1
            njev += 1
            sse_new = float(res_new @ res_new)
            if np.isfinite(sse_new) and sse_new < sse:
                dx = x_new - x
                rel = (sse - sse_new) / max(sse, 1e-300)
                rel_step = float(
                    np.max(np.abs(dx) / np.maximum(np.abs(x), np.array([1e-12, 1e-12, span, 1e-12])))
                )
                lam_used = float(lam)
                x, res, jac, sse = x_new, res_new, jac_new, sse_new
                lam = max(lam * 0.3, 1e-12)
                improved = True
                grad_new = jac.T @ res
                history.append(
                    {
                        "iteration": int(it),
                        "objective": float(sse),
                        "relative_objective_change": float(rel),
                        "e0_rel_step": float(rel_step),
                        "scale_normalized_step": float(np.max(np.abs(dx) / SCALE_VECTOR)),
                        "lambda": lam_used,
                        "scale_normalized_gradient_inf_norm": float(
                            np.max(np.abs(SCALE_VECTOR * grad_new / max(sse / max(f.size - 4, 1), 1e-300)))
                        ),
                    }
                )
                if rel_step < 1e-10 or rel < 1e-14:
                    converged = True
                    converged_by = "criteria_in_loop"
                break
            lam *= 10.0
        if not improved:
            termination_reason = "stalled_no_improving_step"
            broke_early = True
            break
        if converged:
            termination_reason = "criteria_in_loop"
            broke_early = True
            break

    # Post-loop stationarity override, exactly as the frozen loop.
    g = jac.T @ res
    gnorm = (
        float(np.max(np.abs(g))) / (np.sqrt(sse * f.size) + 1e-300)
        if np.isfinite(sse)
        else float("inf")
    )
    if gnorm < 1e-6:
        converged = True
        if converged_by is None:
            converged_by = "post_hoc_gradient"
            if termination_reason == "iteration_budget" and not broke_early:
                termination_reason = "post_hoc_gradient"

    quantities = _gradient_quantities(t, f, x, c)
    return {
        "x": x,
        "sse": sse,
        "converged": bool(converged),
        "converged_by": converged_by,
        "iterations": int(it),
        "max_iter": int(max_iter),
        "iteration_budget_hit": bool(not broke_early and it >= max_iter),
        "termination_reason": termination_reason,
        "nfev": int(nfev),
        "njev": int(njev),
        "rel_step": float(rel_step),
        "grad_norm": gnorm,
        "history": history,
        "quantities": quantities,
    }


def fit_e0_instrumented(
    t: np.ndarray,
    f: np.ndarray,
    c: float,
    n_starts: int = 5,
    max_iter: int = E0_MAX_ITER,
) -> dict:
    """Instrumented copy of :func:`fit.fit_doppler`'s orchestration.

    Same start grid, same ranking, same five refined starts, same
    lowest-SSE-wins selection.  Returns the winning start's instrumented
    result plus the frozen :class:`FitResult` for comparison.
    """
    t = np.asarray(t, dtype=np.float64)
    f = np.asarray(f, dtype=np.float64)
    if t.size != f.size or t.size < 5:
        raise ValueError("need matching t/f arrays with >= 5 samples")
    span = float(t[-1] - t[0])
    t_lo, t_hi = float(t[0] - 10.0 * span), float(t[-1] + 10.0 * span)

    starts = _candidate_starts(t, f, c)
    scored: list[tuple[float, float, float, float]] = []
    for (v, t0, b) in starts:
        sse, _f0, _res, _jac = _profile_sse(t, f, v, t0, b, c)
        if np.isfinite(sse):
            scored.append((sse, v, t0, b))
    if not scored:
        raise RuntimeError("no finite starting point for the Doppler fit")
    chosen = _diverse_top(scored, n_starts, span)

    per_start: list[dict] = []
    for index, (_sse, v, t0, b) in enumerate(chosen):
        _sse0, f0_0, _r, _j = _profile_sse(t, f, v, t0, b, c)
        start = np.array([f0_0, v, t0, b], dtype=np.float64)
        refined = _lm_refine_e0_instrumented(t, f, c, start, t_lo, t_hi, max_iter)
        refined["start_index"] = index
        per_start.append(refined)

    best_index = int(np.argmin([p["sse"] for p in per_start]))
    best = per_start[best_index]
    frozen: FitResult = fit_doppler(t, f, c=c, n_starts=n_starts, max_iter=max_iter)
    return {
        "best": best,
        "best_start_index": best_index,
        "n_starts": len(chosen),
        "n_starts_ranked": len(scored),
        "per_start": per_start,
        "frozen": frozen,
    }


# ---------------------------------------------------------------------------
# Parameter-set evaluation
# ---------------------------------------------------------------------------

def parse_params_set(spec: str) -> tuple[str, np.ndarray]:
    """Parse ``name:f0,v,t0,b`` into ``(name, theta)``."""
    if ":" not in spec:
        raise ValueError(f"--params-set must look like name:f0,v,t0,b, got {spec!r}")
    name, raw = spec.split(":", 1)
    name = name.strip()
    if not name:
        raise ValueError(f"--params-set name is empty in {spec!r}")
    parts = [piece.strip() for piece in raw.split(",")]
    if len(parts) != 4:
        raise ValueError(f"--params-set {name!r} needs exactly 4 values (f0,v,t0,b), got {len(parts)}")
    try:
        theta = np.array([float(piece) for piece in parts], dtype=np.float64)
    except ValueError:
        raise ValueError(f"--params-set {name!r} has a non-numeric value in {spec!r}") from None
    if not np.all(np.isfinite(theta)):
        raise ValueError(f"--params-set {name!r} has a non-finite value in {spec!r}")
    return name, theta


def evaluate_params(
    t: np.ndarray,
    f: np.ndarray,
    c: float,
    params: np.ndarray,
) -> dict:
    """Objective, raw gradient, scale-normalized gradient and FD check at ``params``."""
    params = np.asarray(params, dtype=np.float64)
    quantities = _gradient_quantities(t, f, params, c)
    fd_gradient, fd_steps = _finite_difference_gradient(t, f, params, c)
    return {
        "params": {name: float(params[i]) for i, name in enumerate(PARAM_ORDER)},
        "objective": float(quantities["objective"]),
        "rms_hz": float(quantities["rms_hz"]),
        "sigma_f_hz": float(quantities["sigma_f"]),
        "n_points": int(quantities["n_points"]),
        "raw_gradient": {
            name: float(quantities["raw_gradient"][i]) for i, name in enumerate(PARAM_ORDER)
        },
        "raw_gradient_inf_norm": float(np.max(np.abs(quantities["raw_gradient"]))),
        "scale_normalized_gradient": {
            name: float(quantities["dimensionless_gradient"][i])
            for i, name in enumerate(PARAM_ORDER)
        },
        "scale_normalized_gradient_inf_norm": float(
            np.max(np.abs(quantities["dimensionless_gradient"]))
        ),
        "e0_grad_norm": float(quantities["e0_grad_norm"]),
        "curvature_normalized_gradient": {
            name: float(quantities["predicted_newton_step"][i])
            for i, name in enumerate(PARAM_ORDER)
        },
        "curvature_normalized_gradient_inf_norm": float(
            np.max(np.abs(quantities["predicted_newton_step"]))
        ),
        "finite_difference": {
            "relative_step": FD_RELATIVE_STEP,
            "step": {name: float(fd_steps[i]) for i, name in enumerate(PARAM_ORDER)},
            "raw_gradient": {name: float(fd_gradient[i]) for i, name in enumerate(PARAM_ORDER)},
            "raw_gradient_inf_norm": float(np.max(np.abs(fd_gradient))),
        },
    }


# ---------------------------------------------------------------------------
# Environment record
# ---------------------------------------------------------------------------

def environment_record() -> dict:
    """Platform/arithmetic facts that can change a floating-point decision path."""
    float_info = {
        "epsilon": float(np.finfo(np.float64).eps),
        "max": float(np.finfo(np.float64).max),
        "tiny": float(np.finfo(np.float64).tiny),
        "max_exponent": int(np.finfo(np.float64).maxexp),
        "encoding": str(np.dtype(np.float64)),
    }
    try:
        blas = np.__config__.CONFIG["Build Dependencies"]["blas"]
        blas_record = {
            "name": blas.get("name"),
            "version": blas.get("version"),
            "found": blas.get("found"),
        }
    except Exception:  # pragma: no cover - depends on the numpy build
        blas_record = None
    thread_vars = (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    )
    return {
        "python_version": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
        "python_full_version": sys.version,
        "numpy_version": np.__version__,
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "float64": float_info,
        "numpy_errstate": {key: str(value) for key, value in np.geterr().items()},
        "numpy_blas": blas_record,
        "thread_env": {name: os.environ[name] for name in thread_vars if name in os.environ},
        "timezone": time.strftime("%Z"),
    }


# ---------------------------------------------------------------------------
# Diagnostic document
# ---------------------------------------------------------------------------

def build_diagnostic(
    condition: str,
    trial: int,
    params_sets: Optional[list[tuple[str, np.ndarray]]] = None,
    history_length: int = 5,
) -> dict:
    """Build the complete diagnostic JSON document (pure: no file writes)."""
    if history_length < 1:
        raise ValueError("history_length must be >= 1")
    scenario, seed, obs, track = e0_observation(condition, trial)
    instrumented = fit_e0_instrumented(track.t, track.f, scenario.c)
    best = instrumented["best"]
    frozen: FitResult = instrumented["frozen"]

    final = _gradient_quantities(track.t, track.f, best["x"], scenario.c)
    history = best["history"][-history_length:]
    warnings: list[str] = []

    agreement = {
        "params_bit_identical": bool(
            np.array_equal(best["x"], np.array([frozen.f0, frozen.v, frozen.t0, frozen.b]))
        ),
        "objective_bit_identical": bool(best["sse"] == frozen.sse),
        "iterations_equal": bool(best["iterations"] == frozen.iterations),
        "converged_equal": bool(best["converged"] == frozen.converged),
        "grad_norm_bit_identical": bool(best["grad_norm"] == frozen.grad_norm),
    }
    if not all(agreement.values()):
        warnings.append(
            "instrumented replica disagrees with frozen fit_doppler on this platform: "
            + ", ".join(key for key, ok in agreement.items() if not ok)
        )

    params_set_records: dict[str, dict] = {}
    for name, theta in params_sets or []:
        if name in params_set_records:
            raise ValueError(f"duplicate --params-set name {name!r}")
        params_set_records[name] = evaluate_params(track.t, track.f, scenario.c, theta)

    return {
        "diagnostic_version": DIAGNOSTIC_VERSION,
        "tool": "phaino_acoustics.diagnose",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "experiment": "e0-synthetic-doppler",
        "condition": condition,
        "condition_index": condition_index(condition),
        "trial": int(trial),
        "seed": int(seed),
        "scenario": {key: value for key, value in asdict(scenario).items()},
        "front_end": {
            "method": "Hann STFT peak + log-magnitude parabolic interpolation",
            "frame_len": FRAME_LEN,
            "hop": HOP,
            "f_min_hz": F_MIN,
            "f_max_hz": F_MAX,
            "t_start_s": float(obs.t[0]),
        },
        "definitions": {
            "objective": "SSE = sum_k (f_k - f_hat(t_k; theta))^2, theta = (f0, v, t0, b)",
            "raw_gradient": "raw_gradient = J^T r = 0.5 * d(SSE)/d(theta); LM right-hand side",
            "sigma_f": "sigma_f^2 = SSE / (n_points - 4)",
            "scale_normalized_gradient": (
                "dimensionless_i = s_i * raw_gradient_i / sigma_f^2 with z_i = theta_i / s_i"
            ),
            "e0_grad_norm": "max_i |raw_gradient_i| / sqrt(SSE * n_points) (frozen E0 statistic)",
            "curvature_normalized_gradient": (
                "max_i |raw_gradient_i| / (s_i * (J^T J)_ii): the dimensionless gradient "
                "measured in the local Gauss-Newton metric (maximum predicted dimensionless "
                "parameter step).  Not part of the frozen rule; reported because the frozen "
                "gradient is curvature-amplified.  The authoritative hardened-rule "
                "implementation is phaino_acoustics.fit_hardened.criteria_at."
            ),
            "finite_difference": (
                "central difference of SSE with step FD_RELATIVE_STEP * s_i per parameter"
            ),
            "jacobian_method": "analytic (closed-form model derivatives)",
        },
        "parameter_scales": dict(PARAMETER_SCALES),
        "fit": {
            "termination": {
                "converged": bool(best["converged"]),
                "converged_by": best["converged_by"],
                "termination_reason": best["termination_reason"],
                "iterations": int(best["iterations"]),
                "max_iter": int(best["max_iter"]),
                "iteration_budget_hit": bool(best["iteration_budget_hit"]),
                "nfev": int(best["nfev"]),
                "njev": int(best["njev"]),
                "jacobian_method": "analytic",
                "finite_difference_step": None,
                "final_rel_step": float(best["rel_step"]),
            },
            "final_params": {name: float(best["x"][i]) for i, name in enumerate(PARAM_ORDER)},
            "objective": float(best["sse"]),
            "rms_hz": float(final["rms_hz"]),
            "sigma_f_hz": float(final["sigma_f"]),
            "n_points": int(final["n_points"]),
            "raw_gradient": {
                name: float(final["raw_gradient"][i]) for i, name in enumerate(PARAM_ORDER)
            },
            "raw_gradient_inf_norm": float(np.max(np.abs(final["raw_gradient"]))),
            "scale_normalized_gradient": {
                name: float(final["dimensionless_gradient"][i])
                for i, name in enumerate(PARAM_ORDER)
            },
            "scale_normalized_gradient_inf_norm": float(
                np.max(np.abs(final["dimensionless_gradient"]))
            ),
            "e0_grad_norm": float(final["e0_grad_norm"]),
            "curvature_normalized_gradient": {
                name: float(final["predicted_newton_step"][i])
                for i, name in enumerate(PARAM_ORDER)
            },
            "curvature_normalized_gradient_inf_norm": float(
                np.max(np.abs(final["predicted_newton_step"]))
            ),
            "last_iterations": history,
            "n_starts": int(instrumented["n_starts"]),
            "n_starts_ranked": int(instrumented["n_starts_ranked"]),
            "best_start_index": int(instrumented["best_start_index"]),
            "per_start_objective": [
                {
                    "start_index": int(start["start_index"]),
                    "objective": float(start["sse"]),
                    "converged": bool(start["converged"]),
                    "termination_reason": start["termination_reason"],
                    "iterations": int(start["iterations"]),
                }
                for start in instrumented["per_start"]
            ],
            "identifiability": {
                "se": {name: float(value) for name, value in frozen.se.items()},
                "corr": {name: float(value) for name, value in frozen.corr.items()},
                "worst_rel_se": (
                    float(frozen.worst_rel_se) if frozen.worst_rel_se is not None else None
                ),
                "condition_number": (
                    float(frozen.condition_number) if frozen.condition_number is not None else None
                ),
                "worst_direction": {name: float(value) for name, value in frozen.worst_dir.items()},
                "improvement_ratio": float(frozen.improvement_ratio),
            },
            "frozen_fit_agreement": agreement,
        },
        "params_sets": params_set_records,
        "environment": environment_record(),
        "warnings": warnings,
    }


def write_diagnostic(document: dict, output: str) -> None:
    """Write the diagnostic document as strict JSON to exactly ``output``."""
    payload = json.dumps(_jsonable(document), indent=1, sort_keys=True, allow_nan=False)
    with open(output, "w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.write("\n")


def _jsonable(obj):
    """Convert numpy scalars and non-finite floats to strict-JSON values."""
    if isinstance(obj, dict):
        return {key: _jsonable(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(value) for value in obj]
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (float, np.floating)):
        value = float(obj)
        return value if np.isfinite(value) else None
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    return obj


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reproduce and diagnose one frozen E0 trial (no rule changes)."
    )
    parser.add_argument("--condition", required=True, help="E0 condition name, e.g. snr_+5dB")
    parser.add_argument("--trial", type=int, required=True, help="E0 trial index (0-based)")
    parser.add_argument("--output", required=True, help="path of the diagnostic JSON to write")
    parser.add_argument(
        "--params-set",
        action="append",
        default=[],
        metavar="NAME:f0,v,t0,b",
        help="evaluate an additional parameter vector (repeatable)",
    )
    parser.add_argument(
        "--history",
        type=int,
        default=5,
        help="number of final LM iterations to record (default 5)",
    )
    args = parser.parse_args(argv)

    try:
        params_sets = [parse_params_set(spec) for spec in args.params_set]
        document = build_diagnostic(
            args.condition, args.trial, params_sets=params_sets, history_length=args.history
        )
        write_diagnostic(document, args.output)
    except (ValueError, OSError) as exc:
        print(f"diagnose: {exc}", file=sys.stderr)
        return 2

    fit = document["fit"]
    termination = fit["termination"]
    print(
        f"{document['condition']} trial {document['trial']} seed {document['seed']}: "
        f"converged={termination['converged']} ({termination['converged_by']}) "
        f"iterations={termination['iterations']} reason={termination['termination_reason']} "
        f"sse={fit['objective']:.12g}"
    )
    print(
        f"  e0_grad_norm={fit['e0_grad_norm']:.6e}  "
        f"scale_normalized_gradient_inf_norm="
        f"{fit['scale_normalized_gradient_inf_norm']:.6e}  "
        f"raw_gradient_inf_norm={fit['raw_gradient_inf_norm']:.6e}"
    )
    print(f"  wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
