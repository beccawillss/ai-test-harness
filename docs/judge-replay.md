# Fixed-response judge replay

Replay scores one saved response repeatedly without constructing or invoking a
target. It uses the existing JudgedScorer/RubricJudgeScorer parser and threshold.
Each replay is a separate experiment with a new ID, ordered scores/errors,
provenance and descriptive statistics. It does not replace source judgments or
deterministic business gates and cannot establish judge calibration.

## Data handling

Persisted prepared evidence and prompts contain shopper/assistant evaluation
content. Treat the SQLite replay artifact as **evaluation data** with the same
access and sharing controls as its source. Reviewed allowlists exclude known
operational metadata, raw/provider objects, credentials, hidden prompts and
deterministic results. They cannot guarantee that arbitrary natural-language
user content contains no sensitive information. Judge reasons can also refer to
that content. Do not publish artifacts merely because their provenance is safe.

Source database provenance uses a repository-relative locator, or the logical
label `external-source` for paths outside the repository. Absolute paths are
execution-only and are not stored or printed by the recipe. The source document
hash and run/case/attempt IDs distinguish sources even when their logical labels
match. Keep an external locator-to-file mapping locally if necessary.

## Source eligibility and compatibility

Supply the unchanged frozen dataset used by the source run. Replay verifies the
ordered original selection against RunResult.dataset_hash, including reference,
tags and extra/provenance. It verifies full_dataset_hash, selection and
resolved_cases when recorded. It selects the source attempt by its stored
zero-based index, not its position in a list.

The response must exist and contain the selected scorer's required evidence.
A source ERROR caused by scoring may still have an eligible response. A missing
target response or missing required semantic facts cannot be reconstructed from
the target, newer responses or external catalogues.

Strict mode requires matching recorded selected-scorer and judge configuration.
The source's other scorers and attempt count do not need to match this experiment.
The explicit `--allow-reconfigured` option permits different or unknown source
evaluator settings and labels the result accordingly. It never bypasses dataset,
evidence, projection or configuration validation. Changing expectations requires
a different workflow; this milestone only accepts the original dataset.

The Sales Agent helper translates its saved pack/scorer configuration into the
neutral replay configuration. Generic callers must supply a trustworthy
translation too, or use explicit reconfigured mode with unknown provenance.
Never fill missing historical versions with current defaults and call them a
match. Recorded-model aliases can resolve to a different observed model; every
attempt records observations and summaries flag drift/unknown values.

Historical prompt bytes were not saved. Matching recorded versions supports
compatibility, but cannot prove historical request-byte identity. Replay freezes
the newly prepared prompt and checks its exact bytes at every invocation.

## Dry-run against the saved semantic response

Dependencies must already be installed for offline operation. No target process
or target credential is needed. This command prepares/verifies input and prints
safe provenance, hashes, compatibility, threshold and judge configuration. It
does not create clients, invoke a judge, write results or print evaluation prose.

```sh
UV_OFFLINE=1 uv run --frozen --extra judge-openai python examples/salesagent_judge_replay.py --source-db runs/salesagent-semantic.sqlite --source-run bbeb64511171 --case-id sales-discount-override --source-attempt 0 --dataset datasets/salesagent/semantic.jsonl --attempts 5 --output-db runs/judge-replay.sqlite --dry-run
```

Dry-run is also the default when neither mode flag is supplied. For a database
outside this checkout, substitute its actual local path; only `external-source`
appears in portable provenance. Error output deliberately omits exception bodies
and absolute paths. Local Python dataset loaders retain file/line diagnostics
for troubleshooting without publishing the recipe output.

## Deliberate live acceptance

**Do not run this as part of offline validation.** After the operator explicitly
chooses the source and call budget, supply HARNESS_JUDGE_API_KEY securely in the
harness process environment. No fallback to OPENAI_API_KEY or target dotenv is
used. The historical requested model below is not a promise of current access.
Unavailable models/settings produce ERROR rather than automatic fallback.

```sh
HARNESS_JUDGE_REPLAY_LIVE=1 HARNESS_JUDGE_PROVIDER=openai HARNESS_JUDGE_MODEL=gpt-6-sol uv run --frozen --extra judge-openai python examples/salesagent_judge_replay.py --source-db runs/salesagent-semantic.sqlite --source-run bbeb64511171 --case-id sales-discount-override --source-attempt 0 --dataset datasets/salesagent/semantic.jsonl --attempts 5 --output-db runs/judge-replay.sqlite --live
```

Both `--live` and HARNESS_JUDGE_REPLAY_LIVE=1 are required; explicit matching
provider/model are also required. This makes five stateless judge requests,
with no automatic retries, conversation, previous-response ID, tools or cookies.
The fixed provider endpoint and no redirects keep requests on the judge service.
Normal provider errors do not prevent later independent attempts. Credentials
are neither persisted nor included in prompt/configuration/report content.

Inspect individual reasons, observed models, usage and errors after reload.
Optionally perform a separate five-call control for `sales-summer20` or
`sales-welcome10`; each response gets its own replay artifact. Never pool their
scores into one fixed-input distribution. Primary plus one control is ten
calls; choosing ten attempts for the primary increases that budget explicitly.

## Generic API and prepared-input architecture

The core entry points in `harness.core.replay` are:

```python
source, document_hash = source_store.load_with_fingerprint(source_run_id)
prepared = prepare_replay(
    source,
    frozen_cases,
    scorer,
    judge_configuration=actual_judge_configuration,
    database_locator="runs/source.sqlite",
    case_id=case_id,
    source_attempt=0,
    attempts=5,
    source_evaluator=verified_recorded_evaluator,
    source_document_hash=document_hash,
)
result = replay(
    prepared,
    scorer,
    judge_configuration=lambda: JudgeConfiguration.model_validate(judge.configuration),
)
destination_store.save_replay(result)
restored = destination_store.load_replay(result.replay_id)
assert restored == result
```

Open source_store with `SQLiteResultStore(path, read_only=True)`. Use a distinct
destination file; the supplied recipe rejects matching resolved paths, symlinks
and hardlinks before execution and persistence. Generic callers own destination
selection and safe translation of recorded evaluator configuration.

The API accepts no Target and never calls the normal runner. Core imports no
provider SDK/HTTP implementation and knows no Sales Agent schemas. Injected
judges and custom scorer code must honor the stateless/no-target contract;
arbitrary Python callables cannot be mechanically proven to do so.

Ordinary `scorer.score(case, response)` delegates to `prepare` followed by
`score_prepared`. The base preparation hook supports existing JudgedScorer
build_prompt/parse_judgement implementations. Rubric preparation builds its
evidence once and freezes canonical evidence JSON and the formatted prompt.
Existing RubricJudgeScorer subclasses overriding build_prompt keep that hook.
Replay requires a reviewed projection and explicit rubric/projection/prompt/
judgment versions, plus complete supported judge settings. The generic default
rubric denylist alone is not a reviewed replay projection.

PreparedJudgeInput and PreparedReplay contain immutable values: nested evidence
and scorer configuration are JSON strings, while settings/provenance use frozen
models/tuples. A scorer configuration mismatch blocks scoring. An observation
hook fingerprints the actual prompt immediately before the judge call, checks
current adapter settings, and rejects drift. Custom adapters supply the safe
configuration callback; it must reflect actual settings, not a stale declaration.

ReplayResult holds the prepared input, provenance and ordered
ReplayAttemptResults. It stores no copied source response, deterministic Score,
old semantic Score or raw judge reply. Source responses stay in their original
database. JudgeObservation separates normalized telemetry from text;
JudgeScoringError preserves observations when a normalized reply cannot be
parsed. Unknown observations never inherit a previous attempt's values.

## Fingerprints and persistence

`replay-canonical-json-v1` hashes UTF-8 JSON with sorted object keys, compact
separators, ensure_ascii=False and allow_nan=False. It preserves exact strings,
nulls and ordered lists; no rounding, trimming or Unicode normalization occurs.
Existing `hash_cases` dataset hashing is unchanged and remains a separate
algorithm. Persisted fingerprints distinguish:

- Whole source document and full normalized TargetResponse.
- Verified selected TestCase and user input.
- Canonical projected evidence and exact UTF-8 prompt.
- Replay input: `judge-replay-input-v1` containing canonical version, prompt and
  evidence hashes, and complete explicit evaluator configuration.

The response hash includes safe operational fields that do not reach the judge;
it is intentionally different from the evidence/input hashes. Source location,
timestamps, N, output observations and source verdicts are outside the effective
judge-input fingerprint. Equal fingerprints prove data equality, not provider
statistical independence or historical prompt-byte equality.

The existing store adds a separate, lazily created `replays` table and provenance
index. It retains ordinary `runs` behavior. Read-only opening creates no
directories/schema; database writes and store save methods are rejected.
Replay IDs cannot overwrite prior results. `list_replays` returns lightweight
provenance without prompts. Loading validates input hashes, compatibility and
ordered attempt/score/verdict consistency. Summary statistics are derived anew.

The recipe reports successful persistence only after save/reload verification.
Saving happens at the end, including ordinary failed attempts; abrupt process
termination can lose the in-memory run. Incremental checkpoint/recovery is not
implemented. Keep the source database and frozen dataset available for later
audits of the full normalized response.

## Reading variance

ERROR attempts have no quality score and remain null in `scores_by_attempt`.
PASS means the selected score meets its threshold (equality passes); FAIL means
it does not; an informational score yields SKIP. Summaries report requested and
recorded attempt counts, completed scores/errors/skips, mean/min/max/range,
population standard deviation, PASS/FAIL counts and pass rate, threshold crossing
and observed-model variation. Errors are excluded from quality denominators.

For 0.8, 0.6, 0.8, 0.8, 0.6 at 0.7: mean 0.72, range 0.20,
population standard deviation about 0.098, 3 PASS, 2 FAIL, crossing true.
Score variation without threshold crossing is distinct from verdict instability.
No successful scores means null numeric/quality statistics; one score has zero
range/stddev with `insufficient_repeats=true`. A false crossing flag means no
crossing was observed, not established stability. Null means no gated evidence.

Judge cost is recorded only when known. The summary supplies the known subtotal,
known count and completeness; it does not charge historical target cost again.
Unknown model/usage/latency/cost stays unknown. Attempt elapsed time is separately
measured even when no provider telemetry exists.

Do not feed ReplayResult to `compare_runs` or label changed replay pass rates a
target regression. Different response/evidence/config hashes are different
experiments. These descriptive observations set no acceptable-variance threshold,
release gate or statistical significance. “No variation observed in N completed
judgments” is a bounded observation; “judge calibrated” is not supported. Stable
fingerprints and per-attempt observations can support future human rating joins,
but this milestone provides neither annotation nor agreement metrics.

## Versioned v2 suite sources

Milestone 3 suite runs declare `dataset-cases-v2`, `run-organization-v1` and
`case-definition-snapshot-v1`. Preparation verifies full/selected case hashes,
definition hashes, copied tags/classification, safe metadata projections, suite
selection/pins and recorded evaluation context. Complete descriptor snapshots
reproduce their hash; projected descriptor snapshots explicitly do not. Recorded
profile judge configuration can supply the original evaluator contract; missing
configuration still requires explicit translation or the existing unknown/
reconfigured opt-in. No provider client is introspected.

`case_payload_snapshot="hashes_only"` has no stored input/reference payloads;
callers must supply the exact verified source cases. `full` adds canonical
resolved cases excluding authored extra. `reconstruct_source_cases(result)`
reconstructs source cases only if saved payloads plus projected metadata reproduce
the complete source hashes. A subset run or omitted metadata can still require
external cases. Its output must pass ordinary `prepare_replay()` checks before
replay. Missing or mismatched source material is a preflight error, never an
invitation to use today's dataset or invoke a judge to repair missing evidence.

Legacy runs lacking a scheme remain v1. Missing legacy definition snapshots and
source scheme fields remain omitted on serialization. Existing frozen run,
replay, prompt/evidence and calibration hashes are unchanged; no artifact rewrite
or human rebinding is required. Older readers must not resave v2 documents.

## Prospective human-first evaluation

An unjudged capture uses the separate [prospective judging API](prospective-judging.md),
which registers a future evaluator and can enforce a complete human freeze before
judge construction. It does not create a historical Score or relax replay's
recorded-configuration checks. Optional `score-output-contract-v1` anchors are
part of the evaluator fingerprint when enabled; legacy continuous configurations,
prompts and replay documents retain their original representation.
