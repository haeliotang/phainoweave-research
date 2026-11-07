"""E0 synthetic Doppler identifiability experiment: sweep runner and tables.

Run::

    PYTHONPATH=python python3 -m phaino_acoustics.experiment \
        --output-dir /tmp/e0-synthetic-doppler --jobs 8

The runner writes ``e0-results.json`` (machine-readable, one record per trial
plus per-condition aggregates) and ``tables.md`` (markdown table bodies for the
experiment report) into the output directory, and prints the tables and the
results digest to stdout.

The design is pre-registered in
``docs/experiments/2026-11-04-e0-synthetic-doppler.md``: the tolerance for
"recovered", the SNR/window/acceleration/clock axes, N=100 trials per point,
and the seed formula were fixed before the sweep was run.  Everything here is
deterministic given the seed formula; only the wall-clock timestamp and the
``--jobs`` setting vary, and neither changes any recorded number.

Population: one fixed synthetic geometry per condition (the base geometry is
v=250 m/s, b=3000 m, f0=500 Hz, t0=20 s, c=343 m/s, 60 s at 8 kHz) with 100
noise realizations.  This is an estimator/identifiability study; the numbers
are not a real-world capability estimate.

Sweep config file (``--config <path>``)
---------------------------------------
``--config`` replaces the built-in sweep grid with a JSON document.  Without
``--config`` the runner uses exactly :func:`build_conditions` and
:data:`SEED_BASE`, so the default ``records_sha256`` is unchanged.  The schema
(version 1) is::

    {
      "schema_version": 1,
      "experiment": "e0-synthetic-doppler",
      "seed_base": 20261104,
      "base_geometry": {              # every Scenario field; see synthetic.py
        "f0": 500.0, "v": 250.0, "b": 3000.0, "t0": 20.0,
        "duration": 60.0, "fs": 8000.0, "c": 343.0, "accel": 0.0,
        "snr_db": 20.0, "amplitude": 1.0, "phase0": 0.0,
        "amplitude_mod_depth": 0.0, "amplitude_mod_hz": 0.7,
        "amplitude_geometric": false, "clock_scale_ppm": 0.0,
        "clock_offset_s": 0.0, "emit_signal": true, "seed": 20261104
      },
      "conditions": [
        {
          "name": "snr_+0dB",
          "group": "snr",
          "note": "per-sample SNR; 60 s window; base geometry",
          "n_trials": 100,
          "scenario": {"snr_db": 0.0}   # overrides on base_geometry
        }
      ]
    }

Rules: ``schema_version`` must be 1; ``experiment`` must match
:data:`EXPERIMENT_NAME`; condition names must be unique; every scenario
override key must be a :class:`Scenario` field; ``n_trials`` must be >= 1.
Seeds follow the pre-registered formula ``seed_base + 1000 * condition_index +
trial_index``, where ``condition_index`` is the position after ``--filter`` and
before ``--trials`` overrides.  :func:`default_config` emits the frozen E0
config; :func:`conditions_from_config` and :func:`config_from_conditions`
round-trip it without loss.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, replace

import numpy as np

from .features import estimate_if_track
from .fit import fit_doppler, naive_inversion
from .synthetic import Scenario, generate

# --- Pre-registered analysis constants --------------------------------------
# Fixed before the sweep; see the report's "Preregistered expectation".
F0_REL_TOL = 0.01      # |f0_hat/f0 - 1| <= 1%
V_REL_TOL = 0.02       # |v_hat/v - 1|   <= 2%
T0_ABS_TOL = 0.25      # |t0_hat - t0|   <= 0.25 s
B_REL_TOL = 0.05       # |b_hat/b - 1|   <= 5%
ACCEPT_IMPROVEMENT = 0.5  # Doppler fit accepted iff it explains >=50% of IF variance

# --- Pre-registered front end and generator settings ------------------------
FRAME_LEN = 512
HOP = 256
F_MIN = 180.0
F_MAX = 2800.0
C_SOUND = 343.0

SEED_BASE = 20261104
N_TRIALS = 100

# --- Sweep config file (--config) -------------------------------------------
EXPERIMENT_NAME = "e0-synthetic-doppler"
CONFIG_SCHEMA_VERSION = 1

BASE = Scenario(c=C_SOUND)


@dataclass(frozen=True)
class Condition:
    name: str
    group: str
    note: str
    scenario: Scenario
    n_trials: int = N_TRIALS


def build_conditions() -> list[Condition]:
    """The pre-registered sweep grid (order fixes the seed mapping)."""
    conds: list[Condition] = []

    def add(name: str, group: str, note: str, **overrides: object) -> None:
        conds.append(
            Condition(name=name, group=group, note=note, scenario=replace(BASE, **overrides))
        )

    # SNR sweep (primary)
    for snr in (-10.0, -5.0, 0.0, 5.0, 10.0, 20.0):
        add(f"snr_{snr:+.0f}dB", "snr", "per-sample SNR; 60 s window; base geometry", snr_db=snr)

    # Observation-window sweep at a mid SNR
    for dur in (5.0, 10.0, 20.0):
        add(
            f"window_{dur:.0f}s",
            "window",
            "window length at 5 dB; shortest is 0.42 of the closest-approach time scale b/v",
            duration=dur,
            snr_db=5.0,
        )

    # Acceleration mismatch (generator has constant a; fit assumes a=0)
    for a in (0.1, 0.25, 0.5):
        add(
            f"accel_{a:g}",
            "accel",
            "constant along-track acceleration in the data, zero-acceleration model",
            accel=a,
            snr_db=20.0,
        )

    # Recorder clock rate error (ppm); fit assumes a perfect clock
    for ppm in (10.0, 100.0, 1000.0, 20000.0, 50000.0):
        add(
            f"clock_{ppm:g}ppm",
            "clock_scale",
            "recorder clock runs fast by ppm; analyzer assumes nominal time",
            clock_scale_ppm=ppm,
            snr_db=20.0,
        )

    # Constant recorder clock offset (expected to be absorbed by t0)
    for off in (0.3, 2.0):
        add(
            f"offset_{off:g}s",
            "clock_offset",
            "constant clock offset; expected exact degeneracy with t0",
            clock_offset_s=off,
            snr_db=20.0,
        )

    # Amplitude variation (front end must be amplitude-insensitive)
    add(
        "amp_geometric",
        "amplitude",
        "amplitude ~ b/r (1/r spreading), 5 dB",
        amplitude_geometric=True,
        snr_db=5.0,
    )
    add(
        "amp_mod30pct",
        "amplitude",
        "30% sinusoidal AM at 0.7 Hz, 5 dB",
        amplitude_mod_depth=0.3,
        snr_db=5.0,
    )

    # Geometry variants at 5 dB (exploratory: does one geometry generalise?)
    add("geom_v100_b300", "geometry", "v=100 m/s, b=300 m, 5 dB", v=100.0, b=300.0, snr_db=5.0)
    add(
        "geom_v250_b30000",
        "geometry",
        "v=250 m/s, b=30 km: window covers only +-0.25 closest-approach time scales",
        b=30000.0,
        snr_db=5.0,
    )
    add("geom_v60_b120", "geometry", "v=60 m/s, b=120 m, 5 dB", v=60.0, b=120.0, snr_db=5.0)

    # Null (noise-only) observation at the noise level of a 0 dB signal
    add(
        "null_noise_only",
        "null",
        "no signal; noise level equals a 0 dB reference signal",
        emit_signal=False,
        snr_db=0.0,
    )
    return conds


# ---------------------------------------------------------------------------
# Sweep config file
# ---------------------------------------------------------------------------

def _scenario_dict(scenario: Scenario) -> dict:
    """A JSON-safe dict of every ``Scenario`` field."""
    return asdict(scenario)


def config_from_conditions(
    conditions: list[Condition],
    base: Scenario = BASE,
    seed_base: int = SEED_BASE,
) -> dict:
    """Serialize conditions to the config schema (overrides relative to ``base``)."""
    base_fields = _scenario_dict(base)
    entries = []
    for cond in conditions:
        scenario = _scenario_dict(cond.scenario)
        overrides = {key: value for key, value in scenario.items() if base_fields[key] != value}
        entries.append(
            {
                "name": cond.name,
                "group": cond.group,
                "note": cond.note,
                "n_trials": int(cond.n_trials),
                "scenario": overrides,
            }
        )
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "experiment": EXPERIMENT_NAME,
        "seed_base": int(seed_base),
        "base_geometry": base_fields,
        "conditions": entries,
    }


def default_config() -> dict:
    """The frozen E0 sweep config (25 conditions x 100 trials, pre-registered seeds)."""
    return config_from_conditions(build_conditions())


def _scenario_from_dict(data: object, where: str) -> Scenario:
    if not isinstance(data, dict):
        raise ValueError(f"{where}: expected a JSON object, got {type(data).__name__}")
    known = set(_scenario_dict(Scenario()))
    unknown = sorted(set(data) - known)
    if unknown:
        raise ValueError(f"{where}: unknown Scenario field(s): {', '.join(unknown)}")
    return Scenario(**data)


def conditions_from_config(config: object) -> tuple[list[Condition], int]:
    """Reconstruct ``(conditions, seed_base)`` from a config document.

    Raises ``ValueError`` on a malformed or inconsistent config; the caller
    (``--config``) turns that into a non-zero exit without touching the sweep.
    """
    if not isinstance(config, dict):
        raise ValueError("config: expected a JSON object")
    schema_version = config.get("schema_version")
    if schema_version != CONFIG_SCHEMA_VERSION:
        raise ValueError(
            f"config: unsupported schema_version {schema_version!r} "
            f"(expected {CONFIG_SCHEMA_VERSION})"
        )
    experiment = config.get("experiment")
    if experiment != EXPERIMENT_NAME:
        raise ValueError(
            f"config: experiment {experiment!r} is not {EXPERIMENT_NAME!r}"
        )
    seed_base = config.get("seed_base")
    if not isinstance(seed_base, int) or isinstance(seed_base, bool) or seed_base < 0:
        raise ValueError(f"config: seed_base must be a non-negative integer, got {seed_base!r}")
    base = _scenario_from_dict(config.get("base_geometry"), "config.base_geometry")
    raw_conditions = config.get("conditions")
    if not isinstance(raw_conditions, list) or not raw_conditions:
        raise ValueError("config.conditions: expected a non-empty JSON array")
    conditions: list[Condition] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw_conditions):
        where = f"config.conditions[{index}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{where}: expected a JSON object")
        name = entry.get("name")
        group = entry.get("group")
        note = entry.get("note")
        n_trials = entry.get("n_trials")
        if not isinstance(name, str) or not name:
            raise ValueError(f"{where}.name: expected a non-empty string")
        if name in seen:
            raise ValueError(f"{where}.name: duplicate condition name {name!r}")
        seen.add(name)
        if not isinstance(group, str) or not group:
            raise ValueError(f"{where}.group: expected a non-empty string")
        if not isinstance(note, str):
            raise ValueError(f"{where}.note: expected a string")
        if not isinstance(n_trials, int) or isinstance(n_trials, bool) or n_trials < 1:
            raise ValueError(f"{where}.n_trials: expected an integer >= 1, got {n_trials!r}")
        overrides = entry.get("scenario", {})
        if not isinstance(overrides, dict):
            raise ValueError(f"{where}.scenario: expected a JSON object of overrides")
        scenario = _scenario_from_dict({**_scenario_dict(base), **overrides}, f"{where}.scenario")
        conditions.append(
            Condition(name=name, group=group, note=note, scenario=scenario, n_trials=n_trials)
        )
    return conditions, int(seed_base)


def load_config(path: str) -> dict:
    """Reads and JSON-parses a sweep config; validation happens on use."""
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# One trial
# ---------------------------------------------------------------------------

def _rel_errors(params: dict[str, float], scenario: Scenario) -> dict[str, float]:
    return {
        "f0": (params["f0"] - scenario.f0) / scenario.f0,
        "v": (params["v"] - scenario.v) / scenario.v,
        "t0": (params["t0"] - scenario.t0) / scenario.t0,
        "b": (params["b"] - scenario.b) / scenario.b,
        "t0_abs": params["t0"] - scenario.t0,
    }


def _within_tol(rel: dict[str, float]) -> dict[str, bool]:
    return {
        "f0": abs(rel["f0"]) <= F0_REL_TOL,
        "v": abs(rel["v"]) <= V_REL_TOL,
        "t0": abs(rel["t0_abs"]) <= T0_ABS_TOL,
        "b": abs(rel["b"]) <= B_REL_TOL,
    }


def run_trial(cond_name: str, scenario: Scenario, trial: int, seed: int) -> dict:
    """Generate one observation, run B1 and B0, and record scalar outcomes."""
    sc = replace(scenario, seed=int(seed))
    obs = generate(sc)
    track = estimate_if_track(
        obs.signal,
        sc.fs,
        frame_len=FRAME_LEN,
        hop=HOP,
        f_min=F_MIN,
        f_max=F_MAX,
        t_start=float(obs.t[0]),
    )
    f_true = np.interp(track.t, obs.t, obs.f_apparent)
    if_err = track.f - f_true
    abs_err = np.abs(if_err)

    fit = fit_doppler(track.t, track.f, c=sc.c)
    b0 = naive_inversion(track.t, track.f, c=sc.c)

    rel1 = _rel_errors(fit.params, sc)
    tol1 = _within_tol(rel1)
    rel0 = _rel_errors(b0.params, sc)
    tol0 = _within_tol(rel0)
    accepted = bool(
        fit.converged
        and fit.improvement_ratio >= ACCEPT_IMPROVEMENT
        and np.isfinite(fit.f0)
        and np.isfinite(fit.v)
        and np.isfinite(fit.t0)
        and np.isfinite(fit.b)
        and fit.f0 > 0
        and fit.v > 0
        and fit.b > 0
    )

    return {
        "condition": cond_name,
        "trial": int(trial),
        "seed": int(seed),
        "if_rms_hz": float(np.sqrt(np.mean(if_err**2))),
        "if_median_abs_hz": float(np.median(abs_err)),
        "if_p95_abs_hz": float(np.percentile(abs_err, 95)),
        "b1": {
            "params": {k: float(v) for k, v in fit.params.items()},
            "rel": {k: float(v) for k, v in rel1.items()},
            "within_tol": tol1,
            "success": bool(fit.converged and all(tol1.values())),
            "converged": bool(fit.converged),
            "iterations": int(fit.iterations),
            "n_starts_ranked": int(fit.n_starts_ranked),
            "n_starts": int(fit.n_starts),
            "sse": float(fit.sse),
            "rms_hz": float(fit.rms),
            "sigma_f_hz": float(fit.sigma_f),
            "improvement_ratio": float(fit.improvement_ratio),
            "grad_norm": float(fit.grad_norm),
            "se": {k: float(v) for k, v in fit.se.items()},
            "corr": {k: (float(v) if np.isfinite(v) else None) for k, v in fit.corr.items()},
            "corr_abs": {k: (float(abs(v)) if np.isfinite(v) else None) for k, v in fit.corr.items()},
            "worst_rel_se": float(fit.worst_rel_se) if fit.worst_rel_se is not None else None,
            "condition_number": float(fit.condition_number) if fit.condition_number is not None else None,
            "worst_dir": {k: float(v) for k, v in fit.worst_dir.items()},
        },
        "b0": {
            "params": {k: float(v) for k, v in b0.params.items()},
            "rel": {k: float(v) for k, v in rel0.items()},
            "within_tol": tol0,
            "success": bool(b0.valid and all(tol0.values())),
            "valid": bool(b0.valid),
            "rms_hz": float(b0.rms),
            "improvement_ratio": float(b0.improvement_ratio),
        },
        "accepted": accepted,
    }


def _clean(obj):
    """Recursively replace non-finite floats with None so the JSON is strict."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (float, np.floating)):
        v = float(obj)
        return v if np.isfinite(v) else None
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    return obj


def _worker(task: tuple[str, Scenario, int, int]) -> dict:
    cond_name, scenario, trial, seed = task
    return _clean(run_trial(cond_name, scenario, trial, seed))


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _summ(values) -> dict:
    arr = np.asarray([v for v in values if v is not None and np.isfinite(v)], dtype=np.float64)
    if arr.size == 0:
        nan = float("nan")
        return {"n": 0, "median": nan, "p25": nan, "p75": nan, "p90": nan, "min": nan, "max": nan}
    return {
        "n": int(arr.size),
        "median": float(np.median(arr)),
        "p25": float(np.percentile(arr, 25)),
        "p75": float(np.percentile(arr, 75)),
        "p90": float(np.percentile(arr, 90)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
    }


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2.0 * n)) / denom
    half = z * np.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def aggregate(cond: Condition, records: list[dict]) -> dict:
    n = len(records)
    k_success = sum(1 for r in records if r["b1"]["success"])
    lo, hi = _wilson(k_success, n)
    k_b0_success = sum(1 for r in records if r["b0"]["success"])
    fail_components = {
        comp: sum(1 for r in records if not r["b1"]["within_tol"][comp])
        for comp in ("f0", "v", "t0", "b")
    }
    rel_keys = ("f0", "v", "b")
    summary = {
        "condition": cond.name,
        "group": cond.group,
        "note": cond.note,
        "scenario": {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in asdict(cond.scenario).items()},
        "n": n,
        "success": {
            "k": int(k_success),
            "n": int(n),
            "rate": float(k_success / n) if n else float("nan"),
            "wilson_lo": float(lo),
            "wilson_hi": float(hi),
            "fail_components": fail_components,
        },
        "accepted_rate": float(np.mean([r["accepted"] for r in records])) if n else float("nan"),
        "converged_rate": float(np.mean([r["b1"]["converged"] for r in records])) if n else float("nan"),
        "b1": {
            "rel": {k: _summ([r["b1"]["rel"][k] for r in records]) for k in rel_keys},
            "rel_abs": {k: _summ([abs(r["b1"]["rel"][k]) for r in records]) for k in rel_keys},
            "t0_abs_err": _summ([abs(r["b1"]["rel"]["t0_abs"]) for r in records]),
            "rms_hz": _summ([r["b1"]["rms_hz"] for r in records]),
            "improvement_ratio": _summ([r["b1"]["improvement_ratio"] for r in records]),
            "iterations": _summ([r["b1"]["iterations"] for r in records]),
            "grad_norm": _summ([r["b1"]["grad_norm"] for r in records]),
            "worst_rel_se": _summ([r["b1"]["worst_rel_se"] for r in records]),
            "condition_number": _summ([r["b1"]["condition_number"] for r in records]),
            "cov_available_rate": float(np.mean([
                "f0_v" in r["b1"]["corr"] for r in records])) if n else float("nan"),
            "corr_abs": {k: _summ([r["b1"]["corr_abs"].get(k, float("nan")) for r in records]) for k in (
                "f0_v", "f0_t0", "f0_b", "v_t0", "v_b", "t0_b")},
            "corr_signed": {k: _summ([r["b1"]["corr"].get(k, float("nan")) for r in records]) for k in (
                "f0_v", "f0_t0", "f0_b", "v_t0", "v_b", "t0_b")},
            "worst_dir": {k: _summ([r["b1"]["worst_dir"].get(k, float("nan")) for r in records]) for k in (
                "f0", "v", "t0", "b")},
        },
        "b0": {
            "valid_rate": float(np.mean([r["b0"]["valid"] for r in records])) if n else float("nan"),
            "success": {"k": int(k_b0_success), "rate": float(k_b0_success / n) if n else float("nan")},
            "rel": {k: _summ([r["b0"]["rel"][k] for r in records]) for k in rel_keys},
            "rel_abs": {k: _summ([abs(r["b0"]["rel"][k]) for r in records]) for k in rel_keys},
            "t0_abs_err": _summ([abs(r["b0"]["rel"]["t0_abs"]) for r in records]),
            "rms_hz": _summ([r["b0"]["rms_hz"] for r in records]),
        },
        "front_end": {
            "if_rms_hz": _summ([r["if_rms_hz"] for r in records]),
            "if_median_abs_hz": _summ([r["if_median_abs_hz"] for r in records]),
            "if_p95_abs_hz": _summ([r["if_p95_abs_hz"] for r in records]),
        },
    }
    return summary


def _representative_failure(records: list[dict]) -> dict | None:
    fails = [r for r in records if not r["b1"]["success"]]
    if not fails:
        return None
    fails.sort(key=lambda r: abs(r["b1"]["rel"]["b"]))
    rep = fails[len(fails) // 2]
    return {
        "seed": rep["seed"],
        "trial": rep["trial"],
        "converged": rep["b1"]["converged"],
        "rel": {k: rep["b1"]["rel"][k] for k in ("f0", "v", "t0", "t0_abs", "b")},
        "improvement_ratio": rep["b1"]["improvement_ratio"],
        "if_rms_hz": rep["if_rms_hz"],
        "b1_rms_hz": rep["b1"]["rms_hz"],
    }


# ---------------------------------------------------------------------------
# Markdown tables
# ---------------------------------------------------------------------------

def _pct(x, digits: int = 3) -> str:
    if x is None or not np.isfinite(x):
        return "—"
    v = 100.0 * x
    if v == 0.0:
        return "0"
    if abs(v) < 1e-2:
        return f"{v:.2e}%"
    return f"{v:.{digits}g}%"


def _num(x, digits: int = 3) -> str:
    if x is None or not np.isfinite(x):
        return "—"
    return f"{x:.{digits}g}"


def _ci(k: int, n: int) -> str:
    if n == 0:
        return "—"
    lo, hi = _wilson(k, n)
    return f"{k}/{n} ({100.0 * k / n:.0f}%, {100.0 * lo:.0f}–{100.0 * hi:.0f}%)"


def _table_snr_recovery(conds: list[dict]) -> str:
    rows = [
        "| SNR (dB) | N | success (Wilson 95% CI) | conv. | med \\|Δf0\\|/f0 | med \\|Δv\\|/v | med \\|Δt0\\| (s) | med \\|Δb\\|/b | p90 \\|Δb\\|/b | B1 res RMS (Hz) | IF RMS (Hz) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in conds:
        s = c
        rows.append(
            "| {snr} | {n} | {succ} | {conv} | {f0} | {v} | {t0} | {b} | {b90} | {rms} | {ifr} |".format(
                snr=f"{c['scenario']['snr_db']:+.0f}",
                n=s["n"],
                succ=_ci(s["success"]["k"], s["n"]),
                conv=_pct(s["converged_rate"], 3),
                f0=_pct(s["b1"]["rel_abs"]["f0"]["median"]),
                v=_pct(s["b1"]["rel_abs"]["v"]["median"]),
                t0=_num(s["b1"]["t0_abs_err"]["median"]),
                b=_pct(s["b1"]["rel_abs"]["b"]["median"]),
                b90=_pct(s["b1"]["rel_abs"]["b"]["p90"]),
                rms=_num(s["b1"]["rms_hz"]["median"]),
                ifr=_num(s["front_end"]["if_rms_hz"]["median"]),
            )
        )
    return "\n".join(rows)


def _table_b0_vs_b1(conds: list[dict]) -> str:
    rows = [
        "| SNR (dB) | B0 success | B0 med \\|Δf0\\|/f0 | B0 med \\|Δv\\|/v | B0 med \\|Δt0\\| (s) | B0 med \\|Δb\\|/b | B0 res RMS (Hz) | B1 success | B1 med \\|Δf0\\|/f0 | B1 med \\|Δv\\|/v | B1 med \\|Δt0\\| (s) | B1 med \\|Δb\\|/b | B1 res RMS (Hz) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in conds:
        s = c
        rows.append(
            "| {snr} | {b0s} | {b0f0} | {b0v} | {b0t0} | {b0b} | {b0r} | {b1s} | {b1f0} | {b1v} | {b1t0} | {b1b} | {b1r} |".format(
                snr=f"{c['scenario']['snr_db']:+.0f}",
                b0s=_ci(s["b0"]["success"]["k"], s["n"]),
                b0f0=_pct(s["b0"]["rel_abs"]["f0"]["median"]),
                b0v=_pct(s["b0"]["rel_abs"]["v"]["median"]),
                b0t0=_num(s["b0"]["t0_abs_err"]["median"]),
                b0b=_pct(s["b0"]["rel_abs"]["b"]["median"]),
                b0r=_num(s["b0"]["rms_hz"]["median"]),
                b1s=_ci(s["success"]["k"], s["n"]),
                b1f0=_pct(s["b1"]["rel_abs"]["f0"]["median"]),
                b1v=_pct(s["b1"]["rel_abs"]["v"]["median"]),
                b1t0=_num(s["b1"]["t0_abs_err"]["median"]),
                b1b=_pct(s["b1"]["rel_abs"]["b"]["median"]),
                b1r=_num(s["b1"]["rms_hz"]["median"]),
            )
        )
    return "\n".join(rows)


def _table_failure_conditions(conds: list[dict]) -> str:
    rows = [
        "| Condition | group | N | success | failed f0/v/t0/b (counts) | med \\|Δf0\\|/f0 | med \\|Δv\\|/v | med \\|Δt0\\| (s) | med \\|Δb\\|/b | B1 res RMS (Hz) | IF RMS (Hz) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in conds:
        s = c
        fc = s["success"]["fail_components"]
        rows.append(
            "| {name} | {group} | {n} | {succ} | {fc} | {f0} | {v} | {t0} | {b} | {rms} | {ifr} |".format(
                name=c["condition"],
                group=c["group"],
                n=s["n"],
                succ=_ci(s["success"]["k"], s["n"]),
                fc=f"{fc['f0']}/{fc['v']}/{fc['t0']}/{fc['b']}",
                f0=_pct(s["b1"]["rel_abs"]["f0"]["median"]),
                v=_pct(s["b1"]["rel_abs"]["v"]["median"]),
                t0=_num(s["b1"]["t0_abs_err"]["median"]),
                b=_pct(s["b1"]["rel_abs"]["b"]["median"]),
                rms=_num(s["b1"]["rms_hz"]["median"]),
                ifr=_num(s["front_end"]["if_rms_hz"]["median"]),
            )
        )
    return "\n".join(rows)


def _table_identifiability(conds: list[dict]) -> str:
    rows = [
        "| Condition | med \\|ρ\\|(f0,v) | med \\|ρ\\|(f0,b) | med \\|ρ\\|(v,b) | med \\|ρ\\|(f0,t0) | med worst rel. SE | med cond. number | median worst-direction \\|components\\| (f0,v,t0,b) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for c in conds:
        s = c["b1"]
        wd = s["worst_dir"]
        rows.append(
            "| {name} | {r1} | {r2} | {r3} | {r4} | {w} | {cn} | ({a}, {b}, {c}, {d}) |".format(
                name=c["condition"],
                r1=_num(s["corr_abs"]["f0_v"]["median"]),
                r2=_num(s["corr_abs"]["f0_b"]["median"]),
                r3=_num(s["corr_abs"]["v_b"]["median"]),
                r4=_num(s["corr_abs"]["f0_t0"]["median"]),
                w=_num(s["worst_rel_se"]["median"], 3),
                cn=_num(s["condition_number"]["median"], 3),
                a=_num(wd["f0"]["median"], 2),
                b=_num(wd["v"]["median"], 2),
                c=_num(wd["t0"]["median"], 2),
                d=_num(wd["b"]["median"], 2),
            )
        )
    return "\n".join(rows)


def _table_null(conds: list[dict]) -> str:
    rows = [
        "| Condition | N | accepted (improvement ≥50% & converged) | \"recovered\" within pre-declared tolerance | med improvement ratio | max improvement ratio | B1 res RMS (Hz) | B0 res RMS (Hz) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for c in conds:
        s = c
        rows.append(
            "| {name} | {n} | {acc} | {succ} | {imp} | {impmax} | {rms} | {b0r} |".format(
                name=c["condition"],
                n=s["n"],
                acc=_ci(int(round(s["accepted_rate"] * s["n"])), s["n"]),
                succ=_ci(s["success"]["k"], s["n"]),
                imp=_num(s["b1"]["improvement_ratio"]["median"]),
                impmax=_num(s["b1"]["improvement_ratio"]["max"]),
                rms=_num(s["b1"]["rms_hz"]["median"]),
                b0r=_num(s["b0"]["rms_hz"]["median"]),
            )
        )
    return "\n".join(rows)


def _failure_gallery(conds: list[dict], reps: dict[str, dict | None]) -> str:
    rows = [
        "| Condition | failures / N | components over tolerance (f0/v/t0/b) | representative failing seed | representative relative errors | improvement ratio | B1 res RMS (Hz) |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in conds:
        s = c
        if s["group"] == "null":
            # Null observations have no source to recover; their acceptance
            # rate is reported in the null table, not as a recovery failure.
            continue
        fails = s["n"] - s["success"]["k"]
        if fails == 0:
            continue
        rep = reps.get(c["condition"])
        fc = s["success"]["fail_components"]
        if rep is None:
            continue
        rel = rep["rel"]
        rows.append(
            "| {name} | {f}/{n} | {f0}/{v}/{t0}/{b} | {seed} | f0 {r0:+.2e}, v {r1:+.2e}, t0 {r2:+.3f} s, b {r3:+.2e} | {imp} | {rms} |".format(
                name=c["condition"],
                f=fails,
                n=s["n"],
                f0=fc["f0"],
                v=fc["v"],
                t0=fc["t0"],
                b=fc["b"],
                seed=rep["seed"],
                r0=rel["f0"],
                r1=rel["v"],
                r2=rel["t0_abs"],
                r3=rel["b"],
                imp=_num(rep["improvement_ratio"], 4),
                rms=_num(rep["b1_rms_hz"]),
            )
        )
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def _records_digest(records: list[dict]) -> str:
    payload = json.dumps(records, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_sweep(
    jobs: int = 1,
    trials_override: int | None = None,
    name_filter: str | None = None,
    progress: bool = True,
    config: dict | None = None,
) -> dict:
    if config is None:
        conditions = build_conditions()
        seed_base = SEED_BASE
    else:
        conditions, seed_base = conditions_from_config(config)
    if name_filter:
        conditions = [c for c in conditions if name_filter in c.name or name_filter == c.group]
    if trials_override is not None:
        conditions = [replace(c, n_trials=int(trials_override)) for c in conditions]

    tasks: list[tuple[str, Scenario, int, int]] = []
    trial_meta: list[tuple[int, int, int]] = []  # (cond_index, trial, seed)
    for ci, cond in enumerate(conditions):
        for trial in range(cond.n_trials):
            seed = seed_base + 1000 * ci + trial
            tasks.append((cond.name, cond.scenario, trial, seed))
            trial_meta.append((ci, trial, seed))

    t_start = time.time()
    records: list[dict] = []
    if jobs <= 1:
        for i, task in enumerate(tasks):
            records.append(_worker(task))
            if progress and (i + 1) % 250 == 0:
                print(f"  ... {i + 1}/{len(tasks)} trials", file=sys.stderr)
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            for i, rec in enumerate(pool.map(_worker, tasks, chunksize=8)):
                records.append(rec)
                if progress and (i + 1) % 250 == 0:
                    print(f"  ... {i + 1}/{len(tasks)} trials", file=sys.stderr)
    elapsed = time.time() - t_start

    by_condition: dict[str, list[dict]] = {c.name: [] for c in conditions}
    for rec in records:
        by_condition[rec["condition"]].append(rec)
    for name in by_condition:
        by_condition[name].sort(key=lambda r: r["trial"])

    summaries = []
    reps: dict[str, dict | None] = {}
    for cond in conditions:
        recs = by_condition[cond.name]
        summaries.append(aggregate(cond, recs))
        reps[cond.name] = _representative_failure(recs)

    result = {
        "experiment": "e0-synthetic-doppler",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "config": {
            "c_sound_m_s": C_SOUND,
            "snr_definition": (
                "per-sample SNR = 10*log10((A0^2/2)/sigma^2) with i.i.d. white "
                "Gaussian noise across the full sampling bandwidth; not an STFT-bin "
                "or band-limited SNR"
            ),
            "front_end": {
                "method": "Hann STFT peak + log-magnitude parabolic interpolation",
                "frame_len": FRAME_LEN,
                "hop": HOP,
                "f_min_hz": F_MIN,
                "f_max_hz": F_MAX,
                "sample_rate_hz": conditions[0].scenario.fs if conditions else BASE.fs,
            },
            "fitted_model": "f_obs(t) = f0 / (1 - v_r(t)/c), zero acceleration, delay-free",
            "tolerances": {
                "f0_rel": F0_REL_TOL,
                "v_rel": V_REL_TOL,
                "t0_abs_s": T0_ABS_TOL,
                "b_rel": B_REL_TOL,
                "accept_improvement": ACCEPT_IMPROVEMENT,
            },
            "seed_formula": f"seed = {int(seed_base)} + 1000*condition_index + trial_index",
            "n_trials_per_condition": (
                conditions[0].n_trials
                if conditions and all(c.n_trials == conditions[0].n_trials for c in conditions)
                else None
            ),
            "n_conditions": len(conditions),
            "jobs": int(jobs),
        },
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
        },
        "elapsed_s": float(elapsed),
        "records_sha256": _records_digest(records),
        "conditions": summaries,
        "trials": records,
    }
    return result


def render_tables(result: dict) -> str:
    conds = result["conditions"]
    by_name = {c["condition"]: c for c in conds}
    groups = {
        "snr": [c for c in conds if c["group"] == "snr"],
        "fail": [c for c in conds if c["group"] in ("window", "accel", "clock_scale", "clock_offset", "amplitude", "geometry")],
        "ident": [c for c in conds if c["group"] in ("snr", "window", "geometry")],
        "null": [c for c in conds if c["group"] == "null"],
    }
    reps = {c["condition"]: _representative_failure([r for r in result["trials"] if r["condition"] == c["condition"]])
            for c in conds}
    parts = [
        "## B1 recovery vs SNR\n",
        _table_snr_recovery(groups["snr"]),
        "\n## B0 (direct IF feature inversion) vs B1 (physical fit)\n",
        _table_b0_vs_b1(groups["snr"]),
        "\n## Failure conditions\n",
        _table_failure_conditions(groups["fail"]),
        "\n## Identifiability (linearized, homoscedastic approximation)\n",
        _table_identifiability(groups["ident"]),
        "\n## Null (noise-only) observations\n",
        _table_null(groups["null"]),
        "\n## Failure gallery (machine-generated)\n",
        _failure_gallery(conds, reps),
        "\n",
    ]
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="E0 synthetic Doppler identifiability sweep")
    parser.add_argument("--output-dir", default="/tmp/e0-synthetic-doppler",
                        help="directory for e0-results.json and tables.md")
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--trials", type=int, default=None,
                        help="override trials per condition (smoke testing only)")
    parser.add_argument("--filter", default=None,
                        help="condition name substring or group name")
    parser.add_argument("--config", default=None,
                        help="JSON sweep config file (schema in the module docstring); "
                             "replaces the built-in condition list, base geometry, trial "
                             "counts and seed base")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    config = load_config(args.config) if args.config else None
    try:
        result = run_sweep(
            jobs=args.jobs,
            trials_override=args.trials,
            name_filter=args.filter,
            progress=not args.quiet,
            config=config,
        )
    except ValueError as exc:
        parser.error(str(exc))
    tables = render_tables(result)

    out_dir = args.output_dir
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "e0-results.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1, sort_keys=True, allow_nan=False)
        fh.write("\n")
    tables_path = os.path.join(out_dir, "tables.md")
    with open(tables_path, "w", encoding="utf-8") as fh:
        fh.write(tables)
    with open(json_path, "rb") as fh:
        json_sha = hashlib.sha256(fh.read()).hexdigest()

    total_trials = len(result["trials"])
    print(f"trials: {total_trials}  conditions: {len(result['conditions'])}  "
          f"jobs: {args.jobs}  elapsed: {result['elapsed_s']:.1f} s")
    print(f"records_sha256: {result['records_sha256']}")
    print(f"json: {json_path}  sha256: {json_sha}")
    print(f"tables: {tables_path}")
    if not args.quiet:
        print()
        print(tables)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
