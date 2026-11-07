"""Bench metrics: tone accuracy, window trade-off, clock rate/offset, chain."""

from __future__ import annotations

import math
from typing import Iterable, Optional, Sequence

import numpy as np


def estimate_tone_frequency(samples: Sequence[float], fs: float, n_fft: int = 4096) -> float:
    """Parabolic-interpolated FFT peak; a bench estimator, not a field model."""
    x = np.asarray(samples, dtype=float)
    if x.size < n_fft:
        n_fft = int(2 ** math.floor(math.log2(max(8, x.size))))
    window = np.hanning(x.size)
    spectrum = np.fft.rfft(x * window, n=n_fft)
    magnitude = np.abs(spectrum)
    k = int(np.argmax(magnitude[1:-1])) + 1
    a, b, c = magnitude[k - 1], magnitude[k], magnitude[k + 1]
    denom = a - 2.0 * b + c
    delta = 0.0 if denom == 0 else 0.5 * (a - c) / denom
    return float((k + delta) * fs / n_fft)


def _ci95(values: Sequence[float]) -> tuple[float, float]:
    arr = np.asarray(values, dtype=float)
    if arr.size < 2:
        return (float("nan"), float("nan"))
    half = 1.96 * float(np.std(arr, ddof=1)) / math.sqrt(arr.size)
    return (float(np.mean(arr) - half), float(np.mean(arr) + half))


def window_sweep(
    samples: Sequence[float],
    fs: float,
    expected_hz: float,
    windows: Iterable[int] = (512, 1024, 2048, 4096),
) -> list[dict]:
    """Bias, per-window bin width and algorithmic latency for one tone."""
    rows = []
    for n in windows:
        est = estimate_tone_frequency(samples, fs, n_fft=n)
        rows.append(
            {
                "window": int(n),
                "bin_hz": fs / n,
                "estimated_hz": est,
                "bias_hz": est - expected_hz,
                "latency_s": (n - 1) / (2.0 * fs),
            }
        )
    return rows


def two_anchor_rate_uncertainty(sigma_t_s: float, separation_s: float) -> float:
    """Simple two-anchor clock-rate standard uncertainty sqrt(2)*sigma_t/dT."""
    if separation_s <= 0:
        raise ValueError("separation_s must be positive")
    return math.sqrt(2.0) * sigma_t_s / separation_s


def clock_regression(
    reference_times_s: Sequence[float], observed_times_s: Sequence[float]
) -> dict:
    """OLS of observed vs reference times: t_obs = alpha * t_ref + beta."""
    x = np.asarray(reference_times_s, dtype=float)
    y = np.asarray(observed_times_s, dtype=float)
    if x.size < 3 or x.size != y.size:
        raise ValueError("clock regression needs >=3 paired anchors")
    design = np.column_stack([x, np.ones_like(x)])
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    alpha, beta = float(coef[0]), float(coef[1])
    residuals = y - (alpha * x + beta)
    dof = max(1, x.size - 2)
    sigma2 = float(np.sum(residuals**2) / dof)
    cov = sigma2 * np.linalg.inv(design.T @ design)
    sigma_alpha = float(math.sqrt(max(cov[0, 0], 0.0)))
    sigma_beta = float(math.sqrt(max(cov[1, 1], 0.0)))
    return {
        "alpha": alpha,
        "beta_s": beta,
        "sigma_alpha": sigma_alpha,
        "sigma_beta_s": sigma_beta,
        "residual_rms_s": float(math.sqrt(sigma2)),
        "n_anchors": int(x.size),
        "alpha_ci95": (alpha - 1.96 * sigma_alpha, alpha + 1.96 * sigma_alpha),
        "beta_ci95_s": (beta - 1.96 * sigma_beta, beta + 1.96 * sigma_beta),
    }


def signal_chain_difference(direct: dict, acoustic: dict) -> dict:
    """Compare direct-cable and speaker-microphone estimates of the same tone."""
    return {
        "bias_difference_hz": float(acoustic["bias_hz"] - direct["bias_hz"]),
        "variance_ratio": float(acoustic["variance_hz2"] / direct["variance_hz2"])
        if direct.get("variance_hz2")
        else None,
        "direct": direct,
        "acoustic": acoustic,
    }


def tone_accuracy(estimates_hz: Sequence[float], expected_hz: float) -> dict:
    values = [float(v) for v in estimates_hz]
    mean = float(np.mean(values))
    lo, hi = _ci95(values)
    return {
        "n": len(values),
        "expected_hz": float(expected_hz),
        "mean_hz": mean,
        "bias_hz": mean - expected_hz,
        "std_hz": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
        "ci95_mean_hz": (lo, hi),
    }


def downstream_error_impact(bias_hz: float, tolerance_hz: float) -> dict:
    """Illustrative: would a measured bias consume the claim tolerance?"""
    ratio = abs(bias_hz) / tolerance_hz if tolerance_hz else float("inf")
    return {
        "bias_hz": float(bias_hz),
        "tolerance_hz": float(tolerance_hz),
        "fraction_of_tolerance": ratio,
        "could_flip_decision": ratio >= 1.0,
    }
