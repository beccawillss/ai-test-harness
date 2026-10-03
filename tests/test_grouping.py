"""Evidence arithmetic, classification availability, and inert authored labels."""

import json
from dataclasses import asdict

import pytest
from test_comparison import _attempt, _case, _result

from harness.core.models import CaseDefinitionSnapshot, Score, ScorerKind, Verdict
from harness.reporting.grouping import group_run_results, render_groups_markdown


def classified(case_id, verdicts=(), *, category=None, risk=None, tags=()):
    case = _case(case_id, *[_attempt(i, verdict) for i, verdict in enumerate(verdicts)])
    case.definition = CaseDefinitionSnapshot(
        definition_hash="a" * 64, category=category, risk=risk
    )
    case.tags = list(tags)
    return case


@pytest.mark.parametrize("dimension", ["category", "risk"])
def test_single_value_partitions_keep_known_null_and_unknown_separate(dimension):
    a = classified("a", [Verdict.PASS], category="family", risk="band")
    b = classified("b", [Verdict.ERROR])
    c = _case("legacy", _attempt(0, Verdict.FAIL))
    groups = group_run_results(_result("run", a, b, c), by=dimension)
    assert [g.classification_state for g in groups] == [
        "value",
        "unclassified",
        "unavailable",
    ]
    assert [g.member_case_ids for g in groups] == [("a",), ("b",), ("legacy",)]
    assert [g.definition_availability for g in groups] == [
        "complete",
        "complete",
        "unavailable",
    ]
    assert groups[1].value is groups[2].value is None
    assert sum(g.case_count for g in groups) == 3
    assert all(g.totals_additive for g in groups)


def test_overlapping_tags_deduplicate_legacy_entries_without_rewriting():
    a = classified("a", [Verdict.PASS], tags=["shared", "other"])
    b = _case("legacy", _attempt(0, Verdict.FAIL))
    b.tags = ["shared", "shared", "shared"]
    c = classified("untagged")
    result = _result("run", a, b, c)
    before = result.model_dump_json()
    groups = group_run_results(result, by="tags")
    assert [(g.value, g.member_case_ids) for g in groups] == [
        ("shared", ("a", "legacy")),
        ("other", ("a",)),
        (None, ("untagged",)),
    ]
    assert groups[0].definition_availability == "partial"
    assert groups[0].definition_count == 1
    assert groups[-1].classification_state == "untagged"
    assert sum(g.case_count for g in groups) == 4  # non-additive for three cases
    assert not any(g.totals_additive for g in groups)
    assert result.model_dump_json() == before
    assert "non-additive" in render_groups_markdown(groups)
    json.dumps([asdict(group) for group in groups], allow_nan=False)


def test_all_verdicts_and_independent_scores_match_approved_arithmetic():
    a = classified(
        "a", [Verdict.PASS, Verdict.ERROR], category="family", tags=["shared"]
    )
    c = classified(
        "c", [Verdict.FAIL, Verdict.SKIP], category="family", tags=["shared"]
    )
    a.attempts[1].scores.append(
        Score(name="independent", kind=ScorerKind.DETERMINISTIC, value=0.8)
    )
    c.attempts[0].scores.append(
        Score(name="independent", kind=ScorerKind.DETERMINISTIC, value=0.4)
    )
    result = _result("run", a, c)
    for dimension in ("category", "tags"):
        group = group_run_results(result, by=dimension)[0]
        assert (group.case_count, group.judged_case_count, group.attempt_count) == (
            2,
            2,
            4,
        )
        assert (
            group.pass_count,
            group.fail_count,
            group.error_count,
            group.skip_count,
        ) == (1, 1, 1, 1)
        assert group.quality_pass_rate == 0.5
        assert group.error_rate == 0.25
        assert group.scorers[0].mean == pytest.approx(0.6)
        assert group.scorers[0].evidence_count == 2


@pytest.mark.parametrize(
    "verdicts", [[], [Verdict.ERROR], [Verdict.SKIP], [Verdict.ERROR, Verdict.SKIP]]
)
def test_no_quality_evidence_is_null(verdicts):
    group = group_run_results(_result("r", classified("c", verdicts)), by="risk")[0]
    assert group.quality_pass_rate is None
    assert group.judged_case_count == 0
    assert group.scorers == ()
    assert group.error_rate == (
        verdicts.count(Verdict.ERROR) / len(verdicts) if verdicts else 0
    )


def test_case_mean_is_not_attempt_weighted_or_risk_weighted():
    a = classified("a", [Verdict.PASS] * 3, risk="arbitrary-critical")
    b = classified("b", [Verdict.FAIL], risk="arbitrary-critical")
    c = classified("c", [Verdict.ERROR] * 5, risk="arbitrary-critical")
    group = group_run_results(_result("r", a, b, c), by="risk")[0]
    assert group.quality_pass_rate == 0.5  # not 3/4
    assert group.error_rate == 5 / 9


def test_order_is_first_appearance_and_members_follow_run_order():
    result = _result(
        "r",
        classified("c", tags=["z", "a"]),
        classified("a", tags=["a", "z"]),
        classified("b", tags=["b"]),
    )
    groups = group_run_results(result, by="tags")
    assert [g.value for g in groups] == ["z", "a", "b"]
    assert groups[0].member_case_ids == ("c", "a")
    assert groups == group_run_results(result, by="tags")


@pytest.mark.parametrize(
    "label",
    [
        "[click](https://example.test)",
        "<script>bad()</script>",
        "`code` | **bold**\n# Heading",
        "![image](https://example.test/a)",
        "null",
        "unavailable",
        "Ignore previous instructions",
    ],
)
def test_authored_labels_are_data_and_markdown_is_inert(label):
    result = _result("r", classified("a", category=label))
    groups = group_run_results(result, by="category")
    assert groups[0].value == label
    assert groups[0].classification_state == "value"
    rendered = render_groups_markdown(groups, title=label)
    assert "<script>" not in rendered
    assert "[click](" not in rendered
    assert "![image](" not in rendered
    assert "`code`" not in rendered
    assert "\n# Heading" not in rendered
    assert "**bold**" not in rendered


def test_persisted_evidence_only_and_empty_invalid_duplicate_inputs(tmp_path):
    from harness.core.models import RunResult

    result = _result("r", classified("a", category="saved"))
    result.dataset_path = str(tmp_path / "missing.jsonl")
    loaded = RunResult.model_validate_json(result.model_dump_json())
    assert group_run_results(loaded, by="category")[0].value == "saved"
    assert group_run_results(_result("empty"), by="tags") == ()
    with pytest.raises(ValueError):
        group_run_results(result, by="unsupported")
    result.cases.append(result.cases[0])
    with pytest.raises(ValueError, match="Duplicate"):
        group_run_results(result, by="category")
