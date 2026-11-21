# Canary runtime Slice 1: definition selection and source receipt matching

Scope: offline only. Base `e5638a5138a224c2602956791b87d06f8ea2c5b9`.
Worktree: `/private/tmp/ai-test-harness-canary-runtime-v3-slice1`.
Branch: `feat/canary-runtime-v3-slice1`. One local commit authorised on 2026-11-21;
push, PR creation and merge remain unauthorised. Earlier dated sections retain
their original review-stage status; they do not describe current Git permission.

## Progress

- [x] Verify remote main and approved v2.1/v3 identities; preserve other worktrees.
- [x] Prepare isolated interpreter with `uv sync --locked --offline`.
- [x] Implement immutable selection and strict, source-only receipt verification.
- [x] Add synthetic receipt, Git/worktree and blocked-network regressions.
- [x] Run focused/full locked offline suites, available worker suites and static checks.
- [x] Verify exact addition inventory and protected source/dataset identities.
- [x] Prepare results for human review; no actual source approval or live authority.

## Interfaces and trust boundary

`resolve_definition(identifier=None)` returns a deeply frozen `DefinitionBinding`.
The default is historical C1. V3 requires its exact identifier. Every resolution
recomputes approved identities; mixed/copied bindings fail `validate_binding`.
Historical C1 has no independent definition/execution fingerprint: those fields
are explicitly null, with its historical roster and assertion fingerprints bound.
The v3 storage identity reserves a namespace only; no journal schema is implemented.

`parse_receipt(model | JSON | mapping)` requires a strict, nonsecret
`SourceApprovalReceipt`. It binds the exact harness commit/tree, app commit/tree,
complete definition, both lock hashes, exact runtime, execution profile and
claimed approval reference. There is no issuer or receipt file writer.
`verify_source(receipt, harness_root=..., application_root=...)` independently
collects observations and returns `SourceVerification`, or a fixed diagnostic
`SourceError`. It does not accept an injected observer or policy function.
The receipt's `provenance` and approval reference are unauthenticated claims.
The result exposes `claimed_provenance`, so even `"external-review"` cannot be
mistaken for verified approval. `source_matches_receipt=True` reports matching
source observations only. Both `source_authorised` and
`authorises_live_execution` are fixed `Literal[False]` fields. Slice 1 has no path
to source authorisation, regardless of receipt provenance or a matching digest.

The receipt digest binds its contents, including any provenance claim; it does
not authenticate the claim or its author. Source authorisation remains unavailable
until a separately reviewed authentication mechanism exists. A trusted-channel
assumption is not an implemented control and cannot set an approval flag here.
This slice implements no reviewer authentication, receipt signing, live approval,
private evidence read, credential discovery, reservation, server, worker, provider
client, dispatch or journal.

## Source checks

Read-only Git inspection checks exact root, HEAD/tree, index entries, every
tracked file's Git blob hash and executable bit, and untracked files. This catches
edits hidden by assume-unchanged/skip-worktree flags. Symlink/submodule entries
and ignored source/configuration under `src` are rejected. Git status/diff filters,
network, index refresh, fsmonitor, global config and ambient Git overrides are
avoided. All external diagnostics are suppressed.

Only already-loaded harness/application module origins are inspected; the app is
not imported. Both dependency locks are bound; installed registry versions are
checked against the selected runtime lock, using the existing POSIX exclusions.
The harness offline runtime is CPython 3.12; the worker runtime is CPython 3.13.
The two lock environments are not asserted to be interchangeable. Target-v3
source-profile matching requires v3 plus the worker runtime and still grants no
live authority. Existing C3a source verification is untouched and remains a
separate gate; the new result cannot be passed to it as an exemption.

Tests exercise clean temporary Git repositories and linked worktrees separately
from pure synthetic receipt matching. An additional optional composition test runs
the complete public verifier against a temporary harness commit and the available
pinned app, with a synthetic receipt, no source authorisation and no live authority.
The child receives no ambient credentials/configuration, denies socket activity
and SDK/app imports, and inspects the pinned checkout read-only. Default tests do
not require that external checkout; the composition test also passed separately
in the existing locked CPython 3.13 environment. No test issues actual source
approval for the implementation worktree.

## Remaining integration risks / next slices

- Source authorisation is unavailable. Future source approval requires a separately
  reviewed authentication mechanism, not an unverified receipt claim or digest.
- Filesystem checks are point-in-time, not an atomic lock or protection from a
  malicious interpreter, altered in-memory objects or poisoned bytecode caches.
  Later startup/dispatch must revalidate source/runtime under a trusted launcher.
- Later integration must validate actual worker configuration, ambient settings,
  project controls, evidence freshness and single-use live approval separately.
  App module origins must be checked again after import, before startup: this
  slice checks loaded modules and intentionally does not import the app.
- The reserved storage identity needs an independently reviewed durable journal,
  exact schema and save-only crash/recovery protocol in the next slice.
- No changes to provider attempts, budgets, retry behaviour or no-replay rules.
- No lifecycle/listening-server tests are within this approval.

## Verification results

Initial results (2026-11-17), superseded below for the trust-boundary correction:

- `uv sync --locked --offline`: succeeded; CPython 3.12.13, unchanged lockfile.
- `.venv/bin/python -B -m pytest tests/test_canary_runtime_v3.py -q --tb=short -rs`:
  **86 passed, 1 skipped** (optional CPython 3.13 composition test).
- `.venv/bin/python -B -m pytest -q --tb=short -rs --ignore=tests/test_canary_controller.py`:
  **2,996 passed, 4 skipped**, 148.62 seconds. Three skips are optional installed
  SDK/v2 state/v3 state modules; the fourth is the new optional composition test.
  The listening-server controller module is explicitly excluded, not a skip.
- Existing locked CPython 3.13 environment, with approved app source on PYTHONPATH:
  **368 passed**, no skips, across `test_canary_selection_v3.py`,
  `test_canary_execution_policy.py`, `test_canary_selection_state.py`,
  `test_canary_acceptance.py`, `test_canary_state.py`, `test_canary_sdk.py`,
  `test_canary.py`, `test_canary_preparation.py`. All provider I/O is scripted.
- Same environment, new complete-public-verifier composition test only:
  **1 passed**, no skips. No source/live approval issued.
- Final combined repeat of those 368 regressions plus the composition test with
  `env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:<approved-app>/src`:
  **369 passed**, no skips. No ambient provider configuration was present in the
  original shell either (variable names checked only, no values read).
- `ruff check src tests`: passed. `mypy src`: passed, 56 source files.
- Formatting check of both new Python files: passed.
- Repository-wide `ruff format --check src tests`: **does not pass** on two
  untouched baseline files, `src/harness/targets/base.py` and
  `tests/test_dataset.py`. Both match HEAD byte-for-byte and fail formatting
  directly from HEAD too. They were not reformatted or included in this slice.

All tracked harness source and locks remain at the approved base; the only
additions are this plan, `runtime_v3.py` and `test_canary_runtime_v3.py`. The pinned
Sales Agent remains clean at `3320e556540d3f95bee1e8509f13e558ce266b6c`.
Both approved fixture hashes match. The dataset remains 50 cases with fingerprint
`4a0e40d6dce4b78cc194352bf23d69dabcc8fe3c0f440d50f2cce2bd6a956028`.
Captured historical artifacts and private operator evidence were not accessed.

## Trust-boundary correction (2026-11-19)

Independent review found that `_check_observation()` derived source approval
directly from the unauthenticated `"external-review"` provenance string. That
behaviour was incorrect: matching source does not establish human approval.

Exact correction, limited to the same three Slice 1 files:

- `runtime_v3.py`: remove the provenance-to-authorisation expression; make
  `source_authorised` permanently `Literal[False]`; rename result metadata to
  `claimed_provenance`; clarify that the receipt reference is also a claim.
  Preserve receipt parsing, all source checks and the live-authority prohibition.
- `test_canary_runtime_v3.py`: verify a provenance-only change cannot grant
  approval, even with matching commits/trees/fixtures/locks; repeat identity
  rejection cases under both claims; reject injected authority fields and direct
  attempts to construct or mutate either authority flag to true. Exercise both
  claims through the complete public verifier in the optional locked runtime.
- This report: correct the trust boundary and record replacement verification.

Replacement verification results:

- Focused Slice 1 suite: **99 passed, 1 optional skip**, 2.46 seconds; 13 additional
  passing cases compared with the initial implementation.
- Full offline suite with `--ignore=tests/test_canary_controller.py`:
  **3,009 passed, 4 optional skips**, 147.94 seconds. Listening-server controller
  tests remain explicitly excluded. The four skips are the installed-SDK module,
  v2/v3 application-state modules and the full source-verifier composition test.
- Those optional checks were exercised in the locked application environment:
  **369 passed, no skips**, 6.10 seconds. The full source-verifier test now checks
  both `synthetic-test` and a locally forged `external-review` claim against the
  same source. Both match; both deny source approval and live authority.
- Ruff lint across `src tests`: passed. Mypy: passed, 56 source files.
- Formatting of both Slice 1 Python files: passed. Repository-wide formatting
  still flags only the two unchanged baseline files documented above.

The original temporary CPython 3.13 environment no longer contained pytest.
An attempted fresh, offline-only environment could not finish because the locked
OpenAI SDK wheel was absent from cache; no network download was permitted.
The existing environment at `<approved-app>/.venv` was then verified against the
application lock and used read-only for the 369 checks, with `env -i` and explicit
PYTHONPATH. Neither previous environment nor the application was changed.

All tracked harness bytes and the index still match the approved base; only the
three original Slice 1 additions are untracked. All five v2.1/v3 identities,
historical C1 roster/assertion identities, application revision, both lock hashes,
fixture hashes and the 50-case dataset fingerprint remain unchanged. No approved
policy, controller, source pin, dependency lock, fixture or historical capture has
been changed; credentials and private operator evidence were not accessed.

**Revised recommendation: ready for human approval of offline PR preparation.**
The PR must describe Slice 1 as source matching only, with claimed provenance and
source authorisation unavailable. Actual source approval requires a separately
reviewed authentication mechanism before future integration can rely on it.
No authentication mechanism, receipt issuer, journal or live approval is added.
No commit, push or PR creation is authorised by this correction.

Approved policy identities were independently recomputed and remain unchanged:

| Identity | Fingerprint |
| --- | --- |
| v2.1 | `3c632f6ce5e8b9eda42b4a0a0f91ccb82f4f34783da3b9638762b84351c9c2f9` |
| v3 roster | `564b98533b5b48b13d7d97fec8c150c329a6bf5d7ed38f0f165bae32a8493e17` |
| v3 definition | `e76fd0e10f1176d6aa421a2b5de93f9503dceaa422b0631c2c8f7c957aa75607` |
| v3 acceptance | `575e304da8203b537d281d82a667e73dbf419fc95caee8df82dea6e7feabfce7` |
| v3 execution | `a4d8cdaaa4960ddf406c37703965d164595cea320cfa83c0ddd40fad797fa551` |
| C1 historical roster | `e8778ce74a270e6efbe490198d01e8b9c50bcc43387a02bff5f00b42304d5794` |
| C1 assertions | `646fd93488667251a67a02d98548e1aface9353d2a4bb7594a7343d664f1aa65` |

## Local commit QA (2026-11-21)

The operator approved exactly the three additions listed below for one local
commit, based on `e5638a5138a224c2602956791b87d06f8ea2c5b9`, with message
`Add offline v3 canary definition and source verification`. This approval concerns
Git preparation only; source authorisation and live authority remain unavailable.
Runtime and regression-test content are unchanged from the reviewed correction.

Pre-commit verification completed against the approved base:

- Focused Slice 1 tests: **99 passed, 1 optional skip**, 3.70 seconds.
- Full offline suite, excluding the listening-server controller test module:
  **3,009 passed, 4 optional skips**, 150.08 seconds. Commands and exclusions are
  the same as in the correction verification above.
- Available CPython 3.13.15 environment verified against the approved application
  lock, with no ambient configuration: **369 passed, no skips**, 6.58 seconds.
  This run covers all optional exclusions from the default suite, including both
  provenance claims through the complete public source verifier.
- Ruff lint across `src tests`, mypy across 56 source files and changed-file
  formatting: passed. Repository-wide formatting still flags only
  `src/harness/targets/base.py` and `tests/test_dataset.py`, both unchanged from
  the approved base. Neither is included in the commit.
- Approved v2.1/v3 fingerprints, historical C1 identities, Sales Agent revision,
  fixtures, locks and 50-case dataset bindings were recomputed and are unchanged.
- The reviewed runtime and test files are unchanged. Only this plan's dated QA
  record and local-commit permission wording were updated for preparation.

The commit scope is exactly `src/harness/canary/runtime_v3.py`,
`tests/test_canary_runtime_v3.py` and this plan. Git staged-inventory, byte equality
and whitespace checks are required before creating the commit. No credential,
private evidence, capture, generated output or unrelated file is in this scope.
The local commit is unsigned and hooks are disabled to avoid signing-credential
access or unrequested hook execution. The review packet, complete patch and
proposed PR description stay outside the repository. Commit SHA and final staged
check results belong in that packet, avoiding a self-referential source revision.

Publication remains pending human review. No live compatibility has been tested
by this slice. Source authorisation still requires a separately reviewed
authentication mechanism, and Slice 2 still requires its durable journal and
save-only recovery review. Neither authority nor journal integration is added.

## Proposed review/publication scope

One independently reviewable change containing exactly these three additions;
proposed title: **Add offline canary definition bindings and source verification**.
No controller, approved policy, lockfile, Sales Agent, Study or historical artifact
changes. The local commit is authorised; PR publication and any subsequent slice
require separate approval. Future source receipt must name the exact reviewed integration commit
and tree externally; no future self-referential SHA is embedded in this code.
