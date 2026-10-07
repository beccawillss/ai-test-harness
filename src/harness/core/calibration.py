"""Offline, provider-neutral human–judge agreement on frozen evaluator input.

All prose is evaluation data. Hashes detect alteration, not human authorship.
There is deliberately no target, runner or executable judge interface here.
"""

from __future__ import annotations

import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal, Self
from uuid import uuid4

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

from harness.core.fingerprints import canonical_json, fingerprint
from harness.core.models import RunResult, Score, ScorerKind, Verdict
from harness.core.prospective import (
    PreparedProspectiveJudgment,
    ProspectiveJudgmentResult,
    verify_freeze,
)
from harness.core.replay import (
    PreparedReplay,
    ReplayAttemptResult,
    ReplayResult,
    validate_score,
    variance_summary,
)
from harness.judges.base import JudgeObservation
from harness.scorers.output_contracts import ScoreOutputContract

Preparation = PreparedReplay | PreparedProspectiveJudgment

Number = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Text = Annotated[str, Field(min_length=1)]
Reason = Annotated[str, Field(min_length=1, max_length=1000)]
Exposure = Literal[
    "not_seen", "prior_results_seen", "recognized_during_review", "unknown"
]
DimensionValue = Literal["adequate", "minor_issue", "material_issue", "not_applicable"]
Verification = Literal["frozen_request_verified", "historical_input_reconstructed"]


class Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @property
    def digest(self) -> str:
        return fingerprint(self.model_dump(mode="json"))


class RatingContract(Frozen):
    schema_version: Literal["human-rating-contract-v1"] = "human-rating-contract-v1"
    rubric: Text
    rubric_version: Text
    scale: Literal["anchors", "continuous"]
    anchors: tuple[Number, ...] = ()
    threshold: Number | None
    projection_version: Text
    prompt_version: Text
    judgment_version: Text
    evidence_settings_json: str
    instructions: Text
    instruction_version: Text
    packet_version: Literal["human-packet-v1"] = "human-packet-v1"
    annotation_version: Literal["human-annotation-v1"] = "human-annotation-v1"
    dimensions: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def valid(self) -> Self:
        if self.scale == "anchors":
            if not self.anchors or tuple(sorted(set(self.anchors))) != self.anchors:
                raise ValueError("Anchors must be nonempty, unique and increasing")
        elif self.anchors:
            raise ValueError("Continuous scales must not declare anchors")
        if len(set(self.dimensions)) != len(self.dimensions):
            raise ValueError("Duplicate dimensions")
        if (
            canonical_json(json.loads(self.evidence_settings_json))
            != self.evidence_settings_json
        ):
            raise ValueError("Evidence settings must be canonical")
        return self

    def check_score(self, value: float) -> None:
        if self.scale == "anchors" and value not in self.anchors:
            raise ValueError("Human score is not a permitted rating-contract anchor")

    def passed(self, value: float) -> bool | None:
        self.check_score(value)
        return value >= self.threshold if self.threshold is not None else None

    def check_prepared(self, prepared: Preparation) -> None:
        config = json.loads(prepared.evaluator.scorer_json)
        for key in (
            "rubric",
            "rubric_version",
            "projection_version",
            "prompt_version",
            "judgment_version",
        ):
            if getattr(self, key) != config[key]:
                raise ValueError("Rating and evaluator contracts differ")
        if self.threshold != config[
            "pass_threshold"
        ] or self.evidence_settings_json != canonical_json(config["evidence_settings"]):
            raise ValueError("Rating threshold/evidence settings differ")
        if "output_validation" in config:
            output = ScoreOutputContract.model_validate_json(
                canonical_json(config["output_validation"])
            )
            if self.scale != "anchors" or self.anchors != output.anchors:
                raise ValueError("Human and judge output anchors differ")


class ObservationPolicy(Frozen):
    kind: Literal["historical", "replay", "prospective"]
    artifact_id: Identifier


class CalibrationExample(Frozen):
    """Private identity snapshot. Never passed wholesale to a reviewer renderer."""

    example_id: Identifier
    prepared: Preparation
    contract_hash: Digest
    nonce: Identifier
    binding_hash: Digest
    observation_policy: ObservationPolicy
    prior_exposure: Exposure = "unknown"
    strata: tuple[Identifier, ...] = ()

    @property
    def identity_hash(self) -> str:
        # Include full provenance and snapshot, not merely matching prose/case ID.
        return fingerprint(
            self.prepared.model_dump(mode="json", exclude={"requested_attempt_count"})
        )

    @model_validator(mode="after")
    def valid(self) -> Self:
        if self.prepared.prepared.evidence_json is None or (
            isinstance(self.prepared, PreparedReplay)
            and self.prepared.compatibility != "matching_recorded_configuration"
        ):
            raise ValueError(
                "Calibration requires reviewed evidence and recorded matching configuration"
            )
        if isinstance(self.prepared, PreparedProspectiveJudgment):
            request = self.prepared
            if (
                self.observation_policy
                != ObservationPolicy(
                    kind="prospective", artifact_id=request.selection.observation_id
                )
                or not request.selection.requires_human
                or request.selection.role != "primary"
                or request.plan.rating_contract_hash != self.contract_hash
            ):
                raise ValueError("Prospective example policy/contract differs")
        elif self.observation_policy.kind == "prospective":
            raise ValueError("Historical input cannot claim prospective origin")
        if self.binding_hash != fingerprint(
            [self.nonce, self.example_id, self.identity_hash, self.contract_hash]
        ):
            raise ValueError("Example binding differs")
        if (
            self.observation_policy.kind == "historical"
            and self.observation_policy.artifact_id != self.prepared.source.run_id
        ):
            raise ValueError("Historical observation must use the selected source")
        return self


def make_example(
    prepared: Preparation,
    contract: RatingContract,
    policy: ObservationPolicy,
    *,
    exposure: Exposure = "unknown",
    strata: tuple[str, ...] = (),
) -> CalibrationExample:
    contract.check_prepared(prepared)
    example_id, nonce = uuid4().hex, uuid4().hex
    identity = fingerprint(
        prepared.model_dump(mode="json", exclude={"requested_attempt_count"})
    )
    return CalibrationExample(
        example_id=example_id,
        prepared=prepared,
        contract_hash=contract.digest,
        nonce=nonce,
        binding_hash=fingerprint([nonce, example_id, identity, contract.digest]),
        observation_policy=policy,
        prior_exposure=exposure,
        strata=strata,
    )


class CalibrationManifest(Frozen):
    schema_version: Literal["calibration-manifest-v1"] = "calibration-manifest-v1"
    set_id: Identifier = Field(default_factory=lambda: uuid4().hex)
    policy_version: Text
    selection_rationale: Text
    coverage_gaps: tuple[str, ...]
    exclusions: tuple[str, ...] = ()
    contract: RatingContract
    examples: tuple[CalibrationExample, ...]
    presentation_order: tuple[Identifier, ...]

    @model_validator(mode="after")
    def valid(self) -> Self:
        if len({type(e.prepared) for e in self.examples}) > 1:
            raise ValueError("Mixed preparation workflows require separate manifests")
        for e in self.examples:
            if (
                isinstance(e.prepared, PreparedProspectiveJudgment)
                and e.prepared.plan.review_set_id != self.set_id
            ):
                raise ValueError(
                    "Manifest differs from reserved prospective review set"
                )
        ids = [e.example_id for e in self.examples]
        sources = [
            (
                e.prepared.source.run_id,
                e.prepared.source.case_id,
                e.prepared.source.attempt_index,
            )
            for e in self.examples
        ]
        if not ids or len(set(ids)) != len(ids) or len(set(sources)) != len(sources):
            raise ValueError("Empty or duplicate example/source identities")
        if len(self.presentation_order) != len(ids) or set(
            self.presentation_order
        ) != set(ids):
            raise ValueError("Presentation order must be an exact permutation")
        if len({e.prepared.evaluator for e in self.examples}) != 1:
            raise ValueError(
                "Different evaluator configurations require separate cohorts"
            )
        for example in self.examples:
            self.contract.check_prepared(example.prepared)
            if example.contract_hash != self.contract.digest:
                raise ValueError("Example rating contract differs")
        return self

    def example(self, example_id: str) -> CalibrationExample:
        return next(e for e in self.examples if e.example_id == example_id)

    @property
    def evidence_duplicate_groups(self) -> list[list[str]]:
        groups: dict[str | None, list[str]] = {}
        for e in self.examples:
            groups.setdefault(e.prepared.prepared.evidence_hash, []).append(
                e.example_id
            )
        return [ids for ids in groups.values() if len(ids) > 1]


class BlindReviewItem(Frozen):
    example_id: Identifier
    binding_hash: Digest
    evidence_json: str


class BlindPacket(Frozen):
    schema_version: Literal["human-packet-v1"] = "human-packet-v1"
    set_id: Identifier
    contract: RatingContract
    items: tuple[BlindReviewItem, ...]


def blind_packet(manifest: CalibrationManifest) -> BlindPacket:
    return BlindPacket(
        set_id=manifest.set_id,
        contract=manifest.contract,
        items=tuple(
            BlindReviewItem(
                example_id=e.example_id,
                binding_hash=e.binding_hash,
                evidence_json=e.prepared.prepared.evidence_json or "null",
            )
            for e in (manifest.example(i) for i in manifest.presentation_order)
        ),
    )


class AnnotationDraft(Frozen):
    schema_version: Literal["human-annotation-draft-v1"] = "human-annotation-draft-v1"
    set_id: Identifier
    example_id: Identifier
    packet_hash: Digest
    binding_hash: Digest
    annotator_id: Identifier
    score: Number | None = None
    reason: str = Field(default="", max_length=1000)
    prior_exposure: Exposure = "unknown"
    ambiguous: StrictBool | None = None
    dimensions: tuple[tuple[Identifier, DimensionValue], ...] | None = None
    supersedes: Identifier | None = None


class HumanAnnotation(Frozen):
    schema_version: Literal["human-annotation-v1"] = "human-annotation-v1"
    annotation_id: Identifier = Field(default_factory=lambda: uuid4().hex)
    set_id: Identifier
    example_id: Identifier
    packet_hash: Digest
    binding_hash: Digest
    annotator_id: Identifier
    contract: RatingContract
    contract_hash: Digest
    score: Number
    passed: StrictBool | None
    reason: Reason
    recorded_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    prior_exposure: Exposure
    ambiguous: StrictBool | None = None
    dimensions: tuple[tuple[Identifier, DimensionValue], ...] | None = None
    supersedes: Identifier | None = None
    post_disclosure: StrictBool = False

    @field_validator("reason")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Human reason must not be blank")
        return value

    @model_validator(mode="after")
    def valid(self) -> Self:
        if (
            self.contract_hash != self.contract.digest
            or self.passed is not self.contract.passed(self.score)
        ):
            raise ValueError("Annotation contract or derived verdict differs")
        keys = [k for k, _ in self.dimensions or ()]
        if len(keys) != len(set(keys)) or set(keys) - set(self.contract.dimensions):
            raise ValueError("Unknown or duplicate human dimension")
        return self


def effective_exposure(example: CalibrationExample, annotation: HumanAnnotation) -> str:
    if annotation.post_disclosure:
        return "post_disclosure"
    flags = {example.prior_exposure, annotation.prior_exposure}
    for flag in ("prior_results_seen", "recognized_during_review", "unknown"):
        if flag in flags:
            return flag
    return "not_seen"


class FrozenAnnotationSet(Frozen):
    schema_version: Literal["frozen-annotations-v1"] = "frozen-annotations-v1"
    revision_id: Identifier = Field(default_factory=lambda: uuid4().hex)
    manifest_hash: Digest
    packet_hash: Digest
    draft_hash: Digest
    annotator_id: Identifier
    frozen_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    annotations: tuple[HumanAnnotation, ...]
    active_ids: tuple[Identifier, ...]
    missing_ids: tuple[Identifier, ...]
    partial: StrictBool = False
    previous_receipt_hash: Digest | None = None

    @model_validator(mode="after")
    def valid(self) -> Self:
        by_id = {a.annotation_id: a for a in self.annotations}
        if (
            len(by_id) != len(self.annotations)
            or len(set(self.active_ids)) != len(self.active_ids)
            or set(self.active_ids) - by_id.keys()
        ):
            raise ValueError("Duplicate or unknown annotation IDs")
        if self.missing_ids and not self.partial:
            raise ValueError("Missing labels require explicit partial freeze")
        children: set[str] = set()
        for a in self.annotations:
            if a.recorded_at > self.frozen_at:
                raise ValueError("Annotation timestamp follows freeze")
            if a.annotator_id != self.annotator_id or a.packet_hash != self.packet_hash:
                raise ValueError("Annotation set/annotator differs")
            if a.supersedes:
                parent = by_id.get(a.supersedes)
                if (
                    not parent
                    or (
                        parent.set_id,
                        parent.example_id,
                        parent.binding_hash,
                        parent.contract_hash,
                    )
                    != (a.set_id, a.example_id, a.binding_hash, a.contract_hash)
                    or parent.recorded_at > a.recorded_at
                ):
                    raise ValueError(
                        "Correction crosses binding or has invalid chronology"
                    )
                if a.supersedes in children:
                    raise ValueError("Conflicting correction branches")
                children.add(a.supersedes)
            seen: set[str] = set()
            current: HumanAnnotation | None = a
            while current:
                if current.annotation_id in seen:
                    raise ValueError("Correction cycle")
                seen.add(current.annotation_id)
                current = by_id.get(current.supersedes or "")
        if set(self.active_ids) != by_id.keys() - children:
            raise ValueError("Active versions must explicitly pin every chain tip")
        active = [by_id[i] for i in self.active_ids]
        if len({a.example_id for a in active}) != len(active):
            raise ValueError("Duplicate active annotations")
        return self

    def verify_manifest(self, manifest: CalibrationManifest) -> None:
        packet = blind_packet(manifest)
        if self.manifest_hash != manifest.digest or self.packet_hash != packet.digest:
            raise ValueError("Frozen manifest/packet fingerprint differs")
        for a in self.annotations:
            if a.example_id not in manifest.presentation_order:
                raise ValueError("Unknown annotation example")
            e = manifest.example(a.example_id)
            if (a.set_id, a.binding_hash, a.contract_hash) != (
                manifest.set_id,
                e.binding_hash,
                manifest.contract.digest,
            ):
                raise ValueError("Annotation identity differs")
        active = {
            a.example_id for a in self.annotations if a.annotation_id in self.active_ids
        }
        missing = tuple(i for i in manifest.presentation_order if i not in active)
        if missing != self.missing_ids:
            raise ValueError("Missing annotation coverage differs")


class JudgeCall(Frozen):
    index: int = Field(ge=0, strict=True)
    value: Number | None
    passed: StrictBool | None
    reason: str | None
    error: (
        Literal[
            "judge_execution_error",
            "malformed_judgment",
            "input_integrity_error",
            "missing_score_unknown_cause",
        ]
        | None
    )
    observation: JudgeObservation = Field(default_factory=JudgeObservation)
    prompt_hash: Digest | None

    @model_validator(mode="after")
    def valid(self) -> Self:
        if self.value is None:
            if self.error is None or self.passed is not None or self.reason is not None:
                raise ValueError("Missing judge score needs error, not a quality value")
        elif self.error is not None or not self.reason or not self.reason.strip():
            raise ValueError("Completed score requires a reason and no error")
        return self


class JudgeObservationSet(Frozen):
    schema_version: Literal["calibration-judge-observations-v1"] = (
        "calibration-judge-observations-v1"
    )
    example_id: Identifier
    identity_hash: Digest
    contract_hash: Digest
    artifact_id: Identifier
    artifact_hash: Digest
    verification: Verification
    calls: tuple[JudgeCall, ...]

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len({c.index for c in self.calls}) != len(self.calls):
            raise ValueError("Duplicate judge attempts")
        if [c.index for c in self.calls] != sorted(c.index for c in self.calls):
            raise ValueError("Judge attempts must retain stored order")
        return self

    def verify_example(
        self, example: CalibrationExample, contract: RatingContract
    ) -> None:
        policy = example.observation_policy
        expected = (
            "frozen_request_verified"
            if policy.kind in ("replay", "prospective")
            else "historical_input_reconstructed"
        )
        if (
            self.example_id,
            self.identity_hash,
            self.contract_hash,
            self.artifact_id,
            self.verification,
        ) != (
            example.example_id,
            example.identity_hash,
            contract.digest,
            policy.artifact_id,
            expected,
        ):
            raise ValueError("Judge observation binding/selection differs")
        for call in self.calls:
            config = json.loads(example.prepared.evaluator.scorer_json)
            if call.value is not None and "output_validation" in config:
                ScoreOutputContract.model_validate_json(
                    canonical_json(config["output_validation"])
                ).check_score(call.value)
            if call.value is not None and call.passed is not (
                call.value >= contract.threshold
                if contract.threshold is not None
                else None
            ):
                raise ValueError("Judge threshold verdict differs")
            if (
                self.verification == "frozen_request_verified"
                and call.value is not None
                and call.prompt_hash != example.prepared.prepared.prompt_hash
            ):
                raise ValueError("Actual judge prompt differs")


def verify_rebuilt(example: CalibrationExample, rebuilt: Preparation) -> None:
    if type(rebuilt) is not type(example.prepared):
        raise ValueError("Preparation workflow differs")
    if rebuilt.model_dump(
        exclude={"requested_attempt_count"}
    ) != example.prepared.model_dump(exclude={"requested_attempt_count"}):
        raise ValueError(
            "Rebuilt source/dataset/response/evidence/prompt/configuration differs"
        )


def replay_observations(
    example: CalibrationExample, result: ReplayResult, rebuilt: PreparedReplay
) -> JudgeObservationSet:
    verify_rebuilt(example, rebuilt)
    result = ReplayResult.model_validate_json(result.model_dump_json())
    verify_rebuilt(example, result.input)
    if example.observation_policy != ObservationPolicy(
        kind="replay", artifact_id=result.replay_id
    ):
        raise ValueError("Unselected replay")
    return JudgeObservationSet(
        example_id=example.example_id,
        identity_hash=example.identity_hash,
        contract_hash=example.contract_hash,
        artifact_id=result.replay_id,
        artifact_hash=fingerprint(result.model_dump(mode="json")),
        verification="frozen_request_verified",
        calls=tuple(
            JudgeCall(
                index=a.index,
                value=a.score.value if a.score else None,
                passed=a.score.passed if a.score else None,
                reason=a.score.reason if a.score else None,
                error=a.error,
                observation=a.observation,
                prompt_hash=a.prompt_hash,
            )
            for a in result.attempts
        ),
    )


def prospective_observations(
    example: CalibrationExample,
    result: ProspectiveJudgmentResult,
    rebuilt: PreparedProspectiveJudgment,
    *,
    frozen_bundle: Path,
) -> JudgeObservationSet:
    """Join a reserved primary observation only after source and receipt proof."""
    verify_rebuilt(example, rebuilt)
    result = ProspectiveJudgmentResult.model_validate_json(result.model_dump_json())
    verify_rebuilt(example, result.input)
    proof = verify_freeze(result.input, frozen_bundle)
    if result.freeze != proof or example.observation_policy != ObservationPolicy(
        kind="prospective", artifact_id=result.observation_id
    ):
        raise ValueError("Unselected observation or changed freeze receipt")
    return JudgeObservationSet(
        example_id=example.example_id,
        identity_hash=example.identity_hash,
        contract_hash=example.contract_hash,
        artifact_id=result.observation_id,
        artifact_hash=result.digest,
        verification="frozen_request_verified",
        calls=tuple(
            JudgeCall(
                index=a.index,
                value=a.score.value if a.score else None,
                passed=a.score.passed if a.score else None,
                reason=a.score.reason if a.score else None,
                error=a.error,
                observation=a.observation,
                prompt_hash=a.prompt_hash,
            )
            for a in result.attempts
        ),
    )


def historical_observations(
    example: CalibrationExample, source: RunResult, rebuilt: PreparedReplay
) -> JudgeObservationSet:
    verify_rebuilt(example, rebuilt)
    if (
        fingerprint(source.model_dump(mode="json"))
        != example.prepared.source.document_hash
        or source.run_id != example.observation_policy.artifact_id
        or example.observation_policy.kind != "historical"
    ):
        raise ValueError("Unselected or changed historical source")
    case = next(c for c in source.cases if c.case_id == example.prepared.source.case_id)
    attempt = next(
        a for a in case.attempts if a.index == example.prepared.source.attempt_index
    )
    config = json.loads(example.prepared.evaluator.scorer_json)
    scores = [s for s in attempt.scores if s.name == config["name"]]
    if len(scores) > 1:
        raise ValueError("Duplicate selected historical scorer")
    score = scores[0] if scores else None
    if score:
        validate_score(score, config)
    call = JudgeCall(
        index=attempt.index,
        value=score.value if score else None,
        passed=score.passed if score else None,
        reason=score.reason if score else None,
        error=None if score else "missing_score_unknown_cause",
        observation=JudgeObservation.model_validate(score.extra.get("judge", {}))
        if score
        else JudgeObservation(),
        prompt_hash=None,
    )
    return JudgeObservationSet(
        example_id=example.example_id,
        identity_hash=example.identity_hash,
        contract_hash=example.contract_hash,
        artifact_id=source.run_id,
        artifact_hash=fingerprint(source.model_dump(mode="json")),
        verification="historical_input_reconstructed",
        calls=(call,),
    )


class IssueComparison(Frozen):
    schema_version: Literal["human-issue-review-v1"] = "human-issue-review-v1"
    annotation_hash: Digest
    observation_hash: Digest
    call_index: int = Field(ge=0, strict=True)
    relation: Literal[
        "same_issue",
        "different_issue",
        "partial_overlap",
        "no_issue_both",
        "unclear",
        "human_only_issue",
        "judge_only_issue",
    ]
    reason: Reason
    recorded_at: AwareDatetime

    @field_validator("reason")
    @classmethod
    def nonblank(cls, value: str) -> str:
        return HumanAnnotation.nonblank(value)


def _mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def compare(
    example: CalibrationExample,
    human: HumanAnnotation | None,
    judges: JudgeObservationSet | None,
    issues: tuple[IssueComparison, ...] = (),
) -> dict[str, Any]:
    calls = judges.calls if judges else ()
    replay_attempts = []
    for c in calls:
        score = (
            Score(
                name="calibration",
                kind=ScorerKind.JUDGED,
                value=c.value,
                passed=c.passed,
                reason=c.reason,
            )
            if c.value is not None
            else None
        )
        replay_attempts.append(
            ReplayAttemptResult(
                index=c.index,
                score=score,
                verdict=Verdict.ERROR
                if score is None
                else Verdict.SKIP
                if c.passed is None
                else Verdict.PASS
                if c.passed
                else Verdict.FAIL,
                error="judge_execution_error" if c.error else None,
                started_at=datetime(2000, 1, 1, tzinfo=UTC),
                duration_ms=0,
                prompt_hash=c.prompt_hash,
                input_hash=example.prepared.input_hash,
            )
        )
    distribution = variance_summary(replay_attempts)
    differences = [
        c.value - human.score if human and c.value is not None else None for c in calls
    ]
    pairs = [
        c
        for c in calls
        if human
        and human.passed is not None
        and c.value is not None
        and c.passed is not None
    ]
    values = [c.value for c in calls if c.value is not None]
    matches = sum(c.passed == human.passed for c in pairs) if human else 0
    exact = (
        sum(c.value == human.score for c in calls if c.value is not None)
        if human
        else 0
    )
    matrix = {
        "human_pass_judge_pass": 0,
        "human_pass_judge_fail": 0,
        "human_fail_judge_pass": 0,
        "human_fail_judge_fail": 0,
    }
    for c in pairs:
        assert human is not None
        matrix[
            f"human_{'pass' if human.passed else 'fail'}_judge_{'pass' if c.passed else 'fail'}"
        ] += 1
    relations = []
    for c in calls:
        issue = next(
            (
                i
                for i in issues
                if human
                and judges
                and i.annotation_hash == human.digest
                and i.observation_hash == judges.digest
                and i.call_index == c.index
            ),
            None,
        )
        relations.append(
            "same_issue_different_severity"
            if issue
            and issue.relation == "same_issue"
            and human
            and c.value != human.score
            else issue.relation
            if issue
            else "unreviewed"
        )
    return {
        "example_id": example.example_id,
        "status": "missing_human"
        if human is None
        else "missing_judge"
        if judges is None
        else "judge_error"
        if not values
        else "matched",
        "exposure": effective_exposure(example, human) if human else "unrated",
        "verification": judges.verification if judges else None,
        "human_score": human.score if human else None,
        "human_passed": human.passed if human else None,
        "distribution": distribution,
        "single_observation": len(values) == 1,
        "signed_differences": differences,
        "absolute_differences": [
            abs(d) if d is not None else None for d in differences
        ],
        "mean_signed_difference": _mean([d for d in differences if d is not None]),
        "mae": _mean([abs(d) for d in differences if d is not None]),
        "verdict_matches": matches,
        "verdict_pairs": len(pairs),
        "verdict_agreement": matches / len(pairs) if pairs else None,
        "exact_matches": exact,
        "score_pairs": len(values) if human else 0,
        "human_inside_observed_range": min(values) <= human.score <= max(values)
        if values and human
        else None,
        "confusion_matrix": matrix,
        "issue_relations": relations,
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = sum(r["verdict_pairs"] for r in rows)
    matches = sum(r["verdict_matches"] for r in rows)
    scores = sum(r["score_pairs"] for r in rows)
    exact = sum(r["exact_matches"] for r in rows)
    return {
        "example_count": len(rows),
        "matched_examples": sum(r["status"] == "matched" for r in rows),
        "mae": _mean([r["mae"] for r in rows if r["mae"] is not None]),
        "mean_signed_difference": _mean(
            [
                r["mean_signed_difference"]
                for r in rows
                if r["mean_signed_difference"] is not None
            ]
        ),
        "equal_response_verdict_agreement": _mean(
            [r["verdict_agreement"] for r in rows if r["verdict_agreement"] is not None]
        ),
        "verdict_response_agreement_sum": sum(
            r["verdict_agreement"] for r in rows if r["verdict_agreement"] is not None
        ),
        "verdict_response_denominator": sum(
            r["verdict_agreement"] is not None for r in rows
        ),
        "call_matches": matches,
        "call_pairs": pairs,
        "call_agreement": matches / pairs if pairs else None,
        "exact_matches": exact,
        "score_pairs": scores,
        "exact_score_agreement": exact / scores if scores else None,
        "confusion_matrix": {
            key: sum(r["confusion_matrix"][key] for r in rows)
            for key in (
                "human_pass_judge_pass",
                "human_pass_judge_fail",
                "human_fail_judge_pass",
                "human_fail_judge_fail",
            )
        },
    }


class CalibrationResult(Frozen):
    schema_version: Literal["human-judge-calibration-v1"] = "human-judge-calibration-v1"
    result_id: Identifier = Field(default_factory=lambda: uuid4().hex)
    status: Literal["provisional_uncalibrated"] = "provisional_uncalibrated"
    manifest: CalibrationManifest
    frozen: FrozenAnnotationSet
    observations: tuple[JudgeObservationSet, ...]
    issues: tuple[IssueComparison, ...] = ()

    @model_validator(mode="after")
    def valid(self) -> Self:
        self.frozen.verify_manifest(self.manifest)
        ids = [j.example_id for j in self.observations]
        if len(set(ids)) != len(ids) or set(ids) - set(
            self.manifest.presentation_order
        ):
            raise ValueError("Duplicate or unknown observation examples")
        for j in self.observations:
            j.verify_example(
                self.manifest.example(j.example_id), self.manifest.contract
            )
        active = {
            a.digest: a
            for a in self.frozen.annotations
            if a.annotation_id in self.frozen.active_ids
        }
        observations = {j.digest: j for j in self.observations}
        keys = []
        for issue in self.issues:
            a, issue_judges = (
                active.get(issue.annotation_hash),
                observations.get(issue.observation_hash),
            )
            if (
                not a
                or not issue_judges
                or a.example_id != issue_judges.example_id
                or issue.call_index
                not in [c.index for c in issue_judges.calls if c.value is not None]
                or issue.recorded_at < self.frozen.frozen_at
            ):
                raise ValueError("Issue review is not bound to a frozen pair")
            keys.append(
                (issue.annotation_hash, issue.observation_hash, issue.call_index)
            )
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate issue reviews")
        return self

    @property
    def summary(self) -> dict[str, Any]:
        humans = {
            a.example_id: a
            for a in self.frozen.annotations
            if a.annotation_id in self.frozen.active_ids
        }
        judges = {j.example_id: j for j in self.observations}
        rows = [
            compare(e, humans.get(e.example_id), judges.get(e.example_id), self.issues)
            for e in self.manifest.examples
        ]
        cohorts = {}
        for exposure in (
            "not_seen",
            "prior_results_seen",
            "recognized_during_review",
            "unknown",
            "post_disclosure",
            "unrated",
        ):
            for verification in (
                "frozen_request_verified",
                "historical_input_reconstructed",
                None,
            ):
                subset = [
                    r
                    for r in rows
                    if r["exposure"] == exposure and r["verification"] == verification
                ]
                if subset:
                    cohorts[f"{exposure}/{verification}"] = aggregate(subset)
        primary = [
            r
            for r in rows
            if r["exposure"] == "not_seen"
            and r["verification"] == "frozen_request_verified"
            and r["status"] == "matched"
        ]
        dimensions: dict[str, Any] = {}
        for key in self.manifest.contract.dimensions:
            dimensions[key] = {
                (value or "unassessed"): {
                    "human_count": sum(
                        dict(a.dimensions or ()).get(key) == value
                        for a in humans.values()
                    ),
                    **aggregate(
                        [
                            r
                            for r in rows
                            if r["example_id"] in humans
                            and dict(humans[r["example_id"]].dimensions or ()).get(key)
                            == value
                        ]
                    ),
                }
                for value in (
                    "adequate",
                    "minor_issue",
                    "material_issue",
                    "not_applicable",
                    None,
                )
            }
        families = sorted({s for e in self.manifest.examples for s in e.strata})
        return {
            "status": self.status,
            "interpretation": "Exploratory human–judge agreement evidence. Numeric distances describe the rubric scale, not calibrated prediction error. Five calls or this selected pilot do not establish a general variance rate or statistical reliability estimate.",
            "weighting": "equal fixed response; call-weighted confusion separately",
            "planned_examples": len(rows),
            "frozen_humans": len(humans),
            "missing_humans": len(self.frozen.missing_ids),
            "missing_judges": len(rows) - len(judges),
            "completed_judge_scores": sum(
                r["distribution"]["completed_score_count"] for r in rows
            ),
            "judge_errors": sum(r["distribution"]["error_count"] for r in rows),
            "distinct_cases": len(
                {e.prepared.source.case_id for e in self.manifest.examples}
            ),
            "observed_models": sorted(
                {
                    c.observation.observed_model
                    for j in self.observations
                    for c in j.calls
                    if c.observation.observed_model
                }
            ),
            "unknown_observed_models": sum(
                c.observation.observed_model is None
                for j in self.observations
                for c in j.calls
            ),
            "primary_blind_verified": aggregate(primary),
            "primary_note": "no eligible blind ratings"
            if not primary
            else "Declared unexposed, frozen-request-verified ratings only",
            "cohorts": cohorts,
            "exploratory_all": aggregate(rows),
            "rows": rows,
            "human_dimensions": dimensions,
            "case_families_nonadditive": {
                s: aggregate(
                    [
                        r
                        for r in rows
                        if s in self.manifest.example(r["example_id"]).strata
                    ]
                )
                for s in families
            },
            "numeric_disagreements": [
                r["example_id"] for r in rows if r["mae"] is not None and r["mae"] > 0
            ],
            "threshold_disagreements": [
                r["example_id"]
                for r in rows
                if r["verdict_matches"] < r["verdict_pairs"]
            ],
        }
