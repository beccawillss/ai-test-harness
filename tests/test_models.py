"""Tests for the core data models.

The focus is the pass-rate arithmetic, because that is where ADR 0001
lives: errors must never be able to masquerade as quality failures, and
'no evidence' (None) must never collapse into 'all evidence is bad' (0.0).
"""

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


def _response(cost: float | None = None) -> TargetResponse:
    return TargetResponse(output="hi", cost_usd=cost)


def _attempt(
    index: int,
    verdict: Verdict,
    *,
    scores: list[Score] | None = None,
    cost: float | None = None,
) -> AttemptResult:
    return AttemptResult(
        index=index,
        response=None if verdict is Verdict.ERROR else _response(cost),
        scores=scores or [],
        verdict=verdict,
        error="boom" if verdict is Verdict.ERROR else None,
    )


def _case(case_id: str, *verdicts: Verdict) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        attempts=[_attempt(i, v) for i, v in enumerate(verdicts)],
    )


def _run(*cases: CaseResult) -> RunResult:
    return RunResult(
        config_path="evals/demo.yaml",
        config_snapshot={},
        target_name="static",
        pack_name="demo",
        dataset_path="data/demo.jsonl",
        dataset_hash="abc123",
        cases=list(cases),
    )


# -- CaseResult.pass_rate ---------------------------------------------------


def test_pass_rate_counts_only_judged_attempts():
    case = _case("c1", Verdict.PASS, Verdict.FAIL, Verdict.PASS, Verdict.ERROR)
    # The ERROR is excluded entirely: 2 of 3 judged attempts passed.
    assert case.pass_rate == 2 / 3


def test_pass_rate_is_none_when_every_attempt_errored():
    """The sharpest form of ADR 0001: a dead judge is not a 0% run."""
    case = _case("c1", Verdict.ERROR, Verdict.ERROR, Verdict.ERROR)
    assert case.pass_rate is None
    assert case.had_errors is True


def test_pass_rate_is_none_when_every_attempt_skipped():
    """Explore runs produce only SKIPs and so report no pass rate."""
    case = _case("c1", Verdict.SKIP, Verdict.SKIP)
    assert case.pass_rate is None
    assert case.had_errors is False


def test_pass_rate_zero_is_distinguishable_from_none():
    all_failed = _case("c1", Verdict.FAIL, Verdict.FAIL)
    all_errored = _case("c2", Verdict.ERROR, Verdict.ERROR)
    assert all_failed.pass_rate == 0.0
    assert all_errored.pass_rate is None


def test_pass_rate_is_none_for_a_case_with_no_attempts():
    assert CaseResult(case_id="c1").pass_rate is None


# -- RunResult.aggregate_pass_rate -----------------------------------------


def test_aggregate_skips_unjudged_cases():
    run = _run(
        _case("c1", Verdict.PASS, Verdict.PASS),  # 1.0
        _case("c2", Verdict.PASS, Verdict.FAIL),  # 0.5
        _case("c3", Verdict.ERROR, Verdict.ERROR),  # None — excluded
    )
    # Mean of the two judged cases, not (1.0 + 0.5 + 0.0) / 3.
    assert run.aggregate_pass_rate == 0.75


def test_aggregate_is_none_when_no_case_was_judged():
    run = _run(_case("c1", Verdict.ERROR), _case("c2", Verdict.SKIP))
    assert run.aggregate_pass_rate is None


def test_aggregate_is_none_for_an_empty_run():
    assert _run().aggregate_pass_rate is None


# -- RunResult.error_rate ---------------------------------------------------


def test_error_rate_counts_attempts_across_cases():
    run = _run(
        _case("c1", Verdict.PASS, Verdict.ERROR),
        _case("c2", Verdict.ERROR, Verdict.FAIL),
    )
    assert run.error_rate == 0.5


def test_error_rate_is_one_when_everything_errored():
    run = _run(_case("c1", Verdict.ERROR), _case("c2", Verdict.ERROR))
    assert run.aggregate_pass_rate is None
    assert run.error_rate == 1.0


def test_error_rate_is_zero_for_an_empty_run():
    assert _run().error_rate == 0.0


# -- the other derived helpers still cope with errored attempts -------------


def test_mean_score_averages_matching_scores_only():
    case = CaseResult(
        case_id="c1",
        attempts=[
            _attempt(
                0,
                Verdict.PASS,
                scores=[
                    Score(name="faithfulness", kind=ScorerKind.JUDGED, value=0.8),
                    Score(name="latency", kind=ScorerKind.DETERMINISTIC, value=0.1),
                ],
            ),
            _attempt(
                1,
                Verdict.FAIL,
                scores=[Score(name="faithfulness", kind=ScorerKind.JUDGED, value=0.4)],
            ),
            _attempt(2, Verdict.ERROR),  # no scores, response=None
        ],
    )
    assert case.mean_score("faithfulness") == pytest.approx(0.6)
    assert case.mean_score("latency") == pytest.approx(0.1)
    assert case.mean_score("nonexistent") is None


def test_total_cost_ignores_attempts_without_a_response():
    run = _run(
        CaseResult(
            case_id="c1",
            attempts=[
                _attempt(0, Verdict.PASS, cost=0.01),
                _attempt(1, Verdict.ERROR),  # response is None
                _attempt(2, Verdict.PASS, cost=None),  # response, but no cost
            ],
        )
    )
    assert run.total_cost_usd == 0.01


def test_run_result_round_trips_through_json():
    run = _run(_case("c1", Verdict.PASS, Verdict.ERROR))
    restored = RunResult.model_validate_json(run.model_dump_json())
    assert restored.model_dump() == run.model_dump()
    assert restored.cases[0].pass_rate == 1.0
