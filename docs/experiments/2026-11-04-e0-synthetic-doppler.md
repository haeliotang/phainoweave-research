# E0 — Synthetic Doppler identifiability

**Experiment id:** `E0-synthetic-doppler`
**Status:** complete (pre-registered 2026-11-04T18:25:23Z; sweep finished 2026-11-04T18:26:41Z)
**Report version:** 1
Date: 2026-11-04 (UTC)
Author: PhainoWeave agent `acoustics-e0` (PR-2), for Haelio Tang
Related: [ROADMAP §4 M1 plan](../roadmap/ROADMAP.md#4-m1-experimental-plan) · [benchmark and evals](../roadmap/benchmark-and-evals.md) · [ADR 0002](../decisions/0002-verification-first-inference.md) · [experiments index](./README.md) · code: [`python/phaino_acoustics/`](../../python/phaino_acoustics/)

**Preregistration.** The section *Preregistered expectation* below was written and
frozen **before the sweep was run**. Its exact text was copied to a separate
freeze file, hashed, and the digest is recorded under *Preregistration record*.
The expected outcome, the "recovered" tolerance, the sweep axes, the baselines,
and the decision rule were fixed at that point. Results below were appended
afterwards; none of the pre-registered text was edited afterwards.

> **Scope in one line.** E0 asks whether a physical Doppler model, fitted to a
> noisy acoustic observation of a *known* moving source, recovers the true
> relative-motion parameters — and under which noise, acceleration, clock, and
> window conditions it fails, and which parameters are identifiable at all.
> It is synthetic-only. It is **not** geo-localization, says nothing about real
> recordings or real aircraft, and cannot support a capability claim.

**Result in one line.** The joint physical fit recovers all four parameters with
70–240× margin over the pre-declared tolerance for SNR ≥ −5 dB at a 60 s
window (median b error 0.7 m at 3 km), fails abruptly at
−10 dB because the front end starts picking noise peaks, and beats the naive
IF inversion decisively; the binding limits are unmodelled acceleration
(threshold between 0.1 and 0.25 m/s²) and a short window (5 s collapses
(v,b) and (f0,t0) onto two free combinations). A constant recorder clock
offset is exactly degenerate with the event time, and a clock *rate* error is
an exact source rescaling that only matters above ≈1% (10 000 ppm).

## Question

A narrowband source moves on a straight line past a stationary receiver at
closest-approach distance `b`, speed `v`, rest frequency `f0`, at closest
approach time `t0`, with sound speed `c`. The observable is the instantaneous
frequency of the received narrowband component, which in the delay-free
kinematic model is

```
f_obs(t) = f0 / (1 - v_r(t)/c),      v_r(t) = -d/dt ||x_s(t) - x_o||      (positive approaching)
```

Given a noisy observation of `f_obs(t)` over a finite window and an
instantaneous-frequency front end that does **not** use the physical model,
E0 asks four questions with pre-declared, measurable answers:

1. **Recovery.** Under additive white Gaussian noise at a stated per-sample
   SNR, does a deterministic joint least-squares fit of the physical model
   recover `f0`, `v`, `t0`, `b` within a pre-declared tolerance, and with what
   error distribution?
2. **Baseline.** Does the physical fit beat a naive, model-free inversion of
   the tracked instantaneous frequency — measured by parameter-recovery error
   and residual RMS, not by any location error?
3. **Identifiability.** Which parameter pairs are strongly correlated, and how
   does that depend on SNR and observation-window length? (A parameter pair
   that is not identifiable cannot be "recovered" no matter how high the SNR.)
4. **Failure.** What acceleration mismatch, recorder clock-rate error, clock
   offset, and short-window conditions break the fit, and at what measured
   threshold?

E0 is the first science artifact of the project. A negative answer — a
threshold very close to the operating point, a parameter that is not
identifiable, a failure mode that dominates — is a success for E0, because it
is a measured limit that later real-audio work must respect.

## Preregistered expectation

**Written before the sweep.** Everything in this section — the tolerance for
"recovered", the sweep axes, the baselines, the predicted outcomes, the
decision rule — was fixed before the first sweep run. Predictions are derived
from the model algebra and from the front-end construction, not from sweep
results. Where a prediction is uncertain it is stated as a range.

### Pre-declared "recovered" tolerance (primary metric)

A trial counts as **recovered** if and only if all four conditions hold:

| Parameter | Tolerance | Rationale (operational, not tuned to results) |
|---|---|---|
| `f0` | `\|f0_hat/f0 - 1\| <= 1%` | rest-frequency ambiguity of a few Hz on a tonal component; 1% is the loosest value a kinematic verifier should accept as "same source" |
| `v` | `\|v_hat/v - 1\| <= 2%` | 2% of 250 m/s = 5 m/s, the order of along-track speed uncertainty that still constrains a candidate track |
| `t0` | `\|t0_hat - t0\| <= 0.25 s` | event-time precision needed to join an acoustic event to a candidate track time window |
| `b` | `\|b_hat/b - 1\| <= 5%` | 5% of 3 km = 150 m slant range, the coarsest range that is useful at all |

The fit must also have converged (stationary point of the least-squares cost)
and be physically valid (`f0, v, b > 0`). `t0` is scored as an **absolute**
error in seconds: its relative error is not meaningful because the time origin
is arbitrary. `f0`, `v`, `b` are scored as relative errors.

The **primary metric** is the success rate at each swept condition with
N = 100 fixed-seed noise realizations. The full error distribution (median,
p25–p75, p90) is reported alongside, because the tolerance is coarse relative
to the achieved precision at high SNR and the distribution carries the
information the success rate does not.

### Sweep axes (fixed before running)

| Axis | Values | SNR | N | Why |
|---|---|---|---|---|
| per-sample SNR | −10, −5, 0, 5, 10, 20 dB | — | 100 | the required noise axis |
| window length | 5, 10, 20, (60) s | 5 dB | 100 | short-window identifiability failure |
| acceleration mismatch (data has `a`, model assumes 0) | 0.1, 0.25, 0.5 m/s² | 20 dB | 100 | model-mismatch threshold |
| recorder clock rate (fit assumes exact clock) | 10, 100, 1000, 20000, 50000 ppm | 20 dB | 100 | suspected failure mode told in ppm |
| constant clock offset | 0.3, 2.0 s | 20 dB | 100 | expected exact degeneracy with `t0` |
| amplitude variation | 1/r spreading; 30% AM at 0.7 Hz | 5 dB | 100 | front-end must be amplitude-insensitive |
| geometry (exploratory) | (v,b) = (100,300), (250,30 km), (60,120) m | 5 dB | 100 | is one geometry enough? |
| null | no signal, 0 dB-equivalent noise | — | 100 | does the fit reject noise-only data? |

N = 100 trials per condition. Only the noise realization varies across trials;
the true world state is fixed per condition. Seeds are
`seed = 20261104 + 1000*condition_index + trial_index`.

### Baselines (fixed before running)

* **B0 — naive instantaneous-frequency tracking, no physical model.** The IF
  track is smoothed and inverted in closed form with textbook Doppler
  relations, with no forward-model fit, no noise model, no optimisation:
  `f0 = 2 f_hi f_lo/(f_hi+f_lo)`, `v = c(f_hi-f_lo)/(f_hi+f_lo)` from the
  extreme tracked frequencies, `t0` = the time the smoothed track crosses
  `f0` (at closest approach `v_r = 0` so `f_obs = f0`), and
  `b = f0 v^2 /(c |df/dt|)` at that time. Its parameter-recovery error and the
  RMS residual of its predicted frequency curve are the comparison.
* **B1 — the physical model fit.** Deterministic multi-start
  Levenberg–Marquardt least squares of the four-parameter model to the same IF
  track, with analytic Jacobian, `f0` profiled out for start ranking, and
  five refined starts.

Both baselines see exactly the same front end and the same IF track. No
location/region metric exists in E0; the comparison is parameter recovery and
residual RMS, as stated in the task.

### Analytic predictions (derived from the model, before the run)

`P1 — front-end bias floor.` The Hann + log-parabolic IF estimator has a
deterministic interpolation bias of order ±0.25 Hz (≈0.5 bin at 64 ms windows
and 8 kHz) that oscillates as the true frequency sweeps across DFT bins. At
high SNR this bias, not noise, limits the fit: parameter errors should floor
at order `1e-4 … 1e-3` relative and stop improving above ~10 dB.

`P2 — noise failure is abrupt, not graceful.` A 512-sample Hann frame gives
≈24 dB of processing gain, so at −10 dB per-sample the STFT peak sits only
~14 dB above the per-bin noise floor and the peak can jump to a noise maximum.
The IF track then acquires heavy-tailed outliers; a least-squares fit is
dominated by them. Prediction: success ≈ 1 for SNR ≥ 0 dB, success ≥ 0.95 at
−5 dB, and success ≤ 0.5 at −10 dB — an abrupt front-end failure rather than a
smooth degradation.

`P3 — B0 is systematically biased by window truncation, B1 is not.` In the
base geometry the 60 s window reaches only `|tau| = 30 s = 2.5 (b/v)`, where
the true radial velocity is `v_r = 232.1 m/s`, not 250 m/s. B0's extreme-value
formula therefore returns `v ≈ 232.1 m/s` (**−7.2% bias**) and
`b ≈ f0 v_B0^2/(c * slope) ≈ 2.6 km` (**≈ −14% bias**). Algebraically the
truncation cancels for `f0` and `t0`: `2 f_hi f_lo/(f_hi+f_lo) = f0` exactly
when the two window extremes are symmetric, so B0's `f0` and `t0` should be
nearly unbiased. Prediction: **B0 success = 0 at every SNR** (because `v` and
`b` fail by construction), B0 residual RMS tens of Hz, while B1 succeeds and
its residual RMS approaches the IF-tracking error (≤ 2 Hz for SNR ≥ −5 dB).

`P4 — short windows are degenerate in (v,b), not in f0 or t0.` Writing the
radial velocity in terms of `q1 = v^2/b` (closest-approach slope) and
`q2 = v/b` (transition-time scale), a short window sees mainly the leading
term, so `v` and `b` collapse onto the single combination `v^2/b` and `f0`
trades with the overall slope. Prediction: median `|rho|(v,b) > 0.98` at
T = 5 s and T = 10 s, falling to `0.85–0.95` at T = 60 s; median worst-case
relative standard error ≥ 10% at T = 5 s versus ≤ 1e-3 at T = 60 s; success at
T = 5 s (5 dB) between 0.3 and 0.7, driven by `v`/`b` failures, while T ≥ 10 s
should keep success ≈ 1.

`P5 — acceleration mismatch has a predictable threshold.` A constant
acceleration changes the along-track speed by ±aT/2 over the window
(±15 m/s at a = 0.5 m/s², i.e. 6% of v). A zero-acceleration fit cannot
represent it. Prediction: a = 0.1 m/s² stays within tolerance (v error ≈ 1%,
b error ≈ 3%), a = 0.25 m/s² fails (v ≈ 3%, b ≈ 7%), a = 0.5 m/s² fails
clearly. Measured acceleration threshold expected between 0.1 and 0.25 m/s².

`P6 — clock rate error is an exact reparameterisation; clock offset is an
exact degeneracy.` With `t_true = t_nom(1+eps) + delta`, the nominal model can
absorb

```
f0 -> f0 (1+eps),    v -> v,    t0 -> (t0 - delta)/(1+eps),    b -> b/(1+eps)
```

exactly. Therefore (i) a **constant clock offset `delta` is exactly
degenerate with `t0`**: B1 will return `t0_hat = t0 - delta` and every other
parameter unchanged, and this is an identifiability statement, not an
estimator failure; (ii) a **clock-rate error `eps`** biases `f0`, `t0`, `b`
by about `+eps`, `-eps`, `-eps` and leaves `v` unchanged. Prediction: 10, 100
and 1000 ppm are harmless (biases ≤ 0.1%, far inside tolerance); 20000 ppm
(2%) fails on `f0` (1% tolerance) and `t0` (0.39 s > 0.25 s); 50000 ppm fails
on `f0` and `t0`, with `b` bias ≈ −4.8% just inside its 5% tolerance. The
clock-rate failure threshold is therefore ≈ 1% ≈ 10 000 ppm, and it is *not*
a noise effect.

`P7 — amplitude variation is harmless for a spectral-peak front end.` 1/r
spreading lowers the edge SNR by up to 8.6 dB and 30% AM modulates it; the
frequency estimate does not use amplitude. Prediction: success = 1 at 5 dB
for both, IF RMS at most 2× the constant-amplitude 5 dB case.

`P8 — geometry matters through the window/timescale ratio.` (100 m/s, 300 m)
and (60 m/s, 120 m) have `b/v` of 3 s and 2 s, so a 60 s window covers the
asymptotes and should pass; (250 m/s, 30 km) has `b/v = 120 s`, so the 60 s
window covers only ±0.25 time scales, leaving `v` and `b` nearly degenerate.
Prediction: (250 m/s, 30 km) success < 0.5 and `|rho|(v,b) > 0.98`; the other
two ≈ 1.

`P9 — null data are rejected.` With no signal the IF track is noise-driven;
the physical model should explain almost none of its variance. Prediction:
accepted-Doppler rate (improvement ratio ≥ 50% and converged) ≤ 0.05,
"recovered within tolerance" rate 0, and residual RMS orders of magnitude
larger than on signal data.

`P10 — clock offset is reported as a finding, not hidden.` Because the offset
is exactly absorbed by `t0`, offset trials will score as "not recovered" under
the pre-declared `t0` tolerance whenever `delta > 0.25 s`, even though the fit
is otherwise perfect. This is expected and is the honest reading: a recorder
clock offset cannot be distinguished from a different event time without an
external time reference.

### Decision rule (fixed before running)

E0 is a pass/fail on *estimator and identifiability questions only*; it cannot
pass or fail a real-world capability test. The decision rule is:

* **Continue** the kinematic-verifier line to PR-3 (real-audio / M1
  feasibility) if (a) B1 success ≥ 0.9 for SNR ≥ 0 dB at the 60 s base
  window, (b) B1 beats B0 on at least `f0`, `v` and `b` recovery and on
  residual RMS by a wide margin at every SNR where the front end works, and
  (c) the failure thresholds for acceleration and clock rate are quantified
  and, at the operating point, comfortably above recorder/motion reality
  (≫ 1000 ppm clock error and ≫ 0.1 m/s² unmodelled acceleration) or are
  reported as binding limitations.
* **Revise** (front end, estimator, or experiment scope) if B1 fails at
  SNR ≥ 0 dB, or if the parameter-pair correlations at a *practical* window
  are so high that `v`/`b` cannot be bounded within tolerance, or if the
  measured noise failure sets in at an SNR a real narrowband source cannot
  reach.
* **Abandon** the "fit the Doppler curve for absolute kinematics" approach
  only if the parameters are unidentifiable across the swept windows and
  geometries (correlations → 1 at every practical window), i.e. if the curve
  constrains only a combination and not the individual parameters.

A negative or partially negative result is a valid E0 outcome and is reported
as the finding. No threshold, metric, or prediction in this section may be
changed after the sweep; deviations are appended under their own heading.

### Disclosure: pre-freeze code smoke run

Before this section was frozen, the implementation was smoke-tested end to
end on **one noise realization per condition** (a single trial, not the
100-trial sweep) to verify that every code path executes and that the tables
render. That smoke output was not used to choose any reported sweep number,
tolerance, or prediction; the predictions above are derived from the model
algebra and the front-end construction, as stated. This disclosure is here so
a reader can judge the pre-registration knowing exactly what preceded it.

## Data (generator parameters, seeds, licenses)

**No external data.** Everything is generated by
[`python/phaino_acoustics/synthetic.py`](../../python/phaino_acoustics/synthetic.py)
from fixed seeds. License: repository code (Apache-2.0); no third-party data,
no privacy exposure, no location information anywhere in the artifact.

### Generator (fixed base geometry G1)

| Quantity | Value | Note |
|---|---|---|
| rest frequency `f0` | 500 Hz | narrowband tonal component |
| speed `v` | 250 m/s | along-track, constant (unless the acceleration axis is active) |
| closest-approach distance `b` | 3000 m | slant range at `t0` |
| closest-approach time `t0` | 20 s | on the nominal time axis |
| sound speed `c` | 343 m/s | recorded parameter, held fixed and known to the fit |
| observation window | `[t0 − 30, t0 + 30)` s, 60 s | 5× the closest-approach timescale `b/v = 12 s` |
| sample rate | 8000 Hz | Nyquist 4000 Hz; base Doppler excursion 298–1547 Hz |
| amplitude | 1.0, constant | unless the amplitude-variation axis is active |
| initial phase | 0 rad | |
| noise | i.i.d. zero-mean Gaussian per sample | |

The waveform is the kinematic realization `s(t) = A(t) cos(2π∫f_obs + φ0)`
sampled on the grid; the phase integral is a trapezoid rule on the
(metric-corrected) sample grid. The delay-free formula is used for generation
*and* fitting, so E0 does not test propagation-delay model error.

### SNR definition (exact, reported)

```
SNR_dB = 10 log10( (A0^2 / 2) / sigma^2 )
```

with `sigma^2` the per-sample noise variance and `A0` the nominal amplitude.
This is a **per-sample, full-band** SNR, not an STFT-bin or band-limited SNR.
A Hann frame of `Nw = 512` adds ≈ `10 log10(Nw/2) ≈ 24 dB` of processing gain,
so −10 dB per-sample is ≈ +14 dB in a frame. `measured_snr_db` in the
generator result is the realized `10 log10(mean(clean^2)/sigma^2)`.

### Seeds and trials

`seed = 20261104 + 1000*condition_index + trial_index`, `trial_index` in
`0…99`, condition indices fixed by the order of
[`build_conditions()`](../../python/phaino_acoustics/experiment.py). Every
condition uses N = 100 noise realizations of the same true world state.
Seeding is NumPy PCG64 through `numpy.random.default_rng`.

### Front end (fixed)

Hann-windowed STFT, frame 512 samples (64 ms), hop 256 (32 ms, 50% overlap),
search band 180–2800 Hz, log-magnitude parabolic peak interpolation. The band
is a stated front-end prior (a narrowband component is expected there); it
does not use the true parameters.

### Code and environment

Python 3.14.0, NumPy 2.4.4 (SciPy is installed but **not used**: the fit is
in-house deterministic LM). Exact command, environment record, and results
digest: see *Reproduction* at the end of the report.

## Method and baselines

### B1 — physical model fit (the estimator)

Model `f(t) = f0 / (1 + v^2 τ /(c r)), r = sqrt(v^2 τ^2 + b^2), τ = t - t0`,
zero acceleration, known `c`. `f0` is linear in the model, so it is profiled
out exactly for ranking starting points; the four parameters are then refined
jointly by Levenberg–Marquardt with an analytic Jacobian. Starting grid:
`t0` over the window at 10% steps plus the naive crossing time, `(v,b)` scaled
by 0.6/1.0/1.6 and 0.3/1.0/3.0 around the naive inversion; 90 candidates are
ranked by profiled SSE and the best 5, separated in `t0`, are refined; the
lowest-cost converged solution wins. The returned point is checked for
stationarity (`max|Jᵀr| / sqrt(SSE·n) < 1e-6`). The linearized parameter
covariance is computed from the full 4-parameter Jacobian at the solution;
because IF errors are heteroscedastic and correlated across overlapping
frames, those standard errors and correlations are a **relative
identifiability diagnostic**, not a calibrated uncertainty.

### B0 — naive IF tracking + closed-form inversion (the baseline)

No forward model, no least squares, no noise model. Smooth the IF track over
0.15 s; take `f_hi`, `f_lo` as the window extremes; invert
`f0 = 2 f_hi f_lo/(f_hi+f_lo)`, `v = c(f_hi-f_lo)/(f_hi+f_lo)`; `t0` = the
time the smoothed track crosses `f0`; `b = f0 v^2/(c |df/dt|)` at that time.
This is the estimator a practitioner writes before fitting anything. Its
residual RMS is the RMS of the frequency curve its parameters predict against
the same IF track.

### Scoring

Parameter errors as above; residual RMS in Hz of the predicted frequency curve
against the *observed* IF track; success = convergence + all four tolerances;
identifiability = median absolute linearized correlations across trials plus
the worst-case relative standard error and its eigen-direction; null
acceptance = improvement ratio over a constant-frequency model ≥ 50% and
converged. All numbers are produced by
[`experiment.py`](../../python/phaino_acoustics/experiment.py); the report's
tables are spliced from its output, not retyped.

## Results

**Run record.** 2500 trials (25 conditions × 100 trials), 8 workers, 17.3 s.
The trial-record digest is
`674213d9737f999a84aa8b57cddd9078e0bf2b2998ae02a45d0940cd98185506`; the full
per-trial JSON is the artifact listed under *Reproduction*. Every table body
below is spliced from that artifact by
`experiment.render_tables()`; nothing is retyped. "Success" means a converged
fit and all four pre-declared tolerances (`f0` 1%, `v` 2%, `t0` 0.25 s, `b`
5%); N and Wilson 95% CI are given per row.

### Recovery vs SNR (B1)

| SNR (dB) | N | success (Wilson 95% CI) | conv. | med \|Δf0\|/f0 | med \|Δv\|/v | med \|Δt0\| (s) | med \|Δb\|/b | p90 \|Δb\|/b | B1 res RMS (Hz) | IF RMS (Hz) |
|---|---|---|---|---|---|---|---|---|---|---|
| -10 | 100 | 0/100 (0%, 0–4%) | 100% | 4.4% | 1.93% | 0.31 | 2.53% | 7.04% | 132 | 133 |
| -5 | 100 | 100/100 (100%, 96–100%) | 100% | 7.82e-03% | 5.55e-03% | 0.00169 | 0.0188% | 0.0482% | 1.28 | 1.28 |
| +0 | 100 | 100/100 (100%, 96–100%) | 100% | 0.0135% | 7.93e-03% | 0.00259 | 0.0221% | 0.041% | 0.724 | 0.724 |
| +5 | 100 | 100/100 (100%, 96–100%) | 100% | 0.014% | 8.15e-03% | 0.0026 | 0.0219% | 0.0356% | 0.432 | 0.433 |
| +10 | 100 | 100/100 (100%, 96–100%) | 100% | 0.0142% | 8.71e-03% | 0.00278 | 0.0239% | 0.0297% | 0.285 | 0.286 |
| +20 | 100 | 100/100 (100%, 96–100%) | 100% | 0.0142% | 8.47e-03% | 0.00271 | 0.0236% | 0.0256% | 0.191 | 0.193 |

| SNR (dB) | B0 success | B0 med \|Δf0\|/f0 | B0 med \|Δv\|/v | B0 med \|Δt0\| (s) | B0 med \|Δb\|/b | B0 res RMS (Hz) | B1 success | B1 med \|Δf0\|/f0 | B1 med \|Δv\|/v | B1 med \|Δt0\| (s) | B1 med \|Δb\|/b | B1 res RMS (Hz) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| -10 | 0/100 (0%, 0–4%) | 0.847% | 4.45% | 0.175 | 30.4% | 161 | 0/100 (0%, 0–4%) | 4.4% | 1.93% | 0.31 | 2.53% | 132 |
| -5 | 0/100 (0%, 0–4%) | 0.161% | 7.11% | 0.03 | 24.1% | 52.4 | 100/100 (100%, 96–100%) | 7.82e-03% | 5.55e-03% | 0.00169 | 0.0188% | 1.28 |
| +0 | 0/100 (0%, 0–4%) | 0.0775% | 7.14% | 0.0126 | 21.1% | 52.6 | 100/100 (100%, 96–100%) | 0.0135% | 7.93e-03% | 0.00259 | 0.0221% | 0.724 |
| +5 | 0/100 (0%, 0–4%) | 0.0271% | 7.17% | 0.00549 | 19.7% | 54.6 | 100/100 (100%, 96–100%) | 0.014% | 8.15e-03% | 0.0026 | 0.0219% | 0.432 |
| +10 | 0/100 (0%, 0–4%) | 0.0192% | 7.18% | 0.00262 | 19.7% | 54.5 | 100/100 (100%, 96–100%) | 0.0142% | 8.71e-03% | 0.00278 | 0.0239% | 0.285 |
| +20 | 0/100 (0%, 0–4%) | 0.0274% | 7.19% | 0.00406 | 19.6% | 54.8 | 100/100 (100%, 96–100%) | 0.0142% | 8.47e-03% | 0.00271 | 0.0236% | 0.191 |

B0 is decisively worse in parameter recovery at every SNR where the front end
works: at SNR ≥ −5 dB its median `v` error is 7.1% and its `b` error is
19.6–24.1%, versus B1's 0.006–0.009% and 0.019–0.024%, and B0's residual RMS is
41–286× B1's (54.8 Hz vs 0.191 Hz at 20 dB). B0 never recovers the parameters
at any SNR (0/100 everywhere) because `v` and `b` fail by construction, while
B1 is 100/100 for SNR ≥ −5 dB. The measured B0 biases match the pre-registered
analytic prediction: the window-truncated extreme-value formula returns
`v = 232 m/s` (−7.2%; measured −7.19%), while `f0` and `t0` are algebraically
unbiased (−0.027% and 4 ms at 20 dB). The predicted `b` bias was ≈ −14%;
measured −19.6%, the extra ≈5% coming from the closest-approach slope estimate,
which the 0.15 s smoother and the interpolation bias perturb (prediction **P3
partially held**).

Two caveats keep this honest. First, B1 is the data-generating model, so the
comparison measures the value of a *joint* fit over direct inversion; it is not
"physics beats a learned alternative". Second, at −10 dB the comparison is
mixed: B0's `f0` error (0.85%) and `t0` error (0.175 s) are *smaller* than B1's
(4.40%, 0.310 s), while B1 remains better on `v` and `b`. The naive inversion is
more robust to front-end outliers in some parameters and less in others, and
neither estimator's errors are calibrated uncertainty statements.

### Identifiability

| Condition | med \|ρ\|(f0,v) | med \|ρ\|(f0,b) | med \|ρ\|(v,b) | med \|ρ\|(f0,t0) | med worst rel. SE | med cond. number | median worst-direction \|components\| (f0,v,t0,b) |
|---|---|---|---|---|---|---|---|
| snr_-10dB | 0.793 | 0.52 | 0.894 | 0.817 | 0.0515 | 30.5 | (0.2, 0.22, 0.35, 1) |
| snr_-5dB | 0.805 | 0.518 | 0.886 | 0.817 | 0.000488 | 31.1 | (0.22, 0.22, 0.36, 1) |
| snr_+0dB | 0.805 | 0.518 | 0.886 | 0.817 | 0.000277 | 31.1 | (0.22, 0.22, 0.36, 1) |
| snr_+5dB | 0.805 | 0.518 | 0.886 | 0.817 | 0.000165 | 31.1 | (0.22, 0.22, 0.36, 1) |
| snr_+10dB | 0.805 | 0.518 | 0.886 | 0.817 | 0.000109 | 31.1 | (0.22, 0.22, 0.36, 1) |
| snr_+20dB | 0.805 | 0.518 | 0.886 | 0.817 | 7.32e-05 | 31.1 | (0.22, 0.22, 0.36, 1) |
| window_5s | 0.187 | 0.211 | 1 | 1 | 0.163 | 3.71e+03 | (0.0053, 0.49, 0.0045, 1) |
| window_10s | 0.421 | 0.459 | 0.999 | 0.998 | 0.0153 | 517 | (0.026, 0.46, 0.023, 1) |
| window_20s | 0.597 | 0.624 | 0.996 | 0.979 | 0.00175 | 96.9 | (0.08, 0.39, 0.084, 1) |
| geom_v100_b300 | 0.647 | 0.229 | 0.6 | 0.438 | 0.000581 | 33.4 | (0.011, 0.087, 0.038, 1) |
| geom_v250_b30000 | 0.273 | 0.301 | 1 | 1 | 0.0263 | 1.35e+03 | (0.01, 0.49, 0.085, 1) |
| geom_v60_b120 | 0.45 | 0.131 | 0.52 | 0.345 | 0.00109 | 60.3 | (0.0027, 0.06, 0.015, 1) |

At the base 60 s window all four parameters are statistically identifiable:
median worst-direction relative standard error 7.3×10⁻⁵ (condition number 31),
with the strongest linearized correlations `|rho|(v,b) = 0.886`,
`|rho|(v,t0) = 0.829`, `|rho|(f0,t0) = 0.817` and `|rho|(f0,v) = 0.805`, and
`|rho|(f0,b) = 0.518` weakest. The worst-determined direction is dominated by
`b` (median |components|: f0 0.22, v 0.22, t0 0.36, b 1.00).

Shortening the window is not a matter of "more noise": it removes structural
information and creates exact degeneracies. At T = 5 s the median
`|rho|(v,b) = 1.000` and `|rho|(f0,t0) = 1.000` (condition number 3.7×10³;
worst-direction relative SE 0.163): the data constrain two blocks, essentially
`(v,b)` through `v²/b` and `(f0,t0)` through the level/ramp trade-off. At
T = 10 s the correlations are 0.999/0.998 (worst SE 1.5×10⁻²), at T = 20 s
0.996/0.979 (1.8×10⁻³). Prediction **P4 held**, with one correction to its
framing: the short-window pair is `(v,b)` plus `(f0,t0)`, not `(f0,v)` — the
`f0`–`v` correlation *drops* to 0.187 at T = 5 s because the frequency level
pins `f0` while the ramp trades against the event time.

The consequence is visible in the failure table: at 5 dB, T = 5 s gives 41/100
recoveries (Wilson CI 32–51%), with 59 `v`-failures and 51 `b`-failures
(median `v` 2.53%, `b` 5.07%; p90 6.15%, 12.4%) and *zero* `f0`/`t0` failures;
T = 10 s is already 100/100 (median `v` 0.21%, `b` 0.45%). For this geometry the
window threshold for the pre-declared tolerance sits between 5 and 10 s, i.e.
between 0.4 and 0.8 closest-approach time scales `b/v = 12 s`.

The exploratory distant pass (`v = 250 m/s`, `b = 30 km`; the 60 s window covers
only ±0.25 `b/v`) behaves as a degenerate case in the linearized analysis
(`|rho|(v,b) = 1.000`, worst SE 2.6×10⁻²) but only 16/100 trials actually miss
the tolerance (median `v` 1.42%, `b` 2.88%). **Prediction P8's success figure
(< 0.5) is falsified**: realized errors are bias-limited and stay inside
2%/5% more often than the linearized worst-direction SE suggests. The
degeneracy is real; the linearized SE over-predicts realized error here, which
is itself a warning that these standard errors are diagnostics, not calibrated
error bars.

### Failure conditions (acceleration, clock, window, amplitude, geometry, null)

| Condition | group | N | success | failed f0/v/t0/b (counts) | med \|Δf0\|/f0 | med \|Δv\|/v | med \|Δt0\| (s) | med \|Δb\|/b | B1 res RMS (Hz) | IF RMS (Hz) |
|---|---|---|---|---|---|---|---|---|---|---|
| window_5s | window | 100 | 41/100 (41%, 32–51%) | 0/59/0/51 | 0.192% | 2.53% | 0.0325 | 5.07% | 0.432 | 0.435 |
| window_10s | window | 100 | 100/100 (100%, 96–100%) | 0/0/0/0 | 0.0428% | 0.21% | 0.00693 | 0.454% | 0.431 | 0.433 |
| window_20s | window | 100 | 100/100 (100%, 96–100%) | 0/0/0/0 | 8.19e-03% | 0.0253% | 0.00147 | 0.0663% | 0.437 | 0.438 |
| accel_0.1 | accel | 100 | 100/100 (100%, 96–100%) | 0/0/0/0 | 0.513% | 1.19% | 0.0639 | 2.89% | 0.934 | 0.19 |
| accel_0.25 | accel | 100 | 0/100 (0%, 0–4%) | 100/100/0/100 | 1.3% | 2.9% | 0.167 | 6.98% | 2.3 | 0.189 |
| accel_0.5 | accel | 100 | 0/100 (0%, 0–4%) | 100/100/100/100 | 2.6% | 5.58% | 0.343 | 13.2% | 4.51 | 0.193 |
| clock_10ppm | clock_scale | 100 | 100/100 (100%, 96–100%) | 0/0/0/0 | 0.0153% | 8.51e-03% | 0.00293 | 0.0246% | 0.191 | 0.193 |
| clock_100ppm | clock_scale | 100 | 100/100 (100%, 96–100%) | 0/0/0/0 | 0.0243% | 8.51e-03% | 0.00473 | 0.0337% | 0.191 | 0.193 |
| clock_1000ppm | clock_scale | 100 | 100/100 (100%, 96–100%) | 0/0/0/0 | 0.114% | 8.37e-03% | 0.0227 | 0.123% | 0.192 | 0.194 |
| clock_20000ppm | clock_scale | 100 | 0/100 (0%, 0–4%) | 100/0/100/0 | 1.99% | 5.95e-03% | 0.39 | 1.95% | 0.188 | 0.189 |
| clock_50000ppm | clock_scale | 100 | 0/100 (0%, 0–4%) | 100/0/100/0 | 5.01% | 5.78e-03% | 0.954 | 4.78% | 0.187 | 0.189 |
| offset_0.3s | clock_offset | 100 | 0/100 (0%, 0–4%) | 0/0/100/0 | 0.0143% | 8.07e-03% | 0.303 | 0.0217% | 0.191 | 0.193 |
| offset_2s | clock_offset | 100 | 0/100 (0%, 0–4%) | 0/0/100/0 | 0.0148% | 9.36e-03% | 2 | 0.0268% | 0.189 | 0.191 |
| amp_geometric | amplitude | 100 | 100/100 (100%, 96–100%) | 0/0/0/0 | 0.011% | 6.33e-03% | 0.00217 | 0.018% | 0.719 | 0.719 |
| amp_mod30pct | amplitude | 100 | 100/100 (100%, 96–100%) | 0/0/0/0 | 0.0146% | 8.45e-03% | 0.00268 | 0.0218% | 0.458 | 0.46 |
| geom_v100_b300 | geometry | 100 | 100/100 (100%, 96–100%) | 0/0/0/0 | 0.0188% | 0.0409% | 0.00329 | 0.137% | 0.442 | 0.447 |
| geom_v250_b30000 | geometry | 100 | 84/100 (84%, 76–90%) | 0/16/0/2 | 0.0432% | 1.42% | 0.0723 | 2.88% | 0.432 | 0.433 |
| geom_v60_b120 | geometry | 100 | 100/100 (100%, 96–100%) | 0/0/0/0 | 0.0154% | 0.24% | 0.00327 | 0.947% | 0.411 | 0.451 |

| Condition | N | accepted (improvement ≥50% & converged) | "recovered" within pre-declared tolerance | med improvement ratio | max improvement ratio | B1 res RMS (Hz) | B0 res RMS (Hz) |
|---|---|---|---|---|---|---|---|
| null_noise_only | 100 | 0/100 (0%, 0–4%) | 0/100 (0%, 0–4%) | 0.00153 | 0.00676 | 758 | 1.26e+03 |

**Acceleration mismatch** (fit assumes `a = 0`): `a = 0.1 m/s²` still passes
100/100 but with a deterministic bias (`f0` −0.51%, `v` −1.19%, `b` −2.89%,
|Δt0| 0.064 s); `a = 0.25 m/s²` fails 100/100 (`f0` −1.30%, `v` −2.90%, `b`
−6.98%, 0.167 s); `a = 0.5 m/s²` fails 100/100 (`v` −5.58%, `b` −13.2%).
The p90 equals the median to four significant digits in every acceleration and
clock condition: the error is a deterministic model-mismatch bias, identical
for every noise seed, not a variance effect. The measured threshold is between
0.1 and 0.25 m/s², as pre-registered (**P5 held**).

**Recorder clock rate**: 10, 100 and 1000 ppm pass 100/100, with biases that
are exactly the predicted mapping (`f0` +ε, `b` −ε, |Δt0| ≈ ε·t0, `v` unchanged
at 0.006–0.009%): at 1000 ppm the measured biases are +0.114% (`f0`), −0.123%
(`b`), 22.7 ms (`t0`). 20 000 ppm fails 100/100 on `f0` (+1.989% = ε) and `t0`
(0.390 s = ε·t0) with `b` at −1.946% (inside its 5% tolerance); 50 000 ppm
fails on `f0` (+5.012%) and `t0` (0.954 s) with `b` at −4.776%, still inside 5%.
The clock-rate failure threshold is therefore ≈1% (10 000 ppm), set by the `f0`
and event-time tolerances, not by `b`. **Prediction P6 held exactly.** Recorder
clocks are typically 1–100 ppm, so a pure rate error is irrelevant at this
operating point — far below the threshold — but the mapping is structural: a
clock-rate error *is* a rescaled source.

**Constant clock offset** is an exact degeneracy, not a failure: 0.3 s and 2.0 s
offsets give 0/100 "recovery" only because `t0` then misses the 0.25 s
tolerance; `f0`, `v` and `b` are unchanged to ≤0.03%, and the measured shifts
are −0.303 s and −2.003 s, i.e. exactly −δ. An uncalibrated constant clock
offset and a different event time are indistinguishable from the acoustic data
alone (**P6/P10 held**). This must be carried forward as an abstention
condition, not hidden.

**Amplitude variation**: 1/r spreading passes 100/100 (median `f0`/`v`/`b`
errors 0.011%/0.0063%/0.018%, IF RMS 0.719 Hz vs 0.433 Hz constant-amplitude at
the same SNR); 30% sinusoidal AM passes 100/100
(0.0146%/0.0085%/0.0218%, IF RMS 0.460 Hz). **Prediction P7 held.**

**Null (noise-only)**: 0/100 accepted under the pre-declared rule (improvement
over a constant-frequency model ≥ 50% and converged), 0/100 inside the
parameter tolerance, median improvement ratio 0.0015 (maximum 0.0068), median
residual RMS 758 Hz versus 0.19–1.28 Hz on signal data at SNR ≥ −5 dB. A
stationary point was still reached on 9/100 noise tracks, and the linearized
covariance was singular on 1/100, so convergence alone is not a detection test;
the improvement ratio is. **Prediction P9 held.**

### Failure gallery (counts and representatives)

| Condition | failures / N | components over tolerance (f0/v/t0/b) | representative failing seed | representative relative errors | improvement ratio | B1 res RMS (Hz) |
|---|---|---|---|---|---|---|
| snr_-10dB | 100/100 | 99/47/57/22 | 20261112 | f0 +1.73e-02, v -4.50e-03, t0 +0.099 s, b +2.59e-02 | 0.954 | 97.1 |
| window_5s | 59/100 | 0/59/0/51 | 20267116 | f0 +7.15e-04, v +3.65e-02, t0 -0.012 s, b +7.37e-02 | 0.9999 | 0.404 |
| accel_0.25 | 100/100 | 100/100/0/100 | 20271117 | f0 -1.30e-02, v -2.90e-02, t0 +0.167 s, b -6.98e-02 | 1 | 2.3 |
| accel_0.5 | 100/100 | 100/100/100/100 | 20272163 | f0 -2.60e-02, v -5.58e-02, t0 +0.343 s, b -1.32e-01 | 0.9999 | 4.51 |
| clock_20000ppm | 100/100 | 100/0/100/0 | 20276116 | f0 +1.99e-02, v +6.02e-05, t0 -0.390 s, b -1.95e-02 | 1 | 0.187 |
| clock_50000ppm | 100/100 | 100/0/100/0 | 20277142 | f0 +5.01e-02, v -5.87e-05, t0 -0.954 s, b -4.78e-02 | 1 | 0.186 |
| offset_0.3s | 100/100 | 0/0/100/0 | 20278163 | f0 +1.44e-04, v -8.07e-05, t0 -0.303 s, b -2.17e-04 | 1 | 0.194 |
| offset_2s | 100/100 | 0/0/100/0 | 20279174 | f0 +1.42e-04, v -9.20e-05, t0 -2.003 s, b -2.68e-04 | 1 | 0.187 |
| geom_v250_b30000 | 16/100 | 0/16/0/2 | 20283198 | f0 +1.34e-03, v -2.26e-02, t0 -0.229 s, b -4.67e-02 | 0.9999 | 0.437 |

### Preregistration check

Two pre-registered predictions failed or were off, and they are reported as
such rather than reframed: **P8** predicted the `(250 m/s, 30 km)` geometry
would recover < 50% of trials; it recovered 84% (the degeneracy itself was
predicted correctly). **P3**'s `b` bias prediction (−14%) was 5.6 points below
the measured −19.6%. The remaining predictions held; **P4**'s framing was
corrected in the direction of the data (the short-window pair is `(v,b)` and
`(f0,t0)`, not `(f0,v)`). No threshold, axis, or metric was changed after the
freeze.

| # | Pre-registered prediction | Outcome |
|---|---|---|
| P1 | high-SNR error is front-end-bias limited, floor 1e-4–1e-3 relative | held: median errors flat from −5 to 20 dB (e.g. `b` 0.019–0.024%) while IF RMS falls 1.28 → 0.19 Hz |
| P2 | abrupt front-end failure; success ≥ 0.95 at −5 dB, ≤ 0.5 at −10 dB | held: 100/100 at −5 dB, 0/100 at −10 dB |
| P3 | B0 `v` bias −7.2%, `f0`/`t0` unbiased, `b` ≈ −14%; B0 success 0; B1 residual ≪ B0 | partially held: `v` −7.19%, `f0` −0.027%, `t0` 4 ms, B0 success 0/100, residual 286× — but `b` bias is −19.6% |
| P4 | `|rho|(v,b) > 0.98` short / 0.85–0.95 at 60 s; worst SE ≥ 10% at 5 s, ≤ 1e-3 at 60 s; success 0.3–0.7 at 5 s | held: 1.000 / 0.886; 16.3% / 7.3e-5; 41% (CI 32–51%) — pair framing corrected to `(v,b)`+`(f0,t0)` |
| P5 | `a = 0.1` passes with ≈1% `v`, ≈3% `b`; `a ≥ 0.25` fails; threshold 0.1–0.25 m/s² | held: 1.19%/2.89% and 100/100; 0/100 at 0.25 and 0.5 |
| P6 | offset is an exact `t0` degeneracy; `eps` maps `f0`+ε, `t0`−ε, `b`−ε, `v` unchanged; threshold ≈1% (10 000 ppm) | held exactly, including the 50 000 ppm case where `b` stays inside 5% |
| P7 | amplitude variation harmless; IF RMS ≤ 2× the constant-amplitude case | held: 100/100 both; 1.66× and 1.06× |
| P8 | `(250 m/s, 30 km)` success < 0.5; `|rho|(v,b) > 0.98`; other geometries ≈ 1 | **partially falsified**: degeneracy held (`|rho| = 1.000`, worst SE 2.6%), but success was 84%, not < 50%; other two geometries 100/100 |
| P9 | null accepted ≤ 0.05, "recovered" 0, residual ≫ signal case | held: 0/100 accepted, 0/100 recovered, 758 Hz vs ≤ 1.28 Hz |
| P10 | clock offset scored as "not recovered" through `t0` only | held: failures are `t0`-only (f0/v/t0/b = 0/0/100/0), other parameters unchanged |

## Failure gallery — diagnosis by case class

The machine-generated failure gallery is above (case class, count,
representative failing seed, and the representative error vector). This
prose section adds the diagnosis per failure class; no cherry-picked single
examples are used in place of counts.

Each row above is a case class with its count, per-parameter failure counts, and
one representative failing seed chosen as the *median*-`b`-error failure (not the
worst). The classes and their diagnoses:

1. **Low-SNR front-end peak jumps** (`snr_-10dB`, 100/100 failing). IF RMS
   133 Hz, improvement ratio still ≥ 0.84, all fits converge. The least-squares
   fit is dominated by a heavy-tailed set of frames whose spectral peak left the
   true component. Diagnosis: front-end failure, not physics. A residual-based
   validity check or a robust loss is required, because the model-fit statistic
   does not flag this.
2. **Short-window degeneracy** (`window_5s`, 59/100 failing). 59 `v`-failures
   and 51 `b`-failures, zero `f0`/`t0` failures; `|rho|(v,b) = |rho|(f0,t0) =
   1.000`. Diagnosis: structural non-identifiability at T = 0.42 `b/v`; no
   estimator can fix it, only a longer window or an external prior.
3. **Unmodelled acceleration** (`accel_0.25`, `accel_0.5`, 100/100 each).
   Deterministic biases growing with `a`; p90 = median. Diagnosis: model
   mismatch; the fix is to fit acceleration or segment the pass.
4. **Recorder clock rate** (`clock_20000ppm`, `clock_50000ppm`, 100/100 each).
   Exact `f0`/`t0`/`b` rescaling with `v` unchanged. Diagnosis: structural
   identifiability failure relative to an unknown clock; calibrate or fit the
   clock rate.
5. **Recorder clock offset** (`offset_0.3s`, `offset_2s`, 100/100 each on `t0`
   only). Not a fit failure: the event time shifts by exactly −δ. Diagnosis:
   exact degeneracy with `t0`; requires an external time reference.
6. **Distant slow traverse** (`geom_v250_b30000`, 16/100 failing; 16
   `v`-failures, 2 `b`-failures). The window covers ±0.25 `b/v`;
   `|rho|(v,b) = 1.000`. Diagnosis: marginal identifiability for this geometry
   at the 2% `v` tolerance.
7. **Null**: no recovery cases exist, and there were no false accepts — the null
   result is reported in the null table, not here.

## Limitations and what this does not prove

1. **Synthetic ≠ real.** The noise is i.i.d. white Gaussian across the full
   sampling bandwidth. Real recordings have colored, non-stationary noise,
   reverberation, multipath, ground reflection, atmospheric stratification and
   refraction, wind, Doppler broadening, multiple concurrent sources, and
   propagation delay (retarded time). None of these is modelled. E0 validates
   an estimator and a numerical solver against its own generating model; it
   cannot say how the estimator behaves on real audio.
2. **The generator and the fit share the same delay-free formula.** E0 cannot
   test model-form error of the Doppler formula itself (only the deliberately
   injected acceleration and clock mismatches). `c` is fixed and known; sound
   speed uncertainty, source-frequency drift, and propagation delay are not
   tested.
3. **One narrowband component, one receiver, one source.** No multi-component
   signals, no array/beamforming, no source-receiver geometry beyond the swept
   straight-line passes; the sweeps cover one `(v, b)` pair per condition and
   only three additional geometries.
4. **Identifiability depends on geometry and window.** The measured
   correlations and thresholds are properties of these `(v, b, T, f0, c)`
   values; they are not dimensionless invariants. The three exploratory
   geometries show the dependence but do not map it.
5. **The front end is the precision floor here.** The IF estimator is
   deliberately simple; its deterministic interpolation bias (order 0.25 Hz)
   dominates parameter errors at SNR ≥ −5 dB, and its peak-jump behavior sets
   the low-SNR failure. A better front end would move both. E0 measures
   *this* front end, not the best achievable one.
6. **The correlations/standard errors are linearized and homoscedastic.** IF
   errors from 50%-overlapping frames are correlated, so these are relative
   identifiability diagnostics, not calibrated uncertainties and not a
   covariance claim.
7. **"Recovered" is a tolerance, not a probability.** The primary success
   rate is coarse by construction; the error distributions carry the real
   information and are reported.
8. **No location, no region, no geo claim.** E0 has no location model and
   produces no region. It cannot be used to claim localization accuracy,
   coverage, calibration, or any M1 benchmark result. It is not a
   reproduction of any external aircraft-Doppler result.
9. **No claim about real recorder or motion conditions.** The clock and
   acceleration thresholds are properties of this model and these tolerances.
10. **Local minima.** Multi-start LM is deterministic but not a proof of the
    global optimum; with correlated IF noise, different starts can reach
    different local minima. E0 reports the returned solution and its
    stationarity, not a certificate of global optimality.

**What this does not prove:** that physical Doppler fitting improves
real-world inference, that these SNR thresholds correspond to real acoustic
conditions, that the recovered parameters are geographically meaningful, or
that the project passes any benchmark. E0 can only succeed or fail at
*estimator/identifiability* questions on synthetic data.

## Decision (continue / revise / abandon)

**Decision: continue** to PR-3 (real-audio / M1 feasibility), with four
revisions to the verifier design. The pre-registered continue conditions were
met: (a) B1 success was 100/100 at the 60 s window for SNR ≥ −5 dB (condition:
≥ 0.9 for SNR ≥ 0 dB); (b) B1 beat B0 on `f0`, `v`, `b` and residual RMS at
every SNR where the front end works (≥ −5 dB) by 41–286× on residual RMS and by
≈800× on `v`; (c) the failure thresholds are quantified —
acceleration between 0.1 and 0.25 m/s², clock rate ≈ 1% ≈ 10 000 ppm, window
between 5 and 10 s at this geometry — and two exact degeneracies are identified
(clock offset ↔ `t0`; clock rate ↔ rescaled source). The acceleration threshold
is **not** comfortably above real source maneuvering, so it is carried forward
as a binding limitation rather than a footnote.

Required revisions before or inside PR-3:

1. **Fit acceleration, or piecewise-constant velocity.** A zero-acceleration
   model is not viable for a source that changes speed by more than ≈0.1 m/s²
   over the observation window; this is the single most binding measured
   limitation of the constant-velocity estimator.
2. **Report identifiability and abstain.** The verifier must carry the
   linearized parameter correlations / worst-direction standard error and its
   eigen-direction, and abstain when the window-to-timescale ratio is too small
   (T < ~0.8 `b/v` collapses `(v,b)` and `(f0,t0)`).
3. **Treat the recorder clock as an unknown.** A constant offset is exactly
   degenerate with the event time; the verifier must abstain rather than report
   a "recovered" `t0` when no external time reference exists. A clock *rate*
   must be calibrated or fitted (otherwise `f0`, `t0`, `b` inherit `eps`-level
   biases).
4. **Do not use the model-fit statistic as a validity check.** At −10 dB the
   Doppler model still "fits" (improvement ≥ 0.84, all fits converged) while the
   parameters are wrong. Validity must be checked by residual structure/robust
   statistics and by the parameter uncertainties.

**Abandon is not indicated**: at the base window all four parameters were
identifiable (worst-direction relative SE 7×10⁻⁵) and the joint fit beat the
naive inversion decisively. **No benchmark, capability, or localization claim
is made or supported.** E0 measures an estimator on synthetic data only; the
decision is about whether the estimator/identifiability work should continue,
and it should.

## Preregistration record

**Frozen at:** 2026-11-04T18:25:23Z (UTC) — before the 100-trial sweep was executed.
**Frozen copy:** `/tmp/e0-synthetic-doppler/prereg-frozen.md` (ephemeral; the digests below are the durable record).
**SHA-256 of frozen copy (header + section):** `2722f5065231ceb4e0d77f706e12a4a4750c8bc17b365a6b6d1753e8af2f459e`
**SHA-256 of the preregistered section alone (11183 bytes):** `e734c863be9107559a0a767245065c03706bccef83a749fb26e2ec55b9095fa4`
**Freeze procedure:** copy the text from `## Preregistered expectation` to (not including)
`## Data (generator parameters, seeds, licenses)`, prefix the header above, write the frozen copy, hash it.
**Check the section digest from this report at any time** (it must print `e734c863…`):

```bash
python3 - <<'PYCHECK'
import hashlib, pathlib
t = pathlib.Path('docs/experiments/2026-11-04-e0-synthetic-doppler.md').read_text()
s = t[t.index('## Preregistered expectation'):t.index('## Data (generator parameters')]
print(hashlib.sha256((s.rstrip() + chr(10)).encode()).hexdigest())
PYCHECK
```
**Commit status:** PR-2 runs in a worktree where the agent may not run git commands; the Lead records the commit.
The frozen digests are what show the text preceded the run, so this is checkable even though the commit follows the run.

## Reproduction

```bash
# One command, offline, through the pinned snapshot (PR-3 / ADR 0012):
#   make e0
# It verifies the snapshot bytes, reruns the sweep, and exits non-zero if
# records_sha256 differs from the golden value below. The golden value is
# environment-specific: on macOS arm64 it is exact; on Linux x86_64 the same
# aggregates are produced but the records digest differs (float/backend
# formatting), which `make e0-ci` records as determinism=unknown rather than
# claiming a reproduction. See ADR 0012 §6.

# full sweep (the reported run): 25 conditions x 100 trials, 8 workers
PYTHONPATH=python python3 -m phaino_acoustics.experiment \
    --output-dir /tmp/e0-synthetic-doppler/run-j8 --jobs 8
# trials: 2500  conditions: 25  elapsed: 17.3 s
# records_sha256: 674213d9737f999a84aa8b57cddd9078e0bf2b2998ae02a45d0940cd98185506
# json: /tmp/e0-synthetic-doppler/run-j8/e0-results.json  sha256: a1b9e8b69cd5b45d8a218d1dfac3bd3e830d1fc0cd881ed94a080fbafd137bf3

# replay with one worker: same seeds, different worker count
PYTHONPATH=python python3 -m phaino_acoustics.experiment \
    --output-dir /tmp/e0-synthetic-doppler/run-j1 --jobs 1
# trials: 2500  conditions: 25  elapsed: 92.8 s
# records_sha256: 674213d9… (identical)

PYTHONPATH=python python3 -m pytest python/tests/test_acoustics_e0.py -q
# 13 passed in 1.08 s

PYTHONPATH=python python3 -m pytest python/tests -q
# 55 passed in 1.15 s  (42 pre-existing SDK tests + 13 E0 tests; no other test file touched)
```

**Environment.** macOS-27.0.1-arm64, Python 3.14.0, NumPy 2.4.4, 8 CPUs, no
network. SciPy is installed but not used: the fit is an in-house deterministic
Levenberg–Marquardt with an analytic Jacobian.

**Replay.** The two runs produced 2500/2500 identical trial records and
identical `records_sha256`; the two JSON files are identical after removing
`generated_at_utc`, `elapsed_s` and `config.jobs` (the only fields that are
expected to differ). The report tables were spliced from the `run-j8` artifact
by `experiment.render_tables()`; the only hand-written numbers are quoted from
those tables and from the artifact's summary fields.

**Artifacts (ephemeral, referenced by digest).**
`/tmp/e0-synthetic-doppler/run-j8/e0-results.json` (sha256 `a1b9e8b69cd5b45d8a218d1dfac3bd3e830d1fc0cd881ed94a080fbafd137bf3`) holds
every per-trial record and per-condition aggregate; `/tmp/e0-synthetic-doppler/run-j8/tables.md`
holds the rendered tables; the frozen preregistration copy is
`/tmp/e0-synthetic-doppler/prereg-frozen.md` (sha256 `2722f506…`). The report
itself is the only committed artifact.

