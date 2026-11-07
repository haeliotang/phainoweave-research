"""Deterministic JSON and markdown report assembly for the adequacy evaluation."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from .artifacts import AdequacyArtifact
from .metrics import (
    CONDITIONAL_CLAIM_PATH,
    NEW_RULES,
    OBSERVATIONAL_EQUIVALENCE_MECHANISMS,
    build_report_strata,
    conditional_claim,
    new_status_counts,
    observational_equivalence_section,
)
from .truth import truth_tolerances

HARNESS_LIMITATIONS = (
    "Truth is synthetic. These labels test correctness against the E0 generator's "
    "parameters, not against the physical world or real recordings.",
    "The frozen E0 tolerances (f0 1%, v 2%, t0 0.25 s, b 5%) are not re-tuned and may not "
    "be appropriate for parameter ranges outside the E0/locked grids.",
    "The harness consumes artifacts only. It cannot recompute adequacy tests, check their "
    "calibration, or detect method-internal test leakage or overfitting.",
    "Tuning/locked separation is whatever the artifact labels claim. The harness cannot "
    "detect label leakage or whether locked thresholds were adapted after opening.",
    "Without an exposed numeric operating score, risk-coverage uses a documented "
    "status/reason-signature nesting, not a calibrated probability ordering; matched-"
    "retention values are descriptive, not an operating guarantee.",
    "Wilson/Newcombe intervals are per stratum and do not cluster correlated trials within "
    "a condition, seed family, or recording series; intervals are correspondingly "
    "optimistic when trials share a generator realization.",
    "The old rule's matched-retention curve may be a single observed operating point or a "
    "few nested status points; where the new retention lies outside the old observed range, "
    "old risk is reported as not estimable rather than extrapolated.",
    "Observational equivalence is identified by the declared mechanism label "
    f"({', '.join(sorted(OBSERVATIONAL_EQUIVALENCE_MECHANISMS))}), not inferred by the "
    "harness.",
    "The artifact carries one environment/layer; cross-environment stability and the "
    "three-environment matrix are separate runs and comparisons.",
    "The new rule's own parameter estimates are not present in the fixed contract; "
    "correctness uses hardened.params for both rules. If the adequacy layer changes the "
    "parameters, the contract needs a new parameter field.",
)


def build_report_document(
    artifact: AdequacyArtifact,
    old_decisions: Mapping[tuple[str, int], str],
    old_decision_field: str,
    old_decision_source: str,
    new_rule: str = "epistemic",
) -> dict[str, Any]:
    """Builds the complete deterministic report document."""
    if new_rule not in NEW_RULES:
        raise ValueError(f"unknown new rule {new_rule!r}; expected one of {sorted(NEW_RULES)}")
    trials = artifact.trials
    strata = build_report_strata(trials, old_decisions, new_rule)
    mechanisms = sorted({trial["mechanism"] for trial in trials})
    conditions = sorted({trial["condition"] for trial in trials})
    correct = sum(1 for trial in trials if strata_correct(trial))
    report = {
        "schema_version": 1,
        "artifact": {
            "source": artifact.source,
            "experiment": artifact.experiment,
            "layer": artifact.layer,
            "protocol_digest": artifact.protocol_digest,
            "n_trials": len(trials),
            "conditions": conditions,
            "mechanisms": mechanisms,
        },
        "rules": {
            "old": {
                "definition": "hardened decision status == 'accepted'",
                "decision_field": old_decision_field,
                "decision_source": old_decision_source,
            },
            "new": {
                "rule": new_rule,
                "definition": (
                    "adequacy.tests.degeneracy.conditional_claim_supported == true"
                    if new_rule == "conditional"
                    else "adequacy.epistemic_decision == 'supported'"
                ),
                "conditional_claim_field": CONDITIONAL_CLAIM_PATH
                if new_rule == "conditional"
                else None,
                "missing_conditional_claim_supported": sum(
                    1 for trial in trials if conditional_claim(trial) is None
                )
                if new_rule == "conditional"
                else 0,
                "undetermined_definition": (
                    "epistemic_decision == 'undetermined' and conditional claim is not true"
                    if new_rule == "conditional"
                    else "adequacy.epistemic_decision == 'undetermined'"
                ),
                "epistemic_decision_counts": _epistemic_counts(trials),
                "conditional_claim_counts": _conditional_counts(trials)
                if new_rule == "conditional"
                else None,
                "status_counts": new_status_counts(trials, new_rule),
            },
        },
        "truth": {
            "tolerances": truth_tolerances(),
            "definition": (
                "correct iff |f0_hat-f0|/f0 <= 0.01, |v_hat-v|/v <= 0.02, "
                "|t0_hat-t0| <= 0.25 s, |b_hat-b|/b <= 0.05 using evaluation_only.scenario "
                "truth and hardened.params for both rules"
            ),
            "n_correct": correct,
            "n_incorrect": len(trials) - correct,
        },
        "strata": strata,
        "observational_equivalence": observational_equivalence_section(
            trials, old_decisions, new_rule
        ),
        "harness_limitations": list(HARNESS_LIMITATIONS),
    }
    return report


def strata_correct(trial: Mapping[str, Any]) -> bool:
    from .truth import is_correct

    return is_correct(trial)


def report_json(report: Mapping[str, Any]) -> str:
    """Canonical deterministic report JSON."""
    return (
        json.dumps(
            report,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def report_markdown(report: Mapping[str, Any]) -> str:
    """Deterministic markdown report with per-mechanism and matched-retention tables."""
    lines: list[str] = []
    artifact = report["artifact"]
    lines.append("# Model adequacy decision utility — independent evaluation")
    lines.append("")
    lines.append(
        "Artifact: `{}` · layer: **{}** · protocol: `{}` · trials: {}".format(
            artifact["source"],
            artifact["layer"],
            artifact["protocol_digest"],
            artifact["n_trials"],
        )
    )
    lines.append("")
    lines.append("## Rules and truth")
    lines.append("")
    lines.append("- Old rule: `{}` (field `{}`, source `{}`)".format(
        report["rules"]["old"]["definition"],
        report["rules"]["old"]["decision_field"],
        report["rules"]["old"]["decision_source"],
    ))
    lines.append(
        "- New rule (`{}`): `{}`".format(
            report["rules"]["new"].get("rule", "epistemic"),
            report["rules"]["new"]["definition"],
        )
    )
    if report["rules"]["new"].get("conditional_claim_field"):
        lines.append(
            "- Conditional claim field: `{}`; missing/unknown: {}".format(
                report["rules"]["new"]["conditional_claim_field"],
                report["rules"]["new"]["missing_conditional_claim_supported"],
            )
        )
    lines.append("- Truth: {}".format(report["truth"]["definition"]))
    lines.append(
        "- Truth counts: {} correct / {} incorrect".format(
            report["truth"]["n_correct"], report["truth"]["n_incorrect"]
        )
    )
    lines.append("")
    lines.append("## Per-mechanism decision utility")
    lines.append("")
    lines.append(
        "| Mechanism | N | Correct | Old accepted | Old correct-acc | Old FA rate | "
        "Old retention | Old abstain | New accepted | New correct-acc | New FA rate | "
        "New retention | New abstain |"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    )
    for mechanism, stratum in report["strata"]["by_mechanism"].items():
        lines.append(_stratum_row(mechanism, stratum))
    lines.append("")
    lines.append("## Per-condition decision utility")
    lines.append("")
    lines.append(
        "| Condition | N | Correct | Old accepted | Old FA rate | Old retention | "
        "New accepted | New FA rate | New retention |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for condition, stratum in report["strata"]["by_condition"].items():
        old = stratum["old"]
        new = stratum["new"]
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                condition,
                stratum["n_trials"],
                stratum["n_correct"],
                old["accepted"],
                _fmt_rate(old["false_accept_rate"]),
                _fmt_rate(old["valid_retention"]),
                new["accepted"],
                _fmt_rate(new["false_accept_rate"]),
                _fmt_rate(new["valid_retention"]),
            )
        )
    lines.append("")
    lines.append("## Matched valid-retention comparison")
    lines.append("")
    lines.append(
        "Old risk is linearly interpolated on its risk–coverage curve at each new-rule "
        "retention; points outside the old observed coverage range are marked not "
        "estimable. Intervals are Wilson 95% (risk) and Newcombe (difference)."
    )
    lines.append("")
    lines.append(
        "| Stratum | New retention | New FA rate [95% CI] | Old FA rate [95% CI] | "
        "Difference [95% CI] | Estimable |"
    )
    lines.append("|---|---:|---|---|---|---|")
    for stratum_name, stratum in [
        ("overall", report["strata"]["overall"]),
        *report["strata"]["by_mechanism"].items(),
    ]:
        for entry in stratum["risk_coverage"]["matched_retention"]:
            lines.append(_matched_row(stratum_name, entry))
    lines.append("")
    lines.append("## Risk–coverage ordering")
    lines.append("")
    for label, stratum in [
        ("overall", report["strata"]["overall"]),
        *report["strata"]["by_mechanism"].items(),
    ]:
        curves = stratum["risk_coverage"]
        lines.append(
            "- **{}**: new basis `{}` ({}); old basis `{}` ({}).".format(
                label,
                curves["new"]["basis"],
                curves["new"]["order_definition"],
                curves["old"]["basis"],
                curves["old"]["order_definition"],
            )
        )
    lines.append("")
    lines.append("## Observational-equivalence cases")
    lines.append("")
    equivalence = report["observational_equivalence"]
    lines.append(
        "Declared mechanisms: {}. {}".format(
            ", ".join(equivalence["mechanisms"]), equivalence["declaration"]
        )
    )
    if equivalence["n_trials"]:
        lines.append("")
        lines.append(
            "| N | Correct | Incorrect | Correct undetermined | Wrong supported | "
            "Correct supported | Wrong undetermined | Wrong rejected |"
        )
        lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|")
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} |".format(
                equivalence["n_trials"],
                equivalence["n_correct"],
                equivalence["n_incorrect"],
                equivalence["correct_undetermined"],
                equivalence["wrong_supported"],
                equivalence["correct_supported"],
                equivalence["wrong_undetermined"],
                equivalence["wrong_rejected"],
            )
        )
    lines.append("")
    lines.append("## What this harness cannot measure")
    lines.append("")
    for limitation in report["harness_limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines)


def _stratum_row(mechanism: str, stratum: Mapping[str, Any]) -> str:
    old = stratum["old"]
    new = stratum["new"]
    return (
        "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            mechanism,
            stratum["n_trials"],
            stratum["n_correct"],
            old["accepted"],
            old["correct_accepted"],
            _fmt_rate(old["false_accept_rate"]),
            _fmt_rate(old["valid_retention"]),
            _fmt_rate(old["abstention_rate"]),
            new["accepted"],
            new["correct_accepted"],
            _fmt_rate(new["false_accept_rate"]),
            _fmt_rate(new["valid_retention"]),
            _fmt_rate(new["abstention_rate"]),
        )
    )


def _matched_row(stratum: str, entry: Mapping[str, Any]) -> str:
    new_interval = _fmt_interval(entry["new_false_accept_interval"])
    old_interval = _fmt_interval(entry["old_false_accept_interval"])
    diff_interval = _fmt_interval(entry["difference_interval"])
    return "| {} | {} | {} {} | {} {} | {} {} | {} |".format(
        stratum,
        _fmt_rate(entry["retention"]),
        _fmt_rate(entry["new_false_accept_rate"]),
        new_interval,
        _fmt_rate(entry["old_false_accept_rate"]),
        old_interval,
        _fmt_rate(entry["difference"]),
        diff_interval,
        "yes" if entry["old_estimable"] else "no",
    )


def _fmt_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _fmt_interval(interval: Any) -> str:
    if not interval:
        return "[n/a]"
    return f"[{interval[0]:.4f}, {interval[1]:.4f}]"


def _epistemic_counts(trials: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for trial in trials:
        value = trial["adequacy"]["epistemic_decision"]
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _conditional_counts(trials: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"true": 0, "false": 0, "unknown": 0}
    for trial in trials:
        value = conditional_claim(trial)
        if value is True:
            counts["true"] += 1
        elif value is False:
            counts["false"] += 1
        else:
            counts["unknown"] += 1
    return counts
