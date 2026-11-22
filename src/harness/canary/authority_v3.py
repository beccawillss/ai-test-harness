"""Single-use synthetic records in one independently trusted local store.

No execution/admission token, controller, journal, provider or signing interface.
Configuration, policy/clock suppliers, Python/SQLite/OS and the private filesystem
are trusted. Multi-host use, hostile same-user writes and rollback are unsupported.
"""

from __future__ import annotations

import fcntl
import os
import sqlite3
import stat
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, model_validator

from harness.canary import approval_v3 as approval
from harness.canary.runtime_v3 import Digest, Frozen, _plain
from harness.core.fingerprints import canonical_json, fingerprint

_DATABASE = "authority.sqlite3"
_LOCK = "writer.lock"
_PENDING = "pending-consumption.json"
_JOURNAL = "authority.sqlite3-journal"
_BUSY_SECONDS = 2.0
StoreID = Annotated[str, Field(pattern=r"^synthetic-store-[0-9a-f]{32}$")]
RunID = Annotated[str, Field(pattern=r"^synthetic-run-[0-9a-f]{32}$")]
RecordID = Annotated[str, Field(pattern=r"^synthetic-consumption-[0-9a-f]{32}$")]


class AuthorityError(ValueError):
    """Fixed categories only; never expose SQL, paths or supplied diagnostics."""

    def __init__(self, code: str):
        allowed = {
            "invalid_configuration",
            "invalid_binding",
            "invalid_policy_snapshot",
            "invalid_clock",
            "policy_stale",
            "policy_changed",
            "policy_binding_mismatch",
            "audience_mismatch",
            "verification_interrupted",
            "store_initialization_failed",
            "store_unavailable",
            "store_identity_mismatch",
            "store_permissions",
            "store_corrupt",
            "store_busy",
            "store_pending",
            "store_recovery_required",
            "authorisation_consumed",
            "authorisation_conflict",
            "invalid_inspection",
            "consumption_failed_uncommitted",
            "consumption_outcome_unknown",
        }
        super().__init__(code if code in allowed else "store_unavailable")


def _time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _clock(clock: Callable[[], datetime]) -> datetime:
    try:
        now = clock()
        if (
            type(now) is not datetime
            or now.utcoffset() != timedelta(0)
            or now.microsecond
        ):
            raise ValueError
        return now
    except Exception:  # noqa: BLE001 - trusted supplier failures still remain private
        raise AuthorityError("invalid_clock") from None


class TrustedStoreConfiguration(Frozen):
    schema_id: Literal["canary-synthetic-authority-config-v1"]
    store_path: str
    store_id: StoreID
    execution_audience: approval.Audience
    trust_policy_identity_sha256: Digest
    host_id: approval.Audience
    host_scope: Literal["synthetic-single-host-local"]

    @model_validator(mode="after")
    def _absolute(self) -> TrustedStoreConfiguration:
        path = Path(self.store_path)
        if not path.is_absolute() or str(path) != self.store_path or ".." in path.parts:
            raise ValueError("canonical_absolute_store_required")
        return self


class AuthorityStoreBinding(Frozen):
    schema_id: Literal["canary-synthetic-authority-binding-v1"]
    configuration: TrustedStoreConfiguration
    device: int = Field(ge=0)
    directory_inode: int = Field(ge=1)
    database_inode: int = Field(ge=1)
    lock_inode: int = Field(ge=1)


class PolicyObservation(Frozen):
    """Trusted caller's current synthetic policy; not an external attestation."""

    schema_id: Literal["canary-synthetic-policy-observation-v1"]
    policy: approval.SyntheticTrustPolicy
    observed_at: approval.Timestamp
    expires_at: approval.Timestamp

    @model_validator(mode="after")
    def _window(self) -> PolicyObservation:
        start, end = _time(self.observed_at), _time(self.expires_at)
        if not timedelta(0) < end - start <= timedelta(seconds=60):
            raise ValueError("invalid_policy_freshness_window")
        return self


class ConsumptionReceipt(Frozen):
    schema_id: Literal["canary-synthetic-consumption-v1"]
    store_id: StoreID
    authorisation_id: approval.AuthorisationID
    payload_sha256: Digest
    signature_sha256: Digest
    trust_policy_sha256: Digest
    trust_policy_identity_sha256: Digest
    source_receipt_sha256: Digest
    proposal_sha256: Digest
    execution_audience: approval.Audience
    intended_run_id: RunID
    record_id: RecordID
    consumed_at: approval.Timestamp
    verification_sha256: Digest
    signer_principal: approval.Principal
    signer_public_key_sha256: Digest
    assurance_class: Literal["synthetic-offline-only"] = "synthetic-offline-only"
    real_human_authorisation_authenticated: Literal[False] = False
    source_authorised: Literal[False] = False
    provider_evidence_authenticated: Literal[False] = False
    authorises_live_execution: Literal[False] = False

    @model_validator(mode="after")
    def _valid_time(self) -> ConsumptionReceipt:
        _time(self.consumed_at)
        return self


class ConsumptionInspection(Frozen):
    schema_id: Literal["canary-synthetic-consumption-inspection-v1"] = (
        "canary-synthetic-consumption-inspection-v1"
    )
    status: Literal["consumed", "absent", "conflict", "corrupt", "unavailable"]
    record: ConsumptionReceipt | None = None
    issues: tuple[str, ...] = ()
    assurance_class: Literal["synthetic-offline-only"] = "synthetic-offline-only"
    real_human_authorisation_authenticated: Literal[False] = False
    source_authorised: Literal[False] = False
    provider_evidence_authenticated: Literal[False] = False
    authorises_live_execution: Literal[False] = False


def _strict[Model: Frozen](model: type[Model], value: object, code: str) -> Model:
    try:
        plain = _plain(value)
        result = model.model_validate(plain)
        if canonical_json(plain) != canonical_json(result.model_dump(mode="json")):
            raise ValueError
        return result
    except Exception:  # noqa: BLE001 - suppress validation input and callback content
        raise AuthorityError(code) from None


def policy_identity(policy: approval.SyntheticTrustPolicy) -> str:
    """Pin key/principal/roles/lifetime; only revocations are refreshable facts."""
    checked = _strict(approval.SyntheticTrustPolicy, policy, "invalid_policy_snapshot")
    return fingerprint(checked.model_dump(mode="json", exclude={"revoked_public_keys"}))


def _observation(
    supplier: Callable[[], PolicyObservation],
    binding: AuthorityStoreBinding,
    now: datetime,
) -> PolicyObservation:
    try:
        observation = _strict(PolicyObservation, supplier(), "invalid_policy_snapshot")
    except AuthorityError:
        raise
    except Exception:  # noqa: BLE001 - keep external diagnostics private
        raise AuthorityError("invalid_policy_snapshot") from None
    if not _time(observation.observed_at) <= now < _time(observation.expires_at):
        raise AuthorityError("policy_stale")
    if (
        policy_identity(observation.policy)
        != binding.configuration.trust_policy_identity_sha256
    ):
        raise AuthorityError("policy_binding_mismatch")
    return observation


def _boundary(
    manifest: approval.ApprovalManifest,
    verified: approval.ApprovalVerification,
    binding: AuthorityStoreBinding,
    policy: Callable[[], PolicyObservation],
    clock: Callable[[], datetime],
) -> datetime:
    now = _clock(clock)
    observation = _observation(policy, binding, now)
    if (
        fingerprint(observation.policy.model_dump(mode="json"))
        != verified.trust_policy_sha256
    ):
        raise AuthorityError("policy_changed")
    if now < _time(manifest.not_before):
        raise approval.ApprovalError("approval_not_yet_valid")
    if now >= _time(manifest.expires_at):
        raise approval.ApprovalError("approval_expired")
    return now


def _verify(
    payload: bytes,
    signature: bytes,
    expected: approval.ProposedCanary,
    binding: AuthorityStoreBinding,
    policy: Callable[[], PolicyObservation],
    clock: Callable[[], datetime],
) -> tuple[approval.ApprovalManifest, approval.ApprovalVerification, datetime]:
    now = _clock(clock)
    observation = _observation(policy, binding, now)
    verified = approval.verify_approval(
        payload, signature, expected=expected, trust_policy=observation.policy, now=now
    )
    manifest = approval.parse_manifest(payload)
    if (
        manifest.execution.execution_audience
        != binding.configuration.execution_audience
    ):
        raise AuthorityError("audience_mismatch")
    checked_at = _boundary(manifest, verified, binding, policy, clock)
    return manifest, verified, checked_at


# Fixed statement text only. Every caller-supplied SQL value uses parameters.
_DDL = (
    (
        "table",
        "store_identity",
        "store_identity",
        "CREATE TABLE store_identity (singleton INTEGER PRIMARY KEY CHECK (singleton = 1), binding_json TEXT NOT NULL, binding_sha256 TEXT NOT NULL) STRICT",
    ),
    (
        "table",
        "consumptions",
        "consumptions",
        "CREATE TABLE consumptions (authorisation_id TEXT PRIMARY KEY NOT NULL, intended_run_id TEXT NOT NULL UNIQUE, record_id TEXT NOT NULL UNIQUE, record_json TEXT NOT NULL, record_sha256 TEXT NOT NULL) STRICT",
    ),
    (
        "trigger",
        "identity_no_update",
        "store_identity",
        "CREATE TRIGGER identity_no_update BEFORE UPDATE ON store_identity BEGIN SELECT RAISE(ABORT, 'immutable'); END",
    ),
    (
        "trigger",
        "identity_no_delete",
        "store_identity",
        "CREATE TRIGGER identity_no_delete BEFORE DELETE ON store_identity BEGIN SELECT RAISE(ABORT, 'immutable'); END",
    ),
    (
        "trigger",
        "identity_once",
        "store_identity",
        "CREATE TRIGGER identity_once BEFORE INSERT ON store_identity WHEN EXISTS (SELECT 1 FROM store_identity) BEGIN SELECT RAISE(ABORT, 'immutable'); END",
    ),
    (
        "trigger",
        "consumption_no_update",
        "consumptions",
        "CREATE TRIGGER consumption_no_update BEFORE UPDATE ON consumptions BEGIN SELECT RAISE(ABORT, 'immutable'); END",
    ),
    (
        "trigger",
        "consumption_no_delete",
        "consumptions",
        "CREATE TRIGGER consumption_no_delete BEFORE DELETE ON consumptions BEGIN SELECT RAISE(ABORT, 'immutable'); END",
    ),
)
_EXPECTED_SCHEMA = sorted(
    [
        *list(_DDL),
        ("index", "sqlite_autoindex_consumptions_1", "consumptions", None),
        ("index", "sqlite_autoindex_consumptions_2", "consumptions", None),
        ("index", "sqlite_autoindex_consumptions_3", "consumptions", None),
    ]
)


def _private(info: os.stat_result, *, directory: bool = False) -> None:
    if (
        info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
        or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        or (not directory and info.st_nlink != 1)
    ):
        raise AuthorityError("store_permissions")


def _directory(path: Path) -> int:
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            if part in {".", ".."}:
                raise AuthorityError("invalid_configuration")
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = child
            try:
                os.stat(".git", dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise AuthorityError("invalid_configuration")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _file(directory: int, name: str, *, writable: bool = False) -> int:
    descriptor = os.open(
        name,
        (os.O_RDWR if writable else os.O_RDONLY) | os.O_NOFOLLOW | os.O_NONBLOCK,
        dir_fd=directory,
    )
    try:
        _private(os.fstat(descriptor))
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _create(directory: int, name: str) -> int:
    descriptor = os.open(
        name,
        os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=directory,
    )
    try:
        _private(os.fstat(descriptor))
        os.fsync(descriptor)
        os.fsync(directory)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _json_model[Model: Frozen](model: type[Model], raw: str) -> Model:
    try:
        checked = model.model_validate_json(raw)
        if canonical_json(checked.model_dump(mode="json")) != raw:
            raise ValueError
        return checked
    except Exception:  # noqa: BLE001 - keep external diagnostics private
        raise AuthorityError("store_corrupt") from None


def _layout(root: int, *, pending: bool, journal: bool) -> tuple[str, ...]:
    entries = set(os.listdir(root))
    if entries - {_DATABASE, _LOCK, _PENDING, _JOURNAL}:
        raise AuthorityError("store_corrupt")
    if not {_DATABASE, _LOCK} <= entries:
        raise AuthorityError("store_unavailable")
    issues = []
    for name in (_PENDING, _JOURNAL):
        if name in entries:
            descriptor = _file(root, name)
            os.close(descriptor)
    if _PENDING in entries:
        if not pending:
            raise AuthorityError("store_pending")
        issues.append("pending_consumption")
    if _JOURNAL in entries:
        if not journal:
            raise AuthorityError("store_recovery_required")
        issues.append("rollback_journal_present")
    return tuple(issues)


@dataclass
class _Storage:
    binding: AuthorityStoreBinding
    root: int
    database: int
    lock: int
    connection: sqlite3.Connection
    issues: tuple[str, ...] = ()

    def check(self, *, pending: bool = False, journal: bool = False) -> None:
        current = _directory(Path(self.binding.configuration.store_path))
        try:
            _private(os.fstat(current), directory=True)
            for descriptor, inode in (
                (current, self.binding.directory_inode),
                (self.root, self.binding.directory_inode),
                (self.database, self.binding.database_inode),
                (self.lock, self.binding.lock_inode),
            ):
                info = os.fstat(descriptor)
                if (info.st_dev, info.st_ino) != (self.binding.device, inode):
                    raise AuthorityError("store_identity_mismatch")
            for name, inode in (
                (_DATABASE, self.binding.database_inode),
                (_LOCK, self.binding.lock_inode),
            ):
                info = os.stat(name, dir_fd=current, follow_symlinks=False)
                _private(info)
                if (info.st_dev, info.st_ino) != (self.binding.device, inode):
                    raise AuthorityError("store_identity_mismatch")
            self.issues = _layout(current, pending=pending, journal=journal)
        finally:
            os.close(current)


def _connect(path: Path, *, readonly: bool) -> sqlite3.Connection:
    # No rwc fallback, immutable URI, extension loading, ATTACH or environment VFS.
    connection = sqlite3.connect(
        path.as_uri() + ("?mode=ro" if readonly else "?mode=rw"),
        uri=True,
        timeout=_BUSY_SECONDS,
        isolation_level=None,
    )
    try:
        connection.enable_load_extension(False)
        connection.execute("PRAGMA trusted_schema = OFF")
        connection.execute("PRAGMA temp_store = MEMORY")
        if readonly:
            connection.execute("PRAGMA query_only = ON")
        else:
            connection.execute("PRAGMA synchronous = EXTRA")
            connection.execute("PRAGMA fullfsync = ON")
            connection.execute("PRAGMA cache_spill = OFF")
            if connection.execute("PRAGMA synchronous").fetchone() != (
                3,
            ) or connection.execute("PRAGMA fullfsync").fetchone() != (1,):
                raise AuthorityError("store_unavailable")
        if connection.execute("PRAGMA journal_mode").fetchone() != ("delete",):
            raise AuthorityError("store_corrupt")
        return connection
    except BaseException:
        connection.close()
        raise


def _sql_error(error: sqlite3.Error) -> AuthorityError:
    code = getattr(error, "sqlite_errorcode", 0) & 255
    if code in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
        return AuthorityError("store_busy")
    if code in {sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB, sqlite3.SQLITE_SCHEMA}:
        return AuthorityError("store_corrupt")
    return AuthorityError("store_unavailable")


@contextmanager
def _open(binding: AuthorityStoreBinding, *, readonly: bool) -> Iterator[_Storage]:
    descriptors = []
    connection = None
    try:
        root = _directory(Path(binding.configuration.store_path))
        descriptors.append(root)
        _private(os.fstat(root), directory=True)
        if (os.fstat(root).st_dev, os.fstat(root).st_ino) != (
            binding.device,
            binding.directory_inode,
        ):
            raise AuthorityError("store_identity_mismatch")
        lock = _file(root, _LOCK, writable=not readonly)
        descriptors.append(lock)
        if (os.fstat(lock).st_dev, os.fstat(lock).st_ino) != (
            binding.device,
            binding.lock_inode,
        ):
            raise AuthorityError("store_identity_mismatch")
        try:
            fcntl.flock(
                lock, (fcntl.LOCK_SH if readonly else fcntl.LOCK_EX) | fcntl.LOCK_NB
            )
        except BlockingIOError:
            raise AuthorityError("store_busy") from None
        database = _file(root, _DATABASE, writable=not readonly)
        descriptors.append(database)
        # Check layout before SQLite can attempt rollback recovery.
        issues = _layout(root, pending=readonly, journal=readonly)
        if (os.fstat(database).st_dev, os.fstat(database).st_ino) != (
            binding.device,
            binding.database_inode,
        ):
            raise AuthorityError("store_identity_mismatch")
        connection = _connect(
            Path(binding.configuration.store_path) / _DATABASE, readonly=readonly
        )
        storage = _Storage(binding, root, database, lock, connection, issues)
        storage.check(pending=readonly, journal=readonly)
        yield storage
    except (AuthorityError, approval.ApprovalError):
        raise
    except sqlite3.Error as error:
        raise _sql_error(error) from None
    except Exception:  # noqa: BLE001 - keep external diagnostics private
        raise AuthorityError("store_unavailable") from None
    finally:
        if connection is not None:
            with suppress(sqlite3.Error):
                connection.close()
        for descriptor in reversed(descriptors):
            with suppress(OSError):
                os.close(descriptor)


def _validate(storage: _Storage) -> dict[str, ConsumptionReceipt]:
    db = storage.connection
    if db.execute("PRAGMA user_version").fetchone() != (1,) or db.execute(
        "PRAGMA application_id"
    ).fetchone() != (1128355379,):
        raise AuthorityError("store_corrupt")
    if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
        raise AuthorityError("store_corrupt")
    if (
        db.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_schema ORDER BY type, name"
        ).fetchall()
        != _EXPECTED_SCHEMA
    ):
        raise AuthorityError("store_corrupt")
    identity = db.execute(
        "SELECT singleton, binding_json, binding_sha256 FROM store_identity"
    ).fetchall()
    raw = canonical_json(storage.binding.model_dump(mode="json"))
    if identity != [(1, raw, fingerprint(storage.binding.model_dump(mode="json")))]:
        raise AuthorityError("store_identity_mismatch")
    records = {}
    for auth_id, run_id, record_id, document, digest in db.execute(
        "SELECT authorisation_id, intended_run_id, record_id, record_json, record_sha256 FROM consumptions ORDER BY authorisation_id"
    ):
        record = _json_model(ConsumptionReceipt, document)
        if (
            digest != fingerprint(record.model_dump(mode="json"))
            or (auth_id, run_id, record_id)
            != (record.authorisation_id, record.intended_run_id, record.record_id)
            or record.store_id != storage.binding.configuration.store_id
            or record.execution_audience
            != storage.binding.configuration.execution_audience
            or record.trust_policy_identity_sha256
            != storage.binding.configuration.trust_policy_identity_sha256
        ):
            raise AuthorityError("store_corrupt")
        records[auth_id] = record
    if "pending_consumption" in storage.issues:
        descriptor = _file(storage.root, _PENDING)
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            marker = _json_model(ConsumptionReceipt, stream.read())
        if marker.store_id != storage.binding.configuration.store_id:
            raise AuthorityError("store_corrupt")
    return records


def _sync(storage: _Storage) -> None:
    os.fsync(storage.database)
    os.fsync(storage.root)


def initialize_store(configuration: TrustedStoreConfiguration) -> AuthorityStoreBinding:
    """Exclusive one-time initialization. Never reuse or clean a partial root."""
    config = _strict(TrustedStoreConfiguration, configuration, "invalid_configuration")
    descriptors = []
    connection = None
    try:
        path = Path(config.store_path)
        parent = _directory(path.parent)
        descriptors.append(parent)
        os.mkdir(path.name, mode=0o700, dir_fd=parent)
        os.fsync(parent)
        root = _directory(path)
        descriptors.append(root)
        _private(os.fstat(root), directory=True)
        database = _create(root, _DATABASE)
        descriptors.append(database)
        lock = _create(root, _LOCK)
        descriptors.append(lock)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        binding = AuthorityStoreBinding(
            schema_id="canary-synthetic-authority-binding-v1",
            configuration=config,
            device=os.fstat(root).st_dev,
            directory_inode=os.fstat(root).st_ino,
            database_inode=os.fstat(database).st_ino,
            lock_inode=os.fstat(lock).st_ino,
        )
        connection = _connect(path / _DATABASE, readonly=False)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("PRAGMA user_version = 1")
        connection.execute("PRAGMA application_id = 1128355379")
        for _, _, _, sql in _DDL:
            connection.execute(sql)
        document = binding.model_dump(mode="json")
        connection.execute(
            "INSERT INTO store_identity VALUES (?, ?, ?)",
            (1, canonical_json(document), fingerprint(document)),
        )
        connection.execute("COMMIT")
        storage = _Storage(binding, root, database, lock, connection)
        storage.check()
        _validate(storage)
        _sync(storage)
        return binding
    except BaseException:  # noqa: BLE001 - interruption is a fixed denial
        raise AuthorityError("store_initialization_failed") from None
    finally:
        if connection is not None:
            with suppress(sqlite3.Error):
                connection.close()
        for descriptor in reversed(descriptors):
            with suppress(OSError):
                os.close(descriptor)


def _begin(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")


def _insert(connection: sqlite3.Connection, record: ConsumptionReceipt) -> None:
    document = record.model_dump(mode="json")
    connection.execute(
        "INSERT INTO consumptions VALUES (?, ?, ?, ?, ?)",
        (
            record.authorisation_id,
            record.intended_run_id,
            record.record_id,
            canonical_json(document),
            fingerprint(document),
        ),
    )


def _commit(connection: sqlite3.Connection) -> None:
    connection.execute("COMMIT")


def _pending(storage: _Storage, record: ConsumptionReceipt) -> None:
    descriptor = os.open(
        _PENDING,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=storage.root,
    )
    with os.fdopen(descriptor, "wb") as stream:
        raw = canonical_json(record.model_dump(mode="json")).encode()
        if stream.write(raw) != len(raw):
            raise OSError
        stream.flush()
        os.fsync(stream.fileno())
    os.fsync(storage.root)


def _clear_pending(storage: _Storage) -> None:
    storage.check(pending=True)
    os.unlink(_PENDING, dir_fd=storage.root)
    os.fsync(storage.root)


def consume_approval(
    payload: bytes,
    signature: bytes,
    *,
    expected: approval.ProposedCanary,
    store: AuthorityStoreBinding,
    policy: Callable[[], PolicyObservation],
    clock: Callable[[], datetime],
) -> ConsumptionReceipt:
    """Verify original signed bytes and persist one synthetic intended run.

    No retries. Pending markers after uncertain outcomes block future writes.
    The pre-COMMIT policy/time check is the cutoff, not COMMIT's return time.
    """
    binding = _strict(AuthorityStoreBinding, store, "invalid_binding")
    try:
        _verify(payload, signature, expected, binding, policy, clock)
        with _open(binding, readonly=False) as storage:
            pending = False
            commit_started = False
            try:
                _begin(storage.connection)
                records = _validate(storage)
                manifest, verified, checked_at = _verify(
                    payload, signature, expected, binding, policy, clock
                )
                proposal_digest = fingerprint(
                    manifest.execution.model_dump(mode="json")
                )
                previous = records.get(verified.authorisation_id)
                if previous is not None:
                    same = (
                        previous.payload_sha256,
                        previous.signature_sha256,
                        previous.trust_policy_sha256,
                        previous.proposal_sha256,
                    ) == (
                        verified.payload_sha256,
                        verified.signature_sha256,
                        verified.trust_policy_sha256,
                        proposal_digest,
                    )
                    raise AuthorityError(
                        "authorisation_consumed" if same else "authorisation_conflict"
                    )
                record = ConsumptionReceipt(
                    schema_id="canary-synthetic-consumption-v1",
                    store_id=binding.configuration.store_id,
                    authorisation_id=verified.authorisation_id,
                    payload_sha256=verified.payload_sha256,
                    signature_sha256=verified.signature_sha256,
                    trust_policy_sha256=verified.trust_policy_sha256,
                    trust_policy_identity_sha256=binding.configuration.trust_policy_identity_sha256,
                    source_receipt_sha256=verified.source_receipt_sha256,
                    proposal_sha256=proposal_digest,
                    execution_audience=verified.execution_audience,
                    intended_run_id="synthetic-run-" + uuid4().hex,
                    record_id="synthetic-consumption-" + uuid4().hex,
                    consumed_at=checked_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    verification_sha256=fingerprint(verified.model_dump(mode="json")),
                    signer_principal=verified.signer_principal,
                    signer_public_key_sha256=verified.signer_public_key_sha256,
                )
                storage.check()
                _pending(storage, record)
                pending = True
                _insert(storage.connection, record)
                storage.check(pending=True, journal=True)
                _boundary(manifest, verified, binding, policy, clock)
                commit_started = True
                _commit(storage.connection)
                _sync(storage)
                storage.check(pending=True)
                _clear_pending(storage)
                return record
            except BaseException as error:
                if commit_started:
                    raise AuthorityError("consumption_outcome_unknown") from None
                try:
                    if storage.connection.in_transaction:
                        storage.connection.execute("ROLLBACK")
                    if pending:
                        _sync(storage)
                        _clear_pending(storage)
                except BaseException:  # noqa: BLE001 - preserve uncertain outcome
                    raise AuthorityError("consumption_outcome_unknown") from None
                if isinstance(error, (AuthorityError, approval.ApprovalError)):
                    raise error from None
                if isinstance(error, sqlite3.Error) and getattr(
                    error, "sqlite_errorcode", 0
                ) & 255 in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
                    raise AuthorityError("store_busy") from None
                raise AuthorityError("consumption_failed_uncommitted") from None
    except (AuthorityError, approval.ApprovalError):
        raise
    except BaseException:  # noqa: BLE001 - interruption is a fixed denial
        raise AuthorityError("verification_interrupted") from None


class _Query(Frozen):
    authorisation_id: approval.AuthorisationID


def inspect_consumption(
    store: AuthorityStoreBinding,
    authorisation_id: str,
    *,
    expected_record: ConsumptionReceipt | None = None,
) -> ConsumptionInspection:
    """Read persisted state only. An absent result never grants retry permission."""
    binding = _strict(AuthorityStoreBinding, store, "invalid_binding")
    query = _strict(
        _Query, {"authorisation_id": authorisation_id}, "invalid_inspection"
    )
    expected = (
        None
        if expected_record is None
        else _strict(ConsumptionReceipt, expected_record, "invalid_inspection")
    )
    try:
        with _open(binding, readonly=True) as storage:
            storage.connection.execute("BEGIN")
            records = _validate(storage)
            record = records.get(query.authorisation_id)
            storage.check(pending=True, journal=True)
            status: Literal["consumed", "absent", "conflict"] = (
                "absent" if record is None else "consumed"
            )
            if record is not None and expected is not None and expected != record:
                status = "conflict"
            return ConsumptionInspection(
                status=status, record=record, issues=storage.issues
            )
    except AuthorityError as error:
        return ConsumptionInspection(
            status="corrupt" if str(error) == "store_corrupt" else "unavailable",
            issues=(str(error),),
        )
