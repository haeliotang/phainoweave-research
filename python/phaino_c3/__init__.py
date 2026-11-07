"""C3 risk–coverage analysis over the frozen C2-C sealed artifact.

This is a *post-hoc selective-prediction analysis* of existing adequacy test
statistics, not part of the frozen decision rule.  It introduces a continuous
operating score for analysis only; the frozen B0-B3 decisions are unchanged.
"""

from .curve import build_curve, matched_risk, severity, severity_components

__all__ = ["severity", "severity_components", "build_curve", "matched_risk"]
