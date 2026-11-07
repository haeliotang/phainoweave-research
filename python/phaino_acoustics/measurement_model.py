"""C2-A — measurement-model / extraction-error analysis.

This module is diagnostic.  It uses synthetic truth to compute

    e(t) = f_hat(t) - f_true(t)

for the frozen E0 front end over a chirp-rate/geometry continuum, quantifies the
systematic component ``E[e | chirp rate]``, the dependence on frequency
acceleration, SNR, analysis-window length and time position, the error
covariance (correlation time, heteroscedasticity), and provides an **empirical
error model** usable as a synthetic error generator (bias profile + AR(1)
residual).  It never enters a runtime decision path.

The extraction-error model is not claimed to be causal: it is a diagnostic
description of the measured error structure.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .experiment import BASE, F_MAX, F_MIN, FRAME_LEN, HOP
from .features import estimate_if_track
from .synthetic import Scenario, apparent_frequency, generate

MEASUREMENT_MODEL_ID = "e0-frontend-hann-stft-512-256"
MEASUREMENT_MODEL_VERSION = "1.0.0"
FRONT_END_PARAMETERS = {
    "frame_len": FRAME_LEN,
    "hop": HOP,
    "f_min_hz": F_MIN,
    "f_max_hz": F_MAX,
    "sample_rate_hz": BASE.fs,
    "window": "hann",
    "interpolation": "log-magnitude parabolic peak interpolation",
}

# C2-A design (declared, frozen for this artifact)
SEED_BASE = 70_000_000
SEED_FORMULA = "SEED_BASE + 1000*cell_index + trial"
N_PER_CELL = 3
GEOMETRY_M = tuple(float(value) for value in np.geomspace(120.0, 8000.0, 11))
SPEEDS_M_S = (60.0, 150.0, 250.0)
SNR_LEVELS_DB = (5.0, 20.0)
TIME_BINS = 10
ACF_LAGS = (1, 2, 5, 10, 20, 50)
CHIRP_EDGES_HZ_S = (0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 500.0, 1000.0, 3000.0)
WINDOW_FRAME_LENGTHS = (256, 512, 1024)
WINDOW_SWEEP_CELLS = ((150.0, 250.0), (600.0, 250.0), (2400.0, 250.0))
WINDOW_SWEEP_N = 2
WINDOW_SWEEP_SEED_OFFSET = 500_000


# ---------------------------------------------------------------------------
# Measurement-model record (ADR 0020 A.2/A.3)
# ---------------------------------------------------------------------------

def measurement_model_record() -> dict:
    return {
        "id": MEASUREMENT_MODEL_ID,
        "version": MEASUREMENT_MODEL_VERSION,
        "front_end": dict(FRONT_END_PARAMETERS),
        "error_model_id": "e0-c2a-empirical-bias-ar1-v1",
        "validity_conditions": [
            "narrowband single-source Doppler track within the 180-2800 Hz search band",
            "analysis frame 512 samples (64 ms) at 8 kHz, Hann window, hop 256",
            "per-sample SNR >= 5 dB as used in the C2-A design",
            "straight-line constant-velocity trajectory (no acceleration) for the error-model calibration",
        ],
        "notes": (
            "truth is used only in synthetic diagnosis to define e(t); the front end itself is unchanged "
            "and no runtime/decision path imports this module"
        ),
    }


# ---------------------------------------------------------------------------
# Analysis cells
# ---------------------------------------------------------------------------

def build_analysis_cells() -> list[dict]:
    cells = []
    index = 0
    for geometry in GEOMETRY_M:
        for speed in SPEEDS_M_S:
            for snr in SNR_LEVELS_DB:
                cells.append(
                    {
                        "cell_index": index,
                        "cell_id": f"b{geometry:g}_v{speed:g}_snr{snr:g}",
                        "geometry_m": float(geometry),
                        "speed_m_s": float(speed),
                        "snr_db": float(snr),
                    }
                )
                index += 1
    return cells


def cell_seed(cell_index: int, trial: int) -> int:
    return SEED_BASE + 1000 * int(cell_index) + int(trial)


def window_seed(cell_index: int, trial: int, frame_len: int) -> int:
    return SEED_BASE + WINDOW_SWEEP_SEED_OFFSET + 1000 * int(cell_index) + 100 * int(frame_len) + int(trial)


# ---------------------------------------------------------------------------
# e(t) and descriptive statistics
# ---------------------------------------------------------------------------

def _acf(values: np.ndarray, max_lag: int) -> np.ndarray:
    x = np.asarray(values, dtype=np.float64)
    x = x - float(np.mean(x))
    n = x.size
    if n == 0 or float(np.dot(x, x)) <= 0.0:
        return np.zeros(max_lag + 1)
    spectrum = np.fft.rfft(x, n=2 * n)
    autocovariance = np.fft.irfft(spectrum * np.conj(spectrum))[:n]
    return autocovariance / autocovariance[0]


def correlation_time_s(acf_values: np.ndarray, dt_s: float) -> Optional[float]:
    """Integral correlation time (sum of positive ACF up to the first zero crossing)."""
    total = 0.0
    for value in np.asarray(acf_values, dtype=np.float64)[1:]:
        if value <= 0.0:
            break
        total += float(value)
    return float(total * dt_s) if dt_s > 0.0 else None


def _chirp_rates(times: np.ndarray, true_frequency: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    fdot = np.gradient(np.asarray(true_frequency, dtype=np.float64), np.asarray(times, dtype=np.float64))
    fddot = np.gradient(fdot, np.asarray(times, dtype=np.float64))
    return fdot, fddot


def extract_error_track(
    scenario: Scenario,
    frame_len: int = FRAME_LEN,
    hop: Optional[int] = None,
) -> dict:
    """Generate one observation, extract the IF track, and compute e(t) = f_hat - f_true."""
    hop = (frame_len // 2) if hop is None else int(hop)
    observation = generate(scenario)
    track = estimate_if_track(
        observation.signal,
        scenario.fs,
        frame_len=int(frame_len),
        hop=int(hop),
        f_min=F_MIN,
        f_max=F_MAX,
        t_start=float(observation.t[0]),
    )
    true_frequency = apparent_frequency(scenario, track.t)
    error = np.asarray(track.f, dtype=np.float64) - np.asarray(true_frequency, dtype=np.float64)
    fdot, fddot = _chirp_rates(track.t, true_frequency)
    return {
        "scenario": scenario,
        "times": track.t,
        "true_frequency": true_frequency,
        "extracted_frequency": np.asarray(track.f, dtype=np.float64),
        "error": error,
        "chirp_rate": fdot,
        "chirp_acceleration": fddot,
        "frame_len": int(frame_len),
        "hop": int(hop),
    }


def summarise_track(sample: dict) -> dict:
    """Descriptive statistics for one e(t) track."""
    times = np.asarray(sample["times"], dtype=np.float64)
    error = np.asarray(sample["error"], dtype=np.float64)
    fdot = np.asarray(sample["chirp_rate"], dtype=np.float64)
    fddot = np.asarray(sample["chirp_acceleration"], dtype=np.float64)
    n = error.size
    dt = float(np.median(np.diff(times))) if n > 1 else 0.0
    normalised_time = (times - times[0]) / (times[-1] - times[0]) if n > 1 and times[-1] > times[0] else np.zeros(n)
    bin_index = np.minimum((normalised_time * TIME_BINS).astype(int), TIME_BINS - 1)
    bias_profile = []
    std_profile = []
    count_profile = []
    for bin_number in range(TIME_BINS):
        values = error[bin_index == bin_number]
        bias_profile.append(float(np.mean(values)) if values.size else None)
        std_profile.append(float(np.std(values)) if values.size else None)
        count_profile.append(int(values.size))
    acf = _acf(error, max(ACF_LAGS))
    acf_values = {f"lag_{lag}": float(acf[lag]) for lag in ACF_LAGS}
    residual = error - np.asarray(
        [bias_profile[index] if bias_profile[index] is not None else 0.0 for index in bin_index],
        dtype=np.float64,
    )
    residual_acf = _acf(residual, max(ACF_LAGS))
    std_values = [value for value in std_profile if value is not None and value > 0.0]
    heteroscedasticity = (max(std_values) / min(std_values)) if std_values else None
    return {
        "n_samples": int(n),
        "bias_hz": float(np.mean(error)),
        "rms_hz": float(np.sqrt(np.mean(error**2))),
        "std_hz": float(np.std(error)),
        "min_hz": float(np.min(error)),
        "max_hz": float(np.max(error)),
        "bias_profile": bias_profile,
        "std_profile": std_profile,
        "count_profile": count_profile,
        "time_bin_centers": [float((index + 0.5) / TIME_BINS) for index in range(TIME_BINS)],
        "acf": acf_values,
        "acf_lag1": float(acf[1]) if acf.size > 1 else None,
        "correlation_time_s": correlation_time_s(acf, dt),
        "residual_acf": {f"lag_{lag}": float(residual_acf[lag]) for lag in ACF_LAGS},
        "residual_ar1": float(residual_acf[1]) if residual_acf.size > 1 else None,
        "heteroscedasticity_ratio": heteroscedasticity,
        "chirp_rate_abs_median": float(np.median(np.abs(fdot))),
        "chirp_rate_abs_max": float(np.max(np.abs(fdot))),
        "chirp_acceleration_abs_median": float(np.median(np.abs(fddot))),
        "dt_s": dt,
    }


def aggregate_cell(cell: dict, samples: list[dict], summaries: list[dict]) -> dict:
    errors = np.concatenate([sample["error"] for sample in samples]) if samples else np.array([], dtype=np.float64)
    bias = float(np.mean(errors)) if errors.size else None
    rms = float(np.sqrt(np.mean(errors**2))) if errors.size else None
    std = float(np.std(errors)) if errors.size else None
    # structural fraction: variance of the seed-averaged error / total variance
    structural_fraction = None
    if samples:
        length = min(sample["error"].size for sample in samples)
        stack = np.stack([sample["error"][:length] for sample in samples])
        mean_error = np.mean(stack, axis=0)
        total_variance = float(np.var(stack))
        structural_fraction = float(np.var(mean_error) / total_variance) if total_variance > 0.0 else None
    mean_profiles = np.array(
        [np.mean([summary["bias_profile"][index] for summary in summaries]) for index in range(TIME_BINS)],
        dtype=np.float64,
    )
    mean_std = np.array(
        [np.mean([summary["std_profile"][index] for summary in summaries]) for index in range(TIME_BINS)],
        dtype=np.float64,
    )
    return {
        **cell,
        "n_trials": len(samples),
        "n_samples_total": int(errors.size),
        "bias_hz": bias,
        "rms_hz": rms,
        "std_hz": std,
        "structural_fraction": structural_fraction,
        "bias_profile": [float(value) for value in mean_profiles],
        "std_profile": [float(value) for value in mean_std],
        "time_bin_centers": [float((index + 0.5) / TIME_BINS) for index in range(TIME_BINS)],
        "acf_lag1_median": float(np.median([summary["acf_lag1"] for summary in summaries])) if summaries else None,
        "residual_ar1_median": float(np.median([summary["residual_ar1"] for summary in summaries])) if summaries else None,
        "correlation_time_s_median": float(
            np.median([summary["correlation_time_s"] for summary in summaries if summary["correlation_time_s"] is not None])
        )
        if any(summary["correlation_time_s"] is not None for summary in summaries)
        else None,
        "heteroscedasticity_ratio_median": float(
            np.median([summary["heteroscedasticity_ratio"] for summary in summaries if summary["heteroscedasticity_ratio"] is not None])
        )
        if any(summary["heteroscedasticity_ratio"] is not None for summary in summaries)
        else None,
        "residual_std_hz": float(np.median([summary["std_hz"] for summary in summaries])) if summaries else None,
        "residual_acf": {
            key: float(np.median([summary["residual_acf"][key] for summary in summaries]))
            for key in (f"lag_{lag}" for lag in ACF_LAGS)
        }
        if summaries
        else {},
    }


# ---------------------------------------------------------------------------
# Conditional diagnostics
# ---------------------------------------------------------------------------

def chirp_bin_edges() -> list[float]:
    return list(CHIRP_EDGES_HZ_S)


def conditional_error_by_chirp(samples: list[dict]) -> list[dict]:
    """E[e | |chirp rate|] over the declared chirp bins (pooled samples)."""
    edges = np.asarray(CHIRP_EDGES_HZ_S, dtype=np.float64)
    pooled_error = np.concatenate([sample["error"] for sample in samples])
    pooled_chirp = np.concatenate([np.abs(sample["chirp_rate"]) for sample in samples])
    pooled_accel = np.concatenate([np.abs(sample["chirp_acceleration"]) for sample in samples])
    bins = []
    for index in range(len(edges) - 1):
        low, high = float(edges[index]), float(edges[index + 1])
        mask = (pooled_chirp >= low) & (pooled_chirp < high)
        count = int(np.sum(mask))
        if count == 0:
            bins.append(
                {
                    "bin_id": f"chirp_{low:g}_{high:g}",
                    "chirp_low_hz_s": low,
                    "chirp_high_hz_s": high,
                    "n_samples": 0,
                    "mean_error_hz": None,
                    "std_error_hz": None,
                    "rms_error_hz": None,
                    "mean_abs_chirp_acceleration": None,
                }
            )
            continue
        values = pooled_error[mask]
        bins.append(
            {
                "bin_id": f"chirp_{low:g}_{high:g}",
                "chirp_low_hz_s": low,
                "chirp_high_hz_s": high,
                "n_samples": count,
                "mean_error_hz": float(np.mean(values)),
                "std_error_hz": float(np.std(values)),
                "rms_error_hz": float(np.sqrt(np.mean(values**2))),
                "mean_abs_chirp_acceleration": float(np.mean(pooled_accel[mask])),
            }
        )
    return bins


def conditional_residual_by_chirp(samples: list[dict]) -> list[dict]:
    """Residual (bias removed) std/ACF per chirp bin, pooled across cells."""
    edges = np.asarray(CHIRP_EDGES_HZ_S, dtype=np.float64)
    bin_lags = [[] for _ in range(len(edges) - 1)]
    bin_values = [[] for _ in range(len(edges) - 1)]
    for sample in samples:
        error = np.asarray(sample["error"], dtype=np.float64)
        times = np.asarray(sample["times"], dtype=np.float64)
        normalised = (times - times[0]) / max(times[-1] - times[0], 1e-12)
        bin_index = np.minimum((normalised * TIME_BINS).astype(int), TIME_BINS - 1)
        bias = np.array(
            [np.mean(error[bin_index == index]) if np.any(bin_index == index) else 0.0 for index in range(TIME_BINS)]
        )
        residual = error - bias[bin_index]
        chirp = np.abs(np.asarray(sample["chirp_rate"], dtype=np.float64))
        for bin_number in range(len(edges) - 1):
            mask = (chirp >= edges[bin_number]) & (chirp < edges[bin_number + 1])
            if np.any(mask):
                bin_values[bin_number].append(residual[mask])
        # per-bin ACF is computed from the pooled residual series per bin
    result = []
    for bin_number in range(len(edges) - 1):
        values = np.concatenate(bin_values[bin_number]) if bin_values[bin_number] else np.array([], dtype=np.float64)
        if values.size < 4:
            result.append(
                {
                    "bin_id": f"chirp_{edges[bin_number]:g}_{edges[bin_number + 1]:g}",
                    "n_samples": int(values.size),
                    "residual_std_hz": None,
                    "residual_acf": {},
                }
            )
            continue
        acf = _acf(values, max(ACF_LAGS))
        result.append(
            {
                "bin_id": f"chirp_{edges[bin_number]:g}_{edges[bin_number + 1]:g}",
                "n_samples": int(values.size),
                "residual_std_hz": float(np.std(values)),
                "residual_acf": {f"lag_{lag}": float(acf[lag]) for lag in ACF_LAGS},
            }
        )
    return result


def diagnostic_relationships(samples: list[dict]) -> dict:
    """Descriptive (not causal) relationships between e and frequency history."""
    error = np.concatenate([sample["error"] for sample in samples])
    chirp = np.concatenate([np.abs(sample["chirp_rate"]) for sample in samples])
    accel = np.concatenate([np.abs(sample["chirp_acceleration"]) for sample in samples])
    times = np.concatenate([sample["times"] for sample in samples])
    normalised = np.concatenate(
        [(sample["times"] - sample["times"][0]) / max(sample["times"][-1] - sample["times"][0], 1e-12) for sample in samples]
    )
    design = np.column_stack((np.ones_like(chirp), chirp, accel, normalised))
    coefficients, _residuals, _rank, _singular = np.linalg.lstsq(design, error, rcond=None)
    fitted = design @ coefficients
    total = float(np.sum((error - np.mean(error)) ** 2))
    r_squared = float(1.0 - np.sum((error - fitted) ** 2) / total) if total > 0.0 else None
    return {
        "model": "e ~ 1 + |chirp_rate| + |chirp_acceleration| + normalised_time (descriptive OLS, not causal)",
        "coefficients": {
            "intercept_hz": float(coefficients[0]),
            "abs_chirp_rate_hz_per_hz_s": float(coefficients[1]),
            "abs_chirp_acceleration_hz_per_hz_s2": float(coefficients[2]),
            "normalised_time_hz": float(coefficients[3]),
        },
        "r_squared": r_squared,
        "correlation": {
            "error_vs_abs_chirp_rate": float(np.corrcoef(error, chirp)[0, 1]),
            "error_vs_abs_chirp_acceleration": float(np.corrcoef(error, accel)[0, 1]),
            "chirp_rate_vs_chirp_acceleration": float(np.corrcoef(chirp, accel)[0, 1]),
        },
        "n_samples": int(error.size),
    }


def snr_dependence(cells: list[dict]) -> list[dict]:
    """For each (geometry, speed) compare the error statistics across SNR levels."""
    grouped: dict[tuple[float, float], dict[float, dict]] = {}
    for cell in cells:
        key = (float(cell["geometry_m"]), float(cell["speed_m_s"]))
        grouped.setdefault(key, {})[float(cell["snr_db"])] = cell
    result = []
    for (geometry, speed), by_snr in sorted(grouped.items()):
        levels = sorted(by_snr)
        if len(levels) < 2:
            continue
        low, high = levels[0], levels[-1]
        result.append(
            {
                "geometry_m": geometry,
                "speed_m_s": speed,
                "snr_low_db": low,
                "snr_high_db": high,
                "bias_low_hz": by_snr[low]["bias_hz"],
                "bias_high_hz": by_snr[high]["bias_hz"],
                "rms_low_hz": by_snr[low]["rms_hz"],
                "rms_high_hz": by_snr[high]["rms_hz"],
                "bias_ratio": (
                    float(by_snr[low]["bias_hz"] / by_snr[high]["bias_hz"])
                    if by_snr[low]["bias_hz"] not in (None, 0.0) and by_snr[high]["bias_hz"] not in (None, 0.0)
                    else None
                ),
            }
        )
    return result


def window_length_sweep(frame_len: int, hop: int, cells: list[dict], n_trials: int) -> list[dict]:
    """Small analysis-window-length sweep (the front end exposes frame length)."""
    sweep = []
    for cell_number, (geometry_m, speed_m_s) in enumerate(WINDOW_SWEEP_CELLS):
        scenario = Scenario(
            f0=BASE.f0,
            v=speed_m_s,
            b=geometry_m,
            t0=BASE.t0,
            duration=BASE.duration,
            fs=BASE.fs,
            c=BASE.c,
            snr_db=20.0,
        )
        samples = []
        summaries = []
        for trial in range(n_trials):
            trial_scenario = Scenario(**{**scenario.__dict__, "seed": window_seed(cell_number, trial, frame_len)})
            sample = extract_error_track(trial_scenario, frame_len=frame_len, hop=hop)
            samples.append(sample)
            summaries.append(summarise_track(sample))
        cell = {
            "cell_index": cell_number,
            "cell_id": f"window_{frame_len}_b{geometry_m:g}_v{speed_m_s:g}",
            "geometry_m": geometry_m,
            "speed_m_s": speed_m_s,
            "snr_db": 20.0,
            "frame_len": int(frame_len),
            "hop": int(hop),
        }
        aggregate = aggregate_cell(cell, samples, summaries)
        sweep.append(aggregate)
    return sweep


# ---------------------------------------------------------------------------
# Empirical error model (synthetic generator)
# ---------------------------------------------------------------------------

class EmpiricalErrorModel:
    """Empirical front-end error generator: bias profile + AR(1) residual.

    Built from the C2-A artifact.  For a requested (geometry, speed, SNR) it
    selects the nearest measured cell and generates

        e(t) = bias_profile(normalised time) + sigma * AR(1)(rho)

    with a fixed caller seed.  This is a *description* of the measured error,
    not a causal physical model.
    """

    GENERATOR_ID = "e0-c2a-empirical-bias-ar1-v1"

    def __init__(self, cells: list[dict]):
        self.cells = list(cells)

    @classmethod
    def from_artifact(cls, artifact: dict) -> "EmpiricalErrorModel":
        return cls(artifact["empirical_model"]["cells"])

    @classmethod
    def from_json_file(cls, path: str) -> "EmpiricalErrorModel":
        with open(path, "r", encoding="utf-8") as handle:
            return cls.from_artifact(json.load(handle))

    def _nearest_cell(self, geometry_m: float, speed_m_s: float, snr_db: float) -> dict:
        def distance(cell: dict) -> float:
            return (
                abs(float(cell["geometry_m"]) - float(geometry_m)) / max(float(geometry_m), 1.0)
                + abs(float(cell["speed_m_s"]) - float(speed_m_s)) / max(float(speed_m_s), 1.0)
                + abs(float(cell["snr_db"]) - float(snr_db)) / 20.0
            )

        return min(self.cells, key=distance)

    def generate(self, times: np.ndarray, geometry_m: float, speed_m_s: float, snr_db: float, seed: int) -> np.ndarray:
        """Generate one empirical error realization.

        Preferred method: measured bias profile + a measured residual template
        (bootstrap; preserves the full measured correlation shape).  Fallback
        (older artifacts without templates): AR(1) residual.  Both are
        deterministic for a fixed seed.
        """
        times = np.asarray(times, dtype=np.float64)
        cell = self._nearest_cell(geometry_m, speed_m_s, snr_db)
        normalised = (times - times[0]) / max(float(times[-1] - times[0]), 1e-12)
        bias_profile = np.asarray(
            [0.0 if value is None else float(value) for value in cell["bias_profile"]], dtype=np.float64
        )
        bin_centers = np.asarray(cell["time_bin_centers"], dtype=np.float64)
        bias = np.interp(normalised, bin_centers, bias_profile)
        template = cell.get("residual_template")
        rng = np.random.default_rng(int(seed) + 104729)
        if template:
            template_normalised = np.asarray(template["normalised_time"], dtype=np.float64)
            template_values = np.asarray([0.0 if value is None else float(value) for value in template["residual"]], dtype=np.float64)
            resampled = np.interp(normalised, template_normalised, template_values, left=template_values[0], right=template_values[-1])
            # Deterministic sign/roll variation so independent seeds do not repeat the same template.
            if rng.random() < 0.5:
                resampled = -resampled
            shift = int(rng.integers(0, max(resampled.size, 1)))
            residual = np.roll(resampled, shift)
            target_std = float(cell.get("residual_std_hz") or cell.get("std_hz") or 0.0)
            current_std = float(np.std(residual))
            if target_std > 0.0 and current_std > 0.0:
                residual = residual * (target_std / current_std)
            return bias + residual
        sigma = float(cell.get("residual_std_hz") or cell.get("std_hz") or 0.0)
        rho = float(cell.get("residual_ar1_median") or 0.0)
        rho = max(-0.95, min(0.95, rho))
        white = rng.standard_normal(times.size)
        residual = np.empty_like(white)
        if white.size:
            residual[0] = white[0]
            scale = float(np.sqrt(max(1.0 - rho * rho, 0.0)))
            for index in range(1, white.size):
                residual[index] = rho * residual[index - 1] + scale * white[index]
        return bias + sigma * residual


def build_empirical_model(cells: list[dict], residual_templates: Optional[dict] = None) -> dict:
    residual_templates = residual_templates or {}
    model_cells = []
    for cell in cells:
        model_cells.append(
            {
                "cell_id": cell["cell_id"],
                "geometry_m": cell["geometry_m"],
                "speed_m_s": cell["speed_m_s"],
                "snr_db": cell["snr_db"],
                "bias_profile": cell["bias_profile"],
                "time_bin_centers": cell["time_bin_centers"],
                "residual_std_hz": cell["residual_std_hz"],
                "std_hz": cell["std_hz"],
                "residual_ar1_median": cell["residual_ar1_median"],
                "residual_acf": cell["residual_acf"],
                "correlation_time_s_median": cell["correlation_time_s_median"],
                "residual_template": residual_templates.get(cell["cell_id"]),
            }
        )
    return {
        "model_id": EmpiricalErrorModel.GENERATOR_ID,
        "description": (
            "e(t) = interpolated bias profile over normalised time + measured residual bootstrap template "
            "(preferred; preserves the measured correlation shape, scaled to the cell residual std) or an "
            "AR(1) fallback; cell selected by nearest (geometry, speed, SNR); residual ACF reported per cell"
        ),
        "seed_policy": "caller supplies a fixed integer seed; residual uses numpy default_rng(seed + 104729)",
        "truth_usage": "diagnostic-only synthetic generator; never imported by a runtime/decision path",
        "cells": model_cells,
    }


# ---------------------------------------------------------------------------
# Artifact assembly
# ---------------------------------------------------------------------------

def build_error_model_artifact(
    cells: list[dict],
    chirp_bins: list[dict],
    diagnostics: dict,
    window_sweep: list[dict],
    environment: dict,
    records_sha256: str,
    limitations: list[str],
    residual_templates: Optional[dict] = None,
) -> dict:
    return {
        "artifact": "c2a-error-model",
        "version": "1.0.0",
        "generated_at_utc": None,  # set by caller for determinism control
        "measurement_model": measurement_model_record(),
        "config": {
            "seed_base": SEED_BASE,
            "seed_formula": SEED_FORMULA,
            "n_per_cell": N_PER_CELL,
            "geometry_m": list(GEOMETRY_M),
            "speeds_m_s": list(SPEEDS_M_S),
            "snr_levels_db": list(SNR_LEVELS_DB),
            "time_bins": TIME_BINS,
            "acf_lags": list(ACF_LAGS),
            "chirp_edges_hz_s": list(CHIRP_EDGES_HZ_S),
            "window_frame_lengths": list(WINDOW_FRAME_LENGTHS),
            "window_sweep_cells": [{"geometry_m": g, "speed_m_s": v} for g, v in WINDOW_SWEEP_CELLS],
            "truth_usage": "synthetic diagnosis only; e(t)=f_hat-f_true",
        },
        "cells": cells,
        "chirp_bins": chirp_bins,
        "diagnostics": diagnostics,
        "window_sweep": window_sweep,
        "empirical_model": build_empirical_model(cells, residual_templates),
        "records_sha256": records_sha256,
        "environment": environment,
        "limitations": limitations,
    }


def write_json(path: str, artifact: dict) -> str:
    import hashlib

    payload = (json.dumps(artifact, indent=1, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(payload)
    return hashlib.sha256(payload).hexdigest()
