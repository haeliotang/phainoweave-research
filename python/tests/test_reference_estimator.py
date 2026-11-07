"""Tests for the non-competing phase-difference reference estimator.

Pins the estimator's documented phase-difference relation on a stationary tone,
its determinism, the evaluation-cell design, seed independence, and the property
that it does not touch adequacy thresholds or the sealed C2-C grid.
"""

from __future__ import annotations

import copy
import json
import pathlib

import numpy as np
import pytest

from phaino_acoustics import measurement_model_reference as reference
from phaino_acoustics.adequacy_protocol import PROTOCOL


def test_phase_difference_recovers_a_stationary_tone():
    fs = 8000.0
    frame_len = 512
    hop = 128
    duration = 4.0
    t = np.arange(int(duration * fs)) / fs
    frequency = 1000.0
    signal = np.cos(2.0 * np.pi * frequency * t)
    track = reference.estimate_reference_track(signal, fs, frame_len=frame_len, hop=hop, t_start=0.0)
    times = np.asarray(track["t"])
    frequencies = np.asarray(track["f"])
    assert times.size == frequencies.size
    assert times.size > 10
    # exclude the first frame (no phase reference) and edge frames of the tone
    interior = frequencies[2:-2]
    assert float(np.median(np.abs(interior - frequency))) < 0.5
    assert float(np.percentile(np.abs(interior - frequency), 90)) < 1.0


def test_phase_difference_estimator_is_deterministic_on_a_doppler_scenario():
    from phaino_acoustics.experiment import BASE
    from phaino_acoustics.synthetic import Scenario, apparent_frequency, generate

    scenario = Scenario(**{**BASE.__dict__, "b": 600.0, "seed": 12345})
    observation = generate(scenario)
    first = reference.estimate_reference_track(observation.signal, scenario.fs, t_start=float(observation.t[0]))
    second = reference.estimate_reference_track(observation.signal, scenario.fs, t_start=float(observation.t[0]))
    np.testing.assert_array_equal(first["t"], second["t"])
    np.testing.assert_array_equal(first["f"], second["f"])
    true_frequency = apparent_frequency(scenario, first["t"])
    error_rms = float(np.sqrt(np.mean((first["f"] - true_frequency) ** 2)))
    assert error_rms < 2.0  # small relative to the ~500 Hz carrier and bin width 15.6 Hz
    assert first["estimator"] == reference.REFERENCE_ID


def test_reference_cells_and_seeds_are_declared():
    cells = reference.build_reference_cells()
    correct = [cell for cell in cells if cell["family"] == "correct_constant_velocity"]
    accel = [cell for cell in cells if cell["family"] == "acceleration_misspecification"]
    assert len(correct) == len(reference.CORRECT_CV_GEOMETRIES_M)
    assert len(accel) == len(reference.ACCELERATION_LEVELS_M_S2)
    assert {cell["geometry_m"] for cell in correct} == set(reference.CORRECT_CV_GEOMETRIES_M)
    assert {cell["accel"] for cell in accel} == set(reference.ACCELERATION_LEVELS_M_S2)
    seeds = [reference.cell_seed(cell, trial) for cell in cells for trial in range(reference.REFERENCE_N_TRIALS)]
    assert len(seeds) == len(set(seeds))
    assert min(seeds) >= reference.REFERENCE_SEED_BASE > 80_000_000


def test_reference_worker_returns_adequacy_and_error_metrics():
    cell = reference.build_reference_cells()[0]
    record = reference._worker((cell, 0, "phase_difference"))
    assert record["estimator"] == "phase_difference"
    assert record["adequacy_status"] in ("adequate", "discrepancy", "insufficient_evidence", "indeterminate")
    assert record["error_rms_hz"] >= 0.0
    assert record["n_frames"] > 0
    assert set(record["parameter_rel_errors"]) == {"f0", "v", "t0", "b"}
    front = reference._worker((cell, 0, "front_end"))
    assert front["estimator"] == "front_end"
    assert front["error_rms_hz"] >= 0.0


def test_no_adequacy_threshold_or_sealed_grid_is_touched():
    before = copy.deepcopy(PROTOCOL)
    cell = reference.build_reference_cells()[0]
    reference._worker((cell, 0, "phase_difference"))
    after = copy.deepcopy(PROTOCOL)
    assert before == after
    source = pathlib.Path(reference.__file__).read_text(encoding="utf-8")
    assert "pr4e-c2c" not in source
    assert "thresholds_changed" in source
