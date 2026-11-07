"""Model Adequacy & Discrepancy layer (ADR 0015 sections 3-5).

An **independent** layer over the hardened estimator.  It never replaces the
hardened ``model_adequate`` field; it produces its own status, evidence and
diagnostics.  It uses only:

* the observation (the instantaneous-frequency track ``(t, f)``),
* the fitted model parameters,
* the declared noise-scale estimate (``sigma_f`` from the fit) and the declared
  sound speed.

**Truth/scenario values are never inputs.**  The experiment module writes them
into the artifact under ``evaluation_only`` for the independent evaluator, but
nothing in this module receives or reads them (enforced by the function
signatures and by a test).

Five tests (ADR 0015 section 3):

1. standardized residual scale and distribution;
2. residual autocorrelation / Ljung-Box with declared lag order, df, and a
   calibrated null threshold (no ``p < 0.05`` rule);
3. residual structure vs time and vs the model-predicted Doppler phase --
   targets omitted dynamics such as acceleration;
4. time-block held-out prediction with K=5 blocks;
5. parameter sensitivity / degeneracy, including the explicit clock model
   ``t_observed = alpha * t_physical + beta``.

The clock test is a *declaration*: an unknown clock makes ``alpha`` and
``beta`` exactly degenerate with ``(f0, b)`` and ``t0``, so the observation
cannot separate a clock excursion from a different source state.  The layer
reports ``not_separately_identifiable`` with the degeneracy directions instead
of a physical event time; the epistemic decision is then ``undetermined``.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from .adequacy_protocol import (
    PARAMETER_SCALES,
    PARAM_ORDER,
    PROTOCOL,
    PROTOCOL_DIGEST,
)
from .fit import _lm_refine, _residual_and_jacobian
from .synthetic import C_SOUND_DEFAULT, doppler_frequency, range_and_radial_velocity

SCALE_VECTOR = np.array([PARAMETER_SCALES[name] for name in PARAM_ORDER], dtype=np.float64)

# Clock-model parameter scales: (f0, v, t0, b, alpha, beta).
CLOCK_SCALE_VECTOR = np.array([500.0, 250.0, 20.0, 3000.0, 1.0, 20.0], dtype=np.float64)

# Central finite-difference steps for the clock-model Jacobian (declared).
CLOCK_FD_STEPS = np.array([5.0e-4, 2.5e-4, 2.0e-5, 3.0e-3, 1.0e-6, 1.0e-4], dtype=np.float64)

ACF_LAGS = tuple(int(lag) for lag in PROTOCOL["tests"]["autocorrelation"]["lags"])
LJUNG_BOX_ORDER = int(PROTOCOL["tests"]["autocorrelation"]["ljung_box_order"])
LJUNG_BOX_DF = int(PROTOCOL["tests"]["autocorrelation"]["ljung_box_df"])
N_BLOCKS = int(PROTOCOL["tests"]["block_prediction"]["n_blocks"])


# ---------------------------------------------------------------------------
# Model prediction, including the explicit clock model
# ---------------------------------------------------------------------------

def model_prediction(t: np.ndarray, params, c: float = C_SOUND_DEFAULT) -> np.ndarray:
    """Nominal model prediction ``f0 / (1 - v_r(t)/c)`` for ``params=(f0,v,t0,b)``."""
    theta = np.asarray(params, dtype=np.float64)
    return doppler_frequency(t, theta[0], theta[1], theta[2], theta[3], c)


def clock_model_prediction(
    t: np.ndarray, params_six, c: float = C_SOUND_DEFAULT
) -> np.ndarray:
    """Prediction under ``t_observed = alpha * t_physical + beta``.

    ``params_six = (f0, v, t0, b, alpha, beta)`` are **physical** parameters.
    The observed instantaneous frequency is ``(1/alpha) * f_physical(t_physical)``
    because a clock that runs at rate ``alpha`` also rescales frequency.
    """
    theta = np.asarray(params_six, dtype=np.float64)
    f0, v, t0, b, alpha, beta = (float(x) for x in theta)
    if alpha <= 0.0:
        return np.full(np.shape(t), np.nan)
    t_phys = (np.asarray(t, dtype=np.float64) - beta) / alpha
    _, vr = range_and_radial_velocity(t_phys, v, b, t0)
    return (f0 / alpha) / (1.0 - vr / c)


# ---------------------------------------------------------------------------
# Small statistics helpers
# ---------------------------------------------------------------------------

def _acf(residuals: np.ndarray, max_lag: int) -> np.ndarray:
    x = np.asarray(residuals, dtype=np.float64) - float(np.mean(residuals))
    n = x.size
    spectrum = np.fft.rfft(x, n=2 * n)
    autocovariance = np.fft.irfft(spectrum * np.conj(spectrum))[:n]
    if autocovariance[0] <= 0.0:
        return np.zeros(max_lag + 1, dtype=np.float64)
    return autocovariance / autocovariance[0]


def _ljung_box_statistic(residuals: np.ndarray) -> tuple[float, np.ndarray]:
    n = residuals.size
    acf = _acf(residuals, LJUNG_BOX_ORDER)
    statistic = float(
        n
        * (n + 2)
        * sum(acf[lag] ** 2 / (n - lag) for lag in range(1, LJUNG_BOX_ORDER + 1))
    )
    return statistic, acf


def _judge_upper(value: float, bound: float, margin: float) -> str:
    """pass / indeterminate / fail for an upper bound with a relative margin."""
    if not np.isfinite(value):
        return "fail"
    if value <= bound / (1.0 + margin):
        return "pass"
    if value <= bound * (1.0 + margin):
        return "indeterminate"
    return "fail"


def _judge_lower(value: float, bound: float, margin: float) -> str:
    """pass / indeterminate / fail for a lower bound with a relative margin."""
    if not np.isfinite(value):
        return "fail"
    if value >= bound * (1.0 + margin):
        return "pass"
    if value >= bound / (1.0 + margin):
        return "indeterminate"
    return "fail"


def _combine(statuses: list[str]) -> str:
    if any(status == "fail" for status in statuses):
        return "fail"
    if any(status == "indeterminate" for status in statuses):
        return "indeterminate"
    return "pass"


def _finite(value) -> bool:
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Tests 1-3: residual diagnostics
# ---------------------------------------------------------------------------

def standardized_residuals_test(
    residuals: np.ndarray, sigma_f: float, thresholds: dict, margin: float
) -> dict:
    """Test 1: standardized residual scale and distribution."""
    if not _finite(sigma_f) or sigma_f <= 0.0:
        return {
            "status": "fail",
            "reason": "noise_scale_unavailable",
            "sigma_f_hz": None,
            "metrics": {},
            "thresholds": thresholds,
        }
    z = np.asarray(residuals, dtype=np.float64) / float(sigma_f)
    n = z.size
    mean = float(np.mean(z))
    variance = float(np.var(z))
    median = float(np.median(residuals))
    mad = float(np.median(np.abs(np.asarray(residuals) - median)))
    robust_scale = 1.4826 * mad
    metrics = {
        "n": int(n),
        "rms_standardized": float(np.sqrt(np.mean(z**2))),
        "mean_standardized": mean,
        "robust_scale_ratio": float(sigma_f / robust_scale) if robust_scale > 0 else None,
        "max_abs_z": float(np.max(np.abs(z))),
        "tail_fraction_abs_z_gt_3": float(np.mean(np.abs(z) > 3.0)),
        "excess_kurtosis": float(np.mean((z - mean) ** 4) / variance**2 - 3.0)
        if variance > 0
        else None,
    }
    judgements = []
    rms_low, rms_high = thresholds["rms_bounds"]
    judgements.append(_judge_lower(metrics["rms_standardized"], rms_low, margin))
    judgements.append(_judge_upper(metrics["rms_standardized"], rms_high, margin))
    if metrics["robust_scale_ratio"] is None:
        judgements.append("fail")
    else:
        low, high = thresholds["robust_scale_ratio_bounds"]
        judgements.append(_judge_lower(metrics["robust_scale_ratio"], low, margin))
        judgements.append(_judge_upper(metrics["robust_scale_ratio"], high, margin))
    judgements.append(_judge_upper(metrics["max_abs_z"], thresholds["max_abs_z_max"], margin))
    judgements.append(
        _judge_upper(
            metrics["tail_fraction_abs_z_gt_3"],
            thresholds["tail_fraction_abs_z_gt_3_max"],
            margin,
        )
    )
    if metrics["excess_kurtosis"] is None:
        judgements.append("fail")
    else:
        judgements.append(
            _judge_upper(
                abs(metrics["excess_kurtosis"]), thresholds["abs_excess_kurtosis_max"], margin
            )
        )
    status = _combine(judgements)
    return {
        "status": status,
        "reason": None if status == "pass" else "residual_distribution",
        "judgements": judgements,
        "metrics": metrics,
        "thresholds": thresholds,
    }


def autocorrelation_test(residuals: np.ndarray, thresholds: dict, margin: float) -> dict:
    """Test 2: residual autocorrelation / Ljung-Box (calibrated threshold)."""
    n = residuals.size
    if n <= LJUNG_BOX_ORDER + 5:
        return {
            "status": "indeterminate",
            "reason": "too_few_residuals",
            "metrics": {},
            "thresholds": thresholds,
        }
    statistic, acf = _ljung_box_statistic(residuals)
    max_abs_acf = float(np.max(np.abs(acf[list(ACF_LAGS)])))
    judgements = [
        _judge_upper(statistic, thresholds["ljung_box_statistic_max"], margin),
        _judge_upper(max_abs_acf, thresholds["max_abs_acf_max"], margin),
    ]
    status = judgements[0]  # decided by the Ljung-Box statistic by protocol
    return {
        "status": status,
        "reason": None if status == "pass" else "residual_autocorrelation",
        "decided_by": thresholds["decided_by"],
        "metrics": {
            "n": int(n),
            "ljung_box_statistic": statistic,
            "ljung_box_order": LJUNG_BOX_ORDER,
            "ljung_box_df": LJUNG_BOX_DF,
            "max_abs_acf": max_abs_acf,
            "acf_lags": list(ACF_LAGS),
            "acf": [float(acf[lag]) for lag in ACF_LAGS],
            "max_abs_acf_judgement": judgements[1],
        },
        "thresholds": thresholds,
    }


def time_structure_test(
    t: np.ndarray, residuals: np.ndarray, predicted: np.ndarray, sigma_f: float, thresholds: dict, margin: float
) -> dict:
    """Test 3: residual structure vs time and vs the model-predicted Doppler phase."""
    n = residuals.size
    if not _finite(sigma_f) or sigma_f <= 0.0 or n < 12:
        return {
            "status": "indeterminate",
            "reason": "inputs_unavailable",
            "metrics": {},
            "thresholds": thresholds,
        }
    t = np.asarray(t, dtype=np.float64)
    centre = t - float(np.mean(t))
    spread = float(np.std(t))
    if spread <= 0.0:
        return {
            "status": "indeterminate",
            "reason": "degenerate_time_axis",
            "metrics": {},
            "thresholds": thresholds,
        }
    u = centre / spread
    design = np.column_stack((np.ones(n), u, u * u))
    coefficients = np.linalg.lstsq(design, residuals, rcond=None)[0]
    quadratic = float(coefficients[2] / sigma_f)
    corr_time = 0.0
    if float(np.std(residuals)) > 0.0:
        corr_time = float(np.corrcoef(residuals, u)[0, 1])
    # Model-predicted Doppler phase: phi(t) = 2*pi * integral f_pred dt.
    increments = 0.5 * (predicted[1:] + predicted[:-1]) * np.diff(t)
    phase = 2.0 * np.pi * np.concatenate(([0.0], np.cumsum(increments)))
    phase_corr = 0.0
    if float(np.std(residuals)) > 0.0:
        phase_corr = float(
            max(abs(np.corrcoef(residuals, np.cos(phase))[0, 1]),
                abs(np.corrcoef(residuals, np.sin(phase))[0, 1]))
        )
    metrics = {
        "n": int(n),
        "corr_time": corr_time,
        "quadratic_coefficient_over_sigma_f": quadratic,
        "max_abs_phase_correlation": phase_corr,
        "quadratic_r2": _quadratic_r2(u, residuals, coefficients),
    }
    judgements = [
        _judge_upper(abs(corr_time), thresholds["abs_corr_time_max"], margin),
        _judge_upper(abs(quadratic), thresholds["abs_quadratic_coefficient_max"], margin),
        _judge_upper(phase_corr, thresholds["abs_phase_correlation_max"], margin),
    ]
    status = _combine(judgements)
    return {
        "status": status,
        "reason": None if status == "pass" else "residual_time_structure",
        "judgements": judgements,
        "metrics": metrics,
        "thresholds": thresholds,
    }


def _quadratic_r2(u: np.ndarray, residuals: np.ndarray, coefficients: np.ndarray) -> Optional[float]:
    total = float(np.sum((residuals - np.mean(residuals)) ** 2))
    if total <= 0.0:
        return None
    design = np.column_stack((np.ones(u.size), u, u * u))
    fitted = design @ coefficients
    return float(1.0 - np.sum((residuals - fitted) ** 2) / total)


# ---------------------------------------------------------------------------
# Test 4: time-block held-out prediction
# ---------------------------------------------------------------------------

def block_prediction_test(
    t: np.ndarray,
    f: np.ndarray,
    params,
    c: float,
    sigma_f: float,
    thresholds: dict,
    margin: float,
) -> dict:
    """Test 4: K-block held-out prediction with deterministic local re-refinement."""
    t = np.asarray(t, dtype=np.float64)
    f = np.asarray(f, dtype=np.float64)
    n = f.size
    if n < N_BLOCKS * 10 or not _finite(sigma_f) or sigma_f <= 0.0:
        return {
            "status": "indeterminate",
            "reason": "too_few_samples_or_no_noise_scale",
            "metrics": {},
            "thresholds": thresholds,
        }
    blocks = np.array_split(np.arange(n), N_BLOCKS)
    normalized_rmse: list[float] = []
    explained: list[float] = []
    refit_converged: list[bool] = []
    start = np.asarray(params, dtype=np.float64)
    for block in blocks:
        keep = np.ones(n, dtype=bool)
        keep[block] = False
        t_keep, f_keep = t[keep], f[keep]
        span = max(float(t_keep[-1] - t_keep[0]), 1e-12)
        refined = _lm_refine(
            t_keep,
            f_keep,
            c,
            start,
            float(t_keep[0] - 10.0 * span),
            float(t_keep[-1] + 10.0 * span),
            max_iter=200,
        )
        refit_converged.append(bool(refined.get("converged", False)))
        theta = np.asarray(refined["x"], dtype=np.float64)
        if not np.all(np.isfinite(theta)) or theta[1] <= 0.0 or theta[3] <= 0.0:
            return {
                "status": "indeterminate",
                "reason": "block_refit_failed",
                "metrics": {"n_blocks": N_BLOCKS},
                "thresholds": thresholds,
            }
        predicted = model_prediction(t[block], theta, c)
        error = f[block] - predicted
        rmse = float(np.sqrt(np.mean(error**2)))
        normalized_rmse.append(rmse / sigma_f)
        block_variance = float(np.var(f[block]))
        explained.append(
            float(1.0 - np.mean(error**2) / block_variance) if block_variance > 0.0 else float("-inf")
        )
    metrics = {
        "n_blocks": N_BLOCKS,
        "block_normalized_rmse": normalized_rmse,
        "median_normalized_rmse": float(np.median(normalized_rmse)),
        "max_normalized_rmse": float(np.max(normalized_rmse)),
        "block_explained_fraction": explained,
        "min_block_explained_fraction": float(np.min(explained)),
        "median_block_explained_fraction": float(np.median(explained)),
        "refits_converged": refit_converged,
    }
    judgements = [
        _judge_upper(
            metrics["median_normalized_rmse"],
            thresholds["heldout_normalized_rmse_max"],
            margin,
        ),
        _judge_lower(
            metrics["median_block_explained_fraction"],
            thresholds["heldout_explained_fraction_min"],
            margin,
        ),
    ]
    status = _combine(judgements)
    return {
        "status": status,
        "reason": None if status == "pass" else "heldout_prediction",
        "judgements": judgements,
        "metrics": metrics,
        "thresholds": thresholds,
    }


# ---------------------------------------------------------------------------
# Test 5: parameter sensitivity / degeneracy, explicit clock model
# ---------------------------------------------------------------------------

def _clock_jacobian(t: np.ndarray, params: np.ndarray, c: float) -> np.ndarray:
    """Central-difference 6-parameter Jacobian of the clock-model prediction."""
    jacobian = np.empty((t.size, 6), dtype=np.float64)
    for index in range(6):
        step = np.zeros(6, dtype=np.float64)
        step[index] = CLOCK_FD_STEPS[index]
        plus = clock_model_prediction(t, params + step, c)
        minus = clock_model_prediction(t, params - step, c)
        jacobian[:, index] = (plus - minus) / (2.0 * step[index])
    return jacobian


def _nominal_gate(t: np.ndarray, f: np.ndarray, params: np.ndarray, c: float) -> dict:
    """Nominal 4-parameter linearized gate (ADR 0013 section 2 definitions)."""
    residual, jacobian, _ = _residual_and_jacobian(t, f, params, c)
    n = f.size
    sse = float(residual @ residual)
    dof = max(n - 4, 1)
    sigma_f = float(np.sqrt(sse / dof))
    result = {
        "covariance_available": False,
        "worst_rel_se": None,
        "condition_number": None,
        "worst_direction": {},
        "se": {},
        "sigma_f_hz": sigma_f,
    }
    try:
        covariance = (sigma_f**2) * np.linalg.inv(jacobian.T @ jacobian)
        standard_errors = np.sqrt(np.maximum(np.diag(covariance), 0.0))
        result["se"] = {
            name: float(standard_errors[i]) for i, name in enumerate(PARAM_ORDER)
        }
        scale = np.outer(params, params)
        eigenvalues, eigenvectors = np.linalg.eigh(covariance / scale)
        eigenvalues = np.maximum(eigenvalues, 0.0)
        if eigenvalues[-1] > 0.0:
            result["covariance_available"] = True
            result["worst_rel_se"] = float(np.sqrt(eigenvalues[-1]))
            if eigenvalues[0] > 0.0:
                result["condition_number"] = float(np.sqrt(eigenvalues[-1] / eigenvalues[0]))
            direction = np.abs(eigenvectors[:, -1])
            direction = direction / max(float(np.max(direction)), 1e-300)
            result["worst_direction"] = {
                name: float(direction[i]) for i, name in enumerate(PARAM_ORDER)
            }
    except np.linalg.LinAlgError:
        pass
    return result


def degeneracy_test(
    t: np.ndarray,
    f: np.ndarray,
    params,
    c: float,
    sigma_f: float,
    thresholds: dict,
) -> dict:
    """Test 5: nominal gate + explicit clock-model separability."""
    theta = np.asarray(params, dtype=np.float64)
    nominal = _nominal_gate(t, f, theta, c)
    evidence: dict = {
        "nominal": nominal,
        "clock_model": None,
        "clock_directions": [],
        "status": "indeterminate",
    }

    clock_params = np.array([theta[0], theta[1], theta[2], theta[3], 1.0, 0.0], dtype=np.float64)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        jacobian = _clock_jacobian(t, clock_params, c)
    if not np.all(np.isfinite(jacobian)):
        evidence["reason"] = "clock_jacobian_not_finite"
        return evidence
    scaled = jacobian * CLOCK_SCALE_VECTOR[None, :]
    information = scaled.T @ scaled
    try:
        eigenvalues, eigenvectors = np.linalg.eigh(information)
    except np.linalg.LinAlgError:
        evidence["reason"] = "clock_information_not_diagonalizable"
        return evidence
    largest = float(np.max(eigenvalues))
    if largest <= 0.0:
        evidence["reason"] = "degenerate_information"
        return evidence
    normalized = np.maximum(eigenvalues, 0.0) / largest
    null_ratio = float(normalized[0])
    order = np.argsort(normalized)
    null_vectors = {}
    for rank in range(2):
        index = int(order[rank])
        direction = eigenvectors[:, index]
        direction = direction / max(float(np.max(np.abs(direction))), 1e-300)
        null_vectors[f"direction_{rank}"] = {
            "normalized_eigenvalue": float(normalized[index]),
            "components": {
                name: float(direction[i])
                for i, name in enumerate((*PARAM_ORDER, "alpha", "beta"))
            },
        }

    # Analytic null directions in physical-parameter space (first order at alpha=1):
    #   alpha: (f0, 0, -t0, -b, 1, 0)
    #   beta:  (0, 0, -1, 0, 0, 1)
    f0, v, t0, b = (float(x) for x in theta)
    analytic = {
        "alpha": np.array([f0, 0.0, -t0, -b, 1.0, 0.0]),
        "beta": np.array([0.0, 0.0, -1.0, 0.0, 0.0, 1.0]),
    }
    analytic_residuals = {}
    for name, direction in analytic.items():
        d_theta = direction / max(float(np.linalg.norm(direction)), 1e-300)
        image = jacobian @ d_theta
        analytic_residuals[name] = {
            "relative_residual": float(np.linalg.norm(image) / (np.linalg.norm(scaled) * np.linalg.norm(d_theta) + 1e-300)),
            "components": {
                key: float(d_theta[i])
                for i, key in enumerate((*PARAM_ORDER, "alpha", "beta"))
            },
        }

    # Profile flatness: evaluate SSE along each analytic null direction.
    base_predicted = model_prediction(t, theta, c)
    base_sse = float(np.sum((f - base_predicted) ** 2))
    profile = {}
    for name, direction in analytic.items():
        scale = thresholds["alpha_perturbation"] if name == "alpha" else thresholds["beta_perturbation_s"]
        perturbation = direction / max(float(np.linalg.norm(direction)), 1e-300) * scale
        prediction = clock_model_prediction(t, clock_params + perturbation, c)
        sse = float(np.sum((f - prediction) ** 2))
        profile[name] = {
            "perturbation_norm": float(scale),
            "relative_sse_change": float(abs(sse - base_sse) / base_sse) if base_sse > 0.0 else None,
        }

    clock_null = null_ratio <= thresholds["clock_null_ratio_max"]
    profile_flat = all(
        entry["relative_sse_change"] is not None
        and entry["relative_sse_change"] <= thresholds["clock_profile_flatness_max"]
        for entry in profile.values()
    )
    clock_not_separable = bool(clock_null and profile_flat)

    nominal_gate_pass = bool(
        nominal["covariance_available"]
        and nominal["worst_rel_se"] is not None
        and nominal["worst_rel_se"] <= thresholds["worst_rel_se_max"]
        and nominal["condition_number"] is not None
        and nominal["condition_number"] <= thresholds["condition_number_max"]
    )

    if not nominal["covariance_available"] or not _finite(sigma_f) or sigma_f <= 0.0:
        status = "insufficient_evidence"
    elif not nominal_gate_pass:
        status = "insufficient_evidence"
    elif clock_not_separable:
        status = "not_separately_identifiable"
    else:
        status = "identifiable"

    evidence.update(
        {
            "status": status,
            "nominal_gate_pass": nominal_gate_pass,
            "clock_null_ratio": null_ratio,
            "clock_profile_flat": profile_flat,
            "clock_not_separable": clock_not_separable,
            "null_ratio_threshold": thresholds["clock_null_ratio_max"],
            "profile_threshold": thresholds["clock_profile_flatness_max"],
            "null_vectors": null_vectors,
            "analytic_null_directions": analytic_residuals,
            "profile": profile,
            "required_external_measurement": PROTOCOL["clock_equivalence"][
                "required_external_measurement"
            ],
        }
    )
    return evidence


# ---------------------------------------------------------------------------
# Layer evaluation
# ---------------------------------------------------------------------------

def evaluate_adequacy(
    t: np.ndarray,
    f: np.ndarray,
    params,
    sigma_f: float,
    optimization_status: str,
    c: float = C_SOUND_DEFAULT,
    protocol: Optional[dict] = None,
) -> dict:
    """Run all five tests and return the adequacy block of the artifact.

    No truth/scenario value is accepted or consulted; the arguments are the
    observation, the fitted parameters, the declared noise scale and the
    hardened optimizer status.
    """
    protocol = PROTOCOL if protocol is None else protocol
    theta = np.asarray(params, dtype=np.float64)
    margin = float(protocol["decision"]["margin_fraction"])
    thresholds = protocol["tests"]

    predicted = model_prediction(t, theta, c)
    residuals = np.asarray(f, dtype=np.float64) - predicted

    test_results = {
        "standardized_residuals": standardized_residuals_test(
            residuals, sigma_f, thresholds["standardized_residuals"], margin
        ),
        "autocorrelation": autocorrelation_test(
            residuals, thresholds["autocorrelation"], margin
        ),
        "time_structure": time_structure_test(
            t, residuals, predicted, sigma_f, thresholds["time_structure"], margin
        ),
        "block_prediction": block_prediction_test(
            t, f, theta, c, sigma_f, thresholds["block_prediction"], margin
        ),
        "degeneracy": degeneracy_test(t, f, theta, c, sigma_f, thresholds["degeneracy"]),
    }

    distribution = test_results["standardized_residuals"]["status"]
    structure = [
        test_results["autocorrelation"]["status"],
        test_results["time_structure"]["status"],
        test_results["block_prediction"]["status"],
    ]
    if distribution == "fail":
        model_adequacy_status = "insufficient_evidence"
    elif distribution == "indeterminate":
        model_adequacy_status = "indeterminate"
    elif any(status == "fail" for status in structure):
        model_adequacy_status = "discrepancy"
    elif any(status == "indeterminate" for status in structure):
        model_adequacy_status = "indeterminate"
    else:
        model_adequacy_status = "adequate"

    identifiability_status = test_results["degeneracy"]["status"]

    reason_codes: list[str] = []
    for name, result in test_results.items():
        if name == "degeneracy":
            continue
        if result["status"] != "pass" and result.get("reason"):
            reason_codes.append(result["reason"])
    if identifiability_status == "not_separately_identifiable":
        reason_codes.append("clock_equivalence")
    elif identifiability_status == "insufficient_evidence":
        reason_codes.append("identifiability_insufficient")

    epistemic_decision, decision_reasons = _epistemic_decision(
        optimization_status, model_adequacy_status, identifiability_status, test_results
    )
    reason_codes.extend(decision_reasons)
    # Stable, de-duplicated reason list.
    seen: set[str] = set()
    reason_codes = [code for code in reason_codes if not (code in seen or seen.add(code))]

    # Evidence for a protocol that declares a *conditional* claim (nominal clock
    # assumed): the observation supports the nominal-model solution.  This is
    # recorded inside the degeneracy evidence, never as the epistemic decision.
    test_results["degeneracy"]["conditional_claim_supported"] = bool(
        optimization_status == "converged"
        and test_results["degeneracy"].get("nominal_gate_pass", False)
        and model_adequacy_status == "adequate"
    )

    return {
        "model_adequacy_status": model_adequacy_status,
        "identifiability_status": identifiability_status,
        "epistemic_decision": epistemic_decision,
        "reason_codes": reason_codes,
        "tests": test_results,
    }


def _epistemic_decision(
    optimization_status: str,
    model_adequacy_status: str,
    identifiability_status: str,
    test_results: dict,
) -> tuple[str, list[str]]:
    """Declared epistemic precedence (ADR 0015 section 5)."""
    if optimization_status != "converged":
        return "undetermined", [f"optimization_{optimization_status}"]
    if model_adequacy_status == "discrepancy":
        reasons = [
            result["reason"]
            for name, result in test_results.items()
            if name != "degeneracy" and result["status"] == "fail" and result.get("reason")
        ]
        return "rejected", reasons
    if model_adequacy_status in ("insufficient_evidence", "indeterminate"):
        return "undetermined", ["adequacy_" + model_adequacy_status]
    if identifiability_status == "not_separately_identifiable":
        return "undetermined", ["clock_equivalence"]
    if identifiability_status != "identifiable":
        return "undetermined", ["identifiability_insufficient"]
    return "supported", []
