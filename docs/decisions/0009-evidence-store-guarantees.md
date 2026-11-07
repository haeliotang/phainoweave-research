# ADR 0009 — Evidence store guarantees: append-only, detection, replay

Status: Accepted
Date: 2026-11-04
Deciders: Haelio Tang (founder)

**Amendment (2026-11-07):** the audit table is no longer deferred. `audit_event` is implemented with append-only triggers and append-log chaining; see [ADR 0026](0026-runtime-governance-primitives.md) for the runtime governance contract and its remaining limits.

## Context

The M0 plan said "SQLite append-only store with triggers". That conflates three different guarantees. SQLite triggers can refuse `UPDATE` and `DELETE` on the normal write path, but a principal who can modify the schema can `DROP TRIGGER`, and a principal who can write the file can edit pages directly. "Append-only" as an implementation detail is not "the history cannot be silently rewritten". Separately, `as_of(t)` was ambiguous: in a bitemporal model it must name whether it means *what the system knew at t* or *what happened at or before t*, and the two answers differ for records learned late.

## Decision

Three guarantees are defined and named separately. **M0 claims G1 and G3; G2 is implemented as detection only and must not be described as tamper-proof.**

| ID | Guarantee | What it means | How it is met | Claimed at M0 |
|---|---|---|---|---|
| **G1** | Logical append-only | No normal application write path can modify or delete an existing record. | `BEFORE UPDATE`/`BEFORE DELETE` triggers abort on every record and child table; the sole exception is `hypothesis.status`, which follows a declared transition graph and logs each transition with a non-null `cause_id`. | **Yes** |
| **G2** | Tamper detection | Substitution or deletion of an existing record is detectable by a verifier who holds an external checkpoint. | Hash-chained `append_log` (`seq`, `entity_kind`, `record_id`, `payload_digest`, `prev_hash`, `chain_hash`); `verify_chain()` reports the first broken link. Without an external checkpoint an actor who rewrites the whole database also rewrites the chain. | **Detection only; not claimed as prevention** |
| **G3** | Replayable state | Given the same event set and a cutoff, the projection is identical across runs and machines. | Deterministic projection with PCJ-0 hashing ([ADR 0006](0006-canonical-json-and-digests.md)); `projection_digest` over the ordered result. | **Yes** |

**As-of semantics are two functions, never one flag.**

- `as_of_record_time(t)` — the state the system knew at `t`: filter `_record_time <= t` (store clock, monotone microseconds). This is the bitemporal knowledge axis.
- `as_of_event_time(t)` — records whose claimed event or capture time is at or before `t`: filter `event_time`/`captured_at`. Claims may be absent or wrong; this axis never implies the system knew the record at `t`.

Mixing them in one API, or defaulting to either, is a defect. A query that needs both states its combination explicitly.

**Status transitions.** `hypothesis.status` is the only mutable column in M0. Legal graph: `proposed → under_test → {supported, rejected, insufficient}`, and back to `under_test` from any verdict. Each transition requires `cause_id` naming the `ver_` record or audit row that caused it, and appends `status_transition(hypothesis_id, from, to, cause_id, record_time)`.

**Non-goals at M0.** No external checkpoint or transparency log, no Merkle aggregation, no WORM storage, no encryption at rest, no multi-writer concurrency. Those raise G2's claim level only after a checkpoint and an independent verifier exist.

## Recorded interpretations (M0 implementation)

The first implementation (`crates/phaino-store`, PR-1) had to resolve places where the spec is silent. These are recorded so later code does not "rediscover" them differently:

1. **`_digest` scope.** The digest excludes the store clock — `Observation::record_time` is the store `_record_time` (spec §6), so including it would make two stores with identical bytes disagree — and excludes the mutable `Hypothesis::status`, whose history is the `status_transition` log. Everything else in the row is covered.
2. **Hypotheses are inserted only as `proposed`.** Lifecycle changes happen through the transition graph with a `cause_id`; a worked example showing an `under_test` row is expressed the same way.
3. **The audit table is deferred.** `cause_id` accepts a stored `ver_` id or an opaque `audit:<sequence>` reference; the audit table arrives with the actions runtime.
4. **`as_of_*` are typed query functions, not SQL views.** Views return with the CLI (A2); the guarantee is the projection and its digest, not a schema object.
5. **Permitted infrastructure columns** beyond the object vocabulary: `hypothesis.cause_id`, `_status_record_time`, `created_by_run`; `evidence_edge._record_time`, `_digest`.
6. **Chain scope.** G2 covers the nine record tables, `evidence_edge`, and `status_transition`. Child collection tables are G1-protected but not individually chained.
7. **Deferred, not silently claimed:** the `duplicate_claim` index, `calibration_ref` resolution, identity re-derivation from the identity tuple (only grammar/prefix is validated), and multi-writer enforcement (the store assumes one writer per directory; SQLite does not enforce it).

## Consequences

### Positive

- The project stops overstating "append-only": a reader can tell exactly which guarantees hold and which are detection aids.
- Splitting the two as-of axes forces the bitemporal model into the API instead of a documentation footnote.
- G3 is testable today: same inserts, same cutoff, identical projection digest.

### Negative / costs

- G2 without an external checkpoint has limited value against a database-level attacker; it mainly catches accidental or partial tampering.
- Two as-of functions mean every caller must choose, and choosing wrongly produces plausible but wrong answers.
- The status-transition exception adds trigger complexity and a second table that must be audited.

## Alternatives considered

- **Claim tamper-evidence from triggers alone.** Rejected as false: schema and file access defeat it.
- **Merkle tree + external checkpoint now.** Rejected as premature for M0; it is the natural upgrade when a research node exists.
- **Full event sourcing with no mutable columns at all.** Rejected for M0: the status field is the one place a hypothesis lifecycle is genuinely linear, and modelling it as derived state buys complexity before any experiment needs it.
- **Single `as_of(t)` accepting both.** Rejected: ambiguous semantics are how bitemporal systems produce wrong history.

## References

- [World ontology](../specs/world-ontology.md) §9, §10 — schema, triggers, `_record_time`, `_replay_key`
- [ADR 0006](0006-canonical-json-and-digests.md) — digest canonicalization
- [ROADMAP](../roadmap/ROADMAP.md) — track A1 and its exit criteria
