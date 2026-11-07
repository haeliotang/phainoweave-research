# E1-0 — Instrument and scale feasibility gate

**Status:** design review prepared; **no data collection authorized** · 2026-11-05 · **Authority:** [ADR 0025](../decisions/0025-e1-scope-and-scale-audit.md) · **Related:** [E1 scale audit](E1-scale-audit.md), [E1 preregistration](2026-11-05-e1-preregistration-draft.md)

E1 must first answer whether the existing measurement model can resolve the frequency changes a **safe** controlled pass produces. A synthetic band that cannot be measured safely is not a field target.

## 1. Expected Doppler shift at safe speeds

`Δf ≈ f0·v/c` (low Mach), f0 = 500 Hz, c = 343 m/s:

| v (m/s) | Δf (Hz) |
|---:|---:|
| 1 | 1.46 |
| 2 | 2.92 |
| 3 | 4.37 |
| 5 | 7.29 |

This is a **frequency shift of a few Hz**, not the large chirps used in C2. It is a different measurement regime, not a smaller copy of the same one.

## 2. Frequency resolution of the current front end

STFT bin width `fs/N` at fs = 8000 Hz:

| Frame N | Bin width (Hz) | Δf=2.92 Hz in bins | Δf=7.29 Hz in bins |
|---:|---:|---:|---:|
| 512 | 15.625 | 0.19 | 0.47 |
| 1024 | 7.813 | 0.37 | 0.93 |
| 2048 | 3.906 | 0.75 | 1.87 |
| 4096 | 1.953 | 1.50 | 3.73 |

A bin width is the **spectral sampling interval**, not a hard lower bound on frequency-estimate error: at high SNR, sub-bin interpolation can be more precise. But a longer window also reduces time resolution and smooths/biases a changing frequency. The bench test must therefore report **bias, variance, time lag and downstream decision impact** for at least two frame lengths (512/1024/2048/4096), not merely ask whether 2.9 Hz is "resolvable". The C2-A measured bias (±0.23 Hz, bin-offset dependent) is of the same order as Δf at 1–2 m/s, so a 512-point frame must not be assumed adequate.

## 3. E1-0 acceptance checks (must be answered before collection)

| Check | Question | Evidence required | Status |
|---|---|---|---|
| Frequency resolution | can the chosen frame/estimator resolve the expected Δf with bias and variance small relative to Δf? | bench test with a calibrated source at the expected shift; bias/RMS vs known frequency | **open** |
| Clock calibration | can two independent anchors (or rate calibration + absolute anchor) constrain α,β to the required uncertainty? | measured α,β and their intervals; which equivalence relations the anchors break | **open** |
| Reference truth | how are motion, emission frequency and recorder clock independently measured? | instrument list, calibration certificates, uncertainty budget | **open** |
| Geometry coverage | which (v, b) ranges are safe and can be measured? | site risk assessment; covered Δf and chirp interval | **open** |
| Signal quality | what is the minimum usable SNR and the recorder distortion? | bench/field SNR, THD/IMD, reverberation estimate | **open** |

**Clock requirement is a measurement-error budget, not a nominal tolerance.** Compare the estimate with an independent reference: `|α̂ − α_ref| ≤ 1e-5`, and a `β` error interval against an explicitly defined reference time origin. Two independent anchors each with σ_t ≈ 1 ms separated by ΔT = 150 s give a simple-model rate uncertainty `σ_α ≈ √2·σ_t/ΔT ≈ 9.4e-6` — close to the requirement, but not a high-confidence guarantee. The requirement is **bound to specific claims**: if the budget cannot support absolute time, the run may evaluate measurement error and conditional claims but must not support absolute-time conclusions. A single synchronization event is not a rate calibration.

Bench protocol and analysis harness: [E1-0 bench validation](E1-0-bench-validation.md). Bench data are instrument evidence, not E1 field evidence.

## 4. Safety and site

- 5 m/s at 0.5 m closest approach (~73 Hz/s) is **not** an indoor-safe setup; permitted speed and minimum distance are set by the site risk assessment, not by the synthetic target.
- E1 does not need to cover C2's 150–400 Hz/s band. If safe conditions cannot produce it, that band stays declared uncovered.
- Same chirp rate does not imply the same trajectory, noise, reverberation or propagation; E1 conclusions apply only to the actually observed regime.

## 5. Gate outcome

Collection may start only after **all** E1-0 checks have evidence, plus venue authorization, consent, jurisdiction/legal review and a frozen protocol. Until then, preparation is non-collection only (bench tests, calibration, paperwork). Raw capture bundles are validated by the [E1-0 bundle gate](E1-0-raw-bundle-schema.md) before any snapshot is created.
