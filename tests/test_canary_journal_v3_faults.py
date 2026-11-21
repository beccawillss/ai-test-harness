"""Injected local filesystem faults and child process death; no network activity."""

import errno
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from test_canary_journal_v3 import (
    complete,
    envelope,
    make,
    ready,
    receipt,
    retry_failure,
    retry_writer,
    spending_envelope,
    tree_bytes,
    turn,
)

from harness.canary import journal_v3 as journal
from harness.canary.evidence_v3 import provider_observation
from harness.core.fingerprints import canonical_json, fingerprint

ROOT = Path(__file__).resolve().parents[1]


def rewrite(path, change):
    envelope = json.loads(path.read_bytes())
    change(envelope["payload"])
    envelope["sha256"] = fingerprint(envelope["payload"])
    path.write_text(canonical_json(envelope))


def replace_saved_history(ledger, records):
    """Forge valid checksums/links, leaving semantic replay as the rejection gate."""
    for path in ledger.glob("*.json"):
        path.unlink()
    for sequence, record in enumerate(records):
        record["sequence"] = sequence
        record["previous_sha256"] = (
            fingerprint(records[sequence - 1]) if sequence else None
        )
        path = ledger / f"{sequence:06d}.json"
        path.write_text(
            canonical_json({"payload": record, "sha256": fingerprint(record)})
        )
        path.chmod(0o600)
    # Independently verify every stored envelope and predecessor after rewriting.
    previous = None
    for sequence, path in enumerate(sorted(ledger.glob("*.json"))):
        saved = json.loads(path.read_bytes())
        assert path.name == f"{sequence:06d}.json"
        assert path.read_text() == canonical_json(saved)
        assert saved["sha256"] == fingerprint(saved["payload"])
        assert saved["payload"]["sequence"] == sequence
        assert saved["payload"]["previous_sha256"] == previous
        previous = fingerprint(saved["payload"])


@pytest.mark.parametrize(
    "fault",
    [
        "forged_denial",
        "forged_unreviewed_directive",
        "forged_raw_directive",
        "forged_billing_eligibility",
        "retry_after_denial",
        "retry_after_billing",
        "retry_after_success",
        "retry_after_ambiguous_result",
        "retry_without_result",
        "duplicate_attempt",
        "fourth_attempt",
        "wrong_slot",
        "wrong_call",
    ],
)
def test_saved_replay_rejects_rechained_retry_forgery_without_producer(tmp_path, fault):
    binding, writer = make(tmp_path)
    for slot in ("A1", "B1", "A2", "B2"):
        writer.record_decision(ready())
        turn(writer, slot, attempts=3 if slot == "A1" else 1)
    assert writer.record_decision(ready()).action == "COMPLETE"
    writer.record_shutdown(
        worker_stopped=True, sdk_closed=True, no_inflight_provider=True
    )
    writer.seal()  # Closes the producer; inspection must reconstruct saved state.
    control = journal.inspect_run(binding, "run-1")
    assert control["status"] == "completed"
    assert control["accounting_reconciled"]
    assert control["accounting"]["provider_attempts"] == 6
    records = deepcopy(control["records"])
    results = [i for i, r in enumerate(records) if r["kind"] == "provider_result"]
    dispatches = [i for i, r in enumerate(records) if r["kind"] == "provider_dispatch"]
    first = records[results[0]]["payload"]["observation"]
    retry = records[dispatches[1]]["payload"]
    rejected_at = dispatches[1]
    if fault.startswith("forged_"):
        rejected_at = results[0]
        if fault == "forged_billing_eligibility":
            first["error_category"] = "billing"
            first["retry_directive"] = "true"
        else:
            first["retry_directive"] = {
                "forged_denial": "false",
                "forged_unreviewed_directive": "unreviewed",
                "forged_raw_directive": "PRIVATE_FORGED_DIRECTIVE",
            }[fault]
        assert first["outcome"] == "retryable_http_failure"
    elif fault in {
        "retry_after_denial",
        "retry_after_billing",
        "retry_after_success",
        "retry_after_ambiguous_result",
    }:
        raw = retry_failure(known_zero_usage=True)
        status, directive = 500, None
        if fault == "retry_after_denial":
            directive = "false"
        elif fault == "retry_after_billing":
            raw["error"]["code"] = "insufficient_quota"
            directive = "true"
        elif fault == "retry_after_success":
            raw, status = envelope(), 200
        else:
            raw, status = None, None
        records[results[0]]["payload"]["observation"] = provider_observation(
            raw, http_status=status, should_retry_header=directive
        )
    elif fault == "retry_without_result":
        records.pop(results[0])
        rejected_at -= 1
    elif fault == "duplicate_attempt":
        retry["attempt"] = 1
    elif fault == "fourth_attempt":
        records[results[2]]["payload"]["observation"] = provider_observation(
            retry_failure(known_zero_usage=True), http_status=500
        )
        rejected_at = results[2] + 1
        fourth = deepcopy(records[dispatches[2]])
        fourth["payload"]["attempt"] = 4
        records.insert(rejected_at, fourth)
    elif fault == "wrong_slot":
        retry["slot"] = "B1"
    else:
        retry["logical_call"] = 2
    ledger = Path(binding.path) / "runs/run-1/records"
    replace_saved_history(ledger, records)
    before = tree_bytes(Path(binding.path))
    report = journal.inspect_run(binding, "run-1")
    assert report["status"] == "corrupt"
    assert report["records"] == records[:rejected_at]
    assert not report["accounting_reconciled"]
    assert not report["completion_acknowledged"]
    assert not report["authorises_live_execution"]
    exported = journal.recover_save_only(binding, "run-1", tmp_path / "export")
    assert exported == report
    assert (
        "PRIVATE_FORGED_DIRECTIVE" not in (tmp_path / "export/report.json").read_text()
    )
    assert tree_bytes(Path(binding.path)) == before


@pytest.mark.parametrize("boundary", ["next_call", "retry"])
@pytest.mark.parametrize("input_tokens", [1000000, 1000001])
def test_saved_replay_rejects_reservations_after_known_spending_pause(
    tmp_path, boundary, input_tokens
):
    binding, writer = retry_writer(tmp_path)
    retryable = boundary == "retry"
    writer.record_dispatch(1, 1)
    writer.record_provider_result(
        1,
        1,
        spending_envelope(999999, retryable=retryable),
        http_status=500 if retryable else 200,
    )
    if retryable:
        writer.record_dispatch(1, 2)
    else:
        writer.complete_call(1)
        writer.reserve_call(2)
    writer.close()
    control = journal.inspect_run(binding, "run-1")
    assert control["structurally_validated"]
    records = deepcopy(control["records"])
    result = next(r for r in records if r["kind"] == "provider_result")
    observation = provider_observation(
        spending_envelope(input_tokens, retryable=retryable),
        http_status=500 if retryable else 200,
    )
    result["payload"]["observation"] = observation
    # The new result is internally consistent; the later reservation is illegal.
    rejected_at = len(records) - 1
    assert records[rejected_at]["kind"] == (
        "provider_dispatch" if retryable else "call_reserved"
    )
    replace_saved_history(Path(binding.path) / "runs/run-1/records", records)
    before = tree_bytes(Path(binding.path))
    report = journal.inspect_run(binding, "run-1")
    assert report["status"] == "corrupt"
    assert report["records"] == records[:rejected_at]
    assert (
        report["records"][result["sequence"]]["payload"]["observation"] == observation
    )
    assert report["accounting"]["provider_attempts"] == 1
    assert not report["accounting_reconciled"]
    assert not report["completion_acknowledged"]
    assert journal.recover_save_only(binding, "run-1", tmp_path / "export") == report
    assert tree_bytes(Path(binding.path)) == before


@pytest.mark.parametrize(
    "fault",
    [
        "file_fsync",
        "link",
        "directory_fsync",
        "partial_write",
        "interrupted_write",
        "disk_full",
    ],
)
def test_publication_failure_is_terminal_and_preserves_all_previous_records(
    tmp_path, monkeypatch, fault
):
    binding, writer = make(tmp_path)
    writer.record_decision(ready())
    prior = tree_bytes(Path(binding.path))
    original_fsync = journal.os.fsync

    def failed_sync(descriptor):
        is_directory = stat.S_ISDIR(os.fstat(descriptor).st_mode)
        if (fault == "file_fsync" and not is_directory) or (
            fault == "directory_fsync" and is_directory
        ):
            raise OSError("PRIVATE_FSYNC_FAILURE")
        original_fsync(descriptor)

    def failed_link(*args, **kwargs):
        raise OSError("PRIVATE_LINK_FAILURE")

    original_fdopen = journal.os.fdopen

    class Partial:
        def __init__(self, delegate):
            self.delegate = delegate

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.delegate.close()

        def write(self, data):
            if fault == "disk_full":
                raise OSError(errno.ENOSPC, "PRIVATE_DISK_FULL")
            self.delegate.write(data[:7])
            if fault == "interrupted_write":
                raise KeyboardInterrupt("PRIVATE_INTERRUPT")
            return 7

        def flush(self):
            self.delegate.flush()

        def fileno(self):
            return self.delegate.fileno()

    with monkeypatch.context() as patch:
        if "fsync" in fault:
            patch.setattr(journal.os, "fsync", failed_sync)
        elif fault == "link":
            patch.setattr(journal.os, "link", failed_link)
        else:
            patch.setattr(
                journal.os,
                "fdopen",
                lambda fd, mode: (
                    Partial(original_fdopen(fd, mode))
                    if mode == "wb"
                    else original_fdopen(fd, mode)
                ),
            )
        with pytest.raises(journal.JournalError) as caught:
            writer.reserve_turn("A1")
        assert "PRIVATE" not in str(caught.value)
        assert caught.value.__suppress_context__
    after = tree_bytes(Path(binding.path))
    assert all(after[name] == value for name, value in prior.items())
    final = Path(binding.path) / "runs/run-1/records/000002.json"
    assert final.exists() is (fault == "directory_fsync")
    if final.exists():
        assert json.loads(final.read_text())["payload"]["kind"] == "turn_reserved"
    with pytest.raises(journal.JournalError):
        writer.reserve_turn("A1")
    with pytest.raises(journal.JournalError):
        journal.CanaryJournal(
            binding, "run-1", "other-approval", source_receipt=receipt()
        )
    report = journal.inspect_run(binding, "run-1")
    assert report["status"] != "completed"
    assert "PRIVATE" not in str(report)


def test_exclusive_publication_cannot_replace_equal_or_different_payload(tmp_path):
    directory = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        journal._publish(directory, "record.json", {"value": 1})
        before = (tmp_path / "record.json").read_bytes()
        for value in (1, 2):
            with pytest.raises(journal.JournalError):
                journal._publish(directory, "record.json", {"value": value})
            assert (tmp_path / "record.json").read_bytes() == before
    finally:
        os.close(directory)


def test_temporary_cleanup_failure_does_not_erase_publication(tmp_path, monkeypatch):
    binding, writer = make(tmp_path)
    original = journal.os.unlink

    def fail(name, *args, **kwargs):
        if str(name).startswith(".pending-"):
            raise OSError("PRIVATE_CLEANUP")
        return original(name, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(journal.os, "unlink", fail)
        writer.record_decision(ready())
    writer.close()
    report = journal.inspect_run(binding, "run-1")
    assert report["structurally_validated"]
    assert report["pending_files"] == 1
    assert report["persisted_records"] == 2


@pytest.mark.parametrize(
    "boundary",
    ["root_mkdir", "registry", "run_mkdir", "approval", "records_mkdir", "manifest"],
)
def test_failed_initialization_never_reuses_partial_identity(
    tmp_path, monkeypatch, boundary
):
    original_publish, original_mkdir = journal._publish, journal._mkdir
    binding = None
    if boundary not in {"root_mkdir", "registry"}:
        binding = journal.initialize_registry(tmp_path / "v3")

    def publish(directory, name, payload):
        original_publish(directory, name, payload)
        if (
            (boundary == "registry" and name == "registry.json")
            or (boundary == "approval" and "approval_id" in payload)
            or (
                boundary == "manifest"
                and isinstance(payload, dict)
                and payload.get("kind") == "manifest"
            )
        ):
            raise KeyboardInterrupt("PRIVATE_INIT")

    def mkdir(directory, name):
        descriptor = original_mkdir(directory, name)
        if (
            (boundary == "root_mkdir" and name == "v3")
            or (boundary == "run_mkdir" and name == "run")
            or (boundary == "records_mkdir" and name == "records")
        ):
            os.close(descriptor)
            raise OSError("PRIVATE_INIT")
        return descriptor

    with monkeypatch.context() as patch:
        patch.setattr(journal, "_publish", publish)
        patch.setattr(journal, "_mkdir", mkdir)
        with pytest.raises((journal.JournalError, KeyboardInterrupt)):
            if binding is None:
                journal.initialize_registry(tmp_path / "v3")
            else:
                journal.CanaryJournal(
                    binding, "run", "approval", source_receipt=receipt()
                )
    if binding is None:
        with pytest.raises(journal.JournalError):
            journal.initialize_registry(tmp_path / "v3")
    else:
        with pytest.raises(journal.JournalError):
            journal.CanaryJournal(
                binding, "run", "replacement", source_receipt=receipt()
            )


@pytest.mark.parametrize(
    "fault",
    [
        "truncate",
        "checksum",
        "duplicate_key",
        "noncanonical",
        "missing",
        "extra",
        "predecessor",
        "valid_checksum_conflict",
        "approval_claim",
    ],
)
def test_corrupt_and_conflicting_records_are_reported_without_repair(tmp_path, fault):
    binding, writer = make(tmp_path)
    complete(writer)
    ledger = Path(binding.path) / "runs/run-1/records"
    target = ledger / "000001.json"
    if fault == "truncate":
        target.write_bytes(target.read_bytes()[:20])
    elif fault == "checksum":
        value = json.loads(target.read_bytes())
        value["sha256"] = "0" * 64
        target.write_text(canonical_json(value))
    elif fault == "duplicate_key":
        target.write_text('{"payload":{},"payload":{},"sha256":"0"}')
    elif fault == "noncanonical":
        target.write_bytes(target.read_bytes() + b"\n")
    elif fault == "missing":
        target.unlink()
    elif fault == "extra":
        (ledger / "unexpected.json").write_text("PRIVATE_CORRUPT")
    elif fault == "predecessor":
        rewrite(target, lambda p: p.update(previous_sha256="0" * 64))
    elif fault == "valid_checksum_conflict":
        rewrite(target, lambda p: p["payload"]["decision"].update(action="COMPLETE"))
    else:
        claim = next((Path(binding.path) / "approvals").glob("*.json"))
        rewrite(claim, lambda p: p.update(run_id="different"))
    before = tree_bytes(Path(binding.path))
    report = journal.inspect_run(binding, "run-1")
    assert report["status"] == "corrupt"
    assert not report["accounting_reconciled"]
    exported = journal.recover_save_only(binding, "run-1", tmp_path / "export")
    assert exported["status"] == "corrupt"
    assert not exported["completion_acknowledged"]
    assert "PRIVATE_CORRUPT" not in (tmp_path / "export/report.json").read_text()
    assert tree_bytes(Path(binding.path)) == before


@pytest.mark.parametrize(
    "entry", ["registry", "runs", "run", "records", "record", "permissions"]
)
def test_storage_substitution_or_permissions_close_the_writer(tmp_path, entry):
    binding, writer = make(tmp_path)
    root = Path(binding.path)
    path = {
        "registry": root,
        "runs": root / "runs",
        "run": root / "runs/run-1",
        "records": root / "runs/run-1/records",
        "record": root / "runs/run-1/records/000000.json",
        "permissions": root / "runs/run-1/records/000000.json",
    }[entry]
    if entry == "permissions":
        path.chmod(0o644)
    else:
        renamed = path.with_name(path.name + "-original")
        path.rename(renamed)
        path.symlink_to(renamed, target_is_directory=renamed.is_dir())
    with pytest.raises(journal.JournalError):
        writer.record_decision(ready())
    if entry in {"registry", "runs"}:
        with pytest.raises(journal.JournalError):
            journal.inspect_run(binding, "run-1")
    else:
        assert journal.inspect_run(binding, "run-1")["status"] == "corrupt"


def test_copied_registry_cannot_be_loaded_as_authoritative(tmp_path):
    binding, writer = make(tmp_path)
    writer.close()
    copied = tmp_path / "copied"
    shutil.copytree(binding.path, copied)
    with pytest.raises(journal.JournalError):
        journal.load_registry(copied)
    assert copied.exists()


def test_approval_claim_substitution_blocks_next_record(tmp_path):
    binding, writer = make(tmp_path)
    claim = next((Path(binding.path) / "approvals").glob("*.json"))
    rewrite(claim, lambda p: p.update(run_id="other"))
    with pytest.raises(journal.JournalError):
        writer.record_decision(ready())
    assert journal.inspect_run(binding, "run-1")["status"] == "corrupt"


def child(program, *arguments, **kwargs):
    return subprocess.Popen(
        [sys.executable, "-B", "-c", program, *map(str, arguments)],
        env={
            "PATH": os.defpath,
            "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(ROOT / "tests")]),
        },
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **kwargs,
    )


@pytest.mark.parametrize("operation", ["read", "inspect", "recover", "producer"])
@pytest.mark.parametrize("position", ["manifest", "latest"])
def test_fifo_substitution_is_rejected_without_blocking(tmp_path, operation, position):
    program = """
import os, stat, sys
from pathlib import Path
from harness.canary import journal_v3 as j
from test_canary_journal_v3 import complete, make, ready, receipt, tree_bytes

root, operation, position = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
binding, writer = make(root)
if operation == 'producer':
    writer.record_decision(ready())  # Regular-file integrity reads succeed first.
else:
    complete(writer)
    assert j.inspect_run(binding, 'run-1')['status'] == 'completed'
ledger = Path(binding.path) / 'runs/run-1/records'
target = sorted(ledger.glob('*.json'))[0 if position == 'manifest' else -1]
original = target.read_bytes()
descriptor = os.open(ledger, os.O_RDONLY | os.O_DIRECTORY)
try:
    assert j._read(descriptor, target.name)['kind'] == (
        'manifest' if position == 'manifest' else
        'decision' if operation == 'producer' else 'completion_ack'
    )
    target.unlink()
    os.mkfifo(target, 0o600)  # No FIFO writer will ever be connected.
    target.chmod(0o600)
    identity = target.lstat()
    before = tree_bytes(Path(binding.path))  # Skips the FIFO; never opens it.
    print('special-file-ready', flush=True)
    if operation == 'read':
        try:
            j._read(descriptor, target.name)
        except j.JournalError as error:
            assert str(error) == 'invalid_record'
        else:
            raise AssertionError('special record accepted')
    elif operation == 'producer':
        try:
            writer.stop()
        except j.JournalError as error:
            assert str(error) == 'journal_stopped_preserve_evidence'
        else:
            raise AssertionError('producer accepted substituted evidence')
        try:
            writer.stop()
        except j.JournalError as error:
            assert str(error) == 'journal_stopped_preserve_evidence'
        else:
            raise AssertionError('producer gate reopened')
    report = (
        j.recover_save_only(binding, 'run-1', root / 'export')
        if operation == 'recover' else j.inspect_run(binding, 'run-1')
    )
    assert report['status'] == 'corrupt'
    assert report['issues'] == ['corrupt_or_conflicting_evidence']
    assert not report['completion_certified']
    assert not report['completion_acknowledged']
    assert not report['accounting_reconciled']
    assert not report['authorises_live_execution']
    assert tree_bytes(Path(binding.path)) == before
    after = target.lstat()
    assert stat.S_ISFIFO(after.st_mode)
    assert (after.st_dev, after.st_ino, after.st_mode) == (
        identity.st_dev, identity.st_ino, identity.st_mode
    )
    if operation == 'recover':
        assert j.inspect_run(binding, 'run-1') == report
    if operation == 'producer':
        # Restore regular bytes only in this tampering test: closure must persist
        # after the bad input is removed, and the run must remain single-use.
        target.unlink()
        target.write_bytes(original)
        target.chmod(0o600)
        try:
            writer.record_decision(ready())
        except j.JournalError:
            pass
        else:
            raise AssertionError('restoring bytes reopened producer')
        try:
            j.CanaryJournal(binding, 'run-1', 'replacement', source_receipt=receipt())
        except j.JournalError:
            pass
        else:
            raise AssertionError('replacement producer reopened run')
        assert not j.inspect_run(binding, 'run-1')['completion_certified']
    print('special-file-rejected', flush=True)
finally:
    writer.close()
    os.close(descriptor)
"""
    process = child(program, tmp_path, operation, position)
    try:
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)
            assert "special-file-ready" in stdout, (stdout, stderr)
            pytest.fail(f"FIFO {operation} blocked beyond five seconds")
        assert process.returncode == 0, (stdout, stderr)
        assert stdout.splitlines() == ["special-file-ready", "special-file-rejected"]
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)


def test_concurrent_process_writer_and_duplicate_approval(tmp_path):
    binding = journal.initialize_registry(tmp_path / "v3")
    program = """
import sys
from pathlib import Path
from harness.canary.journal_v3 import CanaryJournal, load_registry
from test_canary_journal_v3 import receipt
w = CanaryJournal(load_registry(Path(sys.argv[1])), 'child-run', 'shared-approval', source_receipt=receipt())
print('claimed', flush=True)
sys.stdin.readline()
w.close()
"""
    process = child(program, binding.path)
    try:
        assert process.stdout.readline().strip() == "claimed"
        with pytest.raises(journal.JournalError, match="busy"):
            journal.CanaryJournal(
                binding, "other", "shared-approval", source_receipt=receipt()
            )
        process.communicate("close\n", timeout=15)
        assert process.returncode == 0
        with pytest.raises(journal.JournalError):
            journal.CanaryJournal(
                binding, "other", "shared-approval", source_receipt=receipt()
            )
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=15)


def test_sigkill_after_dispatch_intent_preserves_unknown_liability(tmp_path):
    binding = journal.initialize_registry(tmp_path / "v3")
    program = """
import sys
from pathlib import Path
from harness.canary.journal_v3 import CanaryJournal, load_registry
from test_canary_journal_v3 import receipt, ready
w = CanaryJournal(load_registry(Path(sys.argv[1])), 'killed', 'approval', source_receipt=receipt())
w.record_decision(ready())
w.reserve_turn('A1')
w.reserve_call(1)
w.record_dispatch(1, 1)
print('inflight', flush=True)
sys.stdin.readline()
raise AssertionError('must be killed')
"""
    process = child(program, binding.path)
    try:
        assert process.stdout.readline().strip() == "inflight"
        os.kill(process.pid, signal.SIGKILL)
        process.communicate(timeout=15)
        assert process.returncode == -signal.SIGKILL
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=15)
    report = journal.inspect_run(binding, "killed")
    assert report["status"] == "operationally_uncertain"
    assert report["accounting"]["unknown_attempts"] == 1
    assert report["accounting"]["estimated_total_usd"] is None
    before = tree_bytes(Path(binding.path))
    journal.recover_save_only(binding, "killed", tmp_path / "saved")
    assert tree_bytes(Path(binding.path)) == before


def test_substituted_export_destination_is_rejected_without_following_symlink(
    tmp_path, monkeypatch
):
    binding, writer = make(tmp_path)
    writer.close()
    destination = tmp_path / "export"
    victim = tmp_path / "victim"
    victim.mkdir()
    original = journal._publish

    def substitute(directory, name, payload):
        destination.rename(tmp_path / "moved-export")
        destination.symlink_to(victim, target_is_directory=True)
        original(directory, name, payload)

    with monkeypatch.context() as patch:
        patch.setattr(journal, "_publish", substitute)
        with pytest.raises(journal.JournalError):
            journal.recover_save_only(binding, "run-1", destination)
    assert list(victim.iterdir()) == []
    assert (tmp_path / "moved-export/report.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "boundary",
    [
        "manifest",
        "decision",
        "turn_reserved",
        "call_reserved",
        "provider_dispatch",
        "provider_result",
        "call_completed",
        "chat",
        "trace",
        "assessment",
        "outcome",
        "shutdown",
        "completion",
        "completion_ack",
        "partial_temporary",
    ],
)
def test_abrupt_process_death_preserves_evidence_and_never_reopens(tmp_path, boundary):
    binding = journal.initialize_registry(tmp_path / "v3")
    program = """
import os, sys
from pathlib import Path
from harness.canary import journal_v3 as j
from test_canary_journal_v3 import receipt, complete
original = j._publish
def publish(directory, name, payload):
    if sys.argv[2] == 'partial_temporary' and isinstance(payload, dict) and payload.get('kind') == 'chat':
        fd = os.open('.pending-killed', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory)
        os.write(fd, b'{partial')
        os.fsync(fd)
        os._exit(73)
    original(directory, name, payload)
    if isinstance(payload, dict) and payload.get('kind') == sys.argv[2]:
        os._exit(73)
j._publish = publish
w = j.CanaryJournal(j.load_registry(Path(sys.argv[1])), 'killed-run', 'killed-approval', source_receipt=receipt())
complete(w)
raise AssertionError('boundary was not reached')
"""
    process = child(program, binding.path, boundary)
    stdout, stderr = process.communicate(timeout=30)
    assert process.returncode == 73, (stdout, stderr)
    with pytest.raises(journal.JournalError):
        journal.CanaryJournal(
            binding, "killed-run", "replacement", source_receipt=receipt()
        )
    before = tree_bytes(Path(binding.path))
    report = journal.inspect_run(binding, "killed-run")
    assert report["status"] == (
        "completed"
        if boundary == "completion_ack"
        else "operationally_uncertain"
        if boundary
        in {
            "turn_reserved",
            "call_reserved",
            "provider_dispatch",
            "provider_result",
            "call_completed",
            "chat",
            "trace",
            "assessment",
            "partial_temporary",
        }
        else "incomplete"
    )
    if boundary == "completion":
        assert (
            report["completion_seal_present"] and not report["completion_acknowledged"]
        )
    if boundary == "partial_temporary":
        assert report["pending_files"] == 1
        assert not any(r["kind"] == "chat" for r in report["records"])
    journal.recover_save_only(binding, "killed-run", tmp_path / "export")
    assert tree_bytes(Path(binding.path)) == before


def test_failure_syncing_completion_cannot_certify_visible_unacknowledged_seal(
    tmp_path, monkeypatch
):
    binding, writer = make(tmp_path)
    complete(writer, seal=False)
    original = journal.os.fsync

    def fail(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("PRIVATE_SYNC")
        original(descriptor)

    with monkeypatch.context() as patch:
        patch.setattr(journal.os, "fsync", fail)
        with pytest.raises(journal.JournalError):
            writer.seal()
    report = journal.inspect_run(binding, "run-1")
    assert report["completion_seal_present"]
    assert not report["completion_acknowledged"]
    assert report["status"] == "incomplete"
    before = tree_bytes(Path(binding.path))
    journal.recover_save_only(binding, "run-1", tmp_path / "saved")
    assert tree_bytes(Path(binding.path)) == before


def test_corrupt_previously_committed_record_blocks_next_reservation(tmp_path):
    binding, writer = make(tmp_path)
    writer.record_decision(ready())
    turn(writer, "A1")
    writer.record_decision(ready())
    ledger = Path(binding.path) / "runs/run-1/records"
    rewrite(ledger / "000000.json", lambda p: p["payload"].update(source_authorised=0))
    with pytest.raises(journal.JournalError):
        writer.reserve_turn("B1")
    assert journal.inspect_run(binding, "run-1")["status"] == "corrupt"


def test_interrupted_export_stays_private_and_retry_uses_new_destination(
    tmp_path, monkeypatch
):
    binding, writer = make(tmp_path)
    writer.close()
    before = tree_bytes(Path(binding.path))
    original = journal._publish

    def fail(directory, name, value):
        original(directory, name, value)
        raise OSError("PRIVATE_EXPORT_FAILURE")

    with monkeypatch.context() as patch:
        patch.setattr(journal, "_publish", fail)
        with pytest.raises(journal.JournalError):
            journal.recover_save_only(binding, "run-1", tmp_path / "partial-export")
    assert (tmp_path / "partial-export").stat().st_mode & 0o777 == 0o700
    assert (tmp_path / "partial-export/report.json").stat().st_mode & 0o777 == 0o600
    journal.recover_save_only(binding, "run-1", tmp_path / "new-export")
    assert tree_bytes(Path(binding.path)) == before


def test_import_inspect_and_export_have_no_external_construction_or_credentials(
    tmp_path,
):
    binding, writer = make(tmp_path)
    writer.close()
    program = """
import os, sys
def guard(event, arguments):
    if event.startswith('socket.') or event in ('subprocess.Popen', 'os.system'):
        raise AssertionError('network/process construction')
    if event == 'import' and arguments[0].split('.')[0] in ('openai', 'salesagent', 'uvicorn'):
        raise AssertionError('SDK/app construction')
sys.addaudithook(guard)
class Environment(dict):
    def __getitem__(self, key):
        if key.startswith(('OPENAI_', 'SALESAGENT_')): raise AssertionError('credential read')
        return super().__getitem__(key)
    def get(self, key, default=None):
        if key.startswith(('OPENAI_', 'SALESAGENT_')): raise AssertionError('credential read')
        return super().get(key, default)
os.environ = Environment(os.environ)
from pathlib import Path
from harness.canary.journal_v3 import load_registry, inspect_run, recover_save_only
r = load_registry(Path(sys.argv[1]))
assert not inspect_run(r, 'run-1')['authorises_live_execution']
recover_save_only(r, 'run-1', Path(sys.argv[2]))
print('offline-only')
"""
    process = child(program, binding.path, tmp_path / "guarded-export")
    stdout, stderr = process.communicate(timeout=15)
    assert process.returncode == 0, stderr
    assert stdout.strip() == "offline-only"
