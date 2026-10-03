# Test taxonomy and dataset selection

Milestones 1–4 provide case classification, versioned fingerprints,
descriptor-aware loading, deterministic selection, suite execution, persisted
definition snapshots, grouped reports and comparison context. No UI is implemented. Direct runner calls default to v1; classified cases require
explicit `fingerprint_scheme="dataset-cases-v2"` or the suite execution API.

The harness owns the mechanism; dataset authors own opaque category, tag, and
risk values. Risk does not alter scoring, gates, or weights. Definitions never
contain latest execution status or PASS/FAIL results.

## Author a descriptor and JSONL cases

```json
{
  "schema_version": "dataset-descriptor-v1",
  "id": "example-evaluation",
  "version": "study-v1",
  "title": "Example evaluation",
  "description": "An authored collection.",
  "cases": "cases.jsonl",
  "extra": {"origin": {"revision": 1}},
  "fingerprint_scheme": "dataset-cases-v2"
}
```

The schema version, ID, authored version, case binding, and fingerprint scheme
are required. Title/description default to null and `extra` defaults to `{}`.
Only this schema and v2 case fingerprints are supported by the new loader.
There is no second metadata dictionary.

`cases` is a local relative file binding interpreted from the descriptor's
directory, independently of process cwd. URLs, absolute paths (including
Windows drive paths), backslash bindings, and parent traversal are rejected.
Nested paths within the descriptor directory are supported; resolved symlinks
must also stay inside it. The authored binding remains unchanged in the
descriptor; resolved absolute paths are I/O context, not fingerprint content.

Every nonblank JSONL line contains an ordinary TestCase, for example:

```json
{"id":"case-a","input":"alpha","reference":"alpha","title":"First example","category":"family-a","tags":["quick","cross-cutting"],"risk":"high","extra":{"origin":{"revision":1}}}
```

Input is a string or object; reference is a string, object, or null. Extra is
arbitrary finite JSON metadata. Title/description/category/risk are optional.
Category expresses primary classification, tags cross-cutting classification,
and risk declared criticality. These values are not registered in core.

`load_dataset()` validates the entire case file before returning anything for
selection. It rejects unknown top-level fields, duplicate JSON keys at any
depth, non-finite numbers (including overflow), blank/duplicate IDs, invalid
types, and blank/duplicate/non-string tags. ID, category, risk, tags, dataset
ID/version, and selector values reject leading/trailing whitespace. Internal
whitespace remains significant and allowed. Values/order are never trimmed,
lowercased, sorted, or deduplicated. Non-null title must be nonblank; description
may be empty or whitespace prose. Case errors report file and physical line;
duplicate-ID errors identify both lines. Diagnostics omit whole case bodies.

The legacy `load_cases(path)` is unchanged and continues its existing permissive
behavior. Strict checks live in the new authoring path, not in legacy callers.

## Load and preview without targets or scorers

```python
from harness.core.dataset import load_dataset
from harness.core.selection import CaseSelection, preview_selection, select_cases

dataset = load_dataset("tests/fixtures/taxonomy/organization/dataset.json")
selection = CaseSelection(categories=["family-a"], tags_any=["quick"])
selected = select_cases(dataset.cases, selection)
preview = preview_selection(dataset, selection)
print(preview.model_dump_json(indent=2))
```

`LoadedDataset` holds the descriptor, ordered TestCases, resolved descriptor/case
paths, full case fingerprint, and descriptor fingerprint. It supports model/JSON
round-tripping and verifies supplied fingerprints against its content. Nested
case/metadata objects remain mutable; preview revalidates all in-memory source
content, including unselected cases, and rejects stale fingerprints. Reload the
source file after edits. Preview does not automatically reread files from disk.

`select_cases()` accepts an already validated sequence, returns references to
matching TestCases in original order, and never mutates inputs. For descriptor-
bound inputs, load the complete dataset first or use `preview_selection()` to
also check its current content and fingerprints. Legacy duplicate tags do not
duplicate returned cases; duplicate source IDs are rejected as ambiguous.

| Selector behavior | Meaning |
| --- | --- |
| Omitted selection / `{}` | All cases |
| Multiple fields | AND across fields |
| `case_ids`, `categories`, `risks` | OR within each array |
| `tags_any` | At least one requested tag |
| `tags_all` | Every requested tag |
| Comparison | Exact, case-sensitive; missing category/risk does not match |
| Order | Original dataset order, never requested-ID order |
| Supplied empty/null arrays or duplicate values | Validation error |
| Unknown explicit ID | Error before applying taxonomy filters |
| ID selectors with taxonomy filters | Intersection |
| No matching cases | Valid preview, `executable: false` |

The fixture example selects `case-a` out of three cases. Preview returns dataset
ID/version, descriptor/full/selected fingerprints and scheme names, the authored
selector, ordered IDs, counts, `executable`, and an empty-selection reason.
It contains no case input/reference or arbitrary metadata bodies. Its
`executable: true` means only that membership is nonempty; no target/scorer
capability or execution preflight has occurred. Suite execution performs the
additional checks described below.

## Fingerprints and compatibility

The descriptor hash is the existing canonical JSON fingerprint of its normalized
authored fields, including `schema_version: dataset-descriptor-v1`, explicit
default nulls/empty extra, relative binding, and all authored metadata. Derived
hashes and absolute I/O paths are not included. A descriptor-only description or
metadata edit changes this hash without changing the case-content fingerprint.

Full and selected case hashes use `dataset-cases-v2` as defined in
[ADR 0006](adr/0006-versioned-case-definitions-and-suites.md). They bind ordered
case definitions, including classification, expectations, and metadata. The
empty subset also has a deterministic hash. Authored version labels, descriptor
hashes, full case hashes, and selected case hashes are separate concepts.

The frozen legacy dataset hashes and synthetic replay/calibration compatibility
fixture remain unchanged. Previews do not create or persist a RunResult.

## Bind and execute a suite

Place a suite such as this in a `suites/` directory beside the descriptor:

```json
{
  "schema_version": "suite-v1",
  "id": "quick-checks",
  "title": "Quick checks",
  "description": "An explicitly selected execution group.",
  "dataset": {
    "id": "example-evaluation",
    "version": "study-v1",
    "descriptor": "../dataset.json"
  },
  "selection": {"tags_any": ["quick"]},
  "attempts": 2,
  "evaluation_profile": "example-v1"
}
```

Required fields are schema version, suite ID, dataset binding and positive
integer attempts. Selection defaults to `{}`; title/description/profile default
to null. IDs reject boundary whitespace; internal whitespace is allowed. Strict
loading rejects unknown fields, duplicate JSON keys, non-finite values and
coercions. Bool/fraction/zero attempt counts are errors.

`DatasetBinding` optionally accepts `expected_case_fingerprint` (the full ordered
case hash) and `expected_descriptor_fingerprint` (the full normalized authored
descriptor hash). Every supplied pin is checked independently. Digest strings
must be 64 lowercase hexadecimal characters. `expected_fingerprint` is rejected.
The descriptor path is relative to the suite file, allowing `../dataset.json`;
URLs and absolute paths are rejected. Descriptor case bindings keep their
stricter no-parent-traversal rule.

`resolve_suite(path)` returns `ResolvedSuite`: authored Suite, LoadedDataset,
SelectionPreview, resolved suite path and normalized suite fingerprint. It
constructs no targets, scorers or judges. Its loaded source is a checked
in-memory definition: re-resolve after disk edits. Execution rechecks in-memory
definitions, bindings, hashes and membership, rejecting mutation since resolution.

Recipe code constructs its target/scorers explicitly and calls:

```python
from harness.core.suites import EvaluationProfile, execute_suite, resolve_suite

resolved = resolve_suite("path/to/suites/quick.json")
# Inspect resolved.preview before constructing application/provider clients.
profile = EvaluationProfile(
    id="example-v1",
    taxonomy_evidence="excluded",
    scorer_configuration={"example_metric": {"version": "metric-v1"}},
)
# target and scorers are explicitly supplied recipe-owned instances.
result = execute_suite(resolved, target, scorers, profile=profile)
```

`EvaluationProfile` is trusted Python configuration, not a dynamically executable
suite-file specification. It requires an ID and `taxonomy_evidence` (`excluded`
or `explicitly_included`). Optional fields are:

- `scorer_configuration`: safe authored configuration keyed by stable scorer name.
- `judge_configurations`: explicit existing `JudgeConfiguration` models keyed by
  scorer name; credentials/client state are never inspected or serialized.
- `safe_parameters`: reviewed, finite JSON profile parameters.
- `reference_contract`: versioned contract name, paired with the explicit
  `validate_reference(TestCase)` callback to `execute_suite()`.
- `case_payload_snapshot`: null/default, `hashes_only` or `full`.
- `requires_full_payload`: false by default; rejects any effective hashes-only
  policy when true. Such a profile must also opt into full persistence.
- `case_extra_keys` / `dataset_extra_keys`: reviewed metadata allowlists, empty by
  default, limited to 128 unique nonempty top-level keys each.

Supplied configuration is checked against public observed scorer attributes.
Missing custom scorer configuration is recorded as `unknown`; supplied
configuration is labelled `authored`, not automatically certified complete.
Judge settings are explicit and checked against the scorer's model identity.
Reference-dependent integrations must supply their named validator. It runs
for every selected case before the first target call; it must be pure and raise
on invalid reference contracts. The harness does not infer reference semantics.

A suite profile must match the supplied profile ID. A profile-less suite still
requires explicit profile and scorer arguments. Keyword overrides are only
`attempts`, `evaluation_profile` and `case_payload_snapshot`. A profile override
names the replacement whose configuration/scorers the caller supplies. Authored
defaults, explicit overrides and effective values are recorded separately.
Selection changes require another resolved suite definition. The authored Suite
is never mutated. Duplicate scorers, missing capabilities, unsafe/nonserializable
configuration, invalid references and empty membership fail before target calls.

## Definition snapshots and payload policy

Direct `run()` additionally accepts `fingerprint_scheme` (default v1),
`case_extra_keys`, and `case_payload_snapshot`. New snapshot options require v2;
an omitted v2 payload policy defaults to `hashes_only`. The runner does no suite
selection. It freezes fingerprints before calls, so populated classification
under v1 fails before execution. V2 snapshots and configuration are deep copies
taken before calls; adapters/scorers receive isolated case copies per attempt.
Historical v1 result shape and serializers remain unchanged.

Every v2 CaseResult retains copied `tags` and a `definition` object containing
`schema_version="case-definition-snapshot-v1"`, `fingerprint_scheme`, full
`definition_hash`, title, description, category, risk and projected `extra`.
There is no duplicate tag list inside the snapshot, and no verdict in a definition.
Absent legacy definitions are omitted from serialization, never backfilled.

`hashes_only` omits `resolved_cases` entirely. `full` explicitly persists selected
canonical case payloads, including input/reference and null classification
defaults, excluding `extra`. Both modes retain classification/hash context and
the same configured metadata projection; policy never changes definition hashes.
This policy does not redact independent target response evidence or explicitly
authored scorer configuration.

Metadata export denies everything by default. An allowlisted key copies its
entire finite JSON subtree: the integration must review that whole subtree for
safety. Names such as `provenance` imply no safety. Do not allowlist secrets,
credentials, hidden prompts or arbitrary client/provider state. This is an
explicit projection policy, not a general redaction system.

The versioned `config_snapshot` records:

- `organization_schema_version="run-organization-v1"`, dataset scheme, projected
  descriptor, full descriptor hash and snapshot completeness.
- Full source case hash, authored suite and its hash, portable locators,
  authored selection and ordered executed IDs.
- Effective profile (taxonomy contract, observed/authored scorer settings,
  explicit judge settings and safe parameters), overrides, attempts, target
  identity/capabilities and existing scorer snapshots.
- Payload policy and its source (`default`, `profile`, `run_override`), metadata
  allowlists and artifact capabilities.

`RunResult.dataset_hash` is always the executed ordered subset. The descriptor
hash binds full authored metadata even if its persisted snapshot is incomplete;
an incomplete snapshot cannot reproduce that hash. Store results with the
existing `SQLiteResultStore.save(result)`; no database migration is needed.
Duplicate IDs are rejected on save. Save failure leaves the caller's complete
in-memory result available for explicit retry under the original run ID.

## Isolation, replay and reader compatibility

Adapters receive TestCase internally but must forward only intended application
input. Expectations/taxonomy/metadata do not belong in SUT requests. State and
sessions remain isolated per attempt by the adapter contract.

Legacy rubric evidence still includes tags and must declare explicit inclusion.
Exclusion profiles require a named, reviewed projection; default rubric evidence
cannot claim exclusion. Integrations must test prompt/evidence invariance under
all classification/metadata edits. No prompt is silently changed by a profile.

Artifact capabilities record `definition_payloads` and
`external_source_cases_required`. Hashes-only always requires separately supplied
verified cases. Full payloads still need external cases if the run selected only
a subset or metadata needed to reproduce full definition hashes was omitted.
`reconstruct_source_cases(result)` succeeds only when full saved payloads and
projected metadata reconstruct the complete source exactly; otherwise it raises.
Pass reconstructed or separately supplied verified cases to `prepare_replay()`;
source availability does not authorize a judge call. Recorded profile judge
settings supply the original evaluator contract; absent settings remain unknown.

Readers must include the Milestone 3 snapshot implementation to consume these
v2 results (the package version has not been bumped). Older readers may discard
new fields and must not resave v2 results. New code preserves frozen v1 dataset,
run/replay serialization and calibration binding hashes exactly. No historical
artifact rewrite or calibration rebinding is needed. Grouped reporting and
comparison context consume these persisted definitions as described below.

## Group saved results

```python
from dataclasses import asdict
from harness.reporting.grouping import group_run_results, render_groups_markdown

result = store.load(run_id)
groups = group_run_results(result, by="category")  # also "tags" or "risk"
records = [asdict(group) for group in groups]       # JSON-serializable
markdown = render_groups_markdown(groups, title="Saved case evidence")
```

This pure API reads persisted `RunResult`/`CaseResult` evidence only. No current
dataset is opened, no missing snapshot is filled, and source objects are never
modified. Duplicate case IDs are rejected. Empty runs return an empty tuple.
Group order is first appearance in the stored run; members retain run order.
Scorer summaries are sorted by stable scorer name.

`GroupResult` contains:

- `dimension`, opaque `value`, and `classification_state`: `value`, `unclassified`,
  `unavailable`, or `untagged`. Known-null category/risk has state `unclassified`;
  a missing historical definition is separately `unavailable`.
- `definition_availability`: `complete`, `partial`, or `unavailable`, plus
  `definition_count`. Legacy tags remain usable even without a definition.
- `member_case_ids`, `case_count`, `judged_case_count`, and `attempt_count`.
- Separate `pass_count`, `fail_count`, `error_count`, and `skip_count`.
- `quality_pass_rate`, `error_rate`, and `scorers` containing each name, mean and
  successful `evidence_count`; plus `totals_additive`.

Category/risk partition cases into exactly one group each. Tags overlap: a case
belongs once to each distinct tag group. Duplicate legacy tags are deduplicated
for membership only; stored tags/hashes stay unchanged. Untagged cases have an
explicit null-valued `untagged` group. Tag totals are non-additive.

Quality pass rate is the mean of case pass rates over cases with PASS/FAIL
evidence, never an attempt-weighted or risk-weighted score. All-error, all-skip
and no-attempt groups have null quality pass rate. Error rate is ERROR attempts
divided by all attempts (zero when there are none). Successful independent scorer
values still contribute when another scorer errored. No composite gate is added.
For PASS/ERROR on one case and FAIL/SKIP on another, the group has four attempts,
one of every verdict, quality pass rate 0.5 and error rate 0.25.

The small Markdown renderer escapes authored labels, scorer names and supplied
titles as text. A literal category called `null` or `unavailable` remains a value,
not a reserved taxonomy term; its classification state disambiguates it.

## Compare saved evidence with explicit context

```python
from dataclasses import asdict
from harness.regression.comparison import compare_runs, render_comparison_markdown

comparison = compare_runs(baseline, candidate)
document = asdict(comparison)
markdown = render_comparison_markdown(comparison)
```

Existing numeric metrics, evidence-gain/loss properties, and legacy boolean flags
remain available. `regressed_case_ids` retains its descriptive meaning: observed
negative pass-rate deltas, not proven target regressions. Legacy booleans retain
their old scope; use the new context checks to assess v2 profile/definition
comparability. The renderer always says observed increase/decrease, unchanged,
or insufficient evidence. It adds no quality gate or significance claim.

`RunComparison.context` contains ordered `checks`, overall evaluation `status`,
separate `artifact_status`, `case_matching`, both ordered case lists and affected
IDs. Each `ContextCheck` includes name, `equal`/`changed`/`unknown`, reason,
baseline/candidate evidence, availability flags, affected IDs, and scope
(`evaluation` or `artifact`). Missing evidence is unknown, not equivalent.
Overall status is changed if any check in its scope changed; otherwise unknown
if any is unknown; otherwise equal. Individual unknowns remain visible even
when another check establishes a change.

Checks distinguish dataset identity/version, full/selected case hashes and
scheme, descriptor definition/hash, authored suite/hash, authored selection,
actual persisted membership, attempts, profile, observed/authored scorer settings,
judge settings, target identity/capabilities/version observations and evidence
schema. Per-case checks compare definition hashes, category, risk and tags.
Optional legacy evaluator/version observations are compared where recorded.
No application taxonomy vocabulary is inferred from IDs or metadata.

Examples of distinct observations:

| Scenario | Relevant output |
| --- | --- |
| Same complete recorded evaluation context | `dataset_identity: equal`, `case_definition_hash: equal`, evaluation status `equal` |
| Descriptor prose edited, same cases | `descriptor_definition: changed`, `case_definition_hash: equal` |
| Selection expression edited, same members | `selection_expression: changed`, `resolved_membership: equal` |
| Legacy run without classification/profile context | `case_category: unknown`, `evaluation_profile: unknown` |
| Different case fingerprint schemes | scheme changed/unknown; direct hash comparisons `unknown` |
| Hashes-only versus full, same evaluation | evaluation context `equal`; payload policy/artifact context `changed` |

Historical absence of a case scheme means v1 by the existing compatibility rule.
Unsupported/contradictory schemes do not establish hash equivalence, even if
strings happen to match. Descriptor, full case, subset and suite hashes retain
separate checks. Descriptor-only changes never become per-case changes by
inference. Comparison is descriptive inspection of recorded evidence, not a
replacement for replay's source-integrity verification.

Same IDs join within a shared named dataset ID; version changes remain explicit
qualification. Different named datasets suppress case joins entirely, even for
identical IDs. For backward compatibility, missing identity retains the existing
same-ID numeric diagnostics, explicitly scoped as `unverified_ids`; they do not
assert scenario equivalence. Run aggregate metrics always describe their own
populations independently. Similar wording never establishes identity.

`RunComparison.groups` contains baseline and candidate `GroupResult` records,
ordered membership evidence and affected IDs, pass-rate metrics, interpretation
and context qualification. Group union order is baseline first, then candidate-
only groups, for category/tags/risk in that order. Classification state is part
of the group key, so known null never joins historical unavailable. Changed
membership or unknown definitions/configuration cannot produce an unqualified
target-regression label. No extra matched-subset metric is silently substituted.

Payload persistence is compared separately from evaluation. Profile payload
requirements/defaults are excluded from evaluator equivalence; effective policy,
policy source, available material, metadata projection and descriptor completeness
are artifact checks. Full payloads allow input/reference field-fingerprint
comparisons without copying private bodies into reports. Hashes-only cannot
supply these details: that diagnostic is explicitly unknown, even if definition
hashes compare equal. A hashes-only artifact may therefore have equal evaluation
context but unknown field-level artifact diagnostics.

Recorded equality is not a causal claim or proof of complete custom-scorer
configuration. Missing authored configuration/judge settings remain unknown.
Target observation checks use only named normalized scalar version fields; they
never inspect live targets, provider clients or raw response objects.

## Run the complete offline example

```sh
.venv/bin/python examples/taxonomy_suites.py --output-dir /tmp/harness-taxonomy-example
```

Choose a fresh explicit output directory. The example refuses to overwrite
existing outputs and does nothing on import. It reads synthetic data from
`examples/data/taxonomy/`, previews four cases, runs two attempts through
in-memory fakes, saves/reloads both runs, then groups and compares saved evidence.
It creates only `runs.sqlite`, `analysis.json`, and `report.md` in that directory.
No network, credentials, Sales Agent dependency, UI or charts are involved.

Baseline evidence contains PASS, FAIL, ERROR and SKIP. Candidate quality pass rate
changes from 0.5 to 1.0 while error rate stays 0.25. The fake target revision also
changes, so comparison explicitly qualifies the observed increase. Overlapping
tag counts sum to five memberships for four cases. Grouped reporting does not
modify either run or its original fingerprints. Sales Agent adoption and the
50-case holdout study remain separately authorized future work.
