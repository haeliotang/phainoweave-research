"""Identifiability Boundary Report (PR-4e C1 deliverable).

Derived from the frozen claims protocol, the symbolic proof artifact and the
locked claim evidence.  For every declared quantity it states the proven
property, the missing information, and which additional observation would break
the observational equivalence.  Negative results (non-identifiable quantities)
are the point of the report, not a failure to hide.
"""

from __future__ import annotations

from typing import Optional

from .claims_protocol import (
    claim_certificate_view,
    evidence,
    evidence_gate,
    protocol_claims,
    protocol_conventions,
    protocol_gate,
    protocol_mechanism_audit,
    symbolic_proof_digest,
)

# Additional observations that would break each equivalence, by claim.
BREAKING_OBSERVATIONS = {
    "v": {
        "missing": [
            "independent sound-speed determination (c is a declared nuisance: the exact scaling (v,b,c)->(lambda v, lambda b, lambda c) changes v)",
            "direction constraint (an unmodelled curved trajectory changes the total-speed interpretation)",
            "propagation-environment model (delay, multipath) not validated",
        ],
        "break": (
            "a co-located sound-speed measurement (temperature/humidity or in-situ c) removes the "
            "scaling degeneracy; a multi-receiver bearing or an independently constrained trajectory "
            "removes the direction ambiguity. A clock reference does not help: v is already invariant "
            "under G_clock."
        ),
    },
    "f0_times_b": {
        "missing": [
            "independent sound-speed determination (the scaling nuisance multiplies f0*b by lambda)",
            "validation of the straight-line constant-velocity model (L2 open)",
        ],
        "break": (
            "an independent sound-speed measurement fixes the scaling and makes the composite "
            "f0*b physically meaningful; the clock group alone leaves it invariant."
        ),
    },
    "t0": {
        "missing": [
            "absolute time reference: the offset generator beta shifts t0 exactly (beta <-> t0)",
            "clock-rate calibration (the rate generator also rescales t0)",
        ],
        "break": (
            "an independent absolute time anchor (GNSS/PPS-disciplined timestamp, or a known emission "
            "time) breaks the offset degeneracy; a clock-rate calibration removes the residual rate "
            "rescaling."
        ),
    },
    "b": {
        "missing": [
            "clock-rate calibration (b -> k b under rate)",
            "independent sound speed (b -> lambda b under the sound-speed scaling)",
        ],
        "break": (
            "an independent clock-rate reference plus an independent sound-speed measurement are both "
            "needed; either one alone leaves one factor free."
        ),
    },
    "f0": {
        "missing": [
            "clock-rate calibration (f0 -> f0/k under rate)",
        ],
        "break": (
            "an independent clock-rate reference (e.g. a known calibration tone recorded through the "
            "same clock, or a GPS-disciplined sample clock) breaks the rate degeneracy. The sound-speed "
            "nuisance does not affect f0."
        ),
    },
    "b_over_f0": {
        "missing": [
            "the candidate is not invariant under the rate family at all (T5; certificate numeric verdict not_invariant)",
            "no additional observation restores its invariance",
        ],
        "break": (
            "none: an independent clock-rate calibration makes b and f0 separately recoverable, after "
            "which the ratio is merely a derived number, not an invariant. The verified invariant "
            "composite is f0*b."
        ),
    },
}


def _status_counts(artifact: dict, claim_id: str) -> dict:
    for summary in artifact.get("claim_summaries", []):
        if summary["claim_id"] == claim_id:
            return summary.get("status_counts", {})
    return {}


def _rate(counts: dict, key: str, n: int) -> str:
    if n <= 0:
        return "n/a"
    return f"{counts.get(key, 0)}/{n} ({100.0 * counts.get(key, 0) / n:.1f}%)"


def render_boundary(protocol: dict, proof: dict, locked_artifact: Optional[dict] = None) -> str:
    claims = protocol_claims(protocol)
    certificate = evidence(protocol).get("certificate") or {}
    gate = protocol_gate(protocol)
    gate_status = evidence_gate(protocol)
    conventions = protocol_conventions(protocol)
    reconciliation = (evidence(protocol).get("symbolic_proof") or {}).get("convention_reconciliation", {})
    mechanism_audit = protocol_mechanism_audit(protocol)
    lines = []
    lines.append("# Identifiability Boundary Report — PR-4e C1")
    lines.append("")
    lines.append(
        f"**Authority:** ADR 0016 (claims), ADR 0017 (gated invariants) · "
        f"**protocol:** `{protocol['protocol_version']}` frozen `{protocol['protocol_digest']}` · "
        f"evidence `{protocol['evidence_digest']}` · "
        f"**symbolic proof:** `{symbolic_proof_digest(protocol)}`"
    )
    lines.append("")
    lines.append(
        "This report is derived from the frozen protocol, the symbolic proof and the locked claim "
        "evidence. It states what the recording plus the declared model can and cannot support, and "
        "which additional observation would break each equivalence. Non-identifiability is a result."
    )
    lines.append("")
    lines.append("## Evidence gate (ADR 0017)")
    lines.append("")
    lines.append(
        f"`supported_invariant` is **not allowed** in this protocol version. Blockers: "
        + "; ".join(gate["supported_invariant_blockers"])
        + "."
    )
    lines.append("")
    lines.append("| L1 | L2 | L3 | maximum status |")
    lines.append("|---|---|---|---|")
    for row in gate["table"]:
        lines.append(f"| {row['L1']} | {row['L2']} | {row['L3']} | {row['max_status']} |")
    lines.append("")
    lines.append("## Evidence-backed gate status")
    lines.append("")
    completeness = gate_status["l1_completeness"]
    lines.append(
        f"- **L1 completeness:** `{completeness['status']}` — required generators "
        f"{', '.join(f'`{name}`' for name in completeness['required_generators'])}; "
        f"proven {', '.join(f'`{name}`' for name in completeness['proven_generators']) or 'none'}; "
        f"missing {', '.join(f'`{name}`' for name in completeness['missing_generators']) or 'none'}."
    )
    conflicts = gate_status["certificate_conflicts"]
    lines.append(
        f"- **Certificate symbolic/numeric conflicts:** {len(conflicts['blocking'])} blocking, "
        f"{len(conflicts['reconciled'])} reconciled. "
        f"Blocking: {[conflict['claim_id'] for conflict in conflicts['blocking']] or 'none'}; "
        f"reconciled: {[conflict['claim_id'] for conflict in conflicts['reconciled']] or 'none'}."
    )
    contradictions = gate_status["nuisance_contradictions"]
    lines.append(
        f"- **Contradicted nuisance probes:** "
        f"{[item['probe_id'] for item in contradictions] or 'none'}."
    )
    lines.append(
        f"- **Withheld claims:** "
        f"{ {claim_id: reasons for claim_id, reasons in gate_status['withheld_claims'].items()} or 'none'}."
    )
    lines.append("")
    lines.append("## Convention reconciliation with the independent certificate")
    lines.append("")
    lines.append(
        f"- Method: `{conventions['method']['time_map']}`, action `{conventions['method']['parameter_action']}`"
    )
    lines.append(
        f"- Certificate: `{conventions['certificate']['time_map']}`, action `{conventions['certificate']['parameter_action']}`"
    )
    lines.append(f"- Mapping: {conventions['mapping']}; symbolically equivalent: **{reconciliation.get('equivalent')}**")
    lines.append(
        f"- Certificate artifact: `{certificate.get('certificate_path')}` "
        f"sha256 `{certificate.get('certificate_sha256')}`"
    )
    lines.append("")
    lines.append("## Mechanism audit (P0 math audit)")
    lines.append("")
    method = mechanism_audit["correct_actions"]["method"]
    cert = mechanism_audit["correct_actions"]["certificate"]
    misstatement = mechanism_audit["pr4d_misstatement"]
    lines.append(
        f"- Correct method action: `{method['action']}` under `{method['time_map']}` "
        f"(audit forward mismatch `{method['max_relative_forward_mismatch_reported_by_audit']:.1e}`); "
        f"invariants {', '.join(f'`{item}`' for item in method['invariants'])}."
    )
    lines.append(
        f"- Correct certificate action: `{cert['action']}` under `{cert['time_map']}` "
        f"(audit forward mismatch `{cert['max_relative_forward_mismatch_reported_by_audit']:.1e}`)."
    )
    lines.append(
        f"- Frozen PR-4d misstatement: `{misstatement['written_rate_triple']}` does **not** preserve the "
        f"observation (audit mismatch `{misstatement['max_relative_mismatch_reported_by_audit']:.1e}`); "
        f"it is an erratum target, not a competing group element. PR-4d's clock-rate-equivalence "
        f"conclusion stands."
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| quantity | L1 (symbolic) | L1 (certificate) | L2 | ceiling | locked supported_conditional |")
    lines.append("|---|---|---|---|---|---|")
    for claim in claims:
        locked_counts = _status_counts(locked_artifact or {}, claim["claim_id"])
        n = sum(locked_counts.values())
        certificate_status = claim_certificate_view(protocol, claim["claim_id"]).get("status", "not_covered")
        lines.append(
            f"| `{claim['claim_id']}` = `{claim['expression']}` | {claim['l1_status']} (`{claim['l1_theorem']}`) | "
            f"{certificate_status} | {claim['l2_status']} | `{claim['max_status']}` | "
            f"{_rate(locked_counts, 'supported_conditional', n)} |"
        )
    lines.append("")
    for claim in claims:
        claim_id = claim["claim_id"]
        breaking = BREAKING_OBSERVATIONS.get(claim_id, {"missing": [], "break": "n/a"})
        locked_counts = _status_counts(locked_artifact or {}, claim_id)
        n = sum(locked_counts.values())
        lines.append(f"## `{claim_id}` — {claim['label']}")
        lines.append("")
        lines.append(f"- **Expression:** `{claim['expression']}` [{claim['units']}]")
        lines.append(f"- **Symmetry scope:** {claim['symmetry_scope']}")
        lines.append(
            f"- **L1 (invariance):** {claim['l1_status']} (`{claim['l1_theorem']}`); "
            f"certificate: `{claim_certificate_view(protocol, claim_id).get('status', 'not_covered')}`"
        )
        lines.append(f"- **L2 (identifiability in the full declared model):** {claim['l2_status']}")
        if claim.get("l2_reason"):
            lines.append(f"  - {claim['l2_reason']}")
        if claim.get("l2_counterexample"):
            lines.append(f"  - counterexample: `{claim['l2_counterexample']}`")
        lines.append(f"- **Ceiling:** `{claim['max_status']}` — {claim['ceiling_reason']}")
        lines.append(f"- **Nuisance assumptions:** {'; '.join(claim['nuisance_assumptions'])}")
        lines.append(
            f"- **Nuisance probes:** {', '.join(f'`{probe}`' for probe in claim.get('nuisance_probes', [])) or 'none'}"
        )
        lines.append(
            f"- **Conditioning:** {'; '.join(claim['conditioning']) if claim['conditioning'] else 'none declared'}"
        )
        lines.append("")
        lines.append("**Missing information.**")
        lines.append("")
        for item in breaking["missing"]:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("**Additional observation that would break the equivalence.**")
        lines.append("")
        lines.append(breaking["break"])
        lines.append("")
        if locked_counts:
            lines.append(
                "**Locked evidence (claim status counts, evaluated without truth):** "
                + ", ".join(f"`{status}` {count}" for status, count in sorted(locked_counts.items()))
                + f" (n={n})."
            )
            lines.append("")
        if claim["l1_status"] == "refuted":
            lines.append(
                "**Negative result.** This quantity is not invariant under the admitted group; it is "
                "reported as `contradicted` for the invariant proposition and is not a physical claim. "
                "The refutation is the deliverable, not a detector failure."
            )
            lines.append("")
    lines.append("## What the recording does support (conditional claims)")
    lines.append("")
    lines.append(
        "Under a declared nominal clock, `f0`, `t0` and (with a known sound speed) `b` are conditionally "
        "recoverable; `v` and `f0*b` are invariant under the clock group but remain conditional because "
        "the sound-speed/direction nuisances are not resolved. None reaches `supported_invariant`."
    )
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    for limitation in proof.get("limitations", []):
        lines.append(f"- {limitation}")
    lines.append(
        "- The locked evidence here reports claim statuses without truth; coverage/validity against "
        "truth is computed by the independent evaluator from the `evaluation_only` block."
    )
    lines.append("")
    return "\n".join(lines)


def write_boundary(protocol: dict, proof: dict, locked_artifact: dict, path: str) -> str:
    import hashlib
    import os

    markdown = render_boundary(protocol, proof, locked_artifact)
    payload = markdown.encode("utf-8")
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(payload)
    return hashlib.sha256(payload).hexdigest()


def main(argv=None) -> int:
    import argparse
    import json

    from .claims_protocol import load_protocol, protocol_claims
    from .symbolic import derive_proof

    parser = argparse.ArgumentParser(description="Render the Identifiability Boundary Report.")
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--locked", default=None, help="locked artifact JSON")
    parser.add_argument("--out", required=True)
    parser.add_argument("--evidence-out", default=None)
    args = parser.parse_args(argv)
    protocol = load_protocol(args.protocol)
    proof = derive_proof()
    locked = json.load(open(args.locked, "r", encoding="utf-8")) if args.locked else None
    sha = write_boundary(protocol, proof, locked or {}, args.out)
    if args.evidence_out:
        payload = json.dumps(
            {
                "artifact": "c1-boundary-report",
                "protocol_digest": protocol["protocol_digest"],
                "evidence_digest": protocol["evidence_digest"],
                "symbolic_proof_digest": symbolic_proof_digest(protocol),
                "markdown_sha256": sha,
                "claims": [claim["claim_id"] for claim in protocol_claims(protocol)],
            },
            indent=1,
            sort_keys=True,
        ) + "\n"
        with open(args.evidence_out, "w", encoding="utf-8") as handle:
            handle.write(payload)
    print(f"boundary: {args.out}  sha256: {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
