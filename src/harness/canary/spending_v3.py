"""Detached conditional spending diagnostics; no acquisition or execution authority.

Trust the caller's independent assignment/policy/reference and explicit clock.
Commitments establish byte agreement, never provider origin or independent custody.
Assessment parsing validates representation only. Recompute for trusted reliance.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Context, Decimal, DecimalException, localcontext
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, Field, model_validator

from harness.canary.runtime_v3 import (
    V3,
    Digest,
    Frozen,
    SourceApprovalReceipt,
    validate_binding,
)
from harness.core.fingerprints import CANONICAL_VERSION, fingerprint

MAX_ASSIGNMENT_BYTES = 32_768
MAX_POLICY_BYTES = 16_384
MAX_REFERENCE_BYTES = 4_096
MAX_BUNDLE_BYTES = MAX_ASSESSMENT_BYTES = 65_536
MAX_DEPTH = 24
MAX_VALUES = 8_192
MAX_ISSUES = 256
KINDS = (
    "incurred_unreported",
    "inflight_unknown",
    "other_consumers",
    "remaining_canary",
)
PROFILES = {
    "spending-manual-claims-v1": "manual_declaration",
    "spending-operator-export-v1": "operator_supplied_export",
    "openai-admin-spending-claims-2026-11-24-v1": "claimed_administrative_api",
    "spending-synthetic-fixture-v1": "synthetic_test",
}
Profile = Literal[
    "spending-manual-claims-v1",
    "spending-operator-export-v1",
    "openai-admin-spending-claims-2026-11-24-v1",
    "spending-synthetic-fixture-v1",
]
Provenance = Literal[
    "manual_declaration",
    "operator_supplied_export",
    "claimed_administrative_api",
    "synthetic_test",
]
Kind = Literal[
    "incurred_unreported", "inflight_unknown", "other_consumers", "remaining_canary"
]
Availability = Literal["present", "unknown", "unavailable", "conflicting"]
Pagination = Literal["complete", "incomplete", "unknown", "not_applicable"]
Completeness = Literal["unknown", "known_incomplete"]
AttemptCoverage = Literal[
    "all_inflight_exposure", "known_attempts_only", "not_applicable"
]
Status = Literal["PASS", "FAIL", "ERROR", "SKIP"]
Requirement = Literal["REQUIRED", "INFORMATIONAL"]
Outcome = Literal[
    "CONDITIONALLY_CONFORMANT", "NONCONFORMANT", "INDETERMINATE", "INVALID_EVIDENCE"
]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]
Counter = Annotated[int, Field(ge=0, le=10**15)]
Seconds = Annotated[int, Field(ge=1, le=86_400)]


class SpendingError(ValueError):
    """Fixed categories only; never retain untrusted validation diagnostics."""

    def __init__(self, code: str):
        self.code = (
            code
            if code
            in {
                "invalid_input",
                "noncanonical_input",
                "resource_limit",
                "invalid_clock",
                "arithmetic_error",
            }
            else "invalid_input"
        )
        super().__init__(self.code)


def _time(value: str) -> datetime:
    try:
        if (
            re.fullmatch(
                r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value
            )
            is None
        ):
            raise ValueError
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except (ValueError, TypeError):
        raise ValueError("invalid_timestamp") from None


def _timestamp(value: str) -> str:
    _time(value)
    return value


Timestamp = Annotated[str, AfterValidator(_timestamp)]


def _money(value: str, *, signed: bool = False) -> str:
    digits = 14 if signed else 12
    pattern = (
        r"-?" if signed else ""
    ) + rf"(?:0|[1-9][0-9]{{0,{digits - 1}}})(?:\.[0-9]{{0,11}}[1-9])?"
    if re.fullmatch(pattern, value) is None or value == "-0":
        raise ValueError("invalid_money")
    return value


Money = Annotated[str, Field(max_length=25), AfterValidator(_money)]
SignedMoney = Annotated[
    str, Field(max_length=28), AfterValidator(lambda v: _money(v, signed=True))
]


def _context() -> Context:
    context = Context(prec=64, Emin=-96, Emax=96, rounding=ROUND_CEILING)
    for signal in context.traps:
        context.traps[signal] = True
    return context


def _text(value: Decimal) -> str:
    result = format(value, "f")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    return "0" if value == 0 else result


class ProjectIdentity(Frozen):
    provider_id: Identifier
    organization_id: Identifier
    project_id: Identifier


class Window(Frozen):
    start: Timestamp
    end: Timestamp

    @model_validator(mode="after")
    def _order(self) -> Window:
        if _time(self.start) >= _time(self.end):
            raise ValueError("invalid_window")
        return self


class BillingPeriod(Window):
    reset_convention: Literal[
        "utc_calendar_month", "independent_explicit_monthly_period"
    ]
    reset_reference_sha256: Digest

    @model_validator(mode="after")
    def _period(self) -> BillingPeriod:
        start, end = _time(self.start), _time(self.end)
        if self.reset_convention == "utc_calendar_month":
            next_month = (
                start.replace(year=start.year + 1, month=1)
                if start.month == 12
                else start.replace(month=start.month + 1)
            )
            if (start.day, start.hour, start.minute, start.second) != (
                1,
                0,
                0,
                0,
            ) or next_month != end:
                raise ValueError("invalid_month")
        elif not timedelta(days=27) <= end - start <= timedelta(days=32):
            raise ValueError("invalid_month")
        return self


class SpendingScope(Frozen):
    project: ProjectIdentity
    environment: Literal["external_claim", "synthetic_fixture"]
    billing_period: BillingPeriod
    horizon_end: Timestamp

    @model_validator(mode="after")
    def _horizon(self) -> SpendingScope:
        if (
            not _time(self.billing_period.start)
            < _time(self.horizon_end)
            <= _time(self.billing_period.end)
        ):
            raise ValueError("invalid_horizon")
        return self


class SpendingEvidenceAssignment(Frozen):
    schema_id: Literal["canary-spending-assignment-v1"] = (
        "canary-spending-assignment-v1"
    )
    assignment_id: Identifier
    audience: Identifier
    purpose: Literal["prospective-offline-spending-diagnostic"] = (
        "prospective-offline-spending-diagnostic"
    )
    source_receipt: SourceApprovalReceipt
    source_receipt_sha256: Digest
    scope: SpendingScope
    observation_profile: Profile
    policy_commitment_sha256: Digest
    opens_at: Timestamp
    closes_at: Timestamp

    @model_validator(mode="after")
    def _binding(self) -> SpendingEvidenceAssignment:
        # Metadata hashes may read unchanged definition source; no checkout inspection.
        validate_binding(self.source_receipt.binding)
        if (
            self.source_receipt.binding.identifier != V3
            or self.source_receipt_sha256
            != fingerprint(self.source_receipt.model_dump(mode="json"))
        ):
            raise ValueError("invalid_source_binding")
        if (
            not _time(self.scope.billing_period.start)
            <= _time(self.opens_at)
            < _time(self.closes_at)
            <= _time(self.scope.horizon_end)
        ):
            raise ValueError("invalid_assignment_window")
        synthetic = self.observation_profile == "spending-synthetic-fixture-v1"
        if synthetic != (self.scope.environment == "synthetic_fixture"):
            raise ValueError("invalid_environment")
        project = self.scope.project
        if synthetic and not (
            project.project_id.startswith("proj_synthetic_")
            and project.organization_id.startswith("org_synthetic_")
        ):
            raise ValueError("invalid_synthetic_identity")
        if self.observation_profile.startswith("openai-admin-") and (
            project.provider_id != "openai"
            or not re.fullmatch(r"proj_[A-Za-z0-9_-]+", project.project_id)
            or not re.fullmatch(r"org[-_][A-Za-z0-9_-]+", project.organization_id)
        ):
            raise ValueError("invalid_profile_identity")
        return self


class ObservationStamp(Frozen):
    collection_started_at: Timestamp
    collection_ended_at: Timestamp
    provider_timestamp: Timestamp | None


class ObservationHeader(Frozen):
    availability: Availability
    stamp: ObservationStamp | None
    supporting_artifact_sha256: Digest | None


class MoneyAmount(Frozen):
    currency: Literal["USD"] = "USD"
    unit: Literal["major", "integer_cents"]
    value: Money

    @model_validator(mode="after")
    def _unit(self) -> MoneyAmount:
        if self.unit == "integer_cents" and "." in self.value:
            raise ValueError("fractional_cents")
        return self


def _major(value: MoneyAmount) -> Decimal:
    with localcontext(_context()):
        return Decimal(value.value) / (100 if value.unit == "integer_cents" else 1)


class ObservedScope(Frozen):
    provider_id: Identifier
    organization_id: Identifier
    project_id: Identifier | None
    level: Literal["project", "organization"]


class ControlValues(Frozen):
    scope: ObservedScope
    kind: Literal["hard_limit", "soft_alert", "unknown", "unsupported"]
    threshold: MoneyAmount | None
    interval: Literal["month", "unknown", "unsupported"]
    enforcement: Literal["enforcing", "inactive", "unknown", "unsupported"]


class AlertValues(Frozen):
    scope: ObservedScope
    thresholds: tuple[MoneyAmount, ...] = Field(max_length=8)
    pagination: Pagination


class CostBucket(Window):
    amount: MoneyAmount | None

    @model_validator(mode="after")
    def _unit(self) -> CostBucket:
        if self.amount is not None and self.amount.unit != "major":
            raise ValueError("cost_unit")
        return self


class CostValues(Frozen):
    scope: ObservedScope
    window: Window
    traffic_scope: Literal["all_project_traffic", "restricted", "unknown"]
    pagination: Pagination
    reporting_completeness: Completeness
    buckets: tuple[CostBucket, ...] = Field(max_length=32)


class UsageValues(Frozen):
    scope: ObservedScope
    window: Window
    traffic_scope: Literal[
        "all_project_traffic", "project_completions_family", "restricted", "unknown"
    ]
    pagination: Pagination
    reporting_completeness: Completeness
    window_coverage: Literal["continuous", "incomplete", "unknown"]
    request_count: Counter | None
    input_tokens: Counter | None
    output_tokens: Counter | None
    total_tokens: Counter | None


class LiabilityValues(Frozen):
    kind: Kind
    scope: ObservedScope
    exposure_window: Window
    amount: MoneyAmount | None
    basis: Literal["amount_claim", "upper_bound_claim"]
    unknown_attempts: Counter | None
    attempt_coverage: AttemptCoverage

    @model_validator(mode="after")
    def _attempts(self) -> LiabilityValues:
        if self.amount is not None and self.amount.unit != "major":
            raise ValueError("liability_unit")
        if self.kind != "inflight_unknown" and (
            self.unknown_attempts is not None
            or self.attempt_coverage != "not_applicable"
        ):
            raise ValueError("invalid_attempt_coverage")
        return self


class _Observation(Frozen):
    header: ObservationHeader

    @model_validator(mode="after")
    def _presence(self) -> _Observation:
        if (self.header.availability == "present") != (
            getattr(self, "payload", None) is not None
        ):
            raise ValueError("invalid_payload_presence")
        return self


class ControlObservation(_Observation):
    payload: ControlValues | None


class AlertObservation(_Observation):
    payload: AlertValues | None


class CostObservation(_Observation):
    payload: CostValues | None


class UsageObservation(_Observation):
    payload: UsageValues | None


class LiabilityObservation(_Observation):
    payload: LiabilityValues | None


class SpendingObservationBundle(Frozen):
    schema_id: Literal["canary-spending-observation-bundle-v1"] = (
        "canary-spending-observation-bundle-v1"
    )
    canonicalization: Literal["replay-canonical-json-v1"] = "replay-canonical-json-v1"
    assignment_commitment_sha256: Digest
    policy_commitment_sha256: Digest
    observation_profile: Profile
    declared_provenance: Provenance
    observer_reference: Identifier
    control: ControlObservation
    alerts: AlertObservation | None
    costs: CostObservation
    usage: UsageObservation | None
    liabilities: tuple[LiabilityObservation | None, ...] = Field(
        min_length=4, max_length=4
    )


class LiabilityRule(Frozen):
    kind: Kind
    source: Literal["declared_upper_bound", "policy_reserve", "independent_bound_claim"]
    allowance_usd: Money | None
    supporting_reference_sha256: Digest | None
    bound_claim_as_of: Timestamp | None
    attempt_coverage: AttemptCoverage

    @model_validator(mode="after")
    def _basis(self) -> LiabilityRule:
        if self.source == "declared_upper_bound":
            if (
                any(
                    v is not None
                    for v in (
                        self.allowance_usd,
                        self.supporting_reference_sha256,
                        self.bound_claim_as_of,
                    )
                )
                or self.attempt_coverage != "not_applicable"
            ):
                raise ValueError("invalid_rule")
        elif self.allowance_usd is None or self.supporting_reference_sha256 is None:
            raise ValueError("missing_allowance")
        if self.source == "independent_bound_claim":
            if self.bound_claim_as_of is None or (
                self.kind != "inflight_unknown"
                and self.attempt_coverage != "not_applicable"
            ):
                raise ValueError("invalid_bound_claim")
        elif (
            self.bound_claim_as_of is not None
            or self.attempt_coverage != "not_applicable"
        ):
            raise ValueError("invalid_rule")
        return self


class OfflineSpendingDiagnosticPolicy(Frozen):
    schema_id: Literal["canary-offline-spending-diagnostic-policy-v1"] = (
        "canary-offline-spending-diagnostic-policy-v1"
    )
    policy_id: Identifier
    scope: SpendingScope
    valid_from: Timestamp
    valid_until: Timestamp
    accepted_provenances: tuple[Provenance, ...] = Field(min_length=1, max_length=4)
    max_project_threshold_usd: Money
    required_enforcement: Literal["enforcing"] = "enforcing"
    required_alerts_usd: tuple[Money, ...] = Field(max_length=8)
    max_control_age_seconds: Seconds
    max_cost_age_seconds: Seconds
    max_usage_age_seconds: Seconds
    max_liability_age_seconds: Seconds
    max_collection_span_seconds: int = Field(ge=1, le=3600)
    max_cost_window_lag_seconds: Seconds
    max_usage_window_lag_seconds: Seconds
    require_usage: bool
    reporting_requirement: Literal[
        "bounded_gap_assumptions", "complete_reporting_required"
    ]
    liability_rules: tuple[LiabilityRule, ...] = Field(min_length=4, max_length=4)
    safety_margin_usd: Money
    minimum_residual_headroom_usd: Money
    require_authenticated_acquisition: bool
    require_verified_liability_bounds: bool
    require_verified_propagation: bool
    require_final_billing: bool
    require_organization_headroom: bool
    require_cost_comparison: bool

    @model_validator(mode="after")
    def _rules(self) -> OfflineSpendingDiagnosticPolicy:
        if not _time(self.valid_from) < _time(self.valid_until) or not Decimal(
            0
        ) < Decimal(self.max_project_threshold_usd) <= Decimal(10):
            raise ValueError("invalid_policy")
        if (
            len(set(self.accepted_provenances)) != len(self.accepted_provenances)
            or tuple(r.kind for r in self.liability_rules) != KINDS
        ):
            raise ValueError("invalid_rules")
        if self.required_alerts_usd != tuple(
            sorted(set(self.required_alerts_usd), key=Decimal)
        ):
            raise ValueError("invalid_alert_order")
        return self


class ExpectedSpendingEvidenceReference(Frozen):
    schema_id: Literal["canary-expected-spending-reference-v1"] = (
        "canary-expected-spending-reference-v1"
    )
    assignment_id: Identifier
    assignment_commitment_sha256: Digest
    policy_commitment_sha256: Digest
    observation_profile: Profile
    bundle_commitment_sha256: Digest


def _plain(value: Any) -> Any:
    remaining = MAX_VALUES

    def visit(item: Any, depth: int) -> Any:
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > MAX_DEPTH:
            raise SpendingError("resource_limit")
        if isinstance(item, BaseModel):
            item = {**vars(item), **(item.__pydantic_extra__ or {})}
        if type(item) is dict:
            if any(type(k) is not str for k in item):
                raise SpendingError("invalid_input")
            return {visit(k, depth + 1): visit(v, depth + 1) for k, v in item.items()}
        if type(item) in (list, tuple):
            return [visit(v, depth + 1) for v in item]
        if item is None or type(item) in (str, bool):
            return item
        if type(item) is int and len(str(item)) <= 19:
            return item
        raise SpendingError("invalid_input")

    return visit(value, 0)


def _encode(value: Any, limit: int) -> bytes:
    try:
        encoder = json.JSONEncoder(
            sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
        output = bytearray()
        for chunk in encoder.iterencode(_plain(value)):
            encoded = chunk.encode("utf-8")
            if len(output) + len(encoded) > limit:
                raise SpendingError("resource_limit")
            output.extend(encoded)
        return bytes(output)
    except SpendingError:
        raise
    except Exception:  # noqa: BLE001 - fixed privacy-safe public boundary
        raise SpendingError("invalid_input") from None


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SpendingError("invalid_input")
        result[key] = value
    return result


def _reject(value: str) -> Any:
    raise SpendingError("invalid_input")


def _integer(value: str) -> int:
    if len(value) > 19:
        raise SpendingError("resource_limit")
    return int(value)


def _decode(raw: bytes, limit: int) -> Any:
    if type(raw) is not bytes or not raw:
        raise SpendingError("invalid_input")
    if len(raw) > limit:
        raise SpendingError("resource_limit")
    try:
        depth, quoted, escaped = 0, False, False
        for byte in raw:
            if quoted:
                if escaped:
                    escaped = False
                elif byte == 92:
                    escaped = True
                elif byte == 34:
                    quoted = False
            elif byte == 34:
                quoted = True
            elif byte in (91, 123):
                depth += 1
                if depth > MAX_DEPTH:
                    raise SpendingError("resource_limit")
            elif byte in (93, 125):
                depth -= 1
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique,
            parse_float=_reject,
            parse_constant=_reject,
            parse_int=_integer,
        )
        if _encode(value, limit) != raw:
            raise SpendingError("noncanonical_input")
        return value
    except SpendingError:
        raise
    except Exception:  # noqa: BLE001 - fixed privacy-safe public boundary
        raise SpendingError("invalid_input") from None


def _issue_occurrences(value: Any) -> int:
    if isinstance(value, dict):
        return sum(
            (
                len(v)
                if k in {"issues", "assumptions", "unresolved_uncertainties"}
                and isinstance(v, list)
                else _issue_occurrences(v)
            )
            for k, v in value.items()
        )
    return sum(_issue_occurrences(v) for v in value) if isinstance(value, list) else 0


def _checked[T: Frozen](model: type[T], value: object, limit: int) -> T:
    try:
        if (
            model is OfflineSpendingAssessment
            and _issue_occurrences(_plain(value)) > MAX_ISSUES
        ):
            raise SpendingError("resource_limit")
        raw = _encode(value, limit)
        checked = model.model_validate_json(raw)
        if _encode(checked, limit) != raw:
            raise SpendingError("invalid_input")
        return checked
    except SpendingError:
        raise
    except Exception:  # noqa: BLE001 - fixed privacy-safe public boundary
        raise SpendingError("invalid_input") from None


def _parse[T: Frozen](model: type[T], raw: bytes, limit: int) -> T:
    return _checked(model, _decode(raw, limit), limit)


def parse_assignment(raw: bytes) -> SpendingEvidenceAssignment:
    return _parse(SpendingEvidenceAssignment, raw, MAX_ASSIGNMENT_BYTES)


def serialize_assignment(value: SpendingEvidenceAssignment) -> bytes:
    return _encode(
        _checked(SpendingEvidenceAssignment, value, MAX_ASSIGNMENT_BYTES),
        MAX_ASSIGNMENT_BYTES,
    )


def parse_policy(raw: bytes) -> OfflineSpendingDiagnosticPolicy:
    return _parse(OfflineSpendingDiagnosticPolicy, raw, MAX_POLICY_BYTES)


def serialize_policy(value: OfflineSpendingDiagnosticPolicy) -> bytes:
    return _encode(
        _checked(OfflineSpendingDiagnosticPolicy, value, MAX_POLICY_BYTES),
        MAX_POLICY_BYTES,
    )


def parse_bundle(raw: bytes) -> SpendingObservationBundle:
    return _parse(SpendingObservationBundle, raw, MAX_BUNDLE_BYTES)


def serialize_bundle(value: SpendingObservationBundle) -> bytes:
    return _encode(
        _checked(SpendingObservationBundle, value, MAX_BUNDLE_BYTES), MAX_BUNDLE_BYTES
    )


def parse_expected_reference(raw: bytes) -> ExpectedSpendingEvidenceReference:
    return _parse(ExpectedSpendingEvidenceReference, raw, MAX_REFERENCE_BYTES)


def serialize_expected_reference(value: ExpectedSpendingEvidenceReference) -> bytes:
    return _encode(
        _checked(ExpectedSpendingEvidenceReference, value, MAX_REFERENCE_BYTES),
        MAX_REFERENCE_BYTES,
    )


def _commit(domain: str, value: Frozen) -> str:
    return fingerprint(
        {
            "domain": domain,
            "canonicalization": CANONICAL_VERSION,
            "value": value.model_dump(mode="json"),
        }
    )


def assignment_commitment(value: SpendingEvidenceAssignment) -> str:
    return _commit(
        "canary-spending-assignment-v1", parse_assignment(serialize_assignment(value))
    )


def policy_commitment(value: OfflineSpendingDiagnosticPolicy) -> str:
    return _commit(
        "canary-offline-spending-diagnostic-policy-v1",
        parse_policy(serialize_policy(value)),
    )


def bundle_commitment(value: SpendingObservationBundle) -> str:
    return _commit(
        "canary-spending-observation-bundle-v1", parse_bundle(serialize_bundle(value))
    )


ISSUES = frozenset(
    {
        "invalid_input",
        "noncanonical_input",
        "resource_limit",
        "arithmetic_error",
        "not_assessed",
        "reference_mismatch",
        "binding_mismatch",
        "profile_mismatch",
        "provenance_not_permitted",
        "authentication_unsupported",
        "verified_bounds_unsupported",
        "propagation_unsupported",
        "billing_unsupported",
        "organization_headroom_unsupported",
        "cost_comparison_deferred",
        "provider_completeness_unestablished",
        "known_incomplete_reporting",
        "outside_validity",
        "period_or_horizon_expired",
        "observation_absent",
        "observation_unknown",
        "observation_unavailable",
        "conflicting_observation",
        "scope_mismatch",
        "exposure_mismatch",
        "future_or_reversed_timestamp",
        "stamp_missing",
        "observation_stale",
        "collection_span_exceeded",
        "provider_timestamp_unsupported",
        "threshold_missing",
        "zero_threshold_unsupported",
        "threshold_exceeds_maximum",
        "hard_limit_required",
        "enforcement_inactive",
        "enforcement_unknown",
        "interval_unsupported",
        "alerts_not_required",
        "required_alert_missing",
        "duplicate_alert",
        "pagination_incomplete",
        "window_mismatch",
        "cost_window_unavailable",
        "window_lag_exceeded",
        "restricted_reporting",
        "missing_cost_buckets",
        "invalid_cost_buckets",
        "unknown_cost_amount",
        "cost_total_out_of_range",
        "usage_not_required",
        "usage_counter_missing",
        "usage_counter_inconsistent",
        "usage_family_unsupported",
        "usage_coverage_incomplete",
        "bound_missing",
        "support_missing",
        "amount_claim_not_bound",
        "policy_reserve_only",
        "bound_stale",
        "bound_future",
        "contradictory_bound",
        "unknown_attempt_count",
        "positive_unknown_attempts",
        "full_exposure_bound_required",
        "positive_gap_bound_required",
        "zero_allowance_for_unknown",
        "liability_kind_mismatch",
        "underlying_liability_unestablished",
        "unverified_bound_claim",
        "policy_reserve_assumption",
        "known_amount_floor",
        "stale_amount_retained",
        "incomplete_bound_claim",
        "headroom_unavailable",
        "hypothetical_only",
        "headroom_nonpositive",
        "headroom_insufficient",
        "reporting_gap_assumption",
        "unreported_exposure_unestablished",
    }
)
Issue = Annotated[str, Field(max_length=64)]


class DiagnosticFinding(Frozen):
    status: Status
    requirement: Requirement
    issues: tuple[Issue, ...] = Field(max_length=MAX_ISSUES)

    @model_validator(mode="after")
    def _codes(self) -> DiagnosticFinding:
        if (
            (self.status == "PASS") != (not self.issues)
            or any(i not in ISSUES for i in self.issues)
            or len(set(self.issues)) != len(self.issues)
        ):
            raise ValueError("invalid_finding")
        return self


def _finding(
    status: Status = "PASS", *issues: str, required: bool = True
) -> DiagnosticFinding:
    return DiagnosticFinding(
        status=status,
        requirement="REQUIRED" if required else "INFORMATIONAL",
        issues=tuple(dict.fromkeys(issues)),
    )


def _aggregate(
    values: tuple[DiagnosticFinding, ...], *, required: bool = True
) -> DiagnosticFinding:
    if not values:
        return _finding("SKIP", "not_assessed", required=required)
    for status in ("ERROR", "FAIL", "SKIP"):
        if any(v.status == status for v in values):
            return _finding(
                status,
                *(i for v in values if v.status == status for i in v.issues),
                required=required,
            )
    return _finding(required=required)


class Assurance(Frozen):
    provider_evidence_authenticated: Literal[False] = False
    billing_verified: Literal[False] = False
    execution_admission_established: Literal[False] = False
    authorises_live_execution: Literal[False] = False
    fresh_source_verification_performed: Literal[False] = False
    source_authorised: Literal[False] = False
    observer_identity_authenticated: Literal[False] = False
    liability_upper_bounds_independently_verified: Literal[False] = False
    provider_reporting_completeness_established: Literal[False] = False
    enforcement_propagation_verified: Literal[False] = False
    maximum_invoice_established: Literal[False] = False
    assessment_origin_authenticated: Literal[False] = False
    real_external_readiness: Literal["UNESTABLISHED"] = "UNESTABLISHED"
    assurance_class: Literal["offline-conditional-diagnostic-only"] = (
        "offline-conditional-diagnostic-only"
    )


class RequirementBasis(Frozen):
    require_usage: bool
    require_alerts: bool
    reporting_requirement: Literal[
        "bounded_gap_assumptions", "complete_reporting_required"
    ]
    require_authenticated_acquisition: bool
    require_verified_liability_bounds: bool
    require_verified_propagation: bool
    require_final_billing: bool
    require_organization_headroom: bool
    require_cost_comparison: bool


class ObservedLiabilityEvidence(Frozen):
    observation: LiabilityObservation
    declared_provenance: Provenance
    freshness: DiagnosticFinding
    qualification: DiagnosticFinding


class PolicyLiabilityEvidence(Frozen):
    rule: LiabilityRule
    scope: SpendingScope
    freshness: DiagnosticFinding
    qualification: DiagnosticFinding


def _selected_bound(
    observed: ObservedLiabilityEvidence | None, policy: PolicyLiabilityEvidence
) -> tuple[
    Literal["observation", "policy"] | None,
    str | None,
    str | None,
    str | None,
    AttemptCoverage,
]:
    """Keep claim attribution atomic; ties prefer the observed claim.

    Unqualified claims remain visible when no qualified candidate exists. Their
    qualification never follows from taking max(reserve, observed amount).
    """
    candidates: list[
        tuple[
            Literal["observation", "policy"],
            str,
            str | None,
            str | None,
            AttemptCoverage,
            bool,
        ]
    ] = []
    payload = observed.observation.payload if observed else None
    if (
        observed is not None
        and payload is not None
        and payload.basis == "upper_bound_claim"
        and payload.amount is not None
    ):
        candidates.append(
            (
                "observation",
                _text(_major(payload.amount)),
                observed.observation.header.supporting_artifact_sha256,
                None,
                payload.attempt_coverage,
                observed.qualification.status == "PASS",
            )
        )
    rule = policy.rule
    if rule.source == "independent_bound_claim":
        assert rule.allowance_usd is not None
        candidates.append(
            (
                "policy",
                rule.allowance_usd,
                rule.supporting_reference_sha256,
                rule.bound_claim_as_of,
                rule.attempt_coverage,
                policy.qualification.status == "PASS",
            )
        )
    qualified = [c for c in candidates if c[-1]]
    if not candidates:
        return None, None, None, None, "not_applicable"
    return max(qualified or candidates, key=lambda c: Decimal(c[1]))[:5]


def _resolved_liability_amount(
    observed: ObservedLiabilityEvidence | None,
    policy: PolicyLiabilityEvidence,
    checks: tuple[DiagnosticFinding, ...],
) -> Decimal | None:
    """Resolve retained operands, including hypothetical and unavailable states."""
    payload = observed.observation.payload if observed else None
    known = (
        _major(payload.amount)
        if payload is not None and payload.amount is not None
        else None
    )
    rule = policy.rule
    allowance = Decimal(rule.allowance_usd) if rule.allowance_usd is not None else None
    qualified = (
        observed is not None
        and payload is not None
        and payload.basis == "upper_bound_claim"
        and observed.qualification.status == "PASS"
    ) or (
        rule.source == "independent_bound_claim"
        and policy.qualification.status == "PASS"
    )
    if rule.source == "declared_upper_bound":
        amount = (
            known
            if observed is not None and observed.qualification.status == "PASS"
            else None
        )
    else:
        assert allowance is not None
        amount = max(allowance, known) if known is not None else allowance
    count = payload.unknown_attempts if payload is not None else None
    if rule.kind == "inflight_unknown" and amount == 0 and count != 0:
        amount = None
    if rule.kind == "incurred_unreported" and (amount is None or amount <= 0):
        amount = None
    if (
        rule.source == "policy_reserve"
        and allowance == 0
        and known in {None, Decimal(0)}
        and not qualified
    ) or any(c.status == "ERROR" for c in checks):
        amount = None
    return amount


class EffectiveDeduction(Frozen):
    kind: Kind
    known_supplied_amount_usd: Money | None
    effective_amount_usd: Money | None
    bound_claim_usd: Money | None
    basis: Literal["declared_upper_bound", "policy_reserve", "independent_bound_claim"]
    supporting_reference_sha256: Digest | None
    bound_claim_as_of: Timestamp | None
    attempt_coverage: AttemptCoverage
    unknown_attempts: Counter | None
    observed_evidence: ObservedLiabilityEvidence | None
    policy_evidence: PolicyLiabilityEvidence
    selected_bound_source: Literal["observation", "policy"] | None
    calculation_eligibility: DiagnosticFinding
    diagnostic_evidence_sufficiency: DiagnosticFinding
    observation_freshness: DiagnosticFinding
    assumptions: tuple[Issue, ...]
    unresolved_uncertainties: tuple[Issue, ...]
    underlying_liability_established: Literal[False] = False
    independently_verified: Literal[False] = False

    @model_validator(mode="after")
    def _consistent(self) -> EffectiveDeduction:
        rule = self.policy_evidence.rule
        observed = self.observed_evidence
        payload = observed.observation.payload if observed else None
        if rule.kind != self.kind or rule.source != self.basis:
            raise ValueError("invalid_policy_attribution")
        common = _liability_observation_checks(
            observed.observation if observed else None,
            rule,
            self.policy_evidence.scope,
            self.observation_freshness,
        )
        if observed is not None and observed.freshness != self.observation_freshness:
            raise ValueError("invalid_observation_freshness")
        if observed is None and self.observation_freshness != _finding(
            "SKIP", "observation_absent"
        ):
            raise ValueError("invalid_absent_freshness")
        if self.known_supplied_amount_usd != (
            _text(_major(payload.amount))
            if payload is not None and payload.amount is not None
            else None
        ) or self.unknown_attempts != (payload.unknown_attempts if payload else None):
            raise ValueError("invalid_observation_attribution")
        if observed is not None:
            expected_qualification = (
                _qualify_bound(
                    _major(payload.amount) if payload.amount is not None else None,
                    observed.observation.header.supporting_artifact_sha256,
                    observed.freshness,
                    self.kind,
                    payload.attempt_coverage,
                    self.unknown_attempts,
                    tuple(common),
                )
                if payload is not None and payload.basis == "upper_bound_claim"
                else _aggregate(
                    (
                        *common,
                        _finding(
                            "SKIP",
                            "amount_claim_not_bound" if payload else "bound_missing",
                        ),
                    ),
                    required=False,
                )
            )
            if observed.qualification != expected_qualification:
                raise ValueError("invalid_observed_qualification")
        if rule.source == "independent_bound_claim":
            contradictions: tuple[DiagnosticFinding, ...] = ()
            if (
                payload is not None
                and payload.basis == "amount_claim"
                and payload.amount is not None
                and rule.allowance_usd is not None
                and Decimal(rule.allowance_usd) < _major(payload.amount)
            ):
                contradictions = (_finding("ERROR", "contradictory_bound"),)
            expected_policy = _qualify_bound(
                Decimal(rule.allowance_usd) if rule.allowance_usd is not None else None,
                rule.supporting_reference_sha256,
                self.policy_evidence.freshness,
                self.kind,
                rule.attempt_coverage,
                self.unknown_attempts,
                contradictions,
            )
            if self.policy_evidence.freshness.requirement != "REQUIRED":
                raise ValueError("invalid_policy_freshness_requirement")
        else:
            expected_policy = _finding(
                "SKIP",
                "policy_reserve_only"
                if rule.source == "policy_reserve"
                else "not_assessed",
                required=False,
            )
            if self.policy_evidence.freshness != expected_policy:
                raise ValueError("invalid_policy_freshness")
        if self.policy_evidence.qualification != expected_policy:
            raise ValueError("invalid_policy_qualification")
        checks = list(common)
        bound_qualifications = []
        if (
            observed is not None
            and payload is not None
            and payload.basis == "upper_bound_claim"
        ):
            bound_qualifications.append(observed.qualification)
        if rule.source == "independent_bound_claim":
            bound_qualifications.append(self.policy_evidence.qualification)
        checks.extend(bound_qualifications)
        if not any(q.status == "PASS" for q in bound_qualifications):
            checks.append(
                _finding(
                    "SKIP",
                    "policy_reserve_only"
                    if rule.source == "policy_reserve"
                    else "amount_claim_not_bound"
                    if payload is not None and payload.basis == "amount_claim"
                    else "bound_missing",
                )
            )
            if (
                rule.source == "policy_reserve"
                and rule.allowance_usd == "0"
                and self.known_supplied_amount_usd in {None, "0"}
            ):
                checks.append(_finding("SKIP", "zero_allowance_for_unknown"))
        amount = _resolved_liability_amount(
            observed, self.policy_evidence, tuple(checks)
        )
        if self.effective_amount_usd != (_text(amount) if amount is not None else None):
            raise ValueError("invalid_resolved_deduction")
        expected_sufficiency = _aggregate(tuple(checks)) if checks else _finding()
        if self.effective_amount_usd is None and expected_sufficiency.status == "PASS":
            expected_sufficiency = _finding("SKIP", "bound_missing")
        if self.diagnostic_evidence_sufficiency != expected_sufficiency:
            raise ValueError("invalid_deduction_sufficiency")
        if (
            self.selected_bound_source,
            self.bound_claim_usd,
            self.supporting_reference_sha256,
            self.bound_claim_as_of,
            self.attempt_coverage,
        ) != _selected_bound(observed, self.policy_evidence):
            raise ValueError("invalid_bound_attribution")
        if (
            self.calculation_eligibility.requirement != "INFORMATIONAL"
            or self.diagnostic_evidence_sufficiency.requirement != "REQUIRED"
            or self.observation_freshness.requirement != "REQUIRED"
        ):
            raise ValueError("invalid_deduction_requirements")
        if (self.calculation_eligibility.status == "PASS") != (
            self.effective_amount_usd is not None
        ):
            raise ValueError("invalid_deduction_amount")
        if (
            self.diagnostic_evidence_sufficiency.status == "PASS"
            and self.calculation_eligibility.status != "PASS"
        ):
            raise ValueError("invalid_deduction_sufficiency")
        if (
            self.effective_amount_usd is not None
            and self.known_supplied_amount_usd is not None
            and Decimal(self.effective_amount_usd)
            < Decimal(self.known_supplied_amount_usd)
        ):
            raise ValueError("liability_reduced")
        if (
            self.effective_amount_usd is not None
            and self.bound_claim_usd is not None
            and Decimal(self.effective_amount_usd) < Decimal(self.bound_claim_usd)
        ):
            raise ValueError("bound_reduced")
        if (
            self.selected_bound_source != "policy"
            and self.bound_claim_as_of is not None
        ):
            raise ValueError("invalid_bound_timestamp")
        if (
            "underlying_liability_unestablished" not in self.unresolved_uncertainties
            or any(
                i not in ISSUES
                for i in (*self.assumptions, *self.unresolved_uncertainties)
            )
        ):
            raise ValueError("invalid_deduction_assurance")
        if (
            self.kind == "inflight_unknown"
            and self.diagnostic_evidence_sufficiency.status == "PASS"
            and (
                self.attempt_coverage != "all_inflight_exposure"
                or (
                    self.unknown_attempts != 0
                    and (
                        self.bound_claim_usd is None
                        or Decimal(self.bound_claim_usd) <= 0
                    )
                )
            )
        ):
            raise ValueError("invalid_full_exposure_bound")
        if self.diagnostic_evidence_sufficiency.status == "PASS" and (
            self.bound_claim_usd is None
            or self.supporting_reference_sha256 is None
            or (
                self.selected_bound_source == "policy"
                and self.bound_claim_as_of is None
            )
            or (
                self.kind == "incurred_unreported"
                and Decimal(self.bound_claim_usd) <= 0
            )
        ):
            raise ValueError("invalid_qualified_bound")
        return self


class CalculationInputs(Frozen):
    effective_threshold_usd: Money
    reported_cost_usd: Money
    deductions_usd: tuple[Money, ...] = Field(min_length=4, max_length=4)
    safety_margin_usd: Money
    minimum_required_residual_usd: Money


def _headroom(inputs: CalculationInputs) -> str:
    try:
        with localcontext(_context()):
            value = Decimal(inputs.effective_threshold_usd) - Decimal(
                inputs.reported_cost_usd
            )
            for deduction in inputs.deductions_usd:
                value -= Decimal(deduction)
            value -= Decimal(inputs.safety_margin_usd)
            return _money(_text(value), signed=True)
    except (ValueError, DecimalException):
        raise SpendingError("arithmetic_error") from None


class CostComparison(Frozen):
    state: Literal["DEFERRED"] = "DEFERRED"
    reason: Literal["historical_cost_comparison_not_supported"] = (
        "historical_cost_comparison_not_supported"
    )
    difference_usd: None = None
    billing_reconciliation_performed: Literal[False] = False


FINDINGS = (
    "structural_validity",
    "expected_reference_agreement",
    "assignment_policy_binding",
    "profile_conformity",
    "provenance_conformity",
    "input_reliability",
    "validity",
    "authentication_assurance",
    "control_freshness",
    "cost_freshness",
    "usage_freshness",
    "liability_freshness",
    "threshold_conformity",
    "enforcement_conformity",
    "alert_conformity",
    "reporting_window_coverage",
    "pagination_coverage",
    "provider_reporting_completeness",
    "usage_assessment",
    "liability_basis_assessment",
    "diagnostic_evidence_sufficiency",
    "conditional_headroom",
    "verified_bounds_assurance",
    "propagation_assurance",
    "billing_assurance",
    "organization_headroom_requirement",
    "cost_comparison_requirement",
)


def _requirements(basis: RequirementBasis) -> dict[str, bool]:
    result = dict.fromkeys(FINDINGS, True)
    result.update(
        {
            "usage_freshness": basis.require_usage,
            "usage_assessment": basis.require_usage,
            "alert_conformity": basis.require_alerts,
            "provider_reporting_completeness": basis.reporting_requirement
            == "complete_reporting_required",
            "authentication_assurance": basis.require_authenticated_acquisition,
            "verified_bounds_assurance": basis.require_verified_liability_bounds,
            "propagation_assurance": basis.require_verified_propagation,
            "billing_assurance": basis.require_final_billing,
            "organization_headroom_requirement": basis.require_organization_headroom,
            "cost_comparison_requirement": basis.require_cost_comparison,
        }
    )
    return result


def _outcome(findings: dict[str, DiagnosticFinding]) -> Outcome:
    status = _aggregate(
        tuple(v for v in findings.values() if v.requirement == "REQUIRED")
    ).status
    return {
        "ERROR": "INVALID_EVIDENCE",
        "FAIL": "NONCONFORMANT",
        "SKIP": "INDETERMINATE",
        "PASS": "CONDITIONALLY_CONFORMANT",
    }[status]  # type: ignore[return-value]


def _headroom_eligible(
    findings: dict[str, DiagnosticFinding], basis: RequirementBasis
) -> bool:
    # Financial evidence prerequisites, distinct from independent conformity
    # requirements such as final billing, authentication and alert availability.
    names = [
        "structural_validity",
        "expected_reference_agreement",
        "assignment_policy_binding",
        "profile_conformity",
        "provenance_conformity",
        "input_reliability",
        "validity",
        "control_freshness",
        "cost_freshness",
        "liability_freshness",
        "threshold_conformity",
        "enforcement_conformity",
        "reporting_window_coverage",
        "pagination_coverage",
        "liability_basis_assessment",
        "diagnostic_evidence_sufficiency",
    ]
    if basis.require_usage:
        names.extend(("usage_freshness", "usage_assessment"))
    if basis.reporting_requirement == "complete_reporting_required":
        names.append("provider_reporting_completeness")
    return all(findings[name].status == "PASS" for name in names)


class OfflineSpendingAssessment(Frozen):
    """A consistent representation, never proof that an assessor executed."""

    schema_id: Literal["canary-offline-spending-assessment-v1"] = (
        "canary-offline-spending-assessment-v1"
    )
    assessed_at: Timestamp
    assignment_commitment_sha256: Digest | None
    policy_commitment_sha256: Digest | None
    bundle_commitment_sha256: Digest | None
    declared_provenance: Provenance | None
    requirement_basis: RequirementBasis
    structural_validity: DiagnosticFinding
    expected_reference_agreement: DiagnosticFinding
    assignment_policy_binding: DiagnosticFinding
    profile_conformity: DiagnosticFinding
    provenance_conformity: DiagnosticFinding
    input_reliability: DiagnosticFinding
    validity: DiagnosticFinding
    authentication_assurance: DiagnosticFinding
    control_freshness: DiagnosticFinding
    cost_freshness: DiagnosticFinding
    usage_freshness: DiagnosticFinding
    liability_freshness: DiagnosticFinding
    threshold_conformity: DiagnosticFinding
    enforcement_conformity: DiagnosticFinding
    alert_conformity: DiagnosticFinding
    reporting_window_coverage: DiagnosticFinding
    pagination_coverage: DiagnosticFinding
    provider_reporting_completeness: DiagnosticFinding
    usage_assessment: DiagnosticFinding
    liability_basis_assessment: DiagnosticFinding
    diagnostic_evidence_sufficiency: DiagnosticFinding
    conditional_headroom: DiagnosticFinding
    verified_bounds_assurance: DiagnosticFinding
    propagation_assurance: DiagnosticFinding
    billing_assurance: DiagnosticFinding
    organization_headroom_requirement: DiagnosticFinding
    cost_comparison_requirement: DiagnosticFinding
    known_cost_subtotal_usd: Money | None
    supplied_report_total_usd: Money | None
    effective_deductions: tuple[EffectiveDeduction, ...] = Field(max_length=4)
    calculation_inputs: CalculationInputs | None
    hypothetical_headroom_usd: SignedMoney | None
    headroom_usd: SignedMoney | None
    headroom_state: Literal["UNAVAILABLE", "HYPOTHETICAL", "DECISION_ELIGIBLE"]
    cost_comparison: CostComparison
    diagnostic_outcome: Outcome
    issues: tuple[Issue, ...] = Field(max_length=MAX_ISSUES)
    assurance: Assurance

    @model_validator(mode="after")
    def _consistent(self) -> OfflineSpendingAssessment:
        findings = {name: getattr(self, name) for name in FINDINGS}
        policy_present = self.policy_commitment_sha256 is not None
        assignment_present = self.assignment_commitment_sha256 is not None
        bundle_present = self.bundle_commitment_sha256 is not None
        provenance_present = self.declared_provenance is not None
        identities_present = (
            policy_present
            and assignment_present
            and bundle_present
            and provenance_present
        )
        if (
            (assignment_present and not policy_present)
            or (bundle_present and not assignment_present)
            or bundle_present != provenance_present
        ):
            raise ValueError("invalid_identity_availability")
        if (
            self.structural_validity.status not in {"PASS", "ERROR"}
            or (self.structural_validity.status == "PASS") != identities_present
        ):
            raise ValueError("invalid_structural_identities")
        if any(
            findings[name].status == "PASS"
            for name in ("assignment_policy_binding", "expected_reference_agreement")
        ) and (not identities_present or self.structural_validity.status != "PASS"):
            raise ValueError("invalid_binding_identities")
        for name, required in _requirements(self.requirement_basis).items():
            if findings[name].requirement != (
                "REQUIRED" if required else "INFORMATIONAL"
            ):
                raise ValueError("invalid_requirement_mapping")
        unsupported = {
            "authentication_assurance": "authentication_unsupported",
            "verified_bounds_assurance": "verified_bounds_unsupported",
            "propagation_assurance": "propagation_unsupported",
            "billing_assurance": "billing_unsupported",
            "organization_headroom_requirement": "organization_headroom_unsupported",
            "cost_comparison_requirement": "cost_comparison_deferred",
        }
        for name, code in unsupported.items():
            if findings[name].status != "SKIP" or findings[name].issues != (code,):
                raise ValueError("unsupported_assurance_promotion")
        if (
            self.provider_reporting_completeness.status != "SKIP"
            or self.provider_reporting_completeness.issues
            != ("provider_completeness_unestablished",)
        ):
            raise ValueError("completeness_promotion")
        if (
            any(
                v.status == "ERROR"
                for k, v in findings.items()
                if k != "input_reliability"
            )
            and self.input_reliability.status != "ERROR"
        ):
            raise ValueError("unreliable_optional_evidence")
        expected_issues = tuple(
            dict.fromkeys(i for v in findings.values() for i in v.issues)
        )
        if (
            self.diagnostic_outcome != _outcome(findings)
            or self.issues != expected_issues
        ):
            raise ValueError("invalid_aggregate")
        if (
            self.supplied_report_total_usd is not None
            and self.known_cost_subtotal_usd != self.supplied_report_total_usd
        ):
            raise ValueError("invalid_report_total")
        if self.effective_deductions and self.liability_basis_assessment != _aggregate(
            tuple(d.diagnostic_evidence_sufficiency for d in self.effective_deductions)
        ):
            raise ValueError("invalid_liability_aggregate")
        if (
            self.effective_deductions
            and tuple(d.kind for d in self.effective_deductions) != KINDS
        ):
            raise ValueError("invalid_deduction_order")
        for deduction in self.effective_deductions:
            observed = deduction.observed_evidence
            if (
                observed is not None
                and observed.declared_provenance != self.declared_provenance
            ):
                raise ValueError("invalid_deduction_provenance")
            if (
                observed is not None
                and observed.observation.header.availability != "conflicting"
                and _observation_time_error(
                    observed.observation.header, _time(self.assessed_at)
                )
                and observed.freshness
                != _finding("ERROR", "future_or_reversed_timestamp")
            ):
                raise ValueError("invalid_observation_timestamp_freshness")
            policy = deduction.policy_evidence
            if (
                policy.rule.source == "independent_bound_claim"
                and policy.freshness.status == "PASS"
                and policy.rule.bound_claim_as_of is not None
                and _time(policy.rule.bound_claim_as_of) > _time(self.assessed_at)
            ):
                raise ValueError("invalid_future_bound_freshness")
        if self.calculation_inputs is None:
            if (
                self.headroom_state != "UNAVAILABLE"
                or self.headroom_usd is not None
                or self.hypothetical_headroom_usd is not None
                or self.conditional_headroom.status in {"PASS", "FAIL"}
                or _headroom_eligible(findings, self.requirement_basis)
            ):
                raise ValueError("invalid_unavailable_headroom")
        else:
            inputs = self.calculation_inputs
            expected = _headroom(inputs)
            if (
                inputs.reported_cost_usd != self.supplied_report_total_usd
                or tuple(d.effective_amount_usd for d in self.effective_deductions)
                != inputs.deductions_usd
            ):
                raise ValueError("invalid_calculation_inputs")
            if self.hypothetical_headroom_usd != expected:
                raise ValueError("invalid_arithmetic")
            if self.headroom_state == "HYPOTHETICAL":
                if (
                    self.headroom_usd is not None
                    or self.conditional_headroom.status != "SKIP"
                    or _headroom_eligible(findings, self.requirement_basis)
                ):
                    raise ValueError("hypothetical_decision")
            elif self.headroom_state == "DECISION_ELIGIBLE":
                if self.headroom_usd != expected or not _headroom_eligible(
                    findings, self.requirement_basis
                ):
                    raise ValueError("ineligible_headroom")
                headroom = Decimal(expected)
                check = (
                    _finding("FAIL", "headroom_nonpositive")
                    if headroom <= 0
                    else _finding("FAIL", "headroom_insufficient")
                    if headroom < Decimal(inputs.minimum_required_residual_usd)
                    else _finding()
                )
                if self.conditional_headroom != check:
                    raise ValueError("invalid_headroom_outcome")
            else:
                raise ValueError("invalid_headroom_state")
        raw = _plain(self)

        if _issue_occurrences(raw) > MAX_ISSUES:
            raise SpendingError("resource_limit")
        return self


def parse_assessment(raw: bytes) -> OfflineSpendingAssessment:
    """Validate representation and consistency only; does not authenticate origin."""
    return _parse(OfflineSpendingAssessment, raw, MAX_ASSESSMENT_BYTES)


def serialize_assessment(value: OfflineSpendingAssessment) -> bytes:
    """Revalidate even constructed/copied representations; no provenance guarantee."""
    return _encode(
        _checked(OfflineSpendingAssessment, value, MAX_ASSESSMENT_BYTES),
        MAX_ASSESSMENT_BYTES,
    )


def _clock(now: datetime) -> str:
    try:
        if (
            type(now) is not datetime
            or now.utcoffset() != timedelta(0)
            or now.microsecond
            or not 2000 <= now.year <= 2099
        ):
            raise ValueError
        return _timestamp(now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    except Exception:  # noqa: BLE001 - even a hostile tzinfo cannot escape the clock boundary
        raise SpendingError("invalid_clock") from None


def _observation_time_error(header: ObservationHeader, now: datetime) -> bool:
    stamp = header.stamp
    if stamp is None:
        return False
    start, end = _time(stamp.collection_started_at), _time(stamp.collection_ended_at)
    return (
        start > end
        or end > now
        or (
            stamp.provider_timestamp is not None
            and _time(stamp.provider_timestamp) > end
        )
    )


def _fresh(
    header: ObservationHeader | None, now: datetime, age: int, span: int
) -> DiagnosticFinding:
    if header is None:
        return _finding("SKIP", "observation_absent")
    if header.availability == "conflicting":
        return _finding("ERROR", "conflicting_observation")
    if _observation_time_error(header, now):
        return _finding("ERROR", "future_or_reversed_timestamp")
    if header.availability != "present":
        return _finding("SKIP", "observation_" + header.availability)
    if header.stamp is None:
        return _finding("SKIP", "stamp_missing")
    stamp = header.stamp
    start, end = _time(stamp.collection_started_at), _time(stamp.collection_ended_at)
    if now - start > timedelta(seconds=age):
        return _finding("SKIP", "observation_stale")
    if end - start > timedelta(seconds=span):
        return _finding("SKIP", "collection_span_exceeded")
    return _finding()


def _scope(value: ObservedScope, expected: SpendingScope) -> DiagnosticFinding:
    p = expected.project
    if (value.level, value.provider_id, value.organization_id, value.project_id) != (
        "project",
        p.provider_id,
        p.organization_id,
        p.project_id,
    ):
        return _finding("ERROR", "scope_mismatch")
    return _finding()


def _window(
    value: Window,
    header: ObservationHeader,
    expected: SpendingScope,
    now: datetime,
    lag: int,
) -> DiagnosticFinding:
    end = _time(value.end)
    if (
        value.start != expected.billing_period.start
        or end > _time(expected.billing_period.end)
        or end > now
        or (header.stamp is not None and end > _time(header.stamp.collection_ended_at))
    ):
        return _finding("ERROR", "window_mismatch")
    if now - end > timedelta(seconds=lag):
        return _finding("SKIP", "window_lag_exceeded")
    return _finding()


def _qualify_bound(
    amount: Decimal | None,
    support: str | None,
    freshness: DiagnosticFinding,
    kind: Kind,
    coverage: AttemptCoverage,
    count: int | None,
    checks: tuple[DiagnosticFinding, ...] = (),
) -> DiagnosticFinding:
    findings = list(checks)
    if freshness.status != "PASS":
        findings.append(freshness)
    if amount is None:
        findings.append(_finding("SKIP", "bound_missing"))
    if support is None:
        findings.append(_finding("SKIP", "support_missing"))
    if kind == "incurred_unreported" and (amount is None or amount <= 0):
        findings.append(_finding("SKIP", "positive_gap_bound_required"))
    if kind == "inflight_unknown" and (
        coverage != "all_inflight_exposure"
        or (count != 0 and (amount is None or amount <= 0))
    ):
        findings.append(_finding("SKIP", "full_exposure_bound_required"))
    return _aggregate(tuple(findings)) if findings else _finding()


def _liability_observation_checks(
    observation: LiabilityObservation | None,
    rule: LiabilityRule,
    scope: SpendingScope,
    fresh: DiagnosticFinding,
) -> tuple[DiagnosticFinding, ...]:
    payload = observation.payload if observation else None
    checks = []
    if payload is not None:
        checks.append(_scope(payload.scope, scope))
        if payload.kind != rule.kind:
            checks.append(_finding("ERROR", "liability_kind_mismatch"))
        if (payload.exposure_window.start, payload.exposure_window.end) != (
            scope.billing_period.start,
            scope.horizon_end,
        ):
            checks.append(_finding("ERROR", "exposure_mismatch"))
        if fresh.status != "PASS":
            checks.append(fresh)
    elif fresh.status == "ERROR":
        checks.append(fresh)
    return tuple(checks)


def _liability(
    observation: LiabilityObservation | None,
    rule: LiabilityRule,
    scope: SpendingScope,
    policy: OfflineSpendingDiagnosticPolicy,
    now: datetime,
    provenance: Provenance,
) -> EffectiveDeduction:
    header = observation.header if observation else None
    payload = observation.payload if observation else None
    fresh = _fresh(
        header,
        now,
        policy.max_liability_age_seconds,
        policy.max_collection_span_seconds,
    )
    known = (
        _major(payload.amount)
        if payload is not None and payload.amount is not None
        else None
    )
    count = payload.unknown_attempts if payload is not None else None
    common = list(_liability_observation_checks(observation, rule, scope, fresh))
    assumptions: list[str] = []
    uncertainties = ["underlying_liability_unestablished"]
    if payload is not None and fresh.status != "PASS" and known is not None:
        assumptions.append("stale_amount_retained")

    observed_evidence = None
    observed_bound = payload is not None and payload.basis == "upper_bound_claim"
    if observation is not None:
        if observed_bound:
            assert header is not None and payload is not None
            observed_qualification = _qualify_bound(
                known,
                header.supporting_artifact_sha256,
                fresh,
                rule.kind,
                payload.attempt_coverage,
                count,
                tuple(common),
            )
            if header.supporting_artifact_sha256 is None:
                uncertainties.append("incomplete_bound_claim")
        else:
            observed_qualification = _aggregate(
                (
                    *common,
                    _finding(
                        "SKIP",
                        "amount_claim_not_bound" if payload else "bound_missing",
                    ),
                ),
                required=False,
            )
        observed_evidence = ObservedLiabilityEvidence(
            observation=observation,
            declared_provenance=provenance,
            freshness=fresh,
            qualification=observed_qualification,
        )

    allowance = Decimal(rule.allowance_usd) if rule.allowance_usd is not None else None
    if rule.source == "independent_bound_claim":
        assert rule.bound_claim_as_of is not None
        as_of = _time(rule.bound_claim_as_of)
        policy_freshness = (
            _finding("ERROR", "bound_future")
            if as_of > now
            else _finding("SKIP", "bound_stale")
            if now - as_of > timedelta(seconds=policy.max_liability_age_seconds)
            else _finding()
        )
        contradictions: tuple[DiagnosticFinding, ...] = ()
        if (
            known is not None
            and payload is not None
            and payload.basis == "amount_claim"
            and allowance is not None
            and allowance < known
        ):
            contradictions = (_finding("ERROR", "contradictory_bound"),)
        policy_qualification = _qualify_bound(
            allowance,
            rule.supporting_reference_sha256,
            policy_freshness,
            rule.kind,
            rule.attempt_coverage,
            count,
            contradictions,
        )
    else:
        policy_freshness = policy_qualification = _finding(
            "SKIP",
            "policy_reserve_only"
            if rule.source == "policy_reserve"
            else "not_assessed",
            required=False,
        )
    policy_evidence = PolicyLiabilityEvidence(
        rule=rule,
        scope=scope,
        freshness=policy_freshness,
        qualification=policy_qualification,
    )
    selected_source, bound, support, as_of_text, coverage = _selected_bound(
        observed_evidence, policy_evidence
    )
    qualified = (
        observed_evidence is not None
        and observed_bound
        and observed_evidence.qualification.status == "PASS"
    ) or (
        rule.source == "independent_bound_claim"
        and policy_qualification.status == "PASS"
    )
    checks = list(common)
    if observed_evidence is not None and observed_bound:
        checks.append(observed_evidence.qualification)
    if rule.source == "independent_bound_claim":
        checks.append(policy_qualification)
    if qualified:
        assumptions.append("unverified_bound_claim")
    else:
        checks.append(
            _finding(
                "SKIP",
                "policy_reserve_only"
                if rule.source == "policy_reserve"
                else "amount_claim_not_bound"
                if payload is not None and payload.basis == "amount_claim"
                else "bound_missing",
            )
        )

    if rule.source != "declared_upper_bound":
        if known is not None:
            assumptions.append("known_amount_floor")
        if rule.source == "policy_reserve":
            assumptions.append("policy_reserve_assumption")
    if rule.kind == "inflight_unknown":
        if count is None:
            uncertainties.append("unknown_attempt_count")
        elif count > 0:
            uncertainties.append("positive_unknown_attempts")
    if rule.kind == "incurred_unreported":
        uncertainties.append("unreported_exposure_unestablished")
        assumptions.append("reporting_gap_assumption")
    if (
        allowance == 0
        and known in {None, Decimal(0)}
        and not qualified
        and rule.source == "policy_reserve"
    ):
        checks.append(_finding("SKIP", "zero_allowance_for_unknown"))
    amount = _resolved_liability_amount(
        observed_evidence, policy_evidence, tuple(checks)
    )
    sufficiency = _aggregate(tuple(checks)) if checks else _finding()
    if amount is None and sufficiency.status == "PASS":
        sufficiency = _finding("SKIP", "bound_missing")
    return EffectiveDeduction(
        kind=rule.kind,
        known_supplied_amount_usd=_text(known) if known is not None else None,
        effective_amount_usd=_text(amount) if amount is not None else None,
        bound_claim_usd=bound,
        basis=rule.source,
        supporting_reference_sha256=support,
        bound_claim_as_of=as_of_text,
        attempt_coverage=coverage,
        unknown_attempts=count,
        observed_evidence=observed_evidence,
        policy_evidence=policy_evidence,
        selected_bound_source=selected_source,
        calculation_eligibility=_finding(required=False)
        if amount is not None
        else _finding("SKIP", "bound_missing", required=False),
        diagnostic_evidence_sufficiency=sufficiency,
        observation_freshness=fresh,
        assumptions=tuple(dict.fromkeys(assumptions)),
        unresolved_uncertainties=tuple(uncertainties),
    )


def _cost_report(
    value: CostValues,
    header: ObservationHeader,
    policy: OfflineSpendingDiagnosticPolicy,
    now: datetime,
) -> tuple[DiagnosticFinding, DiagnosticFinding, str | None, str | None]:
    checks = [
        _scope(value.scope, policy.scope),
        _window(
            value.window, header, policy.scope, now, policy.max_cost_window_lag_seconds
        ),
    ]
    pages = (
        _finding()
        if value.pagination == "complete"
        else _finding("SKIP", "pagination_incomplete")
    )
    if value.traffic_scope != "all_project_traffic":
        checks.append(_finding("SKIP", "restricted_reporting"))
    if value.reporting_completeness == "known_incomplete":
        checks.append(_finding("SKIP", "known_incomplete_reporting"))
    cursor = value.window.start
    continuous = bool(value.buckets)
    known = bool(value.buckets)
    subtotal = Decimal(0)
    with localcontext(_context()):
        for bucket in value.buckets:
            if (
                _time(bucket.start) < _time(cursor)
                or _time(bucket.start) < _time(value.window.start)
                or _time(bucket.end) > _time(value.window.end)
            ):
                checks.append(_finding("ERROR", "invalid_cost_buckets"))
            if bucket.start != cursor:
                continuous = False
            cursor = bucket.end
            if bucket.amount is None:
                known = False
            else:
                subtotal += _major(bucket.amount)
    continuous &= cursor == value.window.end
    if not continuous:
        checks.append(_finding("SKIP", "missing_cost_buckets"))
    if not known:
        checks.append(_finding("SKIP", "unknown_cost_amount"))
    try:
        subtotal_text = _money(_text(subtotal))
    except ValueError:
        return _finding("ERROR", "cost_total_out_of_range"), pages, None, None
    check = _aggregate(tuple(checks))
    total = (
        subtotal_text
        if continuous
        and known
        and pages.status == "PASS"
        and check.status != "ERROR"
        and value.traffic_scope == "all_project_traffic"
        else None
    )
    return check, pages, subtotal_text, total


def _usage_report(
    value: UsageValues,
    header: ObservationHeader,
    costs: CostValues | None,
    policy: OfflineSpendingDiagnosticPolicy,
    now: datetime,
) -> DiagnosticFinding:
    checks = [
        _scope(value.scope, policy.scope),
        _window(
            value.window, header, policy.scope, now, policy.max_usage_window_lag_seconds
        ),
    ]
    if costs is None:
        checks.append(_finding("SKIP", "cost_window_unavailable"))
    elif value.window != costs.window:
        checks.append(_finding("ERROR", "window_mismatch"))
    if value.traffic_scope != "project_completions_family":
        checks.append(_finding("SKIP", "usage_family_unsupported"))
    if value.window_coverage != "continuous":
        checks.append(_finding("SKIP", "usage_coverage_incomplete"))
    if value.pagination != "complete":
        checks.append(_finding("SKIP", "pagination_incomplete"))
    if value.reporting_completeness == "known_incomplete":
        checks.append(_finding("SKIP", "known_incomplete_reporting"))
    if any(
        v is None
        for v in (
            value.request_count,
            value.input_tokens,
            value.output_tokens,
            value.total_tokens,
        )
    ):
        checks.append(_finding("SKIP", "usage_counter_missing"))
    if (
        value.input_tokens is not None
        and value.output_tokens is not None
        and value.total_tokens is not None
        and value.total_tokens != value.input_tokens + value.output_tokens
    ):
        checks.append(_finding("ERROR", "usage_counter_inconsistent"))
    return _aggregate(tuple(checks))


def _basis(policy: OfflineSpendingDiagnosticPolicy | None) -> RequirementBasis:
    flags = {
        name: getattr(policy, name) if policy is not None else False
        for name in (
            "require_usage",
            "require_authenticated_acquisition",
            "require_verified_liability_bounds",
            "require_verified_propagation",
            "require_final_billing",
            "require_organization_headroom",
            "require_cost_comparison",
        )
    }
    return RequirementBasis(
        **flags,
        require_alerts=bool(policy and policy.required_alerts_usd),
        reporting_requirement=policy.reporting_requirement
        if policy
        else "bounded_gap_assumptions",
    )


def _initial(basis: RequirementBasis) -> dict[str, DiagnosticFinding]:
    findings = {
        name: _finding("SKIP", "not_assessed", required=required)
        for name, required in _requirements(basis).items()
    }
    for name, code in (
        ("authentication_assurance", "authentication_unsupported"),
        ("verified_bounds_assurance", "verified_bounds_unsupported"),
        ("propagation_assurance", "propagation_unsupported"),
        ("billing_assurance", "billing_unsupported"),
        ("organization_headroom_requirement", "organization_headroom_unsupported"),
        ("cost_comparison_requirement", "cost_comparison_deferred"),
        ("provider_reporting_completeness", "provider_completeness_unestablished"),
    ):
        findings[name] = _finding("SKIP", code, required=_requirements(basis)[name])
    return findings


def assess_spending(
    raw: bytes,
    *,
    assignment: SpendingEvidenceAssignment,
    policy: OfflineSpendingDiagnosticPolicy,
    expected: ExpectedSpendingEvidenceReference,
    now: datetime,
) -> OfflineSpendingAssessment:
    """Pure conditional diagnostics. Invalid clock raises before any construction.

    All other input failures return qualified INVALID_EVIDENCE, never an invented
    timestamp or authority. Supporting digests are inert and never dereferenced.
    """
    assessed_at = _clock(now)
    basis = _basis(None)
    findings = _initial(basis)
    a_digest = p_digest = b_digest = None
    provenance: Provenance | None = None
    deductions: tuple[EffectiveDeduction, ...] = ()
    subtotal = total = None
    inputs = None
    hypothetical = decision_headroom = None
    state: Literal["UNAVAILABLE", "HYPOTHETICAL", "DECISION_ELIGIBLE"] = "UNAVAILABLE"

    def put(name: str, value: DiagnosticFinding) -> None:
        findings[name] = value.model_copy(
            update={
                "requirement": "REQUIRED"
                if _requirements(basis)[name]
                else "INFORMATIONAL"
            }
        )

    try:
        p = _checked(OfflineSpendingDiagnosticPolicy, policy, MAX_POLICY_BYTES)
        basis = _basis(p)
        findings = _initial(basis)
        p_digest = policy_commitment(p)
        a = _checked(SpendingEvidenceAssignment, assignment, MAX_ASSIGNMENT_BYTES)
        a_digest = assignment_commitment(a)
        reference = _checked(
            ExpectedSpendingEvidenceReference, expected, MAX_REFERENCE_BYTES
        )
        bundle = parse_bundle(raw)
        b_digest = bundle_commitment(bundle)
        provenance = bundle.declared_provenance
        put("structural_validity", _finding())
        binding = (
            a.policy_commitment_sha256 == p_digest == bundle.policy_commitment_sha256
            and a_digest == bundle.assignment_commitment_sha256
            and a.scope == p.scope
            and a.observation_profile == bundle.observation_profile
        )
        put(
            "assignment_policy_binding",
            _finding() if binding else _finding("ERROR", "binding_mismatch"),
        )
        agreement = (
            reference.assignment_id == a.assignment_id
            and reference.assignment_commitment_sha256 == a_digest
            and reference.policy_commitment_sha256 == p_digest
            and reference.observation_profile == a.observation_profile
            and reference.bundle_commitment_sha256 == b_digest
        )
        put(
            "expected_reference_agreement",
            _finding() if agreement else _finding("ERROR", "reference_mismatch"),
        )
        if not binding or not agreement:
            raise SpendingError("invalid_input")
        put("input_reliability", _finding())
        put(
            "profile_conformity",
            _finding()
            if PROFILES[bundle.observation_profile] == bundle.declared_provenance
            else _finding("ERROR", "profile_mismatch"),
        )
        put(
            "provenance_conformity",
            _finding()
            if bundle.declared_provenance in p.accepted_provenances
            else _finding("FAIL", "provenance_not_permitted"),
        )
        validity = []
        if not (
            _time(a.opens_at) <= now < _time(a.closes_at)
            and _time(p.valid_from) <= now < _time(p.valid_until)
        ):
            validity.append(_finding("SKIP", "outside_validity"))
        if (
            not _time(a.scope.billing_period.start)
            <= now
            < _time(a.scope.horizon_end)
            <= _time(a.scope.billing_period.end)
        ):
            validity.append(_finding("SKIP", "period_or_horizon_expired"))
        put("validity", _aggregate(tuple(validity)) if validity else _finding())
        observations = (
            bundle.control,
            bundle.costs,
            bundle.alerts,
            bundle.usage,
            *bundle.liabilities,
        )
        if bundle.observation_profile.startswith("openai-admin-"):
            if any(
                o is not None
                and o.header.stamp is not None
                and o.header.stamp.provider_timestamp is not None
                for o in observations
            ):
                put(
                    "profile_conformity",
                    _finding("ERROR", "provider_timestamp_unsupported"),
                )
            control = bundle.control.payload
            alerts = bundle.alerts.payload if bundle.alerts is not None else None
            if (
                control is not None
                and control.threshold is not None
                and control.threshold.unit != "integer_cents"
            ) or (
                alerts is not None
                and any(t.unit != "integer_cents" for t in alerts.thresholds)
            ):
                put("profile_conformity", _finding("ERROR", "profile_mismatch"))
        control_fresh = _fresh(
            bundle.control.header,
            now,
            p.max_control_age_seconds,
            p.max_collection_span_seconds,
        )
        put("control_freshness", control_fresh)
        control = bundle.control.payload
        threshold = None
        if control is None:
            put("threshold_conformity", control_fresh)
            put("enforcement_conformity", control_fresh)
        else:
            scope_check = _scope(control.scope, a.scope)
            if scope_check.status != "PASS":
                put("input_reliability", scope_check)
            if control.threshold is None:
                put("threshold_conformity", _finding("SKIP", "threshold_missing"))
            else:
                threshold = _major(control.threshold)
                put(
                    "threshold_conformity",
                    _finding("SKIP", "zero_threshold_unsupported")
                    if threshold == 0
                    else _finding("FAIL", "threshold_exceeds_maximum")
                    if threshold > Decimal(p.max_project_threshold_usd)
                    else _finding(),
                )
            enforcement = []
            if control.kind == "soft_alert":
                enforcement.append(_finding("FAIL", "hard_limit_required"))
            elif control.kind != "hard_limit":
                enforcement.append(_finding("SKIP", "hard_limit_required"))
            if control.interval != "month":
                enforcement.append(_finding("SKIP", "interval_unsupported"))
            if control.enforcement != "enforcing":
                enforcement.append(
                    _finding("FAIL", "enforcement_inactive")
                    if control.enforcement == "inactive"
                    else _finding("SKIP", "enforcement_unknown")
                )
            put(
                "enforcement_conformity",
                _aggregate(tuple(enforcement)) if enforcement else _finding(),
            )
        if bundle.alerts is None:
            put(
                "alert_conformity",
                _finding(
                    "SKIP",
                    "observation_absent"
                    if p.required_alerts_usd
                    else "alerts_not_required",
                ),
            )
        else:
            alerts = bundle.alerts.payload
            checks = [
                _fresh(
                    bundle.alerts.header,
                    now,
                    p.max_control_age_seconds,
                    p.max_collection_span_seconds,
                )
            ]
            if alerts is not None:
                checks.append(_scope(alerts.scope, a.scope))
                amounts = tuple(_major(v) for v in alerts.thresholds)
                if len(set(amounts)) != len(amounts):
                    checks.append(_finding("ERROR", "duplicate_alert"))
                if alerts.pagination != "complete":
                    checks.append(_finding("SKIP", "pagination_incomplete"))
                elif any(Decimal(v) not in amounts for v in p.required_alerts_usd):
                    checks.append(_finding("FAIL", "required_alert_missing"))
            put("alert_conformity", _aggregate(tuple(checks)))
        cost_fresh = _fresh(
            bundle.costs.header,
            now,
            p.max_cost_age_seconds,
            p.max_collection_span_seconds,
        )
        put("cost_freshness", cost_fresh)
        costs = bundle.costs.payload
        if costs is not None:
            coverage, pages, subtotal, total = _cost_report(
                costs, bundle.costs.header, p, now
            )
            put("reporting_window_coverage", coverage)
            put("pagination_coverage", pages)
        else:
            put("reporting_window_coverage", cost_fresh)
            put("pagination_coverage", cost_fresh)
        if bundle.usage is None:
            put(
                "usage_freshness",
                _finding(
                    "SKIP",
                    "observation_absent" if p.require_usage else "usage_not_required",
                ),
            )
            put("usage_assessment", findings["usage_freshness"])
        else:
            usage = bundle.usage.payload
            fresh = _fresh(
                bundle.usage.header,
                now,
                p.max_usage_age_seconds,
                p.max_collection_span_seconds,
            )
            put("usage_freshness", fresh)
            put(
                "usage_assessment",
                _usage_report(usage, bundle.usage.header, costs, p, now)
                if usage is not None
                else fresh,
            )
        deductions = tuple(
            _liability(o, rule, a.scope, p, now, bundle.declared_provenance)
            for o, rule in zip(bundle.liabilities, p.liability_rules, strict=True)
        )
        put(
            "liability_basis_assessment",
            _aggregate(tuple(d.diagnostic_evidence_sufficiency for d in deductions)),
        )
        fresh_checks = []
        for observation, rule, deduction in zip(
            bundle.liabilities, p.liability_rules, deductions, strict=True
        ):
            fresh = deduction.observation_freshness
            if (
                observation is None
                or observation.header.availability in {"unknown", "unavailable"}
            ) and rule.source == "independent_bound_claim":
                assert rule.bound_claim_as_of is not None
                as_of = _time(rule.bound_claim_as_of)
                fresh = (
                    _finding("ERROR", "bound_future")
                    if as_of > now
                    else _finding("SKIP", "bound_stale")
                    if now - as_of > timedelta(seconds=p.max_liability_age_seconds)
                    else _finding()
                )
            fresh_checks.append(fresh)
        put("liability_freshness", _aggregate(tuple(fresh_checks)))
        # Reliability applies to all supplied evidence, including informational items.
        errors = tuple(v for v in findings.values() if v.status == "ERROR")
        if errors:
            put("input_reliability", _aggregate(errors))
        evidence_names = (
            "structural_validity",
            "expected_reference_agreement",
            "assignment_policy_binding",
            "profile_conformity",
            "input_reliability",
            "validity",
            "control_freshness",
            "cost_freshness",
            "liability_freshness",
            "reporting_window_coverage",
            "pagination_coverage",
            "liability_basis_assessment",
        )
        evidence = [findings[n] for n in evidence_names]
        if p.require_usage:
            evidence.extend((findings["usage_freshness"], findings["usage_assessment"]))
        if p.reporting_requirement == "complete_reporting_required":
            evidence.append(findings["provider_reporting_completeness"])
        put("diagnostic_evidence_sufficiency", _aggregate(tuple(evidence)))
        numeric = (
            threshold is not None
            and threshold > 0
            and control is not None
            and control.kind == "hard_limit"
            and control.enforcement == "enforcing"
            and control.interval == "month"
            and total is not None
            and costs is not None
            and costs.reporting_completeness != "known_incomplete"
            and findings["reporting_window_coverage"].status == "PASS"
            and findings["pagination_coverage"].status == "PASS"
            and findings["input_reliability"].status == "PASS"
            and all(d.effective_amount_usd is not None for d in deductions)
        )
        if numeric:
            assert threshold is not None and total is not None
            inputs = CalculationInputs(
                effective_threshold_usd=_money(_text(threshold)),
                reported_cost_usd=total,
                deductions_usd=tuple(
                    d.effective_amount_usd
                    for d in deductions
                    if d.effective_amount_usd is not None
                ),
                safety_margin_usd=p.safety_margin_usd,
                minimum_required_residual_usd=p.minimum_residual_headroom_usd,
            )
            hypothetical = _headroom(inputs)
            eligible = _headroom_eligible(findings, basis)
            if eligible:
                state, decision_headroom = "DECISION_ELIGIBLE", hypothetical
                h = Decimal(hypothetical)
                put(
                    "conditional_headroom",
                    _finding("FAIL", "headroom_nonpositive")
                    if h <= 0
                    else _finding("FAIL", "headroom_insufficient")
                    if h < Decimal(p.minimum_residual_headroom_usd)
                    else _finding(),
                )
            else:
                state = "HYPOTHETICAL"
                put("conditional_headroom", _finding("SKIP", "hypothetical_only"))
        else:
            put("conditional_headroom", _finding("SKIP", "headroom_unavailable"))
    except (
        SpendingError,
        DecimalException,
        ValueError,
        TypeError,
        AttributeError,
    ) as error:
        # No unbound payload is assessed. A malformed root has no trusted siblings.
        code = (
            error.code
            if isinstance(error, SpendingError)
            else "arithmetic_error"
            if isinstance(error, DecimalException)
            else "invalid_input"
        )
        if findings["structural_validity"].status != "PASS":
            put("structural_validity", _finding("ERROR", code))
        put("input_reliability", _finding("ERROR", code))
        inputs = None
        hypothetical = decision_headroom = None
        state = "UNAVAILABLE"
    errors = tuple(v for v in findings.values() if v.status == "ERROR")
    if errors:
        put("input_reliability", _aggregate(errors))
    result = OfflineSpendingAssessment(
        schema_id="canary-offline-spending-assessment-v1",
        assessed_at=assessed_at,
        assignment_commitment_sha256=a_digest,
        policy_commitment_sha256=p_digest,
        bundle_commitment_sha256=b_digest,
        declared_provenance=provenance,
        requirement_basis=basis,
        **findings,
        known_cost_subtotal_usd=subtotal,
        supplied_report_total_usd=total,
        effective_deductions=deductions,
        calculation_inputs=inputs,
        hypothetical_headroom_usd=hypothetical,
        headroom_usd=decision_headroom,
        headroom_state=state,
        cost_comparison=CostComparison(),
        diagnostic_outcome=_outcome(findings),
        issues=tuple(dict.fromkeys(i for v in findings.values() for i in v.issues)),
        assurance=Assurance(),
    )
    return _checked(OfflineSpendingAssessment, result, MAX_ASSESSMENT_BYTES)
