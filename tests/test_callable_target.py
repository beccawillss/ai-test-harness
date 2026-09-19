"""Callable target behavior and its evaluation-runner integration."""

from __future__ import annotations

from typing import Any

import pytest

from harness.core.models import RunResult, TargetResponse, ToolCall, Verdict
from harness.core.models import TestCase as EvaluationCase
from harness.core.runner import run
from harness.scorers.exact_match import ExactMatchScorer
from harness.targets.base import (
    CAP_CONTEXTS,
    CAP_TRAJECTORY,
    CallableTarget,
    Target,
)


def _case() -> EvaluationCase:
    return EvaluationCase(
        id="rag-case",
        input={"question": "What is the capital of France?"},
        reference="Paris",
        tags=["RAG", "agent-behaviour"],
        extra={"tenant": "demo"},
    )


def test_callable_target_satisfies_protocol_and_forwards_complete_case():
    received: list[EvaluationCase] = []
    response = TargetResponse(
        output="Paris",
        contexts=["Paris is the capital of France."],
        trajectory=[ToolCall(name="search", arguments={"query": "France capital"})],
        latency_ms=12.5,
        cost_usd=0.001,
        raw={"request_id": "req-1"},
    )

    def application(case: EvaluationCase) -> TargetResponse:
        received.append(case)
        return response

    declared_capabilities = {CAP_CONTEXTS, CAP_TRAJECTORY}
    target = CallableTarget(
        name="local-rag-agent@v1",
        invoke=application,
        capabilities=declared_capabilities,
    )
    declared_capabilities.clear()

    assert isinstance(target, Target)
    assert target.name == "local-rag-agent@v1"
    assert target.capabilities == frozenset({CAP_CONTEXTS, CAP_TRAJECTORY})
    assert target.invoke(_case()) is response
    assert received == [_case()]


def test_callable_target_runs_multiple_attempts_and_round_trips_result():
    received: list[EvaluationCase] = []

    def application(case: EvaluationCase) -> TargetResponse:
        received.append(case)
        return TargetResponse(
            output="Paris",
            contexts=["Paris is the capital of France."],
        )

    result = run(
        CallableTarget(
            name="local-rag@v1",
            invoke=application,
            capabilities={CAP_CONTEXTS},
        ),
        [ExactMatchScorer()],
        [_case()],
        attempts=2,
    )

    assert received == [_case(), _case()]
    assert result.target_name == "local-rag@v1"
    assert result.config_snapshot["target_capabilities"] == [CAP_CONTEXTS]
    assert [attempt.verdict for attempt in result.cases[0].attempts] == [
        Verdict.PASS,
        Verdict.PASS,
    ]
    assert result.cases[0].attempts[0].response == TargetResponse(
        output="Paris",
        contexts=["Paris is the capital of France."],
    )
    restored = RunResult.model_validate_json(result.model_dump_json())
    assert restored.model_dump() == result.model_dump()


def test_callable_exception_is_recorded_as_infrastructure_error():
    def unavailable(_case: EvaluationCase) -> TargetResponse:
        raise TimeoutError("application timed out")

    result = run(
        CallableTarget(name="unavailable-app", invoke=unavailable),
        [ExactMatchScorer()],
        [_case()],
    )

    attempt = result.cases[0].attempts[0]
    assert attempt.verdict is Verdict.ERROR
    assert attempt.response is None
    assert attempt.scores == []
    assert "target 'unavailable-app': TimeoutError: application timed out" == attempt.error
    assert result.aggregate_pass_rate is None
    assert result.error_rate == 1.0


def test_invalid_callable_return_is_recorded_as_infrastructure_error():
    def invalid(_case: EvaluationCase) -> Any:
        return {"output": "Paris"}

    result = run(
        CallableTarget(name="invalid-app", invoke=invalid),
        [ExactMatchScorer()],
        [_case()],
    )

    attempt = result.cases[0].attempts[0]
    assert attempt.verdict is Verdict.ERROR
    assert attempt.response is None
    assert attempt.scores == []
    assert attempt.error == (
        "target 'invalid-app': TypeError: CallableTarget invoke must return "
        "TargetResponse, got dict."
    )


def test_capability_mismatch_fails_before_callable_invocation():
    calls = 0

    def application(_case: EvaluationCase) -> TargetResponse:
        nonlocal calls
        calls += 1
        return TargetResponse(output="Paris")

    target = CallableTarget(name="plain-app", invoke=application)

    class ContextScorer:
        name = "context"
        kind = ExactMatchScorer.kind
        requires = frozenset({CAP_CONTEXTS})

        def score(self, case: EvaluationCase, response: TargetResponse):
            return ExactMatchScorer().score(case, response)

    with pytest.raises(ValueError, match="missing required capabilities: contexts"):
        run(target, [ContextScorer()], [_case()])

    assert calls == 0


@pytest.mark.parametrize("name", ["", "   "])
def test_callable_target_rejects_empty_names(name: str):
    with pytest.raises(ValueError, match="name must not be empty"):
        CallableTarget(
            name=name,
            invoke=lambda _case: TargetResponse(output="unused"),
        )


def test_callable_target_rejects_non_callable_invoker():
    with pytest.raises(TypeError, match="invoke must be callable"):
        CallableTarget(name="invalid", invoke=None)  # type: ignore[arg-type]
