"""Independent forward model and clock-transformation action for E0 claims.

Physics implemented directly from the E0 narrowband model: a stationary receiver and a
straight-line source passing at closest approach ``b`` with speed ``v`` at event time
``t0``. The physical instantaneous frequency is

    tau = t_phys - t0
    r   = sqrt(v^2 tau^2 + b^2)
    f_phys(t_phys) = f0 / (1 + v^2 tau / (c r))

The clock transform maps physical time to observation time as

    t_obs = t_phys / k + beta          (k = 1 + epsilon, k > 0)

so observed frequency in cycles per observed second is

    y(t_obs) = k * f_phys(k * (t_obs - beta)).

The induced parameter action is derived analytically from the same equations and applied
independently:

    f0' = k f0,   v' = v,   t0' = beta + t0/k,   b' = b/k.

The certificate compares y(t_obs) with the nominal forward model evaluated with the
transformed parameters on the same observation-time grid. A relabelled time axis is not
accepted as evidence. No acoustics-method code is imported.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Mapping

import numpy as np

TOLERANCE_FLOOR = 1e-15


@dataclass(frozen=True)
class ModelParameters:
    """The four fitted E0 parameters plus the fixed speed of sound."""

    f0: float
    v: float
    t0: float
    b: float
    c: float = 343.0

    def valid(self) -> bool:
        values = (self.f0, self.v, self.t0, self.b, self.c)
        return all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in values) and (
            self.f0 > 0.0 and self.v > 0.0 and self.b > 0.0 and self.c > 0.0
        )

    def relative_to(self, other: ModelParameters) -> float:
        """Largest relative difference over f0, v, t0, b, c (zero-handled)."""
        return max(
            _relative(self.f0, other.f0),
            _relative(self.v, other.v),
            _relative(self.t0, other.t0),
            _relative(self.b, other.b),
            _relative(self.c, other.c),
        )


@dataclass(frozen=True)
class ClockTransform:
    """An affine observation-clock transform and its induced parameter action."""

    k: float = 1.0
    beta: float = 0.0
    # Diagnostic knobs used only to produce implementation/wrong-generator controls.
    f0_scale: float = 1.0
    b_scale: float = 1.0
    observation_shift_samples: float = 0.0

    def valid(self) -> bool:
        return (
            math.isfinite(self.k)
            and self.k > 0.0
            and math.isfinite(self.beta)
            and math.isfinite(self.f0_scale)
            and math.isfinite(self.b_scale)
            and math.isfinite(self.observation_shift_samples)
        )

    def apply_parameters(self, parameters: ModelParameters) -> ModelParameters:
        """Induced action on the fitted parameters, from the forward-model algebra."""
        return replace(
            parameters,
            f0=parameters.f0 * self.k * self.f0_scale,
            v=parameters.v,
            t0=self.beta + parameters.t0 / self.k,
            b=parameters.b / self.k * self.b_scale,
        )

    def observed_frequency(
        self,
        t_obs: np.ndarray,
        parameters: ModelParameters,
        grid_step: float,
    ) -> np.ndarray:
        """Observed frequency in the same t_obs coordinates under this clock."""
        shifted = t_obs + self.observation_shift_samples * grid_step
        t_phys = self.k * (shifted - self.beta)
        return self.k * physical_frequency(t_phys, parameters)

    def compose(self, other: ClockTransform) -> ClockTransform:
        """Composition ``other ∘ self`` (apply self, then other)."""
        return ClockTransform(
            k=self.k * other.k,
            beta=self.beta / other.k + other.beta,
        )

    def inverse(self) -> ClockTransform:
        return ClockTransform(k=1.0 / self.k, beta=-self.beta * self.k)

    def is_identity(self, tolerance: float = TOLERANCE_FLOOR) -> bool:
        return abs(self.k - 1.0) <= tolerance and abs(self.beta) <= tolerance


def physical_frequency(t_phys: np.ndarray | float, parameters: ModelParameters) -> np.ndarray:
    """Physical instantaneous frequency of the E0 narrowband source."""
    time = np.asarray(t_phys, dtype=np.float64)
    tau = time - parameters.t0
    r = np.sqrt(parameters.v * parameters.v * tau * tau + parameters.b * parameters.b)
    denominator = 1.0 + parameters.v * parameters.v * tau / (parameters.c * r)
    values = parameters.f0 / denominator
    if np.any(~np.isfinite(values)):
        raise FloatingPointError("forward model produced a non-finite frequency")
    return values


def forward_model(t_obs: np.ndarray | float, parameters: ModelParameters) -> np.ndarray:
    """Nominal forward model on an observation-time grid."""
    return physical_frequency(t_obs, parameters)


def claim_value(quantity: str, parameters: ModelParameters) -> float:
    """Value of a declared claim quantity."""
    if quantity == "v":
        return parameters.v
    if quantity == "b/f0":
        return parameters.b / parameters.f0
    if quantity == "t0":
        return parameters.t0
    if quantity == "b":
        return parameters.b
    if quantity == "f0":
        return parameters.f0
    if quantity == "b*f0":
        return parameters.b * parameters.f0
    raise ValueError(f"unknown claim quantity {quantity!r}")


def relative_mismatch(first: float, second: float) -> float:
    """Relative mismatch with a zero-safe denominator."""
    return _relative(first, second)


def sample_grid(t_min: float, t_max: float, count: int) -> tuple[np.ndarray, float]:
    if count < 3:
        raise ValueError("observation grid needs at least 3 samples")
    if not (math.isfinite(t_min) and math.isfinite(t_max) and t_max > t_min):
        raise ValueError("observation grid bounds must be finite and increasing")
    grid = np.linspace(t_min, t_max, count, dtype=np.float64)
    step = (t_max - t_min) / float(count - 1)
    return grid, step


def forward_preservation(
    grid: np.ndarray,
    grid_step: float,
    parameters: ModelParameters,
    transform: ClockTransform,
    observation_tolerance: float,
) -> dict[str, Any]:
    """Compares clock-generated observation with forward(Tθ) in the same coordinates."""
    transformed = transform.apply_parameters(parameters)
    expected = forward_model(grid, transformed)
    generated = transform.observed_frequency(grid, parameters, grid_step)
    mismatch = float(np.max(np.abs(expected - generated) / np.maximum(np.abs(generated), 1e-300)))
    evidence: dict[str, Any] = {
        "max_relative_observation_mismatch": mismatch,
        "observation_tolerance": observation_tolerance,
        "preserves_forward_model": mismatch <= observation_tolerance,
        "grid_samples": int(grid.size),
    }
    if mismatch <= observation_tolerance:
        evidence["failure_class"] = None
        evidence["diagnosis"] = "exact_up_to_floating_point"
        return evidence
    # Distinguish a genuine invalid symmetry from a sampling/time-grid implementation
    # difference. If a rigid grid shift explains the residual, it is an implementation
    # discrepancy, not a physical non-invariance.
    best = None
    for shift in (-2, -1, 1, 2):
        shifted_grid = grid + shift * grid_step
        shifted_expected = forward_model(shifted_grid, transformed)
        shifted_mismatch = float(
            np.max(np.abs(shifted_expected - generated) / np.maximum(np.abs(generated), 1e-300))
        )
        if best is None or shifted_mismatch < best[1]:
            best = (shift, shifted_mismatch)
    if best is not None and best[1] <= observation_tolerance:
        evidence["failure_class"] = "implementation"
        evidence["diagnosis"] = "sampling_or_time_grid_mismatch"
        evidence["grid_shift_samples"] = best[0]
        evidence["shifted_mismatch"] = best[1]
    else:
        evidence["failure_class"] = "invalid_symmetry"
        evidence["diagnosis"] = "generator_does_not_preserve_the_forward_model"
        if best is not None:
            evidence["best_grid_shift_samples"] = best[0]
            evidence["best_shifted_mismatch"] = best[1]
    return evidence


def _relative(first: float, second: float) -> float:
    if not (math.isfinite(first) and math.isfinite(second)):
        return float("inf")
    scale = max(abs(first), abs(second))
    if scale == 0.0:
        return 0.0
    return abs(first - second) / scale


def parameters_from_document(document: Mapping[str, Any]) -> ModelParameters:
    """Builds a parameter point from a JSON protocol point."""
    return ModelParameters(
        f0=float(document["f0"]),
        v=float(document["v"]),
        t0=float(document["t0"]),
        b=float(document["b"]),
        c=float(document.get("c", 343.0)),
    )
