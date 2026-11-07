"""Tests for the E0 sweep config path used by PR-3 offline replay.

The config path exists so a pinned ``config.json`` snapshot can drive the sweep
through ``--config``.  These tests check two properties:

1. Round trip: the frozen default config reconstructs exactly the in-memory
   condition list, so passing ``default_config()`` through ``--config`` cannot
   change the golden ``records_sha256``.
2. Tiny config: the function API accepts a small config (one condition, two
   trials) and returns the same result schema.  The full sweep is never run in
   tests.

No test pins the golden digest itself: that is checked by the offline replay in
``crates/phaino-cli`` (PR-3), not by a unit test.
"""

from __future__ import annotations

import json

import pytest

from phaino_acoustics.experiment import (
    CONFIG_SCHEMA_VERSION,
    EXPERIMENT_NAME,
    N_TRIALS,
    SEED_BASE,
    build_conditions,
    config_from_conditions,
    conditions_from_config,
    default_config,
    load_config,
    run_sweep,
)


def test_default_config_round_trips_to_the_in_memory_grid():
    """A JSON round trip of the frozen config equals ``build_conditions()``."""
    config = json.loads(json.dumps(default_config()))
    conditions, seed_base = conditions_from_config(config)
    assert conditions == build_conditions()
    assert seed_base == SEED_BASE


def test_default_config_re_serializes_identically():
    """Serializing the reconstructed grid reproduces the same config document."""
    config = default_config()
    conditions, seed_base = conditions_from_config(config)
    assert config_from_conditions(conditions, seed_base=seed_base) == config


def test_default_config_describes_the_frozen_e0_grid():
    config = default_config()
    assert config["schema_version"] == CONFIG_SCHEMA_VERSION
    assert config["experiment"] == EXPERIMENT_NAME
    assert config["seed_base"] == SEED_BASE
    assert len(config["conditions"]) == 25
    assert {c["n_trials"] for c in config["conditions"]} == {N_TRIALS}
    # Overrides are relative to the base geometry, so equal-to-base fields are absent.
    assert all(
        set(c["scenario"]) <= set(config["base_geometry"]) for c in config["conditions"]
    )
    # The null control is a generator setting, not emitted signal.
    null = next(c for c in config["conditions"] if c["name"] == "null_noise_only")
    assert null["scenario"] == {"emit_signal": False, "snr_db": 0.0}


def test_load_config_reads_a_file(tmp_path):
    path = tmp_path / "e0-config.json"
    path.write_text(json.dumps(default_config()), encoding="utf-8")
    loaded = load_config(str(path))
    conditions, seed_base = conditions_from_config(loaded)
    assert conditions == build_conditions()
    assert seed_base == SEED_BASE


def test_tiny_config_runs_through_the_function_api():
    """One condition x two trials keeps the result schema and the seed formula."""
    tiny = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "experiment": EXPERIMENT_NAME,
        "seed_base": 1234,
        "base_geometry": {"snr_db": 20.0},
        "conditions": [
            {
                "name": "tiny_null",
                "group": "null",
                "note": "noise-only control",
                "n_trials": 2,
                "scenario": {"emit_signal": False},
            }
        ],
    }
    result = run_sweep(jobs=1, config=tiny, progress=False)

    assert set(result) >= {
        "experiment",
        "generated_at_utc",
        "config",
        "environment",
        "elapsed_s",
        "records_sha256",
        "conditions",
        "trials",
    }
    assert result["experiment"] == EXPERIMENT_NAME
    assert result["config"]["n_conditions"] == 1
    assert result["config"]["n_trials_per_condition"] == 2
    assert result["config"]["seed_formula"].startswith("seed = 1234 +")
    assert len(result["conditions"]) == 1
    assert len(result["trials"]) == 2

    records = result["trials"]
    assert [record["trial"] for record in records] == [0, 1]
    assert [record["seed"] for record in records] == [1234, 1235]
    for record in records:
        assert record["condition"] == "tiny_null"
        assert set(record) >= {"condition", "trial", "seed", "if_rms_hz", "b1", "b0", "accepted"}
        assert set(record["b1"]) >= {"params", "rel", "within_tol", "success", "converged"}
        assert set(record["b0"]) >= {"params", "rel", "within_tol", "success", "valid"}
    assert len(result["records_sha256"]) == 64


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda cfg: cfg.update(schema_version=99), "schema_version"),
        (lambda cfg: cfg.update(experiment="not-e0"), "experiment"),
        (
            lambda cfg: cfg["conditions"][0].update(scenario={"no_such_field": 1}),
            "unknown Scenario field",
        ),
        (
            lambda cfg: cfg["conditions"].append(dict(cfg["conditions"][0])),
            "duplicate condition name",
        ),
        (lambda cfg: cfg["conditions"][0].update(n_trials=0), "n_trials"),
        (lambda cfg: cfg.update(seed_base=-1), "seed_base"),
        (lambda cfg: cfg.update(conditions=[]), "non-empty"),
    ],
)
def test_malformed_config_is_rejected(mutate, message):
    config = default_config()
    mutate(config)
    with pytest.raises(ValueError, match=message):
        conditions_from_config(config)
