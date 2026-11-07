import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "compare_hardened_v11", ROOT / "scripts" / "compare_hardened_v11.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def trial(index: int, condition: str = "c1", **overrides):
    hardened = {
        "decision_status": "accepted",
        "decision_reason": "converged_adequate_identifiable",
        "parameter_identifiable": True,
        "model_adequate": True,
        "optimization_status": "converged",
        "optimization_reason": "fixed_point_verified",
        "improvement_ratio": 0.8,
    }
    hardened.update(overrides)
    return {
        "condition": condition,
        "trial": index,
        "seed": 100 + index,
        "hardened": hardened,
    }


def artifact(trials):
    return {"hardened_version": "1.1.0", "trials": trials}


def protocol():
    return {
        "comparison": {
            "primary_fields": [
                "hardened.decision_status",
                "hardened.decision_reason",
                "hardened.parameter_identifiable",
                "hardened.model_adequate",
            ]
        },
        "expected": {
            "trial_count": 2,
            "conditions": ["c1"],
            "trials_per_condition": 2,
            "identity_sha256": MODULE.identity_digest([trial(0), trial(1)]),
        },
    }


def test_valid_artifact_passes_integrity_and_comparison(tmp_path):
    base = artifact([trial(0), trial(1)])
    cand = artifact([trial(0), trial(1)])
    MODULE.validate_artifact(base, tmp_path / "base.json", protocol())
    result = MODULE.compare(base, cand, protocol())
    assert result["paired_trials"] == 2
    assert result["primary_mismatches"] == []


def test_duplicate_trial_identity_is_rejected(tmp_path):
    bad = artifact([trial(0), trial(0)])
    with pytest.raises(SystemExit, match="duplicate trial identity"):
        MODULE.validate_artifact(bad, tmp_path / "bad.json", protocol())


def test_missing_trial_is_rejected(tmp_path):
    short = artifact([trial(0)])
    with pytest.raises(SystemExit, match="expected 2 trials"):
        MODULE.validate_artifact(short, tmp_path / "short.json", protocol())


def test_missing_primary_field_is_rejected(tmp_path):
    bad = trial(0)
    del bad["hardened"]["decision_reason"]
    with pytest.raises(SystemExit, match="missing primary field"):
        MODULE.validate_artifact(artifact([bad, trial(1)]), tmp_path / "bad.json", protocol())


def test_wrong_trial_indices_or_seeds_are_rejected(tmp_path):
    bad = artifact([trial(100), trial(101)])
    with pytest.raises(SystemExit, match="trial identity digest"):
        MODULE.validate_artifact(bad, tmp_path / "bad.json", protocol())


def test_primary_fields_must_be_declared_by_protocol(tmp_path):
    spec = protocol()
    del spec["comparison"]["primary_fields"]
    with pytest.raises(SystemExit, match="primary_fields is required"):
        MODULE.validate_artifact(artifact([trial(0), trial(1)]), tmp_path / "x.json", spec)


def test_condition_set_is_checked(tmp_path):
    bad = artifact([trial(0, condition="c2"), trial(1, condition="c2")])
    spec = protocol()
    spec["expected"]["identity_sha256"] = MODULE.identity_digest(bad["trials"])
    with pytest.raises(SystemExit, match="condition set mismatch"):
        MODULE.validate_artifact(bad, tmp_path / "bad.json", spec)
