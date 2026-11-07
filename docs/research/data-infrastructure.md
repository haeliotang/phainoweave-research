# Data Infrastructure — Federated World Data

**Status:** survey of record and architecture input, 2026-11-04 · **Owner:** research · **Feeds:** [ADR 0007](../decisions/0007-federated-world-data-infrastructure.md) (binding), [ROADMAP](../roadmap/ROADMAP.md) §4.1 (workstream D1–D6), [data-sources.md](data-sources.md) (per-source licence record), [data-governance.md](../policy/data-governance.md) §7 (licence enforcement).

**Grading.** **V** = primary source fetched and quoted here or in [data-sources.md](data-sources.md); **E** = external claim from the founder survey of 2026-11-04 or a secondary source, not independently reproduced in this repository; **U** = unverified lead. Numbers and quotas below are external claims unless marked V. Section 13 lists what remains unverified.

## 1. Decision in one paragraph

PhainoWeave does not build a second global geographic, satellite, weather, or biological database. It builds a **Federated World Data Infrastructure**: a catalog of what exists, adapters that fetch a pinned snapshot, a planner that chooses the smallest useful set of sources for a given hypothesis, normalization to one coordinate/time/unit contract, and an immutable evidence registry. Global data stays with the institutions that already collect, license, and maintain it. The layer PhainoWeave owns is the one that converts those records into computable physical constraints and falsifiable hypotheses — not the one that stores the planet.

## 2. Four findings that shape the architecture

1. **Base maps already have an open, partitionable supply chain.** Overture Maps publishes global GeoParquet by theme on object storage; OSM/Geofabrik provide regional extracts. A global copy is neither necessary nor affordable (E).
2. **Satellite discovery is standardizing on STAC with COG assets, and no single provider covers everything.** Copernicus Data Space, Earth Search, Planetary Computer, NASA Earthdata, and OpenTopography coexist; a design with one provider becomes an outage on that provider's terms change (E).
3. **Historical weather is deep but model-based at grid scale.** ERA5 runs from 1940 hourly on a native ~31 km grid (the CDS product is interpolated to 0.25°); ERA5-Land is ~9 km native on a 0.1° distributed grid; station observations are direct but sparse (V, 2026-11-04; see §13). None of them is street-level measurement, and none may be reported as such.
4. **Historical motion data is the least open.** OpenSky's full history is eligibility-gated and research-oriented; adsb.lol publishes daily archives under ODbL (V). No default path may depend on a restricted source, so the acoustic vertical's track dependency is adsb.lol with OpenSky as research cross-check ([ROADMAP](../roadmap/ROADMAP.md) §4).

The architectural consequence: support multiple access protocols, permissions, and availability classes from the first version. A data layer that assumes "call an API, get the world" is unbuildable here.

## 3. Eight domains, by inference value

Priority is P0 = core infrastructure, P1 = first-phase expansion, P2 = specialised or long-horizon. Priority reflects *what physical constraint the domain provides* and *whether it can legally back a default path*, not provider prominence.

| Domain | Recommended infrastructure | Priority | What it constrains |
|---|---|---|---|
| Global base map and buildings | Overture Maps; OpenStreetMap / Geofabrik | P0 | Terrain objects, building density and form, roads/rail, acoustic occlusion, candidate positions |
| Satellite imagery and terrain | Copernicus Data Space; Earth Search; Copernicus DEM | P0 | Land cover, surface appearance, flooding/extent, elevation and line-of-sight |
| Historical weather and climate | ECMWF ERA5; Open-Meteo; NOAA ISD / GHCN | P0 | Rain, wind, temperature, cloud, event-time consistency |
| Aircraft and transport tracks | adsb.lol; OpenSky; GTFS / Mobility Database | P0/P1 | Doppler/kinematic constraints, motion events, schedule-based candidate sets |
| Biodiversity and environmental sound | GBIF; iNaturalist; eBird; Xeno-canto; Freesound | P1 | Species range, seasonality, ecological region, soundscape prior |
| Land cover and ecosystems | Copernicus LCFM; ESA WorldCover; Dynamic World | P1 | Environmental prior over urban/farm/forest/water |
| Ocean, seismic, environmental monitoring | NOAA AIS; NDBC; USGS; EarthScope; OpenAQ | P1/P2 | Vessel traffic, sea state, seismic events, air quality |
| Astronomy and space objects | JPL Horizons; CelesTrak | P1/P2 | Sun/moon illumination and shadow direction, satellite passes |

## 4. Domain notes

Verification grades in this section are from the 2026-11-04 pass recorded in §13; **V** claims were fetched and quoted, **E** are external claims, **U** are unverified leads.

### 4.1 Base maps — Overture + OSM/Geofabrik

Overture publishes six themes — Addresses, Base, Buildings, Divisions, Places, Transportation — as GeoParquet with official sources on Amazon S3 and Microsoft Azure (V). **Licences differ by theme, and share-alike is the rule rather than the exception**: Base, Buildings, Divisions, and Transportation are ODbL; Places is CDLA Permissive 2.0 (with Apache-2.0 Foursquare and CC0 AllThePlaces sources); Addresses are permissive per source (V). A redistribution plan that assumes "permissive by theme" is wrong for four of six themes, so ODbL layers stay separately identifiable and carry their notice.

The valuable part for the ontology is **GERS**, Overture's stable global entity IDs: use them as `entity.external_refs` rather than inventing a building identifier scheme (V).

OSM remains irreplaceable for tag richness and update frequency; Geofabrik publishes per-country `.osm.pbf` extracts normally updated every day (V). Public extracts omit usernames, user IDs, and changeset IDs — full metadata is contributor-only (V) — which matters for attribution and for conflict-of-interest research. Intended division of labour:

- **Overture**: global base objects, stable IDs, bulk spatial analysis through DuckDB.
- **OSM/Geofabrik**: finer road/rail/natural tags, regional freshness, offline extracts.
- **Local store**: only the region subset under study, its object references, and inferred records.

Public infrastructure is not a production backend: public Nominatim is limited to an absolute maximum of 1 request/s (V), and the OSM tile servers prohibit bulk download, pre-seeding, tile archives, and offline use (V). Rendering and object query are separate concerns; if tiles are needed, generate them from local extracts (PMTiles) rather than consuming public tile capacity.

### 4.2 Satellite imagery — STAC for discovery, COG for reads

| Platform | Main assets | Role |
|---|---|---|
| Copernicus Data Space | Sentinel optical/SAR and other Copernicus products; OData, STAC, openEO, Sentinel Hub interfaces confirmed (V) | Primary source |
| Earth Search (Element 84) | 9 STAC collections incl. `sentinel-2-c1-l2a`, `sentinel-1-grd`, `landsat-c2-l2`, `cop-dem-glo-30/90`, `naip` (V) | Convenient cloud queries |
| Microsoft Planetary Computer | Multi-domain environmental data with STAC (E; confirmed only indirectly in this pass) | Redundant access and cross-domain analysis |
| NASA Earthdata | NASA Earth observation and science data (E) | Science-grade queries |
| OpenTopography | Global/regional elevation (E) | Terrain and occlusion modelling |

Copernicus' STAC catalog is **not confirmed to cover every collection** (U — the documentation page is JavaScript-rendered), but the fallback interfaces (OData, Sentinel Hub) are confirmed (V), so the adapter must implement a fallback path regardless. Provider roles: Sentinel-2 for land cover/vegetation/water/surface appearance; Sentinel-1 for radar where cloud and light defeat optical; Landsat for long historical surface change (USGS archive from 1972, V); Copernicus DEM for elevation and line-of-sight.

**Copernicus DEM is a surface model, not bare earth**: it includes buildings, infrastructure, and vegetation; GLO-30 is global 30 m; the licence is free but carries a mandatory © DLR/Airbus notice, requires registration, and EEA-10 (10 m) is restricted (V).

**Do not convert resolution into accuracy.** A 30 m DEM is a terrain sampling resolution, not a 30 m positional-accuracy guarantee, and it cannot reconstruct street-level acoustic geometry or building interiors. Satellite *availability* also depends on overpass time, cloud, and product coverage — the existence of an image of a place is not evidence of an observation at the event time.

### 4.3 Weather — three source types, never merged into one "weather fact"

| Class | Sources | What it is | What it can support |
|---|---|---|---|
| Global reanalysis | ERA5 (1940–present, hourly; native ~31 km / 0.28125°, CDS product on 0.25°), ERA5-Land (~9 km native, 0.1° distributed, from Jan 1950), ECMWF IFS (~9 km from 2017) (V) | Model reconstruction from historical observations | Plausibility of rain/wind/cold at a time and region, not a point measurement |
| Station observations | NOAA ISD (1901–present, >14,000 active stations), GHCN-Daily (>100,000 stations cumulative; only ~20,000 report in any 30-day window, ~25,000 with Tmax/Tmin) (V) | Direct observation, sparse and gappy | Independent cross-check near stations; day-scale climate checks |
| Event products | NASA GPM IMERG (half-hourly/daily/monthly; Early ~4 h, Late ~14 h, Final ~3.5 months latency), NOAA NEXRAD (US WSR-88D network; Level II archive on S3, old bucket/SNS retired 2025-09-01) (V) | Satellite/radar precipitation estimates | Event timing and spatial structure where coverage exists |

The rule that follows: preserve the **observation type** on every record (`observation_type: direct | model_estimate | derived`), and never let a reanalysis cell vote as if it were a rain gauge. **Name the grid you are using**: 0.25° is the CDS-interpolated ERA5 product, not the native model grid — writing "ERA5 is ~25 km" without that qualification misstates the dataset.

Open-Meteo is a convenient integration path for reanalysis and forecast products, but its free hosted API is non-commercial with exact caps of **<10,000 calls/day, 5,000/hour, 600/minute, 300,000/month**; the data is CC-BY 4.0 on that tier (V). It may serve prototypes and evaluation, never a default commercial path, and rate-limit/backoff handling must be provisioned for the hourly and per-minute caps, not only the daily one.

A concrete M1-adjacent validation task: test whether rainfall timing in a recording is consistent with a known region and time window's station/reanalysis record. That is a *consistency test*, not "rain sound locates a place".

### 4.4 Motion — the constraint-rich, access-poor domain

- **adsb.lol** publishes per-year historical repositories (`globe_history_YYYY`) on GitHub Releases, one release per day split into multiple tar parts, under ODbL 1.0 (V). The 2026 repository is roughly 1990 GiB (V) — the transfer and storage cost is real and must be planned, not assumed free. It is the default track dependency.
- **OpenSky** grants free historical Trino/MinIO access to university-affiliated researchers, governmental organisations, and aviation authorities; private or commercial entities must obtain a licence, and access is by application review (V) — research-tier cross-check only.

Three engineering problems must be modelled, not papered over: ADS-B broadcast coverage is not ground-truth coverage; tracks have gaps, varying sample intervals, and mixed position sources; and the recorder clock can be offset from the track clock. A track is therefore an **observation sequence with time and position uncertainty**, not an ideal continuous curve (this is why `uncertainty` and `missingness` are mandatory in the data contract).

For rail and public transport, the Mobility Database is confirmed to be a GTFS/GTFS-Realtime/GBFS catalog (V), but its feed and country counts are client-rendered and unverified (U); any plan citing "6,000 feeds in 100 countries" must confirm the count from the operator's API first. Distinguish GTFS Schedule (planned service), GTFS-Realtime (operator's live update), and **historical actual movement**, which neither guarantees. A timetable can form a candidate set; it cannot prove a specific vehicle was there.

### 4.5 Ecology and environmental sound — species evidence, not GPS

| Source | Asset | Access note |
|---|---|---|
| GBIF | Global species occurrence records | 300 records/page maximum and a hard 100,000-record query cap → asynchronous download service (V); monthly full snapshots on AWS Open Data, Planetary Computer/Azure, GCS and BigQuery (V); licence per dataset (CC0 / CC BY / CC BY-NC — E, not re-verified this pass) |
| iNaturalist | Georeferenced observations | "About 1 per second and around 10k requests a day" from the official page (V via archived copy; live page Cloudflare-blocked); sensitive-species coordinate obscuring is real but its canonical help page was not retrievable (U) |
| eBird | Bird observations and abundance | Data-request terms, research-use separation (E) |
| Xeno-canto | Animal sound recordings | Per-recording licences (U in this repository) |
| Freesound | Environmental audio | Per-file licences via API (E) |
| ESC-50 | 50-class environmental sound benchmark | CC BY-NC (E) |

The first-generation ecological module must not output coordinates. Its chain is **Species Evidence → Ecological Distribution → Regional Likelihood**: identify candidate species, then combine season, habitat, and occurrence records into a regional suitability, which enters the hypothesis as a prior with its own uncertainty. Public observation data is sampling-biased (popular birding sites are over-recorded), and a GBIF absence is not an absence of the species.

Two privacy rules are added here: sensitive-species locations are protected data — never re-infer and publish them; and ecological priors are context, not independent proof of a precise location.

### 4.6 Ocean, seismic, environment, astronomy

| Domain | Infrastructure | Caveats |
|---|---|---|
| Vessel tracks | NOAA Marine Cadastre AIS (US waters) | Site redirects to a JS hub; the frequently quoted 2009 start is unverified (U) |
| Sea state / marine weather | NOAA NDBC buoys | Meteorological observations, historical search, NetCDF/THREDDS, and HF-radar surface currents confirmed (V); wave-spectrum and ADCP record types unconfirmed (U) |
| Earthquakes | USGS event API; EarthScope FDSN waveforms (E) | Event catalog vs waveform are different evidence classes |
| Air quality | OpenAQ | API key required; free tier exactly 60/minute and 2,000/hour, 429 beyond (V); aggregated data still bound by upstream terms |
| Sun/moon/planets | NASA JPL Horizons (E) | Illumination and shadow constraints |
| Satellites | CelesTrak | Five-digit catalog numbers ran out on 2026-07-11 (SATCAT at 101263); new objects have no TLE — use OMM JSON/XML/CSV (V) |

Astronomy is a model case for this project: the sun's position is a deterministic function of time and place, so a shadow direction is a *computable constraint* with a residual — exactly the evidence type the ontology is built for.

### 4.7 Land cover — probabilities, not labels

| Dataset | Character | Role |
|---|---|---|
| Copernicus LCFM | "High-resolution (10 m), dynamic global land cover service (2020–2026)"; the 2020 10 m land-cover map and 2020 pan-tropical tree-cover density are available, and no later year is listed (V). "Annual" is not a term the source uses — do not call it an annual series | Long-term primary |
| ESA WorldCover | Global ~10 m maps for 2020 (v100) and 2021 (v200), 3×3° COG tiles (V) | Historical baseline |
| Google Dynamic World | 10 m near-real-time LULC, 9 classes plus a label and per-class probability bands summing to 1, from Sentinel-2 L1C since 2015-06-27 (V) | Temporal change and auxiliary verification |

Two cautions follow. WorldCover's two versions were produced by different algorithm versions, so apparent inter-annual change is confounded with method change (V). Dynamic World's probabilities matter: they let the inference carry class uncertainty instead of hard-coding a label into an environmental fact.

## 5. Why the world does not need to be downloaded

Three existing standards make federation practical, and none needs to be reinvented:

- **STAC** — find assets by space, time, and collection; get references, not bytes. (A community specification, not itself an adopted OGC standard; STAC API builds on OGC API - Features — V.)
- **COG** — read a window of a large GeoTIFF over HTTP Range requests.
- **GeoParquet** — columnar geospatial objects, filterable by region in DuckDB.

Worked example: a researcher studies an authorised experimental area in a given month. (1) Query STAC for the area and dates; (2) read only the needed COG windows; (3) pull buildings/roads/landform for the area from Overture GeoParquet via DuckDB; (4) fetch the historical weather window; (5) hand the declared evidence to the physical inferencers and record snapshot ids. No global imagery, building, or reanalysis copies are maintained.

## 6. The data fabric

```
World Data Catalog          dataset_id · provider_id · licence · extents · resolution ·
                            accuracy · observation type · uncertainty · access policy
        │
Provider Adapters           STAC · REST · OData · bulk file · object storage
        │
Query Planner               spatiotemporal filter · minimal source set · cost/information gain
        │
Data Cache                  regional and temporal subsets · content-addressed
        │
Normalization               CRS · time base · units · quality flags · missingness
        │
Evidence Registry &         source chain · raw references · immutable snapshots ·
Snapshot Store              checksums · access audit
        │
World Ontology + Physical Inference
```

The most important split is **Catalog vs Planner**: the catalog answers "what data exists in the world", the planner answers "what does *this* hypothesis need". A rain hypothesis does not fan out to shipping, seismic, and biodiversity sources; the planner selects the rain products, nearby stations, and terrain for the study area. That is both a cost control and an epistemic control — irrelevant sources manufacture spurious correlations.

## 7. One dataset contract

Every registered dataset carries these fields before first use. Field names are normative for the catalog; the ontology's `source` record references the profile by id.

| Field | Purpose |
|---|---|
| `dataset_id` | Global unique identifier |
| `provider_id` | Publishing institution |
| `source_uri` | Original query/download address |
| `license` | SPDX + terms snapshot + access level |
| `spatial_extent` | Geographic coverage |
| `temporal_extent` | Temporal coverage |
| `spatial_resolution` | Sampling/grid resolution |
| `positional_accuracy` | Declared positional error, **separate from resolution** |
| `temporal_resolution` | Sampling interval |
| `observation_type` | direct observation / model estimate / derived product |
| `uncertainty_model` | How error is represented |
| `version` | Provider dataset version |
| `retrieved_at` | When we fetched it |
| `content_hash` | Integrity check |
| `access_policy` | Permissions, quotas, purpose limits |

Two distinctions are load-bearing in inference: `spatial_resolution` ≠ `positional_accuracy` (a 10 m raster is not a 10 m guarantee), and `temporal_resolution` ≠ event-time precision (an hourly record does not place an event within the hour). Conflating either inflates confidence in exactly the way the evaluation design exists to catch.

**Missingness model.** Every profile states *why* a place/time can be missing — receiver coverage, cloud, revisit gap, station gap, observer bias. The verifier consumes it. "No observation" is never "observed nothing" ([ADR 0007](../decisions/0007-federated-world-data-infrastructure.md) §6).

## 8. Storage and runtime

| Tier | Holds | Technology |
|---|---|---|
| L1 metadata and index | Catalog, object ids, extents, task state | SQLite; PostgreSQL when a research node needs it |
| L2 regional analytical cache | GeoParquet, COG windows, track slices, query results | DuckDB + local object storage |
| L3 immutable evidence archive | Research inputs, model versions, snapshots, inference results | Content-addressed files + Parquet manifests |

Local-first deployment means the user selects a research area and time window; the system caches that subset, not the planet. Rendering: MapLibre GL JS for the map; self-owned regional tiles (PMTiles) when offline rendering is required.

Three cost classes must be planned, not discovered: **transfer** (object-storage requests, cross-region egress), **compute** (global raster/track processing, embedding search), and **maintenance** (versioning, dedupe, quality checks). The planner estimates transfer and request volume before fetching; a "free" API with a call cap is not free at research scale.

## 9. Governance is part of the architecture

Public ≠ free ≠ commercially reusable. The per-source record lives in [data-sources.md](data-sources.md); the enforcement point is the `LicensePolicyEngine` described in [ADR 0007](../decisions/0007-federated-world-data-infrastructure.md) §7 and [data-governance.md](../policy/data-governance.md) §7. Three consequences for the fabric:

- Licence is per dataset or theme, not per provider: Overture themes, GBIF records, and satellite products each carry their own terms.
- A research-only or non-commercial source can support evaluation and cross-checks, never a default product path.
- ODbL sources (OSM, adsb.lol) keep their share-alike layer separately identifiable, carrying notice, ready to be offered under ODbL if distributed.

## 10. Onboarding test for any data source

A source is worth a connector only if it passes five capability questions and one honesty question:

| Dimension | Question |
|---|---|
| Coverage | Which regions and times are actually usable, at what gaps? |
| Fidelity | Resolution, sampling interval, and stated error? |
| Reliability | Update cadence, API stability, outage history? |
| Verifiability | Can independent evidence test this dataset? |
| Legal reusability | Cache, redistribute, research, commercial? |
| Missingness | Why would a record be absent here, and is that modelled? |

Record count is not a criterion.

## 11. Build vs rent

**Rent / federate** (already maintained elsewhere): global maps, DEM, satellite imagery, reanalysis weather, species distributions, aircraft/vessel archives, public astronomy and ocean records.

**Build** (PhainoWeave's own): the federated catalog, cross-source identity mapping, spatiotemporal normalization, evidence source graph, physical constraint solvers, hypothesis comparison, research-task snapshots, reproducible reports.

**Research** (the actual original contribution): multi-modal evidence fusion, dependency correction, inverse physical inference, counterfactual verification, open-world uncertainty estimation, and reliable abstention under insufficient evidence.

The long-horizon capability worth calling out is **evidence-aware query planning**: accept a scientific question without a known location, and decide *which data to fetch next* by expected information gain — rather than brute-forcing the globe. That is where a Palantir-style data layer and inference logic actually combine.

## 12. First ten connectors and phasing

Order (plan, not commitment): 1 Overture Maps; 2 Geofabrik/OSM; 3 Copernicus DEM; 4 Open-Meteo/ERA5; 5 NOAA Global Hourly (ISD); 6 Copernicus/Earth Search STAC; 7 adsb.lol; 8 Copernicus LCFM; 9 GBIF; 10 JPL Horizons.

These map to fabric units in [ROADMAP §4.1](../roadmap/ROADMAP.md): D1–D3 (catalog, first adapters, planner) gate M1; D4 (satellite/station) gates M2; D5 (ecology/land cover) gates M3; D6 (distributed lifecycle) gates M4. The four survey milestones correspond as:

| Survey milestone | ROADMAP mapping | Acceptance |
|---|---|---|
| Federated Data Core | D1–D3 | A research area + time window yields one snapshot with version, licence, and source chain |
| Physical Evidence Integration | D4 | One event is independently tested by ≥2 source families, with support/conflict visible |
| Environmental Inference Benchmark | D5 + M3 evals | Blind test with known truth: coverage, error, calibration, cross-region generalization |
| Distributed World Evidence Infrastructure | D6 + M4 | Same task replays in another environment; differences attributable to data/model/software |

## 13. Verification status

Independent verification pass on 2026-11-04 (28 claims, primary sources fetched). **V** = verified and quoted; **E** = external claim pending verification; **U** = could not be confirmed. Anything graded E or U must be verified before the connector that depends on it is accepted ([ROADMAP](../roadmap/ROADMAP.md) §4.1).

| Claim | Grade | Evidence / qualifier |
|---|---|---|
| Overture six themes, GeoParquet on S3+Azure, GERS stable IDs | V | [docs.overturemaps.org](https://docs.overturemaps.org/) |
| Overture licences per theme: ODbL for Base/Buildings/Divisions/Transportation; Places CDLA-Permissive; Addresses per source | V | [attribution](https://docs.overturemaps.org/attribution/) |
| CDSE offers OData/STAC/openEO/Sentinel Hub | V | [APIs](https://documentation.dataspace.copernicus.eu/APIs.html) |
| CDSE STAC covers all collections | U | Page JS-rendered; adapter fallback required anyway |
| Earth Search has 9 STAC collections incl. `cop-dem-glo-30/90` | V | [collections](https://earth-search.aws.element84.com/v1/collections) |
| Planetary Computer STAC catalog | E | Confirmed only indirectly in this pass |
| ERA5 hourly 1940–present; **native ~31 km / 0.28125°**, CDS product on 0.25° | V (corrected) | [ERA5 data documentation](https://confluence.ecmwf.int/display/CKB/ERA5%3A+data+documentation) — the survey's "~25 km" describes the CDS grid only |
| ERA5-Land ~9 km native, 0.1° distributed, from Jan 1950 | V | [ERA5-Land documentation](https://confluence.ecmwf.int/display/CKB/ERA5-Land%3A+data+documentation) |
| Open-Meteo free tier: <10k/day, 5k/hour, 600/minute, 300k/month; non-commercial; data CC-BY 4.0 | V | [terms](https://open-meteo.com/en/terms) |
| ISD 1901–present, >14,000 active stations | V | [NCEI ISD](https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database) |
| GHCN-D >100,000 stations is **cumulative**; ~20,000 report in any 30-day window (~25,000 with Tmax/Tmin) | V (corrected) | [NCEI GHCN-D](https://www.ncei.noaa.gov/products/land-based-station/global-historical-climatology-network-daily) |
| GPM IMERG half-hourly/daily/monthly; Early ~4 h, Late ~14 h, Final ~3.5 months | V | [IMERG](https://gpm.nasa.gov/data/imerg) |
| NEXRAD US WSR-88D only; Level II on S3; old bucket/SNS retired 2025-09-01 | V | [AWS registry](https://registry.opendata.aws/noaa-nexrad/) |
| adsb.lol per-year repos, one release per day, ODbL 1.0, 2026 repo ≈1990 GiB | V | [globe_history_2026](https://github.com/adsblol/globe_history_2026) |
| OpenSky history: university/government/aviation-authority free access, commercial needs a licence, application review | V | [Trino docs](https://openskynetwork.github.io/opensky-api/trino.html) |
| Mobility Database is a GTFS/GTFS-RT/GBFS catalog; 6,000+/100+ countries | U | Counts client-rendered |
| GBIF 300 records/page, 100,000-record query cap, async downloads | V | [OpenAPI](https://techdocs.gbif.org/openapi/occurrence.json) |
| GBIF cloud distribution (AWS monthly snapshot, Azure Planetary Computer, GCS/BigQuery) | V | [cloud services](https://techdocs.gbif.org/en/cloud-services/) |
| GBIF per-dataset licences CC0 / CC BY / CC BY-NC | E | Not re-verified this pass |
| iNaturalist ~1 req/s and ~10k/day | V | [archived official page](https://web.archive.org/web/20261016165622/https://www.inaturalist.org/pages/api+recommended+practices) |
| iNaturalist obscures sensitive-species coordinates | U | Canonical help page not retrievable; policy applies regardless |
| OpenAQ API key; 60/min, 2,000/hour | V | [rate limits](https://docs.openaq.org/using-the-api/rate-limits) |
| CelesTrak: 5-digit catalog numbers exhausted 2026-07-11 (SATCAT 101263); new objects need OMM JSON/XML/CSV | V (corrected) | [GP data formats](https://celestrak.org/NORAD/documentation/gp-data-formats.php) — the survey's "in addition to TLE" understates it |
| Nominatim maximum 1 request/s; OSM tiles forbid bulk/offline | V | [Nominatim policy](https://operations.osmfoundation.org/policies/nominatim/) · [tile policy](https://operations.osmfoundation.org/policies/tiles/) |
| LCFM: 10 m global land cover service 2020–2026; 2020 map + 2020 pan-tropical TCD available; no later year listed | V (corrected) | [Global Dynamic Land Cover](https://land.copernicus.eu/en/products/global-dynamic-land-cover) — "annual" is not stated |
| WorldCover 2020 v100 and 2021 v200 at ~10 m | V | [ESA WorldCover](https://esa-worldcover.org/en/data-access) |
| Dynamic World: 10 m NRT, 9 classes + per-class probabilities, Sentinel-2 L1C since 2015-06-27 | V | [EE catalog](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1) |
| Geofabrik daily extracts; public extracts omit user names/IDs/changesets | V | [download.geofabrik.de](https://download.geofabrik.de/) |
| Landsat archive from 1972 | V | [Landsat 1](https://www.usgs.gov/landsat-missions/landsat-1) |
| Marine Cadastre AIS history from 2009 | U | Site redirects to a JS hub |
| NDBC wave spectra / ADCP records | U (partial) | Met observations and HF-radar currents confirmed; those record types not |
| Copernicus DEM: DSM incl. buildings/vegetation, GLO-30, free with © DLR/Airbus notice, registration, EEA-10 restricted | V | [COP-DEM](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM) |
| MapLibre GL JS open-source GPU renderer; PMTiles single-file archive over HTTP Range | V | [MapLibre](https://github.com/maplibre/maplibre-gl-js) · [PMTiles](https://docs.protomaps.com/pmtiles/) |
| STAC community spec; COG range reads; GeoParquet incubating OGC standard readable by DuckDB | V | [GeoParquet](https://geoparquet.org/) |

**Corrections applied to the survey text** (already reflected above): ERA5's native grid is ~31 km, not 25 km; GHCN-D's 100,000+ is cumulative, not live coverage; the 5-digit TLE range was exhausted on 2026-07-11, so OMM/JSON/CSV is required for new objects; Overture share-alike covers four of six themes; Open-Meteo's free tier also caps 5,000/hour and 600/minute. Two claims remain open: Mobility Database feed counts and Marine Cadastre's 2009 start.

## 14. Open questions

1. **ODbL derivative stance.** Whether an evidence graph citing OSM/adsb.lol rows is a derivative database is a legal judgment; the conservative engineering choice is a separately identifiable ODbL layer (see [data-sources.md](data-sources.md) §4). Owner: founder + counsel.
2. **Overture pinning.** Which release channel and version cadence the catalog commits to, and how theme-level licence changes propagate to stored snapshots.
3. **GTFS historical actuals.** Where a lawful archive of *actual* vehicle movement exists for the transit modality; without it, transit stays a candidate-set prior.
4. **LCFM year availability.** Which annual maps are actually published when the connector is built; plan for 2020 only.
5. **Station data as evidence.** Minimum station density/spacing rule for treating ISD as an independent constraint rather than a weak prior.
6. **Ocean and astronomy scope.** Whether AIS/NDBC/Horizons enter at M2 or stay behind the M4 distributed phase.
