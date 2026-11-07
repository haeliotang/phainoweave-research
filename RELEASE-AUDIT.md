# Phase 1 release audit

**Status:** released research snapshot · **Source commit:** recorded in `EXPORT-MANIFEST.json` · **Release:** 2026-11-07 / `research-2026-11-07`

## 1. Purpose and boundary

This audit covers the sanitized research snapshot produced by a clean-source release-mode export; the exact source commit is recorded in `EXPORT-MANIFEST.json`. It does not approve making the private `phainoweave` repository public, and it does not create a public repository.

The snapshot is a released research artifact, not a product and not evidence of real-world physical inference.

## 2. Allowlist and exclusions

The manifest uses a default-deny allowlist. Excluded by policy:

- `.git/`, `.github/`, `.repro/`, `artifacts/`, `data/`, caches, virtual environments;
- the Tauri desktop app and all Rust runtime crates except the E0 seed config;
- the container, deployment, and CI harnesses;
- private governance execution code and the private evidence logs;
- images and screenshots;
- any file not named by an allow entry.

## 3. Licence review

| Material | Proposed licence | Status |
|---|---|---|
| Python research code | Apache-2.0 (root LICENSE) | ready, subject to dependency notice review |
| Documentation | CC BY 4.0 | **confirmed by maintainer 2026-11-07**; Gate 3 authorized 2026-11-07 |
| Synthetic C2-C evidence | CC0-1.0 | **confirmed by maintainer 2026-11-07**; synthetic, no personal data |
| `CITATION.cff` / README | same as documentation | CFF 1.2.0 schema validation passed with `cffconvert`; licence approval remains with the maintainer |
| Code snippets in docs | Apache-2.0 for code, CC BY 4.0 for prose | boundary stated in `LICENSING.md` |
| Third-party dependencies | per their own licences; see `THIRD_PARTY.md` | review recorded; no vendored code or data |

Apache-2.0 permits broad use, including commercial use. The research-purpose and non-military/non-surveillance statements in the README are **ethical scope statements**, not additional licence terms, and are not legally enforceable restrictions on Apache-2.0 rights.

## 4. Security and privacy scan (candidate export)

The candidate export (`244` files) was scanned by `scripts/export_research_snapshot.py`:

- **blocked findings: 0** (no absolute user paths, absolute home paths, private-key or token patterns in exported text);
- **symlinks: 0**; no `.git` directory was copied;
- **review findings: 39 in the final export** — 34 generic temporary-path strings, 4 historical run ids, 1 environment-variable name. The earlier 42-finding review had 3 audit-report occurrences; those were **transformed** by rewording the audit text. All 42 recorded findings have a disposition in `DISPOSITIONS.json` / `DISPOSITIONS.md`: 39 `accepted_public`, 3 `transformed`, none `requires_review`. No science input was changed to obtain a zero count;
- **6 private-code links** in exported docs were rewritten to plain text because their targets (Rust/CLI/desktop/scripts) are not in the research snapshot;
- archive subset checksums: `sha256sum -c SHA256SUMS.public` passed for all five included C2-C files;
- a previously included `python/.DS_Store` was removed from the allowlist and frozen hashes. The exporter now denies platform metadata (`DS_Store`, `Thumbs.db`, `desktop.ini`, `.localized`) and unknown binary files by default; the C2-C `.gz` is the only explicit binary-evidence exception;
- content classification is now byte-based, not suffix-based: every file is tested for strict UTF-8; decodable files are scanned even without a suffix, and non-decodable files require an explicit `binary_evidence` manifest entry and matching frozen hash. Negative tests are in `scripts/test_export_security.py`.

A bounded scan of private Git history for token/key patterns found no matches; it did find historical absolute `absolute private workspace paths` paths in failure logs. This is exactly why the public snapshot excludes `.git` and those logs, and why a full private-history audit is still required before any repository visibility change.

## 5. Data publication risk

- C2-C evidence is synthetic, but publishing the sealed trial grid converts it into a **public evaluation set**.
- The public snapshot must not be used as an unseen sealed set for future confirmatory claims.
- No real bench data exists, so no real site, person, consent, or calibration data is included.

## 6. Reproduction test

Executed from the candidate export:

- E0 recomputed to `records_sha256 674213d9…`;
- C2-C independent recomputation returned the published B0–B3 counts and `independent recomputation OK`;
- C1 locked run completed (500 trials per claim);
- `python/tests` passed 448 tests;
- public documentation links: 558 checked, 0 broken.

These are candidate-snapshot checks, not a real-world validation.

## 7. CI evidence status

- Last successful code verification remains run `42367318697` at `6cd02f1` (24/25 jobs; optional macOS arm64 skipped).
- The later docs-only run `42379526139` failed with zero executed steps (22 failure, 3 skipped); it is **unexecuted verification**, not a code-regression result and not a passing claim for the release-prep commits.

## 8. Open items / blockers

- Gate 3 public authorization recorded 2026-11-07;
- dependency and third-party notice review (recorded in `THIRD_PARTY.md`, maintainer confirmation outstanding);
- private Git history audit and credential rotation policy (separate security debt);
- macOS arm64 authoritative CI remains unavailable in the private repository;
- DOI registration remains pending;
- no public repository, tag, DOI or release has been created.
