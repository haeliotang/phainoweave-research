"""Independent numerical certificate for the E0 clock-invariance claims.

The certificate implements the forward model and the clock action from physics (see
``model.py``), then checks group axioms, forward-model preservation, and the five declared
claims. It can fail: observation mismatches are classified as floating-point noise,
implementation/grid discrepancy, or an invalid symmetry; claim disagreement with the
method-side symbolic verdict is reported explicitly.
"""

from __future__ import annotations

import platform
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .model import (
    ClockTransform,
    ModelParameters,
    claim_value,
    forward_model,
    forward_preservation,
    relative_mismatch,
    sample_grid,
)
from .protocol import (
    CERTIFICATE_VERSION,
    KNOWN_GENERATORS,
    REQUIRED_GENERATORS,
    ClaimsProtocol,
)

IMPORT_CHECK = "phaino_acoustics"
FORWARD_MODEL_EQUATIONS = {
    "physical_frequency": "f_phys(t_phys) = f0 / (1 + v^2*tau/(c*r)), tau=t_phys-t0, r=sqrt(v^2*tau^2+b^2)",
    "observed_time": "t_obs = t_phys/k + beta, k = 1 + epsilon > 0",
    "observed_frequency": "y(t_obs) = k * f_phys(k*(t_obs-beta))",
    "parameter_action": "f0' = k*f0; v' = v; t0' = beta + t0/k; b' = b/k",
}


def run_certificate(
    protocol: ClaimsProtocol,
    generator_overrides: Mapping[str, Sequence[ClockTransform]] | None = None,
) -> dict[str, Any]:
    """Builds the machine-readable certificate document."""
    grid, step = sample_grid(*protocol.grid)
    offset_transforms = tuple(
        generator_overrides.get("clock_offset", protocol.offset_transforms)
        if generator_overrides
        else protocol.offset_transforms
    )
    rate_transforms = tuple(
        generator_overrides.get("clock_rate", protocol.rate_transforms)
        if generator_overrides
        else protocol.rate_transforms
    )
    axioms = _group_axioms(protocol, grid, step)
    generators = {
        "clock_offset": _generator_report(
            "clock_offset", offset_transforms, protocol, grid, step
        ),
        "clock_rate": _generator_report("clock_rate", rate_transforms, protocol, grid, step),
    }
    families = {
        "clock_offset": (offset_transforms, protocol.offset_transforms),
        "clock_rate": (rate_transforms, protocol.rate_transforms),
    }
    claims = [
        _claim_report(claim, protocol, grid, step, families)
        for claim in protocol.claims
    ]
    coverage = _generator_coverage(protocol, generators)
    nuisance_conflicts = _annotate_claims(claims, protocol, grid, coverage)
    self_audit = _self_audit(protocol, generators, claims, coverage)

    disagreements = [
        {
            "claim": claim["claim"],
            "symbolic_verdict": claim["symbolic_verdict"],
            "numeric_verdict": claim["numeric_verdict"],
            "max_relative_mismatch": claim["max_relative_mismatch"],
            "tolerance": claim["tolerance"],
        }
        for claim in claims
        if claim["symbolic_verdict"] != "unknown"
        and claim["numeric_verdict"] != "unknown"
        and claim["symbolic_verdict"] != claim["numeric_verdict"]
    ]
    notes: list[str] = []
    rate_claim = next((claim for claim in claims if claim["claim"] == "b/f0"), None)
    if rate_claim is not None and rate_claim["numeric_verdict"] == "not_invariant":
        notes.append(
            "Independent numeric check disagrees with the symbolic claim that b/f0 is "
            "invariant under clock rate. Under the derived action f0'=k f0 and b'=b/k, "
            "the invariant composite is b*f0, not b/f0. This must be resolved on the "
            "method side before b/f0 is used as a claim."
        )

    imported = _imports_acoustics_statically()
    limitations = list(protocol_limitations(protocol))
    if protocol.method_schema:
        limitations.extend(
            [
                "The method protocol's claim_tolerance values are operational L3 "
                "tolerances; numerical invariance uses the declared L1/default tolerance "
                "(1e-12) from l1_certificate or the built-in default. They are not "
                "interchangeable.",
                "The method protocol's existing l1_certificate entries reference the "
                "earlier certificate digest. They were consumed as data and not edited; "
                "the reconciled verdicts in this certificate are new evidence.",
                "Method claim f0_times_b is mapped to the quantity f0*b; b_over_f0 is "
                "mapped to b/f0. The method and certificate rate conventions are "
                "reciprocal (k_c = 1/k_m), so the group action is identical.",
            ]
        )
    return {
        "certificate_version": CERTIFICATE_VERSION,
        "model": {
            "name": protocol.model_name,
            "equations": FORWARD_MODEL_EQUATIONS,
            "speed_of_sound_m_s": protocol.c,
            "observation_grid": {
                "t_min": protocol.grid[0],
                "t_max": protocol.grid[1],
                "count": protocol.grid[2],
            },
            "sample_points": [
                {"f0": p.f0, "v": p.v, "t0": p.t0, "b": p.b, "c": p.c}
                for p in protocol.sample_points
            ],
        },
        "independence": {
            "imports_acoustics": imported,
            "checked_modules": [IMPORT_CHECK],
            "check_method": "static scan of phaino_claim_certificate import statements",
            "forward_model": "independent pure-numpy implementation in phaino_claim_certificate.model",
        },
        "claims_protocol": {
            "id": protocol.protocol_id,
            "version": protocol.version,
            "source": protocol.source,
            "builtin": protocol.builtin,
            "digest": protocol.digest(),
            "warning": (
                "Method-side claims protocol not supplied; using the minimal built-in "
                "protocol. Its symbolic verdicts are the ADR 0016/0017 claim set, not a "
                "method artifact."
            )
            if protocol.builtin
            else None,
        },
        "method_protocol": _method_protocol_block(protocol)
        if protocol.method_schema
        else None,
        "group_axioms": axioms,
        "generators": generators,
        "incomplete_group": coverage["incomplete_group"],
        "self_audit": self_audit,
        "claims": claims,
        "symbolic_numeric_disagreements": disagreements,
        "nuisance_conflicts": nuisance_conflicts,
        "notes": notes,
        "nuisance": {
            "declared": list(protocol.nuisance_assumptions),
            "used_for_invariance_claims": False,
        },
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "platform": platform.system(),
            "machine": platform.machine(),
        },
        "limitations": limitations,
    }


def protocol_limitations(protocol: ClaimsProtocol) -> tuple[str, ...]:
    limitations = [
        "The certificate tests the declared E0 narrowband forward model only: stationary "
        "receiver, straight-line constant-velocity source, delay-free propagation, no noise. "
        "It is not a real-data or full-physics validation.",
        "The clock transforms are affine in observation time (offset plus rate). Other "
        "timing errors, propagation, acceleration and source-direction effects are not in "
        "G_clock and are not used to claim invariance.",
        "N_physical nuisances (sound speed, source direction, acceleration, propagation "
        "environment) are declared but deliberately excluded from the symmetry group; the "
        "certificate cannot promote an invariant through them.",
        "Numeric agreement is a floating-point check at the declared tolerance, not a "
        "statistical proof and not an L2/L3 identifiability or support result.",
        "The method-side claims protocol was not supplied"
        if protocol.builtin
        else "The supplied method-side claims protocol was consumed as data, not imported.",
        "The forward model and parameter action are an independent reimplementation; a "
        "different but algebraically equivalent method parameterization may need its own "
        "action map.",
    ]
    return tuple(limitations)


def _group_axioms(
    protocol: ClaimsProtocol, grid: np.ndarray, step: float
) -> dict[str, Any]:
    identity = ClockTransform()
    all_transforms = (identity,) + protocol.offset_transforms + protocol.rate_transforms
    identity_errors: list[float] = []
    identity_observation: list[float] = []
    for point in protocol.sample_points:
        transformed = identity.apply_parameters(point)
        identity_errors.append(transformed.relative_to(point))
        identity_observation.append(
            _forward_mismatch(grid, step, point, identity, protocol.observation_tolerance)
        )
    composition_errors: list[float] = []
    for point in protocol.sample_points:
        for first in all_transforms:
            for second in all_transforms:
                sequential = second.apply_parameters(first.apply_parameters(point))
                composed = first.compose(second).apply_parameters(point)
                composition_errors.append(sequential.relative_to(composed))
    inverse_errors: list[float] = []
    inverse_representation_errors: list[float] = []
    for point in protocol.sample_points:
        for transform in all_transforms:
            inverse = transform.inverse()
            recovered = inverse.apply_parameters(transform.apply_parameters(point))
            inverse_errors.append(recovered.relative_to(point))
            composed = transform.compose(inverse)
            representation = ClockTransform(k=composed.k, beta=composed.beta)
            inverse_representation_errors.append(
                abs(representation.k - 1.0) + abs(representation.beta)
            )
    domain_failures: list[str] = []
    domain_checks = 0
    for point in protocol.sample_points:
        for transform in all_transforms:
            for candidate in (transform, transform.inverse()):
                domain_checks += 1
                transformed = candidate.apply_parameters(point)
                if not candidate.valid() or not transformed.valid():
                    domain_failures.append(
                        f"k={candidate.k} beta={candidate.beta} point=({point.f0},{point.v},{point.t0},{point.b})"
                    )
    return {
        "identity": max(identity_errors, default=0.0) <= 1e-12
        and max(identity_observation, default=0.0) <= protocol.observation_tolerance,
        "composition": max(composition_errors, default=0.0) <= 1e-12,
        "inverse": max(inverse_errors, default=0.0) <= 1e-12
        and max(inverse_representation_errors, default=0.0) <= 1e-12,
        "domain": not domain_failures,
        "evidence": {
            "near_identity_transforms": _near_identity_values(protocol),
            "large_transforms": _large_values(protocol),
            "max_relative_identity_parameter_error": max(identity_errors, default=0.0),
            "max_relative_identity_observation_error": max(identity_observation, default=0.0),
            "max_relative_composition_parameter_error": max(composition_errors, default=0.0),
            "max_relative_inverse_parameter_error": max(inverse_errors, default=0.0),
            "max_inverse_representation_error": max(inverse_representation_errors, default=0.0),
            "domain_checks": domain_checks,
            "domain_failures": domain_failures,
        },
    }


def _generator_report(
    name: str,
    transforms: Sequence[ClockTransform],
    protocol: ClaimsProtocol,
    grid: np.ndarray,
    step: float,
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    classes: list[str] = []
    for transform in transforms:
        for point in protocol.sample_points:
            report = forward_preservation(
                grid, step, point, transform, protocol.observation_tolerance
            )
            if report["failure_class"] is not None:
                classes.append(report["failure_class"])
            entries.append(
                {
                    "k": transform.k,
                    "beta": transform.beta,
                    "point": {"f0": point.f0, "v": point.v, "t0": point.t0, "b": point.b},
                    "max_relative_observation_mismatch": report[
                        "max_relative_observation_mismatch"
                    ],
                    "preserves_forward_model": report["preserves_forward_model"],
                    "failure_class": report["failure_class"],
                    "diagnosis": report["diagnosis"],
                    "grid_shift_samples": report.get("grid_shift_samples"),
                }
            )
    failure_class = "invalid_symmetry" if "invalid_symmetry" in classes else (
        "implementation" if "implementation" in classes else None
    )
    tested = bool(transforms) and bool(entries)
    return {
        "tested": tested,
        "transforms": [
            {"k": transform.k, "beta": transform.beta} for transform in transforms
        ],
        "preserves_forward_model": (failure_class is None) if tested else None,
        "failure_class": failure_class,
        "observation_tolerance": protocol.observation_tolerance,
        "max_relative_observation_mismatch": max(
            (entry["max_relative_observation_mismatch"] for entry in entries), default=None
        )
        if tested
        else None,
        "grid_samples": int(grid.size),
        "sample_points": len(protocol.sample_points),
        "evidence": entries,
    }


def _claim_report(
    claim_spec: Any,
    protocol: ClaimsProtocol,
    grid: np.ndarray,
    step: float,
    families: Mapping[str, tuple[Sequence[ClockTransform], Sequence[ClockTransform]]],
) -> dict[str, Any]:
    mismatches: list[float] = []
    per_family: dict[str, list[float]] = {"clock_offset": [], "clock_rate": []}
    failures: list[dict[str, Any]] = []
    worst: dict[str, Any] | None = None
    for family_name, (family, _defaults) in families.items():
        for transform in family:
            for point in protocol.sample_points:
                transformed = transform.apply_parameters(point)
                if not transformed.valid():
                    failures.append(
                        {
                            "family": family_name,
                            "k": transform.k,
                            "beta": transform.beta,
                            "point": _point_document(point),
                            "failure_class": "invalid_symmetry",
                            "diagnosis": "transformed parameters outside the model domain",
                        }
                    )
                    continue
                observation = forward_preservation(
                    grid, step, point, transform, protocol.observation_tolerance
                )
                if observation["failure_class"] in {"invalid_symmetry", "implementation"}:
                    failures.append(
                        {
                            "family": family_name,
                            "k": transform.k,
                            "beta": transform.beta,
                            "point": _point_document(point),
                            "failure_class": observation["failure_class"],
                            "diagnosis": observation["diagnosis"],
                            "max_relative_observation_mismatch": observation[
                                "max_relative_observation_mismatch"
                            ],
                        }
                    )
                before = claim_value(claim_spec.quantity, point)
                after = claim_value(claim_spec.quantity, transformed)
                mismatch = relative_mismatch(before, after)
                mismatches.append(mismatch)
                per_family[family_name].append(mismatch)
                if worst is None or mismatch > worst["mismatch"]:
                    worst = {
                        "family": family_name,
                        "k": transform.k,
                        "beta": transform.beta,
                        "point": _point_document(point),
                        "mismatch": mismatch,
                        "value": after,
                    }
    maximum = max(mismatches, default=0.0)
    if failures:
        classes = {failure["failure_class"] for failure in failures}
        failure_class = "invalid_symmetry" if "invalid_symmetry" in classes else "implementation"
        numeric_verdict = "unknown"
        diagnosis = "generator_does_not_preserve_the_forward_model"
    else:
        failure_class = None
        numeric_verdict = (
            "invariant" if maximum <= claim_spec.tolerance else "not_invariant"
        )
        diagnosis = (
            "exact_up_to_floating_point"
            if numeric_verdict == "invariant"
            else "claim_changes_under_a_verified_symmetry"
        )
    agrees = (
        claim_spec.symbolic_verdict == numeric_verdict
        if claim_spec.symbolic_verdict != "unknown" and numeric_verdict != "unknown"
        else None
    )
    return {
        "claim": claim_spec.claim,
        "quantity": claim_spec.quantity,
        "symbolic_verdict": claim_spec.symbolic_verdict,
        "numeric_verdict": numeric_verdict,
        "agrees_with_symbolic": agrees,
        "scope": claim_spec.scope,
        "max_relative_mismatch": maximum,
        "tolerance": claim_spec.tolerance,
        "failure_class": failure_class,
        "diagnosis": diagnosis,
        "method_claim": _json_safe(claim_spec.method_metadata)
        if claim_spec.method_metadata is not None
        else None,
        "evidence": {
            "samples": len(mismatches),
            "max_relative_mismatch_by_generator": {
                name: max(values, default=0.0) for name, values in per_family.items()
            },
            "worst": _json_safe(worst),
            "generator_failures": failures,
            "symbolic_rationale": claim_spec.rationale,
        },
    }


def _forward_mismatch(
    grid: np.ndarray,
    step: float,
    point: ModelParameters,
    transform: ClockTransform,
    tolerance: float,
) -> float:
    return float(
        forward_preservation(grid, step, point, transform, tolerance)[
            "max_relative_observation_mismatch"
        ]
    )


def _near_identity_values(protocol: ClaimsProtocol) -> dict[str, list[float]]:
    return {
        "betas": [
            transform.beta
            for transform in protocol.offset_transforms
            if abs(transform.beta) <= 1e-2
        ],
        "epsilons": [
            transform.k - 1.0
            for transform in protocol.rate_transforms
            if abs(transform.k - 1.0) <= 1e-4
        ],
    }


def _large_values(protocol: ClaimsProtocol) -> dict[str, list[float]]:
    return {
        "betas": [
            transform.beta
            for transform in protocol.offset_transforms
            if abs(transform.beta) > 1e-2
        ],
        "epsilons": [
            transform.k - 1.0
            for transform in protocol.rate_transforms
            if abs(transform.k - 1.0) > 1e-4
        ],
    }


def _point_document(point: ModelParameters) -> dict[str, float]:
    return {"f0": point.f0, "v": point.v, "t0": point.t0, "b": point.b, "c": point.c}


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


_IMPORT_PATTERN = re.compile(r"^(?:from|import)\s+phaino_acoustics(?:\b|\.)")


def _imports_acoustics_statically() -> bool:
    """True only if this certificate package itself imports the acoustics method."""
    package_dir = Path(__file__).resolve().parent
    for path in sorted(package_dir.glob("*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if _IMPORT_PATTERN.match(line.strip()):
                return True
    return False


def _method_protocol_block(protocol: ClaimsProtocol) -> dict[str, Any] | None:
    if not protocol.method_schema:
        return None
    document = protocol.document
    return {
        "schema": "method-claims-protocol",
        "source": protocol.source,
        "source_sha256": protocol.source_sha256,
        "protocol_id": protocol.protocol_id,
        "protocol_version": protocol.version,
        "protocol_digest": document.get("protocol_digest"),
        "symbolic_proof_digest": document.get("symbolic_proof_digest"),
        "declared_model": document.get("declared_model"),
        "clock_model": document.get("clock_model"),
        "symmetry_group": document.get("symmetry_group"),
        "convention_reconciliation": document.get("convention_reconciliation"),
        "thresholds": document.get("thresholds"),
        "declared_generators": list(protocol.declared_generators or ()),
        "declared_generators_source": (
            "explicit"
            if _method_has_explicit_generators(document)
            else "inferred_from_clock_model_and_action"
        ),
        "mapping": {
            "method_clock_model": document.get("clock_model"),
            "certificate_clock_model": "t_obs = t_phys / k_c + beta",
            "rate_mapping": "k_c = 1 / k_m",
            "action_equivalence": (
                "method action (f0/k_m, v, k_m*t0+beta, k_m*b) equals certificate "
                "action (k_c*f0, v, beta+t0/k_c, b/k_c) with k_c=1/k_m"
            ),
            "claim_quantity_map": {
                "v": "v",
                "f0_times_b": "b*f0 (quantity f0*b)",
                "b_over_f0": "b/f0",
                "t0": "t0",
                "b": "b",
                "f0": "f0",
            },
        },
        "claim_metadata": [
            _json_safe(claim.method_metadata)
            for claim in protocol.claims
            if claim.method_metadata is not None
        ],
    }


def _generator_coverage(protocol: ClaimsProtocol, generators: Mapping[str, Any]) -> dict[str, Any]:
    known = set(KNOWN_GENERATORS)
    required = set(REQUIRED_GENERATORS)
    declared = set(protocol.declared_generators or KNOWN_GENERATORS)
    tested = {
        name
        for name in known
        if isinstance(generators.get(name), Mapping) and generators[name].get("tested")
    }
    incomplete = sorted((required | declared) - tested)
    unsupported = sorted(declared - known)
    return {
        "declared": sorted(declared),
        "required": sorted(required),
        "tested": sorted(tested),
        "unsupported": unsupported,
        "incomplete_group": incomplete,
        "complete": not incomplete,
    }


def _annotate_claims(
    claims: list[dict[str, Any]],
    protocol: ClaimsProtocol,
    grid: np.ndarray,
    coverage: Mapping[str, Any],
) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    for claim in claims:
        scope = str(claim.get("scope", "")).lower()
        declares_invariance = (
            claim.get("symbolic_verdict") == "invariant" or "g_clock" in scope
        )
        group_complete = True
        if "g_clock" in scope or "clock" in scope:
            group_complete = bool(coverage["complete"])
        probe = _nuisance_probe(protocol, grid, claim, declares_invariance)
        claim["group_coverage_complete"] = group_complete
        claim["nuisance_probe"] = probe
        claim["nuisance_conflict"] = probe["conflicted"]
        reasons: list[str] = []
        if claim["numeric_verdict"] != "invariant":
            reasons.append("numeric_verdict_not_invariant")
        if claim["agrees_with_symbolic"] is False:
            reasons.append("symbolic_numeric_disagreement")
        if claim["nuisance_conflict"]:
            reasons.append("nuisance_conflict")
        if not group_complete:
            reasons.append("incomplete_group")
        if claim["agrees_with_symbolic"] is False:
            gate_status = "withheld_symbolic_disagreement"
        elif claim["numeric_verdict"] != "invariant":
            gate_status = "not_invariant"
        elif not group_complete:
            gate_status = "withheld_incomplete_group"
        elif claim["nuisance_conflict"]:
            gate_status = "withheld_nuisance_conflict"
        else:
            gate_status = "eligible"
        claim["promotion_allowed"] = gate_status == "eligible"
        claim["gate_status"] = gate_status
        claim["withheld_reasons"] = reasons
        if claim["nuisance_conflict"]:
            conflicts.append(
                {
                    "claim": claim["claim"],
                    "quantity": claim["quantity"],
                    "max_relative_mismatch": probe["max_relative_claim_mismatch"],
                    "probe": probe["probe"],
                    "status": "flagged_not_accepted",
                }
            )
    return conflicts


def _nuisance_probe(
    protocol: ClaimsProtocol,
    grid: np.ndarray,
    claim: Mapping[str, Any],
    declares_invariance: bool,
) -> dict[str, Any]:
    """Unknown sound speed probe: (v,b,c) -> (lambda v, lambda b, lambda c)."""
    lambdas = (0.9, 1.1)
    max_claim = 0.0
    max_forward = 0.0
    for scale in lambdas:
        for point in protocol.sample_points:
            transformed = ModelParameters(
                f0=point.f0,
                v=point.v * scale,
                t0=point.t0,
                b=point.b * scale,
                c=point.c * scale,
            )
            before = forward_model(grid, point)
            after = forward_model(grid, transformed)
            max_forward = max(
                max_forward,
                float(np.max(np.abs(before - after) / np.maximum(np.abs(before), 1e-300))),
            )
            max_claim = max(
                max_claim,
                relative_mismatch(
                    claim_value(claim["quantity"], point),
                    claim_value(claim["quantity"], transformed),
                ),
            )
    forward_preserved = max_forward <= protocol.observation_tolerance
    changed = max_claim > float(claim["tolerance"])
    conflicted = changed and bool(declares_invariance) and forward_preserved
    return {
        "probe": "sound_speed_scaling",
        "lambda_values": list(lambdas),
        "max_relative_claim_mismatch": max_claim,
        "max_relative_forward_mismatch": max_forward,
        "forward_preserved": forward_preserved,
        "conflicted": conflicted,
        "note": "unknown c admits (v,b,c)->(lambda v,lambda b,lambda c); a claim whose value "
        "changes cannot be promoted to a nuisance-free invariant",
    }


def _self_audit(
    protocol: ClaimsProtocol,
    generators: Mapping[str, Any],
    claims: list[dict[str, Any]],
    coverage: Mapping[str, Any],
) -> dict[str, Any]:
    declared = set(coverage["declared"])
    required = set(coverage["required"])
    names = sorted(declared | required | set(generators))
    generator_rows: list[dict[str, Any]] = []
    for name in names:
        report = generators.get(name)
        tested = bool(isinstance(report, Mapping) and report.get("tested"))
        generator_rows.append(
            {
                "generator_id": name,
                "declared": name in declared,
                "required": name in required,
                "supported": name in KNOWN_GENERATORS,
                "tested": tested,
                "preserves_forward": report.get("preserves_forward_model")
                if tested
                else None,
                "failure_class": report.get("failure_class") if tested else None,
                "max_relative_observation_mismatch": report.get(
                    "max_relative_observation_mismatch"
                )
                if tested
                else None,
            }
        )
    return {
        "generators": generator_rows,
        "claims": [
            {
                "claim": claim["claim"],
                "numeric_verdict": claim["numeric_verdict"],
                "symbolic_verdict": claim["symbolic_verdict"],
                "agrees_with_symbolic": claim["agrees_with_symbolic"],
                "group_coverage_complete": claim["group_coverage_complete"],
                "nuisance_conflict": claim["nuisance_conflict"],
                "promotion_allowed": claim["promotion_allowed"],
                "gate_status": claim["gate_status"],
            }
            for claim in claims
        ],
        "incomplete_group": list(coverage["incomplete_group"]),
        "incomplete": bool(coverage["incomplete_group"]),
        "missing_generators": list(coverage["incomplete_group"]),
        "group_coverage_complete": bool(coverage["complete"]),
    }


def _method_has_explicit_generators(document: Mapping[str, Any]) -> bool:
    group = document.get("symmetry_group")
    if isinstance(group, Mapping) and "generators" in group:
        return True
    return "generators" in document
