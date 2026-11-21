# C3b Slice 4: offline ordered four-turn driver

Exact approved baseline: `967ccd2cf8b47efd57c03f3e543034429e5b6c7b`.
Branch: `feat/canary-runtime-v3-slice4`.
Worktree: `/private/tmp/ai-test-harness-canary-runtime-v3-slice4`.

The user's implementation approval permits exactly this plan, new driver_v3.py
and test_canary_driver_v3.py, plus changes to journal_v3.py and its existing test
module. No sixth file, commit, push, PR, merge, server, worker, real provider,
credentials, judge, Study run or later slice is authorised.

## Milestones

- [x] Fetch exact approved commit and create one isolated feature worktree.
- [x] Add checked copy-isolated journal snapshot access without replay changes.
- [x] Implement single-use driver, exact mock gateway and transient history gate.
- [x] Exercise a stateful mock application through the bounded provider client.
- [x] Cover behavioural continuation, operational stops, accounting and faults.
- [x] Run focused, full offline, optional pinned SDK and static verification.
- [x] Verify protected bytes/modes and return uncommitted work for human QA.

## Implementation contract

Resolve explicit V3 and consume its immutable turns verbatim. Journal decisions,
reservations, projected public evidence, assessments and outcomes remain the only
authoritative execution record. Driver snapshots validate the provider binding
under the existing mutex and return independent copies. No record/schema/replay
extension is introduced.

The application gateway directly invokes an exact supplied httpx.MockTransport;
no HTTP client or listener is created. The caller explicitly wires the mock
application to the driver's checked bounded client and supplies offline guards
and resource cleanup. Callbacks and this Python process remain trusted; tests
deny networking. This is not external authentication or hostile-code isolation.

The first model call must match the pinned application's _initial_messages shape:
same-session observed shopper/assistant history and recommended IDs, observed
resolved constraints, then the exact current shopper message. No golden state
repairs, provider input persistence or instruction inspection. Slice 3 retains
application-to-wire validation and within-turn continuation ownership.

For each turn: persist fresh decision, verify its next slot and gates, reserve,
arm history check, POST once, record chat, GET actual trace twice, record stable
projection, reconcile all final successful logical-call usage with public trace
totals, assess, record outcome, persist next policy decision. Behavioural FAIL
can continue; operational ERROR stops; safe SKIP and pending human review retain
their existing meanings. Retry liabilities remain attempt-level journal evidence.

Terminal provider/journal stops override earlier ADVANCE and may prevent later
public records/outcomes. Preserve the prefix; do not invent a STOP decision or
completed outcome. Recovery is inspection/save-only. Clean completion requires
explicit cleanup, truthful no-worker/mock-resource shutdown observations and the
existing completion seal/acknowledgement.

## Verification plan

Use the existing locked CPython 3.12 harness environment, stripped environment,
PYTHONPATH=src, PYTHONDONTWRITEBYTECODE=1 and python -B. Run focused driver/journal,
policy, acceptance, evidence, instrumentation and fault tests; full offline pytest
excluding test_canary_controller.py; Ruff, mypy, formatting and whitespace checks.
Optional existing SDK mock suites may use the approved CPython 3.13/OpenAI 3.3.1
environment without starting the application. Report every optional skip.

Compare all approved-baseline tracked files outside the two authorised modified
files, including modes, policies, fingerprints, fixtures, locks, dataset and
historical captures. Do not read private operator evidence. Implementation and
test results are recorded below only after their commands complete.

## Implementation progress

The journal change is additive: a frozen DriverSnapshot with independent nested
copies and a binding-checked driver_snapshot method. All 53 existing journal
function bodies and all 56 existing journal test function bodies match baseline
ASTs. All 206 other baseline tracked files match bytes and executable modes.
The snapshot cannot reopen a writer or authorise execution.

The driver accepts an explicit bounded client, offline guard supplier and cleanup
callback. Its responses_client must be injected into the trusted mock app, then
run receives an exact mock gateway tied to that same client. The cleanup callback
covers any supplied mock client resources; worker_stopped means no worker exists.
No external worker/SDK shutdown authentication is claimed. Returned inspection
retains the last persisted execution_action; driver_status and terminal dispatch
state must be read as well, since an old ADVANCE can precede a terminal stop.

The first test iterations corrected test-only faults: publication hooks initially
looked inside the on-disk envelope instead of the pre-publication record; malformed
token sums were initially mistaken for well-formed cross-ledger mismatches; and
a privacy assertion included its sentinel in the source line printed by Python.
The current cases distinguish these conditions. A numeric spending assertion now
compares Decimal values rather than estimator formatting. Those preliminary runs
are not final verification results.

## Observed full mock execution

An additional stripped-environment simulation denied all socket audit events and
used the same stateful mock composition as the tests. Its temporary registry was
separate from all existing evidence and removed after the simulation.

| Slot | Outgoing session | Observed session | Actual trace | Turn | Calls/attempts | Input/output/total tokens |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | omitted | mock-session-1 | mock-trace-1 | 1 | 2/2 | 203/23/226 |
| B1 | omitted | mock-session-2 | mock-trace-2 | 1 | 2/2 | 203/23/226 |
| A2 | mock-session-1 | mock-session-1 | mock-trace-3 | 2 | 2/2 | 203/23/226 |
| B2 | mock-session-2 | mock-session-2 | mock-trace-4 | 2 | 2/2 | 203/23/226 |

Four actual shopper POST forwards, eight trace reads, eight logical calls and
eight provider attempt forwards were observed. Each turn sums final call usages
101/11/112 and 102/12/114; it does not use only the last call. Known aggregate
estimated spending was $0.0031340, with zero unknown attempts, incomplete calls or
operational errors. Billing remains unverified. One cleanup callback completed;
the completion seal and acknowledgement were persisted. Mechanical PASS, overall
SKIP, human PENDING, source_authorised=false, provider_evidence_authenticated=false
and authorises_live_execution=false remain distinct.

## Verification results

- Existing pinned SDK instrumentation and historical SDK mock tests: 28 passed,
  no skips, 26.59 seconds. No application/worker was started.
- Ruff and mypy pass (60 source files); final formatting/whitespace and protected
  byte checks will be refreshed after the running suites complete.
- Focused driver/journal/fault/policy/selection/acceptance/evidence/instrumentation
  suite: 804 passed, no skips, 282.46 seconds. This run began before the final
  forwarding-counter refinement and three additional admission/snapshot cases;
  the final full run includes those changes. A focused final-delta check also
  covers those cases and exact mock-transport rejection.
- A second four-turn isolated-process check denied credential environment/file
  discovery, SDK imports, HTTP client construction and every socket audit event;
  the mock run completed with no private sentinel in its saved report.
- Final full locked offline suite: **3,540 passed, five optional skips, 424.46
  seconds**. Listening-server controller tests were excluded. This run includes
  the final implementation and all 134 added test cases (127 driver, seven
  snapshot cases).

The five full-suite skips are the two optional SDK modules, the original and v3
application-state modules, and the complete source-verifier composition requiring
the optional pinned CPython 3.13 worker. Both SDK modules passed separately in the
approved pinned environment (28 passes, zero skips). The other three optional
compositions were not executed; no new compatibility claim is made for them.

The final-delta focused run passed all five cases in 2.78 seconds. Final Ruff,
mypy (60 source files), four-file formatting and tracked/new-file whitespace
checks pass. A refreshed preservation audit verifies all 206 protected files,
all original function ASTs, all four approved V3 fingerprints, the historical C1
roster and the unchanged Study dataset fingerprint
`4a0e40d6dce4b78cc194352bf23d69dabcc8fe3c0f440d50f2cce2bd6a956028`.
Imports resolve to this exact new worktree. The index is untouched and HEAD is
still the approved commit. The original dirty development workspace and clean
Slice 1/2/3 worktrees retain their original states.

## Public interfaces and review limits

`OrderedCanaryDriverV3(journal, client, *, guards, close_client)` exposes the
history-checked `responses_client` for explicit mock-app injection, `run(gateway)`
and terminal `request_stop()`. `MockApplicationGatewayV3(transport, *,
responses_client)` exposes `post_chat(message, *, session_id=None)`,
`get_trace(trace_id)` and `close()`. Only the exact MockTransport type is accepted;
it is rechecked at forwarding. Slot reservations and two-read allowances are
consumed before callback execution; local POST/read counters count actual gateway
forwarding, not reservations. No additional trace read can repair failed evidence.

`CanaryJournal.driver_snapshot(provider_binding)` returns definition/run binding,
persisted Decision/sequence, active reservation and stop state, copied public
evidence, per-turn/total accounting and final successful logical-call token
counts. Its existing binding validator/mutex are reused. No existing function,
record, schema, policy, estimator or replay interpretation changes.

The stateful mock derives its committed history from the actual bounded-client
responses. Tests parameterise behavioural FAIL and operational ERROR at every
slot, including failure to establish A1 colour followed by A2 retaining the
observed null in its input. Prior answer text, recommended IDs, user messages,
context, session and provider continuation tampering fail closed. Operator stops
cover pre-forwarding admission, a blocked POST and an already-forwarded provider
attempt's result/finish drain. Publication faults cover both absent and visible
records at reservation/chat/trace/assessment/outcome/decision/completion boundaries;
abrupt child-process exits cover reservation and dispatch intent. Saved prefixes
remain unchanged and exports cannot reopen, repair or seal them.

Limits remain those approved by V3: four POSTs, 6/24 logical calls, 3/72 attempts
and the existing $5 aggregate estimated pause. Application tool calls are not
model calls. Simulated retries in default tests exercise the real instrumentation;
actual SDK retry headers and behaviour are covered separately by the existing
pinned SDK mock suites. Real billing, live transport, source/reviewer/credential
authentication, model extraction and human prose approval remain unestablished.
Mock callbacks/guards/cleanup and the Python process are trusted; there is no
hostile-code sandbox, real-time stop guarantee or physical-power-loss claim.
No optional pinned application state composition was executed.

## Final commands and disposition

Harness commands used the existing interpreter
`/private/tmp/ai-test-harness-canary-runtime-v3-slice2/.venv/bin/python`, with
`env -i PATH=/usr/bin:/bin PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1` and `-B`.
No dependency installation occurred.

```text
python -B -m pytest tests/test_canary_driver_v3.py tests/test_canary_journal_v3.py tests/test_canary_journal_v3_faults.py tests/test_canary_execution_policy.py tests/test_canary_selection_v3.py tests/test_canary_acceptance.py tests/test_canary_evidence_v3.py tests/test_canary_instrumentation_v3.py -q --tb=short -rs
python -B -m pytest -q --tb=short -rs --ignore=tests/test_canary_controller.py
python -B -m ruff check src tests
python -B -m mypy src
python -B -m ruff format --check src/harness/canary/driver_v3.py src/harness/canary/journal_v3.py tests/test_canary_driver_v3.py tests/test_canary_journal_v3.py
git diff --check
git diff --no-index --check /dev/null <each of the three new files>
```

The five final-delta cases were the pre-forwarding stop, third trace-read refusal,
two unsupported gateway transports and unprofiled Slice 2 snapshot refusal.
Pinned SDK commands used
`/Users/rebeccawilliams/Developer/study-v1-local/sales-agent/.venv/bin/python`,
the same stripped environment, and
`PYTHONPATH=src:/Users/rebeccawilliams/Developer/study-v1-local/sales-agent/src`:

```text
python -B -m pytest tests/test_canary_instrumentation_v3_sdk.py tests/test_canary_sdk.py -q --tb=short -rs
```

Exactly the approved three additions and two modifications remain uncommitted.
No commit, push, PR, merge, server, worker, real provider, credential discovery,
judge or Study execution occurred. Existing workspaces and evidence are preserved.

**GO for independent human QA of the offline five-file diff.** No Slice 5/6,
publication, authenticated approval or live authority is implied. Stop here for
the user's independent review.

## Approved independent-QA publication

The user's subsequent publication instruction provisionally accepts the offline
implementation and authorises one commit, a normal push of this feature branch
and a GitHub PR. This supersedes the earlier no-commit/no-publication restriction
only for those actions. The required commit and PR title are
`Add offline v3 ordered four-turn canary driver`; the exact sole parent must be
`967ccd2cf8b47efd57c03f3e543034429e5b6c7b`. Merge, auto-merge, later slices,
credentials, servers/workers, live providers, judges and Study execution remain
excluded. The five-file inventory is unchanged.

- [x] Confirm GitHub main still matches the exact approved parent.
- [x] Review the twelve pre-publication criteria against source and tests.
- [x] Re-run focused, pinned SDK, full offline and static verification.
- [x] Refresh protected bytes/modes, fingerprints and exact-scope checks.
- [ ] Create the single approved commit and verify its sole parent.
- [ ] Push normally and open the independent-QA PR against main.
- [ ] Verify published blobs/modes, clean worktree, CI/review/mergeability status.

The source review confirms: the immutable four-turn roster is consumed once;
only an explicit exact MockTransport is admitted and rechecked; the stateful test
app uses the injected history-checked bounded client and provider instrumentation;
observed sessions are promoted only after durable correlation; previous response
text, IDs and state come from journal evidence; behavioural FAIL remains eligible
for policy-controlled continuation; operational or terminal stops block further
POSTs; every final successful logical-call usage is summed while retry liabilities
remain separate; snapshots reuse binding checks/mutex and return independent
copies; stopped/interrupted prefixes do not acquire invented completion records;
human review stays PENDING; and protected source/policies/artifacts are preserved.

No executable or test changes were needed for publication preparation. New test
results will be recorded here only after the requested reruns finish.

Pre-publication reruns: focused suites **807 passed, no skips, 286.64 seconds**;
pinned SDK mock suites **28 passed, no skips, 27.79 seconds**; complete locked
offline suite excluding listening-server controller tests **3,540 passed, five
optional skips, 432.10 seconds**. Ruff, mypy (60 source files), four-file
formatting and whitespace checks passed. The repeated preservation audit passes for all 206
protected harness files and all original journal/test function bodies, approved
C1/V3 fingerprints and the Study dataset identity. The pinned application's
source, product/discount fixtures and lock also match the approved revision;
fixture/lock bytes and executable modes were checked explicitly.

The five full-suite skips are exactly the same optional compositions listed
above: two SDK modules (both passed separately in the pinned mock run), two
application-state modules, and the complete CPython 3.13 worker source-check
composition. The latter three were not executed. No concrete executable defect
or scope expansion was discovered. All four accepted source/test SHA-256 digests
remain unchanged from the start of this publication turn; only this plan changed.

This is the final pre-commit plan snapshot. The remaining publication checkboxes
describe the authorised external steps; their exact commit/PR identifiers and
published verification results will be recorded in the PR metadata and final
handoff, preserving the user's one-commit and clean-worktree requirements.
