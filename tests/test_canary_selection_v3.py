"""Selection v3 uses synthetic snapshots; imports and assessment open no clients."""

import copy
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import pytest
from test_canary_acceptance import exchange, remove_tool, tool_data

from harness.canary.acceptance import Check, policy_fingerprint
from harness.canary.inputs import JUDGE_ORDER, TARGET_TURNS, judge_inputs, roster_hash
from harness.canary.selection_acceptance import (
    ACCEPTANCE_POLICY,
    acceptance_fingerprint,
    assess_selection,
)
from harness.canary.selection_v3 import (
    A1,
    A2,
    DEFINITION,
    LIMITS,
    ORDER,
    TURNS,
    definition_fingerprint,
    roster_fingerprint,
)

ROOT = Path(__file__).resolve().parents[1]


def selected(slot="A1", *, product_tool="both"):
    value = exchange(slot, product_tool=product_tool)
    value["trace"]["user_message"] = next(t.message for t in TURNS if t.slot == slot)
    return value


def preceding(slot):
    return {
        t.slot: selected(t.slot)
        for t in TURNS[: next(i for i, t in enumerate(TURNS) if t.slot == slot)]
    }


def test_exact_approved_definition_and_independently_computed_roster_hash():
    assert DEFINITION == "salesagent-canary-selected-preferences-v3"
    assert ACCEPTANCE_POLICY == "salesagent-canary-selection-v3"
    assert (
        A1
        == "Please find a water-resistant day pack for a short canal-side walk. My maximum price is £60. I choose ACC-003 in Moss, 20L; please remember this product, colour and capacity as my preferences for this conversation and check that exact variant's availability. Do not apply a discount."
    )
    assert (
        A2
        == "For the pack and exact variant I selected earlier, validate WELCOME10 and quote the final price. Keep my saved preferences and price limit."
    )
    assert [t.slot for t in TURNS] == ["A1", "B1", "A2", "B2"]
    assert TURNS[1] == TARGET_TURNS[1] and TURNS[3] == TARGET_TURNS[3]
    assert all(cue not in A2 for cue in ("ACC-003", "Moss", "20L", "£60"))
    canonical = json.dumps(
        {
            "target": [vars(t) for t in TURNS],
            "judge": {k: v.prompt_hash for k, v in judge_inputs().items()},
            "order": list(JUDGE_ORDER),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    assert (
        hashlib.sha256(canonical.encode()).hexdigest()
        == roster_fingerprint()
        == "564b98533b5b48b13d7d97fec8c150c329a6bf5d7ed38f0f165bae32a8493e17"
    )
    assert (
        roster_hash()
        == "e8778ce74a270e6efbe490198d01e8b9c50bcc43387a02bff5f00b42304d5794"
    )


def test_v2_1_and_its_reviewed_inventory_are_frozen():
    assert (
        policy_fingerprint()
        == "3c632f6ce5e8b9eda42b4a0a0f91ccb82f4f34783da3b9638762b84351c9c2f9"
    )
    assert (
        policy_fingerprint("salesagent-canary-c1-v1")
        == "646fd93488667251a67a02d98548e1aface9353d2a4bb7594a7343d664f1aa65"
    )
    expected = {
        "src/harness/canary/acceptance.py": "2cf68cc880c133eee7d9b5b7b6c709e5eba8c1d0bab001e86febc1afff82f323",
        "tests/test_canary_acceptance.py": "5dc0de40bd580fb6f9306cc9e61de89b6e13d24dc5c4756158e3acb1d5d14f47",
        "tests/test_canary_state.py": "ca85f6f5e071e19fb84104f5dee6afeb160264ac363bc26628a531e7a6a4c7a3",
        "docs/canary-acceptance-v2.md": "2b74a87dbe812c333f96716885d063408d2e7cd5d9b09b1f93111ffa378a6dd2",
    }
    for path, digest in expected.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("slot", ["A1", "B1", "A2", "B2"])
def test_complete_synthetic_selection_evidence_passes_mechanical_checks(slot):
    report = assess_selection(slot, **selected(slot), previous=preceding(slot))
    assert report.status == "PASS"
    assert report.human_prose_review_required is True
    assert report.current_state.status == report.session_isolation.status == "PASS"
    assert (report.retention.status if report.retention else None) == (
        "PASS" if slot == "A2" else None
    )


@pytest.mark.parametrize("slot", ["A1", "A2"])
@pytest.mark.parametrize("field", ["colour", "size", "maximum_price"])
@pytest.mark.parametrize("value", [None, "wrong"])
def test_selected_current_preferences_are_required_independent_of_inventory(
    slot, field, value
):
    saved = selected(slot)
    saved["trace"]["resolved_constraints"][field] = (
        "50.00" if field == "maximum_price" and value else value
    )
    report = assess_selection(slot, **saved, previous=preceding(slot))
    assert (
        report.factual_evidence.status == report.integration_coverage.status == "PASS"
    )
    assert report.current_state.status == report.status == "FAIL"
    if slot == "A2":
        assert report.retention.status == "FAIL"


@pytest.mark.parametrize("field", ["colour", "size", "maximum_price"])
@pytest.mark.parametrize("value", [None, "wrong"])
def test_unestablished_a1_selection_skips_retention_without_changing_current_state(
    field, value
):
    prior = preceding("A2")
    prior["A1"]["trace"]["resolved_constraints"][field] = (
        "50.00" if field == "maximum_price" and value else value
    )
    a1 = assess_selection("A1", **prior["A1"])
    assert a1.current_state.status == "FAIL"
    report = assess_selection("A2", **selected("A2"), previous=prior)
    assert report.current_state.status == "PASS"
    assert (
        report.retention.status
        == report.structured_state.status
        == report.status
        == "SKIP"
    )


def test_missing_antecedent_cannot_hide_independent_a2_current_violation():
    prior, saved = preceding("A2"), selected("A2")
    prior["A1"]["trace"]["resolved_constraints"]["colour"] = None
    saved["trace"]["resolved_constraints"]["size"] = "10L"
    report = assess_selection("A2", **saved, previous=prior)
    assert report.retention.status == "SKIP"
    assert (
        report.current_state.status
        == report.structured_state.status
        == report.status
        == "FAIL"
    )


def test_missing_previous_snapshots_produce_explicit_unavailable_checks():
    report = assess_selection("A2", **selected("A2"))
    assert report.current_state.status == report.integration_coverage.status == "PASS"
    assert (
        report.retention.status
        == report.session_isolation.status
        == report.factual_evidence.status
        == report.status
        == "SKIP"
    )


@pytest.mark.parametrize("slot", ORDER)
def test_every_required_predecessor_is_derived_from_approved_roster(slot):
    assert (
        assess_selection(
            slot, **selected(slot), previous=preceding(slot)
        ).session_isolation.status
        == "PASS"
    )
    for missing in ORDER[: ORDER.index(slot)]:
        context = preceding(slot)
        del context[missing]
        result = assess_selection(slot, **selected(slot), previous=context)
        assert result.session_isolation == Check(
            "SKIP", ("session_evidence_unavailable:" + missing,)
        )
        assert result.status != "PASS"


@pytest.mark.parametrize("identity", ["trace", "a_session", "b_session"])
def test_b2_requires_a2_identity_consistency_even_when_other_predecessor_missing(
    identity,
):
    context = preceding("B2")
    if identity == "trace":
        context["A2"]["chat"]["trace_id"] = context["A2"]["trace"]["trace_id"] = (
            context["A1"]["trace"]["trace_id"]
        )
    else:
        chosen = (
            "different-a-session"
            if identity == "a_session"
            else context["B1"]["trace"]["session_id"]
        )
        context["A2"]["chat"]["session_id"] = context["A2"]["trace"]["session_id"] = (
            chosen
        )
    assert assess_selection("B2", **selected("B2"), previous=context).status == "ERROR"
    del context["B1"]
    assert assess_selection("B2", **selected("B2"), previous=context).status == "ERROR"


@pytest.mark.parametrize("slot", ["B1", "B2"])
def test_a_session_identity_cannot_be_reused_for_b(slot):
    saved, context = selected(slot), preceding(slot)
    saved["chat"]["session_id"] = saved["trace"]["session_id"] = context["A1"]["chat"][
        "session_id"
    ]
    assert assess_selection(slot, **saved, previous=context).status == "ERROR"


def test_distinct_b_session_with_leaked_preferences_is_behavioural_fail():
    saved = selected("B1")
    saved["trace"]["resolved_constraints"] = {
        "colour": "Moss",
        "maximum_price": "60.00",
    }
    report = assess_selection("B1", **saved, previous=preceding("B1"))
    assert report.session_isolation.status == report.prerequisites.status == "PASS"
    assert report.current_state.status == report.status == "FAIL"


def test_b2_is_still_an_enquiry_with_a_required_price_limit():
    saved = selected("B2")
    saved["trace"]["resolved_constraints"] = {"maximum_price": "25.00"}
    assert assess_selection("B2", **saved, previous=preceding("B2")).status == "PASS"
    saved["trace"]["resolved_constraints"]["maximum_price"] = None
    assert (
        assess_selection("B2", **saved, previous=preceding("B2")).current_state.status
        == "FAIL"
    )


def test_search_facts_do_not_satisfy_target_get_product_coverage():
    saved = selected(product_tool="search_products")
    report = assess_selection("A1", **saved)
    assert report.factual_evidence.status == report.current_state.status == "PASS"
    assert report.integration_coverage.status == report.status == "FAIL"
    unrelated = copy.deepcopy(selected("B2")["trace"]["tool_calls"][1])
    unrelated.update(sequence=3, tool_call_id="another-product")
    saved["trace"]["tool_calls"].append(unrelated)
    report = assess_selection("A1", **saved)
    assert report.factual_evidence.status == "PASS"
    assert report.integration_coverage.issues == (
        "target_product_not_exercised:get_product",
    )


@pytest.mark.parametrize(
    "mutation", ["price", "stock", "inventory_missing", "wrong_quote", "wrong_product"]
)
def test_factual_and_product_continuity_failures_are_independent(mutation):
    slot = "A2" if mutation in ("wrong_quote", "wrong_product") else "A1"
    saved = selected(slot)
    if mutation == "price":
        tool_data(saved, "get_product")["price"] = "99.00"
    elif mutation == "stock":
        tool_data(saved, "check_inventory")["stock"] = 0
    elif mutation == "inventory_missing":
        remove_tool(saved, "check_inventory")
    elif mutation == "wrong_quote":
        saved["chat"]["pricing"]["final_price"] = "0.00"
    else:
        saved["chat"]["pricing"]["product_id"] = "ACC-001"
    report = assess_selection(slot, **saved, previous=preceding(slot))
    assert report.prerequisites.status == report.current_state.status == "PASS"
    assert report.factual_evidence.status == report.status == "FAIL"


@pytest.mark.parametrize(
    "code", ["duplicate_product_id", "unknown_product_id", "ungrounded_product_id"]
)
def test_completed_known_nomination_rejections_are_behavioural_fail(code):
    saved = selected()
    validation = saved["trace"]["recommendation_validation"]
    validation["validation_errors"] = [code + ":ACC-003"]
    validation["all_products_exist"] = code != "unknown_product_id"
    report = assess_selection("A1", **saved)
    assert report.prerequisites.status == report.current_state.status == "PASS"
    assert "business:" + code in report.factual_evidence.issues
    assert report.status == "FAIL"


@pytest.mark.parametrize(
    "code", ["promotion_nomination_missing", "ungrounded_promotion_code"]
)
def test_completed_known_promotion_rejections_are_behavioural_fail(code):
    saved = selected("A2")
    saved["trace"]["errors"] = [{"code": code, "message": "PRIVATE_ERROR"}]
    report = assess_selection("A2", **saved, previous=preceding("A2"))
    assert report.prerequisites.status == "PASS" and report.status == "FAIL"
    assert "PRIVATE_ERROR" not in str(asdict(report))


@pytest.mark.parametrize(
    "code",
    [
        "pricing_calculation_failed",
        "openai_timeout",
        "unknown_tool",
        "invalid_arguments",
        "product_not_found",
        "unrecognised_error",
    ],
)
def test_execution_and_unreviewed_business_categories_fail_closed(code):
    saved = selected()
    saved["trace"]["errors"] = [{"code": code, "message": "PRIVATE_ERROR"}]
    report = assess_selection("A1", **saved)
    assert report.status == "ERROR" and report.current_state.status == "SKIP"
    assert "PRIVATE_ERROR" not in str(asdict(report))


@pytest.mark.parametrize(
    "mutation",
    [
        "lookup_failure",
        "unknown_validation",
        "bad_flags",
        "contradictory_flags",
        "failed_tool",
        "trace_id",
        "tool_sequence",
        "token_total",
        "historical_wording",
        "prior_identity",
        "bad_context",
        "future_context",
    ],
)
def test_malformed_or_unreliable_evidence_remains_error(mutation):
    saved, context = selected(), None
    if mutation == "lookup_failure":
        saved["trace"]["recommendation_validation"]["validation_errors"] = [
            "product_lookup_failed:ACC-003"
        ]
    elif mutation == "unknown_validation":
        saved["trace"]["recommendation_validation"]["validation_errors"] = [
            "PRIVATE_DIAGNOSTIC"
        ]
    elif mutation == "bad_flags":
        saved["trace"]["recommendation_validation"]["prices_match_catalogue"] = False
    elif mutation == "contradictory_flags":
        saved["trace"]["recommendation_validation"]["all_products_exist"] = False
    elif mutation == "failed_tool":
        saved["trace"]["tool_calls"][0]["status"] = "error"
    elif mutation == "trace_id":
        saved["trace"]["trace_id"] = "another"
    elif mutation == "tool_sequence":
        saved["trace"]["tool_calls"][0]["sequence"] = 2
    elif mutation == "token_total":
        saved["trace"]["token_usage"]["total_tokens"] = 999
    elif mutation == "historical_wording":
        saved = exchange()
    elif mutation == "prior_identity":
        saved, context = selected("A2"), preceding("A2")
        context["A1"]["trace"]["session_id"] = context["A1"]["chat"]["session_id"] = (
            "other"
        )
    elif mutation == "bad_context":
        context = []
    else:
        context = {"B2": selected("B2")}
    slot = "A2" if mutation == "prior_identity" else "A1"
    report = assess_selection(slot, **saved, previous=context)
    assert report.status == "ERROR"
    assert "PRIVATE_DIAGNOSTIC" not in str(asdict(report))


def test_no_http_clients_or_input_mutation_and_separate_fingerprints(monkeypatch):
    import httpx

    def forbidden(*args, **kwargs):
        raise AssertionError("No clients in offline policies")

    monkeypatch.setattr(httpx.Client, "__init__", forbidden)
    saved = selected()
    before = copy.deepcopy(saved)
    report = assess_selection("A1", **saved)
    assert report.status == "PASS" and saved == before
    assert asdict(report)["human_prose_review_required"] is True
    assert (
        len(
            {
                definition_fingerprint(),
                acceptance_fingerprint(),
                roster_fingerprint(),
                policy_fingerprint(),
            }
        )
        == 4
    )
    assert asdict(LIMITS)["logical_calls_total"] == 24


def test_canary_errors_are_never_swallowed_as_behavioural_fail(monkeypatch):
    from harness.canary import selection_acceptance
    from harness.canary.recording import CanaryError

    def fail(*args, **kwargs):
        raise CanaryError("synthetic control failure")

    monkeypatch.setattr(selection_acceptance, "_facts", fail)
    with pytest.raises(CanaryError, match="synthetic control failure"):
        assess_selection("A1", **selected())
