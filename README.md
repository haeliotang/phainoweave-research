# PhainoWeave Research — Reproducible Physical Inference Studies

**Status:** research release · 2026-11-07 · tag `research-2026-11-07` (not a product, not a physical inference system)

**A project of Inceptless** · [support@inceptless.com](mailto:support@inceptless.com)

PhainoWeave studies a narrow scientific question:

> Given ambient observations, a declared measurement model, and explicit uncertainty, can a system decide when a physical proposition is supported, when it is contradicted, and when there is not enough evidence to decide?

This repository contains the synthetic studies, frozen protocols, positive and negative results, and the minimum code needed to recompute the central measurements. It does **not** contain real bench data, a production runtime, or evidence that the method recovers hidden physical states in the real world.

## What is established here

- **E0 synthetic Doppler study:** 2,500 pre-registered trials with a replayable digest; parameter tolerances and failure thresholds measured. Synthetic only.
- **C1 identifiability contract:** symbolic proof, independent certificate, and locked claim validation for one acoustic forward model.
- **C2-C sealed confirmation:** one 566-trial sealed run; B1 is conditionally supported on the pre-declared endpoint, with a published family failure at high chirp rates and an unresolved time-block self-confirmation caveat.
- **Negative results retained:** E1-C-estimator audit, trial-level decision instability, R1-D/R2 cross-environment failures, and the hardened v1.1 candidate protocol are documented rather than hidden.

## What is not established

- No real bench measurement exists. E1 remains `prepared / not_evaluated`.
- No claim of real-world localization, tracking, or physical capability.
- No person-level, military, targeting, enforcement, or private-residence inference.
- Cross-platform byte identity (R2) is not established; R1-D is not a blocking gate.
- macOS arm64 is not a verified CI environment for the hardened candidate.
- The local security/governance mechanisms are partial; refer to [LIMITATIONS.md](LIMITATIONS.md).

## Start here

- [LIMITATIONS.md](LIMITATIONS.md) — what the evidence does and does not support.
- [REPRODUCTION.md](REPRODUCTION.md) — environment, commands, expected outputs, and verification boundaries.
- `evidence/c2c-sealed/` — the archived sealed artifact, manifest, report, and independent recomputation path.
- `docs/experiments/` — the experiment records, including negative results.
- `protocols/` — frozen protocols and protocol digests.

## Contact

PhainoWeave is a project of Inceptless. Copyright © 2026 Inceptless. Research collaboration, security reports, licensing and general enquiries: [support@inceptless.com](mailto:support@inceptless.com).

## License and citation

Code is provided under the repository `LICENSE` (Apache-2.0). The proposed documentation/evidence licences and code-in-documentation boundary are in [LICENSING.md](LICENSING.md); official licence texts/links are listed there. Third-party components are listed in [THIRD_PARTY.md](THIRD_PARTY.md). `CITATION.cff`'s `Apache-2.0` field refers to the software code only. The maintainer confirmed the rights and licence scheme on 2026-11-07 and authorized this research release.

This is a research prototype. Do not use it to make decisions about people, private locations, or operational activities.
