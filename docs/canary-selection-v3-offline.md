# Selected-preference v3: offline implementation for review

Authorised scope: definition, acceptance and pure execution decisions only.
No controller integration, servers, credentials, provider requests, semantic
judging, real Study freeze/execution, application edits or Git publication.
The approved harness baseline is `b2c4878a261f2c17251c47437d8d49dd761ddc12`;
Sales Agent remains `3320e556540d3f95bee1e8509f13e558ce266b6c`.

## Separate review and preservation

The existing v2.1 change remains four independent, byte-identical additions:
`src/harness/canary/acceptance.py`, `tests/test_canary_acceptance.py`,
`tests/test_canary_state.py`, and `docs/canary-acceptance-v2.md`.
Its approved fingerprint remains
`3c632f6ce5e8b9eda42b4a0a0f91ccb82f4f34783da3b9638762b84351c9c2f9`.
Preservation regressions bind the SHA-256 of each of those files and the original
C1 assertion fingerprint. Do not combine these paths with v3 in an eventual
commit. V3 intentionally depends on the frozen v2.1 checks/types: review and,
only after separate authorisation, publish v2.1 before v3 as distinct changes.
Nothing has been staged, committed, pushed or merged.

The original driver/controller/recorder/input definitions remain unchanged.
All 22 first-canary files are checked read-only against the existing integrity
manifest, including filenames, byte counts, SHA-256 values and permission modes.
The historical failed result is not reassessed as a v3 success. V3 rejects the
old A1 wording as a definition mismatch. Study definitions, fixture files,
rubrics, journal/execution contracts and historical judge metadata are untouched.

## Definition and identity

Definition: `salesagent-canary-selected-preferences-v3`.
Exact A1:

> Please find a water-resistant day pack for a short canal-side walk. My maximum price is £60. I choose ACC-003 in Moss, 20L; please remember this product, colour and capacity as my preferences for this conversation and check that exact variant's availability. Do not apply a discount.

Exact A2:

> For the pack and exact variant I selected earlier, validate WELCOME10 and quote the final price. Keep my saved preferences and price limit.

B1/B2 and A1 → B1 → A2 → B2 ordering are unchanged. The new tuple is separate
from historical `TARGET_TURNS`; there is no global replacement or monkeypatch.
An independent canonical-JSON/SHA-256 regression recomputes the approved roster
hash. Existing prepared-judge hashes remain in the historical hash format;
preparing that metadata makes no judge request and grants no judge authority.

| Identity | Fingerprint |
| --- | --- |
| V3 input roster | `564b98533b5b48b13d7d97fec8c150c329a6bf5d7ed38f0f165bae32a8493e17` |
| Definition | `e76fd0e10f1176d6aa421a2b5de93f9503dceaa422b0631c2c8f7c957aa75607` |
| `salesagent-canary-selection-v3` acceptance | `575e304da8203b537d281d82a667e73dbf419fc95caee8df82dea6e7feabfce7` |
| `salesagent-canary-behavioural-continuation-v1` execution | `a4d8cdaaa4960ddf406c37703965d164595cea320cfa83c0ddd40fad797fa551` |

The definition fingerprint binds module source, roster, baseline/source pin,
fixture hashes, limits and unchanged cost-estimator implementation. Execution
binds its implementation and definition. Acceptance binds its implementation,
definition, execution and frozen v2.1 identity (including shared schemas/checks).
These are source-bound offline identities, not a deployed commit or permission.
A future integration receipt must bind all identities plus the actual approved
harness revision. No self-referential combined hash is claimed here.

## Independent acceptance

`assess_selection` takes public chat/trace snapshots and optional prior snapshots.
It writes nothing and creates no client or server. It validates exact message,
model, session/trace correlation, sequence, tool envelopes, timestamps and token
totals. Prior snapshots cannot be from a future slot or the historical wording.
Missing offline context produces explicit SKIP checks, never fabricated evidence.
Same A/B session identity, changed within-conversation identity or reused trace
identity is ERROR; leaked preferences under otherwise distinct valid sessions
are a deterministic current-state FAIL.

| Turn | Mandatory state and commerce expectations |
| --- | --- |
| A1 | Moss, 20L and maximum_price=60.00 must be established. Typed product facts and exact inventory support ACC-003; no promotion |
| B1 | Empty independent shopping state; no recommendations, pricing or promotion |
| A2 | Current Moss/20L/60.00 state; target product continuity; WELCOME10 validation and authoritative £49.50 quote |
| B2 | maximum_price=25.00 required; Rust/One Size may be unset or matching because this is still an enquiry; exact inventory required |

Product facts may come from authoritative `search_products` or `get_product`.
Coverage remains separate, including target-specific `get_product` arguments
AND result. Exact inventory arguments/results are required for variant stock;
catalogue stock or `matched_variant` alone cannot substitute. A2 may use the
same-session A1 inventory or a current exact lookup. Conflicting sources and
incorrect displayed product, promotion or quote evidence fail factual checks.

For A2, `current_state` and `retention` are distinct returned checks. If A1 did
not establish any mandatory selected field, A1 current state fails and A2
retention skips with the missing antecedent reason. An independently wrong
current A2 field still fails. If A1 established the selection and A2 loses it,
both current state and retention fail. Known failures are never hidden by SKIP.
Non-A2 turns have no retention check, rather than counting an inapplicable check
as PASS. The aggregate is ERROR > FAIL > required SKIP > PASS.

There is no invented resolved-state product-ID field. Product continuity uses
supported recommendations, trace nominations and A2 pricing. Conversation
history may help the agent answer A2; output correctness alone cannot prove
exclusive use of structured state. `matched_variant=None` remains an existing
projection limitation and separate product work. The serialized report explicitly
marks human shopper-prose review as required. A mechanical PASS is not human
acceptance of arbitrary prose and does not certify a completed live run.

Session isolation derives its required predecessors from `ORDER[:index(slot)]`:
A1 needs none, B1 needs A1, A2 needs A1/B1, and B2 needs A1/B1/A2. An absent
snapshot yields a reasoned `session_evidence_unavailable:<slot>` SKIP in an
independent offline assessment. All supplied identities are still checked;
missing evidence never masks a reused trace or contradictory session ERROR.
Operational decisions reject that SKIP and stop, even alongside behavioural FAIL.

## Reviewed business-failure classification

Original `_trace()` rejects any trace error, validation error/false flag or
failed tool. It is unchanged. V3 has its own typed normalization, rather than
catching `CanaryError` and treating exceptions as quality failures.

| Observed category in a completed, otherwise valid public trace | V3 classification |
| --- | --- |
| `duplicate_product_id:<id>` | Factual FAIL: rejected duplicate nomination |
| `unknown_product_id:<id>` with consistent `all_products_exist=False` | Factual FAIL: completed catalogue lookup rejected a nomination |
| `ungrounded_product_id:<id>` | Factual FAIL: product nomination lacked current evidence |
| `promotion_nomination_missing`, `ungrounded_promotion_code` without tool-error correlation | Factual FAIL: known completed nomination validation |
| `product_lookup_failed`, `pricing_calculation_failed` | ERROR: catalogue/pricing infrastructure unavailable or unreliable |
| Unknown validation prefix, inconsistent flags, malformed evidence, failed tool or provider error | ERROR |

Nomination diagnostics must use the exact reviewed prefix and a bounded ID
shape; only the safe category enters the returned assessment. Arbitrary diagnostic
messages are not returned. Prices/URL/stock validation flags are always true in
the pinned hydrator; false values are unexpected and remain ERROR. The broader
adapter's business-error allowlist is not automatically adopted: `unknown_tool`,
`invalid_arguments` and `product_not_found` remain ERROR in this slice pending a
separate contextual review. Eligible business FAIL is still not authority to
continue unless provider completion, accounting and every operational guard
are independently satisfied. This module does not verify actual billing.

## Pure execution decisions

`decide` returns ADVANCE, STOP or COMPLETE with a frozen state and separate
mechanical, human-review, operational and overall assessments;
it has no dispatch function. `authorises_live_execution` is always false, including
serialized output. `record_outcome` appends only the next scheduled turn and
rejects replay/replacement, out-of-order append and append after STOP/COMPLETE.
Decisions are deterministic; they do not consume a reservation or establish
physical replay protection. Future integration must persist returned states and
retain the existing exclusive, single-use reservations as the dispatch boundary.

All 13 operational booleans default false and must be exactly true: infrastructure,
provider completion, safety, privacy, recording, accounting, project controls,
spending headroom, source/fixtures, configuration, freshness, operator dispatch
permission and exclusive reservations. Provider completion means no unresolved
request and all observed provider work complete, including at an empty prefix.

Usage totals must reconcile with completed outcomes. Each turn permits 1–6
logical calls and at most 3 attempts per call; global ceilings remain 24 logical
calls/72 attempts. Unknown usage, malformed counters, non-finite/negative cost,
estimated spend at or above $5, an unsatisfied guard, a missing turn assessment
or any assessment ERROR
causes immediate STOP. Returned stopped states remain stopped even if a later
snapshot claims readiness. Completion and quality assessment are separate.

Completed trustworthy behavioural FAIL may advance to the next original slot;
the final aggregate still retains FAIL. Known retention-antecedent SKIP and
pending human-prose review may advance under complete guards, but never become
PASS. Missing session/recording/prior evidence or an unknown SKIP classification
stops the decision with ERROR even if a caller incorrectly claims guards passed;
the original per-check SKIP remains in the preserved outcome.

Mandatory human prose review defaults explicitly to PENDING with no review
evidence. COMPLETE means the roster has finished, not that quality passed.
With mechanical PASS and human PENDING, the serialized overall `assessment`
is SKIP (`human_prose_review_pending`); `mechanical_assessment` remains PASS.
Neither a required-review flag nor mechanical success creates human approval.
Pending review permits ADVANCE under all existing guards throughout the roster;
there is no per-turn review requirement. Independent human FAIL yields overall
FAIL. Human PASS cannot erase mechanical FAIL/SKIP/ERROR or an operational ERROR.

An optional explicit `HumanReview` records PASS/FAIL, reviewer `beccawillss`,
timezone-aware review timestamp, nonblank reason and `binding_fingerprint`.
`review_binding` binds a complete four-turn state and execution source identity
to `ReviewContext`: unique run ID, SHA-256 of the private evidence bundle and
the acceptance fingerprint. The bundle must include all shopper-facing chat
outputs, traces and acceptance reports. Any missing/malformed receipt field,
wrong reviewer, incomplete roster or binding mismatch gives ERROR and STOP;
the supplied receipt is preserved independently. Synthetic tests demonstrate
attestations only; no actual human score or approval has been manufactured.

This remains a pure supplied-evidence policy: a digest is not authentication.
Future integration must verify the bundle manifest against actual immutable
files, confirm the current acceptance fingerprint, authenticate the reviewer
and establish timestamp plausibility/freshness through the operator workflow.
It must persist the receipt and all three assessment dimensions. The policy
does not read private files, authenticate a user, consult a clock, judge prose
or write a review record automatically. Review context supplied without a
receipt leaves review PENDING. No provider or judge call is introduced.

No recovery, fallback, replacement, extra shopper turn, judge stage or increased
allowance is provided. Target model/settings, existing two SDK retries, $3 target
allowance plus $2 contingency, $5 estimated pause, $10 project cap and $2/$4/$5
alerts are unchanged. These constants do not independently verify dashboard
settings, prices, credentials or current spending headroom.

## Verification and exact inventory

New files in this v3-only change:

- `src/harness/canary/selection_v3.py`
- `src/harness/canary/selection_acceptance.py`
- `src/harness/canary/execution_policy.py`
- `tests/test_canary_selection_v3.py`
- `tests/test_canary_execution_policy.py`
- `tests/test_canary_selection_state.py`
- `docs/canary-selection-v3-offline.md`

No tracked baseline file was modified. The previously reviewed four v2.1 additions are
not part of this inventory. Default tests block external sockets/DNS. Optional
application tests use service objects and scripted model snapshots; SDK tests
use in-memory transports, not a listening server. Persistence tests do not
measure live model preference extraction. Controller lifecycle tests are not
run or bypassed in this slice.

The final offline QA refinement modifies exactly these five existing v3 additions:

- `src/harness/canary/execution_policy.py`
- `src/harness/canary/selection_acceptance.py`
- `tests/test_canary_execution_policy.py`
- `tests/test_canary_selection_v3.py`
- `docs/canary-selection-v3-offline.md`

It adds no files. The definition and application-persistence test module remain
unchanged. Acceptance and execution fingerprints above supersede the prior
reviewed draft hashes; no old fingerprint is retained as the current identity.

Final verification:

| Check | Result |
| --- | --- |
| Locked harness full offline regression | 2,910 passed, 4 optional module skips, 142.10 seconds |
| Locked worker focused regression | 368 passed, zero skips, 6.15 seconds |
| V3 definition/acceptance regressions | 68 passed |
| Pure execution-decision regressions | 91 passed |
| New pinned-application persistence regressions | 3 passed |
| Preserved v2.1 acceptance/persistence and installed-SDK tests | Executed in the focused worker run; all passed |
| Ruff / six new Python formatting checks | Passed |
| Mypy | Passed, 55 source files |
| Whitespace checks including untracked additions | Passed |
| V2.1 preservation | Four exact file digests and approved policy fingerprint unchanged |
| C1/C3a, controller and Study source preservation | No tracked harness file differs from approved baseline |
| Historical capture preservation | All 22 names, sizes, hashes and modes unchanged |
| Dataset and application | Approved 50-case fingerprint, Sales Agent source pin/cleanliness and both fixture hashes unchanged |
| Fingerprints | Match in harness and worker runtimes and this document |

Default optional skips: controller, SDK, original application-state module and
new v3 application-state module, because the harness-only environment lacks the
OpenAI/application runtime. SDK and both state modules executed successfully in
the prepared worker runtime (OpenAI 3.3.1 and the approved Sales Agent source).
Controller lifecycle tests were not executed in that runtime: this slice starts
no server and does not bypass the original controller's source inventory guard.

The two refined policy modules have 159 focused regressions, including 33 added
test instances in this QA slice. They cover serialized mechanical PASS/human
PENDING/overall SKIP; independent synthetic human PASS/FAIL; changed run, prose
digest, policy or outcome binding; malformed/unattributed receipts; boolean
non-approval; continued scheduling without per-turn review; human PASS unable
to override mechanical/operational failures; every roster-derived predecessor;
identity ERROR despite missing evidence; and operational STOP for missing
predecessors even alongside behavioural FAIL. Existing SET/retain/clear,
session isolation, limits, ERROR precedence and no-replay regressions remain.
An initial Ruff import-order finding was corrected before final passing static
checks. No provider requests or historical artifact changes occurred.

Commands in the feature worktree, reusing the prepared locked environments:

```sh
.venv/bin/python -m pytest -q --tb=short -rs
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="src:${SALES_AGENT_ROOT}/src" "$WORKER_PY" -m pytest tests/test_canary_selection_v3.py tests/test_canary_execution_policy.py tests/test_canary_selection_state.py tests/test_canary_acceptance.py tests/test_canary_state.py tests/test_canary_sdk.py tests/test_canary.py tests/test_canary_preparation.py -q --tb=short
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src/harness/canary/selection_v3.py src/harness/canary/selection_acceptance.py src/harness/canary/execution_policy.py tests/test_canary_selection_v3.py tests/test_canary_execution_policy.py tests/test_canary_selection_state.py
.venv/bin/mypy src
```

`SALES_AGENT_ROOT` and `WORKER_PY` are source/interpreter path placeholders, not
credential variables. No dependency or lockfile changed. Read-only scripts also
verified the existing private capture integrity manifest, original/v2.1 failed
A1 outcomes, rejection of historical wording by v3, and canonical fingerprints.
Those scripts did not copy private project/billing identifiers into this report.

## Proposed later integration, not performed

1. Separately review/publish the v2.1 and v3 changes; retain disjoint file lists.
2. Add an explicit v3 opt-in path while preserving C1 as the historical/default
   path. Pass the same definition through driver, recorder, bounded client and
   saved-evidence replay; never globally replace historical `TARGET_TURNS`.
3. Capture chat/trace, verify stable rereads/session correlation and complete
   telemetry/accounting, then durably record the assessment and decision before
   dispatching the next exclusive slot. An exception or recording failure stops.
4. Keep provider/store safety guards on every attempt. Bind reviewed definition,
   acceptance/execution fingerprints and actual source identity in fresh manual
   readiness/authorisation receipts. Approve an exact source inventory instead
   of weakening or bypassing the present C3a identity check.
5. Test synthetic worker lifecycle, interruption and stop behaviour separately.
   Listening-loopback lifecycle verification needs explicit server permission;
   none is requested or assumed by this offline implementation.
6. Verify immutable evidence manifests, current acceptance identity, reviewer
   authentication and timestamp freshness before accepting a human receipt.
   Persist and display the separate mechanical/human/operational and overall
   results, including overall SKIP while review is pending. Final human review
   is separate from scheduling and must never dispatch an additional request.

Outstanding risks: pure inputs must be backed by measured operational evidence,
not defaults; crash-safe decision persistence and reservation consumption are not
implemented here; new business-error categories require review; live extraction,
provider compatibility and actual billing remain unverified. No Sales Agent fix
is assumed from the old A1 enquiry. Any later application change needs separate
evidence and approval. Human review is required before controller integration,
Git publication or any new live authorisation.
