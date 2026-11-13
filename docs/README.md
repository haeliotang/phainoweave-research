# Documentation index

Read in this order if you are new to the project.

| Order | Document | Why |
| --- | --- | --- |
| 1 | [Product — founding brief](product/founding-brief.md) | What the project is, what it refuses to become, and the one capability that must work |
| 1a | [Research program](research/research-program.md) | The scientific claim being tested: physics-grounded evidence fusion under incomplete observations |
| 1b | [Observability program](research/observability-program.md) | Empirical limits of physical-world observability, Claim Certificates and gates |
| 1c | [Studies index](../studies/README.md) | Five independent research series and their public evidence status |
| 2 | [Roadmap — plan of record](roadmap/ROADMAP.md) | Milestones M0–M4, work breakdown, falsification criteria |
| 3 | [Architecture overview](architecture/overview.md) | Layers, responsibilities, deployment modes |
| 4 | [Spec — world ontology](specs/world-ontology.md) | The nine objects and the invariants enforced in code |
| 5 | [Spec — inferencer contract](specs/inferencer-contract.md) | What every inferencer plugin must emit and why |
| 6 | [Benchmark and evaluations](roadmap/benchmark-and-evals.md) | How capability is measured, and what would be a false win |
| 6a | [M0 status](roadmap/M0-STATUS.md) | What is actually landed today, and what is not |
| 7 | [Policy — ethics and privacy](policy/ethics-and-privacy.md) | Threat model, capability tiers, review gate |
| 7a | [Local actor credentials](specs/local-actor-credentials.md) | Local HMAC audit identity and policy boundary checks (not a PKI) |
| 8 | [Policy — data governance](policy/data-governance.md) | Sensitivity classes, access, retention, publication |
| 9 | [Research — landscape](research/landscape.md) | Prior art, reusable pieces, and the gap this project fills |
| 10 | [Research — data sources](research/data-sources.md) | Licenses, access limits, snapshot policy |
| 11 | [Research — data infrastructure](research/data-infrastructure.md) | Federated data layer: eight domains, provider notes, data fabric, phasing |
| 12 | [ADR 0007 — federated data infrastructure](decisions/0007-federated-world-data-infrastructure.md) | The binding data-layer constraint (no second global database) |
| 13 | [ADR 0008–0025](decisions/README.md) | Two-track execution; store guarantees; M1 as E0/E1/E2; privacy/forensics/publication; minimal fabric v0; reproducibility contract v2 |
| 14 | [E0 report — synthetic Doppler](experiments/2026-11-04-e0-synthetic-doppler.md) | First experiment: preregistered identifiability study, measured limits, failure thresholds |
| 15 | [C1 report — identifiability contract](experiments/2026-11-05-c1-identifiability.md) | Symbolic proof, independent certificate, locked claim validation |
| 16 | [Project review — omissions and unknown unknowns](roadmap/2026-11-07-project-review.md) | Code/documentation review: P0/P1/P2 findings, fixed defects, remaining risks |

## Directories

| Directory | Contents |
| --- | --- |
| `product/` | Founding brief and its Chinese projection |
| `architecture/` | System-level design |
| `specs/` | Normative contracts (object model, inferencer interface) |
| `roadmap/` | Plan of record and evaluation design |
| `research/` | Prior art, data inventory, measurement notes, and the public observability program |
| `studies/` | Public series indexes for PW-A/PW-H/PW-S/PW-R/PW-V; status and evidence-level labels |
| `policy/` | Ethics, privacy, data governance, review records |
| `decisions/` | ADRs (accepted decisions outrank everything else) |
| `experiments/` | Pre-registered experiments and run reports (created when M1 starts) |

## Conventions

- Every document starts with a status line and a one-line purpose.
- Claims are labeled `measured` (artifact path) or `external claim` (link) or `unverified`.
- Relative links only; a document that cannot be reached from this index or the README is an orphan.
