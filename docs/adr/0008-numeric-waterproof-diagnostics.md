# ADR 0008: Bounded reference agreement diagnostics outside quality scoring

Status: architectural direction approved; Milestone 1 artifacts only. Independent
corpus review and source implementation are not approved/completed by this ADR.

## Context

Structured evidence checks establish commerce facts and constraint state, but
cannot establish that every assistant prose claim is supported. The existing
Sales Agent projection retains categorical waterproof ratings and drops unknown
fields. An absent numeric rating in that projection is not evidence that every
authoritative source lacks a numeric rating. A reference fact also does not
prove the agent had or used it when composing its answer.

Study v1 already separates deterministic capture from prospective semantic
judging. Its methodology, candidate cases, gates, fingerprints, rubric, thresholds
and historical artifacts must remain unchanged. A new diagnostic must not silently
redefine their verdicts or appear to supply a missing quality gate.

## Decision

Specify one bounded Sales Agent pack diagnostic over saved TargetResponse values,
with a separate report and no Score/runner integration. First support explicit
numeric waterproof/hydrostatic-head clauses with exactly normalized length units.
Preserve source spans, subject resolution, evidence references, temporal scope,
exclusions and uncertainty. Never infer a number from a categorical rating.

The assessed property is agreement with reviewed authoritative reference evidence
valid for the turn. It is neither real-world truth nor measured grounding in
information available to the agent. Agent grounding is explicitly not assessed.
An evaluator-owned manifest binds source revisions/content, review, completeness
and temporal applicability. Missing normalized keys cannot establish absence.

Separate supported, contradicted, unsupported-within-complete-reference-boundary,
and indeterminate findings. Non-claims are excluded; no detection is no assurance.
Missing optional authority is incompleteness, while malformed required evidence
is an execution error. Preserve unaffected turn findings for partial errors.

Use one diagnostic contract version plus configuration/content hashes, and a
separate revisioned corpus envelope. Do not create independent extraction,
projection, comparison and report registries. Do not change TargetResponse,
Scorer, Score, runner verdicts, result stores, or public target contracts.

Author a small synthetic corpus with exact labels before detector implementation.
Require independent human review of its spans, subjects, authority, findings and
errors. Keep development/acceptance fixtures separate from Study v1; visible
acceptance fixtures are not a blind holdout. Measure extraction and comparison
separately, reporting grammar, counts, false positives/negatives and abstentions.
Never tune this detector against future Study v1 live outputs.

## Alternatives and consequences

The existing semantic/human workflow remains the broader prose-quality mechanism.
An LLM extractor would introduce a separately calibrated judged component; defer
it. Target-reported claims could omit prose fabrications and require an external
contract change; defer them. Universal regex factuality gates are not justified
by narrow language recognition or a small corpus. A numeric Score for abstention
would invent quality evidence and may silently permit an overall PASS; avoid it.

The bounded diagnostic can explain detected reference disagreement offline, but
missed paraphrases remain false negatives. Reviewed reference completeness is a
substantive human judgment, not a schema consequence. Positive numeric-reference
fixtures are synthetic and do not claim the current Sales Agent adapter exposes
numeric values. Real reference authority/deployment bindings need separate review.

See the [contract](../salesagent-grounding-diagnostics-v1.md),
[ExecPlan](../plans/salesagent-waterproof-grounding-diagnostics.md), and
[independent review guide](../../tests/fixtures/salesagent_grounding/v1/README.md).
