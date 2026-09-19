"""Offline vertical-slice tests for the minimal evaluation runner."""

from __future__ import annotations

from typing import Any

import pytest

from harness.core.models import (
    RunResult,
    Score,
    ScorerKind,
    TargetResponse,
    Verdict,
)
from harness.core.models import TestCase as EvaluationCase
from harness.core.runner import run
from harness.scorers.exact_match import ExactMatchScorer
from harness.targets.base import CAP_CONTEXTS, StaticTarget


class StubScorer:
    def __init__(
        self,
        name: str,
        *,
        passed: bool | None = True,
        requires: frozenset[str] = frozenset(),
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self.kind = ScorerKind.DETERMINISTIC
        self.requires = requires
        self.passed = passed
        self.error = error
        self.calls: list[str] = []

    def score(self, case: EvaluationCase, response: TargetResponse) -> Score:
        self.calls.append(case.id)
        if self.error is not None:
            raise self.error
        return Score(
            name=self.name,
            kind=self.kind,
            value=1.0 if self.passed is not False else 0.0,
            passed=self.passed,
        )


class RecordingStaticTarget(StaticTarget):
    def __init__(self, responses: dict[str, TargetResponse]) -> None:
        super().__init__(responses)
        self.received: list[EvaluationCase] = []

    def invoke(self, case: EvaluationCase) -> TargetResponse:
        self.received.append(case)
        return super().invoke(case)


class CloseableStaticTarget(StaticTarget):
    def __init__(self, responses: dict[str, TargetResponse]) -> None:
        super().__init__(responses)
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _case(
    case_id: str = "c1",
    *,
    reference: str = "4",
    tags: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> EvaluationCase:
    return EvaluationCase(
        id=case_id,
        input="What is 2+2?",
        reference=reference,
        tags=tags or [],
        extra=extra or {},
    )


def test_complete_offline_evaluation_path_records_passes_and_failures():
    cases = [_case("passing"), _case("failing")]
    target = StaticTarget(
        {
            "passing": TargetResponse(output="4"),
            "failing": TargetResponse(output="5"),
        }
    )

    result = run(target, [ExactMatchScorer()], cases)

    assert target.calls == ["passing", "failing"]
    assert result.target_name == "static"
    assert result.pack_name == "none"
    assert result.config_path == "<inline>"
    assert result.dataset_path == "<inline>"
    assert len(result.dataset_hash) == 64
    assert result.finished_at is not None
    assert result.config_snapshot["attempts"] == 1
    assert result.config_snapshot["scorers"] == [
        {"name": "exact_match", "kind": "deterministic", "requires": []}
    ]

    passing, failing = result.cases
    assert passing.attempts[0].response == TargetResponse(output="4")
    assert passing.attempts[0].scores[0].name == "exact_match"
    assert passing.attempts[0].verdict is Verdict.PASS
    assert passing.pass_rate == 1.0
    assert failing.attempts[0].verdict is Verdict.FAIL
    assert failing.pass_rate == 0.0
    assert result.aggregate_pass_rate == 0.5
    assert result.error_rate == 0.0


def test_multiple_attempts_are_executed_and_retained():
    target = StaticTarget({"c1": TargetResponse(output="4")})

    result = run(target, [ExactMatchScorer()], [_case()], attempts=3)

    assert target.calls == ["c1", "c1", "c1"]
    assert [attempt.index for attempt in result.cases[0].attempts] == [0, 1, 2]
    assert result.cases[0].pass_rate == 1.0


def test_multiple_scorers_receive_the_same_response():
    first = StubScorer("first")
    second = StubScorer("second")

    result = run(
        StaticTarget({"c1": TargetResponse(output="4")}),
        [first, second],
        [_case()],
    )

    assert first.calls == ["c1"]
    assert second.calls == ["c1"]
    assert [score.name for score in result.cases[0].attempts[0].scores] == [
        "first",
        "second",
    ]


def test_any_gated_failure_makes_the_attempt_fail():
    result = run(
        StaticTarget({"c1": TargetResponse(output="4")}),
        [StubScorer("passing"), StubScorer("failing", passed=False)],
        [_case()],
    )

    assert result.cases[0].attempts[0].verdict is Verdict.FAIL


def test_informational_only_scores_produce_skip():
    result = run(
        StaticTarget({"c1": TargetResponse(output="4")}),
        [StubScorer("information", passed=None)],
        [_case()],
    )

    attempt = result.cases[0].attempts[0]
    assert attempt.verdict is Verdict.SKIP
    assert result.cases[0].pass_rate is None


def test_target_error_is_not_recorded_as_a_quality_failure():
    result = run(StaticTarget({}), [ExactMatchScorer()], [_case()])

    attempt = result.cases[0].attempts[0]
    assert attempt.verdict is Verdict.ERROR
    assert attempt.response is None
    assert attempt.scores == []
    assert "target 'static': LookupError" in (attempt.error or "")
    assert result.cases[0].pass_rate is None
    assert result.error_rate == 1.0


def test_scorer_error_preserves_response_and_successful_scores():
    exploding = StubScorer("broken", error=RuntimeError("judge unavailable"))
    after_error = StubScorer("after_error")
    result = run(
        StaticTarget({"c1": TargetResponse(output="4")}),
        [ExactMatchScorer(), exploding, after_error],
        [_case()],
    )

    attempt = result.cases[0].attempts[0]
    assert attempt.verdict is Verdict.ERROR
    assert attempt.response == TargetResponse(output="4")
    assert [score.name for score in attempt.scores] == ["exact_match", "after_error"]
    assert after_error.calls == ["c1"]
    assert "scorer 'broken': RuntimeError: judge unavailable" in (attempt.error or "")
    assert result.cases[0].pass_rate is None


def test_missing_exact_match_reference_becomes_an_error():
    case = EvaluationCase(id="c1", input="question")
    result = run(
        StaticTarget({"c1": TargetResponse(output="answer")}),
        [ExactMatchScorer()],
        [case],
    )

    attempt = result.cases[0].attempts[0]
    assert attempt.verdict is Verdict.ERROR
    assert "requires a string reference" in (attempt.error or "")


def test_tags_are_retained_and_case_metadata_reaches_the_target():
    case = _case(
        tags=["prompt-injection", "safety", "RAG", "agent-behaviour"],
        extra={"attack_family": "indirect"},
    )
    target = RecordingStaticTarget({"c1": TargetResponse(output="4")})

    result = run(target, [ExactMatchScorer()], [case])

    assert result.cases[0].tags == case.tags
    assert target.received == [case]
    assert target.received[0].extra == {"attack_family": "indirect"}


def test_closeable_target_is_closed_when_an_attempt_errors():
    target = CloseableStaticTarget({})

    run(target, [ExactMatchScorer()], [_case()])

    assert target.closed is True


def test_result_round_trips_through_json():
    result = run(
        StaticTarget({"c1": TargetResponse(output="4")}),
        [ExactMatchScorer()],
        [_case()],
        attempts=2,
    )

    restored = RunResult.model_validate_json(result.model_dump_json())
    assert restored.model_dump() == result.model_dump()


@pytest.mark.parametrize(
    ("scorers", "cases", "attempts", "message"),
    [
        ([ExactMatchScorer()], [_case()], 0, "attempts must be at least 1"),
        ([ExactMatchScorer()], [], 1, "At least one test case"),
        ([], [_case()], 1, "At least one scorer"),
        (
            [ExactMatchScorer()],
            [_case("duplicate"), _case("duplicate")],
            1,
            "Duplicate test case ids: duplicate",
        ),
        (
            [StubScorer("duplicate"), StubScorer("duplicate")],
            [_case()],
            1,
            "Duplicate scorer names: duplicate",
        ),
    ],
)
def test_invalid_runs_fail_before_target_invocation(scorers, cases, attempts, message):
    target = StaticTarget({"c1": TargetResponse(output="4")})

    with pytest.raises(ValueError, match=message):
        run(target, scorers, cases, attempts=attempts)

    assert target.calls == []


def test_capability_mismatch_fails_before_target_invocation():
    target = StaticTarget({"c1": TargetResponse(output="4")})
    scorer = StubScorer("context_scorer", requires=frozenset({CAP_CONTEXTS}))

    with pytest.raises(ValueError, match="missing required capabilities: contexts"):
        run(target, [scorer], [_case()])

    assert target.calls == []
