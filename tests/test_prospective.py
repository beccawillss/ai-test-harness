"""Synthetic prospective judging; no target or provider client is used."""

import pytest
from test_calibration import material as legacy_material
from test_calibration_io import authored_draft
from test_replay import _v2_source, fixture_run, scorer, settings

from harness.core.calibration import (
    CalibrationManifest,
    CalibrationResult,
    ObservationPolicy,
    make_example,
    prospective_observations,
)
from harness.core.calibration_io import export_bundle, freeze_bundle, load_frozen
from harness.core.fingerprints import canonical_json, fingerprint
from harness.core.models import Verdict
from harness.core.prospective import (
    PreparedProspectiveJudgment,
    ProspectiveJudge,
    ProspectiveJudgingPlan,
    ProspectiveJudgmentResult,
    ProspectiveSelection,
    bind_source,
    execute_prospective,
    prepare_prospective,
    verify_prospective,
)
from harness.core.prospective_io import PreparedBundle, ProspectiveStore
from harness.core.replay import EvaluatorConfiguration, prepare_replay
from harness.judges.base import JudgeReply
from harness.scorers.output_contracts import ScoreOutputContract


def revised(model, **changes):
    return type(model).model_validate_json(
        canonical_json({**model.model_dump(mode="json"), **changes})
    )


def raising(_):
    raise AssertionError("Preparation must not invoke a judge")


def material(tmp_path, *, protected=True, count=1, policy=None):
    scoring = scorer(
        raising,
        output_validation=ScoreOutputContract(
            id="synthetic-anchors-v1", anchors=(0.0, 0.3, 0.6, 0.8, 1.0)
        ),
    )
    if policy:
        source, cases, _ = _v2_source(policy=policy)
    else:
        source, cases, _ = fixture_run(scoring)
    source.config_snapshot["scorers"] = []
    source.config_snapshot.pop("evaluation_profile", None)
    for c in source.cases:
        for a in c.attempts:
            a.scores = []
            a.verdict = Verdict.SKIP
    contract = legacy_material.__wrapped__()[3].contract
    selected = []
    for i, case in enumerate(source.cases[:count]):
        p = bind_source(
            source,
            cases,
            database_locator="runs/capture.sqlite",
            case_id=case.case_id,
            source_attempt=case.attempts[0].index,
            source_document_hash=fingerprint(source.model_dump(mode="json")),
        )
        selected.append(
            ProspectiveSelection(
                request_id=f"request-{i}",
                observation_id=f"observation-{i}",
                source=p,
                attempts=1,
                role="primary",
                requires_human=protected,
            )
        )
    evaluator = EvaluatorConfiguration(
        scorer_json=canonical_json(scoring.preparation_configuration), judge=settings()
    )
    plan = ProspectiveJudgingPlan(
        plan_id="synthetic-plan",
        selections=tuple(selected),
        evaluator=evaluator,
        taxonomy_evidence="excluded",
        sharing_policy="evaluation_data",
        review_set_id="synthetic-review" if protected else None,
        rating_contract_hash=contract.digest if protected else None,
    )
    requests = tuple(
        prepare_prospective(
            plan,
            source,
            cases,
            scoring,
            settings(),
            request_id=s.request_id,
            source_document_hash=s.source.document_hash,
        )
        for s in selected
    )
    store = ProspectiveStore(tmp_path / "prospective")
    store.save_prepared(PreparedBundle(plan=plan, requests=requests))
    return source, cases, scoring, contract, requests, store


def frozen_bundle(tmp_path, data, *, requests=None):
    _, _, _, contract, all_requests, _ = data
    requests = requests or all_requests
    examples = tuple(
        make_example(
            r,
            contract,
            ObservationPolicy(
                kind="prospective", artifact_id=r.selection.observation_id
            ),
            exposure="not_seen",
        )
        for r in requests
    )
    manifest = CalibrationManifest(
        set_id="synthetic-review",
        policy_version="synthetic-v1",
        selection_rationale="Synthetic plumbing only",
        coverage_gaps=(),
        contract=contract,
        examples=examples,
        presentation_order=tuple(e.example_id for e in examples),
    )
    export = tmp_path / "export"
    export_bundle(manifest, export, annotator_id="synthetic-reviewer")
    path = tmp_path / "freeze"
    frozen = freeze_bundle(export, authored_draft(export), path)
    return manifest, frozen, path


def execute(data, *, freeze=None, factory=None, parent=None, request=None):
    source, cases, scoring, _, requests, store = data
    return execute_prospective(
        request or requests[0],
        source_loader=lambda _: (
            source,
            cases,
            fingerprint(source.model_dump(mode="json")),
        ),
        verification_scorer=scoring,
        scorer_factory=factory
        or (
            lambda: ProspectiveJudge(
                scorer(output_validation=scoring.output_validation), settings
            )
        ),
        store=store,
        frozen_bundle=freeze,
        parent=parent,
    )


def test_complete_protected_workflow_and_blind_join(tmp_path):
    data = material(tmp_path, count=2)
    source, cases, scoring, _, requests, store = data
    original = source.model_dump_json()
    request = requests[0]
    with pytest.raises(ValueError):
        prepare_replay(
            source,
            cases,
            scoring,
            judge_configuration=settings(),
            attempts=1,
            database_locator="runs/capture.sqlite",
            case_id=request.source.case_id,
            source_attempt=request.source.attempt_index,
        )
    manifest, frozen, path = frozen_bundle(tmp_path, data)
    review = "\n".join(p.read_text() for p in (tmp_path / "export/review").iterdir())
    for secret in (
        "SECRET_",
        "fake-target",
        "fake-v1",
        "observation-0",
        "request-0",
        "capture.sqlite",
        request.source.response_hash,
    ):
        assert secret not in review
    factory_calls = []
    prompts = []

    def factory():
        assert load_frozen(path) == (manifest, frozen)
        factory_calls.append(True)
        return ProspectiveJudge(
            scorer(
                lambda prompt: (
                    prompts.append(prompt) or '{"score":0.8,"reason":"Synthetic."}'
                ),
                output_validation=scoring.output_validation,
            ),
            settings,
        )

    result = execute(data, freeze=path, factory=factory)
    assert factory_calls == [True] and prompts == [request.prepared.prompt]
    assert result.attempts[0].verdict == Verdict.PASS
    assert result.started_at >= frozen.frozen_at
    assert result.observation_id == "observation-0"
    result_path = store.save_result(result)
    assert store.load_result(result_path) == result
    assert store.state(request) == "completed"
    rebuilt = verify_prospective(
        request, lambda _: (source, cases, request.source.document_hash), scoring
    )
    joined = prospective_observations(
        manifest.examples[0], result, rebuilt, frozen_bundle=path
    )
    analysis = CalibrationResult(
        manifest=manifest, frozen=frozen, observations=(joined,)
    )
    assert analysis.summary["rows"][0]["verification"] == "frozen_request_verified"
    assert analysis.summary["rows"][0]["mae"] == pytest.approx(0.2)
    assert source.model_dump_json() == original
    with pytest.raises(FileExistsError):
        execute(data, freeze=path, factory=factory)
    assert len(factory_calls) == 1
    # Attempts returned by the immutable result are detached on every access.
    result.attempts[0].score.value = 0.1
    assert result.attempts[0].score.value == 0.8


@pytest.mark.parametrize("policy", [None, "full", "hashes_only"])
def test_unprotected_v1_v2_sources_roundtrip(tmp_path, policy):
    data = material(tmp_path, protected=False, policy=policy)
    r = data[4][0]
    assert PreparedProspectiveJudgment.model_validate_json(r.model_dump_json()) == r
    result = execute(data)
    assert result.freeze is None
    assert (
        ProspectiveJudgmentResult.model_validate_json(result.model_dump_json())
        == result
    )


@pytest.mark.parametrize(
    "part",
    [
        "missing",
        "receipt.json",
        "manifest.json",
        "packet.json",
        "draft.jsonl",
        "annotations.jsonl",
        "frozen.json",
        "roster",
    ],
)
def test_freeze_gate_precedes_factory(tmp_path, part):
    data = material(tmp_path, count=2)
    if part == "missing":
        path = None
    else:
        _, _, path = frozen_bundle(
            tmp_path, data, requests=data[4][:1] if part == "roster" else None
        )
        if part != "roster":
            p = path / part
            p.write_text("{}" if part == "receipt.json" else p.read_text() + " ")
    called = []
    with pytest.raises((ValueError, OSError)):
        execute(data, freeze=path, factory=lambda: called.append(True))
    assert called == []
    assert data[5].state(data[4][0]) == "prepared"


@pytest.mark.parametrize(
    "field",
    [
        "response",
        "case",
        "tags",
        "selection",
        "full_hash",
        "attempt",
        "definition",
        "document",
    ],
)
def test_source_drift_before_factory(tmp_path, field):
    data = material(tmp_path, policy="hashes_only")
    source, cases = data[:2]
    _, _, path = frozen_bundle(tmp_path, data)
    if field == "response":
        source.cases[0].attempts[0].response.output = "changed"
    if field == "case":
        cases[0].input = "changed"
    if field == "tags":
        cases[0].tags.append("changed")
    if field == "selection":
        source.config_snapshot["selection"]["case_ids"].reverse()
    if field == "full_hash":
        source.config_snapshot["full_dataset_hash"] = "0" * 64
    if field == "attempt":
        source.cases[0].attempts[0].index += 1
    if field == "definition":
        source.cases[0].definition = source.cases[0].definition.model_copy(
            update={"category": "changed"}
        )
    if field == "document":
        source.target_name = "changed"
    called = []
    with pytest.raises(ValueError):
        execute(data, freeze=path, factory=lambda: called.append(True))
    assert not called


@pytest.mark.parametrize("change", ["configuration", "projection", "contract"])
def test_actual_factory_configuration_checked_before_judge(tmp_path, change):
    data = material(tmp_path, protected=False)
    calls = []
    kwargs = {"output_validation": data[2].output_validation}
    if change == "projection":
        kwargs["evidence_builder"] = lambda c, r: {"answer": "drift"}
    if change == "contract":
        kwargs["output_validation"] = ScoreOutputContract(
            id="changed", anchors=(0.0, 1.0)
        )

    def factory():
        return ProspectiveJudge(
            scorer(lambda _: calls.append(True), **kwargs),
            lambda: (
                settings(model="changed") if change == "configuration" else settings()
            ),
        )

    with pytest.raises(ValueError):
        execute(data, factory=factory)
    assert calls == []
    assert data[5].state(data[4][0]) == "started_unresolved"


@pytest.mark.parametrize("reply", [False, True])
@pytest.mark.parametrize(
    "raw",
    [
        '{"score":0.7,"reason":"x"}',
        '{"score":0.5,"reason":"x"}',
        '{"score":0.80000001,"reason":"x"}',
        '{"score":true,"reason":"x"}',
        '{"score":NaN,"reason":"x"}',
        "[]",
        '{"score":0.8,"reason":""}',
        '{"score":0.8,"score":0.6,"reason":"x"}',
    ],
)
def test_malformed_judgments_are_errors_without_quality_score(tmp_path, raw, reply):
    data = material(tmp_path, protected=False)

    def factory():
        return ProspectiveJudge(
            scorer(
                lambda _: (
                    JudgeReply(text=raw, observed_model="synthetic-model", latency_ms=3)
                    if reply
                    else raw
                ),
                output_validation=data[2].output_validation,
            ),
            settings,
        )

    result = execute(data, factory=factory)
    a = result.attempts[0]
    assert a.verdict == Verdict.ERROR and a.score is None
    assert a.error == "malformed_judgment"
    assert a.observation.observed_model == ("synthetic-model" if reply else None)


def test_timeout_has_no_quality_score(tmp_path):
    data = material(tmp_path, protected=False)

    def timeout(_):
        raise TimeoutError("PRIVATE")

    result = execute(
        data,
        factory=lambda: ProspectiveJudge(
            scorer(timeout, output_validation=data[2].output_validation), settings
        ),
    )
    assert result.attempts[0].error == "judge_execution_error"
    assert "PRIVATE" not in result.model_dump_json()


def test_diagnostic_repeats_carry_parent_freeze_and_cannot_join_primary(tmp_path):
    data = material(tmp_path)
    manifest, _, path = frozen_bundle(tmp_path, data)
    parent = data[4][0]
    selection = revised(
        parent.selection,
        request_id="diagnostic-request",
        observation_id="diagnostic-observation",
        role="diagnostic",
        attempts=3,
        parent_request_hash=parent.digest,
    )
    plan = revised(
        parent.plan,
        plan_id="diagnostic-plan",
        selections=[selection.model_dump(mode="json")],
    )
    request = prepare_prospective(
        plan,
        data[0],
        data[1],
        data[2],
        settings(),
        request_id=selection.request_id,
        source_document_hash=parent.source.document_hash,
    )
    data[5].save_prepared(PreparedBundle(plan=plan, requests=(request,)))
    called = []
    with pytest.raises(ValueError):
        execute(data, freeze=path, request=request, factory=lambda: called.append(True))
    assert not called
    result = execute(data, freeze=path, request=request, parent=parent)
    assert len(result.attempts) == 3 and parent.requested_attempt_count == 1
    with pytest.raises(ValueError):
        prospective_observations(
            manifest.examples[0], result, parent, frozen_bundle=path
        )


def test_partial_freeze_rejected(tmp_path):
    data = material(tmp_path, count=2)
    _, _, _, contract, requests, _ = data
    examples = tuple(
        make_example(
            r,
            contract,
            ObservationPolicy(
                kind="prospective", artifact_id=r.selection.observation_id
            ),
        )
        for r in requests
    )
    manifest = CalibrationManifest(
        set_id="synthetic-review",
        policy_version="v1",
        selection_rationale="synthetic",
        coverage_gaps=(),
        contract=contract,
        examples=examples,
        presentation_order=tuple(e.example_id for e in examples),
    )
    export = tmp_path / "export"
    export_bundle(manifest, export, annotator_id="synthetic")
    draft = authored_draft(export)
    lines = draft.read_text().splitlines()
    draft.write_text(lines[0] + "\n")
    path = tmp_path / "freeze"
    freeze_bundle(export, draft, path, partial=True)
    called = []
    with pytest.raises(ValueError):
        execute(data, freeze=path, factory=lambda: called.append(True))
    assert not called


@pytest.mark.parametrize(
    "field",
    [
        "request_id",
        "response_json",
        "input_hash",
        "prompt",
        "evidence",
        "plan_hash",
        "policy",
        "attempts",
    ],
)
def test_request_tampering_blocks_before_factory(tmp_path, field):
    data = material(tmp_path, protected=False)
    request = data[4][0]
    doc = request.model_dump(mode="json")
    if field == "request_id":
        doc[field] = "unknown"
    if field == "response_json":
        doc[field] = "{}"
    if field in ("input_hash", "plan_hash"):
        doc[field] = "0" * 64
    if field == "prompt":
        doc["prepared"]["prompt"] += "changed"
    if field == "evidence":
        doc["prepared"]["evidence_json"] = "{}"
    if field == "policy":
        doc["plan"]["taxonomy_evidence"] = "explicitly_included"
    if field == "attempts":
        doc["plan"]["selections"][0]["attempts"] = 2
    calls = []
    with pytest.raises(ValueError):
        tampered = PreparedProspectiveJudgment.model_validate_json(canonical_json(doc))
        execute(data, request=tampered, factory=lambda: calls.append(True))
    assert not calls


def test_human_contract_mismatch_and_mixed_workflows(tmp_path):
    data = material(tmp_path)
    request = data[4][0]
    changed = revised(data[3], anchors=[0.0, 1.0])
    policy = ObservationPolicy(
        kind="prospective", artifact_id=request.selection.observation_id
    )
    with pytest.raises(ValueError):
        make_example(request, changed, policy)
    with pytest.raises(ValueError):
        make_example(
            request,
            data[3],
            ObservationPolicy(kind="replay", artifact_id="observation-0"),
        )
    old = legacy_material.__wrapped__()[3]
    new = make_example(request, data[3], policy)
    with pytest.raises(ValueError, match="Mixed"):
        revised(
            old,
            examples=[
                old.examples[0].model_dump(mode="json"),
                new.model_dump(mode="json"),
            ],
            presentation_order=[old.examples[0].example_id, new.example_id],
        )


def test_source_with_attempted_historical_judge_is_not_prospective(tmp_path):
    data = material(tmp_path, protected=False)
    source, cases, scoring = data[:3]
    source.config_snapshot["scorers"] = [scoring.preparation_configuration]
    with pytest.raises(ValueError, match="judged"):
        bind_source(
            source,
            cases,
            database_locator="source",
            case_id="a",
            source_attempt=4,
            source_document_hash=fingerprint(source.model_dump(mode="json")),
        )


def test_builder_mutation_is_detected_without_mutating_original(tmp_path):
    data = material(tmp_path, protected=False)
    original = data[0].model_dump_json()
    request = data[4][0]

    def mutate(case, response):
        case.extra["mutation"] = True
        return {"answer": response.output}

    scoring = scorer(
        evidence_builder=mutate, output_validation=data[2].output_validation
    )
    with pytest.raises(ValueError, match="mutated"):
        prepare_prospective(
            request.plan,
            data[0],
            data[1],
            scoring,
            settings(),
            request_id=request.request_id,
            source_document_hash=request.source.document_hash,
        )
    assert data[0].model_dump_json() == original and "mutation" not in data[1][0].extra


def test_wrong_prompt_is_blocked_immediately_before_call(tmp_path):
    data = material(tmp_path, protected=False)
    scoring = scorer(output_validation=data[2].output_validation)
    invoked = []

    def malformed(prepared, *, on_call):
        on_call(prepared.prompt + "changed")
        invoked.append(True)

    scoring.score_prepared = malformed
    result = execute(data, factory=lambda: ProspectiveJudge(scoring, settings))
    assert not invoked
    assert result.attempts[0].error == "input_integrity_error"


def test_factory_failure_and_cleanup_do_not_allow_silent_retries(tmp_path):
    data = material(tmp_path, protected=False)

    def failed():
        raise RuntimeError("construction failed")

    with pytest.raises(RuntimeError):
        execute(data, factory=failed)
    assert data[5].state(data[4][0]) == "started_unresolved"
    with pytest.raises(FileExistsError):
        execute(data)


def test_nonfinite_builder_mutation_cannot_hide_as_null(tmp_path):
    data = material(tmp_path, protected=False)
    request = data[4][0]

    def mutate(case, response):
        response.structured["null"] = float("nan")
        return {"answer": response.output}

    scoring = scorer(
        evidence_builder=mutate, output_validation=data[2].output_validation
    )
    with pytest.raises(ValueError, match="mutated"):
        prepare_prospective(
            request.plan,
            data[0],
            data[1],
            scoring,
            settings(),
            request_id=request.request_id,
            source_document_hash=request.source.document_hash,
        )


def test_cleanup_failure_retains_completed_result(tmp_path):
    data = material(tmp_path, protected=False)

    def close():
        raise OSError("PRIVATE cleanup details")

    with pytest.warns(RuntimeWarning, match="cleanup failed"):
        result = execute(
            data,
            factory=lambda: ProspectiveJudge(
                scorer(output_validation=data[2].output_validation), settings, close
            ),
        )
    assert result.attempts[0].score.value == 0.8
    data[5].save_result(result)


@pytest.mark.parametrize("change", ["protection", "identity", "source"])
def test_diagnostic_cannot_downgrade_parent_contract(tmp_path, change):
    data = material(tmp_path)
    _, _, path = frozen_bundle(tmp_path, data)
    parent = data[4][0]
    selection = revised(
        parent.selection,
        request_id="diagnostic",
        observation_id="diagnostic-observation",
        role="diagnostic",
        attempts=2,
        parent_request_hash=parent.digest,
    )
    plan = revised(
        parent.plan,
        plan_id="diagnostic-plan",
        selections=[selection.model_dump(mode="json")],
    )
    if change == "protection":
        selection = revised(selection, requires_human=False)
        plan = revised(
            plan,
            selections=[selection.model_dump(mode="json")],
            review_set_id=None,
            rating_contract_hash=None,
        )
    if change == "identity":
        selection = revised(selection, request_id=parent.request_id)
        plan = revised(plan, selections=[selection.model_dump(mode="json")])
    if change == "source":
        selection = revised(
            selection,
            source={**selection.source.model_dump(mode="json"), "case_id": "b"},
        )
        plan = revised(plan, selections=[selection.model_dump(mode="json")])
    calls = []
    with pytest.raises(ValueError):
        request = prepare_prospective(
            plan,
            data[0],
            data[1],
            data[2],
            settings(),
            request_id=selection.request_id,
            source_document_hash=parent.source.document_hash,
        )
        execute(
            data,
            freeze=path,
            request=request,
            parent=parent,
            factory=lambda: calls.append(True),
        )
    assert calls == []
