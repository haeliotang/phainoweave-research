"""Reference instantaneous-frequency estimator (non-competing path, ADR 0021 E.3).

A simple phase-difference estimator across STFT frames:

* same analysis frame (512 samples, Hann, hop 128) and search band as the E0
  front end;
* peak bin per frame selected from the magnitude spectrum;
* the fractional-bin offset is recovered from the phase advance between
  consecutive frames at that bin
  ``delta = wrap(dphi) / (2*pi) * N_FFT / hop``, so ``f = (k + delta) * fs/N_FFT``;
* phase difference is unambiguous for the high-chirp cells because the per-hop
  frequency change is < one bin (hop 128, N/hop = 4 -> +-2 bins).

Purpose: test whether the *representation* (magnitude-peak parabolic
interpolation, hop 256) is the limit.  This estimator is not part of B0-B3 and
does not touch adequacy thresholds.  Truth is used only to score the synthetic
evaluation.
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

from .adequacy import evaluate_adequacy
from .experiment import BASE, F_MAX, F_MIN, FRAME_LEN, HOP
from .features import estimate_if_track
from .fit_hardened import fit_hardened
from .synthetic import Scenario, apparent_frequency, generate

REFERENCE_ID = "phase-difference-stft-512h128"
REFERENCE_VERSION = "1.0.0"
REFERENCE_FRAME_LEN = 512
REFERENCE_HOP = 128
REFERENCE_SEED_BASE = 81_000_000
REFERENCE_N_TRIALS = 10
CORRECT_CV_GEOMETRIES_M = (150.0, 300.0, 600.0, 1200.0, 2400.0)
ACCELERATION_LEVELS_M_S2 = (0.2, 0.4)
ACCELERATION_GEOMETRY_M = 3000.0
ACCELERATION_SPEED_M_S = 250.0
SNR_DB = 20.0


def _wrap_phase(phase: np.ndarray) -> np.ndarray:
    return (np.asarray(phase, dtype=np.float64) + np.pi) % (2.0 * np.pi) - np.pi


def estimate_reference_track(
    signal: np.ndarray,
    fs: float,
    frame_len: int = REFERENCE_FRAME_LEN,
    hop: int = REFERENCE_HOP,
    f_min: float = F_MIN,
    f_max: float = F_MAX,
    t_start: float = 0.0,
) -> dict:
    """Phase-difference IF estimator; returns frame-centre times and frequencies."""
    x = np.asarray(signal, dtype=np.float64)
    if not (0 < hop <= frame_len):
        raise ValueError("require 0 < hop <= frame_len")
    if frame_len > x.size:
        raise ValueError("frame_len exceeds signal length")
    window = np.hanning(frame_len)
    n_frames = 1 + (x.size - frame_len) // hop
    idx = np.arange(n_frames) * hop
    frames = x[idx[:, None] + np.arange(frame_len)[None, :]]
    spectra = np.fft.rfft(frames * window[None, :], axis=1)
    magnitude = np.abs(spectra)
    bin_hz = fs / frame_len
    k_min = max(int(np.ceil(f_min / bin_hz)), 1)
    k_max = min(int(np.floor(f_max / bin_hz)), magnitude.shape[1] - 2)
    band = magnitude[:, k_min : k_max + 1]
    peak = np.argmax(band, axis=1) + k_min
    frequencies = np.empty(n_frames, dtype=np.float64)
    frequencies[0] = peak[0] * bin_hz
    ratio = float(frame_len) / float(hop)
    for frame in range(1, n_frames):
        k = int(peak[frame])
        phase_advance = np.angle(spectra[frame, k] * np.conj(spectra[frame - 1, k]))
        # Phase advance over the hop is 2*pi*f*hop/fs = 2*pi*(k + offset)*hop/N,
        # so the fractional-bin offset is (dphi/2pi)*(N/hop) - k.
        delta_total = float(phase_advance) / (2.0 * np.pi) * ratio
        offset = delta_total - float(k)
        offset = (offset + ratio / 2.0) % ratio - ratio / 2.0
        offset = max(-1.0, min(1.0, offset))
        frequencies[frame] = (k + offset) * bin_hz
    times = t_start + (idx + frame_len / 2.0) / fs
    return {
        "t": times,
        "f": frequencies,
        "frame_len": int(frame_len),
        "hop": int(hop),
        "fs": float(fs),
        "f_min": float(f_min),
        "f_max": float(f_max),
        "estimator": REFERENCE_ID,
    }


# ---------------------------------------------------------------------------
# Evaluation cells (high-chirp correct model + acceleration)
# ---------------------------------------------------------------------------

def build_reference_cells() -> list[dict]:
    cells = []
    index = 0
    for geometry in CORRECT_CV_GEOMETRIES_M:
        cells.append(
            {
                "cell_index": index,
                "cell_id": f"cv_b{geometry:g}_v250_snr20",
                "geometry_m": float(geometry),
                "speed_m_s": 250.0,
                "accel": 0.0,
                "snr_db": SNR_DB,
                "family": "correct_constant_velocity",
                "n_trials": REFERENCE_N_TRIALS,
            }
        )
        index += 1
    for accel in ACCELERATION_LEVELS_M_S2:
        cells.append(
            {
                "cell_index": index,
                "cell_id": f"accel_{accel:g}_b{ACCELERATION_GEOMETRY_M:g}",
                "geometry_m": ACCELERATION_GEOMETRY_M,
                "speed_m_s": ACCELERATION_SPEED_M_S,
                "accel": float(accel),
                "snr_db": SNR_DB,
                "family": "acceleration_misspecification",
                "n_trials": REFERENCE_N_TRIALS,
            }
        )
        index += 1
    return cells


def cell_seed(cell: dict, trial: int) -> int:
    return REFERENCE_SEED_BASE + 1000 * int(cell["cell_index"]) + int(trial)


def _worker(task: tuple[dict, int, str]) -> dict:
    cell, trial, estimator = task
    seed = cell_seed(cell, trial)
    scenario = Scenario(
        f0=BASE.f0,
        v=float(cell["speed_m_s"]),
        b=float(cell["geometry_m"]),
        t0=BASE.t0,
        duration=BASE.duration,
        fs=BASE.fs,
        c=BASE.c,
        accel=float(cell["accel"]),
        snr_db=float(cell["snr_db"]),
        seed=seed,
    )
    observation = generate(scenario)
    if estimator == "front_end":
        track = estimate_if_track(
            observation.signal,
            scenario.fs,
            frame_len=FRAME_LEN,
            hop=HOP,
            f_min=F_MIN,
            f_max=F_MAX,
            t_start=float(observation.t[0]),
        )
    elif estimator == "phase_difference":
        track = estimate_reference_track(observation.signal, scenario.fs, t_start=float(observation.t[0]))
    else:
        raise ValueError(f"unknown estimator {estimator!r}")
    if isinstance(track, dict):
        times = np.asarray(track["t"], dtype=np.float64)
        frequencies = np.asarray(track["f"], dtype=np.float64)
    else:
        times = np.asarray(track.t, dtype=np.float64)
        frequencies = np.asarray(track.f, dtype=np.float64)
    true_frequency = apparent_frequency(scenario, times)
    hardened = fit_hardened(times, frequencies, c=scenario.c)
    params = np.array([hardened.f0, hardened.v, hardened.t0, hardened.b], dtype=np.float64)
    adequacy = evaluate_adequacy(
        times,
        frequencies,
        params,
        hardened.sigma_f_hz,
        hardened.optimization_status,
        c=scenario.c,
    )
    return {
        "cell_id": cell["cell_id"],
        "family": cell["family"],
        "estimator": estimator,
        "trial": int(trial),
        "seed": int(seed),
        "n_frames": int(times.size),
        "sigma_f_hz": float(hardened.sigma_f_hz),
        "optimization_status": hardened.optimization_status,
        "adequacy_status": adequacy["model_adequacy_status"],
        "identifiability_status": adequacy["identifiability_status"],
        "ljung_box": adequacy["tests"]["autocorrelation"]["metrics"].get("ljung_box_statistic"),
        "error_rms_hz": float(np.sqrt(np.mean((frequencies - true_frequency) ** 2))),
        "error_bias_hz": float(np.mean(frequencies - true_frequency)),
        "parameter_rel_errors": {
            "f0": (hardened.f0 - scenario.f0) / scenario.f0,
            "v": (hardened.v - scenario.v) / scenario.v,
            "t0": (hardened.t0 - scenario.t0) / scenario.t0,
            "b": (hardened.b - scenario.b) / scenario.b,
        },
    }


def _counts(values) -> dict:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def evaluate_reference(jobs: int = 1, progress: bool = True) -> dict:
    started = time.time()
    cells = build_reference_cells()
    tasks = [(cell, trial, estimator) for cell in cells for trial in range(cell["n_trials"]) for estimator in ("front_end", "phase_difference")]
    records: list[dict] = []
    if jobs <= 1:
        for position, task in enumerate(tasks):
            records.append(_worker(task))
            if progress and (position + 1) % 50 == 0:
                print(f"  ... reference {position + 1}/{len(tasks)}", file=sys.stderr)
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            for position, record in enumerate(pool.map(_worker, tasks, chunksize=4)):
                records.append(record)
                if progress and (position + 1) % 50 == 0:
                    print(f"  ... reference {position + 1}/{len(tasks)}", file=sys.stderr)
    records.sort(key=lambda record: (record["estimator"], record["cell_id"], record["trial"]))

    summaries = []
    for estimator in ("front_end", "phase_difference"):
        for family in ("correct_constant_velocity", "acceleration_misspecification"):
            subset = [record for record in records if record["estimator"] == estimator and record["family"] == family]
            if not subset:
                continue
            summaries.append(
                {
                    "estimator": estimator,
                    "family": family,
                    "n": len(subset),
                    "adequacy_status_counts": _counts(record["adequacy_status"] for record in subset),
                    "false_rejections": sum(1 for record in subset if record["adequacy_status"] == "discrepancy" and family == "correct_constant_velocity"),
                    "correct_detections": sum(1 for record in subset if record["adequacy_status"] == "discrepancy" and family == "acceleration_misspecification"),
                    "adequate_rate": sum(1 for record in subset if record["adequacy_status"] == "adequate") / len(subset),
                    "insufficient_evidence_rate": sum(1 for record in subset if record["adequacy_status"] == "insufficient_evidence") / len(subset),
                    "median_sigma_f_hz": float(np.median([record["sigma_f_hz"] for record in subset])),
                    "median_ljung_box": float(
                        np.median([record["ljung_box"] for record in subset if record["ljung_box"] is not None])
                    ),
                    "median_error_rms_hz": float(np.median([record["error_rms_hz"] for record in subset])),
                }
            )
    by_key = {(summary["estimator"], summary["family"]): summary for summary in summaries}
    front_cv = by_key.get(("front_end", "correct_constant_velocity"))
    ref_cv = by_key.get(("phase_difference", "correct_constant_velocity"))
    front_accel = by_key.get(("front_end", "acceleration_misspecification"))
    ref_accel = by_key.get(("phase_difference", "acceleration_misspecification"))

    def rate(summary, field):
        return (summary[field] / summary["n"]) if summary and summary["n"] else None

    frr_delta = None
    detection_delta = None
    if rate(front_cv, "false_rejections") is not None and rate(ref_cv, "false_rejections") is not None:
        frr_delta = rate(ref_cv, "false_rejections") - rate(front_cv, "false_rejections")
    if rate(front_accel, "correct_detections") is not None and rate(ref_accel, "correct_detections") is not None:
        detection_delta = rate(ref_accel, "correct_detections") - rate(front_accel, "correct_detections")
    front_adequate = (front_cv or {}).get("adequate_rate")
    ref_adequate = (ref_cv or {}).get("adequate_rate")
    front_insufficient = (front_cv or {}).get("insufficient_evidence_rate")
    ref_insufficient = (ref_cv or {}).get("insufficient_evidence_rate")
    if (
        frr_delta is not None
        and detection_delta is not None
        and frr_delta < -0.05
        and detection_delta >= -0.05
        and front_adequate is not None
        and ref_adequate is not None
        and ref_adequate > front_adequate + 0.05
    ):
        verdict = "reference_improves_representation"
    elif (
        frr_delta is not None
        and frr_delta < -0.05
        and front_adequate is not None
        and ref_adequate is not None
        and ref_adequate <= front_adequate + 0.02
        and front_insufficient is not None
        and ref_insufficient is not None
        and ref_insufficient > front_insufficient + 0.05
    ):
        verdict = "reference_abstains_more_than_front_end"
    elif frr_delta is not None and abs(frr_delta) <= 0.05 and abs(detection_delta or 0.0) <= 0.05:
        verdict = "reference_comparable_to_front_end"
    else:
        verdict = "reference_does_not_improve"
    artifact = {
        "artifact": "c2m2-reference-estimator",
        "version": REFERENCE_VERSION,
        "estimator": {
            "id": REFERENCE_ID,
            "description": "phase-difference fractional-bin IF estimator on STFT frames (512 samples, Hann, hop 128)",
            "not_competing_with_B0_B3": True,
        },
        "config": {
            "seed_base": REFERENCE_SEED_BASE,
            "seed_formula": "REFERENCE_SEED_BASE + 1000*cell_index + trial",
            "n_trials_per_cell": REFERENCE_N_TRIALS,
            "correct_cv_geometries_m": list(CORRECT_CV_GEOMETRIES_M),
            "acceleration_levels_m_s2": list(ACCELERATION_LEVELS_M_S2),
            "acceleration_geometry_m": ACCELERATION_GEOMETRY_M,
            "snr_db": SNR_DB,
            "thresholds_changed": False,
            "sealed_c2c_grid_used": False,
        },
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
        },
        "records_sha256": hashlib.sha256(
            json.dumps(records, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        ).hexdigest(),
        "summary": summaries,
        "comparison": {
            "false_rejection_rate_front_end": rate(front_cv, "false_rejections"),
            "false_rejection_rate_reference": rate(ref_cv, "false_rejections"),
            "false_rejection_rate_delta_pp": None if frr_delta is None else 100.0 * frr_delta,
            "adequate_rate_front_end": front_adequate,
            "adequate_rate_reference": ref_adequate,
            "insufficient_evidence_rate_front_end": front_insufficient,
            "insufficient_evidence_rate_reference": ref_insufficient,
            "detection_rate_front_end": rate(front_accel, "correct_detections"),
            "detection_rate_reference": rate(ref_accel, "correct_detections"),
            "detection_rate_delta_pp": None if detection_delta is None else 100.0 * detection_delta,
            "verdict": verdict,
            "statement": {
                "reference_improves_representation": (
                    "The phase-difference estimator reduces correct-model false rejections without losing acceleration "
                    "detection in this synthetic set; replacing the frequency representation is a candidate direction."
                ),
                "reference_abstains_more_than_front_end": (
                    "The phase-difference estimator reduces the discrepancy count but mostly by returning "
                    "insufficient_evidence (residual-scale failure from occasional phase jumps); adequate retention "
                    "is lower. This is abstention, not a representation improvement."
                ),
                "reference_comparable_to_front_end": (
                    "The phase-difference estimator is comparable to the current front end in this set; the "
                    "representation is not clearly improved by this simple estimator."
                ),
                "reference_does_not_improve": (
                    "The phase-difference estimator does not improve correct-model false rejections without losing "
                    "detection; the representation limit is not removed by this reference estimator."
                ),
            }[verdict],
        },
        "records": records,
        "elapsed_s": float(time.time() - started),
        "limitations": [
            "Phase-difference estimation assumes a dominant single spectral peak and small per-hop frequency change; "
            "it is unambiguous only while the per-hop change is within +-N/(2*hop) bins.",
            "The evaluation set is synthetic and small (N=10 per cell); it is a representation test, not a field validation.",
            "The reference estimator uses a different hop (128 vs 256) and therefore a different frame grid; paired comparison is at scenario level.",
        ],
    }
    return artifact


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


def render_markdown(artifact: dict) -> str:
    lines = ["# C2-M2 reference estimator", ""]
    lines.append(
        f"**Artifact:** `{artifact['artifact']}` v{artifact['version']} · records `{artifact['records_sha256']}` · "
        f"estimator `{artifact['estimator']['id']}`"
    )
    lines.append("")
    lines.append("Non-competing reference path: phase-difference fractional-bin IF estimator. No adequacy threshold changed.")
    lines.append("")
    lines.append("| estimator | family | n | status counts | false rejections / detections | median σ_f (Hz) | median LB | median error RMS (Hz) |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for summary in artifact["summary"]:
        lines.append(
            f"| {summary['estimator']} | {summary['family']} | {summary['n']} | "
            f"{json.dumps(summary['adequacy_status_counts'])} | "
            f"{summary['false_rejections']}/{summary['correct_detections']} | "
            f"{summary['median_sigma_f_hz']:.4g} | {summary['median_ljung_box']:.4g} | {summary['median_error_rms_hz']:.4g} |"
        )
    comparison = artifact["comparison"]
    lines.append("")
    lines.append("## Comparison")
    lines.append("")
    lines.append(f"- Verdict: **{comparison['verdict']}**")
    lines.append(f"- {comparison['statement']}")
    lines.append(
        f"- Correct-model FRR: front end {comparison['false_rejection_rate_front_end']}, reference "
        f"{comparison['false_rejection_rate_reference']}, delta {comparison['false_rejection_rate_delta_pp']} pp"
    )
    lines.append(
        f"- Acceleration detection: front end {comparison['detection_rate_front_end']}, reference "
        f"{comparison['detection_rate_reference']}, delta {comparison['detection_rate_delta_pp']} pp"
    )
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    for limitation in artifact["limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Reference phase-difference IF estimator evaluation (non-competing).")
    parser.add_argument("--out", required=True)
    parser.add_argument("--markdown", default=None)
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    artifact = evaluate_reference(jobs=args.jobs, progress=not args.quiet)
    artifact_sha, markdown_sha = write_artifact(artifact, args.out, args.markdown)
    comparison = artifact["comparison"]
    print(f"reference: {comparison['verdict']}")
    print(
        f"  FRR front/reference: {comparison['false_rejection_rate_front_end']} -> "
        f"{comparison['false_rejection_rate_reference']} ({comparison['false_rejection_rate_delta_pp']} pp)"
    )
    print(
        f"  detection front/reference: {comparison['detection_rate_front_end']} -> "
        f"{comparison['detection_rate_reference']} ({comparison['detection_rate_delta_pp']} pp)"
    )
    print(f"  records: {artifact['records_sha256']}")
    print(f"  json: {args.out}  sha256: {artifact_sha}")
    if args.markdown:
        print(f"  markdown: {args.markdown}  sha256: {markdown_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
