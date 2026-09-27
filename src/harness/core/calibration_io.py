"""Exclusive, checksummed calibration bundles. No database/client access here."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from harness.core.calibration import (
    AnnotationDraft,
    BlindPacket,
    CalibrationExample,
    CalibrationManifest,
    CalibrationResult,
    Frozen,
    FrozenAnnotationSet,
    HumanAnnotation,
    IssueComparison,
    JudgeObservationSet,
    blind_packet,
)
from harness.core.fingerprints import canonical_json


class CalibrationIOError(ValueError):
    """Safe diagnostic without evaluation text or absolute filesystem paths."""


def byte_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def decode[M: Frozen](
    raw: bytes, model: type[M], *, label: str, line: int | None = None
) -> M:
    try:
        data = json.loads(raw, object_pairs_hook=_pairs)
        # JSON validation handles tuple/datetime conversions while strict numeric
        # and bool fields still reject string coercion.
        return model.model_validate_json(canonical_json(data))
    except (ValueError, TypeError, UnicodeError, ValidationError):
        where = f" line {line}" if line is not None else ""
        raise CalibrationIOError(
            f"Invalid {label}{where}; check schema and bindings"
        ) from None


def read_model[M: Frozen](path: Path, model: type[M], label: str) -> M:
    try:
        return decode(path.read_bytes(), model, label=label)
    except OSError:
        raise CalibrationIOError(f"Cannot read {label}") from None


def read_jsonl[M: Frozen](raw: bytes, model: type[M], label: str) -> tuple[M, ...]:
    return tuple(
        decode(line, model, label=label, line=index)
        for index, line in enumerate(raw.splitlines(), 1)
        if line.strip()
    )


def _write(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)


def _json(value: Frozen) -> bytes:
    return (canonical_json(value.model_dump(mode="json")) + "\n").encode()


def _new_directory(path: Path) -> None:
    # mkdir(exist_ok=False) also refuses existing symlinks and source aliases.
    path.mkdir(parents=True, exist_ok=False)


def export_bundle(
    manifest: CalibrationManifest, destination: Path, *, annotator_id: str
) -> BlindPacket:
    from harness.reporting.calibration import render_packet

    manifest = CalibrationManifest.model_validate_json(manifest.model_dump_json())
    packet = blind_packet(manifest)
    drafts = tuple(
        AnnotationDraft(
            set_id=manifest.set_id,
            example_id=item.example_id,
            packet_hash=packet.digest,
            binding_hash=item.binding_hash,
            annotator_id=annotator_id,
        )
        for item in packet.items
    )
    _new_directory(destination)
    private, review = destination / "private", destination / "review"
    private.mkdir()
    review.mkdir()
    _write(private / "manifest.json", _json(manifest))
    _write(review / "packet.json", _json(packet))
    _write(review / "packet.md", render_packet(packet).encode())
    _write(review / "draft.jsonl", b"".join(_json(d) for d in drafts))
    return packet


def load_export(path: Path) -> tuple[CalibrationManifest, BlindPacket]:
    manifest = read_model(
        path / "private/manifest.json", CalibrationManifest, "manifest.json"
    )
    packet = read_model(path / "review/packet.json", BlindPacket, "packet.json")
    if packet != blind_packet(manifest):
        raise CalibrationIOError("Packet differs from manifest")
    from harness.reporting.calibration import render_packet

    if (path / "review/packet.md").read_bytes() != render_packet(packet).encode():
        raise CalibrationIOError("Review Markdown differs from frozen packet")
    return manifest, packet


def freeze_bundle(
    export: Path,
    draft_path: Path,
    destination: Path,
    *,
    partial: bool = False,
    previous: Path | None = None,
) -> FrozenAnnotationSet:
    manifest, packet = load_export(export)
    raw = draft_path.read_bytes()
    drafts = read_jsonl(raw, AnnotationDraft, "draft.jsonl")
    if not drafts:
        raise CalibrationIOError("No human-authored annotations")
    if len({d.annotator_id for d in drafts}) != 1 or len(
        {d.example_id for d in drafts}
    ) != len(drafts):
        raise CalibrationIOError("Duplicate examples or multiple annotators")
    history: tuple[HumanAnnotation, ...] = ()
    active: dict[str, HumanAnnotation] = {}
    previous_hash = None
    if previous is not None:
        old_manifest, old = load_frozen(previous)
        if old_manifest != manifest or old.annotator_id != drafts[0].annotator_id:
            raise CalibrationIOError("Correction changes manifest or annotator")
        history = old.annotations
        active = {a.example_id: a for a in history if a.annotation_id in old.active_ids}
        previous_hash = old.digest
    additions = []
    line_numbers = [i for i, line in enumerate(raw.splitlines(), 1) if line.strip()]
    for index, draft in zip(line_numbers, drafts):
        try:
            if draft.example_id not in manifest.presentation_order:
                raise ValueError("Unknown example")
            example = manifest.example(draft.example_id)
            if (draft.set_id, draft.packet_hash, draft.binding_hash) != (
                manifest.set_id,
                packet.digest,
                example.binding_hash,
            ):
                raise ValueError("Draft binding differs")
            if draft.score is None:
                raise ValueError("Incomplete human score")
            old_annotation = active.get(draft.example_id)
            if draft.supersedes != (
                old_annotation.annotation_id if old_annotation else None
            ):
                raise ValueError("Correction must explicitly supersede active ID")
            annotation = HumanAnnotation(
                **draft.model_dump(exclude={"schema_version"}),
                contract=manifest.contract,
                contract_hash=manifest.contract.digest,
                passed=manifest.contract.passed(draft.score),
                post_disclosure=previous is not None,
            )
            additions.append(annotation)
            active[draft.example_id] = annotation
        except (ValueError, TypeError):
            raise CalibrationIOError(
                f"Invalid draft.jsonl line {index}; incomplete rating, contract or binding mismatch"
            ) from None
    frozen = FrozenAnnotationSet(
        manifest_hash=manifest.digest,
        packet_hash=packet.digest,
        draft_hash=byte_hash(raw),
        annotator_id=drafts[0].annotator_id,
        annotations=history + tuple(additions),
        active_ids=tuple(
            active[i].annotation_id for i in manifest.presentation_order if i in active
        ),
        missing_ids=tuple(i for i in manifest.presentation_order if i not in active),
        partial=partial,
        previous_receipt_hash=previous_hash,
    )
    frozen.verify_manifest(manifest)
    _new_directory(destination)
    files = {
        "manifest.json": _json(manifest),
        "packet.json": _json(packet),
        "draft.jsonl": raw,
        "annotations.jsonl": b"".join(_json(a) for a in frozen.annotations),
        "frozen.json": _json(frozen),
    }
    for name, data in files.items():
        _write(destination / name, data)
    # Re-read everything before publishing the final completeness marker.
    checksums = {name: byte_hash(data) for name, data in files.items()}
    if any(
        byte_hash((destination / name).read_bytes()) != digest
        for name, digest in checksums.items()
    ):
        raise CalibrationIOError("Freeze write verification failed")
    receipt = {
        "schema_version": "calibration-receipt-v1",
        "revision_hash": frozen.digest,
        "files": checksums,
    }
    _write(destination / "receipt.json", (canonical_json(receipt) + "\n").encode())
    load_frozen(destination)
    return frozen


def load_frozen(path: Path) -> tuple[CalibrationManifest, FrozenAnnotationSet]:
    try:
        receipt = json.loads(
            (path / "receipt.json").read_bytes(), object_pairs_hook=_pairs
        )
        names = {
            "manifest.json",
            "packet.json",
            "draft.jsonl",
            "annotations.jsonl",
            "frozen.json",
        }
        if (
            set(receipt) != {"schema_version", "revision_hash", "files"}
            or receipt["schema_version"] != "calibration-receipt-v1"
            or set(receipt["files"]) != names
        ):
            raise ValueError("Invalid receipt")
        raw = {name: (path / name).read_bytes() for name in names}
        if any(byte_hash(raw[name]) != receipt["files"][name] for name in names):
            raise ValueError("Bundle checksum differs")
        manifest = decode(
            raw["manifest.json"], CalibrationManifest, label="manifest.json"
        )
        packet = decode(raw["packet.json"], BlindPacket, label="packet.json")
        frozen = decode(raw["frozen.json"], FrozenAnnotationSet, label="frozen.json")
        annotations = read_jsonl(
            raw["annotations.jsonl"], HumanAnnotation, "annotations.jsonl"
        )
        if (
            frozen.digest != receipt["revision_hash"]
            or frozen.annotations != annotations
            or frozen.draft_hash != byte_hash(raw["draft.jsonl"])
            or packet != blind_packet(manifest)
        ):
            raise ValueError("Frozen identity differs")
        frozen.verify_manifest(manifest)
        return manifest, frozen
    except (OSError, ValueError, TypeError, KeyError):
        raise CalibrationIOError(
            "Missing, incomplete or altered freeze bundle; judge loading prohibited"
        ) from None


def analyze_bundle(
    frozen_path: Path,
    load_judges: Callable[[CalibrationExample], JudgeObservationSet | None],
    *,
    issues: tuple[IssueComparison, ...] = (),
) -> CalibrationResult:
    # This ordering is an API boundary and covered by bomb-loader tests.
    manifest, frozen = load_frozen(frozen_path)
    observations = tuple(
        j for e in manifest.examples if (j := load_judges(e)) is not None
    )
    return CalibrationResult(
        manifest=manifest, frozen=frozen, observations=observations, issues=issues
    )


def save_result(result: CalibrationResult, destination: Path) -> None:
    from harness.reporting.calibration import render_appendix, render_report

    result = CalibrationResult.model_validate_json(result.model_dump_json())
    _new_directory(destination)
    _write(
        destination / "result.json",
        (
            canonical_json(
                {"result": result.model_dump(mode="json"), "summary": result.summary}
            )
            + "\n"
        ).encode(),
    )
    _write(destination / "report.md", render_report(result).encode())
    _write(destination / "analyst_appendix.md", render_appendix(result).encode())
    load_result(destination)


def load_result(path: Path) -> CalibrationResult:
    from harness.reporting.calibration import (
        render_appendix,
        render_legacy_report,
        render_report,
    )

    try:
        raw = json.loads((path / "result.json").read_bytes(), object_pairs_hook=_pairs)
        if set(raw) != {"result", "summary"}:
            raise ValueError("Invalid report envelope")
        result = CalibrationResult.model_validate_json(canonical_json(raw["result"]))
        if canonical_json(result.summary) != canonical_json(raw["summary"]):
            raise ValueError("Derived summary differs")
        report = (path / "report.md").read_bytes()
        appendix = path / "analyst_appendix.md"
        if appendix.exists():
            if (
                report != render_report(result).encode()
                or appendix.read_bytes() != render_appendix(result).encode()
            ):
                raise ValueError("Derived reports differ")
        elif report != render_legacy_report(result).encode():
            raise ValueError("Missing appendix or altered legacy report")
        return result
    except (OSError, ValueError, TypeError, KeyError):
        raise CalibrationIOError("Incomplete or altered analysis result") from None


def refresh_reports(path: Path) -> None:
    """Explicit presentation-only refresh; never serialize result.json again.

    Validate the existing legacy/current bundle first and stage both rendered
    documents before replacing either. Each replacement is atomic. An interrupted
    pair is detected by load_result, just like an interrupted initial save.
    """
    from harness.reporting.calibration import render_appendix, render_report

    result = load_result(path)
    staged: list[tuple[Path, Path]] = []
    try:
        for name, content in (
            ("report.md", render_report(result)),
            ("analyst_appendix.md", render_appendix(result)),
        ):
            with tempfile.NamedTemporaryFile(
                dir=path, prefix=".calibration-render-", delete=False
            ) as stream:
                temporary = Path(stream.name)
                staged.append((temporary, path / name))
                stream.write(content.encode())
            if temporary.read_bytes() != content.encode():
                raise CalibrationIOError("Report staging verification failed")
        for temporary, destination in staged:
            os.replace(temporary, destination)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
    load_result(path)
