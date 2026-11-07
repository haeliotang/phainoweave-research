# Public C2-C evidence subset

This directory is a public subset of the private content-addressed C2-C sealed archive.

Included:

- `ARCHIVE.json` — original archive manifest and run lifecycle;
- `SHA256SUMS.public` — checksums for the files in this public subset;
- `c2-repair.json.gz` — the sealed artifact, decompressed SHA-256 `641a1003…`;
- `c2-repair-summary.md` — the sealed result summary;
- `eval/report.json`, `eval/report.md` — the sealed evaluator output.

Excluded from the public snapshot:

- `run-record.json`, `run-console.log`, and `attempts/` — they contain local workspace paths used during the private run;
- the full private archive remains the authoritative audit source.

The original `ARCHIVE.json` still lists the full archive. Verify public files against `SHA256SUMS.public`; do not infer that omitted files are absent from the private archive.

The core sealed artifact digest is `641a100384af991ab71952e9baa1b14825accdcb7d81f407fec8ed55ed8d6d8d`.
