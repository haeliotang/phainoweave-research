import pytest

from phaino_verify.run_state import (
    RunRecord,
    RunStateError,
    advance_execution,
    set_scientific_outcome,
    to_json,
    validate_execution_transition,
)


def completed_run(run_id="run-1"):
    r = RunRecord(run_id)
    advance_execution(r, "sealed")
    advance_execution(r, "running")
    advance_execution(r, "completed", {"artifact_sha256": "abc"})
    return r


def test_full_valid_lifecycle_and_supported_outcome():
    r = completed_run()
    set_scientific_outcome(r, "hypothesis_supported", {"hypothesis_id": "H-1", "decision_protocol": "protocol.json", "data_scope": "synthetic", "primary_endpoint": "pass"})
    assert r.execution_status == "completed"
    assert r.scientific_outcome == "hypothesis_supported"
    assert [h["execution_status"] for h in r.history] == ["prepared", "sealed", "running", "completed"]


def test_negative_result_is_completed_run_not_execution_failure():
    r = completed_run("run-neg")
    set_scientific_outcome(r, "hypothesis_rejected", {"hypothesis_id": "H-1", "decision_protocol": "protocol.json", "data_scope": "synthetic", "reason": "primary endpoint not met"})
    assert r.execution_status == "completed"
    assert r.scientific_outcome == "hypothesis_rejected"


def test_invalid_execution_requires_reason_and_revision_and_blocks_outcome():
    r = RunRecord("run-invalid")
    advance_execution(r, "sealed")
    advance_execution(r, "running")
    with pytest.raises(RunStateError):
        advance_execution(r, "invalid_execution", {"reason": "boom"})
    advance_execution(r, "invalid_execution", {"reason": "boom", "revision": "v3"})
    assert r.execution_status == "invalid_execution"
    assert r.scientific_outcome == "not_evaluated"
    with pytest.raises(RunStateError):
        set_scientific_outcome(r, "hypothesis_rejected")


def test_completed_requires_artifact_digest():
    r = RunRecord("run-3")
    advance_execution(r, "sealed")
    advance_execution(r, "running")
    with pytest.raises(RunStateError):
        advance_execution(r, "completed")
    advance_execution(r, "completed", {"artifact_sha256": "digest"})


def test_illegal_skips_and_terminal_states():
    r = RunRecord("run-4")
    with pytest.raises(RunStateError):
        advance_execution(r, "running")
    advance_execution(r, "sealed")
    advance_execution(r, "running")
    advance_execution(r, "invalid_execution", {"reason": "no data", "revision": "v1"})
    with pytest.raises(RunStateError):
        advance_execution(r, "completed", {"artifact_sha256": "x"})


def test_outcome_requires_completed_and_is_immutable_after_set():
    r = RunRecord("run-5")
    advance_execution(r, "sealed")
    advance_execution(r, "running")
    with pytest.raises(RunStateError):
        set_scientific_outcome(r, "hypothesis_rejected")
    advance_execution(r, "completed", {"artifact_sha256": "digest"})
    set_scientific_outcome(r, "inconclusive", {"hypothesis_id": "H-1", "decision_protocol": "protocol.json", "data_scope": "synthetic"})
    with pytest.raises(RunStateError):
        set_scientific_outcome(r, "hypothesis_supported")


def test_details_normalized_and_serialized():
    detail = validate_execution_transition("running", "completed", {"artifact_sha256": "digest", "extra": 1})
    assert detail["execution_status"] == "completed"
    r = completed_run("run-6")
    set_scientific_outcome(r, "hypothesis_supported", {"hypothesis_id": "H-1", "decision_protocol": "protocol.json", "data_scope": "synthetic", "primary_endpoint": "pass"})
    payload = to_json(r)
    assert '"run_id": "run-6"' in payload
    assert '"execution_status": "completed"' in payload
    assert '"scientific_outcome": "hypothesis_supported"' in payload


def test_outcome_requires_hypothesis_protocol_and_scope():
    r = completed_run("run-7")
    with pytest.raises(RunStateError):
        set_scientific_outcome(r, "hypothesis_supported", {"primary_endpoint": "pass"})
    with pytest.raises(RunStateError):
        set_scientific_outcome(
            r, "hypothesis_supported", {"hypothesis_id": "H-1", "decision_protocol": "p.json"}
        )
    set_scientific_outcome(
        r,
        "hypothesis_supported",
        {"hypothesis_id": "H-1", "decision_protocol": "p.json", "data_scope": "synthetic locked"},
    )
