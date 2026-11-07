import math

import numpy as np
import pytest

from phaino_bench.analysis import (
    clock_regression,
    downstream_error_impact,
    estimate_tone_frequency,
    signal_chain_difference,
    tone_accuracy,
    two_anchor_rate_uncertainty,
    window_sweep,
)
from phaino_bench.schema import BenchSession, Capture, validate_session


def tone(freq, fs=8000, seconds=1.0, phase=0.0):
    t = np.arange(int(fs * seconds)) / fs
    return np.sin(2 * math.pi * freq * t + phase)


def test_tone_frequency_accuracy_and_ci():
    fs, f0 = 8000.0, 500.0
    estimates = [estimate_tone_frequency(tone(f0 + 2.9, fs, 0.5, phase=p), fs) for p in (0.0, 0.7, 1.4)]
    result = tone_accuracy(estimates, f0 + 2.9)
    assert result["n"] == 3
    assert abs(result["bias_hz"]) < 0.5
    assert result["ci95_mean_hz"][0] <= result["mean_hz"] <= result["ci95_mean_hz"][1]


def test_window_sweep_reports_bins_latency_and_bias():
    rows = window_sweep(tone(502.9, 8000.0, 1.0), 8000.0, 502.9, windows=(512, 1024, 2048))
    assert [r["window"] for r in rows] == [512, 1024, 2048]
    assert rows[0]["bin_hz"] == pytest.approx(15.625)
    assert rows[1]["bin_hz"] == pytest.approx(7.8125)
    assert all(math.isfinite(r["bias_hz"]) for r in rows)
    assert rows[2]["latency_s"] > rows[0]["latency_s"]


def test_two_anchor_uncertainty():
    # 1 ms per-anchor error over 150 s separation -> ~9.4e-6
    assert two_anchor_rate_uncertainty(1e-3, 150.0) == pytest.approx(9.428e-6, rel=1e-3)
    with pytest.raises(ValueError):
        two_anchor_rate_uncertainty(1e-3, 0.0)


def test_clock_regression_recovers_rate_and_offset():
    rng = np.random.default_rng(7)
    t_ref = np.linspace(0.0, 150.0, 8)
    alpha, beta = 1.000012, 0.002
    observed = alpha * t_ref + beta + rng.normal(0, 5e-5, t_ref.size)
    result = clock_regression(t_ref, observed)
    assert result["alpha"] == pytest.approx(alpha, abs=5e-5)
    assert result["beta_s"] == pytest.approx(beta, abs=2e-4)
    assert result["sigma_alpha"] > 0
    assert result["alpha_ci95"][0] < alpha < result["alpha_ci95"][1]


def test_clock_regression_needs_three_anchors():
    with pytest.raises(ValueError):
        clock_regression([0.0, 1.0], [0.0, 1.0])


def test_signal_chain_and_downstream():
    direct = {"bias_hz": 0.1, "variance_hz2": 1e-4}
    acoustic = {"bias_hz": 0.4, "variance_hz2": 4e-4}
    diff = signal_chain_difference(direct, acoustic)
    assert diff["bias_difference_hz"] == pytest.approx(0.3)
    assert diff["variance_ratio"] == pytest.approx(4.0)
    impact = downstream_error_impact(0.4, 0.25)
    assert impact["could_flip_decision"] is True


def test_session_split_validation():
    captures = [
        Capture("c1", "calibration", "tone", "/tmp/a.wav", "a" * 64, 8000),
        Capture("c2", "evaluation", "tone", "/tmp/b.wav", "b" * 64, 8000),
    ]
    good = BenchSession("s1", "mm-1", {}, {}, {}, captures, ["c1"], ["c2"])
    validate_session(good)
    bad = BenchSession("s1", "mm-1", {}, {}, {}, captures, ["c1"], ["c1"])
    with pytest.raises(ValueError):
        validate_session(bad)
    with pytest.raises(ValueError):
        validate_session(BenchSession("s1", "mm-1", {}, {}, {}, captures, ["cx"], []))


def test_session_rejects_duplicate_capture_ids():
    captures = [
        Capture("c1", "calibration", "tone", "/tmp/a.wav", "a" * 64, 8000),
        Capture("c1", "evaluation", "tone", "/tmp/b.wav", "b" * 64, 8000),
    ]
    with pytest.raises(ValueError):
        validate_session(BenchSession("s1", "mm-1", {}, {}, {}, captures, ["c1"], []))
