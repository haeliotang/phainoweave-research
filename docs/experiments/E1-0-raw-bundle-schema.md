# E1-0 raw capture bundle — schema and ingestion gate

**Status:** Python validator, Rust library gate (`Fabric::register_e1`), automatic schema-marker gate in `Fabric::register`, `phaino fabric e1-bundle` and `phaino fabric register-e1` implemented and tested · 2026-11-05 · **Gate:** [E1-0 instrument feasibility](E1-0-instrument-feasibility.md) · **Procurement:** [E1-0 package](E1-0-procurement-and-authorization.md)

The first real recording must not reach analysis with a missing time reference, calibration certificate or site authorization. This gate validates the **raw capture bundle** before any snapshot is created.

## 1. Bundle layout

```
<bundle>/
  bundle.json
  audio/<take>.wav
  ref/frequency.<ext>      # calibrated reference tone/track
  ref/time.<ext>           # PPS/GPS or independent time-anchor record
  ref/motion.<ext>         # independent motion truth
```

`bundle.json` (schema `e1-0-bundle-1.0.0`) requires:

| Field | Requirement |
|---|---|
| `bundle_id` | `e1b_<16 lowercase hex>` |
| `measurement_model_id` | versioned front-end id |
| `audio[]` | non-empty; `path`, SHA-256, sample rate, channels, duration |
| `references.reference_snr_db` | numeric ≥ 10 dB; a low-SNR reference is refused before analysis |
| `references.frequency` | file digest + calibration certificate (`id`, `issued_by`, `uncertainty_hz`, `valid_until`) |
| `references.time` | `kind ∈ {pps, gps, audio_anchor}`, file digest, uncertainty |
| `references.motion` | file digest, uncertainty |
| `authorization` | `site_id`, `jurisdiction`, `legal_review_id`, `consent_sha256` |
| `environment` | temperature, humidity 0–100, wind, sound speed |
| `operator` | id and role |

## 2. What the gate refuses

- missing or placeholder fields (`TBD`, `unknown`, empty);
- non-64-hex digests or digest mismatches;
- missing files, absolute paths, `..` escapes, duplicate audio paths;
- consent/authorization placeholders;
- reference SNR below 10 dB;
- malformed calibration certificate or time-reference kind.

A rejection is a typed error list; the bundle is not partially accepted.

## 3. Run it

Direct validator:

```
PYTHONPATH=python python3 -m phaino_e1raw --bundle /path/to/bundle
PYTHONPATH=python python3 -m phaino_e1raw --bundle /path/to/bundle --json
```

Or through the Rust CLI (exit 2 on refusal):

```
cargo run -q -p phaino-cli -- fabric e1-bundle --bundle /path/to/bundle --repo-root .
cargo run -q -p phaino-cli -- fabric register-e1 --fabric <fabric> \
  --bundle /path/to/bundle --profile <profile.json> --repo-root .
```

`register-e1` validates the bundle **before** creating the fabric directory, reading the profile or writing any snapshot bytes; it then calls `Fabric::register_e1`, which repeats the mandatory-field/hash gate inside the library. `e1-bundle` only validates. Exit code 0 only when every check passes. Tests: `python/tests/test_e1raw.py` (11 cases, including symlink refusal, low reference SNR, alternate manifest, and CLI exit codes).

## 4. Honest limits

- There are two gates: the richer Python validator (invoked by the CLI) and the Rust library gate. Both look for `bundle.json` first and then for a top-level JSON whose `schema_version` starts with `e1-0-bundle-`; `Fabric::register` uses the same detection and refuses before writing any snapshot. A malformed or non-E1 JSON manifest can still evade detection, so E1 callers must use `register_e1` or the CLI.
- It checks declared metadata and file digests; it does not verify that the calibration certificate is genuine or that the motion truth is correct.
- A valid bundle is not a valid experiment: E1-0 bench results and authorization still decide whether capture may start.
