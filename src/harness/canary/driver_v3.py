"""Single-use, offline v3 shopper orchestration in a trusted mock process.

No client, SDK, worker, credentials or application is discovered or constructed.
Public evidence and decisions belong to CanaryJournal. History validation is
transient consistency checking, not authentication of an external application.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Callable
from contextlib import suppress
from dataclasses import fields, is_dataclass, replace
from typing import Any, NoReturn

import httpx

from harness.canary.evidence_v3 import project_chat, project_trace
from harness.canary.execution_policy import Decision, OperationalGuards
from harness.canary.instrumentation_v3 import (
    BoundedResponsesClientV3,
    ProviderTransportV3,
)
from harness.canary.journal_v3 import CanaryJournal, DriverSnapshot, inspect_run
from harness.canary.runtime_v3 import V3, Turn, resolve_definition
from harness.core.prospective import strict_json
from harness.targets._salesagent_contract import Constraints

ERRORS = frozenset(
    {
        "configuration_invalid",
        "driver_reused",
        "gateway_invalid",
        "history_invalid",
        "application_failed",
        "invalid_public_evidence",
        "trace_unavailable",
        "usage_mismatch",
        "journal_failed",
        "execution_interrupted",
        "execution_stopped",
        "policy_stop",
        "cleanup_failed",
    }
)


class DriverError(RuntimeError):
    """Fixed safe categories only; no external exception or payload is echoed."""

    def __init__(self, code: str):
        super().__init__(code if code in ERRORS else "application_failed")


def _identity(value: Any, *, session: bool = False) -> str:
    if (
        type(value) is not str
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value) is None
        or (session and value.startswith(("resp_", "req_")))
    ):
        raise DriverError("invalid_public_evidence")
    return value


class HistoryCheckedResponsesClientV3:
    """Check the pinned _initial_messages contract before the bounded first call.

    The application must explicitly receive this client. No app package is
    imported. Expected context is derived exclusively from journal observations.
    Instructions, provider messages and request bodies are never persisted here.
    """

    def __init__(
        self, client: BoundedResponsesClientV3, halted: threading.Event
    ) -> None:
        self.client = client
        self._halted = halted
        self._turn: Turn | None = None
        self._history: tuple[dict[str, Any], ...] = ()
        self._calls = 0

    @property
    def calls(self) -> int:
        return self._calls

    def _arm(self, turn: Turn, snapshot: DriverSnapshot) -> None:
        if self._turn is not None or snapshot.active_slot != turn.slot:
            raise DriverError("history_invalid")
        roster = snapshot.binding.definition.turns
        self._history = tuple(
            snapshot.evidence[t.slot]
            for t in roster[: roster.index(turn)]
            if t.conversation == turn.conversation
        )
        self._turn, self._calls = turn, 0

    def _disarm(self) -> None:
        self._turn, self._history = None, ()

    def _check(self, request: Any) -> None:
        turn = self._turn
        if turn is None or request.previous_response_id is not None:
            raise ValueError
        values = request.input
        if type(values) is not tuple or len(values) != 2 * len(self._history) + 2:
            raise ValueError
        for item in values:
            record: Any = item
            if (
                not is_dataclass(item)
                or isinstance(item, type)
                or {f.name for f in fields(item)} != {"role", "content"}
                or type(record.role) is not str
                or type(record.content) is not str
            ):
                raise ValueError
        for index, prior in enumerate(self._history):
            shopper, assistant = values[2 * index : 2 * index + 2]
            if (
                shopper.role != "user"
                or shopper.content != prior["trace"]["user_message"]
                or assistant.role != "assistant"
                or strict_json(assistant.content)
                != {
                    "message": prior["chat"]["message"],
                    "recommended_product_ids": prior["trace"][
                        "recommended_product_ids"
                    ],
                }
            ):
                raise ValueError
        context, current = values[-2:]
        observed = strict_json(context.content)
        if (
            context.role != "user"
            or type(observed) is not dict
            or set(observed) != {"type", "resolved_constraints"}
            or observed["type"] != "salesagent_context"
            or type(observed["resolved_constraints"]) is not dict
            or set(observed["resolved_constraints"]) != set(Constraints.model_fields)
            or current.role != "user"
            or current.content != turn.message
        ):
            raise ValueError
        expected = (
            self._history[-1]["trace"]["resolved_constraints"]
            if self._history
            else Constraints().model_dump(mode="json")
        )
        actual = Constraints.model_validate(
            observed["resolved_constraints"]
        ).model_dump(mode="json")
        if actual != expected:
            raise ValueError

    def create_response(self, request: Any) -> Any:
        try:
            if self._halted.is_set() or self.client.transport.stopped:
                raise DriverError("execution_stopped")
            if self._turn is None:
                raise DriverError("history_invalid")
            if self._calls == 0:
                self._check(request)
        except BaseException:  # noqa: BLE001 - interruption closes dispatch without echoing inputs
            self._halted.set()
            with suppress(Exception):
                self.client.transport.journal.request_provider_stop(
                    self.client.transport.binding, "request_invalid"
                )
            raise DriverError("history_invalid") from None
        self._calls += 1
        return self.client.create_response(request)


class MockApplicationGatewayV3:
    """Exact supplied in-memory transport; no HTTP client or network fallback.

    The trusted callback must use responses_client for all application model
    calls. The driver checks that those calls match the journal reservations.
    """

    def __init__(
        self,
        transport: httpx.MockTransport,
        *,
        responses_client: HistoryCheckedResponsesClientV3,
    ):
        if (
            type(transport) is not httpx.MockTransport
            or type(responses_client) is not HistoryCheckedResponsesClientV3
        ):
            if type(responses_client) is HistoryCheckedResponsesClientV3:
                responses_client._halted.set()
                provider = responses_client.client.transport
                with suppress(Exception):
                    provider.journal.request_provider_stop(
                        provider.binding, "request_invalid"
                    )
            raise DriverError("gateway_invalid")
        self._transport = transport
        self.responses_client = responses_client
        self._posted: set[str] = set()
        self._closed = False
        self._reads: dict[str, int] = {}
        self._post_count = 0
        self.trace_reads = 0

    def _deny(self) -> NoReturn:
        self.responses_client._halted.set()
        provider = self.responses_client.client.transport
        with suppress(Exception):
            provider.journal.request_provider_stop(provider.binding, "request_invalid")
        raise DriverError("gateway_invalid")

    @property
    def shopper_posts(self) -> int:
        return self._post_count

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        if self._closed or type(self._transport) is not httpx.MockTransport:
            self._deny()
        provider = self.responses_client.client.transport
        if self.responses_client._halted.is_set() or provider.stopped:
            raise DriverError("execution_stopped")
        try:
            # This URL only identifies the public mock route; it is never sent
            # through a client, DNS resolver, redirect handler or network stack.
            request = httpx.Request(method, "http://canary.invalid" + path, json=body)
            if self.responses_client._halted.is_set() or provider.stopped:
                raise DriverError("execution_stopped")
            if method == "POST":
                self._post_count += 1
            else:
                self.trace_reads += 1
            response = self._transport.handle_request(request)
            try:
                if response.status_code != 200:
                    raise ValueError
                return strict_json(response.read())
            finally:
                response.close()
        except BaseException:  # noqa: BLE001 - public boundary suppresses external diagnostics
            raise DriverError(
                "trace_unavailable" if method == "GET" else "application_failed"
            ) from None

    def post_chat(self, message: str, *, session_id: str | None = None) -> Any:
        provider = self.responses_client.client.transport
        snapshot = provider.journal.driver_snapshot(provider.binding)
        turn = next(
            (
                t
                for t in snapshot.binding.definition.turns
                if t.slot == snapshot.active_slot
            ),
            None,
        )
        if (
            snapshot.stopped
            or turn is None
            or turn.message != message
            or turn.slot in self._posted
            or len(self._posted) >= snapshot.binding.definition.limits.shopper_posts
        ):
            self._deny()
        body = {"message": message}
        if session_id is not None:
            body["session_id"] = _identity(session_id, session=True)
        self._posted.add(turn.slot)  # Consumed before callback, including failures.
        return self._request("POST", "/api/v1/chat", body)

    def get_trace(self, trace_id: str) -> Any:
        trace_id = _identity(trace_id)
        provider = self.responses_client.client.transport
        snapshot = provider.journal.driver_snapshot(provider.binding)
        slot = snapshot.active_slot
        if (
            snapshot.stopped
            or slot is None
            or snapshot.evidence.get(slot, {}).get("chat", {}).get("trace_id")
            != trace_id
            or self._reads.get(slot, 0) >= 2
        ):
            self._deny()
        assert slot is not None
        self._reads[slot] = self._reads.get(slot, 0) + 1
        return self._request("GET", "/api/v1/traces/" + trace_id)

    def close(self) -> None:
        self._closed = True
        self._transport.close()


class OrderedCanaryDriverV3:
    """Run one fresh journal's four approved turns, once, using only mocks.

    close_client must close all explicitly supplied mock client resources (or
    confirm none exist). It is trusted cleanup, never an authenticated SDK or
    worker shutdown claim. run() returns saved journal inspection plus local
    driver diagnostics; execution_action there is the last persisted decision.
    """

    def __init__(
        self,
        journal: CanaryJournal,
        client: BoundedResponsesClientV3,
        *,
        guards: Callable[[], OperationalGuards],
        close_client: Callable[[], None],
    ):
        self.journal = journal
        self._halted = threading.Event()
        self._entry = threading.Lock()
        self._used = False
        self._cleaned = False
        try:
            if (
                type(client) is not BoundedResponsesClientV3
                or type(client.transport) is not ProviderTransportV3
                or client.transport.journal is not journal
                or client.transport.binding.definition != resolve_definition(V3)
                or not callable(guards)
                or not callable(close_client)
            ):
                raise ValueError
            self.provider = client.transport
            journal.driver_snapshot(self.provider.binding)
        except BaseException:  # noqa: BLE001 - invalid composition must close dispatch
            with suppress(Exception):
                journal.stop("operational_error")
            raise DriverError("configuration_invalid") from None
        self.responses_client = HistoryCheckedResponsesClientV3(client, self._halted)
        self._guards, self._close_client = guards, close_client

    def request_stop(self) -> None:
        """Close shopper admission before any potentially blocking journal write."""
        self._halted.set()
        self.provider.request_stop()

    def _snapshot(self) -> DriverSnapshot:
        return self.journal.driver_snapshot(self.provider.binding)

    def _open(self) -> None:
        if self._halted.is_set() or self.provider.stopped or self._snapshot().stopped:
            raise DriverError("execution_stopped")

    def _decision(self, *, reconciled: bool = True) -> Decision:
        guards = self._guards()
        if type(guards) is not OperationalGuards:
            raise DriverError("configuration_invalid")
        if not reconciled:
            guards = replace(guards, accounting_complete=False)
        return self.journal.record_decision(guards)

    def _usage_matches(self, slot: str) -> bool:
        snapshot = self._snapshot()
        evidence = snapshot.evidence[slot]
        if "trace" not in evidence:
            return False
        calls = [c for c in snapshot.completed_call_usage if c["slot"] == slot]
        a = snapshot.turn_accounting[slot]
        if (
            not calls
            or len(calls) != self.responses_client.calls
            or len(calls) != a["logical_calls"]
            or a["unknown_attempts"]
            or a["incomplete_calls"]
            or a["operational_errors"]
        ):
            return False
        return all(
            all(type(c[key]) is int and c[key] >= 0 for c in calls)
            and sum(c[key] for c in calls) == evidence["trace"]["token_usage"][key]
            for key in ("input_tokens", "output_tokens", "total_tokens")
        )

    def _cleanup(self, gateway: MockApplicationGatewayV3) -> None:
        if self._cleaned:
            return
        self._cleaned = True
        failed = False
        for close in (gateway.close, self._close_client, self.provider.close):
            try:
                close()
            except BaseException:  # noqa: BLE001 - attempt all cleanup even on interruption
                failed = True
        if failed:
            raise DriverError("cleanup_failed")

    def _failed_turn(self) -> None:
        """Use existing incomplete-evidence semantics only while still recordable."""
        snapshot = self._snapshot()
        if snapshot.stopped:
            return
        if snapshot.active_slot is not None:
            self.journal.assess_turn()
            self.journal.complete_turn()
        self._decision(reconciled=False)

    def run(self, gateway: MockApplicationGatewayV3) -> dict[str, Any]:
        if not self._entry.acquire(blocking=False):
            self.request_stop()
            raise DriverError("driver_reused")
        if self._used:
            self._entry.release()
            raise DriverError("driver_reused")
        self._used = True
        error: str | None = None
        stage = "configuration_invalid"
        completed = False
        try:
            if (
                type(gateway) is not MockApplicationGatewayV3
                or gateway.responses_client is not self.responses_client
            ):
                raise DriverError("gateway_invalid")
            snapshot = self._snapshot()
            if (
                snapshot.active_slot
                or snapshot.evidence
                or snapshot.accounting["logical_calls"]
            ):
                raise DriverError("configuration_invalid")
            self._open()
            stage = "journal_failed"
            decision = self._decision()
            sessions: dict[str, str] = {}
            trace_ids: set[str] = set()
            for turn in resolve_definition(V3).turns:
                if decision.action != "ADVANCE":
                    raise DriverError("policy_stop")
                self._open()
                snapshot = self._snapshot()
                if (
                    snapshot.decision != decision
                    or decision.next_slot != turn.slot
                    or snapshot.active_slot is not None
                ):
                    raise DriverError("configuration_invalid")
                self.journal.reserve_turn(turn.slot)
                self.responses_client._arm(turn, self._snapshot())
                try:
                    self._open()
                    stage = "application_failed"
                    chat = gateway.post_chat(
                        turn.message, session_id=sessions.get(turn.conversation)
                    )
                finally:
                    self.responses_client._disarm()
                self._open()  # A terminal provider stop overrides an old ADVANCE.
                stage = "journal_failed"
                self.journal.record_chat(chat)
                stage = "invalid_public_evidence"
                public = project_chat(chat)
                session = _identity(public["session_id"], session=True)
                trace_id = _identity(public["trace_id"])
                identity_ok = (
                    session == sessions[turn.conversation]
                    if turn.conversation in sessions
                    else session not in sessions.values()
                ) and trace_id not in trace_ids
                stage = "trace_unavailable"
                trace = gateway.get_trace(trace_id)
                # Check the first observed trace before its independent reread.
                # Invalid evidence is still passed to the journal projector;
                # no field is repaired to make correlation or stability pass.
                try:
                    first = project_trace(trace)
                    identity_ok = identity_ok and (
                        first["trace_id"] == trace_id
                        and first["session_id"] == session
                        and first["turn_index"] == int(turn.slot[1])
                        and first["user_message"] == turn.message
                        and first["model"]
                        == self.provider.binding.definition.inference.model
                    )
                except Exception:  # noqa: BLE001 - journal records malformed evidence safely
                    identity_ok = False
                reread = gateway.get_trace(trace_id)
                stage = "journal_failed"
                self.journal.record_trace(trace, reread=reread)
                reconciled = self._usage_matches(turn.slot)
                report = self.journal.assess_turn()
                correlated = report["prerequisites"]["status"] == "PASS"
                if correlated and identity_ok:
                    sessions[turn.conversation] = session
                    trace_ids.add(trace_id)
                self.journal.complete_turn()
                decision = self._decision(reconciled=reconciled and identity_ok)
                if not reconciled:
                    error = "usage_mismatch"
                if not identity_ok or not correlated:
                    error = "invalid_public_evidence"
                if decision.action == "STOP":
                    raise DriverError(error or "policy_stop")
            if decision.action != "COMPLETE":
                raise DriverError("execution_stopped")
            self._open()
            stage = "cleanup_failed"
            self._cleanup(gateway)
            # No worker was constructed. The explicit cleanup callback covers
            # supplied mock clients; synchronous POST/provider work has returned.
            stage = "journal_failed"
            self.journal.record_shutdown(
                worker_stopped=True, sdk_closed=True, no_inflight_provider=True
            )
            self.journal.seal()
            completed = True
        except BaseException as caught:  # noqa: BLE001 - preserve prefix on cancellation too
            error = str(caught) if isinstance(caught, DriverError) else stage
            self._halted.set()
            # Recording is attempted only if the existing journal still permits
            # it. A terminal stop or publication failure leaves its prefix alone.
            with suppress(Exception):
                self._failed_turn()
            with suppress(Exception):
                self.journal.stop(
                    "interrupted"
                    if isinstance(caught, KeyboardInterrupt)
                    else "operational_error"
                )
        finally:
            self._halted.set()
            if type(gateway) is MockApplicationGatewayV3:
                try:
                    self._cleanup(gateway)
                except BaseException:  # noqa: BLE001 - cleanup cannot reopen dispatch
                    error = "cleanup_failed"
                    with suppress(Exception):
                        self.journal.stop("operational_error")
            self.journal.close()
            self._entry.release()
        report = inspect_run(self.journal.registry, self.journal.run_id)
        return {
            **report,
            "driver_status": "completed" if completed else "stopped",
            "driver_error": error,
            "shopper_posts": gateway.shopper_posts
            if type(gateway) is MockApplicationGatewayV3
            else 0,
            "trace_reads": gateway.trace_reads
            if type(gateway) is MockApplicationGatewayV3
            else 0,
        }
