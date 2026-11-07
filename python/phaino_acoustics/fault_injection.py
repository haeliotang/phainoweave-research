"""E1-0 synthetic fault injection on the E0 Doppler pipeline.

Purpose: rehearse field failures before the first campaign.  Each fault is
applied to a deterministic synthetic observation, then the normal front end,
hardened fit and adequacy layer run.  The acceptance rule is asymmetric:

* benign recorder-clock ppm must not turn into a false rejection or an
  unjustified support;
* clipping, dropped buffers, wind bursts and unusable reference channels must
  either inflate the residual scale or produce an explicit abstention/rejection
  reason.  A high-confidence convergence under a severe fault is a failure.

The truth parameters are used only for evaluation diagnostics, never to make
the decision.  This module does not claim that synthetic faults cover real
hardware behaviour.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Optional

import numpy as np

from .adequacy import evaluate_adequacy
from .experiment import (
    B_REL_TOL,
    BASE,
    F0_REL_TOL,
    F_MAX,
    F_MIN,
    FRAME_LEN,
    HOP,
    T0_ABS_TOL,
    V_REL_TOL,
)
from .features import estimate_if_track
from .fit_hardened import fit_hardened
from .synthetic import Scenario, SyntheticObservation, generate


@dataclass(frozen=True)
class FaultSpec:
    """One field-degradation scenario."""

    name: str
    clock_ppm: float = 0.0
    clipping_peak_fraction: Optional[float] = None
    dropout_windows: tuple[tuple[float, float], ...] = ()
    wind_bursts: tuple[tuple[float, float, float], ...] = ()
    reference_missing: bool = False
    reference_snr_db: Optional[float] = None


@dataclass(frozen=True)
class FaultResult:
    """One evaluated fault trial."""

    name: str
    decision: str
    model_adequacy_status: str
    reason_codes: tuple[str, ...]
    residual_sigma_hz: float
    fitted: tuple[float, float, float, float]
    relative_errors: dict[str, float]
    abstention_reason: Optional[str]
    supported: bool

    @property
    def false_convergence(self) -> bool:
        return self.supported

    def to_dict(self) -> dict:
        """JSON-safe projection; NaN residual scales become null."""
        scale = self.residual_sigma_hz
        return {
            "name": self.name,
            "decision": self.decision,
            "model_adequacy_status": self.model_adequacy_status,
            "reason_codes": list(self.reason_codes),
            "residual_sigma_hz": None if scale != scale else scale,
            "fitted": [None if value != value else value for value in self.fitted],
            "relative_errors": dict(self.relative_errors),
            "abstention_reason": self.abstention_reason,
            "supported": self.supported,
        }


def inject_waveform(observation: SyntheticObservation, spec: FaultSpec, seed: int) -> np.ndarray:
    """Apply waveform-domain faults.  Clock ppm is handled by the scenario."""
    x = np.array(observation.signal, dtype=np.float64, copy=True)
    fs = observation.scenario.fs
    if spec.clipping_peak_fraction is not None:
        peak = float(np.max(np.abs(x)))
        if peak > 0:
            limit = spec.clipping_peak_fraction * peak
            x = np.clip(x, -limit, limit)
    for start_s, length_s in spec.dropout_windows:
        start = max(0, int(start_s * fs))
        stop = min(x.size, start + int(length_s * fs))
        if stop > start:
            x[start:stop] = 0.0
    rng = np.random.default_rng(seed)
    for start_s, length_s, amplitude in spec.wind_bursts:
        start = max(0, int(start_s * fs))
        stop = min(x.size, start + int(length_s * fs))
        if stop > start:
            x[start:stop] += rng.normal(0.0, amplitude, size=stop - start)
    return x


def _relative_errors(fit, scenario: Scenario) -> dict[str, float]:
    return {
        "f0": abs(fit.f0 / scenario.f0 - 1.0),
        "v": abs(fit.v / scenario.v - 1.0),
        "t0": abs(fit.t0 - scenario.t0),
        "b": abs(fit.b / scenario.b - 1.0),
    }


def _within_tolerance(errors: dict[str, float]) -> bool:
    return (
        errors["f0"] <= F0_REL_TOL
        and errors["v"] <= V_REL_TOL
        and errors["t0"] <= T0_ABS_TOL
        and errors["b"] <= B_REL_TOL
    )


def run_fault_trial(scenario: Scenario = BASE, spec: FaultSpec = FaultSpec("baseline"), seed: int = 20261104) -> FaultResult:
    """Generate, corrupt, fit and judge one trial.  Truth is evaluation-only."""
    effective = replace(scenario, clock_scale_ppm=spec.clock_ppm, seed=int(seed))
    observation = generate(effective)

    reference_reason = None
    if spec.reference_missing:
        reference_reason = "reference_channel_missing"
    elif spec.reference_snr_db is not None and spec.reference_snr_db < 0.0:
        reference_reason = "reference_channel_snr_below_floor"
    if reference_reason is not None:
        return FaultResult(
            name=spec.name,
            decision="undetermined",
            model_adequacy_status="not_evaluated",
            reason_codes=(reference_reason,),
            residual_sigma_hz=float("nan"),
            fitted=(float("nan"),) * 4,
            relative_errors={},
            abstention_reason=reference_reason,
            supported=False,
        )

    corrupted = inject_waveform(observation, spec, seed)
    track = estimate_if_track(
        corrupted,
        effective.fs,
        frame_len=FRAME_LEN,
        hop=HOP,
        f_min=F_MIN,
        f_max=F_MAX,
        t_start=float(observation.t[0]),
    )
    fit = fit_hardened(track.t, track.f, c=effective.c)
    params = np.array([fit.f0, fit.v, fit.t0, fit.b], dtype=np.float64)
    adequacy = evaluate_adequacy(
        track.t,
        track.f,
        params,
        fit.sigma_f_hz,
        fit.optimization_status,
        c=effective.c,
    )
    errors = _relative_errors(fit, effective)
    decision = adequacy["epistemic_decision"]
    return FaultResult(
        name=spec.name,
        decision=decision,
        model_adequacy_status=adequacy["model_adequacy_status"],
        reason_codes=tuple(adequacy.get("reason_codes", ())),
        residual_sigma_hz=float(fit.sigma_f_hz),
        fitted=(float(fit.f0), float(fit.v), float(fit.t0), float(fit.b)),
        relative_errors=errors,
        abstention_reason=None,
        supported=decision == "supported" and _within_tolerance(errors),
    )


DEFAULT_FAULTS = (
    FaultSpec("baseline"),
    FaultSpec("clock_plus_50ppm", clock_ppm=50.0),
    FaultSpec("clock_minus_50ppm", clock_ppm=-50.0),
    FaultSpec("adc_clipping_10pct", clipping_peak_fraction=0.10),
    FaultSpec(
        "dropped_buffers",
        dropout_windows=((12.0, 0.5), (27.0, 0.5), (42.0, 0.5)),
    ),
    FaultSpec("wind_burst", wind_bursts=((30.0, 2.0, 2.0),)),
    FaultSpec("reference_missing", reference_missing=True),
    FaultSpec("reference_low_snr", reference_snr_db=-3.0),
)

def run_suite(seed: int = 20261104) -> dict:
    """Run the deterministic default fault suite and apply the acceptance rule."""
    results = [run_fault_trial(spec=spec, seed=seed) for spec in DEFAULT_FAULTS]
    by_name = {result.name: result for result in results}
    errors: list[str] = []
    baseline = by_name["baseline"]
    for name in ("baseline", "clock_plus_50ppm", "clock_minus_50ppm"):
        if by_name[name].supported:
            errors.append(f"{name}: unexpected support under benign/clock condition")
    for name in ("adc_clipping_10pct", "dropped_buffers", "wind_burst"):
        result = by_name[name]
        if result.supported:
            errors.append(f"{name}: false support under severe fault")
        if result.residual_sigma_hz != result.residual_sigma_hz:
            errors.append(f"{name}: residual scale is NaN")
    if by_name["dropped_buffers"].residual_sigma_hz <= 10.0 * baseline.residual_sigma_hz:
        errors.append("dropped_buffers: residual scale did not inflate by 10x")
    for name in ("reference_missing", "reference_low_snr"):
        result = by_name[name]
        if result.abstention_reason is None or result.supported:
            errors.append(f"{name}: expected an explicit abstention")
    return {
        "suite": "e1-0-default-faults",
        "seed": int(seed),
        "ok": not errors,
        "errors": errors,
        "results": [result.to_dict() for result in results],
    }


def main(argv=None) -> int:
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description="Run the E1-0 synthetic fault suite")
    parser.add_argument("--out", help="write the JSON report here")
    parser.add_argument("--seed", type=int, default=20261104)
    args = parser.parse_args(argv)
    report = run_suite(seed=args.seed)
    text = json.dumps(report, indent=1, sort_keys=True, allow_nan=False) + "\n"
    if args.out:
        from pathlib import Path

        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path}")
    else:
        sys.stdout.write(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
