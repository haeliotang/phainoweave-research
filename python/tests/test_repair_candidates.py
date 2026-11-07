"""Tests for the PR-4e C2 repair candidates B0-B3 (development-run method side).

These tests cover the candidate transforms/calibration primitives, the frozen
gates they must not bypass, the runtime-observable leakage assertion, and the
ADR 0020 §G artifact contract.  The independent paired evaluator is *not*
imported for metrics here; the artifact loader is used only to prove the
emitted document satisfies its strict JSON contract.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from phaino_acoustics import adequacy_protocol
from phaino_acoustics.adequacy import evaluate_adequacy
from phaino_acoustics.experiment_repair import (
    ALLOWED_CLAIM_STATUSES,
    CANDIDATE_IDS,
    PARAMS_SCHEMA,
    build_conditions,
    build_grid,
    build_repair_protocol,
    canonical_digest,
    claim_statuses_for,
    condition_seed,
    fit_observation,
    load_claims_protocol_file,
    run_evaluation_trial,
    run_repair,
)
from phaino_acoustics.fit_hardened import fit_hardened
from phaino_acoustics.repair_candidates import (
    ALLOWED_RUNTIME_OBSERVABLES,
    B3Calibration,
    B3_SELECTION_INPUTS,
    CANDIDATE_DESCRIPTIONS,
    FORBIDDEN_SELECTION_INPUTS,
    assert_runtime_observable_inputs,
    b3_protocol_variant,
    calibrate_whitened_thresholds,
    decision_from_adequacy,
    dechirped_track,
    estimate_ar_coefficients,
    recompute_adequacy_with_test,
    whitened_autocorrelation_test,
)
from phaino_acoustics.synthetic import Scenario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fit(seed: int, **overrides) -> dict:
    scenario = Scenario(seed=int(seed), **overrides)
    return fit_observation(scenario)


def _dechirp_and_refit(base: dict) -> tuple[dict, dict]:
    scenario = base["scenario"]
    track = base["track"]
    reconstructed = dechirped_track(
        base["observation"].signal,
        base["observation"].t,
        base["params"],
        scenario.c,
        track.t,
        fs=scenario.fs,
    )
    hardened = fit_hardened(track.t, reconstructed, c=scenario.c)
    params = np.array([hardened.f0, hardened.v, hardened.t0, hardened.b], dtype=np.float64)
    adequacy_block = evaluate_adequacy(
        track.t,
        reconstructed,
        params,
        hardened.sigma_f_hz,
        hardened.optimization_status,
        c=scenario.c,
    )
    return adequacy_block, {"hardened": hardened, "track": reconstructed, "params": params}


def _minimal_calibration(base: dict) -> dict:
    """A small honest calibration payload built from one correct-model trial.

    Used only to exercise the candidate pipeline deterministically; the reported
    development run uses the full independent calibration sample.
    """
    sequence = base["residuals"] / float(base["sigma_f_hz"])
    phi = estimate_ar_coefficients([sequence], order=8)
    b2_thresholds = calibrate_whitened_thresholds([sequence], phi)
    b3 = B3Calibration.fit(
        [{"observables": base["observables"], "adequacy": base["adequacy"]}],
        min_cell=1,
    )
    return {
        "b2_phi": [float(value) for value in phi],
        "b2_thresholds": b2_thresholds,
        "b3": b3,
    }


# ---------------------------------------------------------------------------
# Runtime observables and leakage gate
# ---------------------------------------------------------------------------

def test_runtime_observables_are_finite_and_declared():
    base = _fit(93_000_000, b=400.0, v=250.0, snr_db=20.0)
    observables = base["observables"]
    assert set(observables).issubset(set(ALLOWED_RUNTIME_OBSERVABLES) | {"sigma_f_hz"})
    for key, value in observables.items():
        assert np.isfinite(float(value)), key
    selection = {key: observables[key] for key in B3_SELECTION_INPUTS}
    assertion = assert_runtime_observable_inputs(selection)
    assert assertion["runtime_observable_only"] is True


def test_runtime_selector_rejects_truth_and_labels():
    allowed = {"estimated_chirp_rate_hz_s": 200.0}
    for forbidden in FORBIDDEN_SELECTION_INPUTS:
        with pytest.raises(AssertionError):
            assert_runtime_observable_inputs({**allowed, forbidden: 1.0})
    with pytest.raises(AssertionError):
        assert_runtime_observable_inputs({"scenario_label": "accel"})
    with pytest.raises(AssertionError):
        assert_runtime_observable_inputs({"not_a_declared_observable": 1.0})
    with pytest.raises(AssertionError):
        assert_runtime_observable_inputs({"estimated_chirp_rate_hz_s": float("nan")})


def test_b3_selection_uses_only_runtime_observables():
    high = _fit(93_000_001, b=150.0, v=250.0, snr_db=20.0)
    low = _fit(93_000_002, b=3000.0, v=250.0, snr_db=20.0)
    calibration = B3Calibration.fit(
        [
            {"observables": high["observables"], "adequacy": high["adequacy"]},
            {"observables": low["observables"], "adequacy": low["adequacy"]},
        ],
        min_cell=1,
    )
    # Extra truth fields in the caller's mapping must not leak into the decision.
    hostile = {
        **low["observables"],
        "true_b": 3000.0,
        "scenario_label": "correct_cv",
        "within_tolerance": True,
    }
    thresholds, metadata = calibration.thresholds_for(hostile)
    assert "true_b" not in metadata["runtime_observables"]
    assert set(metadata["runtime_observables"]).issubset(set(B3_SELECTION_INPUTS))
    assert metadata["truth_fields_used"] == []
    assert metadata["assertion"]["runtime_observable_only"] is True
    assert "heldout_normalized_rmse_max" in thresholds
    assert np.isfinite(float(thresholds["ljung_box_statistic_max"]))


# ---------------------------------------------------------------------------
# B1 de-chirp
# ---------------------------------------------------------------------------

def test_b1_dechirp_repairs_high_chirp_adequacy():
    base = _fit(92_000_000, b=150.0, v=250.0, snr_db=20.0)
    assert base["adequacy"]["model_adequacy_status"] == "discrepancy"
    adequacy_b1, _ = _dechirp_and_refit(base)
    assert adequacy_b1["model_adequacy_status"] == "adequate"
    lb0 = base["adequacy"]["tests"]["autocorrelation"]["metrics"]["ljung_box_statistic"]
    lb1 = adequacy_b1["tests"]["autocorrelation"]["metrics"]["ljung_box_statistic"]
    assert lb1 < lb0 / 5.0


def test_b1_does_not_remove_genuine_acceleration():
    base = _fit(92_000_001, b=3000.0, v=250.0, accel=0.4, snr_db=20.0)
    assert base["adequacy"]["model_adequacy_status"] == "discrepancy"
    adequacy_b1, pieces = _dechirp_and_refit(base)
    # An unmodelled acceleration is *not* in the CV model prediction, so the
    # de-chirped track still carries it and the adequacy layer still detects it.
    assert adequacy_b1["model_adequacy_status"] == "discrepancy"
    retained = pieces["track"] - base["predicted"]
    assert float(np.sqrt(np.mean(retained**2))) > 1.0
    assert decision_from_adequacy(adequacy_b1) == "reject"


# ---------------------------------------------------------------------------
# B2 pre-whitening
# ---------------------------------------------------------------------------

def _ar1_sequences(phi: float, n: int, count: int, seed: int) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    sequences = []
    for _ in range(count):
        noise = rng.normal(size=n)
        values = np.zeros(n)
        for index in range(1, n):
            values[index] = phi * values[index - 1] + noise[index]
        sequences.append(values)
    return sequences


def test_b2_ar_recovery_and_whitening():
    phi_true = 0.7
    sequences = _ar1_sequences(phi_true, 1500, 6, 93_100_000)
    phi = estimate_ar_coefficients(sequences, order=1)
    assert abs(float(phi[0]) - phi_true) < 0.1
    raw = sequences[0]
    whitened = raw[1:] - float(phi[0]) * raw[:-1]
    raw_acf1 = float(np.corrcoef(raw[:-1], raw[1:])[0, 1])
    whitened_acf1 = float(np.corrcoef(whitened[:-1], whitened[1:])[0, 1])
    assert raw_acf1 > 0.4
    assert abs(whitened_acf1) < 0.2


def test_b2_calibrated_whitened_null_and_preserved_misspecification():
    phi = np.zeros(8, dtype=np.float64)
    calibration_sequences = _ar1_sequences(0.6, 1200, 4, 93_200_000)
    thresholds = calibrate_whitened_thresholds(calibration_sequences, phi)
    assert thresholds["ljung_box_statistic_max"] > 0.0

    acceleration = _fit(92_000_002, b=3000.0, v=250.0, accel=0.4, snr_db=20.0)
    result = whitened_autocorrelation_test(
        acceleration["residuals"], phi, thresholds
    )
    recomputed = recompute_adequacy_with_test(
        acceleration["adequacy"],
        "autocorrelation",
        result,
        acceleration["hardened"].optimization_status,
    )
    # Only the autocorrelation test may change; block/time structure still detect
    # the genuine acceleration misspecification.
    assert recomputed["tests"]["time_structure"]["status"] == acceleration["adequacy"]["tests"]["time_structure"]["status"]
    assert recomputed["tests"]["block_prediction"]["status"] == acceleration["adequacy"]["tests"]["block_prediction"]["status"]
    assert recomputed["model_adequacy_status"] == "discrepancy"


def test_recompute_with_unchanged_test_matches_frozen_decision():
    base = _fit(92_000_003, b=700.0, v=250.0, snr_db=20.0)
    original = base["adequacy"]
    recomputed = recompute_adequacy_with_test(
        original,
        "autocorrelation",
        original["tests"]["autocorrelation"],
        base["hardened"].optimization_status,
    )
    assert recomputed["model_adequacy_status"] == original["model_adequacy_status"]
    assert recomputed["epistemic_decision"] == original["epistemic_decision"]
    assert recomputed["reason_codes"] == original["reason_codes"]


# ---------------------------------------------------------------------------
# B3 calibration and frozen-protocol integrity
# ---------------------------------------------------------------------------

def test_b3_variant_is_a_copy_and_does_not_mutate_frozen_protocol():
    before = adequacy_protocol.PROTOCOL_DIGEST
    before_threshold = adequacy_protocol.PROTOCOL["tests"]["autocorrelation"][
        "ljung_box_statistic_max"
    ]
    thresholds = {
        "ljung_box_statistic_max": 12345.0,
        "max_abs_acf_max": 0.9,
        "abs_corr_time_max": 0.2,
        "abs_quadratic_coefficient_max": 0.4,
        "abs_phase_correlation_max": 0.1,
        "heldout_normalized_rmse_max": 1.9,
    }
    variant = b3_protocol_variant(thresholds)
    assert variant["tests"]["autocorrelation"]["ljung_box_statistic_max"] == 12345.0
    assert variant["tests"]["block_prediction"]["heldout_normalized_rmse_max"] == 1.9
    assert adequacy_protocol.PROTOCOL_DIGEST == before
    assert adequacy_protocol.PROTOCOL["tests"]["autocorrelation"][
        "ljung_box_statistic_max"
    ] == before_threshold


def test_decision_mapping_is_the_adequacy_layer_decision():
    assert decision_from_adequacy({"model_adequacy_status": "adequate"}) == "accept"
    assert decision_from_adequacy({"model_adequacy_status": "discrepancy"}) == "reject"
    assert decision_from_adequacy({"model_adequacy_status": "indeterminate"}) == "undetermined"
    assert (
        decision_from_adequacy({"model_adequacy_status": "insufficient_evidence"})
        == "undetermined"
    )


# ---------------------------------------------------------------------------
# Claim gate (C1 not bypassed)
# ---------------------------------------------------------------------------

def test_claim_gate_never_emits_supported_invariant():
    base = _fit(93_300_000, b=400.0, v=250.0, snr_db=20.0)
    claims_protocol, _ = load_claims_protocol_file()
    statuses = claim_statuses_for(
        base["hardened"], base["adequacy"], claims_protocol
    )
    assert {"v", "f0_times_b", "t0"}.issubset(statuses)
    assert set(statuses.values()).issubset(ALLOWED_CLAIM_STATUSES)
    assert "supported_invariant" not in statuses.values()


# ---------------------------------------------------------------------------
# Determinism and the artifact contract
# ---------------------------------------------------------------------------

def test_candidate_pipeline_is_deterministic():
    base = _fit(93_400_000, b=400.0, v=250.0, snr_db=20.0)
    calibration = _minimal_calibration(base)
    claims_protocol, claims_path = load_claims_protocol_file()
    condition = build_conditions()[0]
    seed = condition_seed(condition, 0)
    protocol = build_repair_protocol(claims_protocol, claims_path, build_grid())
    first = run_evaluation_trial(
        condition,
        0,
        seed,
        calibration=calibration,
        claims_protocol=claims_protocol,
        repair_protocol=protocol,
    )
    second = run_evaluation_trial(
        condition,
        0,
        seed,
        calibration=calibration,
        claims_protocol=claims_protocol,
        repair_protocol=protocol,
    )
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


@pytest.fixture(scope="module")
def tiny_run(tmp_path_factory):
    conditions = build_conditions()
    selected = {}
    for condition in conditions:
        selected.setdefault(condition["stratum"], condition)
    output = tmp_path_factory.mktemp("c2-repair")
    result = run_repair(
        jobs=1,
        trials_override=1,
        calibration_trials_override=1,
        condition_override=list(selected.values()),
        output_dir=str(output),
    )
    return result, output


def test_artifact_satisfies_the_independent_evaluator_contract(tiny_run):
    result, output = tiny_run
    path = Path(result["artifact_path"])
    assert path.is_file()
    artifact = json.loads(path.read_text(encoding="utf-8"))

    # ADR 0020 §G / evaluator top-level contract.
    assert artifact["experiment"] == "c2-repair"
    assert artifact["candidates"] == list(CANDIDATE_IDS)
    assert artifact["thresholds_changed"] is True
    assert artifact["thresholds_changed_candidates"] == ["B2", "B3"]
    assert artifact["detection_loss_bound"] == pytest.approx(0.10)
    assert artifact["undecided_policy"] == "not_detected"
    assert artifact["run_scope"] == "development"
    endpoint = artifact["primary_endpoint"]
    for key in (
        "name",
        "definition",
        "candidate_comparison",
        "decision_rule",
        "detection_non_inferiority_rule",
    ):
        assert isinstance(endpoint[key], str) and endpoint[key]
    assert "B1" in endpoint["candidate_comparison"] and "B0" in endpoint["candidate_comparison"]
    assert endpoint["detection_non_inferiority_rule"].find("0.10") >= 0
    assert artifact["measurement_model_id"].startswith("e0-frontend-hann-stft-512-256")
    assert artifact["environment_id"].startswith("dev-")
    assert artifact["gate_policy_digest"] == artifact["protocol"]["gate_policy_digest"]
    assert artifact["protocol"]["adequacy_protocol_digest"] == adequacy_protocol.PROTOCOL_DIGEST
    assert artifact["adequacy_protocol_guard"]["unchanged"] is True
    assert artifact["grid"]["sealed_grid_used"] is False
    assert artifact["grid"]["sealed_grid_opened"] is False
    assert artifact["grid"]["c2_diagnosis_seeds_reused"] is False
    assert set(artifact["candidate_descriptions"]) == set(CANDIDATE_IDS)
    assert artifact["allowed_claim_statuses"] == sorted(ALLOWED_CLAIM_STATUSES)
    evidence = artifact["mathematical_evidence"]
    assert len(evidence["semantic_claim_digest"]) == 64
    assert len(evidence["proof_artifact_digest"]) == 64
    assert evidence["independent_verification_record"]["verification_for_this_repair"] is False

    # Digests recompute from the frozen definition documents.
    grid_doc = dict(artifact["grid"])
    grid_digest = grid_doc.pop("grid_digest")
    assert canonical_digest(grid_doc) == grid_digest
    protocol_doc = dict(artifact["protocol"])
    protocol_digest = protocol_doc.pop("protocol_digest")
    assert canonical_digest(protocol_doc) == protocol_digest

    # Explicit pairing, trial ids and candidate fields.
    trial_ids: set[str] = set()
    pair_ids: set[str] = set()
    for trial in artifact["trials"]:
        assert {"trial_id", "pair_id", "condition", "mechanism", "seed", "stratum"} <= set(trial)
        assert trial["trial_id"] not in trial_ids
        assert trial["pair_id"] not in pair_ids
        trial_ids.add(trial["trial_id"])
        pair_ids.add(trial["pair_id"])
        assert trial["mechanism"] in ("correct_cv", "acceleration", "null")
        scenario = trial["evaluation_only"]["scenario"]
        assert {"f0", "v", "t0", "b", "accel", "snr_db", "geometry_m"} <= set(scenario)
        tolerance = trial["evaluation_only"]["estimate_within_tolerance"]
        assert tolerance and all(isinstance(value, bool) for value in tolerance.values())
        assert trial["observation"]["source"] == "front_end"
        assert set(trial["candidates"]) == set(CANDIDATE_IDS)
        for candidate in CANDIDATE_IDS:
            record = trial["candidates"][candidate]
            assert {
                "adequacy_status",
                "reason_codes",
                "decision",
                "claim_statuses",
                "params",
            } <= set(record)
            assert record["decision"] in ("accept", "reject", "undetermined")
            assert {"v", "f0_times_b", "t0"} <= set(record["claim_statuses"])
            assert set(record["claim_statuses"].values()).issubset(ALLOWED_CLAIM_STATUSES)
            assert set(record["params"]) <= set(PARAMS_SCHEMA[candidate])
            assert all(np.isfinite(float(value)) for value in record["params"].values())
        assert np.isfinite(float(trial["estimated_chirp_rate"]))
        assert np.isfinite(float(trial["estimated_snr_db"]))
        b3_metadata = trial["candidates"]["B3"]["runtime_observables"]
        assert b3_metadata["truth_fields_used"] == []
        assert set(b3_metadata["runtime_observables"]).issubset(set(B3_SELECTION_INPUTS))
        assert "true_b" not in b3_metadata["runtime_observables"]
        assert trial["candidates"]["B0"]["thresholds_changed"] is False
        assert trial["candidates"]["B2"]["thresholds_changed"] is True
        assert trial["candidates"]["B3"]["thresholds_changed"] is True

    # Evaluation and calibration seed ranges are disjoint (new bases).
    evaluation_seeds = {
        condition_seed(condition, trial)
        for condition in artifact["grid"]["conditions"]
        for trial in range(int(condition["n_trials"]))
    }
    calibration_seeds = {
        int(artifact["calibration"]["seed_base"]) + 1000 * index + trial
        for index in range(int(artifact["calibration"]["conditions"]))
        for trial in range(int(artifact["calibration"]["trials"]) // max(1, int(artifact["calibration"]["conditions"])))
    }
    assert not (evaluation_seeds & calibration_seeds)

    # The evaluator's strict loader accepts the document.
    from phaino_c2_eval.artifacts import load_artifact

    loaded = load_artifact(path)
    assert len(loaded.trials) == len(artifact["trials"])
    assert loaded.candidates == CANDIDATE_IDS
    assert loaded.undecided_policy == "not_detected"
    assert loaded.primary_endpoint["name"] == endpoint["name"]
    assert loaded.chirp_bins is not None and loaded.snr_bins is not None
    assert sum(bin_spec.n_samples for bin_spec in loaded.chirp_bins) == len(artifact["trials"])
    assert (
        sum(bin_spec.n_samples for bin_spec in loaded.snr_bins)
        == artifact["calibration"]["admissible"]
    )
    assert artifact["reporting_bin_populations"]["snr_bins"].startswith(
        "B3 calibration admissible"
    )


def test_grid_override_plumbing_freezes_run_scope_and_grid_identity():
    """The sealed-run wrapper only passes a grid document; no sealed grid is read here."""
    claims_protocol, claims_path = load_claims_protocol_file()
    dev_grid = build_grid()
    sealed_like = dict(dev_grid)
    sealed_like.update(
        {
            "grid_id": "synthetic-sealed-like-v0",
            "grid_digest": "0" * 64,
            "development_grid": False,
            "sealed_grid_used": True,
            "sealed_grid_opened": True,
            "c2_diagnosis_seeds_reused": False,
        }
    )
    protocol = build_repair_protocol(claims_protocol, claims_path, sealed_like)
    assert protocol["run_scope"] == "sealed"
    assert protocol["development_run"] is False
    assert protocol["development_grid"]["sealed_grid_used"] is True
    assert protocol["development_grid"]["frozen_grid_digest"] == "0" * 64


def test_development_run_does_not_open_or_import_the_sealed_grid():
    source = Path(
        __import__("phaino_acoustics.experiment_repair", fromlist=["__file__"]).__file__
    ).read_text(encoding="utf-8")
    assert "c2c-grid-v1.json" not in source
    assert "from .c2_grid" not in source
    assert "import c2_grid" not in source


def test_b1_description_documents_what_is_dechirped():
    description = CANDIDATE_DESCRIPTIONS["B1"].lower()
    assert "de-chirp" in description or "dechirp" in description
    assert "acceleration" in description or "same stft" in description
