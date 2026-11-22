"""Offline, actual-signature authority tests; coordinated processes, no servers."""

from __future__ import annotations

import multiprocessing
import os
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
import test_canary_approval_v3 as approved_tests
from pydantic import ValidationError

from harness.canary import approval_v3 as approval
from harness.canary import authority_v3 as authority
from harness.core.fingerprints import canonical_json, fingerprint

NOW = approved_tests.NOW
keys = approved_tests.keys
manifest = approved_tests.manifest
policy = approved_tests.policy
proposal = approved_tests.proposal
signed = approved_tests.signed

pytestmark = pytest.mark.usefixtures("keys", "manifest", "policy", "proposal", "signed")


def observation(policy, now=NOW):
    return authority.PolicyObservation(
        schema_id="canary-synthetic-policy-observation-v1",
        policy=policy,
        observed_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        expires_at=(now + timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def configuration(path, policy, proposal):
    return authority.TrustedStoreConfiguration(
        schema_id="canary-synthetic-authority-config-v1",
        store_path=str(path.resolve()),
        store_id="synthetic-store-" + uuid4().hex,
        execution_audience=proposal.execution_audience,
        trust_policy_identity_sha256=authority.policy_identity(policy),
        host_id="synthetic-unit-test-host",
        host_scope="synthetic-single-host-local",
    )


@pytest.fixture
def store(tmp_path, policy, proposal):
    return authority.initialize_store(
        configuration(tmp_path / "authority", policy, proposal)
    )


def consume(signed, proposal, policy, store, *, now=NOW, supplier=None, clock=None):
    return authority.consume_approval(
        *signed,
        expected=proposal,
        store=store,
        policy=supplier or (lambda: observation(policy, now)),
        clock=clock or (lambda: now),
    )


def database(store):
    return Path(store.configuration.store_path) / "authority.sqlite3"


def alter(manifest, keys, **fields):
    changed = manifest.model_copy(update=fields)
    raw = approval.serialize_manifest(changed)
    return raw, keys.sign(raw)


def independent(manifest, keys):
    expected = manifest.execution.model_copy(
        update={"authorisation_id": "synthetic-auth-" + uuid4().hex}
    )
    return alter(manifest, keys, execution=expected), expected


def inspect(store, proposal):
    return authority.inspect_consumption(store, proposal.authorisation_id)


def deny(code, signed, proposal, policy, store, **kwargs):
    with pytest.raises(
        (authority.AuthorityError, approval.ApprovalError), match="^" + code + "$"
    ):
        consume(signed, proposal, policy, store, **kwargs)


def test_explicit_initialization_and_durable_settings(store):
    root = Path(store.configuration.store_path)
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert {p.name for p in root.iterdir()} == {"authority.sqlite3", "writer.lock"}
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in root.iterdir())
    with authority._open(store, readonly=False) as storage:
        assert storage.connection.execute("PRAGMA synchronous").fetchone() == (3,)
        assert storage.connection.execute("PRAGMA fullfsync").fetchone() == (1,)
        assert storage.connection.execute("PRAGMA journal_mode").fetchone() == (
            "delete",
        )
        assert storage.connection.execute("PRAGMA cache_spill").fetchone() == (0,)
        assert authority._validate(storage) == {}
    with pytest.raises(authority.AuthorityError, match="^store_initialization_failed$"):
        authority.initialize_store(store.configuration)
    assert database(store).exists()


def test_first_consumption_binds_exact_evidence_and_unique_run(
    store, signed, proposal, policy
):
    verified = approval.verify_approval(
        *signed, expected=proposal, trust_policy=policy, now=NOW
    )
    assert inspect(store, proposal).status == "absent"
    record = consume(signed, proposal, policy, store)
    assert record.authorisation_id == proposal.authorisation_id
    assert record.payload_sha256 == sha256(signed[0]).hexdigest()
    assert record.signature_sha256 == sha256(signed[1]).hexdigest()
    assert record.trust_policy_sha256 == fingerprint(policy.model_dump(mode="json"))
    assert record.proposal_sha256 == fingerprint(proposal.model_dump(mode="json"))
    assert record.source_receipt_sha256 == proposal.source_receipt_sha256
    assert record.verification_sha256 == fingerprint(verified.model_dump(mode="json"))
    assert record.signer_principal == policy.expected_principal
    assert record.execution_audience == proposal.execution_audience
    assert record.store_id == store.configuration.store_id
    assert record.intended_run_id.startswith("synthetic-run-")
    # The unchanged journal accepts this identifier; no journal is constructed.
    from harness.canary.journal_v3 import _identifier

    assert _identifier(record.intended_run_id) == record.intended_run_id
    assert inspect(store, proposal).record == record
    assert not any(
        getattr(record, name)
        for name in (
            "real_human_authorisation_authenticated",
            "source_authorised",
            "provider_evidence_authenticated",
            "authorises_live_execution",
        )
    )
    with pytest.raises(ValidationError):
        record.intended_run_id = "synthetic-run-" + "0" * 32
    deny("authorisation_consumed", signed, proposal, policy, store)
    assert inspect(store, proposal).record == record


def test_verification_and_inspection_never_consume(
    store, signed, proposal, policy, monkeypatch
):
    before = database(store).read_bytes()
    for _ in range(2):
        approval.verify_approval(
            *signed, expected=proposal, trust_policy=policy, now=NOW
        )
        assert inspect(store, proposal).status == "absent"
    monkeypatch.setattr(
        approval, "verify_approval", lambda *a, **k: pytest.fail("inspection verified")
    )
    with authority._open(store, readonly=True) as storage:
        assert storage.connection.execute("PRAGMA query_only").fetchone() == (1,)
        with pytest.raises(sqlite3.OperationalError):
            storage.connection.execute("DELETE FROM consumptions")
    assert inspect(store, proposal).status == "absent"
    assert database(store).read_bytes() == before
    assert len(list(database(store).parent.iterdir())) == 2


@pytest.mark.parametrize("change", ["expiry", "proposal", "policy"])
def test_same_identifier_changed_binding_conflicts(
    change, store, signed, proposal, policy, manifest, keys
):
    first = consume(signed, proposal, policy, store)
    expected, trusted = proposal, policy
    if change == "expiry":
        changed = alter(manifest, keys, expires_at="2026-11-22T12:29:00Z")
    elif change == "proposal":
        expected = proposal.model_copy(update={"project_id": "proj_synthetic_changed"})
        changed = alter(manifest, keys, execution=expected)
    else:
        trusted = policy.model_copy(
            update={"revoked_public_keys": (keys.unknown_public_key,)}
        )
        changed = signed
    deny("authorisation_conflict", changed, expected, trusted, store)
    assert inspect(store, proposal).record == first


def test_distinct_approvals_have_distinct_store_assigned_identities(
    store, signed, proposal, policy, manifest, keys
):
    first = consume(signed, proposal, policy, store)
    other, expected = independent(manifest, keys)
    second = consume(other, expected, policy, store)
    assert first.intended_run_id != second.intended_run_id
    assert first.record_id != second.record_id
    changed = first.model_copy(update={"intended_run_id": second.intended_run_id})
    result = authority.inspect_consumption(
        store, proposal.authorisation_id, expected_record=changed
    )
    assert result.status == "conflict" and result.record == first
    with pytest.raises(TypeError):
        authority.consume_approval(
            *signed,
            expected=proposal,
            store=store,
            policy=lambda: observation(policy),
            clock=lambda: NOW,
            intended_run_id=second.intended_run_id,
        )


@pytest.mark.parametrize(
    "kind",
    [
        "invalid",
        "unknown",
        "namespace",
        "principal",
        "role",
        "revoked",
        "expired",
        "early",
        "expected",
        "canonical",
        "duplicate",
        "malformed",
    ],
)
def test_actual_signature_and_binding_denials(
    kind, tmp_path, signed, proposal, policy, manifest, keys
):
    now, trusted, expected = NOW, policy, proposal
    original = signed
    if kind == "invalid":
        signed = (signed[0], b"invalid synthetic signature")
    elif kind == "unknown":
        signed = (signed[0], keys.sign(signed[0], unknown=True))
    elif kind == "namespace":
        signed = (
            signed[0],
            keys.sign(signed[0], namespace="synthetic-wrong-namespace"),
        )
    elif kind == "principal":
        trusted = policy.model_copy(
            update={"expected_principal": "synthetic-other@canary.invalid"}
        )
    elif kind == "role":
        trusted = policy.model_copy(update={"roles": ("synthetic-observer",)})
    elif kind == "revoked":
        trusted = policy.model_copy(update={"revoked_public_keys": (keys.public_key,)})
    elif kind == "expired":
        now += timedelta(minutes=30)
    elif kind == "early":
        now -= timedelta(seconds=1)
    elif kind == "expected":
        expected = proposal.model_copy(update={"project_id": "proj_synthetic_changed"})
    elif kind == "canonical":
        raw = signed[0] + b"\n"
        signed = (raw, keys.sign(raw))
    elif kind == "duplicate":
        raw = b'{"schema_id":"canary-synthetic-approval-v1",' + signed[0][1:]
        signed = (raw, keys.sign(raw))
    elif kind == "malformed":
        signed = (b"{}", keys.sign(b"{}"))
    store = authority.initialize_store(
        configuration(tmp_path / "authority", trusted, proposal)
    )
    with pytest.raises(approval.ApprovalError):
        consume(signed, expected, trusted, store, now=now)
    assert inspect(store, proposal).status == "absent"
    assert len(list(database(store).parent.iterdir())) == 2
    assert original[0] not in database(store).read_bytes()


@pytest.mark.parametrize(
    "kind,code",
    [
        ("audience", "audience_mismatch"),
        ("policy", "policy_binding_mismatch"),
        ("stale", "policy_stale"),
        ("future", "policy_stale"),
        ("bad_supplier", "invalid_policy_snapshot"),
        ("naive", "invalid_clock"),
        ("fractional", "invalid_clock"),
    ],
)
def test_independent_boundary_rejections(
    kind, code, tmp_path, signed, proposal, policy
):
    config = configuration(tmp_path / "authority", policy, proposal)
    if kind == "audience":
        config = config.model_copy(
            update={"execution_audience": "synthetic-other-host"}
        )
    store = authority.initialize_store(config)
    trusted = (
        policy.model_copy(update={"policy_id": "synthetic-policy-changed"})
        if kind == "policy"
        else policy
    )
    snapshot = observation(trusted)
    if kind in {"stale", "future"}:
        snapshot = observation(
            trusted, NOW + timedelta(seconds=-30 if kind == "stale" else 1)
        )
    supplier = lambda: snapshot
    if kind == "bad_supplier":
        supplier = lambda: (_ for _ in ()).throw(RuntimeError("private-sentinel"))
    now = NOW.replace(tzinfo=None) if kind == "naive" else NOW
    if kind == "fractional":
        now = NOW.replace(microsecond=1)
    deny(code, signed, proposal, trusted, store, now=now, supplier=supplier)
    assert inspect(store, proposal).status == "absent"


@pytest.mark.parametrize("phase", ["after_verification", "after_insert"])
@pytest.mark.parametrize("change", ["expiry", "revocation", "stale"])
def test_boundary_changes_fail_closed(
    phase, change, store, signed, proposal, policy, monkeypatch
):
    current = {"now": NOW, "policy": policy, "stale": False}

    def modify():
        if change == "expiry":
            current["now"] = NOW + timedelta(minutes=30)
        elif change == "revocation":
            current["policy"] = policy.model_copy(
                update={"revoked_public_keys": (policy.public_key,)}
            )
        else:
            current["stale"] = True

    if phase == "after_verification":
        real = approval.verify_approval

        def hook(*args, **kwargs):
            result = real(*args, **kwargs)
            modify()
            return result

        monkeypatch.setattr(approval, "verify_approval", hook)
    else:
        real = authority._insert

        def hook(*args, **kwargs):
            real(*args, **kwargs)
            modify()

        monkeypatch.setattr(authority, "_insert", hook)

    def supplier():
        return observation(
            current["policy"],
            NOW - timedelta(seconds=30) if current["stale"] else current["now"],
        )

    with pytest.raises((approval.ApprovalError, authority.AuthorityError)):
        consume(
            signed,
            proposal,
            policy,
            store,
            clock=lambda: current["now"],
            supplier=supplier,
        )
    assert inspect(store, proposal).status == "absent"
    assert not (database(store).parent / "pending-consumption.json").exists()


def test_sql_constraints_and_append_only_records(store, signed, proposal, policy):
    record = consume(signed, proposal, policy, store)
    with sqlite3.connect(database(store)) as db:
        for sql in (
            "DELETE FROM consumptions",
            "UPDATE consumptions SET record_sha256 = 'changed'",
            "DELETE FROM store_identity",
            "UPDATE store_identity SET binding_sha256 = 'changed'",
            "INSERT INTO store_identity SELECT * FROM store_identity",
            "INSERT INTO consumptions SELECT * FROM consumptions",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(sql)
    assert inspect(store, proposal).record == record


def _worker(pipe, bundle, mode):
    """Spawned child receives public synthetic artifacts; key paths never sent."""
    signed, proposal_json, policy_json, binding_json = bundle
    expected = approval.ProposedCanary.model_validate_json(proposal_json)
    trusted = approval.SyntheticTrustPolicy.model_validate_json(policy_json)
    binding = authority.AuthorityStoreBinding.model_validate_json(binding_json)
    state = {"now": NOW, "policy": trusted}
    if mode == "hold_transaction":
        real_begin = authority._begin

        def held(db):
            real_begin(db)
            pipe.send("transaction_held")
            assert pipe.recv() == "released"

        authority._begin = held
    elif mode in {"expiry_wait", "revoke_wait"}:
        real_begin = authority._begin

        def blocked(db):
            db.execute("PRAGMA busy_timeout = 0")
            try:
                real_begin(db)
            except sqlite3.OperationalError as error:
                assert error.sqlite_errorcode == sqlite3.SQLITE_BUSY
            else:
                raise AssertionError("expected held SQLite write lock")
            pipe.send("sqlite_busy")
            assert pipe.recv() == "released"
            db.execute("PRAGMA busy_timeout = 2000")
            if mode == "expiry_wait":
                state["now"] = NOW + timedelta(minutes=30)
            else:
                state["policy"] = trusted.model_copy(
                    update={"revoked_public_keys": (trusted.public_key,)}
                )
            real_begin(db)

        authority._begin = blocked
    elif mode.startswith("crash_"):
        seam = mode.removeprefix("crash_")
        targets = {
            "before_verify": (approval, "verify_approval", False),
            "before_transaction": (authority, "_begin", False),
            "before_insert": (authority, "_insert", False),
            "after_insert": (authority, "_insert", True),
            "before_commit": (authority, "_commit", False),
            "after_commit": (authority, "_commit", True),
            "after_sync": (authority, "_sync", True),
        }
        module, name, after = targets[seam]
        real = getattr(module, name)

        def crash(*args, **kwargs):
            if after:
                real(*args, **kwargs)
            pipe.send("crash_boundary")
            pipe.recv()  # parent kills this process: no Python finally/close
            raise AssertionError("crash barrier escaped")

        setattr(module, name, crash)
    pipe.send("ready")
    assert pipe.recv() == "go"
    while True:
        try:
            result = authority.consume_approval(
                *signed,
                expected=expected,
                store=binding,
                policy=lambda: observation(state["policy"], state["now"]),
                clock=lambda: state["now"],
            )
            pipe.send(("success", result.model_dump_json()))
        except (authority.AuthorityError, approval.ApprovalError) as error:
            pipe.send(("denied", str(error)))
        command = pipe.recv()
        if command == "stop":
            break
        assert command == "retry_known_busy"
    pipe.close()


def start_worker(signed, proposal, policy, store, mode="normal"):
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    bundle = (
        signed,
        proposal.model_dump_json(),
        policy.model_dump_json(),
        store.model_dump_json(),
    )
    process = context.Process(target=_worker, args=(child, bundle, mode))
    process.start()
    child.close()
    assert receive(parent) == "ready"
    return process, parent


def receive(pipe):
    assert pipe.poll(20), "worker did not reach coordinated boundary"
    return pipe.recv()


def finish(worker):
    process, pipe = worker
    if process.is_alive():
        pipe.send("stop")
    process.join(20)
    if process.is_alive():
        process.kill()
        process.join(5)
        pytest.fail("worker did not stop")
    pipe.close()
    assert process.exitcode == 0


@pytest.mark.parametrize("mode", ["expiry_wait", "revoke_wait"])
def test_sqlite_wait_rechecks_current_time_and_revocation(
    mode, store, signed, proposal, policy
):
    blocker = sqlite3.connect(database(store), isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")
    worker = start_worker(signed, proposal, policy, store, mode)
    try:
        worker[1].send("go")
        assert receive(worker[1]) == "sqlite_busy"
        blocker.execute("ROLLBACK")
        worker[1].send("released")
        kind, code = receive(worker[1])
        assert kind == "denied"
        assert code == (
            "approval_expired" if mode == "expiry_wait" else "signer_revoked"
        )
    finally:
        blocker.close()
        finish(worker)
    assert inspect(store, proposal).status == "absent"


@pytest.mark.parametrize("distinct", [False, True])
def test_process_races_same_and_distinct_authorisations(
    distinct, store, signed, proposal, policy, manifest, keys
):
    inputs = [
        independent(manifest, keys) if distinct else (signed, proposal)
        for _ in range(4)
    ]
    workers = [start_worker(pair, expected, policy, store) for pair, expected in inputs]
    try:
        for _, pipe in workers:
            pipe.send("go")
        results = [receive(pipe) for _, pipe in workers]
        assert any(kind == "success" for kind, _ in results)
        # Explicit retries occur only for a known non-admission busy denial, after
        # all first attempts ended. The production API itself never retries.
        for index, (_, code) in enumerate(results):
            if code == "store_busy":
                workers[index][1].send("retry_known_busy")
                results[index] = receive(workers[index][1])
        successes = [
            authority.ConsumptionReceipt.model_validate_json(raw)
            for kind, raw in results
            if kind == "success"
        ]
        assert len(successes) == (4 if distinct else 1)
        assert len({record.intended_run_id for record in successes}) == len(successes)
        if not distinct:
            assert all(
                kind == "success" or code == "authorisation_consumed"
                for kind, code in results
            )
        for _, expected in inputs:
            assert inspect(store, expected).status == "consumed"
    finally:
        for worker in workers:
            finish(worker)


def test_concurrent_alias_and_copied_store_cannot_bypass_active_writer(
    tmp_path, store, signed, proposal, policy
):
    root = database(store).parent
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    copy = tmp_path / "copy"
    shutil.copytree(root, copy)
    winner = start_worker(signed, proposal, policy, store, "hold_transaction")
    competitors = []
    try:
        winner[1].send("go")
        assert receive(winner[1]) == "transaction_held"
        assert inspect(store, proposal).issues == ("store_busy",)
        for path, code in (
            (alias, "store_unavailable"),
            (copy, "store_identity_mismatch"),
        ):
            config = store.configuration.model_copy(update={"store_path": str(path)})
            alternate = store.model_copy(update={"configuration": config})
            worker = start_worker(signed, proposal, policy, alternate)
            competitors.append(worker)
            worker[1].send("go")
            assert receive(worker[1]) == ("denied", code)
        winner[1].send("released")
        kind, document = receive(winner[1])
        assert kind == "success"
        record = authority.ConsumptionReceipt.model_validate_json(document)
        assert inspect(store, proposal).record == record
    finally:
        for worker in competitors:
            finish(worker)
        finish(winner)


@pytest.mark.parametrize(
    "boundary",
    [
        "before_verify",
        "before_transaction",
        "before_insert",
        "after_insert",
        "before_commit",
        "after_commit",
        "after_sync",
    ],
)
def test_process_death_at_transaction_boundaries(
    boundary, store, signed, proposal, policy, manifest, keys
):
    previous_signed, previous_proposal = independent(manifest, keys)
    previous = consume(previous_signed, previous_proposal, policy, store)
    database_before = database(store).read_bytes()
    worker = start_worker(signed, proposal, policy, store, "crash_" + boundary)
    process, pipe = worker
    try:
        pipe.send("go")
        assert receive(pipe) == "crash_boundary"
        process.kill()
        process.join(20)
        assert process.exitcode == -signal.SIGKILL
    finally:
        if process.is_alive():
            process.kill()
            process.join(5)
        pipe.close()
    result = inspect(store, proposal)
    if boundary in {"after_commit", "after_sync"}:
        assert result.status == "consumed"
        assert "pending_consumption" in result.issues
    else:
        assert result.status in {"absent", "unavailable"}
        assert database(store).read_bytes() == database_before
    if boundary in {"before_verify", "before_transaction"}:
        # This test owns the crashed process and proves no transaction began;
        # inspection alone is never sufficient evidence to retry.
        record = consume(signed, proposal, policy, store)
        assert record.authorisation_id == proposal.authorisation_id
    else:
        deny("store_pending", signed, proposal, policy, store)
    earlier = inspect(store, previous_proposal)
    if earlier.status == "unavailable":
        # A hot journal cannot be recovered by read-only inspection. The old
        # database pages remain byte-preserved because cache_spill is disabled.
        assert "store_unavailable" in earlier.issues
    else:
        assert earlier.record == previous


def test_after_return_and_downstream_failure_never_reopens(
    store, signed, proposal, policy
):
    record = consume(signed, proposal, policy, store)
    with pytest.raises(OSError):
        raise OSError("synthetic downstream journal failure")
    assert inspect(store, proposal).record == record
    approval.verify_approval(*signed, expected=proposal, trust_policy=policy, now=NOW)
    deny("authorisation_consumed", signed, proposal, policy, store)
    assert inspect(store, proposal).record == record


def test_process_death_after_receipt_return_is_still_consumed(
    store, signed, proposal, policy
):
    process, pipe = start_worker(signed, proposal, policy, store)
    try:
        pipe.send("go")
        kind, document = receive(pipe)
        assert kind == "success"
        record = authority.ConsumptionReceipt.model_validate_json(document)
        process.kill()
        process.join(20)
        assert process.exitcode == -signal.SIGKILL
    finally:
        if process.is_alive():
            process.kill()
            process.join(5)
        pipe.close()
    assert inspect(store, proposal).record == record
    deny("authorisation_consumed", signed, proposal, policy, store)


def test_real_sqlite_full_rolls_back_and_preserves_existing_record(
    tmp_path, signed, proposal, policy, manifest, keys, monkeypatch
):
    connect = authority._connect

    def small_pages(path, *, readonly):
        connection = connect(path, readonly=readonly)
        if not readonly and connection.execute("PRAGMA user_version").fetchone() == (
            0,
        ):
            connection.execute("PRAGMA page_size = 512")
        return connection

    monkeypatch.setattr(authority, "_connect", small_pages)
    store = authority.initialize_store(
        configuration(tmp_path / "authority", policy, proposal)
    )
    old_signed, old_proposal = independent(manifest, keys)
    previous = consume(old_signed, old_proposal, policy, store)
    begin = authority._begin
    errors = []
    insert = authority._insert

    def no_more_pages(connection):
        count = connection.execute("PRAGMA page_count").fetchone()[0]
        connection.execute(f"PRAGMA max_page_count = {count:d}")
        begin(connection)

    def capture_full(connection, record):
        try:
            insert(connection, record)
        except sqlite3.OperationalError as error:
            errors.append(error.sqlite_errorcode)
            raise

    monkeypatch.setattr(authority, "_begin", no_more_pages)
    monkeypatch.setattr(authority, "_insert", capture_full)
    deny("consumption_failed_uncommitted", signed, proposal, policy, store)
    assert errors == [sqlite3.SQLITE_FULL]
    assert inspect(store, old_proposal).record == previous
    assert inspect(store, proposal).status == "absent"
    assert {p.name for p in database(store).parent.iterdir()} == {
        "authority.sqlite3",
        "writer.lock",
    }


def test_rollback_failure_keeps_pending_marker(
    store, signed, proposal, policy, monkeypatch
):
    def close_during_insert(connection, record):
        connection.close()
        raise OSError("synthetic storage interruption")

    monkeypatch.setattr(authority, "_insert", close_during_insert)
    deny("consumption_outcome_unknown", signed, proposal, policy, store)
    deny("store_pending", signed, proposal, policy, store)
    result = inspect(store, proposal)
    assert result.status == "absent" and result.issues == ("pending_consumption",)


@pytest.mark.parametrize(
    "mode",
    [
        "disk_full",
        "io",
        "commit_before",
        "commit_after",
        "sync",
        "cleanup",
        "partial_marker",
    ],
)
def test_storage_failures_preserve_history_and_never_auto_retry(
    mode, store, signed, proposal, policy, manifest, keys, monkeypatch
):
    old_signed, old_proposal = independent(manifest, keys)
    previous = consume(old_signed, old_proposal, policy, store)
    attempts = []

    def failure(*args):
        attempts.append(1)
        raise sqlite3.OperationalError("private-path-sentinel: disk full / I/O error")

    if mode in {"disk_full", "io"}:
        monkeypatch.setattr(authority, "_insert", failure)
    elif mode == "commit_before":
        monkeypatch.setattr(authority, "_commit", failure)
    elif mode == "commit_after":
        real = authority._commit

        def committed(db):
            real(db)
            failure()

        monkeypatch.setattr(authority, "_commit", committed)
    elif mode == "sync":
        monkeypatch.setattr(authority, "_sync", failure)
    elif mode == "cleanup":
        monkeypatch.setattr(authority, "_clear_pending", failure)
    else:

        def partial(storage, record):
            path = database(store).parent / "pending-consumption.json"
            path.write_bytes(b"partial")
            path.chmod(0o600)
            failure()

        monkeypatch.setattr(authority, "_pending", partial)
    code = (
        "consumption_failed_uncommitted"
        if mode in {"disk_full", "io", "partial_marker"}
        else "consumption_outcome_unknown"
    )
    deny(code, signed, proposal, policy, store)
    assert len(attempts) == 1
    result = inspect(store, proposal)
    if mode in {"commit_after", "sync", "cleanup"}:
        assert result.status == "consumed" and "pending_consumption" in result.issues
    elif mode == "partial_marker":
        assert result.status == "corrupt"
    else:
        assert result.status == "absent"
    if mode not in {"partial_marker"}:
        assert inspect(store, old_proposal).record == previous
    if mode not in {"disk_full", "io"}:
        deny("store_pending", signed, proposal, policy, store)


def test_sqlite_busy_timeout_is_fixed_and_preserves_history(
    store, signed, proposal, policy, monkeypatch
):
    blocker = sqlite3.connect(database(store), isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")
    real = authority._begin

    def no_wait(db):
        assert db.execute("PRAGMA busy_timeout").fetchone() == (2000,)
        db.execute("PRAGMA busy_timeout = 0")
        real(db)

    monkeypatch.setattr(authority, "_begin", no_wait)
    try:
        deny("store_busy", signed, proposal, policy, store)
    finally:
        blocker.close()
    assert inspect(store, proposal).status == "absent"


@pytest.mark.parametrize(
    "kind",
    [
        "schema",
        "row_json",
        "row_digest",
        "row_binding",
        "truncate",
        "header",
        "version",
        "identity",
    ],
)
def test_corrupt_or_tampered_store_denies(kind, store, signed, proposal, policy):
    record = consume(signed, proposal, policy, store)
    path = database(store)
    if kind == "truncate":
        with path.open("r+b") as stream:
            stream.truncate(200)
    elif kind == "header":
        with path.open("r+b") as stream:
            stream.write(b"corrupted header")
    else:
        with sqlite3.connect(path) as db:
            if kind == "schema":
                db.execute("CREATE TABLE extra (value TEXT)")
            elif kind == "version":
                db.execute("PRAGMA user_version = 9")
            elif kind == "identity":
                db.execute("DROP TRIGGER identity_no_update")
                db.execute("UPDATE store_identity SET binding_sha256 = ?", ("0" * 64,))
                db.execute(
                    {name: sql for _, name, _, sql in authority._DDL}[
                        "identity_no_update"
                    ]
                )
            else:
                db.execute("DROP TRIGGER consumption_no_update")
                if kind == "row_json":
                    db.execute(
                        "UPDATE consumptions SET record_json = ?", ('{"truncated":',)
                    )
                elif kind == "row_digest":
                    db.execute("UPDATE consumptions SET record_sha256 = ?", ("0" * 64,))
                else:
                    changed = record.model_copy(
                        update={"store_id": "synthetic-store-" + "0" * 32}
                    ).model_dump(mode="json")
                    db.execute(
                        "UPDATE consumptions SET record_json = ?, record_sha256 = ?",
                        (canonical_json(changed), fingerprint(changed)),
                    )
                db.execute(
                    {name: sql for _, name, _, sql in authority._DDL}[
                        "consumption_no_update"
                    ]
                )
    result = inspect(store, proposal)
    assert result.status in {"corrupt", "unavailable"}
    assert result.record is None
    before = path.read_bytes()
    with pytest.raises(authority.AuthorityError):
        consume(signed, proposal, policy, store)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "component,mode",
    [("root", 0o755), ("database", 0o644), ("lock", 0o644), ("root", 0o777)],
)
def test_private_permissions_required(component, mode, store, signed, proposal, policy):
    path = {
        "root": database(store).parent,
        "database": database(store),
        "lock": database(store).parent / "writer.lock",
    }[component]
    path.chmod(mode)
    assert inspect(store, proposal).status == "unavailable"
    deny("store_permissions", signed, proposal, policy, store)


@pytest.mark.parametrize(
    "kind",
    [
        "database",
        "lock",
        "root",
        "symlink_database",
        "symlink_root",
        "hardlink",
        "fifo",
        "extra",
        "wal",
        "journal",
    ],
)
def test_substitution_and_sidecars_never_reset_or_recover(
    kind, store, signed, proposal, policy
):
    root = database(store).parent
    path = root / ("writer.lock" if kind == "lock" else "authority.sqlite3")
    if kind in {"database", "lock"}:
        saved = root.parent / "saved"
        shutil.copyfile(path, saved)
        saved.chmod(0o600)
        os.replace(saved, path)
    elif kind in {"root", "symlink_root"}:
        saved = root.with_name("old-root")
        root.rename(saved)
        if kind == "root":
            shutil.copytree(saved, root)
        else:
            root.symlink_to(saved, target_is_directory=True)
    elif kind == "symlink_database":
        saved = root.parent / "saved"
        path.rename(saved)
        path.symlink_to(saved)
    elif kind == "hardlink":
        os.link(path, root.parent / "alias")
    elif kind == "fifo":
        path.unlink()
        os.mkfifo(path, 0o600)
    elif kind in {"extra", "wal", "journal"}:
        extra = (
            root
            / {
                "extra": "unexpected",
                "wal": "authority.sqlite3-wal",
                "journal": "authority.sqlite3-journal",
            }[kind]
        )
        extra.write_bytes(b"")
        extra.chmod(0o600)
    before = {p.name for p in root.iterdir()}
    with pytest.raises(authority.AuthorityError):
        consume(signed, proposal, policy, store)
    assert {p.name for p in root.iterdir()} == before
    result = inspect(store, proposal)
    if kind == "journal":
        assert result.status == "absent" and result.issues == (
            "rollback_journal_present",
        )
        assert extra.exists()
    else:
        assert result.status in {"unavailable", "corrupt"}


def test_alternate_directory_and_copied_binding_are_denied(
    tmp_path, store, signed, proposal, policy
):
    root = database(store).parent
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    config = store.configuration.model_copy(update={"store_path": str(alias)})
    alias_binding = store.model_copy(update={"configuration": config})
    assert (
        authority.inspect_consumption(alias_binding, proposal.authorisation_id).status
        == "unavailable"
    )
    deny("store_unavailable", signed, proposal, policy, alias_binding)
    copy = tmp_path / "copy"
    shutil.copytree(root, copy)
    config = store.configuration.model_copy(update={"store_path": str(copy)})
    copied = store.model_copy(update={"configuration": config})
    deny("store_identity_mismatch", signed, proposal, policy, copied)
    assert inspect(store, proposal).status == "absent"


@pytest.mark.parametrize("target", ["directory", "database", "lock"])
def test_missing_established_store_never_created(
    target, store, signed, proposal, policy
):
    path = database(store)
    if target == "directory":
        shutil.rmtree(path.parent)
    else:
        (path if target == "database" else path.parent / "writer.lock").unlink()
    assert inspect(store, proposal).status == "unavailable"
    deny("store_unavailable", signed, proposal, policy, store)
    assert (
        not path.parent.exists()
        if target == "directory"
        else len(list(path.parent.iterdir())) == 1
    )


def test_partial_initialization_is_not_reused(tmp_path, policy, proposal, monkeypatch):
    config = configuration(tmp_path / "authority", policy, proposal)

    def fail(*args, **kwargs):
        raise OSError("private initialization sentinel")

    with monkeypatch.context() as patch:
        patch.setattr(authority, "_connect", fail)
        with pytest.raises(
            authority.AuthorityError, match="^store_initialization_failed$"
        ):
            authority.initialize_store(config)
    contents = {p.name: p.read_bytes() for p in Path(config.store_path).iterdir()}
    with pytest.raises(authority.AuthorityError, match="^store_initialization_failed$"):
        authority.initialize_store(config)
    assert {
        p.name: p.read_bytes() for p in Path(config.store_path).iterdir()
    } == contents


def test_repository_and_symlink_initialization_denied(tmp_path, policy, proposal):
    repo = tmp_path / "repository"
    repo.mkdir()
    (repo / ".git").mkdir()
    with pytest.raises(authority.AuthorityError):
        authority.initialize_store(configuration(repo / "authority", policy, proposal))
    assert not (repo / "authority").exists()
    alias = tmp_path / "alias"
    alias.symlink_to(repo, target_is_directory=True)
    config = configuration(tmp_path / "authority", policy, proposal).model_copy(
        update={"store_path": str(alias / "authority")}
    )
    with pytest.raises(authority.AuthorityError):
        authority.initialize_store(config)


@pytest.mark.parametrize(
    "field,value",
    [
        ("store_path", "relative"),
        ("store_path", "/private/tmp/../tmp/test"),
        ("store_id", "real-store"),
        ("host_scope", "multi-host"),
        ("execution_audience", "production"),
        ("schema_id", "v2"),
        ("extra", "private-sentinel"),
    ],
)
def test_strict_configuration_revalidation(field, value, tmp_path, policy, proposal):
    config = configuration(tmp_path / "authority", policy, proposal).model_copy(
        update={field: value}
    )
    with pytest.raises(authority.AuthorityError, match="^invalid_configuration$"):
        authority.initialize_store(config)
    assert not (tmp_path / "authority").exists()


def test_constructed_models_and_forged_verification_not_proof(
    store, signed, proposal, policy
):
    bad = store.model_copy(update={"device": str(store.device)})
    deny("invalid_binding", signed, proposal, policy, bad)
    verification = approval.verify_approval(
        *signed, expected=proposal, trust_policy=policy, now=NOW
    )
    with pytest.raises(approval.ApprovalError):
        consume((verification, signed[1]), proposal, policy, store)
    with pytest.raises(authority.AuthorityError, match="^invalid_inspection$"):
        authority.inspect_consumption(store, "private-sentinel")
    assert inspect(store, proposal).status == "absent"


@pytest.mark.parametrize("duration", [0, 61, -1])
def test_policy_observation_window_is_bounded(duration, policy):
    document = observation(policy).model_dump()
    document["expires_at"] = (NOW + timedelta(seconds=duration)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    with pytest.raises(ValidationError):
        authority.PolicyObservation.model_validate(document)


def test_current_unrevoked_policy_changes_cannot_mutate_store_binding(
    store, signed, proposal, policy, keys
):
    refreshed = policy.model_copy(
        update={"revoked_public_keys": (keys.unknown_public_key,)}
    )
    assert authority.policy_identity(refreshed) == authority.policy_identity(policy)
    record = consume(signed, proposal, refreshed, store)
    assert record.trust_policy_sha256 != fingerprint(policy.model_dump(mode="json"))
    assert inspect(store, proposal).record == record


def test_receipts_and_fixed_errors_contain_no_raw_signed_content(
    store, signed, proposal, policy, keys
):
    record = consume(signed, proposal, policy, store)
    raw = database(store).read_bytes()
    assert signed[0] not in raw and signed[1] not in raw
    assert b"PRIVATE KEY" not in raw
    assert keys.public_key.encode() not in raw
    document = record.model_dump_json()
    assert proposal.project_id not in document
    assert proposal.credential_provisioning_reference not in document
    assert store.configuration.store_path not in document
    for value in ("private-path-sentinel", signed[0].decode(), keys.public_key):
        assert str(authority.AuthorityError(value)) == "store_unavailable"


def test_import_has_no_network_provider_or_ambient_discovery():
    script = """
import sys
def audit(event, args):
    if event.startswith(('socket.', 'sqlite3.connect', 'subprocess.Popen')):
        raise AssertionError('unexpected import activity')
    if event == 'open' and isinstance(args[0], str):
        if any(part in args[0] for part in ('/.ssh/', '/.aws/', '/.env', 'credentials')):
            raise AssertionError('credential discovery')
sys.addaudithook(audit)
import harness.canary.authority_v3
assert not any(name.startswith(('openai', 'httpx', 'sales_agent')) for name in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", script],
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0


def test_consumption_does_not_use_environment_or_provider(
    store, signed, proposal, policy, monkeypatch, tmp_path
):
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected network activity")

    with monkeypatch.context() as patch:
        patch.setattr(socket, "socket", forbidden)
        patch.chdir(tmp_path)
        patch.setenv("CANARY_AUTHORITY_STORE", str(tmp_path / "untrusted"))
        patch.setenv("CANARY_AUTHORITY_STORE_ID", "synthetic-store-" + "0" * 32)
        result = consume(signed, proposal, policy, store)
    assert result.store_id == store.configuration.store_id
    assert not (tmp_path / "untrusted").exists()
