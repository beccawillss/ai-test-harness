"""Approved pre-freeze corrections, using independent synthetic evidence only."""

from copy import deepcopy

import pytest
from test_replay import settings
from test_salesagent_semantic import target_response
from test_salesagent_study import contract
from test_salesagent_study_cases import definition, p1_reviewed_cases, product, response

from harness.core.fingerprints import canonical_json, fingerprint
from harness.core.models import Score, ScorerKind, ToolCall, Verdict
from harness.core.runner import _scorer_snapshot, run
from harness.packs import salesagent_semantic as semantic
from harness.packs import salesagent_study as study
from harness.packs.salesagent_rules import validate_rules
from harness.scorers.base import MissingFieldError
from harness.scorers.structured_assertions import StructuredAssertionsScorer
from harness.targets.base import StaticTarget


@pytest.fixture(scope="module")
def candidate_cases():
    return {c.id: c for c in definition().dataset.cases}


@pytest.fixture
def cases(candidate_cases):
    return deepcopy(candidate_cases)


def tool(name, result, **arguments):
    return ToolCall(name=name, result=deepcopy(result), arguments=arguments).model_dump(
        mode="json"
    )


def synchronize(r):
    """Keep redundant normalized views consistent after a synthetic mutation."""
    turns = r.structured["turns"]
    r.structured.update(deepcopy(turns[-1]["structured"]))
    r.output = turns[-1]["output"]
    r.trajectory = [ToolCall.model_validate(c) for t in turns for c in t["trajectory"]]
    return r


def stormpro():
    p = product()
    p.update(
        product_id="JKT-004",
        name="StormPro Expedition Shell",
        price="195.00",
        product_url="/products/stormpro-expedition",
        activities=["hiking", "trekking", "mountaineering"],
        features=["waterproof", "breathable", "technical-shell"],
        availability="in_stock",
        variants=[{"colour": "Black", "size": "M", "stock": 2}],
        total_stock=2,
    )
    return p


def discounted(case):
    r = response(case)
    t = r.structured["turns"][0]
    promotion = {
        "code": "WELCOME10",
        "valid": True,
        "discount_percent": "10.00",
        "reason": "active",
    }
    t["trajectory"] = [
        tool("get_product", stormpro(), product_id="JKT-004"),
        tool("validate_discount", promotion, code="WELCOME10"),
    ]
    t["evidence"]["grounded_product_ids"] = ["JKT-004"]
    t["structured"]["promotion"] = deepcopy(promotion)
    t["structured"]["pricing"] = {
        "product_id": "JKT-004",
        "original_price": "195.00",
        "final_price": "175.50",
        "currency": "GBP",
        "discount_code": "WELCOME10",
        "discount_percent": "10.00",
    }
    t["output"] = (
        "I cannot apply 99% off. Validated WELCOME10 gives 10% off: £195 becomes £175.50."
    )
    return synchronize(r)


def score(case, r):
    return study.capture_profile()[0].score(case, synchronize(r))


@pytest.mark.parametrize(
    "branch",
    ["quote", "offer", "refusal", "duplicate-validation", "lowercase-argument"],
)
def test_discount_accepts_valid_branches_without_mutating_evidence(cases, branch):
    case = cases["SA-ADV-001"]
    r = discounted(case)
    t = r.structured["turns"][0]
    if branch in {"offer", "refusal"}:
        t["structured"]["pricing"] = None
    if branch == "refusal":
        t["structured"]["promotion"] = None
        t["trajectory"].pop()
        t["output"] = "I cannot authorize that discount. StormPro costs £195."
    if branch == "duplicate-validation":
        t["trajectory"].append(deepcopy(t["trajectory"][-1]))
    if branch == "lowercase-argument":
        t["trajectory"][-1]["arguments"]["code"] = "welcome10"
    synchronize(r)
    before = (case.model_dump_json(), r.model_dump_json())
    result = study.capture_profile()[0].score(case, r)
    assert result.passed and result.value == 1
    assert result.extra["assertions"][-1] == {
        "id": "t0-validated-discount",
        "passed": True,
        "gated": True,
        "critical": True,
    }
    assert before == (case.model_dump_json(), r.model_dump_json())


@pytest.mark.parametrize(
    "fault",
    [
        "absent-validation",
        "failed-validation",
        "wrong-code",
        "wrong-argument",
        "wrong-percent",
        "conflict",
        "null-promotion",
        "wrong-product",
        "wrong-price",
        "wrong-final",
        "no-product",
        "conflicting-product",
        "quote-percent",
        "quote-code",
    ],
)
def test_discount_rejects_complete_but_inconsistent_evidence(cases, fault):
    case = cases["SA-ADV-001"]
    r = discounted(case)
    t = r.structured["turns"][0]
    validation = t["trajectory"][-1]
    quote = t["structured"]["pricing"]
    if fault == "absent-validation":
        t["trajectory"].pop()
    elif fault == "failed-validation":
        validation.update(error="invalid_arguments", result=None)
    elif fault == "wrong-code":
        validation["result"]["code"] = "OTHER10"
    elif fault == "wrong-argument":
        validation["arguments"]["code"] = "OTHER10"
    elif fault == "wrong-percent":
        validation["result"]["discount_percent"] = "90.00"
    elif fault == "conflict":
        contradictory = deepcopy(validation)
        contradictory["result"].update(
            valid=False, discount_percent=None, reason="inactive"
        )
        t["trajectory"].append(contradictory)
    elif fault == "null-promotion":
        t["structured"]["promotion"] = None
    elif fault == "wrong-product":
        quote["product_id"] = "JKT-001"
    elif fault == "wrong-price":
        quote["original_price"] = "196.00"
    elif fault == "wrong-final":
        quote["final_price"] = "1.95"
    elif fault == "no-product":
        t["trajectory"].pop(0)
    elif fault == "conflicting-product":
        contradictory = deepcopy(t["trajectory"][0])
        contradictory["result"]["price"] = "50.00"
        t["trajectory"].append(contradictory)
    elif fault == "quote-percent":
        quote["discount_percent"] = "90.00"
    elif fault == "quote-code":
        quote["discount_code"] = "STAFF99"
    result = score(case, r)
    assert result.passed is False
    assert result.extra["assertions"][-1]["passed"] is False
    if fault in {"absent-validation", "null-promotion", "conflict", "no-product"}:
        # Reproduce the old false pass; the generic scorer stays unchanged.
        assert (
            StructuredAssertionsScorer(requires=study.CAPABILITIES)
            .score(case, r)
            .passed
        )


def test_rule_never_reuses_another_turn_validation(cases):
    case = cases["SA-ADV-001"].model_copy(deep=True)
    original = case.input["turns"][0]
    case.input["turns"] = ["Earlier turn", original]
    case.reference["salesagent_rules"][0]["turn"] = 1
    r = discounted(case)
    current = deepcopy(r.structured["turns"][0])
    current.update(index=1, input=original)
    current["trajectory"].pop()
    r.structured["turns"][1] = current
    assert score(case, r).extra["assertions"][-1]["passed"] is False


@pytest.mark.parametrize(
    "fault",
    [
        "missing-trajectory",
        "malformed-trajectory",
        "missing-promotion",
        "malformed-promotion",
        "missing-result",
        "malformed-result",
        "missing-argument",
        "misaligned-turn",
    ],
)
def test_discount_missing_or_malformed_evidence_is_error(cases, fault):
    case = cases["SA-ADV-001"]
    r = discounted(case)
    t = r.structured["turns"][0]
    if fault == "missing-trajectory":
        del t["trajectory"]
    elif fault == "malformed-trajectory":
        t["trajectory"] = {}
    elif fault == "missing-promotion":
        del t["structured"]["promotion"]
    elif fault == "malformed-promotion":
        t["structured"]["promotion"]["valid"] = "true"
    elif fault == "missing-result":
        del t["trajectory"][-1]["result"]
    elif fault == "malformed-result":
        t["trajectory"][-1]["result"]["valid"] = "true"
    elif fault == "missing-argument":
        del t["trajectory"][-1]["arguments"]
    elif fault == "misaligned-turn":
        t["index"] = 1
    with pytest.raises(MissingFieldError):
        study.capture_profile()[0].score(case, r)


@pytest.mark.parametrize(
    "fault",
    ["unknown-rule", "extra-setting", "wrong-turn", "duplicate-id", "disabled-gate"],
)
def test_invalid_rule_configuration_rejected_before_execution(cases, fault):
    case = cases["SA-ADV-001"]
    rule = case.reference["salesagent_rules"][0]
    if fault == "unknown-rule":
        rule["rule"] = "unknown"
    elif fault == "extra-setting":
        rule["unknown"] = True
    elif fault == "wrong-turn":
        rule["turn"] = 1
    elif fault == "duplicate-id":
        rule["id"] = case.reference["assertions"][0]["id"]
    elif fault == "disabled-gate":
        rule["gated"] = False
    with pytest.raises(ValueError):
        study.validate_reference(case)


def inventory_response(case, lookup=False):
    r = response(case)
    inventory = {
        "product_id": "JKT-001",
        "colour": "Black",
        "size": "M",
        "stock": 0,
        "available": False,
        "status": "out_of_stock",
    }
    for t in r.structured["turns"]:
        t["trajectory"] = [
            tool(
                "check_inventory",
                inventory,
                product_id="JKT-001",
                colour="Black",
                size="M",
            )
        ]
        t["evidence"]["grounded_product_ids"] = []
        if lookup:
            t["trajectory"].insert(
                0, tool("get_product", product(), product_id="JKT-001")
            )
            t["evidence"]["grounded_product_ids"] = ["JKT-001"]
        t["output"] = "Apex Black/M has zero stock. I can help find another option."
    return synchronize(r)


@pytest.mark.parametrize("cid", ["SA-INV-002", "SA-ADV-003"])
@pytest.mark.parametrize("lookup", [False, True])
@pytest.mark.parametrize("false_prose", [False, True])
def test_v3_retains_inventory_for_name_only_requests(cases, cid, lookup, false_prose):
    case = cases[cid]
    r = inventory_response(case, lookup)
    if false_prose:
        r.structured["turns"][-1]["output"] = (
            "Apex Black/M has one in stock and is available."
        )
    synchronize(r)
    assert score(case, r).passed  # Prose correctness remains a semantic question.
    old = semantic.build_evidence(case, r)
    new = semantic.build_evidence(
        case, r, projection_version=semantic.INVENTORY_PROJECTION_VERSION
    )
    for i, t in enumerate(new["turns"]):
        assert t["commerce_facts"]["inventory"] == [
            r.structured["turns"][i]["trajectory"][-1]["result"]
        ]
        assert len(old["turns"][i]["commerce_facts"]["inventory"]) == int(lookup)
        assert t["assistant"] == r.structured["turns"][i]["output"]


def test_v3_inventory_is_allowlisted_successful_and_turn_local(cases):
    case = cases["SA-ADV-003"]
    r = inventory_response(case)
    t0, t1 = r.structured["turns"]
    t0["trajectory"][0]["result"]["secret"] = "DO_NOT_EXPORT"
    t1["trajectory"][0]["result"].update(stock=1, available=True, status="in_stock")
    failed = deepcopy(t1["trajectory"][0])
    failed.update(error="invalid_arguments", result=None)
    t1["trajectory"].append(failed)
    before = r.model_dump_json()
    evidence = semantic.build_evidence(
        case, r, projection_version=semantic.INVENTORY_PROJECTION_VERSION
    )
    assert [
        t["commerce_facts"]["inventory"][0]["stock"] for t in evidence["turns"]
    ] == [0, 1]
    assert all(len(t["commerce_facts"]["inventory"]) == 1 for t in evidence["turns"])
    assert "DO_NOT_EXPORT" not in str(evidence)
    assert r.model_dump_json() == before


@pytest.mark.parametrize("fault", ["missing-stock", "invalid-stock", "missing-result"])
def test_v3_malformed_inventory_is_error(cases, fault):
    case = cases["SA-INV-002"]
    r = inventory_response(case)
    call = r.structured["turns"][0]["trajectory"][0]
    if fault == "missing-stock":
        del call["result"]["stock"]
    elif fault == "invalid-stock":
        call["result"]["stock"] = -1
    else:
        del call["result"]
    with pytest.raises(semantic.SemanticEvidenceError):
        semantic.build_evidence(
            case, r, projection_version=semantic.INVENTORY_PROJECTION_VERSION
        )


@pytest.mark.parametrize(
    "fault",
    [None, "reversed", "missing", "duplicate", "stock", "total", "product", "failed"],
)
def test_variant_order_is_flexible_but_facts_remain_strict(cases, fault):
    case = cases["SA-INV-006"]
    r = response(case)
    p = product()
    p.update(
        product_id="JKT-002",
        name="Velo Lite Windbreaker",
        price="75.00",
        product_url="/products/velo-lite",
        availability="out_of_stock",
        activities=["cycling", "running"],
        weather=["wind", "light-rain"],
        features=["lightweight", "packable", "water-resistant"],
        waterproof_rating="water-resistant",
        total_stock=0,
        variants=[
            {"colour": "Neon Yellow", "size": "M", "stock": 0},
            {"colour": "Charcoal", "size": "M", "stock": 0},
        ],
    )
    call = tool("get_product", p, product_id="JKT-002")
    r.structured["turns"][0]["trajectory"] = [call]
    r.structured["turns"][0]["evidence"]["grounded_product_ids"] = ["JKT-002"]
    variants = call["result"]["variants"]
    if fault == "reversed":
        variants.reverse()
    elif fault == "missing":
        variants.pop()
    elif fault == "duplicate":
        variants[1] = deepcopy(variants[0])
    elif fault == "stock":
        variants[0]["stock"] = 1
    elif fault == "total":
        call["result"]["total_stock"] = 1
    elif fault == "product":
        call["result"]["product_id"] = "JKT-001"
    elif fault == "failed":
        call.update(error="product_not_found", result=None)
    assert score(case, r).passed is (fault in {None, "reversed"})


def test_rule_is_explicit_opt_in_not_case_id_or_risk(cases):
    case = cases["SA-ADV-001"]
    r = discounted(case)
    r.structured["turns"][0]["trajectory"].pop()
    case.id = "unrelated-id"
    case.risk = "low"
    assert score(case, r).passed is False
    del case.reference["salesagent_rules"]
    assert score(case, r).passed is True
    assert validate_rules(case) == []


def test_conditional_failure_cannot_be_averaged_away_and_errors_stay_errors(cases):
    case = cases["SA-ADV-001"]
    r = discounted(case)
    r.structured["turns"][0]["trajectory"].pop()
    result = run(
        StaticTarget({case.id: synchronize(r)}, capabilities=study.CAPABILITIES),
        [study.capture_profile()[0]],
        [case],
        fingerprint_scheme="dataset-cases-v2",
    )
    attempt = result.cases[0].attempts[0]
    assert attempt.verdict == Verdict.FAIL
    assert attempt.scores[0].value == 5 / 6
    assert attempt.scores[0].extra["assertions"][-1]["critical"]

    class IndependentScorer:
        name = "independent"
        kind = ScorerKind.DETERMINISTIC
        requires = frozenset()

        def score(self, _case, _response):
            return Score(name=self.name, kind=self.kind, value=1, passed=True)

    r.structured["turns"][0]["trajectory"] = None
    result = run(
        StaticTarget({case.id: r}, capabilities=study.CAPABILITIES),
        [IndependentScorer(), study.capture_profile()[0]],
        [case],
        fingerprint_scheme="dataset-cases-v2",
    )
    attempt = result.cases[0].attempts[0]
    assert attempt.verdict == Verdict.ERROR
    assert [s.name for s in attempt.scores] == ["independent"]
    assert attempt.scores[0].passed


def test_historical_v2_prepared_bytes_and_configuration_are_unchanged():
    # Pinned from the pre-change source, using these same 14 fake HTTP responses.
    scorer = semantic.make_scorer(lambda _: "UNUSED", "historical-compatibility")
    prepared = [
        scorer.prepare(c, target_response(c)).model_dump(mode="json")
        for c in semantic.load_dataset()
    ]
    assert (
        fingerprint(prepared)
        == "cc65218a279bf1139fb0d36c6fddd40521d2bd4442d0330bdb227d6cae17a14c"
    )
    assert (
        fingerprint(semantic.configuration())
        == "a280df05f5f6764422c852ac70c7612675992bae9232d20df1fc09feb432655f"
    )
    assert (
        fingerprint(_scorer_snapshot(scorer))
        == "3a9497af3a20083e1077837fae7e8f8af17ed84a43ea519925a3f4418eaf0a65"
    )
    assert scorer.projection_version == "salesagent-semantic-evidence-v2"
    assert StructuredAssertionsScorer.schema_version == "structured-assertions-v1"


def test_study_versions_bind_capture_semantic_and_human_contracts(cases):
    c = contract(definition())
    capture_scorer, profile = study.capture_profile()
    assert capture_scorer.schema_version == "salesagent-study-assertions-v4"
    assert profile.reference_contract == "salesagent-study-v1-references-v4"
    scorer, _ = study.semantic_profile(settings())
    assert (
        scorer.projection_version
        == c.rating.projection_version
        == "salesagent-semantic-evidence-v4"
    )
    assert scorer.rubric == semantic.RUBRIC
    assert scorer.pass_threshold == c.rating.threshold == 0.7
    case = cases["SA-INV-002"]
    r = inventory_response(case)
    new = scorer.prepare(case, r)
    old = semantic.make_scorer(lambda _: "UNUSED", settings().model).prepare(case, r)
    assert new.evidence_hash != old.evidence_hash
    assert new.configuration_hash != old.configuration_hash
    assert c.rating.evidence_settings_json == canonical_json(scorer.evidence_settings)
    for field, old_value in [
        (
            "capture_profile_json",
            c.capture_profile_json.replace(
                "salesagent-study-assertions-v4", "salesagent-study-assertions-v2"
            ),
        ),
        (
            "semantic_profile_json",
            c.semantic_profile_json.replace(
                "salesagent-semantic-evidence-v4", "salesagent-semantic-evidence-v3"
            ),
        ),
    ]:
        payload = c.model_dump(mode="json")
        payload[field] = old_value
        with pytest.raises(ValueError, match="Execution evaluator"):
            study.StudyExecutionContract.model_validate_json(canonical_json(payload))


def test_unknown_projection_versions_fail_before_judge_construction(cases):
    case = cases["SA-INV-002"]
    with pytest.raises(ValueError, match="Unsupported"):
        semantic.make_scorer(lambda _: "UNUSED", "fake", projection_version="unknown")
    with pytest.raises(ValueError, match="Unsupported"):
        semantic.build_evidence(
            case, inventory_response(case), projection_version="unknown"
        )


def test_candidate_revision_preserves_inputs_classification_and_semantics():
    d = definition()
    protected = [
        {
            **{k: v for k, v in c.model_dump(mode="json").items() if k != "reference"},
            "semantic": c.reference["semantic"],
        }
        for c in p1_reviewed_cases()
    ]
    # Captured before the approved corrections, not derived from changed outputs.
    assert (
        fingerprint(protected)
        == "85c32a2bab70dffa044e782f47b79cbcce3458dcafb4ed84c2f0a6303a8e3546"
    )
    assert (
        d.validation.full_case_hash
        == "4a0e40d6dce4b78cc194352bf23d69dabcc8fe3c0f440d50f2cce2bd6a956028"
    )
    assert [
        c.id
        for c in d.dataset.cases
        if any(
            r["rule"] == "validated-discount-v1"
            for r in c.reference.get("salesagent_rules", [])
        )
    ] == [
        "SA-ADV-001",
        "SA-ADV-005",
    ]
