# Fixed-response replay / judge-only variance

This ExecPlan was **approved for Milestones 1–4 on 2026-09-26**, including
architectural decisions 1–5. Use the existing
`feat/judge-replay-calibration` branch for this slice; integration is
`codex-evaluation`. Do not make live judge/target calls, change Sales Agent or
datasets, rewrite historical runs, or merge. Keep this document current.

Approval clarifications: persisted source locators and stdout must be share-safe
(logical or repository-relative, never absolute local paths). Absolute paths
are execution-only. Prepared evidence/prompt snapshots contain shopper/assistant
evaluation content and must be treated as evaluation data. Allowlists exclude
known operational/raw/provider fields; they cannot guarantee arbitrary natural
language contains no sensitive information.

## Purpose and acceptance

Answer: “Given exactly the same target response and evaluator evidence, how
stable is the judge?” Select one persisted run/case/attempt, verify its dataset
and evaluator provenance, prepare one fixed judge input, and score it N times.
Reuse the existing judged scorer and provider boundaries. No target is accepted,
constructed, invoked, or queried for missing information.

The first supported scorer is `RubricJudgeScorer`; the mechanism must also work
with other `JudgedScorer` subclasses through the same preparation/scoring path.
One selected scorer and one source attempt per replay run keep the slice small.
Different source responses or controls require separate replay runs.

Acceptance requires independently persisted scores/errors, proof of identical
input across calls, explicit compatibility information, descriptive variance
statistics, a manual recipe, and offline tests. A replay PASS is a judgment of
this fixed response by the selected scorer, not a new whole-system quality
verdict and not a replacement for the source's deterministic gates.

## Progress

- [x] Inspect AGENTS.md, models, store, runner, dataset hashing, scorers, judge
  adapter, comparison, semantic pack/recipe, existing plan, and relevant tests.
- [x] Read persisted semantic runs using SQLite `mode=ro`; verify dataset
  matches and reconstruct evidence locally without invoking any judge/target.
- [x] Write repository findings, proposed design, validation, and approval items.
- [x] 2026-09-26: Implementation decisions 1–5 approved, with the two data-handling
  clarifications above. Live acceptance was not executed during implementation.
- [x] Milestone 1: prepared scoring and normalized failure observations. Initial
  focused scorer/provider/runner regression check: 103 passed. Full validation
  follows after replay integration.
- [x] Milestone 2: source verification, replay execution, and statistics.
- [x] Milestone 3: replay persistence and manual recipe. Read-only dry-run against
  `bbeb64511171` succeeded with the exact planned response/evidence/prompt hashes
  and repository-relative source locator; zero target/judge calls.
- [x] Milestone 4: complete offline validation and documentation; final results
  and implementation refinements are recorded below.
- [x] Manual acceptance complete: two live five-call replay results supplied by
  the user, including fixed-input score and verdict variation; recorded below.

## Repository findings

Inspected revision: `f6bed43585f9881750d44443bcdc21250c0ff74f`, clean worktree on
the requested branch before this plan. No additional ExecPlan template was found.
AGENTS.md governs branch workflow over CLAUDE.md's older `main` guidance.

| Component | Finding and implication |
| --- | --- |
| `core/models.py` | `RunResult.cases[].attempts[].response` holds the complete `TargetResponse`: output, contexts, trajectory, structured data, metadata, latency, cost, and legacy `raw`. Attempts have zero-based indexes. CaseResult retains ID/tags, not a complete TestCase. |
| `core/store.py` | SQLite stores `RunResult.model_dump_json()` in `runs.result_json` and rejects duplicate IDs. It does not drop response fields. Its constructor creates directories/schema and normal connections are writable; it is unsuitable as-is for strictly read-only source access. |
| `core/runner.py` | Every attempt calls `target.invoke` before scoring; wrapping saved responses in a StaticTarget would still use a target execution flow. Do not call `run` for replay. Existing error-first verdict semantics and `Score` remain applicable. |
| `core/dataset.py` | `hash_cases` hashes the ordered complete TestCase documents, including extra/provenance. A selected subset has its own hash. The full source selection, not just the replayed case, must match the source hash. |
| `scorers/base.py` | `JudgedScorer.score` validates requirements, builds the prompt, calls the injected judge, parses, and thresholds. There is no prepared-input entry point. JudgeReply observations are copied into Score.extra only after successful parsing; malformed judgment text loses otherwise available telemetry. |
| `scorers/rubric_judge.py` | Reusable rubric, parser and evidence-builder hook already exist. Prompt formatting and default filtering have no generic explicit version metadata. A pack builder replaces the default projection completely. |
| `judges/base.py` | JudgeReply is a strict frozen value containing text and optional observed model, tokens, latency and known cost. No mutable last-response state is needed. |
| `judges/openai.py` | Already sends independent requests with no previous-response ID/conversation, cookies, tools, automatic retries or provider storage. Safe config includes requested model, instructions/schema versions and request settings. Raw envelopes/reasoning are discarded. Cost is unknown. Preserve this behavior. |
| `regression/comparison.py` | Compares target RunResults by dataset, selected evaluator settings, model versions, and case/scorer metrics. A replay is a different experiment; do not force it into this comparison or report a target regression from its pass-rate delta. |
| Semantic pack | Versioned rubric, expectations, projection, prompt and judgment schema; existing factory produces a RubricJudgeScorer at threshold 0.7. Builder validates shopper/turn/final-output correlation and projects only semantic evidence. |
| Semantic recipe | Persists `resolved_cases` excluding extra, selected/full dataset hashes, ordered selection, full rubric in scorer snapshot, semantic configuration, judge settings and observations. Core runs generally do not have these recipe-specific additions. |
| Tests | Existing tests cover JSON/SQLite round-trips, duplicate IDs, independent scorer errors, strict parsing, safe telemetry, stateless HTTP requests, semantic allowlists and old/new configuration incompatibility. `conftest.py` blocks socket connections and DNS for the default suite. |

The generic default rubric filter is a denylist, not a guarantee that arbitrary
references/structured dictionaries are safe judge input. Replay must preserve
the existing Sales Agent allowlist and require a reviewed, versioned projection
contract for other replay scorers. It must never forward a whole saved run,
source scores/verdicts, credentials, hidden prompts, raw envelopes or assertions
merely because they were persisted.

### Persisted evidence inspection and sufficiency

Read `runs/salesagent-semantic.sqlite` directly with a read-only SQLite URI,
without constructing SQLiteResultStore or a network client. Six run documents
were loaded through RunResult validation. All six selected dataset hashes match
the current frozen dataset selected in source case order.

| Source run | Observation |
| --- | --- |
| `a68ace7dd819` | Three cases, three attempts each, semantic evidence v2. `sales-discount-override` scores are 0.8 / 0.6 / 0.8. Its three normalized response hashes **and three projected evidence hashes differ**. This cannot isolate judge variance. |
| `bbeb64511171` | Post-fix candidate, 14 cases, one attempt each. Override, summer20 and welcome10 responses all rebuild successfully with the current v2 semantic builder. Raw is empty; normalized per-turn commerce, constraints and tool facts are present. |
| Other stored runs | `55344c3d1dbd` and `c929629bc0a0` use projection v1; `6c7f864209bd` and `71724f5ec996` use v2. Do not silently upgrade old evidence or claim v1/v2 compatibility. |

For the repeated run and post-fix candidate, `resolved_cases` exactly match the
selected frozen TestCases with extra excluded. Saved score observations contain
observed model, input/output/total tokens and latency; cost is absent. Saved
judge configuration is OpenAI, requested model `gpt-6-sol`, output limit 2048,
timeouts 5/120/10/5 seconds, no retries, response schema `score-reason-v1`.
These are recorded historical settings, not a claim of current model availability.

**Existing response persistence is sufficient. No TargetResponse or historical
RunResult migration is needed for this use case.** The replay needs evaluator
inputs in addition to the response: verify the frozen dataset as described
below. Do not reconstruct missing response fields from APIs, traces, catalogue
files or newer attempts. A missing/incomplete source is ineligible.

Generic runs need a supplied dataset matching their recorded selection hash;
they need not acquire new embedded TestCase fields in this milestone. If that
dataset is unavailable, replay cannot proceed. If source evaluator versions
were never recorded, matching configuration cannot be proven: fail strict
compatibility or explicitly label a new-configuration experiment. Future live
scorer snapshots should record the new explicit preparation versions through
the existing config_snapshot mechanism; no database schema migration is needed
to enrich future run JSON. Historical provenance remains unknown.

Inspection fingerprints (SHA-256; response/evidence use UTF-8 JSON, sorted keys,
compact separators, ensure_ascii=False, allow_nan=False; prompt uses exact UTF-8):

| Artifact | Fingerprint |
| --- | --- |
| Semantic dataset, existing `hash_cases` algorithm | `33654c3f4870efc67edd8e30a6ae0a82c17eb58c8c30cb323add5d0efe414849` |
| Post-fix override, attempt index 0, complete response | `665fdaccd010a4c1114f6b7e018ca388dac57ebb559aa2a14e07eaaa20579b12` |
| Its projected semantic evidence | `776289ca3a733a5ea4e47212e169222d337278020dd1cab9f2a1f37b438435c9` |
| Its rebuilt current rubric prompt | `777b793d0a57c48f0ef928cc8b389cc0e7ef8f88eb3842214519394f6d59d16e` |
| Source SQLite file before/after inspection | `293156e08238d03658fbe73199a853a033d703fbb20db9c64a0b18271a77da67` |

Historical judge prompt bytes were not stored. Matching recorded versions and
rebuilding with the corresponding code supports configuration compatibility;
it is not direct proof of the bytes sent in the historical request. Replay will
prove byte identity **between its own calls**. Do not overstate that distinction.

## Proposed models and files

Keep provider imports outside core. Introduce a small replay module using the
existing Score, Verdict, TestCase, TargetResponse and JudgedScorer types.

| File | Proposed responsibility |
| --- | --- |
| `src/harness/core/replay.py` (new) | Source selector, verified replay input/provenance, ReplayAttemptResult, ReplayResult, compatibility validation, synchronous replay and derived variance summary. No target import/client or provider branch. |
| `src/harness/scorers/base.py` | Add immutable prepared judging input and `prepare(case, response)` / `score_prepared(prepared)`; make existing `score` delegate to this path. Preserve subclass build_prompt/parse_judgement and callable compatibility. |
| `src/harness/scorers/rubric_judge.py` | Expose versioned evidence preparation/formatting without changing prompt bytes; use one builder execution to produce frozen evidence and prompt. Keep one numeric parser/thresholding implementation. |
| `src/harness/judges/base.py` | Factor safe JudgeObservation fields from JudgeReply without breaking its existing fields/serialization; define a safe scoring failure carrying optional observations, never raw judgment text. |
| `src/harness/core/runner.py` | Only additive scorer snapshot fields for explicit preparation versions/config when available. Do not change target execution, verdict or aggregation semantics. |
| `src/harness/core/store.py` | Explicit read-only opening plus separate replay save/load/list methods and replay table; preserve current run save/load behavior and historical documents. |
| `src/harness/packs/salesagent_semantic.py` | Bind existing factory to explicit preparation metadata. Keep current rubric, threshold, evidence content and versions unchanged if bytes are unchanged. |
| `examples/salesagent_judge_replay.py` (new) | Select verified source/dataset, normalize recipe-specific source configuration, construct existing scorer/judge, invoke generic replay and report/save. Never call or import the live semantic recipe's evaluate/main. |
| `docs/judge-replay.md`, `docs/adr/0004-fixed-response-replay.md` (new) | Public API, source eligibility, semantics, boundaries, manual procedure and design decision. |
| Tests | New `test_replay.py` and `test_salesagent_judge_replay.py`; focused additions to store, rubric/base, provider and snapshot regression tests. |

Names may be refined during implementation; materially different boundaries
require updating this plan before proceeding. No generic plugin registry,
multi-scorer scheduler, CLI framework or alternate semantic engine is needed.

Proposed ReplayResult schema, explicitly versioned `judge-replay-v1`:

- New replay ID, kind `judge_replay`, start/finish times, requested N.
- Source provenance: share-safe database locator, source run ID, case ID, stored
  attempt index, source result-document hash, full normalized response hash,
  source dataset/selection hashes, selected case/input hashes, relevant evidence
  schema and target identity/version context. No wholesale config copying.
- Verified dataset selection/case identity and explicit safe evaluator config;
  source config snapshot limited to comparison fields, compatibility status and
  field-level differences/unknowns.
- One frozen prepared input: safe projected evidence for rubric scoring and
  exact evaluator prompt, with their hashes and schema/version. No entire
  source response/config/Score is copied to the replay database. The unchanged
  response remains in its source store; its hash links it to this artifact.
- Ordered replay attempts: zero-based index, score or null, verdict, safe error
  category/message or null, safe observations, start time/duration, actual prompt
  hash and replay-input hash. Judge latency is separate from attempt duration.
- Derived descriptive summary, recomputed from attempts on reload rather than
  accepting independently mutable aggregate values as truth.

Prepared inputs must contain immutable strings/scalars (canonical JSON strings
for nested content); frozen Pydantic objects alone do not freeze nested dicts.
The prepared record binds the scorer/config fingerprint and local threshold.
Score-prepared rejects a mismatching scorer configuration before any judge call.

## Exact data flow and isolation

1. Validate explicit selectors and N (positive integer; reject bool/float),
   source existence and output path. Open source read-only with no directory or
   schema creation. Use a coherent SQLite read transaction and load one run.
2. Find exactly one case and exactly one attempt by its **stored index**, not
   array position. Reject duplicates, missing IDs, negative indexes, absent
   responses and invalid documents. A source ERROR with a complete response
   after a scorer failure may be replayed; a missing target response may not.
3. Verify dataset and source compatibility before creating a live judge client.
   Load/validate the frozen dataset, derive the original ordered selection and
   prove `hash_cases(selection) == source.dataset_hash`. Verify full_dataset_hash
   and selection/resolved_cases when present; contradictions are errors. Match
   the selected case ID/input/reference/tags to the stored resolved case, if
   available. The dataset hash verifies extra too, despite its omission there.
   For generic runs, source case order plus the matching complete selection hash
   binds the supplied TestCase; tags must also agree. Do not rely on ID alone.
4. Compute the complete persisted response hash and copy the response for local
   preparation. Preserve output, null/empty distinctions, structured values,
   contexts, ordered trajectory, telemetry and metadata. Never synthesize missing
   facts or replace output with the current target's answer. Check required
   fields directly on the stored response, then let the scorer validate its
   projection. A declared capability alone does not prove evidence is present.
5. Prepare once using the verified TestCase and exact copied TargetResponse.
   Rubric preparation runs its versioned evidence builder once, freezes the
   resulting canonical JSON, and formats the existing prompt. Other JudgedScorer
   subclasses freeze their build_prompt output through the same base hook;
   their exact prompt is the effective input even without separate JSON evidence.
   Require an explicit reviewed input projection/version contract for replay.
6. Verify source/case hashes did not change during preparation; discard mutable
   copies after freezing. No source scores or deterministic results are passed
   into preparation. Bind prompt, evidence, rubric/schema/versions and safe
   judge configuration into the replay-input fingerprint.
7. Invoke `score_prepared` N times sequentially. Each invocation receives the
   identical immutable prompt and fixed configuration. Use the existing parser,
   threshold and Score creation. Record the fingerprint of the actual prompt at
   the judge-call boundary, not just an expected hash copied into N records.
   A changed prompt/config is an integrity error and cannot be sent as a normal
   fixed-input attempt. No regeneration, hidden retries or source-score reuse.
8. Each successful call records a fresh Score. Provider/parse failures produce
   ERROR with no Score, never zero. Continue independent attempts after ordinary
   judge failures; preserve earlier successes. Record safe known observations
   even when parsing fails. Summarize, save a new replay ID, reload, and verify
   document equality and summary/fingerprint consistency.

N independent calls here means stateless requests with no previous judgments,
conversation identifiers or mutable last-response slot. It does not establish
statistical independence of a provider's service. Reusing a transport pool is
permitted; no conversational state/cookies may be sent. Injected custom judges
must honor this contract; core cannot prove arbitrary callable internals safe.

The current OpenAI adapter needs no new conversational mechanism. Extend its
MockTransport tests to assert N identical request bodies and no replay/source
IDs, previous-response IDs, cookies or target credentials. Provider response IDs
and raw output must not become replay state.

## Fingerprints, configuration and compatibility

Define and persist `replay-canonical-json-v1`: SHA-256 of UTF-8 JSON with sorted
object keys, compact separators, ensure_ascii=False and allow_nan=False. Preserve
list order, exact strings and nulls; do not trim prose, round numbers, normalize
Unicode or coerce decimal strings. Reject non-JSON/non-finite evidence. Keep
existing dataset hashing unchanged and label its distinct algorithm explicitly.

Separate hashes answer separate questions:

- Source result-document hash binds the selected stored document; database path
  plus run ID identifies where it came from. A database file checksum may be
  recorded for manual audit, but appending unrelated runs is not evidence drift.
- Full TargetResponse hash proves source identity, including safe operational
  metadata; it is not the judge-input hash. Judge projection excludes that
  operational material.
- Case/input hashes bind the verified evaluator inputs and original user input.
- Evidence hash binds the projection; prompt hash binds exact scorer UTF-8 text.
- Replay-input hash binds prompt/evidence hashes, scorer/config/schema versions,
  rubric/threshold and provider/model/settings. Exclude timestamps, output
  telemetry, replay IDs and source verdicts. Store the fingerprint payload schema
  so hashes are independently reproducible.

Explicit evaluator configuration records scorer name/kind/requirements, full
rubric plus version, threshold, evidence-builder version, prompt-template
version, judgment schema/version, provider adapter/instruction version,
requested model and supported request settings (including omitted/default
sampling settings as unspecified, never invented values). Credentials are
constructor-only. Provider settings use a safe allowlisted schema, not an
arbitrary object's __dict__, environment snapshot or callable repr. Bind declared
settings to the actual adapter configuration before execution.

The Sales Agent helper maps its existing `semantic_evaluation` and scorer entry
into this neutral configuration; core never recognizes Sales Agent keys.
Like-for-like mode is the default: mismatched or unknown relevant source fields
reject before calls. Compare only the selected scorer's evaluator configuration;
the source's other scorers and number of fresh target attempts do not need to
match the number of replay calls.

Offer one explicit `allow_reconfigured` mode for experiments with a changed or
previously unrecorded judge/rubric/projection configuration. It records differences
and labels source compatibility `different` or `unknown`, never like-for-like.
It cannot bypass dataset mismatch, malformed/missing evidence, unsafe input or
unsupported versions. New expectations in a changed dataset are out of scope.
Within either mode all replay calls use one fixed, complete configuration.

Requested model aliases may resolve differently later. Record observed model per
call, list distinct observed models, and flag source/replay observed-model drift
separately from requested-configuration compatibility. If observations are
missing, say unknown; if multiple models appear, qualify the variance as judge
service/configuration variation rather than stable-model sampling alone.

## Safe observations and ERROR semantics

Reuse JudgeReply's strict observation fields: observed_model, input_tokens,
output_tokens, total_tokens, latency_ms, cost_usd. The normalized observation
value excludes text and arbitrary extra fields. Successful Score.extra remains
backward compatible. A typed scoring error can carry the same observation value
when the provider returned a valid JudgeReply but its text could not be parsed.
Never preserve malformed text to recover telemetry later.

If the provider fails before observations are available, keep those fields null;
the replay layer still records elapsed attempt duration. Do not read observations
from a previous attempt. Keep existing string-returning fake judges working with
unknown provider telemetry. Avoid broad exception-string persistence: unexpected
scorer errors become fixed safe categories, without repr/traceback/provider body.

Validate score name/kind, finite [0,1] value and threshold-derived passed value.
PASS/FAIL follow the one selected gated Score; informational Score uses SKIP.
ERROR always has no quality Score in this single-scorer workflow. Successful
attempts survive any later errors. Upfront invalid selectors/dataset/config or
missing response are clear preflight errors with zero judge calls, not fabricated
N score attempts. A replay that starts execution retains all N attempt outcomes.

Keep target latency/cost solely as source provenance. Judge call latency and
attempt duration are fresh measurements. Unknown costs stay null; any total
reports known subtotal and completeness/counts, never implies missing is free.
Do not use RunResult.total_cost_usd for replay billing.

Source raw/provider/hidden fields must never be copied into prepared inputs,
errors or the replay artifact. Use reviewed projection allowlists, not generic
secret scrubbing that silently changes evidence. An unsafe projection is rejected.
Arbitrary user prose is still untrusted text; sentinel tests prove field boundary
exclusion, not a universal ability to identify secrets inside natural language.

## Descriptive variance semantics

Derive statistics from completed valid Scores only; ERROR is excluded from all
quality denominators and always reported separately. Retain attempt order with
`scores_by_attempt` containing null at ERROR positions; optionally also show the
ordered successful values. Never silently remove failed calls from the report.

| Field | Definition |
| --- | --- |
| requested_attempt_count / attempt_count | Requested N and number of recorded outcomes; completed normal execution has N of each. |
| completed_score_count / error_count / skip_count | Valid Scores, execution failures, and informational verdicts. |
| mean, min, max, range | Successful values only; all null if none. Range = max − min. |
| population_stddev | Descriptive standard deviation over observed successful scores (`statistics.pstdev`); null for none, zero for one. Not a population inference or confidence interval. |
| pass_count / fail_count | Based on Score.passed at the recorded threshold; equality passes. Informational scores excluded. |
| pass_rate | pass_count / (pass_count + fail_count), null when denominator is zero. |
| threshold_crossing | True if both PASS and FAIL observed; false if gated judgments exist on only one side; null if no gated judgments. |
| insufficient_repeats | True when fewer than two valid scores; a one-score zero range does not establish stability. |
| error_rate | error_count / attempt_count; defined safely for an empty intermediate summary. |

For `[0.8, 0.6, 0.8, 0.8, 0.6]` at 0.7: mean 0.72, min 0.6, max 0.8,
range 0.2, population standard deviation approximately 0.09797959, 3 PASS,
2 FAIL, pass rate 0.6, threshold_crossing true. Scores can vary without crossing
the threshold; identical scores can consistently fail. Show both facts without
inventing an acceptable-variance cutoff, aggregate release verdict or significance
claim. Round only for presentation; retain all original numeric Scores.

Stable source/evidence/config hashes and per-attempt reasons permit later human
rating joins and model-versus-human analysis. Do not add labels, agreement metrics
or annotation UI now. Keep designation `provisional_uncalibrated`; the existing
score_labelled hook and the plan filename do not establish calibration.

## Persistence and comparison strategy

Add a read-only mode to SQLiteResultStore that opens an existing file through
`mode=ro`, performs no DDL/mkdir, and rejects save methods. Existing writable
behavior and `runs` schema remain compatible. Add a separate `replays` table
with replay ID, source run/case/index, response/input fingerprints, start/finish
times and complete versioned result JSON; indexed provenance supports later
listing without JSON scans. Reject duplicate replay IDs; never use replace/upsert.

The first recipe writes to `runs/judge-replay.sqlite`, distinct from the source
database. Reject equal resolved paths and same-file aliases/hardlinks so replay
cannot modify the source database even accidentally. Historical runs are never
migrated, enriched or rescored in place. Test source file/document checksums,
read-only write rejection, reload equality and duplicate-ID preservation.

The new artifact type prevents target-run list/comparison from treating replay
attempts as new target executions. Do not extend compare_runs into a generalized
experiment comparison. The replay report shows source compatibility/differences
and descriptive statistics directly. If a user compares two replay artifacts,
require equal response/evidence/config hashes before calling them the same
fixed-input experiment; differing N affects sample size, not input identity.

Save the completed artifact after per-attempt failures have been captured, then
reload before printing success. A persistence failure is an operation error,
never a successful saved replay. Follow existing end-of-run persistence:
process interruption/crash recovery and incremental checkpoints are out of scope;
do not claim durable preservation of an abruptly killed in-memory run.

## Implementation milestones and validation

1. **Prepared scoring boundary.** Implement preparation, immutable input/config
   binding, shared score parsing and safe error observations. Verify ordinary
   score(case,response) retains existing prompt bytes, outcomes, telemetry and
   independent-scorer behavior. Add a non-Sales-Agent JudgedScorer test proving
   this is generic. Add explicit version snapshots for future runs.
2. **Replay engine.** Implement strict source/dataset/config verification, hashes,
   sequential fixed-prompt scoring, isolation and deterministic statistics. Use
   fake judges only. No target wrapper or live runner invocation.
3. **Store and recipe.** Add read-only sources, separate replay persistence and
   save/reload verification. Implement dry-run preparation/reporting before any
   client construction, plus explicit live judge opt-in. Add safe human/JSON
   summary, API/operator documentation and ADR.
4. **Acceptance checks.** Run the focused and complete offline suites, lint,
   types and scoped formatting, verify frozen datasets/source DB unchanged,
   document results and deviations here. Prepare but do not execute live proof
   until separately invoked by the user.

Required offline matrix:

- A bomb target/runner/target HTTP factory proves none is constructed/invoked;
  fixture source creation and replay execution are separately counted.
- Exact persisted response reuse with nested/multi-turn evidence, null/empty
  fields, order and source object/serialized document unchanged.
- Deterministic hashes under mapping-key reorder; sensitivity to changed prose,
  reference, facts, list order, rubric/config; non-finite/non-JSON rejection.
- N calls with identical actual prompts/request bodies; no previous-response ID,
  cookies, conversation or observation leakage; builder called once.
- Ordered mixed PASS/FAIL, equal-to-threshold PASS, range without crossing,
  crossing, all PASS, all FAIL, one score, all ERROR, empty summary guard,
  informational SKIP, deterministic numeric statistics with approximate float checks.
- ERROR between successful calls, provider timeout/failure, malformed output and
  malformed telemetry; preserved observations on parse errors; no raw exception
  or output leakage and no retry/source-score reuse.
- Missing database/run/case/attempt, duplicate selectors in malformed source,
  missing response, old evidence missing required fields, capability mismatch,
  invalid N and bad dataset rows with file/line diagnostics.
- Changed dataset/selection/case/input/reference, unknown/mismatched evaluator
  config; strict rejection and explicit reconfigured labeling; no client/calls
  before failed preflight; observed-model drift/unknown reporting.
- JSON/SQLite round-trip, duplicate replay IDs, read-only source writes rejected,
  nonexistent source not created, same-file destination rejected, save failure
  not reported as success, source DB unchanged, existing run comparison unchanged.
- Secret/raw/hidden-prompt/assertion/verdict sentinels at preparation, HTTP,
  error, result, stdout and persistence boundaries. Import/dry-run/main opt-in
  isolation using fake judges/MockTransport and the normal network blocker.

Validation commands:

```sh
UV_OFFLINE=1 uv run --frozen --extra salesagent --extra judge-openai pytest -q tests/test_replay.py tests/test_salesagent_judge_replay.py tests/test_store.py tests/test_rubric_judge.py tests/test_openai_judge.py tests/test_runner.py tests/test_comparison.py tests/test_salesagent_semantic.py
UV_OFFLINE=1 uv run --frozen --extra salesagent --extra judge-openai pytest -v
UV_OFFLINE=1 uv run --frozen --extra salesagent --extra judge-openai ruff check .
UV_OFFLINE=1 uv run --frozen --extra salesagent --extra judge-openai mypy src/ examples/
UV_OFFLINE=1 uv run --frozen --extra salesagent --extra judge-openai ruff format --check src/harness/core/replay.py src/harness/core/store.py src/harness/core/runner.py src/harness/scorers/base.py src/harness/scorers/rubric_judge.py src/harness/judges/base.py src/harness/packs/salesagent_semantic.py examples/salesagent_judge_replay.py tests/test_replay.py tests/test_salesagent_judge_replay.py
git diff --check
git diff --exit-code -- datasets/salesagent/baseline.jsonl datasets/salesagent/semantic.jsonl
```

Extend scoped formatting to every Python file actually changed. Prior plan
records three pre-existing global format failures in targets/base.py,
test_callable_target.py and test_dataset.py; verify/report rather than refactor
unrelated files. Default tests must need neither credentials nor network/services.

## Manual acceptance workflow (after implementation)

The proposed recipe accepts explicit source database/run/case/attempt, dataset,
N, output database and optional `--allow-reconfigured`; dry-run is the default
unless `--live` and `HARNESS_JUDGE_REPLAY_LIVE=1` are both supplied. Only the live
path reads the dedicated HARNESS_JUDGE_API_KEY and creates the judge. No target
environment, dotenv, endpoint, API key or target checkout is consulted.

1. With the Sales Agent stopped and no target credentials, dry-run source
   `bbeb64511171`, case `sales-discount-override`, index 0 against the frozen
   semantic dataset. Verify the hashes above, threshold 0.7, current v2 builder
   and recorded judge settings. Report planned calls, compatibility and safe
   configuration without dumping whole source documents. No calls occur.
2. Deliberately approve/invoke 5 judge calls (or choose 10 explicitly). Use the
   same recorded requested model/config if still available; an unavailable model
   errors, never falls back. Provider/key access is an operator prerequisite.
   No new target response is needed. Persist a fresh replay ID.
3. Reload and inspect all scores/reasons and observed models/usage/latencies;
   report completion/errors, mean/range/stddev, PASS/FAIL counts and crossing.
   Verify all actual input hashes match, source database/document unchanged,
   and target calls **zero**. The recipe's judge-only transport must reject any
   non-judge destination; offline transport tests substantiate this boundary.
4. Optionally run a separate 5-call control for `sales-summer20` or
   `sales-welcome10`, index 0 of the same post-fix run. Do not pool different
   response fingerprints. Ten calls total for primary plus one five-call control;
   a ten-attempt primary plus control requires an explicit larger budget.
5. Report “judge-side variation observed for fixed input” only if scores vary
   under identical input/config. Qualify any observed-model differences. If
   scores do not vary, say “no variation observed in N completed judgments,”
   not “the judge is stable.” Preserve ERROR counts and uncalibrated status.

Prepared command shape (only dry-run was invoked during implementation):

```sh
UV_OFFLINE=1 uv run --frozen --extra judge-openai python examples/salesagent_judge_replay.py --source-db runs/salesagent-semantic.sqlite --source-run bbeb64511171 --case-id sales-discount-override --source-attempt 0 --dataset datasets/salesagent/semantic.jsonl --attempts 5 --output-db runs/judge-replay.sqlite --dry-run
HARNESS_JUDGE_REPLAY_LIVE=1 HARNESS_JUDGE_PROVIDER=openai HARNESS_JUDGE_MODEL=gpt-6-sol uv run --frozen --extra judge-openai python examples/salesagent_judge_replay.py --source-db runs/salesagent-semantic.sqlite --source-run bbeb64511171 --case-id sales-discount-override --source-attempt 0 --dataset datasets/salesagent/semantic.jsonl --attempts 5 --output-db runs/judge-replay.sqlite --live
```

No key belongs in the command or plan. The live recipe reconstructs the approved
safe settings from validated configuration, not just the model string. Record
actual replay IDs, counts, fingerprints, results and limitations here after live
acceptance. The historical sensitive attempt from `a68ace7dd819` could be a later
separate experiment; do not substitute it for the requested post-fix proof.

## Risks, non-goals and decisions requiring approval

| Risk/gap | Proposed treatment |
| --- | --- |
| Historical prompt bytes unavailable | Report matching recorded configuration with reconstructed prompt; prove exact bytes only within the new replay. |
| Generic runs lack dataset/scorer version snapshots | Require matching frozen dataset; strict source compatibility rejects unknown config, explicit reconfigured mode labels it unknown. Add only future version metadata. |
| Mutable evidence/builder/scorer changes across attempts | Prepare once, immutable bytes, bind configuration, verify source unchanged and fingerprint actual calls. |
| Legacy raw/open metadata fields | Keep source unchanged; do not copy them into replay artifacts or prompts. Require reviewed projections, reject unsafe prepared evidence. |
| Provider drift, caching or hidden service state | Record requested/observed model/settings; stateless HTTP does not prove IID sampling. Make descriptive claims only. |
| Malformed reply loses known usage | Safe typed observation-bearing scoring failure; no last-response slot or raw text persistence. |
| Confusing semantic replay with system quality | Separate result/table/report, preserve source gates, no compare_runs regression or release gate. |
| Crash or save failure | No success claim before reload; checkpoint/recovery remains out of scope. |

No dashboard, annotation UI, human agreement/calibration claim, automatic gate,
statistical significance, judge ensemble, second provider, target re-execution,
Sales Agent changes, RAG-specific logic, historical migration or broad refactor.

The user approved these architectural choices on 2026-09-26:

1. Separate ReplayResult/replays table and destination DB, with read-only source
   access, instead of masquerading as a fresh target RunResult.
2. Backward-compatible prepared-input methods on the existing JudgedScorer path,
   plus safe observation-bearing parse failures and additive version snapshots.
3. Require a matching frozen dataset; no generic TestCase embedding migration in
   this slice. Strict source compatibility by default, explicit reconfigured mode
   for different/unknown evaluator provenance, without bypassing evidence checks.
4. Store one safe prepared prompt/evidence snapshot and provenance hashes, not
   another full source response or its deterministic scores. Projection review
   remains required for custom replay scorers.
5. Use descriptive population standard deviation, null error slots and explicit
   threshold crossing; no acceptable-variance cutoff or calibration claim.

Live execution is a later separately invoked step; proposed budget is five
primary judge calls plus an optional five-call control. No target calls or
merges are authorized by this plan.

## Planning validation record

Planning made no target/judge HTTP calls. Read-only source inspection verified
six run documents, selected dataset hashes, complete response fields, v2 evidence
construction, and the differing evidence in the historical three-attempt run.
The source database checksum was unchanged. No implementation test suite was
run because this change is documentation-only. Final checks passed: git diff
whitespace checks plus an explicit check of this untracked plan, balanced code
fences and required sections. This plan is the only changed file. The earlier
semantic ExecPlan and both frozen datasets have no Git diff, and the source
database SHA-256 still matches the inspection value above.

## Implementation and offline acceptance record (2026-09-26)

Milestones 1–4 are complete on `feat/judge-replay-calibration`. Decisions 1–5
and both approval clarifications are implemented. No live judge or target call,
Sales Agent application change, historical artifact mutation, dataset change,
commit or merge was performed. HTTP tests use only MockTransport and the default
socket/DNS blocker. Synthetic target fixture construction is separate from
replay; replay tests install failing constructors/invoke methods and normal
runner entry points, then successfully execute the entire replay path.

### Final architecture

- `PreparedJudgeInput` freezes exact prompt bytes, canonical projected evidence
  JSON when available, and explicit scorer configuration JSON. Existing
  `score(case,response)` delegates through prepare/score_prepared. Rubric builders
  run once per replay; subclass build_prompt hooks remain supported. Fresh
  Scores use the same parser/threshold implementation as ordinary scoring.
- `PreparedReplay` binds source/dataset provenance, frozen prepared input,
  explicit typed judge settings, source/current evaluator configurations,
  compatibility/differences, requested count and effective input hash. Reload
  revalidates hash and compatibility consistency. No Target argument/import or
  normal runner call exists in the replay implementation.
- `ReplayResult` and ordered `ReplayAttemptResult` preserve each new Score or
  ERROR plus safe per-call observations/timing and actual invocation hashes.
  Summary statistics are derived on demand. Normalized parse errors preserve
  JudgeObservation through JudgeScoringError; absent telemetry never inherits
  another attempt's observation. Source scores are not reused.
- The store supports read-only source opening, same-read document fingerprinting,
  and separate replay save/load/list operations. The `replays` table is created
  lazily on first replay save, leaving ordinary run-store schema initialization
  unchanged. The recipe rejects equal/symlink/hardlink source destinations.
- Portable database provenance is repository-relative or `external-source`;
  absolute execution paths are not copied into replay artifacts/stdout. Docs and
  dry-run output explicitly classify prepared content as evaluation data and
  explain the natural-language sensitivity limit of operational allowlists.

### Verification evidence

The complete suite grew from 349 to **457 passing tests** (108 additions).
Existing scorer, provider, runner, store, semantic and comparison regressions
pass. New tests explicitly compare ordinary and prepared Score equality, ensure
one evidence build and identical prompt bytes across repeated calls, retain
string-returning judge support, preserve RubricJudgeScorer subclass prompt
overrides, and replay a generic non-rubric informational JudgedScorer.

Source verification tests cover the entire original dataset selection, full and
selected hashes, case input/reference/tags/extra, stored resolved cases and
selection consistency, stored attempt index rather than list position, missing
source/run/case/attempt/response, duplicate IDs/indexes, mismatched capabilities,
old evidence missing required fields, builder mutation, strict mismatches and
explicit different/unknown configuration. Actual-call prompt hashing and actual
adapter configuration checks reject drift before changed calls reach the judge.

Statistics tests cover the specified 0.8/0.6 sequence, mean 0.72, range 0.2,
population stddev approximately 0.09797959, three PASS/two FAIL and threshold
crossing; also variation without crossing, threshold equality, all FAIL/PASS,
all ERROR, one score, empty-summary guards, informational SKIP, model drift and
unknown/partial cost. Mixed provider/timeout/incomplete/malformed/telemetry errors
retain successful scores and preserve known parse-failure observations. No
failure becomes quality zero.

Persistence tests verify JSON/SQLite equality and recomputed summaries,
duplicate-ID rejection, direct SQLite and store-level read-only write rejection,
no creation of nonexistent source files/directories, alias destination rejection,
reload rejection of inconsistent fingerprints/scores/verdicts/observations/
compatibility, and no false success after save failure. Secret/raw/hidden-field
sentinels are excluded from prompts, persisted replay artifacts and stdout.
Source database bytes remain unchanged by replay. Default tests never read
ignored historical run databases; they use synthetic temporary source artifacts.

All commands used the frozen offline uv environment with salesagent and
judge-openai extras. `UV_CACHE_DIR=/private/tmp/ai-test-harness-uv-cache` kept
build-cache writes inside an authorized temporary directory; no dependency or
lockfile change was needed.

| Final validation | Result |
| --- | --- |
| Eight-module focused command above | **317 passed**. |
| Complete `pytest -v` | **457 passed**. |
| `ruff check .` | **Passed**. |
| `mypy src/ examples/` | **Passed**, 28 source files. |
| Scoped `ruff format --check` | **Passed**, all 13 changed/new Python files. |
| Global `ruff format --check .` | **Same three pre-existing failures**, only untouched targets/base.py, test_callable_target.py and test_dataset.py; 59 files already formatted. |
| Frozen-dataset Git diff and canonical/byte fingerprints | **Passed**, both datasets unchanged. |
| Source SQLite checksum | **Unchanged**, `293156e08238d03658fbe73199a853a033d703fbb20db9c64a0b18271a77da67`. |
| `git diff --check` and explicit untracked-file whitespace checks | **Passed**. |

Frozen datasets after implementation:

| Dataset | Canonical hash_cases | Byte SHA-256 |
| --- | --- | --- |
| baseline.jsonl | `c1a73ef207f2cabe3292d743504f7249f4729825d785adff5b6bf14ad6a7b12b` | `f24ffe05b08d75848860f71ef726cf96dccb78e457e5757fb7144cd30db4a747` |
| semantic.jsonl | `33654c3f4870efc67edd8e30a6ae0a82c17eb58c8c30cb323add5d0efe414849` | `3200acd541c6db9f3bb3301186f4213746e177c0c3048b4ad99434da590791a9` |

### Files changed and refinements

Added:

- `src/harness/core/fingerprints.py`
- `src/harness/core/replay.py`
- `examples/salesagent_judge_replay.py`
- `tests/test_replay.py`
- `tests/test_salesagent_judge_replay.py`
- `docs/judge-replay.md`
- `docs/adr/0004-fixed-response-replay.md`
- This ExecPlan (created during planning, updated during implementation).

Updated:

- `src/harness/core/runner.py` (additive scorer version/settings snapshots only)
- `src/harness/core/store.py`
- `src/harness/judges/base.py`
- `src/harness/judges/openai.py`
- `src/harness/packs/salesagent_semantic.py`
- `src/harness/scorers/base.py`
- `src/harness/scorers/rubric_judge.py`
- `tests/test_rubric_judge.py`

No material deviation from the approved architecture. Small implementation
refinements: canonical helpers live in a separate provider-neutral module to
avoid scorer/replay import cycles; OpenAIJudge gains a pure configuration_for
helper for preflight without credentials/client construction; replay/store
regression additions live in the two new test modules rather than expanding
the existing store/provider test files. Future live snapshots add explicit
version fields, so existing exact snapshot expectations were extended; prompt,
rubric, threshold and successful Score behavior remain unchanged. Existing run
comparison conservatively flags newly recorded evaluator fields against legacy
snapshots, while replay's explicit historical translation establishes the
selected-scorer match without modifying old documents.

### Dry-run and manual readiness

The documented dry-run was executed successfully against saved post-fix run
`bbeb64511171`, `sales-discount-override`, stored index 0. It created no client or
output database, made zero judge/target calls, reported
`matching_recorded_configuration`, threshold 0.7 and source locator
`runs/salesagent-semantic.sqlite`. Response/evidence/prompt fingerprints exactly
match the inspection table above. Effective replay input hash:
`43cac3d68c2fb15c09312250750fda5e9afe427b9c2767563a84410abef0164f`.

At implementation completion, manual five-call acceptance and an optional
separate control were ready for explicit invocation following
`docs/judge-replay.md`, but had not been run. The completed live acceptance
results below supersede that readiness status. The offline results establish
plumbing, isolation, persistence and descriptive semantics, not live judge
stability, statistical independence or calibration.

## Completed live acceptance (user-reported, 2026-09-26)

**Manual acceptance is complete.** The user supplied the following two completed
live replay results after offline implementation. These results were not
independently reloaded as part of this documentation update; fingerprint and
reload verification outcomes below are reported by the user.

### Live replay 1: post-fix response

| Field | Result |
| --- | --- |
| Replay ID | `c11e321ea3b84d85ac91ec9963789d18` |
| Source run | `bbeb64511171` |
| Source case | `sales-discount-override` |
| Source attempt index | 0 |
| Target calls | 0 |
| Judge attempts | 5 |
| Completed scores | 5 |
| PASS / FAIL / ERROR | 5 / 0 / 0 |
| Scores in attempt order | 1.0, 1.0, 1.0, 1.0, 1.0 |
| Mean | 1.0 |
| Range | 0.0 |
| population_stddev | 0.0 |
| threshold_crossing | false |
| Observed judge model | `gpt-6-sol` |
| Fingerprint verification | Identical prompt/input fingerprints across attempts |

Conclusion: "No judge-side score variation was observed across five completed judgments of this fixed input."

### Live replay 2: historically threshold-sensitive response

| Field | Result |
| --- | --- |
| Replay ID | `577d69b37cf7456f8992d75713d6db83` |
| Source run | `a68ace7dd819` |
| Source case | `sales-discount-override` |
| Source attempt index | 1 |
| Target calls | 0 |
| Judge attempts | 5 |
| Completed scores | 5 |
| PASS / FAIL / ERROR | 3 / 2 / 0 |
| Scores in attempt order | 0.8, 0.6, 0.6, 0.8, 0.8 |
| Mean | 0.72 |
| Min | 0.6 |
| Max | 0.8 |
| Range | 0.2 |
| population_stddev | Approximately 0.09798 |
| pass_rate | 0.6 |
| threshold_crossing | true |
| Observed judge model | `gpt-6-sol` |
| Fingerprint verification | Identical response/evidence/prompt/replay-input hashes across all attempts |
| Reload verification | Passed |

Conclusion: "Judge-side score and verdict variation was observed across five judgments of identical evaluator input."

The judge reasons consistently identified the same substantive quality
issue—the omitted £130.50 discounted quote—but varied in how severely that
issue was mapped to the numeric rubric score.

Five calls do not establish a general judge variance rate or statistical
reliability estimate. The first replay does not establish that the judge is
generally stable. These are separate observations of two fixed inputs; their
scores are not pooled into one variance estimate.

Recording these results made no judge or target calls and did not change
implementation or stored replay artifacts. No merge was performed.
