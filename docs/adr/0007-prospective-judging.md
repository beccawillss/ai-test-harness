# ADR 0007: Prospective judging and explicit output validation

Status: accepted; readiness Milestone 1 implemented 2026-10-05.

## Context

Historical replay proves a relationship to an already recorded evaluator. A
human-first experiment instead captures an unjudged response, registers a future
evaluator, freezes independent human ratings, and only then judges fixed bytes.
Using fabricated historical scores/configuration would misrepresent that order.
Prompt-only numeric anchors also cannot enforce an evaluator's output contract.

## Decision

Introduce separate immutable prospective plans, preparations and results, sharing
source verification, prepared input, evaluator configuration and attempt semantics
with replay. Keep historical recorded-configuration checks intact. New nested
models use canonical strings and strict schema boundaries; a complete plan binds
reserved request/observation identities, roles, sources and review policy.

Reuse calibration's private manifest, blind packet and freeze receipts through a
narrow preparation union and explicit prospective observation policy. Require a
complete exact protected roster before constructing a judge, then verify the
actual projection/configuration and each prompt. The generic API has no Target.
It cannot prevent provider calls outside the workflow; study integration owns its
protected selection contract.

Persist new local JSON artifacts with exclusive identity/execution reservation
files and receipts published last. Never replace source runs, primary observations,
replays or calibration bindings. Return the execution result for explicit saving;
a failed save can be retried without another judge call. An unresolved reservation
is ambiguous after a crash and cannot be silently reused. Diagnostic repeats need
new identities and explicit parent/protection binding.

Add an opt-in, versioned anchor output contract to judged scorer configuration.
Without it, legacy configuration and continuous parsing stay byte-compatible.
With it, parsing and artifact verification reject off-anchor output as ERROR,
without score repair. Generic code owns validation; integrations own values,
rubrics and projection content. Human anchors must agree with an enabled contract.

## Consequences

Historical and prospective artifacts remain distinguishable. Existing replay,
calibration arithmetic, dataset schemes, run models and SQLite schemas are
preserved. Older readers cannot safely resave prospective/anchor-enabled data.
Private artifacts include complete normalized responses and exact evaluator
input under an explicit sharing policy; this is not a redaction framework.

Sales Agent profile factories, exact matrix validation, target freeze configuration,
combined study analysis and case authoring are separate milestones. No study
vocabulary, values or target rules enter generic prospective code.

See [the workflow/API contract](../prospective-judging.md) and
[the living ExecPlan](../plans/salesagent-study-v1-readiness.md).
