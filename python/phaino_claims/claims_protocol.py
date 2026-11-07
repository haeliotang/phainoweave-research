"""Claim protocol for PR-4e C1 — frozen payload, evidence attachments, digests.

Revision 1.2.0 (P0-1 protocol-freeze defect): the protocol is split into

* ``frozen_payload`` — claims definitions, group generators/actions, conventions,
  thresholds, gate rules, decision precedence, model declaration, nuisance-probe
  declarations.  ``protocol_digest`` is the SHA-256 of this payload only.
* ``evidence`` — the symbolic proof digest/theorem statuses, the independent
  certificate artifact digest and per-claim numeric verdicts, development-run
  calibration statistics, nuisance-probe results, environment and timestamps.
  It is referenced by its own ``evidence_digest`` and is **not** part of the
  frozen digest.

Consequently, building the protocol with no certificate, with a different
certificate digest, or with different development-run statistics yields the same
``protocol_digest``; only ``evidence_digest`` changes.

Revision 1.1.0 replaced the refuted ``b/f0`` candidate with the verified
composite ``f0*b``.  This version also records the P0 math-audit mechanism
finding: the correct clock action per convention, the frozen PR-4d report's
incorrect written rate triple, and the numeric re-verification of T4/T5.

Claim evaluation never reads truth and never imports the independent certificate
code; the certificate enters only as evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Optional

PROTOCOL_VERSION = "pr4e-claims-1.3.0"
PROTOCOL_SCHEMA = "pr4e-claims-protocol-v2"
EXPERIMENT_NAME = "pr4e-claims"
DEFAULT_CERTIFICATE_PATH = "/tmp/certificate.json"

# Frozen thresholds are stored at a declared decimal precision so that
# environment-dependent last-bit differences in the development selection
# (e.g. BLAS/numpy build differences of ~1e-15 relative) cannot move the
# frozen digest.  Full-precision values and development statistics are in
# evidence only.
THRESHOLD_PRECISION = 6
THRESHOLD_PRECISION_NOTE = (
    "thresholds in frozen_payload are canonicalised to THRESHOLD_PRECISION significant decimal "
    "digits; full-precision development-selected thresholds and statistics are recorded in evidence."
)

REVISION_NOTE = (
    "1.3.0: thresholds in the frozen payload are canonicalised to THRESHOLD_PRECISION significant "
    "digits (declared in the payload); the full-precision selected values and development statistics "
    "live in evidence only. Fixes cross-architecture digest drift at ~1e-15 caused by BLAS/numpy "
    "last-bit differences in the development-selected thresholds. 1.2.0: frozen payload separated "
    "from evidence attachments; protocol_digest covers only the "
    "frozen payload (claims, generators/actions, conventions, thresholds, gate rules, precedence, "
    "model, nuisance-probe declarations) and is stable across certificate/environment/development "
    "statistics; evidence_digest covers them. Adds the P0 math-audit mechanism finding: correct "
    "clock action per convention, the frozen PR-4d report's incorrect written rate triple, and "
    "numeric re-verification of T4/T5 at 8.9e-16. 1.1.0 replaced the refuted b/f0 candidate with "
    "the verified composite f0*b."
)

CANDIDATE_CORRECTION = {
    "adr_0016_candidate": "b/f0",
    "status": "refuted",
    "replacement": "f0*b",
    "method_derivation": "T4_f0b_invariance (proven), T5_b_over_f0_refuted (refuted)",
    "certificate_agreement": (
        "certificate numeric verdict not_invariant for b/f0; invariant composite b*f0 "
        "(certificate note)"
    ),
}

# Claims evaluated per trial (support/undetermined).  ``b_over_f0`` is
# reported as contradicted by L1 and is not a support candidate.
EVALUATED_CLAIMS = ("v", "f0_times_b", "f0", "b", "t0")
ALL_CLAIMS = ("v", "f0_times_b", "t0", "b", "f0", "b_over_f0")

REQUIRED_GENERATORS = ("clock_offset", "clock_rate")

# ---------------------------------------------------------------------------
# Frozen declarations
# ---------------------------------------------------------------------------

GENERATOR_DECLARATIONS = (
    {
        "name": "clock_offset",
        "parameter": "beta",
        "time_map": "t_obs = k_m*t_phys + beta with k_m = 1",
        "method_action": "(f0, v, t0, b, c) -> (f0, v, t0 + beta, b, c)",
        "certificate_action": "(f0, v, t0, b, c) -> (f0, v, beta + t0, b, c)",
        "l1_status": "proven",
        "theorem": "T2_forward_invariance",
        "note": "constant clock offset; shifts t0 exactly (beta <-> t0)",
    },
    {
        "name": "clock_rate",
        "parameter": "k_m",
        "time_map": "t_obs = k_m*t_phys + beta with beta = 0",
        "method_action": "(f0, v, t0, b, c) -> (f0/k_m, v, k_m*t0, k_m*b, c)",
        "certificate_action": "(f0, v, t0, b, c) -> (k_c*f0, v, t0/k_c, b/k_c, c) with k_c = 1/k_m",
        "l1_status": "proven",
        "theorem": "T2_forward_invariance",
        "note": "constant clock rate; v invariant, f0*b invariant, b/f0 -> k_m^2 b/f0",
    },
)

MODEL_DECLARATION = {
    "name": "e0-narrowband-doppler",
    "model": (
        "straight-line constant-velocity point source; stationary receiver; radial Doppler; "
        "no propagation delay, multipath, source directivity or acceleration"
    ),
    "parameters": ["f0", "v", "t0", "b", "c"],
    "forward_expression": "F(t) = f0 / (1 + v^2*tau/(c*sqrt(b^2 + v^2*tau^2))), tau = t - t0",
    "assumptions": ["f0 > 0", "v > 0", "b > 0", "c > 0", "t0 real", "time real"],
}

CONVENTIONS = {
    "method": {
        "time_map": "t_obs = k_m * t_phys + beta",
        "parameter_action": "(f0, v, t0, b, c) -> (f0/k_m, v, k_m*t0 + beta, k_m*b, c)",
        "where": "this claim protocol and phaino_claims.symbolic",
    },
    "certificate": {
        "time_map": "t_obs = t_phys / k_c + beta",
        "parameter_action": "(f0, v, t0, b, c) -> (k_c*f0, v, beta + t0/k_c, b/k_c, c)",
        "where": "independent certificate artifact (phaino_claim_certificate), evidence only",
    },
    "mapping": "k_c = 1 / k_m (reciprocal rate conventions; identical group action)",
    "equivalence_theorem": "T11_convention_equivalence",
}

MECHANISM_AUDIT = {
    "audit": "P0 math audit (Lead verification) reconciled with C1-A",
    "correct_actions": {
        "method": {
            "time_map": "t_obs = k_m*t_phys + beta",
            "action": "(f0/k_m, v, k_m*t0 + beta, k_m*b, c)",
            "preserves_forward": True,
            "max_relative_forward_mismatch_reported_by_audit": 8.9e-16,
            "invariants": ["v", "f0*b"],
            "non_invariants": {
                "b/f0": "k_m^2 * b/f0",
                "f0": "f0/k_m",
                "b": "k_m*b",
                "t0": "k_m*t0 + beta",
            },
        },
        "certificate": {
            "time_map": "t_obs = t_phys/k_c + beta",
            "action": "(k_c*f0, v, beta + t0/k_c, b/k_c, c)",
            "preserves_forward": True,
            "max_relative_forward_mismatch_reported_by_audit": 8.5e-16,
            "mapping": "k_c = 1/k_m",
            "invariants": ["v", "f0*b"],
        },
    },
    "pr4d_misstatement": {
        "source": "PR-4d report (frozen historical record; erratum to be written by the Lead)",
        "written_rate_triple": "(f0' = k f0, b' = k b, t0' = t0/k)",
        "preserves_forward": False,
        "max_relative_mismatch_reported_by_audit": 2.5e-2,
        "diagnosis": (
            "incorrect written parameter action in the frozen report, not a competing group "
            "element; PR-4d's clock-rate-is-observational-equivalence conclusion stands"
        ),
        "used_by_this_protocol": False,
        "correct_method_action": "(f0/k_m, v, k_m*t0 + beta, k_m*b, c)",
    },
    "reverification": {
        "T4_f0b_invariance": "re-verified numerically at 8.9e-16",
        "T5_b_over_f0_refuted": "re-verified numerically: (b/f0)' = k_m^2 (b/f0)",
        "certificate_numeric_b_over_f0_mismatch": 4.9375e-2,
    },
}

CLAIM_DEFINITIONS = (
    {
        "claim_id": "v",
        "label": "relative speed of the source along the line of sight",
        "expression": "v",
        "units": "m/s",
        "claim_kind": "invariant",
        "symmetry_scope": "G_clock",
        "l1_status": "proven",
        "l1_theorem": "T3_v_invariance",
        "l2_status": "open",
        "l2_scope": "full declared model with declared nuisances (unknown sound speed, direction, propagation environment)",
        "l2_counterexample": "T9_sound_speed_nuisance",
        "l2_reason": (
            "an unknown sound speed admits the exact scaling (v,b,c)->(lambda v, lambda b, lambda c); "
            "direction and propagation nuisances are unmodelled"
        ),
        "nuisance_assumptions": [
            "sound speed c = 343 m/s known to the declared tolerance",
            "straight-line constant-velocity trajectory",
            "no propagation delay, multipath, or source-directivity effects",
        ],
        "nuisance_probes": ["sound_speed_scaling", "direction_constraint", "propagation_environment"],
        "conditioning": [
            "declared model valid",
            "sound speed known (an independent c measurement would be required for physical support)",
        ],
        "max_status": "supported_conditional",
        "ceiling_reason": "L2 is not proven in the full declared model (T9 counterexample)",
        "claim_tolerance": {"kind": "relative", "value": 0.02, "source": "E0 operational tolerance"},
        "uncertainty_metric": {"kind": "relative_se", "expression": "se(v)/v", "parameters": ["v"]},
        "value_expression": "v",
    },
    {
        "claim_id": "f0_times_b",
        "label": "composite emitted frequency times closest-approach distance b*f0 (verified invariant; replaces the b/f0 candidate)",
        "expression": "f0*b",
        "units": "Hz*m",
        "claim_kind": "invariant",
        "symmetry_scope": "G_clock",
        "l1_status": "proven",
        "l1_theorem": "T4_f0b_invariance",
        "l2_status": "open",
        "l2_scope": "full declared model with declared nuisances",
        "l2_counterexample": "T9_sound_speed_nuisance",
        "l2_reason": "the sound-speed scaling nuisance multiplies f0*b by lambda",
        "nuisance_assumptions": [
            "sound speed c = 343 m/s known to the declared tolerance",
            "straight-line constant-velocity trajectory",
        ],
        "nuisance_probes": ["sound_speed_scaling"],
        "conditioning": ["declared model valid", "sound speed known"],
        "max_status": "supported_conditional",
        "ceiling_reason": "L2 is not proven in the full declared model (T9 counterexample)",
        "claim_tolerance": {"kind": "relative", "value": 0.05, "source": "propagated E0 tolerance"},
        "uncertainty_metric": {
            "kind": "relative_se",
            "expression": "sqrt((se_f0/f0)^2 + (se_b/b)^2)",
            "parameters": ["f0", "b"],
        },
        "value_expression": "f0*b",
    },
    {
        "claim_id": "t0",
        "label": "physical event time (closest approach)",
        "expression": "t0",
        "units": "s",
        "claim_kind": "conditional",
        "symmetry_scope": "trivial group (recorder clock assumed nominal: k=1, beta=0)",
        "l1_status": "refuted",
        "l1_theorem": "T6_t0_refuted",
        "l2_status": "proven_within_conditioning",
        "l2_scope": "nominal-clock model; t0 is the directly observed time origin and is invariant under the sound-speed nuisance",
        "l2_counterexample": None,
        "l2_reason": "under the conditioning (nominal clock) the nominal-model 4-observable map identifies t0",
        "nuisance_assumptions": ["recorder clock is nominal", "declared model valid"],
        "nuisance_probes": [],
        "conditioning": ["k = 1 and beta = 0 (nominal clock) within the declared tolerance"],
        "max_status": "supported_conditional",
        "ceiling_reason": "not invariant under G_clock (offset shifts t0); only a conditional claim under a nominal clock",
        "claim_tolerance": {"kind": "absolute", "value": 0.25, "source": "E0 operational tolerance"},
        "uncertainty_metric": {"kind": "absolute_se", "expression": "se(t0)", "parameters": ["t0"]},
        "value_expression": "t0",
    },
    {
        "claim_id": "b",
        "label": "closest-approach distance",
        "expression": "b",
        "units": "m",
        "claim_kind": "conditional",
        "symmetry_scope": "trivial group (recorder clock assumed nominal: k=1, beta=0)",
        "l1_status": "refuted",
        "l1_theorem": "T7_b_refuted",
        "l2_status": "counterexample_within_nuisance",
        "l2_scope": "nominal clock and sound speed known; with unknown c the scaling nuisance changes b",
        "l2_counterexample": "T9_sound_speed_nuisance",
        "l2_reason": "b is rescaled by the clock rate and by the sound-speed nuisance",
        "nuisance_assumptions": ["recorder clock is nominal", "sound speed known"],
        "nuisance_probes": ["sound_speed_scaling"],
        "conditioning": ["k = 1 and beta = 0 (nominal clock)", "c = 343 m/s known"],
        "max_status": "supported_conditional",
        "ceiling_reason": "not invariant under G_clock (rate rescales b); conditional on nominal clock and known c",
        "claim_tolerance": {"kind": "relative", "value": 0.05, "source": "E0 operational tolerance"},
        "uncertainty_metric": {"kind": "relative_se", "expression": "se_b/b", "parameters": ["b"]},
        "value_expression": "b",
    },
    {
        "claim_id": "f0",
        "label": "emitted (rest-frame) frequency",
        "expression": "f0",
        "units": "Hz",
        "claim_kind": "conditional",
        "symmetry_scope": "trivial group (recorder clock assumed nominal: k=1, beta=0)",
        "l1_status": "refuted",
        "l1_theorem": "T8_f0_refuted",
        "l2_status": "proven_within_conditioning",
        "l2_scope": "nominal-clock model; f0 is the directly observed frequency scale",
        "l2_counterexample": None,
        "l2_reason": "under the conditioning (nominal clock) the nominal-model 4-observable map identifies f0",
        "nuisance_assumptions": ["recorder clock is nominal", "declared model valid"],
        "nuisance_probes": [],
        "conditioning": ["k = 1 and beta = 0 (nominal clock) within the declared tolerance"],
        "max_status": "supported_conditional",
        "ceiling_reason": "not invariant under G_clock (rate rescales f0); only a conditional claim under a nominal clock",
        "claim_tolerance": {"kind": "relative", "value": 0.01, "source": "E0 operational tolerance"},
        "uncertainty_metric": {"kind": "relative_se", "expression": "se_f0/f0", "parameters": ["f0"]},
        "value_expression": "f0",
    },
    {
        "claim_id": "b_over_f0",
        "label": "closest-approach distance over emitted frequency (REFUTED candidate from ADR 0016)",
        "expression": "b/f0",
        "units": "m/Hz",
        "claim_kind": "refuted_invariant",
        "symmetry_scope": "G_clock",
        "l1_status": "refuted",
        "l1_theorem": "T5_b_over_f0_refuted",
        "l2_status": "not_reached",
        "l2_scope": None,
        "l2_counterexample": "T5_b_over_f0_refuted",
        "l2_reason": (
            "the candidate is not invariant under the rate generator: in the method convention "
            "b/f0 -> k_m^2 b/f0 (certificate convention: b/(k_c^2 f0) with k_c = 1/k_m)"
        ),
        "nuisance_assumptions": ["as declared model"],
        "nuisance_probes": [],
        "conditioning": [],
        "max_status": "contradicted",
        "ceiling_reason": "L1 refuted: rate family changes b/f0; the invariant composite is f0*b (T4)",
        "claim_tolerance": {"kind": "relative", "value": 0.05, "source": "declared for reporting only"},
        "uncertainty_metric": {
            "kind": "relative_se",
            "expression": "sqrt((se_b/b)^2 + (se_f0/f0)^2)",
            "parameters": ["b", "f0"],
        },
        "value_expression": "b/f0",
    },
)

CLAIMS_BY_ID = {claim["claim_id"]: claim for claim in CLAIM_DEFINITIONS}

NUISANCE_PROBE_DECLARATIONS = (
    {
        "probe_id": "sound_speed_scaling",
        "family": "N_physical",
        "assumption": "sound speed known to the declared tolerance",
        "probe": "exact scaling (v,b,c) -> (lambda v, lambda b, lambda c) leaves the forward observation unchanged",
        "affects_claims": ["v", "f0_times_b", "b"],
        "evidence_theorem": "T9_sound_speed_nuisance",
    },
    {
        "probe_id": "direction_constraint",
        "family": "N_physical",
        "assumption": "straight-line constant-velocity trajectory",
        "probe": "unmodelled trajectory direction; not algebraically formalised",
        "affects_claims": ["v"],
        "evidence_theorem": None,
    },
    {
        "probe_id": "propagation_environment",
        "family": "N_physical",
        "assumption": "no propagation delay or multipath",
        "probe": "unmodelled propagation environment; not algebraically formalised",
        "affects_claims": ["v"],
        "evidence_theorem": None,
    },
)

# Declared default results (evidence values): the sound-speed probe is *open*
# (an exact degeneracy, unresolved), the other two are not probed because no
# algebra exists for them.  A result of "contradicted" withholds support.
DEFAULT_NUISANCE_PROBE_RESULTS = {
    "sound_speed_scaling": {
        "status": "open",
        "basis": "T9_sound_speed_nuisance: exact one-parameter degeneracy; not resolved by the recording",
    },
    "direction_constraint": {
        "status": "not_probed",
        "basis": "direction nuisance is declared but not algebraically formalised",
    },
    "propagation_environment": {
        "status": "not_probed",
        "basis": "propagation nuisance is declared but not algebraically formalised",
    },
}

GATE_TABLE = (
    {"L1": "fail", "L2": "any", "L3": "any", "max_status": "not_claimable (contradicted if a counterexample exists, else undetermined)"},
    {"L1": "pass", "L2": "unproven", "L3": "any", "max_status": "supported_conditional"},
    {"L1": "pass", "L2": "pass", "L3": "not_met", "max_status": "undetermined"},
    {"L1": "pass", "L2": "pass", "L3": "met", "max_status": "supported_invariant"},
)

DECISION_PRECEDENCE = (
    "claim is refuted by L1 (b/f0): status contradicted, independent of the trial fit and of evidence gates",
    "L1 is incomplete (a required generator is missing): every evaluable claim is undetermined with reason l1_incomplete_missing_generator",
    "certificate evidence reports a symbolic-invariant / numeric-refuted conflict for a claim: that claim is undetermined with reason certificate_symbolic_numeric_conflict",
    "a nuisance probe contradicts a claim's declared nuisance assumption: that claim is undetermined with reason nuisance_assumption_contradicted",
    "optimization_status != converged: undetermined (reason optimization_*)",
    "adequacy_status == discrepancy: undetermined (reason model_discrepancy; acceleration trials are labelled model_misspecification and are never used to claim constant-velocity invariance)",
    "adequacy_status in {insufficient_evidence, indeterminate}: undetermined",
    "identifiability_status == insufficient_evidence: undetermined",
    "uncertainty > claim L3 threshold: undetermined (reason uncertainty_exceeds_threshold)",
    "otherwise: supported_conditional; supported_invariant is never emitted by this protocol version",
)

SUPPORTED_INVARIANT_ALLOWED = False
SUPPORTED_INVARIANT_BLOCKERS = (
    "no required claim has L2 proven in the full declared model with nuisances",
    "the independent L1 numerical certificate covers v, t0, b, f0 and refutes b/f0, but not the composite f0*b",
)

THRESHOLD_SELECTION = {
    "layer": "development",
    "nominal_clock_strata": ["control", "near_identity", "geometry_stress", "nominal_snr_control"],
    "candidate_quantiles": [0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99],
    "validity_target": 0.95,
    "minimum_supported": 20,
    "cap_fraction_of_claim_tolerance": 0.5,
    "rule": (
        "for each claim, consider the candidate thresholds at the declared quantiles of the "
        "development uncertainty distribution among nominal-clock trials that pass the gates; "
        "choose the largest candidate whose empirical validity (fraction of supported claims "
        "within claim tolerance) is >= 0.95 and which is <= 0.5 * claim tolerance; if no candidate "
        "is admissible, fall back to 0.5 * claim tolerance. The chosen value is frozen before the "
        "locked layer is opened."
    ),
    "note": "thresholds are selected on development data only; the locked layer never changes them",
    "canonicalisation": THRESHOLD_PRECISION_NOTE,
    "threshold_precision": THRESHOLD_PRECISION,
}

STRATA = {
    "control": "zero-perturbation control, 20 dB",
    "nominal_snr_control": "nominal-SNR control, no perturbation",
    "clock_offset": "constant clock offset (observational equivalence with t0); 20 dB",
    "clock_rate": "constant clock rate error (source rescaling); 20 dB",
    "near_identity": "near-identity clock transforms (group-axiom / stability control)",
    "model_misspecification": "constant along-track acceleration; NOT used to claim constant-velocity invariance",
    "geometry_stress": "unseen closest-approach distances; stress test, not an equal-accuracy claim",
    "null": "noise-only observation; no constant-velocity source",
}

# ---------------------------------------------------------------------------
# Canonical serialization and digests
# ---------------------------------------------------------------------------

def canonicalise_threshold(value, precision: int = THRESHOLD_PRECISION) -> Optional[float]:
    """Round a threshold to a declared number of significant decimal digits.

    Declared quantisation rule: format the float with CPython's fixed decimal
    formatting ``format(value, f".{precision}g")`` and parse the decimal string
    back to float.  The formatting uses **round-half-even** for exact ties and
    is deterministic for a fixed input; it is independent of BLAS, numpy and
    locale (unlike the full-precision development-selected float).  The decimal
    string is produced first, so the canonical value is reproducible on every
    environment.  The tie rule and boundary behaviour are pinned by tests.
    """
    if value is None:
        return None
    return float(f"{float(value):.{precision}g}")


def canonicalise_thresholds(thresholds: dict, precision: int = THRESHOLD_PRECISION) -> dict:
    return {claim_id: canonicalise_threshold(value, precision) for claim_id, value in thresholds.items()}


def full_precision_thresholds(protocol: dict) -> dict:
    """Full-precision selected thresholds from evidence (fallback: frozen canonical)."""
    selected = (evidence(protocol).get("thresholds_full_precision") or {})
    canonical = protocol_thresholds(protocol)
    return {
        claim_id: float(selected[claim_id]) if claim_id in selected and selected[claim_id] is not None else canonical.get(claim_id)
        for claim_id in canonical
    }


def canonical_json(document) -> str:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)


def canonical_digest(document) -> str:
    return hashlib.sha256(canonical_json(document).encode("utf-8")).hexdigest()


def frozen_payload_digest(frozen_payload: dict) -> str:
    return canonical_digest(frozen_payload)


def evidence_digest(evidence_block: dict) -> str:
    return canonical_digest(evidence_block)


def protocol_digest(protocol: dict) -> str:
    """Digest of the frozen payload only (never the evidence attachments)."""
    return frozen_payload_digest(protocol["frozen_payload"])


def verify_protocol_digest(protocol: dict) -> bool:
    return (
        protocol.get("protocol_digest") == frozen_payload_digest(protocol.get("frozen_payload", {}))
        and protocol.get("evidence_digest") == evidence_digest(protocol.get("evidence", {}))
        and protocol.get("protocol_version") == PROTOCOL_VERSION
    )


# ---------------------------------------------------------------------------
# Accessors (the protocol's public view)
# ---------------------------------------------------------------------------

def frozen_payload(protocol: dict) -> dict:
    return protocol["frozen_payload"]


def evidence(protocol: dict) -> dict:
    return protocol["evidence"]


def protocol_claims(protocol: dict) -> list[dict]:
    return protocol["frozen_payload"]["claims"]


def claim_definition(protocol: dict, claim_id: str) -> dict:
    for claim in protocol["frozen_payload"]["claims"]:
        if claim["claim_id"] == claim_id:
            return claim
    raise KeyError(claim_id)


def protocol_thresholds(protocol: dict) -> dict:
    return protocol["frozen_payload"]["thresholds"]


def protocol_strata(protocol: dict) -> dict:
    return protocol["frozen_payload"]["strata"]


def protocol_gate(protocol: dict) -> dict:
    return protocol["frozen_payload"]["gate"]


def protocol_decision_precedence(protocol: dict) -> tuple:
    return tuple(protocol["frozen_payload"]["decision_precedence"])


def protocol_required_generators(protocol: dict) -> tuple:
    return tuple(protocol["frozen_payload"]["group"]["required_generators"])


def protocol_generators(protocol: dict) -> list[dict]:
    return protocol["frozen_payload"]["group"]["generators"]


def protocol_model_declaration(protocol: dict) -> dict:
    return protocol["frozen_payload"]["model_declaration"]


def protocol_conventions(protocol: dict) -> dict:
    return protocol["frozen_payload"]["conventions"]


def protocol_mechanism_audit(protocol: dict) -> dict:
    return protocol["frozen_payload"]["mechanism_audit"]


def protocol_nuisance_probes(protocol: dict) -> list[dict]:
    return protocol["frozen_payload"]["nuisance_probes"]


def symbolic_proof_digest(protocol: dict) -> Optional[str]:
    return (evidence(protocol).get("symbolic_proof") or {}).get("digest")


# ---------------------------------------------------------------------------
# Evidence-backed gate checks
# ---------------------------------------------------------------------------

def _certificate_claim_map(claim_name: str) -> str:
    return {"b/f0": "b_over_f0"}.get(claim_name, claim_name)


def l1_completeness(protocol: dict) -> dict:
    """Check that every required generator is declared and proven (frozen payload)."""
    required = protocol_required_generators(protocol)
    declared = {
        generator["name"]: generator
        for generator in protocol_generators(protocol)
        if generator.get("l1_status") == "proven"
    }
    missing = [name for name in required if name not in declared]
    return {
        "required_generators": list(required),
        "proven_generators": sorted(declared),
        "missing_generators": missing,
        "status": "complete" if not missing else "incomplete",
        "l1_proven": not missing,
    }


def certificate_conflicts(protocol: dict) -> dict:
    """Certificate entries whose own symbolic and numeric verdicts disagree.

    The contract: a certificate that says ``symbolic_verdict == invariant`` while
    its ``numeric_verdict == not_invariant`` may not be used as L1 evidence for
    that claim.  A conflict on a claim the protocol already declares
    ``contradicted`` is *reconciled* (the certificate's built-in symbolic verdict
    is the ADR-0016 declaration, not this protocol's proof); a conflict on a
    support candidate blocks that claim.
    """
    evidence_block = evidence(protocol)
    certificate = evidence_block.get("certificate") or {}
    verdicts = certificate.get("per_claim_numeric_verdicts") or {}
    conflicts = []
    for claim_name, verdict in verdicts.items():
        symbolic = verdict.get("symbolic_verdict")
        numeric = verdict.get("numeric_verdict")
        if symbolic == "invariant" and numeric == "not_invariant":
            mapped = _certificate_claim_map(claim_name)
            conflicts.append(
                {
                    "certificate_claim": claim_name,
                    "claim_id": mapped,
                    "symbolic_verdict": symbolic,
                    "numeric_verdict": numeric,
                    "max_relative_mismatch": verdict.get("max_relative_mismatch"),
                }
            )
    contradicted = {
        claim["claim_id"] for claim in protocol_claims(protocol) if claim["claim_kind"] == "refuted_invariant"
    }
    blocking = [conflict for conflict in conflicts if conflict["claim_id"] not in contradicted]
    reconciled = [conflict for conflict in conflicts if conflict["claim_id"] in contradicted]
    return {"conflicts": conflicts, "blocking": blocking, "reconciled": reconciled}


def nuisance_contradictions(protocol: dict) -> list[dict]:
    """Nuisance probes whose evidence status contradicts a declared assumption."""
    results = evidence(protocol).get("nuisance_probe_results") or {}
    contradictions = []
    for declaration in protocol_nuisance_probes(protocol):
        probe_id = declaration["probe_id"]
        result = results.get(probe_id) or {}
        if result.get("status") == "contradicted":
            contradictions.append(
                {
                    "probe_id": probe_id,
                    "family": declaration.get("family"),
                    "assumption": declaration.get("assumption"),
                    "affects_claims": list(declaration.get("affects_claims", [])),
                    "evidence": result.get("basis"),
                }
            )
    return contradictions


def evidence_gate(protocol: dict) -> dict:
    """The evidence-backed gate: L1 completeness, certificate conflicts, nuisance probes."""
    completeness = l1_completeness(protocol)
    conflicts = certificate_conflicts(protocol)
    contradictions = nuisance_contradictions(protocol)
    withheld: dict[str, list[str]] = {}
    if not completeness["l1_proven"]:
        missing = ",".join(completeness["missing_generators"])
        for claim in protocol_claims(protocol):
            if claim["claim_kind"] != "refuted_invariant":
                withheld.setdefault(claim["claim_id"], []).append(f"l1_incomplete_missing_generator:{missing}")
    for conflict in conflicts["blocking"]:
        withheld.setdefault(conflict["claim_id"], []).append("certificate_symbolic_numeric_conflict")
    for contradiction in contradictions:
        for claim_id in contradiction["affects_claims"]:
            withheld.setdefault(claim_id, []).append(
                f"nuisance_assumption_contradicted:{contradiction['probe_id']}"
            )
    certificate = evidence(protocol).get("certificate") or {}
    supported_invariant_allowed = bool(protocol_gate(protocol)["supported_invariant_allowed"]) and not (
        withheld or conflicts["blocking"] or contradictions
    )
    return {
        "l1_completeness": completeness,
        "certificate_conflicts": conflicts,
        "nuisance_contradictions": contradictions,
        "withheld_claims": {key: sorted(set(value)) for key, value in sorted(withheld.items())},
        "blocked": bool(withheld) or not completeness["l1_proven"],
        "supported_invariant_allowed": supported_invariant_allowed,
        "certificate_status": certificate.get("status", "not_recorded"),
    }


def claim_certificate_view(protocol: dict, claim_id: str) -> dict:
    """Per-claim certificate evidence (attached to the per-trial claim record)."""
    evidence_block = evidence(protocol)
    certificate = evidence_block.get("certificate") or {}
    verdicts = certificate.get("per_claim_numeric_verdicts") or {}
    key = "b/f0" if claim_id == "b_over_f0" else claim_id
    if key not in verdicts:
        return {
            "status": "not_covered",
            "note": "this claim is not in the independent certificate's claim set",
            "certificate_sha256": certificate.get("certificate_sha256"),
        }
    verdict = verdicts[key]
    return {
        "status": verdict.get("numeric_verdict"),
        "max_relative_mismatch": verdict.get("max_relative_mismatch"),
        "tolerance": verdict.get("tolerance"),
        "agrees_with_method_symbolic": (
            (claim_id != "b_over_f0" and verdict.get("numeric_verdict") == "invariant")
            or (claim_id == "b_over_f0" and verdict.get("numeric_verdict") == "not_invariant")
        ),
        "certificate_sha256": certificate.get("certificate_sha256"),
        "note": (
            "certificate builtin symbolic verdict for b/f0 was the ADR 0016 declaration; the numeric "
            "verdict agrees with method T5"
            if claim_id == "b_over_f0"
            else None
        ),
    }


# ---------------------------------------------------------------------------
# Certificate evidence loading
# ---------------------------------------------------------------------------

def load_certificate(path: Optional[str] = None) -> tuple[Optional[dict], Optional[str], Optional[str]]:
    """Load the independent certificate artifact as evidence.

    Returns ``(document, sha256_of_file_bytes, path)``.  Missing/unreadable
    certificates return ``(None, None, path)``; the protocol records the absence
    rather than inventing a verdict.
    """
    path = path or DEFAULT_CERTIFICATE_PATH
    try:
        with open(path, "rb") as handle:
            payload = handle.read()
        document = json.loads(payload.decode("utf-8"))
        return document, hashlib.sha256(payload).hexdigest(), path
    except (OSError, ValueError):
        return None, None, path


def certificate_evidence(
    certificate: Optional[dict],
    certificate_sha256: Optional[str],
    certificate_path: Optional[str],
) -> dict:
    """Summarize the certificate as evidence (no code import)."""
    result = {
        "certificate_sha256": certificate_sha256,
        "certificate_path": certificate_path,
        "certificate_version": None,
        "certificate_builtin_protocol_id": None,
        "certificate_builtin_protocol_digest": None,
        "per_claim_numeric_verdicts": {},
        "symbolic_numeric_disagreements": [],
        "convention_mapping": (
            "certificate: t_obs = t_phys/k_c + beta, action (k_c f0, v, beta + t0/k_c, b/k_c, c); "
            "method: t_obs = k_m t_phys + beta, action (f0/k_m, v, k_m t0 + beta, k_m b, c); "
            "k_c = 1/k_m; identical group action (symbolic T11)"
        ),
        "status": "not_recorded",
        "reconciliation_note": (
            "the certificate's builtin symbolic verdict for b/f0 was the ADR 0016 declaration, not "
            "the method symbolic artifact; its numeric verdict (not_invariant) agrees with method T5"
        ),
    }
    if certificate is None:
        return result
    result["certificate_version"] = certificate.get("certificate_version")
    builtin = certificate.get("claims_protocol") or {}
    result["certificate_builtin_protocol_id"] = builtin.get("id")
    result["certificate_builtin_protocol_digest"] = builtin.get("digest")
    for claim in certificate.get("claims", []):
        result["per_claim_numeric_verdicts"][claim.get("claim")] = {
            "numeric_verdict": claim.get("numeric_verdict"),
            "symbolic_verdict": claim.get("symbolic_verdict"),
            "max_relative_mismatch": claim.get("max_relative_mismatch"),
            "tolerance": claim.get("tolerance"),
            "agrees_with_symbolic": claim.get("agrees_with_symbolic"),
        }
    result["symbolic_numeric_disagreements"] = certificate.get("symbolic_numeric_disagreements", [])
    result["status"] = "recorded"
    return result


# ---------------------------------------------------------------------------
# Build / seal / write / load
# ---------------------------------------------------------------------------

def _claim_record(definition: dict, thresholds: dict) -> dict:
    claim = {
        key: definition[key]
        for key in (
            "claim_id",
            "label",
            "expression",
            "units",
            "claim_kind",
            "symmetry_scope",
            "l1_status",
            "l1_theorem",
            "l2_status",
            "l2_scope",
            "l2_counterexample",
            "l2_reason",
            "nuisance_assumptions",
            "nuisance_probes",
            "conditioning",
            "max_status",
            "ceiling_reason",
            "claim_tolerance",
            "uncertainty_metric",
            "value_expression",
        )
    }
    claim["l3"] = {
        "threshold": thresholds.get(definition["claim_id"]),
        "selected_on": "development",
        "metric": definition["uncertainty_metric"]["expression"],
    }
    claim["evaluated"] = definition["claim_id"] in EVALUATED_CLAIMS
    return claim


def _build_frozen_payload(proof: dict, thresholds: dict, required_generators) -> dict:
    required = tuple(required_generators)
    declared_names = {generator["name"] for generator in GENERATOR_DECLARATIONS}
    # Required-but-undeclared generators stay in the payload: l1_completeness()
    # then reports "incomplete" and the gate withholds support.  This is a
    # contract, not a build error.
    unknown = [name for name in required if name not in declared_names]
    canonical_thresholds = canonicalise_thresholds(thresholds)
    payload = {
        "schema": PROTOCOL_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "experiment": EXPERIMENT_NAME,
        "revision_note": REVISION_NOTE,
        "authority": "ADR 0016, ADR 0017, PR-4e plan, P0 math audit",
        "model_declaration": dict(MODEL_DECLARATION),
        "conventions": dict(CONVENTIONS),
        "group": {
            "symbol": "G_clock",
            "set": "{(k_m, beta) : k_m > 0, beta in R}",
            "composition": "(k2,beta2) o (k1,beta1) = (k2*k1, k2*beta1 + beta2)",
            "identity": "(1, 0)",
            "inverse": "(1/k_m, -beta/k_m)",
            "action": "(f0,v,t0,b,c) -> (f0/k_m, v, k_m*t0 + beta, k_m*b, c)",
            "generators": [dict(generator) for generator in GENERATOR_DECLARATIONS],
            "required_generators": list(required),
            "undeclared_required_generators": unknown,
            "domain_conditions": [
                "k_m > 0",
                "beta real",
                "all parameter images stay in the declared domain (f0,v,b,c > 0)",
            ],
            "invalid_regions": [
                {"region": "k_m = 0", "why": "singular time map; b'=0 leaves the model domain"},
                {"region": "k_m < 0", "why": "b' = k_m*b < 0 leaves the model domain and reverses time orientation"},
            ],
        },
        "threshold_precision": THRESHOLD_PRECISION,
        "threshold_precision_note": THRESHOLD_PRECISION_NOTE,
        "candidate_correction": json.loads(json.dumps(CANDIDATE_CORRECTION)),
        "mechanism_audit": json.loads(json.dumps(MECHANISM_AUDIT)),
        "claims": [_claim_record(definition, canonical_thresholds) for definition in CLAIM_DEFINITIONS],
        "gate": {
            "layers": {
                "L1": "invariance under the proven symbolic group G_clock",
                "L2": "identifiability in the full declared model, including declared nuisances",
                "L3": "statistical support on the frozen locked sample",
            },
            "table": list(GATE_TABLE),
            "supported_invariant_allowed": SUPPORTED_INVARIANT_ALLOWED,
            "supported_invariant_blockers": list(SUPPORTED_INVARIANT_BLOCKERS),
            "max_status_rule": (
                "supported_invariant requires L2 proven for the claim in the full declared model and "
                "the independent L1 certificate; L1 refuted => contradicted for the invariant "
                "proposition; otherwise the ceiling is supported_conditional"
            ),
            "completeness_rule": (
                "every name in group.required_generators must be declared in group.generators with "
                "l1_status=proven; otherwise L1 is incomplete and all evaluable claims are withheld"
            ),
            "evidence_rules": {
                "certificate_conflict": (
                    "a certificate entry with symbolic_verdict=invariant and numeric_verdict=not_invariant "
                    "withholds the mapped claim unless the claim is already contradicted (reconciled)"
                ),
                "nuisance_contradiction": (
                    "a nuisance probe with evidence status contradicted withholds every claim it affects"
                ),
            },
            "required_evidence": ["certificate", "symbolic_proof"],
        },
        "decision_precedence": list(DECISION_PRECEDENCE),
        "threshold_selection": dict(THRESHOLD_SELECTION),
        "thresholds": {
            claim_id: value for claim_id, value in canonical_thresholds.items() if claim_id in CLAIMS_BY_ID
        },
        "strata": dict(STRATA),
        "nuisance_probes": [dict(probe) for probe in NUISANCE_PROBE_DECLARATIONS],
    }
    return payload


def _build_evidence(
    proof: dict,
    thresholds: Optional[dict],
    calibration: Optional[dict],
    certificate: Optional[dict],
    certificate_sha256: Optional[str],
    certificate_path: Optional[str],
    environment: Optional[dict],
    generated_at: Optional[str],
    nuisance_probe_results: Optional[dict],
) -> dict:
    probe_results = json.loads(json.dumps(DEFAULT_NUISANCE_PROBE_RESULTS))
    if nuisance_probe_results:
        for probe_id, result in nuisance_probe_results.items():
            probe_results[probe_id] = dict(result)
    proof_verification = proof.get("mechanism_audit_verification", {})
    evidence_block = {
        "schema": "pr4e-claims-evidence-v1",
        "symbolic_proof": {
            "digest": proof["proof_digest"],
            "theorem_statuses": {
                theorem["id"]: theorem["status"] for theorem in proof.get("theorems", [])
            },
            "generators": [generator["name"] for generator in proof.get("group", {}).get("generators", [])],
            "convention_reconciliation": proof.get("convention_reconciliation", {}),
        },
        "certificate": certificate_evidence(certificate, certificate_sha256, certificate_path),
        "development_calibration": calibration,
        "thresholds_full_precision": {
            claim_id: float(value) for claim_id, value in (thresholds or {}).items()
        },
        "threshold_precision": THRESHOLD_PRECISION,
        "nuisance_probe_results": probe_results,
        "mechanism_audit_verification": {
            "method_convention_max_relative_forward_error": proof_verification.get(
                "method_convention", {}
            ).get("max_relative_forward_error"),
            "certificate_convention_symbolically_equivalent": proof_verification.get(
                "certificate_convention", {}
            ).get("symbolically_equivalent"),
            "pr4d_misstatement_theorem": "T12_pr4d_misstatement",
            "pr4d_misstatement_max_relative_mismatch": proof_verification.get(
                "pr4d_misstatement", {}
            ).get("max_relative_difference"),
            "T4_T5_reverified": True,
            "audit_reported_values": {
                "method_forward_max_relative_error": 8.9e-16,
                "certificate_forward_max_relative_error": 8.5e-16,
                "pr4d_misstatement_max_relative_error": 2.5e-2,
            },
        },
        "environment": dict(environment or {}),
        "generated_at_utc": generated_at,
    }
    return evidence_block


def build_protocol(
    proof: dict,
    thresholds: Optional[dict] = None,
    calibration: Optional[dict] = None,
    certificate: Optional[dict] = None,
    certificate_sha256: Optional[str] = None,
    certificate_path: Optional[str] = None,
    environment: Optional[dict] = None,
    generated_at: Optional[str] = None,
    required_generators=REQUIRED_GENERATORS,
    nuisance_probe_results: Optional[dict] = None,
) -> dict:
    """Build the protocol: frozen payload + evidence, each with its own digest.

    The frozen declarations are asserted against the symbolic proof
    (consistency), but no proof content enters the frozen payload: only the
    digest goes into evidence, so ``protocol_digest`` is independent of the
    proof/certificate/environment/development statistics.
    """
    thresholds = dict(thresholds or {})
    proof_generators = {
        generator["name"]: generator
        for generator in proof.get("group", {}).get("generators", [])
    }
    for generator in GENERATOR_DECLARATIONS:
        peer = proof_generators.get(generator["name"])
        if peer is None:
            raise ValueError(
                f"symbolic proof does not declare generator {generator['name']!r}; L1 is unproven"
            )
        if peer.get("l1_status") != generator["l1_status"]:
            raise ValueError(
                f"generator {generator['name']!r}: protocol declares {generator['l1_status']} "
                f"but proof reports {peer.get('l1_status')}"
            )
    verdicts = proof["claim_verdicts"]
    for definition in CLAIM_DEFINITIONS:
        verdict = verdicts[definition["claim_id"]]
        if verdict["l1"] != definition["l1_status"]:
            raise ValueError(
                f"protocol/symbolic mismatch for {definition['claim_id']}: "
                f"declared {definition['l1_status']} vs proof {verdict['l1']}"
            )
        if verdict["max_status"] != definition["max_status"]:
            raise ValueError(
                f"protocol/symbolic max_status mismatch for {definition['claim_id']}: "
                f"{definition['max_status']} vs {verdict['max_status']}"
            )
    payload = _build_frozen_payload(proof, thresholds, required_generators)
    evidence_block = _build_evidence(
        proof,
        thresholds,
        calibration,
        certificate,
        certificate_sha256,
        certificate_path,
        environment,
        generated_at,
        nuisance_probe_results,
    )
    protocol = {
        "schema": PROTOCOL_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "protocol_digest": frozen_payload_digest(payload),
        "frozen_payload": payload,
        "evidence_digest": evidence_digest(evidence_block),
        "evidence": evidence_block,
    }
    return protocol


def seal_protocol(protocol: dict) -> dict:
    """Recompute both digests from the current payload/evidence (used after edits)."""
    sealed = dict(protocol)
    sealed["protocol_version"] = PROTOCOL_VERSION
    sealed["schema"] = PROTOCOL_SCHEMA
    sealed["protocol_digest"] = frozen_payload_digest(sealed["frozen_payload"])
    sealed["evidence_digest"] = evidence_digest(sealed["evidence"])
    return sealed


def protocol_bytes(protocol: dict) -> bytes:
    return (json.dumps(protocol, indent=1, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def write_protocol(protocol: dict, path: str) -> str:
    payload = protocol_bytes(protocol)
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(payload)
    return hashlib.sha256(payload).hexdigest()


def load_protocol(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        protocol = json.load(handle)
    if not verify_protocol_digest(protocol):
        raise ValueError(f"claims protocol digest mismatch in {path}")
    return protocol
