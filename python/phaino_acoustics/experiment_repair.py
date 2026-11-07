"""PR-4e C2 repair development run — B0-B3 paired adequacy-candidate comparison.

Authority: ADR 0020 D/E/G and ADR 0021 E.  This module emits a *development*
artifact only; the sealed ``pr4e-c2c-v1`` grid is not opened or referenced and
the C2 diagnosis seeds are not reused.  The independent paired evaluator is a
separate workstream and consumes the artifact; this module does not implement
its acceptance rules.

What is emitted
---------------
``c2-repair.json`` with the ADR 0020 §G contract:

* ``experiment == "c2-repair"``, ``protocol_digest``, ``grid_id``,
  ``frozen_grid_digest``, ``candidates``, ``environment_id``,
  ``measurement_model_id``, ``gate_policy_digest``, ``detection_loss_bound``,
  ``thresholds_changed``, per-candidate descriptions;
* per trial: explicit ``trial_id``/``pair_id``, ``condition``, ``mechanism``,
  ``seed``, ``stratum``, ``evaluation_only`` truth, ``observation`` and
  ``candidates.{B0,B1,B2,B3}`` records with ``adequacy_status``,
  ``reason_codes``, ``decision``, ``claim_statuses``, ``params`` and candidate
  metadata (B3 ``runtime_observables``);
* a ``development_summary`` block computed from the artifact (FRR, high-chirp
  FRR, acceleration detection, abstention, claim-status counts) plus the
  calibration record.

Design (development grid, not the sealed grid)
----------------------------------------------
* evaluation seed base 90_000_000, calibration seed base 91_000_000 — disjoint
  from E0 (20.26M), PR-4d (20.3M), C1 (40/41M), C2-A/B (50M/70M) and the sealed
  grid (60M);
* evaluation: 124 trials / 40 conditions — correct-CV continuum (8 geometries x
  2 speeds, 20 dB), correct-CV low SNR (3 geometries x 2 speeds, 10 dB),
  acceleration misspecification (600/3000 m geometry x 2 speeds x 3 levels),
  noise-only null (6);
* calibration: 80 correct-model trials / 40 conditions, independent seeds,
  spanning the runtime-observable chirp grid; only converged, finite fits are
  admitted to calibration (runtime-observable inclusion rule);
* paired: one observation per (condition, trial, seed), all four candidates
  processed on it.

No candidate is combined with another.  All candidates use the frozen adequacy
protocol; B2/B3 introduce candidate-local effective thresholds calibrated from
correct-model development data only, and the artifact declares that they
changed thresholds (the frozen protocol object itself is never mutated).

Decision vocabulary
-------------------
``candidates.<id>.decision`` is the **measurement-model adequacy decision**:
``adequate -> accept``, ``discrepancy -> reject``, ``insufficient_evidence`` or
``indeterminate -> undetermined``.  It is not the physical epistemic decision
(recorded per candidate as ``adequacy.epistemic_decision``; under the frozen C1
gate this is clock-conditional) and not the C1 claim status (recorded as
``claim_statuses`` from the frozen ``pr4e-claims-1.3.0`` gate).  The repair
compares adequacy; the C1 L1/L2/L3 gate is applied unchanged and never
bypassed.
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
from dataclasses import replace
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

import numpy as np

from phaino_claims.claims import apply_claim_statuses, claim_metrics
from phaino_claims.claims_protocol import (
    evidence_gate,
    load_protocol as load_claims_protocol,
    verify_protocol_digest,
)

from . import adequacy_protocol
from .adequacy import evaluate_adequacy, model_prediction
from .experiment import BASE, F_MAX, F_MIN, FRAME_LEN, HOP
from .features import estimate_if_track
from .fit_hardened import fit_hardened
from .measurement_model import (
    FRONT_END_PARAMETERS,
    MEASUREMENT_MODEL_ID,
    MEASUREMENT_MODEL_VERSION,
    measurement_model_record,
)
from .repair_candidates import (
    B1_DEMOD_BAND_HZ,
    B1_FRAME_LEN,
    B1_HOP,
    B2_AR_ORDER,
    B3_CHIRP_EDGES_HZ_S,
    B3_MIN_CALIBRATION_CELL,
    B3_SNR_EDGES_DB,
    B3_SELECTION_INPUTS,
    CANDIDATE_DESCRIPTIONS,
    CANDIDATE_IDS,
    FORBIDDEN_SELECTION_INPUTS,
    B3Calibration,
    assert_runtime_observable_inputs,
    b3_protocol_variant,
    calibrate_whitened_thresholds,
    decision_from_adequacy,
    dechirped_track,
    estimate_ar_coefficients,
    recompute_adequacy_with_test,
    runtime_observables,
    whitened_autocorrelation_test,
)
from .synthetic import Scenario, generate

EXPERIMENT_NAME = "c2-repair"
PROTOCOL_VERSION = "pr4e-c2-repair-dev-1.0.0"
SCHEMA_VERSION = "1.0.0"
GRID_ID = "pr4e-c2-dev-repair-v1"
GRID_VERSION = "1.0.0"

# New seed bases, disjoint from every prior set (see module docstring).
EVALUATION_SEED_BASE = 90_000_000
CALIBRATION_SEED_BASE = 91_000_000
SEED_FORMULA = "SEED_BASE + 1000*condition_index + trial"

# Pre-registered acceptance quantity required by ADR 0020 §G: the repair may
# not lose more acceleration detection than this absolute paired difference.
DETECTION_LOSS_BOUND = 0.10
DETECTION_LOSS_BOUND_RATIONALE = (
    "0.10 absolute detection-rate loss on independent acceleration trials was "
    "declared before the development run; this is a development-run bound, the "
    "locked evaluation applies its own pre-registered rule."
)
HIGH_CHIRP_OBSERVABLE_THRESHOLD_HZ_S = 150.0

# Pre-declared primary endpoint (ADR 0020 §G / ADR 0022 §4 / ADR 0023 §C/E).
# The evaluator's numeric primary_result checks criteria (1) and (4); the
# supported-coverage and claim-integrity guardrails (2)-(3) are mandatory and
# are reported as secondary metrics.  Wording is frozen before the sealed run.
PRIMARY_ENDPOINT = {
    "name": "correct_cv_supported_coverage_and_detection_B1_vs_B0",
    "definition": (
        "On identical paired sealed-grid observations, B1 vs B0: increase correct-CV "
        "valid supported coverage (equivalently reduce correct-CV false rejection) "
        "without losing acceleration discrepancy detection beyond the pre-registered "
        "bound. Supported coverage is the fraction of truth-correct correct-CV trials "
        "whose candidate record is validly supported by the frozen C1 claim gate."
    ),
    "candidate_comparison": (
        "B1 vs B0 (paired on the same observation; B0 is the paired baseline)"
    ),
    "decision_rule": (
        "B1 primary confirmation requires all of: (1) paired false-rejection risk "
        "difference (B1-B0) < 0; (2) paired valid supported coverage increases (B1 > B0); "
        "(3) zero claim-integrity violations for B1 (all claim statuses within "
        "{supported_conditional, undetermined, contradicted}; no supported_invariant); "
        "(4) the detection non-inferiority rule below holds. The evaluator numeric "
        "primary_result checks (1) and (4); (2) and (3) are mandatory pre-declared "
        "guardrails reported as secondary metrics and must both hold for confirmation."
    ),
    "detection_non_inferiority_rule": (
        "Paired acceleration discrepancy-detected risk difference (B1-B0) >= -0.10 "
        "(detection_loss_bound), under undecided_policy=not_detected: an undetermined "
        "acceleration trial is not counted as detected. The alternative excluded-policy "
        "analysis is a reported sensitivity, not the primary rule."
    ),
    "primary_metric": "supported_coverage",
    "candidates": ["B1", "B0"],
    "baseline": "B0",
    "candidate": "B1",
    "level": "primary",
    "multiplicity": (
        "single pre-declared primary comparison; all other endpoints are secondary and "
        "descriptive, with no alpha adjustment claimed"
    ),
}
UNDECIDED_POLICY = "not_detected"
UNDECIDED_POLICY_RATIONALE = (
    "Undetermined is neither acceptance nor detection (ADR 0022 §3): the primary detection "
    "denominator includes every acceleration trial, an undetermined trial is not counted "
    "as detected, and the alternative excluded-policy result is reported as a sensitivity."
)

# Per-observable reporting bins used by the evaluator's chirp/S
# power sections (ADR 0023 §C).  These are reporting bins, not B3's calibration
# bins (which use the declared B3_CHIRP_EDGES_HZ_S/B3_SNR_EDGES_DB constants).
CHIRP_REPORT_BINS = (
    {"bin_id": "chirp_lt_50", "lower": 0.0, "upper": 50.0},
    {"bin_id": "chirp_50_150", "lower": 50.0, "upper": 150.0},
    {"bin_id": "chirp_150_400", "lower": 150.0, "upper": 400.0},
    {"bin_id": "chirp_ge_400", "lower": 400.0, "upper": None},
)
SNR_REPORT_BINS = (
    {"bin_id": "snr_lt_10", "lower": -30.0, "upper": 10.0},
    {"bin_id": "snr_ge_10", "lower": 10.0, "upper": 61.0},
)

# Truth tolerances for the evaluator's truth-correct labels (evaluation only).
F0_REL_TOL = 0.01
V_REL_TOL = 0.02
T0_ABS_TOL = 0.25
B_REL_TOL = 0.05
F0_TIMES_B_REL_TOL = 0.05
CLAIM_KEYS = ("v", "f0_times_b", "t0")
ALLOWED_CLAIM_STATUSES = frozenset(
    {"supported_conditional", "undetermined", "contradicted"}
)
PARAMS_SCHEMA: dict[str, list[str]] = {
    "B0": ["f0", "v", "t0", "b", "sigma_f_hz"],
    "B1": [
        "f0",
        "v",
        "t0",
        "b",
        "sigma_f_hz",
        "demod_band_hz",
        "demod_frames",
        "transform_failed",
    ],
    "B2": [
        "f0",
        "v",
        "t0",
        "b",
        "sigma_f_hz",
        "ar_order",
        "whitened_ljung_box_statistic",
        "whitened_max_abs_acf",
        "whitened_ljung_box_threshold",
        "b0_ljung_box_statistic",
    ],
    "B3": [
        "f0",
        "v",
        "t0",
        "b",
        "sigma_f_hz",
        "estimated_chirp_rate_hz_s",
        "estimated_snr_db",
        "calibration_n",
        "ljung_box_statistic_max",
        "abs_corr_time_max",
        "abs_quadratic_coefficient_max",
        "abs_phase_correlation_max",
        "heldout_normalized_rmse_max",
    ],
}

DEFAULT_CLAIMS_PROTOCOL = (
    Path(__file__).resolve().parents[2] / "protocols" / "pr4e-claims-1.3.0.json"
)

STRATA = (
    "correct_cv_continuum",
    "correct_cv_low_snr",
    "acceleration_misspecification",
    "noise_only_null",
)
MECHANISMS = ("correct_cv", "acceleration", "null")

EVAL_GEOMETRY_M = (150.0, 250.0, 400.0, 700.0, 1200.0, 2200.0, 4000.0, 6500.0)
EVAL_SPEEDS_M_S = (100.0, 250.0)
EVAL_SNR_DB = (20.0,)
EVAL_TRIALS_PER_CONDITION = 4
LOW_SNR_GEOMETRY_M = (150.0, 600.0, 2500.0)
LOW_SNR_SPEEDS_M_S = (150.0, 250.0)
LOW_SNR_LEVELS_DB = (10.0,)
LOW_SNR_TRIALS = 3
ACCEL_GEOMETRY_M = (600.0, 3000.0)
ACCEL_SPEEDS_M_S = (150.0, 250.0)
ACCEL_LEVELS_M_S2 = (0.15, 0.30, 0.50)
ACCEL_SNR_DB = 20.0
ACCEL_TRIALS = 3
NULL_GEOMETRY_M = (3000.0,)
NULL_SNR_DB = (20.0, 10.0)
NULL_TRIALS = 3

CAL_GEOMETRY_M = (120.0, 170.0, 240.0, 350.0, 550.0, 800.0, 1200.0, 2000.0, 3500.0, 5500.0)
CAL_SPEEDS_M_S = (100.0, 250.0)
CAL_SNR_DB = (10.0, 20.0)
CAL_TRIALS_PER_CONDITION = 2


# ---------------------------------------------------------------------------
# Grid and protocol definitions (frozen before the run)
# ---------------------------------------------------------------------------

def _scenario_overrides(**overrides) -> dict:
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
    """The development evaluation conditions, in deterministic seed order."""
    conditions: list[dict] = []
    index = 0

    def add(name, mechanism, stratum, n_trials, label, **overrides):
        nonlocal index
        conditions.append(
            {
                "condition_index": index,
                "name": name,
                "mechanism": mechanism,
                "stratum": stratum,
                "n_trials": int(n_trials),
                "seed_base": EVALUATION_SEED_BASE,
                "label": label,
                "scenario": _scenario_overrides(**overrides),
            }
        )
        index += 1

    for geometry in EVAL_GEOMETRY_M:
        for speed in EVAL_SPEEDS_M_S:
            add(
                f"dev_cv_b{geometry:g}_v{speed:g}_s20",
                "correct_cv",
                "correct_cv_continuum",
                EVAL_TRIALS_PER_CONDITION,
                "correct constant-velocity model; development geometry continuum",
                b=geometry,
                v=speed,
                snr_db=20.0,
            )
    for geometry in LOW_SNR_GEOMETRY_M:
        for speed in LOW_SNR_SPEEDS_M_S:
            add(
                f"dev_lowsnr_b{geometry:g}_v{speed:g}_s10",
                "correct_cv",
                "correct_cv_low_snr",
                LOW_SNR_TRIALS,
                "correct constant-velocity model at 10 dB",
                b=geometry,
                v=speed,
                snr_db=10.0,
            )
    for geometry in ACCEL_GEOMETRY_M:
        for speed in ACCEL_SPEEDS_M_S:
            for accel in ACCEL_LEVELS_M_S2:
                add(
                    f"dev_acc_b{geometry:g}_v{speed:g}_a{accel:g}",
                    "acceleration",
                    "acceleration_misspecification",
                    ACCEL_TRIALS,
                    "unmodelled constant acceleration",
                    b=geometry,
                    v=speed,
                    accel=accel,
                    snr_db=ACCEL_SNR_DB,
                )
    for snr in NULL_SNR_DB:
        add(
            f"dev_null_b{NULL_GEOMETRY_M[0]:g}_s{snr:g}",
            "null",
            "noise_only_null",
            NULL_TRIALS,
            "noise-only null realisation (no source)",
            b=NULL_GEOMETRY_M[0],
            snr_db=snr,
            emit_signal=False,
        )
    return conditions


def build_calibration_conditions() -> list[dict]:
    """Correct-model calibration conditions (independent seeds, runtime-only use)."""
    conditions: list[dict] = []
    index = 0
    for geometry in CAL_GEOMETRY_M:
        for speed in CAL_SPEEDS_M_S:
            for snr in CAL_SNR_DB:
                conditions.append(
                    {
                        "condition_index": index,
                        "name": f"cal_b{geometry:g}_v{speed:g}_s{snr:g}",
                        "mechanism": "correct_cv",
                        "stratum": "calibration",
                        "n_trials": CAL_TRIALS_PER_CONDITION,
                        "seed_base": CALIBRATION_SEED_BASE,
                        "label": "correct-model calibration cell",
                        "scenario": _scenario_overrides(
                            b=geometry, v=speed, snr_db=snr
                        ),
                    }
                )
                index += 1
    return conditions


def condition_seed(condition: Mapping[str, object], trial: int) -> int:
    return int(condition["seed_base"]) + 1000 * int(condition["condition_index"]) + int(trial)


def scenario_for(condition: Mapping[str, object], seed: int) -> Scenario:
    overrides = dict(condition["scenario"])
    overrides["seed"] = int(seed)
    return replace(BASE, **overrides)


def build_grid(conditions: Optional[Sequence[dict]] = None) -> dict:
    conditions = list(build_conditions() if conditions is None else conditions)
    strata_counts: dict[str, int] = {}
    mechanism_counts: dict[str, int] = {}
    mechanism_trials: dict[str, int] = {}
    for condition in conditions:
        strata_counts[condition["stratum"]] = (
            strata_counts.get(condition["stratum"], 0) + condition["n_trials"]
        )
        mechanism_counts[condition["mechanism"]] = (
            mechanism_counts.get(condition["mechanism"], 0) + 1
        )
        mechanism_trials[condition["mechanism"]] = (
            mechanism_trials.get(condition["mechanism"], 0) + condition["n_trials"]
        )
    definition = {
        "grid_id": GRID_ID,
        "grid_version": GRID_VERSION,
        "development_grid": True,
        "sealed_grid_used": False,
        "sealed_grid_opened": False,
        "c2_diagnosis_seeds_reused": False,
        "seed_base": EVALUATION_SEED_BASE,
        "seed_formula": SEED_FORMULA,
        "conditions": conditions,
        "condition_count": len(conditions),
        "trial_count": sum(int(condition["n_trials"]) for condition in conditions),
        "strata": list(STRATA),
        "strata_counts": {stratum: strata_counts.get(stratum, 0) for stratum in STRATA},
        "mechanisms": list(MECHANISMS),
        "mechanism_counts": mechanism_counts,
        "mechanism_trials": mechanism_trials,
        "paired_design": True,
        "candidates": list(CANDIDATE_IDS),
        "candidate_descriptions": dict(CANDIDATE_DESCRIPTIONS),
        "candidate_combination": False,
        "truth_fields_forbidden_as_selection": True,
    }
    grid = dict(definition)
    grid["grid_digest"] = canonical_digest(definition)
    return grid


def canonical_json(document) -> bytes:
    return json.dumps(
        _jsonable(document), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def canonical_digest(document) -> str:
    return hashlib.sha256(canonical_json(document)).hexdigest()


def load_claims_protocol_file(path: Optional[str] = None) -> tuple[dict, str]:
    resolved = Path(path) if path else DEFAULT_CLAIMS_PROTOCOL
    if not resolved.exists():
        raise RuntimeError(
            f"frozen claims protocol not found at {resolved}; the C1 gate is required "
            "for claim integrity and B0-B3 must not bypass it"
        )
    protocol = load_claims_protocol(str(resolved))
    if not verify_protocol_digest(protocol):
        raise RuntimeError(f"claims protocol digest mismatch in {resolved}")
    return protocol, str(resolved)


def gate_policy_document(claims_protocol: Mapping[str, object]) -> dict:
    gate = evidence_gate(claims_protocol)
    return {
        "claims_protocol_digest": claims_protocol["protocol_digest"],
        "allowed_claim_statuses": sorted(ALLOWED_CLAIM_STATUSES),
        "supported_invariant_allowed": False,
        "evidence_gate": gate,
    }


def mathematical_evidence_block(claims_protocol: Mapping[str, object]) -> dict:
    """ADR 0020 §F references, recorded without claiming more than they prove."""
    evidence = claims_protocol.get("evidence") or {}
    symbolic = evidence.get("symbolic_proof") or {}
    certificate = evidence.get("certificate") or {}
    return {
        "applicable": True,
        "semantic_claim_digest": claims_protocol.get("protocol_digest"),
        "semantic_claim_digest_scope": (
            "frozen claims protocol: proposition, assumptions, L1/L2 statuses; "
            "a matching digest does not prove derivation correctness"
        ),
        "proof_artifact_digest": symbolic.get("digest"),
        "proof_artifact_scope": (
            "symbolic proof artifact digest recorded by the frozen claims protocol; "
            "the digest alone is not cited as proof"
        ),
        "independent_verification_record": {
            "available": bool(certificate),
            "certificate_sha256": certificate.get("certificate_sha256"),
            "certificate_version": certificate.get("certificate_version"),
            "certificate_builtin_protocol_digest": certificate.get(
                "certificate_builtin_protocol_digest"
            ),
            "verification_for_this_repair": False,
            "note": (
                "recorded in the frozen C1 protocol; no new independent verification was "
                "run for this C2 repair artifact, and no digest is cited as proof"
            ),
        },
        "claims_protocol_evidence_digest": claims_protocol.get("evidence_digest"),
    }


def build_repair_protocol(
    claims_protocol: Mapping[str, object],
    claims_protocol_path: str,
    grid: Mapping[str, object],
) -> dict:
    gate_document = gate_policy_document(claims_protocol)
    document = {
        "schema": "pr4e-c2-repair-protocol-v1",
        "experiment": EXPERIMENT_NAME,
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "authority": ["ADR 0020", "ADR 0021", "pr4e-c2-repair-plan"],
        "run_scope": "development" if grid.get("development_grid", True) else "sealed",
        "development_run": bool(grid.get("development_grid", True)),
        "development_grid": {
            "grid_id": grid["grid_id"],
            "frozen_grid_digest": grid["grid_digest"],
            "development_grid": bool(grid.get("development_grid", True)),
            "sealed_grid_used": bool(grid.get("sealed_grid_used", False)),
            "sealed_grid_opened": bool(grid.get("sealed_grid_opened", False)),
            "c2_diagnosis_seeds_reused": bool(grid.get("c2_diagnosis_seeds_reused", False)),
        },
        "measurement_model": measurement_model_record(),
        "measurement_model_id": MEASUREMENT_MODEL_ID,
        "measurement_model_version": MEASUREMENT_MODEL_VERSION,
        "adequacy_protocol_digest": adequacy_protocol.PROTOCOL_DIGEST,
        "claims_protocol": {
            "protocol_version": claims_protocol["protocol_version"],
            "protocol_digest": claims_protocol["protocol_digest"],
            "path": "protocols/pr4e-claims-1.3.0.json",
            "note": "relative repository path is digested, not the local absolute path",
        },
        "gate_policy_digest": canonical_digest(gate_document),
        "allowed_claim_statuses": sorted(ALLOWED_CLAIM_STATUSES),
        "supported_invariant_allowed": False,
        "candidates": dict(CANDIDATE_DESCRIPTIONS),
        "candidate_rules": {
            "B0": {
                "method": "original front end + frozen adequacy protocol",
                "physical_fit": "fit_hardened (unchanged)",
                "thresholds_changed": False,
                "params_schema": PARAMS_SCHEMA["B0"],
            },
            "B1": {
                "method": "coherent de-chirp + same-front-end re-extraction + same-estimator refit",
                "dechirped": (
                    "only the B0 fitted constant-velocity model's predicted frequency "
                    "history, via phase phi(t)=2*pi*integral f_pred(t) dt"
                ),
                "not_removed": (
                    "unmodelled acceleration and any other data-model discrepancy: the "
                    "demodulated residual IF ramp is re-extracted and refit, never smoothed"
                ),
                "demod_band_hz": B1_DEMOD_BAND_HZ,
                "frame_len": B1_FRAME_LEN,
                "hop": B1_HOP,
                "physical_fit": "fit_hardened on the reconstructed track (estimator unchanged)",
                "thresholds_changed": False,
                "params_schema": PARAMS_SCHEMA["B1"],
            },
            "B2": {
                "method": "AR(p) pre-whitening of the Ljung-Box autocorrelation test",
                "ar_order": B2_AR_ORDER,
                "calibration": "Yule-Walker on correct-model development residuals, pooled by sigma_f",
                "effective_threshold": "max(whitened calibration statistic) * 1.3",
                "other_tests": "frozen B0 tests, unchanged",
                "thresholds_changed": True,
                "params_schema": PARAMS_SCHEMA["B2"],
            },
            "B3": {
                "method": "conditional threshold calibration",
                "thresholds": [
                    "ljung_box_statistic_max",
                    "max_abs_acf_max",
                    "abs_corr_time_max",
                    "abs_quadratic_coefficient_max",
                    "abs_phase_correlation_max",
                    "heldout_normalized_rmse_max",
                ],
                "chirp_edges_hz_s": list(B3_CHIRP_EDGES_HZ_S),
                "snr_edges_db": list(B3_SNR_EDGES_DB),
                "min_calibration_cell": B3_MIN_CALIBRATION_CELL,
                "margin": float(adequacy_protocol.CALIBRATION_MARGIN),
                "selection_inputs": list(B3_SELECTION_INPUTS),
                "forbidden_inputs": list(FORBIDDEN_SELECTION_INPUTS),
                "thresholds_changed": True,
                "params_schema": PARAMS_SCHEMA["B3"],
            },
        },
        "mathematical_evidence": mathematical_evidence_block(claims_protocol),
        "thresholds_changed": {
            "B0": False,
            "B1": False,
            "B2": True,
            "B3": True,
            "frozen_adequacy_protocol_mutated": False,
            "frozen_adequacy_thresholds_used_by": ["B0", "B1"],
        },
        "detection_loss_bound": DETECTION_LOSS_BOUND,
        "detection_loss_bound_rationale": DETECTION_LOSS_BOUND_RATIONALE,
        "primary_endpoint": dict(PRIMARY_ENDPOINT),
        "undecided_policy": UNDECIDED_POLICY,
        "undecided_policy_rationale": UNDECIDED_POLICY_RATIONALE,
        "reporting_bins": {
            "chirp_bins": [dict(spec) for spec in CHIRP_REPORT_BINS],
            "snr_bins": [dict(spec) for spec in SNR_REPORT_BINS],
            "chirp_bin_population": "evaluation artifact trials",
            "snr_bin_population": (
                "B3 calibration admissible correct-model trials (the SNR conditioning "
                "population); a declared SNR branch with zero calibration samples is "
                "reported unverified per ADR 0023 C"
            ),
            "note": (
                "reporting bins for evaluator per-chirp power / SNR conditioning; "
                "B3 calibration uses the separately declared B3 observable edges"
            ),
        },
        "outcome_taxonomy": {
            "false_rejection": (
                "truth-correct correct-CV trials with adequacy discrepancy or decision reject"
            ),
            "detection": (
                "acceleration trials with adequacy discrepancy or decision reject; "
                "undetermined is not detection"
            ),
            "validly_supported": (
                "at least one supported_conditional claim and no claim status outside the "
                "frozen C1 allowed set; adequacy accept alone is never support"
            ),
            "supported_coverage": (
                "truth-correct correct-CV trials with a validly-supported candidate record"
            ),
            "abstention": "decision == undetermined",
            "zero_events": (
                "observed zero counts are reported with upper bounds, never as a zero "
                "probability"
            ),
            "family_reporting": (
                "mechanism-family and geometry-stratified results are always reported; "
                "no aggregate average may hide a family failure"
            ),
        },
        "within_tolerance": {
            "f0_rel": F0_REL_TOL,
            "v_rel": V_REL_TOL,
            "t0_abs_s": T0_ABS_TOL,
            "b_rel": B_REL_TOL,
            "f0_times_b_rel": F0_TIMES_B_REL_TOL,
            "note": "evaluation-only truth labels; the baseline B0 fit defines the labels",
        },
        "high_chirp_definition": {
            "observable": "estimated_chirp_rate_hz_s",
            "threshold_hz_s": HIGH_CHIRP_OBSERVABLE_THRESHOLD_HZ_S,
            "note": "runtime-observable summary subset; never a decision input",
        },
        "pairing": {
            "paired_design": True,
            "pair_id_scope": "one observation per (condition, trial, seed); all candidates nested",
            "candidate_combination": False,
        },
        "decision_mapping": {
            "adequate": "accept",
            "discrepancy": "reject",
            "insufficient_evidence": "undetermined",
            "indeterminate": "undetermined",
            "note": (
                "artifact `decision` is the measurement-model adequacy decision; the frozen "
                "ADR 0015 physical epistemic decision is recorded separately in each "
                "candidate's adequacy block and the C1 L1/L2/L3 gate is recorded in "
                "claim_statuses. No candidate bypasses the C1 claim gate."
            ),
        },
        "calibration": {
            "seed_base": CALIBRATION_SEED_BASE,
            "conditions": [
                {
                    "name": condition["name"],
                    "scenario": condition["scenario"],
                    "n_trials": condition["n_trials"],
                }
                for condition in build_calibration_conditions()
            ],
            "trials_per_condition": CAL_TRIALS_PER_CONDITION,
            "inclusion": "correct-model trials with converged optimization and finite adequacy metrics",
            "seeds_disjoint_from_evaluation": True,
            "seeds_reused_from_c2_diagnosis": False,
        },
        "environment_id_rule": "dev-<12 hex of canonical environment document>",
    }
    protocol = dict(document)
    protocol["protocol_digest"] = canonical_digest(document)
    return protocol


# ---------------------------------------------------------------------------
# Truth block (evaluation only) and small helpers
# ---------------------------------------------------------------------------

def _relative_errors(params: Mapping[str, float], scenario: Scenario) -> dict[str, float]:
    f0 = float(params["f0"])
    v = float(params["v"])
    t0 = float(params["t0"])
    b = float(params["b"])
    return {
        "f0": (f0 - scenario.f0) / scenario.f0,
        "v": (v - scenario.v) / scenario.v,
        "t0": (t0 - scenario.t0) / scenario.t0,
        "t0_abs": t0 - scenario.t0,
        "b": (b - scenario.b) / scenario.b,
        "f0_times_b": (f0 * b - scenario.f0 * scenario.b) / (scenario.f0 * scenario.b),
    }


def evaluation_only_block(
    scenario: Scenario, params: Mapping[str, float]
) -> dict:
    rel = _relative_errors(params, scenario)
    tolerance = {
        "f0": bool(abs(rel["f0"]) <= F0_REL_TOL),
        "v": bool(abs(rel["v"]) <= V_REL_TOL),
        "t0": bool(abs(rel["t0_abs"]) <= T0_ABS_TOL),
        "b": bool(abs(rel["b"]) <= B_REL_TOL),
        "f0_times_b": bool(abs(rel["f0_times_b"]) <= F0_TIMES_B_REL_TOL),
    }
    return {
        "scenario": {
            "f0": float(scenario.f0),
            "v": float(scenario.v),
            "t0": float(scenario.t0),
            "b": float(scenario.b),
            "accel": float(scenario.accel),
            "snr_db": float(scenario.snr_db),
            "geometry_m": float(scenario.b),
        },
        "scenario_extra": {
            "duration_s": float(scenario.duration),
            "sample_rate_hz": float(scenario.fs),
            "emit_signal": bool(scenario.emit_signal),
        },
        "estimate_within_tolerance": tolerance,
        "parameter_rel_errors": {key: float(value) for key, value in rel.items()},
        "tolerance_definitions": {
            "f0_rel": F0_REL_TOL,
            "v_rel": V_REL_TOL,
            "t0_abs_s": T0_ABS_TOL,
            "b_rel": B_REL_TOL,
            "f0_times_b_rel": F0_TIMES_B_REL_TOL,
        },
        "truth_correct": bool(all(tolerance.values())),
        "label_source": "baseline B0 fit (evaluation only)",
    }


def fallback_adequacy(reason: str) -> dict:
    return {
        "model_adequacy_status": "insufficient_evidence",
        "identifiability_status": "insufficient_evidence",
        "epistemic_decision": "undetermined",
        "reason_codes": [reason],
        "tests": {},
    }


def _compact_adequacy(adequacy_block: Mapping[str, object]) -> dict:
    tests = adequacy_block.get("tests") or {}
    statuses = {
        name: (test.get("status") if isinstance(test, Mapping) else None)
        for name, test in tests.items()
    }
    key_metrics: dict[str, dict[str, object]] = {}
    selected = {
        "standardized_residuals": (
            "rms_standardized",
            "robust_scale_ratio",
            "max_abs_z",
            "excess_kurtosis",
        ),
        "autocorrelation": ("ljung_box_statistic", "max_abs_acf"),
        "time_structure": (
            "corr_time",
            "quadratic_coefficient_over_sigma_f",
            "max_abs_phase_correlation",
        ),
        "block_prediction": (
            "median_normalized_rmse",
            "min_block_explained_fraction",
        ),
        "degeneracy": ("worst_rel_se", "condition_number"),
    }
    for name, keys in selected.items():
        test = tests.get(name)
        if not isinstance(test, Mapping):
            continue
        metrics = test.get("metrics") or {}
        key_metrics[name] = {
            key: _jsonable(metrics.get(key)) for key in keys if key in metrics
        }
    effective_thresholds: dict[str, dict[str, float]] = {}
    for name in ("autocorrelation", "time_structure"):
        test = tests.get(name)
        if not isinstance(test, Mapping):
            continue
        thresholds = test.get("thresholds") or {}
        effective_thresholds[name] = {
            key: float(value)
            for key, value in thresholds.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
    return {
        "epistemic_decision": adequacy_block.get("epistemic_decision"),
        "model_adequacy_status": adequacy_block.get("model_adequacy_status"),
        "identifiability_status": adequacy_block.get("identifiability_status"),
        "reason_codes": list(adequacy_block.get("reason_codes") or []),
        "test_statuses": statuses,
        "key_metrics": key_metrics,
        "effective_thresholds": effective_thresholds,
    }


def _finite_params(params: Mapping[str, object]) -> dict[str, float]:
    result = {}
    for key, value in params.items():
        if isinstance(value, bool):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(number):
            result[str(key)] = number
    return result


def claim_statuses_for(
    hardened,
    adequacy_block: Mapping[str, object],
    claims_protocol: Mapping[str, object],
) -> dict[str, str]:
    metrics = claim_metrics(hardened, adequacy_block)
    claims = apply_claim_statuses(metrics, claims_protocol)
    statuses = {claim["claim_id"]: claim["status"] for claim in claims}
    unexpected = sorted(set(statuses.values()) - ALLOWED_CLAIM_STATUSES)
    if unexpected:
        raise RuntimeError(
            f"claim gate produced statuses outside the allowed set: {unexpected}"
        )
    return statuses


# ---------------------------------------------------------------------------
# One trial: shared observation, then candidates B0-B3
# ---------------------------------------------------------------------------

def fit_observation(scenario: Scenario) -> dict:
    """Generate, extract and fit one observation (no truth used downstream)."""
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
    hardened = fit_hardened(track.t, track.f, c=scenario.c)
    params = np.array([hardened.f0, hardened.v, hardened.t0, hardened.b], dtype=np.float64)
    predicted_track = model_prediction(track.t, params, scenario.c)
    residuals = track.f - predicted_track
    observables = runtime_observables(
        track.t,
        predicted_track,
        residuals,
        hardened.sigma_f_hz,
        hardened.improvement_ratio,
        hardened.worst_rel_se,
        hardened.condition_number,
    )
    try:
        adequacy_block = evaluate_adequacy(
            track.t,
            track.f,
            params,
            hardened.sigma_f_hz,
            hardened.optimization_status,
            c=scenario.c,
        )
    except Exception as error:  # numerical failure must stay explicit, not invented
        adequacy_block = fallback_adequacy(f"adequacy_error:{type(error).__name__}")
    return {
        "scenario": scenario,
        "observation": observation,
        "track": track,
        "hardened": hardened,
        "params": params,
        "predicted": predicted_track,
        "residuals": residuals,
        "sigma_f_hz": float(hardened.sigma_f_hz),
        "adequacy": adequacy_block,
        "observables": observables,
    }


def _candidate_record(
    candidate: str,
    adequacy_block: Mapping[str, object],
    hardened,
    params: Mapping[str, float],
    sigma_f_hz: float,
    claims_protocol: Mapping[str, object],
    *,
    param_extra: Optional[Mapping[str, float]] = None,
    extra: Optional[Mapping[str, object]] = None,
    extra_reasons: Optional[Iterable[str]] = None,
) -> dict:
    claims = claim_statuses_for(hardened, adequacy_block, claims_protocol)
    numeric_params = {
        "f0": float(params["f0"]),
        "v": float(params["v"]),
        "t0": float(params["t0"]),
        "b": float(params["b"]),
        "sigma_f_hz": float(sigma_f_hz),
    }
    numeric_params.update(_finite_params(param_extra or {}))
    reasons = list(adequacy_block.get("reason_codes") or [])
    for reason in extra_reasons or ():
        if reason not in reasons:
            reasons.append(reason)
    record = {
        "adequacy_status": adequacy_block.get("model_adequacy_status"),
        "reason_codes": reasons,
        "decision": decision_from_adequacy(adequacy_block),
        "claim_statuses": claims,
        "params": numeric_params,
        "description": CANDIDATE_DESCRIPTIONS[candidate],
        "thresholds_changed": candidate in ("B2", "B3"),
        "adequacy": _compact_adequacy(adequacy_block),
    }
    if extra:
        record.update(dict(extra))
    return record


def run_evaluation_trial(
    condition: Mapping[str, object],
    trial: int,
    seed: int,
    *,
    calibration: Mapping[str, object],
    claims_protocol: Mapping[str, object],
    repair_protocol: Mapping[str, object],
) -> dict:
    """Process one observation with B0-B3 and return the evaluator trial record."""
    scenario = scenario_for(condition, seed)
    base = fit_observation(scenario)
    track = base["track"]
    hardened0 = base["hardened"]
    params0 = base["params"]
    sigma0 = base["sigma_f_hz"]
    ad0 = base["adequacy"]
    observables = base["observables"]
    status0 = hardened0.optimization_status

    candidates: dict[str, dict] = {}
    candidates["B0"] = _candidate_record(
        "B0", ad0, hardened0, hardened0.params, sigma0, claims_protocol
    )

    # B1 — coherent de-chirp against the B0 model prediction, re-extract, refit.
    transform_metadata = {
        "method": "coherent_demodulation_then_reextract_then_refit",
        "dechirped": "B0 model predicted constant-velocity frequency history only",
        "demod_band_hz": B1_DEMOD_BAND_HZ,
        "frame_len": B1_FRAME_LEN,
        "hop": B1_HOP,
        "residual_smoothing": False,
        "physical_model_changed": False,
        "estimator": "fit_hardened (unchanged)",
    }
    try:
        reconstructed = dechirped_track(
            base["observation"].signal,
            base["observation"].t,
            params0,
            scenario.c,
            track.t,
            fs=scenario.fs,
            band_hz=B1_DEMOD_BAND_HZ,
            frame_len=B1_FRAME_LEN,
            hop=B1_HOP,
        )
        hardened1 = fit_hardened(track.t, reconstructed, c=scenario.c)
        params1 = np.array(
            [hardened1.f0, hardened1.v, hardened1.t0, hardened1.b], dtype=np.float64
        )
        ad1 = evaluate_adequacy(
            track.t,
            reconstructed,
            params1,
            hardened1.sigma_f_hz,
            hardened1.optimization_status,
            c=scenario.c,
        )
        candidates["B1"] = _candidate_record(
            "B1",
            ad1,
            hardened1,
            hardened1.params,
            float(hardened1.sigma_f_hz),
            claims_protocol,
            param_extra={
                "demod_band_hz": B1_DEMOD_BAND_HZ,
                "demod_frames": float(reconstructed.size),
                "transform_failed": 0.0,
            },
            extra={"transform": transform_metadata, "transform_failed": False},
        )
    except Exception as error:
        candidates["B1"] = _candidate_record(
            "B1",
            ad0,
            hardened0,
            hardened0.params,
            sigma0,
            claims_protocol,
            param_extra={"demod_band_hz": B1_DEMOD_BAND_HZ, "transform_failed": 1.0},
            extra={
                "transform": transform_metadata,
                "transform_failed": True,
                "transform_failure": type(error).__name__,
            },
            extra_reasons=[f"b1_transform_failed:{type(error).__name__}"],
        )

    # B2 — AR-whitened Ljung-Box only; other tests remain B0.
    phi = np.asarray(calibration["b2_phi"], dtype=np.float64)
    b2_thresholds = calibration["b2_thresholds"]
    try:
        whitened_result = whitened_autocorrelation_test(
            base["residuals"], phi, b2_thresholds
        )
        ad2 = recompute_adequacy_with_test(ad0, "autocorrelation", whitened_result, status0)
        metrics = whitened_result.get("metrics") or {}
        whitened_lb = float(metrics.get("ljung_box_statistic", float("nan")))
        whitened_acf = float(metrics.get("max_abs_acf", float("nan")))
        candidates["B2"] = _candidate_record(
            "B2",
            ad2,
            hardened0,
            hardened0.params,
            sigma0,
            claims_protocol,
            param_extra={
                "ar_order": float(phi.size),
                "whitened_ljung_box_statistic": whitened_lb,
                "whitened_max_abs_acf": whitened_acf,
                "whitened_ljung_box_threshold": float(
                    b2_thresholds["ljung_box_statistic_max"]
                ),
                "b0_ljung_box_statistic": float(
                    ad0["tests"]["autocorrelation"]["metrics"]["ljung_box_statistic"]
                ),
            },
            extra={
                "whitening": {
                    "method": "yule_walker_ar_pooled_correct_model",
                    "ar_order": int(phi.size),
                    "coefficients": [float(value) for value in phi],
                    "thresholds": {
                        key: float(value)
                        for key, value in b2_thresholds.items()
                        if isinstance(value, (int, float)) and not isinstance(value, bool)
                    },
                    "tests_modified": ["autocorrelation"],
                    "other_tests": "frozen B0",
                    "thresholds_changed": True,
                }
            },
        )
    except Exception as error:
        candidates["B2"] = _candidate_record(
            "B2",
            ad0,
            hardened0,
            hardened0.params,
            sigma0,
            claims_protocol,
            param_extra={"ar_order": float(phi.size), "whitening_failed": 1.0},
            extra={
                "whitening": {"method": "yule_walker_ar_pooled_correct_model"},
                "whitening_failed": True,
                "whitening_failure": type(error).__name__,
            },
            extra_reasons=[f"b2_whitening_failed:{type(error).__name__}"],
        )

    # B3 — conditional thresholds selected from runtime observables only.
    b3: B3Calibration = calibration["b3"]
    thresholds, b3_metadata = b3.thresholds_for(observables)
    protocol_variant = b3_protocol_variant(thresholds)
    ad3 = evaluate_adequacy(
        track.t,
        track.f,
        params0,
        sigma0,
        status0,
        c=scenario.c,
        protocol=protocol_variant,
    )
    b3_extra_reasons: list[str] = []
    if b3_metadata["calibration_source"] in ("chirp_row", "global", "frozen_fallback"):
        b3_extra_reasons.append(f"b3_calibration_backoff:{b3_metadata['calibration_source']}")
    candidates["B3"] = _candidate_record(
        "B3",
        ad3,
        hardened0,
        hardened0.params,
        sigma0,
        claims_protocol,
        param_extra={
            "estimated_chirp_rate_hz_s": observables["estimated_chirp_rate_hz_s"],
            "estimated_snr_db": observables["estimated_snr_db"],
            "calibration_n": float(b3_metadata["n_calibration"]),
            "ljung_box_statistic_max": float(thresholds["ljung_box_statistic_max"]),
            "abs_corr_time_max": float(thresholds["abs_corr_time_max"]),
            "abs_quadratic_coefficient_max": float(
                thresholds["abs_quadratic_coefficient_max"]
            ),
            "abs_phase_correlation_max": float(thresholds["abs_phase_correlation_max"]),
            "heldout_normalized_rmse_max": float(thresholds["heldout_normalized_rmse_max"]),
        },
        extra={
            "runtime_observables": b3_metadata,
            "threshold_overrides": {
                "ljung_box_statistic_max": float(thresholds["ljung_box_statistic_max"]),
                "max_abs_acf_max": float(thresholds["max_abs_acf_max"]),
                "abs_corr_time_max": float(thresholds["abs_corr_time_max"]),
                "abs_quadratic_coefficient_max": float(
                    thresholds["abs_quadratic_coefficient_max"]
                ),
                "abs_phase_correlation_max": float(
                    thresholds["abs_phase_correlation_max"]
                ),
                "heldout_normalized_rmse_max": float(
                    thresholds["heldout_normalized_rmse_max"]
                ),
            },
        },
        extra_reasons=b3_extra_reasons,
    )

    observation_block = {
        "source": "front_end",
        "snr_db": float(observables["estimated_snr_db"]),
        "front_end": {
            "name": MEASUREMENT_MODEL_ID,
            "version": MEASUREMENT_MODEL_VERSION,
            "frame_len": int(FRAME_LEN),
            "hop": int(HOP),
            "f_min_hz": float(F_MIN),
            "f_max_hz": float(F_MAX),
            "sample_rate_hz": float(scenario.fs),
            "interpolation": "hann_stft_peak_log_parabolic",
            **{
                key: value
                for key, value in FRONT_END_PARAMETERS.items()
                if key in ("frame_len", "hop")
            },
        },
        "measurement_model_id": f"{MEASUREMENT_MODEL_ID}@{MEASUREMENT_MODEL_VERSION}",
        "estimated_chirp_rate_hz_s": float(observables["estimated_chirp_rate_hz_s"]),
        "n_frames": int(observables["n_frames"]),
        "observation_id": _observation_identity(condition, seed),
    }

    trial_record = {
        "trial_id": _trial_identity(condition, trial),
        "pair_id": _pair_identity(condition, seed),
        "condition": str(condition["name"]),
        "mechanism": str(condition["mechanism"]),
        "seed": int(seed),
        "stratum": str(condition["stratum"]),
        "runtime_observables": {
            key: float(value) for key, value in observables.items()
        },
        "estimated_chirp_rate": float(observables["estimated_chirp_rate_hz_s"]),
        "estimated_snr_db": float(observables["estimated_snr_db"]),
        "evaluation_only": evaluation_only_block(scenario, hardened0.params),
        "observation": observation_block,
        "candidates": candidates,
    }
    return _jsonable(trial_record)


def _trial_identity(condition: Mapping[str, object], trial: int) -> str:
    return f"{condition['name']}#trial{trial:04d}"


def _pair_identity(condition: Mapping[str, object], seed: int) -> str:
    return f"pair-{condition['name']}-seed{seed}"


def _observation_identity(condition: Mapping[str, object], seed: int) -> str:
    return f"obs-{condition['name']}-seed{seed}"


# ---------------------------------------------------------------------------
# Calibration (independent correct-model development sample)
# ---------------------------------------------------------------------------

def run_calibration(
    trials_override: Optional[int] = None,
) -> dict:
    conditions = build_calibration_conditions()
    if trials_override is not None:
        conditions = [
            {**condition, "n_trials": int(trials_override)} for condition in conditions
        ]
    admissible: list[dict] = []
    excluded: dict[str, int] = {}
    total = 0
    for condition in conditions:
        for trial in range(int(condition["n_trials"])):
            total += 1
            seed = condition_seed(condition, trial)
            try:
                base = fit_observation(scenario_for(condition, seed))
            except Exception as error:
                reason = f"trial_error:{type(error).__name__}"
                excluded[reason] = excluded.get(reason, 0) + 1
                continue
            if base["hardened"].optimization_status != "converged":
                reason = f"optimization_{base['hardened'].optimization_status}"
                excluded[reason] = excluded.get(reason, 0) + 1
                continue
            sigma = float(base["sigma_f_hz"])
            if not np.isfinite(sigma) or sigma <= 0.0:
                excluded["nonfinite_sigma"] = excluded.get("nonfinite_sigma", 0) + 1
                continue
            if not _adequacy_metrics_finite(base["adequacy"]):
                excluded["nonfinite_adequacy_metrics"] = (
                    excluded.get("nonfinite_adequacy_metrics", 0) + 1
                )
                continue
            admissible.append(base)
    if not admissible:
        raise RuntimeError("no admissible calibration trials; refusing to fabricate a null")

    normalized_residuals = [
        base["residuals"] / float(base["sigma_f_hz"]) for base in admissible
    ]
    phi = estimate_ar_coefficients(normalized_residuals, order=B2_AR_ORDER)
    b2_thresholds = calibrate_whitened_thresholds(normalized_residuals, phi)
    b3 = B3Calibration.fit(
        [
            {"observables": base["observables"], "adequacy": base["adequacy"]}
            for base in admissible
        ],
        margin=float(adequacy_protocol.CALIBRATION_MARGIN),
        min_cell=B3_MIN_CALIBRATION_CELL,
    )
    calibration_snr_values = [
        float(base["observables"]["estimated_snr_db"]) for base in admissible
    ]
    snr_reporting_counts = {
        spec["bin_id"]: sum(
            1
            for value in calibration_snr_values
            if value >= float(spec["lower"])
            and (spec["upper"] is None or value < float(spec["upper"]))
        )
        for spec in SNR_REPORT_BINS
    }
    return {
        "seed_base": CALIBRATION_SEED_BASE,
        "conditions": len(conditions),
        "trials": total,
        "admissible": len(admissible),
        "excluded": dict(sorted(excluded.items())),
        "inclusion_rule": (
            "correct-model calibration trial with converged optimization, finite positive "
            "sigma_f and finite adequacy statistics; no truth or label used"
        ),
        "b2_phi": [float(value) for value in phi],
        "b2_phi_l1": float(np.sum(np.abs(phi))),
        "b2_thresholds": _jsonable(b2_thresholds),
        "b3": b3,
        "snr_reporting_bin_counts": snr_reporting_counts,
        "seeds_disjoint_from_evaluation": True,
        "seeds_reused_from_c2_diagnosis": False,
    }


def _adequacy_metrics_finite(adequacy_block: Mapping[str, object]) -> bool:
    try:
        metrics = adequacy_block["tests"]["autocorrelation"]["metrics"]
        time_metrics = adequacy_block["tests"]["time_structure"]["metrics"]
        block_metrics = adequacy_block["tests"]["block_prediction"]["metrics"]
        values = [
            metrics["ljung_box_statistic"],
            metrics["max_abs_acf"],
            time_metrics["corr_time"],
            time_metrics["quadratic_coefficient_over_sigma_f"],
            time_metrics["max_abs_phase_correlation"],
            block_metrics["median_normalized_rmse"],
        ]
    except (KeyError, TypeError):
        return False
    return all(np.isfinite(float(value)) for value in values)


# ---------------------------------------------------------------------------
# Run assembly
# ---------------------------------------------------------------------------

_WORKER_CONTEXT: dict = {}


def _worker_init(calibration: dict, claims_protocol: dict, repair_protocol: dict) -> None:
    _WORKER_CONTEXT["calibration"] = calibration
    _WORKER_CONTEXT["claims_protocol"] = claims_protocol
    _WORKER_CONTEXT["repair_protocol"] = repair_protocol


def _worker_task(task: tuple[dict, int, int]) -> dict:
    condition, trial, seed = task
    return run_evaluation_trial(
        condition,
        trial,
        seed,
        calibration=_WORKER_CONTEXT["calibration"],
        claims_protocol=_WORKER_CONTEXT["claims_protocol"],
        repair_protocol=_WORKER_CONTEXT["repair_protocol"],
    )


def run_repair(
    *,
    jobs: int = 1,
    trials_override: Optional[int] = None,
    calibration_trials_override: Optional[int] = None,
    condition_override: Optional[Sequence[dict]] = None,
    output_dir: Optional[str] = None,
    quiet: bool = False,
    claims_protocol_path: Optional[str] = None,
    grid_override: Optional[Mapping[str, object]] = None,
) -> dict:
    adequacy_guard_before = _capture_adequacy_protocol_digest()
    claims_protocol, claims_path = load_claims_protocol_file(claims_protocol_path)
    if condition_override is not None:
        conditions = list(condition_override)
    elif grid_override is not None and "conditions" in grid_override:
        conditions = list(grid_override["conditions"])
    else:
        conditions = build_conditions()
    if trials_override is not None:
        conditions = [
            {**condition, "n_trials": int(trials_override)} for condition in conditions
        ]
    if grid_override is not None:
        grid = dict(grid_override)
    else:
        grid = build_grid(conditions)
    repair_protocol = build_repair_protocol(claims_protocol, claims_path, grid)
    environment = environment_document()
    environment_id = "dev-" + canonical_digest(environment)[:12]

    started = time.time()
    calibration = run_calibration(trials_override=calibration_trials_override)
    calibration_duration = time.time() - started

    tasks = [
        (condition, trial, condition_seed(condition, trial))
        for condition in conditions
        for trial in range(int(condition["n_trials"]))
    ]
    started = time.time()
    if jobs > 1 and len(tasks) > 1:
        with ProcessPoolExecutor(
            max_workers=jobs,
            initializer=_worker_init,
            initargs=(calibration, claims_protocol, repair_protocol),
        ) as pool:
            trials = list(pool.map(_worker_task, tasks, chunksize=2))
    else:
        trials = [
            run_evaluation_trial(
                condition,
                trial,
                seed,
                calibration=calibration,
                claims_protocol=claims_protocol,
                repair_protocol=repair_protocol,
            )
            for condition, trial, seed in tasks
        ]
    evaluation_duration = time.time() - started

    adequacy_guard_after = _capture_adequacy_protocol_digest()
    if adequacy_guard_after != adequacy_guard_before:
        raise RuntimeError(
            "frozen adequacy protocol changed during the repair run: B0/B1 must use the "
            "frozen thresholds and B2/B3 may only build candidate-local copies"
        )
    trials.sort(key=lambda record: (record["condition"], record["seed"]))
    summary = development_summary(trials)
    artifact = {
        "experiment": EXPERIMENT_NAME,
        "schema_version": SCHEMA_VERSION,
        "run_scope": repair_protocol["run_scope"],
        "protocol_digest": repair_protocol["protocol_digest"],
        "grid_id": grid["grid_id"],
        "frozen_grid_digest": grid["grid_digest"],
        "candidates": list(CANDIDATE_IDS),
        "environment_id": environment_id,
        "measurement_model_id": f"{MEASUREMENT_MODEL_ID}@{MEASUREMENT_MODEL_VERSION}",
        "gate_policy_digest": repair_protocol["gate_policy_digest"],
        "detection_loss_bound": DETECTION_LOSS_BOUND,
        "primary_endpoint": dict(PRIMARY_ENDPOINT),
        "undecided_policy": UNDECIDED_POLICY,
        "chirp_bins": _reporting_bins(trials, "estimated_chirp_rate_hz_s", CHIRP_REPORT_BINS),
        "snr_bins": _reporting_bins_from_counts(
            SNR_REPORT_BINS, calibration["snr_reporting_bin_counts"]
        ),
        "reporting_bin_populations": {
            "chirp_bins": "sealed/evaluation artifact trials (runtime estimated chirp rate)",
            "snr_bins": (
                "B3 calibration admissible correct-model trials; this is the population "
                "that determines whether the SNR conditioning branch was exercised"
            ),
        },
        "thresholds_changed": True,
        "thresholds_changed_candidates": ["B2", "B3"],
        "frozen_adequacy_protocol_digest": adequacy_protocol.PROTOCOL_DIGEST,
        "allowed_claim_statuses": sorted(ALLOWED_CLAIM_STATUSES),
        "mathematical_evidence": mathematical_evidence_block(claims_protocol),
        "adequacy_protocol_guard": {
            "digest_before": adequacy_guard_before["digest"],
            "digest_after": adequacy_guard_after["digest"],
            "thresholds_digest_before": adequacy_guard_before["thresholds_digest"],
            "thresholds_digest_after": adequacy_guard_after["thresholds_digest"],
            "unchanged": True,
        },
        "candidate_descriptions": dict(CANDIDATE_DESCRIPTIONS),
        "protocol": repair_protocol,
        "grid": grid,
        "environment": environment,
        "calibration": {
            "seed_base": calibration["seed_base"],
            "conditions": calibration["conditions"],
            "trials": calibration["trials"],
            "admissible": calibration["admissible"],
            "excluded": calibration["excluded"],
            "inclusion_rule": calibration["inclusion_rule"],
            "b2_phi": calibration["b2_phi"],
            "b2_phi_l1": calibration["b2_phi_l1"],
            "b2_thresholds": calibration["b2_thresholds"],
            "b3": calibration["b3"].to_artifact(),
            "snr_reporting_bin_counts": calibration["snr_reporting_bin_counts"],
            "seeds_disjoint_from_evaluation": True,
            "seeds_reused_from_c2_diagnosis": False,
        },
        "run_timing": {
            "calibration_s": round(calibration_duration, 3),
            "evaluation_s": round(evaluation_duration, 3),
            "jobs": int(jobs),
        },
        "development_summary": summary,
        "trials": trials,
    }
    artifact = _jsonable(artifact)
    artifact["calibration"]["b3"] = _jsonable(artifact["calibration"]["b3"])

    written = None
    digest = None
    if output_dir is not None:
        written = write_artifact(artifact, output_dir)
        digest = hashlib.sha256(Path(written).read_bytes()).hexdigest()
        write_summary_markdown(artifact, Path(output_dir) / "c2-repair-summary.md")
    return {
        "artifact": artifact,
        "artifact_path": written,
        "artifact_sha256": digest,
        "summary": summary,
        "calibration": artifact["calibration"],
        "elapsed_s": calibration_duration + evaluation_duration,
        "grid": grid,
        "repair_protocol": repair_protocol,
    }


def _capture_adequacy_protocol_digest() -> dict:
    """Snapshot the frozen adequacy protocol for the mutation guard.

    B2/B3 build candidate-local copies; this snapshot catches an accidental
    in-place mutation of the frozen object during the development run.
    """
    return {
        "digest": adequacy_protocol.PROTOCOL_DIGEST,
        "thresholds_digest": canonical_digest(adequacy_protocol.PROTOCOL["tests"]),
    }


def environment_document() -> dict:
    return {
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
    }


def _reporting_bins_from_counts(
    specs: Sequence[Mapping[str, object]], counts: Mapping[str, int]
) -> list[dict]:
    bins: list[dict] = []
    for spec in specs:
        bins.append({**dict(spec), "n_samples": int(counts.get(spec["bin_id"], 0))})
    return bins


def _reporting_bins(
    trials: Sequence[Mapping[str, object]],
    observable: str,
    specs: Sequence[Mapping[str, object]],
) -> list[dict]:
    """Count trials per declared reporting bin from runtime observables."""
    values = [
        float(trial["runtime_observables"][observable])
        for trial in trials
    ]
    bins: list[dict] = []
    for spec in specs:
        lower = float(spec["lower"])
        upper = spec["upper"]
        count = sum(
            1
            for value in values
            if value >= lower and (upper is None or value < float(upper))
        )
        bins.append({**dict(spec), "n_samples": int(count)})
    return bins


# ---------------------------------------------------------------------------
# Development summary (descriptive; the independent evaluator is separate)
# ---------------------------------------------------------------------------

def _is_detected(record: Mapping[str, object]) -> bool:
    return (
        record["adequacy_status"] == "discrepancy"
        or record["decision"] == "reject"
    )


def _truth_correct(trial: Mapping[str, object]) -> bool:
    return all(trial["evaluation_only"]["estimate_within_tolerance"].values())


def _rate(numerator: int, denominator: int) -> Optional[float]:
    return (numerator / denominator) if denominator else None


def _delta(candidate: Optional[float], baseline: Optional[float]) -> Optional[float]:
    if candidate is None or baseline is None:
        return None
    return float(candidate) - float(baseline)


def _counts(values: Iterable[object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def development_summary(trials: Sequence[Mapping[str, object]]) -> dict:
    correct_cv = [trial for trial in trials if trial["mechanism"] == "correct_cv"]
    correct_cv_truth = [trial for trial in correct_cv if _truth_correct(trial)]
    high_chirp = [
        trial
        for trial in correct_cv_truth
        if float(trial["runtime_observables"]["estimated_chirp_rate_hz_s"])
        >= HIGH_CHIRP_OBSERVABLE_THRESHOLD_HZ_S
    ]
    acceleration = [trial for trial in trials if trial["mechanism"] == "acceleration"]
    null_trials = [trial for trial in trials if trial["mechanism"] == "null"]
    candidates: dict[str, dict] = {}
    baseline = None
    for candidate in CANDIDATE_IDS:
        records = [trial["candidates"][candidate] for trial in trials]
        frr_k = sum(
            1 for trial in correct_cv_truth if _is_detected(trial["candidates"][candidate])
        )
        high_k = sum(1 for trial in high_chirp if _is_detected(trial["candidates"][candidate]))
        detection_k = sum(
            1 for trial in acceleration if _is_detected(trial["candidates"][candidate])
        )
        abstention_k = sum(1 for record in records if record["decision"] == "undetermined")
        claim_counts = {
            claim: _counts(record["claim_statuses"].get(claim) for record in records)
            for claim in CLAIM_KEYS
        }
        entry = {
            "adequacy_status_counts": _counts(record["adequacy_status"] for record in records),
            "decision_counts": _counts(record["decision"] for record in records),
            "frr_correct_cv": {
                "k": frr_k,
                "n": len(correct_cv_truth),
                "rate": _rate(frr_k, len(correct_cv_truth)),
            },
            "frr_correct_cv_high_chirp": {
                "k": high_k,
                "n": len(high_chirp),
                "rate": _rate(high_k, len(high_chirp)),
            },
            "detection_acceleration": {
                "k": detection_k,
                "n": len(acceleration),
                "rate": _rate(detection_k, len(acceleration)),
            },
            "abstention": {
                "k": abstention_k,
                "n": len(trials),
                "rate": _rate(abstention_k, len(trials)),
            },
            "claim_status_counts": claim_counts,
            "reason_counts": _counts(
                code for record in records for code in record["reason_codes"]
            ),
            "thresholds_changed": candidate in ("B2", "B3"),
        }
        if candidate == "B0":
            baseline = entry
        elif baseline is not None:
            entry["paired_vs_b0"] = {
                "false_rejection_delta": _delta(
                    entry["frr_correct_cv"]["rate"], baseline["frr_correct_cv"]["rate"]
                ),
                "high_chirp_frr_delta": _delta(
                    entry["frr_correct_cv_high_chirp"]["rate"],
                    baseline["frr_correct_cv_high_chirp"]["rate"],
                ),
                "detection_delta": _delta(
                    entry["detection_acceleration"]["rate"],
                    baseline["detection_acceleration"]["rate"],
                ),
                "abstention_delta": _delta(
                    entry["abstention"]["rate"], baseline["abstention"]["rate"]
                ),
            }
        candidates[candidate] = entry
    return {
        "cells": len({trial["condition"] for trial in trials}),
        "trials": len(trials),
        "by_mechanism": _counts(trial["mechanism"] for trial in trials),
        "by_stratum": _counts(trial["stratum"] for trial in trials),
        "truth_correct_by_mechanism": {
            mechanism: sum(
                1
                for trial in trials
                if trial["mechanism"] == mechanism and _truth_correct(trial)
            )
            for mechanism in MECHANISMS
        },
        "high_chirp_definition": {
            "observable": "estimated_chirp_rate_hz_s",
            "threshold_hz_s": HIGH_CHIRP_OBSERVABLE_THRESHOLD_HZ_S,
            "n_trials": len(high_chirp),
        },
        "null_trials": len(null_trials),
        "candidates": candidates,
        "note": (
            "Descriptive development-run counts only. The independent paired evaluator "
            "reports paired intervals and acceptance; this block makes no acceptance claim."
        ),
    }


# ---------------------------------------------------------------------------
# Artifact output
# ---------------------------------------------------------------------------

def write_artifact(artifact: Mapping[str, object], output_dir: str) -> str:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "c2-repair.json"
    payload = (json.dumps(_jsonable(artifact), indent=1, sort_keys=True, allow_nan=False) + "\n").encode(
        "utf-8"
    )
    path.write_bytes(payload)
    return str(path)


def _format_rate(block: Mapping[str, object]) -> str:
    rate = block.get("rate")
    if rate is None:
        return f"{block['k']}/{block['n']} (n/a)"
    return f"{block['k']}/{block['n']} ({100.0 * float(rate):.1f}%)"


def write_summary_markdown(artifact: Mapping[str, object], path: Path) -> str:
    summary = artifact["development_summary"]
    lines = [
        "# C2 repair development run (B0-B3)",
        "",
        f"- experiment: `{artifact['experiment']}`",
        f"- grid: `{artifact['grid_id']}` / `{artifact['frozen_grid_digest']}`",
        f"- protocol: `{artifact['protocol_digest']}`",
        f"- environment: `{artifact['environment_id']}`",
        f"- measurement model: `{artifact['measurement_model_id']}`",
        f"- detection_loss_bound (pre-registered): {artifact['detection_loss_bound']}",
        f"- undecided_policy: {artifact['undecided_policy']}",
        f"- primary_endpoint: {artifact['primary_endpoint']['name']} "
        f"({artifact['primary_endpoint']['candidate_comparison']})",
        f"- thresholds_changed: {artifact['thresholds_changed']} "
        f"({', '.join(artifact['thresholds_changed_candidates'])})",
        f"- cells / trials: {summary['cells']} / {summary['trials']}",
        f"- truth-correct by mechanism: {summary['truth_correct_by_mechanism']}",
        f"- high-chirp definition: {summary['high_chirp_definition']}",
        "",
        "| candidate | FRR correct-CV | FRR high-chirp | detection acceleration | abstention |",
        "|---|---|---|---|---|",
    ]
    for candidate in CANDIDATE_IDS:
        block = summary["candidates"][candidate]
        lines.append(
            "| {cand} | {frr} | {high} | {det} | {abs} |".format(
                cand=candidate,
                frr=_format_rate(block["frr_correct_cv"]),
                high=_format_rate(block["frr_correct_cv_high_chirp"]),
                det=_format_rate(block["detection_acceleration"]),
                abs=_format_rate(block["abstention"]),
            )
        )
    lines.append("")
    lines.append("Descriptive development counts; not an acceptance decision.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "PR-4e C2 repair development run (B0-B3). Emits an ADR 0020 §G artifact; "
            "never opens the sealed pr4e-c2c-v1 grid."
        )
    )
    parser.add_argument("--output-dir", default="/tmp/c2-repair-dev")
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument(
        "--trials",
        type=int,
        default=None,
        help="override trials per condition (smoke testing only; not the reported run)",
    )
    parser.add_argument(
        "--calibration-trials",
        type=int,
        default=None,
        help="override calibration trials per condition (smoke testing only)",
    )
    parser.add_argument("--claims-protocol", default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("--jobs must be >= 1")

    result = run_repair(
        jobs=args.jobs,
        trials_override=args.trials,
        calibration_trials_override=args.calibration_trials,
        output_dir=args.output_dir,
        quiet=args.quiet,
        claims_protocol_path=args.claims_protocol,
    )
    summary = result["summary"]
    print(
        f"experiment: {EXPERIMENT_NAME}  grid: {result['grid']['grid_id']}  "
        f"cells: {summary['cells']}  trials: {summary['trials']}  jobs: {args.jobs}"
    )
    print(f"frozen_grid_digest: {result['grid']['grid_digest']}")
    print(f"protocol_digest: {result['repair_protocol']['protocol_digest']}")
    print(
        f"calibration: {result['calibration']['admissible']}/"
        f"{result['calibration']['trials']} admissible correct-model trials"
    )
    print(
        "candidate     FRR(cv)        FRR(high-chirp)  detection(acc)  abstention"
    )
    for candidate in CANDIDATE_IDS:
        block = summary["candidates"][candidate]
        print(
            f"{candidate:<12} {_format_rate(block['frr_correct_cv']):<14} "
            f"{_format_rate(block['frr_correct_cv_high_chirp']):<16} "
            f"{_format_rate(block['detection_acceleration']):<15} "
            f"{_format_rate(block['abstention'])}"
        )
    print(f"artifact: {result['artifact_path']}")
    print(f"artifact_sha256: {result['artifact_sha256']}")
    print(f"elapsed_s: {result['elapsed_s']:.1f}")
    return 0


def _jsonable(obj):
    if isinstance(obj, Mapping):
        return {str(key): _jsonable(value) for key, value in obj.items()}
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


if __name__ == "__main__":
    raise SystemExit(main())
