"""Descriptive comparison of complete and stored evaluation runs."""

from __future__ import annotations

import pytest

from harness.core.models import (
    AttemptResult,
    CaseResult,
    RunResult,
    Score,
    ScorerKind,
    TargetResponse,
    Verdict,
)
from harness.core.models import TestCase as EvaluationCase
from harness.core.runner import run
from harness.core.store import SQLiteResultStore
from harness.regression.comparison import compare_runs
from harness.scorers.exact_match import ExactMatchScorer
from harness.targets.base import StaticTarget


def _attempt(
    index: int,
    verdict: Verdict,
    *,
    scores: list[Score] | None = None,
) -> AttemptResult:
    return AttemptResult(
        index=index,
        response=(
            None if verdict is Verdict.ERROR else TargetResponse(output="response")
        ),
        scores=scores or [],
        verdict=verdict,
        error="infrastructure error" if verdict is Verdict.ERROR else None,
    )


def _case(case_id: str, *attempts: AttemptResult) -> CaseResult:
    return CaseResult(case_id=case_id, attempts=list(attempts))


def _result(
    run_id: str,
    *cases: CaseResult,
    target_name: str = "target",
    dataset_hash: str = "dataset",
    model_versions: dict[str, str] | None = None,
) -> RunResult:
    return RunResult(
        run_id=run_id,
        config_path="<inline>",
        config_snapshot={},
        target_name=target_name,
        pack_name="none",
        dataset_path="<inline>",
        dataset_hash=dataset_hash,
        model_versions=model_versions or {},
        cases=list(cases),
    )


def test_stored_runs_compare_end_to_end(tmp_path):
    cases = [
        EvaluationCase(id="c1", input="2+2?", reference="4"),
        EvaluationCase(id="c2", input="2+3?", reference="5"),
    ]
    baseline = run(
        StaticTarget(
            {"c1": TargetResponse(output="4"), "c2": TargetResponse(output="5")}
        ),
        [ExactMatchScorer()],
        cases,
    )
    candidate = run(
        StaticTarget(
            {
                "c1": TargetResponse(output="wrong"),
                "c2": TargetResponse(output="5"),
            }
        ),
        [ExactMatchScorer()],
        cases,
    )
    store = SQLiteResultStore(tmp_path / "runs.sqlite")
    store.save(baseline)
    store.save(candidate)

    comparison = compare_runs(
        store.load(baseline.run_id), store.load(candidate.run_id)
    )

    assert comparison.aggregate_pass_rate.baseline == 1.0
    assert comparison.aggregate_pass_rate.candidate == 0.5
    assert comparison.aggregate_pass_rate.delta == -0.5
    assert comparison.error_rate.delta == 0.0
    assert comparison.regressed_case_ids == ("c1",)
    assert comparison.improved_case_ids == ()
    c1 = comparison.cases[0]
    assert c1.pass_rate.delta == -1.0
    assert c1.scores[0].name == "exact_match"
    assert c1.scores[0].metric.delta == -1.0
    assert comparison.dataset_changed is False
    assert comparison.target_changed is False


def test_added_and_removed_cases_preserve_dataset_order():
    baseline = _result(
        "baseline",
        _case("removed", _attempt(0, Verdict.PASS)),
        _case("common", _attempt(0, Verdict.PASS)),
    )
    candidate = _result(
        "candidate",
        _case("common", _attempt(0, Verdict.PASS)),
        _case("added-second", _attempt(0, Verdict.PASS)),
        _case("added-third", _attempt(0, Verdict.PASS)),
    )

    comparison = compare_runs(baseline, candidate)

    assert [case.case_id for case in comparison.cases] == ["common"]
    assert comparison.removed_case_ids == ("removed",)
    assert comparison.added_case_ids == ("added-second", "added-third")


def test_loss_of_quality_evidence_is_not_reported_as_a_regression():
    baseline = _result("baseline", _case("c1", _attempt(0, Verdict.PASS)))
    candidate = _result("candidate", _case("c1", _attempt(0, Verdict.ERROR)))

    comparison = compare_runs(baseline, candidate)

    case = comparison.cases[0]
    assert case.pass_rate.baseline == 1.0
    assert case.pass_rate.candidate is None
    assert case.pass_rate.delta is None
    assert case.error_rate.delta == 1.0
    assert comparison.lost_evidence_case_ids == ("c1",)
    assert comparison.regressed_case_ids == ()


def test_gain_of_quality_evidence_is_recorded_separately():
    baseline = _result("baseline", _case("c1", _attempt(0, Verdict.ERROR)))
    candidate = _result("candidate", _case("c1", _attempt(0, Verdict.FAIL)))

    comparison = compare_runs(baseline, candidate)

    assert comparison.gained_evidence_case_ids == ("c1",)
    assert comparison.cases[0].pass_rate.delta is None
    assert comparison.improved_case_ids == ()


def test_scores_are_compared_by_name_using_attempt_means():
    baseline = _result(
        "baseline",
        _case(
            "c1",
            _attempt(
                0,
                Verdict.PASS,
                scores=[
                    Score(name="faithfulness", kind=ScorerKind.JUDGED, value=0.4)
                ],
            ),
            _attempt(
                1,
                Verdict.PASS,
                scores=[
                    Score(name="faithfulness", kind=ScorerKind.JUDGED, value=0.8)
                ],
            ),
        ),
    )
    candidate = _result(
        "candidate",
        _case(
            "c1",
            _attempt(
                0,
                Verdict.PASS,
                scores=[
                    Score(name="faithfulness", kind=ScorerKind.JUDGED, value=0.8),
                    Score(name="new_metric", kind=ScorerKind.DETERMINISTIC, value=0.5),
                ],
            ),
            _attempt(
                1,
                Verdict.PASS,
                scores=[
                    Score(name="faithfulness", kind=ScorerKind.JUDGED, value=1.0)
                ],
            ),
        ),
    )

    scores = compare_runs(baseline, candidate).cases[0].scores

    assert [score.name for score in scores] == ["faithfulness", "new_metric"]
    assert scores[0].metric.baseline == pytest.approx(0.6)
    assert scores[0].metric.candidate == pytest.approx(0.9)
    assert scores[0].metric.delta == pytest.approx(0.3)
    assert scores[1].metric.baseline is None
    assert scores[1].metric.candidate == 0.5
    assert scores[1].metric.delta is None


def test_metadata_changes_are_flagged_without_blocking_comparison():
    baseline = _result(
        "baseline",
        _case("c1", _attempt(0, Verdict.PASS)),
        target_name="target-v1",
        dataset_hash="dataset-v1",
        model_versions={"target": "model-v1"},
    )
    candidate = _result(
        "candidate",
        _case("c1", _attempt(0, Verdict.PASS)),
        target_name="target-v2",
        dataset_hash="dataset-v2",
        model_versions={"target": "model-v2"},
    )

    comparison = compare_runs(baseline, candidate)

    assert comparison.target_changed is True
    assert comparison.dataset_changed is True
    assert comparison.model_versions_changed is True
    assert len(comparison.cases) == 1


def test_duplicate_case_ids_are_rejected():
    duplicate = _result(
        "duplicate-run",
        _case("c1", _attempt(0, Verdict.PASS)),
        _case("c1", _attempt(0, Verdict.FAIL)),
    )
    candidate = _result("candidate", _case("c1", _attempt(0, Verdict.PASS)))

    with pytest.raises(ValueError, match="duplicate case id 'c1'"):
        compare_runs(duplicate, candidate)
