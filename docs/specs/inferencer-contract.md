# PhainoWeave Inferencer Contract — M0 Interface Specification

**Purpose:** fix the one interface that every inference plugin — Rust or Python — implements, so hypotheses, scores, residuals, data versions, and error states are comparable across modalities and replayable. · **Status:** Normative draft, `contract 1.0`, 2026-11-04; breaking changes require an ADR and a contract major bump.

An inferencer is a bounded, pure function: given declared evidence and declared data versions, it returns candidate world states with scores, provisional residuals, and a determinism declaration. It never writes to the store, never promotes a hypothesis, and never adjudicates. Those three prohibitions are the difference between a scientific instrument and an oracle; they are enforced by the host, not by plugin good behaviour. The object field names this contract refers to are defined only in [`world-ontology.md`](world-ontology.md).

## 1. Boundary rules

MUST hold for every inferencer, in every language:

1. **No store access.** The plugin receives bytes and metadata in the request; it returns a response document. The host performs every write.
2. **No network.** M0 contract has no network capability. A plugin needing remote data fails `dependency_unavailable` and the host fetches through the data fabric instead.
3. **No writes outside the provided scratch directory**, which is created per run and deleted after it.
4. **No hidden inputs.** Every value read that is not in the request must be declared in `referenced_data_versions`; the host checks declarations against what was provisioned.
5. **No verdict.** `verdict`, `status` of a hypothesis, and combination of evidence independence belong to the verifier and the store ([I7, I9](world-ontology.md)).
6. **No abstention-by-omission.** An empty candidate list with `status = ok` is a contract violation; insufficient evidence is `status = abstained` with a reason ([I8](world-ontology.md)).

Capabilities the host may grant, per plugin, as declared in the manifest: `media.audio`, `media.image`, `media.video`, `media.sensor`, `media.document`, `compute.gpu`, `io.scratch`. Nothing else exists in M0.

## 2. Manifest, discovery, lifecycle

A plugin is a directory containing `inferencer.toml`:

| Key | Type | Meaning |
|---|---|---|
| `name` | string | `vendor/family` or `ambient-inference/family`; stable identity |
| `version` | semver | implementation version; changes any output ⇒ version bump |
| `contract_version` | string | `MAJOR.MINOR` the plugin implements |
| `entrypoint` | string | Rust: registered symbol; Python: `package.module:run` |
| `media_kinds` | list | subset of `audio,image,video,sensor,document`; empty means it consumes features only |
| `score_semantics` | enum | `log_likelihood_ratio`, `probability`, or `rank_score` (§4) |
| `determinism` | enum | `deterministic`, `nondeterministic`, `unknown` (§6) |
| `capabilities` | list | from the closed set in §1 |
| `parameters_schema` | object | JSON Schema subset for `parameters`; unknown keys are rejected by the host |
| `limits` | object | default `budget` the plugin can honour (§7) |

Lifecycle: host loads and validates the manifest, checks `contract_version` major equality, resolves `entrypoint`, then for each run provisions a sandboxed process (or in-process Rust call), sends exactly one request document on stdin, reads exactly one response document from stdout, treats stderr as diagnostics only, enforces the budget, and tears the process down. A run is one request/response exchange; a plugin that needs iteration must do it internally and stay inside the budget.

## 3. Request

| Field | Type | Required | Semantics |
|---|---|---|---|
| `contract_version` | string | yes | must equal the plugin's declared major |
| `run_id` | `run_` id | yes | the run the host is recording; the plugin never invents one |
| `ontology_version` | string | yes | schema version for all ids and value objects |
| `inferencer` | `{name, version}` | yes | expected identity; response must echo it exactly |
| `hypothesis_query` | object | yes | `{region?: spatial_region, time?: time_window, state_filter: map, hypothesis_ids: list, max_hypotheses: int}` |
| `observation_refs` | list | yes (may be empty) | `{id, content_hash, media_kind, media_path, license_snapshot}`; `media_path` is a read-only path into the content-addressed store |
| `feature_refs` | list | no | `{id, observation_ids, feature_kind, value, unit, uncertainty}` already extracted, when the host wants re-use |
| `constraint_refs` | list | yes (may be empty) | `{id, constraint_kind, version, expression, parameters, residual_function, tolerance}` |
| `data_snapshot_refs` | list | yes (may be empty) | `{id, uri, version, checksum, access_path?}`; the plugin may rely only on these |
| `evidence_scope` | list of ids | yes | the closed set of record ids a response may cite; the host rejects any citation outside it |
| `parameters` | map | yes | plugin-specific, validated against `parameters_schema` |
| `seed` | integer | yes | single root of all randomness; the plugin must derive all sub-seeds from it deterministically |
| `budget` | object | yes | `{wall_ms, cpu_ms, peak_mem_mb, max_candidates, max_output_bytes}` |
| `scratch_dir` | path | yes | writable, empty, deleted after the run |

Example (elided media path):

```json
{"contract_version":"1.0","run_id":"run_9c8d7e6f5a4b3c2d","ontology_version":"0.1.0",
 "inferencer":{"name":"ambient-inference/acoustic_doppler","version":"0.1.0"},
 "hypothesis_query":{"region":null,"time":null,"state_filter":{},"hypothesis_ids":[],"max_hypotheses":8},
 "observation_refs":[{"id":"obs_3f1c0a9d2b4e67a1","content_hash":"c0a1…","media_kind":"audio","media_path":"blobs/sha256/c0/a1/c0a1…","license_snapshot":{"spdx":"CC-BY-4.0","terms_url":"…","access_level":"public"}}],
 "feature_refs":[], "constraint_refs":[{"id":"con_5d4c3b2a1908f7e6","constraint_kind":"kinematic","version":"1.0.0","expression":"…","parameters":{"c_m_s":343.0},"residual_function":"kinematics.doppler_rms_v1","tolerance":0.01}],
 "data_snapshot_refs":[], "evidence_scope":["obs_3f1c0a9d2b4e67a1","con_5d4c3b2a1908f7e6"],
 "parameters":{"candidate_bearing_step_deg":5.0},"seed":20260314,"budget":{"wall_ms":30000,"cpu_ms":30000,"peak_mem_mb":2048,"max_candidates":8,"max_output_bytes":1048576},
 "scratch_dir":"/tmp/phaino/run_9c8d7e6f5a4b3c2d"}
```

A plugin may return zero candidates with `status = abstained`, and must return `invalid_request` if `hypothesis_query` is unsatisfiable (for example `max_hypotheses = 0` with a non-empty region).

## 4. Response

| Field | Type | Required | Semantics |
|---|---|---|---|
| `contract_version` | string | yes | echoed |
| `inferencer` | `{name, version}` | yes | must equal the manifest exactly |
| `status` | enum | yes | `ok`, `abstained`, `error` (§5, §6) |
| `abstain_reason` | enum | iff `status = abstained` | `insufficient_evidence`, `out_of_distribution`, `unsupported_modality`, `budget_exhausted`; must be absent otherwise (§6) |
| `complete` | bool | yes | `false` only when the plugin stopped early inside budget; partial results must say so |
| `candidates` | list | yes (may be empty only when abstained) | each candidate is a full claim, never a bare coordinate |
| `residuals` | list | yes (may be empty) | provisional constraint residuals; never a verdict |
| `referenced_data_versions` | list | yes | `{id, version, checksum}` for every snapshot actually read |
| `determinism` | enum | yes | must equal the manifest declaration |
| `diagnostics` | list of strings | yes | bounded, redacted, no payloads |
| `timings` | `{wall_ms, cpu_ms}` | yes | informational; excluded from determinism comparison |
| `error` | object | iff `status = error` | `{code, message, retryable, detail?}` |

A candidate:

| Field | Type | Semantics |
|---|---|---|
| `candidate_id` | string | plugin-local, stable across reruns; the host derives the `hyp` id, so this is only for correlation |
| `claim` | `{location: spatial_region, time: time_window, state: map}` | region and window are mandatory and non-degenerate; `state` may be `{}` but must be present |
| `score` | `{value: float, semantics: enum}` | `semantics` must equal the manifest's; see the table below |
| `independence_key` | string | the physical correlation key (e.g. `source:src_…`, `weather-hour:…`); a candidate with no key inherits the host fallback and can never add a second vote |
| `supporting_evidence_ids` | list of ids | subset of `evidence_scope`; the host drops and audits any id outside it |
| `conflict_evidence_ids` | list of ids | subset of `evidence_scope` |
| `constraint_residuals` | list | `{constraint_id (must be in `constraint_refs`), value: float, unit: string, n_observations: int, note?: string}` |
| `explanation` | `{text: string, feature_ids: list}` | short human-readable justification; `text` is not evidence and is never parsed |

Score semantics, normative: `log_likelihood_ratio` is a natural-log LLR for the candidate against the plugin's own alternative, bounded to `|value| ≤ 16` and clipped to `llr_clip` by the host before combination; `probability` is a posterior in `(0,1)` produced by a calibrated model and must carry a `calibration_ref` in `parameters` or in the manifest; `rank_score` is an arbitrary monotone ordering value and **never** participates in confidence combination or in any published probability — it may only order candidates inside one response. A plugin that emits a score it cannot justify as one of these three is non-conformant.

The host recomputes residuals from `constraint_refs` and registry-resolved `residual_function`; a plugin residual is a prediction of what the verifier will find, and disagreement is recorded as a data-quality signal rather than as a correction.

## 5. Error states

`status = error` means the host accepts no candidates from that response; `status = ok` with `complete = false` is the only way to return partial work.

| `error.code` | Meaning | Retryable | Host action |
|---|---|---|---|
| `invalid_request` | request violates this contract or the parameters schema | no | audit, fail the run |
| `unsupported_media` | media kind or codec the plugin cannot read | no | audit; the host may try another plugin |
| `license_violation` | requested evidence is not permitted for this computation under the effective license | no | audit as a policy event, fail the run |
| `resource_exhausted` | declared budget exceeded internally | yes, with a larger budget | audit; run marked `nondeterministic` only if the plugin says so |
| `timeout` | host wall-clock deadline reached | yes, with a larger budget | process killed; no partial acceptance |
| `numeric_failure` | non-convergence, singular solve, NaN/Inf in an output | yes, different parameters | fail the run; no candidates |
| `dependency_unavailable` | a declared snapshot, model weight, or native library is missing | yes, after provisioning | fail the run |
| `cancelled` | host cancelled the run | no | teardown |
| `internal_error` | unhandled exception | yes, after a fix | fail the run; diagnostics retained |

`message` is a single line, `detail` is bounded structured data; neither may contain evidence payloads, file contents, or personal data.

## 6. Determinism and abstention

`deterministic` means: for an identical request (same ids, bytes, parameters, seed, contract and plugin version) the response is byte-identical after removing `timings`, `diagnostics`, and process-level fields. Sources of permitted nondeterminism (thread scheduling, GPU kernels, hash-map iteration, floating-point reduction order) must be documented in the plugin README; if any is present, the declaration is `nondeterministic`. `unknown` is for plugins whose determinism has not been tested and is treated as `nondeterministic` by the runtime.

The plugin MUST derive all randomness from `seed`; using `random` defaults, wall-clock time, hostnames, or environment variables to affect output is a conformance failure. The host runs every deterministic plugin twice during conformance and compares the canonicalized responses.

Abstention is a success mode with a required structure: `status = abstained`, `candidates = []`, `complete = true`, `abstain_reason ∈ {insufficient_evidence, out_of_distribution, unsupported_modality, budget_exhausted}` (response field, §4), and `min_support` recorded in `parameters` (the numeric threshold that would have produced a candidate). The host records the abstention in the run and writes no hypothesis. Abstention must not be used to hide a crash: a plugin that cannot read its input returns `unsupported_media`, not abstention.

## 7. Resource limits

The host enforces the budget in the request, not the plugin's own claim. M0 defaults, all overridable per run and recorded in `inference_run.parameters`:

| Resource | Default | Enforcement |
|---|---|---|
| wall clock | 30 000 ms | process kill (`SIGKILL` after `SIGTERM` grace), reported as `timeout` |
| CPU time | 30 000 ms | `RLIMIT_CPU`; overrun surfaces as `resource_exhausted` |
| peak memory | 2 048 MiB | `RLIMIT_AS` or cgroup; allocation failure surfaces as `resource_exhausted` |
| output document | 1 MiB | host truncates and refuses the run |
| candidates | 8 | host refuses the response as `invalid_request` |
| observations | 64 | host refuses before dispatch |
| filesystem | scratch only | sandbox mount: read-only media paths, writable scratch, no other access |

Exceeding a limit is a normal outcome, not an incident: the run fails with a typed code and the audit row records which limit was hit. A plugin may declare lower limits; the host uses `min(requested, declared)`.

## 8. Conformance tests a new inferencer must pass

Every test ships as a fixture in the plugin's `conformance/` directory and is runnable offline by `--self-test`; the host also runs the set before registering the plugin in a store.

| Test | Pass criterion |
|---|---|
| C1 manifest | all required keys present; semver parses; contract major is 1; schema validates |
| C2 identity echo | response `inferencer` equals manifest; `contract_version` matches |
| C3 scope discipline | every cited id is in `evidence_scope`; every `constraint_residual.constraint_id` is in `constraint_refs` |
| C4 data declaration | `referenced_data_versions` equals exactly what the fixture allows the plugin to read (canary snapshots expose undeclared reads) |
| C5 score discipline | semantics equal manifest; LLR within ±16; probability in `(0,1)`; no `rank_score` in a response declaring a probability |
| C6 claim shape | every candidate has non-degenerate region and window; `state` present; region honours the effective `max_output_granularity` |
| C7 abstention | out-of-distribution fixture yields `abstained` with a reason and `min_support`, never `ok` with zero candidates |
| C8 error taxonomy | malformed request ⇒ `invalid_request`; restricted evidence ⇒ `license_violation`; missing snapshot ⇒ `dependency_unavailable`; no untyped exception escapes |
| C9 determinism | deterministic declaration survives two runs with byte-identical canonical responses; nondeterministic declaration documented |
| C10 resources | a fixture designed to exhaust CPU and one to exhaust memory return typed codes; declared peak memory is not exceeded |
| C11 isolation | runs with networking denied and a read-only root; success without touching anything outside `scratch_dir` and provided media paths |
| C12 version reporting | any behavioural difference under an identical request forces a `version` bump; the fixture asserts name and version stability against a recorded golden response |

C9 and C12 are also the tests that make [I6](../product/founding-brief.md) checkable per plugin; a plugin that cannot pass C9 is still admissible but its runs are recorded as non-deterministic and cannot be used as evidence of reproducibility in a benchmark.

## 9. Versioning of the contract

The host rejects unknown top-level request and response fields, so a field can only be added together with a host that knows it. Additions are therefore MINOR and a minor bump upgrades both sides rather than relying on silent tolerance. Concretely: a plugin declaring `contract_version 1.x` is accepted by a `1.y` host when `x ≤ y`; a plugin declaring `1.y` on a `1.x` host with `x < y` is refused. `capabilities` additions are MINOR. Removing a field, changing a score semantic, or changing the determinism definition is MAJOR and requires an ADR. Deprecation: a field is announced in a MINOR, remains accepted for one MINOR, and is removed in the next MAJOR.

## 10. Rust host interface

The Rust core exposes the same document at the typed boundary; the trait is the in-process form of §3/§4, and the Python path is a subprocess adapter that implements this trait by serialization.

```rust
pub trait Inferencer {
    fn manifest(&self) -> &InferencerManifest;
    fn infer(&self, req: &InferRequest) -> Result<InferResponse, InferencerError>;
}
pub struct InferRequest {   // serde field names are the §3 field names, no renames
    pub contract_version: String, pub run_id: RunId, pub ontology_version: String,
    pub inferencer: InferencerRef, pub hypothesis_query: HypothesisQuery,
    pub observation_refs: Vec<ObservationRef>, pub feature_refs: Vec<FeatureRef>,
    pub constraint_refs: Vec<ConstraintRef>, pub data_snapshot_refs: Vec<DataSnapshotRef>,
    pub evidence_scope: Vec<String>, pub parameters: serde_json::Value, pub seed: i64,
    pub budget: Budget, pub scratch_dir: std::path::PathBuf,
}
```

Unknown enum values are impossible by construction in M0 because the store gate in [`world-ontology.md`](world-ontology.md) §13 refuses a store whose minor version differs from the code's; do not add `#[serde(other)]` catch-alls — they hide vocabulary drift instead of surfacing it. Timestamps are RFC 3339 strings, not `chrono` formatting guesses; ids are newtypes, never bare `String` at API boundaries.

## 11. Python plugin interface

The Python SDK mirrors §3/§4 and is the only supported Python shape: a manifest plus a module exposing `run`. The host launches `python -m phaino_sdk.runner <plugin_dir>`, writes the request as one JSON document to stdin, and reads one JSON document from stdout.

```python
"""Acoustic Doppler inferencer."""
from phaino_sdk import Inferencer, Candidate, Claim, Result

class DopplerInferencer(Inferencer):
    name = "ambient-inference/acoustic_doppler"
    version = "0.1.0"
    contract_version = "1.0"
    score_semantics = "log_likelihood_ratio"
    determinism = "deterministic"

    def run(self, req: dict) -> Result:
        rng = self.rng(req["seed"])          # only permitted randomness source
        ...
        return Result(status="ok", complete=True, candidates=[...],
                      residuals=[], referenced_data_versions=[], diagnostics=[])
```

Plugins may not import the store crate, open sockets, spawn unlisted binaries, or read environment variables that affect output; the `phaino_sdk` package exposes no such helper on purpose. Plugin code runs with the current user's permissions inside the host sandbox described in §7; the sandbox is a resource and policy boundary, not a security boundary against hostile code, and M0 does not claim otherwise.

## 12. Deferred beyond M0

Streaming/chunked responses and progress callbacks; plugin-to-plugin chaining inside one process; GPU memory accounting; multi-request batched runs; cross-run caching with declared cache keys; sandboxing hostile third-party plugins (M0 assumes a trusted plugin set shipped with the repo); a typed constraint IR shared between plugin and verifier (the expression is text, the residual function is a registered symbol, and the registry is the only join point).
