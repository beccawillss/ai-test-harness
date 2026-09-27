"""Presentation-only split and explicitly manual issue relations; synthetic data."""

import html
import importlib
import json
from datetime import timedelta
from pathlib import Path

import pytest
from test_calibration import annotation, frozen, observations, revised
from test_calibration import material as _material

from harness.core.calibration import CalibrationResult, IssueComparison
from harness.core.calibration_io import (
    CalibrationIOError,
    load_result,
    refresh_reports,
    save_result,
)
from harness.core.fingerprints import canonical_json
from harness.core.store import SQLiteResultStore
from harness.reporting.calibration import (
    _cell,
    render_appendix,
    render_legacy_report,
    render_report,
)

material = _material


@pytest.fixture
def result(material):
    m = material[3]
    return CalibrationResult(
        manifest=m, frozen=frozen(m), observations=(observations(m),)
    )


def test_concise_report_and_complete_appendix(result):
    report, appendix = render_report(result), render_appendix(result)
    assert len(report.split()) < 900
    for text in (
        "manifest_hash",
        "binding_hash",
        "scorer_json",
        "prepared",
        "Synthetic material issue.",
        "Synthetic judge reason.",
        result.manifest.examples[0].identity_hash,
    ):
        assert text not in report
        assert text in appendix or text in canonical_json(
            result.model_dump(mode="json")
        )
    assert "source" in appendix and "provenance" in appendix
    assert "Synthetic material issue." in appendix
    assert "Synthetic judge reason." in appendix
    assert "analyst_appendix.md" in report
    assert "result.json" in report
    assert "MAE" in report and "Call-level confusion counts" in report
    assert (
        "historical_input_reconstructed" in report
        and "frozen_request_verified" in report
    )
    assert "numeric_differences" not in report
    assert "### E01" in appendix
    assert result.manifest.examples[0].example_id in appendix


def test_threshold_crossing_and_signed_absolute_fields(result):
    report = render_report(result)
    table = report.split("## Notable disagreements", 1)[1].split("## Findings", 1)[0]
    assert "[E01](analyst_appendix.md#e01)" in table
    assert "0.8, 0.6, 0.6, 0.8, 0.8" in table
    assert "+0.12 / 0.12" in table
    assert "40.0% (2/5)" in table
    assert "| yes |" in table


@pytest.mark.parametrize(
    "values,notable",
    [
        ((0.6,), False),
        ((0.6, 0.6), False),
        ((0.8,), True),
        ((None,), True),
        ((), True),
        ((0.6, None), True),
        ((0.4, 0.8), True),
    ],
)
def test_notable_filter_matches_errors_missing_and_cancellation(
    result, values, notable
):
    changed = revised(result, observations=(observations(result.manifest, values),))
    table = (
        render_report(changed)
        .split("## Notable disagreements", 1)[1]
        .split("## Findings", 1)[0]
    )
    assert ("[E01]" in table) is notable
    if not notable:
        assert "No notable disagreements" in table


def test_missing_judge_record_shown(result):
    report = render_report(revised(result, observations=()))
    assert "No completed observations" in report
    assert "[E01]" in report
    assert "no eligible pairs" in report


def test_large_repeat_count_is_compact(result):
    changed = revised(
        result, observations=(observations(result.manifest, (0.8,) * 100),)
    )
    report = render_report(changed)
    assert "n=100; mean 0.8" in report
    assert "0.8, 0.8, 0.8" not in report


def test_dimensions_empty_collapsed_and_collected_preserved(result):
    report, appendix = render_report(result), render_appendix(result)
    note = "Human dimension ratings were not collected in this pilot."
    assert note in report and note in appendix
    # The JSON source remains unchanged, with empty optional breakdowns intact.
    assert result.summary["human_dimensions"]["clarity"]["adequate"]["human_count"] == 0
    assert '"human_count": 0' not in html.unescape(appendix)
    m = result.manifest
    h = annotation(m, dimensions=(("clarity", "material_issue"),))
    with_ratings = revised(result, frozen=frozen(m, h))
    assert note not in render_report(with_ratings)
    assert note not in render_appendix(with_ratings)
    assert '"human_count": 1' in html.unescape(render_appendix(with_ratings))
    assert "material_issue" in render_appendix(with_ratings)


@pytest.mark.parametrize(
    "relation,label",
    [
        ("human_only_issue", "human-only issue"),
        ("judge_only_issue", "judge-only issue"),
        ("same_issue", "same issue, different severity"),
        ("different_issue", "different issues"),
        ("partial_overlap", "partial overlap"),
        ("no_issue_both", "no issue in either"),
        ("unclear", "unclear"),
    ],
)
def test_manual_issue_taxonomy_roundtrip_and_render(result, relation, label):
    h, j = result.frozen.annotations[0], result.observations[0]
    issue = IssueComparison(
        annotation_hash=h.digest,
        observation_hash=j.digest,
        call_index=0,
        relation=relation,
        reason="Synthetic manually supplied interpretation.",
        recorded_at=result.frozen.frozen_at + timedelta(seconds=1),
    )
    before = result.frozen.model_dump_json()
    changed = revised(result, issues=(issue,))
    restored = CalibrationResult.model_validate_json(changed.model_dump_json())
    assert restored.issues[0].relation == relation
    assert label in render_report(restored)
    assert relation in render_appendix(restored)
    assert issue.reason in render_appendix(restored)
    assert restored.frozen.model_dump_json() == before
    assert restored.observations == result.observations
    # Optional labels affect no agreement metrics.
    assert restored.summary["exploratory_all"] == result.summary["exploratory_all"]


@pytest.mark.parametrize("values", [(1.0,), (0.6,), (0.0,), (0.8, 0.6, 0.6, 0.8, 0.8)])
def test_scores_and_reason_keywords_never_infer_issue_relation(result, values):
    j = observations(result.manifest, values)
    calls = tuple(revised(c, reason="Synthetic material issue.") for c in j.calls)
    changed = revised(result, observations=(revised(j, calls=calls),))
    assert changed.summary["rows"][0]["issue_relations"] == ["unreviewed"] * len(values)
    assert (
        "Manual issue recognition and severity have not been reviewed"
        in render_report(changed)
    )
    assert "human-only issue" not in render_report(changed)
    assert "judge-only issue" not in render_report(changed)


def test_privacy_and_markdown_escaping(result):
    attack = '</pre><script>x</script>\n![x](https://evil/image)|`code`<a href="/PRIVATE">x</a>'
    h = annotation(result.manifest, reason=attack)
    changed = revised(result, frozen=frozen(result.manifest, h))
    appendix = render_appendix(changed)
    assert "<script>" not in appendix and "<a href=" not in appendix
    assert "&lt;script&gt;" in appendix
    escaped = _cell(attack)
    for raw in ("<script>", "![x]", "|", "`", "\n"):
        assert raw not in escaped
    for rendered in (render_report(changed), appendix):
        for excluded in (
            "SECRET_RAW",
            "SECRET_METADATA",
            "SECRET_OLD_REASON",
            "PRIVATE_LOCAL_PATH",
            "PRIVATE_DATASET_PATH",
        ):
            assert excluded not in rendered
    assert attack not in render_report(changed)


def test_save_load_semantics_and_deterministic_rendering(result, tmp_path):
    before = (
        canonical_json(
            {"result": result.model_dump(mode="json"), "summary": result.summary}
        )
        + "\n"
    )
    save_result(result, tmp_path / "analysis")
    path = tmp_path / "analysis"
    assert (path / "result.json").read_text() == before
    assert load_result(path) == result
    for name, render in (
        ("report.md", render_report),
        ("analyst_appendix.md", render_appendix),
    ):
        assert (path / name).read_text() == render(result) == render(load_result(path))
    refresh_reports(path)
    assert (path / "result.json").read_text() == before


@pytest.mark.parametrize("file", ["report.md", "analyst_appendix.md"])
def test_missing_or_changed_derived_document_rejected(result, tmp_path, file):
    path = tmp_path / "analysis"
    save_result(result, path)
    data = (path / file).read_bytes()
    (path / file).write_bytes(data + b"alteration")
    with pytest.raises(CalibrationIOError):
        load_result(path)
    (path / file).unlink()
    with pytest.raises(CalibrationIOError):
        load_result(path)


def test_legacy_report_readable_and_presentation_only_refresh(
    result, tmp_path, monkeypatch
):
    path = tmp_path / "analysis"
    save_result(result, path)
    (path / "analyst_appendix.md").unlink()
    (path / "report.md").write_text(render_legacy_report(result))
    before = (path / "result.json").read_bytes()
    assert load_result(path) == result
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "examples"))
    recipe = importlib.import_module("salesagent_human_calibration")

    def bomb(*args, **kwargs):
        pytest.fail("Presentation refresh opened a source database")

    monkeypatch.setattr(SQLiteResultStore, "__init__", bomb)
    assert recipe.main(["render", "--analysis", str(path)]) == 0
    assert (path / "result.json").read_bytes() == before
    assert (path / "report.md").read_text() == render_report(result)
    assert (path / "analyst_appendix.md").read_text() == render_appendix(result)
    assert load_result(path) == result
    snapshot = {p.name: p.read_bytes() for p in path.iterdir()}
    refresh_reports(path)
    assert {p.name: p.read_bytes() for p in path.iterdir()} == snapshot


def test_refresh_rejects_corrupt_canonical_summary_before_writing(result, tmp_path):
    path = tmp_path / "analysis"
    save_result(result, path)
    data = json.loads((path / "result.json").read_bytes())
    data["summary"]["exploratory_all"]["mae"] = 999
    (path / "result.json").write_text(canonical_json(data))
    before = {p.name: p.read_bytes() for p in path.iterdir()}
    with pytest.raises(CalibrationIOError):
        refresh_reports(path)
    assert {p.name: p.read_bytes() for p in path.iterdir()} == before


def test_exact_match_excluded_from_mixed_disagreement_table(material):
    from test_replay import prepare

    from harness.core.calibration import ObservationPolicy, make_example

    source, cases, scoring, manifest = material
    first = manifest.examples[0]
    other = make_example(
        prepare(source, cases, scoring, case_id="b"),
        manifest.contract,
        ObservationPolicy(kind="replay", artifact_id="other-replay"),
    )
    manifest = revised(
        manifest,
        examples=(first, other),
        presentation_order=(first.example_id, other.example_id),
    )
    h1 = annotation(manifest)
    h2 = revised(
        h1,
        annotation_id="second-human",
        example_id=other.example_id,
        binding_hash=other.binding_hash,
    )
    labels = frozen(
        manifest,
        h1,
        annotations=(h1, h2),
        active_ids=(h1.annotation_id, h2.annotation_id),
    )
    j1 = observations(manifest, (0.6,))
    j2 = revised(
        observations(manifest),
        example_id=other.example_id,
        identity_hash=other.identity_hash,
        artifact_id=other.observation_policy.artifact_id,
        calls=tuple(
            revised(c, prompt_hash=other.prepared.prepared.prompt_hash)
            for c in observations(manifest).calls
        ),
    )
    result = CalibrationResult(manifest=manifest, frozen=labels, observations=(j1, j2))
    table = (
        render_report(result)
        .split("## Notable disagreements", 1)[1]
        .split("## Findings", 1)[0]
    )
    assert "[E01]" not in table and "[E02]" in table
    assert "### E01" in render_appendix(result) and "### E02" in render_appendix(result)
