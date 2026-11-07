"""Strict loading and validation of adequacy / hardened JSON artifacts.

The evaluation harness is independent of the adequacy method: it consumes JSON documents
only. It never imports ``phaino_acoustics`` and it never recomputes the method's tests.
Unknown extra diagnostic fields are tolerated so the method can add evidence; the fixed
contract fields, duplicate trial identities, non-finite numbers, and missing truth are
rejected.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

EXPERIMENT = "e0-adequacy"
LAYERS = frozenset({"tuning", "locked"})
MECHANISMS = frozenset(
    {
        "acceleration",
        "clock_rate",
        "clock_offset",
        "window",
        "geometry",
        "noise",
        "null",
        "within_tolerance",
    }
)
EPISTEMIC_DECISIONS = frozenset({"supported", "rejected", "undetermined"})
ADEQUACY_TEST_KEYS = (
    "standardized_residuals",
    "autocorrelation",
    "time_structure",
    "block_prediction",
    "degeneracy",
)
TOP_LEVEL_REQUIRED = (
    "experiment",
    "layer",
    "protocol_digest",
    "config",
    "environment",
    "trials",
)
TRIAL_REQUIRED = (
    "condition",
    "trial",
    "seed",
    "layer",
    "mechanism",
    "evaluation_only",
    "observation",
    "hardened",
    "adequacy",
)
SCENARIO_REQUIRED = (
    "f0",
    "v",
    "t0",
    "b",
    "c",
    "accel",
    "clock_scale_ppm",
    "clock_offset_s",
)
OBSERVATION_REQUIRED = ("if_rms_hz", "sigma_f_hz", "n_samples", "duration_s")
HARDENED_REQUIRED = (
    "params",
    "optimization_status",
    "identifiability_status_old",
    "decision_status_old",
)
ADEQUACY_REQUIRED = (
    "model_adequacy_status",
    "identifiability_status",
    "epistemic_decision",
    "reason_codes",
    "tests",
)


class AdequacyArtifactError(ValueError):
    """Raised when an artifact violates the fixed contract."""


@dataclass(frozen=True)
class AdequacyArtifact:
    """A validated adequacy artifact. Trials stay as validated mappings."""

    experiment: str
    layer: str
    protocol_digest: str
    config: Mapping[str, Any]
    environment: Mapping[str, Any]
    trials: tuple[Mapping[str, Any], ...]
    source: str | None = None


def load_adequacy_artifact(path: str | Path) -> AdequacyArtifact:
    """Loads and validates one adequacy artifact."""
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as error:
        raise AdequacyArtifactError(f"cannot read adequacy artifact {source}: {error}") from error
    document = parse_strict_json(raw, source=str(source))
    if not isinstance(document, Mapping):
        raise AdequacyArtifactError(f"{source}: top-level artifact must be a JSON object")
    return validate_adequacy_artifact(document, source=str(source))


def validate_adequacy_artifact(
    document: Mapping[str, Any], source: str | None = None
) -> AdequacyArtifact:
    """Validates an in-memory adequacy artifact document."""
    label = source or "<memory>"
    _require_keys(document, TOP_LEVEL_REQUIRED, "$", label)
    if document["experiment"] != EXPERIMENT:
        raise AdequacyArtifactError(
            f"{label}: experiment must be {EXPERIMENT!r}, got {document['experiment']!r}"
        )
    layer = document["layer"]
    if layer not in LAYERS:
        raise AdequacyArtifactError(f"{label}: layer must be one of {sorted(LAYERS)}")
    _require_string(document["protocol_digest"], "$.protocol_digest", label)
    if not isinstance(document["config"], Mapping):
        raise AdequacyArtifactError(f"{label}: config must be an object")
    if not isinstance(document["environment"], Mapping):
        raise AdequacyArtifactError(f"{label}: environment must be an object")
    trials = document["trials"]
    if not isinstance(trials, list) or not trials:
        raise AdequacyArtifactError(f"{label}: trials must be a non-empty list")

    seen: set[tuple[str, int]] = set()
    validated: list[Mapping[str, Any]] = []
    for index, trial in enumerate(trials):
        where = f"{label}: trials[{index}]"
        if not isinstance(trial, Mapping):
            raise AdequacyArtifactError(f"{where} must be an object")
        _validate_trial(trial, where, layer)
        key = (trial["condition"], trial["trial"])
        if key in seen:
            raise AdequacyArtifactError(
                f"{where}: duplicate trial identity condition={key[0]!r} trial={key[1]!r}"
            )
        seen.add(key)
        validated.append(dict(trial))
    return AdequacyArtifact(
        experiment=document["experiment"],
        layer=layer,
        protocol_digest=document["protocol_digest"],
        config=dict(document["config"]),
        environment=dict(document["environment"]),
        trials=tuple(validated),
        source=source,
    )


def load_old_decisions(path: str | Path) -> tuple[dict[tuple[str, int], str], str]:
    """Loads old-rule decisions from a hardened/adequacy artifact.

    Returns ``(decisions, decision_field)``. The field is reported so the comparison can
    state where the old rule came from. Accepted old-rule decision fields are, in order:
    ``hardened.decision_status``, ``hardened.decision_status_old``,
    ``decision_status``, ``decision_status_old``.
    """
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as error:
        raise AdequacyArtifactError(f"cannot read old-decision artifact {source}: {error}") from error
    document = parse_strict_json(raw, source=str(source))
    if not isinstance(document, Mapping):
        raise AdequacyArtifactError(f"{source}: old-decision artifact must be an object")
    trials = document.get("trials")
    if not isinstance(trials, list) or not trials:
        raise AdequacyArtifactError(f"{source}: old-decision artifact needs a non-empty trials list")
    decisions: dict[tuple[str, int], str] = {}
    used_field: str | None = None
    for index, trial in enumerate(trials):
        where = f"{source}: trials[{index}]"
        if not isinstance(trial, Mapping):
            raise AdequacyArtifactError(f"{where} must be an object")
        condition = trial.get("condition")
        trial_number = trial.get("trial")
        if not isinstance(condition, str) or not condition:
            raise AdequacyArtifactError(f"{where}.condition must be a non-empty string")
        if not _is_int(trial_number):
            raise AdequacyArtifactError(f"{where}.trial must be an integer")
        decision, field = _old_decision_from_trial(trial, where)
        if used_field is None:
            used_field = field
        key = (condition, trial_number)
        if key in decisions:
            raise AdequacyArtifactError(f"{where}: duplicate trial decision for {key!r}")
        decisions[key] = decision
    return decisions, used_field or "unknown"


def embedded_old_decisions(
    artifact: AdequacyArtifact,
) -> tuple[dict[tuple[str, int], str], str]:
    """Extracts old-rule decisions embedded in an adequacy artifact."""
    decisions: dict[tuple[str, int], str] = {}
    used_field: str | None = None
    for trial in artifact.trials:
        key = (trial["condition"], trial["trial"])
        decision, field = _old_decision_from_trial(
            trial, f"{artifact.source or '<artifact>'}: condition={key[0]!r} trial={key[1]!r}"
        )
        if used_field is None:
            used_field = field
        decisions[key] = decision
    return decisions, used_field or "unknown"


def _old_decision_from_trial(trial: Mapping[str, Any], where: str) -> tuple[str, str]:
    hardened = trial.get("hardened")
    candidates: list[tuple[str, Any]] = []
    if isinstance(hardened, Mapping):
        candidates.extend(
            [
                ("hardened.decision_status", hardened.get("decision_status")),
                ("hardened.decision_status_old", hardened.get("decision_status_old")),
            ]
        )
    candidates.extend(
        [
            ("decision_status", trial.get("decision_status")),
            ("decision_status_old", trial.get("decision_status_old")),
        ]
    )
    for field, value in candidates:
        if isinstance(value, str) and value:
            return value, field
    raise AdequacyArtifactError(
        f"{where}: old-rule decision is missing; the fixed adequacy contract carries "
        "'hardened.decision_status_old', but the old-rule definition in the task names "
        "'hardened.decision_status'. Supply --hardened/--old-artifact decisions or fix the field."
    )


def _validate_trial(trial: Mapping[str, Any], where: str, artifact_layer: str) -> None:
    _require_keys(trial, TRIAL_REQUIRED, where, where)
    _require_string(trial["condition"], f"{where}.condition", where)
    if not _is_int(trial["trial"]):
        raise AdequacyArtifactError(f"{where}.trial must be an integer")
    if not _is_int(trial["seed"]):
        raise AdequacyArtifactError(f"{where}.seed must be an integer")
    if trial["layer"] != artifact_layer or trial["layer"] not in LAYERS:
        raise AdequacyArtifactError(
            f"{where}.layer must equal the artifact layer {artifact_layer!r}"
        )
    if trial["mechanism"] not in MECHANISMS:
        raise AdequacyArtifactError(
            f"{where}.mechanism must be one of {sorted(MECHANISMS)}"
        )

    evaluation = trial["evaluation_only"]
    if not isinstance(evaluation, Mapping):
        raise AdequacyArtifactError(f"{where}.evaluation_only must be an object")
    scenario = evaluation.get("scenario")
    if not isinstance(scenario, Mapping):
        raise AdequacyArtifactError(f"{where}.evaluation_only.scenario is missing truth")
    _require_keys(scenario, SCENARIO_REQUIRED, f"{where}.evaluation_only.scenario", where)
    for key in SCENARIO_REQUIRED:
        _require_finite_number(
            scenario[key], f"{where}.evaluation_only.scenario.{key}", where
        )
    for key in ("f0", "v", "b"):
        if float(scenario[key]) <= 0.0:
            raise AdequacyArtifactError(
                f"{where}.evaluation_only.scenario.{key} must be positive truth"
            )

    observation = trial["observation"]
    if not isinstance(observation, Mapping):
        raise AdequacyArtifactError(f"{where}.observation must be an object")
    _require_keys(observation, OBSERVATION_REQUIRED, f"{where}.observation", where)
    for key in ("if_rms_hz", "sigma_f_hz"):
        _require_finite_number(observation[key], f"{where}.observation.{key}", where)
    if not _is_int(observation["n_samples"]) or observation["n_samples"] <= 0:
        raise AdequacyArtifactError(f"{where}.observation.n_samples must be a positive integer")
    _require_finite_number(observation["duration_s"], f"{where}.observation.duration_s", where)
    if float(observation["duration_s"]) <= 0.0:
        raise AdequacyArtifactError(f"{where}.observation.duration_s must be positive")

    hardened = trial["hardened"]
    if not isinstance(hardened, Mapping):
        raise AdequacyArtifactError(f"{where}.hardened must be an object")
    _require_keys(hardened, HARDENED_REQUIRED, f"{where}.hardened", where)
    params = hardened["params"]
    if not isinstance(params, Mapping):
        raise AdequacyArtifactError(f"{where}.hardened.params must be an object")
    _require_keys(params, ("f0", "v", "t0", "b"), f"{where}.hardened.params", where)
    for key in ("f0", "v", "t0", "b"):
        _require_finite_number(params[key], f"{where}.hardened.params.{key}", where)
    for key in ("optimization_status", "identifiability_status_old", "decision_status_old"):
        _require_string(hardened[key], f"{where}.hardened.{key}", where)

    adequacy = trial["adequacy"]
    if not isinstance(adequacy, Mapping):
        raise AdequacyArtifactError(f"{where}.adequacy must be an object")
    _require_keys(adequacy, ADEQUACY_REQUIRED, f"{where}.adequacy", where)
    for key in ("model_adequacy_status", "identifiability_status"):
        _require_string(adequacy[key], f"{where}.adequacy.{key}", where)
    if adequacy["epistemic_decision"] not in EPISTEMIC_DECISIONS:
        raise AdequacyArtifactError(
            f"{where}.adequacy.epistemic_decision must be one of "
            f"{sorted(EPISTEMIC_DECISIONS)}"
        )
    reason_codes = adequacy["reason_codes"]
    if not isinstance(reason_codes, list) or any(
        not isinstance(code, str) or not code for code in reason_codes
    ):
        raise AdequacyArtifactError(f"{where}.adequacy.reason_codes must be a list of strings")
    tests = adequacy["tests"]
    if not isinstance(tests, Mapping):
        raise AdequacyArtifactError(f"{where}.adequacy.tests must be an object")
    _require_keys(tests, ADEQUACY_TEST_KEYS, f"{where}.adequacy.tests", where)
    _reject_nonfinite(tests, f"{where}.adequacy.tests")


def parse_strict_json(raw: bytes, source: str) -> Any:
    """Parses strict JSON, rejecting duplicate object keys and NaN/Infinity."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise AdequacyArtifactError(f"{source}: not valid UTF-8") from error

    def reject_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise AdequacyArtifactError(f"{source}: duplicate JSON object key {key!r}")
            result[key] = value
        return result

    def reject_constant(token: str) -> Any:
        raise AdequacyArtifactError(f"{source}: non-finite JSON number {token} is not allowed")

    try:
        return json.loads(
            text, object_pairs_hook=reject_duplicates, parse_constant=reject_constant
        )
    except json.JSONDecodeError as error:
        raise AdequacyArtifactError(f"{source}: malformed JSON: {error}") from error
    except AdequacyArtifactError:
        raise
    except ValueError as error:
        raise AdequacyArtifactError(f"{source}: malformed JSON: {error}") from error


def _require_keys(
    document: Mapping[str, Any],
    required: Iterable[str],
    path: str,
    label: str,
) -> None:
    missing = [key for key in required if key not in document]
    if missing:
        raise AdequacyArtifactError(f"{label}: {path} is missing required keys: {', '.join(missing)}")


def _require_string(value: Any, path: str, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise AdequacyArtifactError(f"{label}: {path} must be a non-empty string")


def _require_finite_number(value: Any, path: str, label: str) -> None:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise AdequacyArtifactError(f"{label}: {path} must be a finite number")


def _reject_nonfinite(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_nonfinite(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_nonfinite(item, f"{path}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise AdequacyArtifactError(f"{path} contains a non-finite number")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
