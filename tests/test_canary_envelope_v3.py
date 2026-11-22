"""Offline synthetic evidence tests. No application, provider or network service."""

from __future__ import annotations

import copy
import errno
import fcntl
import json
import multiprocessing
import os
import signal
import stat
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import test_canary_approval_v3 as approved_tests
import test_canary_journal_v3 as journal_tests
from pydantic import ValidationError

from harness.canary import authority_v3 as authority
from harness.canary import envelope_v3 as envelope
from harness.canary import journal_v3 as journal
from harness.canary.evidence_v3 import AttemptGuards, DispatchTelemetry, ResultTelemetry
from harness.canary.selection_v3 import ORDER
from harness.core.fingerprints import canonical_json, fingerprint

proposal = approved_tests.proposal
keys = approved_tests.keys
manifest = approved_tests.manifest
policy = approved_tests.policy
signed = approved_tests.signed


def source_projection(receipt):
    binding = receipt.binding
    values = {
        name: getattr(receipt, name)
        for name in (
            "schema_id",
            "provenance",
            "execution_profile",
            "harness",
            "application",
            "harness_lock_sha256",
            "application_lock_sha256",
            "runtime",
        )
    }
    values.update(
        {
            name: getattr(binding, name)
            for name in (
                "roster_fingerprint",
                "definition_fingerprint",
                "acceptance_policy",
                "acceptance_fingerprint",
                "execution_policy",
                "execution_fingerprint",
                "v2_1_fingerprint",
                "application_revision",
                "fixture_hashes",
                "inference",
                "limits",
            )
        }
    )
    return envelope.RecordedSource(
        **values,
        receipt_sha256=fingerprint(receipt.model_dump(mode="json")),
        definition_identifier=binding.identifier,
        definition_binding_sha256=fingerprint(binding.model_dump(mode="json")),
        definition_storage_schema=binding.storage_schema,
    )


@pytest.fixture
def candidate(proposal):
    """Intentionally caller-constructed data; never proof of persisted evidence."""
    receipt = authority.ConsumptionReceipt(
        schema_id="canary-synthetic-consumption-v1",
        store_id="synthetic-store-" + "1" * 32,
        authorisation_id=proposal.authorisation_id,
        payload_sha256="1" * 64,
        signature_sha256="2" * 64,
        trust_policy_sha256="3" * 64,
        trust_policy_identity_sha256="4" * 64,
        source_receipt_sha256=proposal.source_receipt_sha256,
        proposal_sha256=fingerprint(proposal.model_dump(mode="json")),
        execution_audience=proposal.execution_audience,
        intended_run_id="synthetic-run-" + "1" * 32,
        record_id="synthetic-consumption-" + "1" * 32,
        consumed_at="2026-11-22T12:00:00Z",
        verification_sha256="5" * 64,
        signer_principal=approved_tests.PRINCIPAL,
        signer_public_key_sha256="6" * 64,
    )
    return envelope.EvidenceEnvelope(
        authority=envelope.AuthorityEvidence(
            store_binding_sha256="7" * 64, receipt=receipt
        ),
        journal=envelope.JournalEvidence(
            registry_id="1" * 32,
            registry_binding_sha256="8" * 64,
            run_id=receipt.intended_run_id,
            approval_id=receipt.authorisation_id,
            validated_records=1,
            history_commitment_sha256="9" * 64,
            evidence_sha256="a" * 64,
        ),
        source=source_projection(proposal.source_receipt),
        execution=envelope.RecordedExecution(
            journal_status="incomplete",
            completion_seal_present=False,
            completion_acknowledged=False,
            journal_completion_certified=False,
            accounting_reconciled=True,
            execution_action=None,
            safe_shutdown_observation=None,
            mechanical_assessment_status=None,
            operational_assessment_status=None,
            overall_assessment_status=None,
        ),
        accounting=envelope.RecordedAccounting(
            logical_calls=0,
            provider_attempts=0,
            unknown_attempts=0,
            incomplete_calls=0,
            retryable_http_failures=0,
            operational_errors=0,
            estimated_subtotal_usd="0",
            estimated_total_usd="0",
            billing_verified=False,
        ),
    )


def deny(code, call):
    with pytest.raises(envelope.EnvelopeError, match="^" + code + "$") as caught:
        call()
    assert caught.value.__suppress_context__ or caught.value.__context__ is None


class TestSchema:
    def test_exact_canonical_roundtrip_and_reviewed_commitment(self, candidate):
        raw = envelope.serialize_envelope(candidate)
        assert raw == canonical_json(candidate.model_dump(mode="json")).encode()
        assert not raw.endswith(b"\n")
        assert envelope.parse_envelope(raw) == candidate
        expected = sha256(
            canonical_json(
                {
                    "domain": "canary-detached-envelope-v1",
                    "canonicalization": "replay-canonical-json-v1",
                    "envelope": candidate.model_dump(mode="json"),
                }
            ).encode()
        ).hexdigest()
        assert envelope.envelope_commitment_sha256(candidate) == expected
        assert sha256(raw).hexdigest() != expected

    @pytest.mark.parametrize("field", list(envelope.EvidenceEnvelope.model_fields))
    def test_every_field_including_constants_is_required(self, candidate, field):
        value = candidate.model_dump(mode="json")
        del value[field]
        deny(
            "invalid_envelope",
            lambda: envelope.parse_envelope(canonical_json(value).encode()),
        )

    @pytest.mark.parametrize(
        "field", ["schema_id", "canonicalization", "commitment_profile"]
    )
    def test_versions_are_exact(self, candidate, field):
        value = candidate.model_dump(mode="json")
        value[field] = "unreviewed"
        deny(
            "unsupported_version",
            lambda: envelope.parse_envelope(canonical_json(value).encode()),
        )

    @pytest.mark.parametrize(
        "change", ["space", "newline", "order", "duplicate", "nested_duplicate"]
    )
    def test_noncanonical_or_duplicate_bytes_are_rejected(self, candidate, change):
        raw = envelope.serialize_envelope(candidate)
        if change == "space":
            raw = b" " + raw
        elif change == "newline":
            raw += b"\n"
        elif change == "order":
            raw = json.dumps(dict(reversed(list(json.loads(raw).items())))).encode()
        elif change == "duplicate":
            raw = b'{"schema_id":"duplicate",' + raw[1:]
        else:
            raw = raw.replace(
                b'"human_review":"PENDING"',
                b'"human_review":"PENDING","human_review":"PENDING"',
            )
        deny(
            "invalid_envelope" if "duplicate" in change else "noncanonical_envelope",
            lambda: envelope.parse_envelope(raw),
        )

    @pytest.mark.parametrize(
        "raw", [b"", b"null", b"[]", b"{", b"\xff", b'{"x":NaN}', b'{"x":Infinity}']
    )
    def test_malformed_input_is_private(self, raw):
        deny("invalid_envelope", lambda: envelope.parse_envelope(raw))

    @pytest.mark.parametrize(
        "path,value",
        [
            (("accounting", "logical_calls"), True),
            (("accounting", "provider_attempts"), "0"),
            (("accounting", "unknown_attempts"), -1),
            (("assurance", "authorises_live_execution"), True),
            (("assurance", "fresh_approval_signature_verified"), True),
            (("authority", "receipt", "source_authorised"), True),
            (("execution", "journal_completion_certified"), True),
            (("execution", "completion_acknowledged"), True),
            (("journal", "run_id"), "synthetic-run-" + "2" * 32),
            (("source", "receipt_sha256"), "0" * 64),
        ],
    )
    def test_coercions_and_forged_claims_fail(self, candidate, path, value):
        document = candidate.model_dump(mode="json")
        parent = document
        for key in path[:-1]:
            parent = parent[key]
        parent[path[-1]] = value
        deny(
            "invalid_envelope",
            lambda: envelope.parse_envelope(canonical_json(document).encode()),
        )

    @pytest.mark.parametrize("field", list(envelope.Assurance.model_fields))
    def test_all_assurance_constants_are_required(self, candidate, field):
        document = candidate.model_dump(mode="json")
        del document["assurance"][field]
        deny(
            "invalid_envelope",
            lambda: envelope.parse_envelope(canonical_json(document).encode()),
        )

    def test_nested_models_and_validation_bypassing_copies_are_revalidated(
        self, candidate
    ):
        for instance in (
            candidate,
            candidate.assurance,
            candidate.source.inference,
            candidate.authority.receipt,
        ):
            with pytest.raises(ValidationError):
                instance.private = "PRIVATE_SENTINEL"
        bad = candidate.model_copy(update={"private": "PRIVATE_SENTINEL"})
        deny("invalid_envelope", lambda: envelope.serialize_envelope(bad))
        bad = candidate.model_copy(
            update={
                "assurance": candidate.assurance.model_copy(
                    update={"source_authorised": True}
                )
            }
        )
        deny("invalid_envelope", lambda: envelope.serialize_envelope(bad))
        assert "PRIVATE" not in str(envelope.EnvelopeError("PRIVATE_SENTINEL"))

    @pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", " 0", "0 ", ""])
    def test_invalid_costs_are_not_zero(self, candidate, value):
        document = candidate.model_dump(mode="json")
        document["accounting"]["estimated_subtotal_usd"] = value
        document["accounting"]["estimated_total_usd"] = value
        deny(
            "invalid_envelope",
            lambda: envelope.parse_envelope(canonical_json(document).encode()),
        )

    def test_unknown_liability_remains_null_and_decimal_spelling_is_retained(
        self, candidate
    ):
        document = candidate.model_dump(mode="json")
        document["accounting"].update(
            unknown_attempts=1, estimated_subtotal_usd="0.000", estimated_total_usd=None
        )
        value = envelope.parse_envelope(canonical_json(document).encode())
        assert value.accounting.estimated_total_usd is None
        assert value.accounting.estimated_subtotal_usd == "0.000"

    def test_size_depth_and_value_limits_reject_without_truncation(self, candidate):
        deny(
            "resource_limit",
            lambda: envelope.parse_envelope(b" " * (envelope.MAX_ENVELOPE_BYTES + 1)),
        )
        deny(
            "resource_limit",
            lambda: envelope.parse_envelope(b"[" * 17 + b"0" + b"]" * 17),
        )
        document = candidate.model_dump(mode="json")
        document["private"] = [0] * envelope.MAX_ENVELOPE_VALUES
        deny(
            "resource_limit",
            lambda: envelope.parse_envelope(canonical_json(document).encode()),
        )
        raw = b'{"literal":"' + b"[" * 20 + b'"}'
        deny("invalid_envelope", lambda: envelope.parse_envelope(raw))

    def test_completed_execution_and_quality_are_independent(self, candidate):
        document = candidate.model_dump(mode="json")
        document["execution"].update(
            journal_status="completed",
            completion_seal_present=True,
            completion_acknowledged=True,
            journal_completion_certified=True,
            execution_action="COMPLETE",
            safe_shutdown_observation={
                "worker_stopped": True,
                "sdk_closed": True,
                "no_inflight_provider": True,
            },
            mechanical_assessment_status="FAIL",
            operational_assessment_status="PASS",
            overall_assessment_status="FAIL",
        )
        value = envelope.parse_envelope(canonical_json(document).encode())
        assert value.execution.journal_completion_certified
        assert value.execution.mechanical_assessment_status == "FAIL"
        assert value.assurance.invocation_status == "not-established"
        assert value.assurance.human_review == "PENDING"


def build_linked(
    tmp_path,
    proposal,
    signed,
    policy,
    *,
    mode="incomplete",
    calls=1,
    attempts=1,
    profiled=False,
    revisions=1,
    prose_size=0,
    fail=False,
):
    config = authority.TrustedStoreConfiguration(
        schema_id="canary-synthetic-authority-config-v1",
        store_path=str((tmp_path / "authority").resolve()),
        store_id="synthetic-store-" + uuid4().hex,
        execution_audience=proposal.execution_audience,
        trust_policy_identity_sha256=authority.policy_identity(policy),
        host_id="synthetic-slice6c-host",
        host_scope="synthetic-single-host-local",
    )
    store = authority.initialize_store(config)
    now = approved_tests.NOW
    consumed = authority.consume_approval(
        *signed,
        expected=proposal,
        store=store,
        clock=lambda: now,
        policy=lambda: authority.PolicyObservation(
            schema_id="canary-synthetic-policy-observation-v1",
            policy=policy,
            observed_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            expires_at=(now + timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        ),
    )
    registry = journal.initialize_registry(tmp_path / "journal")
    writer = journal.CanaryJournal(
        registry,
        consumed.intended_run_id,
        consumed.authorisation_id,
        source_receipt=proposal.source_receipt,
    )
    binding = None
    if profiled:
        binding = writer.bind_provider(
            proposal.source_receipt.binding,
            project_id=proposal.project_id,
            organization_id=proposal.organization_id,
        )
    if mode == "uncertain":
        writer.record_decision(journal_tests.ready())
        writer.reserve_turn("A1")
        writer.reserve_call(1)
        writer.record_dispatch(1, 1)
    elif mode in {"completed", "unacknowledged"}:
        for slot in ORDER:
            assert writer.record_decision(journal_tests.ready()).next_slot == slot
            writer.reserve_turn(slot)
            previous = None
            for number in range(1, calls + 1):
                reservation = None
                if binding:
                    reservation = writer.reserve_provider_call(
                        binding, slot=slot, previous_response_id=previous
                    )
                else:
                    writer.reserve_call(number)
                for attempt in range(1, attempts + 1):
                    final = attempt == attempts
                    response = (
                        journal_tests.envelope()
                        if final
                        else journal_tests.retry_failure(known_zero_usage=True)
                    )
                    response["id"] = "resp_" + slot + "_" + str(number)
                    status = 200 if final else 500
                    if binding:
                        now_dispatch = datetime.now(UTC).isoformat()
                        writer.dispatch_provider_attempt(
                            binding,
                            reservation,
                            attempt,
                            telemetry=DispatchTelemetry(
                                sdk_retry_count=attempt - 1,
                                started_at=now_dispatch,
                                guards=AttemptGuards(
                                    checked_at=now_dispatch,
                                    **{
                                        name: True
                                        for name, field in AttemptGuards.model_fields.items()
                                        if field.annotation is bool
                                    },
                                ),
                            ),
                        )
                        writer.observe_provider_attempt(
                            binding,
                            reservation,
                            attempt,
                            response,
                            http_status=status,
                            request_id="req_synthetic",
                            telemetry=ResultTelemetry(
                                duration_ms=1.0,
                                read_complete=True,
                                json_state="valid",
                                observed_http_status=status,
                            ),
                        )
                    else:
                        writer.record_dispatch(number, attempt)
                        writer.record_provider_result(
                            number, attempt, response, http_status=status
                        )
                if binding:
                    writer.finish_provider_call(
                        binding,
                        reservation,
                        outcome="returned",
                        response_id=response["id"],
                    )
                    previous = response["id"]
                else:
                    writer.complete_call(number)
            public = journal_tests.selected(slot)
            if prose_size:
                public["chat"]["message"] = "SYNTHETIC_PUBLIC_PROSE_" + "x" * prose_size
            if fail and slot == "A1":
                public["trace"]["resolved_constraints"]["maximum_price"] = "1.00"
            writer.record_chat(public["chat"])
            writer.record_trace(public["trace"], reread=copy.deepcopy(public["trace"]))
            for _ in range(revisions):
                writer.assess_turn()
            writer.complete_turn()
        assert writer.record_decision(journal_tests.ready()).action == "COMPLETE"
        writer.record_shutdown(
            worker_stopped=True, sdk_closed=True, no_inflight_provider=True
        )
        if mode == "completed":
            writer.seal()
    writer.close()
    return SimpleNamespace(
        store=store,
        registry=registry,
        proposal=proposal,
        signed=signed,
        consumed=consumed,
        writer=writer,
        records=Path(registry.path) / "runs" / consumed.intended_run_id / "records",
    )


@pytest.fixture
def linked(tmp_path, proposal, signed, policy):
    return build_linked(tmp_path, proposal, signed, policy)


def assemble(linked, **changes):
    return envelope.assemble_envelope(
        **{
            "payload": linked.signed[0],
            "signature": linked.signed[1],
            "expected_proposal": linked.proposal,
            "store": linked.store,
            "registry": linked.registry,
            "run_id": linked.consumed.intended_run_id,
            **changes,
        }
    )


def source_bytes(linked):
    return (
        journal_tests.tree_bytes(Path(linked.store.configuration.store_path)),
        journal_tests.tree_bytes(Path(linked.registry.path)),
    )


class TestAssembly:
    def test_actual_persisted_linkage_exact_commitment_and_observation_order(
        self, linked, monkeypatch
    ):
        before = source_bytes(linked)
        order = []
        original_a = authority.inspect_consumption
        original_j = journal.inspect_run

        def inspect_authority(*args, **kwargs):
            order.append("A")
            return original_a(*args, **kwargs)

        def inspect_journal(*args, **kwargs):
            order.append("J")
            return original_j(*args, **kwargs)

        monkeypatch.setattr(authority, "inspect_consumption", inspect_authority)
        monkeypatch.setattr(journal, "inspect_run", inspect_journal)
        monkeypatch.setattr(
            approved_tests.approval,
            "verify_approval",
            lambda *a, **k: pytest.fail("fresh verification"),
        )
        value = assemble(linked)
        assert order == ["A", "J", "A", "J"]
        report = original_j(linked.registry, linked.consumed.intended_run_id)
        expected = fingerprint(
            {
                "domain": "canary-detached-journal-history-v1",
                "canonicalization": "replay-canonical-json-v1",
                "journal_schema": journal.SCHEMA,
                "registry_id": linked.registry.registry_id,
                "run_id": linked.consumed.intended_run_id,
                "records": report["records"],
            }
        )
        assert value.journal.history_commitment_sha256 == expected
        assert value.authority.receipt == linked.consumed
        assert value.source == source_projection(linked.proposal.source_receipt)
        assert value.journal.evidence_sha256 == report["evidence_sha256"]
        assert source_bytes(linked) == before

    @pytest.mark.parametrize(
        "mode", ["completed", "incomplete", "uncertain", "unacknowledged"]
    )
    def test_real_journal_states_are_distinct(
        self, tmp_path, proposal, signed, policy, mode
    ):
        linked = build_linked(tmp_path, proposal, signed, policy, mode=mode)
        value = assemble(linked)
        expected = {
            "uncertain": "operationally_uncertain",
            "unacknowledged": "incomplete",
        }.get(mode, mode)
        assert value.execution.journal_status == expected
        assert value.execution.journal_completion_certified is (mode == "completed")
        if mode == "uncertain":
            assert value.accounting.unknown_attempts == 1
            assert value.accounting.estimated_total_usd is None
        assert value.assurance.historical_completeness == "not-established"
        assert value.assurance.invocation_status == "not-established"

    def test_completed_behavioural_failure_is_preserved(
        self, tmp_path, proposal, signed, policy
    ):
        value = assemble(
            build_linked(
                tmp_path, proposal, signed, policy, mode="completed", fail=True
            )
        )
        assert value.execution.journal_completion_certified
        assert value.execution.mechanical_assessment_status == "FAIL"
        assert value.execution.overall_assessment_status == "FAIL"
        assert value.assurance.human_review == "PENDING"

    @pytest.mark.parametrize(
        "field", ["payload", "signature", "run_id", "expected_proposal"]
    )
    def test_signed_input_and_identity_mismatch(self, linked, field):
        changes = {
            "payload": linked.signed[0].replace(
                b"synthetic-provisioning-test-only",
                b"synthetic-provisioning-substitute",
            ),
            "signature": linked.signed[1] + b"x",
            "run_id": "synthetic-run-" + "f" * 32,
            "expected_proposal": linked.proposal.model_copy(
                update={"execution_audience": "synthetic-other"}
            ),
        }
        deny("binding_mismatch", lambda: assemble(linked, **{field: changes[field]}))

    def test_existing_controller_identity_is_not_mapped(self, linked):
        deny("invalid_input", lambda: assemble(linked, run_id="run-" + "1" * 32))

    @pytest.mark.parametrize(
        "kind", ["approval", "source", "provider_project", "provider_organization"]
    )
    def test_separate_valid_but_unlinked_journal_is_rejected(
        self, tmp_path, proposal, signed, policy, kind
    ):
        linked = build_linked(tmp_path, proposal, signed, policy)
        other = journal.initialize_registry(tmp_path / "other-journal")
        receipt = proposal.source_receipt
        if kind == "source":
            receipt = receipt.model_copy(
                update={"approval_reference": "synthetic:substituted"}
            )
        writer = journal.CanaryJournal(
            other,
            linked.consumed.intended_run_id,
            "synthetic-auth-" + "2" * 32
            if kind == "approval"
            else proposal.authorisation_id,
            source_receipt=receipt,
        )
        if kind.startswith("provider"):
            writer.bind_provider(
                receipt.binding,
                project_id="proj_synthetic_other"
                if kind == "provider_project"
                else proposal.project_id,
                organization_id="org_synthetic_other"
                if kind == "provider_organization"
                else proposal.organization_id,
            )
        writer.close()
        deny("binding_mismatch", lambda: assemble(linked, registry=other))

    @pytest.mark.parametrize(
        "fault", ["tamper", "middle_missing", "reorder", "truncate_bytes", "pending"]
    )
    def test_corruption_and_pending_block_without_repair(
        self, tmp_path, proposal, signed, policy, fault
    ):
        linked = build_linked(tmp_path, proposal, signed, policy, mode="completed")
        names = sorted(linked.records.iterdir())
        if fault == "tamper":
            names[2].write_bytes(
                names[2].read_bytes().replace(b'"run_id":', b'"wrong_id":', 1)
            )
        elif fault == "middle_missing":
            names[2].unlink()
        elif fault == "reorder":
            left, right = names[2].read_bytes(), names[3].read_bytes()
            names[2].write_bytes(right)
            names[3].write_bytes(left)
        elif fault == "truncate_bytes":
            names[-1].write_bytes(names[-1].read_bytes()[:-1])
        else:
            marker = linked.records / ".pending-test"
            marker.write_bytes(b"partial")
            marker.chmod(0o600)
        before = source_bytes(linked)
        deny(
            "journal_pending" if fault == "pending" else "journal_corrupt",
            lambda: assemble(linked),
        )
        assert source_bytes(linked) == before

    def test_valid_suffix_removal_is_incomplete_not_proof_of_history(
        self, tmp_path, proposal, signed, policy
    ):
        linked = build_linked(tmp_path, proposal, signed, policy, mode="completed")
        original = assemble(linked)
        max(linked.records.iterdir()).unlink()
        value = assemble(linked)
        assert value.execution.journal_status == "incomplete"
        assert not value.execution.journal_completion_certified
        assert value.journal.evidence_sha256 == original.journal.evidence_sha256
        assert (
            value.journal.history_commitment_sha256
            != original.journal.history_commitment_sha256
        )

    @pytest.mark.parametrize(
        "state", ["absent", "conflict", "corrupt", "unavailable", "pending", "rollback"]
    )
    def test_all_authority_denials_and_issues_block(self, linked, monkeypatch, state):
        before = source_bytes(linked)
        status = "consumed" if state in {"pending", "rollback"} else state
        issues = {
            "pending": ("pending_consumption",),
            "rollback": ("rollback_journal_present",),
        }.get(state, ())
        monkeypatch.setattr(
            authority,
            "inspect_consumption",
            lambda *a, **k: authority.ConsumptionInspection(
                status=status,
                record=linked.consumed if status == "consumed" else None,
                issues=issues,
            ),
        )
        deny(
            "authority_pending" if issues else "authority_" + state,
            lambda: assemble(linked),
        )
        assert source_bytes(linked) == before

    def test_actual_pending_authority_and_corruption_remain_untouched(self, linked):
        pending = (
            Path(linked.store.configuration.store_path) / "pending-consumption.json"
        )
        pending.write_text(canonical_json(linked.consumed.model_dump(mode="json")))
        pending.chmod(0o600)
        before = source_bytes(linked)
        deny("authority_pending", lambda: assemble(linked))
        assert source_bytes(linked) == before
        pending.write_text("partial")
        deny("authority_corrupt", lambda: assemble(linked))

    def test_repeat_observation_change_is_rejected_without_retry(
        self, linked, monkeypatch
    ):
        original = journal.inspect_run
        calls = []

        def inspect(*args):
            calls.append(1)
            report = original(*args)
            if len(calls) == 2:
                report["records"][0]["recorded_at"] = "2026-11-22T12:01:00+00:00"
            return report

        monkeypatch.setattr(journal, "inspect_run", inspect)
        deny("source_changed", lambda: assemble(linked))
        assert len(calls) == 2

    def test_actual_held_journal_writer_is_unavailable(self, linked, tmp_path):
        writer = journal.CanaryJournal(
            linked.registry,
            "another-run",
            "another-approval",
            source_receipt=linked.proposal.source_receipt,
        )
        try:
            deny("journal_unavailable", lambda: assemble(linked))
        finally:
            writer.close()

    def test_interrupted_inspection_is_private(self, linked, monkeypatch):
        def interrupted(*args, **kwargs):
            raise KeyboardInterrupt("PRIVATE_SENTINEL")

        monkeypatch.setattr(authority, "inspect_consumption", interrupted)
        deny("inspection_interrupted", lambda: assemble(linked))


def measure(linked, value):
    report = journal.inspect_run(linked.registry, linked.consumed.intended_run_id)
    largest = nodes = 0
    stack = [(report["records"], 0)]
    while stack:
        item, depth = stack.pop()
        nodes += 1
        largest = max(largest, depth)
        if isinstance(item, dict):
            stack.extend((child, depth + 1) for pair in item.items() for child in pair)
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
    sizes = [path.stat().st_size for path in linked.records.iterdir()]
    return {
        "records": len(report["records"]),
        "max_record_bytes": max(sizes),
        "aggregate_record_bytes": sum(sizes),
        "canonical_record_bytes": len(canonical_json(report["records"]).encode()),
        "depth": largest,
        "values": nodes,
        "envelope_bytes": len(envelope.serialize_envelope(value)),
        "authority_database_bytes": (
            Path(linked.store.configuration.store_path) / "authority.sqlite3"
        )
        .stat()
        .st_size,
        "logical_calls": report["accounting"]["logical_calls"],
        "provider_attempts": report["accounting"]["provider_attempts"],
    }


class TestInspectionLimits:
    @pytest.mark.parametrize("kind", ["count", "aggregate"])
    def test_large_source_inventory_is_rejected_before_inspector(
        self, linked, monkeypatch, kind
    ):
        if kind == "count":
            for index in range(1, envelope.MAX_JOURNAL_RECORDS + 1):
                path = linked.records / f"{index:06d}.json"
                path.write_bytes(b"x")
                path.chmod(0o600)
        else:
            for index in range(
                1, envelope.MAX_JOURNAL_BYTES // envelope.MAX_RECORD_BYTES + 1
            ):
                path = linked.records / f"{index:06d}.json"
                with path.open("wb") as stream:
                    stream.truncate(envelope.MAX_RECORD_BYTES)
                path.chmod(0o600)
        monkeypatch.setattr(
            journal, "inspect_run", lambda *a: pytest.fail("inspector called")
        )
        deny("resource_limit", lambda: assemble(linked))

    @pytest.mark.parametrize(
        "kind",
        [
            "completed",
            "profiled",
            "maximum",
            "revisions",
            "large_public",
            "incomplete",
            "uncertain",
        ],
    )
    def test_legitimate_bounded_fixtures_fit(
        self, tmp_path, proposal, signed, policy, kind
    ):
        linked = build_linked(
            tmp_path,
            proposal,
            signed,
            policy,
            mode=kind if kind in {"incomplete", "uncertain"} else "completed",
            calls=6 if kind == "maximum" else 1,
            attempts=3 if kind == "maximum" else 1,
            profiled=kind in {"maximum", "profiled"},
            revisions=3 if kind == "revisions" else 1,
            prose_size=24_000 if kind == "large_public" else 0,
        )
        value = assemble(linked)
        measurements = measure(linked, value)
        assert measurements["records"] <= envelope.MAX_JOURNAL_RECORDS
        assert measurements["max_record_bytes"] <= envelope.MAX_RECORD_BYTES
        assert measurements["aggregate_record_bytes"] <= envelope.MAX_JOURNAL_BYTES
        assert measurements["canonical_record_bytes"] <= envelope.MAX_JOURNAL_BYTES
        assert measurements["depth"] <= envelope.MAX_JOURNAL_DEPTH
        assert measurements["values"] <= envelope.MAX_JOURNAL_VALUES
        assert measurements["envelope_bytes"] <= envelope.MAX_ENVELOPE_BYTES
        assert measurements["authority_database_bytes"] <= envelope.MAX_AUTHORITY_BYTES
        if kind == "maximum":
            assert measurements["logical_calls"] == 24
            assert measurements["provider_attempts"] == 72
        (tmp_path / "measurements.json").write_text(
            json.dumps({"fixture": kind, **measurements}, indent=2)
        )

    def test_oversize_record_fails_before_inspector_without_truncation(
        self, linked, monkeypatch
    ):
        record = linked.records / "000000.json"
        with record.open("r+b") as stream:
            stream.truncate(envelope.MAX_RECORD_BYTES + 1)
        before = record.stat().st_size
        monkeypatch.setattr(
            journal, "inspect_run", lambda *a: pytest.fail("inspector called")
        )
        deny("resource_limit", lambda: assemble(linked))
        assert record.stat().st_size == before

    def test_oversize_authority_preflight_does_not_call_inspector(
        self, linked, monkeypatch
    ):
        database = Path(linked.store.configuration.store_path) / "authority.sqlite3"
        with database.open("r+b") as stream:
            stream.truncate(envelope.MAX_AUTHORITY_BYTES + 1)
        monkeypatch.setattr(
            authority,
            "inspect_consumption",
            lambda *a, **k: pytest.fail("inspector called"),
        )
        deny("resource_limit", lambda: assemble(linked))
        assert database.stat().st_size == envelope.MAX_AUTHORITY_BYTES + 1

    def test_postinspection_growth_is_rejected_without_claiming_internal_budget(
        self, linked, monkeypatch
    ):
        original = journal.inspect_run

        def grown(*args):
            report = original(*args)
            report["records"] *= envelope.MAX_JOURNAL_RECORDS + 1
            return report

        monkeypatch.setattr(journal, "inspect_run", grown)
        deny("resource_limit", lambda: assemble(linked))

    def test_boundaries_of_bounded_encoding(self):
        assert len(envelope._encode("x" * 8, limit=10)) == 10
        deny("resource_limit", lambda: envelope._encode("x" * 9, limit=10))
        assert envelope._encode([0], depth=1, nodes=2) == b"[0]"
        deny("resource_limit", lambda: envelope._encode([0], depth=0, nodes=2))
        deny("resource_limit", lambda: envelope._encode([0], depth=1, nodes=1))


class TestPrivacy:
    def test_projection_omits_paths_prose_and_unnecessary_identifiers(
        self, tmp_path, proposal, signed, policy
    ):
        linked = build_linked(
            tmp_path, proposal, signed, policy, mode="completed", prose_size=100
        )
        raw = envelope.serialize_envelope(assemble(linked))
        for forbidden in (
            str(tmp_path),
            "SYNTHETIC_PUBLIC_PROSE_",
            proposal.project_id,
            proposal.organization_id,
            proposal.credential_provisioning_reference,
            proposal.source_receipt.approval_reference,
            "PRIVATE_PROVIDER_REASONING",
            "req_synthetic",
            "resp_A1_1",
            "user_message",
            "tool_calls",
        ):
            assert forbidden.encode() not in raw
        assert b'"provider_evidence_authenticated":false' in raw
        assert b'"authorises_live_execution":false' in raw


def _inspection_worker(pipe, mode, document):
    """Separate process with explicit barriers; never a provider/application."""
    try:
        if mode == "journal_lock":
            registry = journal.RegistryBinding.model_validate_json(document["registry"])
            writer = journal.CanaryJournal(
                registry,
                "held-run",
                "held-approval",
                source_receipt=document["source"],
            )
            pipe.send("ready")
            assert pipe.recv() == "finish"
            writer.close()
        elif mode == "authority_lock":
            descriptor = os.open(document["lock"], os.O_RDONLY)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                pipe.send("ready")
                assert pipe.recv() == "finish"
            finally:
                os.close(descriptor)
        else:
            pipe.send("ready")
            assert pipe.recv() == "change"
            path = Path(document["record"])
            value = json.loads(path.read_bytes())["payload"]
            value["recorded_at"] = "2000-01-01T00:00:00+00:00"
            path.write_text(
                canonical_json({"payload": value, "sha256": fingerprint(value)})
            )
            pipe.send("changed")
        pipe.send("finished")
    except BaseException:  # noqa: BLE001 - worker diagnostics never expose source content
        pipe.send("failed")
    finally:
        pipe.close()


def receive(pipe):
    assert pipe.poll(20), "worker barrier timeout"
    return pipe.recv()


class TestInspectionProcesses:
    @pytest.mark.parametrize("kind", ["journal_lock", "authority_lock", "changed"])
    def test_coordinated_source_observations(self, linked, monkeypatch, kind):
        parent, child = multiprocessing.get_context("spawn").Pipe()
        process = multiprocessing.get_context("spawn").Process(
            target=_inspection_worker,
            args=(
                child,
                kind,
                {
                    "registry": linked.registry.model_dump_json(),
                    "source": linked.proposal.source_receipt.model_dump_json(),
                    "lock": str(
                        Path(linked.store.configuration.store_path) / "writer.lock"
                    ),
                    "record": str(linked.records / "000000.json"),
                },
            ),
        )
        process.start()
        child.close()
        try:
            assert receive(parent) == "ready"
            if kind == "changed":
                original = journal.inspect_run
                calls = []

                def inspect(*args):
                    report = original(*args)
                    calls.append(1)
                    if len(calls) == 1:
                        parent.send("change")
                        assert receive(parent) == "changed"
                    return report

                monkeypatch.setattr(journal, "inspect_run", inspect)
                deny("source_changed", lambda: assemble(linked))
                assert len(calls) == 2
            else:
                deny(
                    "journal_unavailable"
                    if kind == "journal_lock"
                    else "authority_unavailable",
                    lambda: assemble(linked),
                )
                parent.send("finish")
            assert receive(parent) == "finished"
            process.join(20)
            assert process.exitcode == 0
        finally:
            if process.is_alive():
                process.kill()
                process.join(5)
            parent.close()

    def test_unrelated_clean_authority_append_is_not_a_global_snapshot_claim(
        self, linked, keys, policy, manifest, monkeypatch
    ):
        new_proposal = linked.proposal.model_copy(
            update={"authorisation_id": "synthetic-auth-" + "2" * 32}
        )
        new_manifest = manifest.model_copy(update={"execution": new_proposal})
        payload = approved_tests.approval.serialize_manifest(new_manifest)
        signature = keys.sign(payload)
        original = journal.inspect_run
        calls = []

        def inspect(*args):
            report = original(*args)
            calls.append(1)
            if len(calls) == 1:
                now = approved_tests.NOW
                authority.consume_approval(
                    payload,
                    signature,
                    expected=new_proposal,
                    store=linked.store,
                    clock=lambda: now,
                    policy=lambda: authority.PolicyObservation(
                        schema_id="canary-synthetic-policy-observation-v1",
                        policy=policy,
                        observed_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        expires_at=(now + timedelta(seconds=30)).strftime(
                            "%Y-%m-%dT%H:%M:%SZ"
                        ),
                    ),
                )
            return report

        monkeypatch.setattr(journal, "inspect_run", inspect)
        value = assemble(linked)
        assert len(calls) == 2
        assert value.authority.receipt == linked.consumed
        assert value.assurance.snapshot_semantics == "separate-repeated-observations"
        assert (
            authority.inspect_consumption(
                linked.store, new_proposal.authorisation_id
            ).status
            == "consumed"
        )
        measurements = measure(linked, value)
        measurements["fixture"] = "multiple-consumption-records"
        (
            Path(linked.store.configuration.store_path).parent / "measurements.json"
        ).write_text(json.dumps(measurements, indent=2))


def retained_reference(value):
    """Test operator pins known fixture context before any subsequent mutation."""
    return envelope.ExpectedEnvelopeReference(
        envelope_commitment_sha256=sha256(
            canonical_json(
                {
                    "domain": "canary-detached-envelope-v1",
                    "canonicalization": "replay-canonical-json-v1",
                    "envelope": value.model_dump(mode="json"),
                }
            ).encode()
        ).hexdigest(),
        store_id=value.authority.receipt.store_id,
        store_binding_sha256=value.authority.store_binding_sha256,
        registry_id=value.journal.registry_id,
        registry_binding_sha256=value.journal.registry_binding_sha256,
        authorisation_id=value.authority.receipt.authorisation_id,
        execution_audience=value.authority.receipt.execution_audience,
        run_id=value.journal.run_id,
    )


def publication_root(tmp_path):
    path = tmp_path / "private-publications"
    path.mkdir(mode=0o700)
    info = path.stat()
    return envelope.TrustedPublicationRoot(
        path=str(path), device=info.st_dev, directory_inode=info.st_ino
    )


def manual_artifact(root, value, name="artifact"):
    directory = Path(root.path) / name
    directory.mkdir(mode=0o700)
    path = directory / "envelope.json"
    path.write_bytes(envelope.serialize_envelope(value))
    path.chmod(0o600)
    return directory


class TestArtifactVerification:
    def test_separate_reference_required_no_reference_discovery(
        self, candidate, monkeypatch
    ):
        expected = retained_reference(candidate)
        raw = envelope.serialize_envelope(candidate)
        monkeypatch.setattr(
            envelope,
            "_reference_candidate",
            lambda *a: pytest.fail("derived reference"),
        )
        result = envelope.verify_envelope(raw, expected=expected)
        assert result.envelope_commitment_sha256 == expected.envelope_commitment_sha256
        assert result.source_comparison == "not-performed"
        assert result.approval_signature_verification == "not-performed"
        assert not result.assurance.authorises_live_execution
        deny("invalid_reference", lambda: envelope.verify_envelope(raw, expected=None))
        with pytest.raises(TypeError):
            envelope.verify_envelope(raw)

    @pytest.mark.parametrize(
        "field", list(envelope.ExpectedEnvelopeReference.model_fields)
    )
    def test_every_expected_reference_field_is_required(self, candidate, field):
        reference = retained_reference(candidate).model_dump(mode="json")
        del reference[field]
        deny(
            "invalid_reference",
            lambda: envelope.verify_envelope(
                envelope.serialize_envelope(candidate), expected=reference
            ),
        )

    @pytest.mark.parametrize(
        "field",
        [
            "envelope_commitment_sha256",
            "store_id",
            "store_binding_sha256",
            "registry_id",
            "registry_binding_sha256",
            "authorisation_id",
            "execution_audience",
            "run_id",
        ],
    )
    def test_all_expected_context_is_checked(self, candidate, field):
        expected = retained_reference(candidate)
        changes = {
            "envelope_commitment_sha256": "f" * 64,
            "store_id": "synthetic-store-" + "f" * 32,
            "store_binding_sha256": "f" * 64,
            "registry_id": "f" * 32,
            "registry_binding_sha256": "f" * 64,
            "authorisation_id": "synthetic-auth-" + "f" * 32,
            "execution_audience": "synthetic-other",
            "run_id": "synthetic-run-" + "f" * 32,
        }
        expected = expected.model_copy(update={field: changes[field]})
        deny(
            "reference_mismatch",
            lambda: envelope.verify_envelope(
                envelope.serialize_envelope(candidate), expected=expected
            ),
        )

    def test_raw_file_hash_is_not_the_expected_commitment(self, candidate):
        raw = envelope.serialize_envelope(candidate)
        expected = retained_reference(candidate).model_copy(
            update={"envelope_commitment_sha256": sha256(raw).hexdigest()}
        )
        deny(
            "reference_mismatch",
            lambda: envelope.verify_envelope(raw, expected=expected),
        )

    def test_substituted_artifact_and_checksum_do_not_replace_independent_reference(
        self, candidate
    ):
        expected = retained_reference(candidate)
        document = candidate.model_dump(mode="json")
        document["journal"]["history_commitment_sha256"] = "b" * 64
        substituted = envelope.parse_envelope(canonical_json(document).encode())
        raw = envelope.serialize_envelope(substituted)
        attacker_reference = retained_reference(substituted)
        deny(
            "reference_mismatch",
            lambda: envelope.verify_envelope(raw, expected=expected),
        )
        # Compromise of the caller's trust reference cannot be detected locally.
        result = envelope.verify_envelope(raw, expected=attacker_reference)
        assert result.source_comparison == "not-performed"
        assert result.assurance.source_authorised is False
        assert result.assurance.execution_admission_established is False

    def test_read_only_reopening_does_not_write_or_discover_sidecars(
        self, tmp_path, candidate, monkeypatch
    ):
        root = publication_root(tmp_path)
        directory = manual_artifact(root, candidate)
        expected = retained_reference(candidate)
        before = journal_tests.tree_bytes(Path(root.path))
        original = os.open
        modes = []

        def observe(path, flags, *args, **kwargs):
            modes.append(flags)
            assert not flags & (os.O_CREAT | os.O_WRONLY | os.O_RDWR | os.O_TRUNC)
            return original(path, flags, *args, **kwargs)

        monkeypatch.setattr(envelope.os, "open", observe)
        result = envelope.read_envelope(
            publication_root=root, publication_id="artifact", expected=expected
        )
        assert result.source_comparison == "not-performed" and modes
        assert journal_tests.tree_bytes(Path(root.path)) == before
        # An adjacent candidate is never silently adopted as a reference.
        (directory / "reference.json").write_text(expected.model_dump_json())
        deny(
            "artifact_unavailable",
            lambda: envelope.read_envelope(
                publication_root=root, publication_id="artifact", expected=expected
            ),
        )

    @pytest.mark.parametrize(
        "fault", ["pending", "symlink", "fifo", "hardlink", "permissions", "oversize"]
    )
    def test_unsafe_or_partial_artifact_is_rejected(self, tmp_path, candidate, fault):
        root = publication_root(tmp_path)
        directory = manual_artifact(root, candidate)
        path = directory / "envelope.json"
        if fault == "pending":
            (directory / ".pending-envelope").write_bytes(b"pending")
        elif fault == "symlink":
            saved = directory / "saved"
            path.rename(saved)
            path.symlink_to(saved)
        elif fault == "fifo":
            path.unlink()
            os.mkfifo(path, mode=0o600)
        elif fault == "hardlink":
            os.link(path, tmp_path / "alias")
        elif fault == "permissions":
            path.chmod(0o644)
        else:
            path.write_bytes(b"x" * (envelope.MAX_ENVELOPE_BYTES + 1))
        deny(
            "resource_limit" if fault == "oversize" else "artifact_unavailable",
            lambda: envelope.read_envelope(
                publication_root=root,
                publication_id="artifact",
                expected=retained_reference(candidate),
            ),
        )


def verify_sources(linked, raw, expected, **changes):
    return envelope.verify_against_sources(
        raw,
        **{
            "expected": expected,
            "payload": linked.signed[0],
            "signature": linked.signed[1],
            "expected_proposal": linked.proposal,
            "store": linked.store,
            "registry": linked.registry,
            **changes,
        },
    )


class TestSourceVerification:
    def test_actual_source_reobservation_is_repeatable_read_only_and_not_authentication(
        self, linked, monkeypatch
    ):
        value = assemble(linked)
        raw, expected = envelope.serialize_envelope(value), retained_reference(value)
        before = source_bytes(linked)
        monkeypatch.setattr(
            approved_tests.approval,
            "verify_approval",
            lambda *a, **k: pytest.fail("fresh authentication"),
        )
        monkeypatch.setattr(
            authority, "consume_approval", lambda *a, **k: pytest.fail("consumption")
        )
        for _ in range(2):
            result = verify_sources(linked, raw, expected)
            assert result.source_comparison == "matches-reobserved-sources"
            assert result.approval_signature_verification == "not-performed"
            assert not result.assurance.provider_evidence_authenticated
        assert source_bytes(linked) == before

    @pytest.mark.parametrize("fault", ["suffix", "valid_timestamp", "corrupt"])
    def test_anchored_history_detects_later_source_changes(
        self, tmp_path, proposal, signed, policy, fault
    ):
        linked = build_linked(tmp_path, proposal, signed, policy, mode="completed")
        value = assemble(linked)
        raw, expected = envelope.serialize_envelope(value), retained_reference(value)
        if fault == "suffix":
            max(linked.records.iterdir()).unlink()
        elif fault == "valid_timestamp":
            path = max(linked.records.iterdir())
            record = json.loads(path.read_bytes())["payload"]
            record["recorded_at"] = "2000-01-01T00:00:00+00:00"
            path.write_text(
                canonical_json({"payload": record, "sha256": fingerprint(record)})
            )
        else:
            max(linked.records.iterdir()).write_bytes(b"partial")
        deny(
            "journal_corrupt" if fault == "corrupt" else "source_mismatch",
            lambda: verify_sources(linked, raw, expected),
        )

    def test_independent_context_is_checked_before_source_access(
        self, linked, monkeypatch
    ):
        value = assemble(linked)
        raw, expected = envelope.serialize_envelope(value), retained_reference(value)
        monkeypatch.setattr(
            authority,
            "inspect_consumption",
            lambda *a, **k: pytest.fail("source accessed"),
        )
        wrong = linked.registry.model_copy(update={"registry_id": "f" * 32})
        deny(
            "binding_mismatch",
            lambda: verify_sources(linked, raw, expected, registry=wrong),
        )
        wrong_expected = expected.model_copy(
            update={"envelope_commitment_sha256": "f" * 64}
        )
        deny("reference_mismatch", lambda: verify_sources(linked, raw, wrong_expected))


def publish(linked, root, value=None, name="artifact"):
    return envelope.publish_envelope(
        assemble(linked) if value is None else value,
        publication_root=root,
        publication_id=name,
        store=linked.store,
        registry=linked.registry,
    )


class TestPublication:
    @pytest.mark.parametrize("kind", ["same", "inside", "parent"])
    def test_actual_directory_ancestry_enforces_overlap_without_lexical_shortcut(
        self, linked, tmp_path, monkeypatch, kind
    ):
        value = assemble(linked)
        store_path = Path(linked.store.configuration.store_path)
        path = {
            "same": store_path,
            "inside": store_path / "publication",
            "parent": tmp_path,
        }[kind]
        if kind == "inside":
            path.mkdir(mode=0o700)
        # APFS case aliases resolve to the same identity; Linux still exercises
        # the metadata-only guard when that alias is not available.
        case_alias = path.with_name(path.name.upper())
        if case_alias.exists():
            path = case_alias
        info = path.stat()
        root = envelope.TrustedPublicationRoot(
            path=str(path), device=info.st_dev, directory_inode=info.st_ino
        )
        before = source_bytes(linked)
        with monkeypatch.context() as patch:
            patch.setattr(Path, "is_relative_to", lambda *args: False)
            deny("unsafe_destination", lambda: publish(linked, root, value))
        assert source_bytes(linked) == before

    def test_double_root_alias_cannot_bypass_source_overlap(self, linked):
        value = assemble(linked)
        root = envelope.TrustedPublicationRoot.model_construct(
            schema_id="canary-private-publication-root-v1",
            path="/" + linked.store.configuration.store_path,
            device=linked.store.device,
            directory_inode=linked.store.directory_inode,
        )
        before = source_bytes(linked)
        deny("invalid_publication_root", lambda: publish(linked, root, value))
        assert source_bytes(linked) == before

    def test_private_exclusive_publication_and_complete_candidate_handoff(
        self, linked, tmp_path, monkeypatch
    ):
        value = assemble(linked)
        expected = retained_reference(value)
        before = source_bytes(linked)
        root = publication_root(tmp_path)
        monkeypatch.setattr(
            authority,
            "inspect_consumption",
            lambda *a, **k: pytest.fail("publisher inspected"),
        )
        monkeypatch.setattr(
            journal, "inspect_run", lambda *a, **k: pytest.fail("publisher inspected")
        )
        result = publish(linked, root, value)
        assert result.reference_candidate == expected
        assert result.bytes_written == len(envelope.serialize_envelope(value))
        assert result.publication_status == "local-publication-protocol-completed"
        assert result.source_inspections_performed is False
        assert result.independent_custody == "not-established-by-publisher"
        assert "path" not in result.model_dump_json()
        directory = Path(root.path) / "artifact"
        final = directory / "envelope.json"
        assert list(directory.iterdir()) == [final]
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        assert stat.S_IMODE(final.stat().st_mode) == 0o600
        assert final.stat().st_nlink == 1
        assert final.read_bytes() == envelope.serialize_envelope(value)
        verified = envelope.read_envelope(
            publication_root=root, publication_id="artifact", expected=expected
        )
        assert verified.source_comparison == "not-performed"
        assert source_bytes(linked) == before

    def test_caller_constructed_envelope_is_published_without_provenance_promotion(
        self, linked, tmp_path
    ):
        value = assemble(linked)
        forged = value.model_copy(
            update={
                "journal": value.journal.model_copy(
                    update={"history_commitment_sha256": "f" * 64}
                )
            }
        )
        result = publish(linked, publication_root(tmp_path), forged)
        assert not result.source_inspections_performed
        assert result.independent_custody == "not-established-by-publisher"
        deny(
            "source_mismatch",
            lambda: verify_sources(
                linked, envelope.serialize_envelope(forged), result.reference_candidate
            ),
        )

    @pytest.mark.parametrize("different", [False, True])
    def test_existing_destination_is_never_replaced(self, linked, tmp_path, different):
        root = publication_root(tmp_path)
        value = assemble(linked)
        publish(linked, root, value)
        before = journal_tests.tree_bytes(Path(root.path))
        if different:
            value = value.model_copy(
                update={
                    "journal": value.journal.model_copy(
                        update={"history_commitment_sha256": "e" * 64}
                    )
                }
            )
        deny("destination_exists", lambda: publish(linked, root, value))
        assert journal_tests.tree_bytes(Path(root.path)) == before

    @pytest.mark.parametrize(
        "name",
        ["", ".", "..", ".hidden", "../escape", "a/b", "/absolute", "x" * 65, "a\\b"],
    )
    def test_only_direct_child_identifiers_are_accepted(self, linked, tmp_path, name):
        root = publication_root(tmp_path)
        deny("unsafe_destination", lambda: publish(linked, root, name=name))
        assert list(Path(root.path).iterdir()) == []

    @pytest.mark.parametrize(
        "kind", ["store", "journal", "parent", "inside_store", "inside_journal"]
    )
    def test_source_overlap_is_rejected_in_both_directions(
        self, linked, tmp_path, kind
    ):
        value = assemble(linked)
        path = {
            "store": Path(linked.store.configuration.store_path),
            "journal": Path(linked.registry.path),
            "parent": tmp_path,
            "inside_store": Path(linked.store.configuration.store_path) / "publication",
            "inside_journal": Path(linked.registry.path) / "publication",
        }[kind]
        if kind.startswith("inside"):
            path.mkdir(mode=0o700)
        info = path.stat()
        root = envelope.TrustedPublicationRoot(
            path=str(path), device=info.st_dev, directory_inode=info.st_ino
        )
        before = source_bytes(linked)
        deny("unsafe_destination", lambda: publish(linked, root, value))
        assert not (path / "artifact").exists()
        assert source_bytes(linked) == before

    @pytest.mark.parametrize(
        "fault",
        [
            "mode",
            "inode",
            "symlink",
            "ancestor_symlink",
            "copy",
            "missing",
            "relative",
            "extra",
        ],
    )
    def test_root_binding_is_independently_checked(self, linked, tmp_path, fault):
        root = publication_root(tmp_path)
        path = Path(root.path)
        if fault == "mode":
            path.chmod(0o755)
        elif fault in {"inode", "symlink"}:
            moved = tmp_path / "moved-root"
            path.rename(moved)
            if fault == "symlink":
                path.symlink_to(moved, target_is_directory=True)
            else:
                path.mkdir(mode=0o700)
        elif fault == "ancestor_symlink":
            alias = tmp_path / "alias"
            alias.symlink_to(tmp_path, target_is_directory=True)
            root = root.model_copy(update={"path": str(alias / path.name)})
        elif fault == "copy":
            other = tmp_path / "copy-root"
            other.mkdir(mode=0o700)
            root = root.model_copy(update={"path": str(other)})
        elif fault == "missing":
            path.rmdir()
        elif fault == "relative":
            root = root.model_copy(update={"path": "relative"})
        else:
            root = root.model_copy(update={"private": "PRIVATE_SENTINEL"})
        deny("invalid_publication_root", lambda: publish(linked, root))

    def test_root_caller_responsibility_is_not_a_discovery_claim(
        self, linked, tmp_path
    ):
        # The module cannot recognise every historical namespace. Trusted caller
        # exclusion is a prerequisite, not a discovery service or schema attestation.
        root = publication_root(tmp_path)
        result = publish(linked, root)
        assert not hasattr(result, "historical_namespaces_verified")
        assert not hasattr(result, "repositories_discovered")

    @pytest.mark.parametrize(
        "phase",
        [
            "mkdir_before",
            "mkdir_after",
            "short_write",
            "disk_full",
            "file_sync",
            "root_sync",
            "link_before",
            "link_after",
            "link_sync",
            "unlink_before",
            "unlink_after",
            "final_file_sync",
            "final_dir_sync",
            "reread",
            "close_file",
            "close_directory",
        ],
    )
    @pytest.mark.parametrize("interrupted", [False, True])
    def test_filesystem_failures_preserve_sources_and_partial_output(
        self, linked, tmp_path, monkeypatch, phase, interrupted
    ):
        root = publication_root(tmp_path)
        value = assemble(linked)
        expected = retained_reference(value)
        raw = envelope.serialize_envelope(value)
        before = source_bytes(linked)
        calls = []
        original_mkdir, original_write, original_sync = os.mkdir, os.write, os.fsync
        original_link, original_unlink, original_close = os.link, os.unlink, os.close
        directory = Path(root.path) / "artifact"

        def fail():
            calls.append(1)
            if interrupted:
                raise KeyboardInterrupt("PRIVATE_FAILURE_SENTINEL")
            raise OSError(
                errno.ENOSPC if phase == "disk_full" else errno.EIO,
                "PRIVATE_FAILURE_SENTINEL",
            )

        with monkeypatch.context() as patch:
            if phase.startswith("mkdir"):

                def mkdir(*args, **kwargs):
                    if phase == "mkdir_after":
                        original_mkdir(*args, **kwargs)
                    fail()

                patch.setattr(envelope.os, "mkdir", mkdir)
            elif phase in {"short_write", "disk_full"}:

                def write(fd, data):
                    if phase == "disk_full":
                        fail()
                    calls.append(1)
                    return original_write(fd, data[: len(data) // 2])

                patch.setattr(envelope.os, "write", write)
            elif "sync" in phase:
                count = []
                selected = {
                    "root_sync": 1,
                    "file_sync": 2,
                    "link_sync": 3,
                    "final_file_sync": 4,
                    "final_dir_sync": 5,
                }[phase]

                def fsync(fd):
                    count.append(1)
                    if len(count) == selected:
                        fail()
                    return original_sync(fd)

                patch.setattr(envelope.os, "fsync", fsync)
            elif phase.startswith("link"):

                def link(*args, **kwargs):
                    if phase == "link_after":
                        original_link(*args, **kwargs)
                    fail()

                patch.setattr(envelope.os, "link", link)
            elif phase.startswith("unlink"):

                def unlink(*args, **kwargs):
                    if phase == "unlink_after":
                        original_unlink(*args, **kwargs)
                    fail()

                patch.setattr(envelope.os, "unlink", unlink)
            elif phase == "reread":
                patch.setattr(envelope, "_read_artifact", lambda *a: fail())
            else:

                def close(fd):
                    info = os.fstat(fd)
                    targeted = (
                        stat.S_ISREG(info.st_mode)
                        if phase == "close_file"
                        else (
                            directory.exists()
                            and info.st_ino == directory.stat().st_ino
                        )
                    )
                    if (
                        targeted
                        and (directory / "envelope.json").exists()
                        and not calls
                    ):
                        original_close(fd)
                        fail()
                    return original_close(fd)

                patch.setattr(envelope.os, "close", close)
            code = (
                "publication_failed"
                if phase in {"short_write", "disk_full", "file_sync", "root_sync"}
                else "publication_outcome_unknown"
            )
            deny(code, lambda: publish(linked, root, value))
        assert len(calls) == 1
        assert source_bytes(linked) == before
        if directory.exists():
            deny("destination_exists", lambda: publish(linked, root, value))
            final = directory / "envelope.json"
            if final.exists() and not (directory / ".pending-envelope").exists():
                # Readable anchored bytes do not prove the failed publisher returned.
                assert final.read_bytes() == raw
                result = envelope.read_envelope(
                    publication_root=root, publication_id="artifact", expected=expected
                )
                assert result.source_comparison == "not-performed"

    @pytest.mark.parametrize("which", ["root", "destination"])
    def test_path_substitution_during_publication_never_follows_replacement(
        self, linked, tmp_path, monkeypatch, which
    ):
        value = assemble(linked)
        root = publication_root(tmp_path)
        original = os.link
        outside = tmp_path / "outside"
        outside.mkdir(mode=0o700)
        before = source_bytes(linked)

        def link(*args, **kwargs):
            original(*args, **kwargs)
            path = Path(root.path) if which == "root" else Path(root.path) / "artifact"
            path.rename(tmp_path / "moved")
            path.symlink_to(outside, target_is_directory=True)

        monkeypatch.setattr(envelope.os, "link", link)
        deny("publication_outcome_unknown", lambda: publish(linked, root, value))
        assert list(outside.iterdir()) == []
        assert source_bytes(linked) == before


def _publication_worker(
    pipe, raw, root_json, store_json, registry_json, publication_id, phase="normal"
):
    """Crash/read/write barriers run in a distinct process and private namespace."""
    try:
        value = envelope.parse_envelope(raw)
        root = envelope.TrustedPublicationRoot.model_validate_json(root_json)
        store = authority.AuthorityStoreBinding.model_validate_json(store_json)
        registry = journal.RegistryBinding.model_validate_json(registry_json)
        original_write, original_sync = os.write, os.fsync
        original_link, original_unlink, original_mkdir = os.link, os.unlink, os.mkdir

        def boundary():
            pipe.send(("boundary", phase))
            assert pipe.recv() == "release"

        if phase == "after_mkdir":

            def mkdir(*args, **kwargs):
                original_mkdir(*args, **kwargs)
                boundary()

            envelope.os.mkdir = mkdir
        elif phase in {"before_write", "after_write"}:

            def write(*args, **kwargs):
                if phase == "before_write":
                    boundary()
                result = original_write(*args, **kwargs)
                if phase == "after_write":
                    boundary()
                return result

            envelope.os.write = write
        elif phase in {"after_file_sync", "after_link_sync", "after_final_sync"}:
            count = []
            selected = {
                "after_file_sync": 2,
                "after_link_sync": 3,
                "after_final_sync": 5,
            }[phase]

            def fsync(*args, **kwargs):
                result = original_sync(*args, **kwargs)
                count.append(1)
                if len(count) == selected:
                    boundary()
                return result

            envelope.os.fsync = fsync
        elif phase in {"before_link", "after_link"}:

            def link(*args, **kwargs):
                if phase == "before_link":
                    boundary()
                result = original_link(*args, **kwargs)
                if phase == "after_link":
                    boundary()
                return result

            envelope.os.link = link
        elif phase == "after_unlink":

            def unlink(*args, **kwargs):
                result = original_unlink(*args, **kwargs)
                boundary()
                return result

            envelope.os.unlink = unlink
        pipe.send("ready")
        assert pipe.recv() == "go"
        try:
            result = envelope.publish_envelope(
                value,
                publication_root=root,
                publication_id=publication_id,
                store=store,
                registry=registry,
            )
            pipe.send(("success", result.model_dump_json()))
            if phase == "after_return":
                pipe.recv()
        except envelope.EnvelopeError as error:
            pipe.send(("denied", str(error)))
    except BaseException:  # noqa: BLE001 - child errors cannot disclose fixture inputs
        pipe.send(("failed", "unexpected"))
    finally:
        pipe.close()


def start_publication_worker(linked, value, root, name="artifact", phase="normal"):
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(
        target=_publication_worker,
        args=(
            child,
            envelope.serialize_envelope(value),
            root.model_dump_json(),
            linked.store.model_dump_json(),
            linked.registry.model_dump_json(),
            name,
            phase,
        ),
    )
    process.start()
    child.close()
    return process, parent


def finish_process(process, pipe):
    try:
        process.join(20)
        assert not process.is_alive() and process.exitcode == 0
    finally:
        if process.is_alive():
            process.kill()
            process.join(5)
        pipe.close()


class TestPublicationProcesses:
    def test_three_competing_publishers_one_exclusive_success(self, linked, tmp_path):
        root, value = publication_root(tmp_path), assemble(linked)
        before = source_bytes(linked)
        workers = [start_publication_worker(linked, value, root) for _ in range(3)]
        try:
            for _, pipe in workers:
                assert receive(pipe) == "ready"
            for _, pipe in workers:
                pipe.send("go")
            results = [receive(pipe) for _, pipe in workers]
            assert sum(result[0] == "success" for result in results) == 1
            assert (
                sum(result == ("denied", "destination_exists") for result in results)
                == 2
            )
            assert (
                envelope.read_envelope(
                    publication_root=root,
                    publication_id="artifact",
                    expected=retained_reference(value),
                ).source_comparison
                == "not-performed"
            )
            assert source_bytes(linked) == before
        finally:
            for process, pipe in workers:
                finish_process(process, pipe)

    def test_reader_observes_partial_then_complete_without_durability_attestation(
        self, linked, tmp_path
    ):
        root, value = publication_root(tmp_path), assemble(linked)
        process, pipe = start_publication_worker(
            linked, value, root, phase="after_link"
        )
        try:
            assert receive(pipe) == "ready"
            pipe.send("go")
            assert receive(pipe) == ("boundary", "after_link")
            final = Path(root.path) / "artifact" / "envelope.json"
            assert final.exists() and final.stat().st_nlink == 2
            deny(
                "artifact_unavailable",
                lambda: envelope.read_envelope(
                    publication_root=root,
                    publication_id="artifact",
                    expected=retained_reference(value),
                ),
            )
            pipe.send("release")
            kind, document = receive(pipe)
            assert kind == "success"
            result = envelope.PublicationReceipt.model_validate_json(document)
            assert result.reference_candidate == retained_reference(value)
            verified = envelope.read_envelope(
                publication_root=root,
                publication_id="artifact",
                expected=retained_reference(value),
            )
            assert verified.source_comparison == "not-performed"
        finally:
            finish_process(process, pipe)

    @pytest.mark.parametrize(
        "phase",
        [
            "after_mkdir",
            "before_write",
            "after_write",
            "after_file_sync",
            "before_link",
            "after_link",
            "after_link_sync",
            "after_unlink",
            "after_final_sync",
            "after_return",
        ],
    )
    def test_sigkill_preserves_partial_or_readable_artifact_without_reopening_authority(
        self, linked, tmp_path, phase
    ):
        root, value = publication_root(tmp_path), assemble(linked)
        before = source_bytes(linked)
        process, pipe = start_publication_worker(linked, value, root, phase=phase)
        try:
            assert receive(pipe) == "ready"
            pipe.send("go")
            result = receive(pipe)
            if phase == "after_return":
                assert result[0] == "success"
            else:
                assert result == ("boundary", phase)
            process.kill()
            process.join(20)
            assert process.exitcode == -signal.SIGKILL
            assert source_bytes(linked) == before
            assert (
                authority.inspect_consumption(
                    linked.store, linked.proposal.authorisation_id
                ).record
                == linked.consumed
            )
            directory = Path(root.path) / "artifact"
            assert (
                directory.exists() and stat.S_IMODE(directory.stat().st_mode) == 0o700
            )
            deny("destination_exists", lambda: publish(linked, root, value))
            if phase in {"after_unlink", "after_final_sync", "after_return"}:
                verified = envelope.read_envelope(
                    publication_root=root,
                    publication_id="artifact",
                    expected=retained_reference(value),
                )
                assert verified.source_comparison == "not-performed"
                assert not hasattr(verified, "publisher_returned")
            else:
                deny(
                    "artifact_unavailable",
                    lambda: envelope.read_envelope(
                        publication_root=root,
                        publication_id="artifact",
                        expected=retained_reference(value),
                    ),
                )
        finally:
            if process.is_alive():
                process.kill()
                process.join(5)
            pipe.close()


class TestCompatibility:
    # Complete Git/lock preservation is a one-time publication gate in the plan.
    # These regressions depend on historical contracts, not checkout Git state.
    def test_historical_definition_and_application_contracts_remain_exact(self):
        from harness.canary import runtime_v3

        c1 = runtime_v3.resolve_definition()
        v3 = runtime_v3.resolve_definition(runtime_v3.V3)
        assert (
            c1.roster_fingerprint
            == "e8778ce74a270e6efbe490198d01e8b9c50bcc43387a02bff5f00b42304d5794"
        )
        assert (
            v3.v2_1_fingerprint
            == "3c632f6ce5e8b9eda42b4a0a0f91ccb82f4f34783da3b9638762b84351c9c2f9"
        )
        assert (
            v3.definition_fingerprint
            == "e76fd0e10f1176d6aa421a2b5de93f9503dceaa422b0631c2c8f7c957aa75607"
        )
        assert (
            v3.acceptance_fingerprint
            == "575e304da8203b537d281d82a667e73dbf419fc95caee8df82dea6e7feabfce7"
        )
        assert (
            v3.execution_fingerprint
            == "a4d8cdaaa4960ddf406c37703965d164595cea320cfa83c0ddd40fad797fa551"
        )
        assert v3.application_revision == "3320e556540d3f95bee1e8509f13e558ce266b6c"

    def test_import_assembly_verify_and_read_have_no_execution_or_write_side_effects(
        self, linked, tmp_path
    ):
        value = assemble(linked)
        root = publication_root(tmp_path)
        publish(linked, root, value)
        expected = retained_reference(value)
        before = source_bytes(linked), journal_tests.tree_bytes(Path(root.path))
        script = r"""
import json, os, sys
data = json.loads(sys.stdin.read())
def audit(event, args):
    if event.startswith("socket.") or event in {
        "subprocess.Popen", "os.system", "os.mkdir", "os.remove", "os.rename",
        "os.link", "os.symlink", "os.chmod", "os.truncate",
    }:
        raise RuntimeError("offline_readonly_violation")
    if event == "open" and isinstance(args[2], int) and args[2] & (
        os.O_CREAT | os.O_WRONLY | os.O_RDWR | os.O_TRUNC
    ):
        raise RuntimeError("filesystem_write_violation")
    if event == "sqlite3.connect" and "mode=ro" not in str(args[0]):
        raise RuntimeError("sqlite_write_violation")
sys.addaudithook(audit)
from harness.canary import envelope_v3 as e
from harness.canary import approval_v3, authority_v3, journal_v3
def forbidden(*args, **kwargs):
    raise RuntimeError("execution_or_authentication_violation")
approval_v3.verify_approval = forbidden
authority_v3.consume_approval = forbidden
authority_v3.initialize_store = forbidden
journal_v3.initialize_registry = forbidden
store = authority_v3.AuthorityStoreBinding.model_validate_json(data["store"])
registry = journal_v3.RegistryBinding.model_validate_json(data["registry"])
proposal = approval_v3.ProposedCanary.model_validate_json(data["proposal"])
expected = e.ExpectedEnvelopeReference.model_validate_json(data["expected"])
root = e.TrustedPublicationRoot.model_validate_json(data["root"])
raw = data["raw"].encode()
args = dict(payload=data["payload"].encode(), signature=data["signature"].encode(),
            expected_proposal=proposal, store=store, registry=registry)
observed = e.assemble_envelope(**args, run_id=expected.run_id)
assert e.serialize_envelope(observed) == raw
assert e.verify_envelope(raw, expected=expected).source_comparison == "not-performed"
assert e.verify_against_sources(raw, expected=expected, **args).source_comparison == "matches-reobserved-sources"
assert e.read_envelope(publication_root=root, publication_id="artifact", expected=expected).source_comparison == "not-performed"
print("read-only audit passed")
"""
        document = {
            "store": linked.store.model_dump_json(),
            "registry": linked.registry.model_dump_json(),
            "proposal": linked.proposal.model_dump_json(),
            "expected": expected.model_dump_json(),
            "root": root.model_dump_json(),
            "raw": envelope.serialize_envelope(value).decode(),
            "payload": linked.signed[0].decode(),
            "signature": linked.signed[1].decode(),
        }
        result = subprocess.run(
            [sys.executable, "-B", "-c", script],
            check=False,
            input=json.dumps(document),
            text=True,
            capture_output=True,
            timeout=30,
            env={
                "PATH": os.defpath,
                "PYTHONPATH": "src",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "read-only audit passed"
        assert (
            source_bytes(linked),
            journal_tests.tree_bytes(Path(root.path)),
        ) == before
