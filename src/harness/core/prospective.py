"""Human-first judging of captured responses, without target execution.

These are new prospective identities, never assertions about a historical judge.
Nested data is canonical JSON so an artifact cannot change through a dictionary.
"""

from __future__ import annotations

import hashlib
import json
import warnings
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from harness.core.case_fingerprints import (
    CASE_SCHEME_V2,
    hash_case_definition,
    validate_json_data,
)
from harness.core.fingerprints import canonical_json, fingerprint, text_hash
from harness.core.models import (
    RunResult,
    Score,
    ScorerKind,
    TargetResponse,
    TestCase,
    Verdict,
)
from harness.core.replay import (
    EvaluatorConfiguration,
    JudgeConfiguration,
    ReplayAttemptResult,
    ReplayValidationError,
    SourceProvenance,
    _check_projected_fields,
    _verify_source,
    replay_input_hash,
    score_verdict,
    validate_score,
)
from harness.judges.base import JudgeObservation, JudgeScoringError
from harness.scorers.base import JudgedScorer, PreparedJudgeInput
from harness.scorers.rubric_judge import RubricJudgeScorer

if TYPE_CHECKING:
    from harness.core.prospective_io import ProspectiveStore

Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SourceLoader = Callable[[SourceProvenance], tuple[RunResult, Sequence[TestCase], str]]


def strict_json(value: str | bytes):
    """Reject ambiguity even inside canonical-string bodies."""

    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = item
        return result

    def constant(_):
        raise ValueError("Non-finite JSON")

    return json.loads(value, object_pairs_hook=pairs, parse_constant=constant)


class Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @property
    def digest(self) -> str:
        return fingerprint(self.model_dump(mode="json"))


class ProspectiveSelection(Frozen):
    request_id: Identifier
    observation_id: Identifier
    source: SourceProvenance
    attempts: int = Field(gt=0, strict=True)
    role: Literal["primary", "diagnostic"]
    requires_human: bool
    parent_request_hash: Digest | None = None

    @model_validator(mode="after")
    def valid(self) -> Self:
        if self.role == "primary" and (self.attempts != 1 or self.parent_request_hash):
            raise ValueError("Primary selection requires one call and no parent")
        return self


class ProspectiveJudgingPlan(Frozen):
    schema_version: Literal["prospective-judging-plan-v1"] = (
        "prospective-judging-plan-v1"
    )
    plan_id: Identifier
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    selections: tuple[ProspectiveSelection, ...]
    evaluator: EvaluatorConfiguration
    taxonomy_evidence: Literal["excluded", "explicitly_included"]
    sharing_policy: Literal["evaluation_data"]
    review_set_id: Identifier | None = None
    rating_contract_hash: Digest | None = None

    @model_validator(mode="after")
    def valid(self) -> Self:
        if not self.selections:
            raise ValueError("Plan has no source selections")
        for values in (
            [s.request_id for s in self.selections],
            [s.observation_id for s in self.selections],
            [
                (s.source.run_id, s.source.case_id, s.source.attempt_index)
                for s in self.selections
            ],
        ):
            if len(set(values)) != len(values):
                raise ValueError("Duplicate prospective identity")
        protected = any(s.requires_human for s in self.selections)
        if protected != (
            self.review_set_id is not None and self.rating_contract_hash is not None
        ):
            raise ValueError("Protected plans require a review set and rating contract")
        if not protected and (self.review_set_id or self.rating_contract_hash):
            raise ValueError("Unprotected plan cannot claim a human contract")
        return self

    def selection(self, request_id: str) -> ProspectiveSelection:
        matches = [s for s in self.selections if s.request_id == request_id]
        if len(matches) != 1:
            raise ValueError("Unknown prospective request")
        return matches[0]


class PreparedProspectiveJudgment(Frozen):
    schema_version: Literal["prepared-prospective-judgment-v1"] = (
        "prepared-prospective-judgment-v1"
    )
    kind: Literal["prospective"]
    plan: ProspectiveJudgingPlan
    plan_hash: Digest
    request_id: Identifier
    response_json: str
    prepared: PreparedJudgeInput
    input_hash: Digest

    @property
    def selection(self) -> ProspectiveSelection:
        return self.plan.selection(self.request_id)

    @property
    def source(self) -> SourceProvenance:
        return self.selection.source

    @property
    def evaluator(self) -> EvaluatorConfiguration:
        return self.plan.evaluator

    @property
    def requested_attempt_count(self) -> int:
        return self.selection.attempts

    @model_validator(mode="after")
    def valid(self) -> Self:
        if self.plan_hash != self.plan.digest:
            raise ValueError("Plan fingerprint differs")
        self.plan.selection(self.request_id)
        response = strict_json(self.response_json)
        if (
            canonical_json(response) != self.response_json
            or fingerprint(response) != self.source.response_hash
        ):
            raise ValueError("Response fingerprint differs")
        if (
            canonical_json(
                TargetResponse.model_validate_json(self.response_json).model_dump(
                    mode="json"
                )
            )
            != self.response_json
        ):
            raise ValueError("Response is not a normalized snapshot")
        if (
            self.prepared.configuration_json != self.evaluator.scorer_json
            or self.input_hash != replay_input_hash(self.prepared, self.evaluator)
        ):
            raise ValueError("Prepared evaluator/input fingerprint differs")
        if self.prepared.evidence_json is None:
            raise ValueError("Prospective review requires projected evidence")
        evidence = strict_json(self.prepared.evidence_json)
        if canonical_json(evidence) != self.prepared.evidence_json:
            raise ValueError("Evidence must be canonical")
        _check_projected_fields(evidence)
        return self


def bind_source(
    source: RunResult,
    cases: Sequence[TestCase],
    *,
    database_locator: str,
    case_id: str,
    source_attempt: int,
    source_document_hash: str,
) -> SourceProvenance:
    """Bind an independently loaded stored document and full source dataset."""
    if fingerprint(source.model_dump(mode="json")) != source_document_hash:
        raise ValueError("Stored source document fingerprint differs")
    case, attempt, scheme = _verify_source(
        source,
        cases,
        database_locator=database_locator,
        case_id=case_id,
        source_attempt=source_attempt,
    )
    assert attempt.response is not None
    validate_json_data(case.model_dump())
    validate_json_data(attempt.response.model_dump())
    if any(s.kind == ScorerKind.JUDGED for s in attempt.scores) or any(
        isinstance(s, dict) and s.get("kind") == ScorerKind.JUDGED.value
        for s in source.config_snapshot.get("scorers", [])
    ):
        raise ValueError("Prospective source already contains a judged result")
    return SourceProvenance(
        database=database_locator,
        run_id=source.run_id,
        case_id=case_id,
        attempt_index=source_attempt,
        document_hash=source_document_hash,
        response_hash=fingerprint(attempt.response.model_dump(mode="json")),
        dataset_hash=source.dataset_hash,
        full_dataset_hash=source.config_snapshot.get("full_dataset_hash"),
        case_hash=hash_case_definition(case, scheme=scheme),
        input_hash=fingerprint(case.input),
        selection=tuple(c.case_id for c in source.cases),
        target_name=source.target_name,
        source_model_versions=tuple(sorted(source.model_versions.items())),
        evidence_schema_version=source.config_snapshot.get("evidence_schema_version"),
        dataset_fingerprint_scheme=scheme if scheme == CASE_SCHEME_V2 else None,
    )


def prepare_prospective(
    plan: ProspectiveJudgingPlan,
    source: RunResult,
    cases: Sequence[TestCase],
    scorer: JudgedScorer,
    judge_configuration: JudgeConfiguration,
    *,
    request_id: str,
    source_document_hash: str,
) -> PreparedProspectiveJudgment:
    plan = ProspectiveJudgingPlan.model_validate_json(plan.model_dump_json())
    selection = plan.selection(request_id)
    p = selection.source
    actual = bind_source(
        source,
        cases,
        database_locator=p.database,
        case_id=p.case_id,
        source_attempt=p.attempt_index,
        source_document_hash=source_document_hash,
    )
    if actual != p:
        raise ValueError("Prospective source changed")
    if (
        not scorer.projection_reviewed
        or canonical_json(scorer.preparation_configuration)
        != plan.evaluator.scorer_json
        or judge_configuration != plan.evaluator.judge
    ):
        raise ValueError("Unreviewed or changed evaluator configuration")
    # Exclusion is an integration-owned projection contract, never a core filter.
    if (
        plan.taxonomy_evidence == "excluded"
        and isinstance(scorer, RubricJudgeScorer)
        and scorer.evidence_builder is None
    ):
        raise ValueError("Taxonomy exclusion requires an explicit evidence builder")
    case, attempt, _ = _verify_source(
        source,
        cases,
        database_locator=p.database,
        case_id=p.case_id,
        source_attempt=p.attempt_index,
    )
    assert attempt.response is not None
    response_json = canonical_json(attempt.response.model_dump(mode="json"))
    before = fingerprint(case.model_dump(mode="json"))
    try:
        prepared = scorer.prepare(case, attempt.response)
        validate_json_data(case.model_dump())
        validate_json_data(attempt.response.model_dump())
        if before != fingerprint(
            case.model_dump(mode="json")
        ) or response_json != canonical_json(attempt.response.model_dump(mode="json")):
            raise ValueError("Builder mutated source")
    except Exception:  # noqa: BLE001 - projection errors must not expose source bodies
        raise ValueError("Source projection failed or mutated its inputs") from None
    return PreparedProspectiveJudgment(
        kind="prospective",
        plan=plan,
        plan_hash=plan.digest,
        request_id=request_id,
        response_json=response_json,
        prepared=prepared,
        input_hash=replay_input_hash(prepared, plan.evaluator),
    )


def verify_prospective(
    request: PreparedProspectiveJudgment,
    source_loader: SourceLoader,
    scorer: JudgedScorer,
) -> PreparedProspectiveJudgment:
    request = PreparedProspectiveJudgment.model_validate_json(request.model_dump_json())
    source, cases, stored_hash = source_loader(request.source)
    rebuilt = prepare_prospective(
        request.plan,
        source,
        cases,
        scorer,
        request.evaluator.judge,
        request_id=request.request_id,
        source_document_hash=stored_hash,
    )
    if rebuilt != request:
        raise ValueError("Rebuilt prospective source/input differs")
    return rebuilt


class FreezeProof(Frozen):
    receipt_hash: Digest
    manifest_hash: Digest
    packet_hash: Digest
    annotation_hash: Digest
    revision_id: Identifier
    frozen_at: AwareDatetime


def verify_freeze(
    request: PreparedProspectiveJudgment,
    path: Path | None,
    *,
    parent: PreparedProspectiveJudgment | None = None,
) -> FreezeProof | None:
    """Verify the exact protected roster, before constructing any judge client."""
    from harness.core.calibration_io import load_frozen

    selection = request.selection
    if selection.parent_request_hash is not None:
        if parent is None or parent.digest != selection.parent_request_hash:
            raise ValueError("Missing or changed diagnostic parent")
        if (
            request.plan.plan_id == parent.plan.plan_id
            or request.request_id == parent.request_id
            or selection.observation_id == parent.selection.observation_id
        ):
            raise ValueError("Diagnostic identities must be new")
        if (
            request.source,
            request.prepared,
            request.evaluator,
            request.plan.taxonomy_evidence,
            selection.requires_human,
            request.plan.review_set_id,
            request.plan.rating_contract_hash,
        ) != (
            parent.source,
            parent.prepared,
            parent.evaluator,
            parent.plan.taxonomy_evidence,
            parent.selection.requires_human,
            parent.plan.review_set_id,
            parent.plan.rating_contract_hash,
        ):
            raise ValueError("Diagnostic source/evaluator/protection differs")
        if parent.selection.parent_request_hash:
            raise ValueError("Diagnostic parent must be the original request")
        request = parent
    elif parent is not None:
        raise ValueError("Unexpected diagnostic parent")
    if not request.selection.requires_human:
        if path is not None:
            raise ValueError("Unprotected request cannot claim a freeze receipt")
        return None
    if path is None:
        raise ValueError("Protected request requires a complete freeze receipt")
    raw = (path / "receipt.json").read_bytes()
    manifest, frozen = load_frozen(path)
    if raw != (path / "receipt.json").read_bytes():
        raise ValueError("Receipt changed during verification")
    plan = request.plan
    if (
        manifest.set_id != plan.review_set_id
        or manifest.contract.digest != plan.rating_contract_hash
        or frozen.partial
        or frozen.missing_ids
    ):
        raise ValueError("Wrong or incomplete protected freeze")
    roster = {s.request_id for s in plan.selections if s.requires_human}
    prepared = [e.prepared for e in manifest.examples]
    if any(
        not isinstance(p, PreparedProspectiveJudgment) or p.plan != plan
        for p in prepared
    ):
        raise ValueError("Freeze belongs to another prospective plan")
    actual = {
        p.request_id for p in prepared if isinstance(p, PreparedProspectiveJudgment)
    }
    if actual != roster or len(prepared) != len(roster) or request not in prepared:
        raise ValueError("Freeze does not cover the exact protected roster")
    return FreezeProof(
        receipt_hash=hashlib.sha256(raw).hexdigest(),
        manifest_hash=manifest.digest,
        packet_hash=frozen.packet_hash,
        annotation_hash=frozen.digest,
        revision_id=frozen.revision_id,
        frozen_at=frozen.frozen_at,
    )


class ProspectiveJudgmentResult(Frozen):
    schema_version: Literal["prospective-judgment-result-v1"] = (
        "prospective-judgment-result-v1"
    )
    input: PreparedProspectiveJudgment
    observation_id: Identifier
    started_at: AwareDatetime
    finished_at: AwareDatetime
    freeze: FreezeProof | None
    attempts_json: str

    @property
    def attempts(self) -> tuple[ReplayAttemptResult, ...]:
        return tuple(
            ReplayAttemptResult.model_validate_json(canonical_json(a))
            for a in strict_json(self.attempts_json)
        )

    @model_validator(mode="after")
    def valid(self) -> Self:
        if (
            self.observation_id != self.input.selection.observation_id
            or (self.freeze is not None) != self.input.selection.requires_human
        ):
            raise ValueError("Observation identity/protection differs")
        if canonical_json(strict_json(self.attempts_json)) != self.attempts_json:
            raise ValueError("Attempts must be canonical")
        if (
            self.finished_at < self.started_at
            or self.started_at < self.input.plan.created_at
            or (self.freeze and self.started_at < self.freeze.frozen_at)
        ):
            raise ValueError("Invalid prospective chronology")
        attempts = self.attempts
        if (
            canonical_json([a.model_dump(mode="json") for a in attempts])
            != self.attempts_json
        ):
            raise ValueError("Attempts must contain normalized values without coercion")
        if len(attempts) != self.input.requested_attempt_count:
            raise ValueError("Prospective attempt count differs")
        config = json.loads(self.input.evaluator.scorer_json)
        previous = self.started_at
        for index, attempt in enumerate(attempts):
            if (
                attempt.started_at.tzinfo is None
                or not previous <= attempt.started_at <= self.finished_at
            ):
                raise ValueError("Invalid attempt chronology")
            previous = attempt.started_at
            if (
                attempt.index != index
                or attempt.input_hash != self.input.input_hash
                or (
                    attempt.prompt_hash is not None
                    and attempt.prompt_hash != self.input.prepared.prompt_hash
                )
            ):
                raise ValueError("Actual input fingerprint differs")
            if attempt.score:
                validate_score(attempt.score, config)
                if attempt.prompt_hash is None or attempt.observation.model_dump(
                    exclude_none=True
                ) != attempt.score.extra.get("judge", {}):
                    raise ValueError("Score invocation/observations differ")
        return self


@dataclass(frozen=True)
class ProspectiveJudge:
    scorer: JudgedScorer
    configuration: Callable[[], JudgeConfiguration]
    close: Callable[[], None] = lambda: None


def execute_prospective(
    request: PreparedProspectiveJudgment,
    *,
    source_loader: SourceLoader,
    verification_scorer: JudgedScorer,
    scorer_factory: Callable[[], ProspectiveJudge],
    store: ProspectiveStore,
    frozen_bundle: Path | None = None,
    parent: PreparedProspectiveJudgment | None = None,
) -> ProspectiveJudgmentResult:
    """Reserve once, then judge. Return the complete result for explicit save/retry.

    Verification scorer must be a pure preparer; it is never invoked as a judge.
    A reservation remains after failure/crash; retries need a new diagnostic ID.
    """
    request = verify_prospective(request, source_loader, verification_scorer)
    proof = verify_freeze(request, frozen_bundle, parent=parent)
    if proof and proof.frozen_at > datetime.now(UTC):
        raise ValueError("Freeze time is in the future")
    if request.plan.created_at > datetime.now(UTC):
        raise ValueError("Plan time is in the future")
    store.reserve(request)
    judge = scorer_factory()
    try:
        scorer = judge.scorer
        if (
            not scorer.projection_reviewed
            or canonical_json(scorer.preparation_configuration)
            != request.evaluator.scorer_json
            or judge.configuration() != request.evaluator.judge
        ):
            raise ValueError("Actual judge configuration differs")
        # The actual factory may supply a different projection despite its version label.
        verify_prospective(request, source_loader, scorer)
        started = datetime.now(UTC)
        results = []
        for index in range(request.requested_attempt_count):
            attempt_started, clock = datetime.now(UTC), perf_counter()
            actual_hash: str | None = None
            observation = JudgeObservation()
            score: Score | None = None
            error: (
                Literal[
                    "judge_execution_error",
                    "malformed_judgment",
                    "input_integrity_error",
                ]
                | None
            ) = None

            def on_call(prompt: str) -> None:
                nonlocal actual_hash
                if (
                    actual_hash is not None
                    or text_hash(prompt) != request.prepared.prompt_hash
                    or judge.configuration() != request.evaluator.judge
                    or canonical_json(scorer.preparation_configuration)
                    != request.evaluator.scorer_json
                ):
                    raise ReplayValidationError(
                        "Actual prospective input/configuration changed"
                    )
                actual_hash = text_hash(prompt)

            try:
                candidate = scorer.score_prepared(request.prepared, on_call=on_call)
                if actual_hash is None:
                    raise ReplayValidationError("Missing actual invocation")
                validate_score(candidate, json.loads(request.evaluator.scorer_json))
                observation = JudgeObservation.model_validate(
                    candidate.extra.get("judge", {})
                )
                score = candidate.model_copy(deep=True)
            except JudgeScoringError as exc:
                observation, error = exc.observation, "malformed_judgment"
            except ReplayValidationError:
                error = "input_integrity_error"
            except Exception:  # noqa: BLE001 - retain infrastructure failure as result data
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
                    input_hash=request.input_hash,
                )
            )
        result = ProspectiveJudgmentResult(
            input=request,
            observation_id=request.selection.observation_id,
            started_at=started,
            finished_at=datetime.now(UTC),
            freeze=proof,
            attempts_json=canonical_json([r.model_dump(mode="json") for r in results]),
        )
    finally:
        try:
            judge.close()
        except Exception:  # noqa: BLE001 - cleanup must not discard completed observations
            warnings.warn(
                "Judge cleanup failed; retain the execution reservation/result",
                RuntimeWarning,
                stacklevel=2,
            )
    return result
