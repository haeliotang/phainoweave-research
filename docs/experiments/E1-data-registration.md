# E1 data registration form

**Status:** template, prepared before collection · 2026-11-05 · **Applies to:** E1 Pilot datasets · **Registers through:** minimal fabric (`phaino fabric register`, [ADR 0012](../decisions/0012-research-grade-minimal-fabric.md)) · **Policy:** [data governance](../policy/data-governance.md)

One registration per dataset (one per recording series is acceptable). The form is filled **before** the bytes enter the fabric; registration refuses a profile without license, scale/accuracy fields or a missingness statement.

## 1. Identity

| Field | Value |
|---|---|
| `dataset_id` | `e1-pilot-<series>-<date>` |
| `provider_id` | `phainoweave` or the contributing institution |
| `source_uri` | local series manifest path or repository reference |
| `version` | e.g. `1.0.0` |
| `retrieved_at` | ISO-8601 UTC |
| `content_hash` | snapshot id produced by `fabric register` |

## 2. License and access

| Field | Value |
|---|---|
| `license.spdx` | `CC0-1.0` / `CC-BY-4.0` / project-internal (`research`) / other |
| `license.terms_url` | terms or the signed consent reference |
| `license.access_level` | `public` / `research` / `restricted` |
| `access_policy.allowed_purposes` | `internal_research`, `external_publication`, `redistribution` (tick those permitted) |
| `access_policy.authorization_required` | yes/no; link to the signed consent when yes |
| Consent record reference | participant/venue/equipment authorization ids |

## 3. Scale, accuracy, observation type

| Field | Value | Notes |
|---|---|---|
| `observation_type` | `direct` | real recordings are direct observations |
| `spatial_resolution` | null with reason | not a spatial product |
| `positional_accuracy` | null with reason | not a spatial product |
| `temporal_resolution` | sample period and sync offset | audio sample rate, camera frame rate, measured sync |
| `uncertainty_model` | truth-uncertainty budget reference | [calibration procedure](E1-instrument-calibration.md) §4 |

`spatial_resolution` and `positional_accuracy` are separate fields; "not applicable" must be stated with a reason, never conflated.

## 4. Missingness

State why a pass, frequency, or interval can be absent from this dataset: dropped frames, clipping, excluded passes, device change, weather, sync failure. Absence of a pass is not evidence that an event did not occur.

## 5. Truth references

| Quantity | Instrument | Value ± uncertainty | Method |
|---|---|---|---|
| Path geometry | tape/laser | | |
| Closest-approach distance | tape/laser | | |
| Speed / timing | camera + sync | | |
| Playback frequency | measured static reference | | |
| Temperature / sound speed | thermometer + formula | | |
| Sync offset | shared event | | |

## 6. Content manifest

| File | Bytes | SHA-256 | Class (raw/derived/publishable) |
|---|---|---|---|
| `audio/<pass>.wav` | | | raw |
| `video/<pass>.mp4` | | | raw |
| `calibration/<series>.md` | | | publishable |
| `truth/<pass>.json` | | | raw / publishable per consent |

Publishable artifacts are desensitized features, parameters, hashes and non-sensitive calibration records; raw media and precise locations stay under the consent and retention rules.

## 7. Retention and withdrawal

| Item | Value |
|---|---|
| Raw media retention | 90-day review window (operational rule), decision recorded |
| Precise-location access list | names/roles |
| Withdrawal contact and procedure | |
| Deletion record | where tombstones/errata are recorded |

## 8. Sign-off

Operator, witness, and (where applicable) venue/data owner sign the registration. A registration is invalid if any of §2–§5 is blank.
