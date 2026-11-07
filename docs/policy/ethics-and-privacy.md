# Ethics and Privacy Policy

**Status:** adopted 2026-11-04 · **Owner:** Haelio Tang · **Language:** English (canonical) · **Scope:** every observation, inferencer, verifier, run, publication, and deployment mode of PhainoWeave, binding on maintainers, Research Node operators, consigned researchers, and users of published outputs.

**Authority.** This policy operationalises §12 of the [founding brief](../product/founding-brief.md) and [ADR 0005](../decisions/0005-privacy-and-dual-use.md). Object fields and the six typed actions are specified in [world-ontology.md](../specs/world-ontology.md); data handling rules are in [data-governance.md](data-governance.md). Where this policy and an Accepted ADR disagree, the ADR wins and this policy is amended.

---

## 1. The capability, stated ethically

The engine returns a distribution over place, time, and environmental state, with residuals and an abstention path. Its ethical weight is not accuracy. A distribution over place is a statement about the people who made the recording, and at sufficient precision it becomes an identification of them. Two structural facts drive everything below. First, place-level inference can deanonymize people without ever naming a person: a residence, a workplace, a school run, and a time of day are often enough. Second, the marginal cost of precision is low and falling, so permission to be precise must be structural, not a matter of good intent. The policy therefore constrains what the system can emit, not only what its authors wish it used for.

## 2. Threat model by adversary

Each row is a concrete misuse path with a concrete harm and the control that actually applies. Controls are described in §4; this section names what we are defending against, not what we hope.

| Adversary | Concrete misuse path | Harm | Primary control |
|---|---|---|---|
| Stalker or former partner | Records audio or video of a target, submits it, asks for the precise recording location, travels there. | Physical violence; the target cannot consent, cannot know the query happened, and may not know a recording exists. | `precise` requires an authorization record and review; runtime refusal without it; default `region`; repeated tight-area queries trip Node-level detection. |
| Doxxer of a private residence | Infers street or building from a window frame, reverb, and overflight timing; cross-references public records; publishes the address. | Home address exposure leading to harassment, swatting, or property crime; irreversible for the occupant. | No residence-level output; `precise` reviewed case by case; publication inherits the strictest source cap; any claim whose practical use is residence identification is rejected at review. |
| Harassment campaign | A group runs many coarse queries, or one person runs queries under several accounts, and merges partial results. | Sustained targeting of one person by a distributed group; each individual query looks innocuous. | Node-level rate limits and pattern detection; authorization records bound to identity; audit; node suspension. Partial only: see mosaic effect below. |
| State surveillance | Bulk ingestion of ambient sensors, correlation across a population, watchlists of who was present where. | Chilling effects, political targeting, and irreversible loss of anonymity at population scale. | `person_level` never emitted; no real-time or operational mode; prohibited use with no procurement route; refusals logged. |
| Corporate surveillance and discrimination | Infers neighbourhood condition, flood or noise exposure, upkeep, or occupancy signals and feeds them into insurance, lending, or pricing models. | Opaque, unappealable economic exclusion at scale; the subject never learns an inference was made. | Inferred environmental attributes of a private property are `restricted` data and not a publishable project output; prohibited use; no commercial redistribution of derived per-property scores. |
| Law-enforcement investigative use | Requests precise localization of a place, event, or person under investigative authority. | Mission creep into surveillance; precedent for warrantless or unreviewed use. | Not a supported use; enforced refusal by default; the narrow forensics exception in §5.3 with conditions and audit. |
| Military targeting | Localizes a place or event in support of kinetic or intelligence targeting. | Loss of life; the capability becomes a weapon component. | Prohibited absolutely; no exception, no "defensive" or "dual-use" carve-out, no lawful-authorization override; no military data, support, or examples. |
| Capability extraction into a closed tool | Forks or embeds the engine in a proprietary product; copies the pipeline but drops the verifier, the audit, and the granularity gates. | The safeguards are the part left behind; harm is produced by our code with none of our controls. | The outbound license is Apache-2.0, which permits forks, so the name is the lever we actually hold; the verifier and coarse defaults are not optional modules; a fork that strips the gates must not use the project name; misuse reporting. |

**The three design-driving cases.** Stalking, residence doxxing, and harassment are the realistic, low-effort, high-harm cases and the ones a user of this project can actually cause. They set the default and justify the runtime refusal, because a correct policy that depends on the user reading it is not a policy.

**Enforcement and military use are a different question.** They are about who may borrow or buy the capability, not about which recording a user has. That is handled by refusal, audit, and the absence of an operational mode, not by hoping a licence clause is read.

**Mosaic effect.** Coarse outputs are not automatically safe. Repeated `sub_region` queries over one area, combined with public records and other data, can converge on a residence. Node-level detection, purpose binding, and the refusal to publish fine-grained datasets reduce this. They do not eliminate it, and we do not claim they do.

## 3. Capability tiers

ADR 0005 defines four policy tiers, carried by the typed field `sensitivity.max_output_granularity`. The ontology's validator ([world-ontology](../specs/world-ontology.md) §I10) enforces a region floor: a `spatial_region` under an effective ceiling of `region` must have a bounding-box extent of at least 0.05° per axis, or H3 resolution ≤ 7. The numbers below are **current defaults, not permanent constants** ([ADR 0011](../decisions/0011-privacy-forensics-and-publication-rulings.md) §2): the granularity actually published is decided per output by physical area, location sensitivity, re-identification risk, and publication purpose. Changing a default or a band still requires an ADR; treating a number as a timeless guarantee is a defect.

| Policy tier (ADR 0005) | Output band | Default | Gate | Audit |
|---|---|---|---|---|
| `region` | Extent ≥ 0.25° per axis (about 28 km at mid-latitude), or an H3 cell set of equivalent extent, or anything coarser. | Open. Ordinary queries, examples, demos. | None. | Aggregate counts only. |
| `sub_region` | Extent from 0.05° up to 0.25° per axis; 0.05° / H3 ≤ 7 is the floor. | Logged. | Authenticated researcher or consigned user; per-query audit; rate-limited. | One entry per query. |
| `precise` | Extent below 0.05° per axis, any explicit coordinate, or an address. | Authorized research task only. | Authorization record with reviewed purpose (§4.2), valid and unexpired; refused without one. In ontology 0.1.0 this tier is also blocked by construction: there is no point geometry type (world-ontology §5), so `point` is hard to satisfy rather than gated by goodwill. | Full entry per query, with authorization id and emitted geometry. |
| `person_level` | Any output resolved to a natural person, including a residence when the intent is identification. | Never. | Encoded as `person_data: true` (any reachable root makes the bundle unpublishable) and/or `max_output_granularity: none` (no location at all). No output variant exists. | Attempts logged as contract violations. |

**The two floors are not equivalent protection scales.** H3 resolution 7 has a mean hexagon area of about 5.16 km². A 0.05° latitude span is about 5.6 km north–south, and its east–west extent shrinks with latitude. They differ in shape and in worst-case re-identification risk, so policy compares **physical area and sensitivity**, never the numeric width of a degree or the resolution number alone ([ADR 0011](../decisions/0011-privacy-forensics-and-publication-rulings.md) §3).

**Tier mapping (resolved 2026-11-04).** The four policy tiers are a projection of the three-value ontology cap plus the policy-owned floor, not a fourth enum value ([ADR 0005](../decisions/0005-privacy-and-dual-use.md) clarification 1). `region` and `sub_region` both sit under `max_output_granularity = region` and differ only by the output band in the table above; `precise` requires `max_output_granularity = point` **plus** a signed authorization record; `person_level` is never emitted at any cap. Ontology 0.1.0 keeps exactly `region | point | none`, and the runtime enforces the bands from policy configuration and the audit log. This table is the normative policy for the numerics; changing a band requires an ADR.

**Propagation.** A derived record's effective cap is the strictest among its inputs (`none` > `region` > `point` in strictness; the allowed output is the meet, i.e. the coarsest). A coarse source cannot be transcended by a better inferencer, and a precise authorization on one input does not loosen the others.

## 4. Enforcement mechanisms

Statements without code are the failure mode this section exists to avoid.

1. **Coarse by default.** The default output projection is `region`. There is no command-line flag, environment variable, or config key that raises the default; `precise` is a distinct code path that demands an authorization record. Tests assert that a fresh install cannot emit below `region`.
2. **Authorization records.** Every `precise` output requires a record with: identifier, requester identity and role, Research Node, stated research purpose, data classes and area bound, maximum precision, validity window, reviewer, conditions, and the audit reference. Records are evidence, not settings: they expire, they are revoked on misuse, and an expired record is invalid rather than ignored.
3. **Runtime refusal.** The enforcement point is serialization, not the CLI. The refusal is a typed error and a recorded event; it is never a warning, and there is no `--force`.

```
emit(record, requested):
    cap = strictest_cap(record, all_ancestor_inputs)          # coarsest wins
    if precision(requested) > precision(cap):
        return project(record, cap) with abstention_reason("granularity_capped")
    if requested == precise and not valid_authorization(record, purpose):
        audit(refusal, record, requested)
        return project(record, sub_region) with abstention_reason("authorization_required")
    if emitted == precise:
        audit(precise_query, record, authorization_id)
    return record
```

4. **Publication inherits the strictest source.** `PublishEvidence` (world-ontology §9) requires at least one verification with verdict `pass` or `partial`, a passing bundle licence and sensitivity check, a recorded bundle digest, and — when more than one identity is configured — a publisher different from the hypothesis creator. The bundle's granularity is the effective cap through the evidence graph; a reviewer may never raise it, and only a new authorization for a defined purpose can, appearing in the publication record. Local single-researcher mode makes the publisher separation structurally unenforceable; the audit records `role_source: local_bootstrap` and the publication says so. Publication rules are detailed in [data-governance.md](data-governance.md).
5. **Audit every precise query.** The ontology's audit row records actor, declared role, `action_kind`, target ids, canonical parameter digest, run id, timestamp, and policy digest, under a monotone sequence number (world-ontology §9). The policy layer adds requested and emitted granularity, authorization id, Research Node, and outcome including refusals. Rows are append-only and content-free — references and hashes, not observation content — so the log can outlive the data it describes and cannot reconstruct a deleted recording. M0 claims append-only ordering, not tamper-evidence; hash chaining or a transparency log would be a Research Node extension and is not a current guarantee.
6. **Node-level rate and abuse detection.** Each Research Node watches for signals: repeated tight-area queries, systematic area sweeps, queries clustering around one address, bulk export, and accounts sharing infrastructure or purpose text. The response ladder is throttle, require review, suspend the account, suspend the node, notify maintainers. Detection is statistical and will produce false positives; an appeal path exists and detections are audited. It is not a defence against a determined insider, only a limit on casual abuse.
7. **Person-level is not representable.** `person_level` exists in the tier vocabulary only so that refusals can name it. The output type has no variant for a person, identity fields are not part of a world-state record, and an inferencer that tries to emit one is rejected at the contract boundary.
8. **A bypass is a vulnerability.** Any path that emits below its cap, any fork that removes the authorization check, and any publication that exceeds inherited granularity are treated as security defects with the same intake as §7.

## 5. Sanctioned and prohibited uses

### 5.1 Sanctioned uses

| Use | Why it is allowed | Conditions |
|---|---|---|
| Environmental science | Reconstructing weather, ecology, acoustic, or terrain conditions is the project's stated purpose and rarely identifies a person. | Published data stay coarse by default; precise calibration needs an authorized task and a stated purpose. |
| Authorized forensics | Reconstructing the place, time, and conditions of a past public-interest incident is a legitimate evidentiary need. | The §5.3 conditions; place or event only, never a person; audit. |
| Public-event verification | Checking whether a claimed image or recording is consistent with the physical world serves public accountability. | Outputs stay `region` unless review authorizes otherwise; persons in the material are not identified. |
| Historical research | Reanalysis of archived observations benefits from bitemporal records and does not create new surveillance. | Same caps; historical reanalysis must not silently rewrite the past. |
| Reproducibility studies | Re-running a published claim is how the field stays honest, and it requires the same precision the original used. | Scoped to the original claim's data and purpose; output stays inside the original cap. |

### 5.2 Prohibited uses

These are excluded from the project's intended use, docs, examples, tests, and commit messages (ADR 0005 §3; AGENTS.md). They are not discouraged; they are out of scope.

| Prohibited use | Why |
|---|---|
| Military targeting, intelligence support for targeting | The capability becomes a weapon component; no lawful-authorization override exists. |
| Real-time operational or tactical command | The system is built for reproducible reconstruction, not live pursuit; a live mode changes the harm class entirely. |
| Person-level surveillance or tracking | Locating people covertly is the defining harm this project refuses; it is out of scope rather than gated. |
| Revealing a private residence | A residence is a person's location by proxy; the harm is irreversible and often violent. |
| Enforcement action against individuals | ADR 0005 excludes it; the project does not build case tooling, watchlists, or custody support. |
| Harassment, doxxing, or coordinated targeting | Direct harm to a person who cannot consent or contest. |
| Insurance, lending, pricing, or eligibility decisions from inferred environment | Inferred attributes are not verified facts about a person, and the subject has no appeal. |
| Extracting the capability into a closed tool that drops the verifier, audit, or granularity gates | The safeguards are the product's ethical content; removing them is not a fork, it is a different, unsafe system. |

### 5.3 Law enforcement: the refusal boundary

PhainoWeave is not an enforcement product, and enforcement action against individuals is prohibited. The project documents no enforcement workflow, example, or test; this subsection exists only to state the refusal boundary. The only adjacent sanctioned use is **authorized forensics**, and it is permitted only when every one of the following holds:

1. A lawful authorization — warrant, court order, or equivalent statutory authority in the jurisdiction where the Research Node operates — exists as an artifact before any query runs.
2. The research question concerns a place, event, or environmental condition. It is never the identification of a person.
3. An independent reviewer and a maintainer sign the research task and authorization record. The requesting party cannot self-approve, and the requester is not a reviewer.
4. The cap is `sub_region` by default. `precise` is allowed only if the review explicitly finds it necessary and proportionate to the place-or-event question.
5. There is no real-time, operational, tactical, or custody use, and the project provides no chain-of-custody or testimony product.
6. The query is fully audited; outputs are sealed to the authorized purpose and are not reused, resold, or transferred.
7. A request that fails any condition is refused and the refusal is recorded.

**Status: adopted 2026-11-04 as a strictly limited exception** ([ADR 0011](../decisions/0011-privacy-forensics-and-publication-rulings.md) §1). The route exists only for (a) the operator's own devices, (b) explicitly authorized research subjects, and (c) non-sensitive public environments. The seven conditions are executed by the runtime **and** a human review: a missing or invalid authorization is a typed refusal plus an audit row, never a warning, and no `--force`, environment variable, or config key bypasses it. Absolute prohibitions remain: precise localization of unauthorized private individuals, covert tracking, and disclosure of sensitive locations. The absolute-ban alternative was considered and rejected because it pushes lawful place-level work into forks that strip the audit entirely.

## 6. Ethics review process

**When required.** Review is a merge gate, not advice, for any change that materially raises precision or lowers the cost of achieving it: a new modality; a new verifier or model that tightens regions; any inferencer whose measured coverage at a given area improves beyond run-to-run variance; an order-of-magnitude cost reduction that moves the capability from lab to commodity; a new data class or licence; a new deployment mode; a change to the granularity bands, the authorization schema, or an output enforcement rule; and publication of a dataset that could train the capability. Removing or weakening a safeguard always requires review and an ADR.

**Who reviews.** One maintainer plus one external reviewer who is not employed by the project, for ordinary changes. Changes that could enable person-level or residence-level harm need two external reviewers, at least one with privacy, security, or civil-liberties background. Reviewers disclose conflicts, and the change's author cannot be the sole reviewer. If no qualified external reviewer is available, the change waits; lack of reviewers is not a waiver.

**The artifact.** A short record at `docs/policy/reviews/YYYY-MM-DD-<slug>.md`, the convention of the [reviews directory](reviews/README.md), containing: the change and its precision or cost delta (measured, or explicitly `unverified`); modality and data affected; expected benefit; misuse analysis by adversary; the red-team case and its result; residual risk; decision and conditions; reviewer identities and dates; and a re-review date or trigger. No review record, no merge.

**Red team before capability.** Every reviewed change ships with at least one documented misuse attempt: a test that tries to extract a `precise` output without authorization, to strip a cap through derivation, or to reconstruct a residence from the new capability's output. Where live execution would itself be harmful, a written red-team case with a reasoned expected result is acceptable and must say so. Negative results are kept: "we tried and the gates held" is a valid, useful record.

**Merge gate.** The pull request links the review record; a maintainer verifies the link, the red-team result, and that the stated precision delta matches the benchmark evidence before merge. A change that contradicts an Accepted ADR amends the ADR first.

## 7. Incident response

**Intake.** Reports arrive through the private channels in [SECURITY.md](../../SECURITY.md). Reporters are not named without consent, and no public detail is published before containment.

**Triage.** Severity follows the harm class: physical-safety harm first, then surveillance or discrimination at scale, then institutional and reputational harm. Every confirmed incident gets an owner and a timeline.

**Containment ladder.** These are configuration and credential actions, exercisable without a code deploy, and drilled at least once before a public release:

1. Raise the global granularity cap, or disable the `precise` tier, for the affected deployment.
2. Revoke authorization records and Research Node credentials.
3. Disable or pin the affected inferencer version or model weights.
4. Halt publication and withdraw affected artifacts by tombstone (see [data-governance.md](data-governance.md)); never by silent deletion.
5. Publish an advisory naming the capability, the affected versions, and the mitigation.

**Disclosure.** Acknowledge a report within 7 days, the target set in [SECURITY.md](../../SECURITY.md); give an initial severity assessment within 14 days; publish a public write-up once affected parties are notified and a mitigation exists. The default target is 90 days from confirmation. Delay beyond that requires a recorded reason: active harm, an affected person's request, or a legal restriction. We do not delay to protect reputation.

**Capability rollback.** Rollback means revoke and cap, not rewrite history. The runbook states which config keys and credentials are involved, who may act alone, and who must countersign. Users of a withdrawn capability are notified, published claims that depended on it are marked, and the post-incident record is filed under `docs/policy/reviews/`. Evidence of the incident is preserved; deleting it is itself an incident. M0 stores media outside SQLite, so a tombstone removes the blob content while the observation record and its hash remain; a dedicated tombstone status is not yet in the ontology (see [data-governance.md](data-governance.md) §5).

## 8. Legal posture

**Jurisdiction variance.** Privacy and data-protection law differ by country and subnational jurisdiction. This project cannot encode every regime, and nothing here is legal advice. Each deployment is responsible for its own compliance, and the project's rules are a floor, not a substitute for counsel.

**GDPR-like obligations.** In regimes with GDPR-like law (the EU and UK GDPR and their analogues), location and environment data linked to a person can be personal data. That implies a lawful basis, purpose limitation, minimisation, retention limits, a data-protection impact assessment for high-risk processing, data-subject rights where data are identifiable, and constraints on cross-border transfer. Whether a given Observation is personal data is a fact-specific question, not a property of the file format.

**Deanonymization.** A region, a time window, and an environmental state can jointly identify one person. "Place-level" is therefore not a safe category by definition; it is only safer than a point. Publicly available source data does not make the derived inference public or harmless.

**The rule that makes the defaults matter.** Defaults must be safe without per-query legal review. Legal review happens per deployment and per purpose, never per query, because a floor that depends on counsel being available at the moment of use is not a floor. That is why the runtime enforces granularity rather than relying on a usage policy.

**Export and dual-use controls.** The project makes no compliance claim under any export-control regime. Whether the capability is controlled in any jurisdiction is `unverified`, and it must be resolved with counsel before any hosted or institutional offering.

**The right to refuse.** The project may refuse a use that is legal but harmful. Legality is a necessary condition for a sanctioned use, never a sufficient one.

## 9. Honest residual risk

This policy cannot prevent a determined actor from reimplementing the capability from the published literature and reusing the same physical constraints. It cannot stop analysis of recordings someone already holds. It cannot stop a state actor with its own pipeline, a fork with the safeguards removed, or the mosaic effect of many coarse outputs combined with unrelated data. It cannot prevent an insider with a valid authorization from querying in bad faith; the audit detects that after the fact and supports accountability, but detection is not prevention.

We publish anyway, for reasons we consider stronger than the residual risk. Verification is the product: a capability that cannot be audited or contested is worse than one that can, and secrecy would concentrate the capability in the actors least accountable to the people it affects. The underlying physics is public, so a closed implementation buys little safety and costs the public record. Publishing benchmarks, residuals, abstention behaviour, and failure cases lets other people check our claims and lets affected communities see what the tool can do. We accept that this reduces harm partially rather than eliminating it, and we say so instead of implying a safety we do not have. If evidence ever shows that publication materially accelerates harm beyond what independent reimplementation would produce, this stance is the thing to revisit, and the review record must state why it changed.

## 10. Maintenance

The owner reviews this policy at least annually, and immediately after any incident, any new modality, or any material change in applicable law. A change to a boundary, a tier band, or the prohibited-use list requires an ADR; editorial changes do not. Review records are append-only and are never deleted, including records of changes that were later reversed.
