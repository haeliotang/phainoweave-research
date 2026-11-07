# C2-C sealed confirmation — B0–B3 on the 566-trial grid

**Status:** single valid sealed run completed under revision v3; pre-declared primary endpoint **passes for B1**, with a mandatory family-failure caveat (high-chirp acceleration detection is 0/30 for every candidate) · 2026-11-05 · **Manifest:** `protocols/c2c-freeze-v3.json` (`916a989d…`) · **Authority:** [ADR 0023](../decisions/0023-three-operations-and-sealed-protocol.md)

## 1. Run provenance and the two invalid attempts

| Attempt | Revision | Outcome |
|---|---|---|
| 1 | `c2c-freeze-v1` (`23ad3dd1…`) | **invalid execution failure**: committed grid v1 could not self-verify (digest computed before `selection_inputs_assertion`); no trial, no artifact, no retry |
| 2 | `c2c-freeze-v2` (`033fb262…`) | **invalid execution failure**: frozen runner executed via stdin, default multiprocessing spawn re-imported nonexistent `<stdin>`; `BrokenProcessPool`; no artifact, no retry |
| 3 | `c2c-freeze-v3` (`916a989d…`) | **valid single run**: serial stdin runner (`jobs=1`), 566 trials, artifact written |

Revision v3 changed only runner execution plumbing (jobs=1, output path, manifest path); candidate/evaluator/calibration/tolerance hashes and the primary endpoint were unchanged. Attempts 1 and 2 are recorded as invalid and were not reused; no run was selected or repeated for a better result.

Sealed run facts: grid `pr4e-c2c-v1` digest `2978c8b2…` (file sha `2f0005a1…`, 59 conditions / 566 trials / seed 60M); protocol digest `b61db06d…`; artifact `/tmp/c2c-sealed-v3/c2-repair.json` sha256 `641a1003…`; environment macOS arm64 / Python 3.14.0 / NumPy 2.4.4; `sealed_run_count = 1`.

## 2. Pre-declared primary endpoint: PASS for B1

On identical paired sealed observations, B1 vs B0:

| Criterion | Result |
|---|---|
| supported coverage B1 > B0 | 335/426 (0.7864) vs 44/426 (0.1033); delta **+0.6831** |
| paired FRR difference < 0 | 8/406 (0.0197) vs 278/406 (0.6847); delta **−0.6650** [−0.7109, −0.6191] |
| detection non-inferiority (B1−B0 ≥ −0.10) | 90/120 vs 90/120; delta **0.0000** [0.0000, 0.0000] |
| claim-integrity violations | **0** (no `supported_invariant`; statuses within the frozen gate) |
| coverage difference 95% interval lower bound > 0 | pass |

Evaluator primary result: **pass**; undecided-policy sensitivity (excluded) also pass with the same deltas.

## 3. Secondary results

| Candidate | Supported coverage | FRR | Detection | Valid retention | Abstention |
|---|---:|---:|---:|---:|---:|
| B0 | 44/426 (0.103) | 278/406 (0.685) | 90/120 (0.750) | 96/406 (0.237) | 62/566 (0.110) |
| **B1** | **335/426 (0.786)** | **8/406 (0.020)** | 90/120 (0.750) | 395/406 (0.973) | 33/566 (0.058) |
| B2 | 102/426 (0.239) | 138/406 (0.340) | 90/120 (0.750) | 223/406 (0.549) | 83/566 (0.147) |
| B3 | 176/426 (0.413) | 58/406 (0.143) | 90/120 (0.750) | 306/406 (0.754) | 72/566 (0.127) |

- B1's high-chirp FRR is 8/128 (6.2%), not zero. Supported coverage is 78.6%, not 100%: 8 correct trials are rejected and the claim gate withholds support on others.
- B2 remains partial (FRR 34.0%); B3 is decision calibration (FRR 14.3%) and is not a measurement repair.
- Null/noise-only: 0/20 accepted or supported for every candidate.
- SNR conditioning: unverified (the artifact does not declare more than one estimated-SNR bin with samples); the 60 dB clip saturation noted pre-seal persists.

## 4. Mandatory family-failure caveat: high-chirp acceleration detection is 0/30 for all candidates

| Chirp bin (Hz/s) | CV FRR (B0 / B1) | Accel detection (B0 / B1) |
|---|---|---|
| <50 | 152/212 / **0/212** | 60/60 / 60/60 |
| 50–150 | 49/66 / **0/66** | 30/30 / 30/30 |
| **150–400** | 47/82 / **8/82** | **0/30 / 0/30** (all undetermined) |
| ≥400 | 30/46 / **0/46** | no acceleration samples |

The aggregate 90/120 (75%) hides it: in the 150–400 Hz/s band, **every candidate fails to detect acceleration** (all 30 trials undetermined), exactly the family failure flagged in the pre-seal B3 analysis. The primary endpoint's detection non-inferiority is satisfied relative to B0, but B0 also has no detection capability there. This is a **capability limit of the frequency representation in that chirp band**, not a B1 regression; B1 improves correct-model retention but does not fix it. The sealed confirmation therefore supports B1 as a measurement correction for correct-model adequacy, not as a solution to high-chirp misspecification detection.

## 5. Interpretation under the three operations

- **B1 — Measurement Correction:** confirmed on the pre-declared endpoint (coverage +0.68, FRR −0.665, detection not inferior, claim integrity). **Conditional:** the pre-seal time-block holdout flagged self-confirmation (improvement only in the fitted block, −1.9% held-out); the sealed grid is held-out with respect to candidate development, but B1's mechanism still uses the model's own prediction. The confirmation is therefore for the sealed protocol, not a general proof that de-chirp always improves measurement fidelity.
- **B3 — Decision Calibration:** FRR improvement without measurement change; high-chirp acceleration detection still 0/30. Not equivalent to B1.
- **M3 — Uncertainty Modelling:** separate result (conditional covariance, 2 held-out geometries); not part of this competition.
- The high-chirp acceleration failure is a **representation limit**; per ADR 0023 §F the program should not keep expanding synthetic front-end repair without E1.

## 5a. Three limits on interpreting this confirmation (post-review)

1. **The 0/30 high-chirp detection failure is a measured pipeline failure, not a proven physical or information-theoretic upper bound.** All candidates failing in that band points to a common deficiency in the current representation or decision gate, but the cause could be frequency extraction, parameter degeneracy, numeric gating, or the experimental conditions. Calling it a representation limit requires showing that a more complete observation still cannot identify the mismatch; that experiment has not been done.
2. **B1's time-block self-confirmation is unresolved.** The sealed grid demonstrates cross-trial (scenario) generalisation, not within-event prediction on blocks excluded from the de-chirp/motion estimation. The +134.8% in-block vs −1.9% held-out result must not be treated as cancelled by the sealed primary endpoint passing.
3. **The detection paired interval [0, 0] is not proof that future detection loss is zero.** 120 paired decisions being identical can yield a zero-width Wald interval; it does not exclude degradation under unobserved conditions. Future reports should use interval methods that reflect finite samples and condition clustering, and report the high-chirp family separately rather than relying on the aggregate.

These limits bound the claim: B1 passes the frozen synthetic endpoint conditionally; it does not establish real-world measurement reliability.

## 6. What is established and what is not

Established: under the frozen sealed protocol, B1 substantially improves correct-model supported coverage and false rejection while preserving aggregate acceleration detection and claim integrity; the sealed grid was opened once; the result is reproducible from the frozen manifest.

Not established: real-world measurement reliability (synthetic only); detection of acceleration in the 150–400 Hz/s band (0/30 for all) whether by representation limit or pipeline cause; SNR-conditioned behavior (unverified); cross-platform reproducibility of the sealed artifact (single environment); parameter correctness beyond the frozen truth tolerances; within-event out-of-block prediction for B1 (time-block self-confirmation unresolved); any finite-sample guarantee from the zero-width detection interval.

## 7. Decision

**B1 passes the pre-declared primary endpoint and is accepted as a conditional measurement-correction candidate.** The acceptance is bounded by §4 (high-chirp detection family failure), §5 (self-confirmation caveat), and the single-environment limitation. It is not promoted to "the measurement model is fixed"; B3 is not a measurement repair; the representation limit at high chirp remains an open scientific result.

Per ADR 0023 §F, further synthetic front-end expansion is not the next priority. The next gate is E1's controlled real observation with authorization, calibrated audio, independent motion measurement and affine clock anchors. C3/C4 remain tightly scoped.

## 8. Provenance

Manifest `protocols/c2c-freeze-v3.json` digest `916a989d…`; frozen grid `protocols/c2c-grid-v2.json` digest `2978c8b2…`; artifact `/tmp/c2c-sealed-v3/c2-repair.json` sha `641a1003…`; run record `/tmp/c2c-sealed-v3/run-record.json`; evaluator `/tmp/c2c-sealed-v3/eval/report.json` and `.md`. Invalid attempts: [`attempt 1 record`](2026-11-05-c2-sealed-attempt1.md) and attempt 2 (spawn failure, recorded in the v3 manifest `attempt_history`). No docs/CI/git edits were made by the runner; no retries.
