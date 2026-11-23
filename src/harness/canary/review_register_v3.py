"""One fixed-assignment synthetic review register; never execution authority.

Trust independent configuration/checkpoints/policy/clock and cooperative local
OS/SQLite/filesystem use. No recovery, retry, migration or rollback protection
beyond independently retained checkpoints. Original signed bytes remain private.
"""

from __future__ import annotations

import base64
import fcntl
import os
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from harness.canary import envelope_v3 as envelope
from harness.canary import human_review_v3 as review
from harness.canary import journal_v3 as journal
from harness.canary import review_packet_v3 as packet
from harness.canary.runtime_v3 import Digest, Frozen
from harness.core.fingerprints import fingerprint

REGISTER_SCHEMA = "canary-synthetic-review-register-v1"
DATABASE = "reviews.sqlite3"
LOCK = "writer.lock"
PENDING = "pending-review.json"
JOURNAL = DATABASE + "-journal"
MAX_DATABASE_BYTES = 4 * 1024 * 1024
MAX_EVENT_BYTES = 256 * 1024
CheckpointStatus = Literal["matches", "missing", "stale", "behind", "mismatch"]


class ReviewRegisterConfiguration(Frozen):
    schema_id: Literal["canary-review-register-config-v1"] = (
        "canary-review-register-config-v1"
    )
    path: str
    register_id: review.RegisterID
    host_id: review.Audience
    host_scope: Literal["synthetic-single-host-local"] = "synthetic-single-host-local"
    assignment: review.ReviewAssignment
    assignment_sha256: Digest
    trust_policy_identity_sha256: Digest

    @model_validator(mode="after")
    def _binding(self) -> ReviewRegisterConfiguration:
        packet.absolute(self.path)
        if (
            self.register_id != self.assignment.register_id
            or self.assignment_sha256 != review.assignment_commitment(self.assignment)
            or self.trust_policy_identity_sha256
            != self.assignment.trust_policy_identity_sha256
        ):
            raise ValueError("invalid_register_configuration")
        return self


class ReviewRegisterBinding(Frozen):
    schema_id: Literal["canary-review-register-binding-v1"] = (
        "canary-review-register-binding-v1"
    )
    configuration: ReviewRegisterConfiguration
    device: int = Field(ge=0)
    directory_inode: int = Field(ge=1)
    database_inode: int = Field(ge=1)
    lock_inode: int = Field(ge=1)


class ReviewRegisterCheckpoint(Frozen):
    schema_id: Literal["canary-review-register-checkpoint-v1"] = (
        "canary-review-register-checkpoint-v1"
    )
    register_id: review.RegisterID
    register_binding_sha256: Digest
    assignment_sha256: Digest
    trust_policy_identity_sha256: Digest
    event_count: int = Field(ge=0, le=2)
    head_sha256: Digest


class RegisterInitializationResult(Frozen):
    binding: ReviewRegisterBinding
    checkpoint_candidate: ReviewRegisterCheckpoint
    publication_status: Literal["local-initialization-protocol-completed"] = (
        "local-initialization-protocol-completed"
    )
    independent_custody: Literal["not-established-by-initializer"] = (
        "not-established-by-initializer"
    )


class RegisteredEvent(Frozen):
    schema_id: Literal["canary-registered-review-event-v1"] = (
        "canary-registered-review-event-v1"
    )
    sequence: int = Field(ge=1, le=2)
    kind: Literal["initial", "conflict"]
    previous_sha256: Digest
    assignment_sha256: Digest
    payload_utf8: str = Field(repr=False)
    signature_base64: str = Field(repr=False)
    observation: review.ReviewPolicyObservation = Field(repr=False)
    verification: review.SubmissionVerification
    admission_checked_at: review.Timestamp
    event_sha256: Digest


class RegistrationResult(Frozen):
    status: Literal[
        "RECORDED", "ALREADY_RECORDED", "CONFLICT_RECORDED", "ALREADY_CONFLICTED"
    ]
    checkpoint_candidate: ReviewRegisterCheckpoint
    publication_status: Literal[
        "local-registration-protocol-completed", "existing-record-observed"
    ]
    independent_custody: Literal["not-established-by-register"] = (
        "not-established-by-register"
    )
    prior_publisher_return: Literal["not-established"] = "not-established"


class RegisterInspection(Frozen):
    schema_id: Literal["canary-review-register-inspection-v1"] = (
        "canary-review-register-inspection-v1"
    )
    state: Literal["EMPTY", "RECORDED", "CONFLICT"]
    events: tuple[RegisteredEvent, ...] = Field(repr=False)
    checkpoint_candidate: ReviewRegisterCheckpoint
    checkpoint_status: CheckpointStatus
    issues: tuple[review.Issue, ...]
    conflict_authentication: Literal["not-performed"] = "not-performed"
    prior_publisher_return: Literal["not-established"] = "not-established"
    assurance: review.Assurance = Field(default_factory=review.Assurance)


def binding_digest(binding: ReviewRegisterBinding) -> str:
    return fingerprint(binding.model_dump(mode="json"))


def zero_head(binding: ReviewRegisterBinding) -> str:
    config = binding.configuration
    return fingerprint(
        {
            "domain": "canary-review-register-zero-head-v1",
            "register_schema": REGISTER_SCHEMA,
            "register_id": config.register_id,
            "register_binding_sha256": binding_digest(binding),
            "assignment_sha256": config.assignment_sha256,
            "trust_policy_identity_sha256": config.trust_policy_identity_sha256,
        }
    )


def _checkpoint(
    binding: ReviewRegisterBinding, events: tuple[RegisteredEvent, ...]
) -> ReviewRegisterCheckpoint:
    config = binding.configuration
    return ReviewRegisterCheckpoint(
        register_id=config.register_id,
        register_binding_sha256=binding_digest(binding),
        assignment_sha256=config.assignment_sha256,
        trust_policy_identity_sha256=config.trust_policy_identity_sha256,
        event_count=len(events),
        head_sha256=events[-1].event_sha256 if events else zero_head(binding),
    )


_SCHEMA = (
    "CREATE TABLE register_identity (singleton INTEGER PRIMARY KEY CHECK(singleton=1), binding TEXT NOT NULL, zero_head TEXT NOT NULL) STRICT",
    "CREATE TABLE events (sequence INTEGER PRIMARY KEY CHECK(sequence IN (1,2)), kind TEXT NOT NULL CHECK(kind IN ('initial','conflict')), previous_sha256 TEXT NOT NULL, payload_sha256 TEXT NOT NULL, event_sha256 TEXT NOT NULL UNIQUE, canonical_event TEXT NOT NULL) STRICT",
    "CREATE TRIGGER identity_no_update BEFORE UPDATE ON register_identity BEGIN SELECT RAISE(ABORT,'immutable'); END",
    "CREATE TRIGGER identity_no_delete BEFORE DELETE ON register_identity BEGIN SELECT RAISE(ABORT,'immutable'); END",
    "CREATE TRIGGER identity_once BEFORE INSERT ON register_identity WHEN EXISTS(SELECT 1 FROM register_identity) BEGIN SELECT RAISE(ABORT,'immutable'); END",
    "CREATE TRIGGER event_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'immutable'); END",
    "CREATE TRIGGER event_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'immutable'); END",
    "CREATE TRIGGER event_order BEFORE INSERT ON events WHEN NEW.sequence != (SELECT count(*)+1 FROM events) OR (NEW.sequence=1 AND NEW.kind!='initial') OR (NEW.sequence=2 AND NEW.kind!='conflict') BEGIN SELECT RAISE(ABORT,'sequence'); END",
)


def _connect(path: Path, readonly: bool) -> sqlite3.Connection:
    db = sqlite3.connect(
        path.as_uri() + ("?mode=ro" if readonly else "?mode=rw"),
        uri=True,
        timeout=2,
        isolation_level=None,
    )
    try:
        db.enable_load_extension(False)
        db.execute("PRAGMA trusted_schema=OFF")
        db.execute("PRAGMA temp_store=MEMORY")
        if readonly:
            db.execute("PRAGMA query_only=ON")
        else:
            db.execute("PRAGMA synchronous=EXTRA")
            db.execute("PRAGMA fullfsync=ON")
            db.execute("PRAGMA cache_spill=OFF")
            if db.execute("PRAGMA synchronous").fetchone() != (3,) or db.execute(
                "PRAGMA fullfsync"
            ).fetchone() != (1,):
                raise review.ReviewError("register_unavailable")
        if db.execute("PRAGMA journal_mode").fetchone() != ("delete",):
            raise review.ReviewError("register_corrupt")
        return db
    except BaseException:
        db.close()
        raise


def _file(root: int, name: str, inode: int | None = None) -> int:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
    try:
        info = os.fstat(fd)
        packet.private(info)
        if inode is not None and info.st_ino != inode:
            raise review.ReviewError("unsafe_storage")
        if info.st_size > (MAX_DATABASE_BYTES if name in {DATABASE, JOURNAL} else 4096):
            raise review.ReviewError("resource_limit")
        if name == DATABASE:
            # A read-only SQLite WAL connection can create sidecars in a writable
            # directory. Reject unsupported pager modes BEFORE SQLite opens it.
            header = os.pread(fd, 100, 0)
            if (
                len(header) != 100
                or not header.startswith(b"SQLite format 3\0")
                or header[18:20] != b"\x01\x01"
            ):
                raise review.ReviewError("register_corrupt")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _layout(root: int, *, readonly: bool) -> tuple[review.Issue, ...]:
    entries = set(os.listdir(root))
    if not {DATABASE, LOCK}.issubset(entries) or entries - {
        DATABASE,
        LOCK,
        PENDING,
        JOURNAL,
    }:
        raise review.ReviewError("register_corrupt")
    issues: list[review.Issue] = []
    if PENDING in entries:
        marker = review.decode(packet.read_file(root, PENDING, 4096), 4096)
        if (
            type(marker) is not dict
            or set(marker)
            != {"assignment_sha256", "payload_sha256", "signature_sha256", "sequence"}
            or marker["sequence"] not in (1, 2)
            or type(marker["sequence"]) is not int
            or any(
                not isinstance(marker[k], str)
                or len(marker[k]) != 64
                or any(c not in "0123456789abcdef" for c in marker[k])
                for k in ("assignment_sha256", "payload_sha256", "signature_sha256")
            )
        ):
            raise review.ReviewError("register_corrupt")
        issues.append("register_pending")
    if JOURNAL in entries:
        fd = _file(root, JOURNAL)
        os.close(fd)
        issues.append("rollback_journal_present")
    if issues and not readonly:
        raise review.ReviewError("register_pending")
    return tuple(issues)


@dataclass
class _Storage:
    binding: ReviewRegisterBinding
    root: int
    lock: int
    file: int
    db: sqlite3.Connection
    issues: tuple[review.Issue, ...]

    def check(self, *, readonly: bool) -> None:
        binding = self.binding
        fd = packet.directory(
            Path(binding.configuration.path), (binding.device, binding.directory_inode)
        )
        try:
            packet.private(os.fstat(fd), is_directory=True)
            for name, retained, inode in (
                (DATABASE, self.file, binding.database_inode),
                (LOCK, self.lock, binding.lock_inode),
            ):
                current = _file(fd, name, inode)
                try:
                    if os.fstat(current).st_dev != binding.device or (
                        os.fstat(current).st_dev,
                        os.fstat(current).st_ino,
                    ) != (os.fstat(retained).st_dev, os.fstat(retained).st_ino):
                        raise review.ReviewError("unsafe_storage")
                finally:
                    os.close(current)
            self.issues = _layout(fd, readonly=readonly)
        finally:
            os.close(fd)


@contextmanager
def _open(binding: ReviewRegisterBinding, *, readonly: bool) -> Iterator[_Storage]:
    value = review.checked(ReviewRegisterBinding, binding, "unsafe_storage")
    root = lock = file = None
    db = None
    try:
        root = packet.directory(
            Path(value.configuration.path), (value.device, value.directory_inode)
        )
        packet.private(os.fstat(root), is_directory=True)
        lock = _file(root, LOCK, value.lock_inode)
        try:
            fcntl.flock(
                lock, (fcntl.LOCK_SH if readonly else fcntl.LOCK_EX) | fcntl.LOCK_NB
            )
        except BlockingIOError:
            raise review.ReviewError("register_busy") from None
        issues = _layout(root, readonly=readonly)
        file = _file(root, DATABASE, value.database_inode)
        db = _connect(Path(value.configuration.path) / DATABASE, readonly)
        storage = _Storage(value, root, lock, file, db, issues)
        storage.check(readonly=readonly)
        yield storage
        storage.check(readonly=readonly)
    except review.ReviewError:
        raise
    except sqlite3.Error as error:
        code = getattr(error, "sqlite_errorcode", 0) & 255
        raise review.ReviewError(
            "register_busy"
            if code in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
            else "register_unavailable"
        ) from None
    except Exception:  # noqa: BLE001 - paths/SQL and external diagnostics stay private
        raise review.ReviewError("register_unavailable") from None
    finally:
        close_failed = False
        try:
            if db is not None:
                db.close()
        except BaseException:  # noqa: BLE001 - no external close diagnostics
            close_failed = True
        finally:
            for fd in (file, lock, root):
                if fd is not None:
                    try:
                        os.close(fd)
                    except BaseException:  # noqa: BLE001 - close every retained descriptor
                        close_failed = True
        if close_failed:
            raise review.ReviewError("register_unavailable") from None


def _event_digest(value: RegisteredEvent) -> str:
    return fingerprint(
        {
            "domain": "canary-registered-review-event-v1",
            "event": value.model_dump(mode="json", exclude={"event_sha256"}),
        }
    )


def _validate(storage: _Storage) -> tuple[RegisteredEvent, ...]:
    db, binding = storage.db, storage.binding
    if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
        raise review.ReviewError("register_corrupt")
    actual = tuple(
        row[0]
        for row in db.execute(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name"
        )
    )
    if tuple(sorted(actual)) != tuple(sorted(_SCHEMA)):
        raise review.ReviewError("register_corrupt")
    identity = db.execute(
        "SELECT singleton,binding,zero_head FROM register_identity"
    ).fetchall()
    if identity != [(1, review.encode(binding).decode(), zero_head(binding))]:
        raise review.ReviewError("register_corrupt")
    events: list[RegisteredEvent] = []
    rows = db.execute(
        "SELECT sequence,kind,previous_sha256,payload_sha256,event_sha256,canonical_event FROM events ORDER BY sequence LIMIT 3"
    ).fetchall()
    if len(rows) > 2:
        raise review.ReviewError("register_corrupt")
    for row in rows:
        value = review.parse(
            RegisteredEvent, row[5].encode(), "register_corrupt", MAX_EVENT_BYTES
        )
        payload = review.parse_review_payload(value.payload_utf8.encode())
        try:
            signature = base64.b64decode(value.signature_base64, validate=True)
        except ValueError:
            raise review.ReviewError("register_corrupt") from None
        if (
            base64.b64encode(signature).decode() != value.signature_base64
            or not 0 < len(signature) <= review.MAX_SIGNATURE_BYTES
            or value.sequence != len(events) + 1
            or value.kind != ("initial" if not events else "conflict")
            or value.previous_sha256
            != (events[-1].event_sha256 if events else zero_head(binding))
            or value.assignment_sha256 != binding.configuration.assignment_sha256
            or payload.assignment_sha256 != value.assignment_sha256
            or value.event_sha256 != _event_digest(value)
            or row[:5]
            != (
                value.sequence,
                value.kind,
                value.previous_sha256,
                sha256(value.payload_utf8.encode()).hexdigest(),
                value.event_sha256,
            )
            or value.verification.payload_sha256 != row[3]
            or value.verification.signature_sha256 != sha256(signature).hexdigest()
            or value.verification.observation_sha256
            != fingerprint(value.observation.model_dump(mode="json"))
            or value.verification.verified_at != value.admission_checked_at
            or value.verification.trust_policy_identity_sha256
            != binding.configuration.trust_policy_identity_sha256
            or review.policy_identity(value.observation.policy)
            != binding.configuration.trust_policy_identity_sha256
        ):
            raise review.ReviewError("register_corrupt")
        if events and value.payload_utf8 == events[0].payload_utf8:
            raise review.ReviewError("register_corrupt")
        events.append(value)
    if "register_pending" in storage.issues:
        marker = review.decode(packet.read_file(storage.root, PENDING, 4096), 4096)
        if marker["assignment_sha256"] != binding.configuration.assignment_sha256:
            raise review.ReviewError("register_corrupt")
    return tuple(events)


def _sync(storage: _Storage) -> None:
    os.fsync(storage.file)
    os.fsync(storage.root)


def initialize_register(
    configuration: ReviewRegisterConfiguration,
    *,
    protected_roots: tuple[packet.ProtectedRoot, ...],
) -> RegisterInitializationResult:
    value = review.checked(
        ReviewRegisterConfiguration, configuration, "invalid_assignment"
    )
    root = None
    db = None
    try:
        path = packet.absolute(value.path)
        packet.check_protection(path, protected_roots)
        parent = packet.directory(path.parent)
        try:
            os.mkdir(path.name, mode=0o700, dir_fd=parent)
            os.fsync(parent)
        finally:
            os.close(parent)
        root = packet.directory(path)
        packet.private(os.fstat(root), is_directory=True)
        inodes = []
        for name in (DATABASE, LOCK):
            fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=root,
            )
            try:
                packet.private(os.fstat(fd))
                inodes.append(os.fstat(fd).st_ino)
                os.fsync(fd)
            finally:
                os.close(fd)
        info = os.fstat(root)
        binding = ReviewRegisterBinding(
            configuration=value,
            device=info.st_dev,
            directory_inode=info.st_ino,
            database_inode=inodes[0],
            lock_inode=inodes[1],
        )
        db = _connect(path / DATABASE, False)
        db.execute("BEGIN IMMEDIATE")
        for statement in _SCHEMA:
            db.execute(statement)
        db.execute(
            "INSERT INTO register_identity VALUES(1,?,?)",
            (review.encode(binding).decode(), zero_head(binding)),
        )
        db.execute("COMMIT")
        db.close()
        db = None
        fd = _file(root, DATABASE, binding.database_inode)
        os.fsync(fd)
        os.close(fd)
        os.fsync(root)
        os.close(root)
        root = None
        with _open(binding, readonly=True) as storage:
            if _validate(storage):
                raise review.ReviewError("register_corrupt")
        return RegisterInitializationResult(
            binding=binding, checkpoint_candidate=_checkpoint(binding, ())
        )
    except BaseException:  # noqa: BLE001 - partial roots are preserved, never reused
        raise review.ReviewError("initialization_failed") from None
    finally:
        if db is not None:
            with suppress(Exception):
                db.close()
        if root is not None:
            with suppress(OSError):
                os.close(root)


def _assignment(
    binding: ReviewRegisterBinding, expected: review.ReviewAssignment
) -> review.ReviewAssignment:
    value = review.checked(
        review.ReviewAssignment, expected, "invalid_assignment", review.MAX_SMALL_BYTES
    )
    if value != binding.configuration.assignment:
        raise review.ReviewError("binding_mismatch")
    return value


def _historical(
    events: tuple[RegisteredEvent, ...],
    expected: review.ReviewAssignment,
    material: packet.PacketMaterial,
) -> None:
    for event in events:
        result = review.verify_review_for_submission(
            event.payload_utf8.encode(),
            base64.b64decode(event.signature_base64, validate=True),
            expected=expected,
            observation=event.observation,
            now=review.time_value(event.admission_checked_at),
        )
        if result != event.verification:
            raise review.ReviewError("register_corrupt")
        packet.validate_references(
            review.parse_review_payload(event.payload_utf8.encode()), material.packet
        )


def _submission(
    payload: bytes,
    signature: bytes,
    expected: review.ReviewAssignment,
    policy: Callable[[], review.ReviewPolicyObservation],
    clock: Callable[[], datetime],
) -> tuple[review.SubmissionVerification, review.ReviewPolicyObservation]:
    try:
        observation = review.checked(
            review.ReviewPolicyObservation,
            policy(),
            "invalid_policy",
            review.MAX_SMALL_BYTES,
        )
        now = review.checked_now(clock())
        verified = review.verify_review_for_submission(
            payload, signature, expected=expected, observation=observation, now=now
        )
        return verified, observation
    except review.ReviewError:
        raise
    except BaseException:  # noqa: BLE001 - trusted supplier faults are still private
        raise review.ReviewError("verification_interrupted") from None


def _pending(
    storage: _Storage, value: review.SubmissionVerification, sequence: int
) -> None:
    raw = review.encode(
        {
            "assignment_sha256": value.assignment_sha256,
            "payload_sha256": value.payload_sha256,
            "signature_sha256": value.signature_sha256,
            "sequence": sequence,
        },
        4096,
    )
    fd = os.open(
        PENDING,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=storage.root,
    )
    try:
        if os.write(fd, raw) != len(raw):
            raise OSError
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(storage.root)


def _insert(storage: _Storage, event: RegisteredEvent) -> None:
    raw = review.encode(event, MAX_EVENT_BYTES).decode()
    storage.db.execute(
        "INSERT INTO events VALUES(?,?,?,?,?,?)",
        (
            event.sequence,
            event.kind,
            event.previous_sha256,
            event.verification.payload_sha256,
            event.event_sha256,
            raw,
        ),
    )


def _commit(db: sqlite3.Connection) -> None:
    db.execute("COMMIT")


def _clear_pending(storage: _Storage) -> None:
    os.unlink(PENDING, dir_fd=storage.root)
    os.fsync(storage.root)


def register_review(
    payload: bytes,
    signature: bytes,
    *,
    expected: review.ReviewAssignment,
    envelope_raw: bytes,
    registry: journal.RegistryBinding,
    register: ReviewRegisterBinding,
    policy: Callable[[], review.ReviewPolicyObservation],
    clock: Callable[[], datetime],
) -> RegistrationResult:
    binding = review.checked(ReviewRegisterBinding, register, "unsafe_storage")
    assignment = _assignment(binding, expected)
    # Reject unauthenticated/ineligible submissions BEFORE opening writable state.
    _submission(payload, signature, assignment, policy, clock)
    material = packet.acquire_packet(
        envelope_raw, expected=assignment.subject.expected_envelope, registry=registry
    )
    packet.verify_assignment_packet(material, assignment)
    packet.validate_references(review.parse_review_payload(payload), material.packet)
    commit_started = False
    try:
        with _open(binding, readonly=False) as storage:
            storage.db.execute("BEGIN IMMEDIATE")
            pending_attempted = False
            try:
                events = _validate(storage)
                _historical(events, assignment, material)
                verification, observed = _submission(
                    payload, signature, assignment, policy, clock
                )
                if events and observed.revocation_revision < max(
                    e.observation.revocation_revision for e in events
                ):
                    raise review.ReviewError("policy_changed")
                if len(events) == 2:
                    storage.db.execute("ROLLBACK")
                    result = RegistrationResult(
                        status="ALREADY_CONFLICTED",
                        checkpoint_candidate=_checkpoint(binding, events),
                        publication_status="existing-record-observed",
                    )
                elif events and events[0].payload_utf8.encode() == payload:
                    storage.db.execute("ROLLBACK")
                    result = RegistrationResult(
                        status="ALREADY_RECORDED",
                        checkpoint_candidate=_checkpoint(binding, events),
                        publication_status="existing-record-observed",
                    )
                else:
                    event = RegisteredEvent(
                        sequence=len(events) + 1,
                        kind="conflict" if events else "initial",
                        previous_sha256=events[-1].event_sha256
                        if events
                        else zero_head(binding),
                        assignment_sha256=review.assignment_commitment(assignment),
                        payload_utf8=payload.decode(),
                        signature_base64=base64.b64encode(signature).decode(),
                        observation=observed,
                        verification=verification,
                        admission_checked_at=verification.verified_at,
                        event_sha256="0" * 64,
                    )
                    event = event.model_copy(
                        update={"event_sha256": _event_digest(event)}
                    )
                    review.encode(event, MAX_EVENT_BYTES)
                    storage.check(readonly=False)
                    pending_attempted = True
                    _pending(storage, verification, event.sequence)
                    _insert(storage, event)
                    storage.check(readonly=True)
                    final, final_observed = _submission(
                        payload, signature, assignment, policy, clock
                    )
                    if (
                        final_observed != observed
                        or final.observation_sha256 != verification.observation_sha256
                    ):
                        raise review.ReviewError("policy_changed")
                    commit_started = True
                    _commit(storage.db)
                    _sync(storage)
                    storage.check(readonly=True)
                    _clear_pending(storage)
                    storage.check(readonly=False)
                    saved = _validate(storage)
                    if saved != (*events, event):
                        raise review.ReviewError("register_corrupt")
                    result = RegistrationResult(
                        status="CONFLICT_RECORDED" if events else "RECORDED",
                        checkpoint_candidate=_checkpoint(binding, saved),
                        publication_status="local-registration-protocol-completed",
                    )
            except BaseException as error:
                if commit_started:
                    raise review.ReviewError("registration_outcome_unknown") from None
                try:
                    if storage.db.in_transaction:
                        storage.db.execute("ROLLBACK")
                    if pending_attempted:
                        _sync(storage)
                        if PENDING in os.listdir(storage.root):
                            _clear_pending(storage)
                except BaseException:  # noqa: BLE001 - unknown rollback retains blockers
                    raise review.ReviewError("registration_outcome_unknown") from None
                if isinstance(error, review.ReviewError):
                    raise
                raise review.ReviewError("registration_failed_uncommitted") from None
        return result
    except BaseException as error:
        if commit_started:
            raise review.ReviewError("registration_outcome_unknown") from None
        if isinstance(error, review.ReviewError):
            raise
        raise review.ReviewError("registration_failed_uncommitted") from None


def _checkpoint_status(
    binding: ReviewRegisterBinding,
    events: tuple[RegisteredEvent, ...],
    supplied: ReviewRegisterCheckpoint | None,
) -> tuple[CheckpointStatus, tuple[review.Issue, ...]]:
    if supplied is None:
        return "missing", ("checkpoint_missing",)
    value = review.checked(
        ReviewRegisterCheckpoint,
        supplied,
        "checkpoint_mismatch",
        review.MAX_SMALL_BYTES,
    )
    actual = _checkpoint(binding, events)
    for field in (
        "register_id",
        "register_binding_sha256",
        "assignment_sha256",
        "trust_policy_identity_sha256",
    ):
        if getattr(value, field) != getattr(actual, field):
            return "mismatch", ("checkpoint_mismatch",)
    if value.event_count > len(events):
        return "behind", ("state_behind_checkpoint",)
    head = (
        events[value.event_count - 1].event_sha256
        if value.event_count
        else zero_head(binding)
    )
    if value.head_sha256 != head:
        return "mismatch", ("checkpoint_mismatch",)
    if value.event_count < len(events):
        return "stale", ("checkpoint_stale",)
    return "matches", ()


def inspect_register(
    register: ReviewRegisterBinding,
    *,
    expected: review.ReviewAssignment,
    checkpoint: ReviewRegisterCheckpoint | None = None,
) -> RegisterInspection:
    binding = review.checked(ReviewRegisterBinding, register, "unsafe_storage")
    _assignment(binding, expected)
    with _open(binding, readonly=True) as storage:
        storage.db.execute("BEGIN")
        events = _validate(storage)
        storage.check(readonly=True)
        status, issues = _checkpoint_status(binding, events, checkpoint)
        result = RegisterInspection(
            state="CONFLICT" if len(events) == 2 else "RECORDED" if events else "EMPTY",
            events=events,
            checkpoint_candidate=_checkpoint(binding, events),
            checkpoint_status=status,
            issues=(*storage.issues, *issues),
        )
        storage.db.execute("ROLLBACK")
    return result


def assess_registered_review(
    register: ReviewRegisterBinding,
    *,
    expected: review.ReviewAssignment,
    checkpoint: ReviewRegisterCheckpoint,
    envelope_raw: bytes,
    registry: journal.RegistryBinding,
    policy: Callable[[], review.ReviewPolicyObservation],
    clock: Callable[[], datetime],
) -> review.PostReviewAssessment:
    """Read-only current reliance, including stale-anchor AND verified conflicts.

    Historical signature checks use archived observations pinned by the independent
    assignment. They do not establish independently trusted historical signing time.
    No authority-store or execution-approval verification is performed.
    """
    binding = review.checked(ReviewRegisterBinding, register, "unsafe_storage")
    assignment = _assignment(binding, expected)
    issues: list[review.Issue] = []
    inspection = None
    material = None
    current_observation = None
    current_verified_at = None
    authenticated: list[review.ReviewPayload] = []
    signature_status: Literal["verified", "not-performed", "error"] = "not-performed"
    policy_status: Literal["acceptable", "error"] = "error"
    provenance: Literal[
        "anchored-journal-checks", "anchored-envelope-status-only", "not-established"
    ] = "not-established"
    completion: Literal["completed", "not-established"] = "not-established"
    mechanical = review.QualityCheck(
        status="SKIP", issues=("recorded_mechanical_unavailable",)
    )
    operational = review.QualityCheck(
        status="SKIP", issues=("recorded_operational_unavailable",)
    )
    historical = review.QualityCheck(
        status="SKIP", issues=("recorded_overall_unavailable",)
    )
    try:
        observed = policy()
        now = clock()
        current_observation = review.verify_current_policy(assignment, observed, now)
        current_verified_at = review.utc_text(now)
        policy_status = "acceptable"
    except review.ReviewError as error:
        issues.append(error.code)
    except BaseException:  # noqa: BLE001 - no supplied diagnostics in reports
        issues.append("verification_interrupted")
    try:
        inspection = inspect_register(
            binding, expected=assignment, checkpoint=checkpoint
        )
        issues.extend(inspection.issues)
        if (
            current_observation is not None
            and inspection.events
            and current_observation.revocation_revision
            < max(e.observation.revocation_revision for e in inspection.events)
        ):
            issues.append("policy_changed")
            policy_status = "error"
    except review.ReviewError as error:
        issues.append(error.code)
    try:
        envelope.verify_envelope(
            envelope_raw, expected=assignment.subject.expected_envelope
        )
        original = envelope.parse_envelope(envelope_raw)
        if (
            packet._subject(original, assignment.subject.expected_envelope)
            != assignment.subject
        ):
            raise review.ReviewError("source_mismatch")
        provenance = "anchored-envelope-status-only"
        completion = (
            "completed"
            if original.execution.journal_completion_certified
            else "not-established"
        )

        def recorded(status: review.Status | None, name: str) -> review.QualityCheck:
            if status is None:
                return review.QualityCheck(
                    status="SKIP", issues=(name + "_unavailable",)
                )
            return review.QualityCheck(
                status=status,
                issues=() if status == "PASS" else (name + "_" + status.lower(),),
            )

        mechanical = recorded(
            original.execution.mechanical_assessment_status, "recorded_mechanical"
        )
        operational = recorded(
            original.execution.operational_assessment_status, "recorded_operational"
        )
        historical = recorded(
            original.execution.overall_assessment_status, "recorded_overall"
        )
        material = packet.acquire_packet(
            envelope_raw,
            expected=assignment.subject.expected_envelope,
            registry=registry,
        )
        packet.verify_assignment_packet(material, assignment)
        mechanical = material.packet.assessments.mechanical
        operational = material.packet.assessments.operational
        historical = material.packet.assessments.historical_overall
        provenance = "anchored-journal-checks"
    except review.ReviewError as error:
        material = None
        issues.append(error.code)
    except envelope.EnvelopeError:
        issues.append("source_mismatch")
    if inspection is not None:
        for event in inspection.events:
            try:
                raw = event.payload_utf8.encode()
                verified = review.verify_review_for_submission(
                    raw,
                    base64.b64decode(event.signature_base64, validate=True),
                    expected=assignment,
                    observation=event.observation,
                    now=review.time_value(event.admission_checked_at),
                )
                if verified != event.verification:
                    raise review.ReviewError("register_corrupt")
                payload = review.parse_review_payload(raw)
                if material is not None:
                    packet.validate_references(payload, material.packet)
                authenticated.append(payload)
            except review.ReviewError as error:
                issues.append(error.code)
                signature_status = "error"
            except Exception:  # noqa: BLE001 - stored malformed signature remains private
                issues.append("register_corrupt")
                signature_status = "error"
        if inspection.events and signature_status != "error":
            signature_status = "verified"
    conflict: Literal["absent", "authenticated", "not-established"] = "absent"
    if inspection is not None and inspection.state == "CONFLICT":
        conflict = "authenticated" if len(authenticated) == 2 else "not-established"
        if conflict == "authenticated":
            issues.append("review_conflict")
    verification = (
        review.QualityCheck(status="ERROR", issues=tuple(dict.fromkeys(issues)))
        if issues
        else review.QualityCheck(status="PASS")
    )
    human_state: Literal["PENDING", "COMPLETE", "UNABLE", "REJECTED"] = "REJECTED"
    first = authenticated[0] if authenticated else None
    if first is not None and policy_status == "acceptable":
        human_state = first.completion
    elif inspection is not None and inspection.state == "EMPTY" and not issues:
        human_state = "PENDING"
    result = review.combine_post_review(
        review.AssessmentInputs(
            mechanical=mechanical,
            operational=operational,
            historical_overall=historical,
            verification=verification,
            human_state=human_state,
            review=first,
        )
    )
    details = review.RelianceDetails(
        assignment_sha256=review.assignment_commitment(assignment),
        subject=assignment.subject,
        rubric_sha256=assignment.rubric_sha256,
        register_id=assignment.register_id,
        register_state=inspection.state if inspection else "UNAVAILABLE",
        event_count=len(inspection.events) if inspection else None,
        observed_head_sha256=inspection.checkpoint_candidate.head_sha256
        if inspection
        else None,
        checkpoint_status=inspection.checkpoint_status if inspection else "unavailable",
        conflict_authentication=conflict,
        reviewer_signature=signature_status,
        current_policy=policy_status,
        current_verified_at=current_verified_at,
        current_policy_observation_sha256=fingerprint(
            current_observation.model_dump(mode="json")
        )
        if current_observation is not None
        else None,
        source_comparison="matches-current-inspection" if material else "error",
        recorded_assessment_provenance=provenance,
        authenticated_reviews=tuple(authenticated),
    )
    return result.model_copy(
        update={"details": details, "journal_completion": completion}
    )
