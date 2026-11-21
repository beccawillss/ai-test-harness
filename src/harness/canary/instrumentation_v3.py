"""Explicit v3, synchronous in-memory instrumentation. No live transport factory.

Mock callbacks and the containing Python process are trusted test code. This is
not a sandbox for hostile callbacks. No credentials or ambient configuration are
read, no SDK/client is constructed, and no judge/driver/controller belongs here.
"""

from __future__ import annotations

import logging
import math
import re
import threading
from collections.abc import Callable
from contextlib import suppress
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter
from typing import Any, Literal

import httpx

from harness.canary.evidence_v3 import (
    AttemptGuards,
    DispatchTelemetry,
    ResultTelemetry,
    retry_header_telemetry,
    validate_dispatch,
)
from harness.canary.journal_v3 import CallReservation, CanaryJournal, ProviderBinding
from harness.canary.recording import CanaryError
from harness.core.prospective import strict_json


def _logging_safe() -> bool:
    prefixes = ("openai", "httpx", "httpx2", "httpcore", "httpcore2")
    names = set(prefixes) | {
        name
        for name in dict(logging.Logger.manager.loggerDict)
        if any(name.startswith(p + ".") for p in prefixes)
    }
    return not any(
        logging.getLogger(name).isEnabledFor(logging.DEBUG) for name in names
    )


def _json_copy(value: Any) -> Any:
    """Snapshot only unambiguous JSON values, without retaining mutable aliases."""
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) is list:
        return [_json_copy(item) for item in value]
    if type(value) is dict and all(type(key) is str for key in value):
        return {key: _json_copy(item) for key, item in value.items()}
    raise ValueError


def _application_payload(request: Any) -> dict[str, Any]:
    """Pinned ResponseRequest mapping, structurally checked without app imports.

    The pinned input contract is a string or a nonempty homogeneous tuple of
    two-field dataclass records. This checks representation, not history origin.
    Request contents remain local to the active call and never enter telemetry.
    """
    value = request.input
    mapped: Any = value
    if type(value) is not str:
        if type(value) is not tuple or not value:
            raise ValueError
        mapped = []
        shapes = set()
        for item in value:
            if not is_dataclass(item) or isinstance(item, type):
                raise ValueError
            shape = frozenset(field.name for field in fields(item))
            shapes.add(shape)
            record: Any = item
            if shape == {"role", "content"}:
                role, content = record.role, record.content
                if (
                    type(role) is not str
                    or role not in ("user", "assistant")
                    or type(content) is not str
                ):
                    raise ValueError
                mapped.append({"role": role, "content": content})
            elif shape == {"call_id", "output"}:
                call_id, output = record.call_id, record.output
                if type(call_id) is not str or type(output) is not str:
                    raise ValueError
                mapped.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": output,
                    }
                )
            else:
                raise ValueError
        if len(shapes) != 1:
            raise ValueError
    if (
        type(request.instructions) is not str
        or type(request.tools) is not tuple
        or any(type(tool) is not dict for tool in request.tools)
        or type(request.text_format) is not dict
    ):
        raise ValueError
    return _json_copy(
        {
            "input": mapped,
            "instructions": request.instructions,
            "tools": list(request.tools),
            "text": {"format": request.text_format},
        }
    )


def _same_json(expected: Any, actual: Any) -> bool:
    """Compare parsed JSON values; booleans are distinct from JSON numbers."""
    if type(expected) in (int, float) and type(actual) in (int, float):
        return bool(expected == actual)
    if type(expected) is not type(actual):
        return False
    if type(expected) is dict:
        return expected.keys() == actual.keys() and all(
            _same_json(value, actual[key]) for key, value in expected.items()
        )
    if type(expected) is list:
        return len(expected) == len(actual) and all(
            _same_json(left, right)
            for left, right in zip(expected, actual, strict=True)
        )
    return bool(expected == actual)


class ProviderTransportV3(httpx.BaseTransport):
    """Observe only an explicitly supplied, exact HTTPX MockTransport instance."""

    def __init__(
        self,
        journal: CanaryJournal,
        binding: ProviderBinding,
        delegate: httpx.MockTransport,
        *,
        guards: Callable[[], AttemptGuards],
    ):
        self.journal, self.binding, self.delegate = journal, binding, delegate
        self.guards = guards
        self._halt = threading.Event()
        self._closed = threading.Event()
        self._reason: str | None = None
        self._call_lock, self._attempt_lock = threading.Lock(), threading.Lock()
        self._reason_lock = threading.Lock()
        self._active: CallReservation | None = None
        self._owner: int | None = None
        self._attempt = 0
        self._previous: str | None = None
        self._bytes: bytes | None = None
        self._expected: dict[str, Any] | None = None
        self._last: dict[str, Any] | None = None
        self._completed_ids: set[str] = set()
        try:
            if type(delegate) is not httpx.MockTransport or not callable(guards):
                raise ValueError
            journal.provider_snapshot(binding)
        except BaseException:  # noqa: BLE001 - unsupported construction cannot leave a gate open
            self._stop("request_invalid")
            raise CanaryError(
                "V3 requires an explicit bound in-memory transport"
            ) from None

    @property
    def stopped(self) -> bool:
        return (
            self._halt.is_set()
            or self._closed.is_set()
            or self.journal.provider_stopped
        )

    def _stop(self, reason: str) -> None:
        self._halt.set()  # Set before waiting for any recording/synchronization.
        with self._reason_lock:
            if self._reason is None:
                self._reason = reason
        with suppress(Exception):
            self.journal.request_provider_stop(self.binding, self._reason)

    def request_stop(self, *, pause: bool = False) -> None:
        """Terminal operator control; safe while an already dispatched attempt drains."""
        self._stop("operator_pause" if pause else "operator_stop")

    def _require_open(self) -> None:
        if self.stopped:
            raise CanaryError("V3 provider dispatch is permanently stopped")

    def run_call(self, request: Any, invoke: Callable[[], Any]) -> Any:
        """Reserve once and invoke the unchanged application delegate once."""
        if not self._call_lock.acquire(blocking=False):
            self._stop("concurrency_error")
            raise CanaryError("V3 concurrent or reentrant call rejected")
        reservation = None
        application_id = None
        finished = False
        try:
            self._require_open()
            if not _logging_safe():
                self._stop("guard_failed")
                raise CanaryError("V3 requires SDK and HTTP debug logging disabled")
            snapshot = self.journal.provider_snapshot(self.binding)
            turn = next(
                (
                    t
                    for t in self.binding.definition.turns
                    if t.slot == snapshot.active_slot
                ),
                None,
            )
            inference = self.binding.definition.inference
            if (
                snapshot.stopped
                or turn is None
                or request.model != inference.model
                or request.max_output_tokens != inference.max_output_tokens
                or type(request.max_output_tokens) is not int
                or request.reasoning_effort != inference.reasoning_effort
            ):
                raise ValueError
            self._expected = _application_payload(request)
            if snapshot.next_logical_call == 1:
                message = (
                    request.input
                    if isinstance(request.input, str)
                    else getattr(request.input[-1], "content", None)
                )
                if request.previous_response_id is not None or message != turn.message:
                    raise ValueError
            reservation = self.journal.reserve_provider_call(
                self.binding,
                slot=turn.slot,
                previous_response_id=request.previous_response_id,
            )
            self._active, self._owner = reservation, threading.get_ident()
            self._attempt, self._previous, self._bytes, self._last = (
                0,
                request.previous_response_id,
                None,
                None,
            )
            result = invoke()
            response_id = getattr(result, "response_id", None)
            if isinstance(response_id, str) and re.fullmatch(
                r"resp_[A-Za-z0-9_-]{1,120}", response_id
            ):
                application_id = response_id
            if (
                self._last is None
                or self._last["outcome"] != "completed"
                or not response_id
                or response_id != self._last["response_id"]
            ):
                self._stop("response_identity_mismatch")
                raise CanaryError("V3 application and provider completion differ")
            if self.stopped:
                raise CanaryError("V3 provider stopped after recording result")
            self.journal.finish_provider_call(
                self.binding,
                reservation,
                outcome="returned",
                response_id=response_id,
            )
            finished = True
            self._completed_ids.add(response_id)
            return result
        except BaseException:  # noqa: BLE001 - never emit application/SDK exception chains
            self._stop(
                self._reason or ("delegate_error" if reservation else "request_invalid")
            )
            if reservation is not None and not finished:
                with suppress(Exception):
                    self.journal.finish_provider_call(
                        self.binding,
                        reservation,
                        outcome="error",
                        response_id=application_id,
                        failure=self._reason or "delegate_error",
                    )
            raise CanaryError(
                "V3 logical call failed; preserve evidence; no replacement"
            ) from None
        finally:
            self._active, self._owner = None, None
            self._expected = None
            self._call_lock.release()

    def _validate_request(self, request: httpx.Request) -> int:
        body = strict_json(request.content)
        inference = self.binding.definition.inference
        if (
            request.method != "POST"
            or str(request.url) != "https://api.openai.com/v1/responses"
            or not isinstance(body, dict)
            or body.get("model") != inference.model
            or type(body.get("max_output_tokens")) is not int
            or body["max_output_tokens"] != inference.max_output_tokens
            or body.get("reasoning") != {"effort": inference.reasoning_effort}
            or body.get("stream", False) is not False
            or body.get("previous_response_id") != self._previous
            or set(body)
            - {
                "model",
                "input",
                "previous_response_id",
                "instructions",
                "tools",
                "text",
                "reasoning",
                "max_output_tokens",
                "tool_choice",
                "parallel_tool_calls",
                "store",
                "stream",
            }
            or body.get("parallel_tool_calls", False) is not False
            or body.get("tool_choice", "auto") != "auto"
            or body.get("store", True) is not True
        ):
            raise ValueError
        if self._expected is None or any(
            key not in body or not _same_json(value, body[key])
            for key, value in self._expected.items()
        ):
            raise ValueError
        for header, expected in (
            ("openai-project", self.binding.project_id),
            ("openai-organization", self.binding.organization_id),
        ):
            if request.headers.get_list(header) != [expected]:
                raise ValueError
        retry = request.headers.get_list("x-stainless-retry-count")
        if len(retry) != 1 or re.fullmatch(r"[012]", retry[0]) is None:
            raise ValueError
        if self._bytes is not None and request.content != self._bytes:
            raise ValueError
        timeouts = request.extensions.get("timeout", {})
        if not timeouts or any(
            v != inference.timeout_seconds for v in timeouts.values()
        ):
            raise ValueError
        return int(retry[0])

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self._require_open()  # SDK retries after an exception must fail before any intent.
        if not self._attempt_lock.acquire(blocking=False):
            self._stop("concurrency_error")
            raise CanaryError("V3 concurrent attempt rejected")
        try:
            self._require_open()
            if self._active is None or self._owner != threading.get_ident():
                self._stop("concurrency_error")
                raise CanaryError("V3 attempt has no owning logical call")
            try:
                if not _logging_safe():
                    raise ValueError
                delegate = self.delegate
                if type(delegate) is not httpx.MockTransport:
                    raise ValueError
                retry_count = self._validate_request(request)
            except Exception:  # noqa: BLE001 - request data must never reach diagnostics
                self._stop("request_invalid")
                raise CanaryError(
                    "V3 prepared request differs from its binding"
                ) from None
            attempt = self._attempt + 1
            try:
                guards = self.guards()
                dispatch = DispatchTelemetry(
                    sdk_retry_count=retry_count,
                    started_at=datetime.now(UTC).isoformat(),
                    guards=guards,
                )
                self.journal.dispatch_provider_attempt(
                    self.binding, self._active, attempt, telemetry=dispatch
                )
            except BaseException:  # noqa: BLE001 - no dispatch after failed guards/recording
                self._stop("guard_failed")
                raise CanaryError(
                    "V3 attempt preflight failed; no forwarding"
                ) from None
            self._attempt, self._bytes = attempt, request.content
            validate_dispatch(dispatch, now=datetime.now(UTC))
            self._require_open()
            started = perf_counter()
            response = None
            try:
                response = delegate.handle_request(
                    request
                )  # Original object/bytes/headers/extensions.
                response.read()
            except BaseException:  # noqa: BLE001 - completion is unknown, not a zero-cost failure
                self._stop("transport_ambiguous")
                headers = response.headers if response is not None else httpx.Headers()
                telemetry = ResultTelemetry(
                    duration_ms=(perf_counter() - started) * 1000,
                    read_complete=False,
                    json_state="unavailable",
                    observed_http_status=response.status_code
                    if response is not None
                    else None,
                    **retry_header_telemetry(headers),
                )
                self.journal.observe_provider_attempt(
                    self.binding,
                    self._active,
                    attempt,
                    None,
                    telemetry=telemetry,
                    request_id=headers.get("x-request-id"),
                    should_retry_header=headers.get("x-should-retry"),
                )
                raise CanaryError("V3 transport completion is ambiguous") from None
            json_state: Literal["valid", "invalid", "unavailable"]
            try:
                envelope = strict_json(response.content)
                if not isinstance(envelope, dict):
                    raise TypeError
                json_state = "valid"
            except (ValueError, UnicodeError, TypeError):
                envelope, json_state = None, "invalid"
            telemetry = ResultTelemetry(
                duration_ms=(perf_counter() - started) * 1000,
                read_complete=True,
                json_state=json_state,
                observed_http_status=response.status_code,
                **retry_header_telemetry(response.headers),
            )
            self._last = self.journal.observe_provider_attempt(
                self.binding,
                self._active,
                attempt,
                envelope,
                telemetry=telemetry,
                http_status=response.status_code,
                request_id=response.headers.get("x-request-id"),
                should_retry_header=response.headers.get("x-should-retry"),
            )
            snapshot = self.journal.provider_snapshot(self.binding)
            if self._last["outcome"] not in {"completed", "retryable_http_failure"}:
                self._stop("provider_error")
            elif self._last["outcome"] == "completed":
                if (
                    not self._last["response_id"]
                    or self._last["response_id"] in self._completed_ids
                ):
                    self._stop("response_identity_mismatch")
                elif snapshot.unknown_attempts:
                    self._stop("unknown_usage")
            if Decimal(snapshot.estimated_subtotal_usd) >= Decimal(
                self.binding.definition.limits.estimated_pause_usd
            ):
                self._stop("spending_pause")
            return response
        except BaseException:  # noqa: BLE001 - latch survives SDK retry iterations and disk failure
            self._stop(self._reason or "recording_failed")
            raise CanaryError(
                "V3 provider attempt stopped; no further dispatch"
            ) from None
        finally:
            self._attempt_lock.release()

    def close(self) -> None:
        self._closed.set()
        try:
            self.delegate.close()
        except BaseException:  # noqa: BLE001 - cleanup never grants retry or hides evidence
            self._stop("cleanup_failed")
            raise CanaryError("V3 transport closure failed") from None


class BoundedResponsesClientV3:
    """Decorate the existing application ResponsesClient contract without imports."""

    def __init__(self, delegate: Any, transport: ProviderTransportV3):
        self.delegate, self.transport = delegate, transport

    def create_response(self, request: Any) -> Any:
        return self.transport.run_call(
            request, lambda: self.delegate.create_response(request)
        )
