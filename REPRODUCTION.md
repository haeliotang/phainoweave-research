# Reproduction Guide

This guide describes how an external researcher can recompute the central published results from the candidate snapshot. It is deliberately limited to the synthetic studies.

## Environment

Recommended pinned environment:

- Python **3.14.9**
- NumPy **2.4.4**
- SciPy **1.17.1**
- SymPy **1.14.0**
- pytest **8+** for the test suite

The E0 acoustic fit is an in-house deterministic Levenberg–Marquardt implementation; NumPy is sufficient for that fit. C1/C2 paths may require SciPy/SymPy.

## 1. E0 — synthetic Doppler

```bash
PYTHONPATH=python python -m phaino_acoustics.experiment \
  --config e0/e0-config.json \
  --output-dir out/e0 --jobs 2
```

Expected: the produced result carries `records_sha256` beginning `674213d9…` and the frozen E0 artifact is not modified. Cross-platform execution may differ at the decision boundary; a mismatch is evidence, not a reason to tune thresholds.

## 2. C2-C — independent sealed recomputation

```bash
python scripts/independent_sealed_recompute.py \
  evidence/c2c-sealed/c2-repair.json.gz
```

This script does **not** import the frozen evaluator, the acoustics package, or a truth helper. It reconstructs correctness from the archived artifact and the frozen tolerances, then compares the published counts.

Expected published counts include:

- B0: supported 44/426, FRR 278/406, detected 90/120, undetermined 30/120;
- B1: supported 335/426, FRR 8/406, detected 90/120;
- B2: supported 102/426, FRR 138/406, detected 90/120;
- B3: supported 176/426, FRR 58/406, detected 90/120.

The script exits nonzero on a mismatch. These are the published C2-C numbers, not a new confirmation.

## 3. C1 — locked claim validation

```bash
PYTHONPATH=python python -m phaino_claims.experiment \
  --layer locked --protocol protocols/pr4e-claims-1.3.0.json \
  --out out/c1-locked.json --jobs 2
```

The candidate export produced the locked C1 artifact with 500 trials per claim. This verifies the recorded claim-decision pipeline (statuses and gate outcomes) on the frozen synthetic protocol; it is not an exact numerical reproduction across every platform and not a new physical validation. The artifact carries the exact counts.

## 4. Tests

```bash
PYTHONPATH=python python -m pytest python/tests -q
```

Some platform-conditional tests are skipped outside their recorded reference environment; the skip reason is part of the output. A skipped test is not a pass.

## 5. Archive integrity

The public snapshot contains a **subset** of the full sealed archive: the sealed artifact, archive manifest, report, summary, and integrity metadata. Internal run-console and attempt logs are excluded because they contain local paths. The full archive remains in the private engineering repository.

The core artefact digest is:

`641a100384af991ab71952e9baa1b14825accdcb7d81f407fec8ed55ed8d6d8d`

## 6. What cannot be reproduced here

- Real bench data: none exists.
- macOS arm64 authoritative CI: not run for the public snapshot.
- E1 physical conclusions: none are claimed.
- The complete runtime, Tauri cockpit, and security/governance execution paths: not part of the research snapshot.

If a result cannot be recomputed from the snapshot, that is a **release blocker**, not a documentation gap.
