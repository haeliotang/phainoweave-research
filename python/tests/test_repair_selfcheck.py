"""Tests for the ADR 0023 B1 self-confirmation diagnostics.

Fast unit tests pin the biased-model arithmetic, the B1-with-model record,
time-block block accounting, the outcome taxonomy (separate, never pooled),
B3 per-bin grouping + SNR-branch declaration, and the development-only/no-sealed
grid guard.  The full development run is exercised once by the CLI, not here.
"""

from __future__ import annotations

import copy
import pathlib

import numpy as np
import pytest

from phaino_acoustics import repair_selfcheck as selfcheck
from phaino_acoustics.adequacy_protocol import PROTOCOL
from phaino_acoustics.experiment import BASE
from phaino_acoustics.repair_candidates import B3_CHIRP_EDGES_HZ_S
from phaino_acoustics.synthetic import Scenario, generate


def _scenario(geometry: float = 150.0, speed: float = 250.0, seed: int = 92_000_000) -> Scenario:
    return Scenario(**{**BASE.__dict__, "b": geometry, "v": speed, "snr_db": 20.0, "seed": seed})


def test_biased_model_parameters():
    params = {"f0": 500.0, "v": 200.0, "t0": 20.0, "b": 1000.0}
    correct = selfcheck.biased_model_params(params, "correct_model")
    np.testing.assert_allclose(correct, [500.0, 200.0, 20.0, 1000.0])
    speed = selfcheck.biased_model_params(params, "speed_plus_20pct")
    assert speed[1] == pytest.approx(240.0)
    closest = selfcheck.biased_model_params(params, "closest_approach_plus_30pct")
    assert closest[3] == pytest.approx(1300.0)
    with pytest.raises(ValueError):
        selfcheck.biased_model_params(params, "not_a_model")


def test_b1_with_model_is_deterministic_and_shape_complete():
    scenario = _scenario()
    observation = generate(scenario)
    from phaino_acoustics.experiment import F_MAX, F_MIN, FRAME_LEN, HOP
    from phaino_acoustics.features import estimate_if_track

    track = estimate_if_track(
        observation.signal, scenario.fs, frame_len=FRAME_LEN, hop=HOP, f_min=F_MIN, f_max=F_MAX,
        t_start=float(observation.t[0]),
    )
    from phaino_acoustics.fit_hardened import fit_hardened

    base = fit_hardened(track.t, track.f, c=scenario.c)
    params = np.array([base.f0, base.v, base.t0, base.b])
    first = selfcheck._b1_with_model(observation, track.t, params, scenario.c, scenario.fs)
    second = selfcheck._b1_with_model(observation, track.t, params, scenario.c, scenario.fs)
    assert first == second
    assert first["decision"] in ("accept", "reject", "undetermined")
    assert first["status"] in ("adequate", "discrepancy", "insufficient_evidence", "indeterminate")
    assert first["residual_rms_hz"] is not None and first["residual_rms_hz"] >= 0.0
    assert set(first["params"]) == {"f0", "v", "t0", "b"}
    biased = selfcheck.biased_model_params(params, "closest_approach_plus_30pct")
    wrong = selfcheck._b1_with_model(observation, track.t, biased, scenario.c, scenario.fs)
    assert wrong["transform_failed"] is False
    assert wrong["residual_rms_hz"] is not None


def test_parameter_errors_and_wilson_blocks():
    truth = {"f0": 500.0, "v": 250.0, "t0": 20.0, "b": 1000.0}
    params = {"f0": 505.0, "v": 245.0, "t0": 20.2, "b": 990.0}
    errors = selfcheck._parameter_errors(params, truth)
    assert errors["f0"] == pytest.approx(0.01)
    assert errors["v"] == pytest.approx(-0.02)
    assert errors["t0_abs"] == pytest.approx(0.2)
    assert errors["b"] == pytest.approx(-0.01)
    block = selfcheck.rate_block(0, 10)
    assert block["k"] == 0 and block["n"] == 10 and block["rate"] == 0.0
    assert block["zero_event_upper95"] is not None and 0.0 < block["zero_event_upper95"] < 1.0
    assert block["wilson95"][0] == 0.0
    middle = selfcheck.rate_block(5, 10)
    assert middle["rate"] == 0.5


def _trial(mechanism: str, decisions: dict[str, str], truth_correct: bool = True, chirp: float = 100.0, snr: float = 20.0) -> dict:
    return {
        "mechanism": mechanism,
        "condition": f"c_{mechanism}",
        "stratum": mechanism,
        "runtime_observables": {"estimated_chirp_rate_hz_s": chirp, "estimated_snr_db": snr},
        "evaluation_only": {
            "estimate_within_tolerance": {
                "f0": truth_correct, "v": truth_correct, "t0": truth_correct, "b": truth_correct, "f0_times_b": truth_correct
            }
        },
        "candidates": {
            candidate: {"decision": decisions.get(candidate, "undetermined")}
            for candidate in ("B0", "B1", "B2", "B3")
        },
    }


def test_outcome_taxonomy_counts_are_separate_and_not_pooled():
    trials = [
        _trial("correct_cv", {"B0": "accept", "B1": "accept"}, truth_correct=True),
        _trial("correct_cv", {"B0": "reject", "B1": "accept"}, truth_correct=True),
        _trial("correct_cv", {"B0": "undetermined", "B1": "reject"}, truth_correct=True),
        _trial("acceleration", {"B0": "reject", "B1": "undetermined"}),
        _trial("acceleration", {"B0": "accept", "B1": "reject"}),
        _trial("null", {"B0": "accept", "B1": "undetermined"}),
    ]
    taxonomy = selfcheck.outcome_taxonomy(trials)
    assert taxonomy["correct_model"]["denominator"] == 3
    assert taxonomy["acceleration"]["denominator"] == 2
    assert taxonomy["null"]["denominator"] == 1
    b0 = taxonomy["candidates"]["B0"]
    assert b0["correct_model"]["supported_coverage"]["k"] == 1
    assert b0["correct_model"]["false_rejection"]["k"] == 1
    assert b0["correct_model"]["abstention"]["k"] == 1
    assert b0["acceleration"]["discrepancy_detected"]["k"] == 1
    assert b0["acceleration"]["undetermined"]["k"] == 0
    assert b0["acceleration"]["false_supported"]["k"] == 1
    assert b0["null"]["promoted_valid_event"]["k"] == 1
    b1 = taxonomy["candidates"]["B1"]
    assert b1["correct_model"]["supported_coverage"]["k"] == 2
    assert b1["correct_model"]["false_rejection"]["k"] == 1
    assert b1["correct_model"]["abstention"]["k"] == 0
    assert b1["acceleration"]["undetermined"]["k"] == 1
    assert b1["null"]["promoted_valid_event"]["k"] == 0
    # key invariant: taxonomy entries are not pooled into one accuracy
    assert "accuracy" not in str(taxonomy).lower()


def test_b3_per_chirp_bin_power_and_snr_declaration():
    # one correct-model trial per chirp bin, one acceleration trial at low chirp
    trials = []
    for index, chirp in enumerate((10.0, 80.0, 200.0, 600.0)):
        trials.append(_trial("correct_cv", {"B3": "accept" if index != 2 else "reject"}, chirp=chirp, snr=60.0))
    trials.append(_trial("acceleration", {"B3": "reject"}, chirp=20.0, snr=60.0))
    result = selfcheck.b3_per_chirp_bin_power(trials)
    assert len(result["bins"]) == len(B3_CHIRP_EDGES_HZ_S) - 1
    total_cv = sum(bin_row["cv"]["n"] for bin_row in result["bins"])
    assert total_cv == 4
    low_bin = result["bins"][0]
    assert low_bin["cv"]["n"] == 1 and low_bin["acceleration"]["n"] == 1
    snr = result["estimated_snr"]
    assert snr["max"] == 60.0
    assert snr["saturated"] is True
    assert snr["snr_branch_unverified"] is True
    assert "saturated" in snr["declaration"].lower() or "unverified" in snr["declaration"].lower()


def test_development_scope_no_sealed_grid_and_no_threshold_changes():
    source = pathlib.Path(selfcheck.__file__).read_text(encoding="utf-8")
    assert "pr4e-c2c-v1" in source  # declared as the sealed grid that is NOT opened
    assert selfcheck.SELFCHECK_SEED_BASE >= 92_000_000
    assert selfcheck.SELFCHECK_SEED_BASE not in (90_000_000, 91_000_000)
    before = copy.deepcopy(PROTOCOL)
    _ = selfcheck.biased_model_params({"f0": 500.0, "v": 250.0, "t0": 20.0, "b": 600.0}, "speed_plus_20pct")
    after = copy.deepcopy(PROTOCOL)
    assert before == after
