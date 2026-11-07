# C1 — Identifiability contract: symbolic proof, independent certificate, and locked claim validation

**Status:** C1-A/B/C complete; C1-D locked validation complete on three environments with one protocol-freeze defect found · 2026-11-05 · **Authority:** [ADR 0017](../decisions/0017-gated-invariants.md), [ADR 0016](../decisions/0016-identifiable-claims.md) · **Frozen history:** E0, PR-4c, PR-4d untouched

**Post-publication audit (2026-11-05):** the clock-action convention was audited; the PR-4d action formula was found invalid as written (2.5e-2 forward mismatch) and C1's T4/T5 are confirmed under the declared convention. The protocol digest in this record had a freeze defect; it is superseded by `pr4e-claims-1.3.0` with frozen payload digest `193e70ab…` (thresholds canonicalised to 6 significant digits after v1.2.0's full-precision leak was caught in CI) and an unchanged locked record digest `762ed383…`. Old artifacts and the digests quoted in this report are retained as the historical run; the superseding run is recorded in the [symmetry audit](2026-11-05-c1-symmetry-audit.md) §6 and ADR 0018.

**What C1 set out to test.** Can PhainoWeave decide, given an observation model and declared unknown degrees of freedom, whether a physical proposition qualifies as verifiable knowledge — with invariance as a necessary but not sufficient condition? This report answers that for one acoustic forward model, including the negative results.

## 1. L1 — symbolic proof (sympy; proof digest `b1aa32a5…`)

Convention: `t_obs = k_m · t_phys + β`; induced action `(f0, v, t0, b, c) → (f0/k_m, v, k_m t0 + β, k_m b, c)`. Group `G_clock = {(k,β): k>0}` with `(k2,β2)∘(k1,β1) = (k2k1, k2β1+β2)`.

| Theorem | Statement | Status |
|---|---|---|
| T1 | `G_clock` is a group; the action is a left action; domain `k>0` | **proven** |
| T2 | Forward observation preserved in the same observation coordinates | **proven** (identity simplifies to exactly 0; numeric self-check 8.9e-16) |
| T3 | `v` invariant under all of `G_clock` | **proven** |
| T4 | Composite `f0·b` invariant | **proven** |
| T5 | `b/f0` **not** invariant under rate (`→ k_m²·b/f0`) | **refuted** |
| T6–T8 | `t0`, `b`, `f0` not invariant under the group | **refuted** |
| T9 | Unknown sound speed admits `(v,b,c) → (λv, λb, λc)`; exact one-parameter degeneracy | **proven** |
| T10 | Deliberately wrong action fails (max relative difference 4.4e-2) | **pass** |
| T11 | Method and certificate rate conventions are reciprocal (`k_c = 1/k_m`) and define the same group | **proven** (all checks 0) |

A silent sympy symbol-identity bug was found and fixed during the work (T2 initially failed to simplify); the proof now hard-asserts every identity before emitting "proven".

## 2. L1 — independent numerical certificate (no acoustics imports)

Pure-numpy forward model, independent of the method package (static import check). Same observation grid, not a time-axis relabel.

| Generator | Preserves forward | Max observation mismatch | Tolerance | Failure class |
|---|---|---:|---:|---|
| clock_offset | true | 9.27e-16 | 1e-12 | none |
| clock_rate | true | 1.80e-15 | 1e-12 | none |

Group axioms (identity, composition, inverse, domain): all **true**. Per-claim numeric verdicts against the method protocol:

| Claim | Symbolic | Numeric | Max relative mismatch | Agrees |
|---|---|---|---:|---|
| `v` | invariant | invariant | 0 | yes |
| `f0·b` | invariant | invariant | 1.7e-16 | yes |
| `b/f0` | not invariant | not invariant | **4.94e-2** | yes |
| `t0` / `b` / `f0` | not invariant | not invariant | 0.30 / 2.5e-2 / 2.5e-2 | yes |

No symbolic/numeric disagreements remain after reconciliation. The earlier candidate `b/f0` was refuted by both sides; the invariant composite is **`f0·b`**. The certificate's numeric check also classifies grid-shift mismatches as implementation differences and rejects deliberately wrong generators (failure-class tests), so it can fail rather than smooth over a mismatch.

## 3. L2 — full-model identifiability: open, and that is the result

- Exact clock equivalences are handled (above).
- **Unknown sound speed** admits the exact scaling `(v,b,c) → (λv, λb, λc)`: rank 4, null-space dimension 1, alignment with the scaling direction `0.9999999999999992`. Direction and propagation are declared nuisances but not formalised.
- Therefore `v` and `f0·b` pass L1 but **fail the L2 gate**: they are capped at `supported_conditional`, and `supported_invariant` is disallowed for the whole protocol (`supported_invariant_allowed: false`). `b/f0` is `contradicted` by proof. `t0`, `b`, `f0` remain conditional claims under a nominal clock (with `b` additionally needing known `c`).
- This is the mechanism working as ruled: invariance did not auto-promote to knowledge.

## 4. L3 — PR-4e-L1 locked validation (protocol frozen first)

Protocol `pr4e-claims-1.1.0`, digest `2478226368…`; thresholds selected on a 475-trial development layer (different levels, seed base 40M); locked layer 500 trials / 20 conditions, seed base 41M, opened once; locked records deterministic across 1 and 2 workers.

Locked grid: zero control (25), nominal-SNR control (25), clock offset {−3, −0.5, +0.5, +3} s (100), clock rate {−25k, −10k, +10k, +25k} ppm (100), near-identity {β=±1e-3 s, ε=±10 ppm} (100), acceleration {0.2, 0.4} m/s² as **model misspecification** (50, never used for constant-velocity invariance), geometry {150, 600, 5000} m as **stress** (75), null (25).

| Claim | supported_conditional | undetermined | contradicted | supported_invariant |
|---|---:|---:|---:|---:|
| `v` | 290 | 210 | 0 | 0 |
| `f0·b` | 288 | 212 | 0 | 0 |
| `t0` | 292 | 208 | 0 | 0 |
| `b` | 285 | 215 | 0 | 0 |
| `f0` | 278 | 222 | 0 | 0 |
| `b/f0` | 0 | 0 | **500** (formal_counterexample) | 0 |

By stratum (`v` / `f0·b` support): control 25/25, nominal SNR 24/25, near-identity 98/100, clock rate 75/100, clock offset 68/100 / 66/100, acceleration **0/50**, geometry **0/75**, null **0/25**. The acceleration and geometry strata are handled honestly: misspecification and front-end chirp stress are refused, not accepted. Asymmetries inside clock strata (+3 s and −25 000 ppm undetermined via the frozen uncertainty gate while their mirrors are supported) are reported, not tuned.

## 5. Claim-level truth check (post-hoc; the method used no truth)

Evaluation against synthetic truth (`evaluation_only`), using the frozen operational tolerances:

| Claim | supported & correct | supported & wrong | undetermined & correct | undetermined & wrong | absolute-truth error | conditional-truth error (clock-nominal subset) |
|---|---:|---:|---:|---:|---:|---:|
| `v` | 290 | 0 | 136 | 74 | 0/290 = 0% | 0/49 |
| `f0·b` | 288 | 0 | 137 | 75 | 0/288 = 0% | 0/49 |
| `t0` | 196 | **96** | 104 | 104 | **96/292 = 32.9%** | **0/49** |
| `b` | 285 | 0 | 140 | 75 | 0/285 = 0% | 0/49 |
| `f0` | 228 | **50** | 122 | 100 | **50/278 = 18.0%** | **0/49** |

`0/49` is not a zero error rate: with zero observed failures in 49 clustered trials the one-sided 95% upper bound is about 6%, and the trials are not independent. It is reported as a count, not a rate. `b/f0` is a **`formal_counterexample`** (proof-decided), not an empirical contradiction.
| `b/f0` | — | — | — | — | proof-contradicted, not data-decided | — |

The dual-metric requirement is now visible in data: `t0` and `f0` false supports occur precisely where the nominal-clock assumption is violated; under the conditioning assumption they are 0. `v`, `f0·b` and `b` are never falsely supported — their invariance/conditioning survives the clock perturbations, which is the strongest positive C1 result.

## 6. Identifiability Boundary Report (derived; no new ontology object)

| Quantity | Proven property | L2 | Missing information | Observation that would break the equivalence |
|---|---|---|---|---|
| `v` | invariant under `G_clock` (T3) | open (T9 c-scaling) | independent sound-speed measurement; direction constraint | calibrated `c` and known propagation geometry |
| `f0·b` | invariant composite (T4) | open (T9) | independent `c` | calibrated `c` |
| `b/f0` | **refuted** (T5) | n/a | — | no observation restores its invariance; use `f0·b` |
| `t0` | not invariant under offset (T6) | conditional | absolute time anchor | GPS/PPS or equivalent two-anchor calibration |
| `b` | not invariant under rate (T7) | conditional | clock-rate calibration **and** `c` | rate calibration + sound speed |
| `f0` | not invariant under rate (T8) | conditional | clock-rate calibration | rate calibration |

## 7. Cross-environment result (A macOS arm64, B/C Linux x64/arm64)

Claim statuses are **identical on all three environments: 3000/3000 claim-trial decisions (6 claims × 500 trials)**, for every pair A↔B, A↔C, B↔C. This is the strongest reproducibility result the project has produced at claim level.

**One defect found and reported:** the "frozen" protocol digest differs across environments (`2478226368…` locally, `4823dac1…`/`6b87fd81…` in CI) because the protocol file embeds a certificate-evidence block whose presence/content varies by environment (CI did not run the certificate workflow before writing the protocol). The *scientific content* — claims, thresholds, gate, group, statuses — is identical. Fix required before freezing for E1: separate the frozen protocol payload from environment/evidence attachments, and digest only the frozen payload. This is a C1-C deliverable defect, not a claim-status difference.

## 8. Answer to the C1 question

The gate mechanism works on one forward model: it **refuted** a candidate invariant (`b/f0`), **proved** the correct composite (`f0·b`), **demoted** invariant candidates whose full-model identifiability is open (`v`, `f0·b`), **refused** `supported_invariant` entirely (0/5006), **produced a boundary report** naming the missing observation for each quantity, and kept claim-level decisions identical across three environments. The symbolic engine and the nuisance formalisation are model-specific; the gate structure (L1→L2→L3, scoped group, gated status, boundary output) is the candidate for the World Ontology's general claim semantics.

It did not prove `v` or `b/f0` identifiable, and it did not make any physical claim supported: that would require an independent sound-speed measurement and, for `t0`, an absolute time reference. Those are now specified measurements, not open questions.

## 9. Limitations

1. L2 is open for `v` and `f0·b` (sound-speed degeneracy); direction/propagation nuisances are declared but not formalised.
2. Protocol digest instability across environments (above) must be fixed before the protocol is called frozen.
3. The certificate originally did not cover `f0·b`; the reconciled run now does (1.7e-16 mismatch), but the method protocol's embedded evidence block still references the earlier certificate digest.
4. Extreme clock levels (+3 s, −25 000 ppm) and geometry stress are conservatively undetermined — a coverage cost, not a detector failure.
5. Conditional claims under violated clock assumptions are `supported_conditional` and truth-wrong; the dual metrics expose this rather than hiding it.
6. Single forward model; no real recordings; no risk–coverage; E1 field work remains gated on venue, consent, calibration and legal review.
