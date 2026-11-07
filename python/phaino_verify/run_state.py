"""Sealed-run lifecycle: execution status and scientific outcome are orthogonal.

Execution status answers "did the run execute validly?":

    prepared -> sealed -> running -> completed
                                 -> invalid_execution

Scientific outcome answers "what did the completed experiment conclude?":

    pending | hypothesis_supported | hypothesis_rejected | inconclusive | not_evaluated

A negative scientific result is a *completed* run with outcome
``hypothesis_rejected``; it is never ``scientific_failure``.  An invalid
execution leaves the scientific outcome ``not_evaluated`` and cannot later be
assigned one.  Terminal execution states never transition again.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

EXECUTION_STATES = ("prepared", "sealed", "running", "completed", "invalid_execution")
TERMINAL_EXECUTION = frozenset({"completed", "invalid_execution"})

ALLOWED_EXECUTION = {
    "prepared": frozenset({"sealed"}),
    "sealed": frozenset({"running"}),
    "running": frozenset({"completed", "invalid_execution"}),
    "completed": frozenset(),
    "invalid_execution": frozenset(),
}

SCIENTIFIC_OUTCOMES = (
    "pending",
    "hypothesis_supported",
    "hypothesis_rejected",
    "inconclusive",
    "not_evaluated",
)

REQUIRED_DETAILS = {
    "completed": ("artifact_sha256",),
    "invalid_execution": ("reason", "revision"),
}


class RunStateError(ValueError):
    """Raised when an execution transition or scientific outcome is invalid."""


@dataclass
class RunRecord:
    run_id: str
    execution_status: str = "prepared"
    scientific_outcome: str = "pending"
    history: list[dict[str, Any]] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    outcome_evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.execution_status not in EXECUTION_STATES:
            raise RunStateError(f"unknown execution status: {self.execution_status}")
        if self.scientific_outcome not in SCIENTIFIC_OUTCOMES:
            raise RunStateError(f"unknown scientific outcome: {self.scientific_outcome}")
        if not self.history:
            self.history.append({"execution_status": self.execution_status, "details": {}})


def validate_execution_transition(
    current: str, new_state: str, details: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    if current not in EXECUTION_STATES:
        raise RunStateError(f"unknown current execution status: {current}")
    if new_state not in EXECUTION_STATES:
        raise RunStateError(f"unknown target execution status: {new_state}")
    if new_state not in ALLOWED_EXECUTION[current]:
        raise RunStateError(f"illegal execution transition {current} -> {new_state}")
    details = dict(details or {})
    for key in REQUIRED_DETAILS.get(new_state, ()):
        value = details.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            raise RunStateError(f"execution status {new_state} requires non-empty {key!r}")
    if new_state in ("completed", "invalid_execution") and current != "running":
        raise RunStateError(f"{new_state} may only follow running")
    return {"execution_status": new_state, "details": details}


def advance_execution(
    record: RunRecord, new_state: str, details: Optional[dict[str, Any]] = None
) -> RunRecord:
    normalized = validate_execution_transition(record.execution_status, new_state, details)
    record.execution_status = normalized["execution_status"]
    record.details = normalized["details"]
    record.history.append(normalized)
    if new_state == "invalid_execution":
        # Invalid execution is not a scientific result.
        record.scientific_outcome = "not_evaluated"
    return record


OUTCOME_EVIDENCE_REQUIRED = ("hypothesis_id", "decision_protocol", "data_scope")


def set_scientific_outcome(
    record: RunRecord, outcome: str, evidence: Optional[dict[str, Any]] = None
) -> RunRecord:
    if outcome not in SCIENTIFIC_OUTCOMES:
        raise RunStateError(f"unknown scientific outcome: {outcome}")
    if record.execution_status != "completed":
        raise RunStateError(
            f"scientific outcome requires execution_status=completed, got {record.execution_status}"
        )
    if record.scientific_outcome not in ("pending", outcome):
        raise RunStateError(
            f"scientific outcome already set to {record.scientific_outcome}; it is not mutable"
        )
    evidence = dict(evidence or {})
    # A run-level outcome must name the hypothesis, the decision protocol and
    # the data domain it applies to; otherwise a limited success can be quoted
    # later as a general conclusion.
    for key in OUTCOME_EVIDENCE_REQUIRED:
        value = evidence.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            raise RunStateError(f"scientific outcome requires non-empty {key!r}")
    record.scientific_outcome = outcome
    record.outcome_evidence = evidence
    return record


def to_json(record: RunRecord) -> str:
    return json.dumps(
        {
            "run_id": record.run_id,
            "execution_status": record.execution_status,
            "scientific_outcome": record.scientific_outcome,
            "details": record.details,
            "outcome_evidence": record.outcome_evidence,
            "history": record.history,
        },
        indent=1,
        sort_keys=True,
        allow_nan=False,
    )
