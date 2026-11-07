"""Bench-session metadata contract.

A bench session is instrument calibration/evaluation data, not an E1 field
event.  Every capture records its raw path, digest, role and settings so that
calibration data and independent evaluation data are never mixed.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

ROLES = ("calibration", "evaluation")


@dataclass
class Capture:
    capture_id: str
    role: str
    kind: str  # "tone" | "clock" | "chain" | "noise"
    path: str
    sha256: str
    sample_rate_hz: int
    settings: dict[str, Any] = field(default_factory=dict)
    notes: str = ""


@dataclass
class BenchSession:
    session_id: str
    measurement_model_id: str
    device: dict[str, Any]
    environment: dict[str, Any]
    reference: dict[str, Any]
    captures: list[Capture] = field(default_factory=list)
    calibration_split: list[str] = field(default_factory=list)
    evaluation_split: list[str] = field(default_factory=list)
    protocol_version: str = "e1-0-bench-1.0.0"
    notes: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=1, sort_keys=True, allow_nan=False)


def validate_session(session: BenchSession, require_files: bool = False) -> BenchSession:
    if not session.session_id.strip():
        raise ValueError("session_id is required")
    if not session.measurement_model_id.strip():
        raise ValueError("measurement_model_id is required")
    ids = [c.capture_id for c in session.captures]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate capture_id")
    allowed = set(ids)
    for name in ("calibration_split", "evaluation_split"):
        for cid in getattr(session, name):
            if cid not in allowed:
                raise ValueError(f"{name} references unknown capture {cid!r}")
    overlap = set(session.calibration_split) & set(session.evaluation_split)
    if overlap:
        raise ValueError(f"captures appear in both calibration and evaluation: {sorted(overlap)}")
    for capture in session.captures:
        if capture.role not in ROLES:
            raise ValueError(f"capture {capture.capture_id}: role must be one of {ROLES}")
        if capture.capture_id in session.calibration_split and capture.role != "calibration":
            raise ValueError(f"capture {capture.capture_id} role/ split mismatch")
        if capture.capture_id in session.evaluation_split and capture.role != "evaluation":
            raise ValueError(f"capture {capture.capture_id} role/ split mismatch")
        if require_files and not Path(capture.path).exists():
            raise FileNotFoundError(capture.path)
    return session
