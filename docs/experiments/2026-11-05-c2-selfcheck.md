# C2-C pre-seal self-check — B1 self-confirmation diagnostics, outcome taxonomy, B3 power

**Status:** development diagnostics complete; time-block self-confirmation **flagged** for B1; sealed run not yet executed · 2026-11-05 · **Authority:** [ADR 0023](../decisions/0023-three-operations-and-sealed-protocol.md) · **Sealed manifest:** `protocols/c2c-freeze-v1.json` (`23ad3dd1…`)

This report is the mandatory pre-seal review. It uses the development grid only (seeds ≥92M); the sealed `pr4e-c2c-v1` grid was neither opened nor read.

## 1. B1 wrong-model de-chirp: no self-confirmation, but detection is model-dependent

Correct-CV high-chirp trials (32), predictions deliberately wrong:

| Prediction model | Decisions | Median residual RMS | Median ACF1 | Rejections |
|---|---|---:|---:|---:|
| B0 (no de-chirp) | accept 1 / reject 24 / undetermined 7 | 0.1504 Hz | 0.612 | 24/32 |
| B1 · correct model | accept 32 | 0.0789 Hz | −0.299 | 0/32 |
| B1 · speed +20% | **undetermined 32** | **163.9 Hz** (2080×) | 0.051 | 0/32 |
| B1 · closest approach +30% | **reject 32** | 0.1536 Hz | 0.671 | 32/32 |

No wrong model combines low residuals with removed rejections: the speed-biased de-chirp destroys the track (all abstain) and the geometry-biased one rejects everything. **Wrong-model self-confirmation is not flagged.** However, on acceleration trials a wrong speed model loses 25 pp detection (36/48 → 24/48, 24 undetermined), so B1 detection is prediction-model dependent.

## 2. Time-block holdout: **self-confirmation flagged**

De-chirp parameters estimated on the first 60% of the window; residuals compared on used vs held-out blocks:

| Quantity | Used block | Held-out block |
|---|---:|---:|
| B0 residual RMS | 0.1845 Hz | 0.0775 Hz |
| B1 residual RMS | 0.0786 Hz | 0.0790 Hz |
| Improvement vs B0 | **+134.8%** | **−1.9%** |

B1's residual improvement exists in the block that estimated the de-chirp model and does **not** persist out-of-block. This is exactly the ADR 0023 §B.2 warning. It does not invalidate B1 as a candidate, but it qualifies the mechanism: part of B1's apparent adequacy gain is in-sample to its own prediction. The sealed-grid primary endpoint must therefore be judged on held-out trials, and the report must not present B1's development 0/82 as evidence of a general measurement fix.

## 3. Parameter stability vs truth

Paired B1−B0 parameter errors (82 correct-CV trials):

| Parameter | B0 mean error | B1 mean error | B1−B0 [95% CI] | Mean abs B0 | Mean abs B1 |
|---|---:|---:|---|---:|---:|
| v | +7.78e-4 | −7.34e-5 | −8.51e-4 [−1.88e-3, −3.85e-5] | 1.19e-3 | 1.17e-4 |
| b | +1.62e-3 | −1.54e-4 | −1.77e-3 [−4.02e-3, −5.58e-6] | 2.78e-3 | 2.72e-4 |
| t0 (s) | +3.57e-3 | −1.61e-4 | −3.73e-3 [−8.55e-3, +7.74e-5] | 6.68e-3 | 6.08e-4 |
| f0 | −9.93e-5 | +8.30e-6 | +1.08e-4 [+6.05e-5, +1.54e-4] | 1.88e-4 | 1.72e-5 |

B1 does **not** trade parameter correctness for adequacy; accuracy is equal or better, f0 slightly worse but tiny. Window perturbations (40/80 s) show the same direction (v, t0 improve; b neutral; f0 slightly worse).

## 4. Outcome taxonomy (development, never pooled)

| Candidate | Correct supported coverage | False rejection | Abstention | Accel detected | Accel undetermined | Accel false-supported | Null promoted |
|---|---:|---:|---:|---:|---:|---:|---:|
| B0 | 22/82 (0.268; 0.184–0.373) | 55/82 (0.671) | 5/82 (0.061) | 27/36 (0.750) | 9/36 (0.250) | 0/36 | 0/6 |
| B1 | 82/82 (1.000; 0.955–1.000) | 0/82 | 0/82 | 27/36 (0.750) | 9/36 (0.250) | 0/36 | 0/6 |
| B2 | 52/82 (0.634; 0.526–0.730) | 27/82 (0.329) | 3/82 (0.037) | 27/36 (0.750) | 9/36 (0.250) | 0/36 | 0/6 |
| B3 | 77/82 (0.939; 0.865–0.974) | 0/82 | 5/82 (0.061) | 27/36 (0.750) | 9/36 (0.250) | 0/36 | 0/6 |

Wilson 95% intervals; zero-event cells carry exact upper bounds. B1's 82/82 is qualified by §2. Safe abstention (27/36 detected, 9/36 undetermined) is not counted as detection.

## 5. B3 per-chirp-bin power: a hidden family failure

| Chirp bin (Hz/s) | CV n | CV rejection | CV abstention | Accel n | Accel detected | Accel undetermined |
|---|---:|---:|---:|---:|---:|---:|
| 0–50 | 35 | 0/35 | 0/35 | 18 | 18/18 | 0/18 |
| 50–150 | 22 | 0/22 | 1/22 | 9 | 9/9 | 0/9 |
| **150–400** | 14 | 0/14 | 4/14 | 9 | **0/9** | **9/9** |
| ≥400 | 11 | 0/11 | 0/11 | 0 | n/a | n/a |

The aggregate 27/36 hides a **B3 family failure**: at 150–400 Hz/s all 9 acceleration trials abstain, so no mismatch is detected. Estimated SNR saturates at the 60 dB clip (median 57.2 dB, 6 low / 118 high admissible), so **SNR conditioning is unverified** and must be reported as such on the sealed grid.

## 6. Consequence for the sealed run

The pre-seal diagnostics do not veto the sealed run, but they constrain its interpretation:

- B1 remains a **conditional** candidate measurement correction: wrong-model self-confirmation is absent, but time-block self-confirmation is present. The frozen primary endpoint (supported coverage + detection non-inferiority on paired sealed trials, claim integrity) is the confirmation test; the time-block result is a declared caveat.
- B3 is decision calibration; its sealed report must include per-chirp power; its SNR branch is unverified.
- The M3 error model is a separate uncertainty-modelling result, not part of the B0–B3 competition.
- The sealed manifest `23ad3dd1…` freezes candidate code, calibration, evaluator, tolerances, primary endpoint, undecided policy and failure rules; the run is single and no re-run for a better result is permitted.

## 7. Provenance

Self-check artifact `/tmp/c2selfcheck/selfcheck.json` (sha `efde1ce9…`, verdict `77c5ff57…`), dev artifact `/tmp/c2selfcheck/dev-repair/c2-repair.json` (sha `bf2594ab…`, protocol digest `f549bbe8…`). Code: `python/phaino_acoustics/repair_selfcheck.py`, tests `test_repair_selfcheck.py` (6). Sealed grid: `sealed_grid_opened: false`, `sealed_grid_file_read: false`.
