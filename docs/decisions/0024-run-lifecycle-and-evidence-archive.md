# ADR 0024 — Sealed-run lifecycle and content-addressed evidence archive

Status: Accepted
Date: 2026-11-05
Deciders: Haelio Tang (founder)

## Context

C2-C attempt 1 failed on a grid digest contract and attempt 2 on a stdin/multiprocessing-spawn incompatibility; only attempt 3 produced a valid artifact. Both invalid attempts were preserved, but they existed only as `/tmp` logs, and the single valid sealed artifact (9.4 MB JSON, sha `641a1003…`) also lived only in `/tmp`. A report that depends on temporary local files is not an auditable confirmation.

## Decision

1. **Every sealed run has two orthogonal fields** (amended 2026-11-05; this replaces the earlier single-state `scientific_failure` design):
   - `execution_status`: `prepared → sealed → running → completed | invalid_execution`;
   - `scientific_outcome`: `pending | hypothesis_supported | hypothesis_rejected | inconclusive | not_evaluated`.
   - transitions are validated (`python/phaino_verify/run_state.py`);
   - `completed` requires the artifact digest;
   - `invalid_execution` requires a reason **and** the revision it refers to, forces `scientific_outcome = not_evaluated`, and is terminal and non-deletable;
   - a completed experiment may support, reject or fail to decide its hypothesis; **a negative or inconclusive scientific result is not an execution failure**.
2. **Invalid attempts are part of the record.** They may not be overwritten, omitted, or retried under the same revision. A revision protocol is required and its predecessor is cited in the new manifest.
3. **Execution evidence is archived in the repository's content-addressed evidence store** (`evidence/`), not only in `/tmp`. Each archive records:
   - the original artifact digest and a deterministic compressed copy (`gzip -n`), so decompressed bytes can be re-verified;
   - the evaluator output, run record, console log, and every attempt's log;
   - per-file SHA-256 in `ARCHIVE.json` and `SHA256SUMS`;
   - the run lifecycle histories.
4. **Verification is a command, not a claim:** `sha256sum -c evidence/<run>/SHA256SUMS` and `gunzip -c <artifact>.gz | sha256sum` must match the recorded digest.
5. **This applies to E1 and later real-data runs.** Raw recordings remain under the data policy; the evidence archive stores frozen artifacts and execution records, not sensor data.

## Amendment — execution status and scientific outcome are orthogonal (2026-11-05)

A completed run may support or reject its pre-registered hypothesis; a negative result is not an execution failure. The lifecycle therefore has two orthogonal fields:

- `execution_status`: `prepared → sealed → running → completed | invalid_execution`;
- `scientific_outcome`: `pending | hypothesis_supported | hypothesis_rejected | inconclusive | not_evaluated`.

`invalid_execution` forces `scientific_outcome = not_evaluated` and cannot later receive an outcome. `completed` requires the artifact digest; the scientific outcome is set only after completion and is immutable. `python/phaino_verify/run_state.py` enforces both, and `evidence/c2c-sealed/ARCHIVE.json` records the C2-C attempts with `invalid_execution/not_evaluated` and the valid run with `completed/hypothesis_supported`.

## Consequences

- A reader can audit the sealed result without access to the author's `/tmp`.
- Invalid executions become documented, first-class outcomes with a revision trail.
- The archive adds a small tracked binary (compressed artifact) to the repository; acceptable for a confirmation artifact of this size.
- The state machine adds process overhead before runs.
- Two fields must both be reported; a report that says only "failed" without saying whether execution or hypothesis is now incomplete.

## Alternatives considered

- **Keep only `/tmp` logs and cite hashes in a report.** Rejected: not persistent, not independently verifiable.
- **Discard invalid attempts.** Rejected by the ruling: they are the evidence that the protocol was enforced.
- **Store raw artifacts uncompressed in git.** Rejected: 9.4 MB is unnecessarily heavy; deterministic gzip preserves verifiability.

## References

- [C2-C sealed confirmation](../experiments/2026-11-05-c2-sealed-confirmation.md)
- [Attempt 1 record](../experiments/2026-11-05-c2-sealed-attempt1.md)
- `evidence/c2c-sealed/ARCHIVE.json`
