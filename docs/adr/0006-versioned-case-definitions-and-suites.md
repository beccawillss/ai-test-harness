# ADR 0006: Versioned case definitions and taxonomy boundaries

Status: accepted for the taxonomy ExecPlan; fingerprint/classification foundation
implemented in Milestone 1 (2026-10-03). Descriptor loading and pure selection/
preview are implemented in Milestone 2. Suite execution and definition snapshots
are implemented in Milestone 3. Grouped reporting/comparison context remain
future milestones, not shipped features. See
[the ExecPlan](../plans/test-taxonomy-datasets-suites.md).

## Context

Dataset hashes previously depended on the current TestCase model dump. Adding
fields would change historical dataset hashes, replay case identities, resolved
case verification, and human-calibration bindings without changing dataset files.
Replay and calibration also hash nested serialized documents, so compatibility
must cover their exact serialized representation, not just the dataset digest.

## Decision

The harness owns taxonomy mechanisms; datasets and integrations own opaque
values. TestCase retains `id`, `input`, `reference`, `tags`, and `extra` and adds
optional `title`, `description`, `category`, and `risk`. `extra` remains the
arbitrary case metadata dictionary. Risk does not select scorers or change
verdicts, thresholds, weighting, or critical gates. Verdicts remain results.

Use explicit canonical representations through `core/case_fingerprints.py`:

| Scheme | Ordered dataset hash | Single-case definition hash |
| --- | --- | --- |
| `dataset-cases-v1` | SHA-256 of five-field JSON rows, sorted keys, compact separators, default ASCII escaping, UTF-8, newline after every row | Existing `fingerprint(five_field_payload)` |
| `dataset-cases-v2` | `fingerprint({"scheme":"dataset-cases-v2","cases":[payload,...]})` | `fingerprint({"scheme":"dataset-cases-v2","case":payload})` |

V1 fields are exactly `id`, `input`, `reference`, `tags`, `extra`, including
legacy defaults and nulls. Preserve the existing JSON-mode model serialization
before encoding: under the supported Pydantic version this maps non-finite
floats in JSON-mode dumps to null. Do not change this legacy behavior to match
v2 validation. A populated new field, including an empty description, is an
error under v1 rather than omitted evidence. `hash_cases()` defaults to v1;
unknown schemes fail, even for an empty dataset. No automatic scheme inference.

V2 payloads contain all nine fields, including four explicit null defaults.
Canonical JSON uses sorted keys, compact separators, unescaped Unicode, UTF-8,
and rejects non-finite values. List/tag/case order and all authored metadata
participate; dictionary order and formatting do not. Single-case and dataset
digests are different concepts, including for a one-case dataset.

Before v2 serialization, validate Python values as finite JSON data, rejecting
cycles, non-string object keys, sets, tuples, bytes, datetimes and other values
that model serialization might otherwise normalize. Revalidate mutated and
constructed instances. V2 IDs and tags must be nonblank and free of boundary
whitespace; tags are unique. Internal whitespace is preserved. No silent trim,
case conversion, sort, or deduplication occurs. Existing legacy ID/tag model and
loader semantics are unchanged.

New-field validators apply to direct TestCase construction: non-null title is
a strict nonblank string, category/risk are strict nonblank strings without
boundary whitespace, description is optional strict prose, including empty or
whitespace text. V2 boundary validation rechecks these after mutation. New null
fields use narrowly scoped Pydantic `Field(exclude_if=...)` serialization rules;
all existing fields retain their defaults and nulls. The explicit v2 canonical
builder restores its four null fields. Do not use global `exclude_none=True`.

## Replay and historical artifacts

Missing run-context scheme means v1. Replay hashes and resolved-case checks use
the explicit scheme. SourceProvenance records v2; its newly added optional
scheme field is omitted when absent, including nested model/JSON serialization.
Do not inject new fields into existing replay/calibration documents.

Milestone 1 supports externally supplied synthetic v2 source documents at the
replay boundary. Such documents require an explicit `case_payload_snapshot`
policy, selected case IDs and full dataset hash. `full` requires canonical
resolved cases excluding `extra`; `hashes_only` prohibits these payloads. Both
require externally supplied cases whose selected/full hashes verify. Exact
case identity includes taxonomy even when a judge projection excludes it.
Independent full-model mutation checks prevent builders from changing new
fields under a legacy hash, and v2 values are revalidated after preparation.

Milestone 3 extends this foundation to actual v2 runs: required CaseResult
classification snapshots and metadata policies verify against supplied source
cases. The runner now supports explicit v2 execution and freezes hashes before
calls, including rejecting populated new fields under v1 before execution.
Missing legacy definition fields remain omitted, preserving historical hashes.
Synthetic M1 v2 test builders now include the required snapshot context; pinned
legacy fixtures and expected hashes are unchanged.

Never rewrite frozen files, historical documents, expected hashes, replay
identities, or human bindings. Synthetic compatibility fixtures were generated
before model edits; tests pin their bytes, compact JSON, hashes, prompt/evidence,
observation joins, and calibration bindings. Local historical artifacts provide
additional read-only acceptance, not private CI dependencies.

## Descriptor loading and selection (Milestone 2)

`DatasetDescriptor` declares the required schema/version, stable ID, authored
version, relative case binding and v2 fingerprint scheme, with optional title,
description and arbitrary finite JSON `extra`. Its fingerprint is the canonical
hash of normalized authored fields, including its schema marker and explicit
defaults; absolute filesystem paths and derived hashes do not participate.
`LoadedDataset` retains both descriptor and full ordered case fingerprints.
The new strict loader is separate from the unchanged legacy `load_cases()`.

Strict loading rejects duplicate JSON keys/non-finite numbers, unknown fields,
duplicate case IDs, coercions and invalid identity whitespace. It validates all
rows before returning source material for selection. Binding checks disallow
URLs/absolute paths/parent traversal and resolved symlink escapes; nested local
files work independently of cwd. Errors identify source locations without
copying whole case bodies.

`CaseSelection` implements exact deterministic intersections with original
dataset order and explicit any/all tag matching. `preview_selection()` rechecks
the entire in-memory dataset and its fingerprints, then returns only identity,
hashes, selection, ordered IDs, counts and membership eligibility. Neither path
imports or constructs targets, scorers, judges or the runner. See the
[authoring guide](../test-taxonomy-and-suites.md) for examples and exact semantics.

## Suite execution and snapshots (Milestone 3)

`Suite` strictly binds one descriptor-aware dataset and selector, an attempt
count and an optional logical profile. Optional case and descriptor fingerprint
pins are checked separately before execution. `resolve_suite()` validates all
source material without constructing execution clients. `execute_suite()` takes
explicit uniform scorers, target and trusted `EvaluationProfile` configuration;
it rechecks bindings/membership and invokes integration reference validators for
all selected cases before calling the runner. No dynamic scorer dispatch exists.

`EvaluationProfile` records safe authored configuration and the taxonomy evidence
contract. Missing custom settings remain unknown. Explicit `JudgeConfiguration`
is reused rather than inspecting provider clients. Supported overrides are
attempts, profile ID and payload policy. Full-required profiles reject hashes-only
execution. Reviewed evidence projection contracts do not change legacy prompts.

V2 `CaseResult.definition` is a deep execution-time copy of classification,
definition hash, scheme and projected metadata. Existing `CaseResult.tags` remains
the sole copied tag list. The field is absent from legacy serialization when null.
Case/response copies isolate v2 attempts and independent scorers; target session
isolation remains an adapter responsibility. Shared `core/snapshots.py` helpers
keep execution/replay projection rules identical without changing fingerprints.

The runner stays selection-neutral and defaults to v1. New v2 options are an
explicit scheme, metadata-key allowlist and payload policy. It records subset
hashes before execution; suite context is also copied before calls. The suite
wrapper attaches that frozen context to the v2 result, never relabelling a v1 run.
Existing JSON persistence needs no SQL changes.

Hashes-only is the generic default: no input/reference copies in run context.
Full persistence records canonical resolved cases excluding extra. Both modes
record definitions and explicit safe metadata projection. Allowlists are limited
to 128 unique nonempty top-level keys per case/dataset; their complete subtrees
must be reviewed by integrations. Descriptor completeness is explicit, and its
hash always binds full authored metadata.

Replay checks snapshots, scheme/policy, suite membership/pins and recorded
evaluator context. Full reconstruction is allowed only if persisted payloads and
projected metadata reproduce the complete source hashes; selected subsets or
missing metadata require verified external source cases. Hashes-only cannot
reconstruct missing inputs. A projected descriptor does not independently
reproduce its full authored descriptor hash; its completeness flag preserves
that limit. Artifact capabilities expose payload and external-case requirements.

Minimum readers for these artifacts must support `run-organization-v1` and
`case-definition-snapshot-v1` (Milestone 3), beyond M1's case-fingerprint support.
Package version 0.1.0 alone does not distinguish this unreleased milestone.

## Subsequent milestones and limits

Descriptors distinguish authored version, descriptor fingerprint, full case
fingerprint, and selected subset fingerprint. Suite pins explicitly name expected
case and descriptor fingerprints. Selection precedes the runner; scorer selection
belongs to suite/run configuration, never concrete classes on TestCase. Grouped
reporting and compatibility-aware comparisons will follow in Milestone 4; this
milestone does not claim those APIs already distinguish new context.

None of those future behaviors alters legacy judge evidence. The current
generic rubric builder includes tags, and Target.invoke receives the whole
TestCase; this milestone does not change either boundary. Dataset/integration
authors remain responsible for forwarding only application inputs to a target.
New readers preserve old artifacts; old releases do not understand v2 and must
not resave or relabel v2 documents after dropping fields.
