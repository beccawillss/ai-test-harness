"""Public HTTP contract fixtures; never import the Sales Agent application."""

import copy
import json

import httpx
import pytest

from harness.core.models import TargetResponse, Verdict
from harness.core.models import TestCase as Case
from harness.core.runner import run
from harness.scorers.rubric_judge import RubricJudgeScorer
from harness.targets.base import Target
from harness.targets.salesagent import SalesAgentTarget


def product():
    return {
        "product_id": "JKT-001",
        "name": "Jacket",
        "price": "145.00",
        "currency": "GBP",
        "product_url": "/products/apex-alpine",
        "category": "jacket",
        "activities": ["hiking"],
        "weather": ["heavy-rain"],
        "features": ["waterproof"],
        "waterproof_rating": "high",
        "variants": [{"colour": "Ocean Blue", "size": "M", "stock": 4}],
        "total_stock": 4,
    }


def tool():
    return {
        "sequence": 1,
        "tool_call_id": "tool-1",
        "tool_name": "get_product",
        "arguments": {"product_id": "JKT-001"},
        "status": "success",
        "duration_ms": 2,
        "result": {
            "tool_name": "get_product",
            "success": True,
            "data": product(),
            "error": None,
        },
    }


class FakeHTTP:
    def __init__(self, mutate=None):
        self.requests = []
        self.sessions = {}
        self.traces = {}
        self.mutate = mutate

    def __call__(self, request):
        self.requests.append(request)
        assert "cookie" not in request.headers
        assert "authorization" not in request.headers
        if request.method == "POST":
            body = json.loads(request.content)
            assert set(body) <= {"message", "session_id"}
            session = body.get("session_id")
            if session is None:
                session = f"session-{len(self.sessions)}"
                self.sessions[session] = 0
            self.sessions[session] += 1
            trace_id = f"trace-{len(self.traces)}"
            rec = {
                k: v
                for k, v in product().items()
                if k in {"product_id", "name", "price", "currency", "product_url"}
            }
            rec.update(price=145.0, availability="in_stock", matched_variant=None)
            chat = {
                "session_id": session,
                "trace_id": trace_id,
                "message": "Here is a jacket.",
                "recommendations": [rec],
                "promotion": None,
                "pricing": None,
            }
            trace = {
                "session_id": session,
                "trace_id": trace_id,
                "timestamp": "2026-09-19T00:00:00Z",
                "turn_index": self.sessions[session],
                "user_message": body["message"],
                "model": "fake-model",
                "prompt_version": "p1",
                "resolved_constraints": {"maximum_price": 160},
                "constraint_changes": [
                    {"field": "maximum_price", "previous": None, "current": 160}
                ],
                "tool_calls": [tool()],
                "recommendation_validation": {
                    "all_products_exist": True,
                    "prices_match_catalogue": True,
                    "urls_match_catalogue": True,
                    "stock_claims_validated": True,
                    "validation_errors": [],
                },
                "recommended_product_ids": ["JKT-001"],
                "promotion": None,
                "pricing": None,
                "latency_ms": 10,
                "token_usage": {
                    "input_tokens": 2,
                    "output_tokens": 3,
                    "total_tokens": 5,
                },
                "errors": [],
            }
            self.traces[trace_id] = trace
            payload = chat
        else:
            assert request.method == "GET"
            payload = copy.deepcopy(self.traces[request.url.path.rsplit("/", 1)[-1]])
        if self.mutate:
            replacement = self.mutate(request, payload)
            if isinstance(replacement, httpx.Response):
                return replacement
        return httpx.Response(
            200, json=payload, headers={"set-cookie": "session=do-not-reuse"}
        )


def judge():
    return RubricJudgeScorer(
        lambda _: '{"score":1,"reason":"ok"}', "fake", rubric="Useful"
    )


def case(case_id="private-id", turns=None):
    return Case(
        id=case_id,
        input={"turns": turns or ["First", "Second"]},
        reference={"secret_expectation": "never send"},
        extra={"private": "never send"},
    )


def test_mapping_and_sessions_across_cases_and_attempts():
    fake = FakeHTTP()
    target = SalesAgentTarget(
        "http://local", transport=httpx.MockTransport(fake), target_revision="rev1"
    )
    assert isinstance(target, Target)
    result = run(target, [judge()], [case(), case("other")], attempts=3)
    assert result.error_rate == 0
    assert len(fake.sessions) == 6
    assert list(fake.sessions.values()) == [2] * 6
    assert len(fake.requests) == 24
    assert [r.method for r in fake.requests] == ["POST", "GET"] * 12
    for result_case in result.cases:
        for attempt in result_case.attempts:
            response = attempt.response
            assert response.raw == {}
            assert response.structured["recommendations"][0]["price"] == "145.00"
            assert len(response.structured["turns"]) == 2
            assert len(response.trajectory) == 2
            assert response.metadata["token_usage"]["total_tokens"] == 10
            assert response.metadata["target_revision"] == "rev1"
            assert (
                response.structured["turns"][0]["evidence"]["constraint_changes"][0][
                    "current"
                ]
                == "160.00"
            )
            assert response.cost_usd is None
    assert "never send" not in str([r.content for r in fake.requests])
    assert result.target_name == "salesagent"
    assert TargetResponse.model_validate_json(response.model_dump_json()) == response


@pytest.mark.parametrize(
    "fault",
    [
        "timeout",
        "unavailable",
        "http",
        "json",
        "chat",
        "trace",
        "missing_trace",
        "session",
        "correlation",
        "sequence",
        "turn",
        "change",
        "tool",
        "execution",
    ],
)
def test_failures_are_errors_and_sanitized(fault):
    def mutate(request, payload):
        if request.method == "POST":
            if fault == "timeout":
                raise httpx.ReadTimeout("SECRET")
            if fault == "unavailable":
                raise httpx.ConnectError("SECRET")
            if fault == "http":
                return httpx.Response(503, text="SECRET")
            if fault == "json":
                return httpx.Response(200, text="SECRET")
            if fault == "chat":
                payload["recommendations"] = "SECRET"
            if fault == "session" and "session_id" in json.loads(request.content):
                payload["session_id"] = "different"
        else:
            if fault == "trace":
                del payload["token_usage"]
            if fault == "missing_trace":
                return httpx.Response(404, text="SECRET")
            if fault == "correlation":
                payload["session_id"] = "different"
            if fault == "sequence":
                payload["tool_calls"][0]["sequence"] = 2
            if fault == "turn":
                payload["turn_index"] = 0
            if fault == "change":
                payload["constraint_changes"][0]["current"] = {"secret": "SECRET"}
            if fault == "tool":
                payload["tool_calls"][0]["result"]["data"] = {}
            if fault == "execution":
                payload["errors"] = [{"code": "openai_timeout", "message": "SECRET"}]

    fake = FakeHTTP(mutate)
    result = run(
        SalesAgentTarget("http://local", transport=httpx.MockTransport(fake)),
        [judge()],
        [case()],
    )
    assert result.cases[0].attempts[0].verdict == Verdict.ERROR
    assert result.cases[0].attempts[0].response is None
    assert "SECRET" not in result.model_dump_json()
    assert result.aggregate_pass_rate is None


def test_unknown_nested_fields_and_error_messages_are_not_persisted():
    def mutate(request, payload):
        payload["hidden_prompt"] = "SECRET"
        if request.method == "GET":
            payload["tool_calls"][0]["arguments"]["authorization"] = "SECRET"
            payload["tool_calls"][0]["result"]["data"]["reasoning"] = "SECRET"
            payload["tool_calls"][0]["result"]["data"]["variants"][0]["secret"] = (
                "SECRET"
            )
            payload["recommendation_validation"]["validation_errors"] = ["SECRET"]
            payload["errors"] = [
                {"code": "ungrounded_promotion_code", "message": "SECRET"}
            ]

    response = SalesAgentTarget(
        "http://local", transport=httpx.MockTransport(FakeHTTP(mutate))
    ).invoke(case(turns=["hello"]))
    assert "SECRET" not in response.model_dump_json()
    assert response.structured["turns"][0]["evidence"]["errors"] == [
        {"code": "ungrounded_promotion_code"}
    ]


@pytest.mark.parametrize(
    "input",
    [
        {"turns": []},
        {"turns": [""]},
        {"turns": ["a" * 4001]},
        {"turns": [True]},
        {"turns": ["hello"], "session_id": "leak"},
    ],
)
def test_invalid_input_never_calls_http(input):
    fake = FakeHTTP()
    with pytest.raises(ValueError):
        SalesAgentTarget("http://local", transport=httpx.MockTransport(fake)).invoke(
            Case(id="x", input=input)
        )
    assert fake.requests == []


@pytest.mark.parametrize(
    "url",
    [
        "ftp://host",
        "http://user:secret@host",
        "http://host?secret=x",
        "http://host#secret",
        "host",
    ],
)
def test_rejects_unsafe_base_url(url):
    with pytest.raises(ValueError, match="base_url"):
        SalesAgentTarget(url)


def test_injected_client_owned_by_caller_and_defaults_not_forwarded():
    fake = FakeHTTP()
    with httpx.Client(
        transport=httpx.MockTransport(fake),
        headers={"authorization": "SECRET"},
        cookies={"session": "SECRET"},
    ) as client:
        target = SalesAgentTarget("http://local", client=client)
        run(target, [judge()], [case()])
        assert not client.is_closed


def test_legacy_response_defaults():
    response = TargetResponse.model_validate_json('{"output":"old"}')
    assert response.structured == response.metadata == {}


def test_later_turn_failure_stops_attempt_and_next_attempt_starts_fresh():
    failed = False

    def mutate(request, payload):
        nonlocal failed
        if (
            request.method == "POST"
            and "session_id" in json.loads(request.content)
            and not failed
        ):
            failed = True
            return httpx.Response(500)

    fake = FakeHTTP(mutate)
    result = run(
        SalesAgentTarget("http://local", transport=httpx.MockTransport(fake)),
        [judge()],
        [case()],
        attempts=2,
    )
    assert [a.verdict for a in result.cases[0].attempts] == [
        Verdict.ERROR,
        Verdict.PASS,
    ]
    assert result.cases[0].attempts[0].response is None
    assert len(fake.sessions) == 2
    assert [r.method for r in fake.requests] == [
        "POST",
        "GET",
        "POST",
        "POST",
        "GET",
        "POST",
        "GET",
    ]


def test_false_business_validation_and_invalid_discount_are_not_errors():
    def mutate(request, payload):
        payload["promotion"] = {
            "code": "STAFF99",
            "valid": False,
            "reason": "unknown_code",
        }
        if request.method == "GET":
            payload["recommendation_validation"]["prices_match_catalogue"] = False

    result = run(
        SalesAgentTarget(
            "http://local", transport=httpx.MockTransport(FakeHTTP(mutate))
        ),
        [judge()],
        [case()],
    )
    assert result.error_rate == 0
    assert (
        result.cases[0].attempts[0].response.structured["promotion"]["valid"] is False
    )


def test_empty_business_response_and_tool_trajectory_are_valid():
    def mutate(request, payload):
        if request.method == "POST":
            payload["recommendations"] = []
        else:
            payload["tool_calls"] = []
            payload["recommended_product_ids"] = []

    response = SalesAgentTarget(
        "http://local", transport=httpx.MockTransport(FakeHTTP(mutate))
    ).invoke(case(turns=["Hello"]))
    assert response.trajectory == []
    assert response.structured["recommendations"] == []
    assert response.structured["turns"][0]["evidence"]["grounded_product_ids"] == []


def test_unknown_exception_is_sanitized():
    def transport(request):
        raise RuntimeError("SECRET")

    result = run(
        SalesAgentTarget("http://local", transport=httpx.MockTransport(transport)),
        [judge()],
        [case()],
    )
    assert result.error_rate == 1
    assert "SECRET" not in result.model_dump_json()


def test_owned_client_cleanup_does_not_mask_attempt_results():
    class BrokenClose(httpx.MockTransport):
        def close(self):
            raise RuntimeError("SECRET")

    with pytest.warns(RuntimeWarning, match="cleanup failed"):
        result = run(
            SalesAgentTarget("http://local", transport=BrokenClose(FakeHTTP())),
            [judge()],
            [case()],
        )
    assert result.error_rate == 0
    assert "SECRET" not in result.model_dump_json()


@pytest.mark.parametrize(
    "price,normalized",
    [
        (145.0, "145.00"),
        (145.001, "145.001"),
        (1e30, "1000000000000000000000000000000.00"),
    ],
)
def test_prices_are_normalized_without_rounding_or_decimal_context_loss(
    price, normalized
):
    def mutate(request, payload):
        if request.method == "POST":
            payload["recommendations"][0]["price"] = price

    response = SalesAgentTarget(
        "http://local", transport=httpx.MockTransport(FakeHTTP(mutate))
    ).invoke(case(turns=["price"]))
    assert response.structured["recommendations"][0]["price"] == normalized


def test_missing_required_trace_error_message_is_malformed():
    def mutate(request, payload):
        if request.method == "GET":
            payload["errors"] = [{"code": "ungrounded_promotion_code"}]

    result = run(
        SalesAgentTarget(
            "http://local", transport=httpx.MockTransport(FakeHTTP(mutate))
        ),
        [judge()],
        [case()],
    )
    assert result.error_rate == 1


@pytest.mark.parametrize("tool_name", ["get_product", "search_products"])
@pytest.mark.parametrize(
    "rating", ["missing", None, "", "extreme", True, 1, {"secret": "PRIVATE"}]
)
def test_missing_or_malformed_waterproof_rating_is_safe_adapter_error(
    tool_name, rating
):
    def mutate(request, payload):
        if request.method == "GET":
            call = payload["tool_calls"][0]
            data = call["result"]["data"]
            if rating == "missing":
                del data["waterproof_rating"]
            else:
                data["waterproof_rating"] = rating
            call["tool_name"] = call["result"]["tool_name"] = tool_name
            if tool_name == "search_products":
                call["arguments"] = {}
                call["result"]["data"] = {"products": [data], "count": 1}

    result = run(
        SalesAgentTarget(
            "http://local", transport=httpx.MockTransport(FakeHTTP(mutate))
        ),
        [judge()],
        [case(turns=["Recommend JKT-001"])],
    )
    attempt = result.cases[0].attempts[0]
    assert attempt.verdict is Verdict.ERROR
    assert attempt.response is None and attempt.scores == []
    assert "malformed contract evidence" in attempt.error
    assert "PRIVATE" not in result.model_dump_json()
