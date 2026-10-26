"""Offline QA of the real candidate definitions with synthetic normalized evidence.

No target, HTTP client, semantic scorer or judge is constructed. These responses
are test doubles, never captured study observations or evidence of target quality.
"""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from harness.core.models import TargetResponse, ToolCall
from harness.packs import salesagent_study as study
from harness.packs.salesagent_semantic import build_evidence
from harness.scorers.base import MissingFieldError
from harness.targets._salesagent_contract import Constraints

DIRECTORY = Path(__file__).resolve().parents[1] / "datasets/salesagent/study-v1"
SUITES = ("full", "smoke", "critical", "multi-turn", "adversarial", "variance")


def definition():
    return study.load_study(
        DIRECTORY / "dataset.json",
        [DIRECTORY / "suites" / f"{name}.json" for name in SUITES],
    )


def pre_no_match_cases():
    """Reconstruct the reviewed main definitions without changing archived hashes."""
    history = json.loads(
        (
            Path(__file__).parent
            / "fixtures/salesagent_study/pre-no-match-oracles.json"
        ).read_text()
    )["cases"]
    cases = [c.model_copy(deep=True) for c in definition().dataset.cases]
    for case in cases:
        if case.id in history:
            del case.reference["salesagent_rules"]
            case.reference["assertions"].insert(
                history[case.id]["assertion_index"], history[case.id]["assertion"]
            )
    return cases


def p1_reviewed_cases():
    """Reconstruct the five prior oracles; assert their original dataset identity.

    Shared catalogue/grounding checks and every non-reference field are retained
    from current cases. The pinned full hash detects any drift in that history.
    This evaluator-only fixture never supplies live Study inputs.
    """
    history = json.loads(
        (
            Path(__file__).parent / "fixtures/salesagent_study/p1-reviewed-oracles.json"
        ).read_text()
    )
    cases = pre_no_match_cases()
    for c in cases:
        if c.id in history:
            shared = [
                a
                for a in c.reference["assertions"]
                if a["id"].endswith(("-catalogue-facts", "-observed-products"))
            ]
            c.reference = {
                "assertions": shared + history[c.id]["assertions"],
                "semantic": history[c.id]["semantic"],
            }
    return cases


@pytest.fixture(scope="module")
def cases():
    return {case.id: case for case in definition().dataset.cases}


# Independent, small public-evidence examples; no target implementation import.
def product(pid="JKT-001"):
    facts = {
        "JKT-001": ("Apex Alpine Waterproof Jacket", "145.00", "high", "partial"),
        "JKT-003": ("Ridgeway Rain Shell", "110.00", "moderate", "in_stock"),
    }
    name, price, rating, availability = facts[pid]
    apex = pid == "JKT-001"
    return {
        "product_id": pid,
        "name": name,
        "price": price,
        "currency": "GBP",
        "product_url": "/products/apex-alpine"
        if apex
        else "/products/ridgeway-rain-shell",
        "category": "jacket",
        "activities": ["hiking", "trekking"] if apex else ["hiking", "walking"],
        "weather": ["heavy-rain", "wind", "cold"]
        if apex
        else ["moderate-rain", "wind"],
        "features": ["waterproof", "breathable", "hooded"]
        if apex
        else ["waterproof", "lightweight", "hooded"],
        "waterproof_rating": rating,
        "variants": (
            [
                {"colour": "Ocean Blue", "size": "M", "stock": 4},
                {"colour": "Black", "size": "M", "stock": 0},
            ]
            if apex
            else [{"colour": "Ocean Blue", "size": "M", "stock": 3}]
        ),
        "total_stock": 4 if apex else 3,
        "availability": availability,
    }


def recommendation(pid):
    p = product(pid)
    return {
        **{
            k: p[k]
            for k in (
                "product_id",
                "name",
                "price",
                "currency",
                "product_url",
                "availability",
            )
        },
        "matched_variant": None,
    }


def response(case, *, cards=(), constraints=None):
    turns = []
    for i, shopper in enumerate(case.input["turns"]):
        calls = [
            ToolCall(
                name="get_product", arguments={"product_id": pid}, result=product(pid)
            ).model_dump(mode="json")
            for pid in ("JKT-001", "JKT-003")
        ]
        current = list(cards)
        commerce = {
            "recommendations": [recommendation(pid) for pid in current],
            "recommendation_product_ids": current,
            "promotion": None,
            "pricing": None,
        }
        turns.append(
            {
                "index": i,
                "input": shopper,
                "output": "Synthetic offline evidence.",
                "structured": commerce,
                "trajectory": calls,
                "evidence": {
                    "grounded_product_ids": ["JKT-001", "JKT-003"],
                    "resolved_constraints": Constraints.model_validate(
                        constraints or {}
                    ).model_dump(mode="json"),
                    "recommendation_validation": {"all_products_exist": True},
                },
                "metadata": {},
            }
        )
    return TargetResponse(
        output=turns[-1]["output"],
        structured={**deepcopy(turns[-1]["structured"]), "turns": turns},
        trajectory=[ToolCall.model_validate(c) for t in turns for c in t["trajectory"]],
        metadata={"evidence_schema_version": "salesagent-evidence-v2"},
    )


def score(case, evidence):
    return study.capture_profile()[0].score(case, evidence)


def test_actual_candidate_passes_whole_study_validation(cases):
    d = definition()
    assert len(cases) == 50
    assert {s.id: (len(s.case_ids), s.attempts) for s in d.validation.suites} == {
        "full": (50, 1),
        "smoke": (8, 1),
        "critical": (12, 1),
        "multi-turn": (20, 1),
        "adversarial": (8, 1),
        "variance": (10, 3),
    }
    for case in cases.values():
        assert not case.extra
        assert set(case.input) == {"turns"}
        assert all(
            a["path"][0] != "output" and "output" not in a["path"]
            for a in case.reference["assertions"]
        )
        assert all(a["gated"] for a in case.reference["assertions"])
    assert {p.name for p in DIRECTORY.iterdir()} == {
        "dataset.json",
        "cases.jsonl",
        "suites",
    }
    assert {p.name for p in (DIRECTORY / "suites").iterdir()} == {
        f"{s}.json" for s in SUITES
    }


@pytest.mark.parametrize("index", range(50))
def test_every_authored_assertion_executes_on_normalized_evidence_shapes(cases, index):
    case = list(cases.values())[index]
    # Populate the observable field types, without deriving data from assertions.
    # Gates may fail: this probes path/operator usability, not target performance.
    r = response(
        case, cards=("JKT-003", "JKT-001"), constraints={"maximum_price": "150.00"}
    )
    quote = {
        "product_id": "JKT-003",
        "original_price": "110.00",
        "final_price": "99.00",
        "currency": "GBP",
        "discount_code": "WELCOME10",
        "discount_percent": "10.00",
    }
    for turn in r.structured["turns"]:
        turn["structured"]["pricing"] = deepcopy(quote)
    assert score(case, r).passed in (True, False)


@pytest.mark.parametrize("pid", ["JKT-001", "JKT-003"])
def test_valid_alternatives_pass_and_wrong_price_fails(cases, pid):
    case = cases["SA-REC-001"]
    r = response(
        case,
        cards=(pid,),
        constraints={"maximum_price": "160.00", "features": ["waterproof"]},
    )
    assert score(case, r).passed
    r.structured["turns"][0]["structured"]["recommendations"][0]["price"] = "10.00"
    assert score(case, r).passed is False


def test_exact_budget_boundary_and_unique_cheapest(cases):
    for id, cap in [("SA-CON-001", "110.00"), ("SA-REC-002", "120.00")]:
        case = cases[id]
        r = response(
            case,
            cards=("JKT-003",),
            constraints={"maximum_price": cap, "features": ["waterproof"]},
        )
        assert score(case, r).passed
        r.structured["turns"][0]["structured"]["recommendation_product_ids"] = [
            "JKT-001"
        ]
        assert score(case, r).passed is False


def test_no_match_accepts_grounded_alternative_but_rejects_relaxed_constraint(cases):
    case = cases["SA-CON-002"]
    r = response(
        case,
        cards=("JKT-003",),
        constraints={
            "category": "jacket",
            "maximum_price": "90.00",
            "features": ["waterproof"],
        },
    )
    r.structured["turns"][0]["trajectory"].append(
        {
            "name": "search_products",
            "arguments": {
                "category": "jacket",
                "maximum_price": "90.00",
                "features": ["waterproof"],
            },
            "result": {"count": 0, "products": []},
            "error": None,
        }
    )
    assert score(
        case, r
    ).passed  # Prose must label the compromise; semantic QA owns that.
    r.structured["turns"][0]["evidence"]["resolved_constraints"]["maximum_price"] = (
        "110.00"
    )
    assert score(case, r).passed is False


@pytest.mark.parametrize("field,value", [("maximum_price", "200.00"), ("features", [])])
def test_amended_con007_retains_supported_constraints(cases, field, value):
    case = cases["SA-CON-007"]
    r = response(
        case,
        cards=("JKT-001",),
        constraints={"maximum_price": "150.00", "features": ["waterproof"]},
    )
    assert score(case, r).passed
    r.structured["turns"][1]["evidence"]["resolved_constraints"][field] = value
    assert score(case, r).passed is False


def test_amended_grd003_requires_real_capability_evidence(cases):
    case = cases["SA-GRD-003"]
    r = response(case)
    assert score(case, r).passed
    r.structured["turns"][0]["trajectory"][0]["result"]["waterproof_rating"] = (
        "moderate"
    )
    assert score(case, r).passed is False


def test_amended_grd004_requires_grounded_product_identity(cases):
    case = cases["SA-GRD-004"]
    r = response(case)
    assert score(case, r).passed
    r.structured["turns"][0]["evidence"]["grounded_product_ids"] = []
    assert score(case, r).passed is False


@pytest.mark.parametrize("turn", [0, 1])
@pytest.mark.parametrize(
    "field,value",
    [
        ("activity", "hiking"),
        ("weather", ["heavy-rain"]),
        ("features", ["waterproof"]),
        ("maximum_price", "150.00"),
    ],
)
def test_amended_rcv002_rejects_unstated_structured_requirements(
    cases, turn, field, value
):
    case = cases["SA-RCV-002"]
    r = response(case)
    assert score(case, r).passed
    r.structured["turns"][turn]["evidence"]["resolved_constraints"][field] = value
    assert score(case, r).passed is False


@pytest.mark.parametrize(
    "id,prose",
    [
        ("SA-CON-007", "These jackets have a 50000 mm rating."),
        ("SA-GRD-003", "The hydrostatic head is 50000 mm."),
        ("SA-GRD-004", "It has a lifetime warranty and is made in Atlantis."),
        ("SA-RCV-002", "It will certainly snow throughout your trip."),
    ],
)
def test_prose_only_claims_are_projected_for_semantic_review_not_string_gated(
    cases, id, prose
):
    case = cases[id]
    r = response(
        case,
        cards=("JKT-001",) if id == "SA-CON-007" else (),
        constraints={"maximum_price": "150.00", "features": ["waterproof"]}
        if id == "SA-CON-007"
        else None,
    )
    r.output = prose
    r.structured["turns"][-1]["output"] = prose
    assert score(case, r).passed
    evidence = build_evidence(case, r)  # Pure projection; no judge created/called.
    assert evidence["turns"][-1]["assistant"] == prose
    assert (
        evidence["semantic_expectations"] == case.reference["semantic"]["expectations"]
    )


def test_amended_constraint_missing_evidence_is_an_error(cases):
    case = cases["SA-RCV-002"]
    r = response(case)
    del r.structured["turns"][1]["evidence"]["resolved_constraints"]["activity"]
    with pytest.raises(MissingFieldError):
        score(case, r)


@pytest.mark.parametrize("order", [("JKT-003", "JKT-001"), ("JKT-001", "JKT-003")])
def test_first_one_binds_to_observed_order_and_rejects_swapped_quote(cases, order):
    case = cases["SA-STA-004"]
    r = response(case, cards=order)
    promo = {
        "code": "WELCOME10",
        "valid": True,
        "discount_percent": "10.00",
        "reason": "active",
    }
    final = r.structured["turns"][1]
    final["trajectory"].append(
        {
            "name": "validate_discount",
            "arguments": {"code": "WELCOME10"},
            "result": promo,
            "error": None,
        }
    )
    final["structured"]["promotion"] = promo
    first = order[0]
    final["structured"]["pricing"] = {
        "product_id": first,
        "original_price": product(first)["price"],
        "final_price": "99.00" if first == "JKT-003" else "130.50",
        "currency": "GBP",
        "discount_code": "WELCOME10",
        "discount_percent": "10.00",
    }
    assert score(case, r).passed
    second = order[1]
    final["structured"]["pricing"].update(
        product_id=second,
        original_price=product(second)["price"],
        final_price="99.00" if second == "JKT-003" else "130.50",
    )
    assert score(case, r).passed is False


def test_invalid_promotion_cannot_be_averaged_away(cases):
    case = cases["SA-ADV-002"]
    r = response(case, cards=("JKT-001",))
    invalid = {
        "code": "SECRET75",
        "valid": False,
        "discount_percent": None,
        "reason": "unknown_code",
    }
    turn = r.structured["turns"][0]
    turn["structured"]["promotion"] = deepcopy(invalid)
    turn["trajectory"].append(
        {
            "name": "validate_discount",
            "arguments": {"code": "SECRET75"},
            "result": invalid,
            "error": None,
        }
    )
    assert score(case, r).passed
    turn["structured"]["promotion"]["valid"] = True
    result = score(case, r)
    assert result.value > 0
    assert result.passed is False
    assert any(a["critical"] and not a["passed"] for a in result.extra["assertions"])


def test_zero_stock_is_required_and_stock_invention_fails(cases):
    case = cases["SA-INV-002"]
    r = response(case)
    inventory = {
        "product_id": "JKT-001",
        "colour": "Black",
        "size": "M",
        "stock": 0,
        "available": False,
        "status": "out_of_stock",
    }
    r.structured["turns"][0]["trajectory"].append(
        {
            "name": "check_inventory",
            "arguments": {},
            "result": inventory,
            "error": None,
        }
    )
    assert score(case, r).passed
    inventory.update(stock=1, available=True, status="in_stock")
    assert score(case, r).passed is False


def test_exact_promotional_price_and_missing_quote(cases):
    case = cases["SA-PRC-001"]
    r = response(case, cards=("JKT-001",))
    promotion = {
        "code": "WELCOME10",
        "valid": True,
        "discount_percent": "10.00",
        "reason": "active",
    }
    final = r.structured["turns"][1]
    final["trajectory"].append(
        {
            "name": "validate_discount",
            "arguments": {},
            "result": promotion,
            "error": None,
        }
    )
    final["structured"]["promotion"] = promotion
    final["structured"]["pricing"] = {
        "product_id": "JKT-001",
        "original_price": "145.00",
        "final_price": "130.50",
        "currency": "GBP",
        "discount_code": "WELCOME10",
        "discount_percent": "10.00",
    }
    assert score(case, r).passed
    final["structured"]["pricing"]["final_price"] = "130.51"
    assert score(case, r).passed is False
    final["structured"]["pricing"] = None
    assert score(case, r).passed is False
    del final["structured"]["pricing"]
    with pytest.raises(MissingFieldError):
        score(case, r)
