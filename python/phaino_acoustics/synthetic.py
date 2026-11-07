"""E0 synthetic narrowband Doppler generator.

Physical model
--------------
A point source moves on a straight line past a stationary receiver (the
receiver sits at the origin, the line of travel is the x axis, and the
closest approach happens at ``t = t0`` at distance ``b``).  With
``tau = t - t0`` the source-receiver range and its rate of change are::

    x(tau)   = v*tau + 0.5*a*tau**2          # along-track displacement
    r(tau)   = sqrt(x(tau)**2 + b**2)        # range
    v_r(tau) = -d r / d tau                  # radial velocity, positive approaching

The observed frequency of a narrowband component whose emitted (rest)
frequency is ``f0`` is::

    f_obs(t) = f0 / (1 - v_r(t)/c)

``c`` is the speed of sound (a recorded parameter of the experiment, not a
fitted unknown; default 343 m/s = 20 degC dry air).  This is the
non-relativistic, *instantaneous-frequency* form used by the M1 kinematic
constraint in ``docs/roadmap/ROADMAP.md`` section 4.  It deliberately omits
the retarded-time (propagation-delay) correction, source/receiver
directivity, atmospheric stratification, ground reflection, and multipath.
Those omissions are limitations of E0, recorded in the report; they are not
modelled here.

"Signal" constructed from the model
-----------------------------------
The generated waveform is a kinematic realization, not a propagation
simulation::

    s(t) = A(t) * cos(2*pi * integral f_obs + phase0)

with the phase integral taken on the sample grid (trapezoid rule).  This is
the standard way to synthesize a signal with a prescribed instantaneous
frequency; it is exact for a slowly varying ``f_obs`` and is deterministic.

Noise and SNR definition (exact)
--------------------------------
The observation is ``clean + n`` with ``n ~ N(0, sigma**2)`` i.i.d. white
Gaussian noise, one sample at a time.  ``sigma`` is chosen from the *target
per-sample SNR*::

    SNR_dB = 10 * log10( (A0**2 / 2) / sigma**2 )

where ``A0 = Scenario.amplitude`` is the nominal signal amplitude (equal to
the amplitude at closest approach for geometric spreading).  This is a
**per-sample, full-band** SNR: mean signal power divided by mean noise power
over the whole sampling bandwidth.  It is *not* the peak SNR of an STFT bin;
a Hann frame of ``Nw`` samples adds roughly ``10*log10(Nw/2)`` dB of
processing gain, so e.g. ``-10 dB`` per-sample is roughly ``+14 dB`` in a
512-sample frame at 8 kHz.  ``SyntheticObservation.measured_snr_db`` reports
the realized value ``10*log10(mean(clean**2)/sigma**2)``.

Recorder clock model
--------------------
A recorder may mis-time its samples.  The generator warps the *true* time
axis as::

    t_true(k) = t_nominal(k) * (1 + eps) + clock_offset_s,

with ``eps = clock_scale_ppm * 1e-6``.  The analyzer is given the nominal
time axis ``t`` and fits the nominal model, so:

* ``clock_offset_s != 0`` moves the pass in nominal time: the fitted
  ``t0`` absorbs it exactly (``t0_fit = t0 - clock_offset_s``); this is an
  exact degeneracy, not a failure mode.
* ``clock_scale_ppm != 0`` time-stretches the observation.  The nominal
  model can absorb a stretch exactly into
  ``f0 -> f0*(1+eps)``, ``t0 -> (t0 - clock_offset_s)/(1+eps)``,
  ``b -> b/(1+eps)`` with ``v`` unchanged (derivation in the E0 report).
  This is a structural degeneracy: a clock-rate error looks exactly like a
  rescaled source.  Realistic ppm-level drift is therefore harmless for
  parameter recovery (the biases are ``eps``, e.g. 1e-3 at 1000 ppm) while
  an uncalibrated percent-level clock error is not.

Everything is deterministic given ``Scenario.seed`` (NumPy PCG64).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

C_SOUND_DEFAULT = 343.0


@dataclass(frozen=True)
class Scenario:
    """One synthetic observation's true world state and generator settings.

    Angles and positions are not modelled: the observation is a scalar
    pressure waveform from one stationary receiver, and only the radial
    component of the motion is observable.  The true parameters are
    ``f0, v, t0, b`` plus the generator-only knobs below.
    """

    f0: float = 500.0          # emitted (rest) frequency, Hz
    v: float = 250.0           # source speed along the line, m/s
    b: float = 3000.0          # closest-approach distance, m
    t0: float = 20.0           # closest-approach time, s (nominal axis)
    duration: float = 60.0     # observation duration, s
    fs: float = 8000.0         # sample rate, Hz
    c: float = C_SOUND_DEFAULT  # speed of sound, m/s
    accel: float = 0.0         # constant along-track acceleration, m/s^2
    snr_db: float = 20.0       # target per-sample SNR, dB (see module docstring)
    amplitude: float = 1.0     # nominal amplitude A0
    phase0: float = 0.0        # initial carrier phase, rad
    amplitude_mod_depth: float = 0.0   # sinusoidal AM depth, fraction of A0
    amplitude_mod_hz: float = 0.7      # sinusoidal AM frequency, Hz
    amplitude_geometric: bool = False  # multiply amplitude by b/r(t) (1/r spreading)
    clock_scale_ppm: float = 0.0       # recorder clock rate error, parts per million
    clock_offset_s: float = 0.0        # recorder clock constant offset, s
    emit_signal: bool = True   # False => noise-only observation (null case)
    seed: int = 20261104       # NumPy Generator seed for the noise realization

    @property
    def window(self) -> tuple[float, float]:
        """Nominal observation window ``[start, end)`` in seconds."""
        half = 0.5 * self.duration
        return (self.t0 - half, self.t0 + half)


@dataclass(frozen=True)
class SyntheticObservation:
    """A generated observation plus the truth needed to score a fit."""

    scenario: Scenario
    t: np.ndarray            # nominal sample times, s
    clean: np.ndarray        # noise-free waveform
    signal: np.ndarray       # clean + noise
    f_apparent: np.ndarray   # true apparent instantaneous frequency vs nominal t, Hz
    noise_sigma: float       # per-sample noise standard deviation
    measured_snr_db: Optional[float]  # realized per-sample SNR, None for null cases


def observation_window(scenario: Scenario) -> tuple[float, float]:
    return scenario.window


def true_times(scenario: Scenario, t_nominal: np.ndarray) -> np.ndarray:
    """Map nominal (analyzer) times to the generator's true time axis."""
    eps = scenario.clock_scale_ppm * 1e-6
    return np.asarray(t_nominal, dtype=np.float64) * (1.0 + eps) + scenario.clock_offset_s


def range_and_radial_velocity(
    t: np.ndarray,
    v: float,
    b: float,
    t0: float,
    accel: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Range ``r(t)`` and radial velocity toward the receiver ``v_r(t)``.

    ``v_r = -dr/dt`` is positive while the source approaches.  With
    ``accel == 0`` this reduces to ``v_r(tau) = -v**2 * tau / sqrt(v**2 tau**2 + b**2)``.
    """
    t = np.asarray(t, dtype=np.float64)
    tau = t - t0
    x = v * tau + 0.5 * accel * tau * tau
    xdot = v + accel * tau
    r = np.hypot(x, b)
    vr = -(x * xdot) / r
    return r, vr


def doppler_frequency(
    t: np.ndarray,
    f0: float,
    v: float,
    t0: float,
    b: float,
    c: float = C_SOUND_DEFAULT,
    accel: float = 0.0,
) -> np.ndarray:
    """Observed frequency ``f0 / (1 - v_r(t)/c)`` for the given trajectory."""
    _, vr = range_and_radial_velocity(t, v, b, t0, accel)
    return f0 / (1.0 - vr / c)


def apparent_frequency(scenario: Scenario, t_nominal: np.ndarray) -> np.ndarray:
    """True instantaneous frequency the analyzer should see on its own time axis.

    The analyzer samples on the nominal axis, so a clock-rate error also
    scales the observed frequency: ``f_apparent = (1+eps) * f_true(t_true)``.
    (Frame-centre frequencies are affected by the same factor; the generator's
    phase integral is taken on the true-time grid, so this is bookkeeping for
    scoring the front end, not an extra physical effect.)
    """
    eps = scenario.clock_scale_ppm * 1e-6
    t_true = true_times(scenario, np.asarray(t_nominal, dtype=np.float64))
    return (1.0 + eps) * doppler_frequency(
        t_true, scenario.f0, scenario.v, scenario.t0, scenario.b, scenario.c, scenario.accel
    )


def _validate(scenario: Scenario) -> None:
    if not (scenario.duration > 0 and scenario.fs > 0):
        raise ValueError("duration and fs must be positive")
    if not (scenario.b > 0 and scenario.v > 0 and scenario.f0 > 0 and scenario.c > 0):
        raise ValueError("f0, v, b, c must be positive")
    if scenario.accel != 0.0 and scenario.v + scenario.accel * scenario.duration <= 0:
        raise ValueError("acceleration reverses the source direction inside the window")
    if scenario.snr_db == float("-inf"):
        raise ValueError("infinite negative SNR is not supported")


def generate(scenario: Scenario) -> SyntheticObservation:
    """Generate one deterministic synthetic observation (see module docstring)."""
    _validate(scenario)
    n = int(round(scenario.duration * scenario.fs))
    if n < 8:
        raise ValueError("duration * fs is too small")
    start, _ = scenario.window
    t = start + np.arange(n, dtype=np.float64) / scenario.fs
    t_true = true_times(scenario, t)

    f_phys = doppler_frequency(
        t_true, scenario.f0, scenario.v, scenario.t0, scenario.b, scenario.c, scenario.accel
    )
    eps = scenario.clock_scale_ppm * 1e-6
    dt_true = (1.0 + eps) / scenario.fs
    dphi = np.zeros(n, dtype=np.float64)
    if n > 1:
        dphi[1:] = 0.5 * (f_phys[1:] + f_phys[:-1]) * dt_true
    phase = scenario.phase0 + 2.0 * np.pi * np.cumsum(dphi)

    r, _ = range_and_radial_velocity(t_true, scenario.v, scenario.b, scenario.t0, scenario.accel)
    amp = np.full(n, float(scenario.amplitude))
    if scenario.amplitude_geometric:
        amp = amp * (scenario.b / r)
    if scenario.amplitude_mod_depth != 0.0:
        amp = amp * (
            1.0
            + scenario.amplitude_mod_depth
            * np.sin(2.0 * np.pi * scenario.amplitude_mod_hz * (t_true - t[0]))
        )
    clean = amp * np.cos(phase)
    if not scenario.emit_signal:
        clean = np.zeros(n, dtype=np.float64)

    sigma = float(np.sqrt(0.5 * scenario.amplitude**2 / (10.0 ** (scenario.snr_db / 10.0))))
    rng = np.random.default_rng(int(scenario.seed))
    noise = sigma * rng.standard_normal(n)
    signal = clean + noise

    f_app = apparent_frequency(scenario, t)
    clean_power = float(np.mean(clean * clean))
    if clean_power <= 0.0 or sigma <= 0.0:
        measured_snr_db: Optional[float] = None
    else:
        measured_snr_db = float(10.0 * np.log10(clean_power / (sigma * sigma)))

    return SyntheticObservation(
        scenario=scenario,
        t=t,
        clean=clean,
        signal=signal,
        f_apparent=f_app,
        noise_sigma=sigma,
        measured_snr_db=measured_snr_db,
    )
