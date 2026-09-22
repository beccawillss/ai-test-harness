"""Explicit Python recipe. Importing this module never makes HTTP requests."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from harness.core.dataset import hash_cases, load_cases
from harness.core.models import RunResult, TestCase
from harness.core.runner import run
from harness.core.store import SQLiteResultStore
from harness.regression.comparison import compare_runs
from harness.scorers.base import Scorer
from harness.scorers.rubric_judge import RubricJudgeScorer
from harness.scorers.structured_assertions import (
    SCHEMA_VERSION,
    StructuredAssertionsScorer,
    validate_assertions,
)
from harness.targets.salesagent import (
    EVIDENCE_VERSION,
    SalesAgentTarget,
    validate_input,
)

DATASET = Path(__file__).resolve().parents[1] / "datasets/salesagent/baseline.jsonl"
VARIANCE_IDS = frozenset(
    {
        "sales-replace",
        "sales-staff99-injection",
        "sales-fake-price",
        "sales-previous-product",
        "sales-conversation",
    }
)


def load_dataset(path: Path = DATASET) -> list[TestCase]:
    """Preflight every case, including those outside a selected variance subset."""
    cases = load_cases(path)
    lines = [
        i for i, text in enumerate(path.read_text().splitlines(), 1) if text.strip()
    ]
    seen: set[str] = set()
    for line, case in zip(lines, cases):
        try:
            validate_input(case.input)
            validate_assertions(case.reference)
            if case.id in seen:
                raise ValueError("Duplicate case ID")
            seen.add(case.id)
        except ValueError as exc:
            raise ValueError(f"{path}:{line}: invalid evaluation case: {exc}") from None
    if len(cases) != 14 or not VARIANCE_IDS <= seen:
        raise ValueError(
            "Baseline requires 14 cases and the five configured variance IDs"
        )
    return cases


def select_cases(
    cases: list[TestCase],
    mode: Literal["baseline", "variance"],
    *,
    case_id: str | None = None,
) -> tuple[list[TestCase], int]:
    if case_id is not None:
        if mode != "baseline":
            raise ValueError(
                "Diagnostic case selection cannot be combined with variance mode"
            )
        selected = [case for case in cases if case.id == case_id]
        if len(selected) != 1:
            raise ValueError(
                "Diagnostic case ID must identify exactly one dataset case"
            )
        return selected, 1
    if mode == "baseline":
        return list(cases), 1
    if mode == "variance":
        return [case for case in cases if case.id in VARIANCE_IDS], 3
    raise ValueError("mode must be baseline or variance")


def evaluate(
    target: SalesAgentTarget,
    *,
    dataset_path: Path = DATASET,
    mode: Literal["baseline", "variance"] = "baseline",
    case_id: str | None = None,
    judge: RubricJudgeScorer | None = None,
) -> RunResult:
    """Run an explicitly supplied HTTP target; persist separately after enrichment."""
    all_cases = load_dataset(dataset_path)
    cases, attempts = select_cases(all_cases, mode, case_id=case_id)
    structured = StructuredAssertionsScorer(
        requires=frozenset({"structured", "metadata", "trajectory"})
    )
    scorers: list[Scorer] = [structured] if judge is None else [structured, judge]
    result = run(
        target, scorers, cases, attempts=attempts, dataset_path=str(dataset_path)
    )
    result.config_path = str(Path(__file__).resolve())
    result.config_snapshot.update(
        {
            "target_configuration": target.configuration,
            "evidence_schema_version": EVIDENCE_VERSION,
            "assertion_schema_version": SCHEMA_VERSION,
            "selection": {
                "mode": "diagnostic" if case_id is not None else mode,
                "case_ids": [c.id for c in cases],
            },
            "full_dataset_hash": hash_cases(all_cases),
            "semantic_evaluation": "not_measured"
            if judge is None
            else "injected_judge",
            # Intentionally persist evaluator references, separately from target
            # evidence. Do not copy arbitrary case.extra or process environment.
            "resolved_cases": [
                c.model_dump(mode="json", exclude={"extra"}) for c in cases
            ],
            "dataset_provenance": [
                {
                    k: v
                    for k, v in c.extra.get("provenance", {}).items()
                    if k
                    in {
                        "source_revision",
                        "products_sha256",
                        "discounts_sha256",
                        "scenario_source",
                    }
                }
                for c in cases
            ],
        }
    )
    result.config_snapshot["scorers"][0]["schema_version"] = SCHEMA_VERSION
    responses = [
        a.response for c in result.cases for a in c.attempts if a.response is not None
    ]
    models = sorted({m for response in responses for m in response.metadata["models"]})
    prompts = sorted(
        {p for response in responses for p in response.metadata["prompt_versions"]}
    )
    for index, model in enumerate(models):
        result.model_versions[f"target:{index}"] = model
    result.config_snapshot["target_observations"] = {
        "models": models,
        "prompt_versions": prompts,
        "versions_varied": len(models) > 1 or len(prompts) > 1,
    }
    return result


def persist_and_verify(result: RunResult, database: Path) -> RunResult:
    """Save once, load by ID, and exercise descriptive comparison."""
    store = SQLiteResultStore(database)
    store.save(result)
    restored = store.load(result.run_id)
    if result.model_dump(mode="json") != restored.model_dump(mode="json"):
        raise RuntimeError("Stored result did not round-trip")
    comparison = compare_runs(result, restored)
    if (
        comparison.dataset_changed
        or comparison.target_changed
        or comparison.model_versions_changed
        or comparison.evaluation_config_changed
        or comparison.gained_evidence_case_ids
        or comparison.lost_evidence_case_ids
        or comparison.aggregate_pass_rate.delta not in (None, 0)
        or comparison.error_rate.delta != 0
        or comparison.added_case_ids
        or comparison.removed_case_ids
        or comparison.regressed_case_ids
        or comparison.improved_case_ids
    ):
        raise RuntimeError("Stored result comparison changed")
    return restored


def comparison_summary(baseline: RunResult, candidate: RunResult) -> dict[str, object]:
    """Expose evaluator warnings and deployment context beside descriptive deltas."""
    comparison = compare_runs(baseline, candidate)
    return {
        "comparison": asdict(comparison),
        "evaluation_changed": comparison.dataset_changed
        or comparison.evaluation_config_changed,
        "baseline_target": baseline.config_snapshot.get("target_configuration", {}),
        "candidate_target": candidate.config_snapshot.get("target_configuration", {}),
        "baseline_observations": baseline.config_snapshot.get(
            "target_observations", {}
        ),
        "candidate_observations": candidate.config_snapshot.get(
            "target_observations", {}
        ),
    }


def main() -> None:
    if os.environ.get("SALESAGENT_LIVE_EVAL") != "1":
        raise SystemExit(
            "Live evaluation is opt-in: set SALESAGENT_LIVE_EVAL=1 only for an intentional manual run"
        )
    mode = os.environ.get("SALESAGENT_EVAL_MODE", "baseline")
    if mode not in {"baseline", "variance"}:
        raise SystemExit("SALESAGENT_EVAL_MODE must be baseline or variance")
    # All 14 cases are checked before constructing any live HTTP client.
    case_id = os.environ.get("SALESAGENT_CASE_ID")
    selected_mode: Literal["baseline", "variance"] = (
        "variance" if mode == "variance" else "baseline"
    )
    select_cases(load_dataset(), selected_mode, case_id=case_id)
    target = SalesAgentTarget(
        os.environ.get("SALESAGENT_BASE_URL", "http://127.0.0.1:8000"),
        target_revision=os.environ.get("SALESAGENT_TARGET_REVISION"),
    )
    result = evaluate(target, mode=selected_mode, case_id=case_id)
    database = Path("runs/salesagent.sqlite")
    persist_and_verify(result, database)
    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "database": str(database),
                "mode": result.config_snapshot["selection"]["mode"],
                "dataset_hash": result.dataset_hash,
                "attempts": result.config_snapshot["attempts"],
                "case_count": len(result.cases),
                "pass_rate": result.aggregate_pass_rate,
                "error_rate": result.error_rate,
                "designation": "diagnostic"
                if result.error_rate or case_id is not None
                else "baseline"
                if mode == "baseline"
                else "variance",
                "semantic_evaluation": "not_measured",
                "reload_comparison": "verified",
                "cases": [
                    {
                        "case_id": c.case_id,
                        "attempts": [
                            {
                                "index": a.index,
                                "verdict": a.verdict.value,
                                "failed_critical_assertions": [
                                    item["id"]
                                    for score in a.scores
                                    if score.name == "structured_assertions"
                                    for item in score.extra["assertions"]
                                    if item["critical"] and not item["passed"]
                                ],
                            }
                            for a in c.attempts
                        ],
                    }
                    for c in result.cases
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
