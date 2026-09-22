# AI Test Harness - Codex Guidance

## Project goal

Build an AI testing, evaluation, and red-teaming platform for systems such as:

- RAG applications
- AI agents
- chatbots
- LLM-backed APIs

The long-term product will include persisted evaluation runs, run comparison,
failure inspection, red-team test suites, regression gates, and a dashboard.

The harness is an independent evaluation system. Systems under test must not
need to depend on harness internals in order to be evaluated.

## Current engineering priorities

- Build features as small vertical slices.
- Prefer working end-to-end functionality over broad unfinished abstractions.
- Reuse existing code where it is sound.
- Avoid unnecessary rewrites.
- Avoid premature abstractions.
- Keep the core evaluation engine provider-neutral.
- Prefer the real supported interface of a target over importing its internal
  implementation merely for convenience.
- Introduce target-specific behavior at adapter boundaries rather than in the
  runner, result models, or generic scorer engine.

## Core architecture

The evaluation engine should not know what kind of AI system it is testing.

`Target` is the abstraction for the system under test.

A target may represent:

- an AI agent
- a RAG application
- a chatbot
- an HTTP API
- a model
- a Python callable

Target-specific adapters may understand the external contract of one system,
but the core runner must remain independent of that system.

For example:

SalesAgentTarget
    -> knows the Sales Agent HTTP contract

Runner
    -> knows only Target / TargetResponse

Scorers
    -> evaluate normalized TargetResponse evidence

Do not make the target application change its architecture purely to fit the
harness unless an evaluation-critical interface is genuinely missing.

## TargetResponse and evidence

`TargetResponse` is the normalized boundary between a target and evaluation.

Preserve support for:

- final model/application output
- structured response data
- RAG context
- agent/tool trajectories
- latency
- token/cost information
- model/provider metadata
- arbitrary safe metadata

Target adapters should normalize target-specific output into these concepts
rather than exposing raw SDK/provider objects throughout the evaluation engine.

Do not store or expose:

- API keys
- authorization headers
- hidden prompts unless explicitly part of the evaluation contract
- model chain-of-thought/reasoning
- raw provider objects when a normalized representation is sufficient

## Evaluation isolation

Golden datasets and evaluation expectations must not leak into the system under
test.

Do not send the target:

- scenario IDs
- expected answers
- expected tool calls
- scorer thresholds
- assertion definitions
- pass/fail expectations
- golden labels

unless one of those values is genuinely part of the intended user/application
input.

Do not add production or target-side special cases for individual evaluation
scenarios.

A passing evaluation must result from general system behavior, not awareness of
the test case.

## Evaluation semantics

Quality failures and infrastructure errors are different.

Do not convert:

- target errors
- scorer errors
- judge failures
- malformed judge output
- timeouts
- unavailable dependencies
- malformed target responses

into quality scores of zero.

They should be represented as infrastructure errors.

Semantics:

- PASS = all required/gated quality checks pass.
- FAIL = at least one required/gated quality check fails.
- ERROR = evaluation execution could not be completed reliably.
- SKIP = no gated evaluation determines quality.

Preserve successful scorer results when another independent scorer errors.

## Deterministic and semantic scoring

Prefer deterministic assertions whenever the expected property is objectively
machine-checkable.

Examples include:

- structured product IDs
- prices
- promotion validity
- tool names
- trace fields
- citations
- constraint state
- expected null/non-null fields
- schema/contract rules

Use semantic or LLM-as-a-judge scoring for qualities that genuinely require
judgment, such as:

- relevance
- explanation quality
- completeness
- tone
- usefulness

Do not use exact string matching for generative prose unless exact wording is a
real product requirement.

LLM judges must remain provider-neutral through injected judge interfaces.

Judge model, rubric, thresholds, and relevant configuration must be recorded in
run metadata.

Malformed judge responses and judge execution failures are ERROR, not score 0.

## Critical assertions

Support evaluation rules that cannot be averaged away by otherwise good scores.

A critical business-rule, grounding, security, or safety failure should make
the case fail even if semantic quality scores are high.

For example:

Helpful response quality = high
Invalid fabricated discount = critical failure

Result = FAIL

Do not hide critical failures inside aggregate averages.

## Multi-turn and attempt isolation

Each evaluation case and each repeated attempt must start from an isolated
target state unless the dataset explicitly defines shared state.

For stateful systems:

- preserve state only between turns belonging to the same case attempt;
- do not leak sessions/history between cases;
- do not leak sessions/history between repeated attempts;
- retain per-turn evidence when later assertions depend on trajectory/state.

Repeated attempts should measure model/system variance, not accidental shared
state.

## Runner requirements

The runner should:

- validate target/scorer capability requirements before execution;
- support multiple cases;
- support multiple scorers;
- support multiple attempts;
- preserve scorer results independently;
- distinguish FAIL from ERROR;
- record timing and execution metadata;
- preserve stable dataset fingerprints;
- record target/model/config versions where available;
- produce enough information for later run comparison and regression analysis.

Do not make the runner understand Sales Agent, RAG, OpenAI, or other
target-specific concepts directly.

## Dataset requirements

Datasets should be portable, deterministic inputs to evaluation.

Preserve:

- structured inputs
- references
- tags
- metadata
- stable hashing/fingerprints
- useful validation errors including file and line information

Scenario identifiers should be stable across dataset revisions when the
scenario intent remains the same.

Changes to expectations, inputs, or scenario meaning must be detectable through
dataset/version fingerprints.

Keep target input separate from evaluator-only expectations.

## Reproducibility and comparison

An evaluation run should preserve enough context to understand and compare it
later.

Where available record:

- dataset fingerprint
- target identity/version
- model/provider identity
- prompt/config version
- scorer configuration
- judge configuration
- number of attempts
- timing
- token/cost metadata
- relevant capability metadata

Run comparisons must clearly distinguish changes caused by different datasets
or evaluation configurations from changes produced by target behavior.

Do not present incomparable runs as direct regressions without flagging those
configuration differences.

## External integrations and secrets

Default automated tests must be offline and deterministic.

Do not require:

- OpenAI or other provider credentials
- running external applications
- live network calls
- paid APIs

for the normal test suite.

Use deterministic fake targets, fake judges, scripted responses, and local test
servers where appropriate.

Live integration/evaluation runs must be explicitly invoked and must not run
accidentally during pytest or CI.

Never commit secrets.

Do not print API keys, authorization headers, raw credentials, or sensitive
provider responses in logs or reports.

## Testing expectations

Every implementation should consider:

- happy path
- invalid input
- boundary conditions
- target failures
- scorer failures
- malformed external responses
- timeouts
- serialization round-trips
- repeated-attempt isolation
- state leakage between cases
- capability mismatches
- regression risk

Use deterministic test doubles where possible.

Tests should validate observable behavior rather than implementation details.

Target-specific adapter tests should verify the adapter contract without making
the core engine target-specific.

## Scope control

For implementation tasks:

1. Inspect existing code first.
2. Explain the proposed change before implementing substantial architecture
   changes.
3. Modify only files relevant to the task.
4. Do not refactor unrelated code.
5. Add or update tests.
6. Run relevant tests.
7. Update any active ExecPlan as a living document.
8. Report files changed, tests run, and meaningful deviations.
9. Do not merge branches unless explicitly requested.

When an approved ExecPlan exists, follow it milestone by milestone.

If the plan materially conflicts with the actual repository or these
instructions, stop and explain the conflict before implementing.

## Git workflow

`codex-evaluation` is the integration branch.

For each coherent implementation slice / ExecPlan:

- default to one dedicated feature branch from the current integration branch;
- use separate milestone branches only when the milestones are independently mergeable;
- do not commit directly to `codex-evaluation`;
- keep the branch scoped to that implementation slice / ExecPlan;
- do not merge without explicit approval;
- keep commits understandable and focused.

Do not perform history-changing Git operations such as rebase, force-push, or
branch deletion unless explicitly requested or approved.