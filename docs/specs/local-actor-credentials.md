# Local actor credentials and signed refusal audits

**Status:** implemented as a local-first credential, not a PKI · 2026-11-07 · **Related:** [ADR 0026](../decisions/0026-runtime-governance-primitives.md)

## Purpose

A local actor credential binds an actor id, an authority claim and a revocation flag to a local HMAC-SHA256 secret. It is used by `phaino audit-check --actor-file` so an audit row can prove that the same local key produced it.

It does **not** prove that the key holder is an authorized person, that the authority claim is lawful, or that a policy was approved. It is a local possession check, not institutional identity.

## Credential file

```json
{
  "actor_id": "local-op",
  "authority": "researcher",
  "secret_hex": "<64 lowercase hex characters = 32 bytes>",
  "key_id": "<SHA-256 of the secret bytes>",
  "revoked": false
}
```

- `key_id` must equal `SHA-256(secret)`; a mismatch is refused.
- `revoked: true` is refused.
- On Unix the file must not be group/other-readable (mode `0600` or stricter).
- The secret is not derived from a passphrase and has no hardware protection.

## Signature

`LocalActor::sign` sets `actor_key_id` and an HMAC-SHA256 `actor_signature` over the canonical audit payload digest, excluding `actor_signature` itself. `phaino audit-verify --actor-file` verifies every row against the key. The signature is symmetric: anyone with the credential can sign; there is no non-repudiation.

## Policy artifact source and boundary

`phaino policy-check --policy <file>` loads and validates an externally supplied policy JSON. `phaino audit-check --policy <file>` records that policy digest instead of the compile-time M0 default. The validator rejects non-`region_level` tiers, a zero precision ceiling and a disabled refusal audit. `PolicyArtifact::enforce_output(tier, precision_m)` rejects a tier outside the allowed list and a precision finer than the ceiling.

The policy file is caller-supplied and **not signed or anchored**; loading it proves content integrity only. The boundary check is an API-level check, not yet wired into every data-access/output path.

## Limits

- HMAC secret compromise allows signing; there is no key rotation/revocation service.
- Local actor file authentication is not a multi-user identity system.
- Policy approval provenance and policy signatures are future work.
- The E1 calibration certificate date is syntax-checked (`YYYY-MM-DD`) but its issuer and real validity are not authenticated.
