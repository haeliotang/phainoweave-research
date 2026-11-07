# ADR 0026 — Runtime governance primitives for real-data intake

Status: Accepted (normative decision only)
Date: 2026-11-07
Deciders: Haelio Tang (maintainer)
Maintainer approval: 2026-11-07 — explicit session direction approved the normative decision. This approval does not assert implementation or assurance.

## Status semantics

This ADR deliberately separates three layers. `Accepted` applies only to the first.

| Layer | Meaning | Current status |
|---|---|---|
| Normative Decision | The principles the project chooses to follow | **Accepted** by the maintainer on 2026-11-07 |
| Implementation | Whether the principles are wired into the actual execution path | **Partial** — mechanisms exist (policy digest, refusal audit, lattice, contract, E1 gate); local HMAC actor credentials, external policy loading/boundary checks and calibration-date syntax are now implemented. Missing: institutional identity, signed/approved policy provenance, end-to-end precision enforcement, metadata issuer/validity authentication, lattice→store path |
| Assurance | Whether the implementation has been shown to resist the relevant threats | **Not established** — no independent red-team, signed identity, signed audit root, certificate validation or OS-level host isolation |

A future change must not use this ADR's `Accepted` status to claim Implementation or Assurance completion. Those claims require their own evidence and, for security assurance, independent review.

## Context

E1 will introduce controlled recordings, site authorization, consent, calibration evidence and external reference data. The M0 code demonstrated policy and authority logic on synthetic E0 data, then added several runtime mechanisms during the E1-0 preparation pass:

- a typed `PolicyArtifact` digest;
- refusal auditing in the store;
- a license/sensitivity lattice and a derived-publication decision;
- host-side contract/budget primitives;
- a raw-bundle gate for E1 captures.

These mechanisms are implemented and tested, but they arrived after ADR 0009 said the audit table was deferred, and they are not yet described by one normative decision. This ADR records what the code actually enforces and what remains declarative. It deliberately does not claim that any of these mechanisms makes an E1 bundle authentic, a policy approved, or an actor authenticated.

## Decision

### 1. Policy artifact digest

A `PolicyArtifact` carries a policy id, version, allowed capability tiers, a precision ceiling, a publish-review flag and a refusal-audit flag. Its canonical PCJ-0 SHA-256 is recorded in:

- every authorization audit record;
- the E0 replay record;
- the store `inference_run.parameters`.

The current default is the compile-time `m0_default()`. The core now also supports loading an externally supplied policy JSON (`PolicyArtifact::from_json_str/from_path`), validating its boundary (`validate`) and enforcing a capability/precision boundary (`enforce_output`); the CLI exposes `policy-check` and `audit-check --policy`. The digest authenticates the declared fields; it does **not** prove that a governance body approved those fields, and the policy file itself is caller-supplied and unsigned.

### 2. Refusal auditing

`authorize_attempt*` returns an `AuditRecord` for allowed and denied attempts. `phaino-fabric::record_authorization` appends the record to the store's append-only `audit_event` table. The store assigns the durable monotone sequence; the record carries decision, reason code, required/actual authority, policy digest and an optional input snapshot digest.

The audited path is opt-in: the public raw `authorize()` still returns `Unauthorized` without writing a store row. New production commands use `record_authorization`; the raw path is legacy until it is deprecated or made private.

A local-first signed path now exists: `LocalActor` credentials can HMAC-SHA256-sign an audit record (`record_authorization_with_key`, `audit-check --actor-file`), and `audit-verify --actor-file` verifies the signatures plus the append chain. This is symmetric local possession, not institutional identity and not non-repudiation. Audit rows written without a credential remain unsigned and tamper-evident only within the append log and payload chain.

### 3. License/sensitivity lattice and publication review

`phaino-fabric::lattice` computes join/meet over access level, output granularity, explicit obligations and consent scopes. Obligations are declared, not inferred from SPDX identifiers; legal mapping is a review task. `DerivedClass::publication_review` and `LicenseGate::gate_derived` refuse a derived record when access, person data, output granularity, consent or no-redistribution blocks release, and require review when attribution/share-alike applies.

The lattice is not yet wired into `Profile` ingestion or the store publish path; it is a library contract plus a decision function, not an end-to-end publication gate.

### 4. Host contract

`phaino-fabric::contract` defines MINOR version negotiation, a non-zero run budget and a sandbox-root path resolver. The E0 CLI enforces a wall-clock deadline, Unix CPU limit, Linux address-space limit, a 1 GiB file-size limit, bounded stdout/stderr and an output-entry ceiling; the child runs with a temporary cwd and HOME/TMPDIR/cache confinement.

An OS-level filesystem boundary is provided by the explicit `scripts/sandboxed_e0.sh` container runner (read-only root/repository, only the output directory writable, no network, dropped capabilities). It is not the default CLI path, and the macOS host's `sandbox-exec` is unavailable in this environment. The host process is therefore resource- and environment-bounded, not OS-filesystem-isolated.

### 5. E1 raw-bundle gate

The E1 bundle gate requires the schema marker, audio digests, independent frequency/time/motion references, calibration certificate fields, site authorization, consent hash, environment metadata, a reference SNR of at least 10 dB, and a non-symlink regular-file path inside the bundle. `Fabric::register_e1` and the CLI `register-e1` run the gate before writing snapshot bytes; `Fabric::register` auto-detects a conventional or schema-marked manifest.

The gate validates declarations, file hashes and path boundaries. It does not validate certificate authenticity, consent coverage, calibration expiry, sample-rate/duration consistency or human identity. A passing bundle is not an E1 result and does not authorize collection.

The following three statements are binding and must stay consistent across the API, audit records and cockpit:

1. `--actor` / `--authority` are caller-provided identity declarations, not verified identities.
2. A policy digest proves integrity of the declared policy content; it does not prove lawful origin or that the execution path obeyed the policy.
3. A passing E1 metadata gate does not mean the site authorization, consent record or calibration certificate has been authenticated.

## Consequences

### Positive

- Policy, refusal, lattice and host-boundary behavior become explicit and testable instead of incidental code.
- The audit table is no longer an undocumented deviation from ADR 0009.
- The E1 intake gate has a named contract and a documented authenticity limit.

### Negative / costs

- The policy file is caller-supplied and unsigned; the default remains a code constant. The digest is not governance approval.
- The audited path is not universal; a raw `authorize()` caller can still refuse without a row. Signed rows exist only when `--actor-file` is used.
- The precision/capability boundary is an API/CLI check, not yet enforced on every data-access, inference and output path.
- The lattice is not wired into the store/profile path.
- The OS-level boundary is an explicit container harness, not a default host sandbox.
- The E1 gate checks declarations and digests, not truth.

## Alternatives considered

- **Treat the existing code as implementation-only and leave ADRs silent.** Rejected: external review cannot distinguish a governed mechanism from an accidental code path.
- **Make `authorize()` private immediately.** Deferred: it would break existing tests and callers before the audited path is adopted everywhere; the migration is recorded as required work.
- **Declare the container harness sufficient host sandboxing.** Rejected: it does not sandbox the macOS host and is not the default CLI execution path.

## References

- [ADR 0009](0009-evidence-store-guarantees.md) — store guarantees; audit-table deferral amended here
- [ADR 0011](0011-privacy-forensics-and-publication-rulings.md) — publication boundary
- [ADR 0012](0012-research-grade-minimal-fabric.md) — fabric/snapshot contract
- [E1-0 raw bundle](../experiments/E1-0-raw-bundle-schema.md)
- [E1-0 filesystem sandbox](../experiments/E1-0-filesystem-sandbox.md)
- [Project review](../roadmap/2026-11-07-project-review.md)
