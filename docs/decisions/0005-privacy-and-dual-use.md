# ADR 0005 — Privacy and dual-use boundary

Status: Accepted
Date: 2026-11-04
Deciders: Haelio Tang (founder)

## Context

The capability this project builds — recovering where, when, and in what conditions an observation was made — is the capability used to locate people. Aircraft-Doppler geolocation demonstrations already show that an ordinary recording can be more identifying than its author expects. A default that emits precise coordinates turns a research tool into a stalking instrument with one configuration change. The founding brief (§12) names hard boundaries; this ADR makes them structural.

## Decision

1. **Output tiers are part of the contract.** Four tiers: `region` (default, open), `sub_region` (logged), `precise` (requires an authorization record + research purpose), `person_level` (never emitted). The tier maps to `sensitivity.max_output_granularity` on every source and propagates to derived results, strictest-wins.
2. **No point output without authorization.** The runtime refuses to serialize a point estimate unless an authorization record exists; the refusal is a typed error, not a warning. Coarse-by-construction is the default path.
3. **Prohibited uses are enumerated and not negotiable**: military targeting, real-time operational command, person-level surveillance or tracking, enforcement action against individuals, and any use whose purpose is revealing a private residence. These are excluded from docs, examples, tests, and commit messages — not merely discouraged.
4. **Sanctioned uses**: environmental science, authorized forensics, public-event verification, historical research, reproducibility studies.
5. **Ethics review is a merge gate** for any change that materially raises precision or lowers cost of the capability (new modality, new verifier library that tightens regions, a model that improves point accuracy). Artifact: a review record under `docs/policy/reviews/`, a red-team case, and an explicit statement of the precision change.
6. **Audit everything precise.** Every query that returns below `region` granularity is logged with actor, purpose, data snapshot, and result tier.
7. **Public data is not free data.** License, access terms, and sensitivity travel with the `Source`; publication granularity inherits the strictest applicable constraint.

## Consequences

### Positive

- The safe default is the easy path: an ordinary user or researcher cannot accidentally produce a precise individual location.
- Review has a concrete trigger and a concrete artifact, so it does not drift into vibes.
- The prohibition is checkable in code review: a point-emitting path without an authorization record is a defect.

### Negative / costs

- Some legitimate precision work becomes slower (authorization + review).
- Enforcement of "prohibited uses" is necessarily partial: the code is open, and a determined actor can strip the guard rails. The policy reduces accidental and casual harm; it does not pretend to prevent reimplementation.
- Maintaining a tier system and authorization record adds friction to the first vertical (M1).

## Alternatives considered

- **Policy-only stance (no code enforcement).** Rejected: defaults are what users actually get; a README disclaimer does not prevent a default `--precise` flag.
- **No precise tier at all.** Rejected: authorized forensic research and calibration studies need ground truth; forbidding it pushes the work into forks with no audit.
- **Geofencing by jurisdiction at runtime.** Deferred: jurisdiction mapping is uncertain and easily bypassed; it may be added at the research-node layer later.

## Clarifications (2026-11-04, after policy review)

These clarify this ADR; they do not change its decision.

1. **Tier vocabulary is a projection, not a fourth ontology value.** The ontology enforces exactly three values of `sensitivity.max_output_granularity`: `region`, `point`, `none`. The four policy tiers are derived: `region` and `sub_region` both require `region` (they differ by output-resolution floor — open band vs enforced minimum, numerics owned by the policy); `precise` requires `point` **plus** a signed authorization record; `person_level` is never emitted regardless of cap. Adding a `sub_region` enum value to the ontology is not required and is not done.
2. **"No enforcement use" means no enforcement *product or workflow*.** It prohibits case tooling, watchlists, custody support, and enforcement action against individuals. It does not prohibit documenting a **refusal boundary**, including the narrow authorized-forensics route in [ethics §5.3](../policy/ethics-and-privacy.md) (lawful authorization before any query, place/event question only, independent reviewer, `sub_region` cap by default, full audit). That route is a boundary that keeps audit and coarse gates in place; the project ships no enforcement capability.
3. **Erasure is tombstone-based.** Policy requires removal of blob content while retaining hash, provenance, and append-only audit, with errata rather than silent deletion for published claims. The M0 ontology has no tombstone status yet; adding it is a storage ADR due before any institutional deployment (tracked in the ROADMAP decision log).
4. **Precision numerics belong to policy** (`docs/policy/ethics-and-privacy.md` §3): open band 0.25°, enforced region floor 0.05° / H3 resolution ≤ 7. The ontology owns only the cap. Changing either value requires an ADR.

## References

- [Ethics and privacy](../policy/ethics-and-privacy.md)
- [Data governance](../policy/data-governance.md)
- [Founding brief](../product/founding-brief.md) §12
- [World ontology](../specs/world-ontology.md) — `sensitivity`, `max_output_granularity`
