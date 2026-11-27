"""Identity-linked synthetic interoperability; never mandatory dispatch authority."""

from __future__ import annotations

import copy
import json
import resource
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from time import monotonic
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import test_canary_approval_v3 as approval_tests
import test_canary_driver_v3 as driver_tests
import test_canary_envelope_v3 as envelope_tests
import test_canary_human_review_v3 as review_tests
import test_canary_instrumentation_v3 as instrumentation_tests
import test_canary_journal_v3 as journal_tests
import test_canary_spending_v3 as spending_tests

from harness.canary import approval_v3 as approval
from harness.canary import authority_v3 as authority
from harness.canary import envelope_v3 as envelope
from harness.canary import human_review_v3 as review
from harness.canary import journal_v3 as journal
from harness.canary import review_packet_v3 as packet
from harness.canary import review_register_v3 as register
from harness.canary import runtime_v3 as runtime
from harness.canary import spending_v3 as spending
from harness.canary.driver_v3 import MockApplicationGatewayV3, OrderedCanaryDriverV3
from harness.canary.instrumentation_v3 import (
    BoundedResponsesClientV3,
    ProviderTransportV3,
)
from harness.core.fingerprints import canonical_json, fingerprint

T = datetime(2026, 11, 24, 12, tzinfo=UTC)
ORDER = ("A1", "B1", "A2", "B2")
keys = approval_tests.keys
source = spending_tests.source
spending_case = spending_tests.case


def text_time(value=T):
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def commitment(value):
    """Independent fixture-side computation of the documented commitment domains."""
    return sha256(canonical_json(value).encode()).hexdigest()


def snapshot(root):
    """Content/layout identity; reading may legitimately advance atime."""
    result = {}
    for path in [Path(root), *sorted(Path(root).rglob("*"))]:
        info = path.lstat()
        result[str(path.relative_to(root))] = (
            info.st_dev,
            info.st_ino,
            info.st_mode,
            info.st_nlink,
            info.st_uid,
            info.st_gid,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
            path.read_bytes() if path.is_file() else None,
        )
    return result


def protected(path):
    path = Path(path).resolve()
    info = path.stat()
    return packet.ProtectedRoot(
        path=str(path), device=info.st_dev, directory_inode=info.st_ino
    )


def prepare(root, keys, *, secondary=False, source_receipt=None):
    root.mkdir(mode=0o700)
    receipt = source_receipt or journal_tests.receipt()
    if source_receipt is None and receipt.runtime.python.startswith("3.13."):
        receipt = receipt.model_copy(
            update={
                "runtime": receipt.runtime.model_copy(
                    update={"dependency_lock": "application"}
                )
            }
        )
    runtime.validate_binding(receipt.binding)
    receipt = runtime.parse_receipt(receipt)
    proposal = approval.ProposedCanary(
        authorisation_id="synthetic-auth-" + uuid4().hex,
        execution_audience="synthetic-slice6f-host",
        source_receipt=receipt,
        source_receipt_sha256=fingerprint(receipt.model_dump(mode="json")),
        project_id="proj_synthetic_slice6f_" + ("b" if secondary else "a"),
        organization_id="org_synthetic_slice6f",
        credential_provisioning_reference=None,
    )
    policy = approval.SyntheticTrustPolicy(
        schema_id="canary-synthetic-trust-v1",
        policy_id="synthetic-policy-" + uuid4().hex,
        expected_principal=approval_tests.PRINCIPAL,
        public_key=keys.unknown_public_key if secondary else keys.public_key,
        roles=(approval.APPROVAL_ROLE,),
    )
    manifest = approval.ApprovalManifest(
        schema_id="canary-synthetic-approval-v1",
        purpose="synthetic-offline-target-only-canary-v3",
        environment="synthetic-offline",
        signature_namespace=approval.APPROVAL_NAMESPACE,
        execution=proposal,
        issuer_principal=policy.expected_principal,
        created_at=text_time(T - timedelta(seconds=60)),
        not_before=text_time(),
        expires_at=text_time(T + timedelta(minutes=30)),
        judge_authority=False,
        study_authority=False,
        replacement_authority=False,
        resume_authority=False,
        authorises_live_execution=False,
    )
    raw = approval.serialize_manifest(manifest)
    signature = keys.sign(raw, unknown=secondary)
    configuration = authority.TrustedStoreConfiguration(
        schema_id="canary-synthetic-authority-config-v1",
        store_path=str((root / "authority").resolve()),
        store_id="synthetic-store-" + uuid4().hex,
        execution_audience=proposal.execution_audience,
        trust_policy_identity_sha256=authority.policy_identity(policy),
        host_id="synthetic-slice6f-host",
        host_scope="synthetic-single-host-local",
    )
    return SimpleNamespace(
        root=root,
        keys=keys,
        secondary=secondary,
        receipt=receipt,
        proposal=proposal,
        policy=policy,
        manifest=manifest,
        signed=(raw, signature),
        configuration=configuration,
        source_matching="not-performed; synthetic receipt claims only",
    )


def approval_observation(flow, policy=None):
    return authority.PolicyObservation(
        schema_id="canary-synthetic-policy-observation-v1",
        policy=policy or flow.policy,
        observed_at=text_time(),
        expires_at=text_time(T + timedelta(seconds=30)),
    )


def consume(flow):
    flow.verified = approval.verify_approval(
        *flow.signed, expected=flow.proposal, trust_policy=flow.policy, now=T
    )
    flow.store = authority.initialize_store(flow.configuration)
    flow.consumed = authority.consume_approval(
        *flow.signed,
        expected=flow.proposal,
        store=flow.store,
        policy=lambda: approval_observation(flow),
        clock=lambda: T,
    )
    assert flow.consumed.payload_sha256 == sha256(flow.signed[0]).hexdigest()
    assert flow.consumed.signature_sha256 == sha256(flow.signed[1]).hexdigest()
    assert flow.consumed.source_receipt_sha256 == flow.proposal.source_receipt_sha256
    assert flow.consumed.proposal_sha256 == commitment(
        flow.proposal.model_dump(mode="json")
    )
    assert flow.consumed.trust_policy_sha256 == commitment(
        flow.policy.model_dump(mode="json")
    )
    assert flow.consumed.store_id == flow.configuration.store_id
    assert flow.consumed.signer_principal == flow.policy.expected_principal
    assert flow.consumed.verification_sha256 == fingerprint(
        flow.verified.model_dump(mode="json")
    )
    assert (
        authority.inspect_consumption(flow.store, flow.proposal.authorisation_id).record
        == flow.consumed
    )
    return flow


def execute(flow, *, fail=False, timeout=False, calls=2, attempts=1, before_run=None):
    flow.registry = journal.initialize_registry(flow.root / "journal")
    flow.writer = journal.CanaryJournal(
        flow.registry,
        flow.consumed.intended_run_id,
        flow.consumed.authorisation_id,
        source_receipt=flow.receipt,
    )
    binding = flow.writer.bind_provider(
        flow.receipt.binding,
        project_id=flow.proposal.project_id,
        organization_id=flow.proposal.organization_id,
    )
    flow.forwarded, flow.cleaned = [], []

    def respond(request):
        observed = flow.writer.provider_snapshot(binding)
        slot, number = observed.active_slot, observed.next_logical_call - 1
        attempt = int(request.headers["x-stainless-retry-count"]) + 1
        flow.forwarded.append((slot, number, attempt))
        if timeout:
            raise httpx.ReadTimeout("PRIVATE_SYNTHETIC_TRANSPORT")
        if attempt < attempts:
            return httpx.Response(
                500, json=journal_tests.retry_failure(known_zero_usage=True)
            )
        usage = {"input_tokens": 100 + number, "output_tokens": 10 + number}
        usage["total_tokens"] = sum(usage.values())
        return httpx.Response(
            200,
            json={
                "id": f"resp_{slot}_{number}",
                "model": binding.definition.inference.model,
                "status": "completed",
                "usage": usage,
                "output": [
                    {
                        "public": journal_tests.selected(slot),
                        "reasoning": "PRIVATE_PROVIDER_REASONING",
                    }
                ],
            },
        )

    flow.provider = ProviderTransportV3(
        flow.writer,
        binding,
        httpx.MockTransport(respond),
        guards=instrumentation_tests.attempt_guards,
    )

    def create(request):
        for retry in range(attempts):
            response = flow.provider.handle_request(
                instrumentation_tests.prepared(binding, request, retry=retry)
            )
            try:
                if response.status_code == 200:
                    raw = response.json()
                    return SimpleNamespace(
                        response_id=raw["id"],
                        usage=raw["usage"],
                        public_output=raw["output"][0]["public"],
                    )
            finally:
                response.close()
        raise AssertionError("scripted retries exhausted")

    flow.driver = OrderedCanaryDriverV3(
        flow.writer,
        BoundedResponsesClientV3(
            SimpleNamespace(create_response=create), flow.provider
        ),
        guards=journal_tests.ready,
        close_client=lambda: flow.cleaned.append(True),
    )

    def mutate(slot, value):
        if fail and slot == "A1":
            value["trace"]["resolved_constraints"]["maximum_price"] = "1.00"

    flow.app = driver_tests.StatefulApplication(
        flow.driver.responses_client, mutate=mutate, calls=calls
    )
    flow.gateway = MockApplicationGatewayV3(
        httpx.MockTransport(flow.app), responses_client=flow.driver.responses_client
    )
    if before_run:
        before_run(flow)
    flow.report = flow.driver.run(flow.gateway)
    flow.report = {
        **flow.report,
        **journal.inspect_run(flow.registry, flow.consumed.intended_run_id),
    }
    return flow


def envelope_arguments(flow):
    return {
        "payload": flow.signed[0],
        "signature": flow.signed[1],
        "expected_proposal": flow.proposal,
        "store": flow.store,
        "registry": flow.registry,
        "run_id": flow.consumed.intended_run_id,
    }


def anchor(flow):
    flow.envelope = envelope.assemble_envelope(**envelope_arguments(flow))
    value, report = (
        flow.envelope,
        journal.inspect_run(flow.registry, flow.consumed.intended_run_id),
    )
    assert value.authority.receipt == flow.consumed
    assert value.source == envelope_tests.source_projection(flow.receipt)
    assert value.authority.store_binding_sha256 == commitment(
        flow.store.model_dump(mode="json")
    )
    assert value.source.receipt_sha256 == flow.proposal.source_receipt_sha256
    assert value.source.harness == flow.receipt.harness
    assert value.source.inference == flow.receipt.binding.inference
    assert value.source.limits == flow.receipt.binding.limits
    assert value.journal.run_id == flow.consumed.intended_run_id
    assert value.journal.approval_id == flow.proposal.authorisation_id
    assert value.journal.validated_records == len(report["records"])
    assert value.journal.evidence_sha256 == report["evidence_sha256"]
    assert value.accounting.model_dump(mode="json") == report["accounting"]
    assert value.journal.history_commitment_sha256 == commitment(
        {
            "domain": "canary-detached-journal-history-v1",
            "canonicalization": "replay-canonical-json-v1",
            "journal_schema": journal.SCHEMA,
            "registry_id": flow.registry.registry_id,
            "run_id": flow.consumed.intended_run_id,
            "records": report["records"],
        }
    )
    flow.reference = envelope.ExpectedEnvelopeReference(
        envelope_commitment_sha256=commitment(
            {
                "domain": "canary-detached-envelope-v1",
                "canonicalization": "replay-canonical-json-v1",
                "envelope": value.model_dump(mode="json"),
            }
        ),
        store_id=flow.configuration.store_id,
        store_binding_sha256=commitment(flow.store.model_dump(mode="json")),
        registry_id=flow.registry.registry_id,
        registry_binding_sha256=commitment(flow.registry.model_dump(mode="json")),
        authorisation_id=flow.proposal.authorisation_id,
        execution_audience=flow.proposal.execution_audience,
        run_id=flow.consumed.intended_run_id,
    )
    flow.raw = envelope.serialize_envelope(value)
    return flow


def publish(flow):
    root = flow.root / "envelopes"
    root.mkdir(mode=0o700)
    info = root.stat()
    flow.publication_root = envelope.TrustedPublicationRoot(
        path=str(root), device=info.st_dev, directory_inode=info.st_ino
    )
    retained = flow.reference.model_dump_json()
    result = envelope.publish_envelope(
        flow.envelope,
        publication_root=flow.publication_root,
        publication_id="accepted",
        store=flow.store,
        registry=flow.registry,
    )
    assert result.reference_candidate == flow.reference
    assert flow.reference.model_dump_json() == retained
    envelope.read_envelope(
        publication_root=flow.publication_root,
        publication_id="accepted",
        expected=flow.reference,
    )
    path = root / "accepted" / "envelope.json"
    assert path.stat().st_size <= envelope.MAX_ENVELOPE_BYTES
    flow.raw = path.read_bytes()
    assert (
        envelope.verify_envelope(flow.raw, expected=flow.reference).source_comparison
        == "not-performed"
    )
    assert (
        envelope.verify_against_sources(
            flow.raw,
            expected=flow.reference,
            **{k: v for k, v in envelope_arguments(flow).items() if k != "run_id"},
        ).source_comparison
        == "matches-reobserved-sources"
    )
    return flow


def assign(flow):
    material = packet.acquire_packet(
        flow.raw, expected=flow.reference, registry=flow.registry
    )
    assert (
        packet.acquire_packet(flow.raw, expected=flow.reference, registry=flow.registry)
        == material
    )
    assert packet.render_packet(material.packet) == material.presentation
    assert material.packet_commitment_sha256 == commitment(
        {
            "domain": "canary-review-packet-v1",
            "canonicalization": "replay-canonical-json-v1",
            "packet": material.packet.model_dump(mode="json"),
        }
    )
    assert material.presentation_sha256 == sha256(material.presentation).hexdigest()
    subject = material.packet.subject
    assert subject.expected_envelope == flow.reference
    assert subject.source_receipt_sha256 == flow.proposal.source_receipt_sha256
    assert (
        subject.journal_history_commitment_sha256
        == flow.envelope.journal.history_commitment_sha256
    )
    assert subject.evidence_sha256 == flow.report["evidence_sha256"]
    flow.review_policy = review.SyntheticReviewPolicy(
        policy_id="synthetic-review-policy-" + uuid4().hex,
        expected_principal=review_tests.PRINCIPAL,
        public_key=flow.policy.public_key,
        required_role=review.ROLE,
        purpose=review.PURPOSE,
        review_audience="synthetic-review-slice6f",
        definition_identifier=review.DEFINITION,
        not_before=text_time(T - timedelta(hours=1)),
        expires_at=text_time(T + timedelta(days=1)),
    )
    flow.assignment = review.ReviewAssignment(
        assignment_id="synthetic-review-assignment-" + uuid4().hex,
        review_id="synthetic-review-" + uuid4().hex,
        round=1,
        register_id="synthetic-review-register-" + uuid4().hex,
        review_audience=flow.review_policy.review_audience,
        reviewer_principal=review_tests.PRINCIPAL,
        trust_policy_identity_sha256=review.policy_identity(flow.review_policy),
        subject=subject,
        packet_commitment_sha256=material.packet_commitment_sha256,
        presentation_sha256=material.presentation_sha256,
        rubric_sha256=review.rubric_digest(),
        opens_at=text_time(T - timedelta(seconds=60)),
        closes_at=text_time(T + timedelta(hours=1)),
    )
    flow.material = material
    packet.verify_assignment_packet(material, flow.assignment)
    root = flow.root / "packets"
    root.mkdir(mode=0o700)
    info = root.stat()
    flow.packet_root = packet.PacketPublicationRoot(
        path=str(root), device=info.st_dev, directory_inode=info.st_ino
    )
    packet.publish_packet(
        material,
        root=flow.packet_root,
        publication_id="accepted",
        protected_roots=(
            protected(flow.registry.path),
            protected(flow.configuration.store_path),
        ),
    )
    assert (
        packet.read_packet(
            root=flow.packet_root,
            publication_id="accepted",
            expected_assignment=flow.assignment,
        )
        == material
    )
    return flow


def review_observation(flow, *, revoked=False):
    return review.ReviewPolicyObservation(
        policy=flow.review_policy,
        revocation_revision=1 if revoked else 0,
        revoked_public_key_sha256=(
            sha256(review.public_key_blob(flow.review_policy.public_key)).hexdigest(),
        )
        if revoked
        else (),
        observed_at=text_time(),
        valid_until=text_time(T + timedelta(seconds=30)),
    )


def initialise_review(flow):
    config = register.ReviewRegisterConfiguration(
        path=str(flow.root / "reviews"),
        register_id=flow.assignment.register_id,
        host_id="synthetic-slice6f-host",
        assignment=flow.assignment,
        assignment_sha256=review.assignment_commitment(flow.assignment),
        trust_policy_identity_sha256=flow.assignment.trust_policy_identity_sha256,
    )
    result = register.initialize_register(
        config,
        protected_roots=(
            protected(flow.registry.path),
            protected(flow.configuration.store_path),
        ),
    )
    flow.register = result.binding
    assert flow.register.configuration == config
    zero = commitment(
        {
            "domain": "canary-review-register-zero-head-v1",
            "register_schema": register.REGISTER_SCHEMA,
            "register_id": config.register_id,
            "register_binding_sha256": commitment(
                flow.register.model_dump(mode="json")
            ),
            "assignment_sha256": config.assignment_sha256,
            "trust_policy_identity_sha256": config.trust_policy_identity_sha256,
        }
    )
    flow.checkpoint = register.ReviewRegisterCheckpoint(
        register_id=config.register_id,
        register_binding_sha256=commitment(flow.register.model_dump(mode="json")),
        assignment_sha256=config.assignment_sha256,
        trust_policy_identity_sha256=config.trust_policy_identity_sha256,
        event_count=0,
        head_sha256=zero,
    )
    assert result.checkpoint_candidate == flow.checkpoint
    flow.zero = flow.checkpoint
    observed = register.inspect_register(
        flow.register, expected=flow.assignment, checkpoint=flow.checkpoint
    )
    assert (
        observed.state == "EMPTY"
        and observed.checkpoint_status == "matches"
        and not observed.issues
    )
    return flow


def review_bytes(flow, **changes):
    value = review_tests.make_review(flow.assignment, **changes).model_copy(
        update={"reviewed_at": text_time()}
    )
    raw = review.serialize_review_payload(value)
    signature = flow.keys.sign(raw, unknown=flow.secondary, namespace=review.NAMESPACE)
    assert review.verify_review_signature(
        raw, signature, expected=flow.assignment, trusted_policy=flow.review_policy
    ).signature_cryptographically_verified
    return raw, signature


def registration_arguments(flow):
    return {
        "expected": flow.assignment,
        "envelope_raw": flow.raw,
        "registry": flow.registry,
        "register": flow.register,
    }


def submit(flow, signed=None):
    return register.register_review(
        *(signed or review_bytes(flow)),
        **registration_arguments(flow),
        policy=lambda: review_observation(flow),
        clock=lambda: T,
    )


def retain(flow, result, signed):
    """Operator validates persisted event; never adopt a returned checkpoint blindly."""
    observed = register.inspect_register(
        flow.register, expected=flow.assignment, checkpoint=flow.checkpoint
    )
    assert observed.checkpoint_status == "stale"
    event = observed.events[-1]
    assert event.payload_utf8.encode() == signed[0]
    import base64

    assert base64.b64decode(event.signature_base64, validate=True) == signed[1]
    actual = review.verify_review_for_submission(
        *signed, expected=flow.assignment, observation=review_observation(flow), now=T
    )
    assert event.verification == actual and event.observation == review_observation(
        flow
    )
    assert event.admission_checked_at == text_time()
    assert event.previous_sha256 == flow.checkpoint.head_sha256
    assert event.event_sha256 == commitment(
        {
            "domain": "canary-registered-review-event-v1",
            "event": event.model_dump(mode="json", exclude={"event_sha256"}),
        }
    )
    packet.validate_references(
        review.parse_review_payload(signed[0]), flow.material.packet
    )
    expected = flow.checkpoint.model_copy(
        update={"event_count": event.sequence, "head_sha256": event.event_sha256}
    )
    assert result.checkpoint_candidate == expected
    flow.checkpoint = register.ReviewRegisterCheckpoint.model_validate_json(
        expected.model_dump_json()
    )


def assess_review(flow, *, checkpoint=None, revoked=False):
    return register.assess_registered_review(
        flow.register,
        expected=flow.assignment,
        checkpoint=checkpoint if checkpoint is not None else flow.checkpoint,
        envelope_raw=flow.raw,
        registry=flow.registry,
        policy=lambda: review_observation(flow, revoked=revoked),
        clock=lambda: T,
    )


def complete(
    root, keys, *, secondary=False, fail=False, register_now=True, calls=2, attempts=1
):
    flow = prepare(root, keys, secondary=secondary)
    consume(flow)
    execute(flow, fail=fail, calls=calls, attempts=attempts)
    anchor(flow)
    publish(flow)
    assign(flow)
    initialise_review(flow)
    if register_now:
        signed = review_bytes(flow)
        result = submit(flow, signed)
        assert result.status == "RECORDED"
        retain(flow, result, signed)
        observed = assess_review(flow)
        assert observed.inputs.verification.status == "PASS"
        assert observed.assessment.status == ("FAIL" if fail else "PASS")
    return flow


def spending_inputs(template, flow):
    case = copy.deepcopy(template)
    case["assignment"]["source_receipt"] = flow.receipt.model_dump(mode="json")
    case["assignment"]["source_receipt_sha256"] = flow.proposal.source_receipt_sha256
    case["assignment"]["assignment_id"] = "assignment-" + uuid4().hex
    case["policy"]["policy_id"] = "policy-" + uuid4().hex

    def replace(value):
        if isinstance(value, dict):
            return {k: replace(v) for k, v in value.items()}
        if isinstance(value, list):
            return [replace(v) for v in value]
        if value == "proj_synthetic_test":
            return flow.proposal.project_id
        if value == "org_synthetic_test":
            return flow.proposal.organization_id
        return value

    return replace(case)


def assess_spending(case, *, now=T):
    a, p, b, ref = spending_tests.prepared(case)
    result = spending.assess_spending(
        spending.serialize_bundle(b), assignment=a, policy=p, expected=ref, now=now
    )
    assert result.assurance.real_external_readiness == "UNESTABLISHED"
    assert not any(v for _, v in result.assurance if type(v) is bool)
    return result


def measurement(flow):
    return {
        "records": len(flow.report["records"]),
        "calls": flow.report["accounting"]["logical_calls"],
        "attempts": flow.report["accounting"]["provider_attempts"],
        "envelope_bytes": len(flow.raw),
        "packet_bytes": len(packet.serialize_packet(flow.material.packet)),
        "presentation_bytes": len(flow.material.presentation),
        "source_bytes": sum(
            p.stat().st_size for p in Path(flow.registry.path).rglob("*") if p.is_file()
        ),
        "register_bytes": (Path(flow.register.configuration.path) / register.DATABASE)
        .stat()
        .st_size,
        "process_peak_rss_native": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }


def test_complete_identity_linked_lifecycle(tmp_path, keys, spending_case):
    """P0-01, P0-18: actual harness execution against scripted application."""
    started = monotonic()
    flow = prepare(tmp_path / "a", keys)
    diagnostic = assess_spending(spending_inputs(spending_case, flow))
    assert (
        diagnostic.diagnostic_outcome == "CONDITIONALLY_CONFORMANT"
        and diagnostic.headroom_usd == "4"
    )
    consume(flow)
    execute(flow)
    anchor(flow)
    publish(flow)
    assign(flow)
    initialise_review(flow)
    report = flow.report
    assert report["status"] == report["driver_status"] == "completed"
    assert report["shopper_posts"] == 4 and report["trace_reads"] == 8
    assert [slot for slot, _ in flow.app.posts] == list(ORDER)
    assert (
        len(flow.forwarded)
        == report["accounting"]["logical_calls"]
        == report["accounting"]["provider_attempts"]
        == 8
    )
    assert report["completion_certified"] and report["accounting_reconciled"]
    assert (
        report["mechanical_assessment"]["status"]
        == report["operational_assessment"]["status"]
        == "PASS"
    )
    assert (
        report["assessment"]["status"] == "SKIP"
        and flow.material.packet.assessments.historical_overall.status == "SKIP"
    )
    assert [len(history) for _, history in flow.app.handoffs] == [2, 2, 4, 4]
    a, b = [body["session_id"] for _, body in flow.app.posts[2:]]
    assert (
        a != b
        and len(flow.app.sessions[a]["history"])
        == len(flow.app.sessions[b]["history"])
        == 2
    )
    assert flow.app.handoffs[2][1][0].content == flow.receipt.binding.turns[0].message
    assert flow.app.handoffs[3][1][0].content == flow.receipt.binding.turns[1].message
    assert tuple(t.prior_slots for t in flow.material.packet.turns) == (
        (),
        ("A1",),
        ("A1", "B1"),
        ("A1", "B1", "A2"),
    )
    signed = review_bytes(flow)
    result = submit(flow, signed)
    retain(flow, result, signed)
    observed = assess_review(flow)
    assert observed.assessment.status == observed.human_quality.status == "PASS"
    assert (
        observed.details.checkpoint_status == "matches"
        and observed.details.reviewer_signature == "verified"
    )
    assert observed.details.recorded_assessment_provenance == "anchored-journal-checks"
    assert flow.cleaned == [True] and flow.provider.stopped
    assert (
        not observed.assurance.authorises_live_execution
        and not observed.assurance.human_authorship_established
    )
    assert b"PRIVATE_PROVIDER_REASONING" not in flow.raw + packet.serialize_packet(
        flow.material.packet
    )
    (tmp_path / "measurement.json").write_text(
        json.dumps({**measurement(flow), "seconds": monotonic() - started}, indent=2)
    )


def test_valid_cross_workflow_substitutions(tmp_path, keys):
    """P0-02: validate both contexts before substituting one relationship."""
    a = complete(tmp_path / "a", keys)
    b = complete(tmp_path / "b", keys, secondary=True)
    before_a, before_b = snapshot(a.root), snapshot(b.root)
    with pytest.raises(envelope.EnvelopeError, match="^reference_mismatch$"):
        envelope.verify_envelope(b.raw, expected=a.reference)
    with pytest.raises(envelope.EnvelopeError, match="^binding_mismatch$"):
        envelope.verify_against_sources(
            a.raw,
            expected=a.reference,
            **{
                **{k: v for k, v in envelope_arguments(a).items() if k != "run_id"},
                "store": b.store,
            },
        )
    with pytest.raises(review.ReviewError, match="^source_mismatch$"):
        packet.acquire_packet(a.raw, expected=a.reference, registry=b.registry)
    with pytest.raises(review.ReviewError, match="^binding_mismatch$"):
        register.register_review(
            *review_bytes(b),
            **registration_arguments(a),
            policy=lambda: review_observation(a),
            clock=lambda: T,
        )
    assert snapshot(a.root) == before_a and snapshot(b.root) == before_b
    assert (
        assess_review(a).assessment.status
        == assess_review(b).assessment.status
        == "PASS"
    )


def test_duplicate_and_store_local_scope(tmp_path, keys):
    """P0-03/04: one use per configured store, never global uniqueness."""
    flow = consume(prepare(tmp_path / "a", keys))
    before = snapshot(flow.configuration.store_path)
    with pytest.raises(authority.AuthorityError, match="^authorisation_consumed$"):
        authority.consume_approval(
            *flow.signed,
            expected=flow.proposal,
            store=flow.store,
            policy=lambda: approval_observation(flow),
            clock=lambda: T,
        )
    assert snapshot(flow.configuration.store_path) == before
    config = flow.configuration.model_copy(
        update={
            "store_path": str(tmp_path / "other-store"),
            "store_id": "synthetic-store-" + uuid4().hex,
        }
    )
    other = authority.initialize_store(config)
    second = authority.consume_approval(
        *flow.signed,
        expected=flow.proposal,
        store=other,
        policy=lambda: approval_observation(flow),
        clock=lambda: T,
    )
    assert (
        second.store_id != flow.consumed.store_id
        and second.intended_run_id != flow.consumed.intended_run_id
        and second.record_id != flow.consumed.record_id
    )
    with pytest.raises(authority.AuthorityError, match="^authorisation_consumed$"):
        authority.consume_approval(
            *flow.signed,
            expected=flow.proposal,
            store=other,
            policy=lambda: approval_observation(flow),
            clock=lambda: T,
        )
    assert (
        authority.inspect_consumption(other, flow.proposal.authorisation_id).record
        == second
    )
    assert snapshot(flow.configuration.store_path) == before


def test_consumed_without_execution(tmp_path, keys):
    """P0-05: successful consumption does not establish execution."""
    flow = consume(prepare(tmp_path / "a", keys))
    before = snapshot(flow.root)
    assert not (flow.root / "journal").exists()
    assert (
        authority.inspect_consumption(flow.store, flow.proposal.authorisation_id).status
        == "consumed"
    )
    assert snapshot(flow.root) == before


def test_unknown_attempt_denies_review(tmp_path, keys):
    """P0-06: no invented turn outcome or replacement after uncertainty."""
    flow = consume(prepare(tmp_path / "a", keys))
    execute(flow, timeout=True)
    anchor(flow)
    assert flow.report["driver_error"] == "application_failed"
    assert (
        flow.report["status"] == "operationally_uncertain"
        and not flow.report["completion_certified"]
    )
    assert (
        flow.report["accounting"]["unknown_attempts"] == 1
        and flow.report["accounting"]["estimated_total_usd"] is None
    )
    assert (
        len(flow.forwarded) == 1
        and flow.report["instrumentation_stop"] == "transport_ambiguous"
    )
    before = snapshot(flow.root)
    with pytest.raises(review.ReviewError, match="^source_ineligible$"):
        packet.acquire_packet(flow.raw, expected=flow.reference, registry=flow.registry)
    assert snapshot(flow.root) == before


def test_mechanical_fail_survives_human_pass(tmp_path, keys):
    """P0-07."""
    flow = complete(tmp_path / "a", keys, fail=True)
    result = assess_review(flow)
    assert flow.report["status"] == "completed" and flow.report["shopper_posts"] == 4
    assert (
        result.inputs.operational.status == "PASS"
        and result.inputs.mechanical.status == "FAIL"
    )
    assert result.human_quality.status == "PASS" and result.assessment.status == "FAIL"
    (tmp_path / "measurement.json").write_text(json.dumps(measurement(flow), indent=2))


def test_invalid_review_cannot_poison_and_stale_conflict(tmp_path, keys):
    """P0-08/09."""
    flow = complete(tmp_path / "a", keys)
    old = flow.checkpoint
    before = snapshot(flow.register.configuration.path)
    raw, _ = review_bytes(flow)
    wrong = keys.sign(raw, unknown=True, namespace=review.NAMESPACE)
    with pytest.raises(review.ReviewError, match="^signature_not_verified$"):
        submit(flow, (raw, wrong))
    assert snapshot(flow.register.configuration.path) == before
    assert assess_review(flow).assessment.status == "PASS"
    result = submit(flow, review_bytes(flow, failure=("A1", "R3")))
    assert result.status == "CONFLICT_RECORDED" and flow.checkpoint == old
    observed = assess_review(flow)
    assert (
        observed.assessment.status == "ERROR"
        and observed.details.conflict_authentication == "authenticated"
    )
    assert {"review_conflict", "checkpoint_stale"} <= set(
        observed.inputs.verification.issues
    )
    assert len(observed.details.authenticated_reviews) == 2
    (tmp_path / "measurement.json").write_text(
        json.dumps(
            {
                "mechanism": "authenticated conflicting review register",
                "events": 2,
                "register_bytes": (
                    Path(flow.register.configuration.path) / register.DATABASE
                )
                .stat()
                .st_size,
                "signed_payload_bytes": len(raw),
            },
            indent=2,
        )
    )


def test_direct_incomplete_and_changed_journal(tmp_path, keys):
    """P0-10/11: direct fixture is not application execution."""
    flow = consume(prepare(tmp_path / "incomplete", keys))
    flow.registry = journal.initialize_registry(flow.root / "journal")
    with journal.CanaryJournal(
        flow.registry,
        flow.consumed.intended_run_id,
        flow.proposal.authorisation_id,
        source_receipt=flow.receipt,
    ):
        pass
    anchor(flow)
    assert flow.envelope.execution.journal_status == "incomplete"
    with pytest.raises(review.ReviewError, match="^source_ineligible$"):
        packet.acquire_packet(flow.raw, expected=flow.reference, registry=flow.registry)
    full = complete(tmp_path / "full", keys)
    ledger = (
        Path(full.registry.path) / "runs" / full.consumed.intended_run_id / "records"
    )
    max(ledger.iterdir()).unlink()
    before = snapshot(full.root)
    assert envelope.verify_envelope(full.raw, expected=full.reference)
    with pytest.raises(envelope.EnvelopeError, match="^source_mismatch$"):
        envelope.verify_against_sources(
            full.raw,
            expected=full.reference,
            **{k: v for k, v in envelope_arguments(full).items() if k != "run_id"},
        )
    with pytest.raises(review.ReviewError, match="^source_mismatch$"):
        packet.acquire_packet(full.raw, expected=full.reference, registry=full.registry)
    assert snapshot(full.root) == before


@pytest.mark.parametrize(
    "variant",
    [
        "headroom",
        "reserve",
        "incomplete",
        "stale",
        "rollover",
        "project",
        "import",
        "external",
    ],
)
def test_spending_outcomes_remain_detached(tmp_path, keys, spending_case, variant):
    """P0-19..23/24(project)/25/26; no authority or execution side effects."""
    flow = prepare(tmp_path / "a", keys)
    case = spending_inputs(spending_case, flow)
    now = T
    if variant == "headroom":
        case["bundle"]["control"]["payload"]["threshold"] = spending_tests.amount("6.5")
    elif variant == "reserve":
        spending_tests.unavailable(case, 2)
        spending_tests.rule(case, 2, value="2")
    elif variant == "incomplete":
        case["bundle"]["costs"]["payload"]["reporting_completeness"] = (
            "known_incomplete"
        )
    elif variant == "stale":
        case["bundle"]["control"]["header"]["stamp"].update(
            collection_started_at=text_time(T - timedelta(seconds=61)),
            collection_ended_at=text_time(T - timedelta(seconds=61)),
        )
    elif variant == "rollover":
        now = datetime(2026, 12, 1, tzinfo=UTC)
    elif variant == "project":
        case["bundle"]["control"]["payload"]["scope"]["project_id"] = (
            "proj_synthetic_wrong"
        )
    elif variant == "external":
        case = json.loads(
            json.dumps(case)
            .replace(flow.proposal.project_id, "proj_intended_external")
            .replace(flow.proposal.organization_id, "org_intended_external")
        )
        case["assignment"]["scope"]["environment"] = case["policy"]["scope"][
            "environment"
        ] = "external_claim"
        case["assignment"]["observation_profile"] = case["bundle"][
            "observation_profile"
        ] = "spending-manual-claims-v1"
        case["bundle"]["declared_provenance"] = "manual_declaration"
    before = snapshot(flow.root)
    result = assess_spending(case, now=now)
    if variant == "headroom":
        assert (
            result.headroom_usd == "0.5"
            and result.diagnostic_outcome == "NONCONFORMANT"
        )
        assert result.conditional_headroom.issues == ("headroom_insufficient",)
    elif variant == "reserve":
        assert (
            result.headroom_state == "HYPOTHETICAL"
            and result.hypothetical_headroom_usd == "3"
            and result.headroom_usd is None
        )
        assert (
            result.conditional_headroom.issues == ("hypothetical_only",)
            and result.diagnostic_outcome == "INDETERMINATE"
        )
    elif variant == "incomplete":
        assert (
            "known_incomplete_reporting" in result.issues
            and result.headroom_usd is None
        )
        assert (
            result.known_cost_subtotal_usd == "1"
            and result.diagnostic_outcome == "INDETERMINATE"
        )
    elif variant == "stale":
        assert (
            result.control_freshness.issues == ("observation_stale",)
            and result.headroom_usd is None
        )
    elif variant == "rollover":
        assert {"outside_validity", "period_or_horizon_expired"} <= set(
            result.validity.issues
        ) and result.headroom_usd is None
    elif variant == "project":
        assert (
            result.diagnostic_outcome == "INVALID_EVIDENCE"
            and "scope_mismatch" in result.input_reliability.issues
        )
    elif variant == "import":
        imported = result.model_dump(mode="json")
        imported["known_cost_subtotal_usd"] = imported["supplied_report_total_usd"] = (
            "0"
        )
        imported["calculation_inputs"]["reported_cost_usd"] = "0"
        imported["headroom_usd"] = imported["hypothetical_headroom_usd"] = "5"
        candidate = spending.parse_assessment(canonical_json(imported).encode())
        recomputed = assess_spending(case)
        assert (
            candidate.headroom_usd == "5"
            and recomputed.headroom_usd == "4"
            and candidate != recomputed
        )
        assert not candidate.assurance.assessment_origin_authenticated
    else:
        assert result.diagnostic_outcome == "CONDITIONALLY_CONFORMANT"
    assert snapshot(flow.root) == before and not (flow.root / "authority").exists()


@pytest.mark.parametrize("field", ["assignment", "policy", "reference"])
def test_spending_valid_context_substitution(tmp_path, keys, spending_case, field):
    """P0-24: both independent contexts first succeed."""
    a = prepare(tmp_path / "a", keys)
    b = prepare(tmp_path / "b", keys, secondary=True)
    ca, cb = spending_inputs(spending_case, a), spending_inputs(spending_case, b)
    assert (
        assess_spending(ca).diagnostic_outcome
        == assess_spending(cb).diagnostic_outcome
        == "CONDITIONALLY_CONFORMANT"
    )
    aa, pa, ba, ra = spending_tests.prepared(ca)
    ab, pb, _, rb = spending_tests.prepared(cb)
    args = {"assignment": aa, "policy": pa, "expected": ra, "now": T}
    args[field if field != "reference" else "expected"] = {
        "assignment": ab,
        "policy": pb,
        "reference": rb,
    }[field]
    result = spending.assess_spending(spending.serialize_bundle(ba), **args)
    assert result.diagnostic_outcome == "INVALID_EVIDENCE"
    assert (
        "reference_mismatch" if field == "reference" else "binding_mismatch"
    ) in result.issues
    assert assess_spending(ca).diagnostic_outcome == "CONDITIONALLY_CONFORMANT"


@pytest.mark.parametrize("fault", ["namespace", "expired", "revoked", "policy"])
def test_approval_denials_before_journal(tmp_path, keys, fault):
    """P1-01."""
    flow = prepare(tmp_path / "a", keys)
    flow.store = authority.initialize_store(flow.configuration)
    signed = flow.signed
    now = T
    policy = flow.policy
    if fault == "namespace":
        signed = (signed[0], keys.sign(signed[0], namespace=review.NAMESPACE))
    elif fault == "expired":
        now = T + timedelta(minutes=30)
    elif fault == "revoked":
        policy = policy.model_copy(update={"revoked_public_keys": (policy.public_key,)})
    else:
        policy = policy.model_copy(update={"policy_id": "synthetic-policy-wrong"})
    expected = {
        "namespace": "signature_not_verified",
        "expired": "approval_expired",
        "revoked": "signer_revoked",
        "policy": "policy_binding_mismatch",
    }[fault]
    before = snapshot(flow.configuration.store_path)
    with pytest.raises(
        (approval.ApprovalError, authority.AuthorityError), match="^" + expected + "$"
    ):
        authority.consume_approval(
            *signed,
            expected=flow.proposal,
            store=flow.store,
            policy=lambda: authority.PolicyObservation(
                schema_id="canary-synthetic-policy-observation-v1",
                policy=policy,
                observed_at=text_time(now),
                expires_at=text_time(now + timedelta(seconds=30)),
            ),
            clock=lambda: now,
        )
    assert (
        snapshot(flow.configuration.store_path) == before
        and not (flow.root / "journal").exists()
    )


@pytest.mark.parametrize("exposure,quality", [("not_seen", "FAIL"), ("seen", "SKIP")])
def test_incomplete_and_disqualified_review(tmp_path, keys, exposure, quality):
    """P1-04."""
    flow = complete(tmp_path / "a", keys, register_now=False)
    signed = review_bytes(
        flow, failure=("A1", "R3"), unknown=("B2", "R2"), exposure=exposure
    )
    result = submit(flow, signed)
    retain(flow, result, signed)
    observed = assess_review(flow)
    assert (
        observed.human_quality.status == quality
        and observed.inputs.review.whole_run_verdict is None
    )
    assert observed.human_quality.issues == (
        ("human_criterion_failed",)
        if quality == "FAIL"
        else ("review_quality_disqualified",)
    )


@pytest.mark.parametrize("fault", ["revoked", "register", "source"])
def test_current_reliance_errors_preserve_findings(tmp_path, keys, fault):
    """P1-05."""
    flow = complete(tmp_path / "a", keys)
    if fault == "register":
        (Path(flow.register.configuration.path) / register.DATABASE).rename(
            flow.root / "unavailable-register"
        )
    elif fault == "source":
        ledger = (
            Path(flow.registry.path)
            / "runs"
            / flow.consumed.intended_run_id
            / "records"
        )
        max(ledger.iterdir()).unlink()
    before = snapshot(flow.root)
    result = assess_review(flow, revoked=fault == "revoked")
    assert result.assessment.status == "ERROR"
    assert {
        "revoked": "signer_revoked",
        "register": "register_corrupt",
        "source": "source_mismatch",
    }[fault] in result.inputs.verification.issues
    if fault != "register":
        assert result.details.reviewer_signature == "verified"
    assert snapshot(flow.root) == before


def test_high_volume_actual_driver_and_bounds(tmp_path, keys):
    """P1-06: actual driver completion, not a manufactured journal seal."""
    started = monotonic()
    flow = complete(tmp_path / "a", keys, calls=6, attempts=3)
    assert (
        flow.report["status"] == "completed"
        and flow.report["accounting"]["logical_calls"] == 24
    )
    assert flow.report["accounting"]["provider_attempts"] == len(flow.forwarded) == 72
    assert not flow.report["accounting"]["unknown_attempts"]
    assert len(flow.raw) <= envelope.MAX_ENVELOPE_BYTES
    assert len(packet.serialize_packet(flow.material.packet)) <= packet.MAX_PACKET_BYTES
    assert len(flow.material.presentation) <= packet.MAX_PRESENTATION_BYTES
    (tmp_path / "measurement.json").write_text(
        json.dumps({**measurement(flow), "seconds": monotonic() - started}, indent=2)
    )


def test_pending_review_and_unretained_candidate(tmp_path, keys):
    """P0-15/17: explicit operator custody, not automatic candidate adoption."""
    flow = complete(tmp_path / "a", keys, register_now=False)
    pending = assess_review(flow)
    assert (
        pending.inputs.human_state == "PENDING" and pending.assessment.status == "SKIP"
    )
    assert pending.human_quality.issues == ("human_review_pending",)
    assert pending.inputs.verification.status == "PASS"
    retained = flow.checkpoint.model_dump_json()
    result = submit(flow)
    assert result.status == "RECORDED" and flow.checkpoint.model_dump_json() == retained
    current = assess_review(flow)
    assert (
        current.assessment.status == "ERROR"
        and current.details.checkpoint_status == "stale"
    )
    assert "checkpoint_stale" in current.inputs.verification.issues
    assert current.details.reviewer_signature == "verified"


@pytest.mark.parametrize("shape", ["revisions", "prose", "spending"])
def test_representative_resource_measurements(tmp_path, keys, spending_case, shape):
    """P1-06: measured direct fixtures remain distinct from driver execution."""
    started = monotonic()
    flow = consume(prepare(tmp_path / "a", keys))
    if shape == "spending":
        case = spending_inputs(spending_case, flow)
        big, now = spending_tests.representative_case(case)
        assignment, policy, bundle, reference = spending_tests.prepared(big)
        result = spending.assess_spending(
            spending.serialize_bundle(bundle),
            assignment=assignment,
            policy=policy,
            expected=reference,
            now=now,
        )
        rich = assess_spending(spending_tests.rich_issue_case(case))
        assert (
            result.diagnostic_outcome == "NONCONFORMANT"
            and rich.diagnostic_outcome == "INVALID_EVIDENCE"
        )
        sizes = {}
        for name, value, serialise, limit in (
            (
                "assignment",
                assignment,
                spending.serialize_assignment,
                spending.MAX_ASSIGNMENT_BYTES,
            ),
            ("policy", policy, spending.serialize_policy, spending.MAX_POLICY_BYTES),
            ("bundle", bundle, spending.serialize_bundle, spending.MAX_BUNDLE_BYTES),
            (
                "reference",
                reference,
                spending.serialize_expected_reference,
                spending.MAX_REFERENCE_BYTES,
            ),
            (
                "assessment",
                result,
                spending.serialize_assessment,
                spending.MAX_ASSESSMENT_BYTES,
            ),
            (
                "issue_rich_assessment",
                rich,
                spending.serialize_assessment,
                spending.MAX_ASSESSMENT_BYTES,
            ),
        ):
            sizes[name] = len(serialise(value))
            assert sizes[name] <= limit
        observed = {
            "mechanism": "detached prospective spending",
            "sizes": sizes,
            "buckets": len(bundle.costs.payload.buckets),
            "alerts": len(bundle.alerts.payload.thresholds),
        }
    else:
        flow.registry = journal.initialize_registry(flow.root / "journal")
        writer = journal.CanaryJournal(
            flow.registry,
            flow.consumed.intended_run_id,
            flow.proposal.authorisation_id,
            source_receipt=flow.receipt,
        )
        try:
            for slot in ORDER:
                assert writer.record_decision(journal_tests.ready()).next_slot == slot
                writer.reserve_turn(slot)
                writer.reserve_call(1)
                writer.record_dispatch(1, 1)
                raw = journal_tests.envelope()
                raw["id"] = "resp_" + slot
                writer.record_provider_result(1, 1, raw, http_status=200)
                writer.complete_call(1)
                public = journal_tests.selected(slot)
                if shape == "prose":
                    public["chat"]["message"] = "Synthetic public prose " + "x" * 20_000
                writer.record_chat(public["chat"])
                writer.record_trace(
                    public["trace"], reread=copy.deepcopy(public["trace"])
                )
                for _ in range(3 if shape == "revisions" else 1):
                    writer.assess_turn()
                writer.complete_turn()
            assert writer.record_decision(journal_tests.ready()).action == "COMPLETE"
            writer.record_shutdown(
                worker_stopped=True, sdk_closed=True, no_inflight_provider=True
            )
            writer.seal()
        finally:
            writer.close()
        flow.report = journal.inspect_run(flow.registry, flow.consumed.intended_run_id)
        anchor(flow)
        assign(flow)
        initialise_review(flow)
        observed = {
            "mechanism": "direct supplied journal fixture; no application or driver execution",
            **measurement(flow),
        }
        assert (
            observed["packet_bytes"] <= packet.MAX_PACKET_BYTES
            and observed["presentation_bytes"] <= packet.MAX_PRESENTATION_BYTES
        )
    (tmp_path / "measurement.json").write_text(
        json.dumps({**observed, "seconds": monotonic() - started}, indent=2)
    )
