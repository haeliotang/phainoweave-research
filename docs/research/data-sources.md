# Data Sources, Licences, and Snapshot Policy

**Status:** survey of record, 2026-11-04 · **Owner:** research · **Feeds:** [ROADMAP](../roadmap/ROADMAP.md) §4 (M1 data tiers), [benchmark-and-evals](../roadmap/benchmark-and-evals.md) §7 (reproducibility), [data-governance](../policy/data-governance.md) §4/§7 (inheritance, ingest checks), [world-ontology](../specs/world-ontology.md) §2/§7 (`data_snapshot_ids`, licence lattice).
**Scope:** which external datasets can constrain a world-state hypothesis, what each licence permits, how a snapshot is pinned, and what is refused. This note records facts about sources; it does not grant permissions. Policy is normative in [data-governance.md](../policy/data-governance.md). The architecture that consumes these sources — federated access, catalog, planner, snapshots — is [data-infrastructure.md](data-infrastructure.md) and [ADR 0007](../decisions/0007-federated-world-data-infrastructure.md); this file is the per-source legal and technical evidence behind that contract.

## 1. Scope and grading

A source is *candidate* if it constrains location, time, or environmental state from public physical data, and *admissible* only after its licence, access model, and redistribution rights are recorded as retrieved. Grades follow [landscape.md](landscape.md) §1: **V** = primary source fetched 2026-11-04 and quoted; **E** = assertion from a secondary source or the project's own docs; **U** = unverified lead (blocked, paywalled, or no licence statement found).

Two constraints run through everything below. First, **public data is not free data** (brief §12.4): every row is checked for licence, attribution, share-alike, and redistribution of *derived* data, not just access. Second, **the strongest applicable constraint wins** (data-governance §4): merging a research-only source into a public result does not launder it.

## 2. Source inventory

| Source | What it constrains | Coverage / resolution | Update cadence | Licence | Access model | Snapshot strategy | Attribution | Status |
|---|---|---|---|---|---|---|---|---|
| **adsb.lol daily history** ([repo](https://github.com/adsblol/globe_history), [site](https://adsb.lol/)) | Aircraft position/velocity vs time; candidate tracks for Doppler scoring | Global, crowd-sourced receivers; per-day tar releases, ~3 GB/day download (E: reproduction README); coverage gaps on some 2023–2024 days (E) | Daily releases | **ODbL 1.0** (V: repo README states it; derived crops stay ODbL) | Open download from GitHub release assets; no credentials | Pin release tag + UTC day + SHA-256 of downloaded parts; store only region crops, never delete the source hash | "adsb.lol, ODbL 1.0"; keep ODbL notice on derived crops | **V** |
| **OpenSky Network** ([terms](https://opensky-network.org/about/terms-of-use), [API](https://opensky-network.org/data/api), [Trino](https://opensky-network.org/data/trino)) | Same as above; independent track source for cross-checks | Global network; real-time REST + historical database interface | Continuous / daily partitions | Limited licence **for non-profit research and education only**; for-profit/commercial (including government and military contractors) requires a written licence; REST API in operational use requires prior written agreement (V: terms) | Registration + eligibility; historical interface behind account | If used at all: research tier, never a default product dependency; record dataset id, query, retrieval time, response hash; do not redistribute rows | OpenSky Network, non-profit research use notice | **V** |
| **Open-Meteo historical API** ([docs](https://open-meteo.com/en/docs/historical-weather-api)) | Surface temperature (sound speed `c`), wind, precipitation, cloud, pressure | ERA5 **0.25° (~25 km)**, ERA5-Land **0.1° (~11 km)**, ECMWF IFS **9 km** from 2017; hourly (V) | ERA5/ERA5-Land daily with **5-day delay**; IFS every 6 h (V) | Project [README](https://raw.githubusercontent.com/open-meteo/open-meteo/main/README.md) shows a CC BY 4.0 badge (V); the API docs present **non-commercial / commercial / self-hosted** tiers (V). Which licence covers data vs. code is ambiguous (U) — resolve before a product path depends on it | Open API, no key for the non-commercial tier; commercial terms otherwise | Pin model, variable set, UTC retrieval, response payload hash; record that the latest reanalysis day is provisional | "Weather data by Open-Meteo.com" + model attribution; state licence once resolved | **V / U** |
| **Copernicus DEM GLO-30** ([AWS registry](https://registry.opendata.aws/copernicus-dem/), [readme](https://copernicus-dem-30m.s3.amazonaws.com/readme.html)) | Ground/surface elevation; line-of-sight; predicted acoustic geometry | **30 m**, 2021 release; **digital surface model including buildings, infrastructure, vegetation**; GLO-30 has limited worldwide coverage because some country tiles are withheld; no ocean tiles (V) | Static; tile list can change | Free for the general public under the Copernicus DEM licence (V: registry/readme). Licence page itself not reachable from this survey (U) | Open S3 COG, no account | Pin DEM release (2021) + tile list + per-tile SHA-256; a tile change is a new snapshot, not an edit | "© DLR e.V. 2010–2014 and © Airbus DS GmbH 2014–2018, provided under COPERNICUS by the EU and ESA" (E: reproduction README; verify exact wording against the licence) | **V / E** |
| **OpenStreetMap** ([copyright](https://www.openstreetmap.org/copyright)) | Infrastructure features (rail, roads, airfields, industrial sites), candidate narrowing | Global vector database; variable completeness | Continuous edits | **ODbL 1.0**; attribution + licence statement required; documentation under CC BY-SA 2.0 (V) | Open; bulk extracts (Geofabrik/planet) preferred over live API | Pin dated planet/Geofabrik extract with SHA-256 and extract date; never query live data inside a reported run | "© OpenStreetMap contributors", licensed ODbL 1.0 | **V** |
| **GeoSound** ([HF dataset](https://huggingface.co/datasets/MVRL/GeoSound)) | Audio–place prior and benchmark comparisons; geo-cell split policy | 293,718 / 4,999 / 9,931 rows; 1.27 TB; aggregated from Freesound, Aporee, iNaturalist, Flickr/YFCC100M (V) | Static dataset releases | **Research use only**, per-source copyright retained, no blanket licence; imagery under Bing/EOX provider terms (V) | Hugging Face dataset access under research terms (gating details U) | Pin HF revision commit hash; record per-source attribution table; eval tier only | Per-row original uploader + platform; provider imagery credits | **V** |
| **GBIF** ([API](https://api.gbif.org/v1/dataset)) | Species occurrence ranges → ecological likelihood over region/season | Global occurrence records; per-dataset resolution and quality | Continuous, versioned downloads | Per-dataset: CC0, CC BY 4.0, CC BY-NC (V: search API returned CC BY 4.0 examples; mixed per dataset) | Open API; download account and DOI minting (E: standard GBIF practice, not fetched) | Pin download DOI + date, not the search endpoint | Per-dataset publisher citation + licence | **V (mechanism) / E (download flow)** |
| **iNaturalist** ([API](https://api.inaturalist.org/v1/observations)) | Species observations with location + date → range/season prior | Global observations; API reported 52.8M records for birds (taxon Aves) at fetch time (V) | Continuous | **Per-observation**: `license_code` varies (`cc-by-nc` observed); observations without an open code must be excluded (V: API field present; default-licence claim **U**) | Open API with rate limits; research use | Pin observation IDs + licence code at retrieval; exclude non-open licences | Observer + iNaturalist, per observation | **V / U** |
| **NOAA/NCEI ISD** ([product page](https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database)) | Hourly surface observations; weather-consistency cross-check | Global station network; hourly/sub-hourly | Daily/monthly archives | US federal work; generally not subject to domestic copyright (17 U.S.C. §105) — **legal reading; no licence statement located on the product page** (V page, U licence) | Open download (CDO / bulk) | Pin station list + file hashes + archive date | NCEI citation | **V / U** |

**Candidates not yet verified — do not use until a fetch closes them (U):**

| Candidate | Why it might matter | Open question |
|---|---|---|
| Copernicus CDS ERA5/ERA5-Land direct ([cds.climate.copernicus.eu](https://cds.climate.copernicus.eu/)) | Reproducible reanalysis without a commercial API tier | Copernicus licence text, account terms, request/version pinning — not fetched |
| IMGW public data portal ([danepubliczne.imgw.pl](https://danepubliczne.imgw.pl/)) | Regional Polish weather/warnings for central-European cases | Site and Regulamin exist (V); licence terms not read (Polish-language terms, not fetched) |
| radio aporee ::: maps ([aporee.org](https://aporee.org/maps/)) | Public-domain field recordings used as M1 Tier B audio | About/terms URL returned 404 in this survey; per-recording licence must be checked case by case |
| Xeno-canto ([xeno-canto.org](https://xeno-canto.org/)) | Bird recordings for acoustic-ecology constraints | API requires a personal key (V: API returned `Missing or invalid 'key'`); per-recording CC licences unverified |
| SoundingEarth | Second soundscape benchmark named by Sat2Sound | Dataset size, licence, and split policy unverified |

### 2.1 Data ceilings every report must state

The brief's risk register (§13) names these; the source table is where they become checkable. A report that uses any of these sources must repeat the relevant ceiling in its limitations section, in the source's own units:

| Ceiling | Consequence for a claim |
|---|---|
| ERA5's ~25 km grid (ERA5-Land ~11 km, IFS 9 km) | A weather-consistency constraint supports a regional residual, never a street-level one; sub-grid variability is unmodelled, not small |
| Copernicus DEM is a DSM, not a DTM | Building and canopy heights enter acoustic and line-of-sight geometry; the error is structured (urban/forest), not random noise |
| Crowd-sourced ADS-B has gaps and uneven receiver density | "No track" is not "no aircraft"; absent data must be able to produce abstention, not a confident negative |
| Species ranges come from opportunistic occurrence records | Range edges and vagrants are uncertain; the constraint is a likelihood over region and season, not a boundary |
| OSM completeness varies by country and feature class | Absence of a mapped feature is not absence of the feature; infrastructure constraints inherit mapping bias |

## 3. Licence-compliance implications

**ODbL share-alike (OSM, adsb.lol).** ODbL distinguishes a *Derivative Database* (must be offered under ODbL if distributed) from a *Produced Work* (attribution only). Whether an evidence graph that cites OSM/track rows is a derivative database is a legal judgement we cannot make here; the conservative engineering choice is to keep ODbL-derived tables in a separately identifiable layer, carry the ODbL notice, and be prepared to publish that layer under ODbL if we distribute it. Extracting a "substantial part" triggers the same obligation, so per-run crops and derived region tables inherit the licence — not just the raw download. Attribution: "© OpenStreetMap contributors" plus a licence link; for adsb.lol, its ODbL notice plus feeder acknowledgements.

**Research-use-only (GeoSound, OpenSky).** Neither can back a default product path. They are admissible for benchmarks, ablations, and cross-checks under a `research` sensitivity class (data-governance §2), with results published as aggregates, metrics, and hashes — not as redistributed derived data. Per-source audio rights inside GeoSound vary (Freesound CC0/CC BY/CC BY-NC, Aporee, iNaturalist, Flickr), so a single "GeoSound licence" statement would be false; the per-row attribution table travels with the snapshot.

**Eligibility-gated (OpenSky).** The terms grant a limited licence for non-profit research and education; commercial or for-profit use needs a written licence, and operational REST API use needs a prior agreement (V). Consequence for M1: **default to adsb.lol (ODbL) and Tier A/B audio**; if OpenSky is used, it is a research-tier cross-check, pinned and disclosed, and no published default path may depend on it. This is a business-model constraint, not a technical one, and it belongs in the M1 report's data section.

**Attribution-only (Open-Meteo CC BY 4.0, NOAA).** Credit the provider, state the model and retrieval date, and indicate modifications where the licence requires it. The commercial tier of Open-Meteo is a contract question: a paid plan is not the same as CC BY 4.0, and a default product path must record which one it is on.

**Free-with-attribution (Copernicus DEM).** The attribution string is part of the licence and must appear in any published product derived from it; the licence page was not reachable during this survey, so the exact wording remains **E/U** until a reviewer verifies it.

**Incompatible combinations.** A research-only source and an ODbL source merged into one distributed table produce an unpublishable record under data-governance §4.3. The resolution is not to relicense either: publish the claim with aggregate statistics and hashes, state the access condition, and keep the merged table node-internal.

**Derived regions.** Where a source forbids redistribution of derived data, outputs may still be published as coarse regions and aggregate metrics at the inherited granularity cap (data-governance §4.5); a region that could re-identify a recordist or a residence is capped at `sub_region` or above regardless of what the licence allows.

**Per-source obligation matrix.** The four obligations that change engineering decisions, per source. "Derived redistribution" means redistributing a database built from the source, not a map image or an aggregate statistic.

| Source | Attribution | Share-alike | Derived redistribution | Default product path |
|---|---|---|---|---|
| OSM | Required ("© OpenStreetMap contributors", ODbL link) | Yes, on derivative databases | Allowed under ODbL | Yes, with ODbL layer kept separable |
| adsb.lol | Required (ODbL notice + feeder credits) | Yes, on derivative databases | Allowed under ODbL | Yes |
| Open-Meteo | Required (provider + model) | No | Allowed under CC BY if that is the applicable licence (U) | Only on a resolved licence tier |
| Copernicus DEM | Required (DLR/Airbus/ESA string) | No | Allowed, attribution retained | Yes |
| NOAA NCEI | Citation expected | No | Allowed (US federal work) | Yes, subject to licence verification |
| GeoSound | Per row and per platform | Per source, not project-wide | Forbidden as a blanket grant | **No** — eval tier only |
| OpenSky | Provider notice | No | Only within the research licence | **No** — research cross-check only |
| GBIF | Per dataset | Per dataset | Per dataset licence | Only for CC0/CC BY datasets |
| iNaturalist | Per observation | Per observation | Only open-licensed observations | Only after per-row filtering |

## 4. Snapshot and version pinning policy

Every reported number must trace to an **immutable data snapshot** with a retrieval date. This is invariant I6 and the practical defence against external data drift (brief §13). The mechanics below complement [benchmark-and-evals §7](../roadmap/benchmark-and-evals.md) and ontology §7 (`inputs.data_snapshot_ids`); they do not replace them.

**Snapshot identity.** A snapshot id is a content-addressed digest of a canonical manifest containing: source id and version, dataset release/tag/DOI, query parameters or subset definition (bounding box, time window, station/tile list), retrieval timestamp in UTC, SHA-256 of the exact retrieved bytes, SHA-256 of the licence/terms text as retrieved, adapter name and version, and sensitivity class. Snapshots are immutable. A re-fetch that differs for any reason mints a **new** snapshot id with `supersedes` pointing at the old one; the old one is never edited, and old runs keep resolving to it.

**Every result cites it.** A run record references `data_snapshot_ids`; a claim whose run does not resolve to a snapshot is unverifiable and must not be published. The retrieval date is the second half of the citation — a snapshot hash without a date does not say when the world was observed as that.

**Three cache tiers.** (1) Raw bytes, content-addressed and immutable; (2) parsed/normalised output, pinned to the raw hash plus adapter version; (3) analytical extracts (Parquet/DuckDB), rebuildable and never authoritative. Tier 2 must reproduce byte-identically from tier 1 + adapter version, or it is a new derivation with its own record.

**Detecting silent revision.** A provider can change data without changing its URL. Detection: (a) periodic re-fetch and byte-hash comparison, with a diff report rather than an in-place update; (b) on replay, verify the snapshot bytes' hash before running; a mismatch marks the run *data-changed* and is classified, never silently accepted; (c) prefer provider-native versions where they exist — GBIF download DOI, Hugging Face revision commit, CDS request id, Copernicus DEM tile list, adsb.lol release tag; (d) respect update cadence: ERA5's 5-day delay means "yesterday's final" is provisional, so pin the issue/retrieval date rather than the nominal day; (e) keep the licence text hash, because a relicense must surface as a new source version, not a surprise (ontology §2).

**What gets cached and what gets recorded.**

| Cache | Granularity | Immutability | Recorded with the snapshot |
|---|---|---|---|
| ADS-B release parts / region crops | day × region | raw parts immutable; crops derived | release tag, day, crop bbox, download hash, crop hash |
| DEM tiles | tile | immutable | release (2021), tile list, per-tile hash |
| Weather responses | point × model × variable set × day | immutable | model, variables, issue/retrieval time, payload hash |
| OSM extract | dated planet/Geofabrik cut | immutable | extract date, hash, ODbL notice |
| Audio (Tier B) | clip | immutable | clip id, licence, attribution, source URL, recordist pin (if any) |
| Benchmark rows (GeoSound etc.) | dataset revision | immutable | HF revision, per-source attribution table, research-use flag |
| Licence text | per source version | immutable | terms hash, retrieval date, access-level map |

**Manifest fields a run must be able to print.** The M1 report template asks for a per-source snapshot table ([benchmark-and-evals §6](../roadmap/benchmark-and-evals.md)); this is the minimum that makes it verifiable. Anything missing is an open item in the report, not an implicit default.

```text
snapshot_id        sha256 over the canonical manifest below
source_id          external key, stable across versions
dataset_version    release tag / DOI / HF revision / tile release
subset             bbox, time window, station or tile list, filter expression
retrieved_at       RFC 3339 UTC
payload_sha256     exact bytes as received (before parsing)
license_id         SPDX identifier or provider licence name
license_terms_sha  hash of the terms text as retrieved
adapter            name + version of the ingest code
sensitivity        public | research | restricted (data-governance §2)
attribution        the exact string required by the licence
supersedes         previous snapshot_id, when this is a revision
```

## 5. What we must not ingest

Refused at ingest, per brief §12 and [data-governance §7](../policy/data-governance.md), regardless of what a licence says:

1. **Personal data** — identifiable voices, private interiors or residences, licence plates, any data whose purpose or effect is locating a person.
2. **Private recordings without consent** — including material whose provenance or consent basis cannot be established.
3. **Restricted law-enforcement, intelligence, or targeting datasets** — and anything whose intended use is enforcement, military, or operational command.
4. **Licence terms that forbid inference or derived redistribution** — if the terms prohibit the analysis we do, the data is inadmissible even if the file is downloadable.
5. **Unlawfully obtained data** — unauthorised access, breach dumps, intercepted private communications, covert recordings of private spaces.
6. **Provenance-free datasets** — if the chain from provider to bytes cannot be stated, the source is `restricted` with no publication rights until resolved. Silence in a licence is not permission.

Precise-place outputs are not an ingest rule but a publication cap: the region floor and authorization requirements in [ethics-and-privacy.md](../policy/ethics-and-privacy.md) apply to every published claim independently of source licence.

## 6. Verification status and reconciliation for the Lead

Verified by fetching (V, 2026-11-04): adsb.lol ODbL; OpenSky terms; Open-Meteo resolution and cadence; Copernicus DEM DSM/coverage/free basis; OSM ODbL; GeoSound research-only terms and counts; GBIF per-dataset licence mechanism; iNaturalist per-observation licence field; NOAA ISD product page exists. Stated in secondary sources only (E): Copernicus DEM attribution wording; adsb.lol day-download volume and 2023–2024 gaps. Unverified (U): Copernicus DEM licence page; Copernicus CDS licence; IMGW terms; radio aporee terms; Xeno-canto licences; SoundingEarth; GeoSound gating mechanics; NOAA ISD licence statement; OpenSky historical workflow beyond the REST terms.

**Questions the Lead must resolve before M1 data is declared:**

1. **OpenSky default-path decision.** Confirm that OpenSky is research-tier cross-check only, and that M1's default track dependency is adsb.lol (ODbL). This is a licence term, not a preference (V: terms).
2. **ODbL derived-database stance.** Whether the evidence graph counts as a derivative database is a legal question; until answered, the engineering rule is "keep ODbL-derived tables separable and publish them under ODbL if distributed."
3. **GeoSound admissibility.** Confirm eval-only research tier and that per-row attribution can be preserved without redistributing audio; confirm gated access accepts an automated research account (U).
4. **Copernicus DEM attribution.** Verify the exact licence wording and canonical URL (the product page was unreachable); the current string is E from a third-party README.
5. **Brief reconciliation.** [landscape.md](landscape.md) §4 records that the brief's "Audio Geolocation: A Natural Sounds Benchmark" now resolves to *Bioacoustic Geolocation: Species Sounds as Geographic Signals* (ICML 2026). The brief's §14 should cite the current title.
6. **Species data scope.** GBIF/iNaturalist are listed because the ontology has ecological constraints, but M1 does not use them; confirm they stay M3+ so the source-manifest format is not over-built at M1.
7. **Weather-resolution wording.** The brief (§13) and ROADMAP (§4) say "ERA5 is ~25 km (some fields ~9 km)". Fetched facts: ERA5 is 0.25° (~25 km), ERA5-Land is 0.1° (~11 km), and the 9 km figure is the ECMWF IFS model available from 2017, not ERA5 (V). Recommend the brief cite the three products separately; no claim in this repo should attribute a 9 km ERA5 grid.
