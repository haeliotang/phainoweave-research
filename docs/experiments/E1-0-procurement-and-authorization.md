# E1-0 procurement and authorization package

**Status:** checklist for the experiment organizer; no equipment ordered, no collection authorized · 2026-11-05 · **Gate:** [E1-0 instrument feasibility](E1-0-instrument-feasibility.md)

This is the minimum package needed to run Bench 1–5. Each item must be answered with a document, measurement or certificate, not a verbal assurance. Nothing here authorizes recording or field work by itself.

## 1. Reference signal source

- Generates tones in the 450–550 Hz range with small known offsets (e.g. 0, 1, 2.9, 5.8 Hz) and a **known dynamic trajectory** (linear chirp or stepped FM) for Bench 2.
- Has a **traceable frequency calibration**: certificate or an independent counter/reference; state the calibration uncertainty and date.
- Can output directly (electrical) and via a loudspeaker.
- Records: model, serial, calibration certificate id, uncertainty, settings.

## 2. Audio acquisition

- Sample rate/bit depth fixed and exported as **raw PCM/WAV** with no lossy processing; original files retained.
- Input path documented (direct cable vs microphone), gain settings, filters disabled or recorded.
- Clock source identified (internal, word clock, USB); ability to export timestamps or a marker channel for clock tests.
- Dynamic range and distortion characterised or measured in Bench 1/3.

## 3. Time reference

- Independent of the recorder clock (GPS/PPS, atomic/rubidium reference, or a second clock with a measured drift model).
- Can produce at least two anchors separated enough to constrain `α` (≥150 s for the planning example) and a defined `β` origin.
- Records the reference's own uncertainty and the method used to separate propagation/audio-buffer delay from clock offset.
- Evidence required: `|α̂−α_ref|` and the `β` interval, not a nominal spec sheet only.

## 4. Acoustic path and site

- Static loudspeaker–microphone layout with controlled distance and orientation; reflective surfaces documented.
- Site risk assessment decides permitted distances/speeds; **5 m/s at 0.5 m is not assumed safe**.
- Background noise and reverberation characterised (Bench 3).
- Venue authorization record signed before any capture.

## 5. Data rights, consent and law

- Recording permission and retention period; any person present covered by consent or excluded.
- Applicable jurisdiction and legal review recorded; privacy review for raw audio.
- Data ownership and publication rights stated.
- No person-level analysis, consistent with the project's privacy gate.

## 6. Raw evidence package

For every capture: raw waveform, SHA-256, reference readings, device configuration, calibration record, timestamp, environment (temperature, sound speed, noise), `measurement_model_id`, calibration/evaluation split.

## 7. Feasibility assessment before purchase

Reject a device if it:

- provides only nominal frequency accuracy without an auditable independent reference;
- cannot export raw samples with known clock provenance;
- cannot support the two-anchor clock budget;
- requires unsafe proximity to reach the planned chirp rates.

If the selected equipment cannot meet the claim-specific budget (E1-0 output), the correct result is a documented capability limit, not a purchase of "better-looking" specs.

## 8. Gate outcome

Collection may start only when sections 1–6 have evidence, the E1-0 acceptance table is answered, and the protocol is frozen. Until then: preparation only.
