# C4 semantic audit — execution status vs scientific outcome and claim scoping

**Status:** audit complete; one contradiction found and fixed; no unbounded real-world claim found · 2026-11-05 · **Authority:** [ADR 0024](../decisions/0024-run-lifecycle-and-evidence-archive.md)

## 1. Scope

C4 checks that the project does not conflate:

- **execution validity** (did the run execute?) with **scientific outcome** (what did it conclude?);
- a **limited, scoped result** (synthetic sealed benchmark, single environment) with a general real-world claim;
- **adequacy acceptance** with **supported physical claim**.

Checked: the content-addressed archive and all run records, ADR 0024/0025, the sealed confirmation, attempt records, roadmap status, and the C2-C contract documents.

## 2. Findings

| Check | Result |
|---|---|
| Every archived run carries `execution_status` and `scientific_outcome` | pass (3/3 runs) |
| `invalid_execution` is recorded as `not_evaluated`, with reason and revision | pass (attempts 1–2) |
| Completed run outcome references `hypothesis_id`, `decision_protocol`, `data_scope` | pass (`H-C2C-B1-01`, v3 manifest, synthetic sealed grid) |
| No archived run uses the retired `scientific_failure` execution state | pass |
| Sealed report keeps B1 conditional and bounded | pass (high-chirp 0/30, time-block caveat, single environment stated) |
| No "real-world reliable / measurement model fixed" claim found | pass |
| **ADR 0024 main body still described a single-state lifecycle including `scientific_failure`** | **contradiction with its own amendment — fixed** |

The contradiction was real: the top of ADR 0024 defined `scientific_failure` as an execution state while the amendment (and the code) had moved to orthogonal fields. A reader could have re-introduced the conflation the amendment removed. The main body was corrected to the two-field model; `scientific_failure` is no longer an execution state.

## 3. Executable guardrails added

`python/tests/test_archive_semantics.py` now enforces, on every test run:

- both fields present and valid for every archived run;
- `invalid_execution` → `not_evaluated` + reason + revision;
- completed outcomes carry hypothesis/protocol/data_scope;
- history is a valid execution transition chain;
- no archive run claims unbounded real-world success.

This turns the semantic rule into a failing test rather than a convention.

## 4. Residual limitations

- The audit is pattern- and schema-based; it cannot judge whether a prose sentence is scientifically overconfident beyond the checked phrases.
- Historical frozen reports were not rewritten; their language is reported, not retro-edited.
- The archive is content-addressed but not signed; integrity is SHA-256 + repository history, not an external timestamp.

## 5. Recommendation

Every future run summary must quote the outcome together with its `hypothesis_id`, `decision_protocol` and `data_scope`. A summary that says only "completed / supported" is considered incomplete.
