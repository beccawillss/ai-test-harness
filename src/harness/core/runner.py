"""Minimal synchronous evaluation runner."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from time import perf_counter

from harness.core.dataset import hash_cases
from harness.core.models import (
    AttemptResult,
    CaseResult,
    RunResult,
    Score,
    TargetResponse,
    TestCase,
    Verdict,
)
from harness.scorers.base import Scorer
from harness.targets.base import CloseableTarget, Target, check_pack_compatibility


def _duplicates(values: Sequence[str]) -> list[str]:
    return sorted(value for value, count in Counter(values).items() if count > 1)


def _validate_run(
    target: Target,
    scorers: Sequence[Scorer],
    cases: Sequence[TestCase],
    attempts: int,
) -> None:
    """Reject invalid runs before invoking a potentially expensive target."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1.")
    if not cases:
        raise ValueError("At least one test case is required.")
    if not scorers:
        raise ValueError("At least one scorer is required.")

    if duplicate_ids := _duplicates([case.id for case in cases]):
        raise ValueError(f"Duplicate test case ids: {', '.join(duplicate_ids)}.")
    if duplicate_names := _duplicates([scorer.name for scorer in scorers]):
        raise ValueError(f"Duplicate scorer names: {', '.join(duplicate_names)}.")

    required_capabilities = frozenset(
        capability for scorer in scorers for capability in scorer.requires
    )
    if missing := check_pack_compatibility(target, required_capabilities):
        raise ValueError(
            f"Target '{target.name}' is missing required capabilities: "
            f"{', '.join(missing)}."
        )


def _target_error(target: Target, exc: Exception) -> str:
    return f"target '{target.name}': {type(exc).__name__}: {exc}"


def _scorer_error(scorer: Scorer, exc: Exception) -> str:
    return f"scorer '{scorer.name}': {type(exc).__name__}: {exc}"


def _verdict_for(scores: Sequence[Score], errors: Sequence[str]) -> Verdict:
    if errors:
        return Verdict.ERROR
    gated_scores = [score for score in scores if score.passed is not None]
    if not gated_scores:
        return Verdict.SKIP
    return Verdict.PASS if all(score.passed for score in gated_scores) else Verdict.FAIL


def _execute_attempt(
    index: int,
    case: TestCase,
    target: Target,
    scorers: Sequence[Scorer],
) -> AttemptResult:
    started_at = datetime.now(UTC)
    started_clock = perf_counter()

    def duration_ms() -> float:
        return (perf_counter() - started_clock) * 1000

    try:
        response: TargetResponse = target.invoke(case)
    except Exception as exc:  # noqa: BLE001 - target errors are result data
        return AttemptResult(
            index=index,
            response=None,
            verdict=Verdict.ERROR,
            error=_target_error(target, exc),
            started_at=started_at,
            duration_ms=duration_ms(),
        )

    scores: list[Score] = []
    errors: list[str] = []
    for scorer in scorers:
        try:
            scores.append(scorer.score(case, response))
        except Exception as exc:  # noqa: BLE001 - scorer errors are result data
            errors.append(_scorer_error(scorer, exc))

    return AttemptResult(
        index=index,
        response=response,
        scores=scores,
        verdict=_verdict_for(scores, errors),
        error="; ".join(errors) if errors else None,
        started_at=started_at,
        duration_ms=duration_ms(),
    )


def _scorer_snapshot(scorer: Scorer) -> dict[str, object]:
    snapshot: dict[str, object] = {
        "name": scorer.name,
        "kind": scorer.kind.value,
        "requires": sorted(scorer.requires),
    }
    pass_threshold = getattr(scorer, "pass_threshold", None)
    if isinstance(pass_threshold, (int, float)):
        snapshot["pass_threshold"] = pass_threshold
    judge_model = getattr(scorer, "judge_model", None)
    if isinstance(judge_model, str):
        snapshot["judge_model"] = judge_model
    rubric = getattr(scorer, "rubric", None)
    if isinstance(rubric, str):
        snapshot["rubric"] = rubric
    schema_version = getattr(scorer, "schema_version", None)
    if isinstance(schema_version, str):
        snapshot["schema_version"] = schema_version
    return snapshot


def _model_versions(scorers: Sequence[Scorer]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for scorer in scorers:
        judge_model = getattr(scorer, "judge_model", None)
        if isinstance(judge_model, str):
            versions[f"judge:{scorer.name}"] = judge_model
    return versions


def run(
    target: Target,
    scorers: Sequence[Scorer],
    cases: Sequence[TestCase],
    *,
    attempts: int = 1,
    dataset_path: str = "<inline>",
) -> RunResult:
    """Run every case and scorer, returning one self-contained result."""
    selected_cases = list(cases)
    selected_scorers = list(scorers)
    _validate_run(target, selected_scorers, selected_cases, attempts)

    started_at = datetime.now(UTC)
    case_results: list[CaseResult] = []
    try:
        for case in selected_cases:
            case_results.append(
                CaseResult(
                    case_id=case.id,
                    tags=list(case.tags),
                    attempts=[
                        _execute_attempt(index, case, target, selected_scorers)
                        for index in range(attempts)
                    ],
                )
            )
    finally:
        if isinstance(target, CloseableTarget):
            target.close()

    return RunResult(
        config_path="<inline>",
        config_snapshot={
            "attempts": attempts,
            "target": target.name,
            "target_capabilities": sorted(target.capabilities),
            "scorers": [_scorer_snapshot(scorer) for scorer in selected_scorers],
        },
        target_name=target.name,
        pack_name="none",
        dataset_path=dataset_path,
        dataset_hash=hash_cases(selected_cases),
        model_versions=_model_versions(selected_scorers),
        started_at=started_at,
        finished_at=datetime.now(UTC),
        cases=case_results,
    )


__all__ = ["run"]
