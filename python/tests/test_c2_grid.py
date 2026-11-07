"""Tests for the frozen C2-C validation grid definition.

The grid is a frozen input for the later paired B0-B3 comparison: no repair is
run here.  These tests pin the continuum, strata, seeds, paired design, the
runtime-observable-only selection rule and the digest stability.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest

from phaino_acoustics import c2_grid

REPO = pathlib.Path(__file__).resolve().parents[2]


def test_grid_digest_is_deterministic_and_self_verifying():
    first = c2_grid.build_grid()
    second = c2_grid.build_grid()
    assert first["grid_digest"] == second["grid_digest"]
    assert len(first["grid_digest"]) == 64
    assert c2_grid.verify_grid_digest(first)
    round_tripped = json.loads(json.dumps(first))
    assert c2_grid.verify_grid_digest(round_tripped)
    assert c2_grid.grid_digest(round_tripped) == first["grid_digest"]


def test_grid_definition_excludes_results_and_environment():
    grid = c2_grid.build_grid()
    definition = c2_grid.grid_definition(grid)
    assert "grid_digest" not in definition
    for forbidden in ("results", "environment", "generated_at_utc", "elapsed_s", "records_sha256"):
        assert forbidden not in definition


def test_grid_continuum_and_levels():
    grid = c2_grid.build_grid()
    geometry = grid["geometry_m"]
    assert len(geometry) == 11
    assert geometry[0] == 120.0 and geometry[-1] == 7000.0
    assert all(low < high for low, high in zip(geometry, geometry[1:]))
    ratios = [high / low for low, high in zip(geometry, geometry[1:])]
    assert max(ratios) < 2.0  # dense log-spaced continuum, not only endpoints
    assert grid["speeds_m_s"] == list(c2_grid.SPEEDS_M_S)
    assert grid["snr_levels_db"] == list(c2_grid.SNR_LEVELS_DB)
    assert grid["acceleration_levels_m_s2"] == list(c2_grid.ACCELERATION_LEVELS_M_S2)
    # new acceleration levels, not the C2 diagnosis levels 0.2/0.4
    assert 0.2 not in grid["acceleration_levels_m_s2"]
    assert 0.4 not in grid["acceleration_levels_m_s2"]


def test_grid_condition_and_stratum_counts():
    grid = c2_grid.build_grid()
    assert grid["condition_count"] == 59
    assert grid["trial_count"] == 566
    assert grid["strata_counts"] == {
        "correct_cv_continuum": 330,
        "correct_cv_low_snr": 96,
        "acceleration_misspecification": 120,
        "noise_only_null": 20,
    }
    assert set(grid["family_counts"]) == {
        "cv_continuum",
        "cv_continuum_low_snr",
        "acceleration_continuum",
        "null",
    }
    assert grid["c2_diagnosis_trials_reused"] is False
    for condition in grid["conditions"]:
        assert condition["n_trials"] > 0
        assert condition["stratum"] in c2_grid.STRATA
        scenario = condition["scenario"]
        assert scenario["duration"] > 0 and scenario["fs"] > 0
    # acceleration conditions use only the new levels
    accel_levels = {
        condition["scenario"]["accel"]
        for condition in grid["conditions"]
        if condition["stratum"] == "acceleration_misspecification"
    }
    assert accel_levels == set(c2_grid.ACCELERATION_LEVELS_M_S2)


def test_seed_base_is_new_and_trial_seeds_are_deterministic_and_unique():
    grid = c2_grid.build_grid()
    trials = list(c2_grid.iter_trials(grid))
    assert len(trials) == grid["trial_count"]
    seeds = [trial["seed"] for trial in trials]
    assert len(seeds) == len(set(seeds))
    assert min(seeds) >= c2_grid.SEED_BASE > 50_000_000
    assert max(seeds) < 61_000_000  # disjoint from the C2-A/B base (70M) and all earlier bases
    assert c2_grid.SEED_BASE not in (20_261_104, 20_300_000, 40_000_000, 41_000_000, 50_000_000, 70_000_000)
    for trial in trials:
        condition = grid["conditions"][trial["condition_index"]]
        assert trial["seed"] == condition["seed_base"] + trial["trial"]
    assert [trial["seed"] for trial in list(c2_grid.iter_trials(grid))] == seeds


def test_grid_digest_changes_when_the_definition_changes(tmp_path):
    grid = c2_grid.build_grid()
    baseline = grid["grid_digest"]
    mutated = json.loads(json.dumps(grid))
    mutated["conditions"][0]["scenario"]["b"] = 9999.0
    assert c2_grid.grid_digest(mutated) != baseline
    path = tmp_path / "c2c-grid.json"
    c2_grid.write_grid(grid, str(path))
    loaded = c2_grid.load_grid(str(path))
    assert loaded["grid_digest"] == baseline
    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["conditions"][0]["scenario"]["b"] = 9999.0
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError):
        c2_grid.load_grid(str(path))


def test_paired_design_and_candidates_are_declared():
    grid = c2_grid.build_grid()
    assert grid["paired_design"] is True
    assert grid["candidates"] == ["B0", "B1", "B2", "B3"]
    assert grid["candidate_combination_before_independent_results"] is False
    for candidate in grid["candidates"]:
        assert candidate in grid["candidate_descriptions"]
        assert "NOT implemented" in grid["candidate_descriptions"][candidate] or candidate == "B0"
    # No candidate run is part of the grid artifact.
    assert "records_sha256" not in grid
    assert "results" not in grid


def test_selection_inputs_are_runtime_observable_only():
    assertion = c2_grid.assert_selection_inputs_runtime_only()
    assert assertion["runtime_observable_only"] is True
    assert set(assertion["allowed"]) == set(c2_grid.RUNTIME_OBSERVABLE_SELECTION_INPUTS)
    assert set(assertion["forbidden"]) == set(c2_grid.FORBIDDEN_SELECTION_INPUTS)
    assert assertion["overlap"] == []
    allowed = set(c2_grid.RUNTIME_OBSERVABLE_SELECTION_INPUTS)
    assert "true_closest_approach_b" not in allowed
    assert "true_acceleration" not in allowed
    assert "scenario_label" not in allowed
    for truth_field in ("true_closest_approach_b", "true_acceleration", "true_speed", "mechanism_label"):
        assert truth_field in c2_grid.FORBIDDEN_SELECTION_INPUTS
    grid = c2_grid.build_grid()
    assert grid["runtime_observable_selection_inputs"] == list(c2_grid.RUNTIME_OBSERVABLE_SELECTION_INPUTS)
    assert grid["forbidden_selection_inputs"] == list(c2_grid.FORBIDDEN_SELECTION_INPUTS)
    assert grid["selection_inputs_runtime_only"] is True
    assert grid["truth_fields_forbidden_as_selection"] is True


def test_grid_module_does_not_run_repairs():
    source = (REPO / "python" / "phaino_acoustics" / "c2_grid.py").read_text(encoding="utf-8")
    for imported in ("fit_hardened", "evaluate_adequacy", "experiment_c2a", "experiment_adequacy"):
        assert imported not in source
    import sys

    assert "phaino_acoustics.experiment_c2a" not in sys.modules
