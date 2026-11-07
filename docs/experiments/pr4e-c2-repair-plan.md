# PR-4e C2 repair plan — extraction-error model, noise-matched paths, and B0–B3 comparison

**Status:** C2-C sealed run complete under revision v3; B1 primary endpoint passes with caveats (high-chirp acceleration detection 0/30 for all candidates) · 2026-11-05 · **Authority:** [ADR 0020](../decisions/0020-measurement-model-and-c2-repair.md) · **Prior:** [C2 diagnosis](2026-11-05-c2-diagnosis.md)

**Order.** Measurement-model characterisation first (C2-A), noise-matched controls second (C2-B), new frozen validation grid third (C2-C), then the four candidate comparison (B0–B3). No candidate is selected or combined before the independent comparison.

## Result so far (2026-11-05)

C2-A: no simple `E[e|ḟ]` (R² 0.0075); deterministic share 0.639, time-position/frame-phase and window dependent, chirp-dependent residual correlation. C2-B: white noise reproduces 0 rejections; empirical structured error reproduces 68% overall but 10–100% per geometry (held-out 0.60) → **error model insufficient**. Frozen grid `pr4e-c2c-v1` (`cb8d869d…`, 59 conditions / 566 trials) defined. Repair runs are deferred until the error model is extended. See [measurement-model report](2026-11-05-c2-measurement-model.md).

## C2-M2 result (2026-11-05)

q-bin bias confirmed (R² 0.262, corr −0.387; ±0.23 Hz sign flip near q≈0.5) but no feature set gives a meaningful conditional-mean gain (all within ~1e-6 Hz²). Predictive acceptance on held-out geometries: M0 0/2, M1 1/2, M2 0/2 (FRR matches but LB distribution wrong by 4×), **M3 2/2** (predicted=actual 0.25, distribution within tolerance), with only two geometries. The phase-difference reference estimator lowers FRR only by abstaining (82% insufficient vs 0%), a negative result. See [C2-M2 report](2026-11-05-c2m2-conditional-error.md).

## C2-M2 — conditional measurement-error modeling (ADR 0021)

Four nested models M0 white / M1 empirical / M2 conditional mean / M3 conditional covariance, conditioned on runtime-observable features (local chirp, curvature, frame-centre time, in-window frequency position, fractional FFT-bin offset `q(t)`, signal quality, window parameters). Ablation before high-dimensional modeling; frame phase vs carrier phase separated. New development data with independent noise, initial-phase and frame-alignment perturbations; hierarchical sharing across geometry; resampling unit = trial/scenario, never frames.

Acceptance is predictive: error mean/variance/time structure, ACF, per-geometry Ljung–Box distribution, decision-level false-rejection prediction, generalisation to unseen geometry/SNR/phase, with pre-registered tolerances. Running in parallel with B0–B3; the sealed `pr4e-c2c-v1` grid is not used for selection. A phase-based/reassignment estimator is evaluated as a non-competing reference path. See [ADR 0021](../decisions/0021-conditional-measurement-error-and-predictive-acceptance.md).

## C2-A — extraction-error generative model

For synthetic tracks, `e(t) = f̂(t) − f_true(t)`; report not only RMS but:

- systematic component `E[e(t) | ḟ(t)]` across chirp-rate bins (150–5000 m geometry, 60–250 m/s);
- dependence on `f̈(t)`, SNR, analysis-window length and time position;
- error covariance vs chirp rate (correlation time, heteroscedasticity);
- whether the front-end error is a deterministic function of the physical frequency history (structural error) or an independent noise process.

Deliverable: measurement-model error model artifact + report. Truth is diagnostic-only.

## C2-B — noise-matched control paths

Four observation sources, same physical scenario and seed where possible:

1. ideal generated frequency;
2. generated frequency + known independent noise;
3. generated frequency + empirical front-end error structure (from C2-A);
4. full waveform → front end extraction.

Purpose: separate frequency bias from error correlation from residual-scale failure. Near-noiseless cases may be `insufficient_evidence`; no artificial noise to force significance.

## C2-C — new frozen validation grid

- Unseen seeds (new base), unseen geometry on a **continuum** (e.g. 120–8000 m with logarithmic spacing, not only 150/600/5000 m), unseen chirp-rate combinations, SNR levels and acceleration levels.
- Protocol and grid frozen before opening; the C2 diagnosis trials (1840) are not reused.
- Paired design: every trial is processed by B0, B1, B2, B3 on the same observation; candidate runs are independent artifacts.

## Candidates (evaluated independently, no combinations yet)

| Id | Change | Core question |
|---|---|---|
| B0 | original front end + adequacy | paired baseline |
| B1 | de-chirp: compensate the candidate model's predicted frequency change before analysis | reduces extraction bias without removing true acceleration? |
| B2 | residual pre-whitening: model and compensate normal time-correlated error | improves false alarms while preserving real mismatch? |
| B3 | geometry-conditioned calibration from observable chirp rate / signal quality / fit uncertainty | generalises to unseen geometry scales? |

## C2-C sealed confirmation (ADR 0023)

Conditions before opening `pr4e-c2c-v1`: (1) B1 self-confirmation diagnostics on development data (wrong-model de-chirp, time-block holdout, parameter stability vs truth); (2) outcome taxonomy separated (supported coverage; detected / undetermined / false-supported); (3) B3 per-chirp-bin power, including CV-vs-acceleration at the same chirp, with unexercised SNR branch declared unverified; (4) the whole dependency graph frozen and committed (candidate code/params, calibration samples, model versions, gate policy, evaluator, tolerances, classification rules, primary endpoint, interval method, detection-loss bound, undecided policy, failure rules).

The sealed run takes the committed manifest as input, runs once per frozen candidate set, reports the pre-declared primary endpoint plus every mechanism family, and publishes negative/undecided results. An implementation error keeps the first record and requires a new revision protocol; no re-run for a better result.

## Metrics and acceptance (pre-registered)

| Metric | Requirement |
|---|---|
| False rejection rate, correct CV model | decrease vs B0 on independent geometry continuum |
| Misspecification detection, independent acceleration samples | no degradation beyond pre-registered bound (paired) |
| Valid retention | not improved by indiscriminate abstention |
| Claim integrity | L1/L2/L3 gating unchanged; no new `supported_invariant` |
| Cross-platform | three-environment claim-level consistency reported separately |
| Failure attribution | every reject/abstain carries its statistical/physical reason |

Paired differences with uncertainty intervals; 100/100 is a finite-sample observation, not a detection probability. Negative result allowed and pre-defined: if no candidate improves FRR without detection loss, the representation/residual framework is insufficient and a new observation representation is required.

## Runtime constraints

B3 uses only runtime-observable quantities (estimated chirp rate, signal quality, fit uncertainty); true `b`, true acceleration and synthetic labels are forbidden in rule selection. C1 formal conclusions are unchanged by any adequacy improvement.

## Deliverables

1. **Error-mechanism report** (C2-A/C2-B): systematic error vs chirp, correlation structure, null-distribution implication.
2. **Repair comparison report** (B0–B3): paired FRR/detection/retention, intervals, per-candidate gains and losses.
3. **Independent locked confirmation** on C2-C, three-environment claim-level checks, negative results preserved.
