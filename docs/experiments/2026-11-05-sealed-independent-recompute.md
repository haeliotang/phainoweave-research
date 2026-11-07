# Sealed analysis — independent recomputation

**Status:** independent implementation reproduces the published sealed metrics exactly; one label-definition nuance reported · 2026-11-05 · **Artifact:** `641a1003…` · **Prior:** [sealed confirmation](2026-11-05-c2-sealed-confirmation.md)

## 1. Why

The sealed confirmation was produced by `phaino_c2_eval`. An exact reproduction by a second implementation is execution evidence that the published numbers are not an artefact of one code path.

`scripts/independent_sealed_recompute.py` deliberately imports neither the evaluator, the acoustics package nor any truth helper. It reads the archived artifact, reconstructs correctness from scenario/params and the frozen tolerances, and re-derives support and the misspecification taxonomy.

## 2. Result

| Candidate | Supported coverage | FRR | Detected (accel) | Undetermined | False-supported |
|---|---|---|---|---|---|
| B0 | 44/426 | 278/406 | 90/120 | 30 | 0 |
| B1 | 335/426 | 8/406 | 90/120 | 30 | 0 |
| B2 | 102/426 | 138/406 | 90/120 | 30 | 0 |
| B3 | 176/426 | 58/406 | 90/120 | 30 | 0 |

These are **exactly** the published sealed numbers; claim-status violations 0 and null promotions 0. The recomputation is reproducible from the repository:

```
python3 scripts/independent_sealed_recompute.py
```

## 3. Nuance found: whose parameters define "correct"?

The frozen evaluator labels a trial correct from the artifact's `evaluation_only.truth_correct` field, which is derived from the **baseline B0 fit** (the artifact declares `label_source: "baseline B0 fit (evaluation only)"`). Recomputing correctness from **each candidate's own parameters** gives:

| Candidate | baseline-label correct | candidate-own correct |
|---|---:|---:|
| B0 | 406 | 406 |
| B1 | 406 | **416** |
| B2 | 406 | 406 |
| B3 | 406 | 406 |

So B1's own fits are within the frozen tolerances on 10 more correct-CV trials than the baseline label; its published FRR 8/406 would be 8/416 under a candidate-own denominator. Coverage (335/426) and detection (90/120) are unchanged, and the primary-endpoint conclusion is robust either way.

This is a **label-definition** issue, not a numerical error: the evaluator intentionally freezes one truth label so candidates are compared on the same trials. Future reports should state which label definition is used; a candidate-own denominator must not be mixed with the frozen-labelled numerator. The frozen sealed report is not rewritten; this note records the distinction.

## 4. What this establishes

- The published sealed metrics are independently reproducible from the archived bytes.
- The primary conclusion does not depend on the single evaluator implementation.
- A methodological nuance (baseline vs candidate-own truth label) is now documented and testable.

## 5. Limits

- Same artifact; this is not a new experiment.
- The independent script reuses the frozen truth tolerances and the artifact's trial metadata; it does not re-run the acoustic fit.
- It verifies the sealed numbers, not real-world measurement reliability.
