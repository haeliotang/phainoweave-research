"""Manifest loading and validation for PhainoWeave inferencer plugins.

The manifest schema is fixed by ``docs/specs/inferencer-contract.md`` §2. Unknown keys,
unknown enum values, bad semver, and a contract MAJOR mismatch are rejected.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .contract import (
    CONTRACT_MAJOR,
    CONTRACT_VERSION,
    Determinism,
    ScoreSemantics,
)

MANIFEST_FILENAME = "inferencer.toml"
REQUIRED_KEYS = (
    "name",
    "version",
    "contract_version",
    "entrypoint",
    "media_kinds",
    "score_semantics",
    "determinism",
    "capabilities",
    "parameters_schema",
    "limits",
)
MEDIA_KINDS = frozenset({"audio", "image", "video", "sensor", "document"})
CAPABILITIES = frozenset(
    {
        "media.audio",
        "media.image",
        "media.video",
        "media.sensor",
        "media.document",
        "compute.gpu",
        "io.scratch",
    }
)
LIMIT_KEYS = frozenset(
    {"wall_ms", "cpu_ms", "peak_mem_mb", "max_candidates", "max_output_bytes"}
)

_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
_CONTRACT_VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_ENTRYPOINT = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$")


class ManifestError(ValueError):
    """Raised when an inferencer manifest violates the contract."""


@dataclass(frozen=True)
class Manifest:
    """A validated inferencer manifest."""

    name: str
    version: str
    contract_version: str
    entrypoint: str
    media_kinds: tuple[str, ...]
    score_semantics: ScoreSemantics
    determinism: Determinism
    capabilities: tuple[str, ...]
    parameters_schema: Mapping[str, Any]
    limits: Mapping[str, Any]

    @property
    def score_semantics_value(self) -> str:
        return self.score_semantics.value

    @property
    def determinism_value(self) -> str:
        return self.determinism.value


def load_manifest(path: str | Path) -> Manifest:
    """Loads and validates `inferencer.toml` from a plugin directory or file path."""
    manifest_path = Path(path)
    if manifest_path.is_dir():
        manifest_path = manifest_path / MANIFEST_FILENAME
    try:
        with manifest_path.open("rb") as handle:
            raw = tomllib.load(handle)
    except FileNotFoundError as error:
        raise ManifestError(f"manifest not found: {manifest_path}") from error
    except tomllib.TOMLDecodeError as error:
        raise ManifestError(f"manifest is not valid TOML: {error}") from error

    problems = validate_manifest_document(raw)
    if problems:
        raise ManifestError("; ".join(problems))
    return _manifest_from_document(raw)


def validate_manifest_document(raw: Mapping[str, Any]) -> list[str]:
    """Returns every manifest contract violation for a parsed TOML document."""
    problems: list[str] = []
    keys = set(raw)
    missing = [key for key in REQUIRED_KEYS if key not in keys]
    if missing:
        problems.append(f"missing required keys: {', '.join(sorted(missing))}")
    unknown = [key for key in keys if key not in REQUIRED_KEYS]
    if unknown:
        problems.append(f"unknown keys: {', '.join(sorted(unknown))}")

    name = raw.get("name")
    if not isinstance(name, str) or not name or "/" not in name:
        problems.append("name must be a non-empty vendor/family string")

    version = raw.get("version")
    if not isinstance(version, str) or not _SEMVER.fullmatch(version):
        problems.append("version must be a semver string")

    contract_version = raw.get("contract_version")
    if not isinstance(contract_version, str):
        problems.append("contract_version must be a MAJOR.MINOR string")
    else:
        match = _CONTRACT_VERSION.fullmatch(contract_version)
        if not match:
            problems.append("contract_version must be a MAJOR.MINOR string")
        elif int(match.group(1)) != CONTRACT_MAJOR:
            problems.append(
                f"contract_version major must be {CONTRACT_MAJOR} (SDK is {CONTRACT_VERSION})"
            )

    entrypoint = raw.get("entrypoint")
    if not isinstance(entrypoint, str) or not _ENTRYPOINT.fullmatch(entrypoint):
        problems.append("entrypoint must be 'package.module:run'")

    media_kinds = raw.get("media_kinds")
    if not isinstance(media_kinds, list) or any(
        not isinstance(kind, str) for kind in media_kinds
    ):
        problems.append("media_kinds must be a list of strings")
    else:
        invalid = sorted(set(media_kinds) - MEDIA_KINDS)
        if invalid:
            problems.append(f"unknown media_kinds: {', '.join(invalid)}")

    score_semantics = raw.get("score_semantics")
    if not isinstance(score_semantics, str) or score_semantics not in {
        semantics.value for semantics in ScoreSemantics
    }:
        problems.append("score_semantics must be a contract enum value")

    determinism = raw.get("determinism")
    if not isinstance(determinism, str) or determinism not in {
        mode.value for mode in Determinism
    }:
        problems.append("determinism must be a contract enum value")

    capabilities = raw.get("capabilities")
    if not isinstance(capabilities, list) or any(
        not isinstance(capability, str) for capability in capabilities
    ):
        problems.append("capabilities must be a list of strings")
    else:
        invalid = sorted(set(capabilities) - CAPABILITIES)
        if invalid:
            problems.append(f"unknown capabilities: {', '.join(invalid)}")

    parameters_schema = raw.get("parameters_schema")
    if not isinstance(parameters_schema, dict):
        problems.append("parameters_schema must be an object")

    limits = raw.get("limits")
    if not isinstance(limits, dict):
        problems.append("limits must be an object")
    else:
        unknown = sorted(set(limits) - LIMIT_KEYS)
        if unknown:
            problems.append(f"unknown limit keys: {', '.join(unknown)}")
        for key, value in limits.items():
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                problems.append(f"limit {key} must be a positive integer")
    return problems


def _manifest_from_document(raw: Mapping[str, Any]) -> Manifest:
    return Manifest(
        name=str(raw["name"]),
        version=str(raw["version"]),
        contract_version=str(raw["contract_version"]),
        entrypoint=str(raw["entrypoint"]),
        media_kinds=tuple(str(kind) for kind in raw["media_kinds"]),
        score_semantics=ScoreSemantics(str(raw["score_semantics"])),
        determinism=Determinism(str(raw["determinism"])),
        capabilities=tuple(str(capability) for capability in raw["capabilities"]),
        parameters_schema=dict(raw["parameters_schema"]),
        limits=dict(raw["limits"]),
    )
