import pytest

from phaino_acoustics.detection_consensus import (
    apply_audit,
    consensus_claim,
    consensus_detection,
    estimator_status,
    parameter_agreement,
)


@pytest.mark.parametrize(
    "baseline,independent,status,reason",
    [
        ("discrepancy", "discrepancy", "detected", None),
        ("adequate", "adequate", "not_detected", None),
        ("discrepancy", "adequate", "undetermined", "estimator_disagreement"),
        ("discrepancy", "insufficient_evidence", "undetermined", "incomplete_confirmation"),
        ("adequate", "insufficient_evidence", "undetermined", "insufficient_evidence"),
        ("insufficient_evidence", "indeterminate", "undetermined", "both_inconclusive"),
    ],
)
def test_ternary_fusion_table(baseline, independent, status, reason):
    out = consensus_detection(baseline, independent)
    assert out["detection_status"] == status
    if reason is None:
        assert out["reason_codes"] == []
    else:
        assert out["reason_codes"] == [reason]


def test_detected_is_estimator_consensus_not_physical_confirmation():
    out = consensus_detection("discrepancy", "discrepancy")
    assert out["detection_status"] == "detected"
    assert out["evidence_scope"] == "estimator_consensus"
    assert out["physically_supported"] is False
    no = consensus_detection("adequate", "adequate")
    assert no["evidence_scope"] is None
    assert no["physically_supported"] is False


def test_abstention_is_not_absence_of_evidence():
    out = consensus_detection("insufficient_evidence", "insufficient_evidence")
    assert out["detection_status"] == "undetermined"
    assert out["detection_status"] != "not_detected"


def test_estimator_status_mapping():
    assert estimator_status("discrepancy") == "D"
    assert estimator_status("adequate") == "A"
    assert estimator_status("insufficient_evidence") == "U"
    assert estimator_status("indeterminate") == "U"
    assert estimator_status(None) == "U"


def test_consensus_claim_disagreement_becomes_undetermined():
    assert consensus_claim("supported_conditional", "supported_conditional")["status"] == "supported_conditional"
    out = consensus_claim("supported_conditional", "undetermined")
    assert out["status"] == "undetermined"
    out = consensus_claim("supported_conditional", "supported_conditional", params_agree=False)
    assert out["status"] == "undetermined"
    assert out["reason_codes"] == ["parameter_disagreement"]


def test_parameter_agreement_bounds():
    assert parameter_agreement({"f0_rel": 1e-6}, {"f0_rel": 1e-3})["agrees"]
    out = parameter_agreement({"b_rel": 0.02}, {"b_rel": 0.005})
    assert not out["agrees"]


def test_apply_audit_v2_counts():
    records = [
        {"family": "acceleration_misspecification", "baseline": {"adequacy_status": "discrepancy"},
         "independent": {"adequacy_status": "discrepancy"}, "differences": {"b_rel": 0.001}},
        {"family": "acceleration_misspecification", "baseline": {"adequacy_status": "discrepancy"},
         "independent": {"adequacy_status": "indeterminate"}, "differences": {"b_rel": 0.02}},
        {"family": "acceleration_misspecification", "baseline": {"adequacy_status": "insufficient_evidence"},
         "independent": {"adequacy_status": "insufficient_evidence"}, "differences": {}},
        {"family": "acceleration_misspecification", "baseline": {"adequacy_status": "adequate"},
         "independent": {"adequacy_status": "adequate"}, "differences": {}},
    ]
    out = apply_audit(records, {"b_rel": 0.005})
    assert out["detection"]["detected"] == 1
    assert out["detection"]["undetermined"] == 2
    assert out["detection"]["not_detected"] == 1
    assert out["detection_reasons"]["incomplete_confirmation"] == 1
    assert out["detection_reasons"]["both_inconclusive"] == 1
    assert out["acceleration"]["false_supported"] == 1
    assert out["rates"]["false_discovery_proportion"] == pytest.approx(0.0)


def test_apply_audit_reports_sensitivity_fpr_and_fdp():
    records = [
        {"family": "correct_constant_velocity", "baseline": {"adequacy_status": "discrepancy"},
         "independent": {"adequacy_status": "discrepancy"}, "differences": {}},
        {"family": "correct_constant_velocity", "baseline": {"adequacy_status": "adequate"},
         "independent": {"adequacy_status": "adequate"}, "differences": {}},
        {"family": "acceleration_misspecification", "baseline": {"adequacy_status": "discrepancy"},
         "independent": {"adequacy_status": "discrepancy"}, "differences": {}},
        {"family": "acceleration_misspecification", "baseline": {"adequacy_status": "insufficient_evidence"},
         "independent": {"adequacy_status": "insufficient_evidence"}, "differences": {}},
    ]
    out = apply_audit(records, {})
    assert out["rates"]["sensitivity"] == pytest.approx(0.5)
    assert out["rates"]["false_positive_rate"] == pytest.approx(0.5)
    assert out["rates"]["deterministic_no_detection_rate"] == pytest.approx(0.5)
    assert out["rates"]["abstention_rate_mismatch"] == pytest.approx(0.5)
    assert out["rates"]["abstention_rate_correct"] == 0.0
    # 1 false detection among 2 total detections (1 correct-CV, 1 acceleration).
    assert out["rates"]["false_discovery_proportion"] == pytest.approx(0.5)
    assert out["evidence_scope"] == "estimator_consensus"
    assert out["physically_supported"] is False


def test_consensus_claim_rejects_unknown_status():
    with pytest.raises(ValueError):
        consensus_claim("accepted", "undetermined")
