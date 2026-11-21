# C3b Slice 2: offline durable canary journal

Approved baseline: `a68b13ea2a09345a0ad3de1ce486679ddb00c375`.
Worktree: `/private/tmp/ai-test-harness-canary-runtime-v3-slice2`.
Branch: `feat/canary-runtime-v3-slice2`. Approved pre-FIFO-correction PR #27 head:
`faa8b514f82ee6262a71c9a08f088d5129ee97e4`. Human QA now authorises one third commit,
`Reject blocking special files during canary evidence inspection`, its push to the
existing branch and a PR description update. Only the journal, its fault tests
and this plan may change; preserve the six-file PR inventory. Keep the existing
GitHub review thread open. Do not amend either published commit, merge, enable
auto-merge, begin Slice 3 or run live operations. Earlier permission notes below
describe their respective historical milestones.

The user's implementation approval supersedes the initial plan's proposed seal
repair: recovery never writes to the authoritative registry, including a missing
completion seal. It exports existing validated evidence only.

## Milestones

- [x] 1. Private registry, exclusive reservations and durable atomic publication.
- [x] 2. Privacy-safe evidence, accounting, assessments and policy decisions.
- [x] 3. Inspection, strictly save-only export, fault matrix and regressions.

## Scope and invariants

Exactly six additions: `journal_v3.py`, `evidence_v3.py`, their three test modules
and this plan. Existing source, tests, locks, datasets and approved identities
remain untouched. No servers, workers, provider calls, judges, credentials,
operator evidence, authenticated approvals or controller integration.

The filesystem journal is canary-specific. Records are immutable canonical JSON
checksum envelopes with sequence/predecessor links. Publication uses an exclusive
0600 temporary file, file fsync, non-replacing hard link and directory fsync.
Private directory creation is synced before acknowledgment. Any ambiguous write
closes the writer gate. Temporary files never become committed evidence by scan.

One POSIX writer lock serializes the registry. Run directories and approval claims
are permanent exclusive reservations, including failed initialization. Turn and
attempt reservations follow the frozen definition. No existing run has a producer
reopen API. Policy results come only from unchanged `decide()`; locally measured
accounting/recording facts constrain supplied operational guard claims.

Integrity and accounting reconciliation establish neither provider authentication
nor source approval. Receipt provenance remains claimed. Source authorisation,
authenticated provider evidence and live authority remain unavailable.

Business diagnostics are validated before projection; only the five reviewed
categories survive. Error prose and validation identifier suffixes are discarded.
Fixed parser placeholders exist only in memory. Evidence round-trips must preserve
the approved assessment. Unknown/malformed errors remain operational errors.

Completion requires all four outcomes, reconciled known usage, a durable policy
COMPLETE decision and an explicit safe shutdown observation. That observation is
structurally validated supplied evidence, not independent worker authentication.
Human review remains PENDING. Inspection is read-only; export never repairs,
reassesses, seals or resumes the original. Missing seals are explicit.

## Verification plan

Test competing writers/approval reuse, every publication failure boundary, partial
writes, process death, corrupted/missing/conflicting records, symlink substitution,
unknown usage, provider identity collisions, FAIL continuation, ERROR termination,
partial inspection, save-only export and secret sentinels. Run new suites, existing
canary/Study-journal regressions and the full locked offline suite, excluding the
listening-server controller module. Record all skips/exclusions. Run Ruff, mypy,
changed-file/repository formatting and Git whitespace/protected-byte checks.

## Records and API contracts

The concrete schema is `nonstudy-canary-journal-v3-v1`; the selected immutable
definition's existing `nonstudy-canary-v3-reserved-v1` binding remains unchanged.
`initialize_registry(path)` exclusively creates a private root, runs/approvals
directories, lock and registry binding. `load_registry(path)` checks the bound
absolute path, device/inodes, ownership and privacy. Copies are not authorities.

`CanaryJournal(registry, run_id, approval_id, source_receipt=...)` requires explicit
v3 selection and validates the supplied receipt's structure and pinned definition.
It does not perform source matching or authenticate the receipt. It exclusively
claims the run directory and approval identity while holding the registry writer
lock. Partial claims are never rolled back; one approval cannot move to another
run. The root/claims must remain available; there is no alternate-root fallback.

The fixed record kinds, in their canary lifecycle, are:

1. `manifest`: selected binding, complete supplied source receipt and digest,
   registry/run/approval identities, and false authority/authentication flags.
2. `decision`: supplied and effective guards, accounting snapshot and exact pure
   policy result. Derived counters cannot be reduced by caller claims; additional
   supplied unknown liability or spending can only tighten the policy guard.
3. `turn_reserved`: consumes the last durable ADVANCE decision's next slot.
4. `call_reserved`, `provider_dispatch`, `provider_result`, `call_completed`:
   unique `(slot, logical_call, attempt)` evidence, capped by frozen definition
   shape, with safe provider observations and the unchanged pricing estimator.
5. `chat`, `trace` or `evidence_error`: public projections. Trace records include
   the matching supplied reread's projected digest. Neither receipt nor reread
   matching authenticates external HTTP/provider work.
6. `assessment`, `outcome`: append-only numbered assessment revisions and an
   outcome bound to its exact revision. The existing assessor and `record_outcome`
   construct the policy-compatible data; no alternate decision rules exist.
7. `stop`, `shutdown`: fixed terminal categories and an explicit supplied shutdown
   observation. Shutdown booleans are checked strictly; a supplied safe observation
   remains distinct from independent worker/process verification.
8. `completion`, `completion_ack`: core bundle digest covering all chats, traces
   and assessment revisions, final state/accounting and pending human review.
   The acknowledgement is attempted only after the completion seal's sync returns.
   A crash before it leaves an incomplete, unacknowledged seal. A visible ack after
   its own sync failure still proves the preceding core seal was already synced;
   no further work can follow it. Completion never means quality PASS or approval.

Public producer methods follow those record names: `record_decision`,
`reserve_turn`, `reserve_call`, `record_dispatch`, `record_provider_result`,
`complete_call`, `record_chat`, `record_trace`, `assess_turn`, `complete_turn`,
`stop`, `record_shutdown`, `seal` and `close`. Use a context manager for interruption
cleanup. No method sends a request. Closing or losing a producer never permits a
replacement producer for that run. Forked producers are rejected.

`inspect_run(registry, run_id)` takes a shared nonblocking lock and reads a stable
snapshot. An active producer is reported as busy rather than inventing a stable
snapshot. It verifies canonical checksum envelopes, predecessor links, exact
record schemas, identities and existing deterministic assessments/decisions.
Reports distinguish `completed`, `incomplete`, `corrupt` and
`operationally_uncertain`, with separate mechanical/operational assessments,
human PENDING, seal/ack status, reconciliation, pending temporaries and the validated
record prefix. Corrupt bytes and arbitrary filenames never enter the report.

`recover_save_only(registry, run_id, destination)` takes the exclusive lock and
exports that report/prefix as a private checksum-enveloped `report.json` in a new
directory. Partial/corrupt exports are explicitly labelled; they are not completed
results. The destination must be separate from the registry, repositories and Study
storage. Existing outputs and symlink/substituted destinations are rejected.
There is no execution callback, target/judge factory, missing-result reconstruction,
assessment creation or seal repair. Verification recomputes existing deterministic
records only. Source records, claims, permissions and missing seals stay unchanged.

## Tested failure matrix

| Fault | Required observable result |
| --- | --- |
| Competing processes / duplicate approval | Busy while writer active; approval still consumed after close |
| Partial initialization | Existing root/run/approval never reused or rolled back |
| Partial write, ENOSPC, file fsync, link failure | No partial final record; prior bytes unchanged; writer closed |
| Post-link directory fsync failure | Whole visible record retained, producer closed; no overwrite/retry |
| Completion sync/death before ack | Explicit incomplete seal; recovery cannot certify or repair it |
| Temporary cleanup failure | Whole committed record survives; pending file counted, never promoted |
| Process death at each record kind / SIGKILL in flight | Reservations persist; no producer reopen; unresolved liability retained |
| Missing/truncated/duplicate-key/noncanonical/conflicting records | Corrupt report, no completion certification, validated-prefix-only export |
| Symlink, inode/private-permission or approval substitution | Subsequent producer operation fails closed |
| Orphan/duplicate attempt or result | No conflicting record published; producer closed |
| Unknown usage / incomplete logical call / provider error | Unknown/error visible; claimed-ready guards cannot advance |
| Over-budget known usage / external extra liability | Existing pure policy returns STOP/ERROR |
| Quality FAIL with complete guards | Next original slot scheduled, FAIL preserved |
| Unknown business errors / malformed evidence | Fixed ERROR category; earlier safe evidence retained |
| Five reviewed business categories | Original and restored assessments identical, private diagnostics absent |
| Failed/substituted export | Private partial output; source untouched; retry requires a new destination |

The fault tests model syscall failure and process death on the local filesystem;
they do not claim to simulate a physical power failure or validate network mounts.

## Progress and results

- Exact approved commit fetched and clean isolated worktree created; no existing
  development worktree changed. Git metadata operations required sandbox approval.
- `uv sync --locked --offline` succeeded with cached packages, CPython 3.12.13;
  accessing uv's cache required sandbox approval. Lockfile unchanged. uv emitted
  its existing build-tool version warning (uv 0.12.5 versus uv-build <0.12).
- Initial evidence/lifecycle suite: 72 passed. The expanded fault suite initially
  found that a valid completion prefix plus an unexpected trailing file still
  exposed an acknowledged-completion flag. Status was already corrupt; the flag
  now also fails closed, with separate explicit completion certification.
- Completion uses a seal followed by an acknowledgement record. The latter can
  only be created after the seal's file/directory sync returned. A visible seal
  without acknowledgement cannot certify completion. Recovery never adds either.
- Ruff across src/tests and mypy across 58 source files passed before the final
  fault-matrix additions; final results are recorded below when complete.

Initial Slice 2 verification (2026-11-21), using the locked CPython 3.12.13
environment; superseded by the retry-correction verification below:

| Check | Actual result |
| --- | --- |
| New journal/evidence/fault suites | **132 passed**, no skips, 24.63 seconds |
| Existing canary/Study-journal/execution-control regressions | **571 passed, 4 skipped**, 28.98 seconds |
| Full locked offline suite | **3,141 passed, 4 skipped**, 169.39 seconds |
| `ruff check src tests` | Passed |
| `mypy src` | Passed, 58 source files |
| Formatting, five added Python files | Passed |
| Repository-wide formatting | Two unchanged baseline failures, detailed below |
| Git whitespace checks | Passed, tracked diff and all six additions |
| Approved baseline byte/mode verification | All **198 tracked files** unchanged |
| Change inventory | Exactly the six approved additions; no tracked modifications |

Commands ran with a stripped environment (`env -i PATH=/usr/bin:/bin
PYTHONDONTWRITEBYTECODE=1`) and `.venv/bin/python -B -m pytest`:

```text
tests/test_canary_journal_v3.py tests/test_canary_evidence_v3.py
tests/test_canary_journal_v3_faults.py -q --tb=short -rs

tests/test_canary.py tests/test_canary_acceptance.py
tests/test_canary_execution_policy.py tests/test_canary_preparation.py
tests/test_canary_runtime_v3.py tests/test_canary_sdk.py
tests/test_canary_selection_state.py tests/test_canary_selection_v3.py
tests/test_canary_state.py tests/test_study_journal.py
tests/test_execution_control.py -q --tb=short -rs

-q --tb=short -rs --ignore=tests/test_canary_controller.py
```

The listening-server controller module was explicitly excluded, not reported as a
skip. The four actual skips in both existing/full runs were:

- `test_canary_sdk.py`: optional OpenAI SDK is not installed in the harness lock
  environment. No dependency download or external SDK run was attempted.
- `test_canary_selection_state.py` and `test_canary_state.py`: optional pinned
  application runtime is not loaded.
- `test_canary_runtime_v3.py`: complete source-composition check needs the optional
  pinned CPython 3.13 application runtime.

Repository-wide `ruff format --check src tests` flags only
`src/harness/targets/base.py` and `tests/test_dataset.py`. Both match approved HEAD
byte-for-byte; these same baseline issues were documented in Slice 1. Neither was
modified. `git diff --check` is clean. Each untracked addition was also checked
using `git diff --no-index --check /dev/null <file>`: no whitespace diagnostics
(exit 1 denotes the expected additions). Independent trailing-whitespace checks
passed. All new Python files pass Ruff formatting.

All five approved v2.1/v3 fingerprints were independently recomputed through
`resolve_definition(V3)` and match Slice 1. The application pin and fixture-hash
bindings are unchanged. Study v1 still contains 50 cases with fingerprint
`4a0e40d6dce4b78cc194352bf23d69dabcc8fe3c0f440d50f2cce2bd6a956028`.
No actual application fixture/operator evidence was accessed in this slice.
Existing development worktree state is preserved; the Slice 1 worktree remains
clean. The implementation worktree's HEAD is exactly the approved main revision.

**Recommendation: ready for human QA of this offline six-file diff.** Review the
record/replay validator, partial-initialization claims, seal/ack ordering, business
error placeholders, false authority flags and strictly non-mutating export first.
The fault suite exercises synthetic child processes only. No target worker/server,
provider, judge or live canary ran. No commit, push, PR or merge was created.

## Later integration risks

Local POSIX filesystem/fsync/hard-link and cooperative-process assumptions apply;
whole-registry rollback by its owner cannot be detected without an external anchor.
All uses of an approval must share its authoritative registry. A lost registry or
copied backup does not establish unused authority. Future instrumentation must
capture actual call boundaries without changing request bytes or SDK retries,
verify shutdown, authenticate source/approval independently and supply measured
external guards. No C3a source-gate exception is introduced here.

Local accounting cannot detect provider work that was never instrumented, prove
external event origin, verify actual billing or independently establish safe worker
shutdown. The report explicitly preserves those boundaries. Later instrumentation
must bind real request/result identities, enforce attempt-level guards, retain
request bytes/retry allowances and establish separately reviewed source/approval
authentication. The optional SDK/application checks remain unexercised in this
slice; this is not evidence of live compatibility.

## Independent QA correction: provider retry semantics

Status: focused offline correction authorised within the same six additions.
Protected C1/Study/controller/driver/policy/lock files remain unchanged.

- [x] Reproduce the mismatch before changing implementation.
- [x] Separate attempt retry eligibility from accounting completeness.
- [x] Re-run new, historical, fault and full offline suites plus static checks.
- [x] Record results and stop for independent QA; no publication.

The new deterministic regression first drives the unchanged historical
`ProviderTransport` using `httpx.MockTransport`: HTTP 500, HTTP 500, HTTP 200,
all within one logical reservation. It observes three attempts and two unknown
billing liabilities; another logical reservation is rejected. The same sequence
against the original Slice 2 implementation **failed at dispatch of attempt 2**
(`1 failed`, 0.55 seconds). After correction the reproduction passes.

Root cause: accounting treated every non-successful attempt as a terminal error,
and the intra-call retry check used run-wide unknown/error counters. Conversely,
successful results did not prevent additional attempts before `complete_call`.
The prior multiple-success test masked both issues.

Historical source checks confirm `guard(allow_unknown=True)` at the existing
transport-attempt boundary, but the normal guard at the next logical reservation.
Billing exclusions and ambiguous transport stop the historical store. The optional
installed-SDK regression also explicitly asserts two SDK retries and unchanged
request bytes. Cached OpenAI 2.45.0 source was inspected read-only: SDK defaults
retry HTTP 408/409/429/5xx and recognise `x-should-retry`. This cache inspection is
not a claim that the optional pinned application/SDK composition ran.

Minimum new persisted scalars in `evidence_v3.py`:

- `error_category`: `none`, `http_error`, `server_error`, `server_overloaded`,
  `rate_limit_exceeded`, `billing`, `authentication` or `unreviewed`.
- `retry_directive`: absent, `true`, `false` or fixed `unreviewed`, supplied through
  the optional `should_retry_header` keyword. No raw header or error text is saved.
- Attempt `outcome` distinguishes `completed`, `retryable_http_failure`,
  `operational_error` and `ambiguous_transport`.

Eligibility requires a definitively supplied HTTP failure at 408/409/429/5xx,
a structured error with an absent or reviewed nonterminal code/type, compatible
model/status/tier and no retry denial. A status or affirmative header alone is
insufficient. All five historical spend/quota codes remain terminal, including
when observed as error types. Authentication, unreviewed codes/types, inconsistent
response/configuration evidence and malformed/negative retry directives are also
terminal. Fixed `unreviewed` sentinels retain rejected model/status context without
echoing arbitrary values. `true` does not broaden the eligible HTTP status set.

`journal_v3.py` accepts an attempt after the first only when the immediately prior
attempt in the **same reserved call/slot** has a complete recorded eligible HTTP
failure. Unmatched dispatch, success, terminal error or exhausted three-attempt
limit rejects it. No external request or SDK retry is created by this operation.

Accounting retains every attempt and every unknown estimate. It reports retryable
HTTP failures separately; a later successful result does not erase their usage
or unknown billing. Fully known failures followed by success can reconcile.
Terminal/ambiguous attempts and a logical call ending with an exhausted retryable
failure remain operational errors. Next-call and turn guards remain strict;
unknown liability still blocks them. `decide()` and all its rules are unchanged.

The previous two-call test now uses realistic 500/500/200 sequences with explicit
known zero usage on failed attempts. Tests additionally cover unknown billing,
post-success retry, ambiguity, billing/authentication exclusions, fourth attempts,
misattribution, retry denial, malformed metadata, exhausted failures and operator
stop. The unpublished journal schema's new fields are required on replay; earlier
synthetic pre-correction records are not silently migrated or repaired.

Later instrumentation must supply the fully read HTTP result and actual retry
header, keep SDK retries at two, and enforce existing per-attempt safety/spending
guards. Persisted classifications remain supplied evidence, not independent
authentication or authority. Unknown error types intentionally fail closed even
if an SDK would otherwise retry them.

Correction verification (same stripped environment and commands documented above):

| Check | Actual result |
| --- | --- |
| Reproduction before correction | **1 failed**, attempt 2 rejected, 0.55 seconds |
| New journal/evidence/fault suites after correction | **204 passed**, no skips, 25.70 seconds |
| Existing canary/Study-journal/execution-control suites | **571 passed, 4 skipped**, 29.27 seconds |
| Full locked offline suite | **3,213 passed, 4 skipped**, 171.95 seconds |
| Ruff lint across src/tests | Passed |
| Mypy | Passed, 58 source files |
| Formatting, five added Python files | Passed |
| Repository-wide formatting | Only the same two untouched baseline failures |
| Git whitespace checks | Passed, including all six additions |
| Protected byte/mode verification | All 198 tracked baseline files unchanged |

The 72 added cases include the regression reproducing historical transport
behaviour without requiring SDK/application installation. The optional installed
SDK/application checks remain the same four explicit skips listed above; no new
dependencies or external runtime were used. The listening-server controller
module remains explicitly excluded. Existing fault injection, process-death,
strict save-only recovery and privacy tests all pass in the 204-case suite.

The original five v2.1/v3 fingerprints, application revision and 50-case Study
fingerprint were recomputed and remain unchanged. HEAD remains exact approved
main `a68b13ea2a09345a0ad3de1ce486679ddb00c375`; inventory remains exactly the six
approved additions. This correction revises the two implementation files, their
two direct test modules and this plan. The existing fault-test file was rerun
without change. No protected files were modified, no real provider/network calls,
servers, judges or live execution ran, and no commit or publication was created.

**Recommendation: ready for independent QA of the focused retry correction.**
The 500/500/200 sequence is now representable with all three results and both
unknown liabilities preserved. Unknown billing still blocks the next logical
call and makes the unchanged policy stop before another turn. Eligible known-zero
failures followed by success can reconcile and advance normally. This remains
offline supplied-evidence recording; SDK/controller composition and independent
provider/source authentication remain future integration work.

## Local commit preparation and final QA verification

The latest human instruction authorises exactly one local commit after these
checks, using the message at the top of this plan. Earlier statements that no
commit was authorised describe earlier milestones. Push, PR creation, merge,
Slice 3, servers, SDK execution, provider requests, judging and Study execution
remain outside this authorisation.

- [x] Confirm exact parent `a68b13ea2a09345a0ad3de1ce486679ddb00c375`.
- [x] Confirm exactly six additions and all 198 baseline files unchanged in bytes
  and executable modes, including C1, policies, locks, fixtures and Study files.
- [x] Re-run retry eligibility, terminal exclusions, unknown billing retention,
  no retry after success, call/slot attribution and maximum-three-attempt tests.
- [x] Independently exercise saved replay after rewriting checksums and links.
- [x] Re-run focused/full offline suites, fault injection and static checks.
- [x] Recompute approved C1/v2.1/v3 fingerprints and inspect Study data only.

The final gate adds 13 regressions in the existing fault-test addition; no
implementation change was needed. Each starts with a completed, reconciled
journal containing realistic 500/500/200 retries, closes the producer, changes
saved records, and recomputes every checksum, sequence and predecessor link.
The test independently checks those envelopes and links before inspection.
The scanner rejects at the exact first semantically invalid record, proving that
rejection is independent of producer memory and checksum/chain failures.

Cases cover forged negative, unreviewed and raw retry directives, forged billing
eligibility, consistent terminal denial/billing evidence followed by a retry,
retry after success, ambiguous/missing results, duplicate/fourth attempts and
wrong call/slot attribution. Inspection and save-only export both report corrupt
evidence, preserve only the validated prefix, withhold completion and authority,
exclude raw forged directives and leave the authoritative registry unchanged.
Checksums cannot authenticate a fully self-consistent fabricated history; this
continues to require an independent external authority/anchor.

Final results, using the same stripped-environment pytest commands above:

| Check | Actual result |
| --- | --- |
| New journal/evidence/fault suites | **217 passed**, no skips, 34.84 seconds |
| Existing canary/Study-journal/execution-control suites | **571 passed, 4 skipped**, 32.17 seconds |
| Full locked offline suite | **3,226 passed, 4 skipped**, 179.56 seconds |
| Added saved-replay gate alone | **13 passed**, 6.06 seconds |
| Ruff lint across src/tests | Passed |
| Mypy | Passed, 58 source files |
| Formatting, five added Python files | Passed |
| Repository-wide formatting | Only the same two untouched baseline failures |
| Git whitespace and six-file inventory checks | Passed |
| Protected baseline byte/mode verification | All 198 tracked files unchanged |

The four optional SDK/application skips and explicit exclusion of the
listening-server controller module are unchanged from the earlier verification.
No SDK was installed or executed. The historical retry reproduction uses only
the existing recorder and in-memory MockTransport. All offline fault injection
and interruption checks passed. No server, real provider request, judge, live
canary or Study run was invoked.

`resolve_definition(C1)` and `resolve_definition(V3)` independently recompute and
validate the approved fingerprints. The application revision and both fixture
hash bindings are unchanged. Actual application fixture bytes were not accessed.
Read-only dataset loading confirms the unchanged 50-case Study fingerprint
`4a0e40d6dce4b78cc194352bf23d69dabcc8fe3c0f440d50f2cce2bd6a956028`.
The existing development worktree's unrelated changes were not touched, and the
Slice 1 worktree remains clean.

The staged diff must contain only these six additions; the local commit must be
a direct child of the exact approved base. Verify its inventory, parent and clean
worktree after creation, then stop for human review. Proposed PR title is the
approved commit message; its description should cover the offline durable
journal, privacy-safe evidence, bounded retry/accounting semantics, saved-replay
validation, tests and the POSIX/authentication/optional-runtime limitations above.

## PR #27 QA correction: known-spending reservation boundaries

The initial investigation instruction authorised this correction within the
existing six-file Slice 2 scope only, with no commit, push, merge or Slice 3.
The published head stayed `036fe6473ee625c48b239f2b52ba80504e25c818` during that
investigation; this section records its uncommitted review. Protected source,
approved policies, locks, fixture-hash bindings and Study artifacts remained
unchanged. The later publication authorisation is recorded at the top and below.

- [x] Reproduce both reservation gaps against the published implementation.
- [x] Add the smallest shared transition check without changing `decide()`.
- [x] Verify exact, above and immediately-below threshold behavior, accumulated
  spending, unknown liability and independently reconstructed saved histories.
- [x] Re-run new, existing and full offline suites, fault injection and static
  checks; recompute protected identities and report for independent human QA.

The initial synthetic regression used the frozen estimator, with one million
input tokens and zero output tokens yielding exactly $5 under conservative
long-context pricing. One fewer/more input token yields $4.999995/$5.000005.
Before the implementation correction, both new-call and same-call eligible-retry
reservations were accepted at $5 and above: **4 failed, 2 passed** in 1.16 seconds.
Each failure was `DID NOT RAISE JournalError` at the prohibited reservation. Both
below-threshold controls passed. No provider requests or SDK execution occurred.

Root cause: the locally known cost was supplied to the pure policy only at the
next decision. The within-turn `call_reserved` and `provider_dispatch` transitions
checked identities, accounting completeness or retry eligibility but omitted the
historical C1 known-subtotal pause. C1's existing guard checks the subtotal even
when retry unknown billing is allowed.

The correction adds one four-line precondition to the shared `_apply` validator:
for `call_reserved` or `provider_dispatch`, reject when the run-wide locally known
`estimated_subtotal_usd` is at least `LIMITS.estimated_pause_usd`, using Decimal and
the unchanged frozen $5 limit. This covers both producer and saved-record replay.
It does not change the pure decision policy, pricing, retry eligibility, terminal
exclusions, limits, record schema or observation classifications. It adds no SDK
retry, dispatch, restart or recovery behavior.

The existing `_record` failure path permanently closes the producer on rejection.
No rejected reservation is published. The result that reached the threshold, its
cost and its completed/retryable classification stay unchanged. Subsequent stop
records are rejected by the closed producer; existing single-use reservations
still prevent producer reopening. Result, call completion and evidence saving
remain recordable after reaching $5 until a prohibited reservation is attempted;
the unchanged policy still determines STOP at the next decision.

The 16 new tests cover both boundaries at $4.999995, $5 and $5.000005, a known
subtotal reaching the pause despite another attempt's unknown liability, sums
across multiple calls/retries/turns, permanent closure and unchanged prior bytes.
Four fully checksummed/rechained saved-history regressions replace the earlier
result with an internally valid $5-or-above observation and prove the scanner
rejects the following reservation while retaining that result in the validated
prefix. Inspection/export remain read-only and cannot repair those histories.
Histories containing previously accepted over-threshold reservations are now
explicitly corrupt; no automatic migration or paid replay is available.

The isolated new spending gate passed **16 tests** in 2.59 seconds. Existing
500/500/200 unknown-billing semantics and all thirteen forged-retry replay cases
must remain covered by the complete offline rerun. A below-threshold retry may
remain representable despite earlier unknown usage; later success cannot erase
that liability or permit a new logical call. A known subtotal at $5 must stop even
when `estimated_total_usd` remains unknown.

Future instrumentation must still independently verify operator controls, budget
headroom and actual dispatch eligibility immediately before every network
attempt. This local supplied-evidence precondition does not authenticate those
controls or reserve prospective spend, and cannot prevent a single already-started
attempt from itself reaching or exceeding $5.

Final verification used the same stripped environment and pytest commands
documented above, plus the isolated `-k known_spending_pause` regression gate:

| Check | Actual result |
| --- | --- |
| Before correction, both boundaries at/below/above $5 | **4 failed, 2 passed**, 1.16 seconds |
| New spending-boundary/replay tests after correction | **16 passed**, 2.59 seconds |
| Complete journal/evidence/fault suites | **233 passed**, no skips, 35.99 seconds |
| Existing canary/Study-journal/execution-control suites | **571 passed, 4 skipped**, 30.61 seconds |
| Full locked offline suite | **3,242 passed, 4 skipped**, 180.89 seconds |
| Ruff lint across src/tests | Passed |
| Mypy | Passed, 58 source files |
| Formatting, five Slice 2 Python files | Passed |
| Repository-wide formatting | Same two unchanged baseline failures |
| Git whitespace checks | Passed |
| Protected identities and byte/mode checks | All 198 approved-base files unchanged |

The full new suite retains the historical 500/500/200 regression and all thirteen
forged-retry replay cases. Independent AST comparison confirms every pre-existing
function/test body in both modified test modules is unchanged. Existing fault
injection, crash/interruption, concurrency, privacy and save-only recovery checks
all pass. The listening-server controller module remains explicitly excluded;
the same four optional SDK/application checks remain skipped. No SDK, server,
provider, judge or Study execution was invoked.

The C1/v2.1/v3 fingerprints, application pin, fixture-hash bindings, locks and
50-case Study dataset fingerprint were independently checked and remain unchanged.
No actual application fixture or private operator evidence was accessed. Changes
relative to published head are confined to `journal_v3.py`, its two existing test
modules and this plan, all within the existing six additions. `evidence_v3.py`
and its tests are unchanged. HEAD and the index remain unchanged; no commit,
push, merge, remote PR update or Slice 3 work occurred.

**Prior recommendation: ready for human QA of the uncommitted correction.**
At that review, the published PR still contained the original head and did not
contain this fix. The review covered the four-line shared transition precondition,
retained threshold-reaching observations, permanent producer closure and replay
rejection at the first prohibited reservation before commit/publication approval.
Filesystem, supplied-evidence authenticity, external billing/operator controls and
prospective per-attempt budget verification retain the boundaries documented above.

## Reviewed spending correction: authorised publication

Human QA accepted the reported correction and authorised one additional commit,
`Enforce canary spending pause at reservation boundaries`, on the existing feature
branch and PR #27. Its parent must be the unchanged published commit
`036fe6473ee625c48b239f2b52ba80504e25c818`; the approved main base remains
`a68b13ea2a09345a0ad3de1ce486679ddb00c375`. Do not amend or rewrite either commit.

Only these four files may differ from the pre-correction head: `journal_v3.py`,
`test_canary_journal_v3.py`, `test_canary_journal_v3_faults.py` and this plan. The
complete PR must still contain exactly its six approved additions and no changes
to any of the 198 files tracked at the approved base.

Publication verification reran the unchanged reviewed implementation:

| Check | Actual result |
| --- | --- |
| Journal/evidence/fault suites | **233 passed**, 36.29 seconds |
| Full locked offline suite | **3,242 passed, 4 skipped**, 181.25 seconds |
| Sixteen spending tests, historical retries and thirteen saved-replay regressions | Passed in both reruns |
| Ruff lint across src/tests | Passed |
| Mypy | Passed, 58 source files |
| Formatting, five Slice 2 Python files | Passed |
| Repository-wide formatting | Same two unchanged baseline failures |
| Protected identities, original regression bodies and whitespace | Passed |

The listening-server controller module was explicitly excluded. The same four
optional SDK/application checks were skipped; no SDK/application execution was
enabled. All 198 baseline file bytes and executable modes, approved fingerprints,
source/application pins, fixture-hash bindings, dependency locks and the 50-case
Study dataset identity remain unchanged. Actual application fixtures and private
operator evidence were not accessed; no credential-shaped literals are included.

The four-line source precondition is unchanged from the reviewed correction.
Producer rejection and saved replay both enforce the known subtotal pause, retain
threshold-reaching results and unknown liabilities, and preserve the unchanged
`decide()` and SDK retry semantics. Future real dispatch still requires independent
operator, headroom and eligibility checks immediately before each network attempt.

Stage exactly the four authorised files, verify staged bytes and whitespace, then
create and push only the additional commit. Update the existing PR description
with these safeguards and final totals. Verify the remote head/parent, exact
four-file correction, six-file PR inventory, published blob identities,
mergeability and CI status after publication. Stop for final human QA without
merging, auto-merge, Slice 3, servers, provider requests, judging or Study execution.

## PR #27 QA correction: nonblocking special-file inspection

The spending correction is accepted. The initial investigation authorised local
work only on the unresolved automated review finding at `_read`, with no commit,
push or remote-thread mutation. Published HEAD stayed
`faa8b514f82ee6262a71c9a08f088d5129ee97e4` during that investigation.

Reviewed the existing [GitHub finding](https://github.com/beccawillss/ai-test-harness/pull/27#discussion_r4652597012),
thread `PRRT_kwDOTj88Ls66WivM`, marked unresolved at the published head. It identifies
an owner-private FIFO substituted for `000000.json`: the blocking read-only open
waits for a writer before the later descriptor type check can reject it. That
blocks inspection/recovery while holding the registry lock, and producer record
integrity validation has the same vulnerability.

- [x] Reproduce inspection, save-only recovery and producer validation in isolated
  subprocesses with strict timeouts and bounded termination/reaping.
- [x] Apply only nonblocking open flags; retain descriptor type/privacy validation,
  symlink exclusion, canonical JSON, checksum and chain semantics.
- [x] Test normal regular reads, fixed diagnostics, first/latest-record substitution,
  withheld completion, immutable corrupt-source export and permanent producer closure.
- [x] Re-run focused/full offline suites and static checks, verify protected files
  and identities, then return the uncommitted diff for human QA.

Before the fix, the three new manifest-substitution regressions all reached their
`special-file-ready` marker, then exceeded their five-second timeout: **3 failed**
in 16.43 seconds. The parent killed and reaped each isolated child, so pytest
itself never performed a potentially blocking record open. No FIFO writer was
connected. Inspection, save-only recovery and producer stop/integrity validation
were separately reproduced against the unchanged published `_read`.

The source correction adds `os.O_NONBLOCK` to the existing `os.O_RDONLY |
os.O_NOFOLLOW` open. The existing `_private(os.fstat(stream.fileno()))` still checks
the opened descriptor for regular type, owner and private permissions before
`stream.read()`. Rejection closes the descriptor through the existing context
manager and surfaces only fixed `invalid_record` diagnostics. No path-based type
precheck replaces descriptor validation. Canonical JSON, duplicate-key validation,
checksum comparison, record-chain validation and all state/decision rules remain
unchanged. The source change consists only of the flag, formatting and an
explanatory comment.

Eight new subprocess regressions cover direct reads, inspection, save-only recovery
and producer integrity validation at the manifest and latest-record boundaries.
Each first proves normal committed records load. Read-only controls start from
completed journals, including a final completion-ack substitution, and then require
corrupt reports with no completion, reconciliation or authority. Corrupt-source
regular bytes and FIFO identity/type/permissions stay unchanged by inspection or
export. Producer failures must close the gate, including after test-only restoration
of the original regular bytes; a replacement producer for the run remains rejected.
Every child has a five-second `communicate` timeout, with kill/reap cleanup also
bounded to five seconds. No unbounded `readline` or FIFO I/O runs in the parent.

The fix addresses the review finding in substance locally. The GitHub thread and
published implementation deliberately remain unchanged until human review and
separate publication approval. Existing POSIX filesystem and unauthenticated
supplied-evidence limitations remain; no new recovery or live authority is added.

Final verification used the same stripped-environment commands documented above;
the FIFO-only gate used `-k fifo_substitution`, and the pre-fix reproduction used
`-k 'fifo_substitution and manifest and not read'`:

| Check | Actual result |
| --- | --- |
| Pre-fix inspection/recovery/producer reproduction | **3 failed**, bounded FIFO timeouts, 16.43 seconds |
| FIFO subprocess regressions after correction | **8 passed**, 6.04 seconds |
| Complete journal/evidence/fault suites | **241 passed**, no skips, 41.94 seconds |
| Existing canary/Study-journal/execution-control suites | **571 passed, 4 skipped**, 31.35 seconds |
| Full locked offline suite | **3,250 passed, 4 skipped**, 187.88 seconds |
| Ruff lint across src/tests | Passed |
| Mypy | Passed, 58 source files |
| Formatting, five Slice 2 Python files | Passed |
| Repository-wide formatting | Only the same two unchanged baseline failures |
| Git whitespace and scope checks | Passed |
| Protected files and identities | All 198 approved-base files unchanged in bytes/modes |

The full suites retain all sixteen spending-boundary regressions, historical
500/500/200 retry behavior and all thirteen saved-replay tampering cases. Existing
canonical JSON, checksum, predecessor/sequence, corrupted-record, symlink,
crash/interruption and save-only export tests pass without changes. Independent
AST comparison confirms all prior fault-test functions remain unchanged. Regular
records remain readable before every FIFO substitution in the new tests.

The listening-server controller module remains explicitly excluded, with the
same four optional SDK/application skips. No SDK/application runtime, server,
provider, judge or Study execution was invoked. No credentials or private operator
evidence were accessed. Approved C1/v2.1/v3 fingerprints, source/application pins,
fixture-hash bindings, locks and the 50-case Study dataset identity are unchanged.
Actual application fixture bytes were not accessed.

Only `journal_v3.py`, its existing fault-test module and this plan differ from
published HEAD, within the same six-file Slice 2 PR scope. HEAD and index stay
unchanged; no commit, push, merge, review-thread resolution or other GitHub write
was performed. The remaining three Slice 2 files are unchanged.

**Recommendation: the automated finding is resolved in substance in the local
diff, ready for independent human QA.** The published head and unresolved GitHub
thread still describe the original implementation until separate publication
approval. This change addresses special-file open blocking; it does not broaden
filesystem durability guarantees, authenticate evidence or add live authority.

## Reviewed FIFO correction: authorised third commit

Human QA accepted the local correction and authorised exactly one additional
commit, `Reject blocking special files during canary evidence inspection`, with
parent `faa8b514f82ee6262a71c9a08f088d5129ee97e4`. Preserve both earlier commits
and the approved base `a68b13ea2a09345a0ad3de1ce486679ddb00c375`.
Only `journal_v3.py`, `test_canary_journal_v3_faults.py` and this plan may change;
the full PR must retain exactly the six approved additions.

Pre-publication reruns passed: **241 journal/evidence/fault tests** in 41.51
seconds and **3,250 full offline tests, four optional skips** in 186.13 seconds.
These include all eight bounded FIFO cases, sixteen spending cases, historical
500/500/200 retries and thirteen saved-replay tampering regressions. The
listening-server controller module remains explicitly excluded; optional
SDK/application checks remain skipped, without enabling those runtimes.

Ruff lint, mypy (58 source files), formatting of all five Slice 2 Python files
and whitespace checks passed. Repository-wide formatting still flags only the
two untouched baseline files documented above. All 198 baseline files remain
byte/mode identical, with approved fingerprints, C1 behavior, application/source
pins, fixture-hash bindings, locks and Study data unchanged. Actual application
fixtures, credentials and private operator evidence were not accessed.

AST comparison proves the addition of `O_NONBLOCK` is the only executable source
change; `O_NOFOLLOW`, descriptor validation before read, canonical JSON, checksum
and record-chain logic are unchanged. Existing fault-test bodies are unchanged.
The bounded subprocess checks prove rejection and permanent producer closure.

Before publication GitHub showed only the existing unresolved FIFO finding.
Keep thread `PRRT_kwDOTj88Ls66WivM` open for independent verification; do not post
a resolution or trigger another review. After the exact three-file commit and
push to the existing feature branch, update PR #27's description with the
reproduction, correction, eight passing cases and final test totals. Verify the
remote correction, six-file inventory, published bytes, mergeability, CI and
additional review findings, then stop for final human QA. No merge, auto-merge,
Slice 3, server, SDK execution, provider request, judging or Study execution is
authorised.
