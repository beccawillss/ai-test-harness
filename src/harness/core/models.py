"""Core data models for the harness.

These models are the shared vocabulary of the whole system. Design rules:

1. The core knows nothing about RAG, agents, or adversarial testing.
   Pack-specific data travels in open `dict` fields (`extra`, `metadata`)
   so new packs never require core changes.
2. Nondeterminism is modelled, not ignored. A case is executed as one or
   more *attempts*; pass rates are first-class, binary verdicts are derived.
3. Everything is serialisable. A RunResult round-trips to JSON/SQLite so
   any run can be diffed against a baseline later.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return uuid4().hex[:12]


class Verdict(StrEnum):
    """Outcome of a single attempt or an aggregated case."""

    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"  # target or scorer raised — an infrastructure problem,
    # never counted as a quality failure
    SKIP = "skip"


class ScorerKind(StrEnum):
    DETERMINISTIC = "deterministic"
    JUDGED = "judged"  # LLM-as-judge — calibrated separately


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


class TestCase(BaseModel):
    """A single evaluation case, loaded from a dataset file.

    `input` is deliberately loose: a string for simple prompts, a dict for
    structured inputs (e.g. an agent task definition). `reference` holds
    whatever ground truth the scorers need — expected answer, relevant doc
    ids, success criteria — and may be absent for reference-free metrics.
    `extra` is the arbitrary case metadata container. Classification values
    are opaque; risk never changes scoring or gating semantics.
    """

    id: str
    input: str | dict[str, Any]
    reference: str | dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)  # e.g. ["retrieval", "smoke"]
    extra: dict[str, Any] = Field(default_factory=dict)
    # Omit only new null fields, preserving every legacy default/null and dump.
    title: str | None = Field(default=None, strict=True, exclude_if=lambda v: v is None)
    description: str | None = Field(
        default=None, strict=True, exclude_if=lambda v: v is None
    )
    category: str | None = Field(
        default=None, strict=True, exclude_if=lambda v: v is None
    )
    risk: str | None = Field(default=None, strict=True, exclude_if=lambda v: v is None)

    @field_validator("title", "category", "risk")
    @classmethod
    def nonblank_definition_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Definition text must not be blank")
        return value

    @field_validator("category", "risk")
    @classmethod
    def taxonomy_whitespace(cls, value: str | None) -> str | None:
        if value is not None and value != value.strip():
            raise ValueError("Taxonomy values must not have boundary whitespace")
        return value


# ---------------------------------------------------------------------------
# Target output
# ---------------------------------------------------------------------------


class ToolCall(BaseModel):
    """One step in an agent trajectory."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: str | dict[str, Any] | None = None
    error: str | None = None


class TargetResponse(BaseModel):
    """What a system-under-test returns for one case.

    Only `output` is required. RAG adapters must populate `contexts`;
    agent adapters must populate `trajectory`. Scorers that need a field
    should fail loudly (Verdict.ERROR) if the adapter didn't supply it —
    a misconfigured run must never look like a quality regression.
    """

    output: str
    contexts: list[str] | None = None  # RAG: retrieved chunks, in rank order
    trajectory: list[ToolCall] | None = None  # agents: full tool-call sequence
    latency_ms: float | None = None
    cost_usd: float | None = None
    structured: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)  # provider payload, for debugging


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


class Score(BaseModel):
    """One scorer's opinion on one attempt.

    `value` is always 0.0–1.0 so aggregation and trend charts never need
    per-metric scaling. `passed` is the scorer's own threshold applied to
    `value`; gates may aggregate differently.
    """

    name: str  # e.g. "context_recall@5", "faithfulness"
    kind: ScorerKind
    value: float = Field(ge=0.0, le=1.0)
    passed: bool | None = None  # None => informational metric, not gated
    reason: str | None = None  # judge rationale or diff summary
    extra: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


class AttemptResult(BaseModel):
    """One execution of one case. Repeats exist to measure stability."""

    index: int
    response: TargetResponse | None = None  # None when the target errored
    scores: list[Score] = Field(default_factory=list)
    verdict: Verdict
    error: str | None = None
    started_at: datetime = Field(default_factory=_utcnow)
    duration_ms: float | None = None


class CaseResult(BaseModel):
    """All attempts for one case, plus derived stability stats."""

    case_id: str
    tags: list[str] = Field(default_factory=list)
    attempts: list[AttemptResult] = Field(default_factory=list)

    @property
    def pass_rate(self) -> float | None:
        """Fraction of judged attempts that passed, or None when no attempt
        produced a pass/fail judgment at all. The unit of truth for gating —
        a case is not 'passing' or 'failing', it passes at a rate, exactly
        like a flaky test in a nightly run.

        None means 'no evidence' and is categorically different from 0.0,
        which means 'evidence, all of it bad'. A case whose every attempt
        errored (dead judge API, broken adapter) has no quality evidence;
        reporting it as 0.0 would be indistinguishable from a total product
        regression, which is exactly what ADR 0001 exists to prevent."""
        judged = [a for a in self.attempts if a.verdict in (Verdict.PASS, Verdict.FAIL)]
        if not judged:
            return None
        return sum(a.verdict is Verdict.PASS for a in judged) / len(judged)

    @property
    def had_errors(self) -> bool:
        return any(a.verdict is Verdict.ERROR for a in self.attempts)

    def mean_score(self, name: str) -> float | None:
        values = [s.value for a in self.attempts for s in a.scores if s.name == name]
        return sum(values) / len(values) if values else None


class RunResult(BaseModel):
    """A complete run: one target, one dataset, one pack, one config.

    This is the artifact that gets persisted, reported on, and compared
    against baselines. It must contain everything needed to explain
    itself months later without the original environment.
    """

    run_id: str = Field(default_factory=_new_id)
    config_path: str  # the YAML that defines this run
    config_snapshot: dict[str, Any]  # resolved config, frozen at run time
    target_name: str
    pack_name: str
    dataset_path: str
    dataset_hash: str  # detect silent golden-set drift
    model_versions: dict[str, str] = Field(default_factory=dict)
    # ^ pinned versions of every model involved: target model AND judge
    #   models. A judge upgrade can move scores with zero code changes.
    started_at: datetime = Field(default_factory=_utcnow)
    finished_at: datetime | None = None
    cases: list[CaseResult] = Field(default_factory=list)

    @property
    def aggregate_pass_rate(self) -> float | None:
        """Mean pass rate over the cases that were actually judged.

        Cases with no pass/fail evidence are excluded rather than counted
        as zero; None means the whole run produced no evidence. Always
        read alongside `error_rate` — a run can be green on quality while
        badly degraded on infrastructure."""
        rates = [r for c in self.cases if (r := c.pass_rate) is not None]
        if not rates:
            return None
        return sum(rates) / len(rates)

    @property
    def error_rate(self) -> float:
        """Fraction of all attempts that errored.

        The companion number to `aggregate_pass_rate`: errors are excluded
        from pass rates, so this is where they must show up instead."""
        attempts = [a for c in self.cases for a in c.attempts]
        if not attempts:
            return 0.0
        return sum(a.verdict is Verdict.ERROR for a in attempts) / len(attempts)

    @property
    def total_cost_usd(self) -> float:
        return sum(
            a.response.cost_usd or 0.0
            for c in self.cases
            for a in c.attempts
            if a.response is not None
        )


class Baseline(BaseModel):
    """A blessed RunResult, promoted deliberately via `harness bless`."""

    baseline_id: str = Field(default_factory=_new_id)
    run_id: str
    blessed_at: datetime = Field(default_factory=_utcnow)
    blessed_by: str | None = None  # human or CI identity — audit trail
    note: str | None = None  # why this run became the baseline
