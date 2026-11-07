# E1 pre-registration — draft for review

**Status:** DRAFT v2 · founder decisions 2026-11-05 incorporated · not sealed · **Owner:** founder · **Related:** [research program](../research/research-program.md), [ADR 0010](../decisions/0010-m1-identifiability-program.md), [E0 report](2026-11-04-e0-synthetic-doppler.md), [benchmark and evals](../roadmap/benchmark-and-evals.md)

**What this document is.** The scientific question, design, baselines, metrics, predictions, and failure rules of E1, written before any real recording is collected. It is a *draft*: the pilot (with its own data) may change operational details, and every change is recorded with a rationale. It is **sealed before the locked test set is opened**, not before the pilot.

**What E1 is not.** Not geo-localization. Not a benchmark claim. It tests whether a physical model that worked on synthetic signals still holds on real recordings, and if not, whether the failure is attributable to identifiable physical effects (non-constant velocity, recorder clock, reverberation, background sources) or to model-form error. A negative E1 is a publishable result.

## 1. Question

> **Do real motion sources produce acoustic observations that the simplified constant-velocity, delay-free Doppler model can identify — and when they do not, which physical factor explains the misfit?**

Four sub-questions:

| ID | Question | Condition |
|---|---|---|
| Q1 | Can a frequency track be extracted from real recordings under real background noise and reverberation, with accuracy measured against an independent reference? | E1-A |
| Q2 | Do non-constant velocity, recorder clock error, and reverberation cause the *predicted* parameter errors, or do they produce a different, model-form failure? | E1-B |
| Q3 | Does an identifiability check plus abstention reduce the rate of wrong conclusions at an acceptable coverage cost? | E1-C |
| Q4 | Can measured misfit be separated into (a) physical effects with a model and (b) residual model-form error? | cross-cutting |

## 2. Conditions

### E1-A — Track extraction under real conditions

**Manipulation.** Controlled recordings with known motion, replayed or re-recorded under: three background-noise levels (quiet, urban, traffic-dominant), two reverberation settings (free field, reflective), two SNR definitions (in-band versus broadband) — 12 cells minimum, ≥5 recordings per cell.

**Hypothesis A.** Median instantaneous-frequency error against the independent reference stays within a preregistered fraction of the Doppler excursion over the observation window, and the tail (p90) distinguishes usable from unusable cells.

**Measured.** Track error distribution (median, p90), track continuity (gaps, octave errors), detection rate, and the relationship between error and measured in-band SNR/reverberation time. Failures are classified: noise-dominated, interference, clipping, multipath, model-form.

**What an A-pass does not show.** That parameters are identifiable; that is E1-B.

### E1-B — Physical effects versus model-form error

**Design (2×2×2 plus model comparison).**

| Factor | Levels |
|---|---|
| Motion | constant velocity (verified by reference) vs accelerating or piecewise |
| Recorder clock | nominal vs measured offset and rate (independent reference) |
| Acoustics | free field vs reverberant |

**Hypothesis B.** On accelerating sources, the constant-velocity fit shows the *signed* bias predicted by E0 (speed underestimated, `b` biased, `t0` shifted); adding acceleration (or piecewise segments) reduces held-out residual and recovers the reference-derived parameters, but only where the window-to-timescale ratio keeps them identifiable. Where it does not reduce error, the failure is model-form or identifiability, not "physics is wrong".

**Model comparison.** Four frozen candidates evaluated on held-out recordings within E1-B's own split: M0 instantaneous-frequency baseline (no physical model), M1 constant velocity (E0), M2 constant acceleration, M3 piecewise-constant velocity with penalty. Selection by held-out predictive log-likelihood and residual structure, reported with parameter standard errors — never by in-sample fit alone, because added parameters always fit better.

**Physical-effect attribution.** An effect is attributed to a physical factor only when (i) the manipulation was measured independently, (ii) the sign of the parameter shift matches the prediction, and (iii) the residual structure changes in the predicted way. Otherwise it is reported as unattributed misfit.

### E1-C — Identifiability gate and abstention

**Manipulation.** Offline re-analysis of E1-A/E1-B recordings with the gate enabled versus disabled. Gate = linearized worst-direction relative standard error above a threshold, window-to-timescale ratio below a threshold, or degenerate parameter correlation.

**Hypothesis C.** The gate reduces the rate of *wrong accepted conclusions* (parameters outside physical plausibility, or sign-flipped velocity/offset) at a coverage cost bounded from the pilot, and does not merely discard easy cases: rejected and accepted cases are compared on the same difficulty strata.

**Measured.** Selective risk/coverage curve, error rate among accepted, decision-instability count (a case where a small numeric change flips accept/reject), and the fraction of rejected cases that would have been wrong.

## 3. Data requirements and authorization (gate to the pilot)

**Primary source — project-organized controlled recordings.** Participants explicitly authorize recording; motion is measured independently (reference track/IMU/radar), not inferred from the same audio model; environmental metadata (temperature, humidity, wind, surface) recorded; recorder clock measured against the reference clock.

**Secondary source — published licensed datasets.** Admissible for external validation only if it provides time synchronization and reference motion parameters; license checked and registered through the minimal fabric; no dataset whose terms forbid derived redistribution enters a publication path.

**Pilot versus locked test.** The pilot uses its own recordings (target n≥12 per cell). Model form, thresholds, and the gate are revised once after the pilot, with the revision and its rationale written into this document and timestamped. The locked test set is then collected or sealed, and no adaptation happens after it is opened. Any reuse of pilot recordings in the locked set is declared.

**Prerequisites before any real recording.** Operating jurisdiction named; consent form; retention period; access control for precise locations; data classification per [data governance](../policy/data-governance.md); RMF registration of the source with license, scale fields, and missingness. **Until these are recorded, E1-Pilot does not start.**

## 3a. Clock calibration (formal physical-claim requirement)

PR-4d proved that a constant clock offset is observationally equivalent to a change of event time, and a clock rate is an exact reparameterisation of `(f0, b, t0)` with `v` unchanged. Therefore **an absolute physical claim in E1 requires calibration of the affine clock model** `t_obs = α · t_phys + β`:

- at least **two independent time anchors** separated by enough duration to constrain `α` (rate) and `β` (offset), **or** a reliable rate calibration plus one absolute time anchor;
- a single synchronization event can align one instant but cannot estimate a rate;
- **no pseudo-independence**: if video and audio time references come from the same uncalibrated device clock, treating them as two independent evidences does not break the common drift;
- record the calibration uncertainty interval for `α` and `β` as an error budget against an independent reference (`|α̂−α_ref|≤1e-5`, `β` interval with a defined time origin), bind the requirement to the specific claims it supports, and report **which observation equivalence relations are actually broken** by the added reference (e.g. does the anchor make `t0` physical, or only narrow `β`?);
- claims that remain invariant to the residual clock uncertainty are `supported_invariant`; claims that depend on the declared nominal clock are `supported_conditional`; the rest are `undetermined` ([ADR 0016](../decisions/0016-identifiable-claims.md)).

A pass without a recorded affine clock calibration may support conditional claims only.

## 4. Baselines

| ID | Model | Role |
|---|---|---|
| M0 | Instantaneous-frequency tracking with closed-form inversion (E0's B0) | Shows what a physical model adds |
| M1 | Constant-velocity delay-free Doppler fit (E0's B1) | The model under test |
| M2 | Constant-acceleration fit | Tests whether acceleration explains misfit |
| M3 | Piecewise-constant velocity | Tests whether piecewise structure explains misfit without free acceleration |

Baselines share the same front end, windows, splits, and abstention policy unless a difference is the treatment.

## 4a. C2-derived hypotheses and the scale audit (v4 addition)

E1 is no longer only "can real Doppler be fitted". It must target the failure mechanisms C2 exposed:

| Sub-experiment | Main question | C2 link |
|---|---|---|
| **E1-A Measurement transfer** | does real-audio frequency extraction show the same FFT-bin / window / time-dependent error structure? | C2-A, M2, M3 |
| **E1-B De-chirp out-of-sample validity** | does B1 improve blocks **not used** to estimate the de-chirp or motion parameters? | B1 time-block self-confirmation |
| **E1-C Mismatch recognition** | under real acceleration, clock drift and reverberation, are detection / rejection / abstention reliable? Detection follows **E1-C Detection Consensus v2**: each estimator is D/A/U; D+D detected, A+A no mismatch found, all mixed/U+U undetermined (U+U is never not-detected). Single-estimator detection is secondary only. E1 must pre-register expected consensus power. Estimator agreement tests numerical implementation, not physical/measurement-model validity; claim support compares claim values under the declared transformation group, not only raw parameters. E1-A/B/C outcomes are decided independently. E1-C reports two primary endpoints with abstention: sensitivity/TPR on true mismatch and false positive rate (FPR) on adequate physical models; the false discovery proportion (FDP) is reported as a derived diagnostic when deterministic detections exist. A `detected` result is scoped `evidence_scope = estimator_consensus` and `physically_supported = false`; it cannot be presented as a physical model-mismatch conclusion without an independent measurement-error model, independent prediction or external evidence. | 150-400 Hz/s detection failure; 6/12 estimator flips |

Before any collection, the **E1-0 instrument feasibility gate** ([E1-0](E1-0-instrument-feasibility.md)) must be answered with bench evidence (frequency resolution at a few-Hz Doppler shift, clock calibration uncertainty, independent truth, safe geometry, SNR/distortion). E1-B follows the leakage-proof protocol ([E1-B leakage](E1-B-leakage-protocol.md)): pre-registered block boundaries, STFT guard bands, and no held-out statistics in prediction, gating, normalization or model selection.

E1-B is a primary confirmation experiment: fit on designated blocks, generate the de-chirp prediction once, and evaluate held-out blocks without re-estimating from them. A re-fit on the held-out blocks may be reported only as a separate analysis condition.

The synthetic fault-injection rehearsal ([E1-0 fault injection](E1-0-fault-injection.md)) covers clock ppm, clipping, dropouts, wind bursts and reference-channel loss; it is a synthetic stress test, not instrument evidence. The atmospheric uncertainty operator ([E1-0 atmosphere](E1-0-atmosphere-uncertainty.md)) converts measured temperature/humidity/pressure/wind uncertainty into a predicted Doppler interval; it is a planning bound, not a validated atmospheric model. The raw capture bundle gate ([E1-0 raw bundle](E1-0-raw-bundle-schema.md)) refuses a bundle missing independent frequency/time references, calibration, site authorization or consent before any snapshot is created. The chirp-rate scale audit ([E1-scale-audit.md](E1-scale-audit.md)) shows a safe low-speed pilot covers roughly 0.1-70 Hz/s; the C2 150-400 Hz/s band is not reachable safely and must be declared uncovered unless a separately authorized setup is designed. Same chirp rate does not imply equivalent trajectory, noise or propagation.

## 5. Preregistered predictions

Derived from E0's measured biases and the model algebra, before looking at real data.

1. **P1** — On accelerating sources, the constant-velocity fit underestimates speed and biases closest-approach distance and `t0` in the E0-measured direction; the bias grows with acceleration and window-to-timescale ratio.
2. **P2** — A constant recorder-clock offset is degenerate with `t0`: with no independent time reference, `t0` is not identifiable, and the gate should abstain on `t0` rather than report it. Clock *rate* biases `f0`, `t0`, `b` by approximately the rate error, not `v`.
3. **P3** — Reverberation broadens the instantaneous-frequency track and increases residual RMS more than it biases the median frequency; its effect should appear as tail error and residual autocorrelation, not as a uniform shift.
4. **P4** — The identifiability gate lowers accepted-case error rate; the coverage cost is estimated from the pilot and frozen before the locked test.
5. **P5** — M2/M3 improve held-out fit on high-acceleration recordings but have larger parameter standard errors; the expected trade-off is an identifiability loss, not a free win. If M2 beats M1 on held-out fit but not on parameter recovery, the conclusion is "better prediction, worse identification", and both are reported.
6. **P6** — Real recordings' residual structure will fail a white-noise test (autocorrelation above the pre-declared threshold) in at least the reverberant cells, indicating model-form error that no parameter change fixes.

## 5a. Failure taxonomy and decision stability (ADR 0014)

Every E1 failure is classified into exactly one mechanism, and the classification is reported with evidence:

| Mechanism | What it means in E1 | How it is detected |
|---|---|---|
| Physical unidentifiability | The recordings cannot distinguish candidate states (e.g. `f0`/offset/geometry trade-offs). | Pre-declared operational gate (normalized SE, condition number, local sensitivity); reported as an operational gate, not proven structural identifiability |
| Numerical instability | The optimizer produces different execution states for near-identical problems (iteration path, termination, derivative evaluation). | Fixed-parameter cross-evaluation across environments; termination and iteration records |
| Decision instability | A small numerical difference changes a scientific conclusion (accepted/rejected, published rate). | Declared deciding statistic + margin; `indeterminate` state; raw values preserved |

The four statuses are recorded separately per pass: `optimization_converged`, `parameter_identifiable`, `model_adequate`, `decision_status ∈ {accepted, rejected, indeterminate}`. Any discrete decision that can change a published E1 conclusion must have an explicit margin and an `indeterminate` state ([ADR 0014](../decisions/0014-failure-taxonomy-and-decision-stability.md)).

Prepared before collection and required before the first pass: [consent template](../policy/consent-template.md), [instrument calibration and static-reference procedure](E1-instrument-calibration.md), [data registration form](E1-data-registration.md).

## 6. Metrics and analysis

- **Track accuracy (E1-A):** median and p90 absolute frequency error against the independent reference; continuity; detection rate; error versus measured SNR and reverberation time.
- **Parameter recovery (E1-B):** relative error and signed bias of `f0`, speed, `t0`, `b` against the independently measured truth; standard errors from the fit; physical-plausibility violations.
- **Model comparison:** held-out predictive log-likelihood per recording, paired across recordings, with CIs; parameter SE; residual autocorrelation and normality diagnostics.
- **Selective behavior (E1-C):** error rate among accepted, coverage, risk–coverage area, decision-instability count.
- **Attribution:** fraction of misfit cases assigned to a physical factor under §2's three-condition rule; the rest reported as unattributed.
- **Aggregation:** per cell and per recording, never pooled only; paired comparisons; bootstrap CIs clustered by recording/source, not by window.

No location metric appears in E1. No accuracy claim is made from the pilot.

## 7. Failure rules and stop conditions

| Condition | Consequence |
|---|---|
| E1-A cannot reach track accuracy sufficient for E1-B on ≥half the cells | E1 stops at "the model does not apply to real audio at this scale"; report the failure and the noise/reverb thresholds |
| E1-B finds misfit dominated by unmodeled environment and no model in M2/M3 improves held-out fit | Conclude the constant-velocity model is not identifiable on real recordings; pivot to environment-robust front end plus abstention, still reportable |
| The identifiability gate does not reduce accepted-case error rate (E1-C) | Report the gate as unvalidated; do not ship it as a safeguard |
| A prediction P1–P6 fails | Report as falsified in its own section; no post-hoc rewriting |
| Data authorization unavailable for the pilot | E1 pauses; no substitute with unlicensed recordings |

## 8. Reporting and sealing

1. **Draft (this document)** — reviewed by the founder before the pilot.
2. **Pilot report** — E1-A on pilot data only; design revisions recorded with rationale and date.
3. **Sealed preregistration** — this document frozen with the revisions, the pilot report reference, the gate thresholds, the final n, and the locked-test procedure. Freeze via digest recorded in the report.
4. **Locked test report** — fills the [benchmark report template](../roadmap/benchmark-and-evals.md); includes every failed prediction, the failure gallery, and the data/licence manifest.
5. **Reproduction** — the locked run must replay through the minimal fabric (`make e0`-style path); cross-platform comparison uses the R1 protocol ([ADR 0012](../decisions/0012-research-grade-minimal-fabric.md) §6, PR-4).

## 9. What E1 cannot establish

No geographic localization, no cross-modal fusion, no generalization beyond the studied conditions, no person-level inference. Even a clean E1 only says: *on these real recordings, the simplified model behaves like this, and here is what fails.*

## 10. Companion: independent physical validation (next unit after PR-4)

Three different questions, never substitutes for one another:

| Layer | Question | Mechanism |
|---|---|---|
| Cross-platform reproducibility | Does the same algorithm produce equivalent output in another environment? | R1 protocol (PR-4) |
| Independent physical validation | Does a *different implementation* support the same physical prediction from a fixed truth? | A second implementation (different language or independent math path) checked against the model algebra on fixed cases |
| Real-world validation | Does the physical prediction match real observations? | E1/E2 |

The independent validation unit is scheduled after PR-4 and before E2; it does not replace E1 and is not evidence about the world.

## 11. Founder decisions (2026-11-05)

**Pilot goal (formal).** E1 Pilot exists to show whether PhainoWeave can *identify model misfit, parameter degeneracy, and undecidable states in real observations* — not to fit a Doppler curve successfully, and not to demonstrate geo-localization. A report that says "the model failed here, for these measured reasons" satisfies the pilot.

**Equipment — plan B, hard budget ≤ 400 USD.** Required: fixed uncompressed audio recorder; stable-frequency loudspeaker; tape measure/distance measurement; independent camera for geometry/time; temperature/humidity meter (recommended); phone GNSS/IMU as auxiliary cross-check. Not purchased: RTK GNSS, radar (later phases). Cheap plan A ($0–100, phone + existing speaker) is allowed for instrument-check runs first; equipment purchase is never a prerequisite for starting, and a purchase does not count as acceptance.

**Venue.** A private yard, open experimental lot, or authorized closed test area with explicit permission: safe low-speed passes, space for a fixed receiver, minimal non-participant presence. Not public roads, not near airports, not high-traffic noise environments in the first round.

**Jurisdiction.** Determined by the actual recording location, never inferred from where the equipment owner lives. If the pilot is run in Nepal, Nepal is the tentative jurisdiction pending venue and legal review; the Privacy Act, 2075 (2018) is noted as relevant to personal data and recording, so outdoor placement alone does not imply permission to record or publish.

**Consent and authorization.** Written or electronically signed research consent recording: purpose; the audio/video and motion data involved; who may access raw material and precise locations; whether open-source research, papers and public benchmarks are permitted; retention period and withdrawal mechanism; and the authorization chain (participant, venue manager, equipment owner). Identity verification and a signed copy are prerequisites, not paperwork.

**Pilot scale and design.** 18–30 controlled passes, used to discover equipment, synchronization and model problems — never to claim an accuracy figure. Cover three dimensions: low constant speed; speed variation; different closest-approach distances. Record empty-field background as a control. Per pass record: playback frequency setting, source trajectory, receiver geometry, sample rates, ambient temperature, synchronization events, and raw file hashes.

**Two physical variables that must not be assumed away.** (a) *Speaker frequency stability*: if the playback clock drifts, it can masquerade as source motion; frequency must be measured, not trusted. (b) *Speed of sound*: it changes with temperature (≈343 m/s at 20 °C); it is an estimated parameter with uncertainty, not a permanent constant. Static-source recordings before and after each moving series measure the frequency reference and device clock state, so real Doppler can be separated from device artifacts.

**Truth must carry uncertainty.** Reference values from camera geometry, distance measurement, phone GNSS/IMU, and timing are estimates. The pilot defines a truth-uncertainty budget covering video calibration error, frame rate, clock accuracy, distance measurement, and motion of the reference setup. A model estimate is judged wrong against the truth *interval*, not against a bare number. E0's exact synthetic truth does not transfer.

**Retention (operational rule, not a legal claim).** Raw audio/video defaults to a 90-day review-retention window, then a documented decision to keep or delete; raw precise locations and identifiable audio/video are not published in the pilot report. Publishable artifacts are desensitized features, experiment parameters, hashes and reproducible non-sensitive outputs.

**Data collection status.** Not approved to start. The gate is: venue permission, jurisdiction confirmation, consent/authorization records, instrument calibration and static-reference checks, truth-uncertainty budget, and data-governance/RMF registration all complete. Until then this remains a protocol, and no participant data is collected.

## 12. Remaining open items

1. Exact venue and written permission; planned dates.
2. Who operates the equipment and who signs as witness/operator; consent template and identity-verification method.
3. Legal/ethics review confirmation for the Nepal jurisdiction (or the actual recording jurisdiction if it changes).
4. Loudspeaker frequency stability measurement method (how the playback clock is verified) and the camera calibration procedure.
5. Whether a published dataset with verified synchronization and reference motion is available as the external-validation tier; it does not replace the primary controlled data.
