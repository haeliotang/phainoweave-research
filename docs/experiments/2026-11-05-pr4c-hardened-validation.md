# PR-4c — trial-57 diagnosis and hardened-rule three-environment validation

**Status:** measured; convergence stability improved, decision utility not established · 2026-11-05 · **Authority:** [ADR 0014](../decisions/0014-failure-taxonomy-and-decision-stability.md), [ADR 0013](../decisions/0013-reproducibility-contract-v2.md) · **Plan:** [pr4c-plan.md](pr4c-plan.md) · **Frozen E0:** [2026-11-04-e0-synthetic-doppler.md](2026-11-04-e0-synthetic-doppler.md)

**What this report is.** The diagnostic the ruling required before any rule change, the hardened convergence rule v1 as a separate version, and its validation on three pinned environments. E0's original code, artifact and preregistered criteria are untouched (`records_sha256 674213d9…`); the hardened sweep is a new artifact (`e0-hardened`). Nothing here claims a reproduction level beyond what is measured.

## 1. Diagnostic: where the trial-57 difference actually lives

`phaino_acoustics.diagnose` reproduces the frozen trial exactly (condition `snr_+5dB`, trial 57, seed 20264161; same generator, front end, and an instrumented LM verified bit-identical to `fit_doppler` on the reference machine) and cross-evaluates the objective and gradients at the three platforms' final parameter points.

**Same parameters, different machines** (each environment evaluating all three parameter points; values shown are the curvature-normalized gradient ∞-norm / objective):

| Evaluator | macOS-arm64 point | Linux-x64 point | Linux-arm64 point |
|---|---|---|---|
| A macOS arm64 | 2.88e-16 / 364.4749818415674 | 3.22e-11 / 364.4749818415654 | 4.98e-12 / 364.4749818415709 |
| B Linux x64 | 2.86e-16 / 364.4749818415679 | 3.22e-11 / 364.4749818415658 | 4.98e-12 / 364.4749818415715 |
| C Linux arm64 | 2.88e-16 / 364.4749818415672 | 3.22e-11 / 364.4749818415655 | 4.98e-12 / 364.4749818415710 |

The objective agrees to ~1e-15 relative and the normalized gradient to printing precision **at the same parameter point, on every machine**. The platforms' own fits stop at points ~1e-9 (relative) apart, and the frozen statistic `‖Jᵀr‖₂` amplifies that separation by four orders of magnitude because the problem is curved: 2.97e-12 → 1.63e-7 → 1.06e-6 at the macOS / Linux-arm64 / Linux-x64 stopping points, evaluated on any machine.

**Conclusion.** The difference is not in the derivative or the objective; it is in *where the optimizer stops*, amplified by a curvature-dependent, dimensionally inconsistent statistic whose threshold sat inside that amplified boundary. The appropriate fix is a scale- and curvature-aware convergence criterion, exactly as ruled — not a threshold change and not a derivative rewrite.

## 2. Hardened rule v1 (separate version; frozen E0 untouched)

`fit_hardened.py` / `experiment_hardened.py` — a new estimator, not an edit:

| Element | Definition |
|---|---|
| Declared scales | `s = (f0 500 Hz, v 250 m/s, t0 20 s, b 3000 m)`; `z = θ / s` |
| Residual normalization | `σ_f² = SSE/(n−4)`; curvature ratio uses the same normalization (it cancels) |
| Gradient statistic (declared refinement) | maximum predicted dimensionless parameter step in the local Gauss–Newton metric, `max_i |g_i| / (s_i (JᵀJ)_ii)`; threshold `1e-8`, measured band: converged floor 8.98e-10, nearest unconfirmed stall 1.12e-8, classification invariant for τ ∈ [1e-9, 1e-7] |
| Stability confirmation | ≥3 consecutive iterations satisfying **all** of: normalized gradient ≤ 1e-8, relative objective change ≤ 1e-10, normalized parameter step ≤ 1e-8 (two iterations explicitly insufficient) |
| Budget | 200 iterations per start; fixed-point verification at damping levels 1e-6, 1e-3, 1e0 |
| Outcome | budget exhausted without confirmation → `optimization_status = indeterminate`, never forced accepted/rejected |
| Statuses (separate) | `optimization_converged`, `parameter_identifiable` (operational gate: worst_rel_se ≤ 1e-2, condition number ≤ 1e4, finite positive parameters — not structural proof), `model_adequate` (improvement ratio ≥ 0.5), `decision_status` (precedence: optimization indeterminate/failed → indeterminate; model inadequate → rejected; unidentifiable → indeterminate; else accepted) |

Single-machine results (reference): 2500 trials, deterministic across 1 and 8 workers, `hardened_records_sha256 ed1f2f71…`; 2000 accepted / 499 indeterminate / 1 rejected. Trial 57 is accepted with a ≥250× margin at all three final points; the frozen rule's instability does not recur.

## 3. Three-environment validation of the hardened rule

Pinned environments as in the [three-environment report](2026-11-05-cross-platform-e0.md) §9; CI runs the hardened sweep on `ubuntu-24.04` and `ubuntu-24.04-arm` with Python 3.14.9 + numpy 2.4.4, and locally on macOS arm64 (Python 3.14.0 — still a patch-version confound, see §6).

| | A macOS arm64 | B Linux x64 | C Linux arm64 |
|---|---|---|---|
| `hardened_records_sha256` | `ed1f2f71…` | `724d75c7…` | `34a03ef5…` |
| decision accepted / indeterminate / rejected | 2000 / 499 / 1 | 2000 / 498 / 2 | 2000 / 499 / 1 |
| optimization converged / indeterminate | 2401 / 99 | 2402 / 98 | 2401 / 99 |

**Per-trial comparison (all 2500 trials):**

| Pair | decision_status diffs | optimization_status diffs | identifiable diffs | model_adequate diffs | accepted params max rel diff |
|---|---|---|---|---|---|
| A ↔ B | 1 | 1 | 0 | 0 | 2.32e-9 |
| A ↔ C | **0** | 0 | 0 | 0 | 3.80e-9 |
| B ↔ C | 1 | 1 | 0 | 0 | 3.80e-9 |

- **Trial 57 is now classified identically (accepted) on all three environments** — the convergence fix works.
- **The accepted set is identical on all three: 2000/2000 trials**, and accepted parameters agree to ≤3.8e-9.
- **One residual difference remains**, on a *null* trial (`null_noise_only`, trial 68): improvement ratio 0.00285 on every environment (far from the 0.5 adequacy threshold), but A/C land in `optimization_indeterminate` while B converges and is then `rejected` as model-inadequate. Both are non-accepting states; the difference is in the stall/budget path on a signal-free trial. Formal decision equivalence is therefore **2499/2500, not 2500/2500**.

## 4. Decision utility on truth (exploratory — thresholds were not pre-declared)

Using the synthetic truth and the frozen E0 parameter tolerances (`f0` 1%, `v` 2%, `t0` 0.25 s, `b` 5%), identical on all three environments:

| Measure | Value |
|---|---|
| Accepted trials | 2000 |
| … accepted **and** within truth tolerance | 1400 |
| … accepted but **outside** truth tolerance | 600 (**false-accept rate 30%**) |
| Valid trials (within truth tolerance) | 1625 |
| … retained as accepted | 1400 (86%) |
| … classified indeterminate (lost) | 225 (14%) |
| Accepted-set equivalence across environments | 2000/2000 identical |

The 600 false accepts come from accelerating, clock-offset and clock-rate conditions: the fit explains the observation (high variance explained, converged, identifiable), yet the parameters are wrong beyond tolerance. **This is the project's central distinction made quantitative: "the estimator converged" ≠ "we know what happened".** The hardened rule is a better *convergence* rule; it is **not yet a valid scientific decision rule**, because `model_adequate` = variance-explained accepts a misspecified model.

This analysis is labeled **exploratory**: it was computed after seeing the results, and it must not be used as a pass criterion. The utility half of ADR 0014 requires pre-declared bounds on independent data.

## 5. Verdict against the PR-4c checklist

| Item | State |
|---|---|
| 1 Diagnose trial 57 | **Done** — mechanism identified; derivative/objective consistent at fixed parameters |
| 2 Unify environments | Partial — B/C pinned to Python 3.14.9 + numpy 2.4.4; local A is 3.14.0 |
| 3 Scale/residual normalization | **Done** (curvature-normalized statistic, declared scales) |
| 4 Separate convergence/identifiability/model/decsion | **Done** (four statuses; operational gate labelled) |
| 5 Stability confirmation + indeterminate | **Done** (3 consecutive, budget, stall path) |
| 6 Independent-data validation (equivalence + utility) | **Not met** — equivalence 2499/2500; utility 30% false-accept on truth, exploratory only |
| 7 Keep E0 frozen, separate hardened version | **Done** — E0 digest untouched, hardened artifact separate |
| 8 Enable R1 gates | **Not done** — R1-D stays off; hardened decisions are not R1-D equivalence |

**Honest summary:** PR-4c fixed the *numerical* instability that produced the trial-57 cross-platform flip, and it exposed the larger problem underneath: the acceptance decision is not scientifically valid even when it is numerically stable. Decision equivalence (2499/2500) is close but not exact; decision utility fails. The R1-D gate remains off.

## 6. What remains before the hardened rule can be accepted

1. **Align Python patch on A** (3.14.0 → 3.14.9 via a pinned environment or container) so cross-environment differences cannot be attributed to the interpreter.
2. **Fix the residual stall-path difference** on null trials: the stall/budget path must be classified by the same stability semantics as convergence (a null trial must not change status class between environments). Then formal decision equivalence can be 2500/2500.
3. **Replace variance-explained adequacy** with a model-form test (residual whiteness/autocorrelation, noise-model consistency). Variance explained cannot distinguish "the model is right" from "a biased model still explains most of the variance" — the 600 false accepts are the measured consequence.
4. **Pre-declare the utility bounds and evaluate on an independent split** (tuning vs validation trials; E1's real data with truth). Until then the 30% figure is a diagnostic, not an acceptance result.
5. Only after 1–4: freeze the protocol, enable R1-D, and describe the hardened rule as scientifically useful rather than merely stable.

## 7. Amendment — hardened rule v1.1: stalled-model rejection (2026-11-07)

The residual null-trial stall-path difference identified in §3 is addressed in hardened rule **v1.1**, without changing frozen E0.

**Rule change.** If the optimizer ends `indeterminate` **and** the fitted model's improvement ratio is below `0.25` (half of the declared `0.5` adequacy floor), the decision is `rejected` with reason `model_inadequate`; the stall itself remains visible in `optimization_status` / `optimization_reason`. A stalled fit that is not decisively inadequate remains `indeterminate`; a numerical `failed` remains `indeterminate`. The new precedence is documented in `python/phaino_acoustics/fit_hardened.py`.

**Why.** On the null trial `null_noise_only` / trial 68, one environment stalled before the fixed-point certificate while another converged and was then rejected as model-inadequate. Both fits explain <0.3% of the IF-track variance, so the decision is decisively "reject the model"; classifying one side as indefinite was a stall-path artifact, not a scientific disagreement.

**Measured result on the same E0 grid (hardened v1.1):**

| Environment | `hardened_records_sha256` | decision_status diffs vs host | optimization_status diffs vs host |
|---|---|---:|---:|
| host macOS arm64 | `13bd3382…` | baseline | baseline |
| Linux arm64 container | `74d34371…` | **0 / 2500** | 1 / 2500 |
| Linux amd64 container | `34807b49…` | **0 / 2500** | 1 / 2500 |

- Trial 2456 / seed `20285160` is `rejected` / `model_inadequate` (stalled optimization diagnostic) on host, arm64 and amd64.
- Trial 68 remains a single **optimization-status diagnostic** difference (`indeterminate` vs `converged`), but both environments decide `rejected`; formal **decision equivalence is 2500/2500** for both pairs.
- Frozen E0 (`records_sha256 674213d9…`) is untouched. R1-D for frozen E0 remains off on amd64; this amendment applies to the separate hardened estimator and must not be read as repairing frozen E0 retroactively.

Evidence: `.repro/hardened-host-v11/`, `.repro/hardened-container-v11/`, `.repro/hardened-amd64-v11/` (git-ignored).
