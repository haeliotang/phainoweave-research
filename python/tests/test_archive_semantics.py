import json
from pathlib import Path

from phaino_verify.run_state import (
    EXECUTION_STATES,
    SCIENTIFIC_OUTCOMES,
    TERMINAL_EXECUTION,
    validate_execution_transition,
)

ARCHIVE = Path(__file__).resolve().parents[2] / "evidence" / "c2c-sealed" / "ARCHIVE.json"


def load_runs():
    doc = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    return doc["runs"]


def test_every_run_has_orthogonal_fields():
    for run in load_runs():
        assert run["execution_status"] in EXECUTION_STATES
        assert run["scientific_outcome"] in SCIENTIFIC_OUTCOMES
        assert "scientific_failure" not in run


def test_invalid_execution_is_not_a_scientific_result():
    for run in load_runs():
        if run["execution_status"] == "invalid_execution":
            assert run["scientific_outcome"] == "not_evaluated"
            assert run["details"].get("reason")
            assert run["details"].get("revision")


def test_completed_outcome_is_scoped():
    for run in load_runs():
        if run["execution_status"] == "completed":
            ev = run.get("outcome_evidence", {})
            assert ev.get("hypothesis_id")
            assert ev.get("decision_protocol")
            assert ev.get("data_scope")
            # A limited synthetic result must not claim real-world scope.
            assert "real-world" in ev.get("scope_note", "").lower() or "synthetic" in ev.get("data_scope", "").lower()


def test_archive_history_is_a_valid_execution_chain():
    for run in load_runs():
        history = run.get("history", [])
        assert history and history[0]["execution_status"] == "prepared"
        for prev, curr in zip(history, history[1:]):
            validate_execution_transition(prev["execution_status"], curr["execution_status"], curr.get("details"))
        assert run["execution_status"] == history[-1]["execution_status"]


def test_no_archive_run_claims_unbounded_real_world_success():
    for run in load_runs():
        if run["execution_status"] == "completed":
            text = json.dumps(run, sort_keys=True).lower()
            assert "real-world reliable" not in text
            assert "measurement model is fixed" not in text
