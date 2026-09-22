# 0002. Normalize structured evidence at target boundaries

Date: 2026-09-19
Status: Accepted (approved Sales Agent ExecPlan)

## Context

The first HTTP target exposes structured commerce and multi-turn evidence.
TargetResponse previously offered only text, trajectory, and a raw debug field.
The runner must remain independent of Sales Agent contracts.

## Decision

Add defaulted `structured` and `metadata` dictionaries to TargetResponse.
Adapters own versioned normalization; the Sales Agent adapter keeps raw empty.
Structured assertions read declarative evaluator-only references. Existing
Score.passed conjunction gates quality; ERROR precedence remains unchanged.
Operational metadata is persisted but excluded from default semantic prompts,
including metadata nested within turn evidence.

Target identity is stable (`salesagent`). Deployment revision is separate
operator-supplied provenance. Evaluation configuration differences qualify run
comparisons; a target revision change alone does not change target identity.

## Consequences

Old serialized results load with empty dictionaries. SQLite requires no schema
migration. Core models contain no commerce types. Completed conversations retain
all turns; partial evidence on target exceptions remains unavailable under the
existing runner contract. Assertions and evidence schemas must be versioned.
