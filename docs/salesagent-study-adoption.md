# Sales Agent Evaluation Study v1 adoption contract

The 50-case study is **planned, not authored**. Generic taxonomy, descriptors,
suites, snapshots and reporting are implemented through Milestones 1–4. This
Milestone 5 document specifies future integration contracts only; it adds no
study cases, profile factory, live entry point, scorer or rubric change.

**Design and approve the Sales Agent Evaluation Study v1 coverage matrix before
authoring cases.** This approval is still outstanding. The intended study is a
fresh holdout-style evaluation; earlier scenarios are not automatically its seed
data. Adoption documentation does not authorize case authoring or live execution.

## Planned files and binding

```text
datasets/salesagent/study-v1/
  dataset.json
  cases.jsonl
  suites/
    ...
```

This is a layout contract, not an existing or populated study. Final dataset
identity/version strings, suite filenames, profile IDs and coverage vocabulary
will be chosen later. The directory name does not substitute for descriptor
identity or an authored version.

| File | Future contract |
| --- | --- |
| `dataset.json` | `DatasetDescriptor` with `schema_version: dataset-descriptor-v1`, a new `id` and authored `version`, optional title/description, `cases: cases.jsonl`, dataset-level `extra`, and `fingerprint_scheme: dataset-cases-v2`. |
| `cases.jsonl` | One strict v2 TestCase per nonblank physical line. The eventual approved collection will contain 50 cases; none are supplied here. |
| `suites/*.json` | Generic `suite-v1` definitions binding the exact dataset ID/version through `descriptor: ../dataset.json`, with explicit attempts, authored selection and a logical evaluation profile. Cases are referenced, never copied into suites. |

Use `harness.core.dataset.load_dataset()` for descriptor-aware loading, or
`harness.core.suites.resolve_suite()` to load, bind and preview a suite without
constructing targets, scorers or judges. Validate the entire dataset before
selection, including cases a subset would exclude. Keep legacy Sales Agent
loaders and their exact 14-case validation separate from this new path.

Strict loading rejects unknown keys, duplicate JSON object keys, duplicate IDs,
invalid types/coercions, non-finite JSON values and invalid tags. Identity and
taxonomy strings reject leading/trailing whitespace rather than trimming it;
internal whitespace is allowed. Non-null title must be nonblank; description
remains prose. The descriptor's case binding is local and relative to its
directory, not the process cwd; absolute paths, URLs and parent traversal are
invalid. See the [generic authoring guide](test-taxonomy-and-suites.md) for the
complete validation and selector contracts.

Keep these fingerprint meanings separate:

- Descriptor fingerprint binds the normalized authored descriptor, including
  its full metadata and relative case binding.
- Full case fingerprint binds all ordered case definitions under v2, including
  inputs, references, classification and authored metadata.
- Executed subset fingerprint binds only the ordered selected cases and is
  stored as `RunResult.dataset_hash`.

Suite binding may pin case content with `expected_case_fingerprint` and may also
pin the descriptor with `expected_descriptor_fingerprint`. Every supplied pin
is verified before target calls. Authored versions are not generated from hashes.

## Definition ownership and IDs

The harness owns taxonomy mechanisms; this study and its integration own values.
No Sales Agent vocabulary, scenario special cases or category-to-scorer mappings
belong in core.

| Definition field | Owner and meaning |
| --- | --- |
| `id` | Study-owned stable scenario identifier, unique within its dataset. |
| `title`, `description` | Optional human-readable definition text. |
| `input` | Intended shopper/user turns, using the supported Sales Agent input contract (`input.turns` today). |
| `reference` | Application-specific deterministic assertions and semantic expectations, validated by the integration. |
| `category` | Optional primary classification of what the case is about. |
| `tags` | Cross-cutting classification; values may span several primary categories. |
| `risk` | Optional declared criticality, opaque to core; no built-in weighting, ordering or automatic gate. |
| Case `extra` | Safe authored provenance and case metadata. Export requires a separate explicit allowlist. |
| Descriptor `extra` | Safe study-level provenance/metadata, with its own export allowlist. |

Do not add a second `metadata` container, concrete scorer class names, latest
status or PASS/FAIL to TestCase. Suites define execution membership; profiles/run
configuration select evaluation; attempts in RunResult contain verdicts.

IDs are stable once a study definition is published. Cross-study reuse must be
intentional and semantically justified. Similar wording does not automatically
imply case identity, and a matching ID alone does not establish cross-dataset
comparability. The coverage exercise will decide whether any existing scenario
or ID is reused; this contract makes no such decision. Changed inputs,
expectations or classification remain detectable through definition fingerprints.

## Recipe and evaluation-profile ownership

Future Sales Agent recipe code resolves a suite's logical profile ID through
ordinary explicit Python factories. Suite JSON is not an executable class or
plugin specification. A factory supplies a uniform scorer list for the entire
run, an `EvaluationProfile`, and the integration validator for the selected
reference contract. It does not dispatch scorers by category, risk or case ID.

| Responsibility | Integration contract |
| --- | --- |
| Deterministic evaluation | Construct supported structured assertion scorers explicitly; case references supply assertions. Preserve critical checks and independent scorer results. |
| Semantic evaluation | Construct semantic scorers with injected judges only when required by the approved profile. Record model/provider settings, thresholds, rubric and projection versions through explicit scorer and `JudgeConfiguration` settings. No new rubric or threshold is selected here. |
| Capability requirements | Choose scorers whose declared evidence requirements match the adapter's capabilities. The current adapter advertises `structured`, `metadata`, `trajectory`; requirements come from scorers, never taxonomy. Generic execution checks the union before invocation. |
| Configuration evidence | Populate `scorer_configuration` and applicable `judge_configurations` under stable scorer names; use `safe_parameters` only for reviewed finite JSON configuration. Missing custom configuration remains unknown for comparisons. |
| Taxonomy evidence | Declare `taxonomy_evidence` as `excluded` or `explicitly_included`; document the actual evidence projection rather than infer it from profile names. |
| Metadata export | Supply reviewed `case_extra_keys` and `dataset_extra_keys`; both default to empty. Review the entire subtree of each allowed key. A key named `provenance` does not establish safety. |
| Payload persistence | Choose `case_payload_snapshot` deliberately; defaults are hashes-only and replay-oriented opt-in is described below. |
| Reference semantics | Pair a versioned `reference_contract` with a pure `validate_reference(TestCase)` callback to `execute_suite()`. Validate every selected case before any target call without mutating definitions. |

Future recipes should resolve/inspect preview and perform application input and
reference preflight before constructing live clients. Generic suite validation
does not validate Sales Agent business semantics and cannot undo side effects
of clients already constructed by callers. The integration owns input shape,
reference schema and expected evidence compatibility; it must not route the new
study through a frozen loader merely to reuse its whole-study restrictions.

After preflight, explicitly supplied target/scorer instances and the profile
are passed to `execute_suite()`. Profile ID must match the suite or an explicit
recorded replacement. Supported overrides are attempts, profile replacement and
payload policy; effective values and authored defaults remain distinct. Empty
selection cannot execute. A suite without a profile still requires explicit
profile/scorer arguments; the future study should author logical profile IDs.

Existing integration sources document reusable boundaries, not new study entry
points: [baseline recipe](../examples/salesagent_baseline.py),
[semantic pack](../src/harness/packs/salesagent_semantic.py), and
[HTTP adapter](../src/harness/targets/salesagent.py). Their frozen-study loaders,
rubrics and evidence contracts are unchanged. Future factories must deliberately
select compatible components without inheriting the old dataset size or IDs.

## Payload policy and replay

`hashes_only` is the generic default. Every v2 execution still preserves the
definition hash/scheme, title/description/category/risk, copied tags, configured
safe metadata projection and execution context needed for historical reporting.
It does not persist canonical TestCase input/reference payloads.

Profiles requiring those payloads for exact replay/reconstruction may explicitly
set `case_payload_snapshot: full`. A profile that requires full persistence also
sets `requires_full_payload: true`, rejecting hashes-only overrides. A future
Sales Agent semantic/replay profile may make that choice; simply using a judge
does not opt in. Record effective policy, policy source and any run override.

Full mode additionally stores selected canonical input/reference payloads in
`resolved_cases`, excluding full authored `extra`. It does not guarantee a
self-contained replay: selected subsets, omitted authored metadata or external
evaluator dependencies can still require verified source material. Hashes-only
replay needs externally supplied source cases verified against the recorded
scheme, dataset and definition hashes and execution context. Missing or
mismatched material fails preflight; never substitute current cases silently.

Both modes support persisted classification grouping and definition-hash
comparison. Payload availability differences are artifact context, separate from
quality configuration changes. Neither mode redacts target response evidence or
explicit scorer settings. Do not copy secrets, hidden prompts or raw provider
state into metadata/configuration. No general redaction framework is proposed.

## Target and judge isolation

Only intended shopper/session input reaches the Sales Agent HTTP contract.
Case IDs, titles, descriptions, category, risk, tags, reference expectations,
thresholds and evaluator metadata must not become request input. Session state
is preserved only between turns of the same attempt; cases and repeated attempts
remain isolated. The adapter normalizes per-turn evidence into TargetResponse.

The retained Target protocol passes a TestCase to the adapter, so forwarding
discipline remains an integration obligation. Future adoption tests must record
mock HTTP request bodies and prove that changing only classification, reference
or metadata leaves application request bytes unchanged.

Judge evidence is a separate evaluator boundary. Sales Agent evidence projection
remains integration-owned. An exclusion profile needs a named/versioned reviewed
projection and tests proving that title/description/category/tags/risk/extra
changes leave prepared evidence/prompt bytes unchanged. The default legacy
RubricJudgeScorer builder includes tags; preserve its behavior and never label
that default as taxonomy-excluded. No legacy prompt or rubric is changed here.

## Frozen evidence and future adoption acceptance

`baseline.jsonl` and `semantic.jsonl` remain historical frozen 14-case studies,
with existing loaders, bytes and expected hashes unchanged. Their run, replay,
calibration artifacts and human bindings are not migrated or backfilled. Legacy
v1 serialization/hashes and historical payload representation remain intact.
Do not relabel old runs as v2 or add new persistence-policy keys to them.

The new study uses a separate descriptor and strict v2 path. Readers must
support `run-organization-v1` and `case-definition-snapshot-v1`; old tooling must
not resave artifacts after discarding unknown fields. Fingerprint schemes and
dataset identities must remain explicit when comparing old/new results. No
direct target-regression claim follows from comparing different studies.

After coverage approval and future authoring/integration authorization, adoption
acceptance should use deterministic fakes and mocked HTTP to prove strict whole-
dataset validation, suite binding/preview, selected-reference preflight,
capability mismatch rejection, uniform scoring, request/session isolation,
projection invariance, both payload policies and verified replay requirements.
Check persisted grouping/comparison from recorded evidence alone and unchanged
frozen-study compatibility. These are future acceptance requirements, not tests
or entry points implemented by this documentation milestone. Live evaluations
remain separately and explicitly invoked.

## Outstanding coverage-matrix decisions

Before authoring any of the 50 cases, explicitly approve:

- The 50-case distribution and primary categories.
- Cross-cutting tags and risk assignments.
- Single-turn versus multi-turn distribution.
- Normal versus edge/adversarial cases.
- Deterministic versus semantic expectations.
- Holdout strategy and deliberate reuse, if any, of existing scenarios/IDs.
- Suite membership and associated evaluation profiles.

Possible suite purposes include full evaluation, smoke, critical/high-risk,
semantic quality, and multi-turn or other coverage-driven subsets. These are
possibilities only, not selected names, risk values, membership or filters.
Use the generic selector once coverage is approved; do not predefine a Sales
Agent taxonomy in core or infer profile selection from these labels.

The [ExecPlan](plans/test-taxonomy-datasets-suites.md) records completion of this
preparation milestone. The coverage matrix, actual study files and all 50 case
definitions remain outstanding.
