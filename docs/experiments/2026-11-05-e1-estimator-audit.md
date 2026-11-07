# E1 estimator-independence audit

**Status:** correct-CV conclusions robust to estimator choice; acceleration **detection** is estimator-sensitive at b=1400 m · 2026-11-05 · **Scope:** synthetic audit set (36 trials), no sealed-grid use · **Related:** [E1-0](E1-0-instrument-feasibility.md), [E1-B leakage](E1-B-leakage-protocol.md)

## 1. Question

The C2/C1 conclusions were produced with `fit_hardened`. Before E1, we need to know whether the results depend on that estimator. A second, independent implementation was built with `scipy.optimize.least_squares` (`trf`, `soft_l1`, direct physical-units parameters, own forward model/residuals, finite-difference covariance). `fit_hardened` was used only as the comparison baseline.

Audit set: seed base 100,000,000; 36 trials — 8 correct-CV conditions (geometry {600, 1400} m × speed {60, 250} m/s × SNR {10, 20} dB × 3) and 4 acceleration conditions (geometry {600, 1400} m × accel {0.15, 0.30} m/s², v=250 m/s, SNR 20 dB × 3). Pre-declared agreement bounds: f0/v/b 0.5%, t0 0.05 s.

## 2. Results

**Correct-CV (24 trials): parameters and tolerances agree.**

- Maximum estimator difference: f0 5.87e-5, v 4.70e-4, t0 0.00483 s, b 0.00119 — all within the pre-declared bounds.
- Both estimators pass all four frozen E0 tolerances on all 24 correct-CV trials; zero tolerance/classification disagreements.
- Zero adequacy-status and zero claim-status flips.
- Paired mean differences over all 36 trials: f0 −8.5e-4 [−1.3e-3, −4.0e-4], v +6.35e-4 [+2.9e-4, +9.8e-4], t0 +0.0097 s [+0.0044, +0.0146], b +0.00464 [+0.0022, +0.0073] (95% bootstrap, trial-level).

**Acceleration (12 trials): parameters fail tolerance under both estimators, but detection flips.**

- Both estimators fail all four E0 tolerances on all 12 acceleration trials (expected: constant-velocity model is misspecified).
- **6/12 adequacy-status flips**, all at b=1400 m: baseline returns `discrepancy` (detects mismatch), the independent estimator returns `insufficient_evidence` (a=0.15) or `indeterminate` (a=0.30). Six epistemic decisions follow the same trials.
- At b=600 m no flips.
- **0 claim-status flips** over 36 trials under the frozen claims gate.

## 3. Verdict

`correct_cv_estimator_independent_acceleration_detection_estimator_sensitive`

- The correct-CV parameter/claim conclusions are **not** artefacts of `fit_hardened` in this audit.
- Acceleration **detection vs safe abstention** is estimator-dependent, even though both estimators agree the parameters are outside tolerance. This is not a claim of "detector failure"; it is a warning that a detection claim from a single estimator is not robust evidence.

## 4. Consequences for E1

1. E1 must not present acceleration/mismatch detection from one estimator as the result. Either report detection across at least two estimators, or require an estimator-robust decision rule (e.g. both must agree) and label abstention separately.
2. Correct-CV claim-level conclusions can be reported with a single estimator only if the second estimator agrees within pre-declared bounds; otherwise report both.
3. The estimator audit is implementation-level, not physics-level: both estimators fit the same declared model. It does not validate the model or the measurement chain.
4. No change to frozen E0/PR-4d/C1/C2 decisions; sealed grid untouched.

## 5. Limitations

- Small fixed-seed synthetic audit set (36 trials); robust `soft_l1` and finite-difference SEs differ from the hardened LM.
- No acceleration-detection audit at other geometries/SNRs; the flip is localized to b=1400 m in this set.
- Same declared physical model; a model-form error would affect both estimators and is outside this audit.
- Single environment.

## 6. Provenance

Artifacts `/tmp/e1est/estimator-audit.json` sha256 `90bca559…`, `estimator-audit.md` sha256 `117a5527…`. Code `python/phaino_acoustics/audit_estimator.py`, tests `test_audit_estimator.py` (6). Artifact declares `sealed_grid_opened: false`, `thresholds_changed: false`.
