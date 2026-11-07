"""Tests for the E1 estimator-independence audit.

Covers the independent estimator's own forward model, clean-path parameter
recovery, determinism, audit-set declaration, tolerance helpers and the
independence/no-sealed-grid guards.  The full 36-trial audit is exercised by
the CLI, not in the unit tests.
"""

from __future__ import annotations

import copy
import pathlib

import numpy as np
import pytest

from phaino_acoustics import audit_estimator as audit
from phaino_acoustics.adequacy_protocol import PROTOCOL
from phaino_acoustics.experiment import BASE
from phaino_acoustics.synthetic import Scenario, apparent_frequency, generate


def _clean_scenario() -> Scenario:
    return Scenario(**{**BASE.__dict__, "b": 800.0, "v": 200.0, "snr_db": 60.0, "seed": 123})


def test_independent_forward_model_matches_generator_truth():
    scenario = _clean_scenario()
    observation = generate(scenario)
    times = observation.t[::50]
    truth = apparent_frequency(scenario, times)
    independent = audit.independent_forward_frequency(
        times, {"f0": scenario.f0, "v": scenario.v, "t0": scenario.t0, "b": scenario.b}, scenario.c
    )
    np.testing.assert_allclose(independent, truth, rtol=0.0, atol=1e-9)


def test_independent_estimator_recovers_a_clean_synthetic_doppler_tone():
    scenario = _clean_scenario()
    times, frequencies = audit.extract_track(scenario)
    first = audit.estimate_independent(times, frequencies, c=scenario.c)
    second = audit.estimate_independent(times, frequencies, c=scenario.c)
    for name in ("f0", "v", "t0", "b"):
        assert first["params"][name] is not None
        assert np.isfinite(first["params"][name])
        assert first["params"][name] == pytest.approx(second["params"][name], rel=0.0, abs=0.0)
    flags = audit.parameter_tolerance_flags(first["params"], {
        "f0": scenario.f0, "v": scenario.v, "t0": scenario.t0, "b": scenario.b
    })
    assert flags["all"] is True, (first["params"], flags)
    assert first["optimization_status"] in ("converged", "indeterminate")
    assert first["robust_loss"] == "soft_l1"
    assert first["nfev"] > 0


def test_estimation_is_deterministic_on_a_noisy_track():
    scenario = Scenario(**{**BASE.__dict__, "b": 600.0, "v": 60.0, "snr_db": 10.0, "seed": 321})
    times, frequencies = audit.extract_track(scenario)
    first = audit.estimate_independent(times, frequencies, c=scenario.c)
    second = audit.estimate_independent(times, frequencies, c=scenario.c)
    assert first["params"] == second["params"]
    assert first["se"] == second["se"]
    assert first["optimization_status"] == second["optimization_status"]


def test_audit_conditions_seeds_and_families_are_declared():
    conditions = audit.build_conditions()
    assert len(conditions) == 12
    assert sum(condition["n_trials"] for condition in conditions) == 36
    correct = [condition for condition in conditions if condition["family"] == "correct_constant_velocity"]
    accel = [condition for condition in conditions if condition["family"] == "acceleration_misspecification"]
    assert len(correct) == 8 and len(accel) == 4
    assert {condition["geometry_m"] for condition in correct} == {600.0, 1400.0}
    assert {condition["speed_m_s"] for condition in correct} == {60.0, 250.0}
    assert {condition["snr_db"] for condition in correct} == {10.0, 20.0}
    assert {condition["accel"] for condition in accel} == {0.15, 0.30}
    seeds = [audit.condition_seed(condition, trial) for condition in conditions for trial in range(condition["n_trials"])]
    assert len(seeds) == len(set(seeds))
    assert min(seeds) >= audit.AUDIT_SEED_BASE >= 100_000_000


def test_parameter_helpers_and_tolerance_agreement_counts():
    truth = {"f0": 500.0, "v": 250.0, "t0": 20.0, "b": 1400.0}
    close = {"f0": 502.0, "v": 248.0, "t0": 20.2, "b": 1380.0}
    flags = audit.parameter_tolerance_flags(close, truth)
    assert flags["all"] is True
    far = {"f0": 520.0, "v": 250.0, "t0": 20.0, "b": 1400.0}
    assert audit.parameter_tolerance_flags(far, truth)["all"] is False
    differences = audit.parameter_differences(close, close)
    for key in ("f0_rel", "v_rel", "t0_abs_s", "b_rel"):
        assert differences[key] == pytest.approx(0.0, abs=1e-15)
    errors = audit.parameter_truth_errors(close, truth)
    assert errors["f0_rel"] == pytest.approx(0.004)
    assert errors["t0_abs_s"] == pytest.approx(0.2)
    synthetic = [
        {"differences": {"f0_rel": 1e-3, "v_rel": -2e-3, "t0_abs_s": 0.01, "b_rel": 3e-3},
         "baseline": {"tolerance": {"all": True}}, "independent": {"tolerance": {"all": True}}},
        {"differences": {"f0_rel": 2e-3, "v_rel": -4e-3, "t0_abs_s": 0.02, "b_rel": 6e-3},
         "baseline": {"tolerance": {"all": True}}, "independent": {"tolerance": {"all": False}}},
    ]
    maxima = audit._max_differences_for(synthetic)
    assert maxima["f0_rel"] == pytest.approx(2e-3)
    assert maxima["b_rel"] == pytest.approx(6e-3)
    assert audit._tolerance_disagreements(synthetic) == 1


def test_no_fit_internals_no_sealed_grid_no_threshold_changes():
    source = pathlib.Path(audit.__file__).read_text(encoding="utf-8")
    assert "from .fit import" not in source
    assert "from .fit_hardened import" in source  # baseline only
    assert "pr4e-c2c-v1" in source  # declared as NOT opened
    # the actual scope flag in the artifact schema is false
    assert '"sealed_grid_opened": False' in source
    before = copy.deepcopy(PROTOCOL)
    _ = audit.estimate_independent(*audit.extract_track(_clean_scenario()))
    after = copy.deepcopy(PROTOCOL)
    assert before == after
