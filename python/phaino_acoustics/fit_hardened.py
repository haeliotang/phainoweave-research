"""Hardened convergence rule v1 for the E0 Doppler fit (a NEW version).

This module does **not** modify the frozen E0 estimator.  ``fit.py`` and
``experiment.py`` keep their exact arithmetic, defaults and artifact; the
hardened rule is a separate implementation whose only behavioural difference is
the stopping rule and the four-part status report.

Why a hardened rule exists
--------------------------
The cross-platform E0 report found one decision in 2500 that flips between
architectures although the parameters agree to ~1e-9: the frozen ``grad_norm``
threshold (1e-6) sits inside the numerical boundary of that trial.  The
diagnostic tool (:mod:`phaino_acoustics.diagnose`) measured the mechanism on
trial 57: the frozen statistic is *not dimensionless* (it mixes 1/Hz and 1/m
thresholds), and the plain elementwise scale-normalized gradient is still
curvature-dependent -- over 8 orders of magnitude across E0 conditions
(5.9e-9 to 1.5e-1 for fits the frozen rule called converged), because a 1e-9
relative parameter difference is amplified by the local curvature.  A single
absolute threshold on that quantity either rejects 41/96 genuinely converged
fits or accepts noise-only fits.

The hardened rule therefore keeps the mandated ingredients -- dimensionless
parameters ``z = theta / s`` with declared physical scales, residuals
normalized by ``sigma_f``, and the three simultaneous criteria (gradient,
relative objective change, normalized parameter step) -- but evaluates the
gradient in the metric induced by the local Gauss-Newton curvature.  That is
the dimensionless gradient's infinity norm measured in the natural units of the
problem: the maximum *predicted* dimensionless parameter step

    newton_i = |g_i| / (s_i * (J^T J)_ii)

where ``g = J^T r`` is the raw gradient (``0.5 d(SSE)/d theta``).  With
``sigma_f^2 = SSE/(n-4)``, the normalized-gradient form
``|s_i g_i / sigma_f^2| / (s_i^2 (J^T J)_ii / sigma_f^2)`` is identical -- the
``sigma_f`` normalization cancels in the ratio and only sets the units.  This
is the gradient criterion used below; the literal elementwise dimensionless
gradient is still reported per trial for transparency
(``elementwise_scale_normalized_gradient_inf_norm``).

Declared rule (v1)
------------------
Parameters (declared physical scales, order of magnitude of the E0 geometry)::

    s = (f0: 500 Hz, v: 250 m/s, t0: 20 s, b: 3000 m),   z = theta / s

Thresholds (fixed before the hardened sweep; calibrated on a 100-trial sample
of frozen E0 fits, not on the cross-platform trial-57 values):

* ``GRADIENT_TOL = 1e-8`` -- dimensionless predicted Newton step.  Measured on
  the calibration sample: converged fits max 5.3e-10 (19x margin); fits that
  hit the iteration budget min 1.6e-6 (160x margin).
* ``OBJECTIVE_TOL = 1e-10`` -- relative objective change of one iteration
  (~450x float64 eps at this SSE scale; below it a change is rounding).
* ``STEP_TOL = 1e-8`` -- dimensionless parameter step ``max_i |dz_i|``
  (1e8 eps; 5e-6 Hz in f0, far below any scientific tolerance).
* ``MIN_CONSECUTIVE = 3`` -- the criteria must hold for the last k >= 3
  iterations consecutively.  Two are explicitly not enough.  At a fixed point
  the last iterations are rejected step attempts (zero accepted change), so
  the deciding criterion there is the gradient; the k = 3 attempts are made at
  three declared damping levels ``(1e-6, 1e-3, 1e0)`` so a single unlucky
  damping choice cannot fake a fixed point.

Termination and the four statuses
---------------------------------
* ``optimization_converged`` -- the numerical criterion was met and stability
  was confirmed (``criteria_confirmed`` in the accepted-step chain, or
  ``fixed_point_verified`` by k rejected verification attempts).
* ``optimization_status`` -- ``"converged" | "indeterminate" | "failed"``.
  Hitting the iteration budget without confirmation, or stalling without a
  stationarity certificate, is ``indeterminate`` -- never forced to
  converged or rejected.  Non-finite arithmetic is ``failed``.
* ``parameter_identifiable`` -- operational gate, not a proof of structural
  identifiability: converged AND ``worst_rel_se <= 1e-2`` AND
  ``condition_number <= 1e4`` AND finite positive parameters.  These values
  follow [ADR 0013](../../docs/decisions/0013-reproducibility-contract-v2.md)
  section 2, which names them as the reference-side rule.
* ``model_adequate`` -- declared residual-adequacy rule: the fitted Doppler
  model explains at least half of the IF-track variance relative to a
  constant-frequency model (``improvement_ratio >= 0.5``, the E0 null rule).
  An absolute Hz bound does not transfer across SNR and geometry; a
  variance-explained fraction is dimensionless.
* ``decision_status`` -- ``accepted | rejected | indeterminate`` with this
  declared precedence (first match wins):

  1. ``optimization_status`` is ``failed`` -> ``indeterminate``
     (``numerical_failure``);
  2. ``optimization_status`` is ``indeterminate`` and the model explains less
     than ``STALL_REJECT_IMPROVEMENT`` of the variance -> ``rejected``
     (``model_inadequate``; the stall itself remains visible in
     ``optimization_status``/``optimization_reason``). This is the
     stall-classification fix for null trials: a clearly inadequate model is
     rejected even when the optimizer stopped without a stationarity
     certificate;
  3. ``optimization_status`` is ``indeterminate`` -> ``indeterminate``
     (``optimization_indeterminate``);
  4. ``model_adequate`` is false -> ``rejected`` (``model_inadequate``);
  5. ``parameter_identifiable`` is false -> ``indeterminate``
     (``parameters_unidentifiable``);
  6. otherwise -> ``accepted``.

  Nothing is accepted on a non-converged optimization. The only rejection on
  a stalled optimization requires the fitted model to be far below the
  adequacy floor (margin 0.5 of the 0.5 threshold).

Limitations (stated, not hidden)
--------------------------------
* The curvature-normalized gradient is a *local* stationarity certificate; it
  cannot detect a bad local minimum.  Model adequacy and multi-start diversity
  are the separate guards.
* At a fixed point the objective-change and parameter-step criteria are zero
  by construction; the k verification attempts at distinct damping levels are
  the evidence that the point is fixed, not a single failed step.
* Because the hardened LM keeps iterating after the frozen rule would have
  stopped, hardened parameters can differ from frozen E0 parameters at the
  1e-10 relative level.  That is expected: it is a new version, not a patch of
  the old artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .fit import (
    C_SOUND_DEFAULT,
    _candidate_starts,
    _clip_full,
    _diverse_top,
    _profile_sse,
    _residual_and_jacobian,
)

HARDENED_VERSION = "1.1.0"
# A stalled optimizer whose fitted model explains less than this fraction of
# the IF-track variance is decisively inadequate: classify it rejected rather
# than leaving a null trial in a platform-dependent indeterminate/converged split.
STALL_REJECT_IMPROVEMENT = 0.25

PARAM_ORDER = ("f0", "v", "t0", "b")

# Declared physical scales (order of magnitude of the E0 base geometry).
PARAMETER_SCALES = {"f0": 500.0, "v": 250.0, "t0": 20.0, "b": 3000.0}
SCALE_VECTOR = np.array([PARAMETER_SCALES[name] for name in PARAM_ORDER], dtype=np.float64)

# Declared thresholds (see module docstring for the calibration evidence).
GRADIENT_TOL = 1.0e-8
OBJECTIVE_TOL = 1.0e-10
STEP_TOL = 1.0e-8
MIN_CONSECUTIVE = 3
MAX_ITER = 200
VERIFICATION_DAMPING = (1.0e-6, 1.0e-3, 1.0e0)

# Declared operational gates.
IDENT_WORST_REL_SE_TOL = 1.0e-2
IDENT_CONDITION_NUMBER_TOL = 1.0e4
MODEL_MIN_IMPROVEMENT = 0.5


# ---------------------------------------------------------------------------
# Criteria
# ---------------------------------------------------------------------------

def criteria_at(
    t: np.ndarray,
    f: np.ndarray,
    params: np.ndarray,
    c: float,
    relative_objective_change: float = 0.0,
    scale_normalized_step: float = 0.0,
    scales: np.ndarray = SCALE_VECTOR,
) -> dict:
    """Evaluate the three hardened convergence criteria at one parameter vector.

    ``relative_objective_change`` and ``scale_normalized_step`` describe the
    step that produced this point; for a fixed-point verification attempt both
    are exactly zero (no step was accepted).
    """
    params = np.asarray(params, dtype=np.float64)
    res, jac, _predicted = _residual_and_jacobian(t, f, params, c)
    n = int(f.size)
    sse = float(res @ res)
    dof = max(n - 4, 1)
    sigma2 = sse / dof
    sigma_f = float(np.sqrt(sigma2)) if sse >= 0.0 else float("inf")
    raw_gradient = jac.T @ res
    curvature_diag = np.diag(jac.T @ jac)

    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        predicted_step = np.where(
            curvature_diag > 0.0,
            np.abs(raw_gradient) / (scales * curvature_diag),
            np.inf,
        )
        elementwise = scales * raw_gradient / sigma2 if sigma2 > 0.0 else np.full(4, np.inf)
        elementwise_inf = float(np.max(np.abs(elementwise)))
    predicted_inf = float(np.max(predicted_step))
    if not np.isfinite(predicted_inf):
        predicted_inf = float("inf")

    passes = (
        predicted_inf <= GRADIENT_TOL
        and relative_objective_change <= OBJECTIVE_TOL
        and scale_normalized_step <= STEP_TOL
    )
    return {
        "objective": sse,
        "sigma_f_hz": sigma_f,
        "n_points": n,
        "raw_gradient": {
            name: float(raw_gradient[i]) for i, name in enumerate(PARAM_ORDER)
        },
        "raw_gradient_inf_norm": float(np.max(np.abs(raw_gradient))),
        "predicted_newton_step": {
            name: float(predicted_step[i]) for i, name in enumerate(PARAM_ORDER)
        },
        "predicted_newton_step_inf_norm": predicted_inf,
        "elementwise_scale_normalized_gradient": {
            name: float(elementwise[i]) for i, name in enumerate(PARAM_ORDER)
        },
        "elementwise_scale_normalized_gradient_inf_norm": elementwise_inf,
        "relative_objective_change": float(relative_objective_change),
        "scale_normalized_step": float(scale_normalized_step),
        "criteria_pass": bool(passes),
        "thresholds": {
            "gradient": GRADIENT_TOL,
            "relative_objective_change": OBJECTIVE_TOL,
            "scale_normalized_step": STEP_TOL,
            "min_consecutive": MIN_CONSECUTIVE,
        },
    }


def _derive_decision(
    optimization_status: str,
    model_adequate: bool,
    parameter_identifiable: bool,
    improvement_ratio: float | None = None,
) -> tuple[str, str]:
    """Declared decision precedence (see module docstring).  Pure function."""
    if optimization_status == "failed":
        return "indeterminate", "numerical_failure"
    if (
        optimization_status == "indeterminate"
        and not model_adequate
        and improvement_ratio is not None
        and improvement_ratio < STALL_REJECT_IMPROVEMENT
    ):
        return "rejected", "model_inadequate"
    if optimization_status == "indeterminate":
        return "indeterminate", "optimization_indeterminate"
    if not model_adequate:
        return "rejected", "model_inadequate"
    if not parameter_identifiable:
        return "indeterminate", "parameters_unidentifiable"
    return "accepted", "converged_adequate_identifiable"


# ---------------------------------------------------------------------------
# Hardened Levenberg-Marquardt
# ---------------------------------------------------------------------------

def lm_refine_hardened(
    t: np.ndarray,
    f: np.ndarray,
    c: float,
    x0: np.ndarray,
    t_lo: float,
    t_hi: float,
    max_iter: int = MAX_ITER,
    min_consecutive: int = MIN_CONSECUTIVE,
) -> dict:
    """Levenberg-Marquardt with the hardened, stability-confirmed stopping rule.

    Arithmetic (steps, damping schedule, clipping) is the frozen E0 path; only
    the stopping rule and the bookkeeping differ.
    """
    if min_consecutive < 3:
        raise ValueError("min_consecutive must be >= 3 (two consecutive iterations are not enough)")
    span = max(float(t[-1] - t[0]), 1e-12)
    x = _clip_full(np.asarray(x0, dtype=np.float64), t_lo, t_hi, c)
    res, jac, _pred = _residual_and_jacobian(t, f, x, c)
    nfev = 1
    njev = 1
    sse = float(res @ res)
    lam = 1.0e-3
    consecutive = 0
    verification_iterations = 0
    history: list[dict] = []
    converged = False
    termination_reason = "iteration_budget"
    iteration_budget_hit = False
    it = 0
    last_criteria = criteria_at(t, f, x, c)

    for it in range(1, max_iter + 1):
        if not np.isfinite(sse):
            termination_reason = "numerical_failure"
            break
        a = jac.T @ jac
        g = jac.T @ res
        if not (np.all(np.isfinite(a)) and np.all(np.isfinite(g))):
            termination_reason = "numerical_failure"
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
                zstep = float(np.max(np.abs(dx) / SCALE_VECTOR))
                lam_used = float(lam)
                x, res, jac, sse = x_new, res_new, jac_new, sse_new
                lam = max(lam * 0.3, 1e-12)
                improved = True
                last_criteria = criteria_at(t, f, x, c, rel, zstep)
                last_criteria["lambda"] = lam_used
                last_criteria["kind"] = "accepted_step"
                last_criteria["iteration"] = int(it)
                history.append(last_criteria)
                consecutive = consecutive + 1 if last_criteria["criteria_pass"] else 0
                break
            lam *= 10.0

        if consecutive >= min_consecutive:
            converged = True
            termination_reason = "criteria_confirmed"
            break
        if not improved:
            # Fixed point: the optimizer cannot improve from x.  Evaluate the
            # criteria at x (no accepted change) and require k independent
            # verification attempts at distinct damping levels.
            fixed = criteria_at(t, f, x, c, relative_objective_change=0.0, scale_normalized_step=0.0)
            if not fixed["criteria_pass"]:
                last_criteria = fixed
                termination_reason = "stalled_without_stationarity"
                break
            accepted_in_verification = False
            for lam_v in VERIFICATION_DAMPING:
                try:
                    step = np.linalg.solve(a + lam_v * np.diag(diag), g)
                except np.linalg.LinAlgError:
                    step = None
                if step is None or not np.all(np.isfinite(step)):
                    verification_iterations += 1
                    continue
                x_new = _clip_full(x + step, t_lo, t_hi, c)
                res_new, jac_new, _ = _residual_and_jacobian(t, f, x_new, c)
                nfev += 1
                njev += 1
                sse_new = float(res_new @ res_new)
                if np.isfinite(sse_new) and sse_new < sse:
                    # The point was not fixed after all: accept the step and
                    # resume the main loop (stability counter resets).
                    dx = x_new - x
                    rel = (sse - sse_new) / max(sse, 1e-300)
                    zstep = float(np.max(np.abs(dx) / SCALE_VECTOR))
                    x, res, jac, sse = x_new, res_new, jac_new, sse_new
                    lam = max(lam_v * 0.3, 1e-12)
                    last_criteria = criteria_at(t, f, x, c, rel, zstep)
                    last_criteria["lambda"] = float(lam_v)
                    last_criteria["kind"] = "verification_accepted_step"
                    last_criteria["iteration"] = int(it)
                    history.append(last_criteria)
                    consecutive = consecutive + 1 if last_criteria["criteria_pass"] else 0
                    accepted_in_verification = True
                    break
                verification_iterations += 1
                entry = dict(fixed)
                entry["lambda"] = float(lam_v)
                entry["kind"] = "verification_rejected"
                entry["iteration"] = int(it)
                history.append(entry)
                consecutive += 1
                if consecutive >= min_consecutive:
                    break
            if accepted_in_verification:
                continue
            if consecutive >= min_consecutive:
                converged = True
                termination_reason = "fixed_point_verified"
                break
            termination_reason = "stalled_without_stationarity"
            break
    else:
        iteration_budget_hit = True
        termination_reason = "iteration_budget"

    if it >= max_iter and not converged and termination_reason == "iteration_budget":
        iteration_budget_hit = True

    final = criteria_at(t, f, x, c)
    return {
        "x": x,
        "objective": float(sse),
        "converged": bool(converged),
        "termination_reason": termination_reason,
        "iteration_budget_hit": bool(iteration_budget_hit),
        "iterations": int(it),
        "max_iter": int(max_iter),
        "nfev": int(nfev),
        "njev": int(njev),
        "consecutive_confirmations": int(consecutive),
        "verification_iterations": int(verification_iterations),
        "criteria": final,
        "history": history,
    }


# ---------------------------------------------------------------------------
# Fit (multi-start, same start selection as the frozen E0 fit)
# ---------------------------------------------------------------------------

@dataclass
class HardenedFitResult:
    """Result of the hardened E0 fit with the four separated statuses."""

    f0: float
    v: float
    t0: float
    b: float
    objective: float
    rms_hz: float
    sigma_f_hz: float
    n_points: int
    improvement_ratio: float
    se: dict[str, float] = field(default_factory=dict)
    corr: dict[str, float] = field(default_factory=dict)
    worst_rel_se: Optional[float] = None
    condition_number: Optional[float] = None
    worst_dir: dict[str, float] = field(default_factory=dict)
    optimization_converged: bool = False
    optimization_status: str = "indeterminate"
    optimization_reason: str = ""
    parameter_identifiable: bool = False
    model_adequate: bool = False
    decision_status: str = "indeterminate"
    decision_reason: str = ""
    iterations: int = 0
    max_iter: int = MAX_ITER
    iteration_budget_hit: bool = False
    nfev: int = 0
    njev: int = 0
    consecutive_confirmations: int = 0
    verification_iterations: int = 0
    criteria: dict = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)
    per_start: list[dict] = field(default_factory=list)
    n_starts: int = 0
    n_starts_ranked: int = 0
    best_start_index: int = 0
    n_starts_converged: int = 0

    @property
    def params(self) -> dict[str, float]:
        return {"f0": self.f0, "v": self.v, "t0": self.t0, "b": self.b}


def _covariance_and_identifiability(
    t: np.ndarray, f: np.ndarray, params: np.ndarray, c: float
) -> dict:
    """Linearized covariance diagnostics, same definitions as the frozen fit."""
    res, jac, _ = _residual_and_jacobian(t, f, params, c)
    n = int(f.size)
    sse = float(res @ res)
    dof = max(n - 4, 1)
    sigma_f = float(np.sqrt(sse / dof))
    se: dict[str, float] = {}
    corr: dict[str, float] = {}
    worst_rel_se: Optional[float] = None
    cond: Optional[float] = None
    worst_dir: dict[str, float] = {}
    try:
        cov = (sigma_f**2) * np.linalg.inv(jac.T @ jac)
        d = np.sqrt(np.maximum(np.diag(cov), 0.0))
        se = {name: float(d[i]) for i, name in enumerate(PARAM_ORDER)}
        pairs = (
            ("f0", "v"),
            ("f0", "t0"),
            ("f0", "b"),
            ("v", "t0"),
            ("v", "b"),
            ("t0", "b"),
        )
        for a, bname in pairs:
            ia, ib = PARAM_ORDER.index(a), PARAM_ORDER.index(bname)
            denom = d[ia] * d[ib]
            corr[f"{a}_{bname}"] = float(cov[ia, ib] / denom) if denom > 0 else float("nan")
        scale = np.outer(params, params)
        eigvals, eigvecs = np.linalg.eigh(cov / scale)
        eigvals = np.maximum(eigvals, 0.0)
        if eigvals[-1] > 0.0:
            worst_rel_se = float(np.sqrt(eigvals[-1]))
            if eigvals[0] > 0.0:
                cond = float(np.sqrt(eigvals[-1] / eigvals[0]))
            w = np.abs(eigvecs[:, -1])
            w = w / max(float(np.max(w)), 1e-300)
            worst_dir = {name: float(w[i]) for i, name in enumerate(PARAM_ORDER)}
    except np.linalg.LinAlgError:
        pass
    return {
        "se": se,
        "corr": corr,
        "worst_rel_se": worst_rel_se,
        "condition_number": cond,
        "worst_dir": worst_dir,
        "improvement_ratio": 0.0,
    }


def fit_hardened(
    t: np.ndarray,
    f: np.ndarray,
    c: float = C_SOUND_DEFAULT,
    n_starts: int = 5,
    max_iter: int = MAX_ITER,
    min_consecutive: int = MIN_CONSECUTIVE,
) -> HardenedFitResult:
    """Fit the E0 Doppler model under the hardened rule.

    Start selection is identical to the frozen E0 fit (same deterministic grid,
    same ranking, same five refined starts, same lowest-objective-wins choice),
    so a difference in the result is attributable to the stopping rule, not to
    a different search.
    """
    t = np.asarray(t, dtype=np.float64)
    f = np.asarray(f, dtype=np.float64)
    if t.size != f.size or t.size < 5:
        raise ValueError("need matching t/f arrays with >= 5 samples")
    span = float(t[-1] - t[0])
    t_lo, t_hi = float(t[0] - 10.0 * span), float(t[-1] + 10.0 * span)

    mean = float(np.mean(f))
    sse_const = float(np.sum((f - mean) ** 2))

    starts = _candidate_starts(t, f, c)
    scored: list[tuple[float, float, float, float]] = []
    for (v, t0, b) in starts:
        sse, _f0, _res, _jac = _profile_sse(t, f, v, t0, b, c)
        if np.isfinite(sse):
            scored.append((sse, v, t0, b))
    if not scored:
        raise RuntimeError("no finite starting point for the Doppler fit")
    chosen = _diverse_top(scored, n_starts, span)

    refined_starts: list[dict] = []
    for index, (_sse, v, t0, b) in enumerate(chosen):
        _sse0, f0_0, _r, _j = _profile_sse(t, f, v, t0, b, c)
        start = np.array([f0_0, v, t0, b], dtype=np.float64)
        refined = lm_refine_hardened(
            t, f, c, start, t_lo, t_hi, max_iter=max_iter, min_consecutive=min_consecutive
        )
        refined["start_index"] = index
        refined_starts.append(refined)
    best_index = int(np.argmin([start["objective"] for start in refined_starts]))
    best = refined_starts[best_index]

    params = np.asarray(best["x"], dtype=np.float64)
    f0, v, t0, b = (float(value) for value in params)
    objective = float(best["objective"])
    n = int(f.size)
    covariance = _covariance_and_identifiability(t, f, params, c)
    improvement = 0.0 if sse_const <= 0.0 else float(1.0 - objective / sse_const)
    covariance["improvement_ratio"] = improvement

    finite_params = bool(np.all(np.isfinite(params)) and f0 > 0.0 and v > 0.0 and b > 0.0)
    optimization_converged = bool(best["converged"])
    optimization_status = (
        "converged"
        if optimization_converged
        else ("failed" if best["termination_reason"] == "numerical_failure" else "indeterminate")
    )
    model_adequate = bool(
        improvement >= MODEL_MIN_IMPROVEMENT
        and np.isfinite(objective)
        and np.isfinite(best.get("criteria", {}).get("sigma_f_hz", float("inf")))
        and finite_params
    )
    ident = (
        covariance["worst_rel_se"] is not None
        and covariance["condition_number"] is not None
        and covariance["worst_rel_se"] <= IDENT_WORST_REL_SE_TOL
        and covariance["condition_number"] <= IDENT_CONDITION_NUMBER_TOL
    )
    parameter_identifiable = bool(optimization_converged and ident and finite_params)
    decision_status, decision_reason = _derive_decision(
        optimization_status,
        model_adequate,
        parameter_identifiable,
        improvement_ratio=improvement,
    )

    history = [
        {
            "iteration": int(entry.get("iteration", 0)),
            "kind": entry.get("kind"),
            "lambda": entry.get("lambda"),
            "objective": float(entry["objective"]),
            "relative_objective_change": float(entry["relative_objective_change"]),
            "scale_normalized_step": float(entry["scale_normalized_step"]),
            "predicted_newton_step_inf_norm": float(entry["predicted_newton_step_inf_norm"]),
            "criteria_pass": bool(entry["criteria_pass"]),
        }
        for entry in best["history"][-10:]
    ]
    per_start = [
        {
            "start_index": int(start["start_index"]),
            "objective": float(start["objective"]),
            "converged": bool(start["converged"]),
            "termination_reason": start["termination_reason"],
            "iterations": int(start["iterations"]),
            "iteration_budget_hit": bool(start["iteration_budget_hit"]),
        }
        for start in refined_starts
    ]

    return HardenedFitResult(
        f0=f0,
        v=v,
        t0=t0,
        b=b,
        objective=objective,
        rms_hz=float(np.sqrt(objective / n)),
        sigma_f_hz=float(best["criteria"]["sigma_f_hz"]),
        n_points=n,
        improvement_ratio=improvement,
        se=covariance["se"],
        corr=covariance["corr"],
        worst_rel_se=covariance["worst_rel_se"],
        condition_number=covariance["condition_number"],
        worst_dir=covariance["worst_dir"],
        optimization_converged=optimization_converged,
        optimization_status=optimization_status,
        optimization_reason=str(best["termination_reason"]),
        parameter_identifiable=parameter_identifiable,
        model_adequate=model_adequate,
        decision_status=decision_status,
        decision_reason=decision_reason,
        iterations=int(best["iterations"]),
        max_iter=int(best["max_iter"]),
        iteration_budget_hit=bool(best["iteration_budget_hit"]),
        nfev=int(best["nfev"]),
        njev=int(best["njev"]),
        consecutive_confirmations=int(best["consecutive_confirmations"]),
        verification_iterations=int(best["verification_iterations"]),
        criteria=best["criteria"],
        history=history,
        per_start=per_start,
        n_starts=len(chosen),
        n_starts_ranked=len(scored),
        best_start_index=best_index,
        n_starts_converged=sum(1 for start in refined_starts if start["converged"]),
    )
