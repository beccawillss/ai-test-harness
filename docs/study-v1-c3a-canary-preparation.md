# C3a controlled live canary preparation — human review handoff

Prepared 2026-11-08. **Offline preparation only. No live approval exists.** No
credentials or paid-project settings were accessed. No live provider requests,
real canary inference, semantic model judging, Study cases or freeze commands
were run. The final review authorises a scoped commit, push and PR against `main`;
it grants no merge or live execution authority.

## Worktrees and environment

Clean detached execution worktree:
`/private/tmp/study-v1-c3a-execution/harness`, pinned to
`d43a568168363d2dc4073636a7c8127752afc2c1`.

Implementation worktree:
`/private/tmp/ai-test-harness-study-v1-c3a`, branch
`feat/study-v1-c3a-canary-preparation`, based on that revision plus the eight files below.
The clean execution worktree does not yet contain this proposed controller patch.
Live use requires explicit approval of its source location and reviewed patch
hashes (or a later separately authorised source revision); no promotion is implied.

Previous pinned worktree `/Users/rebeccawilliams/Developer/study-v1-local/harness`
remains detached at `ecb3367cad5c059af76fc6e3fa20c961290ef9d0`. The Sales Agent
remains clean at `3320e556540d3f95bee1e8509f13e558ce266b6c`; its checkout and
all original checkouts were preserved.

Python 3.13.15. Both new harness environments use committed `uv.lock` through
`uv sync --locked --offline --python 3.13`. The implementation's `.venv-worker`
uses hash-checked requirements exported with `uv export --locked` from the
unchanged application lock, including its test tools. The two locks have
different shared dependency pins, so they use separate environments. Application
source is imported from its pinned checkout through explicit `PYTHONPATH`.
Dependencies were downloaded only after the environment-specific tool approvals;
original environments and lockfiles were not changed. Uv emitted a build-backend
version warning when building the harness; runtime/test dependencies remained
locked and checks passed. No new project dependencies or lockfile edits.

Revalidated without invoking any dataset cases:

| Input | Verified identity |
| --- | --- |
| Dataset | 50 cases, 71 turns |
| Dataset fingerprint | `4a0e40d6dce4b78cc194352bf23d69dabcc8fe3c0f440d50f2cce2bd6a956028` |
| products.json SHA-256 | `70960848556e1e63c1bd3337203ab057a9fae1e7f6d343fb383f85a838c541ab` |
| discounts.json SHA-256 | `3147b6863b9458c928459cbb824d01b0e3b73aa2c5da2979debb78de4e1caf0c` |
| C1 roster SHA-256 | `e8778ce74a270e6efbe490198d01e8b9c50bcc43387a02bff5f00b42304d5794` |

## Exact changed-file list

1. `src/harness/canary/controller.py` — opt-in single-worker lifecycle, runtime
   identity/lock/fixture checks, literal loopback transport, fresh live attestation.
2. `src/harness/canary/human.py` — readable packet, saved-draft acceptance and
   receipt-only verification CLI; a reopened human view cannot reserve requests.
3. `src/harness/canary/driver.py` — explicitly accepts the controller-owned local
   transport, bound to the same exclusive store.
4. `src/harness/canary/recording.py` — checks private storage identity/permissions
   before writes/dispatch; terminal operator pause/stop controls.
5. `tests/test_canary_controller.py` — installed SDK/application lifecycle and
   failure tests with scripted provider responses and external sockets blocked.
6. `tests/test_canary_preparation.py` — packet, independent-rating gates, private
   permissions, storage replacement and operator-control regressions.
7. `docs/plans/study-v1-c3a-canary-preparation.md` — living execution record.
8. `docs/study-v1-c3a-canary-preparation.md` — this handoff and proposed checklist.

The application, runner, target adapter, C2 journal/contracts, datasets, judge
adapter, semantic rubric, prepared prompts and inference settings are unchanged.
Private generated artifacts and environments are outside this source change list.

## Controller contract and offline verification

Importing the controller performs no I/O. Explicit construction verifies the
source/import identities, dataset and fixtures, installed application lockfile
versions and Python version before constructing a provider SDK. Ambient
`OPENAI_`/`SALESAGENT_` variables are rejected by name without reading their values.
This also prevents the application's import-time default app from consuming
ambient credentials. Runtime identity is rechecked before binding the worker.
The harness check requires ancestry from the approved base, rejects source changes
outside the eight C3a paths and records both base and actual HEAD, including after
the scoped C3a commit. Source hashes still need separate approval for live use.

One Uvicorn worker runs in the controller process on a pre-bound IPv4
`127.0.0.1` socket with an ephemeral port, no reload and no access logging.
Startup alone sends zero target requests. Explicit `run_target()` uses C1's
unchanged driver and bounded provider client. The transport only reaches this
controller's loopback endpoint; offline construction requires a scripted provider
and the fixed dummy key. Provider credentials are never discovered automatically.

Target settings remain `gpt-5.6-terra`, low reasoning, 2,000 output tokens,
30-second SDK timeout, two SDK retries and the application's existing tools/loop.
The controller preserves provider body bytes; the synthetic lifecycle compares
all 12 request-body hashes with an uninstrumented application baseline. No raw
provider request bodies, instructions, authorization headers or reasoning are saved.

| Boundary | Unchanged ceiling |
| --- | --- |
| Shopper POSTs | 4: A1 / B1 / A2 / B2, serial, no retry |
| Local GETs | 10: health, schema, two trace reads per turn |
| Target logical calls | 6 per turn; 24 total |
| Target outbound attempts | 3 per logical call; 72 total |
| Judge stage | Separate approval; 16 calls maximum, one attempt each |
| Combined maximum after both approvals | 88 provider attempts |
| Diagnostic / variance / replacement allowance | Zero |

Successful synthetic evidence shows four shopper POSTs, ten GETs and 12 scripted
provider attempts (4/1/3/4 by slot), isolated A/B sessions, complete usage telemetry,
estimated synthetic cost USD 0.0132, and a closed SDK/listener/worker. This is an
estimate over invented usage, not a charge or a real-world cost forecast.
Tests cover startup without requests, bind/publication failure, stop-record failure,
interruption, in-flight stop, incomplete replies, missing usage, timeouts, ceiling
violations, spending guards and no replacement calls. No judge model is used;
pre-existing judge-contract tests use deterministic scripted outputs only.

The full default harness suite, focused C1/C2 checks, optional installed-runtime
tests, Ruff and mypy results are recorded in the living plan and private review
summary. Optional SDK/controller modules skip in the harness-only environment
and execute in the application-lock worker environment. Actual local socket tests
needed the sandbox's loopback permission; they still explicitly reject external
DNS/connections. C2's identifiers and durable-capture behavior remain unchanged.

Results: full default **2,631 passed / 2 optional skips**; focused C1/C2 **193
passed**; worker-lock C1/controller checks **97 passed**; final retained lifecycle
proof **1 passed**. Ruff, formatting, mypy (51 source files) and whitespace checks
passed. The private summary is
`/private/tmp/study-v1-c3a-review-20261108/review-summary.json`.
Final lifecycle evidence:
`/private/tmp/study-v1-c3a-review-20261108/lifecycle-evidence-final/test_full_worker_lifecycle_use0/salesagent-preflight-canary/lifecycle`.

Final publication review on 2026-11-08 revalidated the same eight-file scope and
fixed committed-revision acceptance in the runtime source gate. Additional tests
cover the scoped committed revision, unrelated source rejection, INFO-log
redaction and explicit SDK project/org headers. Final results: **2,634 passed /
2 optional skips** for full offline regression; **196 passed** for focused C1/C2;
**100 passed / zero skips** in the installed-worker environment, including all
three installed-SDK compatibility tests. Ruff, formatting, mypy and scoped
secret/whitespace checks pass. Both optional skips are caused by the intentionally
absent SDK in the harness-only environment; those modules execute in the worker.
Private final-review reports/evidence are in
`/private/tmp/study-v1-c3a-pr-review-20261108`; the initial preparation evidence
and blank human packet above are preserved. Publication remains separate from
live authorisation; actual project/credential/billing behavior is unverified.

## Required manual project setup — not performed

After separate approval to configure the paid account, an authorised owner must:

1. Create/select a dedicated canary project, separate from production and Study
   execution. Record its organization/project IDs and current usage; exclude all
   other callers during the canary.
2. In that project's Limits → Spend settings set USD 10 monthly and enable
   **Enforce a hard limit**, save and reopen to verify. Configure operator alerts
   at USD 5 and USD 8; verify recipient access. Alerts alone do not block traffic.
   Record the existing spend and confirm sufficient remaining allowance. Limits
   propagate with delay, so some overshoot remains possible. If hard enforcement
   is unavailable or cannot be verified, live execution stays blocked. See the
   official [spend-limit guide](https://developers.openai.com/api/docs/guides/spend-limits).
3. After separate credential approval, create/select a restricted project-owned
   service-account key with only the needed Responses access. Verify the owner
   and project association in project settings. An authorised administrator can
   also inspect the [project API-key metadata](https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/projects/subresources/api_keys/methods/retrieve).
   Do not use a model request as a credential test. Explicit project/org headers
   express the intended billing context but do not independently prove key ownership.
4. Keep the key in an approved secret mechanism and pass it directly in memory
   only after live approval. No key in shell arguments, environment configuration,
   source, logs, screenshots or this review packet. Redact key values/prefixes;
   record only non-secret project/owner verification evidence and its SHA-256.
5. Verify the project's model permissions and Responses access for the exact
   target model. Public documentation lists [gpt-5.6-terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra)
   and [gpt-6.1-terra](https://developers.openai.com/api/docs/models/gpt-6.1-terra),
   but cannot establish this project's entitlement. Do not substitute models.
6. Recheck [current pricing](https://developers.openai.com/api/docs/pricing) at
   execution time, including service tier, cache writes, long context and region.
   C1 assumes standard USD per million tokens: target 2 input / 0.20 cache read /
   12 output; judge 1 / 0.05 / 5; 30-minute writes at 1.25× input. The published
   target model and judge pricing pages match those base rates on 2026-11-08.
   Any mismatch blocks execution until reviewed; today's public docs are not
   an execution-time price or account-availability attestation.

`LiveReadiness` requires all seven external checks, an explicit authorisation
reference, non-secret project/org IDs, evidence hash and a timestamp no more than
one hour old. Startup and target dispatch check freshness. These are human
attestations, not automated remote billing verification or authority to make calls.
All live readiness and project controls are presently **unverified**.

## Proposed final target-canary execution checklist — approval required

- [ ] Review and approve this patch, source location/digests, exact pins, provider
  settings, artifact location and target-only request/budget envelope.
- [ ] Separately authorise project configuration and credential access; complete
  the manual steps above and retain redacted verification evidence.
- [ ] Approve a private durable artifact root outside Git and Study namespaces.
  Temp evidence is not production storage or an approved backup arrangement.
  Confirm owner-only 0700 directories/0600 files, available disk, encryption and
  backup/recovery choices. No production C2 registry is created for a canary.
- [ ] Recheck runtime identity, both source pins, dataset fingerprint, fixtures,
  actual imports, Python and the unchanged committed lockfiles. Compare controller
  source hashes with the reviewed packet; no additional patch is implied approved.
- [ ] Record fresh model/project/pricing checks. Disable SDK/HTTP debug logging;
  keep proxy/environment trust and redirects disabled. No tracing of raw SDK data.
- [ ] Obtain explicit approval for **target canary only**. Do not invoke a judge,
  Study runner or freeze. Start one local worker and verify its private lifecycle
  record; C1 itself performs exactly the health/schema GETs in its allowance.
- [ ] Execute exactly A1/B1/A2/B2 once. No manual shopper probes, diagnostic calls,
  replacements, automatic restarts, alternate model or changed token/retry settings.
- [ ] Observe reservations, allowlisted telemetry and the USD 5 local guard.
  Review B1 prose for truthful fresh-session behavior, A2 retention/discount and
  B2 independence alongside the deterministic checks.
- [ ] Shut down the worker and SDK; verify shutdown evidence, roster counts,
  session separation, accounting and provider project billing. Preserve all
  reservations and partial evidence even if no request appears to have completed.
- [ ] Stop for human review. Judge execution and any Study operation need their
  own later explicit approval, independently of target-canary success.

## Pause, stop, incomplete requests and billing

`request_operator_stop(store, pause=True)` publishes an owner-only pause record;
`pause=False` publishes a stop record. An operator in a separate terminal can
create the same marker without reopening/resuming the controller:

```python
import os
from pathlib import Path
run = Path("<approved-canary-run-directory>")
fd = os.open(run / "operator-pause.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
os.write(fd, b'{"requested":true,"automatic_resume":false}\n')
os.fsync(fd)
os.close(fd)
# Use operator-stop.json for stop. Neither marker has a resume command.
```

Markers are checked before every local request, logical call and provider
attempt, including SDK retries. Both actions terminate the run's dispatch
authority. They cannot recall an already dispatched request or guarantee billing
cancellation. Ctrl-C exits the controller context and stops subsequent dispatch.
Normal shutdown waits for the worker; unresolved worker/provider activity is
reported as incomplete shutdown, never as successful completion.

Timeouts, incomplete/malformed provider replies, storage errors and interruptions
stop the run. Missing usage or an unmatched dispatch leaves the total unknown;
the known subtotal remains separate. Preserve evidence, reconcile against project
usage/billing and obtain human review. Do not infer zero cost, remove reservations,
delete control markers, resume the run or choose a new run ID to replace a request.
The original SDK retries remain configured, but stopped transport rejects further
attempts after ambiguity. Neither the USD 5 guard nor the external cap reserves
worst-case in-flight liability or guarantees zero overshoot.

## Human reviewer packet and gate

Reviewer: **beccawillss**. The private review summary identifies the final reading
copy `human-packet.md`, complete JSON evidence and editable `human-draft.json`.
Packet directory:
`/private/tmp/study-v1-c3a-review-20261108/salesagent-preflight-canary/packet-for-beccawillss-readable`.
All eight J1–J8 examples, original authoritative commerce evidence, the unchanged
rubric/anchors and scoring instructions are present. No recommended scores or
model judgments are supplied. Full prepared evidence is available under each
example's expandable section.

Read independently, then fill every score/reason in the draft using only
0 / 0.3 / 0.6 / 0.8 / 1. Keep reviewer `beccawillss`; change exposure from
`unknown` to `not_seen` only if truthful. Do not inspect any judge calls/results
before completing and verifying all eight ratings. The independent human gate
does not ask the reviewer to reproduce wording or disclose chain-of-thought.

From the implementation worktree, these commands only accept/verify human data:

```sh
.venv/bin/python -m harness.canary.human accept --directory <packet-directory>
.venv/bin/python -m harness.canary.human verify --directory <packet-directory>
```

The receipt binds the eight ratings/reasons, reviewer, exposure and C1 roster.
No target/judge reservations can be made through this reopened human-only view.
Do not mistake test-only dummy ratings under `synthetic-tests` for reviewer work.
Actual reviewer ratings are still blank and unverified. For a later approved
judge stage, import the independently completed ratings into its fresh approved
canary store using C1's existing `save_human_ratings`, verify the receipt there
and obtain separate judge-call approval. Never reuse the synthetic target run
or change its mode to authorise paid calls.

## Remaining blockers and explicit approvals

Human patch review; approval of live source/digests and durable artifact root;
separate approval for paid-project setup and credential access; verified hard
limit/alerts/project association; execution-time model and pricing verification;
and explicit target-canary call approval remain outstanding. Independent human
ratings and their verified receipt remain required before any separate judge
approval/calls/result reveal. Study execution, freezes and merging remain
unauthorised. A scoped commit, push and PR are authorised solely for human review.
Offline evidence does not prove live API compatibility,
judge accuracy, actual billing enforcement or a guaranteed maximum invoice.
