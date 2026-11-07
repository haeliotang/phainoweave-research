"""ADR 0023 B/C — B1 self-confirmation diagnostics and outcome taxonomy.

Development-grid only.  The sealed `pr4e-c2c-v1` grid is never opened: no import
path, seed or file from it is used here.  B0-B3 implementations are imported
read-only from the (to-be-frozen) repair modules; this module only calls them.

Diagnostics:
1. wrong-model de-chirp: B1 with deliberately biased prediction models
   (v+20%, b+30%) and the constant-velocity (acceleration-omitted) model on
   correct-CV high-chirp and acceleration observations;
2. time-block holdout: estimate/de-chirp from a subset of the window and test
   residuals/adequacy on held-out blocks;
3. parameter stability vs truth: B0 vs B1 parameter errors across geometry,
   noise and observation-window perturbations, paired with intervals;
4. outcome taxonomy per candidate (correct-model coverage/false-rejection/
   abstention; acceleration detected/undetermined/false-supported; null
   promotion), never pooled;
5. B3 per-chirp-bin power and the unverified-SNR-branch declaration.
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
from typing import Mapping, Optional

import numpy as np

from . import experiment_repair
from .adequacy import evaluate_adequacy
from .experiment import BASE, F_MAX, F_MIN, FRAME_LEN, HOP
from .features import estimate_if_track
from .fit_hardened import fit_hardened
from .repair_candidates import (
    B1_DEMOD_BAND_HZ,
    B1_FRAME_LEN,
    B1_HOP,
    B3_CHIRP_EDGES_HZ_S,
    B3_SNR_EDGES_DB,
    dechirped_track,
    decision_from_adequacy,
    model_prediction,
)
from .synthetic import Scenario, generate

ARTIFACT_NAME = "c2-repair-selfcheck"
SELFCHECK_VERSION = "1.0.0"
SELFCHECK_SEED_BASE = 92_000_000  # new base >= 92M, disjoint from dev (90/91M)
SELFCHECK_SEED_FORMULA = "SELFCHECK_SEED_BASE + 1000*cell_index + trial"

HIGH_CHIRP_GEOMETRIES_M = (150.0, 250.0, 400.0, 700.0)
HIGH_CHIRP_SPEED_M_S = 250.0
HIGH_CHIRP_SNR_DB = 20.0
HIGH_CHIRP_TRIALS = 8
ACCEL_GEOMETRIES_M = (600.0, 3000.0)
ACCEL_SPEEDS_M_S = (150.0, 250.0)
ACCEL_LEVELS_M_S2 = (0.15, 0.30, 0.50)
ACCEL_TRIALS = 4
TIME_BLOCK_CELLS_M = (150.0, 250.0, 400.0, 700.0)
TIME_BLOCK_TRIALS = 6
TIME_BLOCK_USED_FRACTION = 0.60
WINDOW_PERTURBATION_CELLS_M = (400.0, 2200.0)
WINDOW_PERTURBATION_DURATIONS_S = (40.0, 80.0)
WINDOW_PERTURBATION_TRIALS = 4
BIASED_MODELS = ("correct_model", "speed_plus_20pct", "closest_approach_plus_30pct")
MODEL_BIAS_DESCRIPTIONS = {
    "correct_model": "B0 fitted constant-velocity model (acceleration omitted by construction)",
    "speed_plus_20pct": "prediction model with speed multiplied by 1.20",
    "closest_approach_plus_30pct": "prediction model with closest approach multiplied by 1.30",
}
CANDIDATES = ("B0", "B1", "B2", "B3")


# ---------------------------------------------------------------------------
# Small helpers
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


def _acf1(values: np.ndarray) -> Optional[float]:
    values = np.asarray(values, dtype=np.float64)
    if values.size < 3:
        return None
    return float(np.corrcoef(values[:-1], values[1:])[0, 1])


def wilson_interval(k: int, n: int, z: float = 1.96) -> list[Optional[float]]:
    if n <= 0:
        return [None, None]
    p = k / n
    denominator = 1.0 + z * z / n
    centre = (p + z * z / (2.0 * n)) / denominator
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denominator
    return [max(0.0, centre - half), min(1.0, centre + half)]


def rate_block(k: int, n: int) -> dict:
    block = {
        "k": int(k),
        "n": int(n),
        "rate": (k / n) if n else None,
        "wilson95": wilson_interval(k, n),
    }
    if k == 0 and n > 0:
        block["zero_event_upper95"] = 1.0 - 0.05 ** (1.0 / n)
    return block


def _params_to_array(params) -> np.ndarray:
    if isinstance(params, Mapping):
        return np.array([float(params["f0"]), float(params["v"]), float(params["t0"]), float(params["b"])])
    return np.asarray(params, dtype=np.float64)[:4].copy()


def biased_model_params(params, model: str) -> np.ndarray:
    theta = _params_to_array(params)
    if model == "correct_model":
        return theta
    if model == "speed_plus_20pct":
        theta[1] *= 1.20
        return theta
    if model == "closest_approach_plus_30pct":
        theta[3] *= 1.30
        return theta
    raise ValueError(f"unknown biased model {model!r}")


def _scenario(geometry: float, speed: float, snr: float, seed: int, *, accel: float = 0.0, duration: float = BASE.duration) -> Scenario:
    return replace(
        BASE,
        b=float(geometry),
        v=float(speed),
        snr_db=float(snr),
        accel=float(accel),
        duration=float(duration),
        seed=int(seed),
    )


def _b1_with_model(observation, frame_times: np.ndarray, prediction_params: np.ndarray, c: float, fs: float) -> dict:
    """B1 de-chirp with a given prediction model, then refit and run adequacy."""
    try:
        reconstructed = dechirped_track(
            observation.signal,
            observation.t,
            prediction_params,
            c,
            frame_times,
            fs=fs,
            band_hz=B1_DEMOD_BAND_HZ,
            frame_len=B1_FRAME_LEN,
            hop=B1_HOP,
        )
        hardened = fit_hardened(frame_times, reconstructed, c=c)
        params = np.array([hardened.f0, hardened.v, hardened.t0, hardened.b], dtype=np.float64)
        predicted = model_prediction(frame_times, params, c)
        residuals = np.asarray(reconstructed, dtype=np.float64) - predicted
        adequacy = evaluate_adequacy(
            frame_times,
            reconstructed,
            params,
            hardened.sigma_f_hz,
            hardened.optimization_status,
            c=c,
        )
        return {
            "status": adequacy["model_adequacy_status"],
            "decision": decision_from_adequacy(adequacy),
            "residual_rms_hz": float(np.sqrt(np.mean(residuals**2))),
            "residual_acf1": _acf1(residuals),
            "ljung_box": adequacy["tests"]["autocorrelation"]["metrics"].get("ljung_box_statistic"),
            "sigma_f_hz": float(hardened.sigma_f_hz),
            "params": {
                "f0": float(hardened.f0),
                "v": float(hardened.v),
                "t0": float(hardened.t0),
                "b": float(hardened.b),
            },
            "transform_failed": False,
        }
    except Exception as error:
        return {
            "status": "insufficient_evidence",
            "decision": "undetermined",
            "residual_rms_hz": None,
            "residual_acf1": None,
            "ljung_box": None,
            "sigma_f_hz": None,
            "params": None,
            "transform_failed": True,
            "failure": type(error).__name__,
        }


# ---------------------------------------------------------------------------
# 1. Wrong-model de-chirp
# ---------------------------------------------------------------------------

def _high_chirp_cells() -> list[dict]:
    cells = []
    index = 0
    for geometry in HIGH_CHIRP_GEOMETRIES_M:
        cells.append(
            {
                "cell_index": index,
                "cell_id": f"selfcheck_hc_b{geometry:g}_v{HIGH_CHIRP_SPEED_M_S:g}",
                "geometry_m": float(geometry),
                "speed_m_s": HIGH_CHIRP_SPEED_M_S,
                "accel": 0.0,
                "snr_db": HIGH_CHIRP_SNR_DB,
                "n_trials": HIGH_CHIRP_TRIALS,
            }
        )
        index += 1
    return cells


def _acceleration_cells() -> list[dict]:
    cells = []
    index = 100
    for geometry in ACCEL_GEOMETRIES_M:
        for speed in ACCEL_SPEEDS_M_S:
            for accel in ACCEL_LEVELS_M_S2:
                cells.append(
                    {
                        "cell_index": index,
                        "cell_id": f"selfcheck_acc_b{geometry:g}_v{speed:g}_a{accel:g}",
                        "geometry_m": float(geometry),
                        "speed_m_s": float(speed),
                        "accel": float(accel),
                        "snr_db": 20.0,
                        "n_trials": ACCEL_TRIALS,
                    }
                )
                index += 1
    return cells


def run_wrong_model_diagnostic() -> dict:
    cells = _high_chirp_cells() + _acceleration_cells()
    records = []
    for cell in cells:
        for trial in range(cell["n_trials"]):
            seed = SELFCHECK_SEED_BASE + 1000 * int(cell["cell_index"]) + trial
            scenario = _scenario(cell["geometry_m"], cell["speed_m_s"], cell["snr_db"], seed, accel=cell["accel"])
            base = experiment_repair.fit_observation(scenario)
            base_params = base["params"]
            b0_decision = decision_from_adequacy(base["adequacy"])
            b0_residuals = np.asarray(base["residuals"], dtype=np.float64)
            record = {
                "cell_id": cell["cell_id"],
                "family": "correct_cv" if cell["accel"] == 0.0 else "acceleration",
                "geometry_m": cell["geometry_m"],
                "speed_m_s": cell["speed_m_s"],
                "accel": cell["accel"],
                "trial": trial,
                "seed": seed,
                "b0": {
                    "decision": b0_decision,
                    "status": base["adequacy"]["model_adequacy_status"],
                    "residual_rms_hz": float(np.sqrt(np.mean(b0_residuals**2))),
                    "residual_acf1": _acf1(b0_residuals),
                },
                "b1_models": {},
            }
            for model in BIASED_MODELS:
                prediction = biased_model_params(base_params, model)
                b1 = _b1_with_model(base["observation"], base["track"].t, prediction, scenario.c, scenario.fs)
                record["b1_models"][model] = b1
            records.append(record)

    def aggregate(family: str, model: str) -> dict:
        subset = [record for record in records if record["family"] == family]
        runs = [record["b1_models"][model] for record in subset]
        rejections = sum(1 for run in runs if run["decision"] == "reject")
        rms_values = [run["residual_rms_hz"] for run in runs if run["residual_rms_hz"] is not None]
        acf_values = [run["residual_acf1"] for run in runs if run["residual_acf1"] is not None]
        return {
            "model": model,
            "description": MODEL_BIAS_DESCRIPTIONS[model],
            "n": len(subset),
            "rejections": rejections,
            "decision_counts": _counts(run["decision"] for run in runs),
            "status_counts": _counts(run["status"] for run in runs),
            "transform_failures": sum(1 for run in runs if run["transform_failed"]),
            "median_residual_rms_hz": float(np.median(rms_values)) if rms_values else None,
            "median_residual_acf1": float(np.median(acf_values)) if acf_values else None,
            "rejection_rate": (rejections / len(subset)) if subset else None,
            "rejection_rate_interval": wilson_interval(rejections, len(subset)),
        }

    correct_cv = [record for record in records if record["family"] == "correct_cv"]
    b0_high_chirp = {
        "model": "B0",
        "n": len(correct_cv),
        "rejections": sum(1 for record in correct_cv if record["b0"]["decision"] == "reject"),
        "decision_counts": _counts(record["b0"]["decision"] for record in correct_cv),
        "median_residual_rms_hz": float(np.median([record["b0"]["residual_rms_hz"] for record in correct_cv])),
        "median_residual_acf1": float(np.median([record["b0"]["residual_acf1"] for record in correct_cv])),
    }
    b0_high_chirp["rejection_rate"] = b0_high_chirp["rejections"] / max(1, b0_high_chirp["n"])
    correct_model_b1 = aggregate("correct_cv", "correct_model")
    wrong_models = [aggregate("correct_cv", model) for model in BIASED_MODELS if model != "correct_model"]
    # self-confirmation signal: a wrong model that keeps the rejection rate near the
    # correct-model/ B0 level and low residuals is evidence of self-confirmation.
    correct_rate = correct_model_b1["rejection_rate"]
    correct_rms = correct_model_b1["median_residual_rms_hz"]
    b0_rate = b0_high_chirp["rejection_rate"]
    flags = []
    for wrong in wrong_models:
        rate = wrong["rejection_rate"]
        wrong_rms = wrong["median_residual_rms_hz"]
        rms_ratio = (wrong_rms / correct_rms) if wrong_rms is not None and correct_rms else None
        if rate is not None and correct_rate is not None:
            beautiful_residuals = rms_ratio is not None and rms_ratio <= 1.5
            absorbs = b0_rate is not None and b0_rate > 0.2 and rate <= max(0.2, 0.5 * b0_rate)
            if absorbs and beautiful_residuals:
                flags.append(
                    {
                        "model": wrong["model"],
                        "wrong_model_rejection_rate": rate,
                        "correct_model_rejection_rate": correct_rate,
                        "b0_rejection_rate": b0_rate,
                        "residual_rms_ratio_vs_correct_model": rms_ratio,
                        "interpretation": "wrong model removes most B0 rejections while keeping residuals near the correct model -> self-confirmation risk",
                    }
                )
    acceleration = [record for record in records if record["family"] == "acceleration"]
    acceleration_b0 = {
        "n": len(acceleration),
        "detections": sum(1 for record in acceleration if record["b0"]["decision"] == "reject"),
        "detection_rate": (
            sum(1 for record in acceleration if record["b0"]["decision"] == "reject") / max(1, len(acceleration))
        ),
    }
    acceleration_models = [aggregate("acceleration", model) for model in BIASED_MODELS]
    correct_accel_rate = next(
        (entry["rejection_rate"] for entry in acceleration_models if entry["model"] == "correct_model"), None
    )
    for entry in acceleration_models:
        entry["detection_loss_vs_correct_model"] = (
            None
            if entry["rejection_rate"] is None or correct_accel_rate is None
            else correct_accel_rate - entry["rejection_rate"]
        )
    # wrong-model de-chirp must not hide real acceleration: detection must stay high
    acceleration_hidden = [
        entry
        for entry in acceleration_models
        if entry["model"] != "correct_model"
        and entry["rejection_rate"] is not None
        and entry["rejection_rate"] < 0.8
    ]
    verdict = (
        "self_confirmation_risk_flagged"
        if flags
        else ("wrong_models_do_not_reproduce_correct_model_behaviour")
    )
    return _jsonable(
        {
            "correct_cv": {
                "b0": b0_high_chirp,
                "b1": [correct_model_b1] + wrong_models,
                "residual_rms_ratio_vs_correct_model": {
                    wrong["model"]: (
                        (wrong["median_residual_rms_hz"] / correct_rms)
                        if wrong["median_residual_rms_hz"] is not None and correct_rms
                        else None
                    )
                    for wrong in wrong_models
                },
                "self_confirmation_flags": flags,
                "note": (
                    "All prediction models are constant-velocity (acceleration omitted by construction). "
                    "A wrong prediction model that also removes rejections and yields low residuals is the "
                    "self-confirmation risk ADR 0023 B.1 asks about."
                ),
            },
            "acceleration": {
                "b0": acceleration_b0,
                "b1": acceleration_models,
                "acceleration_hidden_by_wrong_model": acceleration_hidden,
                "note": (
                    "B1 de-chirps a constant-velocity prediction and re-fits on the residual ramp; real "
                    "acceleration should remain detectable (and must not be hidden by a wrong prediction)."
                ),
            },
            "verdict": verdict,
            "verdict_statement": (
                f"B1 with wrong prediction models keeps {[entry['rejection_rate'] for entry in wrong_models]} correct-CV "
                f"rejection rates vs {correct_rate} for the correct model and {b0_rate} for B0; "
                f"acceleration detection by model: "
                f"{ {entry['model']: entry['rejection_rate'] for entry in acceleration_models} }."
            ),
        }
    )


# ---------------------------------------------------------------------------
# 2. Time-block holdout
# ---------------------------------------------------------------------------

def run_time_block_holdout() -> dict:
    records = []
    for cell_index, geometry in enumerate(TIME_BLOCK_CELLS_M):
        for trial in range(TIME_BLOCK_TRIALS):
            seed = SELFCHECK_SEED_BASE + 20_000 + 1000 * cell_index + trial
            scenario = _scenario(geometry, HIGH_CHIRP_SPEED_M_S, HIGH_CHIRP_SNR_DB, seed)
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
            times = np.asarray(track.t, dtype=np.float64)
            frequencies = np.asarray(track.f, dtype=np.float64)
            n = times.size
            split = max(int(TIME_BLOCK_USED_FRACTION * n), 10)
            split = min(split, n - 10)
            used = slice(0, split)
            held = slice(split, n)
            # B0 view
            base = fit_hardened(times, frequencies, c=scenario.c)
            base_params = np.array([base.f0, base.v, base.t0, base.b], dtype=np.float64)
            base_pred = model_prediction(times, base_params, scenario.c)
            base_residuals = frequencies - base_pred
            # De-chirp using a model estimated on the used block only.
            used_fit = fit_hardened(times[used], frequencies[used], c=scenario.c)
            used_params = np.array([used_fit.f0, used_fit.v, used_fit.t0, used_fit.b], dtype=np.float64)
            try:
                reconstructed = dechirped_track(
                    observation.signal,
                    observation.t,
                    used_params,
                    scenario.c,
                    times,
                    fs=scenario.fs,
                    band_hz=B1_DEMOD_BAND_HZ,
                    frame_len=B1_FRAME_LEN,
                    hop=B1_HOP,
                )
                b1_full_fit = fit_hardened(times, reconstructed, c=scenario.c)
                b1_params = np.array([b1_full_fit.f0, b1_full_fit.v, b1_full_fit.t0, b1_full_fit.b], dtype=np.float64)
                b1_pred = model_prediction(times, b1_params, scenario.c)
                b1_residuals = np.asarray(reconstructed, dtype=np.float64) - b1_pred
                adequacy = evaluate_adequacy(
                    times,
                    reconstructed,
                    b1_params,
                    b1_full_fit.sigma_f_hz,
                    b1_full_fit.optimization_status,
                    c=scenario.c,
                )
                # Held-out-block adequacy with the used-block model (no refit on held-out).
                hold_adequacy = evaluate_adequacy(
                    times[held],
                    reconstructed[held],
                    used_params,
                    used_fit.sigma_f_hz,
                    used_fit.optimization_status,
                    c=scenario.c,
                )
                failed = False
            except Exception as error:
                reconstructed = frequencies
                b1_residuals = base_residuals
                adequacy = {"model_adequacy_status": "insufficient_evidence", "tests": {}}
                hold_adequacy = {"model_adequacy_status": "insufficient_evidence", "tests": {}}
                failed = True
            def block_rms(values: np.ndarray, sl: slice) -> float:
                return float(np.sqrt(np.mean(np.asarray(values)[sl] ** 2)))
            def block_acf1(values: np.ndarray, sl: slice) -> Optional[float]:
                return _acf1(np.asarray(values)[sl])
            records.append(
                {
                    "geometry_m": geometry,
                    "trial": trial,
                    "seed": seed,
                    "n_frames": int(n),
                    "used_frames": int(split),
                    "held_out_frames": int(n - split),
                    "transform_failed": failed,
                    "b0": {
                        "decision": decision_from_adequacy(
                            evaluate_adequacy(
                                times,
                                frequencies,
                                base_params,
                                base.sigma_f_hz,
                                base.optimization_status,
                                c=scenario.c,
                            )
                        ),
                        "used_block_rms_hz": block_rms(base_residuals, used),
                        "held_out_block_rms_hz": block_rms(base_residuals, held),
                        "used_block_acf1": block_acf1(base_residuals, used),
                        "held_out_block_acf1": block_acf1(base_residuals, held),
                    },
                    "b1": {
                        "decision": decision_from_adequacy(adequacy),
                        "status": adequacy["model_adequacy_status"],
                        "held_out_block_decision": decision_from_adequacy(hold_adequacy),
                        "held_out_block_status": hold_adequacy["model_adequacy_status"],
                        "used_block_rms_hz": block_rms(b1_residuals, used),
                        "held_out_block_rms_hz": block_rms(b1_residuals, held),
                        "used_block_acf1": block_acf1(b1_residuals, used),
                        "held_out_block_acf1": block_acf1(b1_residuals, held),
                    },
                }
            )

    def ratio(values, key):
        return float(np.median([record[key] for record in values])) if values else None

    b1_records = [record for record in records if not record["transform_failed"]]
    used_rms = ratio([record["b1"]["used_block_rms_hz"] for record in b1_records], 0) if False else (
        float(np.median([record["b1"]["used_block_rms_hz"] for record in b1_records])) if b1_records else None
    )
    held_rms = float(np.median([record["b1"]["held_out_block_rms_hz"] for record in b1_records])) if b1_records else None
    b0_used = float(np.median([record["b0"]["used_block_rms_hz"] for record in records])) if records else None
    b0_held = float(np.median([record["b0"]["held_out_block_rms_hz"] for record in records])) if records else None
    used_improvement = (b0_used / used_rms - 1.0) if b0_used and used_rms else None
    held_improvement = (b0_held / held_rms - 1.0) if b0_held and held_rms else None
    improvement_only_in_fitted_blocks = bool(
        used_improvement is not None
        and held_improvement is not None
        and used_improvement > 0.2
        and held_improvement < 0.05
    )
    return _jsonable(
        {
            "design": {
                "used_fraction": TIME_BLOCK_USED_FRACTION,
                "cells_m": list(TIME_BLOCK_CELLS_M),
                "trials_per_cell": TIME_BLOCK_TRIALS,
                "seed_base": SELFCHECK_SEED_BASE,
                "dechirp_parameters_estimated_on_used_block_only": True,
            },
            "records": records,
            "summary": {
                "n": len(records),
                "transform_failures": sum(1 for record in records if record["transform_failed"]),
                "median_b0_used_block_rms_hz": b0_used,
                "median_b0_held_out_block_rms_hz": b0_held,
                "median_b1_used_block_rms_hz": used_rms,
                "median_b1_held_out_block_rms_hz": held_rms,
                "used_block_improvement_fraction": used_improvement,
                "held_out_block_improvement_fraction": held_improvement,
                "improvement_only_in_fitted_blocks": improvement_only_in_fitted_blocks,
                "b1_full_decision_counts": _counts(record["b1"]["decision"] for record in records),
                "b1_held_out_block_decision_counts": _counts(record["b1"]["held_out_block_decision"] for record in records),
            },
            "verdict": (
                "improvement_only_in_fitted_blocks"
                if improvement_only_in_fitted_blocks
                else "improvement_persists_out_of_block_or_no_used_block_improvement"
            ),
        }
    )


# ---------------------------------------------------------------------------
# 3. Parameter stability vs truth
# ---------------------------------------------------------------------------

def _parameter_errors(params, truth: Mapping[str, float]) -> dict:
    params = _params_to_array(params)
    return {
        "f0": (float(params[0]) - float(truth["f0"])) / float(truth["f0"]),
        "v": (float(params[1]) - float(truth["v"])) / float(truth["v"]),
        "t0_abs": float(params[2]) - float(truth["t0"]),
        "b": (float(params[3]) - float(truth["b"])) / float(truth["b"]),
    }


def _bootstrap_mean_interval(values, n_boot: int = 1000, seed: int = SELFCHECK_SEED_BASE) -> dict:
    values = np.asarray(values, dtype=np.float64)
    if values.size == 0:
        return {"mean": None, "ci95": [None, None]}
    rng = np.random.default_rng(seed)
    samples = rng.choice(values, size=(n_boot, values.size), replace=True).mean(axis=1)
    return {"mean": float(np.mean(values)), "ci95": [float(np.quantile(samples, 0.025)), float(np.quantile(samples, 0.975))]}


def parameter_stability(dev_trials: list[dict]) -> dict:
    correct = [trial for trial in dev_trials if trial["mechanism"] == "correct_cv"]
    rows = []
    for trial in correct:
        truth = trial["evaluation_only"]["scenario"]
        for candidate in ("B0", "B1"):
            params = trial["candidates"][candidate]["params"]
            errors = _parameter_errors(params, truth)
            rows.append(
                {
                    "candidate": candidate,
                    "condition": trial["condition"],
                    "stratum": trial["stratum"],
                    "geometry_m": float(trial["runtime_observables"].get("estimated_chirp_rate_hz_s", 0.0)),
                    **{f"error_{key}": value for key, value in errors.items()},
                }
            )
    paired = {}
    for key in ("f0", "v", "t0_abs", "b"):
        per_trial = []
        for trial in correct:
            truth = trial["evaluation_only"]["scenario"]
            b0 = _parameter_errors(trial["candidates"]["B0"]["params"], truth)[key]
            b1 = _parameter_errors(trial["candidates"]["B1"]["params"], truth)[key]
            per_trial.append({"b0": b0, "b1": b1, "delta_b1_minus_b0": b1 - b0})
        deltas = [row["delta_b1_minus_b0"] for row in per_trial]
        b0_values = [row["b0"] for row in per_trial]
        b1_values = [row["b1"] for row in per_trial]
        paired[key] = {
            "n": len(per_trial),
            "b0_mean_error": float(np.mean(b0_values)) if b0_values else None,
            "b1_mean_error": float(np.mean(b1_values)) if b1_values else None,
            "mean_delta_b1_minus_b0": float(np.mean(deltas)) if deltas else None,
            "mean_abs_b0": float(np.mean(np.abs(b0_values))) if b0_values else None,
            "mean_abs_b1": float(np.mean(np.abs(b1_values))) if b1_values else None,
            "delta_interval": _bootstrap_mean_interval(deltas),
        }

    # Observation-window perturbation: shorter/longer windows, new seeds.
    window_rows = []
    for cell_index, geometry in enumerate(WINDOW_PERTURBATION_CELLS_M):
        for duration in WINDOW_PERTURBATION_DURATIONS_S:
            for trial in range(WINDOW_PERTURBATION_TRIALS):
                seed = SELFCHECK_SEED_BASE + 40_000 + 1000 * cell_index + 10 * int(duration) + trial
                scenario = _scenario(geometry, HIGH_CHIRP_SPEED_M_S, HIGH_CHIRP_SNR_DB, seed, duration=duration)
                base = experiment_repair.fit_observation(scenario)
                params_b0 = base["params"]
                b1 = _b1_with_model(base["observation"], base["track"].t, params_b0, scenario.c, scenario.fs)
                truth = {"f0": scenario.f0, "v": scenario.v, "t0": scenario.t0, "b": scenario.b}
                window_rows.append(
                    {
                        "geometry_m": geometry,
                        "duration_s": duration,
                        "trial": trial,
                        "b0_errors": _parameter_errors(params_b0, truth),
                        "b1_errors": _parameter_errors(b1["params"], truth) if b1["params"] else None,
                        "b1_transform_failed": b1["transform_failed"],
                    }
                )
    window_deltas = {}
    for key in ("f0", "v", "t0_abs", "b"):
        deltas = []
        for row in window_rows:
            if row["b1_errors"] is None:
                continue
            deltas.append(row["b1_errors"][key] - row["b0_errors"][key])
        window_deltas[key] = _bootstrap_mean_interval(deltas)
    stability_verdict = "stable_or_improved"
    for key, block in paired.items():
        delta = block["b1_mean_error"]
        if delta is not None and abs(delta) > 0.02 and abs(delta) > abs(block["b0_mean_error"] or 0.0):
            stability_verdict = "b1_degrades_physical_parameter_accuracy"
    return _jsonable(
        {
            "design": {
                "correct_cv_trials": len(correct),
                "window_perturbations": {
                    "durations_s": list(WINDOW_PERTURBATION_DURATIONS_S),
                    "geometries_m": list(WINDOW_PERTURBATION_CELLS_M),
                    "trials_per_cell": WINDOW_PERTURBATION_TRIALS,
                    "seed_base": SELFCHECK_SEED_BASE + 40_000,
                },
                "paired_by_trial": True,
            },
            "dev_grid_paired": paired,
            "window_perturbation_delta_intervals": window_deltas,
            "rows": rows,
            "window_rows": window_rows,
            "verdict": stability_verdict,
            "note": (
                "Errors are against synthetic truth (evaluation only). Lower absolute error is better; "
                "a positive B1-B0 delta in f0/v/b means B1 is further from truth."
            ),
        }
    )


# ---------------------------------------------------------------------------
# 4. Outcome taxonomy (dev grid, candidates B0-B3)
# ---------------------------------------------------------------------------

def _truth_correct(trial: Mapping[str, object]) -> bool:
    tolerance = trial["evaluation_only"]["estimate_within_tolerance"]
    return all(bool(value) for value in tolerance.values())


def outcome_taxonomy(dev_trials: list[dict]) -> dict:
    correct = [trial for trial in dev_trials if trial["mechanism"] == "correct_cv"]
    acceleration = [trial for trial in dev_trials if trial["mechanism"] == "acceleration"]
    null = [trial for trial in dev_trials if trial["mechanism"] == "null"]
    result = {
        "correct_model": {"denominator": len(correct), "truth_correct": sum(1 for trial in correct if _truth_correct(trial))},
        "acceleration": {"denominator": len(acceleration)},
        "null": {"denominator": len(null)},
        "candidates": {},
        "note": (
            "Outcomes are reported separately and never pooled. supported coverage = correct-model trial "
            "with truth within tolerance AND candidate decision accept / all correct-model trials. "
            "Zero-event rates carry an exact upper bound, not a zero probability."
        ),
    }
    for candidate in CANDIDATES:
        correct_supported = 0
        correct_false_rejection = 0
        correct_abstention = 0
        for trial in correct:
            decision = trial["candidates"][candidate]["decision"]
            if _truth_correct(trial) and decision == "accept":
                correct_supported += 1
            if _truth_correct(trial) and decision == "reject":
                correct_false_rejection += 1
            if _truth_correct(trial) and decision == "undetermined":
                correct_abstention += 1
        accel_detected = sum(1 for trial in acceleration if trial["candidates"][candidate]["decision"] == "reject")
        accel_undetermined = sum(1 for trial in acceleration if trial["candidates"][candidate]["decision"] == "undetermined")
        accel_false_supported = sum(1 for trial in acceleration if trial["candidates"][candidate]["decision"] == "accept")
        null_promoted = sum(1 for trial in null if trial["candidates"][candidate]["decision"] == "accept")
        null_rejected = sum(1 for trial in null if trial["candidates"][candidate]["decision"] == "reject")
        null_undetermined = sum(1 for trial in null if trial["candidates"][candidate]["decision"] == "undetermined")
        result["candidates"][candidate] = {
            "correct_model": {
                "supported_coverage": rate_block(correct_supported, len(correct)),
                "false_rejection": rate_block(correct_false_rejection, len(correct)),
                "abstention": rate_block(correct_abstention, len(correct)),
            },
            "acceleration": {
                "discrepancy_detected": rate_block(accel_detected, len(acceleration)),
                "undetermined": rate_block(accel_undetermined, len(acceleration)),
                "false_supported": rate_block(accel_false_supported, len(acceleration)),
            },
            "null": {
                "promoted_valid_event": rate_block(null_promoted, len(null)),
                "rejected": rate_block(null_rejected, len(null)),
                "undetermined": rate_block(null_undetermined, len(null)),
            },
        }
    return _jsonable(result)


# ---------------------------------------------------------------------------
# 5. B3 per-chirp-bin power
# ---------------------------------------------------------------------------

def _bin_index(value: float, edges) -> int:
    edges = [float(edge) for edge in edges]
    for index in range(len(edges) - 1):
        if edges[index] <= value < edges[index + 1]:
            return index
    return max(0, len(edges) - 2)


def b3_per_chirp_bin_power(dev_trials: list[dict]) -> dict:
    correct = [trial for trial in dev_trials if trial["mechanism"] == "correct_cv" and _truth_correct(trial)]
    acceleration = [trial for trial in dev_trials if trial["mechanism"] == "acceleration"]
    rows = []
    for index in range(len(B3_CHIRP_EDGES_HZ_S) - 1):
        low, high = float(B3_CHIRP_EDGES_HZ_S[index]), float(B3_CHIRP_EDGES_HZ_S[index + 1])
        cv_subset = [
            trial
            for trial in correct
            if _bin_index(float(trial["runtime_observables"]["estimated_chirp_rate_hz_s"]), B3_CHIRP_EDGES_HZ_S) == index
        ]
        accel_subset = [
            trial
            for trial in acceleration
            if _bin_index(float(trial["runtime_observables"]["estimated_chirp_rate_hz_s"]), B3_CHIRP_EDGES_HZ_S) == index
        ]
        cv_false = sum(1 for trial in cv_subset if trial["candidates"]["B3"]["decision"] == "reject")
        cv_abstain = sum(1 for trial in cv_subset if trial["candidates"]["B3"]["decision"] == "undetermined")
        accel_detected = sum(1 for trial in accel_subset if trial["candidates"]["B3"]["decision"] == "reject")
        accel_undetermined = sum(1 for trial in accel_subset if trial["candidates"]["B3"]["decision"] == "undetermined")
        accel_false = sum(1 for trial in accel_subset if trial["candidates"]["B3"]["decision"] == "accept")
        rows.append(
            {
                "chirp_low_hz_s": low,
                "chirp_high_hz_s": high,
                "cv": {
                    "n": len(cv_subset),
                    "false_rejection": rate_block(cv_false, len(cv_subset)),
                    "abstention": rate_block(cv_abstain, len(cv_subset)),
                },
                "acceleration": {
                    "n": len(accel_subset),
                    "detected": rate_block(accel_detected, len(accel_subset)),
                    "undetermined": rate_block(accel_undetermined, len(accel_subset)),
                    "false_supported": rate_block(accel_false, len(accel_subset)),
                },
                "paired_cv_and_acceleration_in_bin": bool(cv_subset and accel_subset),
            }
        )
    snr_values = [float(trial["runtime_observables"]["estimated_snr_db"]) for trial in dev_trials]
    snr_branch_counts = {}
    for index in range(len(B3_SNR_EDGES_DB) - 1):
        low, high = float(B3_SNR_EDGES_DB[index]), float(B3_SNR_EDGES_DB[index + 1])
        snr_branch_counts[f"{low:g}_{high:g}"] = sum(1 for value in snr_values if low <= value < high)
    exercised = [key for key, count in snr_branch_counts.items() if count > 0]
    thin_branch = any(0 < count < 10 for count in snr_branch_counts.values())
    saturated = bool(snr_values) and max(snr_values) >= 60.0
    snr_unverified = len(exercised) < (len(B3_SNR_EDGES_DB) - 1) or thin_branch or saturated
    if saturated:
        declaration = (
            "The estimated-SNR observable is saturated at the +60 dB clip for most development trials; "
            "the low-SNR branch has only a few trials. B3 conditional calibration on an unexercised/saturated "
            "SNR branch is unverified."
        )
    elif thin_branch:
        declaration = (
            "At least one B3 SNR branch has fewer than 10 development trials (thin branch); B3 conditional "
            "calibration on that branch is unverified."
        )
    elif len(exercised) < (len(B3_SNR_EDGES_DB) - 1):
        declaration = "At least one B3 SNR branch was not exercised in development; it is unverified."
    else:
        declaration = "All B3 SNR branches were exercised in development."
    return _jsonable(
        {
            "chirp_edges_hz_s": list(B3_CHIRP_EDGES_HZ_S),
            "bins": rows,
            "estimated_snr": {
                "min": float(np.min(snr_values)) if snr_values else None,
                "median": float(np.median(snr_values)) if snr_values else None,
                "max": float(np.max(snr_values)) if snr_values else None,
                "b3_snr_edges_db": list(B3_SNR_EDGES_DB),
                "branch_counts": snr_branch_counts,
                "exercised_branches": exercised,
                "snr_branch_unverified": snr_unverified,
                "saturated": saturated,
                "thin_branch": thin_branch,
                "declaration": declaration,
            },
            "pairing_note": (
                "CV and acceleration trials are paired within chirp bins only where both families occur; the "
                "development geometry sets for CV and acceleration do not overlap, so no same-geometry pair exists."
            ),
        }
    )


# ---------------------------------------------------------------------------
# Assembly / CLI
# ---------------------------------------------------------------------------

def run_selfcheck(jobs: int = 1, out_dir: str = "/tmp/c2selfcheck", progress: bool = True) -> dict:
    started = time.time()
    os.makedirs(out_dir, exist_ok=True)
    dev_dir = os.path.join(out_dir, "dev-repair")
    dev = experiment_repair.run_repair(jobs=jobs, output_dir=dev_dir, quiet=not progress)
    dev_trials = dev["artifact"]["trials"]
    wrong_model = run_wrong_model_diagnostic()
    time_block = run_time_block_holdout()
    parameter = parameter_stability(dev_trials)
    taxonomy = outcome_taxonomy(dev_trials)
    b3_power = b3_per_chirp_bin_power(dev_trials)

    self_confirmation = wrong_model["verdict"] == "self_confirmation_risk_flagged"
    verdict_parts = []
    verdict_parts.append(
        "self_confirmation_risk" if self_confirmation else "no_wrong_model_self_confirmation"
    )
    verdict_parts.append(
        "time_block_improvement_only_in_fitted_blocks"
        if time_block["summary"]["improvement_only_in_fitted_blocks"]
        else "time_block_improvement_persists_or_absent"
    )
    verdict_parts.append(parameter["verdict"])
    artifact = {
        "artifact": ARTIFACT_NAME,
        "version": SELFCHECK_VERSION,
        "authority": "ADR 0023 B/C",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_s": float(time.time() - started),
        "scope": {
            "development_grid_only": True,
            "sealed_grid_id": "pr4e-c2c-v1",
            "sealed_grid_opened": False,
            "sealed_grid_file_read": False,
            "seed_base": SELFCHECK_SEED_BASE,
            "seed_formula": SELFCHECK_SEED_FORMULA,
            "development_run": {
                "grid_id": dev["artifact"]["grid_id"],
                "frozen_grid_digest": dev["artifact"]["frozen_grid_digest"],
                "protocol_digest": dev["artifact"]["protocol_digest"],
                "dev_artifact_path": dev.get("artifact_path"),
                "dev_artifact_sha256": dev.get("artifact_sha256"),
                "dev_summary_digest": _digest(dev["artifact"]["development_summary"]),
            },
            "thresholds_changed": False,
            "candidates_imported_read_only": True,
        },
        "wrong_model_de_chirp": wrong_model,
        "time_block_holdout": time_block,
        "parameter_stability": parameter,
        "outcome_taxonomy": taxonomy,
        "b3_per_chirp_bin_power": b3_power,
        "overall_verdict": {
            "parts": verdict_parts,
            "b1_self_confirmation_risk": self_confirmation,
            "statement": (
                "B1 self-confirmation risk is flagged."
                if self_confirmation
                else "No wrong-model self-confirmation was flagged in this development set."
            ),
        },
        "limitations": [
            "Development-grid diagnostics only; the sealed 566-trial grid remains unopened.",
            "Wrong-model de-chirp uses synthetic high-chirp scenarios with new seeds (>=92M); it is a diagnostic, not an acceptance test.",
            "Time-block holdout estimates de-chirp parameters on the first 60% of frames; block sizes are finite and the held-out adequacy uses the used-block sigma.",
            "Parameter stability uses synthetic truth (evaluation only) and a finite development sample; intervals are trial-level bootstrap.",
            "B3 per-bin power is unpaired across geometries between CV and acceleration families; the estimated-SNR branch was not exercised.",
        ],
    }
    artifact = _jsonable(artifact)
    json_path = os.path.join(out_dir, "selfcheck.json")
    payload = (json.dumps(artifact, indent=1, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    with open(json_path, "wb") as handle:
        handle.write(payload)
    json_sha = hashlib.sha256(payload).hexdigest()
    markdown = render_markdown(artifact)
    markdown_path = os.path.join(out_dir, "selfcheck.md")
    markdown_sha = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    with open(markdown_path, "wb") as handle:
        handle.write(markdown.encode("utf-8"))
    return {
        "artifact": artifact,
        "paths": {
            "json": json_path,
            "markdown": markdown_path,
            "dev_artifact": dev.get("artifact_path"),
        },
        "digests": {"json": json_sha, "markdown": markdown_sha, "records": _digest(artifact)},
        "dev": dev,
    }


def _fmt(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def _rate_text(block: Mapping[str, object]) -> str:
    if not block:
        return "n/a"
    interval = block.get("wilson95") or [None, None]
    return f"{block.get('k')}/{block.get('n')} ({_fmt(block.get('rate'))}; 95% {_fmt(interval[0])}–{_fmt(interval[1])})"


def render_markdown(artifact: dict) -> str:
    lines = ["# B1 self-confirmation diagnostics and outcome taxonomy (development grid)", ""]
    lines.append(
        f"**Artifact:** `{artifact['artifact']}` v{artifact['version']} · development grid "
        f"`{artifact['scope']['development_run']['grid_id']}` · sealed grid opened: "
        f"{artifact['scope']['sealed_grid_opened']}"
    )
    lines.append("")
    lines.append("## Wrong-model de-chirp (correct-CV high chirp)")
    lines.append("")
    wrong = artifact["wrong_model_de_chirp"]["correct_cv"]
    lines.append("| prediction model | n | decisions | status | rejections | rate | median residual RMS (Hz) | median ACF1 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    b0 = wrong["b0"]
    lines.append(
        f"| B0 (no de-chirp) | {b0['n']} | {b0['decision_counts']} | n/a | {b0['rejections']} | {_fmt(b0['rejection_rate'])} | "
        f"{_fmt(b0['median_residual_rms_hz'])} | {_fmt(b0['median_residual_acf1'])} |"
    )
    for row in wrong["b1"]:
        lines.append(
            f"| B1 · {row['model']} | {row['n']} | {row['decision_counts']} | {row['status_counts']} | "
            f"{row['rejections']} | {_fmt(row['rejection_rate'])} | {_fmt(row['median_residual_rms_hz'])} | "
            f"{_fmt(row['median_residual_acf1'])} |"
        )
    lines.append("")
    lines.append(f"- Self-confirmation flags: {wrong['self_confirmation_flags'] or 'none'}")
    lines.append(f"- Verdict: **{artifact['wrong_model_de_chirp']['verdict']}**")
    lines.append("")
    lines.append("## Wrong-model de-chirp on acceleration trials")
    lines.append("")
    accel = artifact["wrong_model_de_chirp"]["acceleration"]
    lines.append(f"- B0 detection: {accel['b0']['detections']}/{accel['b0']['n']}")
    lines.append("| prediction model | n | decisions | detections | rate | detection loss vs correct model |")
    lines.append("|---|---|---|---|---|---|")
    for row in accel["b1"]:
        lines.append(
            f"| B1 · {row['model']} | {row['n']} | {row['decision_counts']} | {row['rejections']} | "
            f"{_fmt(row['rejection_rate'])} | {_fmt(row.get('detection_loss_vs_correct_model'))} |"
        )
    lines.append("")
    lines.append("## Time-block holdout")
    lines.append("")
    summary = artifact["time_block_holdout"]["summary"]
    lines.append(f"- n = {summary['n']}, transform failures = {summary['transform_failures']}")
    lines.append(f"- B0 block RMS used/held-out: {_fmt(summary['median_b0_used_block_rms_hz'])} / {_fmt(summary['median_b0_held_out_block_rms_hz'])} Hz")
    lines.append(f"- B1 block RMS used/held-out: {_fmt(summary['median_b1_used_block_rms_hz'])} / {_fmt(summary['median_b1_held_out_block_rms_hz'])} Hz")
    lines.append(f"- used-block improvement: {_fmt(summary['used_block_improvement_fraction'])}; held-out-block improvement: {_fmt(summary['held_out_block_improvement_fraction'])}")
    lines.append(f"- verdict: **{artifact['time_block_holdout']['verdict']}**")
    lines.append("")
    lines.append("## Parameter stability vs truth (B0 vs B1)")
    lines.append("")
    lines.append("| parameter | n | B0 mean error | B1 mean error | B1−B0 delta [95% CI] | mean abs B0 | mean abs B1 |")
    lines.append("|---|---|---|---|---|---|---|")
    for key, block in artifact["parameter_stability"]["dev_grid_paired"].items():
        interval = block["delta_interval"]["ci95"]
        lines.append(
            f"| {key} | {block['n']} | {_fmt(block['b0_mean_error'])} | {_fmt(block['b1_mean_error'])} | "
            f"{_fmt(block['mean_delta_b1_minus_b0'])} [{_fmt(interval[0])}, {_fmt(interval[1])}] | "
            f"{_fmt(block['mean_abs_b0'])} | {_fmt(block['mean_abs_b1'])} |"
        )
    lines.append("")
    lines.append(f"- verdict: **{artifact['parameter_stability']['verdict']}**")
    lines.append("")
    lines.append("## Outcome taxonomy (never pooled)")
    lines.append("")
    lines.append("| candidate | correct supported | false rejection | abstention | acceleration detected | acceleration undetermined | acceleration false supported | null promoted |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for candidate, block in artifact["outcome_taxonomy"]["candidates"].items():
        lines.append(
            f"| {candidate} | {_rate_text(block['correct_model']['supported_coverage'])} | "
            f"{_rate_text(block['correct_model']['false_rejection'])} | {_rate_text(block['correct_model']['abstention'])} | "
            f"{_rate_text(block['acceleration']['discrepancy_detected'])} | {_rate_text(block['acceleration']['undetermined'])} | "
            f"{_rate_text(block['acceleration']['false_supported'])} | {_rate_text(block['null']['promoted_valid_event'])} |"
        )
    lines.append("")
    lines.append("## B3 per-chirp-bin power")
    lines.append("")
    lines.append("| chirp bin (Hz/s) | CV n | CV false rejection | accel n | accel detected | accel undetermined | paired |")
    lines.append("|---|---|---|---|---|---|---|")
    for row in artifact["b3_per_chirp_bin_power"]["bins"]:
        lines.append(
            f"| {row['chirp_low_hz_s']:g}–{row['chirp_high_hz_s']:g} | {row['cv']['n']} | "
            f"{_rate_text(row['cv']['false_rejection'])} | {row['acceleration']['n']} | "
            f"{_rate_text(row['acceleration']['detected'])} | {_rate_text(row['acceleration']['undetermined'])} | "
            f"{row['paired_cv_and_acceleration_in_bin']} |"
        )
    lines.append("")
    snr = artifact["b3_per_chirp_bin_power"]["estimated_snr"]
    lines.append(f"- estimated SNR min/median/max: {_fmt(snr['min'])} / {_fmt(snr['median'])} / {_fmt(snr['max'])} dB")
    lines.append(f"- B3 SNR branch counts: {snr['branch_counts']}; exercised: {snr['exercised_branches']}")
    lines.append(f"- **SNR branch unverified: {snr['snr_branch_unverified']}** — {snr['declaration']}")
    lines.append("")
    lines.append(f"## Overall verdict: **{', '.join(artifact['overall_verdict']['parts'])}**")
    lines.append("")
    lines.append(artifact["overall_verdict"]["statement"])
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    for limitation in artifact["limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="ADR 0023 B/C B1 self-confirmation diagnostics and outcome taxonomy.")
    parser.add_argument("--out-dir", default="/tmp/c2selfcheck")
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    result = run_selfcheck(jobs=args.jobs, out_dir=args.out_dir, progress=not args.quiet)
    print("ADR 0023 self-check artifacts:")
    print(f"  json: {result['paths']['json']}  sha256: {result['digests']['json']}")
    print(f"  markdown: {result['paths']['markdown']}  sha256: {result['digests']['markdown']}")
    print(f"  dev artifact: {result['paths']['dev_artifact']}")
    print(f"  overall verdict: {result['artifact']['overall_verdict']}")
    wrong = result["artifact"]["wrong_model_de_chirp"]
    print(f"  wrong-model de-chirp: {wrong['verdict']}")
    for row in wrong["correct_cv"]["b1"]:
        print(f"    {row['model']:32s} rejections={row['rejections']}/{row['n']} rms={_fmt(row['median_residual_rms_hz'])}")
    taxonomy = result["artifact"]["outcome_taxonomy"]["candidates"]
    print("  taxonomy:")
    for candidate, block in taxonomy.items():
        print(
            f"    {candidate}: correct supported {_rate_text(block['correct_model']['supported_coverage'])}; "
            f"accel detected {_rate_text(block['acceleration']['discrepancy_detected'])}; "
            f"null promoted {_rate_text(block['null']['promoted_valid_event'])}"
        )
    print(f"  B3 SNR branch unverified: {result['artifact']['b3_per_chirp_bin_power']['estimated_snr']['snr_branch_unverified']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
