# ADR 0023 — Three operations, B1 self-confirmation diagnostics, and the sealed confirmation protocol

Status: Accepted
Date: 2026-11-05
Deciders: Haelio Tang (founder)

## Context

The B0–B3 development run gives B1 and B3 identical-looking outcomes (0/82 false rejections, 27/36 acceleration detection) through different causal paths: B1 changes the observation representation; B3 changes decision thresholds. B1 additionally uses a physics model's prediction inside the measurement pipeline and then re-fits the same model, which creates a self-confirmation risk: the model can help make its own residuals look adequate. The sealed 566-trial grid hasn't been opened, and the development result is exploratory.

## Decision

### A. Three operations must remain distinct

| Operation | What it changes | Example | Cannot be presented as |
|---|---|---|---|
| **Measurement Correction** | the observation representation, making it more faithful to the signal | B1 de-chirp | uncertainty modelling or decision calibration |
| **Uncertainty Modelling** | the description of measurement error and its correlation structure | M3 conditional covariance | a measurement fix or a decision rule |
| **Decision Calibration** | the scientific decision rule given a known error model | B3 conditional thresholds | evidence that the measurement was improved |

They may complement each other; they may never impersonate each other. Every report labels which operation it evaluates. This applies to future modalities (satellite imagery, atmosphere, terrain, ecoacoustics) as well.

### B. B1 self-confirmation diagnostics (development stage, before sealing)

1. **Wrong-model de-chirp**: deliberately use a biased prediction (wrong speed/geometry/acceleration) and check whether B1 still produces implausibly good residuals/adequacy. If a wrong model also yields a beautiful fit, B1's improvement is partly self-confirmation.
2. **Time-block holdout**: estimate de-chirp parameters on a subset of the time window and test prediction/adequacy on blocks not used; the improvement must persist out-of-block.
3. **Parameter stability and truth**: compare B1 vs B0 physical parameters across windows, noise perturbations and time blocks against independent truth. If B1 trades parameter correctness for adequacy, it is not a measurement repair.
4. Residual improvement is never sufficient: the acceptance object is **correct physical information retained**, not prettier residuals.

### C. Outcome taxonomy (report separately, never pooled away)

- correct-model: `supported coverage = correct & validly supported / correct-model trials`; false rejection and abstention counted separately.
- misspecification: `discrepancy_detected`, `undetermined`, `false_supported` reported separately; safe abstention is a capability but is **not** counted as successful detection.
- null/noise-only: must not be promoted to a valid physical event.
- All rates carry intervals; zero observed events are reported as counts with upper bounds, not as a zero probability.
- B3 must report test power per observable chirp bin, including CV-vs-acceleration at the same chirp; an SNR branch that was not exercised in development is declared unverified.

### D. Freeze the whole dependency graph

Before opening `pr4e-c2c-v1`, an authoritative manifest freezes and hashes: candidate implementations (B0–B3) and their parameters; calibration samples/seeds; measurement-model and error-model versions; adequacy/gate policy; evaluator and comparison code; tolerances, classification rules; primary endpoint and interval method; detection-loss bound and undecided-trial policy; failure-handling rules distinguishing execution failure from scientific negative. The sealed run takes this committed manifest as input.

### E. Sealed run discipline

1. Run once per frozen candidate set; no re-run for a better result, no selecting an output, no changing tests after seeing results.
2. If an implementation error is found, keep the first record, declare it invalid for confirmation, and create a new revision protocol; never silently replace the run.
3. Primary endpoint is pre-declared; mechanism-family results are always reported alongside it. No aggregate average may hide a family failure.
4. Cross-environment execution is reported as a separate reproducibility dimension, not as a second confirmation of the same endpoint.
5. Results are published in full, including negative and undecided outcomes.

### F. Program direction

C2-C is the last large synthetic measurement-model expansion. After it, C3 (risk–coverage) and C4 (status boundaries) stay tightly scoped, and engineering/research effort shifts to E1's controlled real experiment: authorization, calibrated audio, independent motion measurement, clock anchors, and a pre-frozen protocol. Synthetic generators cannot substitute for independent real observation.

## Consequences

### Positive

- The self-confirmation loop becomes a measurable risk rather than an unstated concern.
- Measurement correction, uncertainty modelling and decision calibration cannot be conflated in reports.
- The sealed run has confirmation status because its whole dependency graph was frozen first.
- The program has an explicit exit from synthetic iteration.

### Negative / costs

- B1 diagnostics add development work and may demote B1 if self-confirmation is found.
- Freezing the dependency graph is extra bookkeeping and constrains late changes.
- A single sealed run means a failed run cannot be "retried"; a revision protocol is required.

## Alternatives considered

- **Start the sealed run immediately.** Rejected: B1 self-confirmation is untested.
- **Treat B3's 0/82 as equivalent to B1's.** Rejected by the operation taxonomy.
- **Keep iterating synthetic front ends.** Rejected: diminishing scientific return; E1 is the gate.

## References

- [C2 repair development report](../experiments/2026-11-05-c2-repair-dev.md)
- [C2-M2 report](../experiments/2026-11-05-c2m2-conditional-error.md)
- [ADR 0022](0022-candidate-classification-and-sealed-run.md), [ADR 0021](0021-conditional-measurement-error-and-predictive-acceptance.md)
