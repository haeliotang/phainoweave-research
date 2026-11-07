"""Tests for the C2 mechanism-attribution diagnosis module.

The module is diagnostic only: these tests pin the declared matrix, the
truth-frequency construction, the frozen adequacy thresholds (which must not
change), deterministic seeds, artifact schema, attribution rules, and the
runtime-isolation property (no runtime module imports the diagnosis).
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pytest

from phaino_acoustics import diagnose_c2
from phaino_acoustics.adequacy_protocol import PROTOCOL
from phaino_acoustics.experiment import BASE
from phaino_acoustics.features import estimate_if_track
from phaino_acoustics.synthetic import apparent_frequency, generate

REPO = pathlib.Path(__file__).resolve().parents[2]


def test_declared_matrix():
    signal, null = diagnose_c2.build_cells(n_trials=5)
    assert [cell.name for cell in signal] == [
        "cv_nominal",
        "accel_0.2",
        "accel_0.4",
        "geom_150",
        "geom_600",
        "geom_5000",
    ]
    assert [cell.name for cell in null] == [f"null_{cell.name}" for cell in signal]
    assert len(signal) == 6 and len(null) == 6
    families = {cell.family for cell in signal}
    assert families == {"correct_constant_velocity", "model_misspecification", "geometry_stress"}
    assert {cell.scenario.accel for cell in signal if cell.family == "model_misspecification"} == {0.2, 0.4}
    assert {cell.scenario.b for cell in signal if cell.family == "geometry_stress"} == {150.0, 600.0, 5000.0}
    for cell in signal:
        assert cell.scenario.v == 250.0
        assert cell.scenario.emit_signal is True
    for cell in null:
        assert cell.scenario.emit_signal is False
        assert cell.family == "noise_only_null"
        assert cell.n_trials == 5
    control = signal[0]
    assert control.family == "correct_constant_velocity"
    assert control.scenario.accel == 0.0
    assert control.scenario.b == 3000.0


def test_seeds_are_declared_and_deterministic():
    signal, null = diagnose_c2.build_cells(n_trials=3)
    cells = signal + null
    seeds = [diagnose_c2.cell_seed(cell, trial) for cell in cells for trial in range(3)]
    assert len(set(seeds)) == len(seeds)
    assert min(seeds) >= diagnose_c2.SEED_BASE
    index = {cell.name: position for position, cell in enumerate(cells)}
    for cell in cells:
        for trial in (0, 1, 2):
            expected = diagnose_c2.SEED_BASE + 1000 * index[cell.name] + trial
            assert diagnose_c2.cell_seed(cell, trial) == expected
    # disjoint from the E0 / PR-4d / claims bases
    assert diagnose_c2.SEED_BASE > 41_000_000  # disjoint from claims 40M/41M, E0 and PR-4d bases


def test_truth_track_is_apparent_frequency_with_declared_floor():
    from dataclasses import replace

    scenario = replace(BASE, seed=123456)
    observation = generate(scenario)
    track = estimate_if_track(
        observation.signal,
        scenario.fs,
        frame_len=diagnose_c2.FRAME_LEN,
        hop=diagnose_c2.HOP,
        f_min=diagnose_c2.F_MIN,
        f_max=diagnose_c2.F_MAX,
        t_start=float(observation.t[0]),
    )
    exact = diagnose_c2.truth_if_track(scenario, track.t, 0.0)
    np.testing.assert_allclose(exact, apparent_frequency(scenario, track.t), rtol=0.0, atol=0.0)
    noisy_a = diagnose_c2.truth_if_track(scenario, track.t, diagnose_c2.TRUTH_IF_NOISE_FLOOR_HZ, seed=scenario.seed)
    noisy_b = diagnose_c2.truth_if_track(scenario, track.t, diagnose_c2.TRUTH_IF_NOISE_FLOOR_HZ, seed=scenario.seed)
    np.testing.assert_array_equal(noisy_a, noisy_b)
    # declared floor: the deviation is white noise of the declared scale
    residual = noisy_a - exact
    assert 0.5 * diagnose_c2.TRUTH_IF_NOISE_FLOOR_HZ < float(np.std(residual)) < 2.0 * diagnose_c2.TRUTH_IF_NOISE_FLOOR_HZ


def test_extracted_and_truth_share_the_seed_pair():
    signal, _null = diagnose_c2.build_cells(n_trials=2)
    cell = signal[0]
    extracted = diagnose_c2.run_trial(cell, 0, "extracted")
    truth = diagnose_c2.run_trial(cell, 0, "truth")
    assert extracted["seed"] == truth["seed"] == diagnose_c2.cell_seed(cell, 0)
    assert extracted["evaluation_only"]["scenario"] == truth["evaluation_only"]["scenario"]
    assert extracted["if_source"] == "extracted" and truth["if_source"] == "truth"
    assert extracted["evaluation_only"]["scenario"]["seed"] == extracted["seed"]


def test_noiseless_truth_path_is_numerically_degenerate():
    signal, _null = diagnose_c2.build_cells(n_trials=1)
    record = diagnose_c2.run_trial(signal[0], 0, "truth_noiseless")
    assert record["hardened"]["sigma_f_hz"] < 1e-6
    assert record["adequacy"]["tests"]["standardized_residuals"]["status"] in ("fail", "indeterminate")
    assert record["adequacy"]["model_adequacy_status"] in ("insufficient_evidence", "indeterminate")


def test_frozen_adequacy_thresholds_are_not_changed():
    assert diagnose_c2.ADF_LB_THRESHOLD == float(
        PROTOCOL["tests"]["autocorrelation"]["ljung_box_statistic_max"]
    )
    assert diagnose_c2.ADF_LB_ORDER == int(PROTOCOL["tests"]["autocorrelation"]["ljung_box_order"])
    assert diagnose_c2.ADF_LB_DF == int(PROTOCOL["tests"]["autocorrelation"]["ljung_box_df"])
    assert diagnose_c2.ADF_BLOCK_RMSE_THRESHOLD == float(
        PROTOCOL["tests"]["block_prediction"]["heldout_normalized_rmse_max"]
    )


def test_small_run_schema_determinism_and_artifact(tmp_path):
    first = diagnose_c2.run_diagnosis(n_trials=2, jobs=1, cell_filter="cv_nominal", progress=False)
    second = diagnose_c2.run_diagnosis(n_trials=2, jobs=1, cell_filter="cv_nominal", progress=False)
    assert first["records_sha256"] == second["records_sha256"]
    assert first["artifact"] == "c2-diagnosis"
    assert first["version"] == diagnose_c2.DIAGNOSTIC_VERSION
    assert set(first) >= {
        "config",
        "environment",
        "records_sha256",
        "trials",
        "signal_cells",
        "noiseless_sensitivity",
        "null_cells",
        "null_distribution_comparison",
        "attribution",
        "limitations",
    }
    config = first["config"]
    assert config["n_trials_per_cell"] == 2
    assert config["thresholds_changed"] is False
    assert config["repair_routes_implemented"] is False
    assert "diagnosis only" in config["truth_usage"]
    assert config["adequacy_protocol_digest"]
    assert len(first["trials"]) > 0
    trial = first["trials"][0]
    assert set(trial) == {
        "cell",
        "family",
        "if_source",
        "trial",
        "seed",
        "evaluation_only",
        "hardened",
        "adequacy",
    }
    assert set(trial["adequacy"]) == {
        "model_adequacy_status",
        "identifiability_status",
        "epistemic_decision",
        "tests",
    }
    assert set(trial["adequacy"]["tests"]) == set(diagnose_c2.TEST_NAMES)
    comparison = first["null_distribution_comparison"]
    assert comparison["frozen_lb_threshold"] == diagnose_c2.ADF_LB_THRESHOLD
    assert comparison["asymptotic_lb_quantiles"]["p99"] > 0.0
    assert comparison["verdict"] in ("test_null_distribution_mismatch", "asymptotic_null_approximately_holds")
    for item in first["attribution"]:
        assert item["mechanism"] in diagnose_c2.MECHANISMS
        assert "verdict" in item and "statement" in item
    payload = json.dumps(first, allow_nan=False)
    assert "NaN" not in payload and "Infinity" not in payload
    # the markdown summary carries the per-cell counts and attribution
    markdown = diagnose_c2.render_markdown(first)
    for fragment in (
        "C2 mechanism attribution",
        "Cell matrix",
        "Parametric null distribution",
        "Attribution verdicts",
        "Limitations",
        "No adequacy threshold was changed",
    ):
        assert fragment.lower() in markdown.lower(), fragment


def test_artifact_writer(tmp_path):
    artifact = diagnose_c2.run_diagnosis(n_trials=1, jobs=1, cell_filter="cv_nominal", progress=False)
    out = tmp_path / "diagnosis.json"
    markdown = tmp_path / "diagnosis.md"
    artifact_sha, markdown_sha = diagnose_c2.write_artifact(artifact, str(out), str(markdown))
    assert out.exists() and markdown.exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["records_sha256"] == artifact["records_sha256"]
    assert len(artifact_sha) == 64 and len(markdown_sha) == 64


def test_attribution_rules():
    def summary(cell, source, family, n=10, false_rejections=0, correct_rejections=0):
        return {
            "cell": cell,
            "family": family,
            "if_source": source,
            "n": n,
            "false_rejections": false_rejections,
            "correct_rejections": correct_rejections,
        }

    comparison = {
        "model_valid_null_lb_quantiles": {"p99": 5000.0},
        "noise_only_null_lb_quantiles": {"p99": 120.0},
        "asymptotic_lb_quantiles": {"p99": 118.0},
        "empirical_over_asymptotic_p99_ratio": 42.0,
        "frozen_threshold_tail_model_valid": 0.0,
        "frozen_threshold_tail_noise_only": 0.0,
    }
    front_end = diagnose_c2._attribution(
        [
            summary("cv_nominal", "extracted", "correct_constant_velocity"),
            summary("cv_nominal", "truth", "correct_constant_velocity"),
            summary("geom_150", "extracted", "geometry_stress", false_rejections=10),
            summary("geom_150", "truth", "geometry_stress"),
        ],
        [],
        comparison,
    )
    verdicts = {item["mechanism"]: item["verdict"] for item in front_end}
    assert verdicts["high_chirp_geometry"] == "front_end_structural_error"
    assert verdicts["noise_only_null"] == "test_null_distribution_mismatch"

    both_paths = diagnose_c2._attribution(
        [
            summary("geom_150", "extracted", "geometry_stress", false_rejections=10),
            summary("geom_150", "truth", "geometry_stress", false_rejections=10),
        ],
        [],
        comparison,
    )
    verdicts = {item["mechanism"]: item["verdict"] for item in both_paths}
    assert verdicts["high_chirp_geometry"] == "fit_or_residual_test_null_calibration"

    acceleration = diagnose_c2._attribution(
        [
            summary("accel_0.2", "extracted", "model_misspecification", correct_rejections=10),
            summary("accel_0.2", "truth", "model_misspecification", correct_rejections=10),
        ],
        [],
        comparison,
    )
    verdicts = {item["mechanism"]: item["verdict"] for item in acceleration}
    assert verdicts["unmodelled_acceleration"] == "model_misspecification"

    no_rejection = diagnose_c2._attribution(
        [
            summary("cv_nominal", "extracted", "correct_constant_velocity"),
            summary("cv_nominal", "truth", "correct_constant_velocity"),
        ],
        [],
        comparison,
    )
    verdicts = {item["mechanism"]: item["verdict"] for item in no_rejection}
    assert verdicts["correct_constant_velocity_control"] == "no_false_rejection"


def test_asymptotic_quantiles_are_chi_square_like():
    asymptotic = diagnose_c2._asymptotic_quantiles()
    assert asymptotic["samples"] == diagnose_c2.ASYMPTOTIC_MC_SAMPLES
    quantiles = asymptotic["quantiles"]
    assert 80.0 < quantiles["p50"] < 90.0
    assert 110.0 < quantiles["p99"] < 130.0
    assert quantiles["p99"] > quantiles["p50"]


def test_diagnosis_is_not_imported_by_runtime_modules():
    package = REPO / "python" / "phaino_acoustics"
    runtime_modules = (
        "fit.py",
        "fit_hardened.py",
        "experiment.py",
        "experiment_hardened.py",
        "experiment_adequacy.py",
        "adequacy.py",
        "features.py",
        "synthetic.py",
    )
    for name in runtime_modules:
        source = (package / name).read_text(encoding="utf-8")
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                assert "diagnose_c2" not in stripped, (name, stripped)
    # the diagnosis module itself records that truth is diagnosis-only
    assert "diagnosis only" in (package / "diagnose_c2.py").read_text(encoding="utf-8")
