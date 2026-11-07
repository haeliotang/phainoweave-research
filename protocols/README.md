# Comparison protocols

A protocol is the **data** that defines how two experiment artifacts are compared. Code
contains no tolerances: `python/phaino_verify` applies whatever `abs_tol` and `rel_tol`
the protocol file supplies. A protocol is strict JSON: unknown keys, malformed paths,
non-finite tolerances, and incomplete structure rules are rejected before comparison.

The first protocol family targets E0 (`docs/experiments/2026-11-04-e0-synthetic-doppler.md`):
2500 trial records (25 conditions × 100 trials) plus per-condition aggregates.

## Reproduction levels

**R0 — execution.** Both artifacts are strict JSON objects (no duplicate keys, no
NaN/Infinity); both contain the required top-level structure; every condition and every
`(condition, trial)` pair appears exactly once; the condition set and, when the protocol
requires it, the condition order match. R0 is a precondition, never a reproduction claim.

**R1 — numerical equivalence.** Every field is classified by the protocol as exact,
numeric, or ignored. Exact fields (ids, condition keys, counts, success/abstain decisions,
enums, version strings) must match exactly. Numeric fields pass when

```
|reference - candidate| <= abs_tol + rel_tol * max(|reference|, |candidate|)
```

for every matched value across every trial and every aggregate. Missing/extra/duplicate
trials, type changes, and NaN/Infinity are R1 failures (or unknown when structure is
insufficient). Per-field maximum absolute and relative errors and their worst location are
reported.

**R2 — bitwise identity.** Both artifacts are copied, only the protocol's `ignored_fields`
are removed, both are canonicalized with PCJ-0 (ADR 0006), and their SHA-256 digests are
compared. Equal digests mean R2. Raw on-disk file SHA-256 is always reported separately,
including when an artifact is gzip-compressed.

Classification follows only those levels:

| Classification | Meaning |
|---|---|
| `exact` | R1 passes and R2 passes |
| `numerically_equivalent` | R1 passes, R2 fails |
| `mismatch` | R1 fails |
| `unknown` | R0 fails: missing/extra/duplicate trials, malformed JSON, non-finite values, condition order change when the protocol requires order |

`numerically_equivalent` is never presented as R2; R0 alone is never a scientific
reproduction.

## Protocol path language

```
experiment                       top-level field
config.jobs                      nested field
trials[].b1.params.f0            every element of the trials list
trials[].b1.params.*             every key of that object
conditions[].success.rate        aggregate field
```

`[]` expands a list; `*` expands a mapping's keys (or a list's indexes). When patterns
overlap, the more specific path wins; the last-resort `"*"` numeric entry in the example
protocol gives unlisted numeric leaves the same placeholder tolerance.

## Ignored fields

Only fields that are not part of the scientific claim may be ignored: wall-clock
`generated_at_utc`, `elapsed_s`, `config.jobs`, the records digest (a hash of exact bytes,
redundant when every trial is compared), and environment runtime strings. Ignored fields
are reported as `ignored_fields_found`; an ignored field may never be a measured value,
decision, id, count, or version.

## Tolerances are placeholders until measured

`e0-cross-platform.example.json` is marked `"tolerance_status": "example_only"` and its
note says so explicitly. **The final tolerances must be filled from the measured
cross-platform report, never chosen to make a comparison pass.** The Lead fills them at the
`numeric_fields` entries of a measured copy of the protocol (the example's values
`abs_tol: 1e-06`, `rel_tol: 1e-09` are placeholders, not a claim), records the report
digest and the two platform artifact digests alongside the protocol, and only then may a
`numerically_equivalent` result be cited as a cross-platform reproduction. A comparison
that requires `R2` across platforms is expected to fail and must not be forced.

## CLI

```
PYTHONPATH=python python3 -m phaino_verify.compare \
  <reference.json[.gz]> <candidate.json[.gz]> \
  --protocol protocols/e0-cross-platform.example.json \
  --report out/report.json \
  [--require R1|R2]
```

- gzip is detected by the magic bytes `1f 8b`.
- `--require` defaults to `R1`.
- Exit codes: `0` required level passes; `1` required level fails; `2` unknown/insufficient
  structure (the report is still written); `3` usage or protocol error.
- The report is deterministic JSON with sorted keys: protocol digest, both artifacts'
  raw/decoded/canonical digests, per-level booleans, classification, per-field stats
  (`field`, `max_abs`, `max_rel`, `violations`, `worst_location`), violations,
  decision-instability entries, ignored fields found, and `reasons` for `unknown`.

## Decision instability

A decision-instability entry means: a decision field changed while every numeric field for
that trial stayed within the protocol tolerance. This is the failure mode where a numerical
difference below the stated tolerance silently flips a success/abstain or
converged/not-converged decision. The entry names the trial and the decision field; the
classification still follows R1/R2, so a flipped exact decision is a `mismatch` even when
the numeric parameters are equivalent.

## Measured cross-platform result (2026-11-05)

The first comparison of E0 artifacts across macOS arm64 and Linux x86_64 is recorded in [`docs/experiments/2026-11-05-cross-platform-e0.md`](../docs/experiments/2026-11-05-cross-platform-e0.md). R0 passes, R2 fails, and **R1 is not established**: parameter differences are ~1e-9 where identifiable, unbounded where not, and 1/2500 convergence decisions flips. The measured bounds in that report are proposals; tolerances here remain unfrozen until PR-4b adds identifiability-conditioned scope and a decision-margin rule, and the protocol is frozen after a second platform pair. `example_only` must never be cited as a reproduction.

## Contract v2 — PR-4b field classes and split R1

`e0-cross-platform.v2.json` implements contract v2. It is a **measured draft**
(`tolerance_status: "measured_draft_not_frozen"`), not a frozen protocol. The four classes
are declared by the protocol and never inferred from cross-machine agreement:

| Class | Fields | Rule |
|---|---|---|
| `A_discrete_identity` | ids, condition/trial keys, seeds, `n`, version/config strings, model/enum values | exact |
| `B_identifiable_numeric` | `f0`, `v`, `t0`, `b` and their `rel`/`rel_abs`, residual RMS/SSE, improvement ratio, front-end RMS | abs+rel tolerance, applied only when the reference trial is identifiable; otherwise reported not-applicable, never as numeric mismatch |
| `C_unidentifiable_diagnostic` | standard errors, condition number, correlations, worst-direction components, `worst_rel_se`, `grad_norm`, iteration/start diagnostics | semantic comparison (both null, sign agreement, order-of-magnitude class within `decades`); differences are diagnostics, never R1 failures |
| `D_decision` | `accepted`, `success`, `converged`, `abstained`, `within_tol.*`, `b0.valid`, and decision-derived condition counts/rates | boundary-stable decision equivalence; `accepted`/`rejected`/`indeterminate` |

`B` condition aggregates have `scope: "condition"` and are compared only when every trial
in the condition is identifiable. `D` decisions preserve `reference_raw` and
`candidate_raw`; a raw value is never rewritten. A derived decision becomes
`indeterminate` when any dependency or its own deciding statistic is indeterminate; the
report also checks that stored derived booleans agree with their declared dependencies.

### Identifiability rule

The v2 protocol fixes the rule before any comparison and evaluates it on the **reference**
artifact only:

```
identifiable = b1.converged
               and b1.worst_rel_se <= 1e-2
               and b1.condition_number <= 1e4
               and all f0, v, t0, b finite
```

On the measured pair this marks 2000/2500 trials identifiable; 500 null/degenerate trials
are scoped out. The rule, thresholds, and counts are data in the protocol and report, so a
trial's class cannot depend on how close the two machines happen to be.

### Decision margins

Margins are absolute distances on the deciding statistic, declared per decision with a
justification in the protocol:

| Decision | Deciding statistic | Threshold | Margin |
|---|---|---|---|
| `b1.converged` | `b1.grad_norm` (`lt`) | 1e-6 | 5e-7 (half the convergence threshold) |
| `b1/b0 within_tol.f0`, `.v`, `.t0`, `.b` | signed `rel` / `t0_abs` (`abs_lt`) | 1%, 2%, 0.25 s, 5% | 1% of each threshold |
| `b1.accepted` | `b1.improvement_ratio` (`ge`) | 0.5 | 1e-3 |
| `b0.valid` | none (structural validity flag) | — | exact decision |

A decision is `indeterminate` when either side's deciding statistic is within its margin;
outside the margin the raw decisions must match. The real trial 57 (`snr_+5dB`) is the
motivating case: parameters agree to ~1e-9, `b1.grad_norm` is 2.97e-12 on the reference and
1.056e-6 on the candidate (margin 5e-7), so `converged`, its derived `success`, and
`accepted` are reported indeterminate with raw `true`/`false` preserved.

### Split R1 and report fields

`R1-N` covers A exactness and B tolerance on identifiable trials; `R1-D` covers decidable
D decisions and condition-level rate materiality. The report carries `r1_n`, `r1_d`,
`reproduction_level ∈ {R2, R1-N+R1-D, R1-N only, R0 only, none}`, per-trial
`identifiability` entries (including `r1_n_status`), per-field B statistics with
not-applicable counts, decision summaries/details, `decision_instability`,
`rate_changes`, C diagnostic summaries/differences, and unclassified-field coverage.

CLI targets: `--require R1-N`, `--require R1-D`, `--require both` (and legacy
`--require R1` = both); exit 0 only when the requested target passes.

### Where the measured-draft values are, and the freeze gate

- B tolerances: `protocols/e0-cross-platform.v2.json` →
  `field_classes.B_identifiable_numeric[*].abs_tol` and `.rel_tol`.
- Decision margins and justifications: `field_classes.D_decision[*].margin` and
  `justification`.
- Rate materiality: `rate_checks[*].material_abs_change` (v2 uses a one-count window of
  0.0105 for 100-trial rates and 1 for counts, so a single masked decision is not a
  material rate change; a two-count shift fails R1-D).
- Freeze gate: validate on a second platform pair (three environments), replace the
  `measured_draft_not_frozen` status/note, record the protocol digest with the validation
  report, and only then cite `numerically_equivalent` as a frozen cross-platform
  reproduction. The Lead fills the final `abs_tol`/`rel_tol`/`margin`/
  `material_abs_change` values; they must be derived from measurement and decision
  thresholds, never chosen to make a run pass.
- The v1 example protocol (`e0-cross-platform.example.json`) remains illustrative and
  `example_only`; v2 is the protocol family for R1-N/R1-D work.
