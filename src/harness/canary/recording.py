"""Private canary artifacts and allowlisted non-streaming provider telemetry."""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any, Literal
from uuid import uuid4

import httpx

from harness.canary.inputs import (
    JUDGE_MODEL,
    JUDGE_ORDER,
    TARGET_MODEL,
    TARGET_REVISION,
    TARGET_TURNS,
    roster_hash,
)
from harness.core.fingerprints import canonical_json


class CanaryError(RuntimeError):
    """Fixed safe diagnostic; never constructed from an external exception."""


class CanaryStore:
    """Single-use private run directory. Not a Study or prospective store."""

    def __init__(
        self, directory: Path, *, mode: Literal["offline", "live"] = "offline"
    ):
        self.path = directory.absolute()
        self.mode = mode
        self.stopped = False
        if mode not in {"offline", "live"}:
            raise CanaryError("Unsupported canary mode")
        if self.path.parent.name != "salesagent-preflight-canary":
            raise CanaryError("A separate canary artifact namespace is required")
        for p in (self.path, *self.path.parents):
            if (
                p.is_symlink()
                or (p / ".git").exists()
                or p.name == "salesagent-study-v1"
            ):
                raise CanaryError(
                    "Canary artifacts must be outside repositories and Study storage"
                )
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent = self.path.parent.stat()
        if parent.st_uid != os.getuid() or parent.st_mode & 0o077:
            raise CanaryError("Canary namespace must be private and owner-controlled")
        self.path.mkdir(mode=0o700)  # Exclusive run identity; no implicit restart.
        self.write(
            "manifest",
            {
                "schema_version": "nonstudy-canary-v1",
                "mode": mode,
                "roster_hash": roster_hash(),
                "authorises_live_execution": False,
                "target_revision": TARGET_REVISION,
                "target": {
                    "model": TARGET_MODEL,
                    "reasoning_effort": "low",
                    "max_output_tokens": 2000,
                    "sdk_retries": 2,
                    "chat_posts": 4,
                    "logical_calls_max": 24,
                    "attempts_max": 72,
                },
                "judge": {
                    "model": JUDGE_MODEL,
                    "max_output_tokens": 8192,
                    "retries": 0,
                    "requests_max": 16,
                },
                "budget": {
                    "operator_pause_usd": "5",
                    "project_limit_usd": "10",
                    "project_limit_verified": False,
                },
            },
        )

    def write(self, name: str, value: Any) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise CanaryError("Invalid canary artifact name")
        try:
            fd = os.open(
                self.path / f"{name}.json",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(canonical_json(value) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            directory_fd = os.open(self.path, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except Exception:  # noqa: BLE001 - sanitize all recording failures at this boundary
            self.stopped = True
            raise CanaryError("Canary recording failed; no further dispatch") from None

    def event(self, value: dict[str, Any]) -> None:
        self.write("event-" + uuid4().hex, value)

    def stop(self, reason: str = "stopped") -> None:
        if reason not in {
            "stopped",
            "target_failure",
            "judge_failure",
            "provider_failure",
            "transport_ambiguous",
            "spending_or_usage_pause",
        }:
            raise CanaryError("Unknown canary stop category")
        self.stopped = True
        if not (self.path / "stopped.json").exists():
            self.write(
                "stopped",
                {"state": "stopped", "reason": reason, "automatic_resume": False},
            )

    def guard(self, *, allow_unknown: bool = False) -> None:
        if self.stopped or (self.path / "stopped.json").exists():
            raise CanaryError("Canary has stopped")
        summary = self.accounting()
        if Decimal(summary["estimated_subtotal_usd"]) >= Decimal(5) or (
            summary["unknown_attempts"] and not allow_unknown
        ):
            self.stop("spending_or_usage_pause")
            raise CanaryError("Canary paused for spending or unknown usage review")

    def accounting(self) -> dict[str, Any]:
        subtotal = Decimal(0)
        dispatched: set[tuple[str, str, int, int]] = set()
        completed: set[tuple[str, str, int, int]] = set()
        unknown = 0
        for path in self.path.glob("event-*.json"):
            value = json.loads(path.read_text())
            key = (
                value["role"],
                value["slot"],
                value["logical_call"],
                value["attempt"],
            )
            if value.get("kind") == "provider_dispatch":
                dispatched.add(key)
            if value.get("kind") == "provider_attempt":
                completed.add(key)
                cost = value["estimated_usd"]
                if cost is None:
                    unknown += 1
                else:
                    subtotal += Decimal(cost)
        unknown += len(dispatched - completed)
        return {
            "attempts": len(dispatched),
            "unknown_attempts": unknown,
            "estimated_subtotal_usd": str(subtotal),
            "estimated_total_usd": str(subtotal) if unknown == 0 else None,
            "billing_verified": False,
        }


def _count(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def usage_metadata(envelope: Any, *, role: str) -> dict[str, Any]:
    """Extract scalars only. Missing counters are unknown, including cache writes."""
    obj = envelope if isinstance(envelope, dict) else {}
    usage = obj.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    inputs = usage.get("input_tokens_details")
    inputs = inputs if isinstance(inputs, dict) else {}
    outputs = usage.get("output_tokens_details")
    outputs = outputs if isinstance(outputs, dict) else {}
    data = {
        key: _count(usage.get(key))
        for key in ("input_tokens", "output_tokens", "total_tokens")
    }
    data.update(
        cached_tokens=_count(inputs.get("cached_tokens")),
        cache_write_tokens=_count(inputs.get("cache_write_tokens")),
        reasoning_tokens=_count(outputs.get("reasoning_tokens")),
    )
    i, o, cached, writes = (
        data[k]
        for k in (
            "input_tokens",
            "output_tokens",
            "cached_tokens",
            "cache_write_tokens",
        )
    )
    cost = None
    if i is not None and o is not None:
        valid = (cached is None or cached <= i) and (writes is None or writes <= i)
        valid = valid and (cached is None or writes is None or cached + writes <= i)
        valid = valid and (
            data["total_tokens"] is None or data["total_tokens"] == i + o
        )
        valid = valid and (
            data["reasoning_tokens"] is None or data["reasoning_tokens"] <= o
        )
        if valid:
            base, read, out = (
                (Decimal(2), Decimal("0.20"), Decimal(12))
                if role == "target"
                else (Decimal(1), Decimal("0.05"), Decimal(5))
            )
            # Missing partitions: conservative write pricing, not invented zero counters.
            reads = cached if cached is not None else 0
            written = writes if writes is not None and cached is not None else i - reads
            cost = (
                (i - reads - written) * base
                + reads * read
                + written * base * Decimal("1.25")
                + o * out
            ) / 1_000_000
            if i > 272_000:
                cost = (
                    (
                        (i - reads - written) * base
                        + reads * read
                        + written * base * Decimal("1.25")
                    )
                    * 2
                    + o * out * Decimal("1.5")
                ) / 1_000_000
    return {
        **data,
        "estimated_usd": str(cost) if cost is not None else None,
        "pricing_assumption": "standard-usd-30m-cache-2026-11-06",
        "billing_verified": False,
    }


def _identifier(value: Any, prefix: str) -> str | None:
    if isinstance(value, str) and re.fullmatch(prefix + r"[A-Za-z0-9_-]{1,120}", value):
        return value
    return None


class ProviderTransport(httpx.BaseTransport):
    """Transparent explicit transport. No default transport or offline fallback.

    Use logical() around each existing client call. Retries share that reservation;
    the SDK still owns its original retry policy. Exceptions never persist text.
    """

    def __init__(
        self,
        store: CanaryStore,
        delegate: httpx.BaseTransport,
        *,
        role: Literal["target", "judge"],
    ):
        if not isinstance(delegate, httpx.BaseTransport):
            raise CanaryError("An explicit provider transport is required")
        if store.mode == "offline" and not isinstance(delegate, httpx.MockTransport):
            raise CanaryError(
                "Offline provider I/O requires an explicit mock transport"
            )
        if role not in {"target", "judge"}:
            raise CanaryError("Unknown provider role")
        self.store, self.delegate, self.role = store, delegate, role
        self.active: tuple[str, int] | None = None
        self.attempt = 0

    @contextmanager
    def logical(self, slot: str, number: int = 1) -> Iterator[None]:
        self.store.guard()
        logger_names = {"openai", "httpx", "httpx2", "httpcore", "httpcore2"}
        logger_names.update(
            name
            for name in dict(logging.Logger.manager.loggerDict)
            if name.startswith(
                ("openai.", "httpx.", "httpx2.", "httpcore.", "httpcore2.")
            )
        )
        if any(
            logging.getLogger(name).isEnabledFor(logging.DEBUG) for name in logger_names
        ):
            self.store.stop()
            raise CanaryError(
                "Canary provider calls require SDK and HTTP debug logging disabled"
            )
        allowed = (
            {t.slot for t in TARGET_TURNS}
            if self.role == "target"
            else {f"{j}-{r}" for r in (1, 2) for j in JUDGE_ORDER[:8]}
        )
        if (
            self.active
            or slot not in allowed
            or type(number) is not int
            or not 1 <= number <= (6 if self.role == "target" else 1)
        ):
            self.store.stop()
            raise CanaryError("Provider logical call is outside the authorised roster")
        self.store.write(
            f"reserved-{self.role}-{slot}-{number}",
            {
                "state": "reserved",
                "role": self.role,
                "slot": slot,
                "logical_call": number,
            },
        )
        self.active, self.attempt = (slot, number), 0
        try:
            yield
        except BaseException:  # noqa: BLE001 - interruption leaves the reservation unresolved
            self.store.stop()
            raise CanaryError(
                "Canary provider call failed or was interrupted"
            ) from None
        finally:
            self.active = None

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.store.guard(allow_unknown=True)
        maximum = 3 if self.role == "target" else 1
        if self.active is None or self.attempt >= maximum:
            self.store.stop()
            raise CanaryError("Provider attempt limit reached or call unreserved")
        try:
            body = json.loads(request.content)
            expected_model = TARGET_MODEL if self.role == "target" else JUDGE_MODEL
            expected_tokens = 2000 if self.role == "target" else 8192
            if (
                request.method != "POST"
                or str(request.url) != "https://api.openai.com/v1/responses"
                or body.get("model") != expected_model
                or body.get("max_output_tokens") != expected_tokens
                or body.get("stream", False) is not False
                or body.get("prompt_cache_retention") not in (None, "30m")
                or body.get("service_tier") not in (None, "default", "auto")
            ):
                raise ValueError
        except Exception:  # noqa: BLE001 - never expose malformed request bodies
            self.store.stop()
            raise CanaryError(
                "Provider request differs from approved configuration"
            ) from None
        self.attempt += 1
        slot, number = self.active
        started = perf_counter()
        self.store.event(
            {
                "kind": "provider_dispatch",
                "role": self.role,
                "slot": slot,
                "logical_call": number,
                "attempt": self.attempt,
                "started_at": datetime.now(UTC).isoformat(),
            }
        )
        try:
            response = self.delegate.handle_request(
                request
            )  # Same request object/bytes.
            response.read()
        except BaseException:  # noqa: BLE001 - unknown in-flight liability must stop dispatch
            self.store.event(
                {
                    "kind": "provider_attempt",
                    "role": self.role,
                    "slot": slot,
                    "logical_call": number,
                    "attempt": self.attempt,
                    "retry_index": self.attempt - 1,
                    "error": "transport_ambiguous",
                    "status": None,
                    "request_id": None,
                    "response_id": None,
                    "model": None,
                    "duration_ms": (perf_counter() - started) * 1000,
                    **usage_metadata(None, role=self.role),
                }
            )
            self.store.stop("transport_ambiguous")
            raise CanaryError("Provider transport failed; billing is unknown") from None
        try:
            envelope = response.json()
        except (ValueError, UnicodeError):
            envelope = {}
        envelope = envelope if isinstance(envelope, dict) else {}
        usage = usage_metadata(envelope, role=self.role)
        tier = envelope.get("service_tier")
        if tier not in (None, "default", "auto"):
            usage["estimated_usd"] = (
                None  # Unexpected pricing is unknown, not Standard.
            )
        observed = envelope.get("model")
        provider_error = envelope.get("error")
        provider_error = provider_error if isinstance(provider_error, dict) else {}
        code = provider_error.get("code")
        billing_codes = {
            "project_spend_limit_exceeded",
            "organization_spend_limit_exceeded",
            "organization_usage_limit_exceeded",
            "credit_balance_exhausted",
            "insufficient_quota",
        }
        safe_code = (
            code
            if isinstance(code, str)
            and code
            in billing_codes
            | {
                "rate_limit_exceeded",
                "invalid_api_key",
                "server_error",
                "server_overloaded",
            }
            else None
        )
        status = envelope.get("status")
        safe_status = (
            status
            if isinstance(status, str)
            and status
            in {
                "completed",
                "incomplete",
                "failed",
                "cancelled",
                "queued",
                "in_progress",
            }
            else None
        )
        self.store.event(
            {
                "kind": "provider_attempt",
                "role": self.role,
                "slot": slot,
                "logical_call": number,
                "attempt": self.attempt,
                "retry_index": self.attempt - 1,
                "http_status": response.status_code,
                "status": safe_status,
                "request_id": _identifier(response.headers.get("x-request-id"), "req_"),
                "response_id": _identifier(envelope.get("id"), "resp_"),
                "model": observed if observed == expected_model else None,
                "error": None
                if 200 <= response.status_code < 300
                else safe_code or "provider_http_error",
                "duration_ms": (perf_counter() - started) * 1000,
                **usage,
            }
        )
        if safe_code in billing_codes:
            self.store.stop("provider_failure")
        if 200 <= response.status_code < 300 and (
            status != "completed" or observed not in (None, expected_model)
        ):
            self.store.stop("provider_failure")
            raise CanaryError(
                "Provider response did not complete with the expected model"
            )
        return response  # No body/header mutations; raw envelope is never saved.

    def close(self) -> None:
        self.delegate.close()


class BoundedResponsesClient:
    """Application ResponsesClient decorator; no target implementation import."""

    def __init__(self, delegate: Any, transport: ProviderTransport):
        if transport.role != "target":
            raise CanaryError("Target instrumentation requires a target transport")
        self.delegate, self.transport = delegate, transport
        self.turn = -1
        self.number = 0
        self.previous: str | None = None
        self.transport.store.write(
            "bounded-target-client",
            {
                "max_calls_per_turn": 6,
                "max_attempts_per_call": 3,
                "roster_hash": roster_hash(),
            },
        )

    def create_response(self, request: Any) -> Any:
        self.transport.store.guard()
        if request.previous_response_id is None:
            self.turn += 1
            self.number = 0
            message = (
                request.input
                if isinstance(request.input, str)
                else getattr(request.input[-1], "content", None)
            )
            if (
                self.turn >= len(TARGET_TURNS)
                or message != TARGET_TURNS[self.turn].message
            ):
                self.transport.store.stop()
                raise CanaryError("Target shopper turn is outside the canary roster")
        elif request.previous_response_id != self.previous:
            self.transport.store.stop()
            raise CanaryError("Target continuation identity differs")
        if (
            request.model != TARGET_MODEL
            or request.max_output_tokens != 2000
            or request.reasoning_effort != "low"
        ):
            self.transport.store.stop()
            raise CanaryError("Target inference configuration differs")
        self.number += 1
        with self.transport.logical(TARGET_TURNS[self.turn].slot, self.number):
            result = self.delegate.create_response(request)
            self.previous = result.response_id
            return result
