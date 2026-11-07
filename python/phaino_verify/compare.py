"""Cross-platform artifact comparison: R0 execution, R1 numerical equivalence, R2 bytes.

The report is deterministic JSON: object keys sorted, compact separators, no timestamps.
Every classification is a pure function of the two artifacts and the protocol; tolerances
come only from the protocol document.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from phaino_sdk.canonical import canonical_sha256

from .artifacts import Artifact, ArtifactError, load_artifact, sha256_bytes
from .paths import (
    delete_concrete,
    delete_order,
    flatten,
    path_specificity,
    resolve,
)
from .protocol import NumericField, Protocol, ProtocolError, load_protocol

CLASSIFICATIONS = ("exact", "numerically_equivalent", "mismatch", "unknown")
LEVELS = ("r0_execution", "r1_numerical_equivalence", "r2_bitwise_identity")
_TRIAL_PATH = re.compile(r"^trials\[(\d+)\]")
_CONDITION_PATH = re.compile(r"^conditions\[(\d+)\]")


@dataclass
class Report:
    """Deterministic comparison report."""

    protocol: dict[str, Any]
    reference: dict[str, Any]
    candidate: dict[str, Any]
    levels: dict[str, bool]
    classification: str
    per_field_stats: list[dict[str, Any]]
    exact_violations: list[dict[str, Any]]
    numeric_violations: list[dict[str, Any]]
    violations: list[dict[str, Any]]
    decision_instability: list[dict[str, Any]]
    ignored_fields_found: list[str]
    reasons: list[str]
    contract_version: int = 1
    r1_n: bool | None = None
    r1_d: bool | None = None
    reproduction_level: str | None = None
    identifiability: list[dict[str, Any]] = field(default_factory=list)
    identifiability_summary: dict[str, Any] = field(default_factory=dict)
    decision_summary: list[dict[str, Any]] = field(default_factory=list)
    decision_changes: list[dict[str, Any]] = field(default_factory=list)
    rate_changes: list[dict[str, Any]] = field(default_factory=list)
    classification_inconsistencies: list[dict[str, Any]] = field(default_factory=list)
    unidentifiable_numeric: list[dict[str, Any]] = field(default_factory=list)
    diagnostic_summary: list[dict[str, Any]] = field(default_factory=list)
    diagnostic_differences: list[dict[str, Any]] = field(default_factory=list)
    unclassified_fields: list[str] = field(default_factory=list)

    def to_document(self) -> dict[str, Any]:
        return copy.deepcopy(
            {
                "protocol": self.protocol,
                "reference": self.reference,
                "candidate": self.candidate,
                "levels": self.levels,
                "classification": self.classification,
                "per_field_stats": self.per_field_stats,
                "exact_violations": self.exact_violations,
                "numeric_violations": self.numeric_violations,
                "violations": self.violations,
                "decision_instability": self.decision_instability,
                "ignored_fields_found": self.ignored_fields_found,
                "reasons": self.reasons,
                "contract_version": self.contract_version,
                "r1_n": self.r1_n,
                "r1_d": self.r1_d,
                "reproduction_level": self.reproduction_level,
                "identifiability": self.identifiability,
                "identifiability_summary": self.identifiability_summary,
                "decision_summary": self.decision_summary,
                "decision_changes": self.decision_changes,
                "rate_changes": self.rate_changes,
                "classification_inconsistencies": self.classification_inconsistencies,
                "unidentifiable_numeric": self.unidentifiable_numeric,
                "diagnostic_summary": self.diagnostic_summary,
                "diagnostic_differences": self.diagnostic_differences,
                "unclassified_fields": self.unclassified_fields,
            }
        )

    def to_json(self) -> str:
        return (
            json.dumps(
                self.to_document(),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        )

    @classmethod
    def unknown(
        cls,
        protocol: Protocol,
        reference: dict[str, Any],
        candidate: dict[str, Any],
        reasons: list[str],
    ) -> Report:
        return cls(
            protocol=_protocol_descriptor(protocol),
            reference=reference,
            candidate=candidate,
            levels={key: False for key in LEVELS},
            classification="unknown",
            per_field_stats=[],
            exact_violations=[],
            numeric_violations=[],
            violations=[],
            decision_instability=[],
            ignored_fields_found=[],
            reasons=list(reasons),
        )


def compare_artifacts(
    reference: Artifact | Mapping[str, Any],
    candidate: Artifact | Mapping[str, Any],
    protocol: Protocol,
) -> Report:
    """Compares two artifacts under a protocol without mutating either input."""
    reference = _as_artifact(reference)
    candidate = _as_artifact(candidate)
    if getattr(protocol, "contract_version", 1) == 2:
        from .v2 import compare_v2

        return compare_v2(reference, candidate, protocol)
    reference_document = reference.document
    candidate_document = candidate.document

    reasons: list[str] = []
    structure_ok = _check_structure(
        reference_document, candidate_document, protocol, reasons
    )

    ignored_found: list[str] = []
    if isinstance(reference_document, Mapping) and isinstance(candidate_document, Mapping):
        try:
            ignored_found = sorted(
                set(_ignored_present(reference_document, protocol))
                | set(_ignored_present(candidate_document, protocol))
            )
        except (KeyError, TypeError):
            ignored_found = []

    canonical_reference: str | None = None
    canonical_candidate: str | None = None
    r2 = False
    if structure_ok:
        try:
            cleaned_reference = _remove_ignored(reference_document, protocol)
            cleaned_candidate = _remove_ignored(candidate_document, protocol)
            canonical_reference = canonical_sha256(cleaned_reference)
            canonical_candidate = canonical_sha256(cleaned_candidate)
            r2 = canonical_reference == canonical_candidate
        except (ValueError, TypeError) as error:
            reasons.append(f"cannot canonicalize artifacts: {error}")
            structure_ok = False

    levels = {
        "r0_execution": structure_ok,
        "r1_numerical_equivalence": False,
        "r2_bitwise_identity": r2 if structure_ok else False,
    }
    reference_descriptor = _artifact_descriptor(reference, canonical_reference)
    candidate_descriptor = _artifact_descriptor(candidate, canonical_candidate)

    if not structure_ok:
        return Report(
            protocol=_protocol_descriptor(protocol),
            reference=reference_descriptor,
            candidate=candidate_descriptor,
            levels=levels,
            classification="unknown",
            per_field_stats=[],
            exact_violations=[],
            numeric_violations=[],
            violations=[],
            decision_instability=[],
            ignored_fields_found=ignored_found,
            reasons=sorted(set(reasons)),
        )

    normalized_reference = _normalized(reference_document, protocol)
    normalized_candidate = _normalized(candidate_document, protocol)
    cleaned_reference = _remove_ignored(normalized_reference, protocol)
    cleaned_candidate = _remove_ignored(normalized_candidate, protocol)

    exact_paths, numeric_map = _classification_sets(
        cleaned_reference, cleaned_candidate, protocol
    )
    reference_leaves = flatten(cleaned_reference)
    candidate_leaves = flatten(cleaned_candidate)
    all_paths = sorted(set(reference_leaves) | set(candidate_leaves))

    violations: list[dict[str, Any]] = []
    exact_violations: list[dict[str, Any]] = []
    numeric_violations: list[dict[str, Any]] = []
    stats = {
        entry.path: {
            "field": entry.path,
            "abs_tol": entry.abs_tol,
            "rel_tol": entry.rel_tol,
            "compared": 0,
            "violations": 0,
            "max_abs": None,
            "max_rel": None,
            "worst_location": None,
        }
        for entry in protocol.numeric_fields
    }

    for path in all_paths:
        in_reference = path in reference_leaves
        in_candidate = path in candidate_leaves
        if in_reference != in_candidate:
            kind = "missing" if not in_reference else "extra"
            violations.append(
                {
                    "kind": kind,
                    "path": path,
                    "location": _location(path, cleaned_reference, cleaned_candidate),
                    "reference": _jsonable(reference_leaves.get(path)) if in_reference else None,
                    "candidate": _jsonable(candidate_leaves.get(path)) if in_candidate else None,
                }
            )
            continue
        reference_value = reference_leaves[path]
        candidate_value = candidate_leaves[path]
        numeric = numeric_map.get(path)
        exact_specificity = exact_paths.get(path)
        if numeric is not None:
            entry, numeric_specificity = numeric
            use_numeric = exact_specificity is None or numeric_specificity > exact_specificity
        else:
            use_numeric = False
        if use_numeric and numeric is not None:
            entry, _ = numeric
            if _is_numeric_or_null(reference_value) and _is_numeric_or_null(candidate_value):
                violation = _compare_numeric(
                    path,
                    reference_value,
                    candidate_value,
                    entry,
                    cleaned_reference,
                    cleaned_candidate,
                    stats[entry.path],
                )
                if violation is not None:
                    violations.append(violation)
                    numeric_violations.append(violation)
                continue
        if _exact_equal(reference_value, candidate_value):
            continue
        violation = {
            "kind": "exact",
            "path": path,
            "location": _location(path, cleaned_reference, cleaned_candidate),
            "reference": _jsonable(reference_value),
            "candidate": _jsonable(candidate_value),
        }
        violations.append(violation)
        exact_violations.append(violation)

    r1 = not violations
    levels["r1_numerical_equivalence"] = r1
    instability = _decision_instability(
        cleaned_reference, cleaned_candidate, protocol, numeric_violations
    )

    if r1 and r2:
        classification = "exact"
    elif r1:
        classification = "numerically_equivalent"
    else:
        classification = "mismatch"

    return Report(
        protocol=_protocol_descriptor(protocol),
        reference=reference_descriptor,
        candidate=candidate_descriptor,
        levels=levels,
        classification=classification,
        per_field_stats=sorted(stats.values(), key=lambda item: item["field"]),
        exact_violations=sorted(exact_violations, key=lambda item: item["path"]),
        numeric_violations=sorted(numeric_violations, key=lambda item: item["path"]),
        violations=sorted(violations, key=lambda item: (item["path"], item["kind"])),
        decision_instability=instability,
        ignored_fields_found=ignored_found,
        reasons=[],
    )


def _as_artifact(value: Artifact | Mapping[str, Any]) -> Artifact:
    if isinstance(value, Artifact):
        return value
    if isinstance(value, Mapping):
        return Artifact.from_document(value)
    raise TypeError("artifact must be an Artifact or a mapping")


def _protocol_descriptor(protocol: Protocol) -> dict[str, Any]:
    return {
        "id": protocol.protocol_id,
        "version": protocol.version,
        "sha256": protocol.digest(),
        "tolerance_status": protocol.tolerance_status,
    }


def _artifact_descriptor(
    artifact: Artifact, canonical: str | None
) -> dict[str, Any]:
    return {
        "path": artifact.path,
        "raw_sha256": artifact.raw_sha256,
        "decoded_sha256": artifact.decoded_sha256,
        "canonical_sha256": canonical,
    }


def _check_structure(
    reference: Any,
    candidate: Any,
    protocol: Protocol,
    reasons: list[str],
) -> bool:
    rules = protocol.structural_rules
    for label, document in (("reference", reference), ("candidate", candidate)):
        if not isinstance(document, Mapping):
            reasons.append(f"{label} artifact is not a JSON object")
    if reasons:
        return False

    for label, document in (("reference", reference), ("candidate", candidate)):
        nonfinite = _find_nonfinite(document)
        if nonfinite is not None:
            reasons.append(f"{label} has a non-finite number at {nonfinite}")
        for key in rules.required_keys:
            if key not in document:
                reasons.append(f"{label} is missing required key {key!r}")
        trials = document.get(rules.trials_key)
        conditions = document.get(rules.conditions_key)
        if not isinstance(trials, list):
            reasons.append(f"{label}.{rules.trials_key} must be a list")
        if not isinstance(conditions, list):
            reasons.append(f"{label}.{rules.conditions_key} must be a list")
    if reasons:
        return False

    reference_conditions = _condition_names(reference, protocol, "reference", reasons)
    candidate_conditions = _condition_names(candidate, protocol, "candidate", reasons)
    if reference_conditions is None or candidate_conditions is None:
        return False
    if rules.same_condition_set and set(reference_conditions) != set(candidate_conditions):
        reasons.append("condition set differs between artifacts")
    if rules.same_condition_order and reference_conditions != candidate_conditions:
        reasons.append("condition order differs between artifacts")

    reference_trials = _trial_ids(reference, protocol, "reference", reasons)
    candidate_trials = _trial_ids(candidate, protocol, "candidate", reasons)
    if reference_trials is None or candidate_trials is None:
        return False
    reference_keys = set(reference_trials)
    candidate_keys = set(candidate_trials)
    if rules.no_missing and reference_keys - candidate_keys:
        reasons.append("candidate is missing trials present in the reference")
    if rules.no_extra and candidate_keys - reference_keys:
        reasons.append("candidate has trials not present in the reference")
    if rules.exactly_once and len(reference_trials) != len(reference_keys):
        reasons.append("reference contains a trial id more than once")
    if rules.exactly_once and len(candidate_trials) != len(candidate_keys):
        reasons.append("candidate contains a trial id more than once")
    if rules.no_duplicates and (
        len(reference_trials) != len(reference_keys)
        or len(candidate_trials) != len(candidate_keys)
    ):
        reasons.append("duplicate trial ids are not allowed")
    return not reasons


def _condition_names(
    document: Mapping[str, Any], protocol: Protocol, label: str, reasons: list[str]
) -> list[str] | None:
    rules = protocol.structural_rules
    conditions = document.get(rules.conditions_key)
    if not isinstance(conditions, list):
        return None
    names: list[str] = []
    for index, entry in enumerate(conditions):
        if not isinstance(entry, Mapping) or rules.condition_key not in entry:
            reasons.append(
                f"{label}.{rules.conditions_key}[{index}] is missing {rules.condition_key!r}"
            )
            return None
        name = entry[rules.condition_key]
        if not isinstance(name, str) or not name:
            reasons.append(
                f"{label}.{rules.conditions_key}[{index}].{rules.condition_key} "
                "must be a non-empty string"
            )
            return None
        names.append(name)
    return names


def _trial_ids(
    document: Mapping[str, Any], protocol: Protocol, label: str, reasons: list[str]
) -> list[tuple[Any, ...]] | None:
    rules = protocol.structural_rules
    trials = document.get(rules.trials_key)
    if not isinstance(trials, list):
        return None
    ids: list[tuple[Any, ...]] = []
    for index, entry in enumerate(trials):
        if not isinstance(entry, Mapping):
            reasons.append(f"{label}.{rules.trials_key}[{index}] must be an object")
            return None
        for key in rules.required_trial_keys:
            if key not in entry:
                reasons.append(
                    f"{label}.{rules.trials_key}[{index}] is missing required key {key!r}"
                )
                return None
        try:
            trial_id = tuple(entry[key] for key in rules.trial_key)
        except KeyError:
            reasons.append(
                f"{label}.{rules.trials_key}[{index}] is missing a trial key field"
            )
            return None
        if any(isinstance(value, (dict, list)) for value in trial_id):
            reasons.append(
                f"{label}.{rules.trials_key}[{index}] trial key fields must be scalars"
            )
            return None
        ids.append(trial_id)
    return ids


def _find_nonfinite(value: Any, path: str = "") -> str | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            found = _find_nonfinite(item, f"{path}.{key}" if path else str(key))
            if found is not None:
                return found
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found = _find_nonfinite(item, f"{path}[{index}]")
            if found is not None:
                return found
    elif isinstance(value, float) and not math.isfinite(value):
        return path or "$"
    return None


def _normalized(document: Mapping[str, Any], protocol: Protocol) -> Mapping[str, Any]:
    rules = protocol.structural_rules
    normalized = copy.deepcopy(document)
    conditions = normalized.get(rules.conditions_key)
    trials = normalized.get(rules.trials_key)
    if not isinstance(conditions, list) or not isinstance(trials, list):
        return normalized
    order = {
        entry.get(rules.condition_key): index
        for index, entry in enumerate(conditions)
        if isinstance(entry, Mapping)
    }
    trials.sort(
        key=lambda entry: (
            order.get(entry.get(rules.condition_key), len(order)),
            tuple(_order_value(entry.get(key)) for key in rules.trial_key),
        )
    )
    return normalized


def _order_value(value: Any) -> tuple[int, Any]:
    if isinstance(value, bool):
        return (0, int(value))
    if isinstance(value, int):
        return (1, value)
    if isinstance(value, float):
        return (2, repr(value))
    if isinstance(value, str):
        return (3, value)
    return (4, 0)


def _ignored_present(document: Mapping[str, Any], protocol: Protocol) -> list[str]:
    found: list[str] = []
    for pattern in protocol.ignored_fields:
        for match in resolve(document, pattern):
            found.append(match.path or pattern)
    return found


def _remove_ignored(
    document: Mapping[str, Any], protocol: Protocol
) -> Mapping[str, Any]:
    cleaned = copy.deepcopy(document)
    for pattern in protocol.ignored_fields:
        paths = [match.path for match in resolve(cleaned, pattern)]
        for path in sorted(paths, key=delete_order, reverse=True):
            delete_concrete(cleaned, path)
    return cleaned


def _classification_sets(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    protocol: Protocol,
) -> tuple[dict[str, tuple[int, int]], dict[str, tuple[NumericField, tuple[int, int]]]]:
    exact_paths: dict[str, tuple[int, int]] = {}
    for pattern in protocol.exact_fields:
        specificity = path_specificity(pattern)
        for document in (reference, candidate):
            for match in resolve(document, pattern):
                for concrete in flatten(match.value, match.path):
                    current = exact_paths.get(concrete)
                    if current is None or specificity > current:
                        exact_paths[concrete] = specificity

    numeric_map: dict[str, tuple[NumericField, tuple[int, int]]] = {}
    for entry in protocol.numeric_fields:
        specificity = path_specificity(entry.path)
        for document in (reference, candidate):
            for match in resolve(document, entry.path):
                for concrete in flatten(match.value, match.path):
                    current = numeric_map.get(concrete)
                    if current is None or specificity > current[1]:
                        numeric_map[concrete] = (entry, specificity)
    return exact_paths, numeric_map


def _is_numeric_or_null(value: Any) -> bool:
    return value is None or (
        isinstance(value, (int, float)) and not isinstance(value, bool)
    )


def _compare_numeric(
    path: str,
    reference_value: Any,
    candidate_value: Any,
    entry: NumericField,
    reference_document: Mapping[str, Any],
    candidate_document: Mapping[str, Any],
    stats: dict[str, Any],
) -> dict[str, Any] | None:
    location = _location(path, reference_document, candidate_document)
    stats["compared"] += 1
    if reference_value is None or candidate_value is None:
        if reference_value is None and candidate_value is None:
            return None
        stats["violations"] += 1
        stats["worst_location"] = location
        return {
            "kind": "numeric",
            "field": entry.path,
            "path": path,
            "location": location,
            "reference": _jsonable(reference_value),
            "candidate": _jsonable(candidate_value),
            "abs_error": None,
            "rel_error": None,
            "abs_tol": entry.abs_tol,
            "rel_tol": entry.rel_tol,
            "reason": "null mismatch",
        }
    reference_number = float(reference_value)
    candidate_number = float(candidate_value)
    absolute_error = abs(reference_number - candidate_number)
    scale = max(abs(reference_number), abs(candidate_number))
    relative_error = absolute_error / scale if scale > 0.0 else 0.0
    if stats["max_abs"] is None or absolute_error > stats["max_abs"]:
        stats["max_abs"] = absolute_error
    if stats["max_rel"] is None or relative_error > stats["max_rel"]:
        stats["max_rel"] = relative_error
    passed = absolute_error <= entry.abs_tol + entry.rel_tol * scale
    if passed:
        return None
    stats["violations"] += 1
    stats["worst_location"] = location
    return {
        "kind": "numeric",
        "field": entry.path,
        "path": path,
        "location": location,
        "reference": _jsonable(reference_value),
        "candidate": _jsonable(candidate_value),
        "abs_error": absolute_error,
        "rel_error": relative_error,
        "abs_tol": entry.abs_tol,
        "rel_tol": entry.rel_tol,
    }


def _exact_equal(reference: Any, candidate: Any) -> bool:
    if isinstance(reference, bool) or isinstance(candidate, bool):
        return isinstance(reference, bool) and isinstance(candidate, bool) and reference == candidate
    if isinstance(reference, (int, float)) or isinstance(candidate, (int, float)):
        if not isinstance(reference, (int, float)) or not isinstance(candidate, (int, float)):
            return False
        if isinstance(reference, bool) or isinstance(candidate, bool):
            return False
        return type(reference) is type(candidate) and reference == candidate
    if type(reference) is not type(candidate):
        return False
    if isinstance(reference, Mapping):
        if set(reference) != set(candidate):
            return False
        return all(_exact_equal(reference[key], candidate[key]) for key in reference)
    if isinstance(reference, list):
        if len(reference) != len(candidate):
            return False
        return all(
            _exact_equal(left, right) for left, right in zip(reference, candidate)
        )
    return reference == candidate


def _decision_instability(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    protocol: Protocol,
    numeric_violations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    violating_trials = set()
    for violation in numeric_violations:
        trial_index = _trial_index(violation["path"])
        if trial_index is not None:
            violating_trials.add(trial_index)

    findings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pattern in protocol.decision_instability.decision_fields:
        reference_matches = {match.path: match.value for match in resolve(reference, pattern)}
        candidate_matches = {match.path: match.value for match in resolve(candidate, pattern)}
        for path in sorted(set(reference_matches) & set(candidate_matches)):
            if _exact_equal(reference_matches[path], candidate_matches[path]):
                continue
            trial_index = _trial_index(path)
            if trial_index is None:
                continue
            if trial_index in violating_trials:
                continue
            key = f"{path}|{pattern}"
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                {
                    "path": path,
                    "location": _location(path, reference, candidate),
                    "decision_field": pattern,
                    "reference": _jsonable(reference_matches[path]),
                    "candidate": _jsonable(candidate_matches[path]),
                    "numeric_fields_within_tolerance": True,
                }
            )
    return sorted(findings, key=lambda item: item["path"])


def _trial_index(path: str) -> int | None:
    match = _TRIAL_PATH.match(path)
    return int(match.group(1)) if match is not None else None


def _location(
    path: str,
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> str:
    trial = _TRIAL_PATH.match(path)
    if trial is not None:
        index = int(trial.group(1))
        document = reference if _trial_exists(reference, index) else candidate
        trials = document.get("trials")
        if isinstance(trials, list) and index < len(trials) and isinstance(trials[index], Mapping):
            record = trials[index]
            condition = record.get("condition")
            trial_number = record.get("trial")
            if condition is not None and trial_number is not None:
                remainder = path.split("]", 1)[1].lstrip(".")
                return (
                    f"condition={condition} trial={trial_number} field={remainder or path}"
                )
    condition = _CONDITION_PATH.match(path)
    if condition is not None:
        index = int(condition.group(1))
        document = reference if _condition_exists(reference, index) else candidate
        conditions = document.get("conditions")
        if (
            isinstance(conditions, list)
            and index < len(conditions)
            and isinstance(conditions[index], Mapping)
            and conditions[index].get("condition") is not None
        ):
            remainder = path.split("]", 1)[1].lstrip(".")
            return f"condition={conditions[index]['condition']} field={remainder or path}"
    return f"field={path}"


def _trial_exists(document: Mapping[str, Any], index: int) -> bool:
    trials = document.get("trials")
    return isinstance(trials, list) and index < len(trials)


def _condition_exists(document: Mapping[str, Any], index: int) -> bool:
    conditions = document.get("conditions")
    return isinstance(conditions, list) and index < len(conditions)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return repr(value)


class UsageError(ValueError):
    """Raised for command-line/protocol usage errors."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # noqa: D401 - argparse hook
        raise UsageError(message)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0/1/2/3 per the documented contract."""
    parser = _Parser(
        prog="python -m phaino_verify.compare",
        description="Compare two experiment artifacts under a comparison protocol.",
    )
    parser.add_argument("reference")
    parser.add_argument("candidate")
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument(
        "--require",
        choices=("R1", "R1-N", "R1-D", "both", "R2"),
        default="R1",
    )
    try:
        args = parser.parse_args(argv)
    except UsageError as error:
        print(f"usage error: {error}", file=sys.stderr)
        return 3

    try:
        protocol = load_protocol(args.protocol)
    except (ProtocolError, OSError) as error:
        print(f"protocol error: {error}", file=sys.stderr)
        return 3

    try:
        reference = load_artifact(args.reference)
        candidate = load_artifact(args.candidate)
    except ArtifactError as error:
        report = Report.unknown(
            protocol,
            _failed_descriptor(args.reference),
            _failed_descriptor(args.candidate),
            [str(error)],
        )
        if not _write_report(report, args.report):
            return 3
        print("classification: unknown")
        print(f"reason: {error}")
        print(f"report: {args.report}")
        return 2

    report = compare_artifacts(reference, candidate, protocol)
    if not _write_report(report, args.report):
        return 3
    print(f"classification: {report.classification}")
    print(f"r1_n: {report.r1_n}")
    print(f"r1_d: {report.r1_d}")
    print(f"reproduction_level: {report.reproduction_level}")
    required = _required_passes(report, args.require)
    print(f"required {args.require}: {'pass' if required else 'fail'}")
    print(f"report: {args.report}")
    if report.classification == "unknown":
        return 2
    return 0 if required else 1


def _required_passes(report: Report, target: str) -> bool:
    if report.contract_version == 2:
        r1_n = report.r1_n is True
        r1_d = report.r1_d is True
        if target in {"R1", "both"}:
            return r1_n and r1_d
        if target == "R1-N":
            return r1_n
        if target == "R1-D":
            return r1_d
        return report.levels["r2_bitwise_identity"]
    if target == "R2":
        return report.levels["r2_bitwise_identity"]
    return report.levels["r1_numerical_equivalence"]


def _failed_descriptor(path: str) -> dict[str, Any]:
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return {"path": path, "raw_sha256": None, "decoded_sha256": None, "canonical_sha256": None}
    return {
        "path": path,
        "raw_sha256": sha256_bytes(raw),
        "decoded_sha256": None,
        "canonical_sha256": None,
    }


def _write_report(report: Report, path: str) -> bool:
    try:
        Path(path).write_text(report.to_json(), encoding="utf-8")
    except OSError as error:
        print(f"report error: {error}", file=sys.stderr)
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
