# E1-0 dry-run readiness — code-side checklist before the field campaign

**Status:** synthetic readiness only; **no bench data collected**, E1 remains gated · 2026-11-06 · **Gate:** [E1-0 instrument feasibility](E1-0-instrument-feasibility.md) · **Procurement:** [E1-0 package](E1-0-procurement-and-authorization.md)

This is a consolidation report for the code work done while the physical E1-0 gates are open. It is not an E1 result, does not authorize collection, and contains no real measurement.

## 1. What is now executable

| Item | Command | Evidence |
|---|---|---|
| Raw bundle schema/gate | `phaino fabric e1-bundle --bundle …`; `register-e1` | missing references/calibration/site/consent/SNR<10 dB refused before snapshot |
| Library auto-gate | `Fabric::register` with an E1 manifest | refuses E1 bundles before writing snapshot bytes |
| Fault rehearsal | `make e1-fault` / `phaino e1-fault` | JSON with decision, adequacy, residual σ, abstention; exit 2 on acceptance failure |
| Atmospheric uncertainty | `python/phaino_acoustics/atmosphere.py` | c(T,RH,wind) → Doppler interval; planning bound only |
| Refusal audit | `phaino audit-check`, `audit-list`, `audit-verify` | durable sequence, input snapshot digest, append-only chain check |
| Policy digest | E0 replay + store `inference_run.parameters` | `659c438a…` |
| Cockpit | `apps/desktop` Governance / E1 views | policy, audit rows (Tauri read-only), synthetic residual diagnostics |
| R1-D evidence | `make r1d-compare` | arm64 pair R1-N+R1-D; amd64 pair R1-N only; R2 fails |
| OS boundary | `scripts/sandboxed_e0.sh` | read-only root/repo, no network, only output writable; explicit harness, not default CLI |
| End-to-end fixture | `make e1-e2e` | bundle→snapshot/store→refusal audit→read-back; CI job configured |

## 2. Measured synthetic outputs (not E1)

- Fault suite: `ok=true`, no false support under severe synthetic faults; dropout residual σ ≈ 98.92 Hz, baseline ≈ 0.189 Hz; reference loss abstains before fit.
- Atmospheric planning example: 20 °C / 50 % RH / 3 m/s along-path wind, 500 Hz, 50 m/s radial → c_eff 347.04 m/s, f_pred 584.164 Hz, 1.96σ_f 0.167 Hz.
- E0 replay on host remains exact `674213d9…`.
- Container R1-D: arm64 passes R1-N+R1-D, amd64 fails R1-D on `null_noise_only.converged_rate` 0.09→0.08 (trial 2456).

## 3. Still physically gated

E1 collection requires evidence for all of:

- independent frequency reference with traceable calibration;
- independent time reference (PPS/GPS or approved anchor) and clock budget;
- authorized site, consent, jurisdiction/legal review, privacy review;
- realized signal quality (SNR, distortion, reverberation);
- frozen protocol and instrument error budget.

The raw-bundle gate refuses a bundle that lacks the declared metadata, but it cannot verify that a certificate is genuine or that the site authorization is valid.

## 4. Still open on the code side

- amd64 trial 2456 stall classification (or an explicit target-scope decision);
- OS-level filesystem sandbox around the Python invocation (currently timeout/CPU/AS/output budgets, not file isolation);
- a real E1 store end-to-end cockpit demonstration (current audit demo uses a synthetic governance store);
- CI cross-environment verification once the GitHub Billing block is lifted.

## 5. Verification at this snapshot

- 116 Rust tests, 448 Python tests, 657 relative doc links;
- `cargo fmt --check`, `clippy -D warnings` clean;
- host `make e0` exact; sealed archive `641a1003…` unchanged;
- 53 working-tree changes are **uncommitted** at this snapshot; CI has not run since `183087e` because of the billing block.
