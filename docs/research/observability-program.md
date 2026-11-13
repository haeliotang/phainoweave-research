<!-- SPDX-FileCopyrightText: 2026 Inceptless <support@inceptless.com> -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# PhainoWeave Research — Empirical Limits of Physical-World Observability

**Status:** public research program · 2026-11-13 · **baseline snapshot:** `research-2026-11-07` (unchanged)

PhainoWeave Research is the public scientific record of the PhainoWeave project. It studies what physical states can — and cannot — be established from incomplete, heterogeneous and dependent observations.

The project is not defined by one sensor. Acoustic, hydrological, satellite, RF and fixed-view visual observations are different measurement mechanisms that may constrain a physical proposition. Five modalities are not five independent pieces of evidence: shared upstream products, shared calibration, shared events and shared electromagnetic propagation must be audited.

## The research question

> Given observations \(y_i\), declared measurement models \(h_i(x,\theta_i)\), nuisance parameters \(\theta_i\), and explicit uncertainty, what set of physical states remains compatible with the evidence — and what does that set imply for a specific proposition \(Q(x)\)?

Two products must be distinguished:

- **State reconstruction** — the best defensible estimate of the world under the observations.
- **Observability boundary** — whether the observations and assumptions actually distinguish the candidate states, or leave the proposition undetermined.

State reconstruction is an experimental task. Claim-level observability boundaries are the primary scientific objective. A prediction can be correct for the wrong reason; a model score is not an evidence statement.

## Claim-level framework

The public unit of scientific output is a **Claim Certificate**:

| Field | Meaning |
|---|---|
| Claim | a truth-evaluable physical proposition |
| Scope | region, time window, resolution and validity conditions |
| Forward model | declared measurement/physics model and version |
| Nuisance assumptions | unknown clocks, calibration, environment and other parameters |
| Observations | provenance, time, version, digest, licence and sensitivity |
| Dependence | duplicates, shared upstream products, shared calibration and shared events |
| Feasible states | compatible states, or a stated outer approximation |
| Decision | `supported`, `contradicted`, `undetermined` or `model_conflict` |
| Counterexample | when undetermined, reproducible states that disagree on the claim |
| Validation and replay | independent reference, error evidence and a rerunnable identity |

`supported` is conditional on the declared model, error bounds and assumptions. It is not a proof about the physical world.

A proposition is only reviewable if it states whether its feasible set is exact, an outer approximation or a sampled approximation. `undetermined` must carry a reproducible counterexample or an explicit statement that the feasible set cannot be enumerated.

## Evidence dependence

Different data sources are not automatically independent. The public research record distinguishes:

- source duplication;
- shared upstream products;
- shared calibration;
- shared event;
- shared physical mechanism, including electromagnetic propagation.

The private engineering repository's `independence_key` is a de-duplication key, not a proof of statistical independence. Public studies must report which dependence assumptions were tested and which remain unresolved.

## Research series and status

| Series | Proposition family | Public status |
|---|---|---|
| **PW-A Acoustic** | Non-person motion under acoustic propagation | **Published synthetic baseline** — E0, C1 and C2-C; E1-0 prepared / not evaluated |
| **PW-H Hydrology** | River-state propositions from radar, imagery and hydrological observations | **Proposed** — no public preregistration or result |
| **PW-S Satellite** | Surface-water/land-state propositions from SAR and optical imaging | **Proposed** — no public preregistration or result |
| **PW-R RF** | Controlled, non-person electromagnetic scattering/channel state | **Proposed** — no authorised public experiment |
| **PW-V Visual** | Fixed-view environmental boundary and water-line propositions | **Proposed** — no authorised public camera study |

See the [studies index](../../studies/README.md) for each series. A proposal is not a capability. No new series has a real-data result in this repository.

## Gates

Each series advances independently through:

| Gate | Question |
|---|---|
| G0 Feasibility | Is there lawful, usable data and a credible independent reference? |
| G1 Model | Is there an explicit forward model with nuisance bounds and mismatch conditions? |
| G2 Identifiability | Which claims can be distinguished, with reproducible counterexamples? |
| G3 Real Evidence | Do real data behave as the model says, against an independent reference? |
| G4 Locked Validation | Does an unseen split reproduce the conclusion? |
| G5 Cross-domain | Does the method transfer to another physical mechanism? |

A series may be at G0 while another is at G4. Cross-series comparison is admitted only after each contributing series has its own G4 package. Negative and `undetermined` results are valid results.

## What this program does not claim

- It does not claim a new fundamental theory of observability. Structural identifiability, inverse problems, set-membership estimation and correlated sensor fusion are existing foundations.
- It does not claim that five modalities provide five independent votes.
- It does not claim real-world capability from synthetic evidence.
- It does not include person-level inference, targeting, surveillance or private-residence inference.
- It does not replace the historical acoustic snapshot. `research-2026-11-07` remains an immutable citation target for the acoustic studies it contains.

## Historical baseline

The repository is the public home of the first PhainoWeave research series and of the broader program. The acoustic baseline was published at tag `research-2026-11-07`; its frozen protocols, evidence hashes and negative results are not rewritten. The broader research program is a project-level evolution on `main`, not a retroactive reinterpretation of that snapshot.

## References

- [Studies index](../../studies/README.md)
- [Acoustic series](../../studies/acoustic/README.md)
- [E0 synthetic Doppler report](../experiments/2026-11-04-e0-synthetic-doppler.md)
- [C1 identifiability report](../experiments/2026-11-05-c1-identifiability.md)
- [C2-C sealed confirmation](../experiments/2026-11-05-c2-sealed-confirmation.md)
- [LIMITATIONS.md](../../LIMITATIONS.md)
