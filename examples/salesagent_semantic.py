"""Explicit semantic evaluation recipe. Importing it makes no network calls."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from salesagent_baseline import comparison_summary as target_comparison_summary
from salesagent_baseline import persist_and_verify

from harness.core.dataset import hash_cases
from harness.core.models import RunResult, TestCase
from harness.core.runner import run
from harness.judges.base import JudgeReply
from harness.judges.openai import OpenAIJudge
from harness.packs import salesagent_semantic as pack
from harness.scorers.structured_assertions import (
    SCHEMA_VERSION,
    StructuredAssertionsScorer,
)
from harness.targets.salesagent import EVIDENCE_VERSION, SalesAgentTarget


def select_cases(
    cases: list[TestCase],
    *,
    case_id: str | None = None,
    case_ids: Sequence[str] | None = None,
    attempts: int = 1,
) -> tuple[list[TestCase], str]:
    if type(attempts) is not int or attempts < 1:
        raise ValueError("Semantic attempts must be a positive integer")
    if case_id is not None and (case_ids is not None or attempts != 1):
        raise ValueError(
            "Single diagnostic selection requires one attempt and no subset"
        )
    requested = (
        [case_id]
        if case_id is not None
        else list(case_ids)
        if case_ids is not None
        else None
    )
    if requested is not None:
        if (
            not requested
            or any(not isinstance(v, str) or not v.strip() for v in requested)
            or len(set(requested)) != len(requested)
        ):
            raise ValueError("Selection requires nonempty unique case IDs")
        if not set(requested) <= {c.id for c in cases}:
            raise ValueError("Unknown semantic case selection")
        return [
            c for c in cases if c.id in requested
        ], "diagnostic" if case_id is not None else "subset"
    return list(cases), "full" if attempts == 1 else "repeated_full"


def _configuration(value: dict[str, Any], model: str) -> dict[str, Any]:
    allowed = {
        "provider",
        "model",
        "adapter_version",
        "endpoint",
        "instruction_version",
        "max_output_tokens",
        "timeouts",
        "retries",
        "store",
        "stream",
        "tools",
        "response_schema",
    }
    if (
        set(value) - allowed
        or value.get("model") != model
        or not isinstance(value.get("provider"), str)
        or not value["provider"].strip()
    ):
        raise ValueError(
            "Explicit safe judge configuration with matching model is required"
        )
    # Snapshot explicit configuration, never callable attributes or environment.
    return json.loads(json.dumps(value, allow_nan=False))  # type: ignore[no-any-return]


def evaluate(
    target: SalesAgentTarget,
    judge: Callable[[str], str | JudgeReply],
    *,
    judge_model: str,
    judge_configuration: dict[str, Any],
    dataset_path: Path = pack.DATASET,
    case_id: str | None = None,
    case_ids: Sequence[str] | None = None,
    attempts: int = 1,
) -> RunResult:
    all_cases = pack.load_dataset(dataset_path)
    cases, mode = select_cases(
        all_cases, case_id=case_id, case_ids=case_ids, attempts=attempts
    )
    config = _configuration(judge_configuration, judge_model)
    scorer = pack.make_scorer(judge, judge_model)
    result = run(
        target,
        [
            StructuredAssertionsScorer(
                requires=frozenset({"structured", "metadata", "trajectory"})
            ),
            scorer,
        ],
        cases,
        attempts=attempts,
        dataset_path=str(dataset_path),
    )
    result.pack_name = pack.PROFILE
    result.config_path = str(Path(__file__).resolve())
    provenance_keys = {
        "source_revision",
        "products_sha256",
        "discounts_sha256",
        "scenario_source",
        "semantic_dataset_version",
        "derived_from_dataset",
        "derived_from_dataset_hash",
        "harness_revision",
    }
    result.config_snapshot.update(
        {
            "target_configuration": target.configuration,
            "evidence_schema_version": EVIDENCE_VERSION,
            "assertion_schema_version": SCHEMA_VERSION,
            "selection": {"mode": mode, "case_ids": [c.id for c in cases]},
            "full_dataset_hash": hash_cases(all_cases),
            "semantic_evaluation": {**pack.configuration(), "judge": config},
            "resolved_cases": [
                c.model_dump(mode="json", exclude={"extra"}) for c in cases
            ],
            "dataset_provenance": [
                {
                    k: v
                    for k, v in c.extra.get("provenance", {}).items()
                    if k in provenance_keys
                }
                for c in cases
            ],
        }
    )
    responses = [
        a.response for c in result.cases for a in c.attempts if a.response is not None
    ]
    models = sorted({m for r in responses for m in r.metadata["models"]})
    prompts = sorted({p for r in responses for p in r.metadata["prompt_versions"]})
    result.config_snapshot["target_observations"] = {
        "models": models,
        "prompt_versions": prompts,
        "versions_varied": len(models) > 1 or len(prompts) > 1,
    }
    for index, model in enumerate(models):
        result.model_versions[f"target:{index}"] = model
    observed = sorted(
        {
            s.extra["judge"]["observed_model"]
            for c in result.cases
            for a in c.attempts
            for s in a.scores
            if s.name == pack.SCORER_NAME
            and s.extra.get("judge", {}).get("observed_model")
        }
    )
    for index, model in enumerate(observed):
        result.model_versions[f"judge_observed:{index}"] = model
    return result


def comparison_summary(baseline: RunResult, candidate: RunResult) -> dict[str, Any]:
    summary = target_comparison_summary(baseline, candidate)
    comparison = summary["comparison"]
    assert isinstance(comparison, dict)

    def judges(result: RunResult) -> dict[str, str]:
        return {
            k: v
            for k, v in result.model_versions.items()
            if k.startswith(("judge:", "judge_observed:"))
        }

    compatible = (
        baseline.pack_name == candidate.pack_name == pack.PROFILE
        and isinstance(baseline.config_snapshot.get("semantic_evaluation"), dict)
        and isinstance(candidate.config_snapshot.get("semantic_evaluation"), dict)
        and not comparison["dataset_changed"]
        and not comparison["evaluation_config_changed"]
        and not comparison["target_changed"]
        and judges(baseline) == judges(candidate)
    )
    return {
        "semantic_compatible": compatible,
        "interpretation": "compatible_semantic_observations"
        if compatible
        else "incompatible_or_confounded",
        **summary,
    }


def result_summary(result: RunResult, database: Path) -> dict[str, Any]:
    scores = [
        s
        for c in result.cases
        for a in c.attempts
        for s in a.scores
        if s.name == pack.SCORER_NAME
    ]
    return {
        "run_id": result.run_id,
        "database": str(database),
        "pack": result.pack_name,
        "dataset_hash": result.dataset_hash,
        "full_dataset_hash": result.config_snapshot["full_dataset_hash"],
        "selection": result.config_snapshot["selection"],
        "attempts": result.config_snapshot["attempts"],
        "case_count": len(result.cases),
        "pass_rate": result.aggregate_pass_rate,
        "error_rate": result.error_rate,
        "semantic_score_count": len(scores),
        "designation": "diagnostic"
        if result.error_rate or result.config_snapshot["selection"]["mode"] != "full"
        else "semantic_observation",
        "reload_comparison": "verified",
        "calibration": "provisional_uncalibrated",
        "cost_note": "Target and judge costs are separate; absent costs are unknown.",
        "cases": [
            {
                "case_id": c.case_id,
                "attempts": [
                    {
                        "index": a.index,
                        "verdict": a.verdict.value,
                        "error": a.error,
                        "semantic_scores": [
                            s.model_dump(mode="json")
                            for s in a.scores
                            if s.name == pack.SCORER_NAME
                        ],
                        "failed_critical_assertions": [
                            item["id"]
                            for s in a.scores
                            if s.name == "structured_assertions"
                            for item in s.extra["assertions"]
                            if item["critical"] and not item["passed"]
                        ],
                    }
                    for a in c.attempts
                ],
            }
            for c in result.cases
        ],
    }


def main() -> None:
    if os.environ.get("SALESAGENT_SEMANTIC_LIVE_EVAL") != "1":
        raise SystemExit(
            "Semantic live evaluation is opt-in: set SALESAGENT_SEMANTIC_LIVE_EVAL=1"
        )
    try:
        provider = os.environ.get("HARNESS_JUDGE_PROVIDER")
        if provider != "openai":
            raise ValueError("Explicit HARNESS_JUDGE_PROVIDER=openai is required")
        key = os.environ.get("HARNESS_JUDGE_API_KEY", "")
        model = os.environ.get("HARNESS_JUDGE_MODEL", "")
        OpenAIJudge.validate_configuration(api_key=key, model=model)
        attempt_text = os.environ.get("SALESAGENT_SEMANTIC_ATTEMPTS", "1")
        if not attempt_text.isascii() or not attempt_text.isdecimal():
            raise ValueError("Semantic attempts must be a positive integer")
        attempts = int(attempt_text)
        case_id = os.environ.get("SALESAGENT_CASE_ID")
        subset = os.environ.get("SALESAGENT_SEMANTIC_CASE_IDS")
        case_ids = (
            [v.strip() for v in subset.split(",")] if subset is not None else None
        )
        select_cases(
            pack.load_dataset(), case_id=case_id, case_ids=case_ids, attempts=attempts
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    judge = OpenAIJudge(api_key=key, model=model)
    target: SalesAgentTarget | None = None
    try:
        target = SalesAgentTarget(
            os.environ.get("SALESAGENT_BASE_URL", "http://127.0.0.1:8000"),
            target_revision=os.environ.get("SALESAGENT_TARGET_REVISION"),
        )
        result = evaluate(
            target,
            judge,
            judge_model=model,
            judge_configuration=judge.configuration,
            case_id=case_id,
            case_ids=case_ids,
            attempts=attempts,
        )
    finally:
        judge.close()
        if target is not None:
            target.close()
    database = Path("runs/salesagent-semantic.sqlite")
    persist_and_verify(result, database)
    print(json.dumps(result_summary(result, database), indent=2))


if __name__ == "__main__":
    main()
