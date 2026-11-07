# Limitations

This document is part of the release candidate. It is intentionally stricter than the README.

## Evidence scope

- **Synthetic only.** E0, C1 and C2-C use generated signals and declared truth. None is a real acoustic measurement.
- **E1 has no physical evidence.** E1 is `prepared / not_evaluated`; there are no bench recordings, no independent instrument reference, and no measured uncertainty budget.
- **C2-C is one sealed run.** It supports a conditional measurement correction on its pre-declared endpoint, not real-world reliability.
- **High-chirp detection fails in the synthetic pipeline.** In the 150–400 Hz/s band, every C2-C candidate abstains (0/30). This is a measured failure of the frozen synthetic test pipeline; it does not establish a representational, information-theoretic or real-world limit.
- **B1 has an unresolved time-block caveat.** In-block improvement did not persist in the held-out time block; the sealed confirmation does not cancel that result.
- **Estimator consensus is not physical truth.** `detected` marks estimator agreement within the frozen test, not confirmation of a real physical event.

## Reproducibility boundaries

- R2 (bitwise identity) fails across tested environments.
- Frozen E0 has a measured R1-D failure on Linux x86_64 (`null_noise_only`, trial 2456); this historical failure remains.
- Hardened v1.1 is a separate `candidate_frozen` estimator. Its measured 2500/2500 decision agreement is limited to the synthetic E0 grid and tested environments.
- Linux arm64 and Linux x86_64 have passed the hardened semantic comparison. macOS arm64 is not an authoritative CI environment in the public release; the private CI cell is optional.
- The CI record for the documentation-only commit `44b89ed` is **unexecuted verification**, not a test failure and not a pass.

## Evaluation-set disclosure

The C2-C sealed trials and results are part of this public release. Once published, this set is a **public evaluation set**:

- it may be used for benchmark comparison and reanalysis;
- it may **not** be presented as an unseen sealed set for future confirmation;
- future methods must use a new, pre-registered evaluation set for confirmatory claims.

## Security and governance

- Local actor credentials use symmetric HMAC; this is local possession, not institutional identity.
- Policy files are caller-supplied and unsigned; policy approval provenance is not authenticated.
- Precision/capability enforcement is not wired through every data access, inference, and output path.
- E1 calibration validity is syntax-checked only; issuer and trusted-clock expiry are not authenticated.
- The cockpit is not a validated decision system and has no browser-level end-to-end test in this release.

## Intended use boundary

No feature here is intended for locating a person, tracking individuals, military or targeting use, enforcement, watchlists, or revealing a private residence. Documentation of refusal boundaries is not an operational capability.
