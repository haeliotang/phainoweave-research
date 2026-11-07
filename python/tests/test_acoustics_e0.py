"""Deterministic, fast regression tests for PR-2 / E0 synthetic Doppler.

These tests pin the *measured* behavior of the estimator and the generator to
regression bounds. The bounds below are set 4-10x away from the values measured
in the E0 sweep (see ``docs/experiments/2026-11-04-e0-synthetic-doppler.md``);
they are regression guards, not new claims, and they are deliberately loose
enough that a numerically unchanged implementation passes on any platform.

The intended pre-declared "recovered" tolerances of the experiment are imported
from ``phaino_acoustics.experiment`` so a test cannot silently drift from the
report.
"""

from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pytest

from phaino_acoustics import (
    Scenario,
    doppler_frequency,
    estimate_if_track,
    fit_doppler,
    generate,
    naive_inversion,
)
from phaino_acoustics.experiment import (
    B_REL_TOL,
    F0_REL_TOL,
    T0_ABS_TOL,
    V_REL_TOL,
    run_sweep,
)
from phaino_acoustics.synthetic import range_and_radial_velocity


def _analyse(scenario: Scenario):
    """Generate, track, and fit one observation. Returns all intermediate pieces."""
    obs = generate(scenario)
    track = estimate_if_track(
        obs.signal, scenario.fs, t_start=float(obs.t[0])
    )
    truth = np.interp(track.t, obs.t, obs.f_apparent)
    fit = fit_doppler(track.t, track.f, c=scenario.c)
    b0 = naive_inversion(track.t, track.f, c=scenario.c)
    rel = {
        "f0": (fit.params["f0"] - scenario.f0) / scenario.f0,
        "v": (fit.params["v"] - scenario.v) / scenario.v,
        "b": (fit.params["b"] - scenario.b) / scenario.b,
        "t0_abs": fit.params["t0"] - scenario.t0,
    }
    b0_rel = {
        "f0": (b0.params["f0"] - scenario.f0) / scenario.f0,
        "v": (b0.params["v"] - scenario.v) / scenario.v,
        "b": (b0.params["b"] - scenario.b) / scenario.b,
        "t0_abs": b0.params["t0"] - scenario.t0,
    }
    return obs, track, truth, fit, b0, rel, b0_rel


BASE = Scenario()


# ---------------------------------------------------------------------------
# Generator / physical model sanity
# ---------------------------------------------------------------------------

def test_doppler_model_at_closest_approach_and_asymptotes():
    """At closest approach v_r = 0 so f = f0; asymptotes are f0/(1 -+ v/c)."""
    t = np.array([BASE.t0, BASE.t0 - 1e-9, BASE.t0 + 1e-9])
    f = doppler_frequency(t, BASE.f0, BASE.v, BASE.t0, BASE.b, BASE.c)
    assert np.allclose(f, BASE.f0, rtol=0, atol=1e-6)

    _, vr = range_and_radial_velocity(
        np.array([BASE.t0 - 1.0, BASE.t0, BASE.t0 + 1.0]), BASE.v, BASE.b, BASE.t0
    )
    assert vr[0] > 0.0          # approaching before closest approach
    assert abs(vr[1]) < 1e-12   # zero radial velocity at closest approach
    assert vr[2] < 0.0          # receding after

    far = np.array([BASE.t0 - 1e9, BASE.t0 + 1e9])
    f_far = doppler_frequency(far, BASE.f0, BASE.v, BASE.t0, BASE.b, BASE.c)
    assert f_far[0] == pytest.approx(BASE.f0 / (1.0 - BASE.v / BASE.c), rel=1e-12)
    assert f_far[1] == pytest.approx(BASE.f0 / (1.0 + BASE.v / BASE.c), rel=1e-12)


def test_snr_definition_is_realized_by_the_generator():
    """SNR_dB = 10 log10((A0^2/2)/sigma^2) must hold for the realized noise."""
    sc = replace(BASE, snr_db=5.0, seed=1)
    obs = generate(sc)
    sigma_expected = np.sqrt(0.5 * sc.amplitude**2 / 10.0 ** (sc.snr_db / 10.0))
    assert obs.noise_sigma == pytest.approx(sigma_expected, rel=1e-12)

    realized_noise = obs.signal - obs.clean
    realized_snr = 10.0 * np.log10(
        np.mean(obs.clean**2) / np.var(realized_noise, ddof=0)
    )
    # The generator records the target-sigma SNR; the realized noise realization
    # differs from its variance by finite-sample sampling error.
    assert realized_snr == pytest.approx(5.0, abs=0.05)
    assert obs.measured_snr_db == pytest.approx(5.0, abs=1e-3)
    assert obs.measured_snr_db == pytest.approx(
        10.0 * np.log10(np.mean(obs.clean**2) / obs.noise_sigma**2), rel=1e-12
    )


def test_generator_peak_near_f0_at_closest_approach():
    """A frame centred on t0 must show a spectral peak within a few Hz of f0."""
    obs, track, _, _, _, _, _ = _analyse(replace(BASE, snr_db=20.0, seed=0))
    i = int(np.argmin(np.abs(track.t - BASE.t0)))
    # The tone chirps ~1.9 Hz across the 64 ms frame at closest approach.
    assert track.f[i] == pytest.approx(BASE.f0, abs=3.0)


def test_deterministic_generation_and_fit():
    """Same seed => bit-identical observation record and identical fit record."""
    sc = replace(BASE, snr_db=5.0, seed=7)
    obs_a = generate(sc)
    obs_b = generate(sc)
    assert np.array_equal(obs_a.signal, obs_b.signal)
    assert np.array_equal(obs_a.f_apparent, obs_b.f_apparent)

    from phaino_acoustics.experiment import run_trial

    rec_a = run_trial("determinism", sc, trial=0, seed=20261104)
    rec_b = run_trial("determinism", sc, trial=0, seed=20261104)
    assert rec_a == rec_b
    # A different noise seed must produce a different observation record.
    rec_c = run_trial("determinism", sc, trial=0, seed=20261105)
    assert rec_c["if_rms_hz"] != rec_a["if_rms_hz"]


# ---------------------------------------------------------------------------
# Front end and estimator accuracy
# ---------------------------------------------------------------------------

def test_if_tracker_accuracy_at_20db():
    """Front end: measured IF error at 20 dB is ~0.17 Hz median, ~0.19 Hz RMS."""
    obs, track, truth, _, _, _, _ = _analyse(replace(BASE, snr_db=20.0, seed=0))
    err = track.f - truth
    assert np.median(np.abs(err)) < 0.5
    assert np.sqrt(np.mean(err**2)) < 1.0


def test_fit_recovers_parameters_on_clean_signal():
    """B1 must recover all four parameters on a 20 dB, 60 s observation."""
    sc = replace(BASE, snr_db=20.0, seed=0)
    _, _, _, fit, _, rel, _ = _analyse(sc)
    assert fit.converged
    assert fit.improvement_ratio > 0.999
    # Tight regression bounds (measured 1.5e-4, 9e-5, 0.0029 s, 2.6e-4).
    assert abs(rel["f0"]) < 1.0e-3
    assert abs(rel["v"]) < 1.0e-3
    assert abs(rel["t0_abs"]) < 0.02
    assert abs(rel["b"]) < 2.0e-3
    # And the pre-declared experiment tolerance must hold by a wide margin.
    assert abs(rel["f0"]) <= F0_REL_TOL
    assert abs(rel["v"]) <= V_REL_TOL
    assert abs(rel["t0_abs"]) <= T0_ABS_TOL
    assert abs(rel["b"]) <= B_REL_TOL


def test_naive_inversion_is_biased_by_window_truncation():
    """B0: measured v bias -7.19%, b bias about -20%, f0/t0 nearly unbiased."""
    sc = replace(BASE, snr_db=20.0, seed=0)
    _, _, _, fit, b0, _, rel0 = _analyse(sc)
    assert b0.valid
    assert -0.075 < rel0["v"] < -0.069       # predicted -7.2% from truncation
    assert rel0["b"] < -0.15                 # measured -19.3% for this seed
    assert abs(rel0["f0"]) < 1.0e-3          # algebraically unbiased
    assert abs(rel0["t0_abs"]) < 0.02
    assert b0.rms > 20.0 * fit.rms           # measured 55.4 Hz vs 0.19 Hz


def test_null_noise_only_observation_is_rejected():
    """Noise-only data: no Doppler acceptance, huge residuals, no recovery."""
    for seed in (0, 1, 2):
        sc = replace(BASE, emit_signal=False, snr_db=0.0, seed=seed)
        _, _, _, fit, _, rel, _ = _analyse(sc)
        assert fit.improvement_ratio < 0.05
        assert not (fit.converged and fit.improvement_ratio >= 0.5)
        assert fit.rms > 500.0
        assert abs(rel["f0"]) > F0_REL_TOL       # nowhere near the true state
        assert abs(rel["v"]) > V_REL_TOL
        assert abs(rel["b"]) > B_REL_TOL
        assert abs(rel["t0_abs"]) > T0_ABS_TOL


# ---------------------------------------------------------------------------
# Failure conditions: clock and window
# ---------------------------------------------------------------------------

def test_clock_rate_bias_matches_analytic_mapping():
    """eps = 1e-3 maps to f0*(1+eps), b/(1+eps), v unchanged, t0 shift -eps*t0."""
    eps = 1000.0e-6
    sc = replace(BASE, snr_db=20.0, seed=0, clock_scale_ppm=1000.0)
    _, _, _, fit, _, rel, _ = _analyse(sc)
    assert fit.converged
    assert rel["f0"] == pytest.approx(eps, abs=3.0e-4)
    assert rel["b"] == pytest.approx(-eps, abs=3.0e-4)
    assert abs(rel["v"]) < 2.0e-4                      # v is invariant
    expected_t0_shift = -eps * BASE.t0 / (1.0 + eps)   # on top of the base bias
    assert rel["t0_abs"] == pytest.approx(expected_t0_shift, abs=6.0e-3)


def test_clock_offset_is_absorbed_by_t0():
    """A constant clock offset is exactly degenerate with the event time."""
    delta = 2.0
    sc = replace(BASE, snr_db=20.0, seed=0, clock_offset_s=delta)
    _, _, _, fit, _, rel, _ = _analyse(sc)
    assert fit.converged
    assert rel["t0_abs"] == pytest.approx(-delta, abs=1.0e-2)
    assert abs(rel["f0"]) < 1.0e-3     # shape and scale unchanged
    assert abs(rel["v"]) < 1.0e-3
    assert abs(rel["b"]) < 1.0e-3


def test_short_window_is_structurally_degenerate():
    """T=5 s: measured |rho|(v,b) and |rho|(f0,t0) ~ 1, worst-direction SE ~ 15%."""
    sc = replace(BASE, duration=5.0, snr_db=5.0, seed=0)
    _, _, _, fit, _, _, _ = _analyse(sc)
    assert abs(fit.corr["v_b"]) > 0.99
    assert abs(fit.corr["f0_t0"]) > 0.99
    assert fit.worst_rel_se is not None and fit.worst_rel_se > 0.05
    assert fit.condition_number is not None and fit.condition_number > 1000.0


def test_short_window_failure_case_is_not_recovered():
    """Regression for a measured failure class: seed 20267116 at T=5 s, 5 dB."""
    sc = replace(BASE, duration=5.0, snr_db=5.0, seed=20267116)
    _, _, _, fit, _, rel, _ = _analyse(sc)
    assert fit.converged
    assert abs(rel["v"]) > V_REL_TOL or abs(rel["b"]) > B_REL_TOL
    assert abs(rel["b"]) > B_REL_TOL   # measured +7.4% for this seed


# ---------------------------------------------------------------------------
# Sweep runner: strict JSON and reproducible trial records
# ---------------------------------------------------------------------------

def test_sweep_runner_is_deterministic_and_json_strict():
    """A tiny sweep must emit strict JSON and the same digest on a rerun."""
    a = run_sweep(jobs=1, trials_override=1, name_filter="null", progress=False)
    b = run_sweep(jobs=1, trials_override=1, name_filter="null", progress=False)
    assert a["records_sha256"] == b["records_sha256"]
    assert len(a["trials"]) == 1
    payload = json.dumps(a, allow_nan=False, sort_keys=True)
    assert "NaN" not in payload and "Infinity" not in payload
