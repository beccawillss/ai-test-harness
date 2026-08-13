"""The runner: config in, RunResult out.

Two ideas govern everything here.

*Fail at config time, not mid-run.* Everything knowable before execution —
target/pack compatibility, duplicate ids, an empty scorer set — is checked
up front and raised. A run that cannot produce a meaningful result should
cost nothing, not fail on case 400 of 500 after real money is spent.

*Errors are not failures.* Once execution starts, nothing a target or
scorer raises escapes: it becomes Verdict.ERROR on that attempt and is
excluded from pass rates entirely (ADR 0001). A bad answer is a low Score
and a FAIL; a broken judge is an ERROR. Conflating them makes gates
untrustworthy, and untrustworthy gates get ignored.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from time import perf_counter

from harness.core.config import RunConfig, RunMode
from harness.core.dataset import duplicate_case_ids, hash_cases
from harness.core.errors import ConfigError, IncompatibleTargetError
from harness.core.models import (
    AttemptResult,
    CaseResult,
    RunResult,
    Score,
    TargetResponse,
    TestCase,
    Verdict,
)
from harness.core.store import Store
from harness.packs.base import Pack
from harness.scorers.base import MissingFieldError, Scorer
from harness.targets.base import CloseableTarget, Target, check_pack_compatibility

logger = logging.getLogger(__name__)

#: Recorded in RunResult.config_snapshot["warnings"]. Not exceptions — the
#: run is still worth executing, but somebody should look at it.
WARN_NO_GATED_SCORES = "no_gated_scores"
WARN_MISSING_CAPABILITIES = "missing_capabilities"


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def select_cases(config: RunConfig, cases: Sequence[TestCase]) -> list[TestCase]:
    """Apply the config's case filters, in order: exclude, include, truncate.

    exclude_tags wins over include_tags — a case tagged both "smoke" and
    "flaky" is excluded, because exclusion is the more deliberate signal.
    """
    selected = list(cases)
    if config.exclude_tags:
        excluded = set(config.exclude_tags)
        selected = [c for c in selected if not excluded & set(c.tags)]
    if config.include_tags:
        included = set(config.include_tags)
        selected = [c for c in selected if included & set(c.tags)]
    if config.max_cases is not None:
        selected = selected[: config.max_cases]
    return selected


def select_scorers(config: RunConfig, pack: Pack | None) -> list[Scorer]:
    """The pack's scorers, restricted to the configured kinds.

    Explore mode and a packless run both select nothing — that is the
    whole point of them.

    Mode is compared with == rather than `is` here and below. RunMode is a
    StrEnum, and a config built by a route that skips validation
    (`model_copy(update=...)`, `model_construct`) holds the plain string
    "explore" — which `is` would miss, silently scoring a run somebody
    asked only to explore. Equality is right for both.
    """
    if pack is None or config.mode == RunMode.EXPLORE:
        return []
    if config.scorer_kinds is None:
        return list(pack.scorers)
    return [s for s in pack.scorers if s.kind in config.scorer_kinds]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_run(
    config: RunConfig,
    target: Target,
    pack: Pack | None,
    cases: Sequence[TestCase],
) -> list[str]:
    """Check a run is coherent before executing it. Returns warning codes.

    Raises ConfigError (or NotImplementedError) for anything that makes the
    run meaningless. Returns non-fatal warning codes for things worth
    recording in the result.
    """
    if config.concurrency > 1:
        raise NotImplementedError(
            "Parallel execution is not implemented yet; use concurrency=1. "
            "The field exists to reserve the name."
        )

    if not cases:
        raise ConfigError(
            "No cases to execute. If filters are configured, include_tags/"
            "exclude_tags/max_cases may have removed everything."
        )

    if duplicates := duplicate_case_ids(cases):
        raise ConfigError(
            f"Duplicate case ids in the dataset: {', '.join(duplicates)}. "
            "Case ids are the join key for regression comparison, so "
            "duplicates would silently corrupt any diff against a baseline."
        )

    warnings: list[str] = []

    if config.mode == RunMode.EXPLORE:
        # Nothing gets scored, so a capability gap cannot break anything —
        # and finding out whether an adapter populates a field is a reason
        # to explore in the first place. Record it, don't raise.
        if pack is not None:
            missing = check_pack_compatibility(target, pack.required_capabilities)
            if missing:
                warnings.append(WARN_MISSING_CAPABILITIES)
                logger.warning(
                    "Target '%s' does not declare %s required by pack '%s'. "
                    "Explore mode does not score, so continuing.",
                    target.name,
                    ", ".join(missing),
                    pack.name,
                )
        return warnings

    if pack is None:
        raise ConfigError(
            "A pack is required in score mode. Use mode='explore' to run without one."
        )

    scorers = select_scorers(config, pack)
    if not scorers:
        kinds = (
            "any kind"
            if config.scorer_kinds is None
            else ", ".join(sorted(k.value for k in config.scorer_kinds))
        )
        raise ConfigError(
            f"Pack '{pack.name}' contributes no scorers for this run "
            f"(kinds requested: {kinds}). A score run with no scorers "
            "produces no signal."
        )

    names = [s.name for s in scorers]
    if len(set(names)) != len(names):
        clashing = sorted({n for n in names if names.count(n) > 1})
        raise ConfigError(
            f"Pack '{pack.name}' has duplicate scorer names: {', '.join(clashing)}. "
            "Scorer names are public API and the key that trend charts and "
            "regression comparison join on; they must be unique within a pack."
        )

    # The check that saves the most money: a RAG pack pointed at a plain
    # model adapter dies here rather than as 500 cryptic scorer errors.
    missing = check_pack_compatibility(target, pack.required_capabilities)
    if missing:
        raise IncompatibleTargetError(
            target_name=target.name,
            pack_name=pack.name,
            missing=missing,
            required_by={
                capability: [s.name for s in scorers if capability in s.requires]
                for capability in missing
            },
        )

    return warnings


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def _describe_target_error(target: Target, exc: Exception) -> str:
    return f"target '{target.name}': {type(exc).__name__}: {exc}"


def _describe_scorer_error(scorer: Scorer, exc: Exception) -> str:
    prefix = f"scorer '{scorer.name}'"
    if isinstance(exc, MissingFieldError):
        # Validation should have caught this; reaching it at runtime means
        # the adapter's declared capabilities lie about what it populates.
        prefix = (
            "adapter/pack mismatch (should have been caught at config validation) "
            f"— {prefix}"
        )
    return f"{prefix}: {type(exc).__name__}: {exc}"


def _verdict_for(scores: Sequence[Score], errors: Sequence[str]) -> Verdict:
    if errors:
        return Verdict.ERROR
    gated = [s for s in scores if s.passed is not None]
    if not gated:
        # Only informational metrics ran, so there is nothing to gate on.
        # SKIP keeps this out of pass rates rather than inventing a verdict.
        return Verdict.SKIP
    return Verdict.PASS if all(s.passed for s in gated) else Verdict.FAIL


def _execute_attempt(
    index: int,
    case: TestCase,
    target: Target,
    scorers: Sequence[Scorer],
    mode: RunMode,
) -> AttemptResult:
    """Run one case once. Never raises for target or scorer failures."""
    started_at = datetime.now(UTC)
    clock = perf_counter()

    def elapsed_ms() -> float:
        return (perf_counter() - clock) * 1000

    try:
        response: TargetResponse = target.invoke(case)
    except Exception as exc:  # noqa: BLE001 — deliberate: any target failure is an ERROR verdict
        return AttemptResult(
            index=index,
            response=None,
            verdict=Verdict.ERROR,
            error=_describe_target_error(target, exc),
            started_at=started_at,
            duration_ms=elapsed_ms(),
        )

    if mode == RunMode.EXPLORE:
        return AttemptResult(
            index=index,
            response=response,
            scores=[],
            verdict=Verdict.SKIP,
            started_at=started_at,
            duration_ms=elapsed_ms(),
        )

    scores: list[Score] = []
    errors: list[str] = []
    for scorer in scorers:
        # Every scorer runs even after one fails, so a single run surfaces
        # every broken scorer instead of one per debugging cycle.
        try:
            scores.append(scorer.score(case, response))
        except Exception as exc:  # noqa: BLE001 — deliberate: any scorer failure is an ERROR verdict
            errors.append(_describe_scorer_error(scorer, exc))

    return AttemptResult(
        index=index,
        response=response,
        scores=scores,  # partial scores are kept for debugging
        verdict=_verdict_for(scores, errors),
        error="; ".join(errors) if errors else None,
        started_at=started_at,
        duration_ms=elapsed_ms(),
    )


def _close_target(target: Target, warnings: list[str]) -> None:
    if not isinstance(target, CloseableTarget):
        return
    try:
        target.close()
    except Exception as exc:  # noqa: BLE001 — a failed cleanup must not destroy the result
        logger.warning("Closing target '%s' failed: %s", target.name, exc)
        warnings.append(f"target_close_failed: {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run(
    config: RunConfig,
    target: Target,
    pack: Pack | None,
    cases: Sequence[TestCase],
    store: Store | None = None,
) -> RunResult:
    """Execute a run and return its result, persisting it if a store is given.

    Target and pack arrive as objects rather than names: the runner is
    orchestration only, and resolving config strings to objects is a
    separate concern (a registry, later).
    """
    selected_cases = select_cases(config, cases)
    warnings = validate_run(config, target, pack, selected_cases)
    scorers = select_scorers(config, pack)

    started_at = datetime.now(UTC)
    case_results: list[CaseResult] = []
    gating_checked = False

    try:
        for case in selected_cases:
            attempts = [
                _execute_attempt(i, case, target, scorers, config.mode)
                for i in range(config.attempts)
            ]
            case_results.append(
                CaseResult(case_id=case.id, tags=list(case.tags), attempts=attempts)
            )

            if not gating_checked and config.mode == RunMode.SCORE:
                gating_checked = _check_gating(attempts, pack, warnings)
    finally:
        _close_target(target, warnings)

    result = RunResult(
        config_path=config.config_path,
        config_snapshot=_snapshot(config, target, pack, scorers, warnings),
        target_name=target.name,
        pack_name=pack.name if pack is not None else "none",
        dataset_path=config.dataset_path,
        dataset_hash=hash_cases(selected_cases),
        model_versions=_model_versions(config, scorers),
        started_at=started_at,
        finished_at=datetime.now(UTC),
        cases=case_results,
    )

    if store is not None:
        store.save(result)
    return result


def _check_gating(
    attempts: Sequence[AttemptResult], pack: Pack | None, warnings: list[str]
) -> bool:
    """Warn once if the pack turns out to gate on nothing. Returns True when checked.

    Whether a scorer gates is only visible in the Score it emits — the
    Scorer Protocol declares name/kind/requires and nothing about gating —
    so this cannot be settled during validation without inventing new
    interface surface. Checking the first attempt that actually produced
    scores costs one invocation and still fires long before the run ends.
    """
    for attempt in attempts:
        if attempt.verdict is Verdict.ERROR or not attempt.scores:
            continue
        if all(s.passed is None for s in attempt.scores):
            warnings.append(WARN_NO_GATED_SCORES)
            logger.warning(
                "Pack '%s' produced only informational scores (every Score.passed "
                "is None), so no attempt can pass or fail and this run has no "
                "gating signal. Attempts are recorded as SKIP.",
                pack.name if pack is not None else "none",
            )
        return True
    return False


def _snapshot(
    config: RunConfig,
    target: Target,
    pack: Pack | None,
    scorers: Sequence[Scorer],
    warnings: list[str],
) -> dict[str, object]:
    """Freeze everything needed to explain this run months from now."""
    snapshot: dict[str, object] = dict(config.model_dump(mode="json"))
    snapshot["target"] = target.name
    snapshot["target_capabilities"] = sorted(target.capabilities)
    snapshot["pack"] = pack.name if pack is not None else None
    snapshot["scorers"] = [
        {
            "name": s.name,
            "kind": s.kind.value,
            "pass_threshold": getattr(s, "pass_threshold", None),
            "requires": sorted(s.requires),
        }
        for s in scorers
    ]
    snapshot["warnings"] = list(warnings)
    return snapshot


def _model_versions(config: RunConfig, scorers: Sequence[Scorer]) -> dict[str, str]:
    """Target model ids from config, judge model ids from the scorers.

    A judge upgrade moves scores with zero code changes, so which judge
    produced a number is part of the number.
    """
    versions = dict(config.model_versions)
    for scorer in scorers:
        judge_model = getattr(scorer, "judge_model", None)
        if isinstance(judge_model, str):
            versions[f"judge:{scorer.name}"] = judge_model
    return versions


__all__ = ["run", "select_cases", "select_scorers", "validate_run"]
