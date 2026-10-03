# Test taxonomy and dataset selection

Milestones 1–3 provide case classification, versioned fingerprints,
descriptor-aware loading, deterministic selection, suite execution and persisted
definition snapshots. Grouped reports, comparison-context extensions and UI are
not implemented yet. Direct runner calls default to v1; classified cases require
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
comparison-context changes remain Milestone 4.
