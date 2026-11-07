"""Data types for the PhainoWeave inferencer contract.

These dataclasses mirror the request, response, and candidate fields of
``docs/specs/inferencer-contract.md`` §3/§4. They are the supported Python shape of the
Rust/Python boundary recorded in ADR 0004; field names are normative and must not be
renamed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Any, Mapping

CONTRACT_VERSION = "1.0"
CONTRACT_MAJOR = 1


class Status(str, Enum):
    """Response status (inferencer contract §4)."""

    OK = "ok"
    ABSTAINED = "abstained"
    ERROR = "error"


class ScoreSemantics(str, Enum):
    """Declared score semantics (inferencer contract §4)."""

    LOG_LIKELIHOOD_RATIO = "log_likelihood_ratio"
    PROBABILITY = "probability"
    RANK_SCORE = "rank_score"


class Determinism(str, Enum):
    """Declared determinism mode (inferencer contract §6)."""

    DETERMINISTIC = "deterministic"
    NONDETERMINISTIC = "nondeterministic"
    UNKNOWN = "unknown"


class AbstainReason(str, Enum):
    """Abstention reasons (inferencer contract §4/§6)."""

    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    OUT_OF_DISTRIBUTION = "out_of_distribution"
    UNSUPPORTED_MODALITY = "unsupported_modality"
    BUDGET_EXHAUSTED = "budget_exhausted"


class ErrorCode(str, Enum):
    """Documented error codes (inferencer contract §5)."""

    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED_MEDIA = "unsupported_media"
    LICENSE_VIOLATION = "license_violation"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    TIMEOUT = "timeout"
    NUMERIC_FAILURE = "numeric_failure"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    CANCELLED = "cancelled"
    INTERNAL_ERROR = "internal_error"


class MediaKind(str, Enum):
    """Closed media-kind set (inferencer contract §1, world ontology §6)."""

    AUDIO = "audio"
    IMAGE = "image"
    VIDEO = "video"
    SENSOR = "sensor"
    DOCUMENT = "document"


class AccessLevel(str, Enum):
    """License access level (world ontology §5)."""

    PUBLIC = "public"
    RESEARCH = "research"
    RESTRICTED = "restricted"


class RegionKind(str, Enum):
    """Spatial region representation (world ontology §5); there is no point kind."""

    BBOX = "bbox"
    H3_CELLS = "h3_cells"
    POLYGON = "polygon"


class ConstraintKind(str, Enum):
    """Constraint families (world ontology §6)."""

    KINEMATIC = "kinematic"
    ACOUSTIC_PROPAGATION = "acoustic_propagation"
    SOLAR_EPHEMERIS = "solar_ephemeris"
    GEOMETRIC = "geometric"
    METEOROLOGICAL = "meteorological"
    ECOLOGICAL = "ecological"


@dataclass(frozen=True)
class SpatialRegion:
    """A region-level location value object `{kind, payload}`."""

    kind: RegionKind
    payload: Mapping[str, Any]

    @classmethod
    def bbox(
        cls, min_lon: float, min_lat: float, max_lon: float, max_lat: float
    ) -> SpatialRegion:
        return cls(
            RegionKind.BBOX,
            {"min_lon": min_lon, "min_lat": min_lat, "max_lon": max_lon, "max_lat": max_lat},
        )

    @classmethod
    def h3_cells(cls, resolution: int, cells: list[str] | tuple[str, ...]) -> SpatialRegion:
        return cls(RegionKind.H3_CELLS, {"resolution": resolution, "cells": list(cells)})

    @classmethod
    def polygon(cls, geojson: Mapping[str, Any]) -> SpatialRegion:
        return cls(RegionKind.POLYGON, {"geojson": dict(geojson)})


@dataclass(frozen=True)
class TimeWindow:
    """A half-open `[start, end)` window with an inner confidence."""

    start: str
    end: str
    inner_confidence: float


@dataclass(frozen=True)
class License:
    """Source license value object."""

    spdx: str
    terms_url: str
    access_level: AccessLevel


@dataclass(frozen=True)
class Uncertainty:
    """Uncertainty value object."""

    method: str
    params: Mapping[str, Any]
    calibration_ref: str | None = None


@dataclass(frozen=True)
class Claim:
    """A candidate world state claim."""

    location: SpatialRegion
    time: TimeWindow
    state: Mapping[str, Any]


@dataclass(frozen=True)
class Score:
    """A candidate score with its declared semantics."""

    value: float
    semantics: ScoreSemantics


@dataclass(frozen=True)
class ConstraintResidual:
    """A provisional residual predicted by the plugin (not a verdict)."""

    constraint_id: str
    value: float
    unit: str
    n_observations: int
    note: str | None = None


@dataclass(frozen=True)
class Explanation:
    """Short human-readable justification; never evidence."""

    text: str
    feature_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Candidate:
    """One candidate world state from a response."""

    candidate_id: str
    claim: Claim
    score: Score
    independence_key: str | None
    supporting_evidence_ids: list[str]
    conflict_evidence_ids: list[str]
    constraint_residuals: list[ConstraintResidual]
    explanation: Explanation


@dataclass(frozen=True)
class InferencerRef:
    """Inferencer identity `{name, version}`."""

    name: str
    version: str


@dataclass(frozen=True)
class HypothesisQuery:
    """Query bounds for a request."""

    region: SpatialRegion | None
    time: TimeWindow | None
    state_filter: Mapping[str, Any]
    hypothesis_ids: list[str]
    max_hypotheses: int


@dataclass(frozen=True)
class ObservationRef:
    """Observation reference passed to a plugin."""

    id: str
    content_hash: str
    media_kind: MediaKind
    media_path: str
    license_snapshot: License


@dataclass(frozen=True)
class FeatureRef:
    """Already extracted feature reference."""

    id: str
    observation_ids: list[str]
    feature_kind: str
    value: Any
    unit: str
    uncertainty: Uncertainty


@dataclass(frozen=True)
class ConstraintRef:
    """Constraint premise reference."""

    id: str
    constraint_kind: ConstraintKind
    version: str
    expression: str
    parameters: Mapping[str, Any]
    residual_function: str
    tolerance: float


@dataclass(frozen=True)
class DataSnapshotRef:
    """External data snapshot reference."""

    id: str
    uri: str
    version: str
    checksum: str
    access_path: str | None = None


@dataclass(frozen=True)
class Budget:
    """Run resource budget."""

    wall_ms: int
    cpu_ms: int
    peak_mem_mb: int
    max_candidates: int
    max_output_bytes: int


@dataclass(frozen=True)
class InferRequest:
    """One inferencer request document (inferencer contract §3)."""

    contract_version: str
    run_id: str
    ontology_version: str
    inferencer: InferencerRef
    hypothesis_query: HypothesisQuery
    observation_refs: list[ObservationRef]
    feature_refs: list[FeatureRef]
    constraint_refs: list[ConstraintRef]
    data_snapshot_refs: list[DataSnapshotRef]
    evidence_scope: list[str]
    parameters: Mapping[str, Any]
    seed: int
    budget: Budget
    scratch_dir: str


@dataclass(frozen=True)
class ReferencedDataVersion:
    """A snapshot actually read by the plugin."""

    id: str
    version: str
    checksum: str


@dataclass(frozen=True)
class Timings:
    """Informational timings, excluded from determinism comparison."""

    wall_ms: int
    cpu_ms: int


@dataclass(frozen=True)
class ContractError:
    """Typed error object for `status = error` responses."""

    code: ErrorCode
    message: str
    retryable: bool
    detail: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class Result:
    """One inferencer response document (inferencer contract §4)."""

    contract_version: str
    inferencer: InferencerRef
    status: Status
    complete: bool
    candidates: list[Candidate]
    residuals: list[ConstraintResidual]
    referenced_data_versions: list[ReferencedDataVersion]
    determinism: Determinism
    diagnostics: list[str]
    timings: Timings
    error: ContractError | None = None
    abstain_reason: AbstainReason | None = None


def to_document(value: Any) -> Any:
    """Converts contract dataclasses and enums into JSON-native documents."""
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        document: dict[str, Any] = {}
        for schema_field in fields(value):
            field_value = getattr(value, schema_field.name)
            if field_value is None:
                continue
            document[schema_field.name] = to_document(field_value)
        return document
    if isinstance(value, Mapping):
        return {str(key): to_document(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_document(item) for item in value]
    return value


class Inferencer(ABC):
    """Abstract Python plugin shape (inferencer contract §11)."""

    name: str
    version: str
    contract_version: str = CONTRACT_VERSION
    score_semantics: ScoreSemantics = ScoreSemantics.LOG_LIKELIHOOD_RATIO
    determinism: Determinism = Determinism.UNKNOWN

    @abstractmethod
    def run(self, req: dict[str, Any]) -> Result:
        """Runs inference for one request document and returns a response document."""
        raise NotImplementedError
