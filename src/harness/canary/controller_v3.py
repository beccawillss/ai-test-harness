"""Owned, single-use, mock-only composition of the pinned Sales Agent.

Public admission always checks clean committed source. The private development
seam produces explicitly unverified simulation evidence, never execution authority.
Callbacks and the containing process are trusted; this is not a hostile-code sandbox.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import socket
import sys
import threading
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from time import monotonic
from typing import Any, Literal
from uuid import uuid4

import httpx

from harness.canary import runtime_v3 as source
from harness.canary.driver_v3 import MockApplicationGatewayV3, OrderedCanaryDriverV3
from harness.canary.evidence_v3 import AttemptGuards
from harness.canary.execution_policy import OperationalGuards
from harness.canary.instrumentation_v3 import (
    BoundedResponsesClientV3,
    ProviderTransportV3,
    _logging_safe,
)
from harness.canary.journal_v3 import CanaryJournal, initialize_registry, inspect_run

_OWNER = threading.Lock()
_NETWORK_BLOCKED = threading.Event()
_NETWORK_VIOLATION = threading.Event()
_AUDIT_INSTALLED = False
_IMPORTED_MAIN: Any = None
_PROJECT = "proj_offline_synthetic"
_ORGANIZATION = "org_offline_synthetic"
_CREDENTIAL = "sk-offline-synthetic-not-associated-with-any-account"
_CLEANUP_SECONDS = 5.0


class ControllerError(RuntimeError):
    """Only fixed categories cross the controller boundary."""

    def __init__(self, code: str):
        allowed = {
            "offline_configuration_required",
            "controller_reused",
            "controller_stopped",
            "application_owned",
            "source_verification_failed",
            "runtime_invalid",
            "ambient_configuration",
            "composition_failed",
            "guard_failed",
            "cleanup_failed",
            "evidence_unavailable",
        }
        super().__init__(code if code in allowed else "composition_failed")


def _audit(event: str, arguments: tuple[Any, ...]) -> None:
    if not _NETWORK_BLOCKED.is_set():
        return
    if event in {
        "socket.connect",
        "socket.bind",
        "socket.getaddrinfo",
        "socket.gethostbyname",
        "socket.gethostbyaddr",
        "socket.sendto",
    }:
        _NETWORK_VIOLATION.set()
        raise ControllerError("guard_failed")
    if event == "socket.__new__" and arguments[1] in {socket.AF_INET, socket.AF_INET6}:
        _NETWORK_VIOLATION.set()
        raise ControllerError("guard_failed")


def _environment_safe() -> bool:
    # Inspect names only. Never read, copy, restore or report ambient credentials.
    return not any(
        key.upper().startswith(("OPENAI_", "SALESAGENT_"))
        or key.upper() in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"}
        for key in os.environ
    )


def _development_digest(root: Path) -> str:
    """Mutation detection only; not a committed identity or approval claim."""
    paths = set((root / "src").rglob("*.py"))
    paths.update(
        root / p
        for p in (
            "uv.lock",
            "pyproject.toml",
            "docs/plans/canary-runtime-v3-slice5.md",
            "tests/test_canary_controller_v3.py",
            "tests/test_canary_controller_v3_application.py",
        )
    )
    digest = sha256()
    for path in sorted(paths):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ControllerError("source_verification_failed")
        if path.exists():
            name, content = (
                path.relative_to(root).as_posix().encode(),
                path.read_bytes(),
            )
            digest.update(len(name).to_bytes(8, "big") + name)
            digest.update(len(content).to_bytes(8, "big") + content)
    return digest.hexdigest()


class _Resources:
    """Observe ownership and termination before the driver records shutdown."""

    def __init__(self) -> None:
        self.http: Any = None
        self.mock: httpx.MockTransport | None = None
        self.sdk: Any = None
        self.provider: ProviderTransportV3 | None = None
        self.client: Any = None
        self.application: Any = None
        self.entered = False
        self.lifespan_exited = False
        self.threads: set[threading.Thread] = set()
        self.posts = 0
        self.requests = 0
        self._request_lock = threading.Lock()
        self._closing = False
        self._attempted = False
        self._failed = False

    def observe_threads(self) -> None:
        if self.client is None or self.client.portal is None:
            return

        def observe() -> set[threading.Thread]:
            # The application lock pins AnyIO 4.14.2. RunVar is loop-local; a
            # process-wide thread-name scan cannot establish ownership.
            from anyio._backends._asyncio import _threadpool_workers

            try:
                workers = set(_threadpool_workers.get())
            except LookupError:
                workers = set()
            return {threading.current_thread(), *workers}

        self.threads.update(self.client.portal.call(observe))

    def forward(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        allowed = (request.method == "POST" and path == "/api/v1/chat") or (
            request.method == "GET"
            and path.startswith("/api/v1/traces/")
            and len(path.split("/")) == 5
            and bool(path.rsplit("/", 1)[-1])
        )
        if (
            not allowed
            or request.url.query
            or request.url.host != "canary.invalid"
            or request.url.scheme != "http"
            or not self.entered
        ):
            raise ControllerError("guard_failed")
        with self._request_lock:
            if self._closing or self.requests:
                raise ControllerError("guard_failed")
            self.requests += 1
            self.posts += int(request.method == "POST")
        try:
            response = self.client.request(
                request.method,
                path,
                content=request.content,
                headers={"content-type": "application/json"},
                follow_redirects=False,
            )
            try:
                if response.is_redirect:
                    raise ControllerError("guard_failed")
                return httpx.Response(response.status_code, content=response.read())
            finally:
                response.close()
        finally:
            try:
                self.observe_threads()
            finally:
                with self._request_lock:
                    self.requests -= 1

    def close(self) -> None:
        if self._attempted:
            if self._failed:
                raise ControllerError("cleanup_failed")
            return
        self._attempted = True
        self._failed = True  # Any failed observation below remains fail-closed.
        started = monotonic()
        failed = False
        with self._request_lock:
            self._closing = True
            failed |= self.requests != 0

        def attempt(action: Callable[[], Any]) -> bool:
            nonlocal failed
            try:
                action()
                return True
            except BaseException:  # noqa: BLE001 - attempt every owned cleanup on interruption
                failed = True
                return False

        if self.client is not None:
            attempt(self.observe_threads)
            if self.entered and attempt(lambda: self.client.__exit__(None, None, None)):
                self.entered = False
                self.lifespan_exited = True
            attempt(self.client.close)
        for owned in (self.sdk, self.http, self.provider, self.mock):
            if owned is not None:
                attempt(owned.close)
        for thread in self.threads:

            def join_thread(t: threading.Thread = thread) -> None:
                t.join(max(0, _CLEANUP_SECONDS - (monotonic() - started)))

            attempt(join_thread)
            failed |= thread.is_alive()
        if self.client is not None:
            failed |= (
                self.entered
                or not self.lifespan_exited
                or not self.client.is_closed
                or self.client.portal is not None
                or not self.client.task.done()
            )
        failed |= self.sdk is not None and not self.sdk.is_closed()
        failed |= self.http is not None and not self.http.is_closed
        if self.provider is not None:
            # Observe the existing transport locks rather than assume that a
            # closed HTTP client proves the absence of admitted provider work.
            for lock in (self.provider._call_lock, self.provider._attempt_lock):
                free = lock.acquire(blocking=False)
                failed |= not free
                if free:
                    lock.release()
            failed |= self.provider._active is not None
        failed |= monotonic() - started > _CLEANUP_SECONDS
        self._failed = bool(failed)
        if failed:
            raise ControllerError("cleanup_failed")

    def report(self) -> dict[str, Any]:
        return {
            "cleanup_verified": self._attempted and not self._failed,
            "active_shopper_requests": self.requests,
            "application_lifespan_exited": self.lifespan_exited,
            "owned_threads": len(self.threads),
            "surviving_owned_threads": sum(t.is_alive() for t in self.threads),
            "sdk_closed": self.sdk is not None and self.sdk.is_closed(),
            "http_closed": self.http is not None and self.http.is_closed,
        }


class OfflineCanaryControllerV3:
    """One offline invocation; no transport discovery, resume or live mode.

    Run in a process without OPENAI_*, SALESAGENT_* or proxy environment settings.
    A caller-supplied event supports stop before construction; deliver subsequent
    stops with request_stop(), which closes provider admission before journal I/O.
    The supplied mock and newly created registry belong exclusively to this run.
    """

    def __init__(
        self,
        *,
        offline: Literal[True],
        harness_root: Path,
        application_root: Path,
        source_receipt: object,
        evidence_parent: Path,
        provider_mock: httpx.MockTransport,
        stop_event: threading.Event | None = None,
    ) -> None:
        if offline is not True or type(provider_mock) is not httpx.MockTransport:
            raise ControllerError("offline_configuration_required")
        if stop_event is not None and type(stop_event) is not threading.Event:
            raise ControllerError("offline_configuration_required")
        self._stop = threading.Event()
        if stop_event is not None and stop_event.is_set():
            self._stop.set()
        self._entry = threading.Lock()
        self._used = False
        self._harness_root = harness_root.resolve()
        self._application_root = application_root.resolve()
        self._receipt = source.parse_receipt(source_receipt)
        source.validate_binding(self._receipt.binding)
        if self._receipt.binding.identifier != source.V3:
            raise ControllerError("offline_configuration_required")
        self._evidence_parent = evidence_parent
        self._mock = provider_mock
        self._resources = _Resources()
        self._resources.mock = provider_mock
        self._journal: CanaryJournal | None = None
        self._driver: OrderedCanaryDriverV3 | None = None
        self._check_source: Callable[[], None] = self._verify_source

    def request_stop(self) -> None:
        self._stop.set()  # Never wait for application, ownership or journal first.
        if self._driver is not None:
            self._driver.request_stop()
        elif self._resources.provider is not None:
            self._resources.provider.request_stop()
        elif self._journal is not None:
            self._journal.stop("operator_stop")

    def _open(self) -> None:
        if self._stop.is_set():
            raise ControllerError("controller_stopped")

    def _verify_source(self) -> None:
        try:
            source.verify_source(
                self._receipt,
                harness_root=self._harness_root,
                application_root=self._application_root,
            )
        except BaseException:  # noqa: BLE001 - no external diagnostics or cancellation leaks
            raise ControllerError("source_verification_failed") from None
        self._open()

    def _check_application(self) -> None:
        try:
            if not _environment_safe():
                raise ControllerError("ambient_configuration")
            runtime = source._runtime("application")
            if not runtime.python.startswith("3.13."):
                raise ControllerError("runtime_invalid")
            if (
                source._git_identity(self._application_root).commit
                != source.APPLICATION_REVISION
            ):
                raise ControllerError("runtime_invalid")
            source._dependencies(self._application_root)
            for name, expected in source.FIXTURE_HASHES:
                if (
                    sha256(
                        (self._application_root / "data" / name).read_bytes()
                    ).hexdigest()
                    != expected
                ):
                    raise ControllerError("runtime_invalid")
            source._module_origins(self._harness_root, self._application_root)
        except ControllerError:
            raise
        except BaseException:  # noqa: BLE001 - no source or runtime payloads in errors
            raise ControllerError("runtime_invalid") from None
        self._open()

    def _assemble(self) -> None:
        global _IMPORTED_MAIN
        self._check_application()
        spec = importlib.util.find_spec("salesagent")
        if (
            spec is None
            or spec.origin is None
            or (
                Path(spec.origin).resolve()
                != self._application_root / "src/salesagent/__init__.py"
            )
        ):
            raise ControllerError("runtime_invalid")
        if (
            "salesagent.main" in sys.modules
            and sys.modules["salesagent.main"] is not _IMPORTED_MAIN
        ):
            raise ControllerError("composition_failed")
        main = importlib.import_module("salesagent.main")
        _IMPORTED_MAIN = main
        default = main.app.state
        unused = default.chat_service._orchestrator._responses_client
        if (
            unused._client is not None
            or unused._api_key is not None
            or (default.session_repository._states or default.trace_repository._traces)
        ):
            raise ControllerError("composition_failed")
        # Imports occur only after the environment, source and mock-only process
        # guard have been checked. The unused default app has no SDK instance.
        openai = importlib.import_module("openai")
        testclient = importlib.import_module("starlette.testclient")
        responses = importlib.import_module("salesagent.agent.responses_client")
        r = self._resources
        assert r.provider is not None and self._journal is not None
        r.http = httpx.Client(
            transport=r.provider,
            trust_env=False,
            follow_redirects=False,
            timeout=30,
        )
        r.sdk = openai.OpenAI(
            api_key=_CREDENTIAL,
            admin_api_key="",
            webhook_secret="",
            organization=_ORGANIZATION,
            project=_PROJECT,
            base_url="https://api.openai.com/v1",
            timeout=30,
            max_retries=2,
            http_client=r.http,
        )
        delegate = responses.OpenAIResponsesClient(
            api_key=None,
            timeout_seconds=30,
            max_retries=2,
            sdk_client=r.sdk,
        )
        bounded = BoundedResponsesClientV3(delegate, r.provider)
        self._driver = OrderedCanaryDriverV3(
            self._journal,
            bounded,
            guards=self._guards,
            close_client=self._close_before_seal,
        )
        self._open()
        r.application = main.create_app(
            settings=main.Settings(
                enable_eval_traces=True,
                openai_api_key=None,
                openai_model="gpt-5.6-terra",
                openai_reasoning_effort="low",
                openai_max_output_tokens=2000,
                openai_timeout_seconds=30,
            ),
            responses_client=self._driver.responses_client,
        )
        r.client = testclient.TestClient(
            r.application,
            base_url="http://canary.invalid",
            follow_redirects=False,
        )
        r.client.__enter__()
        r.entered = True
        r.observe_threads()
        self._open()
        self._check_source()

    def _facts(self) -> dict[str, bool]:
        self._open()
        self._check_source()
        self._check_application()
        r = self._resources
        p = r.provider
        assert p is not None and self._journal is not None
        synthetic = (
            type(self._mock) is httpx.MockTransport
            and p.delegate is self._mock
            and p.binding.project_id == _PROJECT
            and p.binding.organization_id == _ORGANIZATION
            and _NETWORK_BLOCKED.is_set()
            and not _NETWORK_VIOLATION.is_set()
            and _OWNER.locked()
        )
        configured = (
            r.sdk is not None
            and r.sdk.max_retries == 2
            and r.sdk.timeout == 30
            and str(r.sdk.base_url) == "https://api.openai.com/v1/"
            and r.sdk.api_key == _CREDENTIAL
            and r.sdk.project == _PROJECT
            and r.sdk.organization == _ORGANIZATION
            and not r.sdk.is_closed()
            and r.http._transport is p
            and not r.http._mounts
            and not r.http.is_closed
            and not r.http.follow_redirects
        )
        privacy = _environment_safe() and _logging_safe()
        alive = (
            r.entered
            and r.client.portal is not None
            and not r.client.task.done()
            and bool(r.threads)
            and not p.stopped
        )
        return {
            "infrastructure_ok": alive,
            "safety_ok": synthetic and configured,
            "privacy_ok": privacy,
            # These are observations of a synthetic project/mock boundary only.
            "project_controls_verified": synthetic,
            "spending_headroom_verified": synthetic,
            "source_and_fixtures_verified": True,  # checks above returned successfully
            "configuration_verified": configured,
            "evidence_fresh": alive and privacy,
            "operator_allows_dispatch": not self._stop.is_set(),
            "exclusive_reservations_verified": _OWNER.locked() and self._entry.locked(),
        }

    def _close_before_seal(self) -> None:
        try:
            self._check_source()
        finally:
            self._resources.close()
        self._check_source()

    def _guards(self) -> OperationalGuards:
        facts = self._facts()
        assert self._journal is not None and self._resources.provider is not None
        snapshot = self._journal.driver_snapshot(self._resources.provider.binding)
        a = snapshot.accounting
        complete = not (
            a["incomplete_calls"] or a["unknown_attempts"] or a["operational_errors"]
        )
        return OperationalGuards(
            **facts,
            provider_completed=complete,
            recording_complete=snapshot.active_slot is None,
            accounting_complete=complete,
            logical_calls=a["logical_calls"],
            provider_attempts=a["provider_attempts"],
            unknown_attempts=a["unknown_attempts"],
            estimated_total_usd=Decimal(a["estimated_subtotal_usd"]),
        )

    def _attempt_guards(self) -> AttemptGuards:
        facts = self._facts()
        assert self._journal is not None and self._resources.provider is not None
        snapshot = self._journal.provider_snapshot(self._resources.provider.binding)
        facts["spending_headroom_verified"] &= (
            snapshot.unknown_attempts == 0
            and Decimal(snapshot.estimated_subtotal_usd) < Decimal(5)
        )
        return AttemptGuards(
            **facts,
            checked_at=datetime.now(UTC).isoformat(),
            external_unknown_attempts=snapshot.unknown_attempts,
            estimated_total_usd=snapshot.estimated_subtotal_usd,
        )

    def run(self) -> dict[str, Any]:
        """Admit only exact clean source matches, and execute exclusively offline."""
        return self._execute(development=False)

    def _run_development_offline(self) -> dict[str, Any]:
        """Private QA seam approved under §14; never a clean-source certificate."""
        if self._receipt.provenance != "synthetic-test":
            raise ControllerError("offline_configuration_required")
        return self._execute(development=True)

    def _execute(self, *, development: bool) -> dict[str, Any]:
        global _AUDIT_INSTALLED
        if not self._entry.acquire(blocking=False):
            self.request_stop()
            raise ControllerError("controller_reused")
        if self._used:
            self._entry.release()
            raise ControllerError("controller_reused")
        self._used = True
        owned = False
        error: ControllerError | None = None
        report: dict[str, Any] | None = None
        try:
            self._open()
            if not _environment_safe():
                raise ControllerError("ambient_configuration")
            if not _OWNER.acquire(blocking=False):
                raise ControllerError("application_owned")
            owned = True
            self._open()
            if not _AUDIT_INSTALLED:
                sys.addaudithook(_audit)
                _AUDIT_INSTALLED = True
            _NETWORK_BLOCKED.set()
            _NETWORK_VIOLATION.clear()
            if development:
                digest = _development_digest(self._harness_root)

                def check_development() -> None:
                    self._open()
                    if _development_digest(self._harness_root) != digest:
                        raise ControllerError("source_verification_failed")
                    self._check_application()

                self._check_source = check_development
            self._check_source()
            self._open()
            identity = uuid4().hex
            registry = initialize_registry(
                self._evidence_parent / ("offline-v3-" + identity)
            )
            self._journal = CanaryJournal(
                registry,
                "run-" + identity,
                "synthetic-offline-" + identity,
                source_receipt=self._receipt,
            )
            self._open()
            binding = self._journal.bind_provider(
                source.resolve_definition(source.V3),
                project_id=_PROJECT,
                organization_id=_ORGANIZATION,
            )
            self._resources.provider = ProviderTransportV3(
                self._journal,
                binding,
                self._mock,
                guards=self._attempt_guards,
            )
            self._assemble()
            self._open()
            assert self._driver is not None
            gateway = MockApplicationGatewayV3(
                httpx.MockTransport(self._resources.forward),
                responses_client=self._driver.responses_client,
            )
            report = self._driver.run(gateway)
        except BaseException as caught:  # noqa: BLE001 - terminal privacy boundary
            error = ControllerError(
                str(caught)
                if isinstance(caught, ControllerError)
                else "composition_failed"
            )
            with suppress(BaseException):
                self.request_stop()
        finally:
            self._stop.set()
            if owned:
                try:
                    self._resources.close()
                except BaseException:  # noqa: BLE001 - cleanup uncertainty prevents certification
                    error = ControllerError("cleanup_failed")
                if self._journal is not None:
                    try:
                        self._journal.close()
                    except BaseException:  # noqa: BLE001 - closure is part of successful execution
                        error = ControllerError("cleanup_failed")
                # A cleanup uncertainty poisons ownership for this process. A
                # subsequent controller must not overlap an unproven lifetime.
                if error is None or str(error) != "cleanup_failed":
                    _NETWORK_BLOCKED.clear()
                    _OWNER.release()
            else:
                try:
                    self._resources.close()
                except BaseException:  # noqa: BLE001 - dispose even on failed admission
                    error = ControllerError("cleanup_failed")
            self._entry.release()
        if report is None:
            if self._journal is None:
                raise error or ControllerError("composition_failed") from None
            try:
                report = inspect_run(self._journal.registry, self._journal.run_id)
            except BaseException:  # noqa: BLE001 - preserve evidence without exception leakage
                raise ControllerError("evidence_unavailable") from None
        resources = self._resources.report()
        certified = (
            report.get("completion_certified") is True
            and report.get("accounting_reconciled") is True
            and resources["cleanup_verified"] is True
        )
        if (
            report.get("driver_status") == "completed"
            and not certified
            and error is None
        ):
            error = ControllerError("evidence_unavailable")
        return {
            **report,
            "controller_status": "completed"
            if error is None and report.get("driver_status") == "completed"
            else "stopped",
            "controller_error": str(error) if error else report.get("driver_error"),
            "development_only": development,
            "source_verification": "pending_clean_committed_revision"
            if development
            else "clean_source_match_only",
            "source_authorised": False,
            "provider_evidence_authenticated": False,
            "authorises_live_execution": False,
            "human_review": "PENDING",
            "external_project_limit": "unverified_future_requirement",
            "billing": "unknown",
            "operational_observations": "synthetic_offline_only",
            "registry_path": str(self._journal.registry.path)
            if self._journal
            else None,
            "resources": resources,
        }
