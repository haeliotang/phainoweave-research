"""Metrics, stratification, risk–coverage curves, and matched-retention comparison.

The harness never uses the adequacy method's internals. Two decision rules are compared on
the same truth labels:

* old: the hardened rule's decision status is ``accepted``;
* new: ``adequacy.epistemic_decision == "supported"``.

Risk–coverage is computed per stratum (never pooled alone). If the artifact carries an
optional numeric operating score, it is swept directly; otherwise the harness nests the
declared status/reason signatures in a documented deterministic order and says so.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence

from .truth import is_correct

OLD_UNDETERMINED_STATUSES = frozenset({"undetermined", "indeterminate"})
NEW_RULES = frozenset({"epistemic", "conditional"})
CONDITIONAL_CLAIM_PATH = "adequacy.tests.degeneracy.conditional_claim_supported"
OBSERVATIONAL_EQUIVALENCE_MECHANISMS = frozenset({"clock_offset"})
Z_95 = 1.959963984540054
NEW_SCORE_FIELDS = (
    ("adequacy", "confidence"),
    ("adequacy", "score"),
    ("confidence",),
    ("score",),
)
OLD_SCORE_FIELDS = (
    ("hardened", "confidence"),
    ("hardened", "score"),
    ("confidence",),
    ("score",),
)


@dataclass(frozen=True)
class CurvePoint:
    """One operating point of a rule's risk–coverage curve."""

    level: int
    threshold: float | None
    basis: str
    accepted: int
    correct_accepted: int
    false_accepts: int
    retention: float | None
    false_accept_rate: float | None
    false_accept_interval: tuple[float, float] | None
    signature: str | None = None

    def to_document(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "threshold": self.threshold,
            "basis": self.basis,
            "accepted": self.accepted,
            "correct_accepted": self.correct_accepted,
            "false_accepts": self.false_accepts,
            "retention": self.retention,
            "false_accept_rate": self.false_accept_rate,
            "false_accept_interval": list(self.false_accept_interval)
            if self.false_accept_interval is not None
            else None,
            "signature": self.signature,
        }


@dataclass(frozen=True)
class RuleCurve:
    rule: str
    basis: str
    score_field: str | None
    order_definition: str
    points: tuple[CurvePoint, ...]

    def to_document(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "basis": self.basis,
            "score_field": self.score_field,
            "order_definition": self.order_definition,
            "points": [point.to_document() for point in self.points],
        }


def old_decision_status(trial: Mapping[str, Any], old_decisions: Mapping[tuple[str, int], str]) -> str:
    """Returns the old-rule status for a trial from an externally supplied map."""
    return old_decisions[(trial["condition"], trial["trial"])]


def old_accepted(trial: Mapping[str, Any], old_decisions: Mapping[tuple[str, int], str]) -> bool:
    return old_decision_status(trial, old_decisions) == "accepted"


def old_undetermined(
    trial: Mapping[str, Any], old_decisions: Mapping[tuple[str, int], str]
) -> bool:
    return old_decision_status(trial, old_decisions).lower() in OLD_UNDETERMINED_STATUSES


def conditional_claim(trial: Mapping[str, Any]) -> bool | None:
    """Reads ``adequacy.tests.degeneracy.conditional_claim_supported``.

    A missing, null or non-boolean value is ``None`` (unknown), not a crash and not a
    silent acceptance.
    """
    adequacy = trial.get("adequacy")
    if not isinstance(adequacy, Mapping):
        return None
    tests = adequacy.get("tests")
    if not isinstance(tests, Mapping):
        return None
    degeneracy = tests.get("degeneracy")
    if not isinstance(degeneracy, Mapping):
        return None
    value = degeneracy.get("conditional_claim_supported")
    return value if isinstance(value, bool) else None


def new_accepted(trial: Mapping[str, Any], rule: str = "epistemic") -> bool:
    if rule == "conditional":
        return conditional_claim(trial) is True
    if rule == "epistemic":
        return trial["adequacy"]["epistemic_decision"] == "supported"
    raise ValueError(f"unknown new rule {rule!r}")


def new_undetermined(trial: Mapping[str, Any], rule: str = "epistemic") -> bool:
    epistemic_undetermined = trial["adequacy"]["epistemic_decision"] == "undetermined"
    if rule == "conditional":
        return epistemic_undetermined and conditional_claim(trial) is not True
    if rule == "epistemic":
        return epistemic_undetermined
    raise ValueError(f"unknown new rule {rule!r}")


def new_status_counts(trials: Sequence[Mapping[str, Any]], rule: str) -> dict[str, int]:
    """Status counts for the selected new rule; unknown values are explicit."""
    if rule == "conditional":
        counts = {"conditional_supported": 0, "conditional_unsupported": 0, "unknown": 0}
        for trial in trials:
            value = conditional_claim(trial)
            if value is True:
                counts["conditional_supported"] += 1
            elif value is False:
                counts["conditional_unsupported"] += 1
            else:
                counts["unknown"] += 1
        return counts
    counts: dict[str, int] = {}
    for trial in trials:
        value = trial["adequacy"]["epistemic_decision"]
        counts[value] = counts.get(value, 0) + 1
    return counts


def build_stratum(
    trials: Sequence[Mapping[str, Any]],
    old_decisions: Mapping[tuple[str, int], str],
    new_rule: str = "epistemic",
) -> dict[str, Any]:
    """Builds metrics and risk–coverage for one stratum of trials."""
    if not trials:
        return {"n_trials": 0}
    correctness = {id(trial): is_correct(trial) for trial in trials}
    total = len(trials)
    correct_total = sum(1 for trial in trials if correctness[id(trial)])

    old_metrics = _binary_metrics(
        trials,
        correctness,
        accepted=lambda trial: old_accepted(trial, old_decisions),
        undetermined=lambda trial: old_undetermined(trial, old_decisions),
        status_counts=_counts(
            old_decision_status(trial, old_decisions) for trial in trials
        ),
        correct_total=correct_total,
    )
    new_metrics = _binary_metrics(
        trials,
        correctness,
        accepted=lambda trial: new_accepted(trial, new_rule),
        undetermined=lambda trial: new_undetermined(trial, new_rule),
        status_counts=new_status_counts(trials, new_rule),
        correct_total=correct_total,
    )

    old_curve = _build_curve(
        trials,
        correctness,
        accepted=lambda trial: old_accepted(trial, old_decisions),
        score_fields=OLD_SCORE_FIELDS,
        signature=lambda trial: _old_signature(trial, old_decisions),
        rule="old",
        correct_total=correct_total,
    )
    new_curve = _build_curve(
        trials,
        correctness,
        accepted=lambda trial: new_accepted(trial, new_rule),
        score_fields=NEW_SCORE_FIELDS,
        signature=_new_signature,
        rule="new",
        correct_total=correct_total,
    )
    matched = _matched_retention(old_curve, new_curve)
    return {
        "n_trials": total,
        "n_correct": correct_total,
        "n_incorrect": total - correct_total,
        "old": old_metrics,
        "new": new_metrics,
        "risk_coverage": {
            "old": old_curve.to_document(),
            "new": new_curve.to_document(),
            "matched_retention": matched,
        },
    }


def build_report_strata(
    trials: Sequence[Mapping[str, Any]],
    old_decisions: Mapping[tuple[str, int], str],
    new_rule: str = "epistemic",
) -> dict[str, Any]:
    """Builds overall, layer, mechanism, and condition strata (never pooled alone)."""
    by_layer = _group(trials, lambda trial: trial["layer"])
    by_mechanism = _group(trials, lambda trial: trial["mechanism"])
    by_condition = _group(trials, lambda trial: trial["condition"])
    return {
        "overall": build_stratum(trials, old_decisions, new_rule),
        "by_layer": {
            key: build_stratum(group, old_decisions, new_rule)
            for key, group in sorted(by_layer.items())
        },
        "by_mechanism": {
            key: build_stratum(group, old_decisions, new_rule)
            for key, group in sorted(by_mechanism.items())
        },
        "by_condition": {
            key: build_stratum(group, old_decisions, new_rule)
            for key, group in sorted(by_condition.items())
        },
    }


def observational_equivalence_section(
    trials: Sequence[Mapping[str, Any]],
    old_decisions: Mapping[tuple[str, int], str],
    new_rule: str = "epistemic",
) -> dict[str, Any]:
    """Separates the declared observational-equivalence mechanisms."""
    subset = [
        trial
        for trial in trials
        if trial["mechanism"] in OBSERVATIONAL_EQUIVALENCE_MECHANISMS
    ]
    section: dict[str, Any] = {
        "mechanisms": sorted(OBSERVATIONAL_EQUIVALENCE_MECHANISMS),
        "declaration": (
            "clock offset is exactly degenerate with t0; ADR 0015 declares this an "
            "observational-equivalence case. A correct undetermined is preferred to a "
            "wrong supported result."
        ),
        "n_trials": len(subset),
    }
    if not subset:
        return section
    correct = [trial for trial in subset if is_correct(trial)]
    wrong = [trial for trial in subset if not is_correct(trial)]
    section.update(
        {
            "n_correct": len(correct),
            "n_incorrect": len(wrong),
            "correct_undetermined": sum(
                1 for trial in correct if new_undetermined(trial, new_rule)
            ),
            "correct_supported": sum(
                1 for trial in correct if new_accepted(trial, new_rule)
            ),
            "wrong_undetermined": sum(
                1 for trial in wrong if new_undetermined(trial, new_rule)
            ),
            "wrong_supported": sum(
                1 for trial in wrong if new_accepted(trial, new_rule)
            ),
            "wrong_rejected": sum(
                1
                for trial in wrong
                if trial["adequacy"]["epistemic_decision"] == "rejected"
            ),
            "old": _summary_metrics(subset, old_decisions),
            "new": _summary_metrics(
                subset, old_decisions, use_new=True, new_rule=new_rule
            ),
        }
    )
    return section


# ---------------------------------------------------------------------------
# Core metrics
# ---------------------------------------------------------------------------

def _binary_metrics(
    trials: Sequence[Mapping[str, Any]],
    correctness: Mapping[int, bool],
    accepted: Callable[[Mapping[str, Any]], bool],
    undetermined: Callable[[Mapping[str, Any]], bool],
    status_counts: Mapping[str, int],
    correct_total: int,
) -> dict[str, Any]:
    accepted_count = 0
    correct_accepted = 0
    false_accepts = 0
    abstained = 0
    correct_abstained = 0
    for trial in trials:
        accepted_here = accepted(trial)
        undetermined_here = undetermined(trial)
        correct = correctness[id(trial)]
        if accepted_here:
            accepted_count += 1
            if correct:
                correct_accepted += 1
            else:
                false_accepts += 1
        if undetermined_here:
            abstained += 1
            if correct:
                correct_abstained += 1
    total = len(trials)
    return {
        "n_trials": total,
        "accepted": accepted_count,
        "correct_accepted": correct_accepted,
        "false_accepts": false_accepts,
        "false_accept_rate": _ratio(false_accepts, accepted_count),
        "false_accept_interval": _wilson(false_accepts, accepted_count),
        "valid_retention": _ratio(correct_accepted, correct_total),
        "valid": correct_total,
        "abstained": abstained,
        "correct_abstained": correct_abstained,
        "abstention_rate": _ratio(abstained, total),
        "status_counts": dict(sorted(status_counts.items())),
    }


def _summary_metrics(
    trials: Sequence[Mapping[str, Any]],
    old_decisions: Mapping[tuple[str, int], str],
    use_new: bool = False,
    new_rule: str = "epistemic",
) -> dict[str, Any]:
    correct_total = sum(1 for trial in trials if is_correct(trial))
    correctness = {id(trial): is_correct(trial) for trial in trials}
    if use_new:
        return _binary_metrics(
            trials,
            correctness,
            accepted=lambda trial: new_accepted(trial, new_rule),
            undetermined=lambda trial: new_undetermined(trial, new_rule),
            status_counts=new_status_counts(trials, new_rule),
            correct_total=correct_total,
        )
    return _binary_metrics(
        trials,
        correctness,
        accepted=lambda trial: old_accepted(trial, old_decisions),
        undetermined=lambda trial: old_undetermined(trial, old_decisions),
        status_counts=_counts(
            old_decision_status(trial, old_decisions) for trial in trials
        ),
        correct_total=correct_total,
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _wilson(
    successes: int, total: int, z: float = Z_95
) -> tuple[float, float] | None:
    if total <= 0:
        return None
    proportion = successes / total
    denominator = 1.0 + z * z / total
    centre = (proportion + z * z / (2.0 * total)) / denominator
    half = (
        z
        * math.sqrt(proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total))
        / denominator
    )
    return (max(0.0, centre - half), min(1.0, centre + half))


def _newcombe_difference(
    first_rate: float,
    first_interval: tuple[float, float],
    second_rate: float,
    second_interval: tuple[float, float],
) -> tuple[float, float]:
    difference = first_rate - second_rate
    lower = difference - math.sqrt(
        (first_rate - first_interval[0]) ** 2
        + (second_interval[1] - second_rate) ** 2
    )
    upper = difference + math.sqrt(
        (first_interval[1] - first_rate) ** 2
        + (second_rate - second_interval[0]) ** 2
    )
    return (max(-1.0, lower), min(1.0, upper))


# ---------------------------------------------------------------------------
# Risk–coverage curves and matched retention
# ---------------------------------------------------------------------------

def _build_curve(
    trials: Sequence[Mapping[str, Any]],
    correctness: Mapping[int, bool],
    accepted: Callable[[Mapping[str, Any]], bool],
    score_fields: Sequence[tuple[str, ...]],
    signature: Callable[[Mapping[str, Any]], tuple[Any, ...]],
    rule: str,
    correct_total: int,
) -> RuleCurve:
    accepted_trials = [trial for trial in trials if accepted(trial)]
    score_field, scores = _scores(accepted_trials, score_fields)
    if score_field is not None:
        levels: list[tuple[int, float | None, str | None, list[Mapping[str, Any]]]] = []
        thresholds = sorted({scores[id(trial)] for trial in accepted_trials}, reverse=True)
        for level, threshold in enumerate(thresholds, start=1):
            subset = [
                trial for trial in accepted_trials if scores[id(trial)] >= threshold
            ]
            levels.append((level, threshold, None, subset))
        return RuleCurve(
            rule=rule,
            basis="optional_numeric_score",
            score_field=score_field,
            order_definition=(
                f"descending {score_field}; each point accepts candidates with score >= threshold"
            ),
            points=tuple(
                _points_from_subsets(levels, correctness, correct_total, "optional_numeric_score")
            ),
        )

    signatures = sorted(
        {signature(trial) for trial in accepted_trials},
        key=lambda item: (-sum(1 for trial in accepted_trials if signature(trial) == item), repr(item)),
    )
    levels = []
    for level in range(1, len(signatures) + 1):
        allowed = set(signatures[:level])
        subset = [trial for trial in accepted_trials if signature(trial) in allowed]
        levels.append((level, None, repr(signatures[level - 1]), subset))
    return RuleCurve(
        rule=rule,
        basis="status_reason_nesting",
        score_field=None,
        order_definition=(
            "nested status/reason signatures sorted by descending frequency then "
            "lexicographic; each level admits accepted trials whose signature is in the "
            "first k signatures. This is a deterministic ordering, not a calibrated "
            "probability threshold."
        ),
        points=tuple(
            _points_from_subsets(levels, correctness, correct_total, "status_reason_nesting")
        ),
    )


def _points_from_subsets(
    levels: Sequence[tuple[int, float | None, str | None, Sequence[Mapping[str, Any]]]],
    correctness: Mapping[int, bool],
    correct_total: int,
    basis: str,
) -> list[CurvePoint]:
    points: list[CurvePoint] = []
    for level, threshold, signature, subset in levels:
        accepted = len(subset)
        correct_accepted = sum(1 for trial in subset if correctness[id(trial)])
        false_accepts = accepted - correct_accepted
        points.append(
            CurvePoint(
                level=level,
                threshold=threshold,
                basis=basis,
                accepted=accepted,
                correct_accepted=correct_accepted,
                false_accepts=false_accepts,
                retention=_ratio(correct_accepted, correct_total),
                false_accept_rate=_ratio(false_accepts, accepted),
                false_accept_interval=_wilson(false_accepts, accepted),
                signature=signature,
            )
        )
    points.sort(key=lambda point: (point.retention is None, point.retention or 0.0))
    unique: dict[float, CurvePoint] = {}
    for point in points:
        if point.retention is None:
            continue
        previous = unique.get(point.retention)
        if previous is None or point.accepted > previous.accepted:
            unique[point.retention] = point
    return list(unique.values())


def interpolate_risk(
    points: Sequence[CurvePoint], retention: float
) -> tuple[float, tuple[float, float] | None] | None:
    """Interpolates old-rule risk (and its interval) at a target retention."""
    return _interpolate(points, retention)


def _interpolate(
    points: Sequence[CurvePoint], retention: float
) -> tuple[float, tuple[float, float] | None] | None:
    usable = [point for point in points if point.retention is not None and point.false_accept_rate is not None]
    usable.sort(key=lambda point: point.retention or 0.0)
    if not usable:
        return None
    for point in usable:
        if point.retention == retention:
            return point.false_accept_rate, point.false_accept_interval
    lower = None
    upper = None
    for point in usable:
        if (point.retention or 0.0) < retention:
            lower = point
        elif upper is None:
            upper = point
            break
    if lower is None or upper is None:
        return None
    span = (upper.retention or 0.0) - (lower.retention or 0.0)
    if span <= 0.0:
        return upper.false_accept_rate, upper.false_accept_interval
    weight = (retention - (lower.retention or 0.0)) / span

    def blend(values: tuple[float | None, float | None]) -> float | None:
        low, high = values
        if low is None or high is None:
            return None
        return low + (high - low) * weight

    risk = (lower.false_accept_rate or 0.0) + (
        (upper.false_accept_rate or 0.0) - (lower.false_accept_rate or 0.0)
    ) * weight
    interval = None
    if lower.false_accept_interval is not None and upper.false_accept_interval is not None:
        low = blend((lower.false_accept_interval[0], upper.false_accept_interval[0]))
        high = blend((lower.false_accept_interval[1], upper.false_accept_interval[1]))
        if low is not None and high is not None:
            interval = (low, high)
    return risk, interval


def _matched_retention(old_curve: RuleCurve, new_curve: RuleCurve) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for point in new_curve.points:
        if point.retention is None or point.false_accept_rate is None:
            continue
        old = _interpolate(old_curve.points, point.retention)
        entry: dict[str, Any] = {
            "retention": point.retention,
            "new_accepted": point.accepted,
            "new_correct_accepted": point.correct_accepted,
            "new_false_accept_rate": point.false_accept_rate,
            "new_false_accept_interval": list(point.false_accept_interval)
            if point.false_accept_interval is not None
            else None,
            "new_level": point.level,
            "old_estimable": old is not None,
        }
        if old is None:
            entry["old_false_accept_rate"] = None
            entry["old_false_accept_interval"] = None
            entry["difference"] = None
            entry["difference_interval"] = None
            entry["reason"] = "new retention lies outside the old rule's observed coverage range"
        else:
            old_risk, old_interval = old
            entry["old_false_accept_rate"] = old_risk
            entry["old_false_accept_interval"] = list(old_interval) if old_interval else None
            entry["difference"] = point.false_accept_rate - old_risk
            if point.false_accept_interval is not None and old_interval is not None:
                entry["difference_interval"] = list(
                    _newcombe_difference(
                        point.false_accept_rate,
                        point.false_accept_interval,
                        old_risk,
                        old_interval,
                    )
                )
            else:
                entry["difference_interval"] = None
        matched.append(entry)
    return matched


def _scores(
    accepted_trials: Sequence[Mapping[str, Any]],
    fields: Sequence[tuple[str, ...]],
) -> tuple[str | None, dict[int, float]]:
    if not accepted_trials:
        return None, {}
    for field_path in fields:
        values: dict[int, float] = {}
        complete = True
        for trial in accepted_trials:
            value = _nested_get(trial, field_path)
            if not _finite(value):
                complete = False
                break
            values[id(trial)] = float(value)
        if complete:
            return ".".join(field_path), values
    return None, {}


def _nested_get(document: Any, path: Sequence[str]) -> Any:
    current = document
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _new_signature(trial: Mapping[str, Any]) -> tuple[Any, ...]:
    adequacy = trial["adequacy"]
    return (
        adequacy["model_adequacy_status"],
        adequacy["identifiability_status"],
        tuple(sorted(str(code) for code in adequacy["reason_codes"])),
    )


def _old_signature(
    trial: Mapping[str, Any], old_decisions: Mapping[tuple[str, int], str]
) -> tuple[Any, ...]:
    hardened = trial["hardened"]
    return (
        str(hardened["optimization_status"]),
        str(hardened["identifiability_status_old"]),
        old_decision_status(trial, old_decisions),
    )


def _counts(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _group(
    trials: Sequence[Mapping[str, Any]], key: Callable[[Mapping[str, Any]], str]
) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for trial in trials:
        grouped.setdefault(key(trial), []).append(trial)
    return grouped
