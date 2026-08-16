"""Descriptive comparison of two evaluation runs."""

from __future__ import annotations

from dataclasses import dataclass

from harness.core.models import CaseResult, RunResult, Verdict


@dataclass(frozen=True, slots=True)
class MetricComparison:
    """A candidate-minus-baseline comparison of one numeric metric."""

    baseline: float | None
    candidate: float | None
    delta: float | None


@dataclass(frozen=True, slots=True)
class ScoreComparison:
    """Mean values for one stable scorer name."""

    name: str
    metric: MetricComparison


@dataclass(frozen=True, slots=True)
class CaseComparison:
    """Pass, error, and scorer changes for one case present in both runs."""

    case_id: str
    pass_rate: MetricComparison
    error_rate: MetricComparison
    scores: tuple[ScoreComparison, ...]


@dataclass(frozen=True, slots=True)
class RunComparison:
    """Structured descriptive differences between a baseline and candidate run."""

    baseline_run_id: str
    candidate_run_id: str
    aggregate_pass_rate: MetricComparison
    error_rate: MetricComparison
    cases: tuple[CaseComparison, ...]
    added_case_ids: tuple[str, ...]
    removed_case_ids: tuple[str, ...]
    gained_evidence_case_ids: tuple[str, ...]
    lost_evidence_case_ids: tuple[str, ...]
    target_changed: bool
    dataset_changed: bool
    model_versions_changed: bool

    @property
    def regressed_case_ids(self) -> tuple[str, ...]:
        """Cases whose measured pass rate decreased."""
        return tuple(
            case.case_id
            for case in self.cases
            if case.pass_rate.delta is not None and case.pass_rate.delta < 0
        )

    @property
    def improved_case_ids(self) -> tuple[str, ...]:
        """Cases whose measured pass rate increased."""
        return tuple(
            case.case_id
            for case in self.cases
            if case.pass_rate.delta is not None and case.pass_rate.delta > 0
        )


def _metric(baseline: float | None, candidate: float | None) -> MetricComparison:
    delta = None if baseline is None or candidate is None else candidate - baseline
    return MetricComparison(baseline=baseline, candidate=candidate, delta=delta)


def _case_error_rate(case: CaseResult) -> float:
    if not case.attempts:
        return 0.0
    errors = sum(attempt.verdict is Verdict.ERROR for attempt in case.attempts)
    return errors / len(case.attempts)


def _score_names(case: CaseResult) -> set[str]:
    return {score.name for attempt in case.attempts for score in attempt.scores}


def _index_cases(result: RunResult) -> dict[str, CaseResult]:
    indexed: dict[str, CaseResult] = {}
    for case in result.cases:
        if case.case_id in indexed:
            raise ValueError(
                f"Run '{result.run_id}' contains duplicate case id '{case.case_id}'."
            )
        indexed[case.case_id] = case
    return indexed


def compare_runs(baseline: RunResult, candidate: RunResult) -> RunComparison:
    """Compare two runs without deciding whether the candidate is acceptable."""
    baseline_cases = _index_cases(baseline)
    candidate_cases = _index_cases(candidate)

    common_ids = [
        case.case_id for case in baseline.cases if case.case_id in candidate_cases
    ]
    added_ids = tuple(
        case.case_id for case in candidate.cases if case.case_id not in baseline_cases
    )
    removed_ids = tuple(
        case.case_id for case in baseline.cases if case.case_id not in candidate_cases
    )

    case_comparisons: list[CaseComparison] = []
    gained_evidence: list[str] = []
    lost_evidence: list[str] = []
    for case_id in common_ids:
        baseline_case = baseline_cases[case_id]
        candidate_case = candidate_cases[case_id]
        baseline_pass_rate = baseline_case.pass_rate
        candidate_pass_rate = candidate_case.pass_rate

        if baseline_pass_rate is None and candidate_pass_rate is not None:
            gained_evidence.append(case_id)
        elif baseline_pass_rate is not None and candidate_pass_rate is None:
            lost_evidence.append(case_id)

        score_names = sorted(_score_names(baseline_case) | _score_names(candidate_case))
        case_comparisons.append(
            CaseComparison(
                case_id=case_id,
                pass_rate=_metric(baseline_pass_rate, candidate_pass_rate),
                error_rate=_metric(
                    _case_error_rate(baseline_case),
                    _case_error_rate(candidate_case),
                ),
                scores=tuple(
                    ScoreComparison(
                        name=name,
                        metric=_metric(
                            baseline_case.mean_score(name),
                            candidate_case.mean_score(name),
                        ),
                    )
                    for name in score_names
                ),
            )
        )

    return RunComparison(
        baseline_run_id=baseline.run_id,
        candidate_run_id=candidate.run_id,
        aggregate_pass_rate=_metric(
            baseline.aggregate_pass_rate, candidate.aggregate_pass_rate
        ),
        error_rate=_metric(baseline.error_rate, candidate.error_rate),
        cases=tuple(case_comparisons),
        added_case_ids=added_ids,
        removed_case_ids=removed_ids,
        gained_evidence_case_ids=tuple(gained_evidence),
        lost_evidence_case_ids=tuple(lost_evidence),
        target_changed=baseline.target_name != candidate.target_name,
        dataset_changed=baseline.dataset_hash != candidate.dataset_hash,
        model_versions_changed=baseline.model_versions != candidate.model_versions,
    )


__all__ = [
    "CaseComparison",
    "MetricComparison",
    "RunComparison",
    "ScoreComparison",
    "compare_runs",
]
