# Data Governance Policy

**Status:** adopted 2026-11-04 · **Owner:** Haelio Tang · **Language:** English (canonical) · **Scope:** every `Source`, `Observation`, `Feature`, and derived record in PhainoWeave, in every deployment mode.

**Authority.** This policy implements invariants I2 (provenance by default), I6 (reproducibility), and I10 (licence and sensitivity travel with data) from the [founding brief](../product/founding-brief.md), and the tier system in [ADR 0005](../decisions/0005-privacy-and-dual-use.md). Field names, the licence lattice, and the six typed actions are normative in [world-ontology.md](../specs/world-ontology.md); unacceptable uses are in [ethics-and-privacy.md](ethics-and-privacy.md). Licence terms are facts about sources, not conventions of this project.

## 1. Principles

Data governance here is the mechanism that makes the privacy policy enforceable, not a separate compliance exercise. Three rules carry most of the weight: nothing enters the graph without provenance and a licence; nothing derived can be less restrictive than its inputs; and nothing is published without enough context that a third party can rerun it. Everything below applies those rules.

## 2. Sensitivity classes

Every `Source` and every derived record carries exactly one class. In the ontology, three of them are the `license.access_level` values (`public | research | restricted`) and the fourth is an ingest refusal, not a stored level.

| Class | Stored as | Definition | Concrete examples | Default handling |
|---|---|---|---|---|
| `public` | `access_level: public` | Lawfully obtained, openly licensed, redistribution permitted, not about an identifiable person. | Open weather reanalysis; open satellite imagery; OpenStreetMap extracts; public track archives under their access terms. | Readable by any authenticated role; publishable after the §6 checklist. |
| `research` | `access_level: research` | Lawful for research, not cleared for open redistribution, or not yet reviewed. | Node-internal recordings under a data-use agreement; consigned datasets; derived features whose licence or quality is unresolved. | Readable within the node by researchers and reviewers; publication requires the owner's terms plus review. |
| `restricted` | `access_level: restricted` | Identifiable, sensitive, or contractually limited; misuse causes direct harm; purpose-bound access. | Recordings with voices or private interiors; precise calibration ground truth; non-redistribution data; any combination that could identify a residence. | Requires an authorization record and purpose; reviewer visibility; no raw publication; derived output capped by the source. |
| `prohibited` | not stored; no `Source` | Cannot lawfully or ethically be held at all. | Breach dumps; intercepted private communications; personal data without lawful basis; covert recordings of private spaces; military targeting data; data whose terms forbid inference. | Refused at ingest. Not stored, not quarantined for later use, not kept "for testing". |

Class is an input to the granularity cap, not a substitute for it: a `public` dataset can still be capped at `region`, and a `restricted` dataset can still be publication-eligible at the sub-region band with review. The `sensitivity.person_data` boolean is separate from class and, when true on any reachable root, makes a record unpublishable (world-ontology §I10 M0 policy).

## 3. Access control model

The ontology defines three roles as a hierarchy, `researcher < reviewer < publisher`, with a minimum role per action (world-ontology §9). Policy adds separation-of-duties constraints *inside* that hierarchy; it does not remove capability from a higher role.

| Action | Minimum role | Additional policy conditions | Audit |
|---|---|---|---|
| `ExtractFeatures` | researcher | The observation's effective licence permits local computation; `restricted` data needs an authorization record; extractor name and version declared. | Row per call, with data hashes. |
| `ProposeHypothesis` | researcher | Location and time present and non-degenerate; prior in (0,1) recorded; ≥1 evidence id unless `prior_only`; the target is a place, time, or state, never a person. | Row per call. |
| `RunSimulation` | researcher | Cited constraints resolve at the pinned version; residual function registered; environment recorded. | Run record; full parameters. |
| `ChallengeHypothesis` | researcher | Challenger ≠ the creating inferencer unless `self_challenge = true`; conflict edges are recorded, not resolved by rank. | Row per call. |
| `RequestReview` | researcher | ≥1 verification or an explicit `insufficient` verdict; blocks `PublishEvidence` until a review decision exists. | Row; becomes a review record under `docs/policy/reviews/`. |
| `PublishEvidence` | publisher | ≥1 verification with verdict `pass` or `partial`; bundle licence and sensitivity check passes; bundle digest recorded; publisher ≠ hypothesis creator when more than one identity is configured. | Row with publication id and cap evidence. |

**Separation of duties.** A reviewer must not review a claim they authored or ran. For `restricted` claims, publication requires a different identity from the hypothesis creator when multi-actor mode is configured. Local single-researcher mode grants all three roles to one identity; the audit records `role_source: local_bootstrap`, and the self-publish restriction is then structurally unenforceable. The policy states that limitation rather than implying a separation that does not exist.

Read, derive, and publish scopes follow from the table and the class rules:

| Role | Read | Derive | Publish |
|---|---|---|---|
| `researcher` | `public` and `research`; `restricted` only with an authorization record | all five research actions (`ExtractFeatures`, `ProposeHypothesis`, `RunSimulation`, `ChallengeHypothesis`, `RequestReview`) | no |
| `reviewer` | as researcher, plus the review bundle for a claim under review | research actions by hierarchy, but nothing on a claim they review | no |
| `publisher` | `public`, `research`, and the derived bundle it is asked to publish; raw `restricted` only with an authorization record | research actions by hierarchy | yes, after the §6 checklist, and not as creator of a `restricted` bundle in multi-actor mode |

**Prohibited reads.** No role reads `prohibited` data, because it is not held. An ingest attempt is logged as a refusal.

## 4. Derivation inheritance

Three properties propagate through the evidence graph: licence, sensitivity, and the granularity cap. The ontology implements the meet (strictest wins); policy requires that the inherited values are materialised on the derived record at creation, not only recomputed at read time, so that an audit of the record is self-contained.

1. **Licence lattice.** `access_level` is ordered `public < research < restricted`; `person_data` is joined by OR; `max_output_granularity` is ordered `none > region > point` in strictness, and the allowed output is the meet, i.e. the coarsest. The effective licence of a record is the meet over every reachable L1 root's `license_snapshot` and the current `source.license` (world-ontology §I10).
2. **Snapshot, not guess.** An observation's `license_snapshot` copies the source terms at ingest, so a later relicence can narrow a record's terms but never widen them.
3. **Unpublishable combinations.** A record with `person_data = true` on any reachable root is unpublishable; `max_output_granularity = none` forbids `location_hint` and `claim.location` entirely.
4. **Region floor.** Under an effective ceiling of `region`, a `spatial_region` must have a bounding extent of at least 0.05° per axis or H3 resolution ≤ 7. The floor is owned by [ethics-and-privacy.md](ethics-and-privacy.md) §3, where the policy bands around it are stated.
5. **No upgrade.** No inferencer, verifier, reviewer, or publication step may relax an inherited licence, class, `person_data` flag, or granularity cap. Only a new source with looser terms, or a new authorization for a defined purpose, changes an output, and both appear in the record.
6. **Deletion does not relax.** Removing or tombstoning a source does not loosen constraints on records derived from it; it marks them dependent on a tombstoned source.
7. **Publication inherits.** A published bundle's granularity is the minimum of the effective cap and any authorization's maximum. No reviewer may raise it, and no publication template may default to a finer tier.

*Example:* open ERA5 weather (`public`, capped `region`) combined with a personal recording (`restricted`, capped at the sub-region band) yields a derived record that is `restricted` and capped at that band, carrying both licences and the recording's access terms — even if the analysis is 95% weather.

## 5. Retention and deletion

**Raw observations.** Immutable records in SQLite, with media bytes in a content-addressed blob store outside it (world-ontology §10). Retention follows the source: public data is retained while the project maintains the corpus; consigned or contracted data for the agreement's term; `restricted` data only as long as the authorized purpose requires, with the authorization's expiry as a retention trigger. Deletion is an explicit, logged operation, never an unaudited background collection.

**Derived records.** Retained with the run that produced them. Unpublished derived records may be deleted with their run; published claims and the evidence needed to rerun them are retained indefinitely, because withdrawal is a tombstone, not a deletion.

**Right to erasure, and its limit.** Append-only evidence and a right to erasure genuinely conflict: rewriting history would destroy the auditability that is the product, and silently deleting an observation would make a published claim unreproducible. We resolve it with a tombstone, not a rewrite:

1. The observation's content bytes are removed from the blob store and from derived caches; the `observation` row remains, because M0's tables are append-only and there is no legal update or single-row delete.
2. Its identifier, content hash, provenance, licence, and the tombstone record — requester basis, date, approving role, affected records — are retained. The observable tombstone is an observation whose `content_hash` no longer resolves to a blob.
3. No further inference may use the record. Records derived from it are marked dependency-tombstoned; published claims that relied on it receive a published erratum and, where the claim cannot stand without the erased content, are withdrawn by tombstone with the reason stated.
4. Audit entries are content-free references and are not deleted; erasing them would erase the fact that the query happened.

We tell requesters this plainly: we can stop using and stop publishing the content, and we cannot pretend the event of its use never occurred. Two limits are stated rather than hidden. M0 has no `tombstoned` status field, so "marked" currently means an unresolvable blob plus the tombstone record, and adding a status is an open ontology question; and the only legal single-operation delete in M0 is a whole-store purge, which destroys identifiers, so we do not use it for erasure. Where law requires more than this, the conflict is escalated to counsel rather than resolved by quietly shrinking the log.

## 6. Publication policy

A published claim must carry all of the following. A publication missing any item is a defect, not an incomplete preprint.

| Field | What it must contain |
|---|---|
| Claim identity | Stable claim id, version, and the `Hypothesis` and `Verification` references it rests on. |
| Evidence | Observation hashes, `Source` ids, data snapshot ids, dataset versions, and snapshot dates. |
| Licence | Every applicable licence, attribution text, and inherited use restrictions. |
| Granularity | Emitted tier, the effective cap, and, for `precise`, the authorization id. |
| Residuals | The physical constraint residuals, including those that argue against the claim. |
| Calibration | The calibration statement and its evidence, or an explicit `unverified`. |
| Abstention | When the system would have abstained, and what evidence would have changed the verdict. |
| Reproducibility | Inferencer versions, model weight hashes, parameters, seed, ontology version, and environment digest. |
| Independence | Correlated-evidence handling; paired evidence from one event is not counted as two votes. |
| Conflict | Contradicting hypotheses and conflict edges, if any. |
| Time | Event time and record time, kept distinct. |
| Review | The review record id, where the claim came from a review-triggering change. |

The published bundle is a content-addressed manifest with a recorded digest. It is a falsifiable artifact, not a press release: if a third party cannot rerun it from what is published, the publication is incomplete regardless of whether the claim is true. Negative and null results are published as first-class claims, per the evaluation stance in [benchmark-and-evals.md](../roadmap/benchmark-and-evals.md). Whether a published bundle should become a distinct "verified fact" object is open (world-ontology §15 Q5); until then the bundle is the M0 unit of publication.

## 7. Third-party licence compliance at ingest

Checked before a `Source` is created; an unchecked source is not admissible. Per source: the `spdx` identifier and the terms as retrieved (a snapshot of the terms, not a link that may change); permitted purposes including inference and derivative works; redistribution rights for raw and derived data separately; attribution and notice requirements; share-alike obligations; access-control and rate terms for eligibility-gated archives; `access_level`; `person_data` and `max_output_granularity`; any export or jurisdictional restriction; and any ethics approval for human-subjects material. If any field is unknown, the source is treated as `restricted` with no publication rights until it is resolved. Silence in a licence is not permission.

**Prohibited ingest.** Never ingested, regardless of licence text: data obtained by unauthorised access; breach dumps; intercepted private communications; covert recordings of private spaces; personal data without a lawful basis; data whose terms forbid inference or derivative works; military or targeting datasets; datasets whose provenance cannot be established; and anything whose safe use would require per-query legal review. The last item is deliberate: if a dataset is only safe under case-by-case legal advice, the default is to refuse it.

**Enforcement point.** These checks are not a checklist run by a human once. The data fabric ([ADR 0007](../decisions/0007-federated-world-data-infrastructure.md)) registers every dataset under a profile that carries this compliance record, and the `LicensePolicyEngine` is consulted at ingest, at derivation, at sharing, and at publication — including per-dataset and per-theme licences (an Overture theme or a GBIF record is not interchangeable with its parent catalogue's headline licence). A connector that cannot answer a licence question is registered `restricted` and cannot feed a default path. The engine's decisions are audit rows, not console warnings.

**ODbL is reviewed per data flow, not as a blanket rule.** ODbL distinguishes a *derivative database* (may inherit the ODbL obligation if distributed), a *collective database* (the ODbL layer stays separable), and a *produced work* (typically attribution-only). Whether an evidence graph that cites OSM or adsb.lol rows is a derivative database is a legal judgment that depends on how the data is combined and used. The project therefore (a) keeps ODbL-derived layers separately identifiable with their notices, (b) reviews the first use of each ODbL source as a data flow and records the conclusion, and (c) makes no repo-wide claim in either direction — "using OSM forces the ontology open" is as unsupported as "ODbL is free" ([ADR 0011](../decisions/0011-privacy-forensics-and-publication-rulings.md) §7).

## 8. Audit trail requirements

Every one of the six typed actions, every `precise` query, every authorization-record change, every publication, and every deletion or tombstone writes an audit row. The ontology's row carries actor, declared role, `action_kind`, target ids, the referenced data hashes and snapshot ids, canonical parameter digest, run id where applicable, timestamp, and policy digest, under a monotone sequence number — audit rows are infrastructure, not ontology objects, and have no prefixed id (world-ontology §9). The policy layer adds requested and emitted granularity, authorization id, Research Node, and outcome including refusals; the bitemporal `event_time`/`record_time` distinction applies where an audit event is itself about a past event. Rows are append-only; editing or truncating them is a security incident. The log is queryable by reviewers and maintainers, exportable as evidence, and retained longer than the data it references. It stores references and hashes, not observation content, so it remains lawful to keep after a tombstone. M0 claims append-only ordering, not cryptographic tamper-evidence.

## 9. Consignment: joining a Research Node

An external researcher joins by agreement, not by account creation. The agreement names the permitted purpose, the datasets, the granularity cap, a no-redistribution clause, consent to audit, the publication-review requirement, and the exit terms; it is signed by the researcher and the hosting institution and countersigned by a maintainer. Identity is verified; consigned datasets additionally require the data owner's approval.

A consigned researcher holds the `researcher` role on that node only: they may run `ExtractFeatures`, `ProposeHypothesis`, `RunSimulation`, `ChallengeHypothesis`, and `RequestReview` on the datasets their agreement covers, at the cap the agreement sets. They may not `PublishEvidence`; outputs leave through the publication workflow with the host as publisher. They may not ingest data they brought themselves without a new licence check, and prohibited ingest applies to them exactly as to anyone else. At exit, node access and credentials are revoked, audit entries are retained, and derived records stay with the node under the same inherited constraints. Consignment is a privilege granted per project, not a status.

**Node jurisdiction.** Before a Research Node offers any sensitive inference capability, its operating policy states the jurisdiction whose law governs it and records the independent legal and ethical review that cleared that capability; a node that cannot state both does not offer it. While the project has a single maintainer, the absence of separation of duties is stated as a limitation wherever publication or authorization separation is described ([ADR 0011](../decisions/0011-privacy-forensics-and-publication-rulings.md) §4).

## 10. Maintenance

Review annually, after any incident, and before any new deployment mode. A change to the sensitivity classes, the role table, the inheritance rules, or the prohibited-ingest list requires an ethics review record and, if it changes a boundary, an ADR. Retention periods are set per node and must be stated in the node's operating policy rather than inferred from this document.
