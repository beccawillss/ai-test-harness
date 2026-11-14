"""Pure decisions only. No transport, credential access, I/O, recovery or retry.

The caller must persist each returned state and enforce exclusive reservations.
A decision never authorises live execution or consumes a paid request slot.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Literal

from harness.canary.acceptance import Check
from harness.canary.selection_v3 import LIMITS, ORDER, definition_fingerprint
from harness.core.fingerprints import fingerprint

EXECUTION_POLICY = "salesagent-canary-behavioural-continuation-v1"
SAFE_SKIPS = frozenset(
    {
        "prior_selection_not_established:colour",
        "prior_selection_not_established:size",
        "prior_selection_not_established:maximum_price",
        "human_prose_review_pending",
    }
)


def aggregate(checks: tuple[Check, ...]) -> Check:
    """ERROR > FAIL > required SKIP > PASS; unavailable never means success."""
    if not checks:
        return Check("SKIP", ("no_assessments",))
    if any(
        c.status not in ("PASS", "FAIL", "ERROR", "SKIP")
        or (c.status != "PASS" and not c.issues)
        or any(not isinstance(i, str) or not i.strip() for i in c.issues)
        for c in checks
    ):
        return Check("ERROR", ("invalid_assessment",))
    for status in ("ERROR", "FAIL", "SKIP"):
        if any(c.status == status for c in checks):
            return Check(
                status, tuple(i for c in checks if c.status == status for i in c.issues)
            )
    return Check("PASS")


@dataclass(frozen=True)
class OperationalGuards:
    infrastructure_ok: bool = False
    provider_completed: bool = False
    safety_ok: bool = False
    privacy_ok: bool = False
    recording_complete: bool = False
    accounting_complete: bool = False
    project_controls_verified: bool = False
    spending_headroom_verified: bool = False
    source_and_fixtures_verified: bool = False
    configuration_verified: bool = False
    evidence_fresh: bool = False
    operator_allows_dispatch: bool = False
    exclusive_reservations_verified: bool = False
    logical_calls: int = 0
    provider_attempts: int = 0
    unknown_attempts: int = 0
    estimated_total_usd: Decimal = Decimal(0)


@dataclass(frozen=True)
class TurnOutcome:
    slot: str
    checks: tuple[Check, ...]
    logical_calls: int
    provider_attempts: int
    request_completed: bool = False
    evidence_trustworthy: bool = False


@dataclass(frozen=True)
class ExecutionState:
    outcomes: tuple[TurnOutcome, ...] = ()
    stopped: bool = False
    stop_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewContext:
    """Caller-verified identity of the private bundle, including public prose.

    The bundle digest must cover all four chat/trace/assessment artifacts. This
    pure policy neither reads artifacts nor authenticates the human author.
    """

    run_id: str
    evidence_sha256: str
    acceptance_fingerprint: str


@dataclass(frozen=True)
class HumanReview:
    binding_fingerprint: str
    reviewer: str
    reviewed_at: str
    verdict: Literal["PASS", "FAIL"]
    reason: str


@dataclass(frozen=True)
class HumanReviewResult:
    status: Literal["PENDING", "PASS", "FAIL", "ERROR"] = "PENDING"
    issues: tuple[str, ...] = ("human_prose_review_pending",)
    evidence: HumanReview | None = None


def review_binding(state: ExecutionState, context: ReviewContext) -> str:
    """Bind a human attestation to this complete run, source and evidence bundle.

    A digest detects mismatches; it is not authentication or human approval.
    Callers must verify the manifest and acceptance fingerprint independently.
    """
    if (
        tuple(o.slot for o in state.outcomes) != ORDER
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", context.run_id)
        or any(
            not re.fullmatch(r"[0-9a-f]{64}", digest)
            for digest in (context.evidence_sha256, context.acceptance_fingerprint)
        )
    ):
        raise ValueError("Complete roster and verified review context required")
    return fingerprint(
        {
            "context": asdict(context),
            "state": asdict(state),
            "execution_fingerprint": execution_fingerprint(),
        }
    )


def _human_review(
    state: ExecutionState, context: ReviewContext | None, review: HumanReview | None
) -> HumanReviewResult:
    if review is None:
        return HumanReviewResult()
    try:
        if context is None:
            raise ValueError("Missing review context")
        observed = datetime.fromisoformat(review.reviewed_at)
        if (
            review.binding_fingerprint != review_binding(state, context)
            or review.reviewer != "beccawillss"
            or observed.utcoffset() is None
            or review.verdict not in ("PASS", "FAIL")
            or not review.reason.strip()
        ):
            raise ValueError("Invalid review attestation")
    except (ValueError, TypeError, AttributeError):
        return HumanReviewResult("ERROR", ("invalid_human_review_evidence",), review)
    return HumanReviewResult(
        review.verdict,
        () if review.verdict == "PASS" else ("human_prose_review_failed",),
        review,
    )


@dataclass(frozen=True)
class Decision:
    state: ExecutionState
    action: Literal["ADVANCE", "STOP", "COMPLETE"]
    next_slot: str | None
    mechanical_assessment: Check
    human_review: HumanReviewResult = field(default_factory=HumanReviewResult)
    operational_assessment: Check = field(default_factory=lambda: Check("PASS"))
    assessment: Check = field(init=False)
    authorises_live_execution: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        """Overall assessment, qualified by mandatory human review."""
        human = Check(
            "SKIP"
            if self.human_review.status == "PENDING"
            else self.human_review.status,
            self.human_review.issues,
        )
        object.__setattr__(
            self,
            "assessment",
            aggregate((self.mechanical_assessment, human, self.operational_assessment)),
        )


def decide(
    state: ExecutionState,
    guards: OperationalGuards,
    *,
    review_context: ReviewContext | None = None,
    human_review: HumanReview | None = None,
) -> Decision:
    """ADVANCE proposes only the next unseen turn, after every guard passes."""
    problems = list(state.stop_reasons)
    if state.stopped:
        problems.append("execution_already_stopped")
    if tuple(o.slot for o in state.outcomes) != ORDER[: len(state.outcomes)]:
        problems.append("invalid_roster_prefix")
    for guard_field in fields(OperationalGuards):
        if (
            type(guard_field.default) is bool
            and getattr(guards, guard_field.name) is not True
        ):
            problems.append("guard_failed:" + guard_field.name)
    turn_counts_valid = True
    for outcome in state.outcomes:
        if not outcome.checks:
            problems.append("missing_turn_assessment")
        if (
            outcome.request_completed is not True
            or outcome.evidence_trustworthy is not True
        ):
            problems.append("incomplete_or_untrustworthy_request")
        if any(
            c.status == "SKIP" and (not c.issues or set(c.issues) - SAFE_SKIPS)
            for c in outcome.checks
        ):
            problems.append("unclassified_or_operational_skip")
        if (
            type(outcome.logical_calls) is not int
            or type(outcome.provider_attempts) is not int
            or not 1 <= outcome.logical_calls <= LIMITS.logical_calls_per_turn
            or not outcome.logical_calls
            <= outcome.provider_attempts
            <= outcome.logical_calls * LIMITS.attempts_per_call
        ):
            turn_counts_valid = False
            problems.append("invalid_turn_accounting")
    counts = (guards.logical_calls, guards.provider_attempts, guards.unknown_attempts)
    if any(type(n) is not int or n < 0 for n in counts):
        problems.append("invalid_accounting_snapshot")
    elif turn_counts_valid and (
        guards.logical_calls != sum(o.logical_calls for o in state.outcomes)
        or guards.provider_attempts != sum(o.provider_attempts for o in state.outcomes)
        or guards.unknown_attempts != 0
        or guards.logical_calls > LIMITS.logical_calls_total
        or guards.provider_attempts > LIMITS.provider_attempts_total
    ):
        problems.append("unreconciled_or_excess_usage")
    cost = guards.estimated_total_usd
    if (
        not isinstance(cost, Decimal)
        or not cost.is_finite()
        or cost < 0
        or cost >= Decimal(LIMITS.estimated_pause_usd)
    ):
        problems.append("spending_pause_or_invalid_cost")
    assessment = aggregate(tuple(c for o in state.outcomes for c in o.checks))
    if any(aggregate(o.checks).status == "ERROR" for o in state.outcomes):
        problems.append("assessment_error")
    review = _human_review(state, review_context, human_review)
    if review.status == "ERROR":
        problems.append("invalid_human_review_evidence")
    if problems:
        reasons = tuple(dict.fromkeys(problems))
        stopped = replace(state, stopped=True, stop_reasons=reasons)
        return Decision(
            stopped, "STOP", None, assessment, review, Check("ERROR", reasons)
        )
    if len(state.outcomes) == len(ORDER):
        return Decision(state, "COMPLETE", None, assessment, review)
    return Decision(state, "ADVANCE", ORDER[len(state.outcomes)], assessment, review)


def record_outcome(decision: Decision, outcome: TurnOutcome) -> ExecutionState:
    """Append only the scheduled slot. This performs no request or persistence."""
    if (
        decision.action != "ADVANCE"
        or decision.state.stopped
        or outcome.slot != decision.next_slot
    ):
        raise ValueError("Cannot replay, replace or append an unscheduled canary turn")
    return replace(decision.state, outcomes=(*decision.state.outcomes, outcome))


def execution_fingerprint() -> str:
    return fingerprint(
        {
            "execution_policy": EXECUTION_POLICY,
            "implementation_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "definition_fingerprint": definition_fingerprint(),
            "live_authority": False,
        }
    )
