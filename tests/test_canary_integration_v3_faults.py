"""Cross-stage process interruption; fresh read-only observers, never recovery."""

from __future__ import annotations

import fcntl
import json
import multiprocessing
import os
import shutil
import signal
import sqlite3
import stat
import sys
import sysconfig
import tempfile
import threading
from contextlib import suppress
from importlib.util import source_from_cache
from pathlib import Path
from time import monotonic
from types import SimpleNamespace
from urllib.parse import parse_qsl, unquote, urlsplit

import pytest
import test_canary_integration_v3 as c

keys = c.keys
_TEST_DEADLINE = None


@pytest.fixture
def child_scratch(tmp_path):
    root = tmp_path / "child-scratch"
    root.mkdir(mode=0o700)
    (root / "tmp").mkdir(mode=0o700)
    return root


@pytest.fixture
def child_keys(child_scratch, keys):
    # Signing runs under the same narrow writable root as the child workflow.
    # Remove copied synthetic private keys even when a process test fails.
    with tempfile.TemporaryDirectory(dir=child_scratch, prefix="signing-") as name:
        directory = Path(name)
        for key in (keys.primary, keys.unknown):
            shutil.copyfile(key, directory / key.name)
            (directory / key.name).chmod(0o600)
        yield type(keys)(
            directory,
            directory / keys.primary.name,
            directory / keys.unknown.name,
            keys.public_key,
            keys.unknown_public_key,
        )
    assert not directory.exists()


@pytest.fixture(params=("unset", "system", "wrapper"))
def ambient_tmpdir(request, tmp_path, monkeypatch):
    # Only this parent's environment is patched and restored by pytest. Child
    # tempfile configuration must not alter the parent's cached tempfile state.
    cached = tempfile.tempdir
    if request.param == "unset":
        monkeypatch.delenv("TMPDIR", raising=False)
    elif request.param == "system":
        monkeypatch.setenv("TMPDIR", "/tmp")
    else:
        wrapper = tmp_path / "ambient-wrapper" / "tmp"
        wrapper.mkdir(parents=True, mode=0o700)
        monkeypatch.setenv("TMPDIR", str(wrapper))
    yield request.param
    assert tempfile.tempdir == cached


def configure_child_scratch(writable):
    """Called only in fresh children, before audited/temporary-file operations."""
    writable = Path(writable)
    assert writable.is_absolute() and writable.resolve() == writable
    assert writable.is_dir() and (writable / "tmp").is_dir()
    temporary = str(writable / "tmp")
    for name in ("TMPDIR", "TEMP", "TMP"):
        os.environ[name] = temporary
    tempfile.tempdir = temporary
    return writable


def check_child_scratch(writable):
    """Exercise the actual audited boundary before a child's public operation."""
    temporary = writable / "tmp"
    assert Path(tempfile.gettempdir()) == temporary
    assert all(os.environ[name] == str(temporary) for name in ("TMPDIR", "TEMP", "TMP"))
    with tempfile.TemporaryDirectory(prefix="scratch-check-") as name:
        assert Path(name).parent == temporary
        (Path(name) / "permitted").write_text("synthetic")
    outside = writable.parent / "forbidden-child-write"
    with pytest.raises(AssertionError, match="^synthetic write boundary$"):
        outside.write_text("forbidden")
    assert not outside.exists()


@pytest.fixture(autouse=True)
def test_deadline(request):
    global _TEST_DEADLINE
    total = (
        120
        if any(word in request.node.name for word in ("two_process", "isolation"))
        else 90
    )
    _TEST_DEADLINE = monotonic() + total
    yield
    assert monotonic() <= _TEST_DEADLINE, "total process-test deadline exceeded"
    _TEST_DEADLINE = None


def pack(flow):
    result = {"root": str(flow.root), "signed": flow.signed}
    for name in (
        "proposal",
        "policy",
        "receipt",
        "store",
        "consumed",
        "registry",
        "reference",
        "publication_root",
        "assignment",
        "register",
        "checkpoint",
        "review_policy",
    ):
        if hasattr(flow, name):
            result[name] = getattr(flow, name).model_dump_json()
    if hasattr(flow, "raw"):
        result["raw"] = flow.raw
    return result


def unpack(data):
    types = {
        "proposal": c.approval.ProposedCanary,
        "policy": c.approval.SyntheticTrustPolicy,
        "receipt": c.runtime.SourceApprovalReceipt,
        "store": c.authority.AuthorityStoreBinding,
        "consumed": c.authority.ConsumptionReceipt,
        "registry": c.journal.RegistryBinding,
        "reference": c.envelope.ExpectedEnvelopeReference,
        "publication_root": c.envelope.TrustedPublicationRoot,
        "assignment": c.review.ReviewAssignment,
        "register": c.register.ReviewRegisterBinding,
        "checkpoint": c.register.ReviewRegisterCheckpoint,
        "review_policy": c.review.SyntheticReviewPolicy,
    }
    flow = SimpleNamespace(root=Path(data["root"]), signed=data["signed"])
    for name, model in types.items():
        if name in data:
            setattr(flow, name, model.model_validate_json(data[name]))
    if "raw" in data:
        flow.raw = data["raw"]
    return flow


def _descriptor_path(fd):
    if sys.platform == "darwin":
        return Path(os.fsdecode(fcntl.fcntl(fd, 50, b"\0" * 1024).split(b"\0", 1)[0]))
    return Path(os.readlink(f"/proc/self/fd/{fd}"))


def isolation(
    writable,
    *,
    readonly_root=None,
    read_roots=(),
    read_files=(),
    git_roots=(),
    signing_keys=(),
):
    """Cooperative Python audit installed after trusted imports/fixture preparation.

    Native subprocess file access, arbitrary SQL and inherited descriptor writes
    are not confined. Only the reviewed commands/connections are admitted here.
    """
    writable = Path(writable).resolve()
    readonly_root = Path(readonly_root).resolve() if readonly_root else None
    original_open = os.open
    original_connect = sqlite3.connect
    context = threading.local()
    source_root = Path(__file__).resolve().parents[1]
    readable = (
        writable,
        *((readonly_root,) if readonly_root else ()),
        source_root / "src",
        *(
            Path(value).resolve()
            for name, value in sysconfig.get_paths().items()
            if name in {"stdlib", "platstdlib", "purelib", "platlib"}
        ),
        *(Path(value).resolve() for value in read_roots),
    )
    readable_files = {
        *(path.resolve() for path in (source_root / "tests").glob("*.py")),
        *(Path(value).resolve() for value in read_files),
    }
    traversable = {
        parent for path in (*readable, *readable_files) for parent in path.parents
    }
    git_roots = {Path(value).resolve() for value in git_roots}
    signing_keys = {Path(value).resolve() for value in signing_keys}
    observations = {"network": 0, "subprocesses": 0}

    def resolve(path, descriptor=None):
        if isinstance(path, int):
            return _descriptor_path(path).resolve()
        value = Path(os.fsdecode(path))
        if not value.is_absolute():
            value = (
                _descriptor_path(descriptor)
                if descriptor is not None and descriptor != -1
                else Path.cwd()
            ) / value
        return value.resolve()

    def check_read(path, descriptor=None):
        resolved = resolve(path, descriptor)
        cached_source = None
        if resolved.suffix == ".pyc" and resolved.parent.name == "__pycache__":
            with suppress(ValueError):
                cached_source = Path(source_from_cache(str(resolved)))
        if not (
            resolved in readable_files
            or cached_source in readable_files
            or any(resolved.is_relative_to(root) for root in readable)
        ):
            raise AssertionError("synthetic read boundary")

    def allowed(path):
        return path.is_relative_to(writable) and not (
            readonly_root and path.is_relative_to(readonly_root)
        )

    def check_write(path, descriptor=None):
        resolved = resolve(path, descriptor)
        if resolved == Path(os.devnull) and stat.S_ISCHR(resolved.stat().st_mode):
            return  # Fixed null device is subprocess plumbing, never artifact storage.
        if not allowed(resolved):
            raise AssertionError("synthetic write boundary")

    def check_open(path, flags, descriptor=None):
        if isinstance(path, int) and (
            stat.S_ISFIFO(os.fstat(path).st_mode)
            or stat.S_ISSOCK(os.fstat(path).st_mode)
        ):
            return  # Existing local IPC, not persistent file access.
        resolved = resolve(path, descriptor)
        if any(part in {".ssh", ".aws", ".netrc", ".env"} for part in resolved.parts):
            raise AssertionError("credential path discovery forbidden")
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            check_write(resolved)
        elif flags & os.O_DIRECTORY and resolved in traversable:
            return  # Descriptor traversal only; not file reads or directory listing.
        elif resolved != Path(os.devnull):
            check_read(resolved)

    def checked_open(path, flags, mode=0o777, *, dir_fd=None):
        check_open(path, flags, dir_fd)
        previous = getattr(context, "dir_fd", None)
        context.dir_fd = dir_fd
        try:
            return original_open(path, flags, mode, dir_fd=dir_fd)
        finally:
            context.dir_fd = previous

    def check_database(database, uri):
        value = os.fsdecode(database)
        if value == ":memory:" and not uri:
            return
        readonly = False
        if uri and value.startswith("file:"):
            parsed = urlsplit(value)
            pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
            assert (
                not parsed.netloc
                and not parsed.fragment
                and len(pairs) == 1
                and pairs[0][0] == "mode"
                and pairs[0][1] in {"ro", "rw", "rwc"}
            ), "unsupported SQLite URI"
            path = resolve(unquote(parsed.path, errors="strict"))
            readonly = pairs[0][1] == "ro"
        else:
            path = resolve(value)  # With uri=False, mode=ro is only filename text.
        check_open(path, os.O_RDONLY)
        if not readonly:
            check_write(path)

    def checked_connect(database, *args, **kwargs):
        # CPython 3.12/3.13 support uri as the eighth positional argument.
        uri = kwargs.get("uri", args[6] if len(args) > 6 else False)
        check_database(database, uri)
        previous = getattr(context, "sqlite_uri", False)
        context.sqlite_uri = uri
        try:
            return original_connect(database, *args, **kwargs)
        finally:
            context.sqlite_uri = previous

    def check_subprocess(executable, arguments, cwd, env):
        assert isinstance(arguments, (list, tuple)) and arguments[0] == executable
        if executable == "/usr/bin/ssh-keygen":
            assert env == {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C"}
            directory = resolve(cwd)
            assert allowed(directory), "synthetic SSH directory"
            if tuple(arguments[1:3]) == ("-Y", "sign"):
                assert (
                    len(arguments) == 7
                    and arguments[3] == "-f"
                    and arguments[5] == "-n"
                )
                key = resolve(arguments[4])
                assert key in signing_keys and allowed(key) and key.parent == directory
                assert arguments[6] in {
                    c.approval.APPROVAL_NAMESPACE,
                    c.review.NAMESPACE,
                }
            else:
                assert tuple(arguments[1:4]) == ("-Y", "verify", "-f")
                assert len(arguments) in {11, 13}
                assert (
                    arguments[5] == "-I"
                    and arguments[7] == "-n"
                    and arguments[9] == "-s"
                )
                namespace = arguments[8]
                assert namespace in {c.approval.APPROVAL_NAMESPACE, c.review.NAMESPACE}
                assert resolve(arguments[4]) == directory / "allowed-signers"
                approval_signature = namespace == c.approval.APPROVAL_NAMESPACE
                assert arguments[6] == (
                    c.approval_tests.PRINCIPAL
                    if approval_signature
                    else c.review_tests.PRINCIPAL
                )
                assert resolve(arguments[10]) == directory / (
                    "approval.sig" if approval_signature else "review.sig"
                )
                assert len(arguments) == (13 if approval_signature else 11)
                assert directory.name.startswith(
                    "canary-approval-synthetic-"
                    if approval_signature
                    else "canary-review-public-verification-"
                )
                if approval_signature:
                    assert (
                        arguments[11] == "-r"
                        and resolve(arguments[12]) == directory / "revoked-keys"
                    )
        else:
            assert executable in {"git", "/usr/bin/git"}, "unreviewed subprocess"
            assert cwd is None and len(arguments) >= 7, "unreviewed Git invocation"
            assert tuple(arguments[1:3]) == ("--no-optional-locks", "-C")
            assert resolve(arguments[3]) in git_roots, "unreviewed Git root"
            if executable == "git":
                assert tuple(arguments[4:6]) == ("-c", "core.fsmonitor=false")
                assert env == {
                    "PATH": os.defpath,
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_NO_REPLACE_OBJECTS": "1",
                    "GIT_OPTIONAL_LOCKS": "0",
                    "GIT_TERMINAL_PROMPT": "0",
                }
                assert tuple(arguments[6:]) in {
                    ("rev-parse", "--show-toplevel"),
                    ("rev-parse", "HEAD"),
                    ("rev-parse", "HEAD^{tree}"),
                    ("ls-tree", "-r", "-z", "HEAD"),
                    ("ls-files", "--stage", "-z"),
                    ("ls-files", "--others", "--exclude-standard", "-z"),
                }, "unreviewed Git operation"
            else:
                assert tuple(arguments[4:8]) == (
                    "-c",
                    "core.hooksPath=/dev/null",
                    "-c",
                    "commit.gpgsign=false",
                )
                assert env == {
                    "PATH": "/usr/bin:/bin",
                    "GIT_CONFIG_GLOBAL": "/dev/null",
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_TERMINAL_PROMPT": "0",
                    "GIT_NO_REPLACE_OBJECTS": "1",
                }
                assert tuple(arguments[8:]) == ("rev-parse", "HEAD", "HEAD^{tree}"), (
                    "unreviewed Git operation"
                )

    os.open = checked_open
    sqlite3.connect = checked_connect

    def audit(event, args):
        if event in {
            "socket.connect",
            "socket.bind",
            "socket.getaddrinfo",
            "socket.gethostbyname",
            "socket.gethostbyaddr",
            "socket.sendto",
        }:
            observations["network"] += 1
            raise AssertionError("Internet and DNS forbidden")
        if event == "socket.__new__" and args[1] in (2, 30, 10):
            observations["network"] += 1
            raise AssertionError("Internet socket forbidden")
        if event == "open":
            check_open(args[0], args[2], getattr(context, "dir_fd", None))
        if event in {"os.listdir", "os.scandir"}:
            check_read(args[0] if args[0] is not None else Path.cwd())
        if event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod"}:
            check_write(
                args[0], args[2] if event in {"os.mkdir", "os.chmod"} else args[1]
            )
        if event in {"os.rename", "os.link"}:
            check_write(args[0], args[2])
            check_write(args[1], args[3])
        if event == "os.symlink":
            destination = resolve(args[1], args[2])
            check_write(destination)
            target = Path(os.fsdecode(args[0]))
            check_write(target if target.is_absolute() else destination.parent / target)
        if event in {"os.truncate", "os.utime", "os.chown"}:
            check_write(args[0], args[3] if len(args) > 3 else None)
        if event == "sqlite3.connect":
            check_database(args[0], getattr(context, "sqlite_uri", False))
        if event == "subprocess.Popen":
            observations["subprocesses"] += 1
            try:
                check_subprocess(*args)
            except AssertionError:
                raise AssertionError("unreviewed subprocess") from None
        if event in {"os.system", "os.exec"}:
            raise AssertionError("unreviewed command")

    sys.addaudithook(audit)
    return observations


def _worker(pipe, writable, operation, data, phase):
    writable = configure_child_scratch(writable)
    flow = unpack(data)
    assert flow.root.is_relative_to(writable)
    isolation(writable)
    check_child_scratch(writable)
    pipe.send(("ready", operation))
    assert pipe.recv() == "go"

    def boundary(details):
        pipe.send(("boundary", phase, details))
        assert pipe.recv() == "release"

    if operation == "consume":
        if phase in {"before_commit", "after_commit"}:
            original = c.authority._commit

            def commit(db):
                if phase == "after_commit":
                    original(db)
                assert (flow.root / "authority" / "pending-consumption.json").exists()
                assert (
                    db.execute("SELECT count(*) FROM consumptions").fetchone()[0] == 1
                )
                boundary(
                    {"row_in_writer": 1, "commit_returned": phase == "after_commit"}
                )
                if phase == "before_commit":
                    original(db)

            c.authority._commit = commit
        try:
            result = c.authority.consume_approval(
                *flow.signed,
                expected=flow.proposal,
                store=flow.store,
                policy=lambda: c.approval_observation(flow),
                clock=lambda: c.T,
            )
        except (c.authority.AuthorityError, c.approval.ApprovalError) as error:
            pipe.send(("denied", str(error)))
        else:
            if phase == "race":
                pipe.send(("result", result.model_dump_json()))
            else:
                boundary(
                    {
                        "receipt": result.model_dump_json(),
                        "journal_absent": not (flow.root / "journal").exists(),
                    }
                )
    elif operation == "execute":
        c.execute(flow)
        assert (
            flow.report["completion_certified"] and flow.report["accounting_reconciled"]
        )
        boundary(
            {
                "registry": flow.registry.model_dump_json(),
                "completed": True,
                "publication_absent": not (flow.root / "envelopes").exists(),
            }
        )
    elif operation == "publish":
        original = c.envelope.os.fsync
        count = 0

        def fsync(fd):
            nonlocal count
            result = original(fd)
            count += 1
            if count == (2 if phase == "pending" else 5):
                destination = Path(flow.publication_root.path) / "accepted"
                boundary(
                    {
                        "entries": sorted(p.name for p in destination.iterdir()),
                        "fsyncs": count,
                    }
                )
            return result

        c.envelope.os.fsync = fsync
        c.envelope.publish_envelope(
            c.envelope.parse_envelope(flow.raw),
            publication_root=flow.publication_root,
            publication_id="accepted",
            store=flow.store,
            registry=flow.registry,
        )
    elif operation == "review":
        original = c.register._sync

        def sync(storage):
            original(storage)
            assert storage.db.execute("SELECT count(*) FROM events").fetchone()[0] == 1
            assert (
                Path(flow.register.configuration.path) / c.register.PENDING
            ).exists()
            boundary({"events": 1, "pending": True, "commit_and_sync_returned": True})

        c.register._sync = sync
        c.register.register_review(
            *data["review_signed"],
            **c.registration_arguments(flow),
            policy=lambda: c.review_observation(flow),
            clock=lambda: c.T,
        )
    pipe.send(("returned", operation))
    pipe.close()


def _inspector(pipe, writable, operation, data):
    writable = configure_child_scratch(writable)
    flow = unpack(data)
    isolation(writable, readonly_root=flow.root)
    check_child_scratch(writable)
    before = c.snapshot(flow.root)
    with pytest.raises(AssertionError, match="^synthetic write boundary$"):
        (flow.root / "forbidden-inspection-write").write_text("forbidden")
    if operation == "authority":
        observed = c.authority.inspect_consumption(
            flow.store, flow.proposal.authorisation_id
        )
        result = observed.model_dump(mode="json")
    elif operation == "journal":
        report = c.journal.inspect_run(flow.registry, flow.consumed.intended_run_id)
        result = {
            k: report[k]
            for k in (
                "status",
                "completion_certified",
                "accounting_reconciled",
                "issues",
            )
        }
    elif operation == "envelope":
        try:
            verified = c.envelope.read_envelope(
                publication_root=flow.publication_root,
                publication_id="accepted",
                expected=flow.reference,
            )
        except c.envelope.EnvelopeError as error:
            result = {"error": str(error)}
        else:
            result = {"verification": verified.model_dump(mode="json")}
    else:
        try:
            observed = c.register.inspect_register(
                flow.register, expected=flow.assignment, checkpoint=flow.checkpoint
            )
        except c.review.ReviewError as error:
            result = {"error": error.code}
        else:
            assessment = c.assess_review(flow)
            result = {
                "state": observed.state,
                "events": len(observed.events),
                "checkpoint": observed.checkpoint_status,
                "issues": observed.issues,
                "prior_return": observed.prior_publisher_return,
                "assessment": assessment.assessment.status,
                "verification": assessment.inputs.verification.model_dump(mode="json"),
            }
    assert c.snapshot(flow.root) == before
    pipe.send(result)
    pipe.close()


def start(target, args, *, writable, total=90):
    deadline = min(_TEST_DEADLINE or float("inf"), monotonic() + total)
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=target, args=(child, str(writable), *args))
    process.start()
    child.close()
    return SimpleNamespace(process=process, pipe=parent, deadline=deadline)


def receive(worker):
    remaining = worker.deadline - monotonic()
    assert remaining > 0 and worker.pipe.poll(min(20, remaining)), (
        "required process boundary not reached"
    )
    return worker.pipe.recv()


def finish(worker, *, killed=False):
    process = worker.process
    try:
        process.join(max(0, min(20, worker.deadline - monotonic())))
        assert not process.is_alive(), "worker survived deadline"
        assert process.exitcode == (-signal.SIGKILL if killed else 0)
    finally:
        if process.is_alive():
            process.kill()
            process.join(5)
        worker.pipe.close()
        assert not process.is_alive(), "worker survived forced teardown"


def kill(worker):
    assert worker.process.is_alive() and not worker.pipe.poll(0), (
        "worker returned before intended interruption"
    )
    worker.process.kill()
    finish(worker, killed=True)


def inspect_fresh(flow, operation, *, writable):
    worker = start(_inspector, (operation, pack(flow)), writable=writable)
    try:
        result = receive(worker)
    finally:
        finish(worker)
    return result


def store_ready(root, keys):
    flow = c.prepare(root, keys)
    flow.store = c.authority.initialize_store(flow.configuration)
    return flow


@pytest.mark.usefixtures("ambient_tmpdir")
@pytest.mark.parametrize("boundary", ["consumed", "completed"])
def test_cross_stage_kill_after_success(tmp_path, child_scratch, keys, boundary):
    """P0-12/13: actual public operation returned before the handoff kill."""
    flow = (
        store_ready(child_scratch / "a", keys)
        if boundary == "consumed"
        else c.consume(c.prepare(child_scratch / "a", keys))
    )
    operation = "consume" if boundary == "consumed" else "execute"
    worker = start(_worker, (operation, pack(flow), boundary), writable=child_scratch)
    try:
        assert receive(worker) == ("ready", operation)
        worker.pipe.send("go")
        kind, phase, evidence = receive(worker)
        assert (kind, phase) == ("boundary", boundary)
        if boundary == "consumed":
            flow.consumed = c.authority.ConsumptionReceipt.model_validate_json(
                evidence["receipt"]
            )
            assert evidence["journal_absent"] and not (flow.root / "journal").exists()
        else:
            flow.registry = c.journal.RegistryBinding.model_validate_json(
                evidence["registry"]
            )
            assert evidence["completed"] and evidence["publication_absent"]
        kill(worker)
    finally:
        if worker.process.is_alive():
            worker.process.kill()
            worker.process.join(5)
    before = c.snapshot(flow.root)
    result = inspect_fresh(
        flow,
        "authority" if boundary == "consumed" else "journal",
        writable=child_scratch,
    )
    assert result["status"] == ("consumed" if boundary == "consumed" else "completed")
    assert c.snapshot(flow.root) == before
    if boundary == "completed":
        assert result["completion_certified"] and result["accounting_reconciled"]
    (tmp_path / "observation.json").write_text(json.dumps(result, indent=2))


@pytest.mark.parametrize("phase", ["pending", "final"])
def test_envelope_publisher_process_interruption(tmp_path, child_scratch, keys, phase):
    """P0-14: preserve partial layout and independent prepublication anchor."""
    flow = c.consume(c.prepare(child_scratch / "a", keys))
    c.execute(flow)
    c.anchor(flow)
    root = flow.root / "envelopes"
    root.mkdir(mode=0o700)
    info = root.stat()
    flow.publication_root = c.envelope.TrustedPublicationRoot(
        path=str(root), device=info.st_dev, directory_inode=info.st_ino
    )
    retained = flow.reference.model_dump_json()
    before_authority, before_journal = (
        c.snapshot(flow.store.configuration.store_path),
        c.snapshot(flow.registry.path),
    )
    worker = start(_worker, ("publish", pack(flow), phase), writable=child_scratch)
    try:
        assert receive(worker) == ("ready", "publish")
        worker.pipe.send("go")
        kind, actual, evidence = receive(worker)
        assert (kind, actual) == ("boundary", phase)
        assert evidence["entries"] == (
            [".pending-envelope"] if phase == "pending" else ["envelope.json"]
        )
        kill(worker)
    finally:
        if worker.process.is_alive():
            worker.process.kill()
            worker.process.join(5)
    observed = inspect_fresh(flow, "envelope", writable=child_scratch)
    if phase == "pending":
        assert observed == {"error": "artifact_unavailable"}
    else:
        assert observed["verification"]["source_comparison"] == "not-performed"
        assert (
            observed["verification"]["assurance"]["invocation_status"]
            == "not-established"
        )
    assert flow.reference.model_dump_json() == retained
    assert (
        c.snapshot(flow.store.configuration.store_path) == before_authority
        and c.snapshot(flow.registry.path) == before_journal
    )
    before = c.snapshot(flow.root)
    with pytest.raises(c.envelope.EnvelopeError, match="^destination_exists$"):
        c.envelope.publish_envelope(
            flow.envelope,
            publication_root=flow.publication_root,
            publication_id="accepted",
            store=flow.store,
            registry=flow.registry,
        )
    assert c.snapshot(flow.root) == before
    (tmp_path / "observation.json").write_text(json.dumps(observed, indent=2))


def test_review_committed_but_return_uncertain(tmp_path, child_scratch, keys):
    """P0-16: genuine COMMIT and sync evidence, no checkpoint adoption."""
    flow = c.complete(child_scratch / "a", keys, register_now=False)
    retained = flow.checkpoint.model_dump_json()
    data = pack(flow)
    data["review_signed"] = c.review_bytes(flow)
    worker = start(_worker, ("review", data, "after_sync"), writable=child_scratch)
    try:
        assert receive(worker) == ("ready", "review")
        worker.pipe.send("go")
        kind, phase, evidence = receive(worker)
        assert (kind, phase) == ("boundary", "after_sync")
        assert evidence == {
            "events": 1,
            "pending": True,
            "commit_and_sync_returned": True,
        }
        kill(worker)
    finally:
        if worker.process.is_alive():
            worker.process.kill()
            worker.process.join(5)
    observed = inspect_fresh(flow, "review", writable=child_scratch)
    assert (
        observed["events"] == 1
        and observed["state"] == "RECORDED"
        and observed["checkpoint"] == "stale"
    )
    assert {"register_pending", "checkpoint_stale"} <= set(observed["issues"])
    assert (
        observed["prior_return"] == "not-established"
        and observed["assessment"] == "ERROR"
    )
    assert flow.checkpoint.model_dump_json() == retained
    (tmp_path / "observation.json").write_text(json.dumps(observed, indent=2))


@pytest.mark.parametrize("phase", ["before_commit", "after_commit"])
def test_authority_transaction_interruption(tmp_path, child_scratch, keys, phase):
    """P1-03: no successful execution may follow uncertain consumption."""
    flow = store_ready(child_scratch / "a", keys)
    worker = start(_worker, ("consume", pack(flow), phase), writable=child_scratch)
    try:
        assert receive(worker) == ("ready", "consume")
        worker.pipe.send("go")
        kind, actual, evidence = receive(worker)
        assert (kind, actual) == ("boundary", phase)
        assert evidence["row_in_writer"] == 1 and evidence["commit_returned"] is (
            phase == "after_commit"
        )
        kill(worker)
    finally:
        if worker.process.is_alive():
            worker.process.kill()
            worker.process.join(5)
    observed = inspect_fresh(flow, "authority", writable=child_scratch)
    if phase == "after_commit":
        assert (
            observed["status"] == "consumed"
            and "pending_consumption" in observed["issues"]
        )
    else:
        assert observed["status"] in {"absent", "unavailable"}
        assert (
            "pending_consumption" in observed["issues"]
            if observed["status"] == "absent"
            else "store_unavailable" in observed["issues"]
        )
    assert not (flow.root / "journal").exists()
    before = c.snapshot(flow.root)
    with pytest.raises(c.authority.AuthorityError, match="^store_pending$"):
        c.authority.consume_approval(
            *flow.signed,
            expected=flow.proposal,
            store=flow.store,
            policy=lambda: c.approval_observation(flow),
            clock=lambda: c.T,
        )
    assert c.snapshot(flow.root) == before
    (tmp_path / "observation.json").write_text(json.dumps(observed, indent=2))


def test_two_process_consumption_no_retry(tmp_path, child_scratch, keys):
    """P1-02: both contenders start from ready, each calls consumption once."""
    flow = store_ready(child_scratch / "a", keys)
    workers = [
        start(
            _worker, ("consume", pack(flow), "race"), writable=child_scratch, total=120
        )
        for _ in range(2)
    ]
    try:
        for worker in workers:
            assert receive(worker) == ("ready", "consume")
        for worker in workers:
            worker.pipe.send("go")
        outcomes = [receive(worker) for worker in workers]
        assert sum(outcome[0] == "result" for outcome in outcomes) == 1
        loser = next(outcome for outcome in outcomes if outcome[0] == "denied")
        assert loser[1] in {"store_busy", "authorisation_consumed"}
        for worker in workers:
            assert receive(worker) == ("returned", "consume")
            finish(worker)
    finally:
        for worker in workers:
            if worker.process.is_alive():
                worker.process.kill()
                worker.process.join(5)
            with suppress(OSError):
                worker.pipe.close()
    observed = inspect_fresh(flow, "authority", writable=child_scratch)
    assert observed["status"] == "consumed" and not observed["issues"]
    assert not (flow.root / "journal").exists()


def test_publication_failure_preserves_stages(tmp_path, keys, monkeypatch):
    """P1-06: existing outcome-unknown distinction, sources untouched."""
    flow = c.consume(c.prepare(tmp_path / "a", keys))
    c.execute(flow)
    c.anchor(flow)
    root = flow.root / "envelopes"
    root.mkdir(mode=0o700)
    info = root.stat()
    binding = c.envelope.TrustedPublicationRoot(
        path=str(root), device=info.st_dev, directory_inode=info.st_ino
    )
    a, j = (
        c.snapshot(flow.store.configuration.store_path),
        c.snapshot(flow.registry.path),
    )

    def fail(*args, **kwargs):
        raise OSError("PRIVATE_SYNTHETIC_LINK")

    with monkeypatch.context() as patch:
        patch.setattr(c.envelope.os, "link", fail)
        with pytest.raises(
            c.envelope.EnvelopeError, match="^publication_outcome_unknown$"
        ):
            c.envelope.publish_envelope(
                flow.envelope,
                publication_root=binding,
                publication_id="accepted",
                store=flow.store,
                registry=flow.registry,
            )
    assert (root / "accepted" / ".pending-envelope").is_file()
    assert (
        c.snapshot(flow.store.configuration.store_path) == a
        and c.snapshot(flow.registry.path) == j
    )


def _isolation_worker(pipe, writable, root, keys):
    import socket

    writable = configure_child_scratch(writable)
    root = Path(root)
    assert not root.is_relative_to(writable) and writable.is_relative_to(root)
    # Trusted preparation opens only a disposable probe directory before the audit.
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    observations = isolation(writable, signing_keys=(keys.primary, keys.unknown))
    check_child_scratch(writable)
    flow = c.complete(writable / "a", keys)
    result = c.assess_review(flow)
    assert result.assessment.status == "PASS" and observations["network"] == 0
    assert observations["subprocesses"] > 0
    # Deliberate negative probes must be stopped before an external effect.
    outside = root / "slice6f-forbidden-write"
    try:
        outside.write_text("forbidden")
    except AssertionError as error:
        assert str(error) == "synthetic write boundary"
    else:
        raise AssertionError("outside write succeeded")
    assert not outside.exists()
    try:
        with pytest.raises(AssertionError, match="synthetic write boundary"):
            os.open(
                "slice6f-forbidden-dirfd",
                os.O_CREAT | os.O_WRONLY,
                0o600,
                dir_fd=descriptor,
            )
    finally:
        os.close(descriptor)
    with pytest.raises(AssertionError, match="Internet and DNS forbidden"):
        socket.getaddrinfo("canary.invalid", 443)
    with pytest.raises(AssertionError, match="credential path discovery forbidden"):
        (writable / ".ssh" / "synthetic-only").read_bytes()
    pipe.send(
        {
            "assessment": "PASS",
            "before_probes_network": 0,
            "blocked_network_probes": observations["network"],
            "subprocesses": observations["subprocesses"],
            "writable": str(writable),
            "temporary": tempfile.gettempdir(),
            "measurement": c.measurement(flow),
        }
    )
    pipe.close()


@pytest.mark.usefixtures("ambient_tmpdir")
def test_complete_workflow_isolation_in_fresh_process(
    tmp_path, child_scratch, child_keys
):
    worker = start(
        _isolation_worker,
        (str(tmp_path), child_keys),
        writable=child_scratch,
        total=120,
    )
    try:
        result = receive(worker)
    finally:
        finish(worker)
    assert result["assessment"] == "PASS" and result["blocked_network_probes"] == 1
    assert result["writable"] == str(child_scratch)
    assert result["temporary"] == str(child_scratch / "tmp")
    assert not (tmp_path / "slice6f-forbidden-write").exists()
    assert not (tmp_path / "slice6f-forbidden-dirfd").exists()
    (tmp_path / "isolation.json").write_text(json.dumps(result, indent=2))


def _isolation_regression_worker(pipe, writable, root):
    """Disposable stand-ins only; no credential or private-history discovery."""
    import subprocess

    from test_canary_integration_v3_application import local_git, source_copy

    writable = configure_child_scratch(writable)
    root = Path(root)
    outside = root / "outside"
    assert not outside.is_relative_to(writable)
    outside.mkdir()
    readonly = writable / "inspection"
    readonly.mkdir()
    db_path = readonly / "inspection.db"
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE synthetic(value)")
        db.execute("INSERT INTO synthetic VALUES (1)")
    db.close()
    private = outside / "private-history-sentinel"
    private.write_text("SYNTHETIC_PRIVATE_EVIDENCE")
    credentials = writable / ".aws"
    credentials.mkdir()
    (credentials / "credentials").write_text("SYNTHETIC_CREDENTIAL")
    (writable / "escape").symlink_to(outside, target_is_directory=True)
    outside_fd = os.open(outside, os.O_RDONLY | os.O_DIRECTORY)
    inside_fd = os.open(writable, os.O_RDONLY | os.O_DIRECTORY)
    readonly_fd = os.open(readonly, os.O_RDONLY | os.O_DIRECTORY)
    source = source_copy(writable)
    expected_commit = local_git(source, "rev-parse", "HEAD")
    ssh_directory = writable / "canary-approval-synthetic-probe"
    ssh_directory.mkdir()
    # All directories, sentinels, descriptors, Git fixture and imports above are
    # trusted preparation. Every positive/negative operation below is audited.
    observations = isolation(writable, readonly_root=readonly, git_roots=(source,))
    check_child_scratch(writable)
    checks = []

    def denied(name, action, message="boundary|forbidden|unsupported|unreviewed"):
        with pytest.raises(AssertionError, match=message):
            action()
        checks.append(name)

    os.chdir(outside)
    denied("relative Python write", lambda: Path("relative-write").write_text("x"))
    denied(
        "absolute Python write", lambda: (outside / "absolute-write").write_bytes(b"x")
    )
    denied(
        "relative os.open",
        lambda: os.open("ordinary-os-open", os.O_WRONLY | os.O_CREAT, 0o600),
    )
    denied(
        "outside dir_fd write",
        lambda: os.open(
            "dirfd-write", os.O_WRONLY | os.O_CREAT, 0o600, dir_fd=outside_fd
        ),
    )
    denied("read-only Python write", lambda: (readonly / "write").write_text("x"))
    denied(
        "read-only dir_fd write",
        lambda: os.open("write", os.O_WRONLY | os.O_CREAT, 0o600, dir_fd=readonly_fd),
    )
    denied(
        "parent escape",
        lambda: (writable / ".." / "outside" / "parent-write").write_text("x"),
    )
    denied(
        "symlink escape",
        lambda: (writable / "escape" / "symlink-write").write_text("x"),
    )
    denied("private evidence absolute read", private.read_text)
    denied("private evidence relative read", lambda: Path(private.name).read_bytes())
    denied(
        "private evidence dir_fd read",
        lambda: os.open(private.name, os.O_RDONLY, dir_fd=outside_fd),
    )
    denied("credential read", lambda: (credentials / "credentials").read_bytes())
    denied("private directory listing", lambda: list(outside.iterdir()))

    sqlite_probes = [
        (readonly / "filename-mode=ro.db", {}),
        (os.fsencode(readonly / "bytes-mode=ro.db"), {}),
        (str(readonly / "query.db") + "?mode=ro", {}),
        (db_path.as_uri() + "?mode=ro", {"uri": False}),
        (db_path.as_uri() + "?mode=rw&note=mode=ro", {"uri": True}),
        (db_path.as_uri() + "?mode=rw&mode=ro", {"uri": True}),
        (db_path.as_uri() + "?mode=ro&immutable=1", {"uri": True}),
        (db_path.as_uri() + "?mode=rw", {"uri": True}),
        (credentials / "credentials", {}),
        ((credentials / "credentials").as_uri() + "?mode=ro", {"uri": True}),
        (private.as_uri() + "?mode=ro", {"uri": True}),
    ]
    for index, (database, kwargs) in enumerate(sqlite_probes):
        denied(
            f"SQLite deceptive representation {index}",
            lambda database=database, kwargs=kwargs: sqlite3.connect(
                database, **kwargs
            ),
        )
    denied(
        "unvalidated SQLite constructor",
        lambda: sqlite3.Connection(db_path.as_uri() + "?mode=ro", uri=True),
    )
    for positional in (False, True):
        uri = db_path.as_uri() + "?mode=ro"
        db = (
            sqlite3.connect(uri, 2, 0, None, True, sqlite3.Connection, 128, True)
            if positional
            else sqlite3.connect(uri, uri=True)
        )
        try:
            assert db.execute("SELECT value FROM synthetic").fetchone() == (1,)
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                db.execute("CREATE TABLE forbidden(value)")
        finally:
            db.close()
    for name, representation in (("path", Path), ("bytes", os.fsencode)):
        db = sqlite3.connect(representation(writable / (name + ".db")))
        db.execute("CREATE TABLE permitted(value)")
        db.close()

    (writable / "ordinary-positive").write_text("permitted")
    assert (writable / "ordinary-positive").read_text() == "permitted"
    fd = os.open(
        "descriptor-positive", os.O_CREAT | os.O_WRONLY, 0o600, dir_fd=inside_fd
    )
    with os.fdopen(fd, "w") as stream:
        stream.write("permitted")
    fd = os.open("descriptor-positive", os.O_RDONLY, dir_fd=inside_fd)
    with os.fdopen(fd) as stream:
        assert stream.read() == "permitted"
    assert "def isolation(" in Path(__file__).read_text()
    assert "class CanaryJournal" in Path(c.journal.__file__).read_text()
    assert Path(pytest.__file__).read_bytes()

    env = {
        "PATH": os.defpath,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
    }
    prefix = [
        "git",
        "--no-optional-locks",
        "-C",
        str(source),
        "-c",
        "core.fsmonitor=false",
    ]
    assert (
        subprocess.check_output([*prefix, "rev-parse", "HEAD"], env=env)
        .decode()
        .strip()
        == expected_commit
    )
    assert (
        local_git(source, "rev-parse", "HEAD", "HEAD^{tree}").splitlines()[0]
        == expected_commit
    )
    for operation in (
        ("config", "--global", "synthetic.probe", "true"),
        ("config", "--local", "synthetic.probe", "true"),
        ("show", "--ext-diff"),
        ("fetch",),
        ("commit",),
    ):
        denied(
            "Git " + operation[0],
            lambda operation=operation: sys.audit(
                "subprocess.Popen", "git", [*prefix, *operation], None, env
            ),
        )
    denied(
        "Git environment injection",
        lambda: sys.audit(
            "subprocess.Popen",
            "git",
            [*prefix, "rev-parse", "HEAD"],
            None,
            {**env, "GIT_CONFIG_COUNT": "1"},
        ),
    )
    denied(
        "Git root substitution",
        lambda: sys.audit(
            "subprocess.Popen",
            "git",
            [*prefix[:3], str(outside), *prefix[4:], "rev-parse", "HEAD"],
            None,
            env,
        ),
    )
    denied(
        "Git argument injection",
        lambda: sys.audit(
            "subprocess.Popen",
            "git",
            [*prefix, "-c", "synthetic.probe=true", "rev-parse", "HEAD"],
            None,
            env,
        ),
    )
    ssh_env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C"}
    verify = [
        "/usr/bin/ssh-keygen",
        "-Y",
        "verify",
        "-f",
        str(ssh_directory / "allowed-signers"),
        "-I",
        c.approval_tests.PRINCIPAL,
        "-n",
        c.approval.APPROVAL_NAMESPACE,
        "-s",
        str(ssh_directory / "approval.sig"),
        "-r",
        str(ssh_directory / "revoked-keys"),
    ]
    for label, arguments, environment in (
        ("SSH namespace", [*verify[:8], "unreviewed", *verify[9:]], ssh_env),
        ("SSH artifact path", [*verify[:10], str(private), *verify[11:]], ssh_env),
        ("SSH environment", verify, {**ssh_env, "SSH_AUTH_SOCK": "synthetic-only"}),
        (
            "SSH unregistered key",
            [
                "/usr/bin/ssh-keygen",
                "-Y",
                "sign",
                "-f",
                str(private),
                "-n",
                c.approval.APPROVAL_NAMESPACE,
            ],
            ssh_env,
        ),
    ):
        denied(
            label,
            lambda arguments=arguments, environment=environment: sys.audit(
                "subprocess.Popen",
                "/usr/bin/ssh-keygen",
                arguments,
                str(ssh_directory),
                environment,
            ),
        )
    for fd in (outside_fd, inside_fd, readonly_fd):
        os.close(fd)
    assert observations["network"] == 0
    pipe.send(
        {
            "negative_checks": checks,
            "positive_filesystem_sqlite_git": "PASS",
            "network": observations["network"],
            "unapproved_git_executed": False,
            "audit_scope": "after trusted imports and disposable fixture preparation",
        }
    )
    pipe.close()


@pytest.mark.usefixtures("ambient_tmpdir")
def test_isolation_regression_probes_in_fresh_process(tmp_path, child_scratch):
    """QA correction: real Python/SQLite operations and Git audit-only denials."""
    worker = start(
        _isolation_regression_worker,
        (str(tmp_path),),
        writable=child_scratch,
        total=120,
    )
    try:
        result = receive(worker)
    finally:
        finish(worker)
    assert len(result["negative_checks"]) == 37
    assert result["positive_filesystem_sqlite_git"] == "PASS" and result["network"] == 0
    assert not result["unapproved_git_executed"]
    assert sorted(path.name for path in (tmp_path / "outside").iterdir()) == [
        "private-history-sentinel"
    ]
    (tmp_path / "isolation-regression.json").write_text(json.dumps(result, indent=2))
