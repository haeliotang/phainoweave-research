# ADR 0011 — Founder rulings: privacy numerics, forensics boundary, publication posture

Status: Accepted
Date: 2026-11-04
Deciders: Haelio Tang (founder)

## Context

The policy set left several questions explicitly open: whether the authorized-forensics route is a narrow exception or an absolute ban; whether the region floors are permanent constants; who reviews sensitive capability and in which jurisdiction; how the project name constrains forked guardrail removal; when the repository becomes public; and how ODbL obligations apply to an evidence graph. Leaving them open blocks E1 (which needs real recordings and a jurisdiction) and makes the defaults unenforceable. The founder issued rulings on 2026-11-04.

## Decision

1. **Forensics and dual use: a strictly limited exception, not an absolute ban and not an open door.** Permitted only for (a) the operator's own devices, (b) explicitly authorized research subjects, and (c) non-sensitive public environments. Prohibited absolutely: precise localization of unauthorized private individuals, covert tracking, and disclosure of sensitive locations (residence, shelter, medical, protest, workplace of a private person). The seven conditions in [ethics §5.3](../policy/ethics-and-privacy.md) are **executed by the runtime plus a human review**, not merely written in an ADR: an invalid or missing authorization is a typed refusal and an audit row, not a warning. This closes the question §5.3 left open.
2. **Privacy numerics are decision inputs, not permanent constants.** The 0.25° open band, 0.05° enforced floor, and H3 resolution ≤ 7 remain current defaults, but publication granularity is decided per output by four factors: physical area, location sensitivity, re-identification risk, and publication purpose. The policy document must stop presenting the numbers as timeless.
3. **The two floors are not equivalent protection scales and must not be presented as alternatives of equal strength.** H3 resolution 7 has a mean hexagon area of about 5.16 km². A 0.05° latitude span is about 5.6 km north–south, and its east–west extent shrinks with latitude. They describe different shapes and different worst-case re-identification risk; the policy compares the physical area, not the numeric width.
4. **Jurisdiction and review.** The project designates its operating jurisdiction in the Research Node policy before offering any sensitive inference capability, and obtains independent legal and ethical review before that capability is externally available. While the project has a single maintainer, the absence of separation of duties is stated as a limitation wherever publication or authorization separation is described — it is not simulated.
5. **Name and forks.** The name *PhainoWeave* is retained; a trademark search precedes any filing or public launch claim. Apache-2.0 cannot prevent a fork from removing guardrails, so the risk is managed by trademark, hosted-service access control, and verifiable official builds — not by pretending the licence does that work.
6. **Repository visibility.** Publish source and an accurate capability statement after the M0 minimal loop closes, without waiting for M1 success. Sensitive test data, access credentials, and material that could enable locating individuals are handled separately and never in the public repository.
7. **ODbL requires a per-data-flow review, not a blanket conclusion.** ODbL distinguishes a derivative database, a collective database, and a produced work; obligations depend on the specific combination and on whether it is publicly used. Each first use of OSM/adsb.lol data is reviewed as a data flow, and no repo-wide claim ("using OSM means opening the ontology") is made in either direction. The first experiment's data licenses are resolved before its data is fetched; Overture version pinning is settled with the minimal fabric's manifest (ADR 0008), not as a blocker.

## Consequences

### Positive

- E1 can proceed with a lawful data path and a stated jurisdiction instead of an unresolved policy hole.
- Publication granularity becomes a reasoned per-output decision, which is more defensible than a constant copied into every release.
- The fork/name risk is described honestly, and the visibility trigger is testable (M0 loop closes → publish).

### Negative / costs

- Per-output review is slower than a fixed constant and depends on reviewer judgment; it needs a record format, or it will be applied inconsistently.
- Requiring runtime enforcement of the forensic conditions raises the M0/M1 implementation bar: an authorization check with audit becomes a real code path.
- A trademark search and per-flow ODbL review cost money and time before any scientific result exists.

## Alternatives considered

- **Absolute prohibition of forensic use.** Simpler, but it pushes lawful research into forks with no audit and contradicts the founding brief's sanctioned authorized-forensics use.
- **Keep the numeric floors as permanent constants.** Rejected: the H3/degree area mismatch makes a single number indefensible across latitudes and shapes.
- **Defer visibility until M1.** Rejected: the accurate capability statement is exactly what an early public repository is for; waiting invites the opposite impression.
- **Treat Apache-2.0 as a guardrail guarantee.** Rejected as false.

## References

- [Ethics and privacy](../policy/ethics-and-privacy.md) §3, §5.3
- [Data governance](../policy/data-governance.md) §7
- [ADR 0005](0005-privacy-and-dual-use.md) (boundary), [ADR 0008](0008-two-track-execution.md) (fabric tiers)
