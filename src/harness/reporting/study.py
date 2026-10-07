"""Derived Study v1 evidence. Never rewrite a captured RunResult or its verdicts."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from harness.core.fingerprints import canonical_json
from harness.core.models import RunResult, Score, Verdict
from harness.core.prospective import (
    Digest,
    Frozen,
    ProspectiveJudgmentResult,
    SourceLoader,
    strict_json,
    verify_freeze,
)
from harness.core.prospective_io import _load, _save
from harness.core.replay import ReplayAttemptResult, validate_score
from harness.packs.salesagent_study import (
    StudyDefinition,
    StudyExecutionContract,
    StudyPreparation,
    verify_capture,
    verify_preparation,
)
from harness.reporting.grouping import escape_markdown_text


class StudyRow(Frozen):
    case_id: str
    attempt_index: int = Field(ge=0)
    classification_json: str
    deterministic_json: str
    response_available: bool
    semantic_attempt_json: str | None
    request_hash: Digest | None
    observation_hash: Digest | None
    receipt_hash: Digest | None

    @model_validator(mode="after")
    def valid(self) -> Self:
        for field in (
            self.classification_json,
            self.deterministic_json,
            self.semantic_attempt_json,
        ):
            if field is not None and canonical_json(strict_json(field)) != field:
                raise ValueError("Study row bodies must be canonical")
        deterministic = strict_json(self.deterministic_json)
        if set(deterministic) != {"verdict", "scores", "errors"}:
            raise ValueError("Invalid deterministic row")
        scores = [
            Score.model_validate_json(canonical_json(s))
            for s in deterministic["scores"]
        ]
        expected = (
            Verdict.ERROR
            if deterministic["errors"]
            else Verdict.FAIL
            if any(s.passed is False for s in scores)
            else Verdict.PASS
            if any(s.passed is True for s in scores)
            else Verdict.SKIP
        )
        if deterministic["verdict"] != expected.value:
            raise ValueError("Deterministic row verdict differs")
        if not self.response_available and expected != Verdict.ERROR:
            raise ValueError("Missing response must retain target ERROR")
        if self.semantic_attempt_json is not None:
            attempt = ReplayAttemptResult.model_validate_json(
                self.semantic_attempt_json
            )
            if (
                canonical_json(attempt.model_dump(mode="json"))
                != self.semantic_attempt_json
            ):
                raise ValueError("Semantic row must retain the exact typed result")
            if (
                not self.response_available
                or self.request_hash is None
                or self.observation_hash is None
            ):
                raise ValueError("Semantic row lacks source/observation binding")
        elif self.observation_hash or self.receipt_hash:
            raise ValueError("Unobserved row cannot claim result/receipt")
        return self

    @property
    def semantic_availability(self) -> Literal["unavailable", "pending", "terminal"]:
        return (
            "unavailable"
            if not self.response_available
            else "pending"
            if self.semantic_attempt_json is None
            else "terminal"
        )

    @property
    def combined(self) -> str | None:
        if not self.response_available:
            return Verdict.ERROR.value
        if self.semantic_attempt_json is None:
            return None
        outcomes = [
            strict_json(self.deterministic_json)["verdict"],
            strict_json(self.semantic_attempt_json)["verdict"],
        ]
        for verdict in (Verdict.ERROR, Verdict.FAIL, Verdict.PASS):
            if verdict.value in outcomes:
                return verdict.value
        return Verdict.SKIP.value

    @property
    def critical_failures(self) -> tuple[str, ...]:
        return tuple(
            a["id"]
            for s in strict_json(self.deterministic_json)["scores"]
            for a in s.get("extra", {}).get("assertions", [])
            if a.get("critical") and a.get("passed") is False
        )


class StudyAnalysis(Frozen):
    schema_version: Literal["salesagent-study-analysis-v1"] = (
        "salesagent-study-analysis-v1"
    )
    kind: Literal["derived_study_analysis"] = "derived_study_analysis"
    contract: StudyExecutionContract
    source_document_hash: Digest
    source_run_id: str
    suite_id: str
    preparation_hash: Digest | None
    observation_hashes: tuple[Digest, ...]
    rows: tuple[StudyRow, ...]
    observed_context_json: str

    @model_validator(mode="after")
    def valid(self) -> Self:
        bindings = [s for s in self.contract.validation.suites if s.id == self.suite_id]
        if len(bindings) != 1:
            raise ValueError("Unknown analysis suite")
        expected = [
            (id, i) for id in bindings[0].case_ids for i in range(bindings[0].attempts)
        ]
        if [(r.case_id, r.attempt_index) for r in self.rows] != expected:
            raise ValueError("Analysis dropped/reordered source attempts")
        for row in self.rows:
            if row.semantic_attempt_json is not None:
                attempt = ReplayAttemptResult.model_validate_json(
                    row.semantic_attempt_json
                )
                if attempt.score is not None:
                    validate_score(
                        attempt.score, strict_json(self.contract.evaluator.scorer_json)
                    )
        hashes = tuple(
            r.observation_hash for r in self.rows if r.observation_hash is not None
        )
        if hashes != self.observation_hashes or len(set(hashes)) != len(hashes):
            raise ValueError("Duplicate or changed analysis observation binding")
        if (
            canonical_json(strict_json(self.observed_context_json))
            != self.observed_context_json
        ):
            raise ValueError("Observed context must be canonical")
        return self


def observed_context(
    source: RunResult, contract: StudyExecutionContract
) -> dict[str, Any]:
    """Observed labels do not attest deployment fixtures or generation parameters."""
    r = contract.target.requested
    rows: list[dict[str, Any]] = []
    for case in source.cases:
        for attempt in case.attempts:
            metadata = attempt.response.metadata if attempt.response else {}
            facts = {
                k: metadata.get(k)
                for k in (
                    "models",
                    "prompt_versions",
                    "adapter_version",
                    "evidence_schema_version",
                    "target_revision",
                    "target_revision_source",
                    "trace_ids",
                )
            }
            # Retain per-turn observation identities independently of requested facts.
            facts["turns"] = (
                []
                if attempt.response is None
                else [
                    {
                        k: t.get("metadata", {}).get(k)
                        for k in ("model", "prompt_version", "trace_id")
                    }
                    for t in attempt.response.structured.get("turns", [])
                ]
            )
            checks = {
                "model": "unknown"
                if not facts["models"]
                else "equal"
                if facts["models"] == [r.model]
                else "changed",
                "prompt_version": "unknown"
                if not facts["prompt_versions"] or r.prompt_version is None
                else "equal"
                if facts["prompt_versions"] == [r.prompt_version]
                else "changed",
            }
            for key in ("adapter_version", "evidence_schema_version"):
                checks[key] = (
                    "unknown"
                    if facts[key] is None
                    else "equal"
                    if facts[key] == getattr(r, key)
                    else "changed"
                )
            rows.append(
                {
                    "case_id": case.case_id,
                    "attempt_index": attempt.index,
                    "observed": facts,
                    "checks": checks,
                }
            )
    return {
        "requested_freeze_hash": contract.target.digest,
        "rows": rows,
        "homogeneous": "changed"
        if any("changed" in row["checks"].values() for row in rows)
        else "unknown"
        if any("unknown" in row["checks"].values() for row in rows)
        else "equal",
        "unattested": [
            "deployed_target_commit_sha",
            "provider",
            "generation_parameters",
            "prompt_digest",
            "catalogue",
            "promotions",
            "state_configuration",
        ],
    }


def analyze(
    study: StudyDefinition,
    contract: StudyExecutionContract,
    source: RunResult,
    *,
    document_hash: str,
    preparation: StudyPreparation | None = None,
    results: Sequence[ProspectiveJudgmentResult] = (),
    source_loader: SourceLoader | None = None,
    frozen_bundle: Path | None = None,
) -> StudyAnalysis:
    suite_id = verify_capture(study, contract, source, document_hash)
    requests = {}
    if preparation is not None:
        if source_loader is None:
            raise ValueError("Preparation analysis requires verified source loading")
        verify_preparation(study, contract, preparation, source_loader)
        if (
            preparation.mode != "primary"
            or preparation.source_document_hash != document_hash
        ):
            raise ValueError(
                "Diagnostic or wrong-source preparation cannot replace primary observations"
            )
        assert preparation.bundle is not None
        requests = {
            (r.source.case_id, r.source.attempt_index): r
            for r in preparation.bundle.requests
        }
    elif results:
        raise ValueError("Observations require the selected frozen preparation")
    selected = {}
    for result in results:
        result = ProspectiveJudgmentResult.model_validate_json(result.model_dump_json())
        request = result.input
        key = (request.source.case_id, request.source.attempt_index)
        if (
            key in selected
            or request != requests.get(key)
            or request.selection.role != "primary"
            or result.input.source.run_id != source.run_id
        ):
            raise ValueError("Duplicate/unselected/wrong-source semantic observation")
        receipt = verify_freeze(
            request, frozen_bundle if request.selection.requires_human else None
        )
        if result.freeze != receipt:
            raise ValueError("Semantic observation freeze receipt differs")
        selected[key] = result
    rows = []
    for case in source.cases:
        for attempt in case.attempts:
            key = (case.case_id, attempt.index)
            selected_result = selected.get(key)
            selected_request = requests.get(key)
            rows.append(
                StudyRow(
                    case_id=case.case_id,
                    attempt_index=attempt.index,
                    classification_json=canonical_json(
                        {
                            "tags": case.tags,
                            "definition": case.definition.model_dump(mode="json")
                            if case.definition
                            else None,
                        }
                    ),
                    deterministic_json=canonical_json(
                        {
                            "verdict": attempt.verdict.value,
                            "scores": [
                                s.model_dump(mode="json") for s in attempt.scores
                            ],
                            "errors": [attempt.error] if attempt.error else [],
                        }
                    ),
                    response_available=attempt.response is not None,
                    semantic_attempt_json=canonical_json(
                        selected_result.attempts[0].model_dump(mode="json")
                    )
                    if selected_result
                    else None,
                    request_hash=selected_request.digest if selected_request else None,
                    observation_hash=selected_result.digest
                    if selected_result
                    else None,
                    receipt_hash=selected_result.freeze.receipt_hash
                    if selected_result and selected_result.freeze
                    else None,
                )
            )
    return StudyAnalysis(
        contract=contract,
        source_document_hash=document_hash,
        source_run_id=source.run_id,
        suite_id=suite_id,
        preparation_hash=preparation.digest if preparation else None,
        observation_hashes=tuple(
            r.observation_hash for r in rows if r.observation_hash
        ),
        rows=tuple(rows),
        observed_context_json=canonical_json(observed_context(source, contract)),
    )


def _metrics(rows: Sequence[StudyRow], layer: str) -> dict[str, Any]:
    verdicts = []
    rates = defaultdict(list)
    scores = defaultdict(list)
    for row in rows:
        body = (
            strict_json(row.deterministic_json)
            if layer == "deterministic"
            else strict_json(row.semantic_attempt_json)
            if layer == "semantic" and row.semantic_attempt_json
            else None
        )
        outcome = (
            row.combined if layer == "combined" else body["verdict"] if body else None
        )
        verdicts.append(outcome)
        if outcome in ("pass", "fail"):
            rates[row.case_id].append(outcome == "pass")
        if body:
            evidence = (
                body.get("scores", [])
                if layer == "deterministic"
                else [body["score"]]
                if body["score"]
                else []
            )
            for score in evidence:
                scores[score["name"]].append(score["value"])
    counts = Counter(verdicts)
    case_rates = [sum(v) / len(v) for v in rates.values()]
    return {
        "case_count": len({r.case_id for r in rows}),
        "attempt_count": len(rows),
        "quality_case_count": len(case_rates),
        "counts": {v: counts[v] for v in ("pass", "fail", "error", "skip")},
        "nonterminal_or_unavailable_count": counts[None],
        "quality_pass_rate": sum(case_rates) / len(case_rates) if case_rates else None,
        "error_rate": counts["error"] / len(rows) if rows else None,
        "scorers": {
            k: {"mean": sum(v) / len(v), "evidence_count": len(v)}
            for k, v in scores.items()
        },
    }


def summarize(analysis: StudyAnalysis) -> dict[str, Any]:
    return {
        "kind": analysis.kind,
        "interpretation": "Descriptive derived evidence. Target variation is not judge-only variation. Pending semantic evidence has no final quality outcome.",
        "diagnostics": "Excluded from primary joins; retained as separate prospective artifacts.",
        "semantic_availability": dict(
            Counter(r.semantic_availability for r in analysis.rows)
        ),
        "layers": {
            l: _metrics(analysis.rows, l)
            for l in ("deterministic", "semantic", "combined")
        },
        "critical_failures": [
            {
                "case_id": r.case_id,
                "attempt_index": r.attempt_index,
                "assertions": list(r.critical_failures),
            }
            for r in analysis.rows
            if r.critical_failures
        ],
        "critical_case_rows": [
            {
                "case_id": r.case_id,
                "attempt_index": r.attempt_index,
                "combined": r.combined,
            }
            for r in analysis.rows
            if strict_json(r.classification_json)["definition"]["risk"] == "critical"
        ],
        "observed_context": strict_json(analysis.observed_context_json),
    }


def group_study(
    analysis: StudyAnalysis, *, by: Literal["category", "risk", "tags"]
) -> list[dict[str, Any]]:
    if by not in ("category", "risk", "tags"):
        raise ValueError("Unknown grouping dimension")
    groups: dict[str | None, list[StudyRow]] = {}
    for row in analysis.rows:
        classification = strict_json(row.classification_json)
        keys = (
            list(dict.fromkeys(classification["tags"])) or [None]
            if by == "tags"
            else [classification["definition"][by]]
        )
        for key in keys:
            groups.setdefault(key, []).append(row)
    return [
        {
            "dimension": by,
            "value": key,
            "totals_additive": by != "tags",
            "case_ids": list(dict.fromkeys(r.case_id for r in rows)),
            "semantic_availability": dict(
                Counter(r.semantic_availability for r in rows)
            ),
            "layers": {
                l: _metrics(rows, l) for l in ("deterministic", "semantic", "combined")
            },
        }
        for key, rows in groups.items()
    ]


def compare_studies(
    baseline: StudyAnalysis, candidate: StudyAnalysis
) -> dict[str, Any]:
    a, b = baseline.contract, candidate.contract
    context = {
        "dataset": (a.validation.full_case_hash, b.validation.full_case_hash),
        "descriptor": (a.validation.descriptor_hash, b.validation.descriptor_hash),
        "suite": (
            next(
                s.fingerprint for s in a.validation.suites if s.id == baseline.suite_id
            ),
            next(
                s.fingerprint for s in b.validation.suites if s.id == candidate.suite_id
            ),
        ),
        "evaluator": (a.evaluator, b.evaluator),
        "target": (a.target.digest, b.target.digest),
        "methodology": (a.validation.methodology_hash, b.validation.methodology_hash),
    }
    checks = {
        key: "equal" if left == right else "changed"
        for key, (left, right) in context.items()
    }
    observed = [
        strict_json(v.observed_context_json)["homogeneous"]
        for v in (baseline, candidate)
    ]
    compatible = all(v == "equal" for v in checks.values()) and observed == [
        "equal",
        "equal",
    ]
    return {
        "context": checks,
        "observed_context": observed,
        "interpretation": "Descriptive comparison; changed/unknown context does not establish a target regression.",
        "compatible": compatible,
        "baseline": summarize(baseline)["layers"],
        "candidate": summarize(candidate)["layers"],
        "groups": {
            dimension: {
                "baseline": group_study(baseline, by=dimension),
                "candidate": group_study(candidate, by=dimension),
            }
            for dimension in ("category", "risk", "tags")
        },
    }


def render_study(analysis: StudyAnalysis) -> str:
    summary = summarize(analysis)
    lines = [
        "# Derived Study v1 analysis",
        "",
        summary["interpretation"],
        "",
        summary["diagnostics"],
        "",
        "| Case | Attempt | Deterministic | Semantic availability | Combined | Critical failures |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in analysis.rows:
        lines.append(
            f"| {escape_markdown_text(r.case_id)} | {r.attempt_index} | {strict_json(r.deterministic_json)['verdict']} | {r.semantic_availability} | {r.combined or 'pending'} | {escape_markdown_text(', '.join(r.critical_failures))} |"
        )
    lines += [
        "",
        "Tag groups overlap and are non-additive.",
        "Requested target settings and observed labels are distinct; catalogue/configuration facts are not attested by traces.",
    ]
    return "\n".join(lines) + "\n"


def save_analysis(analysis: StudyAnalysis, path: Path) -> None:
    _save(path, StudyAnalysis.model_validate_json(analysis.model_dump_json()))


def load_analysis(path: Path) -> StudyAnalysis:
    return _load(path, StudyAnalysis)
