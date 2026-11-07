"""Request and response contract validation tests."""

import copy

import pytest

from conftest import make_abstained_response, make_request, make_response
from phaino_sdk import (
    Manifest,
    Violation,
    validate_request,
    validate_response,
)


def paths(problems: list[Violation]) -> list[str]:
    return [problem.path for problem in problems]


def test_valid_request_and_response_are_accepted(
    manifest: Manifest, request_doc: dict, response_doc: dict
) -> None:
    assert validate_request(request_doc, manifest) == []
    assert validate_response(response_doc, manifest, request_doc) == []


def test_request_rejects_bad_ids_and_unknown_fields(
    manifest: Manifest, request_doc: dict
) -> None:
    broken = copy.deepcopy(request_doc)
    broken["run_id"] = "obs_0000000000000001"
    broken["unknown_field"] = True
    problems = validate_request(broken, manifest)
    assert "$.run_id" in paths(problems)
    assert "$" in paths(problems)


def test_request_rejects_degenerate_region_and_window(
    manifest: Manifest, request_doc: dict
) -> None:
    broken = copy.deepcopy(request_doc)
    broken["hypothesis_query"]["region"] = {
        "kind": "bbox",
        "payload": {"min_lon": -1.0, "min_lat": 51.0, "max_lon": -1.0, "max_lat": 51.5},
    }
    broken["hypothesis_query"]["time"]["end"] = broken["hypothesis_query"]["time"]["start"]
    problems = validate_request(broken, manifest)
    assert any("region" in problem.path for problem in problems)
    assert any("time" in problem.path for problem in problems)


def test_request_rejects_missing_budget_field(
    manifest: Manifest, request_doc: dict
) -> None:
    broken = copy.deepcopy(request_doc)
    del broken["budget"]["cpu_ms"]
    problems = validate_request(broken, manifest)
    assert "$.budget" in paths(problems)


def test_response_rejects_candidate_without_region(
    manifest: Manifest, request_doc: dict, response_doc: dict
) -> None:
    broken = copy.deepcopy(response_doc)
    del broken["candidates"][0]["claim"]["location"]
    problems = validate_response(broken, manifest, request_doc)
    assert any("claim.location" in problem.path for problem in problems)


def test_response_rejects_unnamed_score_semantics(
    manifest: Manifest, request_doc: dict, response_doc: dict
) -> None:
    broken = copy.deepcopy(response_doc)
    broken["candidates"][0]["score"]["semantics"] = "probability"
    problems = validate_response(broken, manifest, request_doc)
    assert any("score.semantics" in problem.path for problem in problems)


def test_response_rejects_score_outside_semantics(
    manifest: Manifest, request_doc: dict, response_doc: dict
) -> None:
    broken = copy.deepcopy(response_doc)
    broken["candidates"][0]["score"]["value"] = 17.0
    problems = validate_response(broken, manifest, request_doc)
    assert any("score.value" in problem.path for problem in problems)


def test_response_rejects_ids_outside_evidence_scope(
    manifest: Manifest, request_doc: dict, response_doc: dict
) -> None:
    broken = copy.deepcopy(response_doc)
    broken["candidates"][0]["supporting_evidence_ids"] = ["ftr_0000000000000009"]
    problems = validate_response(broken, manifest, request_doc)
    assert any("supporting_evidence_ids" in problem.path for problem in problems)


def test_response_rejects_residual_outside_constraint_refs(
    manifest: Manifest, request_doc: dict, response_doc: dict
) -> None:
    broken = copy.deepcopy(response_doc)
    broken["candidates"][0]["constraint_residuals"][0]["constraint_id"] = (
        "con_0000000000000009"
    )
    problems = validate_response(broken, manifest, request_doc)
    assert any("constraint_residuals" in problem.path for problem in problems)


def test_ok_response_must_have_candidates(
    manifest: Manifest, request_doc: dict, response_doc: dict
) -> None:
    broken = copy.deepcopy(response_doc)
    broken["candidates"] = []
    problems = validate_response(broken, manifest, request_doc)
    assert any("candidates" in problem.path for problem in problems)


def test_abstained_response_requires_a_valid_reason(
    manifest: Manifest, request_doc: dict
) -> None:
    abstained = make_abstained_response(manifest)
    assert validate_response(abstained, manifest, request_doc) == []

    missing_reason = make_abstained_response(manifest)
    del missing_reason["abstain_reason"]
    assert any(
        "abstain_reason" in problem.path
        for problem in validate_response(missing_reason, manifest, request_doc)
    )

    bad_reason = make_abstained_response(manifest)
    bad_reason["abstain_reason"] = "maybe_later"
    assert any(
        "abstain_reason" in problem.path
        for problem in validate_response(bad_reason, manifest, request_doc)
    )

    with_candidates = make_abstained_response(manifest)
    with_candidates["candidates"] = copy.deepcopy(make_response(manifest)["candidates"])
    assert any(
        "candidates" in problem.path
        for problem in validate_response(with_candidates, manifest, request_doc)
    )


def test_abstain_reason_is_forbidden_for_ok_and_error_responses(
    manifest: Manifest, request_doc: dict, response_doc: dict
) -> None:
    ok_with_reason = copy.deepcopy(response_doc)
    ok_with_reason["abstain_reason"] = "insufficient_evidence"
    assert any(
        "abstain_reason" in problem.path
        for problem in validate_response(ok_with_reason, manifest, request_doc)
    )

    error_doc = copy.deepcopy(response_doc)
    error_doc["status"] = "error"
    error_doc["candidates"] = []
    error_doc["error"] = {
        "code": "internal_error",
        "message": "plugin failed",
        "retryable": True,
    }
    error_doc["abstain_reason"] = "budget_exhausted"
    assert any(
        "abstain_reason" in problem.path
        for problem in validate_response(error_doc, manifest, request_doc)
    )


def test_error_response_shape(
    manifest: Manifest, request_doc: dict, response_doc: dict
) -> None:
    error_doc = copy.deepcopy(response_doc)
    error_doc["status"] = "error"
    error_doc["candidates"] = []
    error_doc["error"] = {
        "code": "internal_error",
        "message": "plugin failed",
        "retryable": True,
    }
    assert validate_response(error_doc, manifest, request_doc) == []

    missing_error = copy.deepcopy(error_doc)
    del missing_error["error"]
    assert any(
        "error" in problem.path
        for problem in validate_response(missing_error, manifest, request_doc)
    )

    with_candidates = copy.deepcopy(error_doc)
    with_candidates["candidates"] = copy.deepcopy(response_doc["candidates"])
    assert any(
        "candidates" in problem.path
        for problem in validate_response(with_candidates, manifest, request_doc)
    )


def test_response_echo_and_determinism_are_checked(
    manifest: Manifest, request_doc: dict, response_doc: dict
) -> None:
    broken = copy.deepcopy(response_doc)
    broken["inferencer"]["version"] = "9.9.9"
    broken["determinism"] = "nondeterministic"
    problems = validate_response(broken, manifest, request_doc)
    assert any("inferencer.version" in problem.path for problem in problems)
    assert any("determinism" in problem.path for problem in problems)


def test_response_rejects_unknown_top_level_field(
    manifest: Manifest, request_doc: dict, response_doc: dict
) -> None:
    broken = dict(response_doc)
    broken["surprise"] = 1
    assert any(
        problem.path == "$"
        for problem in validate_response(broken, manifest, request_doc)
    )


def test_bare_point_region_is_rejected(
    manifest: Manifest, request_doc: dict, response_doc: dict
) -> None:
    broken = copy.deepcopy(response_doc)
    broken["candidates"][0]["claim"]["location"] = {
        "kind": "point",
        "payload": {"lat": 51.2, "lon": -1.4},
    }
    problems = validate_response(broken, manifest, request_doc)
    assert any("location.kind" in problem.path for problem in problems)


def test_builder_documents_match_validators(manifest: Manifest) -> None:
    request = make_request(manifest)
    response = make_response(manifest)
    assert validate_request(request, manifest) == []
    assert validate_response(response, manifest, request) == []
