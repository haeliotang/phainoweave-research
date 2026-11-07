"""C2-M2 experiment: conditional measurement-error models and predictive acceptance.

Pipeline:
1. generate the new development data (phase/frame-alignment jitter, new seeds);
2. FFT-bin-offset diagnostic (truth q) and feature ablation (training only,
   leave-one-geometry-out);
3. fit M0 (white), M1 (empirical bias+template), M2 (conditional mean from
   selected features), M3 (conditional variance + AR(2) finite-lag covariance);
4. freeze the predictive-acceptance contract, then score held-out geometries
   once: actual vs predicted false-rejection rate per geometry with trial-level
   bootstrap intervals, ACF/variance/bias and per-geometry Ljung-Box checks;
5. run the non-competing reference estimator evaluation.

No adequacy threshold is changed and the sealed `pr4e-c2c-v1` grid is not used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from typing import Optional

import numpy as np

from . import measurement_error_models as mm
from . import measurement_model_reference as reference
from .adequacy import evaluate_adequacy
from .fit_hardened import fit_hardened

N_BOOTSTRAP = 1000
BOOTSTRAP_SEED = 90_000_000


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


# ---------------------------------------------------------------------------
# Development data
# ---------------------------------------------------------------------------

def _track_worker(task: tuple[mm.DevelopmentCell, int]) -> dict:
    return mm.generate_track(*task)


def generate_development_data(jobs: int = 1, progress: bool = True) -> list[dict]:
    cells = mm.build_cells()
    tasks = [(cell, trial) for cell in cells for trial in range(mm.N_TRIALS_PER_CELL)]
    tracks: list[dict] = []
    if jobs <= 1:
        for position, task in enumerate(tasks):
            tracks.append(_track_worker(task))
            if progress and (position + 1) % 100 == 0:
                print(f"  ... development {position + 1}/{len(tasks)}", file=sys.stderr)
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            for position, track in enumerate(pool.map(_track_worker, tasks, chunksize=4)):
                tracks.append(track)
                if progress and (position + 1) % 100 == 0:
                    print(f"  ... development {position + 1}/{len(tasks)}", file=sys.stderr)
    tracks.sort(key=lambda track: (track["cell"].cell_index, track["trial"]))
    return tracks


# ---------------------------------------------------------------------------
# Predictive helpers
# ---------------------------------------------------------------------------

def _acf1(values: np.ndarray) -> Optional[float]:
    values = np.asarray(values, dtype=np.float64)
    if values.size < 3:
        return None
    return float(np.corrcoef(values[:-1], values[1:])[0, 1])


def _decision(times: np.ndarray, frequencies: np.ndarray, c: float) -> dict:
    hardened = fit_hardened(times, frequencies, c=c)
    params = np.array([hardened.f0, hardened.v, hardened.t0, hardened.b], dtype=np.float64)
    adequacy = evaluate_adequacy(
        times,
        frequencies,
        params,
        hardened.sigma_f_hz,
        hardened.optimization_status,
        c=c,
    )
    return {
        "status": adequacy["model_adequacy_status"],
        "identifiability": adequacy["identifiability_status"],
        "ljung_box": adequacy["tests"]["autocorrelation"]["metrics"].get("ljung_box_statistic"),
        "sigma_f_hz": float(hardened.sigma_f_hz),
        "optimization_status": hardened.optimization_status,
    }


def _predict_worker(task: tuple[str, dict, dict]) -> dict:
    model_name, trial, models = task
    times = np.asarray(trial["times"], dtype=np.float64)
    true_frequency = np.asarray(trial["true_frequency"], dtype=np.float64)
    features = trial["features"]
    cell = trial["cell"]
    speed, snr = float(cell.speed_m_s), float(cell.snr_db)
    records = []
    for simulation in range(mm.N_PREDICTIVE_SIMULATIONS):
        seed = int(trial["seed"]) + 100000 * simulation
        if model_name == "M0":
            error = mm.generate_m0(models["m0"], times, speed, snr, seed)
        elif model_name == "M1":
            error = mm.generate_m1(models["m1"], times, float(cell.geometry_m), speed, snr, seed)
        elif model_name == "M2":
            error = mm.generate_m2_error(models["m2"], features, times, speed, snr, models["m0"], seed)
        elif model_name == "M3":
            error = mm.predict_mean(models["m2"], features) + mm.generate_m3(
                models["m3"], times, features, speed, snr, seed
            )
        else:
            raise ValueError(f"unknown model {model_name!r}")
        simulated_frequency = true_frequency + error
        decision = _decision(times, simulated_frequency, trial["scenario"].c)
        records.append(
            {
                "model": model_name,
                "simulation": simulation,
                "status": decision["status"],
                "ljung_box": decision["ljung_box"],
                "sigma_f_hz": decision["sigma_f_hz"],
                "error_bias_hz": float(np.mean(error)),
                "error_std_hz": float(np.std(error)),
                "error_acf1": _acf1(error),
                "error_rms_hz": float(np.sqrt(np.mean(error**2))),
            }
        )
    return {"model": model_name, "trial": int(trial["trial"]), "cell_id": cell.cell_id, "simulations": records}


def _actual_worker(trial: dict) -> dict:
    times = np.asarray(trial["times"], dtype=np.float64)
    decision = _decision(times, np.asarray(trial["estimated_frequency"], dtype=np.float64), trial["scenario"].c)
    error = np.asarray(trial["features"]["error"], dtype=np.float64)
    return {
        "trial": int(trial["trial"]),
        "cell_id": trial["cell"].cell_id,
        "geometry_m": float(trial["cell"].geometry_m),
        "status": decision["status"],
        "ljung_box": decision["ljung_box"],
        "sigma_f_hz": decision["sigma_f_hz"],
        "error_bias_hz": float(np.mean(error)),
        "error_std_hz": float(np.std(error)),
        "error_acf1": _acf1(error),
        "error_rms_hz": float(np.sqrt(np.mean(error**2))),
    }


def _bootstrap_rate(values, n_boot: int = N_BOOTSTRAP, seed: int = BOOTSTRAP_SEED) -> dict:
    values = np.asarray(values, dtype=np.float64)
    rng = np.random.default_rng(seed)
    if values.size == 0:
        return {"mean": None, "ci_low": None, "ci_high": None}
    samples = rng.choice(values, size=(n_boot, values.size), replace=True).mean(axis=1)
    return {
        "mean": float(np.mean(values)),
        "ci_low": float(np.quantile(samples, 0.05)),
        "ci_high": float(np.quantile(samples, 0.95)),
    }


def _quantiles(values) -> dict:
    values = np.asarray([value for value in values if value is not None], dtype=np.float64)
    if values.size == 0:
        return {}
    return {"p50": float(np.quantile(values, 0.5)), "p90": float(np.quantile(values, 0.9)), "p99": float(np.quantile(values, 0.99))}


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

def run_c2m2(jobs: int = 1, out_dir: str = "/tmp/c2m2", progress: bool = True) -> dict:
    started = time.time()
    os.makedirs(out_dir, exist_ok=True)
    # 1. Pre-register the acceptance contract BEFORE any held-out scoring.
    contract = mm.acceptance_contract()
    contract_sha = mm.write_json(os.path.join(out_dir, "acceptance_contract.json"), contract)
    contract_digest = _digest(contract)

    # 2. Development data (new seeds, phase/frame jitter).
    tracks = generate_development_data(jobs=jobs, progress=progress)
    training = [track for track in tracks if track["cell"].split == "train"]
    held_out = [track for track in tracks if track["cell"].split == "held_out"]
    data_digest = _digest([mm.trial_record(track) for track in tracks])

    # 3. FFT-bin-offset diagnostic.
    fft_diagnostic = mm.fft_bin_offset_diagnostic(tracks)

    # 4. Feature ablation on training geometries (leave-one-geometry-out).
    ablation = mm.select_feature_set(training)
    selected_features = tuple(ablation["selected_features"])

    # 5. Fit models.
    m2_model = mm.fit_hierarchical_mean(training, selected_features)
    m1_model = mm.build_m1_model(training)
    m0_model = mm.fit_m0(training)
    m3_model = mm.fit_m3(training, m2_model)
    models = {"m0": m0_model, "m1": m1_model, "m2": m2_model, "m3": m3_model}

    # 6. Held-out actual decisions.
    actual_records = [_actual_worker(track) for track in held_out]
    actual_by_cell: dict[str, list[dict]] = {}
    for record in actual_records:
        actual_by_cell.setdefault(record["cell_id"], []).append(record)

    # 7. Held-out predictions for M0-M3.
    prediction_tasks = [(model_name, track, models) for model_name in ("M0", "M1", "M2", "M3") for track in held_out]
    predicted: list[dict] = []
    if jobs <= 1:
        for position, task in enumerate(prediction_tasks):
            predicted.append(_predict_worker(task))
            if progress and (position + 1) % 40 == 0:
                print(f"  ... predictions {position + 1}/{len(prediction_tasks)}", file=sys.stderr)
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            for position, result in enumerate(pool.map(_predict_worker, prediction_tasks, chunksize=2)):
                predicted.append(result)
                if progress and (position + 1) % 40 == 0:
                    print(f"  ... predictions {position + 1}/{len(prediction_tasks)}", file=sys.stderr)
    predicted_by_model: dict[str, list[dict]] = {model: [] for model in ("M0", "M1", "M2", "M3")}
    for result in predicted:
        predicted_by_model[result["model"]].append(result)

    geometry_values = sorted({float(track["cell"].geometry_m) for track in held_out})
    evaluations = []
    for model_name in ("M0", "M1", "M2", "M3"):
        for geometry in geometry_values:
            geometry_tracks = [track for track in held_out if float(track["cell"].geometry_m) == geometry]
            geometry_cell_ids = {track["cell"].cell_id for track in geometry_tracks}
            actual = [record for record in actual_records if record["cell_id"] in geometry_cell_ids]
            actual_flags = [1.0 if record["status"] == "discrepancy" else 0.0 for record in actual]
            predicted_geometry = [
                result for result in predicted_by_model[model_name] if result["cell_id"] in geometry_cell_ids
            ]
            predicted_probabilities = []
            predicted_lb = []
            predicted_error_bias = []
            predicted_error_std = []
            predicted_error_acf1 = []
            for result in predicted_geometry:
                flags = [1.0 if sim["status"] == "discrepancy" else 0.0 for sim in result["simulations"]]
                predicted_probabilities.append(float(np.mean(flags)))
                predicted_lb.extend([sim["ljung_box"] for sim in result["simulations"] if sim["ljung_box"] is not None])
                predicted_error_bias.extend([sim["error_bias_hz"] for sim in result["simulations"]])
                predicted_error_std.extend([sim["error_std_hz"] for sim in result["simulations"]])
                predicted_error_acf1.extend([sim["error_acf1"] for sim in result["simulations"] if sim["error_acf1"] is not None])
            actual_rate = _bootstrap_rate(actual_flags)
            predicted_rate = _bootstrap_rate(predicted_probabilities)
            actual_lb = [record["ljung_box"] for record in actual if record["ljung_box"] is not None]
            actual_lb_quantiles = _quantiles(actual_lb)
            predicted_lb_quantiles = _quantiles(predicted_lb)
            actual_error_bias = float(np.mean([record["error_bias_hz"] for record in actual])) if actual else None
            actual_error_std = float(np.mean([record["error_std_hz"] for record in actual])) if actual else None
            actual_error_acf1 = float(np.mean([record["error_acf1"] for record in actual if record["error_acf1"] is not None])) if actual else None
            evaluations.append(
                {
                    "model": model_name,
                    "geometry_m": geometry,
                    "n_actual_trials": len(actual),
                    "n_predictive_simulations": len(predicted_lb),
                    "actual_frr": actual_rate,
                    "predicted_frr": predicted_rate,
                    "frr_gap_pp": (
                        None if actual_rate["mean"] is None or predicted_rate["mean"] is None else 100.0 * (predicted_rate["mean"] - actual_rate["mean"])
                    ),
                    "actual_lb_quantiles": actual_lb_quantiles,
                    "predicted_lb_quantiles": predicted_lb_quantiles,
                    "actual_error_bias_hz": actual_error_bias,
                    "predicted_error_bias_hz": float(np.mean(predicted_error_bias)) if predicted_error_bias else None,
                    "actual_error_std_hz": actual_error_std,
                    "predicted_error_std_hz": float(np.mean(predicted_error_std)) if predicted_error_std else None,
                    "actual_error_acf1": actual_error_acf1,
                    "predicted_error_acf1": float(np.mean(predicted_error_acf1)) if predicted_error_acf1 else None,
                    "adequacy_status_counts_actual": _counts(record["status"] for record in actual),
                }
            )

    tolerances = contract["tolerances"]
    for evaluation in evaluations:
        gaps = []
        if evaluation["frr_gap_pp"] is not None:
            gaps.append(abs(evaluation["frr_gap_pp"]) <= tolerances["frr_gap_max_pp_per_geometry"])
        if evaluation["actual_lb_quantiles"].get("p90") and evaluation["predicted_lb_quantiles"].get("p90"):
            relative = abs(evaluation["predicted_lb_quantiles"]["p90"] - evaluation["actual_lb_quantiles"]["p90"]) / max(
                abs(evaluation["actual_lb_quantiles"]["p90"]), 1.0
            )
            gaps.append(relative <= tolerances["lb_quantile_relative_gap_max"])
        if evaluation["actual_error_bias_hz"] is not None and evaluation["predicted_error_bias_hz"] is not None:
            gaps.append(abs(evaluation["predicted_error_bias_hz"] - evaluation["actual_error_bias_hz"]) <= tolerances["mean_bias_gap_max_hz"])
        if evaluation["actual_error_std_hz"] and evaluation["predicted_error_std_hz"]:
            ratio = evaluation["predicted_error_std_hz"] / evaluation["actual_error_std_hz"]
            gaps.append(tolerances["variance_ratio_range"][0] <= ratio <= tolerances["variance_ratio_range"][1])
        if evaluation["actual_error_acf1"] is not None and evaluation["predicted_error_acf1"] is not None:
            gaps.append(abs(evaluation["predicted_error_acf1"] - evaluation["actual_error_acf1"]) <= tolerances["acf_lag1_gap_max"])
        evaluation["accepted"] = bool(gaps) and all(gaps)
        evaluation["failed_checks"] = [index for index, passed in enumerate(gaps) if not passed]

    model_verdicts = []
    for model_name in ("M0", "M1", "M2", "M3"):
        rows = [row for row in evaluations if row["model"] == model_name]
        mean_abs_frr_gap = float(np.mean([abs(row["frr_gap_pp"]) for row in rows if row["frr_gap_pp"] is not None])) if rows else None
        model_verdicts.append(
            {
                "model": model_name,
                "geometries": len(rows),
                "accepted_geometries": sum(1 for row in rows if row["accepted"]),
                "mean_abs_frr_gap_pp": mean_abs_frr_gap,
                "mean_bias_gap_hz": float(
                    np.mean([abs(row["predicted_error_bias_hz"] - row["actual_error_bias_hz"]) for row in rows if row["predicted_error_bias_hz"] is not None])
                )
                if rows
                else None,
            }
        )
    best_model = min(
        [verdict for verdict in model_verdicts if verdict["mean_abs_frr_gap_pp"] is not None],
        key=lambda verdict: verdict["mean_abs_frr_gap_pp"],
    )
    accepted_models = [verdict["model"] for verdict in model_verdicts if verdict["accepted_geometries"] == verdict["geometries"]]
    if accepted_models:
        acceptance_verdict = "accepted:" + ",".join(accepted_models)
    else:
        acceptance_verdict = "not_accepted:no_model_predicts_all_held_out_geometries_within_tolerance"

    # 8. Reference estimator (non-competing).
    reference_artifact = reference.evaluate_reference(jobs=jobs, progress=progress)

    development_artifact = {
        "artifact": "c2m2-development",
        "version": "1.0.0",
        "acceptance_contract_digest": contract_digest,
        "acceptance_contract_sha256": contract_sha,
        "config": {
            "seed_base": mm.SEED_BASE,
            "seed_formula": mm.SEED_FORMULA,
            "n_trials_per_cell": mm.N_TRIALS_PER_CELL,
            "training_geometries_m": list(mm.TRAIN_GEOMETRIES_M),
            "held_out_geometries_m": list(mm.HELD_OUT_GEOMETRIES_M),
            "speeds_m_s": list(mm.SPEEDS_M_S),
            "snr_levels_db": list(mm.SNR_LEVELS_DB),
            "phase_and_frame_alignment_jitter": True,
            "frame_alignment_max_samples": mm.FRAME_ALIGNMENT_MAX_SAMPLES,
            "n_predictive_simulations": mm.N_PREDICTIVE_SIMULATIONS,
            "thresholds_changed": False,
            "sealed_c2c_grid_used": False,
            "truth_usage": "synthetic development only; deployment features use q_hat, not truth",
        },
        "data_records_sha256": data_digest,
        "cells": [
            {
                "cell_id": cell.cell_id,
                "geometry_m": cell.geometry_m,
                "speed_m_s": cell.speed_m_s,
                "snr_db": cell.snr_db,
                "split": cell.split,
                "n_trials": mm.N_TRIALS_PER_CELL,
            }
            for cell in mm.build_cells()
        ],
        "tracks": [mm.trial_record(track) for track in tracks],
        "fft_bin_offset_diagnostic": fft_diagnostic,
        "feature_ablation": ablation,
        "models": {
            "M0": {"summary": {key: m0_model[key] for key in ("model", "pooled_sigma_hz")}},
            "M1": {"summary": {"model": "empirical bias+template", "cells": [cell["cell_id"] for cell in m1_model["empirical_model"]["cells"]]}},
            "M2": {
                "summary": {
                    "feature_names": m2_model["feature_names"],
                    "training_mse": m2_model["training_mse"],
                    "pooling": m2_model["pooling"],
                }
            },
            "M3": {"summary": m3_model},
        },
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
        },
        "elapsed_s": None,
    }

    predictive_artifact = {
        "artifact": "c2m2-predictive-acceptance",
        "version": "1.0.0",
        "acceptance_contract_digest": contract_digest,
        "contract_frozen_before_held_out_scoring": True,
        "tolerances": tolerances,
        "held_out_geometries_m": list(mm.HELD_OUT_GEOMETRIES_M),
        "records_sha256": _digest({"actual": actual_records, "predicted": predicted}),
        "evaluations": evaluations,
        "model_verdicts": model_verdicts,
        "best_model_by_frr_gap": best_model["model"],
        "acceptance_verdict": acceptance_verdict,
        "language_discipline": (
            "counts and percentage-point gaps; no 'explained X%' claims; insufficient_evidence is not acceptance"
        ),
        "reference_estimator_verdict": reference_artifact["comparison"]["verdict"],
        "limitations": [
            "Held-out scores use N=10 actual trials per cell; FRR intervals are wide at this sample size.",
            "Predictive simulations use features estimated from the actual held-out extracted track (deployment-like) but share the trial's true frequency; this is a synthetic predictive check.",
            "M3 uses a parametric variance function and AR(2) finite-lag correlation, not a full high-dimensional covariance.",
            "The acceptance tolerances were frozen before held-out scoring; any post-hoc choice would require a new pre-registered run.",
        ],
        "environment": development_artifact["environment"],
        "elapsed_s": float(time.time() - started),
    }
    development_artifact["elapsed_s"] = predictive_artifact["elapsed_s"]

    development_sha = mm.write_json(os.path.join(out_dir, "development.json"), _jsonable(development_artifact))
    predictive_sha = mm.write_json(os.path.join(out_dir, "predictive_acceptance.json"), _jsonable(predictive_artifact))
    reference_sha, reference_md_sha = reference.write_artifact(
        reference_artifact,
        os.path.join(out_dir, "reference_estimator.json"),
        os.path.join(out_dir, "reference_estimator.md"),
    )
    return {
        "development": _jsonable(development_artifact),
        "predictive": _jsonable(predictive_artifact),
        "reference": reference_artifact,
        "paths": {
            "out_dir": out_dir,
            "contract": os.path.join(out_dir, "acceptance_contract.json"),
            "development": os.path.join(out_dir, "development.json"),
            "predictive": os.path.join(out_dir, "predictive_acceptance.json"),
            "reference": os.path.join(out_dir, "reference_estimator.json"),
            "reference_markdown": os.path.join(out_dir, "reference_estimator.md"),
        },
        "digests": {
            "contract": contract_sha,
            "development": development_sha,
            "predictive": predictive_sha,
            "reference": reference_sha,
            "reference_markdown": reference_md_sha,
        },
    }


# ---------------------------------------------------------------------------
# Markdown summary
# ---------------------------------------------------------------------------

def _fmt(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def render_summary(result: dict) -> str:
    development = result["development"]
    predictive = result["predictive"]
    lines = ["# C2-M2 conditional measurement-error models", ""]
    lines.append(
        f"**Acceptance contract:** `{predictive['acceptance_contract_digest']}` (frozen before held-out scoring) · "
        f"data records `{development['data_records_sha256']}`"
    )
    lines.append("")
    lines.append("## FFT-bin-offset diagnostic")
    lines.append("")
    fft = development["fft_bin_offset_diagnostic"]
    lines.append(f"- Hypothesis: {fft['hypothesis']}")
    lines.append(f"- Polynomial q-fit R² = {_fmt(fft['q_true_polynomial_fit']['r_squared'])}; "
                 f"corr(e, q_true) = {_fmt(fft['q_hat_relationship']['correlation_error_vs_q_true'])}, "
                 f"corr(e, q_hat) = {_fmt(fft['q_hat_relationship']['correlation_error_vs_q_hat'])}")
    lines.append("")
    lines.append("| q bin | n | mean e (Hz) | std e (Hz) |")
    lines.append("|---|---|---|---|")
    for bin_row in fft["q_bins"]:
        lines.append(f"| {bin_row['q_low']:.1f}–{bin_row['q_high']:.1f} | {bin_row['n_samples']} | {_fmt(bin_row['mean_error_hz'])} | {_fmt(bin_row['std_error_hz'])} |")
    lines.append("")
    lines.append("## Feature ablation (training, leave-one-geometry-out MSE)")
    lines.append("")
    lines.append("| feature set | features | mean CV MSE (Hz²) |")
    lines.append("|---|---|---|")
    for row in development["feature_ablation"]["table"]:
        lines.append(f"| {row['name']} | {', '.join(row['features'])} | {_fmt(row['mean_cv_mse'])} |")
    lines.append(f"\nSelected: **{development['feature_ablation']['selected']}** ({', '.join(development['feature_ablation']['selected_features'])})")
    lines.append("")
    lines.append("## Predictive acceptance (held-out geometries)")
    lines.append("")
    lines.append("| model | geometry (m) | actual FRR [90% CI] | predicted FRR [90% CI] | gap (pp) | bias actual/pred (Hz) | std actual/pred (Hz) | ACF1 actual/pred | accepted |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for row in predictive["evaluations"]:
        lines.append(
            f"| {row['model']} | {row['geometry_m']:g} | "
            f"{_fmt(row['actual_frr']['mean'])} [{_fmt(row['actual_frr']['ci_low'])}, {_fmt(row['actual_frr']['ci_high'])}] | "
            f"{_fmt(row['predicted_frr']['mean'])} [{_fmt(row['predicted_frr']['ci_low'])}, {_fmt(row['predicted_frr']['ci_high'])}] | "
            f"{_fmt(row['frr_gap_pp'])} | {_fmt(row['actual_error_bias_hz'])}/{_fmt(row['predicted_error_bias_hz'])} | "
            f"{_fmt(row['actual_error_std_hz'])}/{_fmt(row['predicted_error_std_hz'])} | "
            f"{_fmt(row['actual_error_acf1'])}/{_fmt(row['predicted_error_acf1'])} | {row['accepted']} |"
        )
    lines.append("")
    lines.append("## Model verdicts")
    lines.append("")
    lines.append("| model | accepted geometries | mean |FRR gap| (pp) | mean bias gap (Hz) |")
    lines.append("|---|---|---|---|")
    for verdict in predictive["model_verdicts"]:
        lines.append(
            f"| {verdict['model']} | {verdict['accepted_geometries']}/{verdict['geometries']} | "
            f"{_fmt(verdict['mean_abs_frr_gap_pp'])} | {_fmt(verdict['mean_bias_gap_hz'])} |"
        )
    lines.append("")
    lines.append(f"Acceptance verdict: **{predictive['acceptance_verdict']}**; best model by FRR gap: **{predictive['best_model_by_frr_gap']}**.")
    lines.append("")
    lines.append("## Reference estimator (non-competing)")
    lines.append("")
    reference_comparison = result["reference"]["comparison"]
    lines.append(f"- Verdict: **{reference_comparison['verdict']}**")
    lines.append(f"- {reference_comparison['statement']}")
    lines.append(
        f"- Correct-model FRR front/reference: {_fmt(reference_comparison['false_rejection_rate_front_end'])} → "
        f"{_fmt(reference_comparison['false_rejection_rate_reference'])} ({_fmt(reference_comparison['false_rejection_rate_delta_pp'])} pp)"
    )
    lines.append(
        f"- Acceleration detection front/reference: {_fmt(reference_comparison['detection_rate_front_end'])} → "
        f"{_fmt(reference_comparison['detection_rate_reference'])} ({_fmt(reference_comparison['detection_rate_delta_pp'])} pp)"
    )
    lines.append("")
    lines.append("## Language discipline")
    lines.append("")
    lines.append(predictive["language_discipline"])
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    for limitation in predictive["limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="C2-M2 conditional measurement-error models and predictive acceptance.")
    parser.add_argument("--out-dir", default="/tmp/c2m2")
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    result = run_c2m2(jobs=args.jobs, out_dir=args.out_dir, progress=not args.quiet)
    summary = render_summary(result)
    summary_path = os.path.join(args.out_dir, "c2m2_summary.md")
    summary_sha = hashlib.sha256(summary.encode("utf-8")).hexdigest()
    with open(summary_path, "wb") as handle:
        handle.write(summary.encode("utf-8"))
    print("C2-M2 artifacts:")
    for key, value in result["digests"].items():
        print(f"  {key}: {result['paths'].get(key, '')}  sha256: {value}")
    print(f"  summary: {summary_path}  sha256: {summary_sha}")
    print(f"  contract digest: {result['predictive']['acceptance_contract_digest']}")
    print(f"  data records: {result['development']['data_records_sha256']}")
    print(f"  acceptance verdict: {result['predictive']['acceptance_verdict']}")
    print(f"  best model by FRR gap: {result['predictive']['best_model_by_frr_gap']}")
    print("  model verdicts:")
    for verdict in result["predictive"]["model_verdicts"]:
        print(
            f"    {verdict['model']}: accepted {verdict['accepted_geometries']}/{verdict['geometries']}, "
            f"mean |FRR gap| {verdict['mean_abs_frr_gap_pp']} pp"
        )
    print(f"  reference: {result['reference']['comparison']['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
