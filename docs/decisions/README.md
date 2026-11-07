# ADR index

Architecture Decision Records for PhainoWeave. Accepted ADRs outrank the ROADMAP and the founding brief; an ADR that is `Proposed` is discussion only.

| ADR | Title | Status |
| --- | --- | --- |
| [0001](0001-brand-scope-and-non-goals.md) | Brand, scope, and non-goals | Accepted |
| [0002](0002-verification-first-inference.md) | Verification-first inference | Accepted |
| [0003](0003-world-ontology-and-provenance.md) | World ontology and provenance | Accepted |
| [0004](0004-rust-core-python-inference-boundary.md) | Rust core / Python inference boundary | Accepted |
| [0005](0005-privacy-and-dual-use.md) | Privacy and dual-use boundary | Accepted |
| [0006](0006-canonical-json-and-digests.md) | Canonical JSON, digests, and the replay key | Accepted |
| [0007](0007-federated-world-data-infrastructure.md) | Federated world data infrastructure | Accepted |
| [0008](0008-two-track-execution.md) | Two-track execution and the research-grade minimal fabric | Accepted |
| [0009](0009-evidence-store-guarantees.md) | Evidence store guarantees: append-only, detection, replay | Accepted |
| [0010](0010-m1-identifiability-program.md) | M1 as an identifiability program (E0/E1/E2) | Accepted |
| [0011](0011-privacy-forensics-and-publication-rulings.md) | Founder rulings: privacy numerics, forensics boundary, publication posture | Accepted |
| [0012](0012-research-grade-minimal-fabric.md) | Research-grade minimal fabric v0 | Accepted |
| [0013](0013-reproducibility-contract-v2.md) | Reproducibility contract v2: R1-N, R1-D, decision stability | Accepted |
| [0014](0014-failure-taxonomy-and-decision-stability.md) | Failure taxonomy and decision stability | Accepted |
| [0015](0015-model-adequacy-and-epistemic-decisions.md) | Model adequacy layer and epistemic decisions | Accepted |
| [0016](0016-identifiable-claims.md) | Identifiable claims and claim-level semantics | Accepted |
| [0017](0017-gated-invariants.md) | Gated invariants: invariance, identifiability, statistical support | Accepted |
| [0018](0018-symmetry-convention-audit.md) | Symmetry convention audit and frozen-protocol digests | Accepted |
| [0019](0019-authoritative-frozen-payload-and-c2.md) | Authoritative frozen payload, evidence layers, C2 attribution rule | Accepted |
| [0020](0020-measurement-model-and-c2-repair.md) | Measurement model, evidence integrity, C2 repair protocol | Accepted |
| [0021](0021-conditional-measurement-error-and-predictive-acceptance.md) | Conditional measurement-error modeling and predictive acceptance | Accepted |
| [0022](0022-candidate-classification-and-sealed-run.md) | Candidate classification and the sealed-run rule | Accepted |
| [0023](0023-three-operations-and-sealed-protocol.md) | Three operations, B1 self-confirmation, sealed confirmation protocol | Accepted |
| [0024](0024-run-lifecycle-and-evidence-archive.md) | Sealed-run lifecycle and content-addressed evidence archive | Accepted |
| [0025](0025-e1-scope-and-scale-audit.md) | E1 scope, scale audit, and pilot/confirmation rules | Accepted |
| [0026](0026-runtime-governance-primitives.md) | Runtime governance primitives for real-data intake | Accepted |
| [0027](0027-hardened-v1.1-reproducibility-protocol.md) | Hardened v1.1 as a separate candidate reproducibility protocol | Accepted |

## Format

```
# ADR NNNN — Title

Status: Accepted | Proposed | Superseded by NNNN
Date: YYYY-MM-DD
Deciders: ...

## Context

## Decision

## Consequences
### Positive
### Negative / costs

## Alternatives considered

## References
```

Rules:

- One decision per ADR. If an ADR needs a second decision, write a second ADR.
- An Accepted ADR is amended by a new ADR, never edited to say something different.
- Numeric claims in an ADR follow the same rule as everywhere else: `measured` with an artifact path, or `external claim` with a link, or `unverified`.
