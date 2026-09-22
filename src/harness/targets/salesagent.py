"""Synchronous Sales Agent HTTP adapter; see docs/salesagent-evidence.md."""

from __future__ import annotations

import math
import warnings
from datetime import datetime
from time import perf_counter
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from harness.core.models import TargetResponse, TestCase, ToolCall
from harness.targets._salesagent_contract import (
    ARGUMENTS,
    BUSINESS_ERRORS,
    RESULTS,
    Chat,
    Constraints,
    Tool,
    ToolResult,
    Trace,
)

EVIDENCE_VERSION = "salesagent-evidence-v1"
ADAPTER_VERSION = "1"


class SalesAgentError(RuntimeError):
    """Safe error suitable for the runner's persisted diagnostic string."""


def validate_input(value: Any) -> list[str]:
    if not isinstance(value, dict) or set(value) != {"turns"}:
        raise ValueError("Sales Agent input must contain only turns")
    turns = value["turns"]
    if not isinstance(turns, list) or not turns:
        raise ValueError("turns must be a nonempty list")
    if any(not isinstance(v, str) or not v.strip() or len(v) > 4000 for v in turns):
        raise ValueError("Each shopper turn must contain 1–4000 nonblank characters")
    return list(turns)


def _tool(tool: Tool) -> ToolCall:
    envelope = ToolResult.model_validate(tool.result)
    if envelope.tool_name != tool.tool_name or envelope.success != (
        tool.status == "success"
    ):
        raise ValueError("Inconsistent tool envelope")
    error = envelope.error.code if envelope.error else None
    if not envelope.success:
        if error not in BUSINESS_ERRORS:
            raise SalesAgentError("tool execution unavailable")
        data = None
    else:
        if error is not None or envelope.data is None:
            raise ValueError("Invalid successful tool evidence")
        data = (
            RESULTS[tool.tool_name]
            .model_validate(envelope.data)
            .model_dump(mode="json")
        )
    return ToolCall(
        name=tool.tool_name,
        arguments=ARGUMENTS[tool.tool_name]
        .model_validate(tool.arguments)
        .model_dump(mode="json", exclude_unset=True),
        result=data,
        error=error,
    )


def _changes(trace: Trace) -> list[dict[str, Any]]:
    changes = []
    for change in trace.constraint_changes:
        if change.field not in Constraints.model_fields:
            raise ValueError("Unknown constraint change")
        # Revalidate each value as its public constraint type; never persist an
        # arbitrary object from the otherwise open change fields.
        values = [
            Constraints.model_validate({change.field: v}).model_dump(mode="json")[
                change.field
            ]
            for v in (change.previous, change.current)
        ]
        changes.append(
            {"field": change.field, "previous": values[0], "current": values[1]}
        )
    return changes


class SalesAgentTarget:
    name = "salesagent"
    capabilities = frozenset({"structured", "metadata", "trajectory"})

    def __init__(
        self,
        base_url: str,
        *,
        target_revision: str | None = None,
        client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
        connect_timeout: float = 5,
        read_timeout: float = 120,
        write_timeout: float = 10,
        pool_timeout: float = 5,
    ) -> None:
        try:
            url = httpx.URL(base_url)
            if (
                url.scheme not in {"http", "https"}
                or not url.host
                or url.userinfo
                or url.query
                or url.fragment
            ):
                raise ValueError
        except (ValueError, httpx.InvalidURL):
            raise ValueError(
                "base_url must be an HTTP(S) URL without credentials, query or fragment"
            ) from None
        if client is not None and transport is not None:
            raise ValueError("Supply a client or transport, not both")
        values = (connect_timeout, read_timeout, write_timeout, pool_timeout)
        if any(isinstance(v, bool) or not math.isfinite(v) or v <= 0 for v in values):
            raise ValueError("Timeouts must be positive finite seconds")
        self.base_url = str(url).rstrip("/")
        self.target_revision = target_revision or "unknown"
        self.timeout = httpx.Timeout(
            connect=connect_timeout,
            read=read_timeout,
            write=write_timeout,
            pool=pool_timeout,
        )
        self._owned = client is None
        self._client = client or httpx.Client(
            transport=transport, trust_env=False, follow_redirects=False
        )

    @property
    def configuration(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "target_revision": self.target_revision,
            "adapter_version": ADAPTER_VERSION,
            "evidence_schema_version": EVIDENCE_VERSION,
            "http_contract_version": "1.0.0",
            "timeouts": self.timeout.as_dict(),
        }

    def close(self) -> None:
        if self._owned:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001 - sanitize adapter boundary failures
                warnings.warn(
                    "Sales Agent HTTP client cleanup failed",
                    RuntimeWarning,
                    stacklevel=2,
                )

    def _request(
        self, method: str, path: str, body: dict[str, str] | None = None
    ) -> Any:
        # Construct directly to avoid injected client defaults (cookies, params,
        # authentication headers) becoming part of the evaluation input.
        request = httpx.Request(
            method,
            self.base_url + path,
            json=body,
            extensions={"timeout": self.timeout.as_dict()},
        )
        try:
            response = self._client.send(request, auth=None, follow_redirects=False)
            if not 200 <= response.status_code < 300:
                raise SalesAgentError(f"HTTP status {response.status_code}")
            return response.json()
        except httpx.TimeoutException:
            raise SalesAgentError("HTTP timeout") from None
        except httpx.HTTPError:
            raise SalesAgentError("HTTP unavailable") from None
        except (ValueError, UnicodeError):
            raise SalesAgentError("malformed JSON") from None

    def invoke(self, case: TestCase) -> TargetResponse:
        messages = validate_input(case.input)
        started = perf_counter()
        session: str | None = None
        seen: set[str] = set()
        turns: list[dict[str, Any]] = []
        trajectory: list[ToolCall] = []
        for index, message in enumerate(messages):
            phase = "chat"
            try:
                body = {"message": message}
                if session is not None:
                    body["session_id"] = session
                chat = Chat.model_validate(self._request("POST", "/api/v1/chat", body))
                if session is not None and chat.session_id != session:
                    raise SalesAgentError("session inconsistency")
                session = chat.session_id
                if chat.trace_id in seen or chat.trace_id in {".", ".."}:
                    raise SalesAgentError("trace inconsistency")
                seen.add(chat.trace_id)
                phase = "trace"
                trace = Trace.model_validate(
                    self._request(
                        "GET", "/api/v1/traces/" + quote(chat.trace_id, safe="")
                    )
                )
                datetime.fromisoformat(trace.timestamp)
                if (
                    trace.trace_id != chat.trace_id
                    or trace.session_id != session
                    or trace.turn_index != index + 1
                    or trace.user_message != message
                ):
                    raise SalesAgentError("trace correlation inconsistency")
                if [t.sequence for t in trace.tool_calls] != list(
                    range(1, len(trace.tool_calls) + 1)
                ):
                    raise SalesAgentError("tool sequence inconsistency")
                if any(e.code not in BUSINESS_ERRORS for e in trace.errors):
                    raise SalesAgentError("trace execution unavailable")
                calls = [_tool(t) for t in trace.tool_calls]
                trajectory.extend(calls)
                structured = chat.model_dump(
                    mode="json", include={"recommendations", "promotion", "pricing"}
                )
                structured["recommendation_product_ids"] = [
                    r.product_id for r in chat.recommendations
                ]
                evidence = trace.model_dump(
                    mode="json",
                    include={
                        "resolved_constraints",
                        "recommendation_validation",
                        "recommended_product_ids",
                        "promotion",
                        "pricing",
                    },
                )
                # Validation messages can include arbitrary diagnostic prose.
                evidence["recommendation_validation"].pop("validation_errors")
                evidence["recommendation_validation"]["validation_error_count"] = len(
                    trace.recommendation_validation.validation_errors
                )
                evidence["constraint_changes"] = _changes(trace)
                evidence["grounded_product_ids"] = [
                    product["product_id"]
                    for call in calls
                    if call.error is None and isinstance(call.result, dict)
                    for product in (
                        call.result["products"]
                        if call.name == "search_products"
                        else [call.result]
                        if call.name == "get_product"
                        else []
                    )
                ]
                evidence["errors"] = [{"code": e.code} for e in trace.errors]
                turns.append(
                    {
                        "index": index,
                        "input": message,
                        "output": chat.message,
                        "structured": structured,
                        "trajectory": [c.model_dump(mode="json") for c in calls],
                        "evidence": evidence,
                        "metadata": {
                            **trace.model_dump(
                                mode="json",
                                include={
                                    "trace_id",
                                    "turn_index",
                                    "model",
                                    "prompt_version",
                                    "token_usage",
                                    "latency_ms",
                                },
                            ),
                            "tools": [
                                t.model_dump(
                                    mode="json",
                                    include={
                                        "sequence",
                                        "tool_call_id",
                                        "status",
                                        "duration_ms",
                                    },
                                )
                                for t in trace.tool_calls
                            ],
                        },
                    }
                )
            except SalesAgentError as exc:
                raise SalesAgentError(f"turn {index + 1} {phase}: {exc}") from None
            except (ValidationError, ValueError, TypeError, KeyError, ArithmeticError):
                raise SalesAgentError(
                    f"turn {index + 1} {phase}: malformed contract evidence"
                ) from None
            except Exception:  # noqa: BLE001 - sanitize adapter boundary failures
                raise SalesAgentError(
                    f"turn {index + 1} {phase}: adapter execution unavailable"
                ) from None
        return TargetResponse(
            output=turns[-1]["output"],
            structured={**turns[-1]["structured"], "turns": turns},
            trajectory=trajectory,
            latency_ms=(perf_counter() - started) * 1000,
            metadata={
                "evidence_schema_version": EVIDENCE_VERSION,
                "adapter_version": ADAPTER_VERSION,
                "target_revision": self.target_revision,
                "target_revision_source": "operator"
                if self.target_revision != "unknown"
                else "unknown",
                "trace_ids": [t["metadata"]["trace_id"] for t in turns],
                "models": sorted({t["metadata"]["model"] for t in turns}),
                "prompt_versions": sorted(
                    {t["metadata"]["prompt_version"] for t in turns}
                ),
                "token_usage": {
                    k: sum(t["metadata"]["token_usage"][k] for t in turns)
                    for k in ("input_tokens", "output_tokens", "total_tokens")
                },
                "latency_scope": "whole_invocation_including_trace_fetches",
            },
        )
