# C2 repair paired evaluation

Primary environment: `env0` (1 env), protocol `b61db06d81b473798693446b0d08d6769c1ddbf25a0f432e43789ff1523cbb16`, grid `pr4e-c2c-v1`, frozen grid `2978c8b24d0ef1bd3b787f13f68431230720154a288575a41067c8ad4c26eeaf`
Candidates: B0, B1, B2, B3; paired comparisons are against B0 on identical trial identities. No pooled percentage is presented without its mechanism and geometry strata.

## Primary endpoint (pre-declared)

- Name: **correct_cv_supported_coverage_and_detection_B1_vs_B0**
- Definition (verbatim): On identical paired sealed-grid observations, B1 vs B0: increase correct-CV valid supported coverage (equivalently reduce correct-CV false rejection) without losing acceleration discrepancy detection beyond the pre-registered bound. Supported coverage is the fraction of truth-correct correct-CV trials whose candidate record is validly supported by the frozen C1 claim gate.
- Candidate comparison (verbatim): B1 vs B0 (paired on the same observation; B0 is the paired baseline)
- Decision rule (verbatim): `B1 primary confirmation requires all of: (1) paired false-rejection risk difference (B1-B0) < 0; (2) paired valid supported coverage increases (B1 > B0); (3) zero claim-integrity violations for B1 (all claim statuses within {supported_conditional, undetermined, contradicted}; no supported_invariant); (4) the detection non-inferiority rule below holds. The evaluator numeric primary_result checks (1) and (4); (2) and (3) are mandatory pre-declared guardrails reported as secondary metrics and must both hold for confirmation.`
- Detection non-inferiority rule (verbatim): `Paired acceleration discrepancy-detected risk difference (B1-B0) >= -0.10 (detection_loss_bound), under undecided_policy=not_detected: an undetermined acceleration trial is not counted as detected. The alternative excluded-policy analysis is a reported sensitivity, not the primary rule.`
- Candidate/baseline: B1 vs B0; detection-loss bound: 0.1; undecided policy: not_detected
- Primary result: **pass**
- Criteria: primary metric improved = True; detection non-inferior = True; primary delta = 0.6831; detection delta = 0.0000.
- Undecided-policy sensitivity (excluded): result pass, primary delta 0.6831, detection delta 0.0000; criteria {'primary_metric': 'supported_coverage', 'primary_improved': True, 'false_rejection_improved': None, 'supported_coverage_improved': True, 'detection_non_inferior': True, 'primary_delta': 0.6830985915492958, 'frr_delta': None, 'detection_delta': 0.0, 'detection_loss_bound': 0.1}.

## Supported coverage (secondary)

Coverage = (truth-correct correct-model trials with valid support) / all correct-model trials. Valid support is explicit or derived from claim statuses plus the C1 gate; adequacy accept alone is never used.

| Candidate | Supported coverage | Support basis counts |
|---|---|---|
| B0 | 44/426 (0.1033) | claim_statuses_gate=426 |
| B1 | 335/426 (0.7864) | claim_statuses_gate=426 |
| B2 | 102/426 (0.2394) | claim_statuses_gate=426 |
| B3 | 176/426 (0.4131) | claim_statuses_gate=426 |

## Rate intervals (secondary)

| Candidate | Supported coverage [Wilson 95%] | FRR [Wilson 95%] | Detection [Wilson 95%] | Valid retention [Wilson 95%] | Abstention [Wilson 95%] |
|---|---|---|---|---|---|
| B0 | 0.1033 [0.0778, 0.1358] | 0.6847 [0.6380, 0.7280] | 0.7500 [0.6656, 0.8189] | 0.2365 [0.1977, 0.2801] | 0.1095 [0.0864, 0.1380] |
| B1 | 0.7864 [0.7450, 0.8227] | 0.0197 [0.0100, 0.0384] | 0.7500 [0.6656, 0.8189] | 0.9729 [0.9521, 0.9848] | 0.0583 [0.0418, 0.0807] |
| B2 | 0.2394 [0.2014, 0.2822] | 0.3399 [0.2955, 0.3873] | 0.7500 [0.6656, 0.8189] | 0.5493 [0.5006, 0.5970] | 0.1466 [0.1199, 0.1782] |
| B3 | 0.4131 [0.3674, 0.4605] | 0.1429 [0.1122, 0.1802] | 0.7500 [0.6656, 0.8189] | 0.7537 [0.7095, 0.7931] | 0.1272 [0.1022, 0.1572] |

## Misspecification taxonomy (secondary)

Acceleration trials split exclusively into discrepancy_detected, undetermined, false_supported and rejected_without_discrepancy; undetermined is never detection.

| Candidate | N | discrepancy_detected | undetermined | false_supported | rejected_without_discrepancy |
|---|---:|---|---|---|---|
| B0 | 120 | 90 (0.7500 [0.6656, 0.8189]) | 30 (0.2500 [0.1811, 0.3344]) | 0 (0.0000 [0.0000, 0.0310]) | 0 (0.0000 [0.0000, 0.0310]) |
| B1 | 120 | 90 (0.7500 [0.6656, 0.8189]) | 30 (0.2500 [0.1811, 0.3344]) | 0 (0.0000 [0.0000, 0.0310]) | 0 (0.0000 [0.0000, 0.0310]) |
| B2 | 120 | 90 (0.7500 [0.6656, 0.8189]) | 30 (0.2500 [0.1811, 0.3344]) | 0 (0.0000 [0.0000, 0.0310]) | 0 (0.0000 [0.0000, 0.0310]) |
| B3 | 120 | 90 (0.7500 [0.6656, 0.8189]) | 30 (0.2500 [0.1811, 0.3344]) | 0 (0.0000 [0.0000, 0.0310]) | 0 (0.0000 [0.0000, 0.0310]) |

## Null/noise-only promotions (secondary)

| Candidate | N | accepted | validly supported | false_supported | Wilson 95% |
|---|---:|---:|---:|---:|---|
| B0 | 20 | 0 | 0 | 0 | [0.0000, 0.1611] |
| B1 | 20 | 0 | 0 | 0 | [0.0000, 0.1611] |
| B2 | 20 | 0 | 0 | 0 | [0.0000, 0.1611] |
| B3 | 20 | 0 | 0 | 0 | [0.0000, 0.1611] |

## Per-chirp-bin power (secondary)

Bins use the runtime-observable estimated_chirp_rate supplied by the artifact. Bins lacking acceleration samples are flagged; paired Bx-B0 comparisons are reported per bin and mechanism.

| Bin | Candidate | CV N | CV FRR | Accel N | Accel detection | No accel samples |
|---|---|---:|---|---:|---|---|
| chirp_lt_50 | B0 | 232 | 152/212 (0.7170) | 60 | 60/60 (1.0000) | False |
| chirp_lt_50 | B1 | 232 | 0/212 (0.0000) | 60 | 60/60 (1.0000) | False |
| chirp_lt_50 | B2 | 232 | 42/212 (0.1981) | 60 | 60/60 (1.0000) | False |
| chirp_lt_50 | B3 | 232 | 0/212 (0.0000) | 60 | 60/60 (1.0000) | False |
| chirp_50_150 | B0 | 66 | 49/66 (0.7424) | 30 | 30/30 (1.0000) | False |
| chirp_50_150 | B1 | 66 | 0/66 (0.0000) | 30 | 30/30 (1.0000) | False |
| chirp_50_150 | B2 | 66 | 49/66 (0.7424) | 30 | 30/30 (1.0000) | False |
| chirp_50_150 | B3 | 66 | 30/66 (0.4545) | 30 | 30/30 (1.0000) | False |
| chirp_150_400 | B0 | 82 | 47/82 (0.5732) | 30 | 0/30 (0.0000) | False |
| chirp_150_400 | B1 | 82 | 8/82 (0.0976) | 30 | 0/30 (0.0000) | False |
| chirp_150_400 | B2 | 82 | 27/82 (0.3293) | 30 | 0/30 (0.0000) | False |
| chirp_150_400 | B3 | 82 | 28/82 (0.3415) | 30 | 0/30 (0.0000) | False |
| chirp_ge_400 | B0 | 46 | 30/46 (0.6522) | 0 | 0/0 (n/a) | True |
| chirp_ge_400 | B1 | 46 | 0/46 (0.0000) | 0 | 0/0 (n/a) | True |
| chirp_ge_400 | B2 | 46 | 20/46 (0.4348) | 0 | 0/0 (n/a) | True |
| chirp_ge_400 | B3 | 46 | 0/46 (0.0000) | 0 | 0/0 (n/a) | True |

- Bins without acceleration samples: chirp_ge_400.
- Trials missing estimated_chirp_rate: 0.

SNR conditioning verified: **False** (unverified); artifact does not declare more than one estimated-SNR bin with samples.

## Per-candidate summary (secondary, primary environment)

| Candidate | N | Accepted | Correct accepted | Supported coverage | FRR | Detection | Valid retention | Abstention | Claim-integrity violations |
|---|---:|---:|---:|---|---|---|---|---|---:|
| B0 | 566 | 96 | 96 | 44/426 (0.1033) | 278/406 (0.6847) | 90/120 (0.7500) | 96/406 (0.2365) | 62/566 (0.1095) |
| B1 | 566 | 415 | 395 | 335/426 (0.7864) | 8/406 (0.0197) | 90/120 (0.7500) | 395/406 (0.9729) | 33/566 (0.0583) |
| B2 | 566 | 235 | 223 | 102/426 (0.2394) | 138/406 (0.3399) | 90/120 (0.7500) | 223/406 (0.5493) | 83/566 (0.1466) |
| B3 | 566 | 306 | 306 | 176/426 (0.4131) | 58/406 (0.1429) | 90/120 (0.7500) | 306/406 (0.7537) | 72/566 (0.1272) |

## Paired overall differences (secondary, Bx − B0)

| Candidate | Metric | Pairs | Baseline rate | Candidate rate | Difference | 95% interval | Discordant b/c |
|---|---|---:|---:|---:|---:|---|---|
| B1 | false_rejection | 406 | 0.6847 | 0.0197 | -0.6650 | [-0.7109, -0.6191] | 0/270 |
| B1 | detection | 120 | 0.7500 | 0.7500 | 0.0000 | [0.0000, 0.0000] | 0/0 |
| B1 | discrepancy_detection | 120 | 0.7500 | 0.7500 | 0.0000 | [0.0000, 0.0000] | 0/0 |
| B1 | valid_retention | 406 | 0.2365 | 0.9729 | 0.7365 | [0.6925, 0.7804] | 301/2 |
| B1 | abstention | 566 | 0.1095 | 0.0583 | -0.0512 | [-0.0707, -0.0318] | 2/31 |
| B2 | false_rejection | 406 | 0.6847 | 0.3399 | -0.3448 | [-0.3911, -0.2986] | 0/140 |
| B2 | detection | 120 | 0.7500 | 0.7500 | 0.0000 | [0.0000, 0.0000] | 0/0 |
| B2 | discrepancy_detection | 120 | 0.7500 | 0.7500 | 0.0000 | [0.0000, 0.0000] | 0/0 |
| B2 | valid_retention | 406 | 0.2365 | 0.5493 | 0.3128 | [0.2677, 0.3579] | 127/0 |
| B2 | abstention | 566 | 0.1095 | 0.1466 | 0.0371 | [0.0215, 0.0527] | 21/0 |
| B3 | false_rejection | 406 | 0.6847 | 0.1429 | -0.5419 | [-0.5908, -0.4929] | 1/221 |
| B3 | detection | 120 | 0.7500 | 0.7500 | 0.0000 | [0.0000, 0.0000] | 0/0 |
| B3 | discrepancy_detection | 120 | 0.7500 | 0.7500 | 0.0000 | [0.0000, 0.0000] | 0/0 |
| B3 | valid_retention | 406 | 0.2365 | 0.7537 | 0.5172 | [0.4677, 0.5668] | 212/2 |
| B3 | abstention | 566 | 0.1095 | 0.1272 | 0.0177 | [-0.0025, 0.0378] | 22/12 |

## Per-mechanism paired differences (secondary)

| Mechanism | Candidate | Metric | Pairs | Baseline rate | Candidate rate | Difference | 95% interval |
|---|---|---|---:|---:|---:|---:|---|
| acceleration | B1 | false_rejection | 0 | n/a | n/a | n/a | [n/a] |
| acceleration | B1 | detection | 120 | 0.7500 | 0.7500 | 0.0000 | [0.0000, 0.0000] |
| acceleration | B2 | false_rejection | 0 | n/a | n/a | n/a | [n/a] |
| acceleration | B2 | detection | 120 | 0.7500 | 0.7500 | 0.0000 | [0.0000, 0.0000] |
| acceleration | B3 | false_rejection | 0 | n/a | n/a | n/a | [n/a] |
| acceleration | B3 | detection | 120 | 0.7500 | 0.7500 | 0.0000 | [0.0000, 0.0000] |
| correct_cv | B1 | false_rejection | 406 | 0.6847 | 0.0197 | -0.6650 | [-0.7109, -0.6191] |
| correct_cv | B1 | detection | 0 | n/a | n/a | n/a | [n/a] |
| correct_cv | B2 | false_rejection | 406 | 0.6847 | 0.3399 | -0.3448 | [-0.3911, -0.2986] |
| correct_cv | B2 | detection | 0 | n/a | n/a | n/a | [n/a] |
| correct_cv | B3 | false_rejection | 406 | 0.6847 | 0.1429 | -0.5419 | [-0.5908, -0.4929] |
| correct_cv | B3 | detection | 0 | n/a | n/a | n/a | [n/a] |
| null | B1 | false_rejection | 0 | n/a | n/a | n/a | [n/a] |
| null | B1 | detection | 0 | n/a | n/a | n/a | [n/a] |
| null | B2 | false_rejection | 0 | n/a | n/a | n/a | [n/a] |
| null | B2 | detection | 0 | n/a | n/a | n/a | [n/a] |
| null | B3 | false_rejection | 0 | n/a | n/a | n/a | [n/a] |
| null | B3 | detection | 0 | n/a | n/a | n/a | [n/a] |

## Per-geometry continuum paired differences (secondary)

| Geometry bin | Candidate | Metric | Pairs | Baseline rate | Candidate rate | Difference | 95% interval |
|---|---|---|---:|---:|---:|---:|---|
| [0,200) | B1 | false_rejection | 92 | 0.5326 | 0.0870 | -0.4457 | [-0.5472, -0.3441] |
| [0,200) | B1 | detection | 0 | n/a | n/a | n/a | [n/a] |
| [0,200) | B2 | false_rejection | 92 | 0.5326 | 0.4239 | -0.1087 | [-0.1723, -0.0451] |
| [0,200) | B2 | detection | 0 | n/a | n/a | n/a | [n/a] |
| [0,200) | B3 | false_rejection | 92 | 0.5326 | 0.1957 | -0.3370 | [-0.4381, -0.2358] |
| [0,200) | B3 | detection | 0 | n/a | n/a | n/a | [n/a] |
| [200,400) | B1 | false_rejection | 30 | 1.0000 | 0.0000 | -1.0000 | [-1.0000, -1.0000] |
| [200,400) | B1 | detection | 0 | n/a | n/a | n/a | [n/a] |
| [200,400) | B2 | false_rejection | 30 | 1.0000 | 1.0000 | 0.0000 | [0.0000, 0.0000] |
| [200,400) | B2 | detection | 0 | n/a | n/a | n/a | [n/a] |
| [200,400) | B3 | false_rejection | 30 | 1.0000 | 0.3333 | -0.6667 | [-0.8354, -0.4980] |
| [200,400) | B3 | detection | 0 | n/a | n/a | n/a | [n/a] |
| [400,800) | B1 | false_rejection | 92 | 0.7500 | 0.0000 | -0.7500 | [-0.8385, -0.6615] |
| [400,800) | B1 | detection | 60 | 0.5000 | 0.5000 | 0.0000 | [0.0000, 0.0000] |
| [400,800) | B2 | false_rejection | 92 | 0.7500 | 0.4239 | -0.3261 | [-0.4219, -0.2303] |
| [400,800) | B2 | detection | 60 | 0.5000 | 0.5000 | 0.0000 | [0.0000, 0.0000] |
| [400,800) | B3 | false_rejection | 92 | 0.7500 | 0.2174 | -0.5326 | [-0.6346, -0.4307] |
| [400,800) | B3 | detection | 60 | 0.5000 | 0.5000 | 0.0000 | [0.0000, 0.0000] |
| [800,1600) | B1 | false_rejection | 60 | 1.0000 | 0.0000 | -1.0000 | [-1.0000, -1.0000] |
| [800,1600) | B1 | detection | 0 | n/a | n/a | n/a | [n/a] |
| [800,1600) | B2 | false_rejection | 60 | 1.0000 | 0.5000 | -0.5000 | [-0.6265, -0.3735] |
| [800,1600) | B2 | detection | 0 | n/a | n/a | n/a | [n/a] |
| [800,1600) | B3 | false_rejection | 60 | 1.0000 | 0.1667 | -0.8333 | [-0.9276, -0.7390] |
| [800,1600) | B3 | detection | 0 | n/a | n/a | n/a | [n/a] |
| [1600,3200) | B1 | false_rejection | 30 | 0.6667 | 0.0000 | -0.6667 | [-0.8354, -0.4980] |
| [1600,3200) | B1 | detection | 60 | 1.0000 | 1.0000 | 0.0000 | [0.0000, 0.0000] |
| [1600,3200) | B2 | false_rejection | 30 | 0.6667 | 0.0000 | -0.6667 | [-0.8354, -0.4980] |
| [1600,3200) | B2 | detection | 60 | 1.0000 | 1.0000 | 0.0000 | [0.0000, 0.0000] |
| [1600,3200) | B3 | false_rejection | 30 | 0.6667 | 0.0000 | -0.6667 | [-0.8354, -0.4980] |
| [1600,3200) | B3 | detection | 60 | 1.0000 | 1.0000 | 0.0000 | [0.0000, 0.0000] |
| [3200,6400) | B1 | false_rejection | 82 | 0.3659 | 0.0000 | -0.3659 | [-0.4701, -0.2616] |
| [3200,6400) | B1 | detection | 0 | n/a | n/a | n/a | [n/a] |
| [3200,6400) | B2 | false_rejection | 82 | 0.3659 | 0.0000 | -0.3659 | [-0.4701, -0.2616] |
| [3200,6400) | B2 | detection | 0 | n/a | n/a | n/a | [n/a] |
| [3200,6400) | B3 | false_rejection | 82 | 0.3659 | 0.0000 | -0.3659 | [-0.4701, -0.2616] |
| [3200,6400) | B3 | detection | 0 | n/a | n/a | n/a | [n/a] |
| [6400,12800) | B1 | false_rejection | 20 | 1.0000 | 0.0000 | -1.0000 | [-1.0000, -1.0000] |
| [6400,12800) | B1 | detection | 0 | n/a | n/a | n/a | [n/a] |
| [6400,12800) | B2 | false_rejection | 20 | 1.0000 | 0.0000 | -1.0000 | [-1.0000, -1.0000] |
| [6400,12800) | B2 | detection | 0 | n/a | n/a | n/a | [n/a] |
| [6400,12800) | B3 | false_rejection | 20 | 1.0000 | 0.0000 | -1.0000 | [-1.0000, -1.0000] |
| [6400,12800) | B3 | detection | 0 | n/a | n/a | n/a | [n/a] |
| [12800,inf) | B1 | false_rejection | 0 | n/a | n/a | n/a | [n/a] |
| [12800,inf) | B1 | detection | 0 | n/a | n/a | n/a | [n/a] |
| [12800,inf) | B2 | false_rejection | 0 | n/a | n/a | n/a | [n/a] |
| [12800,inf) | B2 | detection | 0 | n/a | n/a | n/a | [n/a] |
| [12800,inf) | B3 | false_rejection | 0 | n/a | n/a | n/a | [n/a] |
| [12800,inf) | B3 | detection | 0 | n/a | n/a | n/a | [n/a] |

## Claim integrity

C1 gate allowed claim statuses: contradicted, supported_conditional, undetermined. Any `supported_invariant` or unknown status is flagged below and is not silently accepted.

| Candidate | Status | Violations | supported_invariant count |
|---|---|---:|---:|
| B0 | ok | 0 | 0 |
| B1 | ok | 0 | 0 |
| B2 | ok | 0 | 0 |
| B3 | ok | 0 | 0 |

## Negative-result statement

At least one candidate has a lower false-rejection rate, no point-estimate detection loss, and no abstention-gaming pattern versus B0 in the primary environment: B1, B2, B3. This is a point-estimate summary only; use the paired intervals and stratified tables before drawing conclusions.

- Qualifying candidates: B1, B2, B3.
- FRR-gain candidates: B1, B2, B3; detection-loss candidates: none; abstention-gaming candidates: none.

## Cross-environment claim-status agreement

Environments: env0. Missing trials and status differences are reported; no equality is forced.

| Candidate | Claim | Compared | Agree | Disagree | Missing | Agreement |
|---|---|---:|---:|---:|---:|---:|
| B0 | v | 566 | 566 | 0 | 0 | 1.0000 |
| B0 | f0_times_b | 566 | 566 | 0 | 0 | 1.0000 |
| B0 | t0 | 566 | 566 | 0 | 0 | 1.0000 |
| B1 | v | 566 | 566 | 0 | 0 | 1.0000 |
| B1 | f0_times_b | 566 | 566 | 0 | 0 | 1.0000 |
| B1 | t0 | 566 | 566 | 0 | 0 | 1.0000 |
| B2 | v | 566 | 566 | 0 | 0 | 1.0000 |
| B2 | f0_times_b | 566 | 566 | 0 | 0 | 1.0000 |
| B2 | t0 | 566 | 566 | 0 | 0 | 1.0000 |
| B3 | v | 566 | 566 | 0 | 0 | 1.0000 |
| B3 | f0_times_b | 566 | 566 | 0 | 0 | 1.0000 |
| B3 | t0 | 566 | 566 | 0 | 0 | 1.0000 |

## Contract gaps

- The c2-repair contract has no `validly_supported` field; the evaluator supports it but otherwise derives support from claim_statuses plus the C1 gate. The method should declare support semantics explicitly for a sealed artifact.
- The contract has no `primary_metric` field. The evaluator reads the optional `primary_metric` if present, otherwise infers it from the natural-language definition/decision rule; the machine-evaluable primary metric should be explicit.
- The primary_endpoint fields are natural-language strings. The evaluator prints them verbatim but can only apply its documented canonical rule (primary metric improvement plus detection non-inferiority within detection_loss_bound).
- `detection_loss_bound` has no declared unit or estimation method (rate difference versus percentage points); the evaluator treats it as an absolute rate difference.
- The artifact contract does not declare the alternative undecided policy for the sensitivity check; the evaluator uses the other of {not_detected, excluded}.
- The contract does not supply `estimated_chirp_rate`, `chirp_bins`, `estimated_snr_db` or `snr_bins`; per-chirp-bin power and SNR conditioning are unavailable or unverified when these are absent.
- Null/noise-only mechanism labels are not enumerated; the evaluator groups mechanisms whose lower-case name contains `null` or `noise`.
- The misspecification taxonomy is derived from decision + adequacy_status; the artifact has no explicit taxonomy field or rule id.

## Limitations

- Paired risk differences are descriptive point estimates with a documented paired Wald 95% interval, not a Newcombe interval and not a hypothesis test. Intervals do not account for repeated seeds, shared noise realizations beyond the pairing, or multiple comparisons.
- The evaluator consumes artifacts only. It cannot verify that candidates used only runtime-observable quantities (B3 leakage), that observations were truly identical across candidates, or that the artifact's protocol was frozen before opening.
- Correctness labels come from `evaluation_only.estimate_within_tolerance`; truth is synthetic truth from the artifact, not physical correctness.
- The primary environment is the first supplied artifact. Cross-environment claim agreement is reported descriptively; equality is never forced and no pooled cross-environment rate is computed.
- FRR is defined only on truth-correct correct-CV cells; acceleration detection only on acceleration cells. Cells with no eligible trials report null rates, not zero.
- The negative-result flag uses point estimates (FRR gain with no point-estimate detection loss). The paired intervals and stratified tables must be read before any scientific conclusion; the evaluator makes no candidate recommendation.
- Claim integrity uses the C1 gate's currently allowed set (`supported_conditional`, `undetermined`, `contradicted`). Any `supported_invariant` or unknown status is flagged but not silently rewritten or accepted.
- A `--require-paired` run requires identical candidate lists and trial identities across environments; without it, missing cells are reported, not imputed.
