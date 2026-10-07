"""Delayed evidence joins preserve capture bytes and pending/terminal distinctions."""

import json

import pytest
from test_calibration_io import authored_draft
from test_salesagent_study import captured, prepared

from harness.core.calibration_io import export_bundle, freeze_bundle
from harness.core.fingerprints import canonical_json, fingerprint
from harness.core.prospective import ProspectiveJudge
from harness.packs import salesagent_study as study
from harness.reporting.study import (
    analyze,
    compare_studies,
    group_study,
    load_analysis,
    render_study,
    save_analysis,
    summarize,
)


def loader_for(d, source):
    return lambda _: (
        source,
        d.dataset.cases,
        fingerprint(source.model_dump(mode="json")),
    )


def judge_one(
    data, request, raw='{"score":0.8,"reason":"SYNTHETIC quality."}', freeze=None
):
    d, c, _source, prep, store, loader = data
    return study.judge_request(
        d,
        c,
        prep,
        request.request_id,
        source_loader=loader,
        store=store,
        frozen_bundle=freeze,
        scorer_factory=lambda: ProspectiveJudge(
            study.semantic_profile(c.evaluator.judge, lambda _: raw)[0],
            lambda: c.evaluator.judge,
        ),
    )


def test_pending_capture_is_not_final_pass_roundtrip_and_grouping(tmp_path):
    d, c, source, _ = captured(tmp_path)
    before = source.model_dump_json()
    analysis = analyze(
        d, c, source, document_hash=fingerprint(source.model_dump(mode="json"))
    )
    assert all(
        row.combined is None and row.semantic_availability == "pending"
        for row in analysis.rows
    )
    summary = summarize(analysis)
    assert summary["layers"]["deterministic"]["counts"]["pass"] == 50
    assert summary["layers"]["combined"]["quality_pass_rate"] is None
    assert summary["layers"]["combined"]["counts"] == {
        "pass": 0,
        "fail": 0,
        "error": 0,
        "skip": 0,
    }
    assert (
        sum(
            g["layers"]["combined"]["attempt_count"]
            for g in group_study(analysis, by="category")
        )
        == 50
    )
    tags = group_study(analysis, by="tags")
    assert sum(g["layers"]["combined"]["attempt_count"] for g in tags) == 100
    assert all(not g["totals_additive"] for g in tags)
    path = tmp_path / "analysis"
    save_analysis(analysis, path)
    assert load_analysis(path) == analysis
    assert compare_studies(analysis, analysis)["compatible"]
    assert source.model_dump_json() == before


def test_delayed_primary_join_protected_receipt_and_source_immutable(tmp_path):
    data = prepared(tmp_path)
    d, c, source, prep, _store, loader = data
    manifest = study.human_manifest(d, c, prep, loader)
    export = tmp_path / "export"
    export_bundle(manifest, export, annotator_id="synthetic-only")
    freeze = tmp_path / "freeze"
    freeze_bundle(export, authored_draft(export), freeze)
    protected = next(r for r in prep.bundle.requests if r.selection.requires_human)
    unprotected = next(
        r for r in prep.bundle.requests if not r.selection.requires_human
    )
    before = source.model_dump_json()
    results = [judge_one(data, protected, freeze=freeze), judge_one(data, unprotected)]
    report = analyze(
        d,
        c,
        source,
        document_hash=fingerprint(source.model_dump(mode="json")),
        preparation=prep,
        results=results,
        source_loader=loader,
        frozen_bundle=freeze,
    )
    assert sum(r.combined == "pass" for r in report.rows) == 2
    assert summarize(report)["semantic_availability"] == {"terminal": 2, "pending": 48}
    with pytest.raises(ValueError):
        analyze(
            d,
            c,
            source,
            document_hash=fingerprint(source.model_dump(mode="json")),
            preparation=prep,
            results=results,
            source_loader=loader,
        )
    assert source.model_dump_json() == before
    assert report.rows[0].receipt_hash is not None


def test_malformed_semantic_is_error_and_preserves_deterministic_evidence(tmp_path):
    data = prepared(tmp_path)
    d, c, source, prep, _store, loader = data
    request = next(r for r in prep.bundle.requests if not r.selection.requires_human)
    result = judge_one(data, request, raw='{"score":0.7,"reason":"Off-anchor."}')
    report = analyze(
        d,
        c,
        source,
        document_hash=fingerprint(source.model_dump(mode="json")),
        preparation=prep,
        results=[result],
        source_loader=loader,
    )
    row = next(r for r in report.rows if r.case_id == request.source.case_id)
    assert row.combined == "error" and row.semantic_availability == "terminal"
    assert json.loads(row.deterministic_json)["scores"][0]["value"] == 1
    assert json.loads(row.semantic_attempt_json)["score"] is None
    with pytest.raises(ValueError):
        analyze(
            d,
            c,
            source,
            document_hash=fingerprint(source.model_dump(mode="json")),
            preparation=prep,
            results=[result, result],
            source_loader=loader,
        )


def test_critical_failure_visible_while_semantics_pending(tmp_path):
    def empty(request, payload):
        if request.method == "POST":
            payload["recommendations"] = []

    d, c, source, _ = captured(tmp_path, mutate=empty)
    report = analyze(
        d, c, source, document_hash=fingerprint(source.model_dump(mode="json"))
    )
    assert summarize(report)["layers"]["deterministic"]["counts"]["fail"] == 50
    assert all(
        r.critical_failures == ("synthetic-rule",) and r.combined is None
        for r in report.rows
    )
    assert len(summarize(report)["critical_failures"]) == 50
    assert len(summarize(report)["critical_case_rows"]) == 12


def test_missing_response_stays_error_and_blocks_human_roster(tmp_path):
    import httpx

    def fail(request, payload):
        if (
            request.method == "POST"
            and json.loads(request.content)["message"] == "SYNTHETIC plumbing input 0"
        ):
            return httpx.Response(503)

    d, c, source, _ = captured(tmp_path, mutate=fail)
    digest = fingerprint(source.model_dump(mode="json"))
    with pytest.raises(ValueError, match="Methodological block"):
        study.prepare_primary(
            d,
            c,
            source,
            database_locator="source",
            document_hash=digest,
            plan_id="p",
            review_set_id="h",
        )
    report = analyze(d, c, source, document_hash=digest)
    assert (
        report.rows[0].combined == "error"
        and report.rows[0].semantic_availability == "unavailable"
    )
    assert len(report.rows) == 50


def test_observed_drift_qualifies_comparison_without_rewriting_requested(tmp_path):
    def drift(request, payload):
        if request.method == "GET":
            payload["model"] = "other-model"

    d, c, source, _ = captured(tmp_path, mutate=drift)
    report = analyze(
        d, c, source, document_hash=fingerprint(source.model_dump(mode="json"))
    )
    observed = json.loads(report.observed_context_json)
    assert observed["homogeneous"] == "changed"
    assert c.target.requested.model == "fake-model"
    assert compare_studies(report, report)["compatible"] is False
    assert "target regression" in compare_studies(report, report)["interpretation"]
    assert "pending" in render_study(report)


def test_source_context_and_definition_tampering_rejected(tmp_path):
    d, c, source, _ = captured(tmp_path)
    changed = source.model_copy(deep=True)
    changed.cases[0].definition = changed.cases[0].definition.model_copy(
        update={"risk": "low"}
    )
    with pytest.raises(ValueError):
        analyze(
            d, c, changed, document_hash=fingerprint(changed.model_dump(mode="json"))
        )


@pytest.mark.parametrize(
    "change", ["source", "request", "observation", "configuration", "attempt"]
)
def test_delayed_join_rejects_wrong_bindings(tmp_path, change):
    data = prepared(tmp_path)
    d, c, source, prep, _store, loader = data
    request = next(r for r in prep.bundle.requests if not r.selection.requires_human)
    result = judge_one(data, request)
    if change == "observation":
        bad = result.model_copy(update={"observation_id": "unselected"})
    else:
        plan = request.plan
        if change == "request":
            changed = request.model_copy(update={"request_id": "unselected"})
        else:
            selections = list(plan.selections)
            pos = next(
                i
                for i, s in enumerate(selections)
                if s.request_id == request.request_id
            )
            selection = selections[pos]
            if change == "source":
                selection = selection.model_copy(
                    update={
                        "source": selection.source.model_copy(
                            update={"run_id": "different-source"}
                        )
                    }
                )
            if change == "attempt":
                selection = selection.model_copy(update={"attempts": 2})
            selections[pos] = selection
            plan = plan.model_copy(update={"selections": tuple(selections)})
            if change == "configuration":
                plan = plan.model_copy(
                    update={"taxonomy_evidence": "explicitly_included"}
                )
            changed = request.model_copy(
                update={"plan": plan, "plan_hash": plan.digest}
            )
        bad = result.model_copy(update={"input": changed})
    with pytest.raises(ValueError):
        analyze(
            d,
            c,
            source,
            document_hash=fingerprint(source.model_dump(mode="json")),
            preparation=prep,
            results=[bad],
            source_loader=loader,
        )


@pytest.mark.parametrize("invalid_score", [0.7, True, False])
def test_analysis_reload_validates_anchor_contract_and_inert_labels(
    tmp_path, invalid_score
):
    data = prepared(tmp_path)
    d, c, source, prep, _store, loader = data
    request = next(r for r in prep.bundle.requests if not r.selection.requires_human)
    result = judge_one(data, request)
    report = analyze(
        d,
        c,
        source,
        document_hash=fingerprint(source.model_dump(mode="json")),
        preparation=prep,
        results=[result],
        source_loader=loader,
    )
    doc = report.model_dump(mode="json")
    row = next(r for r in doc["rows"] if r["observation_hash"])
    attempt = json.loads(row["semantic_attempt_json"])
    attempt["score"]["value"] = invalid_score
    row["semantic_attempt_json"] = canonical_json(attempt)
    from harness.reporting.study import StudyAnalysis

    with pytest.raises(ValueError):
        StudyAnalysis.model_validate_json(canonical_json(doc))
    # Renderer escapes authored assertion IDs, even when rendering an in-memory view.
    first = report.rows[0]
    body = json.loads(first.deterministic_json)
    body["scores"][0]["extra"]["assertions"][0].update(
        id="<script>bad</script>", passed=False
    )
    unsafe = first.model_copy(update={"deterministic_json": canonical_json(body)})
    output = render_study(
        report.model_copy(update={"rows": (unsafe, *report.rows[1:])})
    )
    assert "<script>" not in output and "&#60;" in output
