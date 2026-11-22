# C3b Slice 6c — Detached Evidence Provenance

## Authorisation and exact baseline

Independent human QA approved bounded offline implementation and verification of
M0–M5 on 2026-11-22. The reviewed ExecPlan and four-refinement addendum are one
specification; the addendum takes precedence. No commit, push, PR, merge, live
canary or later slice is authorised. Provisional resource ceilings require final
independent QA acceptance before publication.

- Parent: `2cbeea571d2b37968c30e9f4e2f98dca4ac20e1e`.
- Tree: `9ce8b22bb7d7594b4fe98190ac983bcebd1c03ab`.
- Branch: `feat/canary-runtime-v3-slice6c-envelope`.
- Worktree: `/private/tmp/ai-test-harness-canary-runtime-v3-slice6c`.
- Private verification root: `/private/tmp/canary-slice6c-qa-7n4lujbn`.
- Complete approved inventory: 221 regular files, recorded with blob IDs and
  executable modes in `baseline-inventory.json` in that private verification root.

The merge commit was missing locally and acquired non-destructively by authorised
fetch. Its exact tree and all 221 worktree files were verified before additions.
The original dirty checkout and all pre-existing worktrees remain untouched.
No reset, clean, pruning, rebase, force push or branch/worktree deletion is allowed.

Only three new files are authorised:

1. `src/harness/canary/envelope_v3.py`.
2. `tests/test_canary_envelope_v3.py`.
3. This living plan.

Every baseline production/test/plan/dataset/fixture/lock/evidence file is protected
in bytes and executable mode. Final inventory also detects ignored generated
files and requires exactly these three additions, with no staged changes.

## Objective, exclusions and trust boundaries

Bind a persisted synthetic consumption receipt, matching original signed-input
byte digests, an explicitly linked synthetic journal, its complete *currently
inspected validated* sequence, and compact recorded source/outcome/accounting
claims. Do not redefine the historical partial `evidence_sha256`.

The module contains a pure strict schema/serialization/commitment core, a read-only
assembler calling unchanged public inspectors, anchored and source-backed
verifiers, and a private exclusive-create publisher. A model instance is not proof
of inspection. Publication validates/writes a representation; it authenticates no
claims. No public API accepts caller-labelled validated inspection reports.

No controller integration or retrospective controller identity mapping; execution
admission; approval consumption/reissue/retry/recovery/reset; real-human identity;
source authorisation; authenticated provider evidence; production OpenSSH/signing;
credential discovery; provider/billing/Study/judge execution; network service; new
custody service; dependency change; or Slice 6d work is permitted.

The executing code, process, independently retained configuration, local OS,
SQLite/VFS, cooperative locks and protected local filesystem remain trusted.
Hostile same-user/privileged races, mount aliases, rollback, distributed use,
broken flushes and physical power-loss certification are unsupported.

## Reviewed schema and commitments

Strict, deeply immutable models forbid unknown fields. Every public boundary
revalidates copied/constructed instances. Exact canonical UTF-8 has no trailing
newline; duplicate keys, missing fields, coercions, nonfinite numbers and unknown
versions fail with private fixed categories.

- Envelope schema: `canary-detached-evidence-envelope-v1`.
- Canonicalization: `replay-canonical-json-v1` (existing unchanged implementation).
- Commitment profile: `canary-detached-envelope-commitment-sha256-v1`.
- Authoritative value/function/expected-reference field:
  `envelope_commitment_sha256`.

Exact commitment:

```python
fingerprint({
    "domain": "canary-detached-envelope-v1",
    "canonicalization": "replay-canonical-json-v1",
    "envelope": envelope.model_dump(mode="json"),
})
```

No separate raw file-byte SHA-256 is retained. The commitment is not raw SHA-256
of `envelope.json`. All serialization/publication/verification paths use this one
definition. Source-backed verification additionally compares exact canonical bytes.

Complete current-history commitment:

```python
fingerprint({
    "domain": "canary-detached-journal-history-v1",
    "canonicalization": "replay-canonical-json-v1",
    "journal_schema": journal_schema,
    "registry_id": registry_id,
    "run_id": run_id,
    "records": records,
})
```

Include every validated record field/revision, including manifest, decisions,
reservations, telemetry, results, public evidence, assessments, outcomes, shutdown,
completion and acknowledgement. Do not persist records themselves in the envelope.
Malformed/missing-middle records are corruption. Suffix deletion may leave valid
incomplete history; without an earlier independent reference historical
completeness is not established. Earlier anchored artifacts/source comparisons
detect changed history, not completeness preceding that reference.

Allowlisted envelope groups: format; fixed synthetic limitations; exact existing
ConsumptionReceipt and store-binding fingerprint; journal schema/registry-binding
fingerprint/registry/run/approval identities; current-history commitment/count;
historical partial bundle commitment; compact source projection; recorded journal
execution/assessment statuses, shutdown booleans and safe accounting.

Source projection: source schema/provenance/profile/digest, harness/application
commit/tree, locks, runtime, definition identifier/binding digest and existing
roster/definition/acceptance/execution/v2.1 identities, policies, revision, fixtures,
inference, limits and definition storage-schema label. Exclude receipt reference,
turn messages, raw reports, paths/inodes, conversation/tool prose, unnecessary
provider/session/trace IDs, project/provisioning values, keys, headers and errors.

Accounting retains logical/provider/unknown/incomplete/retryable/error counters,
exact nonnegative finite decimal subtotal/nullable total, billing_verified=false.
No inferred token totals or new cost estimator. Quality statuses and execution
completion remain separate; human_review=PENDING and invocation_status=not-established.
All real-human/source/provider/live/execution-admission/fresh-signature authority
fields remain false. Historical completeness is always not-established.

## Acquisition and verification contract

Validate original bytes and expected proposal with parse_manifest, never
verify_approval. No clock/current expiry/revocation refresh. Then bounded
preflight/inspection/postflight in exactly A1/J1/A2/J2 order:

1. inspect_consumption(expected authorisation).
2. inspect_run(expected run).
3. inspect_consumption(expected authorisation, expected_record=A1.record).
4. inspect_run(expected run).

Authority must be consumed, issue-free and exactly equal twice. Journals must be
structurally valid, issue/pending-free, with equal complete-history commitments,
counts and safe projections. Fail immediately; no retries. Different eligible
observations produce source_changed. This is not an atomic snapshot or proof of
uninterrupted stability/current global health.

Require signed authorisation == receipt authorisation == journal approval ID;
receipt intended run == expected/journal run; exact proposed and journal source
receipt equality; source/proposal/payload/signature digests; store audience/policy;
registry binding; issuer principal; recorded consumption time within signed
window; all false-authority fields. Check any instrumentation definition, source,
registry, run, project/organisation against proposal. Unprofiled histories make no
observed-provider-configuration claim. Do not reconstruct verification_sha256:
its original verified_at is not fully retained.

ExpectedEnvelopeReference requires schema, commitment profile, commitment,
store ID/binding digest, registry ID/binding digest, authorisation, audience, run.
No expected values come from the artifact being verified. Artifact verification
requires a separately supplied reference. Source-backed verification first checks
that reference, then reassembles using expected identities and compares bytes.
Actual source matching/signature authentication/controller return/provider
authenticity are not inferred. Read-only operations create no files or caches.

## Trusted publication and handoff

TrustedPublicationRoot(schema_id=canary-private-publication-root-v1, absolute path,
device, directory_inode) is independently provisioned/retained caller configuration,
not artifact/environment/discovery data. Existing root must be same-owner 0700.
The caller guarantees it is outside repositories/historical/other protected stores;
the module cannot discover all such namespaces. No initialisation service is added.

publication_id matches `[A-Za-z0-9][A-Za-z0-9._-]{0,63}` excluding dot/dotdot.
Only one direct child is allowed. Reject root/source overlap in both directions,
including source directory metadata identity checks against retained bindings.
These are path-isolation checks, not source-content inspection. Descriptor walks
reject symlinks; retain descriptors and recheck root/path identities at completion.

Exclusive fresh 0700 child; fsync parent; create 0600 .pending-envelope with
O_EXCL/O_NOFOLLOW; complete write/flush/file fsync; no-overwrite link to
envelope.json; directory fsync; unlink pending; final file and directory fsync;
read-only recheck final bytes/identity/owner/mode/single link/exact layout; recheck
path/root identities; close successfully; only then return success. Never use an
overwriting rename. Readers reject pending/partial layout; visible anchored bytes
do not prove publisher return or physical durability. Existing destination is
always denial, even for equal data. No rollback, cleanup of partial output or retry.

Validation before creation: no output. EEXIST: destination_exists. Confirmed child
creation but before final-link attempt failure: publication_failed. Ambiguous
creation or any failure/interruption after link attempt, final checks or close:
publication_outcome_unknown. Preserve partial state; source state is unchanged.

PublicationReceipt returns schema, publication_id, bytes_written,
publication_status=local-publication-protocol-completed, complete deterministic
reference_candidate, source_inspections_performed=false and
independent_custody=not-established-by-publisher. Operator may review/retain that
candidate separately. A neighbouring receipt is not automatically independent.
No verifier discovers/adopts sidecars. Substitution of both artifact and trusted
reference is outside the guarantee.

## Provisional resource ceilings

Envelope/payload 65,536 bytes; signature/reference 4,096 bytes; envelope depth 16,
4,096 values; journal 2,048 records, 512 KiB per record, 16 MiB aggregate/canonical
records, depth 64 and 500,000 values; authority database preflight 16 MiB.
Reject, never truncate. Existing inspectors have no internal budget parameters;
preflight/postflight cannot guarantee hard end-to-end memory/time bounds under
races. Trusted bounded local stores are required. No inspector changes/supervisor.

Four turns, 24 calls and 72 attempts guide fixture volume, not a universal journal
size bound: evidence/control events/revisions vary. Measure representative complete,
instrumented/unprofiled, maximum-call/attempt, revision, incomplete/uncertain,
larger-public-evidence and multi-receipt-store fixtures in M2. Record byte/count/
depth/node/envelope sizes. Independent QA must accept measurements; no silent raises.

## Milestones and acceptance

- [x] M0 exact parent/tree, isolated workspace, 221-file preservation inventory,
  unchanged locked environment and living plan.
- [x] M1 pure schema, bounded canonical operations and commitments; TestSchema.
- [x] M2 public-inspector assembly, bounds/privacy/linkage, process races and
  measurements; TestInspectionLimits/TestAssembly/TestInspectionProcesses/TestPrivacy
  and unchanged approval/authority/journal/fault suites.
- [x] M3 independent artifact/reference and source verification; TestArtifactVerification
  and TestSourceVerification.
- [x] M4 private exclusive publication; TestPublication/TestPublicationProcesses.
- [x] M5 complete new suite, historical regressions/full offline suite, static and
  full inventory checks; TestCompatibility and independent QA handoff.

Test malformed/canonical/deep/oversize/copied models; full-sequence tamper/reorder/
middle deletion/substitution/rechaining/suffix distinction; exact bindings and
forged claims; all authority statuses/pending/recovery, journal busy/corruption/
pending; changed observations with barrier-controlled processes; valid incomplete/
uncertain and completed behavioural FAIL/pending review; original-byte agreement
without cryptographic claims; reference/candidate separation; root substitution/
overlap/permissions/symlink/FIFO/hardlinks; duplicate publisher/concurrent reader;
short write/full disk/link/unlink/fsync/reopen/close/interruption/SIGKILL boundaries;
privacy sentinels, no network/credentials/authority side effects and full preservation.
Use actual persisted synthetic fixtures and ephemeral approved test keys outside
repositories. No core skips. Pipes/barriers, not sleep-based race assertions.

## Verification environment, commands and execution record

M0 fresh: CPython 3.12.13, SQLite 3.53.1; installed dependencies pass unchanged
runtime dependency checker; harness lock SHA-256
`a8a1997cb57cf88bad6d8b00e38efa0b62b77c2ad0057c667ab52933585b1dba`.
All 221 baseline bytes/modes pass. No tests run in M0. Stripped-environment Git
emitted only its existing Darwin temporary-directory discovery warning.

Interpreter `/private/tmp/ai-test-harness-canary-runtime-v3-slice2/.venv/bin/python`.
Each pytest invocation uses env -i, PATH=/usr/bin:/bin, LC_ALL=C, LANG=C,
PYTHONPATH=src, PYTHONDONTWRITEBYTECODE=1, python -B, -q --tb=short -rs,
-p no:cacheprovider, and a fresh --basetemp child under the private verification
root. Capture commands/results there; never reuse a base directory or delete
historical pytest roots. Static caches also remain in that new private root.

Final commands: full new file; relevant runtime/execution/selection/evidence/driver/
controller suites; full pytest --ignore=tests/test_canary_controller.py (historical
listening server); ruff check --no-cache src tests; mypy --cache-dir=<fresh private
root>/mypy src; ruff format --check --no-cache for the two new Python files;
git diff --check; git diff --cached --exit-code <approved parent>; final full
byte/mode/new-file/whitespace inventory. Report optional historical skips as skips,
never as executed integration successes. Do not enable pinned app/SDK live modes.

Subsequent milestone results, exact commands, corrections and fixture measurements
will be appended as they occur. No inherited result is a freshly executed check.

### M1 fresh execution record

Added the pure schema/commitment core and TestSchema in the two authorised Python
files. Command (using the common environment above): pytest
`--basetemp=/private/tmp/canary-slice6c-qa-7n4lujbn/m1-01
tests/test_canary_envelope_v3.py::TestSchema`: **59 passed, 0 skipped, 0.30s**.
New-file Ruff formatting completed; Ruff check passed after removing one unused
test import. Mypy initially identified five Literal-default annotations; explicit
literal/Final defaults corrected those type annotations without changing the
contract. Focused mypy now passes. No source stores or execution APIs were used
by the pure tests. M2 source acquisition was not implemented at that checkpoint.

### M2 implementation and provisional measurements

Implemented public-inspector acquisition and exact A1/J1/A2/J2 ordering, original
byte-digest/identity/source/profile linkage, source eligibility, bounded preflight
and postflight, deterministic private projections and complete-current-history
commitment. No inspector or other baseline file changed. Public APIs never call
OpenSSH or approval consumption. Internal read-only metadata preflight does not
provide hard inspector memory/time budgets. Independent synthetic journal fixtures
use the store-allocated run identity, not controller IDs.

Fresh `pytest --basetemp=<qa>/m2-01` for TestAssembly/TestInspectionLimits/TestPrivacy:
**43 passed, 0 skipped, 22.67s**. Separate barrier-controlled spawned-process tests
`--basetemp=<qa>/m2-process-01 TestInspectionProcesses`: **4 passed, 0 skipped,
2.64s**. These cover held journal/authority writers, a valid changed source record
between inspections, and an unrelated clean authority append. A later measurement
output was added to the last test and will run in final focused verification.
Focused Ruff/mypy pass after routine import/style corrections. Unchanged
approval/authority/journal/fault regressions are running, not yet claimed passed.

Representative fixture results are persisted as measurements.json below m2-01:

| Fixture | Records | Largest record B | Aggregate B | Canonical records B | Depth / values | Envelope B | DB B | Calls / attempts |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | --- |
| Complete | 45 | 4,102 | 48,878 | 44,964 | 12 / 3,545 | 5,672 | 24,576 | 4 / 4 |
| Profiled | 46 | 4,102 | 59,806 | 55,805 | 12 / 4,127 | 5,672 | 24,576 | 4 / 4 |
| Profiled maximum | 222 | 4,102 | 265,502 | 246,189 | 12 / 16,407 | 5,676 | 24,576 | 24 / 72 |
| Three assessments/turn | 53 | 4,102 | 57,528 | 52,918 | 12 / 4,089 | 5,672 | 24,576 | 4 / 4 |
| Larger public prose | 45 | 24,920 | 144,730 | 140,816 | 12 / 3,545 | 5,672 | 24,576 | 4 / 4 |
| Incomplete | 1 | 4,102 | 4,102 | 4,016 | 7 / 193 | 5,586 | 24,576 | 0 / 0 |
| Operationally uncertain | 5 | 4,102 | 7,316 | 6,882 | 7 / 405 | 5,612 | 24,576 | 1 / 1 |

The 24/72 fixture is constructible through public profiled journal methods with
two recorded known-zero retryable failures then one completion per call. No real
provider was used. All provisional limits fit without raising any ceiling. These
representative results do not prove all valid journals fit; final human QA
acceptance of v1 limits remains required before publication.

M2 completed: unchanged `test_canary_approval_v3.py`,
`test_canary_authority_v3.py`, `test_canary_journal_v3.py` and
`test_canary_journal_v3_faults.py`, with `--basetemp=<qa>/m2-regression-01`:
**536 passed, 0 skipped, 167.78s**. Additional actual oversized-count/aggregate
preflight tests: **2 passed, 0 skipped, 1.04s** (`m2-limits-02`). Updated unrelated
append/measurement test: **1 passed, 0 skipped, 0.89s** (`m2-process-02`). Fresh
221-file byte/mode preservation and unchanged-index checks passed after M2.

### M3 fresh execution record

Implemented explicit independent-reference checks before source access, exact
canonical artifact/structured-commitment verification, source-backed reassembly
comparison, retained TrustedPublicationRoot and safe read-only reopening. The
verifier compares observed fields against supplied expected fields; it never
constructs/adopts its own expected reference or discovers sidecars. Read checks
private ownership/modes, no-follow components, single-link regular files, bounded
reads, stable observed file/directory identities and exact layout. Root exclusion
responsibilities remain with the trusted caller. No directories/files are created
by read/verify APIs, and no signatures are authenticated.

Fresh command `pytest --basetemp=<qa>/m3-01` for TestArtifactVerification and
TestSourceVerification: **33 passed, 0 skipped, 3.83s**. Covers all reference fields,
raw-hash substitution, replaced artifact/reference limits, symlink/FIFO/hardlink/
pending/mode/size rejection, anchored suffix/timestamp/corruption changes and
repeatable byte-preserving source checks. New-file Ruff and mypy pass after
formatting and a fixed-diagnostic exception annotation. Publisher is not yet
implemented at that checkpoint; reopening fixtures were explicitly written by test setup only.

### M4 fresh execution record

Implemented direct-child publication under independently retained private root,
source directory metadata/isolation gates, exclusive creation, unbuffered complete
write, file/directory synchronization, no-overwrite hardlink publication, pending
unlink/final sync, byte/identity/layout checks and conservative fixed uncertainty.
No source contents are inspected by publication. Deterministic reference_candidate
handoff contains the reviewed structured commitment and all expected context; no
independent custody is asserted. Partial destinations are preserved without retry.

Fresh `pytest --basetemp=<qa>/m4-01 TestPublication`: **61 passed, 0 skipped,
16.54s**. Actual write/link/unlink/sync/read/close errors and interrupts, duplicate
equal/different output, invalid root/child/source overlap and substitutions pass.
Fresh process run `--basetemp=<qa>/m4-process-01 TestPublicationProcesses`:
**72 passed, 0 skipped, 24.03s**. At collection time that class temporarily also
contained 60 already exercised publication cases; the run comprises **12 new
process tests plus those 60 repeated cases**. Class placement was subsequently
corrected without changing test semantics. The 12 process tests use barriers for
three competing publishers, partial/concurrent reading and ten SIGKILL boundaries
from mkdir through publisher return. No physical power loss is simulated/claimed.
Both new files pass focused Ruff and mypy. M5 will run all classes on final source.

### M5 checks completed so far

Fresh final focused run `m5-focused-command.json` / `m5-focused.log`,
`--basetemp=<qa>/m5-focused-01 tests/test_canary_envelope_v3.py`:
**217 passed, 0 skipped, 54.13s**. Includes corrected test-class grouping and every
core schema/assembly/verification/publication/process/privacy/compatibility test.
Fresh `TestCompatibility` development check: **3 passed, 0 skipped, 1.22s**.
Its separate-process audit rejects filesystem writes, subprocess/network activity,
non-readonly SQLite and authority/signature/initialisation APIs during import,
assembly, anchored verification, source comparison and read-only reopening.
Complete protected byte/mode/index/new-file/ignored-file/whitespace inventory and
historical fingerprints/lock identities pass in that final focused run.

Fresh final static checks: `ruff check --no-cache src tests` PASS;
`mypy --cache-dir=<qa>/mypy-final src` PASS (**64 source files**);
`ruff format --check --no-cache` for both new Python files PASS. The first audit
test lint check required explicit subprocess check=False; corrected before the
final focused/static checks. No implementation guarantee/assertion was relaxed.

Unchanged relevant regressions (`m5-relevant-command.json` / `.log`),
`--basetemp=<qa>/m5-relevant-01`: **518 passed, 1 optional skip, 196.62s**.
The skip is runtime_v3.py:452, the separately enabled pinned CPython 3.13 source
worker. This is not an executed integration success. Final QA resource acceptance
and non-test publication remain pending separate approval.

Final security review found a canonical-path bug in the new helper: pathlib keeps
the POSIX `//` anchor, permitting differently spelled same-directory source roots
to evade lexical overlap checks. An actual isolated synthetic-source regression
failed before correction (**1 failed, 0.80s**, m5-path-regression-before). Requiring
exactly the single `/` anchor fixes the existing approved canonical-path guarantee;
no protected component/contract/limit changed. The new regression passes
(**1 passed, 0.77s**, m5-path-regression-after). The obsolete full-suite run was
deliberately interrupted and is not final acceptance evidence. Final focused,
static and full-suite checks will be rerun on the corrected source.

The same review exercised overlap without lexical shortcuts, including actual
local case aliases where available. Three metadata-ancestry regressions failed
before correction (**3 failed, 1.37s**, m5-ancestry-before). The new private walk
now compares actual device/inode ancestry along *only the supplied bound paths*
in both directions, in addition to spelling checks. This establishes the approved
source-root separation on case-insensitive/normalising local filesystems without
a discovery service. Mount aliases/hostile races remain unsupported. The four
path regressions pass after correction; final focused/static/full checks will
use this source. Earlier full runs interrupted for these corrections are not
acceptance evidence; all partial logs and synthetic fixtures are preserved.

Fresh final path coverage: **4 passed, 0 skipped, 1.55s** (m5-ancestry-after).
On the source with actual-ancestry and canonical-anchor checks, the complete core
acceptance run (`m5-core-acceptance-command.json` / `.log`) passes **221 tests,
0 skipped, 57.53s**. Fresh `ruff check --no-cache src tests`, mypy across all
**64 source files** (`mypy-acceptance` cache), and new-file formatting check pass.
The complete `m5-full-acceptance` run now uses that corrected production source
and the same final test bytes. No further Python changes are planned. Earlier
217/218-test runs are checkpoints, not substitutes for the 221-test acceptance.

Superseded-run accounting: m5-full ended on deliberate SIGINT after 1,410 passes
and five module-level skips (exit 2), before the complete suite finished.
m5-full-final absorbed SIGINT in a tested execution/error path, continued with a
failure marker, and was subsequently terminated along with its one owned test
child (exit -15). Neither incomplete run establishes a final result. Both logs
remain preserved; no assertion was weakened or failed case removed. Only the
uninterrupted m5-full-acceptance run on the corrected source can satisfy M5.

The final two Python artifact identities are recorded independently in
`<qa>/acceptance-python-identities.json`: source SHA-256
`a7388a706b5bb4238504037a88681f6c9ade650115db82c724b24435c5241317`,
test SHA-256 `c9ddb23b75336b60a17e7c739ac8022fb35d961a5abed67ea3ae19ae15c7ab7f`.
Both are regular nonexecutable files. These are source-file inventory hashes,
not the envelope commitment or a new runtime assurance claim.

### Final uninterrupted acceptance and handoff

The corrected production/test Python identities above are unchanged throughout
the final core and full acceptance checks. Fresh final full offline command is
recorded exactly in `<qa>/m5-full-acceptance-command.json`; output is
`<qa>/m5-full-acceptance.log`. It ran:

```sh
env -i PATH=/usr/bin:/bin LC_ALL=C LANG=C PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 \
  /private/tmp/ai-test-harness-canary-runtime-v3-slice2/.venv/bin/python -B -m pytest \
  -q --tb=short -rs -p no:cacheprovider \
  --basetemp=/private/tmp/canary-slice6c-qa-7n4lujbn/m5-full-acceptance-01 \
  --ignore=tests/test_canary_controller.py
```

**4,120 passed, 6 optional skips, 0 failures, 633.45s**. No core envelope skips.
Only the historical listening-server module was excluded, as approved. Skips:

- test_canary_controller_v3_application.py:26: separately enabled pinned app suite.
- test_canary_instrumentation_v3_sdk.py:22: optional pinned OpenAI 3.3.1 runtime.
- test_canary_sdk.py:9: optional OpenAI package absent.
- test_canary_selection_state.py:5: optional pinned application runtime.
- test_canary_state.py:13: optional pinned application runtime.
- test_canary_runtime_v3.py:452: optional complete CPython 3.13 source worker.

These were not executed as integration successes. All milestone/full/static
results in this document were freshly executed in this task, with superseded and
negative-regression runs explicitly distinguished. No inherited passing count
substitutes for final acceptance.

Final representative high-water measurements from eight fixtures in
`<qa>/m5-core-acceptance-01/*/measurements.json`:

| Metric | Measured | Provisional ceiling |
| --- | ---: | ---: |
| Logical calls / attempts | 24 / 72 | Existing 24 / 72 |
| Records | 222 | 2,048 |
| Largest record bytes | 24,920 | 524,288 |
| Aggregate record bytes | 265,518 | 16,777,216 |
| Canonical record bytes | 246,205 | 16,777,216 |
| Record depth / values | 12 / 16,407 | 64 / 500,000 |
| Envelope bytes | 5,676 | 65,536 |
| Authority database bytes, including multiple receipts | 24,576 | 16,777,216 |

Absolute temporary path lengths explain small record-size differences from the
M2 table. No ceiling was raised. Tests cover preflight rejection before inspectors,
post-inspection growth, exact pure encoding boundaries and no truncation. These
measurements establish representative fit, not hard inspector budgets or a bound
on every valid journal. Independent human QA must accept the measured v1 limits
before any subsequent publication decision.

Engineering recommendation: **CONDITIONAL GO for independent human QA and then
separately authorised PR preparation**, contingent on resource-limit acceptance.
No protected component or approved contract changed. The only implementation
corrections beyond routine typing/style were the tested canonical/physical-path
alias checks needed to satisfy the approved source-root separation guarantee.
The trusted-caller exclusions/custody, local cooperative filesystem assumptions,
non-atomic observations, unestablished historical completeness, unauthenticated
signature/provider/source/human claims and false live authority remain explicit.
No commit, push, PR, merge, non-test evidence publication or later-slice work is
authorised or performed. Stop for independent human review.

Fresh post-documentation final preservation command (`--basetemp=<qa>/
m5-preservation-final tests/test_canary_envelope_v3.py::TestCompatibility`):
**3 passed, 0 skipped**. All **221 protected Git blob/executable-mode identities**,
the complete new/ignored-file scope, historical fingerprints/lock, unchanged
index and new-file whitespace checks pass. `git diff --check` and cached diff
against the exact approved parent pass. Exactly the three authorised regular
nonexecutable additions remain untracked, with HEAD at the approved parent.

### Implemented public API and persisted artifacts

```python
assemble_envelope(*, payload: bytes, signature: bytes,
                  expected_proposal: ProposedCanary, store: AuthorityStoreBinding,
                  registry: RegistryBinding, run_id: str) -> EvidenceEnvelope
serialize_envelope(envelope: EvidenceEnvelope) -> bytes
parse_envelope(raw: bytes) -> EvidenceEnvelope
envelope_commitment_sha256(envelope: EvidenceEnvelope) -> str
verify_envelope(raw: bytes, *, expected: ExpectedEnvelopeReference) -> EnvelopeVerification
verify_against_sources(raw: bytes, *, expected: ExpectedEnvelopeReference,
                       payload: bytes, signature: bytes,
                       expected_proposal: ProposedCanary,
                       store: AuthorityStoreBinding,
                       registry: RegistryBinding) -> EnvelopeVerification
read_envelope(*, publication_root: TrustedPublicationRoot, publication_id: str,
              expected: ExpectedEnvelopeReference) -> EnvelopeVerification
publish_envelope(envelope: EvidenceEnvelope, *, publication_root: TrustedPublicationRoot,
                 publication_id: str, store: AuthorityStoreBinding,
                 registry: RegistryBinding) -> PublicationReceipt
```

Persisted successful layout is only `<trusted root>/<publication_id>/envelope.json`
(0700 directory, 0600 single-link file). Pending/partial layouts remain preserved
after failure and are not accepted by the reader. No receipt/reference sidecar is
created. The receipt is an in-memory handoff result; caller review and independent
retention are outside this module. Only publication writes; read/verify/assembly
are filesystem-read-only and call no signer, consumption or execution API.

Public error taxonomy: invalid_input, invalid_envelope, noncanonical_envelope,
unsupported_version, invalid_reference, reference_mismatch, binding_mismatch,
resource_limit; authority_absent/conflict/corrupt/unavailable/pending;
journal_corrupt/pending/unavailable (busy included); source_changed/source_mismatch,
inspection_interrupted; invalid_publication_root, unsafe_destination,
destination_exists, publication_failed, publication_outcome_unknown,
artifact_unavailable. Codes contain no external detail. No score/status converts
an infrastructure failure into quality zero. Source fields are recorded claims;
completed journal replay never establishes successful producer return or human
review. Digest equality never authenticates either approval signatures or providers.

## Stop gates and final handoff

Stop for independent QA if any protected file must change, resource limit must
rise, approved contract must change, or required guarantee cannot be established.
Keep this document current after every milestone. After M5 report APIs/schema,
files, trust limits, measurements, all actual tests/skips/static checks, all 221
protected bytes/modes, failures/corrections and GO/CONDITIONAL GO/NO-GO for QA/PR
preparation. Do not commit/push/open PR/merge/publish non-test evidence or proceed
to Slice 6d. Final resource acceptance and any publication require separate approval.

## Final independent QA correction: permanent compatibility

The final independent review accepted the implemented architecture and measured
v1 ceilings, with one required compatibility correction before PR preparation.
Only this plan and `tests/test_canary_envelope_v3.py` may change. Production SHA-256
remains `a7388a706b5bb4238504037a88681f6c9ade650115db82c724b24435c5241317`.
All 221 baseline files remain protected; no commit, push, PR or later-slice work
is authorised. The prior conditional resource recommendation is superseded by
the review's acceptance of those ceilings for this stage.

The removed permanent test
`test_complete_protected_inventory_new_scope_modes_and_whitespace` was a
pre-commit publication check: its HEAD/tree/index and exact file inventory
requirements would fail after committing these three additions, after a future
merge or without the historical Git object in shallow CI. Its complete checks
are retained in the independent gate below, outside pytest. The fixed `uv.lock`
identity also moves to that gate: it checks preservation for this slice, rather
than prohibiting future authorised dependency updates. The permanent test is
renamed `test_historical_definition_and_application_contracts_remain_exact` and
retains every historical roster, v2.1, definition, acceptance, execution and
application revision assertion. The import/assembly/verification/read audit test
is unchanged, including its execution, authentication, filesystem, network and
source-byte protections. All other security and behavioral tests are unchanged.
The new suite therefore contains 220 permanent tests rather than 221; no test
is skipped, conditionally bypassed or weakened to mask a Git-state failure.

Fresh correction evidence root (`<correction-qa>`):
`/private/tmp/canary-slice6c-compat-qa-qn15lxgu`. Before-change copies and identities
are retained there. Existing M0–M5 logs remain in their original QA root. The
results above describe earlier runs on the pre-correction tests, and do not
establish fresh acceptance of this correction. No post-commit pytest run is
claimed: committing is explicitly prohibited. Post-commit/merge compatibility
will be assessed by inspection for Git-state dependencies and fresh ordinary
pytest execution on the corrected tests, with its limits recorded below.

### Independent complete pre-publication preservation gate

This one-time procedure intentionally requires the exact approved pre-commit
HEAD/tree, historical baseline objects and unchanged baseline-only index. It is
not an ongoing CI requirement. Re-running it after staging/committing would
require a separately reviewed publication-state procedure; do not weaken its
pre-commit assertions or reintroduce them into pytest. It reads the entire Git
baseline and actual checkout, including hidden, ignored and generated paths,
excluding only root Git administration. Every baseline file is compared directly
with its Git blob bytes and its recomputed Git object identity and executable
mode; dependency/lock/dataset/definition/evidence preservation follows from this
complete 221-file comparison. Only the exact three additions and their necessary
parent directories are permitted. It independently checks the index and status,
regular nonexecutable new files, key/signature material, whitespace and the
frozen production SHA-256. It fails closed on missing baseline objects.

Save the following exact Python procedure **outside** the checkout as
`<correction-qa>/preservation_gate.py`. Run without `-O`, after all checks and plan
updates, using the existing interpreter; no repository or Git state is written:

```sh
env -i PATH=/usr/bin:/bin LC_ALL=C LANG=C PYTHONDONTWRITEBYTECODE=1 \
  /private/tmp/ai-test-harness-canary-runtime-v3-slice2/.venv/bin/python -B \
  /private/tmp/canary-slice6c-compat-qa-qn15lxgu/preservation_gate.py \
  /private/tmp/ai-test-harness-canary-runtime-v3-slice6c \
  /private/tmp/canary-slice6c-compat-qa-qn15lxgu/preservation-final.json
```

```python
"""One-time pre-commit Slice 6c preservation gate; never a pytest test."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
report = Path(sys.argv[2]).resolve()
if report.is_relative_to(root):
    raise RuntimeError("report must remain outside the implementation checkout")
base = "2cbeea571d2b37968c30e9f4e2f98dca4ac20e1e"
tree = "9ce8b22bb7d7594b4fe98190ac983bcebd1c03ab"
environment = {"PATH": os.defpath, "GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C"}


def require(condition, label):
    if not condition:
        raise RuntimeError(label)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=root, env=environment)


def identity(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode), str(path) + ": not regular")
    raw = path.read_bytes()
    return raw, {
        "mode": "100755" if info.st_mode & 0o111 else "100644",
        "blob": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


# Intentionally pre-commit only. Historical objects are required here, never by pytest.
require(git("rev-parse", "HEAD").decode().strip() == base, "unexpected pre-commit HEAD")
require(git("rev-parse", "HEAD^{tree}").decode().strip() == tree, "unexpected HEAD tree")
require(git("rev-parse", base + "^{tree}").decode().strip() == tree, "baseline tree")
protected = {}
for entry in git("ls-tree", "-rz", base).split(b"\0"):
    if not entry:
        continue
    metadata, encoded_name = entry.split(b"\t", 1)
    mode, kind, blob = metadata.decode().split()
    name = os.fsdecode(encoded_name)
    require(kind == "blob" and mode in {"100644", "100755"}, name + ": baseline kind")
    raw, observed = identity(root / name)
    require(observed["mode"] == mode and observed["blob"] == blob, name + ": mode/blob changed")
    require(raw == git("cat-file", "blob", blob), name + ": bytes changed")
    protected[name] = observed
require(len(protected) == 221, "baseline count")

# Exact index inventory and stage-zero modes/blob IDs, as well as Git's cached diff.
index = {}
for entry in git("ls-files", "--stage", "-z").split(b"\0"):
    if not entry:
        continue
    metadata, encoded_name = entry.split(b"\t", 1)
    mode, blob, stage = metadata.decode().split()
    name = os.fsdecode(encoded_name)
    require(stage == "0" and name not in index, "unexpected index stage")
    index[name] = {"mode": mode, "blob": blob}
require(index == {name: {k: v[k] for k in ("mode", "blob")} for name, v in protected.items()}, "index changed")
git("diff", "--cached", "--exit-code", base)
git("diff", "--exit-code", base)

added = {
    "src/harness/canary/envelope_v3.py",
    "tests/test_canary_envelope_v3.py",
    "docs/plans/canary-runtime-v3-slice6c.md",
}
require(not added.intersection(protected), "addition already in baseline")
allowed = set(protected) | added
allowed_directories = {str(parent) for name in allowed for parent in Path(name).parents}
observed_files = set()
for current, directories, files in os.walk(root, followlinks=False):
    if Path(current) == root:
        # Only Git administration is excluded; ignored and hidden files are inspected.
        directories[:] = [name for name in directories if name != ".git"]
        files = [name for name in files if name != ".git"]
    for name in directories:
        path = Path(current) / name
        require(not path.is_symlink(), str(path) + ": symlink directory")
        require(str(path.relative_to(root)) in allowed_directories, str(path) + ": unexpected directory")
    for name in files:
        observed_files.add(str((Path(current) / name).relative_to(root)))
require(observed_files == allowed, "unexpected/missing files: " + repr(observed_files ^ allowed))
status = git("status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignored")
require(set(status.split(b"\0")) - {b""} == {b"?? " + os.fsencode(name) for name in added}, "unexpected status (including ignored/staged)")

new_files = {}
for name in sorted(added):
    path = root / name
    raw, observed = identity(path)
    require(observed["mode"] == "100644", name + ": executable")
    require(path.lstat().st_nlink == 1, name + ": hard link")
    require(raw.endswith(b"\n") and not raw.endswith(b"\n\n"), name + ": terminal newline")
    require(b"\r" not in raw, name + ": CR")
    require(all(line.rstrip(b" \t") == line for line in raw.splitlines()), name + ": trailing whitespace")
    for header in (
        b"-----BEGIN " + b"OPENSSH PRIVATE KEY-----",
        b"-----BEGIN SSH " + b"SIGNATURE-----",
    ):
        require(header not in raw, name + ": prohibited key/signature header")
    require(not re.search(rb"-----BEGIN (?:[A-Z0-9]+ )*(?:PRIVATE KEY|PUBLIC KEY|SIGNATURE)-----", raw), name + ": key/signature material")
    require(not re.search(rb"(?m)(?:^|\s)(?:ssh-(?:rsa|ed25519|dss)|ecdsa-sha2-[^\s]+)\s+[A-Za-z0-9+/]{40,}={0,3}(?:\s|$)", raw), name + ": public key material")
    new_files[name] = observed
require(new_files["src/harness/canary/envelope_v3.py"]["sha256"] == "a7388a706b5bb4238504037a88681f6c9ade650115db82c724b24435c5241317", "production changed")
require(protected["uv.lock"]["sha256"] == "a8a1997cb57cf88bad6d8b00e38efa0b62b77c2ad0057c667ab52933585b1dba", "lock changed")
git("diff", "--check")
git("diff", "--cached", "--check", base)
result = {"result": "PASS", "baseline": base, "tree": tree, "protected": protected, "new_files": new_files,
          "gate_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"result": "PASS", "protected_files": len(protected), "additions": new_files}, indent=2))
```

The script and JSON reports are external QA artifacts, not a fourth tracked file.
File SHA-256s in the report identify source files; they do not redefine runtime
envelope commitments or establish authentication/custody. The plan's own final
hash is recorded externally to avoid a self-referential hash in this document.

### Fresh correction verification record

The exact test-file correction relative to the retained before-change copy is:
old lines 1992–2075 (the one-time inventory method and next method declaration)
become new lines 1992–1994 (two scope comments and the renamed declaration);
old line 2078 (unused repository-root local) and old lines 2102–2105 (fixed lock
hash assertion) are deleted. No other test AST changes exist. The file prefix
before `TestCompatibility` is byte-identical; the remaining side-effect audit
method is unchanged. Evidence: `<correction-qa>/test-correction.diff` and
`compatibility-review.json`. This plan appends the correction record after its
original 550 lines; prior results/failures remain distinguishable history.

Fresh runs use the unchanged interpreter and stripped environment above. Exact
argv/environment/cwd are recorded in `<correction-qa>/<label>-command.json`,
stdout/stderr in `<label>.log`, return code and wall time in `<label>-result.json`.
All pytest runs use `-q --tb=short -rs -p no:cacheprovider` and distinct private
`--basetemp` roots. Fresh completed results:

| Label | Command after `python -B` | Fresh outcome |
| --- | --- | --- |
| correction-core | `-m pytest ... tests/test_canary_envelope_v3.py` | 220 passed, 0 skipped, 59.22s |
| correction-sources | `-m pytest ... tests/test_canary_approval_v3.py tests/test_canary_authority_v3.py tests/test_canary_journal_v3.py tests/test_canary_journal_v3_faults.py tests/test_canary_runtime_v3.py` | 635 passed, 1 optional skip, 178.28s |
| correction-full | `-m pytest ... --ignore=tests/test_canary_controller.py` | 4,119 passed, 6 existing optional skips, 630.50s |
| correction-preservation-posttest | external `preservation_gate.py` procedure above | PASS, 221 exact baseline files, exactly 3 additions; no unexpected index/ignored/generated paths |
| correction-ruff | `-m ruff check --no-cache src tests` | PASS |
| correction-mypy | `-m mypy --cache-dir=<correction-qa>/mypy src` | PASS, 64 source files |
| correction-format | `-m ruff format --check --no-cache src/harness/canary/envelope_v3.py tests/test_canary_envelope_v3.py` | PASS, both already formatted |

The initial independent gate passed all 221 baseline bytes/blob/mode checks,
exact three-file scope, complete directory/ignored-file inventory, baseline-only
index, key/signature/whitespace checks and frozen production identity. Its
`preservation-initial.json` also agrees with the independently retained M0
`baseline-inventory.json` on every path/blob/mode. It will be rerun after the
final documentation update so the final report identifies the final plan bytes.
The stripped Git environment emits the existing Darwin temporary-directory
lookup warning; it does not change the exit status or checked identities.

Compatibility reasoning: the corrected permanent tests never look up the
approved baseline commit/tree, assert an old HEAD or index, or enumerate a fixed
repository inventory. The historical definitions are loaded from current
tracked definition files using `resolve_definition`, and the fixtures use
synthetic receipt identities. A commit or merge that preserves these historical
contracts changes none of these assertions; unrelated approved tracked files or
dependency updates no longer violate a pre-commit inventory or lock hash pin.
No historical Git object is needed by these corrected tests in a shallow
checkout. This is a reasoned compatibility conclusion backed by the recorded
source/AST comparison and fresh ordinary pytest runs. No post-commit,
post-merge or shallow-clone test run has occurred or is claimed.

The unchanged-source run skipped only
`tests/test_canary_runtime_v3.py:452`, the existing optional complete source
check requiring a pinned CPython 3.13 worker. It is not an executed source
integration success. The core envelope suite has no skips.

The full offline run excludes only the already approved historical listening
server module `tests/test_canary_controller.py`. Its exact six skip reasons:

- `test_canary_controller_v3_application.py:26`: explicitly enabled pinned app suite.
- `test_canary_instrumentation_v3_sdk.py:22`: optional pinned OpenAI 3.3.1 runtime.
- `test_canary_sdk.py:9`: optional OpenAI package is absent.
- `test_canary_selection_state.py:5`: optional pinned application runtime.
- `test_canary_state.py:13`: optional pinned application runtime.
- `test_canary_runtime_v3.py:452`: optional complete CPython 3.13 source worker.

No correction check failed or was interrupted. Earlier negative/interrupted M5
runs and their causes remain explicitly recorded above and in the original QA
root; they are not fresh correction failures. The earlier passing counts of
221 core / 4,120 full include the one-time inventory test and are superseded for
this correction by 220 / 4,119, respectively. They were pre-commit successes,
not post-commit compatibility evidence. No hypothetical post-commit failure or
successful post-commit run is represented as an observed result.

The independent post-test gate passed (`preservation-posttest.json`, command/log/
result under `correction-preservation-posttest`). It verified exact baseline
bytes, recomputed Git blob IDs and executable modes for all 221 files; baseline
HEAD/tree and stage-zero index; exactly the three authorised additions; no other
hidden/ignored/generated files or directories; regular nonexecutable new files;
no prohibited key/signature material; final newlines/trailing whitespace and
both ordinary/cached Git whitespace checks. This includes all dependencies,
locks, datasets, definitions and historical evidence without a selective or
reduced inventory. No protected file changed. No production or historical
fingerprint implementation/contract changed.

The gate is rerun after saving this final record as `correction-preservation-final`
and writes `preservation-final.json`, which is the authoritative external
manifest for the final document bytes. The exact documented Python procedure
must match the external script. Production and the test file remain identical
to the versions used by the completed fresh test/static runs:

- Production SHA-256: `a7388a706b5bb4238504037a88681f6c9ade650115db82c724b24435c5241317`.
- Corrected test SHA-256: `cd8217d689d13f912b20e5b7fba1ee3690f55b80651e8b741770788be39ad6e7`.
- Final plan SHA-256, all file byte counts/modes/blob IDs and the gate's own
  identity: retained externally in `preservation-final.json`.

**GO for independent human QA and separately authorised PR preparation.**
The required permanent compatibility correction is complete; there are no new
engineering blockers. Compatibility after committing/merging is justified by
inspection, not a claimed executed run. Optional app/SDK/CPython 3.13 integrations
remain unexecuted, and the accepted synthetic-only, trusted local filesystem,
caller-root exclusion and independent-reference custody assumptions remain.
No production behavior or assurance claim is expanded. This recommendation is
not publication approval. No task commit, push, PR, merge, credentials access,
live service or Slice 6d work is performed. Stop and await separate human
publication authorisation.
