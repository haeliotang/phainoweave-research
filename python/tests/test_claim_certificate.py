"""Tests for the independent E0 clock-invariance certificate.

The certificate is independent of the acoustics method: these tests exercise the pure
numpy forward model, the clock group action, forward-model preservation, and the claim
verdicts (including deliberate failures).
"""

from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from phaino_claim_certificate import (
    ClaimsProtocolError,
    ClockTransform,
    ModelParameters,
    builtin_protocol,
    certificate_json,
    certificate_markdown,
    claim_value,
    forward_model,
    load_claims_protocol,
    physical_frequency,
    run_certificate,
    sample_grid,
)
from phaino_claim_certificate.cli import main

BASE = ModelParameters(f0=500.0, v=250.0, t0=20.0, b=3000.0, c=343.0)


def certificate(**kwargs) -> dict:
    return run_certificate(builtin_protocol(), **kwargs)


def test_forward_model_has_expected_anchor_values() -> None:
    grid, _ = sample_grid(0.0, 40.0, 161)
    frequency = forward_model(grid, BASE)
    at_t0 = physical_frequency(np.array([20.0]), BASE)[0]
    assert at_t0 == pytest.approx(BASE.f0, rel=1e-15)
    assert np.all(np.isfinite(frequency))
    assert np.all(frequency > 0.0)


def test_group_axioms_pass_at_near_and_large_transforms() -> None:
    document = certificate()
    axioms = document["group_axioms"]
    assert axioms["identity"] is True
    assert axioms["composition"] is True
    assert axioms["inverse"] is True
    assert axioms["domain"] is True
    near = axioms["evidence"]["near_identity_transforms"]
    large = axioms["evidence"]["large_transforms"]
    assert near["betas"]
    assert near["epsilons"]
    assert large["betas"]
    assert large["epsilons"]
    assert axioms["evidence"]["domain_failures"] == []


def test_forward_model_is_preserved_under_clock_offset() -> None:
    protocol = builtin_protocol()
    grid, step = sample_grid(*protocol.grid)
    for transform in protocol.offset_transforms:
        for point in protocol.sample_points:
            from phaino_claim_certificate.model import forward_preservation

            report = forward_preservation(
                grid, step, point, transform, protocol.observation_tolerance
            )
            assert report["preserves_forward_model"] is True, (
                transform,
                point,
                report,
            )


def test_forward_model_is_preserved_under_clock_rate() -> None:
    protocol = builtin_protocol()
    grid, step = sample_grid(*protocol.grid)
    from phaino_claim_certificate.model import forward_preservation

    for transform in protocol.rate_transforms:
        for point in protocol.sample_points:
            report = forward_preservation(
                grid, step, point, transform, protocol.observation_tolerance
            )
            assert report["preserves_forward_model"] is True, (transform, point, report)


def test_generator_reports_preserve_forward_model() -> None:
    document = certificate()
    for name in ("clock_offset", "clock_rate"):
        generator = document["generators"][name]
        assert generator["preserves_forward_model"] is True
        assert generator["failure_class"] is None
        assert generator["max_relative_observation_mismatch"] <= generator["observation_tolerance"]


def test_v_is_invariant_under_both_generators() -> None:
    document = certificate()
    claim = next(entry for entry in document["claims"] if entry["claim"] == "v")
    assert claim["numeric_verdict"] == "invariant"
    assert claim["symbolic_verdict"] == "invariant"
    assert claim["agrees_with_symbolic"] is True
    assert claim["max_relative_mismatch"] <= claim["tolerance"]


def test_b_over_f0_numeric_check_disagrees_with_symbolic_claim() -> None:
    document = certificate()
    claim = next(entry for entry in document["claims"] if entry["claim"] == "b/f0")
    assert claim["symbolic_verdict"] == "invariant"
    assert claim["numeric_verdict"] == "not_invariant"
    assert claim["agrees_with_symbolic"] is False
    assert claim["max_relative_mismatch"] > claim["tolerance"]
    # The mismatch must come from the rate family, not the offset family.
    by_generator = claim["evidence"]["max_relative_mismatch_by_generator"]
    assert by_generator["clock_offset"] <= claim["tolerance"]
    assert by_generator["clock_rate"] > 0.01
    disagreements = document["symbolic_numeric_disagreements"]
    assert any(entry["claim"] == "b/f0" for entry in disagreements)
    assert any("b*f0" in note for note in document["notes"])


def test_t0_is_not_invariant_under_clock_offset() -> None:
    document = certificate()
    claim = next(entry for entry in document["claims"] if entry["claim"] == "t0")
    assert claim["numeric_verdict"] == "not_invariant"
    assert claim["symbolic_verdict"] == "not_invariant"
    assert claim["agrees_with_symbolic"] is True
    offset = ClockTransform(k=1.0, beta=3.0)
    transformed = offset.apply_parameters(BASE)
    assert claim_value("t0", transformed) != pytest.approx(claim_value("t0", BASE))
    assert abs(claim_value("t0", transformed) - claim_value("t0", BASE)) == pytest.approx(3.0)


def test_b_and_f0_are_not_invariant_under_rate() -> None:
    document = certificate()
    for name in ("b", "f0"):
        claim = next(entry for entry in document["claims"] if entry["claim"] == name)
        assert claim["numeric_verdict"] == "not_invariant"
        assert claim["max_relative_mismatch"] == pytest.approx(0.025, rel=1e-12)


def test_wrong_generator_is_rejected() -> None:
    protocol = builtin_protocol()
    wrong = ClockTransform(k=1.0, beta=1e-3, f0_scale=1.1)
    document = run_certificate(
        protocol,
        generator_overrides={
            "clock_offset": (wrong,),
            "clock_rate": protocol.rate_transforms,
        },
    )
    generator = document["generators"]["clock_offset"]
    assert generator["preserves_forward_model"] is False
    assert generator["failure_class"] == "invalid_symmetry"
    affected = [
        entry
        for entry in document["claims"]
        if entry["failure_class"] == "invalid_symmetry"
    ]
    assert affected


def test_sampling_grid_mismatch_is_classified_as_implementation() -> None:
    protocol = builtin_protocol()
    shifted = ClockTransform(k=1.0, beta=1e-3, observation_shift_samples=1.0)
    document = run_certificate(
        protocol,
        generator_overrides={
            "clock_offset": (shifted,),
            "clock_rate": protocol.rate_transforms,
        },
    )
    generator = document["generators"]["clock_offset"]
    assert generator["preserves_forward_model"] is False
    assert generator["failure_class"] == "implementation"
    entry = next(
        item
        for item in generator["evidence"]
        if item["failure_class"] == "implementation"
    )
    assert entry["grid_shift_samples"] == 1


def test_certificate_is_deterministic() -> None:
    first = certificate()
    second = certificate()
    assert certificate_json(first) == certificate_json(second)
    assert certificate_markdown(first) == certificate_markdown(second)


def test_certificate_schema_and_independence() -> None:
    document = certificate()
    assert document["certificate_version"] == "1.0.0"
    assert document["model"]["name"] == "e0-narrowband-doppler"
    assert document["independence"]["imports_acoustics"] is False
    assert document["independence"]["checked_modules"] == ["phaino_acoustics"]
    assert document["nuisance"]["used_for_invariance_claims"] is False
    assert document["nuisance"]["declared"]
    assert document["claims_protocol"]["builtin"] is True
    assert document["claims_protocol"]["warning"]
    assert {claim["claim"] for claim in document["claims"]} == {
        "v",
        "b/f0",
        "t0",
        "b",
        "f0",
    }
    assert document["independence"]["check_method"].startswith("static scan")


def test_claims_protocol_loads_from_json(tmp_path: Path) -> None:
    document = builtin_protocol().document
    path = tmp_path / "claims.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    loaded = load_claims_protocol(path)
    assert loaded.builtin is False
    assert loaded.protocol_id == document["protocol_id"]
    assert loaded.claims == builtin_protocol().claims


def test_invalid_claims_protocol_is_rejected(tmp_path: Path) -> None:
    document = copy.deepcopy(builtin_protocol().document)
    document["claims"][0]["symbolic_verdict"] = "insufficient"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ClaimsProtocolError):
        load_claims_protocol(path)

    missing = copy.deepcopy(builtin_protocol().document)
    del missing["generators"]
    path.write_text(json.dumps(missing), encoding="utf-8")
    with pytest.raises(ClaimsProtocolError):
        load_claims_protocol(path)


def test_cli_writes_certificate_and_markdown(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "certificate.json"
    markdown = tmp_path / "certificate.md"
    assert main(["--out", str(out), "--markdown", str(markdown)]) == 0
    document = json.loads(out.read_text())
    assert document["certificate_version"] == "1.0.0"
    assert "clock-invariance" in markdown.read_text()
    captured = capsys.readouterr()
    assert "b/f0" in captured.out
    assert "built-in" in captured.out


def test_cli_rejects_invalid_claims_protocol(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"protocol_id":"x"}', encoding="utf-8")
    assert (
        main(
            [
                "--claims",
                str(bad),
                "--out",
                str(tmp_path / "certificate.json"),
                "--markdown",
                str(tmp_path / "certificate.md"),
            ]
        )
        == 2
    )


# ---------------------------------------------------------------------------
# Method workstream PR-4e claims-protocol schema
# ---------------------------------------------------------------------------

def _method_claim(
    claim_id: str,
    expression: str,
    value: float,
    *,
    kind: str = "invariant",
    l1_status: str = "proven",
    max_status: str = "supported_conditional",
    tolerance_value: float = 1e-12,
) -> dict:
    return {
        "claim_id": claim_id,
        "claim_kind": kind,
        "expression": expression,
        "value_expression": expression,
        "label": f"method claim {claim_id}",
        "evaluated": True,
        "claim_tolerance": {
            "kind": "absolute" if claim_id == "t0" else "relative",
            "value": value,
            "source": "test protocol",
        },
        "l1_status": l1_status,
        "l2_status": "open" if kind == "invariant" else "proven_within_conditioning",
        "max_status": max_status,
        "symmetry_scope": "G_clock",
        "conditioning": ["declared model valid"],
        "nuisance_assumptions": ["sound speed known", "nominal clock"],
        "l1_certificate": {"tolerance": tolerance_value, "status": "pending"},
        "thresholds": {"metric": "test", "threshold": value, "selected_on": "development"},
    }


def method_protocol_document(
    *,
    b_over_f0_l1_status: str = "refuted",
    declared_generators: list[str] | None = None,
) -> dict:
    group = {
        "set": "{(k, beta) : k > 0, beta in R}",
        "action": "(f0,v,t0,b,c) -> (f0/k, v, k*t0 + beta, k*b, c)",
        "identity": "(1, 0)",
        "composition": "(k2,beta2) o (k1,beta1) = (k2*k1, k2*beta1 + beta2)",
        "inverse": "(1/k, -beta/k)",
    }
    if declared_generators is not None:
        group["generators"] = list(declared_generators)
    return {
        "experiment": "test-pr4e-claims",
        "protocol_version": "test-1.1.0",
        "protocol_digest": "test-method-protocol-digest",
        "symbolic_proof_digest": "test-symbolic-digest",
        "declared_model": "straight-line constant-velocity source; radial Doppler",
        "clock_model": "t_obs = k * t_phys + beta",
        "symmetry_group": group,
        "convention_reconciliation": {
            "method_convention": {
                "time_map": "t_obs = k_m * t_phys + beta",
                "parameter_action": "(f0/k_m, v, k_m*t0 + beta, k_m*b, c)",
            },
            "certificate_convention": {
                "time_map": "t_obs = t_phys / k_c + beta",
                "parameter_action": "(k_c*f0, v, beta+t0/k_c, b/k_c, c)",
            },
            "mapping": "k_c = 1/k_m",
            "equivalent": True,
        },
        "thresholds": {"v": 1e-5, "f0_times_b": 7e-5, "b_over_f0": None},
        "claims": [
            _method_claim("v", "v", 0.02),
            _method_claim("f0_times_b", "f0*b", 0.05),
            _method_claim("t0", "t0", 0.25, kind="conditional", l1_status="refuted"),
            _method_claim("b", "b", 0.05, kind="conditional", l1_status="refuted"),
            _method_claim("f0", "f0", 0.01, kind="conditional", l1_status="refuted"),
            _method_claim(
                "b_over_f0",
                "b/f0",
                0.05,
                kind="refuted_invariant",
                l1_status=b_over_f0_l1_status,
                max_status="contradicted" if b_over_f0_l1_status == "refuted" else "supported_conditional",
            ),
        ],
    }


def write_method_protocol(tmp_path: Path, **kwargs) -> Path:
    path = tmp_path / "method-claims-protocol.json"
    path.write_text(json.dumps(method_protocol_document(**kwargs)), encoding="utf-8")
    return path


def test_method_schema_loading(tmp_path: Path) -> None:
    from phaino_claim_certificate import load_method_protocol

    path = write_method_protocol(tmp_path)
    protocol = load_method_protocol(path)
    assert protocol.method_schema is True
    assert protocol.builtin is False
    assert protocol.source_sha256
    assert protocol.protocol_id == "test-pr4e-claims:test-1.1.0"
    assert {claim.claim for claim in protocol.claims} == {
        "v",
        "f0_times_b",
        "t0",
        "b",
        "f0",
        "b_over_f0",
    }
    assert next(claim for claim in protocol.claims if claim.claim == "f0_times_b").quantity == "b*f0"
    assert next(claim for claim in protocol.claims if claim.claim == "b_over_f0").quantity == "b/f0"


def test_method_schema_composite_claims_and_reconciliation(tmp_path: Path) -> None:
    from phaino_claim_certificate import load_method_protocol

    path = write_method_protocol(tmp_path)
    protocol = load_method_protocol(path)
    document = run_certificate(protocol)
    claims = {entry["claim"]: entry for entry in document["claims"]}
    assert claims["v"]["numeric_verdict"] == "invariant"
    assert claims["f0_times_b"]["numeric_verdict"] == "invariant"
    assert claims["f0_times_b"]["max_relative_mismatch"] <= claims["f0_times_b"]["tolerance"]
    assert claims["b_over_f0"]["numeric_verdict"] == "not_invariant"
    assert claims["b_over_f0"]["max_relative_mismatch"] > 0.01
    assert claims["t0"]["numeric_verdict"] == "not_invariant"
    assert claims["b"]["numeric_verdict"] == "not_invariant"
    assert claims["f0"]["numeric_verdict"] == "not_invariant"
    assert document["symbolic_numeric_disagreements"] == []
    assert document["method_protocol"]["mapping"]["rate_mapping"] == "k_c = 1 / k_m"
    assert document["method_protocol"]["source_sha256"]
    assert document["independence"]["imports_acoustics"] is False


def test_method_schema_mismatch_is_disagreement_not_failure(tmp_path: Path) -> None:
    from phaino_claim_certificate import load_method_protocol

    path = write_method_protocol(tmp_path, b_over_f0_l1_status="proven")
    document = run_certificate(load_method_protocol(path))
    claim = next(entry for entry in document["claims"] if entry["claim"] == "b_over_f0")
    assert claim["symbolic_verdict"] == "invariant"
    assert claim["numeric_verdict"] == "not_invariant"
    assert claim["agrees_with_symbolic"] is False
    assert claim["failure_class"] is None
    assert claim["promotion_allowed"] is False
    assert claim["gate_status"] == "withheld_symbolic_disagreement"
    audit_claim = next(
        entry for entry in document["self_audit"]["claims"]
        if entry["claim"] == "b_over_f0"
    )
    assert audit_claim["numeric_verdict"] == "not_invariant"
    assert audit_claim["agrees_with_symbolic"] is False
    assert any(
        entry["claim"] == "b_over_f0"
        for entry in document["symbolic_numeric_disagreements"]
    )
    # Other claims remain valid and the certificate is still produced.
    assert document["group_axioms"]["identity"] is True


def test_method_schema_determinism(tmp_path: Path) -> None:
    from phaino_claim_certificate import load_method_protocol

    path = write_method_protocol(tmp_path)
    protocol = load_method_protocol(path)
    first = run_certificate(protocol)
    second = run_certificate(protocol)
    assert certificate_json(first) == certificate_json(second)
    assert certificate_markdown(first) == certificate_markdown(second)


def test_method_schema_cli(tmp_path: Path) -> None:
    path = write_method_protocol(tmp_path)
    out = tmp_path / "certificate-method.json"
    markdown = tmp_path / "certificate-method.md"
    assert (
        main(
            [
                "--method-protocol",
                str(path),
                "--out",
                str(out),
                "--markdown",
                str(markdown),
            ]
        )
        == 0
    )
    document = json.loads(out.read_text())
    assert document["method_protocol"]["schema"] == "method-claims-protocol"
    assert document["symbolic_numeric_disagreements"] == []
    assert "Method protocol reconciliation" in markdown.read_text()


def test_invalid_method_schema_rejected(tmp_path: Path) -> None:
    from phaino_claim_certificate import load_method_protocol

    path = tmp_path / "bad-method.json"
    path.write_text('{"experiment":"x","claims":[]}', encoding="utf-8")
    with pytest.raises(ClaimsProtocolError):
        load_method_protocol(path)


def test_self_audit_section_and_complete_group() -> None:
    document = certificate()
    assert document["incomplete_group"] == []
    assert document["self_audit"]["group_coverage_complete"] is True
    generators = {row["generator_id"]: row for row in document["self_audit"]["generators"]}
    assert generators["clock_offset"]["tested"] is True
    assert generators["clock_rate"]["tested"] is True
    assert generators["clock_offset"]["preserves_forward"] is True
    claims = {row["claim"]: row for row in document["self_audit"]["claims"]}
    assert claims["v"]["numeric_verdict"] == "invariant"
    assert claims["b/f0"]["numeric_verdict"] == "not_invariant"


def test_missing_required_generator_yields_incomplete_group(tmp_path: Path) -> None:
    from phaino_claim_certificate import load_method_protocol

    document = method_protocol_document(declared_generators=["clock_offset"])
    path = tmp_path / "test-method-incomplete.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    protocol = load_method_protocol(path)
    certificate_document = run_certificate(protocol)
    assert certificate_document["incomplete_group"] == ["clock_rate"]
    assert certificate_document["self_audit"]["group_coverage_complete"] is False
    rate_row = next(
        row
        for row in certificate_document["self_audit"]["generators"]
        if row["generator_id"] == "clock_rate"
    )
    assert rate_row["declared"] is False
    assert rate_row["required"] is True
    assert rate_row["tested"] is False
    claims = {claim["claim"]: claim for claim in certificate_document["claims"]}
    assert claims["v"]["group_coverage_complete"] is False
    assert claims["v"]["promotion_allowed"] is False
    assert claims["v"]["gate_status"] == "withheld_incomplete_group"
    assert claims["f0_times_b"]["group_coverage_complete"] is False
    assert claims["f0_times_b"]["promotion_allowed"] is False


def test_nuisance_conflict_is_flagged_not_accepted(tmp_path: Path) -> None:
    from phaino_claim_certificate import load_method_protocol

    document = method_protocol_document()
    path = tmp_path / "test-method-nuisance.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    certificate_document = run_certificate(load_method_protocol(path))
    claims = {claim["claim"]: claim for claim in certificate_document["claims"]}
    v_claim = claims["v"]
    assert v_claim["numeric_verdict"] == "invariant"
    assert v_claim["nuisance_conflict"] is True
    assert v_claim["promotion_allowed"] is False
    assert v_claim["gate_status"] == "withheld_nuisance_conflict"
    assert any(
        conflict["claim"] == "v"
        for conflict in certificate_document["nuisance_conflicts"]
    )
    assert claims["f0_times_b"]["nuisance_conflict"] is True
    assert claims["f0_times_b"]["promotion_allowed"] is False


def test_self_audit_cli_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "certificate.json"
    markdown = tmp_path / "certificate.md"
    assert main(["--self-audit", "--out", str(out), "--markdown", str(markdown)]) == 0
    captured = capsys.readouterr()
    assert "self-audit:" in captured.out
    assert "clock_offset" in captured.out
    assert "incomplete_group: []" in captured.out
