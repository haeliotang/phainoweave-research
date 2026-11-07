"""Validation of inferencer request and response documents.

Validation reports every violation instead of raising; the host refuses an invalid document
and records the findings. Rules follow ``docs/specs/inferencer-contract.md`` §1, §3, §4, §5.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

from .contract import (
    CONTRACT_MAJOR,
    AbstainReason,
    Determinism,
    ErrorCode,
    MediaKind,
    RegionKind,
    ScoreSemantics,
    Status,
)
from .manifest import Manifest

ID_PATTERN = re.compile(r"^(src|obs|ftr|ent|evt|con|hyp|run|ver)_[0-9a-f]{16}$")
INSTANT_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
H3_CELL_PATTERN = re.compile(r"^[0-9a-f]{15}$")
CONTRACT_VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)$")

REQUEST_REQUIRED = (
    "contract_version",
    "run_id",
    "ontology_version",
    "inferencer",
    "hypothesis_query",
    "observation_refs",
    "constraint_refs",
    "data_snapshot_refs",
    "evidence_scope",
    "parameters",
    "seed",
    "budget",
    "scratch_dir",
)
REQUEST_OPTIONAL = ("feature_refs",)
RESPONSE_REQUIRED = (
    "contract_version",
    "inferencer",
    "status",
    "complete",
    "candidates",
    "residuals",
    "referenced_data_versions",
    "determinism",
    "diagnostics",
    "timings",
)
CANDIDATE_REQUIRED = (
    "candidate_id",
    "claim",
    "score",
    "supporting_evidence_ids",
    "conflict_evidence_ids",
    "constraint_residuals",
    "explanation",
)
CANDIDATE_OPTIONAL = ("independence_key",)
CONSTRAINT_KINDS = frozenset(
    {
        "kinematic",
        "acoustic_propagation",
        "solar_ephemeris",
        "geometric",
        "meteorological",
        "ecological",
    }
)


@dataclass(frozen=True)
class Violation:
    """One contract violation with a JSON-path-like location."""

    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


def validate_request(doc: Mapping[str, Any], manifest: Manifest | None = None) -> list[Violation]:
    """Returns every request-contract violation; an empty list means valid."""
    problems: list[Violation] = []
    if not isinstance(doc, Mapping):
        return [Violation("$", "request must be a JSON object")]

    _check_object(doc, "$", REQUEST_REQUIRED, REQUEST_OPTIONAL, problems)
    _check_contract_version(doc.get("contract_version"), "$.contract_version", problems)
    _check_id(doc.get("run_id"), "$.run_id", problems, prefix="run")
    _check_string(doc.get("ontology_version"), "$.ontology_version", problems)

    inferencer = _check_object(
        doc.get("inferencer"), "$.inferencer", ("name", "version"), (), problems
    )
    if inferencer is not None:
        _check_string(inferencer.get("name"), "$.inferencer.name", problems)
        _check_string(inferencer.get("version"), "$.inferencer.version", problems)
        if manifest is not None:
            if inferencer.get("name") != manifest.name:
                problems.append(Violation("$.inferencer.name", "must equal the manifest name"))
            if inferencer.get("version") != manifest.version:
                problems.append(
                    Violation("$.inferencer.version", "must equal the manifest version")
                )

    query = _check_object(
        doc.get("hypothesis_query"),
        "$.hypothesis_query",
        ("region", "time", "state_filter", "hypothesis_ids", "max_hypotheses"),
        (),
        problems,
    )
    if query is not None:
        if query.get("region") is not None:
            _check_region(query.get("region"), "$.hypothesis_query.region", problems)
        if query.get("time") is not None:
            _check_time_window(query.get("time"), "$.hypothesis_query.time", problems)
        if not isinstance(query.get("state_filter"), Mapping):
            problems.append(
                Violation("$.hypothesis_query.state_filter", "must be an object")
            )
        _check_string_list(
            query.get("hypothesis_ids"), "$.hypothesis_query.hypothesis_ids", problems
        )
        _check_int(
            query.get("max_hypotheses"),
            "$.hypothesis_query.max_hypotheses",
            problems,
            minimum=1,
        )

    _check_list(doc.get("observation_refs"), "$.observation_refs", problems)
    for index, reference in enumerate(_as_list(doc.get("observation_refs"))):
        item = _check_object(
            reference,
            f"$.observation_refs[{index}]",
            ("id", "content_hash", "media_kind", "media_path", "license_snapshot"),
            (),
            problems,
        )
        if item is None:
            continue
        _check_id(item.get("id"), f"$.observation_refs[{index}].id", problems, prefix="obs")
        _check_string(
            item.get("content_hash"), f"$.observation_refs[{index}].content_hash", problems
        )
        _check_media_kind(
            item.get("media_kind"), f"$.observation_refs[{index}].media_kind", problems
        )
        _check_string(
            item.get("media_path"), f"$.observation_refs[{index}].media_path", problems
        )
        _check_license(
            item.get("license_snapshot"),
            f"$.observation_refs[{index}].license_snapshot",
            problems,
        )

    for index, reference in enumerate(_as_list(doc.get("feature_refs"))):
        path = f"$.feature_refs[{index}]"
        item = _check_object(
            reference,
            path,
            ("id", "observation_ids", "feature_kind", "value", "unit", "uncertainty"),
            (),
            problems,
        )
        if item is None:
            continue
        _check_id(item.get("id"), f"{path}.id", problems, prefix="ftr")
        _check_string_list(item.get("observation_ids"), f"{path}.observation_ids", problems)
        _check_string(item.get("feature_kind"), f"{path}.feature_kind", problems)
        _check_string(item.get("unit"), f"{path}.unit", problems)
        _check_uncertainty(item.get("uncertainty"), f"{path}.uncertainty", problems)

    _check_list(doc.get("constraint_refs"), "$.constraint_refs", problems)
    for index, reference in enumerate(_as_list(doc.get("constraint_refs"))):
        path = f"$.constraint_refs[{index}]"
        item = _check_object(
            reference,
            path,
            (
                "id",
                "constraint_kind",
                "version",
                "expression",
                "parameters",
                "residual_function",
                "tolerance",
            ),
            (),
            problems,
        )
        if item is None:
            continue
        _check_id(item.get("id"), f"{path}.id", problems, prefix="con")
        if item.get("constraint_kind") not in CONSTRAINT_KINDS:
            problems.append(
                Violation(f"{path}.constraint_kind", "must be a contract constraint kind")
            )
        _check_string(item.get("version"), f"{path}.version", problems)
        _check_string(item.get("expression"), f"{path}.expression", problems)
        if not isinstance(item.get("parameters"), Mapping):
            problems.append(Violation(f"{path}.parameters", "must be an object"))
        _check_string(
            item.get("residual_function"), f"{path}.residual_function", problems
        )
        _check_number(
            item.get("tolerance"), f"{path}.tolerance", problems, minimum=0.0
        )

    _check_list(doc.get("data_snapshot_refs"), "$.data_snapshot_refs", problems)
    for index, reference in enumerate(_as_list(doc.get("data_snapshot_refs"))):
        path = f"$.data_snapshot_refs[{index}]"
        item = _check_object(
            reference, path, ("id", "uri", "version", "checksum"), ("access_path",), problems
        )
        if item is None:
            continue
        _check_string(item.get("id"), f"{path}.id", problems)
        _check_string(item.get("uri"), f"{path}.uri", problems)
        _check_string(item.get("version"), f"{path}.version", problems)
        _check_string(item.get("checksum"), f"{path}.checksum", problems)
        if item.get("access_path") is not None:
            _check_string(item.get("access_path"), f"{path}.access_path", problems)

    _check_id_list(doc.get("evidence_scope"), "$.evidence_scope", problems)
    if not isinstance(doc.get("parameters"), Mapping):
        problems.append(Violation("$.parameters", "must be an object"))
    _check_int(doc.get("seed"), "$.seed", problems)

    budget = _check_object(
        doc.get("budget"),
        "$.budget",
        ("wall_ms", "cpu_ms", "peak_mem_mb", "max_candidates", "max_output_bytes"),
        (),
        problems,
    )
    if budget is not None:
        for key in (
            "wall_ms",
            "cpu_ms",
            "peak_mem_mb",
            "max_candidates",
            "max_output_bytes",
        ):
            _check_int(budget.get(key), f"$.budget.{key}", problems, minimum=1)
    _check_string(doc.get("scratch_dir"), "$.scratch_dir", problems)
    return problems


def validate_response(
    doc: Mapping[str, Any],
    manifest: Manifest,
    request: Mapping[str, Any],
) -> list[Violation]:
    """Returns every response-contract violation; an empty list means valid."""
    problems: list[Violation] = []
    if not isinstance(doc, Mapping):
        return [Violation("$", "response must be a JSON object")]

    _check_object(doc, "$", RESPONSE_REQUIRED, ("error", "abstain_reason"), problems)
    _check_contract_version(doc.get("contract_version"), "$.contract_version", problems)
    if doc.get("contract_version") != request.get("contract_version"):
        problems.append(
            Violation("$.contract_version", "must echo the request contract_version")
        )

    inferencer = _check_object(
        doc.get("inferencer"), "$.inferencer", ("name", "version"), (), problems
    )
    if inferencer is not None:
        _check_string(inferencer.get("name"), "$.inferencer.name", problems)
        _check_string(inferencer.get("version"), "$.inferencer.version", problems)
        if inferencer.get("name") != manifest.name:
            problems.append(Violation("$.inferencer.name", "must equal the manifest name"))
        if inferencer.get("version") != manifest.version:
            problems.append(
                Violation("$.inferencer.version", "must equal the manifest version")
            )

    status = doc.get("status")
    valid_status = {member.value for member in Status}
    if not isinstance(status, str) or status not in valid_status:
        problems.append(Violation("$.status", "must be a contract status enum value"))
        status = None
    if not isinstance(doc.get("complete"), bool):
        problems.append(Violation("$.complete", "must be a boolean"))

    candidates = doc.get("candidates")
    _check_list(candidates, "$.candidates", problems)
    candidate_values = _as_list(candidates)
    for index, candidate in enumerate(candidate_values):
        _check_candidate(candidate, f"$.candidates[{index}]", manifest, request, problems)

    _check_list(doc.get("residuals"), "$.residuals", problems)
    for index, residual in enumerate(_as_list(doc.get("residuals"))):
        _check_residual(residual, f"$.residuals[{index}]", request, problems)

    _check_list(doc.get("referenced_data_versions"), "$.referenced_data_versions", problems)
    for index, reference in enumerate(_as_list(doc.get("referenced_data_versions"))):
        path = f"$.referenced_data_versions[{index}]"
        item = _check_object(reference, path, ("id", "version", "checksum"), (), problems)
        if item is None:
            continue
        _check_string(item.get("id"), f"{path}.id", problems)
        _check_string(item.get("version"), f"{path}.version", problems)
        _check_string(item.get("checksum"), f"{path}.checksum", problems)

    determinism = doc.get("determinism")
    if not isinstance(determinism, str) or determinism not in {
        member.value for member in Determinism
    }:
        problems.append(Violation("$.determinism", "must be a contract determinism value"))
    elif determinism != manifest.determinism.value:
        problems.append(
            Violation("$.determinism", "must equal the manifest determinism declaration")
        )

    diagnostics = doc.get("diagnostics")
    if not isinstance(diagnostics, list) or any(
        not isinstance(item, str) for item in diagnostics
    ):
        problems.append(Violation("$.diagnostics", "must be a list of strings"))

    timings = _check_object(
        doc.get("timings"), "$.timings", ("wall_ms", "cpu_ms"), (), problems
    )
    if timings is not None:
        _check_int(timings.get("wall_ms"), "$.timings.wall_ms", problems, minimum=0)
        _check_int(timings.get("cpu_ms"), "$.timings.cpu_ms", problems, minimum=0)

    error = doc.get("error")
    if status == Status.ERROR.value:
        _check_error(error, "$.error", problems)
    elif error is not None:
        problems.append(Violation("$.error", "is only allowed when status is error"))

    abstain_reason = doc.get("abstain_reason")
    valid_abstain_reasons = {member.value for member in AbstainReason}
    if status == Status.ABSTAINED.value:
        if not isinstance(abstain_reason, str) or abstain_reason not in valid_abstain_reasons:
            problems.append(
                Violation(
                    "$.abstain_reason",
                    "is required for status abstained and must be a contract enum value",
                )
            )
        if candidate_values:
            problems.append(Violation("$.candidates", "abstained response must be empty"))
        if doc.get("complete") is not True:
            problems.append(Violation("$.complete", "abstained response must be complete"))
    elif abstain_reason is not None:
        problems.append(
            Violation("$.abstain_reason", "must be absent unless status is abstained")
        )

    if status == Status.OK.value and not candidate_values:
        problems.append(
            Violation("$.candidates", "status ok requires at least one candidate")
        )
    elif status == Status.ERROR.value and candidate_values:
        problems.append(Violation("$.candidates", "error response must not carry candidates"))
    return problems


def _check_candidate(
    candidate: Any,
    path: str,
    manifest: Manifest,
    request: Mapping[str, Any],
    problems: list[Violation],
) -> None:
    item = _check_object(candidate, path, CANDIDATE_REQUIRED, CANDIDATE_OPTIONAL, problems)
    if item is None:
        return
    _check_string(item.get("candidate_id"), f"{path}.candidate_id", problems)

    claim = _check_object(item.get("claim"), f"{path}.claim", ("location", "time", "state"), (), problems)
    if claim is not None:
        _check_region(claim.get("location"), f"{path}.claim.location", problems)
        _check_time_window(claim.get("time"), f"{path}.claim.time", problems)
        if not isinstance(claim.get("state"), Mapping):
            problems.append(Violation(f"{path}.claim.state", "must be an object"))

    score = _check_object(item.get("score"), f"{path}.score", ("value", "semantics"), (), problems)
    if score is not None:
        _check_score(score, f"{path}.score", manifest, problems)

    independence_key = item.get("independence_key")
    if independence_key is not None:
        _check_string(independence_key, f"{path}.independence_key", problems)

    evidence_scope = request.get("evidence_scope")
    scope = set(evidence_scope) if isinstance(evidence_scope, list) else set()
    for field_name in ("supporting_evidence_ids", "conflict_evidence_ids"):
        _check_id_list(item.get(field_name), f"{path}.{field_name}", problems)
        for index, evidence_id in enumerate(_as_list(item.get(field_name))):
            if evidence_id not in scope:
                problems.append(
                    Violation(
                        f"{path}.{field_name}[{index}]",
                        "must be inside request.evidence_scope",
                    )
                )

    residuals = item.get("constraint_residuals")
    _check_list(residuals, f"{path}.constraint_residuals", problems)
    for index, residual in enumerate(_as_list(residuals)):
        _check_residual(
            residual, f"{path}.constraint_residuals[{index}]", request, problems
        )

    explanation = _check_object(
        item.get("explanation"), f"{path}.explanation", ("text", "feature_ids"), (), problems
    )
    if explanation is not None:
        _check_string(explanation.get("text"), f"{path}.explanation.text", problems)
        _check_string_list(
            explanation.get("feature_ids"), f"{path}.explanation.feature_ids", problems
        )


def _check_residual(
    residual: Any, path: str, request: Mapping[str, Any], problems: list[Violation]
) -> None:
    item = _check_object(
        residual,
        path,
        ("constraint_id", "value", "unit", "n_observations"),
        ("note",),
        problems,
    )
    if item is None:
        return
    _check_id(item.get("constraint_id"), f"{path}.constraint_id", problems, prefix="con")
    _check_number(item.get("value"), f"{path}.value", problems)
    _check_string(item.get("unit"), f"{path}.unit", problems)
    _check_int(item.get("n_observations"), f"{path}.n_observations", problems, minimum=0)
    if item.get("note") is not None:
        _check_string(item.get("note"), f"{path}.note", problems)

    constraint_ids = {
        ref.get("id")
        for ref in _as_list(request.get("constraint_refs"))
        if isinstance(ref, Mapping)
    }
    if item.get("constraint_id") not in constraint_ids:
        problems.append(
            Violation(f"{path}.constraint_id", "must be in request.constraint_refs")
        )


def _check_score(
    score: Mapping[str, Any], path: str, manifest: Manifest, problems: list[Violation]
) -> None:
    semantics = score.get("semantics")
    if not isinstance(semantics, str) or semantics not in {
        member.value for member in ScoreSemantics
    }:
        problems.append(Violation(f"{path}.semantics", "must be a contract score semantics"))
        return
    if semantics != manifest.score_semantics.value:
        problems.append(
            Violation(f"{path}.semantics", "must equal the manifest score_semantics")
        )
    value = score.get("value")
    _check_number(value, f"{path}.value", problems)
    if not _is_number(value):
        return
    numeric = float(value)
    if semantics == ScoreSemantics.LOG_LIKELIHOOD_RATIO.value:
        if abs(numeric) > 16.0:
            problems.append(Violation(f"{path}.value", "log-likelihood ratio must be within ±16"))
    elif semantics == ScoreSemantics.PROBABILITY.value:
        if not 0.0 < numeric < 1.0:
            problems.append(Violation(f"{path}.value", "probability must be within (0, 1)"))
    # rank_score is an arbitrary finite ordering value; no range constraint.


def _check_error(error: Any, path: str, problems: list[Violation]) -> None:
    item = _check_object(
        error, path, ("code", "message", "retryable"), ("detail",), problems
    )
    if item is None:
        return
    if not isinstance(item.get("code"), str) or item.get("code") not in {
        member.value for member in ErrorCode
    }:
        problems.append(Violation(f"{path}.code", "must be a contract error code"))
    message = item.get("message")
    _check_string(message, f"{path}.message", problems)
    if isinstance(message, str) and ("\n" in message or "\r" in message):
        problems.append(Violation(f"{path}.message", "must be a single line"))
    if not isinstance(item.get("retryable"), bool):
        problems.append(Violation(f"{path}.retryable", "must be a boolean"))
    if item.get("detail") is not None and not isinstance(item.get("detail"), Mapping):
        problems.append(Violation(f"{path}.detail", "must be an object"))


def _check_region(region: Any, path: str, problems: list[Violation]) -> None:
    item = _check_object(region, path, ("kind", "payload"), (), problems)
    if item is None:
        return
    kind = item.get("kind")
    valid_kinds = {member.value for member in RegionKind}
    if not isinstance(kind, str) or kind not in valid_kinds:
        problems.append(
            Violation(f"{path}.kind", "must be bbox|h3_cells|polygon; a bare point is not a region")
        )
        return
    payload_value = item.get("payload")
    if not isinstance(payload_value, Mapping):
        problems.append(Violation(f"{path}.payload", "must be an object"))
        return
    payload = payload_value
    if kind == RegionKind.BBOX.value:
        _check_payload_keys(
            payload,
            f"{path}.payload",
            ("min_lon", "min_lat", "max_lon", "max_lat"),
            problems,
        )
        for key in ("min_lon", "min_lat", "max_lon", "max_lat"):
            _check_number(payload.get(key), f"{path}.payload.{key}", problems)
        if all(_is_number(payload.get(key)) for key in ("min_lon", "min_lat", "max_lon", "max_lat")):
            min_lon = float(payload["min_lon"])
            min_lat = float(payload["min_lat"])
            max_lon = float(payload["max_lon"])
            max_lat = float(payload["max_lat"])
            if not -180.0 <= min_lon < max_lon <= 180.0:
                problems.append(
                    Violation(f"{path}.payload", "longitude bounds must satisfy -180 <= min < max <= 180")
                )
            if not -90.0 <= min_lat < max_lat <= 90.0:
                problems.append(
                    Violation(f"{path}.payload", "latitude bounds must satisfy -90 <= min < max <= 90")
                )
    elif kind == RegionKind.H3_CELLS.value:
        _check_payload_keys(payload, f"{path}.payload", ("resolution", "cells"), problems)
        _check_int(payload.get("resolution"), f"{path}.payload.resolution", problems, minimum=0)
        if _is_int(payload.get("resolution")) and not 0 <= int(payload["resolution"]) <= 15:
            problems.append(Violation(f"{path}.payload.resolution", "must be within 0..=15"))
        cells = payload.get("cells")
        if not isinstance(cells, list) or not cells:
            problems.append(Violation(f"{path}.payload.cells", "must be a non-empty list"))
        else:
            for index, cell in enumerate(cells):
                if not isinstance(cell, str) or not H3_CELL_PATTERN.fullmatch(cell):
                    problems.append(
                        Violation(
                            f"{path}.payload.cells[{index}]",
                            "must be 15 lowercase hexadecimal characters",
                        )
                    )
    else:
        _check_payload_keys(payload, f"{path}.payload", ("geojson",), problems)
        geojson = payload.get("geojson")
        if not isinstance(geojson, Mapping):
            problems.append(Violation(f"{path}.payload.geojson", "must be an object"))
        else:
            if geojson.get("type") not in {"Polygon", "MultiPolygon"}:
                problems.append(
                    Violation(f"{path}.payload.geojson.type", "must be Polygon or MultiPolygon")
                )
            coordinates = geojson.get("coordinates")
            if not isinstance(coordinates, list) or not coordinates:
                problems.append(
                    Violation(f"{path}.payload.geojson.coordinates", "must be non-empty")
                )


def _check_payload_keys(
    payload: Mapping[str, Any],
    path: str,
    required: Sequence[str],
    problems: list[Violation],
) -> None:
    _check_object(payload, path, required, (), problems)


def _check_time_window(window: Any, path: str, problems: list[Violation]) -> None:
    item = _check_object(
        window, path, ("start", "end", "inner_confidence"), (), problems
    )
    if item is None:
        return
    start = _parse_instant(item.get("start"))
    end = _parse_instant(item.get("end"))
    if start is None:
        problems.append(Violation(f"{path}.start", "must be a microsecond UTC instant"))
    if end is None:
        problems.append(Violation(f"{path}.end", "must be a microsecond UTC instant"))
    if start is not None and end is not None and start >= end:
        problems.append(Violation(path, "start must be earlier than end"))
    confidence = item.get("inner_confidence")
    _check_number(confidence, f"{path}.inner_confidence", problems)
    if _is_number(confidence) and not 0.0 <= float(confidence) <= 1.0:
        problems.append(Violation(f"{path}.inner_confidence", "must be within [0, 1]"))


def _check_license(license_doc: Any, path: str, problems: list[Violation]) -> None:
    item = _check_object(
        license_doc, path, ("spdx", "terms_url", "access_level"), (), problems
    )
    if item is None:
        return
    _check_string(item.get("spdx"), f"{path}.spdx", problems)
    _check_string(item.get("terms_url"), f"{path}.terms_url", problems)
    if item.get("access_level") not in {"public", "research", "restricted"}:
        problems.append(Violation(f"{path}.access_level", "must be public|research|restricted"))


def _check_uncertainty(uncertainty_doc: Any, path: str, problems: list[Violation]) -> None:
    item = _check_object(
        uncertainty_doc,
        path,
        ("method", "params"),
        ("calibration_ref",),
        problems,
    )
    if item is None:
        return
    if item.get("method") not in {"interval", "distribution", "monte_carlo"}:
        problems.append(Violation(f"{path}.method", "must be a contract uncertainty method"))
    if not isinstance(item.get("params"), Mapping):
        problems.append(Violation(f"{path}.params", "must be an object"))
    if item.get("calibration_ref") is not None:
        _check_string(item.get("calibration_ref"), f"{path}.calibration_ref", problems)


def _check_media_kind(value: Any, path: str, problems: list[Violation]) -> None:
    if not isinstance(value, str) or value not in {member.value for member in MediaKind}:
        problems.append(Violation(path, "must be a contract media kind"))


def _check_contract_version(value: Any, path: str, problems: list[Violation]) -> None:
    if not isinstance(value, str):
        problems.append(Violation(path, "must be a MAJOR.MINOR string"))
        return
    match = CONTRACT_VERSION_PATTERN.fullmatch(value)
    if not match:
        problems.append(Violation(path, "must be a MAJOR.MINOR string"))
    elif int(match.group(1)) != CONTRACT_MAJOR:
        problems.append(Violation(path, f"major must be {CONTRACT_MAJOR}"))


def _check_object(
    value: Any,
    path: str,
    required: Sequence[str],
    optional: Sequence[str],
    problems: list[Violation],
) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        problems.append(Violation(path, "must be an object"))
        return None
    allowed = set(required) | set(optional)
    missing = [key for key in required if key not in value]
    if missing:
        problems.append(Violation(path, f"missing required keys: {', '.join(sorted(missing))}"))
    unknown = [key for key in value if key not in allowed]
    if unknown:
        problems.append(Violation(path, f"unknown keys: {', '.join(sorted(map(str, unknown)))}"))
    return value


def _check_list(value: Any, path: str, problems: list[Violation]) -> None:
    if not isinstance(value, list):
        problems.append(Violation(path, "must be a list"))


def _check_string(value: Any, path: str, problems: list[Violation]) -> None:
    if not isinstance(value, str) or not value:
        problems.append(Violation(path, "must be a non-empty string"))


def _check_string_list(value: Any, path: str, problems: list[Violation]) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        problems.append(Violation(path, "must be a list of strings"))


def _check_id_list(value: Any, path: str, problems: list[Violation]) -> None:
    if not isinstance(value, list):
        problems.append(Violation(path, "must be a list of ids"))
        return
    for index, item in enumerate(value):
        _check_id(item, f"{path}[{index}]", problems)


def _check_id(
    value: Any, path: str, problems: list[Violation], prefix: str | None = None
) -> None:
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        problems.append(Violation(path, "must be an ontology object id"))
        return
    if prefix is not None and not value.startswith(prefix + "_"):
        problems.append(Violation(path, f"must use the {prefix}_ prefix"))


def _check_int(
    value: Any, path: str, problems: list[Violation], minimum: int | None = None
) -> None:
    if not _is_int(value):
        problems.append(Violation(path, "must be an integer"))
        return
    if minimum is not None and int(value) < minimum:
        problems.append(Violation(path, f"must be >= {minimum}"))


def _check_number(
    value: Any, path: str, problems: list[Violation], minimum: float | None = None
) -> None:
    if not _is_number(value):
        problems.append(Violation(path, "must be a finite number"))
        return
    if minimum is not None and float(value) < minimum:
        problems.append(Violation(path, f"must be >= {minimum}"))


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and (not isinstance(value, float) or value == value)
    )


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _parse_instant(value: Any) -> datetime | None:
    if not isinstance(value, str) or not INSTANT_PATTERN.fullmatch(value):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


