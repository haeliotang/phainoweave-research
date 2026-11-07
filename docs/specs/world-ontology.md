# PhainoWeave World Ontology — M0 Normative Specification

**Purpose:** define the nine-object world model, its invariants, and its SQLite projection so that every record's layer, provenance, time, uncertainty, and license is machine-enforced. · **Status:** Normative draft, `ontology 0.1.0`, 2026-11-04; changes to object vocabulary or invariants require an ADR ([ADR 0003](../decisions/0003-world-ontology-and-provenance.md)).

Scope is M0 as described in the [founding brief](../product/founding-brief.md) and [ROADMAP](../roadmap/ROADMAP.md). This spec is the contract that the Rust core crate (`crates/`, see [architecture overview](../architecture/overview.md)) implements and the [inferencer contract](inferencer-contract.md) produces into. Where this document says MUST, the Rust core crate is expected to enforce it and the [ROADMAP](../roadmap/ROADMAP.md) carries the acceptance tests.

## 1. Scope, terms, notation

A **record** is an immutable object instance stored once with a stable identifier. A **value object** is an embedded structure with no identity of its own (`license`, `spatial_region`, `time_window`, `uncertainty`). A **producer** is any component allowed to write records: ingest adapters (L1), inferencers (L2), verifiers (L3). Only the runtime writes; producers submit typed actions (§9).

Notation: `ID<t>` is an identifier of type `t`; `opt<T>` an absent-or-present value; `list<T>`, `map` (arbitrary string-keyed JSON object), `json` (arbitrary JSON), `instant` (RFC 3339 UTC, microsecond precision, `Z`), `sha256` (64 lowercase hex), `window` = [`time_window`](#5-value-objects), `region` = [`spatial_region`](#5-value-objects). Field names are normative and snake_case; a Rust or Python type may not rename them.

## 2. Identifier scheme

Identifiers are `<prefix>_<d16>` where `d16` is exactly 16 lowercase hexadecimal characters. Grammar: `^(src|obs|ftr|ent|evt|con|hyp|run|ver)_[0-9a-f]{16}$`. The store MUST reject any other identifier and any type/prefix mismatch. Identifiers are opaque: no consumer may parse, order by, or extend them.

Producers MUST derive `d16` from SHA-256 over the RFC 8785 canonical JSON of the record's **identity tuple** — the claim-bearing fields only, never store-assigned fields, timings, or outputs. Replay then reproduces identifiers (I6), and equal identifiers across stores mean equal claims, never equal provenance. The canonicalizer implementation (PCJ-0), its conformance vectors, and the `_replay_key` definition are fixed by [ADR 0006](../decisions/0006-canonical-json-and-digests.md); where this spec and that ADR differ on canonicalization, the ADR wins.

| Type | Identity tuple |
|---|---|
| `src` | `{uri, version}` |
| `obs` | `{source_id, media_kind, content_hash, captured_at, event_time, location_hint, attributes, license_snapshot}` |
| `ftr` | `{observation_ids sorted, extractor{name,version}, feature_kind, value, unit}` |
| `ent` | `{entity_kind, canonical_name, external_refs}` |
| `evt` | `{event_kind, time, region, participant_entity_ids sorted}` |
| `con` | `{constraint_kind, version, expression, parameters}` |
| `hyp` | `{claim, prior, ontology_version, created_by{inferencer,run_id}}` |
| `run` | `{ontology_version, seed, inputs, inferencer_versions sorted, parameters, started_at}` |
| `ver` | `{hypothesis_id, run_id, check_kind, constraint_ids sorted}` |

Collision rules: an insert whose identifier already exists with different canonical bytes is refused as `identity_conflict`; an insert identical byte-for-byte is an idempotent no-op. A source whose terms change MUST publish a new `version`, because a silent relicense is an `identity_conflict`; re-ingesting the same bytes under new terms yields a new `obs` record and leaves prior verifications citing the old one. Because `hyp` identity carries `created_by.run_id`, two runs proposing the same claim produce two records — M0 does not fuse them; the store maintains a `duplicate_claim` index over the claim digest and reports it, never merges it. A `ver` tuple permits exactly one verification per (hypothesis, run, check kind, constraint set); a re-check is a new run.

## 3. Three layers (I1)

A record's layer is fixed by its type, never by how it was produced. The layer names the *subject* of the claim.

| Layer | Height | Record types | Claim subject | Legal `derives_from`/`refers_to` targets |
|---|---|---|---|---|
| L1 Observed | 0 | `src`, `obs`, `ftr` | the artifact and its measurable content | L1 only |
| L2 Inferred | 1 | `ent`, `evt`, `hyp`, `run` | the physical world | L1, L2 |
| L3 Verified | 2 | `ver` | whether an L2 claim explains L1 evidence | L1, L2, L3 |

`feature` is L1 because it asserts something measurable *about the recording* ("the artifact contains a Doppler crossing at t = 4.62 s"), never about the world. A learned extractor does not lift a feature into L2; it only makes `extractor`, `run_id`, and `uncertainty` mandatory.

`constraint` belongs to no layer: it is a versioned **premise** (physics, dataset, or stated assumption) that L2 and L3 cite. Premises are licensed, versioned, and independently replaceable; evidence and premise are stored in different tables so a premise can be revoked without rewriting history, and so that unfalsifiable claims cannot hide inside evidence. It is exempt from the height rules: it may be the `refers_to` target of any layer and is never an endpoint of `supports`, `contradicts`, or `derives_from` — verification binds it through `verification.residuals`.

`evidence_edge` belongs to no layer either: it is the relation over records, and it is where the layering becomes mechanical.

**Merging** means one record asserting both an observation and a world-state claim, a status column shared across layers, or an inference promoted to fact by update. None is expressible. The store has one table per type, no cross-layer status vocabulary, and a write trigger that refuses any edge violating this matrix:

| Edge kind | Allowed `from` | Allowed `to` | Rule |
|---|---|---|---|
| `derives_from` | L1, L2, L3 | any | `height(from) ≥ height(to)`; a claim may not beget data |
| `supports` | any | L2, L3 | target must be a claim; no self-edge; no L1→L1 |
| `contradicts` | any | L2, L3 | as `supports`; conflicts are records, not deletions (I5) |
| `refers_to` | L1, L2, L3 | any | `height(from) ≥ height(to)`; no upward citation from L1 |
| `same_event_as` | same type only | same type only | stored once with `from_id < to_id`, queried symmetrically |

`supports` and `contradicts` may point upward from L1 to an L2/L3 claim (that is how evidence bears on a hypothesis); they may not point between two L1 records. The critical prohibition is `derives_from` from L1 to L2 or L3: a hypothesis may not generate features, because features that were selected by the hypothesis are no longer independent evidence (I7), and predictions must be recorded as predictions (§12 shows how).

## 4. Invariants and their enforcement

| ID | Statement | Enforced by |
|---|---|---|
| I1 | Observation, inference, and verification are three layers | one table per type; edge matrix above; no cross-layer status column |
| I2 | Provenance by default | NOT NULL `run_id`/`created_by`/`ver.run_id`; PROV-O export test (§8) |
| I3 | Bitemporal | `_record_time` store column on every table; `event_time`/`captured_at` are claims; append-only tables; as-of views (§10) |
| I4 | Typed uncertainty | `region`, `window`, `uncertainty` are required where a coordinate or scalar would otherwise appear; no bare float fields for space, time, or state |
| I5 | Contradiction is data | coexisting records; `contradicts` edges; `status` moves only by logged transitions whose cause is a `ver` or audit record; record content never mutates |
| I6 | Reproducibility | identity tuples; `run` inputs/versions/parameters/seed/environment; `_digest`; replay key (§10) |
| I7 | Evidence independence | `independence_key` + the combination function below |
| I8 | Abstention is valid | `ver.verdict = inconclusive` and inferencer abstention are first-class (§11, [contract](inferencer-contract.md)) |
| I9 | Actions are typed and permissioned | six actions, three roles, append-only audit (§9) |
| I10 | License and sensitivity travel | license lattice meet over provenance roots; publish gate (§4, §9) |

### I7 — correlated evidence cannot multiply confidence

Evidence that supports a hypothesis is partitioned into groups by `independence_key`; support edges with no key fall back to `sources:<sorted unique source_ids of its L1 roots>` and, when there is no resolvable L1 ancestry, to `edge:<from_id>-><to_id>`. Evidence sharing an `independence_key` contributes at most once — within a group only the maximum contribution survives, and confidence is never multiplied — which is the rule the Rust core implements as `combine_support`. Across groups contributions add in log-odds. The combination returns, besides the score, the list of groups it collapsed and a `reason` string, so a caller can report that correlated evidence did not grow confidence. The store computes support, not the inferencer:

```
llr_clip(ℓ) = max(-c, min(c, ℓ))                      # c = llr_clip, run parameter, default 8 nats
group_value(g) = max over edges e in g of llr_clip(ℓ(e))   # ties: smallest from_id
score = logit(prior) + Σ_groups group_value(g)        # never a product anywhere
confidence = sigmoid(score)
collapsed = [g for g in groups if |g| > 1]           # groups whose extra members were suppressed
```

`ℓ` is the edge's declared log-likelihood ratio contribution, taken from the candidate's `score.value` when `score.semantics = log_likelihood_ratio`, from `logit(p)` when `probability`, and never from `rank_score`. The function is order-invariant, group-size-invariant, idempotent under duplicate insertion with an equal `independence_key`, and returns `insufficient` when the support set is empty. Mandatory conformance test: a group of size n produces exactly the same `confidence` as a group of size 1 carrying the group's maximum clipped contribution, so adding a second edge with the same `independence_key` whose clipped value does not exceed the current maximum leaves `confidence` unchanged. (A correlated edge with a genuinely larger clipped LLR may raise the group value — that is the maximum rule, not multiplication.)

### I10 — license and sensitivity inheritance

`license` is a bounded lattice: `access_level` ordered `public < research < restricted`; `person_data` joined by OR; `max_output_granularity` ordered `none > region > point` in strictness (the *allowed* output is the meet, i.e. the coarsest). Effective license of a record = meet over the `license_snapshot` and the current `source.license` of every reachable L1 root. Snapshotting means a later source relicense can narrow a record's terms but never widen them. M0 policy: any record with `person_data = true` on a reachable root is unpublishable; `max_output_granularity = none` forbids `location_hint` and `claim.location`. The ontology enforces exactly three caps — `region`, `point`, `none` — plus non-degeneracy of the geometry; it does **not** own output resolution numbers. Output floors are policy parameters owned by [`ethics-and-privacy.md`](../policy/ethics-and-privacy.md) §3 (open-band default 0.25°, enforced minimum floor 0.05° with H3 resolution ≤ 7, `precise` requiring a signed authorization record), and the policy tiers `region`, `sub_region`, `precise`, `person_level` of [ADR 0005](../decisions/0005-privacy-and-dual-use.md) are a projection of that cap plus the floor: `region` and `sub_region` both sit under cap `region` and differ only by resolution floor, `precise` requires cap `point` plus authorization, and `person_level` is never emitted at any cap.

## 5. Value objects

`spatial_region = {kind: bbox|h3_cells|polygon, payload}`. Payloads: `bbox` → `{min_lon, min_lat, max_lon, max_lat}` in WGS84 degrees with `min_lon < max_lon` and `min_lat < max_lat` (antimeridian-crossing areas use `h3_cells` or a multi-polygon; a bbox with inverted bounds is invalid and rejected); `h3_cells` → `{resolution: int 0..15, cells: list<string>}`; `polygon` → `{geojson: object (Polygon|MultiPolygon, EPSG:4326)}`. Degenerate geometries are rejected: there is no point-region type in M0, which is what makes `max_output_granularity = point` structurally hard to satisfy rather than a matter of reviewer goodwill.

`time_window = {start: instant, end: instant, inner_confidence: float in [0,1]}` — half-open `[start, end)`, `start < end`; `inner_confidence` is the claimed probability mass inside the window, not a confidence about the endpoints. `uncertainty = {method: interval|distribution|monte_carlo, params: json, calibration_ref: opt<string>}`; `params` for `interval` is `{lo, hi, level}` in the feature's `unit`, for `distribution` a named family plus parameters, for `monte_carlo` a sample-artifact URI and count. A `calibration_ref` that does not resolve to a stored calibration artifact is a write error.

`license = {spdx: string, terms_url: string, access_level: public|research|restricted}`. `license_snapshot` on an observation is a full copy of the source's `license` at ingest time, so retroactive term changes are visible but not silently applied.

## 6. Objects

`source` — an acquisition channel and its terms.

| Field | Type | Semantics |
|---|---|---|
| id | ID<src> | identity (§2) |
| uri | string | canonical locator an adapter can resolve |
| title | string | human label |
| license | license | terms at acquisition; the only authoritative license record |
| version | string | upstream version label (not necessarily semver) |
| retrieved_at | instant | when the bytes were fetched |
| sensitivity | `{max_output_granularity: region\|point\|none, person_data: bool, notes: string}` | output ceiling and person-data flag |
| acquisition_method | string | `adapter:<name>/<method>@<version>` |
| checksum | sha256 | digest of the retrieved artifact set (manifest digest when a source is a set) |

`observation` — one immutable record of recorded media. `media_kind ∈ audio|image|video|sensor|document`.

| Field | Type | Semantics |
|---|---|---|
| id | ID<obs> | identity |
| source_id | ID<src> | acquiring source |
| media_kind | enum | selects adapter and feature families |
| captured_at | opt<instant> | device clock claim; may be absent or wrong, never authoritative for inference |
| event_time | window | when the recorded physical occurrence happened, as claimed |
| record_time | instant | when the system learned of it; MUST equal the storage `_record_time` |
| content_hash | sha256 | digest of the exact bytes; double duty as blob address |
| location_hint | opt<region> | spatial claim attached by the source, not inferred |
| license_snapshot | license | terms copied at ingest (§5) |
| attributes | map | adapter-specific fields; no semantic weight for invariants |

`feature` — a measurement of observation content. `feature_kind` is a dotted, registered name (`acoustic.doppler_crossing`, `image.shadow_azimuth`), never free text.

| Field | Type | Semantics |
|---|---|---|
| id | ID<ftr> | identity |
| observation_ids | list<ID<obs>> (≥1) | inputs; the store also writes `feature_observation` rows |
| extractor | `{name, version}` | program identity; `name` is `family/module` |
| feature_kind | string | registered vocabulary key |
| value | json | typed payload defined per `feature_kind` in the registry |
| unit | string | SI where one exists; `"1"` for dimensionless |
| uncertainty | uncertainty | mandatory; a feature without stated error is not storable |
| run_id | ID<run> | the run that produced it |
| created_at | instant | producer clock claim |

`entity` — a real-world object or class. `entity_kind ∈ aircraft|rail|weather|terrain|species|infrastructure|other`.

| Field | Type | Semantics |
|---|---|---|
| id | ID<ent> | identity; M0 ids are content-derived, so entity merge is a new record (§14) |
| entity_kind | enum | coarse class |
| canonical_name | string | normalized name within the class |
| external_refs | map | e.g. `{"icao24": "3c4b26"}`, `{"openstreetmap": "way/12345"}` |
| uncertainty | uncertainty | identity uncertainty; mandatory |

`event` — a physical occurrence over a time interval. `event_kind` is a dotted registered name (`overflight`, `rainfall`, `solar_eclipse`).

| Field | Type | Semantics |
|---|---|---|
| id | ID<evt> | identity |
| event_kind | string | registered vocabulary key |
| time | window | occurrence interval |
| region | region | occurrence area |
| participant_entity_ids | list<ID<ent>> | may be empty; stored as `event_participant` rows |
| uncertainty | uncertainty | mandatory |

`constraint` — a versioned premise that links observations to world states. `constraint_kind ∈ kinematic|acoustic_propagation|solar_ephemeris|geometric|meteorological|ecological`.

| Field | Type | Semantics |
|---|---|---|
| id | ID<con> | identity |
| constraint_kind | enum | selects the residual family |
| expression | string | formal text (LaTeX or code-shaped); documentation, not executed by the store |
| parameters | map | numerical premises (speeds, indices, coefficients) |
| applicable_kinds | list<string> | feature_kind / event_kind this may be applied to; empty means none |
| residual_function | string | registered symbol resolved by a verifier plugin, e.g. `kinematics.doppler_rms_v1` |
| tolerance | float ≥ 0 | pass threshold in the residual's unit; the residual declares its own scale |
| authority | enum | `physics` (derivable), `dataset` (empirical reference), `assumption` (explicit guess) |
| version | string | semver of this constraint record; parameters change ⇒ new version ⇒ new id |

`hypothesis` — a candidate world state. `claim = {location: region, time: window, state: map}`; `state` keys are inference-defined except reserved keys `prediction_of` (a `hyp` id) and `predicted_observables` (§12). `status ∈ proposed|under_test|supported|rejected|insufficient`; it moves only by recorded transitions with a `cause_id` (§10) and is never set directly by a producer. `created_by = {inferencer, run_id}`.

`inference_run` — one execution and its reproducibility envelope. `inputs.data_snapshot_ids` identifies external dataset snapshots (weather, tracks, tiles) minted by the data fabric; snapshots are not one of the nine objects, are immutable, and a refreshed dataset is a new snapshot id (see [architecture](../architecture/overview.md)). Model weights are pinned the same way — a weights file is provisioned as a checksummed snapshot — because the canonical record has no separate weights field: `inferencer_versions` names the program, the snapshot id names the bytes ([I2](../product/founding-brief.md)).

| Field | Type | Semantics |
|---|---|---|
| id | ID<run> | identity; includes `started_at` so re-executions are distinct |
| started_at, completed_at | instant | activity interval (`completed_at ≥ started_at`) |
| ontology_version | string | schema version the run was written against |
| seed | integer | root seed for all stochastic choices |
| inputs | `{observation_ids, source_ids, data_snapshot_ids, hypothesis_ids}` | resolved input set; every id must exist |
| inferencer_versions | list<`{name, version}`> | full plugin set, including dependencies of dependencies |
| parameters | map | every numeric knob that can change output, including `llr_clip` |
| environment | `{os, arch, runtime}` | executable environment strings |
| output_artifact_hashes | list<sha256> | digests of every produced artifact, including media |
| determinism | enum | `deterministic|nondeterministic|unknown`; worst of the plugin declarations |
| record_digest | sha256 | digest of the complete canonical record; equals `_digest` |

`verification` — the adjudication of an L2 claim. `check_kind` is dotted (`kinematic.doppler_fit`, `ephemeris.solar_azimuth`); `residual = {constraint_id, value: float, tolerance: float, pass: bool}` with `pass ⇔ |value| ≤ tolerance` (the store validates the implication and refuses rows where it fails). `verdict ∈ pass|partial|fail|inconclusive`: `pass` requires every residual passing and no conflict evidence; `fail` requires a failing residual or conflict evidence; `partial` requires at least one failing and one passing residual; `inconclusive` covers abstention and untestable claims. `notes` is free text and is never evidence.

`evidence_edge = {from_id, to_id, kind, independence_key: opt<string>}`; primary key `(from_id, kind, to_id)`; no self-edges; `independence_key` is opaque and set by the producer that knows the physical correlation (e.g. `weather-hour:2026-03-14T21`, `overflight:evt_...`), never derived from an id.

## 7. Relations and cardinality

| Relation | Cardinality | Storage | Enforcement |
|---|---|---|---|
| source → observation | 1:N | `observation.source_id` FK | FK, required |
| observation ↔ feature | M:N | `feature_observation(feature_id, observation_id)` | ≥1 row per feature |
| feature/observation → run | N:1 | `run_id` FK | required, run must exist |
| entity ↔ event | M:N | `event_participant(event_id, entity_id)` | FK |
| hypothesis ↔ evidence | M:N | derived from incoming `supports`/`contradicts` edges | `hyp.evidence_ids` is a materialized read-only view: writing it without the edge is rejected |
| hypothesis → verification | 1:N | `verification.hypothesis_id` FK | required; ≥1 for status ∈ supported/rejected |
| constraint ↔ verification | 1:N per residual | `verification_residual(verification_id, constraint_id, value, tolerance, pass)` | FK; constraint version pinned |
| run → produced records | 1:N | `run_id` on `ftr`, `hyp`, `ver` | FK |
| any ↔ any | M:N | `evidence_edge` | §3 matrix |

## 8. Provenance and W3C PROV-O (I2)

Every record type below is exported as a PROV-O graph under the `pw:` prefix; the mapping is normative, and an export/round-trip test asserts it. PROV-O terms are used as published by W3C (claim: the vocabulary is stable; this repo does not pin a version of the recommendation).

| Record | PROV-O class | Field mappings |
|---|---|---|
| `source` | `prov:Entity` | `uri`→`prov:atLocation`; `checksum`→`prov:value`; `retrieved_at`→`prov:generatedAtTime`; `acquisition_method`→`prov:wasGeneratedBy` (a `pw:Acquisition` activity); `license`→`dcterms:license`, `pw:accessLevel`; `version`→`pw:sourceVersion` |
| `observation` | `prov:Entity` | `source_id`→`prov:hadPrimarySource`; `content_hash`→`prov:value`; `captured_at`→`pw:capturedAt`; `event_time`→`pw:eventTime`; `record_time`→`prov:generatedAtTime` |
| `feature` | `prov:Entity` | `observation_ids`→`prov:wasDerivedFrom`; `extractor`→`prov:wasGeneratedBy` (`pw:Extraction`) + `prov:wasAttributedTo`; `run_id`→`prov:wasGeneratedBy`; `created_at`→`prov:generatedAtTime`; `uncertainty`→`pw:uncertainty` |
| `entity`, `event` | `prov:Entity` | `participant_entity_ids`→`prov:used`; `time`→`pw:eventTime`; `region`→`pw:region`; `uncertainty`→`pw:uncertainty` |
| `constraint` | `prov:Entity` | `authority`→`prov:wasAttributedTo` (`pw:Physics`, `pw:Dataset`, `pw:Assumption`); `version`→`prov:value`; `parameters`→`pw:parameters` |
| `hypothesis` | `prov:Entity` | `created_by.run_id`→`prov:wasGeneratedBy`; `created_by.inferencer`→`prov:wasAttributedTo`; `evidence_ids`→`prov:wasInfluencedBy`; `prior`→`pw:prior` |
| `inference_run` | `prov:Activity` | `started_at`/`completed_at`→`prov:startedAtTime`/`prov:endedAtTime`; `inputs.*`→`prov:used`; `output_artifact_hashes`→`prov:generated`; `inferencer_versions`→`prov:qualifiedAssociation`; `parameters`→`pw:parameters`; `environment`→`pw:environment`; `determinism`→`pw:determinism` |
| `verification` | `prov:Entity` + `prov:Activity` | the check is the activity; `residuals`→`pw:residual` (typed, one node per residual); `support_evidence_ids`→`prov:used` with `pw:role = supports`; `conflict_evidence_ids`→`prov:used` with `pw:role = contradicts`; `verdict`→`pw:verdict`; `run_id`→`prov:wasGeneratedBy` |
| `evidence_edge` | none (relation) | `derives_from`→`prov:wasDerivedFrom`; `supports`/`contradicts`→`prov:wasInfluencedBy` + `pw:role`; `refers_to`→`prov:wasInfluencedBy` + `pw:role = refers_to`; `same_event_as`→`pw:sameEventAs`; `independence_key`→`pw:independenceKey` |

The store never derives ontology truth from PROV-O, and PROV-O export is lossy in one direction only: `_record_time` survives as `prov:generatedAtTime`, but a PROV graph re-imported without `pw:` annotations cannot reconstruct layer or identity.

## 9. Typed actions and authority (I9)

Roles are `researcher < reviewer < publisher`. Every action is an `INSERT`-only runtime operation that writes its records and one append-only audit row (`actor`, declared role, `action_kind`, `target_ids`, canonical parameter digest, `run_id` where applicable, timestamp, policy digest, decision, reason code, required/actual authority, optional input snapshot digest). Audit rows are infrastructure, not ontology objects, and carry a store-assigned monotone sequence number rather than a prefixed id. The implemented extension is recorded in [ADR 0026](../decisions/0026-runtime-governance-primitives.md).

| Action | Minimum role | Preconditions | Writes |
|---|---|---|---|
| `ExtractFeatures` | researcher | observations exist and their effective license permits local computation; extractor name+version declared; run budget set | `run`, `feature`(+joins), audit |
| `ProposeHypothesis` | researcher | `claim.location` and `claim.time` present and non-degenerate; `prior ∈ (0,1)` recorded; ≥1 evidence id unless `parameters.prior_only` | `run`, `hyp`, `supports` edges, audit |
| `RunSimulation` | researcher | cited constraints resolve at the pinned version; `residual_function` registered; environment recorded | `run`, prediction `hyp` rows (§12), audit |
| `ChallengeHypothesis` | researcher | target exists; challenger ≠ `created_by.inferencer` unless `parameters.self_challenge = true` | `run`, `contradicts` edge, `hyp.status → under_test`, audit |
| `RequestReview` | researcher | hypothesis has ≥1 verification or an explicit `insufficient` verdict; reviewer identity configured in multi-actor mode | audit, `hyp.status → under_test`; blocks `PublishEvidence` until a review decision exists |
| `PublishEvidence` | publisher | ≥1 verification with `verdict ∈ pass|partial`; bundle license/sensitivity check (I10) passes; publisher ≠ hypothesis creator when more than one identity is configured; bundle digest recorded | audit + content-addressed bundle manifest; never mutates the hypothesis |

Local single-researcher mode grants all three roles to one local identity; the audit row records `role_source: local_bootstrap`, and the self-publish restriction is then structurally unenforceable and is stated as such rather than implied.

## 10. Storage projection (SQLite, M0)

One store is one directory: `store.sqlite` (WAL, single writer process) plus `blobs/sha256/<aa>/<bb>/<digest>` for media bytes. Media never enters SQLite; `content_hash` is the only join key, so stores relocate and verify without rewriting metadata.

Every record table has `id TEXT PRIMARY KEY` with a per-table `CHECK (id GLOB '<prefix>_*')`, JSON `TEXT` columns for value objects (`license`, `uncertainty`, `claim`, `time`, `region`, `inputs`, `parameters`, `environment`, `extractor`) validated by the Rust type before insert and *not* by SQLite, and four infrastructure columns absent from the object vocabulary: `_record_time TEXT` (store clock, monotone, microsecond), `_ontology_version TEXT`, `_digest TEXT` (SHA-256 of the canonical row), and on `inference_run` `_replay_key TEXT` (digest of the identity tuple without `started_at`, `environment`, and outputs).

| Table | Traversed collections | Indexes |
|---|---|---|
| `source`, `observation`, `feature`, `entity`, `event`, `constraint`, `hypothesis`, `inference_run`, `verification` | `feature_observation`, `event_participant`, `hypothesis_evidence`, `verification_residual`, `run_input`, `constraint_applicable_kind` | `_record_time` on all; `observation(source_id)`, `observation(content_hash)`, `feature(run_id)`, `hypothesis(created_by_run)`, `verification(hypothesis_id)`, `inference_run(_replay_key)` |
| `evidence_edge` | — | PK `(from_id, kind, to_id)`; `(to_id, kind)` and `(from_id, kind)` |

Append-only: `BEFORE UPDATE` and `BEFORE DELETE` triggers raise `ABORT` on every record and child table. The single exception is `hypothesis.status`: its trigger permits only transitions in the declared graph (`proposed→under_test→{supported,rejected,insufficient}`, and back to `under_test` from any verdict), requires a non-null `cause_id` naming the `ver` or audit row that caused it, and appends a `status_transition(hypothesis_id, from, to, cause_id, _record_time)` row. The one legal delete is an administrative purge of a whole store, which destroys identifiers rather than rewriting them. `evidence_edge` has a `BEFORE INSERT` trigger implementing the §3 matrix (prefix → height lookup, then the per-kind rule) and a `CHECK (from_id <> to_id)`.

Bitemporality (I3): `as_of(t)` views filter `_record_time <= t`; linkage queries join on identifiers, so a later re-analysis adds rows and never changes what an earlier verification cited. There is no `UPDATE ... SET event_time`; a corrected event time is a new `observation` record with a different identity tuple, and any record that depended on the old one keeps that dependency.

## 11. Worked chain

A recording with no metadata, an acoustic feature, a physical premise, one hypothesis, one verification. Field values are illustrative; only the structure is normative.

```json
{"id":"src_7b2e5c1a90fd4433","uri":"file:///imports/field-2026-03-14/rec-a.wav","title":"field recording, unlabelled",
 "license":{"spdx":"CC-BY-4.0","terms_url":"https://creativecommons.org/licenses/by/4.0/","access_level":"public"},
 "version":"1","retrieved_at":"2026-03-15T08:12:40Z",
 "sensitivity":{"max_output_granularity":"region","person_data":false,"notes":"no faces, no speech"},
 "acquisition_method":"adapter:local-files/wav-copy@0.1","checksum":"9d2f0b1c8e7a6f5d4c3b2a1908172635445566778899aabbccddeeff00112233"}

{"id":"obs_3f1c0a9d2b4e67a1","source_id":"src_7b2e5c1a90fd4433","media_kind":"audio",
 "captured_at":"2026-03-14T21:47:03.000000Z",
 "event_time":{"start":"2026-03-14T21:46:58Z","end":"2026-03-14T21:47:09Z","inner_confidence":0.9},
 "record_time":"2026-03-15T08:12:44.031000Z",
 "content_hash":"c0a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f",
 "location_hint":null,"license_snapshot":{"spdx":"CC-BY-4.0","terms_url":"https://creativecommons.org/licenses/by/4.0/","access_level":"public"},
 "attributes":{"sample_rate_hz":48000,"channels":2,"duration_s":11.2}}

{"id":"ftr_1a2b3c4d5e6f7081","observation_ids":["obs_3f1c0a9d2b4e67a1"],
 "extractor":{"name":"ambient-inference/dsp.doppler@0.1.0","version":"0.1.0"},
 "feature_kind":"acoustic.doppler_crossing","value":{"t_cross_s":4.62,"f0_hz":118.4,"slope_hz_s":-2.31},
 "unit":"1","uncertainty":{"method":"interval","params":{"lo":-0.18,"hi":0.18,"level":0.95},"calibration_ref":"cal/doppler/0.1.0"},
 "run_id":"run_9c8d7e6f5a4b3c2d","created_at":"2026-03-15T08:13:02.190000Z"}

{"id":"con_5d4c3b2a1908f7e6","constraint_kind":"kinematic",
 "expression":"f_obs(t) = f0 * c / (c - v_r(t)); residual = RMS(f_obs - f_model)",
 "parameters":{"c_m_s":343.0,"assume_constant_velocity":true},"applicable_kinds":["acoustic.doppler_crossing"],
 "residual_function":"kinematics.doppler_rms_v1","tolerance":0.01,"authority":"physics","version":"1.0.0"}

{"id":"hyp_6e5d4c3b2a1908f7","claim":{"location":{"kind":"bbox","payload":{"min_lon":-1.4,"min_lat":51.2,"max_lon":-1.1,"max_lat":51.5}},
  "time":{"start":"2026-03-14T21:46:55Z","end":"2026-03-14T21:47:15Z","inner_confidence":0.8},
  "state":{"altitude_m":1100,"heading_deg":248,"ground_speed_m_s":130}},
 "prior":0.2,"evidence_ids":["ftr_1a2b3c4d5e6f7081"],"status":"under_test",
 "created_by":{"inferencer":"ambient-inference/acoustic_doppler@0.1.0","run_id":"run_9c8d7e6f5a4b3c2d"}}

{"id":"run_9c8d7e6f5a4b3c2d","started_at":"2026-03-15T08:12:58Z","completed_at":"2026-03-15T08:13:04Z",
 "ontology_version":"0.1.0","seed":20260314,
 "inputs":{"observation_ids":["obs_3f1c0a9d2b4e67a1"],"source_ids":["src_7b2e5c1a90fd4433"],
  "data_snapshot_ids":[],"hypothesis_ids":[]},
 "inferencer_versions":[{"name":"ambient-inference/dsp.doppler","version":"0.1.0"},
  {"name":"ambient-inference/acoustic_doppler","version":"0.1.0"}],
 "parameters":{"llr_clip":8.0,"prior":0.2},
 "environment":{"os":"linux","arch":"x86_64","runtime":"python/3.12"},
 "output_artifact_hashes":["a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90"],
 "determinism":"deterministic",
 "record_digest":"f0e1d2c3b4a5968778695a4b3c2d1e0ff0e1d2c3b4a5968778695a4b3c2d1e0f"}

{"id":"ver_2b3c4d5e6f708192","hypothesis_id":"hyp_6e5d4c3b2a1908f7","run_id":"run_9c8d7e6f5a4b3c2d",
 "check_kind":"kinematic.doppler_fit",
 "residuals":[{"constraint_id":"con_5d4c3b2a1908f7e6","value":0.0041,"tolerance":0.01,"pass":true}],
 "support_evidence_ids":["ftr_1a2b3c4d5e6f7081"],"conflict_evidence_ids":[],
 "verdict":"pass","confidence":0.62,"notes":"single residual; azimuth ambiguity unresolved, see open question 3"}

{"from_id":"hyp_6e5d4c3b2a1908f7","to_id":"ftr_1a2b3c4d5e6f7081","kind":"derives_from","independence_key":null}
{"from_id":"ftr_1a2b3c4d5e6f7081","to_id":"hyp_6e5d4c3b2a1908f7","kind":"supports","independence_key":"source:src_7b2e5c1a90fd4433"}
{"from_id":"hyp_6e5d4c3b2a1908f7","to_id":"con_5d4c3b2a1908f7e6","kind":"refers_to","independence_key":null}
```

The chain crosses the layers exactly once per record: `obs`/`ftr` are L1 (claims about the artifact), `hyp` is L2 (claim about the world), `ver` is L3 (claim about the hypothesis). The constraint is cited, not merged. The support edge names an independence key, so a second acoustic feature from the same recording cannot add a vote; the `supports` edge points *up* (L1→L2) and the `derives_from` edge points *down* (L2→L1) — the matrix allows exactly that pair and forbids the reverse of the first.

## 12. Prediction hypotheses

`RunSimulation` does not produce observations. Its output is recorded as an L2 `hypothesis` whose `claim.state` carries reserved keys `prediction_of` (the `hyp` id under test) and `predicted_observables` (the values a valid world state would have produced), plus a `derives_from` edge to `prediction_of`. Verification compares `predicted_observables` against L1 features and records residuals. This keeps the core capability of the brief — predict, compare, localize the inconsistency — inside the nine-object model without inventing a tenth object, and it makes a prediction falsifiable on exactly the same terms as a world-state claim.

## 13. Versioning and evolution

The ontology is semver'd (`0.1.0` today) and stored per row in `_ontology_version`; a `meta` row holds `store_uuid`, `ontology_version`, and creation time. MAJOR: removed or renamed field, changed layer, changed invariant, changed identity tuple. MINOR: added optional field, added enum value, added edge kind, added object (with an ADR). PATCH: editorial. A store opens only when the code's MAJOR.MINOR equals the store's; a PATCH mismatch is tolerated. This hard gate is deliberate: it makes silent misinterpretation impossible and makes rolling upgrades an explicit migrate-then-restart operation. Migrations are forward-only, one file per version, each shipping a fixture database and a round-trip test; renames keep the old field readable for one MINOR and are removed in the following MAJOR. Enum values are additive in MINOR, and the gate means no consumer ever meets an unknown value. Adding an object or an invariant requires an ADR; the M0 set is closed until [ADR 0003](../decisions/0003-world-ontology-and-provenance.md) is superseded.

## 14. Out of scope for M0

Recorded here so the boundary is not renegotiated per pull request: DuckDB/Parquet/H3 analytical projection (M-multi-node); RDF export beyond the §8 mapping test; entity merge/dedupe and canonical-entity resolution; probabilistic programming or typed constraint IR (`expression` is text, `residual_function` is a registered symbol); cryptography beyond checksums (no signatures, no merkle log, no transparency witnesses); person-level data and any output purpose that locates a private individual; multi-writer concurrency and CRDT merge (one writer per store); cross-store federation, replication, and distributed ids; streaming/real-time ingestion; the investigation UI (M2); model weight hosting and training; automated license reasoning (the lattice is implemented, legal judgment is not); revision ordering of corrections across stores.

## 15. Open questions

1. **Constraint expression language.** M0 keeps `expression` as text and resolves behaviour through `residual_function`. Whether a typed constraint IR is needed before M2 is unresolved; the risk of freezing a DSL too early is the brief's stated ontology-over-engineering risk.
2. **Region floor numerics — resolved 2026-11-04.** Not an ontology question: the cap is enforced here, while the floors (0.25° open band, 0.05° minimum enforced, H3 resolution ≤ 7) are owned by [`ethics-and-privacy.md`](../policy/ethics-and-privacy.md) §3 and projected into policy tiers by [ADR 0005](../decisions/0005-privacy-and-dual-use.md). Kept only as a pointer; the ontology holds no numeric threshold.
3. **Azimuth/heading ambiguity.** The worked chain shows a passing verdict with unresolved ambiguity; whether ambiguity belongs in `claim.state` as a multimodal value or in `verification.notes` needs a decision before M1 benchmarks.
4. **`feature` identity.** Two extractors can emit identical `(observation, extractor, kind, value, unit)` features; the identity tuple then merges them. Whether an ordinal or channel field is needed is unresolved.
5. **Publishable "verified fact".** M0 has no fact object; a published bundle is the closest thing. Whether publication should create an L3 record with elevated status or stay a bundle manifest is left to M2.
6. **`same_event_as` transitivity.** Co-reference is stored as a symmetric pair, not a closure. Whether query-time union-find is sufficient or a co-reference entity is required is open.
7. **`independence_key` assignment authority.** Producers who know the physical correlation set the key; no component validates that two keys are correctly distinct. A verifier-side audit of key assignment is unbuilt.
8. **Blob retention.** Content-addressed media outside SQLite is simple but unbounded; retention and garbage collection are not specified and must not be improvised at publish time.
