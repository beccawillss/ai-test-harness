# Milestone C1 — bounded non-Study canary tooling

Current authorisation — 2026-11-07: final review and offline checks, followed by
commit of exactly these eight new files, branch push and a PR against `main` if
the checks pass. No merge, live requests, server startup, Study capture/freeze,
paid credential configuration, dependency installation or dataset changes.
This supersedes the implementation-stage prohibition on commit/push/PR work;
the implementation-stage evidence below remains historical.

Implementation worktree: `/private/tmp/ai-test-harness-study-v1-c1`, branch
`feat/study-v1-canary-c1`, based on approved harness
`ecb3367cad5c059af76fc6e3fa20c961290ef9d0`. Approved execution worktrees remain
detached and clean. Application revision remains
`3320e556540d3f95bee1e8509f13e558ce266b6c`.

Scope agreed before implementation:

- Add opt-in canary inputs, driver and metadata transport beside existing APIs.
- Preserve A1/B1/A2/B2 and J1–J8 twice. Never judge target canary responses.
- Reuse semantic v5 preparation, anchor parser and HTTP adapter for offline replay.
- Require all eight human ratings before constructing a judge; persist reservations
  before dispatch; stop on infrastructure/recording failures. No resumption/replay
  of ambiguous paid calls. Retain SDK retry configuration, bound attempts.
- Inject all transports explicitly; offline mode accepts only replay/mock I/O.
- Keep outputs in a private `salesagent-preflight-canary` namespace outside Git
  and Study stores. Persist only allowlisted metadata and public target evidence.
- No changes to existing runner, adapters, application, datasets or methodology.
- Test both transport accounting and actual installed SDK with scripted HTTP;
  compare instrumented/uninstrumented application requests and public evidence.

Progress:

- [x] Read repository guidance and inspect client, adapter and capture interfaces.
- [x] Record original checkout content/status baselines; check execution pins.
- [x] Create isolated branch/worktree from approved harness revision.
- [x] Implement canary inputs, private recording, bounded driver and tests.
- [x] Focused/full checks, semantics comparison and protected-workspace checks.
- [x] Document limitations; implementation ready for human review.

Verification completed:

- 66 focused offline tests passed using the existing application environment,
  including OpenAI SDK 3.3.1 / httpx 0.28.1 and the real assembled application
  with scripted model HTTP. All 12 provider request-body hashes and normalized
  public evidence match uninstrumented execution (generated IDs/timing excluded).
- Final full harness suite: 2,501 passed, one optional installed-SDK module
  skipped in the harness environment. The three SDK/application tests passed
  separately in the application environment, including after the final test-log
  redaction change. Full unchanged application suite: 274 passed.
- Repository Ruff check passed; all six added Python files pass formatting.
  Mypy passed for all 45 source files. No dependencies installed.
- No existing tracked harness files differ from the approved base; only eight
  scoped files were added. Original checkout source/test/docs/data content hashes
  and working-tree statuses match their pre-implementation baselines.
- Both execution worktrees remain detached, clean and at their approved commits.
  Offline dataset reload confirms 50 cases / 71 turns and fingerprint
  `4a0e40d6dce4b78cc194352bf23d69dabcc8fe3c0f440d50f2cce2bd6a956028`.
- Application fixtures remain products SHA-256
  `70960848556e1e63c1bd3337203ab057a9fae1e7f6d343fb383f85a838c541ab`
  and promotions SHA-256
  `3147b6863b9458c928459cbb824d01b0e3b73aa2c5da2979debb78de4e1caf0c`.

No broader capture reliability changes, server startup, live inference, actual
Study capture/freeze, commit, push, merge or integration were performed. All
generated test evidence/ratings are explicitly synthetic and outside Study stores.
The runbook is `docs/salesagent-canary-c1.md`. New code remains opt-in and
uncommitted. No material deviation from the authorised C1 scope.

Known limits: provider usage may be missing, retries may incur unknown charges,
cache-write retention affects pricing and project spend enforcement can lag.
Estimates are not invoices. Offline tests cannot establish live judge accuracy.

## Final review and PR preparation — 2026-11-07

Reviewed all eight files against the C1 acceptance criteria. No production code
correction was required. Only this plan and the handoff documentation were
updated for the new publication authorisation. The tooling has no import from
existing default execution paths and no Study case/contract/store integration.
GitHub confirms `main` is still exactly the approved base revision.

The human receipt is verified before judge construction, each dispatch and
result reveal. It binds all eight valid human anchors/reasons, the roster hash,
reviewer and explicit `not_seen` declaration. The owning account remains trusted;
the receipt is a workflow integrity check, not authentication of a human action.
Provider persistence is limited to allowlisted numeric/status/identifier fields;
SDK instructions, request bodies/credentials, provider reasoning items, raw
provider envelopes and exception text do not enter telemetry artifacts. Public
target replies and concise judge justifications remain intentional evidence.

The full harness environment deliberately lacks optional OpenAI SDK/application
packages. Consequently `tests/test_canary_sdk.py` is skipped at collection there.
The same module executes all three tests in the existing application environment,
using SDK 3.3.1 and scripted in-memory HTTP. This is not a live compatibility or
grading-accuracy result. Test network access is blocked by the default fixture.

Final review re-runs: 66 focused tests passed (including all three installed-SDK
tests), 2,501 full harness tests passed with the explained SDK-module skip, and
274 unchanged application tests passed. Repository Ruff checks, formatting of
all six added Python files and mypy on all 45 source files passed.
The approved execution worktrees and original checkout statuses/content hashes
remain unchanged. Dataset and fixture fingerprint verification is repeated before
publication. Only the eight reported additions may enter the commit.
