# AI Test Harness - Codex Guidance

This file is the primary source of project development instructions.

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

1. Complete the first real Sales Agent evaluation study.
2. Analyse the results and publish a technical article.
3. Develop a professional full-stack AI evaluation application for agents, RAG
   systems and chatbots.

- Build features as small vertical slices.
- Prioritise demonstrated requirements; avoid speculative infrastructure.
- Prefer working end-to-end functionality over broad unfinished abstractions.
- Reuse existing code where it is sound.
- Avoid unnecessary rewrites.
- Avoid premature abstractions.
- Keep the core evaluation engine provider-neutral.
- Prefer the real supported interface of a target over importing its internal
  implementation merely for convenience.
- Introduce target-specific behavior at adapter boundaries rather than in the
  runner, result models, or generic scorer engine.

## Engineering standards

Deliver production-quality, maintainable code with clear interfaces and useful
error handling. Consider security, reliability and performance in design and
review. Validate untrusted inputs, bound resource use and measure performance
where the change creates a credible regression risk. Reuse sound existing
capabilities before adding dependencies or abstractions.

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

Live target, judge and Study execution require explicit, scoped human approval.
Preserve applicable credential protections, verified spending controls, approved
request/retry/token/cost limits and stop conditions. Missing or unverifiable
required controls block execution. Development, QA and merge approval do not
grant live execution authority.

Apply the controls required by the approved execution contract. Ordinary
evaluation runs do not automatically require every advanced canary capability;
this does not waive any applicable security, spending or scientific requirement.

Never commit secrets.

Do not print API keys, authorization headers, raw credentials, or sensitive
provider responses in logs or reports.

## Testing expectations

Choose unit, integration, end-to-end and regression tests according to the
behaviour and risk of the change. Add or update meaningful tests for code changes;
documentation-only changes normally need accuracy, link and whitespace checks.
Use focused checks while iterating and broaden verification according to impact.
Report actual results, optional skips, exclusions and unresolved failures.

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

Tests must own explicit scratch directories (for example, pytest's `tmp_path`),
including scratch passed to subprocesses. Never infer a writable root from ambient
`TMPDIR` or its parent. Cleanup must remain within test-owned paths and preserve
unrelated files. Copy important QA evidence to private durable storage before
scratch cleanup; retain the revision, environment, commands, outcomes and relevant
artifacts, including failures and limitations. Never retain secrets as evidence.

## Workspace and environment

The primary workspace is `~/Developer/ai-test-harness-dev`. Use its local `.venv`
and run commands from the checkout root; see [setup and checks](README.md#development).
Worktrees are optional for genuine isolation or parallel development. Keep any
long-lived checkout, worktree, environment or important QA evidence in durable
storage, never under `/tmp`, `/private/tmp` or another temporary directory.
Temporary storage is appropriate only for disposable, explicitly owned scratch.

Maintain committed `uv.lock` and `.python-version`. Provision the source-checkout
environment with `uv sync --locked --no-install-project`, using `PYTHONPATH=src`
for local Python commands. This installs locked dependencies without building the
project. Use the existing `.venv` for routine checks; do not borrow another
checkout's environment. Review intentional dependency, lockfile or Python version
changes together. Record the actual Python/tool versions for reproducibility.

## Scope control

For implementation tasks:

1. Inspect existing code first.
2. Explain the proposed change before implementing substantial architecture
   changes.
3. Modify only files relevant to the task.
4. Do not refactor unrelated code.
5. Add or update tests appropriate to the change.
6. Run relevant verification proportionate to risk.
7. Update an explicitly active plan as a living document, when one is in use.
8. Report files changed, tests run, and meaningful deviations.
9. Do not merge branches unless explicitly requested.

Before implementation, capture relevant workspace state: branch/revision, local
changes and any resources that must be preserved. Keep preservation checks
proportionate to risk. Freeze source changes during formal verification; if source
changes are needed, repeat the affected checks against the final revision. Stop
and investigate unexpected changes to protected resources before continuing.

Scale planning to risk: small changes need a brief scope and verification plan;
substantial or high-risk work needs a written plan. Use existing documentation
rather than introducing a new planning framework. Follow explicitly active,
approved plans milestone by milestone.

Historical ExecPlans and handoffs are records, not automatically active
instructions. Their temporary paths, commands, hashes, results and approvals
describe the work at that time and must not be rewritten as current evidence.
Existing scientific safeguards and execution approval requirements remain binding,
including preregistration, human QA, dataset/target/evaluator freeze and separately
authorised execution where required. A new checkout does not inherit approval
for a different live source location or revision. Publish findings supported by
retained evidence, with uncertainty, failures and limitations disclosed.

If the plan materially conflicts with the actual repository or these
instructions, stop and explain the conflict before implementing.

## Git workflow

`main` is the integration branch.

For each coherent change:

- default to one ordinary feature branch from current `main` in the permanent checkout;
- use separate milestone branches only when the milestones are independently mergeable;
- do not commit directly to `main`;
- keep the branch scoped to the change;
- require independent QA and human PR approval before merge, with review depth
  proportionate to risk; automated checks supplement review;
- do not merge without explicit approval;
- keep commits understandable and focused.

Inspect and preserve unrelated local changes. Obtain explicit approval before
destructive operations, including cleanup that could remove user files.

Do not perform history-changing Git operations such as rebase, force-push, or
branch deletion unless explicitly requested or approved.
