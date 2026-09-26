"""Fixed-input judge experiments. This module has no target execution surface."""

from __future__ import annotations

import json
import math
import re
import statistics
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from harness.core.dataset import hash_cases
from harness.core.fingerprints import (
    CANONICAL_VERSION,
    canonical_json,
    fingerprint,
    text_hash,
)
from harness.core.models import RunResult, Score, ScorerKind, TestCase, Verdict
from harness.judges.base import JudgeObservation, JudgeScoringError
from harness.scorers.base import JudgedScorer, PreparedJudgeInput


class ReplayValidationError(ValueError):
    """Safe preflight diagnostic; never include source data or local paths."""


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class JudgeTimeouts(_Frozen):
    connect: float = Field(gt=0, allow_inf_nan=False, strict=True)
    read: float = Field(gt=0, allow_inf_nan=False, strict=True)
    write: float = Field(gt=0, allow_inf_nan=False, strict=True)
    pool: float = Field(gt=0, allow_inf_nan=False, strict=True)


class JudgeConfiguration(_Frozen):
    """Explicit supported settings, never credentials or arbitrary provider data."""

    provider: str = Field(pattern=r"^[a-zA-Z0-9._-]+$")
    model: str = Field(pattern=r"^[a-zA-Z0-9._:/-]+$")
    adapter_version: str = Field(min_length=1)
    instruction_version: str = Field(min_length=1)
    response_schema: str = Field(min_length=1)
    endpoint: str | None = None
    max_output_tokens: int = Field(gt=0, strict=True)
    timeouts: JudgeTimeouts
    retries: Literal[0] = 0
    store: Literal[False] = False
    stream: Literal[False] = False
    tools: tuple[()] = ()
    sampling: Literal["unspecified"] = "unspecified"

    @field_validator("endpoint")
    @classmethod
    def safe_endpoint(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(
            r"https://[a-zA-Z0-9.-]+(/[a-zA-Z0-9._/-]*)?", value
        ):
            raise ValueError("Judge endpoint must be a credential-free HTTPS URL")
        return value


class EvaluatorConfiguration(_Frozen):
    """Canonical authored scorer settings plus a strict provider-neutral config."""

    scorer_json: str
    judge: JudgeConfiguration

    @field_validator("scorer_json")
    @classmethod
    def scorer_schema(cls, value: str) -> str:
        config = json.loads(value)
        expected = {
            "name",
            "kind",
            "requires",
            "judge_model",
            "pass_threshold",
            "rubric",
            "rubric_version",
            "projection_version",
            "prompt_version",
            "judgment_version",
            "evidence_settings",
        }
        if not isinstance(config, dict) or set(config) != expected:
            raise ValueError("Explicit scorer configuration is required")
        if (
            config["kind"] != "judged"
            or not isinstance(config["name"], str)
            or not config["name"]
        ):
            raise ValueError("A named judged scorer is required")
        for key in (
            "projection_version",
            "prompt_version",
            "judgment_version",
            "rubric_version",
        ):
            if not isinstance(config[key], str) or not config[key].strip():
                raise ValueError("Explicit scorer versions are required")
        threshold = config["pass_threshold"]
        if threshold is not None and (
            type(threshold) not in (int, float)
            or not math.isfinite(threshold)
            or not 0 <= threshold <= 1
        ):
            raise ValueError("Invalid scorer threshold")
        if not isinstance(config["requires"], list) or any(
            not isinstance(v, str) for v in config["requires"]
        ):
            raise ValueError("Invalid scorer requirements")
        if config["rubric"] is not None and not isinstance(config["rubric"], str):
            raise ValueError("Invalid rubric")
        settings = config["evidence_settings"]
        if not isinstance(settings, dict) or any(
            type(v) not in (str, int) for v in settings.values()
        ):
            raise ValueError("Invalid evidence settings")
        return canonical_json(config)

    @model_validator(mode="after")
    def matching_model(self) -> Self:
        if json.loads(self.scorer_json)["judge_model"] != self.judge.model:
            raise ValueError("Scorer and judge models differ")
        return self


class SourceProvenance(_Frozen):
    database: str
    run_id: str
    case_id: str
    attempt_index: int = Field(ge=0, strict=True)
    document_hash: str
    response_hash: str
    dataset_hash: str
    full_dataset_hash: str | None = None
    case_hash: str
    input_hash: str
    selection: tuple[str, ...]
    target_name: str
    source_model_versions: tuple[tuple[str, str], ...] = ()
    evidence_schema_version: str | None = None
    observed_judge_model: str | None = None

    @field_validator("database")
    @classmethod
    def safe_locator(cls, value: str) -> str:
        if not re.fullmatch(
            r"[a-zA-Z0-9][a-zA-Z0-9._/-]*", value
        ) or ".." in value.split("/"):
            raise ValueError("Source locator must be logical or repository-relative")
        return value


def source_locator(path: Path, repository: Path) -> str:
    """Keep absolute and external filesystem paths out of portable artifacts."""
    try:
        value = path.resolve().relative_to(repository.resolve()).as_posix()
        return SourceProvenance.safe_locator(value)
    except ValueError:
        return "external-source"


class PreparedReplay(_Frozen):
    source: SourceProvenance
    prepared: PreparedJudgeInput
    evaluator: EvaluatorConfiguration
    source_evaluator: EvaluatorConfiguration | None
    compatibility: Literal["matching_recorded_configuration", "different", "unknown"]
    differences: tuple[str, ...]
    requested_attempt_count: int = Field(gt=0, strict=True)
    canonical_version: Literal["replay-canonical-json-v1"] = "replay-canonical-json-v1"
    input_hash: str

    @model_validator(mode="after")
    def input_integrity(self) -> Self:
        if self.prepared.configuration_json != self.evaluator.scorer_json:
            raise ValueError("Prepared scorer configuration differs")
        if self.input_hash != replay_input_hash(self.prepared, self.evaluator):
            raise ValueError("Replay input fingerprint differs")
        if self.prepared.evidence_json is not None:
            evidence = json.loads(self.prepared.evidence_json)
            if canonical_json(evidence) != self.prepared.evidence_json:
                raise ValueError("Prepared evidence must be canonical JSON")
            _check_projected_fields(evidence)
        expected_differences = (
            ("source_evaluator_unrecorded",)
            if self.source_evaluator is None
            else tuple(
                _differences(
                    {
                        "scorer": json.loads(self.source_evaluator.scorer_json),
                        "judge": self.source_evaluator.judge.model_dump(mode="json"),
                    },
                    {
                        "scorer": json.loads(self.evaluator.scorer_json),
                        "judge": self.evaluator.judge.model_dump(mode="json"),
                    },
                )
            )
        )
        expected_status = (
            "unknown"
            if self.source_evaluator is None
            else "different"
            if expected_differences
            else "matching_recorded_configuration"
        )
        if (
            self.differences != expected_differences
            or self.compatibility != expected_status
        ):
            raise ValueError("Replay compatibility metadata differs")
        return self


def replay_input_hash(
    prepared: PreparedJudgeInput, evaluator: EvaluatorConfiguration
) -> str:
    return fingerprint(
        {
            "schema": "judge-replay-input-v1",
            "canonical_version": CANONICAL_VERSION,
            "prompt_hash": prepared.prompt_hash,
            "evidence_hash": prepared.evidence_hash,
            "evaluator": evaluator.model_dump(mode="json"),
        }
    )


def _unique(values: Sequence[str | int], description: str) -> None:
    if len(values) != len(set(values)):
        raise ReplayValidationError(f"Duplicate {description}")


def _differences(before: Any, after: Any, prefix: str = "") -> list[str]:
    if isinstance(before, dict) and isinstance(after, dict):
        return [
            field
            for key in sorted(before.keys() | after.keys())
            for field in _differences(
                before.get(key), after.get(key), f"{prefix}.{key}".strip(".")
            )
        ]
    return [prefix] if before != after else []


def _check_projected_fields(value: Any) -> None:
    """Supplement reviewed allowlists with rejection of known operational keys.

    This is not a natural-language sensitive-content detector. A custom prompt
    without structured evidence remains the reviewed scorer author's contract.
    """
    forbidden = {
        "raw",
        "metadata",
        "hidden_prompt",
        "system_prompt",
        "authorization",
        "api_key",
        "assertions",
        "verdict",
        "passed",
        "provider_response",
    }
    if isinstance(value, dict):
        if forbidden & value.keys():
            raise ReplayValidationError(
                "Projected evidence contains excluded operational fields"
            )
        for child in value.values():
            _check_projected_fields(child)
    elif isinstance(value, list):
        for child in value:
            _check_projected_fields(child)


def prepare_replay(
    source: RunResult,
    cases: Sequence[TestCase],
    scorer: JudgedScorer,
    *,
    judge_configuration: JudgeConfiguration,
    database_locator: str,
    case_id: str,
    source_attempt: int,
    attempts: int,
    source_evaluator: EvaluatorConfiguration | None = None,
    source_document_hash: str | None = None,
    allow_reconfigured: bool = False,
) -> PreparedReplay:
    """Verify a saved response and dataset before preparing any provider request.

    A recipe may translate its authored historical settings into source_evaluator;
    it must not substitute current settings for missing historical versions.
    """
    if (
        type(attempts) is not int
        or attempts < 1
        or type(source_attempt) is not int
        or source_attempt < 0
    ):
        raise ReplayValidationError("Attempt counts/indexes must be valid integers")
    SourceProvenance.safe_locator(database_locator)
    _unique([c.id for c in cases], "dataset case IDs")
    _unique([c.case_id for c in source.cases], "source case IDs")
    by_id = {c.id: c for c in cases}
    ids = [c.case_id for c in source.cases]
    if not ids or any(i not in by_id for i in ids):
        raise ReplayValidationError("Source selection is absent from dataset")
    selected = [by_id[i] for i in ids]
    snapshot = source.config_snapshot
    if hash_cases(selected) != source.dataset_hash:
        raise ReplayValidationError("Source dataset fingerprint differs")
    full_hash = snapshot.get("full_dataset_hash")
    if full_hash is not None and full_hash != hash_cases(cases):
        raise ReplayValidationError("Full dataset fingerprint differs")
    if "selection" in snapshot and (
        not isinstance(snapshot["selection"], dict)
        or snapshot["selection"].get("case_ids") != ids
    ):
        raise ReplayValidationError("Stored selection differs")
    resolved = snapshot.get("resolved_cases")
    if resolved is not None and resolved != [
        c.model_dump(mode="json", exclude={"extra"}) for c in selected
    ]:
        raise ReplayValidationError("Stored cases differ from verified dataset")
    if any(c.tags != by_id[c.case_id].tags for c in source.cases):
        raise ReplayValidationError("Stored tags differ from verified dataset")
    matches = [c for c in source.cases if c.case_id == case_id]
    if not matches:
        raise ReplayValidationError("Source case not found")
    stored_case = matches[0]
    _unique([a.index for a in stored_case.attempts], "source attempt indexes")
    matches_attempt = [a for a in stored_case.attempts if a.index == source_attempt]
    if not matches_attempt:
        raise ReplayValidationError("Source attempt not found")
    attempt = matches_attempt[0]
    if attempt.response is None:
        raise ReplayValidationError("Source response is missing")
    if not scorer.projection_reviewed:
        raise ReplayValidationError("Replay requires a reviewed evidence projection")
    evaluator = EvaluatorConfiguration(
        scorer_json=canonical_json(scorer.preparation_configuration),
        judge=judge_configuration,
    )
    source_scorers = snapshot.get("scorers", [])
    if not isinstance(source_scorers, list) or any(
        not isinstance(s, dict) or not isinstance(s.get("name"), str)
        for s in source_scorers
    ):
        raise ReplayValidationError("Malformed source scorer configuration")
    _unique([s["name"] for s in source_scorers], "source scorer names")
    recorded = next((s for s in source_scorers if s["name"] == scorer.name), None)
    if source_evaluator is not None:
        translated = json.loads(source_evaluator.scorer_json)
        if recorded is None or any(
            recorded[k] != translated[k] for k in recorded.keys() & translated.keys()
        ):
            raise ReplayValidationError(
                "Source evaluator translation contradicts stored scorer"
            )
    differences = (
        ("source_evaluator_unrecorded",)
        if source_evaluator is None
        else tuple(
            _differences(
                {
                    "scorer": json.loads(source_evaluator.scorer_json),
                    "judge": source_evaluator.judge.model_dump(mode="json"),
                },
                {
                    "scorer": json.loads(evaluator.scorer_json),
                    "judge": evaluator.judge.model_dump(mode="json"),
                },
            )
        )
    )
    compatibility: Literal[
        "matching_recorded_configuration", "different", "unknown"
    ] = (
        "unknown"
        if source_evaluator is None
        else "different"
        if differences
        else "matching_recorded_configuration"
    )
    if differences and not allow_reconfigured:
        raise ReplayValidationError("Source evaluator is incompatible or unrecorded")

    response = attempt.response.model_copy(deep=True)
    case = by_id[case_id].model_copy(deep=True)
    response_hash = fingerprint(response.model_dump(mode="json"))
    case_hash = fingerprint(case.model_dump(mode="json"))
    try:
        prepared = scorer.prepare(case, response)
        if prepared.evidence_json is not None:
            _check_projected_fields(json.loads(prepared.evidence_json))
    except Exception:  # noqa: BLE001 - unsafe builder errors must not expose source content
        raise ReplayValidationError(
            "Source evidence cannot be prepared by this scorer"
        ) from None
    if (
        fingerprint(response.model_dump(mode="json")) != response_hash
        or fingerprint(case.model_dump(mode="json")) != case_hash
    ):
        raise ReplayValidationError("Evidence builder mutated replay inputs")
    observed = [
        s.extra.get("judge", {}).get("observed_model")
        for s in attempt.scores
        if s.name == scorer.name
    ]
    provenance = SourceProvenance(
        database=database_locator,
        run_id=source.run_id,
        case_id=case_id,
        attempt_index=source_attempt,
        document_hash=source_document_hash
        or fingerprint(source.model_dump(mode="json")),
        response_hash=response_hash,
        dataset_hash=source.dataset_hash,
        full_dataset_hash=full_hash,
        case_hash=case_hash,
        input_hash=fingerprint(case.input),
        selection=tuple(ids),
        target_name=source.target_name,
        source_model_versions=tuple(sorted(source.model_versions.items())),
        evidence_schema_version=snapshot.get("evidence_schema_version"),
        observed_judge_model=observed[0] if len(observed) == 1 else None,
    )
    return PreparedReplay(
        source=provenance,
        prepared=prepared,
        evaluator=evaluator,
        source_evaluator=source_evaluator,
        compatibility=compatibility,
        differences=differences,
        requested_attempt_count=attempts,
        input_hash=replay_input_hash(prepared, evaluator),
    )


class ReplayAttemptResult(_Frozen):
    index: int = Field(ge=0, strict=True)
    score: Score | None = None
    verdict: Verdict
    error: (
        Literal["judge_execution_error", "malformed_judgment", "input_integrity_error"]
        | None
    ) = None
    observation: JudgeObservation = Field(default_factory=JudgeObservation)
    started_at: datetime
    duration_ms: float = Field(ge=0, allow_inf_nan=False)
    prompt_hash: str | None = None
    input_hash: str

    @model_validator(mode="after")
    def outcome(self) -> Self:
        if self.verdict == Verdict.ERROR:
            if self.score is not None or self.error is None:
                raise ValueError("ERROR must have no quality score")
        elif (
            self.score is None
            or self.error is not None
            or self.verdict != score_verdict(self.score)
        ):
            raise ValueError("Replay verdict does not match its score")
        return self


def score_verdict(score: Score) -> Verdict:
    return (
        Verdict.SKIP
        if score.passed is None
        else Verdict.PASS
        if score.passed
        else Verdict.FAIL
    )


def variance_summary(attempts: Sequence[ReplayAttemptResult]) -> dict[str, Any]:
    scores = [a.score.value for a in attempts if a.score is not None]
    passes = sum(a.verdict == Verdict.PASS for a in attempts)
    fails = sum(a.verdict == Verdict.FAIL for a in attempts)
    errors = sum(a.verdict == Verdict.ERROR for a in attempts)
    return {
        "attempt_count": len(attempts),
        "completed_score_count": len(scores),
        "error_count": errors,
        "skip_count": sum(a.verdict == Verdict.SKIP for a in attempts),
        "scores_by_attempt": [
            a.score.value if a.score is not None else None for a in attempts
        ],
        "mean": statistics.mean(scores) if scores else None,
        "min": min(scores) if scores else None,
        "max": max(scores) if scores else None,
        "range": max(scores) - min(scores) if scores else None,
        "population_stddev": statistics.pstdev(scores) if scores else None,
        "pass_count": passes,
        "fail_count": fails,
        "pass_rate": passes / (passes + fails) if passes + fails else None,
        "threshold_crossing": bool(passes and fails) if passes + fails else None,
        "insufficient_repeats": len(scores) < 2,
        "error_rate": errors / len(attempts) if attempts else 0.0,
    }


class ReplayResult(_Frozen):
    schema_version: Literal["judge-replay-v1"] = "judge-replay-v1"
    kind: Literal["judge_replay"] = "judge_replay"
    replay_id: str = Field(default_factory=lambda: uuid4().hex)
    input: PreparedReplay
    started_at: datetime
    finished_at: datetime
    attempts: tuple[ReplayAttemptResult, ...]

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if len(self.attempts) != self.input.requested_attempt_count:
            raise ValueError("Replay attempt count differs")
        scorer = json.loads(self.input.evaluator.scorer_json)
        for index, attempt in enumerate(self.attempts):
            if attempt.index != index or attempt.input_hash != self.input.input_hash:
                raise ValueError("Replay attempt identity differs")
            if (
                attempt.prompt_hash is not None
                and attempt.prompt_hash != self.input.prepared.prompt_hash
            ):
                raise ValueError("Replay prompt fingerprint differs")
            if attempt.score is not None:
                if attempt.prompt_hash is None:
                    raise ValueError("Scored attempt requires an actual invocation")
                validate_score(attempt.score, scorer)
                if attempt.observation.model_dump(
                    exclude_none=True
                ) != attempt.score.extra.get("judge", {}):
                    raise ValueError("Score and attempt observations differ")
        return self

    @property
    def summary(self) -> dict[str, Any]:
        models = sorted(
            {
                a.observation.observed_model
                for a in self.attempts
                if a.observation.observed_model
            }
        )
        known_costs = [
            a.observation.cost_usd
            for a in self.attempts
            if a.observation.cost_usd is not None
        ]
        source_model = self.input.source.observed_judge_model
        return {
            **variance_summary(self.attempts),
            "requested_attempt_count": self.input.requested_attempt_count,
            "observed_models": models,
            "observed_model_varied": len(models) > 1,
            "observed_model_unknown_count": sum(
                a.observation.observed_model is None for a in self.attempts
            ),
            "source_observed_model_changed": any(m != source_model for m in models)
            if source_model and models
            else None,
            "known_cost_usd": sum(known_costs) if known_costs else None,
            "known_cost_count": len(known_costs),
            "cost_complete": len(known_costs) == len(self.attempts),
            "calibration": "provisional_uncalibrated",
        }


def validate_score(score: Score, config: dict[str, Any]) -> None:
    threshold = config["pass_threshold"]
    passed = score.value >= threshold if threshold is not None else None
    if (
        score.name != config["name"]
        or score.kind != ScorerKind.JUDGED
        or not math.isfinite(score.value)
        or not 0 <= score.value <= 1
        or score.passed is not passed
    ):
        raise ValueError("Invalid replay score")
    if (
        set(score.extra) - {"judge", "judge_model"}
        or score.extra.get("judge_model") != config["judge_model"]
    ):
        raise ValueError("Invalid replay score observations")
    JudgeObservation.model_validate(score.extra.get("judge", {}))
    if not isinstance(score.reason, str) or not score.reason.strip():
        raise ValueError("Replay score requires a concise reason")


def replay(
    prepared: PreparedReplay,
    scorer: JudgedScorer,
    *,
    judge_configuration: Callable[[], JudgeConfiguration],
) -> ReplayResult:
    """Run exactly N stateless scoring attempts. No Target or runner is accepted.

    The configuration callback reads the judge adapter's safe actual settings;
    custom injected judges are responsible for honoring the stateless contract.
    """
    prepared = PreparedReplay.model_validate_json(prepared.model_dump_json())
    if (
        not scorer.projection_reviewed
        or canonical_json(scorer.preparation_configuration)
        != prepared.evaluator.scorer_json
        or judge_configuration() != prepared.evaluator.judge
    ):
        raise ReplayValidationError(
            "Execution configuration differs from prepared input"
        )
    started = datetime.now(UTC)
    results: list[ReplayAttemptResult] = []
    config = json.loads(prepared.evaluator.scorer_json)
    for index in range(prepared.requested_attempt_count):
        attempt_started, clock = datetime.now(UTC), perf_counter()
        actual_hash: str | None = None
        observation = JudgeObservation()
        score: Score | None = None
        error: (
            Literal[
                "judge_execution_error", "malformed_judgment", "input_integrity_error"
            ]
            | None
        ) = None

        def on_call(prompt: str) -> None:
            nonlocal actual_hash
            if (
                actual_hash is not None
                or text_hash(prompt) != prepared.prepared.prompt_hash
                or judge_configuration() != prepared.evaluator.judge
            ):
                raise ReplayValidationError("Judge input/configuration changed")
            actual_hash = text_hash(prompt)

        try:
            if (
                canonical_json(scorer.preparation_configuration)
                != prepared.evaluator.scorer_json
            ):
                raise ReplayValidationError("Scorer configuration changed")
            candidate = scorer.score_prepared(prepared.prepared, on_call=on_call)
            if actual_hash is None:
                raise ReplayValidationError("Scorer did not record its invocation")
            validate_score(candidate, config)
            observation = JudgeObservation.model_validate(
                candidate.extra.get("judge", {})
            )
            score = candidate.model_copy(deep=True)
        except JudgeScoringError as exc:
            observation = exc.observation
            error = "malformed_judgment"
        except ReplayValidationError:
            error = "input_integrity_error"
        except Exception:  # noqa: BLE001 - infrastructure errors are safe result data
            error = "judge_execution_error"
        results.append(
            ReplayAttemptResult(
                index=index,
                score=score,
                verdict=score_verdict(score) if score else Verdict.ERROR,
                error=error,
                observation=observation,
                started_at=attempt_started,
                duration_ms=(perf_counter() - clock) * 1000,
                prompt_hash=actual_hash,
                input_hash=prepared.input_hash,
            )
        )
    return ReplayResult(
        input=prepared,
        started_at=started,
        finished_at=datetime.now(UTC),
        attempts=tuple(results),
    )
