"""Scripted journal records only. No target, provider, judge or server calls."""

import copy
import os
import platform
import threading
from dataclasses import asdict, replace
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from test_canary_selection_v3 import selected

from harness.canary import journal_v3 as journal
from harness.canary.execution_policy import OperationalGuards
from harness.canary.inputs import TARGET_MODEL
from harness.canary.runtime_v3 import (
    APPLICATION_REVISION,
    V3,
    GitIdentity,
    RuntimeIdentity,
    SourceApprovalReceipt,
    resolve_definition,
)
from harness.canary.selection_v3 import ORDER
from harness.core.fingerprints import fingerprint


def receipt():
    return SourceApprovalReceipt(
        schema_id="canary-source-approval-v1",
        scope="source-only",
        approval_reference="synthetic:unit-test-only",
        provenance="synthetic-test",
        execution_profile="offline-verification-v1",
        harness=GitIdentity(commit="a" * 40, tree="b" * 40),
        application=GitIdentity(commit=APPLICATION_REVISION, tree="c" * 40),
        binding=resolve_definition(V3),
        harness_lock_sha256="d" * 64,
        application_lock_sha256="e" * 64,
        runtime=RuntimeIdentity(
            implementation="CPython",
            python=platform.python_version(),
            system=platform.system(),
            machine=platform.machine(),
            dependency_lock="harness",
        ),
    )


def ready(**changes):
    return replace(
        OperationalGuards(
            **{
                name: True
                for name, value in asdict(OperationalGuards()).items()
                if type(value) is bool
            }
        ),
        **changes,
    )


def envelope():
    return {
        "id": "resp_test",
        "model": TARGET_MODEL,
        "status": "completed",
        "usage": {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110},
        "output": [{"reasoning": "PRIVATE_PROVIDER_REASONING"}],
    }


def retry_failure(*, known_zero_usage=False):
    value = {"error": {"message": "PRIVATE_RETRY_DIAGNOSTIC"}}
    if known_zero_usage:
        value["usage"] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    return value


def test_driver_snapshot_observes_profile_without_appending_or_sharing_state(tmp_path):
    registry, writer = make(tmp_path)
    binding = writer.bind_provider(
        resolve_definition(V3),
        project_id="proj_synthetic",
        organization_id="org_synthetic",
    )
    before = tree_bytes(Path(registry.path))
    snapshot = writer.driver_snapshot(binding)
    assert snapshot.binding == binding and snapshot.decision is None
    assert snapshot.decision_sequence is None and snapshot.active_slot is None
    assert not snapshot.stopped and not snapshot.authorises_live_execution
    snapshot.accounting["logical_calls"] = 999
    snapshot.turn_accounting["A1"]["provider_attempts"] = 999
    snapshot.evidence["A1"] = {"chat": {"session_id": "forged"}}
    fresh = writer.driver_snapshot(binding)
    assert (
        fresh.accounting["logical_calls"]
        == fresh.turn_accounting["A1"]["provider_attempts"]
        == 0
    )
    assert not fresh.evidence and not fresh.completed_call_usage
    assert tree_bytes(Path(registry.path)) == before
    writer.close()


def test_driver_snapshot_decision_active_slot_public_evidence_and_final_usage(tmp_path):
    from datetime import UTC, datetime

    from test_canary_instrumentation_v3 import app_request, client_for, profiled

    from harness.canary.evidence_v3 import AttemptGuards
    from harness.canary.instrumentation_v3 import ProviderTransportV3

    _registry, writer, binding = profiled(tmp_path)
    active = writer.driver_snapshot(binding)
    assert active.decision.action == "ADVANCE" and active.decision.next_slot == "A1"
    assert active.active_slot == "A1" and active.decision_sequence == 2
    provider = ProviderTransportV3(
        writer,
        binding,
        httpx.MockTransport(lambda _: httpx.Response(200, json=envelope())),
        guards=lambda: AttemptGuards(
            checked_at=datetime.now(UTC).isoformat(),
            **{
                name: True
                for name, field in AttemptGuards.model_fields.items()
                if field.annotation is bool
            },
        ),
    )
    client_for(provider).create_response(app_request())
    value = selected("A1")
    writer.record_chat(value["chat"])
    writer.record_trace(value["trace"], reread=copy.deepcopy(value["trace"]))
    snapshot = writer.driver_snapshot(binding)
    assert snapshot.completed_call_usage == (
        {
            "slot": "A1",
            "logical_call": 1,
            "response_id": "resp_test",
            "input_tokens": 100,
            "output_tokens": 10,
            "total_tokens": 110,
        },
    )
    assert snapshot.turn_accounting["A1"]["logical_calls"] == 1
    assert snapshot.turn_accounting["B1"]["logical_calls"] == 0
    snapshot.evidence["A1"]["trace"]["resolved_constraints"]["colour"] = "forged"
    snapshot.completed_call_usage[0]["input_tokens"] = 0
    assert (
        writer.driver_snapshot(binding).evidence["A1"]["trace"]["resolved_constraints"][
            "colour"
        ]
        == "Moss"
    )
    assert (
        writer.driver_snapshot(binding).completed_call_usage[0]["input_tokens"] == 100
    )
    writer.assess_turn()
    writer.complete_turn()
    decision = writer.record_decision(ready())
    assert writer.driver_snapshot(binding).decision == decision
    writer.stop()
    stopped = writer.driver_snapshot(binding)
    assert stopped.stopped and stopped.decision.action == "ADVANCE"
    writer.close()
    with pytest.raises(journal.JournalError):
        writer.driver_snapshot(binding)


@pytest.mark.parametrize("change", ["run_id", "project_id", "definition", "extra"])
def test_driver_snapshot_binding_mismatch_is_terminal(tmp_path, change):
    registry, writer = make(tmp_path)
    binding = writer.bind_provider(
        resolve_definition(V3),
        project_id="proj_synthetic",
        organization_id="org_synthetic",
    )
    value = {
        "run_id": "other",
        "project_id": "proj_other",
        "definition": resolve_definition(),
        "extra": True,
    }[change]
    wrong = binding.model_copy(update={change: value})
    before = tree_bytes(Path(registry.path))
    with pytest.raises(journal.JournalError):
        writer.driver_snapshot(wrong)
    assert writer.provider_stopped and tree_bytes(Path(registry.path)) == before
    assert journal.inspect_run(registry, "run-1")["status"] == "incomplete"


def test_driver_snapshot_cannot_upgrade_an_unprofiled_slice2_journal(tmp_path):
    registry, writer = make(tmp_path)
    binding = journal.ProviderBinding(
        definition=resolve_definition(V3),
        registry_id=registry.registry_id,
        run_id="run-1",
        source_receipt_sha256=fingerprint(receipt().model_dump(mode="json")),
        project_id="proj_synthetic",
        organization_id="org_synthetic",
    )
    before = tree_bytes(Path(registry.path))
    with pytest.raises(journal.JournalError):
        writer.driver_snapshot(binding)
    assert writer.provider_stopped and tree_bytes(Path(registry.path)) == before
    report = journal.inspect_run(registry, "run-1")
    assert "instrumentation_profile" not in report
    assert len(report["records"]) == 1


def test_historical_500_500_200_is_representable_and_keeps_unknown_billing(tmp_path):
    from harness.canary.recording import CanaryError, CanaryStore, ProviderTransport

    replies = iter([retry_failure(), retry_failure(), envelope()])
    historical = CanaryStore(tmp_path / "salesagent-preflight-canary" / "historical")
    provider = ProviderTransport(
        historical,
        httpx.MockTransport(
            lambda _: httpx.Response(
                500 if historical.accounting()["attempts"] < 3 else 200,
                json=next(replies),
            )
        ),
        role="target",
    )
    request = httpx.Request(
        "POST",
        "https://api.openai.com/v1/responses",
        json={"model": TARGET_MODEL, "max_output_tokens": 2000, "input": "synthetic"},
    )
    with provider.logical("A1"):
        for _ in range(3):
            provider.handle_request(request)
    assert historical.accounting()["attempts"] == 3
    assert historical.accounting()["unknown_attempts"] == 2
    with pytest.raises(CanaryError), provider.logical("A1", 2):
        pytest.fail("Unknown billing must block another logical call")
    provider.close()

    binding, writer = make(tmp_path)
    writer.record_decision(ready())
    writer.reserve_turn("A1")
    writer.reserve_call(1)
    for attempt, status in enumerate((500, 500, 200), 1):
        writer.record_dispatch(1, attempt)
        writer.record_provider_result(
            1,
            attempt,
            envelope() if status == 200 else retry_failure(),
            http_status=status,
        )
    writer.complete_call(1)
    writer.close()
    report = journal.inspect_run(binding, "run-1")
    assert report["accounting"]["provider_attempts"] == 3
    assert report["accounting"]["unknown_attempts"] == 2


def make(tmp_path, run_id="run-1", approval_id="synthetic-approval-1"):
    binding = journal.initialize_registry(tmp_path / "v3-registry")
    writer = journal.CanaryJournal(
        binding, run_id, approval_id, source_receipt=receipt()
    )
    return binding, writer


def turn(writer, slot, *, fail=False, error=False, usage_unknown=False, attempts=1):
    writer.reserve_turn(slot)
    writer.reserve_call(1)
    for attempt in range(1, attempts + 1):
        writer.record_dispatch(1, attempt)
        observed = (
            envelope() if attempt == attempts else retry_failure(known_zero_usage=True)
        )
        if usage_unknown:
            observed.pop("usage")
        writer.record_provider_result(
            1,
            attempt,
            observed,
            http_status=200 if attempt == attempts else 500,
            request_id="req_test",
        )
    writer.complete_call(1)
    raw = selected(slot)
    if fail:
        raw["trace"]["resolved_constraints"]["maximum_price"] = "1.00"
    if error:
        raw["trace"]["errors"] = [
            {"code": "unknown_tool", "message": "PRIVATE_UNKNOWN_ERROR"}
        ]
    writer.record_chat(raw["chat"])
    writer.record_trace(raw["trace"], reread=copy.deepcopy(raw["trace"]))
    report = writer.assess_turn()
    writer.complete_turn()
    return report


def complete(writer, *, fail_at=None, seal=True, shutdown=True):
    for slot in ORDER:
        assert writer.record_decision(ready()).next_slot == slot
        turn(writer, slot, fail=slot == fail_at)
    decision = writer.record_decision(ready())
    assert decision.action == "COMPLETE"
    if shutdown:
        writer.record_shutdown(
            worker_stopped=True, sdk_closed=True, no_inflight_provider=True
        )
    if seal:
        writer.seal()
    return decision


def tree_bytes(path):
    return {
        str(p.relative_to(path)): (p.read_bytes(), p.stat().st_mode & 0o777)
        for p in path.rglob("*")
        if p.is_file()
    }


def test_finalization_accepted_stop_is_durable_before_admission(tmp_path):
    registry, writer = make(tmp_path)
    complete(writer, seal=False)
    for _ in range(2):
        assert writer.stop() == "accepted"
    with pytest.raises(
        journal.JournalError, match="finalization_failed_preserve_evidence"
    ):
        writer.seal()
    assert writer.provider_stopped
    report = journal.inspect_run(registry, "run-1")
    assert not report["completion_seal_present"]
    assert [r["kind"] for r in report["records"]].count("stop") == 2


def test_finalization_request_before_mutex_acquisition_blocks_admission(
    tmp_path, monkeypatch
):
    registry, writer = make(tmp_path)
    complete(writer, seal=False)
    mutex = writer._mutex
    waiting, release_stop = threading.Event(), threading.Event()
    errors = []

    def stop():
        try:
            writer.stop()
        except journal.JournalError:
            errors.append("stop_unaccepted")

    stopper = threading.Thread(target=stop)

    class Mutex:
        def __enter__(self):
            if threading.current_thread() is stopper:
                waiting.set()
                assert release_stop.wait(10)
            return mutex.__enter__()

        def __exit__(self, *args):
            return mutex.__exit__(*args)

    monkeypatch.setattr(writer, "_mutex", Mutex())

    def seal():
        try:
            writer.seal()
        except journal.JournalError:
            errors.append("seal_denied")

    caller = threading.Thread(target=seal)
    try:
        with mutex:
            # Neither operation can acquire the journal mutex. Stop's genuine
            # latch still closes, independently of which recorder is scheduled.
            caller.start()
            stopper.start()
            assert waiting.wait(10) and writer.provider_stopped
        caller.join(10)
    finally:
        release_stop.set()
        caller.join(10)
        stopper.join(10)
        writer.close()
    assert not caller.is_alive() and not stopper.is_alive()
    assert sorted(errors) == ["seal_denied", "stop_unaccepted"]
    report = journal.inspect_run(registry, "run-1")
    assert not report["completion_seal_present"]
    assert not any(r["kind"] == "stop" for r in report["records"])


def test_finalization_holds_mutex_through_publication_and_concurrent_late_stops(
    tmp_path, monkeypatch
):
    registry, writer = make(tmp_path)
    complete(writer, seal=False)
    publishing, release, waiting = (
        threading.Event(),
        threading.Event(),
        [threading.Event() for _ in range(4)],
    )
    results, errors = [], []
    mutex, publish = writer._mutex, journal._publish
    stops = []

    def stop():
        try:
            results.append(writer.stop())
        except BaseException as error:  # noqa: BLE001 - fixed thread diagnostics
            errors.append(type(error).__name__)

    stops.extend(threading.Thread(target=stop) for _ in waiting)

    class Mutex:
        def __enter__(self):
            thread = threading.current_thread()
            if thread in stops:
                waiting[stops.index(thread)].set()
            return mutex.__enter__()

        def __exit__(self, *args):
            return mutex.__exit__(*args)

    def blocked(directory, name, value):
        publish(directory, name, value)
        if value.get("kind") == "completion":
            publishing.set()
            assert release.wait(10)

    def seal():
        try:
            writer.seal()
        except BaseException as error:  # noqa: BLE001 - fixed thread diagnostics
            errors.append(type(error).__name__)

    monkeypatch.setattr(writer, "_mutex", Mutex())
    monkeypatch.setattr(journal, "_publish", blocked)
    caller = threading.Thread(target=seal)
    caller.start()
    try:
        assert publishing.wait(10) and writer.provider_stopped
        for thread in stops:
            thread.start()
        assert all(event.wait(10) for event in waiting)
        assert results == []  # Every stop is still waiting for the held mutex.
    finally:
        release.set()
        caller.join(10)
        for thread in stops:
            if thread.ident is not None:
                thread.join(10)
        writer.close()
    assert not caller.is_alive() and all(not t.is_alive() for t in stops)
    assert errors == [] and results == ["late"] * 4
    report = journal.inspect_run(registry, "run-1")
    assert report["completion_certified"]
    assert not any(r["kind"] == "stop" for r in report["records"])
    before = tree_bytes(Path(registry.path))
    assert writer.stop() == "late"
    journal.recover_save_only(registry, "run-1", tmp_path / "saved")
    assert tree_bytes(Path(registry.path)) == before


@pytest.mark.parametrize("invalid", ["binding", "code", None])
def test_finalization_late_provider_stop_validates_binding_and_never_appends(
    tmp_path, invalid
):
    from test_canary_driver_v3 import composition, run

    c = composition(tmp_path)
    assert run(c)["completion_certified"]
    before = tree_bytes(Path(c.registry.path))
    binding = (
        c.binding.model_copy(update={"run_id": "different"})
        if invalid == "binding"
        else c.binding
    )
    code = "PRIVATE_INVALID_STOP" if invalid == "code" else "operator_stop"
    if invalid:
        with pytest.raises(journal.JournalError) as error:
            c.writer.request_provider_stop(binding, code)
        assert "PRIVATE" not in str(error.value)
    else:
        for _ in range(2):
            assert c.writer.request_provider_stop(binding, code) == "late"
    assert c.writer.provider_stopped
    assert tree_bytes(Path(c.registry.path)) == before


@pytest.mark.parametrize("point", ["manifest_only", "missing_shutdown", "closed"])
def test_finalization_invalid_or_repeated_attempt_is_permanently_closed(
    tmp_path, point
):
    registry, writer = make(tmp_path)
    if point == "missing_shutdown":
        complete(writer, seal=False, shutdown=False)
    if point == "closed":
        writer.close()
    for _ in range(2):
        with pytest.raises(
            journal.JournalError, match="finalization_failed_preserve_evidence"
        ):
            writer.seal()
        assert writer.provider_stopped
    report = journal.inspect_run(registry, "run-1")
    assert not report["completion_certified"]


@pytest.mark.parametrize("entry", ["public", "provider"])
def test_finalization_reentrant_stop_is_latched_but_not_accepted(
    tmp_path, monkeypatch, entry
):
    from test_canary_driver_v3 import composition, run

    c = composition(tmp_path)
    original = journal._publish
    pending = []

    def publish(directory, name, value):
        if value.get("kind") == "completion":
            with pytest.raises(journal.JournalError, match="stop_acceptance_pending"):
                if entry == "public":
                    c.writer.stop()
                else:
                    c.writer.request_provider_stop(c.binding, "operator_stop")
            pending.append(c.writer.provider_stopped)
        original(directory, name, value)

    monkeypatch.setattr(journal, "_publish", publish)
    report = run(c)
    assert pending == [True]
    assert (
        report["completion_certified"]
        and not report["instrumentation_terminal_stop_recorded"]
    )
    assert c.writer.stop() == "late"


@pytest.mark.parametrize("failure", [OSError, KeyboardInterrupt])
def test_finalization_close_failure_is_private_and_cannot_report_late(
    tmp_path, monkeypatch, failure
):
    registry, writer = make(tmp_path)
    complete(writer, seal=False)
    close = writer.close

    def fail():
        close()  # Release real test descriptors even when the observation fails.
        raise failure("PRIVATE_FINALIZATION_CLOSE")

    with monkeypatch.context() as patch:
        patch.setattr(writer, "close", fail)
        with pytest.raises(journal.JournalError) as error:
            writer.seal()
    assert str(error.value) == "finalization_failed_preserve_evidence"
    assert writer.provider_stopped
    report = journal.inspect_run(registry, "run-1")
    # Durable acknowledgement is unchanged, but local closure did not succeed.
    assert report["completion_certified"]
    before = tree_bytes(Path(registry.path))
    with pytest.raises(journal.JournalError):
        writer.stop()
    assert tree_bytes(Path(registry.path)) == before


def test_finalization_reentrant_stop_during_closure_cannot_accept_or_append(
    tmp_path, monkeypatch
):
    registry, writer = make(tmp_path)
    complete(writer, seal=False)
    close = writer.close
    pending = []

    def observed_close():
        with pytest.raises(journal.JournalError, match="stop_acceptance_pending"):
            writer.stop()
        pending.append(writer.provider_stopped)
        close()

    with monkeypatch.context() as patch:
        patch.setattr(writer, "close", observed_close)
        writer.seal()
    assert pending == [True]
    assert writer.stop() == "late"
    report = journal.inspect_run(registry, "run-1")
    assert report["completion_certified"]
    assert not any(r["kind"] == "stop" for r in report["records"])


@pytest.mark.parametrize("fail_at", [None, "A1", "B1", "A2", "B2"])
def test_complete_runs_preserve_fail_or_pending_review_and_export_only(
    tmp_path, fail_at
):
    binding, writer = make(tmp_path)
    decision = complete(writer, fail_at=fail_at)
    before = tree_bytes(Path(binding.path))
    report = journal.inspect_run(binding, "run-1")
    assert report["status"] == "completed"
    assert report["structurally_validated"] and report["accounting_reconciled"]
    assert report["accounting"]["logical_calls"] == 4
    assert report["accounting"]["provider_attempts"] == 4
    assert report["assessment"]["status"] == ("FAIL" if fail_at else "SKIP")
    assert report["human_review"] == "PENDING"
    assert (
        report["mechanical_assessment"]["status"]
        == decision.mechanical_assessment.status
    )
    assert not report["source_authorised"]
    assert not report["provider_evidence_authenticated"]
    assert not report["authorises_live_execution"]
    output = tmp_path / "export"
    assert journal.recover_save_only(binding, "run-1", output) == report
    assert tree_bytes(Path(binding.path)) == before
    assert output.stat().st_mode & 0o777 == 0o700
    assert (output / "report.json").stat().st_mode & 0o777 == 0o600
    assert "PRIVATE" not in (output / "report.json").read_text()
    with pytest.raises(journal.JournalError):
        journal.recover_save_only(binding, "run-1", output)


def test_registry_roundtrip_private_namespace_and_permanent_claims(tmp_path):
    binding, writer = make(tmp_path)
    assert journal.load_registry(Path(binding.path)) == binding
    writer.close()
    with pytest.raises(journal.JournalError):
        journal.CanaryJournal(
            binding, "run-1", "new-approval", source_receipt=receipt()
        )
    with pytest.raises(journal.JournalError):
        journal.CanaryJournal(
            binding, "new-run", "synthetic-approval-1", source_receipt=receipt()
        )
    assert (Path(binding.path) / "runs/new-run").is_dir()
    with pytest.raises(journal.JournalError):
        journal.initialize_registry(Path(binding.path))
    for p in Path(binding.path).rglob("*"):
        assert p.stat().st_uid == os.getuid()
        assert p.stat().st_mode & 0o777 == (0o700 if p.is_dir() else 0o600)


@pytest.mark.parametrize("name", ["salesagent-study-v1", "salesagent-preflight-canary"])
def test_registry_cannot_use_study_or_historical_storage(tmp_path, name):
    parent = tmp_path / name
    parent.mkdir()
    with pytest.raises(journal.JournalError):
        journal.initialize_registry(parent / "new")


@pytest.mark.parametrize("slot", ["B1", "A2", "B2", "A1/../B1"])
def test_only_durable_policy_next_slot_can_be_reserved(tmp_path, slot):
    binding, writer = make(tmp_path)
    assert writer.record_decision(ready()).next_slot == "A1"
    with pytest.raises(journal.JournalError):
        writer.reserve_turn(slot)
    assert journal.inspect_run(binding, "run-1")["persisted_records"] == 2


def test_no_reservation_without_decision_and_no_duplicate_turn(tmp_path):
    _, writer = make(tmp_path)
    with pytest.raises(journal.JournalError):
        writer.reserve_turn("A1")
    binding = journal.load_registry(tmp_path / "v3-registry")
    writer = journal.CanaryJournal(
        binding, "other-run", "other-approval", source_receipt=receipt()
    )
    writer.record_decision(ready())
    turn(writer, "A1")
    writer.record_decision(ready())
    with pytest.raises(journal.JournalError):
        writer.reserve_turn("A1")


@pytest.mark.parametrize("slot", ORDER)
def test_operational_evidence_error_stops_at_every_position(tmp_path, slot):
    binding, writer = make(tmp_path)
    for current in ORDER:
        writer.record_decision(ready())
        turn(writer, current, error=current == slot)
        if current == slot:
            break
    decision = writer.record_decision(ready())
    assert decision.action == "STOP" and decision.assessment.status == "ERROR"
    assert writer.record_decision(ready()).action == "STOP"
    writer.record_shutdown(
        worker_stopped=True, sdk_closed=True, no_inflight_provider=True
    )
    writer.close()
    report = journal.inspect_run(binding, "run-1")
    assert report["status"] == "incomplete" and report["execution_action"] == "STOP"
    assert "PRIVATE" not in str(report)


@pytest.mark.parametrize(
    "reason", ["unknown_usage", "unresolved", "uncompleted_call", "provider_error"]
)
def test_unknown_liability_overrides_claimed_ready_guards(tmp_path, reason):
    binding, writer = make(tmp_path)
    writer.record_decision(ready())
    writer.reserve_turn("A1")
    writer.reserve_call(1)
    writer.record_dispatch(1, 1)
    if reason != "unresolved":
        value = envelope()
        if reason == "unknown_usage":
            value.pop("usage")
        if reason == "provider_error":
            value["status"] = "incomplete"
        writer.record_provider_result(1, 1, value, http_status=200)
    if reason not in {"unresolved", "uncompleted_call"}:
        writer.complete_call(1)
    raw = selected()
    writer.record_chat(raw["chat"])
    writer.record_trace(raw["trace"], reread=raw["trace"])
    writer.assess_turn()
    writer.complete_turn()
    decision = writer.record_decision(ready())
    assert decision.action == "STOP"
    assert decision.operational_assessment.status == "ERROR"
    writer.close()
    report = journal.inspect_run(binding, "run-1")
    assert report["status"] == "operationally_uncertain"
    assert not report["accounting_reconciled"]
    assert (
        report["accounting"]["estimated_total_usd"] is None
        if reason in {"unknown_usage", "unresolved"}
        else True
    )


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate_dispatch",
        "duplicate_result",
        "orphan_result",
        "fourth_attempt",
        "second_call_without_first",
        "duplicate_call",
    ],
)
def test_invalid_provider_identities_are_terminal(tmp_path, fault):
    binding, writer = make(tmp_path)
    writer.record_decision(ready())
    writer.reserve_turn("A1")
    if fault == "second_call_without_first":
        operation = lambda: writer.reserve_call(2)
    else:
        writer.reserve_call(1)
        if fault == "duplicate_call":
            operation = lambda: writer.reserve_call(1)
        elif fault == "orphan_result":
            operation = lambda: writer.record_provider_result(
                1, 1, envelope(), http_status=200
            )
        else:
            writer.record_dispatch(1, 1)
            if fault == "duplicate_dispatch":
                operation = lambda: writer.record_dispatch(1, 1)
            else:
                writer.record_provider_result(1, 1, envelope(), http_status=200)
                operation = lambda: writer.record_provider_result(
                    1, 1, envelope(), http_status=200
                )
                if fault == "fourth_attempt":
                    operation = lambda: writer.record_dispatch(1, 4)
    with pytest.raises(journal.JournalError):
        operation()
    with pytest.raises(journal.JournalError):
        writer.reserve_call(1)
    assert journal.inspect_run(binding, "run-1")["missing_completion_seal"]


def test_attempt_counts_and_assessment_revisions_are_independently_preserved(tmp_path):
    binding, writer = make(tmp_path)
    writer.record_decision(ready())
    writer.reserve_turn("A1")
    for number in (1, 2):
        writer.reserve_call(number)
        for attempt in (1, 2, 3):
            writer.record_dispatch(number, attempt)
            writer.record_provider_result(
                number,
                attempt,
                envelope() if attempt == 3 else retry_failure(known_zero_usage=True),
                http_status=200 if attempt == 3 else 500,
            )
        writer.complete_call(number)
    raw = selected()
    writer.record_chat(raw["chat"])
    writer.record_trace(raw["trace"], reread=raw["trace"])
    assert writer.assess_turn() == writer.assess_turn()
    writer.complete_turn()
    assert writer.record_decision(ready()).action == "ADVANCE"
    writer.close()
    report = journal.inspect_run(binding, "run-1")
    assert report["accounting"]["provider_attempts"] == 6
    assert report["accounting"]["logical_calls"] == 2
    assert report["accounting"]["retryable_http_failures"] == 4
    assert report["accounting"]["operational_errors"] == 0
    assert report["accounting_reconciled"]
    revisions = [r for r in report["records"] if r["kind"] == "assessment"]
    assert [r["payload"]["revision"] for r in revisions] == [0, 1]


@pytest.mark.parametrize("cost", [Decimal(5), Decimal("NaN"), Decimal(-1)])
def test_supplied_additional_cost_cannot_be_reduced_by_local_accounting(tmp_path, cost):
    _, writer = make(tmp_path)
    assert writer.record_decision(ready(estimated_total_usd=cost)).action == "STOP"
    writer.close()


@pytest.mark.parametrize("shutdown", [False, True])
def test_missing_seal_is_reported_and_never_repaired(tmp_path, shutdown):
    binding, writer = make(tmp_path)
    complete(writer, seal=False, shutdown=shutdown)
    writer.close()
    before = tree_bytes(Path(binding.path))
    report = journal.recover_save_only(binding, "run-1", tmp_path / "saved")
    assert report["status"] == "incomplete"
    assert report["execution_action"] == "COMPLETE"
    assert report["missing_completion_seal"]
    assert tree_bytes(Path(binding.path)) == before


def test_completion_requires_explicit_safe_shutdown(tmp_path):
    binding, writer = make(tmp_path)
    complete(writer, seal=False, shutdown=False)
    writer.record_shutdown(
        worker_stopped=False, sdk_closed=True, no_inflight_provider=True
    )
    with pytest.raises(journal.JournalError):
        writer.seal()
    assert journal.inspect_run(binding, "run-1")["status"] == "operationally_uncertain"


def test_inspection_and_recovery_refuse_active_writer(tmp_path):
    binding, writer = make(tmp_path)
    before = tree_bytes(Path(binding.path))
    for operation in (
        lambda: journal.inspect_run(binding, "run-1"),
        lambda: journal.recover_save_only(binding, "run-1", tmp_path / "saved"),
    ):
        with pytest.raises(journal.JournalError, match="busy"):
            operation()
    writer.close()
    assert tree_bytes(Path(binding.path)) == before


@pytest.mark.parametrize("invalid", ["", "../run", ".", "..", "run/a", "x" * 129])
def test_invalid_identities_rejected_before_claims(tmp_path, invalid):
    binding = journal.initialize_registry(tmp_path / "v3")
    with pytest.raises(journal.JournalError):
        journal.CanaryJournal(binding, invalid, "valid", source_receipt=receipt())
    assert list((Path(binding.path) / "runs").iterdir()) == []


def test_export_cannot_write_back_into_registry(tmp_path):
    binding, writer = make(tmp_path)
    writer.close()
    before = tree_bytes(Path(binding.path))
    with pytest.raises(journal.JournalError):
        journal.recover_save_only(binding, "run-1", Path(binding.path) / "export")
    assert tree_bytes(Path(binding.path)) == before


def test_forged_provenance_does_not_change_authority(tmp_path):
    binding = journal.initialize_registry(tmp_path / "v3")
    claim = receipt().model_copy(update={"provenance": "external-review"})
    writer = journal.CanaryJournal(binding, "run", "approval", source_receipt=claim)
    writer.close()
    report = journal.inspect_run(binding, "run")
    assert (
        report["records"][0]["payload"]["source_receipt"]["provenance"]
        == "external-review"
    )
    assert report["source_authorised"] is report["authorises_live_execution"] is False


def test_invalid_trace_reread_is_operational_error_and_preserves_chat(tmp_path):
    binding, writer = make(tmp_path)
    writer.record_decision(ready())
    writer.reserve_turn("A1")
    raw = selected()
    writer.record_chat(raw["chat"])
    other = copy.deepcopy(raw["trace"])
    other["trace_id"] = "different"
    writer.record_trace(raw["trace"], reread=other)
    assert writer.assess_turn()["prerequisites"]["status"] == "ERROR"
    writer.complete_turn()
    assert writer.record_decision(ready()).action == "STOP"
    writer.close()
    report = journal.inspect_run(binding, "run-1")
    assert any(r["kind"] == "chat" for r in report["records"])
    assert not any(r["kind"] == "trace" for r in report["records"])


def test_claim_hash_names_do_not_establish_authentication(tmp_path):
    binding, writer = make(tmp_path)
    writer.close()
    claim = (
        Path(binding.path)
        / "approvals"
        / (fingerprint("synthetic-approval-1") + ".json")
    )
    assert claim.exists()
    assert (
        journal.inspect_run(binding, "run-1")["provider_evidence_authenticated"]
        is False
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("safety_ok", 1),
        ("logical_calls", True),
        ("provider_attempts", -1),
        ("estimated_total_usd", "PRIVATE"),
    ],
)
def test_malformed_guards_close_writer_and_do_not_echo_values(tmp_path, field, value):
    binding, writer = make(tmp_path)
    with pytest.raises(journal.JournalError) as caught:
        writer.record_decision(ready(**{field: value}))
    assert "PRIVATE" not in str(caught.value)
    with pytest.raises(journal.JournalError):
        writer.record_decision(ready())
    assert journal.inspect_run(binding, "run-1")["persisted_records"] == 1


def test_saved_over_budget_usage_stops_policy_and_remains_visible(tmp_path):
    binding, writer = make(tmp_path)
    writer.record_decision(ready())
    writer.reserve_turn("A1")
    writer.reserve_call(1)
    writer.record_dispatch(1, 1)
    raw = envelope()
    raw["usage"] = {
        "input_tokens": 1000000,
        "output_tokens": 1000000,
        "total_tokens": 2000000,
    }
    writer.record_provider_result(1, 1, raw, http_status=200)
    writer.complete_call(1)
    public = selected()
    writer.record_chat(public["chat"])
    writer.record_trace(public["trace"], reread=public["trace"])
    writer.assess_turn()
    writer.complete_turn()
    assert writer.record_decision(ready()).action == "STOP"
    writer.close()
    report = journal.inspect_run(binding, "run-1")
    assert Decimal(report["accounting"]["estimated_total_usd"]) >= 5
    assert report["operational_assessment"]["status"] == "ERROR"


def spending_envelope(input_tokens, *, retryable=False):
    raw = retry_failure() if retryable else envelope()
    # Frozen conservative long-context pricing: $5 for one million input tokens.
    raw["usage"] = {
        "input_tokens": input_tokens,
        "output_tokens": 0,
        "total_tokens": input_tokens,
    }
    return raw


@pytest.mark.parametrize("boundary", ["next_call", "retry"])
@pytest.mark.parametrize(
    "input_tokens,subtotal,paused",
    [
        (999999, "4.999995", False),
        (1000000, "5", True),
        (1000001, "5.000005", True),
    ],
)
def test_known_spending_pause_at_reservation_boundaries(
    tmp_path, boundary, input_tokens, subtotal, paused
):
    binding, writer = retry_writer(tmp_path)
    writer.record_dispatch(1, 1)
    retryable = boundary == "retry"
    writer.record_provider_result(
        1,
        1,
        spending_envelope(input_tokens, retryable=retryable),
        http_status=500 if retryable else 200,
    )
    if not retryable:
        writer.complete_call(1)
    before = tree_bytes(Path(binding.path))
    if paused:
        with pytest.raises(journal.JournalError):
            if retryable:
                writer.record_dispatch(1, 2)
            else:
                writer.reserve_call(2)
        # A rejected reservation closes the whole producer, even for safe records.
        with pytest.raises(journal.JournalError):
            writer.stop()
        assert tree_bytes(Path(binding.path)) == before
    else:
        if retryable:
            writer.record_dispatch(1, 2)
        else:
            writer.reserve_call(2)
            writer.record_dispatch(2, 1)
        writer.close()
    report = journal.inspect_run(binding, "run-1")
    assert report["structurally_validated"]
    assert Decimal(report["accounting"]["estimated_subtotal_usd"]) == Decimal(subtotal)
    assert report["accounting"]["provider_attempts"] == (1 if paused else 2)
    results = [r for r in report["records"] if r["kind"] == "provider_result"]
    assert len(results) == 1
    observed = results[0]["payload"]["observation"]
    assert Decimal(observed["estimated_usd"]) == Decimal(subtotal)
    assert observed["outcome"] == (
        "retryable_http_failure" if retryable else "completed"
    )
    assert report["accounting"]["unknown_attempts"] == (0 if paused else 1)


@pytest.mark.parametrize("input_tokens", [999999, 1000000, 1000001])
def test_known_spending_pause_uses_subtotal_despite_unknown_retry_liability(
    tmp_path, input_tokens
):
    binding, writer = retry_writer(tmp_path)
    writer.record_dispatch(1, 1)
    writer.record_provider_result(1, 1, retry_failure(), http_status=500)
    writer.record_dispatch(1, 2)
    writer.record_provider_result(
        1, 2, spending_envelope(input_tokens, retryable=True), http_status=500
    )
    if input_tokens >= 1000000:
        before = tree_bytes(Path(binding.path))
        with pytest.raises(journal.JournalError):
            writer.record_dispatch(1, 3)
        with pytest.raises(journal.JournalError):
            writer.stop()
        assert tree_bytes(Path(binding.path)) == before
    else:
        writer.record_dispatch(1, 3)
        raw = envelope()
        raw["usage"] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        writer.record_provider_result(1, 3, raw, http_status=200)
        writer.complete_call(1)
        with pytest.raises(journal.JournalError):
            writer.reserve_call(2)  # Success cannot erase attempt 1's liability.
    report = journal.inspect_run(binding, "run-1")
    assert report["structurally_validated"]
    assert report["accounting"]["estimated_total_usd"] is None
    assert report["accounting"]["unknown_attempts"] == 1
    assert Decimal(report["accounting"]["estimated_subtotal_usd"]) == (
        Decimal(input_tokens) * Decimal("0.000005")
    )
    assert report["accounting"]["provider_attempts"] == (
        2 if input_tokens >= 1000000 else 3
    )


@pytest.mark.parametrize("boundary", ["next_call", "retry", "later_turn"])
def test_known_spending_pause_accumulates_all_recorded_attempts(tmp_path, boundary):
    binding, writer = retry_writer(tmp_path)
    for number in (1, 2):
        retryable = boundary == "retry"
        if number == 2 and not retryable:
            if boundary == "later_turn":
                finish_evidence(writer)
                assert writer.record_decision(ready()).next_slot == "B1"
                writer.reserve_turn("B1")
                writer.reserve_call(1)
            else:
                writer.reserve_call(2)
        logical_call = number if boundary == "next_call" else 1
        attempt = number if retryable else 1
        writer.record_dispatch(logical_call, attempt)
        writer.record_provider_result(
            logical_call,
            attempt,
            spending_envelope(500000, retryable=retryable),
            http_status=500 if retryable else 200,
        )
        if not retryable:
            writer.complete_call(logical_call)
    before = tree_bytes(Path(binding.path))
    with pytest.raises(journal.JournalError):
        if boundary == "retry":
            writer.record_dispatch(1, 3)
        else:
            writer.reserve_call(2 if boundary == "later_turn" else 3)
    with pytest.raises(journal.JournalError):
        writer.stop()
    assert tree_bytes(Path(binding.path)) == before
    report = journal.inspect_run(binding, "run-1")
    assert report["structurally_validated"]
    assert report["accounting"]["provider_attempts"] == 2
    assert report["accounting"]["unknown_attempts"] == 0
    assert Decimal(report["accounting"]["estimated_subtotal_usd"]) == 5


def test_external_unknown_liability_still_stops_with_empty_local_ledger(tmp_path):
    _, writer = make(tmp_path)
    assert writer.record_decision(ready(unknown_attempts=1)).action == "STOP"
    writer.close()


def retry_writer(tmp_path):
    binding, writer = make(tmp_path)
    writer.record_decision(ready())
    writer.reserve_turn("A1")
    writer.reserve_call(1)
    return binding, writer


def finish_evidence(writer):
    raw = selected()
    writer.record_chat(raw["chat"])
    writer.record_trace(raw["trace"], reread=raw["trace"])
    writer.assess_turn()
    writer.complete_turn()


@pytest.mark.parametrize("known_zero_usage", [False, True])
@pytest.mark.parametrize("boundary", ["next_call", "next_turn"])
def test_retry_completion_preserves_billing_boundary_and_pure_policy(
    tmp_path, known_zero_usage, boundary
):
    binding, writer = retry_writer(tmp_path)
    writer.record_dispatch(1, 1)
    writer.record_provider_result(
        1, 1, retry_failure(known_zero_usage=known_zero_usage), http_status=500
    )
    writer.record_dispatch(1, 2)
    writer.record_provider_result(1, 2, envelope(), http_status=200)
    writer.complete_call(1)
    if boundary == "next_call":
        if known_zero_usage:
            writer.reserve_call(2)
        else:
            with pytest.raises(journal.JournalError):
                writer.reserve_call(2)
    else:
        finish_evidence(writer)
        decision = writer.record_decision(ready())
        assert decision.action == ("ADVANCE" if known_zero_usage else "STOP")
        if known_zero_usage:
            assert decision.next_slot == "B1"
            writer.reserve_turn("B1")
        else:
            assert decision.operational_assessment.status == "ERROR"
            with pytest.raises(journal.JournalError):
                writer.reserve_turn("B1")
    writer.close()
    report = journal.inspect_run(binding, "run-1")
    assert report["accounting"]["provider_attempts"] == 2
    assert report["accounting"]["retryable_http_failures"] == 1
    assert report["accounting"]["operational_errors"] == 0
    assert report["accounting"]["unknown_attempts"] == (0 if known_zero_usage else 1)
    assert (report["accounting"]["estimated_total_usd"] is None) is not known_zero_usage
    assert "PRIVATE_RETRY_DIAGNOSTIC" not in str(report)


@pytest.mark.parametrize("unknown_usage", [False, True])
def test_no_retry_after_success_even_before_logical_call_completion(
    tmp_path, unknown_usage
):
    binding, writer = retry_writer(tmp_path)
    writer.record_dispatch(1, 1)
    success = envelope()
    if unknown_usage:
        success.pop("usage")
    writer.record_provider_result(1, 1, success, http_status=200)
    with pytest.raises(journal.JournalError):
        writer.record_dispatch(1, 2)
    assert journal.inspect_run(binding, "run-1")["accounting"]["provider_attempts"] == 1


@pytest.mark.parametrize("record_ambiguous_result", [False, True])
def test_no_retry_after_ambiguous_attempt(tmp_path, record_ambiguous_result):
    binding, writer = retry_writer(tmp_path)
    writer.record_dispatch(1, 1)
    if record_ambiguous_result:
        writer.record_provider_result(1, 1, None)
    with pytest.raises(journal.JournalError):
        writer.record_dispatch(1, 2)
    report = journal.inspect_run(binding, "run-1")
    assert report["accounting"]["provider_attempts"] == 1
    assert report["accounting"]["unknown_attempts"] == 1


@pytest.mark.parametrize(
    "code",
    [
        "project_spend_limit_exceeded",
        "organization_spend_limit_exceeded",
        "organization_usage_limit_exceeded",
        "credit_balance_exhausted",
        "insufficient_quota",
        "invalid_api_key",
        "PRIVATE_UNREVIEWED_CODE",
    ],
)
@pytest.mark.parametrize("status", [429, 500])
def test_billing_authentication_and_unknown_errors_cannot_retry(tmp_path, code, status):
    binding, writer = retry_writer(tmp_path)
    writer.record_dispatch(1, 1)
    writer.record_provider_result(
        1,
        1,
        {"error": {"code": code, "message": "PRIVATE_MESSAGE"}},
        http_status=status,
        should_retry_header="true",
    )
    with pytest.raises(journal.JournalError):
        writer.record_dispatch(1, 2)
    report = journal.inspect_run(binding, "run-1")
    assert report["accounting"]["operational_errors"] == 1
    assert report["accounting"]["provider_attempts"] == 1
    assert "PRIVATE" not in str(report)


def test_fourth_attempt_rejected_after_three_eligible_failures(tmp_path):
    binding, writer = retry_writer(tmp_path)
    for attempt in (1, 2, 3):
        writer.record_dispatch(1, attempt)
        writer.record_provider_result(1, attempt, retry_failure(), http_status=500)
    with pytest.raises(journal.JournalError):
        writer.record_dispatch(1, 4)
    report = journal.inspect_run(binding, "run-1")
    assert report["accounting"]["provider_attempts"] == 3
    assert report["accounting"]["unknown_attempts"] == 3


@pytest.mark.parametrize("wrong", ["logical_call", "slot"])
def test_retry_cannot_change_reserved_call_or_slot(tmp_path, wrong):
    binding, writer = retry_writer(tmp_path)
    writer.record_dispatch(1, 1)
    writer.record_provider_result(1, 1, retry_failure(), http_status=500)
    with pytest.raises(journal.JournalError):
        if wrong == "logical_call":
            writer.record_dispatch(2, 2)
        else:
            writer.reserve_turn("B1")
    assert journal.inspect_run(binding, "run-1")["accounting"]["provider_attempts"] == 1


def test_exhausted_known_zero_usage_failures_cannot_complete_successfully(tmp_path):
    binding, writer = retry_writer(tmp_path)
    for attempt in (1, 2, 3):
        writer.record_dispatch(1, attempt)
        writer.record_provider_result(
            1, attempt, retry_failure(known_zero_usage=True), http_status=500
        )
    writer.complete_call(1)
    finish_evidence(writer)
    assert writer.record_decision(ready()).action == "STOP"
    writer.close()
    report = journal.inspect_run(binding, "run-1")
    assert report["accounting"]["unknown_attempts"] == 0
    assert report["accounting"]["operational_errors"] == 1


def test_operator_stop_blocks_an_otherwise_eligible_retry(tmp_path):
    binding, writer = retry_writer(tmp_path)
    writer.record_dispatch(1, 1)
    writer.record_provider_result(1, 1, retry_failure(), http_status=500)
    writer.stop()
    with pytest.raises(journal.JournalError):
        writer.record_dispatch(1, 2)
    assert journal.inspect_run(binding, "run-1")["accounting"]["provider_attempts"] == 1


@pytest.mark.parametrize("code", ["operator_stop", "interrupted", "operational_error"])
def test_public_stop_preserves_legacy_record_protocol(tmp_path, code):
    registry, writer = make(tmp_path)
    writer.stop(code)
    assert writer.provider_stopped
    writer.close()
    report = journal.inspect_run(registry, "run-1")
    assert report["issues"] == [] and "instrumentation_profile" not in report
    assert [record["kind"] for record in report["records"]] == ["manifest", "stop"]
    assert report["records"][-1]["payload"] == {"code": code}
    assert all(record["schema_id"] == journal.SCHEMA for record in report["records"])


@pytest.mark.parametrize("profile", [False, True], ids=["legacy", "instrumented"])
@pytest.mark.parametrize(
    "fault", ["invalid", "before_publication", "after_publication"]
)
def test_failed_public_stop_never_reopens_gate_or_replaces_evidence(
    tmp_path, monkeypatch, profile, fault
):
    from test_canary_instrumentation_v3 import profiled

    if profile:
        registry, writer, _ = profiled(tmp_path)
    else:
        registry, writer = make(tmp_path)
    before = tree_bytes(Path(registry.path))
    original = journal._publish

    def publish(directory, name, value):
        if value.get("kind") in {"stop", "instrumentation_stop"}:
            assert writer.provider_stopped
            if fault == "after_publication":
                original(directory, name, value)
            raise OSError("PRIVATE_STOP_FAILURE")
        original(directory, name, value)

    with monkeypatch.context() as patch:
        if fault != "invalid":
            patch.setattr(journal, "_publish", publish)
        with pytest.raises(journal.JournalError) as error:
            writer.stop(
                "PRIVATE_INVALID_STOP" if fault == "invalid" else "operator_stop"
            )
    assert writer.provider_stopped
    with pytest.raises(journal.JournalError):
        writer.stop()
    assert writer.provider_stopped
    writer.close()
    after = tree_bytes(Path(registry.path))
    assert all(after[name] == content for name, content in before.items())
    report = journal.inspect_run(registry, "run-1")
    kind = "instrumentation_stop" if profile else "stop"
    stops = [
        record["payload"] for record in report["records"] if record["kind"] == kind
    ]
    assert len(stops) == int(fault == "after_publication")
    if stops:
        assert stops[0]["code"] == "operator_stop"
    assert report["issues"] == [] and not report["completion_certified"]
    assert "PRIVATE" not in str(error.value) + str(report)


def test_instrumentation_requires_explicit_exact_definition_and_is_deeply_frozen(
    tmp_path,
):
    from pydantic import ValidationError
    from test_canary_instrumentation_v3 import profiled

    (tmp_path / "default").mkdir()
    registry, writer = make(tmp_path / "default")
    with pytest.raises(journal.JournalError):
        writer.bind_provider(
            resolve_definition(),
            project_id="proj_synthetic",
            organization_id="org_synthetic",
        )
    assert not journal.inspect_run(registry, "run-1")["authorises_live_execution"]
    _, writer, binding = profiled(tmp_path / "explicit")
    with pytest.raises(ValidationError):
        binding.run_id = "changed"
    with pytest.raises(ValidationError):
        binding.definition.inference.model = "changed"
    writer.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", "wrong"),
        ("registry_id", "wrong"),
        ("slot", "B1"),
        ("logical_call", 2),
        ("sequence", 0),
        ("extra", "PRIVATE"),
    ],
)
def test_instrumented_reservation_identity_is_checked_atomically(
    tmp_path, field, value
):
    from test_canary_instrumentation_v3 import attempt_guards, profiled

    from harness.canary.evidence_v3 import DispatchTelemetry

    registry, writer, binding = profiled(tmp_path)
    reservation = writer.reserve_provider_call(
        binding, slot="A1", previous_response_id=None
    )
    guards = attempt_guards()
    telemetry = DispatchTelemetry(
        sdk_retry_count=0, started_at=guards.checked_at, guards=guards
    )
    with pytest.raises(journal.JournalError):
        writer.dispatch_provider_attempt(
            binding,
            reservation.model_copy(update={field: value}),
            1,
            telemetry=telemetry,
        )
    assert writer.provider_stopped
    report = journal.inspect_run(registry, "run-1")
    assert report["accounting"]["provider_attempts"] == 0
    assert "PRIVATE" not in str(report)


@pytest.mark.parametrize(
    "fault", ["duplicate", "fourth", "after_success", "orphan", "duplicate_result"]
)
def test_instrumentation_attempt_order_uses_original_journal_rules(tmp_path, fault):
    from test_canary_instrumentation_v3 import attempt_guards, profiled

    from harness.canary.evidence_v3 import DispatchTelemetry, ResultTelemetry

    registry, writer, binding = profiled(tmp_path)
    reservation = writer.reserve_provider_call(
        binding, slot="A1", previous_response_id=None
    )

    def dispatch(attempt):
        guards = attempt_guards()
        writer.dispatch_provider_attempt(
            binding,
            reservation,
            attempt,
            telemetry=DispatchTelemetry(
                sdk_retry_count=min(attempt - 1, 2),
                started_at=guards.checked_at,
                guards=guards,
            ),
        )

    def result(attempt, *, succeeded=False):
        writer.observe_provider_attempt(
            binding,
            reservation,
            attempt,
            envelope() if succeeded else retry_failure(known_zero_usage=True),
            http_status=200 if succeeded else 500,
            telemetry=ResultTelemetry(
                duration_ms=1.0,
                read_complete=True,
                json_state="valid",
                observed_http_status=200 if succeeded else 500,
            ),
        )

    if fault == "orphan":
        operation = lambda: result(1)
    else:
        for attempt in range(1, 4 if fault == "fourth" else 2):
            dispatch(attempt)
            result(attempt, succeeded=fault == "after_success")
        operation = lambda: dispatch(
            {"duplicate": 1, "fourth": 4, "after_success": 2, "duplicate_result": 1}[
                fault
            ]
        )
        if fault == "duplicate_result":
            operation = lambda: result(1)
    with pytest.raises(journal.JournalError):
        operation()
    assert writer.provider_stopped
    assert journal.inspect_run(registry, "run-1")["accounting"][
        "provider_attempts"
    ] == (0 if fault == "orphan" else 3 if fault == "fourth" else 1)


@pytest.mark.parametrize(
    "legacy",
    ["reserve_call", "record_dispatch", "record_provider_result", "complete_call"],
)
def test_profiled_journal_rejects_legacy_provider_records(tmp_path, legacy):
    from test_canary_instrumentation_v3 import profiled

    registry, writer, _ = profiled(tmp_path)
    arguments = {
        "reserve_call": (1,),
        "record_dispatch": (1, 1),
        "record_provider_result": (1, 1, envelope()),
        "complete_call": (1,),
    }
    with pytest.raises(journal.JournalError):
        getattr(writer, legacy)(*arguments[legacy])
    assert not journal.inspect_run(registry, "run-1")["completion_certified"]


def test_profile_is_opt_in_once_before_decisions_and_cannot_rebind(tmp_path):
    from test_canary_instrumentation_v3 import profiled

    (tmp_path / "late").mkdir()
    registry, writer = make(tmp_path / "late")
    writer.record_decision(ready())
    with pytest.raises(journal.JournalError):
        writer.bind_provider(
            resolve_definition(V3),
            project_id="proj_synthetic",
            organization_id="org_synthetic",
        )
    assert "instrumentation_profile" not in journal.inspect_run(registry, "run-1")
    registry, writer, _ = profiled(tmp_path / "twice")
    with pytest.raises(journal.JournalError):
        writer.bind_provider(
            resolve_definition(V3),
            project_id="proj_synthetic",
            organization_id="org_synthetic",
        )
    assert (
        journal.inspect_run(registry, "run-1")["instrumentation_profile"]
        == "canary-provider-instrumentation-v1"
    )


@pytest.mark.parametrize("calls_per_turn,attempts_per_call", [(1, 1), (6, 3)])
def test_instrumented_complete_roster_keeps_policy_and_save_only_semantics(
    tmp_path, calls_per_turn, attempts_per_call
):
    from test_canary_instrumentation_v3 import (
        app_request,
        attempt_guards,
        client_for,
        profiled,
    )

    from harness.canary.instrumentation_v3 import ProviderTransportV3

    registry, writer, binding = profiled(tmp_path, turn=False)
    observed = []

    def respond(request):
        observed.append(request)
        if len(observed) % attempts_per_call:
            return httpx.Response(500, json=retry_failure(known_zero_usage=True))
        raw = envelope()
        raw["id"] = f"resp_{len(observed)}"
        return httpx.Response(200, json=raw)

    transport = ProviderTransportV3(
        writer, binding, httpx.MockTransport(respond), guards=attempt_guards
    )
    client = client_for(transport, count=attempts_per_call)
    for turn in binding.definition.turns:
        decision = writer.record_decision(ready())
        assert decision.next_slot == turn.slot
        writer.reserve_turn(turn.slot)
        previous = None
        for _ in range(calls_per_turn):
            previous = client.create_response(
                app_request(input=turn.message, previous_response_id=previous)
            ).response_id
        raw = selected(turn.slot)
        writer.record_chat(raw["chat"])
        writer.record_trace(raw["trace"], reread=raw["trace"])
        writer.assess_turn()
        writer.complete_turn()
    assert writer.record_decision(ready()).action == "COMPLETE"
    transport.close()
    writer.record_shutdown(
        worker_stopped=True, sdk_closed=True, no_inflight_provider=True
    )
    writer.seal()
    report = journal.inspect_run(registry, "run-1")
    assert report["completion_certified"] and report["accounting_reconciled"]
    assert report["accounting"]["logical_calls"] == 4 * calls_per_turn
    assert (
        report["accounting"]["provider_attempts"]
        == len(observed)
        == 4 * calls_per_turn * attempts_per_call
    )
    assert not report["source_authorised"] and not report["authorises_live_execution"]
    before = tree_bytes(Path(registry.path))
    assert journal.recover_save_only(registry, "run-1", tmp_path / "export") == report
    assert tree_bytes(Path(registry.path)) == before
