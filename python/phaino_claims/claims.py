"""Claim-level evaluation without truth (PR-4e C1).

Two steps, deliberately separate:

1. :func:`claim_metrics` turns the fitted parameter estimate, its standard
   errors and the PR-4d adequacy block into the claim values, uncertainties and
   gate results.  It takes **no truth and no observation** -- only the fitted
   result and the adequacy verdict.
2. :func:`apply_claim_statuses` applies the frozen protocol (L1 refutation,
   gate precedence, L3 uncertainty thresholds) and produces the claim records.

Truth is used nowhere here; the development layer uses it only to *select* the
L3 thresholds (documented in the development artifact), never to assign a
status.
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np

from .claims_protocol import (
    ALL_CLAIMS,
    CLAIMS_BY_ID,
    EVALUATED_CLAIMS,
    claim_certificate_view,
    evidence_gate,
    full_precision_thresholds,
    protocol_thresholds,
)

STATUSES = ("supported_invariant", "supported_conditional", "undetermined", "contradicted")


def _finite(value) -> bool:
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def _parameter(hardened, name: str) -> float:
    params = hardened.params if isinstance(hardened, dict) else hardened.params
    return float(params[name])


def _standard_error(hardened, name: str) -> float:
    errors = hardened.se if hasattr(hardened, "se") else hardened["se"]
    value = errors.get(name)
    return float(value) if value is not None else float("nan")


def claim_metrics(hardened, adequacy: dict) -> list[dict]:
    """Compute value / uncertainty / gates for every declared claim.

    ``hardened`` is a :class:`phaino_acoustics.fit_hardened.HardenedFitResult`
    (or a dict with ``params``/``se``); ``adequacy`` is the PR-4d adequacy
    block.  No truth enters this function.
    """
    if hasattr(hardened, "params"):
        params = {name: float(value) for name, value in hardened.params.items()}
        se = {name: float(value) for name, value in hardened.se.items()}
    else:
        params = {name: float(value) for name, value in hardened["params"].items()}
        se = {name: float(value) for name, value in hardened["se"].items()}

    f0, v, t0, b = params["f0"], params["v"], params["t0"], params["b"]
    se_f0, se_v, se_t0, se_b = se.get("f0", math.nan), se.get("v", math.nan), se.get("t0", math.nan), se.get("b", math.nan)
    se_available = all(_finite(x) and x >= 0.0 for x in (se_f0, se_v, se_t0, se_b))

    optimization_status = hardened.optimization_status if hasattr(hardened, "optimization_status") else hardened["optimization_status"]
    adequacy_status = adequacy["model_adequacy_status"]
    identifiability_status = adequacy["identifiability_status"]
    gates = {
        "optimization_converged": optimization_status == "converged",
        "adequacy_adequate": adequacy_status == "adequate",
        "identifiability_gate": identifiability_status != "insufficient_evidence",
        "uncertainties_available": bool(se_available),
    }
    gates_ok = all(gates.values())

    values = {
        "v": v,
        "b_over_f0": b / f0 if f0 > 0.0 else math.nan,
        "t0": t0,
        "b": b,
        "f0": f0,
        "f0_times_b": f0 * b,
    }
    relative = {
        "v": se_v / v if v > 0.0 else math.nan,
        "b_over_f0": math.hypot(se_b / b, se_f0 / f0) if b > 0.0 and f0 > 0.0 else math.nan,
        "t0": se_t0,
        "b": se_b / b if b > 0.0 else math.nan,
        "f0": se_f0 / f0 if f0 > 0.0 else math.nan,
        "f0_times_b": math.hypot(se_f0 / f0, se_b / b) if f0 > 0.0 and b > 0.0 else math.nan,
    }

    records = []
    for claim_id in ALL_CLAIMS:
        definition = CLAIMS_BY_ID[claim_id]
        metric = relative[claim_id]
        records.append(
            {
                "claim_id": claim_id,
                "value": float(values[claim_id]),
                "uncertainty": float(metric) if _finite(metric) else None,
                "uncertainty_metric": definition["uncertainty_metric"]["expression"],
                "uncertainty_kind": definition["uncertainty_metric"]["kind"],
                "gates": gates,
                "gates_ok": gates_ok,
                "l1_status": definition["l1_status"],
                "l2_status": definition["l2_status"],
                "symmetry_scope": definition["symmetry_scope"],
                "conditioning": list(definition["conditioning"]),
                "max_status": definition["max_status"],
            }
        )
    return records


def _gate_reasons(metric: dict) -> list[str]:
    reasons = []
    gates = metric["gates"]
    if not gates["optimization_converged"]:
        reasons.append("optimization_not_converged")
    if not gates["adequacy_adequate"]:
        reasons.append("adequacy_not_adequate")
    if not gates["identifiability_gate"]:
        reasons.append("identifiability_insufficient")
    if not gates["uncertainties_available"]:
        reasons.append("uncertainties_unavailable")
    return reasons


def _within_tolerance(value: float, truth: float, tolerance: dict) -> bool:
    if not _finite(value) or not _finite(truth):
        return False
    if tolerance["kind"] == "relative":
        scale = abs(truth) if truth != 0.0 else 1.0
        return abs(value - truth) / scale <= tolerance["value"]
    return abs(value - truth) <= tolerance["value"]


def apply_claim_statuses(metrics: Iterable[dict], protocol: dict) -> list[dict]:
    """Apply the frozen protocol to raw claim metrics (no truth is read).

    Evidence-backed gate checks (L1 completeness, certificate symbolic/numeric
    conflicts, contradicted nuisance probes) are applied before the optimization/
    adequacy/identifiability/uncertainty gates: a claim they withhold is
    ``undetermined`` regardless of the fit quality.
    """
    thresholds = protocol_thresholds(protocol)
    record_thresholds = full_precision_thresholds(protocol)
    gate = evidence_gate(protocol)
    withheld = gate.get("withheld_claims", {})
    claims = []
    for metric in metrics:
        claim_id = metric["claim_id"]
        definition = CLAIMS_BY_ID[claim_id]
        record = {
            "claim_id": claim_id,
            "claim_kind": definition["claim_kind"],
            "invariance_refuted": definition["l1_status"] == "refuted",
            "l1_theorem": definition["l1_theorem"],
            "value": metric["value"],
            "uncertainty": metric["uncertainty"],
            "uncertainty_metric": metric["uncertainty_metric"],
            "symmetry_scope": metric["symmetry_scope"],
            "conditioning": metric["conditioning"],
            "max_status": definition["max_status"],
            "l1_status": definition["l1_status"],
            "l2_status": definition["l2_status"],
            "reason_codes": [],
            "status": "undetermined",
            "threshold": record_thresholds.get(claim_id),
            "l1_certificate": claim_certificate_view(protocol, claim_id),
        }
        if definition["claim_kind"] == "refuted_invariant":
            # The *invariant* proposition is refuted; this is claim-level and independent of the fit.
            record["status"] = "contradicted"
            record["reason_codes"] = [f"l1_counterexample_{definition['l1_theorem']}"]
            claims.append(record)
            continue
        if claim_id in withheld:
            record["status"] = "undetermined"
            record["reason_codes"] = list(withheld[claim_id])
            claims.append(record)
            continue
        gate_reasons = _gate_reasons(metric)
        if gate_reasons:
            record["status"] = "undetermined"
            record["reason_codes"] = gate_reasons
            claims.append(record)
            continue
        threshold = thresholds.get(claim_id)
        if threshold is None:
            record["status"] = "undetermined"
            record["reason_codes"] = ["threshold_not_declared"]
            claims.append(record)
            continue
        uncertainty = metric["uncertainty"]
        if uncertainty is None or not _finite(uncertainty) or uncertainty > float(threshold):
            record["status"] = "undetermined"
            record["reason_codes"] = ["uncertainty_exceeds_threshold"]
            claims.append(record)
            continue
        record["status"] = "supported_conditional"
        record["reason_codes"] = []
        claims.append(record)
    return claims


def claim_truth(scenario) -> dict:
    """Truth values for the evaluator.  EVALUATION ONLY -- never used by a status."""
    return {
        "v": float(scenario.v),
        "b_over_f0": float(scenario.b) / float(scenario.f0),
        "t0": float(scenario.t0),
        "b": float(scenario.b),
        "f0": float(scenario.f0),
        "f0_times_b": float(scenario.f0) * float(scenario.b),
    }


def within_tolerance(claim_id: str, estimate: float, truth: float) -> bool:
    """Evaluate one estimate against truth with the claim's declared tolerance."""
    definition = CLAIMS_BY_ID[claim_id]
    return _within_tolerance(estimate, truth, definition["claim_tolerance"])
