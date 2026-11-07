"""Cross-platform reproducibility tooling: protocol model and R0/R1/R2 comparison.

The package compares two experiment artifacts under a strict, data-defined protocol and
produces a deterministic JSON report. It never picks a tolerance; final tolerances belong
in the protocol that the Lead fills from the measured cross-platform report.
"""

from .artifacts import Artifact, ArtifactError, load_artifact
from .paths import PathError
from .protocol import (
    DecisionInstabilityRule,
    DecisionSpec,
    DiagnosticField,
    FieldSpec,
    IdentifiabilityRule,
    NumericField,
    Protocol,
    ProtocolError,
    ProtocolV2,
    RateCheck,
    StructuralRules,
    load_protocol,
)

def __getattr__(name: str):
    # Lazy import keeps `python -m phaino_verify.compare` from finding the module
    # pre-imported by the package initializer.
    if name in {"Report", "compare_artifacts", "main"}:
        from . import compare

        return getattr(compare, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Artifact",
    "ArtifactError",
    "DecisionInstabilityRule",
    "DecisionSpec",
    "DiagnosticField",
    "FieldSpec",
    "IdentifiabilityRule",
    "NumericField",
    "ProtocolV2",
    "RateCheck",
    "PathError",
    "Protocol",
    "ProtocolError",
    "Report",
    "StructuralRules",
    "compare_artifacts",
    "load_artifact",
    "load_protocol",
    "main",
]
