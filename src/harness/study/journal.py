"""Local, immutable, fail-closed capture journal. Never dispatches or resumes."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable
from contextlib import suppress
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal
from uuid import uuid4

from harness.core.execution_control import ExecutionControlError
from harness.core.fingerprints import canonical_json, fingerprint
from harness.core.models import (
    AttemptResult,
    CaseResult,
    RunResult,
    Score,
    TargetResponse,
    TestCase,
    Verdict,
)
from harness.core.prospective import Frozen, strict_json
from harness.core.snapshots import definition_snapshot

POLICY: Final = "salesagent-study-capture-fail-fast-v1"
JOURNAL_VERSION: Final = "salesagent-study-journal-v1"
COMPLETION_VERSION: Final = "salesagent-study-completion-v1"


class JournalError(ExecutionControlError):
    """Evidence is unavailable or ambiguous; never authorizes another request."""


class RegistryBinding(Frozen):
    schema_version: Literal["salesagent-study-registry-v1"] = (
        "salesagent-study-registry-v1"
    )
    path: str
    registry_id: str
    device: int
    inode: int


def _sync(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish(path: Path, payload: Any) -> None:
    """Publish a whole checksum envelope atomically without replacing any name."""
    temporary = path.parent / (".pending-" + uuid4().hex)
    try:
        data = canonical_json(
            {"payload": payload, "sha256": fingerprint(payload)}
        ).encode()
        with temporary.open("xb") as stream:
            os.chmod(temporary, 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path, follow_symlinks=False)
        _sync(path.parent)
    except Exception as exc:
        raise JournalError(f"Journal publication failed: {path.name}") from exc
    finally:
        # Cleanup cannot undo a publication or mask the primary failure.
        with suppress(OSError):
            temporary.unlink()


def _read(path: Path) -> Any:
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("Missing or indirect journal record")
        raw = path.read_bytes()
        envelope = strict_json(raw)
        if raw != canonical_json(envelope).encode():
            raise ValueError("Noncanonical journal bytes")
        if set(envelope) != {"payload", "sha256"} or envelope["sha256"] != fingerprint(
            envelope["payload"]
        ):
            raise ValueError("Checksum mismatch")
        return envelope["payload"]
    except Exception as exc:
        raise JournalError(f"Invalid journal record: {path.name}") from exc


def initialize_registry(path: Path) -> RegistryBinding:
    """Explicit offline initialization, only at a separately approved location."""
    path = path.absolute()
    try:
        path.mkdir(mode=0o700)  # parent must exist; never reuse an existing root
        _sync(path.parent)
        stat = path.stat()
        binding = RegistryBinding(
            path=str(path.resolve()),
            registry_id=uuid4().hex,
            device=stat.st_dev,
            inode=stat.st_ino,
        )
        (path / "captures").mkdir(mode=0o700)
        with (path / "writer.lock").open("xb") as stream:
            stream.flush()
            os.fsync(stream.fileno())
        _sync(path)
        _publish(path / "registry.json", binding.model_dump(mode="json"))
        return binding
    except JournalError:
        raise
    except Exception as exc:
        raise JournalError(
            "Registry initialization failed; do not reuse partial roots"
        ) from exc


def verify_registry(binding: RegistryBinding) -> Path:
    path = Path(binding.path)
    try:
        stat = path.stat()
        if (
            path.is_symlink()
            or str(path.resolve()) != binding.path
            or (stat.st_dev, stat.st_ino) != (binding.device, binding.inode)
        ):
            raise JournalError(
                "Registry location/identity differs; backups are not authorities"
            )
        if _read(path / "registry.json") != binding.model_dump(mode="json"):
            raise JournalError("Registry binding differs")
        if (path / "captures").is_symlink() or not (path / "captures").is_dir():
            raise JournalError("Registry capture directory differs")
        return path
    except OSError as exc:
        raise JournalError("Authoritative registry unavailable") from exc


def _acquire_writer(registry: RegistryBinding) -> int:
    try:
        import fcntl
    except ImportError as exc:
        raise JournalError("C2 journals require POSIX advisory locking") from exc
    root = verify_registry(registry)
    descriptor = None
    try:
        descriptor = os.open(root / "writer.lock", os.O_RDWR | os.O_NOFOLLOW)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return descriptor
    except OSError as exc:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
        raise JournalError("Authoritative registry writer busy or unavailable") from exc


def load_registry(path: Path) -> RegistryBinding:
    binding = RegistryBinding.model_validate(_read(path / "registry.json"))
    if Path(binding.path) != path.resolve():
        raise JournalError("Registry locator differs from its binding")
    verify_registry(binding)
    return binding


def capture_identity(contract_hash: str, suite_id: str) -> str:
    return fingerprint([JOURNAL_VERSION, contract_hash, suite_id])


class StudyJournal:
    """Single-use writer. Construction exclusively claims the capture identity."""

    def __init__(
        self,
        registry: RegistryBinding,
        contract_hash: str,
        suite_id: str,
        context: dict[str, Any],
        pack_name: str,
    ) -> None:
        self.registry = registry
        self.identity = capture_identity(contract_hash, suite_id)
        self.path = verify_registry(registry) / "captures" / self.identity
        self.claim = {
            "journal_version": JOURNAL_VERSION,
            "policy": POLICY,
            "capture_id": self.identity,
            "registry": registry.model_dump(mode="json"),
            "contract_hash": contract_hash,
            "suite_id": suite_id,
        }
        self.context = deepcopy(context)
        self.pack_name = pack_name
        self.current: tuple[str, int] | None = None
        self.roster: list[list[Any]] = []
        self.completed: list[list[Any]] = []
        self.stopped = False
        self.ready = False
        self.records: dict[Path, str] = {}
        self._writer: int | None = _acquire_writer(registry)
        try:
            self.path.mkdir(mode=0o700)
            _sync(self.path.parent)
            self._write(self.path / "claim.json", self.claim)
            (self.path / "attempts").mkdir(mode=0o700)
            _sync(self.path)
            self._directories = {
                directory: (info.st_dev, info.st_ino)
                for directory in (self.path, self.path / "attempts")
                for info in (directory.lstat(),)
            }
        except BaseException as exc:
            self.close()
            if isinstance(exc, Exception) and not isinstance(exc, JournalError):
                raise JournalError(
                    "Capture identity already reserved or unavailable; inspect only"
                ) from exc
            raise

    def close(self) -> None:
        descriptor, self._writer = self._writer, None
        if descriptor is not None:
            # Releasing a local lock never changes any committed evidence.
            with suppress(OSError):
                os.close(descriptor)

    def _write(self, path: Path, payload: Any) -> None:
        if self._writer is None:
            raise JournalError("Journal writer is closed")
        try:
            _publish(path, payload)
            self.records[path] = fingerprint(payload)
        except BaseException:
            self.stopped = True
            raise

    def _verify_directories(self) -> None:
        try:
            for directory, identity in self._directories.items():
                info = directory.lstat()
                if (
                    not stat.S_ISDIR(info.st_mode)
                    or (info.st_dev, info.st_ino) != identity
                ):
                    raise JournalError(
                        "Capture/attempt directory identity differs; dispatch blocked"
                    )
        except OSError as exc:
            raise JournalError(
                "Capture/attempt directory unavailable; dispatch blocked"
            ) from exc

    def prepared(self, run: RunResult, cases: list[TestCase]) -> None:
        self._verify_directories()
        run.pack_name = self.pack_name
        run.config_snapshot["study"] = deepcopy(self.context)
        run.config_snapshot["capture_identity"] = self.identity
        count = run.config_snapshot["attempts"]
        self.roster = [[case.id, index] for case in cases for index in range(count)]
        self._write(
            self.path / "preparation.json",
            {
                "run": run.model_dump(mode="json"),
                "roster": self.roster,
                "cases": [
                    CaseResult(
                        case_id=case.id,
                        tags=list(case.tags),
                        definition=definition_snapshot(
                            case,
                            run.config_snapshot.get("metadata_snapshot_policy", {}).get(
                                "case_extra_keys", []
                            ),
                        ),
                    ).model_dump(mode="json")
                    for case in cases
                ],
            },
        )

        self.ready = True

    def _attempt_path(self, case_id: str, index: int) -> Path:
        return self.path / "attempts" / fingerprint([case_id, index])

    def reserve(self, case_id: str, index: int) -> None:
        verify_registry(self.registry)
        self._verify_directories()
        for record, digest in self.records.items():
            if fingerprint(_read(record)) != digest:
                raise JournalError(
                    "Previously committed evidence differs; dispatch blocked"
                )
        if (
            self._writer is None
            or not self.ready
            or self.stopped
            or self.current is not None
            or len(self.completed) >= len(self.roster)
            or self.roster[len(self.completed)] != [case_id, index]
        ):
            raise JournalError("Unexpected attempt reservation")
        path = self._attempt_path(case_id, index)
        try:
            path.mkdir(mode=0o700)
            _sync(path.parent)
            self._write(
                path / "reservation.json",
                {"capture_id": self.identity, "case_id": case_id, "index": index},
            )
        except JournalError:
            raise
        except Exception as exc:
            raise JournalError(
                "Attempt reservation ambiguous or already exists"
            ) from exc
        self.current = (case_id, index)

    def _active(self, case_id: str, index: int) -> Path:
        if self.current != (case_id, index):
            raise JournalError("Evidence has no active reservation")
        return self._attempt_path(case_id, index)

    def record_http(
        self, turn_index: int, phase: str, evidence: dict[str, Any]
    ) -> None:
        if self.current is None or phase not in {"chat", "turn"}:
            raise JournalError("HTTP evidence has no active reservation")
        path = self._active(*self.current)
        self._write(
            path / f"http-{turn_index:04d}-{phase}.json",
            {"turn_index": turn_index, "phase": phase, "evidence": evidence},
        )

    def response_received(
        self, case_id: str, index: int, response: TargetResponse
    ) -> None:
        if response.raw:
            raise JournalError("Raw provider payload is forbidden in Study journals")
        self._write(
            self._active(case_id, index) / "response.json",
            response.model_dump(mode="json"),
        )

    def scorer_recorded(
        self,
        case_id: str,
        index: int,
        name: str,
        score: Score | None,
        error: str | None,
    ) -> None:
        # Error strings come from existing sanitized target/scorer contracts.
        self._write(
            self._active(case_id, index) / ("scorer-" + fingerprint(name) + ".json"),
            {
                "name": name,
                "score": score.model_dump(mode="json") if score else None,
                "error": error,
            },
        )

    def attempt_completed(self, case_id: str, attempt: AttemptResult) -> bool:
        self._write(
            self._active(case_id, attempt.index) / "outcome.json",
            attempt.model_dump(mode="json"),
        )
        self.completed.append([case_id, attempt.index])
        self.current = None
        self.stopped = attempt.verdict is Verdict.ERROR
        return not self.stopped

    def run_assembled(self, run: RunResult) -> None:
        self._write(self.path / "run.json", run.model_dump(mode="json"))
        if self.completed == self.roster and not self.stopped:
            receipt = _completion(self.path, self.claim)
            self._write(self.path / "completion.json", receipt)
            run.config_snapshot["capture_completion"] = receipt


def _completion(
    path: Path, claim: dict[str, Any], run_data: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Recompute completion exclusively from durable, mutually bound evidence."""
    if _read(path / "claim.json") != claim:
        raise JournalError("Capture claim differs")
    if (path / "attempts").is_symlink():
        raise JournalError("Indirect attempt directory")
    preparation = _read(path / "preparation.json")
    run_data = _read(path / "run.json") if run_data is None else run_data
    run = RunResult.model_validate(run_data)
    if (
        run.config_snapshot.get("capture_identity") != claim["capture_id"]
        or run.config_snapshot.get("study", {}).get("execution_contract_hash")
        != claim["contract_hash"]
        or run.config_snapshot.get("study", {}).get("suite_id") != claim["suite_id"]
    ):
        raise JournalError("Run capture identity/provenance differs")
    template = preparation["run"]
    expected_run = run.model_copy(deep=True)
    expected_run.cases = []
    expected_run.finished_at = None
    if expected_run.model_dump(mode="json") != template or run.finished_at is None:
        raise JournalError("Assembled run differs from validated preparation")
    case_templates = []
    for case in run.cases:
        template_case = case.model_copy(deep=True)
        template_case.attempts = []
        case_templates.append(template_case.model_dump(mode="json"))
    if case_templates != preparation["cases"]:
        raise JournalError("Assembled case definitions differ from preparation")
    roster = [[case.case_id, a.index] for case in run.cases for a in case.attempts]
    expected_roster = [
        [case_id, i]
        for case_id in run.config_snapshot["selection"]["case_ids"]
        for i in range(run.config_snapshot["attempts"])
    ]
    if roster != preparation["roster"] or roster != expected_roster or not roster:
        raise JournalError("Incomplete attempt roster")
    entries = []
    scorer_names = [s["name"] for s in run.config_snapshot["scorers"]]
    inputs = {
        c["id"]: c["input"]["turns"] for c in run.config_snapshot["resolved_cases"]
    }
    for case in run.cases:
        for attempt in case.attempts:
            directory = path / "attempts" / fingerprint([case.case_id, attempt.index])
            reservation = {
                "capture_id": claim["capture_id"],
                "case_id": case.case_id,
                "index": attempt.index,
            }
            if (
                directory.is_symlink()
                or _read(directory / "reservation.json") != reservation
            ):
                raise JournalError("Reservation identity differs")
            if (
                attempt.verdict not in {Verdict.PASS, Verdict.FAIL}
                or attempt.error
                or attempt.response is None
            ):
                raise JournalError(
                    "Attempt is not acceptable under C2 completion policy"
                )
            if _read(directory / "outcome.json") != attempt.model_dump(
                mode="json"
            ) or _read(directory / "response.json") != attempt.response.model_dump(
                mode="json"
            ):
                raise JournalError("Attempt/response checkpoint differs")
            if [s.name for s in attempt.scores] != scorer_names:
                raise JournalError("Incomplete scorer outcomes")
            if attempt.verdict != (
                Verdict.PASS
                if all(s.passed for s in attempt.scores if s.passed is not None)
                else Verdict.FAIL
            ) or not any(s.passed is not None for s in attempt.scores):
                raise JournalError("Attempt verdict differs from gated scores")
            for score in attempt.scores:
                if _read(
                    directory / ("scorer-" + fingerprint(score.name) + ".json")
                ) != {
                    "name": score.name,
                    "score": score.model_dump(mode="json"),
                    "error": None,
                }:
                    raise JournalError("Scorer outcome differs")
            turns = attempt.response.structured.get("turns")
            if (
                not isinstance(turns, list)
                or not turns
                or len(turns) != len(inputs[case.case_id])
            ):
                raise JournalError("Missing public HTTP evidence")
            for i, turn in enumerate(turns):
                if turn["index"] != i or turn["input"] != inputs[case.case_id][i]:
                    raise JournalError("Turn/input trajectory differs")
                chat = _read(directory / f"http-{i:04d}-chat.json")
                recorded_turn = _read(directory / f"http-{i:04d}-turn.json")
                if (
                    chat["turn_index"] != i
                    or chat["phase"] != "chat"
                    or chat["evidence"]["message"] != turn["output"]
                    or chat["evidence"]["trace_id"] != turn["metadata"]["trace_id"]
                    or recorded_turn
                    != {"turn_index": i, "phase": "turn", "evidence": turn}
                ):
                    raise JournalError("Public HTTP checkpoint differs")
            # Bind every published record, including its checksum, into the receipt.
            records = {
                p.name: fingerprint(_read(p)) for p in sorted(directory.glob("*.json"))
            }
            expected_names = {"reservation.json", "response.json", "outcome.json"}
            expected_names.update(
                "scorer-" + fingerprint(name) + ".json" for name in scorer_names
            )
            expected_names.update(
                f"http-{i:04d}-{phase}.json"
                for i in range(len(turns))
                for phase in ("chat", "turn")
            )
            if set(records) != expected_names:
                raise JournalError("Unexpected or conflicting attempt records")
            entries.append(
                {"case_id": case.case_id, "index": attempt.index, "records": records}
            )
    if {p.name for p in (path / "attempts").iterdir()} != {
        fingerprint(item) for item in roster
    }:
        raise JournalError("Unexpected or conflicting attempt identities")
    return {
        "schema_version": COMPLETION_VERSION,
        "journal_version": JOURNAL_VERSION,
        "policy": POLICY,
        "capture_id": claim["capture_id"],
        "contract_hash": claim["contract_hash"],
        "suite_id": claim["suite_id"],
        "registry": claim["registry"],
        "run_hash": fingerprint(run_data),
        "preparation_hash": fingerprint(preparation),
        "attempts": entries,
    }


def verify_completion(
    registry: RegistryBinding,
    contract_hash: str,
    suite_id: str,
    source: RunResult | None = None,
) -> RunResult:
    root = verify_registry(registry)
    identity = capture_identity(contract_hash, suite_id)
    path = root / "captures" / identity
    if path.is_symlink():
        raise JournalError("Indirect capture directory")
    claim = {
        "journal_version": JOURNAL_VERSION,
        "policy": POLICY,
        "capture_id": identity,
        "registry": registry.model_dump(mode="json"),
        "contract_hash": contract_hash,
        "suite_id": suite_id,
    }
    receipt = _read(path / "completion.json")
    if receipt != _completion(path, claim):
        raise JournalError("Completion receipt differs")
    restored = RunResult.model_validate(_read(path / "run.json"))
    restored.config_snapshot["capture_completion"] = receipt
    if source is not None and source.model_dump(mode="json") != restored.model_dump(
        mode="json"
    ):
        raise JournalError("Source differs from completed journal")
    return restored


def inspect_capture(
    registry: RegistryBinding, contract_hash: str, suite_id: str
) -> dict[str, Any]:
    """Read-only inventory; corrupt or missing records never imply dispatch permission."""
    path = (
        verify_registry(registry)
        / "captures"
        / capture_identity(contract_hash, suite_id)
    )
    if path.is_symlink() or (path / "attempts").is_symlink():
        raise JournalError("Indirect capture/attempt directory")
    records: dict[str, Any] = {}
    for record in sorted(path.rglob("*.json")):
        try:
            records[str(record.relative_to(path))] = _read(record)
        except JournalError:
            records[str(record.relative_to(path))] = {"invalid": True}
    return {
        "capture_id": path.name,
        "exists": path.is_dir(),
        "dispatch_authorized": False,
        "records": records,
    }


def recover_save_only(
    registry: RegistryBinding,
    contract_hash: str,
    suite_id: str,
    save: Callable[[RunResult], None],
) -> RunResult:
    """Save a verified completed run. No target/judge/factory/resume API exists."""
    descriptor = _acquire_writer(registry)
    try:
        return _recover_save_only(registry, contract_hash, suite_id, save)
    finally:
        with suppress(OSError):
            os.close(descriptor)


def _recover_save_only(
    registry: RegistryBinding,
    contract_hash: str,
    suite_id: str,
    save: Callable[[RunResult], None],
) -> RunResult:
    root = verify_registry(registry)
    path = root / "captures" / capture_identity(contract_hash, suite_id)
    if path.is_symlink():
        raise JournalError("Indirect capture directory")
    assembled = None
    receipt = None
    if not (path / "completion.json").exists():
        claim = {
            "journal_version": JOURNAL_VERSION,
            "policy": POLICY,
            "capture_id": path.name,
            "registry": registry.model_dump(mode="json"),
            "contract_hash": contract_hash,
            "suite_id": suite_id,
        }
        if not (path / "run.json").exists():
            # Reassemble only committed complete outcomes. No scoring, response
            # generation, attempt completion or target calls are available here.
            preparation = _read(path / "preparation.json")
            assembled = RunResult.model_validate(preparation["run"])
            for case_data in preparation["cases"]:
                case = CaseResult.model_validate(case_data)
                for index in range(assembled.config_snapshot["attempts"]):
                    record = (
                        path
                        / "attempts"
                        / fingerprint([case.case_id, index])
                        / "outcome.json"
                    )
                    if record.parent.is_symlink() or record.parent.parent.is_symlink():
                        raise JournalError("Indirect attempt directory")
                    case.attempts.append(AttemptResult.model_validate(_read(record)))
                assembled.cases.append(case)
            assembled.finished_at = datetime.now(UTC)
        receipt = _completion(
            path,
            claim,
            assembled.model_dump(mode="json") if assembled is not None else None,
        )
    # Scan existing evidence once, including a visible receipt left by a
    # failed directory fsync. Missing artifacts are published durably afterward.
    for record in path.rglob("*.json"):
        _read(record)
        with record.open("rb") as stream:
            os.fsync(stream.fileno())
    for directory in sorted((p for p in path.rglob("*") if p.is_dir()), reverse=True):
        _sync(directory)
    _sync(path)
    if receipt is not None:
        if assembled is not None:
            _publish(path / "run.json", assembled.model_dump(mode="json"))
        _publish(path / "completion.json", receipt)
    restored = verify_completion(registry, contract_hash, suite_id)
    save(restored.model_copy(deep=True))
    return restored
