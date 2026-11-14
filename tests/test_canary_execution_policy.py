"""Pure policy regressions; decisions do not dispatch, retry, or grant authority."""

from dataclasses import FrozenInstanceError, asdict, replace
from decimal import Decimal

import pytest
from test_canary_selection_v3 import preceding, selected

from harness.canary.acceptance import Check
from harness.canary.execution_policy import (
    EXECUTION_POLICY,
    ExecutionState,
    HumanReview,
    OperationalGuards,
    ReviewContext,
    TurnOutcome,
    aggregate,
    decide,
    execution_fingerprint,
    record_outcome,
    review_binding,
)
from harness.canary.recording import CanaryStore
from harness.canary.selection_acceptance import acceptance_fingerprint, assess_selection
from harness.canary.selection_v3 import LIMITS, ORDER

GUARDS = (
    "infrastructure_ok",
    "provider_completed",
    "safety_ok",
    "privacy_ok",
    "recording_complete",
    "accounting_complete",
    "project_controls_verified",
    "spending_headroom_verified",
    "source_and_fixtures_verified",
    "configuration_verified",
    "evidence_fresh",
    "operator_allows_dispatch",
    "exclusive_reservations_verified",
)


def ready(state):
    return OperationalGuards(
        **{name: True for name in GUARDS},
        logical_calls=sum(o.logical_calls for o in state.outcomes),
        provider_attempts=sum(o.provider_attempts for o in state.outcomes),
    )


def outcome(slot="A1", status="PASS", *, calls=1, attempts=1):
    return TurnOutcome(
        slot,
        (
            Check(
                status,
                ()
                if status == "PASS"
                else (
                    "prior_selection_not_established:colour"
                    if status == "SKIP"
                    else "synthetic_reason",
                ),
            ),
        ),
        calls,
        attempts,
        True,
        True,
    )


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (("PASS",), "PASS"),
        (("PASS", "SKIP"), "SKIP"),
        (("SKIP", "FAIL"), "FAIL"),
        (("FAIL", "ERROR"), "ERROR"),
        (("ERROR", "FAIL", "SKIP"), "ERROR"),
    ],
)
def test_aggregation_precedence_preserves_nonpassing_results(statuses, expected):
    checks = tuple(
        Check(s, () if s == "PASS" else (s.lower() + "_reason",)) for s in statuses
    )
    assert aggregate(checks).status == expected
    assert checks == tuple(checks)


def test_skip_must_have_a_reason_and_unknown_status_is_error():
    assert aggregate(()).status == "SKIP"
    for check in (
        Check("SKIP"),
        Check("FAIL", ("",)),
        Check("UNRECOGNISED", ("unknown",)),
    ):
        assert aggregate((check,)).status == "ERROR"


def test_completed_turn_without_an_assessment_stops_even_if_guards_claim_ready():
    state = ExecutionState((replace(outcome(), checks=()),))
    decision = decide(state, ready(state))
    assert decision.action == "STOP" and decision.assessment.status == "ERROR"
    assert "missing_turn_assessment" in decision.assessment.issues


@pytest.mark.parametrize("status", ["PASS", "FAIL", "SKIP"])
def test_completed_trustworthy_outcome_advances_only_to_next_scheduled_turn(status):
    state = ExecutionState()
    visited = []
    for slot in ORDER:
        decision = decide(state, ready(state))
        assert decision.action == "ADVANCE" and decision.next_slot == slot
        assert decision.authorises_live_execution is False
        visited.append(decision.next_slot)
        state = record_outcome(
            decision, outcome(slot, status if slot == "A1" else "PASS")
        )
    completed = decide(state, ready(state))
    assert visited == ["A1", "B1", "A2", "B2"]
    assert completed.action == "COMPLETE" and completed.next_slot is None
    assert completed.mechanical_assessment.status == status
    assert completed.human_review.status == "PENDING"
    assert completed.assessment.status == ("SKIP" if status == "PASS" else status)
    assert state.outcomes[0].checks[0].status == status
    with pytest.raises(ValueError, match="replay"):
        record_outcome(completed, outcome("A1"))


@pytest.mark.parametrize("guard", GUARDS)
def test_every_operational_guard_stops_even_after_behavioural_fail(guard):
    state = ExecutionState((outcome(status="FAIL"),))
    decision = decide(state, replace(ready(state), **{guard: False}))
    assert decision.action == "STOP" and decision.next_slot is None
    assert decision.assessment.status == "ERROR"
    assert "guard_failed:" + guard in decision.assessment.issues
    assert decision.state.outcomes[0].checks[0].status == "FAIL"
    recovered = decide(decision.state, ready(decision.state))
    assert recovered.action == "STOP" and recovered.next_slot is None
    with pytest.raises(ValueError, match="replay"):
        record_outcome(recovered, outcome("B1"))


@pytest.mark.parametrize("field", ["request_completed", "evidence_trustworthy"])
def test_incomplete_or_ambiguous_request_is_not_continued_or_replaced(field):
    state = ExecutionState((replace(outcome(status="FAIL"), **{field: False}),))
    decision = decide(state, ready(state))
    assert decision.action == "STOP" and decision.assessment.status == "ERROR"
    assert "incomplete_or_untrustworthy_request" in decision.assessment.issues


def test_assessment_error_always_stops_and_defaults_fail_closed():
    state = ExecutionState((outcome(status="ERROR"),))
    assert decide(state, ready(state)).action == "STOP"
    assert decide(ExecutionState(), OperationalGuards()).action == "STOP"
    state = ExecutionState((outcome(),))
    assert decide(state, replace(ready(state), safety_ok=1)).action == "STOP"


@pytest.mark.parametrize(
    "slots", [("B1",), ("A1", "A1"), ("A1", "A2"), ("A1", "B1", "A2", "B2", "A1")]
)
def test_out_of_order_duplicates_and_extra_requests_are_rejected(slots):
    state = ExecutionState(tuple(outcome(s) for s in slots))
    decision = decide(state, ready(state))
    assert (
        decision.action == "STOP"
        and "invalid_roster_prefix" in decision.assessment.issues
    )


def test_record_cannot_replace_previous_slot_or_skip_a_scheduled_turn():
    decision = decide(ExecutionState(), ready(ExecutionState()))
    with pytest.raises(ValueError):
        record_outcome(decision, outcome("B1"))
    state = record_outcome(decision, outcome("A1", "FAIL"))
    decision = decide(state, ready(state))
    with pytest.raises(ValueError):
        record_outcome(decision, outcome("A1"))
    with pytest.raises(ValueError):
        record_outcome(decision, outcome("A2"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("unknown_attempts", 1),
        ("logical_calls", 2),
        ("provider_attempts", 2),
        ("logical_calls", True),
        ("provider_attempts", -1),
        ("unknown_attempts", "unknown"),
        ("logical_calls", 25),
        ("provider_attempts", 73),
    ],
)
def test_unknown_unreconciled_or_invalid_accounting_stops(field, value):
    state = ExecutionState((outcome(),))
    assert decide(state, replace(ready(state), **{field: value})).action == "STOP"


@pytest.mark.parametrize(
    ("calls", "attempts"), [(0, 0), (7, 7), (1, 4), (2, 1), (True, 1), ("1", 1)]
)
def test_turn_call_and_attempt_ceilings_are_enforced(calls, attempts):
    state = ExecutionState((outcome(calls=calls, attempts=attempts),))
    guards = OperationalGuards(
        **{name: True for name in GUARDS}, logical_calls=1, provider_attempts=1
    )
    assert decide(state, guards).action == "STOP"


@pytest.mark.parametrize(
    "cost",
    [
        Decimal(5),
        Decimal("5.01"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-0.01"),
        "0.01",
    ],
)
def test_pause_threshold_and_ambiguous_cost_stop_before_further_dispatch(cost):
    state = ExecutionState((outcome(),))
    assert (
        decide(state, replace(ready(state), estimated_total_usd=cost)).action == "STOP"
    )


def test_exact_approved_call_ceilings_and_below_pause_spend_can_complete():
    state = ExecutionState(tuple(outcome(s, calls=6, attempts=18) for s in ORDER))
    decision = decide(state, replace(ready(state), estimated_total_usd=Decimal("4.99")))
    assert ready(state).logical_calls == 24 and ready(state).provider_attempts == 72
    assert decision.action == "COMPLETE"


def test_limits_match_unchanged_c1_manifest_and_are_immutable(tmp_path):
    store = CanaryStore(tmp_path / "salesagent-preflight-canary" / "limits")
    import json

    manifest = json.loads((store.path / "manifest.json").read_text())
    assert LIMITS.logical_calls_total == manifest["target"]["logical_calls_max"] == 24
    assert LIMITS.provider_attempts_total == manifest["target"]["attempts_max"] == 72
    assert LIMITS.sdk_retries == manifest["target"]["sdk_retries"] == 2
    assert LIMITS.max_output_tokens == manifest["target"]["max_output_tokens"] == 2000
    assert LIMITS.reasoning_effort == manifest["target"]["reasoning_effort"] == "low"
    assert LIMITS.estimated_pause_usd == manifest["budget"]["operator_pause_usd"] == "5"
    assert (
        LIMITS.project_monthly_limit_usd
        == manifest["budget"]["project_limit_usd"]
        == "10"
    )
    assert (LIMITS.target_allowance_usd, LIMITS.contingency_usd, LIMITS.alerts_usd) == (
        "3",
        "2",
        ("2", "4", "5"),
    )
    with pytest.raises(FrozenInstanceError):
        LIMITS.sdk_retries = 0
    assert EXECUTION_POLICY == "salesagent-canary-behavioural-continuation-v1"
    assert len(execution_fingerprint()) == 64


def test_synthetic_v3_coverage_fail_preserves_assessments_and_completes_original_roster():
    state = ExecutionState()
    previous = {}
    reports = []
    for slot in ORDER:
        decision = decide(state, ready(state))
        assert decision.next_slot == slot
        saved = selected(
            slot, product_tool="search_products" if slot == "A1" else "both"
        )
        report = assess_selection(slot, **saved, previous=previous)
        reports.append(report)
        state = record_outcome(
            decision, TurnOutcome(slot, report.checks, 1, 1, True, True)
        )
        previous[slot] = saved
    assert (
        reports[0].factual_evidence.status == reports[0].current_state.status == "PASS"
    )
    assert reports[0].integration_coverage.status == "FAIL"
    assert all(r.status == "PASS" for r in reports[1:])
    final = decide(state, ready(state))
    assert final.action == "COMPLETE" and final.assessment.status == "FAIL"


def test_malformed_v3_evidence_stops_the_pure_sequence_immediately():
    saved = selected()
    saved["trace"]["trace_id"] = "uncorrelated"
    report = assess_selection("A1", **saved)
    initial = decide(ExecutionState(), ready(ExecutionState()))
    state = record_outcome(initial, TurnOutcome("A1", report.checks, 1, 1, True, True))
    assert decide(state, ready(state)).action == "STOP"


def test_policy_is_pure_and_never_creates_a_network_client(monkeypatch):
    import httpx

    def forbidden(*args, **kwargs):
        raise AssertionError("No network clients in decisions")

    monkeypatch.setattr(httpx.Client, "__init__", forbidden)
    state = ExecutionState((outcome(status="FAIL"),))
    before = asdict(state)
    decision = decide(state, ready(state))
    assert decision.next_slot == "B1" and decision.authorises_live_execution is False
    assert asdict(state) == before


@pytest.mark.parametrize(
    "reason",
    [
        "prior_state_unavailable",
        "prior_inventory_evidence_unavailable",
        "session_evidence_unavailable:A1",
        "session_evidence_unavailable:A2",
        "unknown_skip",
    ],
)
def test_missing_operational_evidence_or_unclassified_skip_stops_even_if_guards_claim_ready(
    reason,
):
    value = replace(outcome(), checks=(Check("SKIP", (reason,)),))
    state = ExecutionState((value,))
    decision = decide(state, ready(state))
    assert decision.action == "STOP" and decision.assessment.status == "ERROR"
    assert decision.state.outcomes[0].checks[0].status == "SKIP"


def test_failed_a1_selection_and_skipped_a2_retention_remain_distinct_in_complete_run():
    state = ExecutionState()
    snapshots = {}
    reports = []
    for slot in ORDER:
        saved = selected(slot)
        if slot == "A1":
            saved["trace"]["resolved_constraints"]["colour"] = None
        decision = decide(state, ready(state))
        assert decision.next_slot == slot
        report = assess_selection(slot, **saved, previous=snapshots)
        reports.append(report)
        state = record_outcome(
            decision, TurnOutcome(slot, report.checks, 1, 1, True, True)
        )
        snapshots[slot] = saved
    assert reports[0].current_state.status == "FAIL"
    assert reports[2].current_state.status == "PASS"
    assert reports[2].retention.status == "SKIP"
    assert decide(state, ready(state)).action == "COMPLETE"
    assert decide(state, ready(state)).assessment.status == "FAIL"


@pytest.mark.parametrize("stop_at", ORDER)
def test_error_at_any_roster_position_produces_no_further_slot(stop_at):
    state = ExecutionState()
    visited = []
    for slot in ORDER:
        decision = decide(state, ready(state))
        assert decision.next_slot == slot
        visited.append(slot)
        state = record_outcome(
            decision, outcome(slot, "ERROR" if slot == stop_at else "PASS")
        )
        if slot == stop_at:
            break
    final = decide(state, ready(state))
    assert final.action == "STOP" and final.next_slot is None
    assert tuple(visited) == ORDER[: ORDER.index(stop_at) + 1]


def review_example(verdict="PASS"):
    """Synthetic explicit attestations, never actual approval of captured prose."""
    state = ExecutionState(tuple(outcome(slot) for slot in ORDER))
    context = ReviewContext("synthetic-run-001", "a" * 64, acceptance_fingerprint())
    review = HumanReview(
        review_binding(state, context),
        "beccawillss",
        "2026-11-14T10:00:00+00:00",
        verdict,
        "Synthetic independent prose assessment with reasons.",
    )
    return state, context, review


def test_mechanical_pass_is_qualified_in_serialized_complete_run_until_human_review():
    state, context, _ = review_example()
    result = decide(state, ready(state), review_context=context)
    assert result.action == "COMPLETE"
    assert result.mechanical_assessment.status == "PASS"
    assert result.human_review.status == "PENDING"
    assert result.assessment == Check("SKIP", ("human_prose_review_pending",))
    saved = asdict(result)
    assert saved["mechanical_assessment"]["status"] == "PASS"
    assert saved["human_review"]["status"] == "PENDING"
    assert saved["assessment"]["status"] == "SKIP"
    assert saved["human_review"]["evidence"] is None


@pytest.mark.parametrize("verdict", ["PASS", "FAIL"])
def test_explicit_provenance_bound_human_result_is_independent_of_mechanical_pass(
    verdict,
):
    state, context, review = review_example(verdict)
    before = asdict(state)
    result = decide(state, ready(state), review_context=context, human_review=review)
    assert result.action == "COMPLETE"
    assert result.mechanical_assessment.status == "PASS"
    assert result.human_review.status == result.assessment.status == verdict
    assert result.human_review.evidence == review
    assert asdict(state) == before
    assert result.authorises_live_execution is False
    with pytest.raises(ValueError, match="replay"):
        record_outcome(result, outcome())


@pytest.mark.parametrize("mechanical", ["FAIL", "SKIP", "ERROR"])
def test_human_pass_cannot_erase_independent_mechanical_result(mechanical):
    state, context, review = review_example()
    state = replace(state, outcomes=(outcome(status=mechanical), *state.outcomes[1:]))
    review = replace(review, binding_fingerprint=review_binding(state, context))
    result = decide(state, ready(state), review_context=context, human_review=review)
    assert result.mechanical_assessment.status == mechanical
    assert result.assessment.status == mechanical
    assert result.action == ("STOP" if mechanical == "ERROR" else "COMPLETE")


@pytest.mark.parametrize("change", ["run", "prose", "policy", "assessment", "missing"])
def test_review_from_another_evidence_bundle_run_policy_or_outcome_is_error(change):
    state, context, review = review_example()
    if change == "run":
        context = replace(context, run_id="different-run")
    elif change == "prose":
        context = replace(context, evidence_sha256="b" * 64)
    elif change == "policy":
        context = replace(context, acceptance_fingerprint="b" * 64)
    elif change == "assessment":
        state = replace(state, outcomes=(outcome(status="FAIL"), *state.outcomes[1:]))
    else:
        context = None
    result = decide(state, ready(state), review_context=context, human_review=review)
    assert result.action == "STOP" and result.assessment.status == "ERROR"
    assert result.human_review.status == "ERROR"
    assert result.human_review.evidence == review


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reviewer", "another-reviewer"),
        ("reviewed_at", "not-a-time"),
        ("reviewed_at", "2026-11-14T10:00:00"),
        ("reason", "  "),
        ("verdict", "PENDING"),
        ("verdict", True),
        ("binding_fingerprint", ""),
    ],
)
def test_malformed_or_unattributed_human_evidence_never_approves(field, value):
    state, context, review = review_example()
    result = decide(
        state,
        ready(state),
        review_context=context,
        human_review=replace(review, **{field: value}),
    )
    assert result.assessment.status == "ERROR" and result.action == "STOP"


def test_review_required_boolean_cannot_act_as_review_and_no_review_is_needed_per_turn():
    state, context, review = review_example()
    assert decide(state, ready(state), human_review=True).assessment.status == "ERROR"
    for length in range(4):
        partial = replace(state, outcomes=state.outcomes[:length])
        result = decide(partial, ready(partial))
        assert result.action == "ADVANCE" and result.next_slot == ORDER[length]
        assert result.human_review.status == "PENDING"
        assert result.assessment.status == "SKIP"
        assert (
            decide(
                partial, ready(partial), review_context=context, human_review=review
            ).assessment.status
            == "ERROR"
        )


@pytest.mark.parametrize(
    "field", ["run_id", "evidence_sha256", "acceptance_fingerprint"]
)
def test_review_binding_requires_complete_explicit_provenance(field):
    state, context, _ = review_example()
    with pytest.raises(ValueError, match="context"):
        review_binding(state, replace(context, **{field: ""}))


def test_human_pass_cannot_override_an_operational_stop():
    state, context, review = review_example()
    result = decide(
        state,
        replace(ready(state), recording_complete=False),
        review_context=context,
        human_review=review,
    )
    assert result.human_review.status == result.mechanical_assessment.status == "PASS"
    assert result.action == "STOP" and result.assessment.status == "ERROR"


def test_missing_predecessor_is_offline_skip_but_stops_execution_even_with_behavioural_fail():
    context = preceding("B2")
    del context["A2"]
    saved = selected("B2")
    saved["trace"]["resolved_constraints"]["maximum_price"] = None
    report = assess_selection("B2", **saved, previous=context)
    assert report.current_state.status == "FAIL"
    assert report.session_isolation == Check(
        "SKIP", ("session_evidence_unavailable:A2",)
    )
    state = ExecutionState(
        (
            *tuple(outcome(s) for s in ORDER[:-1]),
            TurnOutcome("B2", report.checks, 1, 1, True, True),
        )
    )
    result = decide(state, ready(state))
    assert result.mechanical_assessment.status == "FAIL"
    assert result.action == "STOP" and result.assessment.status == "ERROR"
    assert result.state.outcomes[-1].checks == report.checks
    with pytest.raises(ValueError, match="replay"):
        record_outcome(result, outcome("B2"))


def test_missing_a2_predecessor_prevents_next_scheduled_b2_dispatch():
    report = assess_selection("A2", **selected("A2"), previous={"A1": selected("A1")})
    assert report.session_isolation.status == "SKIP"
    state = ExecutionState(
        (outcome(), outcome("B1"), TurnOutcome("A2", report.checks, 1, 1, True, True))
    )
    result = decide(state, ready(state))
    assert result.action == "STOP" and result.next_slot is None
