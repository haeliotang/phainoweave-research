"""Cross-estimator detection and claim decision rule (E1-C Detection Consensus v2).

This is a *decision rule*, not a measurement-model claim.  Each estimator
returns a ternary status for a model-mismatch test:

    D  discrepancy          evidence of model mismatch
    A  adequate             passes the predefined adequacy tests
    U  undetermined         insufficient evidence / numerical failure / abstention

The consensus is ternary as well.  In particular, two abstentions are NOT
``not_detected``: absence of evidence is not evidence of absence.  Two
``adequate`` results mean only "no mismatch found under the current tests",
never "the physical model is proven correct".

Consensus detection (E1-C):

    D + D -> detected
    A + A -> not_detected (no mismatch found; not a proof of correctness)
    D + A -> undetermined / estimator_disagreement
    D + U -> undetermined / incomplete_confirmation
    A + U -> undetermined / insufficient_evidence
    U + U -> undetermined / both_inconclusive

Claim support additionally requires identical claim status and parameter
agreement in a declared normalisation; raw parameter equality alone is not
sufficient when an observation equivalence class exists.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

D = "D"
A = "A"
U = "U"

DETECTED = "detected"
NOT_DETECTED = "not_detected"
UNDETERMINED = "undetermined"

# A D+D result is an estimator-level statement only.  Two numerical
# implementations share the observation, measurement representation and
# physical assumptions, so their agreement cannot by itself establish that the
# physical model is wrong.
EVIDENCE_SCOPE_ESTIMATOR = "estimator_consensus"
EVIDENCE_SCOPE_PHYSICAL = "physically_supported"

ORIGIN_STATUSES = {
    "discrepancy": D,
    "adequate": A,
}

CLAIM_AGREE_STATUSES = ("supported_conditional", "undetermined", "contradicted")


def estimator_status(adequacy_status: Optional[str]) -> str:
    """Map an estimator adequacy status to D/A/U.

    Any non-discrepancy, non-adequate state (insufficient_evidence,
    indeterminate, failed, missing) is U: undetermined.
    """
    if adequacy_status == "discrepancy":
        return D
    if adequacy_status == "adequate":
        return A
    return U


def consensus_detection(
    baseline_status: Optional[str], independent_status: Optional[str]
) -> dict[str, Any]:
    """Ternary consensus fusion for a mismatch test."""
    b = estimator_status(baseline_status)
    i = estimator_status(independent_status)
    pair = {b, i}
    if b == D and i == D:
        return {
            "detection_status": DETECTED,
            "reason_codes": [],
            "pair": [b, i],
            "evidence_scope": EVIDENCE_SCOPE_ESTIMATOR,
            "physically_supported": False,
        }
    if b == A and i == A:
        return {
            "detection_status": NOT_DETECTED,
            "reason_codes": [],
            "pair": [b, i],
            "evidence_scope": None,
            "physically_supported": False,
        }
    if pair == {D, A}:
        return {"detection_status": UNDETERMINED, "reason_codes": ["estimator_disagreement"], "pair": [b, i]}
    if pair == {D, U}:
        return {"detection_status": UNDETERMINED, "reason_codes": ["incomplete_confirmation"], "pair": [b, i]}
    if pair == {A, U}:
        return {"detection_status": UNDETERMINED, "reason_codes": ["insufficient_evidence"], "pair": [b, i]}
    return {"detection_status": UNDETERMINED, "reason_codes": ["both_inconclusive"], "pair": [b, i],
            "evidence_scope": None, "physically_supported": False}


def parameter_agreement(differences: dict[str, float], bounds: dict[str, float]) -> dict[str, Any]:
    """Check parameter agreement in a declared normalisation against audit bounds."""
    failures = {}
    for key, bound in bounds.items():
        value = differences.get(key)
        if value is None:
            failures[key] = "missing"
        elif abs(float(value)) > float(bound):
            failures[key] = float(value)
    return {"agrees": not failures, "failures": failures}


def consensus_claim(
    baseline_status: Optional[str],
    independent_status: Optional[str],
    params_agree: bool = True,
) -> dict[str, Any]:
    """Consensus claim status; disagreement becomes undetermined, never promoted."""
    if baseline_status not in CLAIM_AGREE_STATUSES or independent_status not in CLAIM_AGREE_STATUSES:
        raise ValueError("unknown claim status")
    if baseline_status != independent_status:
        return {"status": UNDETERMINED, "reason_codes": ["estimator_disagreement"]}
    if baseline_status == "supported_conditional" and not params_agree:
        return {"status": UNDETERMINED, "reason_codes": ["parameter_disagreement"]}
    return {"status": baseline_status, "reason_codes": []}


def apply_audit(
    records: Iterable[dict[str, Any]], bounds: dict[str, float]
) -> dict[str, Any]:
    """Apply the v2 rule to estimator-audit records and count outcomes."""
    detection = {DETECTED: 0, NOT_DETECTED: 0, UNDETERMINED: 0}
    reasons: dict[str, int] = {}
    correct_cv = {
        "adequate_pairs": 0,
        "discrepancy_pairs": 0,
        "undetermined_pairs": 0,
        "supported_claims": {},
    }
    acceleration = {"n": 0, "false_supported": 0}
    for rec in records:
        base, ind = rec["baseline"], rec["independent"]
        agreement = parameter_agreement(rec.get("differences", {}), bounds)
        if rec.get("family") in {"correct_constant_velocity", "correct_cv"}:
            b_status = estimator_status(base.get("adequacy_status"))
            i_status = estimator_status(ind.get("adequacy_status"))
            if b_status == A and i_status == A:
                correct_cv["adequate_pairs"] += 1
            elif b_status == D and i_status == D:
                correct_cv["discrepancy_pairs"] += 1
            else:
                correct_cv["undetermined_pairs"] += 1
            for claim_id, status in (base.get("claim_statuses") or {}).items():
                out = consensus_claim(status, (ind.get("claim_statuses") or {}).get(claim_id), agreement["agrees"])
                if out["status"] == "supported_conditional":
                    correct_cv["supported_claims"][claim_id] = correct_cv["supported_claims"].get(claim_id, 0) + 1
        elif rec.get("family") in {"acceleration", "acceleration_misspecification"}:
            acceleration["n"] += 1
            out = consensus_detection(base.get("adequacy_status"), ind.get("adequacy_status"))
            detection[out["detection_status"]] += 1
            for reason in out["reason_codes"]:
                reasons[reason] = reasons.get(reason, 0) + 1
            if estimator_status(base.get("adequacy_status")) == A and estimator_status(ind.get("adequacy_status")) == A:
                acceleration["false_supported"] += 1
    n_accel = acceleration["n"]
    n_correct = (
        correct_cv["adequate_pairs"]
        + correct_cv["discrepancy_pairs"]
        + correct_cv["undetermined_pairs"]
    )
    total_detections = detection[DETECTED] + correct_cv["discrepancy_pairs"]
    rates = {
        "sensitivity": (detection[DETECTED] / n_accel) if n_accel else None,
        "false_positive_rate": (correct_cv["discrepancy_pairs"] / n_correct) if n_correct else None,
        "false_discovery_proportion": (
            correct_cv["discrepancy_pairs"] / total_detections if total_detections else None
        ),
        "deterministic_no_detection_rate": (correct_cv["adequate_pairs"] / n_correct) if n_correct else None,
        "abstention_rate_mismatch": (detection[UNDETERMINED] / n_accel) if n_accel else None,
        "abstention_rate_correct": (correct_cv["undetermined_pairs"] / n_correct) if n_correct else None,
    }
    return {
        "detection": detection,
        "detection_reasons": reasons,
        "acceleration": acceleration,
        "correct_cv": correct_cv,
        "rates": rates,
        "evidence_scope": EVIDENCE_SCOPE_ESTIMATOR,
        "physically_supported": False,
        "rule": "E1-C Detection Consensus v2: D/A/U ternary; U+U is undetermined, never not_detected; D+D is estimator consensus only",
    }
