"""Offline public-evidence projection. Diagnostic text never crosses storage.

Restored placeholders are parser compatibility values, never original diagnostics.
Provider observations are supplied scalars, not independently authenticated events.
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, Literal

from pydantic import Field

from harness.canary.inputs import TARGET_MODEL
from harness.canary.recording import usage_metadata
from harness.canary.runtime_v3 import Frozen, _plain
from harness.canary.selection_acceptance import NOMINATION_FAILURES, PROMOTION_FAILURES
from harness.core.fingerprints import canonical_json
from harness.targets._salesagent_contract import (
    ARGUMENTS,
    WARMTH_RESULTS,
    Chat,
    Constraints,
    ToolResult,
    Trace,
)


class EvidenceProjectionError(ValueError):
    """Fixed diagnostics only; suppress external validation details."""


INSTRUMENTATION_PROFILE = "canary-provider-instrumentation-v1"
PROVIDER_FAILURES = frozenset(
    {
        "delegate_error",
        "response_identity_mismatch",
        "provider_error",
        "unknown_usage",
        "spending_pause",
        "operator_stop",
        "operator_pause",
        "interrupted",
        "request_invalid",
        "guard_failed",
        "concurrency_error",
        "recording_failed",
        "transport_ambiguous",
        "cleanup_failed",
    }
)


class AttemptGuards(Frozen):
    """Supplied mock-run facts, never authenticated approval or live authority."""

    checked_at: str
    valid_for_seconds: int = Field(default=30, ge=1, le=60)
    infrastructure_ok: bool = False
    safety_ok: bool = False
    privacy_ok: bool = False
    project_controls_verified: bool = False
    spending_headroom_verified: bool = False
    source_and_fixtures_verified: bool = False
    configuration_verified: bool = False
    evidence_fresh: bool = False
    operator_allows_dispatch: bool = False
    exclusive_reservations_verified: bool = False
    external_unknown_attempts: int = Field(default=0, ge=0)
    estimated_total_usd: str = Field(default="0", pattern=r"^[0-9]+(?:\.[0-9]+)?$")


class DispatchTelemetry(Frozen):
    sdk_retry_count: int = Field(ge=0, le=2)
    started_at: str
    guards: AttemptGuards


class ResultTelemetry(Frozen):
    duration_ms: float = Field(ge=0, allow_inf_nan=False)
    read_complete: bool
    json_state: Literal["valid", "invalid", "unavailable"]
    observed_http_status: int | None = Field(default=None, ge=100, le=599)
    retry_after_state: Literal["absent", "seconds", "date", "invalid"] = "absent"
    retry_after_seconds: float | None = Field(default=None, allow_inf_nan=False)
    retry_after_ms_state: Literal["absent", "valid", "invalid"] = "absent"
    retry_after_ms: float | None = Field(default=None, allow_inf_nan=False)


def checked_telemetry(model: type[Frozen], value: object) -> Any:
    """Revalidate copied/constructed models, suppressing all external diagnostics."""
    try:
        return model.model_validate(_plain(value))
    except Exception:  # noqa: BLE001 - safe projection boundary
        raise EvidenceProjectionError("invalid_instrumentation_telemetry") from None


def validate_dispatch(
    value: object, *, now: datetime | None = None
) -> DispatchTelemetry:
    try:
        data = checked_telemetry(DispatchTelemetry, value)
        started = datetime.fromisoformat(data.started_at)
        checked = datetime.fromisoformat(data.guards.checked_at)
        if started.utcoffset() is None or checked.utcoffset() is None:
            raise ValueError
        reference = started if now is None else now
        age = (reference - checked).total_seconds()
        if not 0 <= age <= data.guards.valid_for_seconds:
            raise ValueError
        if now is not None and not 0 <= (now - started).total_seconds() <= 60:
            raise ValueError
        for item in vars(data.guards).values():
            if type(item) is bool and item is not True:
                raise ValueError
        if data.guards.external_unknown_attempts:
            raise ValueError
        return data
    except Exception:  # noqa: BLE001 - no caller payload in diagnostics
        raise EvidenceProjectionError("invalid_or_stale_attempt_guards") from None


def validate_result(value: object) -> ResultTelemetry:
    data = checked_telemetry(ResultTelemetry, value)
    if (
        (data.read_complete != (data.json_state != "unavailable"))
        or (data.read_complete and data.observed_http_status is None)
        or (data.retry_after_state in {"seconds", "date"})
        != (data.retry_after_seconds is not None)
        or (data.retry_after_ms_state == "valid") != (data.retry_after_ms is not None)
    ):
        raise EvidenceProjectionError("inconsistent_result_telemetry")
    return data


def retry_header_telemetry(headers: Any) -> dict[str, Any]:
    """Retain numeric/date meaning only, never arbitrary header text."""
    result: dict[str, Any] = {}
    for header, key in (
        ("retry-after", "retry_after"),
        ("retry-after-ms", "retry_after_ms"),
    ):
        raw = headers.get(header)
        state, number = "absent", None
        if raw is not None:
            state = "invalid"
            try:
                number = float(raw)
                if not math.isfinite(number):
                    raise ValueError
                state = "seconds" if key == "retry_after" else "valid"
            except (ValueError, TypeError, OverflowError):
                number = None
                if key == "retry_after":
                    try:
                        date = parsedate_to_datetime(raw)
                        if date.utcoffset() is None:
                            raise ValueError
                        number = date.timestamp()
                        state = "date"
                    except (ValueError, TypeError, OverflowError):
                        pass
        result[key + "_state"] = state
        result["retry_after_seconds" if key == "retry_after" else key] = number
    return result


# Same billing exclusions as the frozen historical transport. Unknown codes/types
# are terminal; a retryable HTTP status or retry header cannot override them.
BILLING_ERRORS = frozenset(
    {
        "project_spend_limit_exceeded",
        "organization_spend_limit_exceeded",
        "organization_usage_limit_exceeded",
        "credit_balance_exhausted",
        "insufficient_quota",
    }
)
RETRYABLE_ERRORS = frozenset(
    {"http_error", "server_error", "server_overloaded", "rate_limit_exceeded"}
)


def _error_category(error: object) -> str:
    if error is None:
        return "none"
    if not isinstance(error, dict):
        return "unreviewed"
    code, kind = error.get("code"), error.get("type")
    if any(isinstance(v, str) and v in BILLING_ERRORS for v in (code, kind)):
        return "billing"
    if code == "invalid_api_key" or kind == "authentication_error":
        return "authentication"
    if kind not in (None, "server_error", "rate_limit_error"):
        return "unreviewed"
    if code is None:
        if kind == "server_error":
            return "server_error"
        if kind == "rate_limit_error":
            return "rate_limit_exceeded"
        return "http_error"
    return (
        code
        if isinstance(code, str) and code in RETRYABLE_ERRORS - {"http_error"}
        else "unreviewed"
    )


def _pricing(document: dict[str, Any]) -> None:
    if document.get("pricing") is not None:
        document["pricing"]["base_price"] = document["pricing"].pop("original_price")


def project_chat(raw: object) -> dict[str, Any]:
    try:
        value = Chat.model_validate(raw).model_dump(mode="json")
        _pricing(value)
        canonical_json(value)
        return value
    except Exception:  # noqa: BLE001 - fixed diagnostics at the storage/privacy boundary
        raise EvidenceProjectionError("invalid_public_chat") from None


def project_trace(raw: object) -> dict[str, Any]:
    """Validate diagnostics before discarding prose and rejected-ID suffixes."""
    try:
        parsed = Trace.model_validate(raw)
        categories = []
        for error in parsed.errors:
            if error.code not in PROMOTION_FAILURES or error.tool_call_id is not None:
                raise ValueError
        for text in parsed.recommendation_validation.validation_errors:
            code, separator, identifier = text.partition(":")
            if (
                code not in NOMINATION_FAILURES
                or not separator
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", identifier)
            ):
                raise ValueError
            categories.append(code)
        value = parsed.model_dump(mode="json")
        _pricing(value)
        value["errors"] = [{"code": error.code} for error in parsed.errors]
        validation = value["recommendation_validation"]
        validation.pop("validation_errors")
        validation["validation_categories"] = categories
        for change in parsed.constraint_changes:
            if change.field not in Constraints.model_fields:
                raise ValueError
        value["constraint_changes"] = [
            {
                "field": change.field,
                **{
                    name: Constraints.model_validate({change.field: item}).model_dump(
                        mode="json"
                    )[change.field]
                    for name, item in (
                        ("previous", change.previous),
                        ("current", change.current),
                    )
                },
            }
            for change in parsed.constraint_changes
        ]
        for original, projected in zip(parsed.tool_calls, value["tool_calls"]):
            result = ToolResult.model_validate(original.result)
            if (
                original.status != "success"
                or result.success is not True
                or result.error is not None
                or result.tool_name != original.tool_name
            ):
                raise ValueError
            projected["arguments"] = (
                ARGUMENTS[original.tool_name]
                .model_validate(original.arguments)
                .model_dump(mode="json", exclude_unset=True)
            )
            projected["result"] = {
                "tool_name": result.tool_name,
                "success": True,
                "error": None,
                "data": WARMTH_RESULTS[original.tool_name]
                .model_validate(result.data)
                .model_dump(mode="json"),
            }
        canonical_json(value)
        return value
    except Exception:  # noqa: BLE001 - fixed diagnostics at the storage/privacy boundary
        raise EvidenceProjectionError("invalid_public_trace") from None


def restore_trace(saved: dict[str, Any]) -> dict[str, Any]:
    """Strictly round-trip the projection; never sanitise an unknown category."""
    try:
        import json

        value = json.loads(canonical_json(saved))
        categories = value["recommendation_validation"].pop("validation_categories")
        if not isinstance(categories, list) or any(
            not isinstance(code, str) or code not in NOMINATION_FAILURES
            for code in categories
        ):
            raise ValueError
        value["recommendation_validation"]["validation_errors"] = [
            code + ":REDACTED" for code in categories
        ]
        value["errors"] = [
            {"code": error["code"], "message": "", "tool_call_id": None}
            for error in value["errors"]
            if set(error) == {"code"}
        ]
        if canonical_json(project_trace(value)) != canonical_json(saved):
            raise ValueError
        return value
    except Exception:  # noqa: BLE001 - fixed diagnostics at the storage/privacy boundary
        raise EvidenceProjectionError("invalid_saved_trace") from None


def provider_observation(
    envelope: object,
    *,
    http_status: int | None = None,
    request_id: str | None = None,
    should_retry_header: object = None,
) -> dict[str, Any]:
    """Extract only allowlisted scalars, reusing the frozen target estimator."""
    raw = envelope if isinstance(envelope, dict) else {}

    def identifier(value: object, prefix: str) -> str | None:
        return (
            value
            if isinstance(value, str)
            and re.fullmatch(prefix + r"[A-Za-z0-9_-]{1,120}", value)
            else None
        )

    status = raw.get("status")
    if status is not None and (
        not isinstance(status, str)
        or status
        not in {
            "completed",
            "incomplete",
            "failed",
            "cancelled",
            "queued",
            "in_progress",
        }
    ):
        status = "unreviewed"
    tier = raw.get("service_tier")
    if tier is not None and tier not in ("default", "auto"):
        tier = "unknown"
    http_status = (
        http_status if type(http_status) is int and 100 <= http_status <= 599 else None
    )
    usage = usage_metadata(raw, role="target")
    if tier == "unknown" or http_status is None:
        usage["estimated_usd"] = None
    model = raw.get("model")
    if model is not None and model != TARGET_MODEL:
        model = "unreviewed"
    category = _error_category(raw.get("error"))
    directive = (
        should_retry_header
        if should_retry_header in (None, "true", "false")
        else "unreviewed"
    )
    completed = (
        http_status is not None
        and 200 <= http_status < 300
        and status == "completed"
        and model == TARGET_MODEL
        and raw.get("error") is None
    )
    retryable = (
        http_status is not None
        and (http_status in (408, 409, 429) or http_status >= 500)
        and category in RETRYABLE_ERRORS
        and directive in (None, "true")
        and status in (None, "failed")
        and model in (None, TARGET_MODEL)
        and tier != "unknown"
    )
    outcome = "operational_error"
    if completed:
        outcome = "completed"
    elif http_status is None:
        outcome = "ambiguous_transport"
    elif retryable:
        outcome = "retryable_http_failure"
    return {
        "outcome": outcome,
        "http_status": http_status,
        "provider_status": status,
        "service_tier": tier,
        "model": model,
        "provider_error_present": raw.get("error") is not None,
        "error_category": category,
        "retry_directive": directive,
        "request_id": identifier(request_id, "req_"),
        "response_id": identifier(raw.get("id"), "resp_"),
        **usage,
    }


def validate_observation(value: dict[str, Any]) -> None:
    """Verify saved scalars and cost without accepting raw provider objects."""
    try:
        counters = (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cached_tokens",
            "cache_write_tokens",
            "reasoning_tokens",
        )
        if any(
            value[key] is not None and (type(value[key]) is not int or value[key] < 0)
            for key in counters
        ):
            raise ValueError
        category = value["error_category"]
        if not isinstance(category, str) or category not in RETRYABLE_ERRORS | {
            "none",
            "billing",
            "authentication",
            "unreviewed",
        }:
            raise ValueError
        error = None
        if category == "http_error":
            error = {}
        elif category != "none":
            error = {
                "code": {
                    "billing": "insufficient_quota",
                    "authentication": "invalid_api_key",
                    "unreviewed": "unreviewed",
                }.get(category, category)
            }
        envelope = {
            "model": value["model"],
            "status": value["provider_status"],
            "service_tier": value["service_tier"],
            "id": value["response_id"],
            "error": error,
            "usage": {
                **{key: value[key] for key in counters[:3]},
                "input_tokens_details": {key: value[key] for key in counters[3:5]},
                "output_tokens_details": {
                    "reasoning_tokens": value["reasoning_tokens"]
                },
            },
        }
        if canonical_json(
            provider_observation(
                envelope,
                http_status=value["http_status"],
                request_id=value["request_id"],
                should_retry_header=value["retry_directive"],
            )
        ) != canonical_json(value):
            raise ValueError
    except Exception:  # noqa: BLE001 - fixed diagnostics at the storage/privacy boundary
        raise EvidenceProjectionError("invalid_provider_observation") from None
