"""Private deterministic review packets from an anchored captured journal snapshot.

No authority-store inspection, approval authentication, provider, judge or execution.
Public inspectors remain unbounded internally; trust bounded protected local stores.
"""

from __future__ import annotations

import json
import os
import re
import stat
from contextlib import suppress
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from harness.canary import envelope_v3 as envelope
from harness.canary import human_review_v3 as review
from harness.canary import journal_v3 as journal
from harness.canary.runtime_v3 import Digest, Frozen
from harness.canary.selection_v3 import TURNS
from harness.core.fingerprints import canonical_json, fingerprint

MAX_PACKET_BYTES = 16 * 1024 * 1024
MAX_PRESENTATION_BYTES = 64 * 1024 * 1024


class RecordReference(Frozen):
    sequence: int = Field(ge=0, lt=envelope.MAX_JOURNAL_RECORDS)
    kind: review.Identifier
    record_sha256: Digest


class PacketItem(Frozen):
    item_id: review.Identifier
    source: RecordReference
    content_json: str = Field(repr=False)

    @model_validator(mode="after")
    def _canonical(self) -> PacketItem:
        review.decode(self.content_json.encode(), MAX_PACKET_BYTES)
        return self


class PacketTurn(Frozen):
    """A turn and earlier slots in the packet's chronological review order.

    ``prior_slots`` is the full ORDER prefix, including the other conversation.
    It exposes earlier evidence for leakage review; it grants no conversational
    context. Same-conversation predecessors are only the prefix entries whose
    first character equals ``conversation``: (), (), (A1,), (B1,).
    """

    slot: review.Slot
    conversation: Literal["A", "B"]
    shopper_message: str = Field(repr=False)
    prior_slots: tuple[review.Slot, ...]
    items: tuple[PacketItem, ...]
    assessment_revisions: tuple[int, ...]
    outcome_assessment_revision: int = Field(ge=0)

    @model_validator(mode="after")
    def _consistent(self) -> PacketTurn:
        identifiers = tuple(item.item_id for item in self.items)
        if (
            self.conversation != self.slot[0]
            or self.prior_slots != review.ORDER[: review.ORDER.index(self.slot)]
            or len(set(identifiers)) != len(identifiers)
            or not {"chat", "trace", "outcome"}.issubset(identifiers)
            or self.assessment_revisions != tuple(range(len(self.assessment_revisions)))
            or not self.assessment_revisions
            or self.outcome_assessment_revision != self.assessment_revisions[-1]
        ):
            raise ValueError("invalid_turn_packet")
        if tuple(i for i in identifiers if i.startswith("assessment-")) != tuple(
            f"assessment-{n:06d}" for n in self.assessment_revisions
        ):
            raise ValueError("assessment_revisions_differ")
        return self


class RecordedAssessments(Frozen):
    mechanical: review.QualityCheck
    operational: review.QualityCheck
    historical_overall: review.QualityCheck


class ReviewPacket(Frozen):
    schema_id: Literal["canary-private-review-packet-v1"] = (
        "canary-private-review-packet-v1"
    )
    canonicalization: Literal["replay-canonical-json-v1"] = "replay-canonical-json-v1"
    packet_profile: Literal["canary-review-packet-v1"] = review.PACKET_PROFILE
    presentation_profile: Literal["canary-review-inert-text-v1"] = (
        review.PRESENTATION_PROFILE
    )
    source_verification_profile: Literal["anchored-envelope-current-journal-v1"] = (
        review.SOURCE_PROFILE
    )
    subject: review.ReviewSubject
    rubric: review.ReviewRubric
    turns: tuple[PacketTurn, ...]
    assessments: RecordedAssessments
    completion: envelope.RecordedExecution
    authority_consumption_evidence: Literal["recorded-in-anchored-envelope-only"] = (
        "recorded-in-anchored-envelope-only"
    )
    fresh_authority_store_inspection: Literal["not-performed"] = "not-performed"
    fresh_approval_signature_authentication: Literal["not-performed"] = "not-performed"
    assurance: review.Assurance = Field(default_factory=review.Assurance)

    @model_validator(mode="after")
    def _consistent(self) -> ReviewPacket:
        if (
            tuple(t.slot for t in self.turns) != review.ORDER
            or self.rubric != review.review_rubric()
            or self.completion.journal_status != "completed"
            or not self.completion.journal_completion_certified
            or self.assessments.operational.status != "PASS"
            or self.assessments.mechanical.status == "ERROR"
        ):
            raise ValueError("ineligible_packet")
        for check, status in (
            (self.assessments.mechanical, self.completion.mechanical_assessment_status),
            (
                self.assessments.operational,
                self.completion.operational_assessment_status,
            ),
            (
                self.assessments.historical_overall,
                self.completion.overall_assessment_status,
            ),
        ):
            if check.status != status:
                raise ValueError("assessment_status_differs")
        return self


class PacketMaterial(Frozen):
    packet: ReviewPacket = Field(repr=False)
    packet_commitment_sha256: Digest
    presentation_sha256: Digest
    presentation: bytes = Field(repr=False)


class ProtectedRoot(Frozen):
    path: str
    device: int = Field(ge=0)
    directory_inode: int = Field(ge=1)

    @model_validator(mode="after")
    def _path(self) -> ProtectedRoot:
        absolute(self.path)
        return self


class PacketPublicationRoot(ProtectedRoot):
    schema_id: Literal["canary-review-packet-root-v1"] = "canary-review-packet-root-v1"


class PacketPublicationResult(Frozen):
    publication_id: review.Identifier
    packet_commitment_sha256: Digest
    presentation_sha256: Digest
    publication_status: Literal["local-publication-protocol-completed"] = (
        "local-publication-protocol-completed"
    )
    independent_custody: Literal["not-established-by-publisher"] = (
        "not-established-by-publisher"
    )


def serialize_packet(packet: ReviewPacket) -> bytes:
    value = review.checked(ReviewPacket, packet, "invalid_packet", MAX_PACKET_BYTES)
    _semantic_budget(value)
    return review.encode(value, MAX_PACKET_BYTES)


def parse_packet(raw: bytes) -> ReviewPacket:
    value = review.parse(ReviewPacket, raw, "invalid_packet", MAX_PACKET_BYTES)
    _semantic_budget(value)
    return value


def _semantic_budget(packet: ReviewPacket) -> None:
    # Frozen canonical strings must not hide a larger logical evidence tree.
    value = packet.model_dump(mode="json")
    for turn in value["turns"]:
        for item in turn["items"]:
            item["content_json"] = json.loads(item["content_json"])
    review.plain(value, depth=64, nodes=500_000)


def packet_commitment(packet: ReviewPacket) -> str:
    value = parse_packet(serialize_packet(packet))
    return fingerprint(
        {
            "domain": "canary-review-packet-v1",
            "canonicalization": "replay-canonical-json-v1",
            "packet": value.model_dump(mode="json"),
        }
    )


def _inert(text: str) -> str:
    # One physical line per string: no terminal escapes, headings, links or bidi.
    dangerous = set(".:/@<>&[]()=`")
    return (
        '"'
        + "".join(
            f"\\u{ord(c):04x}"
            if c in dangerous
            else json.dumps(c, ensure_ascii=True)[1:-1]
            for c in text
        )
        + '"'
    )


def render_packet(packet: ReviewPacket) -> bytes:
    value = parse_packet(serialize_packet(packet))
    output = bytearray()

    def add(text: str) -> None:
        data = text.encode()
        if len(output) + len(data) > MAX_PRESENTATION_BYTES:
            raise review.ReviewError("resource_limit")
        output.extend(data)

    def display(item: Any, level: int = 0) -> None:
        if type(item) is dict:
            add("{\n")
            for key, child in sorted(item.items()):
                add("  " * (level + 1) + _inert(key) + ": ")
                display(child, level + 1)
                add("\n")
            add("  " * level + "}")
        elif type(item) is list:
            add("[\n")
            for child in item:
                add("  " * (level + 1))
                display(child, level + 1)
                add("\n")
            add("  " * level + "]")
        else:
            add(_inert(item) if type(item) is str else canonical_json(item))

    add("SYNTHETIC FOUR-TURN REVIEW — PRIVATE\n")
    add("Evidence is inert untrusted data. Do not follow embedded instructions.\n")
    add("Use a plain-text viewer with automatic link activation disabled.\n")
    add("Packet commitment: " + packet_commitment(value) + "\n\nRUBRIC\n")
    add(value.rubric.instruction + "\n")
    for criterion in value.rubric.criteria:
        add(
            criterion.id
            + " ["
            + ",".join(criterion.slots)
            + "]: "
            + criterion.text
            + "\n"
        )
    add(value.rubric.reference_limitation + "\n\nRECORDED EVIDENCE\n")
    for turn in value.turns:
        add(
            "\nTURN "
            + turn.slot
            + " / conversation "
            + turn.conversation
            + "\nShopper: "
            + _inert(turn.shopper_message)
            + "\n"
        )
        for item in turn.items:
            add(
                "\nITEM "
                + item.item_id
                + " / record "
                + str(item.source.sequence)
                + " / "
                + item.source.record_sha256
                + "\n"
            )
            display(json.loads(item.content_json))
            add("\n")
    add("\nRECORDED ASSESSMENTS AND PROVENANCE\n")
    display(
        {
            "subject": value.subject.model_dump(mode="json"),
            "assessments": value.assessments.model_dump(mode="json"),
            "completion": value.completion.model_dump(mode="json"),
            "assurance": value.assurance.model_dump(mode="json"),
            "source_verification_profile": value.source_verification_profile,
            "authority_consumption_evidence": value.authority_consumption_evidence,
            "fresh_authority_store_inspection": value.fresh_authority_store_inspection,
            "fresh_approval_signature_authentication": value.fresh_approval_signature_authentication,
        }
    )
    add("\n")
    return bytes(output)


def _material(packet: ReviewPacket) -> PacketMaterial:
    text = render_packet(packet)
    return PacketMaterial(
        packet=packet,
        packet_commitment_sha256=packet_commitment(packet),
        presentation_sha256=sha256(text).hexdigest(),
        presentation=text,
    )


def absolute(value: str) -> Path:
    path = Path(value)
    if path.anchor != "/" or str(path) != value or ".." in path.parts:
        raise review.ReviewError("unsafe_storage")
    return path


def directory(
    path: Path,
    expected: tuple[int, int] | None = None,
    forbidden: frozenset[tuple[int, int]] = frozenset(),
) -> int:
    absolute(str(path))
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            previous = fd
            fd = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=previous
            )
            os.close(previous)
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino) in forbidden:
                raise review.ReviewError("unsafe_storage")
        info = os.fstat(fd)
        if expected is not None and (info.st_dev, info.st_ino) != expected:
            raise review.ReviewError("unsafe_storage")
        return fd
    except BaseException:
        os.close(fd)
        raise


def private(info: os.stat_result, *, is_directory: bool = False) -> None:
    if (
        info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != (0o700 if is_directory else 0o600)
        or not (
            stat.S_ISDIR(info.st_mode) if is_directory else stat.S_ISREG(info.st_mode)
        )
        or (not is_directory and info.st_nlink != 1)
    ):
        raise review.ReviewError("unsafe_storage")


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_file(root: int, name: str, limit: int, *, inode: int | None = None) -> bytes:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        private(before)
        if inode is not None and before.st_ino != inode:
            raise review.ReviewError("unsafe_storage")
        if before.st_size > limit:
            raise review.ReviewError("resource_limit")
        raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise review.ReviewError("resource_limit")
        after = os.fstat(stream.fileno())
        visible = os.stat(name, dir_fd=root, follow_symlinks=False)
        private(after)
        private(visible)
        if _identity(before) != _identity(after) or _identity(after) != _identity(
            visible
        ):
            raise review.ReviewError("unsafe_storage")
        return raw


def check_protection(path: Path, protected_roots: tuple[ProtectedRoot, ...]) -> None:
    absolute(str(path))
    if not protected_roots or any(
        (p / ".git").exists()
        or p.name in {"salesagent-study-v1", "salesagent-preflight-canary"}
        for p in (path, *path.parents)
    ):
        raise review.ReviewError("unsafe_storage")
    parent = path if path.exists() else path.parent
    identities = frozenset((r.device, r.directory_inode) for r in protected_roots)
    fd = directory(parent, forbidden=identities)
    observed = os.fstat(fd)
    os.close(fd)
    for supplied in protected_roots:
        root = review.checked(
            ProtectedRoot, supplied, "unsafe_storage", review.MAX_SMALL_BYTES
        )
        if path.is_relative_to(root.path) or Path(root.path).is_relative_to(path):
            raise review.ReviewError("unsafe_storage")
        fd = directory(
            Path(root.path),
            (root.device, root.directory_inode),
            frozenset({(observed.st_dev, observed.st_ino)})
            if parent == path
            else frozenset(),
        )
        os.close(fd)


def _preflight(registry: journal.RegistryBinding, run_id: str) -> None:
    fd = directory(absolute(registry.path), (registry.device, registry.inode))
    try:
        private(os.fstat(fd), is_directory=True)
        for name in ("runs", run_id, "records"):
            previous = fd
            fd = os.open(
                name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=previous
            )
            os.close(previous)
            private(os.fstat(fd), is_directory=True)
        count = total = 0
        with os.scandir(fd) as entries:
            for entry in entries:
                count += 1
                if count > envelope.MAX_JOURNAL_RECORDS:
                    raise review.ReviewError("resource_limit")
                if re.fullmatch(r"[0-9]{6}\.json", entry.name) is None:
                    raise review.ReviewError("source_ineligible")
                info = entry.stat(follow_symlinks=False)
                private(info)
                total += info.st_size
                if (
                    info.st_size > envelope.MAX_RECORD_BYTES
                    or total > envelope.MAX_JOURNAL_BYTES
                ):
                    raise review.ReviewError("resource_limit")
    finally:
        os.close(fd)


def _subject(
    value: envelope.EvidenceEnvelope, expected: envelope.ExpectedEnvelopeReference
) -> review.ReviewSubject:
    return review.ReviewSubject(
        expected_envelope=expected,
        source_receipt_sha256=value.source.receipt_sha256,
        roster_fingerprint=value.source.roster_fingerprint,
        definition_fingerprint=value.source.definition_fingerprint,
        acceptance_policy=value.source.acceptance_policy,
        acceptance_fingerprint=value.source.acceptance_fingerprint,
        execution_policy=value.source.execution_policy,
        execution_fingerprint=value.source.execution_fingerprint,
        journal_history_commitment_sha256=value.journal.history_commitment_sha256,
        evidence_sha256=value.journal.evidence_sha256,
    )


def _item(record: dict[str, Any], item_id: str, content: Any) -> PacketItem:
    raw = review.encode(content, MAX_PACKET_BYTES)
    return PacketItem(
        item_id=item_id,
        source=RecordReference(
            sequence=record["sequence"],
            kind=record["kind"],
            record_sha256=fingerprint(record),
        ),
        content_json=raw.decode(),
    )


def _turn(slot: review.Slot, records: list[dict[str, Any]]) -> PacketTurn:
    selected = [r for r in records if r["payload"].get("slot") == slot]
    chats = [r for r in selected if r["kind"] == "chat"]
    traces = [r for r in selected if r["kind"] == "trace"]
    outcomes = [r for r in selected if r["kind"] == "outcome"]
    assessments = [r for r in selected if r["kind"] == "assessment"]
    if len(chats) != 1 or len(traces) != 1 or len(outcomes) != 1 or not assessments:
        raise review.ReviewError("source_ineligible")
    chat = chats[0]["payload"]["chat"]
    trace = traces[0]["payload"]["trace"]
    message = next(t.message for t in TURNS if t.slot == slot)
    if (
        trace["user_message"] != message
        or chat["session_id"] != trace["session_id"]
        or chat["trace_id"] != trace["trace_id"]
    ):
        raise review.ReviewError("source_ineligible")
    projected_chat = {
        name: chat[name]
        for name in ("message", "recommendations", "promotion", "pricing")
    }
    projected_trace = {
        name: trace[name]
        for name in (
            "turn_index",
            "resolved_constraints",
            "constraint_changes",
            "recommendation_validation",
            "recommended_product_ids",
            "promotion",
            "pricing",
        )
    }
    projected_trace["tool_calls"] = [
        {
            name: call[name]
            for name in ("sequence", "tool_name", "arguments", "result", "status")
        }
        for call in trace["tool_calls"]
    ]
    items = (
        _item(chats[0], "chat", projected_chat),
        _item(traces[0], "trace", projected_trace),
        *(
            _item(r, f"assessment-{r['payload']['revision']:06d}", r["payload"])
            for r in assessments
        ),
        _item(outcomes[0], "outcome", outcomes[0]["payload"]),
    )
    return PacketTurn(
        slot=slot,
        conversation="A" if slot[0] == "A" else "B",
        shopper_message=message,
        prior_slots=review.ORDER[: review.ORDER.index(slot)],
        items=items,
        assessment_revisions=tuple(r["payload"]["revision"] for r in assessments),
        outcome_assessment_revision=outcomes[0]["payload"]["assessment_revision"],
    )


def acquire_packet(
    envelope_raw: bytes,
    *,
    expected: envelope.ExpectedEnvelopeReference,
    registry: journal.RegistryBinding,
) -> PacketMaterial:
    """Anchor, inspect once, commit that captured snapshot, then project only it."""
    try:
        envelope.verify_envelope(envelope_raw, expected=expected)
        value = envelope.parse_envelope(envelope_raw)
        reference = review.checked(
            envelope.ExpectedEnvelopeReference,
            expected,
            "invalid_reference",
            envelope.MAX_REFERENCE_BYTES,
        )
        binding = review.checked(
            journal.RegistryBinding,
            registry,
            "invalid_reference",
            review.MAX_SMALL_BYTES,
        )
        if (
            binding.registry_id != reference.registry_id
            or fingerprint(binding.model_dump(mode="json"))
            != reference.registry_binding_sha256
        ):
            raise review.ReviewError("source_mismatch")
        _preflight(binding, reference.run_id)
        report = journal.inspect_run(binding, reference.run_id)
        records = review.decode(
            review.encode(report["records"], envelope.MAX_JOURNAL_BYTES),
            envelope.MAX_JOURNAL_BYTES,
        )
        if (
            type(records) is not list
            or not 1 <= len(records) <= envelope.MAX_JOURNAL_RECORDS
        ):
            raise review.ReviewError("source_ineligible")
        history = fingerprint(
            {
                "domain": "canary-detached-journal-history-v1",
                "canonicalization": "replay-canonical-json-v1",
                "journal_schema": journal.SCHEMA,
                "registry_id": binding.registry_id,
                "run_id": reference.run_id,
                "records": records,
            }
        )
        if (
            history != value.journal.history_commitment_sha256
            or len(records) != value.journal.validated_records
            or report["evidence_sha256"] != value.journal.evidence_sha256
        ):
            raise review.ReviewError("source_mismatch")
        if (
            report["schema_id"] != journal.SCHEMA
            or report["run_id"] != reference.run_id
            or report["structurally_validated"] is not True
            or report["issues"]
            or report["pending_files"]
            or report["status"] != "completed"
            or report["completion_certified"] is not True
            or report["completion_acknowledged"] is not True
            or report["accounting_reconciled"] is not True
            or report["execution_action"] != "COMPLETE"
            or report["persisted_records"] != len(records)
            or report["validated_prefix_records"] != len(records)
            or report["operational_assessment"]["status"] != "PASS"
            or report["mechanical_assessment"]["status"] == "ERROR"
            or any(
                report["accounting"][n]
                for n in ("unknown_attempts", "incomplete_calls", "operational_errors")
            )
            or not report["safe_shutdown_observation"]
            or not all(v is True for v in report["safe_shutdown_observation"].values())
        ):
            raise review.ReviewError("source_ineligible")
        if (
            value.execution.journal_status != "completed"
            or not value.execution.journal_completion_certified
            or report["accounting"] != value.accounting.model_dump(mode="json")
        ):
            raise review.ReviewError("source_mismatch")
        manifest = records[0]["payload"]
        if (
            records[0]["kind"] != "manifest"
            or manifest["run_id"] != reference.run_id
            or manifest["approval_id"] != reference.authorisation_id
            or manifest["registry"] != binding.model_dump(mode="json")
            or fingerprint(manifest["source_receipt"]) != value.source.receipt_sha256
        ):
            raise review.ReviewError("source_mismatch")
        traces = {
            r["payload"]["slot"]: r["payload"]["trace"]
            for r in records
            if r["kind"] == "trace"
        }
        if (
            set(traces) != set(review.ORDER)
            or len({t["trace_id"] for t in traces.values()}) != 4
            or traces["A1"]["session_id"] != traces["A2"]["session_id"]
            or traces["B1"]["session_id"] != traces["B2"]["session_id"]
            or traces["A1"]["session_id"] == traces["B1"]["session_id"]
        ):
            raise review.ReviewError("source_ineligible")
        packet = ReviewPacket(
            subject=_subject(value, reference),
            rubric=review.review_rubric(),
            turns=tuple(_turn(slot, records) for slot in review.ORDER),
            assessments=RecordedAssessments(
                mechanical=review.QualityCheck.model_validate_json(
                    review.encode(report["mechanical_assessment"])
                ),
                operational=review.QualityCheck.model_validate_json(
                    review.encode(report["operational_assessment"])
                ),
                historical_overall=review.QualityCheck.model_validate_json(
                    review.encode(report["assessment"])
                ),
            ),
            completion=value.execution,
        )
        return _material(packet)
    except review.ReviewError:
        raise
    except envelope.EnvelopeError:
        raise review.ReviewError("source_mismatch") from None
    except Exception:  # noqa: BLE001 - fixed privacy-safe boundary
        raise review.ReviewError("source_unavailable") from None


def verify_assignment_packet(
    material: PacketMaterial, expected: review.ReviewAssignment
) -> None:
    assignment = review.checked(
        review.ReviewAssignment, expected, "invalid_assignment", review.MAX_SMALL_BYTES
    )
    rebuilt = _material(parse_packet(serialize_packet(material.packet)))
    if (
        rebuilt.packet.subject != assignment.subject
        or rebuilt.packet_commitment_sha256 != assignment.packet_commitment_sha256
        or rebuilt.presentation_sha256 != assignment.presentation_sha256
        or material.presentation != rebuilt.presentation
        or material.packet_commitment_sha256 != rebuilt.packet_commitment_sha256
        or material.presentation_sha256 != rebuilt.presentation_sha256
    ):
        raise review.ReviewError("presentation_mismatch")


def validate_references(payload: review.ReviewPayload, packet: ReviewPacket) -> None:
    """Structural pointer resolution only, never semantic support certification."""
    value = review.checked(review.ReviewPayload, payload, "invalid_review")
    checked_packet = parse_packet(serialize_packet(packet))
    items = {
        (turn.slot, item.item_id): json.loads(item.content_json)
        for turn in checked_packet.turns
        for item in turn.items
    }
    refs = (
        *value.references,
        *(r for t in value.turns for c in t.criteria for r in c.references),
    )
    try:
        for ref in refs:
            current = items[(ref.slot, ref.item_id)]
            for token in ref.pointer.split("/")[1:] if ref.pointer else ():
                token = token.replace("~1", "/").replace("~0", "~")
                if type(current) is list:
                    if re.fullmatch(r"0|[1-9][0-9]*", token) is None:
                        raise ValueError
                    current = current[int(token)]
                elif type(current) is dict:
                    current = current[token]
                else:
                    raise ValueError
    except Exception:  # noqa: BLE001 - fixed privacy-safe boundary
        raise review.ReviewError("invalid_reference") from None


def _publication(
    root: PacketPublicationRoot, publication_id: str
) -> tuple[PacketPublicationRoot, int]:
    binding = review.checked(
        PacketPublicationRoot, root, "unsafe_storage", review.MAX_SMALL_BYTES
    )
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", publication_id) is None:
        raise review.ReviewError("unsafe_storage")
    fd = directory(Path(binding.path), (binding.device, binding.directory_inode))
    try:
        private(os.fstat(fd), is_directory=True)
        return binding, fd
    except BaseException:
        os.close(fd)
        raise


def _packet_files(fd: int) -> PacketMaterial:
    private(os.fstat(fd), is_directory=True)
    if set(os.listdir(fd)) != {"packet.json", "packet.txt"}:
        raise review.ReviewError("artifact_unavailable")
    value = parse_packet(read_file(fd, "packet.json", MAX_PACKET_BYTES))
    text = read_file(fd, "packet.txt", MAX_PRESENTATION_BYTES)
    material = _material(value)
    if text != material.presentation or set(os.listdir(fd)) != {
        "packet.json",
        "packet.txt",
    }:
        raise review.ReviewError("presentation_mismatch")
    return material


def _path_check(
    binding: PacketPublicationRoot, root: int, name: str, child: int
) -> None:
    fd = directory(Path(binding.path), (binding.device, binding.directory_inode))
    os.close(fd)
    visible = os.stat(name, dir_fd=root, follow_symlinks=False)
    private(visible, is_directory=True)
    actual = os.fstat(child)
    if (visible.st_dev, visible.st_ino) != (actual.st_dev, actual.st_ino):
        raise review.ReviewError("unsafe_storage")


def publish_packet(
    material: PacketMaterial,
    *,
    root: PacketPublicationRoot,
    publication_id: str,
    protected_roots: tuple[ProtectedRoot, ...],
) -> PacketPublicationResult:
    root_fd = child = None
    attempted = False
    try:
        value = _material(parse_packet(serialize_packet(material.packet)))
        if value != material:
            raise review.ReviewError("invalid_packet")
        binding, root_fd = _publication(root, publication_id)
        check_protection(Path(binding.path), protected_roots)
        attempted = True
        try:
            os.mkdir(publication_id, mode=0o700, dir_fd=root_fd)
        except FileExistsError:
            attempted = False
            raise review.ReviewError("destination_exists") from None
        os.fsync(root_fd)
        child = os.open(
            publication_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd
        )
        fd = os.open(
            ".pending-packet",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=child,
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(b"pending")
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(child)
        for name, raw in (
            ("packet.json", serialize_packet(value.packet)),
            ("packet.txt", value.presentation),
        ):
            fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=child,
            )
            try:
                if os.write(fd, raw) != len(raw):
                    raise OSError
                os.fsync(fd)
            finally:
                os.close(fd)
        os.fsync(child)
        os.unlink(".pending-packet", dir_fd=child)
        os.fsync(child)
        if _packet_files(child) != value:
            raise ValueError
        _path_check(binding, root_fd, publication_id, child)
        os.close(child)
        child = None
        os.close(root_fd)
        root_fd = None
        return PacketPublicationResult(
            publication_id=publication_id,
            packet_commitment_sha256=value.packet_commitment_sha256,
            presentation_sha256=value.presentation_sha256,
        )
    except BaseException as error:
        if attempted:
            raise review.ReviewError("publication_outcome_unknown") from None
        if isinstance(error, review.ReviewError):
            raise
        raise review.ReviewError("publication_failed") from None
    finally:
        for cleanup_fd in (child, root_fd):
            if cleanup_fd is not None:
                with suppress(OSError):
                    os.close(cleanup_fd)


def read_packet(
    *,
    root: PacketPublicationRoot,
    publication_id: str,
    expected_assignment: review.ReviewAssignment,
) -> PacketMaterial:
    root_fd = child = None
    try:
        binding, root_fd = _publication(root, publication_id)
        child = os.open(
            publication_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd
        )
        material = _packet_files(child)
        verify_assignment_packet(material, expected_assignment)
        _path_check(binding, root_fd, publication_id, child)
        os.close(child)
        child = None
        os.close(root_fd)
        root_fd = None
        return material
    except review.ReviewError:
        raise
    except BaseException:  # noqa: BLE001 - interrupted reads never expose evidence
        raise review.ReviewError("artifact_unavailable") from None
    finally:
        for cleanup_fd in (child, root_fd):
            if cleanup_fd is not None:
                with suppress(OSError):
                    os.close(cleanup_fd)
