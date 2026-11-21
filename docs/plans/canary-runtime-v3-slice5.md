# C3b Slice 5: bounded offline controller and pinned application integration

Exact approved baseline: `6428c39076c3fa3cf55d65b9ccedfc4f01cf0cab`.
Branch: `feat/canary-runtime-v3-slice5`.
Worktree: `/private/tmp/ai-test-harness-canary-runtime-v3-slice5`.
Pinned application: `3320e556540d3f95bee1e8509f13e558ce266b6c`.

## Authorised scope

Current authorisation is publication of the finalization safety correction only:
the journal, its two test modules and this plan. The user approved one commit,
`Serialize v3 journal finalization and stop acceptance`, and a focused GitHub PR,
`Prevent stop/finalization races in v3 canary journal`, against the exact baseline
above. No merge, auto-merge, controller/application or SDK construction is
authorised. The preceding implementation scope is preserved here as historical
context, superseded for the present step.

Historical initial scope (superseded; not authority to resume):

Create controller_v3.py, test_canary_controller_v3.py,
test_canary_controller_v3_application.py and this plan. Only a necessary
finalization correction may modify journal_v3.py, test_canary_journal_v3.py and
test_canary_journal_v3_faults.py. No eighth file, driver/instrumentation change,
schema change, commit, publication, dependency installation, listener, credentials,
live provider, judge, Study execution or Slice 6 is authorised.

The user explicitly requires stopping with a bounded design proposal if the
stop/finalization invariant cannot be solved with the existing record protocol.
Existing worktrees, application source and private evidence must stay untouched.

## Historical Slice 5 milestones (remaining implementation is not authorised)

- [x] Fetch the exact approved merge and create one isolated feature worktree.
- [x] Write and run deterministic finalization regressions against unchanged code.
- [x] Establish an agreed cutoff that preserves immediate stop and historical replay.
- [x] Stop with the protocol/acceptance blocker before controller implementation.
- [ ] Implement offline controller composition and verified resource ownership.
- [ ] Execute normal and mandatory pinned-application suites and regressions.
- [ ] Verify protected bytes/modes, report exact results and stop for human QA.

## Finalization safety resolution: newly approved investigation

### Publication approval and fresh verification

The user provisionally accepted the correction and explicitly authorised one
commit and a focused PR for independent QA. Before publication, both the isolated
worktree HEAD and GitHub `main` were verified at the exact approved baseline
`6428c39076c3fa3cf55d65b9ccedfc4f01cf0cab`. Only the four approved files differ.
No merge or continuation of Slice 5 is authorised.

Fresh pre-publication journal/fault verification: **267 passed**, no skips,
139.64 seconds. Relevant existing Slice 2–4 regressions: **682 passed, 1 skipped**,
222.19 seconds; the skip still requires optional CPython 3.13. Ruff across
src/tests, mypy across 60 source files, formatting of the three Python files and
tracked whitespace checks all pass. All 22 applicable installed registry package
versions still match the unchanged lock. The fresh full locked offline suite
passed: **3,583 passed, 5 skipped**, 506.37 seconds, with no failures or xfails.
The historical listening-server controller module was explicitly excluded;
the five optional skips are unchanged and listed below. All seven other existing
worktree statuses match their pre-publication snapshots. Plan whitespace and
tracked whitespace checks pass. These results precede the single approved commit.

Fresh preservation checks confirm all other 208 baseline harness files and all
76 pinned application files match their approved blobs and executable modes.
The ten publication/replay/report/policy helpers and all 82 original journal/fault
test functions remain unchanged. Other existing worktree statuses were captured
for a final comparison. No new source-authorisation or live authority is claimed.

The user subsequently approved separation of immediate admission closure from
serialized stop acceptance. This supersedes the initial pre-return cancellation
expectation below, without reclassifying the original eight failures as false
positives. All initial results and the original NO-GO remain historical evidence.
Current scope is journal_v3.py, its two test modules and this plan only. No
controller/application/SDK implementation or execution is authorised in this step.

The explicit admission cutoff is the successful immediate-latch check inside
seal(), under the existing journal RLock. Seal then closes dispatch itself and
retains that mutex continuously through completion, acknowledgement and producer
closure. A pre-check stop request blocks admission even if its recorder has not
acquired the mutex. A durably accepted prior stop also prevents sealing. A request
after admission remains immediately latched but waits for serialized acceptance.
If sealing succeeds, that request returns late without changing evidence. If
sealing fails, it cannot return late or reopen the producer. A visible valid ack
still proves prior core-seal fsync under unchanged replay, independently of a
later producer error. The producer must report that error, not successful return.

Reentrant same-thread stop during seal cannot wait on an RLock and is rejected
with fixed `stop_acceptance_pending`, after latching, without appending a record.
It is not a durably accepted stop. Normal operator stop from another thread waits
for the admitted finalization. No asynchronous recorder or new protocol is added.

Resolution milestones:

- [x] Review all eight original failures and document the new expectation mapping.
- [x] Implement admission/check and continuous mutex ownership, with late-stop results.
- [x] Verify deterministic admission, late/failure, sync and crash interleavings.
- [x] Run complete focused and relevant Slice 2–4/full offline regressions.
- [x] Run static checks, verify protected bytes and stop for independent human QA.

Current disposition: **GO for publishing the finalization safety correction for
independent human QA only**. No journal schema extension was necessary. The later
publication approval permits the single commit and PR described above; it does
not permit merge, controller work, live execution or Slice 6.

The first corrected rerun of the existing 21 Slice 5 investigation cases passed:
**21 passed, 98 deselected**, no skips, 59.24 seconds. Additional direct journal,
concurrent-stop and actual directory-sync regressions then passed with those
existing cases: **40 passed, 224 deselected**, no skips, 77.59 seconds. A final
closure-failure observation guard and two more regressions were subsequently added.

The complete current journal/fault suites passed: **266 passed**, no skips,
139.72 seconds. Static checks also pass: Ruff across src/tests, mypy across 60
source files, formatting of all three changed Python files and tracked whitespace.
All 22 applicable installed registry package versions match the harness lock;
the interpreter is CPython 3.12.13. No dependencies were installed or updated.

Verification commands use the same stripped existing harness interpreter and
`-B`, with pytest cache disabled:

```text
python -B -m pytest tests/test_canary_journal_v3.py tests/test_canary_journal_v3_faults.py -q --tb=short -rs -p no:cacheprovider
python -B -m pytest tests/test_canary_driver_v3.py tests/test_canary_instrumentation_v3.py tests/test_canary_evidence_v3.py tests/test_canary_execution_policy.py tests/test_canary_selection_v3.py tests/test_canary_acceptance.py tests/test_canary_runtime_v3.py -q --tb=short -rs -p no:cacheprovider
python -B -m pytest -q --tb=short -rs -p no:cacheprovider --ignore=tests/test_canary_controller.py
```

The relevant existing driver/instrumentation/evidence/policy/selection/acceptance/
runtime regressions passed: **682 passed, 1 skipped**, 218.63 seconds. The only
skip is the optional complete source-composition test requiring CPython 3.13.
The first full locked offline run was deliberately stopped during final review
to retain the reentrant-finalization guard through producer closure. SIGINT was
caught by a test's existing BaseException handling and produced a test failure;
the process was then stopped with a command scoped SIGTERM (exit 143). This
interrupted run is not a valid suite result or a claimed regression pass. A direct
closure-reentry regression was added; the final suite must run on that correction.

After retaining the guard through closure, the finalization-focused rerun passed:
**43 passed, 224 deselected**, no skips, 79.65 seconds. Ruff, formatting, mypy and
whitespace checks pass again on this final code. A fresh full locked offline run
completed successfully: **3,583 passed, 5 skipped**, 502.93 seconds. It includes all
267 current journal/fault cases, including the closure regression, and reruns the
existing Slice 1–4 regressions on the final code. No failures or xfails occurred.

Exact final exclusions/skips:

- `tests/test_canary_controller.py`: explicitly excluded, historical listening-server
  controller suite; this is not counted as a skip.
- `tests/test_canary_instrumentation_v3_sdk.py`: optional pinned SDK runtime absent.
- `tests/test_canary_sdk.py`: optional OpenAI SDK not installed.
- `tests/test_canary_selection_state.py`: optional pinned application runtime absent.
- `tests/test_canary_state.py`: optional pinned application runtime absent.
- `tests/test_canary_runtime_v3.py:452`: complete source composition requires optional
  CPython 3.13. No source authorisation is claimed in its absence or otherwise.

The SDK/application checks were not invoked separately because the current
authorisation prohibits constructing them. Nothing was installed to satisfy skips.
All static checks passed on final code, and final tracked/document whitespace
checks passed. The original failed investigation and interrupted non-final full
run remain separately recorded below/above; neither is counted as a corrected pass.

### Stop/finalization outcomes and compatibility

- `stop()` and `request_provider_stop()` latch before waiting and return accepted
  only after serialized durable acceptance (or an already recorded provider stop).
- After a successful admitted seal and producer closure, valid stops return late,
  preserving the sealed prefix exactly. Provider stops still validate binding,
  definition, code and PID. They do not regain a writer or dispatch capability.
- A private in-memory finalized observation distinguishes successful local closure
  from a failure even after the ack was published. It creates no saved record and
  does not change replay interpretation. A close failure is sanitized and cannot
  produce a late-stop result.
- A stop requested before mutex acquisition blocks seal admission through the
  latch, even if neither recorder has acquired the mutex. An accepted prior stop
  remains recorded and prevents a completion record.
- Four concurrent post-admission stops all remain pending until the continuously
  held mutex is released, then return late after successful finalization.
- Actual completion-directory-sync failures/interruption leave incomplete saved
  evidence. Ack failure before link also leaves incomplete evidence. Ack directory
  sync failure or failure after ack sync raises a producer error, and pending stop
  acceptance fails; valid visible ack still certifies saved completion under the
  unchanged protocol. Producer failure is not a successful invocation.
- Process death before ack link leaves incomplete evidence; death immediately
  after link retains existing completion interpretation, even without the ack's
  final directory sync or function return. Save-only export never changes records.
- Reentrant same-thread stop is latched and rejected as acceptance pending, without
  interleaving record publication. Invalid/repeated sealing stays permanently
  closed. No terminal marker is synthesized after a failed producer.

No schema, record fields, checksums, replay rules, acceptance, execution policy or
cost estimation changed. The production `_publish`, `_apply`,
`_apply_instrumentation`, `_scan`, `_report`, `_guards`, `_effective`, `_reconciled`,
`inspect_run` and `recover_save_only` functions match the exact approved baseline
in source text. All 56 original journal-test functions and 26 original fault-test
functions retain their baseline ASTs. Normal Slice 4 sealing remains in the
regression/full-suite verification, with no driver modification.

### Remaining limits

Admission and stop acceptance are cooperative in-process serialization, not a
real-time scheduler or hostile-code isolation. A stop can close admission while
waiting for a blocked fsync; it cannot forcibly interrupt that syscall. An admitted
seal may finish before a later stop is accepted. Missing/ambiguous records cannot
be repaired or resumed. Local POSIX hard-link/fsync assumptions and the historical
ack visibility interpretation remain; no physical-power-loss guarantee is added.
Source authentication, live authority, billing and application/worker shutdown
remain outside this focused correction. No controller or pinned application was
constructed. Independent human QA is required before further implementation.

### Current correction inventory and preservation

Only the three approved existing Python files and this plan differ. Against the
exact approved merge, journal_v3.py has 93 additions / 38 deletions, the journal
tests have 270 additions / no deletions, and the fault tests have 396 additions /
no deletions. This plan is the fourth file, containing the original investigation,
the separately approved resolution and the subsequent publication authorization.
No controller file or other scoped file was created. The final commit SHA, PR
status and independent-QA handoff are reported with the published PR.

All 211 harness baseline tracked files were checked by actual Git blob hashes and
executable modes: only those three Python paths differ, leaving all other 208
files exact. All 76 tracked application files match the pinned application commit,
including the original fixture hashes. The ten protected replay/publication/policy
helper functions remain identical in source text. Policies, cost estimation,
source pins, locks, Study data and tracked historical artifacts are preserved.
Existing worktrees and private operator evidence were not modified or accessed
as implementation inputs. The dirty development checkout retains its original
status. No new source-authorisation or clean-commit verification is claimed.

### Eight-case mapping under the approved admission cutoff

All original observed outcomes were driver completed / journal certified, and
all eight failed the former assertion that any pre-return latch must cancel
completion. Those failures remain the original reproduction, not false positives.
The renamed regression preserves the same eight barriers and records this exact
expectation change rather than adding skips or expected-failure markers.

| Original stop-request boundary | Relation to new admission | Corrected requirement |
| --- | --- | --- |
| Before shutdown evidence | Before | No completion certificate |
| Before completion recording (before entering seal) | Before | No completion certificate |
| Completion syscall before link | After | Admitted seal may complete; stop serialized afterward |
| Completion syscall after link | After | Same |
| Between core completion and acknowledgement | After | Same |
| Acknowledgement syscall before link | After | Same |
| Acknowledgement after link before sync | After | Same; ack visibility retains old replay meaning |
| Acknowledgement after sync before publisher return | After | Same |

The six new completed expectations follow the newly approved admission/acceptance
contract. They do not assert that an accepted prior stop can be ignored. Dedicated
tests now distinguish a durably accepted stop, an unrecorded request before mutex
acquisition, post-admission pending stops, successful late results and failed
finalization where stop acceptance fails rather than being classified late.

## Original first safety gate (superseded by the approved cutoff above)

Investigate stop before shutdown/completion, while completion is being published,
between completion and acknowledgement, during acknowledgement publication, and
after confirmed finalization. Use bounded Events and publication/syscall barriers;
never timing-dependent sleeps. Preserve the prefix and use save-only recovery.
Report unchanged-baseline observations separately from any correction.

Candidate completion cutoff for review is confirmed finalization, with a visible
acknowledgement carrying the existing protocol's meaning that the preceding core
completion record was synced. A stop latched before that cutoff must not be
silently relabelled late merely because its durable recording waits for a lock.
No cutoff is approved or implemented by this plan alone.

## Development source gate

Keep verify_source() unchanged. Uncommitted Slice 5 code cannot claim a clean
reviewed executable identity. Development tests must label synthetic source
claims; exact clean-commit verification remains a publication-stage gate.

## Original investigation results (preserved; superseded by resolution above)

Disposition: **NO-GO for continued Slice 5 implementation or PR preparation**.
The mandatory first safety gate is not established. No production source has
been modified. No controller, SDK or pinned application has been constructed.
Tests use the existing Slice 4 synthetic application only to investigate the
real journal/driver finalization boundary. They are not application-integration
evidence and do not satisfy the mandatory pinned-application suite.

### Original reproduction, before any production correction

The first regression-only command returned **8 failed, 98 deselected**, no skips,
in 23.03 seconds. Every failure reached the final assertion that a latched stop
must prevent completion certification; there were no barrier timeouts or leaked
test threads. The original journal, driver and instrumentation were unchanged.

The expanded investigation returned **8 failed, 13 passed, 98 deselected**, no
skips, in 57.86 seconds. The eight failures remain visible and unmarked: no xfail,
skip or changed expected outcome hides the unresolved invariant. Thirteen passing
controls characterize existing behaviour; they do not establish corrected safety.

Both commands used the existing locked harness environment, stripped environment,
`PYTHONPATH=src`, `PYTHONDONTWRITEBYTECODE=1`, `python -B` and disabled pytest cache:

```text
env -i PATH=/usr/bin:/bin PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /private/tmp/ai-test-harness-canary-runtime-v3-slice2/.venv/bin/python -B -m pytest tests/test_canary_journal_v3_faults.py -k slice5_latched_stop -q --tb=short -p no:cacheprovider
env -i PATH=/usr/bin:/bin PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /private/tmp/ai-test-harness-canary-runtime-v3-slice2/.venv/bin/python -B -m pytest tests/test_canary_journal_v3_faults.py -k slice5 -q --tb=short -p no:cacheprovider
```

The stop thread closes the real provider/journal latch, then a bounded barrier at
its mutex entry models delayed journal access. The finalizer continues. The
regression checks both latches, joins both threads, inspects saved evidence and
verifies that save-only export leaves source bytes and modes unchanged. There are
no timing-dependent sleeps, altered production stop gates or fabricated records.

| Stop boundary | Original observed result |
| --- | --- |
| Before shutdown evidence | Driver completed; journal certified completed |
| Before completion recording | Driver completed; journal certified completed |
| Completion syscall, before hard link | Driver completed; journal certified completed |
| Completion syscall, after link before directory sync | Driver completed; journal certified completed |
| Core completion synced, before acknowledgement | Driver completed; journal certified completed |
| Acknowledgement syscall, before hard link | Driver completed; journal certified completed |
| Acknowledgement linked, before its directory sync | Driver completed; journal certified completed |
| Acknowledgement synced, before publisher returns | Driver completed; journal certified completed |

The first six cases latch stop before acknowledgement visibility. The last two
depend additionally on whether the future agreed cutoff is acknowledgement
visibility or confirmed return; this review must not silently choose either.
All eight currently assert the conservative pre-return requirement.

Passing controls:

- One and repeated stops fully recorded before shutdown prevent sealing: 2 cases.
- Repeated stop after successful driver/seal return preserves the completed prefix:
  1 case. This characterizes immutability, not an implemented late-stop interface.
- OSError and KeyboardInterrupt before/after completion/ack publication: 8 cases.
  Visible acknowledgement yields a certified journal despite driver status stopped;
  the other six outcomes remain incomplete under existing replay.
- Abrupt child exit before/after the acknowledgement hard link: 2 cases. Before
  link is incomplete; after link is completed under existing replay, even though
  the acknowledgement's directory fsync and producer return never occur.

### Exact blocker and cutoff decision

The existing protocol makes `completion_ack` the final record. Its visibility
proves that the *preceding core completion* was synced. Replay marks the journal
sealed on that record, even if acknowledgement publication later fails. After
completion, only acknowledgement is allowed; after acknowledgement, no new record
is allowed. This is deliberate historical interpretation, not a malformed record.

The immediate stop event and filesystem hard-link publication are separate
operations. Checking the latch at seal entry, before acknowledgement recording,
or immediately before os.link narrows the race but cannot atomically order a stop
with that syscall. The `ack_before_link` barrier investigates this last interval.
Checking after publication cannot retract the visible acknowledgement, append a
terminal record under the existing protocol, or change what save-only replay sees.
A crash can erase the only in-memory indication of the intervening stop.

Holding the journal mutex across seal is insufficient: public stop intentionally
latches before waiting for that mutex. Silently declaring such a stop unaccepted
until after sealing, or choosing an early cutoff before confirmed finalization,
would change the requested safety semantics. Neither is implemented or approved.

Thus a complete invariant requires agreement on how stop acceptance and final
commit are serialized, including what is durable and what recovery may certify.
This is a protocol/acceptance decision, not merely an additional boolean check.
No safe full correction has been established within the currently approved
protocol. No correction result or completed Slice 5 claim is reported.

### Bounded proposal for independent review

Approve a focused design step before resuming implementation:

1. Define immediate admission closure separately from the durable/serialized
   acceptance acknowledgement of a stop. The admission latch must still close
   before any wait, independently of application and journal work.
2. Define one shared serialization boundary for accepted stop and final commit,
   with an exact cutoff, syscall-failure outcomes and process-loss interpretation.
   A stop accepted first must prevent commit. A commit established first can make
   a subsequent accepted stop late. Unestablished ordering must remain incomplete.
3. Decide explicitly whether a stop latched during an admitted final publication
   may be acknowledged as late after confirmed commit. If this is disallowed,
   additional durable arbitration and a separately reviewed opt-in protocol are
   required; adding one more marker alone does not remove the final-write race.
4. If an opt-in profile/record interpretation is needed, authorise its exact
   producer and replay rules separately, preserving old journals unchanged.
   Do not infer that the present schema approval permits it.
5. Extend these regressions with the agreed cutoff and every uncertainty/crash
   boundary before writing controller composition. Do not weaken pre-cutoff stop
   assertions merely to obtain a passing suite.

This proposal adds no execution authority, restart, repair, alternate transport or
new assessment policy. The same seven-file inventory may suffice, but the allowed
protocol semantics require explicit independent approval. No further implementation
is undertaken under the present conditional GO.

### Deferred deliverables

Controller interfaces, genuine application/session/tool/trace evidence, SDK attempt
accounting, verified resource shutdown and mandatory pinned application execution
are unimplemented/unexecuted. Full offline, pinned SDK and application suites are
not run after this safety blocker. No test result from an earlier slice is reused
as current verification. Clean-commit source matching remains a later gate.

### Final inventory, checks and preservation

Exactly two paths changed within the seven-file scope:

- `tests/test_canary_journal_v3_faults.py`: 279 additions, no deletions; the
  finalization regression and baseline characterization tests above.
- This plan: new file; milestones, reproduction, protocol blocker and proposal.

No controller placeholders or other new source files were created. In particular,
journal_v3.py, driver_v3.py and instrumentation_v3.py remain byte-identical to the
exact approved merge. No production correction was attempted.

Static checks using the existing locked harness interpreter:

- Ruff across `src tests`: passed.
- Formatting of the changed Python test file: passed.
- Mypy across `src`, cache outside the worktree: passed, 60 source files.
- Tracked diff whitespace: passed.

All 211 tracked baseline files were independently compared by Git blob hash and
executable mode. Only the intended fault-test module differs; all other 210 match
exactly. This preserves C1 source/history, approved v3 policies/fingerprints, source
pins, estimator, locks, datasets and tracked historical artifacts without importing
or executing them. No private operator evidence was inspected. The Study JSON file
byte SHA-256 is `ea6153f7a0f22499af4be75bb7c145af2c7307a92593d8aaf5aa6eccfb3803f6`;
this byte hash is not a recomputation of its semantic dataset fingerprint.

The existing dirty development checkout's final status matches its initial
inventory. The pinned application remains clean at the approved revision. No
commit, push, PR, merge, cleanup/prune, dependency installation, listening server,
SDK construction, paid request, judge, Study execution or Slice 6 occurred.
