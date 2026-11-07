"""Tests for the independent adequacy evaluation harness.

All fixtures are synthetic artifact JSON. The harness never imports the adequacy method and
never reads acoustics code.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from phaino_adequacy_eval import (
    AdequacyArtifactError,
    CurvePoint,
    build_report_document,
    correctness,
    embedded_old_decisions,
    interpolate_risk,
    load_adequacy_artifact,
    report_json,
    report_markdown,
    validate_adequacy_artifact,
)
from phaino_adequacy_eval.cli import main
from phaino_adequacy_eval.truth import (
    B_REL_TOL,
    F0_REL_TOL,
    T0_ABS_TOL,
    V_REL_TOL,
)

TESTS = {
    "standardized_residuals": {"statistic": 0.1, "p_value": 0.9},
    "autocorrelation": {"statistic": 0.05, "p_value": 0.8},
    "time_structure": {"statistic": 0.01},
    "block_prediction": {"statistic": 0.02},
    "degeneracy": {"condition_number": 31.0},
}


def make_trial(
    *,
    condition: str = "c1",
    trial: int = 0,
    mechanism: str = "within_tolerance",
    correct: bool = True,
    old_decision: str = "accepted",
    new_decision: str = "supported",
    reason_codes: list[str] | None = None,
    layer: str = "locked",
    old_score: float | None = None,
    new_score: float | None = None,
    conditional_supported: bool | None = None,
    model_adequacy_status: str = "adequate",
    identifiability_status: str = "identifiable",
    optimization_status: str = "converged",
    identifiability_status_old: str = "identifiable",
) -> dict:
    truth = {
        "f0": 500.0,
        "v": 250.0,
        "t0": 20.0,
        "b": 3000.0,
        "c": 343.0,
        "accel": 0.0,
        "clock_scale_ppm": 0.0,
        "clock_offset_s": 0.0,
    }
    params = {"f0": truth["f0"], "v": truth["v"], "t0": truth["t0"], "b": truth["b"]}
    if not correct:
        params["f0"] = truth["f0"] * 1.02
    hardened = {
        "params": params,
        "optimization_status": optimization_status,
        "identifiability_status_old": identifiability_status_old,
        "decision_status_old": old_decision,
    }
    if old_score is not None:
        hardened["score"] = old_score
    adequacy = {
        "model_adequacy_status": model_adequacy_status,
        "identifiability_status": identifiability_status,
        "epistemic_decision": new_decision,
        "reason_codes": list(reason_codes or []),
        "tests": copy.deepcopy(TESTS),
    }
    if new_score is not None:
        adequacy["confidence"] = new_score
    if conditional_supported is not None:
        adequacy["tests"]["degeneracy"]["conditional_claim_supported"] = conditional_supported
    return {
        "condition": condition,
        "trial": trial,
        "seed": 1000 + trial,
        "layer": layer,
        "mechanism": mechanism,
        "evaluation_only": {"scenario": truth},
        "observation": {
            "if_rms_hz": 10.0,
            "sigma_f_hz": 0.5,
            "n_samples": 8000,
            "duration_s": 60.0,
        },
        "hardened": hardened,
        "adequacy": adequacy,
    }


def make_artifact(trials: list[dict], *, layer: str = "locked") -> dict:
    for trial in trials:
        trial["layer"] = layer
    return {
        "experiment": "e0-adequacy",
        "layer": layer,
        "protocol_digest": "test-protocol-digest",
        "config": {"n_conditions": len({trial["condition"] for trial in trials})},
        "environment": {"python": "3.14.0"},
        "trials": trials,
    }


def write_json(path: Path, document: dict) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def evaluate(document: dict, new_rule: str = "epistemic"):
    artifact = validate_adequacy_artifact(document)
    decisions, field = embedded_old_decisions(artifact)
    return build_report_document(
        artifact, decisions, field, "embedded in artifact", new_rule=new_rule
    )


def test_loader_accepts_valid_artifact(tmp_path: Path) -> None:
    path = write_json(tmp_path / "artifact.json", make_artifact([make_trial()]))
    artifact = load_adequacy_artifact(path)
    assert artifact.experiment == "e0-adequacy"
    assert artifact.protocol_digest == "test-protocol-digest"
    assert len(artifact.trials) == 1


def test_loader_rejects_missing_truth(tmp_path: Path) -> None:
    document = make_artifact([make_trial()])
    del document["trials"][0]["evaluation_only"]["scenario"]["f0"]
    path = write_json(tmp_path / "artifact.json", document)
    with pytest.raises(AdequacyArtifactError):
        load_adequacy_artifact(path)


def test_loader_rejects_duplicate_trials(tmp_path: Path) -> None:
    document = make_artifact([make_trial(), make_trial()])
    path = write_json(tmp_path / "artifact.json", document)
    with pytest.raises(AdequacyArtifactError):
        load_adequacy_artifact(path)


def test_loader_rejects_nonfinite_numbers(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    path.write_text('{"experiment":"e0-adequacy","trials":[NaN]}', encoding="utf-8")
    with pytest.raises(AdequacyArtifactError):
        load_adequacy_artifact(path)


def test_truth_uses_frozen_e0_tolerances() -> None:
    trial = make_trial(correct=True)
    assert correctness(trial).correct
    assert F0_REL_TOL == 0.01
    assert V_REL_TOL == 0.02
    assert T0_ABS_TOL == 0.25
    assert B_REL_TOL == 0.05

    boundary = make_trial(correct=True)
    boundary["hardened"]["params"]["f0"] = 500.0 * (1.0 + F0_REL_TOL)
    assert correctness(boundary).correct
    outside = make_trial(correct=True)
    outside["hardened"]["params"]["f0"] = 500.0 * (1.0 + 2.0 * F0_REL_TOL)
    assert not correctness(outside).correct

    t0_boundary = make_trial(correct=True)
    t0_boundary["hardened"]["params"]["t0"] = 20.0 + T0_ABS_TOL
    assert correctness(t0_boundary).correct
    t0_outside = make_trial(correct=True)
    t0_outside["hardened"]["params"]["t0"] = 20.0 + T0_ABS_TOL + 0.01
    assert not correctness(t0_outside).correct

    b_outside = make_trial(correct=True)
    b_outside["hardened"]["params"]["b"] = 3000.0 * (1.0 + 2.0 * B_REL_TOL)
    assert not correctness(b_outside).correct
    v_outside = make_trial(correct=True)
    v_outside["hardened"]["params"]["v"] = 250.0 * (1.0 + 2.0 * V_REL_TOL)
    assert not correctness(v_outside).correct


def test_old_accepts_wrong_is_visible_and_new_rejects_it() -> None:
    wrong = make_trial(trial=1, correct=False, old_decision="accepted", new_decision="rejected")
    report = evaluate(make_artifact([make_trial(), wrong]))
    overall = report["strata"]["overall"]
    assert overall["old"]["accepted"] == 2
    assert overall["old"]["false_accepts"] == 1
    assert overall["old"]["false_accept_rate"] == 0.5
    assert overall["new"]["accepted"] == 1
    assert overall["new"]["false_accepts"] == 0
    assert overall["new"]["false_accept_rate"] == 0.0


def test_new_accepts_correct() -> None:
    report = evaluate(make_artifact([make_trial(correct=True, new_decision="supported")]))
    overall = report["strata"]["overall"]
    assert overall["new"]["accepted"] == 1
    assert overall["new"]["correct_accepted"] == 1
    assert overall["new"]["valid_retention"] == 1.0


def test_new_undetermined_equivalence_beats_wrong_supported() -> None:
    correct_undetermined = make_trial(
        trial=0,
        mechanism="clock_offset",
        correct=True,
        new_decision="undetermined",
    )
    wrong_supported = make_trial(
        trial=1,
        mechanism="clock_offset",
        correct=False,
        new_decision="supported",
    )
    report = evaluate(make_artifact([correct_undetermined, wrong_supported]))
    section = report["observational_equivalence"]
    assert section["n_trials"] == 2
    assert section["correct_undetermined"] == 1
    assert section["wrong_supported"] == 1
    assert section["declaration"]


def test_stratification_by_mechanism_and_condition() -> None:
    trials = [
        make_trial(condition="snr_0", mechanism="within_tolerance", correct=True),
        make_trial(condition="accel", mechanism="acceleration", trial=1, correct=False),
        make_trial(condition="offset", mechanism="clock_offset", trial=2, correct=False),
    ]
    report = evaluate(make_artifact(trials))
    assert set(report["strata"]["by_mechanism"]) == {
        "acceleration",
        "clock_offset",
        "within_tolerance",
    }
    assert set(report["strata"]["by_condition"]) == {"accel", "offset", "snr_0"}
    assert report["strata"]["overall"]["n_trials"] == 3


def test_retention_and_abstention_definitions() -> None:
    trials = [
        make_trial(trial=0, correct=True, old_decision="accepted", new_decision="supported"),
        make_trial(trial=1, correct=True, old_decision="accepted", new_decision="undetermined"),
        make_trial(trial=2, correct=False, old_decision="indeterminate", new_decision="rejected"),
        make_trial(trial=3, correct=False, old_decision="accepted", new_decision="undetermined"),
    ]
    report = evaluate(make_artifact(trials))
    overall = report["strata"]["overall"]
    assert overall["n_correct"] == 2
    assert overall["old"]["accepted"] == 3
    assert overall["old"]["correct_accepted"] == 2
    assert overall["old"]["valid_retention"] == 1.0
    assert overall["old"]["abstention_rate"] == 0.25
    assert overall["new"]["accepted"] == 1
    assert overall["new"]["valid_retention"] == 0.5
    assert overall["new"]["abstention_rate"] == 0.5


def test_reason_nesting_fallback_is_documented() -> None:
    trials = [
        make_trial(trial=0, new_decision="supported", reason_codes=[]),
        make_trial(trial=1, new_decision="supported", reason_codes=["degraded"]),
        make_trial(trial=2, new_decision="supported", reason_codes=["degenerate"]),
        make_trial(trial=3, new_decision="supported", reason_codes=["degraded", "degenerate"]),
    ]
    report = evaluate(make_artifact(trials))
    curve = report["strata"]["overall"]["risk_coverage"]["new"]
    assert curve["basis"] == "status_reason_nesting"
    assert "nested status/reason signatures" in curve["order_definition"]
    assert len(curve["points"]) >= 2


def test_matched_retention_interpolation() -> None:
    first = CurvePoint(
        level=1,
        threshold=None,
        basis="status_reason_nesting",
        accepted=2,
        correct_accepted=1,
        false_accepts=1,
        retention=0.25,
        false_accept_rate=0.5,
        false_accept_interval=(0.1, 0.9),
    )
    second = CurvePoint(
        level=2,
        threshold=None,
        basis="status_reason_nesting",
        accepted=5,
        correct_accepted=3,
        false_accepts=2,
        retention=0.75,
        false_accept_rate=0.4,
        false_accept_interval=(0.2, 0.6),
    )
    interpolated = interpolate_risk([first, second], 0.5)
    assert interpolated is not None
    risk, interval = interpolated
    assert risk == pytest.approx(0.45)
    assert interval == pytest.approx((0.15, 0.75))
    assert interpolate_risk([first, second], 0.95) is None


def test_matched_retention_entries_are_reported() -> None:
    trials = [
        make_trial(
            trial=index,
            correct=index < 2,
            old_decision="accepted",
            new_decision="supported",
            old_score=1.0 - index * 0.1,
            new_score=1.0 - index * 0.1,
        )
        for index in range(4)
    ]
    report = evaluate(make_artifact(trials))
    matched = report["strata"]["overall"]["risk_coverage"]["matched_retention"]
    assert matched
    assert all("retention" in entry for entry in matched)
    assert all("difference_interval" in entry for entry in matched)


def test_report_bytes_are_deterministic(tmp_path: Path) -> None:
    document = make_artifact(
        [
            make_trial(trial=0, correct=True),
            make_trial(trial=1, correct=False, new_decision="rejected"),
            make_trial(trial=2, mechanism="clock_offset", new_decision="undetermined"),
        ]
    )
    first = evaluate(copy.deepcopy(document))
    second = evaluate(copy.deepcopy(document))
    assert report_json(first) == report_json(second)
    assert report_markdown(first) == report_markdown(second)


def test_old_rule_field_fallback_is_reported() -> None:
    report = evaluate(make_artifact([make_trial()]))
    assert report["rules"]["old"]["decision_field"] == "hardened.decision_status_old"
    assert report["rules"]["old"]["definition"] == (
        "hardened decision status == 'accepted'"
    )


def test_external_hardened_decisions_override_embedded(tmp_path: Path) -> None:
    new_document = make_artifact(
        [make_trial(old_decision="rejected", new_decision="supported")]
    )
    new_path = write_json(tmp_path / "new.json", new_document)
    hardened_document = {
        "trials": [
            {"condition": "c1", "trial": 0, "decision_status": "accepted"},
        ]
    }
    hardened_path = write_json(tmp_path / "hardened.json", hardened_document)
    out = tmp_path / "report.json"
    markdown = tmp_path / "report.md"
    code = main(
        [
            "--new",
            str(new_path),
            "--hardened",
            str(hardened_path),
            "--out",
            str(out),
            "--markdown",
            str(markdown),
        ]
    )
    assert code == 0
    report = json.loads(out.read_text())
    assert report["rules"]["old"]["decision_field"] == "decision_status"
    assert report["strata"]["overall"]["old"]["accepted"] == 1
    assert report["strata"]["overall"]["new"]["accepted"] == 1


def test_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    document = make_artifact(
        [
            make_trial(trial=0, correct=True),
            make_trial(trial=1, correct=False, new_decision="rejected"),
        ]
    )
    new_path = write_json(tmp_path / "new.json", document)
    out = tmp_path / "report.json"
    markdown = tmp_path / "report.md"
    assert main(
        ["--new", str(new_path), "--out", str(out), "--markdown", str(markdown)]
    ) == 0
    report = json.loads(out.read_text())
    assert report["artifact"]["n_trials"] == 2
    text = markdown.read_text()
    assert "Per-mechanism decision utility" in text
    assert "Matched valid-retention comparison" in text
    assert "What this harness cannot measure" in text


def test_cli_reports_artifact_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"experiment":"e0-adequacy","trials":[]}', encoding="utf-8")
    out = tmp_path / "report.json"
    markdown = tmp_path / "report.md"
    assert main(["--new", str(bad), "--out", str(out), "--markdown", str(markdown)]) == 2


def test_conditional_rule_accepts_where_epistemic_is_undetermined() -> None:
    document = make_artifact(
        [
            make_trial(
                trial=0,
                correct=True,
                new_decision="undetermined",
                conditional_supported=True,
            ),
            make_trial(
                trial=1,
                correct=False,
                new_decision="undetermined",
                conditional_supported=False,
            ),
        ]
    )
    strict = evaluate(document)
    conditional = evaluate(document, new_rule="conditional")
    assert strict["strata"]["overall"]["new"]["accepted"] == 0
    assert conditional["rules"]["new"]["rule"] == "conditional"
    assert conditional["rules"]["new"]["conditional_claim_field"].endswith(
        "conditional_claim_supported"
    )
    assert conditional["strata"]["overall"]["new"]["accepted"] == 1
    assert conditional["strata"]["overall"]["new"]["correct_accepted"] == 1
    assert conditional["strata"]["overall"]["new"]["status_counts"] == {
        "conditional_supported": 1,
        "conditional_unsupported": 1,
        "unknown": 0,
    }


def test_conditional_rule_missing_field_is_unknown_not_a_crash() -> None:
    document = make_artifact(
        [
            make_trial(trial=0, correct=True, new_decision="undetermined"),
            make_trial(trial=1, correct=False, new_decision="undetermined"),
        ]
    )
    # One trial never had the conditional field; the other has it explicitly null.
    document["trials"][1]["adequacy"]["tests"]["degeneracy"]["conditional_claim_supported"] = None
    report = evaluate(document, new_rule="conditional")
    assert report["rules"]["new"]["missing_conditional_claim_supported"] == 2
    assert report["strata"]["overall"]["new"]["accepted"] == 0
    assert report["strata"]["overall"]["new"]["status_counts"] == {
        "conditional_supported": 0,
        "conditional_unsupported": 0,
        "unknown": 2,
    }
    assert report["rules"]["new"]["conditional_claim_counts"] == {
        "true": 0,
        "false": 0,
        "unknown": 2,
    }


def test_conditional_report_is_deterministic() -> None:
    document = make_artifact(
        [
            make_trial(trial=0, correct=True, conditional_supported=True),
            make_trial(trial=1, correct=False, conditional_supported=False),
            make_trial(
                trial=2,
                mechanism="clock_offset",
                new_decision="undetermined",
                conditional_supported=True,
            ),
        ]
    )
    first = evaluate(copy.deepcopy(document), new_rule="conditional")
    second = evaluate(copy.deepcopy(document), new_rule="conditional")
    assert report_json(first) == report_json(second)
    assert report_markdown(first) == report_markdown(second)


def test_cli_selects_conditional_rule(tmp_path: Path) -> None:
    document = make_artifact(
        [
            make_trial(
                trial=0,
                correct=True,
                new_decision="undetermined",
                conditional_supported=True,
            )
        ]
    )
    new_path = write_json(tmp_path / "new.json", document)
    out = tmp_path / "report.json"
    markdown = tmp_path / "report.md"
    assert main(
        [
            "--new",
            str(new_path),
            "--new-rule",
            "conditional",
            "--out",
            str(out),
            "--markdown",
            str(markdown),
        ]
    ) == 0
    report = json.loads(out.read_text())
    assert report["rules"]["new"]["rule"] == "conditional"
    assert report["strata"]["overall"]["new"]["accepted"] == 1
