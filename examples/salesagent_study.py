"""Explicit Study v1 commands. Import/help/validation never construct clients."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from harness.core.calibration_io import export_bundle, freeze_bundle
from harness.core.fingerprints import canonical_json
from harness.core.prospective import ProspectiveJudge, strict_json
from harness.core.prospective_io import ProspectiveStore, _load, _save
from harness.core.replay import JudgeConfiguration, source_locator
from harness.core.store import SQLiteResultStore
from harness.packs import salesagent_study as pack
from harness.reporting.study import (
    analyze,
    compare_studies,
    load_analysis,
    render_study,
    save_analysis,
    summarize,
)

REPOSITORY = Path(__file__).resolve().parents[1]


def make_target(freeze: pack.StudyTargetFreeze):
    # Called only after explicit live gates, freeze validation and preflight.
    from harness.targets.salesagent import SalesAgentTarget

    r = freeze.requested
    assert r.base_url is not None and r.timeouts is not None
    return SalesAgentTarget(
        r.base_url,
        target_revision=r.deployed_target_commit_sha,
        **{f"{k}_timeout": v for k, v in r.timeouts.model_dump().items()},
    )


def make_judge(config: JudgeConfiguration) -> ProspectiveJudge:
    # Credentials are read only inside the deferred, post-receipt live factory.
    from harness.judges.openai import OpenAIJudge

    supported = JudgeConfiguration.model_validate(
        OpenAIJudge.configuration_for(
            model=config.model,
            max_output_tokens=config.max_output_tokens,
            **{f"{k}_timeout": v for k, v in config.timeouts.model_dump().items()},
        )
    )
    if config != supported:
        raise ValueError(
            "Recipe supports only the exact explicit OpenAI adapter configuration; injected generic judges remain available through Python"
        )
    judge = OpenAIJudge(
        api_key=os.environ.get("HARNESS_JUDGE_API_KEY", ""),
        model=config.model,
        max_output_tokens=config.max_output_tokens,
        **{f"{k}_timeout": v for k, v in config.timeouts.model_dump().items()},
    )
    scorer, _ = pack.semantic_profile(config, judge)
    return ProspectiveJudge(
        scorer,
        lambda: JudgeConfiguration.model_validate(judge.configuration),
        judge.close,
    )


def _read(path: Path, model):
    return model.model_validate_json(canonical_json(strict_json(path.read_bytes())))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    for command in (
        "validate",
        "preview",
        "freeze",
        "capture",
        "prepare",
        "prepare-diagnostic",
        "export",
        "judge",
        "analyze",
    ):
        cmd = commands.add_parser(command)
        cmd.add_argument("--descriptor", type=Path, required=True)
        cmd.add_argument("--suites", type=Path, nargs=6, required=True)
        if command not in ("validate", "preview", "freeze"):
            cmd.add_argument("--contract", type=Path, required=True)
        if command in ("prepare", "prepare-diagnostic", "export", "judge", "analyze"):
            cmd.add_argument("--source-db", type=Path, required=True)
            cmd.add_argument("--run-id", required=True)
        if command in (
            "freeze",
            "capture",
            "prepare",
            "prepare-diagnostic",
            "export",
            "analyze",
        ):
            cmd.add_argument("--output", type=Path, required=True)
        if command in ("export", "judge", "analyze"):
            cmd.add_argument("--preparation", type=Path, required=command != "analyze")
        if command in ("judge", "analyze"):
            cmd.add_argument("--frozen", type=Path)
        if command == "freeze":
            cmd.add_argument("--target-freeze", type=Path, required=True)
            cmd.add_argument("--judge-config", type=Path, required=True)
            cmd.add_argument("--author-review", required=True)
            cmd.add_argument("--reviewed-at", required=True)
            cmd.add_argument("--diagnostic-budget", type=int, required=True)
        if command == "capture":
            cmd.add_argument("--suite", required=True)
            cmd.add_argument("--live", action="store_true")
            cmd.add_argument("--allow-target-calls", action="store_true")
            cmd.add_argument("--target-budget", type=int, required=True)
        if command in ("prepare", "prepare-diagnostic"):
            cmd.add_argument("--plan-id", required=True)
            if command == "prepare":
                cmd.add_argument("--review-set-id", required=True)
            else:
                cmd.add_argument("--case-id", required=True)
                cmd.add_argument("--attempt-index", type=int, required=True)
                cmd.add_argument("--attempts", type=int, required=True)
        if command == "export":
            cmd.add_argument("--annotator", required=True)
        if command == "judge":
            cmd.add_argument("--store", type=Path, required=True)
            cmd.add_argument("--request-id", required=True)
            cmd.add_argument("--live", action="store_true")
            cmd.add_argument("--allow-judge-calls", action="store_true")
            cmd.add_argument("--judge-budget", type=int, required=True)
        if command == "analyze":
            cmd.add_argument("--results", type=Path, nargs="*", default=[])
    check = commands.add_parser("inspect-freeze")
    check.add_argument("path", type=Path)
    human = commands.add_parser("freeze-human")
    human.add_argument("--export", type=Path, required=True)
    human.add_argument("--draft", type=Path, required=True)
    human.add_argument("--output", type=Path, required=True)
    render = commands.add_parser("render")
    render.add_argument("analysis", type=Path)
    compare = commands.add_parser("compare")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("candidate", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "inspect-freeze":
            freeze = _read(args.path, pack.StudyTargetFreeze)
            print(
                canonical_json(
                    {
                        "missing_facts": freeze.missing_facts,
                        "fingerprint": freeze.digest,
                    }
                )
            )
            return 0
        if args.command == "freeze-human":
            freeze_bundle(args.export, args.draft, args.output)
            return 0
        if args.command == "render":
            print(render_study(load_analysis(args.analysis)))
            return 0
        if args.command == "compare":
            print(
                canonical_json(
                    compare_studies(
                        load_analysis(args.baseline), load_analysis(args.candidate)
                    )
                )
            )
            return 0
        definition = pack.load_study(args.descriptor, args.suites)
        if args.command in ("validate", "preview"):
            print(definition.validation.model_dump_json(indent=2))
            return 0
        if args.command == "freeze":
            contract = pack.freeze_execution(
                definition,
                _read(args.target_freeze, pack.StudyTargetFreeze),
                _read(args.judge_config, JudgeConfiguration),
                diagnostic_judge_calls=args.diagnostic_budget,
                author_review=args.author_review,
                reviewed_at=datetime.fromisoformat(args.reviewed_at),
            )
            _save(args.output, contract)
            return 0
        contract = pack.verify_contract(
            definition, _load(args.contract, pack.StudyExecutionContract)
        )
        if args.command == "capture":
            if not args.live or not args.allow_target_calls:
                raise ValueError(
                    "Live capture requires --live and --allow-target-calls"
                )
            bindings = [s for s in contract.validation.suites if s.id == args.suite]
            if len(bindings) != 1 or args.target_budget != bindings[0].target_calls:
                raise ValueError(
                    "Explicit target budget must equal the approved suite attempt count"
                )
            args.output.mkdir()
            store = SQLiteResultStore(args.output / "source.sqlite")
            result = pack.capture(
                definition, contract, args.suite, lambda: make_target(contract.target)
            )
            # A write failure retains a concrete recovery document, never recaptures.
            with (args.output / "capture.json").open("x") as file:
                file.write(result.model_dump_json())
            store.save(result)
            print(
                canonical_json(
                    {
                        "run_id": result.run_id,
                        "stage": "deterministic_capture",
                        "final_study_outcome": False,
                    }
                )
            )
            return 0
        source_store = SQLiteResultStore(args.source_db, read_only=True)
        source, document_hash = source_store.load_with_fingerprint(args.run_id)

        def loader(provenance):
            if provenance.run_id != source.run_id:
                raise ValueError("Unexpected source run")
            current, hash_value = source_store.load_with_fingerprint(provenance.run_id)
            return current, definition.dataset.cases, hash_value

        if args.command in ("prepare", "prepare-diagnostic"):
            options = {
                "database_locator": source_locator(args.source_db, REPOSITORY),
                "document_hash": document_hash,
                "plan_id": args.plan_id,
            }
            if args.command == "prepare":
                preparation = pack.prepare_primary(
                    definition,
                    contract,
                    source,
                    review_set_id=args.review_set_id,
                    **options,
                )
            else:
                preparation = pack.prepare_variance_diagnostic(
                    definition,
                    contract,
                    source,
                    case_id=args.case_id,
                    attempt_index=args.attempt_index,
                    attempts=args.attempts,
                    **options,
                )
            args.output.mkdir()
            observations = ProspectiveStore(args.output / "observations")
            assert preparation.bundle is not None
            observations.save_prepared(preparation.bundle)
            _save(args.output / "preparation", preparation)
            return 0
        preparation = (
            _load(args.preparation, pack.StudyPreparation) if args.preparation else None
        )
        if args.command == "export":
            assert preparation is not None
            manifest = pack.human_manifest(definition, contract, preparation, loader)
            export_bundle(manifest, args.output, annotator_id=args.annotator)
            return 0
        if args.command == "judge":
            if not args.live or not args.allow_judge_calls:
                raise ValueError("Live judging requires --live and --allow-judge-calls")
            assert preparation is not None and preparation.bundle is not None
            selection = preparation.bundle.plan.selection(args.request_id)
            if args.judge_budget != selection.attempts:
                raise ValueError(
                    "Explicit judge budget must equal the reserved request count"
                )
            store = ProspectiveStore(args.store)
            result = pack.judge_request(
                definition,
                contract,
                preparation,
                args.request_id,
                source_loader=loader,
                scorer_factory=lambda: make_judge(contract.evaluator.judge),
                store=store,
                frozen_bundle=args.frozen,
            )
            # Save-only recovery after failure; this command never retries judging.
            with (args.store / f"recovery-{result.observation_id}.json").open(
                "x"
            ) as file:
                file.write(result.model_dump_json())
            store.save_result(result)
            return 0
        if args.command == "analyze":
            result = analyze(
                definition,
                contract,
                source,
                document_hash=document_hash,
                preparation=preparation,
                results=[ProspectiveStore.load_result(p) for p in args.results],
                source_loader=loader,
                frozen_bundle=args.frozen,
            )
            save_analysis(result, args.output)
            print(json.dumps(summarize(result), indent=2))
            return 0
        raise ValueError("Unknown study command")
    except (ValueError, OSError, KeyError) as exc:
        # Do not print dataset/evidence bodies from nested validation errors.
        print(
            f"Study command failed ({type(exc).__name__}); no automatic retry. Check explicit files, contracts and receipts."
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
