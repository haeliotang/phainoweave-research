"""Strict validation of C2 repair artifacts.

The evaluator consumes JSON only and never imports acoustic-method code. It validates the
fixed C2 repair contract, rejects duplicate trials, missing truth, missing candidates,
non-finite numbers and cross-environment protocol/grid mismatches.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

EXPERIMENT = "c2-repair"
SCHEMA_VERSION = "1.0.0"
PRIMARY_ENDPOINT_KEYS = (
    "name",
    "definition",
    "candidate_comparison",
    "decision_rule",
    "detection_non_inferiority_rule",
)
UNDECIDED_POLICIES = frozenset({"not_detected", "excluded"})
POLICY_ALIASES = {
    "not_detected": "not_detected",
    "not-detected": "not_detected",
    "undetected": "not_detected",
    "undecided_not_detected": "not_detected",
    "excluded": "excluded",
    "exclude": "excluded",
    "exclude_undetermined": "excluded",
    "undetermined_as_not_detected": "not_detected",
    "drop_undetermined": "excluded",
}
CANDIDATE_IDS = ("B0", "B1", "B2", "B3")
ADEQUACY_STATUSES = frozenset(
    {"adequate", "discrepancy", "insufficient_evidence", "indeterminate"}
)
DECISIONS = frozenset({"accept", "reject", "undetermined"})
OBSERVATION_SOURCES = frozenset(
    {"front_end", "ideal", "independent_noise", "empirical_error"}
)
SCENARIO_KEYS = ("f0", "v", "t0", "b", "accel", "snr_db", "geometry_m")
CLAIM_KEYS = ("v", "f0_times_b", "t0")
TOP_LEVEL_KEYS = frozenset(
    {
        "experiment",
        "protocol_digest",
        "grid_id",
        "frozen_grid_digest",
        "candidates",
        "trials",
        "primary_endpoint",
        "detection_loss_bound",
        "undecided_policy",
    }
)
TRIAL_KEYS = frozenset(
    {
        "condition",
        "mechanism",
        "seed",
        "stratum",
        "evaluation_only",
        "observation",
        "candidates",
    }
)
CANDIDATE_KEYS = frozenset(
    {"adequacy_status", "reason_codes", "decision", "claim_statuses", "params"}
)


class ArtifactError(ValueError):
    """Raised when a C2 repair artifact violates the fixed contract."""


@dataclass(frozen=True)
class Bin:
    bin_id: str
    lower: float
    upper: float | None
    n_samples: int | None = None


@dataclass(frozen=True)
class CandidateRecord:
    adequacy_status: str
    reason_codes: tuple[str, ...]
    decision: str
    claim_statuses: Mapping[str, str]
    params: Mapping[str, float]
    validly_supported: bool | None = None


@dataclass(frozen=True)
class Trial:
    condition: str
    mechanism: str
    seed: int
    stratum: str
    scenario: Mapping[str, float]
    estimate_within_tolerance: Mapping[str, bool]
    observation_source: str
    observation_snr_db: float
    estimated_chirp_rate: float | None
    estimated_snr_db: float | None
    candidates: Mapping[str, CandidateRecord]

    @property
    def key(self) -> tuple[str, int]:
        return (self.condition, self.seed)

    @property
    def truth_correct(self) -> bool:
        return all(self.estimate_within_tolerance.values())

    @property
    def geometry_m(self) -> float:
        return self.scenario["geometry_m"]


@dataclass(frozen=True)
class Artifact:
    path: str
    experiment: str
    protocol_digest: str
    grid_id: str
    frozen_grid_digest: str
    candidates: tuple[str, ...]
    trials: tuple[Trial, ...]
    primary_endpoint: Mapping[str, Any]
    detection_loss_bound: float
    undecided_policy: str
    chirp_bins: tuple[Bin, ...] | None
    snr_bins: tuple[Bin, ...] | None
    sha256: str

    @property
    def trial_by_key(self) -> dict[tuple[str, int], Trial]:
        return {trial.key: trial for trial in self.trials}


def load_artifacts(
    paths: Sequence[str | Path], *, require_paired: bool = False
) -> list[Artifact]:
    """Loads one or more artifacts and enforces cross-environment digest consistency."""
    if not paths:
        raise ArtifactError("at least one --artifact path is required")
    artifacts = [load_artifact(path) for path in paths]
    _validate_cross_environment(artifacts, require_paired=require_paired)
    return artifacts


def load_artifact(path: str | Path) -> Artifact:
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as error:
        raise ArtifactError(f"cannot read artifact {source}: {error}") from error
    document = parse_strict_json(raw, source=str(source))
    if not isinstance(document, Mapping):
        raise ArtifactError(f"{source}: top-level artifact must be a JSON object")
    artifact = validate_artifact(document, source=str(source))
    return Artifact(
        path=str(source),
        experiment=artifact.experiment,
        protocol_digest=artifact.protocol_digest,
        grid_id=artifact.grid_id,
        frozen_grid_digest=artifact.frozen_grid_digest,
        candidates=artifact.candidates,
        trials=artifact.trials,
        primary_endpoint=artifact.primary_endpoint,
        detection_loss_bound=artifact.detection_loss_bound,
        undecided_policy=artifact.undecided_policy,
        chirp_bins=artifact.chirp_bins,
        snr_bins=artifact.snr_bins,
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def validate_artifact(document: Mapping[str, Any], source: str) -> Artifact:
    _require_keys(document, TOP_LEVEL_KEYS, "$", source)
    if document["experiment"] != EXPERIMENT:
        raise ArtifactError(
            f"{source}: experiment must be {EXPERIMENT!r}, got {document['experiment']!r}"
        )
    for field in ("protocol_digest", "grid_id", "frozen_grid_digest"):
        _require_string(document[field], f"$.{field}", source)

    candidates_raw = document["candidates"]
    if not isinstance(candidates_raw, list) or not candidates_raw:
        raise ArtifactError(f"{source}: candidates must be a non-empty list")
    candidates: list[str] = []
    for index, candidate in enumerate(candidates_raw):
        if not isinstance(candidate, str) or not candidate:
            raise ArtifactError(f"{source}: candidates[{index}] must be a non-empty string")
        if candidate in candidates:
            raise ArtifactError(f"{source}: duplicate candidate {candidate!r}")
        candidates.append(candidate)
    if "B0" not in candidates:
        raise ArtifactError(f"{source}: candidates must include the paired baseline B0")

    primary_endpoint, detection_loss_bound, undecided_policy = _validate_primary_endpoint(
        document, source, tuple(candidates)
    )
    chirp_bins = _validate_optional_bins(document.get("chirp_bins"), source, "chirp_bins")
    snr_bins = _validate_optional_bins(
        document.get("snr_bins"), source, "snr_bins", require_samples=True
    )

    trials_raw = document["trials"]
    if not isinstance(trials_raw, list) or not trials_raw:
        raise ArtifactError(f"{source}: trials must be a non-empty list")
    seen: set[tuple[str, int]] = set()
    trials: list[Trial] = []
    for index, trial_raw in enumerate(trials_raw):
        where = f"{source}: trials[{index}]"
        if not isinstance(trial_raw, Mapping):
            raise ArtifactError(f"{where} must be an object")
        trial = _validate_trial(trial_raw, tuple(candidates), where)
        if trial.key in seen:
            raise ArtifactError(
                f"{where}: duplicate trial identity condition={trial.condition!r} "
                f"seed={trial.seed}"
            )
        seen.add(trial.key)
        trials.append(trial)
    return Artifact(
        path=source,
        experiment=document["experiment"],
        protocol_digest=document["protocol_digest"],
        grid_id=document["grid_id"],
        frozen_grid_digest=document["frozen_grid_digest"],
        candidates=tuple(candidates),
        trials=tuple(trials),
        primary_endpoint=primary_endpoint,
        detection_loss_bound=detection_loss_bound,
        undecided_policy=undecided_policy,
        chirp_bins=chirp_bins,
        snr_bins=snr_bins,
        sha256="",
    )


def _validate_trial(
    trial: Mapping[str, Any], declared_candidates: tuple[str, ...], where: str
) -> Trial:
    _require_keys(trial, TRIAL_KEYS, "$", where)
    _require_string(trial["condition"], f"{where}.condition", where)
    _require_string(trial["mechanism"], f"{where}.mechanism", where)
    _require_string(trial["stratum"], f"{where}.stratum", where)
    if not _is_int(trial["seed"]):
        raise ArtifactError(f"{where}.seed must be an integer")

    evaluation = trial["evaluation_only"]
    if not isinstance(evaluation, Mapping):
        raise ArtifactError(f"{where}.evaluation_only must be an object")
    scenario = evaluation.get("scenario")
    if not isinstance(scenario, Mapping):
        raise ArtifactError(f"{where}.evaluation_only.scenario is missing truth")
    _require_keys(scenario, SCENARIO_KEYS, f"{where}.evaluation_only.scenario", where)
    for key in SCENARIO_KEYS:
        _require_finite_number(
            scenario[key], f"{where}.evaluation_only.scenario.{key}", where
        )
    for key in ("f0", "v", "b", "geometry_m"):
        if float(scenario[key]) <= 0.0:
            raise ArtifactError(
                f"{where}.evaluation_only.scenario.{key} must be positive truth"
            )
    if float(scenario["accel"]) < 0.0:
        raise ArtifactError(f"{where}.evaluation_only.scenario.accel must be non-negative")
    tolerance = evaluation.get("estimate_within_tolerance")
    if not isinstance(tolerance, Mapping) or not tolerance:
        raise ArtifactError(
            f"{where}.evaluation_only.estimate_within_tolerance must be a non-empty object"
        )
    normalized_tolerance: dict[str, bool] = {}
    for key, value in tolerance.items():
        if not isinstance(key, str) or not key or not isinstance(value, bool):
            raise ArtifactError(
                f"{where}.evaluation_only.estimate_within_tolerance must map strings to booleans"
            )
        normalized_tolerance[key] = value

    observation = trial["observation"]
    if not isinstance(observation, Mapping):
        raise ArtifactError(f"{where}.observation must be an object")
    source = observation.get("source")
    if source not in OBSERVATION_SOURCES:
        raise ArtifactError(
            f"{where}.observation.source must be one of {sorted(OBSERVATION_SOURCES)}"
        )
    _require_finite_number(observation.get("snr_db"), f"{where}.observation.snr_db", where)

    candidates_raw = trial["candidates"]
    if not isinstance(candidates_raw, Mapping):
        raise ArtifactError(f"{where}.candidates must be an object")
    missing = sorted(set(declared_candidates) - set(candidates_raw))
    extra = sorted(set(candidates_raw) - set(declared_candidates))
    if missing:
        raise ArtifactError(f"{where}: missing candidate records: {', '.join(missing)}")
    if extra:
        raise ArtifactError(f"{where}: undeclared candidate records: {', '.join(extra)}")
    candidate_records: dict[str, CandidateRecord] = {}
    for candidate in declared_candidates:
        candidate_records[candidate] = _validate_candidate(
            candidates_raw[candidate], f"{where}.candidates.{candidate}", where
        )
    return Trial(
        condition=trial["condition"],
        mechanism=trial["mechanism"],
        seed=trial["seed"],
        stratum=trial["stratum"],
        scenario={key: float(scenario[key]) for key in SCENARIO_KEYS},
        estimate_within_tolerance=normalized_tolerance,
        observation_source=source,
        observation_snr_db=float(observation["snr_db"]),
        estimated_chirp_rate=_optional_finite(trial.get("estimated_chirp_rate"), where, "estimated_chirp_rate"),
        estimated_snr_db=_optional_finite(trial.get("estimated_snr_db"), where, "estimated_snr_db"),
        candidates=candidate_records,
    )


def _validate_candidate(
    candidate: Any, path: str, label: str
) -> CandidateRecord:
    if not isinstance(candidate, Mapping):
        raise ArtifactError(f"{path} must be an object")
    _require_keys(candidate, CANDIDATE_KEYS, path, label)
    adequacy = candidate["adequacy_status"]
    if adequacy not in ADEQUACY_STATUSES:
        raise ArtifactError(
            f"{path}.adequacy_status must be one of {sorted(ADEQUACY_STATUSES)}"
        )
    reason_codes = candidate["reason_codes"]
    if not isinstance(reason_codes, list) or any(
        not isinstance(code, str) or not code for code in reason_codes
    ):
        raise ArtifactError(f"{path}.reason_codes must be a list of non-empty strings")
    decision = candidate["decision"]
    if decision not in DECISIONS:
        raise ArtifactError(f"{path}.decision must be one of {sorted(DECISIONS)}")
    claim_statuses = candidate["claim_statuses"]
    if not isinstance(claim_statuses, Mapping):
        raise ArtifactError(f"{path}.claim_statuses must be an object")
    missing_claims = sorted(set(CLAIM_KEYS) - set(claim_statuses))
    if missing_claims:
        raise ArtifactError(
            f"{path}.claim_statuses is missing claims: {', '.join(missing_claims)}"
        )
    normalized_claims: dict[str, str] = {}
    for claim, status in claim_statuses.items():
        if not isinstance(claim, str) or not claim:
            raise ArtifactError(f"{path}.claim_statuses keys must be strings")
        if not isinstance(status, str) or not status:
            raise ArtifactError(f"{path}.claim_statuses.{claim} must be a non-empty string")
        normalized_claims[claim] = status
    params = candidate["params"]
    if not isinstance(params, Mapping):
        raise ArtifactError(f"{path}.params must be an object")
    normalized_params: dict[str, float] = {}
    for key, value in params.items():
        if not isinstance(key, str) or not key:
            raise ArtifactError(f"{path}.params keys must be strings")
        _require_finite_number(value, f"{path}.params.{key}", path)
        normalized_params[key] = float(value)
    validly_supported = candidate.get("validly_supported")
    if validly_supported is not None and not isinstance(validly_supported, bool):
        raise ArtifactError(f"{path}.validly_supported must be a boolean when present")
    return CandidateRecord(
        adequacy_status=adequacy,
        reason_codes=tuple(reason_codes),
        decision=decision,
        claim_statuses=normalized_claims,
        params=normalized_params,
        validly_supported=validly_supported,
    )


def _validate_cross_environment(
    artifacts: Sequence[Artifact], *, require_paired: bool
) -> None:
    first = artifacts[0]
    for artifact in artifacts[1:]:
        if artifact.protocol_digest != first.protocol_digest:
            raise ArtifactError(
                "cross-environment protocol_digest mismatch: "
                f"{first.path}={first.protocol_digest!r} vs {artifact.path}={artifact.protocol_digest!r}"
            )
        if artifact.grid_id != first.grid_id:
            raise ArtifactError(
                "cross-environment grid_id mismatch: "
                f"{first.path}={first.grid_id!r} vs {artifact.path}={artifact.grid_id!r}"
            )
        if artifact.frozen_grid_digest != first.frozen_grid_digest:
            raise ArtifactError(
                "cross-environment frozen_grid_digest mismatch: "
                f"{first.path}={first.frozen_grid_digest!r} vs "
                f"{artifact.path}={artifact.frozen_grid_digest!r}"
            )
        if artifact.candidates != first.candidates:
            raise ArtifactError(
                "cross-environment candidate list mismatch: "
                f"{first.path}={first.candidates!r} vs {artifact.path}={artifact.candidates!r}"
            )
    if require_paired:
        first_keys = set(first.trial_by_key)
        for artifact in artifacts[1:]:
            keys = set(artifact.trial_by_key)
            missing = first_keys - keys
            extra = keys - first_keys
            if missing or extra:
                raise ArtifactError(
                    "require_paired: cross-environment trial sets differ for "
                    f"{artifact.path}: missing={len(missing)} extra={len(extra)}"
                )


def parse_strict_json(raw: bytes, source: str) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ArtifactError(f"{source}: not valid UTF-8") from error

    def reject_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ArtifactError(f"{source}: duplicate JSON object key {key!r}")
            result[key] = value
        return result

    def reject_constant(token: str) -> Any:
        raise ArtifactError(f"{source}: non-finite JSON number {token} is not allowed")

    try:
        return json.loads(
            text, object_pairs_hook=reject_duplicates, parse_constant=reject_constant
        )
    except json.JSONDecodeError as error:
        raise ArtifactError(f"{source}: malformed JSON: {error}") from error
    except ArtifactError:
        raise
    except ValueError as error:
        raise ArtifactError(f"{source}: malformed JSON: {error}") from error


def _require_keys(
    document: Mapping[str, Any], required: Iterable[str], path: str, label: str
) -> None:
    missing = [key for key in required if key not in document]
    if missing:
        raise ArtifactError(f"{label}: {path} is missing required keys: {', '.join(missing)}")


def _require_string(value: Any, path: str, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise ArtifactError(f"{label}: {path} must be a non-empty string")


def _require_finite_number(value: Any, path: str, label: str) -> None:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise ArtifactError(f"{label}: {path} must be a finite number")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_primary_endpoint(
    document: Mapping[str, Any], source: str, candidates: tuple[str, ...]
) -> tuple[Mapping[str, Any], float, str]:
    endpoint = document["primary_endpoint"]
    if not isinstance(endpoint, Mapping):
        raise ArtifactError(f"{source}: primary_endpoint must be an object")
    missing = [key for key in PRIMARY_ENDPOINT_KEYS if key not in endpoint]
    if missing:
        raise ArtifactError(
            f"{source}: primary_endpoint is missing fields: {', '.join(missing)}"
        )
    for key in PRIMARY_ENDPOINT_KEYS:
        if not isinstance(endpoint[key], str) or not endpoint[key]:
            raise ArtifactError(f"{source}: primary_endpoint.{key} must be a non-empty string")
    candidate_ids = _parse_primary_candidates(endpoint, candidates, source)
    bound = document["detection_loss_bound"]
    _require_finite_number(bound, "$.detection_loss_bound", source)
    if float(bound) < 0.0:
        raise ArtifactError(f"{source}: detection_loss_bound must be non-negative")
    policy_raw = document["undecided_policy"]
    if not isinstance(policy_raw, str) or not policy_raw:
        raise ArtifactError(f"{source}: undecided_policy must be a non-empty string")
    policy = POLICY_ALIASES.get(policy_raw.strip().lower())
    if policy is None:
        raise ArtifactError(
            f"{source}: undecided_policy {policy_raw!r} is not one of "
            f"{sorted(UNDECIDED_POLICIES)} (aliases: {sorted(POLICY_ALIASES)})"
        )
    normalized = dict(endpoint)
    normalized["_parsed_candidate_ids"] = candidate_ids
    normalized["_parsed_baseline"] = "B0"
    return normalized, float(bound), policy


def _parse_primary_candidates(
    endpoint: Mapping[str, Any], candidates: tuple[str, ...], source: str
) -> tuple[str, str]:
    explicit = endpoint.get("candidates")
    if isinstance(explicit, list) and explicit:
        ids = [value for value in explicit if isinstance(value, str)]
    else:
        comparator = endpoint.get("candidate") or endpoint.get("candidate_id")
        baseline = endpoint.get("baseline") or "B0"
        ids = [comparator, baseline] if isinstance(comparator, str) else []
    if not ids:
        import re

        ids = re.findall(r"B[0-9]+", str(endpoint["candidate_comparison"]))
    unique: list[str] = []
    for value in ids:
        if value not in unique:
            unique.append(value)
    if len(unique) < 2 or "B0" not in unique:
        raise ArtifactError(
            f"{source}: primary_endpoint.candidate_comparison must identify B0 and a "
            f"candidate (got {unique!r})"
        )
    baseline = "B0"
    non_baseline = [value for value in unique if value != baseline]
    if len(non_baseline) != 1:
        raise ArtifactError(
            f"{source}: primary_endpoint must identify exactly one non-B0 candidate"
        )
    unknown = [value for value in unique if value not in candidates]
    if unknown:
        raise ArtifactError(
            f"{source}: primary_endpoint references undeclared candidates: {', '.join(unknown)}"
        )
    if len(unique) != 2:
        raise ArtifactError(f"{source}: primary_endpoint candidate pair must have two ids")
    return (non_baseline[0], baseline)


def _validate_optional_bins(
    raw: Any, source: str, field: str, require_samples: bool = False
) -> tuple[Bin, ...] | None:
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw:
        raise ArtifactError(f"{source}: {field} must be a non-empty list when present")
    bins: list[Bin] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        where = f"{source}: {field}[{index}]"
        if not isinstance(item, Mapping):
            raise ArtifactError(f"{where} must be an object")
        bin_id = item.get("bin_id") or item.get("label")
        if not isinstance(bin_id, str) or not bin_id or bin_id in seen:
            raise ArtifactError(f"{where}.bin_id must be a unique non-empty string")
        seen.add(bin_id)
        _require_finite_number(item.get("lower"), f"{where}.lower", where)
        upper = item.get("upper")
        if upper is not None:
            _require_finite_number(upper, f"{where}.upper", where)
            if float(upper) <= float(item["lower"]):
                raise ArtifactError(f"{where}.upper must exceed lower")
        n_samples = item.get("n_samples")
        if n_samples is not None and (not _is_int(n_samples) or n_samples < 0):
            raise ArtifactError(f"{where}.n_samples must be a non-negative integer")
        bins.append(
            Bin(
                bin_id=bin_id,
                lower=float(item["lower"]),
                upper=float(upper) if upper is not None else None,
                n_samples=n_samples,
            )
        )
    bins.sort(key=lambda item: item.lower)
    for left, right in zip(bins, bins[1:]):
        if left.upper is not None and right.lower < left.upper:
            raise ArtifactError(f"{source}: {field} bins overlap")
    return tuple(bins)


def _optional_finite(value: Any, where: str, field: str) -> float | None:
    if value is None:
        return None
    _require_finite_number(value, f"{where}.{field}", where)
    return float(value)
