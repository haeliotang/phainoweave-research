# C1 symmetry-convention audit

**Status:** P0 audit closed; f0·b confirmed under the declared convention; PR-4d action corrected by erratum; protocol-freeze defect fixed in `pr4e-claims-1.2.0` · 2026-11-05 · **Authority:** [ADR 0018](../decisions/0018-symmetry-convention-audit.md) · **Related:** [C1 report](2026-11-05-c1-identifiability.md), [PR-4d corrections](2026-11-05-pr4d-report-corrections.md)

**Why this audit exists.** Two rounds wrote different clock-rate parameter actions. Only one can be a symmetry of the observation; the difference decides whether `b/f0` or `f0·b` is the invariant. This audit fixes the forward model as the single basis and recomputes the action from it.

## 1. Forward model and the two coordinate conventions

Canonical narrowband forward model (stationary receiver, straight line, no propagation delay):

```
F(t; f0,v,t0,b,c) = f0 / (1 + v²·(t−t0) / (c·√(b² + v²·(t−t0)²)))
```

Two observation-time conventions, both in use:

| | Time map | Observed quantity |
|---|---|---|
| **M (method/C1)** | `t_obs = k·t_phys + β` | `(1/k)·F((t_obs−β)/k; θ)` |
| **C (certificate)** | `t_obs = t_phys/k_c + β` | `k_c·F(k_c·(t_obs−β); θ)` |

They are the same convention with `k_c = 1/k`. A report that mixes them without mapping is wrong; a report that states one and maps to the other is fine.

## 2. Derived actions and forward-preservation test

Applying the change of coordinates and matching the canonical form gives:

| Convention | f0 | v | t0 | b | Max relative forward mismatch | f0·b | b/f0 |
|---|---|---|---|---|---|---|---|
| M | `f0/k` | `v` | `k·t0 + β` | `k·b` | **8.9e-16** | invariant | `k²·b/f0` (not invariant) |
| C | `k_c·f0` | `v` | `β + t0/k_c` | `b/k_c` | **8.5e-16** | invariant | `k_c^{-2}·b/f0` (not invariant; equivalent to the M row under `k_c = 1/k_m`) |

Both preserve the observation to machine precision. `v` is invariant under both. `f0·b` is the invariant composite; `b/f0` is not. The two rows are the same statement: `k_c^{-2} = k_m²` under `k_c = 1/k_m`. This conversion is enforced by an automated test (ADR 0019 §B), not by table-reading.

## 3. The PR-4d formula is not a symmetry

The frozen PR-4d report states `f0' = k f0, b' = k b, t0' = t0/k`. Tested as a parameter substitution against the same observation (even allowing a time-axis map `t_obs = t_phys/k`):

| Candidate action | Max relative mismatch vs forward output |
|---|---|
| `(f0/k, v, k t0+β, k b)` — derived (M) | 8.9e-16 |
| `(k_c f0, v, β+t0/k_c, b/k_c)` — derived (C) | 8.5e-16 |
| `(k f0, v, t0/k, k b)` — PR-4d, fixed `t` | **2.5e-2** |
| same PR-4d triple + `t_obs = t_phys/k` | **2.6e-2** |

The PR-4d formula fails forward preservation by ~2.5%, so it cannot be a generator of the clock symmetry group. It arose from conflating the frequency scaling with the induced parameter action. **Its substantive conclusion stands** — a clock rate is an exact reparameterisation and creates observational equivalence — but the written action was wrong. Corrected by [erratum](2026-11-05-pr4d-report-corrections.md).

Consequence: C1's T4/T5 are **confirmed**, not overturned. `f0·b` is invariant; `b/f0` is refuted (becomes `k²·b/f0`). The `b/f0` verdict is labelled **`formal_counterexample`**, distinct from an empirical contradiction: it is decided by proof, not by fitting evidence. This was only acceptable because the audit re-derived both from the forward model rather than trusting either memo.

## 4. Invariance vs equivariance

Clock changes act on the **observation time coordinate**. The forward curve is *equivariant*: `F_obs(t_obs; θ, g) = F_nom(t_obs; ρ(g)θ)`. A physical quantity is *invariant* only when `φ(ρ(g)θ) = φ(θ)` for every `g` in the proven group. The audit checks both: forward preservation (equivariance of the observation) and claim-value preservation (invariance). A claim may not cite one as the other.

## 5. Group axioms and coverage

Identity `(1,0)`, closure `(k2,β2)∘(k1,β1)=(k2k1, k2β1+β2)`, inverse `(1/k,−β/k)`, domain `k>0` (k≤0 invalid: b'≤0 or time reversal). The certificate reports group axioms and generator coverage; a missing/untested declared generator makes L1 incomplete and withholds promotion. Negative contract tests: wrong certificate, omitted generator, contradicted nuisance.

## 6. Frozen-protocol digest defect (P0-2)

C1's protocol digest varied across environments: `2478226368…` locally, `4823dac1…` and `6b87fd81…` in CI. Cause: the certificate-evidence block (and environment metadata) was inside the digested payload, and CI did not run the certificate before writing the protocol.

Fix in `pr4e-claims-1.2.0` (implemented and verified):

- `frozen_payload` = claims, generators/actions, conventions, thresholds, gate rules, precedence, model declaration → canonicalised and digested as `protocol_digest`.
- evidence (certificate digests/verdicts), environment, timestamps, development statistics → attached outside, digested separately as `evidence_digest`.
- **First attempt (v1.2.0) was insufficient and the CI check caught it.** The 1.2.0 frozen payload still contained full-precision development-selected thresholds (99th percentile of a BLAS/numpy-dependent uncertainty distribution); local vs CI x64 vs CI arm64 differed by ~1e-15 relative, giving three different "frozen" digests (`7022c377…`, `98baf8a5…`, `e72c8a4e…`). This was found by downloading the CI protocol artifacts, not by the local stability test, which had only varied evidence.
- **Fix (v1.3.0):** thresholds in the frozen payload are canonicalised to 6 significant digits (`threshold_precision` declared in the payload); full-precision values and development statistics live in evidence. All three observed values map to the same canonical threshold (e.g. `1.59622e-05`). **Frozen digest: `193e70ab42cd1c953d89c735ee6fa4c19bc7aed98d11e2af8cba751c9191e52f`**, identical across local default/1-thread/8-thread runs and (to be confirmed by CI) across architectures; evidence digests vary by design (`ae02af79…` default).
- **No decision moved:** locked records `762ed383…` and development `33feee9e…` are unchanged from 1.1.0/1.2.0, so every claim decision is identical; only the frozen digest representation changed. A jitter test enforces that a ±1e-14 relative change in a selected threshold does not change the digest, while a 1e-2 change does; a scan test fails if a future fit-derived float enters the frozen payload.
- **Claim results did not move:** locked records digest `762ed383ab3d5e81423fbf7bb6de54459b1731b5fa3071c1f1892df7837358d3` and development `33feee9e…` are identical to the 1.1.0 run; all claim counts unchanged (v 290/210, f0·b 288/212, t0 292/208, b 285/215, f0 278/222, b/f0 500 contradicted, supported_invariant 0).
- Negative contract tests now cover: certificate symbolic/numeric conflict (blocking, withheld), missing required generator (`incomplete_group`, all evaluable claims `undetermined`), contradicted nuisance probe (withholds exactly v, f0·b, b).
- Old C1 artifacts and digests are retained as historical records with the defect note; the new locked run is the operational reference.

## 7. Effect on earlier conclusions

| Earlier statement | Audit outcome |
|---|---|
| PR-4d: clock rate creates exact observational equivalence | **stands** |
| PR-4d written action `(k f0, v, t0/k, k b)` | **wrong** (fails forward preservation); corrected |
| C1 T4: `f0·b` invariant | **confirmed** under the declared convention |
| C1 T5: `b/f0` refuted | **confirmed** (`k²·b/f0`) |
| C1: `v` invariant under `G_clock` | **confirmed** (L2 still open due to sound-speed scaling) |
| C1: zero `supported_invariant` | **unchanged** |
| R1-D (frozen protocol) | **unchanged, still not passed** |
| E1 may use unresolved L1 math | **no** — this audit and the digest fix are E1 prerequisites |

## 8. Limits of this audit

- One forward model, one geometry class (straight line, constant velocity, no propagation delay/multipath); the derivation is analytic under those assumptions only.
- No formal proof assistant was used; the symbolic and numeric audits are independent implementations, but a machine-checked proof remains future work.
- Generator coverage is checked against the protocol's declarations; an undeclared generator can still exist in nature (that is what N_physical and the boundary report are for).
- The corrected `pr4e-claims-1.2.0` rerun is a new protocol version; old results are historical, not retroactively edited.
