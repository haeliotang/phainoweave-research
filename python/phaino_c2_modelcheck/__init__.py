"""Independent predictive model check for C2-M2 measurement-error artifacts.

Artifact-only: validates the fixed C2-M2 contract plus required ``fit_scope`` provenance,
checks held-out calibration per model and geometry, computes deterministic cluster
intervals over independent units (not frames), and reports a descriptive reference
estimator section without selecting a model.
"""

from .artifacts import (
    AcfPoint,
    ActualStats,
    Artifact,
    ArtifactError,
    Cell,
    PredictedStats,
    ReferenceEstimator,
    load_artifact,
    parse_strict_json,
    validate_artifact,
)
from .cli import main
from .evaluate import CONTRACT_GAPS, SCHEMA_VERSION, evaluate
from .metrics import (
    BOOTSTRAP_REPLICATES,
    GEOMETRY_BIN_EDGES,
    METRIC_NAMES,
    Z_95,
    acf_difference_at,
    acf_discrepancy,
    bootstrap_interval,
    cell_metrics_for_model,
    evaluate_model,
    geometry_bin_label,
    ks_statistic,
    model_reference_comparison,
    tolerance_summary,
    wilson_interval,
)
from .report import report_json, report_markdown

__all__ = [
    "AcfPoint",
    "ActualStats",
    "Artifact",
    "ArtifactError",
    "BOOTSTRAP_REPLICATES",
    "CONTRACT_GAPS",
    "Cell",
    "GEOMETRY_BIN_EDGES",
    "METRIC_NAMES",
    "PredictedStats",
    "ReferenceEstimator",
    "SCHEMA_VERSION",
    "Z_95",
    "acf_difference_at",
    "acf_discrepancy",
    "bootstrap_interval",
    "cell_metrics_for_model",
    "evaluate",
    "evaluate_model",
    "geometry_bin_label",
    "ks_statistic",
    "load_artifact",
    "main",
    "model_reference_comparison",
    "parse_strict_json",
    "report_json",
    "report_markdown",
    "tolerance_summary",
    "validate_artifact",
    "wilson_interval",
]
