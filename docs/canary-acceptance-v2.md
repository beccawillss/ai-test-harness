# Proposed non-Study canary acceptance v2.1 — independent QA refinement

Status: bounded offline refinement for human review, 2026-11-14. No approval to
commit, publish, integrate into live startup or dispatch another request.
Base: harness `b2c4878a261f2c17251c47437d8d49dd761ddc12`.
Pinned Sales Agent: `3320e556540d3f95bee1e8509f13e558ce266b6c`.

## Policy differences

`harness.canary.acceptance.assess_turn` inspects public chat/trace dictionaries.
It constructs no client, server, store or provider request, reads no credentials,
and writes nothing. It is deliberately not wired into the live controller.
`assess_original_turn` invokes the original, unchanged C1 observations after
public contract/correlation validation. Existing driver and regression tests are
unchanged. The new original-policy label identifies those assertions; no label
or fingerprint is written retrospectively into the old run.

| Dimension | Original C1/C3a | Proposed v2 |
| --- | --- | --- |
| Product support | Selected product/price must appear in `get_product` | Complete typed `search_products` or `get_product` results may support the declared facts; inconsistent sources fail |
| Variant availability | Exact inventory for A1/B2 | Exact successful inventory arguments/results must agree on product/colour/size, stock and availability; catalogue stock or `matched_variant` cannot substitute |
| A2 inventory | No explicit check | Same-session saved A1 inventory supports the retained variant, or current A2 exact inventory; missing evidence fails |
| Tool coverage | Required tools plus selected-product facts from `get_product` | Independent check; required tool names retained; `get_product` arguments AND result must identify the target product |
| A1/B2 structured state | Colour/size must match the enquired variant; price limit not checked | Require explicit £60/£25 price limit; colour/size may be absent/null or match the enquiry; unsupported non-null values fail |
| A2 current state | Requires Moss/20L | Requires Moss/20L for the explicit current KEEP request, and retention of the £60 price limit |
| A2 retention | No prior-state check | Compare available A1/A2 state; missing prior variant selection is SKIP, not proof of a defect or successful retention; known incorrect state fails |
| Fresh B1 | Empty shopping state, no commerce output | State and commerce checks reported independently; no unsupported prior-product nominations |
| Aggregation | First failing observation stops execution | All three dimensions required for aggregate compatibility PASS; ERROR takes precedence; checks unavailable after prerequisite ERROR are SKIP |
| Infrastructure | Existing schema, tool-success, trace correlation, recording and spending guards | Original live controls untouched; offline evaluator reuses C1 schema/tool validation and checks correlation before evaluating facts/state/coverage |

Factual checks cover the declared canary commerce facts: product identity,
name, price, URL, suitability/warmth, exact variant stock, displayed structured
recommendations, requested discount validation and final quote. A valid source
does not hide a contradictory source. Chat and trace commerce projections must
agree. Invalid contracts, reported execution/tool errors, invalid recommendation
validation or identity correlation are ERROR, not a factual score of zero.

These are deterministic evidence-sufficiency checks, not semantic judging or a
certificate that arbitrary shopper prose is true. Human prose review remains
required. Aggregate PASS here means this one saved exchange satisfies these
checks; it does not certify a complete four-turn run, billing, stable trace
rereads, storage/recording completeness, request ceilings or live authorisation.
The existing controller/recorder still owns those gates and is not bypassed.
No tool-coverage shortfall has been made advisory. Continuation after behavioural
FAIL is a separate proposal below; it is not implemented in any controller.

The QA reproducer supplied correct ACC-003 search evidence, an unrelated valid
ACC-001 `get_product` exchange, and exact ACC-003 Moss/20L inventory. The first
v2 draft incorrectly reported coverage PASS: `_coverage` checked only tool names.
The original C1 product-fact assertion nevertheless required the target product
from `get_product`, supporting product-specific coverage intent. V2.1 makes the
smallest correction: a required `get_product` must have both target-product
arguments and a target-product result. Another candidate lookup cannot satisfy
it, while an additional unrelated lookup does not invalidate correct target
coverage. This does not force model routing or collapse coverage into facts.
Other required tool-name checks remain as before; factual validation continues
to bind search, inventory and discount evidence to their exact requested facts.

## State oracle against the unchanged shopper wording

| Input intent | Supported expectation |
| --- | --- |
| A1: “I'm comparing day packs”; “under £60”; “check whether ACC-003 is available in Moss, 20L” | Explicit price cap 60.00. The variant is an availability enquiry, not an unambiguous saved preference |
| B2: “find a beanie under £25”; “check ACC-001 in Rust, One Size” | Explicit price cap 25.00. Again, variant availability does not unambiguously select a saved preference |
| A comparison-only inventory request, without selecting a preference | Must not automatically overwrite existing preferences; tool arguments alone are not shopper intent |
| Explicit “choose/save/remember this colour and size” | Non-null selected preferences should be saved; covered by scripted persistence tests and the future wording proposal below |
| Existing A2: “same Moss 20L”; “Keep the colour and capacity” | Current KEEP request supports current Moss/20L state, but cannot prove A1 selected or saved those preferences |

For A1/B2 v2.1 permits each colour/size field to be null/absent or match the
enquired variant; matching state may represent a task constraint, not necessarily
a lasting preference. The schema does not distinguish these meanings. It does
not permit unrelated non-null state in these fresh shopping sessions. The
explicit price cap must be present and exact; inventory cannot establish it.

For A2 the current KEEP request and price cap must be satisfied. With complete
prior evidence, missing explicit prior price or an unsupported prior non-null
variant is FAIL. If the prior variant was legitimately unset, retention is not
assessable: structured state is SKIP, provided current requirements pass. Missing
prior evidence likewise yields a retention SKIP; it does not create a PASS.
Any demonstrated state violation takes precedence over missing retention
evidence. Aggregate compatibility remains non-PASS when a required check skips.
No original C1 assertion, shopper message or historical roster is changed.

## Version and fingerprints

Proposed policy: `salesagent-canary-acceptance-v2.1`.

Policy fingerprint:
`3c632f6ce5e8b9eda42b4a0a0f91ccb82f4f34783da3b9638762b84351c9c2f9`.

Superseded, provisionally reviewed v2 draft fingerprint:
`313b314e9b4e314ee0fd55d0afaf155fd145c69cb5adc7774a895e3cf41408dc`.
Its state oracle required Moss/20L in A1 and omitted the explicit price-limit
check. That interpretation is superseded, not silently edited under its identity.

Original assertions label: `salesagent-canary-c1-v1`.
Original assertions fingerprint, computed for this review:
`646fd93488667251a67a02d98548e1aface9353d2a4bb7594a7343d664f1aa65`.

Unchanged historical input-roster hash:
`e8778ce74a270e6efbe490198d01e8b9c50bcc43387a02bff5f00b42304d5794`.

The original roster hash binds shopper inputs and prepared judge prompt hashes,
not acceptance assertions. `policy_fingerprint()` separately binds the policy
identifier, acceptance implementation, C1 normalization code, public validation
schemas, input-roster hash, target model/revision and declared offline scope.
The v2 implementation hash covers the entire acceptance module, including its
thresholds and expected facts. Formatting/code changes therefore change it too.
The original fingerprint binds the unchanged C1 observation function rather than
claiming the new v2 module was part of the historical run. Compute fingerprints
with the committed dependency locks; no judge is executed by this operation.

No shopper inputs, models, inference settings, fixture files, Study cases,
rubrics or historical roster/hash have changed. A future prompt change must
receive its own new input-roster hash. Source/controller rollout and any live
authorisation must bind the reviewed policy fingerprint explicitly.

## Captured A1 review

Only the saved public A1 chat and trace were evaluated; no replay transport,
application invocation, model or judge was used. All 22 original artifact names,
byte lengths, SHA-256 digests and permission modes matched the saved post-run
manifest before and after inspection. The historical stopped result is retained.
Private locations and project/billing identifiers are not copied into this file.

| Check | Result |
| --- | --- |
| Original C1 observations | FAIL — required `get_product` coverage missing |
| v2.1 public-evidence prerequisites | PASS |
| v2.1 factual evidence | PASS |
| v2.1 integration coverage | FAIL — `not_exercised:get_product` |
| v2.1 structured state | PASS — maximum_price=60.00; enquiry variant may be unset |
| v2.1 aggregate compatibility | FAIL |

The previous v2 draft reported state FAIL for this same saved A1. V2.1's separate
assessment changes that interpretation under its new fingerprint only; neither
the original failed result nor any historical artifact is relabelled or updated.

Search supplied ACC-003's £55 price, walking suitability, water-resistant feature,
URL and Moss/20L stock. Inventory independently confirmed Moss/20L available,
stock 5. This supports the reviewed shopper answer without an additional
model-invoked product lookup. Broad search remains a retrieval precision and
constraint-extraction observation, not a proven unsupported answer.

## Structured-state mechanism and regression scope

The pinned application merges only `OrchestrationResult.constraint_updates`
into the session's resolved state (`services/chat.py`, `services/constraints.py`).
The final model output supplies that patch. Inventory results are authoritative
stock evidence, not shopper preference updates. They must not automatically
select a preference: a shopper may be comparing another variant.

The strict final-output schema requires every patch field. A JSON null means
retain; an entirely omitted field is invalid; `{operation: clear, value: null}`
explicitly clears it. A valid nonempty SET is preserved by the merger. The new
tests run the actual pinned orchestrator, merger, chat service and session
repository with scripted model snapshots, using no SDK or server.

A1's merged state records the £60 change but no effective Moss/20L SET. Scripted
tests reproduce that outcome with null/retain or clear patches, and produce
correct state when SETs are supplied. The raw final provider envelope was not
retained: null versus clear and the model's reason cannot be recovered. This
establishes the storage mechanism; it does NOT establish failed preference
extraction, because this shopper wording did not clearly select a preference.
The previous report's application-defect inference was too strong.

All eight existing application-state regressions are preserved byte-for-byte:
SET, retain, clear, omitted strict fields, comparing another variant, independent
sessions, successive-turn retention and both no-SET reproductions. Their
scripted patches validate application persistence, not live model extraction
reliability or appropriate intent classification. No Sales Agent change is
justified solely by A1's unset enquiry variant, and none is made here. If a
future explicit-selection experiment exposes a gap, preference extraction and
its ambiguity/negation/comparison regressions need separate review. Do not copy
inventory arguments into preferences or add paid extraction/replacement calls.

## Future selection/retention wording — proposal only

Proposed A1:

> Please find a water-resistant day pack for a short canal-side walk. My maximum
> price is £60. I choose ACC-003 in Moss, 20L; please remember this product,
> colour and capacity as my preferences for this conversation and check that
> exact variant's availability. Do not apply a discount.

Proposed non-leading A2:

> For the pack and exact variant I selected earlier, validate WELCOME10 and
> quote the final price. Keep my saved preferences and price limit.

Neither message is implemented in `TARGET_TURNS`. A future approved definition
must have a new roster version/hash and a selection-specific acceptance revision
(for example, `selection-retention-v3`) requiring non-null selected preferences
after A1 and their retention after A2. The enquiry-permissive v2.1 oracle must
not be reused unchanged for explicit-selection wording. Bind exact prompts,
policy and execution-policy fingerprints, source pins, fixtures and effective
configuration in the new reviewed definition. Recompute the policy fingerprint
too: it binds the roster hash. No future draft hash is claimed before approval.
The historical roster and its hash remain intact.

A2 no longer supplies product ID, colour, size or numeric price limit, but still
has legitimate conversation history. Correct answers alone do not prove exclusive
use of structured state; inspect stored state before/after as well. These are
draft input texts, not a request or authorisation to run another experiment.

## Execution classification and continuation — separate proposal only

| Classification | Proposed meaning and action |
| --- | --- |
| FAIL | Reliable, complete evidence demonstrates an unmet deterministic factual, state or target-tool coverage requirement. Preserve each dimension and the failing result; never present it as PASS or average it away |
| ERROR | Provider/infrastructure failure, invalid or uncorrelated trace, recording failure, safety/privacy/control failure, budget breach, unknown usage or ambiguous billing/completion. Stop dispatch immediately, save available evidence and shut down safely |
| SKIP | A check has no valid antecedent or the evidence needed to assess it is unavailable. Record the reason; never count it as PASS or use it to hide a known FAIL. Evidence missing because live recording failed makes the RUN ERROR even though dependent checks skip |

Recommendation for a separately reviewed, future bounded diagnostic canary:
permit the next originally scheduled shopper turn after behavioural FAIL only
when every safety, recording, identity, spending and provider-completion guard
remains satisfied. This can reveal multi-turn behaviour after missing tool
coverage without disguising the earlier FAIL. A completed run with any required
FAIL remains FAIL; a required SKIP prevents an unqualified PASS. ERROR always
takes precedence. Absence of evidence is not permission to continue: uncertain
recording, billing, provider completion or safety is ERROR and stops the run.

Continuation would mean only the next unexecuted A1/B1/A2/B2 roster entry, not
retrying, replaying, replacing or restarting a failed turn. Preserve the actual
session state, flag dependent observations and never seed missing preferences
to manufacture a valid retention antecedent. Keep the same separately approved
request/attempt/spend ceilings and SDK retry configuration. Pause/stop commands
and spending guards take precedence at every step; never increase a budget to
complete the roster. No automatic resumption after ERROR, and no judge stage.

This is a versioned execution-policy DESIGN PROPOSAL, not implementation or
authorisation. The current live controller still stops at the first C1 failure.
The offline evaluator retains its existing prerequisite ERROR classifications
and aggregates independently reported checks; v2.1 adds only the documented
retention SKIP when an antecedent was not established. Its existing factual
check still marks absent exact inventory support FAIL. A future controller must
distinguish known absence of a required call in a complete trace from a missing
or incomplete trace caused by infrastructure; this proposal does not silently
change that live error handling or approve continuing with unknown evidence.

## Response projection

`services/chat.py::_map_recommendation` unconditionally sets
`matched_variant=None`; hydration is product-level. Backend hydration itself
uses the commerce `get_product` method, which is separate from model tool-path
coverage. The projection limitation does not invalidate the exact inventory
evidence and need not block the next canary on its own. V2 permits null, rejects
a contradictory non-null variant, and still requires exact inventory evidence.
Track variant projection as separate product work: determine the selected
variant explicitly rather than copying the last inventory lookup. It does not
repair the missing structured preferences.

## Verification and review status

Added synthetic acceptance regressions cover both product paths, conflicting
sources, missing sources, product/price/URL/stock errors, display contradictions,
exact inventory correlation, discount/quote errors, fresh-session state,
missing prior state, malformed traces/tool errors, policy fingerprint changes,
unchanged roster and client-free/non-mutating inspection.

QA additions reproduce unrelated-product coverage, target argument/result
agreement, a valid target lookup alongside another candidate, optional enquiry
variants, mandatory exact price caps, current A2 KEEP state, missing retention
antecedents and known state violations taking precedence over SKIP. The original
QA reproducer failed against the first draft (coverage PASS instead of FAIL),
then passed after the product-specific correction. This is an offline regression
failure, not a new canary or provider request.

Eight pinned-application regressions cover explicit SETs, null versus omission,
clears, comparing another variant, no tool-derived preferences, successive-turn
retention, session isolation and both possible no-SET reproductions of A1.
The matched-variant limitation is checked against actual application output.

Final verification:

| Check | Result |
| --- | --- |
| Full locked harness offline suite | 2,751 passed, 3 optional module skips, 141.76 seconds |
| Focused worker-runtime suite | 206 passed, zero skips, 5.18 seconds |
| Acceptance regressions after QA refinement | 117 passed |
| Preserved pinned-application state regressions | 8 passed, file unchanged |
| Existing installed-SDK regressions | All 3 passed, scripted transport only |
| Ruff across source/tests | Passed |
| Formatting of all three new Python files | Passed |
| Mypy | Passed, 52 source files |
| Whitespace checks including untracked files | Passed |
| Captured evidence integrity | All 22 files unchanged, including names, sizes and modes |
| Dataset/fixtures | Approved 50-case fingerprint and both fixture SHA-256 values unchanged |
| Policy identity | Same fingerprint in harness and worker runtimes; matches this document |

The three default-suite skips are the controller, SDK and new state modules:
the harness-only environment has no OpenAI SDK or application installation.
SDK and state modules were separately executed in the prepared C3b worker
runtime, with OpenAI 3.3.1 and pinned Sales Agent source. Controller lifecycle
tests were not executed in that runtime during this slice; no listening server
was started and the controller's source allowlist was not bypassed. All new
state tests invoke service objects directly; existing SDK tests use in-memory
transport/TestClient. The default network-blocking test fixture remained active.

Commands, from the isolated feature worktree (the locked environment was
prepared in the initial slice and reused for this refinement):

```sh
uv sync --locked --offline
.venv/bin/python -m pytest -q --tb=short -rs
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="src:${SALES_AGENT_ROOT}/src" "$WORKER_PY" -m pytest tests/test_canary_acceptance.py tests/test_canary_state.py tests/test_canary_sdk.py tests/test_canary.py tests/test_canary_preparation.py -q --tb=short
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src/harness/canary/acceptance.py tests/test_canary_acceptance.py tests/test_canary_state.py
.venv/bin/mypy src
```

`SALES_AGENT_ROOT` denotes the unchanged approved application checkout;
`WORKER_PY` denotes the existing isolated C3b worker interpreter. These are path
placeholders, not credential settings. No dependencies or lockfiles changed.
The read-only A1 comparison asserted both policy outcomes and checked every
artifact against the existing post-run integrity manifest before and after.
Whitespace checks used `git diff --no-index --check /dev/null <new-file>` so
untracked additions were checked without staging them.

Exact QA refinement change inventory:

- `src/harness/canary/acceptance.py`
- `tests/test_canary_acceptance.py`
- `docs/canary-acceptance-v2.md`

`tests/test_canary_state.py` is preserved byte-for-byte from the reviewed v2
slice (SHA-256 `ca85f6f5e071e19fb84104f5dee6afeb160264ac363bc26628a531e7a6a4c7a3`).
Relative to the approved harness base, the uncommitted feature branch still has
exactly those four additions and no changes to existing tracked files.

Original tracked harness files and the pinned application remain unchanged;
no historical artifact, Study definition, rubric or lockfile was edited.
The feature branch is uncommitted. No credentials, external requests, live
canary continuation, semantic judging, real Study freeze/execution, commit,
push or merge occurred.

Remaining review decisions: approve/revise target-product coverage and the
price-cap/enquiry state oracle; approve/revise retention SKIP reporting; decide
whether a future explicitly selected-preference roster should be authored; and
approve/revise the separate continuation-after-FAIL execution-policy proposal.
Tool coverage remains required for aggregate PASS. No application fix is assumed
necessary from the original ambiguous enquiry. Any application change would need
separate evidence and approval. The unmodified
live controller still runs v1 and restricts source inventory to C3a, so this
worktree is intentionally not a live-ready execution environment. No source
allowlist or identity check was broadened. Human approval and a separately
reviewed deployment/definition binding would be required before adopting v2.1.
Any future live execution also requires fresh operational preflight evidence
and a new explicit authorisation; the consumed first-run approval is not reused.
Only future wording and execution-policy designs are proposed here; no live
dispatch is authorised, requested or scheduled.
