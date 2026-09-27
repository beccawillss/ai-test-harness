"""Synthetic-only collection, freeze, correction and report integrity tests."""

import json

import pytest
from test_calibration import (
    annotation,
    observations,
    revised,
)
from test_calibration import (
    material as _material,
)

from harness.core.calibration import (
    AnnotationDraft,
)
from harness.core.calibration_io import (
    CalibrationIOError,
    analyze_bundle,
    byte_hash,
    export_bundle,
    freeze_bundle,
    load_export,
    load_frozen,
    load_result,
    read_jsonl,
    save_result,
)
from harness.core.fingerprints import canonical_json
from harness.reporting.calibration import (
    inert,
    render_appendix,
    render_packet,
    render_report,
)

material = _material


def authored_draft(export, **changes):
    path = export / "review/draft.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    for row in rows:
        row.update(
            score=0.6,
            reason="SYNTHETIC human rating; not live data.",
            prior_exposure="not_seen",
        )
        row.update(changes)
    path.write_text("\n".join(canonical_json(row) for row in rows) + "\n")
    return path


@pytest.fixture
def exported(material, tmp_path):
    m = material[3]
    path = tmp_path / "export"
    packet = export_bundle(m, path, annotator_id="synthetic-reviewer")
    return m, packet, path


def test_allowlisted_blind_packet_preserves_all_evidence(exported):
    m, packet, path = exported
    assert (
        packet.items[0].evidence_json == m.examples[0].prepared.prepared.evidence_json
    )
    assert packet.contract.rubric == m.contract.rubric
    content = "\n".join(p.read_text() for p in (path / "review").iterdir())
    for secret in (
        "SECRET_OLD_REASON",
        "SECRET_VERDICT",
        "SECRET_METADATA",
        "SECRET_RAW",
        "PRIVATE_LOCAL_PATH",
        "fake-v1",
        "fake-target",
        "snapshot-v1",
        "synthetic-replay",
        "runs/source.sqlite",
        "known_instability",
        m.examples[0].prepared.source.response_hash,
        m.examples[0].prepared.input_hash,
    ):
        assert secret not in content
    item = packet.items[0].model_dump()
    assert set(item) == {"example_id", "binding_hash", "evidence_json"}
    draft = read_jsonl(
        (path / "review/draft.jsonl").read_bytes(), AnnotationDraft, "draft.jsonl"
    )[0]
    assert draft.score is None and draft.reason == ""
    assert load_export(path) == (m, packet)
    with pytest.raises(TypeError):
        render_packet(m)


def test_renderer_inert_adversarial_content(exported):
    _, packet, _ = exported
    attack = '</pre><script>alert(1)</script>\n![remote](https://evil/x)\n```\n# forged\n<a href="https://evil">x</a>'
    item = revised(packet.items[0], evidence_json=canonical_json({"answer": attack}))
    rendered = render_packet(revised(packet, items=(item,)))
    assert "<script>" not in rendered and "<a href=" not in rendered
    assert "&lt;/pre&gt;" in rendered and "&lt;script&gt;" in rendered
    assert inert(attack).startswith("<pre>&lt;/pre&gt;")


def test_freeze_then_analyze_roundtrip_and_recomputed_report(exported, tmp_path):
    m, packet, path = exported
    draft = authored_draft(path)
    raw = draft.read_bytes()
    destination = tmp_path / "frozen"
    f = freeze_bundle(path, draft, destination)
    assert f.draft_hash == byte_hash(raw)
    assert (destination / "draft.jsonl").read_bytes() == raw
    assert f.packet_hash == packet.digest
    assert f.annotations[0].score == 0.6 and f.annotations[0].passed is False
    assert load_frozen(destination) == (m, f)
    result = analyze_bundle(destination, lambda _: observations(m))
    output = tmp_path / "analysis"
    save_result(result, output)
    assert load_result(output) == result
    document = json.loads((output / "result.json").read_bytes())
    document["summary"]["exploratory_all"]["mae"] = 0
    (output / "result.json").write_text(canonical_json(document))
    with pytest.raises(CalibrationIOError, match="altered"):
        load_result(output)


@pytest.mark.parametrize(
    "filename",
    [
        "receipt.json",
        "manifest.json",
        "packet.json",
        "draft.jsonl",
        "annotations.jsonl",
        "frozen.json",
    ],
)
def test_altered_or_missing_freeze_fails_before_judge_loading(
    exported, tmp_path, filename
):
    _, _, path = exported
    frozen = tmp_path / "frozen"
    freeze_bundle(path, authored_draft(path), frozen)
    file = frozen / filename
    file.write_bytes(file.read_bytes() + b" ")
    if filename == "receipt.json":
        file.unlink()
    called = []
    with pytest.raises(CalibrationIOError, match="judge loading prohibited"):
        analyze_bundle(frozen, lambda e: called.append(e))
    assert called == []


def test_unfrozen_export_rejected_before_loading(exported):
    _, _, path = exported
    with pytest.raises(CalibrationIOError):
        analyze_bundle(
            path, lambda _: pytest.fail("Judge observations loaded before freeze")
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"score": None},
        {"reason": " "},
        {"score": 0.7},
        {"binding_hash": "0" * 64},
        {"packet_hash": "0" * 64},
        {"example_id": "other"},
        {"set_id": "other"},
        {"passed": False},
        {"raw": {"secret": "x"}},
        {"supersedes": "unknown"},
    ],
)
def test_invalid_human_drafts_never_publish_receipt(exported, tmp_path, changes):
    _, _, path = exported
    destination = tmp_path / "frozen"
    with pytest.raises(ValueError, match="line 1"):
        freeze_bundle(path, authored_draft(path, **changes), destination)
    assert not (destination / "receipt.json").exists()


def test_jsonl_safe_file_line_errors_and_duplicate_keys():
    for raw in (
        b'\n{"schema_version":"wrong"}\n',
        b'\n{"score":0.6,"score":0.8}\n',
        b'\n{"api_key":"DO_NOT_PRINT"}\n',
        b'\n{"score":NaN}\n',
    ):
        with pytest.raises(CalibrationIOError, match=r"draft.jsonl line 2") as error:
            read_jsonl(raw, AnnotationDraft, "draft.jsonl")
        assert "DO_NOT_PRINT" not in str(error.value)


def test_exclusive_writes_preserve_originals_and_source_aliases(exported, tmp_path):
    m, _, path = exported
    before = {p.name: p.read_bytes() for p in (path / "review").iterdir()}
    with pytest.raises(FileExistsError):
        export_bundle(m, path, annotator_id="other")
    assert before == {p.name: p.read_bytes() for p in (path / "review").iterdir()}
    alias = tmp_path / "alias"
    alias.symlink_to(path, target_is_directory=True)
    with pytest.raises(FileExistsError):
        export_bundle(m, alias, annotator_id="other")
    draft = authored_draft(path)
    frozen = tmp_path / "frozen"
    freeze_bundle(path, draft, frozen)
    with pytest.raises(FileExistsError):
        freeze_bundle(path, draft, frozen)
    result = analyze_bundle(frozen, lambda _: observations(m))
    save_result(result, tmp_path / "result")
    with pytest.raises(FileExistsError):
        save_result(result, tmp_path / "result")


def test_save_failure_leaves_no_usable_receipt(exported, tmp_path, monkeypatch):
    import harness.core.calibration_io as io

    _, _, path = exported
    real_write = io._write

    def fail(path, data):
        if path.name == "frozen.json":
            raise OSError("synthetic disk failure")
        real_write(path, data)

    monkeypatch.setattr(io, "_write", fail)
    destination = tmp_path / "partial-write"
    with pytest.raises(OSError):
        freeze_bundle(path, authored_draft(path), destination)
    assert not (destination / "receipt.json").exists()
    with pytest.raises(CalibrationIOError):
        analyze_bundle(destination, lambda _: pytest.fail("Premature judge loading"))


def test_packet_and_markdown_mutations_rejected(exported, tmp_path):
    _, _, path = exported
    authored_draft(path)
    markdown = path / "review/packet.md"
    markdown.write_text(markdown.read_text() + "Judge hint!")
    with pytest.raises(CalibrationIOError, match="Markdown"):
        freeze_bundle(path, path / "review/draft.jsonl", tmp_path / "no")


def test_immutable_correction_explicit_supersedes_and_old_result_preserved(
    exported, tmp_path
):
    m, _, path = exported
    first = tmp_path / "first"
    f1 = freeze_bundle(path, authored_draft(path), first)
    r1 = analyze_bundle(first, lambda _: observations(m))
    save_result(r1, tmp_path / "report1")
    frozen_bytes = {p.name: p.read_bytes() for p in first.iterdir()}
    draft = authored_draft(
        path,
        score=0.8,
        reason="Synthetic corrected assessment.",
        supersedes=f1.active_ids[0],
    )
    second = tmp_path / "second"
    f2 = freeze_bundle(path, draft, second, previous=first)
    assert f2.active_ids != f1.active_ids
    assert f2.annotations[0] == f1.annotations[0]
    assert f2.annotations[1].supersedes == f1.active_ids[0]
    assert f2.annotations[1].post_disclosure is True
    assert f2.previous_receipt_hash == f1.digest
    assert frozen_bytes == {p.name: p.read_bytes() for p in first.iterdir()}
    assert load_result(tmp_path / "report1") == r1
    r2 = analyze_bundle(second, lambda _: observations(m))
    assert r2.summary["rows"][0]["exposure"] == "post_disclosure"
    assert r2.summary["primary_blind_verified"]["example_count"] == 0
    assert r2.summary["rows"][0]["human_score"] == 0.8
    with pytest.raises(ValueError):
        freeze_bundle(path, draft, tmp_path / "stale", previous=second)
    with pytest.raises(ValueError):
        revised(f2, active_ids=f1.active_ids)


def test_duplicate_ids_conflicts_and_correction_cycles(exported, tmp_path):
    m, _, path = exported
    f = freeze_bundle(path, authored_draft(path), tmp_path / "frozen")
    a = f.annotations[0]
    for kwargs in (
        {"annotations": (a, a)},
        {"active_ids": (a.annotation_id, a.annotation_id)},
        {"annotations": (a, annotation(m)), "active_ids": (a.annotation_id, "unknown")},
    ):
        with pytest.raises(ValueError):
            revised(f, **kwargs)
    self_cycle = revised(a, supersedes=a.annotation_id)
    with pytest.raises(ValueError, match="cycle"):
        revised(f, annotations=(self_cycle,))
    wrong = revised(
        a, annotation_id="new", example_id="other", supersedes=a.annotation_id
    )
    with pytest.raises(ValueError, match="binding"):
        revised(f, annotations=(a, wrong), active_ids=("new",))


def test_partial_requires_explicit_freeze_and_lists_missing(material, tmp_path):
    from test_replay import prepare

    from harness.core.calibration import ObservationPolicy, make_example

    source, cases, scoring, m = material
    other = make_example(
        prepare(source, cases, scoring, case_id="b"),
        m.contract,
        ObservationPolicy(kind="historical", artifact_id=source.run_id),
    )
    m = revised(
        m,
        examples=(m.examples[0], other),
        presentation_order=(*m.presentation_order, other.example_id),
    )
    path = tmp_path / "export"
    export_bundle(m, path, annotator_id="synthetic-reviewer")
    draft = authored_draft(path)
    draft.write_text(draft.read_text().splitlines()[0] + "\n")
    with pytest.raises(ValueError, match="partial"):
        freeze_bundle(path, draft, tmp_path / "full")
    f = freeze_bundle(path, draft, tmp_path / "partial", partial=True)
    assert f.missing_ids == (other.example_id,)
    result = analyze_bundle(tmp_path / "partial", lambda _: None)
    assert result.summary["missing_humans"] == 1
    assert result.summary["missing_judges"] == 2
    assert result.summary["exploratory_all"]["mae"] is None


def test_report_safe_prose_and_no_automatic_issue_inference(exported, tmp_path):
    m, _, path = exported
    draft = authored_draft(path, reason="<script>x</script> [link](https://evil)")
    freeze_bundle(path, draft, tmp_path / "frozen")
    result = analyze_bundle(tmp_path / "frozen", lambda _: observations(m))
    report = render_report(result)
    assert "<script>" not in report
    assert "&lt;script&gt;" not in report
    assert "&lt;script&gt;" in render_appendix(result)
    assert "<script>" not in render_appendix(result)
    assert "unreviewed" in report
    assert "calibrated prediction error" in report
    assert "Exploratory human–judge agreement" in report
