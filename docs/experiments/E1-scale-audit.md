# E1 scale audit — what chirp rates a safe controlled pass can actually produce

**Status:** planning audit; no E1 data collected · 2026-11-05 · **Authority:** [ADR 0025](../decisions/0025-e1-scope-and-scale-audit.md) · **Related:** [E1 preregistration draft](2026-11-05-e1-preregistration-draft.md)

For a straight-line constant-velocity source in the low-Mach-number limit, the frequency rate near closest approach is

```
|ḟ| ≈ f0 · v² / (c · b)
```

with emitted frequency `f0`, speed `v`, sound speed `c`, and closest approach `b`. The full forward model is used for planning; this relation only bounds the order of magnitude.

## Candidate rates (f0 = 500 Hz, c = 343 m/s)

| v \ b | 0.5 m | 1 m | 2 m | 5 m | 10 m |
|---:|---:|---:|---:|---:|---:|
| 1 m/s | 2.9 | 1.5 | 0.7 | 0.3 | 0.1 |
| 2 m/s | 11.7 | 5.8 | 2.9 | 1.2 | 0.6 |
| 3 m/s | 26.2 | 13.1 | 6.6 | 2.6 | 1.3 |
| 5 m/s | 72.9 | 36.4 | 18.2 | 7.3 | 3.6 |
| 10 m/s | 291.5 | 145.8 | 72.9 | 29.2 | 14.6 |
| 15 m/s | 656.0 | 328.0 | 164.0 | 65.6 | 32.8 |

(units: Hz/s)

## Consequences for E1

1. **A safe indoor pedestrian/speaker pilot covers roughly 0.1–70 Hz/s**, not the C2 high-chirp band of 150–400 Hz/s. Reaching 150 Hz/s would need about 10 m/s at 1 m closest approach, or 15 m/s at 2 m — neither is a safe or practical controlled indoor pass.
2. **The 150–400 Hz/s acceleration-detection failure in C2-C is therefore not testable by a low-speed controlled pilot.** E1 must either (a) declare that band uncovered, or (b) design a separate, safety-reviewed setup (e.g. a vehicle pass on a closed course, or a different emitted frequency/geometry that raises the chirp rate without unsafe proximity), with its own authorization. It must not claim to reproduce a synthetic indicator by adding field risk.
3. **Same chirp rate is not equivalence.** Even where rates overlap, the full frequency trajectory, noise, reverberation, source directivity and propagation differ; E1 conclusions are about the overlap region actually observed, not about the synthetic band.
4. **E1 coverage must be pre-declared** from this audit: achievable chirp-rate ranges per pilot setup, the expected `b` and `v` ranges, and the resulting accuracy expectations. The pilot report must state the covered range and explicitly list uncovered regions.

## Planning defaults

- Pilot: 18–30 controlled passes, static source first, then moving series before/after; calibrated audio; independent motion measurement; two time anchors or rate calibration + absolute anchor for `t_obs = α t_phys + β`; declared temperature/sound-speed handling.
- Locked E1 size is set only after the pilot yields effect sizes and variance; pilot results are not confirmation.
- Venue, operator, dates and legal review remain gating; this document does not authorize collection.
