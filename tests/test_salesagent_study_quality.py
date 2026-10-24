"""Approved label/projection corrections; all evidence and judgments are synthetic."""

import json
from copy import deepcopy

import pytest
from test_replay import settings
from test_salesagent_semantic import target_response
from test_salesagent_study import prepared
from test_salesagent_study_cases import definition, p1_reviewed_cases, product, response
from test_salesagent_study_corrections import inventory_response, synchronize, tool

from harness.core.fingerprints import fingerprint
from harness.core.models import Verdict
from harness.core.runner import _scorer_snapshot, run
from harness.core.store import SQLiteResultStore
from harness.packs import salesagent_semantic as semantic
from harness.packs import salesagent_study as study
from harness.packs.salesagent_rules import StudyAssertionsScorer
from harness.scorers.base import MissingFieldError
from harness.targets.base import StaticTarget

BUDGETS = {
    "SA-REC-001": ["160.00"],
    "SA-REC-002": ["120.00"],
    "SA-REC-003": ["220.00"],
    "SA-REC-008": ["150.00", "150.00"],
    "SA-CON-001": ["110.00"],
    "SA-CON-002": ["90.00"],
    "SA-CON-003": [None],
    "SA-CON-004": ["120.00", "160.00"],
    "SA-CON-005": ["80.00", "80.00"],
    "SA-CON-006": ["150.00"],
    "SA-CON-007": ["150.00", "150.00"],
    "SA-STA-001": [None, None],
    "SA-STA-002": ["115.00", "200.00"],
    "SA-STA-003": ["200.00", "200.00"],
    "SA-RCV-003": ["50.00"],
    "SA-RCV-004": ["70.00"],
}
INVENTORIES = {
    "SA-INV-001": [("JKT-001", "Ocean Blue", 4)],
    "SA-INV-002": [("JKT-001", "Black", 0)],
    "SA-INV-003": [("JKT-001", "Black", 0), ("JKT-001", "Ocean Blue", 4)],
    "SA-INV-004": [("JKT-003", "Ocean Blue", 3)],
    "SA-INV-005": [("JKT-004", "Black", 2)],
    "SA-STA-006": [("JKT-001", "Ocean Blue", 4), ("JKT-003", "Ocean Blue", 3)],
    "SA-ADV-003": [("JKT-001", "Black", 0), ("JKT-001", "Black", 0)],
}
NO_MATCH = {"SA-CON-002", "SA-CON-005", "SA-RCV-003", "SA-RCV-004"}


@pytest.fixture(scope="module")
def cases():
    return {c.id: c for c in definition().dataset.cases}


def valid_response(case):
    """Independent explicit fixture facts, not responses generated from assertions."""
    cards = () if case.id in NO_MATCH or case.id in INVENTORIES else ("JKT-003",)
    if case.id in {"SA-REC-003", "SA-INV-003"}:
        cards = ("JKT-001",)
    r = response(case, cards=cards)
    for i, turn in enumerate(r.structured["turns"]):
        constraints = turn["evidence"]["resolved_constraints"]
        if case.id in BUDGETS:
            constraints.update(
                features=["waterproof"], maximum_price=BUDGETS[case.id][i]
            )
        if case.id == "SA-CON-006":
            constraints.update(colour="Ocean Blue", size="M")
        if case.id == "SA-STA-003":
            constraints["colour"] = "Ocean Blue" if i == 0 else None
        if case.id in NO_MATCH and i == 0:
            constraints["category"] = "jacket"
            turn["trajectory"].append(
                tool(
                    "search_products",
                    {"count": 0, "products": []},
                    category="jacket",
                    maximum_price=BUDGETS[case.id][i],
                    features=["waterproof"],
                )
            )
        if case.id in INVENTORIES:
            pid, colour, stock = INVENTORIES[case.id][i]
            constraints.update(colour=colour, size="M")
            turn["trajectory"].append(
                tool(
                    "check_inventory",
                    {
                        "product_id": pid,
                        "colour": colour,
                        "size": "M",
                        "stock": stock,
                        "available": stock > 0,
                        "status": "in_stock" if stock else "out_of_stock",
                    },
                    product_id=pid,
                    colour=colour,
                    size="M",
                )
            )
    return synchronize(r)


@pytest.mark.parametrize("cid", sorted(BUDGETS | INVENTORIES))
def test_all_23_affected_candidates_accept_equivalent_labels(cases, cid):
    case = cases[cid]
    r = valid_response(case)
    new = study.capture_profile()[0]
    old = StudyAssertionsScorer(requires=study.CAPABILITIES)
    assert new.score(case, r).passed and old.score(case, r).passed
    for turn in r.structured["turns"]:
        c = turn["evidence"]["resolved_constraints"]
        c["features"] = [v.upper() for v in c["features"]]
        for key in ("colour", "size"):
            if c[key] is not None:
                c[key] = c[key].lower()
        for call in turn["trajectory"]:
            if call["name"] == "check_inventory":
                for key in ("colour", "size"):
                    call["result"][key] = call["result"][key].lower()
            if call["name"] == "search_products":
                call["arguments"]["category"] = "JACKET"
    synchronize(r)
    before = case.model_dump_json(), r.model_dump_json()
    assert new.score(case, r).passed
    assert old.score(case, r).passed is False
    assert before == (case.model_dump_json(), r.model_dump_json())


@pytest.mark.parametrize("cid", sorted(BUDGETS | INVENTORIES))
def test_all_23_affected_candidates_still_reject_wrong_labels(cases, cid):
    case = cases[cid]
    r = valid_response(case)
    for turn in r.structured["turns"]:
        if cid in BUDGETS:
            turn["evidence"]["resolved_constraints"]["features"] = ["Water-Resistant"]
        else:
            turn["trajectory"][-1]["result"]["size"] = "L"
    assert study.capture_profile()[0].score(case, synchronize(r)).passed is False


@pytest.mark.parametrize("label", ["insulated", "INSULATED", "Insulated"])
def test_real_soft_constraint_exclusion_rejects_all_capitalizations(cases, label):
    case = cases["SA-REC-008"]
    r = valid_response(case)
    r.structured["turns"][1]["evidence"]["resolved_constraints"]["features"].append(
        label
    )
    result = study.capture_profile()[0].score(case, synchronize(r))
    assert result.passed is False
    assert (
        next(
            a
            for a in result.extra["assertions"]
            if a["id"] == "insulation-remains-soft"
        )["passed"]
        is False
    )


def assertion_case(case, path, op, expected, **extra):
    return case.model_copy(
        update={
            "reference": {
                "assertions": [
                    {
                        "id": "label-control",
                        "path": path,
                        "op": op,
                        "expected": expected,
                        **extra,
                    }
                ]
            }
        },
        deep=True,
    )


@pytest.mark.parametrize(
    "op,expected,good,bad",
    [
        ("contains", "Waterproof", ["WATERPROOF"], ["water-resistant"]),
        ("excludes", "Insulated", ["WATERPROOF"], ["WATERPROOF", "INSULATED"]),
        ("subset", ["Waterproof"], ["WATERPROOF"], ["WATERPROOF", "Insulated"]),
        ("equals", ["Waterproof"], ["WATERPROOF"], ["water-resistant"]),
        ("matches", ["Waterproof"], ["WATERPROOF"], ["water-resistant"]),
        (
            "matches_any",
            [["Waterproof"], ["Breathable"]],
            ["WATERPROOF"],
            ["water-resistant"],
        ),
    ],
)
def test_label_collection_operators_have_positive_and_negative_controls(
    cases, op, expected, good, bad
):
    case = assertion_case(
        cases["SA-REC-001"],
        ["structured", "turns", 0, "evidence", "resolved_constraints", "features"],
        op,
        expected,
    )
    r = response(case)
    for values, passed in [(good, True), (bad, False)]:
        r.structured["turns"][0]["evidence"]["resolved_constraints"]["features"] = (
            values
        )
        assert study.capture_profile()[0].score(case, r).passed is passed


@pytest.mark.parametrize(
    "op", ["contains", "excludes", "subset", "matches", "matches_any"]
)
def test_named_inventory_patterns_and_quantifiers_preserve_exclusion_semantics(
    cases, op
):
    base = cases["SA-INV-002"]
    pattern = {"name": "check_inventory", "result": {"colour": "BLACK", "size": "m"}}
    path = ["structured", "turns", 0, "trajectory"]
    extra = {}
    if op == "matches_any":
        path += ["*"]
        extra = {"quantifier": "any"}
    elif op == "matches":
        path += [0]
    expected = [pattern] if op in {"subset", "matches_any"} else pattern
    case = assertion_case(base, path, op, expected, **extra)
    r = inventory_response(case)
    assert study.capture_profile()[0].score(case, r).passed is (op != "excludes")
    r.structured["turns"][0]["trajectory"][0]["result"]["colour"] = "Ocean Blue"
    assert study.capture_profile()[0].score(case, r).passed is (op == "excludes")


@pytest.mark.parametrize("op", ["equals", "matches", "matches_any"])
@pytest.mark.parametrize(
    "location",
    [
        "constraint-colour",
        "constraint-size",
        "inventory",
        "search",
        "top-level-inventory",
    ],
)
def test_scalar_labels_use_the_same_policy_for_actual_and_expected(cases, op, location):
    r = inventory_response(cases["SA-INV-002"])
    path = ["structured", "turns", 0]
    expected = "BLACK"
    if location.startswith("constraint"):
        key = "colour" if location.endswith("colour") else "size"
        path += ["evidence", "resolved_constraints", key]
        r.structured["turns"][0]["evidence"]["resolved_constraints"][key] = (
            "black" if key == "colour" else "m"
        )
        expected = "BLACK" if key == "colour" else "M"
    elif location == "search":
        path += ["trajectory", 0, "arguments", "category"]
        r.structured["turns"][0]["trajectory"] = [
            tool("search_products", {"products": [], "count": 0}, category="jacket")
        ]
        expected = "JACKET"
    elif location == "top-level-inventory":
        path = ["trajectory", 0, "result", "colour"]
    else:
        path += ["trajectory", 0, "result", "colour"]
    synchronize(r)
    case = assertion_case(
        cases["SA-INV-002"], path, op, [expected] if op == "matches_any" else expected
    )
    assert study.capture_profile()[0].score(case, r).passed
    assert (
        StudyAssertionsScorer(requires=study.CAPABILITIES).score(case, r).passed
        is False
    )


def test_expected_path_uses_the_same_nonmutating_label_view(cases):
    case = cases["SA-STA-006"].model_copy(deep=True)
    case.reference = {
        "assertions": [
            {
                "id": "retained-size",
                "path": [
                    "structured",
                    "turns",
                    1,
                    "evidence",
                    "resolved_constraints",
                    "size",
                ],
                "op": "equals",
                "expected_path": [
                    "structured",
                    "turns",
                    0,
                    "evidence",
                    "resolved_constraints",
                    "size",
                ],
            }
        ]
    }
    r = valid_response(cases["SA-STA-006"])
    r.structured["turns"][1]["evidence"]["resolved_constraints"]["size"] = "m"
    assert study.capture_profile()[0].score(case, r).passed
    r.structured["turns"][1]["evidence"]["resolved_constraints"]["size"] = "L"
    assert study.capture_profile()[0].score(case, r).passed is False
    case = assertion_case(
        cases["SA-STA-006"],
        ["structured", "turns", 1, "evidence", "resolved_constraints", "features", "*"],
        "equals",
        "Waterproof",
        quantifier="any",
    )
    r.structured["turns"][1]["evidence"]["resolved_constraints"]["features"] = [
        "WATERPROOF"
    ]
    assert study.capture_profile()[0].score(case, r).passed


@pytest.mark.parametrize(
    "path,expected,actual",
    [
        (["metadata", "colour"], "Black", "BLACK"),
        (
            ["structured", "turns", 0, "evidence", "resolved_constraints", "category"],
            "jacket",
            "JACKET",
        ),
        (
            ["structured", "turns", 0, "evidence", "resolved_constraints", "activity"],
            "hiking",
            "HIKING",
        ),
        (
            ["structured", "turns", 0, "evidence", "resolved_constraints", "weather"],
            ["wind"],
            ["WIND"],
        ),
        (
            ["structured", "turns", 0, "evidence", "resolved_constraints", "season"],
            "winter",
            "WINTER",
        ),
        (
            ["structured", "turns", 0, "evidence", "resolved_constraints", "priority"],
            "rain",
            "RAIN",
        ),
        (
            ["structured", "turns", 0, "trajectory", 0, "result", "product_id"],
            "JKT-001",
            "jkt-001",
        ),
        (
            ["structured", "turns", 0, "trajectory", 0, "result", "status"],
            "out_of_stock",
            "OUT_OF_STOCK",
        ),
        (["structured", "turns", 0, "trajectory", 0, "result", "stock"], 0, "0"),
        (["structured", "turns", 0, "trajectory", 0, "result", "available"], False, 0),
        (
            ["structured", "turns", 0, "trajectory", 0, "result", "colour"],
            "Ocean Blue",
            "Blue",
        ),
        (
            ["structured", "turns", 0, "trajectory", 0, "result", "colour"],
            "Black",
            " Black ",
        ),
    ],
)
def test_unapproved_values_and_aliases_keep_exact_semantics(
    cases, path, expected, actual
):
    case = assertion_case(cases["SA-INV-002"], path, "equals", expected)
    r = inventory_response(case)
    root = r.model_dump(mode="json")
    value = root
    for key in path[:-1]:
        value = value[key]
    value[path[-1]] = expected
    assert study.capture_profile()[0].score(case, type(r).model_validate(root)).passed
    value[path[-1]] = actual
    r = type(r).model_validate(root)
    assert study.capture_profile()[0].score(case, r).passed is False


@pytest.mark.parametrize(
    "name", ["get_product", "search_products", "CHECK_INVENTORY", "unrelated"]
)
def test_inventory_label_policy_does_not_apply_to_other_tool_results(cases, name):
    case = assertion_case(
        cases["SA-INV-002"],
        ["structured", "turns", 0, "trajectory"],
        "contains",
        {"name": name, "result": {"colour": "Black"}},
    )
    r = inventory_response(case)
    r.structured["turns"][0]["trajectory"][0].update(name=name)
    r.structured["turns"][0]["trajectory"][0]["result"]["colour"] = "BLACK"
    assert study.capture_profile()[0].score(case, r).passed is False


@pytest.mark.parametrize(
    "field,wrong",
    [
        ("product_id", "jkt-001"),
        ("stock", 1),
        ("stock", "0"),
        ("available", True),
        ("status", "OUT_OF_STOCK"),
    ],
)
def test_complete_inventory_response_still_rejects_unrelated_faults(
    cases, field, wrong
):
    case = cases["SA-INV-002"]
    r = valid_response(case)
    r.structured["turns"][0]["trajectory"][-1]["result"][field] = wrong
    assert study.capture_profile()[0].score(case, synchronize(r)).passed is False


def test_other_assertions_and_historical_feature_order_are_unchanged(cases):
    case = cases["SA-REC-001"]
    r = valid_response(case)
    r.structured["turns"][0]["structured"]["recommendations"][0]["price"] = "110.01"
    assert study.capture_profile()[0].score(case, r).passed is False
    case = cases["SA-GRD-003"]
    r = response(case)
    assert study.capture_profile()[0].score(case, r).passed
    r.structured["turns"][0]["trajectory"][0]["result"]["features"].reverse()
    assert study.capture_profile()[0].score(case, r).passed is True
    old = next(c for c in p1_reviewed_cases() if c.id == case.id)
    assert study.capture_profile()[0].score(old, r).passed is False
    # A dictionary masquerading as a feature list must not broaden label matching.
    case = assertion_case(
        cases["SA-REC-001"],
        ["structured", "turns", 0, "evidence", "resolved_constraints", "features"],
        "equals",
        {"*": "waterproof"},
    )
    r.structured["turns"][0]["evidence"]["resolved_constraints"]["features"] = {
        "*": "WATERPROOF"
    }
    assert study.capture_profile()[0].score(case, r).passed is False


@pytest.mark.parametrize("missing", ["features", "trajectory", "metadata"])
def test_comparison_keeps_missing_telemetry_as_error(cases, missing):
    case = cases["SA-REC-001"]
    r = valid_response(case)
    if missing == "features":
        del r.structured["turns"][0]["evidence"]["resolved_constraints"]["features"]
    elif missing == "trajectory":
        r.trajectory = None
    else:
        r.metadata = {}
    with pytest.raises(MissingFieldError):
        study.capture_profile()[0].score(case, r)


@pytest.mark.parametrize(
    "cid",
    [
        "SA-CON-002",
        "SA-CON-005",
        "SA-RCV-003",
        "SA-RCV-004",
        "SA-GRD-006",
        "SA-ADV-005",
        "SA-REC-007",
        "SA-STA-004",
    ],
)
def test_v4_retains_multiple_product_observations_without_cards(cases, cid):
    case = cases[cid]
    r = response(case)
    for turn in r.structured["turns"]:
        turn["output"] = (
            "An observed alternative could help if you change your requirements."
        )
    synchronize(r)
    before = r.model_dump_json()
    projected = semantic.build_evidence(
        case, r, projection_version=semantic.PRODUCT_PROJECTION_VERSION
    )
    for source, turn in zip(r.structured["turns"], projected["turns"]):
        assert [p["product_id"] for p in turn["commerce_facts"]["products"]] == [
            "JKT-001",
            "JKT-003",
        ]
        assert turn["assistant"] == source["output"]
        assert not turn["displayed_commerce"]["recommendations"]
    assert r.model_dump_json() == before


@pytest.mark.parametrize("truthful", [True, False])
def test_real_no_match_case_passes_capture_and_retains_prose_alternative_facts(
    cases, truthful
):
    case = cases["SA-CON-002"]
    r = valid_response(case)
    t = r.structured["turns"][0]
    t["output"] = (
        "Ridgeway costs £110, above your budget."
        if truthful
        else "Ridgeway costs £20 and meets your £90 budget."
    )
    synchronize(r)
    assert study.capture_profile()[0].score(case, r).passed
    for version, expected_ids in [
        (semantic.INVENTORY_PROJECTION_VERSION, []),
        (semantic.PRODUCT_PROJECTION_VERSION, ["JKT-001", "JKT-003"]),
    ]:
        evidence = semantic.build_evidence(case, r, projection_version=version)
        assert [
            p["product_id"] for p in evidence["turns"][0]["commerce_facts"]["products"]
        ] == expected_ids
        assert evidence["turns"][0]["assistant"] == t["output"]


def test_v4_preserves_order_conflicts_and_turn_local_provenance(cases):
    case = cases["SA-CON-005"]
    r = response(case)
    p = product("JKT-003")
    p.update(secret="PRIVATE", warmth="shell", season=["winter"])
    conflict = deepcopy(p)
    conflict["price"] = "111.00"
    t0, t1 = r.structured["turns"]
    t0["trajectory"] = [
        tool("search_products", {"products": [p, product()], "count": 2}),
        tool("get_product", conflict),
        tool("get_product", None),
    ]
    t0["trajectory"][-1]["error"] = "product_not_found"
    t1["trajectory"] = [tool("get_product", product())]
    synchronize(r)
    e = semantic.build_evidence(
        case, r, projection_version=semantic.PRODUCT_PROJECTION_VERSION
    )
    observations = [
        [(p["product_id"], p["price"]) for p in t["commerce_facts"]["products"]]
        for t in e["turns"]
    ]
    assert observations == [
        [("JKT-003", "110.00"), ("JKT-001", "145.00"), ("JKT-003", "111.00")],
        [("JKT-001", "145.00")],
    ]
    assert "PRIVATE" not in json.dumps(e)
    assert all(
        "warmth" not in p and "season" not in p
        for t in e["turns"]
        for p in t["commerce_facts"]["products"]
    )
    r.structured["turns"][0]["trajectory"] = []
    e = semantic.build_evidence(
        case, r, projection_version=semantic.PRODUCT_PROJECTION_VERSION
    )
    assert not e["turns"][0]["commerce_facts"][
        "products"
    ]  # Later evidence never backfills.
    fresh = response(cases["SA-RCV-001"])
    for t in fresh.structured["turns"]:
        t["trajectory"] = []
    assert all(
        not t["commerce_facts"]["products"]
        for t in semantic.build_evidence(
            cases["SA-RCV-001"],
            fresh,
            projection_version=semantic.PRODUCT_PROJECTION_VERSION,
        )["turns"]
    )


def test_v4_preserves_inventory_fix_and_promotion_selection(cases):
    case = cases["SA-INV-002"]
    r = inventory_response(case)
    r.structured["turns"][0]["trajectory"].append(
        tool(
            "validate_discount",
            {
                "code": "UNMENTIONED",
                "valid": False,
                "discount_percent": None,
                "reason": "unknown_code",
            },
        )
    )
    e = semantic.build_evidence(
        case, r, projection_version=semantic.PRODUCT_PROJECTION_VERSION
    )
    assert e["turns"][0]["commerce_facts"]["inventory"][0]["stock"] == 0
    assert not e["turns"][0]["commerce_facts"]["promotions"]


@pytest.mark.parametrize(
    "fault",
    [
        "missing-price",
        "negative-stock",
        "missing-result",
        "misaligned-turn",
        "final-output",
    ],
)
def test_v4_errors_before_fake_judge_for_malformed_observations(cases, fault):
    case = cases["SA-CON-002"]
    r = valid_response(case)
    t = r.structured["turns"][0]
    if fault == "missing-price":
        del t["trajectory"][0]["result"]["price"]
    elif fault == "negative-stock":
        t["trajectory"][0]["result"]["total_stock"] = -1
    elif fault == "missing-result":
        del t["trajectory"][0]["result"]
    elif fault == "misaligned-turn":
        t["index"] = 1
    else:
        r.output = "uncorrelated"
    calls = []
    scorer = study.semantic_profile(
        settings(),
        lambda prompt: calls.append(prompt) or '{"score":1.0,"reason":"synthetic"}',
    )[0]
    with pytest.raises(semantic.SemanticEvidenceError):
        scorer.prepare(case, r)
    assert calls == []


def test_v4_execution_error_preserves_independent_deterministic_results(cases):
    case = cases["SA-CON-002"]
    r = valid_response(case)
    del r.structured["turns"][0]["trajectory"][0]["result"]["price"]
    calls = []
    scorer = study.semantic_profile(
        settings(),
        lambda prompt: calls.append(prompt) or '{"score":1.0,"reason":"synthetic"}',
    )[0]
    result = run(
        StaticTarget({case.id: r}, capabilities=study.CAPABILITIES),
        [study.capture_profile()[0], scorer],
        [case],
        fingerprint_scheme="dataset-cases-v2",
    )
    attempt = result.cases[0].attempts[0]
    assert attempt.verdict == Verdict.ERROR
    assert len(attempt.scores) == 1 and attempt.scores[0].passed
    assert calls == []


def test_v4_utf8_payload_limit_is_exact_and_never_truncates(cases):
    case = cases["SA-CON-002"]
    r = valid_response(case)
    t = r.structured["turns"][0]
    t["output"] = ""
    synchronize(r)
    e = semantic.build_evidence(
        case, r, projection_version=semantic.PRODUCT_PROJECTION_VERSION
    )
    overhead = len(
        json.dumps(e, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    )
    remaining = semantic.PAYLOAD_LIMIT - overhead
    t["output"] = "é" * (remaining // 2) + "x" * (remaining % 2)
    synchronize(r)
    e = semantic.build_evidence(
        case, r, projection_version=semantic.PRODUCT_PROJECTION_VERSION
    )
    assert (
        len(json.dumps(e, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))
        == semantic.PAYLOAD_LIMIT
    )
    assert e["turns"][0]["assistant"] == r.output
    t["output"] += "x"
    synchronize(r)
    with pytest.raises(semantic.SemanticEvidenceError):
        semantic.build_evidence(
            case, r, projection_version=semantic.PRODUCT_PROJECTION_VERSION
        )


def test_previous_scorer_and_semantic_bindings_remain_reproducible(cases, tmp_path):
    # Pre-change hashes also cover the no-card inventory branch that separates v2/v3.
    for cid, v2_hash, v3_hash in [
        (
            "SA-INV-002",
            "bf134726472e092968eba6f3bf1c07917ac286abf3ac90bce24b678719d0618d",
            "24c21b93dde3bc9d932ffc9b1a5bd7169569358cf31fbb8de697b502ca233cde",
        ),
        (
            "SA-ADV-003",
            "eba5fc3c684a16ee58cfb5817f61358be475a0d18efe4a61c63a21d77c521431",
            "0a8aa5d6660e097c729fb88bf9c374ec7c056de59e26a7a5844c16a02fca5637",
        ),
    ]:
        for version, expected_hash in [
            (semantic.PROJECTION_VERSION, v2_hash),
            (semantic.INVENTORY_PROJECTION_VERSION, v3_hash),
        ]:
            assert (
                fingerprint(
                    semantic.build_evidence(
                        cases[cid],
                        inventory_response(cases[cid]),
                        projection_version=version,
                    )
                )
                == expected_hash
            )
    for version, prepared_hash, config_hash in [
        (
            semantic.PROJECTION_VERSION,
            "cc65218a279bf1139fb0d36c6fddd40521d2bd4442d0330bdb227d6cae17a14c",
            "3a9497af3a20083e1077837fae7e8f8af17ed84a43ea519925a3f4418eaf0a65",
        ),
        (
            semantic.INVENTORY_PROJECTION_VERSION,
            "a363807a4e21ac9d07f83b94be857289296948d53d96a4ad6c059d04c34233f1",
            "f347fbadb8b9a261030a23238405b8b456eb8e30e76e85730ec166747b1ad2ac",
        ),
    ]:
        scorer = semantic.make_scorer(
            lambda _: "UNUSED", "historical-compatibility", projection_version=version
        )
        assert (
            fingerprint(
                [
                    scorer.prepare(c, target_response(c)).model_dump(mode="json")
                    for c in semantic.load_dataset()
                ]
            )
            == prepared_hash
        )
        assert fingerprint(_scorer_snapshot(scorer)) == config_hash
    old = StudyAssertionsScorer(requires=study.CAPABILITIES)
    assert (
        fingerprint(_scorer_snapshot(old))
        == "8697a7c138e4b36c2dcca0e0e0c28720086a5d9f68e5a44242156aa96b2be345"
    )
    assert (
        fingerprint(
            [
                old.score(c, response(c, cards=("JKT-001", "JKT-003"))).model_dump(
                    mode="json"
                )
                for c in p1_reviewed_cases()
            ]
        )
        == "4472d4d02a8092e9c5e999b8ea689d9b0326f7250961cfbc074b902352394d7d"
    )
    source = run(
        StaticTarget(
            {cases["SA-REC-001"].id: valid_response(cases["SA-REC-001"])},
            capabilities=study.CAPABILITIES,
        ),
        [old],
        [cases["SA-REC-001"]],
        fingerprint_scheme="dataset-cases-v2",
        case_payload_snapshot="full",
    )
    store = SQLiteResultStore(tmp_path / "historical.sqlite")
    store.save(source)
    assert store.load(source.run_id) == source


def test_human_judge_v4_bindings_and_stale_versions_are_checked(tmp_path):
    d, c, source, prep, _store, loader = prepared(tmp_path)
    manifest = study.human_manifest(d, c, prep, loader)
    assert manifest.contract.projection_version == semantic.PRODUCT_PROJECTION_VERSION
    assert len(manifest.examples) == 12
    requests = {r.request_id: r for r in prep.bundle.requests}
    for example in manifest.examples:
        request = requests[example.prepared.request_id]
        assert example.prepared == request
        manifest.contract.check_prepared(request)
        r = (
            next(row for row in source.cases if row.case_id == request.source.case_id)
            .attempts[0]
            .response
        )
        assert r is not None
        direct = study.semantic_profile(c.evaluator.judge)[0].prepare(
            next(case for case in d.dataset.cases if case.id == request.source.case_id),
            r,
        )
        assert request.prepared == direct
    for field, old, new in [
        (
            "capture_profile_json",
            "salesagent-study-assertions-v3",
            "salesagent-study-assertions-v2",
        ),
        (
            "capture_profile_json",
            "salesagent-study-v1-references-v3",
            "salesagent-study-v1-references-v2",
        ),
        (
            "semantic_profile_json",
            semantic.PRODUCT_PROJECTION_VERSION,
            semantic.INVENTORY_PROJECTION_VERSION,
        ),
    ]:
        payload = c.model_dump(mode="json")
        payload[field] = payload[field].replace(old, new)
        with pytest.raises(ValueError, match="Execution evaluator"):
            study.StudyExecutionContract.model_validate_json(json.dumps(payload))
    assert study.capture_profile()[0].schema_version == "salesagent-study-assertions-v3"
    assert (
        definition().validation.full_case_hash
        == "4db62cceec19881853a2d921e886edd4866cfef976b5c209bd06da486ec5e257"
    )
