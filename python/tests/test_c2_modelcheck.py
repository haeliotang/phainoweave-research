"""Tests for the independent C2-M2 predictive measurement-error model check."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from phaino_c2_modelcheck import (
    ArtifactError,
    bootstrap_interval,
    evaluate,
    ks_statistic,
    load_artifact,
    main,
    wilson_interval,
)
from phaino_c2_modelcheck.report import report_json, report_markdown

MODELS = ("M0", "M1", "M2", "M3")
DEFAULT_TOLERANCES = {
    "decision_frr_abs_error_pp": 10.0,
    "distribution_ks_max": 0.2,
    "error_mean_abs_hz": 2.0,
    "error_rms_abs_hz": 2.0,
    "acf_max_abs": 0.2,
}
GOOD_ACF = [
    {"lag_s": 0.0, "value": 1.0},
    {"lag_s": 0.5, "value": 0.5},
    {"lag_s": 1.0, "value": 0.2},
]
BAD_ACF = [
    {"lag_s": 0.0, "value": 1.0},
    {"lag_s": 0.5, "value": 0.8},
    {"lag_s": 1.0, "value": 0.4},
]
LB_GOOD = [1.0, 2.0, 3.0, 4.0]
LB_BAD = [10.0, 20.0, 30.0, 40.0]


def actual_stats(
    mean: float = 0.0,
    rms: float = 1.0,
    frr: float = 0.2,
    lb: list[float] | None = None,
    n_trials: int = 100,
) -> dict:
    return {
        "error_mean_hz": mean,
        "error_rms_hz": rms,
        "acf_lag1": 1.0,
        "acf": copy.deepcopy(GOOD_ACF),
        "lb_stats": list(lb or LB_GOOD),
        "frr": frr,
        "n_trials": n_trials,
    }


def predicted_stats(
    mean: float = 0.0,
    rms: float = 1.0,
    frr: float = 0.2,
    lb: list[float] | None = None,
    acf: list[dict] | None = None,
) -> dict:
    return {
        "error_mean_hz": mean,
        "error_rms_hz": rms,
        "acf": copy.deepcopy(acf or GOOD_ACF),
        "lb_stats": list(lb or LB_GOOD),
        "frr": frr,
    }


def good_models() -> dict:
    return {
        "M0": predicted_stats(mean=5.0, rms=10.0, frr=0.8, lb=LB_BAD, acf=BAD_ACF),
        "M1": predicted_stats(mean=0.1, rms=1.1, frr=0.21),
        "M2": predicted_stats(mean=5.0, rms=10.0, frr=0.8, lb=LB_BAD, acf=BAD_ACF),
        "M3": predicted_stats(mean=5.0, rms=10.0, frr=0.8, lb=LB_BAD, acf=BAD_ACF),
    }


def make_cell(
    cell_id: str,
    geometry_m: float,
    *,
    split: str = "heldout",
    models: dict | None = None,
    units: int = 10,
    resampling_unit: str = "trial",
    fit_scope=None,
    actual: dict | None = None,
) -> dict:
    cell = {
        "cell_id": cell_id,
        "geometry_m": geometry_m,
        "speed_mps": 250.0,
        "snr_db": 20.0,
        "split": split,
        "actual": actual or actual_stats(),
        "predicted": models or good_models(),
        "resampling_unit": resampling_unit,
        "n_independent_units": units,
    }
    if fit_scope is not False:
        cell["fit_scope"] = fit_scope if fit_scope is not None else {
            model: "train" for model in MODELS
        }
    return cell


def make_artifact(
    cells: list[dict],
    *,
    tolerances: dict | None = None,
    reference: dict | None = None,
    repaired_candidates: dict | None = None,
) -> dict:
    document = {
        "experiment": "c2-m2",
        "measurement_model_id": "measurement-model-test-1",
        "development": {"seed_base": 7, "n_trials": 1200},
        "models": list(MODELS),
        "tolerances": dict(tolerances or DEFAULT_TOLERANCES),
        "cells": cells,
        "reference_estimator": reference
        or {"name": "phase-ref", "frr": 0.1, "detection": 0.95, "notes": "test"},
    }
    if repaired_candidates is not None:
        document["repaired_candidates"] = repaired_candidates
    return document


def base_cells() -> list[dict]:
    return [
        make_cell("h150", 150.0, units=10),
        make_cell("h600", 600.0, units=10),
        make_cell("h3000", 3000.0, units=10),
        make_cell("train600", 600.0, split="train", units=50),
    ]


def write_artifact(path: Path, document: dict) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_loader_accepts_contract(tmp_path: Path) -> None:
    path = write_artifact(tmp_path / "artifact.json", make_artifact(base_cells()))
    artifact = load_artifact(path)
    assert artifact.experiment == "c2-m2"
    assert artifact.measurement_model_id == "measurement-model-test-1"
    assert artifact.models == MODELS
    assert len(artifact.heldout_cells) == 3
    assert len(artifact.train_cells) == 1
    assert artifact.sha256


def test_missing_tolerance_rejected(tmp_path: Path) -> None:
    document = make_artifact(base_cells())
    del document["tolerances"]["decision_frr_abs_error_pp"]
    path = write_artifact(tmp_path / "artifact.json", document)
    with pytest.raises(ArtifactError):
        load_artifact(path)


def test_missing_fit_scope_rejected(tmp_path: Path) -> None:
    cells = base_cells()
    cells[0].pop("fit_scope")
    path = write_artifact(tmp_path / "artifact.json", make_artifact(cells))
    with pytest.raises(ArtifactError):
        load_artifact(path)


def test_fit_scope_on_heldout_rejected(tmp_path: Path) -> None:
    cells = base_cells()
    cells[0]["fit_scope"] = {model: "train" for model in MODELS}
    cells[0]["fit_scope"]["M1"] = ["h150"]
    path = write_artifact(tmp_path / "artifact.json", make_artifact(cells))
    with pytest.raises(ArtifactError):
        load_artifact(path)


def test_fit_scope_same_heldout_label_rejected(tmp_path: Path) -> None:
    cells = base_cells()
    cells[0]["fit_scope"] = {model: "heldout" for model in MODELS}
    path = write_artifact(tmp_path / "artifact.json", make_artifact(cells))
    with pytest.raises(ArtifactError):
        load_artifact(path)


def test_no_heldout_cells_rejected(tmp_path: Path) -> None:
    cells = [make_cell("train1", 150.0, split="train")]
    path = write_artifact(tmp_path / "artifact.json", make_artifact(cells))
    with pytest.raises(ArtifactError):
        load_artifact(path)


def test_duplicate_cells_and_nonfinite_rejected(tmp_path: Path) -> None:
    cells = base_cells()
    cells.append(copy.deepcopy(cells[0]))
    path = write_artifact(tmp_path / "artifact.json", make_artifact(cells))
    with pytest.raises(ArtifactError):
        load_artifact(path)

    cells = base_cells()
    cells[0]["predicted"]["M1"]["frr"] = float("nan")
    path = write_artifact(tmp_path / "artifact.json", make_artifact(cells))
    with pytest.raises(ArtifactError):
        load_artifact(path)


def test_clean_passing_model_and_geometry_choice() -> None:
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2m2-clean.json"), make_artifact(base_cells()))
    )
    document = evaluate(artifact, bootstrap_replicates=100)
    assert document["models"]["M1"]["passes_all_heldout"] is True
    assert document["models"]["M0"]["passes_all_heldout"] is False
    assert document["generalisation"]["passing_models"] == ["M1"]
    assert document["generalisation"]["negative_result_holds"] is False
    for geometry in document["generalisation"]["per_geometry"]:
        if geometry["models"]["M1"]["n_cells"]:
            assert geometry["chosen_model"] == "M1"


def test_good_fit_bad_heldout_prediction_fails() -> None:
    cells = base_cells()
    bad = good_models()
    bad["M2"] = predicted_stats(mean=5.0, rms=5.0, frr=0.8, lb=LB_BAD)
    cells[2]["predicted"] = bad
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2m2-badheldout.json"), make_artifact(cells))
    )
    document = evaluate(artifact, bootstrap_replicates=100)
    result = document["models"]["M2"]
    assert result["passes_all_heldout"] is False
    failed_cells = {failure["cell_id"] for failure in result["failed_checks"]}
    assert "h3000" in failed_cells
    assert document["generalisation"]["passing_models"] != ["M2"]


def test_global_p99_gaming_fails_per_geometry() -> None:
    cells = base_cells()
    gaming = good_models()
    # M2 matches only the smallest geometry; the other two are decisively wrong.
    gaming["M2"] = predicted_stats(mean=0.1, rms=1.1, frr=0.21)
    cells[0]["predicted"] = copy.deepcopy(gaming)
    cells[1]["predicted"] = gaming
    cells[1]["predicted"]["M2"] = predicted_stats(
        mean=5.0, rms=5.0, frr=0.8, lb=LB_BAD
    )
    cells[2]["predicted"] = copy.deepcopy(cells[1]["predicted"])
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2m2-gaming.json"), make_artifact(cells))
    )
    document = evaluate(artifact, bootstrap_replicates=100)
    result = document["models"]["M2"]
    assert result["passes_all_heldout"] is False
    assert "[0,200)" not in result["failed_geometry_bins"]
    assert "[400,800)" in result["failed_geometry_bins"]
    assert "[1600,3200)" in result["failed_geometry_bins"]
    assert document["generalisation"]["negative_result_holds"] is False


def test_formulas_are_hand_checkable() -> None:
    assert ks_statistic([0.0, 1.0], [2.0, 3.0]) == pytest.approx(1.0)
    assert ks_statistic([1.0, 2.0], [1.0, 2.0]) == pytest.approx(0.0)
    interval = wilson_interval(0.2, 100)
    assert interval is not None
    assert 0.1 < interval[0] < 0.2
    assert 0.2 < interval[1] < 0.4

    cell = make_cell("formula", 600.0)
    cell["actual"] = actual_stats(mean=0.0, rms=1.0, frr=0.2)
    cell["predicted"]["M1"] = predicted_stats(mean=1.5, rms=2.5, frr=0.31)
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2m2-formula.json"), make_artifact([cell]))
    )
    result = evaluate(artifact, bootstrap_replicates=50)
    metrics = result["models"]["M1"]["cells"][0]
    assert metrics["error_mean_abs_hz"] == pytest.approx(1.5)
    assert metrics["error_rms_abs_hz"] == pytest.approx(1.5)
    assert metrics["decision_frr_abs_error_pp"] == pytest.approx(11.0)
    assert metrics["distribution_ks"] == pytest.approx(0.0)
    assert metrics["actual_frr_wilson_95"] == pytest.approx(list(interval))


def test_intervals_use_units_not_frames() -> None:
    cells = base_cells()
    cells[0]["n_independent_units"] = 100
    cells[1]["n_independent_units"] = 2
    cells[2]["n_independent_units"] = 3
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2m2-units.json"), make_artifact(cells))
    )
    document = evaluate(artifact, bootstrap_replicates=200)
    result = document["models"]["M1"]
    assert document["validation"]["n_independent_units"] == 105
    assert result["intervals"]["n_independent_units"] == 105
    assert result["intervals"]["frame_resampling"] is False
    assert result["intervals"]["n_clusters"] == 3
    interval = bootstrap_interval([1.0, 3.0], [100.0, 2.0], seed=1, replicates=50)
    assert interval["n_independent_units"] == 102
    assert interval["point"] == pytest.approx((100.0 + 6.0) / 102.0)
    assert "frame_resampling" not in interval  # function-level interval has no such field


def test_repeated_match_count_is_not_a_distribution() -> None:
    # Actual ACF/LB differ from predicted even when FRR matches; M1 must not pass.
    cells = base_cells()
    for cell in cells:
        cell["predicted"]["M1"] = predicted_stats(
            mean=0.1, rms=1.1, frr=0.21, lb=LB_BAD, acf=BAD_ACF
        )
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2m2-distribution.json"), make_artifact(cells))
    )
    document = evaluate(artifact, bootstrap_replicates=50)
    assert document["models"]["M1"]["passes_all_heldout"] is False
    assert any(
        failure["tolerance"] in {"distribution_ks_max", "acf_max_abs"}
        for failure in document["models"]["M1"]["failed_checks"]
    )


def test_negative_result_when_no_model_passes() -> None:
    cells = base_cells()
    for cell in cells:
        cell["predicted"] = {
            model: predicted_stats(mean=5.0, rms=10.0, frr=0.8, lb=LB_BAD, acf=BAD_ACF)
            for model in MODELS
        }
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2m2-negative.json"), make_artifact(cells))
    )
    document = evaluate(artifact, bootstrap_replicates=50)
    assert document["generalisation"]["passing_models"] == []
    assert document["generalisation"]["negative_result_holds"] is True
    assert "No model meets" in document["generalisation"]["statement"]


def test_reference_section_without_repaired_candidates() -> None:
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2m2-reference.json"), make_artifact(base_cells()))
    )
    document = evaluate(artifact, bootstrap_replicates=50)
    reference = document["reference_estimator"]
    assert reference["name"] == "phase-ref"
    assert reference["frr"] == pytest.approx(0.1)
    assert reference["detection"] == pytest.approx(0.95)
    assert reference["repaired_candidate_comparison"]["available"] is False
    assert "no repaired-candidate" in reference["repaired_candidate_comparison"]["reason"]
    assert reference["selection"] == "none"


def test_reference_section_with_optional_repaired_candidates() -> None:
    document = make_artifact(
        base_cells(),
        repaired_candidates={
            "B0": {"frr": 0.2, "detection": 0.9},
            "B1": {"frr": 0.15, "detection": 0.92},
        },
    )
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2m2-reference-candidates.json"), document)
    )
    result = evaluate(artifact, bootstrap_replicates=50)
    comparison = result["reference_estimator"]["repaired_candidate_comparison"]
    assert comparison["available"] is True
    assert comparison["reference_beats_all_descriptively"] is True
    assert result["reference_estimator"]["selection"] == "none"


def test_report_deterministic_and_sections() -> None:
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2m2-deterministic.json"), make_artifact(base_cells()))
    )
    first = evaluate(artifact, bootstrap_replicates=100)
    second = evaluate(artifact, bootstrap_replicates=100)
    assert report_json(first) == report_json(second)
    assert report_markdown(first) == report_markdown(second)
    markdown = report_markdown(first)
    for heading in (
        "Per-model held-out calibration",
        "Held-out cell details",
        "Generalisation by geometry continuum",
        "Deterministic cluster intervals",
        "Fit-scope audit",
        "Reference estimator",
        "Negative-result statement",
        "Contract gaps",
        "Limitations",
    ):
        assert heading in markdown


def test_cli_roundtrip_and_bad_artifact(tmp_path: Path) -> None:
    path = write_artifact(tmp_path / "artifact.json", make_artifact(base_cells()))
    out = tmp_path / "report.json"
    markdown = tmp_path / "report.md"
    assert (
        main(
            [
                "--artifact",
                str(path),
                "--bootstrap-replicates",
                "100",
                "--out",
                str(out),
                "--markdown",
                str(markdown),
            ]
        )
        == 0
    )
    document = json.loads(out.read_text())
    assert document["schema_version"] == "1.0.0"
    assert document["generalisation"]["passing_models"] == ["M1"]
    assert "Generalisation by geometry continuum" in markdown.read_text()

    bad = tmp_path / "bad.json"
    bad.write_text('{"experiment":"c2-m2"}', encoding="utf-8")
    assert (
        main(
            [
                "--artifact",
                str(bad),
                "--out",
                str(tmp_path / "bad-report.json"),
                "--markdown",
                str(tmp_path / "bad-report.md"),
            ]
        )
        == 2
    )
