# C2-C sealed run — attempt 1 (invalid, execution failure)

**Status:** invalid for confirmation; sealed run not executed; first record preserved per ADR 0023 §E2 · 2026-11-05 · **Manifest:** `protocols/c2c-freeze-v1.json` (`23ad3dd1…`)

## What happened

Preflight passed: manifest digest recomputed to `23ad3dd1…`, 26 dependency hashes and the runner sha256 matched; `verify_only` did not open the sealed grid.

The single run attempt started at `2026-11-05T04:57:05Z` and stopped after `0.12 s`, before generating any trial, with:

```
ValueError: C2-C grid digest mismatch in <private-workspace>/protocols/c2c-grid-v1.json
```

No artifact, no candidate metrics. `sealed_run_count_attempted = 1`, `sealed_run_count_valid = 0`; no retry, no output selection, no code/calibration/threshold change.

## Root cause

The committed grid v1 was written with `selection_inputs_assertion` added **after** the digest was computed:

- `build_grid()` computes `grid_digest` without the assertion;
- `c2_grid.main()` then appends `selection_inputs_assertion` and writes the file;
- `load_grid()` re-digests every top-level key except `grid_digest`, so the committed file can never self-verify.

This is a writer/loader contract inconsistency, not a candidate or scientific result. The manifest also failed to include `python/phaino_acoustics/c2_grid.py` in its dependency hash set, so preflight could not detect the drift.

## Validated facts

- grid file sha256 `5bec5ef1…` (identical to the C2 grid artifact); declared digest `cb8d869d…`; recomputed over the whole file `2978c8b2…`.
- loader sha256 `953bc3b4…`; the digest mismatch occurs before any trial is generated.

## Fix (revision protocol)

1. `c2_grid.main()` recomputes `grid_digest` after adding `selection_inputs_assertion`; the frozen file now self-verifies under `load_grid()`.
2. New grid artifact `protocols/c2c-grid-v2.json`: sha256 `2f0005a1…`, digest `2978c8b2…`, 59 conditions / 566 trials / seed base 60,000,000. `pr4e-c2c-v1` grid id/version unchanged; only the digest contract is corrected.
3. The revision manifest (`c2c-freeze-v2`) must include `c2_grid.py` in its dependency hashes and reference the v2 grid file/digest.
4. A new single run under the revision manifest is required; attempt 1 remains recorded as invalid and is not reused or interpreted.

This record is intentionally separate from any result: no candidate was evaluated, and no conclusion about B1/B3 can be drawn from it.
