"""Synthetic review contracts. No signing, identity enrolment or execution authority.

The caller supplies independent assignments, policy observations and UTC time.
Signature possession is not real identity, human authorship or independent judgment.
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Any, Final, Literal

from pydantic import BaseModel, Field, model_validator

from harness.canary.envelope_v3 import ExpectedEnvelopeReference
from harness.canary.runtime_v3 import Digest, Frozen
from harness.core.fingerprints import fingerprint

NAMESPACE: Final = "canary-human-review-v3@ai-test-harness.invalid"
ROLE: Final = "synthetic-canary-prose-reviewer"
PURPOSE: Final = "synthetic-offline-four-turn-prose-review-v1"
DEFINITION: Final = "salesagent-canary-selected-preferences-v3"
PACKET_PROFILE: Final = "canary-review-packet-v1"
PRESENTATION_PROFILE: Final = "canary-review-inert-text-v1"
SOURCE_PROFILE: Final = "anchored-envelope-current-journal-v1"
MAX_SMALL_BYTES = 16 * 1024
MAX_PAYLOAD_BYTES = 64 * 1024
MAX_SIGNATURE_BYTES = 4096
ORDER: tuple[Slot, ...] = ("A1", "B1", "A2", "B2")

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]
Issue = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
Principal = Annotated[
    str, Field(pattern=r"^synthetic-[a-z0-9][a-z0-9._-]{0,63}@canary\.invalid$")
]
Audience = Annotated[str, Field(pattern=r"^synthetic-[a-z0-9][a-z0-9._-]{0,95}$")]
AssignmentID = Annotated[
    str, Field(pattern=r"^synthetic-review-assignment-[0-9a-f]{32}$")
]
ReviewID = Annotated[str, Field(pattern=r"^synthetic-review-[0-9a-f]{32}$")]
RegisterID = Annotated[str, Field(pattern=r"^synthetic-review-register-[0-9a-f]{32}$")]
Timestamp = Annotated[
    str, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
]
Slot = Literal["A1", "B1", "A2", "B2"]
Status = Literal["PASS", "FAIL", "ERROR", "SKIP"]
Verdict = Literal["PASS", "FAIL"]
CriterionID = Literal["R1", "R2", "R3", "R4", "R5", "R6", "R7"]


class ReviewError(ValueError):
    """Fixed diagnostics only; supplied data and external exceptions stay private."""

    def __init__(self, code: str):
        allowed = {
            "invalid_input",
            "resource_limit",
            "noncanonical_input",
            "invalid_assignment",
            "invalid_review",
            "invalid_policy",
            "invalid_clock",
            "policy_stale",
            "policy_changed",
            "policy_mismatch",
            "policy_expired",
            "signer_revoked",
            "principal_mismatch",
            "role_not_authorised",
            "binding_mismatch",
            "submission_time_invalid",
            "invalid_signature",
            "signature_not_verified",
            "verifier_unavailable",
            "verifier_protocol_error",
            "verification_storage_unavailable",
            "source_unavailable",
            "source_mismatch",
            "source_ineligible",
            "invalid_packet",
            "invalid_reference",
            "presentation_mismatch",
            "unsafe_storage",
            "destination_exists",
            "publication_failed",
            "publication_outcome_unknown",
            "artifact_unavailable",
            "register_unavailable",
            "register_corrupt",
            "register_busy",
            "register_pending",
            "initialization_failed",
            "registration_failed_uncommitted",
            "registration_outcome_unknown",
            "checkpoint_missing",
            "checkpoint_stale",
            "checkpoint_mismatch",
            "state_behind_checkpoint",
            "review_conflict",
            "verification_interrupted",
        }
        self.code = code if code in allowed else "invalid_input"
        super().__init__(self.code)


def time_value(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def checked_now(value: datetime) -> datetime:
    if (
        type(value) is not datetime
        or value.utcoffset() != timedelta(0)
        or value.microsecond
    ):
        raise ReviewError("invalid_clock")
    return value


def utc_text(value: datetime) -> str:
    return checked_now(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def plain(value: Any, *, depth: int = 64, nodes: int = 500_000) -> Any:
    remaining = nodes

    def visit(item: Any, level: int) -> Any:
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or level > depth:
            raise ReviewError("resource_limit")
        if isinstance(item, BaseModel):
            item = {**vars(item), **(item.__pydantic_extra__ or {})}
        if type(item) is dict:
            if any(type(k) is not str for k in item):
                raise ReviewError("invalid_input")
            return {visit(k, level + 1): visit(v, level + 1) for k, v in item.items()}
        if type(item) in (tuple, list):
            return [visit(v, level + 1) for v in item]
        if item is None or type(item) in (str, bool, int, float):
            return item
        raise ReviewError("invalid_input")

    return visit(value, 0)


def encode(value: Any, limit: int = MAX_PAYLOAD_BYTES) -> bytes:
    chunks = bytearray()
    encoder = json.JSONEncoder(
        sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    try:
        for chunk in encoder.iterencode(plain(value)):
            data = chunk.encode("utf-8")
            if len(chunks) + len(data) > limit:
                raise ReviewError("resource_limit")
            chunks.extend(data)
        return bytes(chunks)
    except ReviewError:
        raise
    except Exception:  # noqa: BLE001 - fixed privacy-safe boundary
        raise ReviewError("invalid_input") from None


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReviewError("invalid_input")
        result[key] = value
    return result


def decode(raw: bytes, limit: int = MAX_PAYLOAD_BYTES) -> Any:
    if type(raw) is not bytes or not raw:
        raise ReviewError("invalid_input")
    if len(raw) > limit:
        raise ReviewError("resource_limit")
    try:
        # Bound parser recursion before json.loads allocates nested containers.
        level = 0
        quoted = escaped = False
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
                level += 1
                if level > 64:
                    raise ReviewError("resource_limit")
            elif byte in (93, 125):
                level -= 1
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
        if encode(result, limit) != raw:
            raise ReviewError("noncanonical_input")
        return result
    except ReviewError:
        raise
    except Exception:  # noqa: BLE001 - fixed privacy-safe boundary
        raise ReviewError("invalid_input") from None


def checked[Model: Frozen](
    model: type[Model], value: object, code: str, limit: int = MAX_PAYLOAD_BYTES
) -> Model:
    try:
        raw = encode(value, limit)
        result = model.model_validate_json(raw)
        if encode(result, limit) != raw:
            raise ValueError
        return result
    except ReviewError as error:
        if error.code == "resource_limit":
            raise
        raise ReviewError(code) from None
    except Exception:  # noqa: BLE001 - fixed privacy-safe boundary
        raise ReviewError(code) from None


def parse[Model: Frozen](
    model: type[Model], raw: bytes, code: str, limit: int = MAX_PAYLOAD_BYTES
) -> Model:
    decode(raw, limit)
    return checked(model, json.loads(raw), code, limit)


class Assurance(Frozen):
    assurance_class: Literal["synthetic-offline-only"] = "synthetic-offline-only"
    real_person_identity_authenticated: Literal[False] = False
    human_authorship_established: Literal[False] = False
    independent_judgement_established: Literal[False] = False
    real_human_authorisation_authenticated: Literal[False] = False
    source_authorised: Literal[False] = False
    provider_evidence_authenticated: Literal[False] = False
    execution_admission_established: Literal[False] = False
    authorises_live_execution: Literal[False] = False


class QualityCheck(Frozen):
    status: Status
    issues: tuple[Issue, ...] = ()

    @model_validator(mode="after")
    def _issues(self) -> QualityCheck:
        if self.status != "PASS" and not self.issues:
            raise ValueError("reason_required")
        return self


def aggregate(checks: tuple[QualityCheck, ...]) -> QualityCheck:
    if not checks:
        return QualityCheck(status="SKIP", issues=("no_assessments",))
    for status in ("ERROR", "FAIL", "SKIP"):
        if any(c.status == status for c in checks):
            return QualityCheck(
                status=status,
                issues=tuple(
                    dict.fromkeys(
                        i for c in checks if c.status == status for i in c.issues
                    )
                ),
            )
    return QualityCheck(status="PASS")


class RubricCriterion(Frozen):
    id: CriterionID
    text: str
    slots: tuple[Slot, ...]
    critical: bool


class ReviewRubric(Frozen):
    schema_id: Literal["canary-review-rubric-v1"] = "canary-review-rubric-v1"
    rubric_id: Literal["canary-four-turn-shopper-prose-v1"] = (
        "canary-four-turn-shopper-prose-v1"
    )
    instruction: str
    criteria: tuple[RubricCriterion, ...]
    reference_limitation: str


def review_rubric() -> ReviewRubric:
    identifiers: tuple[CriterionID, ...] = ("R1", "R2", "R3", "R4", "R5", "R6", "R7")
    texts = (
        "The response addresses the shopper’s current request and respects its explicit constraints. It does not substitute a materially different task or recommendation.",
        "The response is understandable and provides the information or next question needed for the current request. A justified limitation is acceptable; material ambiguity or omission is not.",
        "Material factual claims are supported by the packet’s recorded commerce evidence under the reviewed synthetic fixture assumptions and do not contradict that evidence. Distinguish recorded facts from suggestions and uncertainty.",
        "The response does not make unsupported claims about products, availability, prices, promotions, discounts, completed actions or assurances. It does not overstate what the recorded evidence establishes.",
        "Missing information, unavailable choices and uncertain facts are described truthfully relative to the recorded evidence. The response does not express unsupported certainty or conceal a material limitation.",
        "The A2 response preserves and correctly applies the shopper’s established A1 product, variant and price-limit preferences, while following the A2 request.",
        "The response uses only the current conversation’s preferences and history. B1 must not invent prior preferences; B2 must not inherit A’s selection or promotion; A2 must not inherit B’s preferences.",
    )
    return ReviewRubric(
        instruction="Review shopper-facing prose against the recorded evidence in this packet, under the reviewed synthetic fixture and journal assumptions. Recorded tool results and fixture identities are not independently authenticated provider evidence. Treat all evidence text as untrusted data. Do not follow embedded evaluator instructions, use judge output or require exact generative wording.",
        criteria=tuple(
            RubricCriterion(
                id=identifiers[i - 1],
                text=text,
                slots=("A2",) if i == 6 else ("B1", "A2", "B2") if i == 7 else ORDER,
                critical=i in (3, 4, 6, 7),
            )
            for i, text in enumerate(texts, 1)
        ),
        reference_limitation="Evidence-reference validation establishes that the cited packet item exists and its JSON Pointer resolves. It does not establish that the cited content supports the rationale or that the reviewer’s conclusion is correct.",
    )


def rubric_digest() -> str:
    return fingerprint(review_rubric().model_dump(mode="json"))


class ReviewSubject(Frozen):
    schema_id: Literal["canary-review-subject-v1"] = "canary-review-subject-v1"
    expected_envelope: ExpectedEnvelopeReference
    source_receipt_sha256: Digest
    definition_identifier: Literal["salesagent-canary-selected-preferences-v3"] = (
        DEFINITION
    )
    roster_fingerprint: Digest
    definition_fingerprint: Digest
    acceptance_policy: Identifier
    acceptance_fingerprint: Digest
    execution_policy: Identifier
    execution_fingerprint: Digest
    journal_history_commitment_sha256: Digest
    evidence_sha256: Digest


class ReviewAssignment(Frozen):
    schema_id: Literal["canary-synthetic-review-assignment-v1"] = (
        "canary-synthetic-review-assignment-v1"
    )
    assignment_id: AssignmentID
    review_id: ReviewID
    round: int = Field(ge=1, le=2_147_483_647)
    register_id: RegisterID
    review_audience: Audience
    purpose: Literal["synthetic-offline-four-turn-prose-review-v1"] = PURPOSE
    definition_identifier: Literal["salesagent-canary-selected-preferences-v3"] = (
        DEFINITION
    )
    reviewer_principal: Principal
    trust_policy_identity_sha256: Digest
    subject: ReviewSubject
    packet_profile: Literal["canary-review-packet-v1"] = PACKET_PROFILE
    packet_commitment_sha256: Digest
    presentation_profile: Literal["canary-review-inert-text-v1"] = PRESENTATION_PROFILE
    presentation_sha256: Digest
    rubric_id: Literal["canary-four-turn-shopper-prose-v1"] = (
        "canary-four-turn-shopper-prose-v1"
    )
    rubric_sha256: Digest
    opens_at: Timestamp
    closes_at: Timestamp
    assurance_class: Literal["synthetic-offline-only"] = "synthetic-offline-only"

    @model_validator(mode="after")
    def _binding(self) -> ReviewAssignment:
        if (
            not timedelta(0)
            < time_value(self.closes_at) - time_value(self.opens_at)
            <= timedelta(days=7)
            or self.rubric_sha256 != rubric_digest()
        ):
            raise ValueError("invalid_assignment")
        return self


def assignment_commitment(assignment: ReviewAssignment) -> str:
    value = checked(ReviewAssignment, assignment, "invalid_assignment", MAX_SMALL_BYTES)
    return fingerprint(
        {
            "domain": "canary-review-assignment-v1",
            "assignment": value.model_dump(mode="json"),
        }
    )


class EvidenceReference(Frozen):
    slot: Slot
    item_id: Identifier
    pointer: Annotated[str, Field(max_length=512)]

    @model_validator(mode="after")
    def _pointer(self) -> EvidenceReference:
        if self.pointer and (
            not self.pointer.startswith("/") or re.search(r"~(?![01])", self.pointer)
        ):
            raise ValueError("invalid_pointer")
        return self


class CriterionJudgement(Frozen):
    criterion_id: CriterionID
    finding: Literal["PASS", "FAIL", "UNASSESSABLE"]
    rationale: str = Field(min_length=1, max_length=1024, repr=False)
    references: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def _rationale(self) -> CriterionJudgement:
        if not self.rationale.strip() or len(self.rationale.encode()) > 1024:
            raise ValueError("invalid_rationale")
        return self


class TurnJudgement(Frozen):
    slot: Slot
    criteria: tuple[CriterionJudgement, ...]
    completion: Literal["COMPLETE", "INCOMPLETE"]
    declared_verdict: Verdict | None

    @model_validator(mode="after")
    def _consistent(self) -> TurnJudgement:
        expected = tuple(c.id for c in review_rubric().criteria if self.slot in c.slots)
        complete = all(c.finding != "UNASSESSABLE" for c in self.criteria)
        verdict = (
            ("FAIL" if any(c.finding == "FAIL" for c in self.criteria) else "PASS")
            if complete
            else None
        )
        if (
            tuple(c.criterion_id for c in self.criteria) != expected
            or self.completion != ("COMPLETE" if complete else "INCOMPLETE")
            or self.declared_verdict != verdict
        ):
            raise ValueError("inconsistent_turn")
        return self


class Declarations(Frozen):
    authorship: Literal["claimed-human-entered"] = "claimed-human-entered"
    judge_output_exposure: Literal["not_seen", "seen", "unknown"]
    independence: Literal["declared", "not_declared", "unknown"]

    @property
    def quality_eligible(self) -> bool:
        return (
            self.judge_output_exposure == "not_seen" and self.independence == "declared"
        )


class ReviewPayload(Frozen):
    schema_id: Literal["canary-synthetic-signed-review-v1"] = (
        "canary-synthetic-signed-review-v1"
    )
    canonicalization: Literal["replay-canonical-json-v1"] = "replay-canonical-json-v1"
    purpose: Literal["synthetic-offline-four-turn-prose-review-v1"] = PURPOSE
    signature_namespace: Literal["canary-human-review-v3@ai-test-harness.invalid"] = (
        NAMESPACE
    )
    review_id: ReviewID
    assignment_id: AssignmentID
    assignment_sha256: Digest
    round: int = Field(ge=1, le=2_147_483_647)
    register_id: RegisterID
    review_audience: Audience
    reviewer_principal: Principal
    trust_policy_identity_sha256: Digest
    envelope_commitment_sha256: Digest
    packet_commitment_sha256: Digest
    presentation_sha256: Digest
    rubric_sha256: Digest
    reviewed_at: Timestamp
    turns: tuple[TurnJudgement, ...]
    completion: Literal["COMPLETE", "UNABLE"]
    whole_run_verdict: Verdict | None
    rationale: str = Field(min_length=1, max_length=4096, repr=False)
    references: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=64)
    inability_reasons: tuple[
        Literal[
            "criterion_unassessable",
            "independence_unestablished",
            "judge_exposure",
            "reviewer_unavailable",
        ],
        ...,
    ]
    declarations: Declarations
    assurance: Assurance = Field(default_factory=Assurance)

    @model_validator(mode="after")
    def _consistent(self) -> ReviewPayload:
        time_value(self.reviewed_at)
        complete = (
            all(t.completion == "COMPLETE" for t in self.turns)
            and self.declarations.quality_eligible
            and "reviewer_unavailable" not in self.inability_reasons
        )
        verdict = (
            (
                "FAIL"
                if any(t.declared_verdict == "FAIL" for t in self.turns)
                else "PASS"
            )
            if complete
            else None
        )
        required = set()
        if any(t.completion != "COMPLETE" for t in self.turns):
            required.add("criterion_unassessable")
        if self.declarations.independence != "declared":
            required.add("independence_unestablished")
        if self.declarations.judge_output_exposure != "not_seen":
            required.add("judge_exposure")
        if (
            tuple(t.slot for t in self.turns) != ORDER
            or self.completion != ("COMPLETE" if complete else "UNABLE")
            or self.whole_run_verdict != verdict
            or not self.rationale.strip()
            or len(self.rationale.encode()) > 4096
            or len(set(self.inability_reasons)) != len(self.inability_reasons)
            or (set(self.inability_reasons) - {"reviewer_unavailable"}) != required
        ):
            raise ValueError("inconsistent_review")
        return self


def parse_review_payload(raw: bytes) -> ReviewPayload:
    return parse(ReviewPayload, raw, "invalid_review")


def serialize_review_payload(payload: ReviewPayload) -> bytes:
    return encode(checked(ReviewPayload, payload, "invalid_review"))


def human_quality(payload: ReviewPayload) -> QualityCheck:
    value = checked(ReviewPayload, payload, "invalid_review")
    if not value.declarations.quality_eligible:
        return QualityCheck(status="SKIP", issues=("review_quality_disqualified",))
    findings = tuple(c for t in value.turns for c in t.criteria)
    if any(c.finding == "FAIL" for c in findings):
        return QualityCheck(status="FAIL", issues=("human_criterion_failed",))
    if value.completion == "UNABLE":
        return QualityCheck(status="SKIP", issues=("human_review_unable",))
    return QualityCheck(status="PASS")


def public_key_blob(public_key: str) -> bytes:
    try:
        if type(public_key) is not str or len(public_key) > 128:
            raise ValueError
        algorithm, separator, encoded = public_key.partition(" ")
        blob = base64.b64decode(encoded, validate=True)
        if (
            algorithm != "ssh-ed25519"
            or separator != " "
            or base64.b64encode(blob).decode() != encoded
            or len(blob) != 51
            or blob[:19] != b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20"
        ):
            raise ValueError
        return blob
    except Exception:  # noqa: BLE001 - fixed privacy-safe boundary
        raise ReviewError("invalid_policy") from None


class SyntheticReviewPolicy(Frozen):
    schema_id: Literal["canary-synthetic-review-policy-v1"] = (
        "canary-synthetic-review-policy-v1"
    )
    policy_id: Identifier
    version: Literal[1] = 1
    expected_principal: Principal
    public_key: str = Field(repr=False)
    required_role: str
    purpose: str
    review_audience: Audience
    definition_identifier: str
    not_before: Timestamp
    expires_at: Timestamp
    max_submission_age_seconds: int = Field(default=86400, ge=1, le=604800)
    assurance_class: Literal["synthetic-offline-only"] = "synthetic-offline-only"

    @model_validator(mode="after")
    def _consistent(self) -> SyntheticReviewPolicy:
        public_key_blob(self.public_key)
        if time_value(self.not_before) >= time_value(self.expires_at):
            raise ValueError("invalid_policy_window")
        return self


def policy_identity(policy: SyntheticReviewPolicy) -> str:
    return fingerprint(
        checked(
            SyntheticReviewPolicy, policy, "invalid_policy", MAX_SMALL_BYTES
        ).model_dump(mode="json")
    )


class ReviewPolicyObservation(Frozen):
    schema_id: Literal["canary-review-policy-observation-v1"] = (
        "canary-review-policy-observation-v1"
    )
    policy: SyntheticReviewPolicy
    revocation_revision: int = Field(ge=0)
    revoked_public_key_sha256: tuple[Digest, ...] = Field(max_length=32)
    observed_at: Timestamp
    valid_until: Timestamp

    @model_validator(mode="after")
    def _window(self) -> ReviewPolicyObservation:
        if (
            not timedelta(0)
            < time_value(self.valid_until) - time_value(self.observed_at)
            <= timedelta(seconds=60)
            or tuple(sorted(set(self.revoked_public_key_sha256)))
            != self.revoked_public_key_sha256
        ):
            raise ValueError("invalid_policy_observation")
        return self


class SignatureVerification(Frozen):
    schema_id: Literal["canary-review-signature-verification-v1"] = (
        "canary-review-signature-verification-v1"
    )
    payload_sha256: Digest
    signature_sha256: Digest
    assignment_sha256: Digest
    trust_policy_identity_sha256: Digest
    signer_principal: Principal
    signer_public_key_sha256: Digest
    signature_cryptographically_verified: Literal[True] = True
    assurance: Assurance = Field(default_factory=Assurance)


class SubmissionVerification(SignatureVerification):
    observation_sha256: Digest
    verified_at: Timestamp
    current_policy_acceptable: Literal[True] = True


def _expected(
    payload: ReviewPayload, expected: ReviewAssignment, policy: SyntheticReviewPolicy
) -> None:
    if (
        payload.reviewer_principal != expected.reviewer_principal
        or policy.expected_principal != expected.reviewer_principal
    ):
        raise ReviewError("principal_mismatch")
    if policy.required_role != ROLE:
        raise ReviewError("role_not_authorised")
    if (
        policy.purpose != PURPOSE
        or policy.definition_identifier != DEFINITION
        or policy.review_audience != expected.review_audience
        or policy_identity(policy) != expected.trust_policy_identity_sha256
    ):
        raise ReviewError("policy_mismatch")
    values = {
        "review_id": expected.review_id,
        "assignment_id": expected.assignment_id,
        "assignment_sha256": assignment_commitment(expected),
        "round": expected.round,
        "register_id": expected.register_id,
        "review_audience": expected.review_audience,
        "trust_policy_identity_sha256": expected.trust_policy_identity_sha256,
        "envelope_commitment_sha256": expected.subject.expected_envelope.envelope_commitment_sha256,
        "packet_commitment_sha256": expected.packet_commitment_sha256,
        "presentation_sha256": expected.presentation_sha256,
        "rubric_sha256": expected.rubric_sha256,
    }
    if any(getattr(payload, name) != value for name, value in values.items()):
        raise ReviewError("binding_mismatch")


def _signature(payload: bytes, signature: bytes, policy: SyntheticReviewPolicy) -> None:
    if type(signature) is not bytes or not 0 < len(signature) <= MAX_SIGNATURE_BYTES:
        raise ReviewError("invalid_signature")
    try:
        with tempfile.TemporaryDirectory(
            prefix="canary-review-public-verification-"
        ) as temporary:
            directory = Path(temporary)
            for name, data in (
                (
                    "allowed-signers",
                    f'{policy.expected_principal} namespaces="{NAMESPACE}" {policy.public_key}\n'.encode(
                        "ascii"
                    ),
                ),
                ("review.sig", signature),
            ):
                fd = os.open(
                    directory / name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                )
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
            try:
                result = subprocess.run(
                    [
                        "/usr/bin/ssh-keygen",
                        "-Y",
                        "verify",
                        "-f",
                        str(directory / "allowed-signers"),
                        "-I",
                        policy.expected_principal,
                        "-n",
                        NAMESPACE,
                        "-s",
                        str(directory / "review.sig"),
                    ],
                    input=payload,
                    capture_output=True,
                    check=False,
                    timeout=5,
                    cwd=directory,
                    env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C"},
                )
            except (OSError, subprocess.SubprocessError):
                raise ReviewError("verifier_unavailable") from None
            if result.returncode != 0:
                raise ReviewError("signature_not_verified")
            digest = (
                base64.b64encode(sha256(public_key_blob(policy.public_key)).digest())
                .decode()
                .rstrip("=")
            )
            success = f'Good "{NAMESPACE}" signature for {policy.expected_principal} with ED25519 key SHA256:{digest}\n'.encode()
            if result.stdout != success or result.stderr:
                raise ReviewError("verifier_protocol_error")
    except ReviewError:
        raise
    except Exception:  # noqa: BLE001 - fixed privacy-safe boundary
        raise ReviewError("verification_storage_unavailable") from None


def verify_review_signature(
    payload: bytes,
    signature: bytes,
    *,
    expected: ReviewAssignment,
    trusted_policy: SyntheticReviewPolicy,
) -> SignatureVerification:
    value = parse_review_payload(payload)
    assignment = checked(
        ReviewAssignment, expected, "invalid_assignment", MAX_SMALL_BYTES
    )
    policy = checked(
        SyntheticReviewPolicy, trusted_policy, "invalid_policy", MAX_SMALL_BYTES
    )
    _expected(value, assignment, policy)
    _signature(payload, signature, policy)
    return SignatureVerification(
        payload_sha256=sha256(payload).hexdigest(),
        signature_sha256=sha256(signature).hexdigest(),
        assignment_sha256=assignment_commitment(assignment),
        trust_policy_identity_sha256=policy_identity(policy),
        signer_principal=policy.expected_principal,
        signer_public_key_sha256=sha256(public_key_blob(policy.public_key)).hexdigest(),
    )


def verify_current_policy(
    expected: ReviewAssignment, observation: ReviewPolicyObservation, now: datetime
) -> ReviewPolicyObservation:
    checked_now(now)
    value = checked(
        ReviewPolicyObservation, observation, "invalid_policy", MAX_SMALL_BYTES
    )
    policy = value.policy
    if (
        policy_identity(policy) != expected.trust_policy_identity_sha256
        or policy.expected_principal != expected.reviewer_principal
        or policy.required_role != ROLE
        or policy.purpose != PURPOSE
        or policy.definition_identifier != DEFINITION
        or policy.review_audience != expected.review_audience
    ):
        raise ReviewError("policy_mismatch")
    if not time_value(value.observed_at) <= now < time_value(value.valid_until):
        raise ReviewError("policy_stale")
    if not time_value(policy.not_before) <= now < time_value(policy.expires_at):
        raise ReviewError("policy_expired")
    if (
        sha256(public_key_blob(policy.public_key)).hexdigest()
        in value.revoked_public_key_sha256
    ):
        raise ReviewError("signer_revoked")
    return value


def verify_review_for_submission(
    payload: bytes,
    signature: bytes,
    *,
    expected: ReviewAssignment,
    observation: ReviewPolicyObservation,
    now: datetime,
) -> SubmissionVerification:
    assignment = checked(
        ReviewAssignment, expected, "invalid_assignment", MAX_SMALL_BYTES
    )
    observed = verify_current_policy(assignment, observation, now)
    result = verify_review_signature(
        payload, signature, expected=assignment, trusted_policy=observed.policy
    )
    reviewed = time_value(parse_review_payload(payload).reviewed_at)
    if (
        not time_value(assignment.opens_at) <= now < time_value(assignment.closes_at)
        or not time_value(assignment.opens_at)
        <= reviewed
        < time_value(assignment.closes_at)
        or not 0
        <= (now - reviewed).total_seconds()
        <= observed.policy.max_submission_age_seconds
    ):
        raise ReviewError("submission_time_invalid")
    return SubmissionVerification(
        **result.model_dump(),
        observation_sha256=fingerprint(observed.model_dump(mode="json")),
        verified_at=utc_text(now),
    )


class AssessmentInputs(Frozen):
    mechanical: QualityCheck
    operational: QualityCheck
    historical_overall: QualityCheck
    verification: QualityCheck
    human_state: Literal["PENDING", "COMPLETE", "UNABLE", "REJECTED"]
    review: ReviewPayload | None = Field(default=None, repr=False)


class RelianceDetails(Frozen):
    assignment_sha256: Digest
    subject: ReviewSubject
    rubric_sha256: Digest
    register_id: RegisterID
    register_state: Literal["EMPTY", "RECORDED", "CONFLICT", "UNAVAILABLE"]
    event_count: int | None = Field(ge=0, le=2)
    observed_head_sha256: Digest | None
    checkpoint_status: Literal[
        "matches", "missing", "stale", "behind", "mismatch", "unavailable"
    ]
    conflict_authentication: Literal["absent", "authenticated", "not-established"]
    reviewer_signature: Literal["verified", "not-performed", "error"]
    current_policy: Literal["acceptable", "error"]
    current_verified_at: Timestamp | None
    current_policy_observation_sha256: Digest | None
    source_comparison: Literal["matches-current-inspection", "error"]
    recorded_assessment_provenance: Literal[
        "anchored-journal-checks", "anchored-envelope-status-only", "not-established"
    ]
    authenticated_reviews: tuple[ReviewPayload, ...] = Field(repr=False)


class TurnQuality(Frozen):
    slot: Slot
    completion: Literal["COMPLETE", "INCOMPLETE"]
    declared_verdict: Verdict | None
    quality_eligible: bool
    assessment: QualityCheck
    critical_findings: tuple[CriterionID, ...]


class PostReviewAssessment(Frozen):
    schema_id: Literal["canary-post-review-assessment-v1"] = (
        "canary-post-review-assessment-v1"
    )
    inputs: AssessmentInputs
    human_quality: QualityCheck
    assessment: QualityCheck
    turn_quality: tuple[TurnQuality, ...] = ()
    journal_completion: Literal["completed", "not-established"] = "not-established"
    details: RelianceDetails | None = None
    source_verification_profile: Literal["anchored-envelope-current-journal-v1"] = (
        SOURCE_PROFILE
    )
    authority_consumption_evidence: Literal["recorded-in-anchored-envelope-only"] = (
        "recorded-in-anchored-envelope-only"
    )
    fresh_authority_store_inspection: Literal["not-performed"] = "not-performed"
    fresh_approval_signature_authentication: Literal["not-performed"] = "not-performed"
    assurance: Assurance = Field(default_factory=Assurance)


def combine_post_review(inputs: AssessmentInputs) -> PostReviewAssessment:
    """Pure supplied-input composition, not a provenance/admission capability."""
    value = checked(AssessmentInputs, inputs, "invalid_input", 4 * MAX_PAYLOAD_BYTES)
    if value.human_state == "REJECTED":
        human = QualityCheck(status="ERROR", issues=("review_verification_failed",))
    elif value.review is None:
        if value.human_state != "PENDING":
            raise ReviewError("invalid_input")
        human = QualityCheck(status="SKIP", issues=("human_review_pending",))
    else:
        if value.human_state != value.review.completion:
            raise ReviewError("invalid_input")
        human = human_quality(value.review)
    turns = []
    if value.review is not None:
        eligible = (
            value.human_state != "REJECTED"
            and value.review.declarations.quality_eligible
        )
        for turn in value.review.turns:
            if value.human_state == "REJECTED":
                quality = QualityCheck(
                    status="ERROR", issues=("review_verification_failed",)
                )
            elif not eligible:
                quality = QualityCheck(
                    status="SKIP", issues=("review_quality_disqualified",)
                )
            elif any(c.finding == "FAIL" for c in turn.criteria):
                quality = QualityCheck(
                    status="FAIL", issues=("human_criterion_failed",)
                )
            elif turn.completion == "INCOMPLETE":
                quality = QualityCheck(
                    status="SKIP", issues=("human_criterion_unassessable",)
                )
            else:
                quality = QualityCheck(status="PASS")
            critical = tuple(
                c.criterion_id
                for c in turn.criteria
                if c.finding == "FAIL" and c.criterion_id in ("R3", "R4", "R6", "R7")
            )
            turns.append(
                TurnQuality(
                    slot=turn.slot,
                    completion=turn.completion,
                    declared_verdict=turn.declared_verdict,
                    quality_eligible=eligible,
                    assessment=quality,
                    critical_findings=critical,
                )
            )
    return PostReviewAssessment(
        inputs=value,
        human_quality=human,
        turn_quality=tuple(turns),
        assessment=aggregate(
            (value.mechanical, value.operational, value.verification, human)
        ),
    )
