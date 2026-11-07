# ADR 0008 — Two-track execution and the research-grade minimal fabric

Status: Accepted
Date: 2026-11-04
Deciders: Haelio Tang (founder)

## Context

A status review (2026-11-04) found the project's contracts and architecture mature and its scientific capability at zero, and proposed a strict serial order: finish M0, build data fabric units D1–D3, then start M1. That order is too conservative. M1's first experiment does not need global maps, DEM, weather, and track adapters; it needs **one legally usable fixed dataset plus one independent reference source**. Building platform-grade federation before testing whether any inference mechanism works would spend the project's scarcest resource — the first real result — on infrastructure the experiment does not consume.

The review also found a second problem: design volume is now a substitute for evidence. More ontology, more adapters, and more UI can each look like progress while the central question stays untested.

## Decision

1. **Freeze non-essential architecture.** No new ontology objects, platform components, or surfaces while the first falsifiable experiment is unwritten. A new design, directory, or ADR is admitted only when a concrete experiment is blocked without it. The nine-object model is closed; amendments need a failed experiment to justify them.
2. **Two tracks run in parallel and converge on one experiment.**
   - **Track A — Engineering:** A1 append-only evidence store (PR-1); A2 CLI / golden replay; A3 minimal license gate; A4 fixed-snapshot reader. Each is the smallest unit that unblocks the experiment.
   - **Track B — Science:** B1 freeze the question; B2 controlled synthetic experiment (`E0`); B3 real-sample pilot (`E1`); B4 locked preregistration (`E2` benchmark).
   - **Convergence:** `M1-E0` (first falsifiable experiment, synthetic identifiability) and `M1-E1` (real controlled recordings, locked evaluation). Serialized dependencies inside a track are allowed; one track never waits for the other merely for tidiness.
3. **Split the data fabric into two tiers.**
   - **Research-grade Minimal Fabric (RMF)** — the real M1 prerequisite: source registration, license check, immutable fixed snapshot (checksum + version), offline read, and provenance records. Implemented in PR-3. One dataset may enter through a manifest and a hash; it does not need a catalog service, planner, or cache.
   - **Platform-grade Federated Fabric (PFF)** — the ADR 0007 target: catalog, multiple provider adapters, query planner, incremental cache, fault recovery, redistribution machinery. Deferred until a concrete experiment requires it.
4. **Amend ADR 0007's phasing.** Its decision (federate, do not own a second global database) stands. Its §12–§13 sequencing does not: D1's contract is reduced to what the RMF needs; **D2's five production adapters and D3's planner are deferred** until an experiment states which source it needs and why a fixed snapshot is insufficient. Overture/Geofabrik/DEM/ERA5/adsb.lol adapters are not prerequisites for the first acoustic experiment.
5. **Success criteria change.** The project is judged by executed contracts, covered failure modes, and one reproducible experiment report — not by document volume, test count, or connected sources.

   | Old standard | New standard |
   | --- | --- |
   | More design documents | More contracts proven by execution |
   | More passing tests | Coverage of real failure modes and wrong hypotheses |
   | More data sources | An independent source materially improving inference |
   | More precise location | Trustworthy, calibrated, abstaining output |
   | More platform modules | A reusable, falsifiable physical-inference mechanism |

6. **Engineering hygiene is allowed in parallel but is subordinate.** Documentation link checking and dependency/license auditing may land when they do not displace an experiment; neither may be queued ahead of E0/E1.

## Consequences

### Positive

- The first falsifiable result can exist without a platform; the project can fail fast on the science instead of slowly on the plumbing.
- The RMF still enforces license, provenance, and snapshot discipline, so speed does not reopen the legal/privacy questions the policy closed.
- Scope freezes make "we did not build it" a deliberate decision instead of an omission.

### Negative / costs

- Two tracks in one repository increase coordination cost and the risk of merge conflicts in shared files.
- RMF is deliberately throwaway-adjacent: parts of its manifest/snapshot layer will be absorbed by the PFF later, and some rework is accepted.
- Deferring adapters means E1 cannot expand beyond the fixed datasets already licensed; a data gap can pause science rather than engineering.
- The freeze can hide a genuine architectural need; the escape hatch is "an experiment is blocked", which requires discipline to use honestly.

## Alternatives considered

- **Serial order (M0 → D1–D3 → M1).** Rejected: delays the only question that matters behind infrastructure the experiment does not need.
- **"Just do acoustics with ad-hoc downloads".** Rejected: license, snapshot, and provenance are the project's differentiators; bypassing them for speed would produce an unreproducible toy.
- **Build the full PFF first.** Rejected: it is a multi-month platform with no validated inference to justify it.
- **Fork into two repos (platform vs science).** Rejected for now: one repository keeps the evidence chain and the experiment in one reviewable history; revisiting this is allowed if coordination cost dominates.

## References

- [ROADMAP](../roadmap/ROADMAP.md) — tracks A/B, M1-E0/E1/E2
- [ADR 0007](0007-federated-world-data-infrastructure.md) — federation principle (unchanged), phasing amended here
- [ADR 0009](0009-evidence-store-guarantees.md) — what the append-only store actually claims
- [ADR 0010](0010-m1-identifiability-program.md) — the narrowed M1
- [Research program](../research/research-program.md) — the scientific claim
