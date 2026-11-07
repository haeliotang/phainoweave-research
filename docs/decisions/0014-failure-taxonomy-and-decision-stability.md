# ADR 0014 — Failure taxonomy and decision stability

Status: Accepted
Date: 2026-11-05
Deciders: Haelio Tang (founder)

## Context

The three-environment validation ([report](../experiments/2026-11-05-cross-platform-e0.md) §9) separated numeric equivalence from decision equivalence: R1-N held on all three platform pairs, R1-D failed on the two pairs that involve x86_64, and the entire difference was one near-threshold convergence decision on trial 57 (arm64 `grad_norm` ~1e-12, x86_64 `1.056e-6` against a `1e-6` threshold). The evidence supports "architecture-grouped" as an observation, **not** as a proven cause: OS, BLAS, compiler flags, and optimizer execution path interact and were not isolated.

That result exposes a gap larger than reproducibility: the project has no vocabulary for *why* an inference failed. A fit can be numerically unstable while the physics is fine; it can converge perfectly inside a flat parameter valley that the observation cannot resolve; and it can produce a confident scientific conclusion whose discrete decision sits exactly on a numerical boundary.

## Decision

1. **Three failure mechanisms are named and never substituted for one another:**
   - **Physical unidentifiability** — the observations cannot distinguish the states, regardless of algorithm quality.
   - **Numerical instability** — the optimizer/arithmetic produces different execution states for near-identical problems (this ADR's trigger).
   - **Decision instability** — a small numerical difference changes a downstream scientific conclusion (accept/reject, success/failure, published rate).
   A report must say which one it is reporting; "the model failed" is not an acceptable summary.
2. **Any discrete decision that can change a scientific conclusion has explicit numerical-stability semantics**: a named deciding statistic, a declared margin derived from measured error and the decision's scale, an `indeterminate` state, retention of the raw binary value, and a rule that a material change in a reported output fails the decision-equivalence target even when the individual decision was masked ([ADR 0013](0013-reproducibility-contract-v2.md)).
3. **Four statuses are recorded separately**, never collapsed:
   - `optimization_converged` — the numerical criterion is met;
   - `parameter_identifiable` — the pre-declared *operational* gate passes (normalized standard errors, condition number, local sensitivity); this is not a proof of structural identifiability and is described as an operational gate in every report;
   - `model_adequate` — the declared residual/adequacy rule passes;
   - `decision_status` — `accepted | rejected | indeterminate`, derived from the three above by declared precedence.
   
   *Amended by [ADR 0015](0015-model-adequacy-and-epistemic-decisions.md):* the single `decision_status` is split into `optimization_status`, `identifiability_status`, `model_adequacy_status` and `epistemic_decision`; the raw cause statuses are preserved and never merged. The upper semantics ("no supported physical conclusion") may coincide across distinct execution paths, but the underlying statuses remain visible, and R1-D equivalence continues to be judged by the frozen protocol.
4. **Convergence must be dimensionless and stability-confirmed.** The criterion combines: scale-normalized parameters and residuals (primary); consecutive-iteration stability over at least three iterations (secondary — two consecutive iterations do not distinguish convergence from stalling); an explicit iteration/f-evaluation budget; and `indeterminate` when the budget is exhausted without confirmation. A raw (`‖∇L‖ < const`) threshold is not acceptable as the sole criterion. Parameter scales are declared physically (for E0: 500 Hz, 250 m/s, 20 s, 3000 m) and are part of the rule, not a tuning knob.
4a. **The operative gradient statistic is curvature-normalized.** The literal elementwise dimensionless gradient is curvature-dependent and was measured to span seven orders of magnitude across fits the frozen rule called converged. The hardened rule therefore uses the **maximum predicted dimensionless parameter step in the local Gauss–Newton metric**, `max_i |g_i| / (s_i (JᵀJ)_ii)`, with the same declared scales and residual normalization. In the full E0 artifact the maximum over converged fits is 8.98e-10 and the minimum over unconfirmed-stall fits is 1.12e-8; the threshold `1e-8` sits in that measured band, and the classification is invariant for thresholds in `[1e-9, 1e-7]`. This is a declared change of statistic forced by measurement, not a threshold chosen to make one trial agree.

5. **Diagnose before modifying.** Before any threshold or rule change, the failing case is diagnosed with a fixed-parameter cross-evaluation: the same parameter vector is evaluated on every environment for objective value and (normalized) gradient, with termination reason, iteration counts, last-iteration trajectory, Jacobian method and finite-difference step, and build/dependency/floating-point configuration recorded. If objective or gradient differ materially **at the same parameters**, the derivative/numerical implementation is the first suspect — not the convergence threshold.
6. **E0 is frozen.** The original E0 code path, artifacts, digest and preregistered success criteria are immutable. A hardened rule is a **new version** (`E0-hardened`) with its own artifacts, report and digest, shown alongside the original; no retroactive editing of the original report or its "success" definition.
7. **Hardened-rule acceptance is dual and requires both:**
   - **Decision equivalence**: the same formal classification (`accepted | rejected | indeterminate`) on the same test set across the three environments;
   - **Decision utility** on data not used to tune the rule: pre-declared bounds on false-accept rate, retained-valid fraction, and abstention rate.
   A validator that returns `indeterminate` everywhere is perfectly equivalent and scientifically worthless; it fails the utility half.
8. **Cross-environment confounds are removed before conclusions.** Interpreter patch versions, numpy/SciPy versions, BLAS/LAPACK implementation, CPU architecture, thread settings and image version are pinned and recorded; a difference attributable to a version is not evidence about architecture.

## Consequences

### Positive

- Reports can distinguish "cannot know", "algorithm is unstable", and "decision is on a boundary", which is the project's core research claim applied to its own tooling.
- The hardened rule is evaluated on reproducibility **and** usefulness, preventing the degenerate all-abstain solution.
- Frozen E0 records keep the historical result honest while allowing the method to improve.

### Negative / costs

- More status surface: four per trial, plus margin/indeterminate machinery in every downstream consumer.
- The utility half requires an independent labelled set and pre-declared error/retention bounds, which does not exist yet for E1.
- Convergence research can become a rabbit hole; the ADR limits it to cases that change a scientific conclusion.
- Cross-environment validation costs CI minutes and inventory maintenance.

## Alternatives considered

- **Tune the threshold until R1-D passes.** Rejected by the founder's ruling and by this ADR: it manufactures certainty at exactly the boundary the project must expose.
- **Treat the flip as nondeterminism and average it away.** Rejected: it changed a reported rate.
- **Make everything indeterminate.** Rejected by the utility half.
- **Replace the optimizer.** Deferred: first diagnose whether the difference is derivative, path or termination (decision 5); a rewrite before diagnosis would destroy the evidence.

## References

- [Three-environment validation](../experiments/2026-11-05-cross-platform-e0.md) §9
- [ADR 0013](0013-reproducibility-contract-v2.md) — R1-N/R1-D, field classes, indeterminate
- [ADR 0010](0010-m1-identifiability-program.md) — identifiability as a first-class property
- [PR-4c plan](../experiments/pr4c-plan.md)
