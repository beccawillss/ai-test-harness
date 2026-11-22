"""Offline controller contracts without Sales Agent, SDK or external checkout."""

import json
import logging
import socket
import threading
import traceback
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from test_canary_journal_v3 import make as make_journal
from test_canary_journal_v3 import receipt, tree_bytes

from harness.canary import controller_v3 as controller
from harness.canary import runtime_v3 as source


@pytest.fixture(autouse=True)
def isolated_ownership(monkeypatch):
    monkeypatch.setattr(controller, "_OWNER", threading.Lock())
    controller._NETWORK_VIOLATION.clear()
    yield
    controller._NETWORK_BLOCKED.clear()


def make(tmp_path, **changes):
    settings = {
        "offline": True,
        "harness_root": Path(controller.__file__).resolve().parents[3],
        "application_root": tmp_path / "absent-application",
        "source_receipt": receipt(),
        "evidence_parent": tmp_path,
        "provider_mock": httpx.MockTransport(
            lambda _: pytest.fail("Unexpected forwarding")
        ),
    }
    settings.update(changes)
    return controller.OfflineCanaryControllerV3(**settings)


@pytest.mark.parametrize("offline", [False, None, 1, "offline"])
def test_explicit_offline_only_construction(tmp_path, offline):
    with pytest.raises(
        controller.ControllerError, match="^offline_configuration_required$"
    ):
        make(tmp_path, offline=offline)


def test_no_subclass_or_network_transport_can_enter(tmp_path):
    class NotExact(httpx.MockTransport):
        pass

    with pytest.raises(
        controller.ControllerError, match="offline_configuration_required"
    ):
        make(tmp_path, provider_mock=NotExact(lambda _: httpx.Response(200)))
    with pytest.raises(
        controller.ControllerError, match="offline_configuration_required"
    ):
        make(tmp_path, provider_mock=object())


def test_c1_cannot_be_selected(tmp_path):
    wrong = receipt().model_copy(update={"binding": source.resolve_definition()})
    with pytest.raises(
        controller.ControllerError, match="offline_configuration_required"
    ):
        make(tmp_path, source_receipt=wrong)


def test_stop_before_construction_is_permanent_and_single_use(tmp_path, monkeypatch):
    event = threading.Event()
    event.set()
    c = make(tmp_path, stop_event=event)
    event.clear()  # The caller cannot reopen the controller's permanent latch.
    closed = []
    monkeypatch.setattr(c._mock, "close", lambda: closed.append(True))
    with pytest.raises(controller.ControllerError, match="controller_stopped"):
        c.run()
    with pytest.raises(controller.ControllerError, match="controller_reused"):
        c.run()
    assert closed == [True] and not list(tmp_path.iterdir())


def test_public_source_gate_is_unchanged_and_fail_closed(tmp_path, monkeypatch):
    c = make(tmp_path)
    called = []
    actual = source.verify_source

    def verify(*args, **kwargs):
        called.append((args, kwargs))
        return actual(*args, **kwargs)

    monkeypatch.setattr(source, "verify_source", verify)
    monkeypatch.setattr(
        c, "_assemble", lambda: pytest.fail("Application before source admission")
    )
    with pytest.raises(
        controller.ControllerError, match="^source_verification_failed$"
    ) as caught:
        c.run()
    assert len(called) == 1 and c._journal is None
    assert not controller._OWNER.locked()
    assert "PRIVATE" not in "".join(traceback.format_exception(caught.value))


def test_source_verification_stop_and_concurrent_reentry(tmp_path, monkeypatch):
    c = make(tmp_path)
    entered, release = threading.Event(), threading.Event()
    errors = []

    def verify(*_, **__):
        entered.set()
        assert release.wait(3)
        raise source.SourceError("PRIVATE_SOURCE_ERROR")

    monkeypatch.setattr(source, "verify_source", verify)

    def run():
        try:
            c.run()
        except controller.ControllerError as error:
            errors.append(str(error))

    worker = threading.Thread(target=run)
    worker.start()
    try:
        assert entered.wait(3)
        with pytest.raises(controller.ControllerError, match="controller_reused"):
            c.run()
        assert c._stop.is_set()  # Reentry closes admission while verifier is blocked.
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive() and errors == ["source_verification_failed"]
    assert not list(tmp_path.iterdir())


def test_exclusive_application_ownership_precedes_any_construction(
    tmp_path, monkeypatch
):
    c = make(tmp_path)
    controller._OWNER.acquire()
    monkeypatch.setattr(
        source,
        "verify_source",
        lambda *_a, **_k: pytest.fail("Ownership must precede source work"),
    )
    try:
        with pytest.raises(controller.ControllerError, match="application_owned"):
            c.run()
    finally:
        controller._OWNER.release()
    assert not list(tmp_path.iterdir())


def test_stop_during_ownership_acquisition(tmp_path, monkeypatch):
    c = make(tmp_path)
    released = []

    def acquire(*_, **__):
        c.request_stop()
        return True

    monkeypatch.setattr(
        controller,
        "_OWNER",
        SimpleNamespace(acquire=acquire, release=lambda: released.append(True)),
    )
    with pytest.raises(controller.ControllerError, match="controller_stopped"):
        c.run()
    assert released == [True] and c._journal is None


def test_environment_checks_never_read_credential_values(monkeypatch):
    class NamesOnly:
        def __iter__(self):
            return iter(["OPENAI_API_KEY"])

        def __getitem__(self, _):
            pytest.fail("Ambient credential read")

    with monkeypatch.context() as patch:
        patch.setattr(controller.os, "environ", NamesOnly())
        assert not controller._environment_safe()


@pytest.mark.parametrize(
    "key",
    [
        "OPENAI_CUSTOM_HEADERS",
        "OPENAI_ADMIN_KEY",
        "OPENAI_API_KEY",
        "SALESAGENT_ENABLE_EVAL_TRACES",
        "https_proxy",
    ],
)
def test_ambient_settings_reject_before_source_or_sdk(tmp_path, monkeypatch, key):
    c = make(tmp_path)
    monkeypatch.setenv(key, "PRIVATE_AMBIENT_VALUE")
    with pytest.raises(
        controller.ControllerError, match="^ambient_configuration$"
    ) as caught:
        c.run()
    assert c._journal is None and "PRIVATE" not in str(caught.value)


@pytest.mark.parametrize(
    "event,args",
    [
        ("socket.__new__", (None, socket.AF_INET, 1, 0)),
        ("socket.__new__", (None, socket.AF_INET6, 1, 0)),
        ("socket.connect", (None, ("example.invalid", 443))),
        ("socket.getaddrinfo", ("example.invalid", 443)),
        ("socket.bind", (None, ("127.0.0.1", 0))),
    ],
)
def test_no_socket_or_dns_while_owned(event, args):
    controller._NETWORK_BLOCKED.set()
    with pytest.raises(controller.ControllerError, match="guard_failed"):
        controller._audit(event, args)


def test_development_digest_detects_mutation_and_untracked_source(tmp_path):
    (tmp_path / "src").mkdir()
    file = tmp_path / "src" / "example.py"
    file.write_text("VALUE = 1\n")
    first = controller._development_digest(tmp_path)
    file.write_text("VALUE = 2\n")
    assert controller._development_digest(tmp_path) != first
    second = controller._development_digest(tmp_path)
    (tmp_path / "src" / "extra.py").write_text("X = 1\n")
    assert controller._development_digest(tmp_path) != second


def test_development_digest_rejects_source_indirection(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "link.py").symlink_to(__file__)
    with pytest.raises(controller.ControllerError, match="source_verification_failed"):
        controller._development_digest(tmp_path)


def test_development_seam_rejects_external_review_claims(tmp_path):
    c = make(
        tmp_path,
        source_receipt=receipt().model_copy(update={"provenance": "external-review"}),
    )
    with pytest.raises(
        controller.ControllerError, match="offline_configuration_required"
    ):
        c._run_development_offline()


def resources(*, failure=None, live=False):
    r = controller._Resources()
    closed = []

    def close(name):
        closed.append(name)
        if failure == name:
            raise RuntimeError("PRIVATE_CLEANUP_FAILURE")

    r.http = SimpleNamespace(close=lambda: close("http"), is_closed=True)
    r.sdk = SimpleNamespace(close=lambda: close("sdk"), is_closed=lambda: True)
    r.provider = SimpleNamespace(
        close=lambda: close("provider"),
        _call_lock=threading.Lock(),
        _attempt_lock=threading.Lock(),
        _active=None,
    )
    r.mock = SimpleNamespace(close=lambda: close("mock"))
    r.threads.add(SimpleNamespaceThread(live))
    return r, closed


class SimpleNamespaceThread:
    def __init__(self, live):
        self.live = live
        self.joined = False

    def join(self, _):
        self.joined = True

    def is_alive(self):
        return self.live


@pytest.mark.parametrize("failure", ["sdk", "http", "provider", "mock"])
def test_all_cleanup_steps_attempted_and_failure_is_permanent(failure):
    r, closed = resources(failure=failure)
    with pytest.raises(controller.ControllerError, match="cleanup_failed"):
        r.close()
    assert closed == ["sdk", "http", "provider", "mock"]
    assert all(t.joined for t in r.threads)
    with pytest.raises(controller.ControllerError, match="cleanup_failed"):
        r.close()
    assert not r.report()["cleanup_verified"]


@pytest.mark.parametrize("outstanding", ["worker", "call", "attempt", "post"])
def test_shutdown_requires_observed_quiescence(outstanding):
    r, _ = resources(live=outstanding == "worker")
    if outstanding == "call":
        r.provider._call_lock.acquire()
    if outstanding == "attempt":
        r.provider._attempt_lock.acquire()
    if outstanding == "post":
        r.requests = 1
    with pytest.raises(controller.ControllerError, match="cleanup_failed"):
        r.close()
    assert not r.report()["cleanup_verified"]


def test_cleanup_success_is_observed_and_idempotent():
    r, closed = resources()
    r.close()
    r.close()
    assert closed == ["sdk", "http", "provider", "mock"]
    assert r.report()["cleanup_verified"]
    assert all(t.joined for t in r.threads)


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/health"),
        ("POST", "/api/v1/chat/"),
        ("GET", "/api/v1/traces/a/b"),
        ("POST", "/api/v1/traces/a"),
    ],
)
def test_bridge_only_forwards_approved_routes(method, path):
    r = controller._Resources()
    with pytest.raises(controller.ControllerError, match="guard_failed"):
        r.forward(httpx.Request(method, "http://canary.invalid" + path))


def test_synthetic_guards_observe_configuration_privacy_and_ownership(
    tmp_path, monkeypatch
):
    c = make(tmp_path)
    c._journal = object()
    r = c._resources
    r.provider = SimpleNamespace(
        delegate=c._mock,
        binding=SimpleNamespace(
            project_id=controller._PROJECT, organization_id=controller._ORGANIZATION
        ),
        stopped=False,
    )
    r.http = SimpleNamespace(
        _transport=r.provider, _mounts={}, is_closed=False, follow_redirects=False
    )
    r.sdk = SimpleNamespace(
        max_retries=2,
        timeout=30,
        base_url="https://api.openai.com/v1/",
        api_key=controller._CREDENTIAL,
        project=controller._PROJECT,
        organization=controller._ORGANIZATION,
        is_closed=lambda: False,
    )
    r.entered = True
    r.client = SimpleNamespace(
        portal=object(), task=SimpleNamespace(done=lambda: False)
    )
    r.threads.add(threading.current_thread())
    monkeypatch.setattr(c, "_check_source", lambda: None)
    monkeypatch.setattr(c, "_check_application", lambda: None)
    controller._OWNER.acquire()
    c._entry.acquire()
    controller._NETWORK_BLOCKED.set()
    try:
        assert all(c._facts().values())
        r.sdk.max_retries = 0
        assert not c._facts()["configuration_verified"]
        r.sdk.max_retries = 2
        r.sdk.base_url = "https://unexpected.invalid/"
        assert not c._facts()["safety_ok"]
        r.sdk.base_url = "https://api.openai.com/v1/"
        monkeypatch.setattr(logging.getLogger("openai"), "isEnabledFor", lambda _: True)
        assert not c._facts()["privacy_ok"]
    finally:
        c._entry.release()
        controller._OWNER.release()


def test_unknown_usage_and_local_spending_pause_are_not_hardcoded_success(
    tmp_path, monkeypatch
):
    c = make(tmp_path)
    facts = {
        name: True
        for name, field in controller.AttemptGuards.model_fields.items()
        if field.annotation is bool
    }
    monkeypatch.setattr(c, "_facts", lambda: dict(facts))
    snapshot = SimpleNamespace(unknown_attempts=1, estimated_subtotal_usd="0")
    c._journal = SimpleNamespace(provider_snapshot=lambda _: snapshot)
    c._resources.provider = SimpleNamespace(binding=object())
    result = c._attempt_guards()
    assert (
        not result.spending_headroom_verified and result.external_unknown_attempts == 1
    )
    snapshot.unknown_attempts = 0
    snapshot.estimated_subtotal_usd = "5"
    assert not c._attempt_guards().spending_headroom_verified


def test_fixed_error_categories_do_not_echo_external_values():
    error = controller.ControllerError("PRIVATE_CREDENTIAL_OR_PROVIDER_PAYLOAD")
    assert str(error) == "composition_failed"
    assert "PRIVATE" not in json.dumps({"error": str(error)})


@pytest.mark.parametrize("fault", ["python", "revision", "dependency", "fixtures"])
def test_preparation_rejects_wrong_runtime_revision_dependencies_or_fixtures(
    tmp_path, monkeypatch, fault
):
    c = make(tmp_path)
    monkeypatch.setattr(
        source,
        "_runtime",
        lambda _: SimpleNamespace(python="3.12.13" if fault == "python" else "3.13.15"),
    )
    monkeypatch.setattr(
        source,
        "_git_identity",
        lambda _: SimpleNamespace(
            commit="0" * 40 if fault == "revision" else source.APPLICATION_REVISION
        ),
    )

    def dependencies(_):
        if fault == "dependency":
            raise source.SourceError("PRIVATE_DEPENDENCY_ERROR")

    monkeypatch.setattr(source, "_dependencies", dependencies)
    with pytest.raises(controller.ControllerError, match="^runtime_invalid$"):
        c._check_application()


def test_journal_accounting_and_copy_isolated_evidence_without_application(
    tmp_path, monkeypatch
):
    c = make(tmp_path)
    registry, writer = make_journal(tmp_path)
    binding = writer.bind_provider(
        source.resolve_definition(source.V3),
        project_id=controller._PROJECT,
        organization_id=controller._ORGANIZATION,
    )
    provider = controller.ProviderTransportV3(
        writer, binding, c._mock, guards=c._attempt_guards
    )
    c._journal, c._resources.provider = writer, provider
    facts = {
        name: True
        for name, field in controller.AttemptGuards.model_fields.items()
        if field.annotation is bool
    }
    monkeypatch.setattr(c, "_facts", lambda: dict(facts))
    try:
        before = tree_bytes(Path(registry.path))
        snapshot = writer.driver_snapshot(binding)
        snapshot.accounting["logical_calls"] = 999
        snapshot.evidence["A1"] = {"chat": {"message": "forged"}}
        guards = c._guards()
        assert (
            guards.logical_calls
            == guards.provider_attempts
            == guards.unknown_attempts
            == 0
        )
        assert guards.accounting_complete and guards.recording_complete
        assert not writer.driver_snapshot(binding).evidence
        assert tree_bytes(Path(registry.path)) == before
    finally:
        provider.close()
        writer.close()


def test_cleanup_deadline_cannot_certify_success(monkeypatch):
    r, closed = resources()
    clock = iter([0, 10, 10])
    monkeypatch.setattr(controller, "monotonic", lambda: next(clock))
    with pytest.raises(controller.ControllerError, match="cleanup_failed"):
        r.close()
    assert closed == ["sdk", "http", "provider", "mock"]
    assert not r.report()["cleanup_verified"]
