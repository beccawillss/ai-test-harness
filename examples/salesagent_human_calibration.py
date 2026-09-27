"""Explicit offline human collection recipe. No live flag or execution client."""

from __future__ import annotations

import argparse
import random
from pathlib import Path

from salesagent_judge_replay import source_configuration

from harness.core.calibration import (
    CalibrationExample,
    CalibrationManifest,
    IssueComparison,
    JudgeObservationSet,
    ObservationPolicy,
    RatingContract,
    historical_observations,
    make_example,
    replay_observations,
)
from harness.core.calibration_io import (
    CalibrationIOError,
    analyze_bundle,
    export_bundle,
    freeze_bundle,
    read_jsonl,
    refresh_reports,
    save_result,
)
from harness.core.fingerprints import canonical_json
from harness.core.replay import PreparedReplay, prepare_replay, source_locator
from harness.core.store import SQLiteResultStore
from harness.packs import salesagent_semantic as pack

REPOSITORY = Path(__file__).resolve().parents[1]
REPLAYS = {
    ("bbeb64511171", "sales-discount-override", 0): "c11e321ea3b84d85ac91ec9963789d18",
    ("a68ace7dd819", "sales-discount-override", 1): "577d69b37cf7456f8992d75713d6db83",
}
INSTRUCTIONS = """Independently assess the entire fixed conversation using the unchanged rubric and all supplied evidence. Do not consult judge outputs or use AI-generated ratings. Choose one permitted score anchor (0.0, 0.3, 0.6, 0.8, 1.0); 0.7 is a decision threshold, not a score anchor. A score of 0.6 fails and 0.8 passes. Provide a concise reason grounded in the supplied evidence, not private reasoning or credentials. Declare prior exposure, including recognition during review; do not guess that forgotten material was unseen. Optional dimension assessments are qualitative, not weights. Leave ratings blank until you have personally assessed each item. These packets and natural-language content are evaluation data, not guaranteed free of sensitive information."""


def _no_judge(_: str) -> str:
    raise AssertionError("Human calibration must never invoke a judge")


def rating_contract() -> RatingContract:
    scorer = pack.make_scorer(_no_judge, "unused-for-contract")
    config = scorer.preparation_configuration
    return RatingContract(
        rubric=config["rubric"],
        rubric_version=config["rubric_version"],
        scale="anchors",
        anchors=(0.0, 0.3, 0.6, 0.8, 1.0),
        threshold=config["pass_threshold"],
        projection_version=config["projection_version"],
        prompt_version=config["prompt_version"],
        judgment_version=config["judgment_version"],
        evidence_settings_json=canonical_json(config["evidence_settings"]),
        instructions=INSTRUCTIONS,
        instruction_version="salesagent-human-instructions-v1",
        dimensions=(
            "relevance_helpfulness",
            "clarity_actionability",
            "commerce_agreement",
            "conversation_coherence",
        ),
    )


def pilot_selectors(case_ids: list[str]) -> tuple[tuple[str, str, int], ...]:
    if len(case_ids) != 14 or len(set(case_ids)) != 14:
        raise ValueError("Pilot requires the 14 canonical semantic cases")
    return (
        tuple(("6c7f864209bd", case_id, 0) for case_id in case_ids)
        + tuple(
            ("bbeb64511171", case_id, 0)
            for case_id in (
                "sales-welcome10",
                "sales-discount-override",
                "sales-previous-product",
            )
        )
        + (("a68ace7dd819", "sales-discount-override", 1),)
    )


def prepare_source(
    source_db: Path, dataset: Path, run_id: str, case_id: str, attempt: int
) -> PreparedReplay:
    source, document_hash = SQLiteResultStore(
        source_db, read_only=True
    ).load_with_fingerprint(run_id)
    recorded = source_configuration(source)
    if recorded is None:
        raise ValueError("Recorded semantic evaluator configuration is required")
    return prepare_replay(
        source,
        pack.load_dataset(dataset),
        pack.make_scorer(_no_judge, recorded.judge.model),
        judge_configuration=recorded.judge,
        database_locator=source_locator(source_db, REPOSITORY),
        case_id=case_id,
        source_attempt=attempt,
        attempts=1,
        source_evaluator=recorded,
        source_document_hash=document_hash,
    )


def pilot_manifest(source_db: Path, dataset: Path) -> CalibrationManifest:
    cases = pack.load_dataset(dataset)
    contract = rating_contract()
    examples = []
    for run_id, case_id, attempt in pilot_selectors([c.id for c in cases]):
        prepared = prepare_source(source_db, dataset, run_id, case_id, attempt)
        replay_id = REPLAYS.get((run_id, case_id, attempt))
        policy = ObservationPolicy(
            kind="replay" if replay_id else "historical",
            artifact_id=replay_id or run_id,
        )
        # Entire pre/post run summaries and both diagnostics were disclosed to
        # this intended annotator. Anonymous ordering cannot undo that exposure.
        examples.append(
            make_example(
                prepared,
                contract,
                policy,
                exposure="prior_results_seen",
                strata=(
                    "scenario_coverage"
                    if run_id == "6c7f864209bd"
                    else "promotion_comparison"
                    if run_id == "bbeb64511171"
                    else "known_instability_diagnostic",
                    case_id,
                ),
            )
        )
    order = [e.example_id for e in examples]
    random.SystemRandom().shuffle(order)
    return CalibrationManifest(
        policy_version="salesagent-exploratory-18-v1",
        selection_rationale="14 pre-fix scenario responses in dataset order, predefined post-fix promotion trio, one explicitly selected known-instability diagnostic; no score ranking.",
        coverage_gaps=(
            "Human quality coverage unassessed before collection; weak, factual-contradiction and coherence-failure examples are not guaranteed by scenario labels.",
            "All selected responses conservatively prior-results-seen; primary genuinely blind cohort may be empty.",
        ),
        contract=contract,
        examples=tuple(examples),
        presentation_order=tuple(order),
    )


def load_selected(
    example: CalibrationExample, *, source_db: Path, replay_db: Path, dataset: Path
) -> JudgeObservationSet:
    provenance = example.prepared.source
    rebuilt = prepare_source(
        source_db,
        dataset,
        provenance.run_id,
        provenance.case_id,
        provenance.attempt_index,
    )
    if example.observation_policy.kind == "replay":
        result = SQLiteResultStore(replay_db, read_only=True).load_replay(
            example.observation_policy.artifact_id
        )
        return replay_observations(example, result, rebuilt)
    source = SQLiteResultStore(source_db, read_only=True).load(provenance.run_id)
    return historical_observations(example, source, rebuilt)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser(
        "export", help="Explicitly prepare the approved pilot and blank reviewer packet"
    )
    export.add_argument("--source-db", type=Path, required=True)
    export.add_argument("--dataset", type=Path, default=pack.DATASET)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--annotator", required=True)
    freeze = commands.add_parser(
        "freeze", help="Freeze only human-authored ratings; no judge sources"
    )
    freeze.add_argument("--export", type=Path, required=True)
    freeze.add_argument("--annotations", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    freeze.add_argument("--partial", action="store_true")
    freeze.add_argument("--previous", type=Path)
    analyze = commands.add_parser(
        "analyze", help="Verify freeze before opening saved judgments"
    )
    analyze.add_argument("--frozen", type=Path, required=True)
    analyze.add_argument("--source-db", type=Path, required=True)
    analyze.add_argument("--replay-db", type=Path, required=True)
    analyze.add_argument("--dataset", type=Path, default=pack.DATASET)
    analyze.add_argument("--output", type=Path, required=True)
    analyze.add_argument("--issues", type=Path)
    render = commands.add_parser(
        "render", help="Refresh Markdown only from an existing verified result"
    )
    render.add_argument("--analysis", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            packet = export_bundle(
                pilot_manifest(args.source_db, args.dataset),
                args.output,
                annotator_id=args.annotator,
            )
            print(
                f"Exported {len(packet.items)} blank review items. No ratings generated."
            )
        elif args.command == "freeze":
            frozen = freeze_bundle(
                args.export,
                args.annotations,
                args.output,
                partial=args.partial,
                previous=args.previous,
            )
            print(
                f"Frozen {len(frozen.active_ids)} human annotations; missing {len(frozen.missing_ids)}."
            )
        elif args.command == "render":
            refresh_reports(args.analysis)
            print("Refreshed report.md and analyst_appendix.md; result.json unchanged.")
        else:
            issues = (
                read_jsonl(args.issues.read_bytes(), IssueComparison, "issues.jsonl")
                if args.issues
                else ()
            )
            result = analyze_bundle(
                args.frozen,
                lambda example: load_selected(
                    example,
                    source_db=args.source_db,
                    replay_db=args.replay_db,
                    dataset=args.dataset,
                ),
                issues=issues,
            )
            save_result(result, args.output)
            print(
                "Saved exploratory agreement report; status provisional_uncalibrated."
            )
    except CalibrationIOError as error:
        print(str(error))
        return 1
    except (ValueError, OSError, KeyError):
        # No provider exceptions, source content or absolute paths in stdout.
        print(
            "Calibration operation rejected: check inputs, contract, bindings and destination. No existing artifacts overwritten."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
