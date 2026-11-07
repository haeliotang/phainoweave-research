# Phase 1 release readiness

**Overall:** `released` — Gate 2 technical readiness passed and Gate 3 was authorized by the maintainer on 2026-11-07. Public repository and tag are recorded below; no DOI has been registered.

| Gate | Status | Evidence / blocker |
|---|---|---|
| Gate 1 — manifest freeze | **ready** | `research-release-manifest.json`; default-deny allowlist; source commit pinned; 244 per-file SHA-256 records |
| Formal clean export | **ready** | release-mode from a clean worktree; exact source is in `EXPORT-MANIFEST.json`; 244 files, 0 blocked, 39 review-only findings, 6 link rewrites, 558/0 public links |
| Exporter content class | **ready** | every file is UTF-8-tested; non-UTF8 requires explicit binary_evidence; negative tests in `scripts/test_export_security.py` |
| Sanitized export | **ready** | `scripts/export_research_snapshot.py`; 244 files; no `.git`; 0 blocked findings; 39 current review-only matches (42 recorded dispositions); 6 private-code links rewritten |
| E0 reproduction | **ready** | candidate export recomputes `records_sha256 674213d9…` |
| Public test suite | **ready** | `448 passed` from the candidate export |
| Public documentation links | **ready** | `558 checked; 0 broken` in the candidate export |
| Finding dispositions | **ready** | 42 recorded: 39 `accepted_public`, 3 `transformed`; final export has 39 review-only findings; no secret or private locator found |
| C2-C independent recomputation | **ready** | `scripts/independent_sealed_recompute.py` returns the published counts; public subset checksums pass |
| C1 reproduction | **ready** | candidate export completed a full locked C1 run |
| CITATION.cff | **ready** | validated with `cffconvert` against schema 1.2.0; `authors` present; `date-released` omitted until the actual release |
| Licence / rights | **ready** | maintainer confirmed rights and CC BY 4.0 / CC0 1.0 scheme on 2026-11-07; recorded in `RIGHTS-CONFIRMATION.md` |
| Candidate export history | **ready** | no `.git`, symlinks or blocked token/path patterns in the export |
| Private history audit | **requires_review** | bounded token scan found no keys; historical `absolute private workspace paths` paths exist in private logs; full audit still required before any visibility change |
| macOS arm64 CI | **requires_review** | optional/private CI cell skipped; public snapshot must disclose the gap |
| CI evidence | **requires_review** | last code run `42367318697` success; later docs-only `42379526139` failed before steps and is recorded as unexecuted |
| Gate 3 authorization | **approved** | maintainer authorization recorded 2026-11-07 |
| Public repo / tag | **released** | `haeliotang/phainoweave-research`, tag `research-2026-11-07` |
| DOI | **pending** | to be registered after the public snapshot is frozen |
| Real bench evidence | **not applicable** | E1 is `prepared / not_evaluated`; no real data is in scope |

A `ready` row means the local candidate artifact exists and was exercised. It does not mean the snapshot is approved for public release. The **Public Snapshot Disclosure Audit** is the mandatory Phase 1 gate; the **Private Repository History Audit** is separate security debt and is not an absolute prerequisite for a history-free sanitized snapshot.

## Release record

- Gate 2 technical readiness: accepted.
- Gate 3 maintainer authorization: 2026-11-07.
- Public repository: `haeliotang/phainoweave-research`.
- Tag: `research-2026-11-07`.
- Private engineering repository visibility remains unchanged.
- DOI: not yet registered.
