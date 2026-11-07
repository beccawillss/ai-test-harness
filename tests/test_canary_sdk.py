"""Optional installed-SDK/application comparison; all HTTP is scripted in memory."""

import json
from hashlib import sha256

import httpx
import pytest

openai = pytest.importorskip("openai")
pytest.importorskip("salesagent")

from fastapi.testclient import TestClient
from salesagent.agent.final_output import AgentFinalOutput, ConstraintUpdates
from salesagent.agent.responses_client import OpenAIResponsesClient
from salesagent.config import Settings

from harness.canary.driver import CanaryDriver
from harness.canary.inputs import TARGET_MODEL
from harness.canary.recording import (
    BoundedResponsesClient,
    CanaryError,
    CanaryStore,
    ProviderTransport,
)


class ScriptedProvider:
    def __init__(self):
        self.requests = []
        self.turn = -1
        self.step = 0

    def __call__(self, request):
        self.requests.append(request)
        body = json.loads(request.content)
        if body.get("previous_response_id") is None:
            self.turn += 1
            self.step = 0
        pid = "ACC-001" if self.turn == 3 else "ACC-003"
        colour, size = ("Rust", "One Size") if self.turn == 3 else ("Moss", "20L")
        scripts = [
            [
                ("search_products", {}),
                ("get_product", {"product_id": pid}),
                (
                    "check_inventory",
                    {"product_id": pid, "colour": colour, "size": size},
                ),
            ],
            [],
            [
                ("get_product", {"product_id": pid}),
                ("validate_discount", {"code": "WELCOME10"}),
            ],
            [
                ("search_products", {}),
                ("get_product", {"product_id": pid}),
                (
                    "check_inventory",
                    {"product_id": pid, "colour": colour, "size": size},
                ),
            ],
        ]
        script = scripts[self.turn]
        if self.step < len(script):
            name, args = script[self.step]
            output = [
                {
                    "type": "function_call",
                    "id": f"fc_{len(self.requests)}",
                    "call_id": f"call_{len(self.requests)}",
                    "name": name,
                    "arguments": json.dumps(args),
                    "status": "completed",
                }
            ]
        else:
            updates = ConstraintUpdates.retain_all().model_dump(mode="json")
            if self.turn in (0, 3):
                for field, value in (
                    ("category", "accessory"),
                    ("colour", colour),
                    ("size", size),
                    ("maximum_price", "25" if self.turn == 3 else "60"),
                ):
                    updates[field] = {"operation": "set", "value": value}
            final = AgentFinalOutput.model_validate(
                {
                    "message": "Synthetic public response.",
                    "nominated_product_ids": [] if self.turn == 1 else [pid],
                    "nominated_promotion_code": "WELCOME10" if self.turn == 2 else None,
                    "constraint_updates": updates,
                }
            )
            output = [
                {
                    "type": "message",
                    "id": f"msg_{len(self.requests)}",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": final.model_dump_json(),
                            "annotations": [],
                        }
                    ],
                }
            ]
        self.step += 1
        return httpx.Response(
            200,
            headers={"x-request-id": f"req_{len(self.requests)}"},
            json={
                "id": f"resp_{len(self.requests)}",
                "object": "response",
                "created_at": 0,
                "model": TARGET_MODEL,
                "status": "completed",
                "output": output,
                "usage": {
                    "input_tokens": 200,
                    "output_tokens": 50,
                    "total_tokens": 250,
                    "input_tokens_details": {
                        "cached_tokens": 0,
                        "cache_write_tokens": 200,
                    },
                    "output_tokens_details": {"reasoning_tokens": 20},
                },
            },
        )


def _sdk(transport):
    return openai.OpenAI(
        api_key="offline-not-a-credential",
        max_retries=2,
        timeout=30,
        http_client=httpx.Client(
            transport=transport, trust_env=False, follow_redirects=False
        ),
    )


def test_installed_sdk_application_instrumentation_preserves_bytes_and_semantics(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from salesagent.main import create_app

    observed = []
    for instrumented in (False, True):
        script = ScriptedProvider()
        store = CanaryStore(
            tmp_path / "salesagent-preflight-canary" / str(instrumented)
        )
        transport = httpx.MockTransport(script)
        provider = (
            ProviderTransport(store, transport, role="target")
            if instrumented
            else transport
        )
        sdk = _sdk(provider)
        delegate = OpenAIResponsesClient(
            api_key=None, timeout_seconds=30, max_retries=2, sdk_client=sdk
        )
        client = (
            BoundedResponsesClient(delegate, provider) if instrumented else delegate
        )
        app = create_app(Settings(openai_api_key=None), responses_client=client)
        with TestClient(app) as local:

            def handle(request):
                body = json.loads(request.content) if request.method == "POST" else None
                response = local.request(request.method, request.url.path, json=body)
                return httpx.Response(
                    response.status_code,
                    content=response.content,
                    headers={"content-type": "application/json"},
                )

            normalized = CanaryDriver(store).run_target(httpx.MockTransport(handle))
        assert sdk.max_retries == 2
        public = {}
        for name, response in normalized.items():
            value = response.model_dump(mode="json")
            value.pop("latency_ms")
            value["metadata"].pop("trace_ids")
            for turn in value["structured"]["turns"]:
                for key in ("trace_id", "latency_ms"):
                    turn["metadata"].pop(key)
                for tool in turn["metadata"]["tools"]:
                    tool.pop("duration_ms")
            public[name] = value
        # A failed comparison must not dump developer instructions into test logs.
        observed.append(
            ([sha256(r.content).hexdigest() for r in script.requests], public)
        )
        assert len(script.requests) == 12
        assert all(r.extensions["timeout"]["read"] == 30 for r in script.requests)
        if instrumented:
            assert store.accounting()["attempts"] == 12
            assert store.accounting()["unknown_attempts"] == 0
            metadata = [
                json.loads(p.read_text()) for p in store.path.glob("event-*.json")
            ]
            counts = {
                slot: sum(
                    v["kind"] == "provider_attempt" and v["slot"] == slot
                    for v in metadata
                )
                for slot in ("A1", "B1", "A2", "B2")
            }
            assert counts == {"A1": 4, "B1": 1, "A2": 3, "B2": 4}
            for slot, count in counts.items():
                trace = json.loads((store.path / f"trace-{slot}.json").read_text())
                assert trace["token_usage"]["input_tokens"] == count * 200
                assert trace["token_usage"]["output_tokens"] == count * 50
        sdk.close()
    assert observed[0] == observed[1]


def test_installed_sdk_retry_policy_is_unchanged_and_attempts_are_recorded(tmp_path):
    store = CanaryStore(tmp_path / "salesagent-preflight-canary" / "retry")
    seen = []
    reply = ScriptedProvider()

    def scripted(request):
        seen.append(request)
        if len(seen) < 3:
            return httpx.Response(
                500,
                headers={"retry-after": "0.001"},
                json={"error": {"message": "fake private body"}},
            )
        return reply(request)

    provider = ProviderTransport(store, httpx.MockTransport(scripted), role="target")
    sdk = _sdk(provider)
    with provider.logical("A1"):
        sdk.responses.create(
            model=TARGET_MODEL, input="synthetic", max_output_tokens=2000
        )
    assert sdk.max_retries == 2
    assert len(seen) == 3
    assert len({r.content for r in seen}) == 1
    assert [r.headers["x-stainless-retry-count"] for r in seen] == ["0", "1", "2"]
    assert store.accounting()["attempts"] == 3
    assert store.accounting()["unknown_attempts"] == 2
    with pytest.raises(CanaryError), provider.logical("A1", 2):
        pytest.fail("unknown billing must pause further logical calls")
    sdk.close()


def test_installed_sdk_ambiguous_transport_failure_has_no_replacement_dispatch(
    tmp_path,
):
    store = CanaryStore(tmp_path / "salesagent-preflight-canary" / "timeout")
    calls = []

    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout("private exception")

    provider = ProviderTransport(store, httpx.MockTransport(timeout), role="target")
    sdk = _sdk(provider)
    with pytest.raises(CanaryError), provider.logical("A1"):
        sdk.responses.create(
            model=TARGET_MODEL, input="synthetic", max_output_tokens=2000
        )
    assert sdk.max_retries == 2
    assert (
        len(calls) == 1
    )  # SDK retries remain configured; stopped transport rejects them.
    assert store.accounting()["unknown_attempts"] == 1
    sdk.close()
