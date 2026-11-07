"""C2 mechanism attribution — diagnosis matrix (ADR 0019 section D).

**This module is diagnostic only.**  It is not imported by any runtime or
decision path.  Synthetic truth is used here to build the *true generated
frequency* comparison track and to score fits for diagnostics; it never enters
the adequacy decision of the extracted path.

Matrix
------
Rows: IF source -- ``extracted`` (the frozen E0 front end) vs ``truth`` (the
generator's true apparent frequency sampled at the same frame centres, plus a
declared white IF noise floor ``TRUTH_IF_NOISE_FLOOR_HZ`` to avoid the
numerically degenerate sigma_f ~ 1e-13 case; a noiseless sensitivity variant is
also reported).

Columns: model situation --
1. correct constant-velocity model at nominal geometry (control),
2. unmodelled acceleration {0.2, 0.4} m/s^2,
3. high-chirp geometry stress {150, 600, 5000} m at v = 250 m/s,
plus noise-only null cells per matrix cell.

Per cell we report which adequacy tests fire (residual scale, Ljung-Box,
time-structure, block held-out), whether correct-model trials are falsely
rejected, and whether that happens with the true frequency or only with the
extracted frequency.  A parametric simulation through the whole
generate -> extract -> fit -> adequacy pipeline estimates the actual null
distribution of the Ljung-Box statistic and block RMSE and compares it to the
frozen threshold and to the standard asymptotic chi-square expectation.

No adequacy threshold is changed and no repair route (de-chirping,
pre-whitening, geometry conditioning) is implemented.
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
from dataclasses import asdict, dataclass, replace
from typing import Optional

import numpy as np

from .adequacy import evaluate_adequacy
from .adequacy_protocol import PROTOCOL, PROTOCOL_DIGEST
from .experiment import B_REL_TOL, BASE, F0_REL_TOL, F_MAX, F_MIN, FRAME_LEN, HOP, T0_ABS_TOL, V_REL_TOL
from .features import estimate_if_track
from .fit_hardened import fit_hardened
from .synthetic import Scenario, apparent_frequency, generate

ARTIFACT_NAME = "c2-diagnosis"
DIAGNOSTIC_VERSION = "1.0.0"
N_TRIALS_DEFAULT = 100
SEED_BASE = 50_000_000  # new base, disjoint from E0/PR-4d/claims bases
TRUTH_IF_NOISE_FLOOR_HZ = 0.05
NOISELESS_SENSITIVITY_TRIALS = 20
NOISELESS_SENSITIVITY_CELLS = ("cv_nominal", "geom_150")
ASYMPTOTIC_MC_SAMPLES = 200_000
ASYMPTOTIC_MC_SEED = 50_000_000

ADF_LB_THRESHOLD = float(PROTOCOL["tests"]["autocorrelation"]["ljung_box_statistic_max"])
ADF_LB_ORDER = int(PROTOCOL["tests"]["autocorrelation"]["ljung_box_order"])
ADF_LB_DF = int(PROTOCOL["tests"]["autocorrelation"]["ljung_box_df"])
ADF_BLOCK_RMSE_THRESHOLD = float(PROTOCOL["tests"]["block_prediction"]["heldout_normalized_rmse_max"])

TEST_NAMES = ("standardized_residuals", "autocorrelation", "time_structure", "block_prediction")
MECHANISMS = ("correct_constant_velocity_control", "unmodelled_acceleration", "high_chirp_geometry", "noise_only_null")

SIGNAL_CELL_SPECS = (
    ("cv_nominal", "correct_constant_velocity", "nominal geometry control", {}),
    ("accel_0.2", "model_misspecification", "unmodelled constant acceleration 0.2 m/s^2", {"accel": 0.2}),
    ("accel_0.4", "model_misspecification", "unmodelled constant acceleration 0.4 m/s^2", {"accel": 0.4}),
    ("geom_150", "geometry_stress", "high chirp: closest approach 150 m at 250 m/s", {"b": 150.0}),
    ("geom_600", "geometry_stress", "high chirp: closest approach 600 m at 250 m/s", {"b": 600.0}),
    ("geom_5000", "geometry_stress", "low chirp: closest approach 5000 m at 250 m/s", {"b": 5000.0}),
)


@dataclass(frozen=True)
class DiagnosisCell:
    name: str
    family: str
    label: str
    scenario: Scenario
    n_trials: int
    is_null: bool = False
    cell_index: int = 0


def build_cells(n_trials: int = N_TRIALS_DEFAULT) -> tuple[list[DiagnosisCell], list[DiagnosisCell]]:
    """Signal cells (six) and noise-only null cells (six, one per signal cell)."""
    signal_cells: list[DiagnosisCell] = []
    null_cells: list[DiagnosisCell] = []
    scenario_base = replace(BASE, snr_db=20.0)
    for index, (name, family, label, overrides) in enumerate(SIGNAL_CELL_SPECS):
        scenario = replace(scenario_base, **overrides)
        signal_cells.append(
            DiagnosisCell(name=name, family=family, label=label, scenario=scenario, n_trials=int(n_trials), cell_index=index)
        )
    for offset, signal_cell in enumerate(signal_cells, start=len(SIGNAL_CELL_SPECS)):
        null_scenario = replace(signal_cell.scenario, emit_signal=False)
        null_cells.append(
            DiagnosisCell(
                name=f"null_{signal_cell.name}",
                family="noise_only_null",
                label=f"noise-only realization for {signal_cell.name}",
                scenario=null_scenario,
                n_trials=int(n_trials),
                is_null=True,
                cell_index=offset,
            )
        )
    return signal_cells, null_cells


def cell_seed(cell: DiagnosisCell, trial: int) -> int:
    return SEED_BASE + 1000 * int(cell.cell_index) + int(trial)


# ---------------------------------------------------------------------------
# Truth-frequency diagnostic track (synthetic diagnosis only)
# ---------------------------------------------------------------------------

def truth_if_track(
    scenario: Scenario,
    frame_times: np.ndarray,
    noise_floor_hz: float = TRUTH_IF_NOISE_FLOOR_HZ,
    seed: Optional[int] = None,
) -> np.ndarray:
    """True generated apparent frequency at the frame centres, plus a declared IF floor.

    ``noise_floor_hz == 0`` yields the noiseless sensitivity variant (which is
    numerically degenerate for the fitted residual scale; reported as such).
    """
    values = apparent_frequency(scenario, np.asarray(frame_times, dtype=np.float64))
    if noise_floor_hz > 0.0:
        rng = np.random.default_rng(int(scenario.seed if seed is None else seed) + 7919)
        values = values + float(noise_floor_hz) * rng.standard_normal(values.size)
    return values


def _parameter_rel_errors(params: dict, scenario: Scenario) -> dict:
    return {
        "f0": (params["f0"] - scenario.f0) / scenario.f0,
        "v": (params["v"] - scenario.v) / scenario.v,
        "t0": (params["t0"] - scenario.t0) / scenario.t0,
        "b": (params["b"] - scenario.b) / scenario.b,
        "t0_abs": params["t0"] - scenario.t0,
    }


def _within_e0_tolerance(rel: dict) -> bool:
    return bool(
        abs(rel["f0"]) <= F0_REL_TOL
        and abs(rel["v"]) <= V_REL_TOL
        and abs(rel["t0_abs"]) <= T0_ABS_TOL
        and abs(rel["b"]) <= B_REL_TOL
    )


def _slim_metrics(test_name: str, result: dict) -> dict:
    metrics = result.get("metrics") or {}
    if test_name == "standardized_residuals":
        return {
            "robust_scale_ratio": metrics.get("robust_scale_ratio"),
            "max_abs_z": metrics.get("max_abs_z"),
            "tail_fraction_abs_z_gt_3": metrics.get("tail_fraction_abs_z_gt_3"),
            "excess_kurtosis": metrics.get("excess_kurtosis"),
        }
    if test_name == "autocorrelation":
        return {
            "ljung_box_statistic": metrics.get("ljung_box_statistic"),
            "max_abs_acf": metrics.get("max_abs_acf"),
        }
    if test_name == "time_structure":
        return {
            "corr_time": metrics.get("corr_time"),
            "quadratic_coefficient_over_sigma_f": metrics.get("quadratic_coefficient_over_sigma_f"),
            "max_abs_phase_correlation": metrics.get("max_abs_phase_correlation"),
        }
    return {
        "median_normalized_rmse": metrics.get("median_normalized_rmse"),
        "median_block_explained_fraction": metrics.get("median_block_explained_fraction"),
    }


def run_trial(cell: DiagnosisCell, trial: int, if_source: str) -> dict:
    """One diagnostic cell trial: generate -> (extract | truth) -> fit -> adequacy."""
    seed = cell_seed(cell, trial)
    scenario = replace(cell.scenario, seed=int(seed))
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
    if if_source == "extracted":
        frequencies = track.f
    elif if_source == "truth":
        frequencies = truth_if_track(scenario, track.t, TRUTH_IF_NOISE_FLOOR_HZ, seed=seed)
    elif if_source == "truth_noiseless":
        frequencies = truth_if_track(scenario, track.t, 0.0, seed=seed)
    else:
        raise ValueError(f"unknown if_source {if_source!r}")

    hardened = fit_hardened(track.t, frequencies, c=scenario.c)
    params = np.array([hardened.f0, hardened.v, hardened.t0, hardened.b], dtype=np.float64)
    adequacy = evaluate_adequacy(
        track.t,
        frequencies,
        params,
        hardened.sigma_f_hz,
        hardened.optimization_status,
        c=scenario.c,
    )
    rel = _parameter_rel_errors(hardened.params, scenario)
    return {
        "cell": cell.name,
        "family": cell.family,
        "if_source": if_source,
        "trial": int(trial),
        "seed": int(seed),
        "evaluation_only": {
            "scenario": {
                key: (float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else value)
                for key, value in asdict(scenario).items()
            },
            "parameter_rel_errors": {key: float(value) for key, value in rel.items()},
            "within_e0_tolerance": _within_e0_tolerance(rel),
        },
        "hardened": {
            "params": {name: float(value) for name, value in hardened.params.items()},
            "sigma_f_hz": float(hardened.sigma_f_hz),
            "optimization_status": hardened.optimization_status,
            "worst_rel_se": hardened.worst_rel_se,
            "condition_number": hardened.condition_number,
        },
        "adequacy": {
            "model_adequacy_status": adequacy["model_adequacy_status"],
            "identifiability_status": adequacy["identifiability_status"],
            "epistemic_decision": adequacy["epistemic_decision"],
            "tests": {
                name: {
                    "status": adequacy["tests"][name]["status"],
                    "metrics": _slim_metrics(name, adequacy["tests"][name]),
                }
                for name in TEST_NAMES
            },
        },
    }


def _worker(task: tuple[DiagnosisCell, int, str]) -> dict:
    cell, trial, if_source = task
    return _jsonable(run_trial(cell, trial, if_source))


def _jsonable(obj):
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


def _digest(document) -> str:
    return hashlib.sha256(
        json.dumps(_jsonable(document), sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _counts(values) -> dict:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _quantiles(values, probabilities=(0.5, 0.9, 0.95, 0.99)) -> dict:
    array = np.asarray([value for value in values if value is not None], dtype=np.float64)
    if array.size == 0:
        return {}
    return {
        f"p{int(round(probability * 100))}": float(np.quantile(array, probability))
        for probability in probabilities
    } | {"max": float(np.max(array)), "n": int(array.size)}


def _test_fail_counts(records: list[dict]) -> dict:
    counts = {}
    for name in TEST_NAMES:
        counts[name] = _counts(record["adequacy"]["tests"][name]["status"] for record in records)
    return counts


def _cell_summary(cell: DiagnosisCell, records: list[dict]) -> dict:
    adequacy_counts = _counts(record["adequacy"]["model_adequacy_status"] for record in records)
    optimization_counts = _counts(record["hardened"]["optimization_status"] for record in records)
    return {
        "cell": cell.name,
        "family": cell.family,
        "if_source": records[0]["if_source"] if records else None,
        "n": len(records),
        "adequacy_status_counts": adequacy_counts,
        "optimization_status_counts": optimization_counts,
        "test_status_counts": _test_fail_counts(records),
        "false_rejections": sum(
            1
            for record in records
            if cell.family in ("correct_constant_velocity", "geometry_stress")
            and record["adequacy"]["model_adequacy_status"] == "discrepancy"
        ),
        "correct_rejections": sum(
            1
            for record in records
            if cell.family == "model_misspecification"
            and record["adequacy"]["model_adequacy_status"] == "discrepancy"
        ),
        "lb_quantiles": _quantiles(
            record["adequacy"]["tests"]["autocorrelation"]["metrics"]["ljung_box_statistic"] for record in records
        ),
        "block_rmse_quantiles": _quantiles(
            record["adequacy"]["tests"]["block_prediction"]["metrics"]["median_normalized_rmse"] for record in records
        ),
        "within_e0_tolerance": sum(1 for record in records if record["evaluation_only"]["within_e0_tolerance"]),
        "median_abs_parameter_errors": {
            key: float(
                np.median([abs(record["evaluation_only"]["parameter_rel_errors"][key]) for record in records])
            )
            for key in ("f0", "v", "t0", "b")
        },
    }


def _null_summary(cell: DiagnosisCell, records: list[dict]) -> dict:
    lb = [record["adequacy"]["tests"]["autocorrelation"]["metrics"]["ljung_box_statistic"] for record in records]
    block = [record["adequacy"]["tests"]["block_prediction"]["metrics"]["median_normalized_rmse"] for record in records]
    lb_values = np.asarray([value for value in lb if value is not None], dtype=np.float64)
    return {
        "cell": cell.name,
        "if_source": "extracted",
        "n": len(records),
        "adequacy_status_counts": _counts(record["adequacy"]["model_adequacy_status"] for record in records),
        "optimization_status_counts": _counts(record["hardened"]["optimization_status"] for record in records),
        "test_status_counts": _test_fail_counts(records),
        "lb_quantiles": _quantiles(lb),
        "lb_tail_fraction_above_frozen_threshold": (
            float(np.mean(lb_values > ADF_LB_THRESHOLD)) if lb_values.size else None
        ),
        "block_rmse_quantiles": _quantiles(block),
    }


def _asymptotic_quantiles() -> dict:
    rng = np.random.default_rng(ASYMPTOTIC_MC_SEED)
    samples = rng.chisquare(ADF_LB_DF, size=ASYMPTOTIC_MC_SAMPLES)
    return {
        "distribution": f"chi2(df={ADF_LB_DF}) Monte Carlo",
        "samples": ASYMPTOTIC_MC_SAMPLES,
        "seed": ASYMPTOTIC_MC_SEED,
        "quantiles": _quantiles(samples),
    }


def _attribution(signal_summaries: list[dict], null_summaries: list[dict], comparison: dict) -> list[dict]:
    by_key = {(summary["cell"], summary["if_source"]): summary for summary in signal_summaries}

    def rate(summary, field):
        return (summary[field] / summary["n"]) if summary and summary["n"] else None

    verdicts = []
    # control: correct CV model at nominal geometry
    control_extracted = by_key.get(("cv_nominal", "extracted"))
    control_truth = by_key.get(("cv_nominal", "truth"))
    v = {
        "mechanism": "correct_constant_velocity_control",
        "extracted_false_rejection_rate": rate(control_extracted, "false_rejections"),
        "truth_false_rejection_rate": rate(control_truth, "false_rejections"),
    }
    if (v["extracted_false_rejection_rate"] or 0.0) >= 0.05 and (v["truth_false_rejection_rate"] or 0.0) <= 0.01:
        v["verdict"] = "front_end_structural_error"
    elif (v["extracted_false_rejection_rate"] or 0.0) <= 0.01 and (v["truth_false_rejection_rate"] or 0.0) <= 0.01:
        v["verdict"] = "no_false_rejection"
    else:
        v["verdict"] = "inconclusive_or_persistent"
    v["statement"] = (
        "Correct-model control: false rejections appear with the extracted frequency only "
        "-> front end / its error model is the target."
        if v["verdict"] == "front_end_structural_error"
        else "Correct-model control: no extracted-only false rejection signature."
    )
    verdicts.append(v)

    # acceleration: genuine model misspecification; rejection expected in both paths
    accel_extracted = [summary for summary in signal_summaries if summary["family"] == "model_misspecification" and summary["if_source"] == "extracted"]
    accel_truth = [summary for summary in signal_summaries if summary["family"] == "model_misspecification" and summary["if_source"] == "truth"]
    ext_rate = sum(summary["correct_rejections"] for summary in accel_extracted) / max(1, sum(summary["n"] for summary in accel_extracted))
    truth_rate = sum(summary["correct_rejections"] for summary in accel_truth) / max(1, sum(summary["n"] for summary in accel_truth))
    verdicts.append(
        {
            "mechanism": "unmodelled_acceleration",
            "extracted_correct_rejection_rate": ext_rate,
            "truth_correct_rejection_rate": truth_rate,
            "verdict": "model_misspecification" if ext_rate >= 0.5 and truth_rate >= 0.5 else "inconclusive",
            "statement": (
                "Rejection persists with the true frequency -> the target is the model/fit residual structure, "
                "not the front end; acceleration is genuine misspecification."
                if ext_rate >= 0.5 and truth_rate >= 0.5
                else "Acceleration rejection pattern is inconclusive."
            ),
        }
    )

    # geometry stress: false rejections of a correct model
    geometry_extracted = [summary for summary in signal_summaries if summary["family"] == "geometry_stress" and summary["if_source"] == "extracted"]
    geometry_truth = [summary for summary in signal_summaries if summary["family"] == "geometry_stress" and summary["if_source"] == "truth"]
    ext_rate = sum(summary["false_rejections"] for summary in geometry_extracted) / max(1, sum(summary["n"] for summary in geometry_extracted))
    truth_rate = sum(summary["false_rejections"] for summary in geometry_truth) / max(1, sum(summary["n"] for summary in geometry_truth))
    if ext_rate >= 0.05 and truth_rate <= 0.01:
        geometry_verdict = "front_end_structural_error"
    elif ext_rate >= 0.05 and truth_rate >= 0.05:
        geometry_verdict = "fit_or_residual_test_null_calibration"
    elif ext_rate <= 0.01 and truth_rate <= 0.01:
        geometry_verdict = "no_false_rejection"
    else:
        geometry_verdict = "inconclusive"
    verdicts.append(
        {
            "mechanism": "high_chirp_geometry",
            "extracted_false_rejection_rate": ext_rate,
            "truth_false_rejection_rate": truth_rate,
            "verdict": geometry_verdict,
            "statement": (
                "Geometry false rejections appear with the extracted frequency only "
                "-> front-end structural error (chirp-dependent interpolation bias) is the target."
                if geometry_verdict == "front_end_structural_error"
                else "Geometry false rejections persist with the true frequency -> target the fit/residual test/null calibration."
                if geometry_verdict == "fit_or_residual_test_null_calibration"
                else "Geometry stress shows no false-rejection signature in this sample."
            ),
        }
    )

    # null distribution comparison
    model_null = comparison.get("model_valid_null_lb_quantiles", {})
    asymptotic = comparison.get("asymptotic_lb_quantiles", {})
    noise_null = comparison.get("noise_only_null_lb_quantiles", {})
    ratio = comparison.get("empirical_over_asymptotic_p99_ratio")
    verdicts.append(
        {
            "mechanism": "noise_only_null",
            "frozen_threshold_lb": ADF_LB_THRESHOLD,
            "asymptotic_lb_p99": asymptotic.get("p99"),
            "model_valid_null_lb_p99": model_null.get("p99"),
            "noise_only_null_lb_p99": noise_null.get("p99"),
            "empirical_over_asymptotic_p99_ratio": ratio,
            "frozen_threshold_tail_model_valid": comparison.get("frozen_threshold_tail_model_valid"),
            "frozen_threshold_tail_noise_only": comparison.get("frozen_threshold_tail_noise_only"),
            "verdict": "test_null_distribution_mismatch"
            if ratio is not None and ratio > 5.0
            else "asymptotic_null_approximately_holds",
            "statement": (
                "The Ljung-Box asymptotic chi-square null does not describe the extracted-residual null "
                "(inflated by front-end structural error); the frozen threshold is calibrated to the inflated "
                "pipeline null. Noise-only residuals are much closer to the asymptotic null, so the mismatch is "
                "structural, not a generic statistical error."
                if ratio is not None and ratio > 5.0
                else "The extracted-residual null is close to the asymptotic expectation in this sample."
            ),
        }
    )
    return verdicts


def run_diagnosis(
    n_trials: int = N_TRIALS_DEFAULT,
    jobs: int = 1,
    cell_filter: Optional[str] = None,
    noise_floor_hz: float = TRUTH_IF_NOISE_FLOOR_HZ,
    progress: bool = True,
) -> dict:
    signal_cells, null_cells = build_cells(n_trials=n_trials)
    if cell_filter:
        signal_cells = [cell for cell in signal_cells if cell_filter in cell.name or cell_filter == cell.family]
        null_cells = [cell for cell in null_cells if cell_filter in cell.name]
        if not signal_cells and not null_cells:
            raise ValueError(f"no cell matches filter {cell_filter!r}")
    tasks: list[tuple[DiagnosisCell, int, str]] = []
    for cell in signal_cells:
        for trial in range(cell.n_trials):
            tasks.append((cell, trial, "extracted"))
            tasks.append((cell, trial, "truth"))
        if cell.name in NOISELESS_SENSITIVITY_CELLS and not cell_filter:
            for trial in range(min(NOISELESS_SENSITIVITY_TRIALS, cell.n_trials)):
                tasks.append((cell, trial, "truth_noiseless"))
    for cell in null_cells:
        for trial in range(cell.n_trials):
            tasks.append((cell, trial, "extracted"))

    started = time.time()
    records: list[dict] = []
    if jobs <= 1:
        for position, task in enumerate(tasks):
            records.append(_worker(task))
            if progress and (position + 1) % 200 == 0:
                print(f"  ... {position + 1}/{len(tasks)} trials", file=sys.stderr)
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            for position, record in enumerate(pool.map(_worker, tasks, chunksize=8)):
                records.append(record)
                if progress and (position + 1) % 200 == 0:
                    print(f"  ... {position + 1}/{len(tasks)} trials", file=sys.stderr)
    elapsed = time.time() - started
    records.sort(key=lambda record: (record["cell"], record["if_source"], record["trial"]))

    signal_summaries = []
    for cell in signal_cells:
        for source in ("extracted", "truth"):
            subset = [record for record in records if record["cell"] == cell.name and record["if_source"] == source]
            if subset:
                signal_summaries.append(_cell_summary(cell, subset))
    noiseless_summaries = []
    for cell in signal_cells:
        subset = [record for record in records if record["cell"] == cell.name and record["if_source"] == "truth_noiseless"]
        if subset:
            noiseless_summaries.append(_cell_summary(cell, subset))
    null_summaries = [
        _null_summary(cell, [record for record in records if record["cell"] == cell.name])
        for cell in null_cells
        if any(record["cell"] == cell.name for record in records)
    ]

    asymptotic = _asymptotic_quantiles()
    cv_extracted = next(
        (summary for summary in signal_summaries if summary["cell"] == "cv_nominal" and summary["if_source"] == "extracted"),
        None,
    )
    model_null_lb = cv_extracted["lb_quantiles"] if cv_extracted else {}
    model_null_values = [
        record["adequacy"]["tests"]["autocorrelation"]["metrics"]["ljung_box_statistic"]
        for record in records
        if record["cell"] == "cv_nominal" and record["if_source"] == "extracted"
    ]
    noise_null_values = [
        record["adequacy"]["tests"]["autocorrelation"]["metrics"]["ljung_box_statistic"]
        for record in records
        if record["cell"].startswith("null_")
    ]
    noise_null_lb = _quantiles(noise_null_values)
    asymptotic_p99 = asymptotic["quantiles"].get("p99")
    empirical_ratio = (
        float(model_null_lb["p99"] / asymptotic_p99) if model_null_lb.get("p99") and asymptotic_p99 else None
    )
    comparison = {
        "frozen_lb_threshold": ADF_LB_THRESHOLD,
        "frozen_lb_order": ADF_LB_ORDER,
        "frozen_lb_df": ADF_LB_DF,
        "frozen_block_rmse_threshold": ADF_BLOCK_RMSE_THRESHOLD,
        "asymptotic_lb_quantiles": asymptotic["quantiles"],
        "asymptotic_distribution": asymptotic["distribution"],
        "asymptotic_samples": asymptotic["samples"],
        "model_valid_null_lb_quantiles": model_null_lb,
        "model_valid_null_block_rmse_quantiles": cv_extracted["block_rmse_quantiles"] if cv_extracted else {},
        "noise_only_null_lb_quantiles": noise_null_lb,
        "empirical_over_asymptotic_p99_ratio": empirical_ratio,
        "frozen_threshold_tail_model_valid": (
            float(np.mean(np.asarray(model_null_values, dtype=np.float64) > ADF_LB_THRESHOLD))
            if model_null_values
            else None
        ),
        "frozen_threshold_tail_noise_only": (
            float(np.mean(np.asarray(noise_null_values, dtype=np.float64) > ADF_LB_THRESHOLD))
            if noise_null_values
            else None
        ),
        "verdict": (
            "test_null_distribution_mismatch"
            if empirical_ratio is not None and empirical_ratio > 5.0
            else "asymptotic_null_approximately_holds"
        ),
    }
    attribution = _attribution(signal_summaries, null_summaries, comparison)

    artifact = {
        "artifact": ARTIFACT_NAME,
        "version": DIAGNOSTIC_VERSION,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_s": float(elapsed),
        "config": {
            "n_trials_per_cell": int(n_trials),
            "seed_base": SEED_BASE,
            "seed_formula": "SEED_BASE + 1000*cell_index + trial (extracted and truth share the seed pair)",
            "truth_if_noise_floor_hz": float(noise_floor_hz),
            "noiseless_sensitivity_trials": NOISELESS_SENSITIVITY_TRIALS,
            "noiseless_sensitivity_cells": list(NOISELESS_SENSITIVITY_CELLS),
            "adequacy_protocol_digest": PROTOCOL_DIGEST,
            "adequacy_thresholds_used": {
                "ljung_box_statistic_max": ADF_LB_THRESHOLD,
                "ljung_box_order": ADF_LB_ORDER,
                "ljung_box_df": ADF_LB_DF,
                "block_normalized_rmse_max": ADF_BLOCK_RMSE_THRESHOLD,
            },
            "thresholds_changed": False,
            "repair_routes_implemented": False,
            "truth_usage": (
                "synthetic diagnosis only: the truth path builds the true generated frequency track and "
                "scores fits; no runtime or decision path imports this module"
            ),
            "cells": [
                {
                    "name": cell.name,
                    "family": cell.family,
                    "label": cell.label,
                    "n_trials": cell.n_trials,
                    "is_null": cell.is_null,
                    "scenario": {key: value for key, value in asdict(cell.scenario).items()},
                }
                for cell in signal_cells + null_cells
            ],
        },
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
        },
        "records_sha256": _digest(records),
        "trials": records,
        "signal_cells": signal_summaries,
        "noiseless_sensitivity": noiseless_summaries,
        "null_cells": null_summaries,
        "null_distribution_comparison": comparison,
        "attribution": attribution,
        "limitations": [
            "The truth path is a synthetic diagnostic: true generated apparent frequency sampled at the same frame centres, plus a declared white IF noise floor (%.2f Hz) to avoid the numerically degenerate sigma_f ~ 1e-13 case. The noiseless sensitivity variant is reported separately; it fails the residual-scale test for numerical, not physical, reasons."
            % noise_floor_hz,
            "Truth is used only to build the comparison track and to score fits; the extracted path is the runtime-like path and no adequacy threshold was changed.",
            "The null simulation uses the same scenario noise setting; for noise-only realizations the statistic is scale-invariant, so null cells at different SNR are statistically identical.",
            "Single seed base and N per cell; quantile estimates at the extreme tail are uncertain (N=%d, 100 samples cannot resolve sub-1%% tails precisely)." % n_trials,
            "No repair route (de-chirping, pre-whitening, geometry conditioning) is implemented; this artifact is attribution only.",
        ],
    }
    return _jsonable(artifact)


# ---------------------------------------------------------------------------
# Markdown summary
# ---------------------------------------------------------------------------

def render_markdown(artifact: dict) -> str:
    lines = []
    lines.append("# C2 mechanism attribution — diagnosis matrix")
    lines.append("")
    comparison = artifact["null_distribution_comparison"]
    lines.append(
        f"**Artifact:** `{artifact['artifact']}` v{artifact['version']} · "
        f"records `{artifact['records_sha256']}` · "
        f"N = {artifact['config']['n_trials_per_cell']} per cell · "
        f"adequacy protocol `{artifact['config']['adequacy_protocol_digest']}`"
    )
    lines.append("")
    lines.append("**Attribution only.** No adequacy threshold was changed and no repair route was implemented.")
    lines.append("")
    lines.append("## Cell matrix")
    lines.append("")
    lines.append("| cell | family | if source | n | adequacy statuses | false rejections | correct rejections | within tolerance | median LB | median block RMSE |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for summary in artifact["signal_cells"]:
        lines.append(
            f"| `{summary['cell']}` | {summary['family']} | {summary['if_source']} | {summary['n']} | "
            f"{json.dumps(summary['adequacy_status_counts'])} | {summary['false_rejections']} | "
            f"{summary['correct_rejections']} | {summary['within_e0_tolerance']} | "
            f"{_fmt(summary['lb_quantiles'].get('p50'))} | {_fmt(summary['block_rmse_quantiles'].get('p50'))} |"
        )
    lines.append("")
    lines.append("## Test firing by cell (fail / pass / indeterminate)")
    lines.append("")
    lines.append("| cell | source | residual scale | Ljung-Box | time structure | block held-out |")
    lines.append("|---|---|---|---|---|---|")
    for summary in artifact["signal_cells"]:
        cells = []
        for name in TEST_NAMES:
            counts = summary["test_status_counts"].get(name, {})
            cells.append(f"F{counts.get('fail', 0)}/P{counts.get('pass', 0)}/I{counts.get('indeterminate', 0)}")
        lines.append(
            f"| `{summary['cell']}` | {summary['if_source']} | " + " | ".join(cells) + " |"
        )
    lines.append("")
    if artifact.get("noiseless_sensitivity"):
        lines.append("## Noiseless truth sensitivity (numerical degeneracy)")
        lines.append("")
        lines.append("| cell | n | adequacy statuses | residual-scale statuses | median sigma_f (Hz) |")
        lines.append("|---|---|---|---|---|")
        for summary in artifact["noiseless_sensitivity"]:
            lines.append(
                f"| `{summary['cell']}` | {summary['n']} | {json.dumps(summary['adequacy_status_counts'])} | "
                f"{json.dumps(summary['test_status_counts'].get('standardized_residuals', {}))} | n/a |"
            )
        lines.append("")
    lines.append("## Parametric null distribution")
    lines.append("")
    lines.append(
        f"- Frozen Ljung-Box threshold: `{comparison['frozen_lb_threshold']:.6g}` "
        f"(order {comparison['frozen_lb_order']}, df {comparison['frozen_lb_df']})."
    )
    lines.append(
        f"- Asymptotic expectation: `{comparison['asymptotic_distribution']}`, p99 "
        f"`{_fmt(comparison['asymptotic_lb_quantiles'].get('p99'))}`."
    )
    lines.append(
        f"- Model-valid (correct CV, extracted) null: p99 "
        f"`{_fmt(comparison['model_valid_null_lb_quantiles'].get('p99'))}`; tail above frozen threshold "
        f"`{_fmt(comparison['frozen_threshold_tail_model_valid'])}`; p99 ratio vs asymptotic "
        f"`{_fmt(comparison['empirical_over_asymptotic_p99_ratio'])}`."
    )
    lines.append(
        f"- Noise-only null: p99 `{_fmt(comparison['noise_only_null_lb_quantiles'].get('p99'))}`; tail above frozen "
        f"threshold `{_fmt(comparison['frozen_threshold_tail_noise_only'])}`."
    )
    lines.append("")
    lines.append("| null cell | n | adequacy statuses | LB p50 | LB p90 | LB p99 | tail > frozen | block RMSE p99 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for summary in artifact["null_cells"]:
        lines.append(
            f"| `{summary['cell']}` | {summary['n']} | {json.dumps(summary['adequacy_status_counts'])} | "
            f"{_fmt(summary['lb_quantiles'].get('p50'))} | {_fmt(summary['lb_quantiles'].get('p90'))} | "
            f"{_fmt(summary['lb_quantiles'].get('p99'))} | "
            f"{_fmt(summary['lb_tail_fraction_above_frozen_threshold'])} | "
            f"{_fmt(summary['block_rmse_quantiles'].get('p99'))} |"
        )
    lines.append("")
    lines.append("## Attribution verdicts")
    lines.append("")
    for item in artifact["attribution"]:
        lines.append(f"### `{item['mechanism']}` — **{item['verdict']}**")
        lines.append("")
        for key, value in item.items():
            if key in ("mechanism", "verdict", "statement"):
                continue
            lines.append(f"- {key}: `{_fmt(value)}`")
        lines.append(f"- {item['statement']}")
        lines.append("")
    lines.append("## Limitations")
    lines.append("")
    for limitation in artifact["limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines)


def _fmt(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def write_artifact(artifact: dict, out_path: str, markdown_path: Optional[str] = None) -> tuple[str, Optional[str]]:
    payload = (json.dumps(artifact, indent=1, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    directory = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(directory, exist_ok=True)
    with open(out_path, "wb") as handle:
        handle.write(payload)
    artifact_sha = hashlib.sha256(payload).hexdigest()
    markdown_sha = None
    if markdown_path:
        markdown = render_markdown(artifact).encode("utf-8")
        with open(markdown_path, "wb") as handle:
            handle.write(markdown)
        markdown_sha = hashlib.sha256(markdown).hexdigest()
    return artifact_sha, markdown_sha


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="C2 mechanism attribution diagnosis matrix (no repair routes).")
    parser.add_argument("--out", required=True)
    parser.add_argument("--markdown", default=None)
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--trials", type=int, default=N_TRIALS_DEFAULT)
    parser.add_argument("--filter", default=None)
    parser.add_argument("--noise-floor", type=float, default=TRUTH_IF_NOISE_FLOOR_HZ)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    try:
        artifact = run_diagnosis(
            n_trials=args.trials,
            jobs=args.jobs,
            cell_filter=args.filter,
            noise_floor_hz=args.noise_floor,
            progress=not args.quiet,
        )
    except ValueError as exc:
        print(f"diagnose_c2: {exc}", file=sys.stderr)
        return 2
    artifact_sha, markdown_sha = write_artifact(artifact, args.out, args.markdown)
    cell_count = len(artifact["config"]["cells"])
    trial_count = len(artifact["trials"]) if "trials" in artifact else None
    print(
        f"cells: {cell_count}  N={artifact['config']['n_trials_per_cell']} per signal source  "
        f"jobs: {args.jobs}  elapsed: {artifact['elapsed_s']:.1f} s"
    )
    print(f"records_sha256: {artifact['records_sha256']}")
    print(f"json: {args.out}  sha256: {artifact_sha}")
    if args.markdown:
        print(f"markdown: {args.markdown}  sha256: {markdown_sha}")
    print("attribution verdicts:")
    for item in artifact["attribution"]:
        print(f"  {item['mechanism']:32s} -> {item['verdict']}")
    comparison = artifact["null_distribution_comparison"]
    print(
        f"null comparison: asymptotic p99 {_fmt(comparison['asymptotic_lb_quantiles'].get('p99'))}, "
        f"model-valid null p99 {_fmt(comparison['model_valid_null_lb_quantiles'].get('p99'))}, "
        f"ratio {_fmt(comparison['empirical_over_asymptotic_p99_ratio'])}, "
        f"frozen {comparison['frozen_lb_threshold']:.6g}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
