# ADR 0017 — Gated invariants: invariance, identifiability, and statistical support

Status: Accepted
Date: 2026-11-05
Deciders: Haelio Tang (founder)

## Context

[ADR 0016](0016-identifiable-claims.md) made claims the unit of scientific conclusion and required an invariance obligation. That is necessary but not sufficient: invariance under the clock symmemtries discovered so far does not prove a claim is identifiable in the full declared model, and neither proves the claim is statistically supportable under noise and model misspecification. Treating a symbolic identity as `supported_invariant` would repeat the PR-4d error at a higher level.

The founder's ruling for PR-4e C1 requires three separate evidence layers, two separate objects (`G_clock` vs `N_physical`), a gated `supported_invariant`, an explicit locked sample with algebraic controls, and an Identifiability Boundary Report.

## Decision

1. **Three evidence layers, never substituted:**
   - **L1 — invariance under a proven symmetry group.** Symbolic derivation plus an independent numerical certificate that the *same forward observation function* is preserved, not merely a relabelled time axis.
   - **L2 — identifiability in the full declared model.** A proof that no other allowed transformation (including declared nuisances) leaves the claim ambiguous, or a counterexample showing it does.
   - **L3 — statistical support.** On a locked sample, with noise and model misspecification, the claim's validity and coverage meet pre-declared criteria.
2. **Two different objects.** `G_clock` is an exact symmetry group: identity, closure, inverses and parameter-domain validity are checked; the action is on the observation time coordinate and must preserve the forward model output. `N_physical` is a **nuisance set, not a group**: sound speed, source direction, acceleration, propagation environment. Nuisances change the observation; they belong to adequacy and robustness, never to a symmetry claim. Every claim record carries `symmetry_scope` (which group was proven) and `nuisance_assumptions` (what else is assumed).
3. **`supported_invariant` is gated, not earned by one certificate:**

   | L1 | L2 | L3 | Maximum status |
   |---|---|---|---|
   | fail | — | — | not claimable (`contradicted` if a counterexample exists, else `undetermined`) |
   | pass | unproven | — | `supported_conditional` with the unproven scope declared |
   | pass | pass | not met | `undetermined` |
   | pass | pass | met | `supported_invariant` |

   A claim may be reported as **not identifiable** on the basis of an L2 counterexample; that is a successful C1 result.
4. **Initial claim set and proof order.** `v` is the first proof target (physical-parameter invariance), `b/f0` the second (composite invariance). `t0`, `b`, `f0` start as conditional claims. No claim is presumed identifiable before its obligations are met.
5. **Locked sample `PR-4e-L1`.** New seeds and perturbation levels: acceleration {0.2, 0.4} m/s² (a **model-misspecification** family, never used to claim constant-velocity invariance), clock offset {±0.5, ±3} s, clock rate {±10 000, ±25 000} ppm, closest approach {150, 600, 5000} m as geometry **stress tests** (not equal-accuracy claims), plus a zero-perturbation control and near-identity transforms (e.g. β = ±1e-3 s, rate = ±10 ppm) to test the group axioms and certificate stability at small and large displacements. The protocol is frozen before the locked layer is opened.
6. **The certificate must be able to fail.** An observation mismatch is investigated as floating-point error, implementation difference, or an invalid theoretical symmetry — never waved through as "small error". The certificate implementation must not import the acoustic method code, and the forward model is implemented independently.
7. **Identifiability Boundary Report.** A derived report over `Verification` records (no new ontology object): per physical quantity, the proven property, the missing information, and which additional observation would break the equivalence. It is the basis for later active observation planning.
8. **Claim-level locked evaluation reports separately:** correct support and coverage under model-valid conditions; false support and correct rejection under misspecification; undetermined rate and reasons per claim; cross-environment differences for the same claim. Thresholds are fixed on a development set and never revised against `L1`.
9. **Frozen history stands.** E0, PR-4c and PR-4d artifacts, protocols and reports remain unchanged. C1 uses a new protocol version and new samples. R1-D continues under its frozen protocol and is not retroactively passed by claim-level agreement.
10. **The C1 question is the mechanism, not the five numbers.** If the gate (L1+L2+L3, scoped groups, boundary output) works on one acoustic forward model, it is a candidate for the World Ontology's general inference semantics; if it does not, the negative result is the deliverable.

## Consequences

### Positive

- Prevents promoting symmetry into knowledge: each status is backed by a specific evidence layer.
- Nuisances stay visible instead of silently strengthening a claim.
- A boundary report turns "cannot know" into a specification of the next measurement.
- The gate is model-agnostic by construction, which is the precondition for ontology-level reuse.

### Negative / costs

- Three layers mean symbolic work, an independent implementation, and a locked statistical study — significantly more than a certificate script.
- L2 proof for the full declared model may be open-ended; unresolved L2 caps claims at conditional, which will reduce reported support.
- L1 needs controls (identity, near-identity, composition) to test the group axioms; these are extra conditions in the locked grid.

## Alternatives considered

- **Claim `supported_invariant` from a single algebraic identity.** Rejected by the ruling and by the PR-4d experience.
- **Treat nuisances as part of the symmetry group.** Rejected as category error: nuisances change observations.
- **Skip L2 and rely on locked coverage.** Rejected: statistical success on a finite sample cannot prove identifiability.
- **Wait for E1 real data before formalising the gate.** Rejected: the mechanism must be validated on a synthetic model where truth is known.

## References

- [ADR 0016](0016-identifiable-claims.md), [ADR 0015](0015-model-adequacy-and-epistemic-decisions.md)
- [PR-4e plan](../experiments/pr4e-plan.md)
- [PR-4d corrections](../experiments/2026-11-05-pr4d-report-corrections.md)
- [E1 clock calibration requirement](../experiments/2026-11-05-e1-preregistration-draft.md)
