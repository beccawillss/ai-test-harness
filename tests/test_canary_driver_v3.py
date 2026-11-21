"""Stateful public mock application, with real v3 journal/instrumentation paths."""

import copy
import json
import socket
import subprocess
import sys
import threading
import traceback
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from test_canary_instrumentation_v3 import (
    Message,
    ToolOutput,
    app_request,
    attempt_guards,
    prepared,
    records,
)
from test_canary_journal_v3 import (
    make,
    ready,
    receipt,
    retry_failure,
    selected,
    tree_bytes,
)

from harness.canary import journal_v3 as journal
from harness.canary.driver_v3 import (
    DriverError,
    MockApplicationGatewayV3,
    OrderedCanaryDriverV3,
)
from harness.canary.instrumentation_v3 import (
    BoundedResponsesClientV3,
    ProviderTransportV3,
)
from harness.canary.runtime_v3 import V3, resolve_definition
from harness.canary.selection_v3 import ORDER
from harness.targets._salesagent_contract import Constraints

TURNS = resolve_definition(V3).turns


class StatefulApplication:
    """Own sessions and assemble public evidence from returned mock model data.

    This is test code, deliberately scripted rather than model extraction proof.
    Its history/context is built from committed responses, never supplied by the
    driver or substituted with golden state. Every POST invokes the checked client.
    """

    def __init__(self, client, *, mutate=None, history=None, fault=None, calls=2):
        self.client = client
        self.mutate, self.history, self.fault = mutate, history, fault
        self.calls = calls
        self.sessions = {}
        self.traces = {}
        self.posts = []
        self.gets = []
        self.handoffs = []
        self.model_calls = []
        self.before_post = None
        self.request_change = None

    def __call__(self, request):
        if request.method == "GET":
            trace_id = request.url.path.rsplit("/", 1)[-1]
            self.gets.append(trace_id)
            if self.fault == "trace_unavailable":
                return httpx.Response(404)
            value = copy.deepcopy(self.traces[trace_id])
            if self.fault == "reread" and self.gets.count(trace_id) == 2:
                value["latency_ms"] += 1
            return httpx.Response(200, json=value)
        assert request.method == "POST" and request.url.path == "/api/v1/chat"
        body = json.loads(request.content)
        assert set(body) <= {"message", "session_id"}
        turn = next(t for t in TURNS if t.message == body["message"])
        self.posts.append((turn.slot, copy.deepcopy(body)))
        if self.before_post:
            self.before_post(turn.slot)
        if self.fault == "post_failure":
            raise RuntimeError("PRIVATE_APPLICATION_DIAGNOSTIC")
        session = body.get("session_id")
        if session is None:
            session = f"mock-session-{len(self.sessions) + 1}"
            self.sessions[session] = {
                "history": [],
                "constraints": Constraints().model_dump(mode="json"),
                "turn_index": 0,
            }
        state = self.sessions[session]
        state["turn_index"] += 1
        messages = []
        for prior in state["history"]:
            messages.extend(
                [
                    Message("user", prior["user_message"]),
                    Message(
                        "assistant",
                        json.dumps(
                            {
                                "message": prior["message"],
                                "recommended_product_ids": prior[
                                    "recommended_product_ids"
                                ],
                            }
                        ),
                    ),
                ]
            )
        messages.extend(
            [
                Message(
                    "user",
                    json.dumps(
                        {
                            "type": "salesagent_context",
                            "resolved_constraints": state["constraints"],
                        }
                    ),
                ),
                Message("user", turn.message),
            ]
        )
        if self.history:
            messages = self.history(turn.slot, messages, self)
        self.handoffs.append((turn.slot, copy.deepcopy(messages)))
        previous = None
        usage = {key: 0 for key in ("input_tokens", "output_tokens", "total_tokens")}
        final = None
        for number in range(1, self.calls + 1):
            request = app_request(
                input=tuple(messages)
                if number == 1
                else (ToolOutput("mock-tool", "{}"),),
                previous_response_id=previous,
            )
            if self.request_change:
                self.request_change(turn.slot, number, request)
            self.model_calls.append((turn.slot, number))
            final = self.client.create_response(request)
            previous = final.response_id
            for key in usage:
                usage[key] += final.usage[key]
        assert final is not None
        # Commerce/tool evidence came back through the bounded provider path.
        value = copy.deepcopy(final.public_output)
        chat, trace = value["chat"], value["trace"]
        chat.update(session_id=session, trace_id=f"mock-trace-{len(self.posts)}")
        trace.update(
            session_id=session,
            trace_id=chat["trace_id"],
            turn_index=state["turn_index"],
            user_message=body["message"],
            token_usage=usage,
        )
        if self.mutate:
            self.mutate(turn.slot, value)
        state["constraints"] = Constraints.model_validate(
            trace["resolved_constraints"]
        ).model_dump(mode="json")
        state["history"].append(
            {
                "user_message": body["message"],
                "message": chat["message"],
                "recommended_product_ids": trace["recommended_product_ids"],
            }
        )
        self.traces[chat["trace_id"]] = copy.deepcopy(trace)
        return httpx.Response(200, json=chat)


def composition(
    tmp_path, *, mutate=None, history=None, fault=None, calls=2, retry=None
):
    registry, writer = make(tmp_path)
    binding = writer.bind_provider(
        resolve_definition(V3),
        project_id="proj_synthetic",
        organization_id="org_synthetic",
    )
    forwarded = []

    def respond(request):
        snapshot = writer.provider_snapshot(binding)
        slot, number = snapshot.active_slot, snapshot.next_logical_call - 1
        attempt = int(request.headers["x-stainless-retry-count"]) + 1
        forwarded.append((slot, number, attempt))
        if retry and attempt < retry[0]:
            return httpx.Response(500, json=retry_failure(known_zero_usage=retry[1]))
        usage = {"input_tokens": 100 + number, "output_tokens": 10 + number}
        usage["total_tokens"] = sum(usage.values())
        return httpx.Response(
            200,
            json={
                "id": f"resp_{slot}_{number}",
                "model": binding.definition.inference.model,
                "status": "completed",
                "usage": usage,
                "output": [
                    {
                        "public": selected(slot),
                        "reasoning": "PRIVATE_PROVIDER_REASONING",
                    }
                ],
            },
        )

    provider = ProviderTransportV3(
        writer, binding, httpx.MockTransport(respond), guards=attempt_guards
    )
    delegated = []
    cleaned = []

    def create(request):
        delegated.append(request.previous_response_id)
        for retry_index in range(retry[0] if retry else 1):
            response = provider.handle_request(
                prepared(binding, request, retry=retry_index)
            )
            if response.status_code == 200:
                raw = response.json()
                return SimpleNamespace(
                    response_id=raw["id"],
                    usage=raw["usage"],
                    public_output=raw["output"][0]["public"],
                )
        raise RuntimeError("PRIVATE_DELEGATE_FAILURE")

    driver = OrderedCanaryDriverV3(
        writer,
        BoundedResponsesClientV3(SimpleNamespace(create_response=create), provider),
        guards=ready,
        close_client=lambda: cleaned.append(True),
    )
    app = StatefulApplication(
        driver.responses_client,
        mutate=mutate,
        history=history,
        fault=fault,
        calls=calls,
    )
    gateway = MockApplicationGatewayV3(
        httpx.MockTransport(app), responses_client=driver.responses_client
    )
    return SimpleNamespace(
        registry=registry,
        writer=writer,
        binding=binding,
        provider=provider,
        driver=driver,
        app=app,
        gateway=gateway,
        forwarded=forwarded,
        delegated=delegated,
        cleaned=cleaned,
    )


def run(c):
    return c.driver.run(c.gateway)


def test_complete_order_sessions_history_usage_and_seal(tmp_path):
    c = composition(tmp_path)
    report = run(c)
    assert report["status"] == report["driver_status"] == "completed"
    assert report["driver_error"] is None
    assert report["execution_action"] == "COMPLETE"
    assert report["shopper_posts"] == 4 and report["trace_reads"] == 8
    assert [slot for slot, _ in c.app.posts] == list(ORDER)
    a, b, a2, b2 = [body.get("session_id") for _, body in c.app.posts]
    assert a is b is None
    assert a2 == "mock-session-1" and b2 == "mock-session-2"
    assert c.app.gets == [f"mock-trace-{i}" for i in range(1, 5) for _ in range(2)]
    assert [len(messages) for _, messages in c.app.handoffs] == [2, 2, 4, 4]
    assert c.app.handoffs[2][1][0].content == TURNS[0].message
    assert c.app.handoffs[3][1][0].content == TURNS[1].message
    assert len(c.app.sessions[a2]["history"]) == len(c.app.sessions[b2]["history"]) == 2
    assert c.app.sessions[a2]["constraints"]["colour"] == "Moss"
    assert c.app.sessions[b2]["constraints"]["colour"] == "Rust"
    assert (
        report["accounting"]["logical_calls"]
        == report["accounting"]["provider_attempts"]
        == 8
    )
    assert len(c.app.model_calls) == len(c.delegated) == len(c.forwarded) == 8
    for item in records(report, "trace"):
        assert item["trace"]["token_usage"] == {
            "input_tokens": 203,
            "output_tokens": 23,
            "total_tokens": 226,
        }
    assert [r["slot"] for r in records(report, "turn_reserved")] == list(ORDER)
    assert len(records(report, "decision")) == 5
    assert report["mechanical_assessment"]["status"] == "PASS"
    assert report["assessment"]["status"] == "SKIP"
    assert report["human_review"] == "PENDING"
    assert (
        not report["source_authorised"]
        and not report["provider_evidence_authenticated"]
    )
    assert not report["authorises_live_execution"] and not report["dispatch_available"]
    assert c.cleaned == [True] and c.provider.stopped


@pytest.mark.parametrize("slot", ORDER)
@pytest.mark.parametrize("failure", ["state", "tool", "price", "discount"])
def test_behavioural_fail_continues_at_each_slot(tmp_path, slot, failure):
    def mutate(current, value):
        if current != slot:
            return
        if failure == "state" or current == "B1":
            value["trace"]["resolved_constraints"]["maximum_price"] = "1.00"
        elif failure == "tool":
            value["trace"]["tool_calls"] = []
        elif failure == "price":
            value["chat"]["recommendations"][0]["price"] = "99.00"
        else:
            value["chat"]["promotion"] = {"code": "BAD", "valid": False}

    c = composition(tmp_path, mutate=mutate)
    report = run(c)
    assert report["status"] == "completed" and report["shopper_posts"] == 4
    assert report["assessment"]["status"] == "FAIL"
    assert report["operational_assessment"]["status"] == "PASS"
    assert (
        records(report, "assessment")[ORDER.index(slot)]["report"]["prerequisites"][
            "status"
        ]
        == "PASS"
    )


def test_failed_antecedent_is_observed_without_golden_preference_repair(tmp_path):
    def mutate(slot, value):
        if slot == "A1":
            value["trace"]["resolved_constraints"]["colour"] = None

    c = composition(tmp_path, mutate=mutate)
    report = run(c)
    context = json.loads(c.app.handoffs[2][1][-2].content)
    assert context["resolved_constraints"]["colour"] is None
    assert report["status"] == "completed" and report["assessment"]["status"] == "FAIL"
    a2 = records(report, "assessment")[2]["report"]
    assert (
        a2["current_state"]["status"] == "PASS" and a2["retention"]["status"] == "SKIP"
    )


@pytest.mark.parametrize("slot", ORDER)
@pytest.mark.parametrize(
    "fault", ["trace", "session", "turn", "message", "model", "unknown_error"]
)
def test_operational_error_stops_at_each_boundary(tmp_path, slot, fault):
    def mutate(current, value):
        if current != slot:
            return
        trace = value["trace"]
        if fault == "trace":
            trace["trace_id"] = "another-trace"
        elif fault == "session":
            trace["session_id"] = "another-session"
        elif fault == "turn":
            trace["turn_index"] = 99
        elif fault == "message":
            trace["user_message"] = "another message"
        elif fault == "model":
            trace["model"] = "another-model"
        else:
            trace["errors"] = [{"code": "unknown", "message": "PRIVATE_ERROR"}]

    c = composition(tmp_path, mutate=mutate)
    report = run(c)
    assert report["driver_status"] == "stopped"
    assert report["shopper_posts"] == ORDER.index(slot) + 1
    assert report["execution_action"] == "STOP"
    assert report["assessment"]["status"] == "ERROR"
    assert report["human_review"] == "PENDING" and "PRIVATE" not in str(report)


@pytest.mark.parametrize("slot", ORDER)
@pytest.mark.parametrize(
    "fault", ["missing", "modified", "cross_session", "context", "continuation"]
)
def test_bad_history_rejected_before_first_offending_provider_dispatch(
    tmp_path, slot, fault
):
    def history(current, messages, app):
        if current != slot:
            return messages
        if fault == "missing":
            return messages[1:]
        if fault == "modified":
            messages[-1] = Message("user", "PRIVATE_CORRUPT_SHOPPER")
        elif fault == "cross_session":
            messages.insert(
                0, Message("user", TURNS[0 if slot[0] == "B" else 1].message)
            )
        elif fault == "context":
            context = json.loads(messages[-2].content)
            context["resolved_constraints"]["maximum_price"] = "999.00"
            messages[-2] = Message("user", json.dumps(context))
        else:
            messages[-2] = Message("assistant", messages[-2].content)
        return messages

    c = composition(tmp_path, history=history)
    report = run(c)
    assert report["shopper_posts"] == ORDER.index(slot) + 1
    assert len(c.forwarded) == 2 * ORDER.index(slot)
    assert report["instrumentation_stop"] == "request_invalid"
    assert report["status"] == "operationally_uncertain"
    assert len(records(report, "outcome")) == ORDER.index(slot)
    assert "PRIVATE" not in str(report)


@pytest.mark.parametrize("fault", ["trace_unavailable", "reread", "post_failure"])
def test_no_replacement_post_or_trace_repair(tmp_path, fault):
    c = composition(tmp_path, fault=fault)
    report = run(c)
    assert report["shopper_posts"] == len(c.app.posts) == 1
    assert (
        report["trace_reads"]
        == {"trace_unavailable": 1, "reread": 2, "post_failure": 0}[fault]
    )
    assert report["driver_status"] == "stopped" and report["execution_action"] == "STOP"
    assert len(records(report, "chat")) == (0 if fault == "post_failure" else 1)
    if fault == "reread":
        assert records(report, "evidence_error")[0]["code"] == "trace_reread_differs"


@pytest.mark.parametrize("field", ["session", "trace", "provider_session"])
def test_identity_reuse_is_terminal(tmp_path, field):
    def mutate(slot, value):
        if slot != "B1":
            return
        key, chosen = (
            ("session_id", "mock-session-1")
            if field == "session"
            else ("trace_id", "mock-trace-1")
            if field == "trace"
            else ("session_id", "resp_A1_2")
        )
        value["chat"][key] = value["trace"][key] = chosen

    c = composition(tmp_path, mutate=mutate)
    report = run(c)
    assert report["driver_status"] == "stopped" and report["shopper_posts"] == 2
    assert report["assessment"]["status"] == "ERROR"


@pytest.mark.parametrize("key", ["input_tokens", "output_tokens", "last_call_only"])
def test_usage_must_sum_every_logical_call(tmp_path, key):
    def mutate(slot, value):
        if slot == "A1":
            if key == "last_call_only":
                value["trace"]["token_usage"] = {
                    "input_tokens": 102,
                    "output_tokens": 12,
                    "total_tokens": 114,
                }
            else:
                value["trace"]["token_usage"][key] += 1
                value["trace"]["token_usage"]["total_tokens"] += 1

    c = composition(tmp_path, mutate=mutate)
    report = run(c)
    assert report["shopper_posts"] == 1 and report["driver_error"] == "usage_mismatch"
    assert report["execution_action"] == "STOP"
    assert report["accounting"]["logical_calls"] == 2


@pytest.mark.parametrize("known", [False, True])
def test_retry_liabilities_are_not_replaced_by_trace_usage(tmp_path, known):
    c = composition(tmp_path, retry=(3, known))
    report = run(c)
    assert report["accounting"]["unknown_attempts"] == (0 if known else 2)
    assert report["shopper_posts"] == (4 if known else 1)
    assert report["accounting"]["provider_attempts"] == (24 if known else 3)
    assert report["accounting"]["logical_calls"] == (8 if known else 1)
    assert report["status"] == ("completed" if known else "operationally_uncertain")


@pytest.mark.parametrize("calls", [0, 6, 7])
def test_logical_call_boundary(tmp_path, calls):
    c = composition(tmp_path, calls=calls)
    report = run(c)
    assert report["shopper_posts"] == (4 if calls == 6 else 1)
    assert report["accounting"]["logical_calls"] == (
        24 if calls == 6 else min(calls, 6)
    )
    assert report["accounting"]["provider_attempts"] == (
        24 if calls == 6 else min(calls, 6)
    )


@pytest.mark.parametrize("cost", ["4.999", "5", "5.001"])
def test_spending_guard_before_any_post(tmp_path, cost):
    c = composition(tmp_path)
    c.driver._guards = lambda: ready(estimated_total_usd=Decimal(cost))
    report = run(c)
    assert report["shopper_posts"] == (4 if Decimal(cost) < 5 else 0)
    assert report["execution_action"] == ("COMPLETE" if Decimal(cost) < 5 else "STOP")


def test_single_use_and_duplicate_post_do_not_replay(tmp_path):
    c = composition(tmp_path)
    report = run(c)
    before = tree_bytes(Path(c.registry.path))
    with pytest.raises(DriverError, match="driver_reused"):
        run(c)
    assert len(c.app.posts) == 4 and tree_bytes(Path(c.registry.path)) == before
    assert report["status"] == "completed"


def test_duplicate_post_is_consumed_before_callback_and_terminal(tmp_path):
    c = composition(tmp_path)

    def duplicate(slot):
        with pytest.raises(DriverError, match="gateway_invalid"):
            c.gateway.post_chat(TURNS[0].message)

    c.app.before_post = duplicate
    report = run(c)
    assert report["shopper_posts"] == len(c.app.posts) == 1
    assert not c.forwarded and report["instrumentation_stop"] == "request_invalid"


def test_stop_after_request_construction_prevents_mock_post_forwarding(
    tmp_path, monkeypatch
):
    c = composition(tmp_path)
    original = httpx.Request

    def stop(method, url, **kwargs):
        request = original(method, url, **kwargs)
        if method == "POST" and str(url).startswith("http://canary.invalid"):
            c.driver.request_stop()
        return request

    monkeypatch.setattr(httpx, "Request", stop)
    report = run(c)
    assert report["shopper_posts"] == 0 and not c.app.posts and not c.forwarded
    assert len(records(report, "turn_reserved")) == 1
    assert report["instrumentation_stop"] == "operator_stop"


def test_third_trace_read_is_rejected_before_callback(tmp_path):
    c = composition(tmp_path)
    original = c.gateway.get_trace

    def extra(trace_id):
        value = original(trace_id)
        if c.gateway.trace_reads == 2:
            with pytest.raises(DriverError, match="gateway_invalid"):
                original(trace_id)
        return value

    c.gateway.get_trace = extra
    report = run(c)
    assert (
        report["shopper_posts"] == 1 and report["trace_reads"] == len(c.app.gets) == 2
    )
    assert report["instrumentation_stop"] == "request_invalid"


@pytest.mark.parametrize("slot", ["B1", "A2", "B2"])
def test_previous_provider_response_cannot_continue_another_shopper_turn(
    tmp_path, slot
):
    c = composition(tmp_path)

    def corrupt(current, number, request):
        if current == slot and number == 1:
            request.previous_response_id = "resp_A1_2"

    c.app.request_change = corrupt
    report = run(c)
    assert report["shopper_posts"] == ORDER.index(slot) + 1
    assert len(c.forwarded) == 2 * ORDER.index(slot)
    assert report["instrumentation_stop"] == "request_invalid"


@pytest.mark.parametrize("field", ["assistant", "products", "prior_shopper"])
def test_previous_public_history_must_match_exact_observations(tmp_path, field):
    def history(slot, messages, app):
        if slot != "A2":
            return messages
        if field == "prior_shopper":
            messages[0] = Message("user", "modified previous shopper")
        else:
            value = json.loads(messages[1].content)
            value["message" if field == "assistant" else "recommended_product_ids"] = (
                "modified previous answer" if field == "assistant" else ["ACC-001"]
            )
            messages[1] = Message("assistant", json.dumps(value))
        return messages

    c = composition(tmp_path, history=history)
    report = run(c)
    assert report["shopper_posts"] == 3 and len(c.forwarded) == 4
    assert report["instrumentation_stop"] == "request_invalid"


def test_stop_during_forwarded_attempt_drains_result_but_no_public_outcome(tmp_path):
    c = composition(tmp_path)
    original = c.provider.delegate.handler
    entered, release = threading.Event(), threading.Event()
    result = []

    def respond(request):
        entered.set()
        assert release.wait(10)
        return original(request)

    c.provider.delegate = httpx.MockTransport(respond)
    thread = threading.Thread(target=lambda: result.append(run(c)))
    thread.start()
    assert entered.wait(10)
    c.driver.request_stop()
    release.set()
    thread.join(10)
    assert not thread.is_alive()
    report = result[0]
    assert len(c.forwarded) == 1 and report["shopper_posts"] == 1
    assert len(records(report, "instrumented_result")) == 1
    assert len(records(report, "instrumented_call_finished")) == 1
    assert not records(report, "outcome") and not records(report, "chat")
    assert report["accounting"]["unknown_attempts"] == 0
    assert report["status"] == "operationally_uncertain"


def test_actual_known_spending_pause_inside_post_is_terminal(tmp_path):
    c = composition(tmp_path)
    original = c.provider.delegate.handler

    def expensive(request):
        response = original(request)
        raw = response.json()
        raw["usage"] = {
            "input_tokens": 1_000_000,
            "output_tokens": 0,
            "total_tokens": 1_000_000,
        }
        return httpx.Response(200, json=raw)

    c.provider.delegate = httpx.MockTransport(expensive)
    report = run(c)
    assert report["shopper_posts"] == len(c.forwarded) == 1
    assert report["instrumentation_stop"] == "spending_pause"
    assert Decimal(report["accounting"]["estimated_subtotal_usd"]) == 5
    assert not records(report, "outcome")


def test_stop_during_post_preserves_prefix_and_closes_both_gates(tmp_path):
    c = composition(tmp_path)
    entered, release = threading.Event(), threading.Event()
    result = []

    def wait(slot):
        entered.set()
        assert release.wait(10)

    c.app.before_post = wait
    thread = threading.Thread(target=lambda: result.append(run(c)))
    thread.start()
    assert entered.wait(10)
    c.driver.request_stop()
    assert c.driver._halted.is_set() and c.provider.stopped
    release.set()
    thread.join(10)
    assert not thread.is_alive()
    report = result[0]
    assert report["shopper_posts"] == 1 and not c.forwarded
    assert not records(report, "outcome") and not records(report, "chat")
    assert report["execution_action"] == "ADVANCE"  # Historical, overridden by stop.
    assert (
        report["instrumentation_terminal_stop_recorded"]
        and not report["dispatch_available"]
    )


@pytest.mark.parametrize(
    "kind",
    [
        "turn_reserved",
        "chat",
        "trace",
        "assessment",
        "outcome",
        "decision",
        "completion",
    ],
)
@pytest.mark.parametrize("published", [False, True])
def test_publication_fault_preserves_prefix_and_never_replaces_post(
    tmp_path, monkeypatch, kind, published
):
    c = composition(tmp_path)
    original = journal._publish
    prefix = {}
    fired = False

    def fail(directory, name, value):
        nonlocal fired, prefix
        if not fired and value.get("kind") == kind:
            fired = True
            prefix = tree_bytes(Path(c.registry.path))
            if published:
                original(directory, name, value)
            raise OSError("PRIVATE_DISK_FAILURE")
        return original(directory, name, value)

    monkeypatch.setattr(journal, "_publish", fail)
    report = run(c)
    assert fired and report["driver_status"] == "stopped"
    assert report["shopper_posts"] <= 4
    after = tree_bytes(Path(c.registry.path))
    assert all(after[name] == data for name, data in prefix.items())
    assert report["status"] != "completed" and "PRIVATE" not in str(report)
    output = tmp_path / "saved"
    saved = journal.recover_save_only(c.registry, "run-1", output)
    assert saved["records"] == report["records"]
    assert tree_bytes(Path(c.registry.path)) == after
    with pytest.raises(journal.JournalError):
        journal.CanaryJournal(
            c.registry, "run-1", "new-claim", source_receipt=receipt()
        )


def test_no_clients_credentials_network_or_private_diagnostic_leakage(
    tmp_path, monkeypatch, capsys
):
    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected client construction")

    monkeypatch.setattr(httpx.Client, "__init__", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "__init__", forbidden)
    c = composition(tmp_path)
    report = run(c)
    assert report["status"] == "completed"
    assert "PRIVATE" not in str(report)
    assert "Bearer" not in str(report)
    assert "PRIVATE" not in "".join(capsys.readouterr())
    unapproved = "PRIVATE_" + "UNAPPROVED_DIAGNOSTIC"
    try:
        raise DriverError(unapproved)
    except DriverError:
        assert unapproved not in traceback.format_exc()


@pytest.mark.parametrize("slot", ["A2", "B2"])
def test_correlated_but_changed_continuation_session_stops(tmp_path, slot):
    def mutate(current, value):
        if current == slot:
            value["chat"]["session_id"] = value["trace"]["session_id"] = (
                "changed-session"
            )

    c = composition(tmp_path, mutate=mutate)
    report = run(c)
    assert report["shopper_posts"] == ORDER.index(slot) + 1
    assert report["assessment"]["status"] == "ERROR"
    assert report["driver_status"] == "stopped"


@pytest.mark.parametrize("field", ["session_id", "trace_id"])
@pytest.mark.parametrize("value", [None, "", "../unsafe"])
def test_failed_initial_identity_creation_never_continues(tmp_path, field, value):
    def mutate(slot, saved):
        saved["chat"][field] = saved["trace"][field] = value

    c = composition(tmp_path, mutate=mutate)
    report = run(c)
    assert report["shopper_posts"] == 1 and report["trace_reads"] == 0
    assert report["assessment"]["status"] == "ERROR"


@pytest.mark.parametrize(
    "guard",
    [
        "safety_ok",
        "privacy_ok",
        "operator_allows_dispatch",
        "source_and_fixtures_verified",
    ],
)
def test_failed_initial_operational_guard_prevents_every_post(tmp_path, guard):
    c = composition(tmp_path)
    c.driver._guards = lambda: ready(**{guard: False})
    report = run(c)
    assert report["shopper_posts"] == 0 and not c.forwarded
    assert report["execution_action"] == "STOP"


def test_incorrect_returned_decision_cannot_override_persisted_schedule(tmp_path):
    c = composition(tmp_path)
    original = c.writer.record_decision

    def wrong(guards):
        decision = original(guards)
        return replace(decision, next_slot="B1")

    c.writer.record_decision = wrong
    report = run(c)
    assert report["shopper_posts"] == 0 and not c.forwarded
    assert not records(report, "turn_reserved")
    assert report["driver_error"] == "configuration_invalid"


def test_mock_callback_network_attempt_is_rejected_without_second_post(tmp_path):
    c = composition(tmp_path)
    c.app.before_post = lambda slot: socket.create_connection(
        ("unexpected.invalid", 443)
    )
    report = run(c)
    assert report["shopper_posts"] == 1 and not c.forwarded
    assert report["driver_status"] == "stopped" and report["execution_action"] == "STOP"


def test_uninstrumented_application_evidence_cannot_claim_success(tmp_path):
    c = composition(tmp_path)
    c.gateway._transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=selected("A1")["chat"])
    )
    report = run(c)
    assert report["shopper_posts"] == 1 and not c.forwarded
    assert report["execution_action"] == "STOP"
    assert report["accounting"]["logical_calls"] == 0


@pytest.mark.parametrize("unsupported", ["network", "subclass"])
def test_gateway_requires_exact_mock_transport(tmp_path, unsupported):
    c = composition(tmp_path)

    class Other(httpx.BaseTransport):
        def handle_request(self, request):
            pytest.fail("Unsupported transport was called")

    class Subclass(httpx.MockTransport):
        pass

    delegate = (
        Other() if unsupported == "network" else Subclass(lambda _: httpx.Response(200))
    )
    with pytest.raises(DriverError, match="gateway_invalid"):
        MockApplicationGatewayV3(delegate, responses_client=c.driver.responses_client)
    c.writer.close()


def test_cleanup_failure_prevents_completion_seal(tmp_path):
    c = composition(tmp_path)

    def fail():
        raise RuntimeError("PRIVATE_CLEANUP_DIAGNOSTIC")

    c.driver._close_client = fail
    report = run(c)
    assert report["shopper_posts"] == 4
    assert report["driver_error"] == "cleanup_failed"
    assert not report["completion_seal_present"]
    assert report["status"] == "operationally_uncertain"
    assert "PRIVATE" not in str(report)


@pytest.mark.parametrize("phase", ["reserved", "dispatched"])
def test_abrupt_process_loss_is_save_only(tmp_path, phase):
    program = r"""
import os, sys
from pathlib import Path
from test_canary_driver_v3 import composition, run
from harness.canary import journal_v3 as journal
c = composition(Path(sys.argv[1]))
original = journal._publish
def publish(directory, name, value):
    original(directory, name, value)
    kind = value.get("kind")
    if kind == ("turn_reserved" if sys.argv[2] == "reserved" else "instrumented_dispatch"):
        os._exit(23)
journal._publish = publish
run(c)
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", program, str(tmp_path), phase],
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": "src:tests",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        check=False,
        timeout=20,
    )
    assert result.returncode == 23, result.stderr.decode()
    registry = journal.load_registry(tmp_path / "v3-registry")
    report = journal.inspect_run(registry, "run-1")
    assert report["status"] == "operationally_uncertain"
    assert report["accounting"]["unknown_attempts"] == (
        1 if phase == "dispatched" else 0
    )
    assert not report["dispatch_available"]
    assert not records(report, "outcome")
    before = tree_bytes(Path(registry.path))
    journal.recover_save_only(registry, "run-1", tmp_path / "saved")
    assert tree_bytes(Path(registry.path)) == before
