"""Comparison protocol model: R0/R1/R2 definitions, field classes, tolerances, structure.

A protocol is data, not code. Tolerances are supplied by the protocol file; the comparison
engine contains no final tolerance constants. Every unknown or malformed key is rejected so
a typo cannot silently weaken a comparison.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from phaino_sdk.canonical import canonical_sha256

from .artifacts import parse_json_document
from .paths import PathError, parse_path

PROTOCOL_KEYS = frozenset(
    {
        "protocol_id",
        "version",
        "description",
        "tolerance_status",
        "tolerance_note",
        "levels",
        "exact_fields",
        "numeric_fields",
        "ignored_fields",
        "structural_rules",
        "decision_instability",
    }
)
OPTIONAL_PROTOCOL_KEYS = frozenset({"unclassified_field_policy"})
LEVEL_KEYS = ("r0_execution", "r1_numerical_equivalence", "r2_bitwise_identity")
STRUCTURAL_KEYS = (
    "required_keys",
    "trials_key",
    "conditions_key",
    "trial_key",
    "condition_key",
    "required_trial_keys",
    "same_condition_set",
    "same_condition_order",
    "exactly_once",
    "no_duplicates",
    "no_missing",
    "no_extra",
)
DECISION_KEYS = ("decision_fields", "parameter_scope")
TOLERANCE_STATUSES = frozenset({"example_only", "measured"})
UNCLASSIFIED_POLICIES = frozenset({"exact", "ignore"})
PARAMETER_SCOPES = frozenset({"trial"})


class ProtocolError(ValueError):
    """Raised when a comparison protocol is malformed or incomplete."""


@dataclass(frozen=True)
class NumericField:
    """One numeric field class with an absolute-plus-relative tolerance."""

    path: str
    abs_tol: float
    rel_tol: float
    optional: bool = False


@dataclass(frozen=True)
class StructuralRules:
    """R0 structure rules for the artifact family."""

    required_keys: tuple[str, ...]
    trials_key: str
    conditions_key: str
    trial_key: tuple[str, ...]
    condition_key: str
    required_trial_keys: tuple[str, ...]
    same_condition_set: bool
    same_condition_order: bool
    exactly_once: bool
    no_duplicates: bool
    no_missing: bool
    no_extra: bool


@dataclass(frozen=True)
class DecisionInstabilityRule:
    """Which decisions count as flips when the numeric parameters stay in tolerance."""

    decision_fields: tuple[str, ...]
    parameter_scope: str


@dataclass(frozen=True)
class Protocol:
    """A validated comparison protocol."""

    protocol_id: str
    version: int
    description: str
    tolerance_status: str
    tolerance_note: str
    levels: Mapping[str, str]
    exact_fields: tuple[str, ...]
    numeric_fields: tuple[NumericField, ...]
    ignored_fields: tuple[str, ...]
    structural_rules: StructuralRules
    decision_instability: DecisionInstabilityRule
    unclassified_field_policy: str
    document: Mapping[str, Any]

    def digest(self) -> str:
        return canonical_sha256(self.document)

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> Protocol:
        _validate(document)
        levels = document["levels"]
        rules_document = document["structural_rules"]
        instability = document["decision_instability"]
        return cls(
            protocol_id=document["protocol_id"],
            version=document["version"],
            description=document["description"],
            tolerance_status=document["tolerance_status"],
            tolerance_note=document["tolerance_note"],
            levels={key: levels[key] for key in LEVEL_KEYS},
            exact_fields=tuple(document["exact_fields"]),
            numeric_fields=tuple(
                NumericField(
                    path=entry["path"],
                    abs_tol=float(entry["abs_tol"]),
                    rel_tol=float(entry["rel_tol"]),
                    optional=bool(entry.get("optional", False)),
                )
                for entry in document["numeric_fields"]
            ),
            ignored_fields=tuple(document["ignored_fields"]),
            structural_rules=StructuralRules(
                required_keys=tuple(rules_document["required_keys"]),
                trials_key=rules_document["trials_key"],
                conditions_key=rules_document["conditions_key"],
                trial_key=tuple(rules_document["trial_key"]),
                condition_key=rules_document["condition_key"],
                required_trial_keys=tuple(rules_document["required_trial_keys"]),
                same_condition_set=bool(rules_document["same_condition_set"]),
                same_condition_order=bool(rules_document["same_condition_order"]),
                exactly_once=bool(rules_document["exactly_once"]),
                no_duplicates=bool(rules_document["no_duplicates"]),
                no_missing=bool(rules_document["no_missing"]),
                no_extra=bool(rules_document["no_extra"]),
            ),
            decision_instability=DecisionInstabilityRule(
                decision_fields=tuple(instability["decision_fields"]),
                parameter_scope=instability["parameter_scope"],
            ),
            unclassified_field_policy=document.get("unclassified_field_policy", "exact"),
            document=dict(document),
        )


def load_protocol(path: str | Path) -> Protocol | ProtocolV2:
    """Loads and strictly validates a protocol JSON file (contract v1 or v2)."""
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as error:
        raise ProtocolError(f"cannot read protocol {source}: {error}") from error
    try:
        document = parse_json_document(raw, source=str(source))
    except ValueError as error:
        raise ProtocolError(str(error)) from error
    if not isinstance(document, Mapping):
        raise ProtocolError(f"{source}: protocol must be a JSON object")
    if document.get("contract_version") == 2:
        return ProtocolV2.from_document(document)
    return Protocol.from_document(document)


def _validate(document: Mapping[str, Any]) -> None:
    if not isinstance(document, Mapping):
        raise ProtocolError("protocol must be an object")
    keys = set(document)
    missing = sorted(PROTOCOL_KEYS - keys)
    if missing:
        raise ProtocolError(f"protocol missing keys: {', '.join(missing)}")
    unknown = sorted(keys - PROTOCOL_KEYS - OPTIONAL_PROTOCOL_KEYS)
    if unknown:
        raise ProtocolError(f"protocol has unknown keys: {', '.join(unknown)}")

    _require_string(document["protocol_id"], "protocol_id")
    _require_string(document["description"], "description")
    if not _is_int(document["version"]) or document["version"] < 1:
        raise ProtocolError("version must be an integer >= 1")
    if document["tolerance_status"] not in TOLERANCE_STATUSES:
        raise ProtocolError(
            f"tolerance_status must be one of {sorted(TOLERANCE_STATUSES)}"
        )
    _require_string(document["tolerance_note"], "tolerance_note")

    levels = document["levels"]
    if not isinstance(levels, Mapping) or set(levels) != set(LEVEL_KEYS):
        raise ProtocolError(f"levels must contain exactly {', '.join(LEVEL_KEYS)}")
    for key in LEVEL_KEYS:
        _require_string(levels[key], f"levels.{key}")

    _require_path_list(document["exact_fields"], "exact_fields")
    _require_path_list(document["ignored_fields"], "ignored_fields")
    _require_numeric_fields(document["numeric_fields"])
    _require_structural_rules(document["structural_rules"])
    _require_decision_rule(document["decision_instability"])

    policy = document.get("unclassified_field_policy", "exact")
    if policy not in UNCLASSIFIED_POLICIES:
        raise ProtocolError(
            f"unclassified_field_policy must be one of {sorted(UNCLASSIFIED_POLICIES)}"
        )


def _require_string(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError(f"{label} must be a non-empty string")


def _require_path_list(value: Any, label: str) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ProtocolError(f"{label} must be a list of path strings")
    for item in value:
        _require_path(item, label)


def _require_path(value: Any, label: str) -> None:
    if not isinstance(value, str):
        raise ProtocolError(f"{label} must be a path string")
    try:
        parse_path(value)
    except PathError as error:
        raise ProtocolError(f"{label}: {error}") from error


def _require_numeric_fields(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise ProtocolError("numeric_fields must be a non-empty list")
    seen: set[str] = set()
    for index, entry in enumerate(value):
        if not isinstance(entry, Mapping):
            raise ProtocolError(f"numeric_fields[{index}] must be an object")
        missing = {"path", "abs_tol", "rel_tol"} - set(entry)
        if missing:
            raise ProtocolError(
                f"numeric_fields[{index}] missing keys: {', '.join(sorted(missing))}"
            )
        unknown = set(entry) - {"path", "abs_tol", "rel_tol", "optional"}
        if unknown:
            raise ProtocolError(
                f"numeric_fields[{index}] has unknown keys: {', '.join(sorted(unknown))}"
            )
        _require_path(entry["path"], f"numeric_fields[{index}].path")
        if entry["path"] in seen:
            raise ProtocolError(f"duplicate numeric field path {entry['path']!r}")
        seen.add(entry["path"])
        for key in ("abs_tol", "rel_tol"):
            tolerance = entry[key]
            if (
                not isinstance(tolerance, (int, float))
                or isinstance(tolerance, bool)
                or not math.isfinite(float(tolerance))
                or float(tolerance) < 0.0
            ):
                raise ProtocolError(
                    f"numeric_fields[{index}].{key} must be a finite number >= 0"
                )
        if "optional" in entry and not isinstance(entry["optional"], bool):
            raise ProtocolError(f"numeric_fields[{index}].optional must be a boolean")


def _require_structural_rules(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise ProtocolError("structural_rules must be an object")
    if set(value) != set(STRUCTURAL_KEYS):
        missing = sorted(set(STRUCTURAL_KEYS) - set(value))
        unknown = sorted(set(value) - set(STRUCTURAL_KEYS))
        detail = []
        if missing:
            detail.append(f"missing {', '.join(missing)}")
        if unknown:
            detail.append(f"unknown {', '.join(unknown)}")
        raise ProtocolError(f"structural_rules must contain exactly the contract keys ({'; '.join(detail)})")
    for key in ("required_keys", "required_trial_keys", "trial_key"):
        if not isinstance(value[key], list) or not value[key]:
            raise ProtocolError(f"structural_rules.{key} must be a non-empty list")
        if any(not isinstance(item, str) or not item for item in value[key]):
            raise ProtocolError(f"structural_rules.{key} must contain non-empty strings")
    for key in ("trials_key", "conditions_key", "condition_key"):
        _require_string(value[key], f"structural_rules.{key}")
    for key in (
        "same_condition_set",
        "same_condition_order",
        "exactly_once",
        "no_duplicates",
        "no_missing",
        "no_extra",
    ):
        if not isinstance(value[key], bool):
            raise ProtocolError(f"structural_rules.{key} must be a boolean")
    if value["condition_key"] not in value["trial_key"]:
        raise ProtocolError("structural_rules.trial_key must include the condition_key")
    if len(set(value["required_keys"])) != len(value["required_keys"]):
        raise ProtocolError("structural_rules.required_keys contains duplicates")


def _require_decision_rule(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise ProtocolError("decision_instability must be an object")
    if set(value) != set(DECISION_KEYS):
        raise ProtocolError(
            "decision_instability must contain exactly "
            + ", ".join(DECISION_KEYS)
        )
    _require_path_list(value["decision_fields"], "decision_instability.decision_fields")
    if value["parameter_scope"] not in PARAMETER_SCOPES:
        raise ProtocolError(
            f"decision_instability.parameter_scope must be one of {sorted(PARAMETER_SCOPES)}"
        )


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


# ---------------------------------------------------------------------------
# Contract v2: four field classes, reference-side identifiability, decision margins
# ---------------------------------------------------------------------------

V2_KEYS = frozenset(
    {
        "contract_version",
        "protocol_id",
        "version",
        "description",
        "tolerance_status",
        "tolerance_note",
        "levels",
        "field_classes",
        "identifiability",
        "rate_checks",
        "structural_rules",
        "ignored_fields",
    }
)
V2_LEVEL_KEYS = (
    "r0_execution",
    "r1_numerical_equivalence",
    "r1_decision_equivalence",
    "r2_bitwise_identity",
)
V2_PERMITTED_TOLERANCE_STATUSES = TOLERANCE_STATUSES | {"measured_draft_not_frozen"}
CLASS_KEYS = (
    "A_discrete_identity",
    "B_identifiable_numeric",
    "C_unidentifiable_diagnostic",
    "D_decision",
)
DECISION_COMPARISONS = frozenset({"lt", "le", "gt", "ge", "abs_lt", "abs_le"})
IDENTIFIABILITY_CHECKS = frozenset(
    {"true", "false", "lt", "le", "gt", "ge", "all_finite", "not_null"}
)
DIAGNOSTIC_SEMANTICS = frozenset({"magnitude_class"})


@dataclass(frozen=True)
class FieldSpec:
    """One B-class numeric field with a tolerance and an applicability scope."""

    path: str
    abs_tol: float
    rel_tol: float
    scope: str = "trial"


@dataclass(frozen=True)
class DiagnosticField:
    """One C-class diagnostic compared semantically, never as an R1 failure."""

    path: str
    semantics: str = "magnitude_class"
    decades: int = 1
    sign_sensitive: bool = False


@dataclass(frozen=True)
class DecisionSpec:
    """One D-class decision: threshold-with-margin, derived, or exact."""

    name: str
    path: str
    kind: str
    justification: str
    statistic: str | None = None
    comparison: str | None = None
    threshold: float | None = None
    margin: float | None = None
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class IdentifiabilityCondition:
    """One clause of the pre-declared reference-side identifiability rule."""

    field: str
    check: str
    value: float | None = None


@dataclass(frozen=True)
class IdentifiabilityRule:
    rule_id: str
    description: str
    all_of: tuple[IdentifiabilityCondition, ...]


@dataclass(frozen=True)
class RateCheck:
    """A condition-level rate/count check with a declared material threshold."""

    path: str
    material_abs_change: float
    justification: str


@dataclass(frozen=True)
class ProtocolV2:
    """A validated contract-v2 comparison protocol."""

    protocol_id: str
    version: int
    description: str
    tolerance_status: str
    tolerance_note: str
    levels: Mapping[str, str]
    a_fields: tuple[str, ...]
    b_fields: tuple[FieldSpec, ...]
    c_fields: tuple[DiagnosticField, ...]
    decisions: tuple[DecisionSpec, ...]
    identifiability: IdentifiabilityRule
    rate_checks: tuple[RateCheck, ...]
    structural_rules: StructuralRules
    ignored_fields: tuple[str, ...]
    unclassified_field_policy: str
    document: Mapping[str, Any]
    contract_version: int = 2

    def digest(self) -> str:
        return canonical_sha256(self.document)

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> ProtocolV2:
        _validate_v2(document)
        classes = document["field_classes"]
        rule = document["identifiability"]
        return cls(
            protocol_id=document["protocol_id"],
            version=document["version"],
            description=document["description"],
            tolerance_status=document["tolerance_status"],
            tolerance_note=document["tolerance_note"],
            levels={key: document["levels"][key] for key in V2_LEVEL_KEYS},
            a_fields=tuple(classes["A_discrete_identity"]),
            b_fields=tuple(
                FieldSpec(
                    path=entry["path"],
                    abs_tol=float(entry["abs_tol"]),
                    rel_tol=float(entry["rel_tol"]),
                    scope=entry.get("scope", "trial"),
                )
                for entry in classes["B_identifiable_numeric"]
            ),
            c_fields=tuple(
                DiagnosticField(
                    path=entry["path"],
                    semantics=entry.get("semantics", "magnitude_class"),
                    decades=int(entry.get("decades", 1)),
                    sign_sensitive=bool(entry.get("sign_sensitive", False)),
                )
                for entry in classes["C_unidentifiable_diagnostic"]
            ),
            decisions=tuple(_decision_from_document(entry) for entry in classes["D_decision"]),
            identifiability=IdentifiabilityRule(
                rule_id=rule["rule_id"],
                description=rule["description"],
                all_of=tuple(
                    IdentifiabilityCondition(
                        field=entry["field"],
                        check=entry["check"],
                        value=float(entry["value"]) if "value" in entry else None,
                    )
                    for entry in rule["all_of"]
                ),
            ),
            rate_checks=tuple(
                RateCheck(
                    path=entry["path"],
                    material_abs_change=float(entry["material_abs_change"]),
                    justification=entry["justification"],
                )
                for entry in document["rate_checks"]
            ),
            structural_rules=_structural_rules_from_document(document["structural_rules"]),
            ignored_fields=tuple(document["ignored_fields"]),
            unclassified_field_policy=document.get("unclassified_field_policy", "exact"),
            document=dict(document),
        )


def _decision_from_document(entry: Mapping[str, Any]) -> DecisionSpec:
    return DecisionSpec(
        name=entry["name"],
        path=entry["path"],
        kind=entry["kind"],
        justification=entry["justification"],
        statistic=entry.get("statistic"),
        comparison=entry.get("comparison"),
        threshold=float(entry["threshold"]) if "threshold" in entry else None,
        margin=float(entry["margin"]) if "margin" in entry else None,
        dependencies=tuple(entry.get("dependencies", ())),
    )


def _structural_rules_from_document(value: Mapping[str, Any]) -> StructuralRules:
    return StructuralRules(
        required_keys=tuple(value["required_keys"]),
        trials_key=value["trials_key"],
        conditions_key=value["conditions_key"],
        trial_key=tuple(value["trial_key"]),
        condition_key=value["condition_key"],
        required_trial_keys=tuple(value["required_trial_keys"]),
        same_condition_set=bool(value["same_condition_set"]),
        same_condition_order=bool(value["same_condition_order"]),
        exactly_once=bool(value["exactly_once"]),
        no_duplicates=bool(value["no_duplicates"]),
        no_missing=bool(value["no_missing"]),
        no_extra=bool(value["no_extra"]),
    )


def _validate_v2(document: Mapping[str, Any]) -> None:
    if not isinstance(document, Mapping):
        raise ProtocolError("protocol must be an object")
    keys = set(document)
    missing = sorted(V2_KEYS - keys)
    if missing:
        raise ProtocolError(f"protocol missing keys: {', '.join(missing)}")
    unknown = sorted(keys - V2_KEYS - {"unclassified_field_policy"})
    if unknown:
        raise ProtocolError(f"protocol has unknown keys: {', '.join(unknown)}")
    if document["contract_version"] != 2:
        raise ProtocolError("contract_version must be 2 for a contract-v2 protocol")
    _require_string(document["protocol_id"], "protocol_id")
    _require_string(document["description"], "description")
    if not _is_int(document["version"]) or document["version"] < 1:
        raise ProtocolError("version must be an integer >= 1")
    if document["tolerance_status"] not in V2_PERMITTED_TOLERANCE_STATUSES:
        raise ProtocolError(
            f"tolerance_status must be one of {sorted(V2_PERMITTED_TOLERANCE_STATUSES)}"
        )
    _require_string(document["tolerance_note"], "tolerance_note")

    levels = document["levels"]
    if not isinstance(levels, Mapping) or set(levels) != set(V2_LEVEL_KEYS):
        raise ProtocolError(f"levels must contain exactly {', '.join(V2_LEVEL_KEYS)}")
    for key in V2_LEVEL_KEYS:
        _require_string(levels[key], f"levels.{key}")

    classes = document["field_classes"]
    if not isinstance(classes, Mapping) or set(classes) != set(CLASS_KEYS):
        raise ProtocolError(f"field_classes must contain exactly {', '.join(CLASS_KEYS)}")
    _require_path_list(classes["A_discrete_identity"], "field_classes.A_discrete_identity")
    _validate_b_fields(classes["B_identifiable_numeric"])
    _validate_c_fields(classes["C_unidentifiable_diagnostic"])
    _validate_decisions(classes["D_decision"])
    _validate_identifiability(document["identifiability"])
    _validate_rate_checks(document["rate_checks"])
    _require_structural_rules(document["structural_rules"])
    _require_path_list(document["ignored_fields"], "ignored_fields")
    policy = document.get("unclassified_field_policy", "exact")
    if policy not in UNCLASSIFIED_POLICIES:
        raise ProtocolError(
            f"unclassified_field_policy must be one of {sorted(UNCLASSIFIED_POLICIES)}"
        )


def _validate_b_fields(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise ProtocolError("field_classes.B_identifiable_numeric must be a non-empty list")
    seen: set[str] = set()
    for index, entry in enumerate(value):
        if not isinstance(entry, Mapping):
            raise ProtocolError(f"B_identifiable_numeric[{index}] must be an object")
        missing = {"path", "abs_tol", "rel_tol"} - set(entry)
        if missing:
            raise ProtocolError(
                f"B_identifiable_numeric[{index}] missing keys: {', '.join(sorted(missing))}"
            )
        unknown = set(entry) - {"path", "abs_tol", "rel_tol", "scope"}
        if unknown:
            raise ProtocolError(
                f"B_identifiable_numeric[{index}] has unknown keys: {', '.join(sorted(unknown))}"
            )
        _require_path(entry["path"], f"B_identifiable_numeric[{index}].path")
        if entry["path"] in seen:
            raise ProtocolError(f"duplicate B path {entry['path']!r}")
        seen.add(entry["path"])
        if not entry["path"].startswith("trials[].") and not entry["path"].startswith(
            "conditions[]."
        ):
            raise ProtocolError(
                f"B_identifiable_numeric[{index}].path must start with trials[]. or conditions[]."
            )
        if entry.get("scope", "trial") not in {"trial", "condition"}:
            raise ProtocolError(
                f"B_identifiable_numeric[{index}].scope must be trial or condition"
            )
        for key in ("abs_tol", "rel_tol"):
            tolerance = entry[key]
            if (
                not isinstance(tolerance, (int, float))
                or isinstance(tolerance, bool)
                or not math.isfinite(float(tolerance))
                or float(tolerance) < 0.0
            ):
                raise ProtocolError(
                    f"B_identifiable_numeric[{index}].{key} must be a finite number >= 0"
                )


def _validate_c_fields(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise ProtocolError("field_classes.C_unidentifiable_diagnostic must be a non-empty list")
    for index, entry in enumerate(value):
        if not isinstance(entry, Mapping):
            raise ProtocolError(f"C_unidentifiable_diagnostic[{index}] must be an object")
        if "path" not in entry or "semantics" not in entry:
            raise ProtocolError(
                f"C_unidentifiable_diagnostic[{index}] requires path and semantics"
            )
        unknown = set(entry) - {"path", "semantics", "decades", "sign_sensitive"}
        if unknown:
            raise ProtocolError(
                f"C_unidentifiable_diagnostic[{index}] has unknown keys: {', '.join(sorted(unknown))}"
            )
        _require_path(entry["path"], f"C_unidentifiable_diagnostic[{index}].path")
        if entry["semantics"] not in DIAGNOSTIC_SEMANTICS:
            raise ProtocolError(
                f"C_unidentifiable_diagnostic[{index}].semantics must be one of "
                f"{sorted(DIAGNOSTIC_SEMANTICS)}"
            )
        decades = entry.get("decades", 1)
        if not _is_int(decades) or decades < 0:
            raise ProtocolError(f"C_unidentifiable_diagnostic[{index}].decades must be int >= 0")
        if "sign_sensitive" in entry and not isinstance(entry["sign_sensitive"], bool):
            raise ProtocolError(
                f"C_unidentifiable_diagnostic[{index}].sign_sensitive must be boolean"
            )


def _validate_decisions(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise ProtocolError("field_classes.D_decision must be a non-empty list")
    seen: set[str] = set()
    for index, entry in enumerate(value):
        if not isinstance(entry, Mapping):
            raise ProtocolError(f"D_decision[{index}] must be an object")
        for key in ("name", "path", "kind", "justification"):
            if key not in entry:
                raise ProtocolError(f"D_decision[{index}] missing {key!r}")
        _require_string(entry["name"], f"D_decision[{index}].name")
        _require_path(entry["path"], f"D_decision[{index}].path")
        if not entry["path"].startswith("trials[]."):
            raise ProtocolError(f"D_decision[{index}].path must start with trials[].")
        _require_string(entry["justification"], f"D_decision[{index}].justification")
        if entry["name"] in seen:
            raise ProtocolError(f"duplicate decision name {entry['name']!r}")
        kind = entry["kind"]
        if kind == "threshold":
            allowed = {"name", "path", "kind", "justification", "statistic", "comparison", "threshold", "margin"}
            missing = allowed - set(entry)
            if missing:
                raise ProtocolError(
                    f"D_decision[{index}] threshold decision missing: {', '.join(sorted(missing))}"
                )
            if set(entry) - allowed:
                raise ProtocolError(f"D_decision[{index}] has unknown keys")
            if not isinstance(entry["statistic"], str) or not entry["statistic"].startswith(
                "trials[]."
            ):
                raise ProtocolError(f"D_decision[{index}].statistic must start with trials[].")
            if entry["comparison"] not in DECISION_COMPARISONS:
                raise ProtocolError(
                    f"D_decision[{index}].comparison must be one of "
                    f"{sorted(DECISION_COMPARISONS)}"
                )
            for key in ("threshold", "margin"):
                value = entry[key]
                if (
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not math.isfinite(float(value))
                    or float(value) < 0.0
                ):
                    raise ProtocolError(
                        f"D_decision[{index}].{key} must be a finite number >= 0"
                    )
        elif kind == "derived":
            allowed = {
                "name",
                "path",
                "kind",
                "justification",
                "dependencies",
                "statistic",
                "comparison",
                "threshold",
                "margin",
            }
            if set(entry) - allowed:
                raise ProtocolError(f"D_decision[{index}] has unknown keys")
            dependencies = entry.get("dependencies")
            if not isinstance(dependencies, list) or not dependencies:
                raise ProtocolError(f"D_decision[{index}].dependencies must be non-empty")
            if any(not isinstance(item, str) for item in dependencies):
                raise ProtocolError(f"D_decision[{index}].dependencies must be names")
            for dependency in dependencies:
                if dependency not in seen:
                    raise ProtocolError(
                        f"D_decision[{index}] depends on undeclared or later decision {dependency!r}"
                    )
            threshold_keys = {"statistic", "comparison", "threshold", "margin"}
            present = threshold_keys & set(entry)
            if present and present != threshold_keys:
                raise ProtocolError(
                    f"D_decision[{index}] threshold fields must all be present together"
                )
            if present:
                if not isinstance(entry["statistic"], str) or not entry["statistic"].startswith(
                    "trials[]."
                ):
                    raise ProtocolError(f"D_decision[{index}].statistic must start with trials[].")
                if entry["comparison"] not in DECISION_COMPARISONS:
                    raise ProtocolError(
                        f"D_decision[{index}].comparison must be one of "
                        f"{sorted(DECISION_COMPARISONS)}"
                    )
                for key in ("threshold", "margin"):
                    value = entry[key]
                    if (
                        not isinstance(value, (int, float))
                        or isinstance(value, bool)
                        or not math.isfinite(float(value))
                        or float(value) < 0.0
                    ):
                        raise ProtocolError(
                            f"D_decision[{index}].{key} must be a finite number >= 0"
                        )
        elif kind == "exact":
            if set(entry) != {"name", "path", "kind", "justification"}:
                raise ProtocolError(f"D_decision[{index}] exact decision has unknown keys")
        else:
            raise ProtocolError(f"D_decision[{index}].kind must be threshold, derived, or exact")
        seen.add(entry["name"])


def _validate_identifiability(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise ProtocolError("identifiability must be an object")
    if set(value) != {"rule_id", "description", "all_of"}:
        raise ProtocolError(
            "identifiability must contain exactly rule_id, description, all_of"
        )
    _require_string(value["rule_id"], "identifiability.rule_id")
    _require_string(value["description"], "identifiability.description")
    clauses = value["all_of"]
    if not isinstance(clauses, list) or not clauses:
        raise ProtocolError("identifiability.all_of must be a non-empty list")
    for index, clause in enumerate(clauses):
        if not isinstance(clause, Mapping):
            raise ProtocolError(f"identifiability.all_of[{index}] must be an object")
        if "field" not in clause or "check" not in clause:
            raise ProtocolError(f"identifiability.all_of[{index}] requires field and check")
        unknown = set(clause) - {"field", "check", "value"}
        if unknown:
            raise ProtocolError(
                f"identifiability.all_of[{index}] has unknown keys: {', '.join(sorted(unknown))}"
            )
        _require_path(clause["field"], f"identifiability.all_of[{index}].field")
        if clause["check"] not in IDENTIFIABILITY_CHECKS:
            raise ProtocolError(
                f"identifiability.all_of[{index}].check must be one of "
                f"{sorted(IDENTIFIABILITY_CHECKS)}"
            )
        if clause["check"] in {"lt", "le", "gt", "ge"}:
            if "value" not in clause:
                raise ProtocolError(
                    f"identifiability.all_of[{index}] requires value for check "
                    f"{clause['check']!r}"
                )
            number = clause["value"]
            if (
                not isinstance(number, (int, float))
                or isinstance(number, bool)
                or not math.isfinite(float(number))
            ):
                raise ProtocolError(f"identifiability.all_of[{index}].value must be finite")


def _validate_rate_checks(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise ProtocolError("rate_checks must be a non-empty list")
    for index, entry in enumerate(value):
        if not isinstance(entry, Mapping):
            raise ProtocolError(f"rate_checks[{index}] must be an object")
        if set(entry) != {"path", "material_abs_change", "justification"}:
            raise ProtocolError(
                f"rate_checks[{index}] must contain path, material_abs_change, justification"
            )
        _require_path(entry["path"], f"rate_checks[{index}].path")
        if not entry["path"].startswith("conditions[].") and not entry["path"].startswith(
            "trials[]."
        ):
            raise ProtocolError(f"rate_checks[{index}].path must start with conditions[]. or trials[].")
        _require_string(entry["justification"], f"rate_checks[{index}].justification")
        material = entry["material_abs_change"]
        if (
            not isinstance(material, (int, float))
            or isinstance(material, bool)
            or not math.isfinite(float(material))
            or float(material) < 0.0
        ):
            raise ProtocolError(
                f"rate_checks[{index}].material_abs_change must be a finite number >= 0"
            )
