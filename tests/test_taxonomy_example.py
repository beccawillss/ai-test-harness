"""The complete example is offline, inert on import, and explicit about writes."""

import importlib.util
import json
from pathlib import Path

import pytest

from harness.core.models import Verdict
from harness.core.store import SQLiteResultStore

EXAMPLE = Path(__file__).parents[1] / "examples/taxonomy_suites.py"


def test_example_import_and_persisted_analysis(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location("taxonomy_example", EXAMPLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert list(tmp_path.iterdir()) == []
    output = tmp_path / "explicit-example"
    result = module.run_example(output)
    assert {p.name for p in output.iterdir()} == {
        "runs.sqlite",
        "analysis.json",
        "report.md",
    }
    assert (
        json.loads((output / "analysis.json").read_text())["preview"][
            "selected_case_count"
        ]
        == 4
    )
    store = SQLiteResultStore(output / "runs.sqlite", read_only=True)
    baseline = store.load(result["baseline_run_id"])
    candidate = store.load(result["candidate_run_id"])
    assert {a.verdict for c in baseline.cases for a in c.attempts} == set(Verdict)
    assert baseline.aggregate_pass_rate == 0.5
    assert candidate.aggregate_pass_rate == 1
    assert candidate.error_rate == baseline.error_rate == 0.25
    assert result["comparison"]["context"]["status"] == "changed"  # target revision
    assert result["comparison"]["cases"][1]["pass_rate"]["delta"] == 1
    assert sum(g["case_count"] for g in result["groups"]["tags"]) == 5
    assert "observed increase" in (output / "report.md").read_text()
    assert "non-additive" in (output / "report.md").read_text()
    with pytest.raises(ValueError, match="already exists"):
        module.run_example(output)
