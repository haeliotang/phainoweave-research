"""Claims protocol for the invariance certificate.

A method-side claims protocol can be supplied with ``--claims``. Its schema is declared
here; when no file exists the certificate uses a minimal built-in protocol and says so.
The built-in symbolic verdicts follow the method-side claim set in ADR 0016/0017:
``v`` invariant, ``b/f0`` invariant, ``t0``/``b``/``f0`` not invariant under ``G_clock``.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .model import ClockTransform, ModelParameters, parameters_from_document

CERTIFICATE_VERSION = "1.0.0"
KNOWN_GENERATORS = ("clock_offset", "clock_rate")
REQUIRED_GENERATORS = ("clock_offset", "clock_rate")
CLAIM_QUANTITIES = frozenset({"v", "b/f0", "t0", "b", "f0", "b*f0"})
SYMBOLIC_VERDICTS = frozenset({"invariant", "not_invariant", "unknown"})
CLAIM_KEYS = frozenset(
    {"claim", "quantity", "symbolic_verdict", "scope", "tolerance", "rationale"}
)
PROTOCOL_KEYS = frozenset(
    {
        "protocol_id",
        "version",
        "description",
        "model",
        "tolerances",
        "observation_grid",
        "sample_points",
        "generators",
        "claims",
        "nuisance_assumptions",
    }
)


class ClaimsProtocolError(ValueError):
    """Raised when a claims protocol cannot be validated."""


@dataclass(frozen=True)
class ClaimSpec:
    claim: str
    quantity: str
    symbolic_verdict: str
    scope: str
    tolerance: float
    rationale: str
    operational_tolerance: float | None = None
    operational_tolerance_kind: str | None = None
    method_metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ClaimsProtocol:
    protocol_id: str
    version: str
    description: str
    model_name: str
    c: float
    observation_tolerance: float
    implementation_tolerance: float
    grid: tuple[float, float, int]
    sample_points: tuple[ModelParameters, ...]
    offset_transforms: tuple[ClockTransform, ...]
    rate_transforms: tuple[ClockTransform, ...]
    claims: tuple[ClaimSpec, ...]
    nuisance_assumptions: tuple[str, ...]
    source: str
    builtin: bool
    document: Mapping[str, Any]
    method_schema: bool = False
    source_sha256: str | None = None
    declared_generators: tuple[str, ...] | None = None

    def digest(self) -> str:
        payload = json.dumps(self.document, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def all_transforms(self) -> tuple[ClockTransform, ...]:
        return self.offset_transforms + self.rate_transforms


def builtin_protocol() -> ClaimsProtocol:
    """The minimal protocol used when the method-side claims file is absent."""
    document = {
        "protocol_id": "builtin-e0-clock-invariance",
        "version": "1.0.0",
        "description": (
            "Built-in minimal claim protocol for the E0 narrowband Doppler clock "
            "symmetry. Used because the method-side claims protocol is not present."
        ),
        "model": {"name": "e0-narrowband-doppler", "c": 343.0},
        "tolerances": {
            "observation_relative": 1e-12,
            "implementation_relative": 1e-9,
        },
        "observation_grid": {"t_min": 0.0, "t_max": 40.0, "count": 161},
        "sample_points": [
            {"f0": 500.0, "v": 250.0, "t0": 20.0, "b": 3000.0, "c": 343.0},
            {"f0": 118.4, "v": 150.0, "t0": 10.0, "b": 1000.0, "c": 343.0},
            {"f0": 900.0, "v": 350.0, "t0": 30.0, "b": 6000.0, "c": 343.0},
            {"f0": 250.0, "v": 80.0, "t0": 25.0, "b": 150.0, "c": 343.0},
        ],
        "generators": {
            "clock_offset": {"betas": [-1e-3, 1e-3, -3.0, -0.5, 0.5, 3.0]},
            "clock_rate": {"kappas": [0.99999, 1.00001, 0.975, 0.99, 1.01, 1.025]},
        },
        "claims": [
            {
                "claim": "v",
                "quantity": "v",
                "symbolic_verdict": "invariant",
                "scope": "G_clock",
                "tolerance": 1e-12,
                "rationale": "Relative speed is unchanged by both clock generators.",
            },
            {
                "claim": "b/f0",
                "quantity": "b/f0",
                "symbolic_verdict": "invariant",
                "scope": "G_clock",
                "tolerance": 1e-12,
                "rationale": (
                    "Method-side claim from PR-4d/ADR 0016: the ratio b/f0 is asserted "
                    "invariant under clock rate. The independent numeric check tests it."
                ),
            },
            {
                "claim": "t0",
                "quantity": "t0",
                "symbolic_verdict": "not_invariant",
                "scope": "G_clock",
                "tolerance": 1e-12,
                "rationale": "Clock offset is degenerate with event time; rate rescales it.",
            },
            {
                "claim": "b",
                "quantity": "b",
                "symbolic_verdict": "not_invariant",
                "scope": "G_clock",
                "tolerance": 1e-12,
                "rationale": "Clock rate scales closest approach.",
            },
            {
                "claim": "f0",
                "quantity": "f0",
                "symbolic_verdict": "not_invariant",
                "scope": "G_clock",
                "tolerance": 1e-12,
                "rationale": "Clock rate scales the source frequency.",
            },
        ],
        "nuisance_assumptions": [
            "sound_speed_c",
            "source_direction",
            "acceleration",
            "propagation_environment",
        ],
    }
    return _from_document(document, source="builtin", builtin=True)


def load_claims_protocol(path: str | Path) -> ClaimsProtocol:
    """Loads a method-side claims protocol; invalid schemas fail with a typed error."""
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as error:
        raise ClaimsProtocolError(f"cannot read claims protocol {source}: {error}") from error
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ClaimsProtocolError(f"{source}: malformed JSON: {error}") from error
    if not isinstance(document, Mapping):
        raise ClaimsProtocolError(f"{source}: claims protocol must be a JSON object")
    return _from_document(document, source=str(source), builtin=False)


METHOD_PROTOCOL_KEYS = frozenset(
    {
        "experiment",
        "protocol_version",
        "declared_model",
        "clock_model",
        "symmetry_group",
        "convention_reconciliation",
        "claims",
        "thresholds",
    }
)
METHOD_CLAIM_KEYS = frozenset(
    {"claim_id", "claim_kind", "claim_tolerance", "l1_status", "l2_status", "max_status"}
)
METHOD_EXPRESSION_QUANTITIES = {
    "v": "v",
    "t0": "t0",
    "b": "b",
    "f0": "f0",
    "b/f0": "b/f0",
    "b_over_f0": "b/f0",
    "f0*b": "b*f0",
    "b*f0": "b*f0",
    "f0_times_b": "b*f0",
}


def load_method_protocol(path: str | Path) -> ClaimsProtocol:
    """Loads and maps the method workstream's PR-4e claims-protocol schema.

    The method protocol fixes the clock convention ``t_obs = k_m t_phys + beta`` and the
    action ``(f0/k_m, v, k_m t0 + beta, k_m b)``. This certificate uses the reciprocal
    ``k_c = 1/k_m`` convention, so the mapped action is identical. The method's
    ``claim_tolerance`` values are *operational* L3 tolerances; they are reported but are
    not used as the numerical invariance tolerance (default/declared L1 tolerance: 1e-12).
    """
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as error:
        raise ClaimsProtocolError(f"cannot read method protocol {source}: {error}") from error
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ClaimsProtocolError(f"{source}: malformed JSON: {error}") from error
    if not isinstance(document, Mapping):
        raise ClaimsProtocolError(f"{source}: method protocol must be a JSON object")
    missing = sorted(METHOD_PROTOCOL_KEYS - set(document))
    if missing:
        raise ClaimsProtocolError(
            f"{source}: missing method-protocol keys: {', '.join(missing)}"
        )

    experiment = document["experiment"]
    if not isinstance(experiment, str) or not experiment:
        raise ClaimsProtocolError(f"{source}: experiment must be a non-empty string")
    version = document["protocol_version"]
    if not isinstance(version, str) or not version:
        raise ClaimsProtocolError(f"{source}: protocol_version must be a non-empty string")
    declared_model = document["declared_model"]
    if not isinstance(declared_model, str) or not declared_model:
        raise ClaimsProtocolError(f"{source}: declared_model must be a non-empty string")
    clock_model = document["clock_model"]
    if not isinstance(clock_model, str) or not clock_model:
        raise ClaimsProtocolError(f"{source}: clock_model must be a non-empty string")
    if "k" not in clock_model or "beta" not in clock_model:
        raise ClaimsProtocolError(
            f"{source}: clock_model must describe k and beta (got {clock_model!r})"
        )
    symmetry_group = document["symmetry_group"]
    if not isinstance(symmetry_group, Mapping):
        raise ClaimsProtocolError(f"{source}: symmetry_group must be an object")
    if not isinstance(symmetry_group.get("action"), str):
        raise ClaimsProtocolError(f"{source}: symmetry_group.action must be a string")
    convention = document["convention_reconciliation"]
    if not isinstance(convention, Mapping):
        raise ClaimsProtocolError(f"{source}: convention_reconciliation must be an object")
    thresholds = document["thresholds"]
    if not isinstance(thresholds, Mapping):
        raise ClaimsProtocolError(f"{source}: thresholds must be an object")

    base = builtin_protocol()
    declared_generators = _method_declared_generators(document)
    offset_transforms = (
        base.offset_transforms if "clock_offset" in declared_generators else ()
    )
    rate_transforms = (
        base.rate_transforms if "clock_rate" in declared_generators else ()
    )
    claims_raw = document["claims"]
    if not isinstance(claims_raw, list) or not claims_raw:
        raise ClaimsProtocolError(f"{source}: claims must be a non-empty list")
    claims: list[ClaimSpec] = []
    seen: set[str] = set()
    nuisance: set[str] = set()
    for index, raw_claim in enumerate(claims_raw):
        where = f"{source}: claims[{index}]"
        if not isinstance(raw_claim, Mapping):
            raise ClaimsProtocolError(f"{where} must be an object")
        missing_claim = sorted(METHOD_CLAIM_KEYS - set(raw_claim))
        if missing_claim:
            raise ClaimsProtocolError(
                f"{where} is missing method claim fields: {', '.join(missing_claim)}"
            )
        claim_id = raw_claim["claim_id"]
        if not isinstance(claim_id, str) or not claim_id or claim_id in seen:
            raise ClaimsProtocolError(f"{where}.claim_id is invalid or duplicated")
        expression = raw_claim.get("expression", raw_claim.get("value_expression", claim_id))
        quantity = _method_quantity(expression, claim_id)
        if quantity is None:
            raise ClaimsProtocolError(
                f"{where}.expression {expression!r} is not a known claim quantity"
            )
        l1_status = raw_claim["l1_status"]
        if not isinstance(l1_status, str):
            raise ClaimsProtocolError(f"{where}.l1_status must be a string")
        symbolic = _method_symbolic_verdict(l1_status, raw_claim.get("max_status"))
        claim_tolerance = raw_claim["claim_tolerance"]
        if not isinstance(claim_tolerance, Mapping):
            raise ClaimsProtocolError(f"{where}.claim_tolerance must be an object")
        operational = claim_tolerance.get("value")
        if not _finite(operational) or float(operational) <= 0.0:
            raise ClaimsProtocolError(f"{where}.claim_tolerance.value must be positive")
        tolerance = _method_numeric_tolerance(raw_claim, where)
        scope = raw_claim.get("symmetry_scope", "G_clock")
        if not isinstance(scope, str) or not scope:
            raise ClaimsProtocolError(f"{where}.symmetry_scope must be a string")
        rationale = raw_claim.get("label")
        if not isinstance(rationale, str) or not rationale:
            rationale = " ".join(
                str(item) for item in raw_claim.get("conditioning", []) if item
            ) or claim_id
        for item in raw_claim.get("nuisance_assumptions", []):
            if isinstance(item, str) and item:
                nuisance.add(item)
        metadata = {
            "claim_id": claim_id,
            "claim_kind": raw_claim.get("claim_kind"),
            "expression": expression,
            "l1_status": l1_status,
            "l2_status": raw_claim.get("l2_status"),
            "max_status": raw_claim.get("max_status"),
            "conditioning": raw_claim.get("conditioning", []),
            "operational_tolerance": {
                "kind": claim_tolerance.get("kind"),
                "value": float(operational),
                "source": claim_tolerance.get("source"),
            },
            "l1_certificate": raw_claim.get("l1_certificate"),
            "units": raw_claim.get("units"),
            "evaluated": raw_claim.get("evaluated"),
        }
        seen.add(claim_id)
        claims.append(
            ClaimSpec(
                claim=claim_id,
                quantity=quantity,
                symbolic_verdict=symbolic,
                scope=scope,
                tolerance=tolerance,
                rationale=rationale,
                operational_tolerance=float(operational),
                operational_tolerance_kind=(
                    claim_tolerance.get("kind")
                    if isinstance(claim_tolerance.get("kind"), str)
                    else None
                ),
                method_metadata=metadata,
            )
        )

    if not nuisance:
        nuisance = set(base.nuisance_assumptions)
    return ClaimsProtocol(
        protocol_id=f"{experiment}:{version}",
        version=version,
        description=declared_model,
        model_name=base.model_name,
        c=base.c,
        observation_tolerance=base.observation_tolerance,
        implementation_tolerance=base.implementation_tolerance,
        grid=base.grid,
        sample_points=base.sample_points,
        offset_transforms=offset_transforms,
        rate_transforms=rate_transforms,
        claims=tuple(claims),
        nuisance_assumptions=tuple(sorted(nuisance)),
        source=str(source),
        builtin=False,
        document=dict(document),
        method_schema=True,
        source_sha256=hashlib.sha256(raw).hexdigest(),
        declared_generators=declared_generators,
    )


def _method_declared_generators(document: Mapping[str, Any]) -> tuple[str, ...]:
    """Reads explicit generator declarations, else infers the two clock generators.

    Method protocols in the wild may put a ``generators`` list under ``symmetry_group``
    or at top level. If neither exists, the clock model / group action implies the
    standard clock offset and clock rate generators.
    """
    group = document.get("symmetry_group")
    raw = None
    if isinstance(group, Mapping) and "generators" in group:
        raw = group["generators"]
    elif "generators" in document:
        raw = document["generators"]
    ids: list[str] = []
    if isinstance(raw, Mapping):
        raw = list(raw.keys())
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item:
                ids.append(item)
            elif isinstance(item, Mapping):
                for key in ("generator_id", "id", "name"):
                    value = item.get(key)
                    if isinstance(value, str) and value:
                        ids.append(value)
                        break
    if ids:
        # Stable de-duplication.
        seen: set[str] = set()
        unique: list[str] = []
        for item in ids:
            if item not in seen:
                seen.add(item)
                unique.append(item)
        return tuple(unique)
    text = " ".join(
        str(part)
        for part in (
            document.get("clock_model", ""),
            group.get("action", "") if isinstance(group, Mapping) else "",
            group.get("set", "") if isinstance(group, Mapping) else "",
        )
    ).lower()
    inferred: list[str] = []
    if "beta" in text or "offset" in text:
        inferred.append("clock_offset")
    if "k" in text or "rate" in text or "epsilon" in text:
        inferred.append("clock_rate")
    return tuple(inferred) if inferred else REQUIRED_GENERATORS


def _method_quantity(expression: Any, claim_id: str) -> str | None:
    text = str(expression).strip()
    if text in METHOD_EXPRESSION_QUANTITIES:
        return METHOD_EXPRESSION_QUANTITIES[text]
    return METHOD_EXPRESSION_QUANTITIES.get(str(claim_id).strip())


def _method_symbolic_verdict(l1_status: str, max_status: Any) -> str:
    status = l1_status.strip().lower()
    if status in {"proven", "pass", "passed", "invariant"}:
        return "invariant"
    if status in {"refuted", "failed", "fail", "counterexample"}:
        return "not_invariant"
    if str(max_status).strip().lower() == "contradicted":
        return "not_invariant"
    return "unknown"


def _method_numeric_tolerance(raw_claim: Mapping[str, Any], where: str) -> float:
    certificate = raw_claim.get("l1_certificate")
    if isinstance(certificate, Mapping):
        value = certificate.get("tolerance")
        if value is not None:
            if not _finite(value) or float(value) <= 0.0:
                raise ClaimsProtocolError(f"{where}.l1_certificate.tolerance must be positive")
            return float(value)
    return 1e-12


def _from_document(
    document: Mapping[str, Any], source: str, builtin: bool
) -> ClaimsProtocol:
    missing = sorted(PROTOCOL_KEYS - set(document))
    if missing:
        raise ClaimsProtocolError(
            f"{source}: missing claims-protocol keys: {', '.join(missing)}"
        )
    unknown = sorted(set(document) - PROTOCOL_KEYS)
    if unknown:
        raise ClaimsProtocolError(
            f"{source}: unsupported claims-protocol keys: {', '.join(unknown)}"
        )
    if not isinstance(document["protocol_id"], str) or not document["protocol_id"]:
        raise ClaimsProtocolError(f"{source}: protocol_id must be a non-empty string")
    if not isinstance(document["version"], str) or not document["version"]:
        raise ClaimsProtocolError(f"{source}: version must be a non-empty string")
    if not isinstance(document["description"], str) or not document["description"]:
        raise ClaimsProtocolError(f"{source}: description must be a non-empty string")
    model = document["model"]
    if not isinstance(model, Mapping) or not isinstance(model.get("name"), str):
        raise ClaimsProtocolError(f"{source}: model must contain a name")
    c = model.get("c", 343.0)
    if not _finite(c) or float(c) <= 0.0:
        raise ClaimsProtocolError(f"{source}: model.c must be a positive finite number")
    tolerances = document["tolerances"]
    if not isinstance(tolerances, Mapping):
        raise ClaimsProtocolError(f"{source}: tolerances must be an object")
    observation_tolerance = tolerances.get("observation_relative")
    implementation_tolerance = tolerances.get("implementation_relative")
    for label, value in (
        ("observation_relative", observation_tolerance),
        ("implementation_relative", implementation_tolerance),
    ):
        if not _finite(value) or float(value) <= 0.0:
            raise ClaimsProtocolError(f"{source}: tolerances.{label} must be positive")
    grid = document["observation_grid"]
    if not isinstance(grid, Mapping):
        raise ClaimsProtocolError(f"{source}: observation_grid must be an object")
    t_min = grid.get("t_min")
    t_max = grid.get("t_max")
    count = grid.get("count")
    if not (_finite(t_min) and _finite(t_max) and float(t_max) > float(t_min)):
        raise ClaimsProtocolError(f"{source}: observation_grid bounds must be finite and increasing")
    if not _is_int(count) or count < 3:
        raise ClaimsProtocolError(f"{source}: observation_grid.count must be an integer >= 3")

    points_raw = document["sample_points"]
    if not isinstance(points_raw, list) or not points_raw:
        raise ClaimsProtocolError(f"{source}: sample_points must be a non-empty list")
    points: list[ModelParameters] = []
    for index, raw_point in enumerate(points_raw):
        if not isinstance(raw_point, Mapping):
            raise ClaimsProtocolError(f"{source}: sample_points[{index}] must be an object")
        point = parameters_from_document(raw_point)
        if not point.valid():
            raise ClaimsProtocolError(f"{source}: sample_points[{index}] is not a valid parameter point")
        points.append(ModelParameters(f0=point.f0, v=point.v, t0=point.t0, b=point.b, c=float(c)))

    generators = document["generators"]
    if not isinstance(generators, Mapping):
        raise ClaimsProtocolError(f"{source}: generators must be an object")
    offset_raw = generators.get("clock_offset")
    rate_raw = generators.get("clock_rate")
    if not isinstance(offset_raw, Mapping) or not isinstance(rate_raw, Mapping):
        raise ClaimsProtocolError(
            f"{source}: generators must contain clock_offset and clock_rate"
        )
    betas = offset_raw.get("betas")
    kappas = rate_raw.get("kappas")
    if not isinstance(betas, list) or not betas or not all(_finite(value) for value in betas):
        raise ClaimsProtocolError(f"{source}: clock_offset.betas must be finite values")
    if not isinstance(kappas, list) or not kappas or not all(_finite(value) for value in kappas):
        raise ClaimsProtocolError(f"{source}: clock_rate.kappas must be finite values")
    if any(float(k) <= 0.0 for k in kappas):
        raise ClaimsProtocolError(f"{source}: clock_rate.kappas must be positive")
    offset_transforms = tuple(ClockTransform(k=1.0, beta=float(beta)) for beta in betas)
    rate_transforms = tuple(ClockTransform(k=float(kappa), beta=0.0) for kappa in kappas)

    claims_raw = document["claims"]
    if not isinstance(claims_raw, list) or not claims_raw:
        raise ClaimsProtocolError(f"{source}: claims must be a non-empty list")
    claims: list[ClaimSpec] = []
    seen: set[str] = set()
    for index, raw_claim in enumerate(claims_raw):
        if not isinstance(raw_claim, Mapping):
            raise ClaimsProtocolError(f"{source}: claims[{index}] must be an object")
        if set(raw_claim) != CLAIM_KEYS:
            missing_claim = sorted(CLAIM_KEYS - set(raw_claim))
            unknown_claim = sorted(set(raw_claim) - CLAIM_KEYS)
            raise ClaimsProtocolError(
                f"{source}: claims[{index}] key mismatch "
                f"(missing {missing_claim}, unknown {unknown_claim})"
            )
        claim_id = raw_claim["claim"]
        quantity = raw_claim["quantity"]
        verdict = raw_claim["symbolic_verdict"]
        scope = raw_claim["scope"]
        tolerance = raw_claim["tolerance"]
        rationale = raw_claim["rationale"]
        if not isinstance(claim_id, str) or not claim_id or claim_id in seen:
            raise ClaimsProtocolError(f"{source}: claims[{index}].claim invalid or duplicate")
        if quantity not in CLAIM_QUANTITIES:
            raise ClaimsProtocolError(
                f"{source}: claims[{index}].quantity must be one of {sorted(CLAIM_QUANTITIES)}"
            )
        if verdict not in SYMBOLIC_VERDICTS:
            raise ClaimsProtocolError(
                f"{source}: claims[{index}].symbolic_verdict must be one of "
                f"{sorted(SYMBOLIC_VERDICTS)}"
            )
        if not isinstance(scope, str) or not scope:
            raise ClaimsProtocolError(f"{source}: claims[{index}].scope must be a string")
        if not _finite(tolerance) or float(tolerance) <= 0.0:
            raise ClaimsProtocolError(f"{source}: claims[{index}].tolerance must be positive")
        if not isinstance(rationale, str) or not rationale:
            raise ClaimsProtocolError(f"{source}: claims[{index}].rationale must be a string")
        seen.add(claim_id)
        claims.append(
            ClaimSpec(
                claim=claim_id,
                quantity=quantity,
                symbolic_verdict=verdict,
                scope=scope,
                tolerance=float(tolerance),
                rationale=rationale,
            )
        )

    nuisance = document["nuisance_assumptions"]
    if not isinstance(nuisance, list) or any(not isinstance(item, str) for item in nuisance):
        raise ClaimsProtocolError(f"{source}: nuisance_assumptions must be a list of strings")

    return ClaimsProtocol(
        protocol_id=document["protocol_id"],
        version=document["version"],
        description=document["description"],
        model_name=model["name"],
        c=float(c),
        observation_tolerance=float(observation_tolerance),
        implementation_tolerance=float(implementation_tolerance),
        grid=(float(t_min), float(t_max), int(count)),
        sample_points=tuple(points),
        offset_transforms=offset_transforms,
        rate_transforms=rate_transforms,
        claims=tuple(claims),
        nuisance_assumptions=tuple(nuisance),
        source=source,
        builtin=builtin,
        document=dict(document),
        declared_generators=tuple(sorted(generators.keys())),
    )


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
