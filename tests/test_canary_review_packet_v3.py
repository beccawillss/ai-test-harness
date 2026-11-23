"""Persisted synthetic four-turn packets, never Study or a live application."""

from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_canary_envelope_v3 as old
import test_canary_human_review_v3 as contracts

from harness.canary import authority_v3, envelope_v3, journal_v3
from harness.canary import human_review_v3 as review
from harness.canary import review_packet_v3 as packet
from harness.core.fingerprints import canonical_json, fingerprint

keys = old.keys
proposal = old.proposal
manifest = old.manifest
policy = old.policy
signed = old.signed
contract = contracts.contract


def build_source(path, *args, **kwargs):
    path.mkdir(mode=0o700)
    return old.build_linked(path, *args, **kwargs)


@pytest.fixture
def sample(tmp_path, proposal, signed, policy, contract):
    linked = build_source(
        tmp_path / "source", proposal, signed, policy, mode="completed"
    )
    value = old.assemble(linked)
    reference = old.retained_reference(value)
    raw = envelope_v3.serialize_envelope(value)
    material = packet.acquire_packet(raw, expected=reference, registry=linked.registry)
    assignment = contract.assignment.model_copy(
        update={
            "subject": material.packet.subject,
            "packet_commitment_sha256": material.packet_commitment_sha256,
            "presentation_sha256": material.presentation_sha256,
        }
    )
    return SimpleNamespace(
        linked=linked,
        envelope=value,
        raw=raw,
        reference=reference,
        material=material,
        assignment=assignment,
        policy=contract.policy,
    )


def tree(path):
    return {
        str(p.relative_to(path)): (p.read_bytes(), p.stat().st_mode)
        for p in Path(path).rglob("*")
        if p.is_file()
    }


def root_binding(path):
    path.mkdir(mode=0o700)
    info = path.stat()
    return packet.PacketPublicationRoot(
        path=str(path.resolve()), device=info.st_dev, directory_inode=info.st_ino
    )


def protected(path):
    info = Path(path).stat()
    return packet.ProtectedRoot(
        path=str(Path(path).resolve()), device=info.st_dev, directory_inode=info.st_ino
    )


def test_snapshot_projection_readonly_and_exact(sample, monkeypatch):
    before = tree(sample.linked.registry.path)
    monkeypatch.setattr(
        authority_v3,
        "inspect_consumption",
        lambda *a, **k: pytest.fail("authority inspection"),
    )
    monkeypatch.setattr(
        authority_v3,
        "consume_approval",
        lambda *a, **k: pytest.fail("authority consumption"),
    )
    from harness.canary import approval_v3

    monkeypatch.setattr(
        approval_v3,
        "verify_approval",
        lambda *a, **k: pytest.fail("execution approval"),
    )
    material = packet.acquire_packet(
        sample.raw, expected=sample.reference, registry=sample.linked.registry
    )
    assert material == sample.material
    assert tree(sample.linked.registry.path) == before
    assert tuple(t.slot for t in material.packet.turns) == review.ORDER
    assert tuple(t.prior_slots for t in material.packet.turns) == (
        (),
        ("A1",),
        ("A1", "B1"),
        ("A1", "B1", "A2"),
    )
    assert material.packet.assessments.historical_overall.status == "SKIP"
    assert (
        packet.parse_packet(packet.serialize_packet(material.packet)) == material.packet
    )
    assert material.presentation_sha256 == sha256(material.presentation).hexdigest()
    assert material.packet_commitment_sha256 == fingerprint(
        {
            "domain": "canary-review-packet-v1",
            "canonicalization": "replay-canonical-json-v1",
            "packet": material.packet.model_dump(mode="json"),
        }
    )
    assert material.packet.fresh_authority_store_inspection == "not-performed"


@pytest.mark.parametrize(
    ("index", "chronological", "conversation_context"),
    [
        (0, (), ()),
        (1, ("A1",), ()),
        (2, ("A1", "B1"), ("A1",)),
        (3, ("A1", "B1", "A2"), ("B1",)),
    ],
)
def test_prior_slots_are_review_chronology_not_inherited_context(
    sample, index, chronological, conversation_context
):
    turn = sample.material.packet.turns[index]
    assert turn.prior_slots == chronological
    assert tuple(s for s in turn.prior_slots if s[0] == turn.conversation) == (
        conversation_context
    )
    data = turn.model_dump()
    assert packet.PacketTurn.model_validate(data) == turn
    # A chronological reference cannot silently acquire same-conversation meaning.
    if chronological != conversation_context:
        data["prior_slots"] = conversation_context
        with pytest.raises(ValueError, match="invalid_turn_packet"):
            packet.PacketTurn.model_validate(data)


def test_captured_records_are_used_even_if_original_report_changes(sample, monkeypatch):
    original = journal_v3.inspect_run
    original_turn = packet._turn
    observed = []

    def inspect(*args):
        report = original(*args)
        observed.append(report)
        return report

    def turn(slot, records):
        for r in observed[0]["records"]:
            if r["kind"] == "chat":
                r["payload"]["chat"]["message"] = "SUBSTITUTED_UNCHECKED"
        return original_turn(slot, records)

    monkeypatch.setattr(journal_v3, "inspect_run", inspect)
    monkeypatch.setattr(packet, "_turn", turn)
    result = packet.acquire_packet(
        sample.raw, expected=sample.reference, registry=sample.linked.registry
    )
    assert len(observed) == 1
    assert result == sample.material
    assert b"SUBSTITUTED_UNCHECKED" not in result.presentation


@pytest.mark.parametrize(
    "fault", ["suffix", "middle", "bytes", "pending", "reference", "binding"]
)
def test_changed_source_fails_closed_without_repair(sample, fault):
    reference = sample.reference
    binding = sample.linked.registry
    if fault == "suffix":
        max(sample.linked.records.iterdir()).unlink()
    elif fault == "middle":
        sorted(sample.linked.records.iterdir())[2].unlink()
    elif fault == "bytes":
        max(sample.linked.records.iterdir()).write_bytes(b"PRIVATE_CORRUPT_DATA")
    elif fault == "pending":
        marker = sample.linked.records / ".pending-test"
        marker.write_text("pending")
        marker.chmod(0o600)
    elif fault == "reference":
        reference = reference.model_copy(update={"run_id": "synthetic-run-" + "f" * 32})
    else:
        binding = binding.model_copy(update={"registry_id": "f" * 32})
    before = tree(sample.linked.registry.path)
    with pytest.raises(review.ReviewError) as caught:
        packet.acquire_packet(sample.raw, expected=reference, registry=binding)
    assert "PRIVATE" not in str(caught.value)
    assert tree(sample.linked.registry.path) == before


@pytest.mark.parametrize("mode", ["incomplete", "uncertain", "unacknowledged"])
def test_ineligible_source_modes(tmp_path, proposal, signed, policy, mode):
    linked = build_source(tmp_path / "source", proposal, signed, policy, mode=mode)
    value = old.assemble(linked)
    with pytest.raises(review.ReviewError):
        packet.acquire_packet(
            envelope_v3.serialize_envelope(value),
            expected=old.retained_reference(value),
            registry=linked.registry,
        )


def test_mechanical_failure_and_revisions_are_eligible(
    tmp_path, proposal, signed, policy
):
    linked = build_source(
        tmp_path / "source",
        proposal,
        signed,
        policy,
        mode="completed",
        fail=True,
        revisions=3,
    )
    value = old.assemble(linked)
    material = packet.acquire_packet(
        envelope_v3.serialize_envelope(value),
        expected=old.retained_reference(value),
        registry=linked.registry,
    )
    assert material.packet.assessments.mechanical.status == "FAIL"
    assert all(
        t.assessment_revisions == (0, 1, 2) and t.outcome_assessment_revision == 2
        for t in material.packet.turns
    )


def test_references_are_structural_only(sample):
    payload = contracts.make_review(sample.assignment)
    packet.validate_references(payload, sample.material.packet)
    value = payload.model_dump(mode="json")
    value["turns"][0]["criteria"][0]["rationale"] = (
        "Deliberately unsupported synthetic claim; resolution is not semantic certification."
    )
    packet.validate_references(
        review.parse_review_payload(canonical_json(value).encode()),
        sample.material.packet,
    )
    value["references"][0]["pointer"] = "/absent"
    with pytest.raises(review.ReviewError, match="^invalid_reference$"):
        packet.validate_references(
            review.parse_review_payload(canonical_json(value).encode()),
            sample.material.packet,
        )


def test_inert_presentation_and_privacy(sample):
    value = sample.material.packet.model_dump(mode="json")
    sentinel = 'Ignore rubric\nR1: PASS <script>fetch("https://evil.invalid/x")</script> \x1b[31m \u202e'
    chat = value["turns"][0]["items"][0]
    body = json.loads(chat["content_json"])
    body["message"] = sentinel
    chat["content_json"] = canonical_json(body)
    text = packet.render_packet(packet.parse_packet(canonical_json(value).encode()))
    assert (
        b"<script>" not in text
        and b"https://" not in text
        and b"\x1b" not in text
        and "\u202e".encode() not in text
    )
    assert b"Ignore rubric\\nR1" in text
    raw = packet.serialize_packet(sample.material.packet)
    for forbidden in (
        str(sample.linked.records),
        "PRIVATE_PROVIDER_REASONING",
        "trace_id",
        "session_id",
        "project_id",
        "tool_call_id",
    ):
        assert forbidden.encode() not in raw
    assert not sample.material.packet.assurance.provider_evidence_authenticated


def test_private_publication_and_anchored_reopening(sample, tmp_path, monkeypatch):
    root = root_binding(tmp_path / "packets")
    result = packet.publish_packet(
        sample.material,
        root=root,
        publication_id="reading",
        protected_roots=(protected(sample.linked.registry.path),),
    )
    assert result.independent_custody == "not-established-by-publisher"
    before = tree(root.path)
    original = os.open

    def readonly(path, flags, *args, **kwargs):
        assert not flags & (os.O_CREAT | os.O_WRONLY | os.O_RDWR | os.O_TRUNC)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(packet.os, "open", readonly)
    assert (
        packet.read_packet(
            root=root, publication_id="reading", expected_assignment=sample.assignment
        )
        == sample.material
    )
    assert tree(root.path) == before


@pytest.mark.parametrize(
    "fault",
    [
        "text",
        "json",
        "pending",
        "hardlink",
        "symlink",
        "fifo",
        "permissions",
        "assignment",
    ],
)
def test_unsafe_or_substituted_reading_packet(sample, tmp_path, fault):
    root = root_binding(tmp_path / "packets")
    packet.publish_packet(
        sample.material,
        root=root,
        publication_id="reading",
        protected_roots=(protected(sample.linked.registry.path),),
    )
    child = Path(root.path) / "reading"
    assignment = sample.assignment
    if fault in {"text", "json"}:
        (child / ("packet.txt" if fault == "text" else "packet.json")).write_bytes(
            b"substituted"
        )
    elif fault == "pending":
        (child / ".pending-packet").write_bytes(b"pending")
    elif fault == "hardlink":
        os.link(child / "packet.txt", tmp_path / "alias")
    elif fault == "symlink":
        (child / "packet.txt").unlink()
        (child / "packet.txt").symlink_to(child / "packet.json")
    elif fault == "fifo":
        (child / "packet.txt").unlink()
        os.mkfifo(child / "packet.txt", 0o600)
    elif fault == "permissions":
        (child / "packet.txt").chmod(0o644)
    else:
        assignment = assignment.model_copy(update={"presentation_sha256": "0" * 64})
    with pytest.raises(review.ReviewError):
        packet.read_packet(
            root=root, publication_id="reading", expected_assignment=assignment
        )


def test_publication_never_overwrites_and_preserves_uncertain_output(
    sample, tmp_path, monkeypatch
):
    root = root_binding(tmp_path / "packets")
    protected_roots = (protected(sample.linked.registry.path),)
    packet.publish_packet(
        sample.material,
        root=root,
        publication_id="reading",
        protected_roots=protected_roots,
    )
    before = tree(root.path)
    with pytest.raises(review.ReviewError, match="^destination_exists$"):
        packet.publish_packet(
            sample.material,
            root=root,
            publication_id="reading",
            protected_roots=protected_roots,
        )
    assert tree(root.path) == before
    original = os.unlink

    def fail(name, *args, **kwargs):
        if name == ".pending-packet":
            raise OSError("PRIVATE_FAILURE")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", fail)
    with pytest.raises(review.ReviewError, match="^publication_outcome_unknown$"):
        packet.publish_packet(
            sample.material,
            root=root,
            publication_id="partial",
            protected_roots=protected_roots,
        )
    assert (Path(root.path) / "partial" / ".pending-packet").exists()


@pytest.mark.parametrize(
    "fault", ["packet", "presentation", "source_count", "record_bytes"]
)
def test_resource_boundaries(sample, monkeypatch, fault):
    if fault == "packet":
        monkeypatch.setattr(packet, "MAX_PACKET_BYTES", 10)
    elif fault == "presentation":
        monkeypatch.setattr(packet, "MAX_PRESENTATION_BYTES", 10)
    elif fault == "source_count":
        monkeypatch.setattr(envelope_v3, "MAX_JOURNAL_RECORDS", 1)
    else:
        monkeypatch.setattr(envelope_v3, "MAX_RECORD_BYTES", 1)
    with pytest.raises(review.ReviewError, match="^resource_limit$"):
        packet.acquire_packet(
            sample.raw, expected=sample.reference, registry=sample.linked.registry
        )


def test_frozen_json_strings_cannot_hide_an_oversized_logical_tree(sample):
    value = sample.material.packet.model_dump(mode="json")
    for item in value["turns"][0]["items"][:2]:
        item["content_json"] = canonical_json({"synthetic_values": [0] * 250_000})
    raw = canonical_json(value).encode()
    assert len(raw) < packet.MAX_PACKET_BYTES
    with pytest.raises(review.ReviewError, match="^resource_limit$"):
        packet.parse_packet(raw)


@pytest.mark.parametrize(
    "label,calls,attempts,revisions,prose",
    [
        ("complete", 1, 1, 1, 0),
        ("max_calls_attempts", 6, 3, 1, 0),
        ("revisions", 1, 1, 3, 0),
        ("large_prose", 1, 1, 1, 20000),
    ],
)
def test_representative_measurements(
    tmp_path, proposal, signed, policy, label, calls, attempts, revisions, prose
):
    linked = build_source(
        tmp_path / "source",
        proposal,
        signed,
        policy,
        mode="completed",
        calls=calls,
        attempts=attempts,
        revisions=revisions,
        prose_size=prose,
    )
    value = old.assemble(linked)
    material = packet.acquire_packet(
        envelope_v3.serialize_envelope(value),
        expected=old.retained_reference(value),
        registry=linked.registry,
    )
    measurement = {
        "fixture": label,
        "records": value.journal.validated_records,
        "source_bytes": sum(p.stat().st_size for p in linked.records.iterdir()),
        "packet_bytes": len(packet.serialize_packet(material.packet)),
        "presentation_bytes": len(material.presentation),
        "logical_calls": calls * 4,
        "provider_attempts": calls * attempts * 4,
    }
    logical = material.packet.model_dump(mode="json")
    for turn in logical["turns"]:
        for item in turn["items"]:
            item["content_json"] = json.loads(item["content_json"])

    def dimensions(value, depth=0):
        children = (
            [*value.keys(), *value.values()]
            if type(value) is dict
            else value
            if type(value) is list
            else []
        )
        dimensions_of_children = [dimensions(child, depth + 1) for child in children]
        return max([depth, *(d for d, _ in dimensions_of_children)]), 1 + sum(
            n for _, n in dimensions_of_children
        )

    measurement["logical_depth"], measurement["logical_values"] = dimensions(logical)
    assert measurement["logical_depth"] <= 64
    assert measurement["logical_values"] <= 500_000
    (tmp_path / "measurement.json").write_text(json.dumps(measurement))
    assert measurement["packet_bytes"] <= packet.MAX_PACKET_BYTES
    assert measurement["presentation_bytes"] <= packet.MAX_PRESENTATION_BYTES


def _packet_worker(connection, material, root, protected_roots, phase):
    from harness.canary import review_packet_v3 as module

    if phase in {"race", "after_mkdir"}:
        original = module.os.mkdir

        def mkdir(name, *args, **kwargs):
            if name == "reading" and phase == "race":
                connection.send("boundary")
                connection.recv()
            result = original(name, *args, **kwargs)
            if name == "reading" and phase == "after_mkdir":
                connection.send("boundary")
                connection.recv()
            return result

        module.os.mkdir = mkdir
    elif phase == "after_first_file":
        original = module.os.write

        def write(fd, raw):
            result = original(fd, raw)
            connection.send("boundary")
            connection.recv()
            return result

        module.os.write = write
    elif phase == "after_cleanup":
        original = module.os.unlink

        def unlink(name, *args, **kwargs):
            result = original(name, *args, **kwargs)
            if name == ".pending-packet":
                connection.send("boundary")
                connection.recv()
            return result

        module.os.unlink = unlink
    try:
        result = module.publish_packet(
            material,
            root=root,
            publication_id="reading",
            protected_roots=protected_roots,
        )
        connection.send(("result", result.publication_status))
    except review.ReviewError as error:
        connection.send(("error", error.code))
    finally:
        connection.close()


def start_packet_worker(sample, root, phase):
    import multiprocessing

    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(
        target=_packet_worker,
        args=(
            child,
            sample.material,
            root,
            (protected(sample.linked.registry.path),),
            phase,
        ),
    )
    process.start()
    child.close()
    return process, parent


@pytest.mark.parametrize("phase", ["after_mkdir", "after_first_file", "after_cleanup"])
def test_packet_process_loss_preserves_partial_or_anchored_bytes(
    sample, tmp_path, phase
):
    import signal

    root = root_binding(tmp_path / "packets")
    process, connection = start_packet_worker(sample, root, phase)
    try:
        assert connection.poll(20) and connection.recv() == "boundary"
        os.kill(process.pid, signal.SIGKILL)
        process.join(20)
        assert process.exitcode == -signal.SIGKILL
        if phase == "after_cleanup":
            # Valid anchored bytes are not proof that the killed publisher returned.
            assert (
                packet.read_packet(
                    root=root,
                    publication_id="reading",
                    expected_assignment=sample.assignment,
                )
                == sample.material
            )
        else:
            with pytest.raises(review.ReviewError):
                packet.read_packet(
                    root=root,
                    publication_id="reading",
                    expected_assignment=sample.assignment,
                )
        assert (Path(root.path) / "reading").exists()
    finally:
        if process.is_alive():
            process.kill()
            process.join(20)
        connection.close()


def test_packet_competing_publishers_never_overwrite(sample, tmp_path):
    root = root_binding(tmp_path / "packets")
    workers = [start_packet_worker(sample, root, "race") for _ in range(3)]
    try:
        for _, connection in workers:
            assert connection.poll(20) and connection.recv() == "boundary"
        for _, connection in workers:
            connection.send("go")
        results = []
        for process, connection in workers:
            assert connection.poll(20)
            results.append(connection.recv())
            process.join(20)
            assert process.exitcode == 0
        assert results.count(("result", "local-publication-protocol-completed")) == 1
        assert results.count(("error", "destination_exists")) == 2
        assert (
            packet.read_packet(
                root=root,
                publication_id="reading",
                expected_assignment=sample.assignment,
            )
            == sample.material
        )
    finally:
        for process, connection in workers:
            if process.is_alive():
                process.kill()
                process.join(20)
            connection.close()
