"""Optional real OpenAI 3.3.1 SDK, entirely in-memory HTTP; never a server."""

import json
import logging
import threading
import traceback
from hashlib import sha256
from types import SimpleNamespace

import httpx
import pytest
from test_canary_instrumentation_v3 import (
    app_request,
    attempt_guards,
    change_wire,
    profiled,
    records,
    saved,
)
from test_canary_journal_v3 import ready, retry_failure, selected

openai = pytest.importorskip("openai", reason="Pinned OpenAI 3.3.1 runtime is optional")
pytestmark = pytest.mark.skipif(
    openai.__version__ != "3.3.1", reason="Requires the approved OpenAI 3.3.1 runtime"
)

from harness.canary.instrumentation_v3 import (
    BoundedResponsesClientV3,
    ProviderTransportV3,
)
from harness.canary.recording import CanaryError
from harness.canary.runtime_v3 import V3, resolve_definition


def success(identifier="resp_sdk"):
    return {
        "id": identifier,
        "object": "response",
        "created_at": 0,
        "model": resolve_definition(V3).inference.model,
        "status": "completed",
        "output": [],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 10,
            "total_tokens": 110,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }


def sdk_client(transport, binding, *, hooks=None, strict=False):
    return openai.OpenAI(
        api_key="offline-synthetic-not-a-credential",
        organization=binding.organization_id,
        project=binding.project_id,
        base_url="https://api.openai.com/v1",
        max_retries=2,
        timeout=30,
        _strict_response_validation=strict,
        http_client=httpx.Client(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            event_hooks={"request": hooks or []},
        ),
    )


class SDKDelegate:
    def __init__(self, sdk):
        self.sdk, self.calls = sdk, 0

    def create_response(self, request):
        self.calls += 1
        response = self.sdk.responses.create(
            model=request.model,
            input=request.input,
            previous_response_id=request.previous_response_id,
            reasoning={"effort": request.reasoning_effort},
            max_output_tokens=request.max_output_tokens,
            instructions=request.instructions,
            tools=list(request.tools),
            text={"format": request.text_format},
        )
        return SimpleNamespace(response_id=response.id)


@pytest.mark.parametrize("known_zero", [True, False])
def test_real_sdk_500_500_200_retains_config_actual_headers_and_usage(
    tmp_path, known_zero
):
    registry, writer, binding = profiled(tmp_path)
    forwarded, before = [], []

    def hook(request):
        before.append(
            (
                request,
                sha256(request.content).digest(),
                sha256(repr(request.headers.raw).encode()).digest(),
                dict(request.extensions),
            )
        )

    def respond(request):
        expected = before[len(forwarded)]
        assert request is expected[0]
        assert sha256(request.content).digest() == expected[1]
        assert sha256(repr(request.headers.raw).encode()).digest() == expected[2]
        assert request.extensions == expected[3]
        forwarded.append(request)
        if len(forwarded) < 3:
            return httpx.Response(
                500,
                json=retry_failure(known_zero_usage=known_zero),
                headers={"retry-after-ms": "1", "x-should-retry": "true"},
            )
        return httpx.Response(200, json=success(), headers={"x-request-id": "req_sdk"})

    transport = ProviderTransportV3(
        writer, binding, httpx.MockTransport(respond), guards=attempt_guards
    )
    sdk = sdk_client(transport, binding, hooks=[hook])
    delegate = SDKDelegate(sdk)
    client = BoundedResponsesClientV3(delegate, transport)
    try:
        if known_zero:
            assert client.create_response(app_request()).response_id == "resp_sdk"
        else:
            with pytest.raises(CanaryError):
                client.create_response(app_request())
        assert sdk.max_retries == 2 and delegate.calls == 1
        assert len(forwarded) == 3 and len({r.content for r in forwarded}) == 1
        assert [r.headers["x-stainless-retry-count"] for r in forwarded] == [
            "0",
            "1",
            "2",
        ]
    finally:
        sdk.close()
    report = saved(registry, writer)
    assert report["accounting"]["unknown_attempts"] == (0 if known_zero else 2)
    assert [
        r["telemetry"]["sdk_retry_count"]
        for r in records(report, "instrumented_dispatch")
    ] == [0, 1, 2]
    assert records(report, "instrumented_result")[0]["telemetry"]["retry_after_ms"] == 1


@pytest.mark.parametrize(
    "headers",
    [
        {"retry-after": "121", "x-should-retry": "true"},
        {"retry-after-ms": "121000", "x-should-retry": "true"},
        {"x-should-retry": "false"},
    ],
)
def test_pinned_sdk_declines_retry_without_harness_replacement(tmp_path, headers):
    registry, writer, binding = profiled(tmp_path)
    forwarded = []
    transport = ProviderTransportV3(
        writer,
        binding,
        httpx.MockTransport(
            lambda r: (
                forwarded.append(r)
                or httpx.Response(
                    500, json=retry_failure(known_zero_usage=True), headers=headers
                )
            )
        ),
        guards=attempt_guards,
    )
    sdk = sdk_client(transport, binding)
    try:
        with pytest.raises(CanaryError):
            BoundedResponsesClientV3(SDKDelegate(sdk), transport).create_response(
                app_request()
            )
        assert sdk.max_retries == 2 and len(forwarded) == 1
    finally:
        sdk.close()
    report = saved(registry, writer)
    assert len(records(report, "instrumented_dispatch")) == 1
    assert report["accounting"]["operational_errors"] >= 1


@pytest.mark.parametrize(
    "fault", ["timeout", "billing", "authentication", "malformed_retry", "result_write"]
)
def test_sdk_iterations_after_terminal_fault_cannot_forward_or_record_new_intent(
    tmp_path, monkeypatch, fault
):
    from harness.canary import journal_v3

    registry, writer, binding = profiled(tmp_path)
    forwarded, sdk_entries = [], []

    def fail(*args, **kwargs):
        raise OSError("PRIVATE_DISK_ERROR")

    def respond(request):
        forwarded.append(request)
        if fault == "timeout":
            raise httpx.ReadTimeout("PRIVATE_TIMEOUT")
        if fault == "result_write":
            monkeypatch.setattr(journal_v3, "_publish", fail)
            return httpx.Response(200, json=success())
        code = {
            "billing": "insufficient_quota",
            "authentication": "invalid_api_key",
            "malformed_retry": "server_error",
        }[fault]
        return httpx.Response(
            500,
            json={"error": {"code": code}},
            headers={
                "x-should-retry": "PRIVATE_DIRECTIVE"
                if fault == "malformed_retry"
                else "true",
                "retry-after-ms": "1",
            },
        )

    transport = ProviderTransportV3(
        writer, binding, httpx.MockTransport(respond), guards=attempt_guards
    )
    sdk = sdk_client(transport, binding, hooks=[lambda r: sdk_entries.append(r)])
    try:
        with pytest.raises(CanaryError):
            BoundedResponsesClientV3(SDKDelegate(sdk), transport).create_response(
                app_request()
            )
        assert sdk.max_retries == 2 and len(forwarded) == 1
        assert len(sdk_entries) > 1  # Actual SDK re-entry, rejected by the latch.
    finally:
        monkeypatch.undo()
        sdk.close()
    report = saved(registry, writer)
    assert len(records(report, "instrumented_dispatch")) == 1
    assert "PRIVATE" not in json.dumps(report)


def test_http_success_then_real_sdk_validation_failure_preserves_usage(tmp_path):
    registry, writer, binding = profiled(tmp_path)
    raw = success()
    raw["output"] = 42
    forwarded = []
    transport = ProviderTransportV3(
        writer,
        binding,
        httpx.MockTransport(
            lambda r: forwarded.append(r) or httpx.Response(200, json=raw)
        ),
        guards=attempt_guards,
    )
    sdk = sdk_client(transport, binding, strict=True)
    try:
        with pytest.raises(CanaryError):
            BoundedResponsesClientV3(SDKDelegate(sdk), transport).create_response(
                app_request()
            )
    finally:
        sdk.close()
    report = saved(registry, writer)
    assert len(forwarded) == 1 and report["accounting"]["unknown_attempts"] == 0
    assert (
        records(report, "instrumented_result")[0]["observation"]["outcome"]
        == "completed"
    )
    assert (
        records(report, "instrumented_call_finished")[0]["failure"] == "delegate_error"
    )


def test_stop_during_sdk_backoff_prevents_next_dispatch(tmp_path, monkeypatch):
    from openai import _base_client

    registry, writer, binding = profiled(tmp_path)
    sleeping, release = threading.Event(), threading.Event()
    forwarded, errors = [], []
    transport = ProviderTransportV3(
        writer,
        binding,
        httpx.MockTransport(
            lambda r: (
                forwarded.append(r)
                or httpx.Response(500, json=retry_failure(known_zero_usage=True))
            )
        ),
        guards=attempt_guards,
    )
    sdk = sdk_client(transport, binding)

    def controlled_sleep(_):
        sleeping.set()
        assert release.wait(5)

    # Test-only scheduling barrier; no retry-selection or production patching.
    monkeypatch.setattr(_base_client.time, "sleep", controlled_sleep)

    def invoke():
        try:
            BoundedResponsesClientV3(SDKDelegate(sdk), transport).create_response(
                app_request()
            )
        except CanaryError:
            errors.append("stopped")

    caller = threading.Thread(target=invoke)
    caller.start()
    try:
        assert sleeping.wait(5)
        transport.request_stop()
    finally:
        release.set()
        caller.join(5)
        sdk.close()
    assert not caller.is_alive() and errors == ["stopped"]
    assert len(forwarded) == 1
    assert len(records(saved(registry, writer), "instrumented_dispatch")) == 1


@pytest.mark.parametrize(
    "shape",
    ["string", "empty_configuration", "history", "function_outputs", "a2_history"],
)
def test_pinned_application_client_is_decorated_without_request_reconstruction(
    tmp_path, shape
):
    pytest.importorskip("salesagent")
    from dataclasses import replace

    from salesagent.agent.responses_client import (
        FunctionCallOutput,
        OpenAIResponsesClient,
        ResponseMessage,
        ResponseRequest,
    )

    registry, writer, binding = profiled(tmp_path)
    forwarded, before = [], []

    def hook(request):
        request.extensions["synthetic-marker"] = {"preserve": True}
        before.append(
            (
                request,
                request.content,
                list(request.headers.raw),
                dict(request.extensions),
            )
        )

    def respond(request):
        original, content, headers, extensions = before[len(forwarded)]
        assert request is original and request.content == content
        assert request.headers.raw == headers and request.extensions == extensions
        forwarded.append(request)
        return httpx.Response(200, json=success(f"resp_sdk_{len(forwarded)}"))

    transport = ProviderTransportV3(
        writer,
        binding,
        httpx.MockTransport(respond),
        guards=attempt_guards,
    )
    sdk = sdk_client(transport, binding, hooks=[hook])
    config = app_request()
    request = ResponseRequest(
        input=binding.definition.turns[0].message,
        previous_response_id=None,
        model=binding.definition.inference.model,
        instructions=config.instructions,
        tools=config.tools,
        text_format={
            "type": "json_schema",
            "name": "synthetic",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
                "additionalProperties": False,
            },
        },
        reasoning_effort="low",
        max_output_tokens=2000,
    )
    if shape == "empty_configuration":
        request = replace(
            request, instructions="", tools=(), text_format={"type": "text"}
        )
    try:
        delegate = OpenAIResponsesClient(
            api_key=None, timeout_seconds=30, max_retries=2, sdk_client=sdk
        )
        client = BoundedResponsesClientV3(delegate, transport)
        expected = request.input
        if shape in ("function_outputs", "a2_history"):
            first = client.create_response(request)
            if shape == "function_outputs":
                value = (
                    FunctionCallOutput("call_one", "PRIVATE_OUTPUT_π"),
                    FunctionCallOutput("call_two", '{"PRIVATE_TOOL_RESULT":true}'),
                )
                request = replace(
                    request, input=value, previous_response_id=first.response_id
                )
                expected = [
                    {
                        "type": "function_call_output",
                        "call_id": item.call_id,
                        "output": item.output,
                    }
                    for item in value
                ]
            else:
                for slot in ("A1", "B1"):
                    if slot == "B1":
                        assert writer.record_decision(ready()).next_slot == slot
                        writer.reserve_turn(slot)
                        client.create_response(
                            replace(
                                request,
                                input=next(
                                    turn.message
                                    for turn in binding.definition.turns
                                    if turn.slot == slot
                                ),
                            )
                        )
                    raw = selected(slot)
                    writer.record_chat(raw["chat"])
                    writer.record_trace(raw["trace"], reread=raw["trace"])
                    writer.assess_turn()
                    writer.complete_turn()
                assert writer.record_decision(ready()).next_slot == "A2"
                writer.reserve_turn("A2")
        if shape in ("history", "a2_history"):
            message = next(
                turn.message
                for turn in binding.definition.turns
                if turn.slot == ("A2" if shape == "a2_history" else "A1")
            )
            value = (
                ResponseMessage("user", "PRIVATE_PREVIOUS_SHOPPER_π"),
                ResponseMessage("assistant", "PRIVATE_PREVIOUS_ASSISTANT"),
                ResponseMessage("user", message),
            )
            request = replace(request, input=value)
            expected = [{"role": item.role, "content": item.content} for item in value]
        result = client.create_response(request)
        assert result.response_id == f"resp_sdk_{len(forwarded)}"
        wire = json.loads(forwarded[-1].content)
        assert (
            wire["input"] == expected and wire["instructions"] == request.instructions
        )
        assert wire["tools"] == list(request.tools) and wire["text"] == {
            "format": request.text_format
        }
    finally:
        sdk.close()
    report = saved(registry, writer)
    assert len(records(report, "instrumented_dispatch")) == len(forwarded)
    assert "PRIVATE" not in json.dumps(report)


@pytest.mark.parametrize("field", ["input", "instructions", "tools", "text"])
@pytest.mark.parametrize("missing", [False, True], ids=["altered", "missing"])
def test_pinned_application_wire_mismatch_cannot_be_bypassed_by_sdk_retries(
    tmp_path, caplog, field, missing
):
    pytest.importorskip("salesagent")
    from salesagent.agent.responses_client import OpenAIResponsesClient, ResponseRequest

    registry, writer, binding = profiled(tmp_path)
    entries, forwarded = [], []

    def hook(request):
        entries.append(request)
        if len(entries) == 1:
            change_wire(request, field, missing=missing)
        # Later actual SDK retries have correct bodies; the gate must stay closed.

    transport = ProviderTransportV3(
        writer,
        binding,
        httpx.MockTransport(
            lambda r: forwarded.append(r) or httpx.Response(200, json=success())
        ),
        guards=attempt_guards,
    )
    sdk = sdk_client(transport, binding, hooks=[hook])
    application = ResponseRequest(**vars(app_request()))
    try:
        client = BoundedResponsesClientV3(
            OpenAIResponsesClient(
                api_key=None, timeout_seconds=30, max_retries=2, sdk_client=sdk
            ),
            transport,
        )
        with caplog.at_level(logging.INFO), pytest.raises(CanaryError) as error:
            client.create_response(application)
        assert len(entries) == 3 and sdk.max_retries == 2
        assert transport.stopped and forwarded == []
        with pytest.raises(CanaryError):
            client.create_response(application)
        assert len(entries) == 3
    finally:
        sdk.close()
    report = saved(registry, writer)
    assert records(report, "instrumented_dispatch") == []
    assert records(report, "instrumented_result") == []
    assert len(records(report, "instrumented_call_reserved")) == 1
    assert records(report, "instrumentation_stop")[0]["code"] == "request_invalid"
    assert "PRIVATE" not in json.dumps(report) + caplog.text + "".join(
        traceback.format_exception(error.value)
    )
