import math

import pytest

from phaino_c3.curve import (
    bootstrap_matched_difference,
    build_curve,
    matched_risk,
    severity,
    severity_components,
)


def record(lb_ratio=0.5, corr_ratio=0.5, acf_ratio=0.5, quad_ratio=0.5, phase_ratio=0.5):
    return {
        "adequacy": {
            "effective_thresholds": {
                "autocorrelation": {
                    "ljung_box_statistic_max": 100.0,
                    "max_abs_acf_max": 1.0,
                },
                "time_structure": {
                    "abs_corr_time_max": 0.1,
                    "abs_quadratic_coefficient_max": 0.2,
                    "abs_phase_correlation_max": 0.1,
                },
            },
            "key_metrics": {
                "autocorrelation": {
                    "ljung_box_statistic": 100.0 * lb_ratio,
                    "max_abs_acf": 1.0 * acf_ratio,
                },
                "time_structure": {
                    "corr_time": 0.1 * corr_ratio,
                    "quadratic_coefficient_over_sigma_f": 0.2 * quad_ratio,
                    "max_abs_phase_correlation": 0.1 * phase_ratio,
                },
            },
        }
    }


def trial(sev, correct, candidate="B0", mechanism="correct_cv"):
    return {
        "mechanism": mechanism,
        "evaluation_only": {"truth_correct": correct},
        "candidates": {candidate: record(lb_ratio=sev)},
    }


def test_severity_is_max_normalized_ratio():
    rec = record(lb_ratio=2.0, corr_ratio=0.5)
    assert severity(rec) == pytest.approx(2.0)
    comps = severity_components(rec)
    assert comps["ljung_box_statistic"] == pytest.approx(2.0)


def test_curve_monotonic_coverage_and_risk():
    trials = [trial(0.1, True), trial(0.2, True), trial(0.3, False), trial(0.4, False)]
    curve = build_curve(trials, "B0")
    assert curve["n"] == 4 and curve["n_wrong"] == 2
    cov = [p["coverage"] for p in curve["points"]]
    assert cov == sorted(cov)
    risks = [p["risk"] for p in curve["points"][1:]]
    assert risks[-1] == pytest.approx(0.5)
    assert risks[0] == 0.0


def test_matched_risk_interpolation():
    trials = [trial(0.1, True), trial(0.2, True), trial(0.3, False), trial(0.4, False)]
    curves = {"B0": build_curve(trials, "B0")}
    matched = matched_risk(curves, coverages=(0.5,), baseline="B0")
    assert matched["risk"]["B0"][0] == pytest.approx(0.0)
    assert matched["difference_vs_baseline"]["B0"][0] == pytest.approx(0.0)


def test_bootstrap_difference_deterministic():
    trials = []
    for i in range(20):
        trials.append(trial(0.1 + i * 0.01, i % 3 != 0))
    out1 = bootstrap_matched_difference(trials, "B0", "B0", replicates=50)
    out2 = bootstrap_matched_difference(trials, "B0", "B0", replicates=50)
    assert out1["difference"] == out2["difference"]
    for row in out1["difference"].values():
        assert row["mean"] == pytest.approx(0.0)


def test_bootstrap_requires_three_trials():
    with pytest.raises(ValueError):
        bootstrap_matched_difference([trial(0.1, True), trial(0.2, False)], "B0", "B0")
