"""Synthetic supplied findings, never actual approval of shopper prose."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import test_canary_approval_v3 as approval_tests
from pydantic import ValidationError

from harness.canary import human_review_v3 as review
from harness.canary.envelope_v3 import ExpectedEnvelopeReference
from harness.core.fingerprints import canonical_json

NOW = datetime(2026, 11, 22, 12, tzinfo=UTC)
PRINCIPAL = "synthetic-reviewer@canary.invalid"
keys = approval_tests.keys


@pytest.fixture
def contract():
    public = (
        "ssh-ed25519 "
        + base64.b64encode(
            b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + b"\0" * 32
        ).decode()
    )
    policy = review.SyntheticReviewPolicy(
        policy_id="synthetic-review-policy",
        expected_principal=PRINCIPAL,
        public_key=public,
        required_role=review.ROLE,
        purpose=review.PURPOSE,
        review_audience="synthetic-review-local",
        definition_identifier=review.DEFINITION,
        not_before="2026-11-22T00:00:00Z",
        expires_at="2026-11-24T00:00:00Z",
    )
    reference = ExpectedEnvelopeReference(
        envelope_commitment_sha256="a" * 64,
        store_id="synthetic-store-" + "1" * 32,
        store_binding_sha256="b" * 64,
        registry_id="2" * 32,
        registry_binding_sha256="c" * 64,
        authorisation_id="synthetic-auth-" + "3" * 32,
        execution_audience="synthetic-execution",
        run_id="synthetic-run-" + "4" * 32,
    )
    subject = review.ReviewSubject(
        expected_envelope=reference,
        source_receipt_sha256="d" * 64,
        roster_fingerprint="e" * 64,
        definition_fingerprint="f" * 64,
        acceptance_policy="selection-v3",
        acceptance_fingerprint="a" * 64,
        execution_policy="execution-v3",
        execution_fingerprint="b" * 64,
        journal_history_commitment_sha256="c" * 64,
        evidence_sha256="d" * 64,
    )
    assignment = review.ReviewAssignment(
        assignment_id="synthetic-review-assignment-" + "5" * 32,
        review_id="synthetic-review-" + "6" * 32,
        round=1,
        register_id="synthetic-review-register-" + "7" * 32,
        review_audience=policy.review_audience,
        reviewer_principal=PRINCIPAL,
        trust_policy_identity_sha256=review.policy_identity(policy),
        subject=subject,
        packet_commitment_sha256="e" * 64,
        presentation_sha256="f" * 64,
        rubric_sha256=review.rubric_digest(),
        opens_at="2026-11-22T11:00:00Z",
        closes_at="2026-11-23T12:00:00Z",
    )
    return SimpleNamespace(policy=policy, assignment=assignment)


def make_review(
    assignment,
    *,
    failure=None,
    unknown=None,
    exposure="not_seen",
    independence="declared",
    unavailable=False,
):
    turns = []
    reasons = []
    for slot in review.ORDER:
        criteria = []
        for criterion in review.review_rubric().criteria:
            if slot not in criterion.slots:
                continue
            finding = (
                "FAIL"
                if (slot, criterion.id) == failure
                else "UNASSESSABLE"
                if (slot, criterion.id) == unknown
                else "PASS"
            )
            criteria.append(
                review.CriterionJudgement(
                    criterion_id=criterion.id,
                    finding=finding,
                    rationale="Synthetic fixture judgement; not an actual human approval.",
                    references=(
                        review.EvidenceReference(
                            slot=slot, item_id="chat", pointer="/message"
                        ),
                    ),
                )
            )
        complete = all(c.finding != "UNASSESSABLE" for c in criteria)
        turns.append(
            review.TurnJudgement(
                slot=slot,
                criteria=tuple(criteria),
                completion="COMPLETE" if complete else "INCOMPLETE",
                declared_verdict=(
                    "FAIL" if any(c.finding == "FAIL" for c in criteria) else "PASS"
                )
                if complete
                else None,
            )
        )
    if unknown:
        reasons.append("criterion_unassessable")
    if exposure != "not_seen":
        reasons.append("judge_exposure")
    if independence != "declared":
        reasons.append("independence_unestablished")
    if unavailable:
        reasons.append("reviewer_unavailable")
    complete = not reasons
    return review.ReviewPayload(
        review_id=assignment.review_id,
        assignment_id=assignment.assignment_id,
        assignment_sha256=review.assignment_commitment(assignment),
        round=assignment.round,
        register_id=assignment.register_id,
        review_audience=assignment.review_audience,
        reviewer_principal=assignment.reviewer_principal,
        trust_policy_identity_sha256=assignment.trust_policy_identity_sha256,
        envelope_commitment_sha256=assignment.subject.expected_envelope.envelope_commitment_sha256,
        packet_commitment_sha256=assignment.packet_commitment_sha256,
        presentation_sha256=assignment.presentation_sha256,
        rubric_sha256=assignment.rubric_sha256,
        reviewed_at=review.utc_text(NOW),
        turns=tuple(turns),
        completion="COMPLETE" if complete else "UNABLE",
        whole_run_verdict=("FAIL" if failure else "PASS") if complete else None,
        rationale="Synthetic review only.",
        references=(
            review.EvidenceReference(slot="A1", item_id="chat", pointer="/message"),
        ),
        inability_reasons=tuple(reasons),
        declarations=review.Declarations(
            judge_output_exposure=exposure, independence=independence
        ),
    )


@pytest.mark.parametrize(
    "failure,unknown,exposure,independence,quality,completion",
    [
        (None, None, "not_seen", "declared", "PASS", "COMPLETE"),
        (("A1", "R3"), None, "not_seen", "declared", "FAIL", "COMPLETE"),
        (None, ("A1", "R1"), "not_seen", "declared", "SKIP", "UNABLE"),
        (("A1", "R3"), ("A1", "R2"), "not_seen", "declared", "FAIL", "UNABLE"),
        (("A1", "R3"), ("B2", "R2"), "not_seen", "declared", "FAIL", "UNABLE"),
        (("A1", "R3"), ("B2", "R2"), "seen", "declared", "SKIP", "UNABLE"),
        (("A1", "R3"), None, "not_seen", "unknown", "SKIP", "UNABLE"),
    ],
)
def test_known_fail_is_retained_with_unknown_and_eligibility(
    contract, failure, unknown, exposure, independence, quality, completion
):
    payload = make_review(
        contract.assignment,
        failure=failure,
        unknown=unknown,
        exposure=exposure,
        independence=independence,
    )
    assert review.human_quality(payload).status == quality
    assert payload.completion == completion
    assert (
        payload.whole_run_verdict is None
        if completion == "UNABLE"
        else payload.whole_run_verdict in ("PASS", "FAIL")
    )
    if failure:
        assert (
            next(
                c
                for t in payload.turns
                if t.slot == failure[0]
                for c in t.criteria
                if c.criterion_id == failure[1]
            ).finding
            == "FAIL"
        )
    assert (
        review.parse_review_payload(review.serialize_review_payload(payload)) == payload
    )


def test_exact_rubric_and_applicability():
    rubric = review.review_rubric()
    assert [c.id for c in rubric.criteria] == [f"R{i}" for i in range(1, 8)]
    assert rubric.criteria[5].slots == ("A2",)
    assert rubric.criteria[6].slots == ("B1", "A2", "B2")
    assert [c.id for c in rubric.criteria if c.critical] == ["R3", "R4", "R6", "R7"]
    assert "not independently authenticated provider evidence" in rubric.instruction
    assert "does not establish" in rubric.reference_limitation
    assert (
        "recorded commerce evidence under the reviewed synthetic fixture assumptions"
        in rubric.criteria[2].text
    )


@pytest.mark.parametrize(
    "mechanical,operational,verification,expected",
    [
        ("PASS", "PASS", "PASS", "FAIL"),
        ("SKIP", "PASS", "PASS", "FAIL"),
        ("PASS", "ERROR", "PASS", "ERROR"),
        ("FAIL", "PASS", "ERROR", "ERROR"),
    ],
)
def test_aggregation_preserves_failure_and_error(
    contract, mechanical, operational, verification, expected
):
    def check(status):
        return review.QualityCheck(
            status=status, issues=() if status == "PASS" else ("synthetic_issue",)
        )

    payload = make_review(
        contract.assignment, failure=("A1", "R1"), unknown=("B2", "R2")
    )
    result = review.combine_post_review(
        review.AssessmentInputs(
            mechanical=check(mechanical),
            operational=check(operational),
            historical_overall=check("SKIP"),
            verification=check(verification),
            human_state="UNABLE",
            review=payload,
        )
    )
    assert result.human_quality.status == "FAIL"
    assert result.assessment.status == expected
    assert result.inputs.review.whole_run_verdict is None
    assert not result.assurance.authorises_live_execution


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "unknown",
        "duplicate",
        "coercion",
        "verdict",
        "turn",
        "rubric",
        "false_authority",
        "blank",
    ],
)
def test_strict_review_rejects_malformed_contracts(contract, change):
    value = make_review(contract.assignment).model_dump(mode="json")
    if change == "missing":
        del value["assurance"]
    elif change == "unknown":
        value["embedded_trust_policy"] = {}
    elif change == "coercion":
        value["round"] = "1"
    elif change == "verdict":
        value["whole_run_verdict"] = "FAIL"
    elif change == "turn":
        value["turns"].pop()
    elif change == "rubric":
        value["turns"][0]["criteria"].pop()
    elif change == "false_authority":
        value["assurance"]["authorises_live_execution"] = True
    elif change == "blank":
        value["rationale"] = " "
    raw = canonical_json(value).encode()
    if change == "duplicate":
        raw = b'{"round":1,' + raw[1:]
    with pytest.raises(review.ReviewError):
        review.parse_review_payload(raw)


@pytest.mark.parametrize(
    "change", ["newline", "whitespace", "invalid_utf8", "nan", "oversize", "depth"]
)
def test_canonical_bounds(contract, change):
    raw = review.serialize_review_payload(make_review(contract.assignment))
    raw = {
        "newline": raw + b"\n",
        "whitespace": b" " + raw,
        "invalid_utf8": b"\xff",
        "nan": b'{"x":NaN}',
        "oversize": b"x" * 65537,
        "depth": b"[" * 65 + b"]" * 65,
    }[change]
    with pytest.raises(review.ReviewError):
        review.parse_review_payload(raw)


def test_immutable_nested_and_bypass_revalidation(contract):
    payload = make_review(contract.assignment)
    with pytest.raises(ValidationError):
        payload.turns[0].criteria[0].finding = "FAIL"
    forged = payload.model_copy(update={"whole_run_verdict": "FAIL"})
    with pytest.raises(review.ReviewError):
        review.serialize_review_payload(forged)


@pytest.mark.parametrize("pointer", ["file:///private", "x", "/bad~", "/bad~2"])
def test_pointer_syntax(pointer):
    with pytest.raises(ValidationError):
        review.EvidenceReference(slot="A1", item_id="chat", pointer=pointer)


def observation(policy, now=NOW, revoked=False):
    from hashlib import sha256

    return review.ReviewPolicyObservation(
        policy=policy,
        revocation_revision=int(revoked),
        revoked_public_key_sha256=(
            sha256(review.public_key_blob(policy.public_key)).hexdigest(),
        )
        if revoked
        else (),
        observed_at=review.utc_text(now),
        valid_until=review.utc_text(now + timedelta(seconds=30)),
    )


@pytest.fixture
def crypto_contract(contract, keys):
    policy = contract.policy.model_copy(update={"public_key": keys.public_key})
    assignment = contract.assignment.model_copy(
        update={"trust_policy_identity_sha256": review.policy_identity(policy)}
    )
    return SimpleNamespace(policy=policy, assignment=assignment)


def test_actual_review_signature_and_repeatable_math(crypto_contract, keys):
    payload = review.serialize_review_payload(make_review(crypto_contract.assignment))
    signature = keys.sign(payload, namespace=review.NAMESPACE)
    for _ in range(2):
        result = review.verify_review_for_submission(
            payload,
            signature,
            expected=crypto_contract.assignment,
            observation=observation(crypto_contract.policy),
            now=NOW,
        )
        assert (
            result.signature_cryptographically_verified
            and result.current_policy_acceptable
        )
        assert result.signer_principal == PRINCIPAL
        assert not any(
            result.assurance.model_dump()[name]
            for name in review.Assurance.model_fields
            if name != "assurance_class"
        )


@pytest.mark.parametrize(
    "fault",
    [
        "unknown_key",
        "approval_namespace",
        "file_namespace",
        "seal_namespace",
        "tampered_payload",
        "tampered_signature",
        "wrong_principal",
        "wrong_assignment",
        "wrong_evidence",
        "wrong_packet",
        "wrong_policy",
        "wrong_role",
        "wrong_purpose",
        "wrong_audience",
        "wrong_definition",
        "revoked",
        "stale",
        "expired",
        "future_claim",
        "assignment_closed",
    ],
)
def test_actual_crypto_and_policy_denials(crypto_contract, keys, fault):
    assignment = crypto_contract.assignment
    policy = crypto_contract.policy
    payload = review.serialize_review_payload(make_review(assignment))
    namespace = {
        "approval_namespace": approval_tests.approval.APPROVAL_NAMESPACE,
        "file_namespace": "file",
        "seal_namespace": "canary-seal-v3@ai-test-harness.invalid",
    }.get(fault, review.NAMESPACE)
    signature = keys.sign(payload, namespace=namespace, unknown=fault == "unknown_key")
    now = NOW
    observed = observation(policy)
    if fault == "tampered_payload":
        value = review.parse_review_payload(payload).model_copy(
            update={"rationale": "Altered rationale"}
        )
        payload = review.serialize_review_payload(value)
    elif fault == "tampered_signature":
        import base64

        lines = signature.splitlines()
        decoded = bytearray(base64.b64decode(b"".join(lines[1:-1])))
        decoded[-1] ^= 1
        signature = b"\n".join([lines[0], base64.b64encode(decoded), lines[-1], b""])
    elif fault == "wrong_principal":
        assignment = assignment.model_copy(
            update={"reviewer_principal": "synthetic-other@canary.invalid"}
        )
    elif fault == "wrong_assignment":
        assignment = assignment.model_copy(update={"round": 2})
    elif fault == "wrong_evidence":
        subject = assignment.subject.model_copy(update={"evidence_sha256": "0" * 64})
        assignment = assignment.model_copy(update={"subject": subject})
    elif fault == "wrong_packet":
        assignment = assignment.model_copy(
            update={"packet_commitment_sha256": "0" * 64}
        )
    elif fault in {
        "wrong_policy",
        "wrong_role",
        "wrong_purpose",
        "wrong_audience",
        "wrong_definition",
    }:
        field, value = {
            "wrong_policy": ("policy_id", "synthetic-other-policy"),
            "wrong_role": ("required_role", "synthetic-canary-approver"),
            "wrong_purpose": ("purpose", "approval"),
            "wrong_audience": ("review_audience", "synthetic-other"),
            "wrong_definition": ("definition_identifier", "salesagent-canary-c1-v1"),
        }[fault]
        policy = policy.model_copy(update={field: value})
        observed = observation(policy)
    elif fault == "revoked":
        observed = observation(policy, revoked=True)
    elif fault == "stale":
        observed = observation(policy, NOW - timedelta(seconds=30))
    elif fault == "expired":
        now = datetime(2026, 11, 24, tzinfo=UTC)
        observed = observation(policy, now)
    elif fault == "future_claim":
        now = NOW - timedelta(seconds=1)
        observed = observation(policy, now)
    elif fault == "assignment_closed":
        now = datetime(2026, 11, 23, 12, tzinfo=UTC)
        observed = observation(policy, now)
    with pytest.raises(review.ReviewError) as caught:
        review.verify_review_for_submission(
            payload, signature, expected=assignment, observation=observed, now=now
        )
    assert "PRIVATE" not in str(caught.value)


def test_math_validity_is_separate_from_current_revocation(crypto_contract, keys):
    payload = review.serialize_review_payload(make_review(crypto_contract.assignment))
    signature = keys.sign(payload, namespace=review.NAMESPACE)
    assert review.verify_review_signature(
        payload,
        signature,
        expected=crypto_contract.assignment,
        trusted_policy=crypto_contract.policy,
    ).signature_cryptographically_verified
    with pytest.raises(review.ReviewError, match="^signer_revoked$"):
        review.verify_review_for_submission(
            payload,
            signature,
            expected=crypto_contract.assignment,
            observation=observation(crypto_contract.policy, revoked=True),
            now=NOW,
        )


@pytest.mark.parametrize(
    "clock",
    [NOW.replace(tzinfo=None), NOW.replace(microsecond=1), "2026-11-22T12:00:00Z"],
)
def test_explicit_clock_is_strict(crypto_contract, keys, clock):
    payload = review.serialize_review_payload(make_review(crypto_contract.assignment))
    signature = keys.sign(payload, namespace=review.NAMESPACE)
    with pytest.raises(review.ReviewError, match="^invalid_clock$"):
        review.verify_review_for_submission(
            payload,
            signature,
            expected=crypto_contract.assignment,
            observation=observation(crypto_contract.policy),
            now=clock,
        )


@pytest.mark.parametrize("fault", ["unavailable", "timeout", "stdout", "stderr"])
def test_verifier_failure_is_private(crypto_contract, keys, monkeypatch, fault):
    import subprocess

    payload = review.serialize_review_payload(make_review(crypto_contract.assignment))
    signature = keys.sign(payload, namespace=review.NAMESPACE)

    def broken(*args, **kwargs):
        if fault == "unavailable":
            raise OSError("PRIVATE_EXECUTABLE")
        if fault == "timeout":
            raise subprocess.TimeoutExpired("PRIVATE_COMMAND", 5)
        return SimpleNamespace(
            returncode=0,
            stdout=b"PRIVATE_STDOUT" if fault == "stdout" else b"",
            stderr=b"PRIVATE_STDERR" if fault == "stderr" else b"",
        )

    monkeypatch.setattr(review.subprocess, "run", broken)
    with pytest.raises(review.ReviewError) as caught:
        review.verify_review_for_submission(
            payload,
            signature,
            expected=crypto_contract.assignment,
            observation=observation(crypto_contract.policy),
            now=NOW,
        )
    assert "PRIVATE" not in str(caught.value)


def test_no_ambient_credentials_or_execution_approval(
    crypto_contract, keys, monkeypatch
):
    import os

    payload = review.serialize_review_payload(make_review(crypto_contract.assignment))
    signature = keys.sign(payload, namespace=review.NAMESPACE)

    def forbidden(*args, **kwargs):
        pytest.fail("Execution approval must not be verified")

    monkeypatch.setattr(approval_tests.approval, "verify_approval", forbidden)

    class Environment(dict):
        def get(self, name, default=None):
            if name.startswith(("OPENAI_", "SALESAGENT_", "SSH_")):
                pytest.fail("Ambient credential access")
            return super().get(name, default)

    monkeypatch.setattr(os, "environ", Environment(os.environ))
    result = review.verify_review_for_submission(
        payload,
        signature,
        expected=crypto_contract.assignment,
        observation=observation(crypto_contract.policy),
        now=NOW,
    )
    assert not result.assurance.real_person_identity_authenticated
