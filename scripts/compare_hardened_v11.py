#!/usr/bin/env python3
"""Compare hardened v1.1 artifacts semantically, not just by final status.

The baseline is the authoritative run; candidate runs are compared against it.
A primary mismatch exits nonzero. Optimization-status differences are reported
as diagnostics when the decision status and reason still agree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

PROTOCOL = Path("protocols/e0-hardened-v1.1.json")
REQUIRED_VERSION = "1.1.0"
PRIMARY_FALLBACK = None


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    data = json.loads(path.read_text())
    if data.get("hardened_version") != REQUIRED_VERSION:
        raise SystemExit(f"{path}: hardened_version {data.get('hardened_version')!r} != {REQUIRED_VERSION}")
    return data


def primary_fields(protocol: dict) -> list[str]:
    fields = (protocol.get("comparison") or {}).get("primary_fields")
    if not isinstance(fields, list) or not fields:
        raise SystemExit("protocol.comparison.primary_fields is required; refusing to fall back")
    return fields


def identity_digest(trials: list[dict]) -> str:
    lines = [
        f"{trial['condition']}\t{trial['trial']}\t{trial['seed']}"
        for trial in sorted(trials, key=lambda item: (item["condition"], item["trial"], item["seed"]))
    ]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _path_present(trial: dict, dotted: str) -> bool:
    node = trial
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


def validate_artifact(data: dict, path: Path, protocol: dict) -> list[dict]:
    """Validate the artifact's completeness before it participates in comparison."""
    expected = protocol.get("expected") or {}
    expected_count = int(expected.get("trial_count", 0))
    expected_conditions = set(expected.get("conditions") or [])
    trials = data.get("trials")
    if not isinstance(trials, list):
        raise SystemExit(f"{path}: trials is not a list")
    if expected_count and len(trials) != expected_count:
        raise SystemExit(f"{path}: expected {expected_count} trials, got {len(trials)}")
    seen: set[tuple] = set()
    per_condition: dict[str, int] = {}
    primary = primary_fields(protocol)
    for index, trial in enumerate(trials):
        if not isinstance(trial, dict):
            raise SystemExit(f"{path}: trial {index} is not an object")
        key = (trial.get("condition"), trial.get("trial"), trial.get("seed"))
        if any(part is None for part in key):
            raise SystemExit(f"{path}: trial {index} has an incomplete identity {key!r}")
        if key in seen:
            raise SystemExit(f"{path}: duplicate trial identity {key!r}")
        seen.add(key)
        condition = key[0]
        per_condition[condition] = per_condition.get(condition, 0) + 1
        for field in primary:
            if not _path_present(trial, field):
                raise SystemExit(f"{path}: trial {key!r} is missing primary field {field!r}")
    expected_identity = expected.get("identity_sha256")
    if not expected_identity:
        raise SystemExit("protocol.expected.identity_sha256 is required; identity set is not frozen")
    actual_identity = identity_digest(trials)
    if actual_identity != expected_identity:
        raise SystemExit(
            f"{path}: trial identity digest {actual_identity} != protocol {expected_identity}"
        )
    if expected_conditions and set(per_condition) != expected_conditions:
        missing = sorted(expected_conditions - set(per_condition))[:5]
        extra = sorted(set(per_condition) - expected_conditions)[:5]
        raise SystemExit(f"{path}: condition set mismatch: missing={missing} extra={extra}")
    expected_per_condition = int(expected.get("trials_per_condition", 0))
    if expected_per_condition:
        bad = {name: count for name, count in per_condition.items() if count != expected_per_condition}
        if bad:
            raise SystemExit(f"{path}: condition trial counts differ from {expected_per_condition}: {bad}")
    return trials


def trial_key(trial: dict) -> tuple:
    return (trial.get("condition"), trial.get("trial"), trial.get("seed"))


def value(trial: dict, dotted: str):
    node = trial
    for part in dotted.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def compare(baseline: dict, candidate: dict, protocol: dict) -> dict:
    base = {trial_key(t): t for t in baseline.get("trials", [])}
    cand = {trial_key(t): t for t in candidate.get("trials", [])}
    if set(base) != set(cand):
        missing = sorted(set(base) - set(cand))[:5]
        extra = sorted(set(cand) - set(base))[:5]
        raise SystemExit(f"trial identity mismatch: missing={missing} extra={extra}")

    fields = primary_fields(protocol)
    diagnostics = ["hardened.optimization_status"]
    reason_classes = {
        "criteria_confirmed": "converged",
        "fixed_point_verified": "converged",
        "stalled_without_stationarity": "stalled",
        "iteration_budget": "budget",
        "numerical_failure": "failed",
    }
    mismatches = []
    diagnostic_changes = []
    alias_changes = []
    boundary = []
    for key in sorted(base):
        left, right = base[key], cand[key]
        for field in fields:
            if value(left, field) != value(right, field):
                mismatches.append({"trial": key, "field": field, "baseline": value(left, field), "candidate": value(right, field)})
        for field in diagnostics:
            if value(left, field) != value(right, field):
                diagnostic_changes.append({"trial": key, "field": field, "baseline": value(left, field), "candidate": value(right, field)})
        left_reason = value(left, "hardened.optimization_reason")
        right_reason = value(right, "hardened.optimization_reason")
        if reason_classes.get(left_reason, left_reason) != reason_classes.get(right_reason, right_reason):
            diagnostic_changes.append({"trial": key, "field": "hardened.optimization_reason_class", "baseline": left_reason, "candidate": right_reason})
        elif left_reason != right_reason:
            alias_changes.append({"trial": key, "baseline": left_reason, "candidate": right_reason})
        improvement = value(left, "hardened.improvement_ratio")
        if isinstance(improvement, (int, float)) and abs(improvement - 0.5) <= 0.05:
            boundary.append({"trial": key, "improvement_ratio": improvement, "decision_status": value(left, "hardened.decision_status")})
    return {
        "paired_trials": len(base),
        "primary_mismatches": mismatches,
        "diagnostic_changes": diagnostic_changes,
        "diagnostic_alias_changes": alias_changes,
        "boundary_cases": boundary,
        "baseline_environment": baseline.get("environment"),
        "candidate_environment": candidate.get("environment"),
        "baseline_records_sha256": baseline.get("hardened_records_sha256"),
        "candidate_records_sha256": candidate.get("hardened_records_sha256"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidate", required=True, action="append", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    baseline = load(args.baseline)
    validate_artifact(baseline, args.baseline, protocol)
    report = {
        "protocol_id": protocol["protocol_id"],
        "protocol_version": protocol["version"],
        "protocol_sha256": sha256(args.protocol),
        "baseline": {"path": str(args.baseline), "sha256": sha256(args.baseline)},
        "candidates": [],
    }
    failed = False
    for path in args.candidate:
        candidate = load(path)
        validate_artifact(candidate, path, protocol)
        result = compare(baseline, candidate, protocol)
        result["path"] = str(path)
        result["sha256"] = sha256(path)
        if result["primary_mismatches"]:
            failed = True
        report["candidates"].append(result)
    report["passed"] = not failed
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({
        "passed": report["passed"],
        "paired_trials": report["candidates"][0]["paired_trials"] if report["candidates"] else 0,
        "primary_mismatches": sum(len(c["primary_mismatches"]) for c in report["candidates"]),
        "diagnostic_changes": sum(len(c["diagnostic_changes"]) for c in report["candidates"]),
        "diagnostic_alias_changes": sum(len(c["diagnostic_alias_changes"]) for c in report["candidates"]),
        "boundary_cases": sum(len(c["boundary_cases"]) for c in report["candidates"]),
        "report": str(args.out),
    }, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
