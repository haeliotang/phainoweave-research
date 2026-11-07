"""Deterministic JSON and markdown rendering for the C2-M2 model check."""

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
    lines.append("# C2-M2 predictive measurement-error model check")
    lines.append("")
    lines.append(
        "Measurement model: `{}` · artifact: `{}` · development seed base {} · "
        "development trials {}".format(
            document["measurement_model_id"],
            document["artifact"]["path"],
            document["development"]["seed_base"],
            document["development"]["n_trials"],
        )
    )
    lines.append(
        "Models: {} · held-out cells: {} · train cells: {} · independent units: {}".format(
            ", ".join(document["artifact"]["models"]),
            document["validation"]["n_heldout_cells"],
            document["validation"]["n_train_cells"],
            document["validation"]["n_independent_units"],
        )
    )
    lines.append(
        "Pre-registered tolerances: {}".format(
            ", ".join(
                f"{key}={value}"
                for key, value in document["validation"]["tolerances"]["values"].items()
            )
        )
    )
    lines.append("")
    lines.append("## Per-model held-out calibration")
    lines.append("")
    lines.append(
        "| Model | Pass all held-out | Cells | Units | Mean FRR abs err (pp) | Max FRR abs err (pp) | Max KS | Max mean err (Hz) | Max RMS err (Hz) | Max ACF diff | Failed checks |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for model, result in document["models"].items():
        aggregate = result["aggregate"]
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                model,
                result["passes_all_heldout"],
                result["heldout_cell_count"],
                result["n_independent_units"],
                _fmt(aggregate["decision_frr_abs_error_pp"]["mean"]),
                _fmt(aggregate["decision_frr_abs_error_pp"]["max"]),
                _fmt(aggregate["distribution_ks"]["max"]),
                _fmt(aggregate["error_mean_abs_hz"]["max"]),
                _fmt(aggregate["error_rms_abs_hz"]["max"]),
                _fmt(aggregate["acf_max_abs_diff"]["max"]),
                len(result["failed_checks"]),
            )
        )
    lines.append("")
    lines.append("## Held-out cell details")
    lines.append("")
    lines.append(
        "| Cell | Geometry (m) | Bin | Units | Model | Actual FRR | Predicted FRR | FRR abs err (pp) | KS | ACF diff | Pass |"
    )
    lines.append("|---|---:|---|---:|---|---:|---:|---:|---:|---:|---|")
    for model, result in document["models"].items():
        for cell in result["cells"]:
            lines.append(
                "| {} | {:.1f} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                    cell["cell_id"],
                    cell["geometry_m"],
                    cell["geometry_bin"],
                    cell["n_independent_units"],
                    model,
                    _fmt(cell["actual_frr"]),
                    _fmt(cell["predicted_frr"]),
                    _fmt(cell["decision_frr_abs_error_pp"]),
                    _fmt(cell["distribution_ks"]),
                    _fmt(cell["acf_max_abs_diff"]),
                    cell["passes_tolerances"],
                )
            )
    lines.append("")
    lines.append("## Generalisation by geometry continuum")
    lines.append("")
    lines.append(
        "Tolerances are evaluated per held-out cell; the table shows per-geometry pass/fail "
        "and max discrepancies. No global p99 is computed or used."
    )
    lines.append("")
    lines.append(
        "| Geometry bin | Model | Cells | Pass all cells | Chosen model | Max FRR abs err (pp) | Max KS | Failed checks |"
    )
    lines.append("|---|---|---:|---|---|---:|---:|---:|")
    for geometry in document["generalisation"]["per_geometry"]:
        for model, row in geometry["models"].items():
            if row["n_cells"] == 0:
                continue
            lines.append(
                "| {} | {} | {} | {} | {} | {} | {} | {} |".format(
                    geometry["geometry_bin"],
                    model,
                    row["n_cells"],
                    row["passes_all_cells"],
                    geometry["chosen_model"] or "none",
                    _fmt(row["aggregate"]["decision_frr_abs_error_pp"]["max"]),
                    _fmt(row["aggregate"]["distribution_ks"]["max"]),
                    len(row["failed_checks"]),
                )
            )
    lines.append("")
    lines.append("## Deterministic cluster intervals")
    lines.append("")
    lines.append(
        "Bootstrap method: {}; resampling basis: {}; frame resampling: {}; replicates: {}.".format(
            document["bootstrap"]["method"],
            document["bootstrap"]["resampling_basis"],
            document["bootstrap"]["frame_resampling"],
            document["bootstrap"]["bootstrap_replicates"],
        )
    )
    lines.append("")
    lines.append(
        "| Model | Metric | Cell clusters | Independent units | Point | 95% interval |"
    )
    lines.append("|---|---|---:|---:|---:|---|")
    for model, result in document["models"].items():
        for metric, interval in result["intervals"]["metrics"].items():
            lines.append(
                "| {} | {} | {} | {} | {} | {} |".format(
                    model,
                    metric,
                    interval["n_clusters"],
                    interval["n_independent_units"],
                    _fmt(interval["point"]),
                    _fmt_interval(interval["interval"]),
                )
            )
    lines.append("")
    lines.append("## Fit-scope audit")
    lines.append("")
    lines.append(
        "Held-out fit scopes required for every model; validation rejects scopes that "
        "reference held-out cells. Status: {}; rows: {}.".format(
            document["fit_scope"]["status"],
            document["fit_scope"]["heldout_fit_scope_rows"],
        )
    )
    lines.append("")
    lines.append("## Reference estimator")
    lines.append("")
    reference = document["reference_estimator"]
    lines.append(
        "Name: `{}` · FRR: {} · detection: {} · selection: {}".format(
            reference["name"],
            _fmt(reference["frr"]),
            _fmt(reference["detection"]),
            reference["selection"],
        )
    )
    lines.append("")
    repaired = reference["repaired_candidate_comparison"]
    if repaired["available"]:
        lines.append(
            "Reference beats all supplied repaired candidates descriptively: {}; no selection.".format(
                repaired["reference_beats_all_descriptively"]
            )
        )
    else:
        lines.append(
            "Repaired-candidate comparison unavailable: {}.".format(repaired["reason"])
        )
    lines.append("")
    lines.append("## Negative-result statement")
    lines.append("")
    lines.append(document["generalisation"]["statement"])
    lines.append("")
    lines.append(
        "Passing models: {}.".format(
            ", ".join(document["generalisation"]["passing_models"]) or "none"
        )
    )
    lines.append("")
    lines.append("## Contract gaps")
    lines.append("")
    for gap in document["contract_gaps"]:
        lines.append(f"- {gap}")
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    for limitation in document["limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines)


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4g}"


def _fmt_interval(interval: Any) -> str:
    if not interval:
        return "[n/a]"
    return f"[{interval[0]:.4g}, {interval[1]:.4g}]"
