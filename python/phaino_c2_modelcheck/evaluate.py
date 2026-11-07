"""Top-level C2-M2 model-check evaluation assembly."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .artifacts import Artifact, OPTIONAL_TOLERANCES, REQUIRED_TOLERANCES
from .metrics import (
    BOOTSTRAP_REPLICATES,
    geometry_bins,
    model_reference_comparison,
    tolerance_summary,
)

SCHEMA_VERSION = "1.0.0"
CONTRACT_GAPS = (
    "The artifact contract does not contain `fit_scope`; this evaluator requires it and "
    "rejects held-out predictions whose fit_scope references held-out data. The method "
    "side must add the field before this evaluator can accept real C2-M2 artifacts.",
    "The contract supplies only per-cell aggregate statistics, not unit-level observations. "
    "Intervals therefore use a deterministic cluster bootstrap over held-out cell "
    "aggregates weighted by n_independent_units; this is not a true trial/scenario-level "
    "bootstrap and cannot estimate within-cell unit variance.",
    "The contract has no repaired-candidate B0-B3 outcomes, so the reference estimator "
    "cannot be compared to repaired candidates within this artifact; the reference section "
    "reports that comparison as unavailable and does not select.",
    "The reference estimator has no sampling interval, n_trials, or n_independent_units; "
    "its FRR/detection are reported as supplied.",
    "Tolerances are accepted as pre-registered numbers, but the contract carries no "
    "provenance/digest for the pre-registration or for the tolerance selection.",
    "The artifact carries a measurement_model_id but not the ADR 0021 measurement-model "
    "record fields (window, hop, FFT length, interpolation, peak rule, error-model version, "
    "conditioning features), so measurement-model identity cannot be audited from this "
    "artifact alone.",
    "The contract does not declare which tolerance extra fields are pre-registered; the "
    "evaluator checks the two required fields and known optional fields and reports unused "
    "tolerance keys.",
)


def evaluate(
    artifact: Artifact, bootstrap_replicates: int = BOOTSTRAP_REPLICATES
) -> dict[str, Any]:
    from .metrics import evaluate_model

    models = {
        model: evaluate_model(artifact, model, bootstrap_replicates)
        for model in artifact.models
    }
    generalisation = _generalisation(artifact, models)
    fit_scope = _fit_scope_audit(artifact)
    reference = _reference_section(artifact, models)
    return {
        "schema_version": SCHEMA_VERSION,
        "experiment": artifact.experiment,
        "measurement_model_id": artifact.measurement_model_id,
        "development": {
            "seed_base": artifact.seed_base,
            "n_trials": artifact.development_n_trials,
        },
        "artifact": {
            "path": artifact.path,
            "sha256": artifact.sha256,
            "models": list(artifact.models),
        },
        "validation": {
            "n_cells": len(artifact.cells),
            "n_heldout_cells": len(artifact.heldout_cells),
            "n_train_cells": len(artifact.train_cells),
            "models": list(artifact.models),
            "tolerances": tolerance_summary(artifact.tolerances),
            "resampling_units": sorted({cell.resampling_unit for cell in artifact.heldout_cells}),
            "n_independent_units": sum(
                cell.n_independent_units for cell in artifact.heldout_cells
            ),
        },
        "models": models,
        "generalisation": generalisation,
        "fit_scope": fit_scope,
        "reference_estimator": reference,
        "bootstrap": {
            "method": "deterministic_cluster_bootstrap_over_cell_aggregates",
            "bootstrap_replicates": bootstrap_replicates,
            "frame_resampling": False,
            "resampling_basis": (
                "held-out cells resampled with probability proportional to each cell's "
                "n_independent_units; unit-level records are not present in the contract"
            ),
        },
        "contract_gaps": list(CONTRACT_GAPS),
        "limitations": [
            "Predictive checks are only as good as the artifact's synthetic actual data and "
            "self-reported fit scopes; the evaluator cannot verify how predictions were fit.",
            "Ljung-Box discrepancy is the two-sample empirical-CDF KS statistic; no "
            "asymptotic p-value or global p99 is used.",
            "ACF discrepancy is the maximum absolute difference on the common lag support "
            "with linear interpolation; lags outside the common support are not extrapolated.",
            "FRR actual intervals are Wilson intervals over n_trials; predicted FRR has no "
            "sampling interval, so the predicted-minus-actual interval shifts the actual "
            "Wilson interval and treats the prediction as fixed.",
            "Intervals use cell aggregates weighted by n_independent_units and therefore do "
            "not capture within-cell correlation or frame-level dependence.",
            "Tolerances are consumed as pre-registered data. The evaluator does not tune or "
            "re-interpret them.",
            "The reference estimator is descriptive only; no candidate/model selection is "
            "made and no repaired-candidate comparison is possible from this contract.",
        ],
    }


def _generalisation(
    artifact: Artifact, models: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    per_geometry: list[dict[str, Any]] = []
    for geometry_bin in geometry_bins():
        label = geometry_bin["label"]
        model_rows: dict[str, Any] = {}
        passing_models: list[str] = []
        for model, result in models.items():
            geometry = result["by_geometry"].get(label)
            if geometry is None:
                model_rows[model] = {
                    "n_cells": 0,
                    "passes_all_cells": None,
                    "failed_checks": [],
                }
                continue
            row = {
                "n_cells": geometry["n_cells"],
                "n_independent_units": geometry["n_independent_units"],
                "passes_all_cells": geometry["passes_all_cells"],
                "failed_checks": geometry["failed_checks"],
                "aggregate": geometry["aggregate"],
                "intervals": geometry["intervals"],
            }
            model_rows[model] = row
            if geometry["passes_all_cells"]:
                passing_models.append(model)
        chosen_model = passing_models[0] if len(passing_models) == 1 else None
        per_geometry.append(
            {
                "geometry_bin": label,
                "lower": geometry_bin["lower"],
                "upper": geometry_bin["upper"],
                "models": model_rows,
                "passing_models": passing_models,
                "chosen_model": chosen_model,
                "chosen_model_status": (
                    "unique_pass" if chosen_model else ("none_pass" if not passing_models else "ambiguous_multiple_pass")
                ),
                "note": (
                    "chosen_model is descriptive only: null when zero or multiple models "
                    "pass this geometry bin; no model is selected or recommended."
                ),
            }
        )
    passing_models = [
        model for model, result in models.items() if result["passes_all_heldout"]
    ]
    negative = not passing_models
    if negative:
        statement = (
            "No model meets all pre-registered held-out tolerances across the geometry "
            "continuum. This is the pre-defined negative result: the claim that the "
            "measurement error is conditionally modellable by this family on held-out cells "
            "is refuted by this artifact. No global p99 or pooled single-geometry match is "
            "allowed to override this."
        )
    else:
        statement = (
            "Models meeting all pre-registered held-out tolerances: "
            + ", ".join(passing_models)
            + ". This is a predictive-check result, not a recommendation; geometry-level "
            "failures remain visible in the table."
        )
    return {
        "tolerances": tolerance_summary(artifact.tolerances),
        "per_geometry": per_geometry,
        "passing_models": passing_models,
        "negative_result_holds": negative,
        "statement": statement,
    }


def _fit_scope_audit(artifact: Artifact) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for cell in artifact.heldout_cells:
        for model in artifact.models:
            rows.append(
                {
                    "cell_id": cell.cell_id,
                    "split": cell.split,
                    "model": model,
                    "fit_scope": cell.fit_scopes.get(model),
                }
            )
    return {
        "status": "ok",
        "heldout_fit_scope_rows": len(rows),
        "audited_cells": [cell.cell_id for cell in artifact.heldout_cells],
        "rows": rows,
        "note": (
            "A non-empty held-out fit_scope was required for every model; scopes that "
            "reference the same held-out cell (or any held-out cell) are rejected during "
            "validation."
        ),
    }


def _reference_section(
    artifact: Artifact, models: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    reference = artifact.reference_estimator
    repaired: dict[str, Any] | None = None
    if artifact.repaired_candidates is None:
        repaired = {
            "available": False,
            "reason": (
                "the c2-m2 contract contains no repaired-candidate B0-B3 outcomes, so the "
                "reference estimator cannot be compared to repaired candidates from this "
                "artifact"
            ),
            "reference_beats_all_descriptively": None,
            "candidates": None,
        }
    else:
        details: list[dict[str, Any]] = []
        for candidate, values in artifact.repaired_candidates.items():
            beats = reference.frr < values["frr"] and reference.detection > values["detection"]
            details.append(
                {
                    "candidate": candidate,
                    "frr": values["frr"],
                    "detection": values["detection"],
                    "reference_minus_candidate_frr": reference.frr - values["frr"],
                    "reference_minus_candidate_detection": reference.detection
                    - values["detection"],
                    "reference_beats_candidate_descriptively": beats,
                }
            )
        repaired = {
            "available": True,
            "reference_beats_all_descriptively": all(
                item["reference_beats_candidate_descriptively"] for item in details
            ),
            "candidates": details,
            "statement": "descriptive only; no selection",
        }
    return {
        "name": reference.name,
        "frr": reference.frr,
        "detection": reference.detection,
        "notes": reference.notes,
        "frr_uncertainty": "not supplied by the contract",
        "repaired_candidate_comparison": repaired,
        "model_prediction_comparison": model_reference_comparison(reference, models),
        "selection": "none",
        "statement": (
            "The reference estimator is reported as supplied. It is not used to select a "
            "model or candidate; repaired-candidate comparison is unavailable unless the "
            "artifact explicitly includes repaired_candidates."
        ),
    }
