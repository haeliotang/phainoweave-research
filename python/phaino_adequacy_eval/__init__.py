"""Independent evaluation harness for the PhainoWeave model-adequacy layer.

The harness consumes JSON artifacts only. It does not import the adequacy method or
`phaino_acoustics`; it uses the frozen E0 parameter tolerances to label trials against
synthetic truth and compares the old hardened rule with the new epistemic rule per
mechanism and condition, including risk–coverage and matched-valid-retention intervals.
"""

from .artifacts import (
    AdequacyArtifact,
    AdequacyArtifactError,
    embedded_old_decisions,
    load_adequacy_artifact,
    load_old_decisions,
    parse_strict_json,
    validate_adequacy_artifact,
)
from .cli import main
from .metrics import (
    OBSERVATIONAL_EQUIVALENCE_MECHANISMS,
    CurvePoint,
    build_report_strata,
    build_stratum,
    interpolate_risk,
    observational_equivalence_section,
)
from .report import (
    HARNESS_LIMITATIONS,
    build_report_document,
    report_json,
    report_markdown,
)
from .truth import (
    B_REL_TOL,
    F0_REL_TOL,
    T0_ABS_TOL,
    V_REL_TOL,
    FROZEN_TOLERANCES,
    correctness,
    is_correct,
    truth_tolerances,
)

__all__ = [
    "AdequacyArtifact",
    "AdequacyArtifactError",
    "B_REL_TOL",
    "F0_REL_TOL",
    "FROZEN_TOLERANCES",
    "HARNESS_LIMITATIONS",
    "OBSERVATIONAL_EQUIVALENCE_MECHANISMS",
    "CurvePoint",
    "T0_ABS_TOL",
    "V_REL_TOL",
    "build_report_document",
    "build_report_strata",
    "build_stratum",
    "correctness",
    "embedded_old_decisions",
    "interpolate_risk",
    "is_correct",
    "load_adequacy_artifact",
    "load_old_decisions",
    "main",
    "observational_equivalence_section",
    "parse_strict_json",
    "report_json",
    "report_markdown",
    "truth_tolerances",
    "validate_adequacy_artifact",
]
