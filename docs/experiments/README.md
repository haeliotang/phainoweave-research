# Experiments

Pre-registered experiments and their reports. E0 (synthetic Doppler identifiability) landed 2026-11-04; the real-data steps E1/E2 follow ([ADR 0010](../decisions/0010-m1-identifiability-program.md)).

| Report | Step | Data class | Status |
|---|---|---|---|
| [2026-11-04-e0-synthetic-doppler.md](2026-11-04-e0-synthetic-doppler.md) | E0 | synthetic | complete; continue decision with four revisions |
| [2026-11-05-e1-preregistration-draft.md](2026-11-05-e1-preregistration-draft.md) | E1 | real controlled | draft for review; sealed only before the locked test |
| [2026-11-05-cross-platform-e0.md](2026-11-05-cross-platform-e0.md) | E0 reproduction | two platforms | measurement: R0 pass, R2 fail, R1-N established / R1-D not; three-environment addendum |
| [pr4c-plan.md](pr4c-plan.md) | PR-4c | diagnostics | convergence robustness and decision stability plan |
| [pr4d-plan.md](pr4d-plan.md) | PR-4d | diagnostics + locked validation | model adequacy layer and scientific decision utility plan |
| [2026-11-05-pr4d-adequacy-validation.md](2026-11-05-pr4d-adequacy-validation.md) | PR-4d result | synthetic locked | 240 detectable / 360 equivalence; strict zero accepted; conditional 83.4% retention / 23.1% absolute-truth error |
| [2026-11-05-pr4d-report-corrections.md](2026-11-05-pr4d-report-corrections.md) | PR-4d corrections | — | undefined strict FA ratio, sample-flow table, dual conditional error metrics (frozen report not edited) |
| [pr4e-plan.md](pr4e-plan.md) | PR-4e plan | claims + locked | identifiability contract first, geometry-aware adequacy, risk–coverage, precedence |
| [2026-11-05-c2-diagnosis.md](2026-11-05-c2-diagnosis.md) | C2 diagnosis | synthetic matrix | high-chirp rejection = front-end structural error; asymptotic LB null invalid (47x); no repair selected |
| [pr4e-c2-repair-plan.md](pr4e-c2-repair-plan.md) | C2 repair plan | measurement model | C2-A error model, C2-B noise-matched paths, C2-C frozen grid, B0–B3 independent comparison |
| [2026-11-05-c2-measurement-model.md](2026-11-05-c2-measurement-model.md) | C2-A/B/C result | synthetic measurement model | error is structural, not chirp-mean; white noise reproduces 0; empirical model reproduces 68 of 100 rejections (32 pp gap) → insufficient |
| [2026-11-05-c2m2-conditional-error.md](2026-11-05-c2m2-conditional-error.md) | C2-M2 result | predictive check | q-bin bias confirmed (R² 0.26) but no conditional-mean gain; only M3 covariance accepted on 2 held-out geometries; reference estimator abstains more |
| [2026-11-05-c2-repair-dev.md](2026-11-05-c2-repair-dev.md) | C2 repair development | development grid | B1 de-chirp 0/82, B2 27/82, B3 calibration 0/82; detection 27/36 all; no candidate selected, sealed grid unopened |
| [2026-11-05-c2-selfcheck.md](2026-11-05-c2-selfcheck.md) | C2-C pre-seal | development diagnostics | wrong-model self-confirmation absent; time-block self-confirmation flagged; B3 150–400 Hz/s family failure; SNR branch unverified |
| [2026-11-05-c2-sealed-attempt1.md](2026-11-05-c2-sealed-attempt1.md) | C2-C attempts 1–2 | execution records | both invalid (grid digest contract; stdin+spawn); no artifact, no retry |
| [2026-11-05-c2-sealed-confirmation.md](2026-11-05-c2-sealed-confirmation.md) | C2-C sealed | 566-trial confirmation | B1 primary endpoint PASS (coverage 0.786 vs 0.103, FRR 0.020 vs 0.685, detection equal, 0 claim violations); high-chirp acceleration detection 0/30 for all candidates |
| [2026-11-05-c3-risk-coverage.md](2026-11-05-c3-risk-coverage.md) | C3 result | sealed artifact re-analysis | at matched coverage B1's adequacy severity has higher error risk than B0; de-chirped residuals are a poorer confidence score; frozen decisions unchanged |
| [2026-11-05-c4-semantics-audit.md](2026-11-05-c4-semantics-audit.md) | C4 audit | archive + docs | fixed ADR 0024 lifecycle contradiction; archive semantics tests; no unbounded real-world claim found |
| [2026-11-05-sealed-independent-recompute.md](2026-11-05-sealed-independent-recompute.md) | independent recompute | archived artifact | exact reproduction of sealed metrics; baseline vs candidate-own truth-label nuance documented |
| [2026-11-05-e1-estimator-audit.md](2026-11-05-e1-estimator-audit.md) | E1 estimator audit | synthetic audit set | correct-CV conclusions estimator-independent; acceleration detection estimator-sensitive at b=1400 m (6/12 adequacy flips, 0 claim flips) |
| [2026-11-05-e1-detection-consensus-rule.md](2026-11-05-e1-detection-consensus-rule.md) | E1 rule v1 (historical) | decision calibration | v1 two-valued consensus; superseded by v2 for classification semantics |
| [2026-11-05-e1-detection-consensus-v2.md](2026-11-05-e1-detection-consensus-v2.md) | E1 rule v2 | decision calibration | ternary D/A/U; U+U is undetermined; audit reclassified to 0/12 detected, 12/12 undetermined, 0/12 not-detected; capability gaps stated |
| [E1-0-procurement-and-authorization.md](E1-0-procurement-and-authorization.md) | E1-0 package | organizer checklist | reference source, acquisition, time reference, site, data rights, raw evidence, feasibility gates |
| [E1-0-atmosphere-uncertainty.md](E1-0-atmosphere-uncertainty.md) | E1-0 operator | planning uncertainty | temperature/humidity/pressure/wind → predicted Doppler interval (planning only) |
| [E1-0-fault-injection.md](E1-0-fault-injection.md) | E1-0 rehearsal | synthetic field faults | clock ppm, clipping, dropouts, wind, missing/low-SNR reference; no false support |
| [2026-11-06-r1d-container-report.md](2026-11-06-r1d-container-report.md) | R1-D trial | local container reproduction | Linux/Python 3.13 container mismatches the frozen E0 digest; gate remains off |
| [2026-11-06-refusal-audit-demo.md](2026-11-06-refusal-audit-demo.md) | governance demo | refusal audit | CLI denial → append-only store row → read-only Tauri cockpit view |
| [2026-11-06-e1-0-dry-run-readiness.md](2026-11-06-e1-0-dry-run-readiness.md) | E1-0 consolidation | code-side readiness | executable gates/rehearsals, synthetic outputs, remaining physical gates |
| [E1-0-filesystem-sandbox.md](E1-0-filesystem-sandbox.md) | E1-0 sandbox | container execution boundary | read-only repo/root, no network, only /out writable |
| [2026-11-07-hardened-v1.1-freeze.md](2026-11-07-hardened-v1.1-freeze.md) | Hardened v1.1 freeze | candidate reproducibility protocol | semantic comparison, 0 primary mismatches, CI pending |
| [2026-11-07-e1-end-to-end-fixture.md](2026-11-07-e1-end-to-end-fixture.md) | E1 integration fixture | CLI/Fabric/Store contract | bundle→snapshot/store→signed refusal audit; not a cockpit UI test |
| [2026-11-07-ci-run.md](2026-11-07-ci-run.md) | CI run 42360797336 | first green matrix | 24 success / 1 optional macOS skip; artifacts listed |
| [2026-11-07-local-trust-chain.md](2026-11-07-local-trust-chain.md) | Local trust chain | P1 implementation | HMAC actor, signed audit, policy file/boundary, calibration date |
| [E1-scale-audit.md](E1-scale-audit.md) | E1 planning | scale audit | safe pilot covers ~0.1–70 Hz/s; C2 150–400 Hz/s band declared uncovered unless separately authorized |
| [E1-0-instrument-feasibility.md](E1-0-instrument-feasibility.md) | E1-0 gate | bench design | few-Hz Doppler shift vs STFT resolution; clock/reference/geometry/SNR checks; collection blocked until answered |
| [E1-B-leakage-protocol.md](E1-B-leakage-protocol.md) | E1-B protocol | leakage control | fixed blocks, STFT guard bands, no held-out stats in prediction/gating/calibration; three analysis conditions |
| [E1-0-bench-validation.md](E1-0-bench-validation.md) | E1-0 bench | instrument protocol | five bench tests; calibration/evaluation split; bias/variance/lag/clock budget; no bench data collected yet |
| [2026-11-05-c1-identifiability.md](2026-11-05-c1-identifiability.md) | C1 result | symbolic + locked | b/f0 refuted, f0·b invariant, v/f0·b capped conditional, 0 supported_invariant, 3000/3000 cross-env |
| [2026-11-05-c1-symmetry-audit.md](2026-11-05-c1-symmetry-audit.md) | C1 P0 audit | symbolic + numeric | resolves the clock-action conflict: PR-4d formula invalid (2.5e-2), derived action preserves at 8.9e-16; f0·b confirmed; protocol digest defect documented |
| [2026-11-05-pr4c-hardened-validation.md](2026-11-05-pr4c-hardened-validation.md) | PR-4c result | three environments | diagnostic + hardened rule: equivalence 2499/2500, utility fails (30% false accept) |
| [E1-instrument-calibration.md](E1-instrument-calibration.md) | E1 preparation | procedure | calibration and static-reference procedure |
| [E1-data-registration.md](E1-data-registration.md) | E1 preparation | template | per-dataset registration form |

E0 is a synthetic estimator/identifiability study. It is **not** evidence about real recordings, and it carries no localization or capability claim.

Replaying E0 offline: `make e0` (verifies the pinned snapshot, reruns the sweep, and fails on any `records_sha256` mismatch; see ADR 0012).

## Rules

1. **Pre-register before running.** A hypothesis, the expected outcome, the data snapshot ids, the baselines, and the decision rule are written into the report *before* the first run. Commit that file first.
2. **One report per experiment**, named `YYYY-MM-DD-<slug>.md`.
3. **Report failures.** A report that contains only successes is incomplete by definition.
4. **Attach artifacts by digest, not by size.** Data snapshots and result files are referenced by immutable id/hash and are never committed to the repository.
5. **A changed expectation needs its own paragraph**: what changed, and whether the model, the implementation, or the expectation was wrong.

Template:

```markdown
# <Experiment title>

Status: pre-registered | running | complete
Date: YYYY-MM-DD
Author:
Related: [ROADMAP](../roadmap/ROADMAP.md#m1--acoustic-inference-vertical)

## Question

## Preregistered expectation

## Data (snapshot ids, licenses)

## Method and baselines

## Results

## Failure gallery

## Limitations and what this does not prove

## Decision (continue / revise / abandon)
```
