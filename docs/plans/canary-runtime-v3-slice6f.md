# C3b Slice 6f — Offline Integration and Failure Testing

The PR #37 scratch-root correction record at the end supersedes earlier test
identities and disposition. Earlier implementation, independent-QA correction and
publication records remain historical evidence for their identified bytes.

## Authority and preservation

The operator authorised bounded implementation and offline verification M0–M4 on
2026-11-25, including the accepted detailed ExecPlan and its acceptance clarifications.
No commit, push, PR, merge, production change, live authority, provider acquisition,
credential discovery, account mutation, live inference, judge or Study is authorised.
Stop after verification and four-file ZIP export for independent source/test QA.

Approved merged parent: fd515f875b51ab33b29fed3b618343f14e080678.
Approved tree: e48b5c222905207b837de8690dd8409ad665eb33.
Exactly 234 baseline tracked files are protected in bytes, blobs, modes and index.
Branch: feat/canary-runtime-v3-slice6f-integration.
Worktree: /private/tmp/ai-test-harness-canary-runtime-v3-slice6f.
Initial external QA root: /private/tmp/canary-slice6f-qa-20261125-01.
Correction development QA root: /private/tmp/canary-slice6f-qa-correction-20261125-01.
Authoritative correction QA root: /private/tmp/canary-slice6f-qa-correction-20261125-02.

Exactly four additions: tests/test_canary_integration_v3.py,
tests/test_canary_integration_v3_faults.py,
tests/test_canary_integration_v3_application.py and this plan.
Stop for independent QA if another tracked file, protected-file modification,
dependency, larger ceiling, identity rewriting or new authority semantics is needed.

## Accepted fixture and assurance contract

Three separate paths: (1) identity-linked synthetic lifecycle through actual driver,
instrumentation, journal, approval, authority, envelope and review APIs against a
scripted stateful application; (2) public pinned Sales Agent controller with exact
mock provider; (3) direct journal persistence fixtures, never application execution.
Neither consumption-first test sequencing nor any spending result is an enforced
production dispatch boundary. Controller-generated run/auth/project/org identities
remain unchanged and incompatible with the authority-envelope linkage.

A/B workflows independently prepare IDs, policies, source claims, signed inputs,
stores, registries, assignments and references. They are valid in their own contexts
before substitutions. Synthetic approver/reviewer policies may enrol the same test
key in different roles/namespaces; this is not real identity or independence.

Actual APIs: resolve_definition/validate_binding/parse_receipt; assess_spending;
verify_approval; initialize_store/consume_approval/inspect_consumption;
initialize_registry/CanaryJournal/bind_provider; ProviderTransportV3,
BoundedResponsesClientV3, OrderedCanaryDriverV3 and MockApplicationGatewayV3;
inspect_run; assemble/publish/read/verify_envelope and verify_against_sources;
acquire/render/publish/read_packet; actual review signature/submission verification;
initialize_register/register_review/inspect_register/assess_registered_review.
No successful verification objects are constructed as substitutes.

Default source receipts are synthetic claims, not source verification. T is fixed
at 2026-11-24T12:00:00Z. Approval created T-60s, not-before T, expiry T+30m;
authority observations T..T+30s; review assignment T-60s..T+1h and policy
T-1h..T+1day; current review observation T..T+30s. Instrumentation uses actual
current UTC freshness, never a weakened/frozen production clock. Spending retains
the reviewed November period and prospective horizon. No historical cross-stage
timestamp proof is claimed.

Baseline driver uses 2 calls/turn: 8 logical calls/attempts, 4 POSTs, 8 trace GETs,
A1/B1/A2/B2, isolated sessions and committed same-conversation history. High volume
uses actual driver with 6 calls/turn and 3 attempts/call: 24/72, known-zero retry
failures only. Completion must follow actual continuation/accounting, never a
manufactured seal. Historical pending-review SKIP remains independent of later
human/derived quality. Mechanical FAIL survives human PASS.

## Identity and custody

Prepared expectations: source receipt/definition, proposal/auth ID/audience,
synthetic signer/policy, store configuration, provider project/org, review IDs and
policy, spending assignment/policy/reference. Necessarily returned values: consumed
intended run/record, registry and filesystem bindings. No universal ID/global use.
Consumption is store-local; approval claims are registry-local.

Operator checks envelope source/receipt/profile/history/accounting against original
retained inputs and actual public inspection, independently computes canonical
SHA-256 in documented envelope/history domains, and retains ExpectedEnvelopeReference
BEFORE publication. Publisher candidate is compared, never adopted as its own anchor.
Known persisted envelope bytes are bounded/read and verified before packet acquisition.

Packet/presentation commitments and subject are checked against that retained
context. Operator freezes an independently prepared assignment before any review
submission. Initial register binding is checked against configuration; zero head
is independently computed and compared with initializer candidate before retention.
After successful admission, inspect against OLD checkpoint, authenticate exact signed
bytes/observation/time and references, independently check event/predecessor digest,
construct expected checkpoint, compare candidate, then deliberately retain it.
Uncertain operations never retain a new anchor. Stale anchors and authenticated
conflicts remain visible together. Custody is simulated explicit test-operator work,
not proof of organisational independence.

Spending has no run/store/registry/envelope binding. Prospective external projects
may validly differ from synthetic execution. Parse success is representation only;
trusted test reliance recomputes from independent inputs. All readiness/billing/
provider/source/live authority limitations remain unchanged.

## Bounded scenario traceability

All scenario IDs below are mandatory; parameterised cases may share functions.
Actual node IDs, execution outcomes and durations will be retained in external logs.
No new core test may skip. Existing exhaustive component permutations are reused.

| ID | Expected interaction/boundary |
| --- | --- |
| P0-01 | Complete identity-linked scripted driver lifecycle, actual crypto/persistence and retained custody |
| P0-02 | Both A/B valid; whole artifact/context substitutions reject reference_mismatch, binding_mismatch or source_mismatch without mutation |
| P0-03 | Same-store duplicate authorisation_consumed; original receipt preserved |
| P0-04 | Independently configured second store may consume once; no global uniqueness claim |
| P0-05 | Consumed approval, absent journal/execution, unchanged receipt |
| P0-06 | Actual timeout; transport_ambiguous, unknown accounting, no replacement, source_ineligible review |
| P0-07 | Complete operations/mechanical FAIL/human PASS => derived FAIL |
| P0-08 | Invalid review signature_not_verified cannot poison recorded state |
| P0-09 | Authenticated conflict + stale checkpoint => ERROR, both issues and reviews retained |
| P0-10 | Direct incomplete journal; anchored artifact possible; source_ineligible review |
| P0-11 | Journal suffix change after anchoring => source_mismatch; old anchor unchanged |
| P0-12 | SIGKILL after consumption returned, before journal; consumed row retained |
| P0-13 | SIGKILL after driver journal complete, before envelope; journal independently inspectable |
| P0-14 | SIGKILL during envelope publication; partial denied or anchored bytes readable, no publisher-return claim |
| P0-15 | Verified envelope, no review: anchored EMPTY/PENDING/SKIP |
| P0-16 | SIGKILL after review COMMIT/sync before return: event + pending + stale anchor, ERROR |
| P0-17 | Successful candidate deliberately unretained: checkpoint_stale, no automatic adoption |
| P0-18 | Conditional spending conformity/headroom 4 alongside separate completed workflow |
| P0-19 | Eligible headroom 0.5 => headroom_insufficient/NONCONFORMANT |
| P0-20 | Reserve-only evidence => HYPOTHETICAL/INDETERMINATE, no decision headroom |
| P0-21 | known_incomplete_reporting blocks decision headroom, subtotal retained |
| P0-22 | observation_stale blocks favourable conformity |
| P0-23 | outside_validity + period_or_horizon_expired at rollover |
| P0-24 | Valid A/B assignment/policy/reference substitutions; wrong-project scope_mismatch |
| P0-25 | Internally consistent imported cost 0/headroom 5 differs from recomputed cost 1/headroom 4 |
| P0-26 | Valid prospective external project differs from synthetic scope, no readiness promotion |
| P1-01 | Namespace/expiry/revocation/policy denial before journal, exact fixed codes |
| P1-02 | Two separate consumers, at most one winner, busy/consumed loser, no retries |
| P1-03 | Authority kill before/after COMMIT, actual pending/row transition and fresh inspection |
| P1-04 | Eligible incomplete FAIL vs disqualified UNABLE/SKIP |
| P1-05 | Current revocation/missing register/changed source => ERROR, independent findings preserved |
| P1-06 | Actual high-volume driver and representative persistence error/measurements |

## Process, isolation and resource contracts

Spawn/pipe/barrier protocols require positive evidence of the exact boundary,
confirmed persistence transition where required, actual intended interruption,
confirmed process termination/no normal return, then fresh-process read-only
inspection. Failure before the barrier is a failed scenario, never coverage.
No sleep races, production hooks, automatic retry/recovery/resume/replacement,
marker cleanup, journal rewriting or checkpoint adoption.

Per barrier/readiness/join: at most 20s and remaining monotonic total. Forced
teardown: 5s. Total process test 90s; competing/high-volume 120s; public source
gate 120s; controller gate 180s. Preserve crypto 5s, SQLite 2s, controller cleanup
5s and inference timeouts. Confirm no surviving workers. Timeout fails and preserves
state. Measurements are observed fixture resource usage, not hard system guarantees.

All keys, stores, journals, publications, logs/caches and verification records are
outside source/historical roots. Minimal env; approved TMPDIR; bytecode/cache disabled.
Deny Internet/DNS, credential/SSH discovery, real provider/admin/target/judge/Study
activity and writes outside synthetic roots. Allow necessary local IPC/event-loop
operations only. Exact mock transports. Narrow local unsigned Git init/add/commit
in synthetic source fixtures only; no remote operations from tests. Fixed system
OpenSSH ephemeral signing/verification only. Audits include filesystem dir_fd paths,
SQLite destinations and subprocess commands; Python/OS/filesystem remain trusted.
No hostile-code sandbox, distributed single use or physical power-loss certificate.

Unchanged limits: envelope/reference 64/4KiB; authority preflight16MiB; source
journal16MiB/2048 records/512KiB per record; review packet16MiB/presentation64MiB;
review payload/signature64/4KiB; register4MiB/event256KiB; spending assignment/policy/
reference32/16/4KiB and bundle/assessment64KiB. All logical depth/value/issue limits
also unchanged. Measure complete/FAIL/interrupted/high-volume, assessment revisions,
large prose, register conflicts and issue-rich/max-precision spending. Record bytes,
counts, durations and native peak RSS with platform/measurement-scope limitations.

## Explicit integration gates

New application module has two independent opt-ins: CANARY_V3_SLICE6F_SOURCE=1
and CANARY_V3_SLICE6F_CONTROLLER=1; absent/0 skips only the disabled optional gate;
other values fail. Enabled prerequisites fail, never importorskip/install/fallback.
Application root is explicitly supplied by CANARY_V3_SLICE6F_APPLICATION_ROOT.

Gate A: public verify_source on a clean temporary exact-source copy, actual local
Git commit/locks/runtime, pinned app, fresh child loaded-module origins. Receipt uses
synthetic-test/offline-verification-v1/application-lock runtime. Positive matching,
wrong receipt harness commit => harness_identity_mismatch, changed temporary
tracked py.typed => dirty_worktree. No injected source observations or app mutations.

Gate B: fresh clean source copy and child; public OfflineCanaryControllerV3.run,
never development method. Actual pinned routes/tools/session/commerce/accounting/
shutdown with exact mock provider. Assert 4 POSTs/8 GETs/12 calls/attempts, prices,
stock, isolated A/B histories, completion, zero owned survivors, clean source match,
false authority, billing unknown. Public registry inspection characterises generated
IDs and project/org. Envelope rejects actual run ID invalid_input and consumed
intended run in controller registry journal_unavailable. No IDs/constants rewritten.

## Milestones and verification commands

- [x] M0 exact merged parent/tree, isolated worktree, external inventory and runtime preflight.
- [x] M1 complete actual linked synthetic workflow and custody.
- [x] M2 every relevant P0/P1 substitution, outcome and spending scenario.
- [x] M3 real interruption/race tests, fresh inspections and isolation.
- [x] M4 explicit gates, SDK/regression/full offline/static/privacy/preservation and post-save ZIP gate.

Harness interpreter: /private/tmp/ai-test-harness-canary-runtime-v3-slice2/.venv/bin/python.
Application interpreter: /Users/rebeccawilliams/Developer/study-v1-local/sales-agent/.venv/bin/python.
Common env: env -i PATH=/usr/bin:/bin LC_ALL=C LANG=C TMPDIR=<QA>/tmp
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src, python -B -m pytest -q --tb=short -rs
-p no:cacheprovider, a NEVER-REUSED external --basetemp, log under <QA>/logs.
Gate env adds explicit app source to PYTHONPATH, its root variable and exactly the
enabled gate flag. Core: both new hermetic modules; gates: individual named tests.
Regressions: execution policy, selection/runtime/evidence/instrumentation/driver/
controller/journal/fault/approval/authority/envelope/review/packet/register/spending.
SDK regressions: both existing SDK modules under app interpreter. Full offline:
--ignore=tests/test_canary_controller.py (historical listening-server exclusion only).
Ruff src/tests --no-cache; mypy src with external cache; format three new Python
files --no-cache; external whitespace/privacy/identity/preservation scripts.
Exact commands, logs, collection traceability and measurements retained externally.

M0 confirmed Python3.12.13/3.13.15, SQLite3.53.1, OpenSSH9.9p2/LibreSSL3.3.6.
All 25 harness and 32 applicable app registry packages match their separate locks.
Harness lock a8a1997cb57cf88bad6d8b00e38efa0b62b77c2ad0057c667ab52933585b1dba;
app lock bfb480c44c95acf6df4230a9a3e75fbce7d8e8dbec72db2bcdf5513bb434d11c.
Narrow exact-SHA fetch and worktree creation required sandbox escalation; both were
explicitly authorised. Original checkouts/worktrees/dirty changes are preserved.

Final gate: all 234 original bytes/blobs/modes/index exact; four untracked regular
nonexecutable additions only; no staged/ignored/generated files. No commit/push/PR.
After last plan save, external post-save SHA manifest binds all four final files.
ZIP contains only those files at repo-relative paths, verified against that manifest;
export to Downloads/slice6f-qa-artifacts.zip and verify member/archive identities.

## Initial implementation execution record

Initial main lifecycle suite launched after the first implementation save. Results,
fixture corrections, exact commands, traceability and acceptance evidence follow.

### M1–M3 fresh implementation results

Complete new hermetic core: **43 passed, zero skipped, 121.27s**
(121.574s external wrapper). All P0-01..P0-26 and P1-01..P1-06 are covered.
External scenario-traceability.json records each of the 32 scenario IDs, exact
collected test nodes, execution mechanism, expected boundary, actual PASS and
per-node duration. It is generated from core-final.xml, not inferred from count.
Seven actual process-interruption observations are retained in
interruption-observations.json. Two-process contention, fresh read-only inspectors,
positive barriers, actual COMMIT/sync checks and SIGKILL exit codes passed. No
normal return preceded the selected kill; no worker survived bounded cleanup.

No protected production defect was found. Fixture/expectation corrections:

- main-01: 28 passed, 1 failed, 75.19s. Removing the database from an existing
  register violates its required layout, so _layout returns register_corrupt,
  not the proposed generic register_unavailable. Corrected only the new test's
  exact expectation; missing state still yields overall ERROR/UNAVAILABLE, never
  EMPTY/PENDING. This is the documented contract distinction, not a relaxed gate.
- faults-01: 9 passed, 1 failed, 29.33s. The test audit erroneously permitted
  verification but not reviewed explicit synthetic signing. Added the exact sign
  namespace/key-root checks. faults-02 then passed all 10 tests in 35.43s.
- source-gate-01 failed because the test write audit rejected the fixed /dev/null
  character device used by subprocess.DEVNULL. Allowed only that verified null
  device as local process plumbing; it cannot persist an artifact. All real
  filesystem artifacts remain under the synthetic QA root. source-gate-02 passed.
- Initial Ruff found unused imports, literal-dict style and one nested condition;
  corrected only the three new Python files. Final Ruff and mypy pass below.
- The first external identity script incorrectly requested legacy dataset hashing
  for populated v2 definitions. Corrected the external script to load the actual
  descriptor and dataset-cases-v2 hash. No dataset/assertion/fingerprint changed.
- External interrupted-resource extraction initially assumed an untruncated pytest
  directory name. Corrected the external glob and excluded pytest's current-directory
  symlink alias to avoid double counting. The final record reads the original
  successful core artifacts; no test, artifact or measured state was changed.

Final new-test bytes were frozen before core-final, both explicit final gates,
regression-final, sdk-final and full-final commands. Each *-command.json and
*-result.json records exact argv, stripped environment, duration/exit code and
SHA-256 of all three test modules. No Python test edits followed those launches.

### Explicit public gates

Source-final: **1 passed, zero skipped, 2.420s wrapper**. Actual verify_source
matched clean copied committed source, exact pinned app and application lock/runtime;
negative cases were harness_identity_mismatch and dirty_worktree. All loaded harness
origins were checked in the fresh child; no Sales Agent or OpenAI module was imported.
Source authorisation remains false. This is synthetic fixture-source matching,
not source approval for this implementation checkout.

Controller-final: **1 passed, zero skipped, 14.825s wrapper**. Public .run(), never
_run_development_offline(), executed actual pinned routes/tools/commerce/session
handling and OpenAI3.3.1 SDK against exact provider MockTransport. Four POSTs/eight
trace GETs, twelve logical calls/twelve attempts, isolated A/B histories, expected
prices/stock, certified journal completion and observed SDK/HTTP/lifespan shutdown;
zero surviving owned threads. Fresh loaded-module origins and application runtime
were checked. Source matching was true; source/provider/live authority remained
false; billing unknown and historical overall SKIP/human review PENDING.

Controller generated its own run-/synthetic-offline- identities and offline project/
org. Unchanged assemble_envelope rejected the actual controller run invalid_input,
and the independently consumed intended run against that registry journal_unavailable.
Original journal bytes/metadata were unchanged. Consumption preceding this run
was caller-selected sequencing only, not mandatory authority enforcement.
Gate evidence: source-final-temp/**/gate-result.json and
controller-final-temp/**/gate-result.json; logs, JUnit and commands outside source.

### Representative resource observations

| Mechanism/shape | Records | Calls/attempts | Journal-source bytes | Envelope | Packet / presentation | Register DB |
| --- | ---: | --- | ---: | ---: | --- | ---: |
| Actual scripted driver, complete | 62 | 8 / 8 | 76,833 | 5,676 | 22,807 / 26,479 | 24,576 |
| Actual scripted driver, mechanical FAIL | 62 | 8 / 8 | 77,356 | 5,676 | 23,008 / 26,731 | 24,576 |
| Actual scripted driver, maximum roster accounting | 222 | 24 / 72 | 266,215 | 5,680 | 22,823 / 26,495 | 24,576 |
| Direct journal, 3 assessment revisions/turn | 53 | 4 / 4 | 58,194 | 5,672 | 30,554 / 34,756 | 16,384 |
| Direct journal, 20,000 added prose characters/turn | 45 | 4 / 4 | 129,396 | 5,672 | 102,656 / 106,308 | 16,384 |

The direct fixtures are supplied persistence observations, not application/driver
execution. Full actual 24/72 driver completion took 13.18s; ordinary linked workflow
5.15s. Two authenticated conflicting events grew the register to 40,960 bytes;
representative signed review payload was 6,409 bytes. Zero/one-event DBs measured
16,384/24,576 bytes. Existing resource ceilings were not increased.

Spending representative 31-bucket/eight-alert/max-precision fixture: assignment
4,458 bytes, policy 2,561, bundle 11,611, reference 540, assessment 17,702. Issue-rich
assessment 13,405 bytes. Actual outcomes NONCONFORMANT/INVALID_EVIDENCE are expected;
measurement is not favourable readiness. Separate baseline spending remained
CONDITIONALLY_CONFORMANT/headroom 4, with every fixed assurance limitation intact.
Imported internally consistent cost 0/headroom 5 parsed without origin authentication;
independent recomputation gave cost 1/headroom 4. External project differences were
valid under their own prospective assignment, never interpreted as run expenditure.

macOS ru_maxrss native bytes measured roughly 92–97MB in the shared core pytest
process; these are process high-water observations including preceding tests, not
per-operation peaks. The isolated full-workflow worker measured 77,938,688 bytes
(~74.3MiB). Its successful path had zero network events and twelve allowed synthetic
OpenSSH operations; deliberate DNS/write/dir_fd/credential-path probes were blocked.
The audit is a trusted-test/cooperative runtime control, not a hostile-code sandbox.
Measurements and process observations are retained in measurements.json and
interruption-observations.json. Interrupted operations are not counted as completed
workflows, and observations do not certify physical power-loss behaviour.

The actual timeout observation was operationally_uncertain: 9 records, 1 logical
call/attempt, 1 unknown attempt, 0 incomplete calls and 2 operational errors;
known subtotal "0", total unknown, completion false. Source journal files totalled
14,916 bytes; duration was 1.022s. No positive incomplete-call count or fabricated
stop event is inferred from that observation. The interrupted envelope pending
and durable-final files each measured 5,676 bytes. These observations are retained
separately in interrupted-measurements.json.

### Historical and static preservation

Fresh final-identities.json confirms exact historical C1 roster/assertions, v2.1,
all four V3 fingerprints, rubric, 50-case dataset-cases-v2 hash and descriptor hash,
application revision and both fixture hashes. Dataset remains
4a0e40d6dce4b78cc194352bf23d69dabcc8fe3c0f440d50f2cce2bd6a956028;
rubric 80339c774d9af411d2d2c3e2a1552908faa9ac6e52eb51ca66de50ce7c15f381.
No judge or Study case was executed to compute metadata identities.
Intermediate exhaustive preservation passed all 234 originals, index/parent/tree,
exact four additions and no ignored artifacts. The authoritative final post-save
gate is recorded in preservation-final.json after this plan's last save.

Ruff across src/tests with --no-cache passed. Mypy with external cache passed all
68 source files. Formatting passed for all three new Python modules. External
privacy/whitespace and complete final results are consolidated below. No dependency installation,
lock change, real credential discovery, external provider/admin request, listener,
live target/judge or historical private-evidence access occurred.

Preservation scope qualification: M0 recorded the original unrelated dirty
checkout's Git status and worktree identities, but not an initial byte inventory
of its dirty files. original-checkout-preservation.json now records all 138 files
and confirms every file change time precedes M0. Its original status is unchanged,
and no task operation wrote those files. This is supporting evidence, not a
retroactive initial-byte-hash comparison. The separate approved 234-file baseline
has a complete pre-implementation byte/blob/mode/index inventory.

### Frozen test identities and external QA records

SHA-256 of the exact test bytes used by every final test command:

- tests/test_canary_integration_v3.py:
  0b6705c44876ca071b752141b92d4902e91fcf527bb1d1f708692be2b0966812
- tests/test_canary_integration_v3_faults.py:
  c3040a87c8915a1a9276ae08778a197db9c970019ba09d80756d79e095967873
- tests/test_canary_integration_v3_application.py:
  169366158200198e74415f980166328b0ec96e28a0b54dd10f49c532949c52de

All external records below are relative to the QA root stated above:

- baseline-inventory.json: pre-implementation protected inventory and checkout state.
- runtime-harness.json / runtime-application.json: exact interpreters and locked packages.
- *-command.json / *-result.json / logs/*.log / *.xml: fresh commands and results.
- scenario-traceability.json: all 32 scenarios, actual collected nodes and outcomes.
- measurements.json / interrupted-measurements.json / interruption-observations.json:
  resource, interruption, persistence and cleanup observations.
- final-identities.json: historical definitions, fixture, dataset and rubric identities.
- verification-summary.json: consolidated results and final four-file hashes.
- preservation-final.json: exhaustive post-save preservation and four-file identities.
- archive-verification.json: exact ZIP identity and its four verified members.
- export-verification.json: Downloads copy, archive/member identity verification.
- handoff-manifest.json: hashes of the selected public QA records and final additions.

The post-save manifest carries this plan's final hash; the plan does not attempt
to contain its own hash. The four-file archive deliberately excludes QA records,
keys, signatures, stores, journals, logs, caches and all existing repository files.

### Final component and SDK regressions

Relevant unchanged component regressions: **2,077 passed, 1 historical optional
skip, 685.61s** (685.975s external wrapper). The only skip was
test_canary_runtime_v3.py's complete source check, which requires the separately
enabled pinned CPython 3.13 worker. This ordinary harness run did not enable that
historical opt-in. The new explicitly enabled public source gate independently
executed in the pinned application environment and passed, as recorded above.

Pinned SDK regressions: **28 passed, zero skipped, 25.61s** (26.105s external
wrapper) across test_canary_instrumentation_v3_sdk.py and test_canary_sdk.py using
the actual locked application interpreter, installed OpenAI SDK and mock transport.
No SDK/provider fallback or dependency installation was used.

Final runtime inventories were repeated and compared byte-for-byte with their M0
records: both interpreters, SQLite, every applicable locked package and lock hash
were unchanged. All verification inputs and logs remain outside the worktree.

### Full offline suite and final disposition

Full approved offline suite: **4,871 passed, 8 skipped, 986.66s** (987.103s external
wrapper), exit 0. The only explicit exclusion remained the historical listener
module tests/test_canary_controller.py. All 43 new core tests ran and passed again.
No live target, provider, judge or Study evaluation was invoked; existing offline
Study-related unit tests continued to use their injected fakes and synthetic data.

The eight skips are reported separately from the explicit gate results:

| Scope | Module / reason | Skips |
| --- | --- | ---: |
| Historical optional | test_canary_controller_v3_application.py: explicit application opt-in disabled | 1 |
| Historical optional | test_canary_instrumentation_v3_sdk.py: pinned SDK absent from harness environment | 1 |
| Historical optional | test_canary_sdk.py: OpenAI absent from harness environment | 1 |
| Historical optional | test_canary_selection_state.py: pinned application runtime absent | 1 |
| Historical optional | test_canary_state.py: pinned application runtime absent | 1 |
| Historical optional | test_canary_runtime_v3.py: pinned CPython 3.13 source-worker opt-in disabled | 1 |
| New optional | Slice 6f public source gate disabled in ordinary suite | 1 |
| New optional | Slice 6f public controller gate disabled in ordinary suite | 1 |

Both new optional gates separately ran explicitly enabled and passed with zero
skips; both historical SDK modules separately ran under the actual pinned runtime
and passed all 28 tests. A historical optional skip is not reported as an attempted
gate pass. No new core scenario was skipped or replaced by a weaker mechanism.

Final acceptance evidence is bound to the frozen test bytes above. Ruff, mypy,
formatting, privacy sentinels, filesystem isolation, no-network checks, whitespace
and historical metadata identities passed. No protected code or configuration was
modified. No production defect, new dependency or expanded ceiling was required.
The only semantic expectation correction was the documented register layout error
classification. Authentication and custody are synthetic; store-local consumption
does not enforce production dispatch admission. Public controller identities remain
incompatible with approval-envelope linkage. Spending remains detached/prospective;
mechanical FAIL, independent findings, stale/conflicting review and fixed assurance
limitations remain visible. This does not establish real human/provider authority,
billing verification, application readiness or permission for live execution.

**Recommendation: GO for independent source and test QA of these four additions.**
The original dirty-checkout snapshot qualification above accompanies that
recommendation. Source/test QA and any publication remain separate decisions.

After this final save, the handoff requires the external preservation script to
recheck exact approved parent/tree, all 234 bytes/blobs/Git modes/index entries,
unchanged original checkout status/worktree identities/pinned application state,
exactly four untracked regular non-executable additions and zero generated or
ignored repository artifacts. It then writes preservation-final.json with all four
SHA-256 values, including this plan. Verification-summary.json must match those
final four bytes and every final command's test hashes.

The exclusive ZIP writer must read only those four manifest paths, preserve their
repository-relative names, compare exact member bytes/hashes and pass testzip.
The authorised Downloads copy must match the archive hash and the same four member
identities; archive-verification.json and export-verification.json retain the
results. handoff-manifest.json binds selected external QA records. A failed
post-save gate prevents successful handoff; the final operator response is issued
only after all gates pass. The ZIP contains exactly the four approved additions.

**Mandatory stop after verified export: no commit, push, PR, merge, auto-merge or
subsequent-slice work. Await independent QA and separate publication authority.**

## Independent source/test QA correction

The operator submitted the independent QA correction on 2026-11-25. QA verified
the original four-file ZIP SHA-256
e65c4ac9720e29b891083adeba549daef02f16136293476fc02e63802005f3bf
and accepted the linked architecture, custody, public gates, interruption coverage,
spending semantics, controller incompatibility and resource ceilings. Its
CONDITIONAL GO required the targeted cooperative-audit correction below. No
production defect, redesign, dependency or additional tracked file was requested.
Only the same four uncommitted additions may change; the exact 234-file approved
baseline remains protected. The original dirty-checkout qualification above is
accepted and retained; no retroactive pre-M0 byte comparison is claimed.

### Reproduction before correction

Actual locked CPython 3.12.13 execution loaded the exact uploaded helper with
SHA-256 c3040a87c8915a1a9276ae08778a197db9c970019ba09d80756d79e095967873.
In disposable synthetic directories only, all four reported gaps reproduced:
ordinary relative Path.write_text outside the writable root succeeded; an
outside-root private-history stand-in could be read; a writable SQLite filename
containing mode=ro succeeded; and a simulated unapproved Git config audit event
was admitted. No Git configuration operation was actually executed. Details are
in reproduced-gaps.json under the correction QA root. The correction-start
preservation record matched all 234 protected files and the previous four-file
handoff before any edit.

### Corrected cooperative boundary and installation timing

isolation() remains test-local, with no production hooks or sandbox framework.
Its ordinary Python open audit now checks relative and absolute paths against
actual cwd. The os.open wrapper preserves actual dir_fd calls, resolves their
descriptor paths, and supplies that context to the audit using thread-local state.
Regular file descriptors opened through Python are also checked. Existing local
IPC descriptors are permitted. Realpath checks reject parent/symlink escapes.
Explicit read-only inspection roots deny writes even within the writable tree.

Reads are allowed only under the approved synthetic writable/inspection trees,
unchanged harness source, installed standard-library/package roots, explicit test
source files and explicitly supplied public-gate source/application paths. Import
cache reads correspond to those permitted source files. Ancestor directory opens
with O_DIRECTORY permit required descriptor traversal, not ancestor directory
listing or file reads. Credential-path denials remain an additional check, not the
read policy. Private-evidence and credential probes use disposable stand-ins only.

The sqlite3.connect wrapper checks Path/string/bytes database representations and
the actual uri keyword or supported positional flag. Supported local file: URIs
must have one mode parameter and no authority, fragment or extra URI options.
Only actual uri-enabled mode=ro permits connections to explicit read-only roots;
mode=ro text in a plain filename, uri=False, duplicate modes and extra query
options cannot grant access. Audit events for unwrapped constructors receive no
unproven read-only exemption. Positive inspections also attempt a real write and
require SQLite's readonly error. Existing interrupted COMMIT/pending observations
remain unchanged. This is not arbitrary-SQL or native SQLite confinement.

Git admits only exact reviewed rev-parse/ls-tree/ls-files argument tuples, exact
source/application roots and the two fixed minimal environment/prefix forms used
by the public verifier and fixture identity reader. Configuration operations,
additional flags, environment injection, substituted roots and all other verbs
are denied. OpenSSH admits only exact synthetic signing/verification shapes,
approved key paths, artifact names/directories, principals, namespaces and minimal
environment. Unapproved command probes use audit events, not actual execution.

The audit is installed in fresh child processes after trusted imports, binding
deserialization, ephemeral key generation and fixture preparation. Source copying,
local synthetic Git init/add/commit, initial runtime/app preflight and the exact
tracked-application-file inventory happen before installation; these are not
claimed as audited operations. Public verify_source, controller .run(), their
subsequent imports, linked isolated lifecycle, interruption operations and fresh
durable-state observations run after installation. The full-workflow dir_fd
negative probe opens its disposable ancestor descriptor during trusted preparation.
The regression worker prepares synthetic sentinels, read-only SQLite state, Git
fixture and descriptors first; all positive and negative probe operations follow
audit installation. Fixture cleanup in the pytest parent is trusted test work.

This is a cooperative Python audit for the exercised APIs and reviewed commands.
It does not confine hostile code, arbitrary native file access, inherited raw
descriptor I/O or arbitrary SQL; subprocess internals and Python/OS/tooling are
trusted. Metadata operations without corresponding audit events are not covered.
No claim of general subprocess confinement or an OS sandbox is made.

### Regression probes, retained assertions and development results

One new deterministic core test runs 37 named negative probes in a fresh worker:
ordinary relative/absolute and descriptor-relative writes; read-only writes;
parent/symlink escapes; absolute/relative/dir_fd private-data reads; synthetic
credential reads; private directory listing; eleven SQLite forms (including
credential/private-data stand-ins) and
an unvalidated constructor; and unapproved Git operations/arguments/environment/
roots plus SSH namespace/artifact/environment/key substitutions. The same worker
proves allowed Python/os.open/fdopen reads/writes, actual keyword/positional
read-only SQLite, ordinary Path/bytes writable SQLite, source/package reads and
actual approved local Git identity queries. The existing complete isolated
lifecycle proves actual permitted OpenSSH signing and verification. Outside
directories retain only their original stand-in, with no rejected write artifact.
The new probe does not replace any approved P0/P1 scenario.

assertion-preservation.json compares the original verified ZIP with current ASTs:
all assertions in the 26 original test functions and the original workflow workers,
public gate child and invocation functions are retained. The main lifecycle module
is byte-identical. Only the faults helper/probe code, application audit setup and
this plan changed. All 32 approved scenario IDs and production assertions remain.

Development results (logs and exact source hashes retained externally):

- targeted-correction-01: 1 passed, 2 failed, 7.14s (7.513s wrapper). Strict reads
  initially denied ancestor directory traversal required by unchanged authority/
  packet APIs; added only O_DIRECTORY traversal for approved ancestors.
- source-correction-01 failed: new trusted inventory command emitted a platform Git
  temporary-directory warning on stderr. Reused the existing local_git helper's
  fixed environment/stderr handling; no gate assertion was relaxed.
- controller-correction-01 failed: importlib attempted the cached form of an
  explicitly permitted test source file. Allowed corresponding source-cache paths,
  preserving the source read allowlist and denying unrelated paths.
- targeted-correction-02: 3 passed, 15.04s (15.340s wrapper). Source-correction-02:
  1 passed, 2.23s (2.552s wrapper); controller-correction-02: 1 passed, 17.33s
  (17.638s wrapper). Four SSH and one Git-argument denial probes were then added.
- targeted-correction-03: 3 passed, 14.066s wrapper, including all 34 negative probes.
- A preliminary complete run then passed 44 core tests in 140.23s (140.628s wrapper),
  both public gates and all 28 SDK regressions. During final review, SQLite's
  connection check was routed through the ordinary-open read policy so that it
  shares the credential-path denial too. Three SQLite credential/private-data
  stand-in probes were added, bringing the negative total to 37. This supersedes
  every preliminary final-labelled command under the development QA root; none is
  used as final-byte acceptance evidence, including broad suites already running
  when those test bytes changed. Their actual outcomes remain in development logs.
- targeted-final-preflight under the authoritative correction QA root: 3 passed,
  17.148s wrapper, including all 37 probes and the linked isolated lifecycle/fresh
  inspection. The complete final programme was then launched from fresh basetemps.
  No Python test edit followed those authoritative launches.

### Frozen correction identities and fresh verification

Final test SHA-256 values, bound to every fresh final command/result record:

- tests/test_canary_integration_v3.py:
  0b6705c44876ca071b752141b92d4902e91fcf527bb1d1f708692be2b0966812
- tests/test_canary_integration_v3_faults.py:
  f6b9020fb6e6adc3119b6b72aaa44d804f0b4b9661809c10b9f05c61d724a510
- tests/test_canary_integration_v3_application.py:
  cf1c9e502fac53433ff76d5093a5132e2c8126e1c6a855dd9d12fb13e35484e6

All final correction verification records are under the authoritative correction
QA root; the separate development root retains reproduction/correction history. Fresh
external basetemp directories and the original locked interpreters, minimal
environments, timeouts and historical listener exclusion are unchanged. Ruff,
mypy (68 source files) and formatting passed. Historical dataset/rubric/fingerprint/
fixture identities passed; repeated runtime inventories match the original locks.
The final gate, core and broader suite results, plus post-save artifact gates,
are recorded below after their authoritative commands finish.

### Authoritative correction results and resource observations

Complete core: **44 passed, zero skipped, 192.38s** (192.941s wrapper). All 32
approved scenarios pass, plus the new isolation regression with 37 denial probes
and positive operations. scenario-traceability.json binds each original scenario
to actual passing collected nodes; isolation-correction-traceability.json binds
the reproduced findings and all 37 indexed negative observations. No approved
scenario or assertion was dropped. The retained original assertions were compared
again against the verified original ZIP after the final test-byte freeze.

Both explicit gates passed with zero skips: public source verification, 4.564s
wrapper; actual public pinned controller .run(), 31.923s wrapper. Actual clean-source
and loaded-origin checks, source negatives, four POSTs/eight GETs/twelve calls and
attempts, prices/stock, history isolation, completion and shutdown assertions all
remain. Controller incompatibility is still invalid_input/journal_unavailable with
unmodified generated identities and journal. SDK regressions: **28 passed, zero
skipped**, 31.625s wrapper. No private development controller fallback was used.

Actual linked lifecycle: 62 records, 8 calls/attempts, 76,856 journal-source bytes,
5,676-byte envelope, 22,807-byte packet/26,479-byte presentation, 24,576-byte DB,
8.252s. Mechanical-FAIL case: 77,380 source bytes, packet 23,008/presentation 26,731;
human PASS still cannot reverse FAIL. Actual maximum execution: 222 records,
24 calls/72 attempts, 266,230 source bytes, envelope 5,680, packet 22,823,
presentation 26,495, DB 24,576; actual successful completion took 20.162s.
Existing ceilings and operation timeouts remain unchanged.

Direct journal revision/prose fixtures: 58,216/129,418 source bytes, packets
30,554/102,656 and presentations 34,756/106,308, respectively; these are persistence
observations, not application execution. Two authenticated review events occupy
40,960 DB bytes; signed payload 6,409 bytes. Spending fixture remains 31 buckets/
8 alerts, assignment 4,458/policy 2,561/bundle 11,611/reference 540/assessment 17,702
bytes, issue-rich assessment 13,405 bytes. No assurance outcome was promoted.

Actual timeout: 9 records, 1 call/attempt, 1 unknown, 0 incomplete calls, 2 operational
errors, known subtotal "0"/unknown total, completion false; 14,938 source bytes,
1.740s. Interrupted envelope pending/final files each remain 5,676 bytes. Seven
actual process interruption observations, fresh read-only inspection, pending/
COMMIT state, retained anchors and bounded cleanup all pass; no worker survives.

Shared pytest ru_maxrss observations were 100,515,840–105,168,896 native macOS bytes,
not isolated per-operation peaks. Isolated complete-workflow worker: 82,100,224
bytes, zero successful-path network events, twelve permitted actual synthetic SSH
operations and one subsequently blocked DNS probe. Canonical and percent-encoded
read-only URI parameters were additionally checked against actual SQLite: every
attempted write failed readonly (sqlite-uri-semantics.json). These remain bounded
fixture observations, not hard resource or hostile-code confinement guarantees.

relative-positive.json additionally confirms ordinary relative Python read/write
and relative os.open/fdopen operations succeed with cwd inside the approved
synthetic root. The fix does not deny all relative operations. An intermediate
external preservation gate after the correction passed all 234 protected files,
the exact four additions and absence of ignored/generated repository artifacts.

The original unrelated checkout's 138 files also match the byte/mode/time inventory
retained at the first handoff (original-current-comparison.json). This strengthens
preservation since that late inventory; it does not remove the accepted pre-M0
snapshot qualification.

Authoritative unchanged component regressions: **2,077 passed, 1 historical
optional skip, 897.51s** (898.109s wrapper). The skip is the historical pinned
CPython 3.13 complete-source worker opt-in; it is not an attempted-gate pass.
Both new explicit public gates separately passed without skips, as recorded above.

development-summary.json retains the superseded campaign outcomes. Its component
run passed 2,077 with 1 skip in 855.51s. Its full run finished with 4,871 passed,
8 skipped and 1 failure in 1,222.73s (1,223.360s wrapper): the parent had collected
the 34-probe test while its fresh child loaded the subsequently edited 37-probe
version (assert 37 == 34). That source-mixed run was explicitly invalidated before
completion and is excluded from final acceptance. No assertion was weakened to
hide it; the authoritative complete campaign uses frozen final bytes throughout.

The external traceability generator normalises JUnit's tests.module class names
to actual tests/module.py node paths and compares them with fresh pytest
collection. This corrects record formatting only; scenario mapping, test execution
and results are unchanged.

### Final correction acceptance and artifact gate

Authoritative full approved offline suite: **4,872 passed, 8 skipped, 1,198.73s**
(1,199.428s wrapper), exit 0. The only exclusion remains
tests/test_canary_controller.py, the historical listening-server module. All 44
new core tests passed again, including the 37-probe regression. The eight optional
skips are the same six historical modules and two ordinary-suite Slice 6f gate
opt-ins listed in the initial table above: controller_v3_application,
instrumentation_v3_sdk, canary_sdk, selection_state, canary_state and the runtime_v3
pinned-worker check; plus CANARY_V3_SLICE6F_SOURCE and CANARY_V3_SLICE6F_CONTROLLER.
They are not new core skips. Both new gates and both historical SDK modules were
separately explicitly executed in the pinned application runtime and passed, as
recorded above. Historical opt-ins not attempted remain reported as skips.

- [x] All four original gaps reproduced with the uploaded helper in the locked runtime.
- [x] Relative/absolute/dir_fd filesystem checks, read allowlist and read-only roots corrected.
- [x] SQLite connection representations/actual read-only semantics and shared read policy corrected.
- [x] Git/SSH exact operations, roots, arguments, environment and synthetic paths constrained.
- [x] All 37 negative probes and legitimate positive operations passed.
- [x] All 32 approved scenarios, retained assertions and 44 core tests passed without skips.
- [x] Both explicit public gates, 28 SDK and 2,077 component regressions passed.
- [x] Full offline suite, Ruff, mypy, formatting, privacy/isolation and identity checks passed.
- [x] Final four-file preservation and export are gated by the post-save records below.

Ruff across src/tests passed in 0.044s; mypy passed all 68 source files in 2.006s;
formatting passed all three final test files in 0.028s. Static command/environment/
duration/final-test-hash records are in static-results.json. All historical
fingerprints, dataset/rubric/fixture identities and both locked runtime inventories
are unchanged. No dependency, production source, existing test, tracked configuration
or resource ceiling changed. No genuine production defect was encountered.

**Isolation finding disposition: corrected for the approved cooperative boundary,
with actual locked-runtime reproduction and passing final regression evidence.**
The fixture architecture, source/controller distinction, independent custody,
prospective spending and existing assurance limitations remain unchanged. This is
not mandatory dispatch admission, real approver/reviewer/provider authority,
billing verification, live execution permission or a hostile-code sandbox.

**Recommendation: GO for independent QA confirmation of the targeted correction
and a separate publication decision.** Preserve the accepted original dirty-checkout
snapshot qualification in any publication evidence. No publication is performed here.

After this last plan save, final_validation.py must bind all fresh authoritative
results and exact final test hashes, privacy/whitespace, traceability, static checks
and four final file identities. preserve.py final must match the original external
234-file inventory in bytes/blobs/Git modes/index, exact approved parent/tree,
original checkout status/worktree identities/pinned application state, exactly four
untracked regular non-executable additions, and zero generated/ignored repository
artifacts. preservation-final.json is the post-save SHA-256 manifest, including
this plan's identity. It cannot be replaced by an earlier pre-save manifest.

The exclusive archive writer must include only those four repository-relative paths
and verify member bytes/hashes and testzip. Export the verified archive as
/Users/rebeccawilliams/Downloads/slice6f-qa-artifacts-final.zip; preserve the original
QA archive. verify_export.py must confirm exact archive/member identities and
agreement with verification-summary.json and preservation-final.json.
archive-verification.json and export-verification.json retain the final ZIP SHA-256;
handoff-manifest.json binds the final additions and selected external QA records.
The source ZIP excludes records, keys, signatures, stores, journals and caches.
Successful handoff requires every post-save gate to pass before the final response.

**STOP after verified export. No commit, push, PR, merge, live provider/target/judge/
Study activity or subsequent-slice work. Await separate publication authority.**

## PR #37 review correction — test-owned child scratch roots

The operator authorised this targeted correction after independent GitHub QA of
published head d2eb0879576636d154e1312ac79cf3ba70c63a3f, published tree
3e8188286aca8161e482071f44835a644a1edf45 and sole parent
fd515f875b51ab33b29fed3b618343f14e080678. The P2 review finding is
https://github.com/beccawillss/ai-test-harness/pull/37#discussion_r4699231328.
Only the existing four additions may change. All 234 original baseline files,
their index entries and the original checkout/application/worktrees remain
protected. No commit, push, review-thread resolution, merge or auto-merge is
authorised. This record supersedes historical publication-stage stop text only
for the expressly authorised local correction and independent QA export.

External correction evidence:
/private/tmp/canary-slice6f-pr37-correction-20261125-01.

### Reproduction and bounded correction

The published _worker, _inspector and _isolation_worker were invoked in separate
children under unset, conventional /tmp and approved-wrapper-style TMPDIR
configurations. Interception at audit installation prevented application work;
the actual unchanged audit helper tested only disposable synthetic outside-root
paths. All three entrypoints raised KeyError:'TMPDIR' when unset. All three
selected / as writable with TMPDIR=/tmp and allowed the disposable outside write.
All three selected the wrapper's parent and denied that write under the approved
layout. published-reproduction.json binds nine observations to published bytes.
No write probe targeted a real protected system or user path.

Inspection found the same ambient-parent assumption in the explicit public gate
helper. Therefore the correction also necessarily changes the existing application
test addition; the main integration module remains unchanged. The audit policy
itself is unchanged. Each process fixture provisions child-scratch/tmp, passes the
writable root explicitly, and configures TMPDIR/TEMP/TMP and tempfile's child-only
cache before temporary-file/audited operations. Synthetic signing keys are copied
into a cleanup-managed directory under that root. Inspector evidence remains an
explicit read-only root. Negative writes/descriptors target disposable siblings,
outside the approved writable root. Every child exercises actual temporary-file
success and outside-write denial after installing the audit.

The existing successful linked lifecycle, consume/execute interruption and
37-probe isolation regression are additionally parameterised over unset, /tmp
and wrapper-style ambient TMPDIR. Parent environment changes use monkeypatch
restoration; child configuration cannot change the parent's tempfile cache.
Existing relative/absolute/descriptor, SQLite, Git, SSH, credential and network
policy checks, positive barriers, monotonic deadlines and bounded cleanup remain.

### Frozen test bytes and actual fresh results

Final test-byte freeze, unchanged throughout every authoritative command:

- tests/test_canary_integration_v3.py: 0b6705c44876ca071b752141b92d4902e91fcf527bb1d1f708692be2b0966812 (51,148 bytes).
- tests/test_canary_integration_v3_application.py: 9be1557a5ec66cd16f4decd636615f97cfa5fb3b90909b400e1e713aeda23af2 (17,298 bytes).
- tests/test_canary_integration_v3_faults.py: 3dea0f5d238a47c35f39be788e4532a3776b8d4905732fe36224b0910d2bcb04 (48,014 bytes).

| Check | Actual result | Wrapper duration | Ambient TMPDIR |
| --- | --- | ---: | --- |
| portability-final | 13 passed, 0 skipped | 51.392s | unset |
| core-final | 52 passed, 0 skipped | 167.109s | unset |
| source-final | 1 passed, 0 skipped | 2.625s | unset |
| controller-final | 1 passed, 0 skipped | 17.999s | unset |
| source-system-final | 1 passed, 0 skipped | 3.064s | system |
| controller-system-final | 1 passed, 0 skipped | 23.615s | system |
| source-wrapper-final | 1 passed, 0 skipped | 3.642s | wrapper |
| controller-wrapper-final | 1 passed, 0 skipped | 23.306s | wrapper |
| sdk-final | 28 passed, 0 skipped | 26.324s | unset |
| envelope-serial-final | 1 passed, 0 skipped | 6.664s | unset |
| regression-serial-final | 2077 passed, 1 skipped | 667.578s | unset |
| full-final | 4880 passed, 8 skipped | 1029.580s | unset |

All 32 approved scenario groups pass. The 52-test core retains all original 44
cases and adds eight parameterised portability cases: consume/completed
interruption (2 to 6), complete isolated workflow (1 to 3), and the existing
37-probe regression (1 to 3). Each probe set has all 37 denials and legitimate
filesystem/SQLite/Git positives. Fresh inspection remains read-only and snapshot
identical after explicit write-denial checks. All eleven interruption variants
(including parameterisation), race barriers and bounded teardown pass.

Both explicit public gates passed independently under all three ambient
configurations, with actual source verification and actual public pinned
controller .run(). Child records identify the fixture root and its tmp directory;
every affected worker/inspector asserts temporary-file success inside that root
and outside-root write denial. Keys copied into the root are removed by fixture
teardown, including failure paths. Parent environment patches are restored and
the parent's tempfile cache is unchanged. No private controller substitution,
assertion weakening, production/dependency change or ceiling/deadline increase.

Ruff passed (0.070s), mypy passed all 68 source files
(0.206s), and formatting passed all three test files
(0.030s). All historical definition, dataset,
rubric and pinned fixture identities passed. Both locked runtime inventories are
byte-identical to the approved inventories: harness CPython 3.12.13 and application
CPython 3.13.15 with pinned OpenAI 3.3.1. No dependencies were installed.

The only full-suite exclusion remains tests/test_canary_controller.py. The eight
optional skips are the same historical controller_v3_application,
instrumentation_v3_sdk, canary_sdk, selection_state, canary_state and runtime_v3
pinned-worker opt-ins, plus the two default-disabled Slice 6f gates. Both new gates
and the SDK modules passed separately with explicit opt-ins in the pinned runtime.
The component skip is the historical runtime_v3 complete-source-worker opt-in.
These unexecuted historical opt-ins are not reported as passing.

### Retained failed attempt and remaining limitations

The initial component run overlapped the full run and returned 2,076 passed,
one optional skip and one failure in 697.014s wrapper time. The unchanged
test_canary_envelope_v3.py::TestInspectionLimits::test_legitimate_bounded_fixtures_fit[maximum]
raised provider_boundary_stopped_preserve_evidence during dispatch. Its existing
boundary suppresses the underlying exception, so the cause is not established;
concurrency/timing is not asserted as the cause. This failure is retained in
component-initial-failure.json and regression-final command/result/JUnit/log files,
and is excluded from successful acceptance. No file/assertion/ceiling was changed
in response. The same fixture subsequently passed within full-final (6.502s),
in an isolated check (5.975s), and in the complete serial component rerun. The
successful serial component run and successful full run are the authoritative
broad verification results for the same frozen final bytes.

The core maximum driver still actually completed 24 calls/72 attempts with 222
records, 266,235 source bytes, 5,680 envelope bytes, packet/presentation
22,823/26,495 bytes and a 24,576-byte register DB, in 13.875s. Three isolated
workflows observed native macOS RSS 79,380,480 / 77,594,624 / 77,512,704 bytes,
zero pre-probe network events, twelve actual synthetic SSH operations each and
one denied DNS probe each. These are fixture observations, not hard guarantees.
All production ceilings, crypto/SQLite timeouts and test deadlines remain unchanged.

The audit policy and deadline/cleanup functions are AST-identical to the published
versions. All original assert nodes and pytest.raises expectations are retained;
assertion-preservation.json binds that comparison to final test hashes. Fresh
collection contains 54 nodes (52 core and two optional gates); all 52 core nodes
also pass in the full run. scenario-traceability.json covers all 32 groups, and
portability-isolation-traceability.json binds the three actual probe/workflow
observations. The external extractor excludes pytest's current-directory symlink
aliases, so each child is counted once. Every final command/result records the
frozen test hashes; verification-summary.json binds the evidence hashes.

Trusted imports/fixture/key/local-Git preparation precede audit installation.
The cooperative audit still trusts Python, OS/tooling and native subprocess
internals. It establishes neither general native/SQL/subprocess confinement nor
mandatory admission, external readiness, billing truth, real reviewer identity,
distributed single use or permission for live inference or Study execution.
All three existing execution-path and independent-custody limitations remain.

Only three existing additions changed: this plan, the fault module and the explicit
gate module. The main integration module retains its published bytes. All 234
original baseline files retain bytes/blobs/modes/index entries; HEAD and the full
238-file index remain unchanged at the published commit. The original development
checkout, pinned app and other worktrees are preserved. The accepted qualification
remains: the first byte inventory was acquired after M0, so subsequent byte/time
comparisons do not establish a pre-M0 byte comparison.

**Review finding disposition: corrected locally, with passing portability and
full verification; GO for independent QA of the corrected artifacts.** The review
thread is left unresolved. The unexplained initial historical-test failure is
disclosed above for independent assessment. Commit/push/merge remain unauthorised.

### Post-save independent QA artifact gate

After the final plan save, a new external post-save preservation manifest must
bind all four artifacts, 234 protected baseline blobs/modes/bytes/index entries,
unchanged published HEAD/index, original checkout and pinned application state.
Export only the four reviewed additions to
/Users/rebeccawilliams/Downloads/slice6f-qa-artifacts-pr37-correction.zip, verifying
archive/member hashes and contents. Retain the prior archives unchanged.

STOP before committing or pushing. Await independent corrected-artifact QA and
separate follow-up commit authority. No review-thread resolution, merge, live
provider/target/judge/Study work or subsequent architecture work is authorised.
