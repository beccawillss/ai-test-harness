"""Local suite resolution and explicit profile-driven execution, outside the runner."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from harness.core.case_fingerprints import (
    CASE_SCHEME_V2,
    hash_case_definition,
    validate_json_data,
)
from harness.core.dataset import (
    LoadedDataset,
    _read_authoring_file,
    _strict_json,
    _validation_detail,
    load_dataset,
)
from harness.core.execution_control import ExecutionControl
from harness.core.fingerprints import canonical_json, fingerprint
from harness.core.models import RunResult, TestCase
from harness.core.replay import JudgeConfiguration
from harness.core.runner import _scorer_snapshot, _validate_run, run
from harness.core.selection import (
    CaseSelection,
    SelectionPreview,
    _validated_selection,
    preview_selection,
    select_cases,
)
from harness.core.snapshots import PayloadPolicy, metadata_keys, project_metadata
from harness.scorers.base import JudgedScorer, Scorer
from harness.scorers.rubric_judge import RubricJudgeScorer
from harness.targets.base import Target


def _identity(value: str) -> str:
    if not value or value != value.strip():
        raise ValueError("Identity must be nonblank without boundary whitespace")
    return value


class DatasetBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    id: str
    version: str
    descriptor: str
    expected_case_fingerprint: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    expected_descriptor_fingerprint: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )

    @field_validator("id", "version")
    @classmethod
    def identity(cls, value: str) -> str:
        return _identity(value)

    @field_validator("descriptor")
    @classmethod
    def local_descriptor(cls, value: str) -> str:
        if (
            not value.strip()
            or "\x00" in value
            or "\\" in value
            or PurePosixPath(value).is_absolute()
            or PureWindowsPath(value).drive
            or urlsplit(value).scheme
        ):
            raise ValueError("Suite descriptor binding must be a local relative path")
        return value


class Suite(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["suite-v1"]
    id: str
    title: str | None = None
    description: str | None = None
    dataset: DatasetBinding
    selection: CaseSelection = Field(default_factory=CaseSelection)
    attempts: int = Field(gt=0)
    evaluation_profile: str | None = None

    @field_validator("id", "evaluation_profile")
    @classmethod
    def identity(cls, value: str | None) -> str | None:
        return None if value is None else _identity(value)

    @field_validator("title")
    @classmethod
    def title_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Title must not be blank")
        return value


class EvaluationProfile(BaseModel):
    """Trusted recipe configuration, never an executable spec loaded from Suite JSON.

    The caller reviews safe_parameters, scorer configuration and every allowed
    metadata subtree. JSON validation checks representation, not confidentiality.
    Missing custom scorer/judge configuration is explicitly unknown.
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    id: str
    taxonomy_evidence: Literal["excluded", "explicitly_included"]
    scorer_configuration: dict[str, dict[str, Any]] = Field(default_factory=dict)
    judge_configurations: dict[str, JudgeConfiguration] = Field(default_factory=dict)
    safe_parameters: dict[str, Any] = Field(default_factory=dict)
    reference_contract: str | None = None
    case_payload_snapshot: PayloadPolicy | None = None
    requires_full_payload: bool = False
    case_extra_keys: list[str] = Field(default_factory=list)
    dataset_extra_keys: list[str] = Field(default_factory=list)

    @field_validator("id", "reference_contract")
    @classmethod
    def identity(cls, value: str | None) -> str | None:
        return None if value is None else _identity(value)

    @field_validator("scorer_configuration", "safe_parameters", mode="before")
    @classmethod
    def finite_configuration(cls, value: Any) -> Any:
        validate_json_data(value)
        return value

    @field_validator("case_extra_keys", "dataset_extra_keys")
    @classmethod
    def allowed_keys(cls, value: list[str]) -> list[str]:
        return metadata_keys(value)


@dataclass(frozen=True)
class ResolvedSuite:
    suite: Suite
    dataset: LoadedDataset
    preview: SelectionPreview
    suite_path: Path
    suite_hash: str


def _verify_binding(suite: Suite, dataset: LoadedDataset, suite_path: Path) -> None:
    binding = suite.dataset
    if (suite_path.parent / binding.descriptor).resolve() != dataset.descriptor_path:
        raise ValueError("Suite descriptor binding differs")
    if (binding.id, binding.version) != (
        dataset.descriptor.id,
        dataset.descriptor.version,
    ):
        raise ValueError("Suite dataset ID/version binding differs")
    if (
        binding.expected_case_fingerprint is not None
        and binding.expected_case_fingerprint != dataset.full_dataset_hash
    ):
        raise ValueError("Expected case fingerprint differs")
    if (
        binding.expected_descriptor_fingerprint is not None
        and binding.expected_descriptor_fingerprint != dataset.descriptor_hash
    ):
        raise ValueError("Expected descriptor fingerprint differs")


def resolve_suite(path: str | Path) -> ResolvedSuite:
    """Strictly load/bind/select locally; no target, scorer or judge construction."""
    path = Path(path).resolve()
    try:
        suite = Suite.model_validate(_strict_json(_read_authoring_file(path)))
    except ValueError as exc:
        raise ValueError(f"{path}: invalid suite: {_validation_detail(exc)}") from None
    dataset = load_dataset(path.parent / suite.dataset.descriptor)
    _verify_binding(suite, dataset, path)
    return ResolvedSuite(
        suite=suite,
        dataset=dataset,
        preview=preview_selection(dataset, suite.selection),
        suite_path=path,
        suite_hash=fingerprint(suite.model_dump(mode="json")),
    )


def _profile_snapshot(
    profile: EvaluationProfile, scorers: Sequence[Scorer]
) -> dict[str, Any]:
    names = {s.name for s in scorers}
    if (
        profile.scorer_configuration.keys() | profile.judge_configurations.keys()
    ) - names:
        raise ValueError("Profile contains configuration for an absent scorer")
    entries = []
    for scorer in scorers:
        observed = _scorer_snapshot(scorer)
        if isinstance(scorer, JudgedScorer):
            observed = deepcopy(scorer.preparation_configuration)
            if profile.taxonomy_evidence == "excluded":
                if not scorer.projection_version or not scorer.projection_reviewed:
                    raise ValueError(
                        "Taxonomy exclusion requires a named reviewed projection"
                    )
                if (
                    isinstance(scorer, RubricJudgeScorer)
                    and scorer.evidence_builder is None
                ):
                    raise ValueError("Default rubric evidence includes tags")
        supplied = profile.scorer_configuration.get(scorer.name)
        if supplied is not None and any(
            canonical_json(supplied[key]) != canonical_json(observed[key])
            for key in supplied.keys() & observed.keys()
        ):
            raise ValueError(
                "Profile configuration contradicts observable scorer settings"
            )
        judge = profile.judge_configurations.get(scorer.name)
        if judge is not None and (
            not isinstance(scorer, JudgedScorer) or judge.model != scorer.judge_model
        ):
            raise ValueError("Profile judge configuration contradicts scorer")
        entries.append(
            {
                "observed": observed,
                "configuration": supplied,
                "configuration_status": "authored"
                if supplied is not None
                else "unknown",
                "judge": judge.model_dump(mode="json") if judge is not None else None,
            }
        )
    return {
        "id": profile.id,
        "taxonomy_evidence": profile.taxonomy_evidence,
        "scorers": entries,
        "safe_parameters": profile.safe_parameters,
        "reference_contract": profile.reference_contract,
        "case_payload_snapshot": profile.case_payload_snapshot,
        "requires_full_payload": profile.requires_full_payload,
    }


def execute_suite(
    resolved: ResolvedSuite,
    target: Target,
    scorers: Sequence[Scorer],
    *,
    profile: EvaluationProfile,
    attempts: int | None = None,
    evaluation_profile: str | None = None,
    case_payload_snapshot: PayloadPolicy | None = None,
    validate_reference: Callable[[TestCase], None] | None = None,
    execution_control: ExecutionControl | None = None,
) -> RunResult:
    """Execute a validated, nonempty selection with explicit uniform scorers.

    Reference validators are integration-owned, pure preflight functions. All
    selected cases are checked before run() is entered. No persistence side
    effects occur here; the returned result can be saved/retried by the caller.
    """
    suite = Suite.model_validate(resolved.suite.model_dump(mode="python"))
    _validated_selection(resolved.suite.selection)
    dataset = LoadedDataset.model_validate(resolved.dataset.model_dump(mode="python"))
    if fingerprint(suite.model_dump(mode="json")) != resolved.suite_hash:
        raise ValueError("Resolved suite definition changed")
    _verify_binding(suite, dataset, resolved.suite_path)
    preview = preview_selection(dataset, suite.selection)
    if preview != resolved.preview:
        raise ValueError("Resolved suite selection changed")
    if not preview.executable:
        raise ValueError("Cannot execute an empty suite selection")
    # Recheck nested caller-owned mutable values; these snapshots never alias them.
    profile = EvaluationProfile.model_validate(profile.model_dump(mode="python"))
    selected_scorers = list(scorers)
    selected = select_cases(dataset.cases, suite.selection)
    overrides: dict[str, Any] = {}
    effective_attempts = suite.attempts if attempts is None else attempts
    if type(effective_attempts) is not int or effective_attempts < 1:
        raise ValueError("attempts must be a positive integer")
    if attempts is not None:
        overrides["attempts"] = attempts
    effective_profile = suite.evaluation_profile
    if evaluation_profile is not None:
        if type(evaluation_profile) is not str:
            raise ValueError("Profile override must be an identity string")
        effective_profile = _identity(evaluation_profile)
        overrides["evaluation_profile"] = evaluation_profile
    if effective_profile is not None and effective_profile != profile.id:
        raise ValueError("Resolved profile ID differs from effective suite profile")
    policy = profile.case_payload_snapshot or "hashes_only"
    policy_source = (
        "profile" if profile.case_payload_snapshot is not None else "default"
    )
    if case_payload_snapshot is not None:
        policy = case_payload_snapshot
        policy_source = "run_override"
        overrides["case_payload_snapshot"] = policy
    if policy not in ("hashes_only", "full"):
        raise ValueError("Unknown case payload snapshot policy")
    if profile.requires_full_payload and policy != "full":
        raise ValueError("Profile requires full case payloads")
    _validate_run(target, selected_scorers, selected, effective_attempts)
    profile_snapshot = _profile_snapshot(profile, selected_scorers)
    if bool(profile.reference_contract) != (validate_reference is not None):
        raise ValueError(
            "A named reference contract and validator must be supplied together"
        )
    if validate_reference is not None:
        for case in selected:
            checked = case.model_copy(deep=True)
            before = hash_case_definition(checked, scheme=CASE_SCHEME_V2)
            try:
                validate_reference(checked)
                if before != hash_case_definition(checked, scheme=CASE_SCHEME_V2):
                    raise ValueError("Reference validator must not mutate cases")
            except Exception:  # noqa: BLE001 - integration errors must not leak case bodies
                raise ValueError(
                    f"Selected reference contract failed for case {case.id!r}"
                ) from None
    descriptor_snapshot = dataset.descriptor.model_dump(mode="json")
    descriptor_snapshot["extra"] = project_metadata(
        dataset.descriptor.extra, profile.dataset_extra_keys
    )
    context = {
        "dataset_descriptor": descriptor_snapshot,
        "dataset_descriptor_hash": dataset.descriptor_hash,
        "dataset_descriptor_snapshot_complete": set(dataset.descriptor.extra)
        <= set(profile.dataset_extra_keys),
        "descriptor_locator": suite.dataset.descriptor,
        "suite_locator": resolved.suite_path.name,
        "full_dataset_hash": dataset.full_dataset_hash,
        "suite": suite.model_dump(mode="json"),
        "suite_hash": resolved.suite_hash,
        "selection": {
            "expression": suite.selection.model_dump(mode="json"),
            "case_ids": preview.case_ids,
        },
        "evaluation_profile": profile_snapshot,
        "overrides": overrides,
        "case_payload_snapshot_source": policy_source,
        "metadata_snapshot_policy": {
            "case_extra_keys": profile.case_extra_keys,
            "dataset_extra_keys": profile.dataset_extra_keys,
        },
        "artifact_capabilities": {
            "definition_payloads": policy == "full",
            "external_source_cases_required": policy != "full"
            or len(selected) != len(dataset.cases)
            or any(not set(c.extra) <= set(profile.case_extra_keys) for c in selected),
        },
    }
    validate_json_data(context)
    context = deepcopy(context)
    result = run(
        target,
        selected_scorers,
        selected,
        attempts=effective_attempts,
        dataset_path=dataset.descriptor.cases,
        fingerprint_scheme=CASE_SCHEME_V2,
        case_extra_keys=profile.case_extra_keys,
        case_payload_snapshot=policy,
        execution_control=execution_control,
        execution_context=context if execution_control is not None else None,
    )
    # Context was validated and copied BEFORE execution; never relabel a v1 result.
    result.config_snapshot.update(context)
    return result


__all__ = [
    "DatasetBinding",
    "EvaluationProfile",
    "ResolvedSuite",
    "Suite",
    "execute_suite",
    "resolve_suite",
]
