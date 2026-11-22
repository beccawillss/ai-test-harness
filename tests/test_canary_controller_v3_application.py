"""Mandatory, explicitly invoked pinned application QA; no model or network I/O.

Set CANARY_V3_APPLICATION_TESTS=1 in the existing application CPython 3.13
environment, with both source trees on PYTHONPATH. Enabled tests never skip.
"""

import copy
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

import httpx
import pytest
from test_canary_journal_v3 import receipt, retry_failure, tree_bytes

from harness.canary import controller_v3 as controller
from harness.canary import journal_v3 as journal
from harness.canary.runtime_v3 import V3, resolve_definition

if os.environ.get("CANARY_V3_APPLICATION_TESTS") != "1":
    pytest.skip(
        "Explicit pinned application suite; enable CANARY_V3_APPLICATION_TESTS=1",
        allow_module_level=True,
    )
if sys.version_info[:2] != (3, 13):
    raise RuntimeError("Mandatory application QA requires CPython 3.13")
_SPEC = importlib.util.find_spec("salesagent")
if _SPEC is None or _SPEC.origin is None:
    raise RuntimeError("Mandatory pinned application checkout is unavailable")
APPLICATION = Path(_SPEC.origin).resolve().parents[2]
HARNESS = Path(controller.__file__).resolve().parents[3]
TURNS = resolve_definition(V3).turns


class Script:
    """Only provider replies are scripted. Commerce/API/state are real."""

    def __init__(
        self, *, retry=False, unknown=False, wrong_state=False, bad_promotion=False
    ):
        self.retry = retry
        self.unknown = unknown
        self.wrong_state = wrong_state
        self.bad_promotion = bad_promotion
        self.requests = []
        self.before_response = None
        self.calls = {}

    def __call__(self, request):
        body = json.loads(request.content)
        assert (
            request.method == "POST"
            and str(request.url) == "https://api.openai.com/v1/responses"
        )
        assert request.headers["openai-project"] == controller._PROJECT
        assert request.headers["openai-organization"] == controller._ORGANIZATION
        assert request.headers["authorization"] == "Bearer " + controller._CREDENTIAL
        assert set(request.extensions["timeout"].values()) == {30}
        assert body["model"] == "gpt-5.6-terra"
        assert body["reasoning"] == {"effort": "low"}
        assert body["max_output_tokens"] == 2000
        assert body["store"] is True and body["parallel_tool_calls"] is False
        assert body["tool_choice"] == "auto"
        previous = body.get("previous_response_id")
        if previous:
            _, slot, step = previous.split("_")
            number = int(step) + 1
        else:
            slot = next(
                t.slot for t in TURNS if t.message == body["input"][-1]["content"]
            )
            number = 1
        retry = int(request.headers["x-stainless-retry-count"])
        self.requests.append((slot, number, retry, copy.deepcopy(body)))
        if self.before_response:
            self.before_response(slot, number, retry)
        if self.retry and slot == "A1" and number == 1 and retry < 2:
            return httpx.Response(
                500,
                json=retry_failure(known_zero_usage=not self.unknown),
                headers={"retry-after-ms": "1"},
            )
        steps = {
            "A1": [
                ("search_products", {"category": "accessory", "maximum_price": "60"}),
                ("get_product", {"product_id": "ACC-003"}),
                (
                    "check_inventory",
                    {"product_id": "ACC-003", "colour": "Moss", "size": "20L"},
                ),
            ],
            "A2": [
                ("get_product", {"product_id": "ACC-003"}),
                ("validate_discount", {"code": "WELCOME10"}),
            ],
            "B1": [],
            "B2": [
                ("search_products", {"category": "accessory", "maximum_price": "25"}),
                ("get_product", {"product_id": "ACC-001"}),
                (
                    "check_inventory",
                    {"product_id": "ACC-001", "colour": "Rust", "size": "One Size"},
                ),
            ],
        }[slot]
        if number <= len(steps):
            name, arguments = steps[number - 1]
            output = [
                {
                    "type": "function_call",
                    "id": f"fc_{slot}_{number}",
                    "call_id": f"call_{slot}_{number}",
                    "name": name,
                    "arguments": json.dumps(arguments),
                    "status": "completed",
                }
            ]
        else:
            updates = dict.fromkeys(
                (
                    "category",
                    "activity",
                    "weather",
                    "features",
                    "maximum_price",
                    "colour",
                    "size",
                    "season",
                    "priority",
                )
            )
            if slot in {"A1", "B2"}:
                for key, value in {
                    "maximum_price": "60" if slot == "A1" else "25",
                    "colour": "Moss" if slot == "A1" else "Rust",
                    "size": "20L" if slot == "A1" else "One Size",
                }.items():
                    updates[key] = {"operation": "set", "value": value}
            if self.wrong_state and slot == "A1":
                updates["colour"] = {"operation": "set", "value": "Black"}
            final = {
                "message": "You have not shared preferences yet. What would you like to shop for?"
                if slot == "B1"
                else "Here is the item, with its availability checked using the catalogue.",
                "nominated_product_ids": []
                if slot == "B1"
                else ["ACC-001" if slot == "B2" else "ACC-003"],
                "nominated_promotion_code": (
                    "MADEUP50" if self.bad_promotion else "WELCOME10"
                )
                if slot == "A2"
                else None,
                "constraint_updates": updates,
            }
            output = [
                {
                    "type": "message",
                    "id": f"msg_{slot}_{number}",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(final),
                            "annotations": [],
                        }
                    ],
                }
            ]
        self.calls[(slot, number)] = True
        return httpx.Response(
            200,
            headers={"x-request-id": f"req_{slot}_{number}"},
            json={
                "id": f"resp_{slot}_{number}",
                "object": "response",
                "created_at": 0,
                "model": "gpt-5.6-terra",
                "status": "completed",
                "output": output,
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 10,
                    "total_tokens": 110,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
            },
        )


@pytest.fixture(autouse=True)
def isolate_test_ownership(monkeypatch):
    # Fault tests deliberately poison admission; restore only the test namespace,
    # after checking that real resources did terminate. No production reset API.
    monkeypatch.setattr(controller, "_OWNER", threading.Lock())
    controller._NETWORK_VIOLATION.clear()
    yield
    controller._NETWORK_BLOCKED.clear()


def composition(tmp_path, script=None):
    script = script or Script()
    instance = controller.OfflineCanaryControllerV3(
        offline=True,
        harness_root=HARNESS,
        application_root=APPLICATION,
        source_receipt=receipt(),
        evidence_parent=tmp_path,
        provider_mock=httpx.MockTransport(script),
    )
    return instance, script


def records(report, kind):
    return [r["payload"] for r in report["records"] if r["kind"] == kind]


def assert_development(report):
    assert report["development_only"] is True
    assert report["source_verification"] == "pending_clean_committed_revision"
    assert report["source_authorised"] is False
    assert report["provider_evidence_authenticated"] is False
    assert report["authorises_live_execution"] is False
    assert report["human_review"] == "PENDING"
    assert report["billing"] == "unknown"


def test_genuine_four_turn_application_sessions_tools_prices_history_and_shutdown(
    tmp_path,
):
    c, script = composition(tmp_path)
    report = c._run_development_offline()
    assert report["controller_status"] == "completed", (
        report.get("controller_error"),
        report.get("driver_error"),
    )
    assert_development(report)
    assert report["completion_certified"] and report["accounting_reconciled"]
    assert report["mechanical_assessment"]["status"] == "PASS"
    assert report["shopper_posts"] == 4 and report["trace_reads"] == 8
    assert report["accounting"]["logical_calls"] == 12
    assert report["accounting"]["provider_attempts"] == 12
    assert report["accounting"]["unknown_attempts"] == 0
    assert report["accounting"]["incomplete_calls"] == 0
    chats = {r["slot"]: r["chat"] for r in records(report, "chat")}
    traces = {r["slot"]: r["trace"] for r in records(report, "trace")}
    assert chats["A1"]["session_id"] == chats["A2"]["session_id"]
    assert chats["B1"]["session_id"] == chats["B2"]["session_id"]
    assert chats["A1"]["session_id"] != chats["B1"]["session_id"]
    assert len({v["trace_id"] for v in chats.values()}) == 4
    state = c._resources.application.state
    a = state.session_repository.get_state(chats["A1"]["session_id"])
    b = state.session_repository.get_state(chats["B1"]["session_id"])
    assert [t.user_message for t in a.history] == [TURNS[0].message, TURNS[2].message]
    assert [t.user_message for t in b.history] == [TURNS[1].message, TURNS[3].message]
    assert (
        a.resolved_constraints.colour == "Moss" and a.resolved_constraints.size == "20L"
    )
    assert (
        b.resolved_constraints.colour == "Rust"
        and b.resolved_constraints.size == "One Size"
    )
    assert str(a.resolved_constraints.maximum_price) == "60"
    assert str(b.resolved_constraints.maximum_price) == "25"
    for slot, trace in traces.items():
        assert trace["turn_index"] == int(slot[1])
        assert state.trace_repository.get(trace["trace_id"]) is not None
        assert (
            trace["token_usage"]["total_tokens"]
            == {"A1": 440, "B1": 110, "A2": 330, "B2": 440}[slot]
        )
    assert chats["A1"]["recommendations"][0]["price"] == "55.00"
    assert chats["A2"]["pricing"]["final_price"] == "49.50"
    assert chats["B2"]["recommendations"][0]["price"] == "22.00"
    assert [t["tool_name"] for t in traces["A1"]["tool_calls"]] == [
        "search_products",
        "get_product",
        "check_inventory",
    ]
    assert [t["tool_name"] for t in traces["A2"]["tool_calls"]] == [
        "get_product",
        "validate_discount",
    ]
    assert traces["A1"]["tool_calls"][-1]["result"]["data"]["stock"] == 5
    assert traces["B2"]["tool_calls"][-1]["result"]["data"]["stock"] == 6
    first = {
        slot: body for slot, n, retry, body in script.requests if n == 1 and retry == 0
    }
    assert len(first["A1"]["input"]) == len(first["B1"]["input"]) == 2
    assert len(first["A2"]["input"]) == len(first["B2"]["input"]) == 4
    assert first["A2"]["input"][0]["content"] == TURNS[0].message
    assert first["B2"]["input"][0]["content"] == TURNS[1].message
    assert report["resources"]["cleanup_verified"]
    assert report["resources"]["owned_threads"] >= 2
    assert report["resources"]["surviving_owned_threads"] == 0
    assert report["resources"]["application_lifespan_exited"]
    assert report["resources"]["sdk_closed"] and report["resources"]["http_closed"]
    assert not controller._OWNER.locked()


@pytest.mark.parametrize("unknown", [False, True])
def test_real_sdk_retries_and_unknown_liability(tmp_path, unknown):
    c, script = composition(tmp_path, Script(retry=True, unknown=unknown))
    report = c._run_development_offline()
    assert_development(report)
    if unknown:
        # The next SDK retry enters the transport but its actual accounting
        # guard rejects dispatch as soon as the first unknown liability exists.
        assert [r[2] for r in script.requests] == [0]
        assert report["accounting"]["retryable_http_failures"] == 1
        assert report["controller_status"] == "stopped"
        assert report["accounting"]["unknown_attempts"] == 1
        assert not report["completion_certified"] and report["shopper_posts"] == 1
    else:
        assert [r[2] for r in script.requests[:3]] == [0, 1, 2]
        assert report["accounting"]["retryable_http_failures"] == 2
        assert report["controller_status"] == "completed"
        assert report["accounting"]["logical_calls"] == 12
        assert report["accounting"]["provider_attempts"] == 14
        assert report["accounting"]["unknown_attempts"] == 0


@pytest.mark.parametrize("failure", ["wrong_state", "bad_promotion"])
def test_trustworthy_behavioural_fail_advances_without_repair(tmp_path, failure):
    c, _ = composition(tmp_path, Script(**{failure: True}))
    report = c._run_development_offline()
    assert report["controller_status"] == "completed"
    assert report["mechanical_assessment"]["status"] == "FAIL"
    assert report["shopper_posts"] == 4
    assert report["operational_assessment"]["status"] == "PASS"
    traces = {r["slot"]: r["trace"] for r in records(report, "trace")}
    if failure == "wrong_state":
        assert traces["A1"]["resolved_constraints"]["colour"] == "Black"
        assert traces["A2"]["resolved_constraints"]["colour"] == "Black"
    else:
        assert traces["A2"]["pricing"] is None
        assert traces["A2"]["errors"][0]["code"] == "ungrounded_promotion_code"


@pytest.mark.parametrize(
    "stage",
    [
        "provider",
        "trace",
        "assessment",
        "shutdown",
        "finalization_admission",
        "finalization_publication",
    ],
)
def test_stop_at_genuine_application_and_finalization_boundaries(
    tmp_path, monkeypatch, stage
):
    c, script = composition(tmp_path)
    stopped = False

    def stop_once():
        nonlocal stopped
        if not stopped:
            stopped = True
            c.request_stop()

    if stage == "provider":
        script.before_response = lambda *_: stop_once()
    elif stage == "trace":
        original = controller._Resources.forward

        def forward(self, request):
            response = original(self, request)
            if request.method == "GET":
                stop_once()
            return response

        monkeypatch.setattr(controller._Resources, "forward", forward)
    elif stage == "assessment":
        original = journal.CanaryJournal.assess_turn

        def assess(self):
            stop_once()
            return original(self)

        monkeypatch.setattr(journal.CanaryJournal, "assess_turn", assess)
    elif stage == "shutdown":
        original = controller._Resources.close

        def close(self):
            stop_once()
            return original(self)

        monkeypatch.setattr(controller._Resources, "close", close)
    elif stage == "finalization_admission":
        original = journal.CanaryJournal.seal

        def seal(self):
            stop_once()
            return original(self)

        monkeypatch.setattr(journal.CanaryJournal, "seal", seal)
    else:
        original = journal._publish

        def publish(directory, name, value):
            if value.get("kind") == "completion":
                # A separate operator thread latches immediately, then waits for
                # PR #30's admitted finalization. Never synchronously reenter seal.
                thread = threading.Thread(target=c.request_stop)
                thread.start()
                assert c._stop.wait(3)
                c._test_stop_thread = thread
            return original(directory, name, value)

        monkeypatch.setattr(journal, "_publish", publish)
    report = c._run_development_offline()
    if stage == "finalization_publication":
        c._test_stop_thread.join(3)
        assert not c._test_stop_thread.is_alive()
        assert report["controller_status"] == "completed"
    else:
        assert report["controller_status"] == "stopped"
        assert not report["completion_certified"]
    assert report["resources"]["surviving_owned_threads"] == 0
    assert report["resources"]["sdk_closed"] and report["resources"]["http_closed"]
    assert_development(report)


@pytest.mark.parametrize("fault", ["trace", "session", "usage"])
def test_operational_evidence_corruption_stops_without_replacement(
    tmp_path, monkeypatch, fault
):
    c, _ = composition(tmp_path)
    original = controller._Resources.forward

    def forward(self, request):
        response = original(self, request)
        data = response.json()
        if fault == "trace" and request.method == "GET":
            return httpx.Response(404)
        if fault == "session" and request.method == "POST":
            data["session_id"] = "resp_invalid_session"
        if fault == "usage" and request.method == "GET":
            data["token_usage"] = {
                "input_tokens": 1,
                "output_tokens": 1,
                "total_tokens": 2,
            }
        return httpx.Response(200, json=data)

    monkeypatch.setattr(controller._Resources, "forward", forward)
    report = c._run_development_offline()
    assert report["controller_status"] == "stopped"
    assert report["shopper_posts"] == 1
    assert not report["completion_certified"]
    assert report["resources"]["cleanup_verified"]


def test_durable_evidence_is_private_copy_isolated_and_save_only(tmp_path):
    c, _ = composition(tmp_path)
    report = c._run_development_offline()
    registry = c._journal.registry
    before = tree_bytes(Path(registry.path))
    encoded = json.dumps(report)
    assert controller._CREDENTIAL not in encoded
    assert "instructions" not in encoded and "authorization" not in encoded.lower()
    report["records"].clear()
    report["accounting"]["logical_calls"] = 999
    saved = journal.inspect_run(registry, c._journal.run_id)
    assert saved["accounting"]["logical_calls"] == 12
    journal.recover_save_only(registry, c._journal.run_id, tmp_path / "saved")
    assert tree_bytes(Path(registry.path)) == before
    assert Path(registry.path).stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize("boundary", ["shopper", "dispatch", "retry", "result"])
def test_stop_before_new_admission_and_while_recording_returning_evidence(
    tmp_path, monkeypatch, boundary
):
    c, script = composition(tmp_path, Script(retry=boundary == "retry"))
    stopped = False

    def stop_once():
        nonlocal stopped
        if not stopped:
            stopped = True
            c.request_stop()

    if boundary == "shopper":
        original = controller.MockApplicationGatewayV3.post_chat

        def post(self, *args, **kwargs):
            stop_once()
            return original(self, *args, **kwargs)

        monkeypatch.setattr(controller.MockApplicationGatewayV3, "post_chat", post)
    elif boundary == "dispatch":
        original = c._attempt_guards

        def guards():
            result = original()
            stop_once()
            return result

        monkeypatch.setattr(c, "_attempt_guards", guards)
    elif boundary == "retry":
        from openai import _base_client

        monkeypatch.setattr(_base_client.time, "sleep", lambda _: stop_once())
    else:
        original = journal.CanaryJournal.observe_provider_attempt

        def observe(self, *args, **kwargs):
            stop_once()
            return original(self, *args, **kwargs)

        monkeypatch.setattr(journal.CanaryJournal, "observe_provider_attempt", observe)
    report = c._run_development_offline()
    assert report["controller_status"] == "stopped"
    assert not report["completion_certified"]
    assert len(script.requests) == (0 if boundary in {"shopper", "dispatch"} else 1)
    assert report["resources"]["surviving_owned_threads"] == 0
    if boundary == "result":
        assert len(records(report, "instrumented_result")) == 1
        assert report["accounting"]["unknown_attempts"] == 0


@pytest.mark.parametrize(
    "failure", ["lifespan", "sdk", "http", "provider", "worker_observation"]
)
def test_real_resource_cleanup_failure_never_seals_and_attempts_all_resources(
    tmp_path, monkeypatch, failure
):
    c, _ = composition(tmp_path)
    original = c._assemble

    def assemble():
        original()
        r = c._resources
        if failure == "lifespan":
            target, attribute = type(r.client), "__exit__"
        elif failure == "worker_observation":
            target, attribute = r, "observe_threads"
        else:
            target, attribute = getattr(r, failure), "close"
        old = getattr(target, attribute)

        def fail(*args, **kwargs):
            old(*args, **kwargs)
            raise RuntimeError("PRIVATE_SHUTDOWN_DIAGNOSTIC")

        monkeypatch.setattr(target, attribute, fail)

    monkeypatch.setattr(c, "_assemble", assemble)
    report = c._run_development_offline()
    assert report["controller_status"] == "stopped"
    assert report["controller_error"] == "cleanup_failed"
    assert not report["completion_certified"]
    assert report["resources"]["sdk_closed"] and report["resources"]["http_closed"]
    assert report["resources"]["surviving_owned_threads"] == 0
    assert controller._OWNER.locked()  # Production has no reset/restart API.
    assert "PRIVATE" not in json.dumps(report)


def test_actual_sdk_request_outside_bound_call_never_dispatches(tmp_path, monkeypatch):
    from openai import APIConnectionError

    c, script = composition(tmp_path)
    original = c._assemble

    def assemble():
        original()
        with pytest.raises(APIConnectionError):
            c._resources.sdk.responses.create(
                model="gpt-5.6-terra", input="Unbound request"
            )

    monkeypatch.setattr(c, "_assemble", assemble)
    report = c._run_development_offline()
    assert report["controller_status"] == "stopped"
    assert report["accounting"]["provider_attempts"] == 0
    assert not script.requests and not report["completion_certified"]
    assert report["resources"]["cleanup_verified"]


def test_source_change_after_initial_observation_stops_next_attempt(
    tmp_path, monkeypatch
):
    c, script = composition(tmp_path)
    changed = threading.Event()
    original = controller._development_digest
    monkeypatch.setattr(
        controller,
        "_development_digest",
        lambda root: "0" * 64 if changed.is_set() else original(root),
    )
    script.before_response = lambda *_: changed.set()
    report = c._run_development_offline()
    assert report["controller_status"] == "stopped"
    assert len(script.requests) == 1
    assert not report["completion_certified"]
    assert report["resources"]["cleanup_verified"]


def test_single_owned_sdk_and_unused_default_application(tmp_path, monkeypatch):
    import openai

    c, _ = composition(tmp_path)
    count = []
    original = openai.OpenAI

    def construct(*args, **kwargs):
        count.append(True)
        assert kwargs["api_key"] == controller._CREDENTIAL
        assert kwargs["http_client"]._transport is c._resources.provider
        return original(*args, **kwargs)

    monkeypatch.setattr(openai, "OpenAI", construct)
    report = c._run_development_offline()
    assert report["controller_status"] == "completed"
    assert count == [True]
    default = controller._IMPORTED_MAIN.app.state
    assert (
        not default.session_repository._states and not default.trace_repository._traces
    )
    assert default.chat_service._orchestrator._responses_client._client is None


def test_timeout_preserves_unknown_attempt_and_stops_sdk_reentry(tmp_path):
    c, script = composition(tmp_path)

    def timeout(*_):
        raise httpx.ReadTimeout("PRIVATE_TIMEOUT_PAYLOAD")

    script.before_response = timeout
    report = c._run_development_offline()
    assert report["controller_status"] == "stopped"
    assert report["accounting"]["unknown_attempts"] == 1
    assert report["accounting"]["provider_attempts"] == 1
    assert len(script.requests) == 1 and report["shopper_posts"] == 1
    assert "PRIVATE" not in json.dumps(report)


def test_stop_immediately_closes_dispatch_while_journal_mutex_is_blocked(tmp_path):
    c, script = composition(tmp_path)
    locked, release, returned = threading.Event(), threading.Event(), threading.Event()
    threads = []

    def block_journal():
        with c._journal._mutex:
            locked.set()
            assert release.wait(3)

    def stop():
        c.request_stop()
        returned.set()

    def interrupt(*_):
        holder = threading.Thread(target=block_journal)
        holder.start()
        threads.append(holder)
        assert locked.wait(3)
        operator = threading.Thread(target=stop)
        operator.start()
        threads.append(operator)
        try:
            assert c._stop.wait(3)
            assert c._resources.provider._halt.wait(3)
            assert c._journal._provider_gate.wait(3)
            assert not returned.is_set()
        finally:
            release.set()

    script.before_response = interrupt
    try:
        report = c._run_development_offline()
    finally:
        release.set()
        for thread in threads:
            thread.join(3)
    assert not any(t.is_alive() for t in threads)
    assert returned.is_set() and report["controller_status"] == "stopped"
    assert len(script.requests) == 1 and not report["completion_certified"]


@pytest.mark.parametrize("phase", ["instrumented_dispatch", "instrumented_result"])
def test_controller_process_loss_preserves_prefix_without_replay(tmp_path, phase):
    program = """
import os, sys
from pathlib import Path
from test_canary_controller_v3_application import composition
from harness.canary import journal_v3 as journal
c, _ = composition(Path(sys.argv[1]))
original = journal._publish
def publish(directory, name, value):
    original(directory, name, value)
    if value.get("kind") == sys.argv[2]:
        os._exit(23)
journal._publish = publish
c._run_development_offline()
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", program, str(tmp_path), phase],
        cwd=HARNESS,
        env={
            "PATH": os.defpath,
            "PYTHONDONTWRITEBYTECODE": "1",
            "CANARY_V3_APPLICATION_TESTS": "1",
            "PYTHONPATH": f"{HARNESS / 'src'}:{HARNESS / 'tests'}:{APPLICATION / 'src'}",
        },
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 23, result.stderr.decode()
    registry = journal.load_registry(next(tmp_path.glob("offline-v3-*")))
    run_id = next((Path(registry.path) / "runs").iterdir()).name
    report = journal.inspect_run(registry, run_id)
    assert report["status"] == "operationally_uncertain"
    assert not report["completion_certified"]
    assert report["accounting"]["unknown_attempts"] == (
        1 if phase == "instrumented_dispatch" else 0
    )
    assert report["accounting"]["incomplete_calls"] == 1
    before = tree_bytes(Path(registry.path))
    journal.recover_save_only(registry, run_id, tmp_path / "saved")
    assert tree_bytes(Path(registry.path)) == before


def test_malformed_model_response_is_operational_error_with_known_usage(tmp_path):
    c, script = composition(tmp_path)

    def malformed(request):
        response = script(request)
        data = response.json()
        data["output"] = []
        return httpx.Response(200, json=data)

    c._mock.handler = malformed
    report = c._run_development_offline()
    assert report["controller_status"] == "stopped"
    assert report["shopper_posts"] == 1 and len(script.requests) == 1
    assert report["accounting"]["unknown_attempts"] == 0
    assert not report["completion_certified"]


def test_audit_rejects_real_socket_and_caught_violation_still_stops_run(tmp_path):
    c, script = composition(tmp_path)

    def attempt_socket(*_):
        with pytest.raises(controller.ControllerError, match="guard_failed"):
            socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    script.before_response = attempt_socket
    report = c._run_development_offline()
    assert report["controller_status"] == "stopped"
    assert len(script.requests) == 1 and not report["completion_certified"]
    assert controller._NETWORK_VIOLATION.is_set()


def test_actual_usage_cost_crossing_pause_stops_without_replacement(tmp_path):
    c, script = composition(tmp_path)

    def expensive(request):
        data = script(request).json()
        data["usage"] = {
            "input_tokens": 10_000_000,
            "output_tokens": 0,
            "total_tokens": 10_000_000,
        }
        return httpx.Response(200, json=data)

    c._mock.handler = expensive
    report = c._run_development_offline()
    assert report["controller_status"] == "stopped"
    assert report["accounting"]["unknown_attempts"] == 0
    assert float(report["accounting"]["estimated_subtotal_usd"]) >= 5
    assert len(script.requests) == 1 and not report["completion_certified"]


def test_each_invocation_owns_fresh_private_identity_and_application_state(tmp_path):
    a, _ = composition(tmp_path)
    first = a._run_development_offline()
    b, _ = composition(tmp_path)
    second = b._run_development_offline()
    assert first["controller_status"] == second["controller_status"] == "completed"
    assert first["run_id"] != second["run_id"]
    assert first["registry_path"] != second["registry_path"]
    assert (
        a._resources.application.state.session_repository
        is not b._resources.application.state.session_repository
    )
    first_sessions = {r["chat"]["session_id"] for r in records(first, "chat")}
    second_sessions = {r["chat"]["session_id"] for r in records(second, "chat")}
    assert first_sessions.isdisjoint(second_sessions)


@pytest.mark.parametrize("after_ack", [False, True])
def test_finalization_publication_failure_is_not_successful_invocation(
    tmp_path, monkeypatch, after_ack
):
    c, _ = composition(tmp_path)
    original = journal._publish

    def publish(directory, name, value):
        if not after_ack and value.get("kind") == "completion":
            raise OSError("PRIVATE_FINALIZATION_ERROR")
        original(directory, name, value)
        if after_ack and value.get("kind") == "completion_ack":
            raise OSError("PRIVATE_FINALIZATION_ERROR")

    monkeypatch.setattr(journal, "_publish", publish)
    report = c._run_development_offline()
    assert report["controller_status"] == report["driver_status"] == "stopped"
    assert (
        report["completion_certified"] == after_ack
    )  # Preserve historical visible-ack replay.
    assert report["resources"]["cleanup_verified"]
    assert "PRIVATE" not in json.dumps(report)


@pytest.mark.parametrize("field", ["completion_certified", "accounting_reconciled"])
def test_driver_return_without_final_evidence_proof_cannot_claim_controller_success(
    tmp_path, monkeypatch, field
):
    c, _ = composition(tmp_path)
    original = controller.OrderedCanaryDriverV3.run

    def run(self, gateway):
        report = original(self, gateway)
        report[field] = False  # Simulate a failed final inspection observation.
        return report

    monkeypatch.setattr(controller.OrderedCanaryDriverV3, "run", run)
    report = c._run_development_offline()
    assert report["driver_status"] == "completed"
    assert report["controller_status"] == "stopped"
    assert report["controller_error"] == "evidence_unavailable"
