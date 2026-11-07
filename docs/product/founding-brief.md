# PhainoWeave — Founding Brief

**Status:** adopted 2026-11-04 · **Owner:** Haelio Tang · **Language:** English (canonical; Chinese projection in [`founding-brief.zh-CN.md`](founding-brief.zh-CN.md))

> **Authority order.** Newest Accepted ADR > [`ROADMAP.md`](../roadmap/ROADMAP.md) > this brief > research notes. This brief records *why the project exists and what it refuses to become*; the ROADMAP records *what is built next*. Where they disagree, the ADR wins and this brief gets amended — not bent.

---

## 1. One sentence

**PhainoWeave is open infrastructure for reconstructing hidden physical-world facts from ambient observations — and for keeping every reconstructed fact falsifiable.**

Audio, imagery, video, weather, aircraft tracks, satellite passes, terrain: each carries traces of the physical world that produced it. PhainoWeave turns those traces into evidence, evidence into *candidate world states*, and candidate world states into *tests a third party can rerun*.

*From observations to verifiable world states.*

**Naming.** *PhainoWeave* is the platform brand, from Greek φαίνω — to bring to light, to make appear — and *weave*, for evidence from different modalities interwoven rather than stacked. **Ambient Inference** is the name of the inference engine inside it (Rust crate family and Python SDK). *Environmental Intelligence Workbench* is the researcher-facing product layer; *Open World Evidence Infrastructure* is the developer/research-institution layer. The brand does not change if the domain widens; the engine name does not become the brand.

## 2. The problem, stated as a gap

A recording can contain no GPS, no EXIF, no metadata — and still be constrained by the world: an aircraft's Doppler curve, the propagation path of sound, terrain echoes, solar geometry, weather at that hour, ecological range, nearby infrastructure, the interval between two overflights. Individually these are weak, differently-precise, and sometimes mutually contradictory. Today's tools treat them as separate party tricks — one repo for aircraft Doppler, one benchmark for birdsong, one model for cross-view image geolocation, one OSINT toolkit for manual verification.

The missing layer is not another modality model. It is **the system layer**: how do heterogeneous, noisy, correlated, partly-licensed clues become one world-state inference that is **verifiable, refutable, explainable, and reproducible**?

## 3. The unit of output

PhainoWeave does not output a location. It outputs a **world-state hypothesis with its verifier**:

- candidate region / candidate time window / candidate environmental state — as a *distribution*, never a point estimate dressed as an answer;
- the supporting and conflicting evidence, each with provenance and stated error;
- the physical constraint residuals (how badly the hypothesis fails to explain the observation);
- a calibration statement and an explicit **abstention** when evidence is insufficient.

Formally the target is a posterior over location, time, and state:

```
P(L, T, S | O, D)
```

with `L` location, `T` time, `S` environmental/event state, `O` observational evidence, `D` public data and physical constraints. The deliverable is the region/time distribution and its residuals — not the argmax.

## 4. The core capability (the one thing that must work)

> **Given a candidate world state, the system independently predicts what should have been observed there and then, compares that prediction with the actual observation, and localizes the inconsistency.**

This is the line between "AI guesses the world" and "a model proposes world hypotheses; physical constraints test them". Everything else in the project exists to make that loop trustworthy: the ontology records what is observed versus inferred versus verified; the inferencer contract forces every plugin to expose its residuals; the runtime makes the whole loop replayable.

## 5. What PhainoWeave is not

Non-goals are binding, not aspirational:

1. **Not a GeoGuessr.** Map accuracy is a byproduct. A point estimate without evidence, residuals, and calibration is a defect, not a feature.
2. **Not a covert individual-tracking tool.** Default output is region-level. Precise localization of private individuals is out of scope; precise localization of *places* requires an authorized, audited research task (see [`docs/policy/ethics-and-privacy.md`](../policy/ethics-and-privacy.md)).
3. **Not an oracle.** Language models may propose features, hypotheses, and review critiques. They may not promote an unverified inference to fact, and no LLM output is ever the last step of a verification.
4. **Not a Palantir clone.** The design borrows four disciplines — an operative world ontology (Foundry), an investigation surface (Gotham), agent tooling with evals (AIP), continuous deployment of pieces (Apollo). It rejects military targeting, real-time operational command, and person-level behavioral surveillance outright.
5. **Not a data lake first.** M0 stores core objects in SQLite; DuckDB/Parquet/H3 arrive when the analytical workload justifies them. A platform that owns no data contract is not a platform.
6. **Not a foundation-model training project.** We rent or wrap specialized models; we build the evidence, constraint, and verification substrate.

## 6. Design invariants

These are enforced in the object model (see [`world-ontology.md`](../specs/world-ontology.md)), not left to reviewer discipline.

| # | Invariant | Consequence |
|---|---|---|
| I1 | **Observation, inference, and verified fact are three separate layers** | "The model detected aircraft noise" ≠ "an aircraft was present" ≠ "this is where it was recorded". The data model cannot express the second as the third. |
| I2 | **Provenance by default** | Every derived record cites source, license, data version, processing program, model weights, parameters, and run. PROV-O-aligned vocabulary so it stays interoperable. |
| I3 | **Bitemporal** | Event time (when it happened) and record time (when we learned it) are distinct; historical reanalysis updates must not silently rewrite the past. |
| I4 | **Uncertainty is first-class** | Spatial regions, temporal intervals, and calibration are typed fields, not floats bolted on at report time. |
| I5 | **Contradiction is data** | Mutually exclusive hypotheses coexist with explicit conflict edges. No last-writer-wins. |
| I6 | **Reproducibility** | A run record pins observation hashes, data snapshots, inferencer versions, model weights, physical parameters, ontology version, and execution environment. Same inputs ⇒ same record, or the difference is attributable. |
| I7 | **Evidence independence is tracked** | Rain seen in imagery and rain heard in audio are one weather event, not two votes. Correlated evidence must not multiply confidence. |
| I8 | **Abstention is a valid answer** | Insufficient evidence is a success mode, measured in evals, not a failure to hide. |
| I9 | **Actions are typed and permissioned** | Scientific actions only — `ExtractFeatures`, `ProposeHypothesis`, `RunSimulation`, `ChallengeHypothesis`, `RequestReview`, `PublishEvidence` — each with an authority check and an audit record. |
| I10 | **License and sensitivity travel with data** | A `Source` carries license, access terms, intended use, and sensitivity. Downstream results inherit the strictest applicable constraint. |

## 7. Domain model in one table

Nine core objects. Normative definitions, relations, and actions live in the spec; this is the shared vocabulary.

| Object | Meaning |
|---|---|
| `Source` | An original data source with license, version, acquisition method, sensitivity |
| `Observation` | A recording, image, video, or sensor record — raw, immutable, content-addressed |
| `Feature` | A measurable extracted from observations (spectrum, shadow direction, acoustic event) |
| `Entity` | A real-world object or class: aircraft, railway, weather system, terrain, species |
| `Event` | A physical occurrence over a time interval (overflight, rainfall, eclipse) |
| `Constraint` | A physical or data-backed restriction linking observations to world states |
| `Hypothesis` | A candidate world state (location × time × state) awaiting test |
| `InferenceRun` | One execution: inferencers, parameters, data snapshot, environment |
| `Verification` | The test of a hypothesis: residuals, support, conflict, verdict |

## 8. Architecture

```
 Observations (audio · image · video · sensor)
        │
        ▼
 Data Fabric        adapters, normalisation, versioning, quality, licensing
        │
        ▼
 World Ontology     nine core objects, typed actions, permissions  [Rust core]
        │
        ▼
 Evidence Graph     provenance, dependency, independence, contradiction
        │
        ▼
 Inferencers        acoustic · visual · astronomical · meteorological · ecological
        │           one plugin contract: hypotheses, scores, residuals, refs, errors, version
        ▼
 Verifiers          Doppler kinematics · solar ephemeris · acoustic propagation ·
        │           terrain/geometry · meteorological consistency
        ▼
 Inference Runtime  runs, scheduling, replay, counterfactual re-runs
        │
        ▼
 Surfaces           CLI first · Investigation Workbench (Tauri + React + MapLibre) later
```

Deployment modes are phased, not simultaneous: **Local** (single researcher, privacy), **Research Node** (lab-shared compute and index), **Cloud Worker** (bulk public data), **Edge Node** (field sensors), **Air-gapped** (archived, restricted analysis).

## 9. Stack boundary

- **Rust** — core runtime: ontology contracts, evidence store, scheduling, permission checks, event log, plugin host, reproducible runs.
- **Python** — scientific inference: DSP, computer vision, Bayesian inference, physical solvers, statistical calibration, ML experiments.
- **DuckDB + Parquet/GeoParquet + H3** — analytical layer for bulk spatiotemporal queries (after M0; SQLite serves core objects first).
- **Tauri + React + MapLibre** — investigation workbench (M2), not day one.
- **Interfaces** — a stable object API and an inferencer SDK, so an acoustic researcher and an ecologist can extend the system without reading each other's code.

## 10. Milestones and acceptance

Full acceptance criteria and sequencing live in [`ROADMAP.md`](../roadmap/ROADMAP.md). Summary:

| ID | Milestone | Load-bearing acceptance |
|---|---|---|
| M0 | **World Ontology Foundation** | An authorized observation produces a complete evidence chain; every derived record traces to raw data, version, and run; bitemporal, contradiction, and independence invariants are enforced by tests. |
| M1 | **Acoustic Inference Vertical** | On controlled and publicly-licensed audio, a Doppler/kinematic constraint demonstrably improves inference over a learned prior alone; benchmark report published *including failures*, with error distribution, candidate coverage, false positives, abstention. |
| M2 | **Investigation & Hypothesis Engine** | A complete investigation is replayable; changing one hypothesis flags exactly the affected inferences; map + timeline + evidence graph + simulation view are one workspace. |
| M3 | **Cross-modal Reasoning & Evals** | Multi-modal beats best single modal on held-out data by a stated margin; correlated-evidence overconfidence is measured and mitigated; agent/tool eval suite compares versions. |
| M4 | **Distributed Research Infrastructure** | The same task replays identically on a local machine and an independent node; cross-version result differences localize to data / model / software changes. |

## 11. Evaluation stance

Success is not "how many locations were guessed right". The measured set is:

- localization **error distribution** (not a mean alone) and candidate-region **coverage** (recall at a given area);
- **calibration** (reliability diagrams, expected calibration error over region probabilities);
- **false-positive rate** at the precision the system claims to offer;
- **abstention behavior** — selective risk/coverage curves, not abstention rate in isolation;
- **correlated-evidence overconfidence** — paired evidence from one physical event must not improve calibration spuriously;
- **generalization** under geographic and temporal isolation splits, plus negative and null cases;
- **replay determinism** — a rerun's record must be bit-identical or the delta must be attributable.

Preregistration and negative results are required, not optional. See [`benchmark-and-evals.md`](../roadmap/benchmark-and-evals.md).

## 12. Hard boundaries (privacy, dual use, law)

1. **Region-level by default.** Precise spatial output requires an explicit, logged authorization and a defined research purpose.
2. **No covert tracking of people.** No output whose purpose is to locate a private individual or reveal a private residence. Person-level behavioral inference is out of scope.
3. **No military, targeting, real-time operational command, or enforcement use.** These are excluded from the project's intended use, its docs, and its examples.
4. **Public data ≠ free data.** Every `Source` carries license, access limits, and sensitivity; results inherit them.
5. **Red team before capability.** Any new modality that materially raises precision passes an ethics review and a documented misuse test before merge.

Detail, roles, and the review procedure: [`ethics-and-privacy.md`](../policy/ethics-and-privacy.md) and [ADR 0005](../decisions/0005-privacy-and-dual-use.md).

## 13. Known risks and open questions

- **Wild-audio generalization is unproven.** The public aircraft-Doppler reproduction reported, on held-out recordings, 2 of 18 broadband samples and 1 of 14 tonal samples inside a 3 km radius, with median errors around 12–13 km (external claim from its published evaluation; see [landscape](../research/landscape.md)). That is a case study, not a capability estimate. M1 must measure it, including failures.
- **Data ceilings are real.** OpenSky's full historical archive is research-eligibility-gated; ERA5's distributed product is 0.25° (~25 km on a native ~31 km grid), ERA5-Land is ~9–11 km, and ECMWF IFS ~9 km. None of them supports street-level claims; calibration must say so.
- **Correlated evidence inflates confidence** — the most likely way this project produces plausible nonsense. Invariant I7 exists for this reason; M3 measures it.
- **Benchmark contamination and domain shift** — geographic isolation splits and time isolation are required, but no split fully proves generalization.
- **Ontology over-engineering** — a nine-object model can become a bureaucracy. M0 keeps it minimal; additions need an ADR.
- **Reproducibility under external data drift** — historical weather and track datasets get revised. Snapshotting data versions is mandatory, not advisory.
- **Legal exposure** — privacy law varies by jurisdiction; precise geolocation of places can deanonymize people. Defaults must be safe without legal review per query.

## 14. Prior art we build on (survey: [`landscape.md`](../research/landscape.md))

Aircraft-Doppler geolocation demonstrations and reproductions · distributed acoustic sensing of aircraft (npj Acoustics 2025) · satellite-to-soundscape joint representation (Sat2Sound) · bioacoustic geolocation (*Bioacoustic Geolocation*, arXiv 2505.18726, ICML 2026) · cross-view image geolocation (GeoBridge, CVPR 2026) · OSINT verification practice (Bellingcat toolkit) · OpenSky Network, Open-Meteo, OpenStreetMap, Copernicus DEM, GeoSound · W3C PROV-O for provenance · Palantir Foundry/Gotham/AIP/Apollo as *design* analogies only.

## 15. Provenance of this document

Derived from the founder's project brief of 2026-11-04 (written in Chinese; preserved as [`founding-brief.zh-CN.md`](founding-brief.zh-CN.md)). This English text is the canonical projection. Decisions taken from the brief are recorded as ADRs 0001–0006. Numbers labeled as external claims remain claims until reproduced in this repository.

Corrections of 2026-11-04 (factual only, no decision changed): the reproduction figures are named with their run sets, the reanalysis products are named separately (ERA5 / ERA5-Land / IFS) instead of conflated, and the bioacoustic prior art is cited by its current title. The Chinese projection was written before these corrections and is updated with them.
