# Sales Agent Evaluation Study v1 integration

The study has **50 authored candidates under human QA; it is not frozen or run**.
Readiness Milestones 1–2 implement the prospective workflow and integration
boundary. The subsequent candidate authoring and approved 2026-10-17 quality
corrections are recorded in the [candidate review](studies/sales-agent-evaluation-study-v1-authoring-review.md).
No live deployment freeze, human ratings or study findings are supplied.

The [approved preregistration](studies/sales-agent-evaluation-study-v1-preregistration.md)
is pinned to commit `5995e24d59d3e5795df0429a940f01a638974dd3`, SHA-256
`5de0400bc3de7d910902d72b2d7199aab81d0b553e733faabfe0f4da91fa9ace`.
The independently transcribed [matrix resource](../src/harness/packs/data/salesagent-study-v1-matrix.json)
contains only approved classifications, totals and selectors. Its bytes are
pinned by the integration and checked against a separate reading of that
preregistration in tests. It contains no shopper input or evaluator reference.

## Candidate files

```text
datasets/salesagent/study-v1/
  dataset.json
  cases.jsonl
  suites/
    full.json
    smoke.json
    critical.json
    multi-turn.json
    adversarial.json
    variance.json
```

These files are not created by readiness implementation. The descriptor must
use ID `sales-agent-evaluation-study`, authored version `study-v1`,
`dataset-descriptor-v1` and `dataset-cases-v2`. The strict generic loader resolves
local case bindings relative to the descriptor, rejects unknown/duplicate JSON
keys and non-finite values, and preserves input/reference/metadata structure.
Descriptor, full ordered case, selected subset and suite fingerprints remain
different concepts. Supplied suite fingerprint pins are verified independently.

The harness owns taxonomy mechanisms; the study owns their values. Shopper
turns belong in `input.turns`, deterministic assertions and semantic expectations
in `reference`, and authored provenance in `extra`. No PASS/FAIL, latest status,
scorer class, experimental membership or suite dispatch belongs on a TestCase.
Study metadata allowlists are currently empty. A subtree named `provenance`
is not automatically exported. Full authored metadata still affects hashes.

## Matrix and whole-study validation

`harness.packs.salesagent_study.load_study(descriptor, suite_paths)` uses generic
descriptor/suite loading. `validate_study()` validates all 50 rows before any
selection or client construction. It compares against the package resource,
never against expectations inferred from the candidate itself.

Each approved ID must have its exact category, risk, journey and difficulty.
There must be exactly one journey tag and one difficulty tag, no duplicate or
unapproved tags, and no experimental-membership tags. Single-turn requires one
shopper turn; multi-turn requires at least two. Optional behavior/commerce tags
remain authoring choices within the approved vocabulary. Totals are:

| Dimension | Counts |
| --- | --- |
| Categories, in preregistration order | 8 / 7 / 6 / 7 / 6 / 6 / 5 / 5 |
| Journey: single / multi | 30 / 20 |
| Difficulty: normal / boundary / ambiguous / adversarial | 18 / 19 / 5 / 8 |
| Risk: critical / high / medium / low | 12 / 18 / 15 / 5 |

All cases pass Sales Agent input validation, structured assertion validation and
semantic expectation validation. Invalid references outside a selected smoke
suite still block execution. Identifiers and literal shopper turns from the
frozen historical studies cannot be reused. The approved fresh holdout policy
requires manual review of substantive freshness and factual expectations; there
is no semantic-similarity detector or invented expectation generator.

All six suites bind the same descriptor and use the capture profile. Expressions
and attempts must match the reviewed matrix, not merely happen to select the
same cases:

| Suite | Selector | Cases | Attempts |
| --- | --- | --- | --- |
| full | `{}` | 50 | 1 |
| smoke | Revised eight explicit IDs in preregistration | 8 | 1 |
| critical | `risks: [critical]` | 12 | 1 |
| multi-turn | `tags_all: [journey:multi-turn]` | 20 | 1 |
| adversarial | `tags_all: [difficulty:adversarial]` | 8 | 1 |
| variance | Ten explicit approved IDs | 10 | 3 |

The 12 human IDs are an experimental selector, not a judged suite or taxonomy
tag. They are disjoint from variance and revised smoke. Smoke and variance may
overlap at SA-STA-004 and SA-ADV-002. Dataset order determines resolved execution
order; original expressions and ordered membership are frozen together.

## Profiles and isolation

`capture_profile()` returns only `StudyLabelAssertionsScorer`, requiring
structured, metadata and trajectory evidence, plus profile
`salesagent-study-v1-capture`. This uniform scorer evaluates every capture
attempt. It composes unchanged generic assertions with explicit
`reference.salesagent_rules` opt-ins and records schema
`salesagent-study-assertions-v3`, reference contract
`salesagent-study-v1-references-v3`. It casefolds temporary comparison copies
only for per-turn resolved-constraint features/colour/size, search-products
argument category, and check-inventory result colour/size. Named tool patterns
and concrete indexed tool paths supply tool type; arbitrary matching dictionary
keys do not activate the policy. Values are not trimmed or mapped to aliases.
The original case/response remains intact. Product IDs, numerical values,
status enums, feature order and other fields retain their existing semantics.
The original `StudyAssertionsScorer` v2 remains available explicitly with its
unchanged scorer snapshot and outcomes. Only SA-ADV-001 currently opts into
`validated-discount-v1`: null promotion/pricing permits refusal; a promotion
requires consistent current-turn validation; a quote additionally requires
matching promotion, current product facts and Decimal discount-first pricing.
Rules are selected by reference configuration, never case ID/risk/taxonomy.
The generic scorer and operators are unchanged. It makes zero semantic calls.
The study explicitly opts into full
case payload snapshots and rejects hashes-only overrides; generic defaults
remain unchanged. Case and dataset metadata allowlists remain empty.

`semantic_profile(judge_configuration, judge_fn)` returns the existing Sales
Agent rubric scorer with profile `salesagent-study-v1-semantic`. It preserves
the historical scorer name, rubric/version, prompt format and threshold 0.7.
It explicitly selects `salesagent-semantic-evidence-v4`, which retains every
allowlisted successful get-product/search-products observation in its original
turn, including duplicate/conflicting records in source order, without requiring
cards or textual mentions. It also retains the v3 inventory behavior. These
are observed facts, not a guessed name-to-ID mapping or imported catalogue.
Promotion selection and error handling are unchanged. The existing 64 KiB UTF-8
evidence limit rejects oversized payloads as ERROR before judging; no facts are
silently truncated. No warmth/season fields are added.
The human rating contract selects the same v4 evidence. It also selects the
`salesagent-semantic-anchors-v1` output contract: 0.0, 0.3, 0.6, 0.8, 1.0.
Other scores, including 0.7, are evaluator ERROR under this new profile. The
historical `salesagent-semantic-v1` factory still defaults to v2 evidence and
accepts continuous scores; its prepared bytes and configuration are preserved.
Explicit v3 remains supported with unchanged prepared bytes and configuration.
Existing Study execution contracts with older profiles must be reviewed and
re-frozen before execution, never silently interpreted as the corrected config.

Both study profiles declare taxonomy excluded. Tests prove changing title,
description, category, risk, tags and extra leaves semantic prepared bytes
unchanged. Semantic expectations legitimately enter evaluator evidence; none
of these evaluator fields enters the Sales Agent HTTP request. Recorded mock
requests contain only shopper messages and session input. Sessions persist only
between turns of one attempt and remain isolated across attempts and cases.
Application validation and evidence projection stay in the Sales Agent pack;
there are no study values or category-to-scorer mappings in generic core.

## Target and execution freeze

`StudyTargetFreeze` is a strict immutable integration model with a canonical
digest. `requested` records:

- Credential-free service URL and full deployed target commit SHA.
- Provider/model and reviewed bounded generation parameters: status, temperature,
  top-p, maximum output tokens, seed and reasoning effort when exposed.
- Prompt version and/or digest; catalogue and promotion revision plus SHA-256.
- Adapter/evidence/HTTP contract versions and exact capabilities.
- Isolated-case-attempt session policy, reviewed bounded state settings,
  explicit timeouts and evaluation-trace enablement.

The outer model records full harness revision and operator verification
(statement, timestamp, deployment reference). Missing facts remain visible via
`missing_facts` and `inspect-freeze`; they block execution-contract creation.
Generation/state settings may explicitly say `not_exposed` without claiming
values. Missing model, fixture, revision or interface facts cannot be inferred
from historical files. Unknown labels are not substitutes for required facts.

`freeze_execution()` requires explicit manual author review and creates an
immutable `StudyExecutionContract`. It binds methodology/matrix hashes, descriptor
and full case fingerprints, all suite fingerprints/expressions/memberships,
attempts, both profiles, exact semantic evaluator and anchors, human rating
contract, empty metadata policies, full-payload policy and target freeze.
Budgets record target invocations and maximum HTTP requests per suite, 50 primary
semantic calls, and an explicitly supplied diagnostic-call allowance per plan.
The adapter makes at most two requests per completed shopper turn. These are
local operation budgets, not a cross-process/provider billing quota.

Capture revalidates the entire study before constructing the target and checks
actual adapter configuration against the frozen request. Review/verification
must precede capture. Requested facts are copied before invocation and stored
in run context. Original per-response/per-turn observed labels remain separate.
Trace model/prompt/schema drift qualifies comparison; it never overwrites a
requested setting or triggers automatic recapture. Operator-provided target
commit and fixture facts are not remote attestations from trace labels.

## Two-stage primary workflow

1. Freeze the authored dataset, suites, deployment facts, evaluator and execution
   contract after manual review and explicit future authorization.
2. `capture(..., suite_id="full", target_factory=...)` produces a deterministic
   capture RunResult with 50 attempts. Persist it immutably through the existing
   SQLite store. A capture PASS is not a final study PASS.
3. `prepare_primary()` verifies that exact saved capture and all source cases,
   then prepares the semantic evaluator on each completed response. Nothing
   invokes or reruns the target. Failed unprotected responses are explicitly
   unavailable; a missing protected response blocks preparation of the human
   study rather than shrinking/substituting its 12-case roster.
4. Save the preparation and register its prospective bundle. Primary request
   and observation IDs are derived from the execution contract, original source
   document, case and attempt; another plan cannot silently reissue them in the
   same experiment store.
5. `human_manifest()` creates exactly the reserved 12 protected examples.
   Export the blind packet; humans independently complete the initially blank
   draft. Freeze the complete matching annotations using existing receipts.
6. `judge_request()` validates the complete study/preparation policy. Protected
   requests then pass the generic receipt/roster gate before the judge factory
   is constructed. Unprotected requests can be judged independently. Calls use
   the same captured response and exact prepared prompt/configuration.
7. Save the returned result once; then construct a separate derived analysis.
   Do not modify source runs or substitute a different primary observation.

A protected response may not be downgraded by authoring an unprotected replacement
plan: the study wrapper compares the exact approved human roster and contract.
The generic API still supports other experiments; it cannot prohibit calls made
outside the declared study workflow. Use one experiment store for registration.
Reservations persist after ambiguous failures; see [prospective recovery](prospective-judging.md).

## Variance and derived analysis

After the primary human-review phase, execute the approved variance suite:
10 cases × 3 isolated target attempts. This is end-to-end target variation.
The operator follows the preregistered phase order; the command API does not
schedule phases automatically. Failed conversations retain ERROR with no
fabricated partial TargetResponse. Every completed response remains selectable
by original run/case/attempt. `prepare_variance_diagnostic()` prepares fixed
responses for separately budgeted judge-only diagnostics without another target
call. Diagnostics are distinct artifacts and cannot replace primary observations.

`reporting.study.analyze()` validates source/contract/preparation bindings and
selected result/receipt/configuration before creating immutable `StudyAnalysis`.
Each original attempt has classification, deterministic scores/errors, semantic
availability and evidence, request/result/receipt hashes and a derived outcome.
Pending semantic evidence has no final PASS/FAIL/ERROR/zero. A target failure
without response is terminal ERROR with semantic evidence unavailable. When
all required evidence is terminal, ERROR takes precedence, then gated FAIL,
PASS and SKIP. Critical deterministic failures remain visible independently.

The analysis retains source/preparation/result digests and requested-versus-
observed context. It never impersonates an executed RunResult or mutates one.
JSON receipt persistence supports standalone descriptive grouping by category,
risk and overlapping tags. Each layer has separate counts, quality denominators,
error rates and scorer evidence counts. Quality rates use the existing mean of
case pass rates, excluding absent quality evidence; no risk weighting or new gate
is introduced. Comparisons show both groups/memberships and changed/unknown
context rather than claiming an unqualified target regression. The small
Markdown renderer escapes authored identifiers. Diagnostic artifacts remain
outside primary summaries.

## Commands

The thin [recipe](../examples/salesagent_study.py) has no import-time clients.
Run from the repository environment. Candidate files require completed human QA
and freeze before execution.
`--help` describes required arguments. Commands requiring a study take
`--descriptor PATH --suites PATH1 PATH2 PATH3 PATH4 PATH5 PATH6`.

| Command | Behavior |
| --- | --- |
| `validate`, `preview` | Pure loading/validation and fingerprinted membership/budget summary. |
| `inspect-freeze PATH` | Pure missing-fact list and target-freeze fingerprint. |
| `freeze` | Pure contract preparation from explicit target/judge JSON, review statement/time and diagnostic budget; new receipt directory. |
| `capture` | Requires contract, suite, new output directory, exact target budget, `--live` **and** `--allow-target-calls`. |
| `prepare` | Reads saved capture, creates primary preparation and prospective registration; requires reserved plan/review-set IDs. |
| `prepare-diagnostic` | Reads variance capture; explicit case/attempt, plan ID and bounded judge attempt count. |
| `export` | Verifies preparation and writes blind packet/blank human draft. |
| `freeze-human` | Freezes supplied human-authored draft; never generates ratings. |
| `judge` | Requires prepared request, source, store, exact call budget, `--live` **and** `--allow-judge-calls`; protected requests also require `--frozen`. |
| `analyze`, `render`, `compare` | Read-only joins/rendering/comparison, with new immutable analysis output when requested. |

`capture` writes a recovery JSON before SQLite insertion; `judge` writes a
recovery JSON before result publication. A save failure never triggers another
call. Retain the in-memory/recovery result and retry saving only; partial files
are not overwritten. New output directories and existing observation
reservations prevent silent replacement.

The live recipe currently constructs the existing Sales Agent HTTP adapter and
existing OpenAI judge adapter only for its exact declared configuration. It reads
`HARNESS_JUDGE_API_KEY` solely inside the deferred post-receipt factory and never
records it. Python factories support other injected provider-neutral judges.
Import/help/validation/preview/freeze/preparation/export/analysis never construct
those clients. Readiness tests use only deterministic fakes and mock transport.

## Compatibility and remaining approval

Historical baseline/semantic datasets, their 14-case loaders, profiles, expected
hashes, replay/calibration artifacts and human bindings remain untouched. No
RunResult/SQLite schema, Target protocol or generic taxonomy/suite changes are
needed. New readers require the prospective schemas plus study validation,
target-freeze, execution, preparation and analysis `v1` schemas. Older readers
must not resave these artifacts while dropping context.

Before a live study, remaining work is to finish reviewing the 50
candidate inputs and expectations, freeze their actual descriptor/suites, resolve
real deployment facts, supply and review actual judge configuration, and approve
live execution and budgets. The coverage matrix is already approved; it must not
be redesigned to fit observed outcomes. No case authoring or live run is part of
[the readiness implementation](plans/salesagent-study-v1-readiness.md).
