"""Tests for the hardened convergence rule v1 and the e0-hardened sweep (PR-4c).

The rule must (a) keep the frozen E0 code untouched, (b) separate the four
statuses, (c) refuse to decide on an iteration-budget hit, and (d) report the
trial-57 outcome honestly (whatever it is) rather than tune it.
"""

from __future__ import annotations

import json
import pathlib
import platform
import sys

import numpy as np
import pytest

import phaino_acoustics.experiment_hardened as hardened_sweep
from phaino_acoustics.diagnose import e0_observation
from phaino_acoustics.fit import fit_doppler
from phaino_acoustics.fit_hardened import (
    GRADIENT_TOL,
    HARDENED_VERSION,
    IDENT_CONDITION_NUMBER_TOL,
    IDENT_WORST_REL_SE_TOL,
    MAX_ITER,
    MIN_CONSECUTIVE,
    MODEL_MIN_IMPROVEMENT,
    OBJECTIVE_TOL,
    PARAMETER_SCALES,
    PARAM_ORDER,
    SCALE_VECTOR,
    STEP_TOL,
    VERIFICATION_DAMPING,
    _derive_decision,
    criteria_at,
    fit_hardened,
    lm_refine_hardened,
)
from phaino_acoustics.fit import _residual_and_jacobian


def _track(condition: str, trial: int) -> tuple:
    scenario, _seed, _obs, track = e0_observation(condition, trial)
    return scenario, track


def test_declared_rule_is_complete_and_sane():
    assert HARDENED_VERSION == "1.1.0"
    assert MIN_CONSECUTIVE >= 3  # two consecutive iterations are explicitly not enough
    assert GRADIENT_TOL > 0.0 and OBJECTIVE_TOL > 0.0 and STEP_TOL > 0.0
    assert GRADIENT_TOL < OBJECTIVE_TOL * 1e6  # finite but tight
    assert set(PARAMETER_SCALES) == set(PARAM_ORDER)
    assert np.array_equal(SCALE_VECTOR, np.array([500.0, 250.0, 20.0, 3000.0]))
    assert 0.0 < IDENT_WORST_REL_SE_TOL < 1.0
    assert IDENT_CONDITION_NUMBER_TOL > 1.0
    assert 0.0 < MODEL_MIN_IMPROVEMENT < 1.0
    assert MAX_ITER >= 50
    assert len(VERIFICATION_DAMPING) >= MIN_CONSECUTIVE


@pytest.mark.parametrize(
    "optimization_status, model_adequate, parameter_identifiable, expected",
    [
        ("indeterminate", True, True, ("indeterminate", "optimization_indeterminate")),
        ("indeterminate", False, False, ("indeterminate", "optimization_indeterminate")),
        ("failed", True, True, ("indeterminate", "numerical_failure")),
        ("converged", False, True, ("rejected", "model_inadequate")),
        ("converged", True, False, ("indeterminate", "parameters_unidentifiable")),
        ("converged", True, True, ("accepted", "converged_adequate_identifiable")),
    ],
)
def test_decision_precedence_is_declared(
    optimization_status, model_adequate, parameter_identifiable, expected
):
    """The four statuses are derived by one documented precedence."""
    assert _derive_decision(optimization_status, model_adequate, parameter_identifiable) == expected


def test_criteria_at_a_non_stationary_point_fails_and_at_the_solution_passes():
    scenario, track = _track("snr_+5dB", 57)
    frozen = fit_doppler(track.t, track.f, c=scenario.c)
    solution = np.array([frozen.f0, frozen.v, frozen.t0, frozen.b], dtype=np.float64)
    displaced = solution * np.array([1.01, 1.02, 0.98, 1.05])

    at_solution = criteria_at(track.t, track.f, solution, scenario.c)
    at_displaced = criteria_at(track.t, track.f, displaced, scenario.c)
    assert at_solution["criteria_pass"] is True
    assert at_displaced["criteria_pass"] is False
    assert at_displaced["predicted_newton_step_inf_norm"] > at_solution["predicted_newton_step_inf_norm"]

    # The dimensionless gradient metric is the declared curvature-normalized one.
    res, jac, _ = _residual_and_jacobian(track.t, track.f, displaced, scenario.c)
    raw = jac.T @ res
    expected = np.abs(raw) / (SCALE_VECTOR * np.diag(jac.T @ jac))
    got = np.array(
        [at_displaced["predicted_newton_step"][name] for name in PARAM_ORDER], dtype=np.float64
    )
    assert np.allclose(got, expected, rtol=1e-12, atol=0.0)
    assert at_displaced["predicted_newton_step_inf_norm"] == pytest.approx(
        float(np.max(expected)), rel=1e-12
    )


def test_trial57_hardened_status_is_coherent_on_any_platform():
    """Portable invariants for the ruling's focus case (statuses must cohere)."""
    scenario, track = _track("snr_+5dB", 57)
    frozen = fit_doppler(track.t, track.f, c=scenario.c)
    result = fit_hardened(track.t, track.f, c=scenario.c)

    assert result.optimization_status in ("converged", "indeterminate", "failed")
    assert result.decision_status in ("accepted", "rejected", "indeterminate")
    assert result.decision_status != "rejected"
    assert result.decision_reason in (
        "converged_adequate_identifiable",
        "parameters_unidentifiable",
        "optimization_indeterminate",
        "numerical_failure",
    )
    if result.optimization_converged:
        assert result.consecutive_confirmations >= MIN_CONSECUTIVE
        assert result.optimization_reason in ("fixed_point_verified", "criteria_confirmed")
    # Same estimator arithmetic: parameters must not diverge to a different
    # solution from the frozen fit.
    for name in PARAM_ORDER:
        assert result.params[name] == pytest.approx(getattr(frozen, name), rel=1e-7, abs=1e-9)
    assert result.objective <= frozen.sse * (1.0 + 1e-9)


def test_stalled_clearly_inadequate_model_is_rejected_deterministically():
    assert _derive_decision("indeterminate", False, False, improvement_ratio=0.002) == (
        "rejected",
        "model_inadequate",
    )
    assert _derive_decision("indeterminate", False, False, improvement_ratio=0.4) == (
        "indeterminate",
        "optimization_indeterminate",
    )
    assert _derive_decision("failed", False, False, improvement_ratio=0.0) == (
        "indeterminate",
        "numerical_failure",
    )


@pytest.mark.skipif(
    not (
        platform.system() == "Darwin"
        and platform.machine() == "arm64"
        and sys.version.split()[0] == "3.14.0"
        and np.__version__ == "2.4.4"
    ),
    reason="recorded trial-57 outcome was measured on macOS arm64 / Python 3.14.0 / numpy 2.4.4",
)
def test_trial57_under_the_hardened_rule_on_the_reference_platform():
    """Recorded outcome on this machine: converged, identifiable, adequate, accepted."""
    scenario, track = _track("snr_+5dB", 57)
    result = fit_hardened(track.t, track.f, c=scenario.c)
    assert result.optimization_converged is True
    assert result.optimization_status == "converged"
    assert result.optimization_reason == "fixed_point_verified"
    assert result.consecutive_confirmations >= MIN_CONSECUTIVE
    assert result.iteration_budget_hit is False
    assert result.parameter_identifiable is True
    assert result.model_adequate is True
    assert result.decision_status == "accepted"
    assert result.decision_reason == "converged_adequate_identifiable"
    assert result.iterations >= MIN_CONSECUTIVE
    assert result.criteria["predicted_newton_step_inf_norm"] < GRADIENT_TOL


def test_null_noise_only_is_never_accepted():
    _scenario, track = _track("null_noise_only", 0)
    result = fit_hardened(track.t, track.f, c=343.0)
    assert result.decision_status != "accepted"
    assert result.model_adequate is False
    assert result.decision_reason in (
        "optimization_indeterminate",
        "numerical_failure",
        "model_inadequate",
    )
    if result.iteration_budget_hit:
        assert result.optimization_status == "indeterminate"


def test_iteration_budget_hit_is_indeterminate_never_accepted_or_rejected():
    """A tiny budget must yield indeterminate at both the LM and decision level."""
    scenario, track = _track("snr_+20dB", 0)
    span = float(track.t[-1] - track.t[0])
    start = np.array([500.0, 250.0, 20.0, 3000.0])
    lm = lm_refine_hardened(
        track.t,
        track.f,
        scenario.c,
        start,
        float(track.t[0] - 10 * span),
        float(track.t[-1] + 10 * span),
        max_iter=2,
        min_consecutive=MIN_CONSECUTIVE,
    )
    assert lm["converged"] is False
    if lm["iteration_budget_hit"]:
        assert lm["termination_reason"] == "iteration_budget"
    else:
        assert lm["termination_reason"] == "stalled_without_stationarity"

    result = fit_hardened(track.t, track.f, c=scenario.c, max_iter=2)
    assert result.optimization_converged is False
    assert result.optimization_status == "indeterminate"
    assert result.decision_status == "indeterminate"
    assert result.decision_reason in ("optimization_indeterminate", "numerical_failure")
    assert result.decision_status not in ("accepted", "rejected")


def test_min_consecutive_below_three_is_rejected():
    scenario, track = _track("snr_+20dB", 0)
    span = float(track.t[-1] - track.t[0])
    with pytest.raises(ValueError):
        lm_refine_hardened(
            track.t,
            track.f,
            scenario.c,
            np.array([500.0, 250.0, 20.0, 3000.0]),
            float(track.t[0] - 10 * span),
            float(track.t[-1] + 10 * span),
            max_iter=10,
            min_consecutive=2,
        )


def test_hardened_seed_matches_the_full_e0_grid():
    """Filtering must not renumber trials: seeds are the full-grid E0 seeds."""
    from phaino_acoustics.experiment import SEED_BASE, build_conditions

    grid = build_conditions()
    for index, condition in enumerate(grid):
        for trial in (0, 1, 57):
            assert hardened_sweep.seed_for(condition.name, trial) == SEED_BASE + 1000 * index + trial

    record = hardened_sweep.run_trial(
        "snr_+5dB",
        {condition.name: condition for condition in grid}["snr_+5dB"].scenario,
        57,
        hardened_sweep.seed_for("snr_+5dB", 57),
    )
    assert record["seed"] == 20264161
    assert record["condition"] == "snr_+5dB"
    with pytest.raises(ValueError):
        hardened_sweep.seed_for("not_a_condition", 0)


def test_hardened_trial_record_schema_and_status_consistency():
    """Statuses are one of the declared values and obey the declared precedence."""
    scenario, _track_obj = _track("snr_+5dB", 57)
    record = hardened_sweep.run_trial(
        "snr_+5dB", scenario, 57, hardened_sweep.seed_for("snr_+5dB", 57)
    )
    payload = record["hardened"]
    assert payload["optimization_status"] in ("converged", "indeterminate", "failed")
    assert payload["decision_status"] in ("accepted", "rejected", "indeterminate")
    assert payload["optimization_converged"] == (payload["optimization_status"] == "converged")
    expected = _derive_decision(
        payload["optimization_status"],
        payload["model_adequate"],
        payload["parameter_identifiable"],
    )
    assert (payload["decision_status"], payload["decision_reason"]) == expected
    assert payload["criteria"]["thresholds"]["min_consecutive"] == MIN_CONSECUTIVE
    assert set(payload["params"]) == set(PARAM_ORDER)
    assert payload["n_starts"] == 5
    assert payload["njev"] == payload["nfev"]
    assert 2 <= payload["iterations"] <= MAX_ITER


def test_hardened_sweep_is_deterministic_and_does_not_touch_e0_artifacts(
    tmp_path: pathlib.Path,
):
    first = hardened_sweep.run_sweep(
        jobs=1, trials_override=2, name_filter="snr_+5dB", progress=False
    )
    second = hardened_sweep.run_sweep(
        jobs=1, trials_override=2, name_filter="snr_+5dB", progress=False
    )
    assert first["experiment"] == "e0-hardened"
    assert first["hardened_records_sha256"] == second["hardened_records_sha256"]
    assert len(first["trials"]) == 2
    assert first["conditions"][0]["n"] == 2

    # Artifact isolation: sentinel E0 files must be untouched.
    e0_json = tmp_path / "e0-results.json"
    e0_tables = tmp_path / "tables.md"
    e0_json.write_text('{"sentinel": "e0"}', encoding="utf-8")
    e0_tables.write_text("# E0 sentinel\n", encoding="utf-8")
    code = hardened_sweep.main(
        [
            "--output-dir",
            str(tmp_path),
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
    assert e0_json.read_text(encoding="utf-8") == '{"sentinel": "e0"}'
    assert e0_tables.read_text(encoding="utf-8") == "# E0 sentinel\n"
    hardened_json = tmp_path / hardened_sweep.ARTIFACT_JSON
    hardened_tables = tmp_path / hardened_sweep.ARTIFACT_TABLES
    assert hardened_json.exists() and hardened_tables.exists()
    loaded = json.loads(hardened_json.read_text(encoding="utf-8"))
    assert loaded["experiment"] == "e0-hardened"
    assert loaded["hardened_records_sha256"]
    assert "Decision status by condition" in hardened_tables.read_text(encoding="utf-8")


def test_hardened_artifact_names_never_collide_with_frozen_e0():
    assert hardened_sweep.ARTIFACT_JSON not in hardened_sweep.FROZEN_E0_ARTIFACT_NAMES
    assert hardened_sweep.ARTIFACT_TABLES not in hardened_sweep.FROZEN_E0_ARTIFACT_NAMES
    assert hardened_sweep.ARTIFACT_JSON == "e0-hardened-results.json"
    assert hardened_sweep.ARTIFACT_TABLES == "e0-hardened-tables.md"
