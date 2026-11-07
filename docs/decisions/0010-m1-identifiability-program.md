# ADR 0010 — M1 as an identifiability program (E0/E1/E2)

Status: Accepted
Date: 2026-11-04
Deciders: Haelio Tang (founder)

## Context

M1 was defined as "the acoustic inference vertical": feature extraction, a Doppler/kinematic verifier, a learned prior, and a preregistered comparison. That scope hides the real first question and lets a synthetic demonstration masquerade as evidence. The project's claim is not "we can geo-locate from sound"; it is that physical constraints, applied to incomplete and noisy observations, can make a world-state inference more reliable than a learned prior — and that the system knows when the observation cannot identify the state at all.

The first scientific question must therefore be narrower:

> **Can physical constraints distinguish a real motion event from wrong candidate explanations, in a noisy acoustic observation — and which parameters are identifiable at all?**

## Decision

1. **M1 is three experiments, each with a different epistemic status.**

   | Step | Data | Question | What a passing result establishes | What it cannot establish |
   |---|---|---|---|---|
   | **E0 synthetic** | generated signals, known truth | Does the estimator recover relative-motion parameters, and under what noise/acceleration/clock conditions does it fail? Which parameters are identifiable? | The implementation and numerical solver are correct; identifiability limits under ideal physics | Nothing about real noise, reverberation, propagation, or model mismatch |
   | **E1 real controlled** | licensed real recordings with known ground truth | Does the physical model discriminate true events from wrong candidate explanations under real conditions? | A scientific claim about discrimination, with false-positive/abstention/residual evidence | Generalization beyond the studied conditions |
   | **E2 independent reference** | E1 + one independent licensed source (e.g. track archive) | Does adding independent evidence improve reliability over the acoustic-only baseline? | A gain (or its absence) attributable to independence-aware fusion | That other modalities or regions behave the same |

2. **Synthetic evidence never supports a real-world claim.** E0 validates code and math; the first scientifically meaningful result must come from real data (E1). A pilot sample may guide design but may not be reported as passing a locked benchmark; only the preregistered E2 evaluation can carry a benchmark claim.

3. **The primary metric is area-bounded region coverage, not a point error.**

   ```
   Coverage@A = (1/N) · Σ 1[ y_i ∈ R_i ∧ Area(R_i) ≤ A ]
   ```

   with `y_i` the true location, `R_i` the predicted region, `A` the preregistered maximum area, and **abstentions counted as misses**. Every report must also publish the region-area distribution, abstention rate, reliability/calibration, and the same metrics for B0 (no-observation prior), B1 (learned prior alone), B2 (physics only), and B3 (combined). A prediction of the whole Earth surface scores near zero, which is the point of binding coverage to an area cap. The normative definition and reporting rules are in [`benchmark-and-evals.md`](../roadmap/benchmark-and-evals.md).

4. **`δ` and `ε` are not set now.** The win margin and the calibration guard are chosen at preregistration for E2, justified by power/sample-size reasoning, and fixed before the sealed split is opened. Declaring them in advance of the experiment design would be a number chosen to be met.

5. **Research metrics and publication metrics are separate.** Internally, under authorized conditions, an experiment may evaluate fine-grained error to diagnose failure modes. Externally published results pass through the independent granularity/sensitivity policy ([ethics](../policy/ethics-and-privacy.md), [ADR 0011](0011-privacy-forensics-and-publication-rulings.md)); a research metric does not automatically become a publishable claim.

6. **M1's exit is a report, not a victory.** The milestone is met when a report exists that states, with measured values and code, under which conditions the mechanism works, under which it fails, and whether it beats the simpler baselines — including when the answer is no. A negative result with a clean failure analysis satisfies M1 and triggers the roadmap's pivot criteria, not a rewrite of the claim.

7. **Stop conditions are inherited and sharpened.** If E1 shows the physical constraint adds nothing over the learned prior at the preregistered margin on both data tiers, the project stops claiming constraint-driven improvement at this scale and pivots to a verifier/residual toolkit (ROADMAP §8, S2). Identifiability degeneracy discovered in E0 (e.g. `f0`/velocity trade-off that noise makes unresolvable) is reported before any modeling investment.

## Consequences

### Positive

- Each step has an honest epistemic ceiling, so no later claim can borrow credibility from a synthetic result.
- E0 can start immediately with no external data, no adapters, and no licensing, which unblocks science while engineering catches up.
- A negative E0 or E1 is a published, usable result rather than a silent failure.

### Negative / costs

- Three steps take longer than one demo, and the first externally visible artifact is a synthetic study with deliberately limited claims.
- Binding coverage to an area cap makes headline numbers less impressive than unconstrained point-error results.
- Deferring δ/ε means E2's design work is front-loaded and cannot be skipped.

## Alternatives considered

- **Start with geo-localization accuracy on a public dataset.** Rejected: it measures a model's prior, not the physical mechanism, and invites claims the data cannot support.
- **Synthetic-only evidence program.** Rejected: it validates code, not the world.
- **Unbounded coverage or mean error as the primary metric.** Rejected: both are gameable and neither expresses the project's abstention/uncertainty stance.

## References

- [ROADMAP](../roadmap/ROADMAP.md) §2 M1, §8 falsifiers
- [Benchmark and evals](../roadmap/benchmark-and-evals.md) — normative metric definition
- [Research program](../research/research-program.md)
- [E0 report](../experiments/2026-11-04-e0-synthetic-doppler.md)
