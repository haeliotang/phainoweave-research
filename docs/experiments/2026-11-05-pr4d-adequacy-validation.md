# PR-4d — Model adequacy layer, locked validation, and the decision-utility boundary

**Status:** measured; adequacy layer works, strict policy has zero retention, conditional policy exposes 200 irreducibly-equivalent false accepts; matched-retention comparison not estimable · 2026-11-05 · **Authority:** [ADR 0015](../decisions/0015-model-adequacy-and-epistemic-decisions.md) · **Plan:** [pr4d-plan](pr4d-plan.md) · **Frozen E0:** [E0 report](2026-11-04-e0-synthetic-doppler.md)

**What this report is.** The adequacy layer as implemented, its frozen protocol, the tuning and locked validation results, an independent evaluator's risk–coverage analysis, the cross-environment check, and a correction to the PR-4d plan's failure decomposition. E0's original code, artifact and criteria remain untouched (`674213d9…`); the layer is additive.

## 1. The 600 false accepts do not decompose as first assumed

The plan recorded 400 model misspecification (acceleration + clock rate) and 200 observational equivalence (clock offset). The locked validation corrects that:

| Family | Trials | Verdict | Evidence |
|---|---|---|---|
| Acceleration (unmodelled dynamics) | 240 locked (200 in E0) | **Detectable model misspecification** — adequacy rejects 240/240 | held-out block-median RMSE, Ljung–Box, residual time-structure |
| Clock **offset** | 200 | **Exact observational equivalence** — `β` ↔ `t0` | null ratio 0, profile flat ~1e-14 |
| Clock **rate** | 160 locked (200 in E0) | **Exact observational equivalence** — `α` is a reparameterisation: `f0→f0(1+ε)`, `t0→t0/(1+ε)`, `b→b/(1+ε)`, `v` unchanged | verified at 1e-12; residuals are excellent by construction |

So of the 600: **240 are detectable misspecification and 360 are observationally equivalent** under the nominal model. This is not a detector weakness; it is an information-theoretic statement, and it is test-backed.

## 2. Adequacy layer

Five declared tests, each with a calibrated threshold (protocol digest `c86cb63d487e72a2c9964bfdaf41aa8adfa84199ce1515071eeceb1b78d9f029`, frozen before the locked layer was opened):

| # | Test | Statistic | Threshold | Calibration |
|---|---|---|---|---|
| 1 | residual scale/distribution | max\|z\|, tail>3, \|excess kurtosis\|, robust-scale ratio | 8.84 / 0.0146 / 2.72 / [0.589, 1.561] | tuning maxima ×1.3 margin |
| 2 | autocorrelation | Ljung–Box order 89, df 85 | 7671.6 | calibration max 5901; no fixed p-value |
| 3 | residual time/phase | \|corr(t)\|, quadratic coefficient/σf, \|phase corr\| | 0.0747 / 0.1897 / 0.1431 | tuning maxima ×1.3 |
| 4 | time-block held-out (K=5) | median held-out RMSE/σf; median block explained fraction | 1.406 / ≥0.500 | null vs nominal separation 0.948 |
| 5 | degeneracy + clock model | worst_rel_se, condition number, clock null ratio, profile flatness | 1e-2 / 1e4 / 1e-10 / 1e-4 | analytic null directions |

Outputs per trial: `model_adequacy_status ∈ {adequate, discrepancy, insufficient_evidence, indeterminate}`, `identifiability_status`, `epistemic_decision ∈ {supported, rejected, undetermined}`, reason codes, full test evidence. Truth is present only under `evaluation_only`; the decision entry points accept no truth (signature-tested).

## 3. Locked validation (1420 trials, new seeds and unseen perturbation levels, opened once)

| Rule | Accepted (`supported`) | Correct-accepted | False accepts | FA rate | Valid retention | Abstention |
|---|---|---|---|---|---|---|
| Old hardened | 1240 | 800 | 440 | 35.5% | 100% | 11.6% |
| **New, strict** (physical claim) | 0 | 0 | 0 | — | 0% | 75.6% |
| **New, conditional** (nominal-clock-conditional claim) | 867 | 667 | 200 | 23.1% | 83.4% | 14.6% |

Progress against the ruling's goals:

- **Misspecification detected:** 240/240 acceleration trials rejected — 0 accepted, 0 undetermined.
- **Equivalence declared, not mis-claimed:** 360/360 offset+rate trials are `undetermined` under strict policy; none is `supported`. The strict rule has zero false accepts.
- **Negative result (must not be hidden):** 74/240 valid geometry trials are **wrongly rejected** (LB 22%, time-structure 32% of correct-model geometry trials fire). The residual tests are not geometry-invariant; the front-end's interpolation bias depends on sweep rate (455 Hz/s at 200 m), so thresholds calibrated on the 300–3000 m tuning geometry over-discriminate. The fix is a chirp/quasi-stationarity guard or geometry-stratified calibration — **not** widening thresholds.
- **Non-discriminating tests:** phase correlation fires on 0/1420 trials; max\|ACF\| alone never gates; the distribution test fires only at −12 dB; the block explained-fraction floor fires only on null. Acceleration is caught by held-out block-median RMSE (240/240) plus Ljung–Box and time-structure. These are reported as measured test power, not as successes.

## 4. Independent evaluation and the matched-retention gap

`phaino_adequacy_eval` (written separately, imports no method code) consumes the artifacts and applies the frozen E0 tolerances for truth.

- Old rule: FA 35.5% at 100% retention.
- Strict: FA 0% at 0% retention.
- Conditional: FA 23.1% at 83.4% retention; the 200 false accepts are exactly the observational-equivalence trials that the conditional claim admits.
- **Matched-retention comparison is not estimable.** The old rule exposes a single operating point (all accepted trials share one status signature), so its risk–coverage curve cannot be interpolated at the new rule's retention; the evaluator reports `old_estimable: false` instead of extrapolating. A proper matched-retention comparison requires an old-rule operating score (e.g. improvement ratio or a residual p-value) to construct its risk–coverage curve. This is a PR-4d finding, not a satisfying answer to the ruling's central metric.

## 5. Cross-environment check (A macOS arm64, B/C Linux x64/arm64)

| | A | B | C |
|---|---|---|---|
| protocol digest | `c86cb63d…` | same | same |
| adequacy status counts (1420) | 867 adequate / 444 discrepancy / 59 indeterminate / 50 insufficient | identical | identical |
| identifiability status | identical | identical | identical |
| epistemic decisions | 346 rejected / 1074 undetermined | identical to A (346 / 1074) | 347 rejected / 1073 undetermined (one null trial) |

The single difference is a null trial (`locked_null_-5dB` #27): A/B report `optimization_indeterminate` and therefore `undetermined`; C's optimizer converges and the adequacy verdict is `rejected`. The adequacy status itself is `discrepancy` on all three. Both outcomes are "no supported physical claim", so decision utility is unchanged, but **formal decision equivalence is 1419/1420** and R1-D remains not established for the adequacy layer. The cause is the known precedence issue (optimization first) on a signal-free trial — the same class as the PR-4c null difference, not a new failure.

## 6. The protocol decision that is now unavoidable

Under ADR 0015's strict reading — a clock that is not separately identifiable blocks a physical claim — `supported` is **unreachable in E0**, because a clean recording and a rescaled-source recording are the same observation. The honest options:

| Option | Meaning | Retention | False accepts | Consequence |
|---|---|---|---|---|
| **A — strict** | physical claim requires an absolute external time reference; no reference ⇒ `undetermined` | 0% | 0% | truthful, but the E0 tool cannot conclude anything; the result *is* the boundary |
| **B — conditional** | support a claim explicitly typed *nominal-clock-conditional* | 83.4% | 23.1% (all equivalence cases) | useful for relative content, must never be presented as physical |
| **C — clock-invariant content** | support only content invariant under `(α, β)` — e.g. speed `v`, relative geometry | needs a new protocol version | to be measured | likely the scientifically correct middle path |

**Recommendation to the founder:** adopt A as the default for any *physical* claim; allow B only as an explicitly labelled conditional claim that carries its equivalence-level false accepts; commission C as the next protocol version using reparameterisation-invariant content. Do not silently pick B and call the output "supported".

## 7. Checklist status

| Item | State |
|---|---|
| 1 Freeze E0 / existing decisions | **Done** |
| 2 Group the 600 by mechanism | **Done** (240 detectable / 360 equivalence, evidence-backed) |
| 3 Residual tests + calibrated Ljung–Box | **Done** |
| 4 Block held-out + degeneracy/clock model | **Done** |
| 5 Independent Tuning / Locked layers | **Done** (locked opened once, protocol digest frozen) |
| 6 FA / retention / abstention + risk–coverage comparison | **Partial** — retentions and FA measured; matched-retention blocked by the old rule's single operating point |
| 7 Three-environment validation | **Partial** — adequacy identical, epistemic 1419/1420; the one difference is the known null/precedence case |
| 8 Formal report with failures and negative results | **This document** |

## 8. What comes next (PR-4e candidates)

1. **Old-rule operating score** so matched-retention risk–coverage is actually estimable (the central metric of the ruling).
2. **Geometry-stratified calibration or chirp guard** to remove the 74 false rejections.
3. **Option C protocol** (clock-invariant claims) with its own locked validation.
4. **Null/precedence revisit**: should a `discrepancy` adequacy verdict outrank an `optimization_indeterminate` in the epistemic decision? Needs a new protocol version and a locked re-run.
5. **E1**: the physical/conditional distinction becomes empirical only with an absolute time reference; that is now a formal data requirement for E1, not a footnote.

No claim in this report is about real recordings. The layer is validated on synthetic signal models only, exactly as E0 was.
