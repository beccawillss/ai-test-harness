"""Offline tests of the optional provider contract and credential boundary."""

import copy
import json

import httpx
import pytest

from harness.core.models import TargetResponse, Verdict
from harness.core.models import TestCase as Case
from harness.core.runner import run
from harness.judges.openai import (
    ENDPOINT,
    INSTRUCTIONS,
    JudgeProviderError,
    OpenAIJudge,
)
from harness.scorers.rubric_judge import RubricJudgeScorer
from harness.targets.base import StaticTarget


def envelope(text='{"score":0.4,"reason":"The answer omits the requested next step."}'):
    return {
        "status": "completed",
        "model": "judge-snapshot",
        "output": [
            {"type": "reasoning", "summary": ["SECRET"]},
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {"type": "output_text", "text": text, "annotations": ["SECRET"]}
                ],
            },
        ],
        "usage": {
            "input_tokens": 10,
            "output_tokens": 20,
            "total_tokens": 30,
            "raw": "SECRET",
        },
        "raw": "SECRET",
    }


def test_request_reply_config_are_isolated_and_normalized(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "TARGET_SECRET")
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            200, json=envelope(), headers={"set-cookie": "session=do-not-reuse"}
        )

    judge = OpenAIJudge(
        api_key="JUDGE_SECRET",
        model="requested-model",
        transport=httpx.MockTransport(handle),
    )
    try:
        first, second = judge("first"), judge("second")
        assert first.observed_model == "judge-snapshot"
        assert first.input_tokens == 10 and first.total_tokens == 30
        assert first.latency_ms >= 0 and second.latency_ms >= 0
        assert first.cost_usd is None
        assert "SECRET" not in first.model_dump_json()
        assert "SECRET" not in json.dumps(judge.configuration)
        assert "SECRET" not in repr(judge)
        for request, prompt in zip(requests, ["first", "second"]):
            assert str(request.url) == ENDPOINT
            assert request.headers["authorization"] == "Bearer JUDGE_SECRET"
            assert "cookie" not in request.headers
            body = json.loads(request.content)
            assert body["input"] == [{"role": "user", "content": prompt}]
            assert body["instructions"] == INSTRUCTIONS
            assert (
                body["tools"] == []
                and body["store"] is False
                and body["stream"] is False
            )
            assert "previous_response_id" not in body and "conversation" not in body
            assert "SECRET" not in request.content.decode()
            assert body["text"]["format"]["strict"] is True
            assert body["text"]["format"]["schema"]["additionalProperties"] is False
            assert request.extensions["timeout"]["read"] == 120
    finally:
        judge.close()


@pytest.mark.parametrize("status", [301, 401, 429, 500, 503])
def test_http_errors_are_safe_and_never_retried(status):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            status, text="SECRET", headers={"location": "https://bad.invalid"}
        )

    judge = OpenAIJudge(
        api_key="SECRET", model="fake", transport=httpx.MockTransport(handle)
    )
    try:
        with pytest.raises(JudgeProviderError, match=f"HTTP status {status}") as exc:
            judge("prompt")
        assert "SECRET" not in str(exc.value) and len(requests) == 1
    finally:
        judge.close()


@pytest.mark.parametrize(
    "error,message",
    [
        (httpx.ReadTimeout("SECRET"), "timeout"),
        (httpx.ConnectError("SECRET"), "unavailable"),
        (RuntimeError("SECRET"), "execution unavailable"),
    ],
)
def test_transport_exceptions_are_safe(error, message):
    def handle(request):
        raise error

    judge = OpenAIJudge(
        api_key="SECRET", model="fake", transport=httpx.MockTransport(handle)
    )
    try:
        with pytest.raises(JudgeProviderError, match=message) as exc:
            judge("prompt")
        assert "SECRET" not in str(exc.value)
    finally:
        judge.close()


@pytest.mark.parametrize(
    "change",
    [
        "non_object",
        "not_json",
        "incomplete",
        "refusal",
        "missing_output",
        "empty_output",
        "duplicate_message",
        "duplicate_text",
        "blank_text",
        "nontext",
        "tool",
        "bad_role",
        "bad_usage",
        "boolean_tokens",
        "negative_tokens",
        "bad_model",
        "bad_content",
        "unfinished_message",
    ],
)
def test_malformed_provider_results_are_runner_errors_without_leaks(change):
    data = envelope()
    message = data["output"][1]
    if change == "non_object":
        data = []
    elif change == "incomplete":
        data["status"] = "incomplete"
    elif change == "refusal":
        message["content"] = [{"type": "refusal", "refusal": "SECRET"}]
    elif change == "missing_output":
        del data["output"]
    elif change == "empty_output":
        data["output"] = []
    elif change == "duplicate_message":
        data["output"].append(copy.deepcopy(message))
    elif change == "duplicate_text":
        message["content"].append(copy.deepcopy(message["content"][0]))
    elif change == "blank_text":
        message["content"][0]["text"] = " "
    elif change == "nontext":
        message["content"][0]["text"] = {}
    elif change == "tool":
        data["output"].append({"type": "function_call", "arguments": "SECRET"})
    elif change == "bad_role":
        message["role"] = "user"
    elif change == "bad_usage":
        data["usage"] = "SECRET"
    elif change == "boolean_tokens":
        data["usage"]["input_tokens"] = True
    elif change == "negative_tokens":
        data["usage"]["output_tokens"] = -1
    elif change == "bad_model":
        data["model"] = {}
    elif change == "bad_content":
        message["content"] = "SECRET"
    elif change == "unfinished_message":
        message["status"] = "in_progress"
    response = (
        httpx.Response(200, text="SECRET")
        if change == "not_json"
        else httpx.Response(200, json=data)
    )
    judge = OpenAIJudge(
        api_key="SECRET",
        model="fake",
        transport=httpx.MockTransport(lambda _: response),
    )
    try:
        result = run(
            StaticTarget({"c": TargetResponse(output="answer")}),
            [RubricJudgeScorer(judge, "fake", rubric="Helpful")],
            [Case(id="c", input="question")],
        )
        assert result.cases[0].attempts[0].verdict is Verdict.ERROR
        assert result.cases[0].attempts[0].scores == []
        assert "SECRET" not in result.model_dump_json()
    finally:
        judge.close()


def test_absent_observations_remain_unknown():
    data = envelope()
    del data["usage"], data["model"]
    judge = OpenAIJudge(
        api_key="key",
        model="fake",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data)),
    )
    try:
        reply = judge("prompt")
        assert (
            reply.input_tokens
            is reply.output_tokens
            is reply.total_tokens
            is reply.observed_model
            is reply.cost_usd
            is None
        )
    finally:
        judge.close()


@pytest.mark.parametrize(
    "config",
    [
        {"api_key": ""},
        {"api_key": "key\nsecret"},
        {"model": " "},
        {"read_timeout": 0},
        {"read_timeout": True},
        {"read_timeout": float("inf")},
        {"max_output_tokens": True},
        {"max_output_tokens": 0},
    ],
)
def test_invalid_configuration_never_constructs_client(config, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "TARGET_SECRET")
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: pytest.fail("client constructed")
    )
    with pytest.raises(ValueError):
        OpenAIJudge(**({"api_key": "key", "model": "fake"} | config))


def test_cleanup_exception_is_sanitized():
    class BadClose(httpx.MockTransport):
        def close(self):
            raise RuntimeError("SECRET")

    judge = OpenAIJudge(
        api_key="key", model="fake", transport=BadClose(lambda _: httpx.Response(500))
    )
    with pytest.warns(
        RuntimeWarning, match="Judge HTTP client cleanup failed"
    ) as warnings:
        judge.close()
    assert "SECRET" not in str(warnings[0].message)
