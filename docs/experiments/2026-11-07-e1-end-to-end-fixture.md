# E1 integration fixture — bundle → snapshot/store → refusal audit (CLI/Fabric/Store only)

**Status:** CLI/Fabric/Store integration passing locally and in CI; not a cockpit UI test · 2026-11-07 · **Script:** `scripts/e1_e2e.sh`

This fixture exercises the evidence contract across component boundaries. It is not a cockpit browser test and it is not authentication of any real-world authorization.

## Covered path

1. Build a schema-valid synthetic E1 raw bundle (audio, frequency reference + calibration certificate, PPS time reference, motion reference, site/legal/consent declarations, environment, operator).
2. Run `phaino fabric register-e1`; it must pass the Python gate and create a snapshot.
3. Read the audio back through `phaino fabric read` with the license gate; bytes must match.
4. Build a second bundle with `consent_sha256` removed; `register-e1` must refuse **before** creating the target fabric directory.
5. Record a researcher-denied `publish-evidence` attempt with `phaino audit-check --actor-file`; the denial must persist and be HMAC-signed.
6. Verify every audit signature with `phaino audit-verify --actor-file`, then read the row back with `phaino audit-list --json true`; last decision must be `denied`.

## Local result

```
e1 fixture: 1 audit row(s), last decision=denied
e1 fixture OK: artifacts/e1-e2e
```

## Cockpit status semantics

The E1 view now displays three separate layers, never one green badge:

| Layer | Current status | Meaning |
|---|---|---|
| `metadata_complete` | partial | schema/hash/path/declared-SNR gate only |
| `authority_verified` | not_verified | site authorization/consent are declarations, not authenticated |
| `scientific_evidence_validated` | not_available | no bench data, no real measurements |

## Honest limits

- The fixture's bundle is synthetic and its hashes are self-consistent, not authentic.
- The calibration certificate, legal review ID and consent hash are declarations.
- The store audit actor is a caller-declared identity.
- The cockpit layer statuses are static contract values; this fixture does not yet drive a browser/Tauri end-to-end test.
- Passing this fixture means the components agree on the contract, not that E1 physical validity is established.
