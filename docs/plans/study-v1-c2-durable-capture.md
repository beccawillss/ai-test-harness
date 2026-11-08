# Study v1 C2 ExecPlan — fail-fast capture and durable journaling

Approved baseline: `46d24b91360229fe6e0d4a1aab4da29a27a45c6d`.
Approved dataset: `4a0e40d6dce4b78cc194352bf23d69dabcc8fe3c0f440d50f2cce2bd6a956028`.
Worktree: `/private/tmp/ai-test-harness-study-v1-c2`, branch
`feat/study-v1-c2-durable-capture`. The initial offline phases prohibited
commit/push. Final PR preparation is now authorised after verification: commit,
push and open a PR targeting `main`. Merge, live calls, servers, canaries,
real Study execution and actual freezes remain unauthorised.

## Interfaces and compatibility (recorded before implementation)

Approach A adds one optional typed execution control to `run` and
`execute_suite`: validated preparation/provenance, attempt reservation,
normalized response before scoring, independent scorer outcome, completed
attempt and assembled run. Callback failures propagate; durable recorder failures
use a distinct control exception that adapters and runner must re-raise.
The C2 controller stops dispatch after ERROR, continues after quality FAIL,
and retains successful independent scores. Default calls retain existing
execution, close, serialization and error behavior. Cleanup during a primary
failure must preserve that failure and previously published evidence.

A Study-owned journal uses an explicitly supplied authoritative registry,
deterministic identity (execution contract + suite), exclusive capture/attempt
claims, immutable checksum envelopes, file fsync, atomic no-overwrite publication
and directory fsync. It records validated provenance, public HTTP checkpoints,
normalized responses, scorer outcomes, full attempts and final assembled runs.
Only a complete roster with PASS/FAIL attempts and valid evidence may receive a
completion receipt. Reservations are never reused: missing, stale, conflicting
or corrupt evidence blocks further dispatch. Output directories are exports,
not dispatch authorities. No retry/resume/regeneration exists.

Sales Agent recording is optional at its existing injected HTTP adapter boundary.
It records allowlisted validated public chat before trace I/O and normalized
trace/turn evidence before another chat. Request construction, timeout and
session behavior remain unchanged. No credentials/headers/raw provider objects,
hidden instructions or reasoning are journaled. Earlier checkpoints survive a
later malformed/failed turn. Business errors remain valid quality evidence.

Historical `StudyExecutionContract` stays v1. A separate v2 model binds
`salesagent-study-capture-fail-fast-v1`, `salesagent-study-journal-v1` and
`salesagent-study-completion-v1`. Version-aware loading preserves v1 dumps and
fingerprints. V2 capture requires the journal and recorder. V2 verification,
preparation, export and protected judging require the matching verified receipt.
No evaluator, rubric, anchors, threshold or human methodology changes.

## Milestones and validation

- [x] Inspect baseline, preserve existing checkouts, create isolated worktree.
- [x] Record interfaces and compatibility before implementation.
- [x] Generic opt-in lifecycle and compatibility regression tests.
- [x] Durable Study journal, receipt verification, offline inspection and save-only recovery.
- [x] Safe Sales Agent recorder and partial-conversation tests.
- [x] V2 contract, capture and downstream workflow integration.
- [x] Synthetic fault injection, focused/full offline tests, Ruff/format/mypy (baseline formatting exceptions recorded).
- [x] Revalidate unchanged 50 cases, six suites, approved fingerprint; report review items.

Tests use synthetic definitions, scripted targets/judges and MockTransport only.
Faults cover reservation/publication/fsync boundaries, response-before-score,
scorer and cleanup failures, duplicate/conflicting identities across output
locations, stale backups, incomplete/corrupt receipts and save-only recovery
with zero external calls. Run existing v1 fixture/default compatibility tests.
Use existing local development dependencies with this worktree's `src`.

## Operational proposal and limitations

Registry proposal only: `<approved-encrypted-local-artifact-root>/study-v1/c2-registry`.
No production location is configured or created. Production destination,
filesystem durability guarantees, operational single-writer discipline and
integration require separate human approval.

Save-only recovery reads evidence under the exclusive registry writer lock, verifies every
checksum/binding and completion prerequisite, and exports the already assembled
run (or assembles only fully committed outcomes after an assembly interruption) to a new destination/SQLite store without constructing any target or judge.
An incomplete journal is inspectable evidence and never permission to dispatch.
Exactly-once remote execution is impossible without target-side idempotency:
a crash after reservation may lose a request or response and permanently blocks
that identity. Local guarantees assume a reliable local filesystem supporting
fsync and atomic exclusive links, a single authoritative non-rolled-back registry,
and no external tampering. Backups are evidence, never a replacement authority.

## Progress and evidence

2026-11-08: Exact approved commit was absent locally; fetched only that commit.
Created the dedicated worktree/branch. Existing worktrees and uncommitted files
are unchanged. No implementation or actual Study artifacts created before this plan.

2026-11-08 implementation: completed the six typed lifecycle boundaries, Study
journal with exclusive registry writer lock and capture/attempt claims, validated
public Sales Agent chat/turn recording, v2 contract and recipe integration, and
receipt gates inherited by preparation/export/judging/analysis. All new tests use
synthetic definitions, MockTransport and scripted scorers/judges. No real Study
inputs were dispatched. Save-only recovery may publish only missing assembly or
completion records after verifying all previously committed complete outcomes;
it never scores, retries or regenerates responses.

Compatibility verification: direct in-memory comparison against the approved
baseline matched default runner JSON bytes for both fingerprint schemes with
multiple attempts, target/scorer errors and independent successful scores.
Historical v1 fixture dump bytes and fingerprint match baseline exactly:
`e9f47d68a81aa476aeded815b83ffaed1a2ca6e2ec6b54074cb52ea478034219`.
Read-only verification confirmed 50 cases, six suites and the approved dataset
fingerprint, with dataset/suite/matrix bytes unchanged.

A compatibility regression caught during implementation was fixed: the recipe
must keep loading execution contracts through the existing immutable
`document.json`/`receipt.json` bundle, with version-aware model selection.
No C1 tooling compatibility change was necessary.

Repository-wide Ruff lint and mypy pass. Repository-wide formatting reports three
pre-existing files, each verified byte-identical to the approved baseline:
`docs/test-taxonomy-and-suites.md`, `src/harness/targets/base.py`,
`tests/test_dataset.py`. These unrelated files remain untouched. Final changed-file
formatting and focused/full offline suite results are recorded below.

Final focused verification (2026-11-08):

- `PYTHONPATH=src python -m pytest -q tests/test_execution_control.py tests/test_study_journal.py`: **85 passed**, 17.57s.
- Focused runner/suite/target/Study/reporting regression set (the two new files plus
  `test_runner.py`, `test_salesagent_target.py`, `test_salesagent_study.py`,
  `test_study_reporting.py`, `test_suites.py`): **520 passed**, 87.43s.
- `mypy src`: **49 source files passed**.
- `ruff check .`: **passed**.
- `ruff format --check` over all 12 changed/added Python files: **passed**.
- `git diff --check`: **passed**.
- Synthetic warmth v3 adapter/evidence and v5 projection under execution-v2:
  **8 synthetic attempts with verified completion**, zero external calls.

Fault coverage passed: quality FAIL continuation; target/scorer and malformed
normalized-output ERROR stopping; independent scorer preservation; partial
multi-turn evidence; publication and fsync/link failures; nine abrupt
post-publication interruption boundaries; non-overwrite/cleanup behavior;
concurrent writer exclusion; corrupted prior reservation blocking; duplicates
across output directories; stale/copied registry rejection; valid-checksum
conflicting bindings; stripped receipts/truncated rosters; save failures,
receipt-last recovery and assembly solely from committed outcomes. Recovery
constructs no clients. Full synthetic v2 capture of 50 synthetic rows produces
50 prepared requests, the unchanged 12-item human roster, a synthetic human
freeze, one scripted protected judge outcome and reloadable v2 analysis.
Comparisons now explicitly flag v1/v2 execution-policy changes; v1-only
comparison shape is unchanged. Journal I/O contributes to opt-in timings.

Exact changed-file inventory (14 files; no others):

1. `docs/plans/study-v1-c2-durable-capture.md` — this living ExecPlan and results.
2. `docs/study-v1-c2-durable-capture.md` — architecture, operational proposal, recovery and limits.
3. `examples/salesagent_study.py` — version-aware bundles, opt-in v2 freeze, inspection/recovery commands and completion exit status.
4. `src/harness/core/execution_control.py` — six typed lifecycle callbacks and control exception.
5. `src/harness/core/runner.py` — optional callbacks, independent outcomes, stop control and cleanup precedence.
6. `src/harness/core/suites.py` — optional control and validated pre-dispatch suite provenance.
7. `src/harness/packs/salesagent_study.py` — separate v2 contract, journal/recorder orchestration and receipt verification.
8. `src/harness/reporting/study.py` — version-aware analysis and capture-policy comparison flags.
9. `src/harness/study/__init__.py` — Study-owned module boundary.
10. `src/harness/study/journal.py` — exclusive registry, durable records, receipts, inspection and save-only recovery.
11. `src/harness/targets/salesagent.py` — opt-in validated public chat/turn checkpoints.
12. `src/harness/targets/salesagent_recording.py` — safe typed evidence publisher.
13. `tests/test_execution_control.py` — default/opt-in lifecycle and malformed-output regressions.
14. `tests/test_study_journal.py` — synthetic durable capture, faults, recovery and downstream v2 compatibility.

Implementation adaptations within Approach A: an explicit POSIX registry writer
lock also excludes recovery during capture; complete committed outcomes can be
assembled during save-only recovery without execution/scoring. No broader
plugin/continuation mechanism was introduced. The only outstanding formatting
findings are the three pre-existing baseline files listed above. No unrelated
formatting, Sales Agent application or C1 tooling changes were made.

Human review before integration: approve the code and exact encrypted production
registry destination; confirm local filesystem/power-loss expectations and the
single-authority/backup/restore procedure. Actual v2 Study freeze, live budgets,
commit/push and integration/merge remain separately authorized actions. This task
stops with uncommitted changes in the isolated implementation worktree. The
original checkout's HEAD, branch and dirty-file inventory match the initial
inspection, and the implementation worktree remains based exactly on the
approved commit.

Final full offline suite (2026-11-08), on the final implementation:
`PYTHONPATH=src python -m pytest -q -rs` — **2,586 passed, 1 skipped**, 138.94s.
The single existing collection skip is `tests/test_canary_sdk.py:9` because the
optional `openai` SDK is not installed. No dependencies were installed and no
live canary/SDK/application execution was invoked. The default network-blocking
fixture remained enabled. All 85 new C2 tests passed. All requested offline
verification is complete; no implementation work remains before human review.

The exact local interpreter/tool environment used for the commands above was
`/Users/rebeccawilliams/Developer/ai-test-harness/.venv/bin/`, with
`PYTHONPATH=src` and cwd `/private/tmp/ai-test-harness-study-v1-c2`.
No commit, push, merge, real Study freeze, real Study target execution, server
startup, live canary or external model API call occurred.

## Independent audit corrections — authorised follow-up

The independent audit returned **FIX BEFORE PR**. The user authorised correction
of all five findings in this existing isolated worktree. No source/checkouts,
production registry, real Study artifacts or previously excluded integrations
may change. The original 14-file C2 inventory remains the implementation boundary.

- [x] IMPORTANT: restore baseline per-case metadata capture before attempts;
  bind optional callbacks to that identity even under target/scorer mutation.
  Keep default legacy mutation/isolation semantics and fingerprints unchanged.
- [x] IMPORTANT: create recovery export directories as 0700 and files as 0600,
  without changing process umask or unrelated directories. Exclusively claim
  output paths, reject symlink/unsafe substitutions, pre-create the SQLite file
  privately, and check the new directory/file identities around saves. The
  export parent remains owner-controlled, as does the authoritative registry;
  this is not a general hostile-filesystem framework.
- [x] MINOR: verify created capture/attempt directory identities before the first
  preparation/reservation and every later reservation, rejecting redirects before
  target I/O rather than waiting for completion validation.
- [x] MINOR: perform one durability scan of existing journal evidence per recovery;
  publish missing run/receipt afterward using their own durable publication.
- [x] MINOR: reach each intended fsync/link fault on a fresh publication and assert
  the injected function was called; retain separate non-overwrite collision and
  post-link synchronization coverage.
- [x] Reproduce mutation compatibility against approved baseline, add permission,
  substitution, recovery-failure and bounded real process-death regressions.
- [x] Run focused/full offline tests, Ruff/changed-file formatting/mypy; preserve
  the three unrelated baseline formatting findings and approved Study artifacts.

Expected correction files: `core/runner.py`, `study/journal.py`, the Study recipe,
the two existing C2 test files, this plan and the C2 operations guide. No new
execution features, policy versions, plugin framework or production defaults.
All five before/after observations and final verification are recorded below.

### Correction evidence (2026-11-08)

| Audit finding / before | Correction / after |
| --- | --- |
| Default legacy target/scorer mutation changed the recorded case ID/tags because CaseResult arguments were read after attempts. | Capture ID, copied tags and definition in the baseline's keyword evaluation order before attempts; keep CaseResult construction/validation afterward. Eight regression combinations cover control absent/present, both fingerprint schemes and target/scorer mutation. Callback identities stay bound to the original case. |
| Recovery exports inherited umask: replaying the previous save sequence in a disposable subprocess with `022` reproduced directory `0755`, JSON `0644`, SQLite `0644`. | The recovery recipe exclusively creates `0700`/`0600` outputs; initial modes never grant broader access. Four subprocess tests (`000`, `022`, `077`, `777`) invoke the real recovery command, prohibit runtime umask changes and external factories/socket calls, then read back both identical source documents. Parent permissions remain unchanged. |
| An active `attempts` symlink substitution was rejected only during completion, after synthetic target I/O. | Check created capture/attempt directory device/inode identities before preparation and every reservation. Four tests cover target-factory/pre-reservation substitutions with symlinks and different directories; all reject with zero synthetic HTTP requests. |
| Missing-receipt recovery scanned and fsynced previously visible evidence twice. | One shared scan precedes missing run/receipt publication, each with its own file/parent fsync. Three boundaries (already complete, missing receipt, missing run and receipt) assert each pre-existing record is fsynced exactly once before new publication. Three recovery-failure cases preserve committed bytes, prohibit save until durable, and permit subsequent save-only recovery without more requests. |
| The parameterised directory-fsync fault reused an existing final name, so link collision prevented the injected sync fault. | Publish a fresh filename and assert the injection ran exactly once with the intended cause. File-fsync/link failures leave no final file; directory-fsync failure leaves the complete checksummed publication. A separate collision test proves FileExistsError and zero directory-sync calls; separate post-link ambiguity/non-overwrite coverage remains. |

Security negatives additionally reject existing files/directories, destination
symlinks, symlink parents and unsafe writable parents without changing their
contents or modes. Directory and either output-file substitution during SQLite
save are rejected. SQLite builds in a private scratch directory and only closed
database bytes are copied through an output directory descriptor. An injected
export-file fsync failure leaves a private partial export and intact authoritative
journal; save-only recovery to a new output succeeds with unchanged request count.
Generic `recover_save_only` keeps its existing callback contract; callers of a
custom callback own that callback's export permissions.

The bounded real process-death test exits a child with `os._exit(23)` inside a
synthetic scorer after the normalized response checkpoint, bypassing Python
cleanup. The parent verifies the reservation and response survived, no outcome
or completion exists, the kernel released the writer lock, and both duplicate
capture and incomplete save-only recovery are blocked. The only dispatch is a
synthetic in-process marker; sockets are prohibited. This tests process death,
not machine/power failure or production storage.

Direct comparison loads the approved runner source with `git show` into an
in-memory module, without another checkout. With frozen clocks/UUID, all twelve
default scenarios serialize byte-identically to baseline: both fingerprint
schemes × target mutation, scorer mutation, PASS, FAIL, target ERROR and scorer
ERROR with an independent successful score; two cases and two attempts each.
Historical v1 fixture serialized bytes/digest also match the baseline-loaded
contract model exactly:
`e9f47d68a81aa476aeded815b83ffaed1a2ca6e2ec6b54074cb52ea478034219`.

Correction-only file inventory (7; the original complete C2 inventory remains
exactly the 14 files listed above):

1. `src/harness/core/runner.py`
2. `src/harness/study/journal.py`
3. `examples/salesagent_study.py`
4. `tests/test_execution_control.py`
5. `tests/test_study_journal.py`
6. `docs/plans/study-v1-c2-durable-capture.md`
7. `docs/study-v1-c2-durable-capture.md`

No contract/policy identifiers changed. The 50 approved cases, six suites,
dataset descriptor, matrix and semantic/rule pack files are byte-identical to
the baseline (11 files checked). Read-only Study loading confirms the approved
dataset fingerprint and suite sizes/attempts: full 50×1, smoke 8×1, variance
10×3, critical 12×1, adversarial 8×1 and multi-turn 20×1. Rubric, anchors,
threshold, judge configuration and protected roster are unchanged. Actual
Study inputs were never dispatched. C1 tooling and the Sales Agent application
remain untouched.

Residual limits are unchanged for remote execution: local at-most-once under
one intact authoritative registry, no automatic retry and no remote exactly-once
guarantee. Directory checks assume owner-controlled storage; they do not defend
against concurrent same-owner/privileged tampering between syscalls. Fsync/link
semantics still depend on the filesystem and hardware. A crash may leave a
private partial export or private temporary SQLite scratch files; saving is not
a two-file atomic transaction. Retry only saving into an unused private export,
never dispatch. The operator must approve production storage (including scratch
handling) and the encrypted registry destination separately. No stale registry
restore becomes safe or authorized through these corrections.

### Final correction verification

Commands use the existing local `.venv/bin/` tools with cwd this isolated
worktree and `PYTHONPATH=src`; no dependencies were downloaded.

- `python -m pytest -q tests/test_execution_control.py tests/test_study_journal.py`:
  **118 passed**, 23.31s (33 additional tests beyond the original 85).
- `python -m pytest -q tests/test_execution_control.py tests/test_study_journal.py tests/test_runner.py tests/test_salesagent_target.py tests/test_salesagent_study.py tests/test_study_reporting.py tests/test_suites.py`:
  **553 passed**, 93.20s.
- `python -m pytest -q -rs`: **2,619 passed, 1 skipped**, 146.70s.
  The existing skip remains `tests/test_canary_sdk.py:9`: optional `openai`
  package is absent. It was not installed or invoked.
- `ruff check .`: **passed**.
- `ruff format --check` over the 12 C2 Python files: **passed**.
- `ruff format --check .`: exactly **3 unchanged baseline findings**:
  `docs/test-taxonomy-and-suites.md` (Python code example spacing),
  `src/harness/targets/base.py` (whitespace/spacing), and
  `tests/test_dataset.py` (adjacent string formatting). Each was compared
  byte-for-byte with the approved baseline and left untouched.
- `mypy src`: **49 source files passed**.
- `git diff --check`: **passed**.

The original checkout's HEAD and dirty-file inventory still match the initial
inspection. The implementation branch remains uncommitted at the approved
baseline, with the same complete 14-file inventory. No other worktree was
modified; no commit, push, merge, server, canary, real Study execution/freeze or
external model API call occurred. Tests retained the offline socket blocker;
subprocess tests independently blocked socket connections and used synthetic
evidence exclusively.

Recommendation: **READY FOR PR**, subject to human review before any commit,
PR preparation or integration. Production registry/storage approval and later
live execution/freezing remain separate decisions. Stop here for human review.

## Final pre-PR verification and authorised publication

2026-11-08: The user approved progression after the correction review and
explicitly authorised committing the complete C2 implementation, pushing its
branch and opening a PR targeting `main` if final verification passed. This
supersedes the earlier commit/push/PR hold; it does not authorise merging or any
live Study activity. No implementation or regression code changed in this phase.

Final checks against baseline `46d24b91360229fe6e0d4a1aab4da29a27a45c6d`:

- Exact **14-file inventory** matches both this plan and the complete baseline
  diff, including untracked additions. No out-of-scope changes were found.
- Remote `main` equals the approved baseline (GitHub comparison: identical,
  zero commits ahead/behind). The PR targets `main` as explicitly requested.
- All five correction regressions passed again within the focused/full suites:
  eight target/scorer mutation combinations; private exports under four umasks;
  zero-request directory substitution rejection; one recovery durability scan;
  observable file/link/directory-fsync faults with distinct collision coverage.
- `PYTHONPATH=src python -m pytest -q tests/test_execution_control.py tests/test_study_journal.py tests/test_runner.py tests/test_salesagent_target.py tests/test_salesagent_study.py tests/test_study_reporting.py tests/test_suites.py`:
  **553 passed**, 95.61s, including all **118 C2 tests**.
- `PYTHONPATH=src python -m pytest -q -rs`: **2,619 passed, 1 skipped**,
  145.61s. The only skip is the existing optional `openai` SDK collection
  skip at `tests/test_canary_sdk.py:9`; no SDK was installed or executed.
- Repository Ruff lint passed; mypy passed **49 source files**; formatting
  passed for **all 12 C2 Python files**; `git diff --check` passed.
- Separately, full-repository formatting still reports exactly the three
  baseline exceptions listed above. Each remains byte-identical to baseline.
- Repeated direct baseline comparison confirms **12 byte-identical default
  runner scenarios**, including both fingerprint schemes, target/scorer mutation,
  PASS/FAIL/ERROR and independent score preservation. Historical v1 contract
  serialized bytes and digest remain exactly unchanged.
- V2 strict policy/version binding, invalid/incomplete receipt rejection,
  downstream preparation/human/protected judge gates, quality FAIL continuation
  and infrastructure ERROR stopping all passed the synthetic regression suite.
- Read-only validation reconfirms **50 cases, six suites**, the approved dataset
  fingerprint and byte-identical dataset/descriptor/suite/matrix/semantic-rule
  files. No approved inputs were executed; scoring methodology is unchanged.

An additional bounded subprocess probe complements the checked-in incomplete
attempt death test. With sockets blocked in child and parent, the child captured
only synthetic fixture rows through MockTransport and called `os._exit(24)`
immediately before publishing `run.json`, after all eight outcomes were durable.
The parent verified the missing run/receipt, recovered only those committed
outcomes, verified the completion receipt, and read back the identical source
from private JSON/SQLite exports (`0700`/`0600`). Duplicate dispatch remained
blocked. This proves successful save-only recovery after real process death;
the existing `os._exit(23)` regression separately proves incomplete attempt
recovery remains forbidden. The probe used the canonical resolved temporary
path, as required by the export's symlink-parent rejection.

All verification passed and **no audit findings remain unresolved**. PR content
records the architecture, exact scope, correction evidence, identifiers,
regressions, historical compatibility and residual durability limits. The PR
must remain unmerged for human review. Study v1 remains **unfrozen and unexecuted**;
the Sales Agent application, C1 tooling and other development/execution worktrees
are preserved. Production registry/storage approval remains outstanding.
