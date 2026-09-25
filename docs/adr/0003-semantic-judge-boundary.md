# 0003. Explicit semantic evidence and normalized judge replies

Date: 2026-09-25
Status: Accepted through the semantic-evaluation implementation approval

## Context

RubricJudgeScorer already supports provider-neutral rubric scoring, but its
default payload includes tags, contexts and trajectories. Live Sales Agent
semantic judging needs a smaller explicit trust boundary and independent judge
credentials. A string-only judge return cannot preserve actual usage/model
observations without mutable per-call state.

## Decision

Reuse RubricJudgeScorer, its Score format, and the existing runner's all-gates
and ERROR semantics. An optional generic evidence_builder replaces the default
payload entirely. A Sales Agent pack projects only shopper/assistant turns,
displayed commerce, constraints and relevant normalized commerce facts. It
contains target schema knowledge; the runner and generic scorer do not.

Missing or malformed required evidence is ERROR. Explicit authoritative nulls
and empty collections are business evidence. Complete evidence contradicting
assistant prose is quality evidence for potential FAIL. The rubric asks every
non-perfect judgment to identify its main observable shortcoming concisely,
without revealing a threshold or requesting chain-of-thought. Critical
deterministic failures cannot be averaged away by a semantic score.

Judge callables may return text or an immutable validated JudgeReply containing
text and optional model/usage/latency/cost observations. String-returning callers
retain their result shape. Score.extra carries normalized observations; no raw
provider objects cross this boundary. Strict judgment parsing rejects duplicate
or extra keys as well as malformed values. This intentionally tightens the
previous parser to match its already advertised score/reason-only contract.

The first optional transport uses HTTPX for OpenAI Responses, with explicit
judge-specific credentials, fixed evaluator instructions and endpoint, no tools,
no conversation reuse, and no retries. Errors are sanitized before the runner
persists them. Provider refusals, incomplete responses and malformed envelopes
are ERROR. Unknown usage/cost is not zero.

Persist explicit evaluator settings under the already-compared
semantic_evaluation configuration key; store observations separately. The
existing JSON/SQLite schema and descriptive comparison remain unchanged.

## Consequences

One provider-neutral scoring path serves fake and live judges. The semantic-v1
dataset and provisional 0.7 threshold are independent of the frozen structured
baseline. Compatibility requires the same semantic evaluation configuration.
Projection/version tests and offline provider fixtures protect the boundary,
but cannot prove that an LLM is immune to injected text or calibrated against
human judgment. Manual live acceptance remains a separate explicit operation.
