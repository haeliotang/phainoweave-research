# Project review — omissions and unknown unknowns (2026-11-07)

**Status:** independent code/documentation review of the current working tree · **Scope:** entire repository · **Not a scientific result**

This review found no evidence of a fabricated measurement or a missing real-world claim. It did find several places where the code has moved beyond its specification, where a clean CI would not exercise the same population as the local run, and where real field data would expose assumptions that the synthetic fixtures do not.

During the review, four concrete defects were fixed and re-tested:

1. E1 bundle file hashing loaded whole files into memory (Rust and Python); now streamed.
2. Symlinked reference files could be read by the E1 gate; symlinks are now refused (Rust and Python).
3. `audit-list` / `audit-verify` created a store when the path was missing; they now refuse and create nothing.
4. `Store::verify_chain` rejected its own `audit_event` entries and did not count the audit table; this is fixed, and `audit-verify` now checks both the append-log chain and the audit payload chain.

## P0 — do not call the current tree release-ready

| Finding | Evidence | Why it matters |
|---|---|---|
| **53 working-tree changes are uncommitted** | `git log -1` = `7d3e5f5`; `git status --short` shows 35 modified + 18 untracked paths; latest diff is ~1.4k insertions | The code reviewed and tested here is not in a commit and has never run in CI. A clean checkout cannot reproduce it. |
| **CI is not currently executable** | GitHub Actions runs after `183087e` fail before starting; annotation says account payments/spending limit | The "local green" result is not a substitute for CI. Do not claim current-tree CI verification. |
| **Tauri host is not in CI** | `apps/desktop/src-tauri` is a separate Cargo workspace; `.github/workflows/ci.yml` has only a browser `pnpm build` job | The Rust host, its read-only archive/audit commands and its dependency set can break without CI noticing. |
| **Tauri CSP is disabled** | `apps/desktop/src-tauri/tauri.conf.json` → `"csp": null`; no packaging/signing (`bundle.active: false`) | A local-only read-only shell has a narrow threat model, but CSP is the main defence if the webview is ever compromised. Set a restrictive CSP and test it before shipping. |
| **E1 gate is a declaration gate, not an authenticity gate** | `e1_bundle.rs` / `phaino_e1raw` check IDs, hashes and numeric fields; `valid_until` is not date-parsed, certificates are not signed, consent text is not fetched | A bundle can carry a fabricated certificate ID or a consent hash that names no real document. The gate prevents malformed metadata, not dishonest metadata. |
| **Audit actors are unauthenticated** | `phaino audit-check --actor ... --authority ...` accepts caller-supplied identity; `Actor` has no authentication step | A refusal audit row proves what the local caller declared, not who acted. This is acceptable for the current local demo, but must not be presented as non-repudiation. |

## P1 — correctness, reproducibility and governance gaps

### Verification population and toolchain

- **CI Python is 3.12; local is 3.14.0; E0 CI jobs use 3.14.9.** `python/tests/test_fit_hardened.py:130`, `test_diagnose.py:124` skip unless macOS arm64 / Python 3.14.0 / NumPy 2.4.4; `test_claim_certificate.py:376` skips unless `/tmp/c1/claims-protocol.json` exists. CI can be green with a smaller test population.
- **Rust CI uses `dtolnay/rust-toolchain@stable`**, while the workspace declares `rust-version = "1.94"` and the container pins 1.94.1. Stable is not a reproducibility pin.
- **CI enforces R1-N only.** `.github/workflows/ci.yml` `e0-compare` passes `--require R1-N` and prints R1-D with the gate intentionally off. The local evidence is: arm64 pair R1-N+R1-D pass, amd64 pair R1-D fail (`null_noise_only.converged_rate` 0.09→0.08), R2 fails everywhere. The declared target scope must be explicit.
- **Container harness output does not show Rust test lines.** The latest `container_repro.sh` log shows `cargo fetch`, Python tests and links, then E0; the Rust unit/integration output is absent. The harness should be checked before claiming a full `make test` ran in-container.

### Spec/ADR drift

- `crates/phaino-store/src/lib.rs` already carried the old claim that “the §9 audit table is not implemented”; the code now has `audit_event`. ADR 0009 §3 still says the audit table is deferred. This needs an ADR amendment, not a silent code/doc divergence.
- `AuditRecord` now has `decision`, `reason_code`, `required_authority`, `actual_authority` and `input_snapshot_digest` beyond the §9 field list in `docs/specs/world-ontology.md`.
- `PolicyArtifact`, `lattice`/`DerivedClass`, `contract`, `Fabric::register_e1` and the E1 raw-bundle schema are code-level contracts without a corresponding ADR/spec amendment. They are reasonable, but “code exists” is not the same as “normatively accepted”.
- `PolicyArtifact` is still a **compile-time M0 default**. Its digest authenticates declared fields, but nothing loads an approved policy file, and `max_output_precision_m` / `allowed_capability_tiers` are not enforced by a precision/capability gate. The digest must not be read as proof that a governance body approved the policy.
- `authorize()` remains a public raw API that can return `Unauthorized` without writing a store row. The “refusal must leave a trace” property holds only for callers that use `record_authorization` / `authorize_attempt*` and persist the result. Make the audited path the default or deprecate the raw path.
- `Fabric::register` auto-gates a directory only when it finds `bundle.json` or a top-level JSON with an `e1-0-bundle-` schema marker. A malformed/non-marker manifest can still bypass the heuristic; `register_e1` is the explicit safe path.

### E1 data scale and path handling

- **Fixed during review:** `e1_bundle` and `phaino_e1raw` hashed entire files; both now stream. `Snapshot::create_from_dir` and `verify_entry` also stream blobs now.
- **Remaining:** `Snapshot::read` (and the `phaino fabric read` path) returns the whole file as `Vec<u8>`. A multi-GB E1 audio read will allocate it all. Add a streaming read/blob-reader API if large raw audio is ever served through this path.
- **Remaining:** `e1_bundle`/`phaino_e1raw` check sample rate, channels and duration but do not cross-check them against the reference tracks or acoustic geometry. A syntactically valid bundle can be physically inconsistent.
- **Fixed during review:** symlinked reference files are refused; the snapshot creator already rejected symlinks.
- **Remaining:** a hardlink inside the bundle can still name external content; content hashes pass, and path checks cannot distinguish a hardlink. This is a local-filesystem trust issue.

### Desktop shell and UI

- `apps/desktop/src/data.ts` duplicates claim/run/policy values from reports. `archive-snapshot.json` is generated and checked, but the claims/governance static data has no generator or drift check. A changed report can leave the cockpit showing old numbers while still “building”.
- Governance view says `rowsInSealedArchive: 0` statically; it does not derive that from the archive. It is true today because the sealed archive has no audit rows, but it will age silently.
- There are no UI unit, component or end-to-end tests; CI only type-checks and builds. Accessibility and keyboard behaviour are unverified.
- `load_audit_events` silently skips payloads that fail JSON parsing; a corrupted audit row would be hidden from the cockpit instead of failing closed.
- `load_archive`/`load_audit_events` read local paths from environment variables; acceptable for a local read-only shell, but there is no file-picker/allowlist UX and no signing of the archive.

### Packaging and dependencies

- `python/pyproject.toml` now includes `phaino_e1raw`, but the distribution still packages only `phaino_sdk`, `phaino_acoustics` and `phaino_e1raw`. `phaino_verify`, `phaino_claims`, `phaino_bench`, `phaino_c2_*`, `phaino_c3` and `phaino_claim_certificate` are PYTHONPATH-only in CI, not installable package contents. Also, `dev` extras contain only pytest/numpy, while tests require SciPy and SymPy; CI installs them ad hoc.
- No Rust dependency vulnerability scan is configured (`cargo-audit` is not installed here); `pnpm audit --prod` currently reports no known vulnerabilities, but it is not in CI.
- Container base images (`rust:1.94-slim`, `python:3.14-slim`) use mutable tags; pip packages are version-pinned but not hash-pinned. `scripts/container_repro.sh` depends on Docker and `rsync` and was not tested in CI.

### Documentation/index

- `docs/README.md` was unreachable from the root README; a root Documentation-index link is now added. The index itself still ends around C1 and does not list the new E1-0 readiness/audit/container documents; the experiments index is the effective newer index.
- Some counts were stale and are now corrected (109 Rust / 439 Python / 621 links). The E1 readiness report still should not quote a hard-coded working-tree change count; counts of uncommitted files change during work.
- `M0-STATUS` contains historical “64 tests” context from PR-1; it is labeled historical but easy to misread as current.

## P2 — smaller issues

- `audit-list`/`audit-verify` now refuse a missing store, but the CLI reports it through `CliError::Usage`, which prints the full help text; a typed I/O/“no store” error would be cleaner.
- `Store::append_audit` returns `InvalidOntologyVersion` for an audit-sequence overflow, which is a misleading error type.
- `input_snapshot_digest` is validated only by the CLI; core accepts arbitrary strings from `snapshot_digest` parameters.
- `audit-verify` verifies the store chain and audit rows, but there is no signed audit root; a local database owner can forge both payload and chain hashes. The chain is tamper-evident against accidental edits, not against a malicious owner.
- `e1-fault`/`e1-bundle` invoke Python with no wall-clock/output budget of their own; a hostile or huge bundle can make the validator slow (hashing is now streaming, but no deadline is enforced).
- `Fabric::register` performs profile validation before the E1 auto-gate; that is safe, but a caller with an invalid profile gets no E1-specific diagnostics.
- The `e1_bundle` Rust and Python validators duplicate field rules and fixtures; a shared cross-language fixture would catch drift.
- `Snapshot::read` returning `Vec<u8>` is documented as a read API but is not bounded; future large-media callers need a streaming contract.

## Unknown unknowns to watch

1. **Scale was the hidden assumption.** Synthetic fixtures are small; multi-GB raw audio exposed whole-file reads in the gate, snapshot creation, snapshot verification, Tauri archive hashing and Python validation. Streaming fixes are in progress/completed, but `Snapshot::read` remains.
2. **Integrity is not authenticity.** SHA-256 chains, content-addressed blobs and audit digests prove internal consistency; they do not prove who created a certificate, consent, actor identity or archive. A valid-looking E1 bundle can still be a false claim.
3. **A green suite can hide skips.** Platform-gated trial57 tests and the `/tmp/c1` fixture test are invisible in a normal CI count.
4. **Spec/code drift is now the largest governance risk.** The audit table, lattice, policy artifact, host budget and E1 bundle gate are implemented faster than the ADRs/specs describe them.
5. **The target reproduction scope is ambiguous.** arm64 passes R1-D; amd64 fails one null-trial rate; R2 fails everywhere. “R1-D passed” is not a whole-project statement.
6. **The cockpit can be internally consistent but stale.** Static claims/run/policy values and a generated archive snapshot have different refresh mechanisms; only the archive snapshot has a drift check.
7. **The local shell has no OS filesystem sandbox.** Environment confinement and resource limits are not a security boundary for an untrusted Python plugin.
8. **The field campaign’s truly unknown variables are physical, not code.** Instrument calibration, site authorization, consent, clock truth and signal quality remain unmeasured; no amount of code rehearsal substitutes for the first real bench.

## Recommended next actions (priority order)

1. **Commit the reviewed work in coherent commits** (after the maintainer’s explicit approval), then restore GitHub Billing and run the full CI, including a Tauri `cargo check` job and a Python 3.14 job.
2. **Freeze the target reproducibility scope**: either fix/declare x86_64 or explicitly exclude it; keep R2 and R1-D labels separate.
3. **Amend ADR 0009 / world-ontology §9** for `audit_event` and the extended audit fields; add ADR/spec notes for policy artifact, lattice and E1 bundle gate.
4. **Make audited authorization the default path** and add a test that raw `authorize()` cannot be used as an unaudited refusal path in production code.
5. **Add Tauri CI + CSP + a packaged build test**; add UI unit/e2e coverage for Governance and archive/audit states.
6. **Stream `Snapshot::read` or add a bounded reader**, and add a multi-GB fixture test to the E1 gate/snapshot path.
7. **Add a dependency/toolchain lock policy**: pin Rust in CI, pin CI Python, hash-pin container Python dependencies, run `cargo-audit`/`pnpm audit`.
8. **Add a static-data drift check** for the cockpit’s claims/policy/run data, not only `archive-snapshot.json`.
9. **Remove or make explicit the hidden test skips**; print skipped-test reasons in CI summary.
10. **Do not treat the code-side readiness as E1 evidence**; the physical gates and the first bench remain the critical path.
