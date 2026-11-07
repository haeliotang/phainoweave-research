"""Runner round-trip tests using a temporary plugin directory."""

import io
import json
import sys
from pathlib import Path

import pytest

from conftest import (
    MANIFEST_TOML,
    make_abstained_response,
    make_request,
    make_response,
    write_manifest,
)
from phaino_sdk import (
    ContractError,
    Determinism,
    ErrorCode,
    InferencerRef,
    Result,
    Status,
    Timings,
    load_manifest,
    to_document,
    validate_response,
)
from phaino_sdk.runner import main, run_plugin


def build_plugin(tmp_path: Path, module_name: str, code: str) -> Path:
    entrypoint = f"{module_name}:run"
    manifest_text = MANIFEST_TOML.replace(
        'entrypoint = "fake_plugin:run"', f'entrypoint = "{entrypoint}"'
    )
    plugin_dir = write_manifest(tmp_path, manifest_text)
    (plugin_dir / f"{module_name}.py").write_text(code, encoding="utf-8")
    return plugin_dir


def test_runner_round_trip_accepts_a_conforming_plugin(tmp_path: Path) -> None:
    module_name = "runner_ok_plugin"
    manifest_text = MANIFEST_TOML.replace(
        'entrypoint = "fake_plugin:run"', f'entrypoint = "{module_name}:run"'
    )
    plugin_dir = write_manifest(tmp_path, manifest_text)
    manifest = load_manifest(plugin_dir)
    request = make_request(manifest)
    response = make_response(manifest)

    code = f"RESPONSE = {response!r}\n\n\ndef run(req):\n    return RESPONSE\n"
    (plugin_dir / f"{module_name}.py").write_text(code, encoding="utf-8")

    result = run_plugin(plugin_dir, request)
    assert result["status"] == "ok"
    assert validate_response(result, manifest, request) == []
    assert result["candidates"][0]["candidate_id"] == "candidate-1"


def test_runner_returns_error_for_invalid_request(tmp_path: Path) -> None:
    manifest = load_manifest(
        build_plugin(
            tmp_path,
            "runner_invalid_request_plugin",
            "def run(req):\n    return {}\n",
        )
    )
    request = make_request(manifest)
    del request["run_id"]

    result = run_plugin(tmp_path / "plugin", request)
    assert result["status"] == "error"
    assert result["error"]["code"] == "invalid_request"
    assert result["error"]["detail"]["violations"]


def test_runner_passes_through_a_valid_abstention(tmp_path: Path) -> None:
    module_name = "runner_abstain_plugin"
    manifest_text = MANIFEST_TOML.replace(
        'entrypoint = "fake_plugin:run"', f'entrypoint = "{module_name}:run"'
    )
    plugin_dir = write_manifest(tmp_path, manifest_text)
    manifest = load_manifest(plugin_dir)
    request = make_request(manifest)
    abstained = make_abstained_response(manifest)
    code = f"RESPONSE = {abstained!r}\n\n\ndef run(req):\n    return RESPONSE\n"
    (plugin_dir / f"{module_name}.py").write_text(code, encoding="utf-8")

    result = run_plugin(plugin_dir, request)
    assert result["status"] == "abstained"
    assert result["abstain_reason"] == "insufficient_evidence"
    assert validate_response(result, manifest, request) == []


def test_runner_rejects_abstention_without_a_reason(tmp_path: Path) -> None:
    module_name = "runner_bad_abstain_plugin"
    manifest_text = MANIFEST_TOML.replace(
        'entrypoint = "fake_plugin:run"', f'entrypoint = "{module_name}:run"'
    )
    plugin_dir = write_manifest(tmp_path, manifest_text)
    manifest = load_manifest(plugin_dir)
    request = make_request(manifest)
    abstained = make_abstained_response(manifest)
    del abstained["abstain_reason"]
    code = f"RESPONSE = {abstained!r}\n\n\ndef run(req):\n    return RESPONSE\n"
    (plugin_dir / f"{module_name}.py").write_text(code, encoding="utf-8")

    result = run_plugin(plugin_dir, request)
    assert result["status"] == "error"
    assert result["error"]["code"] == "internal_error"
    assert "abstain_reason" not in result


def test_runner_returns_error_for_plugin_exception(tmp_path: Path) -> None:
    manifest = load_manifest(
        build_plugin(
            tmp_path,
            "runner_raising_plugin",
            'def run(req):\n    raise RuntimeError("boom")\n',
        )
    )
    request = make_request(manifest)

    result = run_plugin(tmp_path / "plugin", request)
    assert result["status"] == "error"
    assert result["error"]["code"] == "internal_error"
    assert "boom" in result["error"]["message"]
    assert "abstain_reason" not in result
    assert validate_response(result, manifest, request) == []


def test_runner_rejects_a_non_conforming_response(tmp_path: Path) -> None:
    manifest = load_manifest(
        build_plugin(
            tmp_path,
            "runner_bad_response_plugin",
            "def run(req):\n"
            '    return {"contract_version": "1.0", "status": "ok", "complete": True,'
            ' "candidates": []}\n',
        )
    )
    request = make_request(manifest)

    result = run_plugin(tmp_path / "plugin", request)
    assert result["status"] == "error"
    assert result["error"]["code"] == "internal_error"
    assert result["error"]["detail"]["violations"]


def test_runner_main_reads_stdin_and_writes_one_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module_name = "runner_cli_plugin"
    manifest = load_manifest(
        build_plugin(tmp_path, module_name, "def run(req):\n    return {}\n")
    )
    request = make_request(manifest)
    response = make_response(manifest)
    code = f"RESPONSE = {response!r}\n\n\ndef run(req):\n    return RESPONSE\n"
    (tmp_path / "plugin" / f"{module_name}.py").write_text(code, encoding="utf-8")

    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(request)))
    exit_code = main([str(tmp_path / "plugin")])
    captured = capsys.readouterr()
    assert exit_code == 0
    written = json.loads(captured.out)
    assert written["status"] == "ok"
    assert validate_response(written, manifest, request) == []


def test_to_document_omits_none_and_converts_enums() -> None:
    result = Result(
        contract_version="1.0",
        inferencer=InferencerRef(name="ambient-inference/unknown", version="0.0.1"),
        status=Status.ERROR,
        complete=True,
        candidates=[],
        residuals=[],
        referenced_data_versions=[],
        determinism=Determinism.UNKNOWN,
        diagnostics=[],
        timings=Timings(wall_ms=0, cpu_ms=0),
        error=ContractError(
            code=ErrorCode.INTERNAL_ERROR,
            message="failed",
            retryable=False,
        ),
    )
    document = to_document(result)
    assert document["status"] == "error"
    assert document["determinism"] == "unknown"
    assert document["error"]["code"] == "internal_error"
    assert "detail" not in document["error"]
