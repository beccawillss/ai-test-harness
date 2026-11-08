"""Canary orchestration/accounting is offline and independent of Study captures."""

import copy
import json
import logging
import os
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest

from harness.canary.driver import (
    CanaryDriver,
    ReplayTransport,
    export_human_packet,
    load_target_replay,
    reveal_judgments,
    save_human_ratings,
)
from harness.canary.inputs import (
    ANCHORS,
    JUDGE_EXAMPLES,
    JUDGE_MODEL,
    JUDGE_ORDER,
    TARGET_MODEL,
    TARGET_TURNS,
    judge_inputs,
    roster_hash,
    scorer,
)
from harness.canary.recording import (
    BoundedResponsesClient,
    CanaryError,
    CanaryStore,
    ProviderTransport,
    usage_metadata,
)


@pytest.fixture
def store(tmp_path):
    return CanaryStore(tmp_path / "salesagent-preflight-canary" / "test")


def ratings():
    return {
        f"J{i}": {"score": 0.8, "reason": "Independent synthetic rating."}
        for i in range(1, 9)
    }


def approve_ratings(store):
    save_human_ratings(store, ratings(), reviewer="beccawillss", exposure="not_seen")


def provider_envelope(score=0.8, *, model=JUDGE_MODEL, usage=True, **updates):
    value = {
        "id": "resp_canary",
        "model": model,
        "status": "completed",
        "output": [
            {"type": "reasoning", "summary": ["HIDDEN_REASONING"]},
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(
                            {"score": score, "reason": "Synthetic observable reason."}
                        ),
                    }
                ],
            },
        ],
    }
    if usage:
        value["usage"] = {
            "input_tokens": 1000,
            "output_tokens": 100,
            "total_tokens": 1100,
            "input_tokens_details": {"cached_tokens": 200, "cache_write_tokens": 300},
            "output_tokens_details": {"reasoning_tokens": 60},
        }
    value.update(updates)
    return value


def provider_request(model=TARGET_MODEL, **updates):
    value = {
        "model": model,
        "max_output_tokens": 2000 if model == TARGET_MODEL else 8192,
        "input": "INTERNAL_PROMPT_SECRET",
        "tools": [{"description": "INTERNAL_PROMPT_SECRET"}],
    }
    value.update(updates)
    return httpx.Request(
        "POST",
        "https://api.openai.com/v1/responses",
        headers={"authorization": "Bearer CREDENTIAL_SECRET"},
        json=value,
    )


def events(store, kind="provider_attempt"):
    return [
        v
        for p in store.path.glob("event-*.json")
        if (v := json.loads(p.read_text()))["kind"] == kind
    ]


class CanaryHTTP:
    """Synthetic public exchanges; no target app or provider is imported."""

    def __init__(self, fault=None):
        self.requests, self.traces, self.exchanges = [], {}, {}
        self.fault = fault

    def __call__(self, request):
        self.requests.append(request)
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/openapi.json":
            return httpx.Response(
                200,
                json={
                    "paths": {
                        "/api/v1/chat": {"post": {}},
                        "/api/v1/traces/{trace_id}": {"get": {}},
                    }
                },
            )
        if request.method == "GET":
            return httpx.Response(
                200, json=self.traces[request.url.path.rsplit("/", 1)[-1]]
            )
        body = json.loads(request.content)
        turn = TARGET_TURNS[len(self.exchanges)]
        if self.fault == turn.slot:
            raise httpx.ReadTimeout("CREDENTIAL_SECRET INTERNAL_PROMPT_SECRET")
        session = "session-" + turn.conversation
        if int(turn.slot[1]) == 1:
            assert body == {"message": turn.message}
        else:
            assert body == {"message": turn.message, "session_id": session}
        trace_id = "trace-" + turn.slot
        pid, name, price, colour, size, stock = (
            ("ACC-001", "Summit Rib Beanie", "22.00", "Rust", "One Size", 6)
            if turn.slot == "B2"
            else ("ACC-003", "Tern Roll-Top Day Pack", "55.00", "Moss", "20L", 5)
        )
        variant = {"colour": colour, "size": size, "stock": stock}
        product = {
            "product_id": pid,
            "name": name,
            "price": price,
            "currency": "GBP",
            "product_url": "/products/canary",
            "category": "accessory",
            "activities": ["walking"],
            "weather": ["cold"],
            "features": ["soft"],
            "waterproof_rating": "water-resistant",
            "warmth": "medium",
            "variants": [variant],
            "total_stock": stock,
        }
        tools = []

        def tool(name, arguments, data):
            tools.append(
                {
                    "sequence": len(tools) + 1,
                    "tool_call_id": "call_" + str(len(tools)),
                    "tool_name": name,
                    "arguments": arguments,
                    "result": {
                        "tool_name": name,
                        "success": True,
                        "data": data,
                        "error": None,
                    },
                    "status": "success",
                    "duration_ms": 1,
                }
            )

        if turn.slot != "B1":
            tool("get_product", {"product_id": pid}, product)
            if turn.slot != "A2":
                tool("search_products", {}, {"products": [product], "count": 1})
                tool(
                    "check_inventory",
                    {"product_id": pid, "colour": colour, "size": size},
                    {
                        "product_id": pid,
                        **variant,
                        "available": True,
                        "status": "in_stock",
                    },
                )
        promotion = None
        pricing = None
        if turn.slot == "A2":
            promotion = {
                "code": "WELCOME10",
                "valid": True,
                "discount_percent": "10",
                "reason": "active",
            }
            tool("validate_discount", {"code": "WELCOME10"}, promotion)
            pricing = {
                "product_id": pid,
                "base_price": "55.00",
                "final_price": "49.50",
                "currency": "GBP",
                "discount_code": "WELCOME10",
                "discount_percent": "10",
            }
        rec = {
            k: product[k]
            for k in ("product_id", "name", "price", "currency", "product_url")
        }
        rec.update(availability="in_stock", matched_variant=variant)
        chat = {
            "session_id": session,
            "trace_id": trace_id,
            "message": "Synthetic public answer.",
            "recommendations": [] if turn.slot == "B1" else [rec],
            "promotion": promotion,
            "pricing": pricing,
        }
        trace = {
            "session_id": session,
            "trace_id": trace_id,
            "timestamp": "2026-11-06T00:00:00Z",
            "turn_index": int(turn.slot[1]),
            "user_message": turn.message,
            "model": TARGET_MODEL,
            "prompt_version": "synthetic",
            "resolved_constraints": {}
            if turn.slot == "B1"
            else {"category": "accessory", "colour": colour, "size": size},
            "constraint_changes": [],
            "tool_calls": tools,
            "recommendation_validation": {
                "all_products_exist": True,
                "prices_match_catalogue": True,
                "urls_match_catalogue": True,
                "stock_claims_validated": True,
                "validation_errors": [],
            },
            "recommended_product_ids": [] if turn.slot == "B1" else [pid],
            "promotion": promotion,
            "pricing": pricing,
            "latency_ms": 1,
            "token_usage": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
            "errors": [],
        }
        self.traces[trace_id] = trace
        self.exchanges[turn.slot] = {"chat": chat, "trace": trace}
        return httpx.Response(200, json=chat)


def test_exact_roster_and_prepared_prompt_hashes():
    assert [t.slot for t in TARGET_TURNS] == ["A1", "B1", "A2", "B2"]
    assert JUDGE_ORDER == tuple(f"J{i}" for i in range(1, 9)) * 2
    expected = [
        "59e6b353c70bf223c336188c68c67ad51eaf3395246eeefe9aa8282c850ec0f9",
        "edaa8e6bf752ffeeb2c0681cad6e12e3f208188126ba3eb8aaee37554ba8e068",
        "9ea7d8dfd3d7d5e384f1985f8d54d39426ba6a922fff0c9ae988ce4b0217843c",
        "c2f1be4e07935b9c61fd4a9240772d470ec34fa9cf10216b20061a5a0a61e8d6",
        "d4ae0ad428754082d346e09655dd20d1f30e99a031f0dcd20fee281b96ba5edc",
        "4fe2a112e2a05ca55d0220c066c6b41870aa5c8811f94f39df265bf406d6aef8",
        "093304b7e3cb4fc790429d3cdb3779b365b0c50b8567922e5c3a73fe180f52a8",
        "7022b31cfa1b2beb61cd62c29c0e767be2401daab4cc31cd04a7f27116a743fa",
    ]
    assert [p.prompt_hash for p in judge_inputs().values()] == expected
    assert all(
        "Synthetic public answer" not in p.prompt for p in judge_inputs().values()
    )
    assert (
        roster_hash()
        == "e8778ce74a270e6efbe490198d01e8b9c50bcc43387a02bff5f00b42304d5794"
    )
    assert len(JUDGE_EXAMPLES) == 8


def test_interleaved_target_roster_and_offline_saved_replay(store):
    fake = CanaryHTTP()
    responses = CanaryDriver(store).run_target(httpx.MockTransport(fake))
    assert list(responses) == ["A", "B"]
    assert len(fake.requests) == 14
    posts = [r for r in fake.requests if r.method == "POST"]
    assert [json.loads(r.content)["message"] for r in posts] == [
        t.message for t in TARGET_TURNS
    ]
    replayed = load_target_replay(store.path)
    for conversation in responses:
        assert replayed[conversation].structured == responses[conversation].structured
        assert replayed[conversation].metadata == responses[conversation].metadata
    with pytest.raises(CanaryError):
        CanaryDriver(store).run_target(httpx.MockTransport(fake))
    assert len(fake.requests) == 14


@pytest.mark.parametrize("fault,posts", [("A1", 1), ("B1", 2), ("A2", 3), ("B2", 4)])
def test_no_replacements_after_target_failure(store, fault, posts):
    fake = CanaryHTTP(fault)
    with pytest.raises(CanaryError, match="no replacement") as exc:
        CanaryDriver(store).run_target(httpx.MockTransport(fake))
    assert "SECRET" not in str(exc.value)
    assert len([r for r in fake.requests if r.method == "POST"]) == posts
    with pytest.raises(CanaryError):
        CanaryDriver(store).run_target(httpx.MockTransport(fake))
    assert len([r for r in fake.requests if r.method == "POST"]) == posts


def test_recording_failure_prevents_dispatch(store, monkeypatch):
    fake = CanaryHTTP()

    def fail(*args, **kwargs):
        raise OSError("SECRET")

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(CanaryError, match="recording failed"):
        CanaryDriver(store).run_target(httpx.MockTransport(fake))
    assert fake.requests == []
    assert store.stopped


def test_offline_modes_never_accept_network_fallback(store):
    transport = httpx.HTTPTransport()
    try:
        with pytest.raises(CanaryError, match="Offline"):
            CanaryDriver(store).run_target(transport)
        with pytest.raises(CanaryError, match="Offline"):
            ProviderTransport(store, transport, role="target")
        with pytest.raises(CanaryError):
            ReplayTransport({}, "A")
    finally:
        transport.close()


def test_private_artifacts_and_namespace_restrictions(tmp_path, store):
    assert store.path.stat().st_mode & 0o777 == 0o700
    assert (store.path / "manifest.json").stat().st_mode & 0o777 == 0o600
    with pytest.raises(CanaryError):
        CanaryStore(
            tmp_path / "salesagent-study-v1" / "salesagent-preflight-canary" / "bad"
        )
    with pytest.raises(FileExistsError):
        CanaryStore(store.path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: somewhere")
    with pytest.raises(CanaryError):
        CanaryStore(repo / "salesagent-preflight-canary" / "bad")


def test_provider_bytes_ids_usage_and_costs_are_preserved_redacted(store):
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(
            200,
            json=provider_envelope(model=TARGET_MODEL),
            headers={"x-request-id": "req_canary", "authorization": "SECRET"},
        )

    transport = ProviderTransport(store, httpx.MockTransport(respond), role="target")
    request = provider_request()
    before = request.content
    with transport.logical("A1"):
        response = transport.handle_request(request)
    assert seen == [request] and seen[0] is request
    assert request.content == before
    assert response.json()["output"][0]["summary"] == ["HIDDEN_REASONING"]
    record = events(store)[0]
    assert (
        record["request_id"] == "req_canary" and record["response_id"] == "resp_canary"
    )
    assert record["cached_tokens"] == 200 and record["reasoning_tokens"] == 60
    assert Decimal(record["estimated_usd"]) == Decimal(
        "0.00299"
    )  # 500*2 + 200*.2 + 300*2.5 + 100*12
    saved = "".join(p.read_text() for p in store.path.glob("*.json"))
    assert all(
        secret not in saved
        for secret in (
            "CREDENTIAL_SECRET",
            "INTERNAL_PROMPT_SECRET",
            "HIDDEN_REASONING",
            "authorization",
            '"output":',
        )
    )
    assert store.accounting()["attempts"] == 1


@pytest.mark.parametrize(
    "usage",
    [None, {}, {"input_tokens": None}, {"input_tokens": True}, {"input_tokens": -1}],
)
def test_missing_invalid_usage_is_unknown(usage):
    result = usage_metadata({"usage": usage}, role="target")
    assert result["estimated_usd"] is None
    assert result["input_tokens"] is None
    assert result["output_tokens"] is None
    assert result["cached_tokens"] is None


def test_partial_cache_usage_uses_conservative_estimate_without_fabricating_counts():
    result = usage_metadata(
        {"usage": {"input_tokens": 1000, "output_tokens": 100}}, role="target"
    )
    assert result["cache_write_tokens"] is None and result["reasoning_tokens"] is None
    assert Decimal(result["estimated_usd"]) == Decimal("0.0037")
    zero = usage_metadata(
        {"usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}},
        role="judge",
    )
    assert Decimal(zero["estimated_usd"]) == 0


def test_retry_and_unknown_attempts_remain_visible_and_pause_next_call(store):
    replies = iter(
        [
            httpx.Response(500, json={"error": {"message": "SECRET"}}),
            httpx.Response(200, json=provider_envelope(model=TARGET_MODEL)),
        ]
    )
    transport = ProviderTransport(
        store, httpx.MockTransport(lambda _: next(replies)), role="target"
    )
    with transport.logical("A1"):
        transport.handle_request(provider_request())
        transport.handle_request(provider_request())
    assert sorted(e["retry_index"] for e in events(store)) == [0, 1]
    assert store.accounting()["estimated_total_usd"] is None
    assert store.accounting()["unknown_attempts"] == 1
    with pytest.raises(CanaryError, match="unknown usage"), transport.logical("A1", 2):
        pytest.fail("must not dispatch")


def test_ambiguous_failure_cannot_be_replayed(store):
    calls = []

    def fail(request):
        calls.append(request)
        raise httpx.ReadTimeout("SECRET")

    transport = ProviderTransport(store, httpx.MockTransport(fail), role="target")
    with pytest.raises(CanaryError), transport.logical("A1"):
        transport.handle_request(provider_request())
    assert store.accounting()["estimated_total_usd"] is None
    with pytest.raises(CanaryError):
        transport.handle_request(provider_request())
    assert len(calls) == 1


def test_unfinished_dispatch_is_unknown(store):
    store.event(
        {
            "kind": "provider_dispatch",
            "role": "target",
            "slot": "A1",
            "logical_call": 1,
            "attempt": 1,
        }
    )
    assert store.accounting()["attempts"] == 1
    assert store.accounting()["unknown_attempts"] == 1
    assert store.accounting()["estimated_total_usd"] is None


def test_target_provider_attempt_limit_without_changing_request(store):
    seen = []

    def reply(request):
        seen.append(request.content)
        return httpx.Response(200, json=provider_envelope(model=TARGET_MODEL))

    transport = ProviderTransport(store, httpx.MockTransport(reply), role="target")
    with pytest.raises(CanaryError), transport.logical("A1"):
        for _ in range(4):
            transport.handle_request(provider_request())
    assert len(seen) == 3


def test_provider_recording_failure_stops_before_sending(store, monkeypatch):
    calls = []
    transport = ProviderTransport(
        store, httpx.MockTransport(lambda r: calls.append(r)), role="target"
    )
    with pytest.raises(CanaryError), transport.logical("A1"):
        monkeypatch.setattr(
            os, "fsync", lambda *_: (_ for _ in ()).throw(OSError("SECRET"))
        )
        transport.handle_request(provider_request())
    assert calls == []


def test_human_ratings_are_required_before_judge_construction_and_reveal(
    store, monkeypatch
):
    calls = []
    with pytest.raises((CanaryError, FileNotFoundError)):
        reveal_judgments(store)
    with pytest.raises(CanaryError):
        CanaryDriver(store).run_judge(httpx.MockTransport(lambda r: calls.append(r)))
    assert calls == []


def test_judge_exact_order_repetitions_and_ratings_gate(store):
    approve_ratings(store)
    calls = []

    def reply(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=provider_envelope())

    result = CanaryDriver(store).run_judge(httpx.MockTransport(reply))
    assert result["attempts"] == 16
    prepared = judge_inputs()
    assert [r["input"][0]["content"] for r in calls] == [
        prepared[k].prompt for k in JUDGE_ORDER
    ]
    assert all(
        r["max_output_tokens"] == 8192
        and r["store"] is False
        and r["tools"] == []
        and "reasoning" not in r
        for r in calls
    )
    assert len(reveal_judgments(store)) == 16
    with pytest.raises(CanaryError):
        CanaryDriver(store).run_judge(httpx.MockTransport(reply))
    assert len(calls) == 16
    with pytest.raises(CanaryError):
        save_human_ratings(
            store, ratings(), reviewer="beccawillss", exposure="not_seen"
        )


@pytest.mark.parametrize("score", [0.7, True, -1, 1.1, "0.8"])
def test_invalid_judge_results_stop_without_replacement(store, score):
    approve_ratings(store)
    calls = []

    def reply(request):
        calls.append(request)
        return httpx.Response(200, json=provider_envelope(score))

    with pytest.raises(CanaryError):
        CanaryDriver(store).run_judge(httpx.MockTransport(reply))
    assert len(calls) == 1
    assert not (store.path / "judge-J1-1.json").exists()
    with pytest.raises(CanaryError):
        CanaryDriver(store).run_judge(httpx.MockTransport(reply))
    assert len(calls) == 1


@pytest.mark.parametrize("anchor", ANCHORS)
def test_existing_anchor_parser_is_reused(anchor):
    assert (
        scorer().parse_judgement(json.dumps({"score": anchor, "reason": "Synthetic."}))[
            0
        ]
        == anchor
    )


def test_changed_human_rating_receipt_blocks_all_judge_calls(store):
    approve_ratings(store)
    path = store.path / "human-ratings.json"
    value = json.loads(path.read_text())
    value["ratings"]["J1"]["score"] = 0.3
    path.write_text(json.dumps(value))
    calls = []
    with pytest.raises(CanaryError):
        CanaryDriver(store).run_judge(httpx.MockTransport(lambda r: calls.append(r)))
    assert calls == []


def test_target_decorator_bounds_and_forwards_the_same_application_request(store):
    seen = []
    delegate = SimpleNamespace(
        create_response=lambda r: (
            seen.append(r) or SimpleNamespace(response_id="resp_next")
        )
    )
    provider = ProviderTransport(
        store, httpx.MockTransport(lambda _: pytest.fail("no network")), role="target"
    )
    wrapper = BoundedResponsesClient(delegate, provider)
    request = SimpleNamespace(
        previous_response_id=None,
        input=TARGET_TURNS[0].message,
        model=TARGET_MODEL,
        reasoning_effort="low",
        max_output_tokens=2000,
    )
    wrapper.create_response(request)
    assert seen[0] is request
    bad = copy.copy(request)
    bad.input = "unapproved shopper input"
    with pytest.raises(CanaryError):
        wrapper.create_response(bad)
    assert len(seen) == 1


def test_export_packet_has_no_scores_and_does_not_assume_no_exposure(store):
    export_human_packet(store)
    packet = json.loads((store.path / "human-packet.json").read_text())
    draft = json.loads((store.path / "human-draft.json").read_text())
    assert [r["id"] for r in packet["examples"]] == list(JUDGE_ORDER[:8])
    assert draft["judge_output_exposure"] == "unknown"
    assert all(r == {"score": None, "reason": ""} for r in draft["ratings"].values())
    assert not list(store.path.glob("reserved-judge-*.json"))


@pytest.mark.parametrize("exposure", ["unknown", "seen", "", None])
def test_human_unknown_or_exposed_declarations_do_not_authorise_judging(
    store, exposure
):
    with pytest.raises(CanaryError):
        save_human_ratings(store, ratings(), reviewer="beccawillss", exposure=exposure)
    assert not (store.path / "human-ratings-receipt.json").exists()


@pytest.mark.parametrize(
    "override",
    [
        {"model": "different"},
        {"max_output_tokens": 2048},
        {"stream": True},
        {"prompt_cache_retention": "12h"},
        {"service_tier": "fast"},
    ],
)
def test_provider_configuration_drift_is_rejected_before_dispatch(store, override):
    calls = []
    provider = ProviderTransport(
        store, httpx.MockTransport(lambda r: calls.append(r)), role="target"
    )
    with pytest.raises(CanaryError), provider.logical("A1"):
        provider.handle_request(provider_request(**override))
    assert calls == []


@pytest.mark.parametrize("status", ["incomplete", "failed", ["malformed"], None])
def test_incomplete_or_malformed_provider_status_stops_judge(store, status):
    approve_ratings(store)
    calls = []

    def reply(request):
        calls.append(request)
        return httpx.Response(200, json=provider_envelope(status=status))

    with pytest.raises(CanaryError):
        CanaryDriver(store).run_judge(httpx.MockTransport(reply))
    assert len(calls) == 1


def test_judge_has_no_http_retries(store):
    approve_ratings(store)
    calls = []

    def reply(request):
        calls.append(request)
        return httpx.Response(500, json={"error": {"message": "SECRET"}})

    with pytest.raises(CanaryError):
        CanaryDriver(store).run_judge(httpx.MockTransport(reply))
    assert len(calls) == 1
    assert store.accounting()["estimated_total_usd"] is None


def test_output_recording_failure_blocks_any_replacement_attempt(store, monkeypatch):
    calls = []

    def reply(request):
        calls.append(request)
        monkeypatch.setattr(
            os, "fsync", lambda *_: (_ for _ in ()).throw(OSError("SECRET"))
        )
        return httpx.Response(200, json=provider_envelope(model=TARGET_MODEL))

    provider = ProviderTransport(store, httpx.MockTransport(reply), role="target")
    with pytest.raises(CanaryError), provider.logical("A1"):
        provider.handle_request(provider_request())
    with pytest.raises(CanaryError):
        provider.handle_request(provider_request())
    assert len(calls) == 1 and store.stopped


def test_pause_threshold_stops_before_another_dispatch(store):
    store.event(
        {
            "kind": "provider_dispatch",
            "role": "target",
            "slot": "A1",
            "logical_call": 1,
            "attempt": 1,
        }
    )
    store.event(
        {
            "kind": "provider_attempt",
            "role": "target",
            "slot": "A1",
            "logical_call": 1,
            "attempt": 1,
            "estimated_usd": "5",
        }
    )
    calls = []
    with pytest.raises(CanaryError, match="paused"):
        CanaryDriver(store).run_target(httpx.MockTransport(lambda r: calls.append(r)))
    assert calls == []


def test_target_decorator_rejects_seventh_logical_call(store):
    seen = []
    delegate = SimpleNamespace(
        create_response=lambda r: (
            seen.append(r) or SimpleNamespace(response_id="resp_next")
        )
    )
    provider = ProviderTransport(
        store, httpx.MockTransport(lambda _: pytest.fail("no HTTP")), role="target"
    )
    wrapper = BoundedResponsesClient(delegate, provider)
    request = SimpleNamespace(
        previous_response_id=None,
        input=TARGET_TURNS[0].message,
        model=TARGET_MODEL,
        reasoning_effort="low",
        max_output_tokens=2000,
    )
    for _ in range(6):
        wrapper.create_response(request)
        request.previous_response_id = "resp_next"
    with pytest.raises(CanaryError):
        wrapper.create_response(request)
    assert len(seen) == 6


def test_public_target_extra_fields_are_discarded_before_storage(store):
    fake = CanaryHTTP()

    def respond(request):
        response = fake(request)
        value = response.json()
        if "message" in value or "tool_calls" in value:
            value["internal_prompt"] = "INTERNAL_PROMPT_SECRET"
        if "tool_calls" in value:
            for tool in value["tool_calls"]:
                tool["arguments"]["internal_prompt"] = "INTERNAL_PROMPT_SECRET"
                tool["result"]["data"]["internal_prompt"] = "INTERNAL_PROMPT_SECRET"
        return httpx.Response(200, json=value)

    CanaryDriver(store).run_target(httpx.MockTransport(respond))
    assert "INTERNAL_PROMPT_SECRET" not in "".join(
        p.read_text() for p in store.path.glob("*.json")
    )


def test_session_leak_stops_before_continuations(store):
    fake = CanaryHTTP()

    def respond(request):
        response = fake(request)
        value = response.json()
        if request.method == "POST" and len(fake.exchanges) == 2:
            value["session_id"] = "session-A"
        return httpx.Response(200, json=value)

    with pytest.raises(CanaryError):
        CanaryDriver(store).run_target(httpx.MockTransport(respond))
    assert len([r for r in fake.requests if r.method == "POST"]) == 2


def test_invalid_trace_diagnostics_are_not_persisted_and_stop_dispatch(store):
    fake = CanaryHTTP()

    def respond(request):
        response = fake(request)
        value = response.json()
        if "recommendation_validation" in value:
            value["recommendation_validation"]["validation_errors"] = [
                "INTERNAL_PROMPT_SECRET"
            ]
        return httpx.Response(200, json=value)

    with pytest.raises(CanaryError):
        CanaryDriver(store).run_target(httpx.MockTransport(respond))
    assert len([r for r in fake.requests if r.method == "POST"]) == 1
    assert "INTERNAL_PROMPT_SECRET" not in "".join(
        p.read_text() for p in store.path.glob("*.json")
    )


def test_live_driver_without_instrumented_client_fails_before_http(tmp_path):
    store = CanaryStore(
        tmp_path / "salesagent-preflight-canary" / "unwired", mode="live"
    )
    calls = []
    with pytest.raises(CanaryError):
        CanaryDriver(store).run_target(httpx.MockTransport(lambda r: calls.append(r)))
    assert calls == []


def test_unexpected_service_tier_retains_usage_but_marks_cost_unknown(store):
    provider = ProviderTransport(
        store,
        httpx.MockTransport(
            lambda _: httpx.Response(
                200, json=provider_envelope(model=TARGET_MODEL, service_tier="fast")
            )
        ),
        role="target",
    )
    with provider.logical("A1"):
        provider.handle_request(provider_request())
    record = events(store)[0]
    assert record["input_tokens"] == 1000 and record["estimated_usd"] is None
    assert store.accounting()["estimated_total_usd"] is None


def test_long_context_prices_and_invalid_usage_are_not_understated():
    usage = {
        "input_tokens": 300000,
        "output_tokens": 100,
        "total_tokens": 300100,
        "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 300000},
    }
    result = usage_metadata({"usage": usage}, role="target")
    assert Decimal(result["estimated_usd"]) == Decimal("1.5018")
    usage["total_tokens"] = 1
    assert usage_metadata({"usage": usage}, role="target")["estimated_usd"] is None


def test_provider_spend_limit_error_stops_before_sdk_retry(store):
    calls = []

    def reply(request):
        calls.append(request)
        return httpx.Response(
            429,
            json={
                "error": {
                    "code": "project_spend_limit_exceeded",
                    "message": "CREDENTIAL_SECRET",
                }
            },
        )

    provider = ProviderTransport(store, httpx.MockTransport(reply), role="target")
    with provider.logical("A1"):
        assert provider.handle_request(provider_request()).status_code == 429
        with pytest.raises(CanaryError):
            provider.handle_request(provider_request())
    assert len(calls) == 1
    assert events(store)[0]["error"] == "project_spend_limit_exceeded"
    assert "CREDENTIAL_SECRET" not in "".join(
        p.read_text() for p in store.path.glob("*.json")
    )


def test_debug_logging_is_rejected_without_changing_logger_configuration(store):
    calls = []
    logger = logging.getLogger("openai._base_client")
    original = logger.level
    logger.setLevel(logging.DEBUG)
    provider = ProviderTransport(
        store, httpx.MockTransport(lambda r: calls.append(r)), role="target"
    )
    try:
        with pytest.raises(CanaryError, match="debug logging"), provider.logical("A1"):
            pytest.fail("must not construct an SDK request")
        assert logger.level == logging.DEBUG
    finally:
        logger.setLevel(original)
    assert calls == []


@pytest.mark.parametrize("role", ["target", "judge"])
def test_missing_transport_cannot_create_a_default_client(store, role):
    with pytest.raises(CanaryError, match="explicit provider"):
        ProviderTransport(store, None, role=role)
    with pytest.raises(CanaryError, match="explicit target"):
        CanaryDriver(store).run_target(None)
