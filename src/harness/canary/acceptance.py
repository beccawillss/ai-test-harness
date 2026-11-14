"""Proposed offline-only canary acceptance; never dispatches or changes C1.

These checks establish support for the canary's declared commerce facts, not
arbitrary prose truthfulness. Shopper prose still requires human review.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from harness.canary.driver import _observations, _trace
from harness.canary.inputs import (
    TARGET_MODEL,
    TARGET_REVISION,
    TARGET_TURNS,
    roster_hash,
)
from harness.canary.recording import CanaryError
from harness.core.fingerprints import fingerprint
from harness.targets._salesagent_contract import ARGUMENTS, WARMTH_RESULTS, Chat, Trace

ORIGINAL_POLICY = "salesagent-canary-c1-v1"
PROPOSED_POLICY = "salesagent-canary-acceptance-v2.1"
Status = Literal["PASS", "FAIL", "ERROR", "SKIP"]


@dataclass(frozen=True)
class Check:
    status: Status
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class Acceptance:
    policy: str
    policy_fingerprint: str
    input_roster_hash: str
    slot: str
    prerequisites: Check
    factual_evidence: Check
    integration_coverage: Check
    structured_state: Check

    @property
    def status(self) -> Status:
        checks = (
            self.prerequisites,
            self.factual_evidence,
            self.integration_coverage,
            self.structured_state,
        )
        if any(c.status == "ERROR" for c in checks):
            return "ERROR"
        if any(c.status == "FAIL" for c in checks):
            return "FAIL"
        return "PASS" if all(c.status == "PASS" for c in checks) else "SKIP"


def policy_fingerprint(policy: str = PROPOSED_POLICY) -> str:
    """Bind assertions/code and schemas separately from the historical roster."""
    if policy not in (ORIGINAL_POLICY, PROPOSED_POLICY):
        raise ValueError("Unknown canary acceptance policy")
    implementation = (
        inspect.getsource(_observations).encode()
        if policy == ORIGINAL_POLICY
        else Path(__file__).read_bytes()
    )
    contracts: tuple[type[BaseModel], ...] = (
        Chat,
        Trace,
        *ARGUMENTS.values(),
        *WARMTH_RESULTS.values(),
    )
    return fingerprint(
        {
            "policy": policy,
            "implementation_sha256": sha256(implementation).hexdigest(),
            "normalization_sha256": sha256(
                inspect.getsource(_trace).encode()
            ).hexdigest(),
            "contracts": [c.model_json_schema() for c in contracts],
            "input_roster_hash": roster_hash(),
            "target_model": TARGET_MODEL,
            "target_revision": TARGET_REVISION,
            "scope": "offline-public-evidence-only; human prose review required",
        }
    )


def _normalise(
    slot: str, chat: Any, trace: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    turns = {t.slot: t for t in TARGET_TURNS}
    if slot not in turns:
        raise ValueError("Unknown canary target slot")
    public = Chat.model_validate(chat).model_dump(mode="json")
    if public["pricing"] is not None:
        public["pricing"]["base_price"] = public["pricing"].pop("original_price")
    safe = _trace(trace)  # Preserve C1's schema/tool/error/validation prerequisites.
    calls = safe["tool_calls"]
    if (
        safe["trace_id"] != public["trace_id"]
        or safe["session_id"] != public["session_id"]
        or safe["user_message"] != turns[slot].message
        or safe["turn_index"] != int(slot[1])
        or safe["model"] != TARGET_MODEL
        or [c["sequence"] for c in calls] != list(range(1, len(calls) + 1))
        or len({c["tool_call_id"] for c in calls}) != len(calls)
    ):
        raise CanaryError("Canary public evidence correlation differs")
    return public, safe


def assess_original_turn(slot: str, chat: Any, trace: Any) -> Check:
    """Apply the unmodified monolithic C1 assertions to a saved public exchange."""
    try:
        public, safe = _normalise(slot, chat, trace)
    except (ValidationError, CanaryError, ValueError, KeyError, TypeError):
        return Check("ERROR", ("invalid_public_evidence",))
    try:
        _observations(slot, public, safe)
    except CanaryError:
        return Check("FAIL", ("original_c1_acceptance_failed",))
    return Check("PASS")


def _check(issues: list[str]) -> Check:
    return Check("FAIL" if issues else "PASS", tuple(dict.fromkeys(issues)))


def _expected(slot: str) -> dict[str, Any]:
    if slot == "B2":
        return {
            "product_id": "ACC-001",
            "name": "Summit Rib Beanie",
            "product_url": "/products/summit-rib-beanie",
            "price": "22.00",
            "colour": "Rust",
            "size": "One Size",
            "stock": 6,
            "maximum_price": "25.00",
        }
    return {
        "product_id": "ACC-003",
        "name": "Tern Roll-Top Day Pack",
        "product_url": "/products/tern-roll-top-pack",
        "price": "55.00",
        "colour": "Moss",
        "size": "20L",
        "stock": 5,
        "maximum_price": "60.00",
    }


def _coverage(slot: str, trace: dict[str, Any]) -> Check:
    required = (
        ()
        if slot == "B1"
        else ("get_product", "validate_discount")
        if slot == "A2"
        else ("search_products", "get_product", "check_inventory")
    )
    names = {c["tool_name"] for c in trace["tool_calls"]}
    issues = ["not_exercised:" + name for name in required if name not in names]
    if "get_product" in required and "get_product" in names:
        pid = _expected(slot)["product_id"]
        if not any(
            c["tool_name"] == "get_product"
            and c["arguments"]["product_id"] == pid
            and c["result"]["data"]["product_id"] == pid
            for c in trace["tool_calls"]
        ):
            issues.append("target_product_not_exercised:get_product")
    return _check(issues)


def _state(slot: str, trace: dict[str, Any], prior: dict[str, Any] | None) -> Check:
    constraints = trace["resolved_constraints"]
    if slot == "B1":
        return _check(
            ["fresh_session_has_preferences"]
            if any(v is not None and v != [] for v in constraints.values())
            else []
        )
    expected = _expected(slot)
    issues = []
    unavailable = []
    if constraints["maximum_price"] != expected["maximum_price"]:
        issues.append("resolved_maximum_price_differs")
    for field in ("colour", "size"):
        # A1/B2 enquire about availability; neither explicitly selects a saved
        # preference. A2 explicitly says to keep the named colour and capacity.
        if slot != "A2" and constraints[field] is None:
            continue
        if str(constraints[field]).casefold() != expected[field].casefold():
            issues.append("resolved_" + field + "_differs")
    if slot == "A2":
        if prior is None:
            unavailable.append("prior_state_unavailable")
        else:
            previous = prior["resolved_constraints"]
            if previous["maximum_price"] != expected["maximum_price"]:
                issues.append("prior_maximum_price_differs")
            for field in ("colour", "size"):
                if previous[field] is None:
                    unavailable.append("prior_" + field + "_not_established")
                elif str(previous[field]).casefold() != expected[field].casefold():
                    issues.append("prior_" + field + "_differs")
    if not issues and unavailable:
        return Check("SKIP", tuple(unavailable))
    return _check(issues)


def _facts(
    slot: str, chat: dict[str, Any], trace: dict[str, Any], prior: dict[str, Any] | None
) -> Check:
    issues: list[str] = []
    if chat["promotion"] != trace["promotion"] or chat["pricing"] != trace["pricing"]:
        issues.append("chat_trace_commerce_differs")
    if slot == "B1":
        if chat["recommendations"] or chat["promotion"] or chat["pricing"]:
            issues.append("fresh_session_has_commerce_claims")
        if trace["recommended_product_ids"]:
            issues.append("fresh_session_has_product_nominations")
        return _check(issues)
    expected = _expected(slot)
    pid = expected["product_id"]
    products: list[dict[str, Any]] = []
    for call in trace["tool_calls"]:
        data = call["result"]["data"]
        if call["tool_name"] == "search_products":
            if data["count"] != len(data["products"]):
                issues.append("search_count_differs")
            products.extend(p for p in data["products"] if p["product_id"] == pid)
        elif call["tool_name"] == "get_product":
            if call["arguments"]["product_id"] != data["product_id"]:
                issues.append("product_arguments_result_differ")
            if data["product_id"] == pid:
                products.append(data)
    if not products:
        issues.append("authoritative_product_missing")
    for product in products:
        if product != products[0]:
            issues.append("contradictory_product_evidence")
        if any(product[k] != expected[k] for k in ("name", "price", "product_url")):
            issues.append("product_facts_differ")
        if not any(
            all(v[k] == expected[k] for k in ("colour", "size", "stock"))
            for v in product["variants"]
        ):
            issues.append("catalogue_variant_differs")
        if slot != "B2" and (
            "walking" not in product["activities"]
            or "water-resistant" not in product["features"]
            or product["waterproof_rating"] != "water-resistant"
        ):
            issues.append("pack_suitability_not_supported")
        if slot == "B2" and (
            "warm" not in product["features"] or product["warmth"] != "medium"
        ):
            issues.append("beanie_warmth_not_supported")
    recommendations = chat["recommendations"]
    if (
        len(recommendations) != 1
        or recommendations[0]["product_id"] != pid
        or trace["recommended_product_ids"] != [pid]
    ):
        issues.append("recommendations_differ")
    for recommendation in recommendations:
        if (
            any(
                recommendation[k] != expected[k]
                for k in ("product_id", "name", "price", "product_url")
            )
            or recommendation["availability"] != "in_stock"
        ):
            issues.append("displayed_product_facts_differ")
        variant = recommendation["matched_variant"]
        if variant is not None and any(
            variant[k] != expected[k] for k in ("colour", "size", "stock")
        ):
            issues.append("displayed_variant_differs")
    inventory_calls = [
        c
        for source in (trace, prior if slot == "A2" else None)
        if source is not None
        for c in source["tool_calls"]
        if c["tool_name"] == "check_inventory"
        and (
            c["arguments"]["product_id"] == pid
            or c["result"]["data"]["product_id"] == pid
        )
    ]
    exact_inventory = []
    for call in inventory_calls:
        data, args = call["result"]["data"], call["arguments"]
        if any(args[k] != data[k] for k in ("product_id", "colour", "size")):
            issues.append("inventory_arguments_result_differ")
        if all(args[k] == expected[k] for k in ("colour", "size")):
            exact_inventory.append(data)
            if (
                data["stock"] != expected["stock"]
                or data["available"] is not True
                or data["status"] != "in_stock"
            ):
                issues.append("contradictory_inventory_evidence")
    if not exact_inventory:
        issues.append("exact_inventory_missing")
    if slot == "A2":
        validated = [
            c for c in trace["tool_calls"] if c["tool_name"] == "validate_discount"
        ]
        if not validated or any(
            c["arguments"]["code"] != "WELCOME10"
            or c["result"]["data"]["code"] != "WELCOME10"
            or c["result"]["data"]["valid"] is not True
            or c["result"]["data"]["discount_percent"] != "10.00"
            for c in validated
        ):
            issues.append("promotion_evidence_missing_or_contradictory")
        if not chat["promotion"] or any(
            chat["promotion"][k] != value
            for k, value in {
                "code": "WELCOME10",
                "valid": True,
                "discount_percent": "10.00",
            }.items()
        ):
            issues.append("displayed_promotion_differs")
        quote = {
            "product_id": pid,
            "base_price": "55.00",
            "final_price": "49.50",
            "currency": "GBP",
            "discount_code": "WELCOME10",
            "discount_percent": "10.00",
        }
        if chat["pricing"] != quote:
            issues.append("displayed_quote_differs")
    elif chat["promotion"] is not None or (
        chat["pricing"] is not None
        and (
            chat["pricing"]["product_id"] != pid
            or chat["pricing"]["base_price"] != expected["price"]
            or chat["pricing"]["final_price"] != expected["price"]
            or chat["pricing"]["discount_code"] is not None
            or chat["pricing"]["discount_percent"] not in (None, "0.00")
        )
    ):
        issues.append("unrequested_or_incorrect_pricing")
    return _check(issues)


def assess_turn(
    slot: str,
    chat: Any,
    trace: Any,
    *,
    prior_a1: dict[str, Any] | None = None,
) -> Acceptance:
    """Inspect data only. A2 needs prior state to establish retention.

    No client, store, server, SDK, credential lookup or paid replay is created.
    All three dimensions gate aggregate compatibility, including tool coverage.
    Exact inventory can come from the same-session A1 or current A2 evidence.
    """
    prior = None
    try:
        public, safe = _normalise(slot, chat, trace)
        if prior_a1 is not None:
            if slot != "A2":
                raise ValueError("Prior A1 evidence is only valid for A2")
            _, prior = _normalise("A1", prior_a1["chat"], prior_a1["trace"])
            if (
                prior["session_id"] != safe["session_id"]
                or prior["trace_id"] == safe["trace_id"]
            ):
                raise CanaryError("Prior A1 evidence has different identity")
    except (ValidationError, CanaryError, ValueError, KeyError, TypeError):
        prerequisites = Check("ERROR", ("invalid_public_evidence",))
        factual = coverage = state = Check("SKIP", ("prerequisites_failed",))
    else:
        prerequisites = Check("PASS")
        factual = _facts(slot, public, safe, prior)
        coverage = _coverage(slot, safe)
        state = _state(slot, safe, prior)
    return Acceptance(
        PROPOSED_POLICY,
        policy_fingerprint(),
        roster_hash(),
        slot,
        prerequisites,
        factual,
        coverage,
        state,
    )
