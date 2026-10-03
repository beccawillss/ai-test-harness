"""Descriptive comparison of two evaluation runs."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from harness.core.fingerprints import canonical_json, fingerprint
from harness.core.models import CaseResult, RunResult, Verdict
from harness.reporting.grouping import (
    GroupResult,
    escape_markdown_text,
    group_run_results,
)

ContextStatus = Literal["equal", "changed", "unknown"]


@dataclass(frozen=True, slots=True)
class ContextCheck:
    name: str
    status: ContextStatus
    reason: str
    baseline: Any = None
    candidate: Any = None
    baseline_available: bool = True
    candidate_available: bool = True
    affected_case_ids: tuple[str, ...] = ()
    scope: Literal["evaluation", "artifact"] = "evaluation"


@dataclass(frozen=True, slots=True)
class ComparisonContext:
    status: ContextStatus
    artifact_status: ContextStatus
    case_matching: Literal["dataset_identity", "unverified_ids", "different_datasets"]
    baseline_case_ids: tuple[str, ...]
    candidate_case_ids: tuple[str, ...]
    affected_case_ids: tuple[str, ...]
    checks: tuple[ContextCheck, ...]


@dataclass(frozen=True, slots=True)
class MetricComparison:
    """A candidate-minus-baseline comparison of one numeric metric."""

    baseline: float | None
    candidate: float | None
    delta: float | None


@dataclass(frozen=True, slots=True)
class ScoreComparison:
    """Mean values for one stable scorer name."""

    name: str
    metric: MetricComparison


@dataclass(frozen=True, slots=True)
class CaseComparison:
    """Same-ID metrics under RunComparison.context's explicit matching scope."""

    case_id: str
    pass_rate: MetricComparison
    error_rate: MetricComparison
    scores: tuple[ScoreComparison, ...]


@dataclass(frozen=True, slots=True)
class GroupComparison:
    baseline: GroupResult | None
    candidate: GroupResult | None
    membership: ContextCheck
    pass_rate: MetricComparison
    context_status: ContextStatus
    interpretation: str
    qualification: str


@dataclass(frozen=True, slots=True)
class RunComparison:
    """Structured descriptive differences between a baseline and candidate run."""

    baseline_run_id: str
    candidate_run_id: str
    aggregate_pass_rate: MetricComparison
    error_rate: MetricComparison
    cases: tuple[CaseComparison, ...]
    added_case_ids: tuple[str, ...]
    removed_case_ids: tuple[str, ...]
    gained_evidence_case_ids: tuple[str, ...]
    lost_evidence_case_ids: tuple[str, ...]
    target_changed: bool
    dataset_changed: bool
    model_versions_changed: bool
    evaluation_config_changed: bool = False
    context: ComparisonContext | None = None
    groups: tuple[GroupComparison, ...] = ()

    @property
    def regressed_case_ids(self) -> tuple[str, ...]:
        """Descriptive observed decreases, not a context-qualified regression gate."""
        return tuple(
            case.case_id
            for case in self.cases
            if case.pass_rate.delta is not None and case.pass_rate.delta < 0
        )

    @property
    def improved_case_ids(self) -> tuple[str, ...]:
        """Cases whose measured pass rate increased."""
        return tuple(
            case.case_id
            for case in self.cases
            if case.pass_rate.delta is not None and case.pass_rate.delta > 0
        )


def _metric(baseline: float | None, candidate: float | None) -> MetricComparison:
    delta = None if baseline is None or candidate is None else candidate - baseline
    return MetricComparison(baseline=baseline, candidate=candidate, delta=delta)


def _case_error_rate(case: CaseResult) -> float:
    if not case.attempts:
        return 0.0
    errors = sum(attempt.verdict is Verdict.ERROR for attempt in case.attempts)
    return errors / len(case.attempts)


def _score_names(case: CaseResult) -> set[str]:
    return {score.name for attempt in case.attempts for score in attempt.scores}


def _index_cases(result: RunResult) -> dict[str, CaseResult]:
    indexed: dict[str, CaseResult] = {}
    for case in result.cases:
        if case.case_id in indexed:
            raise ValueError(
                f"Run '{result.run_id}' contains duplicate case id '{case.case_id}'."
            )
        indexed[case.case_id] = case
    return indexed


def _evaluation_config(result: RunResult) -> dict[str, object]:
    """Compare evaluator settings, not endpoint/deployment observations.

    Missing legacy keys remain missing; explicit configuration is not assumed
    equivalent to a configuration that was never recorded.
    """
    keys = {
        "attempts",
        "scorers",
        "target_capabilities",
        "selection",
        "assertion_schema_version",
        "evidence_schema_version",
        "semantic_evaluation",
    }
    return {
        "pack_name": result.pack_name,
        **{key: value for key, value in result.config_snapshot.items() if key in keys},
    }


def compare_runs(baseline: RunResult, candidate: RunResult) -> RunComparison:
    """Compare two runs without deciding whether the candidate is acceptable."""
    baseline_cases = _index_cases(baseline)
    candidate_cases = _index_cases(candidate)
    context = _comparison_context(baseline, candidate)
    join_ids = context.case_matching != "different_datasets"

    common_ids = [
        case.case_id
        for case in baseline.cases
        if join_ids and case.case_id in candidate_cases
    ]
    added_ids = tuple(
        case.case_id
        for case in candidate.cases
        if not join_ids or case.case_id not in baseline_cases
    )
    removed_ids = tuple(
        case.case_id
        for case in baseline.cases
        if not join_ids or case.case_id not in candidate_cases
    )

    case_comparisons: list[CaseComparison] = []
    gained_evidence: list[str] = []
    lost_evidence: list[str] = []
    for case_id in common_ids:
        baseline_case = baseline_cases[case_id]
        candidate_case = candidate_cases[case_id]
        baseline_pass_rate = baseline_case.pass_rate
        candidate_pass_rate = candidate_case.pass_rate

        if baseline_pass_rate is None and candidate_pass_rate is not None:
            gained_evidence.append(case_id)
        elif baseline_pass_rate is not None and candidate_pass_rate is None:
            lost_evidence.append(case_id)

        score_names = sorted(_score_names(baseline_case) | _score_names(candidate_case))
        case_comparisons.append(
            CaseComparison(
                case_id=case_id,
                pass_rate=_metric(baseline_pass_rate, candidate_pass_rate),
                error_rate=_metric(
                    _case_error_rate(baseline_case),
                    _case_error_rate(candidate_case),
                ),
                scores=tuple(
                    ScoreComparison(
                        name=name,
                        metric=_metric(
                            baseline_case.mean_score(name),
                            candidate_case.mean_score(name),
                        ),
                    )
                    for name in score_names
                ),
            )
        )

    return RunComparison(
        baseline_run_id=baseline.run_id,
        candidate_run_id=candidate.run_id,
        aggregate_pass_rate=_metric(
            baseline.aggregate_pass_rate, candidate.aggregate_pass_rate
        ),
        error_rate=_metric(baseline.error_rate, candidate.error_rate),
        cases=tuple(case_comparisons),
        added_case_ids=added_ids,
        removed_case_ids=removed_ids,
        gained_evidence_case_ids=tuple(gained_evidence),
        lost_evidence_case_ids=tuple(lost_evidence),
        target_changed=baseline.target_name != candidate.target_name,
        dataset_changed=baseline.dataset_hash != candidate.dataset_hash,
        model_versions_changed=baseline.model_versions != candidate.model_versions,
        evaluation_config_changed=_evaluation_config(baseline)
        != _evaluation_config(candidate),
        context=context,
        groups=_compare_groups(baseline, candidate, context),
    )


__all__ = [
    "CaseComparison",
    "ComparisonContext",
    "ContextCheck",
    "GroupComparison",
    "MetricComparison",
    "RunComparison",
    "ScoreComparison",
    "compare_runs",
    "render_comparison_markdown",
]


_MISSING = object()


def _get(value: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return _MISSING
        value = value[key]
    return value


def _same(a: Any, b: Any) -> bool:
    return canonical_json(a) == canonical_json(b)


def _check(
    name: str,
    a: Any,
    b: Any,
    *,
    complete: bool = True,
    comparable: bool = True,
    reason: str = "Recorded values",
    affected: tuple[str, ...] = (),
    scope: Literal["evaluation", "artifact"] = "evaluation",
) -> ContextCheck:
    available_a, available_b = a is not _MISSING, b is not _MISSING
    if not comparable or not available_a or not available_b:
        status: ContextStatus = "unknown"
        detail = "cannot establish equivalence (missing evidence or incompatible identity/scheme)"
    elif not _same(a, b):
        status, detail = "changed", "differ"
    elif not complete:
        status, detail = (
            "unknown",
            "match where recorded, but configuration is incomplete",
        )
    else:
        status, detail = "equal", "match"
    return ContextCheck(
        name,
        status,
        f"{reason}: {detail}.",
        deepcopy(a) if available_a else None,
        deepcopy(b) if available_b else None,
        available_a,
        available_b,
        affected if status != "equal" else (),
        scope,
    )


def _status(checks: list[ContextCheck] | tuple[ContextCheck, ...]) -> ContextStatus:
    if any(check.status == "changed" for check in checks):
        return "changed"
    return "unknown" if any(check.status == "unknown" for check in checks) else "equal"


def _scheme(run: RunResult) -> Any:
    value = run.config_snapshot.get("dataset_fingerprint_scheme", "dataset-cases-v1")
    # Do not interpret a v2 definition as v1 merely because a context key was lost.
    if value not in ("dataset-cases-v1", "dataset-cases-v2") or any(
        case.definition is not None and case.definition.fingerprint_scheme != value
        for case in run.cases
    ):
        return _MISSING
    return value


def _profile(run: RunResult) -> Any:
    value = run.config_snapshot.get("evaluation_profile")
    if not isinstance(value, dict):
        return _MISSING
    return {
        key: val
        for key, val in value.items()
        if key not in {"scorers", "case_payload_snapshot", "requires_full_payload"}
    }


def _scorer_configuration(run: RunResult) -> tuple[Any, bool]:
    entries = _get(run.config_snapshot, "evaluation_profile", "scorers")
    if (
        not isinstance(entries, list)
        or not entries
        or not all(isinstance(e, dict) for e in entries)
    ):
        return _MISSING, False
    complete = all(
        e.get("configuration_status") == "authored"
        and isinstance(e.get("configuration"), dict)
        for e in entries
    )
    return [
        {k: v for k, v in entry.items() if k != "judge"} for entry in entries
    ], complete


def _judges(run: RunResult) -> tuple[Any, bool]:
    entries = _get(run.config_snapshot, "evaluation_profile", "scorers")
    if not isinstance(entries, list) or not entries:
        return _MISSING, False
    judges = {}
    complete = True
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("observed"), dict):
            return _MISSING, False
        observed = entry.get("observed", {})
        if observed.get("kind") == "judged":
            judges[observed.get("name", "")] = entry.get("judge")
            complete = complete and isinstance(entry.get("judge"), dict)
        elif observed.get("kind") != "deterministic":
            complete = False
    return judges, complete


def _observations(run: RunResult, keys: tuple[str, ...]) -> Any:
    """Only normalized, explicitly named version observations, never raw responses."""
    values: dict[str, list[Any]] = {}
    sources = [
        run.config_snapshot,
        run.config_snapshot.get("target_configuration", {}),
        run.config_snapshot.get("target_observations", {}),
    ]
    sources += [
        a.response.metadata
        for c in run.cases
        for a in c.attempts
        if a.response is not None
    ]
    for source in sources:
        for key in keys:
            value = _get(source, key)
            if value is _MISSING or value is None or value == "unknown" or value == []:
                continue
            observed = value if isinstance(value, list) else [value]
            # Version observations are scalar values, not arbitrary metadata trees.
            if all(type(item) in (str, int, float, bool) for item in observed):
                values.setdefault(key, []).extend(observed)
    normalized = {
        key: [
            json_value
            for _, json_value in sorted({canonical_json(v): v for v in items}.items())
        ]
        for key, items in values.items()
    }
    return normalized if normalized else _MISSING


def _case_field(case: CaseResult, name: str, scheme: Any) -> Any:
    if name == "tags":
        return list(case.tags)
    if case.definition is None:
        return _MISSING
    if name == "definition_hash":
        return (
            case.definition.definition_hash
            if case.definition.fingerprint_scheme == scheme
            else _MISSING
        )
    return getattr(case.definition, name)


def _case_check(
    baseline: RunResult, candidate: RunResult, field: str, *, comparable: bool
) -> ContextCheck:
    a_scheme, b_scheme = _scheme(baseline), _scheme(candidate)
    a = {c.case_id: _case_field(c, field, a_scheme) for c in baseline.cases}
    b = {c.case_id: _case_field(c, field, b_scheme) for c in candidate.cases}
    ids = tuple(dict.fromkeys((*a, *b)))
    checks = [
        _check(field, a.get(i, _MISSING), b.get(i, _MISSING), comparable=comparable)
        for i in ids
    ]
    status = _status(checks) if checks else "unknown"
    return ContextCheck(
        f"case_{field}",
        status,
        "Per-case persisted values; missing snapshots/members are unknown; no current dataset is consulted.",
        {i: v for i, v in a.items() if v is not _MISSING},
        {i: v for i, v in b.items() if v is not _MISSING},
        affected_case_ids=tuple(
            i for i, check in zip(ids, checks, strict=True) if check.status != "equal"
        ),
    )


def _payload_fields(run: RunResult) -> Any:
    snapshot = run.config_snapshot
    if snapshot.get("case_payload_snapshot") != "full" or not isinstance(
        snapshot.get("resolved_cases"), list
    ):
        return _MISSING
    payloads = snapshot["resolved_cases"]
    if any(
        not isinstance(case, dict)
        or not all(key in case for key in ("id", "input", "reference"))
        for case in payloads
    ):
        return _MISSING
    if [case["id"] for case in payloads] != [case.case_id for case in run.cases]:
        return _MISSING
    return {
        case["id"]: {key: fingerprint(case[key]) for key in ("input", "reference")}
        for case in payloads
    }


def _comparison_context(baseline: RunResult, candidate: RunResult) -> ComparisonContext:
    a, b = baseline.config_snapshot, candidate.config_snapshot
    a_id, b_id = (
        _get(a, "dataset_descriptor", "id"),
        _get(b, "dataset_descriptor", "id"),
    )
    a_id = a_id if isinstance(a_id, str) and a_id.strip() else _MISSING
    b_id = b_id if isinstance(b_id, str) and b_id.strip() else _MISSING
    matching: Literal["dataset_identity", "unverified_ids", "different_datasets"] = (
        "unverified_ids"
        if a_id is _MISSING or b_id is _MISSING
        else "dataset_identity"
        if a_id == b_id
        else "different_datasets"
    )
    a_ids, b_ids = (
        tuple(c.case_id for c in baseline.cases),
        tuple(c.case_id for c in candidate.cases),
    )
    ids = tuple(dict.fromkeys((*a_ids, *b_ids)))
    a_scheme, b_scheme = _scheme(baseline), _scheme(candidate)
    hash_comparable = (
        a_scheme is not _MISSING and b_scheme is not _MISSING and a_scheme == b_scheme
    )
    checks = [
        _check("dataset_identity", a_id, b_id, affected=ids),
        _check(
            "dataset_version",
            _get(a, "dataset_descriptor", "version"),
            _get(b, "dataset_descriptor", "version"),
            affected=ids,
        ),
        _check(
            "fingerprint_scheme",
            a_scheme,
            b_scheme,
            reason="Declared scheme (historical absence means v1)",
            affected=ids,
        ),
        _check(
            "full_dataset_fingerprint",
            _get(a, "full_dataset_hash"),
            _get(b, "full_dataset_hash"),
            comparable=hash_comparable,
            affected=ids,
        ),
        _check(
            "executed_subset_fingerprint",
            baseline.dataset_hash,
            candidate.dataset_hash,
            comparable=hash_comparable,
            affected=ids,
        ),
        _check(
            "descriptor_definition",
            _get(a, "dataset_descriptor_hash"),
            _get(b, "dataset_descriptor_hash"),
            comparable=_get(a, "dataset_descriptor", "schema_version")
            == _get(b, "dataset_descriptor", "schema_version")
            == "dataset-descriptor-v1",
            affected=ids,
        ),
        _check("suite_definition", _get(a, "suite"), _get(b, "suite"), affected=ids),
        _check(
            "suite_fingerprint",
            _get(a, "suite_hash"),
            _get(b, "suite_hash"),
            comparable=_get(a, "suite", "schema_version")
            == _get(b, "suite", "schema_version")
            == "suite-v1",
            affected=ids,
        ),
        _check(
            "selection_expression",
            _get(a, "selection", "expression"),
            _get(b, "selection", "expression"),
            affected=ids,
        ),
        _check(
            "resolved_membership",
            list(a_ids),
            list(b_ids),
            reason="Ordered persisted case IDs (identity compatibility checked separately)",
            affected=ids,
        ),
        _check(
            "attempt_policy", _get(a, "attempts"), _get(b, "attempts"), affected=ids
        ),
        _check(
            "evaluation_profile", _profile(baseline), _profile(candidate), affected=ids
        ),
        _check(
            "scorer_snapshots", _get(a, "scorers"), _get(b, "scorers"), affected=ids
        ),
        _check(
            "target_identity", baseline.target_name, candidate.target_name, affected=ids
        ),
        _check(
            "target_capabilities",
            _get(a, "target_capabilities"),
            _get(b, "target_capabilities"),
            affected=ids,
        ),
        _check(
            "target_version_observations",
            _observations(
                baseline,
                (
                    "target_revision",
                    "adapter_version",
                    "model",
                    "models",
                    "prompt_version",
                    "prompt_versions",
                ),
            ),
            _observations(
                candidate,
                (
                    "target_revision",
                    "adapter_version",
                    "model",
                    "models",
                    "prompt_version",
                    "prompt_versions",
                ),
            ),
            affected=ids,
        ),
        _check(
            "evidence_schema",
            _observations(baseline, ("evidence_schema_version",)),
            _observations(candidate, ("evidence_schema_version",)),
            affected=ids,
        ),
    ]
    for name in ("assertion_schema_version", "semantic_evaluation"):
        if name in a or name in b:
            checks.append(_check(name, _get(a, name), _get(b, name), affected=ids))
    if baseline.model_versions or candidate.model_versions:
        checks.append(
            _check(
                "model_versions",
                baseline.model_versions or _MISSING,
                candidate.model_versions or _MISSING,
                affected=ids,
            )
        )
    config_a, complete_a = _scorer_configuration(baseline)
    config_b, complete_b = _scorer_configuration(candidate)
    checks.append(
        _check(
            "scorer_configuration",
            config_a,
            config_b,
            complete=complete_a and complete_b,
            affected=ids,
        )
    )
    judge_a, complete_a = _judges(baseline)
    judge_b, complete_b = _judges(candidate)
    checks.append(
        _check(
            "judge_configuration",
            judge_a,
            judge_b,
            complete=complete_a and complete_b,
            affected=ids,
        )
    )
    for field in ("definition_hash", "category", "risk", "tags"):
        checks.append(
            _case_check(
                baseline,
                candidate,
                field,
                comparable=matching != "different_datasets"
                and (hash_comparable or field != "definition_hash"),
            )
        )
    for key in (
        "case_payload_snapshot",
        "case_payload_snapshot_source",
        "artifact_capabilities",
        "metadata_snapshot_policy",
        "dataset_descriptor_snapshot_complete",
    ):
        checks.append(_check(key, _get(a, key), _get(b, key), scope="artifact"))
    checks.append(
        _check(
            "case_input_reference",
            _payload_fields(baseline),
            _payload_fields(candidate),
            comparable=hash_comparable and matching == "dataset_identity",
            reason="Input/reference field fingerprints require full persisted payloads; hashes-only supplies no field-level evidence",
            scope="artifact",
        )
    )
    affected = {
        i
        for check in checks
        if check.scope == "evaluation"
        for i in check.affected_case_ids
    }
    return ComparisonContext(
        status=_status([c for c in checks if c.scope == "evaluation"]),
        artifact_status=_status([c for c in checks if c.scope == "artifact"]),
        case_matching=matching,
        baseline_case_ids=a_ids,
        candidate_case_ids=b_ids,
        affected_case_ids=tuple(i for i in ids if i in affected),
        checks=tuple(checks),
    )


def _interpretation(metric: MetricComparison) -> str:
    if metric.delta is None:
        return "insufficient evidence"
    return (
        "observed decrease"
        if metric.delta < 0
        else "observed increase"
        if metric.delta > 0
        else "unchanged"
    )


def _compare_groups(
    baseline: RunResult, candidate: RunResult, context: ComparisonContext
) -> tuple[GroupComparison, ...]:
    records = []
    for dimension in ("category", "tags", "risk"):
        a = {
            (g.classification_state, g.value): g
            for g in group_run_results(baseline, by=dimension)
        }
        b = {
            (g.classification_state, g.value): g
            for g in group_run_results(candidate, by=dimension)
        }
        for key in dict.fromkeys((*a, *b)):
            old, new = a.get(key), b.get(key)
            old_ids = list(old.member_case_ids) if old else []
            new_ids = list(new.member_case_ids) if new else []
            old_set, new_set = set(old_ids), set(new_ids)
            affected = tuple(
                i
                for i in dict.fromkeys((*old_ids, *new_ids))
                if i not in old_set or i not in new_set
            )
            if old_ids != new_ids and not affected:
                affected = tuple(dict.fromkeys((*old_ids, *new_ids)))
            membership = _check(
                "group_membership",
                old_ids,
                new_ids,
                comparable=context.case_matching != "different_datasets",
                affected=affected,
                reason="Ordered group membership; baseline and candidate evidence are independent",
            )
            metric = _metric(
                old.quality_pass_rate if old else None,
                new.quality_pass_rate if new else None,
            )
            status = _status(
                [membership, *[c for c in context.checks if c.scope == "evaluation"]]
            )
            records.append(
                GroupComparison(
                    old,
                    new,
                    membership,
                    metric,
                    status,
                    _interpretation(metric),
                    "Independent group summaries; changed/unknown context does not establish a target regression."
                    if status != "equal"
                    else "Recorded comparison context matches; differences remain descriptive, without a significance claim.",
                )
            )
    return tuple(records)


def render_comparison_markdown(comparison: RunComparison) -> str:
    """Use observed-change language, never an unqualified regression label."""
    context = comparison.context
    lines = [
        "## Run comparison",
        "",
        f"Quality pass rate: {_interpretation(comparison.aggregate_pass_rate)}.",
        "",
    ]
    if context is not None:
        lines += [
            f"Evaluation context: {context.status}. Artifact context: {context.artifact_status}.",
            f"Case matching scope: {context.case_matching}. Same IDs alone do not establish equivalent definitions.",
            "",
            "| Context | State | Reason |",
            "| --- | --- | --- |",
        ]
        for check in context.checks:
            lines.append(
                f"| {escape_markdown_text(check.name)} | {check.status} | {escape_markdown_text(check.reason)} |"
            )
    lines += [
        "",
        "Group summaries use independent baseline/candidate memberships. Tag totals overlap and are non-additive.",
        "",
        "| Dimension | Value | State | Baseline members | Candidate members | Baseline pass rate | Candidate pass rate | Membership | Observation | Context |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for group in comparison.groups:
        evidence = group.baseline or group.candidate
        assert evidence is not None
        label = (
            "null" if evidence.value is None else escape_markdown_text(evidence.value)
        )
        old = (
            ", ".join(escape_markdown_text(i) for i in group.baseline.member_case_ids)
            if group.baseline
            else "none"
        )
        new = (
            ", ".join(escape_markdown_text(i) for i in group.candidate.member_case_ids)
            if group.candidate
            else "none"
        )
        rate = lambda value: "unavailable" if value is None else f"{value:.3f}"
        lines.append(
            f"| {evidence.dimension} | {label} | {evidence.classification_state} | {old} | {new} | {rate(group.pass_rate.baseline)} | {rate(group.pass_rate.candidate)} | {group.membership.status} | {group.interpretation} | {group.context_status} |"
        )
    return "\n".join(lines) + "\n"
