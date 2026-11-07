# M0 status — updated 2026-11-04 (after the two-track decision)

Snapshot, not a plan. The plan is [ROADMAP](ROADMAP.md); the authority for every claim below is code and test output, not this page.

## Track status

| Track | Unit | State |
|---|---|---|
| A | A1 append-only evidence store (`crates/phaino-store`, PR-1) | **Landed** — SQLite crate; G1+G3 claimed, G2 detection-only per [ADR 0009](../decisions/0009-evidence-store-guarantees.md); 31 store integration tests + 4 unit tests, workspace total 64 green |
| A | A2 CLI / golden replay | **Landed** — `phaino` CLI, verified snapshot replay, license gate; `make e0` proves exact offline replay |
| A | A3 minimal license gate, A4 fixed-snapshot reader (PR-3) | **Landed** — `crates/phaino-fabric` + `phaino` CLI; `make e0` replays E0 offline from a verified snapshot and appends Source/Observation/InferenceRun; contract [ADR 0012](../decisions/0012-research-grade-minimal-fabric.md) |
| B | B1 question frozen ([research program](../research/research-program.md), [ADR 0010](../decisions/0010-m1-identifiability-program.md)) | **Done** |
| B | B2 E0 synthetic Doppler identifiability (PR-2) | **Landed** — [report](../experiments/2026-11-04-e0-synthetic-doppler.md); 2500 trials replayed to the same record digest; 13 tests; decision: continue with four revisions |
| B | B3 E1 real controlled recordings | **Preregistration draft v4 + E1-0 gates** ([E1 draft](../experiments/2026-11-05-e1-preregistration-draft.md), [E1-0](../experiments/E1-0-instrument-feasibility.md)); collection blocked on instrument references, site authorization, consent and legal review — not on code |
| B | B4 E2 locked benchmark | Not started |

## What the store will and will not claim

Per [ADR 0009](../decisions/0009-evidence-store-guarantees.md):

| Guarantee | Meaning | Claimed at M0 |
|---|---|---|
| G1 logical append-only | The normal application write path cannot modify or delete a record; `hypothesis.status` is the only mutable column and moves only along a logged transition graph with a `cause_id` | **Yes** |
| G2 tamper detection | A hash-chained append log detects substitution when a verifier holds an external checkpoint; without one, an actor who rewrites the whole database rewrites the chain | **Detection only — never described as prevention** |
| G3 replayable state | Same event set + cutoff ⇒ identical projection and digest | **Yes** |

`as_of_record_time(t)` (what the system knew at `t`) and `as_of_event_time(t)` (what claims happened at or before `t`) are separate functions; mixing them is a defect.

## Landed before this update

| Area | State |
| --- | --- |
| Docs foundation | Founding brief (EN/zh), ontology spec, inferencer contract, research program, architecture, roadmap, evaluation design, policy, research/data survey |
| ADRs | 0001–0011 accepted and indexed |
| Rust core seed | Nine typed objects, PCJ-0 canonical JSON + identity for all nine, replay key, evidence graph with edge matrix, I7 log-odds combination, strict wire shapes, typed actions + audit |
| Python SDK | `phaino_sdk`: contract types, manifest loader, validators, PCJ-0 subset, runner |
| Verification | 28 data-infrastructure claims graded V/E/U; corrections applied (ERA5 native grid, GHCN cumulative stations, TLE exhaustion, Overture ODbL themes, Open-Meteo caps) |
| Minimal fabric v0 | `crates/phaino-fabric` + `phaino` CLI: profile validation, append-only catalog, verified content-addressed snapshots, license gate, replay records; `make e0` proves exact offline replay of E0 |

## Open units (updated 2026-11-06)

1. **License-lattice integration into the store/publish gate** — the library (`phaino-fabric::lattice`, join/meet over access, granularity, obligations and consent scopes) and a derived publication decision (`LicenseGate::gate_derived`) are landed and tested; wiring it into `Profile` ingestion and the store publish path remains.
2. **Host-enforcement integration** — `phaino-fabric::contract` now negotiates MINOR versions, validates non-zero bounded budgets and resolves paths inside a sandbox root; the E0 Python invocation uses the shared `RunBudget`: 300 s wall-clock deadline with kill/reap, `RLIMIT_CPU` on Unix, `RLIMIT_AS` on Linux (macOS rejects address-space changes), 16 MiB bounded stdout/stderr capture and an output-entry ceiling. The child also runs with `HOME`, `TMPDIR` and `XDG_CACHE_HOME` inside the disposable workspace, bytecode writes disabled and a 1 GiB `RLIMIT_FSIZE` side-effect bound. An OS-level filesystem sandbox remains unenforced.
3. **Cross-environment reproducibility gate** — R1-N passes; R1-D remains off. A local container trial now has comparator evidence, not just a digest mismatch: macOS arm64 ↔ Linux arm64 passes **R1-N + R1-D** (`numerically_equivalent`) while **R2 fails**; macOS arm64 ↔ Linux amd64 passes R1-N but **fails R1-D** on a material `null_noise_only.converged_rate` change (0.09 → 0.08). All-target R1-D therefore remains off; R2 byte identity fails on every pair. See [R1-D container report](../experiments/2026-11-06-r1d-container-report.md). The latest commits have not executed CI since `183087e` because of the GitHub billing block.
4. **E1-0 instrument gates** — reference frequency/time, authorized site, consent/legal review and raw-waveform capture must be evidenced before E1 collection; this is the current M1 priority, not an M0 code unit.

A local end-to-end refusal-audit demo now exists ([report](../experiments/2026-11-06-refusal-audit-demo.md)): `phaino audit-check` writes a denial row (optionally pinning an input snapshot digest), the store assigns a durable monotone sequence, and the Tauri cockpit reads it read-only. Landed in the 2026-11-05 governance pass: **policy artifact digest** (`PolicyArtifact` in `phaino-core`, written into the E0 replay record **and** the store's `inference_run.parameters`), **refusal auditing** (`authorize_attempt*` + append-only `audit_event` table + `phaino_fabric::record_authorization`; tests prove a denied attempt leaves a store row), **license/sensitivity lattice** (`phaino-fabric::lattice` join/meet), **host contract primitives** (`phaino-fabric::contract`) and a bounded E0 subprocess runner. The E1-0 raw bundle validator is landed in `python/phaino_e1raw`, with `phaino fabric e1-bundle`, the gate-first `phaino fabric register-e1` CLI, a reference-SNR floor (≥10 dB) and a Rust library gate; an explicit container filesystem/network boundary exists in `scripts/sandboxed_e0.sh` (not the default CLI path); `Fabric::register` auto-detects `bundle.json` or a top-level JSON with the `e1-0-bundle-` schema marker and refuses an invalid E1 bundle before writing a snapshot (a malformed/non-E1 manifest can still evade the heuristic).

## Accepted deviations (visible, not hidden)

1. `RunRecordBuilder::build()` accepts a caller-supplied run id; only `build_content_addressed()` derives it.
2. `same_event_as` requires same type and normalized ordering; a `constraint` cannot be a `refers_to` source.
3. Python response-level residuals reuse the candidate residual schema.
4. Manifest validation checks contract MAJOR only; MINOR negotiation is host-side work.
5. `record_digest` excludes itself (self-reference) and normalises set-like arrays before PCJ-0.
6. Rust and Python share the ADR 0006 RFC 8785 vectors; both written by the same author, so the M4 cross-language gate still needs an independent check.

## Cross-platform note

`make e0` is exact on the producing environment (macOS arm64). The cross-platform R0/R1/R2 comparison ([report](../experiments/2026-11-05-cross-platform-e0.md)) shows R0 pass, R2 fail, and **R1 not established**: parameters agree to ~1e-9 where identifiable, unidentifiable conditions diverge, and 1/2500 convergence decisions flips (a condition rate changes 100→99). CI runs `make e0-ci` (records `determinism: unknown`) and uploads the Linux artifact; it does not claim R1. PR-4b implements reproducibility contract v2 ([ADR 0013](../decisions/0013-reproducibility-contract-v2.md)): R1-N/R1-D split, A/B/C/D field classes, pre-declared identifiability, `indeterminate` decision state with margins, and three-environment validation (A macOS arm64, B ubuntu-24.04 x86_64, C ubuntu-24.04-arm) before the CI gate. Result: R1-N passes on all three pairs; R1-D fails on pairs involving x86_64. PR-4c added a trial-57 diagnostic and a separate hardened rule: trial 57 is now accepted on all three environments, accepted set identical (2000/2000), accepted params ≤3.8e-9, formal decision equivalence 2499/2500 (one null-trial stall path differs), and **decision utility fails on truth (30% false accepts)** because variance-explained adequacy accepts biased fits. R1-D stays off; next: interpreter alignment on A, stall-path classification, model-form adequacy, pre-declared utility on independent data.

## What this milestone does not claim

No inference capability, no localization, no calibration, no benchmark result. G0 (a verified real-world claim) requires E1 at the earliest; synthetic E0 is explicitly not evidence about the world ([ADR 0010](../decisions/0010-m1-identifiability-program.md)).

## 2026-11-05 — E1-C consensus is estimator-level only

The consensus audit's more important result: on 24 correct-CV trials, 12 are flagged D+D (50% false detection), 9 A+A, 3 U+U; on 12 acceleration trials, 0 D+D, 12 undetermined. Sensitivity 0/12; FPR 12/24; FDP 12/12 (sample); mismatch abstention 12/12. The pair does not separate correct from mismatched models on this audit set. `detected` is therefore scoped `estimator_consensus`, `physically_supported=false`; E1-C reports sensitivity/TPR and FPR with abstention as two primary endpoints, with FDP as a derived diagnostic. No new estimator/threshold tuning against these 36 trials.

## 2026-11-05 — E1-C Detection Consensus v2

Corrected the consensus rule to ternary D/A/U: D+D detected, A+A no mismatch found (not proof of correctness), all mixed pairs and U+U undetermined with explicit reasons. U+U is never `not_detected`. Reclassification of the estimator audit: 0/12 detected, 12/12 undetermined (6 incomplete_confirmation D+U, 6 both_inconclusive U+U), 0/12 not_detected, 0 false supported; correct-CV 9 A/A, 12 D/D, 3 U/U, consensus claims 3 per claim. Capability gaps: detection power (0/12; 95% upper bound ~22.1% if i.i.d., not guaranteed due to geometry clustering) and positive support (9/24 A/A). Estimator agreement tests implementation robustness, not physical/measurement-model validity; claim support compares values under the declared transformation group. E1-A/B/C outcomes decided independently. Added the E1-0 procurement and authorization package.

## 2026-11-05 — C4 audit, sealed recompute, estimator independence

C4: fixed the ADR 0024 lifecycle contradiction (scientific_failure is no longer an execution state) and added archive-semantics tests; no unbounded real-world claim found. The sealed metrics were independently recomputed from the archived artifact and match exactly (with a documented baseline-vs-candidate truth-label nuance). The E1 estimator audit found correct-CV conclusions estimator-independent but acceleration detection estimator-sensitive at b=1400 m (6/12 adequacy flips, 0 claim flips); E1 must report detection across estimators or use an estimator-robust rule.

## 2026-11-05 — E1-0 bench validation is the next main task

C2-C is accepted as a completed synthetic confirmation with all limits retained. The next executable task is **E1-0 bench validation** (static frequency accuracy, window sensitivity, clock stability against an independent reference, signal-chain direct-vs-acoustic, downstream decision impact), with calibration and independent evaluation captures kept disjoint. The analysis harness and metadata contract are in `python/phaino_bench`; **no bench data have been collected yet**, so no instrument evidence exists. C2-C outcome is bound to hypothesis `H-C2C-B1-01`, the frozen v3 protocol and the synthetic sealed grid; it does not support real-world reliability. E1-A/B/C remain drafts until the instrument error budget is measured; field collection stays gated.

## 2026-11-05 — execution status vs scientific outcome, E1-0 gate

Run lifecycle now separates `execution_status` (prepared/sealed/running/completed/invalid_execution) from `scientific_outcome` (hypothesis_supported / hypothesis_rejected / inconclusive / not_evaluated). A completed negative experiment is not an execution failure (ADR 0024 amendment, tested). The C2-C archive records both invalid attempts as `invalid_execution/not_evaluated` and the valid run as `completed/hypothesis_supported`.

E1 collection remains blocked until the **E1-0 instrument feasibility gate** is answered: frequency resolution at the expected few-Hz Doppler shift (~2.9 Hz at 2 m/s), clock calibration uncertainty, independent truth, safe geometry coverage, and measured SNR/distortion. E1-B follows the leakage-proof protocol (fixed blocks, STFT guard bands, no held-out statistics in prediction/gating/calibration). See [E1-0](../experiments/E1-0-instrument-feasibility.md) and [E1-B leakage](../experiments/E1-B-leakage-protocol.md).

## 2026-11-05 — synthetic measurement-front-end cycle closed

C2-C sealed confirmation passed for B1 on the pre-declared endpoint (supported coverage 0.786 vs 0.103; FRR 0.020 vs 0.685; detection not inferior; claim integrity intact), with mandatory caveats: high-chirp acceleration detection is 0/30 for every candidate at 150–400 Hz/s, B1's time-block self-confirmation remains unresolved, and no real-environment evidence exists. Sealed evidence is archived content-addressed in `evidence/c2c-sealed/`; run lifecycle and invalid attempts are recorded (ADR 0024).

Program decision: **stop expanding the synthetic front-end**. E1 is the next major milestone, designed around measurement transfer (E1-A), de-chirp out-of-sample validity (E1-B), and mismatch recognition (E1-C), with a pre-declared chirp-rate coverage from the scale audit. The 150–400 Hz/s band is declared uncovered by a safe low-speed pilot. C3 stays limited to the existing evaluation object; C4 is semantic/audit-only and does not reinterpret frozen R1-D. E1 collection remains gated on venue authorization, legal review, calibrated equipment, independent motion/clock references and consent.
