# C1 non-Study canary tooling — review handoff

**Implementation and offline verification only. No live execution approval.**
No server launcher or automatic live CLI is provided. Importing these modules
never reads credentials, constructs provider clients or starts an application.
Existing application, target adapter, judge adapter, runner and Study APIs are
unchanged. This is not primary capture journaling or a Study execution contract.

## Fixed inputs and limits

`harness.canary.inputs` contains the exact accepted A1/B1/A2/B2 prompts and eight
independently authored judge examples. J1–J8 repeat once, in that order. Target
responses never become judge inputs. No Study case/response files are read by
these modules. Existing semantic-v5 preparation and the unchanged rubric are
reused; anchors are 0/0.3/0.6/0.8/1, threshold 0.7.

Roster SHA-256:
`e8778ce74a270e6efbe490198d01e8b9c50bcc43387a02bff5f00b42304d5794`.
Tests pin this and all eight prepared judge prompt hashes from the assessment.

| Boundary | Limit |
| --- | --- |
| Shopper HTTP POSTs | Four, interleaved A1/B1/A2/B2; no retry |
| Local GETs | Health + OpenAPI + two trace reads for each turn = ten |
| Target logical Responses calls | Six per turn, 24 total |
| Target outbound provider attempts | Three per logical call, 72 total |
| Judge calls | 16, one attempt each; no retry or replacement |
| Combined provider attempts | At most 88; failures/pause can stop much earlier |

Target: gpt-5.6-terra, low reasoning, 2,000 output tokens, SDK timeout 30s,
two retries, unchanged application tools/tool loop. Judge: gpt-6.1-terra,
8,192 output tokens, HTTP connect/read/write/pool timeouts 5/300/10/5s,
no tools, store=false, stream=false. Reasoning is unspecified by the existing
judge adapter, not silently set to low. HTTP read timeouts are not overall
wall-clock deadlines. The canary shopper HTTP client uses 5/600/10/5s.

## Available APIs and future assembly

These are interfaces for a separately approved controller, not instructions to
execute a canary now. There is no default network transport or credential lookup.

1. Create a new `CanaryStore` under
   `~/StudyArtifacts/salesagent-preflight-canary/<approved-run-id>`.
   Directories are owner-only 0700; JSON files are 0600. Git ancestors, symlink
   ancestors, the `salesagent-study-v1` namespace, reused run directories and
   non-private namespaces are rejected. No prospective/calibration store is used.
   `mode="offline"` is the default. An explicit `mode="live"` is bookkeeping,
   **not permission to execute**; the manifest always says it grants no authority.
2. `export_human_packet(store)` writes only synthetic evidence, the existing
   rubric/anchors, and a blank draft. Exposure starts truthfully as `unknown`.
   Reviewer `beccawillss` independently completes all eight anchor ratings/reasons.
   `save_human_ratings(...)` requires all eight and an explicit truthful
   `exposure="not_seen"` declaration. It publishes an immutable hash receipt.
   Test-only dummy ratings are never actual reviewer approval.
3. After separate live approval, a single controller would explicitly create an
   HTTP transport wrapped by `ProviderTransport(store, delegate, role="target")`.
   Supply it to an SDK HTTP client with trust_env=false and redirects disabled;
   preserve SDK max_retries=2 and timeout=30. Pass that SDK client through the
   application's supported `OpenAIResponsesClient(..., sdk_client=...)` boundary,
   then through `BoundedResponsesClient(delegate, provider_transport)`.
4. Supply that decorator to the pinned application's existing
   `create_app(settings, responses_client=...)`. The application does not import
   the harness. A separately reviewed startup controller must still verify the
   pin, fixtures, prompt/configuration, project/key association and safe startup.
   No such launcher, credential handling or server startup runs in C1.
5. The controller owns one shared store and one single-worker application,
   dispatching one request at a time. `CanaryDriver(store).run_target(transport,
   base_url=...)` accepts only literal 127.0.0.1 HTTP without credentials/path
   prefixes. Live mode requires the bounded-client marker and per-turn telemetry.
   Use a fresh explicitly supplied local HTTP transport; never a default client.
6. The driver validates health/schema, sessions, trace correlation, successful
   tools, catalogue/promotion observations and stable rereads. It records only
   validated public chat/trace fields and replays the saved exchanges through
   adapter 3/evidence-v3 with an in-memory-only transport. Prose truthfulness,
   especially B1, still requires human inspection.
7. `run_judge(explicit_transport, api_key=...)` verifies the human receipt before
   constructing the existing judge client and before every call. Offline mode
   accepts only the fixed dummy credential; it never consults environment keys.
   The supplied real credential in a future approved live controller would stay
   in memory. `reveal_judgments(store)` also requires the receipt. Directory gates
   protect this workflow, not against the owning account deliberately bypassing it.
8. `load_target_replay(directory)` accepts saved public evidence only and has no
   network option. Missing/mismatched exchanges fail. Replay creates no Study
   runs, judgments, execution contracts, freezes or database entries.

## Telemetry and failure behaviour

Each logical call has an exclusive reservation. A dispatch record is fsynced
before transport I/O; an allowlisted attempt record follows. Original request
objects/bytes, tools, arguments and headers are forwarded without mutation.
Non-streaming response bodies are read for metadata before
returning; latency therefore includes recording overhead. No raw provider
envelope, instructions, authorization header, error text or reasoning content
is saved. SDK/HTTP debug logging must be disabled; canary calls reject an unsafe
logging configuration without changing it.

Available fields include local call/attempt/retry indices, UTC dispatch time,
duration, HTTP/completion status, allowlisted provider error codes, supported
request/response identifiers, observed model, input/output/total/cache-write/
cache-read/reasoning counters and estimated USD. Missing/invalid counters remain
null. Actual reported zero remains zero. Unknown identifiers are also null.
Public trace usage is the application's aggregate report; provider telemetry is
the source for cost calculations, because the application may default absent
SDK counts to zero.

An unmatched dispatch or an attempt without usable input/output counts makes the
total unknown. Known subtotal remains available, but is never a complete bill.
Known cache partitions use standard rates; missing partitions use conservative
30-minute write pricing without inventing counters. Long-context multipliers are
included. An unexpected service tier makes cost unknown. Rates are dated
2026-11-06 and require re-verification before live use.

There are no harness retries. Existing SDK retries may occur within a reserved
logical call, capped at three outbound attempts. After a transport timeout or
recording failure the transport refuses subsequent SDK attempts; the configured
SDK retry count itself remains unchanged. A provider spend/quota-limit code also
blocks subsequent outbound attempts immediately. Successful recovery from a
retry with unknown charges pauses the next logical call for human review.
Attempt/retry indices count dispatched HTTP attempts; an SDK retry rejected by
the stopped transport is not another outbound request or an assumed charge.

Any target/schema/trace/judge/parser/recording failure stops the canary, preserves
available evidence/reservations and prevents replacement calls. A failed human
receipt check constructs no judge. A stopped/reused run cannot be restarted by
these APIs. Saving synthetic replay results does not authorise new paid calls.

The $5 guard stops subsequent dispatch once the recorded estimate reaches $5,
and pauses on unknown billing. It does not reserve worst-case in-flight cost.
The separately approved $10 project hard limit, alerts and actual billing
reconciliation are external prerequisites, not implemented or configured here.
Neither this guard nor delayed provider enforcement guarantees zero overshoot.
Diagnostic/variance/replacement allowances remain zero.

## Review limitations

All C1 tests use scripted HTTP and fake credentials. They establish transport,
accounting, contract and safety behaviour, not live model availability, accurate
grading, 8,192-token sufficiency, complete provider telemetry, billing accuracy
or completion within $10/$40. Real API compatibility, source/deployment identity,
project controls and approved backup/recovery arrangements remain later gates.

On 2026-11-07 the user separately authorised final offline review, commit/push of
the eight C1 files and a PR against `main`. Publication of that PR does not
authorise merging, deployment, server startup, paid credential configuration,
live canary calls, Study execution or Study freeze. Existing execution worktrees
remain at their approved pins until a later explicit decision.
