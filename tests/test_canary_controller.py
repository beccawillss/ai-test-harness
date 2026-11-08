"""Optional installed-runtime tests. Provider always synthetic; external sockets blocked."""

import json
import socket
import subprocess
import threading
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import httpx
import pytest

pytest.importorskip("openai")
salesagent = pytest.importorskip("salesagent")
pytest.importorskip("uvicorn")

from test_canary_sdk import ScriptedProvider, _sdk

from harness.canary.controller import (
    DATASET_HASH,
    HARNESS_REVISION,
    LiveReadiness,
    LoopbackTransport,
    TargetCanaryController,
    verify_runtime,
)
from harness.canary.driver import CanaryDriver
from harness.canary.human import request_operator_stop
from harness.canary.recording import CanaryError, CanaryStore

HARNESS = Path(__file__).resolve().parents[1]
APPLICATION = Path(salesagent.__file__).resolve().parents[2]
CONNECT = socket.socket.connect
CONNECT_EX = socket.socket.connect_ex
GETADDRINFO = socket.getaddrinfo
CREATE_CONNECTION = socket.create_connection


@pytest.fixture
def local_sockets_only(monkeypatch):
    """Narrow the default no-network fixture to literal loopback only."""

    def check(address):
        if not isinstance(address, tuple) or address[0] != "127.0.0.1":
            raise AssertionError(
                "External network is forbidden in synthetic lifecycle tests"
            )

    def connect(sock, address):
        check(address)
        return CONNECT(sock, address)

    def connect_ex(sock, address):
        check(address)
        return CONNECT_EX(sock, address)

    def getaddrinfo(host, port, *args, **kwargs):
        check((host, port))
        return GETADDRINFO(host, port, *args, **kwargs)

    def create_connection(address, *args, **kwargs):
        check(address)
        return CREATE_CONNECTION(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(socket, "create_connection", create_connection)


@pytest.fixture
def store(tmp_path):
    return CanaryStore(tmp_path / "salesagent-preflight-canary" / "lifecycle")


def controller(store, script=None, **kwargs):
    return TargetCanaryController(
        store,
        harness_root=HARNESS,
        application_root=APPLICATION,
        provider_transport=httpx.MockTransport(script or ScriptedProvider()),
        **kwargs,
    )


def baseline_request_hashes(directory):
    from fastapi.testclient import TestClient
    from salesagent.agent.responses_client import OpenAIResponsesClient
    from salesagent.config import Settings
    from salesagent.main import create_app

    script = ScriptedProvider()
    sdk = _sdk(httpx.MockTransport(script))
    try:
        app = create_app(
            Settings(openai_api_key=None),
            responses_client=OpenAIResponsesClient(
                api_key=None, timeout_seconds=30, max_retries=2, sdk_client=sdk
            ),
        )
        with TestClient(app) as client:

            def handle(request):
                reply = client.request(
                    request.method,
                    request.url.path,
                    content=request.content,
                    headers={"content-type": "application/json"},
                )
                return httpx.Response(
                    reply.status_code,
                    content=reply.content,
                    headers={"content-type": "application/json"},
                )

            CanaryDriver(CanaryStore(directory)).run_target(httpx.MockTransport(handle))
    finally:
        sdk.close()
    return [sha256(request.content).hexdigest() for request in script.requests]


def test_runtime_pins_dataset_fixtures_and_imported_lock_versions():
    result = verify_runtime(HARNESS, APPLICATION)
    assert result["harness_base_revision"] == HARNESS_REVISION
    assert (
        result["harness_revision"]
        == subprocess.check_output(
            ["git", "-C", str(HARNESS), "rev-parse", "HEAD"], text=True
        ).strip()
    )
    assert result["dataset_fingerprint"] == DATASET_HASH
    assert result["dataset_cases"] == 50
    assert result["packages"]["openai"] == "3.3.1"
    assert result["live_authority"] is False


def test_full_worker_lifecycle_uses_synthetic_provider_only(
    store, local_sockets_only, monkeypatch
):
    observed = []
    original = LoopbackTransport.handle_request

    def observe(self, request):
        observed.append(
            (
                request.method,
                request.url.path,
                json.loads(request.content) if request.method == "POST" else None,
            )
        )
        return original(self, request)

    monkeypatch.setattr(LoopbackTransport, "handle_request", observe)
    script = ScriptedProvider()
    worker = controller(store, script)
    with worker:
        assert worker.listener.getsockname()[0] == "127.0.0.1"
        assert worker.server.config.workers == 1 and not worker.server.config.reload
        result = worker.run_target()
        assert set(result) == {"A", "B"}
        assert worker.sdk.max_retries == 2
        assert worker.sdk.timeout == 30
        with pytest.raises(AssertionError):
            socket.create_connection(("api.openai.com", 443))
    assert not worker.thread.is_alive()
    assert worker.sdk is None
    assert len(script.requests) == 12
    assert all(
        r.headers["openai-project"] == "offline-project"
        and r.headers["openai-organization"] == "offline-organization"
        for r in script.requests
    )
    # Compare hashes only, so a mismatch never prints developer instructions.
    assert [
        sha256(request.content).hexdigest() for request in script.requests
    ] == baseline_request_hashes(store.path.with_name("uninstrumented-baseline"))
    assert [method for method, _, _ in observed].count("POST") == 4
    assert [method for method, _, _ in observed].count("GET") == 10
    posts = [body for method, _, body in observed if method == "POST"]
    assert set(posts[0]) == set(posts[1]) == {"message"}
    assert posts[2]["session_id"] != posts[3]["session_id"]
    assert all(
        request.extensions["timeout"]["read"] == 30 for request in script.requests
    )
    summary = store.accounting()
    assert summary["attempts"] == 12 and summary["unknown_attempts"] == 0
    assert summary["estimated_total_usd"] == "0.0132"
    shutdown = json.loads((store.path / "worker-shutdown.json").read_text())
    assert shutdown["worker_stopped"] and shutdown["sdk_closed"]
    assert shutdown["accounting"] == summary
    assert not list(store.path.glob("*judge*"))
    with pytest.raises(CanaryError):
        worker.__enter__()
    with pytest.raises(CanaryError):
        controller(store)


def test_startup_alone_never_dispatches(store, local_sockets_only):
    script = ScriptedProvider()
    worker = controller(store, script)
    with worker:
        assert worker.server.started
    assert not script.requests
    assert store.accounting()["attempts"] == 0


@pytest.mark.parametrize(
    "fault", ["timeout", "incomplete", "unknown_usage", "pause", "stop"]
)
def test_provider_faults_and_operator_controls_stop_without_replacement(
    store, local_sockets_only, fault
):
    script = ScriptedProvider()
    calls = []

    def respond(request):
        calls.append(request)
        if fault == "timeout":
            raise httpx.ReadTimeout("sensitive diagnostic must not be recorded")
        response = script(request)
        body = response.json()
        if fault == "incomplete":
            body["status"] = "incomplete"
        if fault == "unknown_usage":
            body.pop("usage")
        if fault in {"pause", "stop"}:
            request_operator_stop(store, pause=fault == "pause")
        return httpx.Response(200, json=body)

    worker = controller(store, respond)
    with worker, pytest.raises(CanaryError):
        worker.run_target()
    assert len(calls) == 1
    assert store.stopped and not worker.thread.is_alive()
    assert store.accounting()["attempts"] == 1
    assert (store.path / "reserved-target-A1-1.json").exists()
    assert not (store.path / "reserved-chat-B1.json").exists()
    if fault in {"timeout", "unknown_usage"}:
        assert store.accounting()["estimated_total_usd"] is None
    assert "sensitive diagnostic" not in "".join(
        p.read_text() for p in store.path.glob("*.json")
    )


def test_interruption_closes_worker_without_target_dispatch(store, local_sockets_only):
    script = ScriptedProvider()
    worker = controller(store, script)
    with pytest.raises(KeyboardInterrupt), worker:
        raise KeyboardInterrupt
    assert store.stopped and not worker.thread.is_alive()
    assert not script.requests


def test_startup_bind_failure_closes_sdk(store, monkeypatch):
    worker = controller(store)

    def fail(*args, **kwargs):
        raise OSError("private diagnostic")

    monkeypatch.setattr(socket.socket, "bind", fail)
    with pytest.raises(CanaryError):
        worker.__enter__()
    assert worker.sdk is None and store.stopped
    assert store.accounting()["attempts"] == 0


def test_startup_recording_failure_shuts_down_worker(
    store, local_sockets_only, monkeypatch
):
    worker = controller(store)
    original = store.write

    def fail(name, value):
        if name == "worker-started":
            raise CanaryError("scripted recording failure")
        original(name, value)

    monkeypatch.setattr(store, "write", fail)
    with pytest.raises(CanaryError):
        worker.__enter__()
    assert worker.sdk is None and not worker.thread.is_alive()
    assert store.stopped and store.accounting()["attempts"] == 0


def test_failed_stop_record_cannot_prevent_shutdown(
    store, local_sockets_only, monkeypatch
):
    worker = controller(store)
    original = store.write

    def fail(name, value):
        if name in {"worker-started", "stopped"}:
            raise CanaryError("scripted disk failure")
        original(name, value)

    monkeypatch.setattr(store, "write", fail)
    with pytest.raises(CanaryError):
        worker.__enter__()
    assert worker.sdk is None and not worker.thread.is_alive()
    assert store.stopped and store.accounting()["attempts"] == 0


def test_operator_stop_during_inflight_call_retains_usage_and_blocks_next_call(
    store, local_sockets_only
):
    dispatched, release = threading.Event(), threading.Event()
    script = ScriptedProvider()
    errors = []

    def respond(request):
        dispatched.set()
        assert release.wait(3)
        return script(request)

    worker = controller(store, respond)

    def invoke():
        try:
            worker.run_target()
        except CanaryError:
            errors.append("stopped")

    with worker:
        caller = threading.Thread(target=invoke)
        caller.start()
        try:
            assert dispatched.wait(3)
            request_operator_stop(store)
        finally:
            release.set()
            caller.join(5)
        assert not caller.is_alive()
    assert errors == ["stopped"] and len(script.requests) == 1
    assert store.accounting()["unknown_attempts"] == 0
    assert store.accounting()["attempts"] == 1
    assert not worker.thread.is_alive()


def test_loopback_transport_rejects_external_or_wrong_port_before_io(
    store, local_sockets_only
):
    worker = controller(store)
    with worker, LoopbackTransport(worker) as transport:
        for url in (
            "https://api.openai.com/v1/responses",
            f"http://localhost:{worker.port}/health",
            f"http://127.0.0.1:{worker.port + 1}/health",
        ):
            with pytest.raises(CanaryError):
                transport.handle_request(httpx.Request("GET", url))


def test_runtime_rejects_ambient_settings_without_showing_values(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "do-not-read-or-log")
    with pytest.raises(CanaryError) as error:
        verify_runtime(HARNESS, APPLICATION)
    assert "do-not-read-or-log" not in str(error.value)


def test_runtime_rejects_wrong_checkout_before_constructing_clients(store, tmp_path):
    with pytest.raises(CanaryError):
        TargetCanaryController(
            store,
            harness_root=tmp_path,
            application_root=APPLICATION,
            provider_transport=httpx.MockTransport(
                lambda _: pytest.fail("no dispatch")
            ),
        )
    assert store.accounting()["attempts"] == 0


def test_live_startup_is_blocked_without_separate_authority(tmp_path):
    store = CanaryStore(
        tmp_path / "salesagent-preflight-canary" / "unapproved", mode="live"
    )
    with pytest.raises(CanaryError):
        controller(store)
    assert not (store.path / "reserved-controller.json").exists()


def test_live_attestation_requires_all_fresh_external_checks():
    # Validation only. No credential or live controller is constructed.
    now = datetime.now(UTC)
    readiness = LiveReadiness(
        "synthetic-test-only",
        "proj_fake",
        "org_fake",
        now.isoformat(),
        "a" * 64,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
    )
    readiness.verify()
    for field in (
        "dedicated_project",
        "credential_project_verified",
        "enforced_limit_10_usd_verified",
        "alerts_verified",
        "target_model_available",
        "current_prices_match_c1",
        "private_storage_verified",
    ):
        with pytest.raises(CanaryError):
            replace(readiness, **{field: False}).verify()
    with pytest.raises(CanaryError):
        replace(readiness, checked_at=(now - timedelta(hours=2)).isoformat()).verify()
    with pytest.raises(CanaryError):
        replace(readiness, checked_at=(now + timedelta(hours=2)).isoformat()).verify()


def test_offline_controller_rejects_network_transport_and_real_credential(store):
    with pytest.raises(CanaryError):
        controller(store, api_key="not-the-offline-placeholder")
    with httpx.HTTPTransport() as transport, pytest.raises(CanaryError):
        TargetCanaryController(
            store,
            harness_root=HARNESS,
            application_root=APPLICATION,
            provider_transport=transport,
        )
    assert store.accounting()["attempts"] == 0
