"""C2-A / C2-B experiment runner.

C2-A: extraction-error analysis over the chirp-rate/geometry continuum and the
empirical error model artifact (``error_model.json``).

C2-B: noise-matched control paths on the same correct-CV high-chirp scenarios
(``noise_matched.json``): ideal frequency, ideal + white noise matched to the
measured error RMS, ideal + empirical front-end error structure, and full
waveform extraction.

Nothing here changes adequacy thresholds, implements B1/B2/B3, or feeds truth
into a runtime decision.  Truth is used only in this synthetic diagnosis.
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

from . import measurement_model as mm
from .adequacy import evaluate_adequacy
from .experiment import BASE
from .features import estimate_if_track
from .fit_hardened import fit_hardened
from .measurement_model import (
    ACF_LAGS,
    GEOMETRY_M,
    N_PER_CELL,
    SEED_BASE,
    SNR_LEVELS_DB,
    SPEEDS_M_S,
    TIME_BINS,
    WINDOW_FRAME_LENGTHS,
    WINDOW_SWEEP_CELLS,
    WINDOW_SWEEP_N,
    EmpiricalErrorModel,
    aggregate_cell,
    build_analysis_cells,
    build_error_model_artifact,
    cell_seed,
    chirp_bin_edges,
    conditional_error_by_chirp,
    conditional_residual_by_chirp,
    diagnostic_relationships,
    extract_error_track,
    snr_dependence,
    summarise_track,
    window_length_sweep,
    write_json,
)
from .synthetic import Scenario, apparent_frequency, generate

C2B_SEED_BASE = 70_900_000
# four exact C2-A measured geometries (in-sample isolation of mechanism) plus one held-out geometry
C2B_GEOMETRIES_M = tuple(
    [GEOMETRY_M[index] for index in (1, 2, 4, 6)] + [150.0]
)
C2B_SPEED_M_S = 250.0
C2B_SNR_DB = 20.0
C2B_N_TRIALS = 20
C2B_SOURCES = ("ideal", "ideal_white_noise", "ideal_empirical_error", "waveform_extraction")
C2B_SOURCE_LABELS = {
    "ideal": "ideal generated frequency (near-noiseless; may be insufficient_evidence)",
    "ideal_white_noise": "ideal + known independent white noise matched to the measured error RMS",
    "ideal_empirical_error": "ideal + empirical front-end error structure from C2-A (bias + AR(1))",
    "waveform_extraction": "full waveform -> frozen front end extraction",
}
C2B_SEED_FORMULA = "C2B_SEED_BASE + 1000*geometry_index + trial (all four sources share the seed)"


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


# ---------------------------------------------------------------------------
# C2-A
# ---------------------------------------------------------------------------

def _c2a_worker(task: tuple[dict, int]) -> dict:
    cell, trial = task
    scenario = Scenario(
        f0=BASE.f0,
        v=float(cell["speed_m_s"]),
        b=float(cell["geometry_m"]),
        t0=BASE.t0,
        duration=BASE.duration,
        fs=BASE.fs,
        c=BASE.c,
        snr_db=float(cell["snr_db"]),
        seed=cell_seed(cell["cell_index"], trial),
    )
    sample = extract_error_track(scenario)
    summary = summarise_track(sample)
    return {
        "cell_id": cell["cell_id"],
        "cell_index": int(cell["cell_index"]),
        "trial": int(trial),
        "seed": int(scenario.seed),
        "summary": summary,
        "sample": sample,
    }


def _run_c2a_trials(jobs: int, progress: bool = True) -> list[dict]:
    cells = build_analysis_cells()
    tasks = [(cell, trial) for cell in cells for trial in range(N_PER_CELL)]
    results: list[dict] = []
    if jobs <= 1:
        for position, task in enumerate(tasks):
            results.append(_c2a_worker(task))
            if progress and (position + 1) % 100 == 0:
                print(f"  ... C2-A {position + 1}/{len(tasks)}", file=sys.stderr)
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            for position, result in enumerate(pool.map(_c2a_worker, tasks, chunksize=4)):
                results.append(result)
                if progress and (position + 1) % 100 == 0:
                    print(f"  ... C2-A {position + 1}/{len(tasks)}", file=sys.stderr)
    return results


def run_c2a(jobs: int = 1, progress: bool = True) -> dict:
    started = time.time()
    cells = build_analysis_cells()
    results = _run_c2a_trials(jobs, progress=progress)
    by_cell: dict[str, list[dict]] = {}
    for result in results:
        by_cell.setdefault(result["cell_id"], []).append(result)
    aggregates = []
    for cell in cells:
        cell_results = by_cell.get(cell["cell_id"], [])
        samples = [result["sample"] for result in cell_results]
        summaries = [result["summary"] for result in cell_results]
        aggregates.append(aggregate_cell(cell, samples, summaries))
    residual_templates = {}
    for cell in cells:
        cell_results = by_cell.get(cell["cell_id"], [])
        if not cell_results:
            continue
        sample = cell_results[0]["sample"]
        summary = cell_results[0]["summary"]
        times = np.asarray(sample["times"], dtype=np.float64)
        normalised = (times - times[0]) / max(times[-1] - times[0], 1e-12)
        bin_index = np.minimum((normalised * TIME_BINS).astype(int), TIME_BINS - 1)
        bias = np.array(
            [summary["bias_profile"][index] if summary["bias_profile"][index] is not None else 0.0 for index in range(TIME_BINS)]
        )
        residual = np.asarray(sample["error"], dtype=np.float64) - bias[bin_index]
        residual_templates[cell["cell_id"]] = {
            "normalised_time": [float(value) for value in normalised],
            "residual": [float(value) for value in residual],
        }
    all_samples = [result["sample"] for result in results]
    chirp_bins = conditional_error_by_chirp(all_samples)
    residual_by_chirp = conditional_residual_by_chirp(all_samples)
    for chirp_bin, residual_bin in zip(chirp_bins, residual_by_chirp):
        chirp_bin["residual_std_hz"] = residual_bin["residual_std_hz"]
        chirp_bin["residual_acf"] = residual_bin["residual_acf"]
    relationships = diagnostic_relationships(all_samples)
    snr_table = snr_dependence(aggregates)

    window_sweep = []
    for frame_len in WINDOW_FRAME_LENGTHS:
        window_sweep.extend(
            window_length_sweep(int(frame_len), int(frame_len) // 2, cells, WINDOW_SWEEP_N)
        )

    structural_fractions = [
        aggregate["structural_fraction"] for aggregate in aggregates if aggregate.get("structural_fraction") is not None
    ]
    residual_ar1_values = [
        aggregate["residual_ar1_median"] for aggregate in aggregates if aggregate.get("residual_ar1_median") is not None
    ]
    correlation_times = [
        aggregate["correlation_time_s_median"]
        for aggregate in aggregates
        if aggregate.get("correlation_time_s_median") is not None
    ]
    diagnostics = {
        "conditional_chirp_relationship": relationships,
        "snr_dependence": snr_table,
        "time_position": {
            "time_bins": TIME_BINS,
            "max_abs_time_bin_bias_median_hz": float(
                np.median(
                    [
                        max(abs(value) for value in aggregate["bias_profile"] if value is not None)
                        for aggregate in aggregates
                    ]
                )
            ),
            "bias_profile_range_median_hz": float(
                np.median(
                    [
                        max(value for value in aggregate["bias_profile"] if value is not None)
                        - min(value for value in aggregate["bias_profile"] if value is not None)
                        for aggregate in aggregates
                    ]
                )
            ),
            "note": (
                "the deterministic error component is largely a time-position / frame-phase effect: the pooled "
                "E[e|chirp] is near zero while per-track bias profiles vary in time"
            ),
        },
        "structural_vs_noise": {
            "structural_fraction_median": float(np.median(structural_fractions)) if structural_fractions else None,
            "structural_fraction_min": float(np.min(structural_fractions)) if structural_fractions else None,
            "structural_fraction_max": float(np.max(structural_fractions)) if structural_fractions else None,
            "residual_acf_lag1_median": float(np.median(residual_ar1_values)) if residual_ar1_values else None,
            "correlation_time_s_median": float(np.median(correlation_times)) if correlation_times else None,
            "verdict": (
                "structural_error_dominant"
                if structural_fractions and float(np.median(structural_fractions)) > 0.5
                else "noise_dominant_or_mixed"
            ),
            "chirp_rate_explanation": (
                "E[e|chirp rate] is near zero and the |chirp| linear model explains little variance; the "
                "deterministic component is better described by time-position/frame-phase structure than by a "
                "single chirp-rate mean"
            ),
            "note": (
                "structural_fraction = var(seed-averaged e) / var(e); residual_acf_lag1 is the ACF of e after "
                "removing the per-cell time-bin bias"
            ),
        },
        "heteroscedasticity": {
            "median_ratio": float(
                np.median(
                    [
                        aggregate["heteroscedasticity_ratio_median"]
                        for aggregate in aggregates
                        if aggregate.get("heteroscedasticity_ratio_median") is not None
                    ]
                )
            )
            if any(aggregate.get("heteroscedasticity_ratio_median") is not None for aggregate in aggregates)
            else None,
            "note": "ratio of max to min per-time-bin error std within a track",
        },
        "window_length_sweep": {
            "available": True,
            "front_end_parameter": "frame_len (Hann STFT analysis window); hop = frame_len/2",
            "frame_lengths": list(WINDOW_FRAME_LENGTHS),
            "note": "the front end exposes analysis frame length, not observation-duration windows",
        },
    }

    record_payload = [
        {
            "cell_id": result["cell_id"],
            "trial": result["trial"],
            "seed": result["seed"],
            "summary": result["summary"],
        }
        for result in sorted(results, key=lambda item: (item["cell_id"], item["trial"]))
    ]
    artifact = build_error_model_artifact(
        cells=aggregates,
        chirp_bins=chirp_bins,
        diagnostics=diagnostics,
        window_sweep=window_sweep,
        environment={
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
        },
        records_sha256=_digest(record_payload),
        residual_templates=residual_templates,
        limitations=[
            "The extraction-error model is descriptive, not causal: it reports measured e(t) structure over the declared synthetic design.",
            "Truth frequency is used only to compute e(t) in synthetic diagnosis; no runtime/decision path imports this module.",
            "The front end exposes analysis frame length (256/512/1024 samples), not observation-duration windows; the window sweep is limited to the exposed parameter.",
            "Cells use 3 independent noise seeds; the structural fraction is a finite-sample estimate.",
            "The empirical generator uses a measured residual bootstrap template (preferred) or an AR(1) fallback; the template preserves the measured correlation shape of one seed, so it is an empirical resampling, not a causal model.",
        ],
    )
    artifact["generated_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    artifact["elapsed_s"] = float(time.time() - started)
    return _jsonable(artifact)


# ---------------------------------------------------------------------------
# C2-B
# ---------------------------------------------------------------------------

def _c2b_worker(task: tuple[int, float, int, dict, dict]) -> list[dict]:
    geometry_index, geometry, trial, error_model_artifact, rms_by_geometry = task
    seed = int(C2B_SEED_BASE) + 1000 * int(geometry_index) + int(trial)
    scenario = Scenario(
        f0=BASE.f0,
        v=C2B_SPEED_M_S,
        b=float(geometry),
        t0=BASE.t0,
        duration=BASE.duration,
        fs=BASE.fs,
        c=BASE.c,
        snr_db=C2B_SNR_DB,
        seed=seed,
    )
    observation = generate(scenario)
    track = estimate_if_track(
        observation.signal,
        scenario.fs,
        frame_len=mm.FRONT_END_PARAMETERS["frame_len"],
        hop=mm.FRONT_END_PARAMETERS["hop"],
        f_min=mm.FRONT_END_PARAMETERS["f_min_hz"],
        f_max=mm.FRONT_END_PARAMETERS["f_max_hz"],
        t_start=float(observation.t[0]),
    )
    true_frequency = apparent_frequency(scenario, track.t)
    error_model = EmpiricalErrorModel.from_artifact(error_model_artifact)
    sigma_white = float(rms_by_geometry.get(geometry, 0.0))
    rng = np.random.default_rng(int(seed) + 31337)
    white = true_frequency + sigma_white * rng.standard_normal(true_frequency.size)
    empirical = true_frequency + error_model.generate(
        track.t, float(geometry), C2B_SPEED_M_S, C2B_SNR_DB, seed=int(seed)
    )
    sources = {
        "ideal": true_frequency,
        "ideal_white_noise": white,
        "ideal_empirical_error": empirical,
        "waveform_extraction": track.f,
    }
    records = []
    for source_name, frequencies in sources.items():
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
        records.append(
            {
                "geometry_m": float(geometry),
                "geometry_index": int(geometry_index),
                "trial": int(trial),
                "seed": int(seed),
                "source": source_name,
                "sigma_white_hz": float(sigma_white),
                "hardened": {
                    "sigma_f_hz": float(hardened.sigma_f_hz),
                    "optimization_status": hardened.optimization_status,
                },
                "adequacy": {
                    "model_adequacy_status": adequacy["model_adequacy_status"],
                    "identifiability_status": adequacy["identifiability_status"],
                    "tests": {
                        name: {
                            "status": adequacy["tests"][name]["status"],
                            "ljung_box": adequacy["tests"][name]["metrics"].get("ljung_box_statistic"),
                            "median_normalized_rmse": adequacy["tests"][name]["metrics"].get("median_normalized_rmse"),
                        }
                        for name in ("standardized_residuals", "autocorrelation", "time_structure", "block_prediction")
                    },
                },
            }
        )
    return records


def _counts(values) -> dict:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def run_c2b(error_model_artifact: dict, jobs: int = 1, progress: bool = True) -> dict:
    started = time.time()
    cells_by_geometry = {aggregate["geometry_m"]: aggregate for aggregate in error_model_artifact["cells"] if aggregate["speed_m_s"] == C2B_SPEED_M_S and aggregate["snr_db"] == C2B_SNR_DB}
    rms_by_geometry = {}
    for geometry in C2B_GEOMETRIES_M:
        if geometry in cells_by_geometry:
            rms_by_geometry[geometry] = cells_by_geometry[geometry]["rms_hz"]
        else:
            # nearest measured geometry with the same speed/SNR
            nearest = min(cells_by_geometry.values(), key=lambda cell: abs(cell["geometry_m"] - geometry))
            rms_by_geometry[geometry] = nearest["rms_hz"]
    tasks = [
        (index, geometry, trial, error_model_artifact, rms_by_geometry)
        for index, geometry in enumerate(C2B_GEOMETRIES_M)
        for trial in range(C2B_N_TRIALS)
    ]
    records: list[dict] = []
    if jobs <= 1:
        for position, task in enumerate(tasks):
            records.extend(_c2b_worker(task))
            if progress and (position + 1) % 50 == 0:
                print(f"  ... C2-B {position + 1}/{len(tasks)}", file=sys.stderr)
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            for position, result in enumerate(pool.map(_c2b_worker, tasks, chunksize=2)):
                records.extend(result)
                if progress and (position + 1) % 50 == 0:
                    print(f"  ... C2-B {position + 1}/{len(tasks)}", file=sys.stderr)
    records.sort(key=lambda record: (record["geometry_m"], record["trial"], record["source"]))

    summaries = []
    for source in C2B_SOURCES:
        subset = [record for record in records if record["source"] == source]
        per_geometry = []
        for geometry in C2B_GEOMETRIES_M:
            geometry_subset = [record for record in subset if record["geometry_m"] == geometry]
            per_geometry.append(
                {
                    "geometry_m": geometry,
                    "n": len(geometry_subset),
                    "adequacy_status_counts": _counts(record["adequacy"]["model_adequacy_status"] for record in geometry_subset),
                    "false_rejections": sum(
                        1 for record in geometry_subset if record["adequacy"]["model_adequacy_status"] == "discrepancy"
                    ),
                    "insufficient_evidence": sum(
                        1 for record in geometry_subset if record["adequacy"]["model_adequacy_status"] == "insufficient_evidence"
                    ),
                }
            )
        summaries.append(
            {
                "source": source,
                "label": C2B_SOURCE_LABELS[source],
                "n": len(subset),
                "adequacy_status_counts": _counts(record["adequacy"]["model_adequacy_status"] for record in subset),
                "false_rejections": sum(
                    1 for record in subset if record["adequacy"]["model_adequacy_status"] == "discrepancy"
                ),
                "insufficient_evidence": sum(
                    1 for record in subset if record["adequacy"]["model_adequacy_status"] == "insufficient_evidence"
                ),
                "test_fail_counts": {
                    name: _counts(record["adequacy"]["tests"][name]["status"] for record in subset)
                    for name in ("standardized_residuals", "autocorrelation", "time_structure", "block_prediction")
                },
                "median_ljung_box": float(
                    np.median(
                        [
                            record["adequacy"]["tests"]["autocorrelation"]["ljung_box"]
                            for record in subset
                            if record["adequacy"]["tests"]["autocorrelation"]["ljung_box"] is not None
                        ]
                    )
                )
                if subset
                else None,
                "median_sigma_f_hz": float(np.median([record["hardened"]["sigma_f_hz"] for record in subset]))
                if subset
                else None,
                "per_geometry": per_geometry,
            }
        )

    by_source = {summary["source"]: summary for summary in summaries}
    extracted_rate = by_source["waveform_extraction"]["false_rejections"] / max(1, by_source["waveform_extraction"]["n"])
    empirical_rate = by_source["ideal_empirical_error"]["false_rejections"] / max(1, by_source["ideal_empirical_error"]["n"])
    white_rate = by_source["ideal_white_noise"]["false_rejections"] / max(1, by_source["ideal_white_noise"]["n"])
    ideal_rate = by_source["ideal"]["false_rejections"] / max(1, by_source["ideal"]["n"])
    reproduction_fraction = empirical_rate / extracted_rate if extracted_rate > 0.0 else None
    per_geometry_reproduction = []
    for index, geometry in enumerate(C2B_GEOMETRIES_M):
        extracted_row = by_source["waveform_extraction"]["per_geometry"][index]
        empirical_row = by_source["ideal_empirical_error"]["per_geometry"][index]
        extracted_geometry_rate = extracted_row["false_rejections"] / max(1, extracted_row["n"])
        empirical_geometry_rate = empirical_row["false_rejections"] / max(1, empirical_row["n"])
        per_geometry_reproduction.append(
            {
                "geometry_m": geometry,
                "extracted_false_rejection_rate": extracted_geometry_rate,
                "empirical_false_rejection_rate": empirical_geometry_rate,
                "reproduction_fraction": (
                    empirical_geometry_rate / extracted_geometry_rate if extracted_geometry_rate > 0.0 else None
                ),
                "in_c2a_measured_grid": geometry in [float(value) for value in GEOMETRY_M],
            }
        )
    if abs(empirical_rate - extracted_rate) <= 0.15 and white_rate < 0.5 * max(extracted_rate, 1e-9):
        verdict = "structured_extraction_error_reproduces_rejections"
    elif abs(white_rate - extracted_rate) <= 0.15:
        verdict = "independent_noise_reproduces_rejections"
    elif extracted_rate >= 0.05 and 0.5 * extracted_rate <= empirical_rate < extracted_rate - 0.15 and white_rate < 0.05:
        verdict = "structured_extraction_error_partially_reproduces_rejections"
    elif extracted_rate >= 0.05 and empirical_rate < 0.05 and white_rate < 0.05:
        verdict = "unexplained_structural_mechanism"
    else:
        verdict = "inconclusive"
    attribution = {
        "false_rejection_rate_by_source": {
            "ideal": ideal_rate,
            "ideal_white_noise": white_rate,
            "ideal_empirical_error": empirical_rate,
            "waveform_extraction": extracted_rate,
        },
        "verdict": verdict,
        "reproduction_fraction_empirical_vs_extracted": reproduction_fraction,
        "per_geometry_reproduction": per_geometry_reproduction,
        "statement": {
            "structured_extraction_error_reproduces_rejections": (
                "The empirical front-end error structure reproduces the extracted-frequency false-rejection rate; "
                "ideal and white-noise-matched controls do not. The excess rejections are attributable to the "
                "structured extraction error (bias/correlation), not to independent noise or the physical model."
            ),
            "structured_extraction_error_partially_reproduces_rejections": (
                "The empirical bias+residual-template control reproduces only part of the extracted-frequency false "
                "rejections (and white noise reproduces less); the simple empirical error model is insufficient, so an "
                "additional chirp-dependent structure (e.g. geometry-dependent bias or longer-memory correlation) is "
                "missing from the model. This is a negative model-characterisation result, not a threshold issue."
            ),
            "independent_noise_reproduces_rejections": (
                "Independent white noise matched to the measured error RMS reproduces the rejections; the bias/correlation "
                "structure is not required in this sample."
            ),
            "unexplained_structural_mechanism": (
                "Full extraction rejects but both noise-matched controls do not; the mechanism is not captured by the "
                "empirical bias+AR(1) model or white noise alone."
            ),
            "inconclusive": "The four-source comparison does not separate the mechanisms in this sample.",
        }[verdict],
        "near_noiseless_note": (
            "The ideal source is near-noiseless (sigma_f ~ 1e-13); its adequacy status is expected to be "
            "insufficient_evidence, not a false rejection. No artificial noise was added to force significance."
        ),
    }
    artifact = {
        "artifact": "c2b-noise-matched-controls",
        "version": "1.0.0",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_s": float(time.time() - started),
        "config": {
            "seed_base": C2B_SEED_BASE,
            "seed_formula": C2B_SEED_FORMULA,
            "geometry_m": list(C2B_GEOMETRIES_M),
            "speed_m_s": C2B_SPEED_M_S,
            "snr_db": C2B_SNR_DB,
            "n_trials_per_geometry": C2B_N_TRIALS,
            "sources": list(C2B_SOURCES),
            "error_model_id": error_model_artifact["empirical_model"]["model_id"],
            "error_model_records_sha256": error_model_artifact["records_sha256"],
            "thresholds_changed": False,
            "repair_routes_implemented": False,
            "truth_usage": "synthetic diagnosis only; never imported by a runtime/decision path",
        },
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
        },
        "records_sha256": _digest(records),
        "summary": summaries,
        "attribution": attribution,
        "limitations": [
            "All four sources share the same scenario and seed, but waveform extraction is the only source that includes the actual noise realization and front-end pipeline; the other sources are synthetic controls.",
            "The white-noise control uses a declared Gaussian noise scaled to the measured extraction-error RMS (matched variance, no structure).",
            "The empirical control uses a bias profile plus AR(1) residual; it reproduces bias, variance and lag-1 correlation, not all higher-order structure.",
            "The ideal source is numerically degenerate (sigma_f ~ 1e-13); insufficient_evidence is accepted and no noise was added to force a decision.",
            "The scenario is a correct constant-velocity model, so any discrepancy is a false rejection by construction.",
        ],
    }
    return _jsonable(artifact)


# ---------------------------------------------------------------------------
# Markdown summaries
# ---------------------------------------------------------------------------

def _fmt(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def render_error_model_markdown(artifact: dict) -> str:
    lines = ["# C2-A extraction-error model", ""]
    lines.append(
        f"**Artifact:** `{artifact['artifact']}` v{artifact['version']} · records `{artifact['records_sha256']}` · "
        f"measurement model `{artifact['measurement_model']['id']}` v{artifact['measurement_model']['version']}"
    )
    lines.append("")
    lines.append(
        "Diagnostic only: `e(t) = f_hat(t) - f_true(t)` over a geometry/SNR continuum; truth is never used by a runtime path."
    )
    lines.append("")
    lines.append("## Systematic error by chirp bin")
    lines.append("")
    lines.append("| chirp bin (Hz/s) | n samples | mean e (Hz) | std e (Hz) | RMS e (Hz) | mean abs f̈ | residual std (Hz) | residual ACF lag1 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for chirp_bin in artifact["chirp_bins"]:
        residual_acf = chirp_bin.get("residual_acf") or {}
        lines.append(
            f"| {chirp_bin['chirp_low_hz_s']:g}–{chirp_bin['chirp_high_hz_s']:g} | {chirp_bin['n_samples']} | "
            f"{_fmt(chirp_bin['mean_error_hz'])} | {_fmt(chirp_bin['std_error_hz'])} | {_fmt(chirp_bin['rms_error_hz'])} | "
            f"{_fmt(chirp_bin['mean_abs_chirp_acceleration'])} | {_fmt(chirp_bin.get('residual_std_hz'))} | "
            f"{_fmt(residual_acf.get('lag_1'))} |"
        )
    lines.append("")
    lines.append("## Cell summary by geometry and SNR")
    lines.append("")
    lines.append("| geometry (m) | speed (m/s) | SNR (dB) | bias (Hz) | RMS (Hz) | std (Hz) | structural fraction | corr. time (s) | heterosc. ratio |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for cell in artifact["cells"]:
        lines.append(
            f"| {cell['geometry_m']:g} | {cell['speed_m_s']:g} | {cell['snr_db']:g} | {_fmt(cell['bias_hz'])} | "
            f"{_fmt(cell['rms_hz'])} | {_fmt(cell['std_hz'])} | {_fmt(cell['structural_fraction'])} | "
            f"{_fmt(cell['correlation_time_s_median'])} | {_fmt(cell['heteroscedasticity_ratio_median'])} |"
        )
    lines.append("")
    lines.append("## Diagnostics")
    lines.append("")
    diagnostics = artifact["diagnostics"]
    relationship = diagnostics["conditional_chirp_relationship"]
    lines.append(f"- {relationship['model']}")
    lines.append(f"  - R² = {_fmt(relationship['r_squared'])}; correlations: {json.dumps(relationship['correlation'])}")
    lines.append(
        f"- Structural vs noise: {diagnostics['structural_vs_noise']['verdict']} "
        f"(structural fraction median {_fmt(diagnostics['structural_vs_noise']['structural_fraction_median'])}, "
        f"residual ACF lag1 median {_fmt(diagnostics['structural_vs_noise']['residual_acf_lag1_median'])})"
    )
    lines.append(
        f"- Heteroscedasticity: median max/min time-bin std ratio {_fmt(diagnostics['heteroscedasticity']['median_ratio'])}"
    )
    lines.append("- SNR dependence (same geometry/speed):")
    for row in diagnostics["snr_dependence"]:
        lines.append(
            f"  - b={row['geometry_m']:g} m, v={row['speed_m_s']:g} m/s: bias {_fmt(row['bias_low_hz'])} → "
            f"{_fmt(row['bias_high_hz'])} Hz, RMS {_fmt(row['rms_low_hz'])} → {_fmt(row['rms_high_hz'])} Hz"
        )
    lines.append("")
    lines.append("## Analysis-window length sweep")
    lines.append("")
    lines.append("| frame_len | geometry (m) | speed (m/s) | bias (Hz) | RMS (Hz) |")
    lines.append("|---|---|---|---|---|")
    for row in artifact["window_sweep"]:
        lines.append(
            f"| {row['frame_len']} | {row['geometry_m']:g} | {row['speed_m_s']:g} | {_fmt(row['bias_hz'])} | {_fmt(row['rms_hz'])} |"
        )
    lines.append("")
    lines.append("## Empirical error model")
    lines.append("")
    model = artifact["empirical_model"]
    lines.append(f"- Model id: `{model['model_id']}`")
    lines.append(f"- {model['description']}")
    lines.append(f"- Seed policy: {model['seed_policy']}")
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    for limitation in artifact["limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines)


def render_noise_matched_markdown(artifact: dict) -> str:
    lines = ["# C2-B noise-matched control paths", ""]
    lines.append(
        f"**Artifact:** `{artifact['artifact']}` v{artifact['version']} · records `{artifact['records_sha256']}` · "
        f"error model `{artifact['config']['error_model_id']}`"
    )
    lines.append("")
    lines.append("Four observation sources on the same correct-CV high-chirp scenarios, same seed per trial.")
    lines.append("")
    lines.append("| source | n | false rejections | insufficient_evidence | median Ljung–Box | median sigma_f (Hz) |")
    lines.append("|---|---|---|---|---|---|")
    for summary in artifact["summary"]:
        lines.append(
            f"| `{summary['source']}` | {summary['n']} | {summary['false_rejections']} | "
            f"{summary['insufficient_evidence']} | {_fmt(summary['median_ljung_box'])} | {_fmt(summary['median_sigma_f_hz'])} |"
        )
    lines.append("")
    lines.append("## False rejections by geometry")
    lines.append("")
    geometries = [row["geometry_m"] for row in artifact["summary"][0]["per_geometry"]]
    lines.append("| geometry (m) | " + " | ".join(f"`{source}`" for source in C2B_SOURCES) + " |")
    lines.append("|---|" + "---|" * len(C2B_SOURCES))
    for index, geometry in enumerate(geometries):
        cells = []
        for summary in artifact["summary"]:
            row = summary["per_geometry"][index]
            cells.append(f"{row['false_rejections']}/{row['n']} (insuff {row['insufficient_evidence']})")
        lines.append(f"| {geometry:g} | " + " | ".join(cells) + " |")
    lines.append("")
    attribution = artifact["attribution"]
    lines.append("## Attribution")
    lines.append("")
    lines.append(f"- Verdict: **{attribution['verdict']}**")
    lines.append(f"- {attribution['statement']}")
    lines.append(f"- False-rejection rates: {json.dumps(attribution['false_rejection_rate_by_source'])}")
    lines.append(f"- {attribution['near_noiseless_note']}")
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    for limitation in artifact["limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines)


def write_summary(path: str, markdown: str) -> str:
    payload = markdown.encode("utf-8")
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(payload)
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="C2-A extraction-error model and C2-B noise-matched controls.")
    parser.add_argument("--part", choices=("a", "b", "all"), default="all")
    parser.add_argument("--out-dir", default="/tmp/c2a")
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    os.makedirs(args.out_dir, exist_ok=True)
    progress = not args.quiet

    error_model = None
    if args.part in ("a", "all"):
        error_model = run_c2a(jobs=args.jobs, progress=progress)
        error_json = os.path.join(args.out_dir, "error_model.json")
        error_md = os.path.join(args.out_dir, "error_model.md")
        error_sha = write_json(error_json, error_model)
        error_md_sha = write_summary(error_md, render_error_model_markdown(error_model))
        print(
            f"C2-A: cells={len(error_model['cells'])} chirp_bins={len(error_model['chirp_bins'])} "
            f"records={error_model['records_sha256']}"
        )
        print(f"  json: {error_json}  sha256: {error_sha}")
        print(f"  markdown: {error_md}  sha256: {error_md_sha}")
        diagnostics = error_model["diagnostics"]
        print(
            f"  structural vs noise: {diagnostics['structural_vs_noise']['verdict']} "
            f"(median structural fraction {_fmt(diagnostics['structural_vs_noise']['structural_fraction_median'])})"
        )
    if args.part in ("b", "all"):
        if error_model is None:
            error_path = os.path.join(args.out_dir, "error_model.json")
            with open(error_path, "r", encoding="utf-8") as handle:
                error_model = json.load(handle)
        noise = run_c2b(error_model, jobs=args.jobs, progress=progress)
        noise_json = os.path.join(args.out_dir, "noise_matched.json")
        noise_md = os.path.join(args.out_dir, "noise_matched.md")
        noise_sha = write_json(noise_json, noise)
        noise_md_sha = write_summary(noise_md, render_noise_matched_markdown(noise))
        print(f"C2-B: records={noise['records_sha256']} verdict={noise['attribution']['verdict']}")
        print(f"  json: {noise_json}  sha256: {noise_sha}")
        print(f"  markdown: {noise_md}  sha256: {noise_md_sha}")
        for summary in noise["summary"]:
            print(
                f"  {summary['source']:24s} false_rejections={summary['false_rejections']}/{summary['n']} "
                f"insufficient={summary['insufficient_evidence']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
