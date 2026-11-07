"""Atmospheric sound-speed and Doppler uncertainty for E1 planning.

The formulae are deliberately simple engineering approximations.  They are
used to propagate *measurement uncertainty* into a predicted Doppler residual
interval before field data exists, not to claim a validated atmospheric model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Atmosphere:
    temperature_c: float
    relative_humidity_pct: float
    pressure_hpa: float = 1013.25
    wind_mps: float = 0.0
    wind_along_path_fraction: float = 0.0
    temperature_uncertainty_c: float = 0.5
    humidity_uncertainty_pct: float = 5.0
    pressure_uncertainty_hpa: float = 2.0
    wind_uncertainty_mps: float = 0.5

    def __post_init__(self) -> None:
        if not 0.0 <= self.relative_humidity_pct <= 100.0:
            raise ValueError("relative humidity must be within 0..100 %")
        if self.pressure_hpa <= 0.0:
            raise ValueError("pressure must be positive")
        if self.wind_along_path_fraction < -1.0 or self.wind_along_path_fraction > 1.0:
            raise ValueError("wind projection fraction must be within -1..1")


def sound_speed_mps(temperature_c: float, relative_humidity_pct: float) -> float:
    """Approximate dry-air sound speed plus a small humidity correction.

    `c ≈ 331.3 + 0.606 T + 0.0124 RH` (T in °C, RH in %).  Accuracy is about
    0.1–0.3 % over ordinary field conditions; that is enough for planning, not
    for a metrological claim.
    """
    return 331.3 + 0.606 * temperature_c + 0.0124 * relative_humidity_pct


def effective_sound_speed(atmosphere: Atmosphere) -> float:
    """Sound speed plus the wind component along the propagation path."""
    return sound_speed_mps(
        atmosphere.temperature_c, atmosphere.relative_humidity_pct
    ) + atmosphere.wind_mps * atmosphere.wind_along_path_fraction


def sound_speed_uncertainty(atmosphere: Atmosphere) -> float:
    """First-order uncertainty of the effective sound speed (m/s)."""
    sigma = math.hypot(
        0.606 * atmosphere.temperature_uncertainty_c,
        0.0124 * atmosphere.humidity_uncertainty_pct,
        0.03 * atmosphere.pressure_uncertainty_hpa,
        abs(atmosphere.wind_along_path_fraction) * atmosphere.wind_uncertainty_mps,
    )
    return sigma


def predicted_doppler_hz(
    emitted_hz: float, radial_speed_mps: float, atmosphere: Atmosphere
) -> float:
    """Non-relativistic radial Doppler prediction using the effective sound speed."""
    c = effective_sound_speed(atmosphere)
    denominator = 1.0 - radial_speed_mps / c
    if denominator <= 0.0:
        raise ValueError("source speed must stay below the effective sound speed")
    return emitted_hz / denominator


def doppler_residual_interval_hz(
    emitted_hz: float,
    radial_speed_mps: float,
    atmosphere: Atmosphere,
    *,
    sigma_level: float = 1.96,
) -> dict[str, float]:
    """Predicted frequency with a first-order atmospheric uncertainty interval.

    The interval is a planning bound for the *atmospheric* contribution only; it
    does not include front-end, clock or motion-truth uncertainty.
    """
    c = effective_sound_speed(atmosphere)
    f = predicted_doppler_hz(emitted_hz, radial_speed_mps, atmosphere)
    # df/dc = f * (v / c^2) / (1 - v/c), from f = f0 / (1 - v/c).
    derivative = f * (radial_speed_mps / (c * c)) / (1.0 - radial_speed_mps / c)
    sigma_f = abs(derivative) * sound_speed_uncertainty(atmosphere)
    return {
        "effective_sound_speed_mps": c,
        "sound_speed_sigma_mps": sound_speed_uncertainty(atmosphere),
        "predicted_doppler_hz": f,
        "residual_sigma_hz": sigma_f,
        "lower_hz": f - sigma_level * sigma_f,
        "upper_hz": f + sigma_level * sigma_f,
    }
