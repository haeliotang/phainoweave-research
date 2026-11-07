"""Tests for the PR-4e C1 claims layer.

The load-bearing properties:

1. the symbolic proof is internally consistent (group axioms, forward identity,
   convention equivalence, PR-4d misstatement control, negative control) and
   deterministic;
2. the claim protocol is honest: ``b/f0`` is refuted and replaced by ``b*f0``,
   nothing is allowed to reach ``supported_invariant``, and the certificate is
   recorded as evidence only;
3. the frozen payload digest is stable across evidence attachments, while the
   evidence digest changes (P0-1);
4. the evidence-backed gate withholds support on contract violations: an
   incomplete generator set, a certificate whose symbolic and numeric verdicts
   disagree, and a contradicted nuisance assumption (P0-2);
5. claim evaluation takes no truth and respects the declared precedence;
6. the locked grid, seed bases and artifact schema are the declared ones;
7. the boundary report carries the negative results and the mechanism audit.
"""

from __future__ import annotations

import inspect
import json
import pathlib
import sys

import numpy as np
import pytest
import sympy as sp

from phaino_claims import boundary as boundary_module
from phaino_claims import symbolic
from phaino_claims.symbolic import forward_model_numeric, nominal_model_numeric
from phaino_claims.claims import (
    STATUSES,
    apply_claim_statuses,
    claim_metrics,
    claim_truth,
    within_tolerance,
)
from phaino_claims.claims_protocol import (
    ALL_CLAIMS,
    CLAIMS_BY_ID,
    DECISION_PRECEDENCE,
    EVALUATED_CLAIMS,
    PROTOCOL_VERSION,
    THRESHOLD_PRECISION,
    canonicalise_threshold,
    build_protocol,
    certificate_conflicts,
    certificate_evidence,
    claim_certificate_view,
    evidence,
    evidence_digest,
    evidence_gate,
    l1_completeness,
    load_protocol,
    nuisance_contradictions,
    protocol_claims,
    protocol_conventions,
    protocol_decision_precedence,
    protocol_digest,
    protocol_gate,
    protocol_mechanism_audit,
    protocol_thresholds,
    seal_protocol,
    symbolic_proof_digest,
    verify_protocol_digest,
    write_protocol,
)
from phaino_claims.experiment import (
    DEV_SEED_BASE,
    LOCKED_SEED_BASE,
    STRATA,
    _base_conditions,
    condition_seed,
    run_layer,
    select_thresholds,
)

REPO = pathlib.Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def proof() -> dict:
    return symbolic.derive_proof()


def _thresholds() -> dict:
    return {"v": 1e-4, "f0_times_b": 1e-4, "f0": 1e-4, "b": 1e-4, "t0": 1e-3}


def _fake_certificate(conflicting_claim: str | None = None) -> dict:
    claims = [
        {"claim": "v", "numeric_verdict": "invariant", "symbolic_verdict": "invariant", "max_relative_mismatch": 0.0, "tolerance": 1e-12, "agrees_with_symbolic": True},
        {"claim": "b/f0", "numeric_verdict": "not_invariant", "symbolic_verdict": "invariant", "max_relative_mismatch": 0.049375, "tolerance": 1e-12, "agrees_with_symbolic": False},
        {"claim": "t0", "numeric_verdict": "not_invariant", "symbolic_verdict": "not_invariant", "max_relative_mismatch": 0.3, "tolerance": 1e-12, "agrees_with_symbolic": True},
        {"claim": "b", "numeric_verdict": "not_invariant", "symbolic_verdict": "not_invariant", "max_relative_mismatch": 0.025, "tolerance": 1e-12, "agrees_with_symbolic": True},
        {"claim": "f0", "numeric_verdict": "not_invariant", "symbolic_verdict": "not_invariant", "max_relative_mismatch": 0.025, "tolerance": 1e-12, "agrees_with_symbolic": True},
    ]
    if conflicting_claim is not None:
        for entry in claims:
            if entry["claim"] == conflicting_claim:
                entry["symbolic_verdict"] = "invariant"
                entry["numeric_verdict"] = "not_invariant"
                entry["agrees_with_symbolic"] = False
    return {
        "certificate_version": "1.0.0",
        "claims_protocol": {"id": "builtin-e0-clock-invariance", "digest": "8203c2f7bc0085507d8122de746753a0b7655b8cf1eae985dffd8f2bebbe5568"},
        "claims": claims,
        "symbolic_numeric_disagreements": [{"claim": "b/f0"}],
    }


@pytest.fixture(scope="module")
def protocol(proof) -> dict:
    return build_protocol(
        proof,
        thresholds=_thresholds(),
        calibration={"layer": "development", "per_claim": {}},
        certificate=_fake_certificate(),
        certificate_sha256="a" * 64,
        certificate_path="/tmp/fake-certificate.json",
    )


def _hardened(params=None, se=None, optimization_status="converged") -> dict:
    values = {"f0": 500.0, "v": 250.0, "t0": 20.0, "b": 3000.0}
    errors = {"f0": 5e-4, "v": 2.5e-4, "t0": 2e-5, "b": 3e-3}
    values.update(params or {})
    errors.update(se or {})
    return {"params": values, "se": errors, "optimization_status": optimization_status}


def _adequacy(adequacy_status="adequate", identifiability_status="not_separately_identifiable") -> dict:
    return {"model_adequacy_status": adequacy_status, "identifiability_status": identifiability_status}


def _mutated(protocol: dict) -> dict:
    return json.loads(json.dumps(protocol))


def _statuses(protocol: dict) -> dict:
    metrics = claim_metrics(_hardened(), _adequacy())
    return {claim["claim_id"]: claim for claim in apply_claim_statuses(metrics, protocol)}


# ---------------------------------------------------------------------------
# 1. Symbolic proof
# ---------------------------------------------------------------------------

def test_group_axioms_are_proven_symbolically(proof):
    group_theorem = [theorem for theorem in proof["theorems"] if theorem["id"] == "T1_group_definition"][0]
    assert group_theorem["status"] == "proven"
    axioms = {axiom["id"]: axiom for axiom in group_theorem["axioms"]}
    assert set(axioms) == {"G1_identity", "G2_closure", "G3_inverse", "G4_domain"}
    for axiom in axioms.values():
        assert axiom["status"] == "proven", axiom["id"]
    assert proof["group"]["identity"] == "(1, 0)"
    assert proof["group"]["inverse"] == "(1/k, -beta/k)"
    assert any("k = 0" in region["region"] for region in proof["group"]["invalid_regions"])
    assert any("k < 0" in region["region"] for region in proof["group"]["invalid_regions"])


def test_proof_declares_required_generators(proof):
    generators = {generator["name"]: generator for generator in proof["group"]["generators"]}
    assert set(proof["group"]["required_generators"]) == {"clock_offset", "clock_rate"}
    assert set(generators) == {"clock_offset", "clock_rate"}
    for generator in generators.values():
        assert generator["l1_status"] == "proven"
        assert generator["theorem"] == "T2_forward_invariance"


def test_forward_invariance_identity_is_exactly_zero(proof):
    theorem = [theorem for theorem in proof["theorems"] if theorem["id"] == "T2_forward_invariance"][0]
    assert theorem["status"] == "proven"
    assert theorem["difference"] == "0"
    assert len(theorem["lhs_hash"]) == 64
    assert len(theorem["rhs_hash"]) == 64


def test_invariance_and_refutation_table(proof):
    table = {row["quantity"]: row for row in proof["invariance_tables"]["general_group"]}
    assert table["v"]["invariant"] is True
    assert table["f0_times_b"]["invariant"] is True
    assert table["f0"]["invariant"] is False
    assert table["t0"]["invariant"] is False
    assert table["b"]["invariant"] is False
    assert table["b_over_f0"]["invariant"] is False
    assert "k**2" in table["b_over_f0"]["difference"]
    counterexamples = proof["counterexamples"]
    assert counterexamples["b_over_f0"]["rate"]["changed"] is True
    assert counterexamples["b_over_f0"]["offset"]["changed"] is False
    assert counterexamples["t0"]["offset"]["changed"] is True
    assert counterexamples["b"]["rate"]["changed"] is True
    assert counterexamples["f0"]["rate"]["changed"] is True


def test_convention_reconciliation_with_certificate(proof):
    reconciliation = proof["convention_reconciliation"]
    assert reconciliation["equivalent"] is True
    assert all(check == "0" for check in reconciliation["action_equivalence_checks"])
    assert reconciliation["observation_equivalence_check"] == "0"
    assert "k_c = 1 / k_m" in reconciliation["mapping"] or "k_c=1/k" in reconciliation["mapping"].replace(" ", "")
    certificate_theorem = [theorem for theorem in proof["theorems"] if theorem["id"] == "T11_convention_equivalence"][0]
    assert certificate_theorem["status"] == "proven"


def test_pr4d_misstatement_control(proof):
    theorem = [theorem for theorem in proof["theorems"] if theorem["id"] == "T12_pr4d_misstatement"][0]
    assert theorem["status"] == "refuted"
    control = proof["numeric_checks"]["pr4d_misstatement_control"]
    assert control["threshold_exceeded"] is True
    assert control["max_relative_difference"] > 1e-3
    assert "t0/k" in control["statement"]
    verification = proof["mechanism_audit_verification"]
    assert verification["T4_f0b_invariance"].endswith("8.9e-16")
    assert verification["T5_b_over_f0_refuted"].startswith("re-verified")
    assert verification["method_convention"]["max_relative_forward_error"] <= 1e-15


def test_negative_control_rejects_wrong_transformation(proof):
    control = proof["numeric_checks"]["negative_control"]
    assert control["threshold_exceeded"] is True
    assert control["max_relative_difference"] > 1e-3
    theorem = [theorem for theorem in proof["theorems"] if theorem["id"] == "T10_negative_control"][0]
    assert theorem["status"] == "pass"
    assert theorem["symbolic_difference"] != "0"


def test_numeric_forward_preservation(proof):
    forward = proof["numeric_checks"]["forward_preservation"]
    assert forward["passed"] is True
    assert forward["max_relative_error"] <= forward["tolerance"]
    assert forward["kind"] == "internal_numeric_consistency_check"


def test_identifiability_checks(proof):
    identity = proof["numeric_checks"]["identifiability"]
    nominal = identity["nominal_model_c_known"]
    assert nominal["full_rank"] is True
    assert nominal["rank"] == 4
    assert nominal["scaled_condition_number"] < 1e4
    full = identity["full_model_c_unknown"]
    assert full["rank"] == 4
    assert full["null_space_dimension"] == 1
    assert full["alignment_with_scaling_direction"] > 0.999


def test_proof_digest_is_deterministic_and_verifiable(proof):
    assert len(proof["proof_digest"]) == 64
    assert symbolic.verify_proof_digest(proof)
    tampered = dict(proof)
    tampered["proof_digest"] = "0" * 64
    assert not symbolic.verify_proof_digest(tampered)


def test_proof_markdown_has_required_sections(proof):
    markdown = symbolic.render_markdown(proof)
    for fragment in (
        "symbolic proof",
        "Group axioms",
        "Convention reconciliation",
        "T3_v_invariance",
        "T5_b_over_f0_refuted",
        "Negative control",
        "limitations",
    ):
        assert fragment.lower() in markdown.lower(), fragment


def test_proof_artifact_schema(proof):
    assert proof["artifact"] == "c1-symbolic-proof"
    assert proof["sympy_version"]
    assert {theorem["kind"] for theorem in proof["theorems"]} >= {
        "group",
        "identity",
        "invariance",
        "counterexample",
        "negative_control",
        "convention_mapping",
    }
    assert len({theorem["id"] for theorem in proof["theorems"]}) == len(proof["theorems"])
    assert set(proof["claim_verdicts"]) == set(ALL_CLAIMS)
    payload = json.dumps(proof, allow_nan=False)
    assert "NaN" not in payload and "Infinity" not in payload


# ---------------------------------------------------------------------------
# 2. Frozen payload and digest stability (P0-1)
# ---------------------------------------------------------------------------

def test_protocol_declares_corrected_claim_set(protocol):
    assert protocol["protocol_version"] == PROTOCOL_VERSION == "pr4e-claims-1.3.0"
    claims = {claim["claim_id"]: claim for claim in protocol_claims(protocol)}
    assert set(claims) == set(ALL_CLAIMS)
    assert claims["v"]["max_status"] == "supported_conditional"
    assert claims["f0_times_b"]["max_status"] == "supported_conditional"
    assert claims["b_over_f0"]["max_status"] == "contradicted"
    assert claims["b_over_f0"]["l1_status"] == "refuted"
    assert claims["b_over_f0"]["l1_theorem"] == "T5_b_over_f0_refuted"
    assert claims["t0"]["claim_kind"] == "conditional"
    assert claims["b"]["claim_kind"] == "conditional"
    assert claims["f0"]["claim_kind"] == "conditional"
    payload = protocol["frozen_payload"]
    assert payload["candidate_correction"]["replacement"] == "f0*b"
    assert payload["candidate_correction"]["status"] == "refuted"
    assert protocol_gate(protocol)["supported_invariant_allowed"] is False
    assert protocol_gate(protocol)["supported_invariant_blockers"]
    assert protocol_decision_precedence(protocol) == tuple(DECISION_PRECEDENCE)


def test_frozen_payload_contains_only_frozen_declarations(protocol):
    payload = protocol["frozen_payload"]
    required_frozen = {
        "protocol_version",
        "model_declaration",
        "conventions",
        "group",
        "mechanism_audit",
        "claims",
        "gate",
        "decision_precedence",
        "thresholds",
    }
    assert required_frozen <= set(payload)
    for evidence_key in ("evidence", "certificate", "environment", "generated_at_utc", "development_calibration"):
        assert evidence_key not in payload
    assert evidence(protocol)["development_calibration"] is not None


def test_protocol_digest_is_stable_across_evidence(proof):
    """P0-1: no certificate / old digest / different digest → same frozen digest."""
    baseline = build_protocol(proof, thresholds=_thresholds())
    with_certificate_a = build_protocol(
        proof,
        thresholds=_thresholds(),
        certificate=_fake_certificate(),
        certificate_sha256="a" * 64,
        certificate_path="/tmp/cert-a.json",
    )
    with_certificate_b = build_protocol(
        proof,
        thresholds=_thresholds(),
        calibration={"layer": "development", "per_claim": {"v": {"chosen_threshold": 1.0}}},
        certificate=_fake_certificate(conflicting_claim="v"),
        certificate_sha256="b" * 64,
        certificate_path="/tmp/cert-b.json",
        environment={"python": "3.14.0", "machine": "test"},
        generated_at="2026-11-05T00:00:00Z",
    )
    assert baseline["protocol_digest"] == with_certificate_a["protocol_digest"]
    assert baseline["protocol_digest"] == with_certificate_b["protocol_digest"]
    assert baseline["frozen_payload"] == with_certificate_a["frozen_payload"]
    assert baseline["frozen_payload"] == with_certificate_b["frozen_payload"]
    assert baseline["evidence_digest"] != with_certificate_a["evidence_digest"]
    assert with_certificate_a["evidence_digest"] != with_certificate_b["evidence_digest"]
    assert protocol_digest(with_certificate_b) == with_certificate_b["protocol_digest"]


def test_threshold_canonicalisation_makes_frozen_digest_jitter_proof(proof):
    """P0-1 1.3.0: last-bit/BLAS jitter in selected thresholds must not move the digest."""
    raw = {
        "v": 1.5962202539374443e-05,
        "f0_times_b": 7.144609392659601e-05,
        "f0": 2.3259895865761778e-05,
        "b": 6.755384208147497e-05,
        "t0": 0.0005611915841206326,
    }
    baseline = build_protocol(proof, thresholds=raw)
    jittered = build_protocol(
        proof, thresholds={claim_id: value * (1.0 + 1e-14) for claim_id, value in raw.items()}
    )
    assert baseline["protocol_digest"] == jittered["protocol_digest"]
    assert baseline["frozen_payload"] == jittered["frozen_payload"]
    beyond = build_protocol(
        proof, thresholds={claim_id: value * (1.0 + 1e-2) for claim_id, value in raw.items()}
    )
    assert beyond["protocol_digest"] != baseline["protocol_digest"]
    assert beyond["frozen_payload"] != baseline["frozen_payload"]


def test_frozen_thresholds_are_canonical_and_consistent(proof):
    raw = {
        "v": 1.5962202539374443e-05,
        "f0_times_b": 7.144609392659601e-05,
        "f0": 2.3259895865761778e-05,
        "b": 6.755384208147497e-05,
        "t0": 0.0005611915841206326,
    }
    protocol = build_protocol(proof, thresholds=raw)
    payload = protocol["frozen_payload"]
    assert payload["threshold_precision"] == THRESHOLD_PRECISION == 6
    assert "canonicalised" in payload["threshold_precision_note"]
    for claim_id, raw_value in raw.items():
        canonical = canonicalise_threshold(raw_value)
        assert payload["thresholds"][claim_id] == canonical
        claim = next(claim for claim in payload["claims"] if claim["claim_id"] == claim_id)
        assert claim["l3"]["threshold"] == canonical
        # canonical form round-trips at the declared precision
        assert canonicalise_threshold(canonical) == canonical
    assert protocol_thresholds(protocol) == payload["thresholds"]


def test_frozen_payload_has_no_full_precision_selected_threshold(proof):
    raw = {
        "v": 1.5962202539374443e-05,
        "f0_times_b": 7.144609392659601e-05,
        "f0": 2.3259895865761778e-05,
        "b": 6.755384208147497e-05,
        "t0": 0.0005611915841206326,
    }
    protocol = build_protocol(proof, thresholds=raw)

    def numeric_leaves(node):
        if isinstance(node, dict):
            for value in node.values():
                yield from numeric_leaves(value)
        elif isinstance(node, list):
            for value in node:
                yield from numeric_leaves(value)
        elif isinstance(node, float):
            yield node

    for value in numeric_leaves(protocol["frozen_payload"]):
        assert canonicalise_threshold(value) == value, value
    full_precision = evidence(protocol)["thresholds_full_precision"]
    assert full_precision == {claim_id: float(value) for claim_id, value in raw.items()}
    assert all(full_precision[claim_id] != protocol["frozen_payload"]["thresholds"][claim_id] for claim_id in ("v", "t0"))


def test_seal_changes_only_evidence_digest(protocol):
    baseline_digest = protocol["protocol_digest"]
    baseline_evidence = protocol["evidence_digest"]
    mutated = _mutated(protocol)
    mutated["evidence"]["certificate"]["per_claim_numeric_verdicts"]["v"]["max_relative_mismatch"] = 0.5
    sealed = seal_protocol(mutated)
    assert sealed["protocol_digest"] == baseline_digest
    assert sealed["evidence_digest"] != baseline_evidence
    assert verify_protocol_digest(sealed)
    # A frozen-payload mutation DOES change the protocol digest.
    mutated_payload = _mutated(protocol)
    mutated_payload["frozen_payload"]["thresholds"]["v"] = 0.5
    sealed_payload = seal_protocol(mutated_payload)
    assert sealed_payload["protocol_digest"] != baseline_digest


def test_protocol_digest_roundtrip(tmp_path, protocol):
    path = tmp_path / "claims-protocol.json"
    write_protocol(protocol, str(path))
    loaded = load_protocol(str(path))
    assert loaded["protocol_digest"] == protocol["protocol_digest"]
    assert loaded["evidence_digest"] == protocol["evidence_digest"]
    assert verify_protocol_digest(loaded)
    tampered = _mutated(loaded)
    tampered["frozen_payload"]["thresholds"]["v"] = 1.0
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError):
        load_protocol(str(path))


def test_protocol_records_certificate_as_evidence(protocol):
    certificate = evidence(protocol)["certificate"]
    assert certificate["status"] == "recorded"
    assert certificate["certificate_sha256"] == "a" * 64
    assert certificate["certificate_version"] == "1.0.0"
    assert certificate["certificate_builtin_protocol_digest"].startswith("8203c2f7")
    assert certificate["per_claim_numeric_verdicts"]["b/f0"]["numeric_verdict"] == "not_invariant"
    assert claim_certificate_view(protocol, "v")["status"] == "invariant"
    assert claim_certificate_view(protocol, "v")["max_relative_mismatch"] == 0.0
    assert claim_certificate_view(protocol, "b_over_f0")["status"] == "not_invariant"
    assert claim_certificate_view(protocol, "b_over_f0")["agrees_with_method_symbolic"] is True
    assert claim_certificate_view(protocol, "f0_times_b")["status"] == "not_covered"
    assert "b/f0" in certificate["reconciliation_note"]


def test_protocol_without_certificate_records_absence(proof):
    protocol = build_protocol(proof, thresholds=_thresholds(), certificate=None)
    assert evidence(protocol)["certificate"]["status"] == "not_recorded"
    assert evidence(protocol)["certificate"]["certificate_sha256"] is None
    assert evidence_gate(protocol)["certificate_status"] == "not_recorded"


def test_protocol_rejects_symbolic_mismatch(proof):
    tampered = json.loads(json.dumps(proof))
    tampered["claim_verdicts"]["v"]["l1"] = "refuted"
    with pytest.raises(ValueError):
        build_protocol(tampered, thresholds=_thresholds())


def test_protocol_rejects_missing_generator_in_proof(proof):
    tampered = json.loads(json.dumps(proof))
    tampered["group"]["generators"] = [
        generator for generator in tampered["group"]["generators"] if generator["name"] != "clock_rate"
    ]
    with pytest.raises(ValueError):
        build_protocol(tampered, thresholds=_thresholds())


def test_no_claim_can_reach_supported_invariant(protocol):
    for claim in protocol_claims(protocol):
        assert claim["max_status"] != "supported_invariant"
        assert claim["max_status"] in ("supported_conditional", "contradicted", "undetermined")


def test_mechanism_audit_is_frozen_in_protocol(protocol):
    audit = protocol_mechanism_audit(protocol)
    assert audit["correct_actions"]["method"]["action"] == "(f0/k_m, v, k_m*t0 + beta, k_m*b, c)"
    assert audit["correct_actions"]["method"]["preserves_forward"] is True
    assert audit["correct_actions"]["method"]["max_relative_forward_mismatch_reported_by_audit"] == 8.9e-16
    assert audit["correct_actions"]["certificate"]["max_relative_forward_mismatch_reported_by_audit"] == 8.5e-16
    misstatement = audit["pr4d_misstatement"]
    assert misstatement["written_rate_triple"] == "(f0' = k f0, b' = k b, t0' = t0/k)"
    assert misstatement["preserves_forward"] is False
    assert misstatement["max_relative_mismatch_reported_by_audit"] == 2.5e-2
    assert misstatement["used_by_this_protocol"] is False
    assert audit["reverification"]["T4_f0b_invariance"].endswith("8.9e-16")
    conventions = protocol_conventions(protocol)
    assert conventions["mapping"] == "k_c = 1 / k_m (reciprocal rate conventions; identical group action)"


# ---------------------------------------------------------------------------
# 3. Evidence-backed gate contract tests (P0-2)
# ---------------------------------------------------------------------------

def test_l1_complete_on_baseline(protocol):
    completeness = l1_completeness(protocol)
    assert completeness["status"] == "complete"
    assert completeness["missing_generators"] == []
    gate = evidence_gate(protocol)
    assert gate["blocked"] is False
    assert gate["withheld_claims"] == {}
    # The certificate's built-in b/f0 conflict is reconciled, not blocking.
    conflicts = certificate_conflicts(protocol)
    assert [conflict["claim_id"] for conflict in conflicts["blocking"]] == []
    assert [conflict["claim_id"] for conflict in conflicts["reconciled"]] == ["b_over_f0"]


def test_l1_incomplete_withholds_support(protocol):
    """P0-2(b): a required generator missing from the protocol means L1 incomplete."""
    mutated = _mutated(protocol)
    mutated["frozen_payload"]["group"]["generators"] = [
        generator
        for generator in mutated["frozen_payload"]["group"]["generators"]
        if generator["name"] != "clock_rate"
    ]
    incomplete = seal_protocol(mutated)
    completeness = l1_completeness(incomplete)
    assert completeness["status"] == "incomplete"
    assert completeness["missing_generators"] == ["clock_rate"]
    gate = evidence_gate(incomplete)
    assert gate["blocked"] is True
    statuses = _statuses(incomplete)
    for claim_id in EVALUATED_CLAIMS:
        assert statuses[claim_id]["status"] == "undetermined", claim_id
        assert any(
            reason.startswith("l1_incomplete_missing_generator") for reason in statuses[claim_id]["reason_codes"]
        )
    assert statuses["b_over_f0"]["status"] == "contradicted"
    assert all(claim["status"] != "supported_conditional" for claim in statuses.values())


def test_certificate_symbolic_numeric_conflict_withholds_claim(proof):
    """P0-2(a): certificate says symbolic invariant but numeric refutes → withhold."""
    baseline = build_protocol(proof, thresholds=_thresholds(), certificate=_fake_certificate())
    conflicted = build_protocol(
        proof,
        thresholds=_thresholds(),
        certificate=_fake_certificate(conflicting_claim="v"),
        certificate_sha256="c" * 64,
    )
    assert conflicted["protocol_digest"] == baseline["protocol_digest"]  # evidence only
    conflicts = certificate_conflicts(conflicted)
    assert [conflict["claim_id"] for conflict in conflicts["blocking"]] == ["v"]
    gate = evidence_gate(conflicted)
    assert gate["withheld_claims"] == {"v": ["certificate_symbolic_numeric_conflict"]}
    statuses = _statuses(conflicted)
    assert statuses["v"]["status"] == "undetermined"
    assert statuses["v"]["reason_codes"] == ["certificate_symbolic_numeric_conflict"]
    assert statuses["f0_times_b"]["status"] == "supported_conditional"
    assert conflicted["evidence_digest"] != baseline["evidence_digest"]


def test_nuisance_probe_contradiction_withholds_affected_claims(protocol):
    """P0-2(c): a contradicted nuisance probe withholds every claim it affects."""
    mutated = _mutated(protocol)
    mutated["evidence"]["nuisance_probe_results"]["sound_speed_scaling"] = {
        "status": "contradicted",
        "basis": "contract test: probe contradicts the known-c assumption",
    }
    contradicted = seal_protocol(mutated)
    assert contradicted["protocol_digest"] == protocol["protocol_digest"]
    assert contradicted["evidence_digest"] != protocol["evidence_digest"]
    items = nuisance_contradictions(contradicted)
    assert [item["probe_id"] for item in items] == ["sound_speed_scaling"]
    gate = evidence_gate(contradicted)
    assert gate["blocked"] is True
    for claim_id in ("v", "f0_times_b", "b"):
        assert claim_id in gate["withheld_claims"]
    statuses = _statuses(contradicted)
    for claim_id in ("v", "f0_times_b", "b"):
        assert statuses[claim_id]["status"] == "undetermined"
        assert statuses[claim_id]["reason_codes"] == ["nuisance_assumption_contradicted:sound_speed_scaling"]
    for claim_id in ("t0", "f0"):
        assert statuses[claim_id]["status"] == "supported_conditional"


# ---------------------------------------------------------------------------
# 4. Claim evaluation (no truth)
# ---------------------------------------------------------------------------

def test_claim_evaluation_signatures_have_no_truth():
    metrics_parameters = set(inspect.signature(claim_metrics).parameters)
    assert metrics_parameters == {"hardened", "adequacy"}
    apply_parameters = set(inspect.signature(apply_claim_statuses).parameters)
    assert apply_parameters == {"metrics", "protocol"}
    for forbidden in ("scenario", "truth", "seed", "evaluation_only"):
        assert forbidden not in metrics_parameters
        assert forbidden not in apply_parameters


def test_claim_metrics_values_and_uncertainties():
    hardened = _hardened()
    metrics = claim_metrics(hardened, _adequacy())
    by_claim = {metric["claim_id"]: metric for metric in metrics}
    assert set(by_claim) == set(ALL_CLAIMS)
    assert by_claim["v"]["value"] == pytest.approx(250.0)
    assert by_claim["f0_times_b"]["value"] == pytest.approx(500.0 * 3000.0)
    assert by_claim["t0"]["value"] == pytest.approx(20.0)
    assert by_claim["b_over_f0"]["value"] == pytest.approx(6.0)
    assert by_claim["v"]["uncertainty"] == pytest.approx(2.5e-4 / 250.0)
    assert by_claim["t0"]["uncertainty"] == pytest.approx(2e-5)
    assert all(metric["gates_ok"] for metric in metrics)


def test_status_precedence(protocol):
    statuses = _statuses(protocol)
    for claim_id in EVALUATED_CLAIMS:
        assert statuses[claim_id]["status"] == "supported_conditional", claim_id
    assert statuses["b_over_f0"]["status"] == "contradicted"
    assert statuses["b_over_f0"]["reason_codes"] == ["l1_counterexample_T5_b_over_f0_refuted"]
    assert all(claim["status"] != "supported_invariant" for claim in statuses.values())


def test_statuses_undetermined_when_gates_fail(protocol):
    metrics = claim_metrics(_hardened(optimization_status="indeterminate"), _adequacy())
    statuses = {claim["claim_id"]: claim for claim in apply_claim_statuses(metrics, protocol)}
    for claim_id in EVALUATED_CLAIMS:
        assert statuses[claim_id]["status"] == "undetermined"
        assert "optimization_not_converged" in statuses[claim_id]["reason_codes"]
    assert statuses["b_over_f0"]["status"] == "contradicted"  # claim-level, independent of the fit

    metrics = claim_metrics(_hardened(), _adequacy(adequacy_status="discrepancy"))
    statuses = {claim["claim_id"]: claim for claim in apply_claim_statuses(metrics, protocol)}
    assert statuses["v"]["status"] == "undetermined"
    assert "adequacy_not_adequate" in statuses["v"]["reason_codes"]

    metrics = claim_metrics(_hardened(), _adequacy(identifiability_status="insufficient_evidence"))
    statuses = {claim["claim_id"]: claim for claim in apply_claim_statuses(metrics, protocol)}
    assert "identifiability_insufficient" in statuses["v"]["reason_codes"]


def test_statuses_undetermined_when_uncertainty_above_threshold(protocol):
    hardened = _hardened(se={"v": 10.0, "b": 100.0, "f0": 10.0, "t0": 1.0})
    metrics = claim_metrics(hardened, _adequacy())
    statuses = {claim["claim_id"]: claim for claim in apply_claim_statuses(metrics, protocol)}
    for claim_id in EVALUATED_CLAIMS:
        assert statuses[claim_id]["status"] == "undetermined"
        assert "uncertainty_exceeds_threshold" in statuses[claim_id]["reason_codes"]


def test_claim_statuses_do_not_read_evaluation_only_truth():
    metrics = claim_metrics(_hardened(), _adequacy())
    protocol = build_protocol(symbolic.derive_proof(), thresholds=_thresholds())
    statuses_a = apply_claim_statuses(metrics, protocol)
    statuses_b = apply_claim_statuses(metrics, protocol)
    assert json.dumps(statuses_a, sort_keys=True) == json.dumps(statuses_b, sort_keys=True)


# ---------------------------------------------------------------------------
# 5. Grids and seeds
# ---------------------------------------------------------------------------

def test_locked_grid_matches_the_preregistered_levels():
    conditions = _base_conditions("locked")
    assert len(conditions) == 20
    by_stratum: dict[str, list] = {}
    for condition in conditions:
        by_stratum.setdefault(condition.stratum, []).append(condition)
    assert len(by_stratum["clock_offset"]) == 4
    assert len(by_stratum["clock_rate"]) == 4
    assert len(by_stratum["near_identity"]) == 4
    assert len(by_stratum["model_misspecification"]) == 2
    assert len(by_stratum["geometry_stress"]) == 3
    assert len(by_stratum["control"]) == 1
    assert len(by_stratum["nominal_snr_control"]) == 1
    assert len(by_stratum["null"]) == 1
    offsets = sorted(condition.scenario.clock_offset_s for condition in by_stratum["clock_offset"])
    assert offsets == [-3.0, -0.5, 0.5, 3.0]
    rates = sorted(condition.scenario.clock_scale_ppm for condition in by_stratum["clock_rate"])
    assert rates == [-25000.0, -10000.0, 10000.0, 25000.0]
    accels = sorted(condition.scenario.accel for condition in by_stratum["model_misspecification"])
    assert accels == [0.2, 0.4]
    distances = sorted(condition.scenario.b for condition in by_stratum["geometry_stress"])
    assert distances == [150.0, 600.0, 5000.0]
    near = by_stratum["near_identity"]
    assert sorted(abs(condition.scenario.clock_offset_s) for condition in near) == [0.0, 0.0, 1e-3, 1e-3]
    assert sorted(abs(condition.scenario.clock_scale_ppm) for condition in near) == [0.0, 0.0, 10.0, 10.0]
    assert any(condition.scenario.emit_signal is False for condition in by_stratum["null"])


def test_locked_and_development_grids_and_seeds_are_disjoint():
    development = _base_conditions("development")
    locked = _base_conditions("locked")
    assert len(development) == 19
    assert LOCKED_SEED_BASE > DEV_SEED_BASE > 20_326_099
    dev_seeds = {
        condition_seed("development", index, trial)
        for index in range(len(development))
        for trial in range(3)
    }
    locked_seeds = {
        condition_seed("locked", index, trial)
        for index in range(len(locked))
        for trial in range(3)
    }
    assert dev_seeds.isdisjoint(locked_seeds)
    assert min(locked_seeds) >= LOCKED_SEED_BASE
    assert min(dev_seeds) >= DEV_SEED_BASE
    assert condition_seed("locked", 3, 7) == LOCKED_SEED_BASE + 3000 + 7


def test_dev_levels_differ_from_locked_levels():
    dev_offsets = {c.scenario.clock_offset_s for c in _base_conditions("development") if c.stratum == "clock_offset"}
    locked_offsets = {c.scenario.clock_offset_s for c in _base_conditions("locked") if c.stratum == "clock_offset"}
    assert dev_offsets != locked_offsets
    dev_rates = {c.scenario.clock_scale_ppm for c in _base_conditions("development") if c.stratum == "clock_rate"}
    locked_rates = {c.scenario.clock_scale_ppm for c in _base_conditions("locked") if c.stratum == "clock_rate"}
    assert dev_rates != locked_rates
    dev_geometry = {c.scenario.b for c in _base_conditions("development") if c.stratum == "geometry_stress"}
    locked_geometry = {c.scenario.b for c in _base_conditions("locked") if c.stratum == "geometry_stress"}
    assert dev_geometry != locked_geometry


def test_strata_labels_are_declared():
    locked = _base_conditions("locked")
    for condition in locked:
        assert condition.stratum in STRATA
    mechanism_labels = {condition.mechanism for condition in locked}
    assert "acceleration" in mechanism_labels
    assert "geometry" in mechanism_labels
    for condition in locked:
        if condition.stratum == "model_misspecification":
            assert "NOT used to claim constant-velocity invariance" in condition.note
        if condition.stratum == "geometry_stress":
            assert "stress" in condition.note


# ---------------------------------------------------------------------------
# 6. Layer runs, schema, boundary report
# ---------------------------------------------------------------------------

def _run_small_dev(tmp_path):
    directory = tmp_path / "c1"
    artifact, protocol = run_layer(
        "development",
        str(directory / "dev.json"),
        jobs=1,
        trials_override=1,
        name_filter="control_zero",
        progress=False,
    )
    return directory, artifact, protocol


def test_small_development_run_freezes_protocol(tmp_path):
    directory, artifact, protocol = _run_small_dev(tmp_path)
    assert artifact["experiment"] == "pr4e-claims"
    assert artifact["layer"] == "development"
    assert artifact["protocol_version"] == PROTOCOL_VERSION
    assert artifact["protocol_digest"] == protocol["protocol_digest"]
    assert artifact["evidence_digest"] == protocol["evidence_digest"]
    assert artifact["symbolic_proof_digest"] == symbolic.derive_proof()["proof_digest"]
    protocol_path = directory / "claims-protocol.json"
    assert protocol_path.exists()
    assert protocol_path == pathlib.Path(artifact["protocol_path"])
    assert set(artifact["thresholds"]) == set(EVALUATED_CLAIMS)
    for threshold in artifact["thresholds"].values():
        assert threshold > 0.0
    assert artifact["grid"]["strata"]["control"] == 1
    assert len(artifact["trials"]) == 1
    assert artifact["protocol_gate"]["l1_completeness"]["status"] == "complete"
    assert artifact["protocol_gate"]["blocked"] is False
    json.dumps(artifact, allow_nan=False)


def test_small_development_run_is_record_deterministic(tmp_path):
    _, first, _ = _run_small_dev(tmp_path / "a")
    _, second, _ = _run_small_dev(tmp_path / "b")
    assert first["records_sha256"] == second["records_sha256"]
    assert first["trials"] == second["trials"]
    assert first["protocol_digest"] == second["protocol_digest"]


def test_small_locked_run_uses_frozen_protocol(tmp_path):
    directory, dev_artifact, dev_protocol = _run_small_dev(tmp_path)
    artifact, protocol = run_layer(
        "locked",
        str(directory / "locked.json"),
        jobs=1,
        trials_override=1,
        name_filter="control_zero",
        progress=False,
    )
    assert artifact["protocol_digest"] == dev_protocol["protocol_digest"]
    assert artifact["evidence_digest"] == dev_protocol["evidence_digest"]
    assert protocol["protocol_digest"] == dev_protocol["protocol_digest"]
    boundary_path = directory / "boundary.md"
    boundary_module.write_boundary(protocol, symbolic.derive_proof(), artifact, str(boundary_path))
    assert boundary_path.exists()


def test_locked_layer_refuses_missing_or_tampered_protocol(tmp_path):
    with pytest.raises(ValueError):
        run_layer(
            "locked",
            str(tmp_path / "empty" / "locked.json"),
            jobs=1,
            trials_override=1,
            name_filter="control_zero",
            progress=False,
        )
    directory, _artifact, _protocol = _run_small_dev(tmp_path)
    protocol_path = directory / "claims-protocol.json"
    tampered = json.loads(protocol_path.read_text(encoding="utf-8"))
    tampered["frozen_payload"]["thresholds"]["v"] = 1.0
    protocol_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError):
        run_layer(
            "locked",
            str(directory / "locked.json"),
            jobs=1,
            trials_override=1,
            name_filter="control_zero",
            progress=False,
        )


def test_trial_record_schema(tmp_path):
    _directory, artifact, _protocol = _run_small_dev(tmp_path)
    trial = artifact["trials"][0]
    assert set(trial) == {
        "condition",
        "trial",
        "seed",
        "layer",
        "stratum",
        "mechanism",
        "level",
        "evaluation_only",
        "observation",
        "hardened",
        "claims",
    }
    assert set(trial["evaluation_only"]) == {"scenario", "claim_truth", "estimate_within_tolerance"}
    assert set(trial["evaluation_only"]["claim_truth"]) == set(EVALUATED_CLAIMS) | {"b_over_f0"}
    assert set(trial["observation"]) == {"sigma_f_hz", "n_samples", "duration_s"}
    assert set(trial["hardened"]) >= {
        "params",
        "se",
        "optimization_status",
        "adequacy_status",
        "identifiability_status",
    }
    claims = {claim["claim_id"]: claim for claim in trial["claims"]}
    assert set(claims) == set(ALL_CLAIMS)
    for claim in claims.values():
        assert claim["status"] in STATUSES
        assert claim["status"] != "supported_invariant"
        assert "reason_codes" in claim
        assert "l1_certificate" in claim
    assert claims["v"]["status"] == "supported_conditional"
    assert claims["b_over_f0"]["status"] == "contradicted"
    payload = json.dumps(artifact, allow_nan=False)
    assert "NaN" not in payload and "Infinity" not in payload


def test_boundary_report_contains_all_claims_and_negative_result(tmp_path):
    _directory, artifact, protocol = _run_small_dev(tmp_path)
    markdown = boundary_module.render_boundary(protocol, symbolic.derive_proof(), artifact)
    for claim_id in ("v", "f0_times_b", "t0", "b", "f0", "b_over_f0"):
        assert f"`{claim_id}`" in markdown, claim_id
    assert "b/(k" in markdown or "b/(k_c" in markdown or "k^2" in markdown
    assert "Additional observation that would break the equivalence" in markdown
    assert "supported_invariant" in markdown
    assert "not allowed" in markdown
    assert "independent sound-speed" in markdown
    assert "absolute time" in markdown
    assert "Negative result" in markdown
    assert "Mechanism audit (P0 math audit)" in markdown
    assert "PR-4d misstatement" in markdown or "misstatement" in markdown
    assert protocol["protocol_digest"] in markdown
    assert protocol["evidence_digest"] in markdown


def test_no_certificate_code_is_imported():
    package_dir = REPO / "python" / "phaino_claims"
    for path in package_dir.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                assert "phaino_claim_certificate" not in stripped, (path.name, stripped)
    # Do not assert sys.modules: the independent evaluator's own tests may import
    # the certificate package in the same pytest session.  The static scan above
    # is the property that matters: the claims layer never imports it.


def test_certificate_evidence_does_not_invent_verdicts():
    evidence_block = certificate_evidence(None, None, "/tmp/missing.json")
    assert evidence_block["status"] == "not_recorded"
    assert evidence_block["per_claim_numeric_verdicts"] == {}
    assert evidence_block["certificate_sha256"] is None


# ---------------------------------------------------------------------------
# 7. Executable conventions and quantisation boundaries (ADR 0019 B / A.3)
# ---------------------------------------------------------------------------

def test_convention_conversion_is_executable():
    """M and C actions describe the same group element under k_c = 1/k_m."""
    f0, v, t0, b, c, k_m, k_c = sp.symbols("f0 v t0 b c k_m k_c", positive=True)
    beta = sp.symbols("beta", real=True)
    method_action = (f0 / k_m, v, k_m * t0 + beta, k_m * b, c)
    certificate_action = (k_c * f0, v, beta + t0 / k_c, b / k_c, c)
    mapping = {k_m: 1 / k_c}
    for method_component, certificate_component in zip(method_action, certificate_action):
        assert sp.simplify(method_component.subs(mapping) - certificate_component) == 0

    method_f0, method_v, method_t0, method_b, _ = method_action
    cert_f0, cert_v, cert_t0, cert_b, _ = certificate_action
    for action_f0, action_v, action_b in (
        (method_f0, method_v, method_b),
        (cert_f0, cert_v, cert_b),
    ):
        assert sp.simplify(action_v - v) == 0          # v invariant
        assert sp.simplify(action_f0 * action_b - f0 * b) == 0  # f0*b invariant

    # b/f0 scaling: k_m^2 under M, k_c^{-2} under C, and equivalent under the mapping.
    method_ratio = (k_m * b) / (f0 / k_m)
    certificate_ratio = (b / k_c) / (k_c * f0)
    assert sp.simplify(method_ratio - k_m**2 * b / f0) == 0
    assert sp.simplify(certificate_ratio - k_c**-2 * b / f0) == 0
    assert sp.simplify(method_ratio.subs(mapping) - certificate_ratio) == 0
    # A deliberately wrong exponent must fail.
    assert sp.simplify(method_ratio.subs(mapping) - k_c**2 * b / f0) != 0

    # Forward preservation within numerical tolerance for both actions.
    times = np.linspace(0.0, 60.0, 4001)
    params = (500.0, 250.0, 20.0, 3000.0)
    c_value = 343.0
    for k_m_value, beta_value in ((1.01, 0.5), (0.975, -2.0), (1.00001, 0.001)):
        k_c_value = 1.0 / k_m_value

        observed_method = forward_model_numeric(times, params, c_value, k_m_value, beta_value)
        method_params = (
            params[0] / k_m_value,
            params[1],
            k_m_value * params[2] + beta_value,
            k_m_value * params[3],
        )
        modelled_method = nominal_model_numeric(times, method_params, c_value)
        scale_method = max(float(np.max(np.abs(observed_method))), 1.0)
        assert float(np.max(np.abs(observed_method - modelled_method)) / scale_method) <= 1e-12

        observed_certificate = forward_model_numeric(times, params, c_value, 1.0 / k_c_value, beta_value)
        certificate_params = (
            k_c_value * params[0],
            params[1],
            beta_value + params[2] / k_c_value,
            params[3] / k_c_value,
        )
        modelled_certificate = nominal_model_numeric(times, certificate_params, c_value)
        scale_certificate = max(float(np.max(np.abs(observed_certificate))), 1.0)
        assert (
            float(np.max(np.abs(observed_certificate - modelled_certificate)) / scale_certificate) <= 1e-12
        )
        np.testing.assert_allclose(method_params, certificate_params, rtol=0.0, atol=1e-12)


def test_quantisation_boundary_rule_is_deterministic_and_documented():
    rule_doc = inspect.getdoc(canonicalise_threshold) or ""
    assert "round-half-even" in rule_doc
    assert "deterministic" in rule_doc

    # x.xxxxx5 boundary for 6 significant digits.  The exact decimal literal is
    # represented just below the tie, so it rounds down; the next float up
    # rounds up.  Each fixed input is deterministic.
    boundary = 1.234565e-5
    adjacent_low = float(np.nextafter(boundary, -np.inf))
    adjacent_high = float(np.nextafter(boundary, np.inf))
    cases = (adjacent_low, boundary, adjacent_high, 1.2345649999999997e-5, 1.2345650000000002e-5)
    expected = [float(f"{value:.6g}") for value in cases]
    for value, want in zip(cases, expected):
        assert canonicalise_threshold(value) == want
        assert canonicalise_threshold(value) == canonicalise_threshold(value)
        # JSON round-trip of the canonical value is lossless and stable
        round_tripped = json.loads(json.dumps(canonicalise_threshold(value)))
        assert canonicalise_threshold(round_tripped) == canonicalise_threshold(value)

    # Documented tie outcome for this boundary (CPython round-half-even on the
    # decimal formatting; the literal sits just below the exact tie).
    assert canonicalise_threshold(boundary) == 1.23456e-5
    assert canonicalise_threshold(adjacent_high) == 1.23457e-5
    # Canonical values are fixed points of the rule.
    for value in expected:
        assert canonicalise_threshold(value) == value
    # A change beyond the canonical precision must move the canonical value.
    assert canonicalise_threshold(boundary) != canonicalise_threshold(boundary * (1.0 + 1e-4))

    # The three historical CI threshold values all map to the same canonical value.
    historical_ci = (1.5962202539374443e-05, 1.596220253934089e-05, 1.5962202539374064e-05)
    assert len({canonicalise_threshold(value) for value in historical_ci}) == 1
    assert canonicalise_threshold(historical_ci[0]) == 1.59622e-05


# ---------------------------------------------------------------------------
# 8. Canonical, environment-invariant symbolic proof digest
# ---------------------------------------------------------------------------

def test_proof_digest_ignores_numeric_self_checks_and_environment(proof):
    """P0-CI fix: numeric self-check magnitudes and env fields are evidence only."""
    mutated = json.loads(json.dumps(proof))
    mutated["numeric_checks"]["forward_preservation"]["max_relative_error"] *= 3.0
    mutated["numeric_checks"]["negative_control"]["max_relative_difference"] *= 2.0
    mutated["numeric_checks"]["pr4d_misstatement_control"]["max_relative_difference"] *= 4.0
    mutated["numeric_checks"]["identifiability"]["nominal_model_c_known"]["scaled_condition_number"] *= 2.0
    mutated["numeric_checks"]["identifiability"]["nominal_model_c_known"]["scaled_singular_values"] = [
        value * 2.0 for value in mutated["numeric_checks"]["identifiability"]["nominal_model_c_known"]["scaled_singular_values"]
    ]
    mutated["numeric_checks"]["identifiability"]["full_model_c_unknown"]["scaled_singular_values"] = [
        value * 3.0 for value in mutated["numeric_checks"]["identifiability"]["full_model_c_unknown"]["scaled_singular_values"]
    ]
    mutated["numeric_checks"]["identifiability"]["full_model_c_unknown"]["alignment_with_scaling_direction"] = 0.9999999
    mutated["mechanism_audit_verification"]["method_convention"]["max_relative_forward_error"] *= 2.0
    mutated["mechanism_audit_verification"]["pr4d_misstatement"]["max_relative_difference"] *= 2.0
    mutated["sympy_version"] = "9.9.9"
    mutated["python_version"] = "9.9.9"
    mutated["counterexamples"]["b_over_f0"]["rate"]["before"] += 1.0
    mutated["counterexamples"]["b_over_f0"]["rate"]["after"] += 2.0
    mutated["theorems"][0]["lhs_hash"] = "0" * 64
    for theorem in mutated["theorems"]:
        if theorem["id"] == "T2_forward_invariance":
            theorem["lhs"] = "mutated-expression"
            theorem["rhs"] = "mutated-expression"
    assert symbolic.proof_digest(mutated) == proof["proof_digest"]
    assert symbolic.verify_proof_digest({**mutated, "proof_digest": proof["proof_digest"]})
    # Numeric content still present in the artifact as evidence.
    assert mutated["numeric_checks"]["forward_preservation"]["max_relative_error"] != proof["numeric_checks"]["forward_preservation"]["max_relative_error"]


def test_proof_digest_changes_on_semantic_change(proof):
    import copy

    base_digest = proof["proof_digest"]
    status_change = copy.deepcopy(proof)
    status_change["theorems"][1]["status"] = "refuted"  # T2 is proven; change to refuted
    assert symbolic.proof_digest(status_change) != base_digest

    statement_change = copy.deepcopy(proof)
    statement_change["theorems"][1]["statement"] = statement_change["theorems"][1]["statement"] + " (mutated)"
    assert symbolic.proof_digest(statement_change) != base_digest

    verdict_change = copy.deepcopy(proof)
    verdict_change["claim_verdicts"]["v"]["max_status"] = "supported_invariant"
    assert symbolic.proof_digest(verdict_change) != base_digest

    generator_change = copy.deepcopy(proof)
    generator_change["group"]["generators"][0]["l1_status"] = "open"
    assert symbolic.proof_digest(generator_change) != base_digest

    control_change = copy.deepcopy(proof)
    control_change["numeric_checks"]["negative_control"]["threshold_exceeded"] = False
    assert symbolic.proof_digest(control_change) != base_digest


def test_canonical_proof_content_is_float_free_and_excludes_evidence(proof):
    content = symbolic.canonical_proof_content(proof)
    assert content["canonical_schema"] == symbolic.PROOF_CANONICAL_SCHEMA
    assert "numeric_checks" not in content
    assert "sympy_version" not in content
    assert "python_version" not in content

    def floats(node, path=()):
        if isinstance(node, dict):
            for key, value in node.items():
                yield from floats(value, path + (key,))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                yield from floats(value, path + (index,))
        elif isinstance(node, float):
            yield (path, node)

    assert list(floats(content)) == []
    # json round-trip stability
    round_tripped = json.loads(json.dumps(proof))
    assert symbolic.canonical_proof_content(round_tripped) == content
    assert symbolic.proof_digest(round_tripped) == proof["proof_digest"]


def test_archived_protocol_agrees_with_canonical_proof_digest():
    archived = REPO / "protocols" / "pr4e-claims-1.3.0.json"
    assert archived.exists(), "authoritative frozen protocol file is missing"
    protocol = load_protocol(str(archived))
    assert protocol["protocol_digest"] == "193e70ab42cd1c953d89c735ee6fa4c19bc7aed98d11e2af8cba751c9191e52f"
    assert verify_protocol_digest(protocol)
    fresh_digest = symbolic.derive_proof()["proof_digest"]
    assert symbolic_proof_digest(protocol) == fresh_digest
    assert symbolic_proof_digest(protocol) == "b251848244c44044d5bda47e8dc7cb34c909c05326af7fe35d3fc4bd63cf9eb2"
