# ADR 0012 — Research-grade minimal fabric v0

Status: Accepted
Date: 2026-11-04
Deciders: Haelio Tang (founder)

## Context

[ADR 0008](0008-two-track-execution.md) split the data layer in two: a research-grade minimal fabric (RMF) that E1 actually needs, and a platform-grade federated fabric that is deferred. [ADR 0007](0007-federated-world-data-infrastructure.md) defines the full contract; the RMF needs a much smaller one. PR-3 must make one experiment reproducible offline: pinned inputs, a license gate, verified bytes, and a record that proves which inputs produced which outputs.

Without a fixed layout, "minimal" grows into a catalog service by accident. This ADR fixes the v0 shape.

## Decision

1. **Layout.** One fabric directory contains:
   - `catalog.json` — append-only array of dataset profiles; a rewrite of an existing entry is refused, an identical append is a no-op, a conflicting one is a typed error.
   - `snapshots/<snapshot_id>/manifest.json` plus `blobs/sha256/<aa>/<bb>/<digest>` — content-addressed bytes. `snapshot_id` is the SHA-256 of the canonical manifest (sorted entries, each `{path, size, sha256}`).
   - `runs/<run_id>.json` — replay records (see §4).
2. **Dataset profile (reduced ADR 0007 contract).** Required: `dataset_id`, `provider_id`, `source_uri`, `license{spdx, terms_url, access_level: public|research|restricted}`, `observation_type: direct|model_estimate|derived|synthetic`, `version`, `retrieved_at`, `content_hash` (snapshot id), `access_policy{allowed_purposes: [internal_research|external_publication|redistribution], authorization_required: bool}`, `missingness` (non-empty text). Also required, nullable only with a stated reason: `spatial_resolution`, `positional_accuracy`, `temporal_resolution`, `uncertainty_model`. `spatial_resolution` and `positional_accuracy` are separate fields; conflating them is a validation error, not a style issue.
3. **License gate.** A gate call takes a purpose and returns `Allow`, `RequireAuthorization(record_id)`, or `Refuse(reason)`. `restricted` never reads without a valid authorization record; `research` never satisfies `external_publication` or `redistribution`; `public` may be used for any listed purpose. The gate is a library function called by every read path in the RMF; a read that bypasses it is a defect. Decisions carry a machine-readable reason for the audit row.
4. **Snapshot verification.** Opening a snapshot re-hashes every file and refuses on any mismatch, missing file, or extra file not in the manifest. Reads are offline: no path may fetch, and a snapshot that is incomplete cannot be partially used. Bytes are returned only after verification passes.
5. **Replay record.** A replay writes `runs/<run_id>.json` with: fabric and snapshot ids, dataset ids, the code identity (`package version` + repository commit if provided), the configuration digest, every input content hash, every output artifact hash, the expected-vs-observed digest comparison, and a determinism verdict (`exact` | `mismatch` | `unknown`). A mismatch is a non-zero exit, never a warning.
6. **Exactness, then tolerance.** Byte/digest equality is required; numeric tolerance for floating-point outputs is deliberately deferred (ADR 0010's evaluation stance) and is recorded as `unknown` rather than assumed zero. Cross-platform float equality is not claimed.

   **Reproducibility levels (2026-11-05).** One "reproduced" claim is not enough; three levels are named, and they are never substituted for one another:

| Level | Definition | Acceptance | Claimed across platforms |
|---|---|---|---|
| **R0 execution** | The same inputs run to completion and produce complete artifacts | Process succeeds, artifacts exist and hash | Useful, but **not** a reproduction claim |
| **R1 numerical equivalence** | Every trial and every key scientific output matches within a frozen protocol (abs+rel tolerance per field; exact for ids, counts, decisions, enums) | Per-trial comparison passes; mismatch fails CI | **Yes — the minimum for cross-platform scientific reproduction** |
| **R2 bitwise identity** | Canonical output bytes are identical | SHA-256 equal | No; a stronger engineering property, environment-bound |

Rules: R1 passing is never reported as R2; R0 success is never reported as scientific reproduction; classification must be `exact` (R1+R2), `numerically_equivalent` (R1 only), `mismatch`, or `unknown`, and a real R1 mismatch fails CI. Tolerances are **measured first** and chosen from the numerical algorithm's expected error, parameter scale and decision threshold — never picked to make the current experiment pass — then frozen at the E2 preregistration. Decision instability (a numeric change inside tolerance flipping an accept/reject or success/fail) is reported as a finding and blocks a "reproduced" claim. The comparator and protocol are PR-4; the protocol lives under `protocols/` and its digest is part of every report.

**Measured result (2026-11-05).** The first R0/R1/R2 comparison is recorded in the [cross-platform report](../experiments/2026-11-05-cross-platform-e0.md). R0 passes; R2 fails; **R1 is not established**, for three structural reasons rather than "the numbers are off": (a) parameter differences in identifiable conditions are ~1e-9, but unidentifiable/null conditions produce unbounded differences that a whole-artifact comparison cannot gate; (b) 1 in 2500 convergence decisions flips near its threshold, changing a reported condition success rate 100→99; (c) least-squares iteration counts and gradient norms (implementation metadata, not science) differ broadly. A frozen protocol therefore needs identifiability-conditioned scope, a decision-margin/indeterminate rule, and completed field classification (PR-4b). The measured bounds (parameters rel 1e-5, ratios absolute-only, rates exact) are proposals, not a frozen protocol, and were not chosen to make the run pass.

**Observed cross-platform limit (2026-11-04).** The E0 `records_sha256` differs between macOS arm64 (`674213d9…`, every reported aggregate reproduced) and the Linux x86_64 CI runner (`3d57f169…`): floating-point formatting/FMA/BLAS differences, not a logic difference. Consequences: `make e0` is the **strict same-environment** claim; `make e0-ci` passes `--allow-digest-mismatch true`, records `determinism: unknown`, and **must never be cited as a reproduction**; a structural numeric comparison with a stated tolerance is the required next RMF unit before E2. A CI job that forced exact equality across platforms would either be permanently red or hide the difference by pinning a second golden value — both are worse than stating the limit.
7. **Integration with the evidence store.** A successful replay appends, through `phaino-store`, an `Observation` for the pinned synthetic fixture (content hash + license snapshot) and an `InferenceRun` carrying snapshot ids, versions, seeds, parameters, environment, output digests, and determinism. Hypothesis and verification records arrive with E1; v0 does not fake them.
8. **Non-goals for v0.** No catalog service, no provider adapters, no query planner, no incremental cache, no redistribution machinery, no multi-writer, no remote access. One fabric directory, one writer, offline by default.

## Recorded interpretations (v0 implementation)

The first implementation (`crates/phaino-fabric`, `crates/phaino-cli`) resolved several points the decision above leaves open. Recorded so later code does not rediscover them differently:

1. **Layout adds `store/`.** §1 lists catalog, snapshots, runs; §7 requires appending through `phaino-store`, so a fabric directory also contains `store/` (the store crate's own one-directory layout).
2. **`nullability_reasons`.** §2 requires nullable fields to carry a stated reason; the profile carries `nullability_reasons: {<field>: <reason>}`. A null field without an entry is invalid, and a reason for a non-null field is also invalid.
3. **`fabric_id`.** §5 requires one but does not define it; v0 defines `fabric_<16hex>` = SHA-256 of the canonical fabric root path. It is **local identity, not a content claim**, and must not be compared across machines.
4. **Extra-file scope.** §4's "extra file" check applies within `snapshots/<id>/`. `blobs/` is a shared content-addressed store, so a blob referenced by another snapshot is not an extra file for this one.
5. **A `Source` record is also appended.** §7 names Observation and InferenceRun; an Observation's `source_id` must resolve, so registration appends an idempotent `Source` first.
6. **Determinism mapping.** `ReplayRecord` uses `exact | mismatch | unknown`; `InferenceRun` uses the ontology's `deterministic | nondeterministic | unknown`. `exact` maps to `deterministic`; `mismatch` maps to `unknown` (never claims nondeterminism), and the replay record keeps the exact comparison.
7. **Outputs are hashed, not retained.** v0 has no artifacts directory: the produced JSON's hash enters the replay and run records, and the temporary directory is deleted.
8. **`repository_commit` is optional.** Code identity is the package version; a commit may be supplied by the caller and is null otherwise.
9. **Registration is two-step.** The profile's `content_hash` must equal the snapshot id the source directory produces; a first registration with a guessed hash fails with `ContentHashMismatch` and prints the computed id. Known v0 usability defect.
10. **`fabric verify`** covers catalog plus snapshots, not run/store consistency.
11. **Single writer.** Catalog read-modify-write has no file lock; one writer per fabric directory is assumed (§8).

## Consequences

### Positive

- E1's real data can enter through an already-testable path instead of a future platform.
- The license gate exists before the first real dataset, which is when it must.
- Replay is provable: snapshot verification plus digest comparison plus a stored run record.

### Negative / costs

- The reduced profile will be extended when the PFF lands; some fields will be re-homed.
- `catalog.json` append-only is a weak catalog (no query, no dedupe beyond dataset_id); replacing it with a store-backed table is expected work.
- Exact-digest replay will fail across platforms and is reported as `mismatch`, which may be noisy until the environment is pinned (M4).

## Alternatives considered

- **Skip the fabric; E1 loads files directly.** Rejected: licence and snapshot discipline are the E1 prerequisite from ADR 0008, and retrofitting them after real data is far more expensive.
- **Use the platform catalog design now.** Rejected: a service before one experiment is the trap ADR 0008 named.
- **Manifest with a Merkle tree.** Rejected for v0 as unnecessary; a sorted-entry digest is enough for offline verification, and the upgrade path is additive.

## References

- [ADR 0008](0008-two-track-execution.md), [ADR 0007](0007-federated-world-data-infrastructure.md)
- [Data governance](../policy/data-governance.md) §7 (licence enforcement point)
- [ROADMAP](../roadmap/ROADMAP.md) §4.1 (RMF acceptance)
- [E0 report](../experiments/2026-11-04-e0-synthetic-doppler.md) — the experiment v0 must replay
