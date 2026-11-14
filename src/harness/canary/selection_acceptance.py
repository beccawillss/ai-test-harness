"""Offline v3 public-evidence acceptance, independent of the live controller."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from harness.canary.acceptance import (
    Check,
    _coverage,
    _expected,
    _facts,
    _state,
)
from harness.canary.acceptance import (
    policy_fingerprint as v2_1_fingerprint,
)
from harness.canary.execution_policy import aggregate, execution_fingerprint
from harness.canary.inputs import TARGET_MODEL
from harness.canary.selection_v3 import (
    DEFINITION,
    ORDER,
    TURNS,
    definition_fingerprint,
    roster_fingerprint,
)
from harness.core.fingerprints import fingerprint
from harness.targets._salesagent_contract import (
    ARGUMENTS,
    WARMTH_RESULTS,
    Chat,
    ToolResult,
    Trace,
)

ACCEPTANCE_POLICY = "salesagent-canary-selection-v3"
PROMOTION_FAILURES = frozenset(
    {"promotion_nomination_missing", "ungrounded_promotion_code"}
)
NOMINATION_FAILURES = frozenset(
    {"duplicate_product_id", "unknown_product_id", "ungrounded_product_id"}
)


class EvidenceError(ValueError):
    """Only fixed safe codes; never constructed from external error messages."""


@dataclass(frozen=True)
class SelectionAssessment:
    definition: str
    roster_fingerprint: str
    policy: str
    policy_fingerprint: str
    slot: str
    prerequisites: Check
    factual_evidence: Check
    integration_coverage: Check
    session_isolation: Check
    current_state: Check
    retention: Check | None
    human_prose_review_required: bool = field(default=True, init=False)

    @property
    def structured_state(self) -> Check:
        return aggregate(
            (self.current_state,) + ((self.retention,) if self.retention else ())
        )

    @property
    def checks(self) -> tuple[Check, ...]:
        return (
            self.prerequisites,
            self.factual_evidence,
            self.integration_coverage,
            self.session_isolation,
            self.structured_state,
        )

    @property
    def status(self) -> str:
        return aggregate(self.checks).status


def _normalise(
    slot: str, chat: Any, trace: Any
) -> tuple[dict[str, Any], dict[str, Any], tuple[str, ...]]:
    public = Chat.model_validate(chat).model_dump(mode="json")
    parsed = Trace.model_validate(trace)
    datetime.fromisoformat(parsed.timestamp)
    turn = next(t for t in TURNS if t.slot == slot)
    calls = parsed.tool_calls
    if (
        parsed.trace_id != public["trace_id"]
        or parsed.session_id != public["session_id"]
        or parsed.user_message != turn.message
        or parsed.turn_index != int(slot[1])
        or parsed.model != TARGET_MODEL
        or [c.sequence for c in calls] != list(range(1, len(calls) + 1))
        or len({c.tool_call_id for c in calls}) != len(calls)
        or parsed.token_usage.total_tokens
        != parsed.token_usage.input_tokens + parsed.token_usage.output_tokens
    ):
        raise EvidenceError("public_evidence_correlation_differs")
    business = []
    for error in parsed.errors:
        if error.code not in PROMOTION_FAILURES or error.tool_call_id is not None:
            raise EvidenceError("execution_or_unknown_trace_error")
        business.append("business:" + error.code)
    validation = parsed.recommendation_validation
    rejected = set()
    for value in validation.validation_errors:
        code, separator, identifier = value.partition(":")
        if (
            code not in NOMINATION_FAILURES
            or not separator
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", identifier)
        ):
            raise EvidenceError("unknown_recommendation_validation")
        rejected.add(code)
        business.append("business:" + code)
    if (
        not validation.prices_match_catalogue
        or not validation.urls_match_catalogue
        or not validation.stock_claims_validated
        or validation.all_products_exist != ("unknown_product_id" not in rejected)
    ):
        raise EvidenceError("unexpected_recommendation_validation_flags")
    safe = parsed.model_dump(mode="json")
    for document in (public, safe):
        if document["pricing"] is not None:
            document["pricing"]["base_price"] = document["pricing"].pop(
                "original_price"
            )
    for original, projected in zip(calls, safe["tool_calls"]):
        result = ToolResult.model_validate(original.result)
        if (
            original.status != "success"
            or not result.success
            or result.error is not None
            or result.tool_name != original.tool_name
        ):
            raise EvidenceError("failed_or_inconsistent_tool")
        projected["arguments"] = (
            ARGUMENTS[original.tool_name]
            .model_validate(original.arguments)
            .model_dump(mode="json", exclude_unset=True)
        )
        projected["result"] = {
            "tool_name": original.tool_name,
            "success": True,
            "error": None,
            "data": WARMTH_RESULTS[original.tool_name]
            .model_validate(result.data)
            .model_dump(mode="json"),
        }
    return public, safe, tuple(dict.fromkeys(business))


def _current_state(slot: str, trace: dict[str, Any]) -> Check:
    if slot in ("B1", "B2"):
        return _state(slot, trace, None)
    expected = _expected(slot)
    issues = tuple(
        "resolved_" + field + "_differs"
        for field in ("colour", "size", "maximum_price")
        if str(trace["resolved_constraints"][field]).casefold()
        != expected[field].casefold()
    )
    return Check("FAIL" if issues else "PASS", issues)


def _retention(trace: dict[str, Any], prior: dict[str, Any] | None) -> Check:
    if prior is None:
        return Check("SKIP", ("prior_state_unavailable",))
    expected = _expected("A1")
    missing = tuple(
        "prior_selection_not_established:" + field
        for field in ("colour", "size", "maximum_price")
        if str(prior["resolved_constraints"][field]).casefold()
        != expected[field].casefold()
    )
    if missing:
        return Check("SKIP", missing)
    return _current_state("A2", trace)


def _isolation(
    slot: str, trace: dict[str, Any], previous: dict[str, dict[str, Any]]
) -> Check:
    needed = ORDER[: ORDER.index(slot)]
    missing = tuple(
        "session_evidence_unavailable:" + s for s in needed if s not in previous
    )
    values = [(slot, trace), *previous.items()]
    for index, (left_slot, left) in enumerate(values):
        for right_slot, right in values[index + 1 :]:
            if left["trace_id"] == right["trace_id"] or (
                left["session_id"] == right["session_id"]
            ) != (left_slot[0] == right_slot[0]):
                raise EvidenceError("session_or_trace_identity_differs")
    return Check("SKIP", missing) if missing else Check("PASS")


def assess_selection(
    slot: str,
    chat: Any,
    trace: Any,
    *,
    previous: Mapping[str, dict[str, Any]] | None = None,
) -> SelectionAssessment:
    """Inspect snapshots only. This never catches CanaryError or dispatches I/O."""
    try:
        if slot not in ORDER:
            raise EvidenceError("unknown_target_slot")
        context = previous if previous is not None else {}
        if not isinstance(context, Mapping):
            raise EvidenceError("invalid_previous_evidence")
        if set(context) - set(ORDER[: ORDER.index(slot)]):
            raise EvidenceError("invalid_previous_roster")
        public, safe, business = _normalise(slot, chat, trace)
        prior = {s: _normalise(s, v["chat"], v["trace"])[1] for s, v in context.items()}
        isolation = _isolation(slot, safe, prior)
    except (ValidationError, EvidenceError, ValueError, KeyError, TypeError):
        prerequisites = Check("ERROR", ("invalid_or_unreliable_public_evidence",))
        factual = coverage = isolation = current = Check(
            "SKIP", ("prerequisites_failed",)
        )
        retention = Check("SKIP", ("prerequisites_failed",)) if slot == "A2" else None
    else:
        prerequisites = Check("PASS")
        factual = _facts(slot, public, safe, prior.get("A1"))
        if (
            slot == "A2"
            and "A1" not in prior
            and factual.issues == ("exact_inventory_missing",)
        ):
            factual = Check("SKIP", ("prior_inventory_evidence_unavailable",))
        if business:
            factual = Check("FAIL", tuple(dict.fromkeys((*factual.issues, *business))))
        coverage = _coverage(slot, safe)
        current = _current_state(slot, safe)
        retention = _retention(safe, prior.get("A1")) if slot == "A2" else None
    return SelectionAssessment(
        DEFINITION,
        roster_fingerprint(),
        ACCEPTANCE_POLICY,
        acceptance_fingerprint(),
        slot,
        prerequisites,
        factual,
        coverage,
        isolation,
        current,
        retention,
    )


def acceptance_fingerprint() -> str:
    return fingerprint(
        {
            "acceptance_policy": ACCEPTANCE_POLICY,
            "implementation_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "definition_fingerprint": definition_fingerprint(),
            "execution_fingerprint": execution_fingerprint(),
            "frozen_v2_1_fingerprint": v2_1_fingerprint(),
            "human_prose_review": "required",
        }
    )
