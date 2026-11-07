# Benchmark and Evaluation Design

**Status:** Adopted, evaluation protocol · **Last updated:** 2026-11-04 · **Owner:** Haelio Tang
**Authority order:** newest Accepted ADR > [ROADMAP](./ROADMAP.md) > [founding brief](../product/founding-brief.md) > research notes.
**Scope:** how PhainoWeave measures inference, and what may and may not be claimed from a measurement. This file is binding on every experiment report. It defines the protocol; it contains no results. Object field names come from [world-ontology.md](../specs/world-ontology.md); the residual and abstention fields a run must emit come from [inferencer-contract.md](../specs/inferencer-contract.md).

## 1. The unit of evaluation

The unit is a **world-state hypothesis with residuals**, not a point answer. For case `i` the system emits a record containing: candidate region `R_i` with a stated region probability `p_i` (the probability that the true location lies in `R_i`), candidate time window `W_i`, environmental state `S_i`, the evidence graph path that produced the candidate, one normalized residual per applied constraint, and either `answered` or `abstained` with a reason code.

The ground truth is a reference location `l_i`, reference time `t_i`, and reference state, with its own stated error. Scoring consumes only the run record: no hidden scores, no re-derived outputs, no manual post-processing. A metric that cannot be recomputed from the record is not a metric.

**Population and exclusions.** The evaluation population is defined before unsealing: which observation classes are eligible, which are out of scope, and how one case is constructed (one recording, one event, one image pair). Excluded cases are counted by reason in a table — insufficient ground truth, unresolved license, failed ingest, duplicate — and never silently removed. The report states the eligible population, the sampled subset, and the inclusion rule, so a reader can tell what the metrics apply to and what they do not.

Two consequences follow. First, an abstention is a scored outcome, not a missing value: it is a miss in coverage denominators and a decision point in selective curves, never a row to drop. Second, a system that outputs a region is scored on that region's area and probability, so a wide region is not free and a confident narrow region that misses is expensive.

## 2. Splits

Every report scores the same case definitions across all splits and declares each split's construction in the data snapshot. A split that was used for any tuning decision is not a test split.

| Split | Construction | What it measures | What it cannot prove |
|---|---|---|---|
| Tuning | Development cases; model selection, thresholds, and aggregation rules are chosen here only | Nothing reportable as capability | — (never reported as a result) |
| Geographic isolation | Hold out entire regions or terrain classes absent from tuning; report each held-out region separately | Transfer across ecology, propagation, infrastructure, and track density | That the system generalizes to unheld regions; isolation selects on known axes only |
| Temporal isolation | Hold out a time window after all tuning decisions; report each window separately | Drift from fleet changes, sensor populations, seasons, and dataset revisions | Stationarity into the future; epoch-specific confounds remain |
| Negative / null | Observations with no target source or event present; system should abstain or return a null world state | False positives and the cost of asserting on absence | That a detection threshold is safe outside the sampled negative population |
| Abstain | Deliberately insufficient evidence: clipped, broadband, no candidate track, contradictory evidence | Whether abstention is calibrated and selective | That all unanswerable cases are recognized |
| Near-duplicate leakage | Exact and approximate duplicate detection before assignment; duplicates never span splits | Contamination from the same recording, event, or sensor | That semantically related but non-duplicate cases are absent |

Near-duplicate controls must name the detector and its threshold: audio fingerprinting for recordings, perceptual hashing for imagery, and proximity in time and space for sensor or event records. Report overlap counts before and after deduplication. Duplicates found across a proposed split boundary are removed and counted, not silently kept.

**Split hygiene.** The test split is sealed before any tuning decision and its hash recorded in the preregistration; it is opened once per report. Tuning logs (every configuration evaluated and where) are retained so that an undeclared selection cannot be reconstructed post hoc. Case counts, per-split label balance, and the dedup report are part of the data snapshot. A test split inspected for a failed run is retired for the primary metric; the rerun uses a new seal, and both seals are reported.

**What no split proves.** A split is a selection on axes we can observe; it does not establish out-of-distribution generalization. Three failures are structural. (1) A pretrained prior may have seen evaluation regions during its own training; that contamination is unobservable from inside this repository, so the report must name the model's provenance and every known data-coverage limitation, and label the residual risk `unverified`. (2) Geographic and temporal isolation cannot separate physics from culture, regulation, and infrastructure that co-vary with them. (3) A passing split bounds fragility on the sampled axes; it is a lower bound on generalization, never a proof. Reports must include this paragraph's substance in their limitations, not only a reference to it.

## 3. Metrics

Notation: `N` cases; `d_i` is the geodesic distance from `l_i` to `R_i`, zero when `l_i ∈ R_i`; `y_i = 1[l_i ∈ R_i]`; area `A_i`; a case is answered unless the record says `abstained`.

| Metric | Exact definition | Reporting format |
|---|---|---|
| Localization error distribution | `d_i` over answered cases; abstentions excluded here and counted in coverage and selective curves | `n`, median, IQR (p25–p75), p90, p95, p99, max, histogram bin edges and counts; paired per-case differences against each baseline with bootstrap CI; never a mean alone |
| Candidate-region coverage | `coverage@A = \|{i : d_i = 0, A_i ≤ A}\| / N_total`; abstentions are misses; also report an answered-only variant, explicitly labeled | Curve over `A ∈ {0.1, 1, 10, 100, 1000}` km²; area-at-coverage for coverage 0.5 and 0.8; `N_total` stated |
| Calibration | Reliability diagram over region probabilities `p_i` with outcome `y_i`; equal-width and equal-count binning both reported; `ECE = Σ_b (n_b/N) · \|acc_b − conf_b\|` | Diagram data table (bin, n, mean confidence, empirical accuracy, Wilson CI), ECE with bootstrap CI, N and binning rule; Brier score optional |
| Selective risk / coverage | Order cases by the stated confidence score; coverage `c = answered/N`; risk is the error rate among answered at the reported operating point, with both error definitions labeled: region miss, and `d_i > A` at tolerance `A` | Risk–coverage curve at `c ∈ {0.1, …, 1.0}`, area under the curve, and risk at preregistered operating coverage(s); abstention reason distribution |
| False-positive rate at claimed precision | Claim set `C_p` = answered cases whose record states confidence `≥ p`; observed precision `= \|{i ∈ C_p : y_i}\| / \|C_p\|` with Clopper–Pearson CI; `FPR = 1 − observed precision` on that claim set. Separately, null-case FPR = fraction of negative cases where any claim is asserted at `p` | Confusion counts per claim level, precision claim vs. observed precision with CI, null-case FPR; no rate without its denominator |
| Constraint-residual distribution | Per constraint `c` and case `i`: raw residual `r_ic` and normalized `z_ic = r_ic / σ_ic`; joint statistic per verification | Per-constraint median, IQR, p90, p99, `P(\|z\| > 3)`, joint statistic; stratified by `y_i` (true states should fit better) and by inferencer version |
| Correlated-evidence overconfidence | Paired-evidence cases built per §5; `ΔECE = ECE_paired − ECE_singleton` at matched coverage; confidence inflation `= mean stated confidence − empirical accuracy` | ΔECE with CI, inflation for paired vs. singleton, naive vs. independence-aware aggregation side by side; paired-case count |
| Replay determinism | Fraction of reruns whose canonical run-record digest equals the original under identical inputs, code, and environment | `matches / N_replay`; each mismatch classified as data, model, software, environment, or unresolved nondeterminism, with both digests |

**Uncertainty and aggregation.** Confidence intervals use a bootstrap clustered by physical event and by location cell, not by case, because cases from one event or one site are not independent; the number of clusters is reported alongside `n`. Metrics that are ratios (coverage, FPR, precision) also report the denominator. All comparisons are paired per case on the same case set, and the pairing is stated. When a metric is undefined for a split (for example no negatives), the report writes `undefined` with the reason rather than zero.

**Scores and probabilities.** A score may order cases for selective curves, but any metric named calibration consumes a stated probability, and the mapping from score to probability is part of the method under test, not of the evaluation. Region probabilities are probabilities that the true location lies in the reported region, not confidence in the candidate's existence.

Two rules apply across the table. Metrics are computed per split and reported per split; a pooled number may appear only alongside the per-split results, never instead of them. Every cell carries `n` and a CI; a metric without an interval is a point estimate in disguise and is not reportable for a decision.

### 3.1 Metric set per experiment

| Step | Primary metric | Required companions | Not allowed |
|---|---|---|---|
| E0 synthetic | parameter-recovery error for `f0`, speed, closest-approach time and distance, against a tolerance declared before the run | success rate; identifiability analysis (parameter correlation, profile-likelihood flatness, Fisher information); residual RMS; failure thresholds for acceleration mismatch, clock offset (ppm), window length | any location claim; any coverage figure |
| E1 real controlled | discrimination of true events from wrong candidate explanations at a fixed operating point | true/false positives, abstentions with reasons, residuals by class, calibration of the stated decision confidence, null-case FPR | geographic accuracy claims |
| E2 locked | area-bounded `Coverage@A` (abstentions as misses) | region-area distribution, abstention rate and reasons, reliability/ECE, selective risk/coverage, paired B0–B3 comparison, replay determinism | pooled across splits; point-error-only reporting |

`Coverage@A` is the primary metric **only for E2**, where a region is the output. Binding coverage to a preregistered area cap `A` is what prevents a whole-Earth prediction from scoring well. E0 and E1 must not be reported in coverage terms: their metrics answer estimator and discrimination questions, and substituting one metric family for another is a category error, not a simplification.

## 4. Baselines and win declaration

Baselines are fixed at preregistration and share the same inputs, splits, abstention policy, and run pipeline. Any privilege difference must be stated; if it cannot be removed, it must be estimated as a separate ablation.

| ID | Baseline | Definition |
|---|---|---|
| B0 | Global prior | Base rate over region and time; no observation features |
| B1 | Learned unimodal | Frozen pretrained features with a nonparametric or linear head fitted on the tuning split only; no backbone training |
| B2 | Physics-only | The modality's physical constraint with B0 as the spatial prior; no learned score |
| B3 | Combined | B1 and B2 under the independence-aware aggregation rule |

**Win declaration.** Exactly one primary metric is preregistered with its direction and operating point (for example: median localization error, or coverage at a fixed area with a calibration guard). A win requires all of: the paired point estimate of the improvement over the best baseline is at least the preregistered margin `δ`; the 95% paired-bootstrap CI lower bound on that improvement exceeds zero; the calibration guard holds (`ECE_combined − ECE_baseline ≤ ε`); and replay determinism is 100% on the report's run set. `δ` is expressed in the primary metric's own units and must be operationally meaningful against the region grid, not merely statistically detectable. `ε` is likewise preregistered; a margin in accuracy bought with worse calibration is a loss. **`δ` and `ε` are deliberately not fixed by this document**: they are chosen at the E2 preregistration, derived from the power calculation and the region grid's operational resolution, and frozen before the sealed split is opened ([ADR 0010](../decisions/0010-m1-identifiability-program.md) §4). A margin chosen before the experiment design exists would be a number selected to be met.

**Sample size.** For a paired metric with per-case difference standard deviation `σ_d`, the target is `n ≥ (z_{1−α/2} + z_{1−β})² · σ_d² / δ²`. `σ_d` comes from pilot data or a small labeled pilot split; if neither exists, the report states the assumed value and labels the power calculation `assumed`, not `measured`. Each split needs enough cases for the coarsest metric's CI target; per-stratum shortfalls are reported as shortfalls. An underpowered comparison is reported as **inconclusive**, not as a negative result and not as a win.

**External claims.** A number taken from outside this repository is labeled `external claim`, cited with its source, and excluded from baseline tables and win decisions until it is reproduced here with a run record. A reproduced external result is labeled `measured` and cites both the reproduction and the original claim.

**Ties.** A comparison whose interval includes zero, or whose point estimate falls short of `δ` but whose interval overlaps it, is reported as **inconclusive**. It is not reported as "no worse", not as a win, and not retroactively relabeled after additional splits.

**Multiple comparisons.** One primary metric, no exceptions. Secondary metrics form a preregistered family `K` and are reported with Holm–Bonferroni-adjusted intervals at family `α = 0.05`. Splits are analyzed separately and not merged into a favorable pool. Any comparison not in the preregistration is labeled exploratory, reported without a decision role, and may not be used to declare a win. If the primary is rerun for any reason, the rerun and its reason are reported together.

## 5. Correlated-evidence protocol

Correlated evidence inflates confidence when one physical event contributes several apparent votes. It is the failure mode most likely to produce plausible nonsense, and it is tested, not assumed away.

1. **Identification.** The evidence graph records an `independence_key` per evidence item, derived from source, event identity, sensor path, and derivation lineage. Two items with the same key are one physical event and count once.
2. **Latent correlation.** Where the key is unknown, estimate dependence from residuals: condition on the claimed state, compute cross-item residual correlation, and run a permutation test over case labels. A pair whose residual correlation exceeds the preregistered threshold is flagged and handled conservatively.
3. **Aggregation.** The default combination is covariance-aware or equivalent-sample-size weighted. Naive multiplication of likelihoods across items sharing a key is a contract violation. A conservative rule — treat the correlated cluster as its single most informative member — is the fallback when the dependence structure is unknown.
4. **Paired-case construction.** From single physical events with multiple independently licensed observations (two sensors, two segments, two artifacts of one overflight), build paired cases where the two items are the same event. Ground truth is shared. A matched singleton set is built from events with one observation, balanced on geography, time, and difficulty where possible.
5. **Measurement.** Run naive aggregation and independence-aware aggregation on the same paired cases, plus the singleton control. Report ΔECE, confidence inflation, coverage, and risk at matched coverage. The naive run is expected to be miscalibrated; if it is not, the test lacks power and the protocol has failed, not passed.
6. **Passing.** Independence-aware aggregation shows no inflation beyond the preregistered tolerance and no degradation of ECE relative to the singleton control, at matched coverage. The paired-case count and the observed naive failure are reported. A failure blocks any cross-modal capability claim in that milestone and is recorded as an open unknown, not deleted.
7. **Enforcement.** The aggregation rule and its version are recorded in the run record. A run whose evidence graph violates the independence-key or aggregation contract fails validation and is reported as a contract failure, not as a model result.

The protocol, thresholds, and paired-case construction are fixed in the preregistration before the test split is opened. Retuning the test after seeing paired results is a changed experiment and requires a new preregistration and a new test set.

## 6. Reporting template

Reports live at `docs/experiments/YYYY-MM-DD-<slug>.md` and follow the skeleton in `docs/experiments/README.md`. The structure below is the evaluation-critical content that skeleton must carry: the index's Question and Preregistered expectation map to this template's Claim and Decision rule, and the remaining sections are mandatory expansions. The filled report's single H1 is its experiment id and claim; the skeleton marks it in bold so that copying the block does not add a second heading. Empty sections must say why they are empty; deleting a section is not permitted.

```markdown
**Experiment <experiment-id> — <claim in one line>**

**Status:** draft · **Preregistration:** <commit id, file sha256> · **Report version:** <n>
**Claim:** <one falsifiable sentence, including the population and split>
**Decision rule:** <primary metric, δ, ε, α, power, from the preregistration>

## Data snapshot
<table per source: license, version, retrieval date, subset definition, sha256, sensitivity tier>
<splits: construction, case counts, dedup counts, seal hash>

## Code and environment
<commit/tag, container or Nix digest, toolchain versions, lockfile hash, seeds, hardware, timezone>

## Results
<table: split × baseline × metric: n, point estimate, CI, and the primary comparison>
<per-metric plates required by §3: error distribution, coverage curve, reliability diagram, risk-coverage, FPR, residuals>

## Correlated evidence
<paired-case count, naive vs aware ΔECE and inflation, protocol outcome>

## Replay
<matches/N, digests, mismatch classification>

## Failure gallery
<case class, count, representative artifact id, diagnosis> — no cherry-picked single examples

## Limitations
<data ceilings, split limits per §2, model provenance, unverified items, what this does not prove>

## Decision
<proceed / pivot / stop per ROADMAP §8, with the rule that produced it>
**Artifacts:** <run-record ids, metric JSON, figures, code path>
```

## 7. Reproducibility requirements

- **Hashes.** Every raw input is content-addressed (SHA-256) at ingest; every derived artifact carries its parents' digests. The data snapshot is a manifest: source, version, retrieval time, license, subset definition, transform hash, and checksum per object.
- **Data.** Data is never committed (workspace rule); runs reference immutable snapshot ids. If a license forbids redistributing derived features, the report publishes hashes and aggregate statistics and states the access condition.
- **Environment.** Report OS and architecture, toolchain versions, lockfile hashes, container or environment digest, BLAS and thread-count settings, locale and timezone, and any declared nondeterminism (sampling, parallel reductions, GPU kernels). A run that cannot name its environment is not reproducible.
- **Seeds.** Every stochastic step takes an explicit seed recorded in the run record. Seed sweeps report all seeds, not the best one; the primary result is the preregistered seed policy, not a chosen seed.
- **Artifacts.** Retain run records, per-case predictions, metric JSON, figures, and logs for every reported number; regenerate report tables from these artifacts rather than typing them. Retention follows the data-governance policy; audits keep references and hashes, not observation content.
- **Replay.** Each report states the replay command and the digest equality rate. A reported number that cannot be regenerated from a recorded run is withdrawn in a corrected report.
- **Redaction.** Sensitive source content, ground-truth coordinates finer than the recorded sensitivity tier, and authorization identifiers are withheld from published artifacts under the data-governance policy; the report states what was withheld and why it does not change the measured claim.
- **Retention.** Run records and metric artifacts outlive the report. Raw observations are retained only where the license permits; otherwise they are referenced by snapshot id and hash, so the claim stays checkable without redistributing the source.

## 8. Preregistration, reports, and where they live

The preregistration is written before the test split is unsealed and, per the experiments index, lives in the report file in its `pre-registered` state. It contains: hypothesis, primary metric and direction, `δ`, `ε`, `α`, power target, expected effect and its basis, splits and their construction, exclusions, baselines, ablations, aggregation rules, stopping rule, analysis-code commit, and the exact decision rule. That state is committed before unsealing; the commit id, the file's SHA-256, and the sealed test-split manifest hash are recorded in the final report. Once unsealed, preregistered content is not edited: deviations are appended under their own heading with dates and reasons, and the final report names the preregistration commit. A report whose preregistration cannot be shown to precede the run is not a preregistered experiment and cannot support a win.

Paths, fixed by the experiments index: reports at `docs/experiments/YYYY-MM-DD-<slug>.md`, one report per experiment; artifacts referenced by hash and never committed. A report is immutable once its status is complete; a correction is a new dated report that cites the original and is indexed as its own record. Negative and inconclusive results follow the same path and the same template.

## 9. Anti-patterns

| Anti-pattern | Why it is invalid | Required alternative |
|---|---|---|
| Mean-only reporting | Hides the tail that determines whether a claim is useful | Full distribution per §3 |
| Tuning on the test split | Converts a test into a tuning set; the report becomes unfalsifiable | Preregistered split roles; retune only on tuning |
| Silently dropping abstentions | Inflates accuracy by hiding hard cases | Abstentions are misses in coverage and points on selective curves |
| Best-of-N reporting | Reports a maximum over runs, not the system's behavior | Pre-registered seed/run policy; report all runs or their aggregate |
| Point-estimate maps | Contradicts the output contract and hides uncertainty | Region maps with probability and residuals |
| Pooling splits | Lets an easy region mask failure in a hard one | Per-split results, pooled only alongside |
| Post-hoc metric changes | Manufactures a win after seeing data | Preregistered primary; changed metric = new experiment |
| Reusing the test set for ablations | Exhausts the test budget and contaminates it | Ablations on tuning; test opened once per report |
| Relative-only improvements | "X% better" without absolute distribution is uninterpretable | Absolute error, coverage, and calibration alongside |
| Case study as capability | Anecdotes do not estimate generalization or tails | Label as case study; capability only from split-scored reports |
| Unpaired baseline comparison | Adds variance and hides the treatment effect | Paired per-case differences with CI |
| ECE without reliability diagram | Scalar ECE hides bin-level miscalibration | Diagram data table plus ECE |
| Confidence from correlated evidence | One physical event counted as several votes | Independence-aware aggregation per §5 |
| Notebook-only results | Cannot be replayed; numbers are untraceable | Run records and committed analysis code |

## 10. Research metrics vs publication metrics

Two metric sets are computed separately and labeled in every report.

- **Research metrics** are computed inside an authorized node and may use fine-grained ground truth to diagnose failure modes, identifiability, residual structure, and calibration. They are not publication outputs.
- **Publication metrics** are the subset released under the sensitivity and granularity policy ([ethics](../policy/ethics-and-privacy.md), [ADR 0011](../decisions/0011-privacy-forensics-and-publication-rulings.md)): aggregate distributions, coarse regions, hashes, and stated conditions. A research metric does not become a publishable claim by being statistically significant.

The report states which numbers are research-only, which are published, and what was withheld; a published claim that cannot be reproduced at published granularity is labeled as such rather than silently upgraded.
