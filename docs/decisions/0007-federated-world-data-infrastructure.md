# ADR 0007 — Federated world data infrastructure

Status: Accepted
Date: 2026-11-04
Deciders: Haelio Tang (founder)

## Context

The founding brief assumes public environmental data — maps, satellite imagery, terrain, reanalysis weather, aircraft tracks, species distributions, ocean and astronomy records — as the `D` in `P(L, T, S | O, D)`. The obvious way to build that assumption is to ingest the world: copy Overture, mirror Sentinel scenes, keep an ERA5 grid, and grow a global database. That path is a treadmill (storage, refresh, license, quality) that would consume the project's entire engineering budget before it produced one verified inference.

A survey of the public data ecosystem ([data infrastructure survey](../research/data-infrastructure.md), 2026-11-04) found the opposite leverage: mature institutions already collect, publish, version, and license this data. What is missing is not another copy; it is a layer that can *find, constrain, cite, snapshot, and verify* records from those institutions.

The survey also found four properties that must shape the architecture rather than be discovered later: (a) base maps already have an open, partitionable supply chain (Overture GeoParquet, OSM/Geofabrik extracts); (b) satellite discovery is standardizing on STAC with COG assets, and no single provider covers everything; (c) historical weather is deep but model-based at 9–25 km, not street-level measurement; (d) historical motion data (aircraft, vessels, vehicles) is the least open, and access terms differ per provider, so no default path may depend on a restricted one.

## Decision

1. **PhainoWeave does not own a second global geographic, satellite, weather, or biological database.** Global observation data remains owned, collected, and maintained by its institutions. PhainoWeave builds **Federated World Data Infrastructure**: catalog, adapters, spatiotemporal query planning, normalization, caching, and immutable evidence snapshots over existing providers.
2. **One boundary, three layers.** `External World Data` (providers) → `PhainoWeave Data Fabric` (access, normalization, snapshot, license, provenance) → `World Evidence Engine` (ontology, constraints, hypotheses, verification). No provider is called directly from an inferencer, a verifier, or a surface; every read passes the fabric and is recorded.
3. **The fabric has six components,** each with a single responsibility: `World Data Catalog` (what exists, with coverage, license, access, fidelity), `Provider Adapters` (STAC/REST/OData/bulk-file per provider), `Query Planner` (what this task needs, at what cost), `Data Cache` (regional/time-window subsets, content-addressed), `Normalization` (CRS, time base, units, quality flags), and `Evidence Registry & Snapshot Store` (source chain, immutable snapshot ids, checksums, access audit). The Catalog and the Planner are deliberately separate: describing the world's available data is not deciding which data a hypothesis needs.
4. **Every dataset is registered under one machine-readable contract before first use**: `dataset_id`, `provider_id`, `source_uri`, `license`, `spatial_extent`, `temporal_extent`, `spatial_resolution`, `positional_accuracy`, `temporal_resolution`, `observation_type` (direct observation | model estimate | derived product), `uncertainty_model`, `version`, `retrieved_at`, `content_hash`, `access_policy`. The registration also carries a capability profile (coverage, fidelity, reliability, verifiability, legal reusability) and a **missingness model**.
5. **`spatial_resolution` and `positional_accuracy` are distinct normative fields.** A 10 m raster does not imply 10 m object accuracy; an hourly record does not imply the event is known to the hour. A dataset with no stated uncertainty model is usable only as context, never as a constraint with a residual.
6. **Absence of observation is not observed absence.** Every dataset profile declares why a place or time can be missing (no receiver coverage, cloud cover, revisit gap, station gap, observer bias). The ontology's `missingness` handling and the verifier must consume this; a missing track row or GBIF record may not be used as negative evidence.
7. **Licenses are enforced, not documented.** A `LicensePolicyEngine` runs at ingest, derivation, sharing, and publication, using the source's license and the license lattice of the ontology (I10). Per-dataset and per-theme licenses are the unit: Overture themes, GBIF records, and satellite products do not share one license. Public ≠ free ≠ commercially reusable; a restricted source can never become a default path. (Verified 2026-11-04: Overture's ODbL covers Base, Buildings, Divisions, and Transportation; Places and Addresses are permissive per source — so share-alike is the default for most of the base map, not an edge case.)
8. **Access protocol preference**: STAC → COG → GeoParquet → provider REST/OData → bulk file. Every fetch pins an immutable snapshot (provider version, release tag, retrieval time, content hash) so a run replays against the same bytes. No result may cite a live endpoint as its data source.
9. **Query planning is evidence-aware and cost-aware.** The planner receives a hypothesis/query, selects a minimal set of providers that can constrain it, estimates the information gain and the cost (transfer, requests, compute), and records the plan in the run record. Global brute-force fan-out is prohibited by design, not by convention.
10. **Three storage tiers, local-first by research area**: L1 metadata/index (SQLite; PostgreSQL when a research node needs it), L2 regional analytical cache (DuckDB + GeoParquet, COG windows, track slices), L3 immutable evidence archive (content-addressed blobs + Parquet manifests). A user caches the region and time window in use, not the planet.
11. **No production dependency on public OSM tiles or public Nominatim.** Regional `.osm.pbf` extracts, self-hosted or self-generated tiles (PMTiles) where rendering is needed, and direct object queries through the fabric replace bulk tile access and rate-limited geocoding.
12. **First connectors (plan, not commitment)**, in the survey's order: Overture Maps (P0), Geofabrik/OSM extract (P0), Copernicus DEM (P0), Open-Meteo/ERA5 (P0), NOAA ISD (P0/P1), Copernicus Data Space / Earth Search STAC (P0/P1), adsb.lol (P0 for licensed motion-reference experiments), Copernicus LCFM (P1), GBIF (P1), JPL Horizons (P1). Priority reflects inference value and legal reusability, not provider prominence.
13. **This boundary is binding on future work.** Any new data provider, geospatial database, model, or agent must enter through the fabric: a registered profile with a license and missingness declaration, an adapter, and a recorded snapshot. A capability that can only be obtained by a direct API call bypassing the fabric is not accepted into the core.

## Consequences

### Positive

- The project stays a knowledge layer instead of becoming a data-maintenance organisation; engineering effort goes to constraints and verification.
- Every inference is reproducible against pinned snapshots and attributable to a licensed source, which is the point of the evidence ontology.
- License and precision limits become machine-checkable, so a 25 km reanalysis cannot silently be reported as street-level evidence.
- Provider churn is absorbed by adapters, not by the ontology.

### Negative / costs

- Adapter maintenance is permanent work; each provider's API, terms, and schemas drift.
- Federation cannot guarantee coverage or latency; some questions will be unanswerable because the data exists only behind a restricted path.
- Snapshot storage and network transfer cost real money; the cost-aware planner mitigates it but does not remove it.
- Missingness modelling is an ongoing analytical burden with no finished state.

## Alternatives considered

- **Own a global data lake (mirror maps, imagery, weather).** Rejected: enormous storage and refresh cost, licensing constraints, and it front-loads years of work before the first verified inference.
- **Single-provider dependency (e.g. one cloud STAC + one map dataset).** Rejected: the survey shows no provider covers all modalities or all regions, and single dependency turns a license change into a project outage.
- **Pure on-demand API access with no snapshots.** Rejected: unreproducible — a rerun against a live endpoint does not test the same data, breaking I6 and the evaluation stance.
- **Lakehouse-first with inference added later.** Rejected: without the evidence/constraint layer it is a data platform with no falsifiable claim, which is precisely the failure mode the founding brief names.
- **Treat public data as free data.** Rejected by [ADR 0005](0005-privacy-and-dual-use.md) and the data governance policy; several of the most useful sources are research-only or non-commercial.

## References

- [Data infrastructure survey](../research/data-infrastructure.md) — the eight domains, provider notes, verification grades
- [Data sources inventory](../research/data-sources.md) — licenses, access limits, snapshot policy
- [Data governance](../policy/data-governance.md) — sensitivity classes, access, retention
- [World ontology](../specs/world-ontology.md) — `source`, `license`, `license_snapshot`, I10
- [ROADMAP](../roadmap/ROADMAP.md) — data fabric workstream and phased milestones
