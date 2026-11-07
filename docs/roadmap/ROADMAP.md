# PhainoWeave Roadmap

**Status:** Adopted, plan of record · **Last updated:** 2026-11-04 · **Owner:** Haelio Tang
**Authority order:** newest Accepted ADR > this file > [founding brief](../product/founding-brief.md) > research notes.
**Scope:** sequencing, acceptance criteria, and deferrals for M0–M4. This file records intent and constraints; it is not evidence. No capability claim may cite it. Every capability claim must cite a published experiment report under `docs/experiments/` that follows [benchmark-and-evals.md](./benchmark-and-evals.md).

Companion documents (paths reserved; siblings are written concurrently): [world ontology](../specs/world-ontology.md) · [inferencer contract](../specs/inferencer-contract.md) · [ethics and privacy](../policy/ethics-and-privacy.md) · [research landscape](../research/landscape.md) · [benchmark and evals](./benchmark-and-evals.md). A link here is a contract, not confirmation that a sibling document is populated.

## §0 Current snapshot

As of 2026-11-04 the repository is a bootstrap, not a system. What exists is documentation, a reserved directory tree, and a seed Rust workspace; what does not exist is any inference capability, and no number in this repository is a measured capability estimate.

| Exists today (bootstrap) | State |
|---|---|
| [`docs/product/founding-brief.md`](../product/founding-brief.md) | Adopted; defines problem, invariants, non-goals, milestones |
| Specification set | [`world-ontology.md`](../specs/world-ontology.md) and [`inferencer-contract.md`](../specs/inferencer-contract.md) land in this bootstrap; the object model is normative there, not in code |
| Policy set | [`ethics-and-privacy.md`](../policy/ethics-and-privacy.md) plus data governance: tiers, review gate, license propagation |
| This roadmap and the [evaluation design](./benchmark-and-evals.md) | Plan of record; prose, not results |
| Seed Rust core `crates/phaino-core` | Typed object model, in-memory evidence graph, canonical run digest, independence-aware support combination, typed actions; no persistence beyond memory and no CLI |
| ADRs 0001–0007 | Accepted; they outrank this file |
| Data fabric architecture ([ADR 0007](../decisions/0007-federated-world-data-infrastructure.md)) | Federated access decided: no second global database; catalog, adapters, planner, snapshots are not built |

| Does not exist today | Consequence |
|---|---|
| Persistent evidence store, CLI, end-to-end replay harness | Records do not survive a process; replay is not demonstrated end to end; M0 exits are open |
| Data catalog, provider adapters, query planner, snapshot store | Public data cannot yet be fetched, license-checked, or cited through the fabric; M1 context data is blocked on fabric units D1–D3 (§4.1) |
| Python inference code | Only a contract-conformance package is in M0 scope; no model, DSP, or verifier exists |
| Acoustic vertical, Doppler/kinematic verifier | Zero M1 evidence. The brief's aircraft-Doppler reproduction is an external case study, not our result |
| Benchmark data, splits, preregistrations, reports | No benchmark exists, so no win, tie, or capability can be declared |
| Workbench, cross-modal verifiers, distributed replay | M2–M4 are unstarted |

**Capability claims permitted today: none.** Any statement about localization error, region coverage, calibration, false-positive rate, or generalization is out of bounds until an M1 report exists. The only honest current claim is that the contract for making such claims is being specified and is not yet enforced end to end in a persistent store.

## §1 Sequencing principle

The order is **docs and contract (M0) → one falsifiable vertical (M1) → investigation semantics (M2) → cross-modal reasoning (M3) → distribution (M4)**. Depth first, then breadth, then scale. Breadth is never allowed before falsification, and scale is never allowed before determinism.

**Execution is two parallel tracks, not one serial chain** ([ADR 0008](../decisions/0008-two-track-execution.md)). Track A builds only what the experiment consumes — append-only store, CLI/golden replay, minimal license gate, fixed-snapshot reader; track B runs the science — freeze the question, E0 synthetic, E1 real pilot, E2 locked evaluation. Within a track the order is strict; across tracks neither waits for tidiness. The M0 → M1 → M2 → M3 → M4 sequence describes the dependency of *claims*, not the order of *work*.

1. **Contract before code.** The product's unit of output is a world-state hypothesis *with its verifier*, not a prediction. Its API is therefore an ontology plus an inferencer contract that forces residuals, provenance, uncertainty, and abstention into the type system. Changing those contracts after several verticals exist is a rewrite; locking them first is cheaper, and tests make the lock checkable.
2. **One vertical before any breadth.** A single-modality, end-to-end path is the only way to falsify the project's load-bearing hypothesis (§4). Breadth multiplies interface surface before any interface has been validated by a rerun, and it produces demos that are indistinguishable from capability until evaluated. One vertical also makes evidence independence measurable: with two modalities, correlated evidence from one physical event can masquerade as two independent votes, and the system has no baseline against which to detect the inflation.
3. **Acoustic first.** The constraint side of the acoustic vertical — Doppler/kinematics from public track data — is computable without learned perception, so a negative result cannot be blamed on a weak feature extractor. It has a known external reproduction target (a case study to audit, not a result to inherit), public track and weather sources, and residuals that are physically interpretable.
4. **Investigation before cross-modal.** M2 makes "change one hypothesis, flag affected inferences" a typed, replayable operation. Without it, adding modalities at M3 adds evidence that cannot be attributed to a candidate state, and failures cannot be localized.
5. **Distribution last.** M4 distributes replay, which presupposes replay. A distributed system built before local determinism distributes unattributable differences and calls it scale.

## §2 Milestones M0–M4

Each milestone names checkable exits. A milestone is complete only when every exit criterion has an artifact a reviewer can rerun; a milestone with unmet exits is not "mostly done", it blocks the next.

### M0 — World Ontology Foundation

**Objective.** Freeze the data and plugin contracts, finish their Rust implementation and persistence, and prove the founding invariants with tests, so that a complete evidence chain is expressible, storable, and replayable before any inference exists.
**Deliverables.** `docs/specs/world-ontology.md` frozen at v0.1; `docs/specs/inferencer-contract.md`; `crates/phaino-core` completed from the seed with an append-only SQLite store, a `phaino` CLI, and conformance/invariant tests; the Python contract package limited to conformance; ADRs per §7; CI.
**Entry criteria.** Brief adopted; maintainer can build and run Rust tests locally; no inference code is needed to proceed.
**Exit criteria (checkable).** (a) One fixture chain — authorized synthetic observation → feature → hypothesis → verification — runs end to end, every derived record carries provenance and content hashes, and the chain replays to an identical run-record digest. (b) Rejection tests exist for I1 (inferred cannot be stored as verified), I2 (missing provenance rejected), I3 (record time required and cannot rewrite event time), I4 (uncertainty typed, no bare point float), I5 (contradictory hypotheses coexist with a conflict edge), I7 (evidence independence group typed), I10 (license inheritance enforced); building the illegal record must fail to compile or fail validation. (c) `cargo test --locked` is green on the CI matrix, the docs link check is green, and the test suite performs no network access.
**Non-goals.** No inference or verifier logic, no real-data ingest, no map or timeline UI, no multi-user auth or roles beyond a local principal and authorization records, no DuckDB/H3/Parquet, no performance claims.
**Main risks.** Ontology over-engineering (mitigated by the nine-object cap and ADR gating for additions); SQLite schema churn; canonicalization instability breaking digests (float formatting, map ordering, hash algorithm); scope creep from "just one small inference helper" that bypasses the contract.

### M1 — Identifiability program (E0/E1/E2)

**Objective.** Answer, in three steps with different epistemic ceilings, whether physical constraints can identify and discriminate world states from noisy acoustic observations — and publish the answer including failures ([ADR 0010](../decisions/0010-m1-identifiability-program.md)).

**Deliverables.** (E0) synthetic identifiability study with a report; (E1) real controlled-recording study with the first scientific claim; (E2) preregistered, sealed evaluation against independent reference evidence. Each report at `docs/experiments/YYYY-MM-DD-<slug>.md`, with run records for every number; E1/E2 data entering only through the minimal fabric (PR-3) with license, source registration, and immutable snapshot.

**Entry criteria.** E0 needs nothing from M0 but the normative constraint model: it can start now. E1 needs the minimal fabric (PR-3) plus lawfully usable fixed data. E2 needs E1's graded evidence and a sealed split. M0's store/CLI are required for E1's replay record, not for E0.

**Exit criteria (checkable).**
- E0: parameter-recovery error vs SNR for `f0`, speed, closest-approach time and distance; success rate against a preregistered tolerance; identifiability analysis (parameter correlations/degeneracies); failure conditions for acceleration mismatch, clock offset, and short windows. No real-world claim is made.
- E1: discrimination between true events and wrong candidate explanations on real recordings with known truth, reported as true/false positives, abstention, and residuals; the acoustic-only baseline is reported alongside.
- E2: area-bounded `Coverage@A` (abstentions counted as misses), area distribution, reliability/ECE, selective risk, and the B0–B3 comparison at a preregistered margin and calibration guard fixed in advance.

**Non-goals.** No geo-localization claim from synthetic data; no cross-modal fusion; no workbench; no backbone training; no claim of street-level or person-level accuracy; no live use.

**Main risks.** Identifiability degeneracy (`f0` vs velocity, unknown track offset) making the region unrecoverable — which is itself a reportable result; real-data licensing delay for E1; a null result being reframed post hoc (prevented by preregistration).

### M2 — Investigation & Hypothesis Engine

**Objective.** Make an investigation a first-class, replayable object and quantify the effect of changing one hypothesis.
**Deliverables.** Investigation/session records as typed objects (ontology extension via ADR); hypothesis-delta engine; CLI commands for record, replay, diff, and export; a local investigation surface rendering map, timeline, evidence graph, and simulation views from one run record; report.
**Entry criteria.** M0 exits met and M1 vertical executable; ADR accepted for investigation objects and for UI scope (see §7 and §5).
**Exit criteria (checkable).** (a) A recorded fixture investigation replays to an identical state digest in isolation, and the replay is independent of working-directory state. (b) Property test over fixture evidence graphs: changing one hypothesis flags exactly the dependency-closure of affected inferences and verifications — no over-flagging, no under-flagging. (c) The four views render from the same run record and show the same hypothesis set, with view data derived from the record rather than a separate query path. (d) A written report documents the replay and delta tests and includes a failure gallery.
**Non-goals.** No packaged Tauri desktop application (a local browser surface is the M2 deliverable; see §5); no collaboration, accounts, or server deployment; no cloud storage; no analytics database; no new modalities.
**Main risks.** Ontology growth (investigations, sessions, notes) reopening M0 contracts; UI scope expansion displacing the replay and delta tests; demo surfaces being read as capability claims; affected-set semantics under contradiction (I5) being underspecified.

### M3 — Cross-modal Reasoning & Evals

**Objective.** Measure whether heterogeneous modalities improve inference over the best single modality under independence-aware aggregation, and make correlated-evidence overconfidence visible and bounded.
**Deliverables.** At least two non-acoustic verifiers (visual/astronomical, meteorological, terrain/geometry — selection per ADR); independence representation in the evidence graph with aggregation rules; eval harness and a version-comparison suite; agent/tool eval set; published report(s).
**Entry criteria.** M1 report accepted (including a negative result, if that is what it is); independence-model ADR accepted; licenses and sensitivity recorded for every new modality; M2 delta engine available to localize regressions.
**Exit criteria (checkable).** (a) Multi-modal beats the best single modality on held-out splits by the preregistered margin, with the calibration guard and multiple-comparison policy of [benchmark-and-evals.md](./benchmark-and-evals.md). (b) The correlated-evidence protocol is executed and passes: paired evidence from one physical event does not inflate confidence or degrade calibration beyond the preregistered tolerance. (c) The eval suite compares two code versions and reports the metric deltas automatically, and the agent/tool eval set detects a seeded regression. (d) Reports include failures and an explicit statement of what each split does not prove.
**Non-goals.** No person-level inference, no real-time or operational command use, no foundation-model training (frozen pretrained features and nonparametric or linear heads only), no packaged workbench, no multi-node deployment.
**Main risks.** Correlated evidence inflating confidence — the most likely failure mode in the brief and the reason M3 exists; data ceilings in weather and imagery limiting what can honestly be claimed; ontology complexity; benchmark overfitting through repeated reuse of the same evaluation set (test-budget exhaustion); hidden dependence between a pretrained model's training data and the evaluation regions.

### M4 — Distributed Research Infrastructure

**Objective.** Prove that the same task replays identically on a local machine and an independent node, and that cross-version result differences localize to data, model, software, or environment changes.
**Deliverables.** Portable, digest-pinned environment specification (toolchains, system libraries, data snapshot manifest); snapshot fetch/verify tool; replay-parity harness across two independent machines; version-attribution tool; operational documentation for a Research Node; published report.
**Entry criteria.** M3 report accepted; local replay determinism demonstrated; environment pin exists; a second independent machine is available.
**Exit criteria (checkable).** (a) The same fixture task on two independent nodes yields identical run-record digests, or every observed difference is classified and supported by evidence. (b) Controlled injections of a data change, a model-weight change, and a software change are each localized to the correct layer on the fixture set, with zero misattributions. (c) The report states which nondeterminism sources remain and why they are attributable.
**Non-goals.** No Kubernetes or cluster orchestration, no multi-tenant identity, no cloud cost optimization, no edge deployment, no live data streaming, no person-level or precise-place operation.
**Main risks.** External data drift (tracks and reanalysis get revised); floating-point and toolchain nondeterminism; environment-lock maintenance cost; node heterogeneity (CPU features, BLAS, timezone, locale); distributing before attribution works.

## §3 M0 work breakdown

Ordered so each unit ends in a state a reviewer can verify. Module names inside `crates/phaino-core` are provisional and ratified by an ADR (§7); the crate itself is fixed by ADR 0004 and the workspace facts.

| # | Unit | Verifiable result |
|---|---|---|
| 1 | Spec freeze (`../specs/world-ontology.md` v0.1) | Nine objects, relations, typed actions, and invariants are normative; open questions closed; reviewed by a non-author; ontology version string defined |
| 2 | Contract primitives (`phaino-core::uncertainty`, `::id`) | Region, time window, calibration reference, and typed identifiers; serialization round-trip; rejection tests for bare point values; Rust/Python parity against the spec |
| 3 | Object model and actions (`phaino-core::objects`, `::provenance`, `::actions`, `::evidence`) | Nine objects; one accept and one reject test per invariant (I1–I5, I7, I10); contradiction edges and independence-aware combination covered by tests |
| 4 | Evidence store (`crates/phaino-store`, new crate; PR-1) | SQLite schema v0 per spec §10; **G1** logical append-only (triggers abort UPDATE/DELETE; `hypothesis.status` transition graph with `cause_id`), **G3** replayable projection with deterministic digest, `as_of_record_time` and `as_of_event_time` as separate functions; **G2** hash-chained append log with `verify_chain()` as detection only. Tests prove no normal rewrite path, dangling edges rejected, hash mismatch rejected |
| 5 | Run record and replay (`phaino-core::run` plus harness) | Digest extended to data snapshots, code version, inferencer versions, parameters, seeds, and environment; fixture replay reproduces the digest; one-byte-change difference test |
| 6 | CLI (`phaino`) | `validate`, `ingest`, `run`, `replay`, `digest` commands with `--json`; integration test on the fixture; deterministic exit codes; no inference commands |
| 7 | Fixture evidence chain | Authorized synthetic observation → feature → hypothesis → verification in a versioned fixture; golden digest; replay test |
| 8 | ADR set | ADRs 0001–0011 accepted and indexed; CI checks ADR status and format |
| 9 | CI | `fmt`, `clippy -D warnings`, `cargo test`, docs link check (`scripts/check_links.py`), Python tests; no network during tests |

**Definition of done for M0.** A clean clone on a supported machine runs one documented command to build, one to test, and one to ingest and replay the fixture; the replayed digest equals the golden digest; the invariant rejection suite fails on illegal records and passes on legal ones; CI is green. **The M0 claim is G1 + G3 only.** G2 is detection (hash chain), not tamper prevention, and no document may describe the store as tamper-proof.

**PR sequencing against tracks** ([ADR 0008](../decisions/0008-two-track-execution.md)): **PR-1** append-only store (A1); **PR-2** synthetic E0 experiment (B2, no store or fabric needed); **PR-3** minimal data fabric and replay (A3/A4). The CLI/golden replay (A2) may land between PR-2 and PR-3.

## §4 M1 experimental plan (E0/E1/E2)

**Plan, not evidence.** Nothing in this section is a result. Every number will come from a report whose run records replay. The three steps and their epistemic ceilings are normative in [ADR 0010](../decisions/0010-m1-identifiability-program.md).

**E0 question.** *Do physical constraints recover the relative-motion parameters of a known source from a noisy observation, which parameters are identifiable at all, and under what noise, acceleration, and clock-error conditions does estimation fail?* Synthetic only; validates the estimator and solver, never the world.

**E1 question.** *Do physical constraints discriminate true motion events from wrong candidate explanations under real recording conditions?* Real, licensed, known-truth data. This is the first scientific claim the project can make.

**E2 question.** *Does adding one independent licensed reference source improve reliability over the acoustic-only baseline at a preregistered margin, without degrading calibration?* Sealed split, locked metrics, preregistered δ and ε.

**H1 (E2 headline).** *For recordings whose world state is constrained by a Doppler-emitting source with a candidate track set, adding the kinematic constraint to a learned prior improves area-bounded region coverage and/or calibration at fixed coverage relative to the learned prior alone.*

**Data (licensing declared first, E1 onward).**
- E0 — generated signals with known truth: no external data, no license, fully deterministic seeds.
- E1 — fixed licensed real recordings with verifiable location/time: license, access terms, sensitivity, version, and retrieval method recorded before the first read; entering only through the minimal fabric as an immutable snapshot.
- E2 — E1 plus one independent licensed reference source (for example an ODbL track archive). Prefer a source whose independence from the recording conditions can be argued; report the independence assumption.
- Negative and null cases — no source present, indoor/broadband noise, clipped segments, deliberately insufficient evidence; used for false-positive and abstention measurement.
- Context data: public historical track data and meteorological reanalysis at native resolution, through the minimal fabric. Default track dependency is **adsb.lol (ODbL)**; **OpenSky** is research-tier cross-check only ([data sources](../research/data-sources.md)). Reanalysis resolutions: ERA5 on the 0.25° CDS grid (~25 km; native ~31 km), ERA5-Land ~9–11 km, IFS ~9 km; none supports street-level claims.

**Doppler/kinematic constraint model (spec level).** For a narrowband component with unknown rest frequency `f0` emitted by a source at `x_s(t)` and received at `x_o`:

```
f_obs(t) ≈ f0 · c / (c − v_r(t)),   v_r(t) = − d/dt ||x_s(t) − x_o||
r(t) = f_obs(t) − f_pred(t; θ),     z(t) = r(t) / σ_f(t)
```

`c` is sound speed from temperature and humidity; emission time accounts for propagation delay `t − ||x_s − x_o||/c`; `θ` includes `f0`, a track/clock time offset `τ`, source speed and geometry, and `c` uncertainty. Known degeneracies — `f0`/`τ`/speed trade-offs, mirror geometry, a single track constraining a curve rather than a region — are part of the specification and must appear as limitations.

**E0 design (starts now).** Synthetic generator: straight-line source, narrowband emission, additive noise at a defined SNR, optional constant acceleration, optional recorder clock offset/scale, optional short windows. Estimator: a physical fit plus a model-free instantaneous-frequency tracker as the competitive baseline. Report: parameter relative error vs SNR (N≥100 trials/point, fixed seeds), success rate against a tolerance declared before the run, parameter-correlation/identifiability analysis, and failure thresholds for acceleration mismatch, clock ppm, and window length.

**Baselines (E1/E2).** B0 global prior: base rate over region and time, no observation features. B1 learned unimodal prior: frozen pretrained acoustic features with a nonparametric/linear head fitted on the tuning split only. B2 physics-only: the Doppler/kinematic verifier with B0. B3 combined: B1 and B2 under independence-aware aggregation. Every baseline uses the same inputs, splits, and abstention policy.

**Ablations.** `f0` marginalized vs fixed; propagation delay on/off; sound-speed correction on/off; clock offset injected; single vs multiple narrowband components; segment duration; evidence split into independence groups vs naive pooling; track shuffle as a leakage control; per-geography subsets.

**Metric.** Primary is area-bounded region coverage, `Coverage@A` with abstentions counted as misses, plus the region-area distribution, abstention rate, reliability/ECE, and the B0–B3 comparison ([benchmark-and-evals](./benchmark-and-evals.md), [ADR 0010](../decisions/0010-m1-identifiability-program.md)). δ and ε are fixed at E2 preregistration with a stated power/sample-size justification; they are not set in advance of the design.

**Required published report.** Per [benchmark-and-evals](./benchmark-and-evals.md) template: claim, data snapshot with hashes and licenses, code version, preregistration reference, results with distributions, coverage and calibration, selective curves, false-positive rates, residuals, correlated-evidence test, replay determinism, failure gallery, limitations (including what the splits cannot prove), and a decision line. Reports are published whether or not the result is positive.

## §4.1 Data fabric: two tiers, one deferred

**Constraint.** PhainoWeave does not own a second global database ([ADR 0007](../decisions/0007-federated-world-data-infrastructure.md)). Data reaches the ontology through a fabric boundary, never by a direct provider call from an inferencer. But the boundary has two tiers ([ADR 0008](../decisions/0008-two-track-execution.md) §3–§4):

| Tier | Scope | When |
|---|---|---|
| **Research-grade Minimal Fabric (RMF)** — PR-3 | Source registration; dataset profile with license, resolution, positional accuracy, observation type, and missingness; `LicensePolicyEngine` check; immutable fixed snapshot (version + retrieval + content hash); offline read; provenance records. Contract fixed by [ADR 0012](../decisions/0012-research-grade-minimal-fabric.md) | Before E1. One or two sources, no service |
| **Platform-grade Federated Fabric (PFF)** — deferred | World Data Catalog, provider adapters (Overture/Geofabrik/DEM/satellite/ERA5/adsb.lol), query planner with cost/information-gain model, incremental cache, fault recovery, distributed connector lifecycle | Only when an experiment states which source it needs and why a fixed snapshot is insufficient |

**RMF acceptance (checkable).** (a) A source cannot be registered without license, resolution/accuracy fields, and a missingness statement; `spatial_resolution` and `positional_accuracy` cannot be conflated. (b) A restricted or non-commercial source cannot feed a default publication path. (c) The snapshot's bytes are verified against its content hash before every run. (d) A run with no network access replays from the snapshot and reproduces the same input digests. (e) The record carries source, version, license, and retrieval time.

**RMF v0 landed (PR-3).** `crates/phaino-fabric` (profile validation, append-only catalog, verified snapshots, license gate, replay records) plus the `phaino` CLI. `make e0` replays the E0 experiment offline through a verified snapshot: snapshot `ae88e811…`, expected = observed `674213d9…`, comparison `exact`, and Source/Observation/InferenceRun appended to the evidence store. License gate refusals are tested (`research` source cannot satisfy `external_publication`). 20 fabric integration tests. Contract: [ADR 0012](../decisions/0012-research-grade-minimal-fabric.md).

**Cross-platform contract v2 (ADR 0013).** R1 is split into R1-N (numeric equivalence of identifiable fields) and R1-D (decision equivalence with an `indeterminate` state and pre-declared margins), fields are classified A/B/C/D, identifiability comes from a pre-declared reference-side rule, and a protocol is validated on three environments (macOS arm64, ubuntu-24.04 x86_64, ubuntu-24.04-arm) with adversarial boundary/unidentifiability fixtures before any CI gate. PR-4b implements this; the CI gate stays off until the protocol is frozen.

**Cross-platform limit (measured 2026-11-05).** `make e0` proves exact replay in the producing environment. The R0/R1/R2 comparison across macOS arm64 and Linux x86_64 ([report](../experiments/2026-11-05-cross-platform-e0.md)) finds: parameters agree to ~1e-9 where identifiable; unidentifiable/null conditions diverge without bound; 1/2500 convergence decisions flips and changes a reported condition rate (100→99); implementation metadata (iterations) differs broadly. **R1 is not established**, and CI does not claim it. PR-4b (scope + decision margin + field classes + frozen protocol + gate) is the next unit and gates E2.

**PFF deferral is explicit.** D2's five production adapters, D3's planner, and the catalog service are not prerequisites for E0/E1. Overture pinning is resolved when the first source actually enters the RMF; GTFS, LCFM, station density, ocean, and astronomy work does not block the first acoustic experiment.

## §4.2 Data fabric units (deferred register)

Kept for the PFF plan of record; none is on the critical path today. Unblocking condition for every row: an experiment specifies the source and why a fixed snapshot is insufficient.

| Unit | Scope | Unblocked by |
|---|---|---|
| D2 | Adapters: Overture GeoParquet, Geofabrik extract, Copernicus DEM, ERA5/Open-Meteo, adsb.lol | E2 needs a second/independent source that must be refreshed, or a study spans regions requiring tract-dependent extraction |
| D3 | Query planner v0 with cost/information-gain estimate | Two or more sources must be selected per hypothesis against a budget |
| D4 | Satellite/station adapters: STAC, COG windows, NOAA ISD, JPL Horizons | A visual or station-based constraint enters the program |
| D5 | Ecological/land-cover adapters: GBIF, iNaturalist, LCFM/WorldCover/Dynamic World | An ecological prior becomes load-bearing in a study |
| D6 | Distributed connector lifecycle, update/rollback, offline bundles | M4 parity work starts |

**Rules that bind every unit.** A connector does not merge without a registered profile, a license review, and a snapshot-parity test. `spatial_resolution` and `positional_accuracy` are separate fields and are never conflated in a report. Absence of a record is not negative evidence; the verifier consults the missingness model. A result that cites a live URL instead of a snapshot id is invalid.

## §4.1 Data fabric workstream (ADR 0007)

**Constraint.** PhainoWeave does not own a second global database ([ADR 0007](../decisions/0007-federated-world-data-infrastructure.md)). Data reaches the ontology only through the fabric: catalog → adapter → planner → normalization → immutable snapshot → evidence registry. No inferencer, verifier, or surface calls a provider directly. The units below are numbered D* and gate M1's context data.

| Unit | Scope | Milestone | Acceptance (checkable) |
|---|---|---|---|
| D1 | `World Data Catalog`; dataset profile (ADR 0007 §4 contract + capability profile + missingness model); `LicensePolicyEngine`; snapshot manifest | M1 | Every source used in M1 has a profile; registration is refused without license, resolution, or missingness; a restricted source cannot be selected for a default path; snapshot ids resolve to content hashes |
| D2 | Adapters: Overture GeoParquet via DuckDB, Geofabrik regional `.osm.pbf`, Copernicus DEM tiles, ERA5/Open-Meteo historical, adsb.lol daily archive | M1 | Each adapter produces a pinned snapshot (version/retrieval/hash) and a capability profile; a network-free replay reads only the snapshot; region extraction from one snapshot is byte-identical across runs |
| D3 | `Query Planner` v0: minimal provider selection, cost estimate (requests, bytes, compute), plan recorded in the run record | M1 | A hypothesis/query yields a stable plan; the planner never fans out to providers that cannot constrain the query; the run record replays the plan |
| D4 | Satellite and station adapters: Copernicus Data Space / Earth Search STAC, COG window reads, NOAA ISD, JPL Horizons | M2 | Same as D2, plus a pinned catalog version and a COG window read verified against its snapshot hash |
| D5 | Ecological and land-cover adapters: GBIF (dataset-level licenses), iNaturalist, LCFM/WorldCover/Dynamic World | M3 | Per-dataset license filtering; sensitive-species coordinates never enter the evidence graph unredacted; missingness modelled per dataset |
| D6 | Distributed connector lifecycle: packaged adapters, update/rollback, offline bundles, replay parity across nodes | M4 | The same query on two nodes yields the same snapshot ids and the same inference record; a failed connector update rolls back without changing the evidence chain |

**Rules that bind every unit.** A connector does not merge without a registered profile, a license review, and a snapshot-parity test. `spatial_resolution` and `positional_accuracy` are separate fields and are never conflated in a report. Absence of a record is not negative evidence; the verifier consults the missingness model. A result that cites a live URL instead of a snapshot id is invalid.

## §5 Explicit deferrals

| Deferred | Why deferred now | Unblocking condition |
|---|---|---|
| Tauri/React desktop workbench | Packaging before investigation semantics are replayable ships a demo, not a tool; the brief's M2 workspace is delivered as a local browser surface first | M2 replay and delta exits are met, and a documented user need requires a packaged desktop application; recorded as an ADR because it narrows brief §9/§10 |
| Docker/Kubernetes deployment | Containers solve deployment, not reproducibility; a container does not pin external data or prove replay parity | M4 parity holds on two nodes and provisioning is the measured bottleneck |
| Multi-node/distributed scheduling | Distribution before local determinism distributes unattributable differences | M4 replay parity and version attribution pass; throughput demand documented |
| Model training or fine-tuning (beyond a fitted head on frozen features) | The project rents or wraps specialized models; the load-bearing claim is about constraints, not model capacity | A published report shows a frozen model's ceiling is the binding error term, with a license-reviewed dataset and an ADR |
| H3/DuckDB/Parquet analytics | Core objects fit SQLite; planet-scale analytics before the M1 workload is speculative infrastructure. DuckDB is admitted only as the L2 regional cache of the data fabric (ADR 0007 §10), reading pinned GeoParquet/COG subsets | Measured query envelope of SQLite is exceeded, or M3 cross-modal joins require spatial analytics beyond the L2 cache; ADR required |
| Live/field sensor acquisition | Acquisition raises privacy, authorization, and data-contract questions ahead of an evaluated system | M2 investigation semantics plus an ethics review and a documented misuse test (brief §12.5) |
| Platform-grade federated fabric (catalog service, five production adapters, query planner) | Research-grade minimal fabric is the real E1 prerequisite; the platform tier is multi-month work with no validated inference to justify it ([ADR 0008](../decisions/0008-two-track-execution.md) §3–§4) | An experiment names the source it needs and why a fixed snapshot is insufficient; then the PFF unit is unblocked (§4.2) |
| Full tranche of data-source work (GTFS, LCFM, station density, ocean, astronomy) | None of it constrains the first acoustic identifiability question | An acoustic result exists (E1) and a specific follow-up study needs that domain |

Precise-place and person-level localization are not deferrals; they are excluded by the founding brief and require an authorized, audited research task under [ethics and privacy](../policy/ethics-and-privacy.md).

## §6 Dependency graph

```
Tracks (ADR 0008)

A: store --> CLI/golden replay --> minimal fabric (RMF) --> replayable experiments
                                      |                         |
                                      v                         v
B: freeze question --> E0 synthetic --> E1 real controlled --> E2 locked benchmark
        (no deps)          |                    |                     |
                           v                    v                     v
                    identifiability      first scientific      independent-source
                    limits report        claim (or its         gain claim (or its
                                         falsification)        falsification)

Milestones (claims, not work order): M0 --> M1 --> M2 --> M3 --> M4
```

Hard edges, stated as claim dependencies: E0 needs only the constraint model; E1 needs E0's failure analysis, the RMF, and licensed fixed data; E2 needs E1's graded evidence and a sealed split; M2's investigation semantics need at least one replayable E1 study; M3 needs M1's graded evidence and M2's attribution machinery; M4 needs M3's reports and M0–M2's determinism. Track A units are sized to the experiment that consumes them, not to the full PFF (§4.1–§4.2).## §7 Decision log placeholder

Decisions that still require an ADR before the milestone listed. ADR numbers are assigned by the decision owner at acceptance; the list below is a topic register, not a numbering.

| Decision | Needed before | Why it cannot stay informal |
|---|---|---|
| `phaino-core` module boundaries and CLI crate split | M0 | Public API surface and maintenance boundary; ADR 0004 fixes the Rust/Python boundary but not the internal split |
| Investigation objects (session, hypothesis-change record) and their ontology placement | M2 | Extends the nine-object model; a normative change under AGENTS.md |
| Digest canonicalization (encoding, floats, ordering, hash algorithm) | M0 | Replay determinism depends on it; changing it invalidates published digests — **resolved 2026-11-04: [ADR 0006](../decisions/0006-canonical-json-and-digests.md)** (PCJ-0, replay key, cross-language vector gate) |
| SQLite schema ownership, migrations, and append-only enforcement | M0 | Invariant I6 and the store's audit properties — **resolved 2026-11-04: [ADR 0009](../decisions/0009-evidence-store-guarantees.md)** (G1 logical append-only, G2 detection-only hash chain, G3 replayable state, two as-of axes) |
| Ontology amendment procedure and the nine-object cap | M0 | Prevents over-engineering and silent contract drift |
| Data snapshot and license manifest format | M1 | Licensing (I10) must be enforced, not documented — **resolved 2026-11-04: [ADR 0007](../decisions/0007-federated-world-data-infrastructure.md) + [ADR 0008](../decisions/0008-two-track-execution.md)**: the RMF manifest is the M1 requirement; the full catalog/planner is deferred |
| Data source capability profile and missingness schema | RMF / E1 | Priority/selection without fidelity and missingness data becomes guesswork (ADR 0007 §4–§6); the RMF needs the reduced profile, not the full catalog schema |
| Query planning cost and information-gain model | After E1/E2 (PFF) | The planner is the component that keeps federation affordable; deferred with the PFF ([ADR 0008](../decisions/0008-two-track-execution.md) §4). Not a prerequisite for E0/E1 |
| Preregistration sealing and report immutability procedure | M1 | Evaluation stance is binding; post-hoc metric changes must be impossible |
| Learned-prior sourcing and license constraints (frozen weights) | M1 | Model provenance affects both licensing and split contamination |
| Independence-group representation and aggregation rule | M3 | Correlated-evidence handling is the main overconfidence risk (I7) |
| Environment pinning and reproducibility budget (Nix vs. container vs. lockfiles) | M3 | M4 parity is impossible without a portable environment |
| Tauri workbench scope vs. local browser surface for M2 | M2 | Brief §9/§10 imply a desktop workspace; this roadmap delivers the views without packaging (§5) |
| Eval suite versioning and test-budget policy | M3 | Prevents evaluation-set exhaustion and overfitting |
| Cross-platform replay comparison (structural, stated tolerance) | Before E2 | Exact digests are environment-bound; E2 needs a comparison that separates float noise from a real change (ADR 0012 §6) — **PR-4 landed the comparator and the measured report; ADR 0013 replaced the single R1 target with R1-N/R1-D, four field classes, and a decision-margin rule. **PR-4b**: contract v2 + three environments; R1-N passes on all pairs, R1-D failed where x86_64 was involved (one convergence decision). **PR-4c**: [diagnosis](../experiments/2026-11-05-pr4c-hardened-validation.md) showed the frozen statistic was curvature-amplified at the stopping point; the hardened version (scale-normalized gradient, 3-iteration stability, four statuses, budget→indeterminate) makes trial 57 accepted on all three environments and the accepted set identical (2000/2000). But formal decision equivalence is 2499/2500 and **decision utility fails on truth (30% false accepts)**, so R1-D stays off until adequacy is model-form-tested and utility is pre-declared on independent data** |
| M1 primary metric and the research/publication metric split | M1 | **resolved 2026-11-04: [ADR 0010](../decisions/0010-m1-identifiability-program.md) + [ADR 0011](../decisions/0011-privacy-forensics-and-publication-rulings.md)** (area-bounded `Coverage@A`; abstentions as misses; δ/ε fixed at E2 preregistration; publication granularity per output) |
| Forensics boundary, privacy numerics, jurisdiction, visibility, name/fork posture | M1 | **resolved 2026-11-04: [ADR 0011](../decisions/0011-privacy-forensics-and-publication-rulings.md)** (limited exception enforced at runtime + human review; numerics as decision inputs; H3/degree non-equivalence; publish after the M0 loop) |

## §8 What would make us stop or pivot

These are project-level falsifiers, not milestone risks. They are stated before any result exists so that a negative result cannot be reframed afterward.

| # | Condition | Response |
|---|---|---|
| S1 | Track A's M0 exits are not met within two milestone cycles | Narrow the ontology to the five objects E1–M2 actually use, or stop; a contract that cannot be enforced is not a contract. E0/E1 are not blocked on this |
| S2 | E1/E2 show the kinematic constraint adds nothing over the learned prior at the preregistered margin, on both data tiers, and the null result reproduces | Stop the claim that physical constraints improve inference at this scale. Pivot to a narrower, defensible role: a verifier/residual toolkit for hypotheses produced by others |
| S3 | Correlated evidence cannot be made safe — after documented mitigation, paired single-event evidence still degrades calibration beyond tolerance | Freeze cross-modal claims; ship single-modal evidence verification only until independence representation is fixed |
| S4 | Replay determinism cannot reach full attribution for the pinned environment | No capability claims are permitted; the product's core promise is rerunnable tests |
| S5 | The only viable data for a modality requires terms that violate the brief's privacy or license boundaries | Drop that modality. Do not renegotiate the boundary to keep the roadmap |
| S6 | Two independent M3 attempts fail to beat the best single modality on held-out splits | Conclude that the cross-modal system layer does not pay for itself at this scale; publish the negative result and remain a single-modal evidence system |
| S7 | E0/E1 show the realistic parameter regime is degenerate (unknown `f0`/offset/geometry trade-offs make the state unidentifiable) | Claim only the smaller contribution: identifying when the inverse problem is unanswerable, with the identifiability analysis as the result. Do not reframe it as a localization success |

S1–S7 are the program-level falsifiers. The research program's F1–F4 ([research-program.md](../research/research-program.md)) are the same conditions stated in scientific terms; F4 is S7.

A pivot keeps the invariants and the evidence store; it may change the capability claim. A stop publishes the failures and the artifacts so that the negative result is reusable. In both cases the report is published before the decision is announced.
