# ADR 0002 — Verification-first inference

Status: Accepted
Date: 2026-11-04
Deciders: Haelio Tang (founder)

## Context

The founding brief's central observation is that no single modality is the product: aircraft Doppler, birdsong ranges, solar geometry, weather reanalysis, cross-view imagery are each weak, differently precise, and sometimes contradictory. The obvious system design — feed observations to a model, emit a location — produces confident nonsense and cannot state why it should be believed. The founder's stated key capability is predictive verification:

> Given a candidate world state, the system independently predicts what should have been observed there and then, compares that prediction with the actual observation, and localizes the inconsistency.

This ADR makes that the architectural axis rather than one feature among many.

## Decision

1. **The system is an inverse-problem pipeline, not a classifier.** The unit of work is a *hypothesis* `H = (L, T, S)` over location, time, and environmental state, tested against observations `O` and public/physical data `D`. The target object is `P(L, T, S | O, D)`, reported as a region/time distribution, never an argmax.
2. **Proposers and verifiers are separate components with separate contracts.** Inferencers (Python, plugin) propose candidates and must emit constraint residuals and referenced data versions. Verifiers (deterministic where possible) test candidates against physical constraints and public data. A proposer's self-reported confidence is not evidence.
3. **No LLM output is the final step of a verification.** Language models may extract features, propose hypotheses, retrieve data, and critique evidence. The verdict must come from a check that is stated, deterministic or statistical, and rerunnable.
4. **Abstention is an output state, not an error.** Every inference returns `abstained` with a reason code when the evidence cannot separate candidates to the claimed precision.
5. **Every run is reproducible by construction.** A run record pins observation hashes, data snapshot ids, inferencer versions, model weights, physical parameters, ontology version, seed, and environment; the digest is content-addressed.
6. **Evidence independence is a first-class field.** Correlated evidence (rain in the image and rain in the audio = one weather event) must not multiply confidence; the combination rule collapses same-`independence_key` evidence to one vote.

## Consequences

### Positive

- A wrong answer is attributable: residuals show *which* physical assumption failed.
- Benchmarking becomes meaningful: calibration, coverage, and selective risk are measurable; "guessed right" is not the only score.
- Reproducibility is enforceable (record digest + snapshot ids) rather than a documentation promise.

### Negative / costs

- More machinery before the first useful answer: proposers, residuals, snapshots, and records all exist before a working vertical does.
- Verifiers are per-modality work (kinematics, ephemeris, propagation, meteorology); the system is only as good as its verifier library.
- Ensembles are slower and more expensive than a single model call.

## Alternatives considered

- **Single multimodal model → coordinates.** Fast to demo, unverifiable, and cannot report what it does not know. Rejected as the architectural centre; may still be used as one proposer.
- **LLM-as-verifier with chain-of-thought justification.** Rejected: unfalsifiable, non-reproducible, and confidently wrong in exactly the cases that matter.
- **Bayesian network over modalities only (no physics verifiers).** Rejected: without physical models the system cannot distinguish a candidate that is merely plausible from one that is *physically possible under the observation*.

## References

- [Founding brief](../product/founding-brief.md) §3, §4, §11
- [Inferencer contract](../specs/inferencer-contract.md)
- [Benchmark and evals](../roadmap/benchmark-and-evals.md)
