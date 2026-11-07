"""JSON entry point for PhainoWeave inferencer plugins (inferencer contract §11).

The host writes one request JSON document to stdin and reads one response JSON document
from stdout. Failures are emitted as contract error responses rather than stack traces.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

from .contract import (
    CONTRACT_VERSION,
    Determinism,
    ErrorCode,
    Result,
    Status,
    to_document,
)
from .manifest import Manifest, ManifestError, load_manifest
from .validate import Violation, validate_request, validate_response


def run_plugin(plugin_dir: str | Path, request: Mapping[str, Any]) -> dict[str, Any]:
    """Loads the plugin, runs it, validates the response, and returns a response document."""
    try:
        manifest = load_manifest(plugin_dir)
    except ManifestError as error:
        return _error_response(None, request, ErrorCode.INVALID_REQUEST, str(error))

    problems = validate_request(request, manifest)
    if problems:
        return _error_response(
            manifest,
            request,
            ErrorCode.INVALID_REQUEST,
            "request violates the inferencer contract",
            detail={"violations": _violations_document(problems)},
        )

    try:
        plugin = load_plugin(manifest, plugin_dir)
        raw_result = _invoke(plugin, request)
        response = _response_document(raw_result)
    except Exception as error:  # noqa: BLE001 - plugin boundary must not leak stack traces
        return _error_response(
            manifest,
            request,
            ErrorCode.INTERNAL_ERROR,
            f"{type(error).__name__}: {error}",
        )

    problems = validate_response(response, manifest, request)
    if problems:
        return _error_response(
            manifest,
            request,
            ErrorCode.INTERNAL_ERROR,
            "response violates the inferencer contract",
            detail={"violations": _violations_document(problems)},
        )
    return response


def load_plugin(manifest: Manifest, plugin_dir: str | Path) -> Any:
    """Imports the plugin entrypoint from `plugin_dir`."""
    module_name, _, attribute = manifest.entrypoint.partition(":")
    resolved = str(Path(plugin_dir).resolve())
    if resolved not in sys.path:
        sys.path.insert(0, resolved)
    importlib.invalidate_caches()
    module = importlib.import_module(module_name)
    target = getattr(module, attribute)
    if isinstance(target, type):
        target = target()
    return target


def main(argv: list[str] | None = None) -> int:
    """Reads one request from stdin, writes one response to stdout."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        response = _error_response(
            None,
            {},
            ErrorCode.INVALID_REQUEST,
            "usage: python -m phaino_sdk.runner <plugin_dir>",
        )
    else:
        plugin_dir = arguments[0]
        raw_request = sys.stdin.read()
        try:
            request = json.loads(raw_request)
        except json.JSONDecodeError as error:
            response = _error_response(
                None,
                {},
                ErrorCode.INVALID_REQUEST,
                f"request is not valid JSON: {error}",
            )
        else:
            if not isinstance(request, Mapping):
                response = _error_response(
                    None,
                    {},
                    ErrorCode.INVALID_REQUEST,
                    "request must be a JSON object",
                )
            else:
                response = run_plugin(plugin_dir, request)
    sys.stdout.write(json.dumps(response, separators=(",", ":"), sort_keys=True))
    sys.stdout.write("\n")
    return 0


def _invoke(plugin: Any, request: Mapping[str, Any]) -> Any:
    runner: Callable[[Mapping[str, Any]], Any] = (
        plugin.run if hasattr(plugin, "run") else plugin
    )
    return runner(request)


def _response_document(result: Any) -> dict[str, Any]:
    if isinstance(result, Result):
        return to_document(result)
    if isinstance(result, Mapping):
        return dict(result)
    raise TypeError("plugin run() must return phaino_sdk.Result or a response mapping")


def _error_response(
    manifest: Manifest | None,
    request: Mapping[str, Any],
    code: ErrorCode,
    message: str,
    retryable: bool = False,
    detail: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    request_inferencer = request.get("inferencer")
    if manifest is not None:
        inferencer = {"name": manifest.name, "version": manifest.version}
        determinism = manifest.determinism.value
        contract_version = manifest.contract_version
    else:
        inferencer = (
            dict(request_inferencer)
            if isinstance(request_inferencer, Mapping)
            else {"name": "unknown/invalid", "version": "0.0.0"}
        )
        determinism = Determinism.UNKNOWN.value
        contract_version = str(request.get("contract_version", CONTRACT_VERSION))
    error: dict[str, Any] = {
        "code": code.value,
        "message": message,
        "retryable": retryable,
    }
    if detail is not None:
        error["detail"] = dict(detail)
    return {
        "contract_version": contract_version,
        "inferencer": inferencer,
        "status": Status.ERROR.value,
        "complete": True,
        "candidates": [],
        "residuals": [],
        "referenced_data_versions": [],
        "determinism": determinism,
        "diagnostics": [],
        "timings": {"wall_ms": 0, "cpu_ms": 0},
        "error": error,
    }


def _violations_document(problems: list[Violation]) -> list[dict[str, str]]:
    return [{"path": problem.path, "message": problem.message} for problem in problems]


if __name__ == "__main__":
    raise SystemExit(main())
