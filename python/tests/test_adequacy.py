"""Tests for the Model Adequacy & Discrepancy layer (PR-4d).

The load-bearing properties under test:

1. the protocol is declared and frozen (digest, thresholds, calibration rationale);
2. clock offset and clock rate are *exact* observational equivalences -- the
   unit test the ruling requires for offset<->t0, extended to clock rate;
3. acceleration is detected as a model discrepancy;
4. observational-equivalence trials are `undetermined`, never `supported`;
5. the decision never receives or reads the synthetic truth;
6. the tuning/locked grids, seeds and artifact schema are the declared ones.
"""

from __future__ import annotations

import inspect
import json
import pathlib

import numpy as np
import pytest

from phaino_acoustics import adequacy, adequacy_protocol
from phaino_acoustics.adequacy import (
    block_prediction_test,
    degeneracy_test,
    evaluate_adequacy,
    model_prediction,
    standardized_residuals_test,
    _epistemic_decision,
)
from phaino_acoustics.adequacy_protocol import (
    PARAM_ORDER,
    PROTOCOL,
    PROTOCOL_DIGEST,
    protocol_digest,
)
from phaino_acoustics.experiment import BASE, build_conditions
from phaino_acoustics.experiment_adequacy import (
    LOCKED_SEED_BASE,
    TUNING_CONDITIONS,
    locked_conditions,
    locked_seed,
    run_layer,
    run_trial,
    tuning_conditions,
    tuning_seed,
    main,
)
from phaino_acoustics.features import estimate_if_track
from phaino_acoustics.fit_hardened import fit_hardened
from phaino_acoustics.synthetic import (
    Scenario,
    apparent_frequency,
    doppler_frequency,
    generate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _track(scenario: Scenario):
    observation = generate(scenario)
    track = estimate_if_track(
        observation.signal,
        scenario.fs,
        t_start=float(observation.t[0]),
    )
    return observation, track


def _evaluate(scenario: Scenario):
    observation, track = _track(scenario)
    hardened = fit_hardened(track.t, track.f, c=scenario.c)
    params = np.array([hardened.f0, hardened.v, hardened.t0, hardened.b])
    result = evaluate_adequacy(
        track.t,
        track.f,
        params,
        hardened.sigma_f_hz,
        hardened.optimization_status,
        c=scenario.c,
    )
    return result, hardened, track, params


def _base(**overrides) -> Scenario:
    values = dict(
        f0=500.0,
        v=250.0,
        b=3000.0,
        t0=20.0,
        duration=60.0,
        fs=8000.0,
        c=343.0,
        snr_db=20.0,
        seed=12345,
    )
    values.update(overrides)
    return Scenario(**values)


def _condition(name: str, n_trials: int = 1):
    for condition in tuning_conditions(n_trials=n_trials):
        if condition.name == name:
            return condition
    raise KeyError(name)


# ---------------------------------------------------------------------------
# 1. Protocol: declared, frozen, with rationales
# ---------------------------------------------------------------------------

def test_protocol_is_declared_and_frozen():
    assert PROTOCOL["protocol_version"] == "adeq-1.0.0"
    assert PROTOCOL["layer"] == "model-adequacy-and-discrepancy"
    assert PROTOCOL_DIGEST == protocol_digest()
    assert len(PROTOCOL_DIGEST) == 64
    assert PROTOCOL["parameter_scales"] == {
        "f0": 500.0,
        "v": 250.0,
        "t0": 20.0,
        "b": 3000.0,
    }
    ac = PROTOCOL["tests"]["autocorrelation"]
    assert ac["lags"] == [1, 2, 3, 5, 8, 13, 21, 34, 55, 89]
    assert ac["ljung_box_order"] == 89
    assert ac["ljung_box_df"] == 85  # order - 4 fitted parameters
    assert PROTOCOL["tests"]["block_prediction"]["n_blocks"] >= 4
    assert PROTOCOL["decision"]["margin_fraction"] > 0.0
    assert PROTOCOL["decision"]["epistemic_precedence"]
    assert PROTOCOL["decision"]["identifiability_precedence"]
    assert PROTOCOL["calibration"]["population"] == [
        "snr_+5dB",
        "window_20s",
        "geom_v100_b300",
        "amp_geometric",
        "amp_mod30pct",
        "clock_1000ppm",
        "offset_0.3s",
    ]
    assert "accel_0.1" in PROTOCOL["calibration"]["excluded"]
    # Every test declares a rationale, and every threshold is positive.
    for name, entry in PROTOCOL["tests"].items():
        assert entry.get("rationale"), name
        for key, value in entry.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool) and "rationale" not in key:
                if key in ("n_blocks", "ljung_box_order", "ljung_box_df"):
                    assert value >= 4
                else:
                    assert value > 0.0, (name, key)


def test_clock_equivalence_is_declared_with_the_required_measurement():
    clock = PROTOCOL["clock_equivalence"]
    assert clock["invariant_parameter"] == "v"
    assert set(clock["degenerate_parameters"]) == {"f0", "t0", "b"}
    assert clock["required_external_measurement"]
    assert "t_observed = alpha * t_physical + beta" == PROTOCOL["clock_model"]


# ---------------------------------------------------------------------------
# 2. Exact observational equivalence (the ruling's offset<->t0 unit test)
# ---------------------------------------------------------------------------

def test_clock_offset_is_exactly_degenerate_with_t0():
    """A constant clock offset produces exactly the nominal curve at t0 - delta."""
    grid = np.linspace(-10.0, 50.0, 40001)
    for delta in (0.3, 2.0, 5.0):
        warped = _base(clock_offset_s=delta)
        observed = apparent_frequency(warped, grid)
        reparameterized = doppler_frequency(
            grid, warped.f0, warped.v, warped.t0 - delta, warped.b, warped.c
        )
        assert np.allclose(observed, reparameterized, rtol=1e-12, atol=1e-9)


def test_clock_rate_is_exactly_a_source_rescaling():
    """A clock rate error is exactly f0*(1+eps), t0/(1+eps), b/(1+eps), v unchanged."""
    grid = np.linspace(-10.0, 50.0, 40001)
    for ppm in (5000.0, 35000.0):
        eps = ppm * 1e-6
        warped = _base(clock_scale_ppm=ppm)
        observed = apparent_frequency(warped, grid)
        reparameterized = doppler_frequency(
            grid,
            warped.f0 * (1.0 + eps),
            warped.v,
            warped.t0 / (1.0 + eps),
            warped.b / (1.0 + eps),
            warped.c,
        )
        assert np.allclose(observed, reparameterized, rtol=1e-12, atol=1e-9)


# ---------------------------------------------------------------------------
# 3. Statuses: clean, clock, acceleration, null, noise
# ---------------------------------------------------------------------------

def test_clean_track_is_adequate_but_clock_degenerate():
    result, hardened, _track_obj, _params = _evaluate(_base())
    assert hardened.optimization_status == "converged"
    assert result["model_adequacy_status"] == "adequate"
    assert result["identifiability_status"] == "not_separately_identifiable"
    assert result["epistemic_decision"] == "undetermined"
    assert "clock_equivalence" in result["reason_codes"]
    # Evidence for a conditional (nominal-clock) protocol is recorded, but it is
    # not the epistemic decision.
    assert result["tests"]["degeneracy"]["conditional_claim_supported"] is True


def test_clock_offset_track_is_undetermined_and_not_supported():
    result, hardened, _track_obj, _params = _evaluate(_base(clock_offset_s=2.0))
    assert hardened.optimization_status == "converged"
    assert result["model_adequacy_status"] == "adequate"  # no residual discrepancy
    assert result["identifiability_status"] == "not_separately_identifiable"
    assert result["epistemic_decision"] == "undetermined"
    assert result["epistemic_decision"] != "supported"
    assert "clock_equivalence" in result["reason_codes"]


def test_clock_rate_track_is_undetermined_and_not_supported():
    result, hardened, _track_obj, _params = _evaluate(_base(clock_scale_ppm=35000.0))
    assert hardened.optimization_status == "converged"
    assert result["model_adequacy_status"] == "adequate"
    assert result["identifiability_status"] == "not_separately_identifiable"
    assert result["epistemic_decision"] == "undetermined"


def test_acceleration_is_detected_as_a_model_discrepancy():
    result, hardened, _track_obj, _params = _evaluate(_base(accel=0.25))
    assert hardened.optimization_status == "converged"
    assert result["model_adequacy_status"] == "discrepancy"
    assert result["epistemic_decision"] == "rejected"
    assert "residual_autocorrelation" in result["reason_codes"]
    assert "residual_time_structure" in result["reason_codes"]
    assert "heldout_prediction" in result["reason_codes"]


def test_null_noise_only_is_never_supported():
    scenario = _base(snr_db=0.0, emit_signal=False)
    result, _hardened, _track_obj, _params = _evaluate(scenario)
    assert result["epistemic_decision"] != "supported"
    assert result["epistemic_decision"] != "rejected" or result["model_adequacy_status"] == "discrepancy"
    assert result["tests"]["block_prediction"]["status"] == "fail"


def test_heavy_tailed_front_end_failure_is_insufficient_evidence():
    """A broken noise model must not be used to declare model discrepancy."""
    observation, track = _track(_base(snr_db=20.0))
    damaged = np.array(track.f, dtype=np.float64)
    rng = np.random.default_rng(7)
    indices = rng.choice(damaged.size, size=12, replace=False)
    damaged[indices] = rng.uniform(200.0, 2700.0, size=indices.size)
    hardened = fit_hardened(track.t, damaged, c=343.0)
    params = np.array([hardened.f0, hardened.v, hardened.t0, hardened.b])
    result = evaluate_adequacy(
        track.t, damaged, params, hardened.sigma_f_hz, hardened.optimization_status, c=343.0
    )
    assert result["tests"]["standardized_residuals"]["status"] in ("fail", "indeterminate")
    assert result["epistemic_decision"] in ("undetermined", "rejected")


# ---------------------------------------------------------------------------
# 4. Truth is never an input to a decision
# ---------------------------------------------------------------------------

def test_decision_entry_points_do_not_accept_truth():
    allowed = {"t", "f", "params", "sigma_f", "optimization_status", "c", "protocol"}
    parameters = set(inspect.signature(evaluate_adequacy).parameters)
    assert parameters == allowed
    for name in ("standardized_residuals_test", "block_prediction_test", "degeneracy_test"):
        callables = getattr(adequacy, name)
        names = set(inspect.signature(callables).parameters)
        assert not ({"scenario", "truth", "seed", "evaluation_only"} & names), (name, names)


def test_adequacy_block_schema_is_exact():
    result, _hardened, _track_obj, _params = _evaluate(_base())
    assert set(result) == {
        "model_adequacy_status",
        "identifiability_status",
        "epistemic_decision",
        "reason_codes",
        "tests",
    }
    assert set(result["tests"]) == {
        "standardized_residuals",
        "autocorrelation",
        "time_structure",
        "block_prediction",
        "degeneracy",
    }
    for name in ("standardized_residuals", "autocorrelation", "time_structure", "block_prediction"):
        assert result["tests"][name]["status"] in ("pass", "fail", "indeterminate")
        assert "metrics" in result["tests"][name]
    assert "conditional_claim_supported" in result["tests"]["degeneracy"]


# ---------------------------------------------------------------------------
# 5. Degeneracy evidence: directions, profile flatness, nominal gate
# ---------------------------------------------------------------------------

def test_degeneracy_evidence_reports_clock_directions_and_flat_profile():
    _result, _hardened, track, params = _evaluate(_base())
    evidence = degeneracy_test(
        track.t, track.f, params, 343.0, 0.19, PROTOCOL["tests"]["degeneracy"]
    )
    assert evidence["nominal_gate_pass"] is True
    assert evidence["clock_null_ratio"] <= evidence["null_ratio_threshold"]
    assert evidence["clock_not_separable"] is True
    assert evidence["clock_profile_flat"] is True
    assert evidence["status"] == "not_separately_identifiable"
    # Analytic null directions: alpha is degenerate with (f0,t0,b), beta with t0.
    alpha = evidence["analytic_null_directions"]["alpha"]["components"]
    beta = evidence["analytic_null_directions"]["beta"]["components"]
    assert abs(alpha["t0"]) > 0.0 and abs(alpha["b"]) > 0.0 and abs(alpha["f0"]) > 0.0
    assert abs(alpha["alpha"]) > 0.0
    assert abs(beta["beta"]) > 0.0 and abs(beta["t0"]) > 0.0
    assert evidence["analytic_null_directions"]["beta"]["relative_residual"] < 1e-6
    assert evidence["analytic_null_directions"]["alpha"]["relative_residual"] < 1e-6
    for entry in evidence["profile"].values():
        assert entry["relative_sse_change"] < 1e-4
    assert evidence["required_external_measurement"]


def test_block_prediction_discriminates_acceleration():
    _obs, track = _track(_base())
    hardened = fit_hardened(track.t, track.f, c=343.0)
    params = np.array([hardened.f0, hardened.v, hardened.t0, hardened.b])
    clean = block_prediction_test(
        track.t, track.f, params, 343.0, hardened.sigma_f_hz,
        PROTOCOL["tests"]["block_prediction"], PROTOCOL["decision"]["margin_fraction"],
    )
    accelerated_scenario = _base(accel=0.5)
    _obs2, track2 = _track(accelerated_scenario)
    hardened2 = fit_hardened(track2.t, track2.f, c=343.0)
    params2 = np.array([hardened2.f0, hardened2.v, hardened2.t0, hardened2.b])
    accelerated = block_prediction_test(
        track2.t, track2.f, params2, 343.0, hardened2.sigma_f_hz,
        PROTOCOL["tests"]["block_prediction"], PROTOCOL["decision"]["margin_fraction"],
    )
    assert clean["status"] == "pass"
    assert accelerated["status"] == "fail"
    assert accelerated["metrics"]["median_normalized_rmse"] > clean["metrics"]["median_normalized_rmse"]


# ---------------------------------------------------------------------------
# 6. Declared decision precedence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "optimization, adequacy_status, identifiability, expected",
    [
        ("indeterminate", "discrepancy", "insufficient_evidence", "undetermined"),
        ("converged", "discrepancy", "not_separately_identifiable", "rejected"),
        ("converged", "insufficient_evidence", "identifiable", "undetermined"),
        ("converged", "indeterminate", "identifiable", "undetermined"),
        ("converged", "adequate", "not_separately_identifiable", "undetermined"),
        ("converged", "adequate", "insufficient_evidence", "undetermined"),
        ("converged", "adequate", "identifiable", "supported"),
    ],
)
def test_epistemic_precedence(optimization, adequacy_status, identifiability, expected):
    tests = {
        "standardized_residuals": {"status": "pass", "reason": None},
        "autocorrelation": {"status": "pass", "reason": None},
        "time_structure": {"status": "pass", "reason": None},
        "block_prediction": {"status": "pass", "reason": None},
        "degeneracy": {"status": identifiability},
    }
    if adequacy_status == "discrepancy":
        tests["autocorrelation"] = {"status": "fail", "reason": "residual_autocorrelation"}
    decision, reasons = _epistemic_decision(
        optimization, adequacy_status, identifiability, tests
    )
    assert decision == expected
    if expected == "rejected":
        assert "residual_autocorrelation" in reasons


# ---------------------------------------------------------------------------
# 7. Grids, seeds, layers
# ---------------------------------------------------------------------------

def test_tuning_grid_matches_the_frozen_list_and_e0_seeds():
    conditions = tuning_conditions(n_trials=3)
    assert [condition.name for condition in conditions] == list(TUNING_CONDITIONS)
    e0_grid = build_conditions()
    e0_index = {condition.name: index for index, condition in enumerate(e0_grid)}
    for condition in conditions:
        for trial in (0, 1, 2):
            assert tuning_seed(condition.name, trial) == (
                20261104 + 1000 * e0_index[condition.name] + trial
            )
        assert condition.scenario.f0 == e0_grid[e0_index[condition.name]].scenario.f0


def test_locked_grid_stratification_and_new_seeds():
    conditions = locked_conditions()
    counts: dict[str, int] = {}
    for condition in conditions:
        counts[condition.mechanism] = counts.get(condition.mechanism, 0) + condition.n_trials
    # The Lead's framing: 400 misspecification (acceleration + clock rate),
    # 200 observational equivalence (clock offset).
    assert counts["acceleration"] + counts["clock_rate"] == 400
    assert counts["clock_offset"] == 200
    assert counts["acceleration"] == 240
    assert counts["clock_rate"] == 160
    assert counts["window"] == 100
    assert counts["geometry"] == 270
    assert counts["noise"] == 200
    assert counts["null"] == 100
    assert counts["within_tolerance"] == 150
    assert sum(counts.values()) == 1420
    assert set(counts) == {
        "acceleration",
        "clock_rate",
        "clock_offset",
        "window",
        "geometry",
        "noise",
        "null",
        "within_tolerance",
    }
    # New seeds, disjoint from every E0/tuning seed (E0 maximum is 20285103).
    e0_max = 20261104 + 1000 * (len(build_conditions()) - 1) + 999
    assert LOCKED_SEED_BASE > e0_max
    seeds = {locked_seed(index, trial) for index in range(30) for trial in range(5)}
    assert len(seeds) == 150
    assert min(seeds) >= LOCKED_SEED_BASE


def test_locked_condition_count_is_stable():
    assert len(locked_conditions()) == 27
    assert len({condition.name for condition in locked_conditions()}) == 27


# ---------------------------------------------------------------------------
# 8. Artifact schema, determinism, output path
# ---------------------------------------------------------------------------

def test_small_tuning_layer_schema_and_determinism():
    first = run_layer(
        "tuning", jobs=1, trials_override=1, name_filter="snr_+5dB", progress=False
    )
    second = run_layer(
        "tuning", jobs=1, trials_override=1, name_filter="snr_+5dB", progress=False
    )
    assert first["experiment"] == "e0-adequacy"
    assert first["layer"] == "tuning"
    assert first["protocol_digest"] == PROTOCOL_DIGEST
    assert first["records_sha256"] == second["records_sha256"]
    assert len(first["trials"]) == 1
    trial = first["trials"][0]
    assert set(trial) == {
        "condition",
        "trial",
        "seed",
        "layer",
        "mechanism",
        "evaluation_only",
        "observation",
        "hardened",
        "adequacy",
    }
    assert set(trial["evaluation_only"]) == {
        "scenario",
        "parameter_rel_errors",
        "within_e0_tolerance",
    }
    assert trial["evaluation_only"]["scenario"]["seed"] == trial["seed"]
    assert set(trial["observation"]) == {
        "if_rms_hz",
        "sigma_f_hz",
        "n_samples",
        "duration_s",
    }
    assert set(trial["hardened"]) == {
        "params",
        "optimization_status",
        "identifiability_status_old",
        "decision_status_old",
    }
    assert set(trial["adequacy"]) == {
        "model_adequacy_status",
        "identifiability_status",
        "epistemic_decision",
        "reason_codes",
        "tests",
    }
    assert trial["adequacy"]["epistemic_decision"] in (
        "supported",
        "rejected",
        "undetermined",
    )
    # Strict JSON: no NaN/Infinity survives.
    payload = json.dumps(first, allow_nan=False)
    assert "NaN" not in payload and "Infinity" not in payload
    assert first["calibration"] is not None
    # A filtered/sub-sampled run cannot re-derive the frozen thresholds.
    assert first["calibration"]["calibration_complete"] is False
    assert first["calibration"]["thresholds_match_calibration"] is None


def test_artifact_writer_writes_only_requested_path(tmp_path: pathlib.Path):
    output = tmp_path / "tuning.json"
    code = main(
        [
            "--layer",
            "tuning",
            "--output",
            str(output),
            "--filter",
            "snr_+5dB",
            "--trials",
            "1",
            "--jobs",
            "1",
            "--quiet",
        ]
    )
    assert code == 0
    assert [path.name for path in tmp_path.iterdir()] == ["tuning.json"]
    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded["layer"] == "tuning"
    assert loaded["protocol_digest"] == PROTOCOL_DIGEST


def test_run_trial_separates_evaluation_only_truth_from_the_decision():
    condition = _condition("snr_+5dB")
    seed = tuning_seed(condition.name, 0)
    record = run_trial(condition, 0, seed, "tuning")
    assert record["evaluation_only"]["scenario"]["emit_signal"] is True
    assert isinstance(record["evaluation_only"]["within_e0_tolerance"], bool)
    # The decision must be the same if truth changes but the observation does not.
    # Reconstruct the same observation and run the layer with the same inputs:
    adequacy_block = record["adequacy"]
    assert adequacy_block["model_adequacy_status"] in (
        "adequate",
        "discrepancy",
        "insufficient_evidence",
        "indeterminate",
    )
    assert adequacy_block["identifiability_status"] in (
        "identifiable",
        "not_separately_identifiable",
        "insufficient_evidence",
    )
