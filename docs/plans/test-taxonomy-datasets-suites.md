# Generic test taxonomy, dataset descriptors, and suites

This ExecPlan was created on 2026-10-02 and is **approved with the four
amendments incorporated on 2026-10-03**: strict v2 whitespace/direct validation,
explicit suite fingerprint types, explicit case payload persistence policy,
and deferred cross-study ID reuse decisions. Subsequent requests authorized
Milestones 1, 2 and 3 individually; **all three are completed and validated below**.
Milestones 4–5 remain unstarted; do not begin Milestone 4 without explicit approval.
Frozen datasets, stored runs, replay artifacts, and calibration artifacts are
unchanged. No live targets or judges were invoked.

Working branch: `feat/test-taxonomy-suites`. Integration branch:
`codex-evaluation`. Planning HEAD: `9198ad26d84576a319537909f146c5121412be99`.
Milestone 2 starting HEAD: `a3d9d96719d87be8b6ca30bcd387e61f8bc5aa67`
(committed Milestone 1; clean worktree verified before Milestone 2).
Milestone 3 starting HEAD: `3352ea57849865bd2d87f0e318bb5f6ff9b80086`
(committed Milestone 2; clean worktree verified before Milestone 3).
The worktree was clean before this document was added. Continue this coherent
slice on the existing feature branch; do not merge, rebase, delete branches,
or rewrite history. Check for intervening repository changes before starting
implementation. Follow `AGENTS.md` and update this living document at each
milestone with decisions, tests, deviations, and outcomes.

## Purpose and acceptance

Allow a dataset author to describe cases, bind a versioned dataset, preview a
suite's members, execute those members through the existing generic runner,
and inspect persisted results grouped by classification. Definitions remain
separate from execution results. A future dashboard can consume these outputs
without inferring taxonomy from application-specific IDs, references, or traces.

**The harness owns the taxonomy mechanism; datasets/integrations own the
taxonomy values.** Production generic code contains no application taxonomy
constants, special-case IDs, business rules, or category-to-scorer mappings.
Example values below are opaque fixture data, not vocabulary registered in core.

Acceptance requires all of the following:

- Existing frozen dataset bytes and hashes remain identical and reproducible.
- Existing run, replay, and calibration bindings still validate without
  rewriting artifacts or relaxing integrity checks.
- New descriptor-aware datasets use an explicit extended fingerprint scheme
  and a strict authoring path while legacy loading remains compatible.
- V2 identity/taxonomy values reject leading/trailing whitespace without
  normalization; legitimate internal whitespace remains meaningful and allowed.
- Suite case-content and descriptor pins are independently named and every
  supplied pin is checked before target calls.
- Selection is deterministic, inspectable, and completed before target calls.
- One uniform scorer list applies to a run; suite/run configuration selects
  scorers, while case references supply expectations.
- Execution-time classification snapshots survive JSON/SQLite round-trips and
  remain stable after source dataset or in-memory case edits.
- Every v2 execution records its case payload persistence policy. Generic runs
  default to `hashes_only`; `full` input/reference snapshots require explicit
  profile/run opt-in. Both preserve definition hashes and reporting context.
- Reports retain PASS, FAIL, ERROR, and SKIP separately, describe overlapping
  tag groups accurately, and qualify comparisons when context changes.
- All automated validation is offline and deterministic. No UI is built.

Milestones 1–4 constitute the generic implementation. Milestone 5 is adoption
preparation only. Authoring the 50-case study additionally requires explicit
coverage-matrix approval and completed, validated generic Milestones 1–4.

## Progress

- [x] Read the approved audit amendments and repository instructions.
- [x] Reinspect models, dataset hashing, runner, replay, calibration identity,
  comparison, persistence, existing plans, and relevant test contracts.
- [x] Verify frozen dataset byte/content hashes and record local artifact byte
  hashes read-only, without target/judge calls.
- [x] Draft architecture, file map, schemas, validation, acceptance, and recovery.
- [x] ExecPlan approved subject to four amendments (2026-10-03); amendments
  incorporated in the preceding document-only revision.
- [x] Milestone 1: compatibility fixtures, canonical schemes, TestCase fields
  (2026-10-03; explicit Milestone 1 implementation authorization).
- [x] Milestone 2: descriptor, strict loading, pure selection and preview
  (2026-10-03; explicit Milestone 2 implementation authorization).
- [x] Milestone 3: suite execution and immutable result snapshots
  (2026-10-03; explicit Milestone 3 implementation authorization).
- [ ] Milestone 4: grouped reporting and comparison context.
- [ ] Milestone 5: study layout and adoption documentation only.
- [ ] Complete offline acceptance and record final results/deviations.
- [ ] Separate future approval: 50-case coverage matrix and case authoring.

## Current boundaries and compatibility hazards

This section records pre-implementation findings at the inspected revision.
The milestone implementation records below describe the completed changes.

`src/harness/core/models.py::TestCase` currently has `id`, `input`, `reference`,
`tags`, and `extra`. It uses permissive Pydantic defaults: unknown top-level
fields are ignored; blank IDs/tags and duplicate tags are accepted. JSON data
inside `extra` survives model serialization, but arbitrary Python objects are
not necessarily JSON-safe. `extra` is the existing case metadata container.

`core/dataset.py::load_cases` reads ordered JSONL, ignores blank lines, and
reports invalid rows with file/line information. It returns a list, not a
Dataset. `hash_cases` hashes the entire current model dump per row. Adding even
nullable model fields would therefore change historical hashes without editing
a dataset file. The legacy algorithm also differs from `core/fingerprints.py`
in Unicode escaping and non-finite-number behavior; do not conflate them.

`core/runner.py::run` accepts an already selected sequence and scorer instances.
It checks duplicate IDs/names, positive attempts, and the union of scorer
capability requirements, then applies every scorer to every attempt. Its
`dataset_hash` describes the executed sequence, not necessarily the full file.
Scorer snapshots record known attributes but are not a complete generic
configuration serializer. `CaseResult` currently persists ID, tags, attempts.

The Sales Agent recipes already record `full_dataset_hash`, `selection`,
`resolved_cases` excluding `extra`, and allowlisted provenance in
`RunResult.config_snapshot`. Their 14-case validation is a frozen-study rule,
not a constraint for new generic datasets. Reuse their separation of definition
and target evidence without moving their vocabulary or policies into core.

`core/replay.py::prepare_replay` verifies selected/full dataset hashes, stored
resolved cases, tags, the individual case hash, source response, and evaluator
configuration. `core/calibration.py` hashes serialized PreparedReplay objects
and RunResults to validate identities and human bindings. Consequently,
preserving dataset hashes alone is insufficient: adding null fields to nested
CaseResults or SourceProvenance can break calibration too.

`core/store.py::SQLiteResultStore` already persists full JSON documents and
supports read-only loading with the stored document's fingerprint. Keep its
SQL schema. `regression/comparison.py::compare_runs` exposes descriptive deltas
and compatibility flags but no classification snapshots or group comparisons.

Two existing execution-boundary debts are explicitly retained:

1. `Target.invoke(TestCase)` exposes the complete case to adapter code.
   Adapters must forward only intended application input; expectations,
   taxonomy, and provenance must not reach the system under test.
2. `RubricJudgeScorer` includes tags in its default evidence builder. Preserve
   that legacy behavior and prompt bytes. New profiles must explicitly declare
   their taxonomy evidence contract rather than silently inheriting a claim
   that taxonomy cannot affect judging.

## Decisions and explicit non-goals

Retain all five existing TestCase fields. Add `title`, `description`, `category`,
and `risk` as optional strings. Do not add `metadata` alongside `extra`.
Category is the primary classification; tags are cross-cutting; risk expresses
declared criticality. Core treats category, tags, and risk as opaque strings.
Documentation may recommend `low / medium / high / critical` for risk, but
there is no enforced risk enum, ordering, weighting, or automatic gate.

Keep `reference` open and scorer-specific. Keep capability requirements as
evidence capability strings. Do not derive capabilities, scorer selection, or
verdicts from classification. Do not put PASS/FAIL or latest status in TestCase.

No dynamic imports, plugin registry, scorer dispatch per case, suite nesting,
query DSL, regex/exclusion filters, random sampling, taxonomy hierarchy,
multi-dataset suites, dataset/taxonomy SQL tables, new indexes, background
scheduler, UI, live evaluation, model tuning, or Target protocol rewrite.
Do not change calibration cohort/strata meaning or replace its reporting.
Do not rename existing scorer names or change legacy judge evidence/rubrics.
Do not author the 50 cases or modify either frozen 14-case dataset.

## Canonical representations and compatibility strategy

### Scheme names and exact content

Introduce explicit scheme identifiers `dataset-cases-v1` and
`dataset-cases-v2`, owned by the dataset fingerprint boundary. Retain
`replay-canonical-json-v1` unchanged for existing generic object fingerprints.
These identifiers describe representations, not authored dataset versions.

Proposed API in a small `core/case_fingerprints.py` module:

```text
case_payload(case, *, scheme) -> JSON object
hash_case_definition(case, *, scheme) -> SHA-256 hex
resolved_case_payload(case, *, scheme) -> JSON object
```

`dataset.py::hash_cases(cases, *, scheme="dataset-cases-v1")` retains its
existing default and delegates representation explicitly. Unknown schemes are
errors. Do not silently fall back or guess a scheme from populated fields.

For v1, construct exactly the five legacy fields with their defaults:
`id`, `input`, `reference`, `tags`, `extra`. Preserve `reference: null`, empty
lists/dictionaries, list ordering, string values, and nested values. Hash each
row with the existing `json.dumps(sort_keys=True, separators=(",", ":"))`
settings, UTF-8 encoding, and a trailing newline per case. No scheme prefix is
inserted into this existing digest. Document the old default ASCII escaping
and number behavior rather than silently improving them. A populated new
TestCase field passed to v1 hashing is an error directing the caller to v2;
classification must never disappear from a definition fingerprint.

For v2, build the same five fields plus all four new fields, including their
explicit null defaults. Validate finite JSON data and hash:

```text
SHA256(canonical_json({"scheme": "dataset-cases-v2", "cases": [payload, ...]}))
```

Here `canonical_json` is the existing sorted, compact UTF-8 representation
with `ensure_ascii=False` and `allow_nan=False`. Dictionary order and JSON
whitespace are irrelevant. Case order, tags order, all definition fields,
reference expectations, and full authored `extra` affect the digest. Omitted
new optional values and explicit nulls have the same v2 definition meaning.
Do not introduce a second taxonomy-only or evaluation-only hash in this slice.

Single-case definitions need a separate compatible rule: v1 uses the existing
`fingerprint(five_field_payload)` to preserve replay case hashes; v2 uses
`fingerprint({"scheme": "dataset-cases-v2", "case": payload})`. A single-case
definition hash is not the hash of a one-element dataset. Mutation detection
uses the full extended in-memory case, independently of legacy hash projection,
so a builder cannot mutate a new field without detection.

When the v2 payload persistence policy is `full`, resolved-case snapshots use
the scheme's payload excluding `extra`, preserving the existing evaluator-
reference snapshot convention. Under `hashes_only`, omit these payloads from
the result. Safe metadata is stored separately in either mode; full authored
metadata still participates in definition hashes. Payload persistence policy
does not change the canonical definition or dataset hash algorithms. Existing
legacy resolved-case snapshots retain their historical representation exactly.

### Serialization protection beyond dataset hashing

The four new nullable TestCase fields must be omitted from ordinary legacy
model serialization when null, without dropping any existing null/default
field. Use a narrowly scoped serializer and test both Python and JSON dumps,
including nested models and include/exclude calls. The explicit v2 canonical
builder still inserts its four null fields. This keeps existing recipe
`model_dump(exclude={"extra"})` outputs stable for legacy cases.

For result snapshots, add one optional `CaseResult.definition` object in
Milestone 3. Omit only this new field when absent, including when nested in a
RunResult. Do not fill missing historical snapshots by consulting today's
dataset. Existing `tags`, attempts, response fields, and defaults retain their
exact serialization behavior. Keep RunResult's top-level schema unchanged;
new run context goes into documented `config_snapshot` entries.

For replay, add an optional `SourceProvenance.dataset_fingerprint_scheme`:
absent means v1, v2 is written explicitly for new sources. Omit the new field
when absent rather than emitting null. Existing PreparedReplay/calibration
digests must remain exact. Update only the boundaries needed to carry and
verify this distinction; do not change existing replay input/prompt/evidence
hash algorithms or automatically populate new keys on loaded v1 artifacts.

`prepare_replay` selects the scheme from recorded run context, validates
persisted resolved cases through that scheme when policy is `full`, and rejects
unknown/contradictory schemes or payload policies. Missing scheme in a historical
run means v1; do not infer a new persistence policy for that run. A run claiming
v2 must have its definition/classification snapshots, explicit payload policy,
and execution context. `hashes_only` does not require `resolved_cases`; `full`
does. Rebuilds must verify v2 classification snapshots and definition hashes
against verified source cases. Do not permit v2 payloads to be verified with a
five-field projection.

Hash-only artifacts support grouping and definition-hash comparison without
source inputs. They cannot reconstruct missing input/reference bytes from a
digest. Replay may use separately supplied source cases only after verifying
the recorded scheme, selected/full dataset hashes, definition hashes, and
execution/evaluator context. Missing or mismatched material is an explicit
replay preflight error before any judge call, never an inferred current-dataset
replacement. Full snapshots preserve input/reference but do not promise that
all external source requirements disappear: omitted authored `extra` or other
evaluator dependencies can still require verified source material. Expose these
artifact capabilities and source requirements rather than claiming every saved
run is self-contained for exact replay.

Stored JSON fingerprints remain based on the original stored document through
`load_with_fingerprint`. Calibration's existing model-dump fingerprints must
also stay equal for supported legacy documents; preserving only the raw hash
would not fix those call sites. Test `historical_observations`, `verify_rebuilt`,
ReplayResult reload, and calibration identity/binding validation together.
If narrow serialization compatibility cannot preserve these contracts, stop
Milestone 1 and revise the plan; never regenerate human bindings as a repair.

### Frozen protection values

Read-only measurements at planning time:

| File | Byte SHA-256 | Legacy case hash |
| --- | --- | --- |
| `datasets/salesagent/baseline.jsonl` | `f24ffe05b08d75848860f71ef726cf96dccb78e457e5757fb7144cd30db4a747` | `c1a73ef207f2cabe3292d743504f7249f4729825d785adff5b6bf14ad6a7b12b` |
| `datasets/salesagent/semantic.jsonl` | `3200acd541c6db9f3bb3301186f4213746e177c0c3048b4ad99434da590791a9` | `33654c3f4870efc67edd8e30a6ae0a82c17eb58c8c30cb323add5d0efe414849` |

Local artifacts, used only for optional read-only acceptance and never required
as private CI fixtures:

| File | Byte SHA-256 |
| --- | --- |
| `runs/salesagent-semantic.sqlite` | `293156e08238d03658fbe73199a853a033d703fbb20db9c64a0b18271a77da67` |
| `runs/judge-replay.sqlite` | `7ab0ebe516415be162807f8d68299afc44b3a93bda6005133072f15d330b2a6d` |
| `runs/calibration/salesagent-human-v1-analysis/result.json` | `c54b510b6b67ab319af67ccd232cd79199a0bad254043bc0a91629f6fe0d6984` |

Before changing models, generate small synthetic legacy run/replay/calibration
fixtures using current code, pin their serialized JSON and expected hashes,
and include them under `tests/fixtures/taxonomy/`. Do not generate the expected
legacy representation using already changed models. Do not copy private runs
or human annotations into test fixtures. Existing dataset constants remain
unchanged; updating them to make a failing test pass is prohibited.

## Dataset descriptor and strict authoring path

Add `DatasetDescriptor` and `LoadedDataset` in `core/dataset.py` and preserve
`load_cases(path) -> list[TestCase]`. Proposed new API:
`load_dataset(descriptor_path) -> LoadedDataset`. The descriptor is JSON;
case data remains one TestCase per nonblank JSONL line.

```json
{
  "schema_version": "dataset-descriptor-v1",
  "id": "example-evaluation",
  "version": "study-v1",
  "title": "Example evaluation study",
  "description": "An authored collection of reusable cases.",
  "cases": "cases.jsonl",
  "extra": {"provenance": {"source_revision": "fixture-v1"}},
  "fingerprint_scheme": "dataset-cases-v2"
}
```

An example case, containing no scorer class or status:

```json
{
  "id": "case-a",
  "title": "First example",
  "description": "Check the defined output for this input.",
  "input": "alpha",
  "reference": "alpha",
  "category": "family-a",
  "tags": ["quick", "cross-cutting"],
  "risk": "high",
  "extra": {"provenance": {"source": "authored-fixture"}}
}
```

Descriptor validation rejects unknown keys, duplicate JSON object keys,
non-finite JSON numbers, blank identity/version/binding strings, leading or
trailing whitespace in dataset ID/version, and unsupported schema/scheme values.
Internal whitespace in identity values remains allowed. This first descriptor
schema supports v2 only. Resolve
`cases` relative to the descriptor's directory, never process cwd; use a local
relative binding, with no URLs, absolute paths, or parent traversal in this
initial portable format. Do not fetch remote data. Keep the authored locator
in snapshots, not the resolved machine-specific absolute path.

`LoadedDataset` holds descriptor, ordered cases, descriptor/source locators,
full case fingerprint, and descriptor fingerprint. Locators used for I/O are
not implicitly included in content hashes. Hash the normalized descriptor
(including authored relative binding and full authored `extra`) under
`dataset-descriptor-v1`, excluding any derived hash fields. Formatting changes
do not change it; descriptor description/provenance changes do. Authored
`version` is never generated from or substituted for either fingerprint.

The new loader applies strict authoring checks without changing legacy
`load_cases` behavior. Prefer a small internal strict validation model/helper
that returns the ordinary TestCase, not a second public case abstraction.
Validate every row before selection:

- Reject missing/blank IDs, duplicate IDs with both source line locations,
  unknown top-level fields, incorrect declared types, and non-object rows.
- Reject blank non-null title/category/risk. Description may be empty text;
  it is prose, not a selector identity. Null is allowed for optional fields.
- Reject blank or duplicate tag values in v2. Reject tag coercions, including
  non-string elements and non-array values. Missing tags mean an empty list.
- Reject leading/trailing whitespace in case IDs, category, risk, and every
  tag; do not silently trim it. Apply the same rule to dataset ID/version,
  suite ID, evaluation-profile IDs (including overrides), and selector values.
  Internal whitespace, such as `family a`, remains allowed and significant.
  Compare the value to its whitespace-stripped form only to detect invalid
  boundaries, never to replace the authored value. Preserve accepted strings
  and array order; do not lowercase, sort, or deduplicate.
- Require JSON object `extra`, with recursively JSON-compatible finite values.
  Preserve nested lists/objects, booleans, numbers, strings, and nulls.
- Reject duplicate JSON keys and non-finite values in input/reference too.
  Keep the existing public input/reference union shapes.
- Retain filename and physical line number for row errors; descriptor errors
  identify descriptor path and field. Avoid dumping whole inputs into errors.

Place safe validation for new TestCase fields on those fields themselves:
non-null `title` must be a nonblank string; non-null `category`/`risk` must be
nonblank strings without leading/trailing whitespace. Keep prose description
content unchanged, including empty text and whitespace. These new-field checks
apply to ordinary Python construction/model validation as well as JSON loading.
Do not add validators to legacy `id`, `tags`, `input`, `reference`, or `extra`
that would alter their existing model/loader behavior.

Direct construction is not an exemption from the remaining v2 rules. Use a
shared v2 validation boundary before canonical v2 hashing and execution, also
called by descriptor loading, to check existing-field IDs/tags, finite JSON,
and other v2 authoring constraints. This protects v2 Python callers and catches
post-construction mutation without changing legacy TestCase construction or
v1 loading. Add direct-construction tests for the new fields and v2-boundary
tests for existing fields; do not introduce a second public TestCase type.

Core validates structure, not a reference's application semantics. Integration
validators remain at recipe/pack boundaries. Profile-specific reference
validation covers all selected cases before any target call. Existing frozen
study loaders retain their stronger whole-study preflight policies.

## Selector semantics, examples, and preview

Add `CaseSelection` and `select_cases` in `core/selection.py`. Selection accepts
validated cases and never mutates, invokes, or scores them. Model fields are
optional arrays of strings; omitted means unconstrained. Supplied arrays must
be nonempty with nonblank values and no leading/trailing whitespace. Internal
whitespace remains allowed. Reject unknown selector keys and explicit null
arrays. Reject duplicate requested values in all selector arrays for
consistent authoring diagnostics, including the required duplicate-ID error.

Semantics are fixed:

| Input | Result |
| --- | --- |
| No selectors / `{}` | All cases |
| Multiple selector fields | AND across fields |
| `case_ids`, `categories`, `risks` | OR within each field |
| `tags_any` | At least one requested tag present |
| `tags_all` | Every requested tag present |
| `category`/`risk` absent on a case | Does not match a requested value |
| String equality | Exact, case-sensitive |
| Result order | Dataset order, never request-array order |
| Unknown explicit ID | Error, checked before other filters |
| Empty selected result | Valid preview; invalid execution |

Legacy duplicate tags, if present in an explicitly supplied legacy sequence,
do not duplicate selected cases. Reject duplicate input case IDs rather than
return an ambiguous preview. Non-ID values with no match produce no members;
they are not checked against a global taxonomy vocabulary.

For a dataset ordered as follows:

| ID | Category | Tags | Risk |
| --- | --- | --- | --- |
| `case-a` | `family-a` | `quick`, `cross-cutting` | `high` |
| `case-b` | `family-b` | `quick` | `low` |
| `case-c` | `family-a` | `cross-cutting` | absent |

Examples:

```json
{}
{"case_ids": ["case-c", "case-a"]}
{"categories": ["family-a"], "tags_any": ["quick"]}
{"tags_all": ["quick", "cross-cutting"]}
{"case_ids": ["case-a", "case-b"], "risks": ["high"]}
{"categories": ["family-a"], "risks": ["low"]}
```

Their ordered memberships are respectively `[a,b,c]`, `[a,c]`, `[a]`, `[a]`,
`[a]`, and `[]`, where letters abbreviate the full IDs above. Unknown `case-z`
is an error even if another filter would exclude it. `{"tags_any": []}` is
invalid. `{ "tags_any": ["Quick"] }` matches nothing in this dataset.
`{"tags_any": [" quick"]}` and `{"case_ids": ["case-a "]}` are validation
errors, not alternative identities or values to be trimmed. A selector value
`"family a"` is valid but matches only that exact internally spaced category.

Provide serializable preview data containing dataset identity/version, source
and executed-subset hashes with schemes, authored selection, ordered selected
IDs, total/selected counts, and `executable` with a reason for an empty result.
Preview requires no target or judge construction. An empty v2 sequence has a
well-defined fingerprint but may not be passed to the runner.

## Suite model and execution boundary

Add `Suite`, `DatasetBinding`, `ResolvedSuite`, `resolve_suite`, and
`execute_suite` in `core/suites.py`, with a strict local JSON suite loader.
Use one dataset per suite; a suite never embeds copied TestCases.

```json
{
  "schema_version": "suite-v1",
  "id": "quick-checks",
  "title": "Quick checks",
  "description": "Reusable selection and attempt policy.",
  "dataset": {
    "id": "example-evaluation",
    "version": "study-v1",
    "descriptor": "../dataset.json"
  },
  "selection": {"tags_any": ["quick"]},
  "attempts": 2,
  "evaluation_profile": "exact-output-v1"
}
```

The binding accepts two distinctly named optional pins:

- `expected_case_fingerprint`: the full ordered **case** fingerprint under the
  descriptor's declared scheme, never the executed subset or descriptor hash.
- `expected_descriptor_fingerprint`: the fingerprint of the normalized authored
  dataset descriptor, including its full authored metadata, computed before any
  safe persistence projection.

A suite can pin case content only or both case content and the descriptor
definition. Validate every supplied digest's shape and verify every supplied
pin before target calls; never substitute one fingerprint type for another.
The executed subset fingerprint remains a third, separately recorded concept.
For example, binding additions may be:

```json
{"expected_case_fingerprint": "<full-ordered-case-sha256>"}
{"expected_case_fingerprint": "<full-ordered-case-sha256>", "expected_descriptor_fingerprint": "<normalized-descriptor-sha256>"}
```

These digest placeholders illustrate field meanings and must be replaced with
actual SHA-256 values in executable suite files. A descriptor-only edit with
unchanged cases passes a case-content pin but fails a stale descriptor pin.
Reject the superseded ambiguous pin field as unknown in the strict schema.
Require exact bound dataset ID/version equality without boundary whitespace. The
suite's descriptor locator resolves relative to the suite file; allow relative
parent references here to support a `suites/` subdirectory, but no remote URL
fetches or implicit current-directory resolution. The stricter case-file
binding within a descriptor stays as specified above.

Require nonblank suite/profile IDs without leading/trailing whitespace,
including directly constructed bindings and run profile overrides. Allow
legitimate internal whitespace. Require a strict positive integer attempt count
(reject booleans/fractions), known schema, and no unknown top-level keys.
Optional title/description follow the same text rules as the descriptor.
No general mutable configuration dictionary or arbitrary executable spec is
accepted in Suite JSON.

`resolve_suite` loads/binds/validates the dataset and selection and returns a
preview plus an in-memory resolved execution input. It makes no target/judge
calls. `execute_suite` receives that resolved input, an explicitly supplied
target, uniform scorer instances, and explicit safe profile configuration.
Recipe code resolves logical profiles with ordinary functions; core does not
import a class based on a dataset string or discover plugins.

Require the supplied resolved profile ID to match the effective profile: the
suite's profile unless an explicit recorded profile override replaces it.
A suite without a profile requires explicit run scorer/configuration
input; no default scorer is inferred. Supported run overrides initially are
attempt count, explicit profile replacement, and the case payload snapshot
policy described below. Record authored defaults, requested overrides, and
effective values. A profile requiring full payloads rejects a `hashes_only`
override before target calls; changing such a requirement needs an explicitly
different compatible profile. Do not mutate the original suite.
Change selection by authoring/resolving another suite value; do not invent
hidden CLI-only selection precedence in this slice.

Resolved profile configuration records stable scorer names, kinds, capability
requirements, thresholds, versioned rubrics/evidence projections and judge
settings where applicable, plus profile-specific safe parameters. Reuse
`_scorer_snapshot` and explicit judge configuration rather than introspecting
private objects/environment. Check supplied configuration against observable
scorer attributes before execution. Arbitrary custom scorers remain supported,
but the caller owns complete authored configuration for comparability; missing
configuration is recorded as unknown, not fabricated as equivalent.

Reject empty execution, bad bindings, invalid selected reference contracts,
duplicate scorer names, unsupported scheme, unsafe snapshot data, and missing
capabilities before invoking the target. A recipe can instantiate clients only
after preview/profile preflight; core cannot prevent side effects in a target
the caller has already constructed. Existing target/scorer runtime failures
continue to produce ERROR and preserve independent scores.

Minimal runner extension: accept an explicit fingerprint scheme (default v1),
a bounded metadata-key allowlist for new definition snapshots, and an explicit
v2 case payload snapshot policy (default `hashes_only`). Selection
remains outside `run`; the runner knows no suite filter values. Freeze dataset
hashes and case-definition snapshots before invoking any target, including
before a custom adapter can mutate an input object. Legacy runs without a new
context retain old output shape. V2 direct callers must opt into v2 explicitly.
Do not post-hoc relabel a v1 execution as v2 by replacing only its hash.

### Isolation and judge contract

Document adapter forwarding rules in `targets/base.py` and prove them with
recording application callables and the existing mock HTTP adapter tests.
Changing only classification must leave application request bytes unchanged.
State/session isolation and attempt lifecycle remain the adapter contract.

Do not silently change the default RubricJudgeScorer builder. New evaluation
profiles record `taxonomy_evidence` as `excluded` or `explicitly_included`.
Profiles claiming exclusion supply an evidence builder with a named/versioned
projection and tests proving category/tags/risk/title/description/extra changes
do not change prepared prompt/evidence bytes. Generic legacy builder usage is
explicit inclusion of tags, never mislabelled as exclusion. No new default
projection behavior is needed to ship this milestone. A future projection
change requires a new version and comparison/replay compatibility tests.

## Execution-time persistence shape

Add `CaseDefinitionSnapshot` to `models.py` and optional
`CaseResult.definition`. Keep existing `CaseResult.tags` as the authoritative
copied tag list; avoid a second persisted tag list inside the snapshot.

Illustrative fragment (digest strings below are placeholders):

```json
{
  "case_id": "case-a",
  "tags": ["quick", "cross-cutting"],
  "definition": {
    "schema_version": "case-definition-snapshot-v1",
    "fingerprint_scheme": "dataset-cases-v2",
    "definition_hash": "<case-definition-sha256>",
    "title": "First example",
    "description": "Check the defined output for this input.",
    "category": "family-a",
    "risk": "high",
    "extra": {"provenance": {"source": "authored-fixture"}}
  },
  "attempts": []
}
```

No verdict is stored on the definition. Attempts contain execution verdicts.
The definition hash binds the full case, including unexported metadata. The
snapshot alone is not a reconstruction of input/reference or redacted metadata.

### Explicit case payload persistence policy

Record `case_payload_snapshot` as `hashes_only` or `full` in v2 run context.
This is a profile/run persistence decision, not part of TestCase or its
definition fingerprint. Generic v2 behavior defaults to `hashes_only`; profile
configuration or an explicit allowed run override can opt into `full`. Do not
implicitly opt in because an available scorer happens to be a judge. The exact
API spelling may be refined during implementation without changing these rules.

| Persisted material | `hashes_only` | `full` |
| --- | --- | --- |
| Definition hash and fingerprint scheme | Required | Required |
| Execution-time title/description/category/risk/tags | Required | Required |
| Configured safe case metadata projection | Required | Required |
| Descriptor/suite/selection/effective execution context | Required | Required |
| Canonical case input/reference in `resolved_cases` | Absent | Required |

For `full`, persist selected resolved-case payloads with the versioned canonical
input/reference representation (excluding full authored `extra` as described
above). For `hashes_only`, omit `resolved_cases` entirely rather than storing
empty or fabricated input/reference values, and do not copy these bodies into
another run-context field. This policy controls TestCase definition payloads;
it does not redact independently recorded target response evidence or explicit
scorer configuration. No general redaction/security framework is introduced.

Persist the effective policy and whether it came from a profile default or
explicit run override. Expose artifact capabilities such as persisted definition
payload availability and whether verified external source cases are required
for replay. Do not equate payload availability with permission to invoke a
judge. Exact replay profiles can require `full`; a future Sales Agent semantic/
replay profile may opt in. Existing frozen Sales Agent runs keep their original
`resolved_cases` and lack of this new key unchanged; legacy verification uses
their historical representation rather than retroactively assigning a policy.

### Run context

Use documented, versioned keys in `config_snapshot` for v2 suite execution:

```text
organization_schema_version: "run-organization-v1"
dataset_fingerprint_scheme: "dataset-cases-v2"
dataset_descriptor: {normalized descriptor with safe projected extra}
dataset_descriptor_hash: <hash of full authored descriptor>
dataset_descriptor_snapshot_complete: true | false
full_dataset_hash: <full ordered cases under v2>
suite: {authored validated suite}
suite_hash: <fingerprint of normalized authored suite-v1 document>
selection: {expression: {...}, case_ids: [ordered resolved IDs]}
case_payload_snapshot: "hashes_only" | "full"
case_payload_snapshot_source: "default" | "profile" | "run_override"
resolved_cases: [v2 canonical case payloads excluding extra; present only for full]
evaluation_profile: {id, effective safe configuration, taxonomy_evidence}
overrides: {only explicitly supplied attempts/profile/payload-policy override values}
metadata_snapshot_policy: {case_extra_keys: [...], dataset_extra_keys: [...]}
attempts: <effective count, retaining existing key>
scorers: <effective scorer snapshots, retaining existing key>
target: <existing target identity>
target_capabilities: <existing capability snapshot>
```

`RunResult.dataset_hash` stays the executed ordered subset fingerprint.
`dataset_path` remains the case source locator, while the descriptor and suite
locators belong to their context. Dataset, descriptor, suite, and evaluation
fingerprints are intentionally distinct. Two files at different absolute
checkout locations can be equivalent; two different authored descriptor
bindings are visibly different descriptor definitions.

Metadata export is deny-by-default: copy only explicitly allowlisted top-level
`extra` keys supplied by trusted recipe/profile configuration, after validating
their complete nested values as finite JSON. An allowlisted subtree must be
reviewed as safe by that integration; JSON compatibility alone cannot certify
privacy. Never infer safety from a key called `provenance`, and never serialize
credentials, hidden prompts, raw provider objects, or arbitrary client state.
Do not create a content-redaction/security framework in this milestone.

Default metadata projections are empty. Persist the policy, and mark a
descriptor snapshot incomplete if its `extra` was projected. The descriptor
hash still binds the complete authored descriptor; do not claim that a redacted
snapshot reproduces it. Case snapshots always distinguish the full definition
hash from projected `extra`. Existing Sales Agent recipes retain their
allowlists. When explicitly enabled by `full`, input/reference snapshots are
evaluator artifacts with the same sharing restrictions as their source datasets,
never target request bodies. Neither policy changes the configured safe metadata
projection or implies that arbitrary case metadata may be copied.

Take deep execution-time copies before all target calls and never mutate them
after execution. Mutation of a caller's dataset/selector/scorer configuration
must not rewrite historical context. Store and reload through the existing
SQLite JSON column without SQL migration. No new dataset listing database is
necessary: descriptor loading and suite previews are the future browsing API.

## Reporting and comparison semantics

Add `reporting/grouping.py` with a pure `group_run_results(result, by=...)`
function for category, tags, or risk. Return serializable records, with an
optional small Markdown renderer exercised by the offline example. Escape
authored text in rendering; never interpret taxonomy strings as markup/code.

Group records include dimension, opaque value (or null for unclassified),
definition availability, ordered member IDs, case count, judged case count,
attempt count, separate PASS/FAIL/ERROR/SKIP counts, aggregate pass rate,
error rate, and scorer means with evidence counts. Category/risk each partition
cases by their one field value. A case with two tags appears once in each tag
group; tag totals are non-additive. Legacy duplicate tags count a case once per
distinct tag for reporting only, without rewriting stored tags or fingerprints.
Untagged cases have an explicit untagged group. Missing historical definition
snapshots mean classification is unavailable, distinct from a known v2 null
category/risk. Do not fetch current datasets to backfill historical groups.

Preserve existing arithmetic: mean of case pass rates over judged cases;
attempt error fraction separately. Empty/all-error/all-skip groups have null
quality pass rate, not zero. Scorer means retain independent successful scores
even on an attempt whose other scorer errored; report evidence counts so that
scope is clear. Do not average scores into a new quality gate or weight risk.

Example: a group containing case-a with PASS/ERROR and case-c with FAIL/SKIP
has two cases, four attempts, one of each verdict, pass rate 0.5 (mean of case
rates 1 and 0), and error rate 0.25. A tag shared by these cases has the same
metrics; another tag on case-a contributes to an overlapping group and cannot
be summed into a larger independent sample.

Extend comparison with structured context checks: `equal`, `changed`, or
`unknown`, with reasons, plus affected case IDs and baseline/candidate member
lists. Preserve existing descriptive metrics and legacy flags for callers.
Compare at least:

- Dataset identity/version, full source hash, executed subset hash, and scheme.
- Descriptor changes separately from per-case definition hash changes.
- Authored suite/selection changes separately from resolved membership changes.
- Effective evaluation profile/scorer/judge configuration and attempt policy.
- Per-case category/risk/tags and classification/group membership changes.
- Existing target identity, model/version and evidence-schema observations.
- Payload persistence policy and available source material, separately from
  quality/evaluator changes. Hash-only runs still support definition-hash and
  classification comparisons, but cannot supply field-level input/reference
  diffs or reconstruct missing source bodies from the artifact alone. Expose
  those limits explicitly; any additional source material must be verified.

A payload policy change alone is an artifact availability difference, not proof
of target or scoring behavior change. Exclude persistence-only policy/default/
override fields when deriving evaluator equivalence while comparing them in
artifact context. A corresponding profile/evaluator change must still be
reported through the normal evaluation-context checks.

Missing legacy metadata is unknown, not proof of equivalence. Different schemes
are visibly incompatible/unknown for direct content comparison unless verified
through an explicit supported representation; never compare hash strings from
different schemes as if they shared meaning. Case joins remain by stable ID
within compatible dataset identity context; different named datasets cannot
be treated as the same scenarios solely because IDs match.

Keep existing `regressed_case_ids` as descriptive negative pass-rate deltas for
API compatibility, document this limit, and ensure new reports call them
observed decreases unless compatibility is established. Grouped comparison
exposes membership changes rather than reporting the shifted group as a target
regression. Present baseline/candidate group metrics independently and suppress
an unqualified regression classification when membership/definitions/evaluation
context differ. A matched-case diagnostic may be shown only with its scope
explicit. Do not introduce a new regression gate or statistical significance
claim in this milestone.

The future UI can keep definition browsing independent of history. Latest
canonical result must eventually be scoped by compatible target, dataset
identity/revision, suite selection, and effective evaluation profile; a single
diagnostic run is not a replacement for a full-suite result. This plan supplies
context and timestamps, not a latest-status service or UI policy engine.

## Affected files and milestone implementation sequence

### Milestone 1 — fingerprint compatibility and case classification

Before adding fields, freeze synthetic compatibility fixtures with the current
code and both frozen dataset constants. Then implement explicit representations
and optional TestCase fields together with legacy serialization protection.
Adapt replay verification and source provenance only as required. Do not ship
an intermediate model change that invalidates old hashes.

Known files/classes:

- `src/harness/core/models.py`: TestCase fields, safe new-field validators, and
  narrow serializer; legacy-field validation remains unchanged.
- `src/harness/core/case_fingerprints.py` (new): payload/hash scheme helpers.
- `src/harness/core/dataset.py`: explicit scheme argument, legacy default.
- `src/harness/core/replay.py`: prepare_replay and SourceProvenance compatibility.
- `src/harness/core/fingerprints.py`: reuse unchanged canonical primitives;
  no algorithm/version change is expected.
- `src/harness/core/calibration.py`, `calibration_io.py`, `store.py`: audit hash
  call sites; edit only if required to preserve exact legacy contracts. No
  schema migration or calibration rebinding.
- `tests/fixtures/taxonomy/` (new synthetic JSON fixtures),
  `tests/test_case_fingerprints.py` (new), `test_dataset.py`, `test_models.py`,
  `test_replay.py`, `test_calibration.py`, `test_calibration_io.py`.

Tests: exact dataset byte/hash constants; default and explicit v1 equivalence;
legacy unknown fields/blank tags and legacy ID/tag whitespace remain accepted;
direct construction rejects blank new title/category/risk and surrounding
category/risk whitespace while allowing internal whitespace and prose description;
v2 hash validation rejects bad IDs/tags even from Python-created or mutated
cases without tightening legacy fields; legacy nested serialization
matches pre-change fixtures; v1 rejects populated new fields; v2 changes for
each new field, input, reference, extra, tag order, and case order; defaults and
JSON formatting are stable; unknown schemes and non-finite v2 values fail;
Unicode representation is pinned; rebuilt legacy replay case/document hashes,
prepared evidence/prompt bytes, and calibration identity/binding stay exact;
mutated or mismatched sources still fail. Include v2 replay round-trip and
classification tampering failure; full versus hash-only source requirements
must be explicit without modifying legacy binding behavior. Existing judge
evidence tests remain intact.

Exit criterion: compatibility tests pass without changed golden hashes or
rewritten historical artifacts. Record the exact representation in ADR 0006.

### Milestone 2 — descriptor, strict loader, selector

Implement descriptor-aware loading and the deterministic selector. Keep legacy
loader behavior isolated. Provide preview data without targets or scorers.

Files: extend `core/dataset.py`; add `core/selection.py`;
`tests/test_dataset_descriptor.py`, `tests/test_selection.py`; extend
`test_dataset.py`; add synthetic fixture descriptors/JSONL under tests.

Tests: descriptor round-trip, authored metadata preservation, relative binding
independent of cwd, missing/unreadable file, empty dataset, unsupported schemes,
unknown fields, duplicate keys/IDs with line numbers, blank values, wrong types,
duplicate/blank tags, boundary whitespace in IDs/category/risk/tags/dataset
ID/version, allowed internal whitespace, direct model versus JSON parity,
invalid nested JSON, and unchanged legacy acceptance.
Test every selection table row, input immutability, dataset-order preservation,
ID intersection and unknown IDs checked before filtering, missing categories,
case sensitivity, repeated tags in legacy input, empty preview, invalid selector
arrays/unknown fields/boundary whitespace, allowed internally spaced selector
values, and descriptor hash changes independent of case hash.
Use unrelated opaque taxonomies in fixtures to demonstrate mechanism reuse.

Exit criterion: complete dataset validation precedes preview; all selection
results are deterministic and contain no target-specific branching.

### Milestone 3 — suites, execution, persistence snapshots

Implement Suite binding/profile resolution outside the runner. Add narrowly
scoped v2 runner options and immutable definition snapshots; enrich v2 runs
with the documented context. Keep legacy direct-run behavior and serialization.

Files: `core/suites.py` (new); `core/models.py::CaseDefinitionSnapshot/CaseResult`;
`core/runner.py::run`; `core/replay.py` for final v2 run-context verification;
`targets/base.py` for adapter contract documentation; `scorers/base.py` and
`rubric_judge.py` documentation only unless a concrete contract fix is needed;
`tests/test_suites.py` (new), `test_runner.py`, `test_store.py`, `test_replay.py`,
`test_calibration.py`, `test_callable_target.py`, `test_rubric_judge.py`, and
existing Sales Agent isolation tests. `core/store.py` needs no SQL changes.

Tests: ID/version binding mismatch; case-only pins and both pins; malformed or
swapped fingerprint types; case-content and descriptor-only drift; both supplied
pins independently checked before target calls; ambiguous old pin field rejected;
unsupported scheme, attempts including bool/fraction/zero, suite/profile/binding
identity whitespace rejection in JSON and Python, missing/mismatched profile,
explicit override precedence,
zero-selection execution rejection, capability mismatch before invocation,
uniform scorers, reference validation before calls, PASS/FAIL/ERROR/SKIP and
independent scorer preservation, failed/timeout attempts, repeated-attempt and
case isolation, safe metadata projection with nested secret sentinels, immutable
snapshots after source mutation, complete JSON/SQLite round-trip, duplicate run
ID rejection, default hash-only results containing no copied TestCase input/
reference payloads, explicit full payloads with canonical round-trip, unchanged
definition hashes across persistence policies, recorded policy/source/overrides,
invalid policy rejection and incompatible profile-policy override rejection,
classification/safe metadata present under both policies, hash-only replay with
verified external material versus missing/mismatched material preflight errors,
full-mode source dependencies, legacy document digests after CaseResult extension,
and replay/calibration rebuilds under both schemes. Prove no evaluator metadata reaches
recorded SUT requests, unchanged legacy judge prompt bytes, and exclusion
profiles' invariant prompt bytes under classification edits.

Exit criterion: offline suite execution and store/load work under both policies;
replay source preparation succeeds with sufficient verified material and reports
insufficiency before judge calls otherwise, without schema migration or
historical rewrites.

### Milestone 4 — grouped reports and comparison context

Add generic grouping records and comparison context while preserving existing
descriptive comparison APIs. Add a self-contained offline example that can
load a fixture descriptor/suite, preview, run deterministic fakes, persist to a
temporary path, group, and compare. The example is explicitly invoked and makes
no network calls on import or execution.

Files: `reporting/grouping.py` (new), `reporting/__init__.py` if exports are useful,
`regression/comparison.py`; `tests/test_grouping.py` (new),
`tests/test_comparison.py`; `examples/taxonomy_suites.py` (new) with synthetic
example data under `examples/data/taxonomy/`. Do not refactor calibration reports.

Tests: exclusive category/risk partitions, overlapping/non-additive tags,
untagged and unknown legacy classification, duplicate legacy tags counted once,
all verdict counts, null/no-quality-evidence behavior, scorer counts and errors,
no risk weighting, stable output order, inert authored labels, membership drift,
same ID with changed definition/reference, full versus subset drift, descriptor-
only edit, suite expression edit with same members, attempt/profile/judge changes,
scheme mismatch, missing legacy context, and compatible unchanged controls.
Test grouping and hash-level definition comparison under both payload policies,
explicitly unavailable input/reference diffs for hash-only artifacts, and a
policy-only change reported as artifact availability rather than regression.
Verify no report calls changed group membership a target regression. Test the
offline example and compatibility of existing Sales Agent comparison wrappers.

Exit criterion: a persisted run alone supplies reproducible grouping; comparisons
expose unknown/changed context without relying on today's dataset definitions.

### Milestone 5 — Sales Agent adoption preparation only

After Milestones 1–4 pass, document the future layout, without creating a dataset
that claims to contain 50 cases:

```text
datasets/salesagent/study-v1/dataset.json
datasets/salesagent/study-v1/cases.jsonl
datasets/salesagent/study-v1/suites/*.json
```

The future descriptor will declare a new identity/revision and v2 scheme.
The coverage matrix will own category/tags/risk vocabulary and selected suites.
Shopper input stays in `input`; assertions/semantic expectations in `reference`;
provenance in `extra` and dataset metadata. This is intended as a fresh
holdout-style study; whether any prior scenario or ID is deliberately reused
is deferred to coverage-matrix approval, not decided by this adoption plan.
The generic ID requirements are: IDs are stable within a dataset definition,
IDs are unique within that dataset, and cross-study reuse must be intentional
and semantically justified. The harness must never infer equivalence from
similar wording or ID resemblance; a shared ID alone also does not establish
cross-study comparability. Existing frozen loaders and their exact 14-case
rules remain untouched.

Document recipe contracts for profile factories, integration validators, safe
metadata allowlists, and evidence projection, using the generic suite API.
Do not wire the future study into a live entry point or invent its taxonomy,
coverage matrix, thresholds, rubric changes, or 50 case expectations. Future
adoption tests will prove HTTP isolation and generic suite use with mocks;
this milestone only specifies them until authoring is approved.

Files: update `datasets/salesagent/README.md` and add
`docs/salesagent-study-adoption.md` during approved implementation. No changes
to `baseline.jsonl`, `semantic.jsonl`, their hashes, or stored artifacts.

Exit criterion: documented migration/file contracts and explicit outstanding
coverage approval; the 50-case authoring task remains unstarted.

## Documentation and ADR work

During implementation, add `docs/adr/0006-versioned-case-definitions-and-suites.md`
covering taxonomy ownership, v1/v2 representations, descriptor versus subset
hashes, distinctly typed suite pins, suite/run scorer ownership, snapshot
isolation and explicit payload policies, and comparison/replay capability limits.
Add `docs/test-taxonomy-and-suites.md` with complete schemas, selector truth
table, whitespace rejection/direct v2 validation, safe metadata and payload
persistence policies, offline usage, profile/override behavior, migration,
and future latest-status scoping. Link it from README without rewriting unrelated
project documentation. Update `docs/judge-replay.md` and
`docs/human-judge-calibration.md` only for version-aware source verification and
unchanged legacy binding guarantees. Document retained Target/judge debts.

Keep all current ADR conclusions about ERROR versus FAIL, critical assertions,
normalized evidence, replay, and human calibration. New classification neither
supersedes nor silently modifies those contracts.

## Validation commands and manual acceptance

Run commands from the repository root using the existing environment; do not
install dependencies or invoke paid/network services merely to execute this
plan. The commands below are future implementation checks, not tests already
run during planning. `tests/conftest.py` blocks socket/DNS access.

After Milestone 1:

```sh
.venv/bin/python -m pytest tests/test_case_fingerprints.py tests/test_dataset.py tests/test_models.py tests/test_replay.py tests/test_calibration.py tests/test_calibration_io.py
```

After Milestone 2:

```sh
.venv/bin/python -m pytest tests/test_dataset_descriptor.py tests/test_selection.py tests/test_dataset.py tests/test_case_fingerprints.py
```

After Milestone 3:

```sh
.venv/bin/python -m pytest tests/test_suites.py tests/test_runner.py tests/test_store.py tests/test_replay.py tests/test_calibration.py tests/test_callable_target.py tests/test_rubric_judge.py tests/test_salesagent_target.py tests/test_salesagent_baseline.py tests/test_salesagent_semantic.py
```

After Milestone 4 and before declaring generic completion:

```sh
.venv/bin/python -m pytest
.venv/bin/ruff check src tests examples
.venv/bin/mypy src
git diff --check
```

Record failures that predate the slice rather than silently refactoring unrelated
code. All new/changed behavior and relevant compatibility tests must pass.

Manual offline acceptance sequence:

1. Record current dataset byte/case hashes and private artifact byte hashes;
   confirm frozen dataset constants above before making implementation changes.
2. Load the new synthetic descriptor and inspect preserved nested `extra`.
   Run all selector examples and compare exact ordered IDs with this document.
   Check leading/trailing whitespace rejection in each v2 identity/taxonomy
   location, internal-whitespace acceptance, direct Python new-field validation,
   v2-boundary checks for existing fields, and unchanged legacy acceptance.
3. Preview a suite matching no cases and an unknown-ID suite. Confirm empty
   preview succeeds, unknown ID fails, and neither constructs/calls clients.
4. Verify a case-content pin and both case/descriptor pins, then independently
   change descriptor metadata and case content to prove each supplied pin is
   checked before calls. Execute a nonempty suite with deterministic fake
   targets/scorers and two attempts under default `hashes_only`, then explicit
   `full`. Inspect effective policy/source/overrides, profile, all three distinct
   fingerprints, and classification/safe metadata snapshots; store/load in a
   new temporary SQLite database. Confirm input/reference snapshots are absent
   under hash-only and canonical under full, with identical definition hashes.
5. Modify only the in-memory source classification after execution. Confirm
   saved results and grouping remain unchanged; a newly loaded revised dataset
   changes its v2 definition fingerprint.
6. Run the reporting example with PASS/FAIL/ERROR/SKIP evidence. Verify separate
   counts, null evidence behavior, and non-additive tag groups.
7. Compare unchanged runs, changed references, changed suite membership,
   descriptor-only changes, missing legacy metadata, and policy-only changes.
   Check context flags, hash-only detail limits, and report language rather
   than only numeric deltas; grouping works without complete case payloads.
8. Reload/rebuild synthetic legacy replay and calibration fixtures with a fake
   judge that raises if called. Verify exact original bindings. If local
   historical artifacts are present, use read-only SQLite/model loaders to
   verify existing replay and calibration bindings as additional acceptance;
   do not execute collection, judge scoring, report export, or artifact writes.
   Check v2 hash-only replay preparation with verified external cases and
   rejection when those cases are missing/mismatched, plus full-mode source
   requirements, using a judge that raises if called throughout preparation.
9. Recheck dataset/artifact byte hashes, inspect the final diff, and verify no
   frozen datasets or historical artifacts changed. Run the full offline suite
   and applicable static checks; record actual commands and outcomes here.

The normal tests must not depend on private local artifacts or a running
application. Historical validation uses existing evidence only and must not
turn missing files into an invitation to rerun a target or judge.

## Failure, rollback, and implementation review rules

Fingerprint/binding mismatch blocks the milestone. Diagnose payload, scheme,
or serialization differences; never rewrite expected constants or backfill
new metadata into old documents. Reject unrecognized schemes and contradictory
snapshots before paid execution. Reject missing/invalid v2 payload policies,
policy-inconsistent payload storage, profile-policy conflicts, or either stale
suite fingerprint pin before target calls. Insufficient verified source material
for replay is a preflight error, not a quality failure or an invitation to
reconstruct missing inputs from current expectations. Keep detailed safe
diagnostics without dumping private case bodies or credentials.

Unsupported v2 artifacts remain distinct from v1. Old releases may ignore new
model fields and cannot reliably replay v2 data; backward compatibility means
new code reads/verifies old artifacts, not that old code understands new ones.
Before rollout, document the minimum reader version for v2 results. Downgrades
must use the retained legacy datasets/recipes and must not relabel v2 artifacts.

No database migration is planned, so rollback does not require SQL restoration.
New immutable runs can remain stored; older tooling must not resave them after
discarding unknown data. Keep original artifact files intact. Revert only this
feature's changes through reviewed normal commits if rollback is required;
no reset/rebase/force-push is authorized. Do not delete results as cleanup.

Runtime target/scorer errors retain ordinary ERROR semantics. Snapshot/config
serialization is validated before target calls so avoidable persistence-shape
errors do not waste execution. If SQLite save fails, surface that failure and
retain the complete in-memory result for explicit retry under its original run
ID; do not claim it was saved or silently rerun the target.

Stop and explain a material conflict with these contracts or AGENTS.md before
implementing a different architecture. Routine choices within the stated
boundaries belong in this plan's decision log, not additional approval loops.
The coverage-matrix approval requirement is explicit user scope, independent
of implementation approval for generic Milestones 1–4.

## Planning validation and decision log

2026-10-02: Rechecked a clean `feat/test-taxonomy-suites` branch and current
source boundaries. Confirmed frozen baseline/semantic byte and case hashes with
a read-only Python probe; measured three existing artifact files without
loading provider clients. No test suite, target, judge, migration, or code
implementation was run. Added this ExecPlan only.

Proposed implementation details selected here for review: one optional nested
CaseResult definition snapshot to minimize legacy serialization surface;
explicit v1/v2 case representations with no automatic scheme guessing; strict
descriptor authoring independent of legacy loading; metadata allowlists owned
by recipe/profile configuration; unchanged legacy judge evidence; and context
checks that preserve existing descriptive comparison APIs.

Record implementation outcomes, test counts, deviations, and any revised
decisions below as work is approved and completed.

2026-10-03: ExecPlan approved subject to four amendments, incorporated in this
document-only revision. V2 identity/taxonomy boundary whitespace is rejected
without normalization, with new-field model validators and shared v2 entry
validation while legacy fields/loaders stay compatible. Suite bindings use
`expected_case_fingerprint` and optional `expected_descriptor_fingerprint`,
checked independently. V2 runs record `case_payload_snapshot`, defaulting to
`hashes_only`; `full` is explicit, classification/hash/safe metadata context is
mandatory in both modes, and replay/detail capabilities reflect source
availability. Frozen legacy resolved-case representations remain unchanged.
Milestone 5 defers all cross-study scenario/ID reuse to holdout coverage-matrix
approval. Updated examples, tests, acceptance, documentation, and failure
semantics accordingly. No implementation, dataset edits, or target/judge calls
are authorized by this revision request or performed during it.

## Milestone 1 implementation and validation record (2026-10-03)

Implemented only the fingerprint/classification foundation after the user's
explicit Milestone 1 authorization. Re-read AGENTS.md and this amended plan.
The branch remained `feat/test-taxonomy-suites`, HEAD remained
`9198ad26d84576a319537909f146c5121412be99`, and `git diff` against that revision
was empty before implementation. The sole untracked file was this approved
plan; no relevant repository code had changed since planning. No commits,
merges, or history-changing operations were performed.

### Fixture-first sequence and changes

1. Ran the existing focused compatibility suite before model edits: 211 passed.
2. Generated `tests/fixtures/taxonomy/legacy-v1.json` with the unchanged models.
   Its SHA-256 is
   `5818ce99cec46d4ec82095b7a6e9eb11685a8537248cff8eae2419e95dd49e4b`.
   The fixture pins original compact model JSON, parsed documents, dataset and
   case hashes, replay preparation/result, synthetic annotation/frozen set,
   calibration identity/binding, and historical/replay observation joins.
   Fixed timestamps/IDs and a raising judge callable ensure no live or fake
   inference is needed to capture these artifacts. All labels are synthetic.
3. Added legacy fixture and frozen dataset protection tests and ran them before
   production edits: 2 passed. Neither expected hashes nor fixture bytes were
   subsequently changed.
4. Added explicit `case_payload`, `hash_case_definition`,
   `resolved_case_payload`, scheme validation and a shared `validate_v2_case`
   boundary in `core/case_fingerprints.py`. Extended `hash_cases` with an
   explicit keyword scheme while preserving its v1 default/algorithm.
5. Added optional TestCase title/description/category/risk, strict new-field
   validation, and field-local `exclude_if` serialization rules. This uses
   Pydantic's built-in per-field serialization facility rather than a custom
   model serializer; it preserves nested/include/exclude behavior while
   omitting only newly added nulls. No existing-field validators changed.
6. Made replay's case hashes and resolved payload verification scheme-aware;
   added an optional source scheme emitted for v2 and omitted for legacy
   sources. V2 source preparation verifies explicit full/hash-only payload
   policy and required full hash/selection against externally supplied cases.
   It detects classification tampering and evidence-builder mutations without
   changing the legacy prompt/evidence or calibration algorithms.
7. Added ADR 0006 with exact representations, compatibility rules and the
   remaining milestone boundaries. No runner, target protocol, scorer/judge
   behavior, calibration/store implementation, descriptor, selector, suite,
   reporting, dataset, or UI implementation was changed.

### Implemented behavior and compatibility results

V1 remains SHA-256 over sorted compact five-field JSON rows with default ASCII
escaping and trailing newlines. Existing default nulls and empty containers
remain present. JSON-mode Pydantic serialization maps non-finite floats to null
under the installed version, just as before; this was checked directly against
the pre-change model at HEAD after a new test's initial NaN assumption proved
incorrect. The new test expectation was corrected to that observed behavior;
no pinned legacy hash or artifact was modified.

V1 rejects every populated new field, including empty prose descriptions. V2
explicitly includes all nine fields and four null defaults and hashes the
approved scheme envelope; single-case hashes use the separate case envelope.
V2 rejects non-finite/non-JSON Python values before serialization, revalidates
mutated/constructed cases, rejects ID/tag boundary whitespace and duplicate
tags, and preserves legitimate internal whitespace. New category/risk field
validators also reject boundary whitespace on direct construction. Description
prose remains unchanged; title must be a strict nonblank string.

Both frozen dataset byte SHA-256 and legacy case hashes remain exactly the
values in the protection table. All pinned run/replay/calibration model JSON,
document hashes, source/case identities, prompt/evidence and human binding
values match the pre-change fixture. V2 calibration identity binds changed
classification even when the reviewed judge projection produces the same prompt.

Additional local acceptance was read-only: rebuilt both stored replay inputs
from their original source/configuration and validated all 18 calibration
examples/source joins against the saved analysis. All 22 inventoried JSON,
JSONL, SQLite, and Markdown artifact/dataset files retained their byte hashes.
These local files are not test dependencies or committed fixtures.

### Validation commands and outcomes

Final required Milestone 1 command:

```sh
.venv/bin/python -m pytest tests/test_case_fingerprints.py tests/test_dataset.py tests/test_models.py tests/test_replay.py tests/test_calibration.py tests/test_calibration_io.py
```

Result: **365 passed**. Includes 109 new fingerprint/fixture/serialization tests
and 45 additional replay cases (the pre-change focused set had 211 tests).

Additional checks after the final code changes:

```sh
.venv/bin/python -m pytest
.venv/bin/ruff check src tests examples
.venv/bin/mypy src
git diff --check
```

Results: **756 passed** in the full offline suite; Ruff passed; mypy passed for
29 source files; diff whitespace check passed. The full suite was justified by
shared TestCase/replay serialization changes and covers existing runner,
adapter, rubric, study recipe, store, and calibration-reporting behavior.
No live credentials, target, judge, network, or private artifact dependency was
used by pytest. Intermediate failures were confined to new tests: the NaN
assumption above and a missing required duration in a synthetic replay attempt;
both test setups were corrected before the final successful commands.

The read-only historical probe used `prepare_source`/`load_selected` with the
existing raising judge callable and read-only SQLite stores. It rebuilt
preparation and observation bindings only, not judge execution or report export.

### Scope decisions, remaining risks, and stop point

No material architecture deviation. Built-in field-local serialization provides
the planned narrow omission rule. For Milestone 1, v2 replay preparation tests
use explicitly constructed synthetic source documents; full or hash-only
payload availability is verified without introducing run persistence policy
selection. Execution-time CaseResult definition snapshots and their additional
verification remain Milestone 3, as does descriptor/suite context. This is
foundation verification, not a claim that a v2 suite runner now exists.

The ordinary runner remains a legacy v1 caller until Milestone 3. Do not pass
populated new fields to it for execution: its existing dataset hash computation
occurs after target calls and will reject them. Explicit v2 fingerprint APIs
are available now; v2 runner preflight/options are deliberately deferred to
avoid beginning another milestone. The Target protocol and legacy rubric tags
behavior remain unchanged architectural debts. Hash-only replay still requires
verified external case material; no input/reference is reconstructed from hashes.

At Milestone 1 completion, work stopped pending explicit Milestone 2 approval.
The subsequent authorization and implementation are recorded below.

## Milestone 2 implementation and validation record (2026-10-03)

Implemented only descriptor loading, strict authoring validation, deterministic
selection and definition-only preview after explicit user authorization.
Re-read AGENTS.md and this amended plan. Confirmed Milestone 1 was committed as
`a3d9d96719d87be8b6ca30bcd387e61f8bc5aa67` on `feat/test-taxonomy-suites`, with
no subsequent commits or worktree changes before implementation. The pre-change
dataset/fingerprint checks passed (116 tests). No commits, merges or history
changes were performed during Milestone 2.

### Implemented APIs and decisions

- `DatasetDescriptor` requires `schema_version="dataset-descriptor-v1"`, `id`,
  authored `version`, relative `cases`, and `fingerprint_scheme="dataset-cases-v2"`.
  Optional title/description default to null; `extra` defaults to an empty object.
  Its `descriptor_hash` property fingerprints the normalized authored dictionary,
  including the schema marker and defaults, never derived hashes or absolute paths.
- `LoadedDataset` contains the descriptor, ordered ordinary TestCases, resolved
  `descriptor_path`/`cases_path`, `full_dataset_hash` and `descriptor_hash`.
  It validates both hashes on construction and JSON round-trip. Complete source
  validation precedes selection, including rows that filters would exclude.
- `load_dataset()` strictly parses descriptor JSON and every nonblank JSONL row.
  It rejects unknown fields, duplicate JSON keys, non-finite numbers including
  overflow, type coercions, invalid identity whitespace, duplicate/blank tags,
  duplicate IDs, and non-JSON metadata. Duplicate IDs report both source lines;
  diagnostics do not echo whole inputs. Prose and legitimate internal whitespace
  retain their values. Case-file binding is relative to the descriptor directory;
  URLs, absolute/Windows paths, backslashes, parent traversal and symlink escapes
  are rejected. New JSONL parsing uses physical newline boundaries so literal
  Unicode line-separator characters inside strings remain valid data.
- `CaseSelection` has optional `case_ids`, `categories`, `tags_any`, `tags_all`,
  and `risks` arrays. Omitted fields impose no constraint; supplied null/empty,
  duplicate, non-string, blank or boundary-whitespace values are errors.
  `select_cases()` implements the approved truth table without mutations: AND
  across fields, OR within IDs/categories/risks, any/all tags, exact comparison,
  original dataset order, and unknown explicit IDs rejected before filtering.
- `preview_selection()` returns serializable `SelectionPreview` identity,
  descriptor/full/selected fingerprints and scheme names, authored selection,
  ordered IDs, counts, `executable` and a reason for empty membership. It carries
  no case payload bodies. Empty selection is valid with `executable=false`;
  nonempty membership is not target/scorer preflight or execution authorization.
- Nested loaded case/metadata objects remain mutable. Preview revalidates all
  content and both fingerprints, including unselected cases, to reject drift.
  Pure `select_cases()` accepts already validated sequences, as designed.
  Preview copies selector data; later selector-list edits do not alter its result.
- Reused the existing finite JSON validator through `validate_json_data()`;
  neither fingerprint algorithm changed. The source of legacy `load_cases()`
  and `hash_cases()` is exactly unchanged from Milestone 1. No runner, replay,
  calibration, target, scorer or result model implementation changed.
- Added synthetic descriptor/JSONL fixtures, authoring/selection tests, the
  current-feature guide and README link, and updated ADR 0006. No application
  vocabulary or category-to-scorer mapping was introduced.

Example preview for `categories=["family-a"]`, `tags_any=["quick"]` against
`tests/fixtures/taxonomy/organization/dataset.json`:

```json
{
  "dataset_id": "example-evaluation",
  "dataset_version": "study-v1",
  "descriptor_hash": "6cc4abcb061c3211ead78a5f5006afc0d61846fdd23b070b84fd934ab788ff92",
  "descriptor_fingerprint_scheme": "dataset-descriptor-v1",
  "full_dataset_hash": "878d6f8fb3fb350c3c533380bdc632190e2f9221c50806fa6628c97494712b84",
  "selected_dataset_hash": "193d0f8e4bb54700c4f371fc147d489575703dc2a236a20c4600ab8e871e57ad",
  "case_fingerprint_scheme": "dataset-cases-v2",
  "selection": {"categories": ["family-a"], "tags_any": ["quick"]},
  "case_ids": ["case-a"],
  "total_case_count": 3,
  "selected_case_count": 1,
  "executable": true,
  "reason": null
}
```

### Validation and compatibility results

Required Milestone 2 command:

```sh
.venv/bin/python -m pytest tests/test_dataset_descriptor.py tests/test_selection.py tests/test_dataset.py tests/test_case_fingerprints.py
```

Result: **300 passed** (100 descriptor tests, 84 selector/preview tests, 116
existing dataset/fingerprint tests). Includes all selection examples, invalid
unselected rows, mutation checks, Unicode values, unrelated opaque taxonomies,
round-tripping, relative bindings, and an isolated import/preview check proving
execution modules are not imported or constructed.

Additional focused offline compatibility and static checks:

```sh
.venv/bin/python -m pytest tests/test_replay.py tests/test_calibration.py tests/test_calibration_io.py tests/test_models.py
.venv/bin/ruff check src tests examples
.venv/bin/mypy src
git diff --check
```

Results: **249 passed**; Ruff passed; mypy passed for **30 source files**;
diff whitespace check passed. All 549 tests across the two final pytest groups
passed. No full-suite rerun was needed for this isolated authoring/selection
slice after these checks. No live target, judge or network calls were made.

Read-only acceptance rechecked all **23** inventoried existing artifact, dataset
and legacy fixture files: byte hashes unchanged. Both frozen dataset byte hashes
and v1 case hashes still exactly match the protection table. The pinned synthetic
legacy fixture retains SHA-256
`5818ce99cec46d4ec82095b7a6e9eb11685a8537248cff8eae2419e95dd49e4b`.
No historical artifact or human binding was rewritten.

### Deviations, limitations and stop point

No material deviation from the approved plan. Symlink containment/backslash
rejection make the specified portable relative case binding explicit; neither
changes the legacy loader. Descriptor fingerprints use the existing canonical
fingerprint primitive over normalized fields with `schema_version` as the
representation marker. These routine details are documented in ADR 0006.

The current runner still supports v1 only; v2 execution and persistence remain
Milestone 3. These previews concern membership only, do not validate profile
references/capabilities, and do not persist full input/reference payloads or run
results. Full snapshot policies and suite fingerprint pins remain future work.

At Milestone 2 completion, work stopped pending explicit Milestone 3 approval.
The subsequent authorization and implementation are recorded below. Milestone 2
itself introduced no suites, runner v2 options or persistence snapshots.

## Milestone 3 implementation and validation record (2026-10-03)

Implemented only suite execution and persistence snapshots after explicit user
authorization in the attached request. Re-read AGENTS.md and this amended plan.
Milestone 2 was committed as `3352ea57849865bd2d87f0e318bb5f6ff9b80086` on
`feat/test-taxonomy-suites`; the worktree was clean with no subsequent repository
changes. The commit's 11-file diff matches the approved Milestone 2 record.
Pre-change fingerprint/descriptor/selection checks passed: 293 tests. Inventoried
23 existing artifact/dataset/legacy-fixture files before edits. No commits,
merges, staging or history-changing operations were performed during this work.

### Implemented APIs and execution boundary

- Added strict `Suite` and `DatasetBinding` in `core/suites.py`, with local JSON
  loading through `resolve_suite(path)`. Schema, IDs, attempt types, selection,
  relative descriptor paths and both independently named fingerprint pins are
  validated before execution. Suite paths allow relative parents; descriptor case
  bindings retain Milestone 2's stricter containment. No TestCases are embedded.
- `ResolvedSuite` contains Suite, LoadedDataset, SelectionPreview, source path
  and normalized suite hash. Resolution does not construct targets/scorers/judges.
  Execution revalidates in-memory definitions, membership, hashes and bindings;
  it does not silently switch to revised disk data after resolution.
- `execute_suite(resolved, target, scorers, *, profile, ...)` accepts explicit
  uniform scorers and a trusted `EvaluationProfile`. The small strict profile
  model records ID, taxonomy evidence contract, explicit scorer/judge settings,
  safe parameters, optional named reference contract, payload policy and safe
  metadata allowlists. It is not a file-driven executable registry. Missing
  custom configuration is recorded as unknown; authored settings are checked
  against public observable scorer values. Judge settings reuse the existing
  `JudgeConfiguration` model, without client/environment introspection.
- Supported run overrides are attempts, explicit profile ID replacement and
  payload policy. Authored defaults, requested overrides and effective values
  remain separate. No profile or scorer is inferred for a profile-less suite.
- Reference-dependent integrations supply a versioned `reference_contract` and
  pure `validate_reference(TestCase)` callback together. Every selected case is
  checked before execution. Reference-free profiles need neither. Invalid
  contracts/mutations, empty selection, binding errors, duplicate scorers,
  missing capabilities and invalid snapshot configuration all fail before calls.
- Runner extensions are `fingerprint_scheme`, `case_extra_keys` and
  `case_payload_snapshot`. Selection stays outside `run()`. V1 remains the
  default with its historical result shape. Hashes are now computed before
  calls, including rejecting populated new fields under v1 before execution.
  V2 freezes definitions/configuration and isolates case/response copies per
  attempt and scorer. Runtime errors retain ERROR semantics and independent
  successful scores survive other scorer failures.

### Snapshot, metadata and replay contracts

Added `CaseDefinitionSnapshot` and optional `CaseResult.definition`. The new
field uses the existing narrow `exclude_if` technique: absent legacy definitions
remain omitted, including nested RunResult JSON, preserving pinned document
hashes. Snapshots contain schema/scheme, full definition hash, title, description,
category, risk and projected extra. Tags remain only on CaseResult. Verdicts
remain on attempts. Shared `core/snapshots.py` helpers keep runner/replay
projection rules identical without changing case fingerprint algorithms.

Generic v2 payload policy is `hashes_only`; `full` is explicit. Both preserve
classification/hashes and safe metadata. Only full mode writes selected canonical
`resolved_cases` with input/reference and no extra. Definition/dataset hashes do
not depend on persistence policy. A full-required profile rejects hashes-only;
policy source and explicit overrides are recorded. Capability fields identify
payload availability and whether complete external source cases are required.

Case/dataset metadata allowlists default to empty. Each accepts at most 128 unique
nonempty top-level keys; entire nested values must be finite JSON and reviewed
by the integration as safe. No key name implies safety. Profile safe parameters
and explicitly authored scorer configuration carry the same caller obligation;
structural JSON validation is not secret detection. Tests use nested secret
sentinels to prove unallowlisted data stays absent. Descriptor completeness is
recorded separately from the hash of the full authored descriptor.

All snapshots, hashes, tags and suite/profile context are deep-copied before the
first target call. Tests mutate original cases, selectors and nested profile
configuration during/after execution and verify recorded history stays fixed.
The suite wrapper attaches already-frozen context to an explicitly v2 runner
result; it never relabels a v1 execution. Existing SQLite JSON persistence is
unchanged. Tests cover JSON/store reloads and duplicate run IDs. Saving remains
explicit, so callers retain the result for retry after a persistence failure.

Replay now verifies required v2 definition snapshots, safe metadata policy,
suite selection/pins and recorded evaluator context. Missing legacy scheme still
means v1. Recorded suite judge configuration can provide the source evaluator;
missing configuration remains unknown under existing replay rules. A new pure
`reconstruct_source_cases()` helper succeeds only if full payloads plus projected
metadata reproduce the entire source hashes. Hashes-only, selected subsets or
omitted authored metadata require verified external source cases. Reconstruction
returns detached cases, so editing them cannot rewrite the saved artifact.
Projected descriptor metadata cannot independently reproduce a full descriptor
hash; the completeness flag makes that limitation explicit.

M1's in-test synthetic v2 source builders now include the required definitions
and metadata policy. Tests authoring a revised synthetic definition also update
its new snapshot. No legacy fixture, expected legacy hash, human binding or
historical artifact was regenerated. Legacy rubric prompt/evidence behavior is
unchanged. New exclusion profiles require named reviewed evidence projections;
tests prove title/description/category/tags/risk/extra changes leave prepared
prompt/evidence bytes unchanged. Default rubric evidence cannot claim exclusion.

### Isolation, validation and compatibility results

Recording callable and mocked HTTP tests prove changes to IDs, references,
classification and extra leave intended SUT request bytes identical. HTTP
sessions remain isolated between repeated attempts and cases. Target protocol
and scorer/judge behavior were not redesigned; production adapter/scorer edits
are documentation only. No live targets, judges, credentials or network calls
were used. No grouped reporting/comparison implementation was added.

Final required Milestone 3 command:

```sh
.venv/bin/python -m pytest tests/test_suites.py tests/test_runner.py tests/test_store.py tests/test_replay.py tests/test_calibration.py tests/test_callable_target.py tests/test_rubric_judge.py tests/test_salesagent_target.py tests/test_salesagent_baseline.py tests/test_salesagent_semantic.py
```

Result: **550 passed**, including 90 new suite/execution/snapshot tests and 16
additional callable/HTTP isolation cases. Existing tests cover legacy runtime,
store, judge prompt, replay, calibration and study-recipe behavior.

Additional final checks:

```sh
.venv/bin/python -m pytest
.venv/bin/ruff check src tests examples
.venv/bin/mypy src
git diff --check
```

Results: **1,046 passed**; Ruff passed; mypy passed for **32 source files**;
diff whitespace check passed. Full-suite validation is justified by runner,
CaseResult serialization and replay-boundary changes; it includes every M1/M2
fingerprint/loader/selector test, calibration identity/binding tests and pinned
legacy fixtures. Final checks followed the reconstructed-case aliasing fix.

Intermediate failures were new/synthetic fixture setup issues: M1 v2 synthetic
sources needed their now-required snapshots, a supposedly mismatched relative
path actually resolved to the same descriptor, and a new calibration fixture
omitted required evidence settings. These setups were corrected without changing
legacy expected values or weakening validation. No failures remain.

Read-only local acceptance loaded **16 historical runs** and checked model-dump
fingerprints against original stored document fingerprints; **two saved replays**
reloaded/round-tripped successfully. All **23** inventoried files retained their
byte hashes. Frozen baseline/semantic byte and v1 content hashes remain exactly
the protection-table values. The synthetic legacy fixture retains SHA-256
`5818ce99cec46d4ec82095b7a6e9eb11685a8537248cff8eae2419e95dd49e4b`.
Local artifacts are not test dependencies and were never written.

### Decisions, limitations and stop point

No material deviation from the approved architecture. Routine API decisions are
the strict Python `EvaluationProfile`, small shared snapshot helper, 128-key
allowlist bound, explicit reference validator hook, and conservative verified
full-source reconstruction. These are documented in the authoring guide and
ADR 0006. The new reader requirement is support for `run-organization-v1` and
`case-definition-snapshot-v1`; the unreleased package version alone does not
identify milestone support. Older readers must not resave v2 artifacts.

Trusted integration code still owns confidentiality review of exported subtrees,
complete custom-scorer configuration, reference semantics, projection invariance
and target session isolation. JSON compatibility cannot prove any of these.
Hashes-only does not redact target response evidence; full mode does not promise
self-contained replay. Existing comparison APIs have not gained context awareness
and grouped reporting remains unimplemented, as required by this milestone.

**Milestone 3 is complete. Stop before Milestone 4 until explicitly approved.**
No grouping, comparison-context changes, 50-case study authoring, UI, latest-status
service, target protocol redesign, plugin registry or per-case scorer dispatch
was implemented. No outstanding Milestone 3 work remains.
