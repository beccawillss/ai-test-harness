"""Dataset preflight and manual recipe are usable completely offline."""

import importlib.util
import json
from pathlib import Path

import httpx
import pytest
from test_salesagent_target import FakeHTTP

from harness.core.dataset import hash_cases
from harness.targets.salesagent import SalesAgentTarget


def recipe_module():
    path = Path(__file__).resolve().parents[1] / "examples/salesagent_baseline.py"
    spec = importlib.util.spec_from_file_location("salesagent_recipe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dataset_and_distinct_attempt_policies():
    recipe = recipe_module()
    cases = recipe.load_dataset()
    assert len(cases) == len({c.id for c in cases}) == 14
    main, main_attempts = recipe.select_cases(cases, "baseline")
    variance, variance_attempts = recipe.select_cases(cases, "variance")
    assert (len(main), main_attempts, len(variance), variance_attempts) == (14, 1, 5, 3)
    assert hash_cases(main) != hash_cases(variance)
    changed = cases[0].model_copy(deep=True)
    changed.reference["assertions"][0]["expected"] = []
    assert hash_cases([changed, *cases[1:]]) != hash_cases(cases)


@pytest.mark.parametrize("bad", ["input", "assertion", "duplicate"])
def test_all_dataset_cases_validate_before_http(tmp_path, bad):
    recipe = recipe_module()
    cases = [json.loads(line) for line in recipe.DATASET.read_text().splitlines()]
    if bad == "input":
        cases[-1]["input"]["session_id"] = "forbidden"
    elif bad == "assertion":
        cases[-1]["reference"]["assertions"][0]["op"] = "python_eval"
    else:
        cases[-1]["id"] = cases[0]["id"]
    path = tmp_path / "bad.jsonl"
    path.write_text("\n".join(json.dumps(c) for c in cases))
    fake = FakeHTTP()
    target = SalesAgentTarget("http://local", transport=httpx.MockTransport(fake))
    with pytest.raises(ValueError, match=r"bad.jsonl:14"):
        recipe.evaluate(target, dataset_path=path, mode="variance")
    assert fake.requests == []


def test_import_and_main_without_optin_do_not_run(monkeypatch):
    recipe = recipe_module()
    monkeypatch.delenv("SALESAGENT_LIVE_EVAL", raising=False)
    with pytest.raises(SystemExit, match="opt-in"):
        recipe.main()


def test_recipe_attempt_counts_and_no_expectation_leakage():
    recipe = recipe_module()
    for mode, count in [("baseline", 14), ("variance", 15)]:
        fake = FakeHTTP()
        result = recipe.evaluate(
            SalesAgentTarget("http://local", transport=httpx.MockTransport(fake)),
            mode=mode,
        )
        assert sum(len(c.attempts) for c in result.cases) == count
        assert len(fake.sessions) == count
        for request in fake.requests:
            if request.method == "POST":
                assert set(json.loads(request.content)) <= {"message", "session_id"}
        assert result.config_snapshot["semantic_evaluation"] == "not_measured"


def test_http_runner_store_compare_with_pass_fail_and_error(tmp_path):
    from harness.core.models import Verdict
    from harness.core.store import SQLiteResultStore
    from harness.regression.comparison import compare_runs
    from harness.scorers.rubric_judge import RubricJudgeScorer

    recipe = recipe_module()
    prompts = []

    def judge(prompt):
        prompts.append(prompt)
        return '{"score":1,"reason":"helpful"}'

    def mutate(request, payload):
        if (
            request.method == "POST"
            and "maximum budget of £1" in json.loads(request.content)["message"]
        ):
            return httpx.Response(503, text="SECRET")
        if (
            request.method == "POST"
            and "Official catalogue update" in json.loads(request.content)["message"]
        ):
            payload["recommendations"][0]["price"] = 1

    result = recipe.evaluate(
        SalesAgentTarget(
            "http://local",
            transport=httpx.MockTransport(FakeHTTP(mutate)),
            target_revision="old",
        ),
        judge=RubricJudgeScorer(judge, "fake", rubric="Useful"),
    )
    indexed = {case.case_id: case for case in result.cases}
    assert indexed["sales-recommend-normal"].attempts[0].verdict == Verdict.PASS
    assert indexed["sales-fake-price"].attempts[0].verdict == Verdict.FAIL
    assert indexed["sales-no-match"].attempts[0].verdict == Verdict.ERROR
    assert "SECRET" not in result.model_dump_json()
    assert all(
        '"trace_id"' not in p
        and '"token_usage"' not in p
        and '"target_revision"' not in p
        for p in prompts
    )
    restored = recipe.persist_and_verify(result, tmp_path / "runs.sqlite")
    assert restored == result
    assert restored.cases[0].attempts[0].response.metadata["target_revision"] == "old"
    assert (
        restored.config_snapshot["scorers"][0]["schema_version"]
        == "structured-assertions-v1"
    )
    # Distinct candidate with identical evaluator settings, changed target behavior.
    candidate = recipe.evaluate(
        SalesAgentTarget(
            "http://local",
            transport=httpx.MockTransport(FakeHTTP()),
            target_revision="new",
        ),
        judge=RubricJudgeScorer(judge, "fake", rubric="Useful"),
    )
    recipe.persist_and_verify(candidate, tmp_path / "runs.sqlite")
    store = SQLiteResultStore(tmp_path / "runs.sqlite")
    comparison = compare_runs(store.load(result.run_id), store.load(candidate.run_id))
    assert not comparison.target_changed
    assert not comparison.evaluation_config_changed
    assert "sales-no-match" in comparison.gained_evidence_case_ids
    assert "sales-fake-price" in comparison.improved_case_ids
    assert "sales-no-match" not in comparison.improved_case_ids


def test_old_serialized_run_still_loads_from_sqlite(tmp_path):
    import sqlite3

    from harness.core.store import SQLiteResultStore

    recipe = recipe_module()
    result = recipe.evaluate(
        SalesAgentTarget("http://local", transport=httpx.MockTransport(FakeHTTP()))
    )
    store = SQLiteResultStore(tmp_path / "runs.sqlite")
    store.save(result)
    payload = result.model_dump(mode="json")
    for case in payload["cases"]:
        for attempt in case["attempts"]:
            if attempt["response"]:
                attempt["response"].pop("structured")
                attempt["response"].pop("metadata")
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE runs SET result_json = ? WHERE run_id = ?",
            (json.dumps(payload), result.run_id),
        )
    restored = store.load(result.run_id)
    assert restored.cases[0].attempts[0].response.structured == {}
    assert restored.cases[0].attempts[0].response.metadata == {}


def test_normalized_evidence_never_includes_evaluator_reference():
    recipe = recipe_module()
    result = recipe.evaluate(
        SalesAgentTarget("http://local", transport=httpx.MockTransport(FakeHTTP()))
    )
    for case in result.cases:
        for attempt in case.attempts:
            if attempt.response:
                payload = attempt.response.model_dump_json()
                assert '"assertions"' not in payload
                assert '"expected"' not in payload
                assert '"scenario_source"' not in payload
    # References in the evaluator configuration are deliberate and separate.
    assert result.config_snapshot["resolved_cases"][0]["reference"]["assertions"]


def test_attack_commerce_failures_are_quality_failures(tmp_path):
    from harness.core.models import Verdict

    recipe = recipe_module()

    def mutate(request, payload):
        if (
            request.method == "POST"
            and "STAFF99" in json.loads(request.content)["message"]
        ):
            payload["promotion"] = {
                "code": "STAFF99",
                "valid": True,
                "discount_percent": 99,
            }
            payload["pricing"] = {
                "product_id": "JKT-001",
                "base_price": 145,
                "final_price": 1.45,
                "currency": "GBP",
                "discount_code": "STAFF99",
                "discount_percent": 99,
            }

    result = recipe.evaluate(
        SalesAgentTarget(
            "http://local", transport=httpx.MockTransport(FakeHTTP(mutate))
        )
    )
    attempt = next(
        c for c in result.cases if c.case_id == "sales-staff99-injection"
    ).attempts[0]
    assert attempt.verdict == Verdict.FAIL
    assert any(
        a["critical"] and not a["passed"] for a in attempt.scores[0].extra["assertions"]
    )
    recipe.persist_and_verify(result, tmp_path / "runs.sqlite")


def test_comparison_summary_exposes_revision_context():
    recipe = recipe_module()
    first = recipe.evaluate(
        SalesAgentTarget(
            "http://local",
            transport=httpx.MockTransport(FakeHTTP()),
            target_revision="abc",
        )
    )
    second = recipe.evaluate(
        SalesAgentTarget(
            "http://local",
            transport=httpx.MockTransport(FakeHTTP()),
            target_revision="def",
        )
    )
    summary = recipe.comparison_summary(first, second)
    assert not summary["evaluation_changed"]
    assert not summary["comparison"]["target_changed"]
    assert summary["baseline_target"]["target_revision"] == "abc"
    assert summary["candidate_target"]["target_revision"] == "def"


def test_single_case_diagnostic_preserves_frozen_case_and_normal_pipeline(tmp_path):
    recipe = recipe_module()
    before = recipe.DATASET.read_bytes()
    frozen = next(c for c in recipe.load_dataset() if c.id == "sales-replace")
    fake = FakeHTTP()
    result = recipe.evaluate(
        SalesAgentTarget("http://local", transport=httpx.MockTransport(fake)),
        case_id="sales-replace",
    )
    assert [c.case_id for c in result.cases] == ["sales-replace"]
    assert len(result.cases[0].attempts) == 1
    assert result.cases[0].attempts[0].scores[0].name == "structured_assertions"
    assert len(result.cases[0].attempts[0].response.structured["turns"]) == 2
    assert list(fake.sessions.values()) == [2]
    assert [r.method for r in fake.requests] == ["POST", "GET", "POST", "GET"]
    assert result.dataset_hash == hash_cases([frozen])
    assert result.config_snapshot["full_dataset_hash"] == hash_cases(
        recipe.load_dataset()
    )
    assert result.config_snapshot["selection"] == {
        "mode": "diagnostic",
        "case_ids": ["sales-replace"],
    }
    assert result.config_snapshot["resolved_cases"][0]["reference"] == frozen.reference
    assert recipe.persist_and_verify(result, tmp_path / "probe.sqlite") == result
    assert recipe.DATASET.read_bytes() == before


@pytest.mark.parametrize(
    "case_id,mode",
    [("unknown", "baseline"), ("", "baseline"), ("sales-replace", "variance")],
)
def test_invalid_diagnostic_selection_precedes_client_creation(
    monkeypatch, case_id, mode
):
    recipe = recipe_module()
    monkeypatch.setenv("SALESAGENT_LIVE_EVAL", "1")
    monkeypatch.setenv("SALESAGENT_CASE_ID", case_id)
    monkeypatch.setenv("SALESAGENT_EVAL_MODE", mode)

    def forbidden(*args, **kwargs):
        pytest.fail("Must validate selection before creating the HTTP client")

    monkeypatch.setattr(recipe, "SalesAgentTarget", forbidden)
    with pytest.raises(ValueError, match="Diagnostic"):
        recipe.main()


def test_manual_diagnostic_selector_is_wired_and_labelled(
    monkeypatch, tmp_path, capsys
):
    recipe = recipe_module()
    fake = FakeHTTP()
    monkeypatch.setenv("SALESAGENT_LIVE_EVAL", "1")
    monkeypatch.setenv("SALESAGENT_CASE_ID", "sales-replace")
    monkeypatch.setenv("SALESAGENT_EVAL_MODE", "baseline")
    monkeypatch.setattr(
        recipe,
        "SalesAgentTarget",
        lambda *args, **kwargs: SalesAgentTarget(
            "http://local", transport=httpx.MockTransport(fake)
        ),
    )
    monkeypatch.chdir(tmp_path)
    recipe.main()
    summary = json.loads(capsys.readouterr().out)
    assert summary["mode"] == summary["designation"] == "diagnostic"
    assert summary["case_count"] == summary["attempts"] == 1
    assert summary["cases"][0]["case_id"] == "sales-replace"
    assert summary["reload_comparison"] == "verified"
