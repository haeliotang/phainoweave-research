# ADR 0027 — Hardened v1.1 as a separate candidate reproducibility protocol

Status: Accepted (normative decision only; candidate estimator not yet a blocking gate)
Date: 2026-11-07
Deciders: Haelio Tang (maintainer)
Maintainer approval: 2026-11-07 — explicit session direction selected option A (retain x86_64, freeze hardened v1.1 separately, preserve frozen E0 failures).

## Context

Frozen E0 (`records_sha256 674213d9…`) has a measured R1-D failure on Linux x86_64 for `null_noise_only` trial 2456: the convergence flag flips on a near-threshold stall. The failure is historical and must remain visible.

The separate hardened estimator v1.1 changes the stalled-model classification: an indeterminate fit whose model explains less than half the adequacy floor (`improvement_ratio < 0.25`) is decisively `rejected` rather than left indeterminate. On the E0 grid this removes the null-trial decision split; measured decision equivalence is 2500/2500 on both host↔Linux-arm64 and host↔Linux-amd64.

That measurement is not yet a reproducibility gate. It was produced by locally generated artifacts, not by an authoritative CI run over a frozen protocol, code revision, dependency set and input artifact. This ADR records the decision to keep x86_64 in the target and to treat hardened v1.1 as a **separate candidate protocol**, never as a retroactive repair of frozen E0.

## Decision

1. **Frozen E0 is immutable.** Its contents, digest and R1-D failure conclusion remain the historical record. Hardened v1.1 results must not be used to rewrite or "retroactively pass" E0.
2. **Retain Linux x86_64, macOS arm64 and Linux arm64 as support targets.** x86_64 is not removed to obtain a green result.
3. **Freeze hardened v1.1 as a separate candidate protocol**, with its own protocol file, estimator version, code revision, dependency pins and input artifact identity.
4. **R1-N remains enforced** for the existing E0 path.
5. **R1-D becomes blocking only after the candidate protocol passes its own verification**; until then it is reported, not claimed.
6. **R2 remains a reported bitwise difference**, never "passed" merely because v1.1 decisions agree.
7. **No coverage claim.** The 2500/2500 result means: on the tested 2500 E0-grid cases, v1.1 decisions agree across the tested environments. It does not establish E1 reproducibility, and it does not cover the physical mismatch/false-accept behavior observed in E1-C.

## Precondition for enabling blocking R1-D on v1.1

All three must hold:

1. **Semantic comparison, not just final status.** Compare `decision_status`, `decision_reason`, `parameter_identifiable`, `model_adequate`, and the indeterminate/boundary semantics. A final-status match with a different reason is not equivalent. The artifact must also match the frozen canonical identity digest for all 2500 `(condition, trial, seed)` tuples; count equality alone is insufficient. `primary_fields` must come from the protocol and its absence is a hard failure, not a fallback.
2. **Authoritative common inputs.** CI runs one frozen protocol at one code revision with pinned Python/Rust dependencies and a reproducible input artifact. Platforms must not compare against their own newly generated baseline. If a target runner is unavailable (for example hosted arm64 macOS on a private repo), that cell is explicitly reported as missing, never silently treated as passing.
3. **No retroactive or over-broad claim.** v1.1 cannot pass frozen E0 retroactively, and 2500/2500 cannot mask the E1-C physical mismatch/false-accept findings.

## Consequences

### Positive

- Keeps x86_64 in scope without falsifying history.
- Separates "decision agreement" from "reproducibility gate".
- Gives hardened v1.1 a path to blocking status with explicit evidence.

### Negative / costs

- CI must run a second 2500-trial matrix on three environments.
- Frozen E0 will remain red on R1-D in reports; v1.1 is an additional protocol, not a replacement.
- A boundary/reason-aware comparator must be maintained.

## References

- [ADR 0013](0013-reproducibility-contract-v2.md) — R1-N/R1-D/R2 definitions (historical meaning unchanged)
- [ADR 0014](0014-failure-taxonomy-and-decision-stability.md) — failure taxonomy
- [PR-4c report §7](../experiments/2026-11-05-pr4c-hardened-validation.md)
- [R1-D container report](../experiments/2026-11-06-r1d-container-report.md)
