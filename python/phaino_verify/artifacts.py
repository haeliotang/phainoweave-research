"""Strict loading of experiment artifacts, optionally gzip-compressed.

Artifacts are JSON documents. The loader rejects duplicate object keys, NaN/Infinity, and
invalid UTF-8 rather than silently accepting a value the comparison could misinterpret.
Raw file SHA-256 is always recorded from the exact bytes on disk.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from phaino_sdk.canonical import canonical_sha256

GZIP_MAGIC = b"\x1f\x8b"


class ArtifactError(ValueError):
    """Raised when an artifact cannot be read as strict JSON."""


@dataclass(frozen=True)
class Artifact:
    """A parsed artifact plus the identities of the bytes it came from."""

    document: Mapping[str, Any]
    raw_sha256: str
    decoded_sha256: str
    path: str | None = None
    compressed: bool = False

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, Any],
        raw_sha256: str | None = None,
        path: str | None = None,
    ) -> Artifact:
        """Builds an artifact for tests/tools; the canonical digest is the raw digest."""
        digest = raw_sha256 or canonical_sha256(document)
        return cls(
            document=document,
            raw_sha256=digest,
            decoded_sha256=digest,
            path=path,
            compressed=False,
        )


def sha256_bytes(data: bytes) -> str:
    """Lowercase SHA-256 hex of bytes."""
    return hashlib.sha256(data).hexdigest()


def load_artifact(path: str | Path) -> Artifact:
    """Loads a JSON or gzip-compressed JSON artifact (gzip detected by magic bytes)."""
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as error:
        raise ArtifactError(f"cannot read artifact {source}: {error}") from error
    raw_sha256 = sha256_bytes(raw)
    compressed = raw[:2] == GZIP_MAGIC
    if compressed:
        try:
            decoded = gzip.decompress(raw)
        except OSError as error:
            raise ArtifactError(f"cannot decompress {source}: {error}") from error
    else:
        decoded = raw
    decoded_sha256 = sha256_bytes(decoded)
    document = parse_json_document(decoded, source=str(source))
    if not isinstance(document, Mapping):
        raise ArtifactError(f"{source}: artifact JSON must be an object")
    return Artifact(
        document=document,
        raw_sha256=raw_sha256,
        decoded_sha256=decoded_sha256,
        path=str(source),
        compressed=compressed,
    )


def parse_json_document(data: bytes, source: str = "<bytes>") -> Any:
    """Parses strict JSON, rejecting duplicate keys and non-finite numbers."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ArtifactError(f"{source}: artifact is not valid UTF-8") from error

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
            text,
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as error:
        raise ArtifactError(f"{source}: malformed JSON: {error}") from error
    except ArtifactError:
        raise
    except ValueError as error:
        raise ArtifactError(f"{source}: malformed JSON: {error}") from error
