"""C2-C — frozen validation grid definition (no repair runs).

Defines the new, independent validation set used later to compare the four
candidates B0 (original), B1 (de-chirping), B2 (pre-whitening) and B3
(geometry-conditioned calibration) on the **same observations**.

Design rules (ADR 0020 D):

* new seed base, not used by E0 / PR-4c / PR-4d / C1 / C2 diagnosis;
* geometry continuum (log-spaced), not the 150/600/5000 m endpoints alone;
* unseen chirp-rate/geometry combinations, SNR levels and acceleration levels
  (0.15/0.30/0.50 m/s^2 were not used in the C2 diagnosis);
* the 1840 C2-diagnosis trials are not reused;
* paired design: one trial is processed by B0-B3 on the same (condition, trial,
  seed); candidates are independent artifacts, never combined before the
  independent results are known;
* B3 may condition only on runtime-observable quantities.  True geometry,
  true acceleration and scenario/mechanism labels are forbidden as selection
  inputs.

The grid digest covers the **grid definition only** (no results, no
environment, no timestamps).  No candidate is run by this module.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from typing import Optional

GRID_ID = "pr4e-c2c-v1"
GRID_VERSION = "1.0.0"
SEED_BASE = 60_000_000  # new base: E0 ~20.26M, PR-4d ~20.3M, C1 40/41M, C2-A/B 50M/70M
SEED_FORMULA = "SEED_BASE + 1000*condition_index + trial"

# Log-spaced geometry continuum (declared values, 120-8000 m).
GEOMETRY_M = (120.0, 180.0, 270.0, 400.0, 600.0, 900.0, 1400.0, 2100.0, 3200.0, 4800.0, 7000.0)
SPEEDS_M_S = (60.0, 150.0, 250.0)
SNR_LEVELS_DB = (5.0, 10.0, 20.0)
ACCELERATION_LEVELS_M_S2 = (0.15, 0.30, 0.50)  # new levels, not used by C2 diagnosis (0.2/0.4)
CANDIDATES = ("B0", "B1", "B2", "B3")
CANDIDATE_DESCRIPTIONS = {
    "B0": "original front end + adequacy (paired baseline)",
    "B1": "de-chirping candidate (NOT implemented in this round)",
    "B2": "residual pre-whitening candidate (NOT implemented in this round)",
    "B3": "geometry-conditioned calibration candidate (NOT implemented in this round)",
}

RUNTIME_OBSERVABLE_SELECTION_INPUTS = (
    "estimated_chirp_rate",
    "signal_quality",
    "fit_uncertainty",
    "estimated_snr",
)
FORBIDDEN_SELECTION_INPUTS = (
    "true_closest_approach_b",
    "true_speed",
    "true_acceleration",
    "scenario_label",
    "mechanism_label",
    "within_e0_tolerance",
)
SELECTION_INPUTS_RUNTIME_ONLY = True

STRATA = (
    "correct_cv_continuum",
    "correct_cv_low_snr",
    "acceleration_misspecification",
    "noise_only_null",
)

# Family sizes (declared)
N_TRIALS = {
    "cv_continuum": 10,
    "cv_continuum_low_snr": 8,
    "acceleration_continuum": 10,
    "null": 10,
}
LOW_SNR_GEOMETRY_M = (150.0, 600.0, 3200.0)
LOW_SNR_SPEEDS_M_S = (150.0, 250.0)
LOW_SNR_LEVELS_DB = (5.0, 10.0)
ACCEL_GEOMETRY_M = (600.0, 3000.0)
ACCEL_SPEEDS_M_S = (150.0, 250.0)
NULL_SNR_DB = (20.0, 0.0)


# ---------------------------------------------------------------------------
# Grid construction
# ---------------------------------------------------------------------------

def _scenario(**overrides) -> dict:
    from .experiment import BASE

    values = {
        "f0": BASE.f0,
        "v": BASE.v,
        "b": BASE.b,
        "t0": BASE.t0,
        "duration": BASE.duration,
        "fs": BASE.fs,
        "c": BASE.c,
        "accel": 0.0,
        "snr_db": 20.0,
        "emit_signal": True,
    }
    values.update(overrides)
    return values


def build_conditions() -> list[dict]:
    conditions: list[dict] = []
    index = 0

    def add(name, family, stratum, n_trials, label, **scenario_overrides):
        nonlocal index
        conditions.append(
            {
                "condition_index": index,
                "name": name,
                "family": family,
                "stratum": stratum,
                "label": label,
                "n_trials": int(n_trials),
                "seed_base": SEED_BASE + 1000 * index,
                "scenario": _scenario(**scenario_overrides),
            }
        )
        index += 1

    # correct-CV geometry continuum at nominal SNR (33 conditions)
    for geometry in GEOMETRY_M:
        for speed in SPEEDS_M_S:
            add(
                f"cv_b{geometry:g}_v{speed:g}_snr20",
                "cv_continuum",
                "correct_cv_continuum",
                N_TRIALS["cv_continuum"],
                "correct constant-velocity model, geometry continuum, 20 dB",
                b=geometry,
                v=speed,
                snr_db=20.0,
            )
    # correct-CV low-SNR subset over unseen chirp combinations (12 conditions)
    for geometry in LOW_SNR_GEOMETRY_M:
        for speed in LOW_SNR_SPEEDS_M_S:
            for snr in LOW_SNR_LEVELS_DB:
                add(
                    f"cv_lowsnr_b{geometry:g}_v{speed:g}_snr{snr:g}",
                    "cv_continuum_low_snr",
                    "correct_cv_low_snr",
                    N_TRIALS["cv_continuum_low_snr"],
                    "correct constant-velocity model, low-SNR unseen levels",
                    b=geometry,
                    v=speed,
                    snr_db=snr,
                )
    # independent acceleration samples with new levels (12 conditions)
    for geometry in ACCEL_GEOMETRY_M:
        for speed in ACCEL_SPEEDS_M_S:
            for accel in ACCELERATION_LEVELS_M_S2:
                add(
                    f"accel_b{geometry:g}_v{speed:g}_a{accel:g}",
                    "acceleration_continuum",
                    "acceleration_misspecification",
                    N_TRIALS["acceleration_continuum"],
                    "unmodelled constant acceleration, level not used in the C2 diagnosis",
                    b=geometry,
                    v=speed,
                    accel=accel,
                    snr_db=20.0,
                )
    # noise-only nulls
    for snr in NULL_SNR_DB:
        add(
            f"null_snr{snr:g}",
            "null",
            "noise_only_null",
            N_TRIALS["null"],
            "noise-only observation, no constant-velocity source",
            snr_db=snr,
            emit_signal=False,
        )
    return conditions


def build_grid() -> dict:
    conditions = build_conditions()
    trials_per_condition = sum(condition["n_trials"] for condition in conditions)
    strata_counts: dict[str, int] = {}
    family_counts: dict[str, int] = {}
    family_trials: dict[str, int] = {}
    for condition in conditions:
        strata_counts[condition["stratum"]] = strata_counts.get(condition["stratum"], 0) + condition["n_trials"]
        family_counts[condition["family"]] = family_counts.get(condition["family"], 0) + 1
        family_trials[condition["family"]] = family_trials.get(condition["family"], 0) + condition["n_trials"]
    definition = {
        "grid_id": GRID_ID,
        "grid_version": GRID_VERSION,
        "seed_base": SEED_BASE,
        "seed_formula": SEED_FORMULA,
        "geometry_m": list(GEOMETRY_M),
        "speeds_m_s": list(SPEEDS_M_S),
        "snr_levels_db": list(SNR_LEVELS_DB),
        "acceleration_levels_m_s2": list(ACCELERATION_LEVELS_M_S2),
        "conditions": conditions,
        "condition_count": len(conditions),
        "trial_count": trials_per_condition,
        "strata": list(STRATA),
        "strata_counts": {stratum: strata_counts.get(stratum, 0) for stratum in STRATA},
        "family_counts": family_counts,
        "family_trials": family_trials,
        "paired_design": True,
        "candidates": list(CANDIDATES),
        "candidate_descriptions": dict(CANDIDATE_DESCRIPTIONS),
        "candidate_combination_before_independent_results": False,
        "runtime_observable_selection_inputs": list(RUNTIME_OBSERVABLE_SELECTION_INPUTS),
        "forbidden_selection_inputs": list(FORBIDDEN_SELECTION_INPUTS),
        "selection_inputs_runtime_only": SELECTION_INPUTS_RUNTIME_ONLY,
        "c2_diagnosis_trials_reused": False,
        "truth_fields_forbidden_as_selection": True,
    }
    grid = dict(definition)
    grid["grid_digest"] = grid_digest(grid)
    return grid


def grid_definition(grid: dict) -> dict:
    """The digested grid definition only (no digest, results, environment, time)."""
    return {key: value for key, value in grid.items() if key not in ("grid_digest",)}


def grid_digest(grid: dict) -> str:
    definition = grid_definition(grid)
    canonical = json.dumps(definition, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def verify_grid_digest(grid: dict) -> bool:
    return grid.get("grid_digest") == grid_digest(grid)


# ---------------------------------------------------------------------------
# Trials and validation
# ---------------------------------------------------------------------------

def condition_seed(condition: dict, trial: int) -> int:
    return int(condition["seed_base"]) + int(trial)


def iter_trials(grid: dict):
    """Yield the frozen trial plan: one entry per (condition, trial, seed)."""
    for condition in grid["conditions"]:
        for trial in range(int(condition["n_trials"])):
            yield {
                "condition": condition["name"],
                "family": condition["family"],
                "stratum": condition["stratum"],
                "condition_index": int(condition["condition_index"]),
                "trial": int(trial),
                "seed": condition_seed(condition, trial),
            }


def trial_count(grid: dict) -> int:
    return sum(int(condition["n_trials"]) for condition in grid["conditions"])


def assert_selection_inputs_runtime_only() -> dict:
    """Assert that B3's declared selection inputs contain no truth/label inputs."""
    allowed = set(RUNTIME_OBSERVABLE_SELECTION_INPUTS)
    forbidden = set(FORBIDDEN_SELECTION_INPUTS)
    overlap = allowed & forbidden
    if overlap:
        raise AssertionError(f"truth/label inputs appear in runtime-observable selection inputs: {sorted(overlap)}")
    if not SELECTION_INPUTS_RUNTIME_ONLY:
        raise AssertionError("selection_inputs_runtime_only must be declared True")
    return {
        "allowed": sorted(allowed),
        "forbidden": sorted(forbidden),
        "overlap": sorted(overlap),
        "runtime_observable_only": True,
    }


# ---------------------------------------------------------------------------
# Freeze artifact I/O
# ---------------------------------------------------------------------------

def write_grid(grid: dict, path: str) -> str:
    payload = (json.dumps(grid, indent=1, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(payload)
    return hashlib.sha256(payload).hexdigest()


def load_grid(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        grid = json.load(handle)
    if not verify_grid_digest(grid):
        raise ValueError(f"C2-C grid digest mismatch in {path}")
    return grid


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Emit the frozen C2-C grid definition (no repair runs).")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    grid = build_grid()
    grid["selection_inputs_assertion"] = assert_selection_inputs_runtime_only()
    # Recompute the digest AFTER adding the assertion: the frozen file must
    # self-verify under load_grid(), which digests every top-level key except
    # the digest itself.  (v1 was written with the assertion outside the
    # digest, so the committed artifact could not self-verify.)
    grid["grid_digest"] = grid_digest(grid)
    grid_sha = write_grid(grid, args.out)
    print(f"grid_id: {GRID_ID}  version: {GRID_VERSION}  digest: {grid['grid_digest']}")
    print(
        f"conditions: {grid['condition_count']}  trials: {grid['trial_count']}  "
        f"seed_base: {grid['seed_base']}"
    )
    print(f"strata counts: {grid['strata_counts']}")
    print(f"json: {args.out}  sha256: {grid_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
