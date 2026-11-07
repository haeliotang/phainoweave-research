"""Tests for C2-M2 conditional measurement-error models.

Pins the new development design, phase/frame jitter, features (including the
FFT-bin-offset q hypothesis), hierarchical partial pooling, M0/M1/M2/M3
generator determinism, the pre-registered acceptance contract, and the absence
of adequacy-threshold changes.
"""

from __future__ import annotations

import copy
import json
from dataclasses import replace

import numpy as np
import pytest

from phaino_acoustics import measurement_error_models as mm
from phaino_acoustics.adequacy_protocol import PROTOCOL
from phaino_acoustics.experiment import BASE, HOP


def _cells():
    return mm.build_cells()


def _tracks(cell_count: int = 4, trials: int = 2):
    tracks = []
    for cell in _cells()[:cell_count]:
        for trial in range(trials):
            tracks.append(mm.generate_track(cell, trial))
    return tracks


def test_development_design_and_splits():
    cells = _cells()
    assert len(cells) == (len(mm.TRAIN_GEOMETRIES_M) + len(mm.HELD_OUT_GEOMETRIES_M)) * len(mm.SPEEDS_M_S) * len(mm.SNR_LEVELS_DB)
    train = [cell for cell in cells if cell.split == "train"]
    held = [cell for cell in cells if cell.split == "held_out"]
    assert {cell.geometry_m for cell in train} == set(mm.TRAIN_GEOMETRIES_M)
    assert {cell.geometry_m for cell in held} == set(mm.HELD_OUT_GEOMETRIES_M)
    assert {cell.speed_m_s for cell in cells} == set(mm.SPEEDS_M_S)
    assert {cell.snr_db for cell in cells} == set(mm.SNR_LEVELS_DB)
    seeds = [mm.cell_seed(cell, trial) for cell in cells for trial in range(mm.N_TRIALS_PER_CELL)]
    assert len(seeds) == len(set(seeds))
    assert min(seeds) >= mm.SEED_BASE > 70_000_000


def test_track_generation_has_phase_and_frame_jitter_and_is_deterministic():
    cell = _cells()[0]
    first = mm.generate_track(cell, 0)
    second = mm.generate_track(cell, 0)
    np.testing.assert_array_equal(first["estimated_frequency"], second["estimated_frequency"])
    assert first["phase0"] == second["phase0"]
    assert first["frame_offset_samples"] == second["frame_offset_samples"]
    assert 0 <= first["frame_offset_samples"] < HOP
    assert 0.0 <= first["phase0"] < 2.0 * np.pi
    # different trials have different phase/alignment realisations
    other = mm.generate_track(cell, 1)
    assert other["phase0"] != first["phase0"] or other["frame_offset_samples"] != first["frame_offset_samples"]


def test_features_include_q_and_runtime_observables():
    cell = _cells()[0]
    track = mm.generate_track(cell, 0)
    features = track["features"]
    n = track["times"].size
    for name in ("q_hat", "q_sin", "q_cos", "chirp", "abs_chirp", "curvature", "frame_position", "freq_position", "quality_db"):
        assert features[name].shape == (n,), name
    assert np.all((features["q_hat"] >= 0.0) & (features["q_hat"] < 1.0))
    assert np.all((features["q_true"] >= 0.0) & (features["q_true"] < 1.0))
    np.testing.assert_allclose(features["error"], track["estimated_frequency"] - track["true_frequency"], rtol=0.0, atol=0.0)
    # q_true is diagnostic only and is not a deployment feature
    assert "q_true" not in mm.FEATURE_ABLATION[0][1]
    for _name, feature_names in mm.FEATURE_ABLATION:
        assert "q_true" not in feature_names


def test_fft_bin_offset_diagnostic_is_deterministic():
    tracks = _tracks(cell_count=2, trials=2)
    first = mm.fft_bin_offset_diagnostic(tracks)
    second = mm.fft_bin_offset_diagnostic(tracks)
    assert first == second
    assert len(first["q_bins"]) == mm.Q_BINS
    assert sum(bin_row["n_samples"] for bin_row in first["q_bins"]) > 0
    assert first["q_true_polynomial_fit"]["r_squared"] is not None
    assert "diagnostic reference only" in first["truth_usage"]


def test_hierarchical_mean_fit_predict_and_ablation_deterministic():
    tracks = _tracks(cell_count=6, trials=2)
    model = mm.fit_hierarchical_mean(tracks, ("q_hat", "abs_chirp"))
    assert model["feature_names"] == ["q_hat", "abs_chirp"]
    assert len(model["geometry_intercepts"]) >= 1
    assert model["pooling"].startswith("partial")
    predicted_first = mm.predict_mean(model, tracks[0]["features"])
    predicted_second = mm.predict_mean(model, tracks[0]["features"])
    np.testing.assert_array_equal(predicted_first, predicted_second)
    assert predicted_first.shape == tracks[0]["features"]["error"].shape
    ablation = mm.select_feature_set(tracks)
    assert ablation["selected"] in {name for name, _ in mm.FEATURE_ABLATION}
    assert ablation["selected_features"] == [row for row in ablation["table"] if row["name"] == ablation["selected"]][0]["features"]
    assert ablation == mm.select_feature_set(tracks)


def test_m0_m1_m2_m3_generators_are_deterministic():
    tracks = _tracks(cell_count=6, trials=2)
    m0 = mm.fit_m0(tracks)
    m2 = mm.fit_hierarchical_mean(tracks, ("q_hat", "abs_chirp"))
    m1 = mm.build_m1_model(tracks)
    m3 = mm.fit_m3(tracks, m2)
    times = tracks[0]["times"]
    speed, snr = tracks[0]["cell"].speed_m_s, tracks[0]["cell"].snr_db
    m0_first = mm.generate_m0(m0, times, speed, snr, seed=7)
    m0_second = mm.generate_m0(m0, times, speed, snr, seed=7)
    np.testing.assert_array_equal(m0_first, m0_second)
    m1_first = mm.generate_m1(m1, times, tracks[0]["cell"].geometry_m, speed, snr, seed=7)
    m1_second = mm.generate_m1(m1, times, tracks[0]["cell"].geometry_m, speed, snr, seed=7)
    np.testing.assert_array_equal(m1_first, m1_second)
    m2_first = mm.generate_m2_error(m2, tracks[0]["features"], times, speed, snr, m0, seed=7)
    m2_second = mm.generate_m2_error(m2, tracks[0]["features"], times, speed, snr, m0, seed=7)
    np.testing.assert_array_equal(m2_first, m2_second)
    m3_first = mm.generate_m3(m3, times, tracks[0]["features"], speed, snr, seed=7)
    m3_second = mm.generate_m3(m3, times, tracks[0]["features"], speed, snr, seed=7)
    np.testing.assert_array_equal(m3_first, m3_second)
    assert m3_first.shape == times.shape
    assert float(np.std(m3_first)) > 0.0


def test_acceptance_contract_is_pre_registered_and_threshold_free():
    contract = mm.acceptance_contract()
    assert contract["frozen_before_held_out_scoring"] is True
    tolerances = contract["tolerances"]
    for key in ("frr_gap_max_pp_per_geometry", "lb_quantile_relative_gap_max", "mean_bias_gap_max_hz", "variance_ratio_range", "acf_lag1_gap_max"):
        assert key in tolerances
    assert "never 'explained" in contract["tolerances"]["language_rule"] or "explained" in contract["tolerances"]["language_rule"]
    assert contract["models"] == ["M0", "M1", "M2", "M3"]
    assert "truth" not in contract["selection_rule"].lower() or "held-out" in contract["selection_rule"]


def test_no_adequacy_threshold_constants_changed():
    before = copy.deepcopy(PROTOCOL)
    tracks = _tracks(cell_count=2, trials=1)
    _ = mm.fit_m0(tracks)
    _ = mm.fit_hierarchical_mean(tracks, ("q_hat",))
    after = copy.deepcopy(PROTOCOL)
    assert before == after
