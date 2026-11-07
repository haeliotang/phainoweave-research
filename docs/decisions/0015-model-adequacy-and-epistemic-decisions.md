# ADR 0015 — Model adequacy layer and epistemic decisions

Status: Accepted
Date: 2026-11-05
Deciders: Haelio Tang (founder)

## Context

The hardened E0 rule fixed the numerical instability and then exposed a larger failure: 2000 trials are accepted, but only 1400 are within the frozen parameter tolerances. The 600 false accepts decompose into two different problems, both measurable from the synthetic truth:

| Mechanism | Trials | What happens |
|---|---|---|
| **Model misspecification** | 400 | unmodelled acceleration (200) and clock rate (200) — a constant-velocity, nominal-clock model fits the observation well enough (high variance explained) with wrong parameters |
| **Observational equivalence** | 200 | a constant clock offset is exactly degenerate with the event time `t0`; the fit recovers `t0` perfectly *under its own model* and is wrong against physical time — no residual test can resolve this using the same recording |

Accepting "the fit explains the variance" as "the parameters are right" conflates three propositions: the optimizer found a stable solution; the data support that parameter solution; the solution represents the physical process. High explained variance is not model adequacy (the same point is made in standard engineering-statistics practice, e.g. NIST/SEMATECH's caution that a high R² does not validate a model).

## Decision

1. **A new, independent `Model Adequacy & Discrepancy` layer is added.** It does **not** overwrite the existing `model_adequate` judgment; it produces its own status, evidence and diagnostics. The old field remains available for comparison.
2. **Status separation (amends ADR 0014 §3).** Four fields are recorded separately and never merged or erased:
   - `optimization_status` — did the optimizer satisfy the numerical convergence criterion?
   - `identifiability_status` — does the observation constrain the parameters (operational gate + degeneracy analysis)?
   - `model_adequacy_status` — does the model explain the observation's structure, not only its variance?
   - `epistemic_decision ∈ {supported, rejected, undetermined}` — is there a basis for a physical conclusion?
   Distinct execution paths may share the *upper* semantics "no supported physical conclusion", but their raw statuses stay visible. R1-D equivalence continues to be judged by the frozen protocol, whatever the new semantics say.
3. **The adequacy layer implements five tests, each with declared limits:**
   1. standardized residual scale and distribution (depends on the noise-scale estimate being trustworthy);
   2. residual autocorrelation / Ljung–Box (statistic with calibrated lag order and degrees of freedom; **no fixed `p < 0.05` rule** — the null distribution is calibrated on tuning data);
   3. residual structure versus time / phase (detects omitted dynamics such as acceleration; confounded by sampling and model estimation);
   4. time-block held-out prediction (tests whether the fit predicts blocks not used in estimation; common bias can affect both sides);
   5. parameter sensitivity and profile-likelihood degeneracy (detects weak constraints and near-equivalent solutions; cannot manufacture missing information).
4. **The clock is modelled explicitly**: `t_observed = α · t_physical + β`. When `β` (or `α`) is not separately identifiable from `t0` (`f0`, geometry), the system returns **"not separately identifiable"** with the degeneracy direction, rather than reporting a recovered event time. A constant offset with no external time reference is the canonical case: residuals are excellent and `t0` is still not physical.
5. **Epistemic decisions are a first-class output.** `undetermined` is a legitimate scientific result, not a failure of the tool. A physical conclusion requires: optimization stable, identifiable under the operational gate, model adequate, and the conclusion expressed within the truth-uncertainty semantics of the evidence. Acceptance without adequacy is a defect.
6. **Three data layers, frozen in meaning:**
   - **Original E0** — historical record; may be used to *understand* failures, never as independent validation;
   - **Tuning** — calibration of diagnostics, thresholds, lag orders; every choice logged;
   - **Locked Validation** — independent seeds and **unseen perturbation levels / parameter ranges**, stratified by mechanism (acceleration, clock rate, clock offset, window, geometry, noise, null). Thresholds are frozen before it is opened; no adaptation afterwards.
7. **Utility is judged by risk–coverage, not by a single threshold.** The comparison reports false-accept rate, valid-retention and abstention **at matched retention**, old rule versus new, per mechanism, with intervals. No target such as "30% → 5%" is set in advance: if a class is unidentifiable from the available observations, the correct result is the boundary and the independent measurement required to cross it.
8. **Implementation and evaluation are separated.** The evaluation harness is written independently of the adequacy method, consumes artifacts only, and never imports method internals. Both are reviewed as separate units.

## Measured correction and claim tiers (2026-11-05)

The locked validation corrected the failure decomposition and forced a claim distinction:

1. **Clock rate is also an exact equivalence.** A rate error `α` is absorbed by `f0 → f0(1+ε)`, `t0 → t0/(1+ε)`, `b → b/(1+ε)` with `v` unchanged (verified at 1e-12), so it is observationally identical to a clean recording of a rescaled source. Of the 600 E0 false accepts, **240 are detectable model misspecification (acceleration) and 360 are observational equivalence (200 offset + 160 rate)**.
2. **A physical claim and a nominal-clock-conditional claim are different claim types.** Under the strict rule a physical conclusion requires an absolute external time reference; without one, E0 retains **zero** supported trials (0 false accepts). A conditionally-supported claim retains 83.4% with 23.1% false accepts, all of them the equivalence trials.
3. **Adopted hierarchy:** (i) physical claims require strict support; (ii) conditional claims must be labelled `nominal-clock-conditional` in every output and may never be reported as physical; (iii) clock-invariant content (e.g. speed, relative geometry) is the candidate for a future protocol version that supports a physical claim without an absolute time reference. A report that presents a conditional claim as physical is a defect.

## Consequences

### Positive

- The project can distinguish "the model is wrong" from "the observation cannot decide", which is its central research question applied to its own inference.
- The 600 false accepts become a diagnosed, stratified phenomenon rather than a single failure rate.
- Adequacy tests have declared limits, so a white-noise residual cannot be presented as proof of correct parameters.

### Negative / costs

- More machinery per trial: five tests, calibrated null distributions, degeneracy analysis; runtime and false-positive risk increase.
- Calibration of Ljung–Box lag/df and the adequacy thresholds is itself a modelling exercise that can overfit; the locked layer exists to detect that.
- Three data layers require new synthetic condition grids unseen in E0, not just a random trial split.
- `undetermined` will increase substantially; reports must carry both retention and abstention.

## Alternatives considered

- **Replace variance-explained with a residual whiteness test.** Rejected as too narrow: it catches structured residual cases but cannot address observational equivalence (200 of 600), and it would present "white residual" as proof of correctness.
- **Keep one `decision_status`.** Rejected: it merges three different failures and makes the cross-platform classification differences uninterpretable.
- **Tune adequacy thresholds on the existing 600.** Rejected: those cases are already studied; the locked layer must contain unseen perturbation levels.
- **Drop the worst conditions and report the rest.** Rejected: it hides the scientifically interesting failure classes.

## References

- [PR-4c hardened validation](../experiments/2026-11-05-pr4c-hardened-validation.md) — the 600 false accepts and the trial-57 diagnosis
- [ADR 0014](0014-failure-taxonomy-and-decision-stability.md) — failure taxonomy and status separation (amended here)
- [ADR 0013](0013-reproducibility-contract-v2.md) — R1-N/R1-D and indeterminate
- [PR-4d plan](../experiments/pr4d-plan.md)
