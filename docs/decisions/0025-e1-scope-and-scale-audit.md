# ADR 0025 — E1 scope: measurement transfer, de-chirp out-of-sample, mismatch recognition, and the scale audit

Status: Accepted
Date: 2026-11-05
Deciders: Haelio Tang (founder)

## Context

C2-C confirmed B1 as a conditional measurement correction on synthetic data (supported coverage 0.786 vs 0.103, FRR 0.020 vs 0.685, detection not inferior, claim integrity intact) while exposing three unresolved issues: B1's time-block self-confirmation, a 150–400 Hz/s acceleration-detection family failure (0/30 for every candidate), and no real-environment evidence. The safe controlled-pass chirp-rate audit shows the C2 high-chirp band is not reachable by an indoor low-speed pilot.

## Decision

1. **E1 targets the exposed mechanisms, not just Doppler fitting:**
   - **E1-A Measurement transfer:** does real-audio extraction reproduce the FFT-bin/window/time-dependent error structure found in C2?
   - **E1-B De-chirp out-of-sample validity (primary):** fit motion/de-chirp parameters on designated blocks, freeze the prediction, and evaluate held-out blocks without re-estimating from them. A re-fit may be reported only as a separate condition.
   - **E1-C Mismatch recognition:** under real acceleration, clock drift and reverberation, are detection, rejection and abstention reliable, reported separately with the taxonomy from ADR 0023?
2. **Coverage is pre-declared from the scale audit** (`|ḟ| ≈ f0 v²/(c b)`). A safe indoor pilot covers roughly 0.1–70 Hz/s; the 150–400 Hz/s band must be declared **uncovered** unless a separately authorized setup is designed. Same chirp rate does not imply equivalent trajectory, noise or propagation.
3. **Clock calibration remains a formal requirement:** affine `t_obs = α t_phys + β` with two independent anchors spaced in time, or rate calibration plus an absolute anchor; no pseudo-independence from a shared device clock; record calibration uncertainty and which equivalence relations the anchors break.
4. **Truth is interval-valued.** Motion truth, clock calibration, sound speed and temperature carry uncertainty; the truth-uncertainty budget is reported and propagated into claim evaluation.
5. **Pilot vs confirmation:** 18–30 controlled passes are a pilot; locked E1 size and effect-size assumptions are set only after the pilot, and pilot results are never presented as confirmation.
6. **Program direction:** the synthetic front-end expansion cycle is closed. C3 (risk–coverage) stays limited to the existing evaluation object; C4 stays semantic/audit-only and does not reinterpret frozen R1-D. E1 is the next major research milestone, gated by venue authorization, legal review, equipment calibration and consent.
7. **The E1 success criterion includes honest ignorance:** when real data does not match the generator, the system must state what it does not know (undetermined claims, declared coverage gaps) rather than force a confident parameter.

## Amendment — E1-0 gate and leakage-proof E1-B (2026-11-05)

1. **E1-0 Instrument Feasibility Gate** must be completed before collection: frequency-resolution check at the expected few-Hz Doppler shift (bench test with a calibrated source and at least two frame lengths), clock calibration uncertainty for α/β, independent reference-truth measurement, safe geometry coverage, and measured SNR/distortion. The gate's evidence is recorded; unanswered checks keep the collection ban. A 512-point STFT is likely inadequate for 1–2 m/s shifts and must not be assumed adequate.
2. **E1-B leakage controls**: block boundaries pre-registered before analysis; guard band of at least two STFT frames with straddling frames discarded; de-chirp prediction, model selection, quality gating, normalization and error-model calibration estimated on fit blocks or separate calibration events only; results reported as three analyses (full-event fit, true out-of-sample, re-fit-on-held-out as a separate condition). The primary object is held-out prediction, not residual aesthetics.

## Amendment — cross-estimator detection rule (2026-11-05)

Because the estimator audit found acceleration detection to be estimator-sensitive (6/12 adequacy flips at b=1400 m), E1-C uses a **consensus decision rule**, not a single-estimator detection:

- each estimator is mapped to **D** (discrepancy), **A** (adequate) or **U** (insufficient/indeterminate/failure);
- **D+D** → `detected`; **A+A** → `not_detected` ("no mismatch found", not proof of correctness);
- every mixed pair and **U+U** → `undetermined` with a reason (`estimator_disagreement`, `incomplete_confirmation`, `insufficient_evidence`, `both_inconclusive`); **U+U is never `not_detected`**;
- claim support additionally requires identical claim status and parameter agreement in a declared normalisation; raw parameter equality alone is insufficient under an observation equivalence class;
- estimator agreement tests numerical implementation robustness, not physical-model, measurement-model or environment robustness; a D+D consensus is scoped as `estimator_consensus` with `physically_supported = false`; E1-C reports sensitivity/TPR and false positive rate (FPR) together with abstention, with false discovery proportion as a derived diagnostic;
- E1-A/B/C have independent hypotheses and outcomes; a near-zero E1-C detection rate does not fail E1-A/B.

This is a decision-calibration rule, not a measurement correction. E1 must pre-register expected consensus detection power; near-zero detection is a capability result, not grounds to relax the rule. See [Detection Consensus v2](../experiments/2026-11-05-e1-detection-consensus-v2.md).

## Consequences

- E1 is designed around the three failure mechanisms rather than a single localization demo.
- The high-chirp synthetic band is explicitly out of E1 scope unless a new safe setup is authorized.
- The program accepts lower synthetic complexity in exchange for real-world falsifiability.

## References

- [E1 scale audit](../experiments/E1-scale-audit.md)
- [E1 preregistration draft](../experiments/2026-11-05-e1-preregistration-draft.md)
- [C2-C sealed confirmation](../experiments/2026-11-05-c2-sealed-confirmation.md)
- [ADR 0023](0023-three-operations-and-sealed-protocol.md)
