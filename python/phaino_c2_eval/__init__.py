"""Independent paired evaluator for C2 repair candidates (B0-B3).

Artifact-only: validates the fixed C2 repair contract, computes paired false-rejection,
detection, valid-retention and abstention metrics with uncertainty intervals, flags
claim-integrity violations, reports per-mechanism and per-geometry strata, and compares
claim statuses across environments without forcing equality.
"""

from .artifacts import (
    Artifact,
    ArtifactError,
    Bin,
    CandidateRecord,
    Trial,
    load_artifact,
    load_artifacts,
    parse_strict_json,
    validate_artifact,
)
from .cli import main
from .evaluate import (
    C2_CONTRACT_GAPS,
    C2_LIMITATIONS,
    SCHEMA_VERSION,
    cross_environment,
    evaluate,
)
from .metrics import (
    C1_ALLOWED_CLAIM_STATUSES,
    GEOMETRY_BIN_EDGES,
    METRIC_NAMES,
    Z_95,
    candidate_metrics,
    chirp_power,
    claim_integrity,
    geometry_bin_label,
    negative_result,
    paired_comparison,
    paired_tables,
    paired_wald_interval,
    select_candidates,
    snr_conditioning,
    support_basis,
    validly_supported,
)
from .report import report_json, report_markdown

__all__ = [
    "Artifact",
    "ArtifactError",
    "Bin",
    "C1_ALLOWED_CLAIM_STATUSES",
    "C2_CONTRACT_GAPS",
    "C2_LIMITATIONS",
    "CandidateRecord",
    "GEOMETRY_BIN_EDGES",
    "METRIC_NAMES",
    "SCHEMA_VERSION",
    "Trial",
    "Z_95",
    "candidate_metrics",
    "chirp_power",
    "claim_integrity",
    "cross_environment",
    "evaluate",
    "geometry_bin_label",
    "load_artifact",
    "load_artifacts",
    "main",
    "negative_result",
    "paired_comparison",
    "paired_tables",
    "paired_wald_interval",
    "parse_strict_json",
    "report_json",
    "report_markdown",
    "select_candidates",
    "snr_conditioning",
    "support_basis",
    "validly_supported",
    "validate_artifact",
]
