# PR-4e plan — Identifiable claims, geometry-aware adequacy, and decision utility

**Status:** C1 in progress · 2026-11-05 · **Authority:** [ADR 0016](../decisions/0016-identifiable-claims.md) (claim semantics), [ADR 0015](../decisions/0015-model-adequacy-and-epistemic-decisions.md) (adequacy), [PR-4d corrections](2026-11-05-pr4d-report-corrections.md) · **Frozen:** E0, PR-4c and PR-4d artifacts and reports

**Priority order (per the founder's ruling).** Define what is recoverable **before** improving detection or risk curves. Claims are the unit; detection and evaluation follow.

## 0. P0 — close before C2

- **P0-1 frozen-protocol digest**: digest only the frozen payload; evidence/environment attached separately. Status: **closed after a caught failure** — v1.2.0 leaked full-precision development thresholds into the frozen payload and CI produced three different digests; v1.3.0 canonicalises thresholds to 6 significant digits, frozen digest `193e70ab…`, locked records unchanged `762ed383…` ([audit report](2026-11-05-c1-symmetry-audit.md) §6).
- **P0-2 symmetry convention**: forward-preservation audit of `G_clock`, invariance vs equivariance, generator coverage, PR-4d erratum. Status: **audit closed**; f0·b confirmed, PR-4d formula corrected ([ADR 0018](../decisions/0018-symmetry-convention-audit.md)).
- **Negative contract tests**: wrong certificate, omitted generator, contradicted nuisance must withhold support. Status: **closed** — wrong certificate, missing generator and contradicted nuisance all withhold support; 45 claims tests.

## 1. C — Formal identifiability contract (first; [ADR 0017](../decisions/0017-gated-invariants.md))

**Question.** Given the declared model, the declared allowed transformation group `G`, and the available observations, which propositions about the world are invariant across the observation equivalence class?

**C1 status (2026-11-05):** A, B and C delivered; D delivered on the locked layer with one defect — the frozen protocol digest varies with environment because evidence is embedded in the digest payload ([result report](2026-11-05-c1-identifiability.md) §7). Fix required before calling the protocol frozen.

**Deliverables.**

1. **Declared group.** `G` contains the transforms the evidence cannot exclude: clock offset `β`, clock rate `k = 1+ε`, and any additional declared nuisance (e.g. sound-speed uncertainty). Every claim record carries `G`; no implicit groups.
2. **Symbolic derivation** for each generator: `F(θ) = F(Tθ)` for the forward model, with the algebra shown.
3. **Independent numerical certificate**: a separate implementation (different code path from the method) samples parameter points, applies `T`, and checks `F` and each candidate `φ` within a declared tolerance.
4. **Claim taxonomy** for the E0-class parameters under `G`:
   - `v` — candidate invariant under rate and offset; **must be re-verified** with unmodelled sound-speed and direction uncertainty before it can be called physical;
   - `b/f0` — algebraically invariant under rate; physical interpretation open, not yet a supported claim;
   - `f0`, `b`, `t0` — not invariant under `G` (offset kills `t0`; rate rescales `f0`, `b`, `t0`).
5. **Claim-level output contract implementation** compatible with the nine-object ontology: `claim_id`, proposition, `G`, conditioning, status (`supported_invariant | supported_conditional | undetermined | contradicted`), evidence/verification references, uncertainty, sources.
6. **Normative spec addition** to [world-ontology](../specs/world-ontology.md) for claim records over `Hypothesis`/`Verification`.
7. **New independent validation sample** `PR-4e-L1` (new seeds, perturbation levels not used in PR-4d) and a **new protocol version**; frozen before opening.

**Acceptance.** (a) Symbolic and independent numerical derivations agree for every generator; (b) on `PR-4e-L1`, claim-level conclusions satisfy pre-declared validity and coverage criteria per claim; (c) a claim that does not survive the invariance obligation is reported `undetermined`, not promoted; (d) the frozen R1-D remains not passed and is reported separately.

## 2. Geometry-aware adequacy

**C2 diagnosis (2026-11-05) — complete.** Matrix of true vs extracted frequency: high-chirp false rejections are a **front-end structural error** (66% extracted vs 0% with true frequency), acceleration is genuine misspecification (rejects in both paths), and the asymptotic Ljung–Box null is invalid for the pipeline (pipeline p99 47× asymptotic) while the frozen threshold's tail stays 0/100. No repair route selected; per ADR 0019 §D the next step compares de-chirping, pre-whitening and observable-only geometry conditioning on paired observations. Artifacts in [diagnosis report](2026-11-05-c2-diagnosis.md). Repair phase follows [the C2 repair plan](pr4e-c2-repair-plan.md) and ADR 0020: extraction-error model first, then noise-matched controls, then B0–B3 paired comparison on a new frozen grid.

**Question.** Why are 74/240 correct-model trials in unseen geometry rejected, and can the adequacy tests become geometry-aware without losing acceleration detection?

**Approach.** Diagnose the residual structure under high chirp rate (front-end interpolation bias, non-stationarity), then compare: de-chirping before residual tests, pre-whitening, geometry-conditioned calibration, or a front-end validity guard. **No threshold widening.**

**Acceptance.** The false-rejection mechanism is attributed and reduced on a held-out geometry set while acceleration detection on the new locked sample remains ≥ the PR-4d rate (240/240); unmodelled limitations are reported even if not eliminated.

## 3. Risk–coverage with a valid old operating score

**Question.** Can old and new rules be compared at matched valid retention?

**Approach.** Give the old predictor a continuous operating score (e.g. improvement ratio or a calibrated residual statistic), then compute risk–coverage for both. If the score is not a calibrated probability, the report calls it "old predictor + selection mechanism", not the original old rule.

**Acceptance.** Estimable risk–coverage curves at matched retention with intervals, per claim and per mechanism; if the old rule cannot be ordered, say so instead of interpolating.

## 4. Decision precedence review

**Question.** Should `discrepancy` (model inadequate) outrank `optimization_indeterminate` when they disagree, and how should claim-level decisions handle the null-trial path difference?

**Approach.** Decouple optimizer status, adequacy status and claim status; evaluate the null-trial/precedence case independently on the new sample; keep raw causes visible. Upper claim semantics may coincide ("no supported claim") while raw reasons differ.

**Acceptance.** Claim-level semantics consistent across the three environments (or differences classified by ADR 0013), raw causes preserved, R1-D reported by its frozen protocol.

## Data, metrics, and reporting rules (all four items)

- **Frozen history.** E0/PR-4c/PR-4d artifacts, protocols and reports are not edited. PR-4e has its own protocol version, digest, and locked sample.
- **Claim-level evaluation.** Validity/coverage per claim; no pooled run-level accuracy; sample-flow table per mechanism (family sizes, accepted, correct, rejected, undetermined).
- **Strict policy.** Zero accepted claims ⇒ false-accept ratio **undefined**, reported as count + zero accepted, never as 0%.
- **Conditional claims.** Absolute-truth and conditional-truth error rates reported separately; conditioning population defined by the declared assumptions. **Assumption coverage** is the third required dimension: which assumptions are independently evidenced vs stipulated, and whether the current observation can detect an assumption violation. A conditional claim must never be read as "the assumption is known to hold".
- **Zero-event counts.** `0/k` is a count, not a zero error rate: report the one-sided upper bound and the clustering of trials.
- **No retroactive promotion.** Claim-level agreement never converts to R1-D pass.

## Non-goals

No new data adapters; no geo-localization claims; no rewriting of E0/PR-4c/PR-4d results; no threshold tuning to remove a specific failure.
