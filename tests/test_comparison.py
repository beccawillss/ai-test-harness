"""Descriptive comparison of complete and stored evaluation runs."""

from __future__ import annotations

import pytest

from harness.core.models import (
    AttemptResult,
    CaseResult,
    RunResult,
    Score,
    ScorerKind,
    TargetResponse,
    Verdict,
)
from harness.core.models import TestCase as EvaluationCase
from harness.core.runner import run
from harness.core.store import SQLiteResultStore
from harness.regression.comparison import compare_runs
from harness.scorers.exact_match import ExactMatchScorer
from harness.targets.base import StaticTarget


def _attempt(
    index: int,
    verdict: Verdict,
    *,
    scores: list[Score] | None = None,
) -> AttemptResult:
    return AttemptResult(
        index=index,
        response=(
            None if verdict is Verdict.ERROR else TargetResponse(output="response")
        ),
        scores=scores or [],
        verdict=verdict,
        error="infrastructure error" if verdict is Verdict.ERROR else None,
    )


def _case(case_id: str, *attempts: AttemptResult) -> CaseResult:
    return CaseResult(case_id=case_id, attempts=list(attempts))


def _result(
    run_id: str,
    *cases: CaseResult,
    target_name: str = "target",
    dataset_hash: str = "dataset",
    model_versions: dict[str, str] | None = None,
) -> RunResult:
    return RunResult(
        run_id=run_id,
        config_path="<inline>",
        config_snapshot={},
        target_name=target_name,
        pack_name="none",
        dataset_path="<inline>",
        dataset_hash=dataset_hash,
        model_versions=model_versions or {},
        cases=list(cases),
    )


def test_stored_runs_compare_end_to_end(tmp_path):
    cases = [
        EvaluationCase(id="c1", input="2+2?", reference="4"),
        EvaluationCase(id="c2", input="2+3?", reference="5"),
    ]
    baseline = run(
        StaticTarget(
            {"c1": TargetResponse(output="4"), "c2": TargetResponse(output="5")}
        ),
        [ExactMatchScorer()],
        cases,
    )
    candidate = run(
        StaticTarget(
            {
                "c1": TargetResponse(output="wrong"),
                "c2": TargetResponse(output="5"),
            }
        ),
        [ExactMatchScorer()],
        cases,
    )
    store = SQLiteResultStore(tmp_path / "runs.sqlite")
    store.save(baseline)
    store.save(candidate)

    comparison = compare_runs(store.load(baseline.run_id), store.load(candidate.run_id))

    assert comparison.aggregate_pass_rate.baseline == 1.0
    assert comparison.aggregate_pass_rate.candidate == 0.5
    assert comparison.aggregate_pass_rate.delta == -0.5
    assert comparison.error_rate.delta == 0.0
    assert comparison.regressed_case_ids == ("c1",)
    assert comparison.improved_case_ids == ()
    c1 = comparison.cases[0]
    assert c1.pass_rate.delta == -1.0
    assert c1.scores[0].name == "exact_match"
    assert c1.scores[0].metric.delta == -1.0
    assert comparison.dataset_changed is False
    assert comparison.target_changed is False


def test_added_and_removed_cases_preserve_dataset_order():
    baseline = _result(
        "baseline",
        _case("removed", _attempt(0, Verdict.PASS)),
        _case("common", _attempt(0, Verdict.PASS)),
    )
    candidate = _result(
        "candidate",
        _case("common", _attempt(0, Verdict.PASS)),
        _case("added-second", _attempt(0, Verdict.PASS)),
        _case("added-third", _attempt(0, Verdict.PASS)),
    )

    comparison = compare_runs(baseline, candidate)

    assert [case.case_id for case in comparison.cases] == ["common"]
    assert comparison.removed_case_ids == ("removed",)
    assert comparison.added_case_ids == ("added-second", "added-third")


def test_loss_of_quality_evidence_is_not_reported_as_a_regression():
    baseline = _result("baseline", _case("c1", _attempt(0, Verdict.PASS)))
    candidate = _result("candidate", _case("c1", _attempt(0, Verdict.ERROR)))

    comparison = compare_runs(baseline, candidate)

    case = comparison.cases[0]
    assert case.pass_rate.baseline == 1.0
    assert case.pass_rate.candidate is None
    assert case.pass_rate.delta is None
    assert case.error_rate.delta == 1.0
    assert comparison.lost_evidence_case_ids == ("c1",)
    assert comparison.regressed_case_ids == ()


def test_gain_of_quality_evidence_is_recorded_separately():
    baseline = _result("baseline", _case("c1", _attempt(0, Verdict.ERROR)))
    candidate = _result("candidate", _case("c1", _attempt(0, Verdict.FAIL)))

    comparison = compare_runs(baseline, candidate)

    assert comparison.gained_evidence_case_ids == ("c1",)
    assert comparison.cases[0].pass_rate.delta is None
    assert comparison.improved_case_ids == ()


def test_scores_are_compared_by_name_using_attempt_means():
    baseline = _result(
        "baseline",
        _case(
            "c1",
            _attempt(
                0,
                Verdict.PASS,
                scores=[Score(name="faithfulness", kind=ScorerKind.JUDGED, value=0.4)],
            ),
            _attempt(
                1,
                Verdict.PASS,
                scores=[Score(name="faithfulness", kind=ScorerKind.JUDGED, value=0.8)],
            ),
        ),
    )
    candidate = _result(
        "candidate",
        _case(
            "c1",
            _attempt(
                0,
                Verdict.PASS,
                scores=[
                    Score(name="faithfulness", kind=ScorerKind.JUDGED, value=0.8),
                    Score(name="new_metric", kind=ScorerKind.DETERMINISTIC, value=0.5),
                ],
            ),
            _attempt(
                1,
                Verdict.PASS,
                scores=[Score(name="faithfulness", kind=ScorerKind.JUDGED, value=1.0)],
            ),
        ),
    )

    scores = compare_runs(baseline, candidate).cases[0].scores

    assert [score.name for score in scores] == ["faithfulness", "new_metric"]
    assert scores[0].metric.baseline == pytest.approx(0.6)
    assert scores[0].metric.candidate == pytest.approx(0.9)
    assert scores[0].metric.delta == pytest.approx(0.3)
    assert scores[1].metric.baseline is None
    assert scores[1].metric.candidate == 0.5
    assert scores[1].metric.delta is None


def test_metadata_changes_are_flagged_without_blocking_comparison():
    baseline = _result(
        "baseline",
        _case("c1", _attempt(0, Verdict.PASS)),
        target_name="target-v1",
        dataset_hash="dataset-v1",
        model_versions={"target": "model-v1"},
    )
    candidate = _result(
        "candidate",
        _case("c1", _attempt(0, Verdict.PASS)),
        target_name="target-v2",
        dataset_hash="dataset-v2",
        model_versions={"target": "model-v2"},
    )

    comparison = compare_runs(baseline, candidate)

    assert comparison.target_changed is True
    assert comparison.dataset_changed is True
    assert comparison.model_versions_changed is True
    assert len(comparison.cases) == 1


def test_duplicate_case_ids_are_rejected():
    duplicate = _result(
        "duplicate-run",
        _case("c1", _attempt(0, Verdict.PASS)),
        _case("c1", _attempt(0, Verdict.FAIL)),
    )
    candidate = _result("candidate", _case("c1", _attempt(0, Verdict.PASS)))

    with pytest.raises(ValueError, match="duplicate case id 'c1'"):
        compare_runs(duplicate, candidate)


@pytest.mark.parametrize(
    "key,first,second",
    [
        ("attempts", 1, 3),
        (
            "scorers",
            [{"name": "judge", "rubric": "a"}],
            [{"name": "judge", "rubric": "b"}],
        ),
        (
            "scorers",
            [{"name": "judge", "pass_threshold": 0.7}],
            [{"name": "judge", "pass_threshold": 0.8}],
        ),
        ("assertion_schema_version", "v1", "v2"),
        ("evidence_schema_version", "v1", "v2"),
    ],
)
def test_evaluation_configuration_changes_are_flagged(key, first, second):
    baseline = _result("b")
    candidate = _result("c")
    baseline.config_snapshot[key] = first
    candidate.config_snapshot[key] = second
    assert compare_runs(baseline, candidate).evaluation_config_changed


def test_revision_and_endpoint_are_not_evaluator_or_identity_changes():
    baseline = _result("b", target_name="salesagent")
    candidate = _result("c", target_name="salesagent")
    baseline.config_snapshot["target_configuration"] = {
        "target_revision": "abc",
        "base_url": "http://one",
    }
    candidate.config_snapshot["target_configuration"] = {
        "target_revision": "def",
        "base_url": "http://two",
    }
    comparison = compare_runs(baseline, candidate)
    assert not comparison.target_changed
    assert not comparison.evaluation_config_changed


def test_legacy_configuration_is_not_assumed_equivalent():
    baseline = _result("b")
    candidate = _result("c")
    candidate.config_snapshot["attempts"] = 1
    assert compare_runs(baseline, candidate).evaluation_config_changed


@pytest.fixture
def organized(tmp_path):
    from test_suites import Metric, RecordingTarget, author, profile

    from harness.core.suites import execute_suite, resolve_suite

    resolved = resolve_suite(author(tmp_path))
    result = execute_suite(
        resolved,
        RecordingTarget(),
        [Metric()],
        profile=profile(scorer_configuration={"metric": {"version": "metric-v1"}}),
    )
    for case in result.cases:
        for attempt in case.attempts:
            attempt.response.metadata = {
                "target_revision": "target-v1",
                "evidence_schema_version": "evidence-v1",
            }
    store = SQLiteResultStore(tmp_path / "comparison.sqlite")
    store.save(result)
    return store.load(result.run_id)


def checks(comparison):
    return {check.name: check for check in comparison.context.checks}


def test_compatible_context_is_equal_and_serializable_without_mutation(organized):
    import json
    from dataclasses import asdict

    before = organized.model_dump_json()
    candidate = organized.model_copy(deep=True)
    candidate.run_id = "candidate"
    candidate.cases[0].attempts[0].verdict = Verdict.FAIL
    comparison = compare_runs(organized, candidate)
    assert comparison.context.status == "equal"
    assert comparison.context.case_matching == "dataset_identity"
    assert comparison.regressed_case_ids == ("a",)
    assert all(g.context_status == "equal" for g in comparison.groups)
    assert any(g.interpretation == "observed decrease" for g in comparison.groups)
    assert checks(comparison)["case_input_reference"].status == "unknown"
    assert checks(comparison)["dataset_identity"].baseline == "dataset"
    assert (
        json.loads(json.dumps(asdict(comparison), allow_nan=False))["context"]["status"]
        == "equal"
    )
    candidate.config_snapshot["evaluation_profile"]["safe_parameters"]["later"] = "edit"
    assert checks(comparison)["evaluation_profile"].candidate["safe_parameters"] == {}
    assert organized.model_dump_json() == before


@pytest.mark.parametrize(
    "key,value,expected",
    [
        ("attempts", 3, "attempt_policy"),
        ("full_dataset_hash", "b" * 64, "full_dataset_fingerprint"),
        (
            "scorers",
            [
                {
                    "name": "metric",
                    "kind": "deterministic",
                    "requires": [],
                    "pass_threshold": 0.9,
                }
            ],
            "scorer_snapshots",
        ),
        ("target_capabilities", ["new-evidence"], "target_capabilities"),
        ("evidence_schema_version", "evidence-v2", "evidence_schema"),
    ],
)
def test_recorded_run_context_changes(organized, key, value, expected):
    candidate = organized.model_copy(deep=True)
    candidate.config_snapshot[key] = value
    comparison = compare_runs(organized, candidate)
    assert checks(comparison)[expected].status == "changed"
    assert comparison.context.status == "changed"
    assert checks(comparison)[expected].affected_case_ids == ("a", "b")


@pytest.mark.parametrize(
    "field", ["category", "risk", "tags", "reference", "title", "input", "extra"]
)
def test_reauthored_case_changes_are_bound_and_classification_is_separate(
    tmp_path, organized, field
):
    import json

    from test_suites import Metric, RecordingTarget, profile

    from harness.core.suites import execute_suite, resolve_suite

    path = tmp_path / "cases.jsonl"
    rows = [json.loads(row) for row in path.read_text().splitlines()]
    rows[0][field] = (
        ["quick", "new"]
        if field == "tags"
        else {"revised": True}
        if field == "extra"
        else "revised"
    )
    path.write_text("\n".join(json.dumps(row) for row in rows))
    revised = execute_suite(
        resolve_suite(tmp_path / "suites/quick.json"),
        RecordingTarget(),
        [Metric()],
        profile=profile(scorer_configuration={"metric": {"version": "metric-v1"}}),
    )
    comparison = compare_runs(organized, revised)
    context = checks(comparison)
    assert context["case_definition_hash"].status == "changed"
    assert context["case_definition_hash"].affected_case_ids == ("a",)
    assert context["descriptor_definition"].status == "equal"
    assert context["resolved_membership"].status == "equal"
    assert (
        context["case_input_reference"].status == "unknown"
    )  # no invented field-level evidence
    if field in ("category", "risk", "tags"):
        assert context[f"case_{field}"].status == "changed"
        assert any(group.membership.status == "changed" for group in comparison.groups)
    else:
        assert all(
            context[f"case_{key}"].status == "equal"
            for key in ("category", "risk", "tags")
        )


def test_descriptor_only_edit_is_not_a_case_definition_edit(organized):
    from harness.core.fingerprints import fingerprint

    candidate = organized.model_copy(deep=True)
    candidate.config_snapshot["dataset_descriptor"]["description"] = "new prose"
    candidate.config_snapshot["dataset_descriptor_hash"] = fingerprint(
        candidate.config_snapshot["dataset_descriptor"]
    )
    context = checks(compare_runs(organized, candidate))
    assert context["descriptor_definition"].status == "changed"
    assert context["case_definition_hash"].status == "equal"
    assert context["full_dataset_fingerprint"].status == "equal"
    assert context["executed_subset_fingerprint"].status == "equal"


def test_expression_change_can_leave_membership_equal(organized):
    from harness.core.fingerprints import fingerprint

    candidate = organized.model_copy(deep=True)
    candidate.config_snapshot["suite"]["selection"] = {"tags_all": ["quick"]}
    candidate.config_snapshot["suite_hash"] = fingerprint(
        candidate.config_snapshot["suite"]
    )
    candidate.config_snapshot["selection"]["expression"] = {"tags_all": ["quick"]}
    comparison = compare_runs(organized, candidate)
    context = checks(comparison)
    assert context["suite_definition"].status == "changed"
    assert context["selection_expression"].status == "changed"
    assert context["resolved_membership"].status == "equal"
    assert all(group.membership.status == "equal" for group in comparison.groups)
    assert all(group.context_status == "changed" for group in comparison.groups)


def test_full_dataset_and_executed_subset_are_separate(organized):
    candidate = organized.model_copy(deep=True)
    candidate.cases.pop()
    candidate.dataset_hash = "c" * 64
    comparison = compare_runs(organized, candidate)
    context = checks(comparison)
    assert context["full_dataset_fingerprint"].status == "equal"
    assert context["executed_subset_fingerprint"].status == "changed"
    assert context["resolved_membership"].status == "changed"
    assert comparison.context.baseline_case_ids == ("a", "b")
    assert comparison.context.candidate_case_ids == ("a",)
    assert comparison.removed_case_ids == ("b",)
    shared = next(
        g for g in comparison.groups if (g.baseline or g.candidate).dimension == "tags"
    )
    assert shared.membership.baseline == ["a", "b"]
    assert shared.membership.candidate == ["a"]
    assert shared.membership.affected_case_ids == ("b",)
    assert shared.context_status == "changed"
    assert "Independent" in shared.qualification


def test_different_named_datasets_never_join_same_case_ids(organized):
    candidate = organized.model_copy(deep=True)
    candidate.config_snapshot["dataset_descriptor"]["id"] = "different-study"
    candidate.cases[0].attempts[0].verdict = Verdict.FAIL
    comparison = compare_runs(organized, candidate)
    assert comparison.context.case_matching == "different_datasets"
    assert comparison.context.status == "changed"
    assert comparison.cases == ()
    assert comparison.regressed_case_ids == ()
    assert comparison.added_case_ids == comparison.removed_case_ids == ("a", "b")
    assert all(group.membership.status == "unknown" for group in comparison.groups)
    assert comparison.aggregate_pass_rate.delta < 0  # explicitly unpaired run summaries


def test_authored_version_drift_retains_scoped_ids_but_qualifies_comparison(organized):
    candidate = organized.model_copy(deep=True)
    candidate.config_snapshot["dataset_descriptor"]["version"] = "study-v2"
    comparison = compare_runs(organized, candidate)
    assert comparison.context.case_matching == "dataset_identity"
    assert checks(comparison)["dataset_version"].status == "changed"
    assert len(comparison.cases) == 2


@pytest.mark.parametrize("scheme", ["dataset-cases-v1", "future", None])
def test_scheme_mismatch_never_equates_hash_strings(organized, scheme):
    candidate = organized.model_copy(deep=True)
    candidate.config_snapshot["dataset_fingerprint_scheme"] = scheme
    # Stored v2 definitions also make the downgrade contradictory.
    context = checks(compare_runs(organized, candidate))
    assert context["fingerprint_scheme"].status in ("changed", "unknown")
    assert context["full_dataset_fingerprint"].status == "unknown"
    assert context["executed_subset_fingerprint"].status == "unknown"
    assert context["case_definition_hash"].status == "unknown"


def test_known_v1_v2_scheme_difference_is_changed_even_if_hash_text_matches(organized):
    legacy = organized.model_copy(deep=True)
    legacy.config_snapshot["dataset_fingerprint_scheme"] = "dataset-cases-v1"
    for case in legacy.cases:
        case.definition = None
    context = checks(compare_runs(legacy, organized))
    assert context["fingerprint_scheme"].status == "changed"
    assert context["executed_subset_fingerprint"].status == "unknown"


def test_legacy_missing_metadata_stays_unknown_but_descriptive_api_remains():
    baseline = _result("b", _case("same", _attempt(0, Verdict.PASS)))
    candidate = _result("c", _case("same", _attempt(0, Verdict.FAIL)))
    comparison = compare_runs(baseline, candidate)
    context = checks(comparison)
    assert comparison.context.case_matching == "unverified_ids"
    assert comparison.context.status == "unknown"
    assert comparison.regressed_case_ids == ("same",)
    assert comparison.cases[0].pass_rate.delta == -1
    for key in (
        "dataset_identity",
        "dataset_version",
        "evaluation_profile",
        "descriptor_definition",
        "case_category",
        "case_definition_hash",
        "judge_configuration",
    ):
        assert context[key].status == "unknown"
    assert context["fingerprint_scheme"].status == "equal"  # historical v1 rule


def test_missing_custom_configuration_is_not_certified_equivalent(organized):
    for entry in organized.config_snapshot["evaluation_profile"]["scorers"]:
        entry["configuration_status"] = "unknown"
        entry["configuration"] = None
    comparison = compare_runs(organized, organized)
    assert checks(comparison)["scorer_configuration"].status == "unknown"
    assert comparison.context.status == "unknown"


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "profile-v2"),
        ("taxonomy_evidence", "explicitly_included"),
        ("safe_parameters", {"threshold": 0.2}),
        ("reference_contract", "new-contract"),
    ],
)
def test_effective_profile_changes_are_visible(organized, field, value):
    candidate = organized.model_copy(deep=True)
    candidate.config_snapshot["evaluation_profile"][field] = value
    assert (
        checks(compare_runs(organized, candidate))["evaluation_profile"].status
        == "changed"
    )


def test_judge_and_custom_scorer_configuration_changes(organized):
    entry = organized.config_snapshot["evaluation_profile"]["scorers"][0]
    entry["observed"]["kind"] = "judged"
    entry["judge"] = {"model": "fake-model-v1", "max_output_tokens": 1024}
    candidate = organized.model_copy(deep=True)
    candidate.config_snapshot["evaluation_profile"]["scorers"][0]["judge"][
        "max_output_tokens"
    ] = 512
    assert (
        checks(compare_runs(organized, candidate))["judge_configuration"].status
        == "changed"
    )
    candidate = organized.model_copy(deep=True)
    candidate.config_snapshot["evaluation_profile"]["scorers"][0]["configuration"][
        "version"
    ] = "new-version"
    assert (
        checks(compare_runs(organized, candidate))["scorer_configuration"].status
        == "changed"
    )
    entry["judge"] = None
    assert (
        checks(compare_runs(organized, organized))["judge_configuration"].status
        == "unknown"
    )


def test_target_version_observations_do_not_change_legacy_flags(organized):
    candidate = organized.model_copy(deep=True)
    candidate.cases[0].attempts[0].response.metadata["target_revision"] = "target-v2"
    candidate.model_versions["target"] = "model-v2"
    comparison = compare_runs(organized, candidate)
    assert not comparison.target_changed
    assert checks(comparison)["target_version_observations"].status == "changed"
    assert checks(comparison)["model_versions"].status == "unknown"  # baseline absent


def test_payload_policy_only_change_is_an_artifact_difference(tmp_path, organized):
    from test_suites import Metric, RecordingTarget, profile

    from harness.core.suites import execute_suite, resolve_suite

    candidate = execute_suite(
        resolve_suite(tmp_path / "suites/quick.json"),
        RecordingTarget(),
        [Metric()],
        profile=profile(
            case_payload_snapshot="full",
            scorer_configuration={"metric": {"version": "metric-v1"}},
        ),
    )
    for case in candidate.cases:
        for attempt in case.attempts:
            attempt.response.metadata = {
                "target_revision": "target-v1",
                "evidence_schema_version": "evidence-v1",
            }
    comparison = compare_runs(organized, candidate)
    assert comparison.context.status == "equal"
    assert comparison.context.artifact_status == "changed"
    assert checks(comparison)["evaluation_profile"].status == "equal"
    assert checks(comparison)["case_payload_snapshot"].status == "changed"
    assert checks(comparison)["case_input_reference"].status == "unknown"
    assert all(group.context_status == "equal" for group in comparison.groups)
    full = compare_runs(candidate, candidate)
    assert checks(full)["case_input_reference"].status == "equal"
    assert full.context.artifact_status == "equal"


def test_group_reports_qualify_membership_drift_and_escape_authored_labels(organized):
    from harness.regression.comparison import render_comparison_markdown

    candidate = organized.model_copy(deep=True)
    candidate.cases[0].definition = candidate.cases[0].definition.model_copy(
        update={"category": "[bad](https://example.test) | <b>title</b>\n# Heading"}
    )
    candidate.cases[0].attempts[0].verdict = Verdict.FAIL
    comparison = compare_runs(organized, candidate)
    markdown = render_comparison_markdown(comparison)
    assert "observed decrease" in markdown
    assert "Evaluation context: changed" in markdown
    assert "[bad](" not in markdown
    assert "<b>" not in markdown
    assert "\n# Heading" not in markdown
    assert "regression" not in markdown
    changed = [g for g in comparison.groups if g.membership.status == "changed"]
    assert changed
    assert all(g.context_status == "changed" for g in changed)


def test_reordered_membership_reports_order_change_and_affected_cases(organized):
    candidate = organized.model_copy(deep=True)
    candidate.cases.reverse()
    comparison = compare_runs(organized, candidate)
    assert checks(comparison)["resolved_membership"].status == "changed"
    assert comparison.added_case_ids == comparison.removed_case_ids == ()
    shared = next(
        group
        for group in comparison.groups
        if (group.baseline or group.candidate).dimension == "tags"
    )
    assert shared.membership.baseline == ["a", "b"]
    assert shared.membership.candidate == ["b", "a"]
    assert shared.membership.affected_case_ids == ("a", "b")


def test_incomplete_profile_payload_and_null_identity_are_unknown(organized):
    organized.config_snapshot["evaluation_profile"]["scorers"] = [None]
    organized.config_snapshot["dataset_descriptor"]["id"] = None
    organized.config_snapshot["case_payload_snapshot"] = "full"
    organized.config_snapshot["resolved_cases"] = []
    comparison = compare_runs(organized, organized)
    assert comparison.context.case_matching == "unverified_ids"
    for key in (
        "dataset_identity",
        "scorer_configuration",
        "judge_configuration",
        "case_input_reference",
    ):
        assert checks(comparison)[key].status == "unknown"


def test_known_null_and_unavailable_classification_do_not_compare_as_equal(organized):
    candidate = organized.model_copy(deep=True)
    assert candidate.cases[1].definition.category is None
    candidate.cases[1].definition = None
    comparison = compare_runs(organized, candidate)
    assert checks(comparison)["case_category"].status == "unknown"
    categories = [
        g
        for g in comparison.groups
        if (g.baseline or g.candidate).dimension == "category"
    ]
    assert any(
        g.baseline
        and g.baseline.classification_state == "unclassified"
        and g.candidate is None
        for g in categories
    )
    assert any(
        g.candidate
        and g.candidate.classification_state == "unavailable"
        and g.baseline is None
        for g in categories
    )


def test_full_payload_field_comparison_does_not_copy_private_inputs(organized):
    import json
    from dataclasses import asdict

    organized.config_snapshot["case_payload_snapshot"] = "full"
    organized.config_snapshot["resolved_cases"] = [
        {"id": c.case_id, "input": "PRIVATE_INPUT", "reference": "expected"}
        for c in organized.cases
    ]
    candidate = organized.model_copy(deep=True)
    candidate.config_snapshot["resolved_cases"][0]["reference"] = "changed expected"
    comparison = compare_runs(organized, candidate)
    fields = checks(comparison)["case_input_reference"]
    assert fields.status == "changed"
    assert fields.baseline["a"]["input"] == fields.candidate["a"]["input"]
    assert fields.baseline["a"]["reference"] != fields.candidate["a"]["reference"]
    assert "PRIVATE_INPUT" not in json.dumps(asdict(comparison))
