"""Deterministic JSON and markdown rendering for the invariance certificate."""

from __future__ import annotations

import json
from typing import Any, Mapping


def certificate_json(document: Mapping[str, Any]) -> str:
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


def certificate_markdown(document: Mapping[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# E0 clock-invariance certificate")
    lines.append("")
    lines.append(f"Certificate version: `{document['certificate_version']}`")
    lines.append(f"Model: `{document['model']['name']}`")
    protocol = document["claims_protocol"]
    lines.append(
        "Claims protocol: `{}` version {} (source: `{}`{})".format(
            protocol["id"],
            protocol["version"],
            protocol["source"],
            ", built-in" if protocol["builtin"] else "",
        )
    )
    if protocol["builtin"]:
        lines.append("")
        lines.append(f"> Warning: {protocol['warning']}")
    method_protocol = document.get("method_protocol")
    if method_protocol:
        lines.append("")
        lines.append("## Method protocol reconciliation")
        lines.append("")
        lines.append(f"- Declared model: {method_protocol['declared_model']}")
        lines.append(f"- Method clock model: `{method_protocol['clock_model']}`")
        lines.append(
            f"- Mapping: {method_protocol['mapping']['rate_mapping']}; "
            f"{method_protocol['mapping']['action_equivalence']}"
        )
        lines.append(
            f"- Method protocol digest: `{method_protocol['protocol_digest']}`; "
            f"symbolic proof digest: `{method_protocol['symbolic_proof_digest']}`; "
            f"source SHA-256: `{method_protocol['source_sha256']}`"
        )
        lines.append("")
        lines.append(
            "| Claim | Kind | L1 status | L2 status | Max status | Operational tolerance |"
        )
        lines.append("|---|---|---|---|---|---|")
        for metadata in method_protocol["claim_metadata"]:
            tolerance = metadata["operational_tolerance"]
            lines.append(
                "| {} | {} | {} | {} | {} | {} {} |".format(
                    metadata["claim_id"],
                    metadata["claim_kind"],
                    metadata["l1_status"],
                    metadata["l2_status"],
                    metadata["max_status"],
                    tolerance["value"],
                    tolerance["kind"],
                )
            )
    lines.append("")
    lines.append("## Forward model")
    lines.append("")
    for name, equation in document["model"]["equations"].items():
        lines.append(f"- `{name}`: `{equation}`")
    lines.append(
        f"- c = {document['model']['speed_of_sound_m_s']} m/s; observation grid "
        f"[{document['model']['observation_grid']['t_min']}, "
        f"{document['model']['observation_grid']['t_max']}] with "
        f"{document['model']['observation_grid']['count']} samples"
    )
    lines.append(
        f"- Independent implementation: {document['independence']['forward_model']}; "
        f"imports acoustics: **{document['independence']['imports_acoustics']}**"
    )
    lines.append("")
    lines.append("## Group axioms")
    lines.append("")
    lines.append("| Axiom | Pass |")
    lines.append("|---|---|")
    for key in ("identity", "composition", "inverse", "domain"):
        lines.append(f"| {key} | {document['group_axioms'][key]} |")
    evidence = document["group_axioms"]["evidence"]
    lines.append("")
    lines.append(
        "Evidence: identity parameter error {}, identity observation error {}, "
        "composition parameter error {}, inverse parameter error {}, domain checks {} "
        "(failures {}).".format(
            _fmt(evidence["max_relative_identity_parameter_error"]),
            _fmt(evidence["max_relative_identity_observation_error"]),
            _fmt(evidence["max_relative_composition_parameter_error"]),
            _fmt(evidence["max_relative_inverse_parameter_error"]),
            evidence["domain_checks"],
            len(evidence["domain_failures"]),
        )
    )
    lines.append("")
    lines.append("## Generators")
    lines.append("")
    lines.append(
        "| Family | Preserves forward | Max observation mismatch | Tolerance | Failure class |"
    )
    lines.append("|---|---|---:|---:|---|")
    for name, generator in document["generators"].items():
        lines.append(
            "| {} | {} | {} | {} | {} |".format(
                name,
                generator["preserves_forward_model"],
                _fmt(generator["max_relative_observation_mismatch"]),
                _fmt(generator["observation_tolerance"]),
                generator["failure_class"] or "none",
            )
        )
    lines.append("")
    lines.append("## Claims")
    lines.append("")
    lines.append(
        "| Claim | Symbolic | Numeric | Max rel mismatch | Tolerance | Failure class | Agrees |"
    )
    lines.append("|---|---|---|---:|---:|---|---|")
    for claim in document["claims"]:
        agrees = claim["agrees_with_symbolic"]
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} |".format(
                claim["claim"],
                claim["symbolic_verdict"],
                claim["numeric_verdict"],
                _fmt(claim["max_relative_mismatch"]),
                _fmt(claim["tolerance"]),
                claim["failure_class"] or "none",
                "n/a" if agrees is None else agrees,
            )
        )
    lines.append("")
    lines.append("### Symbolic / numeric disagreements")
    lines.append("")
    if document["symbolic_numeric_disagreements"]:
        for entry in document["symbolic_numeric_disagreements"]:
            lines.append(
                "- **{}**: symbolic `{}` vs numeric `{}` (max relative mismatch {}, "
                "tolerance {}).".format(
                    entry["claim"],
                    entry["symbolic_verdict"],
                    entry["numeric_verdict"],
                    _fmt(entry["max_relative_mismatch"]),
                    _fmt(entry["tolerance"]),
                )
            )
    else:
        lines.append("- None.")
    for note in document["notes"]:
        lines.append(f"- Note: {note}")
    lines.append("")
    lines.append("## Self-audit")
    lines.append("")
    lines.append(
        "| Generator | Declared | Required | Tested | Preserves forward |"
    )
    lines.append("|---|---|---|---|---|")
    for generator in document["self_audit"]["generators"]:
        lines.append(
            "| {} | {} | {} | {} | {} |".format(
                generator["generator_id"],
                generator["declared"],
                generator["required"],
                generator["tested"],
                "n/a" if generator["preserves_forward"] is None else generator["preserves_forward"],
            )
        )
    lines.append("")
    lines.append("| Claim | Numeric verdict | Promotion allowed | Gate status |")
    lines.append("|---|---|---|---|")
    for claim in document["self_audit"]["claims"]:
        lines.append(
            "| {} | {} | {} | {} |".format(
                claim["claim"],
                claim["numeric_verdict"],
                claim["promotion_allowed"],
                claim["gate_status"],
            )
        )
    lines.append("")
    lines.append(
        "`incomplete_group`: {}. Group coverage complete: {}.".format(
            document["incomplete_group"],
            document["self_audit"]["group_coverage_complete"],
        )
    )
    if document.get("nuisance_conflicts"):
        lines.append("")
        lines.append("Nuisance conflicts (not accepted as nuisance-free invariants):")
        for conflict in document["nuisance_conflicts"]:
            lines.append(
                " - **{}**: max relative mismatch {} under {}.".format(
                    conflict["claim"],
                    _fmt(conflict["max_relative_mismatch"]),
                    conflict["probe"],
                )
            )
    lines.append("")
    lines.append("## Nuisance assumptions")
    lines.append("")
    lines.append(
        "Declared but not used for invariance claims: {}. `used_for_invariance_claims`: "
        "{}.".format(
            ", ".join(document["nuisance"]["declared"]),
            document["nuisance"]["used_for_invariance_claims"],
        )
    )
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    for limitation in document["limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")
    lines.append("## Environment")
    lines.append("")
    lines.append(
        "Python {}, numpy {}, platform {}, machine {}.".format(
            document["environment"]["python"],
            document["environment"]["numpy"],
            document["environment"]["platform"],
            document["environment"]["machine"],
        )
    )
    lines.append("")
    return "\n".join(lines)


def _fmt(value: float) -> str:
    return "n/a" if value is None else f"{value:.3e}"
