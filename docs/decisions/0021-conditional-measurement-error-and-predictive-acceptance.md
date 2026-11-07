# ADR 0021 — Conditional measurement-error modeling and predictive acceptance

Status: Accepted
Date: 2026-11-05
Deciders: Haelio Tang (founder)

## Context

C2-A showed that the extraction error has a large deterministic component (63.9% of variance) whose conditional mean is nevertheless near zero; the structure is shaped by time position/frame phase, analysis window and chirp-dependent residual correlation. C2-B showed white noise reproduces none of the high-chirp rejections, while the empirical structured-error model reproduces 68 of 100 (a 32-percentage-point decision-level gap), and full extraction reproduces 100/100. The empirical model is therefore incomplete, but requiring a complete error generator before any repair comparison would block the repair program indefinitely — the repair candidates can run on real front-end outputs without it.

Two statistical corrections are adopted: "reproduced 68/100" is a decision-level count, not an explained-variance claim; and 100/100 `insufficient_evidence` on near-noiseless truth is correct numerical handling, not 100/100 successful acceptance.

## Decision

### A. Measurement Model contract (long-lived)

A measurement-model record names and versions at least: analysis window (shape, length, hop), sampling rate, FFT length, zero-padding and boundary handling, interpolation method, peak-selection rule, numerical dependencies, error-model version, and the runtime-observable features used for conditioning. It separates two uncertainties explicitly:

- **Measurement uncertainty** — introduced when the algorithm turns the raw signal into a frequency track;
- **Physical model uncertainty** — remaining when the measured track is taken as given and the physical model explains it.

They may be correlated; naive variance addition is prohibited. The same discipline applies to future modalities (image/remote-sensing/weather): pixel classification error is not geophysical uncertainty, and a reanalysis grid's error is not event randomness.

### B. C2-M2 — conditional measurement error, four nested models

| Model | Content | Question |
|---|---|---|
| M0 | independent white noise | negative control |
| M1 | current empirical bias+template model | 68/100 baseline |
| M2 | conditional mean `μ(x_t)` from observable features | is there generalisable systematic bias? |
| M3 | conditional covariance `η(t;x_t)` (low-rank / finite-lag / parametric covariance function), not a full high-dimensional matrix | can it reproduce the downstream test-statistic distribution? |

Observable candidate features: local chirp rate, frequency curvature, frame-centre time, in-window frequency position, **fractional FFT-bin offset** `q(t) = frac(f(t)·N_FFT/f_s)`, signal quality, analysis-window parameters. Frame phase (analysis frame ↔ event alignment) and carrier phase must not be conflated. Ablation precedes any high-dimensional model: a feature is admitted only if it provides generalisable information.

`q(t)` is a priority hypothesis because log-magnitude parabolic interpolation is known to have bin-offset-dependent bias. Truth `f(t)` may be used in diagnosis only; deployment uses estimated `q(t)`.

### C. Development data and resampling

The C2-A grid (3 trials per cell) is insufficient for per-cell long-memory covariance. C2-M2 uses a new development set with independent noise realisations, initial-phase variation and frame-alignment perturbation, and hierarchical sharing of information across geometry conditions. Uncertainty intervals are resampled by **independent trial or scenario**, never by correlated frames within one track.

### D. Predictive acceptance, not retrospective replication

The acceptance object is a simulation-based/posterior-predictive model check. A model must predict held-out data behaviour, not merely fit the discovery data:

- measurement-error mean, variance and time structure;
- ACF and long-lag dependence;
- Ljung–Box statistic distribution and upper quantiles **per geometry condition**, never one global p99;
- decision-level false-rejection rate per geometry with uncertainty intervals;
- generalisation to unseen geometry, SNR and phase conditions.

Tolerances for error rate and distributional discrepancy are pre-registered before the run. A model that merely produces larger random noise is not accepted. Predefined negative result: if no conditional model predicts the held-out decisions better than M1, the claim that the representation's error is conditionally modellable in this family is refuted.

### E. Repair comparison proceeds in parallel

1. C2-M2 (mechanism) and B0–B3 (repair) are independent tracks and must not block each other.
2. B0–B3 run on real front-end outputs; the sealed grid `pr4e-c2c-v1` remains sealed until candidate methods and evaluation rules are frozen. It must not be used to select B1–B3 parameters or to pick a winner.
3. An additional **reference path** — a phase-based / time-frequency reassignment frequency estimator — is evaluated outside the initial B0–B3 competition. Its purpose is to test whether the original frequency representation has limits that repair cannot overcome; if it clearly improves both correct-model retention and misspecification detection, replacing the measurement model becomes the recommended direction.
4. Repair acceptance keeps ADR 0020 §E: paired differences with intervals, detection preservation on independent samples, no retention gains through abstention, claim integrity, cross-environment claims, failure attribution.

### F. Language discipline

Reports state decision-level counts with their gap ("reproduced 68 of 100 rejections, 32 percentage points below full extraction"), never "explained 68% of the mechanism"; and distinguish "100/100 insufficient_evidence" from "100/100 accepted". A CI-green run or a synthetic attribution does not establish measurement reliability in the real environment; E1 with independent references remains the field gate.

### G. Standing principle

> **Measurement is itself an inference process. Its errors must be modeled, tested, and propagated — not silently treated as observations of truth.**

## Consequences

### Positive

- Mechanism research and repair comparison proceed in parallel without either blocking the other.
- Acceptance is predictive and pre-registered, which prevents retrospective curve-fitting from being called validation.
- Measurement uncertainty and physical-model uncertainty become separate, auditable quantities.
- A reference estimator gives a clean test of representation limits, rather than an endless repair loop.

### Negative / costs

- C2-M2 needs new development data with phase/alignment perturbations and hierarchical modeling; more compute and bookkeeping.
- Predictive checks need pre-registered tolerances and independent resampling units.
- The sealed grid remains unused until freeze, delaying final confirmation but protecting independence.

## Alternatives considered

- **Require a complete error generator before B0–B3.** Rejected: repairs run on real outputs; blocking the program is not justified.
- **High-dimensional conditional covariance immediately.** Rejected: needs ablation and data volume; low-rank/parametric structures first.
- **Accept a global p99 match as validation.** Rejected: zero distributions differ by geometry.
- **Tune the empirical model until 100/100 is reproduced.** Rejected: reproduction count is not the acceptance object; held-out prediction is.

## References

- [C2 measurement-model report](../experiments/2026-11-05-c2-measurement-model.md)
- [C2 repair plan](../experiments/pr4e-c2-repair-plan.md)
- [ADR 0020](0020-measurement-model-and-c2-repair.md)
- [C2 diagnosis](../experiments/2026-11-05-c2-diagnosis.md)
