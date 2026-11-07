# C3 — risk–coverage on the frozen C2-C sealed artifact

**Status:** post-hoc selective-prediction analysis of existing adequacy statistics; no new model, no new data, no change to the frozen decision rule · 2026-11-05 · **Authority:** [ADR 0020](../decisions/0020-measurement-model-and-c2-repair.md) §C3 (limited scope)

## 1. Question and method

The sealed confirmation reported decision rates: B1 correctly raised supported coverage from 0.10 to 0.79 and cut false rejection from 0.68 to 0.02. C3 asks a different question: **if a user selects a subset of trials by a continuous confidence score, what is the error risk of the accepted subset and how much coverage does it buy?**

- Score (analysis-only): severity = maximum normalized adequacy statistic (Ljung–Box / its effective threshold, max|ACF| / threshold, |corr_time| / threshold, |quadratic coefficient| / threshold, |phase correlation| / threshold). Lower is better.
- Label: `evaluation_only.truth_correct` (all frozen E0 parameter tolerances) on the correct-CV mechanism (426 trials, 20 wrong).
- Curve: accept trials with severity ≤ t, sweep t; risk = wrong/accepted, coverage = accepted/all.
- Comparison at matched coverage; bootstrap over independent trials (not STFT frames), 500 replicates, fixed seed.
- This score is a **new selection mechanism**, not part of the frozen B0–B3 decision rule; it is used only for analysis.

## 2. Matched risk (correct-CV, frozen sealed artifact)

| Candidate | n | wrong | risk @25% | @50% | @75% | @90% |
|---|---:|---:|---:|---:|---:|---:|
| B0 | 426 | 20 | 0.000 | 0.000 | 0.000 | 0.000 |
| B1 | 426 | 20 | 0.056 | 0.042 | 0.044 | 0.039 |
| B2 | 426 | 20 | 0.188 | 0.094 | 0.063 | 0.052 |
| B3 | 426 | 20 | 0.000 | 0.000 | 0.000 | 0.025 |

B1 − B0 matched-risk difference (bootstrap over trials):

| Coverage | Δrisk | 95% CI |
|---:|---:|---|
| 25% | +0.059 | [+0.019, +0.103] |
| 50% | +0.044 | [+0.019, +0.073] |
| 75% | +0.044 | [+0.022, +0.069] |
| 90% | +0.040 | [+0.021, +0.060] |

All intervals are positive: **at the same retained coverage, B0's adequacy severity separates wrong from correct fits better than B1's**. This does not overturn the sealed primary endpoint (decision-rate coverage), but it is a warning about using de-chirped residual severity as a confidence score.

## 3. Interpretation

1. **Decision-rate improvement ≠ better selective reliability.** B1 accepts far more correct trials than B0, but among the trials it accepts by low severity, the fraction with wrong parameters is higher than B0's at the same coverage. The de-chirp makes wrong-parameter fits look adequate, which is consistent with the pre-seal time-block self-confirmation finding.
2. **The frozen single operating point is far from any risk–coverage optimum.** B0's frozen decision accepts 96/566 with 69% false rejection; its severity ordering could in principle reach zero observed risk at moderate coverage — but that is a post-hoc selection mechanism, not the frozen rule, and must not be reported as a property of the original method.
3. **B3's risk curve resembles B0's at low coverage** because B3 re-calibrates thresholds (its severity is normalized by its own thresholds); comparisons across candidates are about each candidate's own confidence consistency, not a common physical scale.
4. **No claim of a universal ordering.** Only 20 wrong trials, one sealed artifact, two normalized test families; block-prediction severity is not included because the artifact carries no effective threshold for it. Intervals are over trials within this grid.

## 4. What this does not change

- The sealed primary endpoint (B1 supported coverage + FRR + detection non-inferiority + claim integrity) stands as reported.
- The frozen B0–B3 decisions are unchanged; no candidate is re-selected; no new synthetic data was generated.
- The 150–400 Hz/s acceleration-detection failure and B1 time-block caveat remain.

## 5. Consequence for E1

If a residual-based confidence score is used in E1 (e.g. to abstain), it must be **separately calibrated per measurement model and per candidate**; de-chirping can compress the severity of wrong fits. The risk–coverage curve, not a single FRR, is the object to report at the claim level.

## 6. Provenance

Artifact: `/tmp/c2c-sealed-v3/c2-repair.json` sha `641a1003…`; analysis code `python/phaino_c3/`; output `/tmp/c2c-sealed-v3/eval/risk-coverage.json` / `.md`. Bootstrap seed 20261105, 500 replicates over 426 trials.
