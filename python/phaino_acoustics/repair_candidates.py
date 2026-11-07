"""PR-4e C2 repair candidates B0-B3 — measurement-layer primitives.

ADR 0020 D defines four *independent* candidates on the same observations:

* **B0** original front end + adequacy (paired baseline).
* **B1** de-chirp: compensate the candidate model's predicted frequency change
  before residual analysis.  Implemented as a *coherent measurement-model
  transform*: the raw waveform is demodulated by the phase of the B0 fitted
  constant-velocity model, the nearly-constant residual IF is re-extracted with
  the same Hann/STFT/parabolic front end, and the model prediction is added
  back.  The result is a reconstructed track on the original time axis; the
  **same physical estimator** (``fit_hardened``) is then run on it.  Exactly the
  model's *predicted CV frequency history* is de-chirped.  Genuine acceleration
  is **not** in the model prediction, so it survives as a residual frequency
  ramp and remains detectable; ``residual`` values are never smoothed, trended
  or thresholded away.
* **B2** residual pre-whitening: an AR(p) filter is estimated from
  *correct-model* calibration residuals (separate seeds) and applied to the
  Ljung-Box autocorrelation statistic only.  The other four adequacy tests and
  the frozen adequacy thresholds are untouched; the whitened Ljung-Box null is
  calibrated from the same correct-model calibration sample.
* **B3** geometry-conditioned calibration: the Ljung-Box, time-structure and
  held-out block-prediction thresholds are calibrated per cell of
  **runtime-observable** quantities (estimated chirp rate, estimated SNR) from
  correct-model calibration data.
  True closest approach, true speed/acceleration, scenario/mechanism labels and
  within-tolerance flags are forbidden inputs and are asserted absent.

This module contains no truth usage: every function takes observation-derived
quantities, fitted parameters and calibration data only.  The experiment module
writes truth into ``evaluation_only`` for the independent evaluator; nothing
here reads it.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

import numpy as np

from . import adequacy
from .adequacy import autocorrelation_test, model_prediction
from .adequacy_protocol import CALIBRATION_MARGIN, PROTOCOL
from .synthetic import doppler_frequency

CANDIDATE_IDS: tuple[str, ...] = ("B0", "B1", "B2", "B3")

CANDIDATE_DESCRIPTIONS: dict[str, str] = {
    "B0": "original front end + frozen adequacy protocol (paired baseline)",
    "B1": (
        "coherent de-chirp: demodulate by the B0 model-predicted phase, re-extract the "
        "residual IF with the same STFT front end, add the prediction back, and refit with "
        "the same hardened estimator"
    ),
    "B2": (
        "AR(p) residual pre-whitening of the Ljung-Box autocorrelation test, with the "
        "whitened null calibrated on correct-model development residuals"
    ),
    "B3": (
        "geometry-conditioned calibration of the Ljung-Box and time-structure thresholds "
        "from runtime-observable estimated chirp rate and estimated SNR bins"
    ),
}

#: Runtime-observable quantities this method side is allowed to compute and use.
ALLOWED_RUNTIME_OBSERVABLES: tuple[str, ...] = (
    "estimated_chirp_rate_hz_s",
    "median_abs_chirp_rate_hz_s",
    "estimated_snr_db",
    "signal_quality_improvement_ratio",
    "fit_uncertainty_worst_rel_se",
    "fit_condition_number",
    "residual_rms_hz",
    "n_frames",
)

#: The subset B3 is allowed to select its calibration cell with.
B3_SELECTION_INPUTS: tuple[str, ...] = (
    "estimated_chirp_rate_hz_s",
    "estimated_snr_db",
    "signal_quality_improvement_ratio",
    "fit_uncertainty_worst_rel_se",
)

#: ADR 0020 D.3 / repair plan: truth and labels are never selection inputs.
FORBIDDEN_SELECTION_INPUTS: tuple[str, ...] = (
    "true_closest_approach_b",
    "true_speed",
    "true_acceleration",
    "true_b",
    "true_v",
    "true_accel",
    "scenario_label",
    "mechanism_label",
    "stratum",
    "condition",
    "within_tolerance",
    "estimate_within_tolerance",
    "truth",
)

_FORBIDDEN_TOKENS: tuple[str, ...] = (
    "true_",
    "truth",
    "scenario",
    "mechanism",
    "closest_approach",
    "within_tolerance",
    "tolerance",
    "acceleration",
    "speed",
    "label",
)

# --- B1 de-chirp constants (declared before the development run) -----------
B1_DEMOD_BAND_HZ = 400.0
B1_FRAME_LEN = 512
B1_HOP = 256
B1_MIN_FRAMES = 8

# --- B2 pre-whitening constants -------------------------------------------
B2_AR_ORDER = 8

# --- B3 conditioning grid (runtime observables only) ----------------------
B3_CHIRP_EDGES_HZ_S: tuple[float, ...] = (0.0, 50.0, 150.0, 400.0, 1.0e12)
B3_SNR_EDGES_DB: tuple[float, ...] = (-1.0e12, 10.0, 1.0e12)
B3_MIN_CALIBRATION_CELL = 4


# ---------------------------------------------------------------------------
# Runtime observables (never truth)
# ---------------------------------------------------------------------------

def runtime_observables(
    frame_times: np.ndarray,
    predicted: np.ndarray,
    residuals: np.ndarray,
    sigma_f_hz: float,
    improvement_ratio: float,
    worst_rel_se: Optional[float],
    condition_number: Optional[float],
) -> dict[str, float]:
    """Compute the declared runtime-observable conditioning features.

    Every returned value is a finite float derived from the observation, the
    fitted parameters or the fit diagnostics.  No truth, scenario label or
    tolerance flag is accepted by this function.
    """
    times = np.asarray(frame_times, dtype=np.float64)
    pred = np.asarray(predicted, dtype=np.float64)
    res = np.asarray(residuals, dtype=np.float64)
    chirp = np.gradient(pred, times)
    abs_chirp = np.abs(chirp)
    improvement = float(np.clip(float(improvement_ratio), 0.0, 1.0 - 1e-12))
    estimated_snr_db = 10.0 * math.log10((improvement + 1e-12) / (1.0 - improvement + 1e-12))
    estimated_snr_db = float(np.clip(estimated_snr_db, -30.0, 60.0))
    residual_rms = float(np.sqrt(np.mean(res**2))) if res.size else float("nan")
    return {
        "estimated_chirp_rate_hz_s": _finite_or(float(np.max(abs_chirp)), 0.0),
        "median_abs_chirp_rate_hz_s": _finite_or(float(np.median(abs_chirp)), 0.0),
        "estimated_snr_db": _finite_or(estimated_snr_db, -30.0),
        "signal_quality_improvement_ratio": _finite_or(improvement, 0.0),
        "fit_uncertainty_worst_rel_se": _finite_or(worst_rel_se, 1.0),
        "fit_condition_number": _finite_or(condition_number, 1.0e12),
        "residual_rms_hz": _finite_or(residual_rms, 0.0),
        "n_frames": float(times.size),
        "sigma_f_hz": _finite_or(sigma_f_hz, 0.0),
    }


def _finite_or(value, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    return number if np.isfinite(number) else float(fallback)


def assert_runtime_observable_inputs(features: Mapping[str, object]) -> dict:
    """Assert that a selection map contains only declared runtime observables.

    Raises :class:`AssertionError` if a key is a truth/label quantity or is not
    in :data:`ALLOWED_RUNTIME_OBSERVABLES`.  This is the runtime-leakage gate
    required by ADR 0020 D.3 / the repair plan; it is called by B3 before every
    calibration lookup.
    """
    if not isinstance(features, Mapping):
        raise AssertionError("selection inputs must be a mapping")
    allowed = set(ALLOWED_RUNTIME_OBSERVABLES)
    declared = set(B3_SELECTION_INPUTS)
    for key, value in features.items():
        if not isinstance(key, str) or not key:
            raise AssertionError(f"selection input key {key!r} is not a non-empty string")
        lowered = key.lower()
        if key in FORBIDDEN_SELECTION_INPUTS or any(token in lowered for token in _FORBIDDEN_TOKENS):
            raise AssertionError(
                f"truth/label selection input {key!r} is forbidden by ADR 0020 D.3"
            )
        if key not in allowed:
            raise AssertionError(
                f"selection input {key!r} is not a declared runtime observable"
            )
        if not isinstance(value, (int, float, np.integer, np.floating)) or isinstance(value, bool):
            raise AssertionError(f"selection input {key!r} must be numeric, got {type(value).__name__}")
        if not np.isfinite(float(value)):
            raise AssertionError(f"selection input {key!r} must be finite")
    if not set(features).issubset(declared):
        raise AssertionError(
            "selection inputs must be a subset of B3_SELECTION_INPUTS: "
            f"{sorted(set(features) - declared)}"
        )
    return {
        "allowed": sorted(allowed),
        "selection_inputs": sorted(declared),
        "provided": sorted(features),
        "forbidden": list(FORBIDDEN_SELECTION_INPUTS),
        "runtime_observable_only": True,
    }


# ---------------------------------------------------------------------------
# B1 — coherent de-chirp against the candidate model's predicted frequency
# ---------------------------------------------------------------------------

def dechirped_track(
    signal: np.ndarray,
    sample_times: np.ndarray,
    params: Sequence[float],
    c: float,
    frame_times: np.ndarray,
    *,
    fs: float,
    band_hz: float = B1_DEMOD_BAND_HZ,
    frame_len: int = B1_FRAME_LEN,
    hop: int = B1_HOP,
) -> np.ndarray:
    """Reconstruct the IF track after de-chirping the model's predicted phase.

    The **only** thing removed is the B0 fitted constant-velocity model's
    predicted frequency history, through the phase
    ``phi(t) = 2*pi * integral f_pred(t) dt``.  The demodulated signal keeps any
    discrepancy between the data and that prediction — in particular an
    unmodelled acceleration appears as a residual frequency ramp and is
    re-estimated.  Residual values are not smoothed or trend-removed.

    Returns the reconstructed frequency at ``frame_times``, on the original
    physical frequency axis (``f_pred(frame_times) + f_residual``).
    """
    x = np.asarray(signal, dtype=np.float64)
    times = np.asarray(sample_times, dtype=np.float64)
    centres = np.asarray(frame_times, dtype=np.float64)
    theta = np.asarray(params, dtype=np.float64)
    if x.ndim != 1 or times.shape != x.shape or times.size < 2:
        raise ValueError("signal and sample_times must be matching 1-D arrays")
    if not (0 < hop <= frame_len <= x.size):
        raise ValueError("require 0 < hop <= frame_len <= signal length")
    if not (band_hz > 0.0):
        raise ValueError("band_hz must be positive")

    f_pred_samples = doppler_frequency(times, theta[0], theta[1], theta[2], theta[3], c)
    dt = float(np.median(np.diff(times)))
    if not np.isfinite(dt) or dt <= 0.0:
        raise ValueError("sample_times must be strictly increasing")
    phase = np.zeros_like(times)
    phase[1:] = 2.0 * np.pi * np.cumsum(0.5 * (f_pred_samples[1:] + f_pred_samples[:-1]) * dt)
    demodulated = x * np.exp(-1j * phase)

    window = np.hanning(frame_len)
    n_frames = 1 + (demodulated.size - frame_len) // hop
    if n_frames < B1_MIN_FRAMES:
        raise ValueError("too few frames for de-chirped re-extraction")
    indices = np.arange(n_frames) * hop
    frames = demodulated[indices[:, None] + np.arange(frame_len)[None, :]]
    spectra = np.fft.fftshift(np.fft.fft(frames * window[None, :], axis=1), axes=1)
    magnitude = np.abs(spectra)
    frequencies = np.fft.fftshift(np.fft.fftfreq(frame_len, 1.0 / fs))
    mask = np.abs(frequencies) <= band_hz
    if int(np.count_nonzero(mask)) < 5:
        raise ValueError("demodulation band contains too few DFT bins")
    band = magnitude[:, mask]
    peak_rel = np.argmax(band, axis=1)
    peak = np.where(mask)[0][peak_rel]
    log_magnitude = np.log(magnitude + 1e-12)
    rows = np.arange(n_frames)
    y_lo = log_magnitude[rows, peak - 1]
    y_centre = log_magnitude[rows, peak]
    y_hi = log_magnitude[rows, peak + 1]
    denominator = y_lo - 2.0 * y_centre + y_hi
    delta = np.zeros(n_frames, dtype=np.float64)
    usable = np.abs(denominator) > 1e-12
    delta[usable] = 0.5 * (y_lo[usable] - y_hi[usable]) / denominator[usable]
    delta = np.clip(delta, -0.5, 0.5)
    bin_hz = fs / frame_len
    residual_frequency = frequencies[peak] + delta * bin_hz

    centre_times = float(times[0]) + (indices + 0.5 * frame_len) / float(fs)
    f_pred_centres = model_prediction(centres, theta, c)
    residual_at_centres = np.interp(centres, centre_times, residual_frequency)
    reconstructed = f_pred_centres + residual_at_centres
    if not np.all(np.isfinite(reconstructed)):
        raise ValueError("de-chirped reconstruction produced non-finite frequencies")
    return reconstructed


# ---------------------------------------------------------------------------
# B2 — residual pre-whitening
# ---------------------------------------------------------------------------

def estimate_ar_coefficients(
    residual_sequences: Sequence[np.ndarray], order: int = B2_AR_ORDER
) -> np.ndarray:
    """Yule-Walker AR(``order``) coefficients from correct-model residuals.

    The sequences should be zero-mean and unit-scale (the caller normalizes by
    each trial's ``sigma_f``) so the pooled autocovariance is comparable across
    trials.  A singular system returns zero coefficients (whitening disabled),
    which is reported by the caller instead of silently inventing a model.
    """
    if order < 1:
        raise ValueError("order must be >= 1")
    sequences = [np.asarray(seq, dtype=np.float64) for seq in residual_sequences]
    if not sequences:
        return np.zeros(order, dtype=np.float64)
    autocovariance = np.zeros(order + 1, dtype=np.float64)
    total = 0.0
    for sequence in sequences:
        values = sequence - float(np.mean(sequence))
        n = values.size
        if n <= order:
            continue
        for lag in range(order + 1):
            autocovariance[lag] += float(np.dot(values[: n - lag], values[lag:]))
        total += float(n)
    if total <= 0.0 or autocovariance[0] <= 0.0:
        return np.zeros(order, dtype=np.float64)
    autocovariance /= total
    matrix = np.empty((order, order), dtype=np.float64)
    for i in range(order):
        for j in range(order):
            matrix[i, j] = autocovariance[abs(i - j)]
    rhs = autocovariance[1 : order + 1]
    try:
        coefficients = np.linalg.solve(matrix, rhs)
    except np.linalg.LinAlgError:
        return np.zeros(order, dtype=np.float64)
    if not np.all(np.isfinite(coefficients)):
        return np.zeros(order, dtype=np.float64)
    return np.asarray(coefficients, dtype=np.float64)


def whiten_residuals(residuals: np.ndarray, coefficients: np.ndarray) -> np.ndarray:
    """Apply the AR(p) whitening filter ``w[t] = r[t] - sum_i phi_i r[t-i]``."""
    values = np.asarray(residuals, dtype=np.float64)
    phi = np.asarray(coefficients, dtype=np.float64)
    order = phi.size
    if values.size <= order + 5:
        raise ValueError("too few residuals for the declared AR order")
    if not np.any(phi):
        return values.copy()
    innovations = np.empty(values.size - order, dtype=np.float64)
    for index in range(order, values.size):
        innovations[index - order] = values[index] - float(
            np.dot(phi, values[index - order : index][::-1])
        )
    return innovations


def _provisional_autocorrelation_thresholds(base_thresholds: Mapping[str, object]) -> dict:
    return {
        "ljung_box_statistic_max": float("inf"),
        "max_abs_acf_max": float("inf"),
        "decided_by": base_thresholds.get("decided_by", "ljung_box_statistic"),
    }


def calibrate_whitened_thresholds(
    residual_sequences: Sequence[np.ndarray],
    coefficients: np.ndarray,
    *,
    margin: float = CALIBRATION_MARGIN,
    base_thresholds: Optional[Mapping[str, object]] = None,
) -> dict:
    """Calibrate the whitened Ljung-Box null from correct-model residuals.

    Threshold = max(calibration statistic) * margin, following the frozen
    adequacy protocol's declared calibration rule.  The frozen adequacy
    thresholds themselves are not modified; this is a candidate-specific
    effective threshold recorded in the artifact.
    """
    base = dict(base_thresholds or PROTOCOL["tests"]["autocorrelation"])
    provisional = _provisional_autocorrelation_thresholds(base)
    statistics: list[float] = []
    acf_values: list[float] = []
    for sequence in residual_sequences:
        whitened = whiten_residuals(sequence, coefficients)
        result = autocorrelation_test(whitened, provisional, float(PROTOCOL["decision"]["margin_fraction"]))
        metrics = result.get("metrics") or {}
        if "ljung_box_statistic" in metrics:
            statistics.append(float(metrics["ljung_box_statistic"]))
            acf_values.append(float(metrics["max_abs_acf"]))
    if not statistics:
        return {
            "ljung_box_statistic_max": float(base["ljung_box_statistic_max"]),
            "max_abs_acf_max": float(base["max_abs_acf_max"]),
            "decided_by": base.get("decided_by", "ljung_box_statistic"),
            "n_calibration": 0,
            "calibration": "frozen_fallback",
        }
    return {
        "ljung_box_statistic_max": float(max(statistics) * float(margin)),
        "max_abs_acf_max": float(max(acf_values) * float(margin)),
        "decided_by": base.get("decided_by", "ljung_box_statistic"),
        "n_calibration": len(statistics),
        "calibration": "correct_model_max_times_margin",
        "margin": float(margin),
        "whitened_median_lb": float(np.median(statistics)),
    }


def whitened_autocorrelation_test(
    residuals: np.ndarray,
    coefficients: np.ndarray,
    thresholds: Mapping[str, object],
) -> dict:
    """Run the frozen Ljung-Box test on AR-whitened residuals."""
    whitened = whiten_residuals(residuals, coefficients)
    return autocorrelation_test(
        whitened,
        dict(thresholds),
        float(PROTOCOL["decision"]["margin_fraction"]),
    )


# ---------------------------------------------------------------------------
# B3 — geometry-conditioned calibration
# ---------------------------------------------------------------------------

def _bin_index(value: float, edges: Sequence[float]) -> int:
    index = int(np.digitize([float(value)], list(edges))[0] - 1)
    return int(np.clip(index, 0, len(edges) - 2))


@dataclass(frozen=True)
class B3Calibration:
    """Conditional adequacy thresholds keyed by runtime-observable bins."""

    chirp_edges: tuple[float, ...]
    snr_edges: tuple[float, ...]
    cells: dict[tuple[int, int], dict]
    row_fallback: dict[int, dict]
    global_fallback: dict
    margin: float
    min_cell: int
    n_records: int
    selection_inputs: tuple[str, ...] = B3_SELECTION_INPUTS

    @classmethod
    def fit(
        cls,
        records: Sequence[Mapping[str, object]],
        *,
        margin: float = CALIBRATION_MARGIN,
        min_cell: int = B3_MIN_CALIBRATION_CELL,
    ) -> "B3Calibration":
        """Calibrate from correct-model records: ``{observables, adequacy}``."""
        cells_raw: dict[tuple[int, int], list[dict]] = {}
        rows_raw: dict[int, list[dict]] = {}
        everything: list[dict] = []
        for record in records:
            observables = record["observables"]
            adequacy_block = record["adequacy"]
            assert_runtime_observable_inputs(
                {key: observables[key] for key in B3_SELECTION_INPUTS}
            )
            stats = _adequacy_statistics(adequacy_block)
            chirp_bin = _bin_index(float(observables["estimated_chirp_rate_hz_s"]), B3_CHIRP_EDGES_HZ_S)
            snr_bin = _bin_index(float(observables["estimated_snr_db"]), B3_SNR_EDGES_DB)
            entry = {"chirp_bin": chirp_bin, "snr_bin": snr_bin, **stats}
            cells_raw.setdefault((chirp_bin, snr_bin), []).append(entry)
            rows_raw.setdefault(chirp_bin, []).append(entry)
            everything.append(entry)
        cells = {key: _cell_thresholds(entries, margin) for key, entries in cells_raw.items()}
        row_fallback = {key: _cell_thresholds(entries, margin) for key, entries in rows_raw.items()}
        global_fallback = _cell_thresholds(everything, margin)
        return cls(
            chirp_edges=B3_CHIRP_EDGES_HZ_S,
            snr_edges=B3_SNR_EDGES_DB,
            cells=cells,
            row_fallback=row_fallback,
            global_fallback=global_fallback,
            margin=float(margin),
            min_cell=int(min_cell),
            n_records=len(everything),
        )

    def thresholds_for(self, observables: Mapping[str, float]) -> tuple[dict, dict]:
        """Select the calibration cell from runtime observables only."""
        selection = {key: observables[key] for key in self.selection_inputs}
        assertion = assert_runtime_observable_inputs(selection)
        chirp_bin = _bin_index(float(selection["estimated_chirp_rate_hz_s"]), self.chirp_edges)
        snr_bin = _bin_index(float(selection["estimated_snr_db"]), self.snr_edges)
        cell = self.cells.get((chirp_bin, snr_bin))
        if cell is not None and cell["n_calibration"] >= self.min_cell:
            source = "cell"
        else:
            cell = self.row_fallback.get(chirp_bin)
            source = "chirp_row"
            if cell is None or cell["n_calibration"] < self.min_cell:
                cell = self.global_fallback
                source = "global"
                if cell["n_calibration"] < self.min_cell:
                    source = "frozen_fallback"
        thresholds = _b3_threshold_dict(cell, source)
        metadata = {
            "runtime_observables": {
                key: float(selection[key]) for key in self.selection_inputs
            },
            "chirp_bin": chirp_bin,
            "snr_bin": snr_bin,
            "chirp_edges_hz_s": list(self.chirp_edges),
            "snr_edges_db": list(self.snr_edges),
            "calibration_source": source,
            "n_calibration": int(cell["n_calibration"]),
            "margin": self.margin,
            "min_cell": self.min_cell,
            "selection_inputs": list(self.selection_inputs),
            "assertion": assertion,
            "truth_fields_used": [],
        }
        return thresholds, metadata

    def to_artifact(self) -> dict:
        return {
            "chirp_edges_hz_s": list(self.chirp_edges),
            "snr_edges_db": list(self.snr_edges),
            "margin": self.margin,
            "min_cell": self.min_cell,
            "n_records": self.n_records,
            "selection_inputs": list(self.selection_inputs),
            "cells": [
                {
                    "chirp_bin": chirp_bin,
                    "snr_bin": snr_bin,
                    **thresholds,
                }
                for (chirp_bin, snr_bin), thresholds in sorted(self.cells.items())
            ],
            "row_fallback": [
                {"chirp_bin": chirp_bin, **thresholds}
                for chirp_bin, thresholds in sorted(self.row_fallback.items())
            ],
            "global_fallback": self.global_fallback,
        }


def _adequacy_statistics(adequacy_block: Mapping[str, object]) -> dict:
    tests = adequacy_block["tests"]
    autocorrelation = tests["autocorrelation"]["metrics"]
    time_structure = tests["time_structure"]["metrics"]
    block = tests["block_prediction"]["metrics"]
    return {
        "ljung_box_statistic": float(autocorrelation["ljung_box_statistic"]),
        "max_abs_acf": float(autocorrelation["max_abs_acf"]),
        "abs_corr_time": abs(float(time_structure["corr_time"])),
        "abs_quadratic": abs(float(time_structure["quadratic_coefficient_over_sigma_f"])),
        "abs_phase_correlation": float(time_structure["max_abs_phase_correlation"]),
        "median_normalized_rmse": float(block["median_normalized_rmse"]),
    }


def _cell_thresholds(entries: Sequence[Mapping[str, float]], margin: float) -> dict:
    if not entries:
        return {
            "n_calibration": 0,
            "ljung_box_statistic_max": float(PROTOCOL["tests"]["autocorrelation"]["ljung_box_statistic_max"]),
            "max_abs_acf_max": float(PROTOCOL["tests"]["autocorrelation"]["max_abs_acf_max"]),
            "abs_corr_time_max": float(PROTOCOL["tests"]["time_structure"]["abs_corr_time_max"]),
            "abs_quadratic_coefficient_max": float(
                PROTOCOL["tests"]["time_structure"]["abs_quadratic_coefficient_max"]
            ),
            "abs_phase_correlation_max": float(
                PROTOCOL["tests"]["time_structure"]["abs_phase_correlation_max"]
            ),
            "heldout_normalized_rmse_max": float(
                PROTOCOL["tests"]["block_prediction"]["heldout_normalized_rmse_max"]
            ),
        }
    return {
        "n_calibration": len(entries),
        "ljung_box_statistic_max": float(
            max(float(entry["ljung_box_statistic"]) for entry in entries) * margin
        ),
        "max_abs_acf_max": float(max(float(entry["max_abs_acf"]) for entry in entries) * margin),
        "abs_corr_time_max": float(max(float(entry["abs_corr_time"]) for entry in entries) * margin),
        "abs_quadratic_coefficient_max": float(
            max(float(entry["abs_quadratic"]) for entry in entries) * margin
        ),
        "abs_phase_correlation_max": float(
            max(float(entry["abs_phase_correlation"]) for entry in entries) * margin
        ),
        "heldout_normalized_rmse_max": float(
            max(float(entry["median_normalized_rmse"]) for entry in entries) * margin
        ),
    }


def _b3_threshold_dict(cell: Mapping[str, object], source: str) -> dict:
    return {
        "ljung_box_statistic_max": float(cell["ljung_box_statistic_max"]),
        "max_abs_acf_max": float(cell["max_abs_acf_max"]),
        "abs_corr_time_max": float(cell["abs_corr_time_max"]),
        "abs_quadratic_coefficient_max": float(cell["abs_quadratic_coefficient_max"]),
        "abs_phase_correlation_max": float(cell["abs_phase_correlation_max"]),
        "heldout_normalized_rmse_max": float(cell["heldout_normalized_rmse_max"]),
        "calibration_source": source,
        "n_calibration": int(cell["n_calibration"]),
    }


def b3_protocol_variant(thresholds: Mapping[str, object]) -> dict:
    """Deep-copy the frozen adequacy protocol with B3's effective thresholds.

    The module-level frozen protocol object is never mutated; a candidate-local
    copy is returned and the change is recorded in the artifact.
    """
    protocol = copy.deepcopy(PROTOCOL)
    autocorrelation = protocol["tests"]["autocorrelation"]
    autocorrelation["ljung_box_statistic_max"] = float(thresholds["ljung_box_statistic_max"])
    autocorrelation["max_abs_acf_max"] = float(thresholds["max_abs_acf_max"])
    time_structure = protocol["tests"]["time_structure"]
    time_structure["abs_corr_time_max"] = float(thresholds["abs_corr_time_max"])
    time_structure["abs_quadratic_coefficient_max"] = float(
        thresholds["abs_quadratic_coefficient_max"]
    )
    time_structure["abs_phase_correlation_max"] = float(
        thresholds["abs_phase_correlation_max"]
    )
    protocol["tests"]["block_prediction"]["heldout_normalized_rmse_max"] = float(
        thresholds["heldout_normalized_rmse_max"]
    )
    return protocol


# ---------------------------------------------------------------------------
# Adequacy recombination (B2) and decision mapping
# ---------------------------------------------------------------------------

def _epistemic_decision(
    optimization_status: str,
    model_adequacy_status: str,
    identifiability_status: str,
    tests: Mapping[str, Mapping[str, object]],
) -> tuple[str, list[str]]:
    """Mirror of ``adequacy._epistemic_decision`` (frozen precedence, ADR 0015 §5)."""
    if optimization_status != "converged":
        return "undetermined", [f"optimization_{optimization_status}"]
    if model_adequacy_status == "discrepancy":
        reasons = [
            str(result["reason"])
            for name, result in tests.items()
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


def recompute_adequacy_with_test(
    baseline: Mapping[str, object],
    test_name: str,
    replacement: Mapping[str, object],
    optimization_status: str,
) -> dict:
    """Return a baseline adequacy block with one test replaced and re-decided.

    The frozen precedence of ``adequacy.evaluate_adequacy`` is re-applied so a
    replaced test cannot silently bypass the decision graph.
    """
    block = copy.deepcopy(dict(baseline))
    tests = block["tests"]
    if test_name not in tests:
        raise KeyError(f"unknown adequacy test {test_name!r}")
    tests[test_name] = copy.deepcopy(dict(replacement))

    distribution = tests["standardized_residuals"]["status"]
    structure = [
        tests["autocorrelation"]["status"],
        tests["time_structure"]["status"],
        tests["block_prediction"]["status"],
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

    identifiability_status = str(tests["degeneracy"]["status"])
    reason_codes: list[str] = []
    for name, result in tests.items():
        if name == "degeneracy":
            continue
        if result["status"] != "pass" and result.get("reason"):
            reason_codes.append(str(result["reason"]))
    if identifiability_status == "not_separately_identifiable":
        reason_codes.append("clock_equivalence")
    elif identifiability_status == "insufficient_evidence":
        reason_codes.append("identifiability_insufficient")
    decision, decision_reasons = _epistemic_decision(
        optimization_status, model_adequacy_status, identifiability_status, tests
    )
    reason_codes.extend(decision_reasons)
    seen: set[str] = set()
    reason_codes = [code for code in reason_codes if not (code in seen or seen.add(code))]

    block["model_adequacy_status"] = model_adequacy_status
    block["identifiability_status"] = identifiability_status
    block["epistemic_decision"] = decision
    block["reason_codes"] = reason_codes
    tests["degeneracy"]["conditional_claim_supported"] = bool(
        optimization_status == "converged"
        and tests["degeneracy"].get("nominal_gate_pass", False)
        and model_adequacy_status == "adequate"
    )
    return block


def decision_from_adequacy(adequacy_block: Mapping[str, object]) -> str:
    """Map the *measurement-model adequacy* status to the artifact decision.

    ``accept`` means the model is adequate for this observation; ``reject`` means
    a model discrepancy was detected; ``undetermined`` covers insufficient or
    indeterminate evidence.  This is deliberately *not* the physical epistemic
    decision (which additionally requires an absolute clock and is recorded
    separately in ``adequacy.epistemic_decision``), and it is *not* the C1 claim
    gate (recorded in ``claim_statuses``).  The repair compares measurement-model
    adequacy; the C1 L1/L2/L3 gate is never bypassed by this mapping.
    """
    status = adequacy_block.get("model_adequacy_status")
    if status == "adequate":
        return "accept"
    if status == "discrepancy":
        return "reject"
    return "undetermined"
