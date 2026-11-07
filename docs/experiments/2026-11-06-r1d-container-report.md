# R1-D local container trial — arm64 decision equivalence passes, R2 byte identity fails; amd64 R1-D fails

**Status:** measured mixed result; R1-D is **not established across all target environments** · 2026-11-06 · **Harness:** [`scripts/container_repro.sh`](../../scripts/container_repro.sh) · **Image:** [`containers/repro/Dockerfile`](../../containers/repro/Dockerfile) · **Comparator:** [ADR 0013](../decisions/0013-reproducibility-contract-v2.md), `python -m phaino_verify.compare`

CI has not run since `183087e` because of the GitHub Billing block. This trial uses local Docker to obtain cross-environment evidence without waiting for CI. It does **not** replace CI, and it does not produce R2 byte equality.

## 1. Environments

| | Host | Container |
|---|---|---|
| OS / arch | macOS arm64 | Linux arm64 / Linux amd64 |
| Rust | 1.94.0 (Homebrew) | 1.94.1 |
| Python | 3.14.0 | 3.13.5 / 3.14.10 |
| NumPy / SciPy / SymPy | 2.4.4 / 1.17.1 / 1.14.0 | same pinned versions |
| Image | — | `phainoweave-repro:1.94-py311`, `python:3.14-slim` |

The container is copied from a temporary tree, so `target/` and `artifacts/` in the working tree are untouched.

## 2. Test and replay results

- Python: **435 passed, 3 skipped** in the latest Linux arm64 container run; host **439 passed** under Python 3.14. Three version-conditional skips mean the test populations are not identical.
- Documentation links: **619 checked, 0 broken**.
- `make e0` exits 3 on the E0 digest mismatch and still writes the replay record (`ALLOW_MISMATCH=1` records it as negative evidence).

## 3. R2 vs R1-D — do not conflate them

E0 digest:

| Field | Value |
|---|---|
| Host (macOS arm64) | `674213d9737f999a84aa8b57cddd9078e0bf2b2998ae02a45d0940cd98185506` |
| Linux arm64 container | `b77716f0b36d43b1391fe75030e1bb69bab360bae24e885255988250778346da` |
| Linux amd64 container | `0d167be8add3c031d5a0498bfe9a9a408072052ccd046dd32029ce03ee4bde81` |

- **R2 (bitwise identity) fails on every pair.** This is expected and is not the R1-D gate.
- **R1-D (decision equivalence, ADR 0013)** was evaluated with the existing comparator, not inferred from the digest.

The pair comparison is automated by `make r1d-compare` (or `scripts/r1d_compare.sh`), which defaults to the local `.repro` artifacts. Raw commands:

```
PYTHONPATH=python python -m phaino_verify.compare \
  .repro/host-py-e0/e0-results.json .repro/container-py-e0/e0-results.json \
  --protocol protocols/e0-cross-platform.v2.json --report .repro/r1d-compare.json --require R1-D

PYTHONPATH=python python -m phaino_verify.compare \
  .repro/host-py-e0/e0-results.json .repro/py314-amd64-e0/e0-results.json \
  --protocol protocols/e0-cross-platform.v2.json --report .repro/r1d-compare-amd64.json --require R1-D
```

Comparator result:

| Pair | R0 | R1-N | R1-D | R2 | reproduction_level |
|---|---|---|---|---|---|
| host mac arm64 ↔ Linux arm64 | pass | **pass** | **pass** | fail | **R1-N+R1-D** (`numerically_equivalent`) |
| host mac arm64 ↔ Linux amd64 | pass | pass | **fail** | fail | **R1-N only** (`mismatch`) |

The amd64 R1-D failure is a material rate change, not a masked decision:

```
conditions[24].converged_rate: 0.09 → 0.08   (null_noise_only, material)
```

The changed trial is localized: `null_noise_only`, seed `20285160`. Both environments run 11 b1 iterations and produce essentially the same fit (`f0` ≈ 1472.70649, `v` ≈ 1.0, `b` = 1.0, SSE ≈ 1.0847e9, `sigma_f` ≈ 761.6 Hz); only the **convergence flag** differs (host `true`, amd64 `false`). The parameter difference is tiny (`v` differs by ~2.2e-8, `f0` by ~1e-7). A direct diagnostic of that trial shows the mechanism: both host and amd64 stop at 11 iterations with essentially identical parameters and an above-threshold stationarity norm (`grad_norm ≈ 5.321e-6` host, `5.322e-6` amd64; the E0 stationarity gate is `<1e-6`). The host's relative-step stop fires; the amd64 run's floating-point path does not, so the `converged` flag differs. This is a boundary/stall classification on a null trial, not a broad disagreement about the E0 parameters. ADR 0013 still treats the resulting rate change as material, so R1-D remains failed for this pair; the protocol is not adjusted to make it pass.

So the local **arm64 pair passes R1-D**, while the **amd64 pair fails it**. R1-D as an all-target gate is therefore still off; the earlier three-environment validation also failed pairs involving x86_64.

## 4. Python-only decomposition

| Environment | Python | `records_sha256` | R1-D vs host |
|---|---|---:|---|
| macOS arm64 (host) | 3.14.0 | `674213d9…` | baseline |
| Linux arm64 container | 3.13.5 | `b77716f0…` | **pass** |
| Linux arm64 container | 3.14.10 | `b77716f0…` | pass |
| Linux amd64 container | 3.14.10 | `0d167be8…` | **fail** (rate change) |

The host and containers use the same NumPy/SciPy/SymPy versions. Python 3.13 and 3.14 on Linux arm64 produce the same digest, so interpreter/package versions do not explain the macOS byte difference. A Linux arm64 run with `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1` and `MKL_NUM_THREADS=1` also produced `b77716f0…`, ruling out BLAS thread scheduling. Remaining R2 candidates are platform binary builds (libm/BLAS/OpenBLAS kernels), architecture-specific code paths and OS-level floating-point behaviour.

A structural diff over 2500 host-vs-arm64 trials found zero `success`/`converged`/`within_tol` flips, but tiny parameter differences (907 above `1e-12`, 3 above `1e-6`, worst `1.9e-3` on one `null_noise_only` trial). These are enough to change the full-document digest, but the declared R1-D protocol accepts the arm64 pair because decisions and condition rates are unchanged.

## 5. What this means

- **R2 byte identity fails** across macOS/Linux and arm64/amd64. Do not describe a digest mismatch as an R1-D failure.
- **R1-D passes for the arm64 container pair** under the frozen comparator protocol; that is a real local gain.
- **R1-D fails for the amd64 pair** because `null_noise_only.converged_rate` changes 0.09 → 0.08. The all-target R1-D gate remains off.
- The 3 skipped Python tests mean the container did not execute the identical test population; R1-D is still evaluated by the comparator, not by test counts.
- CI has not executed these commits; this is local evidence only.

Evidence is retained under `.repro/` (git-ignored): `container-linux-arm64/`, `host-py-e0/`, `container-py-e0/`, `py314-amd64-e0/`, `r1d-compare.json`, `r1d-compare-amd64.json`.

## 6. Hardened v1.1 amendment

The separate hardened estimator now classifies stalled clearly-inadequate null fits as `rejected / model_inadequate` (stall visible as an optimization diagnostic); its decision equivalence is 2500/2500 on host↔arm64 and host↔amd64. See [PR-4c §7](2026-11-05-pr4c-hardened-validation.md). Frozen E0 and its R1-D status are unchanged.

## 7. Target-scope note (not a normative change)

Frozen E0 R1-D remains failed on the x86_64 pair; the separate hardened v1.1 estimator now has 2500/2500 decision equivalence on both local pairs. Until a new ADR explicitly adopts the hardened estimator for the reproducibility gate (or removes x86_64 from the declared target), **CI continues to enforce R1-N only** and no report may claim whole-project R1-D. Adopting hardened v1.1 would also require its own freeze, artifact provenance and CI job; that decision is not made here.

## 8. Next probes

1. Reproduce trial 2456 (`null_noise_only`, seed `20285160`) on amd64 and classify its b1 termination/stall path. Diagnostic so far: both runs stop at 11 iterations; host relative-step stop fires, amd64 does not; do not relax the rate rule to hide it.
2. Align the amd64 decision rule or document why x86_64 remains outside the declared target.
3. Re-run the three-environment validation after the fix; freeze only when R1-N and R1-D hold on all declared pairs.
4. Keep R2 as a separate, explicitly failed level; never silently turn it into R1-D.
