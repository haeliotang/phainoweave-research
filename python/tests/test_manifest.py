"""Manifest loading and validation tests."""

from pathlib import Path

import pytest

from conftest import MANIFEST_TOML, write_manifest
from phaino_sdk import (
    Determinism,
    ManifestError,
    ScoreSemantics,
    load_manifest,
    validate_manifest_document,
)


def test_valid_manifest_loads_from_directory(tmp_path: Path) -> None:
    manifest = load_manifest(write_manifest(tmp_path))
    assert manifest.name == "ambient-inference/acoustic_doppler"
    assert manifest.version == "0.1.0"
    assert manifest.contract_version == "1.0"
    assert manifest.entrypoint == "fake_plugin:run"
    assert manifest.media_kinds == ("audio",)
    assert manifest.score_semantics is ScoreSemantics.LOG_LIKELIHOOD_RATIO
    assert manifest.determinism is Determinism.DETERMINISTIC
    assert manifest.capabilities == ("media.audio",)
    assert manifest.limits["wall_ms"] == 30000


def test_valid_manifest_loads_from_file(tmp_path: Path) -> None:
    plugin_dir = write_manifest(tmp_path)
    manifest = load_manifest(plugin_dir / "inferencer.toml")
    assert manifest.name == "ambient-inference/acoustic_doppler"


@pytest.mark.parametrize(
    ("mutation", "fragment"),
    [
        (MANIFEST_TOML.replace('version = "0.1.0"\n', ""), "missing required keys"),
        (MANIFEST_TOML + 'unknown_key = "x"\n', "unknown keys"),
        (
            MANIFEST_TOML.replace('contract_version = "1.0"', 'contract_version = "2.0"'),
            "major",
        ),
        (
            MANIFEST_TOML.replace(
                'score_semantics = "log_likelihood_ratio"',
                'score_semantics = "confidence"',
            ),
            "score_semantics",
        ),
        (
            MANIFEST_TOML.replace('media_kinds = ["audio"]', 'media_kinds = ["lidar"]'),
            "unknown media_kinds",
        ),
        (
            MANIFEST_TOML.replace(
                'capabilities = ["media.audio"]', 'capabilities = ["net.http"]'
            ),
            "unknown capabilities",
        ),
        (
            MANIFEST_TOML.replace('entrypoint = "fake_plugin:run"', 'entrypoint = "fake_plugin"'),
            "entrypoint",
        ),
        (
            MANIFEST_TOML.replace("wall_ms = 30000", "wall_ms = 0"),
            "positive integer",
        ),
        (
            MANIFEST_TOML.replace(
                'determinism = "deterministic"', 'determinism = "sometimes"'
            ),
            "determinism",
        ),
    ],
)
def test_invalid_manifest_is_rejected(tmp_path: Path, mutation: str, fragment: str) -> None:
    plugin_dir = write_manifest(tmp_path, mutation)
    with pytest.raises(ManifestError) as raised:
        load_manifest(plugin_dir)
    assert fragment in str(raised.value)


def test_manifest_document_validation_is_pure() -> None:
    import tomllib

    document = tomllib.loads(MANIFEST_TOML)
    assert validate_manifest_document(document) == []
