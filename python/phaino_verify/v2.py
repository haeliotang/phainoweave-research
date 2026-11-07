"""Contract-v2 comparison: classed fields, identifiability gating, decision margins.

R1 is split into two reported targets. R1-N applies A exactness and B numeric tolerance
only to trials the protocol's fixed reference-side identifiability rule marks identifiable.
R1-D evaluates D-class decisions with declared margins, records every indeterminate
decision without rewriting its raw value, and fails on material condition-level rate
changes. C-class diagnostics are compared semantically and never fail R1.
"""

from __future__ import annotations

import copy
import math
from typing import Any, Mapping

from phaino_sdk.canonical import canonical_sha256

from .artifacts import Artifact
from .compare import (
    Report,
    _artifact_descriptor,
    _check_structure,
    _exact_equal,
    _find_nonfinite,
    _ignored_present,
    _location,
    _normalized,
    _protocol_descriptor,
    _remove_ignored,
)
from .paths import flatten, path_specificity, resolve
from .protocol import (
    DecisionSpec,
    DiagnosticField,
    FieldSpec,
    IdentifiabilityRule,
    ProtocolV2,
)

MISSING = object()
DIAGNOSTIC_DIFFERENCE_LIMIT = 2000


def compare_v2(
    reference: Artifact,
    candidate: Artifact,
    protocol: ProtocolV2,
) -> Report:
    """Compares two artifacts under a contract-v2 protocol."""
    reference_document = reference.document
    candidate_document = candidate.document
    reasons: list[str] = []
    structure_ok = _check_structure(
        reference_document, candidate_document, protocol, reasons
    )

    ignored_found: list[str] = []
    canonical_reference: str | None = None
    canonical_candidate: str | None = None
    r2 = False
    if structure_ok:
        try:
            ignored_found = sorted(
                set(_ignored_present(reference_document, protocol))
                | set(_ignored_present(candidate_document, protocol))
            )
            canonical_reference = canonical_sha256(
                _remove_ignored(reference_document, protocol)
            )
            canonical_candidate = canonical_sha256(
                _remove_ignored(candidate_document, protocol)
            )
            r2 = canonical_reference == canonical_candidate
        except (ValueError, TypeError) as error:
            reasons.append(f"cannot canonicalize artifacts: {error}")
            structure_ok = False

    levels = {
        "r0_execution": structure_ok,
        "r1_numerical_equivalence": False,
        "r1_decision_equivalence": False,
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
            contract_version=2,
            r1_n=False,
            r1_d=False,
            reproduction_level="none",
        )

    normalized_reference = _normalized(reference_document, protocol)
    normalized_candidate = _normalized(candidate_document, protocol)
    clean_reference = _remove_ignored(normalized_reference, protocol)
    clean_candidate = _remove_ignored(normalized_candidate, protocol)

    rules = protocol.structural_rules
    reference_trials = _trials(clean_reference, rules.trials_key)
    candidate_trials = _trials(clean_candidate, rules.trials_key)
    reference_conditions = _conditions(clean_reference, rules.conditions_key)
    candidate_conditions = _conditions(clean_candidate, rules.conditions_key)

    identifiability, identifiable_flags, identifiability_summary = _identifiability(
        reference_trials, protocol.identifiability, rules
    )
    identifiable_count = sum(1 for flag in identifiable_flags if flag)
    condition_identifiable = _condition_identifiability(
        reference_trials, identifiable_flags, reference_conditions, rules
    )

    violations: list[dict[str, Any]] = []
    exact_violations: list[dict[str, Any]] = []
    numeric_violations: list[dict[str, Any]] = []

    reference_leaves = flatten(clean_reference)
    candidate_leaves = flatten(clean_candidate)

    a_covered = _compare_a(
        clean_reference,
        clean_candidate,
        protocol,
        violations,
        exact_violations,
    )
    b_stats, b_covered, b_applicable = _compare_b(
        clean_reference,
        clean_candidate,
        reference_leaves,
        candidate_leaves,
        protocol,
        identifiable_flags,
        condition_identifiable,
        reference_conditions,
        reference_trials,
        rules,
        violations,
        numeric_violations,
    )
    c_summary, c_covered, diagnostic_differences = _compare_c(
        clean_reference,
        clean_candidate,
        reference_leaves,
        candidate_leaves,
        protocol,
        violations,
    )

    decision_summary, decision_changes, decision_instability, consistency_failures = (
        _compare_decisions(
            clean_reference,
            clean_candidate,
            reference_trials,
            candidate_trials,
            protocol,
            rules,
        )
    )
    rate_changes, rate_material = _compare_rates(
        clean_reference,
        clean_candidate,
        protocol,
        rules,
        reference_conditions,
    )

    d_covered = _decision_covered_paths(clean_reference, clean_candidate, protocol)
    rate_covered = _rate_covered_paths(clean_reference, clean_candidate, protocol)
    unclassified_fields, unclassified_violations = _compare_unclassified(
        reference_leaves,
        candidate_leaves,
        clean_reference,
        clean_candidate,
        protocol,
        a_covered | b_covered | c_covered | d_covered | rate_covered,
    )
    violations.extend(unclassified_violations)

    r1_n: bool | None
    if violations:
        r1_n = False
    elif identifiable_count == 0 or b_applicable == 0:
        r1_n = None
        reasons.append("no identifiable trials with B-class evidence; R1-N not applicable")
    else:
        r1_n = True

    rejected_decisions = sum(
        entry["rejected"] for entry in decision_summary
    )
    indeterminate_decisions = sum(
        entry["indeterminate"] for entry in decision_summary
    )
    r1_d = (
        rejected_decisions == 0 and not rate_material and not consistency_failures
    )

    levels["r1_numerical_equivalence"] = r1_n is True
    levels["r1_decision_equivalence"] = r1_d

    if r2:
        classification = "exact"
    elif r1_n is True and r1_d:
        classification = "numerically_equivalent"
    elif r1_n is False or not r1_d:
        classification = "mismatch"
    else:
        classification = "unknown"
        reasons.append("insufficient applicable numeric evidence for a reproduction claim")

    if r2:
        reproduction_level = "R2"
    elif r1_n is True and r1_d:
        reproduction_level = "R1-N+R1-D"
    elif r1_n is True:
        reproduction_level = "R1-N only"
    else:
        reproduction_level = "R0 only"

    identifiability_summary.update(
        {
            "identifiable_trials": identifiable_count,
            "unidentifiable_trials": len(identifiable_flags) - identifiable_count,
        }
    )
    if r1_n is None:
        reasons.append("R1-N has no identifiable trial to evaluate")

    return Report(
        protocol=_protocol_descriptor(protocol),
        reference=reference_descriptor,
        candidate=candidate_descriptor,
        levels=levels,
        classification=classification,
        per_field_stats=b_stats,
        exact_violations=sorted(exact_violations, key=lambda item: item["path"]),
        numeric_violations=sorted(numeric_violations, key=lambda item: item["path"]),
        violations=sorted(violations, key=lambda item: (item["path"], item["kind"])),
        decision_instability=decision_instability,
        ignored_fields_found=ignored_found,
        reasons=sorted(set(reasons)),
        contract_version=2,
        r1_n=r1_n,
        r1_d=r1_d,
        reproduction_level=reproduction_level,
        identifiability=identifiability,
        identifiability_summary=identifiability_summary,
        decision_summary=decision_summary,
        decision_changes=decision_changes,
        rate_changes=rate_changes,
        classification_inconsistencies=consistency_failures,
        unidentifiable_numeric=[],
        diagnostic_summary=c_summary,
        diagnostic_differences=diagnostic_differences,
        unclassified_fields=sorted(set(unclassified_fields)),
    )


# ---------------------------------------------------------------------------
# Identifiability
# ---------------------------------------------------------------------------

def _identifiability(
    trials: list[Mapping[str, Any]],
    rule: IdentifiabilityRule,
    rules: Any,
) -> tuple[list[dict[str, Any]], list[bool], dict[str, Any]]:
    details: list[dict[str, Any]] = []
    flags: list[bool] = []
    failed_counts: dict[str, int] = {}
    for trial in trials:
        failed: list[str] = []
        for clause in rule.all_of:
            matches = resolve(trial, clause.field)
            value = matches[0].value if len(matches) == 1 else MISSING
            if not _identifiability_clause(value, clause):
                failed.append(clause.field)
                failed_counts[clause.field] = failed_counts.get(clause.field, 0) + 1
        identifiable = not failed
        flags.append(identifiable)
        details.append(
            {
                "condition": trial.get(rules.condition_key),
                "trial": _trial_number(trial, rules),
                "identifiable": identifiable,
                "r1_n_status": "applicable" if identifiable else "not_applicable",
                "failed_checks": failed,
            }
        )
    summary = {
        "rule_id": rule.rule_id,
        "total_trials": len(trials),
        "failed_check_counts": dict(sorted(failed_counts.items())),
    }
    return details, flags, summary


def _identifiability_clause(value: Any, clause: Any) -> bool:
    check = clause.check
    if value is MISSING or value is None:
        return check == "not_null" and value is not MISSING
    if check == "true":
        return value is True
    if check == "false":
        return value is False
    if check == "all_finite":
        if isinstance(value, Mapping):
            leaves = flatten(value)
            return bool(leaves) and all(
                isinstance(item, (int, float))
                and not isinstance(item, bool)
                and math.isfinite(float(item))
                for item in leaves.values()
            )
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(
            float(value)
        )
    if check == "not_null":
        return True
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    numeric = float(value)
    if not math.isfinite(numeric):
        return False
    threshold = clause.value
    if threshold is None:
        return False
    if check == "lt":
        return numeric < threshold
    if check == "le":
        return numeric <= threshold
    if check == "gt":
        return numeric > threshold
    if check == "ge":
        return numeric >= threshold
    return False


def _condition_identifiability(
    trials: list[Mapping[str, Any]],
    flags: list[bool],
    conditions: list[Mapping[str, Any]],
    rules: Any,
) -> dict[str, bool]:
    by_condition: dict[str, list[bool]] = {
        condition.get(rules.condition_key): [] for condition in conditions
    }
    for trial, flag in zip(trials, flags):
        name = trial.get(rules.condition_key)
        if name in by_condition:
            by_condition[name].append(flag)
    return {name: bool(values) and all(values) for name, values in by_condition.items()}


# ---------------------------------------------------------------------------
# A / B / C field classes
# ---------------------------------------------------------------------------

def _compare_a(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    protocol: ProtocolV2,
    violations: list[dict[str, Any]],
    exact_violations: list[dict[str, Any]],
) -> set[str]:
    covered: set[str] = set()
    for pattern in protocol.a_fields:
        reference_values: dict[str, Any] = {}
        candidate_values: dict[str, Any] = {}
        for match in resolve(reference, pattern):
            for path, value in flatten(match.value, match.path).items():
                reference_values[path] = value
                covered.add(path)
        for match in resolve(candidate, pattern):
            for path, value in flatten(match.value, match.path).items():
                candidate_values[path] = value
                covered.add(path)
        for path in sorted(set(reference_values) | set(candidate_values)):
            in_reference = path in reference_values
            in_candidate = path in candidate_values
            if not in_reference or not in_candidate:
                violation = {
                    "kind": "missing" if not in_reference else "extra",
                    "class": "A",
                    "path": path,
                    "location": _location(path, reference, candidate),
                    "reference": _jsonable(reference_values.get(path)) if in_reference else None,
                    "candidate": _jsonable(candidate_values.get(path)) if in_candidate else None,
                }
                violations.append(violation)
                continue
            if _exact_equal(reference_values[path], candidate_values[path]):
                continue
            violation = {
                "kind": "exact",
                "class": "A",
                "path": path,
                "location": _location(path, reference, candidate),
                "reference": _jsonable(reference_values[path]),
                "candidate": _jsonable(candidate_values[path]),
            }
            violations.append(violation)
            exact_violations.append(violation)
    return covered


def _compare_b(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    reference_leaves: dict[str, Any],
    candidate_leaves: dict[str, Any],
    protocol: ProtocolV2,
    identifiable_flags: list[bool],
    condition_identifiable: dict[str, bool],
    conditions: list[Mapping[str, Any]],
    trials: list[Mapping[str, Any]],
    rules: Any,
    violations: list[dict[str, Any]],
    numeric_violations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], set[str], int]:
    entries: dict[str, tuple[FieldSpec, tuple[int, int]]] = {}
    covered: set[str] = set()
    for spec in protocol.b_fields:
        specificity = path_specificity(spec.path)
        for document in (reference, candidate):
            for match in resolve(document, spec.path):
                for path in flatten(match.value, match.path):
                    covered.add(path)
                    current = entries.get(path)
                    if current is None or specificity > current[1]:
                        entries[path] = (spec, specificity)

    stats = {
        spec.path: {
            "field": spec.path,
            "class": "B",
            "scope": spec.scope,
            "abs_tol": spec.abs_tol,
            "rel_tol": spec.rel_tol,
            "applicable_compared": 0,
            "applicable_violations": 0,
            "not_applicable_compared": 0,
            "max_abs": None,
            "max_rel": None,
            "worst_location": None,
            "not_applicable_max_abs": None,
            "not_applicable_max_rel": None,
            "not_applicable_example": None,
        }
        for spec in protocol.b_fields
    }
    applicable = 0
    for path in sorted(entries):
        spec = entries[path][0]
        stats_entry = stats[spec.path]
        is_applicable = _b_applicable(
            path, spec, identifiable_flags, condition_identifiable, conditions, trials, rules
        )
        in_reference = path in reference_leaves
        in_candidate = path in candidate_leaves
        if not is_applicable:
            stats_entry["not_applicable_compared"] += 1
            if in_reference and in_candidate:
                reference_value = reference_leaves[path]
                candidate_value = candidate_leaves[path]
                if _is_numeric(reference_value) and _is_numeric(candidate_value):
                    absolute_error = abs(float(reference_value) - float(candidate_value))
                    scale = max(abs(float(reference_value)), abs(float(candidate_value)))
                    relative_error = absolute_error / scale if scale > 0.0 else 0.0
                    if (
                        stats_entry["not_applicable_max_abs"] is None
                        or absolute_error > stats_entry["not_applicable_max_abs"]
                    ):
                        stats_entry["not_applicable_max_abs"] = absolute_error
                        stats_entry["not_applicable_max_rel"] = relative_error
                        stats_entry["not_applicable_example"] = _location(
                            path, reference, candidate
                        )
            continue
        applicable += 1
        stats_entry["applicable_compared"] += 1
        if not in_reference or not in_candidate:
            violation = {
                "kind": "missing" if not in_reference else "extra",
                "class": "B",
                "field": spec.path,
                "path": path,
                "location": _location(path, reference, candidate),
                "reference": _jsonable(reference_leaves.get(path)) if in_reference else None,
                "candidate": _jsonable(candidate_leaves.get(path)) if in_candidate else None,
            }
            violations.append(violation)
            numeric_violations.append(violation)
            stats_entry["applicable_violations"] += 1
            stats_entry["worst_location"] = violation["location"]
            continue
        reference_value = reference_leaves[path]
        candidate_value = candidate_leaves[path]
        location = _location(path, reference, candidate)
        if not _is_numeric(reference_value) or not _is_numeric(candidate_value):
            if _exact_equal(reference_value, candidate_value):
                continue
            violation = {
                "kind": "type",
                "class": "B",
                "field": spec.path,
                "path": path,
                "location": location,
                "reference": _jsonable(reference_value),
                "candidate": _jsonable(candidate_value),
            }
            violations.append(violation)
            numeric_violations.append(violation)
            stats_entry["applicable_violations"] += 1
            stats_entry["worst_location"] = location
            continue
        reference_number = float(reference_value)
        candidate_number = float(candidate_value)
        absolute_error = abs(reference_number - candidate_number)
        scale = max(abs(reference_number), abs(candidate_number))
        relative_error = absolute_error / scale if scale > 0.0 else 0.0
        if stats_entry["max_abs"] is None or absolute_error > stats_entry["max_abs"]:
            stats_entry["max_abs"] = absolute_error
            stats_entry["max_rel"] = relative_error
            stats_entry["worst_location"] = location
        passed = absolute_error <= spec.abs_tol + spec.rel_tol * scale
        if passed:
            continue
        violation = {
            "kind": "numeric",
            "class": "B",
            "field": spec.path,
            "path": path,
            "location": location,
            "reference": _jsonable(reference_value),
            "candidate": _jsonable(candidate_value),
            "abs_error": absolute_error,
            "rel_error": relative_error,
            "abs_tol": spec.abs_tol,
            "rel_tol": spec.rel_tol,
        }
        violations.append(violation)
        numeric_violations.append(violation)
        stats_entry["applicable_violations"] += 1
        stats_entry["worst_location"] = location
    return (
        sorted(stats.values(), key=lambda item: item["field"]),
        covered,
        applicable,
    )


def _b_applicable(
    path: str,
    spec: FieldSpec,
    identifiable_flags: list[bool],
    condition_identifiable: dict[str, bool],
    conditions: list[Mapping[str, Any]],
    trials: list[Mapping[str, Any]],
    rules: Any,
) -> bool:
    if spec.scope == "condition":
        index = _index_for(path, "conditions")
        if index is None or index >= len(conditions):
            return False
        name = conditions[index].get(rules.condition_key)
        return bool(condition_identifiable.get(name, False))
    index = _index_for(path, "trials")
    if index is None or index >= len(identifiable_flags):
        return True
    return identifiable_flags[index]


def _compare_c(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    reference_leaves: dict[str, Any],
    candidate_leaves: dict[str, Any],
    protocol: ProtocolV2,
    violations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], set[str], list[dict[str, Any]]]:
    entries: dict[str, tuple[DiagnosticField, tuple[int, int]]] = {}
    covered: set[str] = set()
    for spec in protocol.c_fields:
        specificity = path_specificity(spec.path)
        for document in (reference, candidate):
            for match in resolve(document, spec.path):
                for path in flatten(match.value, match.path):
                    covered.add(path)
                    current = entries.get(path)
                    if current is None or specificity > current[1]:
                        entries[path] = (spec, specificity)

    stats = {
        spec.path: {
            "field": spec.path,
            "class": "C",
            "semantics": spec.semantics,
            "compared": 0,
            "disagreements": 0,
            "max_abs": None,
            "max_rel": None,
        }
        for spec in protocol.c_fields
    }
    differences: list[dict[str, Any]] = []
    total_disagreements = 0
    for path in sorted(entries):
        spec = entries[path][0]
        stats_entry = stats[spec.path]
        stats_entry["compared"] += 1
        in_reference = path in reference_leaves
        in_candidate = path in candidate_leaves
        if not in_reference or not in_candidate:
            total_disagreements += 1
            stats_entry["disagreements"] += 1
            if len(differences) < DIAGNOSTIC_DIFFERENCE_LIMIT:
                differences.append(
                    {
                        "kind": "diagnostic",
                        "field": spec.path,
                        "path": path,
                        "location": _location(path, reference, candidate),
                        "reference": _jsonable(reference_leaves.get(path)) if in_reference else None,
                        "candidate": _jsonable(candidate_leaves.get(path)) if in_candidate else None,
                        "reason": "missing",
                    }
                )
            continue
        reference_value = reference_leaves[path]
        candidate_value = candidate_leaves[path]
        if _is_numeric(reference_value) and _is_numeric(candidate_value):
            absolute_error = abs(float(reference_value) - float(candidate_value))
            scale = max(abs(float(reference_value)), abs(float(candidate_value)))
            relative_error = absolute_error / scale if scale > 0.0 else 0.0
            if stats_entry["max_abs"] is None or absolute_error > stats_entry["max_abs"]:
                stats_entry["max_abs"] = absolute_error
                stats_entry["max_rel"] = relative_error
        agree, why = _diagnostic_agrees(reference_value, candidate_value, spec)
        if agree:
            continue
        total_disagreements += 1
        stats_entry["disagreements"] += 1
        if len(differences) < DIAGNOSTIC_DIFFERENCE_LIMIT:
            differences.append(
                {
                    "kind": "diagnostic",
                    "field": spec.path,
                    "path": path,
                    "location": _location(path, reference, candidate),
                    "reference": _jsonable(reference_value),
                    "candidate": _jsonable(candidate_value),
                    "reason": why,
                }
            )
    summary = sorted(stats.values(), key=lambda item: item["field"])
    for entry in summary:
        entry["disagreements_total"] = entry["disagreements"]
    return summary, covered, differences


def _diagnostic_agrees(
    reference_value: Any, candidate_value: Any, spec: DiagnosticField
) -> tuple[bool, str | None]:
    if reference_value is None and candidate_value is None:
        return True, None
    if reference_value is None or candidate_value is None:
        return False, "null_mismatch"
    if spec.semantics != "magnitude_class":
        return _exact_equal(reference_value, candidate_value), "unsupported_semantics"
    if not _is_numeric(reference_value) or not _is_numeric(candidate_value):
        return _exact_equal(reference_value, candidate_value), "non_numeric"
    reference_number = float(reference_value)
    candidate_number = float(candidate_value)
    if spec.sign_sensitive and (
        (reference_number < 0.0) != (candidate_number < 0.0)
        and reference_number != 0.0
        and candidate_number != 0.0
    ):
        return False, "sign_mismatch"
    if reference_number == 0.0 or candidate_number == 0.0:
        return (reference_number == 0.0 and candidate_number == 0.0), "zero_mismatch"
    reference_class = math.floor(math.log10(abs(reference_number)))
    candidate_class = math.floor(math.log10(abs(candidate_number)))
    if abs(reference_class - candidate_class) <= spec.decades:
        return True, None
    return False, "magnitude_class"


# ---------------------------------------------------------------------------
# D decisions and rates
# ---------------------------------------------------------------------------

def _compare_decisions(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    reference_trials: list[Mapping[str, Any]],
    candidate_trials: list[Mapping[str, Any]],
    protocol: ProtocolV2,
    rules: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    summary: dict[str, dict[str, Any]] = {
        spec.name: {
            "decision": spec.name,
            "kind": spec.kind,
            "accepted": 0,
            "rejected": 0,
            "indeterminate": 0,
        }
        for spec in protocol.decisions
    }
    changes: list[dict[str, Any]] = []
    instability: list[dict[str, Any]] = []
    inconsistencies: list[dict[str, Any]] = []
    for index, (reference_trial, candidate_trial) in enumerate(
        zip(reference_trials, candidate_trials)
    ):
        statuses: dict[str, str] = {}
        raw_values: dict[str, tuple[Any, Any]] = {}
        for spec in protocol.decisions:
            status, reference_raw, candidate_raw, reference_stat, candidate_stat = _evaluate_decision(
                spec, reference_trial, candidate_trial, statuses
            )
            summary[spec.name][status] += 1
            statuses[spec.name] = status
            raw_values[spec.name] = (reference_raw, candidate_raw)
            if spec.kind == "derived":
                expected_reference = _derived_expected(spec, raw_values, reference_trial, 0)
                expected_candidate = _derived_expected(spec, raw_values, candidate_trial, 1)
                if (
                    isinstance(reference_raw, bool)
                    and isinstance(candidate_raw, bool)
                    and (
                        reference_raw != expected_reference
                        or candidate_raw != expected_candidate
                    )
                ):
                    inconsistencies.append(
                        {
                            "decision": spec.name,
                            "condition": reference_trial.get(rules.condition_key),
                            "trial": _trial_number(reference_trial, rules),
                            "reference_raw": reference_raw,
                            "candidate_raw": candidate_raw,
                            "expected_reference": expected_reference,
                            "expected_candidate": expected_candidate,
                        }
                    )
            if status == "accepted" and reference_raw == candidate_raw:
                continue
            entry = {
                "decision": spec.name,
                "path": spec.path,
                "kind": spec.kind,
                "status": status,
                "condition": reference_trial.get(rules.condition_key),
                "trial": _trial_number(reference_trial, rules),
                "location": _decision_location(reference_trial, rules, spec),
                "reference_raw": _jsonable(reference_raw),
                "candidate_raw": _jsonable(candidate_raw),
                "reference_statistic": _jsonable(reference_stat),
                "candidate_statistic": _jsonable(candidate_stat),
                "threshold": spec.threshold,
                "margin": spec.margin,
                "comparison": spec.comparison,
                "justification": spec.justification,
            }
            changes.append(entry)
            if status == "indeterminate" and reference_raw != candidate_raw:
                instability.append(copy.deepcopy(entry))
    return (
        sorted(summary.values(), key=lambda item: item["decision"]),
        sorted(changes, key=lambda item: (item["trial"], item["decision"])),
        sorted(instability, key=lambda item: (item["trial"], item["decision"])),
        inconsistencies,
    )


def _evaluate_decision(
    spec: DecisionSpec,
    reference_trial: Mapping[str, Any],
    candidate_trial: Mapping[str, Any],
    statuses: dict[str, str],
) -> tuple[str, Any, Any, Any, Any]:
    reference_raw = _trial_field(reference_trial, spec.path)
    candidate_raw = _trial_field(candidate_trial, spec.path)
    if spec.kind == "exact":
        if not isinstance(reference_raw, bool) or not isinstance(candidate_raw, bool):
            return "indeterminate", reference_raw, candidate_raw, None, None
        return (
            "accepted" if reference_raw == candidate_raw else "rejected",
            reference_raw,
            candidate_raw,
            None,
            None,
        )
    if spec.kind == "derived":
        reference_stat = MISSING
        candidate_stat = MISSING
        if spec.statistic is not None:
            reference_stat = _trial_field(reference_trial, spec.statistic)
            candidate_stat = _trial_field(candidate_trial, spec.statistic)
            if not _threshold_decidable(
                spec, reference_stat, candidate_stat
            ):
                return (
                    "indeterminate",
                    reference_raw,
                    candidate_raw,
                    reference_stat,
                    candidate_stat,
                )
        if any(statuses.get(dependency) == "indeterminate" for dependency in spec.dependencies):
            return (
                "indeterminate",
                reference_raw,
                candidate_raw,
                reference_stat,
                candidate_stat,
            )
        if not isinstance(reference_raw, bool) or not isinstance(candidate_raw, bool):
            return (
                "indeterminate",
                reference_raw,
                candidate_raw,
                reference_stat,
                candidate_stat,
            )
        if any(statuses.get(dependency) == "rejected" for dependency in spec.dependencies):
            return (
                "rejected",
                reference_raw,
                candidate_raw,
                reference_stat,
                candidate_stat,
            )
        status = "accepted" if reference_raw == candidate_raw else "rejected"
        return status, reference_raw, candidate_raw, reference_stat, candidate_stat

    reference_stat = _trial_field(reference_trial, spec.statistic or "")
    candidate_stat = _trial_field(candidate_trial, spec.statistic or "")
    if not _threshold_decidable(spec, reference_stat, candidate_stat):
        return (
            "indeterminate",
            reference_raw,
            candidate_raw,
            reference_stat,
            candidate_stat,
        )
    if not isinstance(reference_raw, bool) or not isinstance(candidate_raw, bool):
        return (
            "indeterminate",
            reference_raw,
            candidate_raw,
            reference_stat,
            candidate_stat,
        )
    status = "accepted" if reference_raw == candidate_raw else "rejected"
    return status, reference_raw, candidate_raw, reference_stat, candidate_stat


def _threshold_decidable(spec: DecisionSpec, reference_stat: Any, candidate_stat: Any) -> bool:
    if not _is_numeric(reference_stat) or not _is_numeric(candidate_stat):
        return False
    threshold = spec.threshold
    margin = spec.margin or 0.0
    if threshold is None:
        return False
    distance_reference = _threshold_distance(spec.comparison, float(reference_stat), threshold)
    distance_candidate = _threshold_distance(spec.comparison, float(candidate_stat), threshold)
    return distance_reference > margin and distance_candidate > margin


def _threshold_distance(comparison: str | None, statistic: float, threshold: float) -> float:
    if comparison in {"abs_lt", "abs_le"}:
        return abs(abs(statistic) - threshold)
    return abs(statistic - threshold)


def _derived_expected(
    spec: DecisionSpec,
    raw_values: dict[str, tuple[Any, Any]],
    trial: Mapping[str, Any],
    side: int,
) -> bool | None:
    expected = True
    for dependency in spec.dependencies:
        values = raw_values.get(dependency, (None, None))
        raw = values[side]
        if not isinstance(raw, bool):
            return None
        expected = expected and raw
    if spec.statistic is not None and spec.threshold is not None:
        statistic = _trial_field(trial, spec.statistic)
        if not _is_numeric(statistic):
            return None
        passed = _threshold_passes(
            spec.comparison, float(statistic), spec.threshold
        )
        expected = expected and passed
    return expected


def _threshold_passes(comparison: str | None, statistic: float, threshold: float) -> bool:
    if comparison == "lt":
        return statistic < threshold
    if comparison == "le":
        return statistic <= threshold
    if comparison == "gt":
        return statistic > threshold
    if comparison == "ge":
        return statistic >= threshold
    if comparison == "abs_lt":
        return abs(statistic) < threshold
    if comparison == "abs_le":
        return abs(statistic) <= threshold
    return False


def _compare_rates(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    protocol: ProtocolV2,
    rules: Any,
    conditions: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    changes: list[dict[str, Any]] = []
    material_failure = False
    for check in protocol.rate_checks:
        reference_matches = {match.path: match.value for match in resolve(reference, check.path)}
        candidate_matches = {match.path: match.value for match in resolve(candidate, check.path)}
        for path in sorted(set(reference_matches) | set(candidate_matches)):
            if path not in reference_matches or path not in candidate_matches:
                material_failure = True
                changes.append(
                    {
                        "field": check.path,
                        "path": path,
                        "status": "unavailable",
                        "reference": _jsonable(reference_matches.get(path)),
                        "candidate": _jsonable(candidate_matches.get(path)),
                        "material_abs_change": check.material_abs_change,
                        "material": True,
                        "justification": check.justification,
                    }
                )
                continue
            reference_value = reference_matches[path]
            candidate_value = candidate_matches[path]
            if not _is_numeric(reference_value) or not _is_numeric(candidate_value):
                material_failure = True
                changes.append(
                    {
                        "field": check.path,
                        "path": path,
                        "status": "non_numeric",
                        "reference": _jsonable(reference_value),
                        "candidate": _jsonable(candidate_value),
                        "material_abs_change": check.material_abs_change,
                        "material": True,
                        "justification": check.justification,
                    }
                )
                continue
            delta = abs(float(reference_value) - float(candidate_value))
            material = delta > check.material_abs_change
            if delta == 0.0 and not material:
                continue
            material_failure = material_failure or material
            changes.append(
                {
                    "field": check.path,
                    "path": path,
                    "status": "material" if material else "within_margin",
                    "condition": _condition_for_path(path, conditions, rules),
                    "reference": _jsonable(reference_value),
                    "candidate": _jsonable(candidate_value),
                    "abs_delta": delta,
                    "material_abs_change": check.material_abs_change,
                    "material": material,
                    "justification": check.justification,
                }
            )
    return sorted(changes, key=lambda item: (item["field"], item["path"])), material_failure


# ---------------------------------------------------------------------------
# Coverage and small helpers
# ---------------------------------------------------------------------------

def _compare_unclassified(
    reference_leaves: dict[str, Any],
    candidate_leaves: dict[str, Any],
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    protocol: ProtocolV2,
    covered: set[str],
) -> tuple[list[str], list[dict[str, Any]]]:
    if protocol.unclassified_field_policy == "ignore":
        return [], []
    unclassified = sorted(
        (set(reference_leaves) | set(candidate_leaves)) - covered
    )
    violations: list[dict[str, Any]] = []
    for path in unclassified:
        in_reference = path in reference_leaves
        in_candidate = path in candidate_leaves
        if in_reference and in_candidate and _exact_equal(
            reference_leaves[path], candidate_leaves[path]
        ):
            continue
        violations.append(
            {
                "kind": "unclassified",
                "class": "unclassified",
                "path": path,
                "location": _location(path, reference, candidate),
                "reference": _jsonable(reference_leaves.get(path)) if in_reference else None,
                "candidate": _jsonable(candidate_leaves.get(path)) if in_candidate else None,
            }
        )
    return unclassified, violations


def _decision_covered_paths(
    reference: Mapping[str, Any], candidate: Mapping[str, Any], protocol: ProtocolV2
) -> set[str]:
    covered: set[str] = set()
    for spec in protocol.decisions:
        for document in (reference, candidate):
            for match in resolve(document, spec.path):
                covered.update(flatten(match.value, match.path))
    return covered


def _rate_covered_paths(
    reference: Mapping[str, Any], candidate: Mapping[str, Any], protocol: ProtocolV2
) -> set[str]:
    covered: set[str] = set()
    for check in protocol.rate_checks:
        for document in (reference, candidate):
            for match in resolve(document, check.path):
                covered.update(flatten(match.value, match.path))
    return covered


def _trial_field(trial: Mapping[str, Any], path: str) -> Any:
    prefix = "trials[]."
    if not path.startswith(prefix):
        return MISSING
    matches = resolve(trial, path[len(prefix) :])
    if len(matches) != 1:
        return MISSING
    return matches[0].value


def _decision_location(
    trial: Mapping[str, Any], rules: Any, spec: DecisionSpec
) -> str:
    condition = trial.get(rules.condition_key)
    trial_number = _trial_number(trial, rules)
    field = spec.path[len("trials[].") :] if spec.path.startswith("trials[].") else spec.path
    return f"condition={condition} trial={trial_number} field={field}"


def _trial_number(trial: Mapping[str, Any], rules: Any) -> Any:
    for key in rules.trial_key:
        if key != rules.condition_key:
            return trial.get(key)
    return None


def _index_for(path: str, root: str) -> int | None:
    prefix = f"{root}["
    if not path.startswith(prefix):
        return None
    end = path.find("]", len(prefix))
    if end < 0:
        return None
    try:
        return int(path[len(prefix) : end])
    except ValueError:
        return None


def _condition_for_path(path: str, conditions: list[Mapping[str, Any]], rules: Any) -> str | None:
    index = _index_for(path, "conditions")
    if index is None or index >= len(conditions):
        return None
    return conditions[index].get(rules.condition_key)


def _is_numeric(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _jsonable(value: Any) -> Any:
    if value is MISSING:
        return None
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return repr(value)


def _trials(document: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = document.get(key)
    return value if isinstance(value, list) else []


def _conditions(document: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = document.get(key)
    return value if isinstance(value, list) else []
