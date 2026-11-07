# E1-0 bench validation — instrument error budget before any field collection

**Status:** protocol and analysis harness ready; **no bench data collected yet** · 2026-11-05 · **Authority:** [ADR 0025](../decisions/0025-e1-scope-and-scale-audit.md) · **Related:** [E1-0 gate](E1-0-instrument-feasibility.md)

Bench data are instrument evidence, not E1 field evidence. A bench session cannot be cited as validation of real-motion inference.

## 1. Test matrix

| Test | Method | Deliverable |
|---|---|---|
| Static frequency accuracy | calibrated reference source at 500 Hz with small known offsets (e.g. 0, 1, 2.9, 5.8 Hz) | bias, variance, 95% interval |
| Window sensitivity | same capture analysed at 512/1024/2048/4096 points | bias/variance/time-lag trade-off table |
| Clock stability | long recording with independent reference timestamps | α̂, β̂, σα, σβ, residual RMS; comparison with two-anchor prediction |
| Signal-chain stability | direct cable vs speaker–microphone path for the same tone | playback vs acquisition bias/latency difference |
| Downstream decision | feed measured errors into the existing adequacy/claim verifier | whether the measured error could flip a supported/undetermined decision |

## 2. Metadata required per session

- device: recorder, microphone, speaker, cable path, gains, filters;
- settings: sample rate, bit depth, frame lengths, window, interpolation method;
- environment: room, temperature, background noise, reverberation estimate;
- reference: calibrated source/clock/motion reference and its uncertainty;
- `measurement_model_id` and version;
- raw waveform path + SHA-256 for every capture;
- **calibration vs evaluation split**: captures used to calibrate (bias, latency, thresholds) must be disjoint from captures used to evaluate them;
- protocol version (`e1-0-bench-1.0.0`).

The harness (`python/phaino_bench`) validates the split, rejects duplicate captures and role/split mismatches, and computes the metrics. It does not substitute for the actual measurement.

## 3. Acceptance framing (not yet a result)

- frequency bias and variance must be reported **relative to the expected few-Hz Doppler shift**, not only in absolute Hz;
- window choice is a trade-off: a longer window reduces bin width but increases smoothing/latency under chirp, so bias, variance and time lag must be reported together;
- clock: |α̂ − α_ref| ≤ 1e-5 and a β error interval against a defined reference origin; per-claim binding (absolute-time claims are withheld if the budget cannot support them);
- signal-chain: separate playback error from acquisition error;
- downstream: report the fraction of decisions that would flip if the measured error were injected, not just the raw frequency error.

## 4. What this does not establish

Bench accuracy on a stationary calibration source does not establish performance on a moving source, in a reverberant room, with a real clock and independent motion truth. Those are E1-A/B/C. Field collection remains gated on venue authorization, consent, jurisdiction/legal review, clock calibration and independent reference truth.

## 5. Data handling

Raw bench waveforms are not committed to the repository. The session manifest, digests, settings and result summaries are archived in the evidence store; calibration and evaluation captures are stored and reported separately.
