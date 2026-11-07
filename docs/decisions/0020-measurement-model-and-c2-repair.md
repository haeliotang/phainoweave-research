# ADR 0020 — Measurement model, evidence integrity, and the C2 repair protocol

Status: Accepted
Date: 2026-11-05
Deciders: Haelio Tang (founder)

## Context

C2 attribution showed that with the true generated frequency, correct-model high-chirp geometries are accepted (0/100 false rejections) while the existing front end rejects them (100/100 at 150 m, 99/100 at 600 m); acceleration is rejected in both paths; and the parametric null distribution of the Ljung–Box statistic is 47× the asymptotic reference for the real pipeline. The physical forward model was not what failed — the **measurement representation** was.

This requires four standing changes: a formal Measurement Model concept, a repair protocol that evaluates candidates independently, an evidence-integrity distinction between semantic and artifact digests, and acceptance criteria that protect misspecification detection while improving false rejections.

## Decision

### A. Measurement Model is a first-class architecture concept

1. The inference chain is:
   `Observation → Measurement Model → Physical Model → Identifiable Claims`.
2. A **Measurement Model** names and versions: the front end (sampling, windowing, time–frequency representation, frequency-track extraction), its error model, calibration and validity conditions. It is not a preprocessing detail.
3. Every claim record references the measurement-model id/version that produced its observation representation. A claim whose evidence chain has no measurement-model reference is incomplete.
4. Adequacy and identifiability are properties of the pair (measurement model, physical model): the same physical claim may be adequate under a faithful measurement representation and inadequate under a biased one.
5. The ontology addition (a normative section for the measurement-model record) is a follow-up deliverable; the concept and the reference requirement apply immediately.

### B. C2-A: extraction-error generative model

1. Define the extraction error `e(t) = f̂(t) − f_true(t)` for synthetic diagnosis and analyse its dependence on: frequency rate `ḟ(t)`, frequency acceleration `f̈(t)`, SNR, analysis-window length, and time position.
2. Report the systematic component `E[e(t) | ḟ(t)]` and the error covariance as functions of chirp rate, not only mean-square error.
3. A systematic, chirp-dependent error is a **measurement-model structural error**; it must inform the adequacy null design and may not be absorbed by widening thresholds.
4. Truth frequency is permitted only in synthetic diagnosis; it never enters a runtime decision path.

### C. C2-B: noise-matched control paths

Compare, under comparable noise conditions: ideal generated frequency; generated frequency with known independent noise; generated frequency with the empirical front-end error structure; full waveform extraction. The comparison must separate frequency bias, error correlation, and residual-scale failure. Near-noiseless degeneracies may return `insufficient_evidence`; adding noise to force a test result is prohibited.

### D. C2-C: repair comparison on a new frozen validation set

1. The 1840 attribution trials are discovery data and must not be reused as an independent confirmation set.
2. A new locked grid covers unseen geometry on a **continuum** (not only 150/600/5000 m endpoints), unseen chirp-rate combinations, SNR levels and acceleration levels; independent seeds; protocol frozen before opening.
3. Candidates are evaluated **independently** — B0 original, B1 de-chirping, B2 residual pre-whitening, B3 geometry-conditioned calibration — on the **same observations** (paired). No combination of B1–B3 is attempted before the independent results are known.
4. B3 may condition only on runtime-observable quantities (estimated chirp rate, signal quality, fit uncertainty); true `b`, true acceleration or synthetic scenario labels may never select a rule.

### E. Acceptance: protect both capabilities

| Metric | Requirement |
|---|---|
| False rejection rate (correct constant-velocity model) | decreases versus B0 on independent geometry levels |
| Misspecification detection (independent acceleration samples) | no degradation beyond a pre-registered bound |
| Valid retention | not improved by indiscriminate abstention |
| Claim integrity | C1's L1/L2/L3 gating not bypassed; no new `supported_invariant` from looser adequacy |
| Cross-platform | claim-level decisions validated on three environments |
| Failure attribution | every rejection/abstention keeps its statistical or physical reason |

Improvements are measured by paired differences with uncertainty intervals, not by comparing two percentages. 100/100 detection is a finite-sample observation, not a claim that the detection probability is exactly 100%. If no route improves false rejection without losing detection, the negative result is that the current frequency representation or residual framework is insufficient and a new observation representation is required — not another threshold adjustment.

### F. Evidence integrity: semantic digest, artifact digest, verification record

Mathematical evidence keeps three distinct references:

| Field | Identifies | Does not prove |
|---|---|---|
| **Semantic Claim Digest** | canonical proposition, assumptions, domain, generators, normalised proof statuses | that the derivation is correct |
| **Proof Artifact Digest** | the proof script/certificate/derivation artifact bytes | that the semantic claim matches the artifact's actual content |
| **Independent Verification Record** | verifier version, environment, checks executed, result, evidence refs | mathematical truth beyond the checks performed |

A semantic digest matching does not prove correctness; an independent numerical certificate can find counterexamples but finite sampling cannot replace a proof. Claims and protocols record all three references; a digest alone is never cited as proof.

### G. Repair-artifact contract (required fields)

The independent evaluator requires, and the method side must emit:

- `trial_id` / `pair_id` explicit (pairing is never inferred from condition+seed);
- `measurement_model_id` (ADR 0020 A) per trial/claim evidence chain;
- `environment_id` in every artifact;
- `gate_policy_digest` and the allowed claim-status set used for claim-integrity checks;
- a pre-registered `detection_loss_bound` (the repair cannot lose more acceleration detection than this bound);
- declared `params`/estimate schema per candidate, and a per-claim truth map (`estimate_within_tolerance` keys must be explicit);
- B3 runtime-observability metadata (which runtime-observable inputs selected its calibration) with truth/label fields forbidden;
- the three mathematical-evidence references where applicable (semantic claim digest, proof artifact digest, independent verification record).

### H. Sequencing

C3 (risk–coverage) waits for C2's new validation results; any continuous operating score added to the old rule is labelled a new selection mechanism, never retroactively attributed to the historical rule. C4 keeps optimizer, adequacy, identifiability and claim statuses separate; the frozen R1-D is not reinterpreted. E1 preparation continues unchanged, including the authorization gate, independent time reference and affine clock calibration.

## Consequences

### Positive

- The measurement process becomes an auditable part of the evidence chain rather than an invisible assumption.
- Repair candidates are compared under a single paired protocol with pre-declared acceptance, preventing a threshold fix from being mistaken for a scientific improvement.
- Mathematical evidence cannot be cited by digest alone; the artifact and verification record are separate obligations.
- A negative C2 result has a defined meaning (representation insufficiency), not an endless tuning loop.

### Negative / costs

- A new measurement-model record and references in every claim; ontology/spec work.
- C2-A/B/C add substantial diagnostics before any repair can be claimed.
- Three digests plus a verification record increase bookkeeping.
- Paired evaluation on a new frozen grid costs another experiment cycle.

## Alternatives considered

- **Treat C2 as a front-end bug fix only.** Rejected: the systematic error model and null-distribution dependence must be characterised to know whether a fix generalises.
- **Jump directly to B1/B2/B3 and pick the best number.** Rejected: independent evaluation is required, and a combination could hide which capability was lost.
- **Cite the semantic proof digest as proof correctness.** Rejected by decision F.
- **Keep the measurement model implicit in code.** Rejected: it is exactly the component that produced the scientific error.

## References

- [C2 diagnosis](../experiments/2026-11-05-c2-diagnosis.md)
- [C1 report](../experiments/2026-11-05-c1-identifiability.md)
- [ADR 0019](0019-authoritative-frozen-payload-and-c2.md)
- [PR-4e plan](../experiments/pr4e-plan.md)
