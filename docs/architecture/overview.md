# PhainoWeave System Architecture — M0

**Purpose:** state the layer responsibilities, process boundaries, deployment modes, and end-to-end path of one observation, so that every component's authority is explicit before code exists. · **Status:** Normative architecture, 2026-11-04, tracks M0 of the [ROADMAP](../roadmap/ROADMAP.md); the object vocabulary it implements is defined only in [`world-ontology.md`](../specs/world-ontology.md).

## 1. System shape

Logical flow, top to bottom; each arrow is a typed data contract, not a call into shared mutable state:

```
 ambient data ──► [DATA FABRIC]      adapters · license resolution · snapshot ids · checksums
                      │ L1: source, observation, blob
                      ▼
                  [ONTOLOGY CORE]    types · identity derivation · layer matrix · SQLite projection
                      │ records + edges
                      ▼
                  [EVIDENCE GRAPH]   provenance closure · independence keys · as-of · conflicts
                      │ evidence bundles
                      ▼
                  [INFERENCERS]      plugin contract · candidates · provisional residuals
                      │ candidate claims
                      ▼
                  [VERIFIERS]        registered residual functions · recomputed residuals · L3 verdicts
                      │ verification log
                      ▼
                  [RUNTIME]          actions · roles · audit · run records · replay
                      │ published bundles
                      ▼
                  [SURFACES]         CLI (M0) · investigation workbench (M2, deferred)
```

Nothing skips a layer: an inferencer cannot write, a verifier cannot propose, a surface cannot reach the store except through a typed action. The single exception is read-only inspection for surfaces, which is a projection, not a write path.

Process topology on one host:

```
 phaino process (single writer)
 ├── cli             argv → ActionRequest; renders records and bundles
 ├── runtime         action dispatch, role check, audit, run recorder, replay driver
 ├── core            crates/phaino-core: ontology types · store · graph queries · verifier registry
 ├── store           store.sqlite (WAL) + blobs/sha256/aa/bb/<digest>
 └── inferencer host spawns one sandboxed process per run; the store handle is never passed through
                      ├── python plugin   python -m phaino_sdk.runner <plugin_dir>
                      └── rust plugin     in-process behind the same Inferencer trait
```

M0 is one process plus plugin children. There is no message queue, no service mesh, no second database, and no network listener.

## 2. Layer responsibilities and boundaries

| Layer | Owns | May read | Must never | On failure |
|---|---|---|---|---|
| **Data fabric** | acquisition adapters, license resolution, `source` and `observation` writes, blob ingestion, external dataset snapshot ids | network (adapters only), local files, source terms | interpret content, infer anything, write L2/L3 | refuse the ingest with a typed error and an audit row; no partial source |
| **Ontology core** | type definitions, identity derivation, layer matrix, SQLite schema and migrations, value-object validation | everything in the store, licences | hold domain inference logic, call plugins | abort the write; a store that fails validation stays unchanged |
| **Evidence graph** | edge table queries, provenance closure, independence grouping and `combine_support`, as-of projection, contradiction enumeration | record tables and edges | own a second storage engine, mutate records | return an explicit `unavailable`/`incomplete` result rather than an empty graph |
| **Inferencers** | candidate claims, score declarations, provisional residuals, abstention | the request document only (media paths, features, snapshots) | write, verdict, combine evidence, network | typed failure recorded on the run; no candidates accepted |
| **Verifiers** | residual recomputation, `verification` rows and verdicts | L1 features, L2 hypotheses, pinned constraints | propose hypotheses, call inferencers, read licences at a wider scope | verdict `inconclusive` with the failure noted; never a silent pass |
| **Runtime** | action dispatch, role enforcement, audit log, run records, replay and counterfactual re-runs | the store, action registry | compute science, bypass role checks, edit records | fail the action atomically; audit records what was refused |
| **Surfaces** | CLI verbs and output rendering (M0), workbench (M2) | published bundles and read-only projections | write records, hold a store handle, call plugins directly | degrade to the previous valid projection and report staleness |

Boundaries worth stating, because each one is load-bearing:

- **The evidence graph is a query layer, not a database.** Edges and records live in the same SQLite store; provenance closure and independence grouping are functions in the core. Giving the graph its own store would create two sources of truth and allow a record to exist in one and not the other.
- **The platform is Rust; the science is Python.** Only the core enforces invariants. Python plugins are extension points, so they sit behind a process boundary with a document contract ([inferencer contract](../specs/inferencer-contract.md)) and no store handle.
- **Verifiers are compiled in, not plugins.** A verifier that an author can replace can be made to pass. M0 verifiers are registered `residual_function` symbols in the core, versioned with the ontology; adding one is a code change with tests, not configuration.
- **Feature extraction is an action; content interpretation is not.** The data fabric copies bytes and records terms; it never decides what the bytes mean. That keeps L1 writes mechanical and auditable.
- **LLMs are inferencers at most.** An LLM may be registered as a plugin that emits candidates with scores, subject to the same contract and the same zero write authority. No LLM output is a verdict, and there is no path from a language model to a `ver` row ([founding brief](../product/founding-brief.md) §5).

## 3. Contracts between layers

Each arrow in §1 is a versioned document, not a function call. A layer may not reach into another layer's storage, and a change to a contract is a version bump with a conformance test rather than a quiet patch.

| From → To | Artifact | Producer guarantees | Consumer obligation |
|---|---|---|---|
| data fabric → ontology core | `source` and `observation` records plus blob digests | licence and sensitivity copied verbatim; checksum computed on the exact bytes | validate and store; never re-derive terms |
| ontology core → evidence graph | record tables, edge table, value objects | identifiers, layers, digests conform to the spec | read-only; may not create records |
| evidence graph → inferencer | request document, contract 1.0 | closed `evidence_scope`; snapshots pinned by checksum | cite only in-scope ids; declare every snapshot read |
| inferencer → runtime | response document, contract 1.0 | own name and version, determinism, score semantics | validate, clip, combine, and write; never trust a verdict |
| runtime → verifier | hypothesis pinned to a run, evidence scope, constraint versions | constraints and residual functions resolved at fixed versions | recompute residuals; may not substitute a constraint or a hypothesis |
| verifier → runtime | verification candidate: residuals, verdict, confidence | residual values with units, pass implication respected | validate and append; never edit a prior verification |
| runtime → surface | published bundle manifest | licence envelope, record digests, replay key | render only; may not add or reinterpret records |
| surface → runtime | `ActionRequest` (action, targets, parameters) | actor identity and declared role | enforce role, preconditions, and audit |

## 4. Storage and consistency

One writer process, WAL mode, append-only tables, and content-addressed blobs. Runs are the unit of transactionality: a run record plus everything it produced either lands together or the store is left as it was; the identity/digest rule ([ontology §2](../specs/world-ontology.md)) makes a retried insert idempotent, which is what lets the runtime retry a crashed action without duplicating evidence. Reads are consistent snapshots at the store's current `_record_time`; as-of queries decorrelate knowledge time from event time.

External datasets (weather fields, state vectors, terrain tiles, ephemerides) never enter the store as records. The fabric mints an immutable snapshot id with a checksum, the run cites `data_snapshot_ids`, and the artifact is retained outside SQLite. A refreshed dataset is a new id; there is no in-place update of a snapshot, because that would silently change what a historical run could have seen.

## 5. Concurrency and ordering

One writer per store is a correctness decision, not an implementation convenience: append-only ordering, monotone `_record_time`, and the idempotent-insert rule all assume a single sequencer. Readers may run concurrently with the writer (WAL snapshot reads) and see a consistent prefix. Plugin processes run concurrently only in the sense that the host may dispatch several runs; their writes are serialized by the single writer, so a run's outputs land as one contiguous group in the log even when execution overlaps. Ordering between runs is therefore execution order, not causal order; causality is expressed by identifiers and edges, never by timestamps.

## 6. One observation end to end

| Stage | Actor | Records written | Failure or abstention path |
|---|---|---|---|
| S0 acquire | data fabric | `source`, `observation`, blob | checksum mismatch or unreadable media ⇒ refuse ingest, audit |
| S1 snapshot | data fabric | snapshot id (not a record) | missing external dataset ⇒ `dependency_unavailable` |
| S2 extract | runtime + plugin (`ExtractFeatures`) | `run`, `feature`(+joins), audit | plugin error/timeout ⇒ run failed, no feature, no downstream record |
| S3 propose | runtime + plugin (`ProposeHypothesis`) | `run`, `hyp`, `supports` edges, audit | abstention ⇒ run records `abstained`, no hypothesis, no verdict |
| S4 predict | runtime + plugin (`RunSimulation`) | `run`, prediction `hyp`, `derives_from` edge | numeric failure ⇒ run failed; predictions are never silently skipped |
| S5 verify | verifier | `ver` with residuals, audit | untestable claim ⇒ `inconclusive`; residual exceeds tolerance ⇒ `fail` |
| S6 transition | store | `status_transition` row | conflicting verdicts ⇒ status returns to `under_test`; both verifications stay |
| S7 contest | reviewer or researcher (`ChallengeHypothesis`) | `run`, `contradicts` edge, audit | challenge not allowed ⇒ refused with reason, audit |
| S8 publish | publisher (`PublishEvidence`) | bundle manifest + audit | licence or sensitivity gate fails ⇒ refused, audit, no bundle |
| S9 replay | runtime | comparison report (not a record) | `_replay_key` differs ⇒ runs are not comparable and are reported as such |

Worked reading: a raw audio file becomes a `source` and an `observation` in L1 with a blob digest; a plugin turns the bytes into a Doppler feature, still L1; another plugin proposes an L2 hypothesis with a region and a window and a support edge whose `independence_key` names the source; a verifier recomputes the constraint residual and writes the only L3 record; the runtime moves the hypothesis status with a cause pointer; publication packages the hypothesis, its verifications, its evidence closure, and the licence envelope into a bundle that a third party can replay. Every stage is either an inserted record or a typed refusal.

Replay is comparison, not re-execution: the runtime rebuilds the run's input set from `_replay_key`, re-executes, and compares `record_digest` values. Differences are attributed to one of the fields the digest covers — environment, outputs, or a plugin version — and a run declared `nondeterministic` is compared on its claim set and residuals, never claimed bit-identical. M4's cross-node requirement is this same comparison across stores; M0 builds the mechanism and one local fixture.

## 7. Deployment modes

| Mode | Topology in M0 | Status | Binding constraint |
|---|---|---|---|
| **Local** | one process, one store, one local identity, adapters run on demand | **supported** | region-level default output; network only when an adapter is explicitly invoked |
| **Research Node** | shared store and index across a lab's machines | **deferred** (export/import bundles only) | multi-writer concurrency and role separation are not implemented; a shared writer would silently break append-only ordering |
| **Cloud Worker** | ephemeral container per run, object-store blobs, network store | **deferred to M4** | no network listener exists in M0; would need the store as a service and per-run isolation |
| **Edge Node** | device-local store, periodic bundle export | **deferred** | power/thermal budgets and limited licence scope; M0 assumes a workstation |
| **Air-gapped** | Local with adapters disabled, snapshots imported as bundles | **supported as a configuration** | no adapter can reach the network; the licence gate and region floor are identical, since they are not runtime-optional |

Deployment does not change the object model. A mode changes transport, identity, and process boundaries only; if a mode would require a schema change, the mode is wrong for M0.

## 8. Trust boundaries and failure modes

| Boundary | Mechanism | Residual risk |
|---|---|---|
| plugin ↔ host | separate process, one request/one response, budget enforced by the host, read-only media paths, no store handle, no network | the sandbox is a resource and policy boundary; M0 assumes a trusted plugin set shipped with the repo and does not claim hostile-code isolation |
| adapter ↔ network | only the fabric performs I/O, and only when an adapter is invoked | terms misread or a source silently changes access level; mitigated by snapshotting licences and by refusing silent relicensing |
| store ↔ filesystem | single writer, digest verification on read, WAL | disk corruption and no cryptographic signatures: checksums detect accidental corruption, not tampering |
| publish ↔ world | licence lattice meet, region floor, `person_data` refusal, audit | the numeric floor is a policy default, not a legal judgment; publishing remains a human role by design |
| verifier ↔ physics | compiled-in residual functions tied to constraint versions | a residual can be correctly computed from wrong physics; versioned constraints and explicit `authority` keep the premise visible rather than hidden in code |
| surface ↔ store | read-only projections and typed actions | a surface that grows a write path bypasses role checks; the CLI is the only M0 surface partly to keep this small |

Degradation rules: a crashed plugin fails one run; a crashed runtime fails the process and the store remains consistent (single writer, WAL, idempotent inserts); a failed verifier yields `inconclusive`, never `pass`; a missing snapshot fails the run with a typed code; an unavailable graph query returns explicit incompleteness. There is no component whose failure can promote an unverified claim, which is the property that makes the rest tolerable.

## 9. Audit and observability

Every state change passes through a typed action and leaves one append-only audit row: actor, declared role, action, target identifiers, canonical parameter digest, run id where applicable, timestamp, and the policy digest in force. The run records are the telemetry: inputs, versions, parameters, environment, determinism, output digests. There is no separate metrics pipeline in M0 and no payload logging: diagnostics are bounded, redacted strings, and evidence bytes are never copied into logs. A question of the form "why does this record exist" is answered by following one audit row and one run record, which is the minimum standard for a system whose output is a claim about the world.

## 10. What M0 builds, in order

1. Ontology types, identity derivation, layer/edge validation, SQLite schema and append-only triggers — the invariants first, because retrofitting them is a rewrite.
2. Store read/write paths, as-of projection, digest and replay-key computation, idempotent insert.
3. Runtime action dispatch with roles, audit rows, and honest single-identity mode.
4. Data fabric with one local-file adapter and licence resolution: enough L1 to exercise the chain.
5. Plugin host plus the Python SDK; one acoustic feature extractor and one kinematic verifier, both narrow and tested.
6. Publish bundle writer and reader, replay comparison, and the conformance suite that makes the invariants checkable.

The workbench, DuckDB/H3 projection, distributed replay, and the multi-modal inferencer set are explicitly not in this path ([ROADMAP](../roadmap/ROADMAP.md), [ADR 0003](../decisions/0003-world-ontology-and-provenance.md)).

## 11. Architectural non-goals

Microservices or a shared database server; an RDF store behind the PROV-O mapping; an ORM or a second object layer over the typed core; a plugin marketplace or third-party plugin distribution; model serving and weight hosting; a graph database; the investigation UI before M2. Each of these would add a component whose authority overlaps a layer above, and each is deferred rather than designed around.
