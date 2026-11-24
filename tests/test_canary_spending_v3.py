"""Deterministic spending claims; no acquisition, provider or signing."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone
from decimal import ROUND_DOWN, getcontext, localcontext
from pathlib import Path

import pytest
from pydantic import ValidationError

from harness.canary import runtime_v3 as runtime
from harness.canary import spending_v3 as s
from harness.core.fingerprints import canonical_json, fingerprint

NOW = datetime(2026, 11, 24, 12, tzinfo=UTC)
AT = "2026-11-24T12:00:00Z"
START = "2026-11-01T00:00:00Z"
END = "2026-12-01T00:00:00Z"
HORIZON = "2026-11-24T12:30:00Z"
DIGEST = "a" * 64


def raw(value):
    return canonical_json(value).encode()


def amount(value="1", unit="major"):
    return {"currency": "USD", "unit": unit, "value": value}


def observed_scope():
    return {
        "provider_id": "openai",
        "organization_id": "org_synthetic_test",
        "project_id": "proj_synthetic_test",
        "level": "project",
    }


def header(availability="present"):
    return {
        "availability": availability,
        "stamp": {
            "collection_started_at": AT,
            "collection_ended_at": AT,
            "provider_timestamp": None,
        },
        "supporting_artifact_sha256": DIGEST,
    }


@pytest.fixture(scope="module")
def source():
    return runtime.SourceApprovalReceipt(
        schema_id="canary-source-approval-v1",
        scope="source-only",
        approval_reference="synthetic:spending-test",
        provenance="synthetic-test",
        execution_profile="offline-verification-v1",
        harness=runtime.GitIdentity(commit="a" * 40, tree="b" * 40),
        application=runtime.GitIdentity(
            commit=runtime.APPLICATION_REVISION, tree="c" * 40
        ),
        binding=runtime.resolve_definition(runtime.V3),
        harness_lock_sha256="d" * 64,
        application_lock_sha256="e" * 64,
        runtime=runtime.RuntimeIdentity(
            implementation="CPython",
            python="3.12.13",
            system="Darwin",
            machine="arm64",
            dependency_lock="harness",
        ),
    ).model_dump(mode="json")


@pytest.fixture
def case(source):
    scope = {
        "project": {k: v for k, v in observed_scope().items() if k != "level"},
        "environment": "synthetic_fixture",
        "billing_period": {
            "start": START,
            "end": END,
            "reset_convention": "utc_calendar_month",
            "reset_reference_sha256": DIGEST,
        },
        "horizon_end": HORIZON,
    }
    policy = {
        "schema_id": "canary-offline-spending-diagnostic-policy-v1",
        "policy_id": "diagnostic-policy",
        "scope": scope,
        "valid_from": "2026-11-24T11:00:00Z",
        "valid_until": "2026-11-24T13:00:00Z",
        "accepted_provenances": list(s.PROFILES.values()),
        "max_project_threshold_usd": "10",
        "required_enforcement": "enforcing",
        "required_alerts_usd": [],
        "max_control_age_seconds": 60,
        "max_cost_age_seconds": 120,
        "max_usage_age_seconds": 180,
        "max_liability_age_seconds": 60,
        "max_collection_span_seconds": 60,
        "max_cost_window_lag_seconds": 120,
        "max_usage_window_lag_seconds": 180,
        "require_usage": False,
        "reporting_requirement": "bounded_gap_assumptions",
        "safety_margin_usd": "1",
        "minimum_residual_headroom_usd": "1",
        "liability_rules": [
            {
                "kind": k,
                "source": "declared_upper_bound",
                "allowance_usd": None,
                "supporting_reference_sha256": None,
                "bound_claim_as_of": None,
                "attempt_coverage": "not_applicable",
            }
            for k in s.KINDS
        ],
        **dict.fromkeys(
            (
                "require_authenticated_acquisition",
                "require_verified_liability_bounds",
                "require_verified_propagation",
                "require_final_billing",
                "require_organization_headroom",
                "require_cost_comparison",
            ),
            False,
        ),
    }
    assignment = {
        "schema_id": "canary-spending-assignment-v1",
        "assignment_id": "assignment-test",
        "audience": "diagnostic-review",
        "purpose": "prospective-offline-spending-diagnostic",
        "source_receipt": source,
        "source_receipt_sha256": fingerprint(source),
        "scope": scope,
        "observation_profile": "spending-synthetic-fixture-v1",
        "policy_commitment_sha256": DIGEST,
        "opens_at": "2026-11-24T11:00:00Z",
        "closes_at": HORIZON,
    }
    window = {"start": START, "end": AT}
    bundle = {
        "schema_id": "canary-spending-observation-bundle-v1",
        "canonicalization": "replay-canonical-json-v1",
        "assignment_commitment_sha256": DIGEST,
        "policy_commitment_sha256": DIGEST,
        "observation_profile": "spending-synthetic-fixture-v1",
        "declared_provenance": "synthetic_test",
        "observer_reference": "declared-observer",
        "control": {
            "header": header(),
            "payload": {
                "scope": observed_scope(),
                "kind": "hard_limit",
                "threshold": amount("10"),
                "interval": "month",
                "enforcement": "enforcing",
            },
        },
        "alerts": None,
        "costs": {
            "header": header(),
            "payload": {
                "scope": observed_scope(),
                "window": window,
                "traffic_scope": "all_project_traffic",
                "pagination": "complete",
                "reporting_completeness": "unknown",
                "buckets": [{**window, "amount": amount()}],
            },
        },
        "usage": None,
        "liabilities": [
            {
                "header": header(),
                "payload": {
                    "kind": k,
                    "scope": observed_scope(),
                    "exposure_window": {"start": START, "end": HORIZON},
                    "amount": amount(),
                    "basis": "upper_bound_claim",
                    "unknown_attempts": 0 if k == "inflight_unknown" else None,
                    "attempt_coverage": "all_inflight_exposure"
                    if k == "inflight_unknown"
                    else "not_applicable",
                },
            }
            for k in s.KINDS
        ],
    }
    return {"policy": policy, "assignment": assignment, "bundle": bundle}


def prepared(case):
    """Fixture issuer constructs anchors outside the production assessor."""
    p = s.parse_policy(raw(case["policy"]))
    a_doc = copy.deepcopy(case["assignment"])
    a_doc["policy_commitment_sha256"] = s.policy_commitment(p)
    a = s.parse_assignment(raw(a_doc))
    b_doc = copy.deepcopy(case["bundle"])
    b_doc.update(
        policy_commitment_sha256=s.policy_commitment(p),
        assignment_commitment_sha256=s.assignment_commitment(a),
    )
    b = s.parse_bundle(raw(b_doc))
    ref = s.ExpectedSpendingEvidenceReference(
        assignment_id=a.assignment_id,
        assignment_commitment_sha256=s.assignment_commitment(a),
        policy_commitment_sha256=s.policy_commitment(p),
        observation_profile=a.observation_profile,
        bundle_commitment_sha256=s.bundle_commitment(b),
    )
    return a, p, b, ref


def assess(case, now=NOW):
    a, p, b, ref = prepared(case)
    return s.assess_spending(
        s.serialize_bundle(b), assignment=a, policy=p, expected=ref, now=now
    )


def unavailable(case, index, state="unknown"):
    case["bundle"]["liabilities"][index] = (
        None if state == "absent" else {"header": header(state), "payload": None}
    )


def rule(case, index, source="policy_reserve", value="2"):
    case["policy"]["liability_rules"][index].update(
        source=source,
        allowance_usd=value,
        supporting_reference_sha256=DIGEST,
        bound_claim_as_of=AT if source == "independent_bound_claim" else None,
        attempt_coverage="all_inflight_exposure"
        if source == "independent_bound_claim" and index == 1
        else "not_applicable",
    )


def with_usage(case):
    case["bundle"]["usage"] = {
        "header": header(),
        "payload": {
            "scope": observed_scope(),
            "window": {"start": START, "end": AT},
            "traffic_scope": "project_completions_family",
            "pagination": "complete",
            "reporting_completeness": "unknown",
            "window_coverage": "continuous",
            "request_count": 2,
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
        },
    }


def test_conditional_success_is_explicit_and_roundtrips(case):
    r = assess(case)
    assert r.diagnostic_outcome == "CONDITIONALLY_CONFORMANT"
    assert r.headroom_usd == r.hypothetical_headroom_usd == "4"
    assert r.headroom_state == "DECISION_ELIGIBLE"
    assert r.provider_reporting_completeness.status == "SKIP"
    assert r.provider_reporting_completeness.requirement == "INFORMATIONAL"
    assert s.parse_assessment(s.serialize_assessment(r)) == r
    assert not any(v for _, v in r.assurance if type(v) is bool)
    assert r.assurance.real_external_readiness == "UNESTABLISHED"
    assert r.cost_comparison.difference_usd is None
    assert all(
        not d.independently_verified and not d.underlying_liability_established
        for d in r.effective_deductions
    )


@pytest.mark.parametrize("index", range(4))
@pytest.mark.parametrize("state", ["absent", "unknown", "unavailable"])
def test_reserve_unknown_is_hypothetical_only(case, index, state):
    unavailable(case, index, state)
    rule(case, index)
    r = assess(case)
    assert r.diagnostic_outcome == "INDETERMINATE"
    assert r.headroom_state == "HYPOTHETICAL" and r.headroom_usd is None
    assert r.hypothetical_headroom_usd == "3"
    assert (
        r.effective_deductions[index].diagnostic_evidence_sufficiency.status == "SKIP"
    )


@pytest.mark.parametrize("index", range(4))
@pytest.mark.parametrize("state", ["absent", "unknown", "unavailable"])
def test_qualified_independent_claim_covers_missing_observation(case, index, state):
    unavailable(case, index, state)
    rule(case, index, "independent_bound_claim")
    r = assess(case)
    assert r.diagnostic_outcome == "CONDITIONALLY_CONFORMANT"
    assert r.effective_deductions[index].observation_freshness.status == "SKIP"
    assert not r.assurance.liability_upper_bounds_independently_verified


@pytest.mark.parametrize("index", range(4))
def test_reserve_cannot_reduce_supplied_amount(case, index):
    rule(case, index, value="0.5")
    case["bundle"]["liabilities"][index]["payload"].update(
        amount=amount("3"), basis="amount_claim"
    )
    r = assess(case)
    assert r.effective_deductions[index].effective_amount_usd == "3"
    assert r.headroom_usd is None and r.diagnostic_outcome == "INDETERMINATE"


@pytest.mark.parametrize("index", range(4))
def test_independent_bound_cannot_contradict_supplied_amount(case, index):
    rule(case, index, "independent_bound_claim", "0.5")
    case["bundle"]["liabilities"][index]["payload"]["basis"] = "amount_claim"
    r = assess(case)
    assert r.diagnostic_outcome == "INVALID_EVIDENCE"
    assert "contradictory_bound" in r.issues and r.calculation_inputs is None


@pytest.mark.parametrize(
    "fault", ["support", "stale", "scope", "window", "conflicting"]
)
@pytest.mark.parametrize(
    "selected_source", ["policy_reserve", "independent_bound_claim"]
)
def test_allowance_cannot_hide_submitted_bad_evidence(case, fault, selected_source):
    rule(case, 2, selected_source)
    o = case["bundle"]["liabilities"][2]
    if fault == "support":
        o["header"]["supporting_artifact_sha256"] = None
    elif fault == "stale":
        o["header"]["stamp"].update(
            collection_started_at="2026-11-24T11:58:00Z",
            collection_ended_at="2026-11-24T11:58:00Z",
        )
    elif fault == "scope":
        o["payload"]["scope"]["project_id"] = "proj_wrong"
    elif fault == "window":
        o["payload"]["exposure_window"]["end"] = "2026-11-24T12:20:00Z"
    else:
        unavailable(case, 2, "conflicting")
    r = assess(case)
    assert r.diagnostic_outcome == (
        "INDETERMINATE" if fault in {"support", "stale"} else "INVALID_EVIDENCE"
    )
    assert r.headroom_usd is None


@pytest.mark.parametrize("count", [None, 0, 1])
@pytest.mark.parametrize(
    "coverage", ["all_inflight_exposure", "known_attempts_only", "not_applicable"]
)
@pytest.mark.parametrize("value", ["0", "1"])
def test_unknown_count_and_full_exposure_bound(case, count, coverage, value):
    case["bundle"]["liabilities"][1]["payload"].update(
        unknown_attempts=count, attempt_coverage=coverage, amount=amount(value)
    )
    r = assess(case)
    qualifies = coverage == "all_inflight_exposure" and (value != "0" or count == 0)
    assert (r.diagnostic_outcome == "CONDITIONALLY_CONFORMANT") == qualifies
    assert not r.effective_deductions[1].underlying_liability_established


@pytest.mark.parametrize("index", range(4))
def test_zero_reserve_cannot_replace_unknown(case, index):
    unavailable(case, index)
    rule(case, index, value="0")
    r = assess(case)
    assert r.effective_deductions[index].effective_amount_usd is None
    assert r.diagnostic_outcome == "INDETERMINATE" and r.headroom_state == "UNAVAILABLE"


def test_zero_unreported_claim_cannot_cover_unknown_provider_completeness(case):
    case["bundle"]["liabilities"][0]["payload"]["amount"] = amount("0")
    r = assess(case)
    assert r.diagnostic_outcome == "INDETERMINATE"
    assert "positive_gap_bound_required" in r.issues


@pytest.mark.parametrize(
    "fault",
    [
        "pages",
        "no_buckets",
        "amount",
        "gap",
        "known_incomplete",
        "restricted",
        "overlap",
    ],
)
def test_report_content_cannot_be_replaced_with_reserve(case, fault):
    rule(case, 0, value="8")
    c = case["bundle"]["costs"]["payload"]
    if fault == "pages":
        c["pagination"] = "incomplete"
    elif fault == "no_buckets":
        c["buckets"] = []
    elif fault == "amount":
        c["buckets"][0]["amount"] = None
    elif fault == "gap":
        c["buckets"][0]["start"] = "2026-11-02T00:00:00Z"
    elif fault == "known_incomplete":
        c["reporting_completeness"] = "known_incomplete"
    elif fault == "restricted":
        c["traffic_scope"] = "restricted"
    else:
        c["buckets"].append(copy.deepcopy(c["buckets"][0]))
    r = assess(case)
    assert r.headroom_state == "UNAVAILABLE" and r.calculation_inputs is None
    assert r.diagnostic_outcome == (
        "INVALID_EVIDENCE" if fault == "overlap" else "INDETERMINATE"
    )


@pytest.mark.parametrize("value", ["0", "0.000000000001"])
def test_explicit_zero_and_subcent_costs_are_preserved(case, value):
    case["bundle"]["costs"]["payload"]["buckets"][0]["amount"] = amount(value)
    r = assess(case)
    assert r.supplied_report_total_usd == value
    assert r.headroom_usd == ("5" if value == "0" else "4.999999999999")


@pytest.mark.parametrize(
    "field", ["request_count", "input_tokens", "output_tokens", "total_tokens"]
)
def test_each_required_usage_counter_is_required(case, field):
    with_usage(case)
    case["policy"]["require_usage"] = True
    case["bundle"]["usage"]["payload"][field] = None
    r = assess(case)
    assert (
        r.usage_assessment.status == "SKIP" and r.diagnostic_outcome == "INDETERMINATE"
    )


@pytest.mark.parametrize(
    "fault",
    ["family", "coverage", "pages", "window", "scope", "total", "known_incomplete"],
)
@pytest.mark.parametrize("required", [False, True])
def test_usage_optional_and_required_reliability(case, fault, required):
    with_usage(case)
    case["policy"]["require_usage"] = required
    u = case["bundle"]["usage"]["payload"]
    if fault == "family":
        u["traffic_scope"] = "all_project_traffic"
    elif fault == "coverage":
        u["window_coverage"] = "unknown"
    elif fault == "pages":
        u["pagination"] = "unknown"
    elif fault == "window":
        u["window"]["end"] = "2026-11-24T11:59:59Z"
    elif fault == "scope":
        u["scope"]["level"] = "organization"
    elif fault == "total":
        u["total_tokens"] = 1
    else:
        u["reporting_completeness"] = "known_incomplete"
    r = assess(case)
    unreliable = fault in {"window", "scope", "total"}
    assert r.diagnostic_outcome == (
        "INVALID_EVIDENCE"
        if unreliable
        else "INDETERMINATE"
        if required
        else "CONDITIONALLY_CONFORMANT"
    )


def test_required_valid_usage_remains_usage_not_billing(case):
    with_usage(case)
    case["policy"]["require_usage"] = True
    r = assess(case)
    assert (
        r.diagnostic_outcome == "CONDITIONALLY_CONFORMANT"
        and not r.assurance.billing_verified
    )


@pytest.mark.parametrize(
    "policy_flag,finding",
    [
        ("require_authenticated_acquisition", "authentication_assurance"),
        ("require_verified_liability_bounds", "verified_bounds_assurance"),
        ("require_verified_propagation", "propagation_assurance"),
        ("require_final_billing", "billing_assurance"),
        ("require_organization_headroom", "organization_headroom_requirement"),
        ("require_cost_comparison", "cost_comparison_requirement"),
    ],
)
@pytest.mark.parametrize("required", [False, True])
def test_unsupported_requirements_never_upgrade(case, policy_flag, finding, required):
    case["policy"][policy_flag] = required
    r = assess(case)
    assert getattr(r, finding).status == "SKIP"
    assert getattr(r, finding).requirement == (
        "REQUIRED" if required else "INFORMATIONAL"
    )
    assert r.diagnostic_outcome == (
        "INDETERMINATE" if required else "CONDITIONALLY_CONFORMANT"
    )
    assert not any(v for _, v in r.assurance if type(v) is bool)


def test_complete_reporting_requirement_is_not_satisfied_by_pages(case):
    case["policy"]["reporting_requirement"] = "complete_reporting_required"
    r = assess(case)
    assert r.pagination_coverage.status == "PASS"
    assert r.provider_reporting_completeness.requirement == "REQUIRED"
    assert r.diagnostic_outcome == "INDETERMINATE"


@pytest.mark.parametrize(
    "limit,expected,value",
    [
        ("10", "CONDITIONALLY_CONFORMANT", "4"),
        ("7", "CONDITIONALLY_CONFORMANT", "1"),
        ("6.5", "NONCONFORMANT", "0.5"),
        ("6", "NONCONFORMANT", "0"),
        ("5", "NONCONFORMANT", "-1"),
        ("0", "INDETERMINATE", None),
    ],
)
def test_exact_headroom_boundaries(case, limit, expected, value):
    case["bundle"]["control"]["payload"]["threshold"] = amount(limit)
    r = assess(case)
    assert r.threshold_conformity.status == ("SKIP" if limit == "0" else "PASS")
    assert r.diagnostic_outcome == expected and r.headroom_usd == value


@pytest.mark.parametrize("reserve", ["2", "20"])
def test_hypothetical_positive_or_negative_never_gates(case, reserve):
    unavailable(case, 2)
    rule(case, 2, value=reserve)
    r = assess(case)
    assert r.headroom_state == "HYPOTHETICAL" and r.headroom_usd is None
    assert (
        r.conditional_headroom.status == "SKIP"
        and r.diagnostic_outcome == "INDETERMINATE"
    )
    assert r.hypothetical_headroom_usd == ("3" if reserve == "2" else "-15")


@pytest.mark.parametrize(
    "fault,status",
    [
        ("inactive", "FAIL"),
        ("soft_alert", "FAIL"),
        ("unknown", "SKIP"),
        ("unsupported", "SKIP"),
    ],
)
def test_enforcement_is_not_amount_or_alert(case, fault, status):
    c = case["bundle"]["control"]["payload"]
    c["kind" if fault == "soft_alert" else "enforcement"] = fault
    r = assess(case)
    assert r.enforcement_conformity.status == status
    assert r.diagnostic_outcome == (
        "NONCONFORMANT" if status == "FAIL" else "INDETERMINATE"
    )


@pytest.mark.parametrize("state", ["absent", "stale", "conflicting", "scope"])
@pytest.mark.parametrize("required", [False, True])
def test_optional_alerts_reliability_and_requirements(case, state, required):
    if required:
        case["policy"]["required_alerts_usd"] = ["2"]
    if state != "absent":
        case["bundle"]["alerts"] = {
            "header": header(),
            "payload": {
                "scope": observed_scope(),
                "thresholds": [amount("2")],
                "pagination": "complete",
            },
        }
        if state == "stale":
            case["bundle"]["alerts"]["header"]["stamp"].update(
                collection_started_at="2026-11-24T11:58:00Z",
                collection_ended_at="2026-11-24T11:58:00Z",
            )
        elif state == "conflicting":
            case["bundle"]["alerts"] = {
                "header": header("conflicting"),
                "payload": None,
            }
        else:
            case["bundle"]["alerts"]["payload"]["scope"]["project_id"] = "wrong"
    r = assess(case)
    assert r.diagnostic_outcome == (
        "INVALID_EVIDENCE"
        if state in {"conflicting", "scope"}
        else "INDETERMINATE"
        if required
        else "CONDITIONALLY_CONFORMANT"
    )


@pytest.mark.parametrize(
    "change",
    [
        "outcome",
        "headroom",
        "hypothetical",
        "threshold",
        "cost",
        "deduction",
        "margin",
        "minimum",
        "requirement",
        "assurance",
        "origin",
    ],
)
def test_assessment_representation_rejects_inconsistency(case, change):
    value = assess(case).model_dump(mode="json")
    if change == "outcome":
        value["diagnostic_outcome"] = "INVALID_EVIDENCE"
    elif change == "headroom":
        value["headroom_usd"] = "5"
    elif change == "hypothetical":
        value["hypothetical_headroom_usd"] = "5"
    elif change in {"threshold", "cost", "margin", "minimum"}:
        key = {
            "threshold": "effective_threshold_usd",
            "cost": "reported_cost_usd",
            "margin": "safety_margin_usd",
            "minimum": "minimum_required_residual_usd",
        }[change]
        value["calculation_inputs"][key] = "9"
    elif change == "deduction":
        value["calculation_inputs"]["deductions_usd"][0] = "2"
    elif change == "requirement":
        value["authentication_assurance"]["requirement"] = "REQUIRED"
    else:
        value["assurance"][
            "assessment_origin_authenticated"
            if change == "origin"
            else "provider_evidence_authenticated"
        ] = True
    with pytest.raises(s.SpendingError):
        s.parse_assessment(raw(value))


def test_internally_consistent_import_does_not_prove_execution(case):
    value = assess(case).model_dump(mode="json")
    value["assessed_at"] = "2026-11-24T12:00:01Z"
    imported = s.parse_assessment(raw(value))
    assert (
        not imported.assurance.assessment_origin_authenticated
        and imported.assessed_at != AT
    )


def test_immutable_and_public_revalidation(case):
    a, p, b, ref = prepared(case)
    result = assess(case)
    for item, serialize, field, wrong in [
        (a, s.serialize_assignment, "audience", "bad space"),
        (p, s.serialize_policy, "max_project_threshold_usd", "11"),
        (b, s.serialize_bundle, "observer_reference", "bad space"),
        (ref, s.serialize_expected_reference, "assignment_id", "bad space"),
        (result, s.serialize_assessment, "headroom_usd", "9"),
    ]:
        with pytest.raises(ValidationError):
            setattr(item, field, wrong)
        with pytest.raises(s.SpendingError):
            serialize(item.model_copy(update={field: wrong}))
        with pytest.raises(s.SpendingError):
            serialize(item.model_copy(update={"extra": "PRIVATE"}))


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate",
        "newline",
        "space",
        "utf8",
        "float",
        "nan",
        "oversize",
        "depth",
        "missing",
        "extra",
        "version",
        "auth",
        "local_cost",
    ],
)
def test_strict_parser_faults(case, fault):
    value = copy.deepcopy(case["bundle"])
    if fault == "missing":
        del value["observer_reference"]
    if fault in {"extra", "auth", "local_cost"}:
        value[
            {
                "extra": "extra",
                "auth": "provider_evidence_authenticated",
                "local_cost": "local_cost_usd",
            }[fault]
        ] = True
    if fault == "version":
        value["schema_id"] = "v2"
    payload = raw(value)
    payload = {
        "duplicate": b'{"observer_reference":"duplicate",' + payload[1:],
        "newline": payload + b"\n",
        "space": b" " + payload,
        "utf8": b"\xff",
        "float": b'{"x":1.5}',
        "nan": b'{"x":NaN}',
        "oversize": b"x" * 65537,
        "depth": b"[" * 25 + b"]" * 25,
    }.get(fault, payload)
    with pytest.raises(s.SpendingError):
        s.parse_bundle(payload)


@pytest.mark.parametrize("target", ["assignment", "policy", "reference", "bundle"])
def test_substitution_does_not_adopt_artifact_reference(case, target):
    a, p, b, ref = prepared(case)
    if target == "assignment":
        a = a.model_copy(update={"audience": "other-audience"})
    elif target == "policy":
        p = p.model_copy(update={"safety_margin_usd": "2"})
    elif target == "reference":
        ref = ref.model_copy(update={"bundle_commitment_sha256": "f" * 64})
    else:
        b = b.model_copy(update={"observer_reference": "substituted"})
    r = s.assess_spending(
        s.serialize_bundle(b), assignment=a, policy=p, expected=ref, now=NOW
    )
    assert r.diagnostic_outcome == "INVALID_EVIDENCE" and r.headroom_usd is None


def test_malformed_optional_evidence_is_required_error(case):
    a, p, b, ref = prepared(case)
    value = b.model_dump(mode="json")
    value["usage"] = {"private": "PRIVATE_TOKEN"}
    r = s.assess_spending(raw(value), assignment=a, policy=p, expected=ref, now=NOW)
    assert (
        r.diagnostic_outcome == "INVALID_EVIDENCE"
        and r.input_reliability.requirement == "REQUIRED"
    )
    assert "PRIVATE" not in s.serialize_assessment(r).decode()


@pytest.mark.parametrize(
    "now",
    [
        None,
        AT,
        NOW.replace(tzinfo=None),
        NOW.replace(microsecond=1),
        NOW.replace(tzinfo=timezone(timedelta(hours=1))),
        datetime(1999, 1, 1, tzinfo=UTC),
        datetime(2100, 1, 1, tzinfo=UTC),
    ],
)
def test_invalid_clock_precedes_inputs(now):
    with pytest.raises(s.SpendingError, match="^invalid_clock$"):
        s.assess_spending(
            b"invalid", assignment=None, policy=None, expected=None, now=now
        )


def test_arithmetic_is_independent_of_ambient_context(case):
    case["bundle"]["costs"]["payload"]["buckets"][0]["amount"] = amount(
        "0.000000000001"
    )
    expected = assess(case)
    with localcontext() as context:
        context.prec = 1
        context.rounding = ROUND_DOWN
        context.Emax = 1
        for signal in context.traps:
            context.traps[signal] = True
        assert assess(case) == expected
    assert getcontext().prec != 1


@pytest.mark.parametrize("profile,provenance", list(s.PROFILES.items()))
def test_all_profiles_are_declared_only(case, profile, provenance):
    case["assignment"]["observation_profile"] = profile
    case["bundle"].update(observation_profile=profile, declared_provenance=provenance)
    if profile != "spending-synthetic-fixture-v1":
        case["policy"]["scope"]["environment"] = "external_claim"
    if profile.startswith("openai-admin-"):
        case["bundle"]["control"]["payload"]["threshold"] = amount(
            "1000", "integer_cents"
        )
    r = assess(case)
    assert r.diagnostic_outcome == "CONDITIONALLY_CONFORMANT"
    assert r.calculation_inputs.effective_threshold_usd == "10"
    assert not r.assurance.provider_evidence_authenticated


@pytest.mark.parametrize("fault", ["provenance", "provider_timestamp", "unit"])
def test_claimed_api_profile_does_not_authenticate_or_invent_fields(case, fault):
    profile = "openai-admin-spending-claims-2026-11-24-v1"
    case["assignment"]["observation_profile"] = profile
    case["policy"]["scope"]["environment"] = "external_claim"
    case["bundle"].update(
        observation_profile=profile, declared_provenance="claimed_administrative_api"
    )
    case["bundle"]["control"]["payload"]["threshold"] = amount("1000", "integer_cents")
    if fault == "provenance":
        case["bundle"]["declared_provenance"] = "synthetic_test"
    elif fault == "provider_timestamp":
        case["bundle"]["control"]["header"]["stamp"]["provider_timestamp"] = AT
    else:
        case["bundle"]["control"]["payload"]["threshold"] = amount("10")
    r = assess(case)
    assert r.diagnostic_outcome == "INVALID_EVIDENCE"
    assert not r.assurance.provider_evidence_authenticated


@pytest.mark.parametrize(
    "component,age", [("control", 60), ("costs", 120), ("usage", 180)]
)
@pytest.mark.parametrize("extra", [0, 1])
def test_separate_freshness_exact_boundaries(case, component, age, extra):
    if component == "usage":
        with_usage(case)
        case["policy"]["require_usage"] = True
    case["policy"]["max_collection_span_seconds"] = 3600
    case["bundle"][component]["header"]["stamp"]["collection_started_at"] = (
        NOW - timedelta(seconds=age + extra)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = assess(case)
    name = {
        "control": "control_freshness",
        "costs": "cost_freshness",
        "usage": "usage_freshness",
    }[component]
    assert getattr(r, name).status == ("PASS" if extra == 0 else "SKIP")
    assert r.diagnostic_outcome == (
        "CONDITIONALLY_CONFORMANT" if extra == 0 else "INDETERMINATE"
    )


@pytest.mark.parametrize(
    "fault", ["future", "reversed", "missing_stamp", "span", "future_unavailable"]
)
def test_collection_failures_are_explicit(case, fault):
    h = case["bundle"]["control"]["header"]
    if fault == "future":
        h["stamp"]["collection_ended_at"] = "2026-11-24T12:00:01Z"
    elif fault == "reversed":
        h["stamp"]["collection_started_at"] = "2026-11-24T12:00:01Z"
    elif fault == "missing_stamp":
        h["stamp"] = None
    elif fault == "span":
        case["policy"]["max_control_age_seconds"] = 3600
        h["stamp"]["collection_started_at"] = "2026-11-24T11:58:00Z"
    else:
        h.update(availability="unavailable")
        h["stamp"]["collection_ended_at"] = "2026-11-24T12:00:01Z"
        case["bundle"]["control"]["payload"] = None
    r = assess(case)
    assert r.diagnostic_outcome == (
        "INDETERMINATE" if fault in {"missing_stamp", "span"} else "INVALID_EVIDENCE"
    )


@pytest.mark.parametrize("kind", ["policy", "assignment", "rollover"])
def test_validity_is_half_open_and_month_rollover_blocks(case, kind):
    if kind == "policy":
        case["policy"]["valid_until"] = AT
    elif kind == "assignment":
        case["assignment"]["closes_at"] = AT
    r = assess(case, datetime(2026, 12, 1, tzinfo=UTC) if kind == "rollover" else NOW)
    assert r.diagnostic_outcome == "INDETERMINATE"
    assert r.headroom_usd is None


@pytest.mark.parametrize("fault", ["wrong_period", "future_window", "lag"])
def test_reporting_window_is_not_acquisition_freshness(case, fault):
    c = case["bundle"]["costs"]["payload"]
    if fault == "wrong_period":
        c["window"]["start"] = "2026-11-02T00:00:00Z"
    elif fault == "future_window":
        c["window"]["end"] = "2026-11-24T12:00:01Z"
    else:
        c["window"]["end"] = c["buckets"][0]["end"] = "2026-11-24T11:57:59Z"
    r = assess(case)
    assert r.cost_freshness.status == "PASS"
    assert r.diagnostic_outcome == (
        "INDETERMINATE" if fault == "lag" else "INVALID_EVIDENCE"
    )


@pytest.mark.parametrize(
    "value",
    [
        "-1",
        "-0",
        "NaN",
        "Infinity",
        "1e2",
        "01",
        "0.0",
        "1.",
        ".1",
        " 1",
        "1 ",
        "1.00",
        "0.0000000000001",
        "1000000000000",
        0.1,
        True,
        None,
    ],
)
def test_reject_invalid_monetary_representations(case, value):
    case["bundle"]["control"]["payload"]["threshold"]["value"] = value
    with pytest.raises(s.SpendingError):
        prepared(case)


@pytest.mark.parametrize(
    "fault",
    [
        "currency",
        "unit",
        "fractional_cents",
        "cost_cents",
        "negative_adjustment",
        "counter_bool",
    ],
)
def test_units_currency_and_counter_precision(case, fault):
    if fault == "currency":
        case["bundle"]["control"]["payload"]["threshold"]["currency"] = "GBP"
    elif fault == "unit":
        case["bundle"]["control"]["payload"]["threshold"]["unit"] = "credits"
    elif fault == "fractional_cents":
        case["bundle"]["control"]["payload"]["threshold"] = amount(
            "1.1", "integer_cents"
        )
    elif fault == "cost_cents":
        case["bundle"]["costs"]["payload"]["buckets"][0]["amount"]["unit"] = (
            "integer_cents"
        )
    elif fault == "negative_adjustment":
        case["bundle"]["costs"]["payload"]["buckets"][0]["amount"]["value"] = "-1"
    else:
        with_usage(case)
        case["bundle"]["usage"]["payload"]["request_count"] = True
    with pytest.raises(s.SpendingError):
        prepared(case)


def test_bounded_totals_and_exact_max_precision(case):
    c = case["bundle"]["costs"]["payload"]
    c["buckets"] = [
        {
            "start": START,
            "end": "2026-11-02T00:00:00Z",
            "amount": amount("999999999999.999999999999"),
        },
        {
            "start": "2026-11-02T00:00:00Z",
            "end": AT,
            "amount": amount("0.000000000001"),
        },
    ]
    r = assess(case)
    assert (
        r.diagnostic_outcome == "INVALID_EVIDENCE"
        and "cost_total_out_of_range" in r.issues
    )
    c["buckets"][1]["amount"] = amount("0")
    r = assess(case)
    assert r.headroom_usd == "-999999999994.999999999999"
    assert r.diagnostic_outcome == "NONCONFORMANT"


@pytest.mark.parametrize("fault", ["support", "date", "scope"])
def test_independent_policy_claim_requires_its_own_support(case, fault):
    rule(case, 2, "independent_bound_claim")
    if fault == "support":
        case["policy"]["liability_rules"][2]["supporting_reference_sha256"] = None
    elif fault == "date":
        case["policy"]["liability_rules"][2]["bound_claim_as_of"] = None
    else:
        case["policy"]["scope"] = copy.deepcopy(case["policy"]["scope"])
        case["policy"]["scope"]["project"]["project_id"] = "other"
    if fault == "scope":
        assert assess(case).diagnostic_outcome == "INVALID_EVIDENCE"
    else:
        with pytest.raises(s.SpendingError):
            prepared(case)


@pytest.mark.parametrize(
    "when,status",
    [
        ("2026-11-24T11:59:00Z", "CONDITIONALLY_CONFORMANT"),
        ("2026-11-24T11:58:59Z", "INDETERMINATE"),
        ("2026-11-24T12:00:01Z", "INVALID_EVIDENCE"),
    ],
)
def test_independent_claim_freshness(case, when, status):
    unavailable(case, 2)
    rule(case, 2, "independent_bound_claim")
    case["policy"]["liability_rules"][2]["bound_claim_as_of"] = when
    assert assess(case).diagnostic_outcome == status


def test_independent_failures_survive_skips_and_errors(case):
    case["bundle"]["control"]["payload"]["threshold"] = amount("11")
    case["policy"]["require_final_billing"] = True
    r = assess(case)
    assert r.diagnostic_outcome == "NONCONFORMANT"
    assert (
        r.threshold_conformity.status == "FAIL" and r.billing_assurance.status == "SKIP"
    )
    with_usage(case)
    case["bundle"]["usage"]["payload"]["total_tokens"] = 1
    r = assess(case)
    assert r.diagnostic_outcome == "INVALID_EVIDENCE"
    assert (
        r.threshold_conformity.status == "FAIL" and r.billing_assurance.status == "SKIP"
    )


def test_qualified_zero_bound_does_not_come_from_zero_count_alone(case):
    o = case["bundle"]["liabilities"][1]["payload"]
    o.update(amount=amount("0"), basis="amount_claim", unknown_attempts=0)
    assert assess(case).diagnostic_outcome == "INDETERMINATE"
    o.update(basis="upper_bound_claim", attempt_coverage="known_attempts_only")
    assert assess(case).diagnostic_outcome == "INDETERMINATE"
    o["attempt_coverage"] = "all_inflight_exposure"
    assert assess(case).diagnostic_outcome == "CONDITIONALLY_CONFORMANT"


def test_liability_aggregation_cannot_be_forged_inside_assessment(case):
    r = assess(case)
    bad_deduction = r.effective_deductions[2].model_copy(
        update={
            "diagnostic_evidence_sufficiency": s.DiagnosticFinding(
                status="SKIP", requirement="REQUIRED", issues=("bound_missing",)
            )
        }
    )
    forged = r.model_copy(
        update={
            "effective_deductions": (
                *r.effective_deductions[:2],
                bad_deduction,
                r.effective_deductions[3],
            )
        }
    )
    with pytest.raises(s.SpendingError):
        s.serialize_assessment(forged)


def test_all_serializers_and_commitment_domains(case):
    a, p, b, ref = prepared(case)
    for value, serialize, parse in (
        (a, s.serialize_assignment, s.parse_assignment),
        (p, s.serialize_policy, s.parse_policy),
        (b, s.serialize_bundle, s.parse_bundle),
        (ref, s.serialize_expected_reference, s.parse_expected_reference),
    ):
        encoded = serialize(value)
        assert parse(encoded) == value
        assert encoded == raw(value.model_dump(mode="json")) and not encoded.endswith(
            b"\n"
        )
    assert s.assignment_commitment(a) == fingerprint(
        {
            "domain": "canary-spending-assignment-v1",
            "canonicalization": "replay-canonical-json-v1",
            "value": a.model_dump(mode="json"),
        }
    )
    assert s.policy_commitment(p) == fingerprint(
        {
            "domain": "canary-offline-spending-diagnostic-policy-v1",
            "canonicalization": "replay-canonical-json-v1",
            "value": p.model_dump(mode="json"),
        }
    )
    assert s.bundle_commitment(b) == fingerprint(
        {
            "domain": "canary-spending-observation-bundle-v1",
            "canonicalization": "replay-canonical-json-v1",
            "value": b.model_dump(mode="json"),
        }
    )


def test_source_metadata_validation_is_not_runtime_inspection(case, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("runtime source inspection prohibited")

    monkeypatch.setattr(runtime, "verify_source", forbidden)
    monkeypatch.setattr(runtime, "_git_identity", forbidden)
    r = assess(case)
    assert r.diagnostic_outcome == "CONDITIONALLY_CONFORMANT"
    assert not r.assurance.fresh_source_verification_performed


def test_import_and_all_public_boundaries_have_no_external_side_effects(case):
    a, p, b, ref = prepared(case)
    document = {
        "assignment": a.model_dump(mode="json"),
        "policy": p.model_dump(mode="json"),
        "bundle": b.model_dump(mode="json"),
        "reference": ref.model_dump(mode="json"),
    }
    program = r"""
import json, os, sys
def audit(event, args):
    if event.startswith("socket.") or event in {"subprocess.Popen", "sqlite3.connect"}:
        raise RuntimeError("external side effect")
    if event == "open":
        path, mode, flags = args
        if flags & (os.O_CREAT | os.O_WRONLY | os.O_RDWR | os.O_TRUNC):
            raise RuntimeError("filesystem write")
        if isinstance(path, str) and any(p in path for p in ("/.ssh/", "/.aws/", "/.env", "credentials", "authority.sqlite", "review.sqlite", "/private-evidence/")):
            raise RuntimeError("private discovery")
    if event in {"os.mkdir", "os.remove", "os.rmdir", "os.rename", "os.link", "os.symlink", "os.chmod"}:
        raise RuntimeError("filesystem mutation")
class Environment(dict):
    def get(self, key, default=None):
        if key.startswith(("OPENAI_", "SALESAGENT_", "SSH_", "AWS_")): raise RuntimeError("secret lookup")
        return super().get(key, default)
    def __getitem__(self, key):
        if key.startswith(("OPENAI_", "SALESAGENT_", "SSH_", "AWS_")): raise RuntimeError("secret lookup")
        return super().__getitem__(key)
os.environ = Environment(os.environ)
sys.addaudithook(audit)
from harness.canary import spending_v3 as s
from datetime import UTC, datetime
d = json.loads(sys.stdin.read())
def raw(v): return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
a = s.parse_assignment(raw(d["assignment"]))
p = s.parse_policy(raw(d["policy"]))
b = s.parse_bundle(raw(d["bundle"]))
ref = s.parse_expected_reference(raw(d["reference"]))
# Normal module loading is now complete. Public APIs may read definition source
# metadata, but may not perform any directory enumeration or artifact discovery.
def no_discovery(event, args):
    if event in {"os.listdir", "os.scandir"}: raise RuntimeError("directory discovery")
sys.addaudithook(no_discovery)
for obj, serialize, parse in ((a,s.serialize_assignment,s.parse_assignment),(p,s.serialize_policy,s.parse_policy),(b,s.serialize_bundle,s.parse_bundle),(ref,s.serialize_expected_reference,s.parse_expected_reference)):
    assert parse(serialize(obj)) == obj
assert s.assignment_commitment(a)
assert s.policy_commitment(p)
assert s.bundle_commitment(b)
r = s.assess_spending(s.serialize_bundle(b), assignment=a, policy=p, expected=ref, now=datetime(2026,11,24,12,tzinfo=UTC))
assert r.diagnostic_outcome == "CONDITIONALLY_CONFORMANT"
assert s.parse_assessment(s.serialize_assessment(r)) == r
assert not r.assurance.assessment_origin_authenticated
assert "openai" not in sys.modules and "salesagent" not in sys.modules and "uvicorn" not in sys.modules
print("offline-public-api-audit-passed")
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", program],
        input=json.dumps(document),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "offline-public-api-audit-passed"


@pytest.mark.parametrize(
    "resource",
    [
        "buckets",
        "alerts",
        "liabilities",
        "rules",
        "identifier",
        "policy_bytes",
        "assignment_bytes",
        "reference_bytes",
        "nodes",
    ],
)
def test_resource_limits_reject_without_truncation(case, resource):
    if resource == "buckets":
        case["bundle"]["costs"]["payload"]["buckets"] *= 33
    elif resource == "alerts":
        case["policy"]["required_alerts_usd"] = [str(i) for i in range(9)]
    elif resource == "liabilities":
        case["bundle"]["liabilities"].append(None)
    elif resource == "rules":
        case["policy"]["liability_rules"].pop()
    elif resource == "identifier":
        case["bundle"]["observer_reference"] = "a" * 129
    elif resource == "nodes":
        with pytest.raises(s.SpendingError, match="resource_limit"):
            s.parse_bundle(raw({"items": [None] * 8192}))
        return
    else:
        parse, limit = {
            "policy_bytes": (s.parse_policy, s.MAX_POLICY_BYTES),
            "assignment_bytes": (s.parse_assignment, s.MAX_ASSIGNMENT_BYTES),
            "reference_bytes": (s.parse_expected_reference, s.MAX_REFERENCE_BYTES),
        }[resource]
        with pytest.raises(s.SpendingError, match="resource_limit"):
            parse(b"x" * (limit + 1))
        return
    with pytest.raises(s.SpendingError):
        prepared(case)


@pytest.mark.parametrize("index,count", [(0, None), (1, None), (1, 1)])
def test_positive_reserve_cannot_promote_unqualified_zero_bound(case, index, count):
    rule(case, index, value="2")
    case["bundle"]["liabilities"][index]["payload"]["amount"] = amount("0")
    if index == 1:
        case["bundle"]["liabilities"][index]["payload"]["unknown_attempts"] = count
    r = assess(case)
    assert r.headroom_state == "HYPOTHETICAL" and r.headroom_usd is None
    assert r.effective_deductions[index].bound_claim_usd == "0"
    assert (
        r.effective_deductions[index].diagnostic_evidence_sufficiency.status == "SKIP"
    )
    assert r.diagnostic_outcome == "INDETERMINATE"


def representative_case(base):
    """31-day supplied report, eight alerts, bounded maximum-precision liabilities."""
    substitutions = {
        START: "2026-10-01T00:00:00Z",
        END: "2026-11-01T00:00:00Z",
        AT: "2026-10-31T23:59:59Z",
        HORIZON: "2026-11-01T00:00:00Z",
        "2026-11-24T11:00:00Z": "2026-10-31T23:00:00Z",
        "2026-11-24T13:00:00Z": "2026-11-01T00:00:00Z",
    }

    def substitute(value):
        if isinstance(value, dict):
            return {k: substitute(v) for k, v in value.items()}
        if isinstance(value, list):
            return [substitute(v) for v in value]
        return substitutions.get(value, value) if isinstance(value, str) else value

    case = substitute(copy.deepcopy(base))
    now = datetime(2026, 10, 31, 23, 59, 59, tzinfo=UTC)
    case["bundle"]["costs"]["payload"]["buckets"] = [
        {
            "start": datetime(2026, 10, day, tzinfo=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": min(
                datetime(2026, 10, day, tzinfo=UTC) + timedelta(days=1), now
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "amount": amount("0.000000000001"),
        }
        for day in range(1, 32)
    ]
    case["policy"]["required_alerts_usd"] = [str(i) for i in range(1, 9)]
    case["bundle"]["alerts"] = {
        "header": copy.deepcopy(case["bundle"]["control"]["header"]),
        "payload": {
            "scope": observed_scope(),
            "thresholds": [amount(str(i)) for i in range(1, 9)],
            "pagination": "complete",
        },
    }
    for o in case["bundle"]["liabilities"]:
        o["payload"]["amount"] = amount("999999999999.999999999999")
    long_project = {
        k: v[:15] + "x" * (128 - len(v[:15]))
        for k, v in case["policy"]["scope"]["project"].items()
    }
    # Preserve explicit synthetic prefixes while exercising maximum identifier size.
    long_project.update(
        provider_id="p" * 128,
        project_id="proj_synthetic_" + "p" * 113,
        organization_id="org_synthetic_" + "o" * 114,
    )
    for assigned in (case["policy"]["scope"], case["assignment"]["scope"]):
        assigned["project"] = copy.deepcopy(long_project)
    for o in (
        case["bundle"]["control"],
        case["bundle"]["costs"],
        case["bundle"]["alerts"],
        *case["bundle"]["liabilities"],
    ):
        o["payload"]["scope"].update(long_project)
    case["assignment"]["assignment_id"] = "a" * 128
    case["bundle"]["observer_reference"] = "o" * 128
    case["policy"]["policy_id"] = "p" * 128
    return case, now


def rich_issue_case(base):
    case = copy.deepcopy(base)
    case["bundle"]["control"]["payload"]["threshold"] = amount("11")
    case["policy"]["require_usage"] = True
    case["policy"]["require_authenticated_acquisition"] = True
    with_usage(case)
    case["bundle"]["usage"]["payload"].update(
        total_tokens=1,
        request_count=None,
        pagination="incomplete",
        window_coverage="unknown",
        reporting_completeness="known_incomplete",
    )
    case["bundle"]["costs"]["payload"].update(
        pagination="incomplete", reporting_completeness="known_incomplete"
    )
    for i in range(4):
        unavailable(case, i, "conflicting")
    return case


def test_representative_resource_shapes_fit_without_relaxation(case):
    big, now = representative_case(case)
    a, p, b, ref = prepared(big)
    r = s.assess_spending(
        s.serialize_bundle(b), assignment=a, policy=p, expected=ref, now=now
    )
    assert r.diagnostic_outcome == "NONCONFORMANT"
    assert len(b.costs.payload.buckets) == 31 and len(b.alerts.payload.thresholds) == 8
    assert r.headroom_usd == "-3999999999991.000000000027"
    rich = assess(rich_issue_case(case))
    assert rich.diagnostic_outcome == "INVALID_EVIDENCE"
    assert rich.threshold_conformity.status == "FAIL"
    for value, serialize, limit in (
        (a, s.serialize_assignment, s.MAX_ASSIGNMENT_BYTES),
        (p, s.serialize_policy, s.MAX_POLICY_BYTES),
        (b, s.serialize_bundle, s.MAX_BUNDLE_BYTES),
        (ref, s.serialize_expected_reference, s.MAX_REFERENCE_BYTES),
        (r, s.serialize_assessment, s.MAX_ASSESSMENT_BYTES),
        (rich, s.serialize_assessment, s.MAX_ASSESSMENT_BYTES),
    ):
        assert len(serialize(value)) < limit


def test_issue_occurrence_ceiling_is_enforced(case):
    value = assess(case).model_dump(mode="json")
    codes = sorted(s.ISSUES)
    for name in (
        "structural_validity",
        "input_reliability",
        "diagnostic_evidence_sufficiency",
    ):
        value[name].update(status="ERROR", issues=codes)
    value.update(
        effective_deductions=[],
        calculation_inputs=None,
        hypothetical_headroom_usd=None,
        headroom_usd=None,
        headroom_state="UNAVAILABLE",
        diagnostic_outcome="INVALID_EVIDENCE",
    )
    value["conditional_headroom"].update(status="SKIP", issues=["headroom_unavailable"])
    value["issues"] = list(
        dict.fromkeys(i for name in s.FINDINGS for i in value[name]["issues"])
    )
    with pytest.raises(s.SpendingError, match="resource_limit"):
        s.parse_assessment(raw(value))


@pytest.mark.parametrize("field", ["assumptions", "unresolved_uncertainties"])
def test_issue_occurrence_ceiling_includes_deduction_qualifiers(case, field):
    value = assess(case).model_dump(mode="json")
    value["effective_deductions"][0][field] = ["underlying_liability_unestablished"] * (
        s.MAX_ISSUES + 1
    )
    with pytest.raises(s.SpendingError, match="resource_limit"):
        s.parse_assessment(raw(value))


@pytest.mark.parametrize("fault", ["support", "bound_floor", "independent_as_of"])
def test_sufficient_imported_deduction_preserves_bound_qualifiers(case, fault):
    if fault == "independent_as_of":
        rule(case, 2, "independent_bound_claim")
    value = assess(case).model_dump(mode="json")
    deduction = value["effective_deductions"][2]
    if fault == "support":
        deduction["supporting_reference_sha256"] = None
    elif fault == "bound_floor":
        deduction["bound_claim_usd"] = "9"
    else:
        deduction["bound_claim_as_of"] = None
    with pytest.raises(s.SpendingError):
        s.parse_assessment(raw(value))


@pytest.mark.parametrize(
    "field",
    [
        "provider_evidence_authenticated",
        "billing_verified",
        "execution_admission_established",
        "authorises_live_execution",
        "fresh_source_verification_performed",
        "source_authorised",
        "observer_identity_authenticated",
        "liability_upper_bounds_independently_verified",
        "provider_reporting_completeness_established",
        "enforcement_propagation_verified",
        "maximum_invoice_established",
        "assessment_origin_authenticated",
    ],
)
def test_each_assurance_invariant_rejects_forgery(case, field):
    value = assess(case).model_dump(mode="json")
    value["assurance"][field] = True
    with pytest.raises(s.SpendingError):
        s.parse_assessment(raw(value))


def test_historical_limits_and_definitions_are_metadata_only(case):
    a, _, _, _ = prepared(case)
    binding = a.source_receipt.binding
    assert binding.limits.logical_calls_total == 24
    assert binding.limits.provider_attempts_total == 72
    assert binding.limits.estimated_pause_usd == "5"
    assert binding.limits.project_monthly_limit_usd == "10"
    assert binding.limits.alerts_usd == ("2", "4", "5")
    assert (
        binding.roster_fingerprint,
        binding.definition_fingerprint,
        binding.acceptance_fingerprint,
        binding.execution_fingerprint,
    ) == runtime.V3_FINGERPRINTS


def test_assessor_retains_clock_valid_error_representation(case):
    a, p, _, ref = prepared(case)
    for invalid in (b"", b"\xff", b"x" * 65537, b'{"cost":-1}'):
        r = s.assess_spending(invalid, assignment=a, policy=p, expected=ref, now=NOW)
        assert r.diagnostic_outcome == "INVALID_EVIDENCE" and r.assessed_at == AT
        assert s.parse_assessment(s.serialize_assessment(r)) == r
        assert not r.assurance.assessment_origin_authenticated


def test_qa_observed_bound_keeps_its_own_support_with_policy_reserve(case):
    rule(case, 2, value="2")
    case["policy"]["liability_rules"][2]["supporting_reference_sha256"] = "b" * 64
    r = assess(case)
    d = r.effective_deductions[2]
    assert d.effective_amount_usd == "2" and d.bound_claim_usd == "1"
    assert d.supporting_reference_sha256 == DIGEST


def test_qa_independent_zero_does_not_displace_observed_positive_bound(case):
    rule(case, 1, "independent_bound_claim", "0")
    case["policy"]["liability_rules"][1]["supporting_reference_sha256"] = "b" * 64
    r = assess(case)
    d = r.effective_deductions[1]
    assert d.effective_amount_usd == "1"
    assert d.bound_claim_usd == "1" and d.supporting_reference_sha256 == DIGEST


@pytest.mark.parametrize(
    "limit,check", [("5", "FAIL"), ("6", "FAIL"), ("6.5", "FAIL"), ("7", "PASS")]
)
def test_qa_headroom_survives_independent_billing_requirement(case, limit, check):
    case["bundle"]["control"]["payload"]["threshold"] = amount(limit)
    case["policy"]["require_final_billing"] = True
    r = assess(case)
    assert r.headroom_state == "DECISION_ELIGIBLE"
    assert r.conditional_headroom.status == check
    assert r.diagnostic_outcome == (
        "NONCONFORMANT" if check == "FAIL" else "INDETERMINATE"
    )
    assert s.parse_assessment(s.serialize_assessment(r)) == r


@pytest.mark.parametrize("required", [False, True])
def test_qa_unavailable_cost_comparison_is_not_usage_contradiction(case, required):
    with_usage(case)
    case["policy"]["require_usage"] = required
    case["bundle"]["costs"] = {"header": header("unavailable"), "payload": None}
    r = assess(case)
    assert r.usage_assessment.status == "SKIP"
    assert "window_mismatch" not in r.usage_assessment.issues
    assert r.diagnostic_outcome == "INDETERMINATE" and r.headroom_usd is None


@pytest.mark.parametrize(
    "field",
    [
        "assignment_commitment_sha256",
        "policy_commitment_sha256",
        "bundle_commitment_sha256",
        "declared_provenance",
    ],
)
def test_qa_successful_import_requires_complete_identities(case, field):
    r = assess(case)
    document = r.model_dump(mode="json")
    document[field] = None
    with pytest.raises(s.SpendingError):
        s.parse_assessment(raw(document))
    with pytest.raises(s.SpendingError):
        s.serialize_assessment(r.model_copy(update={field: None}))


@pytest.mark.parametrize("reserve", ["0", "0.5", "2", "3"])
def test_qa_reserve_and_observed_evidence_remain_distinct(case, reserve):
    rule(case, 2, value=reserve)
    case["policy"]["liability_rules"][2]["supporting_reference_sha256"] = "b" * 64
    r = assess(case)
    d = r.effective_deductions[2]
    assert d.effective_amount_usd == (reserve if reserve in {"2", "3"} else "1")
    assert d.selected_bound_source == "observation"
    assert d.bound_claim_usd == "1" and d.supporting_reference_sha256 == DIGEST
    assert d.observed_evidence.observation.payload.amount.value == "1"
    assert d.observed_evidence.observation.header.supporting_artifact_sha256 == DIGEST
    assert d.observed_evidence.declared_provenance == "synthetic_test"
    assert d.observed_evidence.qualification.status == "PASS"
    assert d.policy_evidence.rule.allowance_usd == reserve
    assert d.policy_evidence.rule.supporting_reference_sha256 == "b" * 64
    assert d.policy_evidence.qualification.status == "SKIP"
    assert d.policy_evidence.qualification.requirement == "INFORMATIONAL"
    assert s.parse_assessment(s.serialize_assessment(r)) == r


@pytest.mark.parametrize(
    "observed,policy,selected",
    [
        ("1", "2", "policy"),
        ("2", "1", "observation"),
        ("1", "0", "observation"),
        ("0", "1", "policy"),
        ("1", "1", "observation"),
    ],
)
def test_qa_qualified_bounds_select_larger_without_mixing_attribution(
    case, observed, policy, selected
):
    case["bundle"]["liabilities"][1]["payload"]["amount"] = amount(observed)
    rule(case, 1, "independent_bound_claim", policy)
    case["policy"]["liability_rules"][1]["supporting_reference_sha256"] = "b" * 64
    r = assess(case)
    d = r.effective_deductions[1]
    expected = max((observed, policy), key=int)
    assert d.effective_amount_usd == d.bound_claim_usd == expected
    assert d.selected_bound_source == selected
    assert d.supporting_reference_sha256 == (
        DIGEST if selected == "observation" else "b" * 64
    )
    assert d.bound_claim_as_of == (None if selected == "observation" else AT)
    assert (
        d.observed_evidence.qualification.status
        == d.policy_evidence.qualification.status
        == "PASS"
    )
    assert d.observed_evidence.observation.payload.amount.value == observed
    assert d.policy_evidence.rule.allowance_usd == policy
    assert s.parse_assessment(s.serialize_assessment(r)) == r


@pytest.mark.parametrize("count", [None, 0, 1])
@pytest.mark.parametrize(
    "observed_coverage,policy_coverage",
    [
        ("all_inflight_exposure", "known_attempts_only"),
        ("known_attempts_only", "all_inflight_exposure"),
        ("known_attempts_only", "known_attempts_only"),
    ],
)
def test_qa_attempt_coverage_is_qualified_per_bound(
    case, count, observed_coverage, policy_coverage
):
    case["bundle"]["liabilities"][1]["payload"].update(
        unknown_attempts=count, attempt_coverage=observed_coverage
    )
    rule(case, 1, "independent_bound_claim", "2")
    case["policy"]["liability_rules"][1]["attempt_coverage"] = policy_coverage
    d = assess(case).effective_deductions[1]
    assert d.observed_evidence.observation.payload.attempt_coverage == observed_coverage
    assert d.policy_evidence.rule.attempt_coverage == policy_coverage
    assert d.observed_evidence.qualification.status == (
        "PASS" if observed_coverage == "all_inflight_exposure" else "SKIP"
    )
    assert d.policy_evidence.qualification.status == (
        "PASS" if policy_coverage == "all_inflight_exposure" else "SKIP"
    )
    assert d.diagnostic_evidence_sufficiency.status == "SKIP"
    assert d.attempt_coverage == (
        observed_coverage
        if d.selected_bound_source == "observation"
        else policy_coverage
    )


@pytest.mark.parametrize("index,count", [(0, None), (1, None), (1, 1)])
@pytest.mark.parametrize("zero_source", ["observation", "policy"])
def test_qa_zero_bound_cannot_be_hidden_by_another_positive_bound(
    case, index, count, zero_source
):
    case["bundle"]["liabilities"][index]["payload"]["unknown_attempts"] = count
    rule(
        case, index, "independent_bound_claim", "0" if zero_source == "policy" else "2"
    )
    case["bundle"]["liabilities"][index]["payload"]["amount"] = amount(
        "0" if zero_source == "observation" else "1"
    )
    r = assess(case)
    d = r.effective_deductions[index]
    assert d.selected_bound_source != zero_source
    assert d.diagnostic_evidence_sufficiency.status == "SKIP"
    assert r.headroom_state == "HYPOTHETICAL" and r.headroom_usd is None
    assert r.diagnostic_outcome == "INDETERMINATE"


@pytest.mark.parametrize(
    "when,status", [("2026-11-24T11:58:00Z", "SKIP"), ("2026-11-24T12:00:01Z", "ERROR")]
)
def test_qa_stale_or_future_policy_bound_cannot_hide_behind_observed_bound(
    case, when, status
):
    rule(case, 2, "independent_bound_claim")
    case["policy"]["liability_rules"][2]["bound_claim_as_of"] = when
    r = assess(case)
    d = r.effective_deductions[2]
    assert d.selected_bound_source == "observation"
    assert (
        d.policy_evidence.freshness.status
        == d.policy_evidence.qualification.status
        == status
    )
    assert (
        d.observed_evidence.freshness.status
        == d.observed_evidence.qualification.status
        == "PASS"
    )
    assert d.diagnostic_evidence_sufficiency.status == status
    assert r.headroom_usd is None
    assert s.parse_assessment(s.serialize_assessment(r)) == r


@pytest.mark.parametrize(
    "fault",
    [
        "support",
        "coverage",
        "provenance",
        "amount",
        "qualification",
        "policy_scope",
        "selected",
        "missing_field",
        "unknown_field",
    ],
)
def test_qa_imported_claim_attribution_is_consistent(case, fault):
    rule(case, 1, "independent_bound_claim")
    r = assess(case)
    document = r.model_dump(mode="json")
    d = document["effective_deductions"][1]
    if fault == "support":
        d["observed_evidence"]["observation"]["header"][
            "supporting_artifact_sha256"
        ] = None
    elif fault == "coverage":
        d["policy_evidence"]["rule"]["attempt_coverage"] = "known_attempts_only"
    elif fault == "provenance":
        d["observed_evidence"]["declared_provenance"] = "manual_declaration"
    elif fault == "amount":
        d["policy_evidence"]["rule"]["allowance_usd"] = "0"
        d["observed_evidence"]["observation"]["payload"]["unknown_attempts"] = 1
        d["unknown_attempts"] = 1
    elif fault == "qualification":
        d["policy_evidence"]["qualification"].update(
            status="SKIP", issues=["bound_missing"]
        )
    elif fault == "policy_scope":
        d["policy_evidence"]["scope"]["project"]["project_id"] = "wrong"
    elif fault == "selected":
        d["selected_bound_source"] = "observation"
    elif fault == "missing_field":
        del d["policy_evidence"]
    else:
        d["policy_evidence"]["extra"] = "PRIVATE"
    with pytest.raises(s.SpendingError):
        s.parse_assessment(raw(document))
    copied = r.model_copy(
        update={
            "effective_deductions": tuple(
                s.EffectiveDeduction.model_construct(**v)
                for v in document["effective_deductions"]
            )
        }
    )
    with pytest.raises(s.SpendingError):
        s.serialize_assessment(copied)


@pytest.mark.parametrize(
    "flag",
    [
        "require_authenticated_acquisition",
        "require_verified_liability_bounds",
        "require_verified_propagation",
        "require_final_billing",
        "require_organization_headroom",
        "require_cost_comparison",
    ],
)
@pytest.mark.parametrize(
    "threshold,check,h",
    [
        ("5", "FAIL", "-1"),
        ("6", "FAIL", "0"),
        ("6.5", "FAIL", "0.5"),
        ("7", "PASS", "1"),
    ],
)
def test_qa_all_independent_requirements_preserve_headroom(
    case, flag, threshold, check, h
):
    case["policy"][flag] = True
    case["bundle"]["control"]["payload"]["threshold"] = amount(threshold)
    r = assess(case)
    assert r.headroom_state == "DECISION_ELIGIBLE" and r.headroom_usd == h
    assert r.conditional_headroom.status == check
    assert r.diagnostic_outcome == (
        "NONCONFORMANT" if check == "FAIL" else "INDETERMINATE"
    )
    assert not any(v for _, v in r.assurance if type(v) is bool)
    assert s.parse_assessment(s.serialize_assessment(r)) == r


@pytest.mark.parametrize("threshold", ["5", "6", "6.5", "7"])
def test_qa_unresolved_liability_still_cannot_gate_despite_independent_requirements(
    case, threshold
):
    for flag in (
        "require_authenticated_acquisition",
        "require_verified_liability_bounds",
        "require_verified_propagation",
        "require_final_billing",
        "require_organization_headroom",
        "require_cost_comparison",
    ):
        case["policy"][flag] = True
    case["bundle"]["control"]["payload"]["threshold"] = amount(threshold)
    unavailable(case, 2)
    rule(case, 2, value="1")
    r = assess(case)
    assert r.headroom_state == "HYPOTHETICAL"
    assert r.conditional_headroom.status == "SKIP" and r.headroom_usd is None
    assert r.diagnostic_outcome == "INDETERMINATE"


def test_qa_import_cannot_reinstate_superseded_all_required_gate(case):
    case["policy"]["require_final_billing"] = True
    case["bundle"]["control"]["payload"]["threshold"] = amount("5")
    r = assess(case)
    document = r.model_dump(mode="json")
    document.update(
        headroom_state="HYPOTHETICAL",
        headroom_usd=None,
        diagnostic_outcome="INDETERMINATE",
    )
    document["conditional_headroom"].update(status="SKIP", issues=["hypothetical_only"])
    document["issues"] = list(
        dict.fromkeys(i for name in s.FINDINGS for i in document[name]["issues"])
    )
    with pytest.raises(s.SpendingError):
        s.parse_assessment(raw(document))


@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize(
    "fault",
    ["none", "scope", "counter", "conflicting", "future", "window", "malformed"],
)
def test_qa_usage_faults_remain_independent_when_costs_are_unavailable(
    case, required, fault
):
    with_usage(case)
    case["policy"]["require_usage"] = required
    case["bundle"]["costs"] = {"header": header("unavailable"), "payload": None}
    usage = case["bundle"]["usage"]
    if fault == "scope":
        usage["payload"]["scope"]["project_id"] = "wrong"
    elif fault == "counter":
        usage["payload"]["total_tokens"] = 1
    elif fault == "conflicting":
        usage.update(header=header("conflicting"), payload=None)
    elif fault == "future":
        usage["header"]["stamp"]["collection_ended_at"] = "2026-11-24T12:00:01Z"
    elif fault == "window":
        usage["payload"]["window"]["start"] = "2026-11-02T00:00:00Z"
    elif fault == "malformed":
        usage["payload"]["extra"] = "PRIVATE"
        a, p, _, ref = prepared({**case, "bundle": {**case["bundle"], "usage": None}})
        r = s.assess_spending(
            raw(case["bundle"]), assignment=a, policy=p, expected=ref, now=NOW
        )
        assert r.diagnostic_outcome == "INVALID_EVIDENCE"
        return
    r = assess(case)
    assert r.headroom_usd is None
    assert r.diagnostic_outcome == (
        "INDETERMINATE" if fault == "none" else "INVALID_EVIDENCE"
    )
    assert r.input_reliability.status == ("PASS" if fault == "none" else "ERROR")


@pytest.mark.parametrize("required", [False, True])
def test_qa_available_incompatible_cost_window_remains_error(case, required):
    with_usage(case)
    case["policy"]["require_usage"] = required
    costs = case["bundle"]["costs"]["payload"]
    costs["window"]["end"] = costs["buckets"][0]["end"] = "2026-11-24T11:59:59Z"
    r = assess(case)
    assert r.usage_assessment.status == "ERROR"
    assert "window_mismatch" in r.usage_assessment.issues
    assert r.input_reliability.status == "ERROR"


@pytest.mark.parametrize(
    "stage,identities",
    [
        ("policy", (False, False, False)),
        ("assignment", (True, False, False)),
        ("reference", (True, True, False)),
        ("bundle", (True, True, False)),
        ("agreement", (True, True, True)),
    ],
)
def test_qa_legitimate_invalid_input_identity_prefixes_roundtrip(
    case, stage, identities
):
    a, p, b, ref = prepared(case)
    data = s.serialize_bundle(b)
    if stage == "policy":
        p = p.model_copy(update={"max_project_threshold_usd": "11"})
    elif stage == "assignment":
        a = a.model_copy(update={"audience": "invalid space"})
    elif stage == "reference":
        ref = ref.model_copy(update={"assignment_id": "invalid space"})
    elif stage == "bundle":
        data = b"malformed"
    else:
        ref = ref.model_copy(update={"bundle_commitment_sha256": "f" * 64})
    r = s.assess_spending(data, assignment=a, policy=p, expected=ref, now=NOW)
    assert r.diagnostic_outcome == "INVALID_EVIDENCE"
    assert (
        tuple(
            v is not None
            for v in (
                r.policy_commitment_sha256,
                r.assignment_commitment_sha256,
                r.bundle_commitment_sha256,
            )
        )
        == identities
    )
    assert (r.declared_provenance is not None) == identities[2]
    assert s.parse_assessment(s.serialize_assessment(r)) == r


@pytest.mark.parametrize("kind", ["FAIL", "SKIP", "ERROR"])
@pytest.mark.parametrize(
    "field",
    [
        "assignment_commitment_sha256",
        "policy_commitment_sha256",
        "bundle_commitment_sha256",
        "declared_provenance",
    ],
)
def test_qa_binding_success_requires_identities_even_when_overall_unsuccessful(
    case, kind, field
):
    if kind == "FAIL":
        case["bundle"]["control"]["payload"]["threshold"] = amount("5")
    elif kind == "SKIP":
        case["policy"]["require_final_billing"] = True
    else:
        case["bundle"]["costs"]["payload"]["scope"]["project_id"] = "wrong"
    r = assess(case)
    assert (
        r.assignment_policy_binding.status
        == r.expected_reference_agreement.status
        == "PASS"
    )
    document = r.model_dump(mode="json")
    document[field] = None
    with pytest.raises(s.SpendingError):
        s.parse_assessment(raw(document))
    with pytest.raises(s.SpendingError):
        s.serialize_assessment(r.model_copy(update={field: None}))


@pytest.mark.parametrize(
    "fault",
    [
        "policy_order",
        "bundle_without_provenance",
        "provenance_without_bundle",
        "structural_pass",
        "binding_pass",
        "reference_pass",
    ],
)
def test_qa_invalid_input_representation_still_requires_consistent_identity_progression(
    case, fault
):
    a, p, _, ref = prepared(case)
    r = s.assess_spending(b"malformed", assignment=a, policy=p, expected=ref, now=NOW)
    document = r.model_dump(mode="json")
    if fault == "policy_order":
        document["policy_commitment_sha256"] = None
    elif fault == "bundle_without_provenance":
        document["bundle_commitment_sha256"] = DIGEST
    elif fault == "provenance_without_bundle":
        document["declared_provenance"] = "synthetic_test"
    else:
        key = {
            "structural_pass": "structural_validity",
            "binding_pass": "assignment_policy_binding",
            "reference_pass": "expected_reference_agreement",
        }[fault]
        document[key].update(status="PASS", issues=[])
        document["issues"] = list(
            dict.fromkeys(i for name in s.FINDINGS for i in document[name]["issues"])
        )
    with pytest.raises(s.SpendingError):
        s.parse_assessment(raw(document))


def _lower_serialized_deduction(result, index, value):
    document = result.model_dump(mode="json")
    document["effective_deductions"][index]["effective_amount_usd"] = value
    document["calculation_inputs"]["deductions_usd"][index] = value
    document.update(
        headroom_usd="4",
        hypothetical_headroom_usd="4",
        diagnostic_outcome="CONDITIONALLY_CONFORMANT",
    )
    document["conditional_headroom"].update(status="PASS", issues=[])
    document["issues"] = list(
        dict.fromkeys(i for name in s.FINDINGS for i in document[name]["issues"])
    )
    return document


@pytest.mark.parametrize("rule_source", ["policy_reserve", "independent_bound_claim"])
def test_final_qa_retained_policy_cannot_be_reduced_with_consistent_arithmetic(
    case, rule_source
):
    index = s.KINDS.index("other_consumers")
    rule(case, index, source=rule_source, value="6")
    result = assess(case)
    assert result.effective_deductions[index].effective_amount_usd == "6"
    assert result.headroom_usd == "-1"
    assert result.diagnostic_outcome == "NONCONFORMANT"
    assert s.parse_assessment(s.serialize_assessment(result)) == result
    document = _lower_serialized_deduction(result, index, "1")
    with pytest.raises(s.SpendingError):
        s.parse_assessment(raw(document))


@pytest.mark.parametrize("index", range(4))
@pytest.mark.parametrize("fault", ["future", "reversed", "provider_after_end"])
def test_final_qa_successful_freshness_cannot_contradict_retained_timestamps(
    case, index, fault
):
    result = assess(case)
    assert result.diagnostic_outcome == "CONDITIONALLY_CONFORMANT"
    document = result.model_dump(mode="json")
    stamp = document["effective_deductions"][index]["observed_evidence"]["observation"][
        "header"
    ]["stamp"]
    if fault == "future":
        stamp["collection_ended_at"] = "2026-11-24T12:00:01Z"
    elif fault == "reversed":
        stamp["collection_started_at"] = "2026-11-24T12:00:01Z"
    else:
        stamp["provider_timestamp"] = "2026-11-24T12:00:01Z"
    with pytest.raises(s.SpendingError):
        s.parse_assessment(raw(document))
    with pytest.raises(s.SpendingError):
        s.serialize_assessment(s.OfflineSpendingAssessment.model_construct(**document))


@pytest.mark.parametrize("index", range(4))
@pytest.mark.parametrize("rule_source", ["policy_reserve", "independent_bound_claim"])
@pytest.mark.parametrize("state", ["present", "absent", "unqualified_policy"])
def test_final_qa_policy_floor_survives_hypothetical_and_unselected_claims(
    case, index, rule_source, state
):
    rule(case, index, source=rule_source, value="6")
    if state == "absent":
        unavailable(case, index, "absent")
    elif state == "unqualified_policy" and rule_source == "independent_bound_claim":
        case["policy"]["liability_rules"][index]["bound_claim_as_of"] = (
            "2026-11-24T11:58:00Z"
        )
    elif state == "unqualified_policy":
        case["bundle"]["liabilities"][index]["header"]["supporting_artifact_sha256"] = (
            None
        )
    result = assess(case)
    deduction = result.effective_deductions[index]
    assert deduction.effective_amount_usd == "6"
    assert s.parse_assessment(s.serialize_assessment(result)) == result
    document = _lower_serialized_deduction(result, index, "1")
    if result.headroom_state == "HYPOTHETICAL":
        document["headroom_usd"] = None
        document["diagnostic_outcome"] = "INDETERMINATE"
        document["conditional_headroom"] = result.conditional_headroom.model_dump(
            mode="json"
        )
        document["issues"] = list(result.issues)
    with pytest.raises(s.SpendingError):
        s.parse_assessment(raw(document))
    with pytest.raises(s.SpendingError):
        s.serialize_assessment(s.OfflineSpendingAssessment.model_construct(**document))


@pytest.mark.parametrize("index", range(4))
@pytest.mark.parametrize(
    "rule_source", ["declared_upper_bound", "policy_reserve", "independent_bound_claim"]
)
@pytest.mark.parametrize(
    "fault", ["missing", "unsupported", "conflicting", "zero", "contradictory"]
)
def test_final_qa_resolution_preserves_legitimate_nonconformant_evidence_roundtrips(
    case, index, rule_source, fault
):
    if rule_source != "declared_upper_bound":
        rule(case, index, source=rule_source, value="0" if fault == "zero" else "2")
    observation = case["bundle"]["liabilities"][index]
    if fault == "missing":
        unavailable(case, index)
    elif fault == "unsupported":
        observation["header"]["supporting_artifact_sha256"] = None
    elif fault == "conflicting":
        unavailable(case, index, "conflicting")
    elif fault == "zero":
        observation["payload"].update(amount=amount("0"))
        if index == 1:
            observation["payload"]["unknown_attempts"] = None
    else:
        observation["payload"].update(amount=amount("3"), basis="amount_claim")
    result = assess(case)
    assert s.parse_assessment(s.serialize_assessment(result)) == result
    if fault == "conflicting" or (
        fault == "contradictory" and rule_source == "independent_bound_claim"
    ):
        assert result.effective_deductions[index].effective_amount_usd is None
        assert result.diagnostic_outcome == "INVALID_EVIDENCE"
    if fault == "missing" and rule_source == "policy_reserve":
        assert result.headroom_state == "HYPOTHETICAL"
    if fault == "missing" and rule_source == "declared_upper_bound":
        assert result.headroom_state == "UNAVAILABLE"


@pytest.mark.parametrize("index", range(4))
@pytest.mark.parametrize("fault", ["future", "reversed", "provider_after_end"])
@pytest.mark.parametrize(
    "availability", ["present", "unknown", "unavailable", "conflicting"]
)
def test_final_qa_invalid_timestamps_with_error_findings_roundtrip(
    case, index, fault, availability
):
    if availability != "present":
        unavailable(case, index, availability)
    stamp = case["bundle"]["liabilities"][index]["header"]["stamp"]
    if fault == "future":
        stamp["collection_ended_at"] = "2026-11-24T12:00:01Z"
    elif fault == "reversed":
        stamp["collection_started_at"] = "2026-11-24T12:00:01Z"
    else:
        stamp["provider_timestamp"] = "2026-11-24T12:00:01Z"
    result = assess(case)
    assert result.diagnostic_outcome == "INVALID_EVIDENCE"
    freshness = result.effective_deductions[index].observation_freshness
    assert freshness.status == "ERROR"
    assert freshness.issues == (
        "conflicting_observation"
        if availability == "conflicting"
        else "future_or_reversed_timestamp",
    )
    assert s.parse_assessment(s.serialize_assessment(result)) == result


@pytest.mark.parametrize("index", range(4))
@pytest.mark.parametrize("provider_time", [None, AT, "2026-11-24T11:59:59Z"])
def test_final_qa_timestamp_boundaries_and_earlier_provider_time_roundtrip(
    case, index, provider_time
):
    case["bundle"]["liabilities"][index]["header"]["stamp"]["provider_timestamp"] = (
        provider_time
    )
    result = assess(case)
    assert result.diagnostic_outcome == "CONDITIONALLY_CONFORMANT"
    assert s.parse_assessment(s.serialize_assessment(result)) == result
