# ADR 0013 — Reproducibility contract v2: R1-N, R1-D, and decision stability

Status: Accepted
Date: 2026-11-05
Deciders: Haelio Tang (founder)

## Context

The first cross-platform comparison ([report](../experiments/2026-11-05-cross-platform-e0.md)) found that numeric agreement and scientific agreement are different properties. Parameters matched to ~1e-9 where the inverse problem is identifiable, yet one of 2500 convergence decisions flipped near its threshold and changed a condition's reported success rate from 100/100 to 99/100. Under the v1 contract (ADR 0012 §6) that had to be reported as "R1 not established", which is honest but says too little: it does not distinguish *the numbers are equal but a decision is unstable* from *the numbers changed* from *the quantity is unidentifiable and has no business being compared*.

The same comparison also showed that unidentifiable quantities (standard errors, condition numbers, correlations in null/degenerate conditions) can differ by orders of magnitude while the science is unchanged, and that implementation metadata (least-squares iterations) differs almost everywhere without being a scientific output.

Tolerances cannot fix this. Loosening a tolerance until the comparison passes would hide exactly the decision instability that matters, and deciding "identifiable" from the fact that two machines agree would be circular.

## Decision

1. **Four field classes, declared by the protocol.** Every comparable field belongs to exactly one class:
   - **A — discrete identity**: trial/condition ids, sample index, seed, version strings, model type, counts (`n`, `k`). Must match exactly.
   - **B — identifiable numeric**: `f0`, `v`, `t0`, `b`, their relative errors, residual RMS/SSE, improvement ratio. Compared with abs+rel tolerance, and **only for trials the pre-declared rule calls identifiable**.
   - **C — unidentifiable diagnostic**: standard errors, condition number, correlations, worst-direction components, worst-direction relative SE, gradient norm. Compared by **semantics** (do both sides agree the quantity is degenerate/non-finite/within the same order-of-magnitude class), never by unbounded numeric equality. Numeric differences are reported, never gated.
   - **D — decision**: `accepted`, `success`, `converged`, `abstained`, and condition-level rates derived from them. Compared by classification consistency plus boundary stability.
2. **Identifiability is pre-declared on the reference, never inferred from agreement.** The protocol fixes one rule evaluated before any comparison (e.g. reference converged, worst-direction relative SE ≤ 1e-2, condition number ≤ 1e4, parameters finite). It is applied identically to every trial and reported per trial. A trial's class cannot depend on how close the two machines happen to be.
3. **Decisions have an `indeterminate` state with a declared margin.** Each decision names its deciding statistic and a margin. If the statistic lies within the margin of the threshold, the decision is `indeterminate` on both sides; outside it, the decisions must match. The **raw binary values are retained** in the report (`reference_raw`, `candidate_raw`, `status`); post-processing never overwrites what was observed. Margins and their justification are part of the protocol.
4. **R1 is split into two reported targets.**
   - **R1-N (numerical equivalence)**: all class-A fields exact and all class-B fields of identifiable trials within tolerance.
   - **R1-D (decision equivalence)**: every decidable decision matches after indeterminate masking, no indeterminate becomes a decided difference, and **no condition-level rate or count changes at all** (strict materiality: a masked indeterminate flip that still changes a reported rate fails R1-D; masking explains the mechanism, it does not excuse the changed scientific output).
   - A report carries `reproduction_level ∈ {R2, R1-N+R1-D, R1-N only, R0 only, none}`. `exact` only when R2; `numerically_equivalent` only when R1-N+R1-D; a decision-instability count is always visible. Unidentifiable trials are `not_applicable` for R1-N, not silently dropped.
5. **Three-environment validation before any freeze.** A cross-platform protocol is validated on: A local macOS arm64 (reference), B `ubuntu-24.04` x86_64, C `ubuntu-24.04-arm` arm64, with fixed runner labels (not `ubuntu-latest`), pinned Python/numpy/SciPy and dependency lock, and recorded BLAS/LAPACK implementation, CPU architecture, thread/settings and OS image version. B↔C tests same-OS/different-architecture; A↔C tests same-architecture/different-OS.
6. **Validation must include adversarial fixtures**, not only the real artifact: boundary samples just inside/outside each decision margin; unidentifiable samples where B fields diverge widely; a real numeric regression that must fail R1-N; a material rate change that must fail R1-D. Rules are validated on a sample not used to derive the tolerances.
7. **The CI gate is enabled only after the protocol is frozen** (bounds validated on the three environments and on the held-out sample, protocol digest recorded). Until then CI compares and reports without claiming R1.
8. **Environment differences are recorded separately from numerical tolerance.** A difference attributable to interpreter/library/image version is not a numerical-equivalence result; the protocol records environment identity with every comparison.

## Consequences

### Positive

- Reports answer the scientific question directly: did the numbers agree, did the decisions agree, and were the compared quantities identifiable at all?
- Decision instability becomes a first-class, visible outcome rather than a hidden threshold flip or a tolerance casualty.
- Unidentifiable quantities stop generating false failures; implementation metadata stops generating meaningless exactness requirements.
- Tolerances are constrained: they grow from measurement and from decision margins, not from a desire to pass.

### Negative / costs

- More protocol surface: classes, margins, identifiability rule, two targets, reproduction level.
- The identifiability rule and margins are scientific commitments that need justification and a held-out validation; they can be wrong and must be revisable only by a new protocol version.
- `indeterminate` adds a third decision value and therefore a reporting obligation (counts, material-change rule).
- Three-environment CI costs runner minutes and requires pinned environments that must be maintained.

## Alternatives considered

- **Loosen tolerances until R1 passes.** Rejected: hides decision instability and is exactly the failure mode this contract exists to prevent.
- **Infer identifiability from cross-machine agreement.** Rejected as circular; the rule must be independent and pre-declared.
- **Treat the decision flip as nondeterminism and ignore it.** Rejected: it changed a reported scientific rate.
- **One R1 target with a footnote.** Rejected: conflates numeric and decision reproducibility; the report must separate them to be usable.

## References

- [Cross-platform measured report](../experiments/2026-11-05-cross-platform-e0.md)
- [ADR 0012](0012-research-grade-minimal-fabric.md) §6 — R0/R1/R2 levels (this ADR refines R1)
- [ADR 0010](0010-m1-identifiability-program.md) — identifiability as a first-class property
- [Protocol v2](../experiments/2026-11-05-cross-platform-e0.md) — measured-draft protocol and validation plan
