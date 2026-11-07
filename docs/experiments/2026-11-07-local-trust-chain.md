# Local trust chain — signed audit, policy file, boundary check, calibration date

**Status:** implemented; CI green at 42365583281 (except optional macOS arm64 cell) · 2026-11-07 · **Related:** [ADR 0026](../decisions/0026-runtime-governance-primitives.md), [local actor spec](../specs/local-actor-credentials.md)

This is the minimal local-first trust chain requested for P1. It is **not** a multi-user PKI and does not establish institutional authorization.

## Implemented

1. **Local actor credential** (`phaino-core::LocalActor`)
   - JSON file with actor id, authority claim, 32-byte HMAC secret, derived key id and revocation flag;
   - Unix file mode must be `0600` or stricter;
   - revoked credentials are refused;
   - `sign`/`verify` HMAC-SHA256 over the canonical audit payload excluding the signature field.

2. **Signed audit path** (`record_authorization_with_key`)
   - `phaino audit-check --actor-file <credential.json>` records a signed allowed/denied attempt;
   - `phaino audit-verify --actor-file <credential.json>` verifies every stored row against the key and still checks the append-log/payload chain.

3. **External policy file** (`PolicyArtifact::from_path`)
   - `phaino audit-check --policy <policy.json>` records the supplied policy digest;
   - `phaino policy-check --policy <policy.json> [--tier region_level] [--precision-m N]` validates the artifact and enforces the declared capability/precision boundary;
   - non-`region_level` tiers, a zero precision ceiling and disabled refusal audit are refused.

4. **Calibration date syntax** (E1 gate, Rust + Python)
   - `valid_until` must be a real ISO `YYYY-MM-DD` date; malformed dates are refused.
   - This is syntax, not issuer authentication or expiry against a trusted clock.

## Verified locally

- Rust: 116 tests; Python: 441 tests; links: 648.
- `phaino audit-check --actor-file` produced a signed denial; `audit-verify` returned `audit signatures verified: 1 row(s)`.
- `phaino policy-check` accepted `region_level, 1000 m` and refused `region_level, 500 m` under a 1000 m ceiling.
- The E1 end-to-end fixture now signs its refusal row and verifies the signature.

## Remaining P1 gaps

- No institutional identity, key rotation service or revocation list; HMAC is symmetric.
- Policy file source/signature and governance approval are not verified.
- The boundary check is an API/CLI check, not wired into every data-access/output path.
- Calibration issuer allowlist and expiry against a trusted time source are not implemented; only date syntax.
- Consent coverage remains a declared hash.
