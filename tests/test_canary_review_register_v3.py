"""Authenticated synthetic persistence; no real person or execution authority."""

from __future__ import annotations

import json
import multiprocessing
import os
import signal
import sqlite3
import stat
import sys
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_canary_human_review_v3 as contracts
import test_canary_review_packet_v3 as packets

from harness.canary import human_review_v3 as review
from harness.canary import review_register_v3 as register
from harness.core.fingerprints import fingerprint

keys = packets.keys
proposal = packets.proposal
manifest = packets.manifest
policy = packets.policy
signed = packets.signed
contract = packets.contract
sample = packets.sample


@pytest.fixture
def case(tmp_path, sample, keys):
    policy = sample.policy.model_copy(update={"public_key": keys.public_key})
    assignment = sample.assignment.model_copy(
        update={"trust_policy_identity_sha256": review.policy_identity(policy)}
    )
    configuration = register.ReviewRegisterConfiguration(
        path=str((tmp_path / "reviews").resolve()),
        register_id=assignment.register_id,
        host_id="synthetic-review-host",
        assignment=assignment,
        assignment_sha256=review.assignment_commitment(assignment),
        trust_policy_identity_sha256=assignment.trust_policy_identity_sha256,
    )
    initialized = register.initialize_register(
        configuration, protected_roots=(packets.protected(sample.linked.registry.path),)
    )
    return SimpleNamespace(
        sample=sample,
        assignment=assignment,
        policy=policy,
        binding=initialized.binding,
        zero=initialized.checkpoint_candidate,
        keys=keys,
    )


def bundle(case, **changes):
    payload = review.serialize_review_payload(
        contracts.make_review(case.assignment, **changes)
    )
    return payload, case.keys.sign(payload, namespace=review.NAMESPACE)


def arguments(case):
    return {
        "expected": case.assignment,
        "envelope_raw": case.sample.raw,
        "registry": case.sample.linked.registry,
        "register": case.binding,
    }


def submit(case, signed=None, **changes):
    return register.register_review(
        *(signed or bundle(case)),
        **arguments(case),
        policy=changes.get("policy", lambda: contracts.observation(case.policy)),
        clock=changes.get("clock", lambda: contracts.NOW),
    )


def inspect(case, checkpoint=None):
    return register.inspect_register(
        case.binding, expected=case.assignment, checkpoint=checkpoint
    )


def test_zero_checkpoint_and_readonly_inspection(case, monkeypatch):
    info = inspect(case, case.zero)
    assert (
        info.state == "EMPTY"
        and info.checkpoint_status == "matches"
        and not info.issues
    )
    assert info.checkpoint_candidate == case.zero
    assert case.zero.event_count == 0 and case.zero.head_sha256 == register.zero_head(
        case.binding
    )
    assert case.zero.register_binding_sha256 == fingerprint(
        case.binding.model_dump(mode="json")
    )
    before = packets.tree(case.binding.configuration.path)
    original = os.open

    def readonly(path, flags, *args, **kwargs):
        assert not flags & (os.O_CREAT | os.O_WRONLY | os.O_RDWR | os.O_TRUNC)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", readonly)
    assert inspect(case).checkpoint_status == "missing"
    assert packets.tree(case.binding.configuration.path) == before


def test_initial_review_duplicate_and_authenticated_conflict(case, tmp_path):
    first = bundle(case)
    recorded = submit(case, first)
    assert recorded.status == "RECORDED"
    assert recorded.checkpoint_candidate.event_count == 1
    event = inspect(case, recorded.checkpoint_candidate).events[0]
    assert event.previous_sha256 == case.zero.head_sha256
    before = packets.tree(case.binding.configuration.path)
    duplicate = submit(case, first)
    assert duplicate.status == "ALREADY_RECORDED"
    assert duplicate.prior_publisher_return == "not-established"
    assert packets.tree(case.binding.configuration.path) == before
    conflict = submit(case, bundle(case, failure=("A1", "R3")))
    assert conflict.status == "CONFLICT_RECORDED"
    reopened = inspect(case, conflict.checkpoint_candidate)
    assert reopened.state == "CONFLICT" and len(reopened.events) == 2
    assert reopened.events[0] == event
    assert reopened.events[1].previous_sha256 == event.event_sha256
    before = packets.tree(case.binding.configuration.path)
    assert submit(case, first).status == "ALREADY_CONFLICTED"
    assert packets.tree(case.binding.configuration.path) == before
    measurement = {
        "payload_bytes": len(first[0]),
        "signature_bytes": len(first[1]),
        "event_bytes": [
            len(review.encode(e, register.MAX_EVENT_BYTES)) for e in reopened.events
        ],
        "database_bytes": (Path(case.binding.configuration.path) / register.DATABASE)
        .stat()
        .st_size,
    }
    (tmp_path / "measurement.json").write_text(json.dumps(measurement))


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize(
    "fault",
    [
        "signature",
        "unknown_key",
        "wrong_namespace",
        "assignment",
        "review_id",
        "verdict",
        "packet",
        "policy",
        "revoked",
        "exposure",
        "reference",
    ],
)
def test_forged_or_invalid_submission_cannot_poison(case, monkeypatch, existing, fault):
    if existing:
        submit(case)
    payload, signature = bundle(case, failure=("A1", "R3"))
    args = arguments(case)
    supplier = lambda: contracts.observation(case.policy)
    if fault == "signature":
        signature = b"invalid"
    elif fault == "unknown_key":
        signature = case.keys.sign(payload, unknown=True, namespace=review.NAMESPACE)
    elif fault == "wrong_namespace":
        signature = case.keys.sign(payload)
    elif fault in {"review_id", "verdict", "exposure", "reference"}:
        value = json.loads(payload)
        if fault == "review_id":
            value["review_id"] = "synthetic-review-" + "0" * 32
        elif fault == "verdict":
            value["whole_run_verdict"] = "PASS"
        elif fault == "exposure":
            value["declarations"]["judge_output_exposure"] = "seen"
        else:
            value["references"][0]["pointer"] = "/missing"
        payload = review.encode(value)
        signature = case.keys.sign(payload, namespace=review.NAMESPACE)
    elif fault == "assignment":
        args["expected"] = case.assignment.model_copy(update={"round": 2})
    elif fault == "packet":
        args["envelope_raw"] = args["envelope_raw"] + b"\n"
    elif fault == "policy":
        supplier = lambda: contracts.observation(
            case.policy.model_copy(
                update={"required_role": "synthetic-canary-approver"}
            )
        )
    else:
        supplier = lambda: contracts.observation(case.policy, revoked=True)
    before = packets.tree(case.binding.configuration.path)
    original = register._open

    def guarded(binding, *, readonly):
        assert readonly, "invalid submission reached writable register"
        return original(binding, readonly=readonly)

    monkeypatch.setattr(register, "_open", guarded)
    with pytest.raises(review.ReviewError):
        register.register_review(
            payload, signature, **args, policy=supplier, clock=lambda: contracts.NOW
        )
    assert packets.tree(case.binding.configuration.path) == before
    assert not (Path(case.binding.configuration.path) / register.PENDING).exists()


@pytest.mark.parametrize("kind", ["stale", "behind", "head", "binding"])
def test_checkpoint_distinctions(case, kind):
    recorded = submit(case)
    checkpoint = recorded.checkpoint_candidate
    if kind == "stale":
        checkpoint = case.zero
    elif kind == "behind":
        checkpoint = checkpoint.model_copy(update={"event_count": 2})
    elif kind == "head":
        checkpoint = checkpoint.model_copy(update={"head_sha256": "0" * 64})
    else:
        checkpoint = checkpoint.model_copy(update={"register_binding_sha256": "0" * 64})
    result = inspect(case, checkpoint)
    assert (
        result.checkpoint_status
        == {
            "stale": "stale",
            "behind": "behind",
            "head": "mismatch",
            "binding": "mismatch",
        }[kind]
    )


def test_authenticated_disqualified_unable_is_a_disposition(case):
    signed = bundle(case, failure=("A1", "R1"), exposure="seen")
    assert submit(case, signed).status == "RECORDED"
    payload = review.parse_review_payload(inspect(case).events[0].payload_utf8.encode())
    assert (
        payload.completion == "UNABLE"
        and review.human_quality(payload).status == "SKIP"
    )
    assert submit(case, bundle(case)).status == "CONFLICT_RECORDED"


@pytest.mark.parametrize(
    "point", ["insert", "commit_before", "commit_after", "sync", "cleanup"]
)
def test_failure_and_uncertainty_preserve_state(case, monkeypatch, point):
    original_commit = register._commit
    if point == "insert":

        def fail(*args):
            raise OSError("PRIVATE_INSERT")

        monkeypatch.setattr(register, "_insert", fail)
    elif point.startswith("commit"):

        def commit(db):
            if point == "commit_after":
                original_commit(db)
            raise OSError("PRIVATE_COMMIT")

        monkeypatch.setattr(register, "_commit", commit)
    else:

        def fail(*args):
            raise OSError("PRIVATE_IO")

        monkeypatch.setattr(
            register, "_sync" if point == "sync" else "_clear_pending", fail
        )
    expected = (
        "registration_failed_uncommitted"
        if point == "insert"
        else "registration_outcome_unknown"
    )
    with pytest.raises(review.ReviewError, match="^" + expected + "$"):
        submit(case)
    result = inspect(case)
    if point == "insert":
        assert not result.events and "register_pending" not in result.issues
    else:
        assert "register_pending" in result.issues
        assert len(result.events) == (0 if point == "commit_before" else 1)


def test_sqlite_full_preserves_previous_review(case, monkeypatch):
    recorded = submit(case)
    old = inspect(case, recorded.checkpoint_candidate).events
    original = register._insert

    def full(storage, event):
        count = storage.db.execute("PRAGMA page_count").fetchone()[0]
        storage.db.execute(f"PRAGMA max_page_count={count}")
        original(storage, event)

    monkeypatch.setattr(register, "_insert", full)
    with pytest.raises(review.ReviewError, match="^registration_failed_uncommitted$"):
        submit(case, bundle(case, failure=("A1", "R3")))
    assert inspect(case).events == old


@pytest.mark.parametrize(
    "fault",
    [
        "permissions",
        "symlink",
        "hardlink",
        "fifo",
        "missing",
        "sidecar",
        "database_corrupt",
    ],
)
def test_unsafe_stores_cannot_be_reopened(case, tmp_path, fault):
    root = Path(case.binding.configuration.path)
    database = root / register.DATABASE
    if fault == "permissions":
        database.chmod(0o644)
    elif fault == "symlink":
        destination = tmp_path / "moved.sqlite3"
        database.rename(destination)
        database.symlink_to(destination)
    elif fault == "hardlink":
        os.link(database, tmp_path / "alias")
    elif fault == "fifo":
        database.unlink()
        os.mkfifo(database, 0o600)
    elif fault == "missing":
        database.unlink()
    elif fault == "sidecar":
        (root / "unexpected").write_text("extra")
    else:
        database.write_bytes(b"PRIVATE_CORRUPT_SQLITE")
    with pytest.raises(review.ReviewError):
        inspect(case, case.zero)


def _worker(connection, args, payload, signature, policy, phase="normal"):
    from harness.canary import review_register_v3 as reg

    if phase == "hot_journal":
        connect = reg._connect

        def spilling_connect(path, readonly):
            db = connect(path, readonly)
            # Fixture only: force dirty pages to disk before COMMIT, producing a
            # real hot DELETE journal rather than a zero-header buffered journal.
            db.execute("PRAGMA cache_size=1")
            db.execute("PRAGMA cache_spill=ON")
            return db

        reg._connect = spilling_connect
        phase = "before_commit"

    if phase != "normal":
        name, after = {
            "after_pending": ("_pending", True),
            "after_insert": ("_insert", True),
            "before_commit": ("_commit", False),
            "after_commit": ("_commit", True),
            "after_sync": ("_sync", True),
            "after_cleanup": ("_clear_pending", True),
            "race": ("_open", False),
        }[phase]
        original = getattr(reg, name)
        reached = False

        def boundary(*values, **kwargs):
            nonlocal reached
            result = original(*values, **kwargs) if after else None
            if not reached:
                reached = True
                connection.send("boundary")
                connection.recv()
            return result if after else original(*values, **kwargs)

        setattr(reg, name, boundary)
    try:
        result = reg.register_review(
            payload,
            signature,
            **args,
            policy=lambda: contracts.observation(policy),
            clock=lambda: contracts.NOW,
        )
        connection.send(("result", result.status))
        connection.recv()
    except review.ReviewError as error:
        connection.send(("error", error.code))
    finally:
        connection.close()


def start_worker(case, signed, phase):
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(
        target=_worker, args=(child, arguments(case), *signed, case.policy, phase)
    )
    process.start()
    child.close()
    return process, parent


def receive(connection):
    assert connection.poll(20), "coordinated worker timed out"
    return connection.recv()


def _register_snapshot(root):
    """Complete bytes, directory entries and all exposed stat metadata.

    Capture metadata after reading: access times may reflect the permitted read.
    Tests compare every field except atime, which read-only access may advance.
    """
    paths = [root, *sorted(root.rglob("*"))]
    data = {str(p.relative_to(root)): p.read_bytes() for p in paths if p.is_file()}
    metadata = {}
    for path in paths:
        info = path.lstat()
        metadata[str(path.relative_to(root))] = {
            name: getattr(info, name) for name in dir(info) if name.startswith("st_")
        }
    return {"bytes": data, "metadata": metadata}


def _inspect_interrupted(connection, binding, assignment, checkpoint):
    def audit(event, args):
        if event == "open" and args[2] & (
            os.O_CREAT | os.O_WRONLY | os.O_RDWR | os.O_TRUNC
        ):
            raise RuntimeError("write access forbidden")
        if event in {
            "os.remove",
            "os.rmdir",
            "os.mkdir",
            "os.rename",
            "os.link",
            "os.symlink",
            "os.chmod",
            "os.chown",
            "os.truncate",
            "os.utime",
        }:
            raise RuntimeError("filesystem mutation forbidden")
        if event == "sqlite3.connect" and "?mode=ro" not in args[0]:
            raise RuntimeError("writable SQLite forbidden")

    sys.addaudithook(audit)
    try:
        result = register.inspect_register(
            binding, expected=assignment, checkpoint=checkpoint
        )
        connection.send(("inspection", result.model_dump(mode="json")))
    except review.ReviewError as error:
        connection.send(("error", error.code))
    finally:
        connection.close()


@pytest.mark.parametrize("phase", ["before_commit", "hot_journal"])
@pytest.mark.parametrize("write_permissions", [True, False])
def test_interrupted_delete_journal_inspection_preserves_all_state(
    case, tmp_path, phase, write_permissions
):
    payload = contracts.make_review(case.assignment)
    if phase == "hot_journal":
        payload = payload.model_copy(
            update={
                "turns": tuple(
                    t.model_copy(
                        update={
                            "criteria": tuple(
                                c.model_copy(update={"rationale": "x" * 1024})
                                for c in t.criteria
                            ),
                        }
                    )
                    for t in payload.turns
                ),
            }
        )
    raw = review.serialize_review_payload(payload)
    signed = raw, case.keys.sign(raw, namespace=review.NAMESPACE)
    process, connection = start_worker(case, signed, phase)
    root = Path(case.binding.configuration.path)
    reader = None
    try:
        assert receive(connection) == "boundary"
        os.kill(process.pid, signal.SIGKILL)
        process.join(20)
        assert process.exitcode == -signal.SIGKILL
        assert {p.name for p in root.iterdir()} == {
            register.DATABASE,
            register.LOCK,
            register.PENDING,
            register.JOURNAL,
        }
        journal_bytes = (root / register.JOURNAL).read_bytes()
        assert len(journal_bytes) > 512
        if phase == "hot_journal":
            assert journal_bytes[:8] == bytes.fromhex("d9d505f920a163d7")
            assert int.from_bytes(journal_bytes[8:12], "big") > 0
        else:
            assert journal_bytes[:8] == bytes(8)
        if not write_permissions:
            for path in root.iterdir():
                path.chmod(stat.S_IRUSR)
            root.chmod(stat.S_IRUSR | stat.S_IXUSR)
        before = _register_snapshot(root)
        # Persist full initial fixture bytes and metadata outside the repository.
        snapshot = tmp_path / "initial-register-snapshot.json"
        snapshot.write_text(
            json.dumps(
                {
                    "bytes_hex": {k: v.hex() for k, v in before["bytes"].items()},
                    "metadata": before["metadata"],
                },
                sort_keys=True,
            )
        )
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe()
        reader = context.Process(
            target=_inspect_interrupted,
            args=(child, case.binding, case.assignment, case.zero),
        )
        reader.start()
        child.close()
        try:
            result = receive(parent)
            reader.join(20)
            assert reader.exitcode == 0
        finally:
            parent.close()
        after = _register_snapshot(root)
        (tmp_path / "inspection-result.json").write_text(
            json.dumps(
                {
                    "result": result,
                    "bytes_hex": {k: v.hex() for k, v in after["bytes"].items()},
                    "metadata": after["metadata"],
                },
                sort_keys=True,
            )
        )
        assert after["bytes"] == before["bytes"]
        for metadata in (before["metadata"], after["metadata"]):
            for values in metadata.values():
                values.pop("st_atime")
                values.pop("st_atime_ns")
        assert after["metadata"] == before["metadata"]
        assert register.PENDING in after["bytes"]
        assert result[0] == "error" or (
            result[0] == "inspection"
            and result[1]["prior_publisher_return"] == "not-established"
            and "register_pending" in result[1]["issues"]
            and not result[1]["events"]
        )
        if result[0] == "error":
            assert result[1] in {
                "register_unavailable",
                "unsafe_storage",
                "register_pending",
            }
    finally:
        for worker in (process, reader):
            if worker is not None and worker.is_alive():
                worker.kill()
                worker.join(20)
        connection.close()
        if not write_permissions:
            root.chmod(0o700)
            for path in root.iterdir():
                path.chmod(0o600)


@pytest.mark.parametrize(
    "phase",
    [
        "after_pending",
        "after_insert",
        "before_commit",
        "after_commit",
        "after_sync",
        "after_cleanup",
    ],
)
def test_process_loss_never_certifies_publisher_return(case, phase):
    process, connection = start_worker(case, bundle(case), phase)
    try:
        assert receive(connection) == "boundary"
        os.kill(process.pid, signal.SIGKILL)
        process.join(20)
        assert process.exitcode == -signal.SIGKILL
        try:
            result = inspect(case, case.zero)
        except review.ReviewError as error:
            assert error.code == "register_unavailable"
        else:
            assert result.prior_publisher_return == "not-established"
            if phase in {"after_commit", "after_sync", "after_cleanup"}:
                assert len(result.events) == 1 and result.checkpoint_status == "stale"
            if phase != "after_cleanup":
                assert "register_pending" in result.issues
    finally:
        if process.is_alive():
            process.kill()
            process.join(20)
        connection.close()


def test_two_process_duplicate_admission_and_active_reader(case):
    signed = bundle(case)
    workers = [start_worker(case, signed, "race") for _ in range(2)]
    try:
        for _, connection in workers:
            assert receive(connection) == "boundary"
        for _, connection in workers:
            connection.send("go")
        results = [receive(connection) for _, connection in workers]
        assert results.count(("result", "RECORDED")) == 1
        assert all(
            r
            in {
                ("result", "RECORDED"),
                ("result", "ALREADY_RECORDED"),
                ("error", "register_busy"),
            }
            for r in results
        )
        for (process, connection), result in zip(workers, results):
            if result[0] == "result":
                connection.send("finish")
            process.join(20)
            assert process.exitcode == 0
        assert len(inspect(case).events) == 1
        process, connection = start_worker(
            case, bundle(case, failure=("A1", "R3")), "after_insert"
        )
        try:
            assert receive(connection) == "boundary"
            with pytest.raises(review.ReviewError, match="^register_busy$"):
                inspect(case)
            connection.send("go")
            assert receive(connection) == ("result", "CONFLICT_RECORDED")
            connection.send("finish")
            process.join(20)
            assert process.exitcode == 0
        finally:
            if process.is_alive():
                process.kill()
                process.join(20)
            connection.close()
    finally:
        for process, connection in workers:
            if process.is_alive():
                process.kill()
                process.join(20)
            connection.close()


def assess(case, checkpoint, **changes):
    args = arguments(case)
    args.pop("register")
    revoked = changes.pop("revoked", False)
    args.update(changes)
    return register.assess_registered_review(
        case.binding,
        checkpoint=checkpoint,
        **args,
        policy=lambda: contracts.observation(case.policy, revoked=revoked),
        clock=lambda: contracts.NOW,
    )


def test_anchored_pending_and_missing_checkpoint(case):
    result = assess(case, case.zero)
    assert result.inputs.human_state == "PENDING"
    assert result.human_quality.status == result.assessment.status == "SKIP"
    assert result.inputs.verification.status == "PASS"
    assert result.details.checkpoint_status == "matches"
    assert result.details.reviewer_signature == "not-performed"
    assert result.inputs.historical_overall.status == "SKIP"
    missing = assess(case, None)
    assert missing.assessment.status == "ERROR"
    assert missing.inputs.human_state == "REJECTED"
    assert "checkpoint_missing" in missing.inputs.verification.issues


@pytest.mark.parametrize(
    "failure,unknown,exposure,quality,expected",
    [
        (None, None, "not_seen", "PASS", "PASS"),
        (("A1", "R3"), None, "not_seen", "FAIL", "FAIL"),
        (("A1", "R3"), ("A1", "R2"), "not_seen", "FAIL", "FAIL"),
        (("A1", "R3"), ("B2", "R2"), "not_seen", "FAIL", "FAIL"),
        (None, ("B2", "R2"), "not_seen", "SKIP", "SKIP"),
        (("A1", "R3"), ("B2", "R2"), "seen", "SKIP", "SKIP"),
    ],
)
def test_derived_quality_with_incomplete_and_disqualified_reviews(
    case, failure, unknown, exposure, quality, expected
):
    recorded = submit(
        case, bundle(case, failure=failure, unknown=unknown, exposure=exposure)
    )
    result = assess(case, recorded.checkpoint_candidate)
    assert result.human_quality.status == quality
    assert result.assessment.status == expected
    assert result.inputs.verification.status == "PASS"
    assert result.details.reviewer_signature == "verified"
    assert result.details.current_verified_at == review.utc_text(contracts.NOW)
    assert result.details.current_policy_observation_sha256 == fingerprint(
        contracts.observation(case.policy).model_dump(mode="json")
    )
    if failure:
        turn = next(t for t in result.turn_quality if t.slot == failure[0])
        assert turn.assessment.status == ("FAIL" if exposure == "not_seen" else "SKIP")
        if failure[1] in ("R3", "R4", "R6", "R7"):
            assert failure[1] in turn.critical_findings
    if unknown or exposure != "not_seen":
        assert result.inputs.review.whole_run_verdict is None
    assert not result.assurance.real_person_identity_authenticated
    assert not result.assurance.authorises_live_execution


def test_stale_checkpoint_does_not_hide_newer_authenticated_conflict(case):
    first = submit(case)
    conflict = submit(case, bundle(case, failure=("A1", "R3")))
    for checkpoint in (
        case.zero,
        first.checkpoint_candidate,
        conflict.checkpoint_candidate,
    ):
        result = assess(case, checkpoint)
        assert result.assessment.status == "ERROR"
        assert result.details.conflict_authentication == "authenticated"
        assert len(result.details.authenticated_reviews) == 2
        assert "review_conflict" in result.inputs.verification.issues
        if checkpoint != conflict.checkpoint_candidate:
            assert "checkpoint_stale" in result.inputs.verification.issues


def test_current_revocation_does_not_erase_historical_signature_or_conflict(case):
    submit(case)
    conflict = submit(case, bundle(case, failure=("A1", "R3")))
    before = packets.tree(case.binding.configuration.path)
    result = register.assess_registered_review(
        case.binding,
        checkpoint=conflict.checkpoint_candidate,
        **{k: v for k, v in arguments(case).items() if k != "register"},
        policy=lambda: contracts.observation(case.policy, revoked=True),
        clock=lambda: contracts.NOW,
    )
    assert result.assessment.status == "ERROR"
    assert result.details.reviewer_signature == "verified"
    assert result.details.current_policy == "error"
    assert result.details.conflict_authentication == "authenticated"
    assert {"review_conflict", "signer_revoked"}.issubset(
        result.inputs.verification.issues
    )
    assert packets.tree(case.binding.configuration.path) == before


def test_later_reliance_does_not_reapply_submission_window(case):
    from datetime import timedelta

    first = submit(case)
    later = contracts.NOW + timedelta(hours=25)
    result = register.assess_registered_review(
        case.binding,
        checkpoint=first.checkpoint_candidate,
        **{k: v for k, v in arguments(case).items() if k != "register"},
        policy=lambda: contracts.observation(case.policy, later),
        clock=lambda: later,
    )
    assert result.assessment.status == "PASS"


def test_source_corruption_preserves_recorded_findings_but_is_error(case):
    recorded = submit(case, bundle(case, failure=("A1", "R3"), unknown=("B2", "R2")))
    max(case.sample.linked.records.iterdir()).unlink()
    result = assess(case, recorded.checkpoint_candidate)
    assert result.assessment.status == "ERROR"
    assert result.human_quality.status == "FAIL"
    assert result.inputs.review.whole_run_verdict is None
    assert result.details.source_comparison == "error"
    assert (
        result.details.recorded_assessment_provenance == "anchored-envelope-status-only"
    )


def test_current_reliance_is_readonly_and_has_no_authority_side_effects(
    case, monkeypatch
):
    from harness.canary import approval_v3, authority_v3

    recorded = submit(case)
    before_source = packets.tree(case.sample.linked.registry.path)
    before_register = packets.tree(case.binding.configuration.path)

    def forbidden(*args, **kwargs):
        pytest.fail("Execution authority side effect")

    monkeypatch.setattr(approval_v3, "verify_approval", forbidden)
    monkeypatch.setattr(authority_v3, "inspect_consumption", forbidden)
    monkeypatch.setattr(authority_v3, "consume_approval", forbidden)
    result = assess(case, recorded.checkpoint_candidate)
    assert result.assessment.status == "PASS"
    assert (
        result.fresh_authority_store_inspection
        == result.fresh_approval_signature_authentication
        == "not-performed"
    )
    assert packets.tree(case.binding.configuration.path) == before_register
    assert packets.tree(case.sample.linked.registry.path) == before_source


def test_append_only_sql_constraints_and_reinitialization_denied(case):
    result = submit(case)
    path = Path(case.binding.configuration.path)
    before = packets.tree(path)
    with sqlite3.connect(path / register.DATABASE) as db:
        for sql in (
            "DELETE FROM events",
            "UPDATE events SET kind='conflict'",
            "DELETE FROM register_identity",
            "UPDATE register_identity SET zero_head='x'",
        ):
            with pytest.raises(sqlite3.DatabaseError):
                db.execute(sql)
    assert packets.tree(path) == before
    with pytest.raises(review.ReviewError, match="^initialization_failed$"):
        register.initialize_register(
            case.binding.configuration,
            protected_roots=(packets.protected(case.sample.linked.registry.path),),
        )
    assert inspect(case, result.checkpoint_candidate).state == "RECORDED"


def test_current_observation_cannot_regress_known_revocation_revision(case):
    observation = contracts.observation(case.policy).model_copy(
        update={"revocation_revision": 2}
    )
    result = submit(case, policy=lambda: observation)
    later = assess(case, result.checkpoint_candidate)
    assert later.assessment.status == "ERROR"
    assert "policy_changed" in later.inputs.verification.issues


def test_missing_register_is_never_an_empty_review_set(case):
    (Path(case.binding.configuration.path) / register.DATABASE).unlink()
    result = assess(case, case.zero)
    assert result.assessment.status == "ERROR"
    assert result.inputs.human_state == "REJECTED"
    assert result.details.register_state == "UNAVAILABLE"


def test_unsupported_wal_header_is_rejected_before_sqlite_can_create_sidecars(
    case, monkeypatch
):
    root = Path(case.binding.configuration.path)
    db = sqlite3.connect(root / register.DATABASE)
    assert db.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
    db.close()
    before = packets.tree(root)
    assert {p.name for p in root.iterdir()} == {register.DATABASE, register.LOCK}

    def forbidden(*args, **kwargs):
        pytest.fail("unsupported pager mode reached SQLite")

    monkeypatch.setattr(register, "_connect", forbidden)
    with pytest.raises(review.ReviewError, match="^register_corrupt$"):
        inspect(case, case.zero)
    assert packets.tree(root) == before


def test_expired_current_policy_preserves_mathematical_signature(case):
    from datetime import UTC, datetime

    result = submit(case)
    now = datetime(2026, 11, 24, tzinfo=UTC)
    report = register.assess_registered_review(
        case.binding,
        checkpoint=result.checkpoint_candidate,
        **{k: v for k, v in arguments(case).items() if k != "register"},
        policy=lambda: contracts.observation(case.policy, now),
        clock=lambda: now,
    )
    assert report.assessment.status == "ERROR"
    assert report.details.reviewer_signature == "verified"
    assert "policy_expired" in report.inputs.verification.issues


def test_cryptographically_forged_stored_conflict_is_not_promoted(case):
    import base64

    first = submit(case)
    conflict = submit(case, bundle(case, failure=("A1", "R3")))
    event = inspect(case, conflict.checkpoint_candidate).events[1]
    unknown_signature = case.keys.sign(
        event.payload_utf8.encode(), namespace=review.NAMESPACE, unknown=True
    )
    verification = event.verification.model_copy(
        update={"signature_sha256": sha256(unknown_signature).hexdigest()}
    )
    forged = event.model_copy(
        update={
            "signature_base64": base64.b64encode(unknown_signature).decode(),
            "verification": verification,
        }
    )
    forged = forged.model_copy(update={"event_sha256": register._event_digest(forged)})
    # Simulate a coherent outside-protocol edit; signature verification still rejects.
    with sqlite3.connect(
        Path(case.binding.configuration.path) / register.DATABASE
    ) as db:
        db.execute("DROP TRIGGER event_no_update")
        db.execute(
            "UPDATE events SET event_sha256=?,canonical_event=? WHERE sequence=2",
            (
                forged.event_sha256,
                review.encode(forged, register.MAX_EVENT_BYTES).decode(),
            ),
        )
        db.execute(next(s for s in register._SCHEMA if "TRIGGER event_no_update " in s))
    report = assess(case, first.checkpoint_candidate)
    assert report.assessment.status == "ERROR"
    assert report.details.conflict_authentication == "not-established"
    assert len(report.details.authenticated_reviews) == 1
    assert "review_conflict" not in report.inputs.verification.issues
    assert "signature_not_verified" in report.inputs.verification.issues


def test_policy_change_before_commit_rolls_back_without_conflict(case):
    count = 0

    def supplier():
        nonlocal count
        count += 1
        return contracts.observation(case.policy, revoked=count >= 3)

    with pytest.raises(review.ReviewError, match="^signer_revoked$"):
        submit(case, policy=supplier)
    result = inspect(case, case.zero)
    assert not result.events and not result.issues


def test_reader_close_error_is_not_success(case, monkeypatch):
    original = register.os.close
    root = Path(case.binding.configuration.path)
    lock_inode = (root / register.LOCK).stat().st_ino
    raised = False

    def close(fd):
        nonlocal raised
        info = os.fstat(fd)
        original(fd)
        if info.st_ino == lock_inode and not raised:
            raised = True
            raise OSError("PRIVATE_CLOSE")

    monkeypatch.setattr(register.os, "close", close)
    with pytest.raises(review.ReviewError):
        inspect(case, case.zero)


def test_import_and_reliance_audit_excludes_services_credentials_and_store_writes(case):
    import subprocess
    import sys

    result = submit(case)
    program = r"""
import json, os, sys, tempfile
tempfile.gettempdir()
def audit(event, args):
    if event.startswith("socket."):
        raise RuntimeError("network forbidden")
    if event == "import" and args[0].split(".")[0] in {"openai", "salesagent", "uvicorn"}:
        raise RuntimeError("application or SDK forbidden")
    if event == "sqlite3.connect" and "?mode=ro" not in args[0]:
        raise RuntimeError("non-readonly SQLite")
    if event == "subprocess.Popen":
        executable, command = args[0], args[1]
        if executable != "/usr/bin/ssh-keygen" or command[1:3] != ["-Y", "verify"]:
            raise RuntimeError("only public verification allowed")
    if event == "open":
        path, mode, flags = args
        if isinstance(path, str):
            if any(p in path for p in ("/.aws/", "/.ssh/", "credentials", "synthetic-primary", "synthetic-unknown")):
                raise RuntimeError("private identity read")
            if flags & (os.O_CREAT | os.O_WRONLY | os.O_RDWR | os.O_TRUNC) and "canary-review-public-verification-" not in path:
                raise RuntimeError("authoritative store write")
    if event in {"os.mkdir", "os.remove", "os.rmdir", "os.rename", "os.link", "os.symlink", "os.chmod"}:
        path = args[0]
        if isinstance(path, str) and "canary-review-public-verification-" not in path and path not in {"allowed-signers", "review.sig"}:
            raise RuntimeError("filesystem mutation")
class Environment(dict):
    def get(self, key, default=None):
        if key.startswith(("OPENAI_", "SALESAGENT_", "SSH_")):
            raise RuntimeError("credential lookup")
        return super().get(key, default)
    def __getitem__(self, key):
        if key.startswith(("OPENAI_", "SALESAGENT_", "SSH_")):
            raise RuntimeError("credential lookup")
        return super().__getitem__(key)
os.environ = Environment(os.environ)
sys.addaudithook(audit)
from harness.canary import human_review_v3 as h, review_register_v3 as r, journal_v3 as j
data = json.loads(sys.stdin.read())
binding = r.ReviewRegisterBinding.model_validate_json(json.dumps(data["binding"]))
assignment = h.ReviewAssignment.model_validate_json(json.dumps(data["assignment"]))
checkpoint = r.ReviewRegisterCheckpoint.model_validate_json(json.dumps(data["checkpoint"]))
registry = j.RegistryBinding.model_validate_json(json.dumps(data["registry"]))
observation = h.ReviewPolicyObservation.model_validate_json(json.dumps(data["observation"]))
report = r.assess_registered_review(binding, expected=assignment, checkpoint=checkpoint,
    envelope_raw=data["envelope"].encode(), registry=registry,
    policy=lambda: observation, clock=lambda: h.time_value(data["now"]))
assert report.assessment.status == "PASS"
assert not report.assurance.authorises_live_execution
print("synthetic-readonly")
"""
    data = {
        "binding": case.binding.model_dump(mode="json"),
        "assignment": case.assignment.model_dump(mode="json"),
        "checkpoint": result.checkpoint_candidate.model_dump(mode="json"),
        "registry": case.sample.linked.registry.model_dump(mode="json"),
        "observation": contracts.observation(case.policy).model_dump(mode="json"),
        "envelope": case.sample.raw.decode(),
        "now": review.utc_text(contracts.NOW),
    }
    before = packets.tree(case.binding.configuration.path)
    completed = subprocess.run(
        [sys.executable, "-B", "-c", program],
        input=json.dumps(data).encode(),
        capture_output=True,
        check=False,
        timeout=30,
        env={
            "PATH": "/usr/bin:/bin",
            "LC_ALL": "C",
            "LANG": "C",
            "PYTHONPATH": "src",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )
    assert completed.returncode == 0, completed.stderr.decode()
    assert completed.stdout == b"synthetic-readonly\n"
    assert packets.tree(case.binding.configuration.path) == before
