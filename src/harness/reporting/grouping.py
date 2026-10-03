"""Pure classification summaries of persisted evidence, never current datasets."""

from __future__ import annotations

import string
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from harness.core.models import CaseResult, RunResult, Verdict

GroupDimension = Literal["category", "tags", "risk"]
ClassificationState = Literal["value", "unclassified", "unavailable", "untagged"]


@dataclass(frozen=True, slots=True)
class ScorerEvidence:
    name: str
    mean: float
    evidence_count: int


@dataclass(frozen=True, slots=True)
class GroupResult:
    """JSON-serializable through dataclasses.asdict; tags overlap across groups."""

    dimension: GroupDimension
    value: str | None
    classification_state: ClassificationState
    definition_availability: Literal["complete", "partial", "unavailable"]
    definition_count: int
    member_case_ids: tuple[str, ...]
    case_count: int
    judged_case_count: int
    attempt_count: int
    pass_count: int
    fail_count: int
    error_count: int
    skip_count: int
    quality_pass_rate: float | None
    error_rate: float
    scorers: tuple[ScorerEvidence, ...]
    totals_additive: bool


def group_run_results(
    result: RunResult, *, by: GroupDimension
) -> tuple[GroupResult, ...]:
    """First-observed group order and run case order; no input mutation or I/O."""
    if by not in ("category", "tags", "risk"):
        raise ValueError("Grouping dimension must be category, tags or risk")
    groups: dict[tuple[ClassificationState, str | None], list[CaseResult]] = {}
    seen: set[str] = set()
    for case in result.cases:
        if case.case_id in seen:
            raise ValueError("Duplicate case IDs prevent unambiguous grouping")
        seen.add(case.case_id)
        keys: list[tuple[ClassificationState, str | None]]
        if by == "tags":
            # Historical tags are recorded evidence even without definition snapshots.
            keys = [("value", tag) for tag in dict.fromkeys(case.tags)] or [
                ("untagged", None)
            ]
        elif case.definition is None:
            keys = [("unavailable", None)]
        else:
            value = getattr(case.definition, by)
            keys = [("unclassified" if value is None else "value", value)]
        for key in keys:
            groups.setdefault(key, []).append(case)

    records = []
    for (state, value), cases in groups.items():
        attempts = [attempt for case in cases for attempt in case.attempts]
        counts = Counter(attempt.verdict for attempt in attempts)
        rates = [rate for case in cases if (rate := case.pass_rate) is not None]
        evidence: dict[str, list[float]] = {}
        for attempt in attempts:
            for score in attempt.scores:
                evidence.setdefault(score.name, []).append(score.value)
        definitions = sum(case.definition is not None for case in cases)
        records.append(
            GroupResult(
                dimension=by,
                value=value,
                classification_state=state,
                definition_availability="complete"
                if definitions == len(cases)
                else "partial"
                if definitions
                else "unavailable",
                definition_count=definitions,
                member_case_ids=tuple(case.case_id for case in cases),
                case_count=len(cases),
                judged_case_count=len(rates),
                attempt_count=len(attempts),
                pass_count=counts[Verdict.PASS],
                fail_count=counts[Verdict.FAIL],
                error_count=counts[Verdict.ERROR],
                skip_count=counts[Verdict.SKIP],
                quality_pass_rate=sum(rates) / len(rates) if rates else None,
                error_rate=counts[Verdict.ERROR] / len(attempts) if attempts else 0.0,
                scorers=tuple(
                    ScorerEvidence(name, sum(values) / len(values), len(values))
                    for name, values in sorted(evidence.items())
                ),
                totals_additive=by != "tags",
            )
        )
    return tuple(records)


def escape_markdown_text(value: str) -> str:
    """Entity-escape authored punctuation/line breaks before Markdown parsing."""
    return "".join(
        f"&#{ord(char)};"
        if char in string.punctuation or (char.isspace() and char != " ")
        else char
        for char in value
    )


def _number(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:.3f}"


def render_groups_markdown(
    groups: tuple[GroupResult, ...], *, title: str = "Grouped results"
) -> str:
    lines = [f"## {escape_markdown_text(title)}", ""]
    if any(not group.totals_additive for group in groups):
        lines += ["Tag groups overlap; totals are non-additive.", ""]
    lines += [
        "| Dimension | Value | Classification | Definitions | Cases / judged | Attempts | PASS | FAIL | ERROR | SKIP | Quality pass rate | Error rate | Scorer mean (evidence count) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for group in groups:
        scores = (
            "; ".join(
                f"{escape_markdown_text(s.name)}: {_number(s.mean)} ({s.evidence_count})"
                for s in group.scorers
            )
            or "none"
        )
        value = "null" if group.value is None else escape_markdown_text(group.value)
        lines.append(
            f"| {group.dimension} | {value} | {group.classification_state} | {group.definition_availability} | "
            f"{group.case_count} / {group.judged_case_count} | {group.attempt_count} | {group.pass_count} | {group.fail_count} | "
            f"{group.error_count} | {group.skip_count} | {_number(group.quality_pass_rate)} | {_number(group.error_rate)} | {scores} |"
        )
    return "\n".join(lines) + "\n"


__all__ = [
    "GroupDimension",
    "GroupResult",
    "ScorerEvidence",
    "group_run_results",
    "render_groups_markdown",
]
