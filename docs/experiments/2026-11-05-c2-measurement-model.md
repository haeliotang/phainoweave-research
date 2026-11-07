# C2 measurement-model characterisation — extraction-error model, noise-matched paths, frozen repair grid

**Status:** C2-A/B/C complete; the empirical error model is **insufficient** to explain all high-chirp rejections; B0–B3 repair runs not started · 2026-11-05 · **Authority:** [ADR 0020](../decisions/0020-measurement-model-and-c2-repair.md) · **Plan:** [C2 repair plan](pr4e-c2-repair-plan.md)

**Measurement model under test:** `e0-frontend-hann-stft-512-256` v1.0.0 — STFT frame 512, hop 256, 180–2800 Hz band, Hann window, log-magnitude parabolic interpolation. This is now an explicit, versioned object in the evidence chain, not a preprocessing detail.

## 1. C2-A — what the extraction error actually looks like

Design: 66 cells = 11 log-spaced closest approaches (120–8000 m) × speeds {60, 150, 250} m/s × SNR {5, 20} dB, N=3 fixed seeds (base 70,000,000), plus a 9-cell window sweep. `e(t) = f̂(t) − f_true(t)`.

**A simple chirp-rate bias does not exist.** Pooled `E[e | chirp rate]` is essentially zero across bins from 0.5 to 3000 Hz/s (|mean| ≤ 0.03 Hz; correlation(e, |ḟ|) = 0.009; OLS R² = 0.0075). Reporting only RMS would have hidden this, and reporting only the mean would have wrongly exonerated the front end.

The structure is elsewhere:

| Property | Measured |
|---|---|
| Deterministic (seed-averaged) share of error variance | **0.639** (median) |
| Time-position dependence | median max time-bin bias 0.198 Hz; median profile range 0.307 Hz |
| Residual autocorrelation | ACF lag1 median 0.090; median integral correlation time 0.055 s |
| Heteroscedasticity | max/min time-bin std median 1.44 |
| ACF by chirp bin | ranges from −0.36 to +0.15 — chirp-dependent correlation, not a single chirp-rate function |
| SNR effect | RMS ≈ 0.44 Hz at 5 dB vs 0.13–0.23 Hz at 20 dB; bias similar → low SNR is noise-dominated, the 20 dB structure is interpolation bias |
| Analysis-window effect | frame 256: RMS 0.40–0.45 Hz; 512: 0.15–0.19 Hz; 1024: 0.085–0.11 Hz; bias changes sign/magnitude |

**Verdict C2-A:** the front end introduces a real deterministic structural error whose shape depends on time position/frame phase and analysis window, with chirp-dependent residual correlation. It is **not** well modelled as `E[e|ḟ]`; a chirp-rate-only error model would be scientifically wrong. The empirical generator (per-cell 10-bin bias profile + measured residual template) is stored per cell with fixed seeds for C2-B.

## 2. C2-B — which observation source reproduces the rejections?

Same scenario/seed per trial, 5 geometries (four C2-A cells + held-out 150 m), v=250 m/s, 20 dB, N=20 per cell (100 per source).

| Observation source | False rejections | insuff. evidence | median Ljung–Box | median σ_f |
|---|---:|---:|---:|---:|
| ideal generated frequency | 0/100 | 100 | n/a (near-noiseless) | ~1e-13 |
| ideal + white noise (matched RMS) | 0/100 | 0 | ~120 | 0.20 |
| ideal + empirical error structure | **68/100** | 4 | ~5.5e3 | 0.22 |
| full waveform extraction | **100/100** | 0 | ~1.5e4 | 0.20 |

Independent white noise reproduces **none** of the excess rejections. The empirical bias+template model reproduces 68% overall, but per-geometry reproduction ranges from **0.10 to 1.00**, and the held-out geometry is 0.60. The simple empirical error model is therefore **insufficient**: a geometry-dependent and/or longer-memory structure is missing. The near-noiseless ideal path returns `insufficient_evidence` 100/100, as expected and accepted; no artificial noise was added.

**Verdict C2-B:** the rejections are caused by the measurement model's *structured* error, not by independent measurement noise; but the current error characterisation does not yet fully reproduce it. This is a negative result that must be resolved before a repair route is chosen: otherwise B1/B2/B3 would be tuned against an incomplete error model.

## 3. C2-C — frozen repair grid (defined, not run)

- Grid id `pr4e-c2c-v1` v1.0.0, **digest `cb8d869d85f41743d3cbaecf0214892d60ae24e1ac1ced5bee15891bff8cd431`**, seed base 60,000,000 (new, disjoint from E0/PR-4d/C1/C2), 59 conditions, **566 trials**.
- Geometry continuum: 120, 180, 270, 400, 600, 900, 1400, 2100, 3200, 4800, 7000 m × speeds {60, 150, 250} m/s; SNR {5, 10, 20} dB; acceleration levels {0.15, 0.30, 0.50} m/s² (new).
- Strata: correct-CV continuum 330, correct-CV low-SNR 96, acceleration misspecification 120, noise-only null 20.
- Paired design: B0–B3 on the same `(condition, trial, seed)`; candidates evaluated independently, no combination. B3 allowed selection inputs: `estimated_chirp_rate`, `signal_quality`, `fit_uncertainty`, `estimated_snr`; true `b`, true speed/acceleration, scenario labels and within-tolerance flags are forbidden (`selection_inputs_runtime_only: true`).
- The grid digest covers the grid definition only (no results, environment or timestamps). The 1840 attribution trials are not reused.

## 4. What this means for the repair step

1. **Do not start B1/B2/B3 yet.** The measurement-model error is only partially characterised (68% overall, 10–100% per geometry). A repair tuned against an incomplete error model risks "fixing" a geometry-specific artefact rather than the mechanism.
2. **Next C2-A iteration:** extend the empirical model with geometry-dependent and longer-memory structure (e.g. 2-D bias over chirp × time-position/frame phase, chirp-conditioned residual covariance with correlation time), or show that template resampling is the wrong uncertainty representation. Acceptance: reproduction of the extracted false-rejection rate across the held-out geometry set with intervals, without changing adequacy thresholds.
3. **Then** run B0–B3 paired on `pr4e-c2c-v1` with the independent paired evaluator (already implemented, 21 tests; it reports paired risk differences with intervals, detection loss, retention, abstention-gaming, claim integrity, cross-environment agreement).
4. If the extended error model still cannot reproduce the rejections, the pre-defined negative result applies: the frequency representation or residual framework is insufficient; the answer is a new observation representation, not a threshold adjustment.

## 5. Limitations

- One front end (STFT/Hann/parabolic interpolation); no alternative extractor was compared.
- The front end exposes analysis-frame length, not observation-duration windows; the window sweep is frame length only.
- Truth instantaneous frequency is synthetic-only and carries a declared noise floor; near-noiseless cases are numerically degenerate.
- C2-B uses 5 geometries; the reproduction fraction is an estimate, not a universal law.
- The empirical generator embeds residual templates by cell (artifact 6.8 MB); reproducibility depends on the stored seeds and templates, not on re-running the front end identically.

## 6. Provenance

Artifacts: `/tmp/c2a/error_model.json` (records `3df926ca…`), `/tmp/c2a/error_model.md` (`71332e97…`), `/tmp/c2a/noise_matched.json` (records `c20b5a1c…`), `/tmp/c2a/noise_matched.md` (`82b6bfcb…`), `/tmp/c2c-grid.json` (sha `5bec5ef1…`, grid digest `cb8d869d…`). Code: `python/phaino_acoustics/measurement_model.py`, `c2_grid.py`, `experiment_c2a.py`; tests `test_measurement_model.py` (9), `test_c2_grid.py` (9). Adequacy thresholds unchanged (test asserts the protocol constant).
