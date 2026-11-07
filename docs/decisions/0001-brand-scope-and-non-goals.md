# ADR 0001 — Brand, scope, and non-goals

Status: Accepted
Date: 2026-11-04
Deciders: Haelio Tang (founder)

## Context

The founding brief (2026-11-04) explored several names and two scopes: a narrow "audio geolocation" tool and a general infrastructure for recovering hidden physical-world facts. It also considered keeping *Ambient Inference* as the project name after a product-architecture revision. The repository, brand, and public identity need one decision, not two names competing for the same thing.

## Decision

1. **Brand: PhainoWeave** (from Greek φαίνω, "to bring to light", and *weave*, "evidence interwoven rather than stacked"). Platform, repository, organisation-facing name, and the name that survives future domain expansion.
2. **Engine: Ambient Inference** is the technical name of the inference engine only (crate family, Python SDK, papers). It is not the brand and does not appear as the project name.
3. **Layer names.** Researcher-facing product layer: *Environmental Intelligence Workbench*. Developer / research-institution layer: *Open World Evidence Infrastructure*.
4. **Scope.** Reconstruct hidden physical-world facts from ambient observations (audio, image, video, sensor, weather, tracks, satellite, terrain) with physics-grounded, verifiable inference; output world-state hypotheses with residuals, uncertainty, calibration, and abstention — not point answers.
5. **Non-goals are binding** (full list in the founding brief §5): not a GeoGuessr; not a covert individual-tracking tool; not an oracle; not a Palantir clone; not a data lake first; not a foundation-model training project.
6. **Tagline.** *From observations to verifiable world states.*

## Consequences

### Positive

- One name for the long horizon; the engine can be renamed or split without rebranding the platform.
- The scope statement names the verification obligation, which forces the ontology and runtime design rather than bolting them on later.

### Negative / costs

- "PhainoWeave" is unfamiliar and needs a one-line gloss everywhere it appears; the README, brief, and docs each carry it.
- Keeping *Ambient Inference* as a secondary name means two names must be maintained consistently in code and docs.

## Alternatives considered

- **Ambient Inference as the project name.** Rejected: the founder's brief explicitly reserves it as the engine name so the platform can expand beyond inference (ontology, workbench, distributed research infrastructure).
- **A narrower name** (`aircraft-doppler-geolocation`, `geo-forensics`). Rejected: scope-locked names become wrong when the platform adds ecology, astronomy, and industrial inference.
- **No product/infra layer distinction.** Rejected: a researcher workspace and a developer substrate have different contracts; conflating them produces docs that serve neither.

## References

- [Founding brief](../product/founding-brief.md) §1, §5
- [ROADMAP](../roadmap/ROADMAP.md)
