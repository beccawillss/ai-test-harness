"""Study v1 integration contract. No case bodies, environment reads or live clients.

All application vocabulary belongs here and in the independently pinned matrix.
Definitions, capture evidence and delayed judgments remain distinct artifacts.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Any, Literal, Protocol, Self
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import AwareDatetime, Field, field_validator, model_validator

from harness.core.calibration import (
    CalibrationManifest,
    ObservationPolicy,
    RatingContract,
    make_example,
)
from harness.core.case_fingerprints import resolved_case_payload, validate_json_data
from harness.core.dataset import LoadedDataset, hash_cases, load_cases, load_dataset
from harness.core.fingerprints import canonical_json, fingerprint
from harness.core.models import RunResult, TestCase
from harness.core.prospective import (
    Digest,
    Frozen,
    ProspectiveJudge,
    ProspectiveJudgingPlan,
    ProspectiveJudgmentResult,
    ProspectiveSelection,
    SourceLoader,
    bind_source,
    execute_prospective,
    prepare_prospective,
    strict_json,
    verify_prospective,
)
from harness.core.prospective_io import PreparedBundle, ProspectiveStore
from harness.core.replay import (
    EvaluatorConfiguration,
    JudgeConfiguration,
    JudgeTimeouts,
    _verify_v2_definitions,
)
from harness.core.runner import _scorer_snapshot
from harness.core.selection import CaseSelection, select_cases
from harness.core.suites import (
    EvaluationProfile,
    ResolvedSuite,
    _profile_snapshot,
    execute_suite,
    resolve_suite,
)
from harness.judges.base import JudgeReply
from harness.packs import salesagent_semantic as semantic
from harness.packs.salesagent_rules import StudyLabelAssertionsScorer, validate_rules
from harness.scorers.output_contracts import ScoreOutputContract
from harness.scorers.rubric_judge import RubricJudgeScorer
from harness.targets.salesagent import (
    ADAPTER_VERSION,
    EVIDENCE_VERSION,
    WARMTH_ADAPTER_VERSION,
    WARMTH_EVIDENCE_VERSION,
    adapter_version_for,
    validate_input,
)

METHODOLOGY_COMMIT = "5995e24d59d3e5795df0429a940f01a638974dd3"
METHODOLOGY_HASH = "5de0400bc3de7d910902d72b2d7199aab81d0b553e733faabfe0f4da91fa9ace"
MATRIX_BYTES = "c0e15099ab3bccf54b7528a20d11fddbff71c5dccec89ab4ea9022a6ba9924b1"
CAPTURE_PROFILE = "salesagent-study-v1-capture"
SEMANTIC_PROFILE = "salesagent-study-v1-semantic"
REFERENCE_CONTRACT = "salesagent-study-v1-references-v3"
CAPABILITIES = frozenset({"structured", "metadata", "trajectory"})
ANCHORS = ScoreOutputContract(
    id="salesagent-semantic-anchors-v1", anchors=(0.0, 0.3, 0.6, 0.8, 1.0)
)
Text = Annotated[str, Field(min_length=1, max_length=500)]
Commit = Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]


def matrix_contract() -> dict[str, Any]:
    raw = (
        files("harness.packs")
        .joinpath("data/salesagent-study-v1-matrix.json")
        .read_bytes()
    )
    if hashlib.sha256(raw).hexdigest() != MATRIX_BYTES:
        raise ValueError("Reviewed Study v1 matrix resource changed")
    return strict_json(raw)  # fresh detached data, never derived from candidate cases


def _no_judge(_: str) -> str:
    raise RuntimeError("Pure study preparation cannot invoke a judge")


def validate_reference(case: TestCase) -> None:
    validate_rules(case)
    semantic.semantic_expectations(case.reference)


def capture_profile() -> tuple[StudyLabelAssertionsScorer, EvaluationProfile]:
    scorer = StudyLabelAssertionsScorer(requires=CAPABILITIES)
    return scorer, EvaluationProfile(
        id=CAPTURE_PROFILE,
        taxonomy_evidence="excluded",
        scorer_configuration={scorer.name: _scorer_snapshot(scorer)},
        reference_contract=REFERENCE_CONTRACT,
        case_payload_snapshot="full",
        requires_full_payload=True,
        case_extra_keys=[],
        dataset_extra_keys=[],
    )


def evidence_version_for_projection(projection_version: str) -> str:
    """The two reviewed Study bindings; never infer an upgrade from evidence."""
    if projection_version == semantic.PRODUCT_PROJECTION_VERSION:
        return EVIDENCE_VERSION
    if projection_version == semantic.WARMTH_PROJECTION_VERSION:
        return WARMTH_EVIDENCE_VERSION
    raise ValueError("Unsupported Study semantic projection version")


def semantic_profile(
    judge: JudgeConfiguration,
    judge_fn: Callable[[str], str | JudgeReply] = _no_judge,
    *,
    projection_version: str = semantic.PRODUCT_PROJECTION_VERSION,
) -> tuple[RubricJudgeScorer, EvaluationProfile]:
    evidence_version_for_projection(projection_version)
    scorer = semantic.make_scorer(
        judge_fn, judge.model, projection_version=projection_version
    )
    scorer.output_validation = ANCHORS
    return scorer, EvaluationProfile(
        id=SEMANTIC_PROFILE,
        taxonomy_evidence="excluded",
        scorer_configuration={scorer.name: scorer.preparation_configuration},
        judge_configurations={scorer.name: judge},
        reference_contract=REFERENCE_CONTRACT,
        case_payload_snapshot="full",
        requires_full_payload=True,
        case_extra_keys=[],
        dataset_extra_keys=[],
    )


def rating_contract(
    *, projection_version: str = semantic.PRODUCT_PROJECTION_VERSION
) -> RatingContract:
    evidence_version_for_projection(projection_version)
    scorer = semantic.make_scorer(
        _no_judge,
        "preparation-only",
        projection_version=projection_version,
    )
    return RatingContract(
        rubric=semantic.RUBRIC,
        rubric_version=semantic.RUBRIC_VERSION,
        scale="anchors",
        anchors=ANCHORS.anchors,
        threshold=0.7,
        projection_version=projection_version,
        prompt_version=semantic.PROMPT_VERSION,
        judgment_version=semantic.JUDGMENT_VERSION,
        evidence_settings_json=canonical_json(scorer.evidence_settings),
        instructions="Rate the complete fixed conversation independently using the rubric anchors. Do not consult judge results. Declare any prior exposure truthfully.",
        instruction_version="salesagent-study-v1-human-v1",
        dimensions=(
            "relevance_helpfulness",
            "clarity_actionability",
            "commerce_agreement",
            "conversation_coherence",
        ),
    )


class SuiteBinding(Frozen):
    id: str
    fingerprint: Digest
    selection_json: str
    case_ids: tuple[str, ...]
    attempts: int = Field(gt=0)
    target_calls: int = Field(gt=0)
    max_http_requests: int = Field(gt=0)


class StudyValidation(Frozen):
    schema_version: Literal["salesagent-study-validation-v1"] = (
        "salesagent-study-validation-v1"
    )
    methodology_hash: Digest
    matrix_hash: Digest
    descriptor_hash: Digest
    full_case_hash: Digest
    suites: tuple[SuiteBinding, ...]
    human_ids: tuple[str, ...]
    totals_json: str


@dataclass(frozen=True)
class StudyDefinition:
    dataset: LoadedDataset
    suites: tuple[ResolvedSuite, ...]
    validation: StudyValidation


def validate_study(
    dataset: LoadedDataset, suites: Sequence[ResolvedSuite]
) -> StudyValidation:
    """Validate every row before selection, against the separately pinned matrix."""
    dataset = LoadedDataset.model_validate(dataset.model_dump(mode="python"))
    matrix = matrix_contract()
    descriptor = dataset.descriptor
    if (
        descriptor.id,
        descriptor.version,
        descriptor.schema_version,
        descriptor.fingerprint_scheme,
    ) != (
        matrix["dataset_id"],
        matrix["dataset_version"],
        "dataset-descriptor-v1",
        "dataset-cases-v2",
    ):
        raise ValueError("Study descriptor identity/version/scheme differs")
    expected = {r["id"]: r for r in matrix["cases"]}
    if len(dataset.cases) != 50 or {c.id for c in dataset.cases} != expected.keys():
        raise ValueError("Study requires the exact 50 unique approved IDs")
    # Literal freshness only; substantive holdout review remains a manual freeze step.
    historical = load_cases(semantic.DATASET) + load_cases(
        semantic.DATASET.with_name("baseline.jsonl")
    )
    historical_ids = {c.id for c in historical}
    historical_turns = {t for c in historical for t in validate_input(c.input)}
    totals: dict[str, Counter[str]] = {d: Counter() for d in matrix["totals"]}
    for case in dataset.cases:
        try:
            validate_reference(case)
            turns = validate_input(case.input)
            if case.id in historical_ids or any(t in historical_turns for t in turns):
                raise ValueError("Literal historical ID or shopper wording reuse")
            if not set(case.tags) <= set(matrix["tags"]):
                raise ValueError("Unapproved or experimental-membership tag")
            row = expected[case.id]
            for dimension in ("category", "risk"):
                if getattr(case, dimension) != row[dimension]:
                    raise ValueError(f"Per-ID {dimension} differs")
            for dimension in ("journey", "difficulty"):
                tags = [t for t in case.tags if t.startswith(dimension + ":")]
                if tags != [dimension + ":" + row[dimension]]:
                    raise ValueError(f"Per-ID {dimension} tag differs")
            if (len(turns) == 1) != (row["journey"] == "single-turn"):
                raise ValueError("Journey does not match shopper turn count")
            for d, counts in totals.items():
                counts[row[d]] += 1
        except ValueError as exc:
            raise ValueError(f"{dataset.cases_path}: case {case.id}: {exc}") from None
    if {d: dict(counts) for d, counts in totals.items()} != matrix["totals"]:
        raise ValueError("Study aggregate matrix counts differ")
    if len(suites) != 6 or {s.suite.id for s in suites} != matrix["suites"].keys():
        raise ValueError("Exactly the six approved suites are required")
    bindings = []
    for resolved in sorted(suites, key=lambda s: s.suite.id):
        # Reopen local bindings to reject stale files and mutable nested snapshots.
        actual = resolve_suite(resolved.suite_path)
        if (
            actual != resolved
            or actual.dataset.descriptor_hash != dataset.descriptor_hash
            or actual.dataset.full_dataset_hash != dataset.full_dataset_hash
            or actual.dataset.descriptor_path != dataset.descriptor_path
        ):
            raise ValueError("Suite binding or dataset snapshot differs")
        authored = resolved.suite
        approved = matrix["suites"][authored.id]
        selection = CaseSelection.model_validate(approved["selection"])
        if (
            authored.selection != selection
            or authored.attempts != approved["attempts"]
            or authored.evaluation_profile != CAPTURE_PROFILE
        ):
            raise ValueError(
                f"Suite {authored.id}: expression, attempts or capture profile differs"
            )
        selected = select_cases(dataset.cases, selection)
        bindings.append(
            SuiteBinding(
                id=authored.id,
                fingerprint=resolved.suite_hash,
                selection_json=canonical_json(selection.model_dump(mode="json")),
                case_ids=tuple(c.id for c in selected),
                attempts=authored.attempts,
                target_calls=len(selected) * authored.attempts,
                max_http_requests=2
                * authored.attempts
                * sum(len(validate_input(c.input)) for c in selected),
            )
        )
    human_ids = tuple(
        c.id
        for c in select_cases(
            dataset.cases, CaseSelection.model_validate(matrix["human"])
        )
    )
    variance = set(matrix["suites"]["variance"]["selection"]["case_ids"])
    smoke = set(matrix["suites"]["smoke"]["selection"]["case_ids"])
    if len(human_ids) != 12 or set(human_ids) & (variance | smoke):
        raise ValueError("Human roster or experimental disjointness differs")
    return StudyValidation(
        methodology_hash=METHODOLOGY_HASH,
        matrix_hash=fingerprint(matrix),
        descriptor_hash=dataset.descriptor_hash,
        full_case_hash=dataset.full_dataset_hash,
        suites=tuple(bindings),
        human_ids=human_ids,
        totals_json=canonical_json(matrix["totals"]),
    )


def load_study(descriptor: Path, suite_paths: Sequence[Path]) -> StudyDefinition:
    dataset = load_dataset(descriptor)
    suites = tuple(resolve_suite(p) for p in suite_paths)
    return StudyDefinition(dataset, suites, validate_study(dataset, suites))


class Revision(Frozen):
    revision: Text
    sha256: Digest

    @field_validator("revision")
    @classmethod
    def known_revision(cls, value: str) -> str:
        if (
            not value.strip()
            or value != value.strip()
            or value.casefold() in {"unknown", "unavailable", "not_exposed"}
        ):
            raise ValueError("An explicit reviewed fixture revision is required")
        return value


class GenerationParameters(Frozen):
    status: Literal["recorded", "not_exposed"]
    temperature: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    top_p: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    max_output_tokens: int | None = Field(default=None, gt=0)
    seed: int | None = None
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None = None

    @model_validator(mode="after")
    def valid(self) -> Self:
        if self.status == "not_exposed" and any(
            v is not None for k, v in self.model_dump().items() if k != "status"
        ):
            raise ValueError("Unexposed generation settings cannot claim values")
        return self


class StateConfiguration(Frozen):
    status: Literal["recorded", "not_exposed"]
    max_history_turns: int | None = Field(default=None, gt=0)
    session_ttl_seconds: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def valid(self) -> Self:
        if self.status == "not_exposed" and (
            self.max_history_turns is not None or self.session_ttl_seconds is not None
        ):
            raise ValueError("Unexposed state settings cannot claim values")
        return self


class RequestedTarget(Frozen):
    base_url: str | None = None
    deployed_target_commit_sha: Commit | None = None
    provider: Text | None = None
    model: Text | None = None
    reviewed_generation_parameters: GenerationParameters | None = None
    prompt_version: Text | None = None
    prompt_digest: Digest | None = None
    catalogue: Revision | None = None
    promotions: Revision | None = None
    adapter_version: Text | None = None
    evidence_schema_version: Text | None = None
    http_contract_version: Text | None = None
    capabilities: tuple[str, ...] = ()
    session_policy: Literal["isolated_case_attempt"] | None = None
    reviewed_state_configuration: StateConfiguration | None = None
    timeouts: JudgeTimeouts | None = None
    evaluation_traces_enabled: bool | None = None

    @field_validator("base_url")
    @classmethod
    def endpoint(cls, value: str | None) -> str | None:
        if value is not None:
            url = urlsplit(value)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
                or value.endswith("/")
            ):
                raise ValueError(
                    "Target URL must be canonical HTTP(S), without credentials/query/fragment"
                )
        return value

    @field_validator(
        "provider",
        "model",
        "prompt_version",
        "adapter_version",
        "evidence_schema_version",
        "http_contract_version",
    )
    @classmethod
    def identity(cls, value: str | None) -> str | None:
        if value is not None and (
            not value.strip()
            or value != value.strip()
            or value.casefold() in {"unknown", "not_exposed", "unavailable"}
        ):
            raise ValueError("Freeze identities require nonblank exact values")
        return value


class DeploymentVerification(Frozen):
    operator_statement: Text
    verified_at: AwareDatetime
    deployment_reference: Text

    @field_validator("operator_statement", "deployment_reference")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Deployment verification must not be blank")
        return value


class StudyTargetFreeze(Frozen):
    schema_version: Literal["salesagent-study-target-freeze-v1"] = (
        "salesagent-study-target-freeze-v1"
    )
    requested: RequestedTarget
    harness_revision: Commit | None = None
    verification: DeploymentVerification | None = None

    @property
    def missing_facts(self) -> tuple[str, ...]:
        r = self.requested
        missing = [
            f"requested.{k}"
            for k, v in r.model_dump().items()
            if v is None and k not in {"prompt_version", "prompt_digest"}
        ]
        if not r.prompt_version and not r.prompt_digest:
            missing.append("requested.prompt_version_or_digest")
        if r.evaluation_traces_enabled is not True:
            missing.append("requested.evaluation_traces_enabled:true")
        if set(r.capabilities) != CAPABILITIES or len(r.capabilities) != len(
            CAPABILITIES
        ):
            missing.append("requested.capabilities")
        for k, supported in (
            ("adapter_version", {ADAPTER_VERSION, WARMTH_ADAPTER_VERSION}),
            ("evidence_schema_version", {EVIDENCE_VERSION, WARMTH_EVIDENCE_VERSION}),
            ("http_contract_version", {"1.0.0"}),
        ):
            if getattr(r, k) is not None and getattr(r, k) not in supported:
                missing.append(f"requested.{k}:unsupported")
        if (
            r.adapter_version in {ADAPTER_VERSION, WARMTH_ADAPTER_VERSION}
            and r.evidence_schema_version in {EVIDENCE_VERSION, WARMTH_EVIDENCE_VERSION}
            and adapter_version_for(r.evidence_schema_version) != r.adapter_version
        ):
            missing.append("requested.adapter_evidence_pair:unsupported")
        if self.harness_revision is None:
            missing.append("harness_revision")
        if self.verification is None:
            missing.append("verification")
        return tuple(missing)

    def require_complete(self) -> None:
        if self.missing_facts:
            raise ValueError(
                "Missing/unsupported target freeze facts: "
                + ", ".join(self.missing_facts)
            )


class StudyExecutionContract(Frozen):
    schema_version: Literal["salesagent-study-execution-v1"] = (
        "salesagent-study-execution-v1"
    )
    validation: StudyValidation
    capture_profile_json: str
    semantic_profile_json: str
    evaluator: EvaluatorConfiguration
    output_contract: ScoreOutputContract
    rating: RatingContract
    selectors_json: str
    metadata_policy_json: str
    case_payload_snapshot: Literal["full"]
    primary_judge_calls: Literal[50]
    diagnostic_judge_calls: int = Field(ge=0)
    target: StudyTargetFreeze
    author_review: Text
    reviewed_at: AwareDatetime

    @model_validator(mode="after")
    def valid(self) -> Self:
        self.target.require_complete()
        matrix = matrix_contract()
        if (
            self.validation.methodology_hash != METHODOLOGY_HASH
            or self.validation.matrix_hash != fingerprint(matrix)
        ):
            raise ValueError("Execution methodology/matrix differs")
        _, capture = capture_profile()
        version = self.rating.projection_version
        evidence_version = evidence_version_for_projection(version)
        if (
            self.target.requested.evidence_schema_version != evidence_version
            or self.target.requested.adapter_version
            != adapter_version_for(evidence_version)
        ):
            raise ValueError("Execution evaluator/target evidence versions differ")
        scoring, profile = semantic_profile(
            self.evaluator.judge, projection_version=version
        )
        if (
            self.capture_profile_json != canonical_json(capture.model_dump(mode="json"))
            or self.semantic_profile_json
            != canonical_json(profile.model_dump(mode="json"))
            or self.evaluator.scorer_json
            != canonical_json(scoring.preparation_configuration)
            or self.output_contract != ANCHORS
            or self.rating != rating_contract(projection_version=version)
        ):
            raise ValueError("Execution evaluator/profile/anchors differ")
        selectors = {
            "human": matrix["human"],
            "variance": matrix["suites"]["variance"]["selection"],
            "smoke": matrix["suites"]["smoke"]["selection"],
        }
        if self.selectors_json != canonical_json(
            selectors
        ) or self.metadata_policy_json != canonical_json(
            {"case_extra_keys": [], "dataset_extra_keys": []}
        ):
            raise ValueError("Execution selectors/metadata policy differ")
        if not self.author_review.strip():
            raise ValueError("Manual author review is required")
        return self


def freeze_execution(
    study: StudyDefinition,
    target: StudyTargetFreeze,
    judge: JudgeConfiguration,
    *,
    diagnostic_judge_calls: int,
    author_review: str,
    reviewed_at: datetime,
    projection_version: str = semantic.PRODUCT_PROJECTION_VERSION,
) -> StudyExecutionContract:
    validation = validate_study(study.dataset, study.suites)
    if validation != study.validation:
        raise ValueError("Study changed after validation")
    matrix = matrix_contract()
    scoring, profile = semantic_profile(judge, projection_version=projection_version)
    return StudyExecutionContract(
        validation=validation,
        capture_profile_json=canonical_json(
            capture_profile()[1].model_dump(mode="json")
        ),
        semantic_profile_json=canonical_json(profile.model_dump(mode="json")),
        evaluator=EvaluatorConfiguration(
            scorer_json=canonical_json(scoring.preparation_configuration), judge=judge
        ),
        output_contract=ANCHORS,
        rating=rating_contract(projection_version=projection_version),
        selectors_json=canonical_json(
            {
                "human": matrix["human"],
                "variance": matrix["suites"]["variance"]["selection"],
                "smoke": matrix["suites"]["smoke"]["selection"],
            }
        ),
        metadata_policy_json=canonical_json(
            {"case_extra_keys": [], "dataset_extra_keys": []}
        ),
        case_payload_snapshot="full",
        primary_judge_calls=50,
        diagnostic_judge_calls=diagnostic_judge_calls,
        target=target,
        author_review=author_review,
        reviewed_at=reviewed_at,
    )


def verify_contract(
    study: StudyDefinition, contract: StudyExecutionContract
) -> StudyExecutionContract:
    contract = StudyExecutionContract.model_validate_json(contract.model_dump_json())
    if validate_study(study.dataset, study.suites) != contract.validation:
        raise ValueError("Study no longer matches frozen execution contract")
    return contract


class StudyTarget(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def capabilities(self) -> frozenset[str]: ...
    @property
    def configuration(self) -> dict[str, Any]: ...
    def invoke(self, case: TestCase): ...
    def close(self) -> None: ...


def capture(
    study: StudyDefinition,
    contract: StudyExecutionContract,
    suite_id: str,
    target_factory: Callable[[], StudyTarget],
) -> RunResult:
    """Uniform deterministic capture; complete study validation precedes construction."""
    contract = verify_contract(study, contract)
    assert contract.target.verification is not None
    if max(
        contract.reviewed_at, contract.target.verification.verified_at
    ) > datetime.now(UTC):
        raise ValueError("Study review/target verification must precede capture")
    matches = [s for s in study.suites if s.suite.id == suite_id]
    if len(matches) != 1:
        raise ValueError("Unknown study suite")
    resolved = matches[0]
    context = {
        "execution_contract": contract.model_dump(mode="json"),
        "execution_contract_hash": contract.digest,
        "suite_id": suite_id,
        "stage": "deterministic_capture",
        "final_study_outcome": False,
    }
    validate_json_data(context)
    target = target_factory()
    r = contract.target.requested
    expected = {
        "base_url": r.base_url,
        "target_revision": r.deployed_target_commit_sha,
        "adapter_version": r.adapter_version,
        "evidence_schema_version": r.evidence_schema_version,
        "http_contract_version": r.http_contract_version,
        "timeouts": r.timeouts.model_dump(mode="json") if r.timeouts else None,
    }
    try:
        if (
            target.name != "salesagent"
            or set(target.capabilities) != set(r.capabilities)
            or target.configuration != expected
        ):
            raise ValueError(
                "Actual target adapter differs from frozen requested configuration"
            )
    except Exception:
        target.close()
        raise
    scorer, profile = capture_profile()
    # execute_suite/run own close-on-completion; source context was copied before calls.
    result = execute_suite(
        resolved,
        target,
        [scorer],
        profile=profile,
        validate_reference=validate_reference,
    )
    result.pack_name = CAPTURE_PROFILE
    result.config_snapshot["study"] = context
    return result


def verify_capture(
    study: StudyDefinition,
    contract: StudyExecutionContract,
    source: RunResult,
    document_hash: str,
) -> str:
    verify_contract(study, contract)
    if fingerprint(source.model_dump(mode="json")) != document_hash:
        raise ValueError("Stored capture document differs")
    assert contract.target.verification is not None
    if source.started_at < max(
        contract.reviewed_at, contract.target.verification.verified_at
    ):
        raise ValueError("Capture predates the frozen study review")
    context = source.config_snapshot.get("study", {})
    suite_id = context.get("suite_id")
    matches = [s for s in contract.validation.suites if s.id == suite_id]
    if len(matches) != 1:
        raise ValueError("Capture has no approved study suite")
    binding = matches[0]
    if context != {
        "execution_contract": contract.model_dump(mode="json"),
        "execution_contract_hash": contract.digest,
        "suite_id": suite_id,
        "stage": "deterministic_capture",
        "final_study_outcome": False,
    }:
        raise ValueError("Capture execution contract differs")
    snapshot = source.config_snapshot
    if (
        source.pack_name != CAPTURE_PROFILE
        or source.target_name != "salesagent"
        or snapshot.get("suite_hash") != binding.fingerprint
        or snapshot.get("dataset_descriptor_hash")
        != contract.validation.descriptor_hash
        or snapshot.get("full_dataset_hash") != contract.validation.full_case_hash
        or snapshot.get("case_payload_snapshot") != "full"
        or snapshot.get("metadata_snapshot_policy")
        != strict_json(contract.metadata_policy_json)
        or [c.case_id for c in source.cases] != list(binding.case_ids)
    ):
        raise ValueError("Capture profile/dataset/selection differs")
    expected_scorer, expected_profile = capture_profile()
    _verify_v2_definitions(source, study.dataset.cases)
    selected = [case for case in study.dataset.cases if case.id in binding.case_ids]
    if source.dataset_hash != hash_cases(
        selected, scheme="dataset-cases-v2"
    ) or snapshot.get("resolved_cases") != [
        resolved_case_payload(case, scheme="dataset-cases-v2") for case in selected
    ]:
        raise ValueError("Capture definition payload/subset fingerprint differs")
    if (
        snapshot.get("evaluation_profile")
        != _profile_snapshot(expected_profile, [expected_scorer])
        or snapshot.get("scorers") != [_scorer_snapshot(capture_profile()[0])]
        or snapshot.get("attempts") != binding.attempts
        or snapshot.get("dataset_fingerprint_scheme") != "dataset-cases-v2"
        or snapshot.get("overrides") != {}
    ):
        raise ValueError("Capture scorers or attempt policy differs")
    for case in source.cases:
        if any(
            len(a.scores) > 1
            or any(
                score.name != "structured_assertions"
                or score.kind.value != "deterministic"
                for score in a.scores
            )
            for a in case.attempts
        ):
            raise ValueError("Capture contains an unexpected scorer result")
        if [a.index for a in case.attempts] != list(range(binding.attempts)):
            raise ValueError("Capture attempt identity differs")
    return str(suite_id)


class MissingSource(Frozen):
    case_id: str
    attempt_index: int
    reason: Literal["target_response_unavailable"] = "target_response_unavailable"


class StudyPreparation(Frozen):
    schema_version: Literal["salesagent-study-preparation-v1"] = (
        "salesagent-study-preparation-v1"
    )
    execution_contract_hash: Digest
    source_document_hash: Digest
    mode: Literal["primary", "variance_diagnostic"]
    bundle: PreparedBundle | None
    unavailable: tuple[MissingSource, ...]


def _primary_ids(
    contract_hash: str, source_hash: str, case_id: str, attempt_index: int
) -> tuple[str, str]:
    binding = [contract_hash, source_hash, case_id, attempt_index]
    return fingerprint(["study-primary-request-v1", binding]), fingerprint(
        ["study-primary-observation-v1", binding]
    )


def prepare_primary(
    study: StudyDefinition,
    contract: StudyExecutionContract,
    source: RunResult,
    *,
    database_locator: str,
    document_hash: str,
    plan_id: str,
    review_set_id: str,
) -> StudyPreparation:
    if verify_capture(study, contract, source, document_hash) != "full":
        raise ValueError("Primary preparation requires the full capture")
    protected = set(contract.validation.human_ids)
    missing = tuple(
        MissingSource(case_id=c.case_id, attempt_index=a.index)
        for c in source.cases
        for a in c.attempts
        if a.response is None
    )
    if any(m.case_id in protected for m in missing):
        raise ValueError(
            "Methodological block: a protected source has no complete response; the 12-case roster cannot be reduced or substituted"
        )
    selections = []
    for c in source.cases:
        a = c.attempts[0]
        if a.response is None:
            continue
        provenance = bind_source(
            source,
            study.dataset.cases,
            database_locator=database_locator,
            case_id=c.case_id,
            source_attempt=a.index,
            source_document_hash=document_hash,
        )
        request_id, observation_id = _primary_ids(
            contract.digest, document_hash, c.case_id, a.index
        )
        selections.append(
            ProspectiveSelection(
                request_id=request_id,
                observation_id=observation_id,
                source=provenance,
                attempts=1,
                role="primary",
                requires_human=c.case_id in protected,
            )
        )
    scoring, _ = semantic_profile(
        contract.evaluator.judge, projection_version=contract.rating.projection_version
    )
    plan = ProspectiveJudgingPlan(
        plan_id=plan_id,
        selections=tuple(selections),
        evaluator=contract.evaluator,
        taxonomy_evidence="excluded",
        sharing_policy="evaluation_data",
        review_set_id=review_set_id,
        rating_contract_hash=contract.rating.digest,
    )
    requests = tuple(
        prepare_prospective(
            plan,
            source,
            study.dataset.cases,
            scoring,
            contract.evaluator.judge,
            request_id=s.request_id,
            source_document_hash=document_hash,
        )
        for s in selections
    )
    return StudyPreparation(
        execution_contract_hash=contract.digest,
        source_document_hash=document_hash,
        mode="primary",
        bundle=PreparedBundle(plan=plan, requests=requests),
        unavailable=missing,
    )


def prepare_variance_diagnostic(
    study: StudyDefinition,
    contract: StudyExecutionContract,
    source: RunResult,
    *,
    database_locator: str,
    document_hash: str,
    case_id: str,
    attempt_index: int,
    attempts: int,
    plan_id: str,
) -> StudyPreparation:
    if verify_capture(study, contract, source, document_hash) != "variance":
        raise ValueError("Variance diagnostic requires the approved variance capture")
    if (
        type(attempts) is not int
        or not 1 <= attempts <= contract.diagnostic_judge_calls
    ):
        raise ValueError("Diagnostic judge call budget exceeded")
    provenance = bind_source(
        source,
        study.dataset.cases,
        database_locator=database_locator,
        case_id=case_id,
        source_attempt=attempt_index,
        source_document_hash=document_hash,
    )
    selection = ProspectiveSelection(
        request_id=uuid4().hex,
        observation_id=uuid4().hex,
        source=provenance,
        attempts=attempts,
        role="diagnostic",
        requires_human=False,
    )
    plan = ProspectiveJudgingPlan(
        plan_id=plan_id,
        selections=(selection,),
        evaluator=contract.evaluator,
        taxonomy_evidence="excluded",
        sharing_policy="evaluation_data",
    )
    scoring, _ = semantic_profile(
        contract.evaluator.judge, projection_version=contract.rating.projection_version
    )
    request = prepare_prospective(
        plan,
        source,
        study.dataset.cases,
        scoring,
        contract.evaluator.judge,
        request_id=selection.request_id,
        source_document_hash=document_hash,
    )
    return StudyPreparation(
        execution_contract_hash=contract.digest,
        source_document_hash=document_hash,
        mode="variance_diagnostic",
        bundle=PreparedBundle(plan=plan, requests=(request,)),
        unavailable=(),
    )


def verify_preparation(
    study: StudyDefinition,
    contract: StudyExecutionContract,
    preparation: StudyPreparation,
    source_loader: SourceLoader,
) -> None:
    verify_contract(study, contract)
    preparation = StudyPreparation.model_validate_json(preparation.model_dump_json())
    if (
        preparation.execution_contract_hash != contract.digest
        or preparation.bundle is None
    ):
        raise ValueError("Study preparation binding missing or changed")
    bundle = preparation.bundle
    plan = bundle.plan
    if (
        plan.evaluator != contract.evaluator
        or plan.taxonomy_evidence != "excluded"
        or any(
            s.source.document_hash != preparation.source_document_hash
            for s in plan.selections
        )
    ):
        raise ValueError("Study prospective evaluator/source differs")
    first = bundle.requests[0]
    source, _, document_hash = source_loader(first.source)
    suite_id = verify_capture(study, contract, source, document_hash)
    scorer, _ = semantic_profile(
        contract.evaluator.judge, projection_version=contract.rating.projection_version
    )
    if preparation.mode == "primary":
        if (
            suite_id != "full"
            or plan.rating_contract_hash != contract.rating.digest
            or not plan.review_set_id
        ):
            raise ValueError("Primary preparation review contract differs")
        expected = [
            (c.case_id, a.index)
            for c in source.cases
            for a in c.attempts
            if a.response is not None
        ]
        actual = [(s.source.case_id, s.source.attempt_index) for s in plan.selections]
        missing = tuple(
            MissingSource(case_id=c.case_id, attempt_index=a.index)
            for c in source.cases
            for a in c.attempts
            if a.response is None
        )
        if (
            actual != expected
            or missing != preparation.unavailable
            or len(actual) > contract.primary_judge_calls
        ):
            raise ValueError("Primary preparation roster/availability differs")
        for s in plan.selections:
            if (s.request_id, s.observation_id) != _primary_ids(
                contract.digest, document_hash, s.source.case_id, s.source.attempt_index
            ):
                raise ValueError("Primary request/observation reservation differs")
            if (
                s.requires_human != (s.source.case_id in contract.validation.human_ids)
                or s.role != "primary"
                or s.attempts != 1
                or s.source.run_id != source.run_id
            ):
                raise ValueError("Primary protected selection/attempt differs")
        if {s.source.case_id for s in plan.selections if s.requires_human} != set(
            contract.validation.human_ids
        ):
            raise ValueError("Incomplete protected roster")
    else:
        if (
            suite_id != "variance"
            or preparation.unavailable
            or len(plan.selections) != 1
        ):
            raise ValueError("Invalid variance diagnostic")
        s = plan.selections[0]
        if (
            s.requires_human
            or s.role != "diagnostic"
            or s.attempts > contract.diagnostic_judge_calls
            or s.source.run_id != source.run_id
        ):
            raise ValueError("Variance diagnostic policy/budget differs")
    for request in bundle.requests:
        verify_prospective(request, source_loader, scorer)


def human_manifest(
    study: StudyDefinition,
    contract: StudyExecutionContract,
    preparation: StudyPreparation,
    source_loader: SourceLoader,
) -> CalibrationManifest:
    verify_preparation(study, contract, preparation, source_loader)
    if preparation.mode != "primary" or preparation.bundle is None:
        raise ValueError("Human review requires primary preparation")
    examples = tuple(
        make_example(
            r,
            contract.rating,
            ObservationPolicy(
                kind="prospective", artifact_id=r.selection.observation_id
            ),
        )
        for r in preparation.bundle.requests
        if r.selection.requires_human
    )
    assert preparation.bundle.plan.review_set_id is not None
    return CalibrationManifest(
        set_id=preparation.bundle.plan.review_set_id,
        policy_version="salesagent-study-v1-human-selection-v1",
        selection_rationale="Preregistered fixed responses; no selection using observed scores",
        coverage_gaps=(),
        contract=contract.rating,
        examples=examples,
        presentation_order=tuple(e.example_id for e in examples),
    )


def judge_request(
    study: StudyDefinition,
    contract: StudyExecutionContract,
    preparation: StudyPreparation,
    request_id: str,
    *,
    source_loader: SourceLoader,
    scorer_factory: Callable[[], ProspectiveJudge],
    store: ProspectiveStore,
    frozen_bundle: Path | None = None,
) -> ProspectiveJudgmentResult:
    verify_preparation(study, contract, preparation, source_loader)
    assert preparation.bundle is not None
    matches = [r for r in preparation.bundle.requests if r.request_id == request_id]
    if len(matches) != 1:
        raise ValueError("Unknown selected study request")
    scorer, _ = semantic_profile(
        contract.evaluator.judge, projection_version=contract.rating.projection_version
    )
    return execute_prospective(
        matches[0],
        source_loader=source_loader,
        verification_scorer=scorer,
        scorer_factory=scorer_factory,
        store=store,
        frozen_bundle=frozen_bundle,
    )
