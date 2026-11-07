"""Shared fixtures and builders for the phaino-sdk test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from phaino_sdk import Manifest, load_manifest

MANIFEST_TOML = """\
name = "ambient-inference/acoustic_doppler"
version = "0.1.0"
contract_version = "1.0"
entrypoint = "fake_plugin:run"
media_kinds = ["audio"]
score_semantics = "log_likelihood_ratio"
determinism = "deterministic"
capabilities = ["media.audio"]
parameters_schema = { type = "object" }
limits = { wall_ms = 30000, cpu_ms = 30000, peak_mem_mb = 2048, max_candidates = 8, max_output_bytes = 1048576 }
"""


def write_manifest(tmp_path: Path, text: str = MANIFEST_TOML) -> Path:
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir(exist_ok=True)
    (plugin_dir / "inferencer.toml").write_text(text, encoding="utf-8")
    return plugin_dir


def make_request(manifest: Manifest) -> dict:
    return {
        "contract_version": "1.0",
        "run_id": "run_0000000000000001",
        "ontology_version": "0.1.0",
        "inferencer": {"name": manifest.name, "version": manifest.version},
        "hypothesis_query": {
            "region": {
                "kind": "bbox",
                "payload": {
                    "min_lon": -1.4,
                    "min_lat": 51.2,
                    "max_lon": -1.1,
                    "max_lat": 51.5,
                },
            },
            "time": {
                "start": "2026-03-14T21:46:55.000000Z",
                "end": "2026-03-14T21:47:15.000000Z",
                "inner_confidence": 0.8,
            },
            "state_filter": {},
            "hypothesis_ids": [],
            "max_hypotheses": 8,
        },
        "observation_refs": [
            {
                "id": "obs_0000000000000001",
                "content_hash": "c0a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f",
                "media_kind": "audio",
                "media_path": "blobs/sha256/c0/a1/c0a1",
                "license_snapshot": {
                    "spdx": "CC-BY-4.0",
                    "terms_url": "https://creativecommons.org/licenses/by/4.0/",
                    "access_level": "public",
                },
            }
        ],
        "feature_refs": [],
        "constraint_refs": [
            {
                "id": "con_0000000000000001",
                "constraint_kind": "kinematic",
                "version": "1.0.0",
                "expression": "f_obs(t) = f0 * c / (c - v_r(t))",
                "parameters": {"c_m_s": 343.0},
                "residual_function": "kinematics.doppler_rms_v1",
                "tolerance": 0.01,
            }
        ],
        "data_snapshot_refs": [],
        "evidence_scope": [
            "obs_0000000000000001",
            "ftr_0000000000000001",
            "con_0000000000000001",
        ],
        "parameters": {"candidate_bearing_step_deg": 5.0},
        "seed": 20260314,
        "budget": {
            "wall_ms": 30000,
            "cpu_ms": 30000,
            "peak_mem_mb": 2048,
            "max_candidates": 8,
            "max_output_bytes": 1048576,
        },
        "scratch_dir": "/tmp/phaino/run_0000000000000001",
    }


def make_response(manifest: Manifest) -> dict:
    return {
        "contract_version": "1.0",
        "inferencer": {"name": manifest.name, "version": manifest.version},
        "status": "ok",
        "complete": True,
        "candidates": [
            {
                "candidate_id": "candidate-1",
                "claim": {
                    "location": {
                        "kind": "bbox",
                        "payload": {
                            "min_lon": -1.4,
                            "min_lat": 51.2,
                            "max_lon": -1.1,
                            "max_lat": 51.5,
                        },
                    },
                    "time": {
                        "start": "2026-03-14T21:46:55.000000Z",
                        "end": "2026-03-14T21:47:15.000000Z",
                        "inner_confidence": 0.8,
                    },
                    "state": {"altitude_m": 1100, "heading_deg": 248},
                },
                "score": {"value": 2.5, "semantics": "log_likelihood_ratio"},
                "independence_key": "source:src_0000000000000001",
                "supporting_evidence_ids": ["ftr_0000000000000001"],
                "conflict_evidence_ids": [],
                "constraint_residuals": [
                    {
                        "constraint_id": "con_0000000000000001",
                        "value": 0.0041,
                        "unit": "1",
                        "n_observations": 1,
                    }
                ],
                "explanation": {
                    "text": "doppler crossing fits the candidate track",
                    "feature_ids": ["ftr_0000000000000001"],
                },
            }
        ],
        "residuals": [],
        "referenced_data_versions": [],
        "determinism": "deterministic",
        "diagnostics": [],
        "timings": {"wall_ms": 12, "cpu_ms": 8},
    }


def make_abstained_response(manifest: Manifest) -> dict:
    response = make_response(manifest)
    response["status"] = "abstained"
    response["candidates"] = []
    response["abstain_reason"] = "insufficient_evidence"
    response["diagnostics"] = []
    return response


@pytest.fixture
def manifest(tmp_path: Path) -> Manifest:
    return load_manifest(write_manifest(tmp_path))


@pytest.fixture
def request_doc(manifest: Manifest) -> dict:
    return make_request(manifest)


@pytest.fixture
def response_doc(manifest: Manifest) -> dict:
    return make_response(manifest)
