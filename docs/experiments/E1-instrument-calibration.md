# E1 instrument calibration and static-reference procedure

**Status:** procedure for the E1 Pilot, prepared before data collection · 2026-11-05 · **Applies to:** [E1 protocol](2026-11-05-e1-preregistration-draft.md) §11 equipment plan B · **Related:** [consent template](../policy/consent-template.md), [data registration](E1-data-registration.md)

**Purpose.** Make the reference truth and the device behavior measurable before any moving pass, so that a Doppler estimate can be separated from recorder-clock drift, speaker-frequency drift, camera calibration error and temperature effects. A calibration record that is not written down did not happen.

## 1. Devices and what each must prove

| Device | Calibration / verification | Acceptance (pre-declared) | Recorded |
|---|---|---|---|
| Audio recorder | Sample-rate accuracy against a reference clock over ≥10 min; no dropped samples; gain/clipping check with a 1 kHz tone at expected levels | measured sample-rate error documented; zero dropped samples in a 10-min test; no clipping at planned gain | device id, firmware, sample rate, measured drift ppm, file hash of test recording |
| Loudspeaker / playback | Emitted frequency stability over ≥10 min at each planned setting, measured by the recorder or a second analyzer | frequency drift documented; if drift exceeds _TBD ppm_, the pass is excluded or the frequency is treated as time-varying | playback source, file hash, measured frequency vs time, drift ppm |
| Camera | Lens/geometry calibration (checkerboard or measured markers); frame-rate check against the audio/file clock | reprojection error documented; frame timestamps consistency documented | calibration file hash, reprojection RMS, frame rate, sync method |
| Distance/layout | Tape/laser measurements of path, closest-approach distance, receiver height, marker positions | measurement uncertainty recorded (instrument resolution + operator) | diagram, distances, uncertainty |
| Temperature/humidity | One reading before and after each series, same instrument | instrument resolution recorded | time series, instrument id |
| Sync method | A shared event (clap, flash, tone burst) recorded by audio and camera simultaneously | measured offset between modalities documented | offsets per series |
| Phone GNSS/IMU (auxiliary) | Only as cross-check; not the primary truth | stated accuracy class; no precision claim from phone GNSS | logs, app/version |

## 2. Static-reference runs (required before and after every moving series)

1. Loudspeaker stationary at the receiver's closest-approach point; record ≥60 s at each planned frequency. This measures the frequency reference and device clock state with no motion.
2. Repeat after the moving series. A change in the static reference between before/after bounds the drift that could masquerade as Doppler.
3. Keep the same gain, sample rate, and playback file; hash every recording.

## 3. Moving pass record (minimum fields)

| Field | Note |
|---|---|
| Pass id, condition (speed regime / distance regime) | matches [E1 protocol](2026-11-05-e1-preregistration-draft.md) design |
| Playback frequency setting and measured frequency | measured, not trusted |
| Path geometry: endpoints, closest-approach distance, height, markers | from tape/laser, with uncertainty |
| Speed profile | constant / accelerating / piecewise, with measured timing |
| Audio file hash, video file hash, sync offset | immutably recorded |
| Temperature, humidity, wind, surface | before/after |
| Clock offsets: audio vs camera, playback clock | measured |
| Operator, witness, consent/venue references | links to the signed records |

## 4. Truth-uncertainty budget

Every reference quantity enters the record as **value ± uncertainty**, with the basis stated:

- distance: instrument resolution + placement error;
- time/speed: frame timing + sync offset uncertainty;
- closest-approach time: marker interpolation uncertainty;
- camera geometry: reprojection error propagated to position;
- playback frequency: measured drift.

A parameter estimate is judged against this interval, not against a bare reference number. The budget is fixed before the first moving pass; a revised budget after seeing data is reported as a deviation.

## 5. Failure handling

- A pass whose calibration record is incomplete is excluded and listed.
- A static reference that drifts beyond the pre-declared bound invalidates the series; re-run rather than repair.
- Any device change (new firmware, new playback file, new gain) starts a new series with a new calibration record.

## 6. Files produced per series

`calibration/<series-id>.md` (this procedure filled), raw calibration recordings with hashes, camera calibration file, sync notes, and the operator's signed checklist. Registered through the minimal fabric before use ([data registration](E1-data-registration.md)).
