"""Persistence: a run that can't be reloaded can't be compared."""

from __future__ import annotations

import pytest
from conftest import StubScorer

from harness.core.config import RunConfig
from harness.core.models import RunResult
from harness.core.runner import run
from harness.core.store import JsonRunStore, RunNotFoundError, Store
from harness.packs.base import SimplePack
from harness.targets.base import StaticTarget


def _boom(case, response) -> float:
    raise RuntimeError("judge API 503")


def _result(**overrides) -> RunResult:
    defaults = {
        "config_path": "evals/demo.yaml",
        "config_snapshot": {"attempts": 2, "warnings": []},
        "target_name": "static",
        "pack_name": "demo",
        "dataset_path": "data/demo.jsonl",
        "dataset_hash": "abc123",
    }
    return RunResult(**{**defaults, **overrides})


class TestJsonRunStore:
    def test_json_store_satisfies_the_protocol(self, tmp_path):
        assert isinstance(JsonRunStore(tmp_path), Store)

    def test_save_then_load_round_trips(self, tmp_path):
        store = JsonRunStore(tmp_path)
        original = _result(model_versions={"target": "claude-opus-5"})

        path = store.save(original)
        restored = store.load(original.run_id)

        assert path.endswith(f"{original.run_id}.json")
        assert restored.model_dump() == original.model_dump()
        # Datetimes survive the trip as aware datetimes, not strings.
        assert restored.started_at == original.started_at
        assert restored.started_at.tzinfo is not None

    def test_save_creates_the_directory(self, tmp_path):
        store = JsonRunStore(tmp_path / "runs" / "nested")
        store.save(_result())
        assert (tmp_path / "runs" / "nested").is_dir()

    def test_saving_twice_overwrites_in_place(self, tmp_path):
        store = JsonRunStore(tmp_path)
        result = _result()
        store.save(result)
        result.config_snapshot = {"attempts": 5, "warnings": []}
        store.save(result)

        assert store.list_runs() == [result.run_id]
        assert store.load(result.run_id).config_snapshot["attempts"] == 5

    def test_no_temp_files_are_left_behind(self, tmp_path):
        store = JsonRunStore(tmp_path)
        store.save(_result())
        assert [p.suffix for p in tmp_path.iterdir()] == [".json"]

    def test_loading_an_unknown_run_raises(self, tmp_path):
        with pytest.raises(RunNotFoundError, match="No run 'nope'"):
            JsonRunStore(tmp_path).load("nope")

    def test_list_runs_is_empty_when_nothing_is_stored(self, tmp_path):
        assert JsonRunStore(tmp_path / "missing").list_runs() == []

    def test_list_runs_returns_every_stored_run(self, tmp_path):
        store = JsonRunStore(tmp_path)
        results = [_result(), _result(), _result()]
        for result in results:
            store.save(result)
        assert set(store.list_runs()) == {r.run_id for r in results}


class TestRunnerPersistence:
    def test_run_persists_when_given_a_store(self, tmp_path, cases, responses):
        store = JsonRunStore(tmp_path)
        result = run(
            RunConfig(attempts=2),
            StaticTarget(responses),
            SimplePack("demo", [StubScorer()]),
            cases,
            store=store,
        )

        restored = store.load(result.run_id)
        assert restored.model_dump() == result.model_dump()
        assert restored.aggregate_pass_rate == 1.0
        assert restored.cases[0].attempts[0].response.output == "4"

    def test_an_errored_run_is_still_persisted(self, tmp_path, cases, responses):
        """Especially an errored run — that's the one somebody has to debug."""
        store = JsonRunStore(tmp_path)
        pack = SimplePack("demo", [StubScorer(behaviour=_boom)])

        result = run(RunConfig(), StaticTarget(responses), pack, cases, store=store)

        restored = store.load(result.run_id)
        assert restored.error_rate == 1.0
        assert restored.aggregate_pass_rate is None
        assert "judge API 503" in restored.cases[0].attempts[0].error
