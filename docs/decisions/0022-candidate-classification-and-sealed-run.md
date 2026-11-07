# ADR 0022 — Candidate classification and the sealed-run rule

Status: Accepted
Date: 2026-11-05
Deciders: Haelio Tang (founder)

## Context

The B0–B3 development comparison produced a sharp but easily misread result: B1 (de-chirp) and B3 (geometry-conditioned calibration) both reduce correct-model false rejections to 0/82 while acceleration detection stays 27/36, and B2 (pre-whitening) reduces it to 27/82. But B1 repairs the measurement representation, B2 changes a test's dependence model, and B3 changes thresholds/zero distributions. Treating them as interchangeable "repairs" would repeat the error ADR 0020 warned about: widening a threshold is not improving a measurement.

The development run also changed after seeing its first artifact (decision mapping and B3 threshold coverage), which means the development result is exploratory, not frozen. The sealed grid `pr4e-c2c-v1` has not been opened and must not be used to select parameters.

## Decision

1. **Candidates are classified by what they change:**
   - **B1 — measurement-representation repair** (de-chirp compensation of the candidate model's predicted frequency history). Only B1 may be described as improving the *measurement model*. Report that it refits the same estimator on the repaired track, so parameters necessarily differ from B0.
   - **B2 — test-dependence correction** (residual pre-whitening). It changes the residual test's dependence model, not the measurement. Its calibration must come from independent correct-model samples and must preserve real mismatch signals.
   - **B3 — conditional calibration** (thresholds/zero distributions conditioned on runtime-observable features). It is an inference-calibration change, **not** a measurement repair; it must be labelled as such and may not be presented as evidence that the front end was fixed.
   - The phase-based/reassignment reference estimator is outside the competition; a replacement recommendation requires better **adequate** retention and detection, not merely fewer rejections via abstention.
2. **Decision vocabulary is separated.** In repair artifacts, `decision` means the adequacy decision (`adequate→accept`, `discrepancy→reject`, `insufficient_evidence/indeterminate→undetermined`). Physical claim statuses and the C1 epistemic gate are stored separately (`claim_statuses`, `epistemic_decision`); no evaluator or report may equate adequacy acceptance with a supported physical claim. Claim integrity is checked independently and may not be improved by relaxing adequacy.
3. **Undecided is not detection loss.** In the development grid, 9/36 acceleration trials are `undetermined` because the frozen distribution test returns `insufficient_evidence`, not because a candidate lost detection. Sealed analysis must report undecided separately, and the pre-registered detection-loss bound must state how undecided trials are handled.
4. **Sealed run rule.** Before opening `pr4e-c2c-v1`: candidate code, calibration samples, evaluation rules, tolerances and the detection-loss bound are frozen and hashed; the grid is run once per frozen candidate set; no parameter is changed afterwards. The development grid is for implementation and sanity only. Any post-development implementation change is documented (the decision mapping and B3 coverage were changed once) and the final frozen code hash is recorded.
5. **No candidate is selected from the development run.** B1's 0/82 is a hypothesis to test on unseen geometry; B3's 0/82 is explained by threshold conditioning and must survive the same independent checks; B2's partial improvement is reported as partial. The reference estimator's abstention trade-off is recorded as a negative result.
6. **Negative results remain.** If no candidate improves correct-model rejection without detection loss and without abstention gaming on the sealed grid, the conclusion is representation insufficiency, not a justification for another threshold.

## Consequences

### Positive

- The difference between fixing a measurement and relaxing a test stays visible in every report.
- The sealed grid keeps its independence; development changes cannot leak into confirmation.
- Adequacy decisions, physical claims and undecided outcomes are reported separately.

### Negative / costs

- B3 may still be operationally attractive; labelling it as calibration rather than repair will make it look less like progress, which is the point.
- Freezing code and tolerances before the sealed run adds a hash/provenance step.
- The B1 refit means accepted parameters are not directly comparable to B0; reports must pair parameter differences with claim-status differences.

## Alternatives considered

- **Treat all four as repairs and pick the lowest FRR.** Rejected: B3's zero FRR is a threshold effect.
- **Run the sealed grid now without freezing.** Rejected: the development run already showed implementation changes after seeing results.
- **Use the epistemic decision as the primary repair metric.** Rejected: under clock equivalence it is `undetermined` almost everywhere; it would make measurement-adequacy differences invisible. It is reported separately.

## References

- [C2-M2 report](../experiments/2026-11-05-c2m2-conditional-error.md)
- [C2 repair development report](../experiments/2026-11-05-c2-repair-dev.md)
- [ADR 0020](0020-measurement-model-and-c2-repair.md), [ADR 0021](0021-conditional-measurement-error-and-predictive-acceptance.md)
