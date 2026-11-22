"""Detached synthetic evidence commitments, never execution or authentication.

Trust retained bindings, code/process, cooperative local stores and OS/filesystem.
Public inspectors have no hard resource budgets. Commitments detect differences;
they do not authenticate claims, establish historical completeness or confer
authority. Publication does not perform source inspection or independent custody.
"""

from __future__ import annotations

import json
import os
import re
import stat
from contextlib import suppress
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated, Any, Final, Literal

from pydantic import BaseModel, Field, model_validator

from harness.canary import approval_v3 as approval
from harness.canary import authority_v3 as authority
from harness.canary import journal_v3 as journal
from harness.canary import runtime_v3 as source
from harness.core.fingerprints import CANONICAL_VERSION, fingerprint

SCHEMA: Final = "canary-detached-evidence-envelope-v1"
COMMITMENT_PROFILE: Final = "canary-detached-envelope-commitment-sha256-v1"
MAX_ENVELOPE_BYTES = 65_536
MAX_REFERENCE_BYTES = 4_096
MAX_PAYLOAD_BYTES = 65_536
MAX_SIGNATURE_BYTES = 4_096
MAX_ENVELOPE_DEPTH = 16
MAX_ENVELOPE_VALUES = 4_096
MAX_JOURNAL_RECORDS = 2_048
MAX_RECORD_BYTES = 512 * 1_024
MAX_JOURNAL_BYTES = 16 * 1_024 * 1_024
MAX_JOURNAL_DEPTH = 64
MAX_JOURNAL_VALUES = 500_000
MAX_AUTHORITY_BYTES = 16 * 1_024 * 1_024

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]
RegistryID = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
Counter = Annotated[int, Field(ge=0, le=2_147_483_647)]
QualityStatus = Literal["PASS", "FAIL", "ERROR", "SKIP"]


class EnvelopeError(ValueError):
    """Only fixed codes; no supplied paths, payloads or external diagnostics."""

    def __init__(self, code: str):
        allowed = {
            "invalid_input",
            "invalid_envelope",
            "noncanonical_envelope",
            "unsupported_version",
            "invalid_reference",
            "reference_mismatch",
            "binding_mismatch",
            "resource_limit",
            "authority_absent",
            "authority_conflict",
            "authority_corrupt",
            "authority_unavailable",
            "authority_pending",
            "journal_corrupt",
            "journal_pending",
            "journal_unavailable",
            "source_changed",
            "source_mismatch",
            "inspection_interrupted",
            "invalid_publication_root",
            "unsafe_destination",
            "destination_exists",
            "publication_failed",
            "publication_outcome_unknown",
            "artifact_unavailable",
        }
        super().__init__(code if code in allowed else "invalid_input")


class Assurance(source.Frozen):
    assurance_class: Literal["synthetic-offline-only"] = "synthetic-offline-only"
    history_scope: Literal["currently-inspected-validated-sequence"] = (
        "currently-inspected-validated-sequence"
    )
    historical_completeness: Literal["not-established"] = "not-established"
    snapshot_semantics: Literal["separate-repeated-observations"] = (
        "separate-repeated-observations"
    )
    approval_evidence: Literal["recorded-consumption-byte-digest-agreement"] = (
        "recorded-consumption-byte-digest-agreement"
    )
    source_evidence: Literal["recorded-source-receipt-claims"] = (
        "recorded-source-receipt-claims"
    )
    invocation_status: Literal["not-established"] = "not-established"
    human_review: Literal["PENDING"] = "PENDING"
    real_human_authorisation_authenticated: Literal[False] = False
    source_authorised: Literal[False] = False
    provider_evidence_authenticated: Literal[False] = False
    authorises_live_execution: Literal[False] = False
    execution_admission_established: Literal[False] = False
    fresh_approval_signature_verified: Literal[False] = False


class AuthorityEvidence(source.Frozen):
    store_binding_sha256: source.Digest
    receipt: authority.ConsumptionReceipt


class JournalEvidence(source.Frozen):
    schema_id: Literal["nonstudy-canary-journal-v3-v1"] = (
        "nonstudy-canary-journal-v3-v1"
    )
    registry_id: RegistryID
    registry_binding_sha256: source.Digest
    run_id: authority.RunID
    approval_id: approval.AuthorisationID
    validated_records: int = Field(ge=1, le=MAX_JOURNAL_RECORDS)
    history_commitment_sha256: source.Digest
    evidence_sha256: source.Digest


class RecordedSource(source.Frozen):
    schema_id: Literal["canary-source-approval-v1"]
    provenance: Literal["synthetic-test"]
    execution_profile: Literal["offline-verification-v1"]
    receipt_sha256: source.Digest
    harness: source.GitIdentity
    application: source.GitIdentity
    harness_lock_sha256: source.Digest
    application_lock_sha256: source.Digest
    runtime: source.RuntimeIdentity
    definition_identifier: Literal["salesagent-canary-selected-preferences-v3"]
    definition_binding_sha256: source.Digest
    roster_fingerprint: source.Digest
    definition_fingerprint: source.Digest
    acceptance_policy: Identifier
    acceptance_fingerprint: source.Digest
    execution_policy: Identifier
    execution_fingerprint: source.Digest
    v2_1_fingerprint: source.Digest
    application_revision: source.Revision
    fixture_hashes: tuple[
        tuple[Literal["products.json", "discounts.json"], source.Digest], ...
    ]
    inference: source.Inference
    limits: source.Limits
    definition_storage_schema: Identifier


class ShutdownObservation(source.Frozen):
    worker_stopped: bool
    sdk_closed: bool
    no_inflight_provider: bool


class RecordedExecution(source.Frozen):
    journal_status: Literal["completed", "incomplete", "operationally_uncertain"]
    completion_seal_present: bool
    completion_acknowledged: bool
    journal_completion_certified: bool
    accounting_reconciled: bool
    execution_action: Literal["ADVANCE", "STOP", "COMPLETE"] | None
    safe_shutdown_observation: ShutdownObservation | None
    mechanical_assessment_status: QualityStatus | None
    operational_assessment_status: QualityStatus | None
    overall_assessment_status: QualityStatus | None

    @model_validator(mode="after")
    def _consistent(self) -> RecordedExecution:
        completed = self.journal_status == "completed"
        if self.journal_completion_certified != completed:
            raise ValueError("invalid_completion")
        if self.completion_acknowledged != completed:
            raise ValueError("invalid_acknowledgement")
        if completed and not (
            self.completion_seal_present
            and self.accounting_reconciled
            and self.execution_action == "COMPLETE"
            and self.safe_shutdown_observation is not None
            and all(vars(self.safe_shutdown_observation).values())
        ):
            raise ValueError("invalid_completion_observations")
        statuses = (
            self.mechanical_assessment_status,
            self.operational_assessment_status,
            self.overall_assessment_status,
        )
        if any(
            (value is None) != (self.execution_action is None) for value in statuses
        ):
            raise ValueError("invalid_assessment_presence")
        return self


class RecordedAccounting(source.Frozen):
    logical_calls: Counter
    provider_attempts: Counter
    unknown_attempts: Counter
    incomplete_calls: Counter
    retryable_http_failures: Counter
    operational_errors: Counter
    estimated_subtotal_usd: str = Field(min_length=1, max_length=64)
    estimated_total_usd: str | None = Field(max_length=64)
    billing_verified: Literal[False]

    @model_validator(mode="after")
    def _costs(self) -> RecordedAccounting:
        for value in (self.estimated_subtotal_usd, self.estimated_total_usd):
            if value is not None:
                try:
                    amount = Decimal(value)
                    if not amount.is_finite() or amount < 0 or value != value.strip():
                        raise ValueError("invalid_cost")
                except InvalidOperation:
                    raise ValueError("invalid_cost") from None
        if self.estimated_total_usd != (
            None if self.unknown_attempts else self.estimated_subtotal_usd
        ):
            raise ValueError("invalid_total")
        return self


class EvidenceEnvelope(source.Frozen):
    schema_id: Literal["canary-detached-evidence-envelope-v1"] = SCHEMA
    canonicalization: Literal["replay-canonical-json-v1"] = "replay-canonical-json-v1"
    commitment_profile: Literal["canary-detached-envelope-commitment-sha256-v1"] = (
        COMMITMENT_PROFILE
    )
    assurance: Assurance = Field(default_factory=Assurance)
    authority: AuthorityEvidence
    journal: JournalEvidence
    source: RecordedSource
    execution: RecordedExecution
    accounting: RecordedAccounting

    @model_validator(mode="after")
    def _bindings(self) -> EvidenceEnvelope:
        receipt = self.authority.receipt
        if (
            receipt.intended_run_id != self.journal.run_id
            or receipt.authorisation_id != self.journal.approval_id
            or receipt.source_receipt_sha256 != self.source.receipt_sha256
            or self.source.application_revision != source.APPLICATION_REVISION
            or self.source.application.commit != source.APPLICATION_REVISION
        ):
            raise ValueError("invalid_envelope_bindings")
        if self.execution.journal_completion_certified and (
            self.accounting.unknown_attempts
            or self.accounting.incomplete_calls
            or self.accounting.operational_errors
        ):
            raise ValueError("invalid_completed_accounting")
        return self


class ExpectedEnvelopeReference(source.Frozen):
    schema_id: Literal["canary-expected-envelope-reference-v1"] = (
        "canary-expected-envelope-reference-v1"
    )
    commitment_profile: Literal["canary-detached-envelope-commitment-sha256-v1"] = (
        COMMITMENT_PROFILE
    )
    envelope_commitment_sha256: source.Digest
    store_id: authority.StoreID
    store_binding_sha256: source.Digest
    registry_id: RegistryID
    registry_binding_sha256: source.Digest
    authorisation_id: approval.AuthorisationID
    execution_audience: approval.Audience
    run_id: authority.RunID


class EnvelopeVerification(source.Frozen):
    schema_id: Literal["canary-envelope-verification-v1"] = (
        "canary-envelope-verification-v1"
    )
    envelope_commitment_sha256: source.Digest
    artifact_representation: Literal["canonical-valid"] = "canonical-valid"
    expected_reference: Literal["matches-supplied-reference"] = (
        "matches-supplied-reference"
    )
    source_comparison: Literal["not-performed", "matches-reobserved-sources"]
    approval_signature_verification: Literal["not-performed"] = "not-performed"
    assurance: Assurance = Field(default_factory=Assurance)


class TrustedPublicationRoot(source.Frozen):
    """Independently provisioned caller binding, never artifact-selected storage.

    The caller establishes repository/historical/other protected exclusions.
    Metadata checks are not a defence against a hostile same-user/privileged OS.
    """

    schema_id: Literal["canary-private-publication-root-v1"] = (
        "canary-private-publication-root-v1"
    )
    path: str
    device: int = Field(ge=0)
    directory_inode: int = Field(ge=1)

    @model_validator(mode="after")
    def _path(self) -> TrustedPublicationRoot:
        _absolute(self.path)
        return self


class PublicationReceipt(source.Frozen):
    schema_id: Literal["canary-envelope-publication-result-v1"] = (
        "canary-envelope-publication-result-v1"
    )
    publication_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")]
    bytes_written: int = Field(ge=1, le=MAX_ENVELOPE_BYTES)
    publication_status: Literal["local-publication-protocol-completed"] = (
        "local-publication-protocol-completed"
    )
    reference_candidate: ExpectedEnvelopeReference
    source_inspections_performed: Literal[False] = False
    independent_custody: Literal["not-established-by-publisher"] = (
        "not-established-by-publisher"
    )


def _plain(value: Any, *, depth: int, nodes: int, string_limit: int) -> Any:
    remaining = nodes

    def visit(item: Any, level: int) -> Any:
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or level > depth:
            raise EnvelopeError("resource_limit")
        if isinstance(item, BaseModel):
            # Preserve unknown fields on validation-bypassing copies.
            item = {**vars(item), **(item.__pydantic_extra__ or {})}
        if type(item) is dict:
            result = {}
            for key, child in item.items():
                if type(key) is not str:
                    raise ValueError
                visit(key, level + 1)
                result[key] = visit(child, level + 1)
            return result
        if type(item) in (list, tuple):
            return [visit(child, level + 1) for child in item]
        if type(item) is str:
            if len(item) > string_limit or len(item.encode("utf-8")) > string_limit:
                raise EnvelopeError("resource_limit")
            return item
        if item is None or type(item) in (bool, int, float):
            return item
        raise ValueError

    return visit(value, 0)


def _encode(
    value: Any,
    *,
    limit: int = MAX_ENVELOPE_BYTES,
    depth: int = MAX_ENVELOPE_DEPTH,
    nodes: int = MAX_ENVELOPE_VALUES,
) -> bytes:
    plain = _plain(value, depth=depth, nodes=nodes, string_limit=limit)
    encoder = json.JSONEncoder(
        sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    chunks = bytearray()
    for chunk in encoder.iterencode(plain):
        data = chunk.encode("utf-8")
        if len(chunks) + len(data) > limit:
            raise EnvelopeError("resource_limit")
        chunks.extend(data)
    return bytes(chunks)


def _checked[Model: BaseModel](
    model: type[Model], value: object, code: str, *, limit: int = MAX_ENVELOPE_BYTES
) -> Model:
    try:
        raw = _encode(value, limit=limit)
        checked = model.model_validate_json(raw)
        if raw != _encode(checked, limit=limit):
            raise ValueError
        return checked
    except EnvelopeError:
        raise
    except Exception:  # noqa: BLE001 - never expose supplied models or diagnostics
        raise EnvelopeError(code) from None


def serialize_envelope(envelope: EvidenceEnvelope) -> bytes:
    """Pure canonical representation only; not proof of inspection."""
    return _encode(_checked(EvidenceEnvelope, envelope, "invalid_envelope"))


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError
        value[key] = item
    return value


def _json_depth(raw: bytes) -> None:
    level = 0
    quoted = escaped = False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            level += 1
            if level > MAX_ENVELOPE_DEPTH:
                raise EnvelopeError("resource_limit")
        elif byte in (93, 125):
            level -= 1


def parse_envelope(raw: bytes) -> EvidenceEnvelope:
    """Require bounded exact canonical bytes, including all constant fields."""
    if type(raw) is not bytes or not raw:
        raise EnvelopeError("invalid_envelope")
    if len(raw) > MAX_ENVELOPE_BYTES:
        raise EnvelopeError("resource_limit")
    try:
        _json_depth(raw)
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
        if _encode(value) != raw:
            raise EnvelopeError("noncanonical_envelope")
        if type(value) is dict and any(
            key in value and value[key] != expected
            for key, expected in (
                ("schema_id", SCHEMA),
                ("canonicalization", CANONICAL_VERSION),
                ("commitment_profile", COMMITMENT_PROFILE),
            )
        ):
            raise EnvelopeError("unsupported_version")
        return _checked(EvidenceEnvelope, value, "invalid_envelope")
    except EnvelopeError:
        raise
    except Exception:  # noqa: BLE001 - malformed bytes remain private
        raise EnvelopeError("invalid_envelope") from None


def envelope_commitment_sha256(envelope: EvidenceEnvelope) -> str:
    """Reviewed structured commitment; deliberately not a raw file-byte hash."""
    checked = parse_envelope(serialize_envelope(envelope))
    return fingerprint(
        {
            "domain": "canary-detached-envelope-v1",
            "canonicalization": CANONICAL_VERSION,
            "envelope": checked.model_dump(mode="json"),
        }
    )


def _absolute(value: str) -> Path:
    path = Path(value)
    if path.anchor != "/" or str(path) != value or ".." in path.parts:
        raise ValueError
    return path


def _directory(
    path: Path,
    expected: tuple[int, int] | None = None,
    *,
    forbidden: frozenset[tuple[int, int]] = frozenset(),
) -> int:
    """No-follow descriptor walk; no discovery, creation or recovery."""
    path = _absolute(str(path))
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        info = os.fstat(descriptor)
        if (info.st_dev, info.st_ino) in forbidden:
            raise EnvelopeError("unsafe_destination")
        for part in path.parts[1:]:
            previous = descriptor
            descriptor = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(previous)
            info = os.fstat(descriptor)
            if (info.st_dev, info.st_ino) in forbidden:
                raise EnvelopeError("unsafe_destination")
        if expected is not None:
            info = os.fstat(descriptor)
            if (info.st_dev, info.st_ino) != expected:
                raise ValueError
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _private(info: os.stat_result, *, directory: bool = False) -> None:
    if (
        info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
        or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        or (not directory and info.st_nlink != 1)
    ):
        raise ValueError


def _preflight_authority(binding: authority.AuthorityStoreBinding) -> None:
    root = _directory(
        _absolute(binding.configuration.store_path),
        (binding.device, binding.directory_inode),
    )
    try:
        _private(os.fstat(root), directory=True)
        info = os.stat("authority.sqlite3", dir_fd=root, follow_symlinks=False)
        _private(info)
        if (info.st_dev, info.st_ino) != (binding.device, binding.database_inode):
            raise ValueError
        if info.st_size > MAX_AUTHORITY_BYTES:
            raise EnvelopeError("resource_limit")
    finally:
        os.close(root)


def _preflight_journal(binding: journal.RegistryBinding, run_id: str) -> None:
    """Admission checks only: the unchanged inspector has no internal budget."""
    descriptors = []
    try:
        root = _directory(_absolute(binding.path), (binding.device, binding.inode))
        descriptors.append(root)
        _private(os.fstat(root), directory=True)
        parent = root
        for name in ("runs", run_id, "records"):
            child = os.open(
                name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
            )
            descriptors.append(child)
            _private(os.fstat(child), directory=True)
            parent = child
        total = count = 0
        with os.scandir(parent) as entries:
            for entry in entries:
                count += 1
                if count > MAX_JOURNAL_RECORDS:
                    raise EnvelopeError("resource_limit")
                if entry.name.startswith(".pending-"):
                    raise EnvelopeError("journal_pending")
                if re.fullmatch(r"[0-9]{6}\.json", entry.name) is None:
                    raise EnvelopeError("journal_corrupt")
                info = entry.stat(follow_symlinks=False)
                _private(info)
                total += info.st_size
                if info.st_size > MAX_RECORD_BYTES or total > MAX_JOURNAL_BYTES:
                    raise EnvelopeError("resource_limit")
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _consumption(
    binding: authority.AuthorityStoreBinding,
    authorisation_id: str,
    expected: authority.ConsumptionReceipt | None = None,
) -> authority.ConsumptionReceipt:
    try:
        _preflight_authority(binding)
        observed = authority.inspect_consumption(
            binding, authorisation_id, expected_record=expected
        )
        observed = _checked(
            authority.ConsumptionInspection, observed, "authority_corrupt"
        )
        if observed.status != "consumed":
            raise EnvelopeError("authority_" + observed.status)
        if observed.issues:
            raise EnvelopeError(
                "authority_pending"
                if set(observed.issues)
                & {"pending_consumption", "rollback_journal_present"}
                else "authority_unavailable"
            )
        if observed.record is None:
            raise EnvelopeError("authority_corrupt")
        if expected is not None and observed.record != expected:
            raise EnvelopeError("source_changed")
        return observed.record
    except EnvelopeError:
        raise
    except Exception:  # noqa: BLE001 - no source paths or external diagnostics
        raise EnvelopeError("authority_unavailable") from None


def _journal(binding: journal.RegistryBinding, run_id: str) -> dict[str, Any]:
    try:
        _preflight_journal(binding, run_id)
        report = journal.inspect_run(binding, run_id)
        if (
            report["structurally_validated"] is not True
            or report["issues"]
            or report["status"] == "corrupt"
        ):
            raise EnvelopeError("journal_corrupt")
        if report["pending_files"] != 0:
            raise EnvelopeError("journal_pending")
        records = report["records"]
        if type(records) is not list or not records:
            raise EnvelopeError("journal_corrupt")
        if len(records) > MAX_JOURNAL_RECORDS:
            raise EnvelopeError("resource_limit")
        _encode(
            records,
            limit=MAX_JOURNAL_BYTES,
            depth=MAX_JOURNAL_DEPTH,
            nodes=MAX_JOURNAL_VALUES,
        )
        if (
            report["schema_id"] != journal.SCHEMA
            or report["run_id"] != run_id
            or report["persisted_records"] != len(records)
            or report["validated_prefix_records"] != len(records)
            or any(
                report[name] is not False
                for name in (
                    "source_authorised",
                    "provider_evidence_authenticated",
                    "authorises_live_execution",
                )
            )
        ):
            raise EnvelopeError("journal_corrupt")
        return report
    except EnvelopeError:
        raise
    except journal.JournalError:
        raise EnvelopeError("journal_unavailable") from None
    except Exception:  # noqa: BLE001 - inspector/layout diagnostics stay private
        raise EnvelopeError("journal_unavailable") from None


def _recorded_source(receipt: source.SourceApprovalReceipt) -> RecordedSource:
    document = receipt.model_dump(mode="json")
    binding = document["binding"]
    projection = {
        name: document[name]
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
    projection.update(
        {
            name: binding[name]
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
    projection.update(
        receipt_sha256=fingerprint(document),
        definition_identifier=binding["identifier"],
        definition_binding_sha256=fingerprint(binding),
        definition_storage_schema=binding["storage_schema"],
    )
    return _checked(RecordedSource, projection, "binding_mismatch")


def _history_commitment(
    records: list[dict[str, Any]], binding: journal.RegistryBinding, run_id: str
) -> str:
    # Call only after bounded record encoding. No private replay implementation.
    return fingerprint(
        {
            "domain": "canary-detached-journal-history-v1",
            "canonicalization": CANONICAL_VERSION,
            "journal_schema": journal.SCHEMA,
            "registry_id": binding.registry_id,
            "run_id": run_id,
            "records": records,
        }
    )


def _projection(
    receipt: authority.ConsumptionReceipt,
    report: dict[str, Any],
    proposal: approval.ProposedCanary,
    store: authority.AuthorityStoreBinding,
    registry: journal.RegistryBinding,
    run_id: str,
) -> EvidenceEnvelope:
    records = report["records"]
    manifest = records[0]["payload"]
    saved_source = source.parse_receipt(_encode(manifest["source_receipt"]).decode())
    if (
        records[0]["kind"] != "manifest"
        or manifest["approval_id"] != receipt.authorisation_id
        or manifest["run_id"] != run_id
        or manifest["registry"] != registry.model_dump(mode="json")
        or saved_source != proposal.source_receipt
        or manifest["source_receipt_sha256"] != receipt.source_receipt_sha256
    ):
        raise EnvelopeError("binding_mismatch")
    for record in records:
        if record["kind"] == "instrumentation_profile":
            saved = record["payload"]["binding"]
            if saved != {
                "definition": proposal.source_receipt.binding.model_dump(mode="json"),
                "registry_id": registry.registry_id,
                "run_id": run_id,
                "source_receipt_sha256": receipt.source_receipt_sha256,
                "project_id": proposal.project_id,
                "organization_id": proposal.organization_id,
                "transport_kind": "mock",
            }:
                raise EnvelopeError("binding_mismatch")
    execution = {
        "journal_status": report["status"],
        "completion_seal_present": report["completion_seal_present"],
        "completion_acknowledged": report["completion_acknowledged"],
        "journal_completion_certified": report["completion_certified"],
        "accounting_reconciled": report["accounting_reconciled"],
        "execution_action": report["execution_action"],
        "safe_shutdown_observation": report["safe_shutdown_observation"],
        **{
            name + "_status": None if report[key] is None else report[key]["status"]
            for name, key in (
                ("mechanical_assessment", "mechanical_assessment"),
                ("operational_assessment", "operational_assessment"),
                ("overall_assessment", "assessment"),
            )
        },
    }
    return EvidenceEnvelope(
        authority=AuthorityEvidence(
            store_binding_sha256=fingerprint(store.model_dump(mode="json")),
            receipt=receipt,
        ),
        journal=JournalEvidence(
            registry_id=registry.registry_id,
            registry_binding_sha256=fingerprint(registry.model_dump(mode="json")),
            run_id=run_id,
            approval_id=receipt.authorisation_id,
            validated_records=len(records),
            history_commitment_sha256=_history_commitment(records, registry, run_id),
            evidence_sha256=report["evidence_sha256"],
        ),
        source=_recorded_source(saved_source),
        execution=_checked(RecordedExecution, execution, "journal_corrupt"),
        accounting=_checked(
            RecordedAccounting, report["accounting"], "journal_corrupt"
        ),
    )


def assemble_envelope(
    *,
    payload: bytes,
    signature: bytes,
    expected_proposal: approval.ProposedCanary,
    store: authority.AuthorityStoreBinding,
    registry: journal.RegistryBinding,
    run_id: str,
) -> EvidenceEnvelope:
    """A1/J1/A2/J2 observations, no atomic snapshot or fresh authentication."""
    try:
        proposal = _checked(approval.ProposedCanary, expected_proposal, "invalid_input")
        store = _checked(authority.AuthorityStoreBinding, store, "invalid_input")
        registry = _checked(journal.RegistryBinding, registry, "invalid_input")
        _absolute(store.configuration.store_path)
        _absolute(registry.path)
        if (
            type(run_id) is not str
            or re.fullmatch(r"synthetic-run-[0-9a-f]{32}", run_id) is None
        ):
            raise EnvelopeError("invalid_input")
        if (
            type(payload) is not bytes
            or type(signature) is not bytes
            or not payload
            or not signature
        ):
            raise EnvelopeError("invalid_input")
        if len(payload) > MAX_PAYLOAD_BYTES or len(signature) > MAX_SIGNATURE_BYTES:
            raise EnvelopeError("resource_limit")
        manifest = approval.parse_manifest(payload)
        if manifest.execution != proposal:
            raise EnvelopeError("binding_mismatch")
        first_receipt = _consumption(store, proposal.authorisation_id)
        from hashlib import sha256

        consumed_at = datetime.strptime(
            first_receipt.consumed_at, "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=UTC)
        start = datetime.strptime(manifest.not_before, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC
        )
        end = datetime.strptime(manifest.expires_at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC
        )
        if (
            first_receipt.authorisation_id != proposal.authorisation_id
            or first_receipt.intended_run_id != run_id
            or first_receipt.store_id != store.configuration.store_id
            or first_receipt.execution_audience != proposal.execution_audience
            or first_receipt.execution_audience
            != store.configuration.execution_audience
            or first_receipt.trust_policy_identity_sha256
            != store.configuration.trust_policy_identity_sha256
            or first_receipt.payload_sha256 != sha256(payload).hexdigest()
            or first_receipt.signature_sha256 != sha256(signature).hexdigest()
            or first_receipt.proposal_sha256
            != fingerprint(proposal.model_dump(mode="json"))
            or first_receipt.source_receipt_sha256 != proposal.source_receipt_sha256
            or first_receipt.signer_principal != manifest.issuer_principal
            or not start <= consumed_at < end
        ):
            raise EnvelopeError("binding_mismatch")
        first_report = _journal(registry, run_id)
        first = _projection(
            first_receipt, first_report, proposal, store, registry, run_id
        )
        second_receipt = _consumption(store, proposal.authorisation_id, first_receipt)
        second_report = _journal(registry, run_id)
        second = _projection(
            second_receipt, second_report, proposal, store, registry, run_id
        )
        if serialize_envelope(first) != serialize_envelope(second):
            raise EnvelopeError("source_changed")
        return second
    except EnvelopeError:
        raise
    except (KeyboardInterrupt, SystemExit):
        raise EnvelopeError("inspection_interrupted") from None
    except Exception:  # noqa: BLE001 - parsing, validation and source details stay private
        raise EnvelopeError("invalid_input") from None


def _reference_candidate(envelope: EvidenceEnvelope) -> ExpectedEnvelopeReference:
    """Publication handoff data only. Never discover/adopt a verification anchor."""
    return ExpectedEnvelopeReference(
        envelope_commitment_sha256=envelope_commitment_sha256(envelope),
        store_id=envelope.authority.receipt.store_id,
        store_binding_sha256=envelope.authority.store_binding_sha256,
        registry_id=envelope.journal.registry_id,
        registry_binding_sha256=envelope.journal.registry_binding_sha256,
        authorisation_id=envelope.authority.receipt.authorisation_id,
        execution_audience=envelope.authority.receipt.execution_audience,
        run_id=envelope.journal.run_id,
    )


def verify_envelope(
    raw: bytes, *, expected: ExpectedEnvelopeReference
) -> EnvelopeVerification:
    """Agree with a separately supplied reference; custody is a caller duty."""
    reference = _checked(
        ExpectedEnvelopeReference,
        expected,
        "invalid_reference",
        limit=MAX_REFERENCE_BYTES,
    )
    checked = parse_envelope(raw)
    if (
        envelope_commitment_sha256(checked) != reference.envelope_commitment_sha256
        or checked.authority.receipt.store_id != reference.store_id
        or checked.authority.store_binding_sha256 != reference.store_binding_sha256
        or checked.journal.registry_id != reference.registry_id
        or checked.journal.registry_binding_sha256 != reference.registry_binding_sha256
        or checked.authority.receipt.authorisation_id != reference.authorisation_id
        or checked.authority.receipt.execution_audience != reference.execution_audience
        or checked.journal.run_id != reference.run_id
    ):
        raise EnvelopeError("reference_mismatch")
    return EnvelopeVerification(
        envelope_commitment_sha256=reference.envelope_commitment_sha256,
        source_comparison="not-performed",
    )


def verify_against_sources(
    raw: bytes,
    *,
    expected: ExpectedEnvelopeReference,
    payload: bytes,
    signature: bytes,
    expected_proposal: approval.ProposedCanary,
    store: authority.AuthorityStoreBinding,
    registry: journal.RegistryBinding,
) -> EnvelopeVerification:
    """Anchored artifact check, then separate fresh A1/J1/A2/J2 observations."""
    verified = verify_envelope(raw, expected=expected)
    reference = _checked(
        ExpectedEnvelopeReference,
        expected,
        "invalid_reference",
        limit=MAX_REFERENCE_BYTES,
    )
    proposal = _checked(approval.ProposedCanary, expected_proposal, "invalid_input")
    store = _checked(authority.AuthorityStoreBinding, store, "invalid_input")
    registry = _checked(journal.RegistryBinding, registry, "invalid_input")
    if (
        reference.store_id != store.configuration.store_id
        or reference.store_binding_sha256 != fingerprint(store.model_dump(mode="json"))
        or reference.registry_id != registry.registry_id
        or reference.registry_binding_sha256
        != fingerprint(registry.model_dump(mode="json"))
        or reference.authorisation_id != proposal.authorisation_id
        or reference.execution_audience != proposal.execution_audience
    ):
        raise EnvelopeError("binding_mismatch")
    assembled = assemble_envelope(
        payload=payload,
        signature=signature,
        expected_proposal=proposal,
        store=store,
        registry=registry,
        run_id=reference.run_id,
    )
    if serialize_envelope(assembled) != raw:
        raise EnvelopeError("source_mismatch")
    return EnvelopeVerification(
        envelope_commitment_sha256=verified.envelope_commitment_sha256,
        source_comparison="matches-reobserved-sources",
    )


def _publication_id(value: str) -> str:
    if (
        type(value) is not str
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", value) is None
    ):
        raise EnvelopeError("unsafe_destination")
    return value


def _publication_root(
    root: TrustedPublicationRoot,
) -> tuple[TrustedPublicationRoot, int]:
    binding = _checked(TrustedPublicationRoot, root, "invalid_publication_root")
    descriptor = None
    try:
        descriptor = _directory(
            Path(binding.path), (binding.device, binding.directory_inode)
        )
        _private(os.fstat(descriptor), directory=True)
        return binding, descriptor
    except BaseException:  # noqa: BLE001 - fixed root denial on interruption too
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
        raise EnvelopeError("invalid_publication_root") from None


def _exact_layout(directory: int) -> None:
    entries = []
    with os.scandir(directory) as iterator:
        for entry in iterator:
            entries.append(entry.name)
            if len(entries) > 1:
                raise ValueError
    if entries != ["envelope.json"]:
        raise ValueError


def _file_identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read_artifact(directory: int) -> bytes:
    _private(os.fstat(directory), directory=True)
    _exact_layout(directory)
    descriptor = os.open(
        "envelope.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
    )
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        _private(before)
        if before.st_size > MAX_ENVELOPE_BYTES:
            raise EnvelopeError("resource_limit")
        raw = stream.read(MAX_ENVELOPE_BYTES + 1)
        if len(raw) > MAX_ENVELOPE_BYTES:
            raise EnvelopeError("resource_limit")
        after = os.fstat(stream.fileno())
        current = os.stat("envelope.json", dir_fd=directory, follow_symlinks=False)
        _private(after)
        _private(current)
        if _file_identity(before) != _file_identity(after) or _file_identity(
            after
        ) != _file_identity(current):
            raise ValueError
    _exact_layout(directory)
    return raw


def _check_publication_path(
    binding: TrustedPublicationRoot, root: int, publication_id: str, directory: int
) -> None:
    current = _directory(Path(binding.path), (binding.device, binding.directory_inode))
    os.close(current)
    visible = os.stat(publication_id, dir_fd=root, follow_symlinks=False)
    _private(visible, directory=True)
    actual = os.fstat(directory)
    if (visible.st_dev, visible.st_ino) != (actual.st_dev, actual.st_ino):
        raise ValueError


def read_envelope(
    *,
    publication_root: TrustedPublicationRoot,
    publication_id: str,
    expected: ExpectedEnvelopeReference,
) -> EnvelopeVerification:
    """Read anchored bytes only; never create, recover or infer publisher return."""
    reference = _checked(
        ExpectedEnvelopeReference,
        expected,
        "invalid_reference",
        limit=MAX_REFERENCE_BYTES,
    )
    name = _publication_id(publication_id)
    root = directory = None
    try:
        binding, root = _publication_root(publication_root)
        directory = os.open(
            name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root
        )
        raw = _read_artifact(directory)
        result = verify_envelope(raw, expected=reference)
        _check_publication_path(binding, root, name, directory)
        os.close(directory)
        directory = None
        os.close(root)
        root = None
        return result
    except EnvelopeError:
        raise
    except BaseException:  # noqa: BLE001 - interruption and external diagnostics stay private
        raise EnvelopeError("artifact_unavailable") from None
    finally:
        for descriptor in (directory, root):
            if descriptor is not None:
                with suppress(OSError):
                    os.close(descriptor)


def _publication_sources(
    root: TrustedPublicationRoot,
    envelope: EvidenceEnvelope,
    store: authority.AuthorityStoreBinding,
    registry: journal.RegistryBinding,
) -> None:
    """Directory metadata/isolation only, never source-content inspection."""
    store = _checked(authority.AuthorityStoreBinding, store, "invalid_input")
    registry = _checked(journal.RegistryBinding, registry, "invalid_input")
    if (
        fingerprint(store.model_dump(mode="json"))
        != envelope.authority.store_binding_sha256
        or store.configuration.store_id != envelope.authority.receipt.store_id
        or fingerprint(registry.model_dump(mode="json"))
        != envelope.journal.registry_binding_sha256
        or registry.registry_id != envelope.journal.registry_id
    ):
        raise EnvelopeError("binding_mismatch")
    publication = Path(root.path)
    publication_identity = (root.device, root.directory_inode)
    sources = (
        (
            _absolute(store.configuration.store_path),
            (store.device, store.directory_inode),
        ),
        (_absolute(registry.path), (registry.device, registry.inode)),
    )
    # Actual ancestry catches local case/Unicode aliases without namespace discovery.
    descriptor = _directory(
        publication,
        publication_identity,
        forbidden=frozenset(identity for _, identity in sources),
    )
    os.close(descriptor)
    for path, identity in sources:
        if path.is_relative_to(publication) or publication.is_relative_to(path):
            raise EnvelopeError("unsafe_destination")
        descriptor = _directory(
            path, identity, forbidden=frozenset({publication_identity})
        )
        try:
            _private(os.fstat(descriptor), directory=True)
        finally:
            os.close(descriptor)


def publish_envelope(
    envelope: EvidenceEnvelope,
    *,
    publication_root: TrustedPublicationRoot,
    publication_id: str,
    store: authority.AuthorityStoreBinding,
    registry: journal.RegistryBinding,
) -> PublicationReceipt:
    """Exclusive local publication only; no proof of inspection or custody.

    Caller excludes repositories/historical namespaces when provisioning the root.
    Preserve every partial destination. No automatic retry, overwrite or cleanup.
    A visible artifact can outlive a failed call; reopening cannot prove return.
    """
    root = directory = output = None
    creation_attempted = created = link_attempted = False
    try:
        raw = serialize_envelope(envelope)
        checked = parse_envelope(raw)
        candidate = _reference_candidate(checked)
        name = _publication_id(publication_id)
        binding, root = _publication_root(publication_root)
        _publication_sources(binding, checked, store, registry)
        creation_attempted = True
        try:
            os.mkdir(name, mode=0o700, dir_fd=root)
        except FileExistsError:
            creation_attempted = False
            raise EnvelopeError("destination_exists") from None
        created = True
        os.fsync(root)
        directory = os.open(
            name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root
        )
        _private(os.fstat(directory), directory=True)
        output = os.open(
            ".pending-envelope",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        _private(os.fstat(output))
        # Unbuffered write: no userspace buffer to flush; a short write is failure.
        if os.write(output, raw) != len(raw):
            raise OSError
        os.fsync(output)
        link_attempted = True
        os.link(
            ".pending-envelope",
            "envelope.json",
            src_dir_fd=directory,
            dst_dir_fd=directory,
            follow_symlinks=False,
        )
        os.fsync(directory)
        os.unlink(".pending-envelope", dir_fd=directory)
        os.fsync(output)
        os.fsync(directory)
        if _read_artifact(directory) != raw:
            raise ValueError
        visible = os.stat("envelope.json", dir_fd=directory, follow_symlinks=False)
        retained = os.fstat(output)
        _private(retained)
        if _file_identity(visible) != _file_identity(retained):
            raise ValueError
        _check_publication_path(binding, root, name, directory)
        os.close(output)
        output = None
        os.close(directory)
        directory = None
        os.close(root)
        root = None
        return PublicationReceipt(
            publication_id=name,
            bytes_written=len(raw),
            reference_candidate=candidate,
        )
    except BaseException as error:
        if creation_attempted:
            raise EnvelopeError(
                "publication_outcome_unknown"
                if link_attempted or not created
                else "publication_failed"
            ) from None
        if isinstance(error, EnvelopeError):
            raise error from None
        raise EnvelopeError("unsafe_destination") from None
    finally:
        for descriptor in (output, directory, root):
            if descriptor is not None:
                with suppress(OSError):
                    os.close(descriptor)
