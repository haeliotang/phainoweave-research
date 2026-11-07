"""Contract-v2 tests: field classes, identifiability gating, decision margins, R1-N/R1-D.

These fixtures are synthetic and deliberately small; the real-artifact comparison is a
separate demo/CI concern. Every tolerance and margin comes from the test protocol.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from phaino_verify import Artifact, ProtocolV2, compare_artifacts, load_protocol
from phaino_verify.compare import main

REPO_ROOT = Path(__file__).resolve().parents[2]


def protocol_document(**overrides: object) -> dict:
    document = {
        "contract_version": 2,
        "protocol_id": "test-e0-v2",
        "version": 2,
        "description": "Synthetic contract-v2 test protocol.",
        "tolerance_status": "example_only",
        "tolerance_note": "Test-only margins; not a measured protocol.",
        "levels": {
            "r0_execution": "structure",
            "r1_numerical_equivalence": "identifiable numeric equivalence",
            "r1_decision_equivalence": "decidable decisions match",
            "r2_bitwise_identity": "canonical bytes equal",
        },
        "field_classes": {
            "A_discrete_identity": [
                "config.*",
                "experiment",
                "conditions[].condition",
                "conditions[].n",
                "conditions[].success.n",
                "trials[].condition",
                "trials[].trial",
                "trials[].seed",
                "trials[].identifiable",
            ],
            "B_identifiable_numeric": [
                {"path": "trials[].value", "abs_tol": 1e-06, "rel_tol": 0.0},
                {"path": "trials[].param", "abs_tol": 1e-06, "rel_tol": 1e-06},
            ],
            "C_unidentifiable_diagnostic": [
                {"path": "trials[].diagnostic", "semantics": "magnitude_class"},
                {"path": "trials[].stat", "semantics": "magnitude_class"},
                {"path": "trials[].ratio", "semantics": "magnitude_class"},
            ],
            "D_decision": [
                {
                    "name": "converged",
                    "path": "trials[].converged",
                    "kind": "threshold",
                    "statistic": "trials[].stat",
                    "comparison": "lt",
                    "threshold": 1.0,
                    "margin": 0.1,
                    "justification": "test boundary statistic",
                },
                {
                    "name": "success",
                    "path": "trials[].success",
                    "kind": "derived",
                    "dependencies": ["converged"],
                    "justification": "success = converged in the fixture",
                },
                {
                    "name": "accepted",
                    "path": "trials[].accepted",
                    "kind": "derived",
                    "dependencies": ["converged"],
                    "statistic": "trials[].ratio",
                    "comparison": "ge",
                    "threshold": 0.5,
                    "margin": 0.01,
                    "justification": "accepted = converged and ratio >= 0.5",
                },
            ],
        },
        "identifiability": {
            "rule_id": "test-identifiable",
            "description": "Fixture declares identifiability directly.",
            "all_of": [{"field": "identifiable", "check": "true"}],
        },
        "rate_checks": [
            {
                "path": "conditions[].success.rate",
                "material_abs_change": 0.0105,
                "justification": "one-count window",
            },
            {
                "path": "conditions[].success.k",
                "material_abs_change": 1.0,
                "justification": "one decision count",
            },
        ],
        "ignored_fields": ["generated_at_utc", "elapsed_s", "environment", "records_sha256"],
        "structural_rules": {
            "required_keys": ["experiment", "config", "environment", "conditions", "trials"],
            "trials_key": "trials",
            "conditions_key": "conditions",
            "trial_key": ["condition", "trial"],
            "condition_key": "condition",
            "required_trial_keys": [
                "condition",
                "trial",
                "seed",
                "value",
                "param",
                "identifiable",
                "stat",
                "converged",
                "success",
                "accepted",
                "ratio",
                "diagnostic",
            ],
            "same_condition_set": True,
            "same_condition_order": True,
            "exactly_once": True,
            "no_duplicates": True,
            "no_missing": True,
            "no_extra": True,
        },
        "unclassified_field_policy": "exact",
    }
    document.update(overrides)
    return document


def make_protocol(**overrides: object) -> ProtocolV2:
    return ProtocolV2.from_document(protocol_document(**overrides))


def make_document() -> dict:
    return {
        "experiment": "e0-v2-fixture",
        "generated_at_utc": "2026-11-05T00:00:00Z",
        "elapsed_s": 0.1,
        "config": {"version": "1"},
        "environment": {"python": "3.14.0"},
        "conditions": [
            {
                "condition": "c1",
                "n": 100,
                "success": {"k": 100, "n": 100, "rate": 1.0},
            }
        ],
        "trials": [
            {
                "condition": "c1",
                "trial": 0,
                "seed": 1,
                "value": 1.0,
                "param": 1.0,
                "identifiable": True,
                "stat": 0.5,
                "converged": True,
                "success": True,
                "accepted": True,
                "ratio": 0.9,
                "diagnostic": 1.0,
            },
            {
                "condition": "c1",
                "trial": 1,
                "seed": 2,
                "value": 2.0,
                "param": 2.0,
                "identifiable": True,
                "stat": 0.5,
                "converged": True,
                "success": True,
                "accepted": True,
                "ratio": 0.9,
                "diagnostic": 2.0,
            },
        ],
    }


def artifact(document: dict | None = None) -> Artifact:
    return Artifact(
        document=copy.deepcopy(document if document is not None else make_document()),
        raw_sha256="0" * 64,
        decoded_sha256="0" * 64,
    )


def compare(reference: dict | None = None, candidate: dict | None = None):
    return compare_artifacts(
        artifact(reference),
        artifact(candidate),
        make_protocol(),
    )


def test_exact_copy_is_r2() -> None:
    report = compare()
    assert report.contract_version == 2
    assert report.classification == "exact"
    assert report.r1_n is True
    assert report.r1_d is True
    assert report.reproduction_level == "R2"
    assert report.levels == {
        "r0_execution": True,
        "r1_numerical_equivalence": True,
        "r1_decision_equivalence": True,
        "r2_bitwise_identity": True,
    }


def test_decision_inside_margin_is_indeterminate_on_both_sides() -> None:
    candidate = make_document()
    candidate["trials"][0]["stat"] = 0.95
    candidate["trials"][0]["converged"] = True
    reference = make_document()
    reference["trials"][0]["stat"] = 1.05
    report = compare(reference=reference, candidate=candidate)
    converged = [
        entry for entry in report.decision_changes if entry["decision"] == "converged"
    ]
    assert len(converged) == 1
    assert converged[0]["status"] == "indeterminate"
    assert converged[0]["reference_raw"] is True
    assert converged[0]["reference_statistic"] == 1.05
    assert report.r1_d is True


def test_decision_outside_margin_must_match() -> None:
    reference = make_document()
    candidate = make_document()
    reference["trials"][0]["stat"] = 0.5
    candidate["trials"][0]["stat"] = 1.5
    candidate["trials"][0]["converged"] = False
    report = compare(reference=reference, candidate=candidate)
    converged = [
        entry for entry in report.decision_changes if entry["decision"] == "converged"
    ]
    assert converged
    assert converged[0]["status"] == "rejected"
    assert report.r1_d is False
    assert report.classification == "mismatch"


def test_trial_57_shape_masks_decisions_but_never_claims_r2() -> None:
    reference = make_document()
    candidate = make_document()
    reference["trials"][0].update(
        {"stat": 0.95, "converged": True, "success": True, "accepted": True}
    )
    candidate["trials"][0].update(
        {
            "stat": 1.05,
            "converged": False,
            "success": False,
            "accepted": False,
            "value": 1.0 + 1e-9,
            "param": 1.0 + 1e-9,
        }
    )
    candidate["conditions"][0]["success"] = {"k": 99, "n": 100, "rate": 0.99}
    report = compare(reference=reference, candidate=candidate)
    assert report.r1_n is True
    assert report.r1_d is True
    assert report.reproduction_level == "R1-N+R1-D"
    assert report.classification == "numerically_equivalent"
    assert report.reproduction_level != "R2"
    instability = report.decision_instability
    assert {entry["decision"] for entry in instability} == {
        "converged",
        "success",
        "accepted",
    }
    for entry in instability:
        assert entry["status"] == "indeterminate"
        assert entry["reference_raw"] is True
        assert entry["candidate_raw"] is False


def test_unidentifiable_numeric_difference_is_not_r1_n_failure() -> None:
    reference = make_document()
    candidate = make_document()
    reference["trials"] = [reference["trials"][0]]
    candidate["trials"] = [candidate["trials"][0]]
    reference["trials"][0]["identifiable"] = False
    candidate["trials"][0]["identifiable"] = False
    candidate["trials"][0]["param"] = 1.3
    report = compare(reference=reference, candidate=candidate)
    assert report.classification == "unknown"
    assert report.r1_n is None
    assert report.reproduction_level == "R0 only"
    assert report.numeric_violations == []
    param_stats = [
        entry for entry in report.per_field_stats if entry["field"] == "trials[].param"
    ]
    assert param_stats[0]["not_applicable_compared"] > 0
    assert not param_stats[0]["applicable_compared"]
    trial_status = report.identifiability[0]
    assert trial_status["identifiable"] is False
    assert trial_status["r1_n_status"] == "not_applicable"


def test_identifiable_numeric_regression_fails_r1_n() -> None:
    candidate = make_document()
    candidate["trials"][0]["param"] = 1.01
    report = compare(candidate=candidate)
    assert report.classification == "mismatch"
    assert report.r1_n is False
    assert report.r1_d is True
    violation = report.numeric_violations[0]
    assert violation["class"] == "B"
    assert violation["field"] == "trials[].param"
    assert "trial=0" in violation["location"]


def test_material_rate_change_fails_r1_d_even_when_decision_is_masked() -> None:
    reference = make_document()
    candidate = make_document()
    reference["trials"][0]["stat"] = 0.95
    candidate["trials"][0]["stat"] = 1.05
    candidate["trials"][0]["converged"] = False
    candidate["conditions"][0]["success"] = {"k": 99, "n": 100, "rate": 0.99}
    report = compare(
        reference=reference,
        candidate=candidate,
    ).to_document()
    # Re-run with a tight material threshold to make the one-count change material.
    tight_protocol = make_protocol(
        rate_checks=[
            {
                "path": "conditions[].success.rate",
                "material_abs_change": 0.001,
                "justification": "test material threshold",
            },
            {
                "path": "conditions[].success.k",
                "material_abs_change": 0.5,
                "justification": "test material count threshold",
            },
        ]
    )
    tight = compare_artifacts(
        artifact(reference), artifact(candidate), tight_protocol
    )
    assert tight.classification == "mismatch"
    assert tight.r1_d is False
    assert tight.decision_instability
    material = [entry for entry in tight.rate_changes if entry["material"]]
    assert material
    assert "conditions[].success.rate" in {entry["field"] for entry in material}
    assert report["classification"] in {"numerically_equivalent", "mismatch"}


def test_c_diagnostics_never_fail_r1_n() -> None:
    candidate = make_document()
    candidate["trials"][0]["diagnostic"] = 300.0
    report = compare(candidate=candidate)
    assert report.violations == []
    assert report.r1_n is True
    assert report.diagnostic_differences
    assert report.classification == "numerically_equivalent"


def test_a_class_change_is_mismatch() -> None:
    candidate = make_document()
    candidate["trials"][0]["seed"] = 999
    report = compare(candidate=candidate)
    assert report.classification == "mismatch"
    assert report.r1_n is False
    assert any(entry["path"] == "trials[0].seed" for entry in report.exact_violations)


def test_v2_protocol_is_strict() -> None:
    from phaino_verify import ProtocolError

    with_exception = False
    try:
        ProtocolV2.from_document({**protocol_document(), "contract_version": 1})
    except ProtocolError:
        with_exception = True
    assert with_exception

    broken = protocol_document()
    broken["field_classes"]["D_decision"][0]["margin"] = -1.0
    try:
        ProtocolV2.from_document(broken)
    except ProtocolError:
        pass
    else:
        raise AssertionError("negative decision margin must be rejected")


def test_real_v2_protocol_file_loads() -> None:
    protocol = load_protocol(REPO_ROOT / "protocols" / "e0-cross-platform.v2.json")
    assert isinstance(protocol, ProtocolV2)
    assert protocol.tolerance_status == "measured_draft_not_frozen"
    assert protocol.identifiability.rule_id == "e0-b1-identifiable-v1"
    assert len(protocol.decisions) == 13
    assert len(protocol.rate_checks) == 8


def write_v2(tmp_path: Path, reference: dict, candidate: dict) -> tuple[Path, Path, Path]:
    reference_path = tmp_path / "reference.json"
    candidate_path = tmp_path / "candidate.json"
    protocol_path = tmp_path / "protocol.json"
    reference_path.write_text(json.dumps(reference), encoding="utf-8")
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
    protocol_path.write_text(json.dumps(protocol_document()), encoding="utf-8")
    return reference_path, candidate_path, protocol_path


def test_v2_cli_requires_split_targets(tmp_path: Path) -> None:
    reference = make_document()
    candidate = make_document()
    candidate["trials"][0]["param"] = 1.01
    reference_path, candidate_path, protocol_path = write_v2(
        tmp_path, reference, candidate
    )
    report_path = tmp_path / "report.json"
    arguments = [
        str(reference_path),
        str(candidate_path),
        "--protocol",
        str(protocol_path),
        "--report",
        str(report_path),
    ]
    assert main([*arguments, "--require", "R1-N"]) == 1
    assert main([*arguments, "--require", "R1-D"]) == 0
    assert main([*arguments, "--require", "both"]) == 1
    assert main([*arguments, "--require", "R1"]) == 1
    written = json.loads(report_path.read_text())
    assert written["r1_n"] is False
    assert written["r1_d"] is True
    assert written["reproduction_level"] == "R0 only"
