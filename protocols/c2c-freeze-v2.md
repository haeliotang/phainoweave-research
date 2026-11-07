# C2-C sealed freeze manifest **v2** — stage 1 rationale

**Status:** stage 1 complete — v2 frozen, **no sealed run**; attempt 1 (v1) is invalid · 2026-11-05 · **Authority:** ADR 0023 §D/E2, ADR 0022 §4, ADR 0020 §D/G

**Manifest:** `protocols/c2c-freeze-v1.json` → `protocols/c2c-freeze-v2.json`
**Canonical digest:** `033fb2620fc1d95f6bdd21538c7e14c3e9d395951007f5f808a581159b1c460c`
**Predecessor:** v1 `protocols/c2c-freeze-v1.json` digest `23ad3dd10a3940336f6bbb880ec45b3be8226c990770ada9f2465193dd89f8ca` — attempt 1 invalid for confirmation, no valid run.
**Runner:** inline frozen program sha256 `dafc473949afa08c3bd9a1147bf010fb78657ba43f5870ed83ae279150e03d83`; loads only `protocols/c2c-grid-v2.json`.

## Revision v2 — what changed and why

- **Attempt history:** attempt 1 (`2026-11-05T04:57:05Z`, manifest v1) failed at `c2_grid.load_grid -> verify_grid_digest` with `ValueError: C2-C grid digest mismatch in …/protocols/c2c-grid-v1.json`; no artifact, no valid run, no retry.
- **Root cause:** v1 grid was written with `selection_inputs_assertion` appended after digest computation, while the loader digests every top-level key except `grid_digest`; v1 could not self-verify.
- **Fix:** new sealed grid `protocols/c2c-grid-v2.json`, sha256 `2f0005a16dc5d223245629a6e29ef0ebf38d0252a6e714bf56ad4ae07b351987`, digest `2978c8b24d0ef1bd3b787f13f68431230720154a288575a41067c8ad4c26eeaf`, 59 conditions / 566 trials / seed base 60000000. The file content is identical to v1 except the `grid_digest` field now covers the assertion too; current `c2_grid.load_grid` verifies it.
- **Dependency graph:** `python/phaino_acoustics/c2_grid.py` (`b49af98d16ef54225d78fa2a4028b815bf243b9ba930d23cfed2df5997a61c00`) and `python/tests/test_c2_grid.py` (`ef355df1670c63cfbef716a8dc082f723124c5924352ed1aa1b7a7641390da08`) are now frozen dependencies; the v2 grid file is itself a frozen dependency.
- **Unchanged from v1:** candidate implementations/rules, calibration sample and seeds, adequacy/claims protocols, evaluator, tolerances, primary endpoint, detection-loss bound, undecided policy, interval method and failure rules. Re-hashed from the current working tree.

## Primary endpoint (unchanged, pre-declared before opening any grid)

**Name:** `correct_cv_supported_coverage_and_detection_B1_vs_B0`

**Definition:** On identical paired sealed-grid observations, B1 vs B0: increase correct-CV valid supported coverage (equivalently reduce correct-CV false rejection) without losing acceleration discrepancy detection beyond the pre-registered bound. Supported coverage is the fraction of truth-correct correct-CV trials whose candidate record is validly supported by the frozen C1 claim gate.

**Decision rule:** B1 primary confirmation requires all of: (1) paired false-rejection risk difference (B1-B0) < 0; (2) paired valid supported coverage increases (B1 > B0); (3) zero claim-integrity violations for B1 (all claim statuses within {supported_conditional, undetermined, contradicted}; no supported_invariant); (4) the detection non-inferiority rule below holds. The evaluator numeric primary_result checks (1) and (4); (2) and (3) are mandatory pre-declared guardrails reported as secondary metrics and must both hold for confirmation.

**Detection non-inferiority rule:** Paired acceleration discrepancy-detected risk difference (B1-B0) >= -0.10 (detection_loss_bound), under undecided_policy=not_detected: an undetermined acceleration trial is not counted as detected. The alternative excluded-policy analysis is a reported sensitivity, not the primary rule.

**Numeric evaluation (frozen evaluator):** primary metric `supported_coverage`; paired supported-coverage risk difference B1−B0 > 0 and paired acceleration `discrepancy_detected` difference ≥ −0.10 under `undecided_policy=not_detected`; 95% paired Wald interval, false-rejection guardrail and claim-integrity guardrail are reported and applied by the Lead per the frozen final confirmation rule.

## Hash list

| item | sha256 / digest |
|---|---|
| `python/phaino_acoustics/repair_candidates.py` | `3803b0e5f3ee415d1b8fa30c264967d22cceb96d6dec0768d75a8cd1582cd5ff` |
| `python/phaino_acoustics/experiment_repair.py` | `3d51004c7c37bfb2fba18d7d09c25018f369bf6237a96db2b565d341f611c2ca` |
| `python/tests/test_repair_candidates.py` | `ec10f76ef1f8b13506da2a2cf34d80229a1a76e1a3e36775938963ee8ee25f22` |
| `python/phaino_acoustics/repair_selfcheck.py` | `195cc4ee4ef9a000edfba9d95548a91028151250791d6ead24a8eed71c6baf96` |
| `python/tests/test_repair_selfcheck.py` | `f22104211650346ee573acd420732b7979bf7bb5e1a0ec8054bc420a7b2cc7e4` |
| `python/phaino_acoustics/c2_grid.py` | `b49af98d16ef54225d78fa2a4028b815bf243b9ba930d23cfed2df5997a61c00` |
| `python/tests/test_c2_grid.py` | `ef355df1670c63cfbef716a8dc082f723124c5924352ed1aa1b7a7641390da08` |
| `python/phaino_acoustics/adequacy_protocol.py` | `c5c0427207436ae8c3a4562ab71d7f92ff4f61f8db6eaec77bf0980b55ea6b17` |
| `python/phaino_acoustics/measurement_model.py` | `6c52d9b2c9ccbca52db72f2b2d56609881650e9db95ad1d596db5d2e2b6e471c` |
| `protocols/pr4e-claims-1.3.0.json` | `16c62ca63577668b4dfb45f542db97214d1275a2b0dcd95c3e23734871dcbfa6` |
| sealed grid v2 file (`protocols/c2c-grid-v2.json`) | `2f0005a16dc5d223245629a6e29ef0ebf38d0252a6e714bf56ad4ae07b351987` |
| sealed grid v2 definition digest | `2978c8b24d0ef1bd3b787f13f68431230720154a288575a41067c8ad4c26eeaf` |
| evaluator package digest | `b8ffb2459adcaf6bf1f480c48da35459bedc8fad38a69ace51447505aeb968d5` |
| adequacy protocol digest | `c86cb63d487e72a2c9964bfdaf41aa8adfa84199ce1515071eeceb1b78d9f029` |
| claims protocol digest / gate policy digest | `193e70ab42cd1c953d89c735ee6fa4c19bc7aed98d11e2af8cba751c9191e52f` / `b1379457562af446a4136e560200c7e551247668b886a017bfde0ab2c47710da` |
| execution runner program | `dafc473949afa08c3bd9a1147bf010fb78657ba43f5870ed83ae279150e03d83` |
| dependency bundle (29 files) | `4f635cd732a9f0e731ae105b801862275e0a571f58c833e690ba2acd64dbe030` |
| development artifact provenance (`/tmp/c2-repair-final/c2-repair.json`) | `b32d91f8f5b787f73d261e65633e0d537e4d2154009905b272a5f7015a9c9dcd` |
| development summary digest | `c70037a04d65b4c55909fc07f94580cb9fa9709606cf1c49059e74da960d40b5` |
| selfcheck artifact / verdict digest | `9cc967681259454b96c48a6f9afe3eed948b8330905e2112e593b666910b7225` / `77c5ff5752a1f8c997e599c8d97c868dae9b07af2e1d33e9aa165806b1fcef2a` |
| calibration sample-definition digest | `e0cf48f4bdf6aa2f89cbaf748fbb981623cb3cf5c5805a71498066a03d854c85` |
| manifest canonical digest | `033fb2620fc1d95f6bdd21538c7e14c3e9d395951007f5f808a581159b1c460c` |

## Stage-1 verification performed (no sealed run)

```
manifest_digest: <v2 digest, recomputed from file>  # match
program_sha256: dafc473949afa08c3bd9a1147bf010fb78657ba43f5870ed83ae279150e03d83  # sha256(program text) matches
dependency_hashes_ok: 29
frozen protocol and calibration digests ok
verify_only: preflight passed; v2 grid bytes hashed for dependency verification; grid not parsed/loaded; no trial generation
```

- The v2 grid file was read in stage 1 **only** for sealing: file sha256 recorded as a dependency and its declared definition digest verified with `c2_grid.load_grid` during manifest construction; no trial was generated or executed.
- Candidate/development implementation files contain no sealed-grid filename or 60M seed reference; the chain from candidate/development code to the grid is only the frozen runner.
- `sealed_grid_non_use_evidence` in JSON records the static checks and seed facts; `c2_diagnosis_seeds_reused = false`; v1 grid never used.

## Remaining gaps (also in JSON `unfrozen_gaps`)

- The evaluator package may still be edited by another workstream; v2 freezes the current working-tree hash. Re-run the v2 preflight immediately before committing; regenerate/re-freeze if any dependency hash changed.
- v1 grid `protocols/c2c-grid-v1.json` remains in the tree as a historical invalid artifact. It must never be used; v2 manifest/runners reference only `protocols/c2c-grid-v2.json`.
- ADR 0023 B selfcheck artifact is referenced by hash/verdict digest only; its time-block-holdout finding must be adjudicated by the Lead.
- B3's low estimated-SNR conditioning branch has zero admissible calibration samples in the frozen calibration design; the artifact declares it unverified (ADR 0023 C).
- The C2-M2 M3 error model has no separate semantic version field; its acceptance-contract version/digest is declared in the C2-M2 report and not recomputed here; it is not used by B0-B3.
- Cross-platform reproducibility of repair artifacts is not frozen or claimed; environment_id is recorded per artifact.
- No repository commit hash is available in the manifest (git operations were not performed); authority documents are frozen by working-tree sha256.
- The development report still cites the pre-metadata-update artifact sha; reconciliation remains a docs action outside stage-1 scope.
- The v2 sealed runner is an inline program frozen by hash rather than a committed file; if the Lead prefers a file, this manifest must be revised.
- The v2 grid file was read in stage 1 only for sealing hash/digest verification; no trial was executed. Any further change to the grid file or c2_grid.py invalidates this manifest.

## Execution discipline (unchanged from v1)

- exactly one sealed run per frozen v2 manifest/candidate set; runner refuses an existing artifact;
- execution failure invalidates the run, keeps the first record, and requires a new revision; no retry or output selection;
- valid artifact missing the pre-registered primary rule is a scientific negative result, published in full;
- cross-environment execution is a separate reproducibility dimension, not a second confirmation.

## Next step (Lead)

Commit `protocols/c2c-freeze-v2.json` and this rationale, then instruct the single sealed run. The runner is executed from `sealed_runner.program` via stdin; it verifies the manifest digest, **29** dependency hashes (including the v2 grid file), `c2_grid.py`, frozen protocols/calibration and the v2 grid id/digest/566 trials before the single run.
