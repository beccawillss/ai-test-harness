"""Provider-neutral rubric judge scoring and runner integration."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from harness.core.models import (
    ScorerKind,
    TargetResponse,
    ToolCall,
    Verdict,
)
from harness.core.models import TestCase as EvaluationCase
from harness.core.runner import run
from harness.scorers.base import MissingFieldError, Scorer
from harness.scorers.exact_match import ExactMatchScorer
from harness.scorers.rubric_judge import RubricJudgeScorer
from harness.targets.base import CAP_CONTEXTS, StaticTarget


def _scorer(
    judge_fn: Callable[[str], str],
    **overrides,
) -> RubricJudgeScorer:
    options = {
        "rubric": "The answer must be correct and directly address the question.",
        "name": "correctness",
        "pass_threshold": 0.7,
    }
    options.update(overrides)
    return RubricJudgeScorer(judge_fn, "judge-model-v1", **options)


def _case() -> EvaluationCase:
    return EvaluationCase(
        id="c1",
        input="What is the capital of France?",
        reference="Paris",
        tags=["geography"],
        extra={"difficulty": "easy"},
    )


def test_rubric_judge_satisfies_scorer_protocol():
    assert isinstance(_scorer(lambda _: '{"score": 1, "reason": "correct"}'), Scorer)


def test_builds_prompt_and_returns_passing_judged_score():
    prompts: list[str] = []

    def judge(prompt: str) -> str:
        prompts.append(prompt)
        return '{"score": 0.8, "reason": "The answer is correct."}'

    scorer = _scorer(judge)
    response = TargetResponse(
        output="Paris",
        contexts=["Paris is the capital of France."],
        trajectory=[ToolCall(name="search", arguments={"query": "France capital"})],
    )

    score = scorer.score(_case(), response)

    assert score.name == "correctness"
    assert score.kind is ScorerKind.JUDGED
    assert score.value == 0.8
    assert score.passed is True
    assert score.reason == "The answer is correct."
    assert score.extra == {"judge_model": "judge-model-v1"}
    prompt = prompts[0]
    assert "untrusted" in prompt
    assert scorer.rubric in prompt
    assert "What is the capital of France?" in prompt
    assert '"reference": "Paris"' in prompt
    assert '"contexts"' in prompt
    assert '"trajectory"' in prompt
    assert '"difficulty": "easy"' in prompt


def test_score_below_threshold_is_a_quality_failure():
    scorer = _scorer(lambda _: '{"score": 0.6, "reason": "Incomplete."}')

    score = scorer.score(_case(), TargetResponse(output="Maybe Paris"))

    assert score.value == 0.6
    assert score.passed is False


def test_score_equal_to_threshold_passes():
    scorer = _scorer(lambda _: '{"score": 0.7, "reason": "Sufficient."}')

    assert scorer.score(_case(), TargetResponse(output="Paris")).passed is True


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("not-json", "not valid JSON"),
        ("[]", "must be a JSON object"),
        ('{"reason": "missing score"}', "'score' must be a number"),
        ('{"score": true, "reason": "boolean"}', "'score' must be a number"),
        ('{"score": 1.1, "reason": "too high"}', "between 0.0 and 1.0"),
        ('{"score": 0.5}', "'reason' must be a non-empty string"),
        ('{"score": 0.5, "reason": "  "}', "'reason' must be a non-empty string"),
    ],
)
def test_malformed_judge_output_raises(raw, message):
    scorer = _scorer(lambda _: raw)

    with pytest.raises(ValueError, match=message):
        scorer.score(_case(), TargetResponse(output="Paris"))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"name": "  "}, "name must not be empty"),
        ({"rubric": "  "}, "Rubric must not be empty"),
        ({"pass_threshold": -0.1}, "between 0.0 and 1.0"),
        ({"pass_threshold": 1.1}, "between 0.0 and 1.0"),
        ({"pass_threshold": True}, "between 0.0 and 1.0"),
    ],
)
def test_invalid_configuration_is_rejected(overrides, message):
    with pytest.raises(ValueError, match=message):
        _scorer(lambda _: '{"score": 1, "reason": "correct"}', **overrides)


def test_empty_judge_model_is_rejected():
    with pytest.raises(ValueError, match="model must not be empty"):
        RubricJudgeScorer(
            lambda _: '{"score": 1, "reason": "correct"}',
            "  ",
            rubric="Correctness",
        )


def test_required_response_field_is_checked_before_calling_judge():
    called = False

    def judge(_: str) -> str:
        nonlocal called
        called = True
        return '{"score": 1, "reason": "correct"}'

    scorer = _scorer(judge, requires=frozenset({CAP_CONTEXTS}))

    with pytest.raises(MissingFieldError, match="requires response field 'contexts'"):
        scorer.score(_case(), TargetResponse(output="Paris"))

    assert called is False


def test_runner_records_judge_score_and_model_version():
    scorer = _scorer(lambda _: '{"score": 0.9, "reason": "Correct."}')
    result = run(
        StaticTarget({"c1": TargetResponse(output="Paris")}),
        [scorer],
        [_case()],
    )

    attempt = result.cases[0].attempts[0]
    assert attempt.verdict is Verdict.PASS
    assert attempt.scores[0].kind is ScorerKind.JUDGED
    assert result.model_versions == {"judge:correctness": "judge-model-v1"}
    assert result.config_snapshot["scorers"] == [
        {
            "name": "correctness",
            "kind": "judged",
            "requires": [],
            "pass_threshold": 0.7,
            "judge_model": "judge-model-v1",
            "rubric": scorer.rubric,
        }
    ]


def test_judge_call_failure_becomes_infrastructure_error():
    def unavailable(_: str) -> str:
        raise ConnectionError("judge unavailable")

    result = run(
        StaticTarget({"c1": TargetResponse(output="Paris")}),
        [_scorer(unavailable)],
        [_case()],
    )

    attempt = result.cases[0].attempts[0]
    assert attempt.verdict is Verdict.ERROR
    assert attempt.scores == []
    assert "ConnectionError: judge unavailable" in (attempt.error or "")
    assert result.aggregate_pass_rate is None
    assert result.error_rate == 1.0


def test_malformed_judge_output_becomes_infrastructure_error():
    result = run(
        StaticTarget({"c1": TargetResponse(output="Paris")}),
        [_scorer(lambda _: "malformed")],
        [_case()],
    )

    attempt = result.cases[0].attempts[0]
    assert attempt.verdict is Verdict.ERROR
    assert "Judge output was not valid JSON" in (attempt.error or "")


def test_deterministic_and_judged_scorers_gate_together():
    judge = _scorer(lambda _: '{"score": 0.4, "reason": "Insufficient detail."}')
    result = run(
        StaticTarget({"c1": TargetResponse(output="Paris")}),
        [ExactMatchScorer(), judge],
        [_case()],
    )

    attempt = result.cases[0].attempts[0]
    assert [score.passed for score in attempt.scores] == [True, False]
    assert attempt.verdict is Verdict.FAIL


def test_multiple_attempts_call_judge_each_time():
    calls = 0

    def judge(_: str) -> str:
        nonlocal calls
        calls += 1
        return '{"score": 1.0, "reason": "Correct."}'

    result = run(
        StaticTarget({"c1": TargetResponse(output="Paris")}),
        [_scorer(judge)],
        [_case()],
        attempts=3,
    )

    assert calls == 3
    assert len(result.cases[0].attempts) == 3
    assert result.cases[0].pass_rate == 1.0
