"""Tests for the C2-A measurement-model / extraction-error analysis module.

Truth is used only inside the synthetic diagnostic; these tests pin the e(t)
definition, deterministic seeds, descriptive statistics, the empirical error
generator's determinism, and the property that no adequacy threshold constant is
touched.
"""

from __future__ import annotations

import copy
from dataclasses import replace

import numpy as np
import pytest

from phaino_acoustics import measurement_model as mm
from phaino_acoustics.adequacy_protocol import PROTOCOL
from phaino_acoustics.experiment import BASE
from phaino_acoustics.synthetic import Scenario, apparent_frequency, generate


def _scenario(seed: int = 424242, **overrides) -> Scenario:
    return replace(BASE, seed=seed, **overrides)


def test_measurement_model_record_is_declared():
    record = mm.measurement_model_record()
    assert record["id"] == mm.MEASUREMENT_MODEL_ID
    assert record["version"] == mm.MEASUREMENT_MODEL_VERSION
    assert record["front_end"]["frame_len"] == 512
    assert record["front_end"]["hop"] == 256
    assert record["front_end"]["window"] == "hann"
    assert record["error_model_id"]
    assert "truth" in record["notes"].lower()


def test_extraction_error_computation_and_determinism():
    scenario = _scenario()
    first = mm.extract_error_track(scenario)
    second = mm.extract_error_track(scenario)
    np.testing.assert_array_equal(first["error"], second["error"])
    np.testing.assert_allclose(
        first["error"],
        first["extracted_frequency"] - first["true_frequency"],
        rtol=0.0,
        atol=0.0,
    )
    # truth frequency is the generator's apparent frequency at the frame times
    np.testing.assert_allclose(
        first["true_frequency"],
        apparent_frequency(scenario, first["times"]),
        rtol=0.0,
        atol=0.0,
    )
    assert first["times"].shape == first["error"].shape
    assert np.all(np.isfinite(first["chirp_rate"]))
    assert np.all(np.isfinite(first["chirp_acceleration"]))


def test_summarise_track_on_a_known_error():
    n = 600
    times = np.linspace(0.0, 60.0, n)
    rng = np.random.default_rng(7)
    error = np.full(n, 1.0) + 0.1 * rng.standard_normal(n)
    sample = {
        "times": times,
        "error": error,
        "chirp_rate": np.zeros(n),
        "chirp_acceleration": np.zeros(n),
    }
    summary = mm.summarise_track(sample)
    assert summary["bias_hz"] == pytest.approx(float(np.mean(error)))
    assert summary["rms_hz"] == pytest.approx(float(np.sqrt(np.mean(error**2))))
    assert summary["std_hz"] == pytest.approx(float(np.std(error)))
    assert len(summary["bias_profile"]) == mm.TIME_BINS
    assert len(summary["time_bin_centers"]) == mm.TIME_BINS
    assert summary["acf_lag1"] is not None
    assert summary["residual_ar1"] is not None
    assert summary["n_samples"] == n
    # the constant bias dominates the time-bin profile
    assert all(value is None or abs(value - 1.0) < 0.2 for value in summary["bias_profile"])


def test_chirp_bins_and_conditional_error_are_declared_and_deterministic():
    edges = mm.chirp_bin_edges()
    assert edges == list(mm.CHIRP_EDGES_HZ_S)
    assert edges[0] < edges[-1]
    assert all(low < high for low, high in zip(edges, edges[1:]))

    n = 400
    samples = []
    for index, chirp_value in enumerate((0.8, 7.0, 40.0, 700.0)):
        samples.append(
            {
                "times": np.linspace(0.0, 60.0, n),
                "error": np.full(n, 0.25 * index - 0.2),
                "chirp_rate": np.full(n, chirp_value),
                "chirp_acceleration": np.full(n, 10.0 * index),
            }
        )
    first = mm.conditional_error_by_chirp(samples)
    second = mm.conditional_error_by_chirp(samples)
    assert first == second
    assert len(first) == len(edges) - 1
    assert sum(chirp_bin["n_samples"] for chirp_bin in first) == len(samples) * n


def test_structural_fraction_distinguishes_deterministic_and_noise():
    n = 300
    times = np.linspace(0.0, 60.0, n)
    deterministic = {
        "times": times,
        "error": np.sin(np.linspace(0.0, 6.0, n)),
        "chirp_rate": np.full(n, 5.0),
        "chirp_acceleration": np.zeros(n),
    }
    cell = {"cell_index": 0, "cell_id": "synthetic", "geometry_m": 600.0, "speed_m_s": 250.0, "snr_db": 20.0}
    identical = mm.aggregate_cell(cell, [deterministic, deterministic, deterministic], [mm.summarise_track(deterministic)] * 3)
    assert identical["structural_fraction"] == pytest.approx(1.0)
    noisy_samples = []
    rng = np.random.default_rng(11)
    for _ in range(3):
        noisy_samples.append({**deterministic, "error": deterministic["error"] + 0.5 * rng.standard_normal(n)})
    mixed = mm.aggregate_cell(cell, noisy_samples, [mm.summarise_track(sample) for sample in noisy_samples])
    assert 0.0 <= mixed["structural_fraction"] < 0.9


def test_empirical_error_model_template_is_deterministic():
    times = np.linspace(0.0, 60.0, 500)
    normalised = (times - times[0]) / (times[-1] - times[0])
    template = np.sin(2.0 * np.pi * normalised * 3.0)
    cell = {
        "cell_id": "b600_v250_snr20",
        "geometry_m": 600.0,
        "speed_m_s": 250.0,
        "snr_db": 20.0,
        "bias_profile": [0.1] * mm.TIME_BINS,
        "time_bin_centers": [(index + 0.5) / mm.TIME_BINS for index in range(mm.TIME_BINS)],
        "residual_std_hz": 0.2,
        "std_hz": 0.2,
        "residual_ar1_median": 0.3,
        "residual_template": {
            "normalised_time": [float(value) for value in normalised],
            "residual": [float(value) for value in template],
        },
    }
    model = mm.EmpiricalErrorModel([cell])
    first = model.generate(times, 600.0, 250.0, 20.0, seed=5)
    second = model.generate(times, 600.0, 250.0, 20.0, seed=5)
    third = model.generate(times, 600.0, 250.0, 20.0, seed=6)
    np.testing.assert_array_equal(first, second)
    assert not np.array_equal(first, third)
    assert first.size == times.size
    np.testing.assert_allclose(first, first, rtol=0.0, atol=0.0)
    # bias profile is reproduced; residual is scaled to the declared std
    assert float(np.mean(first)) == pytest.approx(0.1, abs=0.05)
    assert float(np.std(first)) == pytest.approx(0.2, rel=0.35)


def test_empirical_error_model_ar1_fallback_is_deterministic():
    times = np.linspace(0.0, 60.0, 400)
    cell = {
        "cell_id": "fallback",
        "geometry_m": 900.0,
        "speed_m_s": 250.0,
        "snr_db": 20.0,
        "bias_profile": [0.0] * mm.TIME_BINS,
        "time_bin_centers": [(index + 0.5) / mm.TIME_BINS for index in range(mm.TIME_BINS)],
        "residual_std_hz": 0.3,
        "std_hz": 0.3,
        "residual_ar1_median": 0.5,
        "residual_template": None,
    }
    model = mm.EmpiricalErrorModel([cell])
    first = model.generate(times, 900.0, 250.0, 20.0, seed=3)
    second = model.generate(times, 900.0, 250.0, 20.0, seed=3)
    np.testing.assert_array_equal(first, second)
    assert float(np.std(first)) == pytest.approx(0.3, rel=0.25)
    assert abs(float(np.corrcoef(first[:-1], first[1:])[0, 1]) - 0.5) < 0.2


def test_analysis_cells_seeds_and_design_are_declared():
    cells = mm.build_analysis_cells()
    assert len(cells) == len(mm.GEOMETRY_M) * len(mm.SPEEDS_M_S) * len(mm.SNR_LEVELS_DB)
    assert len({cell["cell_id"] for cell in cells}) == len(cells)
    assert cells[0]["geometry_m"] == mm.GEOMETRY_M[0]
    speeds = {cell["speed_m_s"] for cell in cells}
    assert speeds == set(mm.SPEEDS_M_S)
    snrs = {cell["snr_db"] for cell in cells}
    assert snrs == set(mm.SNR_LEVELS_DB)
    seeds = [mm.cell_seed(cell["cell_index"], trial) for cell in cells for trial in range(mm.N_PER_CELL)]
    assert len(seeds) == len(set(seeds))
    assert min(seeds) >= mm.SEED_BASE


def test_no_adequacy_threshold_constant_is_changed():
    before = copy.deepcopy(PROTOCOL)
    _ = mm.extract_error_track(_scenario(b=150.0))
    _ = mm.summarise_track(_)
    after = copy.deepcopy(PROTOCOL)
    assert before == after
