"""Paired decision metrics for C2 repair candidates.

All comparisons are paired on the same trial identities. Binary metrics are expanded into
the four-cell table (both, baseline-only, candidate-only, neither); the risk difference is
the candidate rate minus the B0 rate. The interval is a documented paired Wald 95%
interval (an explicit alternative to Newcombe; see ``paired_wald_interval``).
"""

from __future__ import annotations

import math
from bisect import bisect_right
from typing import Any, Callable, Mapping, Sequence

from .artifacts import Artifact, CandidateRecord, Trial

Z_95 = 1.959963984540054
C1_ALLOWED_CLAIM_STATUSES = frozenset(
    {"supported_conditional", "undetermined", "contradicted"}
)
METRIC_NAMES = (
    "false_rejection",
    "detection",
    "discrepancy_detection",
    "supported_coverage",
    "valid_retention",
    "abstention",
)
SUPPORTED_CLAIM_STATUS = "supported_conditional"
GEOMETRY_BIN_EDGES = (0.0, 200.0, 400.0, 800.0, 1600.0, 3200.0, 6400.0, 12800.0)


def validly_supported(record: CandidateRecord) -> bool:
    """Explicit valid support, or claim-status + C1-gate derivation.

    The artifact may provide `validly_supported` explicitly. If absent, support is taken
    from claim statuses: at least one `supported_conditional` claim and no status outside
    the C1 gate allowed set. Adequacy accept alone is never treated as support.
    """
    if record.decision != "accept":
        return False
    gate_ok = all(
        status in C1_ALLOWED_CLAIM_STATUSES for status in record.claim_statuses.values()
    )
    explicit = record.validly_supported
    if explicit is not None:
        return bool(explicit and gate_ok)
    return gate_ok and any(
        status == SUPPORTED_CLAIM_STATUS for status in record.claim_statuses.values()
    )


def support_basis(record: CandidateRecord) -> str:
    return "explicit_field" if record.validly_supported is not None else "claim_statuses_gate"


def candidate_metrics(trials: Sequence[Trial], candidate: str) -> dict[str, Any]:
    """Decision metrics for one candidate on one environment."""
    records = [(trial, trial.candidates[candidate]) for trial in trials]
    total = len(records)
    truth_correct = sum(1 for trial, _ in records if trial.truth_correct)
    accepted = sum(1 for _, record in records if record.decision == "accept")
    rejected = sum(1 for _, record in records if record.decision == "reject")
    undetermined = sum(1 for _, record in records if record.decision == "undetermined")
    correct_accepted = sum(
        1 for trial, record in records if trial.truth_correct and record.decision == "accept"
    )
    false_rejections = sum(
        1 for trial, record in records if _false_rejection(trial, record)
    )
    frr_denominator = sum(
        1
        for trial, record in records
        if trial.mechanism == "correct_cv" and trial.truth_correct
    )
    detection_count = sum(
        1 for trial, record in records if trial.mechanism == "acceleration" and _detected(record)
    )
    detection_denominator = sum(
        1 for trial, record in records if trial.mechanism == "acceleration"
    )
    reason_counts: dict[str, int] = {}
    undetermined_reasons: dict[str, int] = {}
    for trial, record in records:
        for code in record.reason_codes:
            reason_counts[code] = reason_counts.get(code, 0) + 1
        if record.decision == "undetermined":
            if not record.reason_codes:
                undetermined_reasons["<none>"] = undetermined_reasons.get("<none>", 0) + 1
            for code in record.reason_codes:
                undetermined_reasons[code] = undetermined_reasons.get(code, 0) + 1
    correct_model = [trial for trial in trials if trial.mechanism == "correct_cv"]
    supported_count = sum(
        1
        for trial in correct_model
        if trial.truth_correct and validly_supported(trial.candidates[candidate])
    )
    acceleration = [
        (trial, trial.candidates[candidate])
        for trial in trials
        if trial.mechanism == "acceleration"
    ]
    taxonomy = _misspecification_taxonomy(acceleration, candidate)
    null_noise = _null_noise_only(trials, candidate)
    support_basis_counts = _counts(
        support_basis(trial.candidates[candidate]) for trial in correct_model
    )
    return {
        "candidate": candidate,
        "n_trials": total,
        "truth_correct": truth_correct,
        "accepted": accepted,
        "rejected": rejected,
        "undetermined": undetermined,
        "correct_accepted": correct_accepted,
        "false_accepts": accepted - correct_accepted,
        "false_rejection": {
            "numerator": false_rejections,
            "denominator": frr_denominator,
            "rate": _ratio(false_rejections, frr_denominator),
            "wilson_95": list(_wilson_bounds(false_rejections, frr_denominator))
            if frr_denominator
            else None,
            "definition": "truth-correct correct-CV trials with adequacy discrepancy or decision reject",
        },
        "detection": {
            "numerator": detection_count,
            "denominator": detection_denominator,
            "rate": _ratio(detection_count, detection_denominator),
            "wilson_95": list(_wilson_bounds(detection_count, detection_denominator))
            if detection_denominator
            else None,
            "definition": "acceleration trials with adequacy discrepancy or decision reject",
        },
        "valid_retention": {
            "numerator": correct_accepted,
            "denominator": truth_correct,
            "rate": _ratio(correct_accepted, truth_correct),
            "wilson_95": list(_wilson_bounds(correct_accepted, truth_correct))
            if truth_correct
            else None,
            "definition": "truth-correct trials accepted",
        },
        "abstention": {
            "numerator": undetermined,
            "denominator": total,
            "rate": _ratio(undetermined, total),
            "wilson_95": list(_wilson_bounds(undetermined, total)) if total else None,
        },
        "supported_coverage": {
            "numerator": supported_count,
            "denominator": len(correct_model),
            "rate": _ratio(supported_count, len(correct_model)),
            "wilson_95": list(_wilson_bounds(supported_count, len(correct_model)))
            if correct_model
            else None,
            "definition": (
                "truth-correct correct-model trials with explicit/claim-gated valid support, "
                "over all correct-model trials"
            ),
            "support_basis_counts": support_basis_counts,
        },
        "misspecification_taxonomy": taxonomy,
        "null_noise_only": null_noise,
        "decision_counts": {
            "accept": accepted,
            "reject": rejected,
            "undetermined": undetermined,
        },
        "adequacy_status_counts": _counts(record.adequacy_status for _, record in records),
        "reason_breakdown": {
            "all": dict(sorted(reason_counts.items())),
            "undetermined": dict(sorted(undetermined_reasons.items())),
        },
        "claim_status_counts": {
            claim: _counts(record.claim_statuses.get(claim, "<missing>") for _, record in records)
            for claim in ("v", "f0_times_b", "t0")
        },
        "by_mechanism": _by_group(
            records, lambda trial: trial.mechanism, candidate
        ),
        "by_geometry": _by_group(
            records, lambda trial: geometry_bin_label(trial.geometry_m), candidate
        ),
    }


def claim_integrity(trials: Sequence[Trial], candidate: str) -> dict[str, Any]:
    """Flags any status C1's gate would not allow; it never rewrites the status."""
    violations: list[dict[str, Any]] = []
    status_counts: dict[str, dict[str, int]] = {
        claim: {} for claim in ("v", "f0_times_b", "t0")
    }
    supported_invariant = 0
    for trial in trials:
        record = trial.candidates[candidate]
        for claim in ("v", "f0_times_b", "t0"):
            status = record.claim_statuses.get(claim, "<missing>")
            status_counts[claim][status] = status_counts[claim].get(status, 0) + 1
            if status == "supported_invariant":
                supported_invariant += 1
            if status not in C1_ALLOWED_CLAIM_STATUSES:
                violations.append(
                    {
                        "condition": trial.condition,
                        "seed": trial.seed,
                        "candidate": candidate,
                        "claim": claim,
                        "status": status,
                        "reason": (
                            "supported_invariant is not allowed by the C1 gate"
                            if status == "supported_invariant"
                            else "status is not allowed by the C1 gate"
                        ),
                    }
                )
    return {
        "candidate": candidate,
        "allowed_claim_statuses": sorted(C1_ALLOWED_CLAIM_STATUSES),
        "status": "violations" if violations else "ok",
        "n_violations": len(violations),
        "supported_invariant_count": supported_invariant,
        "by_claim_status_counts": {
            claim: dict(sorted(counts.items())) for claim, counts in status_counts.items()
        },
        "violations": violations,
    }


def paired_comparison(
    trials: Sequence[Trial],
    baseline: str,
    candidate: str,
    metric: str,
    undecided_policy: str = "not_detected",
) -> dict[str, Any]:
    """Paired binary comparison for one metric; returns counts, rates and interval."""
    metric_function = _metric_function(metric, undecided_policy)
    pairs: list[tuple[bool, bool]] = []
    excluded = 0
    for trial in trials:
        baseline_value = metric_function(trial, trial.candidates[baseline])
        candidate_value = metric_function(trial, trial.candidates[candidate])
        if baseline_value is None or candidate_value is None:
            excluded += 1
            continue
        pairs.append((baseline_value, candidate_value))
    n = len(pairs)
    both = sum(1 for baseline_value, candidate_value in pairs if baseline_value and candidate_value)
    baseline_only = sum(
        1 for baseline_value, candidate_value in pairs if baseline_value and not candidate_value
    )
    candidate_only = sum(
        1 for baseline_value, candidate_value in pairs if candidate_value and not baseline_value
    )
    neither = n - both - baseline_only - candidate_only
    baseline_rate = _ratio(both + baseline_only, n)
    candidate_rate = _ratio(both + candidate_only, n)
    risk_difference = (
        (candidate_only - baseline_only) / n
        if n
        else None
    )
    interval = paired_wald_interval(candidate_only, baseline_only, n)
    return {
        "metric": metric,
        "baseline_candidate": baseline,
        "candidate": candidate,
        "n_pairs": n,
        "n_excluded": excluded,
        "counts": {
            "both": both,
            "baseline_only": baseline_only,
            "candidate_only": candidate_only,
            "neither": neither,
        },
        "baseline_rate": baseline_rate,
        "candidate_rate": candidate_rate,
        "risk_difference": risk_difference,
        "risk_difference_interval": list(interval) if interval is not None else None,
        "interval_method": "paired_wald_95",
        "z": Z_95,
        "undecided_policy": undecided_policy if metric == "discrepancy_detection" else None,
    }


def paired_wald_interval(
    candidate_only: int, baseline_only: int, n: int, z: float = Z_95
) -> tuple[float, float] | None:
    """Paired Wald 95% interval for a risk difference.

    Let b=n10 (candidate event, baseline non-event), c=n01 (baseline event, candidate
    non-event), d=(b-c)/n. The estimated variance of d for paired Bernoulli data is

        Var(d) = (b + c - (b-c)^2/n) / n^2.

    The interval is d +/- z*sqrt(Var(d)), clipped to [-1,1]. This is an explicit
    documented alternative to the Newcombe paired score interval; it is not a
    Newcombe interval.
    """
    if n <= 0:
        return None
    difference = (candidate_only - baseline_only) / n
    variance = (candidate_only + baseline_only - (candidate_only - baseline_only) ** 2 / n) / (
        n * n
    )
    if variance < 0.0:
        variance = 0.0
    half = z * math.sqrt(variance)
    return (max(-1.0, difference - half), min(1.0, difference + half))


def geometry_bin_label(value: float) -> str:
    edges = GEOMETRY_BIN_EDGES
    index = bisect_right(edges, value) - 1
    if index < 0:
        index = 0
    if index >= len(edges) - 1:
        return f"[{edges[-1]:g},inf)"
    lower = edges[index]
    upper = edges[index + 1]
    return f"[{lower:g},{upper:g})"


def geometry_bins() -> list[dict[str, Any]]:
    bins: list[dict[str, Any]] = []
    for index in range(len(GEOMETRY_BIN_EDGES)):
        lower = GEOMETRY_BIN_EDGES[index]
        upper = GEOMETRY_BIN_EDGES[index + 1] if index + 1 < len(GEOMETRY_BIN_EDGES) else None
        label = f"[{lower:g},inf)" if upper is None else f"[{lower:g},{upper:g})"
        bins.append({"label": label, "lower": lower, "upper": upper})
    return bins


def paired_tables(
    trials: Sequence[Trial],
    baseline: str,
    candidate: str,
    undecided_policy: str = "not_detected",
) -> dict[str, Any]:
    """Overall, per-mechanism and per-geometry paired tables for all metrics."""
    overall = {
        metric: paired_comparison(
            trials, baseline, candidate, metric, undecided_policy=undecided_policy
        )
        for metric in METRIC_NAMES
    }
    mechanisms = sorted({trial.mechanism for trial in trials})
    by_mechanism: dict[str, Any] = {}
    for mechanism in mechanisms:
        subset = [trial for trial in trials if trial.mechanism == mechanism]
        by_mechanism[mechanism] = {
            metric: paired_comparison(
                subset, baseline, candidate, metric, undecided_policy=undecided_policy
            )
            for metric in METRIC_NAMES
        }
    by_geometry: dict[str, Any] = {}
    for geometry in geometry_bins():
        label = geometry["label"]
        if geometry["upper"] is None:
            subset = [trial for trial in trials if trial.geometry_m >= geometry["lower"]]
        else:
            subset = [
                trial
                for trial in trials
                if geometry["lower"] <= trial.geometry_m < geometry["upper"]
            ]
        by_geometry[label] = {
            "lower": geometry["lower"],
            "upper": geometry["upper"],
            "n_trials": len(subset),
            "metrics": {
                metric: paired_comparison(
                    subset, baseline, candidate, metric, undecided_policy=undecided_policy
                )
                for metric in METRIC_NAMES
            },
        }
    return {
        "overall": overall,
        "by_mechanism": by_mechanism,
        "by_geometry": by_geometry,
        "undecided_policy": undecided_policy,
    }


def negative_result(
    metrics_by_candidate: Mapping[str, Mapping[str, Any]],
    paired_by_candidate: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Explicit negative-result statement; no candidate recommendation."""
    qualifying: list[str] = []
    frr_gain: list[str] = []
    detection_loss: list[str] = []
    abstention_gaming: list[str] = []
    details: dict[str, Any] = {}
    baseline = metrics_by_candidate["B0"]
    for candidate in metrics_by_candidate:
        if candidate == "B0":
            continue
        paired = paired_by_candidate[candidate]["overall"]
        frr_delta = paired["false_rejection"]["risk_difference"]
        detection_delta = paired.get(
            "discrepancy_detection", paired["detection"]
        )["risk_difference"]
        retention_delta = paired["valid_retention"]["risk_difference"]
        abstention_delta = paired["abstention"]["risk_difference"]
        correct_delta = (
            metrics_by_candidate[candidate]["correct_accepted"] - baseline["correct_accepted"]
        )
        frr_gain_flag = frr_delta is not None and frr_delta < 0.0
        detection_loss_flag = detection_delta is not None and detection_delta < 0.0
        if frr_gain_flag:
            frr_gain.append(candidate)
        if detection_loss_flag:
            detection_loss.append(candidate)
        gaming = (
            frr_gain_flag
            and abstention_delta is not None
            and abstention_delta > 0.0
            and correct_delta <= 0
        )
        if gaming:
            abstention_gaming.append(candidate)
        qualifies = frr_gain_flag and not detection_loss_flag and not gaming
        if qualifies:
            qualifying.append(candidate)
        details[candidate] = {
            "false_rejection_delta": frr_delta,
            "detection_delta": detection_delta,
            "valid_retention_delta": retention_delta,
            "abstention_delta": abstention_delta,
            "correct_accepted_delta": correct_delta,
            "frr_gain": frr_gain_flag,
            "detection_loss": detection_loss_flag,
            "qualifies": qualifies,
            "abstention_gaming": gaming,
        }
    holds = not qualifying
    if holds:
        statement = (
            "No candidate improves the false-rejection rate on correct constant-velocity "
            "cells without losing acceleration detection or without an abstention-gaming "
            "pattern in the primary environment. This is a negative result: the current "
            "representation/residual framework is not repaired by these candidates; it is "
            "not a recommendation of a threshold or candidate."
        )
    else:
        statement = (
            "At least one candidate has a lower false-rejection rate, no point-estimate "
            "detection loss, and no abstention-gaming pattern versus B0 in the primary "
            "environment: "
            + ", ".join(qualifying)
            + ". This is a point-estimate summary only; use the paired intervals and "
            "stratified tables before drawing conclusions."
        )
    return {
        "negative_result_holds": holds,
        "statement": statement,
        "qualifying_candidates": qualifying,
        "frr_gain_candidates": frr_gain,
        "detection_loss_candidates": detection_loss,
        "abstention_gaming_candidates": abstention_gaming,
        "criteria": (
            "FRR gain: paired point risk difference < 0 on truth-correct correct-CV cells. "
            "Detection loss: paired point risk difference < 0 for discrepancy_detected "
            "on acceleration cells; undetermined is never counted as detection. "
            "Qualification requires FRR gain, no detection loss, and no abstention-gaming "
            "pattern (FRR gain via increased abstention without more correct accepted). "
            "Intervals are reported "
            "in the paired tables; no candidate is recommended."
        ),
        "details": details,
    }


def select_candidates(artifact: Artifact, requested: Sequence[str] | None) -> tuple[str, ...]:
    if not requested:
        return artifact.candidates
    selected = tuple(requested)
    if len(set(selected)) != len(selected):
        raise ValueError("duplicate candidate ids in --candidates")
    missing = [candidate for candidate in selected if candidate not in artifact.candidates]
    if missing:
        raise ValueError(
            f"selected candidates not present in artifact: {', '.join(missing)}"
        )
    if "B0" not in selected:
        raise ValueError("--candidates must include the paired baseline B0")
    return selected


def _metric_function(
    metric: str, undecided_policy: str = "not_detected"
) -> Callable[[Trial, CandidateRecord], bool | None]:
    if metric == "false_rejection":
        return _false_rejection
    if metric == "detection":
        return lambda trial, record: (
            _detected(record) if trial.mechanism == "acceleration" else None
        )
    if metric == "discrepancy_detection":
        return lambda trial, record: _discrepancy_detection(
            trial, record, undecided_policy
        )
    if metric == "supported_coverage":
        return lambda trial, record: (
            (trial.truth_correct and validly_supported(record))
            if trial.mechanism == "correct_cv"
            else None
        )
    if metric == "valid_retention":
        return lambda trial, record: (
            record.decision == "accept" if trial.truth_correct else None
        )
    if metric == "abstention":
        return lambda trial, record: record.decision == "undetermined"
    raise ValueError(f"unknown metric {metric!r}")


def _false_rejection(trial: Trial, record: CandidateRecord) -> bool | None:
    if trial.mechanism != "correct_cv" or not trial.truth_correct:
        return None
    return _detected(record)


def _detected(record: CandidateRecord) -> bool:
    return record.decision == "reject" or record.adequacy_status == "discrepancy"


def _discrepancy_detection(
    trial: Trial, record: CandidateRecord, undecided_policy: str
) -> bool | None:
    """Taxonomy detection: only a rejected discrepancy counts, never abstention/accept."""
    if trial.mechanism != "acceleration":
        return None
    if record.decision == "undetermined":
        if undecided_policy == "excluded":
            return None
        return False
    return record.decision == "reject" and record.adequacy_status == "discrepancy"


def _by_group(
    records: Sequence[tuple[Trial, CandidateRecord]],
    key_function: Callable[[Trial], str],
    candidate: str,
) -> dict[str, Any]:
    groups: dict[str, list[tuple[Trial, CandidateRecord]]] = {}
    for trial, record in records:
        groups.setdefault(key_function(trial), []).append((trial, record))
    return {
        key: _group_metrics(group, candidate)
        for key, group in sorted(groups.items())
    }


def _group_metrics(
    records: Sequence[tuple[Trial, CandidateRecord]], candidate: str
) -> dict[str, Any]:
    total = len(records)
    truth_correct = sum(1 for trial, _ in records if trial.truth_correct)
    accepted = sum(1 for _, record in records if record.decision == "accept")
    correct_accepted = sum(
        1 for trial, record in records if trial.truth_correct and record.decision == "accept"
    )
    undetermined = sum(1 for _, record in records if record.decision == "undetermined")
    false_rejections = sum(
        1 for trial, record in records if _false_rejection(trial, record)
    )
    frr_denominator = sum(
        1
        for trial, _ in records
        if trial.mechanism == "correct_cv" and trial.truth_correct
    )
    detection_count = sum(
        1 for trial, record in records if trial.mechanism == "acceleration" and _detected(record)
    )
    detection_denominator = sum(
        1 for trial, _ in records if trial.mechanism == "acceleration"
    )
    return {
        "candidate": candidate,
        "n_trials": total,
        "truth_correct": truth_correct,
        "accepted": accepted,
        "correct_accepted": correct_accepted,
        "undetermined": undetermined,
        "supported_coverage": _ratio(
            sum(
                1
                for trial, record in records
                if trial.mechanism == "correct_cv"
                and trial.truth_correct
                and validly_supported(record)
            ),
            sum(1 for trial, _ in records if trial.mechanism == "correct_cv"),
        ),
        "false_rejection_rate": _ratio(false_rejections, frr_denominator),
        "false_rejection_wilson_95": list(_wilson_bounds(false_rejections, frr_denominator))
        if frr_denominator
        else None,
        "detection_rate": _ratio(detection_count, detection_denominator),
        "detection_wilson_95": list(_wilson_bounds(detection_count, detection_denominator))
        if detection_denominator
        else None,
        "valid_retention": _ratio(correct_accepted, truth_correct),
        "valid_retention_wilson_95": list(_wilson_bounds(correct_accepted, truth_correct))
        if truth_correct
        else None,
        "abstention_rate": _ratio(undetermined, total),
        "abstention_wilson_95": list(_wilson_bounds(undetermined, total)) if total else None,
    }


def _counts(values: Sequence[str] | Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _misspecification_taxonomy(
    records: Sequence[tuple[Trial, CandidateRecord]], candidate: str
) -> dict[str, Any]:
    counts = {
        "discrepancy_detected": 0,
        "undetermined": 0,
        "false_supported": 0,
        "rejected_without_discrepancy": 0,
    }
    rows: list[dict[str, Any]] = []
    for trial, record in records:
        if record.decision == "undetermined":
            category = "undetermined"
        elif record.decision == "accept":
            category = "false_supported"
        elif record.decision == "reject" and record.adequacy_status == "discrepancy":
            category = "discrepancy_detected"
        else:
            category = "rejected_without_discrepancy"
        counts[category] += 1
        rows.append(
            {
                "condition": trial.condition,
                "seed": trial.seed,
                "category": category,
                "validly_supported": validly_supported(record),
            }
        )
    denominator = len(records)
    categories: dict[str, Any] = {}
    for category, count in counts.items():
        interval = _wilson_bounds(count, denominator)
        categories[category] = {
            "count": count,
            "rate": _ratio(count, denominator),
            "wilson_95": list(interval) if interval else None,
        }
    return {
        "candidate": candidate,
        "denominator": denominator,
        "categories": categories,
        "rows": rows,
        "definition": (
            "acceleration trials classified exclusively by decision: undetermined -> "
            "undetermined; accept -> false_supported; reject+discrepancy -> "
            "discrepancy_detected; reject without discrepancy -> rejected_without_discrepancy. "
            "Safe abstention is never counted as detection."
        ),
    }


def _null_noise_only(trials: Sequence[Trial], candidate: str) -> dict[str, Any]:
    subset = [
        trial
        for trial in trials
        if "null" in trial.mechanism.lower() or "noise" in trial.mechanism.lower()
    ]
    accepted = sum(
        1 for trial in subset if trial.candidates[candidate].decision == "accept"
    )
    supported = sum(
        1 for trial in subset if validly_supported(trial.candidates[candidate])
    )
    promoted = sum(
        1
        for trial in subset
        if trial.candidates[candidate].decision == "accept"
        or validly_supported(trial.candidates[candidate])
    )
    upper = _wilson_bounds(promoted, len(subset))
    return {
        "candidate": candidate,
        "n_trials": len(subset),
        "accepted": accepted,
        "validly_supported": supported,
        "false_supported": promoted,
        "false_supported_rate": _ratio(promoted, len(subset)),
        "false_supported_wilson_95": list(upper) if upper else None,
        "zero_intent": True,
        "definition": (
            "null/noise-only trials promoted to accepted or validly supported; the target "
            "is zero promotion, and observed counts are reported without converting zero "
            "counts into a zero probability."
        ),
    }


def chirp_power(artifact: Artifact, selected_candidates: Sequence[str]) -> dict[str, Any]:
    """Per-observable-chirp-bin CV FRR and acceleration discrepancy detection."""
    bins = artifact.chirp_bins
    policy = artifact.undecided_policy
    if not bins:
        return {
            "declared": False,
            "bins": [],
            "bins_without_acceleration": [],
            "trials_missing_chirp_observable": sum(
                1 for trial in artifact.trials if trial.estimated_chirp_rate is None
            ),
            "note": "artifact supplies no chirp_bins; per-chirp power is unavailable",
        }
    rows: list[dict[str, Any]] = []
    no_acceleration: list[str] = []
    for bin_spec in bins:
        subset = [
            trial
            for trial in artifact.trials
            if trial.estimated_chirp_rate is not None
            and _in_bin(trial.estimated_chirp_rate, bin_spec)
        ]
        cv = [trial for trial in subset if trial.mechanism == "correct_cv"]
        accel = [trial for trial in subset if trial.mechanism == "acceleration"]
        cv_rates = {}
        accel_rates = {}
        paired: dict[str, Any] = {}
        for candidate in selected_candidates:
            cv_den = sum(1 for trial in cv if trial.truth_correct)
            cv_num = sum(
                1
                for trial in cv
                if trial.truth_correct
                and (
                    trial.candidates[candidate].decision == "reject"
                    or trial.candidates[candidate].adequacy_status == "discrepancy"
                )
            )
            accel_counts = _taxonomy_counts(accel, candidate)
            cv_rates[candidate] = {
                "numerator": cv_num,
                "denominator": cv_den,
                "rate": _ratio(cv_num, cv_den),
                "wilson_95": list(_wilson_bounds(cv_num, cv_den)) if cv_den else None,
            }
            accel_rates[candidate] = {
                "discrepancy_detected": accel_counts["discrepancy_detected"],
                "undetermined": accel_counts["undetermined"],
                "false_supported": accel_counts["false_supported"],
                "denominator": len(accel),
                "detection_rate": _ratio(
                    accel_counts["discrepancy_detected"], len(accel)
                ),
                "detection_wilson_95": list(
                    _wilson_bounds(accel_counts["discrepancy_detected"], len(accel))
                )
                if accel
                else None,
            }
            if candidate != "B0":
                paired[candidate] = {
                    "cv_false_rejection": paired_comparison(
                        cv, "B0", candidate, "false_rejection"
                    ),
                    "acceleration_detection": paired_comparison(
                        accel, "B0", candidate, "discrepancy_detection",
                        undecided_policy=policy,
                    ),
                }
        if not accel:
            no_acceleration.append(bin_spec.bin_id)
        rows.append(
            {
                "bin_id": bin_spec.bin_id,
                "lower": bin_spec.lower,
                "upper": bin_spec.upper,
                "n_trials": len(subset),
                "n_correct_cv": len(cv),
                "n_acceleration": len(accel),
                "no_acceleration_samples": not accel,
                "estimated_chirp_rate_observable": True,
                "cv_false_rejection": cv_rates,
                "acceleration_detection": accel_rates,
                "paired": paired,
            }
        )
    return {
        "declared": True,
        "bins": rows,
        "bins_without_acceleration": no_acceleration,
        "trials_missing_chirp_observable": sum(
            1 for trial in artifact.trials if trial.estimated_chirp_rate is None
        ),
        "note": (
            "Per-bin CV FRR and acceleration detection; bins without acceleration samples "
            "are flagged. Paired comparisons are Bx-B0 within each bin and mechanism."
        ),
    }


def snr_conditioning(artifact: Artifact) -> dict[str, Any]:
    bins = artifact.snr_bins
    verified = bool(
        bins is not None
        and len(bins) > 1
        and all((bin_spec.n_samples or 0) > 0 for bin_spec in bins)
    )
    return {
        "snr_conditioning_verified": verified,
        "snr_branch": "verified" if verified else "unverified",
        "declared_bins": [
            {"bin_id": bin_spec.bin_id, "lower": bin_spec.lower, "upper": bin_spec.upper, "n_samples": bin_spec.n_samples}
            for bin_spec in (bins or ())
        ],
        "reason": (
            "artifact declares more than one estimated-SNR bin with samples"
            if verified
            else "artifact does not declare more than one estimated-SNR bin with samples"
        ),
    }


def _taxonomy_counts(
    records: Sequence[Trial], candidate: str
) -> dict[str, int]:
    counts = {
        "discrepancy_detected": 0,
        "undetermined": 0,
        "false_supported": 0,
        "rejected_without_discrepancy": 0,
    }
    for trial in records:
        record = trial.candidates[candidate]
        if record.decision == "undetermined":
            counts["undetermined"] += 1
        elif record.decision == "accept":
            counts["false_supported"] += 1
        elif record.decision == "reject" and record.adequacy_status == "discrepancy":
            counts["discrepancy_detected"] += 1
        else:
            counts["rejected_without_discrepancy"] += 1
    return counts


def _in_bin(value: float, bin_spec: Any) -> bool:
    return value >= bin_spec.lower and (bin_spec.upper is None or value < bin_spec.upper)


def _wilson_bounds(successes: int, total: int) -> tuple[float, float] | None:
    if total <= 0:
        return None
    z = Z_95
    proportion = successes / total
    denominator = 1.0 + z * z / total
    centre = (proportion + z * z / (2.0 * total)) / denominator
    half = (
        z
        * math.sqrt(proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total))
        / denominator
    )
    return (max(0.0, centre - half), min(1.0, centre + half))
