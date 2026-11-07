# E1-C Detection Consensus v2 — ternary fusion

**Status:** semantic correction of the v1 consensus rule; original audit results and v1 report preserved · 2026-11-05 · **Terminology erratum (2026-11-05):** the value previously called "false detection rate" (12/24) is the **False Positive Rate (FPR)**. The **False Discovery Proportion (FDP)** on this audit set is 12/12 = 1.0. Numbers and original state are unchanged; only the names are corrected. · **Authority:** [ADR 0025](../decisions/0025-e1-scope-and-scale-audit.md) amendment · **Data:** [estimator audit](2026-11-05-e1-estimator-audit.md)

## 1. The correction

v1 fused `{discrepancy, not-discrepancy}` and classified **two abstentions as `not_detected`**. That violates the project's own principle: absence of evidence is not evidence of absence. Each estimator must be mapped to three states:

| State | Meaning |
|---|---|
| **D** | evidence of model mismatch (`discrepancy`) |
| **A** | passes the predefined adequacy tests (`adequate`) |
| **U** | insufficient evidence / numerical undetermined / estimator failure |

Fusion is ternary:

| Baseline | Independent | Consensus |
|---|---|---|
| D | D | `detected` |
| A | A | `not_detected` — **only** "no mismatch found under these tests", not proof of correctness |
| D | A | `undetermined / estimator_disagreement` |
| D | U | `undetermined / incomplete_confirmation` |
| A | U | `undetermined / insufficient_evidence` |
| U | U | `undetermined / both_inconclusive` |

`U + U` is never `not_detected`. The rule is symmetric in the two estimators.

## 2. Reclassification of the existing audit (no raw estimates changed)

12 acceleration trials:

| Outcome | Count |
|---|---:|
| consensus `detected` | **0/12** |
| consensus `undetermined` | **12/12** |
| consensus `not_detected` | **0/12** |
| false supported | 0/12 |

Reasons: `incomplete_confirmation` 6 (D+U), `both_inconclusive` 6 (U+U). No trial fell into D+A in this set.

Correct-CV (24 trials): 9 A/A, 12 D/D (both estimators flag a discrepancy on a correct-model trial — the known false-rejection behaviour), 3 U/U; consensus claim support is 3 trials per claim.

**v1's 0/12 detected and 0 false-supported are unchanged; only the 6+6 undetermined classification is corrected.**

## 3. Two distinct capability gaps

1. **Detection power.** 0/12 consensus detections. If the 12 trials were independent and identically distributed, zero successes give a one-sided 95% Clopper–Pearson upper bound of about **22.1%**; the trials are grouped by geometry, so this is not a strict population guarantee. Per-geometry reporting is retained.
2. **Positive support.** Only 9/24 correct-CV trials are A/A and only 3 trials per claim receive consensus support. A system that never wrongly supports but rarely supports correct conclusions is safe but not scientifically useful; E1 must measure both sides.

## 3a. The more important result: consistent false positives

Putting the 24 correct-CV and 12 acceleration trials into one matrix:

| True model state | consensus D+D | consensus A+A | undetermined |
|---|---:|---:|---:|
| correct constant velocity (24) | **12** | 9 | 3 |
| acceleration mismatch (12) | **0** | 0 | 12 |

Derived rates for the current estimator pair on this audit set:

| Metric | Value |
|---|---:|
| sensitivity / TPR `P(detected \| true mismatch)` | **0/12 = 0.0** |
| false positive rate (FPR) `P(detected \| adequate model)` | **12/24 = 0.5** |
| false discovery proportion (FDP) `P(adequate \| detected)` on this set | **12/12 = 1.0** |
| deterministic no-detection on correct model | 9/24 = 0.375 |
| abstention on mismatch | 12/12 = 1.0 |
| abstention on correct model | 3/24 = 0.125 |

FPR and FDP answer different questions: 50% of adequate-model trials are flagged; 100% of the deterministic detections in this audit set are false. The latter is a sample FDP, not a population FDR (the audit set was selected, and real prevalence may differ).

These are small, selected synthetic audit numbers, not population probabilities. But they support a stronger statement than "safe but limited": **on this set the estimator consensus does not distinguish a correct constant-velocity model from an acceleration mismatch.** Twelve correct-model trials are *consistently* flagged as discrepancies by both estimators. If `detected` were read as a physical mismatch result, that would itself be a scientific error.

This is why `detected` is now scoped as **Estimator Consensus Discrepancy**, not physically supported model discrepancy. The code returns:

```
evidence_scope: "estimator_consensus"
physically_supported: false
```

Upgrading to a physical claim requires a validated measurement-error model, independent prediction or external evidence — not merely a second optimiser that shares the same observation, measurement representation and physical assumptions.

## 3b. A general question the project should keep

> When several algorithms share the same measurement model and physical assumptions, how much independent evidence does their agreement add about physical truth?

The 12/24 and 0/12 results say: not much can be assumed. Agreement across implementations is evidence about numerical robustness, not about the world.

## 4. What estimator agreement does and does not show

`fit_hardened` and the scipy `least_squares` implementation use different optimisers but share the **same observations, forward model, measurement representation and nuisance assumptions**. Their agreement tests robustness to numerical implementation, not robustness to a wrong physical model, a biased measurement model, or unknown environment. Two estimators can agree while both fitting the same wrong model.

Parameter agreement is also conditional on identifiability. Where a clock equivalence or another degeneracy exists, raw parameter vectors can differ while the physical claim is invariant. E1 therefore keeps two comparisons:

- raw parameters in a declared normalisation (implementation agreement);
- **claim values under the declared transformation group, with intervals** (the appropriate basis for claim support).

## 4a. E1-C pre-registration endpoints

E1-C now has **two primary endpoints, reported with abstention**:

- **Sensitivity / TPR** `P(consensus detected | true model mismatch)`;
- **False positive rate (FPR)** `P(consensus detected | adequate physical model)`.

The false discovery proportion `P(adequate | detected)` is reported as a derived diagnostic when there are deterministic detections; it is not the primary denominator.

A detector that never detects, or that detects everything, satisfies only one side. Both must be reported per mechanism and per geometry, with intervals; undetermined is reported separately. The audited pair's current values (0/12 sensitivity, 12/24 FPR, 12/12 FDP) are an audit-set observation, not an E1 result. No new estimator, threshold or fusion rule will be tuned against these 36 trials.

## 5. E1-C isolation

A near-zero consensus detection rate does **not** fail E1 as a whole. E1-A (measurement transfer) and E1-B (out-of-sample de-chirp prediction) have separate hypotheses and outcomes. Each must be pre-registered, reported and decided independently; no aggregate "E1 passed/failed" claim.

## 6. Provenance

Rule code `python/phaino_acoustics/detection_consensus.py` (v2), tests `test_detection_consensus.py` (14). Audit artifact `/tmp/e1est/estimator-audit.json` sha `90bca559…`. v1 report [2026-11-05-e1-detection-consensus-rule.md](2026-11-05-e1-detection-consensus-rule.md) is retained as the historical protocol; v2 supersedes its classification only.
