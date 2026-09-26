"""Explicit judge-only recipe. Import and dry-run never construct a client."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from harness.core.fingerprints import canonical_json
from harness.core.models import RunResult
from harness.core.replay import (
    EvaluatorConfiguration,
    JudgeConfiguration,
    PreparedReplay,
    ReplayResult,
    ReplayValidationError,
    prepare_replay,
    replay,
    source_locator,
)
from harness.core.store import SQLiteResultStore
from harness.judges.openai import OpenAIJudge
from harness.packs import salesagent_semantic as pack

REPOSITORY = Path(__file__).resolve().parents[1]


def validate_destination(source: Path, destination: Path) -> None:
    if source.resolve() == destination.resolve() or (
        source.exists() and destination.exists() and source.samefile(destination)
    ):
        raise ReplayValidationError(
            "Replay destination must differ from source database"
        )


def source_configuration(source: RunResult) -> EvaluatorConfiguration | None:
    """Translate recorded pack settings; never fill unknown versions from today."""
    semantic = source.config_snapshot.get("semantic_evaluation")
    scorers = [
        s
        for s in source.config_snapshot.get("scorers", [])
        if s.get("name") == pack.SCORER_NAME
    ]
    if not isinstance(semantic, dict) or len(scorers) != 1:
        return None
    required = {
        "profile",
        "expectations_version",
        "rubric_version",
        "projection_version",
        "prompt_version",
        "judgment_version",
        "payload_limit_bytes",
        "scope",
        "calibration",
        "pass_threshold",
        "judge",
    }
    if set(semantic) != required:
        raise ReplayValidationError(
            "Stored semantic configuration is incomplete or unsupported"
        )
    saved = scorers[0]
    config = {
        key: saved[key]
        for key in (
            "name",
            "kind",
            "requires",
            "judge_model",
            "pass_threshold",
            "rubric",
        )
    }
    config.update(
        {
            key: semantic[key]
            for key in (
                "rubric_version",
                "projection_version",
                "prompt_version",
                "judgment_version",
            )
        }
    )
    config["evidence_settings"] = {
        key: semantic[key]
        for key in (
            "expectations_version",
            "payload_limit_bytes",
            "scope",
        )
    }
    if saved["pass_threshold"] != semantic["pass_threshold"]:
        raise ReplayValidationError("Stored threshold settings disagree")
    return EvaluatorConfiguration(
        scorer_json=canonical_json(config),
        judge=JudgeConfiguration.model_validate(semantic["judge"]),
    )


def _no_judge(_: str) -> str:
    raise AssertionError("Preparation must never invoke a judge")


def prepare_from_store(
    *,
    source_db: Path,
    source_run: str,
    case_id: str,
    source_attempt: int,
    dataset: Path,
    attempts: int,
    output_db: Path,
    judge_model: str | None = None,
    allow_reconfigured: bool = False,
) -> PreparedReplay:
    validate_destination(source_db, output_db)
    store = SQLiteResultStore(source_db, read_only=True)
    source, document_hash = store.load_with_fingerprint(source_run)
    recorded = source_configuration(source)
    model = judge_model or (recorded.judge.model if recorded else None)
    if not model:
        raise ReplayValidationError("An explicit judge model is required")
    # Preserve recorded adjustable limits; fixed adapter instructions/schema are
    # today's actual versions and compatibility checking will detect drift.
    settings: dict[str, Any] = {"model": model}
    if recorded:
        settings.update(max_output_tokens=recorded.judge.max_output_tokens)
        settings.update(
            {f"{k}_timeout": v for k, v in recorded.judge.timeouts.model_dump().items()}
        )
    judge_config = JudgeConfiguration.model_validate(
        OpenAIJudge.configuration_for(**settings)
    )
    return prepare_replay(
        source,
        pack.load_dataset(dataset),
        pack.make_scorer(_no_judge, model),
        judge_configuration=judge_config,
        database_locator=source_locator(source_db, REPOSITORY),
        case_id=case_id,
        source_attempt=source_attempt,
        attempts=attempts,
        source_evaluator=recorded,
        source_document_hash=document_hash,
        allow_reconfigured=allow_reconfigured,
    )


def persist_and_verify(
    result: ReplayResult, source: Path, destination: Path
) -> ReplayResult:
    validate_destination(source, destination)
    store = SQLiteResultStore(destination)
    store.save_replay(result)
    restored = store.load_replay(result.replay_id)
    if (
        restored.model_dump(mode="json") != result.model_dump(mode="json")
        or restored.summary != result.summary
    ):
        raise RuntimeError("Replay persistence verification failed")
    return restored


def preparation_summary(prepared: PreparedReplay) -> dict[str, Any]:
    return {
        "source": prepared.source.model_dump(mode="json"),
        "compatibility": prepared.compatibility,
        "differences": prepared.differences,
        "requested_attempt_count": prepared.requested_attempt_count,
        "prompt_hash": prepared.prepared.prompt_hash,
        "evidence_hash": prepared.prepared.evidence_hash,
        "input_hash": prepared.input_hash,
        "judge_configuration": prepared.evaluator.judge.model_dump(mode="json"),
        "threshold": json.loads(prepared.evaluator.scorer_json)["pass_threshold"],
        "target_calls": 0,
        "data_handling": "Prepared snapshots contain evaluation content; treat them as evaluation data.",
    }


def result_summary(result: ReplayResult) -> dict[str, Any]:
    return {
        **preparation_summary(result.input),
        "replay_id": result.replay_id,
        "summary": result.summary,
        "reload_verification": "verified",
        "attempts": [a.model_dump(mode="json") for a in result.attempts],
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--source-run", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--source-attempt", type=int, required=True)
    parser.add_argument("--dataset", type=Path, default=pack.DATASET)
    parser.add_argument("--attempts", type=int, required=True)
    parser.add_argument(
        "--output-db", type=Path, default=Path("runs/judge-replay.sqlite")
    )
    parser.add_argument("--allow-reconfigured", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    options = parser.parse_args(argv)
    if options.live and os.environ.get("HARNESS_JUDGE_REPLAY_LIVE") != "1":
        raise SystemExit(
            "Judge replay is opt-in: set HARNESS_JUDGE_REPLAY_LIVE=1 and --live"
        )
    try:
        prepared = prepare_from_store(
            source_db=options.source_db,
            source_run=options.source_run,
            case_id=options.case_id,
            source_attempt=options.source_attempt,
            dataset=options.dataset,
            attempts=options.attempts,
            output_db=options.output_db,
            judge_model=os.environ.get("HARNESS_JUDGE_MODEL"),
            allow_reconfigured=options.allow_reconfigured,
        )
    except Exception:  # noqa: BLE001 - never echo source paths or validation input
        # Dataset validation APIs retain file/line errors for local callers;
        # portable recipe diagnostics never echo paths or validation input data.
        raise SystemExit(
            "Replay preflight failed: check source, dataset, selectors and evaluator compatibility"
        ) from None
    if not options.live:
        print(
            json.dumps(
                {"mode": "dry_run", "judge_calls": 0, **preparation_summary(prepared)},
                indent=2,
            )
        )
        return
    if (
        os.environ.get("HARNESS_JUDGE_PROVIDER") != "openai"
        or os.environ.get("HARNESS_JUDGE_MODEL") != prepared.evaluator.judge.model
    ):
        raise SystemExit(
            "Explicit matching HARNESS_JUDGE_PROVIDER and HARNESS_JUDGE_MODEL are required"
        )
    config = prepared.evaluator.judge
    try:
        judge = OpenAIJudge(
            api_key=os.environ.get("HARNESS_JUDGE_API_KEY", ""),
            model=config.model,
            max_output_tokens=config.max_output_tokens,
            **{f"{k}_timeout": v for k, v in config.timeouts.model_dump().items()},
        )
    except Exception:  # noqa: BLE001 - never expose credentials in constructor errors
        raise SystemExit(
            "Judge configuration failed; check the dedicated judge credential"
        ) from None
    try:
        result = replay(
            prepared,
            pack.make_scorer(judge, config.model),
            judge_configuration=lambda: JudgeConfiguration.model_validate(
                judge.configuration
            ),
        )
    finally:
        judge.close()
    try:
        restored = persist_and_verify(result, options.source_db, options.output_db)
    except Exception:  # noqa: BLE001 - save failures must not expose local paths/content
        raise SystemExit(
            "Replay persistence failed; result was not verified as saved"
        ) from None
    print(json.dumps(result_summary(restored), indent=2))


if __name__ == "__main__":
    main()
