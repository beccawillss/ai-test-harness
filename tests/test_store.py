"""SQLite persistence and failure inspection."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest

from harness.core.models import TargetResponse
from harness.core.models import TestCase as EvaluationCase
from harness.core.runner import run
from harness.core.store import SQLiteResultStore
from harness.scorers.exact_match import ExactMatchScorer
from harness.targets.base import StaticTarget


def _result():
    cases = [
        EvaluationCase(id="passing", input="2+2?", reference="4"),
        EvaluationCase(id="failing", input="2+3?", reference="5"),
        EvaluationCase(id="erroring", input="2+4?", reference="6"),
    ]
    target = StaticTarget(
        {
            "passing": TargetResponse(output="4"),
            "failing": TargetResponse(output="wrong"),
        }
    )
    return run(target, [ExactMatchScorer()], cases, dataset_path="cases.jsonl")


def test_save_and_load_round_trip_complete_result(tmp_path):
    store = SQLiteResultStore(tmp_path / "runs.sqlite")
    original = _result()

    store.save(original)
    restored = store.load(original.run_id)

    assert restored.model_dump() == original.model_dump()
    assert restored.aggregate_pass_rate == original.aggregate_pass_rate
    assert restored.error_rate == original.error_rate


def test_store_creates_parent_directories_and_database(tmp_path):
    path = tmp_path / "nested" / "results" / "runs.sqlite"

    SQLiteResultStore(path)

    assert path.is_file()


def test_connection_is_closed_after_context_exits(tmp_path):
    store = SQLiteResultStore(tmp_path / "runs.sqlite")

    with store._connect() as connection:
        connection.execute("SELECT 1")

    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connection.execute("SELECT 1")


def test_duplicate_run_id_is_rejected_without_replacing_original(tmp_path):
    store = SQLiteResultStore(tmp_path / "runs.sqlite")
    original = _result()
    store.save(original)
    changed = original.model_copy(update={"target_name": "changed"})

    with pytest.raises(ValueError, match=f"Run '{original.run_id}' is already stored"):
        store.save(changed)

    assert store.load(original.run_id).target_name == original.target_name


def test_loading_unknown_run_raises_key_error(tmp_path):
    store = SQLiteResultStore(tmp_path / "runs.sqlite")

    with pytest.raises(KeyError, match="Run 'missing' was not found"):
        store.load("missing")


def test_list_runs_returns_summaries_newest_first(tmp_path):
    store = SQLiteResultStore(tmp_path / "runs.sqlite")
    older = _result().model_copy(
        update={"started_at": datetime(2026, 1, 1, tzinfo=UTC)}
    )
    newer = _result().model_copy(
        update={"started_at": datetime(2026, 2, 1, tzinfo=UTC)}
    )
    store.save(older)
    store.save(newer)

    summaries = store.list_runs()

    assert [summary.run_id for summary in summaries] == [newer.run_id, older.run_id]
    assert summaries[0].target_name == newer.target_name
    assert summaries[0].dataset_hash == newer.dataset_hash
    assert summaries[0].aggregate_pass_rate == newer.aggregate_pass_rate
    assert summaries[0].error_rate == newer.error_rate


def test_list_runs_is_empty_for_new_store(tmp_path):
    assert SQLiteResultStore(tmp_path / "runs.sqlite").list_runs() == []


def test_problem_cases_include_failures_and_errors_with_diagnostics(tmp_path):
    store = SQLiteResultStore(tmp_path / "runs.sqlite")
    result = _result()
    store.save(result)

    problems = store.problem_cases(result.run_id)

    assert [case.case_id for case in problems] == ["failing", "erroring"]
    failed_attempt = problems[0].attempts[0]
    error_attempt = problems[1].attempts[0]
    assert failed_attempt.response == TargetResponse(output="wrong")
    assert failed_attempt.scores[0].passed is False
    assert error_attempt.response is None
    assert "LookupError" in (error_attempt.error or "")
