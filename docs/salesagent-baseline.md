# Manual Sales Agent baseline and variance runs

The integration is offline-tested. No live baseline has been executed yet.
The entry point is a Python example, not a harness CLI. Importing it is inert.

## Prepare

Install locked dependencies separately with `uv sync --frozen --extra salesagent`.
Start the separately running Sales Agent through its normal workflow, using its
own model credentials. Set `SALESAGENT_ENABLE_EVAL_TRACES=true` in that service.
No provider credentials are needed in this harness. Confirm its deployed
revision, model/prompt configuration, and catalogue/promotion fixtures against
`datasets/salesagent/README.md`. Do not assume the adjacent checkout is deployed.

Confirm the target URL and intended live-call budget. The baseline invokes 14
conversations (18 shopper turns); variance invokes five conversations three
times each (21 shopper turns). Every successful chat also has one trace GET.
There are no invisible retries. Conversations can perform multiple model/tool
calls inside the Sales Agent and can incur provider charges there.

## Run explicitly

For a single diagnostic probe of the existing two-turn `sales-replace` case:

```sh
SALESAGENT_LIVE_EVAL=1 SALESAGENT_EVAL_MODE=baseline SALESAGENT_CASE_ID=sales-replace SALESAGENT_BASE_URL=http://127.0.0.1:8000 uv run --frozen --extra salesagent python examples/salesagent_baseline.py
```

This validates the frozen dataset, selects exactly one case by ID, and uses one
attempt through the normal adapter, runner, and scorers. It persists a separate
diagnostic run with the selected-case hash and full-dataset hash. It never
designates the probe as the full baseline, even if it passes. Unknown/empty IDs
and case selection combined with variance mode fail before client creation.
Omit `SALESAGENT_CASE_ID` for the normal full baseline or variance workflows.

From the harness root, run the primary structured-only baseline:

```sh
SALESAGENT_LIVE_EVAL=1 SALESAGENT_BASE_URL=http://127.0.0.1:8000 SALESAGENT_TARGET_REVISION=<deployed-revision> uv run --frozen --extra salesagent python examples/salesagent_baseline.py
```

Replace `<deployed-revision>` with the actual revision (or omit the environment
variable to record unknown). Target identity is always `salesagent`.
The recipe validates all 14 cases before any HTTP call, executes one attempt per
case, and persists to ignored `runs/salesagent.sqlite`. It prints the run ID,
dataset hash, pass/error rates, every attempt verdict and failed critical IDs.
Evaluator references are intentionally retained in the run configuration, never
in target request bodies or normalized target responses. Use synthetic shopper
inputs; do not put secrets in inputs, references, revisions, or fixture data.

Run the distinct variance subset only when deliberately requested:

```sh
SALESAGENT_LIVE_EVAL=1 SALESAGENT_EVAL_MODE=variance SALESAGENT_BASE_URL=http://127.0.0.1:8000 SALESAGENT_TARGET_REVISION=<deployed-revision> uv run --frozen --extra salesagent python examples/salesagent_baseline.py
```

This creates its own run ID, selected-case hash, and three-attempt configuration.
Never merge its attempts into the main baseline or describe their differing
configurations as a direct target regression. Semantic quality is explicitly
`not_measured`. A caller can supply an injected `RubricJudgeScorer` to `evaluate`
in a separately identified semantic run; no provider integration is included.

## Inspect and compare

`persist_and_verify` loads the new run and checks full equality plus descriptive
comparison. That self-comparison proves persistence compatibility, not quality
improvement. Later, use `SQLiteResultStore.load(run_id)` and
`compare_runs(baseline, candidate)` for real candidate comparisons. Inspect
`dataset_changed`, `evaluation_config_changed`, `model_versions_changed`, and
`target_changed` alongside case deltas. The recipe's `comparison_summary` also
includes revision and observed prompt/model context. Config/dataset differences
mean the comparison cannot isolate target behavior; no automatic gate is added.

Keep both quality pass rate and error rate visible. A genuine product FAIL is a
valid baseline observation. Any ERROR run is labelled diagnostic: investigate,
retain it, and rerun deliberately under a new ID. Never overwrite failed runs,
change golden assertions to match observations, or silently retry conversations.
A missing/disabled trace route is ERROR even when the shopper reply succeeded.
Earlier turn evidence is unavailable if a later turn errors under the existing
runner contract. Missing costs are unknown, not proof that execution was free.

After a real manual run, record run ID/database path, deployment revision,
model/prompt observations, dataset and evaluation configuration, quality/error
rates, and reload/comparison verification in the ExecPlan. Baseline and variance
runs remain separate. Do not merge the feature branch without explicit approval.
