"""E0-hardened sweep: same conditions/trials/seeds as E0, hardened fit only.

This is a **separate artifact** (``e0-hardened``).  It never writes, rewrites or
reads the frozen E0 files (``e0-results.json`` / ``tables.md``); the frozen
estimator in :mod:`phaino_acoustics.fit` and the frozen runner
:mod:`phaino_acoustics.experiment` are untouched.  The only scientific
difference from E0 is the stopping rule and the four-part status report of
:mod:`phaino_acoustics.fit_hardened`.

Seed policy
-----------
For a given ``(condition, trial)`` the seed is the pre-registered E0 seed of
the *full* E0 grid::

    seed = 20261104 + 1000 * full_grid_condition_index + trial

``--filter`` only selects which conditions are run; it does not renumber them.
That is deliberate: a filtered run must be a slice of the full artifact, so a
hardened trial is directly comparable with the same E0 trial.  (The frozen E0
runner numbers conditions after filtering; for the full run both are identical.)

Usage::

    python -m phaino_acoustics.experiment_hardened --output-dir /tmp/e0-hardened --jobs 8
    python -m phaino_acoustics.experiment_hardened \
        --output-dir /tmp/e0-hardened-smoke --filter snr_+5dB --trials 10 --jobs 1

Artifacts written into ``--output-dir`` (nothing else):
``e0-hardened-results.json`` and ``e0-hardened-tables.md``.
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
from typing import Optional

import numpy as np

from .experiment import (
    B_REL_TOL,
    BASE,
    F0_REL_TOL,
    F_MAX,
    F_MIN,
    FRAME_LEN,
    HOP,
    SEED_BASE,
    T0_ABS_TOL,
    V_REL_TOL,
    build_conditions,
)
from .features import estimate_if_track
from .fit_hardened import (
    GRADIENT_TOL,
    HARDENED_VERSION,
    IDENT_CONDITION_NUMBER_TOL,
    IDENT_WORST_REL_SE_TOL,
    MAX_ITER,
    MIN_CONSECUTIVE,
    MODEL_MIN_IMPROVEMENT,
    OBJECTIVE_TOL,
    PARAMETER_SCALES,
    STEP_TOL,
    VERIFICATION_DAMPING,
    fit_hardened,
)
from .synthetic import Scenario, generate

EXPERIMENT_NAME = "e0-hardened"
ARTIFACT_JSON = "e0-hardened-results.json"
ARTIFACT_TABLES = "e0-hardened-tables.md"
# Frozen E0 artifact names: this runner must never write these.
FROZEN_E0_ARTIFACT_NAMES = frozenset({"e0-results.json", "tables.md"})

GRID = build_conditions()
GRID_INDEX = {condition.name: index for index, condition in enumerate(GRID)}


@dataclass(frozen=True)
class HardenedCondition:
    name: str
    group: str
    note: str
    scenario: Scenario
    n_trials: int = 100


def _as_condition(condition) -> HardenedCondition:
    return HardenedCondition(
        name=condition.name,
        group=condition.group,
        note=condition.note,
        scenario=condition.scenario,
        n_trials=condition.n_trials,
    )


def build_hardened_conditions() -> list[HardenedCondition]:
    """The full E0 grid (same order, same scenarios, same N)."""
    return [_as_condition(condition) for condition in GRID]


def seed_for(condition_name: str, trial: int) -> int:
    """The pre-registered E0 seed of the full grid (filter does not renumber)."""
    if condition_name not in GRID_INDEX:
        raise ValueError(f"unknown condition {condition_name!r}")
    if isinstance(trial, bool) or not isinstance(trial, int) or trial < 0:
        raise ValueError(f"trial must be a non-negative integer, got {trial!r}")
    return SEED_BASE + 1000 * GRID_INDEX[condition_name] + trial


def _rel_errors(params: dict[str, float], scenario: Scenario) -> dict[str, float]:
    return {
        "f0": (params["f0"] - scenario.f0) / scenario.f0,
        "v": (params["v"] - scenario.v) / scenario.v,
        "t0": (params["t0"] - scenario.t0) / scenario.t0,
        "b": (params["b"] - scenario.b) / scenario.b,
        "t0_abs": params["t0"] - scenario.t0,
    }


def _within_e0_tolerance(rel: dict[str, float]) -> bool:
    """The frozen E0 success tolerance, kept for continuity of the comparison."""
    return bool(
        abs(rel["f0"]) <= F0_REL_TOL
        and abs(rel["v"]) <= V_REL_TOL
        and abs(rel["t0_abs"]) <= T0_ABS_TOL
        and abs(rel["b"]) <= B_REL_TOL
    )


def _jsonable(obj):
    """Convert numpy scalars and non-finite floats to strict-JSON values."""
    if isinstance(obj, dict):
        return {key: _jsonable(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(value) for value in obj]
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (float, np.floating)):
        value = float(obj)
        return value if np.isfinite(value) else None
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    return obj


# ---------------------------------------------------------------------------
# One trial
# ---------------------------------------------------------------------------

def run_trial(condition_name: str, scenario: Scenario, trial: int, seed: int) -> dict:
    """Generate the E0 observation, run the hardened fit, record the statuses."""
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

    result = fit_hardened(track.t, track.f, c=sc.c)
    rel = _rel_errors(result.params, sc)

    return {
        "condition": condition_name,
        "trial": int(trial),
        "seed": int(seed),
        "if_rms_hz": float(np.sqrt(np.mean(if_err**2))),
        "if_median_abs_hz": float(np.median(abs_err)),
        "if_p95_abs_hz": float(np.percentile(abs_err, 95)),
        "hardened": {
            "params": {name: float(value) for name, value in result.params.items()},
            "rel": {name: float(value) for name, value in rel.items()},
            "within_e0_tolerance": _within_e0_tolerance(rel),
            "objective": float(result.objective),
            "rms_hz": float(result.rms_hz),
            "sigma_f_hz": float(result.sigma_f_hz),
            "improvement_ratio": float(result.improvement_ratio),
            "optimization_converged": bool(result.optimization_converged),
            "optimization_status": result.optimization_status,
            "optimization_reason": result.optimization_reason,
            "parameter_identifiable": bool(result.parameter_identifiable),
            "model_adequate": bool(result.model_adequate),
            "decision_status": result.decision_status,
            "decision_reason": result.decision_reason,
            "iterations": int(result.iterations),
            "max_iter": int(result.max_iter),
            "iteration_budget_hit": bool(result.iteration_budget_hit),
            "nfev": int(result.nfev),
            "njev": int(result.njev),
            "consecutive_confirmations": int(result.consecutive_confirmations),
            "verification_iterations": int(result.verification_iterations),
            "n_starts": int(result.n_starts),
            "n_starts_ranked": int(result.n_starts_ranked),
            "n_starts_converged": int(result.n_starts_converged),
            "best_start_index": int(result.best_start_index),
            "criteria": {
                "predicted_newton_step_inf_norm": float(
                    result.criteria["predicted_newton_step_inf_norm"]
                ),
                "elementwise_scale_normalized_gradient_inf_norm": float(
                    result.criteria["elementwise_scale_normalized_gradient_inf_norm"]
                ),
                "relative_objective_change": float(
                    result.criteria["relative_objective_change"]
                ),
                "scale_normalized_step": float(result.criteria["scale_normalized_step"]),
                "thresholds": dict(result.criteria["thresholds"]),
            },
            "identifiability": {
                "worst_rel_se": (
                    float(result.worst_rel_se) if result.worst_rel_se is not None else None
                ),
                "condition_number": (
                    float(result.condition_number)
                    if result.condition_number is not None
                    else None
                ),
                "se": {name: float(value) for name, value in result.se.items()},
                "corr": {name: float(value) for name, value in result.corr.items()},
                "worst_dir": {name: float(value) for name, value in result.worst_dir.items()},
            },
            "history": [dict(entry) for entry in result.history[-5:]],
            "per_start": [dict(entry) for entry in result.per_start],
        },
    }


def _worker(task: tuple[str, Scenario, int, int]) -> dict:
    condition_name, scenario, trial, seed = task
    return _jsonable(run_trial(condition_name, scenario, trial, seed))


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


def aggregate(condition: HardenedCondition, records: list[dict]) -> dict:
    n = len(records)
    hardened = [record["hardened"] for record in records]
    decisions = {status: 0 for status in ("accepted", "rejected", "indeterminate")}
    optimization = {status: 0 for status in ("converged", "indeterminate", "failed")}
    reasons: dict[str, int] = {}
    for record in hardened:
        decisions[record["decision_status"]] += 1
        optimization[record["optimization_status"]] += 1
        reasons[record["decision_reason"]] = reasons.get(record["decision_reason"], 0) + 1
    accepted = [record for record in hardened if record["decision_status"] == "accepted"]
    rel_keys = ("f0", "v", "b")
    summary = {
        "condition": condition.name,
        "group": condition.group,
        "note": condition.note,
        "scenario": {
            key: (float(value) if isinstance(value, (int, float)) else value)
            for key, value in asdict(condition.scenario).items()
        },
        "n": n,
        "decisions": {
            **{status: {"k": count, "rate": float(count / n)} for status, count in decisions.items()},
            "accepted_wilson_lo": float(_wilson(decisions["accepted"], n)[0]),
            "accepted_wilson_hi": float(_wilson(decisions["accepted"], n)[1]),
        },
        "optimization": {status: {"k": count, "rate": float(count / n)} for status, count in optimization.items()},
        "decision_reasons": {reason: count for reason, count in sorted(reasons.items())},
        "parameter_identifiable_rate": float(np.mean([r["parameter_identifiable"] for r in hardened])),
        "model_adequate_rate": float(np.mean([r["model_adequate"] for r in hardened])),
        "iteration_budget_hit_rate": float(np.mean([r["iteration_budget_hit"] for r in hardened])),
        "e0_tolerance_rate": float(np.mean([r["within_e0_tolerance"] for r in hardened])),
        "accepted_rel_abs": {
            key: _summ([abs(record["rel"][key]) for record in accepted])
            for key in rel_keys
        },
        "accepted_t0_abs_err": _summ([abs(record["rel"]["t0_abs"]) for record in accepted]),
        "accepted_rms_hz": _summ([record["rms_hz"] for record in accepted]),
        "all_rel_abs": {
            key: _summ([abs(record["rel"][key]) for record in hardened]) for key in rel_keys
        },
        "all_t0_abs_err": _summ([abs(record["rel"]["t0_abs"]) for record in hardened]),
        "worst_rel_se": _summ([r["identifiability"]["worst_rel_se"] for r in hardened]),
        "condition_number": _summ([r["identifiability"]["condition_number"] for r in hardened]),
        "predicted_newton_step_inf_norm": _summ(
            [r["criteria"]["predicted_newton_step_inf_norm"] for r in hardened]
        ),
        "iterations": _summ([r["iterations"] for r in hardened]),
        "front_end": {
            "if_rms_hz": _summ([record["if_rms_hz"] for record in records]),
            "if_median_abs_hz": _summ([record["if_median_abs_hz"] for record in records]),
        },
    }
    return summary


# ---------------------------------------------------------------------------
# Markdown tables
# ---------------------------------------------------------------------------

def _pct(x, digits: int = 3) -> str:
    if x is None or not np.isfinite(x):
        return "—"
    return f"{100.0 * x:.{digits}g}%"


def _num(x, digits: int = 3) -> str:
    if x is None or not np.isfinite(x):
        return "—"
    return f"{x:.{digits}g}"


def _ci(k: int, n: int) -> str:
    if n == 0:
        return "—"
    lo, hi = _wilson(k, n)
    return f"{k}/{n} ({100.0 * k / n:.0f}%, {100.0 * lo:.0f}–{100.0 * hi:.0f}%)"


def render_status_table(summaries: list[dict]) -> str:
    rows = [
        "| Condition | N | accepted | rejected | indeterminate | optimization converged | parameter identifiable | model adequate | budget hit | E0-tolerance (for continuity) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for summary in summaries:
        decisions = summary["decisions"]
        rows.append(
            "| {name} | {n} | {accepted} | {rejected} | {indeterminate} | {conv} | {ident} | {model} | {budget} | {e0} |".format(
                name=summary["condition"],
                n=summary["n"],
                accepted=_ci(decisions["accepted"]["k"], summary["n"]),
                rejected=_pct(decisions["rejected"]["rate"]),
                indeterminate=_pct(decisions["indeterminate"]["rate"]),
                conv=_pct(summary["optimization"]["converged"]["rate"]),
                ident=_pct(summary["parameter_identifiable_rate"]),
                model=_pct(summary["model_adequate_rate"]),
                budget=_pct(summary["iteration_budget_hit_rate"]),
                e0=_pct(summary["e0_tolerance_rate"]),
            )
        )
    return "\n".join(rows)


def render_accepted_error_table(summaries: list[dict]) -> str:
    rows = [
        "| Condition | N accepted | med \\|Δf0\\|/f0 | med \\|Δv\\|/v | med \\|Δt0\\| (s) | med \\|Δb\\|/b | med worst rel. SE | med cond. number |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for summary in summaries:
        accepted_n = summary["decisions"]["accepted"]["k"]
        rel = summary["accepted_rel_abs"]
        rows.append(
            "| {name} | {n} | {f0} | {v} | {t0} | {b} | {wse} | {cond} |".format(
                name=summary["condition"],
                n=accepted_n,
                f0=_pct(rel["f0"]["median"]) if accepted_n else "—",
                v=_pct(rel["v"]["median"]) if accepted_n else "—",
                t0=_num(summary["accepted_t0_abs_err"]["median"]) if accepted_n else "—",
                b=_pct(rel["b"]["median"]) if accepted_n else "—",
                wse=_num(summary["worst_rel_se"]["median"]),
                cond=_num(summary["condition_number"]["median"]),
            )
        )
    return "\n".join(rows)


def render_reason_table(summaries: list[dict]) -> str:
    reasons = sorted({reason for summary in summaries for reason in summary["decision_reasons"]})
    if not reasons:
        return "| Condition | (no decisions) |\n|---|---|"
    header = "| Condition | " + " | ".join(reasons) + " |"
    sep = "|---" * (len(reasons) + 1) + "|"
    rows = [header, sep]
    for summary in summaries:
        cells = [str(summary["decision_reasons"].get(reason, 0)) for reason in reasons]
        rows.append("| " + summary["condition"] + " | " + " | ".join(cells) + " |")
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Sweep driver
# ---------------------------------------------------------------------------

def run_sweep(
    jobs: int = 1,
    trials_override: Optional[int] = None,
    name_filter: Optional[str] = None,
    progress: bool = True,
) -> dict:
    conditions = build_hardened_conditions()
    if name_filter:
        conditions = [
            condition
            for condition in conditions
            if name_filter in condition.name or name_filter == condition.group
        ]
        if not conditions:
            raise ValueError(f"no condition matches filter {name_filter!r}")
    if trials_override is not None:
        conditions = [replace(condition, n_trials=int(trials_override)) for condition in conditions]

    tasks: list[tuple[str, Scenario, int, int]] = []
    for condition in conditions:
        for trial in range(condition.n_trials):
            tasks.append((condition.name, condition.scenario, trial, seed_for(condition.name, trial)))

    started = time.time()
    records: list[dict] = []
    if jobs <= 1:
        for index, task in enumerate(tasks):
            records.append(_worker(task))
            if progress and (index + 1) % 250 == 0:
                print(f"  ... {index + 1}/{len(tasks)} trials", file=sys.stderr)
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            for index, record in enumerate(pool.map(_worker, tasks, chunksize=8)):
                records.append(record)
                if progress and (index + 1) % 250 == 0:
                    print(f"  ... {index + 1}/{len(tasks)} trials", file=sys.stderr)
    elapsed = time.time() - started

    by_condition: dict[str, list[dict]] = {condition.name: [] for condition in conditions}
    for record in records:
        by_condition[record["condition"]].append(record)
    for name in by_condition:
        by_condition[name].sort(key=lambda record: record["trial"])
    summaries = [aggregate(condition, by_condition[condition.name]) for condition in conditions]

    records_digest = hashlib.sha256(
        json.dumps(_jsonable(records), sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
            "utf-8"
        )
    ).hexdigest()

    result = {
        "experiment": EXPERIMENT_NAME,
        "base_experiment": "e0-synthetic-doppler",
        "hardened_version": HARDENED_VERSION,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "config": {
            "c_sound_m_s": BASE.c,
            "front_end": {
                "method": "Hann STFT peak + log-magnitude parabolic interpolation",
                "frame_len": FRAME_LEN,
                "hop": HOP,
                "f_min_hz": F_MIN,
                "f_max_hz": F_MAX,
                "sample_rate_hz": BASE.fs,
            },
            "fitted_model": "f_obs(t) = f0 / (1 - v_r(t)/c), zero acceleration, delay-free",
            "seed_formula": "seed = 20261104 + 1000*full_grid_condition_index + trial_index (filter does not renumber)",
            "n_trials_per_condition": int(conditions[0].n_trials) if conditions else 0,
            "n_conditions": len(conditions),
            "jobs": int(jobs),
            "hardened_rule": {
                "parameter_scales": dict(PARAMETER_SCALES),
                "gradient_tol": GRADIENT_TOL,
                "objective_tol": OBJECTIVE_TOL,
                "step_tol": STEP_TOL,
                "min_consecutive": MIN_CONSECUTIVE,
                "max_iter": MAX_ITER,
                "verification_damping": list(VERIFICATION_DAMPING),
                "gradient_metric": (
                    "max_i |g_i| / (s_i * (J^T J)_ii): dimensionless predicted Newton step "
                    "(Gauss-Newton curvature-normalized gradient infinity norm)"
                ),
                "identifiable_gate": {
                    "worst_rel_se_max": IDENT_WORST_REL_SE_TOL,
                    "condition_number_max": IDENT_CONDITION_NUMBER_TOL,
                },
                "model_adequate_rule": {
                    "improvement_ratio_min": MODEL_MIN_IMPROVEMENT,
                    "definition": "1 - SSE / SSE(constant-frequency); at least half the IF variance explained",
                },
                "decision_precedence": [
                    "optimization indeterminate -> indeterminate",
                    "optimization failed -> indeterminate",
                    "model inadequate -> rejected",
                    "parameters unidentifiable -> indeterminate",
                    "otherwise -> accepted",
                ],
            },
            "e0_tolerances_for_continuity": {
                "f0_rel": F0_REL_TOL,
                "v_rel": V_REL_TOL,
                "t0_abs_s": T0_ABS_TOL,
                "b_rel": B_REL_TOL,
            },
        },
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
        },
        "elapsed_s": float(elapsed),
        "hardened_records_sha256": records_digest,
        "conditions": summaries,
        "trials": records,
    }
    # Some aggregates are undefined (e.g. accepted-only medians when nothing was
    # accepted); strict JSON cannot carry NaN, so undefined becomes null.
    return _jsonable(result)


def render_tables(result: dict) -> str:
    summaries = result["conditions"]
    parts = [
        "## Decision status by condition\n",
        render_status_table(summaries),
        "\n## Decision reasons\n",
        render_reason_table(summaries),
        "\n## Parameter recovery among accepted trials\n",
        render_accepted_error_table(summaries),
        "\n",
    ]
    return "\n".join(parts)


def _guard_artifact_names() -> None:
    for name in (ARTIFACT_JSON, ARTIFACT_TABLES):
        if name in FROZEN_E0_ARTIFACT_NAMES:
            raise RuntimeError(f"hardened artifact name {name!r} collides with a frozen E0 artifact")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    _guard_artifact_names()
    parser = argparse.ArgumentParser(
        description="E0-hardened sweep: same grid/seeds as E0, hardened convergence rule."
    )
    parser.add_argument("--output-dir", default="/tmp/e0-hardened")
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--trials", type=int, default=None, help="override trials per condition")
    parser.add_argument("--filter", default=None, help="condition name substring or group name")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    result = run_sweep(
        jobs=args.jobs,
        trials_override=args.trials,
        name_filter=args.filter,
        progress=not args.quiet,
    )
    tables = render_tables(result)

    os.makedirs(args.output_dir, exist_ok=True)
    json_path = os.path.join(args.output_dir, ARTIFACT_JSON)
    tables_path = os.path.join(args.output_dir, ARTIFACT_TABLES)
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=1, sort_keys=True, allow_nan=False)
        handle.write("\n")
    with open(tables_path, "w", encoding="utf-8") as handle:
        handle.write(tables)
    with open(json_path, "rb") as handle:
        json_sha = hashlib.sha256(handle.read()).hexdigest()

    print(
        f"trials: {len(result['trials'])}  conditions: {len(result['conditions'])}  "
        f"jobs: {args.jobs}  elapsed: {result['elapsed_s']:.1f} s"
    )
    print(f"hardened_records_sha256: {result['hardened_records_sha256']}")
    print(f"json: {json_path}  sha256: {json_sha}")
    print(f"tables: {tables_path}")
    if not args.quiet:
        print()
        print(tables)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
