# Research Program — Physics-grounded Evidence Fusion under Incomplete Observations

**Status:** adopted 2026-11-04 · **Owner:** founder · **Supersedes nothing; narrows the claim** · **Feeds:** [ADR 0010](../decisions/0010-m1-identifiability-program.md), [ROADMAP](../roadmap/ROADMAP.md) tracks A/B, [benchmark-and-evals](../roadmap/benchmark-and-evals.md)

## The claim the project is testing

> **Physics-grounded Evidence Fusion under Incomplete Observations**
>
> Can physically grounded, provenance-aware inference reliably reconstruct latent environmental states from incomplete, noisy, and potentially contradictory observations?

中文：**当环境观测不完整、存在噪声、甚至相互矛盾时，融合物理约束与可追溯证据，能否可靠地重建潜在环境状态？**

This is not "locate a recording from sound". Geolocation is one *instance* of latent-state reconstruction; the reusable mechanism is the one that turns physical constraints into tests of world-state hypotheses while tracking provenance, dependence, and the limits of what the data can identify.

## Core scientific principle

> **Recover what is identifiable. Preserve what is uncertain. Never promote observational equivalence into physical certainty.**

This is the project's decision rule for its own outputs. The unit of scientific conclusion is the **claim**, not the inference run: a recording may support relative-motion claims, leave absolute time unidentifiable, and support a distance only under a declared clock assumption — all in one report ([ADR 0016](../decisions/0016-identifiable-claims.md)). Detection quality and risk–coverage matter, but only after the set of recoverable claims is defined.

## What would make this a research contribution

Four properties, each independently testable. A system that has some of them is a tool; a system that establishes all four under adversarial conditions has a method.

| # | Property | Testable form | Failure that disproves it |
|---|---|---|---|
| P1 | **Physical consistency** | Every accepted hypothesis satisfies the declared constraint residuals within tolerance; a candidate that violates kinematics/ephemeris/geometry is rejected and the residual is reported. | A hypothesis survives with an unexplainable residual, or the residual is decoration rather than a filter. |
| P2 | **Evidence-dependence correction** | Correlated evidence from one physical event does not increase confidence beyond one vote ([I7](../specs/world-ontology.md)); paired-evidence tests show calibration is not degraded by naive pooling. | Same-event evidence multiplies confidence, or "independence-aware" aggregation cannot be distinguished from naive pooling on held-out data. |
| P3 | **Reliable uncertainty** | Reported regions/windows are calibrated (reliability diagram, ECE) and selective risk improves monotonically along the coverage–risk curve. | Confidence is uncalibrated, or abstention does not buy accuracy. |
| P4 | **Identifiability awareness** | The system declares when the observation cannot distinguish candidate states — and is right about it. | It returns a confident region where the inverse problem is degenerate (e.g. unknown source frequency traded against velocity). |

**P4 is the theoretical core.** Most inference systems are built to answer; this one must also be able to say "you cannot know this from what was observed", and be correct when it does. That is an inverse-problem identifiability question, not a model-accuracy question, and it is where the project can contribute something a larger platform cannot.

## What is *not* the claim

- Not "better geolocation than existing models". That would be a benchmark race on priors, not a mechanism.
- Not a platform claim. Ontology, fabric, workbench, and distributed deployment are engineering necessary to make results reproducible, not the contribution.
- Not that physics beats learning. The claim is that a verified physical constraint plus a learned prior is *better calibrated and more falsifiable* than either alone — and the data may say otherwise.
- Not a claim about person-level inference. That stays excluded (ADR 0005, 0011).

## How it is tested

The investigation is deliberately narrow first ([ADR 0010](../decisions/0010-m1-identifiability-program.md)):

| Step | Question | Evidence class | What it can establish |
|---|---|---|---|
| **E0** synthetic Doppler | Which relative-motion parameters are recoverable, under what noise/acceleration/clock error, and when are they not identifiable? | Synthetic | Estimator/solver correctness; identifiability limits under ideal physics |
| **E1** real controlled recordings | Do physical constraints discriminate true motion events from wrong candidate explanations under real noise? | Real, licensed, known truth | The first scientific claim about the mechanism, with false-positive and abstention evidence |
| **E2** locked benchmark with independent reference | Does independent evidence improve reliability over the acoustic-only baseline, at a preregistered margin, without hurting calibration? | Real + independent source, sealed split | A benchmark claim, or its falsification |

Rules that constrain every step: the output is a region/time distribution with residuals, never a point; abstention is scored; the win margin and calibration guard are fixed at preregistration; failures are published; synthetic results never support real-world claims.

## Falsifiers for the research program

- **F1.** At E1, the physical constraint does not improve discrimination over the learned prior at the preregistered margin on both data tiers → the constraint claim fails at this scale; pivot to a verifier/residual toolkit.
- **F2.** After documented mitigation, correlated evidence still degrades calibration → cross-modal fusion claims are frozen; single-modal verification only.
- **F3.** Reported uncertainty remains uncalibrated on held-out splits after recalibration attempts → the system is not fit to produce scientific output; publish the negative result.
- **F4.** Identifiability analysis shows the realistic regimes are degenerate (e.g. unknown source frequency plus unknown track offset make the region unrecoverable) → the project's viable contribution shrinks to identification of *when* the question is unanswerable; that is still a contribution, and must be claimed as the smaller one.

Each falsifier is written before results exist so a negative result cannot be reframed afterward.

## Relation to prior art

The individual physics and modalities are not new: aircraft-Doppler geolocation demonstrations and reproductions, distributed acoustic sensing, bioacoustic geolocation, cross-view geolocation, and OSINT verification practice all exist ([landscape](landscape.md)). What is missing in each is the system-level discipline this program tests: evidence provenance, explicit dependence, calibrated uncertainty, and identifiability — applied across modalities rather than as a single-modality demo.

## Near-term deliverables

0. **Identifiable-claims contract** — symbolic and independent numerical invariance proofs, claim-level statuses, and a new locked sample (PR-4e C item).
1. **E0 report** — synthetic identifiability study with measured parameter errors, failure conditions, and a preregistered expectation section.
2. **E1 report** — real controlled recordings; the first scientific claim the project can make, positive or negative.
3. **RMF** — the minimal licensed, snapshot, offline-replay fabric that makes E1/E2 reproducible ([ADR 0008](../decisions/0008-two-track-execution.md)).
4. **E2 preregistration** — sealed split, metric (`Coverage@A` bounded), baselines B0–B3, δ and ε justified.

## Success, stated so it cannot drift

The program succeeds when a third party can rerun an experiment and reach the same conclusion about *when the mechanism works, when it fails, and whether it beats a simpler baseline* — including when the answer is "it does not". Document volume, test count, connector count, and platform features are not success measures ([ADR 0008](../decisions/0008-two-track-execution.md) §5).
