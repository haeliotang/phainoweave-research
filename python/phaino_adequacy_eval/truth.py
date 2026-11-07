"""Truth-based correctness with the frozen E0 parameter tolerances.

The tolerances are the pre-registered E0 decision thresholds, unchanged:
``f0`` 1% relative, ``v`` 2% relative, ``t0`` 0.25 s absolute, ``b`` 5% relative.
They are not tuned by this harness and none of them is used by the adequacy method.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

F0_REL_TOL = 0.01
V_REL_TOL = 0.02
T0_ABS_TOL = 0.25
B_REL_TOL = 0.05

FROZEN_TOLERANCES = {
    "f0_rel": F0_REL_TOL,
    "v_rel": V_REL_TOL,
    "t0_abs_s": T0_ABS_TOL,
    "b_rel": B_REL_TOL,
}


@dataclass(frozen=True)
class Correctness:
    """Truth comparison for one trial."""

    correct: bool
    within: Mapping[str, bool]
    relative_errors: Mapping[str, float]
    t0_absolute_error: float


def correctness(trial: Mapping[str, Any]) -> Correctness:
    """Compares ``hardened.params`` with the trial's synthetic truth."""
    scenario = trial["evaluation_only"]["scenario"]
    params = trial["hardened"]["params"]
    truth_f0 = float(scenario["f0"])
    truth_v = float(scenario["v"])
    truth_t0 = float(scenario["t0"])
    truth_b = float(scenario["b"])
    estimate_f0 = float(params["f0"])
    estimate_v = float(params["v"])
    estimate_t0 = float(params["t0"])
    estimate_b = float(params["b"])

    f0_rel = (estimate_f0 - truth_f0) / truth_f0
    v_rel = (estimate_v - truth_v) / truth_v
    b_rel = (estimate_b - truth_b) / truth_b
    t0_abs = estimate_t0 - truth_t0
    within = {
        "f0": abs(f0_rel) <= F0_REL_TOL,
        "v": abs(v_rel) <= V_REL_TOL,
        "t0": abs(t0_abs) <= T0_ABS_TOL,
        "b": abs(b_rel) <= B_REL_TOL,
    }
    return Correctness(
        correct=all(within.values()),
        within=within,
        relative_errors={"f0": f0_rel, "v": v_rel, "b": b_rel},
        t0_absolute_error=t0_abs,
    )


def is_correct(trial: Mapping[str, Any]) -> bool:
    """True when the trial's fitted parameters are within all frozen tolerances."""
    return correctness(trial).correct


def truth_tolerances() -> dict[str, float]:
    """Returns the frozen tolerance set for the report."""
    return dict(FROZEN_TOLERANCES)


def finite(value: Any) -> bool:
    """True for a finite, non-boolean number."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )
