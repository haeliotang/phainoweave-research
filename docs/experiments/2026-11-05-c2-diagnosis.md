# C2 diagnosis — attributing the high-chirp false rejections

**Status:** attribution complete; no repair route selected or implemented; thresholds unchanged · 2026-11-05 · **Authority:** [ADR 0019](../decisions/0019-authoritative-frozen-payload-and-c2.md) · **Related:** [PR-4d validation](2026-11-05-pr4d-adequacy-validation.md) (74/240 geometry false rejections), [C1 report](2026-11-05-c1-identifiability.md)

**Question.** PR-4d rejected 74/240 correct-model trials in unseen geometry. Is that a front-end frequency-estimation error, a model-fit error, or an invalid residual-test null distribution? The ruling required attribution before any repair.

## 1. Diagnostic matrix

Design: `true generated frequency ↔ existing front-end extraction`, crossed with three situations — correct constant-velocity model (nominal and high-chirp geometry), unmodelled acceleration, and noise-only null. 12 cells, N=100 signal realizations per source (fixed seed base 50,000,000), 600 noise-only null realizations, 1840 trials total. Truth instantaneous frequency has a declared 0.05 Hz white floor; it is used for diagnosis only and never enters a runtime decision path (static test).

| Cell (correct-model families) | Extracted frequency | True generated frequency |
|---|---|---|
| cv nominal control | 0/100 false rejections | 0/100 |
| geometry 150 m @ 250 m/s | **100/100** discrepancy (LB 100, time-structure 100) | **0/100** |
| geometry 600 m @ 250 m/s | **99/100** discrepancy (+1 indeterminate) | **0/100** |
| geometry 5000 m @ 250 m/s | 0/100 (LB p99 6711 < frozen 7671) | 0/100 |
| unmodelled acceleration 0.2/0.4 | 100/100 discrepancy | **100/100 discrepancy** |

The same observation, if its frequency were known exactly, is accepted. With the real front end it is rejected at 150/600 m. That separates the causes: the forward model and the fit are not what fails at high chirp; the **front end** is.

## 2. Null distribution: the asymptotic Ljung–Box null does not hold

Parametric simulation through the whole generate → extract → fit → residual pipeline:

| Quantity | p50 | p99 | Ratio to asymptotic p99 |
|---|---:|---:|---:|
| asymptotic χ²(df=85) Monte Carlo | 84.4 | 118.2 | 1.0 |
| model-valid null (correct CV, extracted) | 5158.7 | **5576.7** | **47.2×** |
| noise-only null (600 realizations) | 89.4 | 128.2 | 1.08× |

The standard Ljung–Box null is invalid for this pipeline: front-end structural correlation inflates the statistic by two orders of magnitude. The **frozen threshold (7671.6) was calibrated to that inflated null**, and its tail above threshold is 0/100 — so the calibration is doing its job. High-chirp geometry crosses the threshold because front-end bias adds to the statistic, not because the threshold is wrong. Block-RMSE p99 is 1.063 against the frozen 1.406; the block test does not fire.

## 3. Attribution verdicts

| Family | Verdict | Basis |
|---|---|---|
| correct-model, nominal geometry | `no_false_rejection` | 0/100 both paths |
| unmodelled acceleration | `model_misspecification` | rejection persists with **true** frequency (100/100), and LB p99 ≈ 1.1e5 |
| high-chirp geometry | **`front_end_structural_error`** | 66% extracted false-rejection rate vs 0% with true frequency |
| noise-only null | `test_null_distribution_mismatch` | pipeline null p99 47× asymptotic; frozen calibration tail 0/100 |

A numerical limitation is reported separately: on noiseless truth (σ_f ≈ 1e-13) the residual-scale test degenerates and returns `insufficient_evidence` 20/20; this is not model error.

## 4. What this means for the repair step

Per ADR 0019 §D, no repair route is selected by this experiment. The findings constrain the next step:

- The primary target is **the front end or its error model**, not the fit and not a looser residual test. Any repair that widens the Ljung–Box threshold would accept high-chirp bias as if it were noise — the exact failure the calibration caught.
- De-chirping, pre-whitening and geometry-conditioned calibration remain competing candidates and must be compared on the same observations, with the acceleration detection rate checked on **new** mismatch samples (not only the old 240).
- Geometry conditioning may use only runtime-observable quantities (estimated chirp rate, signal quality, fit uncertainty); using the true closest approach would be truth leakage.
- C2 repair must not change C1's formal results: a model-adequacy improvement cannot resolve the sound-speed structural non-identifiability and cannot promote a claim.
- Acceptance remains: reduce correct-model false rejections on independent geometry levels, preserve acceleration detection on new samples, keep claim gating unchanged or stricter, validate on three environments, and show a paired same-observation comparison without indiscriminate abstention.

## 5. Cross-check against PR-4d and limitations

- PR-4d measured 74/240 geometry false rejections; this matrix uses different geometry levels/seeds and reports per-cell counts, so the two numbers are not interchangeable. The *mechanism* is consistent: high chirp is where the extracted track departs from the physical frequency.
- N=100 per cell resolves a 66% vs 0% contrast but not sub-1% tail rates; the null-distribution conclusion rests on the p99 ratio, not a precise tail estimate.
- Truth-IF uses a declared 0.05 Hz floor; noiseless variants are numerically degenerate and reported as such.
- Attribution is one model, one front end, synthetic data. It does not establish how a real recorder's front end behaves; E1's independent calibration remains the field test.

## 6. Provenance

Artifacts: `/tmp/c2/diagnosis.json` (sha `0269d393…`, records `2161a7fd…`), `/tmp/c2/diagnosis.md` (sha `6aab9ab8…`). Code: `python/phaino_acoustics/diagnose_c2.py`, tests `python/tests/test_diagnose_c2.py` (11 tests). Thresholds asserted equal to `adequacy_protocol` (`thresholds_changed: false`); `repair_routes_implemented: false`.
