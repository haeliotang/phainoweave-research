"""Deterministic JSON and markdown rendering for the C2 paired evaluator."""

from __future__ import annotations

import json
from typing import Any, Mapping


def report_json(document: Mapping[str, Any]) -> str:
    return (
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def report_markdown(document: Mapping[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# C2 repair paired evaluation")
    lines.append("")
    evaluation = document["evaluation"]
    metrics = document["candidate_metrics"]
    lines.append(
        "Primary environment: `{}` ({} env{}), protocol `{}`, grid `{}`, frozen grid `{}`".format(
            evaluation["primary_environment"],
            evaluation["n_environments"],
            "" if evaluation["n_environments"] == 1 else "s",
            evaluation["protocol_digest"],
            evaluation["grid_id"],
            evaluation["frozen_grid_digest"],
        )
    )
    lines.append(
        "Candidates: {}; paired comparisons are against B0 on identical trial identities. "
        "No pooled percentage is presented without its mechanism and geometry strata.".format(
            ", ".join(evaluation["selected_candidates"])
        )
    )
    lines.append("")
    primary = document["primary_endpoint"]
    lines.append("## Primary endpoint (pre-declared)")
    lines.append("")
    lines.append(f"- Name: **{primary['name']}**")
    lines.append(f"- Definition (verbatim): {primary['definition']}")
    lines.append(f"- Candidate comparison (verbatim): {primary['candidate_comparison']}")
    lines.append(f"- Decision rule (verbatim): `{primary['decision_rule']}`")
    lines.append(
        f"- Detection non-inferiority rule (verbatim): "
        f"`{primary['detection_non_inferiority_rule']}`"
    )
    lines.append(
        f"- Candidate/baseline: {primary['candidate']} vs {primary['baseline']}; "
        f"detection-loss bound: {primary['detection_loss_bound']}; "
        f"undecided policy: {primary['undecided_policy']}"
    )
    lines.append(f"- Primary result: **{primary['primary_result']}**")
    criteria = primary["criteria"]
    lines.append(
        "- Criteria: primary metric improved = {}; detection non-inferior = {}; "
        "primary delta = {}; detection delta = {}.".format(
            criteria["primary_improved"],
            criteria["detection_non_inferior"],
            _fmt_rate(criteria["primary_delta"]),
            _fmt_rate(criteria["detection_delta"]),
        )
    )
    sensitivity = primary["sensitivity"]
    lines.append(
        "- Undecided-policy sensitivity ({}): result {}, primary delta {}, detection delta {}; "
        "criteria {}.".format(
            sensitivity["policy"],
            sensitivity["result"],
            _fmt_rate(sensitivity["criteria"]["primary_delta"]),
            _fmt_rate(sensitivity["criteria"]["detection_delta"]),
            sensitivity["criteria"],
        )
    )
    lines.append("")
    lines.append("## Supported coverage (secondary)")
    lines.append("")
    lines.append(
        "Coverage = (truth-correct correct-model trials with valid support) / all "
        "correct-model trials. Valid support is explicit or derived from claim statuses "
        "plus the C1 gate; adequacy accept alone is never used."
    )
    lines.append("")
    lines.append("| Candidate | Supported coverage | Support basis counts |")
    lines.append("|---|---|---|")
    for candidate in evaluation["selected_candidates"]:
        coverage = metrics[candidate]["supported_coverage"]
        lines.append(
            "| {} | {} | {} |".format(
                candidate,
                _rate_pair(coverage["numerator"], coverage["denominator"]),
                ", ".join(
                    f"{key}={value}"
                    for key, value in coverage["support_basis_counts"].items()
                )
                or "none",
            )
        )
    lines.append("")
    lines.append("## Rate intervals (secondary)")
    lines.append("")
    lines.append(
        "| Candidate | Supported coverage [Wilson 95%] | FRR [Wilson 95%] | Detection [Wilson 95%] | Valid retention [Wilson 95%] | Abstention [Wilson 95%] |"
    )
    lines.append("|---|---|---|---|---|---|")
    for candidate in evaluation["selected_candidates"]:
        values = metrics[candidate]
        lines.append(
            "| {} | {} | {} | {} | {} | {} |".format(
                candidate,
                _rate_interval(values["supported_coverage"]),
                _rate_interval(values["false_rejection"]),
                _rate_interval(values["detection"]),
                _rate_interval(values["valid_retention"]),
                _rate_interval(values["abstention"]),
            )
        )
    lines.append("")
    lines.append("## Misspecification taxonomy (secondary)")
    lines.append("")
    lines.append(
        "Acceleration trials split exclusively into discrepancy_detected, undetermined, "
        "false_supported and rejected_without_discrepancy; undetermined is never detection."
    )
    lines.append("")
    lines.append(
        "| Candidate | N | discrepancy_detected | undetermined | false_supported | rejected_without_discrepancy |"
    )
    lines.append("|---|---:|---|---|---|---|")
    for candidate in evaluation["selected_candidates"]:
        taxonomy = metrics[candidate]["misspecification_taxonomy"]
        categories = taxonomy["categories"]
        lines.append(
            "| {} | {} | {} | {} | {} | {} |".format(
                candidate,
                taxonomy["denominator"],
                _category_text(categories["discrepancy_detected"]),
                _category_text(categories["undetermined"]),
                _category_text(categories["false_supported"]),
                _category_text(categories["rejected_without_discrepancy"]),
            )
        )
    lines.append("")
    lines.append("## Null/noise-only promotions (secondary)")
    lines.append("")
    lines.append("| Candidate | N | accepted | validly supported | false_supported | Wilson 95% |")
    lines.append("|---|---:|---:|---:|---:|---|")
    for candidate in evaluation["selected_candidates"]:
        null = metrics[candidate]["null_noise_only"]
        lines.append(
            "| {} | {} | {} | {} | {} | {} |".format(
                candidate,
                null["n_trials"],
                null["accepted"],
                null["validly_supported"],
                null["false_supported"],
                _fmt_interval(null["false_supported_wilson_95"]),
            )
        )
    lines.append("")
    lines.append("## Per-chirp-bin power (secondary)")
    lines.append("")
    lines.append(
        "Bins use the runtime-observable estimated_chirp_rate supplied by the artifact. "
        "Bins lacking acceleration samples are flagged; paired Bx-B0 comparisons are "
        "reported per bin and mechanism."
    )
    lines.append("")
    chirp = document["chirp_power"]
    if not chirp["declared"]:
        lines.append(f"- Per-chirp power unavailable: {chirp['note']}")
    else:
        lines.append(
            "| Bin | Candidate | CV N | CV FRR | Accel N | Accel detection | No accel samples |"
        )
        lines.append("|---|---|---:|---|---:|---|---|")
        for bin_row in chirp["bins"]:
            for candidate in evaluation["selected_candidates"]:
                cv = bin_row["cv_false_rejection"][candidate]
                accel = bin_row["acceleration_detection"][candidate]
                lines.append(
                    "| {} | {} | {} | {} | {} | {} | {} |".format(
                        bin_row["bin_id"],
                        candidate,
                        bin_row["n_correct_cv"],
                        _rate_pair(cv["numerator"], cv["denominator"]),
                        bin_row["n_acceleration"],
                        _rate_pair(
                            accel["discrepancy_detected"],
                            accel["denominator"],
                        ),
                        bin_row["no_acceleration_samples"],
                    )
                )
        lines.append("")
        lines.append(
            "- Bins without acceleration samples: {}.".format(
                ", ".join(chirp["bins_without_acceleration"]) or "none"
            )
        )
        lines.append(
            "- Trials missing estimated_chirp_rate: {}.".format(
                chirp["trials_missing_chirp_observable"]
            )
        )
    snr = document["snr_conditioning"]
    lines.append("")
    lines.append(
        "SNR conditioning verified: **{}** ({}); {}.".format(
            snr["snr_conditioning_verified"], snr["snr_branch"], snr["reason"]
        )
    )
    lines.append("")
    lines.append("## Per-candidate summary (secondary, primary environment)")
    lines.append("")
    lines.append(
        "| Candidate | N | Accepted | Correct accepted | Supported coverage | FRR | Detection | Valid retention | Abstention | Claim-integrity violations |"
    )
    lines.append("|---|---:|---:|---:|---|---|---|---|---|---:|")
    for candidate in evaluation["selected_candidates"]:
        values = metrics[candidate]
        frr = values["false_rejection"]
        detection = values["detection"]
        retention = values["valid_retention"]
        abstention = values["abstention"]
        violations = document["claim_integrity"][candidate]["n_violations"]
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                candidate,
                values["n_trials"],
                values["accepted"],
                values["correct_accepted"],
                _rate_pair(
                    values["supported_coverage"]["numerator"],
                    values["supported_coverage"]["denominator"],
                ),
                _rate_pair(frr["numerator"], frr["denominator"]),
                _rate_pair(detection["numerator"], detection["denominator"]),
                _rate_pair(retention["numerator"], retention["denominator"]),
                _rate_pair(abstention["numerator"], abstention["denominator"]),
                violations,
            )
        )
    lines.append("")
    lines.append("## Paired overall differences (secondary, Bx − B0)")
    lines.append("")
    lines.append(
        "| Candidate | Metric | Pairs | Baseline rate | Candidate rate | Difference | 95% interval | Discordant b/c |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---|---|")
    for candidate in evaluation["selected_candidates"]:
        if candidate == "B0":
            continue
        for metric in (
            "false_rejection",
            "detection",
            "discrepancy_detection",
            "valid_retention",
            "abstention",
        ):
            entry = document["paired"][candidate]["overall"][metric]
            lines.append(_paired_row(candidate, metric, entry))
    lines.append("")
    lines.append("## Per-mechanism paired differences (secondary)")
    lines.append("")
    lines.append(
        "| Mechanism | Candidate | Metric | Pairs | Baseline rate | Candidate rate | Difference | 95% interval |"
    )
    lines.append("|---|---|---|---:|---:|---:|---:|---|")
    mechanisms = sorted(document["paired"][_first_comparison_candidate(document)]["by_mechanism"])
    for mechanism in mechanisms:
        for candidate in evaluation["selected_candidates"]:
            if candidate == "B0":
                continue
            for metric in ("false_rejection", "detection"):
                entry = document["paired"][candidate]["by_mechanism"][mechanism][metric]
                lines.append(_paired_stratum_row(mechanism, candidate, metric, entry))
    lines.append("")
    lines.append("## Per-geometry continuum paired differences (secondary)")
    lines.append("")
    lines.append(
        "| Geometry bin | Candidate | Metric | Pairs | Baseline rate | Candidate rate | Difference | 95% interval |"
    )
    lines.append("|---|---|---|---:|---:|---:|---:|---|")
    first_candidate = _first_comparison_candidate(document)
    geometry_bins = document["paired"][first_candidate]["by_geometry"]
    for label in geometry_bins:
        for candidate in evaluation["selected_candidates"]:
            if candidate == "B0":
                continue
            for metric in ("false_rejection", "detection"):
                entry = document["paired"][candidate]["by_geometry"][label]["metrics"][metric]
                lines.append(_paired_stratum_row(label, candidate, metric, entry))
    lines.append("")
    lines.append("## Claim integrity")
    lines.append("")
    lines.append(
        "C1 gate allowed claim statuses: {}. Any `supported_invariant` or unknown status is "
        "flagged below and is not silently accepted.".format(
            ", ".join(document["claim_integrity"]["B0"]["allowed_claim_statuses"])
        )
    )
    lines.append("")
    lines.append("| Candidate | Status | Violations | supported_invariant count |")
    lines.append("|---|---|---:|---:|")
    for candidate in evaluation["selected_candidates"]:
        integrity = document["claim_integrity"][candidate]
        lines.append(
            "| {} | {} | {} | {} |".format(
                candidate,
                integrity["status"],
                integrity["n_violations"],
                integrity["supported_invariant_count"],
            )
        )
    lines.append("")
    lines.append("## Negative-result statement")
    lines.append("")
    negative = document["negative_result"]
    lines.append(negative["statement"])
    lines.append("")
    lines.append(
        "- Qualifying candidates: {}.".format(
            ", ".join(negative["qualifying_candidates"]) or "none"
        )
    )
    lines.append(
        "- FRR-gain candidates: {}; detection-loss candidates: {}; "
        "abstention-gaming candidates: {}.".format(
            ", ".join(negative["frr_gain_candidates"]) or "none",
            ", ".join(negative["detection_loss_candidates"]) or "none",
            ", ".join(negative["abstention_gaming_candidates"]) or "none",
        )
    )
    lines.append("")
    lines.append("## Cross-environment claim-status agreement")
    lines.append("")
    cross = document["cross_environment"]
    lines.append(
        "Environments: {}. Missing trials and status differences are reported; no equality "
        "is forced.".format(", ".join(cross["environment_ids"]))
    )
    lines.append("")
    lines.append(
        "| Candidate | Claim | Compared | Agree | Disagree | Missing | Agreement |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|")
    for entry in cross["claim_status_agreement"]:
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} |".format(
                entry["candidate"],
                entry["claim"],
                entry["n_trials_compared"],
                entry["agree"],
                entry["disagree"],
                entry["missing"],
                _fmt_rate(entry["agreement_rate"]),
            )
        )
    lines.append("")
    lines.append("## Contract gaps")
    lines.append("")
    for gap in document.get("contract_gaps", []):
        lines.append(f"- {gap}")
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    for limitation in document["limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines)


def _first_comparison_candidate(document: Mapping[str, Any]) -> str:
    for candidate in document["evaluation"]["selected_candidates"]:
        if candidate != "B0":
            return candidate
    raise ValueError("no non-B0 candidate selected")


def _paired_row(candidate: str, metric: str, entry: Mapping[str, Any]) -> str:
    return "| {} | {} | {} | {} | {} | {} | {} | {} |".format(
        candidate,
        metric,
        entry["n_pairs"],
        _fmt_rate(entry["baseline_rate"]),
        _fmt_rate(entry["candidate_rate"]),
        _fmt_rate(entry["risk_difference"]),
        _fmt_interval(entry["risk_difference_interval"]),
        "{}/{}".format(entry["counts"]["candidate_only"], entry["counts"]["baseline_only"]),
    )


def _paired_stratum_row(
    stratum: str, candidate: str, metric: str, entry: Mapping[str, Any]
) -> str:
    return "| {} | {} | {} | {} | {} | {} | {} | {} |".format(
        stratum,
        candidate,
        metric,
        entry["n_pairs"],
        _fmt_rate(entry["baseline_rate"]),
        _fmt_rate(entry["candidate_rate"]),
        _fmt_rate(entry["risk_difference"]),
        _fmt_interval(entry["risk_difference_interval"]),
    )


def _rate_pair(numerator: int, denominator: int) -> str:
    rate = numerator / denominator if denominator else None
    return "{}/{} ({})".format(numerator, denominator, _fmt_rate(rate))


def _fmt_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _fmt_interval(interval: Any) -> str:
    if not interval:
        return "[n/a]"
    return f"[{interval[0]:.4f}, {interval[1]:.4f}]"


def _category_text(category: Mapping[str, Any]) -> str:
    return "{} ({} {})".format(
        category["count"], _fmt_rate(category["rate"]), _fmt_interval(category["wilson_95"])
    )


def _rate_interval(entry: Mapping[str, Any]) -> str:
    interval = entry.get("wilson_95")
    return "{} {}".format(_fmt_rate(entry.get("rate")), _fmt_interval(interval))
