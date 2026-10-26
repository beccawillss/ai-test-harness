"""No-match proof policy over synthetic public evidence, never live outputs."""

import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest
from test_salesagent_study import contract
from test_salesagent_study_cases import definition, pre_no_match_cases, response
from test_salesagent_study_corrections import synchronize, tool
from test_salesagent_study_p2 import CATALOGUE, observed_product

from harness.core.case_fingerprints import hash_case_definition
from harness.core.dataset import hash_cases
from harness.core.fingerprints import fingerprint
from harness.core.models import Score, ScorerKind, Verdict
from harness.core.runner import run
from harness.packs import salesagent_semantic as semantic
from harness.packs import salesagent_study as study
from harness.packs.salesagent_search import validate_search_rules
from harness.scorers.base import MissingFieldError
from harness.targets._salesagent_contract import SearchArguments
from harness.targets.base import StaticTarget

IDS = ("SA-CON-002", "SA-CON-005", "SA-RCV-003", "SA-RCV-004")
CAPS = dict(zip(IDS, ("90.00", "80.00", "50.00", "70.00")))
HISTORY = json.loads(
    (
        Path(__file__).parent / "fixtures/salesagent_study/pre-no-match-oracles.json"
    ).read_text()
)


@pytest.fixture(scope="module")
def cases():
    return {c.id: c for c in definition().dataset.cases}


def observation(arguments, ids):
    return tool(
        "search_products",
        {"count": len(ids), "products": [observed_product(pid) for pid in ids]},
        **SearchArguments.model_validate(arguments).model_dump(mode="json"),
    )


def evidence(case, arguments=None, ids=()):
    args = {
        "category": "jacket",
        "maximum_price": CAPS[case.id],
        "features": ["waterproof"],
    }
    if arguments is not None:
        args = arguments
    r = response(
        case,
        constraints={
            "category": "jacket",
            "maximum_price": CAPS[case.id],
            "features": ["waterproof"],
        },
    )
    r.structured["turns"][0]["trajectory"].append(observation(args, ids))
    return synchronize(r)


def score(case, r):
    return study.capture_profile()[0].score(case, synchronize(r))


@pytest.mark.parametrize("cid", IDS)
def test_strict_waterproof_search_proves_no_match(cases, cid):
    case = cases[cid]
    r = evidence(case)
    before = case.model_dump_json(), r.model_dump_json()
    result = score(case, r)
    assert result.passed
    assert next(
        a for a in result.extra["assertions"] if a["id"] == "t0-no-exact-match"
    ) == {"id": "t0-no-exact-match", "passed": True, "gated": True, "critical": False}
    assert before == (case.model_dump_json(), r.model_dump_json())


@pytest.mark.parametrize("cid", IDS)
@pytest.mark.parametrize(
    "kind",
    [
        "budget-jackets",
        "all-jackets",
        "uncapped-waterproof",
        "broader-cap",
        "all-products",
    ],
)
def test_complete_broader_results_independently_prove_absence(cases, cid, kind):
    case = cases[cid]
    if kind == "budget-jackets":
        args = {"category": "jacket", "maximum_price": CAPS[cid]}
        ids = {
            "90.00": ["JKT-002", "JKT-005"],
            "80.00": ["JKT-002"],
            "50.00": [],
            "70.00": [],
        }[CAPS[cid]]
    elif kind == "all-jackets":
        args = {"category": "jacket"}
        ids = ["JKT-001", "JKT-002", "JKT-003", "JKT-004", "JKT-005", "INS-001"]
    elif kind == "uncapped-waterproof":
        args = {"category": "jacket", "features": ["waterproof"]}
        ids = ["JKT-001", "JKT-003", "JKT-004"]
    elif kind == "broader-cap":
        args = {"category": "jacket", "maximum_price": "110.00"}
        ids = ["JKT-002", "JKT-003", "JKT-005"]
    else:
        args = {}  # The complete reviewed catalogue is also a valid broad result.
        ids = [p["id"] for p in CATALOGUE]
    assert score(case, evidence(case, args, ids)).passed
    # Product/source order is immaterial; no copied target implementation is used.
    assert score(case, evidence(case, args, list(reversed(ids)))).passed


@pytest.mark.parametrize("cid", IDS)
def test_exact_four_previously_reported_false_passes_are_rejected(cases, cid):
    case = cases[cid]
    r = evidence(case)
    r.structured["turns"][0]["trajectory"][-1]["arguments"].update(
        features=["insulated"], activity="skiing"
    )
    old = next(c for c in pre_no_match_cases() if c.id == cid)
    assert (
        study.capture_profile(reference_contract=study.REFERENCE_CONTRACT)[0]
        .score(old, synchronize(r))
        .passed
    )
    assert score(case, r).passed is False


@pytest.mark.parametrize("cid", IDS)
@pytest.mark.parametrize(
    "restriction",
    [
        {"activity": "skiing"},
        {"weather": ["snow"]},
        {"colour": "Purple"},
        {"size": "XXXL"},
        {"in_stock_only": True},
        {"features": ["insulated"]},
        {"features": ["waterproof", "hooded"]},
        {"category": "trousers"},
        {"maximum_price": "1.00"},
    ],
)
def test_narrowed_empty_search_is_not_a_proof(cases, cid, restriction):
    case = cases[cid]
    r = evidence(case)
    r.structured["turns"][0]["trajectory"][-1]["arguments"].update(restriction)
    assert score(case, r).passed is False


@pytest.mark.parametrize("cid", IDS)
def test_independent_proof_can_coexist_with_exploration(cases, cid):
    case = cases[cid]
    r = evidence(case)
    r.structured["turns"][0]["trajectory"].insert(
        0, observation({"category": "jacket", "activity": "skiing"}, [])
    )
    assert score(case, r).passed


@pytest.mark.parametrize("cid", IDS)
@pytest.mark.parametrize(
    "fault",
    [
        "missing-record",
        "wrong-id",
        "wrong-price",
        "wrong-category",
        "wrong-features",
        "wrong-rating",
        "false-empty",
    ],
)
def test_complete_but_false_result_sets_fail(cases, cid, fault):
    case = cases[cid]
    r = evidence(
        case,
        {"category": "jacket"},
        ["JKT-001", "JKT-002", "JKT-003", "JKT-004", "JKT-005", "INS-001"],
    )
    result = r.structured["turns"][0]["trajectory"][-1]["result"]
    if fault == "missing-record":
        result["products"].pop()
        result["count"] -= 1
    elif fault == "false-empty":
        result.update(products=[], count=0)
    else:
        result["products"][0][
            {
                "wrong-id": "product_id",
                "wrong-price": "price",
                "wrong-category": "category",
                "wrong-features": "features",
                "wrong-rating": "waterproof_rating",
            }[fault]
        ] = {
            "wrong-id": "JKT-999",
            "wrong-price": "1.00",
            "wrong-category": "socks",
            "wrong-features": ["water-resistant"],
            "wrong-rating": "none",
        }[fault]
    assert score(case, r).passed is False
    # A contradictory successful relevant result is not erased by another proof.
    r.structured["turns"][0]["trajectory"].append(
        observation(
            {
                "category": "jacket",
                "features": ["waterproof"],
                "maximum_price": CAPS[cid],
            },
            [],
        )
    )
    assert score(case, r).passed is False


@pytest.mark.parametrize("cid", IDS)
@pytest.mark.parametrize(
    "fault",
    [
        "count",
        "duplicate",
        "missing-arguments",
        "null-arguments",
        "unknown-filter",
        "bad-filter-type",
        "missing-result",
        "bad-products",
        "bad-price",
    ],
)
def test_malformed_search_telemetry_is_error(cases, cid, fault):
    case = cases[cid]
    r = evidence(case)
    call = r.structured["turns"][0]["trajectory"][-1]
    if fault == "count":
        call["result"]["count"] = 1
    elif fault == "duplicate":
        call["result"] = {"count": 2, "products": [observed_product("JKT-001")] * 2}
    elif fault == "missing-arguments":
        del call["arguments"]
    elif fault == "null-arguments":
        call["arguments"] = None
    elif fault == "unknown-filter":
        call["arguments"]["unknown_filter"] = True
    elif fault == "bad-filter-type":
        call["arguments"]["in_stock_only"] = "false"
    elif fault == "missing-result":
        del call["result"]
    elif fault == "bad-products":
        call["result"]["products"] = None
    else:
        p = observed_product("JKT-001")
        p["price"] = "NaN"
        call["result"] = {"count": 1, "products": [p]}
    # Avoid regenerating the aggregate model from intentionally malformed telemetry.
    with pytest.raises(MissingFieldError):
        study.capture_profile()[0].score(case, r)


@pytest.mark.parametrize("cid", IDS)
def test_no_tool_or_failed_tool_is_quality_fail(cases, cid):
    case = cases[cid]
    r = evidence(case)
    r.structured["turns"][0]["trajectory"].pop()
    assert score(case, r).passed is False
    r.structured["turns"][0]["trajectory"].append(
        {
            "name": "search_products",
            "arguments": {},
            "result": None,
            "error": "invalid_arguments",
        }
    )
    assert score(case, r).passed is False


def test_turn_scope_budget_constraint_and_safe_label_policy(cases):
    case = cases["SA-CON-005"]
    r = evidence(case)
    call = r.structured["turns"][0]["trajectory"].pop()
    r.structured["turns"][1]["trajectory"].append(call)
    assert score(case, r).passed is False
    r = evidence(case)
    r.structured["turns"][0]["trajectory"][-1]["arguments"].update(
        category=" JACKET ", features=[" WATERPROOF "]
    )
    assert score(case, r).passed
    r.structured["turns"][0]["evidence"]["resolved_constraints"]["maximum_price"] = (
        "90.00"
    )
    assert score(case, r).passed is False


@pytest.mark.parametrize(
    "fault",
    [
        "unknown-rule",
        "duplicate-id",
        "bad-turn",
        "bad-budget",
        "duplicate-catalogue-id",
        "affordable-product",
        "wrong-source-hash",
    ],
)
def test_invalid_authoring_fails_preflight(cases, fault):
    case = deepcopy(cases["SA-CON-002"])
    rule = case.reference["salesagent_rules"][0]
    if fault == "unknown-rule":
        rule["rule"] = "unknown-v1"
    elif fault == "duplicate-id":
        rule["id"] = case.reference["assertions"][0]["id"]
    elif fault == "bad-turn":
        rule["turn"] = 99
    elif fault == "bad-budget":
        rule["maximum_price"] = "NaN"
    elif fault == "duplicate-catalogue-id":
        rule["catalogue"].append(deepcopy(rule["catalogue"][0]))
    elif fault == "affordable-product":
        rule["catalogue"][0]["price"] = "1.00"
    else:
        rule["catalogue_sha256"] = "unknown"
    with pytest.raises(ValueError):
        study.validate_reference(case)


def test_error_preserves_independent_scorer_and_fail_cannot_average_away(cases):
    class Independent:
        name = "independent"
        requires = frozenset()
        kind = ScorerKind.DETERMINISTIC

        def score(self, case, response):
            return Score(name=self.name, value=1.0, passed=True, kind=self.kind)

    case = cases["SA-CON-002"]
    r = evidence(case)
    r.structured["turns"][0]["trajectory"][-1]["result"]["count"] = 1
    result = run(
        StaticTarget({case.id: r}, capabilities=study.CAPABILITIES),
        [Independent(), study.capture_profile()[0]],
        [case],
        fingerprint_scheme="dataset-cases-v2",
    )
    attempt = result.cases[0].attempts[0]
    assert attempt.verdict == Verdict.ERROR
    assert [s.name for s in attempt.scores] == ["independent"]
    r = evidence(case)
    r.structured["turns"][0]["trajectory"][-1]["arguments"]["activity"] = "skiing"
    result = run(
        StaticTarget({case.id: r}, capabilities=study.CAPABILITIES),
        [Independent(), study.capture_profile()[0]],
        [case],
        fingerprint_scheme="dataset-cases-v2",
    )
    assert result.cases[0].attempts[0].verdict == Verdict.FAIL


def test_exact_scope_source_snapshot_and_version_pins(cases):
    historical = pre_no_match_cases()
    assert (
        hash_cases(historical, scheme="dataset-cases-v2") == HISTORY["full_case_hash"]
    )
    changed = []
    for before in historical:
        after = cases[before.id]
        if before != after:
            changed.append(before.id)
        assert before.model_dump(exclude={"reference"}) == after.model_dump(
            exclude={"reference"}
        )
        assert before.reference["semantic"] == after.reference["semantic"]
        if before.id in IDS:
            assert (
                hash_case_definition(before, scheme="dataset-cases-v2")
                == HISTORY["cases"][before.id]["definition_hash"]
            )
            rules = validate_search_rules(after)
            assert rules[0].maximum_price == Decimal(CAPS[before.id])
            assert [p.model_dump(mode="json") for p in rules[0].catalogue] == [
                {
                    "product_id": p["id"],
                    **{
                        k: p[k]
                        for k in ("category", "price", "features", "waterproof_rating")
                    },
                }
                for p in CATALOGUE
            ]
    assert tuple(changed) == IDS
    legacy = study.capture_profile(reference_contract=study.REFERENCE_CONTRACT)
    assert (
        fingerprint(legacy[1].model_dump(mode="json"))
        == "5f213df23d3281c4240b924b013c5740dca18343c113b81ff14d4086a69d1770"
    )
    assert study.capture_profile()[0].schema_version == "salesagent-study-assertions-v4"
    assert (
        study.capture_profile()[1].reference_contract == study.SEARCH_REFERENCE_CONTRACT
    )
    with pytest.raises(ValueError):
        study.capture_profile(reference_contract="unknown")


def test_legacy_contract_is_readable_but_rejected_for_revised_dataset_before_target():
    path = Path(__file__).parent / "fixtures/salesagent_study/pre-warmth-execution.json"
    archived = study.StudyExecutionContract.model_validate_json(path.read_text())
    assert (
        archived.digest
        == "e9f47d68a81aa476aeded815b83ffaed1a2ca6e2ec6b54074cb52ea478034219"
    )
    with pytest.raises(ValueError, match="no longer matches"):
        study.capture(
            definition(), archived, "full", lambda: pytest.fail("target constructed")
        )
    revised = contract(definition())
    payload = revised.model_dump(mode="json")
    payload["capture_profile_json"] = archived.capture_profile_json
    downgraded = study.StudyExecutionContract.model_validate_json(json.dumps(payload))
    with pytest.raises(ValueError):
        study.capture(
            definition(), downgraded, "full", lambda: pytest.fail("target constructed")
        )


@pytest.mark.parametrize("index", range(46))
def test_other_46_cases_keep_identical_outcomes(cases, index):
    case = [c for c in cases.values() if c.id not in IDS][index]
    r = response(
        case, cards=("JKT-003", "JKT-001"), constraints={"maximum_price": "150.00"}
    )
    before = study.capture_profile(reference_contract=study.REFERENCE_CONTRACT)[
        0
    ].score(case, r)
    after = study.capture_profile()[0].score(case, r)
    assert (before.value, before.passed, before.reason, before.extra["assertions"]) == (
        after.value,
        after.passed,
        after.reason,
        after.extra["assertions"],
    )


@pytest.mark.parametrize("cid", IDS)
def test_semantic_and_human_evidence_remains_identical_for_revised_references(
    cases, cid
):
    case = cases[cid]
    old = next(c for c in pre_no_match_cases() if c.id == cid)
    r = evidence(case)
    r.metadata.update(
        adapter_version="3", evidence_schema_version="salesagent-evidence-v3"
    )
    for turn in r.structured["turns"]:
        for call in turn["trajectory"]:
            if call["name"] == "get_product":
                call["result"]["warmth"] = next(
                    p["warmth"]
                    for p in CATALOGUE
                    if p["id"] == call["result"]["product_id"]
                )
    r = synchronize(r)
    assert score(case, r).passed
    assert semantic.build_evidence(
        old, r, projection_version=semantic.WARMTH_PROJECTION_VERSION
    ) == semantic.build_evidence(
        case, r, projection_version=semantic.WARMTH_PROJECTION_VERSION
    )


def test_missing_turn_telemetry_is_error_not_quality_failure(cases):
    case = cases["SA-CON-002"]
    for fault in (
        "missing-trajectory",
        "null-trajectory",
        "misaligned-index",
        "missing-turns",
    ):
        r = evidence(case)
        if fault == "missing-trajectory":
            del r.structured["turns"][0]["trajectory"]
        elif fault == "null-trajectory":
            r.structured["turns"][0]["trajectory"] = None
        elif fault == "misaligned-index":
            r.structured["turns"][0]["index"] = 7
        else:
            del r.structured["turns"]
        with pytest.raises(MissingFieldError):
            study.capture_profile()[0].score(case, r)
