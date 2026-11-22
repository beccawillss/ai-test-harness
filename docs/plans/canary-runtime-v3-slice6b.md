# C3b Slice 6b: single-use synthetic authority storage

## Scope and baseline

Independent human QA approved this bounded offline implementation on 2026-11-22.
GitHub main was verified at `0628ce316f09fd86cd501b6468ae5c800271c229`, the
PR #32 merge, tree `cc6aa4ba013ba50d1f56890a15bf88d5e9fd71fa`.
One feature branch/worktree was created from that exact commit:
`feat/canary-runtime-v3-slice6b-authority` at
`/private/tmp/ai-test-harness-canary-runtime-v3-slice6b`.
Existing worktrees, development changes, historical registrations and private
evidence remain untouched. No commit, push, PR or merge is authorised.

Only three additions are authorised: `src/harness/canary/authority_v3.py`,
`tests/test_canary_authority_v3.py` and this plan. All 218 baseline tracked files
must retain their exact bytes and executable modes. No dependencies, locks,
fixtures, dataset, fingerprints, existing tests or approved components may change.

## Design decisions

The independent trusted configuration fixes an absolute canonical private store
directory, synthetic store ID, host/scope, permitted audience and trust-policy
identity. It never comes from an approval or ambient environment. One-time
initialization exclusively creates the directory, database and local lock file;
returns an immutable binding including device/inodes; and records that binding
in a fixed SQLite schema. The caller must retain that binding independently.
Normal opening uses SQLite `mode=rw`, inspection uses `mode=ro`; neither creates
or resets an established store. Symlink components, hardlinked files, path/file
identity substitution, unsafe permissions and unexpected layout fail closed.

SQLite uses DELETE rollback journaling, synchronous=EXTRA, fullfsync=ON, strict
tables, uniqueness constraints and append-only triggers. All variable data uses
SQL parameters; schema and pragma statements are fixed literals. BEGIN IMMEDIATE
serializes insert admission. A nonblocking local advisory lock additionally
serializes cooperating store clients and protects inspection/layout checks. Busy
is a denial, not an automatic transaction retry. SQLite lock waits are bounded.

Consumption takes original payload/signature, expected proposal, trusted store
binding, a current synthetic-policy observation supplier and a controlled clock.
The actual unchanged Slice 6a verifier runs before storage and again after SQLite
write-lock acquisition. Policy observations have an explicit freshness window of
at most 60 seconds. Stable policy identity pins everything except revocation
entries; the exact current policy digest, including revocations, is recorded.
Changed policy or expiry during verification/waits/precommit closes consumption.

The approval authenticates its existing authorisation ID, audience and proposal.
It does not sign a run ID. Inside the transaction, the store assigns exactly one
`synthetic-run-<uuidhex>` identity, compatible with journal identifier rules, and
persists it in the consumption row. No caller-selected run ID, journal creation,
controller integration or dispatch token is introduced.

A small fsynced pending-intent marker precedes the consumption insert. It contains
safe record identifiers/digests only. It is removed only after successful commit
and explicit synchronization, or a confirmed rollback before commit admission.
A crash/ambiguous commit can leave the marker: subsequent writes are blocked,
while read-only inspection reports persisted rows where SQLite can read them
without recovery. No marker clearing, hot-journal recovery, history repair or
reset API is provided. This deliberately sacrifices availability after uncertainty.
A leftover rollback journal blocks writes; read-only inspection cannot recover it.

The final time/policy check immediately before COMMIT is the admission cutoff.
A valid cutoff does not imply that disk synchronization returns before expiry.
`consumed_at` records the successful verification boundary inside the write
transaction; it is not a physical disk-commit timestamp. The host ID is a trusted
configuration label, not hardware/OS attestation. Policy identity pins key,
principal, roles and lifetime; only revocation entries can refresh without a
separately designed store/policy migration. No migration API is included.
After COMMIT is attempted, any uncertain outcome is terminal and never retried.
Committed rows remain consumed even when no receipt returns or downstream work
fails. Inspection is not permission to retry, dispatch or reconstruct approval.

## Guarantees and limitations

Exclusivity is limited to this fixed local protected store. No multiple-host,
distributed, privileged-host, malicious same-user filesystem or rollback-resistance
guarantee is made. Trust configuration, policy supplier, clock, code, SQLite/VFS,
OS locking and filesystem are trusted. Python's SQLite API opens paths; descriptor
checks do not sandbox an adversary able to race writes in the private namespace.
All legitimate writers must use this protocol. Snapshots/copies/backups must not
be substituted as authorities. Store loss or an uncertainty marker is a blocker,
not permission to initialize a fresh store under a replacement configuration.

The schema/row checks detect accidental corruption, unexpected edits and invalid
records; locally stored checksums are not reviewer/provider authentication.
Physical power loss, broken disk flushes and network filesystem locking are not
certified. Supported verification environment: existing locked CPython 3.12.13,
SQLite 3.53.1 and system OpenSSH_9.9p2 / LibreSSL 3.3.6. No installation occurred.
The unchanged Slice 6a verifier still requires the original canonical payload,
namespace `canary-approval-v3@ai-test-harness.invalid`, exact English success
stdout for the pinned principal/key fingerprint, and empty stderr. Other OpenSSH
output protocols are unsupported until independently tested; there is no relaxed
output parsing or verification fallback in this module.
Receipts retain real_human_authorisation_authenticated=false,
source_authorised=false, provider_evidence_authenticated=false and
authorises_live_execution=false. Real identity, external controls, controller
composition, judge, Study and later slices remain separately authorised work.

SQLite references consulted read-only:
[transaction and storage assumptions](https://www.sqlite.org/atomiccommit.html),
[durability pragmas](https://www.sqlite.org/pragma.html), and
[read-only/read-write URI modes](https://www.sqlite.org/uri.html).

## Milestones

- [x] Verify remote baseline, preserve state and create isolated worktree.
- [x] Inspect Slice 6a/journal interfaces and existing locked environment.
- [x] Implement only the new authority module and tests.
- [x] Exercise real signatures, single use, conflicts and read-only inspection.
- [x] Exercise coordinated multi-process locking, crashes and storage failures.
- [x] Run focused, unchanged Slice 6a and source/journal/policy regressions.
- [x] Run full locked offline suite excluding historical listening-server tests.
- [x] Run Ruff, mypy, formatting, whitespace and complete preservation inventory.
- [x] Record exact results and independent-QA recommendation; stop without commit.

## Public interfaces and persisted contract

- `policy_identity(policy)` computes the stable synthetic policy pin.
- `initialize_store(TrustedStoreConfiguration)` exclusively creates a store and
  returns `AuthorityStoreBinding`. Keep this binding in independently trusted
  configuration; passing arbitrary replacement bindings is outside the guarantee.
- `consume_approval(payload, signature, *, expected, store, policy, clock)` calls
  the actual Slice 6a verifier and returns an immutable `ConsumptionReceipt` only
  after confirmed commit, synchronization and pending-marker finalization. `policy`
  supplies a strict `PolicyObservation` with explicit UTC freshness boundaries;
  `clock` supplies a trusted UTC whole-second datetime. No caller run-ID argument
  or constructed `ApprovalVerification` admission path exists.
- `inspect_consumption(store, authorisation_id, *, expected_record=None)` returns
  consumed, absent, conflict, corrupt or unavailable, with bounded fixed issues.
  It accepts no policy, signature, mutation or execution callback. A supplied
  different expected receipt detects a conflict; it cannot change persisted state.

The fixed schema consists of one immutable `store_identity` row plus append-only
`consumptions` rows, strict tables, a primary key on authorisation ID, and unique
intended-run and record IDs. Canonical receipt JSON and a digest must agree with
each indexed column, the store identity, audience and policy pin. Opening checks
the exact schema, versions, identity, rows and SQLite quick_check. These checks
detect corruption; they do not authenticate local evidence against a privileged
attacker who can replace code, trusted configuration, checksums or stored state.

Receipts include payload/signature, exact policy, proposal/source and verification
digests; synthetic signer principal/key digest; store/audience/auth/run/record IDs;
time; and the four explicit false authority flags. They omit raw signed content,
signatures, public/private key material and project/provisioning values. The
database identity row necessarily contains the trusted store path; receipts do not.

## Crash and concurrency evidence

Tests use actual system OpenSSH signatures and ephemeral synthetic Ed25519 keys
from unchanged Slice 6a fixtures. Temporary key directories are deleted at fixture
teardown; stores/artifacts remain only under explicit test temporary directories
outside repositories. No sleep-based race assertions or network services occur.

| Coordinated boundary | Required and observed outcome |
| --- | --- |
| SIGKILL before verification or transaction admission | No row; database byte-identical; the test knows no transaction began |
| SIGKILL before insert, after insert, before commit | No consumed row (or read-only unavailable); database byte-identical; pending intent blocks every later write |
| Commit call raises before real COMMIT | Outcome unknown; row absent; marker blocks writes |
| Real COMMIT then raised error / SIGKILL / sync or cleanup failure | Committed row persists; marker blocks further writes |
| SIGKILL after receipt returned | Row persists; replay denied |
| Synthetic downstream journal-creation failure | No release; row persists; replay denied |
| Same-ID four-process race | Exactly one successful consumption; known-busy losers may explicitly attempt again and are then denied replay |
| Distinct-ID four-process race | Explicit known-busy retries succeed independently; all run IDs unique |
| Active writer versus separate-process symlink alias and copied store | Alias/copy denied; original writer alone commits; inspection reports busy while writer holds lock |
| Proven SQLite write-lock contention, followed by expiry or revocation | Verifier reruns after lock release; consumption denied |
| Real SQLite SQLITE_FULL and simulated I/O failures | Insert rolls back; earlier record preserved; no automatic retry |
| Rollback cannot be confirmed | Outcome unknown; pending marker retained |

Tests also cover invalid/unknown-key/wrong-namespace/principal/role/revoked
signatures, canonical-byte rejection, proposal/audience/policy mismatches,
stale/future policy, final-boundary changes, duplicate/conflicting IDs, strict
configuration, read-only inspection, schema/row/header corruption, missing stores,
partial initialization, inode replacement, hardlinks/FIFOs/symlinks/aliases,
permissions, sidecars, fixed private diagnostics and import/ambient-store isolation.
There is no API for marker removal, reset, repair, reissue or downstream dispatch.

## Verification record

Fresh final focused authority run: **100 passed, no skips, 23.06 seconds**.
The unchanged Slice 6a/runtime/source/policy/selection/journal/fault regression
command passed **694 tests, with one optional skip, in 153.70 seconds**. This
includes all 169 unchanged Slice 6a tests, 258 runtime/source/policy/selection
tests and 267 journal/fault tests. The skip is the optional complete source check
requiring the separate pinned CPython 3.13 worker (`test_canary_runtime_v3.py:452`).
Ruff across src/tests, mypy across all 63 source files and formatting for both
new Python files passed. All 218 baseline tracked files were verified exact in
bytes and executable modes; exactly three untracked additions and no staged
changes exist. Final full locked offline verification passed **3,899 tests, with
six optional skips and zero failures, in 587.40 seconds**. It included the final
concurrent alias/copy test added after the first full run began.
The earlier run (without that final additional test) completed with 3,898 passed,
six optional skips and no failures in 586.35 seconds; it is not substituted for
the final full-suite result.

No real credentials, providers, Sales Agent service, judge or Study ran. All
169 unchanged Slice 6a tests passed in the combined regression run. Full offline
verification excludes only historical listening-server `tests/test_canary_controller.py`;
optional pinned application/SDK/source fixtures must be reported as skips, never
as executed integration successes.

| Final check | Fresh Slice 6b result |
| --- | --- |
| Authority suite | 100 passed, 0 skipped, 0 failures; 23.06 seconds |
| Unchanged Slice 6a/source/policy/journal regression command | 694 passed, 1 optional skip, 0 failures; 153.70 seconds |
| Complete locked offline suite | 3,899 passed, 6 optional skips, 0 failures; 587.40 seconds |
| Ruff, src/tests | PASS |
| Mypy, src | PASS, 63 source files |
| Formatting, new Python files | PASS, both files |
| Tracked/index and explicit new-file whitespace checks | PASS |
| Protected baseline byte/executable-mode inventory | PASS, all 218 tracked files |
| New file scope and modes | Exactly three untracked regular nonexecutable files; no staged changes |
| Historical definitions, policies, fixture and lock identities | Exact approved values, recomputed below |

The full suite's six optional skips were:

- `tests/test_canary_controller_v3_application.py:26`: separately enabled pinned
  application integration suite; not enabled here.
- `tests/test_canary_instrumentation_v3_sdk.py:22`: optional pinned OpenAI 3.3.1
  runtime unavailable in the locked harness environment.
- `tests/test_canary_sdk.py:9`: optional OpenAI package absent.
- `tests/test_canary_selection_state.py:5`: optional pinned application runtime.
- `tests/test_canary_state.py:13`: optional pinned application runtime.
- `tests/test_canary_runtime_v3.py:452`: optional complete CPython 3.13 source check.

Those pinned application/SDK modules and complete source fixture were not
executed. No core approval or authority test skipped. All reported final counts
and static checks were freshly executed in Slice 6b, rather than inherited from
Slice 6a. The final full suite includes unchanged C1, v2.1/v3, source, journal
finalization/fault, mock-only controller, driver, instrumentation and policy unit
coverage. Test fixtures and fake targets do not constitute a real application,
provider, judge or Study execution.

## Reproduction commands

Run from the isolated Slice 6b worktree using the existing locked interpreter.
No dependency installation, lock update or package download is needed.

```sh
env -i PATH=/usr/bin:/bin PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /private/tmp/ai-test-harness-canary-runtime-v3-slice2/.venv/bin/python -B -m pytest -q --tb=short -rs -p no:cacheprovider tests/test_canary_authority_v3.py
env -i PATH=/usr/bin:/bin PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /private/tmp/ai-test-harness-canary-runtime-v3-slice2/.venv/bin/python -B -m pytest -q --tb=short -rs -p no:cacheprovider tests/test_canary_approval_v3.py tests/test_canary_runtime_v3.py tests/test_canary_execution_policy.py tests/test_canary_selection_v3.py tests/test_canary_journal_v3.py tests/test_canary_journal_v3_faults.py
env -i PATH=/usr/bin:/bin PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /private/tmp/ai-test-harness-canary-runtime-v3-slice2/.venv/bin/python -B -m pytest -q --tb=short -rs -p no:cacheprovider --ignore=tests/test_canary_controller.py
env -i PATH=/usr/bin:/bin PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /private/tmp/ai-test-harness-canary-runtime-v3-slice2/.venv/bin/python -B -m ruff check --no-cache src tests
env -i PATH=/usr/bin:/bin PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /private/tmp/ai-test-harness-canary-runtime-v3-slice2/.venv/bin/python -B -m mypy --cache-dir=/private/tmp/canary-slice6b-mypy src
env -i PATH=/usr/bin:/bin PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /private/tmp/ai-test-harness-canary-runtime-v3-slice2/.venv/bin/python -B -m ruff format --check --no-cache src/harness/canary/authority_v3.py tests/test_canary_authority_v3.py
git diff --check
git diff --cached --check
```

The complete preservation check reads `git ls-tree -rz` for the exact approved
base, hashes every current tracked file with the Git blob header, compares every
blob ID and executable mode, and requires exactly the three authorised untracked
additions. New files also receive explicit trailing-whitespace/newline, mode and
embedded private-key/signature-header checks because normal `git diff --check`
does not inspect untracked additions. No synthetic stores/keys/run artifacts are
created in the repository or added to the index.

Historical compatibility was freshly recomputed with unchanged runtime helpers:
C1 roster `e8778ce74a270e6efbe490198d01e8b9c50bcc43387a02bff5f00b42304d5794`,
v2.1 `3c632f6ce5e8b9eda42b4a0a0f91ccb82f4f34783da3b9638762b84351c9c2f9`,
v3 definition `e76fd0e10f1176d6aa421a2b5de93f9503dceaa422b0631c2c8f7c957aa75607`,
v3 acceptance `575e304da8203b537d281d82a667e73dbf419fc95caee8df82dea6e7feabfce7`,
and v3 execution `a4d8cdaaa4960ddf406c37703965d164595cea320cfa83c0ddd40fad797fa551`.
Pinned application revision remains `3320e556540d3f95bee1e8509f13e558ce266b6c`;
fixture hashes remain products `70960848556e1e63c1bd3337203ab057a9fae1e7f6d343fb383f85a838c541ab`
and discounts `3147b6863b9458c928459cbb824d01b0e3b73aa2c5da2979debb78de4e1caf0c`.
Harness lock SHA-256 remains `a8a1997cb57cf88bad6d8b00e38efa0b62b77c2ad0057c667ab52933585b1dba`;
the unchanged runtime dependency checker accepted every installed locked version.
The original dirty checkout's seven modified tracked paths and two untracked
entries remain as found; no pre-existing worktree or private evidence was edited.

## Independent QA recommendation

**GO for preparation of a bounded Slice 6b PR, subject to independent human QA.**
The three-file offline milestone is implemented and verified. It authenticates
synthetic signatures and persists local single-use consumption only; it grants
no execution admission, real-human authentication, source authorisation,
provider evidence or live authority. Local rollback, privileged filesystem
replacement, multiple machines, hardware trust, real identity, live project
controls and controller/coordinator composition remain future requirements.
Crash uncertainty may permanently block the fixed store; availability/recovery
is intentionally not solved through a reset or alternate store.

HEAD remains the exact approved merged-main commit. No commit, push, PR, merge,
key enrolment, authority/controller integration or subsequent milestone occurred.
Stop here for independent human QA; publication needs separate authorisation.
