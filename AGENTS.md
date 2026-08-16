# AI Test Harness - Codex Guidance

## Project goal

Build an AI testing, evaluation, and red-teaming platform for systems such as:

- RAG applications
- AI agents
- chatbots
- LLM-backed APIs

The long-term product will include persisted evaluation runs, run comparison,
failure inspection, red-team test suites, and a dashboard.

## Current engineering priorities

- Build features as small vertical slices.
- Prefer working end-to-end functionality over broad unfinished abstractions.
- Reuse existing code where it is sound.
- Avoid unnecessary rewrites.
- Avoid premature abstractions.
- Keep the core evaluation engine provider-neutral.

## Core architecture

The evaluation engine should not know what kind of AI system it is testing.

Target is the abstraction for the system under test.

A target may represent:

- an AI agent
- a RAG application
- a chatbot
- an HTTP API
- a model
- a Python callable

Scorers evaluate TargetResponse objects.

Preserve support for:
- deterministic scorers
- LLM-as-a-judge scorers
- multiple scorers
- multiple attempts
- RAG context
- agent trajectories
- latency
- token/cost information
- arbitrary metadata

## Evaluation semantics

Quality failures and infrastructure errors are different.

Do not convert:
- target errors
- scorer errors
- judge failures
- malformed judge output
- timeouts

into quality scores of zero.

They should be represented as infrastructure errors.

PASS = all gated scores pass.
FAIL = at least one gated score fails.
ERROR = evaluation execution failed.
SKIP = no gated evaluation determines quality.

## Testing expectations

Every implementation should consider:

- happy path
- invalid input
- boundary conditions
- target failures
- scorer failures
- malformed external responses
- serialization round-trips
- regression risk

Use deterministic test doubles where possible.

Tests should validate observable behaviour rather than implementation details.

## Scope control

For implementation tasks:

1. Inspect existing code first.
2. Explain the proposed change before implementing substantial architecture changes.
3. Modify only files relevant to the task.
4. Do not refactor unrelated code.
5. Add or update tests.
6. Run relevant tests.
7. Report files changed and test results.
8. Do not merge branches unless explicitly requested.

## Git workflow

`codex-evaluation` is the integration branch.

For each implementation milestone:
- create a dedicated feature branch
- do not commit directly to `codex-evaluation`
- keep the branch scoped to one milestone
- do not merge without explicit approval