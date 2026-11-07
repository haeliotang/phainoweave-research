# ADR 0018 — Symmetry convention audit and frozen-protocol digests

Status: Accepted
Date: 2026-11-05
Deciders: Haelio Tang (founder)

## Context

C1's symbolic proof and the independent certificate agreed with each other, but the clock-rate parameter action recorded in the PR-4d report (`f0' = k f0, b' = k b, t0' = t0/k`) differs from the action C1 uses (`f0' = f0/k, v' = v, t0' = k t0 + β, b' = k b`). C1 concluded `f0·b` invariant and `b/f0` refuted; the PR-4d formula would imply the opposite. The discrepancy had to be resolved before `f0·b` could be called a theorem, and before any unresolved L1 mathematics entered E1.

The audit also exposed a second P0 defect: the "frozen" claims protocol digest differs across environments because evidence attachments are inside the digested payload.

## Decision

1. **The forward model is the sole basis for a symmetry claim.** A generator is admitted only if, under an explicitly stated observation-time coordinate convention, applying it to the parameters reproduces the *observed output function* within a declared tolerance. A parameter expression that looks invariant is not evidence; forward preservation plus group axioms is.
2. **Two conventions, one group, explicit mapping.**
   - Method/C1 convention: `t_obs = k · t_phys + β`, induced action `(f0, v, t0, b, c) → (f0/k, v, k·t0 + β, k·b, c)`; observed frequency is `(1/k)·f_phys((t_obs − β)/k)`.
   - Certificate convention: `t_obs = t_phys/k_c + β`, induced action `(k_c·f0, v, β + t0/k_c, b/k_c, c)`; mapping `k_c = 1/k`.
   Both preserve the forward output (measured max relative mismatch 8.9e-16 and 8.5e-16) and generate the same group. Any report must name its convention and map to the other; mixing them is a defect.
3. **Audit verdict.** A `contradicted` claim produced by an L1 proof must be labelled **`formal_counterexample`** (proof-decided), never conflated with an empirically contradicted physical statement. The PR-4d written triple does **not** preserve the observation (measured 2.5e-2 mismatch even with a time-axis map); it was an incorrect statement in a frozen report, not a competing symmetry. The correct action is the one above. The PR-4d equivalence conclusion ("a clock rate is an exact reparameterisation") stands; its written parameter action is corrected by erratum. Under the correct action, **`f0·b` is invariant, `b/f0` is not** (`b/f0 → k²·b/f0`), and `v` is invariant under `G_clock`; T4/T5 are confirmed, not overturned.
4. **Invariance vs equivariance is stated explicitly.** Clock changes act on the observation coordinate; the forward curve is equivariant, while a physical quantity is invariant only if its value is preserved by the induced parameter action. Every claim record names which notion it relies on.
5. **Generator coverage is a gate condition.** A group claim requires every declared generator to be tested (identity, composition, inverse, domain, forward preservation). A missing or untested generator yields `L1 incomplete`, never `L1 proven`; a certificate that claims invariance while its numeric check refutes it is a disagreement that withholds support. Negative contract tests are mandatory: wrong certificate, omitted generator, contradicted nuisance assumption.
6. **Frozen protocol digests cover only the frozen payload.** Claims, generators/actions, conventions, thresholds, gate rules, precedence and model declaration are canonicalised and digested. Certificate evidence, environment, timestamps and development statistics are attached outside the payload and referenced by their own digest. The environment must not change the frozen digest.
7. **Historical runs are preserved, not rewritten.** C1's original protocol digests (`2478226368…` locally, `4823dac1…`/`6b87fd81…` in CI) and results remain as historical records with the defect noted. A new protocol version (`pr4e-claims-1.2.0`) with the separated payload is validated against a new locked run; only then is anything called frozen.
8. **No unresolved L1 mathematics flows into E1.** C2 may proceed, but E1's physical-claim design waits on the closure of this audit and the protocol-freeze fix. Negative results and erratum are published alongside the original reports.

## Consequences

### Positive

- The invariant set is now tied to an explicit convention and a forward-preservation test, not to a remembered formula.
- Evidence can accumulate without perturbing the frozen protocol digest, which is what a frozen protocol is for.
- The gate now has contract tests that make "omitted generator" a blocking condition.

### Negative / costs

- Two conventions must be maintained and mapped in code, reports and proofs; a convention bug is possible and must be covered by tests.
- Erratum and a new protocol version add bookkeeping; old results are superseded for operational use but retained for history.
- Generator-coverage checks add protocol surface and can fail closed.

## Alternatives considered

- **Pick the PR-4d formula and adjust the forward model.** Rejected: it does not preserve the observation; changing physics to fit a memo is exactly what the project forbids.
- **Declare both conventions "the same" without mapping.** Rejected: they produce different parameter actions; the mapping must be explicit.
- **Redefine the C1 digest by overwriting the old protocol.** Rejected by the founder's ruling: old runs stay historical; a new version and independent digest are created.

## References

- [Audit report](../experiments/2026-11-05-c1-symmetry-audit.md)
- [PR-4d corrections](../experiments/2026-11-05-pr4d-report-corrections.md)
- [ADR 0017](0017-gated-invariants.md), [ADR 0016](0016-identifiable-claims.md)
- [C1 report](../experiments/2026-11-05-c1-identifiability.md)
- [ADR 0019](0019-authoritative-frozen-payload-and-c2.md) — authoritative frozen payload, evidence layers, C2 attribution rule
