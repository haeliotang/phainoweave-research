<!-- SPDX-FileCopyrightText: 2026 Inceptless <support@inceptless.com> -->
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# PW-S — Satellite series

**Status:** proposed; no public preregistration or result
**Framework:** [Empirical Limits of Physical-World Observability](../../docs/research/observability-program.md)

## Proposition family

For a declared region and time window, did a specified surface-water or land-state change occur beyond a preregistered threshold?

## Measurement mechanisms under study

- Sentinel-1 SAR, with acquisition geometry, calibration and missingness recorded;
- Sentinel-2 optical observations, with cloud, illumination and atmospheric assumptions declared;
- no automatic assumption that two satellite products are independent.

## Independent reference

A ground, airborne or authoritative surface-water observation that is not derived from the same satellite product used as the observation. Shared atmospheric correction, resampling or land-cover upstream data must be audited.

## Current status

Proposed. No region, event window, public preregistration or result is frozen. No flood-mapping or global surface-water capability is claimed.

## Public outputs expected at each gate

- G0: region, acquisition and independent-reference audit;
- G1: explicit SAR/optical measurement and nuisance model;
- G2: identifiable/undetermined surface-change propositions with counterexamples;
- G3/G4: real-data and locked-validation packages, if available.

A missing-reference or undetermined result is a valid outcome. No result exists yet.
