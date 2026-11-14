"""Offline policy checks use invented public exchanges, never provider clients."""

import copy
from dataclasses import asdict

import pytest

from harness.canary.acceptance import (
    ORIGINAL_POLICY,
    PROPOSED_POLICY,
    assess_original_turn,
    assess_turn,
    policy_fingerprint,
)
from harness.canary.driver import _observations
from harness.canary.inputs import TARGET_MODEL, TARGET_TURNS, roster_hash
from harness.canary.recording import CanaryError

HISTORICAL_ROSTER = "e8778ce74a270e6efbe490198d01e8b9c50bcc43387a02bff5f00b42304d5794"


def exchange(slot="A1", *, product_tool="both"):
    """Independent synthetic commerce facts; no live evidence is copied here."""
    b2 = slot == "B2"
    pid = "ACC-001" if b2 else "ACC-003"
    variant = {
        "colour": "Rust" if b2 else "Moss",
        "size": "One Size" if b2 else "20L",
        "stock": 6 if b2 else 5,
    }
    product = {
        "product_id": pid,
        "name": "Summit Rib Beanie" if b2 else "Tern Roll-Top Day Pack",
        "price": "22.00" if b2 else "55.00",
        "currency": "GBP",
        "product_url": "/products/summit-rib-beanie"
        if b2
        else "/products/tern-roll-top-pack",
        "category": "accessory",
        "activities": ["walking", "camping"] if b2 else ["walking", "paddling"],
        "weather": ["cold", "dry"] if b2 else ["moderate-rain", "spray"],
        "features": ["warm", "soft"] if b2 else ["roll-top", "water-resistant"],
        "waterproof_rating": "none" if b2 else "water-resistant",
        "warmth": "medium" if b2 else "none",
        "variants": [variant],
        "total_stock": variant["stock"],
    }
    calls = []

    def tool(name, arguments, data):
        index = len(calls) + 1
        calls.append(
            {
                "sequence": index,
                "tool_call_id": f"synthetic-{slot}-{index}",
                "tool_name": name,
                "arguments": arguments,
                "result": {
                    "tool_name": name,
                    "success": True,
                    "error": None,
                    "data": data,
                },
                "status": "success",
                "duration_ms": 1,
            }
        )

    promotion, pricing = None, None
    if slot != "B1":
        if product_tool in ("both", "search_products"):
            tool(
                "search_products",
                {},
                {"products": [copy.deepcopy(product)], "count": 1},
            )
        if product_tool in ("both", "get_product"):
            tool("get_product", {"product_id": pid}, copy.deepcopy(product))
        if slot != "A2":
            tool(
                "check_inventory",
                {
                    "product_id": pid,
                    "colour": variant["colour"],
                    "size": variant["size"],
                },
                {"product_id": pid, **variant, "available": True, "status": "in_stock"},
            )
        else:
            promotion = {
                "code": "WELCOME10",
                "valid": True,
                "discount_percent": "10.00",
                "reason": "active",
            }
            pricing = {
                "product_id": pid,
                "base_price": "55.00",
                "final_price": "49.50",
                "currency": "GBP",
                "discount_code": "WELCOME10",
                "discount_percent": "10.00",
            }
            tool("validate_discount", {"code": "WELCOME10"}, copy.deepcopy(promotion))
    recommendation = {
        k: product[k]
        for k in ("product_id", "name", "price", "currency", "product_url")
    }
    recommendation.update(availability="in_stock", matched_variant=None)
    chat = {
        "session_id": "synthetic-" + slot[0],
        "trace_id": "synthetic-" + slot,
        "message": "Synthetic shopper answer requiring independent prose review.",
        "recommendations": [] if slot == "B1" else [recommendation],
        "promotion": copy.deepcopy(promotion),
        "pricing": copy.deepcopy(pricing),
    }
    trace = {
        "session_id": chat["session_id"],
        "trace_id": chat["trace_id"],
        "timestamp": "2026-11-14T00:00:00Z",
        "turn_index": int(slot[1]),
        "user_message": next(t.message for t in TARGET_TURNS if t.slot == slot),
        "model": TARGET_MODEL,
        "prompt_version": "synthetic",
        "resolved_constraints": {}
        if slot == "B1"
        else {
            "colour": variant["colour"],
            "size": variant["size"],
            "maximum_price": "25.00" if b2 else "60.00",
        },
        "constraint_changes": [],
        "tool_calls": calls,
        "recommendation_validation": {
            "all_products_exist": True,
            "prices_match_catalogue": True,
            "urls_match_catalogue": True,
            "stock_claims_validated": True,
            "validation_errors": [],
        },
        "recommended_product_ids": [] if slot == "B1" else [pid],
        "promotion": promotion,
        "pricing": pricing,
        "latency_ms": 1,
        "token_usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        "errors": [],
    }
    return {"chat": chat, "trace": trace}


def remove_tool(saved, name):
    calls = saved["trace"]["tool_calls"]
    calls[:] = [c for c in calls if c["tool_name"] != name]
    for index, call in enumerate(calls, 1):
        call["sequence"] = index


def tool_data(saved, name):
    return next(
        c["result"]["data"]
        for c in saved["trace"]["tool_calls"]
        if c["tool_name"] == name
    )


@pytest.mark.parametrize("slot", ["A1", "B1", "A2", "B2"])
def test_both_policies_accept_complete_synthetic_evidence(slot):
    saved = exchange(slot)
    prior = exchange("A1") if slot == "A2" else None
    assert assess_original_turn(slot, **saved).status == "PASS"
    report = assess_turn(slot, **saved, prior_a1=prior)
    assert report.status == "PASS"
    assert all(
        asdict(report)[name]["status"] == "PASS"
        for name in (
            "prerequisites",
            "factual_evidence",
            "integration_coverage",
            "structured_state",
        )
    )


@pytest.mark.parametrize("slot", ["A1", "A2", "B2"])
@pytest.mark.parametrize("product_tool", ["search_products", "get_product"])
def test_authoritative_product_paths_are_independent_of_coverage(slot, product_tool):
    saved = exchange(slot, product_tool=product_tool)
    report = assess_turn(slot, **saved, prior_a1=exchange() if slot == "A2" else None)
    assert report.factual_evidence.status == "PASS"
    assert report.structured_state.status == "PASS"
    missing = product_tool == "search_products" or slot != "A2"
    assert report.integration_coverage.status == ("FAIL" if missing else "PASS")
    assert report.status == ("FAIL" if missing else "PASS")


def test_original_policy_and_historical_roster_remain_unchanged():
    saved = exchange(product_tool="search_products")
    with pytest.raises(CanaryError, match="Expected canary tool coverage is missing"):
        _observations("A1", **saved)
    assert assess_original_turn("A1", **saved).status == "FAIL"
    saved["trace"]["resolved_constraints"] = {"maximum_price": "60.00"}
    report = assess_turn("A1", **saved)
    assert report.factual_evidence.status == "PASS"
    assert report.integration_coverage.issues == ("not_exercised:get_product",)
    assert report.structured_state.status == "PASS"
    assert report.structured_state.issues == ()
    assert report.status == "FAIL"
    assert roster_hash() == HISTORICAL_ROSTER == report.input_roster_hash
    assert ORIGINAL_POLICY != PROPOSED_POLICY
    assert policy_fingerprint(ORIGINAL_POLICY) != policy_fingerprint()
    with pytest.raises(ValueError, match="Unknown"):
        policy_fingerprint("unreviewed")


@pytest.mark.parametrize("tool", ["both", "search_products", "get_product"])
def test_missing_authoritative_evidence_does_not_fall_back_to_displayed_facts(tool):
    saved = exchange(product_tool=tool)
    remove_tool(saved, "search_products")
    remove_tool(saved, "get_product")
    report = assess_turn("A1", **saved)
    assert "authoritative_product_missing" in report.factual_evidence.issues
    assert report.structured_state.status == "PASS"
    assert report.status == "FAIL"


@pytest.mark.parametrize(
    ("field", "value", "issue"),
    [
        ("price", "54.99", "product_facts_differ"),
        ("name", "Invented pack", "product_facts_differ"),
        ("product_url", "/invented", "product_facts_differ"),
        ("activities", [], "pack_suitability_not_supported"),
        ("features", [], "pack_suitability_not_supported"),
        ("waterproof_rating", "high", "pack_suitability_not_supported"),
        ("variants", [], "catalogue_variant_differs"),
    ],
)
def test_incorrect_search_facts_fail_without_get_product(field, value, issue):
    saved = exchange(product_tool="search_products")
    tool_data(saved, "search_products")["products"][0][field] = value
    report = assess_turn("A1", **saved)
    assert issue in report.factual_evidence.issues
    assert report.status == "FAIL"


def test_contradictory_product_sources_fail_even_with_one_correct_result():
    saved = exchange()
    tool_data(saved, "get_product")["price"] = "56.00"
    report = assess_turn("A1", **saved)
    assert "contradictory_product_evidence" in report.factual_evidence.issues
    assert report.integration_coverage.status == "PASS"


def test_a1_unrelated_get_product_does_not_cover_the_requested_product_lookup():
    saved = exchange()
    unrelated = copy.deepcopy(tool_data(exchange("B2"), "get_product"))
    lookup = next(
        c for c in saved["trace"]["tool_calls"] if c["tool_name"] == "get_product"
    )
    lookup["arguments"] = {"product_id": unrelated["product_id"]}
    lookup["result"]["data"] = unrelated
    assert assess_original_turn("A1", **saved).status == "FAIL"
    report = assess_turn("A1", **saved)
    assert report.factual_evidence.status == "PASS"
    assert report.integration_coverage.status == "FAIL"
    assert report.integration_coverage.issues == (
        "target_product_not_exercised:get_product",
    )
    assert report.status == "FAIL"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "Wrong"),
        ("price", "1.00"),
        ("product_url", "/wrong"),
        ("product_id", "ACC-002"),
        ("availability", "out_of_stock"),
    ],
)
def test_displayed_product_must_match_evidence(field, value):
    saved = exchange()
    saved["chat"]["recommendations"][0][field] = value
    assert assess_turn("A1", **saved).factual_evidence.status == "FAIL"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("stock", 0),
        ("available", False),
        ("status", "out_of_stock"),
        ("colour", "Black"),
        ("size", "10L"),
        ("product_id", "ACC-002"),
    ],
)
def test_inventory_cannot_be_missing_or_contradictory(field, value):
    saved = exchange()
    tool_data(saved, "check_inventory")[field] = value
    assert assess_turn("A1", **saved).factual_evidence.status == "FAIL"


def test_missing_inventory_is_not_inferred_from_product_stock_or_matched_variant():
    saved = exchange()
    saved["chat"]["recommendations"][0]["matched_variant"] = {
        "colour": "Moss",
        "size": "20L",
        "stock": 5,
    }
    remove_tool(saved, "check_inventory")
    report = assess_turn("A1", **saved)
    assert "exact_inventory_missing" in report.factual_evidence.issues


def test_contradictory_second_inventory_is_not_hidden_by_correct_first_result():
    saved = exchange()
    call = copy.deepcopy(saved["trace"]["tool_calls"][-1])
    call.update(sequence=4, tool_call_id="contradictory")
    call["result"]["data"]["stock"] = 2
    saved["trace"]["tool_calls"].append(call)
    assert (
        "contradictory_inventory_evidence"
        in assess_turn("A1", **saved).factual_evidence.issues
    )


@pytest.mark.parametrize("field", ["colour", "size"])
def test_variant_state_is_independent_of_correct_tools_and_facts(field):
    saved = exchange()
    saved["trace"]["resolved_constraints"][field] = "Wrong"
    report = assess_turn("A1", **saved)
    assert (
        report.factual_evidence.status == report.integration_coverage.status == "PASS"
    )
    assert report.structured_state.status == report.status == "FAIL"


def test_a2_requires_prior_state_not_current_prompt_reconstruction():
    saved, prior = exchange("A2"), exchange()
    prior["trace"]["resolved_constraints"] = {"maximum_price": "60.00"}
    report = assess_turn("A2", **saved, prior_a1=prior)
    assert report.factual_evidence.status == "PASS"
    assert report.structured_state.issues == (
        "prior_colour_not_established",
        "prior_size_not_established",
    )
    assert report.structured_state.status == report.status == "SKIP"
    missing_prior = assess_turn("A2", **saved)
    assert missing_prior.factual_evidence.status == "FAIL"
    assert missing_prior.structured_state.status == "SKIP"
    assert missing_prior.status == "FAIL"


@pytest.mark.parametrize(
    "change",
    [
        "session",
        "trace",
        "message",
        "sequence",
        "tool_id",
        "model",
        "timestamp",
        "turn",
        "tool_error",
        "validation",
        "malformed",
        "prior_session",
        "prior_trace",
        "prior_slot",
    ],
)
def test_prerequisite_failures_remain_errors_and_never_become_quality_pass(change):
    saved, prior, slot = exchange(), None, "A1"
    if change == "session":
        saved["trace"]["session_id"] = "another"
    elif change == "trace":
        saved["trace"]["trace_id"] = "another"
    elif change == "message":
        saved["trace"]["user_message"] = "another"
    elif change == "sequence":
        saved["trace"]["tool_calls"][0]["sequence"] = 2
    elif change == "tool_id":
        saved["trace"]["tool_calls"][1]["tool_call_id"] = saved["trace"]["tool_calls"][
            0
        ]["tool_call_id"]
    elif change == "model":
        saved["trace"]["model"] = "another"
    elif change == "timestamp":
        saved["trace"]["timestamp"] = "not-a-date"
    elif change == "turn":
        saved["trace"]["turn_index"] = 2
    elif change == "tool_error":
        saved["trace"]["tool_calls"][0]["status"] = "error"
    elif change == "validation":
        saved["trace"]["recommendation_validation"]["prices_match_catalogue"] = False
    elif change == "malformed":
        saved["trace"]["tool_calls"][0]["result"]["data"] = {"secret": "DO_NOT_ECHO"}
    elif change == "prior_slot":
        prior = exchange()
    else:
        slot, saved, prior = "A2", exchange("A2"), exchange()
        if change == "prior_session":
            prior["trace"]["session_id"] = prior["chat"]["session_id"] = "another"
        else:
            prior["trace"]["trace_id"] = prior["chat"]["trace_id"] = saved["chat"][
                "trace_id"
            ]
    report = assess_turn(slot, **saved, prior_a1=prior)
    assert report.status == report.prerequisites.status == "ERROR"
    assert (
        report.factual_evidence.status
        == report.integration_coverage.status
        == report.structured_state.status
        == "SKIP"
    )
    assert "DO_NOT_ECHO" not in str(asdict(report))


@pytest.mark.parametrize(
    "mutation",
    [
        "search_count",
        "product_argument",
        "inventory_argument",
        "matched_variant",
        "no_recommendation",
        "nominations",
        "unrequested_promotion",
        "unrequested_quote",
        "trace_commerce",
        "beanie_warmth",
        "promotion_missing",
        "promotion_wrong",
        "quote_wrong",
    ],
)
def test_additional_evidence_contradictions_fail(mutation):
    slot = (
        "B2"
        if mutation == "beanie_warmth"
        else "A2"
        if mutation in ("promotion_missing", "promotion_wrong", "quote_wrong")
        else "A1"
    )
    saved = exchange(slot)
    if mutation == "search_count":
        tool_data(saved, "search_products")["count"] = 2
    elif mutation == "product_argument":
        saved["trace"]["tool_calls"][1]["arguments"]["product_id"] = "ACC-002"
    elif mutation == "inventory_argument":
        saved["trace"]["tool_calls"][-1]["arguments"]["colour"] = "Black"
    elif mutation == "matched_variant":
        saved["chat"]["recommendations"][0]["matched_variant"] = {
            "colour": "Black",
            "size": "20L",
            "stock": 5,
        }
    elif mutation == "no_recommendation":
        saved["chat"]["recommendations"] = []
    elif mutation == "nominations":
        saved["trace"]["recommended_product_ids"] = []
    elif mutation == "unrequested_promotion":
        saved["chat"]["promotion"] = {"code": "WELCOME10", "valid": True}
    elif mutation == "unrequested_quote":
        saved["chat"]["pricing"] = {
            "product_id": "ACC-003",
            "base_price": "55.00",
            "final_price": "49.50",
            "currency": "GBP",
            "discount_code": "WELCOME10",
        }
    elif mutation == "trace_commerce":
        saved["trace"]["promotion"] = {"code": "WELCOME10", "valid": True}
    elif mutation == "beanie_warmth":
        tool_data(saved, "get_product")["warmth"] = "none"
    elif mutation == "promotion_missing":
        remove_tool(saved, "validate_discount")
    elif mutation == "promotion_wrong":
        tool_data(saved, "validate_discount")["discount_percent"] = "50"
    elif mutation == "quote_wrong":
        saved["chat"]["pricing"]["final_price"] = "0"
    report = assess_turn(slot, **saved, prior_a1=exchange() if slot == "A2" else None)
    assert report.factual_evidence.status == report.status == "FAIL"


@pytest.mark.parametrize(
    "dimension", ["state", "recommendations", "nominations", "promotion", "pricing"]
)
def test_b1_fresh_session_checks(dimension):
    saved, shopping = exchange("B1"), exchange()
    if dimension == "state":
        saved["trace"]["resolved_constraints"] = {"colour": "Moss"}
    elif dimension == "recommendations":
        saved["chat"]["recommendations"] = shopping["chat"]["recommendations"]
    elif dimension == "nominations":
        saved["trace"]["recommended_product_ids"] = ["ACC-003"]
    elif dimension == "promotion":
        saved["chat"]["promotion"] = {"code": "WELCOME10", "valid": True}
    else:
        saved["chat"]["pricing"] = exchange("A2")["chat"]["pricing"]
    report = assess_turn("B1", **saved)
    assert report.status == "FAIL"
    assert (
        report.structured_state if dimension == "state" else report.factual_evidence
    ).status == "FAIL"


def test_inspection_does_not_mutate_inputs_or_create_clients(monkeypatch):
    import httpx

    def forbidden(*args, **kwargs):
        raise AssertionError("Offline acceptance must never create an HTTP client")

    monkeypatch.setattr(httpx.Client, "__init__", forbidden)
    saved = exchange()
    before = copy.deepcopy(saved)
    assert assess_turn("A1", **saved).status == "PASS"
    assert assess_original_turn("A1", **saved).status == "PASS"
    assert saved == before


def test_definition_fingerprint_binds_policy_code_separately_from_input_roster(
    monkeypatch,
):
    from harness.canary import acceptance

    before = policy_fingerprint()
    original = policy_fingerprint(ORIGINAL_POLICY)
    monkeypatch.setattr(
        acceptance.Path, "read_bytes", lambda _: b"changed acceptance implementation"
    )
    assert policy_fingerprint() != before
    assert policy_fingerprint(ORIGINAL_POLICY) == original
    assert roster_hash() == HISTORICAL_ROSTER


def test_unknown_slots_and_invalid_original_evidence_fail_closed():
    saved = exchange()
    assert assess_turn("UNKNOWN", **saved).status == "ERROR"
    saved["trace"]["session_id"] = "different"
    assert assess_original_turn("A1", **saved).status == "ERROR"


def test_inventory_result_cannot_impersonate_another_requested_product():
    saved = exchange()
    call = copy.deepcopy(saved["trace"]["tool_calls"][-1])
    call.update(sequence=4, tool_call_id="impersonated")
    call["arguments"]["product_id"] = "ACC-002"
    saved["trace"]["tool_calls"].append(call)
    assert (
        "inventory_arguments_result_differ"
        in assess_turn("A1", **saved).factual_evidence.issues
    )


def test_a2_can_refresh_exact_inventory_without_inventing_prior_state():
    saved, prior = exchange("A2"), exchange()
    inventory = copy.deepcopy(prior["trace"]["tool_calls"][-1])
    remove_tool(prior, "check_inventory")
    inventory.update(sequence=4, tool_call_id="a2-exact-inventory")
    saved["trace"]["tool_calls"].append(inventory)
    assert assess_turn("A2", **saved, prior_a1=prior).status == "PASS"


def test_undiscounted_quote_requires_consistent_base_and_final_prices():
    saved = exchange()
    quote = {
        "product_id": "ACC-003",
        "base_price": "55.00",
        "final_price": "55.00",
        "currency": "GBP",
        "discount_code": None,
        "discount_percent": None,
    }
    saved["chat"]["pricing"] = copy.deepcopy(quote)
    saved["trace"]["pricing"] = copy.deepcopy(quote)
    assert assess_turn("A1", **saved).status == "PASS"
    saved["chat"]["pricing"]["final_price"] = "54.00"
    saved["trace"]["pricing"]["final_price"] = "54.00"
    assert (
        "unrequested_or_incorrect_pricing"
        in assess_turn("A1", **saved).factual_evidence.issues
    )


def test_reported_execution_error_never_exposes_diagnostic_text():
    saved = exchange()
    saved["trace"]["errors"] = [{"code": "timeout", "message": "PRIVATE_DIAGNOSTIC"}]
    report = assess_turn("A1", **saved)
    assert report.status == "ERROR"
    assert "PRIVATE_DIAGNOSTIC" not in str(asdict(report))


@pytest.mark.parametrize("slot", ["A1", "B2"])
@pytest.mark.parametrize(
    "variant", ["absent", "null", "colour_only", "size_only", "matching"]
)
def test_availability_enquiry_does_not_require_saved_variant_preferences(slot, variant):
    saved = exchange(slot)
    constraints = saved["trace"]["resolved_constraints"]
    if variant == "absent":
        del constraints["colour"]
        del constraints["size"]
    elif variant == "null":
        constraints.update(colour=None, size=None)
    elif variant == "colour_only":
        constraints["size"] = None
    elif variant == "size_only":
        constraints["colour"] = None
    report = assess_turn(slot, **saved)
    assert report.structured_state.status == report.status == "PASS"
    if slot == "A1" and variant in ("absent", "null"):
        assert assess_original_turn(slot, **saved).status == "FAIL"


@pytest.mark.parametrize("slot", ["A1", "B2"])
@pytest.mark.parametrize(
    "price", [None, "missing", "0.00", "59.99", "60.01", "24.99", "25.01"]
)
def test_explicit_price_limit_must_be_saved_exactly(slot, price):
    saved = exchange(slot)
    if price == "missing":
        del saved["trace"]["resolved_constraints"]["maximum_price"]
    else:
        saved["trace"]["resolved_constraints"]["maximum_price"] = price
    report = assess_turn(slot, **saved)
    assert (
        report.factual_evidence.status == report.integration_coverage.status == "PASS"
    )
    assert report.structured_state.issues == ("resolved_maximum_price_differs",)
    assert report.status == "FAIL"


@pytest.mark.parametrize("slot", ["A1", "B2"])
@pytest.mark.parametrize("field", ["colour", "size"])
def test_enquiry_does_not_support_an_unrelated_saved_variant(slot, field):
    saved = exchange(slot)
    saved["trace"]["resolved_constraints"][field] = "Unrequested"
    report = assess_turn(slot, **saved)
    assert (
        report.factual_evidence.status == report.integration_coverage.status == "PASS"
    )
    assert report.structured_state.issues == ("resolved_" + field + "_differs",)
    assert report.status == "FAIL"


@pytest.mark.parametrize("field", ["colour", "size", "maximum_price"])
def test_a2_explicit_keep_and_prior_price_limit_cannot_disappear(field):
    saved = exchange("A2")
    saved["trace"]["resolved_constraints"][field] = None
    report = assess_turn("A2", **saved, prior_a1=exchange())
    assert (
        report.factual_evidence.status == report.integration_coverage.status == "PASS"
    )
    assert report.structured_state.issues == ("resolved_" + field + "_differs",)
    assert report.status == "FAIL"


@pytest.mark.parametrize("field", ["colour", "size", "maximum_price"])
def test_a2_cannot_hide_incorrect_prior_state_with_correct_current_state(field):
    saved, prior = exchange("A2"), exchange()
    prior["trace"]["resolved_constraints"][field] = (
        "50.00" if field == "maximum_price" else "Unrequested"
    )
    report = assess_turn("A2", **saved, prior_a1=prior)
    assert report.structured_state.issues == ("prior_" + field + "_differs",)
    assert report.status == "FAIL"


def test_a2_missing_prior_limit_is_a_failure_not_a_missing_preference_skip():
    saved, prior = exchange("A2"), exchange()
    prior["trace"]["resolved_constraints"] = {}
    report = assess_turn("A2", **saved, prior_a1=prior)
    assert report.structured_state.status == "FAIL"
    assert "prior_maximum_price_differs" in report.structured_state.issues


def test_current_a2_inventory_does_not_make_unavailable_retention_evidence_pass():
    saved, prior = exchange("A2"), exchange()
    inventory = copy.deepcopy(prior["trace"]["tool_calls"][-1])
    inventory.update(sequence=4, tool_call_id="a2-inventory-only")
    saved["trace"]["tool_calls"].append(inventory)
    report = assess_turn("A2", **saved)
    assert (
        report.factual_evidence.status == report.integration_coverage.status == "PASS"
    )
    assert report.structured_state.status == report.status == "SKIP"
    assert report.structured_state.issues == ("prior_state_unavailable",)


def test_target_get_product_is_covered_even_when_another_candidate_was_also_checked():
    saved = exchange()
    unrelated = copy.deepcopy(exchange("B2")["trace"]["tool_calls"][1])
    unrelated.update(sequence=4, tool_call_id="another-candidate")
    saved["trace"]["tool_calls"].append(unrelated)
    assert assess_turn("A1", **saved).status == "PASS"


@pytest.mark.parametrize("side", ["arguments", "result"])
def test_get_product_coverage_requires_target_arguments_and_result(side):
    saved = exchange()
    lookup = saved["trace"]["tool_calls"][1]
    if side == "arguments":
        lookup["arguments"]["product_id"] = "ACC-001"
    else:
        lookup["result"]["data"] = copy.deepcopy(
            tool_data(exchange("B2"), "get_product")
        )
    report = assess_turn("A1", **saved)
    assert report.integration_coverage.issues == (
        "target_product_not_exercised:get_product",
    )
    assert report.factual_evidence.status == report.status == "FAIL"
