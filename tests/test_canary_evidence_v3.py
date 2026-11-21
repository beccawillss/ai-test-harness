"""Synthetic public snapshots only; no HTTP, SDK or target construction."""

import copy

import pytest
from test_canary_selection_v3 import preceding, selected

from harness.canary.evidence_v3 import (
    EvidenceProjectionError,
    project_chat,
    project_trace,
    provider_observation,
    restore_trace,
    validate_observation,
)
from harness.canary.inputs import TARGET_MODEL
from harness.canary.selection_acceptance import assess_selection
from harness.core.fingerprints import canonical_json


@pytest.mark.parametrize("slot", ["A1", "B1", "A2", "B2"])
def test_normal_evidence_roundtrip_preserves_assessment_and_inputs(slot):
    raw, previous = selected(slot), preceding(slot)
    before = copy.deepcopy(raw)
    restored = {
        "chat": project_chat(raw["chat"]),
        "trace": restore_trace(project_trace(raw["trace"])),
    }
    restored_previous = {
        s: {
            "chat": project_chat(e["chat"]),
            "trace": restore_trace(project_trace(e["trace"])),
        }
        for s, e in previous.items()
    }
    assert assess_selection(slot, **raw, previous=previous) == assess_selection(
        slot, **restored, previous=restored_previous
    )
    assert raw == before


@pytest.mark.parametrize(
    "code",
    [
        "duplicate_product_id",
        "unknown_product_id",
        "ungrounded_product_id",
        "promotion_nomination_missing",
        "ungrounded_promotion_code",
    ],
)
def test_each_reviewed_business_error_preserves_fail_without_private_content(code):
    slot = "A2" if "promotion" in code else "A1"
    raw, previous = selected(slot), preceding(slot)
    if "promotion" in code:
        raw["trace"]["errors"] = [
            {"code": code, "message": "PRIVATE_DIAGNOSTIC_SECRET"}
        ]
    else:
        raw["trace"]["recommendation_validation"]["validation_errors"] = [
            code + ":PRIVATE_IDENTIFIER_SECRET"
        ]
        raw["trace"]["recommendation_validation"]["all_products_exist"] = (
            code != "unknown_product_id"
        )
    expected = assess_selection(slot, **raw, previous=previous)
    assert expected.status == "FAIL"
    saved = project_trace(raw["trace"])
    actual = assess_selection(
        slot, raw["chat"], restore_trace(saved), previous=previous
    )
    assert actual == expected
    text = canonical_json(saved)
    assert "PRIVATE" not in text
    assert "message" not in saved.get("errors", [{}])[0] if saved["errors"] else True
    assert "validation_errors" not in saved["recommendation_validation"]


@pytest.mark.parametrize(
    "change",
    [
        "unknown",
        "bad_suffix",
        "missing_message",
        "tool_error",
        "correlated",
        "extra_separator",
        "unknown_change",
    ],
)
def test_unknown_or_malformed_errors_cannot_be_promoted_by_redaction(change):
    raw = selected()["trace"]
    if change == "unknown":
        raw["errors"] = [{"code": "PRIVATE_UNKNOWN", "message": "PRIVATE_MESSAGE"}]
    elif change == "bad_suffix":
        raw["recommendation_validation"]["validation_errors"] = [
            "unknown_product_id:PRIVATE text"
        ]
    elif change == "missing_message":
        raw["errors"] = [{"code": "promotion_nomination_missing"}]
    elif change == "tool_error":
        raw["tool_calls"][0]["status"] = "error"
    elif change == "correlated":
        raw["errors"] = [
            {
                "code": "ungrounded_promotion_code",
                "message": "PRIVATE",
                "tool_call_id": "tool-1",
            }
        ]
    elif change == "extra_separator":
        raw["recommendation_validation"]["validation_errors"] = [
            "unknown_product_id:ACC-003:PRIVATE"
        ]
    else:
        raw["constraint_changes"] = [
            {
                "field": "PRIVATE",
                "previous": {"secret": "PRIVATE"},
                "current": "PRIVATE",
            }
        ]
    with pytest.raises(EvidenceProjectionError) as caught:
        project_trace(raw)
    assert "PRIVATE" not in str(caught.value)
    assert caught.value.__suppress_context__


@pytest.mark.parametrize(
    "change", ["unknown_category", "error_prose", "extra", "invalid_change"]
)
def test_saved_projection_must_roundtrip_exactly(change):
    saved = project_trace(selected()["trace"])
    if change == "unknown_category":
        saved["recommendation_validation"]["validation_categories"] = ["PRIVATE"]
    elif change == "error_prose":
        saved["errors"] = [{"code": "ungrounded_promotion_code", "message": "PRIVATE"}]
    elif change == "extra":
        saved["private"] = "PRIVATE"
    else:
        saved["constraint_changes"] = [
            {"field": "colour", "previous": {"PRIVATE": True}, "current": "Moss"}
        ]
    with pytest.raises(EvidenceProjectionError, match="invalid_saved_trace"):
        restore_trace(saved)


def test_unknown_fields_and_untyped_constraint_values_do_not_cross_boundary():
    raw = selected()
    raw["chat"]["authorization"] = "PRIVATE_HEADER"
    raw["trace"]["internal_prompt"] = "PRIVATE_PROMPT"
    raw["trace"]["tool_calls"][0]["arguments"]["hidden"] = "PRIVATE_ARGUMENT"
    raw["trace"]["tool_calls"][0]["result"]["reasoning"] = "PRIVATE_REASONING"
    raw["trace"]["constraint_changes"] = [
        {"field": "maximum_price", "previous": "70.00", "current": "60.00"}
    ]
    text = canonical_json([project_chat(raw["chat"]), project_trace(raw["trace"])])
    assert "PRIVATE" not in text
    raw["trace"]["constraint_changes"][0]["previous"] = {"private": "PRIVATE"}
    with pytest.raises(EvidenceProjectionError):
        project_trace(raw["trace"])


def test_provider_projection_has_only_scalars_and_keeps_estimation_unknowns():
    raw = {
        "id": "resp_test",
        "model": TARGET_MODEL,
        "status": "completed",
        "output": [{"reasoning": "PRIVATE_REASONING"}],
        "error": {"message": "PRIVATE_DIAGNOSTIC"},
        "usage": {"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100},
    }
    value = provider_observation(raw, http_status=200, request_id="req_test")
    validate_observation(value)
    assert value["estimated_usd"] == "0.0037"
    assert value["cache_write_tokens"] is None
    assert value["billing_verified"] is False
    assert "PRIVATE" not in canonical_json(value)
    raw["usage"]["total_tokens"] = 50
    assert provider_observation(raw)["estimated_usd"] is None
    raw["usage"]["input_tokens"] = True
    assert provider_observation(raw)["input_tokens"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("estimated_usd", "-1"),
        ("input_tokens", True),
        ("output_tokens", -1),
        ("extra", "PRIVATE"),
    ],
)
def test_saved_provider_scalars_cannot_invent_cost_or_counters(field, value):
    observed = provider_observation(None)
    observed[field] = value
    with pytest.raises(EvidenceProjectionError):
        validate_observation(observed)


def test_unknown_provider_status_model_and_tier_are_not_echoed():
    observation = provider_observation(
        {
            "status": "PRIVATE",
            "model": "PRIVATE",
            "id": "PRIVATE",
            "service_tier": "PRIVATE",
        },
        request_id="PRIVATE",
        http_status=500,
    )
    assert observation["outcome"] == "operational_error"
    assert observation["estimated_usd"] is None
    assert "PRIVATE" not in canonical_json(observation)
    validate_observation(observation)


def test_error_envelope_cannot_claim_provider_completion():
    raw = {
        "model": TARGET_MODEL,
        "status": "completed",
        "error": {"message": "PRIVATE_DIAGNOSTIC"},
        "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
    }
    saved = provider_observation(raw, http_status=200)
    assert saved["outcome"] == "operational_error"
    assert saved["provider_error_present"] is True
    assert "PRIVATE" not in canonical_json(saved)
    validate_observation(saved)


@pytest.mark.parametrize("status", [408, 409, 429, 500, 502, 503, 599])
@pytest.mark.parametrize(
    "code", [None, "server_error", "server_overloaded", "rate_limit_exceeded"]
)
def test_retryable_http_evidence_has_safe_category_and_independent_unknown_billing(
    status, code
):
    raw = {"error": {"code": code, "message": "PRIVATE_DIAGNOSTIC"}}
    saved = provider_observation(raw, http_status=status)
    assert saved["outcome"] == "retryable_http_failure"
    assert saved["error_category"] == (code or "http_error")
    assert saved["estimated_usd"] is None
    assert "PRIVATE" not in canonical_json(saved)
    validate_observation(saved)


@pytest.mark.parametrize(
    "change",
    [
        "no_error_envelope",
        "malformed_error",
        "unknown_code",
        "unknown_type",
        "billing_type",
        "authentication_type",
        "mismatched_model",
        "unknown_status",
        "incomplete_status",
        "completed_status",
        "unknown_tier",
        "retry_denied",
        "invalid_retry_header",
        "header_true_on_400",
    ],
)
def test_http_status_and_retry_header_cannot_override_terminal_context(change):
    raw = {"error": {"message": "PRIVATE_MESSAGE"}}
    status, directive = 500, "true"
    if change == "no_error_envelope":
        raw = {}
    elif change == "malformed_error":
        raw["error"] = "PRIVATE_ERROR"
    elif change == "unknown_code":
        raw["error"]["code"] = "PRIVATE_CODE"
    elif change == "unknown_type":
        raw["error"]["type"] = "PRIVATE_TYPE"
    elif change == "billing_type":
        raw["error"]["type"] = "insufficient_quota"
    elif change == "authentication_type":
        raw["error"]["type"] = "authentication_error"
    elif change == "mismatched_model":
        raw["model"] = "PRIVATE_MODEL"
    elif change == "unknown_status":
        raw["status"] = "PRIVATE_STATUS"
    elif change == "incomplete_status":
        raw["status"] = "incomplete"
    elif change == "completed_status":
        raw["status"] = "completed"
    elif change == "unknown_tier":
        raw["service_tier"] = "PRIVATE_TIER"
    elif change == "retry_denied":
        directive = "false"
    elif change == "invalid_retry_header":
        directive = "PRIVATE_HEADER"
    else:
        status = 400
    saved = provider_observation(raw, http_status=status, should_retry_header=directive)
    assert saved["outcome"] == "operational_error"
    assert "PRIVATE" not in canonical_json(saved)
    validate_observation(saved)


def test_retryable_failure_zero_usage_is_known_and_attempt_category_is_strict():
    raw = {
        "error": {"code": "server_error"},
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    }
    saved = provider_observation(raw, http_status=500, should_retry_header="true")
    assert saved["outcome"] == "retryable_http_failure"
    assert float(saved["estimated_usd"]) == 0
    validate_observation(saved)
    saved["error_category"] = "none"
    with pytest.raises(EvidenceProjectionError):
        validate_observation(saved)


def test_missing_http_completion_remains_ambiguous_despite_retry_header():
    saved = provider_observation(
        {"error": {"code": "server_error"}}, should_retry_header="true"
    )
    assert saved["outcome"] == "ambiguous_transport"
    assert saved["estimated_usd"] is None
    validate_observation(saved)
