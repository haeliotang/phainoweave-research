"""PR-4e-L1 claim experiment: development (threshold selection) and locked layers.

The locked grid is frozen by the protocol written by the development layer; the
locked layer loads it, verifies the digest and never changes a threshold.

Claim statuses are computed **without truth**: the per-trial pipeline is
observation -> front end -> hardened fit -> PR-4d adequacy block ->
:func:`phaino_claims.claims.claim_metrics` -> frozen protocol.  Synthetic truth
is written per trial under ``evaluation_only`` for the independent evaluator and
is used only on the development layer to *select* the L3 thresholds (documented
in the development artifact).
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
from dataclasses import asdict, dataclass, field, replace
from typing import Optional

import numpy as np

from phaino_acoustics.adequacy import evaluate_adequacy
from phaino_acoustics.experiment import BASE, F_MAX, F_MIN, FRAME_LEN, HOP
from phaino_acoustics.features import estimate_if_track
from phaino_acoustics.fit_hardened import fit_hardened
from phaino_acoustics.synthetic import Scenario, generate

from .claims import apply_claim_statuses, claim_metrics, claim_truth, within_tolerance
from .claims_protocol import (
    ALL_CLAIMS,
    CLAIMS_BY_ID,
    EVALUATED_CLAIMS,
    EXPERIMENT_NAME,
    THRESHOLD_SELECTION,
    build_protocol,
    evidence,
    evidence_gate,
    load_certificate,
    load_protocol,
    protocol_thresholds,
    symbolic_proof_digest,
    THRESHOLD_PRECISION,
    write_protocol,
)
from .symbolic import derive_proof, proof_digest, verify_proof_digest

DEV_SEED_BASE = 40_000_000
LOCKED_SEED_BASE = 41_000_000
TRIALS_PER_CONDITION = 25

STRATA = (
    "control",
    "nominal_snr_control",
    "clock_offset",
    "clock_rate",
    "near_identity",
    "model_misspecification",
    "geometry_stress",
    "null",
)


@dataclass(frozen=True)
class ClaimCondition:
    name: str
    stratum: str
    mechanism: str
    level: str
    note: str
    scenario: Scenario
    n_trials: int = TRIALS_PER_CONDITION


def _base_conditions(layer: str) -> list[ClaimCondition]:
    """The declared grid.  Development uses intermediate levels; locked uses the PR-4e-L1 levels."""
    if layer == "development":
        offsets = (-2.0, -0.25, 0.25, 2.0)
        rates = (-20000.0, -5000.0, 5000.0, 20000.0)
        near = (
            ("beta_plus_2ms", dict(clock_offset_s=2.0e-3)),
            ("beta_minus_2ms", dict(clock_offset_s=-2.0e-3)),
            ("rate_plus_20ppm", dict(clock_scale_ppm=20.0)),
            ("rate_minus_20ppm", dict(clock_scale_ppm=-20.0)),
        )
        accels = (0.3,)
        geometry = (250.0, 1000.0, 3000.0)
    elif layer == "locked":
        offsets = (-3.0, -0.5, 0.5, 3.0)
        rates = (-25000.0, -10000.0, 10000.0, 25000.0)
        near = (
            ("beta_plus_1ms", dict(clock_offset_s=1.0e-3)),
            ("beta_minus_1ms", dict(clock_offset_s=-1.0e-3)),
            ("rate_plus_10ppm", dict(clock_scale_ppm=10.0)),
            ("rate_minus_10ppm", dict(clock_scale_ppm=-10.0)),
        )
        accels = (0.2, 0.4)
        geometry = (150.0, 600.0, 5000.0)
    else:
        raise ValueError(f"unknown layer {layer!r}")

    conditions: list[ClaimCondition] = []

    def add(name, stratum, mechanism, level, note, n_trials=TRIALS_PER_CONDITION, **overrides):
        conditions.append(
            ClaimCondition(
                name=name,
                stratum=stratum,
                mechanism=mechanism,
                level=level,
                note=note,
                scenario=replace(BASE, **overrides),
                n_trials=n_trials,
            )
        )

    add(
        "control_zero",
        "control",
        "zero_perturbation",
        "no perturbation",
        "zero-perturbation control, 20 dB nominal SNR",
        snr_db=20.0,
    )
    add(
        "control_nominal_snr",
        "nominal_snr_control",
        "nominal_snr_control",
        "no perturbation",
        "nominal-SNR control (independent replicate), 20 dB",
        snr_db=20.0,
    )
    for offset in offsets:
        add(
            f"offset_{offset:+.3g}s".replace("+", "p").replace("-", "m").replace(".", "d"),
            "clock_offset",
            "clock_offset",
            f"beta={offset:+.3g} s",
            "constant clock offset; observational equivalence with t0 (20 dB)",
            clock_offset_s=offset,
            snr_db=20.0,
        )
    for ppm in rates:
        add(
            f"rate_{ppm:+.0f}ppm".replace("+", "p").replace("-", "m"),
            "clock_rate",
            "clock_rate",
            f"rate={ppm:+.0f} ppm",
            "constant clock rate error; observational source rescaling (20 dB)",
            clock_scale_ppm=ppm,
            snr_db=20.0,
        )
    for name, overrides in near:
        add(
            f"near_identity_{name}",
            "near_identity",
            "near_identity",
            ", ".join(f"{key}={value:g}" for key, value in overrides.items()),
            "near-identity clock transform; group-axiom and stability control (20 dB)",
            snr_db=20.0,
            **overrides,
        )
    for value in accels:
        add(
            f"accel_{value:g}",
            "model_misspecification",
            "acceleration",
            f"accel={value:g} m/s^2",
            "constant along-track acceleration; model misspecification, NOT used to claim constant-velocity invariance",
            accel=value,
            snr_db=20.0,
        )
    for distance in geometry:
        add(
            f"geometry_b{distance:g}m",
            "geometry_stress",
            "geometry",
            f"b={distance:g} m",
            "unseen closest-approach distance; geometry stress test (not an equal-accuracy claim), 20 dB",
            b=distance,
            snr_db=20.0,
        )
    add(
        "null",
        "null",
        "null",
        "noise only, 0 dB reference",
        "noise-only observation; no constant-velocity source",
        emit_signal=False,
        snr_db=0.0,
    )
    return conditions


def condition_seed(layer: str, condition_index: int, trial: int) -> int:
    base = DEV_SEED_BASE if layer == "development" else LOCKED_SEED_BASE
    return base + 1000 * int(condition_index) + int(trial)


# ---------------------------------------------------------------------------
# Trial pipeline (no truth in any decision)
# ---------------------------------------------------------------------------

def run_trial(condition: ClaimCondition, trial: int, seed: int, layer: str) -> dict:
    """Generate, fit, run the PR-4d adequacy block, compute truth-free claim metrics."""
    scenario = replace(condition.scenario, seed=int(seed))
    observation = generate(scenario)
    track = estimate_if_track(
        observation.signal,
        scenario.fs,
        frame_len=FRAME_LEN,
        hop=HOP,
        f_min=F_MIN,
        f_max=F_MAX,
        t_start=float(observation.t[0]),
    )
    hardened = fit_hardened(track.t, track.f, c=scenario.c)
    params = np.array([hardened.f0, hardened.v, hardened.t0, hardened.b], dtype=np.float64)
    adequacy = evaluate_adequacy(
        track.t,
        track.f,
        params,
        hardened.sigma_f_hz,
        hardened.optimization_status,
        c=scenario.c,
    )
    metrics = claim_metrics(hardened, adequacy)
    truth = claim_truth(scenario)
    return {
        "condition": condition.name,
        "trial": int(trial),
        "seed": int(seed),
        "layer": layer,
        "stratum": condition.stratum,
        "mechanism": condition.mechanism,
        "level": condition.level,
        "evaluation_only": {
            "scenario": {
                key: (float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else value)
                for key, value in asdict(scenario).items()
            },
            "claim_truth": truth,
        },
        "observation": {
            "sigma_f_hz": float(hardened.sigma_f_hz),
            "n_samples": int(track.t.size),
            "duration_s": float(scenario.duration),
        },
        "hardened": {
            "params": {name: float(value) for name, value in hardened.params.items()},
            "se": {name: float(value) for name, value in hardened.se.items()},
            "optimization_status": hardened.optimization_status,
            "adequacy_status": adequacy["model_adequacy_status"],
            "identifiability_status": adequacy["identifiability_status"],
            "worst_rel_se": hardened.worst_rel_se,
            "condition_number": hardened.condition_number,
        },
        "claim_metrics": metrics,
    }


def _worker(task: tuple[ClaimCondition, int, int, str]) -> dict:
    condition, trial, seed, layer = task
    return _jsonable(run_trial(condition, trial, seed, layer))


# ---------------------------------------------------------------------------
# Threshold selection (development only; uses development truth for calibration)
# ---------------------------------------------------------------------------

def _tolerance_error(claim_id: str, value: float, truth: float) -> Optional[float]:
    definition = CLAIMS_BY_ID[claim_id]
    tolerance = definition["claim_tolerance"]
    if not np.isfinite(value) or not np.isfinite(truth):
        return None
    if tolerance["kind"] == "relative":
        scale = abs(truth) if truth != 0.0 else 1.0
        return abs(value - truth) / scale
    return abs(value - truth)


def select_thresholds(raw_records: list[dict]) -> tuple[dict, dict]:
    nominal_strata = set(THRESHOLD_SELECTION["nominal_clock_strata"])
    margin = float(THRESHOLD_SELECTION["cap_fraction_of_claim_tolerance"])
    validity_target = float(THRESHOLD_SELECTION["validity_target"])
    minimum_supported = int(THRESHOLD_SELECTION["minimum_supported"])
    thresholds: dict[str, float] = {}
    calibration: dict[str, dict] = {}
    for claim_id in EVALUATED_CLAIMS:
        definition = CLAIMS_BY_ID[claim_id]
        tolerance = definition["claim_tolerance"]
        rows = []
        for record in raw_records:
            if record["stratum"] not in nominal_strata:
                continue
            for metric in record["claim_metrics"]:
                if metric["claim_id"] != claim_id or not metric["gates_ok"]:
                    continue
                truth = record["evaluation_only"]["claim_truth"][claim_id]
                error = _tolerance_error(claim_id, metric["value"], truth)
                if error is None or not np.isfinite(metric["uncertainty"]):
                    continue
                rows.append({"uncertainty": float(metric["uncertainty"]), "error": float(error)})
        uncertainties = np.array([row["uncertainty"] for row in rows], dtype=np.float64)
        errors = np.array([row["error"] for row in rows], dtype=np.float64)
        candidates = []
        chosen = None
        fallback = False
        if uncertainties.size:
            for quantile in THRESHOLD_SELECTION["candidate_quantiles"]:
                threshold = float(np.quantile(uncertainties, quantile))
                if threshold <= 0.0:
                    continue
                if threshold > margin * tolerance["value"]:
                    continue
                supported = uncertainties <= threshold
                count = int(np.sum(supported))
                if count < minimum_supported:
                    continue
                validity = float(np.mean(errors[supported] <= tolerance["value"]))
                candidates.append(
                    {
                        "quantile": float(quantile),
                        "threshold": threshold,
                        "supported": count,
                        "validity": validity,
                    }
                )
                if validity >= validity_target:
                    chosen = threshold
        if chosen is None:
            chosen = margin * tolerance["value"]
            fallback = True
        supported = uncertainties <= chosen if uncertainties.size else np.array([], dtype=bool)
        thresholds[claim_id] = float(chosen)
        calibration[claim_id] = {
            "metric": definition["uncertainty_metric"]["expression"],
            "claim_tolerance": tolerance,
            "n_nominal_clock_gate_ok": int(uncertainties.size),
            "candidates": candidates,
            "chosen_threshold": float(chosen),
            "fallback": bool(fallback),
            "dev_supported": int(np.sum(supported)),
            "dev_support_rate": float(np.mean(supported)) if uncertainties.size else None,
            "dev_validity": float(np.mean(errors[supported] <= tolerance["value"])) if uncertainties.size and np.any(supported) else None,
        }
    evidence = {
        "layer": "development",
        "seed_base": DEV_SEED_BASE,
        "nominal_clock_strata": sorted(nominal_strata),
        "rule": THRESHOLD_SELECTION["rule"],
        "per_claim": calibration,
    }
    return thresholds, evidence


# ---------------------------------------------------------------------------
# Finalization and summaries
# ---------------------------------------------------------------------------

def finalize_record(raw: dict, protocol: dict) -> dict:
    statuses = apply_claim_statuses(raw["claim_metrics"], protocol)
    truth = raw["evaluation_only"]["claim_truth"]
    truth_tolerance = {
        claim["claim_id"]: within_tolerance(claim["claim_id"], claim["value"], truth[claim["claim_id"]])
        for claim in statuses
        if claim["claim_id"] in EVALUATED_CLAIMS
    }
    return {
        "condition": raw["condition"],
        "trial": raw["trial"],
        "seed": raw["seed"],
        "layer": raw["layer"],
        "stratum": raw["stratum"],
        "mechanism": raw["mechanism"],
        "level": raw["level"],
        "evaluation_only": {
            "scenario": raw["evaluation_only"]["scenario"],
            "claim_truth": truth,
            "estimate_within_tolerance": truth_tolerance,
        },
        "observation": raw["observation"],
        "hardened": raw["hardened"],
        "claims": statuses,
    }


def _counts(values) -> dict:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _claim_summaries(records: list[dict]) -> list[dict]:
    summaries = []
    for claim_id in ALL_CLAIMS:
        rows = []
        for record in records:
            for claim in record["claims"]:
                if claim["claim_id"] == claim_id:
                    rows.append(claim)
        statuses = _counts(claim["status"] for claim in rows)
        reasons = _counts(code for claim in rows for code in claim["reason_codes"])
        summary = {
            "claim_id": claim_id,
            "n": len(rows),
            "status_counts": statuses,
            "supported_conditional_rate": (
                statuses.get("supported_conditional", 0) / len(rows) if rows else None
            ),
            "undetermined_rate": statuses.get("undetermined", 0) / len(rows) if rows else 0.0,
            "contradicted_rate": statuses.get("contradicted", 0) / len(rows) if rows else 0.0,
            "reason_counts": reasons,
            "by_stratum": {},
        }
        for stratum in STRATA:
            subset = [
                claim
                for record in records
                if record["stratum"] == stratum
                for claim in record["claims"]
                if claim["claim_id"] == claim_id
            ]
            if subset:
                summary["by_stratum"][stratum] = {
                    "n": len(subset),
                    "status_counts": _counts(claim["status"] for claim in subset),
                    "supported_conditional_rate": (
                        sum(claim["status"] == "supported_conditional" for claim in subset) / len(subset)
                    ),
                }
        summaries.append(summary)
    return summaries


def _strata_summaries(records: list[dict]) -> list[dict]:
    summaries = []
    for stratum in STRATA:
        subset = [record for record in records if record["stratum"] == stratum]
        if not subset:
            continue
        statuses = {
            claim_id: _counts(
                claim["status"] for record in subset for claim in record["claims"] if claim["claim_id"] == claim_id
            )
            for claim_id in EVALUATED_CLAIMS
        }
        within = {
            claim_id: _counts(
                record["evaluation_only"]["estimate_within_tolerance"].get(claim_id)
                for record in subset
            )
            for claim_id in EVALUATED_CLAIMS
        }
        summaries.append(
            {
                "stratum": stratum,
                "n": len(subset),
                "mechanisms": _counts(record["mechanism"] for record in subset),
                "claim_status_counts": statuses,
                "evaluation_only_within_tolerance": within,
            }
        )
    return summaries


def _digest(document) -> str:
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def _jsonable(obj):
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
# Layer runner
# ---------------------------------------------------------------------------

def run_layer(
    layer: str,
    output: str,
    jobs: int = 1,
    trials_override: Optional[int] = None,
    name_filter: Optional[str] = None,
    protocol_path: Optional[str] = None,
    progress: bool = True,
) -> tuple[dict, dict]:
    """Run one layer.  Returns ``(artifact, protocol)``."""
    conditions = _base_conditions(layer)
    if name_filter:
        conditions = [
            condition for condition in conditions if name_filter in condition.name or name_filter == condition.stratum
        ]
        if not conditions:
            raise ValueError(f"no condition matches filter {name_filter!r}")
    if trials_override is not None:
        if int(trials_override) < 1:
            raise ValueError("--trials must be >= 1")
        conditions = [replace(condition, n_trials=int(trials_override)) for condition in conditions]

    tasks = []
    for index, condition in enumerate(conditions):
        for trial in range(condition.n_trials):
            tasks.append((condition, trial, condition_seed(layer, index, trial), layer))

    started = time.time()
    raws: list[dict] = []
    if jobs <= 1:
        for position, task in enumerate(tasks):
            raws.append(_worker(task))
            if progress and (position + 1) % 200 == 0:
                print(f"  ... {position + 1}/{len(tasks)} trials", file=sys.stderr)
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            for position, raw in enumerate(pool.map(_worker, tasks, chunksize=8)):
                raws.append(raw)
                if progress and (position + 1) % 200 == 0:
                    print(f"  ... {position + 1}/{len(tasks)} trials", file=sys.stderr)
    elapsed = time.time() - started
    raws.sort(key=lambda record: (record["condition"], record["trial"]))

    proof = derive_proof()
    if not verify_proof_digest(proof):
        raise RuntimeError("symbolic proof digest verification failed")

    environment = {
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
    }
    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    if layer == "development":
        thresholds, calibration = select_thresholds(raws)
        certificate, certificate_sha, certificate_file = load_certificate()
        protocol = build_protocol(
            proof,
            thresholds=thresholds,
            calibration=calibration,
            certificate=certificate,
            certificate_sha256=certificate_sha,
            certificate_path=certificate_file,
            environment=environment,
            generated_at=generated_at,
        )
        written_path = protocol_path or os.path.join(os.path.dirname(os.path.abspath(output)), "claims-protocol.json")
        protocol_file_sha = write_protocol(protocol, written_path)
    else:
        resolved_protocol = protocol_path or os.path.join(os.path.dirname(os.path.abspath(output)), "claims-protocol.json")
        if not os.path.exists(resolved_protocol):
            raise ValueError(
                f"frozen claims protocol not found at {resolved_protocol}; run the development layer first"
            )
        protocol = load_protocol(resolved_protocol)
        if symbolic_proof_digest(protocol) != proof["proof_digest"]:
            raise ValueError(
                "frozen protocol was built against a different symbolic proof digest "
                f"({symbolic_proof_digest(protocol)} != {proof['proof_digest']}); rebuild the development layer"
            )
        written_path = resolved_protocol
        protocol_file_sha = None

    records = [finalize_record(raw, protocol) for raw in raws]

    artifact = {
        "experiment": EXPERIMENT_NAME,
        "layer": layer,
        "protocol_version": protocol["protocol_version"],
        "protocol_digest": protocol["protocol_digest"],
        "evidence_digest": protocol["evidence_digest"],
        "protocol_path": written_path,
        "protocol_file_sha256": protocol_file_sha,
        "symbolic_proof_digest": proof["proof_digest"],
        "protocol_gate": {
            "l1_completeness": evidence_gate(protocol)["l1_completeness"],
            "certificate_conflicts": evidence_gate(protocol)["certificate_conflicts"],
            "nuisance_contradictions": evidence_gate(protocol)["nuisance_contradictions"],
            "withheld_claims": evidence_gate(protocol)["withheld_claims"],
            "blocked": evidence_gate(protocol)["blocked"],
        },
        "seed_base": DEV_SEED_BASE if layer == "development" else LOCKED_SEED_BASE,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "grid": {
            "conditions": [
                {
                    "name": condition.name,
                    "stratum": condition.stratum,
                    "mechanism": condition.mechanism,
                    "level": condition.level,
                    "note": condition.note,
                    "n_trials": int(condition.n_trials),
                    "scenario": {key: value for key, value in asdict(condition.scenario).items()},
                }
                for condition in conditions
            ],
            "strata": {stratum: sum(c.n_trials for c in conditions if c.stratum == stratum) for stratum in STRATA},
            "condition_count": len(conditions),
            "trial_count": len(tasks),
        },
        "thresholds": protocol_thresholds(protocol),
        "threshold_precision": THRESHOLD_PRECISION,
        "threshold_calibration": evidence(protocol).get("development_calibration"),
        "environment": environment,
        "elapsed_s": float(elapsed),
        "records_sha256": _digest(records),
        "claim_summaries": _claim_summaries(records),
        "strata_summaries": _strata_summaries(records),
        "trials": records,
    }
    return _jsonable(artifact), protocol


def write_artifact(artifact: dict, output: str) -> str:
    directory = os.path.dirname(os.path.abspath(output))
    os.makedirs(directory, exist_ok=True)
    payload = (json.dumps(artifact, indent=1, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    with open(output, "wb") as handle:
        handle.write(payload)
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="PR-4e-L1 claim experiment (development / locked).")
    parser.add_argument("--layer", required=True, choices=("development", "locked"))
    parser.add_argument("--out", required=True, help="artifact JSON path")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--trials", type=int, default=None)
    parser.add_argument("--filter", default=None)
    parser.add_argument("--protocol", default=None, help="protocol JSON path (default: next to --out)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    try:
        artifact, protocol = run_layer(
            args.layer,
            args.out,
            jobs=args.jobs,
            trials_override=args.trials,
            name_filter=args.filter,
            protocol_path=args.protocol,
            progress=not args.quiet,
        )
    except ValueError as exc:
        print(f"experiment: {exc}", file=sys.stderr)
        return 2
    sha = write_artifact(artifact, args.out)

    print(
        f"layer: {artifact['layer']}  trials: {len(artifact['trials'])}  "
        f"conditions: {artifact['grid']['condition_count']}  jobs: {args.jobs}  "
        f"elapsed: {artifact['elapsed_s']:.1f} s"
    )
    print(
        f"protocol_version: {artifact['protocol_version']}  protocol_digest: {artifact['protocol_digest']}"
    )
    print(f"evidence_digest: {artifact['evidence_digest']}")
    print(f"threshold_precision: {artifact['threshold_precision']} significant digits (frozen payload)")
    print(f"symbolic_proof_digest: {artifact['symbolic_proof_digest']}")
    print(f"records_sha256: {artifact['records_sha256']}")
    print(f"json: {args.out}  sha256: {sha}")
    strata = artifact["grid"]["strata"]
    print("strata: " + ", ".join(f"{name}={count}" for name, count in strata.items() if count))
    if args.layer == "development":
        print()
        print("selected L3 thresholds (frozen before locked):")
        for claim_id, threshold in artifact["thresholds"].items():
            calibration = (artifact["threshold_calibration"] or {}).get("per_claim", {}).get(claim_id, {})
            print(
                f"  {claim_id:12s} threshold={threshold:.6g}  "
                f"dev_support_rate={calibration.get('dev_support_rate')}  "
                f"dev_validity={calibration.get('dev_validity')}  fallback={calibration.get('fallback')}"
            )
        print(f"protocol written: {artifact['protocol_path']}")
    if args.layer == "locked":
        from .boundary import write_boundary

        boundary_path = os.path.join(os.path.dirname(os.path.abspath(args.out)), "boundary.md")
        boundary_sha = write_boundary(protocol, derive_proof(), artifact, boundary_path)
        print(f"boundary_report: {boundary_path}  sha256: {boundary_sha}")
    print()
    print("claim status counts:")
    for summary in artifact["claim_summaries"]:
        print(
            f"  {summary['claim_id']:12s} n={summary['n']:4d} "
            f"status={json.dumps(summary['status_counts'])} "
            f"supported_conditional_rate={summary['supported_conditional_rate']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
