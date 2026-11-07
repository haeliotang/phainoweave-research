# E1-B — leakage-proof out-of-sample de-chirp protocol

**Status:** protocol design; no data collection · 2026-11-05 · **Authority:** [ADR 0025](../decisions/0025-e1-scope-and-scale-audit.md) · **Related:** [E1-0](E1-0-instrument-feasibility.md), [E1 preregistration](2026-11-05-e1-preregistration-draft.md)

B1's C2 self-check showed +134.8% residual improvement in the fitted block and −1.9% on held-out blocks. E1-B's purpose is to test the *prediction*, not the residual aesthetics, and it must close every leakage path, not just explicit re-fitting.

## 1. Fixed partition (pre-registered)

- Block boundaries are fixed before the recording is analysed, from event geometry (e.g. before/after closest approach), not chosen after seeing residuals.
- A **guard band** of at least the larger of two STFT frame lengths (preferably 3–4 frames) separates fit and held-out blocks.
- Any STFT frame whose support intersects the guard band is discarded from both fit and evaluation; no window straddles the boundary.
- The same fixed partition is used for every candidate; no data-driven block selection.

## 2. What is estimated on the fit blocks only

- motion parameters and de-chirp prediction;
- hyperparameters and model-form choices (candidate selection is pre-registered or chosen on separate calibration events);
- signal-quality gating and normalization;
- error-model calibration (if any);
- any threshold used for held-out evaluation.

Held-out blocks may not contribute to any of these. If a quantity cannot be fixed without held-out data, it is declared unavailable.

## 3. Report three distinct analyses

1. **Full-event fit** (in-sample; for reference only).
2. **True out-of-sample**: frozen prediction from fit blocks evaluated on held-out blocks; this is the E1-B primary object.
3. **Re-fit on held-out**: a separate analysis condition, clearly labelled, never substituted for (2).

The report must show the difference between (1) and (2) explicitly; improvement in (1) alone is not evidence of measurement transfer.

## 4. Primary endpoint and failure modes

- Primary: held-out prediction error (frequency and physical-parameter prediction) and adequacy/claim status on held-out blocks, with intervals resampled by independent passes, not frames.
- Secondary: fit-block residual improvement; parameter stability; clock/geometry uncertainty propagation.
- Failure modes to report: no held-out improvement despite fit improvement (leakage or self-confirmation); held-out improvement without physical-parameter improvement; model selection instability; partition sensitivity (report at least one pre-registered alternative partition as a robustness check, not to choose a winner).

## 5. Prohibited

- Re-estimating the de-chirp/motion parameters after inspecting held-out errors and then calling it out-of-sample.
- Using held-out statistics for quality gating, normalization, threshold calibration or model choice.
- Splicing frames across the boundary, or treating correlated frames as independent units.
