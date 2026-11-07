"""Tests for the independent C2 repair paired evaluator."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from phaino_c2_eval import (
    ArtifactError,
    candidate_metrics,
    claim_integrity,
    evaluate,
    load_artifact,
    load_artifacts,
    main,
    negative_result,
    paired_comparison,
    paired_tables,
    paired_wald_interval,
    select_candidates,
)
from phaino_c2_eval.evaluate import cross_environment
from phaino_c2_eval.report import report_json, report_markdown

ALLOWED_CLAIMS = {
    "v": "supported_conditional",
    "f0_times_b": "supported_conditional",
    "t0": "contradicted",
}


def make_candidate(
    decision: str = "accept",
    adequacy_status: str = "adequate",
    reason_codes: tuple[str, ...] = (),
    claim_statuses: dict | None = None,
    validly_supported: bool | None = None,
) -> dict:
    record = {
        "adequacy_status": adequacy_status,
        "reason_codes": list(reason_codes),
        "decision": decision,
        "claim_statuses": dict(claim_statuses or ALLOWED_CLAIMS),
        "params": {"f0": 500.0, "v": 250.0, "t0": 20.0, "b": 3000.0},
    }
    if validly_supported is not None:
        record["validly_supported"] = validly_supported
    return record


def make_trial(
    condition: str,
    mechanism: str,
    seed: int,
    geometry_m: float,
    *,
    truth_within_tolerance: bool = True,
    decisions: dict | None = None,
    candidate_records: dict | None = None,
    estimated_chirp_rate: float | None = None,
    estimated_snr_db: float | None = 20.0,
) -> dict:
    if candidate_records is None:
        decisions = decisions or {}
        candidate_records = {
            candidate: make_candidate(**decisions.get(candidate, {}))
            for candidate in ("B0", "B1", "B2", "B3")
        }
    return {
        "condition": condition,
        "mechanism": mechanism,
        "seed": seed,
        "stratum": "test",
        "evaluation_only": {
            "scenario": {
                "f0": 500.0,
                "v": 250.0,
                "t0": 20.0,
                "b": 3000.0,
                "accel": 0.0 if mechanism == "correct_cv" else 0.4,
                "snr_db": 20.0,
                "geometry_m": geometry_m,
            },
            "estimate_within_tolerance": {
                "v": truth_within_tolerance,
                "f0_times_b": truth_within_tolerance,
                "t0": truth_within_tolerance,
            },
        },
        "observation": {"source": "front_end", "snr_db": 20.0},
        "estimated_chirp_rate": (
            estimated_chirp_rate
            if estimated_chirp_rate is not None
            else (0.2 if mechanism in {"acceleration", "high_chirp"} else 0.02)
        ),
        "estimated_snr_db": estimated_snr_db,
        "candidates": candidate_records,
    }


def make_artifact(
    trials: list[dict],
    *,
    protocol_digest: str = "protocol-1",
    grid_id: str = "grid-1",
    frozen_grid_digest: str = "frozen-grid-1",
    candidates: tuple[str, ...] = ("B0", "B1", "B2", "B3"),
    primary_endpoint: dict | None = None,
    detection_loss_bound: float = 0.05,
    undecided_policy: str = "not_detected",
    chirp_bins: list | None = None,
    snr_bins: list | None = None,
) -> dict:
    return {
        "experiment": "c2-repair",
        "protocol_digest": protocol_digest,
        "grid_id": grid_id,
        "frozen_grid_digest": frozen_grid_digest,
        "candidates": list(candidates),
        "primary_endpoint": primary_endpoint
        or {
            "name": "supported-coverage-and-detection",
            "definition": "B1 vs B0: supported coverage and acceleration discrepancy detection",
            "candidate_comparison": "B1 vs B0",
            "decision_rule": "B1 must reduce FRR and preserve discrepancy detection",
            "detection_non_inferiority_rule": "detection delta >= -0.05",
        },
        "detection_loss_bound": detection_loss_bound,
        "undecided_policy": undecided_policy,
        "chirp_bins": chirp_bins
        if chirp_bins is not None
        else [
            {"bin_id": "low", "lower": 0.0, "upper": 0.03},
            {"bin_id": "mid", "lower": 0.03, "upper": 0.1},
            {"bin_id": "high", "lower": 0.1, "upper": None},
        ],
        "snr_bins": snr_bins
        if snr_bins is not None
        else [{"bin_id": "snr20", "lower": 18.0, "upper": 22.0, "n_samples": 5}],
        "trials": trials,
    }


def write_artifact(path: Path, document: dict) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def base_trials() -> list[dict]:
    return [
        make_trial(
            "cv150",
            "correct_cv",
            1,
            150.0,
            decisions={
                "B0": {"decision": "reject", "adequacy_status": "discrepancy"},
                "B1": {"decision": "accept"},
                "B2": {"decision": "undetermined", "reason_codes": ("insufficient_support",)},
                "B3": {"decision": "accept"},
            },
        ),
        make_trial(
            "cv600",
            "correct_cv",
            2,
            600.0,
            decisions={
                "B0": {"decision": "reject", "adequacy_status": "discrepancy"},
                "B1": {"decision": "accept"},
                "B2": {"decision": "undetermined", "reason_codes": ("insufficient_support",)},
                "B3": {"decision": "accept"},
            },
        ),
        make_trial(
            "cv3000",
            "correct_cv",
            3,
            3000.0,
            decisions={
                "B0": {"decision": "accept"},
                "B1": {"decision": "accept"},
                "B2": {"decision": "undetermined", "reason_codes": ("weak_snr",)},
                "B3": {"decision": "accept"},
            },
        ),
        make_trial(
            "accel",
            "acceleration",
            4,
            600.0,
            truth_within_tolerance=False,
            decisions={
                "B0": {"decision": "reject", "adequacy_status": "discrepancy"},
                "B1": {"decision": "reject", "adequacy_status": "discrepancy"},
                "B2": {"decision": "reject", "adequacy_status": "discrepancy"},
                "B3": {"decision": "accept"},
            },
        ),
        make_trial(
            "chirp",
            "high_chirp",
            5,
            150.0,
            decisions={
                "B0": {"decision": "reject", "adequacy_status": "discrepancy"},
                "B1": {"decision": "accept"},
                "B2": {"decision": "undetermined", "reason_codes": ("insufficient_support",)},
                "B3": {"decision": "accept"},
            },
        ),
    ]


def base_artifact() -> dict:
    return make_artifact(base_trials())


def test_loader_accepts_contract(tmp_path: Path) -> None:
    path = write_artifact(tmp_path / "artifact.json", base_artifact())
    artifact = load_artifact(path)
    assert artifact.experiment == "c2-repair"
    assert artifact.candidates == ("B0", "B1", "B2", "B3")
    assert len(artifact.trials) == 5
    assert artifact.sha256


def test_duplicate_trial_rejected(tmp_path: Path) -> None:
    document = base_artifact()
    document["trials"].append(copy.deepcopy(document["trials"][0]))
    path = write_artifact(tmp_path / "artifact.json", document)
    with pytest.raises(ArtifactError):
        load_artifact(path)


def test_missing_truth_rejected(tmp_path: Path) -> None:
    document = base_artifact()
    del document["trials"][0]["evaluation_only"]["scenario"]["geometry_m"]
    path = write_artifact(tmp_path / "artifact.json", document)
    with pytest.raises(ArtifactError):
        load_artifact(path)


def test_missing_candidate_rejected(tmp_path: Path) -> None:
    document = base_artifact()
    del document["trials"][0]["candidates"]["B1"]
    path = write_artifact(tmp_path / "artifact.json", document)
    with pytest.raises(ArtifactError):
        load_artifact(path)


def test_nonfinite_numbers_rejected(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    document = base_artifact()
    document["trials"][0]["candidates"]["B0"]["params"]["f0"] = float("nan")
    # json.dumps emits NaN by default; the strict parser must reject it.
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ArtifactError):
        load_artifact(path)


def test_cross_environment_digest_mismatch_rejected(tmp_path: Path) -> None:
    first = write_artifact(tmp_path / "a.json", base_artifact())
    second = write_artifact(
        tmp_path / "b.json",
        make_artifact(base_trials(), protocol_digest="different"),
    )
    with pytest.raises(ArtifactError):
        load_artifacts([first, second])


def test_require_paired_rejects_missing_trial(tmp_path: Path) -> None:
    first = write_artifact(tmp_path / "a.json", base_artifact())
    short = make_artifact(base_trials()[:-1])
    second = write_artifact(tmp_path / "b.json", short)
    # Without require_paired the artifacts load; missing trials are reported later.
    load_artifacts([first, second])
    with pytest.raises(ArtifactError):
        load_artifacts([first, second], require_paired=True)


def test_paired_discordant_math_matches_hand_computation() -> None:
    # B0 events: T,T,F,F ; B1 events: T,F,T,F.
    trials = []
    for index, (b0_event, b1_event) in enumerate(
        [(True, True), (True, False), (False, True), (False, False)]
    ):
        decisions = {
            "B0": (
                {"decision": "reject", "adequacy_status": "discrepancy"}
                if b0_event
                else {"decision": "accept"}
            ),
            "B1": (
                {"decision": "reject", "adequacy_status": "discrepancy"}
                if b1_event
                else {"decision": "accept"}
            ),
        }
        trials.append(
            make_trial(
                f"cv{index}",
                "correct_cv",
                index,
                600.0,
                decisions=decisions,
            )
        )
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2-paired-math.json"), make_artifact(trials))
    )
    # Override B2/B3 so only the paired B0/B1 event structure matters.
    result = paired_comparison(artifact.trials, "B0", "B1", "false_rejection")
    assert result["n_pairs"] == 4
    assert result["counts"] == {
        "both": 1,
        "baseline_only": 1,
        "candidate_only": 1,
        "neither": 1,
    }
    assert result["baseline_rate"] == pytest.approx(0.5)
    assert result["candidate_rate"] == pytest.approx(0.5)
    assert result["risk_difference"] == pytest.approx(0.0)
    variance = (1 + 1) / 16.0
    half = 1.959963984540054 * variance**0.5
    assert result["risk_difference_interval"] == pytest.approx([-half, half])


def test_paired_interval_sanity() -> None:
    assert paired_wald_interval(0, 0, 10) == pytest.approx((0.0, 0.0))
    assert paired_wald_interval(0, 0, 0) is None
    lower, upper = paired_wald_interval(8, 1, 20)
    assert -1.0 <= lower <= upper <= 1.0
    assert lower > 0.0


def test_clean_improvement_and_negative_result() -> None:
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2-clean.json"), base_artifact())
    )
    document = evaluate([artifact], artifact.candidates, require_paired=False)
    paired = document["paired"]["B1"]["overall"]
    assert paired["false_rejection"]["risk_difference"] < 0.0
    assert paired["false_rejection"]["risk_difference_interval"][1] < 0.0
    assert paired["detection"]["risk_difference"] == pytest.approx(0.0)
    assert "B1" in document["negative_result"]["qualifying_candidates"]
    assert document["negative_result"]["negative_result_holds"] is False


def test_detection_loss_reported() -> None:
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2-detection-loss.json"), base_artifact())
    )
    document = evaluate([artifact], artifact.candidates, require_paired=False)
    paired = document["paired"]["B1"]
    # The base fixture keeps detection for B1; B3 loses it.
    assert document["paired"]["B3"]["overall"]["detection"]["risk_difference"] < 0.0
    assert "B3" in document["negative_result"]["detection_loss_candidates"]


def test_abstention_gaming_is_flagged() -> None:
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2-abstention.json"), base_artifact())
    )
    document = evaluate([artifact], artifact.candidates, require_paired=False)
    details = document["negative_result"]["details"]["B2"]
    assert details["frr_gain"] is True
    assert details["correct_accepted_delta"] < 0
    assert details["abstention_gaming"] is True
    assert details["qualifies"] is False
    assert "B2" in document["negative_result"]["abstention_gaming_candidates"]
    assert "B2" not in document["negative_result"]["qualifying_candidates"]


def test_negative_result_holds_explicitly() -> None:
    trials = base_trials()
    # B1: FRR improvement but detection loss.
    trials[3]["candidates"]["B1"] = make_candidate(decision="accept")
    # B2: no FRR gain (same rejection as B0 on correct-CV) and no abstention increase.
    for trial in trials[:3]:
        trial["candidates"]["B2"] = make_candidate(decision="reject", adequacy_status="discrepancy")
    # B3: detection loss and no FRR improvement.
    trials[3]["candidates"]["B3"] = make_candidate(decision="accept")
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2-negative.json"), make_artifact(trials))
    )
    document = evaluate([artifact], artifact.candidates, require_paired=False)
    assert document["negative_result"]["negative_result_holds"] is True
    assert document["negative_result"]["qualifying_candidates"] == []
    assert "No candidate improves" in document["negative_result"]["statement"]


def test_claim_integrity_flags_without_rewriting() -> None:
    trials = base_trials()
    trials[0]["candidates"]["B2"]["claim_statuses"]["v"] = "supported_invariant"
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2-integrity.json"), make_artifact(trials))
    )
    integrity = claim_integrity(artifact.trials, "B2")
    assert integrity["status"] == "violations"
    assert integrity["n_violations"] == 1
    assert integrity["supported_invariant_count"] == 1
    assert integrity["violations"][0]["claim"] == "v"
    # The candidate's stored claim status is untouched (flagged, not silently accepted).
    assert artifact.trials[0].candidates["B2"].claim_statuses["v"] == "supported_invariant"


def test_mechanism_and_geometry_strata_are_present() -> None:
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2-strata.json"), base_artifact())
    )
    metrics = candidate_metrics(artifact.trials, "B1")
    assert "correct_cv" in metrics["by_mechanism"]
    assert "acceleration" in metrics["by_mechanism"]
    assert "high_chirp" in metrics["by_mechanism"]
    paired = paired_tables(artifact.trials, "B0", "B1")
    assert set(paired["by_mechanism"]) == {"acceleration", "correct_cv", "high_chirp"}
    assert "[0,200)" in paired["by_geometry"]
    assert "[400,800)" in paired["by_geometry"]
    assert "[1600,3200)" in paired["by_geometry"]


def test_reason_breakdown_and_decision_counts() -> None:
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2-reasons.json"), base_artifact())
    )
    metrics = candidate_metrics(artifact.trials, "B2")
    assert metrics["decision_counts"]["undetermined"] == 4
    assert metrics["reason_breakdown"]["undetermined"]["insufficient_support"] == 3
    assert metrics["reason_breakdown"]["undetermined"]["weak_snr"] == 1


def test_cross_environment_claim_differences_are_reported(tmp_path: Path) -> None:
    first_document = base_artifact()
    second_document = copy.deepcopy(first_document)
    second_document["trials"][1]["candidates"]["B1"]["claim_statuses"]["v"] = "contradicted"
    first = write_artifact(tmp_path / "env-a.json", first_document)
    second = write_artifact(tmp_path / "env-b.json", second_document)
    artifacts = load_artifacts([first, second])
    document = evaluate(artifacts, artifacts[0].candidates, require_paired=True)
    entry = next(
        entry
        for entry in document["cross_environment"]["claim_status_agreement"]
        if entry["candidate"] == "B1" and entry["claim"] == "v"
    )
    assert entry["n_trials_compared"] == 5
    assert entry["disagree"] == 1
    assert entry["differences"][0]["condition"] == "cv600"
    assert "env0" in entry["differences"][0]["statuses"]
    assert document["validation"]["digest_consistency"]["protocol_digest"] is True


def test_candidate_selection_and_cli_determinism(tmp_path: Path) -> None:
    path = write_artifact(tmp_path / "artifact.json", base_artifact())
    artifact = load_artifact(path)
    assert select_candidates(artifact, ("B0", "B1")) == ("B0", "B1")
    with pytest.raises(ValueError):
        select_candidates(artifact, ("B1",))
    out = tmp_path / "report.json"
    markdown = tmp_path / "report.md"
    argv = [
        "--artifact",
        str(path),
        "--candidates",
        "B0,B1",
        "--out",
        str(out),
        "--markdown",
        str(markdown),
    ]
    assert main(argv) == 0
    first = out.read_bytes()
    first_markdown = markdown.read_bytes()
    assert main(argv) == 0
    assert out.read_bytes() == first
    assert markdown.read_bytes() == first_markdown
    document = json.loads(first)
    assert document["evaluation"]["selected_candidates"] == ["B0", "B1"]
    assert "B2" not in document["paired"]
    text = markdown.read_text()
    assert "Per-candidate summary" in text
    assert "Per-mechanism paired differences" in text
    assert "Per-geometry continuum paired differences" in text
    assert "Claim integrity" in text
    assert "Cross-environment claim-status agreement" in text
    assert "Negative-result statement" in text
    assert "Limitations" in text


def test_cli_rejects_bad_artifact(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"experiment":"c2-repair"}', encoding="utf-8")
    assert (
        main(
            [
                "--artifact",
                str(bad),
                "--out",
                str(tmp_path / "report.json"),
                "--markdown",
                str(tmp_path / "report.md"),
            ]
        )
        == 2
    )


def test_report_json_is_deterministic() -> None:
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2-deterministic.json"), base_artifact())
    )
    first = evaluate([artifact], artifact.candidates, require_paired=False)
    second = evaluate([artifact], artifact.candidates, require_paired=False)
    assert report_json(first) == report_json(second)
    assert report_markdown(first) == report_markdown(second)


def test_cross_environment_presence_without_require_paired() -> None:
    artifact_a = load_artifact(
        write_artifact(Path("/tmp/c2-presence-a.json"), base_artifact())
    )
    short_document = make_artifact(base_trials()[:-1])
    artifact_b = load_artifact(
        write_artifact(Path("/tmp/c2-presence-b.json"), short_document)
    )
    cross = cross_environment([artifact_a, artifact_b], artifact_a.candidates)
    assert cross["trial_presence"][1]["missing_trial_count_vs_union"] == 1
    entry = next(
        item
        for item in cross["claim_status_agreement"]
        if item["candidate"] == "B1" and item["claim"] == "v"
    )
    assert entry["missing"] == 1


# ---------------------------------------------------------------------------
# ADR 0023 outcome taxonomy, coverage, chirp power, and primary endpoint
# ---------------------------------------------------------------------------

def test_supported_coverage_is_explicit_claim_gated_not_adequacy_accept() -> None:
    trials = [
        make_trial(
            "cv-supported",
            "correct_cv",
            1,
            600.0,
            decisions={"B1": {"decision": "accept"}},
        ),
        make_trial(
            "cv-rejected",
            "correct_cv",
            2,
            600.0,
            decisions={"B1": {"decision": "reject", "adequacy_status": "discrepancy"}},
        ),
        make_trial(
            "cv-wrong",
            "correct_cv",
            3,
            600.0,
            truth_within_tolerance=False,
            decisions={"B1": {"decision": "accept"}},
        ),
    ]
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2-coverage.json"), make_artifact(trials))
    )
    coverage = candidate_metrics(artifact.trials, "B1")["supported_coverage"]
    assert coverage["denominator"] == 3
    assert coverage["numerator"] == 1
    assert coverage["rate"] == pytest.approx(1.0 / 3.0)
    assert coverage["support_basis_counts"] == {"claim_statuses_gate": 3}
    assert coverage["wilson_95"] is not None

    trials[0]["candidates"]["B1"]["validly_supported"] = False
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2-coverage-explicit.json"), make_artifact(trials))
    )
    coverage = candidate_metrics(artifact.trials, "B1")["supported_coverage"]
    assert coverage["numerator"] == 0
    assert coverage["support_basis_counts"]["explicit_field"] == 1


def test_misspecification_taxonomy_and_abstention_not_detection() -> None:
    trials = [
        make_trial(
            "acc-detected",
            "acceleration",
            1,
            600.0,
            truth_within_tolerance=False,
            decisions={
                "B0": {"decision": "reject", "adequacy_status": "discrepancy"},
                "B1": {"decision": "reject", "adequacy_status": "discrepancy"},
            },
        ),
        make_trial(
            "acc-undetermined",
            "acceleration",
            2,
            600.0,
            truth_within_tolerance=False,
            decisions={
                "B0": {"decision": "reject", "adequacy_status": "discrepancy"},
                "B1": {"decision": "undetermined", "reason_codes": ("insufficient_support",)},
            },
        ),
        make_trial(
            "acc-false-supported",
            "acceleration",
            3,
            600.0,
            truth_within_tolerance=False,
            decisions={
                "B0": {"decision": "reject", "adequacy_status": "discrepancy"},
                "B1": {"decision": "accept"},
            },
        ),
        make_trial(
            "acc-rejected-other",
            "acceleration",
            4,
            600.0,
            truth_within_tolerance=False,
            decisions={
                "B0": {"decision": "reject", "adequacy_status": "discrepancy"},
                "B1": {"decision": "reject", "adequacy_status": "adequate"},
            },
        ),
    ]
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2-taxonomy.json"), make_artifact(trials))
    )
    metrics = candidate_metrics(artifact.trials, "B1")
    taxonomy = metrics["misspecification_taxonomy"]
    assert taxonomy["denominator"] == 4
    assert taxonomy["categories"]["discrepancy_detected"]["count"] == 1
    assert taxonomy["categories"]["undetermined"]["count"] == 1
    assert taxonomy["categories"]["false_supported"]["count"] == 1
    assert taxonomy["categories"]["rejected_without_discrepancy"]["count"] == 1
    pair = paired_comparison(
        artifact.trials, "B0", "B1", "discrepancy_detection", undecided_policy="not_detected"
    )
    assert pair["counts"] == {
        "both": 1,
        "baseline_only": 3,
        "candidate_only": 0,
        "neither": 0,
    }
    assert pair["risk_difference"] == pytest.approx(-0.75)
    # Safe abstention is not detection: the undetermined trial is neither event.
    assert pair["n_pairs"] == 4


def test_null_noise_only_false_supported_counts() -> None:
    trials = [
        make_trial(
            "noise-only",
            "noise",
            1,
            600.0,
            truth_within_tolerance=False,
            decisions={"B1": {"decision": "accept"}},
        )
    ]
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2-null.json"), make_artifact(trials))
    )
    null = candidate_metrics(artifact.trials, "B1")["null_noise_only"]
    assert null["n_trials"] == 1
    assert null["false_supported"] == 1
    assert null["false_supported_rate"] == pytest.approx(1.0)
    assert null["false_supported_wilson_95"] is not None


def test_chirp_power_bins_and_missing_acceleration_are_flagged() -> None:
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2-chirp.json"), base_artifact())
    )
    chirp = evaluate([artifact], artifact.candidates, require_paired=False)["chirp_power"]
    assert chirp["declared"] is True
    assert set(chirp["bins_without_acceleration"]) == {"low", "mid"}
    high = next(item for item in chirp["bins"] if item["bin_id"] == "high")
    assert high["n_acceleration"] == 1
    assert high["no_acceleration_samples"] is False
    assert high["paired"]["B1"]["cv_false_rejection"]["n_pairs"] == 0
    assert high["paired"]["B1"]["acceleration_detection"]["n_pairs"] == 1


def test_snr_conditioning_flag_false_unless_multiple_sampled_bins() -> None:
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2-snr-false.json"), base_artifact())
    )
    document = evaluate([artifact], artifact.candidates, require_paired=False)
    assert document["snr_conditioning"]["snr_conditioning_verified"] is False
    assert document["snr_conditioning"]["snr_branch"] == "unverified"

    document_with_two = make_artifact(
        base_trials(),
        snr_bins=[
            {"bin_id": "low-snr", "lower": 0.0, "upper": 20.0, "n_samples": 10},
            {"bin_id": "high-snr", "lower": 20.0, "upper": None, "n_samples": 10},
        ],
    )
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2-snr-true.json"), document_with_two)
    )
    result = evaluate([artifact], artifact.candidates, require_paired=False)
    assert result["snr_conditioning"]["snr_conditioning_verified"] is True
    assert result["snr_conditioning"]["snr_branch"] == "verified"


def test_primary_endpoint_is_required_and_evaluated() -> None:
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2-primary.json"), base_artifact())
    )
    document = evaluate([artifact], artifact.candidates, require_paired=False)
    primary = document["primary_endpoint"]
    assert primary["name"] == "supported-coverage-and-detection"
    assert primary["candidate"] == "B1"
    assert primary["baseline"] == "B0"
    assert primary["primary_result"] == "pass"
    assert primary["primary_metric"] == "supported_coverage"
    assert primary["criteria"]["primary_improved"] is True
    assert primary["criteria"]["detection_non_inferior"] is True
    assert primary["detection"]["metric"] == "discrepancy_detected"
    assert primary["sensitivity"]["policy"] == "excluded"

    missing = base_artifact()
    del missing["primary_endpoint"]
    path = write_artifact(Path("/tmp/c2-primary-missing.json"), missing)
    with pytest.raises(ArtifactError):
        load_artifact(path)

    bad_pair = base_artifact()
    bad_pair["primary_endpoint"]["candidate_comparison"] = "B9 vs B0"
    path = write_artifact(Path("/tmp/c2-primary-badpair.json"), bad_pair)
    with pytest.raises(ArtifactError):
        load_artifact(path)


def test_undecided_policy_changes_primary_and_sensitivity() -> None:
    trials = [
        make_trial(
            "acc-undetermined",
            "acceleration",
            1,
            600.0,
            truth_within_tolerance=False,
            decisions={
                "B0": {"decision": "reject", "adequacy_status": "discrepancy"},
                "B1": {"decision": "undetermined", "reason_codes": ("insufficient_support",)},
            },
        ),
        make_trial(
            "acc-detected",
            "acceleration",
            2,
            600.0,
            truth_within_tolerance=False,
            decisions={
                "B0": {"decision": "reject", "adequacy_status": "discrepancy"},
                "B1": {"decision": "reject", "adequacy_status": "discrepancy"},
            },
        ),
        make_trial(
            "cv-improved",
            "correct_cv",
            3,
            600.0,
            decisions={
                "B0": {"decision": "reject", "adequacy_status": "discrepancy"},
                "B1": {"decision": "accept"},
            },
        ),
    ]
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2-undecided.json"), make_artifact(trials))
    )
    document = evaluate([artifact], artifact.candidates, require_paired=False)
    primary = document["primary_endpoint"]
    assert primary["undecided_policy"] == "not_detected"
    assert primary["detection"]["paired"]["n_pairs"] == 2
    assert primary["detection"]["paired"]["risk_difference"] == pytest.approx(-0.5)
    assert primary["primary_result"] == "fail"
    assert primary["sensitivity"]["policy"] == "excluded"
    assert primary["sensitivity"]["criteria"]["detection_delta"] == pytest.approx(0.0)
    assert primary["sensitivity"]["result"] == "pass"


def test_primary_endpoint_rejects_missing_detection_policy(tmp_path: Path) -> None:
    document = base_artifact()
    del document["undecided_policy"]
    path = write_artifact(tmp_path / "missing-policy.json", document)
    with pytest.raises(ArtifactError):
        load_artifact(path)
    document = base_artifact()
    document["undecided_policy"] = "count_as_detected"
    path = write_artifact(tmp_path / "bad-policy.json", document)
    with pytest.raises(ArtifactError):
        load_artifact(path)


def test_adr0023_report_sections_and_determinism() -> None:
    artifact = load_artifact(
        write_artifact(Path("/tmp/c2-adr23.json"), base_artifact())
    )
    first = evaluate([artifact], artifact.candidates, require_paired=False)
    second = evaluate([artifact], artifact.candidates, require_paired=False)
    assert report_json(first) == report_json(second)
    assert report_markdown(first) == report_markdown(second)
    text = report_markdown(first)
    for heading in (
        "Primary endpoint (pre-declared)",
        "Supported coverage (secondary)",
        "Misspecification taxonomy (secondary)",
        "Null/noise-only promotions (secondary)",
        "Per-chirp-bin power (secondary)",
        "SNR conditioning",
    ):
        assert heading in text
