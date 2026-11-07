# C2-C sealed freeze manifest — stage 1 rationale

**Status:** stage 1 complete — manifest frozen, sealed grid NOT opened, sealed run count 0 · 2026-11-05 · **Authority:** ADR 0020 §D/G, ADR 0021 §E, ADR 0022 §4, ADR 0023 §D/E

**Manifest:** `protocols/c2c-freeze-v1.json` · canonical digest `23ad3dd10a3940336f6bbb880ec45b3be8226c990770ada9f2465193dd89f8ca`
**Runner:** inline python program frozen by sha256 `1afec8c2e8acd7571bc53127d29d6e961edaa6a52fb7e6a0e1755302468a192c`; preflight passed without opening the grid.

## What this manifest freezes

- candidate implementations B0–B3 and their parameters/calibration rules (B0 frozen adequacy; B1 de-chirp; B2 AR(8) pre-whitening; B3 conditional threshold calibration);
- the calibration sample definition and seeds (base 91,000,000; 40 conditions x 2 trials = 80 admissible correct-model trials);
- the measurement model `e0-frontend-hann-stft-512-256@1.0.0` and its declared error-model id `e0-c2a-empirical-bias-ar1-v1`;
- frozen adequacy protocol `adeq-1.0.0` digest `c86cb63d487e72a2c9964bfdaf41aa8adfa84199ce1515071eeceb1b78d9f029`;
- frozen C1 claim gate `pr4e-claims-1.3.0` digest `193e70ab42cd1c953d89c735ee6fa4c19bc7aed98d11e2af8cba751c9191e52f`; gate policy digest `b1379457562af446a4136e560200c7e551247668b886a017bfde0ab2c47710da`;
- evaluator package `python/phaino_c2_eval` (schema 1.0.0) package digest `b8ffb2459adcaf6bf1f480c48da35459bedc8fad38a69ace51447505aeb968d5` and its contract tests;
- dependency bundle digest `9a04f0ccc3eb324d7341aacb586d9d6946160249129da4c3d005fe00c60c3ee9` over 26 files;
- tolerances, classification rules, interval method, detection-loss bound and undecided-trial policy;
- primary and secondary endpoints, failure-handling rules, single-run rule and implementation-error rule;
- declared sealed-grid identity (`pr4e-c2c-v1`, declared digest `cb8d869d…`, 566 trials, seed base 60,000,000) and non-use evidence.

## Primary endpoint (pre-declared before opening the grid)

**Name:** `correct_cv_supported_coverage_and_detection_B1_vs_B0`

**Definition:** On identical paired sealed-grid observations, B1 vs B0: increase correct-CV valid supported coverage (equivalently reduce correct-CV false rejection) without losing acceleration discrepancy detection beyond the pre-registered bound. Supported coverage is the fraction of truth-correct correct-CV trials whose candidate record is validly supported by the frozen C1 claim gate.

**Decision rule:** B1 primary confirmation requires all of: (1) paired false-rejection risk difference (B1-B0) < 0; (2) paired valid supported coverage increases (B1 > B0); (3) zero claim-integrity violations for B1 (all claim statuses within {supported_conditional, undetermined, contradicted}; no supported_invariant); (4) the detection non-inferiority rule below holds. The evaluator numeric primary_result checks (1) and (4); (2) and (3) are mandatory pre-declared guardrails reported as secondary metrics and must both hold for confirmation.

**Detection non-inferiority rule:** Paired acceleration discrepancy-detected risk difference (B1-B0) >= -0.10 (detection_loss_bound), under undecided_policy=not_detected: an undetermined acceleration trial is not counted as detected. The alternative excluded-policy analysis is a reported sensitivity, not the primary rule.

**Numeric evaluation (frozen evaluator):** primary metric = `supported_coverage`; paired supported-coverage risk difference B1−B0 > 0 (point estimate) and paired acceleration `discrepancy_detected` risk difference ≥ −0.10 under `undecided_policy=not_detected`; the evaluator's `primary_result` implements these two criteria. The final confirmation rule in the manifest additionally requires the 95% paired Wald interval lower bound > 0, a non-worsening false-rejection point estimate, and zero claim-integrity violations; the evaluator reports these components and the Lead applies the final rule on the single run.

**Undecided policy:** `not_detected` — undetermined is neither acceptance nor detection; the excluded-policy analysis is reported only as sensitivity. The known development pattern (9/36 acceleration trials undetermined because the frozen distribution test returns `insufficient_evidence`) is carried as undecided, not detection loss.

## Hash list (abridged; complete list in the JSON)

| item | sha256 / digest |
|---|---|
| `python/phaino_acoustics/repair_candidates.py` | `3803b0e5f3ee415d1b8fa30c264967d22cceb96d6dec0768d75a8cd1582cd5ff` |
| `python/phaino_acoustics/experiment_repair.py` | `3d51004c7c37bfb2fba18d7d09c25018f369bf6237a96db2b565d341f611c2ca` |
| `python/tests/test_repair_candidates.py` | `ec10f76ef1f8b13506da2a2cf34d80229a1a76e1a3e36775938963ee8ee25f22` |
| `python/phaino_acoustics/repair_selfcheck.py` | `195cc4ee4ef9a000edfba9d95548a91028151250791d6ead24a8eed71c6baf96` |
| `python/phaino_acoustics/adequacy_protocol.py` | `c5c0427207436ae8c3a4562ab71d7f92ff4f61f8db6eaec77bf0980b55ea6b17` |
| `python/phaino_acoustics/measurement_model.py` | `6c52d9b2c9ccbca52db72f2b2d56609881650e9db95ad1d596db5d2e2b6e471c` |
| `protocols/pr4e-claims-1.3.0.json` | `16c62ca63577668b4dfb45f542db97214d1275a2b0dcd95c3e23734871dcbfa6` |
| evaluator package digest | `b8ffb2459adcaf6bf1f480c48da35459bedc8fad38a69ace51447505aeb968d5` |
| execution runner program | `1afec8c2e8acd7571bc53127d29d6e961edaa6a52fb7e6a0e1755302468a192c` |
| development artifact provenance (`/tmp/c2-repair-final/c2-repair.json`) | `b32d91f8f5b787f73d261e65633e0d537e4d2154009905b272a5f7015a9c9dcd` |
| development summary digest | `c70037a04d65b4c55909fc07f94580cb9fa9709606cf1c49059e74da960d40b5` |
| selfcheck artifact hash | `9cc967681259454b96c48a6f9afe3eed948b8330905e2112e593b666910b7225` |
| selfcheck verdict digest | `77c5ff5752a1f8c997e599c8d97c868dae9b07af2e1d33e9aa165806b1fcef2a` |
| calibration sample-definition digest | `e0cf48f4bdf6aa2f89cbaf748fbb981623cb3cf5c5805a71498066a03d854c85` |
| manifest canonical digest | `23ad3dd10a3940336f6bbb880ec45b3be8226c990770ada9f2465193dd89f8ca` |

## Sealed-grid non-use evidence

- the sealed grid file was not opened, parsed or hashed in stage 1; only the accepted declared id/digest/trial-count/seed-base from ADR 0020/0022, the C2 measurement-model report and the Lead message are recorded;
- static grep checks over `repair_candidates.py`, `experiment_repair.py` and `repair_selfcheck.py` find no `c2c-grid`/`c2_grid` reference and no `60_000_000` seed; the existing source-scan test `test_development_run_does_not_open_or_import_the_sealed_grid` passes;
- candidate/development seed bases are 90M / 91M / 92M; the sealed base 60M appears only as declared metadata;
- the frozen runner verifies the grid id/definition digest/trial count against the declared values before the single run, then records the artifact hash and a run record.

## Development provenance and disclosure

- final frozen development artifact: `/tmp/c2-repair-final/c2-repair.json` sha256 `b32d91f8f5b787f73d261e65633e0d537e4d2154009905b272a5f7015a9c9dcd`, protocol digest `1f80b7a42b559bb56f9416e2f5a519add9f8a0faaa018e052d4ca4ea96cccd97`, development grid digest `b0e381fa0458b92a0669705a1bf9f3e7d93acaf68b82f55770f97cd5f94f1dbe`;
- development summary digest `c70037a04d65b4c55909fc07f94580cb9fa9709606cf1c49059e74da960d40b5` is identical before and after the stage-1 metadata/plumbing update;
- during stage-1 preparation the evaluator artifact contract gained required `primary_endpoint`, `undecided_policy`, reporting bins and trial-level runtime observables; the artifact producer was updated to emit them. No candidate decision logic, threshold rule, calibration sample or truth tolerance changed. The development report still cites the pre-update artifact sha (`1392b3d2…`); the Lead should reconcile that report with the frozen hashes above.
- the selfcheck artifact is referenced by hash and verdict digest only: `9cc967681259454b96c48a6f9afe3eed948b8330905e2112e593b666910b7225` / `77c5ff5752a1f8c997e599c8d97c868dae9b07af2e1d33e9aa165806b1fcef2a`. Its time-block-holdout part must be read by the Lead when adjudicating the conditional approval.

## Unfrozen dependencies / honest gaps

- The evaluator package was edited by another workstream during stage-1 preparation (observed mtime/hash changes); this manifest freezes the working-tree state at generation time. If evaluator files change before the Lead commits, the manifest must be regenerated and re-frozen.
- The sealed grid file itself was not opened or hashed in stage 1 (sealing); only the accepted declared grid digest/count/seed base are recorded. The frozen runner verifies them against the file exactly once at run.
- ADR 0023 B selfcheck exists and is referenced by digest; its time-block-holdout finding must be adjudicated by the Lead as part of the conditional approval. This manifest does not convert that development finding into acceptance.
- B3's SNR conditioning branch is unverified: the calibration sample has zero admissible trials in the low estimated-SNR reporting bin, so the artifact declares that branch unexercised (ADR 0023 C).
- The C2-M2 M3 error model has no separate semantic version field; its acceptance-contract version/digest is declared in the C2-M2 report and not recomputed here. It is not used by B0-B3.
- Cross-platform reproducibility of repair artifacts is not frozen or claimed; only environment_id is recorded per artifact.
- No repository commit hash is available (git operations were not performed); authority documents are frozen by working-tree sha256 instead of a commit id.
- The development report (`docs/experiments/2026-11-05-c2-repair-dev.md`) still cites the pre-metadata-update artifact sha; docs were not edited in stage 1 (reconciliation listed above).
- The sealed runner is an inline program frozen by hash rather than a committed file; if the Lead prefers a file, this manifest must be revised.
- Development-derived B2/B3 calibration reference floats are environment-dependent; the sealed run recomputes calibration from the frozen sample and any difference is reported, not retuned.

## Execution discipline

- one sealed run per frozen manifest/candidate set; the runner refuses an existing sealed artifact;
- execution failure (hash/digest/contract/candidate exception) invalidates the run and requires a new revision protocol; the first record is kept;
- a valid artifact that misses the pre-registered primary rule is a scientific negative result, published in full and not retried;
- cross-environment execution is a separate reproducibility dimension, not a second confirmation.

## Stage-1 verification performed (no grid opened)

- manifest digest recomputed from the file: match;
- frozen runner preflight (`--verify-only`) run through the manifest program: exit 0, 26 dependency hashes and all frozen digests verified, grid not opened;
- sealed grid file: not opened.

**Next step (Lead):** commit `protocols/c2c-freeze-v1.json` (and this rationale), then message the method side to execute the frozen runner exactly once.
