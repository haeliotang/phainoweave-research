"""Tests for the cross-platform artifact comparison tooling (PR-4)."""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import math
from pathlib import Path

import pytest

from phaino_verify import (
    Artifact,
    ArtifactError,
    Protocol,
    ProtocolError,
    compare_artifacts,
    load_artifact,
    load_protocol,
)
from phaino_verify.compare import main

REPO_ROOT = Path(__file__).resolve().parents[2]


def protocol_document(**overrides: object) -> dict:
    document = {
        "protocol_id": "test-e0-cross-platform",
        "version": 1,
        "description": "Test protocol for the comparison engine.",
        "tolerance_status": "example_only",
        "tolerance_note": "Placeholder tolerances; never choose tolerances to pass.",
        "levels": {
            "r0_execution": "Both artifacts parse and contain every trial exactly once.",
            "r1_numerical_equivalence": "Exact fields match and numeric fields are within tolerance.",
            "r2_bitwise_identity": "Canonical bytes after ignored-field removal are identical.",
        },
        "exact_fields": [
            "experiment",
            "config.version",
            "conditions[].condition",
            "conditions[].n",
            "trials[].condition",
            "trials[].trial",
            "trials[].seed",
            "trials[].success",
            "trials[].b1.within_tol.f0",
        ],
        "numeric_fields": [
            {"path": "trials[].value", "abs_tol": 1e-6, "rel_tol": 0.0},
            {"path": "trials[].relative", "abs_tol": 0.0, "rel_tol": 1e-9},
            {"path": "conditions[].mean", "abs_tol": 1e-6, "rel_tol": 0.0},
        ],
        "ignored_fields": [
            "generated_at_utc",
            "elapsed_s",
            "config.jobs",
            "environment.python",
        ],
        "structural_rules": {
            "required_keys": ["experiment", "config", "environment", "conditions", "trials"],
            "trials_key": "trials",
            "conditions_key": "conditions",
            "trial_key": ["condition", "trial"],
            "condition_key": "condition",
            "required_trial_keys": ["condition", "trial", "seed", "success"],
            "same_condition_set": True,
            "same_condition_order": True,
            "exactly_once": True,
            "no_duplicates": True,
            "no_missing": True,
            "no_extra": True,
        },
        "decision_instability": {
            "decision_fields": ["trials[].success"],
            "parameter_scope": "trial",
        },
        "unclassified_field_policy": "exact",
    }
    document.update(overrides)
    return document


def make_protocol(**overrides: object) -> Protocol:
    return Protocol.from_document(protocol_document(**overrides))


def make_document() -> dict:
    return {
        "experiment": "e0-test",
        "generated_at_utc": "2026-11-04T00:00:00Z",
        "elapsed_s": 1.0,
        "config": {"version": "1", "jobs": 8},
        "environment": {"python": "3.14.0"},
        "conditions": [
            {"condition": "c1", "n": 2, "mean": 1.0},
            {"condition": "c2", "n": 1, "mean": 2.0},
        ],
        "trials": [
            {
                "condition": "c1",
                "trial": 0,
                "seed": 1,
                "value": 1.0,
                "relative": 1.0,
                "success": True,
                "b1": {"within_tol": {"f0": True}},
            },
            {
                "condition": "c1",
                "trial": 1,
                "seed": 2,
                "value": 2.0,
                "relative": 2.0,
                "success": False,
                "b1": {"within_tol": {"f0": True}},
            },
            {
                "condition": "c2",
                "trial": 0,
                "seed": 3,
                "value": 3.0,
                "relative": 3.0,
                "success": True,
                "b1": {"within_tol": {"f0": True}},
            },
        ],
    }


def artifact(document: dict | None = None, raw_sha256: str = "0" * 64) -> Artifact:
    return Artifact(
        document=document if document is not None else make_document(),
        raw_sha256=raw_sha256,
        decoded_sha256=raw_sha256,
    )


def compare(
    reference: dict | None = None,
    candidate: dict | None = None,
    protocol: Protocol | None = None,
):
    return compare_artifacts(
        artifact(reference),
        artifact(candidate),
        protocol or make_protocol(),
    )


def test_exact_copy_is_exact() -> None:
    report = compare()
    assert report.classification == "exact"
    assert report.levels == {
        "r0_execution": True,
        "r1_numerical_equivalence": True,
        "r2_bitwise_identity": True,
    }
    assert report.violations == []


def test_within_tolerance_float_is_numerically_equivalent() -> None:
    candidate = make_document()
    candidate["trials"][0]["value"] = 1.0 + 2e-7
    report = compare(candidate=candidate)
    assert report.classification == "numerically_equivalent"
    assert report.levels["r1_numerical_equivalence"] is True
    assert report.levels["r2_bitwise_identity"] is False
    assert report.violations == []
    stats = {entry["field"]: entry for entry in report.per_field_stats}
    assert stats["trials[].value"]["max_abs"] > 0.0


def test_out_of_tolerance_float_is_mismatch_with_location() -> None:
    candidate = make_document()
    candidate["trials"][0]["value"] = 1.5
    report = compare(candidate=candidate)
    assert report.classification == "mismatch"
    assert report.levels["r1_numerical_equivalence"] is False
    violation = report.numeric_violations[0]
    assert violation["field"] == "trials[].value"
    assert "condition=c1" in violation["location"]
    assert "trial=0" in violation["location"]
    assert "field=value" in violation["location"]
    stats = {entry["field"]: entry for entry in report.per_field_stats}
    assert stats["trials[].value"]["violations"] == 1


def test_relative_tolerance_is_absolute_plus_relative() -> None:
    candidate = make_document()
    candidate["trials"][0]["relative"] = 1.0 + 5e-10
    report = compare(candidate=candidate)
    assert report.levels["r1_numerical_equivalence"] is True

    candidate["trials"][0]["relative"] = 1.0 + 5e-9
    report = compare(candidate=candidate)
    assert report.levels["r1_numerical_equivalence"] is False


def test_exact_int_change_is_mismatch() -> None:
    candidate = make_document()
    candidate["config"]["version"] = "2"
    report = compare(candidate=candidate)
    assert report.classification == "mismatch"
    assert any(violation["path"] == "config.version" for violation in report.exact_violations)


def test_decision_change_is_mismatch_and_instability() -> None:
    candidate = make_document()
    candidate["trials"][0]["success"] = False
    report = compare(candidate=candidate)
    assert report.classification == "mismatch"
    assert len(report.decision_instability) == 1
    finding = report.decision_instability[0]
    assert finding["decision_field"] == "trials[].success"
    assert finding["reference"] is True
    assert finding["candidate"] is False
    assert "condition=c1" in finding["location"]


def test_nan_or_infinity_is_unknown() -> None:
    for bad in (math.nan, math.inf, -math.inf):
        document = make_document()
        document["trials"][0]["value"] = bad
        report = compare_artifacts(
            artifact(document, raw_sha256="a" * 64),
            artifact(make_document(), raw_sha256="b" * 64),
            make_protocol(),
        )
        assert report.classification == "unknown"
        assert any("non-finite" in reason for reason in report.reasons)


def test_missing_trial_is_unknown() -> None:
    candidate = make_document()
    del candidate["trials"][2]
    report = compare(candidate=candidate)
    assert report.classification == "unknown"
    assert report.levels["r0_execution"] is False
    assert any("missing trials" in reason for reason in report.reasons)


def test_extra_trial_is_unknown() -> None:
    candidate = make_document()
    candidate["trials"].append(
        {
            "condition": "c2",
            "trial": 1,
            "seed": 4,
            "value": 4.0,
            "relative": 4.0,
            "success": True,
            "b1": {"within_tol": {"f0": True}},
        }
    )
    report = compare(candidate=candidate)
    assert report.classification == "unknown"
    assert any("not present" in reason for reason in report.reasons)


def test_duplicate_trial_is_unknown() -> None:
    candidate = make_document()
    candidate["trials"].append(copy.deepcopy(candidate["trials"][0]))
    report = compare(candidate=candidate)
    assert report.classification == "unknown"
    assert any("more than once" in reason for reason in report.reasons)


def test_condition_order_change_is_documented_unknown() -> None:
    candidate = make_document()
    candidate["conditions"].reverse()
    report = compare(candidate=candidate)
    assert report.classification == "unknown"
    assert any("condition order" in reason for reason in report.reasons)


def test_ignored_metadata_change_stays_exact() -> None:
    candidate = make_document()
    candidate["generated_at_utc"] = "2030-01-01T00:00:00Z"
    candidate["elapsed_s"] = 999.0
    candidate["config"]["jobs"] = 2
    candidate["environment"]["python"] = "3.12.0"
    report = compare(candidate=candidate)
    assert report.classification == "exact"
    assert set(report.ignored_fields_found) == {
        "config.jobs",
        "elapsed_s",
        "environment.python",
        "generated_at_utc",
    }


def test_gzip_artifact_is_loaded_and_compared(tmp_path: Path) -> None:
    payload = json.dumps(make_document()).encode("utf-8")
    path = tmp_path / "artifact.json.gz"
    path.write_bytes(gzip.compress(payload))
    loaded = load_artifact(path)
    assert loaded.compressed is True
    report = compare_artifacts(loaded, loaded, make_protocol())
    assert report.classification == "exact"


def test_report_bytes_are_deterministic() -> None:
    first = compare()
    second = compare()
    assert first.to_json() == second.to_json()
    assert hashlib.sha256(first.to_json().encode()).hexdigest() == hashlib.sha256(
        second.to_json().encode()
    ).hexdigest()


def test_compare_does_not_mutate_inputs() -> None:
    reference = make_document()
    candidate = make_document()
    candidate["trials"][0]["value"] = 1.5
    reference_before = copy.deepcopy(reference)
    candidate_before = copy.deepcopy(candidate)
    compare(reference=reference, candidate=candidate)
    assert reference == reference_before
    assert candidate == candidate_before


def test_protocol_validation_rejects_bad_documents() -> None:
    with pytest.raises(ProtocolError):
        Protocol.from_document({**protocol_document(), "unknown_key": 1})

    missing = protocol_document()
    del missing["numeric_fields"]
    with pytest.raises(ProtocolError):
        Protocol.from_document(missing)

    bad_tolerance = protocol_document(
        numeric_fields=[{"path": "trials[].value", "abs_tol": math.nan, "rel_tol": 0.0}]
    )
    with pytest.raises(ProtocolError):
        Protocol.from_document(bad_tolerance)

    bad_path = protocol_document(exact_fields=["trials[].not..valid"])
    with pytest.raises(ProtocolError):
        Protocol.from_document(bad_path)

    bad_policy = protocol_document(unclassified_field_policy="guess")
    with pytest.raises(ProtocolError):
        Protocol.from_document(bad_policy)


def test_example_protocol_file_loads() -> None:
    protocol = load_protocol(REPO_ROOT / "protocols" / "e0-cross-platform.example.json")
    assert protocol.tolerance_status == "example_only"
    assert protocol.numeric_fields
    assert any("trials[].b1.params.*" == field.path for field in protocol.numeric_fields)


def write_artifacts(
    tmp_path: Path, reference: dict, candidate: dict, protocol: dict
) -> tuple[Path, Path, Path]:
    reference_path = tmp_path / "reference.json"
    candidate_path = tmp_path / "candidate.json"
    protocol_path = tmp_path / "protocol.json"
    reference_path.write_text(json.dumps(reference), encoding="utf-8")
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
    protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
    return reference_path, candidate_path, protocol_path


def test_cli_exit_codes(tmp_path: Path) -> None:
    reference = make_document()
    within = copy.deepcopy(reference)
    within["trials"][0]["value"] = 1.0 + 2e-7
    out_of_tolerance = copy.deepcopy(reference)
    out_of_tolerance["trials"][0]["value"] = 1.5
    missing = copy.deepcopy(reference)
    del missing["trials"][2]

    ref_path, _, protocol_path = write_artifacts(
        tmp_path, reference, reference, protocol_document()
    )
    exact_report = tmp_path / "exact.json"
    assert (
        main(
            [
                str(ref_path),
                str(ref_path),
                "--protocol",
                str(protocol_path),
                "--report",
                str(exact_report),
            ]
        )
        == 0
    )
    assert json.loads(exact_report.read_text())["classification"] == "exact"

    within_path = tmp_path / "within.json"
    within_path.write_text(json.dumps(within), encoding="utf-8")
    assert (
        main(
            [
                str(ref_path),
                str(within_path),
                "--protocol",
                str(protocol_path),
                "--report",
                str(tmp_path / "within-report.json"),
                "--require",
                "R1",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                str(ref_path),
                str(within_path),
                "--protocol",
                str(protocol_path),
                "--report",
                str(tmp_path / "within-r2-report.json"),
                "--require",
                "R2",
            ]
        )
        == 1
    )

    outside_path = tmp_path / "outside.json"
    outside_path.write_text(json.dumps(out_of_tolerance), encoding="utf-8")
    assert (
        main(
            [
                str(ref_path),
                str(outside_path),
                "--protocol",
                str(protocol_path),
                "--report",
                str(tmp_path / "outside-report.json"),
            ]
        )
        == 1
    )

    missing_path = tmp_path / "missing.json"
    missing_path.write_text(json.dumps(missing), encoding="utf-8")
    assert (
        main(
            [
                str(ref_path),
                str(missing_path),
                "--protocol",
                str(protocol_path),
                "--report",
                str(tmp_path / "missing-report.json"),
            ]
        )
        == 2
    )

    bad_protocol = protocol_document()
    bad_protocol["unknown_key"] = 1
    bad_protocol_path = tmp_path / "bad-protocol.json"
    bad_protocol_path.write_text(json.dumps(bad_protocol), encoding="utf-8")
    assert (
        main(
            [
                str(ref_path),
                str(ref_path),
                "--protocol",
                str(bad_protocol_path),
                "--report",
                str(tmp_path / "bad-protocol-report.json"),
            ]
        )
        == 3
    )


def test_cli_malformed_artifact_is_unknown_and_written(tmp_path: Path) -> None:
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(protocol_document()), encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    report_path = tmp_path / "report.json"
    assert (
        main(
            [
                str(bad),
                str(bad),
                "--protocol",
                str(protocol_path),
                "--report",
                str(report_path),
            ]
        )
        == 2
    )
    report = json.loads(report_path.read_text())
    assert report["classification"] == "unknown"
    assert report["reasons"]


def test_cli_reports_are_byte_deterministic(tmp_path: Path) -> None:
    reference = make_document()
    ref_path, cand_path, protocol_path = write_artifacts(
        tmp_path, reference, reference, protocol_document()
    )
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    arguments = [str(ref_path), str(cand_path), "--protocol", str(protocol_path)]
    assert main([*arguments, "--report", str(first)]) == 0
    assert main([*arguments, "--report", str(second)]) == 0
    assert first.read_bytes() == second.read_bytes()


def test_raw_sha256_is_always_reported(tmp_path: Path) -> None:
    reference = make_document()
    ref_path, _, protocol_path = write_artifacts(
        tmp_path, reference, reference, protocol_document()
    )
    report = compare_artifacts(
        load_artifact(ref_path), load_artifact(ref_path), load_protocol(protocol_path)
    )
    expected = hashlib.sha256(ref_path.read_bytes()).hexdigest()
    assert report.reference["raw_sha256"] == expected
    assert report.candidate["raw_sha256"] == expected
    assert report.protocol["sha256"]


def test_artifact_loader_rejects_duplicate_keys_and_nonfinite(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"a":1,"a":2}', encoding="utf-8")
    with pytest.raises(ArtifactError):
        load_artifact(duplicate)

    nonfinite = tmp_path / "nan.json"
    nonfinite.write_text('{"a":NaN}', encoding="utf-8")
    with pytest.raises(ArtifactError):
        load_artifact(nonfinite)
