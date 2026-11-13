<!-- SPDX-FileCopyrightText: 2026 Inceptless <support@inceptless.com> -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# PhainoWeave Research

## Empirical Limits of Physical-World Observability

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/phainoweave-mono-dark.svg">
    <img src="assets/phainoweave-mono.svg" alt="PhainoWeave logo — Doppler in the spectrogram" width="110">
  </picture>
</p>

**A project of Inceptless** · [support@inceptless.com](mailto:support@inceptless.com)

**Status:** public research program · baseline tag [`research-2026-11-07`](https://github.com/haeliotang/phainoweave-research/tree/research-2026-11-07) · not a product, not a validated physical inference system.

PhainoWeave Research is the public scientific record of the PhainoWeave project. It investigates what physical states can — and cannot — be established from incomplete, heterogeneous and dependent observations.

> Given incomplete observations, declared measurement models, unknown nuisance parameters and explicit uncertainty, what physical propositions can be supported, contradicted, or left undetermined?

The project is not defined by a single sensor. Acoustic, hydrological, satellite, RF and fixed-view visual observations are different measurement mechanisms that may constrain a physical proposition. They are not automatically independent evidence: shared upstream products, calibration, events and physical propagation must be audited.

## Research program

The public program separates two products:

- **State reconstruction** — an experimental task: what is the most defensible estimate of the world given these observations?
- **Observability boundary** — the primary scientific objective: do the observations and declared assumptions actually distinguish the candidate states?

A prediction can be correct for the wrong reason. A model score is not evidence that the observation identifies the state. The public unit of output is a **Claim Certificate** with a declared forward model, nuisance assumptions, provenance, dependence, feasible states, counterexample and replay identity.

Read the full public program: [Empirical Limits of Physical-World Observability](docs/research/observability-program.md).

## Research series

| Series | Public status |
|---|---|
| **PW-A Acoustic** | Published synthetic baseline; E1-0 prepared / not evaluated. [Index](studies/acoustic/README.md) |
| **PW-H Hydrology** | Proposed; no public preregistration or result. [Index](studies/hydrology/README.md) |
| **PW-S Satellite** | Proposed; no public preregistration or result. [Index](studies/satellite/README.md) |
| **PW-R RF** | Proposed; no authorised public experiment. [Index](studies/rf/README.md) |
| **PW-V Visual** | Proposed; no authorised public camera study. [Index](studies/visual/README.md) |

The acoustic series is the first published series, not the whole program. The other series are proposals; their existence does not imply data, preregistration or results.

## First published series — acoustic

- **E0 synthetic Doppler study:** 2,500 preregistered trials with a replayable digest; parameter tolerances and failure thresholds measured. Synthetic only.
- **C1 identifiability contract:** symbolic proof, independent certificate, and locked claim validation for one acoustic forward model.
- **C2-C sealed confirmation:** one 566-trial sealed run; B1 conditionally supported on the pre-declared endpoint, with a published family failure at high chirp rates and an unresolved time-block self-confirmation caveat.
- **Negative results retained:** E1-C-estimator audit, trial-level decision instability, R1-D/R2 cross-environment failures, and the hardened v1.1 candidate protocol are documented rather than hidden.

## What is not established

- No real bench measurement exists. E1 remains `prepared / not_evaluated`.
- No real-world localization, tracking, or physical capability is claimed.
- No result is claimed for PW-H, PW-S, PW-R or PW-V.
- Five modalities are not five independent pieces of evidence.
- No person-level, military, targeting, enforcement, or private-residence inference.
- Cross-platform byte identity (R2) is not established; R1-D is not a blocking gate.
- macOS arm64 is not a verified CI environment for the hardened candidate.
- The local security/governance mechanisms are partial; refer to [LIMITATIONS.md](LIMITATIONS.md).

## Historical baseline

The acoustic studies, frozen protocols, evidence hashes and negative results were published at tag `research-2026-11-07`. The tag and its frozen files are not moved or retroactively reinterpreted. The broader program is a project-level evolution on `main`, not a rewrite of that snapshot.

This repository does **not** contain real bench data, a production runtime, a shared multimodal platform, or evidence that any proposed non-acoustic series has reached a real-data result.

## Start here

- [Empirical Limits of Physical-World Observability](docs/research/observability-program.md) — public research program, claim framework and gates.
- [Studies index](studies/README.md) — five series and their evidence status.
- [LIMITATIONS.md](LIMITATIONS.md) — what the evidence does and does not support.
- [REPRODUCTION.md](REPRODUCTION.md) — environment, commands, expected outputs, and verification boundaries.
- `evidence/c2c-sealed/` — the archived sealed artifact, manifest, report, and independent recomputation path.
- `docs/experiments/` — the experiment records, including negative results.
- `protocols/` — frozen protocols and protocol digests.

## Contact

PhainoWeave is a project of Inceptless. Copyright © 2026 Inceptless. Research collaboration, security reports, licensing and general enquiries: [support@inceptless.com](mailto:support@inceptless.com).

## License and citation

Code is provided under the repository `LICENSE` (Apache-2.0). Documentation is CC-BY-4.0; published project-owned synthetic evidence bytes are CC0-1.0 where identified in [LICENSING.md](LICENSING.md). Third-party components are listed in [THIRD_PARTY.md](THIRD_PARTY.md). `CITATION.cff`'s `Apache-2.0` field refers to the software code only.

This is a research program. Do not use it to make decisions about people, private locations, or operational activities.
