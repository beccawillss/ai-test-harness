# Study v1 C3a — controlled canary preparation

Current authorisation — final verification and PR preparation, 2026-11-08:
offline review/checks, one scoped commit, branch push and a PR against `main`.
No merge, live server, paid project setup, real credential access, actual canary,
model call, Study execution or freeze. This supersedes only the initial prohibition
on committing/pushing/opening a PR; the preparation record below is historical.

Authorised 2026-11-08: offline setup, minimal controller development and synthetic
verification only. No paid calls, real canary inference, semantic judging, Study
execution, freezes, credential access, project configuration, commit, push or merge.

Base: `d43a568168363d2dc4073636a7c8127752afc2c1`; application:
`3320e556540d3f95bee1e8509f13e558ce266b6c`. Dedicated branch/worktree:
`feat/study-v1-c3a-canary-preparation`, `/private/tmp/ai-test-harness-study-v1-c3a`.
Previous execution worktrees and original checkouts are preserved.
New clean detached execution worktree:
`/private/tmp/study-v1-c3a-execution/harness` at the same approved revision.
It remains clean; the proposed source patch exists only in the implementation
worktree and needs human approval before use for live execution.

Implementation follows C1 transport/client/driver APIs and leaves C2 and the
Sales Agent unchanged. The controller owns one loopback Uvicorn worker, explicit
provider transport, SDK and deterministic shutdown. Live startup requires a
separate, fresh operator attestation and explicit in-memory credential; there is
no live CLI, environment credential lookup or judge entry point in the controller.
Attestations record human checks; they cannot independently prove remote billing
enforcement. Human preparation uses the existing C1 receipt format.

- [x] Inspect C1/C2 and create dedicated worktree at approved base.
- [x] Build separate environments from the two committed lockfiles.
- [x] Verify dataset, fixtures, actual imported runtime identities and dependencies.
- [x] Implement lifecycle, pause/stop checks and readable human packet.
- [x] Verify synthetic startup/shutdown, failure controls and C1/C2 compatibility.
- [x] Publish local evidence, operational checklist, blockers and exact file list.

Use the harness environment for the default suite and the worker environment for
installed-SDK/application tests. Application source is supplied through PYTHONPATH;
it is never edited or installed over an original environment. The worker environment
is synchronized to hash-checked requirements exported from the application lock;
the harness environment is synchronized with `uv sync --locked`. Shared runtime
dependencies differ between lockfiles, so environments remain separate.

This is a living implementation record. Final evidence and deviations follow here.

## Verification and handoff — 2026-11-08

| Check | Result |
| --- | --- |
| Full default harness pytest | **2,631 passed, 2 skipped**, 139.15 seconds |
| C1/preparation/C2 journal/execution-control focused pytest | **193 passed**, 23.89 seconds |
| Worker-lock controller/SDK/preparation/C1 pytest | **97 passed**, 9.88 seconds |
| Final formatted-source startup/shutdown and byte comparison | **1 passed**, 1.21 seconds |
| Repository Ruff check | Passed |
| Six changed Python files: Ruff formatting | Passed |
| Mypy | Passed, all 51 source files |
| Git whitespace check | Passed |

Commands run in the implementation worktree:

```sh
.venv/bin/python -m pytest -q --tb=short
.venv/bin/python -m pytest tests/test_canary_preparation.py tests/test_canary.py tests/test_study_journal.py tests/test_execution_control.py -q --tb=short
PYTHONPATH=src:/Users/rebeccawilliams/Developer/study-v1-local/sales-agent/src .venv-worker/bin/python -m pytest tests/test_canary_controller.py tests/test_canary_sdk.py tests/test_canary_preparation.py tests/test_canary.py -q --tb=short --basetemp=/private/tmp/study-v1-c3a-review-20261108/synthetic-tests-final
PYTHONPATH=src:/Users/rebeccawilliams/Developer/study-v1-local/sales-agent/src .venv-worker/bin/python -m pytest tests/test_canary_controller.py::test_full_worker_lifecycle_uses_synthetic_provider_only -q --tb=short --basetemp=/private/tmp/study-v1-c3a-review-20261108/lifecycle-evidence-final
.venv/bin/ruff check src tests
.venv/bin/mypy src
git diff --check
```

The two default-suite skips are the optional installed-SDK and controller modules;
both ran in the worker environment. External sockets/DNS are blocked throughout
these tests; lifecycle tests permit literal 127.0.0.1 only. The real application
and SDK consumed scripted responses, never a model. C1 roster, request ceilings,
prompt hashes, retry behavior and human gating remain compatible. C2 journal,
execution-control and runner tests pass without changes to those interfaces.

Private review root: `/private/tmp/study-v1-c3a-review-20261108`.
Final startup/shutdown evidence is under
`lifecycle-evidence-final/test_full_worker_lifecycle_use0/salesagent-preflight-canary/lifecycle`.
It includes runtime identity/source hashes, startup, shutdown, target completion,
exclusive reservations, public synthetic exchanges and all 12 provider dispatch /
usage records. The retained uninstrumented baseline allows public comparison;
the test compared every provider request-body hash without printing prompt bytes.
Observed provider calls per slot: A1=4, B1=1, A2=3, B2=4. Four shopper POSTs,
ten GETs, two isolated sessions, no judge stage, zero unknown usage, USD 0.0132
estimated over synthetic usage. Worker/SDK shut down; this represents no charge.

Final human packet:
`salesagent-preflight-canary/packet-for-beccawillss-readable/human-packet.md`,
with complete JSON evidence and `human-draft.json` alongside it. Eight blank
ratings, reviewer `beccawillss`, exposure `unknown`, no human receipt and no judge
results. Separate test-only dummy annotations are never reviewer approval.

Initial local-server tests failed because the sandbox denied bind; reruns needed
the narrow loopback test approval and continued to block external connections.
Development also caught two test-only issues: decimal formatting in an assertion
and a missing JSON content-type in the uninstrumented comparison bridge. Both
were corrected; the final 97 tests and retained lifecycle proof passed. Earlier
synthetic failure artifacts are preserved separately, not silently overwritten.

No material scope deviation. Minimal changes remain confined to C1 canary tooling,
tests and documentation; the application and all C2/core/dataset/judge contracts
are unchanged. The separate environments resolve differing committed lock pins.
The new clean execution worktree was kept separate from the uncommitted patch.
No production artifact root or project control is inferred from temporary paths.
No live inference, actual Study execution/freeze, credential lookup/project edits,
commit, push or merge. Human review and every live approval listed in the handoff
remain outstanding.

## Final publication review — 2026-11-08

The exact eight-file inventory was rechecked against the approved base; no
out-of-scope paths are included. GitHub `main` was confirmed at that same base.
Source review found one publication issue: exact HEAD equality would reject the
controller immediately after its authorised commit. The C3a runtime check now
requires approved-base ancestry, allows differences/untracked paths only in the
same eight-file C3a inventory, and records both the approved base and actual HEAD.
Tests use a local synthetic Git repository to verify committed-patch acceptance
and rejection of unrelated tracked/untracked changes. This changes no C1 roster,
provider/judge setting, dataset binding, application or C2 contract.

Provider/log redaction was checked with synthetic key, input, hidden-instruction,
reasoning and error-body sentinels. Only allowlisted metadata persists; ordinary
INFO logs contain none of those sentinels and DEBUG logging blocks dispatch.
Project/org headers are verified in scripted installed-SDK execution. Live
project association and spending-limit verification remain human attestations,
not authenticated remote checks or authority inferred from this PR.

Final offline verification results and publication evidence are recorded below
before committing. Previous human packet, ratings state and historical artifacts
are preserved; no test-only ratings count as independent human approval.

Final publication checks (2026-11-08):

| Check | Result |
| --- | --- |
| Full offline regression | **2,634 passed, 2 optional skips**, 134.35 seconds |
| Focused C1/C2/preparation checks | **196 passed**, 22.03 seconds |
| Worker-lock controller/C1/preparation/SDK checks | **100 passed, zero skips**, 10.44 seconds |
| Installed SDK tests within that worker run | **All three passed** |
| Repository Ruff | Passed |
| Changed Python formatting | Passed, six files |
| Mypy | Passed, all 51 source files |
| Whitespace and scoped secret-pattern scan | Passed; zero secret-pattern matches |
| Exact inventory | Eight approved files, no other paths |
| Dataset/fixture/roster bindings | All approved fingerprints unchanged |

The two skips explicitly report missing `openai` in the harness-only environment:
`tests/test_canary_sdk.py` and `tests/test_canary_controller.py`. Both modules
executed in `.venv-worker`, with pinned OpenAI SDK 3.3.1 and Sales Agent source.
External sockets remain blocked; only synthetic lifecycle tests allow literal
127.0.0.1. No live server or real provider is used. Lifecycle evidence still
shows exactly A1/B1/A2/B2, 4 POSTs / 10 GETs, 12 scripted attempts, isolated sessions
and a closed worker/SDK. Target ceilings remain 24 logical / 72 HTTP attempts;
the separately gated future judge maximum remains 16 attempts. No replacements.

Final-review evidence is separate from the original preparation evidence:
`/private/tmp/study-v1-c3a-pr-review-20261108`. Private JUnit reports are
`full-harness.xml` and `focused-worker.xml`; synthetic lifecycle evidence is under
`synthetic-tests/test_full_worker_lifecycle_use0/salesagent-preflight-canary/lifecycle`.
The final commit/PR identity and committed-source smoke results are recorded in
the PR description and private final-verification JSON, avoiding a self-referential
commit SHA in this document. The approved source/pins, original human packet and
old execution checkout were rechecked without alteration. Only this scoped branch
is authorised for publication; no merge, live execution or credential action.
