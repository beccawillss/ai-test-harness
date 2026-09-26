"""Persisted semantic replay recipe; HTTP calls are MockTransport-only."""

import importlib
import json
from pathlib import Path

import httpx
import pytest
from test_openai_judge import envelope
from test_salesagent_semantic import target_response

from harness.core.dataset import hash_cases
from harness.core.fingerprints import fingerprint
from harness.core.models import AttemptResult, CaseResult, RunResult, Verdict
from harness.core.replay import JudgeConfiguration, replay
from harness.core.store import SQLiteResultStore
from harness.judges.openai import ENDPOINT, OpenAIJudge
from harness.packs import salesagent_semantic as pack


@pytest.fixture
def recipe(monkeypatch):
    for name in (
        "HARNESS_JUDGE_REPLAY_LIVE",
        "HARNESS_JUDGE_PROVIDER",
        "HARNESS_JUDGE_MODEL",
        "HARNESS_JUDGE_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "examples"))
    return importlib.import_module("salesagent_judge_replay")


@pytest.fixture
def saved(tmp_path):
    # Build synthetic normalized evidence with the existing scripted transport,
    # before installing replay's bomb constructors. No external target exists.
    cases = pack.load_dataset()
    case = next(c for c in cases if c.id == "sales-previous-product")
    response = target_response(case)
    response.raw = {"hidden_prompt": "SECRET_RAW"}
    response.metadata["unknown"] = "SECRET_METADATA"
    for turn in response.structured["turns"]:
        turn["metadata"]["private"] = "SECRET_TURN"
        turn["structured"]["private"] = "SECRET_STRUCTURED"
        turn["evidence"]["recommendation_validation"] = {"passed": "SECRET_VERDICT"}
    scoring = pack.make_scorer(lambda _: pytest.fail("seed judge called"), "fake-v1")
    source = RunResult(
        run_id="saved-source",
        config_path="/PRIVATE/repo/recipe.py",
        dataset_path="/PRIVATE/dataset",
        dataset_hash=hash_cases([case]),
        target_name="salesagent",
        pack_name=pack.PROFILE,
        config_snapshot={
            "scorers": [scoring.preparation_configuration],
            "semantic_evaluation": {
                **pack.configuration(),
                "judge": OpenAIJudge.configuration_for(model="fake-v1"),
            },
            "full_dataset_hash": hash_cases(cases),
            "selection": {"case_ids": [case.id]},
            "resolved_cases": [case.model_dump(mode="json", exclude={"extra"})],
            "evidence_schema_version": "salesagent-evidence-v2",
        },
        cases=[
            CaseResult(
                case_id=case.id,
                tags=case.tags,
                attempts=[
                    AttemptResult(
                        index=0,
                        response=response,
                        verdict=Verdict.ERROR,
                        error="SECRET_PRIOR_ERROR",
                    ),
                ],
            )
        ],
    )
    path = tmp_path / "private" / "source.sqlite"
    SQLiteResultStore(path).save(source)
    return path, case, source


def options(saved, tmp_path):
    source, case, _ = saved
    return {
        "source_db": source,
        "source_run": "saved-source",
        "case_id": case.id,
        "source_attempt": 0,
        "dataset": pack.DATASET,
        "attempts": 5,
        "output_db": tmp_path / "replays.sqlite",
    }


def arguments(options):
    return [
        item
        for key, value in options.items()
        for item in ("--" + key.replace("_", "-"), str(value))
    ]


def forbid_targets(monkeypatch):
    from harness.core import runner
    from harness.targets import salesagent
    from harness.targets.base import StaticTarget

    def bomb(*args, **kwargs):
        pytest.fail("Replay constructed or invoked a target/normal runner")

    monkeypatch.setattr(runner, "run", bomb)
    monkeypatch.setattr(salesagent.SalesAgentTarget, "__init__", bomb)
    monkeypatch.setattr(salesagent.SalesAgentTarget, "invoke", bomb)
    monkeypatch.setattr(StaticTarget, "__init__", bomb)
    monkeypatch.setattr(StaticTarget, "invoke", bomb)


def test_import_and_dry_run_never_construct_clients_or_expose_paths(
    recipe, saved, tmp_path, monkeypatch, capsys
):
    before = saved[0].read_bytes()
    forbid_targets(monkeypatch)
    monkeypatch.setattr(
        httpx, "Client", lambda *a, **k: pytest.fail("client constructed")
    )
    monkeypatch.setenv("OPENAI_API_KEY", "SECRET_TARGET_KEY")
    monkeypatch.setenv("SALESAGENT_BASE_URL", "SECRET_TARGET_URL")
    monkeypatch.setenv("HARNESS_JUDGE_API_KEY", "SECRET_JUDGE_KEY")
    importlib.reload(recipe)
    opts = options(saved, tmp_path)
    recipe.main(arguments(opts))  # Dry-run is the default.
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["judge_calls"] == report["target_calls"] == 0
    assert report["source"]["database"] == "external-source"
    assert report["compatibility"] == "matching_recorded_configuration"
    assert report["source"]["response_hash"] == fingerprint(
        saved[2].cases[0].attempts[0].response.model_dump(mode="json")
    )
    assert report["threshold"] == 0.7
    assert (
        str(tmp_path) not in output
        and "PRIVATE" not in output
        and "SECRET" not in output
    )
    assert saved[0].read_bytes() == before and not opts["output_db"].exists()


def test_identical_stateless_requests_from_saved_multiturn_evidence(
    recipe, saved, tmp_path, monkeypatch
):
    forbid_targets(monkeypatch)
    prepared = recipe.prepare_from_store(**options(saved, tmp_path))
    payload = json.loads(prepared.prepared.evidence_json)
    assert len(payload["turns"]) == 2
    assert [t["shopper"] for t in payload["turns"]] == saved[1].input["turns"]
    requests = []
    values = iter([0.8, 0.6, 0.8, 0.8, 0.6])

    def provider(request):
        assert str(request.url) == ENDPOINT and request.method == "POST"
        requests.append(request)
        return httpx.Response(
            200,
            json=envelope(
                json.dumps({"score": next(values), "reason": "Clarity finding."})
            ),
            headers={"set-cookie": "conversation=SECRET_COOKIE"},
        )

    judge = OpenAIJudge(
        api_key="JUDGE_ONLY_KEY",
        model="fake-v1",
        transport=httpx.MockTransport(provider),
    )
    try:
        result = replay(
            prepared,
            pack.make_scorer(judge, "fake-v1"),
            judge_configuration=lambda: JudgeConfiguration.model_validate(
                judge.configuration
            ),
        )
    finally:
        judge.close()
    assert len(requests) == 5 and len({r.content for r in requests}) == 1
    for request in requests:
        body = json.loads(request.content)
        assert "previous_response_id" not in body and "conversation" not in body
        assert "cookie" not in request.headers
        assert request.headers["authorization"] == "Bearer JUDGE_ONLY_KEY"
        assert body["tools"] == [] and body["store"] is False
        assert (
            "SECRET" not in request.content.decode()
            and "JUDGE_ONLY_KEY" not in request.content.decode()
        )
        assert (
            "assertions" not in request.content.decode()
            and '"passed"' not in request.content.decode()
        )
    assert result.summary["threshold_crossing"] is True
    source_before = saved[0].read_bytes()
    restored = recipe.persist_and_verify(result, saved[0], tmp_path / "replay.sqlite")
    assert restored == result and saved[0].read_bytes() == source_before
    assert (
        "SECRET" not in restored.model_dump_json()
        and str(tmp_path) not in restored.model_dump_json()
    )


@pytest.mark.parametrize(
    "failure", ["timeout", "http", "malformed", "incomplete", "telemetry"]
)
def test_provider_failures_among_successful_attempts(recipe, saved, tmp_path, failure):
    calls = []

    def provider(request):
        calls.append(request)
        if len(calls) != 2:
            return httpx.Response(200, json=envelope('{"score":0.8,"reason":"Clear."}'))
        if failure == "timeout":
            raise httpx.ReadTimeout("SECRET_TIMEOUT")
        if failure == "http":
            return httpx.Response(500, text="SECRET_BODY")
        data = envelope(
            "SECRET_BAD_JUDGMENT"
            if failure == "malformed"
            else '{"score":0.8,"reason":"Clear."}'
        )
        if failure == "incomplete":
            data["status"] = "incomplete"
        if failure == "telemetry":
            data["usage"]["input_tokens"] = "SECRET_BAD_TOKEN"
        return httpx.Response(200, json=data)

    prepared = recipe.prepare_from_store(**options(saved, tmp_path))
    judge = OpenAIJudge(
        api_key="SECRET_KEY", model="fake-v1", transport=httpx.MockTransport(provider)
    )
    try:
        result = replay(
            prepared,
            pack.make_scorer(judge, "fake-v1"),
            judge_configuration=lambda: JudgeConfiguration.model_validate(
                judge.configuration
            ),
        )
    finally:
        judge.close()
    assert len(calls) == 5 and result.summary["error_count"] == 1
    assert result.summary["scores_by_attempt"] == [0.8, None, 0.8, 0.8, 0.8]
    if failure == "malformed":
        assert result.attempts[1].observation.total_tokens == 30
    else:
        assert result.attempts[1].observation.total_tokens is None
    assert "SECRET" not in result.model_dump_json()


@pytest.mark.parametrize("kind", ["same", "symlink", "hardlink"])
def test_same_database_destinations_rejected(recipe, saved, tmp_path, kind):
    output = tmp_path / "alias.sqlite"
    if kind == "same":
        output = saved[0]
    elif kind == "symlink":
        output.symlink_to(saved[0])
    else:
        output.hardlink_to(saved[0])
    with pytest.raises(ValueError, match="must differ"):
        recipe.prepare_from_store(**(options(saved, tmp_path) | {"output_db": output}))


@pytest.mark.parametrize(
    "change",
    [
        "missing_db",
        "missing_run",
        "missing_case",
        "missing_attempt",
        "zero_attempts",
        "unknown_model",
        "dataset",
    ],
)
def test_preflight_failure_never_constructs_judge(
    recipe, saved, tmp_path, monkeypatch, capsys, change
):
    opts = options(saved, tmp_path)
    if change == "missing_db":
        opts["source_db"] = tmp_path / "absent" / "missing.sqlite"
    elif change == "missing_run":
        opts["source_run"] = "missing"
    elif change == "missing_case":
        opts["case_id"] = "missing"
    elif change == "missing_attempt":
        opts["source_attempt"] = 8
    elif change == "zero_attempts":
        opts["attempts"] = 0
    elif change == "unknown_model":
        monkeypatch.setenv("HARNESS_JUDGE_MODEL", "new-model")
    else:
        bad = tmp_path / "PRIVATE-dataset.jsonl"
        bad.write_text('{"id": "x"}\n')
        opts["dataset"] = bad
        with pytest.raises(ValueError, match=r"PRIVATE-dataset.jsonl:1:"):
            pack.load_dataset(bad)
    monkeypatch.setattr(
        httpx, "Client", lambda *a, **k: pytest.fail("client constructed")
    )
    monkeypatch.setenv("HARNESS_JUDGE_REPLAY_LIVE", "1")
    with pytest.raises(SystemExit, match="preflight failed") as caught:
        recipe.main([*arguments(opts), "--live"])
    assert str(tmp_path) not in str(caught.value) and "PRIVATE" not in str(caught.value)
    assert not capsys.readouterr().out and not opts["output_db"].exists()
    if change == "missing_db":
        assert not opts["source_db"].parent.exists()


def test_reconfigured_mode_is_explicit(recipe, saved, tmp_path):
    prepared = recipe.prepare_from_store(
        **options(saved, tmp_path), judge_model="different", allow_reconfigured=True
    )
    assert (
        prepared.compatibility == "different" and "judge.model" in prepared.differences
    )


def test_old_missing_evidence_cannot_be_upgraded(recipe, saved, tmp_path):
    source = saved[2].model_copy(deep=True)
    source.run_id = "old"
    source.config_snapshot["semantic_evaluation"]["projection_version"] = (
        "salesagent-semantic-evidence-v1"
    )
    source.config_snapshot["scorers"][0]["projection_version"] = (
        "salesagent-semantic-evidence-v1"
    )
    for turn in source.cases[0].attempts[0].response.structured["turns"]:
        for call in turn["trajectory"]:
            if call["name"] == "get_product":
                call["result"].pop("waterproof_rating", None)
    SQLiteResultStore(saved[0]).save(source)
    with pytest.raises(ValueError, match="cannot be prepared"):
        recipe.prepare_from_store(
            **(options(saved, tmp_path) | {"source_run": "old"}),
            allow_reconfigured=True,
        )


def test_main_live_optin_and_persistence_failure(
    recipe, saved, tmp_path, monkeypatch, capsys
):
    opts = options(saved, tmp_path)
    forbid_targets(monkeypatch)
    with pytest.raises(SystemExit, match="opt-in"):
        recipe.main([*arguments(opts), "--live"])
    monkeypatch.setenv("HARNESS_JUDGE_REPLAY_LIVE", "1")
    monkeypatch.setenv("HARNESS_JUDGE_PROVIDER", "openai")
    monkeypatch.setenv("HARNESS_JUDGE_MODEL", "fake-v1")
    monkeypatch.setenv("HARNESS_JUDGE_API_KEY", "SECRET_KEY")
    requests = []
    closed = []

    class FakeJudge(OpenAIJudge):
        def __init__(self, **kwargs):
            def provider(request):
                assert str(request.url) == ENDPOINT
                requests.append(request)
                return httpx.Response(
                    200, json=envelope('{"score":0.8,"reason":"Clear."}')
                )

            super().__init__(**kwargs, transport=httpx.MockTransport(provider))

        def close(self):
            closed.append(True)
            super().close()

    monkeypatch.setattr(recipe, "OpenAIJudge", FakeJudge)
    recipe.main([*arguments(opts), "--live"])
    report = json.loads(capsys.readouterr().out)
    assert (
        report["reload_verification"] == "verified"
        and len(requests) == 5
        and closed == [True]
    )
    assert str(tmp_path) not in json.dumps(report) and "SECRET" not in json.dumps(
        report
    )

    def fail_save(*args, **kwargs):
        raise OSError("SECRET_PATH_OR_CREDENTIAL")

    monkeypatch.setattr(recipe, "persist_and_verify", fail_save)
    with pytest.raises(SystemExit, match="persistence failed") as caught:
        recipe.main([*arguments(opts), "--live"])
    assert "SECRET" not in str(caught.value) and not capsys.readouterr().out
    assert closed == [True, True]
