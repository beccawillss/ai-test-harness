# Study v1 C2 durable capture

Status: offline implementation awaiting human review. No production registry,
actual Study freeze, live target/judge request, server or canary is created by
this change. Baseline: `46d24b91360229fe6e0d4a1aab4da29a27a45c6d`.

## Architecture and identifiers

`core.execution_control.ExecutionControl` is an optional synchronous protocol:
`prepared`, `reserve`, `response_received`, `scorer_recorded`,
`attempt_completed`, `run_assembled`. The runner knows only normalized models.
`execute_suite` supplies its validated provenance before dispatch when the
control is present. Default calls keep their prior exhaustive execution and
serialization. Control failures escape ordinary target/scorer handling.
Successful independent scorer results survive another scorer's ERROR. The
Study controller stops subsequent attempts/cases after ERROR and continues after
quality FAIL. An incomplete run is retained with its actual completed attempts;
there are no fabricated responses or unexecuted attempt results.

The Study-owned `study.journal` module implements the policy and persistence.
The harness's `SalesAgentTarget` adds an optional `SalesAgentRecorder` beside
its existing injected HTTP client/transport boundary. It checkpoints allowlisted,
validated chat before fetching its trace, then the normalized public turn before
sending another shopper message. It does not change HTTP request construction,
request bytes, session handling, timeout values or normalization rules. The
recorder receives no headers or credentials and stores no raw tool/provider
envelopes, hidden instructions or reasoning. Legitimate business errors and
quality failures remain evidence. Neither the Sales Agent application nor C1
canary tooling changes.

| Purpose | Identifier |
| --- | --- |
| Execution contract | `salesagent-study-execution-v2` |
| Capture policy | `salesagent-study-capture-fail-fast-v1` |
| Journal | `salesagent-study-journal-v1` |
| Completion receipt requirement | `salesagent-study-completion-v1` |
| Authoritative registry binding | `salesagent-study-registry-v1` |

V1 remains the existing `StudyExecutionContract` model. V2 is a separate
`StudyExecutionContractV2` model with the same evaluation fields and validators,
plus policy/journal/completion constants and a registry binding. Use
`load_execution_contract` for version-aware deserialization. The recipe retains
the existing immutable execution `document.json`/`receipt.json` bundle format.
`freeze_execution(..., registry=...)` explicitly selects v2; omitting the
registry preserves v1. No judge, rubric, anchors, threshold, projection or
human-rating methodology changes are introduced.

V2 `verify_capture` verifies the authoritative journal and exact source document
against its completion receipt. Primary/variance preparation, human manifest
export, protected judging and analysis inherit this gate. Stripping the receipt,
truncating the roster or substituting a different source cannot release judging.
The receipt is separate from the later human annotation freeze receipt; both
requirements remain applicable. Study comparisons flag changed capture policy/contract
versions; opt-in journaling adds local I/O to measured invocation/attempt timings.
Timing across capture policies must therefore be interpreted with that difference.

## Registry and durability

Proposed operational location, **subject to separate approval**:

`<approved-encrypted-local-artifact-root>/study-v1/c2-registry`

There is deliberately no default production path. The enclosing encrypted
artifact root's actual path was not supplied in this task. Do not infer it from
the source checkout or the implementation worktree. Resolve the proposal only
after the operator approves the production destination and filesystem.

Explicit initialization creates a private registry with a random registry ID,
its resolved absolute location and filesystem device/inode binding. That binding
is frozen into v2. A copied/relocated root fails verification. A POSIX advisory
lock permits one active capture or recovery writer for that registry. Inspection
is read-only. A running capture excludes save-only recovery writes.

The capture ID is the canonical SHA-256 fingerprint of:

`["salesagent-study-journal-v1", execution_contract_hash, suite_id]`

Output directories do not participate in identity or dispatch authorization.
The capture directory is claimed exclusively before target construction. Each
attempt directory and reservation is claimed exclusively before target invoke.
An existing or partial claim is never reused. Before each later attempt, the
writer rechecks its registry and all previously committed record checksums.
The writer also checks the created capture and `attempts` directory device/inode
identities before preparation and every reservation, including the first one.
Substituting either directory with a symlink or different directory blocks
dispatch. This assumes an owner-controlled registry, not a hostile filesystem.

Every record has a canonical JSON checksum envelope. Publication writes a fresh
private temporary file, flushes and fsyncs it, exclusively hard-links the complete
file to its final name, then fsyncs the containing directory. Final names are
never replaced. Canonical byte verification also rejects whitespace-only file
changes. Temporary-file cleanup cannot remove published records or mask a write
failure. Capture/attempt directory creation is followed by parent-directory fsync
before it can authorize dispatch.

Records include the claim, prepared run/provenance and required roster, each
reservation, public chat/turn checkpoints, normalized response before scoring,
each independent scorer outcome, complete attempt outcomes and an assembled run.
Completion rechecks all bindings, inputs/turns, scorer outcomes, checkpoints and
checksums. Every required attempt must have a complete normalized response and
PASS or FAIL with gated scores and no execution error. SKIP and ERROR cannot
receive completion. The receipt binds every attempt record, the preparation and
the assembled run. It is embedded in the exported source only after publication;
the journal's base run excludes that receipt to avoid a circular hash.

The recipe saves partial C2 result documents when execution returns ERROR and
reports exit status 2 with `capture_complete: false`. The partial run remains
ineligible for preparation. A journal publication failure propagates immediately;
its committed checkpoints remain available even if no result was returned.

## Offline inspection and save-only recovery

These commands are documentation, not authorization to initialize a production
registry or execute Study cases. The contract argument is the existing immutable
execution bundle directory.

```sh
PYTHONPATH=src python examples/salesagent_study.py inspect-capture \
  --contract <approved-v2-execution-bundle> --suite full

PYTHONPATH=src python examples/salesagent_study.py recover-capture \
  --contract <approved-v2-execution-bundle> --suite full \
  --output <new-unused-export-directory>
```

Inspection returns an inventory, invalid-record markers and
`dispatch_authorized: false`. It never grants permission to run again. It is
also useful while a writer is active; that inventory is not an atomic snapshot.

Recovery acquires the writer lock and verifies the authoritative registry. It
reuses the already assembled run when present. If assembly was interrupted, it
can assemble only the complete, already committed attempt outcomes under the
original run ID and prepared configuration; its finish time is the recovery
assembly time. It never completes an attempt, invokes a scorer or regenerates a
response. It rechecks all completion prerequisites, performs one fsync scan of visible evidence,
publishes only missing run/completion artifacts, and exports the verified source
to fresh `capture.json` and `source.sqlite` files. Existing journal artifacts are
never replaced. Existing export directories are rejected; choose another unused
export directory to retry only saving. The generic Python API
`recover_save_only(..., save=...)` accepts a save callback, never a target or
judge factory.

The recipe creates recovery export directories as `0700` and files as `0600`
regardless of umask, without changing process umask or existing directories.
The export parent must already exist, be owner-controlled, and have no symlink
aliases in its path. Existing destinations and symlink substitutions are
rejected. Files are exclusively created relative to a held directory descriptor;
directory identities are checked before writes and after saving. SQLite builds
in a separate private temporary directory with a pre-created `0600` database;
the closed database is copied into the export through that descriptor. Partial
exports remain private after a save failure. Choose a fresh destination for
save-only recovery; the journal remains authoritative. Callers supplying their
own Python save callback are responsible for that callback's export permissions.

Missing/corrupt/conflicting reservations, responses, scorer results, turn
checkpoints, attempt outcomes or receipts block recovery. A response checkpoint
without a complete scorer/attempt outcome is inspection-only. Preserve the
registry and obtain human review; there is no resume/retry/unreserve command.
Do not copy a stale output backup into the authoritative registry or change a
contract/registry to work around a blocked capture.

## Limits and review boundary

The harness guarantees local at-most-once dispatch for an identity under one
intact authoritative registry. It cannot guarantee exactly-once remote execution
without target-side idempotency. A crash after reservation but before dispatch
can permanently block an unissued request; a crash after remote execution but
before response capture can lose evidence of an issued request. Neither state
authorizes a replacement paid call.

Durability depends on the local filesystem honoring fsync, atomic exclusive
hard links and POSIX advisory locking. Hardware/power-loss behavior, encrypted
volume mounting, disk failure and backup/restore behavior were not tested with
real production storage. This implementation does not provide distributed locks,
Windows journal support, signatures or protection against a privileged writer
rewriting/deleting the authoritative registry. Default runner/v1 imports do not
require POSIX locking. Restoring the registry in place to an older snapshot is
not detectable in general and is forbidden operationally: backups are evidence,
not alternate dispatch authorities. Moving the registry changes its frozen
binding and needs a separately reviewed migration, never automatic recapture.
A legitimate remount that changes device identity can also require that review.
Recovery export is not an atomic two-file transaction: process death can leave
an incomplete private export or private SQLite scratch files in the operating
system's temporary directory. Cleanup is best effort and cannot undo committed
journal evidence or mask the original failure. Retry only saving to a fresh
export path after inspection. Directory identity checks do not promise defense
against concurrent same-owner or privileged tampering between filesystem calls.

Human review must approve the implementation/integration, exact encrypted
registry destination, single-authority/backup procedure, filesystem guarantees,
and later actual v2 target/evaluator freeze and live budgets. The final PR
preparation authorisation permits a verified commit, branch push and PR targeting
`main`; merging still requires separate approval. Study v1 remains unfrozen and
unexecuted. Existing worktrees and approved source revisions remain intact.

## Verification record

The initial implementation's 85 C2 tests and 520 focused regressions passed.
After the five independent-audit corrections, all 118 C2 tests, 553 focused
regressions and 2,619 full offline tests passed, with one existing optional
OpenAI SDK module skipped. Mypy
passed all 49 source files, repository-wide Ruff lint passed, and all 12 changed
Python files passed formatting. Full-repository formatting flags only three
unchanged baseline files. Exact commands and the changed-file inventory are recorded in the living
[C2 ExecPlan](plans/study-v1-c2-durable-capture.md).

Historical contract fixture canonical fingerprint:
`e9f47d68a81aa476aeded815b83ffaed1a2ca6e2ec6b54074cb52ea478034219`.
A direct in-memory comparison against the approved baseline confirmed identical
v1 contract serialized bytes and fingerprint. Frozen-clock synthetic default
runs also matched baseline serialized bytes for both dataset fingerprint
schemes, repeated attempts, target/scorer ERROR and preserved independent scores.
The correction verification additionally matches baseline JSON bytes in 12
frozen-clock default-runner scenarios including target and scorer mutation.
Case ID/tags are captured before attempts, while CaseResult validation remains
afterward, matching the baseline's evaluation order. Optional lifecycle callbacks
retain the original case identity. Legacy input mutation and v2 input isolation
retain their historical behavior.

Read-only validation confirmed the unchanged 50 cases and six suites:
full 50×1, smoke 8×1, variance 10×3, critical 12×1, adversarial 8×1,
multi-turn 20×1. All dataset, suite and matrix files are byte-identical to the
approved baseline. Dataset fingerprint remains
`4a0e40d6dce4b78cc194352bf23d69dabcc8fe3c0f440d50f2cce2bd6a956028`.
