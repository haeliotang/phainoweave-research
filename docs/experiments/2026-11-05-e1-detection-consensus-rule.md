# E1 detection rule — cross-estimator consensus

**Status:** decision rule specified and applied to the estimator audit; it is a decision rule, not a measurement-model conclusion · 2026-11-05 · **Authority:** [ADR 0025](../decisions/0025-e1-scope-and-scale-audit.md) amendment · **Data:** audit set from [estimator audit](2026-11-05-e1-estimator-audit.md)

## 1. The rule

A **model-mismatch detection** (acceleration, clock drift, reverberation) requires **both** estimators to report `discrepancy`:

| Baseline | Independent | Decision |
|---|---|---|
| discrepancy | discrepancy | `detected` |
| neither discrepancy | neither | `not_detected` |
| exactly one discrepancy | — | **`undetermined` with reason `estimator_disagreement`** — never counted as detection |

A **claim support** additionally requires both estimators to give the same claim status **and** to agree on parameters within the pre-declared audit bounds (f0/v/b 0.5%, t0 0.05 s). If they agree on status but not on parameters, the claim is withheld as `undetermined` with reason `parameter_disagreement`; if they disagree on status, `undetermined` with `estimator_disagreement`.

This rule is deliberately conservative. It does not change the frozen B0–B3 or C1 decisions; it governs E1 reporting.

## 2. Application to the estimator audit

12 acceleration trials, both estimators agree parameters fail tolerance:

| Outcome | Count |
|---|---:|
| `detected` (both discrepancy) | **0/12** |
| `undetermined` (one-sided) | **6/12** |
| `not_detected` (both abstain) | 6/12 |
| false supported | 0/12 |

The baseline alone "detected" 6/12 (the one-sided cases); the consensus rule converts all of them to `undetermined`. On this audit set the current estimator pair therefore has **no consensus detection capability** for acceleration. That is a real capability result, not a reason to relax the rule.

Correct-CV under the same rule: 9/24 trials accepted by both (both adequate); 15/24 undetermined because at least one estimator reported discrepancy or indeterminate; claim support consensus is 3 trials per claim. No claim flips were introduced (consistent with the estimator audit).

## 3. What this means for E1

1. E1-C cannot claim mismatch detection from a single estimator. Single-estimator detection is reported only as a secondary, estimator-specific observation.
2. The primary E1-C detection metric is the consensus decision above; one-sided detections are reported as `undetermined` with their reason.
3. E1 must **pre-register an expected detection capability / minimum acceptable consensus power**. If consensus detection is near zero on the pilot, the honest result is a capability failure (and possibly `inconclusive`), not a lower threshold.
4. If consensus detection is required and the estimator pair cannot provide it, the remedy is a better estimator/model or a different observable — not a redefinition of detection.
5. Claims that depend on parameter agreement are withheld when the two estimators differ beyond the audit bounds, even if both fit "adequately".

## 4. Rule classification

This is a **Decision Calibration** rule (per the three-operation distinction): it changes how a scientific decision is made from estimator outputs. It is not a Measurement Correction and not an Uncertainty Model; it must not be described as improving the measurement.

## 5. Limitations

- Applied to a small synthetic audit set (36 trials); the 0/12 consensus detection is specific to that set and estimator pair.
- The rule's parameter-agreement bounds are the pre-declared audit bounds, not an E1 measurement budget.
- No real-data detection claim is made; E1 remains gated.
- The rule is conservative by construction; its cost is visible detection power.

## 6. Provenance

Audit artifact `/tmp/e1est/estimator-audit.json` sha256 `90bca559…`; code `python/phaino_acoustics/detection_consensus.py`, tests `test_detection_consensus.py` (6). Applied via `apply_audit` with bounds f0/v/b 0.005, t0 0.05 s.
