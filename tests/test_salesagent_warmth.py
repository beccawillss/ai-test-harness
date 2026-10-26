"""Opt-in warmth evidence: offline public-contract fixtures and frozen bindings."""

import importlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from shutil import copyfile

import httpx
import pytest
from test_replay import settings
from test_salesagent_semantic import target_response
from test_salesagent_study import target_freeze
from test_salesagent_study_cases import definition, pre_no_match_cases, response
from test_salesagent_study_corrections import inventory_response, synchronize, tool
from test_salesagent_study_p2 import CATALOGUE, observed_product
from test_salesagent_target import FakeHTTP

from harness.core.calibration import blind_packet
from harness.core.fingerprints import canonical_json, fingerprint
from harness.core.models import TargetResponse, Verdict
from harness.core.prospective_io import ProspectiveStore
from harness.core.runner import run
from harness.core.store import SQLiteResultStore
from harness.packs import salesagent_semantic as semantic
from harness.packs import salesagent_study as study
from harness.targets.salesagent import (
    EVIDENCE_VERSION,
    WARMTH_EVIDENCE_VERSION,
    SalesAgentError,
    SalesAgentTarget,
)

V5 = semantic.WARMTH_PROJECTION_VERSION
FIXTURES = Path(__file__).parent / "fixtures/salesagent_study"
WARM_CASES = ("SA-REC-004", "SA-REC-008", "SA-GRD-002", "SA-RCV-005")
BAD_WARMTH = (None, "", "HIGH", " high ", "very-warm", 3, 20.0, True, [], {})


@pytest.fixture(scope="module")
def cases():
    return {c.id: c for c in definition().dataset.cases}


def product(pid):
    """Independent reviewed catalogue snapshot; never build facts from assertions."""
    p = observed_product(pid)
    p["warmth"] = next(p["warmth"] for p in CATALOGUE if p["id"] == pid)
    return p


def complete_response(case, mode="lookup"):
    """Complete normalized doubles; only four scenarios need special positive prose."""
    r = response(
        case,
        cards=("JKT-003",),
        constraints={"maximum_price": "150.00", "features": ["waterproof"]},
    )
    pid = "INS-001" if case.id == "SA-REC-004" else "JKT-003"
    for i, t in enumerate(r.structured["turns"]):
        products = [product("INS-001"), product("JKT-003")]
        if mode == "search":
            t["trajectory"] = [
                tool(
                    "search_products",
                    {"count": 2, "products": products},
                    category="jacket",
                )
            ]
            if case.id == "SA-GRD-002":  # Approved mandatory lookup remains in force.
                t["trajectory"].append(
                    tool("get_product", products[0], product_id="INS-001")
                )
        else:
            t["trajectory"] = [
                tool("get_product", p, product_id=p["product_id"]) for p in products
            ]
        t["evidence"]["grounded_product_ids"] = [p["product_id"] for p in products]
        if case.id in {"SA-REC-004", "SA-REC-008"}:
            p = product(pid)
            fields = (
                "product_id",
                "name",
                "price",
                "currency",
                "product_url",
                "availability",
            )
            t["structured"]["recommendations"] = [
                {**{k: p[k] for k in fields}, "matched_variant": None}
            ]
            t["structured"]["recommendation_product_ids"] = [pid]
        if case.id == "SA-REC-004":
            t["output"] = (
                "Cairn at £130 prioritises insulation for cold, dry use. Its warmth category is high, but it is not waterproof. Ridgeway is a rain shell."
            )
        elif case.id == "SA-REC-008":
            t["output"] = (
                "Ridgeway costs £110 and meets waterproof/£150 requirements; it is lightweight and blue."
                if i == 0
                else "Waterproofing and £150 remain hard limits. Ridgeway is a shell; no jacket combines all your preferences. Cairn is insulated but not waterproof. Insulation remains a compromise, not a hard filter."
            )
        elif case.id == "SA-GRD-002":
            t["output"] = (
                "Cairn is insulated, warm and wind-resistant with high categorical warmth, but has no waterproof protection. Ridgeway is a waterproof shell for rain."
            )
        elif case.id == "SA-RCV-005":
            t["output"] = (
                "Cairn offers insulation for cold/dry use; Ridgeway offers moderate rain protection as a shell. Which conditions and stopping time matter most? You have not chosen a priority."
            )
    r.metadata.update(
        evidence_schema_version=WARMTH_EVIDENCE_VERSION, adapter_version="3"
    )
    return synchronize(r)


def mock_http(cases, mode="lookup", alter=None):
    """Expose synthetic responses through the public HTTP boundary, with no network."""
    scripts = {
        text: t
        for c in cases
        for text, t in zip(
            c.input["turns"], complete_response(c, mode).structured["turns"]
        )
    }

    def mutate(request, payload):
        message = (
            json.loads(request.content)["message"]
            if request.method == "POST"
            else payload["user_message"]
        )
        t = scripts[message]
        if request.method == "POST":
            payload.update(deepcopy(t["structured"]))
            payload["message"] = t["output"]
        else:
            payload["resolved_constraints"] = deepcopy(
                t["evidence"]["resolved_constraints"]
            )
            payload["constraint_changes"] = []
            payload["recommended_product_ids"] = t["structured"][
                "recommendation_product_ids"
            ]
            calls = []
            for seq, call in enumerate(t["trajectory"], 1):
                result = deepcopy(call["result"])
                records = (
                    result["products"]
                    if call["name"] == "search_products"
                    else [result]
                )
                for record in records:
                    record.update(season=["winter"], secret="PRIVATE_EXTRA")
                calls.append(
                    {
                        "sequence": seq,
                        "tool_call_id": f"call-{seq}",
                        "tool_name": call["name"],
                        "arguments": call["arguments"],
                        "status": "success",
                        "duration_ms": 1,
                        "result": {
                            "tool_name": call["name"],
                            "success": True,
                            "data": result,
                            "error": None,
                        },
                    }
                )
            payload["tool_calls"] = calls
            if alter:
                alter(payload)

    return FakeHTTP(mutate)


def target(fake, evidence_version=WARMTH_EVIDENCE_VERSION):
    return SalesAgentTarget(
        "http://fake",
        target_revision="1" * 40,
        evidence_version=evidence_version,
        transport=httpx.MockTransport(fake),
    )


def new_contract(d):
    return study.freeze_execution(
        d,
        target_freeze(
            adapter_version="3", evidence_schema_version=WARMTH_EVIDENCE_VERSION
        ),
        settings(),
        diagnostic_judge_calls=3,
        author_review="SYNTHETIC warmth compatibility only",
        reviewed_at=datetime.now(UTC),
        projection_version=V5,
    )


@pytest.mark.parametrize("cid", WARM_CASES)
@pytest.mark.parametrize("mode", ["lookup", "search"])
def test_all_four_real_cases_preserve_associated_warmth_through_adapter(
    cases, cid, mode
):
    case = cases[cid]
    fake = mock_http([case], mode)
    with_target = target(fake)
    try:
        r = with_target.invoke(case)
        assert with_target.configuration["adapter_version"] == "3"
        assert (
            with_target.configuration["evidence_schema_version"]
            == WARMTH_EVIDENCE_VERSION
        )
    finally:
        with_target.close()
    assert study.capture_profile()[0].score(case, r).passed is True
    assert TargetResponse.model_validate_json(r.model_dump_json()) == r
    projected = semantic.build_evidence(case, r, projection_version=V5)
    for i, t in enumerate(r.structured["turns"]):
        expected = [
            (p["product_id"], p["warmth"])
            for call in t["trajectory"]
            for p in (
                call["result"]["products"]
                if call["name"] == "search_products"
                else [call["result"]]
            )
        ]
        assert [
            (p["product_id"], p["warmth"])
            for p in projected["turns"][i]["commerce_facts"]["products"]
        ] == expected
        assert ("INS-001", "high") in expected and ("JKT-003", "shell") in expected
    assert "PRIVATE_EXTRA" not in r.model_dump_json()
    assert '"season":[' not in r.model_dump_json()
    assert "PRIVATE_EXTRA" not in json.dumps(projected)
    aggregate = [
        p
        for call in r.trajectory
        for p in (
            call.result["products"] if call.name == "search_products" else [call.result]
        )
    ]
    assert [(p["product_id"], p["warmth"]) for p in aggregate] == [
        (p["product_id"], p["warmth"])
        for t in projected["turns"]
        for p in t["commerce_facts"]["products"]
    ]
    for req in fake.requests:
        if req.method == "POST":
            assert set(json.loads(req.content)) <= {"message", "session_id"}


@pytest.mark.parametrize("pid", [p["id"] for p in CATALOGUE])
@pytest.mark.parametrize("mode", ["lookup", "search"])
def test_all_authoritative_categories_remain_exact_and_unranked(cases, pid, mode):
    case = cases["SA-RCV-005"]
    r = complete_response(case)
    p = product(pid)
    r.structured["turns"][0]["trajectory"] = [
        tool("get_product", p, product_id=pid)
        if mode == "lookup"
        else tool("search_products", {"count": 1, "products": [p]})
    ]
    synchronize(r)
    facts = semantic.build_evidence(case, r, projection_version=V5)["turns"][0][
        "commerce_facts"
    ]["products"]
    assert (
        len(facts) == 1
        and facts[0]["product_id"] == pid
        and facts[0]["warmth"] == p["warmth"]
    )
    assert isinstance(facts[0]["warmth"], str)


@pytest.mark.parametrize("bad", (*BAD_WARMTH, "MISSING"))
@pytest.mark.parametrize("mode", ["lookup", "search"])
def test_adapter_rejects_malformed_warmth_as_error(cases, bad, mode):
    case = cases["SA-REC-004"]

    def alter(payload):
        raw = payload["tool_calls"][0]["result"]["data"]
        if mode == "search":
            raw = raw["products"][0]
        if bad == "MISSING":
            del raw["warmth"]
        else:
            raw["warmth"] = bad

    fake = mock_http([case], mode, alter)
    with pytest.raises(SalesAgentError, match="malformed contract evidence"):
        t = target(fake)
        try:
            t.invoke(case)
        finally:
            t.close()


@pytest.mark.parametrize("bad", (*BAD_WARMTH, "MISSING"))
@pytest.mark.parametrize("mode", ["lookup", "search"])
def test_projection_rejects_missing_or_malformed_source_warmth_before_judge(
    cases, bad, mode
):
    case = cases["SA-REC-004"]
    r = complete_response(case, mode)
    raw = r.structured["turns"][0]["trajectory"][0]["result"]
    if mode == "search":
        raw = raw["products"][0]
    if bad == "MISSING":
        del raw["warmth"]
    else:
        raw["warmth"] = bad
    r.structured["turns"][0]["structured"]["recommendations"][0]["warmth"] = "high"
    synchronize(r)
    calls = []
    scorer = study.semantic_profile(
        settings(),
        lambda p: calls.append(p) or '{"score":1,"reason":"unused"}',
        projection_version=V5,
    )[0]
    with pytest.raises(semantic.SemanticEvidenceError):
        scorer.prepare(case, r)
    assert calls == []


def test_observation_order_conflicts_and_turn_isolation(cases):
    case = cases["SA-RCV-005"]
    r = complete_response(case)
    a, b = product("INS-001"), product("JKT-003")
    conflict = deepcopy(a)
    conflict["warmth"] = "shell"
    r.structured["turns"][0]["trajectory"] = [
        tool("get_product", b),
        tool("get_product", a),
        tool("search_products", {"products": [conflict, b], "count": 2}),
    ]
    synchronize(r)
    payload = semantic.build_evidence(case, r, projection_version=V5)
    assert [
        (p["product_id"], p["warmth"])
        for p in payload["turns"][0]["commerce_facts"]["products"]
    ] == [
        ("JKT-003", "shell"),
        ("INS-001", "high"),
        ("INS-001", "shell"),
        ("JKT-003", "shell"),
    ]
    assert payload["turns"][1]["commerce_facts"]["products"][0]["warmth"] == "high"
    r.structured["turns"][0]["trajectory"] = []
    synchronize(r)
    assert (
        semantic.build_evidence(case, r, projection_version=V5)["turns"][0][
            "commerce_facts"
        ]["products"]
        == []
    )


def test_empty_search_and_failed_tool_do_not_fabricate_warmth(cases):
    case = cases["SA-RCV-005"]
    r = complete_response(case)
    for t in r.structured["turns"]:
        t["trajectory"] = [
            tool("search_products", {"products": [], "count": 0}),
            tool("get_product", None, product_id="JKT-999"),
        ]
        t["trajectory"][1]["error"] = "product_not_found"
    synchronize(r)
    assert all(
        t["commerce_facts"]["products"] == []
        for t in semantic.build_evidence(case, r, projection_version=V5)["turns"]
    )


@pytest.mark.parametrize("cid", ["SA-INV-002", "SA-ADV-003"])
def test_v5_preserves_v4_inventory_and_promotion_projection(cases, cid):
    case = cases[cid]
    r = inventory_response(case)
    r.metadata.update(
        adapter_version="3", evidence_schema_version=WARMTH_EVIDENCE_VERSION
    )
    for t in r.structured["turns"]:
        for call in t["trajectory"]:
            if call["name"] == "get_product" and call["error"] is None:
                call["result"]["warmth"] = product(call["result"]["product_id"])[
                    "warmth"
                ]
    synchronize(r)
    old = semantic.build_evidence(
        case, r, projection_version=semantic.PRODUCT_PROJECTION_VERSION
    )
    new = semantic.build_evidence(case, r, projection_version=V5)
    for t in new["turns"]:
        for p in t["commerce_facts"]["products"]:
            del p["warmth"]
    assert old == new


def test_real_utf8_limit_accepts_exact_boundary_and_never_truncates(cases):
    case = cases["SA-REC-004"]
    r = complete_response(case)

    def size(payload):
        return len(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode()
        )

    payload = semantic.build_evidence(case, r, projection_version=V5)
    gap = 64 * 1024 - size(payload)
    r.structured["turns"][0]["output"] += "é" * (gap // 2) + "x" * (gap % 2)
    synchronize(r)
    assert size(semantic.build_evidence(case, r, projection_version=V5)) == 64 * 1024
    r.structured["turns"][0]["output"] += "x"
    synchronize(r)
    with pytest.raises(semantic.SemanticEvidenceError, match="byte limit"):
        semantic.build_evidence(case, r, projection_version=V5)


def test_cases_and_attempts_keep_separate_warmth_trajectories(cases):
    selected = [cases["SA-REC-004"], cases["SA-RCV-005"]]
    fake = mock_http(selected)
    result = run(
        target(fake),
        [study.capture_profile()[0]],
        selected,
        attempts=2,
        fingerprint_scheme="dataset-cases-v2",
        case_payload_snapshot="full",
    )
    assert len(fake.sessions) == 4 and sorted(fake.sessions.values()) == [1, 1, 2, 2]
    assert all(a.verdict == Verdict.PASS for c in result.cases for a in c.attempts)
    a = result.cases[0].attempts[0].response
    b = result.cases[0].attempts[1].response
    a.structured["turns"][0]["trajectory"][0]["result"]["warmth"] = "none"
    assert b.structured["turns"][0]["trajectory"][0]["result"]["warmth"] == "high"


def test_historical_prepared_configurations_and_execution_are_unchanged(tmp_path):
    expected = json.loads((FIXTURES / "pre-warmth-bindings.json").read_text())
    for version in [
        semantic.PROJECTION_VERSION,
        semantic.INVENTORY_PROJECTION_VERSION,
        semantic.PRODUCT_PROJECTION_VERSION,
    ]:
        scorer = semantic.make_scorer(
            lambda _: "UNUSED",
            "warmth-historical-compatibility",
            projection_version=version,
        )
        assert (
            fingerprint(
                [
                    scorer.prepare(c, target_response(c)).model_dump(mode="json")
                    for c in semantic.load_dataset()
                ]
            )
            == expected[version]["prepared"]
        )
        assert (
            fingerprint(scorer.preparation_configuration)
            == expected[version]["configuration"]
        )
    assert (
        fingerprint(
            study.capture_profile(reference_contract=study.REFERENCE_CONTRACT)[
                1
            ].model_dump(mode="json")
        )
        == expected["capture_profile"]
    )
    assert (
        fingerprint(study.semantic_profile(settings())[1].model_dump(mode="json"))
        == expected["semantic_profile"]
    )
    assert study.rating_contract().digest == expected["rating"]
    archived = study.StudyExecutionContract.model_validate_json(
        (FIXTURES / "pre-warmth-execution.json").read_text()
    )
    assert archived.digest == expected["execution"]
    # Reconstruct its original committed inputs; never rebind it to revised oracles.
    d = definition()
    (tmp_path / "suites").mkdir()
    copyfile(d.dataset.descriptor_path, tmp_path / "dataset.json")
    for suite in d.suites:
        copyfile(suite.suite_path, tmp_path / "suites" / suite.suite_path.name)
    (tmp_path / "cases.jsonl").write_text(
        "\n".join(
            canonical_json(c.model_dump(mode="json")) for c in pre_no_match_cases()
        )
        + "\n"
    )
    historical = study.load_study(
        tmp_path / "dataset.json", list((tmp_path / "suites").glob("*.json"))
    )
    assert study.verify_contract(historical, archived) == archived


@pytest.mark.parametrize("mode", ["lookup", "search"])
def test_legacy_adapter_ignores_new_warmth_and_keeps_original_metadata(cases, mode):
    case = cases["SA-REC-004"]

    def malformed(payload):
        data = payload["tool_calls"][0]["result"]["data"]
        if mode == "search":
            data = data["products"][0]
        data["warmth"] = {"secret": "PRIVATE_WARMTH"}

    fake = mock_http([case], mode, malformed)
    t = target(fake, EVIDENCE_VERSION)
    try:
        r = t.invoke(case)
    finally:
        t.close()
    assert (
        r.metadata["adapter_version"] == "2"
        and r.metadata["evidence_schema_version"] == EVIDENCE_VERSION
    )
    assert "PRIVATE_WARMTH" not in r.model_dump_json()
    for call in r.trajectory:
        records = (
            call.result["products"] if call.name == "search_products" else [call.result]
        )
        assert all("warmth" not in p for p in records)
    for version in [
        semantic.PROJECTION_VERSION,
        semantic.INVENTORY_PROJECTION_VERSION,
        semantic.PRODUCT_PROJECTION_VERSION,
    ]:
        payload = semantic.build_evidence(case, r, projection_version=version)
        assert all(
            "warmth" not in p
            for t in payload["turns"]
            for p in t["commerce_facts"]["products"]
        )
    with pytest.raises(semantic.SemanticEvidenceError):
        semantic.build_evidence(case, r, projection_version=V5)


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        None,
        {"adapter_version": "2", "evidence_schema_version": EVIDENCE_VERSION},
        {"adapter_version": "2", "evidence_schema_version": WARMTH_EVIDENCE_VERSION},
        {"adapter_version": "3", "evidence_schema_version": EVIDENCE_VERSION},
    ],
)
def test_v5_never_infers_or_upgrades_old_evidence(cases, metadata):
    case = cases["SA-REC-004"]
    r = complete_response(case)
    r.metadata = metadata
    with pytest.raises(semantic.SemanticEvidenceError):
        semantic.build_evidence(case, r, projection_version=V5)


def test_unsupported_adapter_and_judge_projection_rejected_before_clients(monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError("Client construction is forbidden")

    monkeypatch.setattr(httpx, "Client", forbidden)
    with pytest.raises(ValueError, match="Unsupported"):
        SalesAgentTarget("http://fake", evidence_version="unknown")
    monkeypatch.syspath_prepend(str(Path("examples").resolve()))
    recipe = importlib.import_module("salesagent_study")
    with pytest.raises(ValueError, match="Unsupported"):
        recipe.make_judge(settings(), projection_version="unknown")
    mixed = target_freeze(adapter_version="3", evidence_schema_version=EVIDENCE_VERSION)
    with pytest.raises(ValueError, match="unsupported"):
        recipe.make_target(mixed)


@pytest.mark.parametrize(
    "mutation", ["adapter", "evidence", "projection", "profile", "rating", "scorer"]
)
def test_mismatched_study_contract_rejected_before_recipe_clients(
    cases, tmp_path, monkeypatch, mutation
):
    c = new_contract(definition())
    p = c.model_dump(mode="json")
    if mutation == "adapter":
        p["target"]["requested"]["adapter_version"] = "2"
    elif mutation == "evidence":
        p["target"]["requested"]["evidence_schema_version"] = EVIDENCE_VERSION
    elif mutation == "projection":
        p["rating"]["projection_version"] = "unknown"
    elif mutation == "profile":
        p["semantic_profile_json"] = p["semantic_profile_json"].replace(
            V5, semantic.PRODUCT_PROJECTION_VERSION
        )
    elif mutation == "rating":
        p["rating"] = study.rating_contract().model_dump(mode="json")
    else:
        p["evaluator"]["scorer_json"] = p["evaluator"]["scorer_json"].replace(
            V5, semantic.PRODUCT_PROJECTION_VERSION
        )
    path = tmp_path / "invalid.json"
    path.write_text(canonical_json(p))
    monkeypatch.syspath_prepend(str(Path("examples").resolve()))
    recipe = importlib.import_module("salesagent_study")

    def forbidden(*a, **kw):
        raise AssertionError("No live factory may be reached")

    monkeypatch.setattr(recipe, "make_target", forbidden)
    monkeypatch.setattr(recipe, "make_judge", forbidden)
    d = definition()
    common = [
        "--descriptor",
        str(d.dataset.descriptor_path),
        "--suites",
        *[str(s.suite_path) for s in d.suites],
        "--contract",
        str(path),
    ]
    assert (
        recipe.main(
            [
                "capture",
                *common,
                "--suite",
                "full",
                "--target-budget",
                "50",
                "--output",
                str(tmp_path / "unused"),
                "--live",
                "--allow-target-calls",
            ]
        )
        == 2
    )
    assert not (tmp_path / "unused").exists()
    assert (
        recipe.main(
            [
                "judge",
                *common,
                "--source-db",
                str(tmp_path / "absent.sqlite"),
                "--run-id",
                "synthetic",
                "--preparation",
                str(tmp_path / "absent-preparation"),
                "--store",
                str(tmp_path / "unused-judge"),
                "--request-id",
                "synthetic",
                "--judge-budget",
                "1",
                "--live",
                "--allow-judge-calls",
            ]
        )
        == 2
    )
    assert not (tmp_path / "unused-judge").exists()


def test_real_candidate_v5_capture_preparation_store_and_blind_packet_agree(tmp_path):
    d = definition()
    c = new_contract(d)
    fake = mock_http(d.dataset.cases)
    source = study.capture(d, c, "full", lambda: target(fake))
    assert len(source.cases) == 50 and source.error_rate == 0
    store = SQLiteResultStore(tmp_path / "source.sqlite")
    store.save(source)
    loaded = store.load(source.run_id)
    assert loaded == source
    digest = fingerprint(loaded.model_dump(mode="json"))
    prep = study.prepare_primary(
        d,
        c,
        loaded,
        database_locator="runs/synthetic.sqlite",
        document_hash=digest,
        plan_id="warmth-synthetic",
        review_set_id="warmth-synthetic-human",
    )
    ps = ProspectiveStore(tmp_path / "prepared")
    ps.save_prepared(prep.bundle)
    assert ps.load_prepared(prep.bundle.plan) == prep.bundle
    loader = lambda _: (loaded, d.dataset.cases, digest)
    study.verify_preparation(d, c, prep, loader)
    manifest = study.human_manifest(d, c, prep, loader)
    packet = blind_packet(manifest)
    assert len(manifest.examples) == len(packet.items) == 12
    assert manifest.contract.projection_version == V5
    requests = {r.request_id: r for r in prep.bundle.requests}
    by_id = {c.id: c for c in d.dataset.cases}
    for example, item in zip(manifest.examples, packet.items):
        request = requests[example.prepared.request_id]
        assert example.prepared == request
        assert item.evidence_json == request.prepared.evidence_json
        manifest.contract.check_prepared(request)
    for row in loaded.cases:
        request = next(
            r for r in prep.bundle.requests if r.source.case_id == row.case_id
        )
        direct = study.semantic_profile(
            c.evaluator.judge, projection_version=c.rating.projection_version
        )[0].prepare(by_id[row.case_id], row.attempts[0].response)
        assert request.prepared == direct
        assert json.loads(request.evaluator.scorer_json)["projection_version"] == V5
    assert c.rating.digest != study.rating_contract().digest
    assert (
        d.validation.full_case_hash
        == "4a0e40d6dce4b78cc194352bf23d69dabcc8fe3c0f440d50f2cce2bd6a956028"
    )


def test_malformed_projection_keeps_independent_capture_score(cases):
    from harness.targets.base import StaticTarget

    case = cases["SA-REC-004"]
    r = complete_response(case)
    del r.structured["turns"][0]["trajectory"][0]["result"]["warmth"]
    synchronize(r)
    called = []
    scorer = study.semantic_profile(
        settings(), lambda p: called.append(p) or "UNUSED", projection_version=V5
    )[0]
    result = run(
        StaticTarget({case.id: r}, capabilities=study.CAPABILITIES),
        [study.capture_profile()[0], scorer],
        [case],
        fingerprint_scheme="dataset-cases-v2",
        case_payload_snapshot="full",
    )
    attempt = result.cases[0].attempts[0]
    assert attempt.verdict == Verdict.ERROR
    assert len(attempt.scores) == 1 and attempt.scores[0].passed is True
    assert called == []


@pytest.mark.parametrize("cid", WARM_CASES)
@pytest.mark.parametrize("truthful", [True, False])
def test_warmth_contrast_reaches_unchanged_semantic_gate(cases, cid, truthful):
    from harness.targets.base import StaticTarget

    case = cases[cid]
    r = complete_response(case)
    if not truthful:
        r.structured["turns"][-1]["output"] = (
            "Ridgeway has high insulation and guarantees warmth at minus 30 degrees. It combines all warmth and waterproof requirements."
        )
    synchronize(r)
    prompts = []
    scorer = study.semantic_profile(
        settings(),
        lambda p: (
            prompts.append(p)
            or json.dumps(
                {
                    "score": 1.0 if truthful else 0.3,
                    "reason": "Scripted warmth contrast, not live judge accuracy",
                }
            )
        ),
        projection_version=V5,
    )[0]
    prepared = scorer.prepare(case, r)
    payload = json.loads(prepared.evidence_json)
    assert {
        p["warmth"] for t in payload["turns"] for p in t["commerce_facts"]["products"]
    } == {"high", "shell"}
    result = run(
        StaticTarget({case.id: r}, capabilities=study.CAPABILITIES),
        [study.capture_profile()[0], scorer],
        [case],
        fingerprint_scheme="dataset-cases-v2",
        case_payload_snapshot="full",
    )
    assert result.cases[0].attempts[0].verdict == (
        Verdict.PASS if truthful else Verdict.FAIL
    )
    assert len(prompts) == 1


def test_recipe_explicit_freeze_selection_is_pure_and_bound(tmp_path, monkeypatch):
    from harness.core.prospective_io import _load

    monkeypatch.syspath_prepend(str(Path("examples").resolve()))
    recipe = importlib.import_module("salesagent_study")

    def forbidden(*a, **kw):
        raise AssertionError("Pure configuration must not construct clients")

    monkeypatch.setattr(recipe, "make_target", forbidden)
    monkeypatch.setattr(recipe, "make_judge", forbidden)
    d = definition()
    tf = target_freeze(
        adapter_version="3", evidence_schema_version=WARMTH_EVIDENCE_VERSION
    )
    (tmp_path / "target.json").write_text(tf.model_dump_json())
    (tmp_path / "judge.json").write_text(settings().model_dump_json())
    args = [
        "freeze",
        "--descriptor",
        str(d.dataset.descriptor_path),
        "--suites",
        *[str(s.suite_path) for s in d.suites],
        "--target-freeze",
        str(tmp_path / "target.json"),
        "--judge-config",
        str(tmp_path / "judge.json"),
        "--author-review",
        "SYNTHETIC test only",
        "--reviewed-at",
        datetime.now(UTC).isoformat(),
        "--diagnostic-budget",
        "3",
        "--output",
        str(tmp_path / "unselected"),
    ]
    # A new adapter must never silently upgrade the legacy default projection.
    assert recipe.main(args) == 2
    assert not (tmp_path / "unselected").exists()
    args[args.index("--output") + 1] = str(tmp_path / "explicit")
    assert recipe.main([*args, "--projection-version", V5]) == 0
    c = _load(tmp_path / "explicit", study.StudyExecutionContract)
    assert (
        c.rating.projection_version == V5 and c.target.requested.adapter_version == "3"
    )


def test_v5_variance_diagnostic_uses_frozen_projection_and_rejects_stale_binding(
    tmp_path,
):
    d = definition()
    c = new_contract(d)
    fake = mock_http(d.dataset.cases)
    source = study.capture(d, c, "variance", lambda: target(fake))
    digest = fingerprint(source.model_dump(mode="json"))
    prep = study.prepare_variance_diagnostic(
        d,
        c,
        source,
        database_locator="runs/variance-synthetic.sqlite",
        document_hash=digest,
        case_id="SA-RCV-005",
        attempt_index=1,
        attempts=2,
        plan_id="synthetic-warmth-diagnostic",
    )
    loader = lambda _: (source, d.dataset.cases, digest)
    study.verify_preparation(d, c, prep, loader)
    assert all(
        json.loads(r.evaluator.scorer_json)["projection_version"] == V5
        for r in prep.bundle.requests
    )
    assert all(not s.requires_human for s in prep.bundle.plan.selections)
    old = study.StudyExecutionContract.model_validate_json(
        (FIXTURES / "pre-warmth-execution.json").read_text()
    )
    with pytest.raises(ValueError):
        study.verify_preparation(d, old, prep, loader)


def test_adapter_v3_keeps_empty_and_failed_observations_as_business_outcomes(cases):
    case = cases["SA-RCV-005"]

    def business(payload):
        first, second = payload["tool_calls"]
        first.update(status="error")
        first["result"].update(
            success=False,
            data=None,
            error={"code": "product_not_found", "message": "Public business result"},
        )
        second.update(tool_name="search_products", arguments={})
        second["result"].update(
            tool_name="search_products", data={"products": [], "count": 0}
        )

    fake = mock_http([case], alter=business)
    t = target(fake)
    try:
        r = t.invoke(case)
    finally:
        t.close()
    assert all(
        c.result is None if c.error else c.result == {"products": [], "count": 0}
        for c in r.trajectory
    )
    assert all(
        not t["commerce_facts"]["products"]
        for t in semantic.build_evidence(case, r, projection_version=V5)["turns"]
    )
