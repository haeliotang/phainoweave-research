"""C2-M2 — conditional measurement-error models (M0-M3) and features.

New development data (ADR 0021 C): geometry-continuum subset × speeds × SNR,
independent noise, initial carrier-phase jitter and frame-alignment jitter.
The C2-A cells are not reused as independent data.

Models (ADR 0021 B):
- M0 independent white noise (negative control);
- M1 empirical bias+template (the C2-A model, rebuilt on this development set);
- M2 conditional mean mu(x_t) from observable features (ablation, hierarchical
  partial pooling across geometry);
- M3 conditional covariance eta(t;x_t): parametric variance function + AR(2)
  finite-lag correlation (not a full high-dimensional matrix).

Features are runtime-observable except the diagnostic truth `q_true`, which is
reported for the FFT-bin-offset hypothesis only and never used by a deployment
generator.  Truth e(t) is used to fit the models (synthetic diagnosis).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from typing import Optional

import numpy as np

from .experiment import BASE, F_MAX, F_MIN, FRAME_LEN, HOP
from .features import estimate_if_track
from .measurement_model import EmpiricalErrorModel
from .synthetic import Scenario, apparent_frequency, generate

SEED_BASE = 80_000_000
SEED_FORMULA = "SEED_BASE + 1000*cell_index + trial"
TRAIN_GEOMETRIES_M = (180.0, 270.0, 400.0, 600.0, 900.0, 1400.0)
HELD_OUT_GEOMETRIES_M = (2100.0, 3200.0)
SPEEDS_M_S = (60.0, 250.0)
SNR_LEVELS_DB = (5.0, 20.0)
N_TRIALS_PER_CELL = 10
N_PREDICTIVE_SIMULATIONS = 8
FRAME_ALIGNMENT_MAX_SAMPLES = HOP  # jitter in [0, hop)
Q_BINS = 10
FEATURE_ABLATION = (
    ("F0_q", ("q_hat", "q_sin", "q_cos")),
    ("F1_q_chirp", ("q_hat", "q_sin", "q_cos", "abs_chirp")),
    ("F2_q_chirp_curvature", ("q_hat", "q_sin", "q_cos", "abs_chirp", "abs_curvature")),
    ("F3_plus_frame_position", ("q_hat", "q_sin", "q_cos", "abs_chirp", "abs_curvature", "frame_position")),
    (
        "F4_plus_freq_position",
        ("q_hat", "q_sin", "q_cos", "abs_chirp", "abs_curvature", "frame_position", "freq_position"),
    ),
    (
        "F5_plus_quality",
        (
            "q_hat",
            "q_sin",
            "q_cos",
            "abs_chirp",
            "abs_curvature",
            "frame_position",
            "freq_position",
            "quality_db",
        ),
    ),
)
RIDGE_LAMBDA = 1.0e-2
GEOMETRY_SHRINK_K = 200.0

# Pre-registered predictive tolerances (written before held-out scoring).
ACCEPTANCE_TOLERANCES = {
    "frr_gap_max_pp_per_geometry": 10.0,
    "lb_quantile_relative_gap_max": 0.5,
    "mean_bias_gap_max_hz": 0.10,
    "variance_ratio_range": [0.5, 2.0],
    "acf_lag1_gap_max": 0.20,
    "resample_unit": "independent trial/scenario (never frames)",
    "bootstrap_resamples": 1000,
    "language_rule": (
        "decision-level counts and percentage-point gaps; never 'explained X%'; "
        "insufficient_evidence is distinct from acceptance"
    ),
}


def acceptance_contract() -> dict:
    return {
        "artifact": "c2m2-acceptance-contract",
        "version": "1.0.0",
        "frozen_before_held_out_scoring": True,
        "tolerances": dict(ACCEPTANCE_TOLERANCES),
        "models": ["M0", "M1", "M2", "M3"],
        "held_out_geometries_m": list(HELD_OUT_GEOMETRIES_M),
        "training_geometries_m": list(TRAIN_GEOMETRIES_M),
        "speeds_m_s": list(SPEEDS_M_S),
        "snr_levels_db": list(SNR_LEVELS_DB),
        "feature_ablation": [{"name": name, "features": list(features)} for name, features in FEATURE_ABLATION],
        "selection_rule": (
            "feature set chosen on training geometries by leave-one-geometry-out predictive MSE; "
            "ties prefer fewer features; held-out geometries are scored once after freezing"
        ),
    }


# ---------------------------------------------------------------------------
# Development data
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DevelopmentCell:
    cell_index: int
    geometry_m: float
    speed_m_s: float
    snr_db: float
    split: str  # "train" or "held_out"

    @property
    def cell_id(self) -> str:
        return f"b{self.geometry_m:g}_v{self.speed_m_s:g}_snr{self.snr_db:g}"


def build_cells() -> list[DevelopmentCell]:
    cells = []
    index = 0
    for geometry in TRAIN_GEOMETRIES_M + HELD_OUT_GEOMETRIES_M:
        split = "train" if geometry in TRAIN_GEOMETRIES_M else "held_out"
        for speed in SPEEDS_M_S:
            for snr in SNR_LEVELS_DB:
                cells.append(
                    DevelopmentCell(
                        cell_index=index,
                        geometry_m=float(geometry),
                        speed_m_s=float(speed),
                        snr_db=float(snr),
                        split=split,
                    )
                )
                index += 1
    return cells


def cell_seed(cell: DevelopmentCell, trial: int) -> int:
    return SEED_BASE + 1000 * cell.cell_index + int(trial)


# ---------------------------------------------------------------------------
# Spectral quality (runtime-observable)
# ---------------------------------------------------------------------------

def spectral_quality_db(signal: np.ndarray, fs: float, frame_len: int, hop: int, f_min: float, f_max: float) -> np.ndarray:
    x = np.asarray(signal, dtype=np.float64)
    window = np.hanning(frame_len)
    n_frames = 1 + (x.size - frame_len) // hop
    if n_frames <= 0:
        return np.array([], dtype=np.float64)
    idx = np.arange(n_frames) * hop
    frames = x[idx[:, None] + np.arange(frame_len)[None, :]]
    mag = np.abs(np.fft.rfft(frames * window[None, :], axis=1))
    bin_hz = fs / frame_len
    k_min = max(int(np.ceil(f_min / bin_hz)), 1)
    k_max = min(int(np.floor(f_max / bin_hz)), mag.shape[1] - 2)
    band = mag[:, k_min : k_max + 1]
    peak = np.max(band, axis=1)
    median = np.median(band, axis=1) + 1e-12
    return 10.0 * np.log10(peak / median + 1e-12)


# ---------------------------------------------------------------------------
# Track generation with phase/frame-alignment jitter
# ---------------------------------------------------------------------------

def _fractional(values: np.ndarray) -> np.ndarray:
    return np.asarray(values, dtype=np.float64) - np.floor(np.asarray(values, dtype=np.float64))


def compute_features(
    times: np.ndarray,
    estimated_frequency: np.ndarray,
    true_frequency: np.ndarray,
    quality_db: np.ndarray,
    frame_len: int,
    fs: float,
) -> dict:
    times = np.asarray(times, dtype=np.float64)
    f_hat = np.asarray(estimated_frequency, dtype=np.float64)
    f_true = np.asarray(true_frequency, dtype=np.float64)
    kernel = np.ones(5, dtype=np.float64) / 5.0
    smoothed = np.convolve(f_hat, kernel, mode="same")
    chirp = np.gradient(smoothed, times)
    curvature = np.gradient(chirp, times)
    normalised_time = (times - times[0]) / max(float(times[-1] - times[0]), 1e-12)
    fft_bins = f_hat * float(frame_len) / float(fs)
    true_bins = f_true * float(frame_len) / float(fs)
    q_hat = _fractional(fft_bins)
    q_true = _fractional(true_bins)
    if quality_db.size != times.size:
        quality_db = np.interp(np.linspace(0.0, 1.0, times.size), np.linspace(0.0, 1.0, quality_db.size), quality_db) if quality_db.size else np.zeros(times.size)
    return {
        "times": times,
        "error": f_hat - f_true,
        "q_hat": q_hat,
        "q_sin": np.sin(2.0 * np.pi * q_hat),
        "q_cos": np.cos(2.0 * np.pi * q_hat),
        "q_true": q_true,
        "chirp": chirp,
        "abs_chirp": np.abs(chirp),
        "curvature": curvature,
        "abs_curvature": np.abs(curvature),
        "frame_position": normalised_time,
        "freq_position": (f_hat - F_MIN) / (F_MAX - F_MIN),
        "quality_db": quality_db,
    }


def generate_track(cell: DevelopmentCell, trial: int) -> dict:
    """One development track: noise, initial phase and frame-alignment jitter."""
    seed = cell_seed(cell, trial)
    rng = np.random.default_rng(seed)
    phase0 = float(rng.uniform(0.0, 2.0 * np.pi))
    frame_offset = int(rng.integers(0, FRAME_ALIGNMENT_MAX_SAMPLES))
    scenario = Scenario(
        f0=BASE.f0,
        v=cell.speed_m_s,
        b=cell.geometry_m,
        t0=BASE.t0,
        duration=BASE.duration,
        fs=BASE.fs,
        c=BASE.c,
        snr_db=cell.snr_db,
        phase0=phase0,
        seed=seed,
    )
    observation = generate(scenario)
    trimmed = observation.signal[frame_offset:]
    t_start = float(observation.t[0]) + frame_offset / float(scenario.fs)
    track = estimate_if_track(
        trimmed,
        scenario.fs,
        frame_len=FRAME_LEN,
        hop=HOP,
        f_min=F_MIN,
        f_max=F_MAX,
        t_start=t_start,
    )
    true_frequency = apparent_frequency(scenario, track.t)
    quality = spectral_quality_db(trimmed, scenario.fs, FRAME_LEN, HOP, F_MIN, F_MAX)
    features = compute_features(track.t, track.f, true_frequency, quality, FRAME_LEN, scenario.fs)
    return {
        "cell": cell,
        "trial": int(trial),
        "seed": int(seed),
        "phase0": phase0,
        "frame_offset_samples": frame_offset,
        "scenario": scenario,
        "times": track.t,
        "true_frequency": np.asarray(true_frequency, dtype=np.float64),
        "estimated_frequency": np.asarray(track.f, dtype=np.float64),
        "features": features,
        "error": features["error"],
    }


def _worker_track(task: tuple[DevelopmentCell, int]) -> dict:
    cell, trial = task
    return generate_track(cell, trial)


# ---------------------------------------------------------------------------
# FFT-bin-offset diagnostic (truth q allowed in diagnosis only)
# ---------------------------------------------------------------------------

def fft_bin_offset_diagnostic(trials: list[dict]) -> dict:
    error = np.concatenate([trial["features"]["error"] for trial in trials])
    q_true = np.concatenate([trial["features"]["q_true"] for trial in trials])
    q_hat = np.concatenate([trial["features"]["q_hat"] for trial in trials])
    edges = np.linspace(0.0, 1.0, Q_BINS + 1)
    bins = []
    for index in range(Q_BINS):
        low, high = float(edges[index]), float(edges[index + 1])
        mask = (q_true >= low) & (q_true < high)
        values = error[mask]
        bins.append(
            {
                "q_low": low,
                "q_high": high,
                "n_samples": int(mask.sum()),
                "mean_error_hz": float(np.mean(values)) if values.size else None,
                "std_error_hz": float(np.std(values)) if values.size else None,
            }
        )
    design = np.column_stack((np.ones_like(q_true), q_true, q_true**2, q_true**3))
    coefficients, _res, _rank, _singular = np.linalg.lstsq(design, error, rcond=None)
    fitted = design @ coefficients
    total = float(np.sum((error - np.mean(error)) ** 2))
    r_squared = float(1.0 - np.sum((error - fitted) ** 2) / total) if total > 0 else None
    return {
        "hypothesis": "parabolic log-magnitude interpolation bias is a function of fractional FFT-bin offset q(t)",
        "q_bins": bins,
        "q_true_polynomial_fit": {
            "model": "e ~ 1 + q + q^2 + q^3 (descriptive)",
            "coefficients": [float(value) for value in coefficients],
            "r_squared": r_squared,
        },
        "q_hat_relationship": {
            "correlation_error_vs_q_hat": float(np.corrcoef(error, q_hat)[0, 1]) if error.size > 1 else None,
            "correlation_error_vs_q_true": float(np.corrcoef(error, q_true)[0, 1]) if error.size > 1 else None,
        },
        "truth_usage": "q_true is a diagnostic reference only; deployment features use q_hat",
    }


# ---------------------------------------------------------------------------
# M2: conditional mean with hierarchical partial pooling
# ---------------------------------------------------------------------------

def _standardize(feature_matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = np.mean(feature_matrix, axis=0)
    std = np.std(feature_matrix, axis=0)
    std[std <= 0.0] = 1.0
    return (feature_matrix - mean) / std, mean, std


def _feature_matrix(trials: list[dict], feature_names: tuple[str, ...]) -> tuple[np.ndarray, np.ndarray, list[np.ndarray]]:
    rows = np.concatenate([np.column_stack([trial["features"][name] for name in feature_names]) for trial in trials])
    targets = np.concatenate([trial["features"]["error"] for trial in trials])
    geometry_ids = np.concatenate(
        [
            np.full(trial["features"]["error"].size, float(trial["cell"].geometry_m))
            for trial in trials
        ]
    )
    return rows, targets, geometry_ids


def _fit_ridge(feature_matrix: np.ndarray, target: np.ndarray, ridge: float = RIDGE_LAMBDA) -> np.ndarray:
    design = np.column_stack((np.ones(feature_matrix.shape[0]), feature_matrix))
    penalty = ridge * np.eye(design.shape[1])
    penalty[0, 0] = 0.0  # do not penalise the intercept
    coefficients = np.linalg.solve(design.T @ design + penalty, design.T @ target)
    return coefficients


def fit_hierarchical_mean(trials: list[dict], feature_names: tuple[str, ...]) -> dict:
    feature_matrix, target, geometry_ids = _feature_matrix(trials, feature_names)
    standardized, mean, std = _standardize(feature_matrix)
    coefficients = _fit_ridge(standardized, target)
    fitted = np.column_stack((np.ones(standardized.shape[0]), standardized)) @ coefficients
    residual = target - fitted
    geometry_values = np.asarray(geometry_ids)
    intercepts: dict[str, float] = {}
    for geometry in np.unique(geometry_values):
        mask = geometry_values == geometry
        count = int(mask.sum())
        mean_residual = float(np.mean(residual[mask])) if count else 0.0
        intercepts[str(float(geometry))] = mean_residual * (count / (count + GEOMETRY_SHRINK_K))
    return {
        "model": "hierarchical conditional mean",
        "feature_names": list(feature_names),
        "feature_mean": mean.tolist(),
        "feature_std": std.tolist(),
        "coefficients": coefficients.tolist(),
        "geometry_intercepts": intercepts,
        "ridge_lambda": RIDGE_LAMBDA,
        "geometry_shrink_k": GEOMETRY_SHRINK_K,
        "training_mse": float(np.mean(residual**2)),
        "pooling": "partial: global ridge coefficients + shrunk per-geometry intercepts (unseen geometry uses the global mean)",
    }


def predict_mean(model: dict, features: dict) -> np.ndarray:
    names = model["feature_names"]
    matrix = np.column_stack([features[name] for name in names])
    mean = np.asarray(model["feature_mean"])
    std = np.asarray(model["feature_std"])
    standardized = (matrix - mean) / std
    design = np.column_stack((np.ones(standardized.shape[0]), standardized))
    return design @ np.asarray(model["coefficients"])


def leave_one_geometry_out_mse(trials: list[dict], feature_names: tuple[str, ...]) -> dict:
    geometries = sorted({float(trial["cell"].geometry_m) for trial in trials})
    errors = []
    per_geometry = {}
    for geometry in geometries:
        train = [trial for trial in trials if float(trial["cell"].geometry_m) != geometry]
        test = [trial for trial in trials if float(trial["cell"].geometry_m) == geometry]
        model = fit_hierarchical_mean(train, feature_names)
        predicted = []
        target = []
        for trial in test:
            predicted.append(predict_mean(model, trial["features"]))
            target.append(trial["features"]["error"])
        predicted_values = np.concatenate(predicted)
        target_values = np.concatenate(target)
        mse = float(np.mean((target_values - predicted_values) ** 2))
        errors.append(mse)
        per_geometry[str(geometry)] = mse
    return {
        "mean_cv_mse": float(np.mean(errors)) if errors else None,
        "per_geometry_mse": per_geometry,
        "n_geometries": len(geometries),
    }


def select_feature_set(trials: list[dict]) -> dict:
    table = []
    for name, features in FEATURE_ABLATION:
        cv = leave_one_geometry_out_mse(trials, features)
        table.append({"name": name, "features": list(features), **cv})
    # choose minimum CV MSE; ties prefer the smaller feature set (declared order)
    best = min(table, key=lambda row: (row["mean_cv_mse"], len(row["features"])))
    return {"table": table, "selected": best["name"], "selected_features": best["features"], "selection_rule": "minimum leave-one-geometry-out MSE; ties prefer fewer features"}


# ---------------------------------------------------------------------------
# M1: current empirical bias+template model on the new development cells
# ---------------------------------------------------------------------------

def build_m1_model(training_trials: list[dict]) -> dict:
    by_cell: dict[str, list[dict]] = {}
    for trial in training_trials:
        by_cell.setdefault(trial["cell"].cell_id, []).append(trial)
    cells = []
    for cell_id, trials in sorted(by_cell.items()):
        cell = trials[0]["cell"]
        # frame-alignment jitter makes the frame count vary across trials; average
        # the time-bin bias profile over trials instead of stacking raw arrays.
        profile_accumulator = np.zeros(10, dtype=np.float64)
        profile_counts = np.zeros(10, dtype=np.int64)
        residuals = []
        ar1_values = []
        template = None
        for trial in trials:
            times = np.asarray(trial["features"]["times"], dtype=np.float64)
            error = np.asarray(trial["features"]["error"], dtype=np.float64)
            normalised = (times - times[0]) / max(times[-1] - times[0], 1e-12)
            bin_index = np.minimum((normalised * 10).astype(int), 9)
            trial_profile = np.zeros(10, dtype=np.float64)
            for index in range(10):
                mask = bin_index == index
                if np.any(mask):
                    trial_profile[index] = float(np.mean(error[mask]))
                    profile_accumulator[index] += trial_profile[index]
                    profile_counts[index] += 1
            residual = error - trial_profile[bin_index]
            residuals.append(residual)
            if residual.size > 2:
                ar1_values.append(float(np.corrcoef(residual[:-1], residual[1:])[0, 1]))
            if template is None:
                template = {
                    "normalised_time": [float(value) for value in normalised],
                    "residual": [float(value) for value in residual],
                }
        bias_profile = [
            float(profile_accumulator[index] / profile_counts[index]) if profile_counts[index] else 0.0
            for index in range(10)
        ]
        pooled_residual = np.concatenate(residuals) if residuals else np.array([], dtype=np.float64)
        cells.append(
            {
                "cell_id": cell_id,
                "geometry_m": cell.geometry_m,
                "speed_m_s": cell.speed_m_s,
                "snr_db": cell.snr_db,
                "bias_profile": bias_profile,
                "time_bin_centers": [(index + 0.5) / 10.0 for index in range(10)],
                "residual_std_hz": float(np.std(pooled_residual)),
                "std_hz": float(np.std(pooled_residual)),
                "residual_ar1_median": float(np.median(ar1_values)) if ar1_values else 0.0,
                "residual_template": template,
            }
        )
    return {"empirical_model": {"cells": cells}}


# ---------------------------------------------------------------------------
# M0 / M3 generators
# ---------------------------------------------------------------------------

def fit_m0(training_trials: list[dict]) -> dict:
    errors = np.concatenate([trial["features"]["error"] for trial in training_trials])
    group_sigma = {}
    for speed in SPEEDS_M_S:
        for snr in SNR_LEVELS_DB:
            values = [
                trial["features"]["error"]
                for trial in training_trials
                if trial["cell"].speed_m_s == speed and trial["cell"].snr_db == snr
            ]
            subset = np.concatenate(values) if values else np.array([], dtype=np.float64)
            group_sigma[f"{speed:g}_{snr:g}"] = (
                float(np.sqrt(np.mean(subset**2)))
                if subset.size
                else (float(np.sqrt(np.mean(errors**2))) if errors.size else 0.0)
            )
    return {"model": "white noise", "sigma_by_group_hz": group_sigma, "pooled_sigma_hz": float(np.sqrt(np.mean(errors**2)))}


def generate_m0(model: dict, times: np.ndarray, speed: float, snr: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(int(seed) + 24601)
    sigma = model["sigma_by_group_hz"].get(f"{speed:g}_{snr:g}", model["pooled_sigma_hz"])
    return sigma * rng.standard_normal(times.size)


def _ar2_coefficients(acf1: float, acf2: float) -> tuple[float, float]:
    """Yule-Walker for an AR(2) process."""
    denominator = 1.0 - acf1 * acf1
    if denominator <= 1e-6:
        return max(-0.95, min(0.95, acf1)), 0.0
    phi1 = acf1 * (1.0 - acf2) / denominator
    phi2 = (acf2 - acf1 * acf1) / denominator
    phi1 = max(-1.5, min(1.5, phi1))
    phi2 = max(-0.9, min(0.9, phi2))
    return phi1, phi2


def fit_m3(training_trials: list[dict], mean_model: dict) -> dict:
    """Conditional covariance: group variance × chirp-dependent scale + AR(1).

    Low-dimensional parametric covariance (finite-lag AR(1), variance conditioned
    on the observable |chirp|), not a full high-dimensional matrix.
    """
    groups: dict[tuple[float, float], list[np.ndarray]] = {}
    residuals = []
    abs_chirp = []
    for trial in training_trials:
        residual = trial["features"]["error"] - predict_mean(mean_model, trial["features"])
        residuals.append(residual)
        abs_chirp.append(trial["features"]["abs_chirp"])
        groups.setdefault((trial["cell"].speed_m_s, trial["cell"].snr_db), []).append(residual)
    pooled_residual = np.concatenate(residuals)
    pooled_chirp = np.concatenate(abs_chirp)
    global_std = float(np.std(pooled_residual))
    # chirp-dependent variance scale (pooled): std in 5 log-spaced bins / global std
    positive = pooled_chirp[pooled_chirp > 0.0]
    edges = np.quantile(positive, [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]) if positive.size else np.array([0.0, 1.0])
    edges = np.unique(np.maximum(edges, 1e-6))
    scale_points = []
    for index in range(len(edges) - 1):
        mask = (pooled_chirp >= edges[index]) & (pooled_chirp <= edges[index + 1])
        values = pooled_residual[mask]
        scale_points.append(float(np.std(values) / global_std) if values.size > 2 and global_std > 0.0 else 1.0)
    centers = [float((edges[index] + edges[index + 1]) / 2.0) for index in range(len(edges) - 1)]
    if not centers:
        centers, scale_points = [0.0], [1.0]
    correlation_by_group = {}
    variance_by_group = {}
    for (speed, snr), group_residuals in groups.items():
        stacked = np.concatenate(group_residuals)
        if stacked.size < 3:
            rho = 0.0
        else:
            rho = float(np.corrcoef(stacked[:-1], stacked[1:])[0, 1])
        rho = max(-0.9, min(0.9, rho))
        correlation_by_group[f"{speed:g}_{snr:g}"] = rho
        variance_by_group[f"{speed:g}_{snr:g}"] = float(np.std(stacked)) if stacked.size else global_std
    return {
        "model": "group variance x chirp-dependent variance scale + AR(1) finite-lag correlation",
        "global_std_hz": global_std,
        "chirp_scale_centers_hz_s": centers,
        "chirp_scale_factors": scale_points,
        "variance_by_group_hz": variance_by_group,
        "correlation_by_group_ar1": {"correlation_by_group": correlation_by_group},
        "note": "low-dimensional conditional covariance (group + observable chirp scale, AR(1)); not high-dimensional",
    }


def generate_m3(model: dict, times: np.ndarray, features: dict, speed: float, snr: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(int(seed) + 57321)
    group_key = f"{speed:g}_{snr:g}"
    base_std = float(model["variance_by_group_hz"].get(group_key, model["global_std_hz"]))
    centers = np.asarray(model["chirp_scale_centers_hz_s"], dtype=np.float64)
    scales = np.asarray(model["chirp_scale_factors"], dtype=np.float64)
    chirp = np.asarray(features["abs_chirp"], dtype=np.float64)
    conditional_std = base_std * np.interp(chirp, centers, scales, left=scales[0], right=scales[-1])
    rho = float(model["correlation_by_group_ar1"]["correlation_by_group"].get(group_key, 0.0))
    white = rng.standard_normal(times.size)
    residual = np.empty_like(white)
    if white.size:
        innovation = np.sqrt(max(1.0 - rho * rho, 1e-6))
        residual[0] = white[0]
        for index in range(1, white.size):
            residual[index] = rho * residual[index - 1] + innovation * white[index]
    return conditional_std * residual


def generate_m1(model_artifact: dict, times: np.ndarray, geometry: float, speed: float, snr: float, seed: int) -> np.ndarray:
    generator = EmpiricalErrorModel.from_artifact(
        {"empirical_model": {"cells": model_artifact["empirical_model"]["cells"]}}
    )
    return generator.generate(times, geometry, speed, snr, seed=seed)


def generate_m2_error(model: dict, features: dict, times: np.ndarray, speed: float, snr: float, m0: dict, seed: int) -> np.ndarray:
    rng = np.random.default_rng(int(seed) + 90210)
    sigma = m0["sigma_by_group_hz"].get(f"{speed:g}_{snr:g}", m0["pooled_sigma_hz"])
    return predict_mean(model, features) + sigma * rng.standard_normal(times.size)


# ---------------------------------------------------------------------------
# Artifact helpers
# ---------------------------------------------------------------------------

def trial_record(trial: dict) -> dict:
    return {
        "cell": {
            "cell_id": trial["cell"].cell_id,
            "geometry_m": trial["cell"].geometry_m,
            "speed_m_s": trial["cell"].speed_m_s,
            "snr_db": trial["cell"].snr_db,
            "split": trial["cell"].split,
        },
        "trial": trial["trial"],
        "seed": trial["seed"],
        "phase0": trial["phase0"],
        "frame_offset_samples": trial["frame_offset_samples"],
        "n_frames": int(trial["times"].size),
        "error_mean_hz": float(np.mean(trial["features"]["error"])),
        "error_rms_hz": float(np.sqrt(np.mean(trial["features"]["error"] ** 2))),
        "q_hat_mean": float(np.mean(trial["features"]["q_hat"])),
    }


def write_json(path: str, artifact: dict) -> str:
    import hashlib

    payload = (json.dumps(artifact, indent=1, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(payload)
    return hashlib.sha256(payload).hexdigest()
