# ADR 0004 — Rust core / Python inference boundary

Status: Accepted
Date: 2026-11-04
Deciders: Haelio Tang (founder)

## Context

The [founding brief](../product/founding-brief.md) §9 splits the stack: Rust owns the core runtime (ontology contracts, evidence store, scheduling, permission checks, event log, plugin host, reproducible runs), and Python owns scientific inference (DSP, computer vision, Bayesian inference, physical solvers, calibration, ML experiments). The split is not aesthetic. The two halves fail differently.

The institutional half fails by drift: a field is renamed, a provenance reference is dropped, a hypothesis is promoted to fact by an update, correlated evidence is counted twice, a replay record omits a parameter. Those failures are cheap to prevent with static types and runtime checks, and expensive to discover after a benchmark or a publication. The scientific half fails by iteration speed: a researcher needs numpy, scipy, torch, librosa, and a notebook loop, and will not rewrite a Doppler estimator in a language with a borrow checker to satisfy a storage layer. Freezing the science in Rust before M1 would make the first vertical slow to build and slow to replace.

The [world ontology](../specs/world-ontology.md) is the contract that must not move silently; the [inferencer contract](../specs/inferencer-contract.md) is the interface that must move with the science. They are split across the boundary accordingly.

## Decision

1. **The ontology, evidence graph, permission checks, and replay records live in Rust.** `crates/phaino-core` is the only layer allowed to define the nine objects, identity tuples, evidence edges, provenance requirements, typed actions, and run digests. Invariants I1–I10 are enforced there by types and constructors, not by reviewer discipline. If a value cannot be represented without violating an invariant, it is not representable in the core crate.

2. **Scientific inference lives in Python.** An inferencer is a bounded, pure function: it receives a typed request, returns candidate world states with scores, residuals, evidence references, referenced data versions, errors, and explicit abstention. It never writes to the store, never promotes a hypothesis, and never renders a verdict; those remain core responsibilities. `python/phaino_sdk` is the M0 Python shape of that contract, and the normative document is [`inferencer-contract.md`](../specs/inferencer-contract.md).

3. **Only a versioned JSON document, content hashes, and ids cross the boundary.** The request and response are JSON documents whose field names come from the two specs; no Python object, SQLite handle, or Rust lifetime crosses. Every input is named by an id or snapshot version, and every output that matters is content-addressed. Timestamps are RFC 3339 strings; identifiers are prefixed newtypes in Rust and validated strings in Python. The ontology version is pinned in the run record, and a store opens only for a matching MAJOR.MINOR version. Identity tuples and digests are canonicalized with PCJ-0; the Rust core and the Python SDK implement it independently and are gated by the same RFC 8785 vectors (ADR 0006).

4. **The core never depends on a Python process to decide truth.** Verification is either deterministic code in the core/verifier library or a separately recorded check; a Python plugin's self-reported confidence is evidence input, never a verdict. This is the mechanical form of the brief's "no LLM output is the final step of a verification".

5. **M0 ships the boundary as types plus contract tests, not as an RPC service.** In-process Rust calls and a subprocess adapter are enough for one researcher on one machine. Transport, sandboxing, and service boundaries are deferred until the interface has survived the first vertical; see §12 of the inferencer contract.

## What crosses, concretely

- Request: contract version, run id, ontology version, inferencer identity, hypothesis query, observation/feature/constraint/snapshot references, evidence scope, parameters, seed, budget, scratch directory.
- Response: status, completeness, candidates with claims/scores/residuals/evidence refs, referenced data versions, determinism declaration, diagnostics, and a typed error.
- Stored side: content-addressed media, canonical record JSON, SHA-256 record digests, ids derived from identity tuples, and the run's pinned environment and inferencer versions.
- Never crosses: mutable store access, network access, a verifier verdict, or a node-local path outside the declared media and scratch paths.

## Consequences

### Positive

- The invariants are enforced where they are cheapest to enforce: types, constructors, and append-only graph operations.
- The scientific layer can use the Python ecosystem and iterate without recompiling the core.
- Replay is attributable: a record digest pins inputs, versions, parameters, and environment, so a different answer is localisable.
- A plugin in either language is replaceable without changing the ontology.

### Negative / costs

- Two toolchains and two CI jobs; contributors need Rust for core work and Python for inferencer work.
- Schema duplication: the same field vocabulary is mirrored in Rust and Python (and later in SQLite). Drift is a real risk; mitigation is contract tests on both sides plus a versioned contract, not a hope.
- Serialization boundaries lose type information unless the contracts stay explicit; unknown fields are refused rather than silently tolerated.
- A subprocess boundary adds process lifecycle, budget enforcement, and environment capture that an all-in-one process would not need.

## Alternatives considered

- **All-Rust with `candle`.** One toolchain and no serialization seam, but it forces every researcher to write Rust and pulls GPU/ML dependencies into the core runtime. Rejected for M0; the boundary allows an inferencer to be rewritten in Rust later without changing the ontology.
- **All-Python.** Fastest to a demo and the natural home of the science, but a Python-only core makes the type-level invariants optional, weakens replay and permission enforcement, and ties the runtime to the interpreter. Rejected.
- **gRPC service split now.** The right end state for distributed nodes, but it adds deployment, version negotiation, and failure semantics before the contract has settled. Deferred; the JSON document is deliberately shaped so a transport can wrap it later.
- **Shared schema generated from one IDL.** Attractive, but M0 has no IDL and one more generator is one more failure mode. Revisit when the ontology reaches a second major version.

## References

- [Founding brief](../product/founding-brief.md) §6, §8, §9
- [World ontology](../specs/world-ontology.md) §2–§9
- [Inferencer contract](../specs/inferencer-contract.md) §1, §3–§4, §10–§11
- [ADR 0002](0002-verification-first-inference.md), [ADR 0003](0003-world-ontology-and-provenance.md), [ADR 0006](0006-canonical-json-and-digests.md)
- [ROADMAP](../roadmap/ROADMAP.md) M0 exit criteria
