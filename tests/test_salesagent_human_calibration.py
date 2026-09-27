"""Entire offline recipe from synthetic saved data; all execution paths bombed."""

import importlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_calibration_io import authored_draft
from test_salesagent_judge_replay import forbid_targets

from harness.core.calibration_io import byte_hash, load_export, load_result
from harness.core.dataset import hash_cases, load_cases
from harness.core.fingerprints import canonical_json
from harness.core.models import (
    AttemptResult,
    CaseResult,
    RunResult,
    Score,
    ScorerKind,
    TargetResponse,
    Verdict,
)
from harness.core.replay import ReplayAttemptResult, ReplayResult
from harness.core.store import SQLiteResultStore
from harness.judges.openai import OpenAIJudge
from harness.packs import salesagent_semantic as pack
from harness.targets._salesagent_contract import Constraints


@pytest.fixture
def recipe(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "examples"))
    return importlib.import_module("salesagent_human_calibration")


def bomb_execution(monkeypatch):
    import httpx

    from harness.scorers.base import JudgedScorer

    forbid_targets(monkeypatch)

    def bomb(*args, **kwargs):
        pytest.fail(
            "Calibration attempted target/judge/client construction or execution"
        )

    monkeypatch.setattr(OpenAIJudge, "__init__", bomb)
    monkeypatch.setattr(OpenAIJudge, "__call__", bomb)
    monkeypatch.setattr(httpx, "Client", bomb)
    monkeypatch.setattr(JudgedScorer, "score", bomb)
    monkeypatch.setattr(JudgedScorer, "score_prepared", bomb)
    monkeypatch.setattr(JudgedScorer, "score_labelled", bomb)


def synthetic_source(run_id, cases, all_cases, scoring, *, attempt=0):
    results = []
    for case in cases:
        turns = [
            {
                "index": i,
                "input": shopper,
                "output": f"Synthetic saved answer {i}.",
                "structured": {
                    "recommendations": [],
                    "promotion": None,
                    "pricing": None,
                    "private": "SECRET_STRUCTURED",
                },
                "evidence": {
                    "resolved_constraints": Constraints().model_dump(),
                    "recommendation_validation": {"passed": "SECRET_VERDICT"},
                },
                "trajectory": [],
                "metadata": {"hidden_prompt": "SECRET_TURN"},
            }
            for i, shopper in enumerate(case.input["turns"])
        ]
        response = TargetResponse(
            output=turns[-1]["output"],
            structured={"turns": turns},
            raw={"api_key": "SECRET_RAW"},
            metadata={"provider": "SECRET_PROVIDER"},
        )
        results.append(
            CaseResult(
                case_id=case.id,
                tags=case.tags,
                attempts=[
                    AttemptResult(
                        index=attempt,
                        response=response,
                        scores=[
                            Score(
                                name=pack.SCORER_NAME,
                                kind=ScorerKind.JUDGED,
                                value=0.8,
                                passed=True,
                                reason="SECRET_PRIOR_REASON",
                                extra={
                                    "judge_model": "fake-v1",
                                    "judge": {
                                        "observed_model": "SECRET_OBSERVED_MODEL"
                                    },
                                },
                            )
                        ],
                        verdict=Verdict.ERROR,
                        error="SECRET_UNRELATED_ERROR",
                    )
                ],
            )
        )
    return RunResult(
        run_id=run_id,
        config_path="/PRIVATE/config",
        dataset_path="/PRIVATE/dataset",
        dataset_hash=hash_cases(cases),
        target_name="salesagent",
        pack_name=pack.PROFILE,
        config_snapshot={
            "scorers": [scoring.preparation_configuration],
            "semantic_evaluation": {
                **pack.configuration(),
                "judge": OpenAIJudge.configuration_for(model="fake-v1"),
            },
            "full_dataset_hash": hash_cases(all_cases),
            "selection": {"case_ids": [c.id for c in cases]},
            "resolved_cases": [
                c.model_dump(mode="json", exclude={"extra"}) for c in cases
            ],
        },
        cases=results,
    )


@pytest.fixture
def stores(recipe, tmp_path, monkeypatch):
    bomb_execution(monkeypatch)
    # Direct normalized fixtures: even setup constructs/invokes no targets.
    cases = pack.load_dataset()
    scoring = pack.make_scorer(recipe._no_judge, "fake-v1")
    source_db, replay_db = tmp_path / "sources.sqlite", tmp_path / "replays.sqlite"
    store = SQLiteResultStore(source_db)
    for run_id, selection, index in (
        ("6c7f864209bd", cases, 0),
        ("bbeb64511171", cases, 0),
        ("a68ace7dd819", [c for c in cases if c.id == "sales-discount-override"], 1),
    ):
        store.save(synthetic_source(run_id, selection, cases, scoring, attempt=index))
    replays = SQLiteResultStore(replay_db)
    now = datetime.now(UTC)
    for (run_id, case_id, attempt), replay_id in recipe.REPLAYS.items():
        prepared = recipe.prepare_source(
            source_db, pack.DATASET, run_id, case_id, attempt
        )
        data = prepared.model_dump()
        data["requested_attempt_count"] = 5
        prepared = type(prepared).model_validate(data)
        calls = tuple(
            ReplayAttemptResult(
                index=i,
                score=Score(
                    name=pack.SCORER_NAME,
                    kind=ScorerKind.JUDGED,
                    value=value,
                    passed=value >= 0.7,
                    reason="SECRET_REPLAY_REASON",
                    extra={"judge_model": "fake-v1"},
                ),
                verdict=Verdict.PASS if value >= 0.7 else Verdict.FAIL,
                started_at=now,
                duration_ms=0,
                prompt_hash=prepared.prepared.prompt_hash,
                input_hash=prepared.input_hash,
            )
            for i, value in enumerate((0.8, 0.6, 0.6, 0.8, 0.8))
        )
        replays.save_replay(
            ReplayResult(
                replay_id=replay_id,
                input=prepared,
                started_at=now,
                finished_at=now,
                attempts=calls,
            )
        )
    return source_db, replay_db


def test_full_18_item_offline_workflow_no_target_judge_or_source_mutation(
    recipe, stores, tmp_path, monkeypatch, capsys
):
    source_db, replay_db = stores
    before = {p: byte_hash(p.read_bytes()) for p in stores}
    original_load_replay = SQLiteResultStore.load_replay
    monkeypatch.setattr(
        SQLiteResultStore,
        "load_replay",
        lambda *args: pytest.fail("Judge observations loaded before freeze"),
    )
    output, frozen, report = (
        tmp_path / name for name in ("export", "frozen", "analysis")
    )
    assert (
        recipe.main(
            [
                "export",
                "--source-db",
                str(source_db),
                "--output",
                str(output),
                "--annotator",
                "synthetic-reviewer",
            ]
        )
        == 0
    )
    manifest, packet = load_export(output)
    assert len(manifest.examples) == 18
    assert len({e.example_id for e in manifest.examples}) == 18
    assert {e.prior_exposure for e in manifest.examples} == {"prior_results_seen"}
    assert sum(len(json.loads(i.evidence_json)["turns"]) > 1 for i in packet.items) == 5
    selectors = [
        (
            e.prepared.source.run_id,
            e.prepared.source.case_id,
            e.prepared.source.attempt_index,
        )
        for e in manifest.examples
    ]
    assert tuple(selectors) == recipe.pilot_selectors(
        [c.id for c in pack.load_dataset()]
    )
    assert sum(e.observation_policy.kind == "replay" for e in manifest.examples) == 2
    assert packet.contract.anchors == (0, 0.3, 0.6, 0.8, 1)
    assert packet.contract.threshold == 0.7
    assert packet.contract.instruction_version == "salesagent-human-instructions-v1"
    review = "\n".join(p.read_text() for p in (output / "review").iterdir())
    for excluded in (
        "SECRET_",
        "fake-v1",
        "6c7f864209bd",
        "bbeb64511171",
        "a68ace7dd819",
        "sales-discount-override",
        "sources.sqlite",
        "prior_results_seen",
        "known_instability_diagnostic",
        "/PRIVATE",
        *recipe.REPLAYS.values(),
    ):
        assert excluded not in review
    for example in manifest.examples:
        item = next(i for i in packet.items if i.example_id == example.example_id)
        assert item.evidence_json == example.prepared.prepared.evidence_json
        assert example.prepared.source.response_hash not in review
        assert example.prepared.input_hash not in review
    # No user-facing live label is generated; authored_draft is a synthetic fixture.
    draft = authored_draft(output)
    assert (
        recipe.main(
            [
                "freeze",
                "--export",
                str(output),
                "--annotations",
                str(draft),
                "--output",
                str(frozen),
            ]
        )
        == 0
    )
    monkeypatch.setattr(SQLiteResultStore, "load_replay", original_load_replay)
    assert (
        recipe.main(
            [
                "analyze",
                "--frozen",
                str(frozen),
                "--source-db",
                str(source_db),
                "--replay-db",
                str(replay_db),
                "--output",
                str(report),
            ]
        )
        == 0
    )
    result = load_result(report)
    assert len(result.observations) == 18
    assert result.summary["completed_judge_scores"] == 26  # 16 historical + 2 * 5
    assert result.summary["primary_blind_verified"]["example_count"] == 0
    assert result.summary["primary_blind_verified"]["mae"] is None
    assert (
        result.summary["cohorts"]["prior_results_seen/historical_input_reconstructed"][
            "example_count"
        ]
        == 16
    )
    assert (
        result.summary["cohorts"]["prior_results_seen/frozen_request_verified"][
            "example_count"
        ]
        == 2
    )
    assert before == {p: byte_hash(p.read_bytes()) for p in stores}
    stdout = capsys.readouterr().out
    assert "SECRET" not in stdout and str(tmp_path) not in stdout
    assert "0.6" not in stdout


def test_analyze_rejects_missing_freeze_before_any_database_open(
    recipe, tmp_path, monkeypatch
):
    def bomb(*args, **kwargs):
        pytest.fail("Database opened before freeze validation")

    monkeypatch.setattr(SQLiteResultStore, "__init__", bomb)
    assert (
        recipe.main(
            [
                "analyze",
                "--frozen",
                str(tmp_path / "missing"),
                "--source-db",
                str(tmp_path / "sources"),
                "--replay-db",
                str(tmp_path / "judges"),
                "--output",
                str(tmp_path / "result"),
            ]
        )
        == 1
    )


def test_frozen_dataset_hashes_and_no_pack_changes():
    baseline = Path("datasets/salesagent/baseline.jsonl")
    assert (
        byte_hash(baseline.read_bytes())
        == "f24ffe05b08d75848860f71ef726cf96dccb78e457e5757fb7144cd30db4a747"
    )
    assert (
        hash_cases(load_cases(baseline))
        == "c1a73ef207f2cabe3292d743504f7249f4729825d785adff5b6bf14ad6a7b12b"
    )
    assert (
        byte_hash(pack.DATASET.read_bytes())
        == "3200acd541c6db9f3bb3301186f4213746e177c0c3048b4ad99434da590791a9"
    )
    assert (
        hash_cases(pack.load_dataset())
        == "33654c3f4870efc67edd8e30a6ae0a82c17eb58c8c30cb323add5d0efe414849"
    )


def test_pilot_selection_invalid_cardinality_and_duplicate_ids(recipe):
    for ids in ([], ["same"] * 14, [str(i) for i in range(15)]):
        with pytest.raises(ValueError):
            recipe.pilot_selectors(ids)


def test_no_live_path_and_no_judge_callable(recipe):
    with pytest.raises(SystemExit):
        recipe.main(["--live"])
    with pytest.raises(AssertionError):
        recipe._no_judge("prompt")


@pytest.mark.parametrize("field", ["input", "reference", "extra"])
def test_changed_dataset_rejected_before_export(recipe, stores, tmp_path, field):
    cases = [c.model_dump(mode="json") for c in pack.load_dataset()]
    if field == "input":
        cases[0][field]["turns"][0] += " changed"
    elif field == "reference":
        cases[0][field]["semantic"]["expectations"].append("changed")
    else:
        cases[0][field]["new"] = "changed"
    dataset = tmp_path / "changed.jsonl"
    dataset.write_text("\n".join(canonical_json(c) for c in cases))
    with pytest.raises(ValueError, match="fingerprint"):
        recipe.pilot_manifest(stores[0], dataset)


def test_contract_changes_cannot_join_original_prepared_source(recipe, stores):
    prepared = recipe.prepare_source(
        stores[0], pack.DATASET, "6c7f864209bd", "sales-discount-override", 0
    )
    original = recipe.rating_contract()
    for key, value in (
        ("rubric", "different"),
        ("threshold", 0.8),
        ("projection_version", "v3"),
        ("evidence_settings_json", "{}"),
    ):
        data = original.model_dump()
        data[key] = value
        changed = type(original).model_validate(data)
        with pytest.raises(ValueError):
            changed.check_prepared(prepared)
