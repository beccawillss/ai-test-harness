"""Canary-specific offline journal. No dispatch, restart or authority API.

POSIX local-filesystem durability and cooperative locking are required. Checksums
establish local integrity, not external event authenticity or rollback resistance.
Recovery exports only; it never writes to the authoritative registry.
"""

from __future__ import annotations

import fcntl
import os
import re
import stat
import threading
from contextlib import suppress
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Self
from uuid import uuid4

from harness.canary.evidence_v3 import (
    EvidenceProjectionError,
    project_chat,
    project_trace,
    provider_observation,
    restore_trace,
    validate_observation,
)
from harness.canary.execution_policy import (
    Decision,
    ExecutionState,
    OperationalGuards,
    TurnOutcome,
    decide,
    record_outcome,
)
from harness.canary.runtime_v3 import (
    V3,
    Frozen,
    parse_receipt,
    validate_binding,
)
from harness.canary.selection_acceptance import assess_selection
from harness.canary.selection_v3 import LIMITS, ORDER
from harness.core.fingerprints import canonical_json, fingerprint
from harness.core.prospective import strict_json

SCHEMA = "nonstudy-canary-journal-v3-v1"


class JournalError(RuntimeError):
    """Only fixed diagnostics. External exceptions and payloads are suppressed."""


class RegistryBinding(Frozen):
    schema_id: str = SCHEMA
    path: str
    registry_id: str
    device: int
    inode: int
    runs_inode: int
    approvals_inode: int
    lock_inode: int


def _identifier(value: str) -> str:
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value)
        or value in {".", ".."}
    ):
        raise JournalError("invalid_identity")
    return value


def _private(info: os.stat_result, *, directory: bool = False) -> None:
    if (
        info.st_uid != os.getuid()
        or info.st_mode & 0o077
        or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
    ):
        raise JournalError("unsafe_storage")


def _open_directory(path: Path) -> int:
    """Walk from / through directory descriptors; never follow a symlink."""
    path = path.absolute()
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            if part in {".", ".."}:
                raise JournalError("indirect_storage")
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:  # noqa: BLE001 - interruptions must close recording gates
        os.close(descriptor)
        raise JournalError("storage_unavailable") from None


def _outside(path: Path) -> None:
    if any(
        (parent / ".git").exists()
        or parent.name in {"salesagent-study-v1", "salesagent-preflight-canary"}
        for parent in (path, *path.parents)
    ):
        raise JournalError("separate_private_namespace_required")


def _mkdir(parent: int, name: str) -> int:
    os.mkdir(name, mode=0o700, dir_fd=parent)
    os.fsync(parent)
    return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)


def _publish(directory: int, name: str, value: Any) -> None:
    """An existing final name is never success, even for byte-identical data."""
    temporary = ".pending-" + uuid4().hex
    try:
        data = canonical_json({"payload": value, "sha256": fingerprint(value)}).encode()
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        with os.fdopen(descriptor, "wb") as stream:
            if stream.write(data) != len(data):
                raise OSError
            stream.flush()
            os.fsync(stream.fileno())
        os.link(
            temporary,
            name,
            src_dir_fd=directory,
            dst_dir_fd=directory,
            follow_symlinks=False,
        )
        os.fsync(directory)
    except BaseException:  # noqa: BLE001 - interruptions must close recording gates
        raise JournalError("publication_failed_or_ambiguous") from None
    finally:
        # Cleanup cannot undo publication, mask an error or authorise a retry.
        with suppress(OSError):
            os.unlink(temporary, dir_fd=directory)


def _read(directory: int, name: str) -> Any:
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        with os.fdopen(descriptor, "rb") as stream:
            _private(os.fstat(stream.fileno()))
            raw = stream.read()
        envelope = strict_json(raw)
        if (
            raw != canonical_json(envelope).encode()
            or set(envelope) != {"payload", "sha256"}
            or envelope["sha256"] != fingerprint(envelope["payload"])
        ):
            raise ValueError
        return envelope["payload"]
    except Exception:  # noqa: BLE001 - fixed diagnostics at the storage/privacy boundary
        raise JournalError("invalid_record") from None


def initialize_registry(path: Path) -> RegistryBinding:
    """Explicit private offline initialization. Partial roots are never reused."""
    path = path.absolute()
    _outside(path)
    descriptors = []
    try:
        parent = _open_directory(path.parent)
        descriptors.append(parent)
        root = _mkdir(parent, path.name)
        descriptors.append(root)
        runs = _mkdir(root, "runs")
        descriptors.append(runs)
        approvals = _mkdir(root, "approvals")
        descriptors.append(approvals)
        lock = os.open(
            "writer.lock",
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=root,
        )
        descriptors.append(lock)
        os.fsync(lock)
        os.fsync(root)
        identity = os.fstat(root)
        binding = RegistryBinding(
            path=str(path),
            registry_id=uuid4().hex,
            device=identity.st_dev,
            inode=identity.st_ino,
            runs_inode=os.fstat(runs).st_ino,
            approvals_inode=os.fstat(approvals).st_ino,
            lock_inode=os.fstat(lock).st_ino,
        )
        _publish(root, "registry.json", binding.model_dump(mode="json"))
        return binding
    except Exception:  # noqa: BLE001 - fixed diagnostics at the storage/privacy boundary
        raise JournalError("registry_initialization_failed") from None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _registry(binding: RegistryBinding) -> int:
    _outside(Path(binding.path))
    root = _open_directory(Path(binding.path))
    try:
        _private(os.fstat(root), directory=True)
        if (
            binding.schema_id != SCHEMA
            or (os.fstat(root).st_dev, os.fstat(root).st_ino)
            != (binding.device, binding.inode)
            or _read(root, "registry.json") != binding.model_dump(mode="json")
        ):
            raise JournalError("registry_identity_differs")
        for name, inode in (
            ("runs", binding.runs_inode),
            ("approvals", binding.approvals_inode),
            ("writer.lock", binding.lock_inode),
        ):
            info = os.stat(name, dir_fd=root, follow_symlinks=False)
            _private(info, directory=name != "writer.lock")
            if (info.st_dev, info.st_ino) != (binding.device, inode):
                raise JournalError("registry_identity_differs")
        return root
    except Exception:  # noqa: BLE001 - fixed diagnostics at the storage/privacy boundary
        os.close(root)
        raise JournalError("registry_unavailable_or_substituted") from None


def load_registry(path: Path) -> RegistryBinding:
    descriptor = _open_directory(path)
    try:
        binding = RegistryBinding.model_validate(_read(descriptor, "registry.json"))
        if binding.path != str(path.absolute()):
            raise ValueError
        verified = _registry(binding)
        os.close(verified)
        return binding
    except Exception:  # noqa: BLE001 - fixed diagnostics at the storage/privacy boundary
        raise JournalError("invalid_registry_binding") from None
    finally:
        os.close(descriptor)


def _lock(binding: RegistryBinding, *, exclusive: bool) -> int:
    root = _registry(binding)
    descriptor = None
    try:
        descriptor = os.open("writer.lock", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root)
        if os.fstat(descriptor).st_ino != binding.lock_inode:
            raise ValueError
        fcntl.flock(
            descriptor, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB
        )
        return descriptor
    except Exception:  # noqa: BLE001 - fixed diagnostics at the storage/privacy boundary
        if descriptor is not None:
            os.close(descriptor)
        raise JournalError("registry_writer_busy_or_unavailable") from None
    finally:
        os.close(root)


def _json(value: Any) -> Any:
    """Dataclasses contain Decimal; the on-disk guard snapshot uses decimal text."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json(item) for item in value]
    return value


@dataclass
class _Run:
    manifest: dict[str, Any] | None = None
    state: ExecutionState = field(default_factory=ExecutionState)
    decision: Decision | None = None
    decision_sequence: int | None = None
    active: str | None = None
    scheduled: Decision | None = None
    calls: dict[tuple[str, int], dict[str, Any]] = field(default_factory=dict)
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    assessments: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    shutdown: dict[str, bool] | None = None
    completion_sequence: int | None = None
    sealed: bool = False

    def bundle_digest(self) -> str:
        return fingerprint({"evidence": self.evidence, "assessments": self.assessments})

    def accounting(self, slot: str | None = None) -> dict[str, Any]:
        calls = [c for (s, _), c in self.calls.items() if slot is None or s == slot]
        results = [r for c in calls for r in c["results"].values()]
        dispatched = sum(len(c["dispatches"]) for c in calls)
        unknown = (
            dispatched - len(results) + sum(r["estimated_usd"] is None for r in results)
        )
        subtotal = sum(
            (
                Decimal(r["estimated_usd"])
                for r in results
                if r["estimated_usd"] is not None
            ),
            Decimal(0),
        )
        return {
            "logical_calls": len(calls),
            "provider_attempts": dispatched,
            "unknown_attempts": unknown,
            "incomplete_calls": sum(not c["complete"] for c in calls),
            "retryable_http_failures": sum(
                r["outcome"] == "retryable_http_failure" for r in results
            ),
            "operational_errors": sum(
                r["outcome"] in {"operational_error", "ambiguous_transport"}
                for r in results
            )
            + sum(
                c["complete"]
                and c["results"][c["dispatches"][-1]]["outcome"]
                == "retryable_http_failure"
                for c in calls
                if c["dispatches"] and len(c["results"]) == len(c["dispatches"])
            ),
            "estimated_subtotal_usd": str(subtotal),
            "estimated_total_usd": str(subtotal) if unknown == 0 else None,
            "billing_verified": False,
        }

    def previous(self, slot: str) -> dict[str, Any]:
        return {
            prior: {"chat": e["chat"], "trace": restore_trace(e["trace"])}
            for prior in ORDER[: ORDER.index(slot)]
            if (e := self.evidence.get(prior)) and "trace" in e
        }

    def assessment(self, slot: str) -> dict[str, Any]:
        e = self.evidence.get(slot, {})
        report = assess_selection(
            slot,
            e.get("chat", {}),
            restore_trace(e["trace"]) if "trace" in e else {},
            previous=self.previous(slot),
        )
        return _json(asdict(report))


def _guards(payload: dict[str, Any]) -> OperationalGuards:
    defaults = asdict(OperationalGuards())
    if set(payload) != set(defaults):
        raise JournalError("invalid_guards")
    for name, default in defaults.items():
        value = payload[name]
        if type(default) is bool and type(value) is not bool:
            raise JournalError("invalid_guards")
        if type(default) is int and (type(value) is not int or value < 0):
            raise JournalError("invalid_guards")
    cost = payload["estimated_total_usd"]
    if not isinstance(cost, str):
        raise JournalError("invalid_guards")
    return OperationalGuards(**{**payload, "estimated_total_usd": Decimal(cost)})


def _effective(run: _Run, supplied: OperationalGuards) -> OperationalGuards:
    a = run.accounting()
    ready = (
        not a["unknown_attempts"]
        and not a["incomplete_calls"]
        and not a["operational_errors"]
    )
    observed_cost = Decimal(a["estimated_subtotal_usd"])
    cost = supplied.estimated_total_usd
    # Supplied additional liability may tighten the guard, never reduce it.
    cost = max(cost, observed_cost) if cost.is_finite() and cost >= 0 else cost
    return replace(
        supplied,
        provider_completed=supplied.provider_completed and ready,
        recording_complete=supplied.recording_complete and run.active is None,
        accounting_complete=supplied.accounting_complete
        and _reconciled(run)
        and supplied.unknown_attempts == 0,
        logical_calls=a["logical_calls"],
        provider_attempts=a["provider_attempts"],
        unknown_attempts=max(supplied.unknown_attempts, a["unknown_attempts"]),
        estimated_total_usd=cost,
    )


def _reconciled(run: _Run) -> bool:
    a = run.accounting()
    return bool(
        run.active is None
        and not a["unknown_attempts"]
        and not a["incomplete_calls"]
        and not a["operational_errors"]
        and a["logical_calls"] == sum(o.logical_calls for o in run.state.outcomes)
        and a["provider_attempts"]
        == sum(o.provider_attempts for o in run.state.outcomes)
    )


def _apply(run: _Run, kind: str, p: dict[str, Any], sequence: int) -> None:
    """Validate this fixed canary record sequence, including persisted policy results."""
    expected: dict[str, Any]
    if (
        run.sealed
        or (run.completion_sequence is not None and kind != "completion_ack")
        or (run.manifest is None and kind != "manifest")
    ):
        raise JournalError("invalid_transition")
    if kind == "manifest":
        receipt = parse_receipt(canonical_json(p["source_receipt"]))
        validate_binding(receipt.binding)
        if run.manifest is not None or receipt.binding.identifier != V3:
            raise JournalError("invalid_manifest")
        expected = {
            "schema_id": SCHEMA,
            "run_id": _identifier(p["run_id"]),
            "approval_id": _identifier(p["approval_id"]),
            "registry": RegistryBinding.model_validate(p["registry"]).model_dump(
                mode="json"
            ),
            "source_receipt": receipt.model_dump(mode="json"),
            "source_receipt_sha256": fingerprint(receipt.model_dump(mode="json")),
            "source_authorised": False,
            "authorises_live_execution": False,
            "provider_evidence_authenticated": False,
        }
        run.manifest = expected
    elif kind == "decision":
        if run.active is not None or run.shutdown is not None:
            raise JournalError("decision_before_outcome_or_after_shutdown")
        supplied = _guards(p["supplied_guards"])
        effective = _effective(run, supplied)
        decision = decide(run.state, effective)
        expected = {
            "supplied_guards": _json(asdict(supplied)),
            "effective_guards": _json(asdict(effective)),
            "accounting": run.accounting(),
            "decision": _json(asdict(decision)),
        }
        run.decision, run.state = decision, decision.state
        run.decision_sequence = sequence
    elif kind == "turn_reserved":
        slot = p["slot"]
        if (
            run.active is not None
            or run.shutdown is not None
            or run.state.stopped
            or run.decision is None
            or run.decision.action != "ADVANCE"
            or slot != run.decision.next_slot
            or slot in run.evidence
        ):
            raise JournalError("invalid_turn_reservation")
        expected = {"slot": slot, "decision_sequence": run.decision_sequence}
        run.active, run.scheduled = slot, run.decision
        run.evidence[slot] = {}
    elif kind in {
        "call_reserved",
        "provider_dispatch",
        "provider_result",
        "call_completed",
    }:
        slot, number = p["slot"], p["logical_call"]
        if slot != run.active or run.shutdown is not None or run.state.stopped:
            raise JournalError("no_active_turn")
        if run.evidence[slot]:
            raise JournalError("provider_work_after_public_evidence")
        if kind in {"call_reserved", "provider_dispatch"} and Decimal(
            run.accounting()["estimated_subtotal_usd"]
        ) >= Decimal(LIMITS.estimated_pause_usd):
            raise JournalError("known_spending_pause")
        if type(number) is not int or not 1 <= number <= LIMITS.logical_calls_per_turn:
            raise JournalError("invalid_logical_call")
        key = (slot, number)
        if kind == "call_reserved":
            a = run.accounting()
            if (
                key in run.calls
                or number != 1 + sum(s == slot for s, _ in run.calls)
                or (
                    a["incomplete_calls"]
                    or a["unknown_attempts"]
                    or a["operational_errors"]
                )
                or run.evidence[slot]
            ):
                raise JournalError("invalid_call_reservation")
            expected = {"slot": slot, "logical_call": number}
            run.calls[key] = {"dispatches": [], "results": {}, "complete": False}
        else:
            call = run.calls[key]
            if call["complete"]:
                raise JournalError("logical_call_already_completed")
            if kind == "call_completed":
                if not call["dispatches"] or len(call["results"]) != len(
                    call["dispatches"]
                ):
                    raise JournalError("unresolved_provider_attempt")
                expected = {"slot": slot, "logical_call": number}
                call["complete"] = True
            else:
                attempt = p["attempt"]
                if (
                    type(attempt) is not int
                    or not 1 <= attempt <= LIMITS.attempts_per_call
                ):
                    raise JournalError("invalid_attempt_identity")
                expected = {"slot": slot, "logical_call": number, "attempt": attempt}
                if kind == "provider_dispatch":
                    # Billing may be unknown for an observed retryable HTTP
                    # failure in this call. It cannot make an ambiguous attempt,
                    # terminal result or successful result eligible for a retry.
                    if attempt != len(call["dispatches"]) + 1 or (
                        attempt > 1
                        and (
                            len(call["results"]) != len(call["dispatches"])
                            or call["results"][attempt - 1]["outcome"]
                            != "retryable_http_failure"
                        )
                    ):
                        raise JournalError("duplicate_or_unresolved_attempt")
                    call["dispatches"].append(attempt)
                else:
                    if attempt not in call["dispatches"] or attempt in call["results"]:
                        raise JournalError("orphan_or_duplicate_result")
                    validate_observation(p["observation"])
                    expected["observation"] = p["observation"]
                    call["results"][attempt] = p["observation"]
    elif kind in {"chat", "trace", "evidence_error", "assessment", "outcome"}:
        slot = p["slot"]
        if slot != run.active or run.state.stopped or run.shutdown is not None:
            raise JournalError("no_active_turn")
        evidence = run.evidence[slot]
        if kind == "chat":
            if "chat" in evidence or "error" in evidence:
                raise JournalError("duplicate_chat")
            expected = {"slot": slot, "chat": project_chat(p["chat"])}
            evidence["chat"] = expected["chat"]
        elif kind == "trace":
            if "chat" not in evidence or "trace" in evidence or "error" in evidence:
                raise JournalError("invalid_trace_checkpoint")
            restored = restore_trace(p["trace"])
            safe = project_trace(restored)
            expected = {"slot": slot, "trace": safe, "reread_sha256": fingerprint(safe)}
            evidence["trace"] = safe
        elif kind == "evidence_error":
            if "error" in evidence or "trace" in evidence:
                raise JournalError("duplicate_evidence_error")
            if p["code"] not in {
                "invalid_public_chat",
                "invalid_public_trace",
                "trace_reread_differs",
            }:
                raise JournalError("unknown_error_category")
            expected = {"slot": slot, "code": p["code"]}
            evidence["error"] = p["code"]
        elif kind == "assessment":
            reports = run.assessments.setdefault(slot, [])
            expected = {
                "slot": slot,
                "revision": len(reports),
                "evidence_sha256": fingerprint(evidence),
                "report": run.assessment(slot),
            }
            reports.append(expected)
        else:
            if not run.assessments.get(slot) or run.scheduled is None:
                raise JournalError("missing_assessment_or_schedule")
            if run.assessments[slot][-1]["evidence_sha256"] != fingerprint(evidence):
                raise JournalError("assessment_evidence_changed")
            report = assess_selection(
                slot,
                evidence.get("chat", {}),
                restore_trace(evidence["trace"]) if "trace" in evidence else {},
                previous=run.previous(slot),
            )
            a = run.accounting(slot)
            complete = bool(
                "chat" in evidence
                and "trace" in evidence
                and not a["incomplete_calls"]
                and not a["unknown_attempts"]
                and not a["operational_errors"]
            )
            outcome = TurnOutcome(
                slot,
                report.checks,
                a["logical_calls"],
                a["provider_attempts"],
                complete,
                complete and report.prerequisites.status == "PASS",
            )
            expected = {
                "slot": slot,
                "assessment_revision": len(run.assessments[slot]) - 1,
                "outcome": _json(asdict(outcome)),
            }
            run.state = record_outcome(run.scheduled, outcome)
            run.active = None
    elif kind == "stop":
        if p["code"] not in {"operator_stop", "interrupted", "operational_error"}:
            raise JournalError("invalid_stop_code")
        expected = {"code": p["code"]}
        run.state = replace(
            run.state, stopped=True, stop_reasons=(*run.state.stop_reasons, p["code"])
        )
    elif kind == "shutdown":
        if run.shutdown is not None or not (
            run.state.stopped or (run.decision and run.decision.action == "COMPLETE")
        ):
            raise JournalError("invalid_shutdown_boundary")
        expected = {
            name: p[name]
            for name in ("worker_stopped", "sdk_closed", "no_inflight_provider")
        }
        if any(type(value) is not bool for value in expected.values()):
            raise JournalError("invalid_shutdown_observation")
        run.shutdown = expected
    elif kind == "completion":
        a = run.accounting()
        if (
            run.decision is None
            or run.decision.action != "COMPLETE"
            or run.state.stopped
            or tuple(o.slot for o in run.state.outcomes) != ORDER
            or run.active is not None
            or run.shutdown is None
            or not all(run.shutdown.values())
            or a["unknown_attempts"]
            or a["incomplete_calls"]
            or a["operational_errors"]
        ):
            raise JournalError("completion_not_established")
        expected = {
            "evidence_sha256": run.bundle_digest(),
            "state_sha256": fingerprint(_json(asdict(run.state))),
            "accounting": a,
            "human_review": "PENDING",
        }
        run.completion_sequence = sequence
    elif kind == "completion_ack":
        if run.completion_sequence is None:
            raise JournalError("missing_completion")
        expected = {"completion_sequence": run.completion_sequence}
        run.sealed = True
    else:
        raise JournalError("unknown_record_type")
    if canonical_json(p) != canonical_json(expected):
        raise JournalError("record_fields_or_bindings_differ")


def _scan(
    binding: RegistryBinding, run_id: str
) -> tuple[_Run, list[dict[str, Any]], list[str], int]:
    run, pending = _Run(), 0
    records: list[dict[str, Any]] = []
    issues: list[str] = []
    descriptors = []
    try:
        root = _registry(binding)
        descriptors.append(root)
        runs = os.open(
            "runs", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root
        )
        descriptors.append(runs)
        directory = os.open(
            _identifier(run_id),
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=runs,
        )
        descriptors.append(directory)
        _private(os.fstat(directory), directory=True)
        if set(os.listdir(directory)) - {"records"}:
            issues.append("unexpected_run_entry")
        ledger = os.open(
            "records", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
        )
        descriptors.append(ledger)
        _private(os.fstat(ledger), directory=True)
        for name in sorted(os.listdir(ledger)):
            if name.startswith(".pending-"):
                _private(os.stat(name, dir_fd=ledger, follow_symlinks=False))
                pending += 1
                continue
            if name != f"{len(records):06d}.json":
                raise JournalError("missing_or_unexpected_record")
            record = _read(ledger, name)
            observed_at = datetime.fromisoformat(record["recorded_at"])
            if observed_at.utcoffset() is None:
                raise JournalError("invalid_record_time")
            if set(record) != {
                "schema_id",
                "run_id",
                "sequence",
                "previous_sha256",
                "recorded_at",
                "kind",
                "payload",
            } or (
                record["schema_id"] != SCHEMA
                or record["run_id"] != run_id
                or type(record["sequence"]) is not int
                or record["sequence"] != len(records)
                or record["previous_sha256"]
                != (fingerprint(records[-1]) if records else None)
            ):
                raise JournalError("record_chain_differs")
            candidate = deepcopy(run)
            _apply(candidate, record["kind"], record["payload"], len(records))
            if not records:
                manifest = candidate.manifest
                assert manifest is not None
                if manifest["run_id"] != run_id or manifest[
                    "registry"
                ] != binding.model_dump(mode="json"):
                    raise JournalError("manifest_identity_differs")
                approvals = os.open(
                    "approvals",
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=root,
                )
                try:
                    claim = _read(
                        approvals, fingerprint(manifest["approval_id"]) + ".json"
                    )
                    if claim != {
                        "run_id": run_id,
                        "approval_id": manifest["approval_id"],
                        "registry_id": binding.registry_id,
                    }:
                        raise JournalError("approval_claim_differs")
                finally:
                    os.close(approvals)
            run = candidate
            records.append(record)
        if not records:
            issues.append("missing_manifest")
    except Exception:  # noqa: BLE001 - fixed diagnostics at the storage/privacy boundary
        issues.append("corrupt_or_conflicting_evidence")
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    return run, records, issues, pending


class CanaryJournal:
    """Single-use producer of supplied offline evidence; cannot reopen any run."""

    def __init__(
        self,
        registry: RegistryBinding,
        run_id: str,
        approval_id: str,
        *,
        source_receipt: object,
    ):
        self.registry = registry
        self.run_id = _identifier(run_id)
        approval_id = _identifier(approval_id)
        receipt = parse_receipt(source_receipt)
        validate_binding(receipt.binding)
        if receipt.binding.identifier != V3:
            raise JournalError("explicit_v3_required")
        self._mutex = threading.RLock()
        self._pid = os.getpid()
        self._writer: int | None = _lock(registry, exclusive=True)
        self._ledger: int | None = None
        self._records: list[dict[str, Any]] = []
        self._run = _Run()
        descriptors = []
        try:
            root = _registry(registry)
            descriptors.append(root)
            runs = os.open(
                "runs", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root
            )
            descriptors.append(runs)
            directory = _mkdir(runs, run_id)
            descriptors.append(directory)
            self._directory_identity = (
                os.fstat(directory).st_dev,
                os.fstat(directory).st_ino,
            )
            approvals = os.open(
                "approvals", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root
            )
            descriptors.append(approvals)
            _publish(
                approvals,
                fingerprint(approval_id) + ".json",
                {
                    "run_id": run_id,
                    "approval_id": approval_id,
                    "registry_id": registry.registry_id,
                },
            )
            self._ledger = _mkdir(directory, "records")
            self._ledger_identity = (
                os.fstat(self._ledger).st_dev,
                os.fstat(self._ledger).st_ino,
            )
            self._append(
                "manifest",
                {
                    "schema_id": SCHEMA,
                    "run_id": run_id,
                    "approval_id": approval_id,
                    "registry": registry.model_dump(mode="json"),
                    "source_receipt": receipt.model_dump(mode="json"),
                    "source_receipt_sha256": fingerprint(
                        receipt.model_dump(mode="json")
                    ),
                    "source_authorised": False,
                    "authorises_live_execution": False,
                    "provider_evidence_authenticated": False,
                },
            )
        except BaseException:  # noqa: BLE001 - interruptions must close recording gates
            self.close()
            raise JournalError("run_or_approval_consumed_or_unavailable") from None
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    def close(self) -> None:
        for name in ("_ledger", "_writer"):
            descriptor = getattr(self, name, None)
            setattr(self, name, None)
            if descriptor is not None:
                os.close(descriptor)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is not None and self._writer is not None:
            with suppress(JournalError):
                self.stop("interrupted")
        self.close()

    def _append(self, kind: str, payload: dict[str, Any]) -> None:
        if self._ledger is None:
            raise JournalError("writer_closed")
        candidate = deepcopy(self._run)
        _apply(candidate, kind, payload, len(self._records))
        record = {
            "schema_id": SCHEMA,
            "run_id": self.run_id,
            "sequence": len(self._records),
            "previous_sha256": fingerprint(self._records[-1])
            if self._records
            else None,
            "recorded_at": datetime.now(UTC).isoformat(),
            "kind": kind,
            "payload": payload,
        }
        _publish(self._ledger, f"{len(self._records):06d}.json", record)
        self._records.append(record)
        self._run = candidate

    def _record(self, kind: str, payload: dict[str, Any]) -> None:
        with self._mutex:
            try:
                if self._writer is None or self._pid != os.getpid():
                    raise JournalError("writer_closed_or_forked")
                path = Path(self.registry.path) / "runs" / self.run_id
                for location, expected in (
                    (path, self._directory_identity),
                    (path / "records", self._ledger_identity),
                ):
                    info = location.lstat()
                    _private(info, directory=True)
                    if (info.st_dev, info.st_ino) != expected:
                        raise JournalError("directory_substituted")
                root = _registry(self.registry)
                try:
                    approvals = os.open(
                        "approvals",
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=root,
                    )
                    try:
                        assert self._run.manifest is not None
                        approval = self._run.manifest["approval_id"]
                        if _read(approvals, fingerprint(approval) + ".json") != {
                            "run_id": self.run_id,
                            "approval_id": approval,
                            "registry_id": self.registry.registry_id,
                        }:
                            raise JournalError("approval_claim_changed")
                    finally:
                        os.close(approvals)
                finally:
                    os.close(root)
                if self._ledger is None:
                    raise JournalError("writer_closed")
                names = set(os.listdir(self._ledger))
                final = {name for name in names if not name.startswith(".pending-")}
                if final != {f"{i:06d}.json" for i in range(len(self._records))}:
                    raise JournalError("committed_evidence_changed")
                for i, expected_record in enumerate(self._records):
                    if fingerprint(_read(self._ledger, f"{i:06d}.json")) != fingerprint(
                        expected_record
                    ):
                        raise JournalError("committed_evidence_changed")
                self._append(kind, payload)
            except BaseException:  # noqa: BLE001 - interruptions must close recording gates
                self.close()
                raise JournalError("journal_stopped_preserve_evidence") from None

    def record_decision(self, guards: OperationalGuards) -> Decision:
        try:
            supplied = _guards(_json(asdict(guards)))
        except Exception:  # noqa: BLE001 - malformed guard claims cannot leave a producer enabled
            self.close()
            raise JournalError("invalid_guard_snapshot") from None
        effective = _effective(self._run, supplied)
        decision = decide(self._run.state, effective)
        self._record(
            "decision",
            {
                "supplied_guards": _json(asdict(supplied)),
                "effective_guards": _json(asdict(effective)),
                "accounting": self._run.accounting(),
                "decision": _json(asdict(decision)),
            },
        )
        assert self._run.decision is not None
        return self._run.decision

    def reserve_turn(self, slot: str) -> None:
        self._record(
            "turn_reserved",
            {"slot": slot, "decision_sequence": self._run.decision_sequence},
        )

    def reserve_call(self, number: int) -> None:
        self._record(
            "call_reserved", {"slot": self._run.active, "logical_call": number}
        )

    def record_dispatch(self, number: int, attempt: int) -> None:
        self._record(
            "provider_dispatch",
            {"slot": self._run.active, "logical_call": number, "attempt": attempt},
        )

    def record_provider_result(
        self,
        number: int,
        attempt: int,
        envelope: object,
        *,
        http_status: int | None = None,
        request_id: str | None = None,
        should_retry_header: object = None,
    ) -> None:
        self._record(
            "provider_result",
            {
                "slot": self._run.active,
                "logical_call": number,
                "attempt": attempt,
                "observation": provider_observation(
                    envelope,
                    http_status=http_status,
                    request_id=request_id,
                    should_retry_header=should_retry_header,
                ),
            },
        )

    def complete_call(self, number: int) -> None:
        self._record(
            "call_completed", {"slot": self._run.active, "logical_call": number}
        )

    def record_chat(self, raw: object) -> None:
        try:
            safe = project_chat(raw)
        except EvidenceProjectionError:
            self._record(
                "evidence_error",
                {"slot": self._run.active, "code": "invalid_public_chat"},
            )
        else:
            self._record("chat", {"slot": self._run.active, "chat": safe})

    def record_trace(self, raw: object, *, reread: object) -> None:
        code = "invalid_public_trace"
        try:
            safe = project_trace(raw)
            if safe != project_trace(reread):
                code = "trace_reread_differs"
                raise EvidenceProjectionError(code)
        except EvidenceProjectionError:
            self._record("evidence_error", {"slot": self._run.active, "code": code})
        else:
            self._record(
                "trace",
                {
                    "slot": self._run.active,
                    "trace": safe,
                    "reread_sha256": fingerprint(safe),
                },
            )

    def assess_turn(self) -> dict[str, Any]:
        slot = self._run.active
        if slot is None:
            raise JournalError("no_active_turn")
        payload: dict[str, Any] = {
            "slot": slot,
            "revision": len(self._run.assessments.get(slot, [])),
            "evidence_sha256": fingerprint(self._run.evidence[slot]),
            "report": self._run.assessment(slot),
        }
        self._record("assessment", payload)
        return deepcopy(payload["report"])

    def complete_turn(self) -> None:
        # Compute the outcome using the same fixed-record validator used by scan.
        slot = self._run.active
        if slot is None or not self._run.assessments.get(slot):
            raise JournalError("missing_active_assessment")
        e = self._run.evidence[slot]
        report = assess_selection(
            slot,
            e.get("chat", {}),
            restore_trace(e["trace"]) if "trace" in e else {},
            previous=self._run.previous(slot),
        )
        a = self._run.accounting(slot)
        complete = bool(
            "chat" in e
            and "trace" in e
            and not a["incomplete_calls"]
            and not a["unknown_attempts"]
            and not a["operational_errors"]
        )
        outcome = TurnOutcome(
            slot,
            report.checks,
            a["logical_calls"],
            a["provider_attempts"],
            complete,
            complete and report.prerequisites.status == "PASS",
        )
        self._record(
            "outcome",
            {
                "slot": slot,
                "assessment_revision": len(self._run.assessments[slot]) - 1,
                "outcome": _json(asdict(outcome)),
            },
        )

    def stop(self, code: str = "operator_stop") -> None:
        self._record("stop", {"code": code})

    def record_shutdown(
        self, *, worker_stopped: bool, sdk_closed: bool, no_inflight_provider: bool
    ) -> None:
        self._record(
            "shutdown",
            {
                "worker_stopped": worker_stopped,
                "sdk_closed": sdk_closed,
                "no_inflight_provider": no_inflight_provider,
            },
        )

    def seal(self) -> None:
        self._record(
            "completion",
            {
                "evidence_sha256": self._run.bundle_digest(),
                "state_sha256": fingerprint(_json(asdict(self._run.state))),
                "accounting": self._run.accounting(),
                "human_review": "PENDING",
            },
        )
        # This record can only be created after the completion seal's fsync
        # returned. Its presence proves that prior seal was acknowledged, even
        # if publication of this final acknowledgement was itself interrupted.
        self._record(
            "completion_ack", {"completion_sequence": self._run.completion_sequence}
        )
        self.close()


def _report(binding: RegistryBinding, run_id: str) -> dict[str, Any]:
    run, records, issues, pending = _scan(binding, run_id)
    a = run.accounting()
    uncertain = bool(
        a["unknown_attempts"]
        or a["incomplete_calls"]
        or a["operational_errors"]
        or run.active is not None
        or (run.shutdown is not None and not all(run.shutdown.values()))
    )
    status = (
        "corrupt"
        if issues
        else "operationally_uncertain"
        if uncertain
        else "completed"
        if run.sealed
        else "incomplete"
    )
    return {
        "schema_id": SCHEMA,
        "run_id": run_id,
        "status": status,
        "persisted_records": len(records),
        "validated_prefix_records": len(records),
        "evidence_sha256": run.bundle_digest(),
        "structurally_validated": not issues,
        "issues": issues,
        "pending_files": pending,
        "completion_seal_present": run.completion_sequence is not None,
        "missing_completion_seal": run.completion_sequence is None,
        "completion_acknowledged": run.sealed and not issues,
        "completion_certified": status == "completed",
        "accounting": a,
        "accounting_reconciled": not issues and _reconciled(run),
        "safe_shutdown_observation": run.shutdown,
        "shutdown_evidence": "supplied_not_independently_authenticated",
        "execution_action": run.decision.action if run.decision else None,
        "assessment": _json(asdict(run.decision.assessment)) if run.decision else None,
        "mechanical_assessment": _json(asdict(run.decision.mechanical_assessment))
        if run.decision
        else None,
        "operational_assessment": _json(asdict(run.decision.operational_assessment))
        if run.decision
        else None,
        "human_review": "PENDING",
        "source_authorised": False,
        "provider_evidence_authenticated": False,
        "authorises_live_execution": False,
        "records": records,
    }


def inspect_run(registry: RegistryBinding, run_id: str) -> dict[str, Any]:
    """Read-only stable inventory; refuse a snapshot while a producer holds the lock."""
    _identifier(run_id)
    descriptor = _lock(registry, exclusive=False)
    try:
        return _report(registry, run_id)
    finally:
        os.close(descriptor)


def recover_save_only(
    registry: RegistryBinding, run_id: str, destination: Path
) -> dict[str, Any]:
    """Export only the validated prefix and explicit status; never repair/seal source."""
    _identifier(run_id)
    destination = destination.absolute()
    _outside(destination)
    root_path = Path(registry.path)
    if destination.is_relative_to(root_path) or root_path.is_relative_to(destination):
        raise JournalError("export_must_be_separate")
    descriptor = _lock(registry, exclusive=True)
    parent = output = None
    try:
        report = _report(registry, run_id)
        parent = _open_directory(destination.parent)
        output = _mkdir(parent, destination.name)
        _publish(output, "report.json", report)
        current = _open_directory(destination)
        try:
            _private(os.fstat(current), directory=True)
            if (os.fstat(current).st_dev, os.fstat(current).st_ino) != (
                os.fstat(output).st_dev,
                os.fstat(output).st_ino,
            ):
                raise JournalError("export_destination_substituted")
        finally:
            os.close(current)
        return report
    except Exception:  # noqa: BLE001 - fixed diagnostics at the storage/privacy boundary
        raise JournalError("save_only_export_failed") from None
    finally:
        for opened in (output, parent, descriptor):
            if opened is not None:
                os.close(opened)
