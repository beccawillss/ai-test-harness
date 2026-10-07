"""Disposable synthetic 50-row candidates; never real study authoring."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from test_replay import settings
from test_salesagent_target import FakeHTTP

from harness.core.fingerprints import canonical_json, fingerprint
from harness.core.models import Verdict
from harness.core.prospective_io import ProspectiveStore
from harness.packs import salesagent_study as study
from harness.targets.salesagent import SalesAgentTarget


def candidate(tmp_path, mutate=None, mutate_suite=None):
    matrix = study.matrix_contract()
    cases = []
    for i, row in enumerate(matrix["cases"]):
        turns = [f"SYNTHETIC plumbing input {i}"]
        if row["journey"] == "multi-turn":
            turns.append("SYNTHETIC follow-up")
        cases.append(
            {
                "id": row["id"],
                "input": {"turns": turns},
                "reference": {
                    "assertions": [
                        {
                            "id": "synthetic-rule",
                            "path": ["structured", "recommendations"],
                            "op": "nonempty",
                            "critical": True,
                        }
                    ],
                    "semantic": {
                        "schema_version": "salesagent-semantic-expectations-v1",
                        "expectations": [
                            "SYNTHETIC plumbing expectation; not study content."
                        ],
                    },
                },
                "category": row["category"],
                "risk": row["risk"],
                "tags": [
                    f"journey:{row['journey']}",
                    f"difficulty:{row['difficulty']}",
                ],
                "extra": {"provenance": {"secret": "DO_NOT_EXPORT"}},
            }
        )
    if mutate:
        mutate(cases)
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "cases.jsonl").write_text(
        "\n".join(canonical_json(c) for c in cases) + "\n"
    )
    (tmp_path / "dataset.json").write_text(
        canonical_json(
            {
                "schema_version": "dataset-descriptor-v1",
                "id": "sales-agent-evaluation-study",
                "version": "study-v1",
                "cases": "cases.jsonl",
                "fingerprint_scheme": "dataset-cases-v2",
                "extra": {"private": "DATASET_PRIVATE"},
            }
        )
    )
    directory = tmp_path / "suites"
    directory.mkdir()
    paths = []
    for id, spec in matrix["suites"].items():
        suite = {
            "schema_version": "suite-v1",
            "id": id,
            "dataset": {
                "id": matrix["dataset_id"],
                "version": "study-v1",
                "descriptor": "../dataset.json",
            },
            "selection": spec["selection"],
            "attempts": spec["attempts"],
            "evaluation_profile": study.CAPTURE_PROFILE,
        }
        if mutate_suite:
            mutate_suite(suite)
        path = directory / f"{id}.json"
        path.write_text(canonical_json(suite))
        paths.append(path)
    return tmp_path / "dataset.json", paths


def definition(tmp_path, **kwargs):
    path, suites = candidate(tmp_path, **kwargs)
    return study.load_study(path, suites)


def target_freeze(**changes):
    requested = {
        "base_url": "http://fake",
        "deployed_target_commit_sha": "1" * 40,
        "provider": "synthetic",
        "model": "fake-model",
        "reviewed_generation_parameters": {"status": "not_exposed"},
        "prompt_version": "p1",
        "catalogue": {"revision": "synthetic-catalogue", "sha256": "2" * 64},
        "promotions": {"revision": "synthetic-promotions", "sha256": "3" * 64},
        "adapter_version": "2",
        "evidence_schema_version": "salesagent-evidence-v2",
        "http_contract_version": "1.0.0",
        "capabilities": ["metadata", "structured", "trajectory"],
        "session_policy": "isolated_case_attempt",
        "reviewed_state_configuration": {"status": "not_exposed"},
        "timeouts": {"connect": 5, "read": 120, "write": 10, "pool": 5},
        "evaluation_traces_enabled": True,
    }
    requested.update(changes)
    return study.StudyTargetFreeze.model_validate_json(
        canonical_json(
            {
                "requested": requested,
                "harness_revision": "4" * 40,
                "verification": {
                    "operator_statement": "SYNTHETIC fixture only",
                    "verified_at": datetime.now(UTC).isoformat(),
                    "deployment_reference": "synthetic-deployment",
                },
            }
        )
    )


def contract(d, **changes):
    return study.freeze_execution(
        d,
        target_freeze(**changes),
        settings(),
        diagnostic_judge_calls=3,
        author_review="SYNTHETIC fixture review only",
        reviewed_at=datetime.now(UTC),
    )


def captured(tmp_path, *, suite="full", mutate=None):
    d = definition(tmp_path / "data")
    c = contract(d)
    transport = FakeHTTP(mutate)
    source = study.capture(
        d,
        c,
        suite,
        lambda: SalesAgentTarget(
            "http://fake",
            target_revision="1" * 40,
            transport=httpx.MockTransport(transport),
        ),
    )
    return d, c, source, transport


def prepared(tmp_path):
    d, c, source, _transport = captured(tmp_path)
    digest = fingerprint(source.model_dump(mode="json"))
    prep = study.prepare_primary(
        d,
        c,
        source,
        database_locator="runs/synthetic.sqlite",
        document_hash=digest,
        plan_id="synthetic-plan",
        review_set_id="synthetic-human",
    )
    store = ProspectiveStore(tmp_path / "prospective")
    store.save_prepared(prep.bundle)
    loader = lambda _: (source, d.dataset.cases, digest)
    return d, c, source, prep, store, loader


def test_matrix_resource_against_separate_pinned_document_reading():
    raw = Path(
        "docs/studies/sales-agent-evaluation-study-v1-preregistration.md"
    ).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == study.METHODOLOGY_HASH
    matrix = study.matrix_contract()
    rows = [
        line.split("|")[1:-1]
        for line in raw.decode().splitlines()
        if line.startswith("| SA-")
    ]
    names = [
        "recommendation-quality",
        "constraint-handling",
        "inventory-variants",
        "promotions-pricing",
        "conversation-state",
        "grounding-factuality",
        "recovery-ambiguity",
        "business-rule-resistance",
    ]
    families = ["REC", "CON", "INV", "PRC", "STA", "GRD", "RCV", "ADV"]
    expected = []
    for row in rows:
        id, _scenario, risk, journey, difficulty, _v, _h = [
            cell.strip() for cell in row
        ]
        expected.append(
            {
                "id": id,
                "category": names[families.index(id.split("-")[1])],
                "risk": risk,
                "journey": journey,
                "difficulty": difficulty,
            }
        )
    assert matrix["cases"] == expected
    assert matrix["human"]["case_ids"] == [
        row[0].strip() for row in rows if row[6].strip()
    ]
    assert matrix["suites"]["variance"]["selection"]["case_ids"] == [
        row[0].strip() for row in rows if row[5].strip()
    ]
    assert matrix["suites"]["smoke"]["selection"]["case_ids"] == [
        "SA-REC-002",
        "SA-CON-003",
        "SA-INV-001",
        "SA-PRC-004",
        "SA-STA-004",
        "SA-GRD-001",
        "SA-RCV-004",
        "SA-ADV-002",
    ]
    assert not any(
        k in canonical_json(matrix) for k in ('"input"', '"reference"', '"assertions"')
    )


def test_synthetic_candidate_and_all_suite_counts(tmp_path):
    d = definition(tmp_path)
    assert len(d.dataset.cases) == 50
    assert {s.id: len(s.case_ids) for s in d.validation.suites} == {
        "full": 50,
        "smoke": 8,
        "critical": 12,
        "multi-turn": 20,
        "adversarial": 8,
        "variance": 10,
    }
    assert {s.id: s.target_calls for s in d.validation.suites}["variance"] == 30
    assert set(d.validation.human_ids).isdisjoint(
        next(s.case_ids for s in d.validation.suites if s.id == "smoke")
    )
    assert (
        len(
            set(next(s.case_ids for s in d.validation.suites if s.id == "smoke"))
            & set(next(s.case_ids for s in d.validation.suites if s.id == "variance"))
        )
        == 2
    )


@pytest.mark.parametrize("index", range(50))
@pytest.mark.parametrize("dimension", ["category", "risk", "journey", "difficulty"])
def test_every_per_id_mismatch_rejected(tmp_path, index, dimension):
    def change(rows):
        if dimension in ("category", "risk"):
            rows[index][dimension] = "incorrect"
        else:
            rows[index]["tags"] = [
                t if not t.startswith(dimension + ":") else dimension + ":incorrect"
                for t in rows[index]["tags"]
            ]

    with pytest.raises(ValueError):
        definition(tmp_path, mutate=change)


@pytest.mark.parametrize("dimension", ["category", "risk", "journey", "difficulty"])
def test_same_totals_swapped_classification_rejected(tmp_path, dimension):
    def change(rows):
        get = lambda r: (
            r[dimension]
            if dimension in ("category", "risk")
            else next(t for t in r["tags"] if t.startswith(dimension + ":"))
        )
        a = rows[0]
        b = next(r for r in rows if get(r) != get(a))
        x, y = get(a), get(b)
        if dimension in ("category", "risk"):
            a[dimension], b[dimension] = y, x
        else:
            a["tags"] = [y if t == x else t for t in a["tags"]]
            b["tags"] = [x if t == y else t for t in b["tags"]]

    with pytest.raises(ValueError):
        definition(tmp_path, mutate=change)


@pytest.mark.parametrize(
    "failure",
    [
        "input",
        "assertion",
        "semantic",
        "journey",
        "tag",
        "duplicate",
        "missing",
        "historical",
    ],
)
def test_all_row_preflight_invalid_last_row(tmp_path, failure):
    def change(rows):
        r = rows[-1]
        if failure == "input":
            r["input"] = {"turns": []}
        if failure == "assertion":
            r["reference"]["assertions"][0]["op"] = "unsupported"
        if failure == "semantic":
            r["reference"]["semantic"]["expectations"] = []
        if failure == "journey":
            r["input"]["turns"].append("extra")
        if failure == "tag":
            r["tags"].append("experiment:human")
        if failure == "duplicate":
            r["id"] = rows[0]["id"]
        if failure == "missing":
            rows.pop()
        if failure == "historical":
            r["input"]["turns"][0] = study.load_cases(study.semantic.DATASET)[0].input[
                "turns"
            ][0]

    with pytest.raises(ValueError):
        definition(tmp_path, mutate=change)


@pytest.mark.parametrize(
    "failure", ["obsolete-smoke", "extra-filter", "attempts", "profile", "pin"]
)
def test_suite_policies_reject_drift(tmp_path, failure):
    def change(s):
        if s["id"] != "smoke":
            return
        if failure == "obsolete-smoke":
            s["selection"]["case_ids"][0] = "SA-REC-001"
        if failure == "extra-filter":
            s["selection"]["risks"] = ["medium", "high", "critical", "low"]
        if failure == "attempts":
            s["attempts"] = 2
        if failure == "profile":
            s["evaluation_profile"] = "salesagent-semantic-v1"
        if failure == "pin":
            s["dataset"]["expected_case_fingerprint"] = "0" * 64

    with pytest.raises(ValueError):
        definition(tmp_path, mutate_suite=change)


def test_deterministic_capture_full_payload_and_safe_metadata(tmp_path):
    d, c, source, transport = captured(tmp_path)
    assert len(source.cases) == 50 and len(transport.sessions) == 50
    assert all(
        a.verdict == Verdict.PASS for case in source.cases for a in case.attempts
    )
    assert all(
        [s.name for s in a.scores] == ["structured_assertions"]
        for case in source.cases
        for a in case.attempts
    )
    assert (
        "DO_NOT_EXPORT" not in source.model_dump_json()
        and "DATASET_PRIVATE" not in source.model_dump_json()
    )
    assert source.config_snapshot["case_payload_snapshot"] == "full"
    assert source.config_snapshot["study"]["execution_contract_hash"] == c.digest
    assert source.config_snapshot["study"]["final_study_outcome"] is False
    assert (
        study.verify_capture(d, c, source, fingerprint(source.model_dump(mode="json")))
        == "full"
    )


def test_variance_capture_isolation_and_fixed_response_selection(tmp_path):
    d, c, source, transport = captured(tmp_path, suite="variance")
    assert len(source.cases) == 10 and len(transport.sessions) == 30
    assert all([a.index for a in case.attempts] == [0, 1, 2] for case in source.cases)
    prep = study.prepare_variance_diagnostic(
        d,
        c,
        source,
        database_locator="runs/source.sqlite",
        document_hash=fingerprint(source.model_dump(mode="json")),
        case_id=source.cases[0].case_id,
        attempt_index=2,
        attempts=3,
        plan_id="diagnostic",
    )
    assert prep.bundle.requests[0].source.attempt_index == 2
    assert prep.bundle.requests[0].selection.role == "diagnostic"


def test_primary_twelve_protected_and_gate_before_factory(tmp_path):
    d, c, _source, prep, store, loader = prepared(tmp_path)
    assert len(prep.bundle.requests) == 50
    protected = [r for r in prep.bundle.requests if r.selection.requires_human]
    assert len(protected) == 12
    manifest = study.human_manifest(d, c, prep, loader)
    assert len(manifest.examples) == 12
    calls = []
    with pytest.raises(ValueError, match="freeze"):
        study.judge_request(
            d,
            c,
            prep,
            protected[0].request_id,
            source_loader=loader,
            scorer_factory=lambda: calls.append(True),
            store=store,
        )
    assert not calls


@pytest.mark.parametrize(
    "field",
    [
        "deployed_target_commit_sha",
        "provider",
        "model",
        "reviewed_generation_parameters",
        "catalogue",
        "promotions",
        "adapter_version",
        "evidence_schema_version",
        "http_contract_version",
        "session_policy",
        "reviewed_state_configuration",
        "timeouts",
        "evaluation_traces_enabled",
        "base_url",
    ],
)
def test_missing_freeze_critical_facts_block_contract(tmp_path, field):
    d = definition(tmp_path)
    freeze = target_freeze(**{field: None})
    assert any(field in missing for missing in freeze.missing_facts)
    with pytest.raises(ValueError, match="freeze facts"):
        study.freeze_execution(
            d,
            freeze,
            settings(),
            diagnostic_judge_calls=0,
            author_review="synthetic",
            reviewed_at=datetime.now(UTC),
        )


def test_invalid_freeze_data_and_metadata_policy(tmp_path):
    d = definition(tmp_path)
    with pytest.raises(ValueError):
        target_freeze(
            reviewed_generation_parameters={"status": "recorded", "api_key": "REJECTED"}
        )
    with pytest.raises(ValueError):
        target_freeze(base_url="http://user:secret@host")
    with pytest.raises(ValueError):
        target_freeze(deployed_target_commit_sha="short")
    c = contract(d)
    doc = c.model_dump(mode="json")
    doc["metadata_policy_json"] = canonical_json(
        {"case_extra_keys": ["provenance"], "dataset_extra_keys": []}
    )
    with pytest.raises(ValueError):
        study.StudyExecutionContract.model_validate_json(canonical_json(doc))
    assert study.StudyExecutionContract.model_validate_json(c.model_dump_json()) == c


def test_semantic_profile_reuses_prompt_and_excludes_taxonomy(tmp_path):
    d, c, source, _transport = captured(tmp_path)
    case = d.dataset.cases[0]
    response = source.cases[0].attempts[0].response
    old = study.semantic.make_scorer(
        lambda _: '{"score":0.7,"reason":"legacy"}', c.evaluator.judge.model
    )
    new, _profile = study.semantic_profile(c.evaluator.judge)
    assert new.prepare(case, response).prompt == old.prepare(case, response).prompt
    assert new.name == old.name and new.pass_threshold == 0.7
    assert "output_validation" not in old.preparation_configuration
    changed = case.model_copy(deep=True)
    changed.title = "DIFFERENT"
    changed.description = "PRIVATE prose"
    changed.category = "other"
    changed.risk = "other"
    changed.tags = ["OTHER"]
    changed.extra = {"secret": "HIDDEN"}
    assert new.prepare(case, response) == new.prepare(changed, response)
    assert old.parse_judgement('{"score":0.7,"reason":"legacy"}')[0] == 0.7
    with pytest.raises(ValueError):
        new.parse_judgement('{"score":0.7,"reason":"off anchor"}')


def test_http_bytes_exclude_evaluator_fields(tmp_path):
    d = definition(tmp_path)
    original = d.dataset.cases[0]
    changed = original.model_copy(deep=True)
    changed.id = "PRIVATE_ID"
    changed.category = "other"
    changed.tags = ["PRIVATE_TAG"]
    changed.risk = "other"
    changed.reference = {"hidden": "PRIVATE_REFERENCE"}
    changed.extra = {"secret": "PRIVATE_EXTRA"}
    requests = []
    for case in (original, changed):
        transport = FakeHTTP()
        target = SalesAgentTarget(
            "http://fake", transport=httpx.MockTransport(transport)
        )
        try:
            target.invoke(case)
        finally:
            target.close()
        requests.append([(r.method, str(r.url), r.content) for r in transport.requests])
    assert requests[0] == requests[1]
    assert b"PRIVATE" not in b"".join(body for _method, _url, body in requests[1])


def test_invalid_candidate_before_factory_and_snapshot_drift(tmp_path):
    d = definition(tmp_path)
    c = contract(d)
    d.dataset.cases[-1].reference["semantic"]["expectations"] = []
    calls = []
    with pytest.raises(ValueError):
        study.capture(d, c, "smoke", lambda: calls.append(True))
    assert not calls


def test_variance_failed_conversation_has_no_fabricated_response(tmp_path):
    def fail(request, payload):
        if (
            request.method == "POST"
            and json.loads(request.content)["message"] == "SYNTHETIC follow-up"
        ):
            return httpx.Response(503)

    d, _c, source, transport = captured(tmp_path, suite="variance", mutate=fail)
    assert len(transport.sessions) == 30
    assert sum(len(case.attempts) for case in source.cases) == 30
    failed = [
        a for case in source.cases for a in case.attempts if a.verdict == Verdict.ERROR
    ]
    assert failed and all(a.response is None for a in failed)
    for case in source.cases:
        for a in case.attempts:
            if a.response is not None:
                assert (
                    study.bind_source(
                        source,
                        d.dataset.cases,
                        database_locator="source",
                        case_id=case.case_id,
                        source_attempt=a.index,
                        source_document_hash=fingerprint(
                            source.model_dump(mode="json")
                        ),
                    ).attempt_index
                    == a.index
                )


def test_unprotected_failure_remains_unavailable_without_shrinking_human_roster(
    tmp_path,
):
    def fail(request, payload):
        if (
            request.method == "POST"
            and json.loads(request.content)["message"] == "SYNTHETIC plumbing input 1"
        ):
            return httpx.Response(503)

    d, c, source, _transport = captured(tmp_path, mutate=fail)
    p = study.prepare_primary(
        d,
        c,
        source,
        database_locator="source",
        document_hash=fingerprint(source.model_dump(mode="json")),
        plan_id="primary",
        review_set_id="human",
    )
    assert len(p.bundle.requests) == 49 and len(p.unavailable) == 1
    assert sum(r.selection.requires_human for r in p.bundle.requests) == 12


def test_primary_ids_cannot_be_reissued_under_another_plan(tmp_path):
    d, c, source, p, store, _loader = prepared(tmp_path)
    again = study.prepare_primary(
        d,
        c,
        source,
        database_locator="runs/synthetic.sqlite",
        document_hash=p.source_document_hash,
        plan_id="another-plan",
        review_set_id="another-human",
    )
    assert (
        again.bundle.requests[0].selection.observation_id
        == p.bundle.requests[0].selection.observation_id
    )
    with pytest.raises(FileExistsError):
        store.save_prepared(again.bundle)


def test_command_help_validation_and_live_gates_construct_no_clients(
    tmp_path, monkeypatch, capsys
):
    import importlib

    monkeypatch.syspath_prepend(str(Path("examples").resolve()))
    recipe = importlib.import_module("salesagent_study")

    def forbidden(*args, **kwargs):
        raise AssertionError("No client should be constructed")

    monkeypatch.setattr(recipe, "make_target", forbidden)
    monkeypatch.setattr(recipe, "make_judge", forbidden)
    with pytest.raises(SystemExit) as exit:
        recipe.main(["--help"])
    assert exit.value.code == 0
    d = definition(tmp_path / "data")
    c = contract(d)
    from harness.core.prospective_io import _save

    _save(tmp_path / "contract", c)
    common = [
        "--descriptor",
        str(d.dataset.descriptor_path),
        "--suites",
        *[str(s.suite_path) for s in d.suites],
    ]
    assert recipe.main(["validate", *common]) == 0
    assert recipe.main(["preview", *common]) == 0
    assert (
        recipe.main(
            [
                "capture",
                *common,
                "--contract",
                str(tmp_path / "contract"),
                "--suite",
                "full",
                "--target-budget",
                "50",
                "--output",
                str(tmp_path / "no-capture"),
            ]
        )
        == 2
    )
    assert not (tmp_path / "no-capture").exists()
    assert "salesagent-study-validation-v1" in capsys.readouterr().out


def test_thin_recipe_offline_pipeline_with_injected_fakes(
    tmp_path, monkeypatch, capsys
):
    import importlib

    from test_calibration_io import authored_draft

    from harness.core.prospective import ProspectiveJudge
    from harness.core.prospective_io import _load, _save
    from harness.core.store import SQLiteResultStore

    monkeypatch.syspath_prepend(str(Path("examples").resolve()))
    recipe = importlib.import_module("salesagent_study")
    d = definition(tmp_path / "data")
    c = contract(d)
    _save(tmp_path / "contract", c)
    common = [
        "--descriptor",
        str(d.dataset.descriptor_path),
        "--suites",
        *[str(s.suite_path) for s in d.suites],
        "--contract",
        str(tmp_path / "contract"),
    ]
    calls = []

    def target(freeze):
        calls.append("target")
        return SalesAgentTarget(
            "http://fake",
            target_revision="1" * 40,
            transport=httpx.MockTransport(FakeHTTP()),
        )

    def judge(config):
        calls.append("judge")
        return ProspectiveJudge(
            study.semantic_profile(
                config, lambda _: '{"score":0.8,"reason":"synthetic"}'
            )[0],
            lambda: config,
        )

    monkeypatch.setattr(recipe, "make_target", target)
    monkeypatch.setattr(recipe, "make_judge", judge)
    capture_dir = tmp_path / "capture"
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
                str(capture_dir),
                "--live",
                "--allow-target-calls",
            ]
        )
        == 0
    )
    source = SQLiteResultStore(
        capture_dir / "source.sqlite", read_only=True
    ).list_runs()[0]
    selection = [
        "--source-db",
        str(capture_dir / "source.sqlite"),
        "--run-id",
        source.run_id,
    ]
    prepdir = tmp_path / "prospective"
    assert (
        recipe.main(
            [
                "prepare",
                *common,
                *selection,
                "--plan-id",
                "recipe-plan",
                "--review-set-id",
                "recipe-human",
                "--output",
                str(prepdir),
            ]
        )
        == 0
    )
    prep = _load(prepdir / "preparation", study.StudyPreparation)
    assert calls == ["target"]
    export = tmp_path / "export"
    assert (
        recipe.main(
            [
                "export",
                *common,
                *selection,
                "--preparation",
                str(prepdir / "preparation"),
                "--annotator",
                "synthetic-reviewer",
                "--output",
                str(export),
            ]
        )
        == 0
    )
    assert calls == ["target"]
    protected = next(r for r in prep.bundle.requests if r.selection.requires_human)
    judging = [
        "judge",
        *common,
        *selection,
        "--preparation",
        str(prepdir / "preparation"),
        "--store",
        str(prepdir / "observations"),
        "--request-id",
        protected.request_id,
        "--judge-budget",
        "1",
        "--live",
        "--allow-judge-calls",
    ]
    assert recipe.main(judging) == 2
    assert calls == ["target"]
    frozen = tmp_path / "frozen"
    assert (
        recipe.main(
            [
                "freeze-human",
                "--export",
                str(export),
                "--draft",
                str(authored_draft(export)),
                "--output",
                str(frozen),
            ]
        )
        == 0
    )
    assert recipe.main([*judging, "--frozen", str(frozen)]) == 0
    assert calls == ["target", "judge"]
    result = prepdir / "observations" / f"result-{protected.selection.observation_id}"
    assert (
        recipe.main(
            [
                "analyze",
                *common,
                *selection,
                "--preparation",
                str(prepdir / "preparation"),
                "--results",
                str(result),
                "--frozen",
                str(frozen),
                "--output",
                str(tmp_path / "analysis"),
            ]
        )
        == 0
    )
    assert calls == ["target", "judge"]
    assert "pending" in capsys.readouterr().out


def test_protected_policy_cannot_be_stripped_in_study_preparation(tmp_path):
    from harness.core.prospective_io import PreparedBundle

    d, c, _source, prep, store, loader = prepared(tmp_path)
    plan = prep.bundle.plan
    doc = plan.model_dump(mode="json")
    for selection in doc["selections"]:
        selection["requires_human"] = False
    doc["review_set_id"] = None
    doc["rating_contract_hash"] = None
    changed = type(plan).model_validate_json(canonical_json(doc))
    requests = tuple(
        r.model_copy(update={"plan": changed, "plan_hash": changed.digest})
        for r in prep.bundle.requests
    )
    altered = prep.model_copy(
        update={"bundle": PreparedBundle(plan=changed, requests=requests)}
    )
    called = []
    with pytest.raises(ValueError):
        study.judge_request(
            d,
            c,
            altered,
            requests[0].request_id,
            source_loader=loader,
            scorer_factory=lambda: called.append(True),
            store=store,
        )
    assert not called


@pytest.mark.parametrize(
    "id", ["full", "smoke", "critical", "multi-turn", "adversarial", "variance"]
)
def test_all_suite_attempt_policies_are_frozen(tmp_path, id):
    def change(s):
        if s["id"] == id:
            s["attempts"] += 1

    with pytest.raises(ValueError):
        definition(tmp_path, mutate_suite=change)


def test_human_variance_overlap_in_execution_selector_rejected(tmp_path):
    d = definition(tmp_path)
    c = contract(d)
    doc = c.model_dump(mode="json")
    selectors = json.loads(doc["selectors_json"])
    selectors["human"]["case_ids"][0] = selectors["variance"]["case_ids"][0]
    doc["selectors_json"] = canonical_json(selectors)
    with pytest.raises(ValueError):
        study.StudyExecutionContract.model_validate_json(canonical_json(doc))
