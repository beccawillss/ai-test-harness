"""Deterministic in-memory adapter tests; no SDK, application, sockets or server."""

import json
import logging
import threading
import traceback
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from test_canary_journal_v3 import (
    envelope,
    make,
    ready,
    retry_failure,
    spending_envelope,
)

from harness.canary import journal_v3 as journal
from harness.canary.evidence_v3 import AttemptGuards
from harness.canary.instrumentation_v3 import (
    BoundedResponsesClientV3,
    ProviderTransportV3,
)
from harness.canary.recording import CanaryError
from harness.canary.runtime_v3 import V3, resolve_definition


def attempt_guards(**changes):
    return AttemptGuards(
        **{
            "checked_at": datetime.now(UTC).isoformat(),
            **{
                name: True
                for name, field in AttemptGuards.model_fields.items()
                if field.annotation is bool
            },
            **changes,
        }
    )


def profiled(tmp_path, *, turn=True):
    tmp_path.mkdir(parents=True, exist_ok=True)
    registry, writer = make(tmp_path)
    binding = writer.bind_provider(
        resolve_definition(V3),
        project_id="proj_synthetic",
        organization_id="org_synthetic",
    )
    if turn:
        writer.record_decision(ready())
        writer.reserve_turn("A1")
    return registry, writer, binding


def app_request(**changes):
    inference = resolve_definition(V3).inference
    return SimpleNamespace(
        **{
            "input": resolve_definition(V3).turns[0].message,
            "previous_response_id": None,
            "model": inference.model,
            "reasoning_effort": inference.reasoning_effort,
            "max_output_tokens": inference.max_output_tokens,
            "instructions": "PRIVATE_SYNTHETIC_INSTRUCTIONS",
            "tools": (
                {
                    "type": "function",
                    "name": "synthetic_tool",
                    "description": "PRIVATE_SYNTHETIC_TOOL",
                    "parameters": {"type": "object", "properties": {}},
                },
            ),
            "text_format": {"type": "text"},
            **changes,
        }
    )


@dataclass(frozen=True, slots=True)
class Message:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ToolOutput:
    call_id: str
    output: str


@dataclass(frozen=True, slots=True)
class AmbiguousInput:
    role: str
    content: str
    call_id: str
    output: str


def prepared(binding, application, retry=0, *, raw=None, headers=None, **changes):
    value = application.input
    if isinstance(value, tuple) and value:
        if all(isinstance(item, Message) for item in value):
            value = [{"role": item.role, "content": item.content} for item in value]
        elif all(isinstance(item, ToolOutput) for item in value):
            value = [
                {
                    "type": "function_call_output",
                    "call_id": item.call_id,
                    "output": item.output,
                }
                for item in value
            ]
    body = {
        "model": application.model,
        "input": value,
        "previous_response_id": application.previous_response_id,
        "reasoning": {"effort": application.reasoning_effort},
        "max_output_tokens": application.max_output_tokens,
        "instructions": application.instructions,
        "tools": list(application.tools),
        "text": {"format": application.text_format},
        **changes,
    }
    return httpx.Request(
        "POST",
        "https://api.openai.com/v1/responses",
        content=json.dumps(body, indent=2).encode() if raw is None else raw,
        headers={
            "openai-project": binding.project_id,
            "openai-organization": binding.organization_id,
            "x-stainless-retry-count": str(retry),
            "authorization": "Bearer SYNTHETIC_PRIVATE_KEY",
            **(headers or {}),
        },
        extensions={
            "timeout": {name: 30 for name in ("connect", "read", "write", "pool")}
        },
    )


def client_for(
    transport, *, requests=None, result_id=None, count=1, after=None, change=None
):
    seen = requests if requests is not None else []

    def create(application):
        response = None
        for retry in range(count):
            request = prepared(transport.binding, application, retry)
            if change:
                change(request)
            seen.append(request)
            response = transport.handle_request(request)
        if after:
            after()
        return SimpleNamespace(response_id=result_id or response.json().get("id"))

    return BoundedResponsesClientV3(SimpleNamespace(create_response=create), transport)


def saved(registry, writer):
    writer.close()
    return journal.inspect_run(registry, "run-1")


def records(report, kind):
    return [r["payload"] for r in report["records"] if r["kind"] == kind]


def change_wire(request, field, *, missing=False):
    body = json.loads(request.content)
    if missing:
        del body[field]
    else:
        body[field] = {
            "input": "PRIVATE_DIFFERENT_SHOPPER",
            "instructions": "PRIVATE_DIFFERENT_INSTRUCTIONS",
            "tools": [],
            "text": {"format": {"type": "json_object"}},
        }[field]
    # Test-only corruption after preparation and before instrumentation.
    request._content = json.dumps(body).encode()
    request.stream = httpx.ByteStream(request.content)
    request.headers["content-length"] = str(len(request.content))


@pytest.mark.parametrize("field", ["input", "instructions", "tools", "text"])
@pytest.mark.parametrize("missing", [False, True], ids=["altered", "missing"])
def test_application_to_wire_mismatch_stops_before_any_dispatch(
    tmp_path, caplog, field, missing
):
    registry, writer, binding = profiled(tmp_path)
    forwarded = []
    transport = ProviderTransportV3(
        writer,
        binding,
        httpx.MockTransport(
            lambda r: forwarded.append(r) or httpx.Response(200, json=envelope())
        ),
        guards=attempt_guards,
    )
    with caplog.at_level(logging.INFO), pytest.raises(CanaryError) as error:
        client_for(
            transport, change=lambda r: change_wire(r, field, missing=missing)
        ).create_response(app_request())
    assert (
        str(error.value) == "V3 logical call failed; preserve evidence; no replacement"
    )
    assert error.value.__cause__ is None and error.value.__suppress_context__
    assert transport.stopped and forwarded == []
    with pytest.raises(CanaryError):
        client_for(transport).create_response(app_request())
    with pytest.raises(CanaryError):
        transport.handle_request(prepared(binding, app_request(), retry=1))
    report = saved(registry, writer)
    assert records(report, "instrumented_dispatch") == []
    assert records(report, "instrumented_result") == []
    assert report["instrumentation_terminal_stop_recorded"]
    assert "PRIVATE" not in json.dumps(report) + caplog.text + str(error.value)
    assert "PRIVATE" not in "".join(traceback.format_exception(error.value))


@pytest.mark.parametrize(
    "value",
    [
        (),
        [],
        [{"role": "user", "content": resolve_definition(V3).turns[0].message}],
        ({"role": "user", "content": resolve_definition(V3).turns[0].message},),
        (
            SimpleNamespace(
                role="user", content=resolve_definition(V3).turns[0].message
            ),
        ),
        (Message("system", resolve_definition(V3).turns[0].message),),
        (Message("user", 42),),
        (ToolOutput("call_synthetic", 42),),
        (
            ToolOutput("call_synthetic", "PRIVATE_OUTPUT"),
            Message("user", resolve_definition(V3).turns[0].message),
        ),
        (
            AmbiguousInput(
                "user",
                resolve_definition(V3).turns[0].message,
                "call_synthetic",
                "PRIVATE_OUTPUT",
            ),
        ),
    ],
    ids=[
        "empty-tuple",
        "empty-list",
        "list",
        "dict-record",
        "duck-record",
        "role",
        "content",
        "output",
        "mixed",
        "ambiguous",
    ],
)
def test_unsupported_application_input_stops_before_delegate(tmp_path, value):
    registry, writer, binding = profiled(tmp_path)
    invoked = []
    transport = ProviderTransportV3(
        writer,
        binding,
        httpx.MockTransport(lambda r: pytest.fail("forwarded")),
        guards=attempt_guards,
    )
    with pytest.raises(CanaryError):
        transport.run_call(app_request(input=value), lambda: invoked.append(True))
    assert transport.stopped and invoked == []
    report = saved(registry, writer)
    assert records(report, "instrumented_call_reserved") == []
    assert records(report, "instrumented_dispatch") == []


@pytest.mark.parametrize("field", ["tools", "text_format"])
def test_mutable_application_values_are_snapshotted_before_delegate(tmp_path, field):
    registry, writer, binding = profiled(tmp_path)
    transport = ProviderTransportV3(
        writer,
        binding,
        httpx.MockTransport(lambda r: pytest.fail("forwarded")),
        guards=attempt_guards,
    )
    request = app_request()

    def invoke():
        if field == "tools":
            request.tools[0]["parameters"]["properties"]["PRIVATE_NEW"] = {
                "type": "string"
            }
        else:
            request.text_format["type"] = "json_object"
        transport.handle_request(prepared(binding, request))

    with pytest.raises(CanaryError):
        transport.run_call(request, invoke)
    assert records(saved(registry, writer), "instrumented_dispatch") == []


@pytest.mark.parametrize("field", ["tools", "text"])
def test_json_boolean_and_number_are_not_equivalent(tmp_path, field):
    registry, writer, binding = profiled(tmp_path)
    request = app_request(text_format={"type": "json_schema", "strict": True})
    request.tools[0]["strict"] = True

    def change(wire):
        body = json.loads(wire.content)
        target = body["tools"][0] if field == "tools" else body["text"]["format"]
        target["strict"] = 1
        wire._content = json.dumps(body).encode()
        wire.stream = httpx.ByteStream(wire.content)

    transport = ProviderTransportV3(
        writer,
        binding,
        httpx.MockTransport(lambda r: pytest.fail("forwarded")),
        guards=attempt_guards,
    )
    with pytest.raises(CanaryError):
        client_for(transport, change=change).create_response(request)
    assert records(saved(registry, writer), "instrumented_dispatch") == []


def test_mismatch_preserves_previously_committed_evidence(tmp_path):
    registry, writer, binding = profiled(tmp_path)
    forwarded = []
    transport = ProviderTransportV3(
        writer,
        binding,
        httpx.MockTransport(
            lambda r: forwarded.append(r) or httpx.Response(200, json=envelope())
        ),
        guards=attempt_guards,
    )
    client_for(transport).create_response(app_request())
    root = Path(registry.path) / "runs" / "run-1"
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    with pytest.raises(CanaryError):
        client_for(transport, change=lambda r: change_wire(r, "input")).create_response(
            app_request(
                previous_response_id="resp_test",
                input=(ToolOutput("call_synthetic", "PRIVATE_OUTPUT"),),
            )
        )
    assert all(path.read_bytes() == content for path, content in before.items())
    report = saved(registry, writer)
    assert len(forwarded) == len(records(report, "instrumented_dispatch")) == 1
    assert len(records(report, "instrumented_result")) == 1
    assert records(report, "instrumented_call_finished")[0]["outcome"] == "returned"


def test_equivalent_parsed_json_values_preserve_original_request(tmp_path):
    registry, writer, binding = profiled(tmp_path)
    request = app_request(instructions="PRIVATE_UNICODE_π")
    request.tools[0]["parameters"]["minimum"] = 1.0
    before, forwarded = [], []

    def change(wire):
        # Different ordering, whitespace, escaping and numeric notation are equal.
        body = json.loads(wire.content)
        wire._content = (
            json.dumps(body, sort_keys=True, ensure_ascii=True)
            .replace("1.0", "1")
            .encode()
        )
        wire.stream = httpx.ByteStream(wire.content)
        wire.headers["content-length"] = str(len(wire.content))
        wire.extensions["synthetic-marker"] = {"preserve": True}
        before.append(
            (wire, wire.content, list(wire.headers.raw), dict(wire.extensions))
        )

    def respond(wire):
        original, content, headers, extensions = before[0]
        assert wire is original and wire.content == content
        assert wire.headers.raw == headers and wire.extensions == extensions
        forwarded.append(wire)
        return httpx.Response(200, json=envelope())

    transport = ProviderTransportV3(
        writer, binding, httpx.MockTransport(respond), guards=attempt_guards
    )
    assert (
        client_for(transport, change=change).create_response(request).response_id
        == "resp_test"
    )
    assert len(forwarded) == 1
    assert "PRIVATE" not in json.dumps(saved(registry, writer))


@pytest.mark.parametrize(
    "changes",
    [
        {"instructions": None},
        {"tools": []},
        {"tools": (None,)},
        {"text_format": []},
        {"text_format": {1: "PRIVATE_INVALID_KEY"}},
        {"text_format": {"PRIVATE_NAN": float("nan")}},
        {"text_format": {"PRIVATE_TUPLE": (1, 2)}},
    ],
)
def test_unsupported_application_configuration_stops_before_delegate(tmp_path, changes):
    registry, writer, binding = profiled(tmp_path)
    invoked = []
    transport = ProviderTransportV3(
        writer,
        binding,
        httpx.MockTransport(lambda r: pytest.fail("forwarded")),
        guards=attempt_guards,
    )
    with pytest.raises(CanaryError):
        transport.run_call(app_request(**changes), lambda: invoked.append(True))
    assert invoked == [] and transport.stopped
    assert "PRIVATE" not in json.dumps(saved(registry, writer))


def test_original_request_object_bytes_headers_and_extensions_and_safe_evidence(
    tmp_path, caplog
):
    registry, writer, binding = profiled(tmp_path)
    outbound, seen = [], []

    def respond(request):
        outbound.append(
            (request, request.content, request.headers.raw, dict(request.extensions))
        )
        return httpx.Response(
            200,
            json=envelope(),
            headers={"x-request-id": "req_test", "private-header": "PRIVATE_HEADER"},
        )

    transport = ProviderTransportV3(
        writer, binding, httpx.MockTransport(respond), guards=attempt_guards
    )
    with caplog.at_level(logging.INFO):
        result = client_for(transport, requests=seen).create_response(app_request())
    assert result.response_id == "resp_test"
    original, content, headers, extensions = outbound[0]
    assert original is seen[0]
    assert content == seen[0].content and headers == seen[0].headers.raw
    assert extensions == seen[0].extensions
    assert b'\n  "model"' in content
    report = saved(registry, writer)
    assert report["accounting"]["provider_attempts"] == 1
    assert report["accounting"]["unknown_attempts"] == 0
    assert (
        records(report, "instrumented_dispatch")[0]["telemetry"]["sdk_retry_count"] == 0
    )
    text = json.dumps(report) + caplog.text
    assert all(
        secret not in text
        for secret in (
            "SYNTHETIC_PRIVATE_KEY",
            "PRIVATE_HEADER",
            "PRIVATE_PROVIDER_REASONING",
            '"authorization"',
        )
    )
    assert (
        not report["authorises_live_execution"]
        and not report["provider_evidence_authenticated"]
    )


@pytest.mark.parametrize("known_zero", [True, False])
def test_simulated_eligible_same_call_retries_retain_liabilities(tmp_path, known_zero):
    registry, writer, binding = profiled(tmp_path)
    responses = iter(
        [
            httpx.Response(500, json=retry_failure(known_zero_usage=known_zero)),
            httpx.Response(500, json=retry_failure(known_zero_usage=known_zero)),
            httpx.Response(200, json=envelope()),
        ]
    )
    seen = []
    transport = ProviderTransportV3(
        writer,
        binding,
        httpx.MockTransport(lambda r: seen.append(r) or next(responses)),
        guards=attempt_guards,
    )
    client = client_for(transport, count=3)
    if known_zero:
        client.create_response(app_request())
    else:
        with pytest.raises(CanaryError):
            client.create_response(app_request())
    assert len(seen) == 3 and len({r.content for r in seen}) == 1
    report = saved(registry, writer)
    assert report["accounting"]["unknown_attempts"] == (0 if known_zero else 2)
    assert report["accounting"]["retryable_http_failures"] == 2
    assert len(records(report, "instrumented_call_reserved")) == 1
    assert report["instrumentation_terminal_stop_recorded"] is not known_zero
    assert report["dispatch_available"] is False


@pytest.mark.parametrize(
    "code", ["insufficient_quota", "invalid_api_key", "PRIVATE_UNKNOWN"]
)
@pytest.mark.parametrize("directive", ["true", "false", "PRIVATE_INVALID"])
def test_terminal_result_blocks_a_subsequent_attempt_before_intent(
    tmp_path, code, directive
):
    registry, writer, binding = profiled(tmp_path)
    forwarded = []
    transport = ProviderTransportV3(
        writer,
        binding,
        httpx.MockTransport(
            lambda r: (
                forwarded.append(r)
                or httpx.Response(
                    500,
                    json={"error": {"code": code, "message": "PRIVATE_MESSAGE"}},
                    headers={"x-should-retry": directive},
                )
            )
        ),
        guards=attempt_guards,
    )
    with pytest.raises(CanaryError):
        client_for(transport, count=2).create_response(app_request())
    report = saved(registry, writer)
    assert len(forwarded) == len(records(report, "instrumented_dispatch")) == 1
    assert report["accounting"]["unknown_attempts"] == 1
    assert "PRIVATE" not in json.dumps(report)


@pytest.mark.parametrize("boundary", ["retry", "next_call"])
@pytest.mark.parametrize(
    "tokens,paused", [(999999, False), (1000000, True), (1000001, True)]
)
def test_spending_boundaries_within_a_turn(tmp_path, boundary, tokens, paused):
    registry, writer, binding = profiled(tmp_path)
    forwarded = []

    def respond(request):
        forwarded.append(request)
        if len(forwarded) == 1:
            return httpx.Response(
                500 if boundary == "retry" else 200,
                json=spending_envelope(tokens, retryable=boundary == "retry"),
            )
        raw = envelope()
        raw["id"] = "resp_second"
        raw["usage"] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        return httpx.Response(200, json=raw)

    transport = ProviderTransportV3(
        writer, binding, httpx.MockTransport(respond), guards=attempt_guards
    )
    client = client_for(transport, count=2 if boundary == "retry" else 1)
    if paused:
        with pytest.raises(CanaryError):
            client.create_response(app_request())
    else:
        client.create_response(app_request())
        if boundary == "next_call":
            client.create_response(
                app_request(
                    previous_response_id="resp_test", input="synthetic tool output"
                )
            )
    assert len(forwarded) == (1 if paused else 2)
    report = saved(registry, writer)
    assert (
        records(report, "instrumented_result")[0]["observation"]["estimated_usd"]
        is not None
    )


@pytest.mark.parametrize(
    "guard",
    [
        name
        for name, field in AttemptGuards.model_fields.items()
        if field.annotation is bool
    ],
)
def test_each_failed_guard_prevents_forwarding(tmp_path, guard):
    registry, writer, binding = profiled(tmp_path)
    forwarded = []
    transport = ProviderTransportV3(
        writer,
        binding,
        httpx.MockTransport(lambda r: forwarded.append(r)),
        guards=lambda: attempt_guards(**{guard: False}),
    )
    with pytest.raises(CanaryError):
        client_for(transport).create_response(app_request())
    assert not forwarded
    assert not records(saved(registry, writer), "instrumented_dispatch")


@pytest.mark.parametrize(
    "changes",
    [
        {"external_unknown_attempts": 1},
        {"estimated_total_usd": "5"},
        {"checked_at": (datetime.now(UTC) - timedelta(minutes=2)).isoformat()},
        {"checked_at": (datetime.now(UTC) + timedelta(minutes=2)).isoformat()},
    ],
)
def test_stale_external_unknown_and_spending_guards_cannot_override_local_gate(
    tmp_path, changes
):
    registry, writer, binding = profiled(tmp_path)
    forwarded = []
    transport = ProviderTransportV3(
        writer,
        binding,
        httpx.MockTransport(lambda r: forwarded.append(r)),
        guards=lambda: attempt_guards(**changes),
    )
    with pytest.raises(CanaryError):
        client_for(transport).create_response(app_request())
    assert not forwarded and not records(
        saved(registry, writer), "instrumented_dispatch"
    )


@pytest.mark.parametrize(
    "fault",
    [
        "model",
        "reasoning",
        "stream",
        "temperature",
        "continuation",
        "project",
        "retry",
        "timeout",
        "json",
    ],
)
def test_prepared_request_drift_is_rejected_without_repair(tmp_path, fault):
    registry, writer, binding = profiled(tmp_path)
    forwarded = []
    transport = ProviderTransportV3(
        writer,
        binding,
        httpx.MockTransport(lambda r: forwarded.append(r)),
        guards=attempt_guards,
    )

    def change(request):
        if fault in {"project", "retry"}:
            request.headers[
                "openai-project" if fault == "project" else "x-stainless-retry-count"
            ] = "PRIVATE_INVALID"
        elif fault == "timeout":
            request.extensions["timeout"]["read"] = 31
        else:
            body = json.loads(request.content)
            body.update(
                {
                    {
                        "model": "model",
                        "reasoning": "reasoning",
                        "stream": "stream",
                        "temperature": "temperature",
                        "continuation": "previous_response_id",
                        "json": "model",
                    }[fault]: "PRIVATE_INVALID"
                }
            )
            request._content = (
                b"PRIVATE_INVALID" if fault == "json" else json.dumps(body).encode()
            )

    with pytest.raises(CanaryError):
        client_for(transport, change=change).create_response(app_request())
    assert not forwarded and not records(
        saved(registry, writer), "instrumented_dispatch"
    )


@pytest.mark.parametrize("failure", ["identity", "parse", "no_http"])
def test_application_completion_failures_preserve_observed_provider_usage(
    tmp_path, failure
):
    registry, writer, binding = profiled(tmp_path)
    transport = ProviderTransportV3(
        writer,
        binding,
        httpx.MockTransport(lambda _: httpx.Response(200, json=envelope())),
        guards=attempt_guards,
    )

    def fail():
        raise ValueError("PRIVATE_PARSE_ERROR")

    client = client_for(
        transport,
        result_id="resp_different" if failure == "identity" else None,
        after=fail if failure == "parse" else None,
    )
    if failure == "no_http":
        client = BoundedResponsesClientV3(
            SimpleNamespace(
                create_response=lambda _: SimpleNamespace(response_id="resp_test")
            ),
            transport,
        )
    with pytest.raises(CanaryError) as caught:
        client.create_response(app_request())
    assert "PRIVATE" not in str(caught.value)
    report = saved(registry, writer)
    assert report["accounting"]["provider_attempts"] == (
        0 if failure == "no_http" else 1
    )
    assert report["accounting"]["operational_errors"] >= 1
    assert records(report, "instrumented_call_finished")[0]["outcome"] == "error"
    if failure == "identity":
        assert (
            records(report, "instrumented_call_finished")[0]["response_id"]
            == "resp_different"
        )


@pytest.mark.parametrize("partial", [False, True])
def test_transport_ambiguity_never_becomes_known_zero(tmp_path, partial):
    registry, writer, binding = profiled(tmp_path)

    class BrokenStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b'{"usage":'
            raise httpx.ReadTimeout("PRIVATE_PARTIAL_BODY")

    def respond(_):
        if partial:
            return httpx.Response(
                200, stream=BrokenStream(), headers={"x-request-id": "req_partial"}
            )
        raise httpx.ReadTimeout("PRIVATE_TRANSPORT_ERROR")

    transport = ProviderTransportV3(
        writer, binding, httpx.MockTransport(respond), guards=attempt_guards
    )
    with pytest.raises(CanaryError):
        client_for(transport).create_response(app_request())
    report = saved(registry, writer)
    result = records(report, "instrumented_result")[0]
    assert result["observation"]["outcome"] == "ambiguous_transport"
    assert result["telemetry"]["observed_http_status"] == (200 if partial else None)
    assert report["accounting"]["unknown_attempts"] == 1
    assert "PRIVATE" not in json.dumps(report)


@pytest.mark.parametrize(
    "control", ["stop", "pause", "journal_stop", "concurrent", "reentrant"]
)
def test_inflight_stop_and_concurrency_retain_returning_result(tmp_path, control):
    registry, writer, binding = profiled(tmp_path)
    entered, release = threading.Event(), threading.Event()
    forwarded, errors = [], []
    client = None

    def respond(request):
        forwarded.append(request)
        entered.set()
        if control == "reentrant":
            with pytest.raises(CanaryError):
                client.create_response(app_request())
        else:
            assert release.wait(5)
        return httpx.Response(200, json=envelope())

    transport = ProviderTransportV3(
        writer, binding, httpx.MockTransport(respond), guards=attempt_guards
    )
    client = client_for(transport)

    def invoke():
        try:
            client.create_response(app_request())
        except CanaryError:
            errors.append("stopped")

    caller = threading.Thread(target=invoke)
    caller.start()
    try:
        assert entered.wait(5)
        if control == "concurrent":
            with pytest.raises(CanaryError):
                client.create_response(app_request())
        elif control == "journal_stop":
            writer.stop()
        elif control != "reentrant":
            transport.request_stop(pause=control == "pause")
    finally:
        release.set()
        caller.join(5)
    assert not caller.is_alive() and errors == ["stopped"]
    report = saved(registry, writer)
    assert len(forwarded) == 1 and report["accounting"]["unknown_attempts"] == 0
    assert (
        records(report, "instrumented_result")[0]["observation"]["outcome"]
        == "completed"
    )
    assert report["instrumentation_terminal_stop_recorded"]


def test_stop_after_intent_before_forwarding_retains_unresolved_liability(
    tmp_path, monkeypatch
):
    registry, writer, binding = profiled(tmp_path)
    forwarded = []
    transport = ProviderTransportV3(
        writer,
        binding,
        httpx.MockTransport(lambda r: forwarded.append(r)),
        guards=attempt_guards,
    )
    original = writer.dispatch_provider_attempt

    def stop(*args, **kwargs):
        original(*args, **kwargs)
        transport.request_stop()

    monkeypatch.setattr(writer, "dispatch_provider_attempt", stop)
    with pytest.raises(CanaryError):
        client_for(transport).create_response(app_request())
    report = saved(registry, writer)
    assert not forwarded and len(records(report, "instrumented_dispatch")) == 1
    assert report["accounting"]["unknown_attempts"] == 1


def test_logging_is_checked_before_application_delegate(tmp_path, monkeypatch):
    registry, writer, binding = profiled(tmp_path)
    transport = ProviderTransportV3(
        writer,
        binding,
        httpx.MockTransport(lambda _: pytest.fail("no HTTP")),
        guards=attempt_guards,
    )
    logger = logging.getLogger("openai._base_client")
    original = logger.level
    client = BoundedResponsesClientV3(
        SimpleNamespace(create_response=lambda _: pytest.fail("no SDK")), transport
    )
    try:
        logger.setLevel(logging.DEBUG)
        with pytest.raises(CanaryError):
            client.create_response(app_request())
    finally:
        logger.setLevel(original)
    assert not records(saved(registry, writer), "instrumented_call_reserved")


def test_network_transports_and_mock_subclasses_are_rejected(tmp_path):
    registry, writer, binding = profiled(tmp_path)

    class Untrusted(httpx.MockTransport):
        pass

    with pytest.raises(CanaryError):
        ProviderTransportV3(
            writer, binding, Untrusted(lambda _: None), guards=attempt_guards
        )
    assert not records(saved(registry, writer), "instrumented_dispatch")


def test_cleanup_failure_is_terminal_without_erasing_results(tmp_path, monkeypatch):
    registry, writer, binding = profiled(tmp_path)
    delegate = httpx.MockTransport(lambda _: httpx.Response(200, json=envelope()))
    transport = ProviderTransportV3(writer, binding, delegate, guards=attempt_guards)
    client_for(transport).create_response(app_request())

    def fail():
        raise OSError("PRIVATE_CLOSE_ERROR")

    monkeypatch.setattr(delegate, "close", fail)
    with pytest.raises(CanaryError):
        transport.close()
    report = saved(registry, writer)
    assert report["accounting"]["provider_attempts"] == 1
    assert report["instrumentation_stop"] == "cleanup_failed"


@pytest.mark.parametrize("count", [6, 7])
def test_six_call_boundary_and_continuation_identity(tmp_path, count):
    registry, writer, binding = profiled(tmp_path)
    forwarded = []

    def respond(request):
        forwarded.append(request)
        raw = envelope()
        raw["id"] = f"resp_{len(forwarded)}"
        return httpx.Response(200, json=raw)

    transport = ProviderTransportV3(
        writer, binding, httpx.MockTransport(respond), guards=attempt_guards
    )
    client = client_for(transport)
    previous = None
    for number in range(1, count + 1):
        application = app_request(previous_response_id=previous)
        if number == 7:
            with pytest.raises(CanaryError):
                client.create_response(application)
        else:
            previous = client.create_response(application).response_id
    assert len(forwarded) == 6
    assert saved(registry, writer)["accounting"]["logical_calls"] == 6


def test_mutated_transport_cannot_introduce_network_capability(tmp_path):
    registry, writer, binding = profiled(tmp_path)
    transport = ProviderTransportV3(
        writer,
        binding,
        httpx.MockTransport(lambda _: pytest.fail("no dispatch")),
        guards=attempt_guards,
    )

    class Other(httpx.BaseTransport):
        def handle_request(self, request):
            pytest.fail("unsupported transport must not run")

    transport.delegate = Other()
    with pytest.raises(CanaryError):
        client_for(transport).create_response(app_request())
    assert not records(saved(registry, writer), "instrumented_dispatch")
