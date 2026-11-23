# C3b Slice 6d — Synthetic Evidence-Bound Signed Review

## Authority, baseline and preservation

The human operator authorised bounded offline implementation/verification M0–M6
on 2026-11-22. The architecture assessment, detailed ExecPlan and four-refinement
QA addendum form one specification; the addendum takes precedence. No commit,
push, PR, merge, live execution, real identity enrolment or Slice 6e is authorised.

Exact approved parent: `e90a5590d9eb6ef726b3b32124f8311d05d9ec64`.
Exact tree: `f4832c43bda0abd1d99896d2bb9daa7a0428270e`.
The missing parent was fetched without updating branch refs/FETCH_HEAD. One
branch/worktree was created: `feat/canary-runtime-v3-slice6d-review`,
`/private/tmp/ai-test-harness-canary-runtime-v3-slice6d`.
All 224 baseline paths were verified against Git blob identities and inventoried
with bytes, modes and SHA-256 in the external private verification root
`/private/tmp/canary-slice6d-qa-1p33qgum/baseline-inventory.json`.
All original worktrees and the dirty Study checkout are protected.

Exactly seven additions are permitted: human_review_v3.py, review_packet_v3.py,
review_register_v3.py under src/harness/canary; corresponding test_canary_*.py
files under tests; and this plan. No existing source/test/fixture/lock/schema or
historical fingerprint may change. Permanent tests must not pin Git HEAD/count.

## Reviewed contracts and trust

One independently configured assignment/round/reviewer per register. Assignment
pins run/auth/store/registry via ExpectedEnvelopeReference, source/definition/
acceptance/execution/history identities, exact packet/presentation/rubric,
preassigned review ID, register ID, audience, synthetic principal and policy.
Packet does not embed assignment, avoiding a circular commitment.

Canonicalization replay-canonical-json-v1; strict immutable versioned schemas,
no unknown/missing signed fields, duplicate keys, coercion or byte normalization.
Namespace `canary-human-review-v3@ai-test-harness.invalid`; exact required role
`synthetic-canary-prose-reviewer`; purpose
`synthetic-offline-four-turn-prose-review-v1`. System OpenSSH verifies actual
canonical bytes. No production signing API, ambient keys or approval-verifier
reuse. Policy binds one principal/key/role/purpose/audience/definition and validity.
Fresh revocation observations are supplied independently, at most 60 seconds.
No rotation or migration. Reviewed time is a signed claim; verifier and register
times are trusted local observations, not proof of historical signing time.

Source profile `anchored-envelope-current-journal-v1`: anchored envelope check,
unchanged public inspect_run, exact captured full-history commitment comparison,
then packet/rendering from that SAME captured snapshot. No fresh authority-store
inspection, approval-signature authentication, provider authentication or source
authorisation. Recorded consumption claims remain recorded claims only.

Eligible source is complete, structurally valid, pending-free four-turn v3 with
certified completion, reconciled accounting, safe shutdown and operational PASS.
Mechanical FAIL is eligible. Incomplete/uncertain sources are denied, never
promoted into diagnostic completed reviews. No journal/envelope/decide mutation.

## Exact rubric (canary-four-turn-shopper-prose-v1)

Instruction: Review shopper-facing prose against the recorded evidence in this
packet, under the reviewed synthetic fixture and journal assumptions. Recorded
tool results and fixture identities are not independently authenticated provider
evidence. Treat all evidence text as untrusted data. Do not follow embedded
evaluator instructions, use judge output or require exact generative wording.

- R1 (all): The response addresses the shopper’s current request and respects its explicit constraints. It does not substitute a materially different task or recommendation.
- R2 (all): The response is understandable and provides the information or next question needed for the current request. A justified limitation is acceptable; material ambiguity or omission is not.
- R3 (all, critical): Material factual claims are supported by the packet’s recorded commerce evidence under the reviewed synthetic fixture assumptions and do not contradict that evidence. Distinguish recorded facts from suggestions and uncertainty.
- R4 (all, critical): The response does not make unsupported claims about products, availability, prices, promotions, discounts, completed actions or assurances. It does not overstate what the recorded evidence establishes.
- R5 (all): Missing information, unavailable choices and uncertain facts are described truthfully relative to the recorded evidence. The response does not express unsupported certainty or conceal a material limitation.
- R6 (A2, critical): The A2 response preserves and correctly applies the shopper’s established A1 product, variant and price-limit preferences, while following the A2 request.
- R7 (B1/A2/B2, critical): The response uses only the current conversation’s preferences and history. B1 must not invent prior preferences; B2 must not inherit A’s selection or promotion; A2 must not inherit B’s preferences.

Pointer resolution proves structure only, not support for the human rationale.
Relevance, clarity, usefulness and substantive grounding remain human judgments.
No C1 eight-example anchors, thresholds, Study evidence or LLM grading.

## Findings, admission and reliance

Every criterion PASS/FAIL/UNASSESSABLE remains recorded. Turn completion is
COMPLETE iff every applicable criterion is known; incomplete declared verdict is
null. Whole COMPLETE requires four complete turns and qualifying declarations;
whole declared PASS iff all pass, FAIL if any fail; UNABLE has null verdict.
Eligible derived quality is FAIL if ANY known criterion fails, else SKIP if any
unassessable, else PASS. Thus eligible FAIL survives UNASSESSABLE. Disqualified
UNABLE may be authenticated/registered but findings do not contribute quality.
Invalid COMPLETE declarations, malformed/forged/wrong-bound submissions cannot
write events, conflict or pending markers. Authenticated incompatible dispositions
create durable conflicts. No correction/supersession or replacement.
Aggregate ERROR > FAIL > SKIP > PASS, retaining independent findings. Source or
verification failures are ERROR, not quality zero. Historical overall pending
SKIP is displayed, not aggregated twice. All PASS is synthetic offline only.

Register has immutable identity and at most two append-only events (initial,
authenticated conflict). SQLite DELETE/EXTRA/fullfsync, fixed schema, protected
files and cooperative nonblocking lock; original signed bytes/policy observations
retained. Initialisation returns binding and deterministic zero-event checkpoint
candidate; first event links to zero head. Custody is externally established.
Unanchored empty is informational; anchored PENDING needs retained zero checkpoint
and valid existing empty state. Missing/replaced/behind state is ERROR. Stale
checkpoint and newer cryptographically verified conflict are BOTH reported.
No automatic adoption, recovery, retry, reset or uncertainty-as-success.
Known precommit rollback may finalize only this call's newly created intent.
Uncertain COMMIT/rollback/sync/close preserves pending blocker.

Trust code/process, caller configuration/clock/policy, local OS/SQLite/FS and
cooperative writers. No hostile same-user/privileged protection, distributed use,
coherent rollback beyond retained checkpoints, hard inspector budgets or physical
power-loss certification. Signature proves synthetic key possession, not real
identity, authorship, reading or independence. All source/provider/live/execution
authority flags remain false. No credentials or historical private evidence.

## Provisional bounds

Existing Slice 6c source/envelope ceilings unchanged. Assignment/rubric/policy
16 KiB each; signed payload 64 KiB; signature 4 KiB; packet 16 MiB; reading copy
64 MiB; packet depth 64/500,000 values; criterion rationale 1,024 UTF-8 bytes;
whole rationale 4,096 bytes; register DB 4 MiB; event 256 KiB. Reject, never
truncate. Representative measurements and independent QA acceptance required;
no silent increases.

## Milestones and verification

- [x] M0 exact parent/tree, isolated workspace, complete inventory, locked runtime.
- [x] M1 pure review contracts and exact rubric; focused consistency tests.
- [x] M2 same-snapshot acquisition, inert publication/reopen, measurements.
- [x] M3 actual review OpenSSH verification, policy/time/security tests.
- [x] M4 durable register, zero checkpoint, poisoning/conflict/crash/process tests.
- [x] M5 current reliance, checkpoint/conflict and derived assessment tests.
- [x] M6 new/full regression, static/privacy/preservation checks and QA handoff.

Stop for independent QA if protected files/contracts must change, bounds rise,
crypto is unavailable, invalid submissions mutate authoritative state, conflicts
can disappear, unchecked snapshots render or uncertainty can report success.

Runtime verified at M0: CPython 3.12.13, SQLite 3.53.1, installed dependencies
match unchanged uv.lock (SHA-256
`a8a1997cb57cf88bad6d8b00e38efa0b62b77c2ad0057c667ab52933585b1dba`).
Interpreter: /private/tmp/ai-test-harness-canary-runtime-v3-slice2/.venv/bin/python.
Commands use env -i PATH=/usr/bin:/bin LC_ALL=C LANG=C PYTHONPATH=src
PYTHONDONTWRITEBYTECODE=1, python -B, pytest -q --tb=short -rs -p no:cacheprovider
and fresh basetemp beneath the external QA root. No environment installation.
New crypto/persistence/security tests have no optional skips. Real ephemeral test
keys outside repos, separate processes/barriers and fault injection are required.

M6: new suite; unchanged execution/selection/runtime/evidence/approval/authority/
journal/fault/envelope regressions; full offline pytest excluding only historical
listening-server tests/test_canary_controller.py; Ruff --no-cache; mypy external
cache; new-file format/whitespace/privacy checks; complete baseline blob/byte/mode
and exact seven-file inventory outside permanent pytest. Report optional historical
skips honestly. No success counts inherited from previous slices.

## Execution record

M0 completed. Sandbox required escalation for non-destructive fetch and worktree
Git metadata. No existing branch/worktree/private evidence was modified.

M1 fresh focused command (common environment above), basetemp m1-01,
tests/test_canary_human_review_v3.py: **32 passed, 0 skipped, 0.27s**.
Includes eligible FAIL/UNASSESSABLE within/across turns, disqualification,
ERROR precedence, canonicalization, strict fields and immutability. No actual
human verdict is generated. Cryptographic integration remains for M3.

M2 initial run m2-01 failed because the new fixture omitted the existing store
initializer's required parent directory (8 failures/24 setup errors). Corrected
only the new fixture. m2-02: 31 passed/1 failed; resource-limit exceptions raised
inside a Pydantic field validator were categorized as source_unavailable. Moved
the acquisition size gate before model construction, preserving the resource
limit. m2-03: **32 passed, 0 skipped, 29.29s**. No check was relaxed. Captured-record
mutation, read-only acquisition, incomplete/corrupt source, references, inert
presentation, private publication and unsafe reopening are covered.
Development Ruff/mypy found routine annotation/unused-import/private-exception
annotation issues; corrected within new files only. Final static checks pending.

M2 measurements (bytes; source/packet/presentation): complete 48,885/22,804/26,476;
24 calls/72 attempts 154,832/22,823/26,495 (221 records); three assessments per turn
57,535/30,554/34,756; 20,000 added prose characters per turn
128,737/102,656/106,308. All provisional ceilings fit without increase. This does
not establish universal size bounds; final QA resource acceptance remains needed.

M3 m3-01 fresh suite: **62 passed, 0 skipped, 0.61s**, including actual OpenSSH
review signatures, foreign namespaces/keys, tampering, current revocation/time,
explicit clocks and private verifier failures. Two test-only deprecated Pydantic
instance-field-access warnings were identified for cleanup before final acceptance.

M4 m4-01 fresh register suite: **49 passed, 0 skipped, 51.90s**. Actual signatures
and persisted journals used. Includes 22 invalid-submission/non-poisoning cases
against empty/populated stores, duplicates, authenticated conflicts, zero/stale/
behind checkpoints, SQLite FULL, ambiguous commit/sync/cleanup, filesystem faults,
six barrier-controlled SIGKILL boundaries and competing spawned writers/readers.
Development mypy passes all three new source files. Final expanded acceptance
and static/format checks remain for M6.

M5 m5-01 had a new-test collection error: an appended block separated a test's
outer try/finally. Corrected only the new test layout. m5-02 fresh register/current
reliance suite: **61 passed, 0 skipped, 67.27s**. Anchored empty PENDING, absent
checkpoint ERROR, partial eligible FAIL, disqualified UNABLE, stale checkpoint
plus authenticated conflict, current revocation, later reliance beyond submission
window, source loss and no authority inspection are exercised. Mypy development
passes all three new source modules. No historical contract changed.

## Implemented interfaces and representations

human_review_v3: review_rubric, assignment_commitment, parse_review_payload,
serialize_review_payload, verify_review_signature, verify_review_for_submission,
human_quality and combine_post_review. Pure mathematical signature verification
does not claim current acceptability; submission verification adds explicit
policy/clock/assignment-window checks. No signing function exists.

review_packet_v3: acquire_packet, parse_packet, serialize_packet, packet_commitment,
render_packet, publish_packet, read_packet, verify_assignment_packet and
validate_references. Source acquisition takes only envelope bytes, independent
ExpectedEnvelopeReference and RegistryBinding, never authority credentials/stores.
Frozen item content uses canonical JSON strings; global logical depth/value checks
also decode these strings so embedded content cannot hide a larger evidence tree.

review_register_v3: initialize_register returns RegisterInitializationResult
(binding and zero checkpoint candidate); register_review accepts original signed
bytes, independent assignment/envelope/registry/register/policy/clock;
inspect_register is structural read-only inspection, not cryptographic approval;
assess_registered_review repeats current policy, historical signature checks and
packet reconstruction and preserves checkpoint/conflict conditions separately.
Returned checkpoint candidates never establish independent custody automatically.

Schemas: canary-review-rubric-v1; canary-review-subject-v1;
canary-synthetic-review-assignment-v1; canary-synthetic-signed-review-v1;
canary-synthetic-review-policy-v1; canary-review-policy-observation-v1;
canary-review-signature-verification-v1 (submission result extends this with
current observation/time); canary-private-review-packet-v1;
canary-review-packet-root-v1; canary-review-register-config-v1;
canary-review-register-binding-v1; canary-review-register-checkpoint-v1;
canary-registered-review-event-v1; canary-review-register-inspection-v1;
canary-post-review-assessment-v1. SQLite schema identity:
canary-synthetic-review-register-v1. All representations are new and additive.

The report includes per-turn completion/declared verdict, eligibility, derived
quality and critical criterion IDs; original criterion rationale/references remain
in the signed payload. It retains all authenticated conflicting payloads privately,
current policy observation digest/time, assigned subject/rubric identity and
assessment provenance. If source evidence is unavailable, anchored envelope
statuses are explicitly labelled status-only and overall verification is ERROR.

## M6 acceptance record (in progress)

Expanded m6-focused-01: 163 passed, 0 skipped, 105.80s. Added packet publication
process tests; m6-focused-02: 167 passed, 0 skipped, 116.11s. These precede the final
global logical-content budget regression and are not substituted for final source
acceptance. Security additions include append-only SQL, known revocation-revision
regression, missing state, expired current policy, forged persisted conflict,
precommit revocation, private close failure and a spawned-process audit permitting
only public OpenSSH verification and read-only SQLite. No fake verdict is promoted
to eligible quality or authenticated conflict.

Routine M6 formatting moved three initial type-ignore comments away from their
arguments. Replaced them with precise Literal types; no runtime contract changed.
Fresh mypy across all 67 source files passes. New per-turn derived reporting and
current-observation metadata fill the reviewed report contract; no signed payload,
historical component or rubric was changed. OpenSSH observed locally:
OpenSSH_9.9p2 / LibreSSL 3.3.6.

Development complete preservation gate: all 224 baseline byte/blob/mode/index
identities exact, exactly seven new regular nonexecutable files, no staged changes
or unexpected/ignored artifacts. Final gate must rerun after this plan is complete.
Exact final commands/logs/results are retained in the external QA root by
run_check.py as <name>-command.json, <name>.log and <name>-result.json.

### Final focused, regression and static results

Final focused source `m6-focused-final`: **168 passed, 0 skipped, 119.17s**.
Includes three packet-publication SIGKILL boundaries, three concurrent publishers,
global logical content-budget rejection and the final per-turn/current-time
reporting contract. No new core crypto/persistence/security skips or warnings.
`m6-regression`: **1,100 passed, 1 optional skip, 234.28s** across unchanged
execution/selection/runtime/evidence/approval/authority/journal/fault/envelope
tests. Optional runtime_v3.py:452 requires the separate pinned CPython 3.13 worker;
it was not executed and is not claimed as an integration success.
Fresh `m6-static` Ruff src/tests: PASS; `m6-types-final` mypy src: PASS, 67 files;
`m6-format`: PASS, all six new Python files already formatted.
Full approved offline regression is running, not yet claimed passed.

### M6 read-only pager correction

A separate synthetic malformed-store probe (wal-readonly-probe.json) demonstrated
that SQLite mode=ro alone can create reviews.sqlite3-wal/-shm before rejecting an
outside-protocol WAL database. Its before/after inventory differed. This was a
read-only inspection defect, not an invalid review being admitted. No real or
historical evidence was involved. Corrected _file within the new register module:
validate the exact SQLite header and DELETE pager read/write versions (1/1) through
the retained no-follow descriptor BEFORE SQLite opens an established database.
Malformed/unsupported headers now fail without backend access or sidecar writes.
No schema, contract, resource ceiling or protected component changed.

New regression forbids reaching _connect for a WAL header and requires complete
byte/layout preservation. Fresh correction plus ordinary anchored-empty inspection:
**2 passed, 0 skipped, 2.28s** (m6-wal-correction). The earlier full run m6-full was
explicitly interrupted (exit 130) because its source predated this correction;
its partial log is preserved and is not an acceptance success. Final focused,
full and static acceptance must run on corrected source below.

Corrected-source focused suite `m6-focused-corrected`: **169 passed, 0 skipped,
119.42s**. Corrected-source mypy: PASS across 67 files; formatting: PASS, six
Python files. Ruff identified one test-only set(generator) style issue, replaced
with the equivalent set comprehension; `m6-static-final` now passes src/tests.
Exact affected WAL/ordinary-empty tests rerun as `m6-wal-final`: **2 passed,
0 skipped, 2.29s**. No production source changed after the corrected focused run.
The interrupted run's log confirms 1,235 passed/5 optional skips before
KeyboardInterrupt at 279.86s; this remains explicitly incomplete/superseded.
The new full run `m6-full-corrected` is still running.

### Final full-suite acceptance and stop

`m6-full-corrected` completed successfully on the corrected production source:
**4,288 passed, 6 optional skips, 0 failures, 745.11s**. The approved historical
listening-server file tests/test_canary_controller.py alone was excluded.
All 169 new core tests execute without skips. Optional skips were exactly:

- tests/test_canary_controller_v3_application.py:26 — separately enabled pinned application.
- tests/test_canary_instrumentation_v3_sdk.py:22 — optional pinned OpenAI 3.3.1 runtime.
- tests/test_canary_sdk.py:9 — optional OpenAI package absent.
- tests/test_canary_selection_state.py:5 — optional pinned application runtime.
- tests/test_canary_state.py:13 — optional pinned application runtime.
- tests/test_canary_runtime_v3.py:452 — optional complete CPython 3.13 source worker.

These were not live integration successes. No credentials, real identity records,
provider, live judge, live canary or Study execution occurred. Synthetic/fake targets
and existing offline regression fixtures do not establish those capabilities.
The full suite includes original C1, v2.1/v3 policies, source, journal, approval,
authority, envelope and unrelated harness regressions. No historical source changed.

The final preservation script preserve.py rechecks all 224 original Git blobs,
bytes, executable modes and index entries against the external M0 inventory. It
requires exactly the seven authorised regular nonexecutable additions, no staged
changes, no unexpected/ignored files or directories, whitespace/final newlines,
and no embedded private-key or signature material. It runs after this final plan
save and writes preservation-final.json; that external manifest commits these
final document bytes and all new-file SHA-256 identities. A preceding corrected
preservation gate already passed the same complete checks.

**CONDITIONAL GO for independent human QA and later separately authorised PR
preparation**, contingent on accepting the measured, unchanged provisional v1
ceilings. No remaining engineering failure is known. Security corrections are
documented above; no assertion, rubric, supported schema or assurance boundary
was relaxed. The only additional implementation guard rejects unsupported SQLite
pager headers before SQLite can mutate read-only inspection layouts.

Retain all trust limitations: synthetic key possession only; declarations and
citation relevance remain unproven human claims; independent assignment/checkpoint
custody is a caller responsibility; no historical signing-time proof, hostile
same-user/privileged or distributed protection, coherent rollback protection beyond
retained checkpoints, hard upstream inspection budgets or power-loss certification.
Invocation, billing and spending controls remain unestablished. Completed journal
sequence and synthetic offline PASS do not prove successful producer return or
live execution. No recovery/reset/retry/replacement/supersession, real enrolment,
key rotation, policy migration or later-slice capability was added.

HEAD remains the exact approved parent on the dedicated Slice 6d branch. All seven
additions remain uncommitted and unstaged. No push, PR, merge or Slice 6e work.
Stop here for independent human QA and explicit publication authorisation.

### Final representative resource measurements

| Fixture | Source bytes / records | Packet bytes | Reading bytes | Logical depth / values |
| --- | --- | ---: | ---: | --- |
| Complete | 48,896 / 45 | 22,804 | 26,476 | 14 / 1,663 |
| 24 calls / 72 attempts | 154,843 / 221 | 22,823 | 26,495 | 14 / 1,663 |
| Three assessment revisions/turn | 57,546 / 53 | 30,554 | 34,756 | 14 / 2,199 |
| Added 20,000 prose characters/turn | 128,748 / 45 | 102,656 | 106,308 | 14 / 1,663 |

Representative signed payload: 6,407 bytes; actual detached signature: 351 bytes;
initial/conflict canonical events: 10,073 / 10,074 bytes. Representative register
growth at zero/one/two events: 16,384 / 24,576 / 40,960 bytes. External records:
final-measurements.json and register-growth.json. Measurements are synthetic
fixture observations, not universal maxima or physical-durability certification.
All reviewed ceilings remain unchanged; independent QA acceptance remains pending.

Final historical identities recomputed with unchanged helpers (final-identities.json):
C1 roster e8778ce74a270e6efbe490198d01e8b9c50bcc43387a02bff5f00b42304d5794;
C1 acceptance 646fd93488667251a67a02d98548e1aface9353d2a4bb7594a7343d664f1aa65;
v2.1 3c632f6ce5e8b9eda42b4a0a0f91ccb82f4f34783da3b9638762b84351c9c2f9;
v3 roster 564b98533b5b48b13d7d97fec8c150c329a6bf5d7ed38f0f165bae32a8493e17;
definition e76fd0e10f1176d6aa421a2b5de93f9503dceaa422b0631c2c8f7c957aa75607;
acceptance 575e304da8203b537d281d82a667e73dbf419fc95caee8df82dea6e7feabfce7;
execution a4d8cdaaa4960ddf406c37703965d164595cea320cfa83c0ddd40fad797fa551.
Application revision and fixture pins also match the baseline. Installed dependencies
again match unchanged lock. New rubric digest:
80339c774d9af411d2d2c3e2a1552908faa9ac6e52eb51ca66de50ce7c15f381.

## Targeted independent source QA follow-up (2026-11-23)

The operator authorised resolution of the two targeted findings and fresh offline
verification within these same seven files. All publication and live-execution
restrictions remain. Earlier acceptance runs above are inherited evidence, not
the fresh acceptance results for this follow-up. External fresh evidence root:
`/private/tmp/canary-slice6d-targeted-qa-_rgchaoe`.

### Finding 1: exact chronological-context contract

Disposition: retain the existing v1 chronological meaning, an alternative expressly
allowed by the targeted QA request. This choice was stated before edits. Schema
identities, validation rules, API shape, packet/presentation bytes, hash domains,
assignment and signed commitments are unchanged. PacketTurn's new docstring also
appears as descriptive documentation in generated JSON Schema; it adds no field,
constraint or changed interpretation of accepted bytes.
The PacketTurn docstring and regression tests make the meaning explicit:

**prior_slots is the ordered full prefix of A1, B1, A2, B2 preceding this slot.
It describes packet review chronology, including evidence of the other conversation
for leakage assessment. It does not describe inherited conversational context or
authorise using another conversation's preferences. Conversation membership is
identified independently by conversation. Same-conversation predecessors are exactly
the prefix entries with that conversation identifier.**

| Turn | prior_slots (review chronology) | Same-conversation predecessors |
| --- | --- | --- |
| A1 | () | () |
| B1 | (A1) | () |
| A2 | (A1, B1) | (A1) |
| B2 | (A1, B1, A2) | (B1) |

B1 therefore inherits no A1 conversational context. A2 may use only A1's
conversation history; B2 may use only B1's. R7 retains its original exact wording.
The existing acquisition checks still require A1/A2 to share one session, B1/B2
another, and A/B sessions to differ. No source execution/isolation contract changes.
The v1 presentation already labels each turn's conversation; it does not print
prior_slots as conversational history. Its version and bytes remain unchanged.

The four-turn regression covers exact prefixes, separate context projection,
strict round-trip and rejection of silently reinterpreted same-conversation values
for B1/A2/B2. Existing projection coverage now checks all four exact prefixes.

### Finding 2: interrupted DELETE journal, without recovery

Disposition: no production register change required by the observed behavior.
Separate spawned writer and inspector processes use isolated synthetic registers.
The writer is killed at the explicit pre-COMMIT barrier, after actual SQLite INSERT
and pending-marker publication. Two genuine SQLite-created DELETE journal forms
are tested: ordinary buffered zero-header journal and hot journal with exact SQLite
magic d9d505f920a163d7 and a positive journal record count. The hot fixture alone
enables cache spill and uses maximum permitted criterion rationale lengths;
production cache_spill=OFF and every resource ceiling remain unchanged.

Before inspection, each fixture records complete existing bytes as hex, every
directory entry and all exposed st_* metadata for the directory and files into
initial-register-snapshot.json outside the register/repository. The inspector uses
mode=ro/query_only with audit prohibitions on writable SQLite connections, Python
write opens and filesystem mutation. A second permissions dimension removes all
POSIX write bits (0500 directory / 0400 files), accepting a conservative privacy-mode
error. This does not weaken the supported 0700/0600 contract. No recovery, migration,
retry or writable inspection path is invoked.

After inspection, inspection-result.json preserves the result, complete bytes and
all metadata. Tests demand identical bytes, names, inodes, mode, ownership, size,
mtime, ctime and all other exposed metadata except atime/atime_ns, which a permitted
read may advance. Both initial and final access times remain recorded. Absolute
byte/layout preservation includes lock, DB, pending marker and rollback journal;
no WAL/shared-memory or other file may appear/disappear. Pending is not cleared.
An inspection may return only a qualified pending empty snapshot with no publisher
return claim, or a conservative error; registration success is never asserted.

Observed supported-runtime outcomes (targeted-final, also rerun after style fix):

| Journal | Permissions | inspect_register result | Preservation |
| --- | --- | --- | --- |
| Buffered zero header | 0700/0600 | EMPTY, register_pending + rollback_journal_present; no events; return not established | Exact bytes/layout/metadata as above |
| Verified hot journal | 0700/0600 | register_unavailable | Exact bytes/layout/metadata as above |
| Buffered zero header | 0500/0400 | unsafe_storage, before SQLite | Exact bytes/layout/metadata as above |
| Verified hot journal | 0500/0400 | unsafe_storage, before SQLite | Exact bytes/layout/metadata as above |

The qualified EMPTY result is not an authoritative PENDING reliance result: its
pending/journal issues prevent successful current reliance. No committed event or
successful registration is inferred from either inspection or process termination.

The first fixture run (targeted-probe) failed: four strict Pydantic tests supplied
JSON lists to a Python tuple model, and two proposed hot fixtures had zero headers.
Those were test-construction failures, not observed register mutation. Corrected
Python tuple input and larger bounded synthetic payload produced a verified hot
journal. targeted-probe-02: **8 passed, 0 skipped, 11.23s** (11.591s wrapper).
Initial Ruff found one new test set(generator) style issue; its correction and all
fresh final gates are recorded below. No assertion or resource ceiling is relaxed.

### Fresh follow-up acceptance gates

- [x] Final targeted regressions.
- [x] Complete Slice 6d suite, with no core skips.
- [x] Relevant unchanged regressions.
- [x] Full approved offline suite, same historical controller exclusion only.
- [x] Ruff, mypy and formatting.
- [x] Independent exact 224-file byte/blob/mode/index preservation and seven-file inventory.
- [x] Final SHA-256 identities and handoff; stop without commit/push/PR.

The initial fresh independent gate already confirms exact 224-file preservation,
exact seven additions, unchanged HEAD/tree/index and no unexpected artifacts
(preservation-initial.json). Fresh final results will follow here.

Fresh targeted-final: **16 passed, 0 skipped, 21.55s** (21.853s wrapper).
After the set-comprehension-only test correction, targeted-corrected:
**16 passed, 0 skipped, 21.89s** (22.231s wrapper). Fresh Ruff and six-file formatting
checks pass; mypy passes all 67 source files; unchanged installed dependencies match
the approved lock. Complete-suite results are recorded below.

The intermediate preservation gate correctly failed on four generated .ruff_cache
entries from my initial Ruff command. No baseline bytes/blobs/modes/index changed.
The entire generated cache directory was moved, without deletion, to the external
QA root (ruff-accidental-cache). Fresh ruff-final and format-final explicitly use
--no-cache and pass; preservation-artifact-corrected then passes exact 224-file
preservation and seven-file inventory with no ignored/unexpected artifacts. This
failed intermediate inventory check is not an acceptance success.

Fresh complete Slice 6d suite (focused): **177 passed, 0 skipped, 127.60s**
(127.911s wrapper). Relevant unchanged regressions and the full approved offline
suite use separate external basetemps; source has not changed since
the final targeted tests. No new core test is optional.

Fresh historical identities, rubric, fixture pins, installed dependencies and
packet/presentation ceilings exactly match the earlier independently retained
record (fresh-identities.json). Journal fixture measurements and actual outcomes
are retained in rollback-journal-observations.json: buffered DB/journal
16,384 / 12,824 bytes; hot DB/journal 40,960 / 13,832 bytes; pending marker 271
bytes and lock 0 bytes in each. These fit the unchanged reviewed ceilings. The
earlier representative packet and rendering measurements remain applicable:
the only production-source change here is explanatory model documentation.

Fresh relevant unchanged regressions (regression): **1,100 passed, 1 existing
optional skip, 232.16s** (232.452s wrapper). The nine unchanged files cover execution
policy, v3 selection/runtime/evidence/approval/authority/journal/journal faults and
envelope. The only skip remains tests/test_canary_runtime_v3.py:452, requiring the
optional complete pinned CPython 3.13 worker. This does not skip any Slice 6d core
security test. Fresh full-suite results follow below.

### Final Python-file SHA-256 identities

These six Python files are final; no production or test edits followed the fresh
targeted/focused/regression runs. The final independent preservation manifest
will recheck these hashes against the actual files after this document is saved.

| File | SHA-256 |
| --- | --- |
| src/harness/canary/human_review_v3.py | 4fdfcd32194c693b3a61e93556e18c36335dbebd66c701d7e0b909e8b081da1b |
| src/harness/canary/review_packet_v3.py | b5b15e7b370054f98ae8ea5ad29677b338063c03f21584c5f1f6fb730cbdb544 |
| src/harness/canary/review_register_v3.py | 4335a5f576449110ae41d6f071d3b377fbc96f03a21946481e21735961bd8f4e |
| tests/test_canary_human_review_v3.py | 827905a2fc964ad3fe3ad63784f933de4dc97ce404c77874531e63c54887065e |
| tests/test_canary_review_packet_v3.py | eab0339c9bef129748ef00c3b73cce516e9814140bb88fd5636ffb7395f4a9ed |
| tests/test_canary_review_register_v3.py | eb675b704cb17f099a532474d4b29ce7fe0dd7106ed7529631129d9ff846a381 |

The final identity of this plan, and all six Python files above, is recorded by
reference in the external [final preservation and SHA-256 manifest](/private/tmp/canary-slice6d-targeted-qa-_rgchaoe/preservation-final.json).
That manifest is generated after the final document save. A file cannot contain
its own final literal SHA-256 without changing the bytes being hashed; the external
manifest is authoritative for this document's exact final bytes. This reference
does not claim independent custody; the operator must retain the evidence externally.

### Final fresh verification and handoff

Full approved offline suite (full): **4,296 passed, 6 existing optional skips,
0 failures, 759.54s** (759.938s wrapper). The only exclusion was the unchanged
historical listening-server file tests/test_canary_controller.py. All 177 Slice 6d
tests ran without skips. The six optional skips are exactly the same as the prior
handoff: explicitly enabled pinned application (controller_v3_application.py:26),
optional OpenAI 3.3.1 instrumentation runtime (instrumentation_v3_sdk.py:22), absent
optional OpenAI SDK (canary_sdk.py:9), optional pinned application runtime
(selection_state.py:5 and state.py:13), and complete optional CPython 3.13 source
worker (runtime_v3.py:452). See full.log and full-command.json for precise paths.
No live integration success is inferred from these offline results.

| Fresh gate | Result | External record |
| --- | --- | --- |
| Targeted regressions, after final style correction | 16 passed / 0 skipped | targeted-corrected.log, 21.89s |
| Complete Slice 6d | 177 passed / 0 skipped | focused.log, 127.60s |
| Relevant unchanged regressions | 1,100 passed / 1 optional skip | regression.log, 232.16s |
| Full approved offline suite | 4,296 passed / 6 optional skips | full.log, 759.54s |
| Ruff src/tests, caching disabled | PASS | ruff-final.log |
| Mypy all 67 source files, external cache | PASS | mypy.log |
| Formatting all six Slice 6d Python files, caching disabled | PASS | format-final.log |
| Historical fingerprints, fixtures, rubric, ceilings and lock | Exact match | fresh-identities.json |
| Baseline bytes/blobs/modes/index, HEAD/tree, exact additions, privacy/whitespace | PASS: 224 originals + exactly seven additions | preservation-pre-handoff.json; final post-save manifest |
| Six literal Python SHA-256 entries above | Match actual bytes | final post-save manifest |

Only four of the seven files differ from the prior handoff: review_packet_v3.py
adds the chronological-context documentation; its test file strengthens the
existing exact projection assertion and adds four per-turn regressions; the
register test file adds coordinated real-journal writer/reader processes, complete
snapshots, read-only audit restrictions and four journal/permission regressions;
this plan records contracts, failures/corrections, results and identities. The
human review module, register implementation and pure review tests are byte-identical
to the previous handoff. No SQLite production fix or public API change was needed.

The final pre-handoff gate independently passed all 224 original byte/blob/mode/
index identities, exact parent/tree and exactly seven regular nonexecutable
additions, with no staged changes or unexpected/ignored paths. The same gate runs
once more after this last plan save to bind all final bytes in preservation-final.json.
All six Python hashes above were independently compared with actual bytes. The
original dirty Study checkout remains on ac176dbc981789713df7e35473e0075c6f8d9691
with the same seven modified tracked files and two untracked entries. No branch,
worktree, baseline fixture, dependency, lock or historical evidence was changed.

All reviewed resource ceilings remain unchanged and provisional. Existing source
inspection limits and assurance boundaries remain unchanged. Journal preservation
is demonstrated for the supported locked runtime and these real interrupted
synthetic transactions; it is not certification of every SQLite/OS/filesystem or
power-loss behavior. Read-only access may advance atime; original/final access
times are captured, while bytes, layout and all other exposed metadata are required
to match. Synthetic principal authentication does not establish human identity,
authorship, substantive judgment, provider evidence or execution authority.

No unresolved implementation defect or architectural decision remains for these
two findings. **GO recommendation for PR publication following independent QA and
separate explicit publication authorisation.** The chronological v1 interpretation
is the documented alternative expressly allowed by the targeted QA request; no
silent versioned commitment was changed. No recovery, migration, automatic retry,
credential access, real identity enrolment, live execution or Slice 6e was added.

STOP: all seven additions remain untracked, unstaged and uncommitted on the
dedicated Slice 6d branch at the exact approved parent. No commit, push, PR or merge.
Await independent human QA and separate publication authorisation.
