"""Tests for the E0 trial diagnostic tool (PR-4c, task 1).

The diagnostic must (a) reproduce the frozen E0 trial exactly, (b) expose the
termination/gradient facts that explain the cross-platform decision flip, and
(c) evaluate another platform's final parameters with the same objective and
gradient machinery.  These tests are deterministic and fast.
"""

from __future__ import annotations

import json
import platform
import pathlib
import sys

import numpy as np
import pytest

from phaino_acoustics.diagnose import (
    DIAGNOSTIC_VERSION,
    PARAMETER_SCALES,
    PARAM_ORDER,
    SCALE_VECTOR,
    build_diagnostic,
    condition_index,
    e0_observation,
    e0_scenario,
    e0_seed,
    evaluate_params,
    main,
    parse_params_set,
    write_diagnostic,
)
from phaino_acoustics.experiment import SEED_BASE, build_conditions

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
REFERENCE_PATH = REPO_ROOT / "docs" / "experiments" / "pr4c" / "trial57-params.json"


def _reference_trial57() -> dict:
    return json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))["macos_arm64"]


def _final_params_from_diagnostic(document: dict) -> np.ndarray:
    return np.array(
        [document["fit"]["final_params"][name] for name in PARAM_ORDER], dtype=np.float64
    )


def test_condition_index_and_seed_formula():
    """The diagnostic uses the pre-registered E0 seed formula, not a new one."""
    assert condition_index("snr_+5dB") == 3
    assert e0_seed("snr_+5dB", 57) == SEED_BASE + 3000 + 57 == 20264161

    scenario, seed = e0_scenario("snr_+5dB", 57)
    assert seed == 20264161
    conditions = {condition.name: condition for condition in build_conditions()}
    source = conditions["snr_+5dB"].scenario
    assert scenario.f0 == source.f0
    assert scenario.v == source.v
    assert scenario.t0 == source.t0
    assert scenario.b == source.b
    assert scenario.duration == source.duration
    assert scenario.snr_db == 5.0
    assert scenario.seed == seed

    with pytest.raises(ValueError):
        condition_index("not_a_condition")
    with pytest.raises(ValueError):
        e0_seed("snr_+5dB", -1)


def test_diagnostic_reproduces_frozen_e0_fit_exactly():
    """The instrumented replica must return bit-identical frozen-fit results."""
    document = build_diagnostic("snr_+5dB", 57)
    fit = document["fit"]
    agreement = fit["frozen_fit_agreement"]
    assert all(agreement.values()), agreement
    assert document["diagnostic_version"] == DIAGNOSTIC_VERSION
    assert document["condition_index"] == 3
    assert document["seed"] == 20264161

    termination = fit["termination"]
    assert termination["jacobian_method"] == "analytic"
    assert termination["finite_difference_step"] is None
    assert termination["nfev"] == termination["njev"]  # coupled analytic evaluation
    assert termination["nfev"] > 0
    assert termination["max_iter"] == 200
    assert isinstance(termination["converged"], bool)
    assert 1 <= termination["iterations"] <= termination["max_iter"]
    # Platform-dependent facts (frozen trial-57 decision/iteration count) are
    # asserted only in the reference-platform test below.

    # Gradient definitions must be internally consistent.
    raw = np.array([fit["raw_gradient"][name] for name in PARAM_ORDER])
    assert fit["raw_gradient_inf_norm"] == pytest.approx(float(np.max(np.abs(raw))), rel=1e-15)
    dimensionless = np.array(
        [fit["scale_normalized_gradient"][name] for name in PARAM_ORDER], dtype=np.float64
    )
    assert fit["scale_normalized_gradient_inf_norm"] == pytest.approx(
        float(np.max(np.abs(dimensionless))), rel=1e-15
    )
    e0_expected = float(np.max(np.abs(raw))) / np.sqrt(fit["objective"] * fit["n_points"])
    assert fit["e0_grad_norm"] == pytest.approx(e0_expected, rel=1e-12)

    # The last-five iteration record has the declared fields.
    history = fit["last_iterations"]
    assert 1 <= len(history) <= 5
    required = {
        "iteration",
        "objective",
        "relative_objective_change",
        "e0_rel_step",
        "scale_normalized_step",
        "lambda",
        "scale_normalized_gradient_inf_norm",
    }
    for entry in history:
        assert required <= set(entry)
        assert entry["scale_normalized_step"] >= 0.0
        assert entry["objective"] > 0.0


@pytest.mark.skipif(
    not (
        platform.system() == "Darwin"
        and platform.machine() == "arm64"
        and sys.version.split()[0] == "3.14.0"
        and np.__version__ == "2.4.4"
    ),
    reason="reference artifact was produced on macOS arm64 / Python 3.14.0 / numpy 2.4.4",
)
def test_trial57_matches_committed_reference_on_reference_platform():
    """On the reference environment the diagnostic reproduces the recorded facts."""
    reference = _reference_trial57()
    document = build_diagnostic("snr_+5dB", 57)
    fit = document["fit"]
    assert fit["final_params"] == pytest.approx(
        {name: reference[name] for name in PARAM_ORDER}, rel=1e-15, abs=1e-15
    )
    assert fit["e0_grad_norm"] == reference["grad_norm"]
    assert fit["termination"]["iterations"] == reference["iterations"] == 10
    assert fit["termination"]["converged"] == reference["converged"] is True
    assert fit["termination"]["iteration_budget_hit"] is False
    # The cross-platform fact this diagnostic exists to explain: on this platform
    # the e0 statistic is far below its 1e-6 threshold.
    assert fit["e0_grad_norm"] < 1e-10


def test_params_set_evaluation_deterministic_and_finite_difference_consistent():
    """--params-set evaluation is deterministic and the analytic gradient is right."""
    scenario, _seed, _obs, track = e0_observation("snr_+5dB", 57)
    # A point away from the stationary point: there the finite difference has
    # enough signal to be a meaningful independent check (near a minimum the
    # SSE difference is below float64 resolution).
    document = build_diagnostic("snr_+5dB", 57)
    final = _final_params_from_diagnostic(document)
    perturbed = final * np.array([1.01, 1.02, 0.98, 1.05])

    first = evaluate_params(track.t, track.f, scenario.c, perturbed)
    second = evaluate_params(track.t, track.f, scenario.c, perturbed)
    assert first == second  # exact determinism

    analytic = np.array([first["raw_gradient"][name] for name in PARAM_ORDER], dtype=np.float64)
    finite_difference = np.array(
        [first["finite_difference"]["raw_gradient"][name] for name in PARAM_ORDER],
        dtype=np.float64,
    )
    assert np.all(np.abs(analytic) > 1.0)
    relative_error = np.abs(analytic - finite_difference) / np.abs(analytic)
    assert np.max(relative_error) < 1.0e-6

    # The scale-normalized gradient must be exactly s * raw / sigma_f^2.
    sigma2 = first["sigma_f_hz"] ** 2
    expected = SCALE_VECTOR * analytic / sigma2
    got = np.array(
        [first["scale_normalized_gradient"][name] for name in PARAM_ORDER], dtype=np.float64
    )
    assert np.allclose(got, expected, rtol=1e-12, atol=0.0)
    assert first["scale_normalized_gradient_inf_norm"] == pytest.approx(
        float(np.max(np.abs(expected))), rel=1e-12
    )


def test_curvature_normalized_metric_agrees_with_the_hardened_rule():
    """The diagnostic's extra metric and the hardened rule's authoritative one agree."""
    from phaino_acoustics.fit_hardened import criteria_at

    scenario, _seed, _obs, track = e0_observation("snr_+5dB", 57)
    document = build_diagnostic("snr_+5dB", 57)
    final = _final_params_from_diagnostic(document)
    hardened = criteria_at(track.t, track.f, final, scenario.c)
    assert document["fit"]["curvature_normalized_gradient_inf_norm"] == pytest.approx(
        hardened["predicted_newton_step_inf_norm"], rel=1e-12
    )
    for name in PARAM_ORDER:
        assert document["fit"]["curvature_normalized_gradient"][name] == pytest.approx(
            hardened["predicted_newton_step"][name], rel=1e-12
        )

    displaced = final * np.array([1.01, 1.02, 0.98, 1.05])
    evaluated = evaluate_params(track.t, track.f, scenario.c, displaced)
    hardened_displaced = criteria_at(track.t, track.f, displaced, scenario.c)
    assert evaluated["curvature_normalized_gradient_inf_norm"] == pytest.approx(
        hardened_displaced["predicted_newton_step_inf_norm"], rel=1e-12
    )
    assert evaluated["curvature_normalized_gradient"] == pytest.approx(
        hardened_displaced["predicted_newton_step"], rel=1e-12
    )


def test_parse_params_set():
    name, theta = parse_params_set("p:500,250,20,3000")
    assert name == "p"
    assert np.array_equal(theta, np.array([500.0, 250.0, 20.0, 3000.0]))
    with pytest.raises(ValueError):
        parse_params_set("no-colon")
    with pytest.raises(ValueError):
        parse_params_set("p:1,2,3")
    with pytest.raises(ValueError):
        parse_params_set("p:1,2,3,four")
    with pytest.raises(ValueError):
        parse_params_set(":1,2,3,4")
    with pytest.raises(ValueError):
        parse_params_set("p:1,2,3,nan")


def test_diagnostic_json_schema_is_stable(tmp_path: pathlib.Path):
    """Writing the diagnostic produces strict JSON with the declared schema."""
    scenario, seed, _obs, track = e0_observation("snr_+5dB", 57)
    params = np.array([scenario.f0, scenario.v, scenario.t0, scenario.b]) * np.array(
        [1.01, 1.02, 0.98, 1.05]
    )
    document = build_diagnostic(
        "snr_+5dB",
        57,
        params_sets=[("hypothesis", params)],
        history_length=5,
    )
    output = tmp_path / "diag.json"
    write_diagnostic(document, str(output))
    assert [path.name for path in tmp_path.iterdir()] == ["diag.json"]

    loaded = json.loads(output.read_text(encoding="utf-8"))
    top_level = {
        "diagnostic_version",
        "tool",
        "generated_at_utc",
        "experiment",
        "condition",
        "condition_index",
        "trial",
        "seed",
        "scenario",
        "front_end",
        "definitions",
        "parameter_scales",
        "fit",
        "params_sets",
        "environment",
        "warnings",
    }
    assert top_level <= set(loaded)
    assert set(loaded["parameter_scales"]) == set(PARAM_ORDER)
    assert loaded["parameter_scales"] == PARAMETER_SCALES

    fit = loaded["fit"]
    assert {
        "termination",
        "final_params",
        "objective",
        "raw_gradient",
        "scale_normalized_gradient",
        "e0_grad_norm",
        "curvature_normalized_gradient",
        "curvature_normalized_gradient_inf_norm",
        "last_iterations",
        "identifiability",
        "frozen_fit_agreement",
    } <= set(fit)
    assert set(fit["final_params"]) == set(PARAM_ORDER)

    params_set = loaded["params_sets"]["hypothesis"]
    assert set(params_set["params"]) == set(PARAM_ORDER)
    assert {
        "objective",
        "raw_gradient",
        "raw_gradient_inf_norm",
        "scale_normalized_gradient",
        "scale_normalized_gradient_inf_norm",
        "e0_grad_norm",
        "curvature_normalized_gradient",
        "curvature_normalized_gradient_inf_norm",
        "finite_difference",
    } <= set(params_set)
    assert "finite_difference" in params_set
    # Strict JSON: the writer rejects NaN/Infinity, and the payload reparses.
    assert "NaN" not in output.read_text(encoding="utf-8")
    json.dumps(loaded, allow_nan=False)


def test_cli_writes_only_the_requested_output(tmp_path: pathlib.Path):
    output = tmp_path / "diag.json"
    code = main(
        [
            "--condition",
            "snr_+5dB",
            "--trial",
            "57",
            "--output",
            str(output),
            "--params-set",
            "truth:500,250,20,3000",
            "--history",
            "3",
        ]
    )
    assert code == 0
    assert [path.name for path in tmp_path.iterdir()] == ["diag.json"]
    document = json.loads(output.read_text(encoding="utf-8"))
    assert "truth" in document["params_sets"]
    assert len(document["fit"]["last_iterations"]) <= 3


def test_cli_rejects_malformed_params_set(tmp_path: pathlib.Path):
    output = tmp_path / "diag.json"
    code = main(
        [
            "--condition",
            "snr_+5dB",
            "--trial",
            "57",
            "--output",
            str(output),
            "--params-set",
            "broken-spec",
        ]
    )
    assert code == 2
    assert not output.exists()
