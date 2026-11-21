# C3b Slice 3: offline definition-bound provider instrumentation

Approved base: `93fbceaed1acfa3284190af39de2c3f0d6fa9abc` (exact HEAD).
Branch: `feat/canary-runtime-v3-slice3`.
Worktree: `/private/tmp/ai-test-harness-canary-runtime-v3-slice3`.
The user's Slice 3 implementation approval authorises only the nine files listed
below, mock-only I/O and offline verification. No commit, push, PR, server, worker,
judge, live transport, credential discovery or Study execution is authorised.
The specific approved main baseline supersedes the default integration branch.

## Milestones

- [x] Create an isolated worktree at the exact approved commit; preserve others.
- [x] Define the opt-in record profile before modifying journal handling.
- [x] Implement checked journal APIs and safe telemetry validation/replay.
- [x] Implement explicit-v3 decorator and transparent synchronous mock transport.
- [x] Add deterministic unit, fault, corruption and pinned SDK regressions.
- [x] Run focused, full offline, pinned-runtime and static verification.
- [x] Verify protected bytes, exact file scope and return for independent human QA.

## Exact additional record profile

Profile identifier: `canary-provider-instrumentation-v1`. The enclosing existing
journal schema remains `nonstudy-canary-journal-v3-v1`. This is an explicit record
extension, never an upgrade or reinterpretation of a saved Slice 2 journal.

New record kind `instrumentation_profile` is permitted exactly once, immediately
after the manifest, before any decision or provider work. Payload: `profile`,
`binding`, `source_authorised=false`, `provider_evidence_authenticated=false`,
`authorises_live_execution=false`. Binding is a strict immutable model containing
the exact v3 definition, registry/run identities, source-receipt digest, explicit
synthetic project/organisation identities and `transport_kind=mock`.

The profile requires new provider record kinds (all carry the exact `profile`):

1. `instrumented_call_reserved`: `reservation`, `previous_response_id`.
   Reservation contains binding digest, run/registry identities, slot, logical-call
   number and reservation sequence. The journal issues it once; later methods
   compare every field. Calls remain sequential and bounded by the existing rules.
2. `instrumented_dispatch`: `reservation`, `attempt`, `telemetry`. Telemetry stores
   the observed SDK retry count, attempt start timestamp and strict fresh guard
   snapshot. Guards default false, include source/configuration/privacy/project/
   headroom/operator/exclusivity checks, external unknown count and estimated total.
   Guard time must be timezone-aware and within a bounded freshness interval.
   SDK count must match attempt minus one; it is extracted from the real header.
3. `instrumented_result`: `reservation`, `attempt`, `observation`, `telemetry`.
   Observation uses the unchanged Slice 2 projector/estimator. Telemetry stores
   finite nonnegative elapsed milliseconds, read-complete flag, JSON state,
   observed header HTTP status and safe parsed Retry-After / Retry-After-MS values
   and format states. Raw headers/bodies/error prose are never stored. Partial
   reads retain observed header status separately and remain ambiguous liabilities.
4. `instrumented_call_finished`: `reservation`, `outcome` (`returned` or `error`),
   `response_id`, `failure` (fixed category or null). A returned call requires a
   matching valid ID from its final completed HTTP result. Error evidence never
   replaces attempt results; unresolved dispatches remain incomplete liabilities.
5. `instrumentation_stop`: `profile`, `code` (fixed terminal category). The producer
   closes its in-memory dispatch latch before attempting publication. The record
   blocks calls/attempts but permits the already active call's result and finish.
   Execution state becomes stopped after that call finishes, or immediately when
   no call is active. This avoids invoking legacy `stop` before the active result.

Strict field sets, profile identity, reservation identities and transitions are
validated by the same replay path as production. Legacy provider record kinds
cannot be mixed into a profiled journal; new kinds cannot occur without the
profile. Existing Slice 2 journals retain their original record shapes and rules.
Inspection reports the profile and terminal state separately; no observation,
checksum, source match or claim gains authentication/live authority. Old code is
not expected to read this new opt-in extension. Recovery remains save-only.

## Execution and synchronization

Journal-issued immutable provider/call identities replace adapter access to private
journal state. Validation and append run under its existing RLock; failed checks
close the producer and the terminal gate. No lock spans delegate/network I/O.
One call and one attempt may be active; reentrant/concurrent activity is rejected.
An independent Event closes dispatch immediately even while result I/O is active.
The SDK alone retries: two retries, three attempts, six calls per turn, 24/72 total.
Unknown usage may survive eligible same-call retries but blocks the next call.
The known subtotal at $5 blocks dispatch even when total spending is unknown.

The adapter accepts exactly an explicitly supplied `httpx.MockTransport`, rejecting
custom network transports/subclasses. A mock callback is trusted test code, not a
hostile-code sandbox; test processes additionally block sockets and DNS. No SDK
or HTTP client is constructed by the instrumentation. Prepared request objects,
bytes, headers and extensions are forwarded unchanged. Strict request validation
rejects drift rather than repairing it. SDK/app exceptions are sanitised at the
outer boundary; later SDK iterations see the permanent gate before any new intent.

## Approved files and verification

Create instrumentation_v3.py, its unit and SDK test modules, and this plan. Modify
only journal_v3.py, evidence_v3.py and their three existing test modules. Preserve
C1/controller/driver, policies, fingerprints, estimator, fixtures, captures, dataset
and locks. Verify every approved-base tracked file outside the five modified paths
against its Git blob/mode without reading private operator evidence.

Use stripped test environments and existing pinned environments; do not install.
Run focused instrumentation/evidence/journal/fault suites, existing canary suites,
full locked offline pytest excluding test_canary_controller.py, Ruff, mypy,
changed-file formatting and whitespace checks. Run real SDK mock tests with the
approved CPython 3.13 / OpenAI 3.3.1 application environment and report skips.
No listening server is needed. Preserve literal request-byte comparisons without
printing prompts/credentials. Test publication failures, replay/profile tampering,
SDK retries/long delays, partial transport, stop/backoff/concurrency and accounting.

## Progress and results

Exact approved commit fetched and isolated worktree created with sandbox approval.
Existing development changes and Slice 1/2 worktrees remain untouched. No commit,
push, PR, server, worker, external model request, judging or Study run occurred.

Public journal interfaces: immutable `ProviderBinding`, `CallReservation`,
`ProviderSnapshot`; `bind_provider`, `provider_snapshot`, `reserve_provider_call`,
`dispatch_provider_attempt`, `observe_provider_attempt`, `finish_provider_call`,
`request_provider_stop`, and the read-only `provider_stopped` property. Profiled
`stop()` routes to the evidence-preserving stop API; legacy stop records cannot
be mixed into the profile. Adapter interfaces: `ProviderTransportV3` with required
journal/binding/exact MockTransport/guard callback, `request_stop`, and
`BoundedResponsesClientV3.create_response`. No adapter accesses journal internals.

Telemetry time formats: timezone-aware ISO strings for guard/start observations;
finite numeric elapsed milliseconds; Retry-After seconds for numeric headers or
Unix seconds when the explicit format is `date`; Retry-After-MS is milliseconds.
Invalid raw headers become fixed `invalid` state, never arbitrary text. Snapshot
freshness is rechecked after durable intent and before forwarding. Safe application
response IDs are retained on identity failures alongside the actual HTTP evidence.
No ID, timing, source claim or profile flag authenticates external provider work.

Verification uses existing environments only, with `env -i PATH=/usr/bin:/bin
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1` and `python -B`. The harness interpreter is
`/private/tmp/ai-test-harness-canary-runtime-v3-slice2/.venv/bin/python` (CPython
3.12); its installed packages match the unchanged harness lock. Optional SDK tests
use `/Users/rebeccawilliams/Developer/study-v1-local/sales-agent/.venv/bin/python`
(CPython 3.13) and add the approved Sales Agent `src` directory to PYTHONPATH.
All SDK credentials/project IDs in those tests are synthetic. Test-only fault
injection and a scheduling barrier exercise SDK backoff; production does not
patch SDK internals, logging configuration or retry behaviour.

| Check | Actual result |
| --- | --- |
| Final instrumentation/evidence/journal/fault suites | 352 passed, 79.83 seconds |
| Final pinned OpenAI 3.3.1 new and historical SDK suites | 16 passed, no skips, 11.59 seconds |
| Ruff across src/tests | Passed |
| Mypy | Passed, 59 source files |
| Changed Python formatting | All eight files passed |
| Tracked whitespace | Passed |
| Protected baseline files, bytes and executable modes | All 199 files outside the five approved modifications match |
| C1/v2.1/v3 identities and estimator | Approved fingerprints unchanged |
| Study dataset | 50 cases; `4a0e40d6dce4b78cc194352bf23d69dabcc8fe3c0f440d50f2cce2bd6a956028` |
| First full locked offline suite excluding listening controller tests | 3,361 passed, five optional skips, 226.60 seconds |
| Final full locked offline suite after inspection correction | 3,361 passed, five optional skips, 225.39 seconds |

The focused run includes original Slice 2 fault/FIFO/replay tests; new failures
at call/dispatch/result/finish publication, visible post-publication ambiguity,
crash after intent, ten fully rechained profile/semantic forgeries, in-flight
adapter/journal stop, reentrancy/concurrency, threshold boundaries and complete
synthetic 24-call/72-attempt accounting. All previous test bodies remain intact.
The pinned tests execute actual SDK 500/500/200 retries, real retry-count headers,
long-delay retry refusal, terminal-fault SDK re-entry without a second intent,
HTTP success followed by SDK validation failure, backoff stop and the unmodified
application ResponsesClient. Request hooks compare the original object, byte/header
digests and extensions immediately before the transport against the mock callback.

Slice 4 remains separately gated: shopper scheduling, controller/worker lifecycle,
source/approval authentication, real project/credential association, external
budget/usage freshness and live authority are absent. Mock callbacks and the
Python process remain trusted; no claim is made of hostile-process isolation,
actual billing verification, prospective spend reservation or physical-power-loss
durability. The $5 estimated pause is not an actual billed-spend guarantee.

Final review correction: inspection now distinguishes
`instrumentation_terminal_stop_recorded` from `dispatch_available=false`.
A recording failure may prevent a durable stop marker, but cannot reopen the
producer or make saved evidence dispatchable. Absence of that marker is never
reported as an open dispatch gate. Fault tests cover this distinction both before
and after visible result publication. Final full and pinned-runtime reruns passed
after this correction, as did Ruff, mypy and changed-file formatting. The focused
352-test run preceded this inspection-only correction; the final full run includes
all those focused tests against the final source bytes.

Exact verification commands after the environment prefixes above:

```text
python -B -m pytest tests/test_canary_instrumentation_v3.py tests/test_canary_journal_v3.py tests/test_canary_evidence_v3.py tests/test_canary_journal_v3_faults.py -q --tb=short
python -B -m pytest tests/test_canary_instrumentation_v3_sdk.py tests/test_canary_sdk.py -q --tb=short -rs
python -B -m pytest -q --tb=short -rs --ignore=tests/test_canary_controller.py
python -B -m ruff check src tests
python -B -m mypy src
python -B -m ruff format --check <the eight approved Python files>
git diff --check
git diff --no-index --check /dev/null <each new file>
```

Five full-suite optional skips: both SDK modules, the original and selected-state
application modules, and the complete CPython 3.13 source-verifier composition
test. Both SDK modules executed with zero skips in the separate pinned-runtime
run. The application-state/source-composition optional checks remain explicitly
unexecuted in this slice; no compatibility claim is made for those compositions.
The listening-server controller module was excluded, never executed.

Final scope verification confirms exactly four additions and five modifications,
79 existing test functions/classes unchanged by AST comparison, an untouched index
and HEAD still exactly the approved merge revision. Existing development changes
remain present; Slice 1 and Slice 2 worktrees remain clean. All new/tracked files
pass whitespace checks. The source-preservation check covers 199 unchanged baseline
files, including C1, policies, locks, dataset and tracked fixtures/captures.

**Recommendation: ready for independent human QA of the uncommitted nine-file
offline diff.** Review the extension replay validator, atomic reservation checks,
stop/drain ordering, publication ambiguity and known/unknown billing first.
No commit, publication, Slice 4 integration or live execution is authorised.

## Independent QA follow-up: application-to-wire request integrity

The focused offline QA authorisation permits changes only to the adapter, its
two test modules and this plan. The other five files in the nine-file Slice 3
diff remain unchanged from the provisionally accepted implementation. No journal
contract, telemetry, dependency, fixture, policy, application source or model
configuration changes are needed.

- [x] Inspect the pinned application mapping and add regressions first.
- [x] Run against the unchanged adapter and report reproduction before correction.
- [x] Add application-value snapshots and parsed-value validation before intent.
- [x] Verify pinned application mapping, SDK retry rejection and request preservation.
- [x] Complete focused, full locked offline and static verification; return for QA.

Pinned source: `src/salesagent/agent/responses_client.py` at application HEAD
`3320e556540d3f95bee1e8509f13e558ce266b6c`; that file has no diff from the pin.
`ResponseRequest.input` is a string or a nonempty homogeneous tuple of
`ResponseMessage(role, content)` or `FunctionCallOutput(call_id, output)` records.
The client maps those tuples to ordered JSON arrays, adding
`type=function_call_output` for outputs. It passes instructions directly,
converts tools to a list, and wraps `text_format` as `text={format: ...}`.

Reproduction command, before the source correction:

```text
python -B -m pytest tests/test_canary_instrumentation_v3.py -k application_to_wire_mismatch -q --tb=short
```

Actual result: **eight failed, 58 deselected, 3.52 seconds**. Every expected
rejection instead returned successfully through the mock provider: altered and
missing `input`, `instructions`, `tools` and `text`, independently. All other
guards remained correct. The adapter source SHA-256 was still
`488cbdacb0397fb5c74f7eec6cfcfd25e9e88d5f25e293b1a2a76e6c92e8128c`.
This result was reported to the user before editing the adapter.

The correction snapshots only these four application fields before invoking the
unchanged client. It checks the pinned tuple/dataclass shapes structurally,
without importing application classes; rejects mixed, empty, ambiguous and
unsupported input representations; and copies only finite, unambiguous JSON
configuration values. The wire must contain all four fields, including empty
values when supplied by the application. Parsed comparison ignores object-key
ordering, whitespace, Unicode escaping and equivalent JSON numeric notation;
it preserves array order and distinguishes booleans from numbers. The snapshot
has no mutable aliases and is cleared in `finally`. It never enters the journal.

Validation runs on every attempt before `dispatch_provider_attempt`. A mismatch
uses the existing fixed `request_invalid` category, permanently closes the gate,
records no new dispatch, preserves earlier committed evidence, and returns the
existing fixed diagnostics. Real SDK retries with subsequently correct bodies
are still rejected by the gate. No production SDK construction, retry behaviour
or outgoing request mutation was introduced. The existing first-call shopper
check is unchanged; history authenticity remains a later driver responsibility.

New tests cover eight independent wire omissions/alterations, unsupported input
and configuration shapes, mutable application dictionaries, JSON boolean/number
distinctions, equivalent parsed JSON, byte-preserved earlier journal evidence,
and safe formatted exceptions/logs/replay. Pinned-client positives include empty
configuration, structured text, tools, strings, multiple historical messages,
multiple function outputs and A2 history after the approved A1/B1 sequence.
Hook-to-mock assertions compare request identity, bytes, raw headers and extensions.
Eight pinned-client negatives observe all three real SDK entries with zero
forwarding or dispatch records, even when retries restore the correct body.

| Follow-up check | Actual result |
| --- | --- |
| Adapter module, including new regressions | 89 passed, 30.09 seconds |
| Instrumentation/evidence/journal/fault suites | 383 passed, 91.88 seconds |
| Pinned OpenAI 3.3.1 instrumentation and historical SDK suites | 28 passed, no skips, 25.88 seconds |
| Full locked offline suite excluding listening controller tests | 3,392 passed, five optional skips, 237.07 seconds |
| Ruff across src/tests | Passed |
| Mypy | Passed, all 59 source files |
| Formatting | All eight Slice 3 Python files pass |
| Tracked and untracked whitespace | Passed |
| Other five Slice 3 files | SHA-256 unchanged from the start of this QA correction |
| Protected approved-base files | All 199 bytes/modes unchanged; HEAD and index unchanged |

The verification commands and stripped environments above were reused unchanged.
The 31 added adapter cases and 12 additional pinned SDK cases pass. Existing
adapter test bodies remain unchanged; the original pinned-client positive was
expanded into five input/configuration variants. A test setup initially assumed
A2 followed A1 directly; it was corrected to respect A1/B1/A2, and the complete
pinned SDK suites were rerun successfully. This was a test-only correction.
The five optional skips are the same modules/composition listed above; both SDK
modules separately ran with zero skips. The application-state and full source
composition checks remain optional and unexecuted here. The listening controller
module was excluded and no server was started. Existing spending, concurrency,
interruption, publication-fault and saved-replay regressions all pass.

An exact unified follow-up diff against the provisionally accepted nine-file
implementation is saved at `/private/tmp/c3b-slice3-request-integrity.patch` for
review. Its four baseline files were recovered and checked against SHA-256 values
captured before this investigation's first edit. It contains only the four paths
authorised for the correction; the repository still has exactly the original
nine-file Slice 3 scope. No new implementation files or contract changes occurred.

Remaining limitations are unchanged: the comparison establishes fidelity to the
application request, not the authenticity of earlier session history or source
approval. It intentionally accepts only the pinned input representation and JSON
configuration values. Mock callbacks and the containing process remain trusted.
No live compatibility, billing or Study result is claimed. Independent human QA
is required before publication; no commit, push, PR, merge or Slice 4 work occurs.

## Approved publication for independent QA

The user's later publication instruction supersedes the earlier commit/push/PR
restrictions above. It authorises one local commit named
`Add offline v3 provider instrumentation and request-integrity validation`, a
normal push of `feat/canary-runtime-v3-slice3`, and a PR titled
`Add definition-bound v3 provider instrumentation`. Its parent must be exactly
`93fbceaed1acfa3284190af39de2c3f0d6fa9abc`. Merge, auto-merge, Slice 4, servers,
credentials, live provider requests, judging and Study execution remain excluded.

- [x] Recheck exact nine-file scope, protected bytes and approved base.
- [x] Review complexity and request-validation boundaries without source changes.
- [x] Rerun focused, pinned SDK, full locked offline and static checks.
- [x] Commit once with the exact parent and verify committed bytes.
- [x] Push, open the PR and verify published head/base, scope and status.

Before publication, all 199 tracked files outside the five approved modifications
still match the approved base in bytes and executable modes. The index was empty,
the feature branch HEAD was exactly the approved base, and GitHub `main` was also
exactly that base. The remote feature branch did not exist. The harness environment
has 23 installed distributions matching its unchanged lock (excluding packaging
bootstrap tools); tests use the existing stripped environments above.

The request-integrity correction's per-file breakdown, before this publication
bookkeeping entry:

| File | Kind | Exact correction | Purpose |
| --- | --- | --- | --- |
| `src/harness/canary/instrumentation_v3.py` | Executable source | +102/-0 | Snapshot four application fields, map pinned input records, compare parsed JSON before intent, clear snapshot on exit |
| `tests/test_canary_instrumentation_v3.py` | Tests | +304/-1 | 31 added cases plus faithful request test helpers; no original test body changed |
| `tests/test_canary_instrumentation_v3_sdk.py` | Tests | +186/-24 | 12 additional cases; expand the pinned-client positive to five variants and supply the four fields in the SDK test double |
| `docs/plans/canary-runtime-v3-slice3.md` | Documentation | +102/-0 | Reproduction, mapping, correction, verification and remaining limitations |

The correction adds three private helpers (`_json_copy`, `_application_payload`,
`_same_json`) and one temporary per-call snapshot. It adds no public interface,
journal record or telemetry field. The wider Slice 3 interfaces remain the checked
provider binding/reservation/snapshot APIs and the two adapter classes documented
above. JSON-value copying and comparison are separate to prevent mutable aliases
and boolean/number equality mistakes. Application configuration, prepared-wire
guards and saved-record transitions validate distinct boundaries; application-to-
wire field comparison has one implementation. Guard freshness is deliberately
rechecked after durable intent. No unnecessary duplicate semantic validator or
concrete defect was found; executable source and tests remain exactly as accepted.

All ten final correction checks are confirmed by the focused and pinned-SDK reruns:

1. All eight originally reproduced alterations/omissions are rejected.
2. Parsed equivalence covers `input`, `instructions`, `tools` and `text`.
3. Strings, ResponseMessage tuples and FunctionCallOutput tuples match the pin.
4. A2/history and subsequent logical calls pass, including function outputs.
5. The original prepared request object, bytes, headers and extensions survive.
6. Mismatches create no dispatch intent and perform no provider forwarding.
7. Rejection permanently closes the dispatch gate, including later direct entry.
8. Actual SDK retries with restored valid bodies cannot bypass that rejection.
9. Evidence, fixed diagnostics and formatted exception/log output omit sensitive
   request content; no new request-content telemetry exists.
10. The opt-in profile leaves original Slice 2 records on the original replay
    path; existing synthetic legacy read/replay tests pass without migration.

Existing spending, unknown-liability accounting, concurrency, interruption,
stop/drain, publication-fault and saved-replay checks remain enabled and pass.

| Publication rerun | Actual result |
| --- | --- |
| Focused instrumentation/evidence/journal/fault suites | 383 passed, no skips, 92.59 seconds |
| Pinned OpenAI 3.3.1 instrumentation and historical SDK suites | 28 passed, no skips, 27.99 seconds |
| Full locked offline suite excluding controller module | 3,392 passed, five optional skips, 238.74 seconds |
| Ruff | Passed across src/tests |
| Mypy | Passed, all 59 source files |
| Formatting | All eight changed Python files pass |
| Whitespace and exact scope | Passed, including all four added files |

The full-suite skips are `test_canary_instrumentation_v3_sdk.py`,
`test_canary_sdk.py`, `test_canary_selection_state.py`, `test_canary_state.py`, and
the complete pinned CPython 3.13 source-composition check in
`test_canary_runtime_v3.py`. Both SDK modules passed separately with no skips.
The two application-state modules and full source-composition check remain
unexecuted here. `tests/test_canary_controller.py` was explicitly excluded; no
listening server or live test ran. All commands used the unchanged locked and
pinned environments and prefixes documented above. All eight Python file hashes
still match their provisionally accepted bytes; only this plan changed.

This is the checked pre-commit publication record. The last two actions above
follow this report; PR metadata and the final external report carry their actual
commit SHA, CI/review status and remote-byte confirmation. This plan will not
require a second commit to record its own publication.

## PR #28 independent QA follow-up: stop latch before journal synchronisation

Published review baseline: `f1ec3c3ed142ed4807341d5bdbed81d8526eb1e3`, sole parent
`93fbceaed1acfa3284190af39de2c3f0d6fa9abc`, PR
`https://github.com/beccawillss/ai-test-harness/pull/28`. The prior publication
completed with matching remote commit/tree/nine file blobs and modes; its
pre-publication milestones above are now marked complete. The user's new
authorisation permits this local offline correction only. **Do not commit, push,
amend the PR, resolve its review thread, merge or start Slice 4.** No servers,
credentials, live provider calls, judging or Study execution are permitted.

- [x] Confirm a clean local worktree at the exact reviewed commit.
- [x] Add and run a deterministic reproduction before modifying source.
- [x] Close the existing provider latch at public stop entry, before the mutex.
- [x] Add bounded contention, result-drain, failure and legacy regressions.
- [x] Rerun focused, pinned SDK, full locked offline and static verification.
- [x] Verify exact local diff and protected bytes; stop for independent human QA.

Reproduction command, using the stripped harness environment documented above:

```text
python -B -m pytest tests/test_canary_instrumentation_v3.py -k public_stop_closes_gate_before_waiting -q --tb=short
```

Against unchanged published source: **one failed, 89 deselected, 1.19 seconds**.
The test retains the original journal RLock while simulating durable recording.
A second thread calls public `stop()`. A context-manager observer sets an Event
at that thread's mutex-entry boundary, before delegating to the held original
RLock. At that exact point, the observed pair `(latch_closed, gate_rejected)` was
`(False, False)`: the dispatch latch remained open and the existing provider gate
check passed. This demonstrates admission through that gate, not a claim that a
second HTTP dispatch completed. No sleeps or lock-acquisition timing assumptions
are used. Waits/joins are bounded and cleanup releases the held operation.

The reproduction was reported before the source correction. The correction is
one executable line at the start of `CanaryJournal.stop()`:

```python
self._provider_gate.set()  # Close dispatch before waiting for journal I/O.
```

The existing synchronized stop path then records the same terminal evidence.
No new lock, scheduling loop, retry mechanism, asynchronous worker, record schema,
replay rule or interface is introduced. Invalid or failed stops cannot undo this
permanent latch. Legacy unprofiled stops still emit the original `stop` record
and code; their provider latch is unused by the legacy execution path. Historical
C1 source and behaviour remain untouched.

After correction the reproduction passes: **one passed, 89 deselected, 0.67
seconds**. The complete new regression selection passes **14 cases, 199
deselected, 4.02 seconds**. It covers both journal and transport stop while actual
`instrumented_result` publication retains the mutex, for completed responses and
eligible known-zero-usage HTTP 500 retries. The latch closes before lock entry;
later attempt entry is rejected with one original dispatch only. The already
dispatched result drains and retains known usage; stop publication then completes
with `operator_stop`, an error-finished call and operationally uncertain saved
evidence, without losing earlier committed bytes. A delegate-side Event lets stop
publication finish before the retry/return boundary, so record ordering is
deterministic without assuming RLock fairness.

Additional cases cover invalid stop codes and failures before/after visible stop
publication for both journal profiles. Every case retains the permanent latch and
original evidence prefix; any visible stop record remains valid on replay.
Legacy stop records retain all three original codes and the original schema.
The test observer wraps the existing RLock and introduces no replacement lock.

Final verification and the exact four-file local diff are recorded below.
The existing approved nine-file PR scope remains the outer boundary; no other
implementation, policy, application, dataset, fixture or historical file changes
are authorised.

| Local stop-correction verification | Actual result |
| --- | --- |
| New bounded stop/record/failure/legacy cases | 14 passed, 4.02 seconds |
| Focused instrumentation/evidence/journal/fault suites | 397 passed, no skips, 95.14 seconds |
| Pinned OpenAI 3.3.1 instrumentation and historical SDK suites | 28 passed, no skips, 25.50 seconds |
| Full locked offline suite excluding controller module | 3,406 passed, five optional skips, 241.14 seconds |
| Ruff | Passed across src/tests |
| Mypy | Passed, all 59 source files |
| Formatting | All eight Slice 3 Python files pass |
| Existing tests in the two modified modules | All 62 functions/classes unchanged by AST comparison |
| Published-head preservation | All 204 files outside the four local modifications match in bytes/modes |
| Approved-base preservation | All 199 protected files match in bytes/modes |
| Application source pin | HEAD is 3320e556540d3f95bee1e8509f13e558ce266b6c; Responses client unchanged |
| Harness environment | 23 installed distributions match the unchanged lock |

All verification uses the previously documented stripped offline environments and
commands. The pinned SDK module itself is unchanged; its actual SDK retries,
request-integrity negatives, history/function-output positives and historical
500/500/200 cases pass. The only lint follow-up annotated the test thread handlers'
intentional BaseException collection; it changed no executable statements.
The five full-suite skips are both SDK modules, both optional application-state
modules, and the complete pinned CPython 3.13 source-composition check. Both SDK
modules passed separately with zero skips; the two state modules and full source
composition remain unexecuted. `tests/test_canary_controller.py` was explicitly
excluded and no listening server ran. Final tracked whitespace checks pass.

Exact local patch against the reviewed PR head:
`/private/tmp/c3b-slice3-stop-latch.patch`. Only the four preferred files are
modified. The executable source delta is the single latch-setting line;
instrumentation tests add 157 lines, and journal tests add 63 lines. Documentation
records this reproduction and verification and marks the previously completed
publication steps accurately. The index is untouched and HEAD remains exactly
`f1ec3c3ed142ed4807341d5bdbed81d8526eb1e3`. The overall PR inventory is still four
additions and five modifications against its approved base.

**Recommendation: ready for independent human QA of this local patch.** No commit,
push, PR amendment, review-thread resolution, merge or live action was performed.

Remaining limitations: already-dispatched work may finish after dispatch closes;
the correction preserves its evidence rather than cancelling it. Public `stop()`
still waits for journal synchronisation to publish its durable terminal record.
Recording failure or process loss can prevent that record; the in-memory gate
cannot reopen, and persisted evidence remains inspection/save-only. The mock and
trusted-process limits above remain unchanged; these tests do not establish live
transport behaviour or hard real-time scheduling guarantees.

## Final operator-stop correction publication

The user's later instruction authorises one additional commit named
`Close v3 provider dispatch gate before journal stop locking` and a normal push
to the existing feature branch and PR #28. Its parent must remain exactly
`f1ec3c3ed142ed4807341d5bdbed81d8526eb1e3`; the original published commit is not
amended, squashed, rebased or rewritten. This publication approval supersedes the
preceding local-only restriction. Merge, auto-merge, Slice 4, credentials, servers,
live providers, judging and Study execution remain excluded.

The entire four-file patch first matched the previously verified local patch
byte for byte (SHA-256
`1a34cd857f14eae66889e54b47e3002784149391039548e4409f77ab2c99f3fc`). No further
executable source or test edits were needed. Only this publication record was
added. The 14 stop regressions were refreshed: **14 passed, 199 deselected, 3.76
seconds**. Ruff, mypy (59 source files), formatting (all eight Slice 3 Python
files) and whitespace checks pass. The unchanged executable/test bytes retain
the reported **397 focused passes, 28 pinned SDK mock passes and 3,406 full
offline passes with five optional skips**; those broader suites were not rerun
during this publication step. Listening-server controller tests remain excluded.

Pre-publication checks confirm all nine requested properties: gate closure before
mutex acquisition; no additional locks/schemas/replay changes; all 14 regressions;
no later retry/intent admission; in-flight result drain; permanent closure after
stop-record failures; unchanged legacy interpretation; retained historical retry,
request-integrity, spending, privacy and replay results; and unchanged protected
fingerprints, application pins, fixtures, locks and Study data. All 204 other
published-head files and all 199 protected approved-base files match in bytes and
executable modes. Remote main and feature refs still match their approved SHAs.

The existing operator-stop thread `PRRT_kwDOTj88Ls66ZIN6` is open and must remain
open for independent verification of the published correction. Publication will
update only the PR description, leaving thread resolution to human QA. This is
the pre-commit record; the final external report and PR metadata will give the
new commit SHA, exact parent, remote-byte confirmation and current review status.
