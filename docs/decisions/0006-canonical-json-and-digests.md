# ADR 0006 — Canonical JSON, digests, and the replay key

Status: Accepted
Date: 2026-11-04
Deciders: Haelio Tang (founder)

## Context

[The ontology spec](../specs/world-ontology.md) §2 derives every identifier from SHA-256 over RFC 8785 canonical JSON of a record's identity tuple, and §10 stores `_digest` per row plus a `_replay_key` on `inference_run` (identity tuple without `started_at`, `environment`, and outputs). Replay parity at M4 requires the same bytes on an independent node, and the Python SDK must eventually produce the same digests.

The M0 crate currently serializes with sorted-key `serde_json`, which is not RFC 8785 for numbers (Rust `ryu` emits `1e30`, RFC 8785 requires `1e+30`) and differs for `-0.0`. Two ways to close the gap: add a JCS crate dependency, or implement the canonicalizer in-core. Adding an unvetted dependency to the module that defines identity is a supply-chain decision we should not make on day one, and the current sandbox cannot install a new crate. The replay key was also not implemented at all (`replay_digest()` returned the record digest).

## Decision

1. **Adopt PCJ-0: an in-core canonical JSON that conforms to RFC 8785 for the value subset the ontology uses** — `null`, booleans, strings, integers, finite doubles, arrays, and objects. Normative rules:
   - UTF-8 output, no insignificant whitespace.
   - Object members sorted by UTF-16 code units; **M0 restriction: object keys are ASCII**, where byte order and code-unit order coincide. Non-ASCII or supplementary-plane keys are rejected rather than sorted incorrectly.
   - Strings escaped minimally: `\"`, `\\`, `\b`, `\t`, `\n`, `\f`, `\r`, other C0 controls as `\u00XX` with lowercase hex; `/` is not escaped; non-ASCII is emitted as UTF-8 (no `\u` escaping).
   - Numbers: integers within ±(2^53−1) emitted as integers; doubles emitted with ECMAScript `Number::toString` semantics (shortest round-trip digits; plain decimal when `1e-6 ≤ |x| < 1e21`, otherwise `d[.ddd]e±X`, with `+` only for a non-negative exponent: `1e-7`, `1e-27`, `1e+21`). `-0.0` is `0`. NaN and ±Infinity are rejected, never serialized.
   - Duplicate object members cannot occur because inputs are typed records, not parsed text.
2. **Identity, digest, replay key.**
   - Identifier `d16` = first 16 lowercase hex of SHA-256 over PCJ-0 of the type's identity tuple (spec §2 table).
   - `_digest` = SHA-256 over PCJ-0 of the complete stored canonical record (excluding `_record_time`, which is store clock, unless the row is immutable and already carries it).
   - `_replay_key` = SHA-256 over PCJ-0 of the identity tuple **excluding** `started_at`, `environment`, and output hashes. Two runs of the same inputs on different hosts must share a replay key while their record digests may differ.
3. **Conformance is tested, not asserted.** Tests must include the RFC 8785 Appendix B number and string vectors (at minimum `333333333.33333329 → 333333333.3333333`, `1E30 → 1e+30`, `4.50 → 4.5`, `2e-3 → 0.002`, `1e-27 → 1e-27`, and the escaped-literal vector). The Rust core and the Python SDK must both pass the same vectors before any digest is published across implementations; this is a hard gate for M4, tracked in the ROADMAP decision register.
4. **Changing the canonical form requires an ADR** and invalidates all previously published digests. The ontology version pins the canonicalization version.
5. **A vetted JCS dependency may replace the in-core implementation later** — only by ADR, with the same conformance vectors and cross-language vectors passing before and after.

## Consequences

### Positive

- Identity is deterministic, reproducible across processes, and testable against a published standard rather than "whatever serde did".
- The replay key separates "same inputs" from "same host timing", which is exactly what M4 parity needs.
- No new dependency on the module that mints identity.

### Negative / costs

- We own ~150 lines of subtle numbering/escaping code and must maintain it; an error changes identifiers silently.
- ASCII-key restriction is a real limit; a non-ASCII key is a typed error rather than a JCS-correct sort.
- The Python SDK must implement the same canonicalizer (allowed to be a separate implementation, validated by shared vectors).

## Alternatives considered

- **Keep sorted-key `serde_json` digests.** Rejected: silently non-conformant with the published spec and non-portable to Python.
- **Add `serde_jcs` / `jcs-canonicalize` now.** Reasonable later; rejected today because identity is a supply-chain-sensitive surface and the sandbox cannot install it. Recorded as the approved upgrade path.
- **Hash binary encodings (postcard/bincode) instead of JSON.** Rejected: the Python SDK and external verifiers must compute the same digests without a Rust runtime; JSON is the interop contract.

## References

- [World ontology](../specs/world-ontology.md) §2, §10, I6
- [Inferencer contract](../specs/inferencer-contract.md) §3, §4
- [ROADMAP](../roadmap/ROADMAP.md) §7 — digest canonicalization and cross-language vector gate
- RFC 8785 (JSON Canonicalization Scheme), Appendix B test vectors
