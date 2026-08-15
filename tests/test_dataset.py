"""Dataset loading, fingerprinting, and runner integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.core.dataset import hash_cases, load_cases
from harness.core.models import TargetResponse
from harness.core.models import TestCase as EvaluationCase
from harness.core.runner import run
from harness.scorers.exact_match import ExactMatchScorer
from harness.targets.base import StaticTarget


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_jsonl_and_preserves_case_data(tmp_path):
    path = _write(
        tmp_path / "cases.jsonl",
        '{"id":"c1","input":"2+2?","reference":"4","tags":["smoke"]}\n'
        "\n"
        '{"id":"c2","input":{"task":"search"},'
        '"extra":{"category":"RAG"}}\n',
    )

    cases = load_cases(path)

    assert [case.id for case in cases] == ["c1", "c2"]
    assert cases[0].tags == ["smoke"]
    assert cases[1].input == {"task": "search"}
    assert cases[1].extra == {"category": "RAG"}


def test_invalid_case_reports_file_and_line_number(tmp_path):
    path = _write(
        tmp_path / "broken.jsonl",
        '{"id":"valid","input":"hello"}\n'
        "\n"
        '{"id":"missing-input"}\n',
    )

    with pytest.raises(ValueError, match=r"broken\.jsonl:3: invalid TestCase"):
        load_cases(path)


def test_missing_file_is_reported_as_a_dataset_error(tmp_path):
    with pytest.raises(ValueError, match="Cannot read dataset"):
        load_cases(tmp_path / "missing.jsonl")


def test_empty_dataset_is_rejected(tmp_path):
    path = _write(tmp_path / "empty.jsonl", "\n  \n")

    with pytest.raises(ValueError, match="contains no test cases"):
        load_cases(path)


def test_hash_is_stable_across_equivalent_json_formatting(tmp_path):
    compact = _write(
        tmp_path / "compact.jsonl",
        '{"id":"c1","input":"hello","reference":"world","tags":["smoke"]}\n',
    )
    reformatted = _write(
        tmp_path / "reformatted.jsonl",
        '{ "tags": ["smoke"], "reference": "world", '
        '"input": "hello", "id": "c1" }\n',
    )

    assert hash_cases(load_cases(compact)) == hash_cases(load_cases(reformatted))


def test_hash_changes_with_content_or_order():
    first = EvaluationCase(id="c1", input="a")
    second = EvaluationCase(id="c2", input="b")
    edited = EvaluationCase(id="c2", input="B")

    assert hash_cases([first, second]) != hash_cases([first, edited])
    assert hash_cases([first, second]) != hash_cases([second, first])


def test_jsonl_cases_flow_through_runner_to_run_result(tmp_path):
    path = _write(
        tmp_path / "arithmetic.jsonl",
        '{"id":"addition","input":"2+2?","reference":"4",'
        '"tags":["smoke","reasoning"]}\n',
    )
    cases = load_cases(path)

    result = run(
        StaticTarget({"addition": TargetResponse(output="4")}),
        [ExactMatchScorer()],
        cases,
        dataset_path=str(path),
    )

    assert result.dataset_path == str(path)
    assert result.dataset_hash == hash_cases(cases)
    assert result.cases[0].tags == ["smoke", "reasoning"]
    assert result.cases[0].pass_rate == 1.0
