# E1-0 synthetic fault injection — field-degradation rehearsal

**Status:** deterministic harness implemented and tested on the E0 Doppler pipeline · 2026-11-05 · **Gate:** [E1-0 instrument feasibility](E1-0-instrument-feasibility.md) · **Bundle gate:** [E1-0 raw bundle](E1-0-raw-bundle-schema.md)

The first field campaign is expensive. This harness rehearses common instrument and environment failures **before** real data exists. It is a synthetic stress test, not evidence about a specific recorder.

## 1. Faults

| Fault | Injection | Acceptance |
|---|---|---|
| Recorder clock | `clock_scale_ppm = ±50` in the E0 generator | must not become false support; parameter bias stays small |
| ADC clipping | clip waveform at 10 % of peak | must inflate residual scale or abstain/reject |
| Dropped buffers | zero three 0.5 s windows | residual scale must inflate; no false support |
| Wind burst | additive Gaussian burst (2 s, amplitude 2.0) | no false support; abstain/reject allowed |
| Missing reference | `reference_missing` | explicit `reference_channel_missing` abstention, no fit |
| Low-SNR reference | `reference_snr_db = −3` | explicit `reference_channel_snr_below_floor` abstention |

## 2. Pipeline and decision rule

`python/phaino_acoustics/fault_injection.py`:

1. generate a deterministic `Scenario` (seed-controlled);
2. apply waveform faults (clock ppm is applied to the scenario);
3. extract the IF track through the normal front end;
4. run `fit_hardened` + `evaluate_adequacy` (truth is **evaluation-only**);
5. report decision, adequacy status, reason codes, residual scale, fitted parameters and relative errors.

A clear support under a severe fault is a **false convergence** and fails the rehearsal. A benign clock ppm may remain `undetermined` because the E0 model has the documented clock-equivalence degeneracy; it must not become a false rejection.

## 3. Run the auditable suite

```
make e1-fault
# or through the CLI:
cargo run -q -p phaino-cli -- e1-fault --repo-root . --out artifacts/e1-fault.json
# or directly:
PYTHONPATH=python python3 -m phaino_acoustics.fault_injection --out artifacts/e1-fault.json
```

The JSON report contains the seed, per-fault decision/adequacy/residual scale, and an `ok` verdict. It exits 1 if any severe fault is falsely supported, the dropout residual scale does not inflate by 10x, or a reference fault fails to abstain. `artifacts/` is git-ignored: it is a local dry-run artifact, not an E1 result.

## 4. Observed acceptance (deterministic tests)

`python/tests/test_fault_injection.py` (7 tests):

- baseline and ±50 ppm: not false-supported; velocity error < 2 %;
- 10 % clipping: `undetermined`/`rejected`, residual scale inflated vs baseline;
- dropped buffers: residual scale > 10× baseline;
- wind burst: no false support;
- reference loss/low SNR: explicit abstention reason, no fit;
- default suite deterministic under fixed seed.

These are assertions on a synthetic fixture, not a population estimate. The reference-channel faults are gated before fitting; they test the gate, not a physical receiver.

## 5. Limits / next

- Waveform faults are simplified: no ADC transfer curve, no packet-loss model, no wind spectral shaping, no real PPS receiver.
- The harness does not yet emit a signed E1-0 artifact or run in the fabric; that integration is next.
- E1 collection remains gated on the physical instrument and authorization checks.
