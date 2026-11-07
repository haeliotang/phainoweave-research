# C2-M2 — conditional measurement-error models and predictive acceptance

**Status:** complete on a small pre-registered development set; M3 (conditional covariance) is the only model accepted on all held-out geometries, with a weak 2-geometry check; the reference estimator is a negative result · 2026-11-05 · **Authority:** [ADR 0021](../decisions/0021-conditional-measurement-error-and-predictive-acceptance.md) · **Prior:** [C2 measurement-model report](2026-11-05-c2-measurement-model.md)

**Question.** Can a small set of runtime-observable features plus a reasonable time-correlation structure predict, on unseen geometry, how the front end distorts the physical frequency track — rather than merely fitting the discovery data?

## 1. Data and pre-registration

New development set, seed base 80,000,000: train geometries {180, 270, 400, 600, 900, 1400} m, held-out {2100, 3200} m; speeds {60, 250} m/s; SNR {5, 20} dB; N=10 trials per cell with independent noise, initial carrier-phase jitter and frame-alignment jitter (0–255 samples): 32 cells / 320 tracks. Hierarchical partial pooling across geometry; intervals resample trials/scenarios, never frames.

The acceptance contract was written and hashed **before** held-out scoring (contract digest `c9b18996…`): FRR gap ≤10 pp per geometry, Ljung–Box p90 relative gap ≤0.5, bias gap ≤0.1 Hz, variance ratio ∈[0.5, 2], ACF1 gap ≤0.2.

## 2. FFT fractional-bin offset: mechanism confirmed, but small

The hypothesis was that log-magnitude parabolic interpolation bias depends on the fractional FFT-bin position `q(t)`. Confirmed:

| q bin | mean e (Hz) | std e (Hz) |
|---|---:|---:|
| 0.0–0.1 | +0.062 | 0.320 |
| 0.2–0.3 | +0.233 | 0.294 |
| 0.3–0.4 | +0.223 | 0.274 |
| 0.5–0.6 | −0.090 | 0.237 |
| 0.7–0.8 | −0.230 | 0.294 |
| 0.9–1.0 | −0.064 | 0.317 |

Cubic fit `e ~ 1+q+q²+q³`: R² = 0.262; corr(e, q_true) = −0.387; corr(e, q̂) = −0.368. The sign flip near q≈0.5 is real. But a cubic q fit explains only 26% of frame-level variance; the rest is chirp/geometry/time-position dependent.

## 3. Feature ablation: no useful conditional-mean gain

Leave-one-geometry-out CV MSE (Hz²): F0 q-only 0.0793690; F1 q+chirp 0.0793680; F2 +curvature 0.0793686; F3 +frame position 0.0793743; F4 +freq position 0.0793702; F5 +quality 0.0793702. The declared minimum-CV rule selects F1, but the gain over F0 is ~1e-6 Hz² (0.001%) — **no meaningful generalisable conditional-mean improvement**. This is consistent with the earlier finding that the error's conditional mean is near zero while its structure is real: the mean is not where the predictive leverage is.

## 4. Predictive acceptance (held-out geometries)

| Model | Accepted geometries | Mean \|FRR gap\| | Why it fails where it fails |
|---|---:|---:|---|
| M0 white noise | 0/2 | 25.00 pp | predicted FRR 0.00 vs actual 0.25; LB p90 ~105 vs actual 44k–55k |
| M1 empirical bias+template | 1/2 | 15.16 pp | 2100 m +24.06 pp; 3200 m +6.25 pp (accepted there) |
| M2 conditional mean + white noise | 0/2 | **0.47 pp** | decision FRR matches (0.241/0.250 vs 0.250) but LB p90 ~10–12k vs actual 44–55k → distribution check fails |
| **M3 conditional covariance** (group variance × chirp scale + AR(1)) | **2/2** | **0.00 pp** | predicted = actual FRR 0.25 [0.15, 0.375] on both; bias/std/ACF1 within tolerance; LB p90 39.0k/48.9k vs actual 44.2k/54.8k |

**Verdict: accepted M3 only.** M3's structure is modest: global σ = 0.282 Hz, chirp-scale factors 0.76–1.10, group AR(1) ρ = −0.08…−0.33 (negative/alternating residual correlation). The important negative finding is M2: **matching the decision-level FRR is not acceptance** — its test-statistic distribution is wrong by a factor of four, and a decision-only check would have falsely accepted it.

Caveat: M3 is accepted on two held-out geometries with N=10 trials each (actual FRR 90% CI 0.15–0.375). This supports conditional modellability; it is **not** a sealed-grid confirmation and does not establish real-environment measurement reliability.

## 5. Reference estimator: a negative result

A phase-difference instantaneous-frequency estimator (512-sample Hann, hop 128) was evaluated as a non-competing reference:

| Metric | Current front end | Phase-difference |
|---|---:|---:|
| Error RMS (correct-CV, median) | 0.182 Hz | 0.486 Hz |
| Correct-model FRR | 40/50 (0.80) | 0/50 (0.00) |
| Adequate rate | 20% | **8%** |
| `insufficient_evidence` rate | 0% | **82%** |
| Acceleration detection | 20/20 | 20/20 |

The reference estimator's lower FRR is achieved by **abstaining more**, not by a better adequate representation: phase-jump outliers fail the residual-scale test. It is a negative result for this simple reference estimator and does not support replacing the measurement model on this evidence alone.

## 6. What this means

- The measurement error is **stable in structure but not in mean**: conditional covariance (variance scaling with chirp + short-memory AR structure) is what reproduces the downstream decision distribution; a conditional-mean model does not add predictive value at this residual-variance level.
- A decision-level FRR match is insufficient evidence of a correct error model; the per-geometry test-statistic distribution is a necessary acceptance check.
- The simple phase-difference reference estimator fails the "improve the representation" test because it trades false rejections for abstentions. A more capable representation (e.g. proper reassignment or a model-based tracker) remains untested.

## 7. Limitations

1. Two held-out geometries, N=10 trials — weak predictive evidence; contract tolerances were pre-registered but the sample is small.
2. Development data are synthetic; initial-phase and frame-alignment jitter are simulated, not measured on a real recorder.
3. The q feature uses estimated `q̂` at deployment; diagnostic `q_true` is never used in decisions (tested).
4. M3's covariance structure is deliberately low-dimensional (group variance × chirp scale + AR(1)); a richer structure was not attempted.
5. No B0–B3 repair comparison in this report; no use of the sealed `pr4e-c2c-v1` grid; no adequacy-threshold changes.

## 8. Provenance

Artifacts: `/tmp/c2m2/acceptance_contract.json` (sha `9d56eca1…`, contract digest `c9b18996…`), `development.json` (`3a861af2…`, records `05658205…`), `predictive_acceptance.json` (`fbafb0d4…`, records `bb670dfe…`), `reference_estimator.json` (`f92da892…`, records `a27191ff…`), `c2m2_summary.md` (`317ca9fb…`). Code: `python/phaino_acoustics/measurement_error_models.py`, `experiment_c2m2.py`, `measurement_model_reference.py`; tests `test_measurement_error_models.py` (8), `test_reference_estimator.py` (5). Independent predictive check: `python/phaino_c2_modelcheck` (18 tests).
