# Sales Agent Study v1 readiness

This ExecPlan was created on 2026-10-03. Its architecture is approved, with the
per-case journey/difficulty amendment committed on 2026-10-05. **Milestone 1 only
is authorized for implementation.** Milestone 2 and study case authoring remain
unstarted and require separate approval. No live targets or judges are authorized.

Authoritative methodology: [Sales Agent Evaluation Study v1 pre-registration](../studies/sales-agent-evaluation-study-v1-preregistration.md).
It is committed at `5995e24d59d3e5795df0429a940f01a638974dd3`, has status
`Approved pre-registration`, and its file SHA-256 is
`5de0400bc3de7d910902d72b2d7199aab81d0b553e733faabfe0f4da91fa9ace`.
This pins the approved methodology for this slice; it does not claim the future
50-case dataset has been authored or frozen. The revised smoke IDs below are
part of this approved revision. Do not use the earlier smoke selection.

Planning inspected integrated `main` at
`fa1db065a9446ac300ab3ae99761eb7fa36f22af`. Generic Milestones 1–5 are merged
through `3ae4838`; their architecture remains unchanged. Implementation re-read
AGENTS.md, verified the integrated revision, and created the dedicated feature
branch `feat/salesagent-study-v1-readiness` from that main revision. The only
pre-existing worktree item was this untracked approved planning document; no
tracked source changes intervened.
The named integration branch `codex-evaluation` currently points to ancestor
`60f9ad4fb58423b75a306171fbf31da23529a731`, which lacks the inspected merged work.
Start the feature from the inspected integrated revision or its approved
successor containing both prerequisites, rather than downgrading the baseline.
The later implementation request explicitly authorized the prerequisite
preregistration commit, now pinned above. Implementation remains on that
feature branch. No merge, rebase, branch deletion or history rewrite is authorized;
Milestone 1 code remains uncommitted for review.

## Purpose, acceptance and progress

Enable an unjudged fixed response to enter a prospective human-first experiment
without pretending that a historical judge result/configuration existed. After
human annotations are frozen, judge exactly the prepared request and join its
immutable observation to its original source. Then wire the approved study to
this generic path, enforcing its matrix and versioned anchor contract outside
core. The slice ends with deterministic offline acceptance, not case authoring
or live study execution.

Acceptance requires all of the following:

- Human-protected requests cannot invoke a judge through the prospective API
  without a verified, complete, matching annotation freeze receipt.
- Every judged request binds the original source document/attempt/response,
  case definition, exact prepared evidence/prompt and intended evaluator.
- No target is accepted by prospective preparation, judging or analysis APIs.
- Historical replay, calibration, continuous-score parsing and fingerprint
  representations retain their exact meaning and serialized bytes.
- Study validation compares against an independently reviewed matrix, including
  revised smoke membership, before any target/client invocation.
- Primary capture has uniform deterministic scorers. Delayed semantic results
  are separate evidence; a capture PASS is never labelled final study PASS.
- All five specified anchors are accepted; other numeric values, including 0.7,
  are evaluator ERROR under the new contract, never rounded or scored as zero.
- Every completed variance response remains selectable; failed conversations
  without a TargetResponse remain ERROR without fabricated evidence.
- No actual study input, assertion, semantic expectation or target setting is
  invented in this slice. No live services or paid dependencies are needed.

Progress:

- [x] Read the request, AGENTS.md, committed methodology and reusable boundaries.
- [x] Confirm clean starting tree, merged prerequisites and revised smoke IDs.
- [x] Recheck 23 protected file hashes read-only.
- [x] Draft architecture, compatibility strategy, file map and offline acceptance.
- [x] Architecture approved; exact per-ID methodology amendment committed first.
- [x] Milestone 1 authorized on 2026-10-05; Milestone 2 remains unauthorized.
- [x] Milestone 1: prospective judging, opt-in human freeze and anchor contract.
- [ ] Milestone 2: Study v1 integration, validation and offline analysis join.
- [x] Record Milestone 1 validation commands, results and implementation decisions.
- [ ] Separate future authorization: author/review/freeze the 50 study cases.
- [ ] Separate future authorization: live study execution.

## A. Current reusable components

`core/dataset.py`, `core/selection.py` and `core/suites.py` already implement
strict descriptor-aware v2 loading, deterministic selection, suite binding/pins,
preview and explicit uniform scorer execution. `core/runner.py` freezes source
classification and hashes, retains each attempt/response, preserves independent
scorer results and distinguishes PASS/FAIL/ERROR/SKIP. Reuse these contracts.

`StructuredAssertionsScorer` is named `structured_assertions`, uses schema
`structured-assertions-v1`, and exposes `validate_assertions(reference)`.
Sales Agent recipes require structured, metadata and trajectory evidence.
`targets/salesagent.py::validate_input` validates `input.turns`; its adapter
starts an isolated session per invocation and exposes normalized per-turn
results. It advertises `structured`, `metadata`, `trajectory` and records
operator-supplied target revision plus observed model/prompt metadata.

`packs/salesagent_semantic.py` supplies `semantic_expectations`, `build_evidence`,
`make_scorer` and `configuration`. Preserve these historical identifiers:

| Contract | Existing value |
| --- | --- |
| Profile | `salesagent-semantic-v1` |
| Scorer | `salesagent_semantic_quality` |
| Rubric | `salesagent-shopper-quality-v1` |
| Projection | `salesagent-semantic-evidence-v2` |
| Expectations | `salesagent-semantic-expectations-v1` |
| Prompt | `rubric-untrusted-json-v1` |
| Judgment shape | `score-reason-v1` |
| Threshold | 0.7 |

The generic `RubricJudgeScorer` parser accepts finite [0,1] scores; anchors are
currently rubric guidance for judges. The human `RatingContract` already
requires exactly its declared anchors. Keep the distinction explicit.

`PreparedJudgeInput` freezes canonical configuration/evidence strings and prompt
text with existing hashes. `EvaluatorConfiguration` binds scorer and explicit
safe `JudgeConfiguration`. `SourceProvenance` identifies source document,
response, dataset/case/input, selection and attempt. Historical `prepare_replay`
requires verified source definitions and recorded evaluator compatibility;
`replay` checks actual request bytes/configuration without accepting a target.

`CalibrationManifest`, `CalibrationExample`, `blind_packet`, `export_bundle`,
`freeze_bundle`, `load_frozen`, `analyze_bundle` and the calibration renderer
already implement reviewer separation, binding nonces, receipt verification,
exposure flags, correction history and descriptive agreement. Their historical
path expects `PreparedReplay` with matching recorded evaluator configuration.
The concrete Sales Agent calibration recipe hardcodes the previous 18-response
pilot and must remain unchanged.

`SQLiteResultStore` preserves whole RunResults/ReplayResults; read-only
`load_with_fingerprint` binds the original stored document. Generic grouping and
comparison consume persisted RunResult evidence. Neither currently joins delayed
semantic observations. Do not mutate a capture run to disguise this gap.

## B. Exact architecture changes proposed

Add a small generic prospective path beside historical replay, a versioned
opt-in score-output contract, and one study-owned integration module/recipe.
Avoid a new execution engine, plugin registry, query language or generic study
framework. Proposed names below are implementation-review API names, not claims
that those APIs already exist.

1. Extract only shared source-definition/response verification from
   `prepare_replay` into a private pure helper. Historical preparation still
   performs every recorded-scorer/configuration check after that helper. The
   prospective path intentionally binds a future evaluator separately and never
   labels it `matching_recorded_configuration`.
2. Add `core/prospective.py` for prospective plans, requests, results, verification
   and fixed-input execution. Reuse `PreparedJudgeInput`, `EvaluatorConfiguration`,
   SourceProvenance, canonical hashes and replay attempt/score-validation helpers.
3. Add `core/prospective_io.py` for immutable local JSON bundles and exclusive
   execution reservations. Leave existing SQL tables and stored documents alone.
4. Narrowly extend calibration's accepted preparation/observation kinds so its
   existing packet and human-freeze machinery also accepts honest prospective
   material. Keep historical branches and identity bytes unchanged.
5. Add opt-in anchor output validation and a new Sales Agent logical profile.
6. Add a study-specific validator/profile/target-freeze/analysis integration and
   an explicitly invoked recipe. No change to Target, generic selectors, suites,
   dataset fingerprints or the Sales Agent HTTP contract.

## C. Generic prospective data model and workflow

Use strict frozen models with canonical JSON strings for nested immutable
response/prepared/configuration bodies. Pydantic `frozen=True` alone does not
freeze nested dictionaries. Reject unknown fields, duplicate JSON keys and
non-finite data; validate loaded artifacts again before use. Unknown versions
fail closed. Derived hashes are recomputed, never trusted from caller input.

`ProspectiveJudgingPlan` (`prospective-judging-plan-v1`) contains:

- Immutable plan ID and source selections in declared order: source locator,
  run ID, document hash, case ID, attempt index, response hash and case/dataset
  fingerprints, using existing provenance representations.
- Intended `EvaluatorConfiguration`, taxonomy-evidence declaration and explicit
  payload/evidence sharing policy; these describe future evaluation, not source
  scorer execution. Freeze the configuration before any human packet.
- Preallocated request IDs and observation IDs, unique across the plan, with
  requested judge attempt counts and role (`primary` or `diagnostic`).
- Explicit protected source selections; optional review-set ID and rating-
  contract hash, required when any request needs human-first review.
- Schema/version, creation time and canonical digest. No prompt or target data
  is inferred from a case ID or current dataset.

`PreparedProspectiveJudgment` (`prepared-prospective-judgment-v1`) contains:

- Required discriminant `kind: prospective`, plan digest, reserved request and
  observation IDs, source provenance, canonical source TargetResponse snapshot
  and intended evaluator configuration.
- Existing `PreparedJudgeInput` with exact prompt, canonical evidence and
  configuration. Evidence must be non-null and projection reviewed.
- Existing replay input hash for the same prepared input/evaluator; a separate
  whole-request digest additionally binds source, role, IDs and plan policy.
- Requested attempt count; explicit review requirement/set/contract references
  verified against the plan. There is no historical compatibility assertion or
  fabricated historical semantic Score.

Creation order avoids circular hashes: verify sources and reserve identifiers;
freeze the plan; prepare/hash requests referring to that plan; then construct
and freeze the human manifest referring to those requests. The plan does not
contain its own digest or hashes of the later human manifest. A manifest's
set ID is the already-reserved review-set ID.

`prepare_prospective(plan, source, cases, scorer, judge_configuration, ...)`
checks source/full/subset/definition hashes, tags and v2 snapshots through the
shared verifier. Check source-document fingerprint against the original stored
JSON, clone inputs and detect builder mutations. Prepare a reviewed projection
with no judge invocation. Reject missing response, unsupported schemes, unsafe
projection, invalid evidence or any mismatch with the pre-registered plan.
Preserve the supplied original normalized response in canonical form; do not
regenerate or enrich its content from today's target.

A public verifier rebuilds evidence/prompt with the frozen case material and
scorer and compares all bytes/hashes before execution and analysis. Supplying
external cases under hashes-only remains legal only after full verification.
Full case snapshots still need external source when omitted metadata/subsets
prevent reconstruction. The source dataset remains an independent immutable
input, not a record reconstructed from human labels.

`ProspectiveJudgmentResult` (`prospective-judgment-result-v1`) contains the
reserved observation ID, complete prepared request or its verified bundle
binding, per-call attempt records, timestamps, effective evaluator, actual
prompt/input hashes and normalized judge observations. Protected results also
record the verified freeze receipt digest, manifest/packet hashes and frozen
annotation revision. Unprotected results explicitly record no human receipt.
Both are new immutable artifacts, separate from RunResult and ReplayResult.

Use existing attempt verdict/error semantics. A malformed/off-anchor judgment
has no quality score and produces ERROR. Retain provider observations where
available. Do not persist raw provider responses or synthesize a score/reason.

## D. Anchor-enforcement design

Introduce a small generic `ScoreOutputContract` with a schema marker, an opaque
versioned ID, `kind: anchors`, and an ordered unique tuple of finite numeric
anchors in [0,1]. Reject booleans, duplicates, non-finite/out-of-range anchors,
unknown kinds and malformed contracts. Core does not contain Sales Agent anchor
constants or profile-name switches.

Proposed new logical profile: `salesagent-study-v1-semantic`.
Proposed output contract ID: `salesagent-semantic-anchors-v1`.
Its pack-owned anchors are exactly `(0.0, 0.3, 0.6, 0.8, 1.0)`. Preserve the
stable scorer name `salesagent_semantic_quality`, existing rubric text/version,
evidence projection, prompt bytes, whole-conversation scope and 0.7 threshold.
A new logical profile is required because acceptance of judge outputs changes;
do not replace `salesagent-semantic-v1` in place.

Add optional `output_validation` to the judged scorer's preparation configuration
only when explicitly supplied. The default generic parser and legacy pack factory
remain continuous and emit their exact previous configuration dictionaries.
`RubricJudgeScorer` may accept the optional contract; after its existing JSON/
shape/range checks it enforces exact numeric membership. No tolerance, rounding,
clamping, repair prompt or retry is allowed. 0.7 is a threshold, not an anchor.

`EvaluatorConfiguration.scorer_schema` accepts the existing exact key set or
that set plus one validated `output_validation` object. Unknown additional keys
remain errors. Do not inject null/default keys into historical configuration.
The full contract object, not just its label, participates in configuration,
prepared-request, replay input and prospective fingerprints. Record it in the
explicit profile's scorer configuration and compare it in evaluator context.

Shared score validation on artifact reload must also enforce the recorded
contract, preventing forged off-anchor Scores from bypassing the parser.
Runner scorer snapshots must include the optional contract when enabled, with
no new key on the historical default path. Suite profile snapshots already use
the full judged-scorer preparation configuration; keep both representations
consistent and test explicit profile versus observed-setting mismatches.
Historical configurations without the field retain continuous acceptance,
including historical scores of 0.7. Replay must reject an anchor-enabled scorer
against an old continuous configuration unless the existing explicitly different
experiment rules apply; never claim they are equivalent. Prospective execution
requires exact equality with its frozen contract, without a reconfiguration
escape hatch. Do not globally alter provider `score-reason-v1` JSON schema.

## E. Study-specific integration design

Use `packs/salesagent_study.py` (new) for the study's validation/profile/freeze
boundary and `examples/salesagent_study.py` (new) as a thin explicit recipe.
Application concepts stay in this integration and its reviewed matrix data.
Existing `salesagent_baseline.py`, `salesagent_semantic.py` and historical human/
replay recipes keep their defaults, 14-case loaders and observed behavior.

Proposed capture profile ID: `salesagent-study-v1-capture`. It supplies only
`StructuredAssertionsScorer` with declared structured/metadata/trajectory
requirements. All selected cases and attempts use this same scorer list.
The semantic profile above supplies the unchanged semantic evidence projection
plus the new output contract and explicit judge settings. It is invoked over
captured responses through prospective judging, not through a second target run.
No category/risk/ID dispatch chooses scorers inside a run.

Factories return ordinary scorer instances, `EvaluationProfile` and a pure named
reference validator. Reuse `validate_input`, `validate_assertions` and
`semantic_expectations`. Validate all 50 cases at study preflight, then retain
selected-case reference validation at execution. Profile IDs/configuration must
match the effective suite and frozen study contract. Unknown profiles fail
before clients are built; do not resolve dynamic imports from JSON.

Both profiles declare case taxonomy excluded from judging. The semantic builder
still legitimately includes product attributes/commerce facts; these are not
TestCase taxonomy. Prove title/description/category/tags/risk/extra invariance of
prepared evidence/prompt. No evaluator-only fields reach HTTP shopper requests.

For Study v1 capture, explicitly choose `case_payload_snapshot: full` with
`requires_full_payload: true` to retain canonical inputs/references. This is a
study opt-in and does not change the generic hashes-only default. Prospective
projection snapshots themselves contain evaluator input and must have an
explicit sharing policy even when a generic source used hashes-only; never imply
that source policy guarantees later evaluator artifacts contain no input text.

Metadata allowlists remain integration-owned. Default to no case metadata export
until authored provenance keys and whole subtrees have been reviewed. Freeze
exact `case_extra_keys`/`dataset_extra_keys` in the profile before live capture.
Do not translate the historical nested provenance whitelist into indiscriminate
export of a whole `provenance` subtree. Dataset/reference hashes always bind
complete authored data, regardless of safe export policy. No key name certifies
privacy; no secrets/environment dumps or redaction framework are introduced.

The future CLI should separate offline validation/freeze/prepare/export/analyze
from explicit target-capture and judge-execute commands. Live commands require
an explicit command flag and dedicated opt-in, validated frozen configuration,
new destinations and call-budget settings. Merely importing or previewing must
never construct clients. This slice tests command boundaries with fakes only.
Do not create study dataset/suite files or wire a default invocation to them.

The capture manifest/analysis retains all selected attempts, including failures.
Only attempts with a complete verified TargetResponse can become prepared
prospective requests. Record missing-source reasons separately without inventing
response hashes. A failed protected source blocks complete human-set preparation;
an unprotected target failure remains visible as ERROR rather than disappearing
from study denominators.

## F. Study validator and independently reviewed matrix

Store the integration's approved expected specification as a package resource,
proposed `packs/data/salesagent-study-v1-matrix.json`. This is matrix metadata,
not a TestCase dataset: only approved IDs, categories, risks, journeys, difficulties, controlled tags,
counts and experimental/suite selectors. It contains no shopper prompts,
assertions, semantic expectations or purported authored case definitions.
Pin its source methodology revision/hash. Transcribe all 50 per-ID category/risk/journey/difficulty
assignments from section 11, independently review that transcription, and test
it against a separate source-matrix reading of the pinned document. Never derive
expected entries or totals from candidate cases. Changes require reviewed
pre-registration amendment and a new matrix contract revision.

Required totals:

| Dimension | Approved distribution |
| --- | --- |
| Category | recommendation-quality 8; constraint-handling 7; inventory-variants 6; promotions-pricing 7; conversation-state 6; grounding-factuality 6; recovery-ambiguity 5; business-rule-resistance 5 |
| Journey | single-turn 30; multi-turn 20 |
| Difficulty | normal 18; boundary 19; ambiguous 5; adversarial 8 |
| Risk | critical 12; high 18; medium 15; low 5 |

Exact experimental selectors, outside taxonomy:

```text
variance (10; 3 attempts)
SA-REC-007 SA-REC-008 SA-CON-005 SA-CON-007 SA-INV-003
SA-PRC-006 SA-STA-004 SA-RCV-002 SA-RCV-005 SA-ADV-002

human review (12; primary fixed responses, one initial judge call each)
SA-REC-001 SA-REC-004 SA-CON-002 SA-CON-006 SA-INV-002 SA-PRC-001
SA-PRC-007 SA-STA-003 SA-GRD-003 SA-GRD-006 SA-RCV-003 SA-ADV-004

revised smoke (8; 1 attempt)
SA-REC-002 SA-CON-003 SA-INV-001 SA-PRC-004
SA-STA-004 SA-GRD-001 SA-RCV-004 SA-ADV-002
```

Variance/human are disjoint. Revised smoke/human are also disjoint; smoke and
variance intentionally overlap at SA-STA-004 and SA-ADV-002. Do not accidentally
reject that permitted overlap or use the obsolete human-overlapping smoke IDs.

`validate_study(dataset, suites, matrix)` returns an immutable validation summary
bound to all fingerprints or raises safe actionable file/case diagnostics.
It proves, before target calls:

1. Descriptor ID `sales-agent-evaluation-study`, authored version `study-v1`,
   strict `dataset-descriptor-v1` and `dataset-cases-v2`; exact approved roster,
   unique IDs and 50 cases. No whole-study checks are added to generic loading.
2. Exact per-ID primary category, risk, journey and difficulty, not just totals.
   No assignment changes to meet quotas. All tags belong to the controlled vocabulary from
   pre-registration section 5; experimental membership tags are prohibited.
3. Exactly one journey and one difficulty tag per case. Single-turn means one
   actual shopper turn; multi-turn means at least two. Check approved totals.
   Compare journey/difficulty against the approved exact per-ID values. Only
   optional behavior/commerce tags remain authoring decisions, unless required
   elsewhere by the approved methodology.
4. All cases satisfy input/reference validators; verify assertion shape, unique
   assertion IDs, supported paths/operators and semantic expectation schema.
   Structural validity is not proof of semantic correctness or expected outcomes.
5. Full suite selects all cases in dataset order with one attempt. Smoke uses
   exactly the revised explicit IDs. Critical uses `risks: [critical]` and has
   12 members. Multi-turn uses `tags_all: [journey:multi-turn]` and has 20.
   Adversarial uses `tags_all: [difficulty:adversarial]` and has 8. Variance uses
   exactly its 10 IDs with three attempts. Others have one attempt. Enforce
   approved expressions as well as resolved membership; reject extra filters.
6. All six suites bind the same descriptor ID/version, verify supplied pins and
   use the approved capture profile. Semantic profile and human selection live
   in the frozen study execution contract, not hidden tag conventions.
7. Human selector exactly matches the approved 12, has no duplicate/unknown IDs,
   and is disjoint from variance. Freeze selectors and ordered resolved IDs.
8. IDs are fresh relative to historical datasets, and prompts are not copied
   verbatim. Manual review checks substantive fresh wording and factual grounding;
   no similarity algorithm infers scenario identity.

For offline tests, programmatically generate clearly synthetic disposable data
under pytest temporary paths. A 50-row synthetic validator input may use the
approved ID roster solely to exercise counts; mark it synthetic, with trivial
non-study content. Do not commit it as `datasets/salesagent/study-v1/cases.jsonl`
or present it as the authored study. Test generic prospective components with
unrelated taxonomies and small fixtures, independent of this matrix.

## G. Target configuration freeze shape

Add a strict integration-owned `StudyTargetFreeze` and `StudyExecutionContract`,
with explicit schema versions and canonical fingerprints. The contract binds
methodology/matrix hashes, descriptor/full-case/suite fingerprints, both profiles,
metadata/payload policies, human/variance/smoke selectors, attempts and budgets.
Freeze it before capture; do not infer mutable runtime settings from environment.

Conceptual `StudyTargetFreeze` fields:

```text
schema_version
requested:
  deployed_target_commit_sha
  provider, model, reviewed_generation_parameters
  prompt_version and/or prompt_digest
  catalogue: {revision, sha256}
  promotions: {revision, sha256}
  adapter_version, evidence_schema_version, http_contract_version
  capabilities
  session_policy, reviewed_state_configuration
  timeouts, evaluation_traces_enabled
harness_revision
verification: {operator_statement, verified_at, deployment_reference}
```

Require nonblank/full revisions and valid digests, explicit unknown/not-exposed
settings where justified rather than fabricated defaults, and manual resolution
of missing freeze-critical deployment facts before live execution. Use bounded
allowlists/typed fields for provider and state parameters, not arbitrary config
objects. Never read credentials, raw environment, hidden prompt text or SDK state.
The target SHA is operator-verified; the adapter does not remotely attest it.
Historical product/discount hashes are not evidence of the new deployment.

Copy the safe requested freeze snapshot/hash into run context before final save,
using deep copies prepared before target calls. Preserve observed per-response/
per-turn model, prompt, trace identity and evidence-version data separately;
record differences/unknown observations without rewriting requested values.
The current adapter's model/prompt labels do not attest complete generation
configuration, fixture identity or prompt bytes. Do not infer those from labels.
Unexpected observed versions qualify comparison and block declaring a homogeneous
study; preserve the run and require review, never recapture automatically.

Use existing adapter `configuration` plus explicitly supplied reviewed study
facts. No target API/trace changes or environment introspection are planned.
Catalogue availability and business expectations still require author review.

## H. Delayed-observation persistence and analysis join

Keep target capture in existing SQLite RunResult storage, immutable after save.
Store prospective plan/request/result documents in a new explicit directory,
using exclusive creation, canonical JSON and a checksummed receipt published
last. Reuse existing serialization/hash and exclusive-write patterns; no SQL
migration, mutable status table or artifact rewriting is needed.

Reserve each observation ID before human review. Before a judge call, verify
inputs/receipt and acquire an exclusive execution-start record for that ID. A
second invocation of the same ID fails before the judge, including concurrent
invocations. Write the completed result once. If execution crashes after a call,
leave the reservation unresolved; never assume it is safe to retry a primary
request and spend another call. Recovery requires explicit diagnostic/replacement
policy and a new linked artifact, retaining the original ambiguity. Do not
promise exactly-once remote execution across process failure.

Join keys include source document digest, dataset identity/scheme/fingerprints,
case definition hash, run/case/attempt selector, response hash, prepared request
hash, evaluator hash and reserved observation ID. Verify original source JSON
read-only with `load_with_fingerprint`, rebuild input from verified source cases,
and compare actual-call prompt hashes. Reject duplicate/mismatched observations,
wrong attempts, changed request/configuration and unexpected selected artifacts.
No best-score selection, case-ID-only join or post-hoc observation substitution.

Add an immutable derived `StudyAnalysis` document outside RunResult. It records
source/plan/result/receipt digests and one row per original case attempt with:
classification snapshot, deterministic scores/verdict/error, semantic availability
and scores/verdict/error, and an explicitly derived combined outcome when known.
Missing/pending semantic evidence is not an attempted evaluator ERROR, not a zero,
and not final PASS. Retain a separate completion state. A terminal target failure
without response remains ERROR with semantic evidence unavailable. Once all
required evaluations are terminal, apply existing verdict precedence (ERROR,
then failing required gates, PASS when all required gates pass, otherwise SKIP).
Keep every deterministic critical failure visible even when final state is ERROR.

Report deterministic, semantic and combined evidence separately, with clear
counts/denominators and pending coverage. Primary semantic policy permits one
judge attempt per fixed response. Diagnostic repeats are explicitly linked but
excluded from the primary measure; no averaging away failed critical assertions.
Use existing grouping arithmetic and comparison-context checks on detached
analysis projections where useful, clearly labelled derived and never saved as
an executed/replayable RunResult. Projection must preserve source classification,
add future evaluator context explicitly and report pending coverage; never simply
replace a source run's scorer list or scores. Pure join/report code owns this
boundary, with source documents unchanged before and after analysis.

For human comparison, add `prospective_observations()` analogous to
`replay_observations()`, validating the reserved artifact ID and complete source/
request/freeze binding. Reuse `JudgeObservationSet`, rating distances, exposure
rules, issue-review and report arithmetic. The verification label
`frozen_request_verified` still means verified actual prompt bytes; a new
`ObservationPolicy.kind: prospective` explicitly identifies the origin workflow.
Do not relabel prospective data as historical or manufacture a ReplayResult.

## I. Human freeze enforcement

Narrowly allow `CalibrationExample.prepared` to hold either historical
`PreparedReplay` or the new strictly discriminated prospective request. Preserve
old serialization without adding default/null fields to existing artifacts.
Historical examples still require matching recorded configuration. Prospective
examples instead require a verified plan/source/request with a pre-registered
future evaluator; use `ObservationPolicy.kind: prospective` and the reserved
observation ID. Mixed preparation workflows in one manifest are rejected.

Bind the same existing RatingContract to prepared rubric/projection/threshold/
settings, and additionally check that an explicit output-anchor contract matches
human anchors. Do not add new keys to old RatingContract dumps. Existing example
identity and nonce binding continue to hash their complete preparation. A
prospective request carries new context honestly inside its new model.

Reuse existing packet shape: opaque example IDs/bindings, rating instructions
and exact projected evidence only. No source selectors, target/judge identity,
judge scores/reasons, deterministic outcomes, experimental strata or identifying
public hashes are exposed. Do not generate human ratings. Keep private manifest
separate from the review directory. Existing freeze/correction/receipt semantics
and truthful exposure declarations remain unchanged.

`execute_prospective(plan, request, scorer_factory, judge_configuration, *,
frozen_bundle=...)` enforces the policy, derived from the verified plan rather
than a caller-supplied bypass flag. For protected requests it must:

1. Validate plan/request/source/evaluator and matching reserved IDs.
2. Call existing `load_frozen()` before constructing/invoking a judge client.
3. Verify receipt checksums, manifest/packet bindings, expected set and rating
   contract, and every protected request's exact identity. The manifest must
   cover the exact protected roster from the plan, not a one-item substitute.
4. Require complete annotations for that protected roster, not partial freeze;
   verify the selected request's observation policy and frozen annotation binding.
5. Revalidate the actual scorer/judge configuration, output contract and source
   evidence. Check actual prompt bytes immediately before every invocation.
6. Record receipt/annotation revision digests and call start timestamps; call
   times must not precede the verified freeze time. Receipt verification is the
   primary gate; timestamps alone do not establish causal ordering.

No receipt is required for a plan with unprotected requests. Passing a receipt
must not upgrade an unrelated response or downgraded replacement plan. Study
execution verifies the full StudyExecutionContract and exact human IDs before
any judging, preventing accidental policy stripping via another suite/profile.
Generic APIs cannot stop a malicious operator calling a provider independently;
this is an enforced workflow contract, not an access-control/security service.

Follow-up judge-only diagnostics may reuse the exact frozen evaluator input but
must create a new plan/request/observation identity with an explicit parent
request digest and diagnostic role. For protected sources, verify the original
receipt against the parent request and prove source/evidence/prompt/evaluator/
anchor equality, carrying the protection forward. Never edit the original
request's attempt count or replace its primary observation. No diagnostic is
silently joined as the primary human comparison. Non-protected variance sources
can be prepared for N judge attempts under a declared diagnostic plan.

A protected case lacking a complete TargetResponse cannot receive a fabricated
packet or rating. Keep the target ERROR and block the study's complete 12-item
human workflow until an explicit methodological disposition is reviewed. Do not
replace it with an easier case or silently use partial freeze to release judging.
Exposure/recognition issues likewise remain visible rather than being marked
blind by default. The current human correction and cohort rules still apply.

## J. Replay/calibration compatibility strategy

Before changing shared models/helpers, pin synthetic pre-change artifacts using
the current code, including continuous 0.7 scores, PreparedReplay, ReplayResult,
CalibrationManifest, frozen annotations and canonical analysis. Use existing
`tests/fixtures/taxonomy/legacy-v1.json` unchanged and add only small clearly
synthetic compatibility fixtures where existing coverage is insufficient.
Never copy private annotations or runs into CI fixtures.

Default scorer configuration dictionaries and all historical model dumps must
remain byte/semantic equivalent. New optional output configuration is absent
unless enabled. Calibration unions must preserve the selected historical type,
including nested dumps, include/exclude operations and JSON reloads. Reject
ambiguous/wrong discriminants. Reuse the existing canonical JSON algorithm and
v1/v2 dataset/case schemes without changes.

Extract source verification without relaxing evaluator checks in `prepare_replay`.
A source lacking a semantic scorer still fails its historical path. Generic
`replay()` does not acquire a global human-freeze requirement. Existing pilot
selectors, source/replay IDs, receipts and historical observations remain valid.
Prospective paths never call `allow_reconfigured` to evade their exact frozen
contract. Differences under the new anchor profile are real evaluator changes.

Existing calibration identity/hash, correction, exposure, primary-blind proof
requirements and descriptive calculations remain unchanged for old material.
Extend workflow-kind dispatch and proof validation only. New prospective content
may use the same human freeze envelope because its nested model is explicitly
versioned; old readers cannot handle it and must not resave it. Document the
minimum feature/schema support required rather than relying on the unreleased
package version. No migration or backfill is permitted.

## K. Expected files/classes

| File | Bounded change |
| --- | --- |
| `src/harness/core/prospective.py` (new) | Plan/request/result models, source/input verification, guarded preparation/execution, diagnostic parent binding. |
| `src/harness/core/prospective_io.py` (new) | Strict JSON bundles, exclusive IDs/reservations, result receipts and read-only loading. |
| `src/harness/core/replay.py` | Extract pure source verification; validate optional output contract in EvaluatorConfiguration and persisted scores; retain historical checks. |
| `src/harness/scorers/output_contracts.py` (new) | Small generic anchor-contract model/validator, no application values. |
| `src/harness/scorers/base.py` | Opt-in preparation configuration only; absent contract leaves legacy dictionaries unchanged. |
| `src/harness/scorers/rubric_judge.py` | Optional explicit output contract; unchanged default parser/prompt. |
| `src/harness/core/runner.py::_scorer_snapshot` | Record the optional output contract only when enabled; no execution, verdict or default snapshot changes. |
| `src/harness/core/calibration.py` | Discriminated preparation union, prospective policy/observations, exact binding and contract checks. |
| `src/harness/core/calibration_io.py` | Only changes needed to load/verify the new nested type and enforce existing receipt semantics; no weaker freeze. |
| `src/harness/packs/salesagent_study.py` (new) | Matrix/input/reference validation, profiles, target/execution freeze contract and orchestration. |
| `src/harness/packs/data/salesagent-study-v1-matrix.json` (new) | Reviewed expected matrix metadata and selectors, never case bodies. |
| `src/harness/reporting/study.py` (new) | Immutable derived analysis/join and small safe renderer, reuse existing descriptive arithmetic. |
| `examples/salesagent_study.py` (new) | Explicit command workflow, offline previews and guarded capture/judging; no import side effects. |
| `docs/prospective-judging.md` (new) | Workflow, schema/reader, receipt, replay distinction and failure contracts. |
| `docs/adr/0007-prospective-judging.md` (new) | Decisions and rejected historical-fabrication alternatives. |
| `docs/salesagent-study-adoption.md` | Supported readiness commands/contracts and remaining case-authoring boundary. |
| `docs/judge-replay.md`, `docs/human-judge-calibration.md` | Additive prospective distinction and unchanged historical guarantees. |
| This ExecPlan | Living progress, test outcomes, deviations and remaining decisions. |

Tests: new `test_prospective.py`, `test_prospective_io.py`,
`test_output_contracts.py`, `test_salesagent_study.py`, `test_study_reporting.py`;
extend existing replay/calibration/calibration_io/rubric/suite tests only for
shared-boundary compatibility. Frozen dataset files, historical recipes,
`core/models.py::RunResult`, SQL schema, target adapter/protocol, selectors and
core taxonomy models need no changes. Calibration renderer changes only if
necessary to display the new workflow honestly, never to change old metrics or
rendered historical outputs. Stop and revise the plan for material scope growth.

## L. Test plan

All tests use synthetic data, deterministic fake callables and mocked transport;
`tests/conftest.py` continues blocking socket/DNS access. No target/judge/provider
is constructed during pure preparation/preview tests; use raising factories.

Milestone 1 tests must demonstrate:

- Source with no semantic scorer/result successfully prepares prospectively and
  still fails incompatible historical replay. No fabricated error/Score needed.
- Exact response/evidence/prompt/configuration snapshots, stable canonical hashes,
  immutability after source mutation and complete JSON round-trips.
- Each source/document/definition/attempt/response/prompt/evidence/evaluator/policy/
  anchor/identity tampering variant fails before client construction/invocation.
- Packet contains exact reviewed projection and no judge/deterministic outcomes
  or operational identities; exports start with blank human ratings.
- Missing/altered/wrong/partial receipts, wrong roster, wrong request, wrong
  contract and post-freeze source drift fail with zero calls. Verify receipt
  loading precedes judge factory creation. Successful protected execution uses
  the exact frozen bytes once; unprotected execution needs no human receipt.
- Reserved observation IDs survive prepare/export/freeze/execute/load/join;
  duplicate/concurrent execution fails, save failure never reruns, incomplete
  reservation produces explicit recovery state.
- All anchors accepted; 0.7, 0.5, near-anchor floats, booleans, non-finite values,
  malformed shapes and empty reasons become ERROR without score/rounding. Test
  plain-string and JudgeReply parsing, retained safe provider observations and
  persisted off-anchor tampering. Generic/historical 0.7 remains valid.
- Reconfigured anchor/evaluator is rejected in prospective execution; historic
  replay drift flags remain unchanged. Fingerprints change under contract edits.
- Human/calibration historical golden dumps, bindings, cohort metrics and reports
  remain exact; prospective join uses the same proof strength and arithmetic.
- Diagnostic repeats retain parent identity and receipt protection, all attempts
  and errors, and cannot replace a primary observation or masquerade as new
  target output. Changing only request count never mutates a frozen request.

Milestone 2 tests must demonstrate:

- Correct synthetic 50-row candidate passes the independent matrix validator;
  every count, per-ID category/risk/journey/difficulty, tag family/vocabulary, journey/turn, suite
  expression/attempt/pin/identity and subset error independently fails.
- Same aggregate counts with swapped case categories/risks/journeys/difficulties still fail. Missing
  human cases/obsolete smoke membership fail; permitted smoke/variance overlap
  passes. Matrix expectations cannot be supplied by the candidate dataset.
- All-row input/assertion/semantic validation precedes filtering and target calls.
  Literal historical-prompt reuse fails; no semantic guarantees are invented.
- Capture uses uniform deterministic scoring and zero semantic calls. Target
  request bytes and sessions remain isolated under evaluator metadata changes.
- Requested target freeze and observed trace metadata are distinct, detached,
  finite safe snapshots; mismatch/unknown reports do not fabricate provenance.
- Primary preparation has exactly 12 protected sources; 38 others may be judged
  independently. Failed responses stay ERROR and cannot be substituted.
- Variance selects the exact 10 IDs, three isolated attempts each; completed
  attempts remain individually selectable for prospective fixed-input repeats.
- Delayed join rejects wrong attempts/results/configs/receipts, retains independent
  successes and four verdicts, handles pending/missing separately, shows critical
  failures, and leaves original RunResult bytes unchanged.
- Category/risk partitions, overlapping tags, null metrics without evidence,
  context-aware comparisons, safe rendering and explicit diagnostic exclusions.
- CLI import/help/preview/validation cannot create clients; explicit live gates
  are tested offline. No actual study dataset is required by normal tests.

Future implementation validation commands (not executed during planning):

```sh
.venv/bin/python -m pytest tests/test_prospective.py tests/test_prospective_io.py tests/test_output_contracts.py tests/test_replay.py tests/test_calibration.py tests/test_calibration_io.py tests/test_calibration_reporting.py tests/test_rubric_judge.py tests/test_case_fingerprints.py
.venv/bin/python -m pytest tests/test_salesagent_study.py tests/test_study_reporting.py tests/test_suites.py tests/test_salesagent_target.py tests/test_salesagent_baseline.py tests/test_salesagent_semantic.py tests/test_salesagent_judge_replay.py tests/test_salesagent_human_calibration.py tests/test_grouping.py tests/test_comparison.py
.venv/bin/python -m pytest
.venv/bin/ruff check src tests examples
.venv/bin/mypy src
git diff --check
```

Run focused tests at the corresponding milestone; run full/static acceptance
before completion because shared scorer/calibration configuration changes affect
historical identities. Never update expected legacy hashes to make failures pass.

## M. Manual offline acceptance

1. Re-read approved plan/methodology; verify methodology committed/approved and
   hash pinned above. Check worktree and protected-file inventory before edits.
2. Generate/pin any additional synthetic historical compatibility material before
   changing shared configuration/model behavior. No private artifacts in fixtures.
3. Capture two synthetic responses with a deterministic fake target, with no
   semantic scorer. One request is human-protected, one unprotected. After capture
   replace the target with a raising sentinel so reuse would fail immediately.
4. Prepare/store/reload prospective plan and inputs with a raising judge; verify
   source, prompt/evidence and intended output contract hashes. Export blank
   review packet. Attempt execution before freeze and with wrong/partial bundles;
   verify zero judge calls and no changes to capture artifacts.
5. Use clearly synthetic test annotations only, freeze/reload receipt, then
   execute a scripted fake judge. Verify the exact previously prepared prompt,
   reserved observation ID, freeze provenance and successful immutable join.
6. Repeat with off-anchor output 0.7, malformed output, timeout and persistence
   failure. Confirm ERROR/no-score, retained deterministic evidence, no automatic
   retry and explicit unresolved-reservation handling where relevant.
7. Try every drift/mismatch and a duplicate invocation; verify rejection before
   calls. Run a diagnostic repeat with parent binding, proving no target calls
   and no replacement of the primary judgment.
8. Exercise the independently reviewed matrix with disposable synthetic 50-row
   candidates and all six suite definitions in a temporary test directory. Check
   exact counts/selectors, new smoke disjointness and malformed unselected rows.
9. Exercise three attempts on ten synthetic selections and grouped/combined
   analysis. Confirm original source JSON unchanged and pending semantic evidence
   is not labelled a completed primary PASS.
10. Run tests/static checks; verify historical model-dump identities and optional
    local read-only replay/calibration checks without invoking any judge. Recheck
    every protected byte hash. Inspect final diff for accidental datasets/live
    artifacts or fixture/hash rewrites; record actual outcomes here.

## N. Backward-compatibility guarantees and protection values

Existing v1/v2 case algorithms, default nullable-field omission, legacy dataset
loaders, full/hash-only policies, historical replay checks and calibration human
bindings remain unchanged. No frozen artifact acquires new keys automatically.
Generic continuous judging and legacy semantic pack outputs remain valid.
Opt-in contracts/new prospective artifacts are supported by new readers only;
older readers must reject or avoid rewriting them. No SQL migration is planned.

| Protected file | Byte SHA-256 | Legacy case hash |
| --- | --- | --- |
| `datasets/salesagent/baseline.jsonl` | `f24ffe05b08d75848860f71ef726cf96dccb78e457e5757fb7144cd30db4a747` | `c1a73ef207f2cabe3292d743504f7249f4729825d785adff5b6bf14ad6a7b12b` |
| `datasets/salesagent/semantic.jsonl` | `3200acd541c6db9f3bb3301186f4213746e177c0c3048b4ad99434da590791a9` | `33654c3f4870efc67edd8e30a6ae0a82c17eb58c8c30cb323add5d0efe414849` |

Pinned synthetic legacy fixture byte SHA-256:
`5818ce99cec46d4ec82095b7a6e9eb11685a8537248cff8eae2419e95dd49e4b`.
Planning rechecked all 23 locally inventoried dataset/run/replay/calibration/
fixture files against the previous milestone inventory; none changed. Regenerate
only an inventory of existing bytes before implementation, never the artifacts.
Private local files remain optional read-only acceptance, not CI dependencies.

## O. Failure and rollback rules

A legacy hash/binding/serialization mismatch blocks the milestone. Diagnose and
fix the new code or revise the plan; never rewrite human bindings, old source
configs or golden hashes. Missing source/evidence/configuration/receipt fails
before judge calls. Actual judge/target failures remain recorded ERROR; incomplete
capture is never treated as a successful partial response.

No implicit paid retry or target rerun is permitted. On failed persistence retain
the complete in-memory result and original reserved ID for an explicit save-only
retry. An ambiguous crash leaves an execution reservation, not an invitation to
call again. Existing artifacts/destinations are never overwritten to recover.
Human corrections use existing new-revision/supersession rules and truthful
exposure; do not alter old frozen bundles or admit post-disclosure labels as blind.

Rollback uses reviewed normal feature reversions. Keep new immutable artifacts
and original source files; no delete/reset/rebase/force-push or SQL restoration.
Older tooling must not resave prospective/anchor-enabled material. Return to
legacy recipes only with their unchanged legacy contracts. Do not disguise an
anchor-enabled or prospective result as a historical artifact.

Methodology drift requires explicit reviewed amendment before implementation of
that change. A change to the approved smoke/matrix, rubric, threshold, anchor
meaning, protected roster or call policy is not a routine implementation choice.
Routine API details within this plan are recorded in its decision log. Material
new storage/calibration/target architecture requires stopping and explaining the
conflict rather than extending scope silently.

## P. Explicit non-goals

No 50-case authoring, shopper wording, assertions or semantic expectation writing;
no real study dataset/descriptor/suite files; no live target/judge runs; no target
changes; no rewrite of taxonomy/selection/suite architecture; no per-case scorer
dispatch; no changes to historical semantic rubric/prompt/threshold or fixtures;
no hidden scorer-result fabrication; no target rerun to obtain judge evidence;
no human rating generation; no changing freeze/correction semantics; no global
human gate on replay; no statistical calibration claim or new regression gate;
no UI, scheduler, remote service, dynamic registry, generic redaction framework,
new database tables or broad report redesign.

## Q. Milestone sequence and implementation review decisions

**Milestone 1 — prospective blind judging and explicit output validation.**
First pin legacy fixtures. Implement optional output-contract serialization/
validation with the default path unchanged. Implement shared verified-source
extraction, prospective plan/request/result bundles, reserved identities,
receipt-gated execution and calibration integration. Test the full synthetic
capture-to-human-freeze-to-judge-to-analysis path with no target re-execution.
Document generic semantics and reader compatibility in ADR 0007. Exit only when
all drift/receipt/anchor tests and historical golden bindings pass. Do not begin
Study v1 live work; this milestone supplies generic mechanics and no study data.

**Milestone 2 — Sales Agent Study v1 integration.**
Transcribe and independently review matrix metadata, implement study validator,
profile factories, explicit target freeze and two-stage orchestration, then the
immutable delayed-evidence analysis join and thin command recipe. Use disposable
synthetic candidates and mocks. Update adoption documentation with actual command
syntax only after implemented. Exit only after required counts, revised smoke,
blind ordering, 10-by-3 variance, scope guards and full compatibility/static
checks pass. The slice ends here; final case authoring needs separate approval.

Implementation-review decisions proposed here:

- Separate prospective model/kind instead of fabricated historical configuration.
- Existing human receipt envelope/semantics with a strictly discriminated new
  preparation branch; actual-call proof remains `frozen_request_verified`.
- Preallocated observation IDs and exclusive local execution reservations rather
  than retrospective relabelling or exactly-once claims.
- New semantic profile/output-contract version, stable scorer/rubric/projection
  names and bytes, opt-in anchor validation; no change to legacy continuous scores.
- Separate JSON prospective artifacts and derived analysis; source RunResult and
  SQL schema unchanged. Explicit complete protected-roster freeze is required.
- Full source payload persistence for this study, while generic defaults remain
  hashes-only; safe metadata remains independently reviewed and allowlisted.
- Uniform deterministic capture followed by fixed-response semantic judging,
  with explicit pending/completion state and diagnostic separation.

Planning validation: checked approved committed methodology and its exact hash,
50 matrix rows/risk totals and revised smoke/human disjointness; rechecked 23
protected artifact hashes read-only. Reviewed scorer preparation/configuration,
replay validation, calibration model/receipt/report boundaries and existing
suite/store interfaces. No code tests, execution clients, target/judge calls,
case authoring, artifact writes or implementation occurred. Only this document
was created; implementation results belong below after approval.

Plan-only validation passed: all sections A–Q are present, fenced blocks are
balanced, local links resolve, and whitespace checks pass. Reconfirmed the
methodology bytes equal the committed document, all 23 protected hashes are
unchanged, no tracked files were modified, and the study dataset directory
remains absent. The implementation test commands above have not been run.

## Milestone 1 implementation log — 2026-10-05

Created `feat/salesagent-study-v1-readiness` from integrated main
`fa1db065a9446ac300ab3ae99761eb7fa36f22af`. Committed the user-supplied exact
journey/difficulty assignments as `5995e24d59d3e5795df0429a940f01a638974dd3` before code changes.
Converted matrix rows to Markdown tables without changing scenario/risk/V/H
values. Verified 50 unique IDs, approved counts and unchanged subsets. The
independent matrix-contract design now requires all four exact per-ID fields.
The matrix resource/validator remains Milestone 2; no case data was authored.


Before source edits, generated `tests/fixtures/prospective/legacy.json` from the
pre-change code with synthetic source/replay/calibration data and no calls.
Pinned SHA-256:
`1a5e209688f781fb27ed1ab0ff90d09a1441b71f2b7dac87a6624b5cc694e7b8`.
The fixture pins exact compact model JSON, model fingerprints, continuous 0.7
parsing and unchanged scorer configuration. Existing taxonomy fixtures were not
modified. The pre-change focused compatibility check passed 394 tests.

Implemented generic `ScoreOutputContract`, optional judged scorer validation,
shared source verification, immutable prospective plan/selection/request/result
models, guarded execution and local checksummed bundles. Calibration accepts an
explicit prospective preparation/policy and joins its verified reserved result;
existing source/replay/calibration models retain their old serialization. No
changes were needed in calibration I/O, SQLite schema or legacy recipes.

Implementation choices within the approved architecture:

- Requests embed their complete immutable plan and record its digest. Source,
  evaluator, observation and attempt properties derive from the selected plan
  entry rather than duplicate mutable fields. Canonical response/attempt bodies
  retain exact snapshots; loaded attempts are detached and coercions rejected.
- `sharing_policy="evaluation_data"` is an explicit acceptance of private full
  normalized response/evidence snapshots. Source TestCase payload policies stay
  unchanged. The core owns no Sales Agent anchor/category/matrix values.
- Preparation uses a pure scorer with a raising judge. Execution receives a
  source-loader callback, a verification scorer and a deferred `ProspectiveJudge`
  factory. The factory is called only after source/input, complete human receipt
  and reservation checks. Its actual scorer/projection/settings are verified
  again before judging; prompt/configuration checks run at each call boundary.
- Registration claims request and observation IDs exclusively before review.
  Execution claims a separate start record. Local artifact directories publish
  `document.json` before `receipt.json`; incomplete bundles fail loading.
  Execution returns its complete result; saving is explicit, allowing save-only
  recovery to an unused destination. An ambiguous reservation never retries.
- Protected diagnostics use a new plan/request/observation and the original
  request as parent. They preserve source/evidence/evaluator/protection and use
  the original complete human receipt; they cannot join as primary observations.
  Parent chains are intentionally limited to the original request.
- Default rubric evidence cannot claim taxonomy exclusion. Custom projections
  remain integration-owned/reviewed, following existing suite contract checks.
  Anchor validation is opt-in and does not rewrite legacy rubric/prompt bytes.

Validation performed offline (no target/judge service, credentials or installs):

```sh
.venv/bin/python -m pytest tests/test_prospective.py tests/test_prospective_io.py tests/test_output_contracts.py tests/test_replay.py tests/test_calibration.py tests/test_calibration_io.py tests/test_calibration_reporting.py tests/test_rubric_judge.py tests/test_case_fingerprints.py
```

Result: **523 passed**. Includes the complete blind synthetic workflow, all five
anchors and malformed/off-anchor ERROR semantics, strict artifact integrity,
pre-client freeze/source/policy rejection, v1/v2 full/hash-only sources, exact
legacy golden serialization, concurrent reservation exclusion, diagnostic parent
protection and save-only recovery. No synthetic rating is a real human finding.

Final full/static and read-only acceptance results are recorded below.

Final acceptance:

- `.venv/bin/python -m pytest`: **1,200 passed** (2.59 seconds).
- `.venv/bin/ruff check src tests examples`: **passed**.
- `.venv/bin/mypy src`: **passed**, 36 source files.
- `git diff --check`: **passed**; new-file whitespace and documentation links
  also checked locally. No additional repository Markdown checker is configured.
- Read-only local integrity probe: all **23 protected byte hashes unchanged**,
  including both frozen datasets, all protected replay/calibration files and the
  earlier taxonomy golden fixture. Both legacy ordered case hashes remain the
  exact constants in section N.
- Reloaded the two stored replay artifacts. Rebuilt and matched all **18** saved
  observation bindings in each of the two historical calibration analyses;
  frozen annotations, derived summaries, reports and appendices still validate.
  No provider was constructed/invoked and no report/artifact was rewritten.
- Rechecked committed preregistration bytes and new SHA-256. All **50** original
  IDs/scenarios/risks/V/H cells remain unchanged. Counts: journey **30/20**;
  difficulty **18/19/5/8**; risk **12/18/15/5**; category sizes
  **8/7/6/7/6/6/5/5**. Variance **10**, human **12**, smoke **8** memberships and
  all execution-policy text are unchanged. The amendment adds a final newline;
  it does not change any study decision beyond recording the supplied values.

A final review added regression tests for non-finite source-builder mutations
that could otherwise serialize as null, Boolean persisted-score coercion,
cleanup failure and diagnostic protection drift. The full/focused results above
include these checks. Early test-development failures were corrected; no golden
hash, historical artifact or human binding was changed to make tests pass.

No material architecture deviation. Concrete function signatures and bundle
layout are documented in `docs/prospective-judging.md` and ADR 0007. Expected
limitations remain explicit: a workflow cannot prohibit out-of-band provider
calls; a crash after reservation can leave ambiguous execution; custom projection
privacy is an integration responsibility; and source cases are independently
required when a run lacks complete reconstructible material. No release version
is assigned yet; reader feature/schema requirements are documented.

**Milestone 1 complete. Stop here.** Milestone 2, its matrix resource/validator,
Sales Agent profile/target-freeze wiring, combined study analysis, Study v1 case
authoring and live execution remain unstarted. Only the preregistration amendment
was committed; implementation and this living plan are left for review on
`feat/salesagent-study-v1-readiness`.
