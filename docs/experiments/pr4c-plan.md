# PR-4c plan — Convergence robustness and decision stability

**Status:** in progress · 2026-11-05 · **Authority:** [ADR 0014](../decisions/0014-failure-taxonomy-and-decision-stability.md) · **Evidence:** [three-environment report](2026-11-05-cross-platform-e0.md) §9

**Success criterion (per the founder's ruling).** A convergence rule with clear numerical meaning that is stable across the three pinned environments and useful on independent data — **not** CI green, and **not** making trial 57 agree by loosening conditions. The original E0 records stay frozen; the hardened rule produces a separate `E0-hardened` version.

## Checklist

| # | Item | State | Evidence / notes |
|---|---|---|---|
| 1 | Diagnose trial 57: objective and (normalized) gradient at the same parameter vectors on A/B/C, termination path, iteration trajectory, Jacobian/FD method, environment | **Done** | [validation report](2026-11-05-pr4c-hardened-validation.md) §1: objective agrees ~1e-15 and normalized gradient to printing precision at the same parameter point on every machine; difference is the stopping point amplified by curvature |
| 2 | Unify Python patch and numeric dependencies across A/B/C | Partial | CI pins Python 3.14.9 + numpy 2.4.4 on B/C; local A is 3.14.0 and must be aligned or labelled as a distinct environment |
| 3 | Implement parameter/residual scale normalization in convergence | **Done** | `fit_hardened.py`: z = θ/s (s = 500 Hz, 250 m/s, 20 s, 3000 m), σ_f-normalized residuals, curvature-normalized gradient statistic (τ=1e-8 in measured band) |
| 4 | Separate `optimization_converged`, `parameter_identifiable`, `model_adequate`, `decision_status` | **Done** | four statuses in `e0-hardened`; operational gate labelled as such |
| 5 | Stability confirmation + formal `indeterminate` | **Done** | ≥3 consecutive iterations; budget/stall → indeterminate; trial 57 now accepted on all three environments |
| 6 | Validate on data not used to choose thresholds, across A/B/C | **Partial** | equivalence measured: 2499/2500 formal, 2000/2000 accepted set, accepted params ≤3.8e-9; utility exploratory and **failing** (30% false-accept on truth). Independent split and pre-declared utility bounds still missing |
| 7 | Keep E0 frozen; produce independent hardened version/report | **Done** | [validation report](2026-11-05-pr4c-hardened-validation.md); E0 digest `674213d9…` untouched; hardened digests recorded per environment |
| 8 | Enable R1-N/R1-D CI gates only after validation | **Blocked** | R1-D stays off: equivalence is 2499/2500 and utility fails; see report §6 for the four remaining requirements |

## Diagnostic design (item 1)

For each environment, `phaino_acoustics.diagnose` reproduces trial 57 and records:

- final parameters; objective; raw gradient; scale-normalized gradient; iterations; f/g evaluation counts; termination reason; last five iterations (objective and normalized step);
- Jacobian method (analytic/numeric) and finite-difference step if used;
- objective and gradient at every parameter vector in [`pr4c/trial57-params.json`](pr4c/trial57-params.json) — this is the cross-evaluation: each environment evaluates the macOS, x86_64 and arm64 final points.

Interpretation rule, fixed *before* looking at the results:

| Observation | Conclusion |
|---|---|
| Same parameters give the same objective/gradient across environments (within a declared tolerance), but termination differs | The difference is in the stopping logic or iteration path, not the derivative — convergence rule is the fix |
| Same parameters give materially different gradients (beyond a declared tolerance) | Derivative/numeric implementation is the first suspect; fix that before touching thresholds |
| Both differ | Both must be addressed; report separately |

Tolerances for "same gradient" are declared in the diagnostic report from the scale-normalized gradient norm of the reference, not chosen after seeing the disagreement.

## Utility half (item 6)

The hardened rule is judged on two axes:

1. **Equivalence** — formal classification (`accepted | rejected | indeterminate`) identical on the same test set in A/B/C.
2. **Utility** — on trials not used to tune the rule: false-accept rate (accepted but wrong beyond tolerance), retained-valid fraction (correct trials still accepted), and indeterminate rate, each against pre-declared bounds. An all-indeterminate rule passes axis 1 and fails axis 2 by definition.

## Non-goals

No change to E0's original report, digest or preregistered criteria. No threshold change intended to make a specific trial agree. No optimizer rewrite before the diagnosis is complete.
