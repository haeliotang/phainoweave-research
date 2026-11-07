# ADR 0019 — Authoritative frozen payload, evidence layers, and the C2 attribution rule

Status: Accepted
Date: 2026-11-05
Deciders: Haelio Tang (founder)

## Context

Three findings from the C1 audit need to become standing rules:

1. A convention conversion was correct in prose but wrong in a table (`b/f0` under the certificate convention is `k_c^{-2}·b/f0`, not `k_c²·b/f0`). Text alone is not a reliable carrier of algebra; conversions must be executable.
2. `pr4e-claims-1.3.0` produces the same frozen digest on three environments, but "each environment can regenerate the same protocol" is not the same as "each environment executes one authoritative frozen protocol". CI currently regenerates the protocol from development statistics before running the locked layer, which means the frozen artefact is a conclusion of the run rather than an input to it.
3. High-chirp false rejections (74/240 in PR-4d) have at least two distinct causes: front-end frequency-estimation error, and a residual test whose null distribution does not hold for the actual extraction/fitting pipeline. Conflating them would lead to the wrong repair.

## Decision

### A. One authoritative frozen payload

1. The frozen payload (claims, group generators/actions, conventions, canonicalised thresholds, gate rules, precedence, model declaration, nuisance declarations) is generated **once**, in a designated environment, and archived as an immutable versioned artefact (committed file plus digest, or a signed archive). It is the input to execution.
2. **CI and other environments must read and verify that artefact; they must not regenerate it from development statistics.** Development calibration remains evidence, never the source of the executed protocol.
3. The digest covers the canonicalised payload only. The quantisation rule (currently 6 significant digits) is declared in the payload; boundary behaviour is covered by tests (values adjacent to a rounding boundary must be documented, and the rule must not silently flip).
4. Full-precision development statistics and selected thresholds remain in evidence, referenced by a separate evidence digest. Changing evidence or environment may never change the frozen digest; changing the frozen payload must.
5. Historical versions remain archived and are superseded, not rewritten.

### B. Convention conversions are executable

1. The two clock conventions are related by `k_c = 1/k_m`. This mapping, the induced actions, and the resulting scalings are enforced by automated tests, not prose:
   - M action `(f0/k_m, v, k_m t0 + β, k_m b)` and C action `(k_c f0, v, β + t0/k_c, b/k_c)` must describe the same group element under the mapping;
   - `f0·b` invariant under both;
   - `b/f0` scales by `k_m²` under M and by `k_c^{-2}` under C — the two statements must be tested to be equivalent, and a wrong exponent must fail;
   - forward preservation within tolerance for both actions.
2. Any new convention must arrive with the same executable conversion test. A table in a report is not evidence of an algebraic identity.
3. **Mathematical-evidence digests hash semantic content only**: theorem statements/statuses, assumptions, domain conditions, group declarations, booleans and counterexample references. Numeric self-check magnitudes, tool versions and environment strings are evidence, not digest content. The C1 incident (local `28696c97…`, CI `e01d02c7…`/`8db63f3d…`) is the reason this is a rule, not a preference.

### C. Evidence layers with distinct obligations

The system distinguishes three evidence kinds; they cannot substitute for one another:

| Layer | What it proves | Example | What it cannot prove |
|---|---|---|---|
| **Observational** | what the world presented to a sensor or published source | a recorded track, a controlled E1 pass | that a model is correct or a proposition is identifiable |
| **Mathematical** | a symmetry, parameter equivalence, or claim invariance under a declared model and group | symbolic proof T4/T5, numerical certificate | that the required observation exists in the field |
| **Execution** | what a specified code version, input and environment actually produced | three-environment claim decisions, replay digests | mathematical truth, or empirical support |

A claim record must state which layers support it and which are missing. The ontology addition (a normative section on evidence obligations) is a later deliverable; this decision fixes the distinction and the reporting requirement now.

### D. C2 rule: attribute before repair

1. The first C2 experiment is a diagnosis matrix, not a repair: **true generated frequency vs existing front-end extraction**, crossed with **correct constant-velocity model / unmodelled acceleration / high-chirp geometry**.
2. True generated frequency is permitted only in synthetic diagnosis. It must never enter a runtime or deployment decision path.
3. If false rejections appear only with the extracted frequency, the front end or its error model is the target. If they persist with the true frequency, the fit, residual statistic, or its null calibration is the target. A parametric simulation of the whole generate→extract→fit→residual pipeline estimates the actual null distribution of the test statistic.
4. De-chirping, pre-whitening and geometry-conditioned calibration remain **competing candidates**, all evaluated; no winner is declared before the attribution. Geometry conditioning may use only runtime-observable quantities (estimated chirp rate, signal quality, fit uncertainty) — never synthetic truth such as the true closest approach.
5. C2 may not change C1's formal conclusions: a model-adequacy improvement cannot solve the sound-speed structural non-identifiability, and cannot promote a claim.

### E. C2 acceptance

- false rejections of correct-model trials reduced on independent geometry levels;
- acceleration misspecification detection preserved **on new mismatch samples**, not only on the old 240;
- claim-level gating unchanged or stricter (no promotion through looser adequacy);
- three-environment claim decisions validated for the new rule;
- paired same-observation comparison old vs new, with intervals on an independent locked set;
- no improvement obtained by indiscriminate abstention.

## Consequences

### Positive

- The frozen protocol is an input with a single owner, not a per-environment recomputation.
- Algebraic conventions become test-enforced; a typo becomes a failing test rather than a paragraph to be trusted.
- C2 starts with attribution, so a front-end bug is not "fixed" by loosening a statistical test.
- Evidence types become reportable, which is the precondition for "what evidence is missing?".

### Negative / costs

- An extra frozen-artefact file and verification path; CI must fail if the digest or the artefact's content is inconsistent.
- Quantisation boundaries need explicit tests and documentation.
- C2 is slower because diagnosis precedes any repair, and three routes must be carried in parallel.
- Evidence-layer reporting adds fields to every claim record.

## Alternatives considered

- **Keep CI regenerating the protocol and compare digests.** Rejected: it tests reproducibility, not authority; a drift could be normalised away by regeneration.
- **Store full-precision thresholds in the frozen payload and accept cross-environment differences.** Rejected by the ruling and by the three-digest incident.
- **Skip attribution and add a chirp-rate guard directly.** Rejected: it might mask a front-end defect and would violate the no-premature-winner rule.
- **Let geometry conditioning use true `b`.** Rejected as truth leakage.

## References

- [Symmetry audit](../experiments/2026-11-05-c1-symmetry-audit.md), [ADR 0018](0018-symmetry-convention-audit.md)
- [C1 report](../experiments/2026-11-05-c1-identifiability.md)
- [PR-4e plan](../experiments/pr4e-plan.md)
- [PR-4d corrections](../experiments/2026-11-05-pr4d-report-corrections.md)
