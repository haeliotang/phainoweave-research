# ADR 0003 — World Ontology, Three Evidence Layers, and PROV-O-Aligned Provenance

**Status:** Accepted · **Date:** 2026-11-04 · **Owners:** maintainer, ontology track · **Supersedes:** none · **Superseded by:** none

## Context

M0 must ship a data contract before it ships inference code, because every later component — inferencers, verifiers, runtime, surfaces — reads and writes the same nine objects. The [founding brief](../product/founding-brief.md) fixes the object list and invariants I1–I10 but leaves four choices open: where the invariants are enforced, how records are identified and revised, whether provenance gets its own storage model, and what "observation versus inference versus fact" means mechanically rather than rhetorically.

The decision has to hold under M0's constraints: one store on one machine, one writer, no server, region-level output by default, and several tracks writing code and prose in parallel against this contract. It also has to survive a future where the ontology is queried by people who were not in the room.

Three failure modes drive the decision. First, conflating layers: a detector firing becomes "an aircraft was here", which becomes "this is where the recording was made". Second, provenance as annotation: a results table with a free-text notes column, impossible to replay or license. Third, correlated evidence treated as independent votes, which is the brief's named most-likely path to plausible nonsense (I7). Each is cheap to allow and expensive to retrofit.

## Decision

**D1. Nine objects, closed set.** `source`, `observation`, `feature`, `entity`, `event`, `constraint`, `hypothesis`, `inference_run`, `verification`, plus the value objects `spatial_region`, `time_window`, `uncertainty`, `license`, and the relation record `evidence_edge`. Additions require a superseding ADR. The normative field definitions live in [`world-ontology.md`](../specs/world-ontology.md).

**D2. Three layers, enforced by an edge matrix.** L1 `source`/`observation`/`feature` (claims about the artifact), L2 `entity`/`event`/`hypothesis`/`inference_run` (claims about the world), L3 `verification` (claims about a hypothesis). A feature is L1 because a measurement of a recording never asserts a world state. `verification` is the only record type carrying a pass/fail verdict, and a hypothesis status moves only through logged transitions with a cause record.

**D3. Constraints are premises, not evidence.** A constraint is a versioned, licensed, citable premise with declared authority (`physics`, `dataset`, `assumption`); it may be cited by any layer and is never an endpoint of `supports`, `contradicts`, or `derives_from`. Verification binds it by residual. This keeps a wrong assumption visible and revocable instead of buried in evidence.

**D4. Identity is derived, not assigned.** Identifier = type prefix plus 16 hex of SHA-256 over the RFC 8785 canonical JSON of the record's identity tuple. Replay reproduces identifiers, equal identifiers across stores mean equal claims, and a conflicting re-insert is refused rather than overwriting. Corrections are new records; bitemporality comes from a store-assigned `_record_time`, not from mutating `event_time`.

**D5. SQLite first, one writer, append-only, content-addressed blobs.** One store directory contains `store.sqlite` (WAL, single writer) and `blobs/sha256/...`. Nested value objects are JSON columns validated by the typed core; media bytes never enter SQLite; append-only is enforced by triggers. DuckDB/Parquet/H3 are deferred until an analytical workload justifies them.

**D6. PROV-O is the export vocabulary, not the storage model.** Every record maps to PROV-O terms under a `pw:` prefix (mapping table in the spec), and one round-trip test asserts the mapping. No RDF store, no SPARQL dependency, no inference over the provenance graph in M0.

**D7. Independence and uncertainty are core functions.** `independence_key` groups correlated support; within a group one vote survives (max), across groups log-odds add, and `rank_score` never contributes to confidence. Uncertainty is typed at write time (`region`, `window`, `uncertainty`), not attached at report time. Both rules live in the core crate, not in plugins, because a rule an author can bypass is not an invariant. Output granularity is the enforced three-valued cap `region|point|none`; the four policy tiers of [ADR 0005](0005-privacy-and-dual-use.md) are a projection of that cap plus policy-owned floors ([ethics §3](../policy/ethics-and-privacy.md#3-capability-tiers)), never a fourth enum value.

**D8. Typed actions, three roles, append-only audit.** `ExtractFeatures`, `ProposeHypothesis`, `RunSimulation`, `ChallengeHypothesis`, `RequestReview`, `PublishEvidence`, each with preconditions and an audit row; roles `researcher < reviewer < publisher`. Single-user local mode grants everything to one identity and records `role_source: local_bootstrap` rather than pretending separation of duties exists.

**D9. Hard schema gate and ontology semver.** A store opens only when its recorded MAJOR.MINOR matches the code's; migrations are forward-only, one file per version, each with a fixture database and round-trip test.

**D10. Predictions are hypotheses, not observations.** `RunSimulation` writes an L2 `hypothesis` carrying `prediction_of` and `predicted_observables` in `claim.state`, linked by `derives_from`. The core capability of the brief — predict what should have been observed, compare, localize the inconsistency — therefore needs no tenth object and no privileged "prediction" record type, and a prediction is falsifiable on exactly the same terms as a world-state claim.

These decisions bind the specification. Anything not decided here — tombstone/erasure semantics, blob retention, federation, multi-writer merge, a typed constraint IR — is deferred rather than implied, and adding it requires its own ADR.

## Consequences

### Positive

- The invariants are checkable by tests over tables and triggers rather than by reviewer memory, which is the only way I1–I10 survive contact with contributors.
- A third party can replay an evidence chain from a published bundle without running this codebase, which is the point of the project.
- PROV-O export gives interoperability with provenance tooling without committing the core to an RDF stack.
- Drift between the specification, the Rust types, and the Python contract becomes a compile failure or a conformance failure rather than documentation debt.
- Per-run provenance makes failure attribution actionable: "the run was nondeterministic" and "the data snapshot changed" are distinguishable from "the inference is wrong".

### Negative / costs

- Nine tables and a curated field set cost more than a JSON blob, and the set will need discipline (and ADRs) to stay minimal.
- Content-derived identifiers behave unlike UUID systems: dedupe, attribution, and merge semantics must be explained to operators, and a hurried script cannot mint a plausible-looking id.
- The hard MAJOR.MINOR gate blocks rolling upgrades and forces a migrate-then-restart step on every minor change.
- Single-writer storage defers the Research Node mode until M4, and one schema change still touches Rust, Python, fixtures, and the specification simultaneously.
- Append-only storage grows without a retention policy for blobs or for superseded records; that policy is named as deferred, not solved.
- Several invariants (edge matrix, combination function, license lattice) require a test corpus that does not exist yet; until it does, the claim "enforced" is a design statement, not a measured fact.

## Alternatives considered

- **Free-form JSON document store.** Fastest to start, but every invariant becomes a validator someone must remember to call, contradiction has no representation, and provenance becomes a convention. Rejected: it moves the hard part from schema design to perpetual review.
- **RDF triple store first.** Natural fit for PROV-O and for justifying claims with edges, but the science needs typed vectorized computation over regions, windows, and residuals; a triple store forces every numeric field through literals and either duplicates the model or makes the core slow. Rejected for M0; the export mapping keeps the door open.
- **Graph database first.** Good for traversal, wrong for the primary workload (bulk append plus geometric-temporal predicates) and it adds a second engine to keep consistent with SQLite for no M0 benefit. Rejected.
- **Single flat evidence table.** One wide table with a `kind` column and JSON payload is the tempting simplification; it makes layers a convention, permits a status column shared across kinds, and makes the edge matrix unenforceable. Rejected as the precise shape of the failure mode the project exists to avoid.
- **Random UUIDs for identifiers, mutable rows for corrections.** Simpler to write, but replay cannot reproduce identifiers and "no silent rewriting of the past" becomes a policy rather than a property. Rejected.

## References

[Founding brief](../product/founding-brief.md) · [World ontology specification](../specs/world-ontology.md) · [Inferencer contract](../specs/inferencer-contract.md) · [Architecture overview](../architecture/overview.md) · [ROADMAP](../roadmap/ROADMAP.md) · [Ethics and privacy](../policy/ethics-and-privacy.md) · [Benchmark and evals](../roadmap/benchmark-and-evals.md) · W3C PROV-O (external standard; terms used as published) · RFC 8785 JSON Canonicalization Scheme (external standard).
