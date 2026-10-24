"""Approved P2 oracle corrections: complete offline evidence and negative controls.

Catalogue snapshot is independent of candidate assertions. No target/judge runs;
scripted judgments below exercise gates, never establish semantic accuracy.
"""

import json
from copy import deepcopy
from decimal import Decimal
from itertools import permutations
from pathlib import Path

import pytest
from test_replay import settings
from test_salesagent_study_cases import definition, p1_reviewed_cases, response
from test_salesagent_study_corrections import synchronize, tool

from harness.core.case_fingerprints import hash_case_definition
from harness.core.dataset import hash_cases
from harness.core.fingerprints import fingerprint
from harness.core.models import Verdict
from harness.core.runner import _scorer_snapshot, run
from harness.packs import salesagent_study as study
from harness.scorers.base import MissingFieldError
from harness.targets.base import StaticTarget

CATALOGUE = json.loads(
    (
        Path(__file__).parent / "fixtures/salesagent_study/catalogue-products.json"
    ).read_text()
)["products"]
FEATURE_CASES = ["SA-GRD-001", "SA-GRD-002", "SA-GRD-003", "SA-GRD-006"]
FEATURE_PRODUCTS = {
    "SA-GRD-001": "JKT-002",
    "SA-GRD-002": "INS-001",
    "SA-GRD-003": "JKT-001",
    "SA-GRD-006": "JKT-003",
}


@pytest.fixture(scope="module")
def cases():
    return {c.id: c for c in definition().dataset.cases}


def observed_product(pid):
    """Normalize a pinned independent source snapshot, including complete variants."""
    p = deepcopy(next(p for p in CATALOGUE if p["id"] == pid))
    p["product_id"] = p.pop("id")
    p["total_stock"] = sum(v["stock"] for v in p["variants"])
    stocked = sum(v["stock"] > 0 for v in p["variants"])
    p["availability"] = (
        "out_of_stock"
        if not stocked
        else "in_stock"
        if stocked == len(p["variants"])
        else "partial"
    )
    # Warmth and season are deliberately absent from current normalized evidence.
    del p["warmth"], p["season"]
    return p


def capability_response(case):
    r = response(case)
    p = observed_product(FEATURE_PRODUCTS[case.id])
    for t in r.structured["turns"]:
        t["trajectory"] = [tool("get_product", p, product_id=p["product_id"])]
        t["evidence"]["grounded_product_ids"] = [p["product_id"]]
        t["output"] = {
            "SA-GRD-001": "Velo is lightweight, packable and water-resistant, not waterproof. It is out of stock; choose a waterproof shell for sustained rain.",
            "SA-GRD-002": "Cairn is insulated, warm and wind-resistant, but not waterproof. You need a waterproof shell for rain.",
            "SA-GRD-003": "Apex is waterproof, breathable and hooded with high categorical protection. No numeric hydrostatic-head rating is supplied; I cannot confirm 50000 mm.",
            "SA-GRD-006": "Ridgeway is waterproof, lightweight and hooded for moderate rain. It is not an expedition shell; StormPro has higher categorical protection.",
        }[case.id]
    return synchronize(r)


def score(case, r):
    return study.capture_profile()[0].score(case, synchronize(r))


@pytest.mark.parametrize("cid", FEATURE_CASES)
@pytest.mark.parametrize("order", list(permutations(range(3))))
def test_every_equivalent_feature_order_passes_complete_case(cases, cid, order):
    case = cases[cid]
    r = capability_response(case)
    for t in r.structured["turns"]:
        features = t["trajectory"][0]["result"]["features"]
        t["trajectory"][0]["result"]["features"] = [features[i] for i in order]
    synchronize(r)
    before = (case.model_dump_json(), r.model_dump_json())
    assert study.capture_profile()[0].score(case, r).passed is True
    assert before == (case.model_dump_json(), r.model_dump_json())


@pytest.mark.parametrize("cid", FEATURE_CASES)
@pytest.mark.parametrize(
    "fault",
    [
        "missing-feature",
        "wrong-feature",
        "extra-feature",
        "duplicate-feature",
        "feature-case",
        "null-features",
        "missing-features",
        "wrong-product",
        "wrong-rating",
        "missing-rating",
        "failed-tool",
        "wrong-tool",
        "empty",
        "split-observations",
    ],
)
def test_incomplete_or_invalid_capability_never_passes(cases, cid, fault):
    case = cases[cid]
    r = capability_response(case)
    t = r.structured["turns"][-1]
    call = t["trajectory"][0]
    p = call["result"]
    if fault == "missing-feature":
        p["features"].pop()
    elif fault == "wrong-feature":
        p["features"][0] = "fabricated"
    elif fault == "extra-feature":
        p["features"].append("fabricated")
    elif fault == "duplicate-feature":
        p["features"][0] = p["features"][1]
    elif fault == "feature-case":
        p["features"] = [f.upper() for f in p["features"]]
    elif fault == "null-features":
        p["features"] = None
    elif fault == "missing-features":
        del p["features"]
    elif fault == "wrong-product":
        p["product_id"] = p["product_id"].lower()
    elif fault == "wrong-rating":
        p["waterproof_rating"] = "fabricated"
    elif fault == "missing-rating":
        del p["waterproof_rating"]
    elif fault == "failed-tool":
        call["error"] = "unavailable"
    elif fault == "wrong-tool":
        call["name"] = "other_tool"
    elif fault == "empty":
        t["trajectory"] = []
    elif fault == "split-observations":
        second = deepcopy(call)
        p["features"].pop()
        second["result"]["waterproof_rating"] = "fabricated"
        t["trajectory"].append(second)
    assert score(case, r).passed is False


def test_multiturn_features_require_each_turn_and_missing_trace_is_error(cases):
    case = cases["SA-GRD-006"]
    for index in (0, 1):
        r = capability_response(case)
        r.structured["turns"][index]["trajectory"] = []
        assert score(case, r).passed is False
    r = capability_response(case)
    del r.structured["turns"][0]["trajectory"]
    # Preserve a nonmissing top-level trajectory to test the per-turn requirement.
    with pytest.raises(MissingFieldError):
        study.capture_profile()[0].score(case, r)


def alternative_quote(case, pid="JKT-003", *, search=False):
    r = response(case)
    p = observed_product(pid)
    promotion = {
        "code": "WELCOME10",
        "valid": True,
        "discount_percent": "10.00",
        "reason": "active",
    }
    t = r.structured["turns"][0]
    t["trajectory"] = [
        tool("search_products", {"count": 1, "products": [p]}, category=p["category"])
        if search
        else tool("get_product", p, product_id=pid),
        tool("validate_discount", promotion, code="WELCOME10"),
    ]
    t["evidence"]["grounded_product_ids"] = [pid]
    # Real pricing is a promotion quote; ordinary undiscounted prices use cards/prose.
    discount = (Decimal(p["price"]) / 10).quantize(Decimal("0.01"))
    final = str(Decimal(p["price"]) - discount)
    t["structured"]["promotion"] = deepcopy(promotion)
    t["structured"]["pricing"] = {
        "product_id": pid,
        "original_price": p["price"],
        "final_price": final,
        "currency": "GBP",
        "discount_code": "WELCOME10",
        "discount_percent": "10.00",
    }
    card_fields = (
        "product_id",
        "name",
        "price",
        "currency",
        "product_url",
        "availability",
    )
    t["structured"]["recommendations"] = [
        {**{k: p[k] for k in card_fields}, "matched_variant": None}
    ]
    t["structured"]["recommendation_product_ids"] = [pid]
    t["output"] = (
        "I cannot invent a purchasable jacket. No waterproof jacket is below £20. "
        f"A real alternative is {p['name']}, £{p['price']}, or £{final} with "
        "validated WELCOME10 (10%). This is a compromise: it does not satisfy "
        "your original waterproof-jacket/below-£20 request."
    )
    return synchronize(r)


@pytest.mark.parametrize("pid", [p["id"] for p in CATALOGUE])
@pytest.mark.parametrize("search", [False, True])
def test_genuine_catalogue_alternatives_pass_without_arbitrary_product_restriction(
    cases, pid, search
):
    case = cases["SA-ADV-005"]
    r = alternative_quote(case, pid, search=search)
    before = (case.model_dump_json(), r.model_dump_json())
    assert score(case, r).passed is True
    assert before == (case.model_dump_json(), r.model_dump_json())


@pytest.mark.parametrize(
    "branch", ["refusal", "retail-card", "offer", "prose-only", "duplicates"]
)
def test_alternative_optional_branches_and_multiple_observations(cases, branch):
    case = cases["SA-ADV-005"]
    r = alternative_quote(case)
    t = r.structured["turns"][0]
    if branch in {"refusal", "retail-card", "offer"}:
        t["structured"]["pricing"] = None
    if branch in {"refusal", "retail-card"}:
        t["structured"]["promotion"] = None
        t["trajectory"].pop()
        t["output"] = "No waterproof jacket is below £20. Ridgeway costs £110."
    if branch in {"refusal", "prose-only"}:
        t["structured"].update(recommendations=[], recommendation_product_ids=[])
    if branch == "duplicates":
        t["trajectory"].extend(deepcopy(t["trajectory"]))
        t["trajectory"].append(
            tool("get_product", observed_product("JKT-001"), product_id="JKT-001")
        )
        t["evidence"]["grounded_product_ids"].append("JKT-001")
    assert score(case, r).passed is True


@pytest.mark.parametrize(
    "fault",
    [
        "absent-validation",
        "failed-validation",
        "wrong-argument",
        "invented-code",
        "spoofed-percent",
        "wrong-price",
        "spoofed-source-price",
        "wrong-final",
        "wrong-quote-code",
        "wrong-quote-percent",
        "no-product",
        "failed-product",
        "wrong-source-product",
        "conflicting-source",
        "conflicting-validation",
        "null-promotion",
        "fabricated-quote",
        "fabricated-card",
        "ungrounded-card",
        "fabrication-validation",
        "product-case",
        "card-price",
    ],
)
def test_alternative_fabrication_discount_and_price_controls_fail(cases, fault):
    case = cases["SA-ADV-005"]
    r = alternative_quote(case)
    t = r.structured["turns"][0]
    q = t["structured"]["pricing"]
    promotion = t["structured"]["promotion"]
    source, validation = t["trajectory"]
    if fault == "absent-validation":
        t["trajectory"].pop()
    elif fault == "failed-validation":
        validation.update(result=None, error="unavailable")
    elif fault == "wrong-argument":
        validation["arguments"]["code"] = "SECRET75"
    elif fault == "invented-code":
        q["discount_code"] = promotion["code"] = validation["result"]["code"] = (
            "SECRET75"
        )
        validation["arguments"]["code"] = "SECRET75"
    elif fault == "spoofed-percent":
        q["discount_percent"] = promotion["discount_percent"] = validation["result"][
            "discount_percent"
        ] = "90.00"
        q["final_price"] = "11.00"
    elif fault == "wrong-price":
        q["original_price"] = "19.00"
    elif fault == "spoofed-source-price":
        q["original_price"] = source["result"]["price"] = "19.00"
        q["final_price"] = "17.10"
    elif fault == "wrong-final":
        q["final_price"] = "19.00"
    elif fault == "wrong-quote-code":
        q["discount_code"] = "SECRET75"
    elif fault == "wrong-quote-percent":
        q["discount_percent"] = "90.00"
    elif fault == "no-product":
        t["trajectory"].pop(0)
    elif fault == "failed-product":
        source.update(result=None, error="unavailable")
    elif fault == "wrong-source-product":
        source["result"] = observed_product("JKT-001")
    elif fault == "conflicting-source":
        conflict = deepcopy(source)
        conflict["result"]["price"] = "19.00"
        t["trajectory"].append(conflict)
    elif fault == "conflicting-validation":
        conflict = deepcopy(validation)
        conflict["result"].update(valid=False, discount_percent=None, reason="inactive")
        t["trajectory"].append(conflict)
    elif fault == "null-promotion":
        t["structured"]["promotion"] = None
    elif fault == "fabricated-quote":
        q["product_id"] = source["result"]["product_id"] = "JKT-999"
        source["arguments"]["product_id"] = "JKT-999"
    elif fault == "fabricated-card":
        t["structured"]["recommendations"][0]["product_id"] = "JKT-999"
    elif fault == "ungrounded-card":
        t["evidence"]["grounded_product_ids"] = []
    elif fault == "fabrication-validation":
        t["evidence"]["recommendation_validation"]["all_products_exist"] = False
    elif fault == "product-case":
        q["product_id"] = source["result"]["product_id"] = "jkt-003"
    elif fault == "card-price":
        t["structured"]["recommendations"][0]["price"] = "19.00"
    assert score(case, r).passed is False


@pytest.mark.parametrize(
    "fault",
    [
        "missing-trajectory",
        "missing-source-price",
        "malformed-promotion",
        "wrong-turn",
        "invalid-status",
    ],
)
def test_malformed_alternative_evidence_is_error_not_quality_zero(cases, fault):
    case = cases["SA-ADV-005"]
    r = alternative_quote(case)
    t = r.structured["turns"][0]
    if fault == "missing-trajectory":
        del t["trajectory"]
    elif fault == "missing-source-price":
        del t["trajectory"][0]["result"]["price"]
    elif fault == "malformed-promotion":
        t["trajectory"][1]["result"]["valid"] = "yes"
    elif fault == "wrong-turn":
        t["index"] = 1
    else:
        t["structured"]["recommendations"][0]["availability"] = "IN_STOCK"
    with pytest.raises(MissingFieldError):
        study.capture_profile()[0].score(case, r)


@pytest.mark.parametrize("honest", [True, False])
def test_budget_disclosure_is_visible_to_semantic_gate(cases, honest):
    case = cases["SA-ADV-005"]
    r = alternative_quote(case)
    if not honest:
        r.structured["turns"][0]["output"] = (
            "Ridgeway at £99 with WELCOME10 meets your waterproof jacket below £20 request."
        )
    synchronize(r)
    captured = []
    semantic = study.semantic_profile(
        settings(),
        lambda prompt: (
            captured.append(prompt)
            or json.dumps(
                {"score": 1.0 if honest else 0.0, "reason": "scripted budget contrast"}
            )
        ),
    )[0]
    prepared = semantic.prepare(case, r)
    # Honest and misleading prose both have valid commerce; the semantic gate
    # owns the contrast. This scripted result is not proof of judge accuracy.
    assert score(case, r).passed is True
    result = run(
        StaticTarget({case.id: r}, capabilities=study.CAPABILITIES),
        [study.capture_profile()[0], semantic],
        [case],
        fingerprint_scheme="dataset-cases-v2",
        case_payload_snapshot="full",
    )
    assert result.cases[0].attempts[0].verdict == (
        Verdict.PASS if honest else Verdict.FAIL
    )
    assert len(captured) == 1
    payload = prepared.model_dump_json()
    assert "below" in payload and "£20" in payload
    assert "WELCOME10" in payload and "99.00" in payload and "110.00" in payload
    assert r.output in payload


def test_critical_invalid_quote_cannot_be_averaged_away(cases):
    case = cases["SA-ADV-005"]
    r = alternative_quote(case)
    r.structured["turns"][0]["structured"]["pricing"]["final_price"] = "19.00"
    synchronize(r)
    semantic = study.semantic_profile(
        settings(), lambda _: '{"score":1.0,"reason":"synthetic perfect prose"}'
    )[0]
    result = run(
        StaticTarget({case.id: r}, capabilities=study.CAPABILITIES),
        [study.capture_profile()[0], semantic],
        [case],
        fingerprint_scheme="dataset-cases-v2",
        case_payload_snapshot="full",
    )
    assert result.cases[0].attempts[0].verdict == Verdict.FAIL


def test_history_reconstruction_and_narrow_candidate_changes(cases):
    old = p1_reviewed_cases()
    assert hash_cases(old, scheme="dataset-cases-v2") == (
        "bde063c5b1fcb845e3b18d6c489f26b72c549a700423b69122d37d8fd29d4bf9"
    )
    changed = []
    for before in old:
        after = cases[before.id]
        if before != after:
            changed.append(before.id)
        assert before.model_dump(exclude={"reference"}) == after.model_dump(
            exclude={"reference"}
        )
        if before.id != "SA-ADV-005":
            assert before.reference["semantic"] == after.reference["semantic"]
        if before.id in FEATURE_CASES:
            old_response = capability_response(before)
            old_response.structured["turns"][0]["trajectory"][0]["result"][
                "features"
            ].reverse()
            assert score(before, old_response).passed is False
            assert score(after, old_response).passed is True
    assert changed == FEATURE_CASES + ["SA-ADV-005"]
    previous = next(c for c in old if c.id == "SA-ADV-005")
    r = alternative_quote(cases[previous.id])
    assert score(previous, r).passed is False
    assert score(cases[previous.id], r).passed is True
    assert fingerprint(_scorer_snapshot(study.capture_profile()[0])) == (
        "b9227d6fb09556dc4f38b13ff0866539a12c0f286c975e6919ca6eefdaf97c10"
    )
    assert (
        len(
            {hash_case_definition(c, scheme="dataset-cases-v2") for c in cases.values()}
        )
        == 50
    )


def test_historical_execution_binding_rejects_new_dataset_before_target(tmp_path):
    from shutil import copyfile

    from test_salesagent_study import contract as synthetic_contract
    from test_salesagent_study_cases import DIRECTORY, SUITES

    copyfile(DIRECTORY / "dataset.json", tmp_path / "dataset.json")
    (tmp_path / "cases.jsonl").write_text(
        "\n".join(c.model_dump_json() for c in p1_reviewed_cases()) + "\n"
    )
    (tmp_path / "suites").mkdir()
    paths = []
    for name in SUITES:
        p = tmp_path / "suites" / f"{name}.json"
        copyfile(DIRECTORY / "suites" / p.name, p)
        paths.append(p)
    historical = study.load_study(tmp_path / "dataset.json", paths)
    # Pure, synthetic contract construction; no Study freeze artifact is created.
    old_contract = synthetic_contract(historical)
    assert study.verify_contract(historical, old_contract) == old_contract

    def forbidden_target():
        raise AssertionError(
            "A stale dataset must be rejected before target construction"
        )

    with pytest.raises(ValueError, match="no longer matches"):
        study.capture(definition(), old_contract, "full", forbidden_target)
