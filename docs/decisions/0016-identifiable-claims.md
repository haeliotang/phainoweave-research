# ADR 0016 — Identifiable claims and claim-level semantics

Status: Accepted
Date: 2026-11-05
Deciders: Haelio Tang (founder)

## Context

PR-4c/PR-4d established three results that the current output contract cannot express:

1. Some failures are detectable model error (240 acceleration cases rejected).
2. Some failures are **observational equivalence** under an admitted parameter transformation: a constant clock offset `β` is exactly degenerate with event time `t0`, and a clock rate `k = 1+ε` reparameterises `(f0, b, t0)` with `v` unchanged (verified at 1e-12).
3. The strict "physical claim" policy that follows from (2) has **zero valid retention** on E0: a whole-recording `supported/undetermined` verdict throws away knowledge a recording *does* support (e.g. relative speed) because other quantities are not identifiable.

A single `epistemic_decision` per inference run therefore answers the wrong question. The scientific question is: **given these observations and this model, which propositions about the world are supported?**

## Decision

1. **Claims, not runs, are the unit of scientific conclusion.** Each claim is a typed proposition `φ(θ)` over the model parameters (and derived quantities), evaluated against the observations. A run may carry many claims with different statuses; the run itself has no single "supported" verdict.
2. **The allowed transformation group is declared per claim.** `G` contains the transformations under which the observation is invariant and which the evidence cannot exclude (for E0: `β`-shift, rate rescaling `k = 1+ε`, and any other declared nuisance such as sound-speed uncertainty). A claim is *invariant* when `φ(θ) = φ(Tθ)` for every `T ∈ G` that maps the observed data to itself within the declared tolerance. `G` is part of the claim record; it cannot be implicit.
3. **Invariance must be proven, not asserted.** Two obligations:
   - a **symbolic/algebraic derivation** that `F(θ) = F(Tθ)` for each generator of `G`;
   - an **independent numerical certificate**: random parameter points, apply `T`, compare forward observations and `φ` within a declared tolerance.
   Candidate invariants from PR-4d are `v` (under rate and offset) and the ratio `b/f0` (under rate); `f0`, `b`, `t0` are not invariant under the declared group. **Invariance does not automatically imply a useful physical interpretation**: `b/f0` is algebraically invariant but its scientific meaning is open; it may be a claim only after interpretation and validation.
4. **Four claim statuses:**

   | Status | Meaning |
   |---|---|
   | `supported_invariant` | Holds for every state in the observation equivalence class, and the invariance obligation is satisfied |
   | `supported_conditional` | Holds only under explicitly recorded assumptions (e.g. nominal clock `α=1, β=0`); never presented as unconditional |
   | `undetermined` | The observations neither support nor contradict the claim at the declared tolerance |
   | `contradicted` | Valid evidence within the declared model and error bounds refutes the claim |

   A claim record carries: `claim_id`, typed proposition, allowed transformation group `G`, conditioning assumptions, model/version, evidence and verification references, uncertainty, and source snapshots.
5. **A physical claim requires `supported_invariant`.** A conditional claim is a different output type and must carry its conditioning assumptions in the same record; presenting a conditional claim as physical is a defect.
6. **Strict-policy zero accepted claims means an undefined false-accept ratio.** When `accepted = 0`, the false-accept *rate* is undefined; reports state "zero false-accept count; zero accepted; ratio undefined", never "0% false-accept rate". Zero accepted is not evidence of reliability.
7. **Conditional claims are evaluated under two metrics, separately:**
   - **absolute-truth error**: error rate of conditional-supported claims against physical truth (PR-4d: 200/867 ≈ 23.1%);
   - **conditional-truth error**: error rate restricted to the population where the conditioning assumption actually holds (PR-4d: 0/507 for clock-nominal trials).
   The gap between them is the cost of the assumption; neither number alone describes the method.
8. **Every report carries a sample-flow table.** Per mechanism family: `n`, accepted under each rule, correct/incorrect against truth, rejected, undetermined, conditional/absolute status. Family sizes are never presented as if they were error counts (PR-4d: family sizes 240/200/160, locked old false accepts 440).
9. **Frozen artifacts stay frozen.** Original E0, PR-4c and PR-4d artifacts, digests, protocols and reports are historical records. PR-4e introduces a new protocol version and independent validation samples. Claim-level agreement never retroactively passes the frozen R1-D; R1-D continues to be judged by its own frozen protocol and is reported separately.
10. **Compatibility with the ontology.** Claims are a layer over `Hypothesis` and `Verification`: a claim references hypothesis evidence and verification results; no tenth object is required. The claim record is a projection over existing records plus the transformation group and conditioning fields. A normative addition to [`world-ontology.md`](../specs/world-ontology.md) is a PR-4e deliverable.

## Consequences

### Positive

- A recording can support relative-motion claims while declaring absolute time unidentifiable — the exact outcome the strict whole-run policy lost.
- Equivalence is handled as mathematics (a transformation group with proof obligations), not as a detector failure or a threshold.
- Conditional output becomes honest: its assumption, its absolute error and its conditional error are all visible.
- Multi-modal evidence now has a precise job: break a specific equivalence relation, not "raise confidence".

### Negative / costs

- Every claim needs a declared group, a proof obligation and an independent numerical certificate; the ontology gains a claim record and a spec section.
- Invariance proofs are per-model-version work; a model change can invalidate a claim's group.
- Claim-level evaluation needs its own benchmark definition (claim sets, coverage, validity), not a single run metric.
- The temptation to promote conditional claims is now a documented defect rather than a phrasing choice.

## Alternatives considered

- **Keep one run-level decision.** Rejected: it cannot express partial knowledge and produces the zero-retention outcome.
- **Promote `v` and `b/f0` to invariants immediately.** Rejected: invariance under the current group does not survive unmodelled uncertainties (sound speed, direction); symbolic plus numerical proof first, interpretation second.
- **Treat equivalence as a detector failure and widen the model.** Rejected: no amount of fitting removes an exact reparameterisation; only additional observations (independent time reference) do.
- **Report strict zero-accepted as perfect reliability.** Rejected by decision 6.

## References

- [PR-4d validation report](../experiments/2026-11-05-pr4d-adequacy-validation.md) and its [corrections](../experiments/2026-11-05-pr4d-report-corrections.md)
- [ADR 0015](0015-model-adequacy-and-epistemic-decisions.md) — adequacy layer and status separation
- [ADR 0013](0013-reproducibility-contract-v2.md) — R1-N/R1-D
- [PR-4e plan](../experiments/pr4e-plan.md)
- [Research program](../research/research-program.md) — updated core principle
