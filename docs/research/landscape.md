# Research Landscape — Prior Art, Reusable Parts, and the Gap

**Status:** survey of record, 2026-11-04 · **Owner:** research · **Feeds:** [founding brief](../product/founding-brief.md) §14, [ROADMAP](../roadmap/ROADMAP.md) §4, [benchmark-and-evals](../roadmap/benchmark-and-evals.md).
**Scope:** what already exists that PhainoWeave can reuse, what must not be mistaken for capability, and where the missing layer actually is. This is a research note, not evidence: no capability claim may cite it (ROADMAP §0).

## 1. Purpose and method

The question is narrow: **who already turns ambient physical traces into location/time/state, with what precision class, under what licence, and how would we know they are right?** Four kinds of prior art count:

1. peer-reviewed methods with a described error model (Doppler kinematics, distributed acoustic sensing);
2. public benchmarks and datasets that fix a task and a split (natural-sound geolocation, soundscape mapping, cross-view geolocation);
3. field methodology with an evidence discipline but no automation (OSINT geolocation verification);
4. standards and product patterns we can borrow structurally (PROV-O; Palantir's public positioning).

Media demonstrations count as evidence that a thing is *possible*, never as a capability estimate. Every claim below carries one of three grades:

| Grade | Meaning in this note | How to falsify it |
|---|---|---|
| **V — verified-in-repo** | Checked against a primary document fetched during this survey (2026-11-04); the link is the receipt. No code exists in this repository yet, so "in-repo" means "primary-source verified and dated in this file"; the grade upgrades to a reproduced run at M1. | Follow the link; the quoted fact is visible in the document. |
| **E — external claim** | Asserted by a secondary source (press, another project's README, its own self-report) and **not** independently reproduced here. | Rerun the experiment; until then, treat the number as a hypothesis about someone else's code. |
| **U — unverified lead** | No retrievable primary source, or the source was blocked, paywalled, or nondeterministic on fetch. | Must not be promoted into a spec, an ADR, or a report without a fetch. |

Unless a date is given, "fetched" means 2026-11-04. Numbers are quoted with the qualifiers their source uses; where the source hedges, the hedge is kept.

## 2. Acoustic geolocation from aircraft Doppler

### 2.1 The November 2026 demonstration (E)

A YouTube video by the channel **colsto**, "I discovered a sound that leaks your exact location (and it's everywhere)" ([youtube.com/watch?v=UytYrhYLOKI](https://www.youtube.com/watch?v=UytYrhYLOKI); title and channel verified via the YouTube oEmbed endpoint, fetched 2026-11-04; upload date **unverified** — the watch page was not retrievable anonymously from this environment) presents a method for locating a recording from aircraft-noise Doppler curves matched to flight tracks, with a demonstration. The reproduction project states the author "released no code" and that its own scripts are an "independent implementation of the steps he describes, not his pipeline" ([README](https://github.com/mojomast/hermes-aircraft-doppler-geolocation), V).

The press restatement is TechRadar, published **3 November 2026** ([article](https://www.techradar.com/computing/cyber-security/youtuber-discovers-aircraft-noise-trick-that-can-geolocate-your-videos-to-within-100m-doppler-effect-pinpoints-locations-from-just-60-seconds-of-audio), V; graded **E** for the capability number): location "to within 100 meters" from "less than one minute of sound", hedged in the article's own summary as "apparently accurate to within 100m". The quoted demonstration is one clip — the author describes the audio as "just from some random security camera" — presented as an educational OSINT demonstration, not a benchmark. No dataset, code, error distribution, or uncertainty interval accompanied it. **The 100 m figure is therefore a single-case media claim, not a transferable precision class.** The brief's "November 2026" is consistent with the 3 November 2026 press date; the video's own date is **U**.

### 2.2 The independent reproduction (E for all its numbers)

[`mojomast/hermes-aircraft-doppler-geolocation`](https://github.com/mojomast/hermes-aircraft-doppler-geolocation) is MIT-licensed, created **2026-11-02** (two days before this survey), v0.3.1 released 2026-11-03; a Hermes community plugin by Kyle Durepos, explicitly "not a Nous Research product" (V: repository metadata and README fetched 2026-11-04). Its README's own status sentence is the most useful line in the whole literature so far: it "locates clean multi-pass recordings to within about 1 km but mostly fails on unseen clips: 2 of 18 held-out runs came in under 3 km" (E).

Method, as documented (V for the description; E for the results): narrowband components follow `f_obs(t) ≈ f0 · c / (c − v_r(t))`; detection uses a whitened 1 s spectrogram, harmonic sum with CFAR, Viterbi multi-ridge tracking, joint harmonic-family fit, segment linking, and acceptance tests; the scorer predicts each event's curve from real ADS-B tracks (turns included, emission time solved, Copernicus DEM ground height, Open-Meteo temperature for sound speed `c`) at every grid point, fits a robust `f0` scale, penalises passes that should have been heard, and tempers the posterior by a Birge ratio times `temper_extra = 4`. An opt-in broadband model uses the Lloyd's-mirror ground-reflection fringe delay to recover CPA range and microphone height.

| Split, frozen once | Runs | Solved | < 3 km | Median error (solved) | Truth in padded 95 % area |
|---|---|---|---|---|---|
| Tune, tonal | 24 | 12 | 5 | 7.2 km | 9/12 |
| Held-out, tonal (14 clips) | 14 | 8 | **1** | **12.1 km** | 6/8 |
| Held-out, broadband on (18 clips) | 18 | 11 | **2** | **13.2 km** | 8/11 |

Source: [README "Real-world results"](https://github.com/mojomast/hermes-aircraft-doppler-geolocation#real-world-results) and [docs/evaluation.md](https://raw.githubusercontent.com/mojomast/hermes-aircraft-doppler-geolocation/main/docs/evaluation.md) (V; figures **E**). The three facts that matter for us:

1. The method mostly **does not generalize**: 6 of 14 held-out tonal runs produced no events; the single held-out `ok` flag was 13.2 km wrong and its 95 % area missed the truth. A confidence flag is not a guarantee.
2. **Calibration was an afterthought and is visibly weak**: without extra tempering, unpadded 95 % areas contained the truth in 0 of 23 earlier runs; `temper_extra = 4` was chosen on 12 tune rows and covers 9 of 12 tune solves, while `temper_extra = 64` covers 11 of 12 only by inflating the 95 % area to the whole 15 km search disc. This is the failure our brief's §11 exists to prevent.
3. The evaluation design is better than the method: clips split **by location before tuning**, held-out splits run **once** with frozen settings, ground truth from recordist pins or spotting locations with stated `truth_unc_m` (300–1500 m), exclusions recorded with reasons, audio never redistributed (V: `docs/evaluation.md`). That is close to the discipline [benchmark-and-evals](../roadmap/benchmark-and-evals.md) requires and is worth copying.

**Reconciliation flag.** The brief says "2 of 18 held-out recordings within 3 km". That is the broadband-on row. The tonal row is 1 of 14. Both appear in the same README; any citation must name which run set it refers to.

### 2.3 What is technically transferable

| Component | Mechanism | Reusable as | Caveat |
|---|---|---|---|
| Doppler curve extraction | Harmonic-family tracking with Viterbi ridges, acceptance tests, segment linking | A `Feature` extractor with residuals and rejection reasons | Needs tonal lines; jets usually produce none (E) |
| Candidate-region scoring | Forward-predict the full curve at every grid point from real tracks; solve emission time; DEM + temperature for `c` | The first `Constraint`/verifier pair (M1) | Grid likelihood is not a posterior until calibrated; tempering is a fudge factor, not a model |
| Interval constraints | Two overflights at a fixed offset, or a known start time, resolve the along-track ambiguity a single pass cannot | Temporal evidence type; also a lesson for interval arithmetic | Requires track coverage for *both* passes; missing days kill it |
| Broadband multipath | Lloyd's-mirror cepstral delay → CPA range and mic height | Second acoustic event class, independent error model | Needs flat ground, a close pass, and the CPA inside the recording; two held-out clips regressed when enabled (E) |
| Residual reporting | χ² per event, CPA-distance consistency, normalised residuals | The verifier's output contract | The repo does not expose residual distributions as a dataset; we would have to add that |

### 2.4 What does not transfer

- **The 100 m number.** One hedged demonstration, no code, no distribution, no abstention behaviour. It is not a capability claim and must not become a target in an eval.
- **The reproduction's pipeline as a product.** Two days old, one author, 8 stars, no audit, no provenance store, no replay digest; its own evaluation says it mostly fails on unseen clips.
- **Track access treated as free.** Historical track data is licence- and eligibility-constrained (see [data-sources.md](data-sources.md)); the reproduction downloads ~3 GB per uncached day from adsb.lol (ODbL) and notes missing 2023–2024 release days (E).
- **"Confidence: ok" as a decision rule.** It was wrong on the only held-out case where it fired (E). Our verification verdict must be a residual statement, not a badge.

## 3. Acoustic sensing: arrays versus one microphone

**V:** *Detection of aircraft noise using distributed acoustic sensing with a buried telecommunication cable*, npj Acoustics, published **2025-03-27** ([nature.com/articles/s44384-025-00007-8](https://www.nature.com/articles/s44384-025-00007-8)). Four weeks of continuous DAS on a telecom cable buried under the Curtin University campus, Perth; 10 m gauge length; aircraft signatures at **70–120 Hz at distances up to 2.5 km**; **propeller aircraft only**, no jet detections, attributed to jets' higher-frequency emission requiring a smaller gauge length.

Implications for a single-microphone project:

- A spatial array samples the wavefield and can estimate bearing/geometry from channel-to-channel coherence; a single microphone yields one scalar frequency-versus-time curve and inherits the mirror/along-track ambiguities the reproduction documents (E). Array sensing is the physically correct way to turn acoustic detection into a geometric constraint.
- Gauge length is a hard frequency ceiling: the sensing geometry, not the algorithm, decides what is detectable. The same is true of a phone microphone's high-pass filtering, which is why commentary-heavy livestream audio failed in the reproduction (E).
- DAS is infrastructure-bound and not deployable as a portable instrument; it belongs to the **Edge Node / Research Node** modes of the brief, not M1.
- The paper reports detection and flight-parameter estimation, not point geolocation; the abstract announces no open dataset or code, and availability was not established (V for the abstract; dataset and code availability **U**). Treat DAS as an M3+ sensing modality with an ethics review, not as an M1 shortcut.

## 4. Audio–place representation

| Work | What it contributes | Limit for PhainoWeave |
|---|---|---|
| **Sat2Sound** — "A Unified Framework for Zero-Shot Soundscape Mapping", arXiv [2505.13777](https://arxiv.org/abs/2505.13777), accepted at **EarthVision 2026** per the arXiv comment (V); checkpoints MIT-licensed on [Hugging Face](https://huggingface.co/MVRL/sat2sound) (V); evaluated on GeoSound and SoundingEarth per the abstract (V) | Joint audio/text/satellite embedding; "soundscape concepts"; hyper-localised soundscape *prediction*, not source recording localisation | It predicts what a place *should* sound like, so at best it is the learned prior B1, never the verifier; its retrieval claims are region-scale and its training data is research-only |
| **Bioacoustic Geolocation: Species Sounds as Geographic Signals** — arXiv [2505.18726](https://arxiv.org/abs/2505.18726), v3 updated 2026-06-17, accepted to **ICML 2026** per the arXiv comment (V) | Benchmarks audio geolocation with species ranges; oracles, species-centric baselines, hybrid range+retrieval; spatiotemporal aggregation; movie audio+visual case studies; asks whether localisation is "within a country, state, or even city" (V: abstract) | Its own framing is coarse: country/state/city, not site. Species range is a *constraint* (an ecological likelihood), which fits our ontology better than a learned classifier does |
| **GeoSound** — [MVRL/GeoSound](https://huggingface.co/datasets/MVRL/GeoSound) (V), built from Freesound, Aporee, iNaturalist, Flickr/YFCC100M; 293,718 train / 4,999 val / 9,931 test rows; 1.27 TB; PSM cell-based geographic splits (V: dataset card) | A geo-referenced audio+imagery benchmark with a defensible geographic split policy | **Research use only**, per-source copyright retained, no blanket licence, imagery under provider terms (V). Cannot back a default product path; eval-only, and derived redistributables must be checked per source |

**Title reconciliation.** The brief cites this paper as "Audio Geolocation: A Natural Sounds Benchmark". The arXiv ID matches, but the current title is *Bioacoustic Geolocation: Species Sounds as Geographic Signals* and the venue is ICML 2026. The brief's title appears to be an earlier version; the Lead should confirm and amend the brief's §14/§13 wording so citations resolve.

**What to take:** the species-range constraint as an evidence item with its own error model (not a vote that multiplies with an acoustic score); the geo-cell split policy; the learned prior as baseline B1, fitted on tuning split only, no backbone training (ROADMAP §5).
**What not to build:** another soundscape foundation model. The brief already refuses foundation-model training; Sat2Sound's existence is an argument for wrapping, not training.

## 5. Visual geolocation: reuse cross-view retrieval, do not rebuild it

**GeoBridge** — "A Semantic-Anchored Multi-View Foundation Model Bridging Images and Text for Geo-Localization", **CVPR 2026**, pp. 27793–27803, Song et al. ([CVF open access](https://openaccess.thecvf.com/content/CVPR2026/html/Song_GeoBridge_A_Semantic-Anchored_Multi-View_Foundation_Model_Bridging_Images_and_Text_CVPR_2026_paper.html), V). Bidirectional matching across drone/street/satellite views plus language-to-image retrieval through textual semantic anchors; the paper introduces the **GeoLoc** dataset, "over 50,000 pairs" from **36 countries** with descriptions, and states that code, dataset, and pretrained models **will be released** at the project repository (V: abstract). An extended version, GeoBridge++, is arXiv [2512.02697](https://arxiv.org/abs/2512.02697) (V). The official repository [MiliLab/GeoBridge](https://github.com/MiliLab/GeoBridge) exists but declares **no licence file** as of 2026-11-04 (V: GitHub API metadata) — code cannot be reused until that is resolved.

What to reuse at M3: the retrieval pattern (index reference imagery; coarse-to-fine candidate pruning; embed query and candidate into a shared space); the evaluation habit of cross-view and language queries; the dataset's existence as a public cross-view reference.

What not to rebuild: a new cross-view foundation model, or a visual-geolocation training pipeline. Visual matching is one `Constraint` over candidate regions, and it is exactly the kind of modality whose precision triggers the brief's §12.5 ethics review before merge. Its failure modes are imagery vintage, occlusion, seasonal mismatch, and reference coverage — all of which belong in residuals, not in prose.

## 6. Verification practice: what OSINT already got right

**V:** Bellingcat's [Online Investigation Toolkit, Geolocation category](https://bellingcat.gitbook.io/toolkit/categories/geolocation) (fetched 2026-11-04) catalogues the practical stack: OpenStreetMap proximity search, Shadow Finder and ShadeMap (solar/shadow constraints), SunCalc (solar geometry), GeoHints (regional infrastructure details), GeoNames, and a natural-language OSM query tool. Its [Guides & Handbooks](https://bellingcat.gitbook.io/toolkit/resources/guides-and-handbooks) page points to the *Verification Handbook* series ([datajournalism.com](https://datajournalism.com/read/handbook/verification-3)) and the **Berkeley Protocol on Digital Open Source Investigations** ([OHCHR](https://www.ohchr.org/en/publications/policy-and-methodological-publications/berkeley-protocol-digital-open-source)) (V that the links exist and are listed; the Berkeley Protocol page itself returned HTTP 403 to this survey and its content is therefore **U**).

The discipline worth encoding, stated as practices rather than tool names (E: standard OSINT method as described in those guides, not independently audited here):

1. **Capture and hash before analysis.** The artifact is fixed, and every later statement cites that exact artifact.
2. **Separate what is seen from what is inferred.** A shadow direction is observed; the time-of-day that follows is inferred; the location that follows is inferred again.
3. **Chronolocate and geolocate independently** before combining them; a time that fits a place is not evidence for the place.
4. **Argue against yourself.** Name the alternative hypothesis and the observation that would have falsified the chosen one.
5. **Preserve the evidence chain** so a third party can re-walk it; publication is an argument with links, not a verdict.

PhainoWeave automates steps 1, 2 and 5 (hashes, layers, run records) and should make steps 3 and 4 typed: contradictions coexist (I5), and abstention is a scored outcome (I8). It should not pretend Bellingcat's judgement — the "does this street furniture match" step — is automatable today.

## 7. Provenance standards: W3C PROV-O

**V:** *PROV-O: The PROV Ontology*, W3C Recommendation **30 April 2013** ([w3.org/TR/prov-o](https://www.w3.org/TR/prov-o/)). Three starting classes — `prov:Entity`, `prov:Activity`, `prov:Agent` — with `wasDerivedFrom`/`used`/`wasGeneratedBy`/`wasAttributedTo`, an expanded layer (`Plan`, `Bundle`, `Collection`, `Revision`, `hadPrimarySource`, `alternateOf`, `invalidatedAtTime`), and qualified influence patterns for attaching role and time to a relation.

**Adopted, normatively:** the mapping in [world-ontology.md](../specs/world-ontology.md) §8 — every record exports as a PROV-O graph; `InferenceRun` is an `Activity`; observations/features/hypotheses/verifications are `Entity`; inferencers are `SoftwareAgent`; `Plan` models the inferencer spec; `Bundle` models a run; `Revision` models reanalysis; `hadPrimarySource` links an observation to its source; `wasGeneratedBy`/`qualifiedAssociation` carry versions and parameters.

**Where we extend it, because PROV-O is descriptive and cannot express these:**

| Gap | Our extension | Where it lives |
|---|---|---|
| Uncertainty and probability | typed `uncertainty` value object; region probability; residual nodes | ontology §5, §8 |
| Contradiction | first-class conflict edges and `pw:role = contradicts`; no last-writer-wins | ontology §4, I5 |
| Evidence independence | `independence_key` + group-wise aggregation; PROV has no notion of correlated evidence | ontology I7, benchmark-and-evals §5 |
| Bitemporality | store `_record_time` plus claim-level event time; PROV distinguishes only generation time | ontology I3 |
| Licence and sensitivity | licence lattice meet over roots; `pw:accessLevel`, `dcterms:license` | ontology I10, [data-governance](../policy/data-governance.md) §4 |
| Verification as test, not assertion | `Verification` is both entity and activity, with typed residuals; PROV-O has no verdict | ontology §2, §8 |

Do not invent a provenance vocabulary, and do not claim "PROV-O conformant" until the export/round-trip test in ontology §8 exists and passes.

## 8. Design analogies: what is borrowed from Palantir, and what is refused

This project borrows **patterns**, not products or internals. Palantir's internal architecture is not public; the only claims made here are from the public positioning pages fetched 2026-11-04 (V for the quotes, E for any inference): [Foundry](https://www.palantir.com/platforms/foundry/) — "Run your business as code. The Ontology/AI-powered operating system for the modern enterprise."; [AIP](https://www.palantir.com/platforms/aip/) — "Run LLMs and other models on your private network with full control."; [Apollo](https://www.palantir.com/platforms/apollo/) — "autonomous software deployment … full roll backs"; [Gotham](https://www.palantir.com/platforms/gotham/) — "The Operating System for Defense Decision Making."

| Pattern | What we take | What we refuse |
|---|---|---|
| Ontology as the operational layer (Foundry) | The nine-object model is the product's API; actions are typed and permissioned; every surface reads from the same record (I9, ontology §10) | Ontology as a sales surface; customer-data gravity; "run the business as code" as a goal |
| Investigation surface (Gotham's public positioning) | M2's one workspace: hypothesis set + map + timeline + evidence graph derived from one run record | The mission. Gotham is positioned as defense decision-making; the brief excludes military, targeting, real-time command, and person-level surveillance outright — that exclusion is structural, not a style note |
| Agent tooling with evals (AIP) | Tool/inferencer registry, eval suite that compares versions, LLMs propose but never verify (brief §5.3) | Autonomous action on the world; an LLM as the last step of verification |
| Staged deployment of pieces (Apollo) | Environment pinning, replay parity, release channels for inferencers, attributable deltas (M4) | Auto-rollout to operational deployments, "autonomous deployment" as an aspiration |

The honest summary: the four disciplines are **organisational ideas with public analogues**, and the part of Palantir we will not copy is the part its own Gotham page leads with — operational command. Where the brief says "not a Palantir clone", this is what it means: same ontology/investigation/eval/deployment discipline, opposite use boundary.

## 9. Synthesis: the gap, per modality

| Modality / prior art | What it can constrain | Precision class (claimed → observed) | Verification data | Maturity | Failure modes |
|---|---|---|---|---|---|
| Aircraft Doppler, tonal (reproduction, **E**) | radial geometry, CPA slant range, relative time alignment | demo 100 m (E, one clip) → 1–3 km best case, 12–13 km median on held-out (E) | ADS-B tracks; recordist pins; synthetic passes | community code, 2 days old, unaudited | no tonal line (jets), turning passes, mirror/along-track ambiguity, track gaps, calibration |
| Aircraft Doppler, broadband (Lloyd's mirror, **E**) | CPA range and mic height | 0.19 km on one tuned case → 2 of 18 held-out < 3 km (E) | same | opt-in, experimental | needs flat ground, close pass, CPA inside clip; regressions observed |
| Buried DAS array (**V**) | detection + flight parameters of propeller aircraft, ≤ 2.5 km | detection, not point localisation | none public | one 4-week field study, no dataset/code | gauge-length frequency ceiling, infrastructure-bound, no jets |
| Weather reanalysis (ERA5/ERA5-Land, **V**) | regional state, sound speed, rain/wind consistency | ~25 km (ERA5) / ~11 km (ERA5-Land) / 9 km (ECMWF IFS from 2017) grids (V) | station observations; reanalysis uncertainty | mature | sub-grid variability, revision drift, not street-level |
| Terrain (Copernicus DEM GLO-30, **V**) | elevation, line-of-sight, echo/obstruction geometry | 30 m, DSM including buildings and vegetation (V) | independent elevation data | mature, static | surface-model bias, temporal mismatch (canopy), withheld tiles |
| Solar geometry (ephemeris, SunCalc-class) | time and orientation given a place, or place given a time | high precision, weak constraint alone | ephemerides; shadow tools | mature | requires visible shadows or clear sky context; repeats across places |
| Species ranges / bioacoustics (**V**) | ecological likelihood over region and season | country/state/city scale (V: abstract framing) | occurrence records (GBIF/iNaturalist) | research benchmark, new | vagrants, introduced species, audio quality, range-data gaps |
| Learned audio–place embedding (Sat2Sound, **V**) | prior over plausible soundscape | region-scale retrieval, not site | benchmark splits (GeoSound, research-only) | published 2026, code out | domain shift, training-data contamination, licence prevents product path |
| Visual cross-view retrieval (GeoBridge, **V**) | candidate region from reference imagery | street/region with reference coverage | GeoLoc, 36 countries | published 2026; no licence declared on repo | imagery vintage, occlusion, seasonal mismatch, coverage |
| Infrastructure / OSM (**V**) | presence of repeating features; candidate narrowing | high local precision, low alone | OSM snapshots | mature, open (ODbL) | mapping completeness and vintage; features repeat across regions |

**The gap.** None of the above emits a *typed* world-state hypothesis with residuals, independence keys, contradiction edges, and a replay digest. The aircraft-Doppler code is a single-modality pipeline with a calibration fudge; the benchmarks emit predictions; OSINT emits prose; PROV-O emits provenance without uncertainty; Palantir's public positioning sells an operational layer, and falsifiability is not part of that pitch. **The missing layer is the constraint-and-verification substrate, not another modality model** — which is what the brief claims and what this survey supports.

## 10. Reproduction targets for M1

Ordered by dependency. "Reproduced" is a checkable claim about *our* run records, not about the upstream project's numbers. All targets obey [benchmark-and-evals](../roadmap/benchmark-and-evals.md): sealed split, preregistered rule, replay digest.

| # | Target | What "reproduced" means | Data and licence | Why first |
|---|---|---|---|---|
| R1 | Synthetic Doppler pass with known truth (Tier A) | Pipeline recovers `f0`, speed, and CPA slant range within the injected-noise prediction; the **single-pass along-track ambiguity reproduces** (km-scale error without a time hint), and a second pass or known start time collapses it to the grid step | Author-generated synthetic audio; no third-party licence | Cheapest falsifier of the kinematics and the ambiguity claim; no data dependency |
| R2 | Tonal held-out re-run on a legally usable subset | On a sealed subset of publicly licensed recordings with pinned ADS-B crops, our error distribution is *consistent* with the published one (1/14 < 3 km, median ≈ 12 km) or every per-clip difference is attributed to a named cause (release gap, DEM tile, temperature source); failures counted, not dropped | CC0/public-domain clips; adsb.lol daily history under ODbL | Tests the headline failure honestly; if we cannot reproduce the failure, the model is wrong |
| R3 | Broadband best-case re-run (`man_hg0903` 0.19 km, `man_hg0909` 0.33 km, E) | Event counts and CPA ranges reproduce within tolerance on the same audio and pinned tracks; report whether the result survives without the tuned gates | Public-domain field recordings; adsb.lol ODbL | Distinguishes a real physical model from a tuned anecdote |
| R4 | Prior-only baseline (B1) on sealed geographic cells | Frozen pretrained audio features + linear/nonparametric head, fitted on tuning cells only, produce a *reported* error distribution, coverage curve, and reliability diagram on held-out cells | GeoSound for cache/benchmark comparison only (research-only, eval tier) plus openly licensed audio for the sealed split | M1's H1 needs a credible non-strawman prior; this fixes B1 before any combined claim |
| R5 | Snapshot and replay determinism | Same clip + pinned snapshots (tracks, DEM tiles, weather, model hashes) ⇒ identical residual vector and identical run-record digest; one-field perturbations (track day, +1 K, one DEM tile) produce classified, attributable deltas | Pinned snapshot fixtures; no redistribution of restricted data | Without this, R1–R4 numbers are anecdotes; it is also the M0→M1 handoff |

**Also required at M1, though not a "reproduction":** the mismatch between the demo's 100 m framing and the reproduction's held-out median must be stated in the report, with the demo classified as an external case study (per ROADMAP §0 and brief §13).

## 11. Open research questions, ranked by value

| Rank | Question | Why it matters | Cheapest evidence that would settle it |
|---|---|---|---|
| 1 | Does a physical constraint add value over a learned prior on **unseen** recordings at fixed coverage (H1)? | The entire project rests on it; the available external evidence is mostly negative for tonal Doppler (E) | M1 preregistered B1 vs B3 on a sealed split with calibration guard |
| 2 | How much of the acoustic evidence is one event wearing several hats (harmonics, segments, multipath), and how badly does naive pooling inflate confidence? | Correlated evidence is the brief's named top risk (I7); the Doppler case has built-in correlation | Independence-key ablation and ΔECE on paired single-event cases (benchmark-and-evals §5) |
| 3 | What is the attainable precision floor for single-microphone acoustic place inference? | The 100 m claim is unverified; the honest class may be km-scale | R2/R3 error distributions with CIs; region coverage at 1, 10, 100 km² |
| 4 | How should a single-microphone constraint be fused with array/DAS observations without double-counting the same wavefield? | Arrays convert detection into geometry; fusing naively manufactures confidence | M3 protocol once a DAS dataset or simulation exists; independence-key design |
| 5 | How should track-data coverage, gaps, and crowd-sourced bias be represented as evidence rather than as a nuisance? | adsb.lol has missing days and uneven coverage (E); OpenSky is eligibility-gated (V) | Track-coverage covariate in the prior; abstention on no-track cases |
| 6 | How large is the DSM-versus-DTM error term in acoustic and terrain constraints, and when does it dominate? | GLO-30 is a surface model including buildings and vegetation (V) | Perturbation study across urban/forest tiles |
| 7 | Do audio–place embeddings transfer across geography when trained on research-only benchmarks? | Determines whether B1 is usable at all beyond its training regions | Geographic isolation split on openly licensed audio |
| 8 | Can verification discipline be typed without becoming bureaucracy? | Ontology over-engineering is a named risk; OSINT practice is prose for a reason | M0 rejection tests + M2 replay/delta checks |

## 12. Evidence ledger

| # | Claim or fact | Grade | Source (fetched 2026-11-04) |
|---|---|---|---|
| 1 | Video exists, title/channel | V | [YouTube oEmbed](https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=UytYrhYLOKI&format=json) |
| 2 | "Within 100 m", "apparently accurate", single security-camera clip, published 2026-11-03 | V for text, E for capability | [TechRadar](https://www.techradar.com/computing/cyber-security/youtuber-discovers-aircraft-noise-trick-that-can-geolocate-your-videos-to-within-100m-doppler-effect-pinpoints-locations-from-just-60-seconds-of-audio) |
| 3 | No code released by demo author | V | Reproduction [README](https://github.com/mojomast/hermes-aircraft-doppler-geolocation) |
| 4 | Reproduction repo metadata, MIT, created 2026-11-02, v0.3.1 2026-11-03 | V | [GitHub](https://github.com/mojomast/hermes-aircraft-doppler-geolocation) / [API](https://api.github.com/repos/mojomast/hermes-aircraft-doppler-geolocation) |
| 5 | Held-out results (1/14 tonal, 2/18 broadband) | E | README §"Real-world results"; [docs/evaluation.md](https://raw.githubusercontent.com/mojomast/hermes-aircraft-doppler-geolocation/main/docs/evaluation.md) |
| 6 | DAS study facts (10 m gauge, 70–120 Hz, 2.5 km, propeller only, 2025-03-27) | V | [npj Acoustics](https://www.nature.com/articles/s44384-025-00007-8) |
| 7 | Sat2Sound venue + MIT checkpoints | V | [arXiv 2505.13777](https://arxiv.org/abs/2505.13777); [HF model card](https://huggingface.co/MVRL/sat2sound) |
| 8 | Bioacoustic paper title, v3, ICML 2026 | V | [arXiv 2505.18726](https://arxiv.org/abs/2505.18726) |
| 9 | GeoSound size, splits, research-only terms | V | [Dataset card](https://huggingface.co/datasets/MVRL/GeoSound) |
| 10 | GeoBridge CVPR 2026, GeoLoc 50k pairs/36 countries, no repo licence | V | [CVF page](https://openaccess.thecvf.com/content/CVPR2026/html/Song_GeoBridge_A_Semantic-Anchored_Multi-View_Foundation_Model_Bridging_Images_and_Text_CVPR_2026_paper.html); [GitHub API](https://api.github.com/repos/MiliLab/GeoBridge) |
| 11 | Bellingcat toolkit contents and guide list | V (links); U (Berkeley Protocol content) | [Geolocation category](https://bellingcat.gitbook.io/toolkit/categories/geolocation); [Guides](https://bellingcat.gitbook.io/toolkit/resources/guides-and-handbooks) |
| 12 | PROV-O terms, REC 2013-04-30 | V | [W3C](https://www.w3.org/TR/prov-o/) |
| 13 | Palantir product-positioning one-liners | V for quotes, E for inference | [Foundry](https://www.palantir.com/platforms/foundry/) · [Gotham](https://www.palantir.com/platforms/gotham/) · [AIP](https://www.palantir.com/platforms/aip/) · [Apollo](https://www.palantir.com/platforms/apollo/) |

**Open unknowns this survey could not close:** the demonstration video's upload date and full method (U); whether the demonstration's 100 m figure has an uncertainty interval (U); the Berkeley Protocol's precise evidentiary requirements (U, page blocked); whether OpenSky's historical archive is reachable for a non-profit research project without a written agreement beyond the REST API terms (V for the terms, U for the operational workflow); whether GeoSound's gated access accepts an automated research account (U). None of these block M1's design; all of them must be resolved before a report cites them.
