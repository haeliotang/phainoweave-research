# Errata — published Phase 1 snapshot metadata

**Applies to:** tag `research-2026-11-07`, initial public commit `b163466`
**Status:** metadata clarification only; the tagged snapshot is not rewritten.

Three metadata inconsistencies were found after publication:

1. `EXPORT-MANIFEST.json` in the tagged snapshot records
   `release.status = "candidate_not_published"` and
   `release.version = "0.1.0-research-candidate"`. The actual release is
   `0.1.0-research`, tag `research-2026-11-07`. The scientific content and
   artifact hashes are unchanged.
2. The same file has two source fields:
   - `release.source_commit = 4572302...` is the **frozen manifest baseline**;
   - top-level `source_commit = 317da92...` is the **actual clean export commit**.
   These are different roles, not a contradiction. Corrected exports record both
   explicitly as `source_commit` (actual) and `manifest_source_commit` (baseline).
3. Some public README/licensing text still says "proposed" because it predates
   the maintainer's 2026-11-07 rights/licence confirmation. The maintainer
   confirmed CC BY 4.0 for documentation and CC0 1.0 for project-owned synthetic
   evidence; third-party materials retain their own licences. The tagged text
   is retained for provenance; this note records the confirmed status.

No experiment code, protocol, evidence artifact, hash, or scientific claim was
changed. The tag continues to point to `b163466`; this errata is a follow-up
commit on `main`, not a replacement of the research release.
