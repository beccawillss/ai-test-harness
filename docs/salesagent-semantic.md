# Manual Sales Agent semantic evaluation

The semantic-v1 recipe evaluates all 14 Sales Agent scenario concepts with the
existing deterministic gates and one conversation-level semantic Score. The
provisional semantic threshold is 0.7. It measures relevance/helpfulness,
clarity/actionability, agreement between prose and commerce evidence, and
conversation coherence. The judge is not calibrated against human labels yet.
No live semantic acceptance has been performed by this implementation.

## Optional warmth evidence v5

The generic semantic factory still defaults to evidence v2, and explicit v3/v4
retain their existing prepared/configuration bytes. Explicit
`projection_version="salesagent-semantic-evidence-v5"` adds the exact authoritative
product `warmth` enum from adapter 3 / `salesagent-evidence-v3` observations.
The v5 builder requires those matching response metadata labels, retains all
successful lookup/search observations (including prose-only alternatives), and
preserves v4 inventory/promotion behavior, order, conflicts and per-turn provenance.
No later observation fills an earlier turn, and no catalogue import or inference
fills missing warmth. Missing/invalid warmth is ERROR before judgment, even if
an untrusted recommendation card claims to supply it. Valid contradictory facts
remain visible rather than being deduplicated or resolved by the projection.

The existing 64 KiB UTF-8 evidence limit applies unchanged, with no truncation.
Warmth is not a temperature scale; `shell` must not be translated into an
insulation rating. Season expansion is excluded. The rubric, anchors and 0.7
threshold do not change. For Study v1, use the explicit, frozen version selection
in the [Study workflow](salesagent-study-adoption.md#opt-in-warmth-binding).

## Prepare independently

Prepare locked dependencies separately:

```sh
uv sync --frozen --extra salesagent --extra judge-openai
```

Start the target through its normal workflow, with its own model credentials
and `SALESAGENT_ENABLE_EVAL_TRACES=true`. Confirm the deployed revision, model,
prompt configuration, and fixtures documented in `datasets/salesagent/README.md`.
The harness does not import or start the target application.

Provide `HARNESS_JUDGE_API_KEY` securely in the harness process environment.
It is an independent judge credential: the recipe never falls back to
`OPENAI_API_KEY`, loads dotenv, or reads target configuration. Set
`HARNESS_JUDGE_PROVIDER=openai` and an explicit `HARNESS_JUDGE_MODEL` that supports
Responses with structured JSON output. There is no default model, automatic
provider fallback, or automatic retry. Prefer a pinned model and agree a call
budget before invoking live evaluation. Do not put keys into files or shell
commands that may be recorded.

The adapter uses the fixed OpenAI Responses endpoint with tools and streaming
disabled, `store=false`, no conversation reuse, a 2048 output-token ceiling, and
5/120/10/5 second connect/read/write/pool timeouts. Unsupported model/settings
produce ERROR rather than a fallback. Request settings and observed model/usage
are recorded separately. Provider output is projected to judgment text and safe
observations; raw envelopes and reasoning are discarded.

## Smoke, inspect, then full run

Only invoke these commands when live execution is deliberately authorized.
Replace the model and revision placeholders with actual values. Importing the
example is inert; `main` requires its own semantic live opt-in. Setting the
older structured-baseline opt-in does not enable this entry point.

```sh
SALESAGENT_SEMANTIC_LIVE_EVAL=1 HARNESS_JUDGE_PROVIDER=openai HARNESS_JUDGE_MODEL=<selected-model> SALESAGENT_CASE_ID=sales-summer20 SALESAGENT_BASE_URL=http://127.0.0.1:8000 SALESAGENT_TARGET_REVISION=<deployed-revision> uv run --frozen --extra salesagent --extra judge-openai python examples/salesagent_semantic.py
```

This validates all 14 rows before creating clients, then runs the selected case
once. It uses one target POST/trace GET pair and at most one judge request.
The recipe saves a new diagnostic run to ignored `runs/salesagent-semantic.sqlite`,
reloads it, verifies equality, and prints normalized semantic Scores, failed
critical assertion IDs, attempt verdicts/errors, hashes and completion count.

Inspect the concise Score reason against the normalized conversation. A
below-threshold reason should identify the main observable shortcoming, such as
claiming that an inactive promotion was applied. The rubric requests that for
every non-perfect score without revealing the threshold. The parser validates
shape and a nonempty reason; it cannot deterministically prove that the reason
is a sound judgment. Human review remains necessary. Do not request or inspect
chain-of-thought.

To reload and inspect a stored artifact without any network calls:

```python
from harness.core.store import SQLiteResultStore

result = SQLiteResultStore("runs/salesagent-semantic.sqlite").load("<run-id>")
for case in result.cases:
    for attempt in case.attempts:
        print(case.case_id, attempt.index, attempt.verdict, attempt.error)
        for score in attempt.scores:
            if score.name == "salesagent_semantic_quality":
                print(score.model_dump(mode="json"))
```

Stop on ERROR before proceeding to a larger run. Keep the diagnostic record and
fix the infrastructure problem; rerun explicitly under a new ID. A genuine
quality FAIL is a finding, not a reason to modify expectations to match output.

For the full semantic-v1 observation, invoke the same command without
`SALESAGENT_CASE_ID` (ensure that variable is unset in the process environment).
The default is 14 conversations, 18 shopper turns and at most 14 judge requests.
The target may make additional internal model/tool calls. Successful persistence
is reported only after save, reload and comparison verification. A save failure
raises rather than printing a false success.

## Optional repeated subset

For a separate combined target/judge variance run, use:

```sh
SALESAGENT_SEMANTIC_LIVE_EVAL=1 HARNESS_JUDGE_PROVIDER=openai HARNESS_JUDGE_MODEL=<selected-model> SALESAGENT_SEMANTIC_CASE_IDS=sales-summer20,sales-fake-price,sales-replace SALESAGENT_SEMANTIC_ATTEMPTS=3 SALESAGENT_BASE_URL=http://127.0.0.1:8000 SALESAGENT_TARGET_REVISION=<deployed-revision> uv run --frozen --extra salesagent --extra judge-openai python examples/salesagent_semantic.py
```

Unset the single-ID selector first; single-ID and subset selection are mutually
exclusive. A single diagnostic ID always uses one attempt. Attempts must be a
positive integer; empty, unknown or duplicate IDs are rejected. Subsets retain
dataset order and their own hash, selection and attempt policy. This example
uses nine conversations, twelve shopper turns and at most nine judge requests.
Each attempt starts a fresh target session and a stateless judge request.

Fresh target attempts measure combined variance. Isolating judge variance
requires separately authorized rejudging of fixed saved normalized responses
with the same rubric/configuration and recording every returned Score; it is
not implemented as a general replay workflow here.

## Evidence, errors, and comparison

The separate `datasets/salesagent/semantic.jsonl` copies the frozen baseline's
inputs and deterministic assertions, and adds versioned semantic expectations
and derivation provenance. The structured baseline remains frozen. Only shopper
messages and returned session IDs reach the target.

The semantic pack allowlists shopper/assistant turns, displayed commerce,
resolved constraints, and relevant normalized product/inventory/promotion facts.
It excludes scenario/assertion IDs, deterministic verdicts, thresholds, tags,
operational metadata, raw tool payloads and hidden prompts. Strings in evidence
remain untrusted data. JSON boundaries and fixed evaluator instructions reduce
prompt injection exposure; passing fake tests does not prove live model immunity.

- Missing/malformed evidence needed for a fair judgment is ERROR before the judge.
- Explicit authoritative null/empty business outcomes are valid judge inputs.
- Complete evidence contradicting prose is quality evidence, potentially FAIL.
- Judge/provider failures and malformed judgments are ERROR, with independent
  structured results retained. A critical failure remains visible even when a
  simultaneous judge error makes the attempt ERROR.
- High semantic scores never override deterministic gated or critical failures.

Pass rates exclude ERROR/SKIP attempts. Read them with error rate and completed
semantic-score count. Individual scores retained on ERROR attempts can still
contribute to scorer means. Costs absent from target or judge observations are
unknown; `RunResult.total_cost_usd` is not a combined semantic-run cost. Judge
token counts and call latency appear in `Score.extra["judge"]` only when known.

For compatible candidates use the existing `compare_runs`, and the semantic
example's `comparison_summary` to label compatibility beside deltas. From a
Python process that imports examples, put the `examples/` directory on its
module search path and import `salesagent_semantic.comparison_summary`.
Compatibility requires matching dataset/selection, attempts, pack, rubric,
projection/prompt versions, gates, and judge provider/model/settings. Changed
observed judge models also qualify comparison, even if an alias is unchanged.
Target revisions/models/prompts remain separately displayed context.

Full versus smoke/subset/variance, and semantic versus structured-only runs,
answer different questions. Never interpret the semantic aggregate as a direct
regression against structured runs `93b767af4dac` or `c21b28ef0053`. Reload
self-comparison proves persistence, not quality improvement. No automatic release
gate, baseline promotion, live CI, or merge is part of this milestone.
