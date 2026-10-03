"""Explicit offline descriptor → preview → execution → persistence → analysis.

Run with --output-dir pointing to a disposable directory. No code runs on import.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from harness.core.models import Score, ScorerKind, TargetResponse, TestCase
from harness.core.store import SQLiteResultStore
from harness.core.suites import EvaluationProfile, execute_suite, resolve_suite
from harness.regression.comparison import compare_runs, render_comparison_markdown
from harness.reporting.grouping import group_run_results, render_groups_markdown
from harness.targets.base import CallableTarget


class ExampleScorer:
    name = "example_exact"
    kind = ScorerKind.DETERMINISTIC
    requires: frozenset[str] = frozenset()

    def score(self, case: TestCase, response: TargetResponse) -> Score:
        passed = None if case.reference is None else response.output == case.reference
        return Score(
            name=self.name,
            kind=self.kind,
            value=float(passed) if passed is not None else 1.0,
            passed=passed,
        )


def _target(*, strip: bool) -> CallableTarget:
    def invoke(case: TestCase) -> TargetResponse:
        # This fake application consumes only intended input, never expectations.
        assert isinstance(case.input, dict)
        if case.input.get("simulate_timeout"):
            raise TimeoutError("Synthetic offline timeout")
        text = case.input["text"]
        return TargetResponse(
            output=text.strip() if strip else text,
            metadata={
                "target_revision": "echo-v2" if strip else "echo-v1",
                "evidence_schema_version": "example-evidence-v1",
            },
        )

    return CallableTarget(name="offline-echo", invoke=invoke)


def run_example(output_dir: Path) -> dict[str, Any]:
    """Write only to an explicit caller-owned output directory; never overwrite."""
    destinations = [
        output_dir / name for name in ("runs.sqlite", "analysis.json", "report.md")
    ]
    if any(path.exists() for path in destinations):
        raise ValueError(
            "Example output already exists; choose a fresh output directory"
        )
    resolved = resolve_suite(Path(__file__).parent / "data/taxonomy/suite.json")
    preview = resolved.preview.model_dump(mode="json")
    profile = EvaluationProfile(
        id="offline-exact-v1",
        taxonomy_evidence="excluded",
        scorer_configuration={
            "example_exact": {
                "version": "example-exact-v1",
                "null_reference": "informational",
            }
        },
    )
    baseline = execute_suite(
        resolved, _target(strip=False), [ExampleScorer()], profile=profile
    )
    candidate = execute_suite(
        resolved, _target(strip=True), [ExampleScorer()], profile=profile
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    store = SQLiteResultStore(destinations[0])
    store.save(baseline)
    store.save(candidate)
    # Everything below consumes saved evidence, not the descriptor/cases.
    baseline, candidate = store.load(baseline.run_id), store.load(candidate.run_id)
    groups = {
        by: group_run_results(candidate, by=by) for by in ("category", "tags", "risk")
    }
    comparison = compare_runs(baseline, candidate)
    analysis = {
        "preview": preview,
        "baseline_run_id": baseline.run_id,
        "candidate_run_id": candidate.run_id,
        "groups": {
            by: [asdict(group) for group in records] for by, records in groups.items()
        },
        "comparison": asdict(comparison),
    }
    destinations[1].write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    destinations[2].write_text(
        "\n".join(
            render_groups_markdown(records, title=f"Candidate by {by}")
            for by, records in groups.items()
        )
        + "\n"
        + render_comparison_markdown(comparison),
        encoding="utf-8",
    )
    return analysis


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    analysis = run_example(args.output_dir)
    print(
        json.dumps(
            {
                "selected_cases": analysis["preview"]["case_ids"],
                "comparison_context": analysis["comparison"]["context"]["status"],
                "output_dir": str(args.output_dir),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
