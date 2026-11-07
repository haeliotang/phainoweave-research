"""Strict validation of C2-M2 predictive measurement-error artifacts.

Artifact-only evaluator: no acoustics imports. The contract is fixed; the evaluator adds
an explicit ``fit_scope`` obligation so held-out predictions cannot be fit on the same
held-out cell, and pre-registered tolerance fields are mandatory.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

EXPERIMENT = "c2-m2"
SCHEMA_VERSION = "1.0.0"
SPLITS = frozenset({"train", "heldout"})
RESAMPLING_UNITS = frozenset({"trial", "scenario"})
REQUIRED_TOLERANCES = ("decision_frr_abs_error_pp", "distribution_ks_max")
OPTIONAL_TOLERANCES = ("error_mean_abs_hz", "error_rms_abs_hz", "acf_max_abs")
TOP_LEVEL_KEYS = frozenset(
    {
        "experiment",
        "measurement_model_id",
        "development",
        "models",
        "tolerances",
        "cells",
        "reference_estimator",
    }
)
CELL_KEYS = frozenset(
    {
        "cell_id",
        "geometry_m",
        "speed_mps",
        "snr_db",
        "split",
        "actual",
        "predicted",
        "resampling_unit",
        "n_independent_units",
    }
)
ACTUAL_KEYS = frozenset(
    {"error_mean_hz", "error_rms_hz", "acf_lag1", "acf", "lb_stats", "frr", "n_trials"}
)
PREDICTED_KEYS = frozenset(
    {"error_mean_hz", "error_rms_hz", "acf", "lb_stats", "frr"}
)
TRAIN_SCOPE_LABELS = frozenset(
    {"train", "training", "train_cells", "train_only", "cv_train", "cross_validation_train"}
)
LEAKY_SCOPE_LABELS = frozenset(
    {
        "heldout",
        "held_out",
        "held-out",
        "heldout_cells",
        "all",
        "global",
        "same_cell",
        "this_cell",
        "cell",
    }
)


class ArtifactError(ValueError):
    """Raised when a C2-M2 artifact violates the fixed contract."""


@dataclass(frozen=True)
class AcfPoint:
    lag_s: float
    value: float


@dataclass(frozen=True)
class ActualStats:
    error_mean_hz: float
    error_rms_hz: float
    acf_lag1: float
    acf: tuple[AcfPoint, ...]
    lb_stats: tuple[float, ...]
    frr: float
    n_trials: int


@dataclass(frozen=True)
class PredictedStats:
    error_mean_hz: float
    error_rms_hz: float
    acf: tuple[AcfPoint, ...]
    lb_stats: tuple[float, ...]
    frr: float


@dataclass(frozen=True)
class Cell:
    cell_id: str
    geometry_m: float
    speed_mps: float
    snr_db: float
    split: str
    actual: ActualStats
    predicted: Mapping[str, PredictedStats]
    resampling_unit: str
    n_independent_units: int
    fit_scopes: Mapping[str, Any]


@dataclass(frozen=True)
class ReferenceEstimator:
    name: str
    frr: float
    detection: float
    notes: str | None


@dataclass(frozen=True)
class Artifact:
    path: str
    experiment: str
    measurement_model_id: str
    seed_base: int
    development_n_trials: int
    models: tuple[str, ...]
    tolerances: Mapping[str, float]
    cells: tuple[Cell, ...]
    reference_estimator: ReferenceEstimator
    repaired_candidates: Mapping[str, Mapping[str, float]] | None
    sha256: str

    @property
    def heldout_cells(self) -> tuple[Cell, ...]:
        return tuple(cell for cell in self.cells if cell.split == "heldout")

    @property
    def train_cells(self) -> tuple[Cell, ...]:
        return tuple(cell for cell in self.cells if cell.split == "train")


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
        measurement_model_id=artifact.measurement_model_id,
        seed_base=artifact.seed_base,
        development_n_trials=artifact.development_n_trials,
        models=artifact.models,
        tolerances=artifact.tolerances,
        cells=artifact.cells,
        reference_estimator=artifact.reference_estimator,
        repaired_candidates=artifact.repaired_candidates,
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def validate_artifact(document: Mapping[str, Any], source: str) -> Artifact:
    _require_keys(document, TOP_LEVEL_KEYS, "$", source)
    if document["experiment"] != EXPERIMENT:
        raise ArtifactError(
            f"{source}: experiment must be {EXPERIMENT!r}, got {document['experiment']!r}"
        )
    _require_string(document["measurement_model_id"], "$.measurement_model_id", source)
    development = document["development"]
    if not isinstance(development, Mapping):
        raise ArtifactError(f"{source}: development must be an object")
    seed_base = development.get("seed_base")
    n_trials = development.get("n_trials")
    if not _is_int(seed_base):
        raise ArtifactError(f"{source}: development.seed_base must be an integer")
    if not _is_int(n_trials) or n_trials <= 0:
        raise ArtifactError(f"{source}: development.n_trials must be a positive integer")

    models_raw = document["models"]
    if not isinstance(models_raw, list) or not models_raw:
        raise ArtifactError(f"{source}: models must be a non-empty list")
    models: list[str] = []
    for index, model in enumerate(models_raw):
        if not isinstance(model, str) or not model:
            raise ArtifactError(f"{source}: models[{index}] must be a non-empty string")
        if model in models:
            raise ArtifactError(f"{source}: duplicate model {model!r}")
        models.append(model)

    tolerances = _validate_tolerances(document["tolerances"], source)
    cells_raw = document["cells"]
    if not isinstance(cells_raw, list) or not cells_raw:
        raise ArtifactError(f"{source}: cells must be a non-empty list")

    # First pass: cell ids/splits and duplicate detection, so fit_scope can be audited.
    cell_ids: set[str] = set()
    train_ids: set[str] = set()
    heldout_ids: set[str] = set()
    for index, raw_cell in enumerate(cells_raw):
        where = f"{source}: cells[{index}]"
        if not isinstance(raw_cell, Mapping):
            raise ArtifactError(f"{where} must be an object")
        cell_id = raw_cell.get("cell_id")
        if not isinstance(cell_id, str) or not cell_id:
            raise ArtifactError(f"{where}.cell_id must be a non-empty string")
        if cell_id in cell_ids:
            raise ArtifactError(f"{where}: duplicate cell_id {cell_id!r}")
        cell_ids.add(cell_id)
        split = raw_cell.get("split")
        if split not in SPLITS:
            raise ArtifactError(f"{where}.split must be one of {sorted(SPLITS)}")
        if split == "heldout":
            heldout_ids.add(cell_id)
        else:
            train_ids.add(cell_id)
    if not heldout_ids:
        raise ArtifactError(f"{source}: at least one held-out cell is required")

    cells: list[Cell] = []
    for index, raw_cell in enumerate(cells_raw):
        where = f"{source}: cells[{index}]"
        cells.append(
            _validate_cell(
                raw_cell,
                where,
                tuple(models),
                cell_ids,
                train_ids,
                heldout_ids,
            )
        )

    reference = _validate_reference(document["reference_estimator"], source)
    repaired = _validate_optional_repaired_candidates(document, source)
    return Artifact(
        path=source,
        experiment=document["experiment"],
        measurement_model_id=document["measurement_model_id"],
        seed_base=seed_base,
        development_n_trials=n_trials,
        models=tuple(models),
        tolerances=tolerances,
        cells=tuple(cells),
        reference_estimator=reference,
        repaired_candidates=repaired,
        sha256="",
    )


def _validate_tolerances(raw: Any, source: str) -> dict[str, float]:
    if not isinstance(raw, Mapping):
        raise ArtifactError(f"{source}: tolerances must be an object")
    missing = sorted(set(REQUIRED_TOLERANCES) - set(raw))
    if missing:
        raise ArtifactError(
            f"{source}: tolerances is missing pre-registered fields: {', '.join(missing)}"
        )
    tolerances: dict[str, float] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key:
            raise ArtifactError(f"{source}: tolerance keys must be non-empty strings")
        _require_finite_number(value, f"$.tolerances.{key}", source)
        if float(value) <= 0.0:
            raise ArtifactError(f"{source}: tolerances.{key} must be positive")
        tolerances[key] = float(value)
    return tolerances


def _validate_cell(
    raw: Mapping[str, Any],
    where: str,
    models: tuple[str, ...],
    cell_ids: set[str],
    train_ids: set[str],
    heldout_ids: set[str],
) -> Cell:
    _require_keys(raw, CELL_KEYS, "$", where)
    _require_string(raw["cell_id"], f"{where}.cell_id", where)
    for field in ("geometry_m", "speed_mps", "snr_db"):
        _require_finite_number(raw[field], f"{where}.{field}", where)
    if float(raw["geometry_m"]) <= 0.0:
        raise ArtifactError(f"{where}.geometry_m must be positive")
    if float(raw["speed_mps"]) <= 0.0:
        raise ArtifactError(f"{where}.speed_mps must be positive")
    if raw["split"] not in SPLITS:
        raise ArtifactError(f"{where}.split must be one of {sorted(SPLITS)}")
    if raw["resampling_unit"] not in RESAMPLING_UNITS:
        raise ArtifactError(
            f"{where}.resampling_unit must be one of {sorted(RESAMPLING_UNITS)}"
        )
    if not _is_int(raw["n_independent_units"]) or raw["n_independent_units"] <= 0:
        raise ArtifactError(f"{where}.n_independent_units must be a positive integer")
    actual = _validate_actual(raw["actual"], f"{where}.actual", where)
    predicted_raw = raw["predicted"]
    if not isinstance(predicted_raw, Mapping):
        raise ArtifactError(f"{where}.predicted must be an object")
    missing = sorted(set(models) - set(predicted_raw))
    extra = sorted(set(predicted_raw) - set(models))
    if missing:
        raise ArtifactError(f"{where}.predicted is missing models: {', '.join(missing)}")
    if extra:
        raise ArtifactError(f"{where}.predicted has undeclared models: {', '.join(extra)}")
    predicted: dict[str, PredictedStats] = {}
    for model in models:
        predicted[model] = _validate_predicted(
            predicted_raw[model], f"{where}.predicted.{model}", where
        )
    fit_scopes = _validate_fit_scopes(
        raw,
        where,
        models,
        cell_ids,
        train_ids,
        heldout_ids,
    )
    return Cell(
        cell_id=raw["cell_id"],
        geometry_m=float(raw["geometry_m"]),
        speed_mps=float(raw["speed_mps"]),
        snr_db=float(raw["snr_db"]),
        split=raw["split"],
        actual=actual,
        predicted=predicted,
        resampling_unit=raw["resampling_unit"],
        n_independent_units=raw["n_independent_units"],
        fit_scopes=fit_scopes,
    )


def _validate_actual(raw: Any, path: str, label: str) -> ActualStats:
    if not isinstance(raw, Mapping):
        raise ArtifactError(f"{path} must be an object")
    _require_keys(raw, ACTUAL_KEYS, path, label)
    for field in ("error_mean_hz", "error_rms_hz", "acf_lag1", "frr"):
        _require_finite_number(raw[field], f"{path}.{field}", label)
    if not 0.0 <= float(raw["frr"]) <= 1.0:
        raise ArtifactError(f"{path}.frr must be in [0,1]")
    if float(raw["error_rms_hz"]) < 0.0:
        raise ArtifactError(f"{path}.error_rms_hz must be non-negative")
    if not _is_int(raw["n_trials"]) or raw["n_trials"] <= 0:
        raise ArtifactError(f"{path}.n_trials must be a positive integer")
    acf = _validate_acf(raw["acf"], f"{path}.acf", label)
    lb_stats = _validate_numeric_list(raw["lb_stats"], f"{path}.lb_stats", label)
    if not lb_stats:
        raise ArtifactError(f"{path}.lb_stats must be non-empty")
    return ActualStats(
        error_mean_hz=float(raw["error_mean_hz"]),
        error_rms_hz=float(raw["error_rms_hz"]),
        acf_lag1=float(raw["acf_lag1"]),
        acf=acf,
        lb_stats=lb_stats,
        frr=float(raw["frr"]),
        n_trials=raw["n_trials"],
    )


def _validate_predicted(raw: Any, path: str, label: str) -> PredictedStats:
    if not isinstance(raw, Mapping):
        raise ArtifactError(f"{path} must be an object")
    _require_keys(raw, PREDICTED_KEYS, path, label)
    for field in ("error_mean_hz", "error_rms_hz", "frr"):
        _require_finite_number(raw[field], f"{path}.{field}", label)
    if not 0.0 <= float(raw["frr"]) <= 1.0:
        raise ArtifactError(f"{path}.frr must be in [0,1]")
    if float(raw["error_rms_hz"]) < 0.0:
        raise ArtifactError(f"{path}.error_rms_hz must be non-negative")
    acf = _validate_acf(raw["acf"], f"{path}.acf", label)
    lb_stats = _validate_numeric_list(raw["lb_stats"], f"{path}.lb_stats", label)
    if not lb_stats:
        raise ArtifactError(f"{path}.lb_stats must be non-empty")
    return PredictedStats(
        error_mean_hz=float(raw["error_mean_hz"]),
        error_rms_hz=float(raw["error_rms_hz"]),
        acf=acf,
        lb_stats=lb_stats,
        frr=float(raw["frr"]),
    )


def _validate_acf(raw: Any, path: str, label: str) -> tuple[AcfPoint, ...]:
    if not isinstance(raw, list) or not raw:
        raise ArtifactError(f"{path} must be a non-empty list of {log_lag_contract()}")
    points: list[AcfPoint] = []
    seen: set[float] = set()
    for index, point in enumerate(raw):
        if not isinstance(point, Mapping):
            raise ArtifactError(f"{path}[{index}] must be an object with lag_s and value")
        if set(point) != {"lag_s", "value"}:
            raise ArtifactError(f"{path}[{index}] must have exactly lag_s and value")
        _require_finite_number(point["lag_s"], f"{path}[{index}].lag_s", label)
        _require_finite_number(point["value"], f"{path}[{index}].value", label)
        lag = float(point["lag_s"])
        if lag in seen:
            raise ArtifactError(f"{path}: duplicate ACF lag {lag}")
        seen.add(lag)
        points.append(AcfPoint(lag_s=lag, value=float(point["value"])))
    return tuple(sorted(points, key=lambda item: item.lag_s))


def _validate_numeric_list(raw: Any, path: str, label: str) -> tuple[float, ...]:
    if not isinstance(raw, list):
        raise ArtifactError(f"{path} must be a list of finite numbers")
    values: list[float] = []
    for index, value in enumerate(raw):
        _require_finite_number(value, f"{path}[{index}]", label)
        values.append(float(value))
    return tuple(values)


def log_lag_contract() -> str:
    return "{lag_s, value} objects"


def _validate_fit_scopes(
    raw: Mapping[str, Any],
    where: str,
    models: tuple[str, ...],
    cell_ids: set[str],
    train_ids: set[str],
    heldout_ids: set[str],
) -> dict[str, Any]:
    cell_scope = raw.get("fit_scope")
    cell_mapping: dict[str, Any] = {}
    if cell_scope is not None:
        if isinstance(cell_scope, Mapping):
            unknown = sorted(set(cell_scope) - set(models))
            if unknown:
                raise ArtifactError(
                    f"{where}.fit_scope has undeclared models: {', '.join(unknown)}"
                )
            cell_mapping = {model: cell_scope[model] for model in models if model in cell_scope}
        elif isinstance(cell_scope, (str, list)):
            cell_mapping = {model: cell_scope for model in models}
        else:
            raise ArtifactError(f"{where}.fit_scope must be a string, list or model mapping")

    predicted_raw = raw["predicted"]
    scopes: dict[str, Any] = {}
    for model in models:
        predicted_scope = None
        if isinstance(predicted_raw.get(model), Mapping):
            predicted_scope = predicted_raw[model].get("fit_scope")
        scope = predicted_scope if predicted_scope is not None else cell_mapping.get(model)
        if scope is None:
            if raw["split"] == "heldout":
                raise ArtifactError(
                    f"{where}: fit_scope is required for held-out cell {raw['cell_id']!r} "
                    f"and model {model!r}"
                )
            continue
        _check_scope(scope, where, raw["cell_id"], raw["split"], cell_ids, train_ids, heldout_ids)
        scopes[model] = scope
    return scopes


def _check_scope(
    scope: Any,
    where: str,
    cell_id: str,
    split: str,
    cell_ids: set[str],
    train_ids: set[str],
    heldout_ids: set[str],
) -> None:
    values: list[Any]
    if isinstance(scope, str):
        values = [scope]
    elif isinstance(scope, list) and scope:
        values = scope
    else:
        raise ArtifactError(
            f"{where}: fit_scope for {cell_id!r} must be a string or non-empty list"
        )
    if split != "heldout":
        return
    for value in values:
        if not isinstance(value, str) or not value:
            raise ArtifactError(f"{where}: fit_scope entries must be non-empty strings")
        normalized = value.strip().lower()
        if normalized in TRAIN_SCOPE_LABELS:
            continue
        if normalized in LEAKY_SCOPE_LABELS:
            raise ArtifactError(
                f"{where}: fit_scope {value!r} for held-out cell {cell_id!r} leaks held-out data"
            )
        if value in heldout_ids:
            raise ArtifactError(
                f"{where}: fit_scope references held-out cell {value!r} for held-out cell {cell_id!r}"
            )
        if value in train_ids:
            continue
        raise ArtifactError(
            f"{where}: unsupported fit_scope {value!r} for held-out cell {cell_id!r}; "
            "use train labels or train cell_ids"
        )


def _validate_reference(raw: Any, source: str) -> ReferenceEstimator:
    if not isinstance(raw, Mapping):
        raise ArtifactError(f"{source}: reference_estimator must be an object")
    missing = sorted({"name", "frr", "detection"} - set(raw))
    if missing:
        raise ArtifactError(
            f"{source}: reference_estimator is missing keys: {', '.join(missing)}"
        )
    if not isinstance(raw["name"], str) or not raw["name"]:
        raise ArtifactError(f"{source}: reference_estimator.name must be a non-empty string")
    for field in ("frr", "detection"):
        _require_finite_number(raw[field], f"$.reference_estimator.{field}", source)
        if not 0.0 <= float(raw[field]) <= 1.0:
            raise ArtifactError(f"{source}: reference_estimator.{field} must be in [0,1]")
    notes = raw.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise ArtifactError(f"{source}: reference_estimator.notes must be a string")
    return ReferenceEstimator(
        name=raw["name"],
        frr=float(raw["frr"]),
        detection=float(raw["detection"]),
        notes=notes,
    )


def _validate_optional_repaired_candidates(
    document: Mapping[str, Any], source: str
) -> Mapping[str, Mapping[str, float]] | None:
    raw = document.get("repaired_candidates")
    if raw is None:
        return None
    if not isinstance(raw, Mapping) or not raw:
        raise ArtifactError(f"{source}: repaired_candidates must be a non-empty object")
    result: dict[str, Mapping[str, float]] = {}
    for candidate, values in raw.items():
        if not isinstance(candidate, str) or not candidate:
            raise ArtifactError(f"{source}: repaired_candidates keys must be strings")
        if not isinstance(values, Mapping):
            raise ArtifactError(f"{source}: repaired_candidates.{candidate} must be an object")
        for field in ("frr", "detection"):
            _require_finite_number(
                values.get(field),
                f"$.repaired_candidates.{candidate}.{field}",
                source,
            )
            if not 0.0 <= float(values[field]) <= 1.0:
                raise ArtifactError(
                    f"{source}: repaired_candidates.{candidate}.{field} must be in [0,1]"
                )
        result[candidate] = {
            "frr": float(values["frr"]),
            "detection": float(values["detection"]),
        }
    return result


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
