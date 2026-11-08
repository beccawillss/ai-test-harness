"""Minimal synchronous evaluation runner."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from copy import deepcopy
from datetime import UTC, datetime
from time import perf_counter

from harness.core.case_fingerprints import (
    CASE_SCHEME_V1,
    CASE_SCHEME_V2,
    resolved_case_payload,
    validate_case_scheme,
    validate_json_data,
)
from harness.core.dataset import hash_cases
from harness.core.execution_control import ExecutionControl, ExecutionControlError
from harness.core.models import (
    AttemptResult,
    CaseResult,
    RunResult,
    Score,
    TargetResponse,
    TestCase,
    Verdict,
)
from harness.core.snapshots import definition_snapshot, metadata_keys
from harness.scorers.base import Scorer
from harness.scorers.output_contracts import ScoreOutputContract
from harness.targets.base import CloseableTarget, Target, check_pack_compatibility


def _duplicates(values: Sequence[str]) -> list[str]:
    return sorted(value for value, count in Counter(values).items() if count > 1)


def _validate_run(
    target: Target,
    scorers: Sequence[Scorer],
    cases: Sequence[TestCase],
    attempts: int,
) -> None:
    """Reject invalid runs before invoking a potentially expensive target."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1.")
    if not cases:
        raise ValueError("At least one test case is required.")
    if not scorers:
        raise ValueError("At least one scorer is required.")

    if duplicate_ids := _duplicates([case.id for case in cases]):
        raise ValueError(f"Duplicate test case ids: {', '.join(duplicate_ids)}.")
    if duplicate_names := _duplicates([scorer.name for scorer in scorers]):
        raise ValueError(f"Duplicate scorer names: {', '.join(duplicate_names)}.")

    required_capabilities = frozenset(
        capability for scorer in scorers for capability in scorer.requires
    )
    if missing := check_pack_compatibility(target, required_capabilities):
        raise ValueError(
            f"Target '{target.name}' is missing required capabilities: "
            f"{', '.join(missing)}."
        )


def _target_error(target: Target, exc: Exception) -> str:
    return f"target '{target.name}': {type(exc).__name__}: {exc}"


def _scorer_error(scorer: Scorer, exc: Exception) -> str:
    return f"scorer '{scorer.name}': {type(exc).__name__}: {exc}"


def _verdict_for(scores: Sequence[Score], errors: Sequence[str]) -> Verdict:
    if errors:
        return Verdict.ERROR
    gated_scores = [score for score in scores if score.passed is not None]
    if not gated_scores:
        return Verdict.SKIP
    return Verdict.PASS if all(score.passed for score in gated_scores) else Verdict.FAIL


def _execute_attempt(
    index: int,
    case: TestCase,
    target: Target,
    scorers: Sequence[Scorer],
    *,
    isolate: bool = False,
    execution_control: ExecutionControl | None = None,
    case_id: str | None = None,
) -> AttemptResult:
    identity = case.id if case_id is None else case_id
    started_at = datetime.now(UTC)
    started_clock = perf_counter()

    def duration_ms() -> float:
        return (perf_counter() - started_clock) * 1000

    if execution_control is not None:
        execution_control.reserve(identity, index)

    try:
        response: TargetResponse = target.invoke(
            case.model_copy(deep=True) if isolate else case
        )
        if execution_control is not None:
            if not isinstance(response, TargetResponse):
                raise TypeError("Target did not return a TargetResponse")
            response = TargetResponse.model_validate(response.model_dump(mode="python"))
        if isolate:
            response = response.model_copy(deep=True)
    except Exception as exc:
        if execution_control is not None and isinstance(exc, ExecutionControlError):
            raise
        return AttemptResult(
            index=index,
            response=None,
            verdict=Verdict.ERROR,
            error=_target_error(target, exc),
            started_at=started_at,
            duration_ms=duration_ms(),
        )

    if execution_control is not None:
        execution_control.response_received(
            identity, index, response.model_copy(deep=True)
        )

    scores: list[Score] = []
    errors: list[str] = []
    for scorer in scorers:
        score = None
        error = None
        try:
            score = scorer.score(
                case.model_copy(deep=True) if isolate else case,
                response.model_copy(deep=True) if isolate else response,
            )
            if execution_control is not None:
                if not isinstance(score, Score) or score.name != scorer.name:
                    raise TypeError("Scorer did not return a matching Score")
                score = Score.model_validate(score.model_dump(mode="python"))
            scores.append(score.model_copy(deep=True) if isolate else score)
        except Exception as exc:
            if execution_control is not None and isinstance(exc, ExecutionControlError):
                raise
            score = None
            error = _scorer_error(scorer, exc)
            errors.append(error)
        if execution_control is not None:
            execution_control.scorer_recorded(
                identity,
                index,
                scorer.name,
                score.model_copy(deep=True) if score is not None else None,
                error,
            )

    return AttemptResult(
        index=index,
        response=response,
        scores=scores,
        verdict=_verdict_for(scores, errors),
        error="; ".join(errors) if errors else None,
        started_at=started_at,
        duration_ms=duration_ms(),
    )


def _scorer_snapshot(scorer: Scorer) -> dict[str, object]:
    snapshot: dict[str, object] = {
        "name": scorer.name,
        "kind": scorer.kind.value,
        "requires": sorted(scorer.requires),
    }
    pass_threshold = getattr(scorer, "pass_threshold", None)
    if isinstance(pass_threshold, (int, float)):
        snapshot["pass_threshold"] = pass_threshold
    judge_model = getattr(scorer, "judge_model", None)
    if isinstance(judge_model, str):
        snapshot["judge_model"] = judge_model
    rubric = getattr(scorer, "rubric", None)
    if isinstance(rubric, str):
        snapshot["rubric"] = rubric
    schema_version = getattr(scorer, "schema_version", None)
    if isinstance(schema_version, str):
        snapshot["schema_version"] = schema_version
    for key in (
        "projection_version",
        "prompt_version",
        "judgment_version",
        "rubric_version",
    ):
        value = getattr(scorer, key, None)
        if isinstance(value, str):
            snapshot[key] = value
    evidence_settings = getattr(scorer, "evidence_settings", None)
    if evidence_settings:
        snapshot["evidence_settings"] = evidence_settings
    output = getattr(scorer, "output_validation", None)
    if isinstance(output, ScoreOutputContract):
        snapshot["output_validation"] = output.model_dump(mode="json")
    return snapshot


def _model_versions(scorers: Sequence[Scorer]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for scorer in scorers:
        judge_model = getattr(scorer, "judge_model", None)
        if isinstance(judge_model, str):
            versions[f"judge:{scorer.name}"] = judge_model
    return versions


def run(
    target: Target,
    scorers: Sequence[Scorer],
    cases: Sequence[TestCase],
    *,
    attempts: int = 1,
    dataset_path: str = "<inline>",
    fingerprint_scheme: str = CASE_SCHEME_V1,
    case_extra_keys: Sequence[str] = (),
    case_payload_snapshot: str | None = None,
    execution_control: ExecutionControl | None = None,
    execution_context: dict[str, object] | None = None,
) -> RunResult:
    """Run every case and scorer, returning one self-contained result."""
    if execution_context is not None and execution_control is None:
        raise ValueError("Execution context requires execution control")
    scheme = validate_case_scheme(fingerprint_scheme)
    v2 = scheme == CASE_SCHEME_V2
    if not v2 and (case_extra_keys or case_payload_snapshot is not None):
        raise ValueError("Definition snapshot options require dataset-cases-v2")
    if v2 and (type(attempts) is not int or attempts < 1):
        raise ValueError("attempts must be a positive integer")
    policy = "hashes_only" if case_payload_snapshot is None else case_payload_snapshot
    if policy not in ("hashes_only", "full"):
        raise ValueError("Unknown case payload snapshot policy")
    selected_cases = [c.model_copy(deep=True) for c in cases] if v2 else list(cases)
    selected_scorers = list(scorers)
    _validate_run(target, selected_scorers, selected_cases, attempts)
    # Hash before calls even for v1: populated v2 fields must fail in preflight.
    dataset_hash = hash_cases(selected_cases, scheme=scheme)
    definitions = (
        [definition_snapshot(c, case_extra_keys) for c in selected_cases] if v2 else []
    )
    config = None
    versions = None
    if v2:
        config = {
            "organization_schema_version": "run-organization-v1",
            "dataset_fingerprint_scheme": scheme,
            "full_dataset_hash": dataset_hash,
            "selection": {"expression": {}, "case_ids": [c.id for c in selected_cases]},
            "case_payload_snapshot": policy,
            "case_payload_snapshot_source": "default"
            if case_payload_snapshot is None
            else "run_override",
            "artifact_capabilities": {
                "definition_payloads": policy == "full",
                "external_source_cases_required": policy != "full"
                or any(
                    not set(c.extra) <= set(case_extra_keys) for c in selected_cases
                ),
            },
            "metadata_snapshot_policy": {
                "case_extra_keys": metadata_keys(case_extra_keys),
                "dataset_extra_keys": [],
            },
            "attempts": attempts,
            "target": target.name,
            "target_capabilities": sorted(target.capabilities),
            "scorers": [_scorer_snapshot(s) for s in selected_scorers],
        }
        if policy == "full":
            config["resolved_cases"] = [
                resolved_case_payload(c, scheme=scheme) for c in selected_cases
            ]
        validate_json_data(config)
        config = deepcopy(config)
        versions = deepcopy(_model_versions(selected_scorers))

    started_at = datetime.now(UTC)
    case_results: list[CaseResult] = []
    controlled_run = None
    if execution_control is not None:
        controlled_run = RunResult(
            config_path="<inline>",
            config_snapshot=config
            if config is not None
            else {
                "attempts": attempts,
                "target": target.name,
                "target_capabilities": sorted(target.capabilities),
                "scorers": [_scorer_snapshot(s) for s in selected_scorers],
            },
            target_name=target.name,
            pack_name="none",
            dataset_path=dataset_path,
            dataset_hash=dataset_hash,
            model_versions=versions or _model_versions(selected_scorers),
            started_at=started_at,
        )
        if execution_context is not None:
            validate_json_data(execution_context)
            controlled_run.config_snapshot.update(deepcopy(execution_context))
    primary_failure: BaseException | None = None
    try:
        if execution_control is not None:
            assert controlled_run is not None
            execution_control.prepared(controlled_run, selected_cases)
        dispatch = True
        for position, case in enumerate(selected_cases):
            # Match the baseline's keyword evaluation order: capture metadata
            # before attempts, but construct/validate CaseResult afterward.
            case_id = case.id
            tags = list(case.tags)
            definition = definitions[position] if v2 else None
            completed: list[AttemptResult] = []
            for index in range(attempts):
                attempt = _execute_attempt(
                    index,
                    case,
                    target,
                    selected_scorers,
                    isolate=v2,
                    execution_control=execution_control,
                    case_id=case_id,
                )
                completed.append(attempt)
                if execution_control is not None:
                    dispatch = execution_control.attempt_completed(
                        case_id, attempt.model_copy(deep=True)
                    )
                    if not dispatch:
                        break
            case_results.append(
                CaseResult(
                    case_id=case_id,
                    tags=tags,
                    definition=definition,
                    attempts=completed,
                )
            )
            if not dispatch:
                break
    except BaseException as exc:
        primary_failure = exc
        raise
    finally:
        if isinstance(target, CloseableTarget):
            if execution_control is None:
                target.close()
            else:
                try:
                    target.close()
                except BaseException as cleanup:
                    if primary_failure is not None:
                        primary_failure.add_note(
                            f"Target cleanup also failed: {type(cleanup).__name__}"
                        )
                    elif isinstance(cleanup, Exception) and any(
                        attempt.verdict is Verdict.ERROR
                        for case_result in case_results
                        for attempt in case_result.attempts
                    ):
                        assert controlled_run is not None
                        controlled_run.config_snapshot["execution_cleanup_error"] = (
                            type(cleanup).__name__
                        )
                    else:
                        raise

    if execution_control is not None:
        assert controlled_run is not None
        controlled_run.cases = case_results
        controlled_run.finished_at = datetime.now(UTC)
        execution_control.run_assembled(controlled_run)
        return controlled_run

    return RunResult(
        config_path="<inline>",
        config_snapshot=config
        if config is not None
        else {
            "attempts": attempts,
            "target": target.name,
            "target_capabilities": sorted(target.capabilities),
            "scorers": [_scorer_snapshot(scorer) for scorer in selected_scorers],
        },
        target_name=str(config["target"]) if config is not None else target.name,
        pack_name="none",
        dataset_path=dataset_path,
        dataset_hash=dataset_hash,
        model_versions=versions
        if versions is not None
        else _model_versions(selected_scorers),
        started_at=started_at,
        finished_at=datetime.now(UTC),
        cases=case_results,
    )


__all__ = ["run"]
