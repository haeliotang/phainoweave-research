"""Tuning and Locked Validation layers for the Model Adequacy & Discrepancy layer.

Two artifacts are emitted, each with its own layer label:

* ``--layer tuning`` -- the nine pre-registered tuning conditions, E0 seeds
  (``20261104 + 1000*E0_condition_index + trial``).  Thresholds were calibrated
  on this layer only; the artifact carries the calibration evidence.
* ``--layer locked`` -- **new seeds and unseen perturbation levels**, generated
  by the same generator (never a resample of E0 trials).  The frozen protocol
  digest is recorded; no threshold changes after this layer is opened.

Per-mechanism stratification (ADR 0015 section 6):
``acceleration, clock_rate, clock_offset, window, geometry, noise, null,
within_tolerance``.

The adequacy decision never uses the synthetic truth.  Truth is written only
under ``evaluation_only`` (the scenario and the truth-tolerance diagnostics) so
the independent evaluator can score it; ``phaino_acoustics.adequacy`` receives
only the IF track, the fitted parameters, the declared noise scale and the
hardened optimizer status.

Usage::

    python -m phaino_acoustics.experiment_adequacy --layer tuning \
        --output /tmp/adeq/tuning.json --jobs 8
    python -m phaino_acoustics.experiment_adequacy --layer locked \
        --output /tmp/adeq/locked.json --jobs 8
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
from dataclasses import asdict, dataclass, field, replace
from typing import Optional

import numpy as np

from .adequacy import evaluate_adequacy
from .adequacy_protocol import (
    CALIBRATION_MARGIN,
    CALIBRATION_POPULATION,
    PROTOCOL,
    PROTOCOL_DIGEST,
    PARAM_ORDER,
)
from .experiment import (
    B_REL_TOL,
    BASE,
    F0_REL_TOL,
    F_MAX,
    F_MIN,
    FRAME_LEN,
    HOP,
    SEED_BASE,
    T0_ABS_TOL,
    V_REL_TOL,
    build_conditions,
)
from .features import estimate_if_track
from .fit_hardened import fit_hardened
from .synthetic import Scenario, generate

EXPERIMENT_NAME = "e0-adequacy"
TUNING_SEED_BASE = SEED_BASE            # E0 pre-registered seed formula
LOCKED_SEED_BASE = 20_300_000          # disjoint from E0 seeds (<= 20_285_103)
TUNING_TRIALS_PER_CONDITION = 100

# The nine tuning conditions fixed by PR-4d / ADR 0015 section 6, in order.
TUNING_CONDITIONS = (
    "accel_0.1",
    "clock_1000ppm",
    "offset_0.3s",
    "snr_+5dB",
    "window_20s",
    "geom_v100_b300",
    "amp_geometric",
    "amp_mod30pct",
    "null_noise_only",
)

E0_GRID = build_conditions()
E0_INDEX = {condition.name: index for index, condition in enumerate(E0_GRID)}

MECHANISMS = (
    "acceleration",
    "clock_rate",
    "clock_offset",
    "window",
    "geometry",
    "noise",
    "null",
    "within_tolerance",
)


@dataclass(frozen=True)
class AdequacyCondition:
    name: str
    mechanism: str
    level: str
    note: str
    scenario: Scenario
    n_trials: int


@dataclass(frozen=True)
class AdequacyLayerConfig:
    layer: str
    seed_base: int
    seed_formula: str
    conditions: tuple[AdequacyCondition, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Condition grids
# ---------------------------------------------------------------------------

def tuning_conditions(n_trials: int = TUNING_TRIALS_PER_CONDITION) -> list[AdequacyCondition]:
    """The E0 tuning conditions (same scenarios, same seeds as the E0 artifact)."""
    result = []
    for name in TUNING_CONDITIONS:
        source = E0_GRID[E0_INDEX[name]]
        result.append(
            AdequacyCondition(
                name=name,
                mechanism=_tuning_mechanism(name),
                level=name,
                note=f"E0 tuning condition {name}",
                scenario=source.scenario,
                n_trials=int(n_trials),
            )
        )
    return result


def _tuning_mechanism(name: str) -> str:
    if name.startswith("accel"):
        return "acceleration"
    if name.startswith("clock"):
        return "clock_rate"
    if name.startswith("offset"):
        return "clock_offset"
    if name.startswith("null"):
        return "null"
    if name.startswith("window"):
        return "window"
    if name.startswith("geom"):
        return "geometry"
    return "within_tolerance"


def locked_conditions() -> list[AdequacyCondition]:
    """The locked grid: new seeds, unseen perturbation levels (PR-4d plan).

    Composition (documented, so the evaluator can map the Lead's expected
    "400 misspecification / 200 equivalence" strata):

    * misspecification group = acceleration (3 x 80) + clock rate (2 x 80) = 400
    * equivalence group   = clock offset (80 + 60 + 60) = 200
    * window (2 x 50), geometry (3 b x 3 v x 30 = 270), noise (4 x 50),
      null (2 x 50), within_tolerance (100 + 50) = 820
    """
    result: list[AdequacyCondition] = []
    base = BASE

    def add(name: str, mechanism: str, level: str, note: str, n_trials: int, **overrides) -> None:
        result.append(
            AdequacyCondition(
                name=name,
                mechanism=mechanism,
                level=level,
                note=note,
                scenario=replace(base, **overrides),
                n_trials=int(n_trials),
            )
        )

    # Model misspecification -- acceleration (unseen levels).
    for value in (0.175, 0.35, 0.75):
        add(
            f"locked_accel_{value:g}",
            "acceleration",
            f"accel={value:g} m/s^2",
            "constant along-track acceleration, zero-acceleration model, 20 dB",
            80,
            accel=float(value),
            snr_db=20.0,
        )

    # Model/form mismatch candidate -- clock rate (unseen levels).
    for ppm in (5000.0, 35000.0):
        add(
            f"locked_clock_{int(ppm)}ppm",
            "clock_rate",
            f"clock_rate={int(ppm)} ppm",
            "recorder clock rate error, nominal-clock model, 20 dB",
            80,
            clock_scale_ppm=float(ppm),
            snr_db=20.0,
        )

    # Observational equivalence -- constant clock offset (unseen levels).
    for offset, n_trials in ((0.15, 80), (1.0, 60), (5.0, 60)):
        add(
            f"locked_offset_{offset:g}s",
            "clock_offset",
            f"offset={offset:g} s",
            "constant clock offset; exactly degenerate with t0, 20 dB",
            n_trials,
            clock_offset_s=float(offset),
            snr_db=20.0,
        )

    # Window length (unseen values) at an unseen noise level.
    for duration in (12.0, 30.0):
        add(
            f"locked_window_{duration:g}s",
            "window",
            f"duration={duration:g} s",
            "short/long observation window, 10 dB",
            50,
            duration=float(duration),
            snr_db=10.0,
        )

    # Geometry: all b x v combinations, unseen values, 10 dB.
    for b in (200.0, 800.0, 10000.0):
        for v in (60.0, 150.0, 250.0):
            add(
                f"locked_geom_b{b:g}_v{v:g}",
                "geometry",
                f"b={b:g} m, v={v:g} m/s",
                "unseen closest-approach distance x speed, 10 dB",
                30,
                b=float(b),
                v=float(v),
                snr_db=10.0,
            )

    # Noise levels not used in tuning (tuning uses 5 and 20 dB).
    for snr in (10.0, 0.0, -5.0, -12.0):
        add(
            f"locked_noise_{snr:+.0f}dB",
            "noise",
            f"snr={snr:+.0f} dB",
            "unseen per-sample SNR, base geometry",
            50,
            snr_db=float(snr),
        )

    # Null (noise-only) observations at unseen noise levels.
    for snr in (0.0, -5.0):
        add(
            f"locked_null_{snr:+.0f}dB",
            "null",
            f"null snr={snr:+.0f} dB",
            "no signal; noise-equivalent level unbeknownst to the method",
            50,
            emit_signal=False,
            snr_db=float(snr),
        )

    # Positive control: no perturbation, unseen seeds.
    add(
        "locked_within_tolerance_20dB",
        "within_tolerance",
        "snr=+20 dB",
        "base geometry, no perturbation, 20 dB, new seeds",
        100,
        snr_db=20.0,
    )
    add(
        "locked_within_tolerance_10dB",
        "within_tolerance",
        "snr=+10 dB",
        "base geometry, no perturbation, 10 dB, new seeds",
        50,
        snr_db=10.0,
    )
    return result


# ---------------------------------------------------------------------------
# Seeds
# ---------------------------------------------------------------------------

def tuning_seed(condition_name: str, trial: int) -> int:
    """The E0 pre-registered seed of the tuning condition."""
    if condition_name not in E0_INDEX:
        raise ValueError(f"unknown tuning condition {condition_name!r}")
    return TUNING_SEED_BASE + 1000 * E0_INDEX[condition_name] + int(trial)


def locked_seed(condition_index: int, trial: int) -> int:
    """Locked seeds are new and disjoint from every E0/tuning seed."""
    return LOCKED_SEED_BASE + 1000 * int(condition_index) + int(trial)


# ---------------------------------------------------------------------------
# One trial
# ---------------------------------------------------------------------------

def _parameter_rel_errors(params: dict[str, float], scenario: Scenario) -> dict[str, float]:
    """Truth-relative errors.  EVALUATION ONLY -- never used by adequacy decisions."""
    return {
        "f0": (params["f0"] - scenario.f0) / scenario.f0,
        "v": (params["v"] - scenario.v) / scenario.v,
        "t0": (params["t0"] - scenario.t0) / scenario.t0,
        "b": (params["b"] - scenario.b) / scenario.b,
        "t0_abs": params["t0"] - scenario.t0,
    }


def run_trial(condition: AdequacyCondition, trial: int, seed: int, layer: str) -> dict:
    """Generate the observation, fit, run the adequacy layer, and record."""
    scenario = replace(condition.scenario, seed=int(seed))
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
    # Observation-quality descriptor (evaluation-only: it needs the true apparent track).
    true_apparent = np.interp(track.t, observation.t, observation.f_apparent)
    if_rms = float(np.sqrt(np.mean((track.f - true_apparent) ** 2)))

    hardened = fit_hardened(track.t, track.f, c=scenario.c)
    params = np.array([hardened.f0, hardened.v, hardened.t0, hardened.b], dtype=np.float64)
    adequacy = evaluate_adequacy(
        track.t,
        track.f,
        params,
        hardened.sigma_f_hz,
        hardened.optimization_status,
        c=scenario.c,
    )

    # EVALUATION-ONLY truth diagnostics (never passed to evaluate_adequacy).
    rel = _parameter_rel_errors(hardened.params, scenario)
    within_tolerance = bool(
        abs(rel["f0"]) <= F0_REL_TOL
        and abs(rel["v"]) <= V_REL_TOL
        and abs(rel["t0_abs"]) <= T0_ABS_TOL
        and abs(rel["b"]) <= B_REL_TOL
    )

    if hardened.optimization_status == "converged":
        identifiability_old = (
            "identifiable" if hardened.parameter_identifiable else "not_identifiable"
        )
    else:
        identifiability_old = "indeterminate"

    return {
        "condition": condition.name,
        "trial": int(trial),
        "seed": int(seed),
        "layer": layer,
        "mechanism": condition.mechanism,
        "evaluation_only": {
            "scenario": {
                key: (float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else value)
                for key, value in asdict(scenario).items()
            },
            "parameter_rel_errors": {name: float(value) for name, value in rel.items()},
            "within_e0_tolerance": within_tolerance,
        },
        "observation": {
            "if_rms_hz": if_rms,
            "sigma_f_hz": float(hardened.sigma_f_hz),
            "n_samples": int(track.t.size),
            "duration_s": float(scenario.duration),
        },
        "hardened": {
            "params": {name: float(value) for name, value in hardened.params.items()},
            "optimization_status": hardened.optimization_status,
            "identifiability_status_old": identifiability_old,
            "decision_status_old": hardened.decision_status,
        },
        "adequacy": adequacy,
    }


def _worker(task: tuple[AdequacyCondition, int, int, str]) -> dict:
    condition, trial, seed, layer = task
    return _jsonable(run_trial(condition, trial, seed, layer))


# ---------------------------------------------------------------------------
# JSON hygiene and digests
# ---------------------------------------------------------------------------

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
        json.dumps(_jsonable(document), sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
            "utf-8"
        )
    ).hexdigest()


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _counts(values) -> dict:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))


def _summary_block(records: list[dict], key: str) -> dict:
    return {
        key: _counts(record[key] for record in records),
        "model_adequacy_status": _counts(
            record["adequacy"]["model_adequacy_status"] for record in records
        ),
        "identifiability_status": _counts(
            record["adequacy"]["identifiability_status"] for record in records
        ),
        "epistemic_decision": _counts(
            record["adequacy"]["epistemic_decision"] for record in records
        ),
        "reason_codes": _counts(
            code for record in records for code in record["adequacy"]["reason_codes"]
        ),
        "n": len(records),
        "evaluation_only": {
            "within_e0_tolerance": _counts(
                record["evaluation_only"]["within_e0_tolerance"] for record in records
            ),
        },
    }


def _condition_summaries(records: list[dict]) -> list[dict]:
    summaries = []
    for condition in sorted({record["condition"] for record in records}):
        subset = [record for record in records if record["condition"] == condition]
        block = _summary_block(subset, "condition")
        block["condition"] = condition
        block["mechanism"] = subset[0]["mechanism"]
        summaries.append(block)
    return summaries


def _mechanism_summaries(records: list[dict]) -> list[dict]:
    summaries = []
    for mechanism in MECHANISMS:
        subset = [record for record in records if record["mechanism"] == mechanism]
        if not subset:
            continue
        block = _summary_block(subset, "mechanism")
        block["mechanism"] = mechanism
        summaries.append(block)
    return summaries


def calibration_evidence(records: list[dict]) -> dict:
    """Recompute the calibration maxima from the tuning records (transparency)."""
    population = [record for record in records if record["condition"] in CALIBRATION_POPULATION]
    per_condition: dict[str, int] = {}
    for record in population:
        per_condition[record["condition"]] = per_condition.get(record["condition"], 0) + 1
    required = int(PROTOCOL["calibration"]["trials_per_condition"])
    calibration_complete = all(
        per_condition.get(name, 0) >= required for name in CALIBRATION_POPULATION
    )
    excluded = [record for record in records if record["condition"] not in CALIBRATION_POPULATION]
    thresholds = PROTOCOL["tests"]

    def collect(records_subset, path):
        values = []
        for record in records_subset:
            node = record
            for key in path:
                node = node.get(key, {}) if isinstance(node, dict) else {}
            if node is not None and isinstance(node, (int, float)) and not isinstance(node, bool):
                values.append(float(node))
        return np.array(values, dtype=np.float64) if values else np.array([], dtype=np.float64)

    def maximum(path, absolute=False):
        values = collect(population, path)
        if values.size == 0:
            return None
        return float(np.max(np.abs(values))) if absolute else float(np.max(values))

    evidence = {
        "population": list(CALIBRATION_POPULATION),
        "n_population_trials": len(population),
        "trials_per_condition": required,
        "calibration_complete": bool(calibration_complete),
        "excluded_conditions": sorted({record["condition"] for record in excluded}),
        "calibration_margin": CALIBRATION_MARGIN,
        "statistics": {
            "max_abs_z": {
                "calibration_max": maximum(("adequacy", "tests", "standardized_residuals", "metrics", "max_abs_z")),
                "threshold": thresholds["standardized_residuals"]["max_abs_z_max"],
            },
            "tail_fraction": {
                "calibration_max": maximum(("adequacy", "tests", "standardized_residuals", "metrics", "tail_fraction_abs_z_gt_3")),
                "threshold": thresholds["standardized_residuals"]["tail_fraction_abs_z_gt_3_max"],
            },
            "excess_kurtosis": {
                "calibration_max": maximum(("adequacy", "tests", "standardized_residuals", "metrics", "excess_kurtosis")),
                "threshold": thresholds["standardized_residuals"]["abs_excess_kurtosis_max"],
            },
            "ljung_box": {
                "calibration_max": maximum(("adequacy", "tests", "autocorrelation", "metrics", "ljung_box_statistic")),
                "threshold": thresholds["autocorrelation"]["ljung_box_statistic_max"],
            },
            "corr_time": {
                "calibration_max": maximum(("adequacy", "tests", "time_structure", "metrics", "corr_time"), absolute=True),
                "threshold": thresholds["time_structure"]["abs_corr_time_max"],
            },
            "quadratic_coefficient": {
                "calibration_max": maximum(("adequacy", "tests", "time_structure", "metrics", "quadratic_coefficient_over_sigma_f"), absolute=True),
                "threshold": thresholds["time_structure"]["abs_quadratic_coefficient_max"],
            },
            "phase_correlation": {
                "calibration_max": maximum(("adequacy", "tests", "time_structure", "metrics", "max_abs_phase_correlation"), absolute=True),
                "threshold": thresholds["time_structure"]["abs_phase_correlation_max"],
            },
            "median_block_rmse": {
                "calibration_max": maximum(("adequacy", "tests", "block_prediction", "metrics", "median_normalized_rmse")),
                "threshold": thresholds["block_prediction"]["heldout_normalized_rmse_max"],
            },
            "median_block_explained_fraction": {
                "calibration_min": (
                    float(np.min(collect(population, ("adequacy", "tests", "block_prediction", "metrics", "median_block_explained_fraction"))))
                    if collect(population, ("adequacy", "tests", "block_prediction", "metrics", "median_block_explained_fraction")).size
                    else None
                ),
                "threshold": thresholds["block_prediction"]["heldout_explained_fraction_min"],
            },
        },
        "note": (
            "thresholds were derived as calibration_max * margin for upper bounds; the "
            "explained-fraction floor is the declared separator between the tuning null "
            "and the nominal-null population"
        ),
    }
    # Check the frozen thresholds actually match max*margin (within a small relative tolerance).
    matches = True
    for name in (
        "max_abs_z",
        "tail_fraction",
        "excess_kurtosis",
        "ljung_box",
        "corr_time",
        "quadratic_coefficient",
        "phase_correlation",
        "median_block_rmse",
    ):
        entry = evidence["statistics"][name]
        if entry["calibration_max"] is not None:
            expected = entry["calibration_max"] * CALIBRATION_MARGIN
            matches &= abs(entry["threshold"] - expected) <= 1e-12 * max(1.0, abs(expected))
    evidence["thresholds_match_calibration"] = bool(matches) if calibration_complete else None
    return evidence


# ---------------------------------------------------------------------------
# Layer runner
# ---------------------------------------------------------------------------

def build_layer(layer: str, trials_override: Optional[int] = None, name_filter: Optional[str] = None):
    if layer == "tuning":
        conditions = tuning_conditions()
        seed_base = TUNING_SEED_BASE
        seed_formula = "E0 pre-registered: 20261104 + 1000*E0_condition_index + trial"
        seed_for = lambda index, condition_name, trial: tuning_seed(condition_name, trial)  # noqa: E731
    elif layer == "locked":
        conditions = locked_conditions()
        seed_base = LOCKED_SEED_BASE
        seed_formula = "locked: 20300000 + 1000*locked_condition_index + trial (new seeds)"
        seed_for = lambda index, condition_name, trial: locked_seed(index, trial)  # noqa: E731
    else:
        raise ValueError(f"unknown layer {layer!r} (expected 'tuning' or 'locked')")

    if name_filter:
        conditions = [
            condition
            for condition in conditions
            if name_filter in condition.name or name_filter == condition.mechanism
        ]
        if not conditions:
            raise ValueError(f"no condition matches filter {name_filter!r}")
    if trials_override is not None:
        if int(trials_override) < 1:
            raise ValueError("--trials must be >= 1")
        conditions = [replace(condition, n_trials=int(trials_override)) for condition in conditions]
    return conditions, seed_base, seed_formula, seed_for


def run_layer(
    layer: str,
    jobs: int = 1,
    trials_override: Optional[int] = None,
    name_filter: Optional[str] = None,
    progress: bool = True,
) -> dict:
    conditions, seed_base, seed_formula, seed_for = build_layer(
        layer, trials_override=trials_override, name_filter=name_filter
    )
    tasks: list[tuple[AdequacyCondition, int, int, str]] = []
    for index, condition in enumerate(conditions):
        for trial in range(condition.n_trials):
            tasks.append((condition, trial, seed_for(index, condition.name, trial), layer))

    started = time.time()
    records: list[dict] = []
    if jobs <= 1:
        for position, task in enumerate(tasks):
            records.append(_worker(task))
            if progress and (position + 1) % 250 == 0:
                print(f"  ... {position + 1}/{len(tasks)} trials", file=sys.stderr)
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            for position, record in enumerate(pool.map(_worker, tasks, chunksize=8)):
                records.append(record)
                if progress and (position + 1) % 250 == 0:
                    print(f"  ... {position + 1}/{len(tasks)} trials", file=sys.stderr)
    elapsed = time.time() - started
    records.sort(key=lambda record: (record["condition"], record["trial"]))

    result = {
        "experiment": EXPERIMENT_NAME,
        "layer": layer,
        "protocol_digest": PROTOCOL_DIGEST,
        "frozen_protocol": True,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "config": {
            "seed_base": int(seed_base),
            "seed_formula": seed_formula,
            "tuning_seed_base": TUNING_SEED_BASE,
            "locked_seed_base": LOCKED_SEED_BASE,
            "conditions": [
                {
                    "name": condition.name,
                    "mechanism": condition.mechanism,
                    "level": condition.level,
                    "note": condition.note,
                    "n_trials": int(condition.n_trials),
                    "scenario": {
                        key: value for key, value in asdict(condition.scenario).items()
                    },
                }
                for condition in conditions
            ],
            "layers": {
                "original_e0": "historical/diagnostic only (never validation)",
                "tuning": "calibration of diagnostics and thresholds",
                "locked": "new seeds + unseen perturbation levels; thresholds frozen",
            },
            "seed_disjointness": {
                "e0_max_seed": SEED_BASE + 1000 * (len(E0_GRID) - 1) + 999,
                "locked_min_seed": LOCKED_SEED_BASE,
                "disjoint": LOCKED_SEED_BASE > SEED_BASE + 1000 * (len(E0_GRID) - 1) + 999,
            },
            "protocol": PROTOCOL,
            "protocol_digest": PROTOCOL_DIGEST,
            "mechanisms": list(MECHANISMS),
            "front_end": {
                "method": "Hann STFT peak + log-magnitude parabolic interpolation",
                "frame_len": FRAME_LEN,
                "hop": HOP,
                "f_min_hz": F_MIN,
                "f_max_hz": F_MAX,
                "sample_rate_hz": BASE.fs,
            },
            "noise_model": "additive white Gaussian, per-sample SNR (E0 definition)",
            "parameters": {"estimator": "fit_hardened v1.0.0", "parameter_order": list(PARAM_ORDER)},
            "schema_notes": {
                "truth_separation": (
                    "truth is written only under evaluation_only; "
                    "phaino_acoustics.adequacy receives only the IF track, fitted "
                    "parameters, sigma_f and the hardened optimizer status"
                ),
                "observation.if_rms_hz": (
                    "front-end tracking error against the true apparent track; it is "
                    "an observation-quality descriptor for the evaluator and is never "
                    "read by any adequacy decision"
                ),
                "null_values": "undefined/non-finite aggregates are written as null",
            },
        },
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
        },
        "elapsed_s": float(elapsed),
        "records_sha256": _digest(records),
        "condition_summaries": _condition_summaries(records),
        "mechanism_summaries": _mechanism_summaries(records),
        "calibration": calibration_evidence(records) if layer == "tuning" else None,
        "trials": records,
    }
    return _jsonable(result)


def write_artifact(result: dict, output: str) -> str:
    directory = os.path.dirname(os.path.abspath(output))
    os.makedirs(directory, exist_ok=True)
    payload = (json.dumps(_jsonable(result), indent=1, sort_keys=True, allow_nan=False) + "\n").encode(
        "utf-8"
    )
    with open(output, "wb") as handle:
        handle.write(payload)
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Model Adequacy layer artifacts: tuning and locked layers."
    )
    parser.add_argument("--layer", required=True, choices=("tuning", "locked"))
    parser.add_argument("--output", required=True, help="artifact JSON path (written exactly here)")
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--trials", type=int, default=None, help="override trials per condition")
    parser.add_argument("--filter", default=None, help="condition-name substring or mechanism")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = run_layer(
            args.layer,
            jobs=args.jobs,
            trials_override=args.trials,
            name_filter=args.filter,
            progress=not args.quiet,
        )
    except ValueError as exc:
        print(f"experiment_adequacy: {exc}", file=sys.stderr)
        return 2
    sha = write_artifact(result, args.output)

    print(
        f"layer: {result['layer']}  trials: {len(result['trials'])}  "
        f"conditions: {len(result['condition_summaries'])}  jobs: {args.jobs}  "
        f"elapsed: {result['elapsed_s']:.1f} s"
    )
    print(f"protocol_digest: {result['protocol_digest']}")
    print(f"records_sha256: {result['records_sha256']}")
    print(f"json: {args.output}  sha256: {sha}")
    if not args.quiet:
        print()
        print("mechanism | n | adequacy | identifiability | epistemic")
        for summary in result["mechanism_summaries"]:
            print(
                f"{summary['mechanism']:16s} | {summary['n']:4d} | "
                f"{json.dumps(summary['model_adequacy_status'])} | "
                f"{json.dumps(summary['identifiability_status'])} | "
                f"{json.dumps(summary['epistemic_decision'])}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
