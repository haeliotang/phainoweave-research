"""Top-level paired evaluation assembly for C2 repair artifacts."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .artifacts import Artifact
from .metrics import (
    candidate_metrics,
    chirp_power,
    claim_integrity,
    negative_result,
    paired_comparison,
    paired_tables,
    snr_conditioning,
)

SCHEMA_VERSION = "1.0.0"
C2_CONTRACT_GAPS = (
    "The c2-repair contract has no `validly_supported` field; the evaluator supports it "
    "but otherwise derives support from claim_statuses plus the C1 gate. The method "
    "should declare support semantics explicitly for a sealed artifact.",
    "The contract has no `primary_metric` field. The evaluator reads the optional "
    "`primary_metric` if present, otherwise infers it from the natural-language "
    "definition/decision rule; the machine-evaluable primary metric should be explicit.",
    "The primary_endpoint fields are natural-language strings. The evaluator prints them "
    "verbatim but can only apply its documented canonical rule (primary metric "
    "improvement plus detection non-inferiority within detection_loss_bound).",
    "`detection_loss_bound` has no declared unit or estimation method (rate difference "
    "versus percentage points); the evaluator treats it as an absolute rate difference.",
    "The artifact contract does not declare the alternative undecided policy for the "
    "sensitivity check; the evaluator uses the other of {not_detected, excluded}.",
    "The contract does not supply `estimated_chirp_rate`, `chirp_bins`, "
    "`estimated_snr_db` or `snr_bins`; per-chirp-bin power and SNR conditioning are "
    "unavailable or unverified when these are absent.",
    "Null/noise-only mechanism labels are not enumerated; the evaluator groups mechanisms "
    "whose lower-case name contains `null` or `noise`.",
    "The misspecification taxonomy is derived from decision + adequacy_status; the "
    "artifact has no explicit taxonomy field or rule id.",
)
C2_LIMITATIONS = (
    "Paired risk differences are descriptive point estimates with a documented paired "
    "Wald 95% interval, not a Newcombe interval and not a hypothesis test. Intervals do "
    "not account for repeated seeds, shared noise realizations beyond the pairing, or "
    "multiple comparisons.",
    "The evaluator consumes artifacts only. It cannot verify that candidates used only "
    "runtime-observable quantities (B3 leakage), that observations were truly identical "
    "across candidates, or that the artifact's protocol was frozen before opening.",
    "Correctness labels come from `evaluation_only.estimate_within_tolerance`; truth is "
    "synthetic truth from the artifact, not physical correctness.",
    "The primary environment is the first supplied artifact. Cross-environment claim "
    "agreement is reported descriptively; equality is never forced and no pooled "
    "cross-environment rate is computed.",
    "FRR is defined only on truth-correct correct-CV cells; acceleration detection only "
    "on acceleration cells. Cells with no eligible trials report null rates, not zero.",
    "The negative-result flag uses point estimates (FRR gain with no point-estimate "
    "detection loss). The paired intervals and stratified tables must be read before any "
    "scientific conclusion; the evaluator makes no candidate recommendation.",
    "Claim integrity uses the C1 gate's currently allowed set "
    "(`supported_conditional`, `undetermined`, `contradicted`). Any `supported_invariant` "
    "or unknown status is flagged but not silently rewritten or accepted.",
    "A `--require-paired` run requires identical candidate lists and trial identities "
    "across environments; without it, missing cells are reported, not imputed.",
)


def evaluate(
    artifacts: Sequence[Artifact],
    selected_candidates: Sequence[str],
    *,
    require_paired: bool,
) -> dict[str, Any]:
    primary = artifacts[0]
    environments: list[dict[str, Any]] = []
    all_metrics: dict[str, dict[str, Any]] = {}
    for index, artifact in enumerate(artifacts):
        metrics = {
            candidate: candidate_metrics(artifact.trials, candidate)
            for candidate in selected_candidates
        }
        paired = {
            candidate: paired_tables(
                artifact.trials, "B0", candidate, artifact.undecided_policy
            )
            for candidate in selected_candidates
            if candidate != "B0"
        }
        integrity = {
            candidate: claim_integrity(artifact.trials, candidate)
            for candidate in selected_candidates
        }
        environment = {
            "environment_id": f"env{index}",
            "source": artifact.path,
            "sha256": artifact.sha256,
            "protocol_digest": artifact.protocol_digest,
            "grid_id": artifact.grid_id,
            "frozen_grid_digest": artifact.frozen_grid_digest,
            "n_trials": len(artifact.trials),
            "candidate_metrics": metrics,
            "paired": paired,
            "claim_integrity": integrity,
        }
        if index == 0:
            negative = negative_result(metrics, paired)
            environment["negative_result"] = negative
        environments.append(environment)
        all_metrics[artifact.path] = metrics
    primary_metrics = environments[0]["candidate_metrics"]
    primary_paired = environments[0]["paired"]
    primary_integrity = environments[0]["claim_integrity"]
    cross = cross_environment(artifacts, selected_candidates)
    primary_endpoint = _primary_endpoint(primary, selected_candidates)
    chirp = chirp_power(primary, selected_candidates)
    snr = snr_conditioning(primary)
    labels = {
        "primary_endpoint": "primary",
        "candidate_metrics": "secondary",
        "paired_overall": "secondary",
        "paired_by_mechanism": "secondary",
        "paired_by_geometry": "secondary",
        "supported_coverage": "secondary",
        "misspecification_taxonomy": "secondary",
        "null_noise_only": "secondary",
        "chirp_power": "secondary",
        "reference": "secondary",
        "cross_environment": "reproducibility_dimension",
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "experiment": primary.experiment,
        "evaluation": {
            "artifact_paths": [artifact.path for artifact in artifacts],
            "n_environments": len(artifacts),
            "primary_environment": "env0",
            "selected_candidates": list(selected_candidates),
            "protocol_digest": primary.protocol_digest,
            "grid_id": primary.grid_id,
            "frozen_grid_digest": primary.frozen_grid_digest,
            "require_paired": require_paired,
        },
        "validation": {
            "n_trials": len(primary.trials),
            "trials_per_environment": {
                f"env{index}": len(artifact.trials) for index, artifact in enumerate(artifacts)
            },
            "candidate_lists": {
                f"env{index}": list(artifact.candidates)
                for index, artifact in enumerate(artifacts)
            },
            "digest_consistency": {
                "protocol_digest": len({artifact.protocol_digest for artifact in artifacts}) == 1,
                "grid_id": len({artifact.grid_id for artifact in artifacts}) == 1,
                "frozen_grid_digest": len(
                    {artifact.frozen_grid_digest for artifact in artifacts}
                )
                == 1,
            },
        },
        "environments": environments,
        "statistical_method": {
            "name": "paired_wald_95",
            "risk_difference": "d = (n10 - n01)/n",
            "variance": "Var(d) = (n10 + n01 - (n10 - n01)^2/n) / n^2",
            "interval": "d +/- 1.959963984540054 * sqrt(Var(d)), clipped to [-1,1]",
            "n10": "candidate-only discordant pairs",
            "n01": "baseline-only discordant pairs",
            "note": (
                "Documented paired Wald alternative to Newcombe; no Newcombe pairing "
                "adjustment is claimed."
            ),
        },
        "primary_endpoint": primary_endpoint,
        "candidate_metrics": primary_metrics,
        "paired": primary_paired,
        "claim_integrity": primary_integrity,
        "negative_result": environments[0]["negative_result"],
        "chirp_power": chirp,
        "snr_conditioning": snr,
        "analysis_labels": labels,
        "cross_environment": cross,
        "contract_gaps": list(C2_CONTRACT_GAPS),
        "limitations": list(C2_LIMITATIONS),
    }


def _primary_endpoint(artifact: Artifact, selected_candidates: Sequence[str]) -> dict[str, Any]:
    endpoint = artifact.primary_endpoint
    parsed = endpoint.get("_parsed_candidate_ids")
    if not isinstance(parsed, (list, tuple)) or len(parsed) != 2:
        raise ValueError("primary_endpoint has no parsed candidate pair")
    candidate, baseline = parsed[0], parsed[1]
    if candidate not in selected_candidates or baseline not in selected_candidates:
        raise ValueError(
            "primary endpoint candidates are not in the selected candidate list: "
            f"{candidate}/{baseline}"
        )
    policy = artifact.undecided_policy
    alternative = "excluded" if policy == "not_detected" else "not_detected"
    bound = artifact.detection_loss_bound
    primary_metric = _primary_metric(endpoint)
    primary_pair = paired_comparison(
        artifact.trials, baseline, candidate, primary_metric
    )
    frr = paired_comparison(
        artifact.trials, baseline, candidate, "false_rejection"
    )
    detection = paired_comparison(
        artifact.trials,
        baseline,
        candidate,
        "discrepancy_detection",
        undecided_policy=policy,
    )
    detection_alt = paired_comparison(
        artifact.trials,
        baseline,
        candidate,
        "discrepancy_detection",
        undecided_policy=alternative,
    )
    primary_result, criteria = _evaluate_primary_criteria(
        primary_metric, primary_pair, detection, bound
    )
    alt_result, alt_criteria = _evaluate_primary_criteria(
        primary_metric, primary_pair, detection_alt, bound
    )
    return {
        "name": endpoint["name"],
        "definition": endpoint["definition"],
        "candidate_comparison": endpoint["candidate_comparison"],
        "decision_rule": endpoint["decision_rule"],
        "detection_non_inferiority_rule": endpoint["detection_non_inferiority_rule"],
        "candidate": candidate,
        "baseline": baseline,
        "detection_loss_bound": bound,
        "undecided_policy": policy,
        "primary_metric": primary_metric,
        "primary_metric_comparison": primary_pair,
        "false_rejection": frr,
        "detection": {
            "metric": "discrepancy_detected",
            "policy": policy,
            "paired": detection,
            "alternative_policy": alternative,
            "alternative_paired": detection_alt,
        },
        "criteria": criteria,
        "primary_result": primary_result,
        "sensitivity": {
            "policy": alternative,
            "criteria": alt_criteria,
            "result": alt_result,
            "note": (
                "sensitivity check under the alternative undecided policy; the primary "
                "result above uses the artifact's declared policy"
            ),
        },
        "evaluation_basis": (
            "The natural-language decision_rule and detection_non_inferiority_rule are "
            "printed verbatim. Numeric evaluation uses the declared candidate pair, the "
            "paired primary metric difference (supported_coverage/valid_retention improve "
            "iff delta>0; false_rejection improves iff delta<0), the paired "
            "discrepancy_detected difference under the declared undecided policy, and the "
            "artifact's detection_loss_bound: detection is non-inferior iff "
            "delta >= -detection_loss_bound."
        ),
        "result_level": "primary",
    }


def _evaluate_primary_criteria(
    primary_metric: str,
    primary_comparison: Mapping[str, Any],
    detection: Mapping[str, Any],
    bound: float,
) -> tuple[str, dict[str, Any]]:
    primary_delta = primary_comparison["risk_difference"]
    detection_delta = detection["risk_difference"]
    if primary_delta is None or detection_delta is None:
        return "undetermined", {
            "primary_metric": primary_metric,
            "primary_improved": None,
            "false_rejection_improved": None,
            "detection_non_inferior": None,
            "primary_delta": primary_delta,
            "frr_delta": primary_delta if primary_metric == "false_rejection" else None,
            "detection_delta": detection_delta,
            "detection_loss_bound": bound,
        }
    if primary_metric in {"supported_coverage", "valid_retention"}:
        primary_improved = primary_delta > 0.0
    else:
        primary_improved = primary_delta < 0.0
    detection_non_inferior = detection_delta >= -bound
    result = "pass" if (primary_improved and detection_non_inferior) else "fail"
    return result, {
        "primary_metric": primary_metric,
        "primary_improved": primary_improved,
        "false_rejection_improved": (
            primary_improved if primary_metric == "false_rejection" else None
        ),
        "supported_coverage_improved": (
            primary_improved if primary_metric == "supported_coverage" else None
        ),
        "detection_non_inferior": detection_non_inferior,
        "primary_delta": primary_delta,
        "frr_delta": primary_delta if primary_metric == "false_rejection" else None,
        "detection_delta": detection_delta,
        "detection_loss_bound": bound,
    }


def _primary_metric(endpoint: Mapping[str, Any]) -> str:
    explicit = endpoint.get("primary_metric") or endpoint.get("metric")
    if isinstance(explicit, str) and explicit in {
        "supported_coverage",
        "false_rejection",
        "valid_retention",
    }:
        return explicit
    text = f"{endpoint.get('definition', '')} {endpoint.get('decision_rule', '')}".lower()
    if "supported coverage" in text or "coverage" in text:
        return "supported_coverage"
    if "false rejection" in text or "frr" in text:
        return "false_rejection"
    if "valid retention" in text or "retention" in text:
        return "valid_retention"
    return "false_rejection"


def cross_environment(
    artifacts: Sequence[Artifact], selected_candidates: Sequence[str]
) -> dict[str, Any]:
    """Claim-status agreement across environments; differences are reported, never forced."""
    environment_ids = [f"env{index}" for index in range(len(artifacts))]
    trial_keys_by_env = {
        environment_id: set(artifact.trial_by_key)
        for environment_id, artifact in zip(environment_ids, artifacts)
    }
    union_keys = set().union(*trial_keys_by_env.values())
    presence: list[dict[str, Any]] = []
    for index, artifact in enumerate(artifacts):
        environment_id = environment_ids[index]
        missing = union_keys - trial_keys_by_env[environment_id]
        presence.append(
            {
                "environment_id": environment_id,
                "source": artifact.path,
                "n_trials": len(artifact.trials),
                "missing_trial_count_vs_union": len(missing),
                "missing_trials": [
                    {"condition": condition, "seed": seed}
                    for condition, seed in sorted(missing)
                ],
            }
        )
    agreement: list[dict[str, Any]] = []
    for candidate in selected_candidates:
        for claim in ("v", "f0_times_b", "t0"):
            statuses = _claim_status_map(artifacts, candidate, claim)
            complete_keys = [
                key
                for key in sorted(union_keys)
                if all(key in statuses[index] for index in range(len(artifacts)))
            ]
            agree = 0
            differences: list[dict[str, Any]] = []
            for key in complete_keys:
                values = [statuses[index][key] for index in range(len(artifacts))]
                if len(set(values)) == 1:
                    agree += 1
                else:
                    differences.append(
                        {
                            "condition": key[0],
                            "seed": key[1],
                            "statuses": {
                                environment_ids[index]: values[index]
                                for index in range(len(artifacts))
                            },
                        }
                    )
            missing = len(union_keys) - len(complete_keys)
            distributions: dict[str, dict[str, int]] = {}
            for index in range(len(artifacts)):
                counts: dict[str, int] = {}
                for key, status in statuses[index].items():
                    counts[status] = counts.get(status, 0) + 1
                distributions[environment_ids[index]] = dict(sorted(counts.items()))
            agreement.append(
                {
                    "candidate": candidate,
                    "claim": claim,
                    "n_trials_compared": len(complete_keys),
                    "agree": agree,
                    "disagree": len(differences),
                    "missing": missing,
                    "agreement_rate": (agree / len(complete_keys)) if complete_keys else None,
                    "status_distributions": distributions,
                    "differences": differences,
                }
            )
    return {
        "environment_ids": environment_ids,
        "trial_presence": presence,
        "claim_status_agreement": agreement,
        "note": (
            "Cross-environment agreement is descriptive. Missing trials and disagreeing "
            "statuses are listed; no environment is treated as authoritative and no "
            "equality is forced."
        ),
    }


def _claim_status_map(
    artifacts: Sequence[Artifact], candidate: str, claim: str
) -> list[dict[tuple[str, int], str]]:
    result: list[dict[tuple[str, int], str]] = []
    for artifact in artifacts:
        result.append(
            {
                trial.key: trial.candidates[candidate].claim_statuses[claim]
                for trial in artifact.trials
            }
        )
    return result
