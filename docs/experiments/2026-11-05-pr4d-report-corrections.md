# PR-4d report corrections

**Status:** corrections to a frozen report · 2026-11-05 · **Frozen source:** [PR-4d adequacy validation](2026-11-05-pr4d-adequacy-validation.md) (not edited) · **Authority:** [ADR 0016](../decisions/0016-identifiable-claims.md)

The PR-4d report is frozen as a historical record. Three presentation/statistical problems are corrected here rather than by editing it.

## 1. Strict-policy false-accept rate is undefined, not 0%

The frozen report shows "FA 0%" for the strict rule. With `accepted = 0`, the false-accept ratio has no denominator and is **undefined**.

Correct statement: **zero false-accept count, zero accepted claims, false-accept ratio undefined, valid retention 0%**. Zero accepted is not evidence of reliability; it is evidence that the claim type was not supported.

## 2. Sample-flow table for the locked layer

Family sizes are not error counts. Locked layer (`n = 1420`; 800 trials within truth tolerance, 620 outside):

| Family | n | Old accepted | Old correct | Old wrong | New strict supported | New conditional accepted | Conditional wrong |
|---|---:|---:|---:|---:|---:|---:|---:|
| acceleration | 240 | 240 | 0 | 240 | 0 | 0 | 0 |
| clock_offset | 200 | 200 | 80 | 120 | 0 | 200 | 120 |
| clock_rate | 160 | 160 | 80 | 80 | 0 | 160 | 80 |
| geometry | 270 | 240 | 240 | 0 | 0 | 107 | 0 |
| noise | 200 | 150 | 150 | 0 | 0 | 150 | 0 |
| window | 100 | 100 | 100 | 0 | 0 | 100 | 0 |
| within_tolerance | 150 | 150 | 150 | 0 | 0 | 150 | 0 |
| null | 100 | 0 | 0 | 0 | 0 | 0 | 0 |
| **total** | **1420** | **1240** | **800** | **440** | **0** | **867** | **200** |

The 240/200/160 family sizes are the locked grid; the locked old-rule false accepts are 440. Both numbers are correct and measure different things.

## 3. Conditional claim: two error rates, not one

The frozen report's 23.1% (200/867) is **absolute-truth error**: conditional-supported outputs compared against physical truth.

The complementary metric is **conditional-truth error**, restricted to the population where the conditioning assumption actually holds. In the locked layer the conditional rule accepts 507 clock-nominal trials (geometry 107 + noise 150 + window 100 + within_tolerance 150) and is wrong on **0** of them.

| Metric | Definition | Locked value |
|---|---|---|
| Absolute-truth error | wrong / conditional-supported, all trials | 200/867 = 23.1% |
| Conditional-truth error | wrong / conditional-supported among trials where `α = 1, β = 0` within tolerance | 0/507 = 0% |

The gap is the price of the assumption. PR-4e must fix the evaluation object (claim set, allowed transformations, conditioning population) before comparing rules by risk.

## 4. What else stands unchanged

The frozen report's measured findings stand: 240/240 acceleration rejected; 360/360 equivalence undetermined under strict; 74/240 geometry false rejections; phase-correlation and ACF test power statements; cross-environment 1419/1420 epistemic agreement. The corrections above change presentation and metric definition only.

## 5. Clock-rate parameter action was misstated

The frozen PR-4d report's clock-rate action (`f0' = k f0, b' = k b, t0' = t0/k`) does **not** preserve the forward observation: measured max relative mismatch 2.5e-2, even allowing a time-axis map. The action derived from the same forward model under `t_obs = k t_phys + β` is

```
f0' = f0/k,  v' = v,  t0' = k t0 + β,  b' = k b
```

which preserves the observation to 8.9e-16 and gives the invariants `f0·b` (preserved) and `b/f0 → k²·b/f0` (not preserved). Under the reciprocal certificate convention `t_obs = t_phys/k_c + β` the action is `(k_c f0, v, β+t0/k_c, b/k_c)`, identical after `k_c = 1/k`.

The frozen report's **substantive conclusion stands** — a clock rate is an exact reparameterisation and produces observational equivalence. The written action was wrong and is corrected here; the C1 conclusions T4 (`f0·b` invariant) and T5 (`b/f0` refuted) are confirmed by the audit, not overturned. Full derivation and numeric evidence: [symmetry-convention audit](2026-11-05-c1-symmetry-audit.md).
