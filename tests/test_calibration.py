"""Synthetic human labels test plumbing/math only; never live annotations."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from test_replay import fixture_run, prepare, scorer

from harness.core.calibration import (
    AnnotationDraft,
    CalibrationManifest,
    CalibrationResult,
    FrozenAnnotationSet,
    HumanAnnotation,
    IssueComparison,
    JudgeCall,
    JudgeObservationSet,
    ObservationPolicy,
    RatingContract,
    aggregate,
    blind_packet,
    compare,
    effective_exposure,
    historical_observations,
    make_example,
    replay_observations,
    verify_rebuilt,
)
from harness.core.fingerprints import canonical_json, fingerprint
from harness.core.models import Score, ScorerKind, Verdict
from harness.core.replay import ReplayAttemptResult, ReplayResult
from harness.judges.base import JudgeObservation


@pytest.fixture
def material():
    source, cases, scoring = fixture_run(scorer(pass_threshold=0.7))
    for case in source.cases:
        case.attempts[0].scores[0].extra["judge_model"] = "fake-v1"
    prepared = prepare(source, cases, scoring)
    c = scoring.preparation_configuration
    contract = RatingContract(
        rubric=c["rubric"],
        rubric_version=c["rubric_version"],
        scale="anchors",
        anchors=(0.0, 0.3, 0.6, 0.8, 1.0),
        threshold=c["pass_threshold"],
        projection_version=c["projection_version"],
        prompt_version=c["prompt_version"],
        judgment_version=c["judgment_version"],
        evidence_settings_json=canonical_json(c["evidence_settings"]),
        instructions="Rate independently. Do not consult judge results.",
        instruction_version="synthetic-human-v1",
        dimensions=("clarity",),
    )
    example = make_example(
        prepared,
        contract,
        ObservationPolicy(kind="replay", artifact_id="synthetic-replay"),
        exposure="not_seen",
        strata=("generic",),
    )
    manifest = CalibrationManifest(
        policy_version="synthetic-v1",
        selection_rationale="Synthetic coverage, never actual human ratings",
        coverage_gaps=(),
        contract=contract,
        examples=(example,),
        presentation_order=(example.example_id,),
    )
    return source, cases, scoring, manifest


def annotation(manifest, **changes):
    e = manifest.examples[0]
    return HumanAnnotation(
        **{
            "set_id": manifest.set_id,
            "example_id": e.example_id,
            "packet_hash": blind_packet(manifest).digest,
            "binding_hash": e.binding_hash,
            "annotator_id": "synthetic-reviewer",
            "contract": manifest.contract,
            "contract_hash": manifest.contract.digest,
            "score": 0.6,
            "passed": False,
            "reason": "Synthetic material issue.",
            "prior_exposure": "not_seen",
            **changes,
        }
    )


def observations(manifest, values=(0.8, 0.6, 0.6, 0.8, 0.8)):
    e = manifest.examples[0]
    calls = tuple(
        JudgeCall(
            index=i,
            value=v,
            passed=v >= manifest.contract.threshold
            if v is not None and manifest.contract.threshold is not None
            else None,
            reason="Synthetic judge reason." if v is not None else None,
            error=None if v is not None else "judge_execution_error",
            prompt_hash=e.prepared.prepared.prompt_hash,
            observation=JudgeObservation(observed_model="fake-v1"),
        )
        for i, v in enumerate(values)
    )
    return JudgeObservationSet(
        example_id=e.example_id,
        identity_hash=e.identity_hash,
        contract_hash=manifest.contract.digest,
        artifact_id=e.observation_policy.artifact_id,
        artifact_hash="b" * 64,
        verification="frozen_request_verified"
        if e.observation_policy.kind == "replay"
        else "historical_input_reconstructed",
        calls=calls,
    )


def frozen(manifest, human=None, **changes):
    human = human or annotation(manifest)
    return FrozenAnnotationSet(
        **{
            "manifest_hash": manifest.digest,
            "packet_hash": blind_packet(manifest).digest,
            "draft_hash": "a" * 64,
            "annotator_id": human.annotator_id,
            "annotations": (human,),
            "active_ids": (human.annotation_id,),
            "missing_ids": (),
            **changes,
        }
    )


def revised(model, **changes):
    return type(model).model_validate({**model.model_dump(), **changes})


@pytest.mark.parametrize(
    "value", [True, False, "0.6", float("nan"), float("inf"), -0.1, 1.1, 0.7, 0.4]
)
def test_invalid_human_score(material, value):
    with pytest.raises(ValueError):
        annotation(material[3], score=value)


@pytest.mark.parametrize(
    "value,passed", [(0.0, False), (0.3, False), (0.6, False), (0.8, True), (1.0, True)]
)
def test_declared_anchors(material, value, passed):
    assert annotation(material[3], score=value, passed=passed).passed is passed


@pytest.mark.parametrize(
    "changes",
    [
        {"reason": " "},
        {"reason": "x" * 1001},
        {"recorded_at": "2026-01-01T00:00:00"},
        {"schema_version": "bad"},
        {"annotator_id": "email@example.com"},
        {"prior_exposure": "blind"},
        {"dimensions": (("missing", "adequate"),)},
        {"dimensions": (("clarity", "adequate"), ("clarity", "minor_issue"))},
        {"passed": True},
        {"passed": 0},
        {"api_key": "SECRET"},
        {"contract_hash": "0" * 64},
    ],
)
def test_annotation_schema_rejects_invalid(material, changes):
    with pytest.raises(ValueError):
        annotation(material[3], **changes)


@pytest.mark.parametrize(
    "field,value",
    [
        ("rubric", "New rubric"),
        ("rubric_version", "v2"),
        ("anchors", (0.0, 0.6, 1.0)),
        ("threshold", 0.8),
        ("projection_version", "v3"),
        ("instructions", "Changed guidance"),
        ("instruction_version", "v2"),
        ("dimensions", ("new_dimension",)),
        ("evidence_settings_json", '{"scope":"new"}'),
    ],
)
def test_contract_binds_rating_guidance(material, field, value):
    original = material[3].contract
    assert revised(original, **{field: value}).digest != original.digest


def test_continuous_scale_and_threshold_equality(material):
    contract = revised(material[3].contract, scale="continuous", anchors=())
    assert contract.passed(0.7) is True
    assert contract.passed(0.4) is False
    with pytest.raises(ValueError):
        revised(contract, anchors=(0.0, 1.0))
    with pytest.raises(ValueError):
        revised(contract, packet_version="new-schema")


def test_models_deep_frozen_and_roundtrip(material):
    manifest = material[3]
    assert (
        CalibrationManifest.model_validate_json(manifest.model_dump_json()) == manifest
    )
    with pytest.raises(ValidationError):
        manifest.contract.instructions = "mutate"
    with pytest.raises(ValidationError):
        manifest.examples[0].prepared.prepared.prompt = "mutate"
    assert isinstance(manifest.examples, tuple)
    assert isinstance(
        annotation(manifest, dimensions=(("clarity", "adequate"),)).dimensions, tuple
    )


@pytest.mark.parametrize(
    "field,value",
    [("binding_hash", "0" * 64), ("contract_hash", "0" * 64), ("nonce", "changed")],
)
def test_example_binding_recomputed(material, field, value):
    with pytest.raises(ValueError):
        revised(material[3].examples[0], **{field: value})


@pytest.mark.parametrize(
    "where,field,value",
    [
        ("source", "response_hash", "0" * 64),
        ("source", "dataset_hash", "0" * 64),
        ("source", "case_hash", "0" * 64),
        ("source", "input_hash", "0" * 64),
        ("source", "document_hash", "0" * 64),
        ("source", "attempt_index", 2),
        ("source", "case_id", "other"),
        ("prepared", "evidence_json", '{"answer":"different"}'),
        ("prepared", "prompt", "changed"),
    ],
)
def test_source_join_rejects_payload_identity_changes(material, where, field, value):
    e = material[3].examples[0]
    payload = e.prepared.model_dump()
    payload[where][field] = value
    with pytest.raises(ValueError):
        verify_rebuilt(e, type(e.prepared).model_validate(payload))


def test_same_prose_not_same_evidence_or_case(material):
    source, cases, scoring, manifest = material
    other = prepare(source, cases, scoring, case_id="b")
    assert (
        source.cases[0].attempts[0].response.output
        == source.cases[1].attempts[0].response.output
    )
    with pytest.raises(ValueError):
        verify_rebuilt(manifest.examples[0], other)
    assert (
        other.prepared.evidence_hash
        != manifest.examples[0].prepared.prepared.evidence_hash
    )


def test_manifest_duplicates_order_and_configuration(material):
    source, cases, scoring, manifest = material
    e = manifest.examples[0]
    for changes in (
        {"examples": (e, e)},
        {"presentation_order": ()},
        {"presentation_order": (e.example_id, e.example_id)},
    ):
        with pytest.raises(ValueError):
            revised(manifest, **changes)
    other = make_example(
        prepare(source, cases, scoring, case_id="b"),
        manifest.contract,
        ObservationPolicy(kind="historical", artifact_id=source.run_id),
    )
    multiple = revised(
        manifest,
        examples=(e, other),
        presentation_order=(other.example_id, e.example_id),
    )
    assert blind_packet(multiple).items[0].example_id == other.example_id
    assert multiple.evidence_duplicate_groups == []


def test_repeated_distribution_and_disagreement(material):
    m = material[3]
    row = compare(m.examples[0], annotation(m), observations(m))
    assert row["distribution"]["mean"] == pytest.approx(0.72)
    assert row["distribution"]["population_stddev"] == pytest.approx(0.09797959)
    assert row["distribution"]["range"] == pytest.approx(0.2)
    assert row["distribution"]["threshold_crossing"] is True
    assert row["mean_signed_difference"] == pytest.approx(0.12)
    assert row["mae"] == pytest.approx(0.12)
    assert row["verdict_agreement"] == 0.4
    assert row["exact_matches"] == 2
    assert row["human_inside_observed_range"] is True
    assert row["confusion_matrix"]["human_fail_judge_fail"] == 2
    assert row["confusion_matrix"]["human_fail_judge_pass"] == 3
    assert row["issue_relations"] == ["unreviewed"] * 5
    assert "mean_verdict" not in row


def test_cancellation_and_unequal_repeat_weights(material):
    m = material[3]
    cancelled = compare(m.examples[0], annotation(m), observations(m, (0.4, 0.8)))
    assert cancelled["mean_signed_difference"] == pytest.approx(0)
    assert cancelled["mae"] == pytest.approx(0.2)
    rows = [
        compare(m.examples[0], annotation(m), observations(m)),
        compare(m.examples[0], annotation(m), observations(m, (0.6,))),
    ]
    total = aggregate(rows)
    assert total["mae"] == pytest.approx(0.06)
    assert total["equal_response_verdict_agreement"] == pytest.approx(0.7)
    assert total["call_agreement"] == 3 / 6
    assert total["score_pairs"] == 6
    assert total["call_pairs"] == 6


@pytest.mark.parametrize(
    "values", [(), (None,), (None, None), (0.6,), (None, 0.8, None, 0.6)]
)
def test_empty_single_errors_and_order(material, values):
    m = material[3]
    row = compare(m.examples[0], annotation(m), observations(m, values))
    assert row["distribution"]["scores_by_attempt"] == list(values)
    assert row["distribution"]["error_count"] == values.count(None)
    assert row["score_pairs"] == sum(v is not None for v in values)
    assert row["single_observation"] is (sum(v is not None for v in values) == 1)
    if not any(v is not None for v in values):
        assert (
            row["mae"]
            is row["verdict_agreement"]
            is row["human_inside_observed_range"]
            is None
        )
    assert (
        compare(m.examples[0], None, observations(m, values))["status"]
        == "missing_human"
    )
    assert compare(m.examples[0], annotation(m), None)["status"] == "missing_judge"
    assert aggregate([])["mae"] is aggregate([])["call_agreement"] is None


def test_informational_numeric_comparison_without_verdict(material):
    source, cases, _, old = material
    scoring = scorer()
    scoring.pass_threshold = None
    source.config_snapshot["scorers"] = [scoring.preparation_configuration]
    prepared = prepare(source, cases, scoring)
    contract = revised(old.contract, threshold=None)
    e = make_example(
        prepared, contract, ObservationPolicy(kind="replay", artifact_id="skip")
    )
    m = revised(
        old, contract=contract, examples=(e,), presentation_order=(e.example_id,)
    )
    row = compare(e, annotation(m, passed=None), observations(m, (0.8,)))
    assert row["mae"] == pytest.approx(0.2)
    assert row["verdict_pairs"] == 0
    assert row["verdict_agreement"] is None
    assert row["distribution"]["skip_count"] == 1


@pytest.mark.parametrize(
    "prior,declared,expected",
    [
        ("prior_results_seen", "not_seen", "prior_results_seen"),
        ("unknown", "not_seen", "unknown"),
        ("not_seen", "recognized_during_review", "recognized_during_review"),
        ("not_seen", "not_seen", "not_seen"),
    ],
)
def test_conservative_exposure(material, prior, declared, expected):
    m = material[3]
    e = revised(m.examples[0], prior_exposure=prior)
    assert effective_exposure(e, annotation(m, prior_exposure=declared)) == expected
    assert (
        effective_exposure(e, annotation(m, post_disclosure=True)) == "post_disclosure"
    )


def test_result_cohorts_and_dimensions(material):
    m = material[3]
    human = annotation(
        m,
        prior_exposure="prior_results_seen",
        dimensions=(("clarity", "material_issue"),),
    )
    result = CalibrationResult(
        manifest=m, frozen=frozen(m, human), observations=(observations(m),)
    )
    s = result.summary
    assert s["primary_blind_verified"]["example_count"] == 0
    assert s["primary_blind_verified"]["mae"] is None
    assert s["primary_note"] == "no eligible blind ratings"
    assert s["human_dimensions"]["clarity"]["material_issue"]["human_count"] == 1
    assert (
        s["cohorts"]["prior_results_seen/frozen_request_verified"]["matched_examples"]
        == 1
    )
    assert s["status"] == "provisional_uncalibrated"
    assert CalibrationResult.model_validate_json(result.model_dump_json()).summary == s
    canonical_json(s)


def test_selected_history_survives_unrelated_errors_and_missing_is_not_zero(material):
    source, cases, scoring, m = material
    source.cases[0].attempts[0].verdict = Verdict.ERROR
    source.cases[0].attempts[0].error = "SECRET_OTHER_SCORER_ERROR"
    prepared = prepare(source, cases, scoring)
    e = make_example(
        prepared,
        m.contract,
        ObservationPolicy(kind="historical", artifact_id=source.run_id),
    )
    j = historical_observations(e, source, prepared)
    assert j.verification == "historical_input_reconstructed"
    assert j.calls[0].value == 0.1
    assert "SECRET_OTHER" not in j.model_dump_json()
    source.cases[0].attempts[0].scores = []
    prepared = prepare(source, cases, scoring)
    e = make_example(
        prepared,
        m.contract,
        ObservationPolicy(kind="historical", artifact_id=source.run_id),
    )
    j = historical_observations(e, source, prepared)
    assert j.calls[0].value is None
    assert j.calls[0].error == "missing_score_unknown_cause"


def synthetic_replay(example, values=(0.8, 0.6, 0.6, 0.8, 0.8)):
    now = datetime.now(UTC)
    attempts = tuple(
        ReplayAttemptResult(
            index=i,
            score=Score(
                name="helpfulness",
                kind=ScorerKind.JUDGED,
                value=v,
                passed=v >= 0.7,
                reason="Synthetic reason.",
                extra={"judge_model": "fake-v1"},
            )
            if v is not None
            else None,
            verdict=Verdict.ERROR
            if v is None
            else Verdict.PASS
            if v >= 0.7
            else Verdict.FAIL,
            error="judge_execution_error" if v is None else None,
            started_at=now,
            duration_ms=0,
            prompt_hash=example.prepared.prepared.prompt_hash,
            input_hash=example.prepared.input_hash,
        )
        for i, v in enumerate(values)
    )
    prepared = revised(example.prepared, requested_attempt_count=len(values))
    return ReplayResult(
        replay_id=example.observation_policy.artifact_id,
        input=prepared,
        started_at=now,
        finished_at=now,
        attempts=attempts,
    )


def test_replay_import_checks_exact_saved_and_rebuilt_input(material):
    e = material[3].examples[0]
    result = synthetic_replay(e)
    j = replay_observations(e, result, e.prepared)
    assert j.verification == "frozen_request_verified"
    assert j.artifact_hash == fingerprint(result.model_dump(mode="json"))
    with pytest.raises(ValueError):
        replay_observations(e, revised(result, replay_id="other"), e.prepared)
    altered = result.model_dump()
    altered["attempts"][0]["prompt_hash"] = "0" * 64
    with pytest.raises(ValueError):
        ReplayResult.model_validate(altered)


@pytest.mark.parametrize(
    "field,value",
    [
        ("identity_hash", "0" * 64),
        ("contract_hash", "0" * 64),
        ("artifact_id", "unselected"),
        ("verification", "historical_input_reconstructed"),
    ],
)
def test_observation_join_mismatches(material, field, value):
    m = material[3]
    with pytest.raises(ValueError):
        CalibrationResult(
            manifest=m,
            frozen=frozen(m),
            observations=(revised(observations(m), **{field: value}),),
        )


def test_duplicate_calls_observations_and_invalid_verdict(material):
    m = material[3]
    j = observations(m)
    with pytest.raises(ValueError):
        revised(j, calls=(j.calls[0], j.calls[0]))
    with pytest.raises(ValueError):
        CalibrationResult(manifest=m, frozen=frozen(m), observations=(j, j))
    bad = revised(j, calls=(revised(j.calls[0], passed=False),))
    with pytest.raises(ValueError):
        CalibrationResult(manifest=m, frozen=frozen(m), observations=(bad,))


def test_optional_issue_review_requires_exact_frozen_pair(material):
    m = material[3]
    h, j = annotation(m), observations(m)
    f = frozen(m, h)
    issue = IssueComparison(
        annotation_hash=h.digest,
        observation_hash=j.digest,
        call_index=0,
        relation="same_issue",
        reason="Synthetic manual interpretation.",
        recorded_at=f.frozen_at + timedelta(seconds=1),
    )
    r = CalibrationResult(manifest=m, frozen=f, observations=(j,), issues=(issue,))
    assert (
        r.summary["rows"][0]["issue_relations"]
        == ["same_issue_different_severity"] + ["unreviewed"] * 4
    )
    for changes in (
        {"annotation_hash": "0" * 64},
        {"call_index": 99},
        {"recorded_at": f.frozen_at - timedelta(seconds=1)},
    ):
        with pytest.raises(ValueError):
            revised(r, issues=(revised(issue, **changes),))
    with pytest.raises(ValueError):
        revised(r, issues=(issue, issue))


def test_blank_draft_never_prefills_human_judgment(material):
    m = material[3]
    p = blind_packet(m)
    d = AnnotationDraft(
        set_id=m.set_id,
        example_id=p.items[0].example_id,
        packet_hash=p.digest,
        binding_hash=p.items[0].binding_hash,
        annotator_id="reviewer",
    )
    assert d.score is None and d.reason == "" and d.prior_exposure == "unknown"
    with pytest.raises(ValueError):
        revised(d, score=True)


def test_mixed_evaluator_configurations_rejected(material):
    from test_replay import settings

    from harness.core.replay import EvaluatorConfiguration, prepare_replay

    source, cases, scoring, m = material
    scoring.judge_model = "other-model"
    source.config_snapshot["scorers"] = [scoring.preparation_configuration]
    changed = prepare_replay(
        source,
        cases,
        scoring,
        case_id="b",
        database_locator="runs/source.sqlite",
        source_attempt=4,
        attempts=1,
        judge_configuration=settings(model="other-model"),
        source_evaluator=EvaluatorConfiguration(
            scorer_json=canonical_json(scoring.preparation_configuration),
            judge=settings(model="other-model"),
        ),
    )
    e = make_example(
        changed,
        m.contract,
        ObservationPolicy(kind="historical", artifact_id=source.run_id),
    )
    with pytest.raises(ValueError, match="separate cohorts"):
        revised(
            m,
            examples=(*m.examples, e),
            presentation_order=(*m.presentation_order, e.example_id),
        )


def test_actual_prompt_verification_required(material):
    m = material[3]
    j = observations(m)
    for prompt_hash in (None, "0" * 64):
        bad = revised(j, calls=(revised(j.calls[0], prompt_hash=prompt_hash),))
        with pytest.raises(ValueError, match="prompt"):
            CalibrationResult(manifest=m, frozen=frozen(m), observations=(bad,))


def test_duplicate_or_changed_historical_documents_rejected(material):
    source, cases, scoring, m = material
    source.cases[0].attempts[0].scores.append(source.cases[0].attempts[0].scores[0])
    p = prepare(source, cases, scoring)
    e = make_example(
        p, m.contract, ObservationPolicy(kind="historical", artifact_id=source.run_id)
    )
    with pytest.raises(ValueError, match="Duplicate"):
        historical_observations(e, source, p)
    source.cases[0].attempts[0].scores.pop()
    with pytest.raises(ValueError, match="changed historical"):
        historical_observations(e, source, p)


def test_nonfinite_judge_scores_and_errors_cannot_be_zero(material):
    c = observations(material[3]).calls[0]
    for changes in (
        {"value": float("nan")},
        {"value": True},
        {"value": "0.8"},
        {"value": 0, "error": "judge_execution_error"},
        {"value": None, "error": None},
        {"observation": {"raw": "SECRET"}},
    ):
        with pytest.raises(ValueError):
            revised(c, **changes)


def test_annotation_timestamp_must_precede_freeze(material):
    m = material[3]
    h = annotation(m, recorded_at=datetime.now(UTC) + timedelta(days=1))
    with pytest.raises(ValueError, match="timestamp"):
        frozen(m, h)
