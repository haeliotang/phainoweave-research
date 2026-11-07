"""Physical Doppler model fit (B1) and the model-free naive inversion (B0).

The measured quantity is an instantaneous-frequency track ``(t_k, f_k)`` from
:mod:`features`.  The physical model is the one in :mod:`synthetic`::

    f(t; f0, v, t0, b) = f0 / D(t),   D(t) = 1 + v**2 * tau / (c * r(tau)),
    r(tau) = sqrt(v**2 * tau**2 + b**2),   tau = t - t0,

with ``c`` fixed at the recorded sound speed and zero acceleration (the model
fitted in E0; acceleration mismatch is studied as a failure condition).

Estimator B1: deterministic multi-start Levenberg-Marquardt
-----------------------------------------------------------
``f0`` enters the model *linearly* (``f = f0 * h`` with ``h = 1/D``), so it is
profiled out exactly: for fixed ``(v, t0, b)`` the least-squares ``f0`` is
``(h . f) / (h . h)``.  The remaining three nonlinear parameters are refined by
Levenberg-Marquardt with an analytic Jacobian.  A deterministic coarse grid of
starts is ranked by profiled sum of squared errors and the best few
(diverse in ``t0``) are refined; the lowest-cost converged solution wins.  No
randomness, no dependence on a solver library.

Estimator B0: direct feature inversion (the baseline)
-----------------------------------------------------
The naive baseline reads the parameters off the IF track with no joint fit and
no noise model:

* ``t0``  = time of maximum ``|df/dt|`` (the closest-approach time, because the
  frequency slope is extremal there), refined by a parabola through the three
  neighbouring samples;
* ``f0``  = IF at that ``t0`` (at closest approach the radial velocity is zero);
* ``v``   = ``c * (f_hi - f_lo) / (f_hi + f_lo)`` from the extreme IF values,
  which is exact only if the window reaches the asymptotic approach and
  recede frequencies (it normally does not, so B0 carries a systematic
  window-truncation bias -- that is part of B0's definition);
* ``b``   = ``f0 * v**2 / (c * |df/dt|_max)`` from the closest-approach slope.

The functions return residuals and model-based asymptotic standard errors.
Because IF errors are heteroscedastic and correlated across overlapping
frames, the standard errors/correlations are a *linearized, homoscedastic
approximation*; E0 uses them for relative identifiability statements only, not
for calibration claims.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .synthetic import C_SOUND_DEFAULT, doppler_frequency


@dataclass
class FitResult:
    """Result of the physical model fit (estimator B1)."""

    f0: float
    v: float
    t0: float
    b: float
    converged: bool
    iterations: int
    n_starts: int
    n_starts_ranked: int
    sse: float
    rms: float
    n: int
    improvement_ratio: float          # 1 - SSE / SSE(constant-frequency model)
    sigma_f: float                    # sqrt(SSE/(n-4)), IF residual scale in Hz
    grad_norm: float = float("nan")   # normalized max|J^T r| at the returned point
    se: dict[str, float] = field(default_factory=dict)       # asymptotic 1-sigma, absolute units
    corr: dict[str, float] = field(default_factory=dict)     # signed parameter correlations
    worst_rel_se: Optional[float] = None                    # sqrt(max eig of relative covariance)
    condition_number: Optional[float] = None                # sqrt(max eig / min eig), relative
    worst_dir: dict[str, float] = field(default_factory=dict)  # |components| of worst eigvec
    predicted: np.ndarray = field(default_factory=lambda: np.zeros(0))
    residuals: np.ndarray = field(default_factory=lambda: np.zeros(0))

    @property
    def params(self) -> dict[str, float]:
        return {"f0": self.f0, "v": self.v, "t0": self.t0, "b": self.b}


@dataclass
class NaiveResult:
    """Result of the direct feature inversion (estimator B0)."""

    f0: float
    v: float
    t0: float
    b: float
    valid: bool
    rms: float
    improvement_ratio: float
    predicted: np.ndarray = field(default_factory=lambda: np.zeros(0))

    @property
    def params(self) -> dict[str, float]:
        return {"f0": self.f0, "v": self.v, "t0": self.t0, "b": self.b}


# ---------------------------------------------------------------------------
# Model pieces and analytic derivatives
# ---------------------------------------------------------------------------

def _model_terms(
    t: np.ndarray, v: float, t0: float, b: float, c: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return ``h = f/f0`` and its partial derivatives wrt ``v, t0, b``.

    ``h = 1/D`` with ``D = 1 + w/c`` and ``w = v**2 * tau / r``.
    """
    tau = t - t0
    r2 = v * v * tau * tau + b * b
    r = np.sqrt(r2)
    w = v * v * tau / r
    h = 1.0 / (1.0 + w / c)

    dw_dv = (v * tau / r) * (2.0 - v * v * tau * tau / r2)
    dw_dt0 = -(v * v * b * b) / (r2 * r)
    dw_db = -(v * v * tau * b) / (r2 * r)

    h2 = h * h
    dh_dv = -h2 * dw_dv / c
    dh_dt0 = -h2 * dw_dt0 / c
    dh_db = -h2 * dw_db / c
    return h, dh_dv, dh_dt0, dh_db


def _profile_sse(
    t: np.ndarray, f: np.ndarray, v: float, t0: float, b: float, c: float
) -> tuple[float, float, np.ndarray, np.ndarray]:
    """Profiled SSE and optimal ``f0``; also returns residual and prediction Jacobian."""
    h, dh_dv, dh_dt0, dh_db = _model_terms(t, v, t0, b, c)
    hh = float(h @ h)
    if not np.isfinite(hh) or hh <= 1e-300:
        return np.inf, np.nan, np.zeros_like(f), np.zeros((f.size, 3))
    f0 = float(h @ f) / hh
    res = f - f0 * h
    sse = float(res @ res)
    # d(prediction)/d(nonlinear params), f0 held at its profiled optimum
    jac = np.column_stack((f0 * dh_dv, f0 * dh_dt0, f0 * dh_db))
    return sse, f0, res, jac


def _clip(x: np.ndarray, t_lo: float, t_hi: float, c: float) -> np.ndarray:
    v = min(max(float(x[0]), 1.0), 0.98 * c)
    t0 = min(max(float(x[1]), t_lo), t_hi)
    b = min(max(float(x[2]), 1.0), 1.0e9)
    return np.array([v, t0, b], dtype=np.float64)


def _residual_and_jacobian(
    t: np.ndarray, f: np.ndarray, params: np.ndarray, c: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Residual ``f - f0*h`` and its analytic Jacobian wrt ``(f0, v, t0, b)``."""
    f0, v, t0, b = (float(params[0]), float(params[1]), float(params[2]), float(params[3]))
    h, dh_dv, dh_dt0, dh_db = _model_terms(t, v, t0, b, c)
    pred = f0 * h
    res = f - pred
    jac = np.column_stack((h, f0 * dh_dv, f0 * dh_dt0, f0 * dh_db))
    return res, jac, pred


def _sse_full(t: np.ndarray, f: np.ndarray, params: np.ndarray, c: float) -> float:
    f0, v, t0, b = (float(params[0]), float(params[1]), float(params[2]), float(params[3]))
    if not (np.isfinite(f0) and np.isfinite(v) and np.isfinite(t0) and np.isfinite(b)):
        return np.inf
    h, _, _, _ = _model_terms(t, v, t0, b, c)
    res = f - f0 * h
    return float(res @ res)


def _clip_full(
    x: np.ndarray, t_lo: float, t_hi: float, c: float
) -> np.ndarray:
    return np.array(
        [
            min(max(float(x[0]), 1.0e-3), 1.0e9),
            min(max(float(x[1]), 1.0), 0.98 * c),
            min(max(float(x[2]), t_lo), t_hi),
            min(max(float(x[3]), 1.0), 1.0e9),
        ],
        dtype=np.float64,
    )


def _lm_refine(
    t: np.ndarray,
    f: np.ndarray,
    c: float,
    x0: np.ndarray,
    t_lo: float,
    t_hi: float,
    max_iter: int = 100,
) -> dict:
    """Levenberg-Marquardt on all four parameters with an analytic Jacobian.

    ``f0`` is initialized from the exact profiled optimum for the starting
    ``(v, t0, b)``; the joint LM then refines all four parameters together.
    """
    span = max(float(t[-1] - t[0]), 1e-12)
    x = _clip_full(np.asarray(x0, dtype=np.float64), t_lo, t_hi, c)
    res, jac, _pred = _residual_and_jacobian(t, f, x, c)
    sse = float(res @ res)
    lam = 1.0e-3
    converged = False
    it = 0
    rel_step = np.inf
    for it in range(1, max_iter + 1):
        if not np.isfinite(sse):
            break
        a = jac.T @ jac
        g = jac.T @ res
        if not (np.all(np.isfinite(a)) and np.all(np.isfinite(g))):
            break
        diag = np.diag(a).copy()
        diag[diag <= 0.0] = 1.0
        improved = False
        for _ in range(12):
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
            sse_new = float(res_new @ res_new)
            if np.isfinite(sse_new) and sse_new < sse:
                dx = x_new - x
                rel = (sse - sse_new) / max(sse, 1e-300)
                rel_step = float(
                    np.max(np.abs(dx) / np.maximum(np.abs(x), np.array([1e-12, 1e-12, span, 1e-12])))
                )
                x, res, jac, sse = x_new, res_new, jac_new, sse_new
                lam = max(lam * 0.3, 1e-12)
                improved = True
                if rel_step < 1e-10 or rel < 1e-14:
                    converged = True
                break
            lam *= 10.0
        if not improved:
            break
        if converged:
            break

    # Stationarity check at the returned point.  A fit that stopped moving
    # because it reached the floating-point floor of the cost is converged even
    # if the relative-step test never fired.
    g = jac.T @ res
    gnorm = float(np.max(np.abs(g))) / (np.sqrt(sse * f.size) + 1e-300) if np.isfinite(sse) else np.inf
    if gnorm < 1e-6:
        converged = True
    return {
        "x": x,
        "sse": sse,
        "converged": converged,
        "iterations": it,
        "rel_step": rel_step,
        "grad_norm": gnorm,
    }


def _smooth(y: np.ndarray, width: int) -> np.ndarray:
    if width <= 1 or y.size < width:
        return y.copy()
    if width % 2 == 0:
        width += 1
    pad = width // 2
    yp = np.pad(y, pad, mode="edge")
    kernel = np.ones(width, dtype=np.float64) / width
    return np.convolve(yp, kernel, mode="valid")


def _parabolic_vertex(t: np.ndarray, y: np.ndarray) -> float:
    y_lo, y_c, y_hi = float(y[0]), float(y[1]), float(y[2])
    denom = y_lo - 2.0 * y_c + y_hi
    if abs(denom) < 1e-30:
        return float(t[1])
    step = 0.5 * (float(t[2]) - float(t[0]))
    delta = 0.5 * (y_lo - y_hi) / denom
    return float(t[1]) + step * delta


def _naive_features(
    t: np.ndarray, f: np.ndarray, c: float
) -> dict[str, float | bool]:
    """Closed-form feature inversion used by B0 and by B1's start grid.

    Textbook reduction from the two asymptotic Doppler frequencies
    ``f_hi = f0/(1-v/c)`` and ``f_lo = f0/(1+v/c)``::

        f0 = 2 f_hi f_lo / (f_hi + f_lo),   v = c (f_hi - f_lo)/(f_hi + f_lo)

    The observed window extremes are used as if they were the asymptotes (they
    are not, unless the window is long compared with ``b/v``), so ``v`` carries
    a systematic truncation bias.  The closest-approach time is the time at
    which the smoothed track crosses ``f0`` (at closest approach the radial
    velocity is zero, so ``f_obs = f0``); the closest-approach slope gives
    ``b = f0 v**2 / (c |df/dt|)``.  No forward-model fit, no noise model.

    Note: ``argmax |df/dt|`` is *not* the closest-approach time for this model
    -- the Doppler compression factor ``1/D**2`` shifts the steepest point onto
    the approaching side -- so a slope-peak estimator would be wrong by design.
    """
    span = float(t[-1] - t[0])
    if span <= 0.0 or f.size < 5:
        return {"valid": False, "t0": float(t[0]), "v": np.nan, "b": np.nan, "f0": float(f[0])}
    dt = float(np.median(np.diff(t)))
    width = max(3, int(round(0.15 / dt)))
    if width % 2 == 0:
        width += 1
    smooth = _smooth(f, width)
    slope = np.gradient(smooth, t)
    f_hi = float(np.max(smooth))
    f_lo = float(np.min(smooth))
    denom = f_hi + f_lo
    if not (denom > 0.0):
        return {"valid": False, "t0": float(t[0]), "v": np.nan, "b": np.nan, "f0": float(f[0])}
    f0 = 2.0 * f_hi * f_lo / denom
    v = c * (f_hi - f_lo) / denom
    # Track is decreasing in time (approaching -> receding); invert for the
    # time at which it crosses f0.  np.interp needs ascending x.
    t0 = float(np.interp(f0, smooth[::-1], t[::-1]))
    t0 = min(max(t0, float(t[0])), float(t[-1]))
    slope_at_t0 = float(abs(np.interp(t0, t, np.abs(slope))))
    b = f0 * v * v / (c * slope_at_t0) if slope_at_t0 > 0.0 else np.nan
    valid = bool(
        np.isfinite(v)
        and np.isfinite(b)
        and v > 1.0
        and v < 0.95 * c
        and b > 1.0
        and f0 > 0.0
    )
    return {"valid": valid, "t0": t0, "v": v, "b": b, "f0": f0}


def _candidate_starts(
    t: np.ndarray, f: np.ndarray, c: float
) -> list[tuple[float, float, float]]:
    """Deterministic coarse grid of (v, t0, b) starts."""
    span = float(t[-1] - t[0])
    nv = _naive_features(t, f, c)
    if nv["valid"]:
        v0 = float(nv["v"])
        b0 = float(nv["b"])
    else:
        v0 = 0.35 * c
        b0 = max(1.0, v0 * span / 6.0)
    v0 = min(max(v0, 2.0), 0.9 * c)
    b0 = min(max(b0, 1.0), 1.0e7)

    t0_base = float(nv["t0"])
    grid = list(np.linspace(t[0] + 0.05 * span, t[-1] - 0.05 * span, 9))
    grid.append(t0_base)
    starts: list[tuple[float, float, float]] = []
    for t0c in grid:
        for vf in (0.6, 1.0, 1.6):
            for bf in (0.3, 1.0, 3.0):
                starts.append((v0 * vf, float(t0c), b0 * bf))
    return starts


def _diverse_top(
    scored: list[tuple[float, float, float, float]], k: int, span: float
) -> list[tuple[float, float, float, float]]:
    chosen: list[tuple[float, float, float, float]] = []
    for cand in sorted(scored, key=lambda r: r[0]):
        if all(abs(cand[2] - c[2]) > 0.03 * span for c in chosen):
            chosen.append(cand)
        if len(chosen) >= k:
            break
    return chosen


def fit_doppler(
    t: np.ndarray,
    f: np.ndarray,
    c: float = C_SOUND_DEFAULT,
    n_starts: int = 5,
    max_iter: int = 200,
) -> FitResult:
    """Fit the physical Doppler model to an IF track (estimator B1)."""
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

    best: Optional[dict] = None
    for (_sse, v, t0, b) in chosen:
        _sse0, f0_0, _r, _j = _profile_sse(t, f, v, t0, b, c)
        start = np.array([f0_0, v, t0, b], dtype=np.float64)
        refined = _lm_refine(t, f, c, start, t_lo, t_hi, max_iter)
        if best is None or refined["sse"] < best["sse"]:
            best = refined
    assert best is not None

    f0, v, t0, b = (float(x) for x in best["x"])
    sse = float(best["sse"])
    _res, _jac, predicted = _residual_and_jacobian(t, f, best["x"], c)
    res = np.asarray(_res, dtype=np.float64)
    n = f.size
    dof = max(n - 4, 1)
    sigma_f = float(np.sqrt(sse / dof))

    # Full 4-parameter Jacobian for the asymptotic covariance.
    _h, dh_dv, dh_dt0, dh_db = _model_terms(t, v, t0, b, c)
    jac4 = _jac
    theta = np.array([f0, v, t0, b], dtype=np.float64)
    se: dict[str, float] = {}
    corr: dict[str, float] = {}
    worst_rel_se: Optional[float] = None
    cond: Optional[float] = None
    worst_dir: dict[str, float] = {}
    try:
        jtj = jac4.T @ jac4
        cov = (sigma_f**2) * np.linalg.inv(jtj)
        d = np.sqrt(np.maximum(np.diag(cov), 0.0))
        names = ("f0", "v", "t0", "b")
        se = {nm: float(d[i]) for i, nm in enumerate(names)}
        pairs = (("f0", "v"), ("f0", "t0"), ("f0", "b"), ("v", "t0"), ("v", "b"), ("t0", "b"))
        for a, bname in pairs:
            ia, ib = names.index(a), names.index(bname)
            denom = d[ia] * d[ib]
            corr[f"{a}_{bname}"] = float(cov[ia, ib] / denom) if denom > 0 else float("nan")
        scale = np.outer(theta, theta)
        cov_rel = cov / scale
        eigvals, eigvecs = np.linalg.eigh(cov_rel)
        eigvals = np.maximum(eigvals, 0.0)
        if eigvals[-1] > 0.0:
            worst_rel_se = float(np.sqrt(eigvals[-1]))
            if eigvals[0] > 0.0:
                cond = float(np.sqrt(eigvals[-1] / eigvals[0]))
            w = np.abs(eigvecs[:, -1])
            w = w / max(float(np.max(w)), 1e-300)
            worst_dir = {nm: float(w[i]) for i, nm in enumerate(names)}
    except np.linalg.LinAlgError:
        pass

    improvement = 0.0 if sse_const <= 0.0 else float(1.0 - sse / sse_const)
    return FitResult(
        f0=f0,
        v=v,
        t0=t0,
        b=b,
        converged=bool(best["converged"]),
        iterations=int(best["iterations"]),
        n_starts=len(chosen),
        n_starts_ranked=len(scored),
        sse=sse,
        rms=float(np.sqrt(sse / n)),
        n=n,
        improvement_ratio=improvement,
        sigma_f=sigma_f,
        grad_norm=float(best.get("grad_norm", float("nan"))),
        se=se,
        corr=corr,
        worst_rel_se=worst_rel_se,
        condition_number=cond,
        worst_dir=worst_dir,
        predicted=predicted,
        residuals=res,
    )


def naive_inversion(
    t: np.ndarray,
    f: np.ndarray,
    c: float = C_SOUND_DEFAULT,
) -> NaiveResult:
    """Direct feature inversion of the IF track (estimator B0), no fitting."""
    t = np.asarray(t, dtype=np.float64)
    f = np.asarray(f, dtype=np.float64)
    nf = _naive_features(t, f, c)
    t0 = float(nf["t0"])
    f0 = float(nf["f0"])
    v = float(nf["v"])
    b = float(nf["b"])
    valid = bool(nf["valid"])
    mean = float(np.mean(f))
    sse_const = float(np.sum((f - mean) ** 2))
    if not (np.isfinite(f0) and np.isfinite(v) and np.isfinite(b) and v > 0.0 and b > 0.0):
        return NaiveResult(
            f0=f0, v=v, t0=t0, b=b, valid=False, rms=float("inf"),
            improvement_ratio=0.0, predicted=np.zeros(0),
        )
    predicted = doppler_frequency(t, f0, v, t0, b, c)
    sse = float(np.sum((f - predicted) ** 2))
    improvement = 0.0 if sse_const <= 0.0 else float(1.0 - sse / sse_const)
    return NaiveResult(
        f0=f0,
        v=v,
        t0=t0,
        b=b,
        valid=valid,
        rms=float(np.sqrt(sse / f.size)),
        improvement_ratio=improvement,
        predicted=predicted,
    )
