"""Generic structured quality gates and infrastructure semantics."""

import pytest

from harness.core.models import TargetResponse, Verdict
from harness.core.models import TestCase as Case
from harness.core.runner import run
from harness.scorers.base import Scorer
from harness.scorers.rubric_judge import RubricJudgeScorer
from harness.scorers.structured_assertions import (
    StructuredAssertionsScorer,
    validate_assertions,
)
from harness.targets.base import StaticTarget


def assertion(op="equals", **kwargs):
    return {"id": "check", "path": ["structured", "value"], "op": op, **kwargs}


def evaluate(spec, value):
    return StructuredAssertionsScorer().score(
        Case(id="c", input="hi", reference={"assertions": [spec]}),
        TargetResponse(output="ok", structured={"value": value}),
    )


@pytest.mark.parametrize(
    "spec,value,passed",
    [
        (assertion(expected=True), True, True),
        (assertion(expected=1), True, False),
        (assertion("decimal_equals", expected="130.50"), 130.5, True),
        (assertion("decimal_equals", expected="130.50"), "130.501", False),
        (assertion("decimal_lte", expected="120"), "120.00", True),
        (assertion("decimal_lte", expected="120"), "120.01", False),
        (assertion("not_null"), None, False),
        (assertion("is_null"), None, True),
        (assertion("exists", expected=True), None, True),
        (assertion("nonempty"), [], False),
        (
            assertion("contains", expected={"name": "tool"}),
            [{"name": "tool", "result": {}}],
            True,
        ),
        (assertion("excludes", expected={"name": "tool"}), [], True),
        (
            assertion("matches_any", expected=[None, {"valid": False}]),
            {"valid": False, "code": "invalid"},
            True,
        ),
        (assertion("subset", expected=["a", "b"]), ["b"], True),
        (assertion("subset", expected=["a", "b"]), ["c"], False),
    ],
)
def test_operators(spec, value, passed):
    score = evaluate(spec, value)
    assert score.passed is passed
    assert isinstance(StructuredAssertionsScorer(), Scorer)


@pytest.mark.parametrize(
    "spec",
    [
        assertion("unsupported", expected=1),
        assertion(expected=1, critical=True, gated=False),
        assertion(),
        assertion("decimal_equals", expected=True),
        assertion("decimal_lte", expected="NaN"),
        assertion(expected=1, unknown="secret"),
        assertion(expected=1, path=["raw"]),
        assertion(expected=1, path=["structured", True]),
        assertion(expected=1, path=["structured", "*"]),
        assertion(expected=1, expected_path=["output"]),
    ],
)
def test_invalid_config_is_error(spec):
    with pytest.raises(ValueError):
        validate_assertions({"assertions": [spec]})


def test_missing_evidence_and_invalid_decimal_are_errors():
    with pytest.raises(RuntimeError):
        StructuredAssertionsScorer().score(
            Case(id="c", input="x", reference={"assertions": [assertion(expected=1)]}),
            TargetResponse(output="x", structured={"other": 1}),
        )
    for value in [True, "NaN", {}, "not numeric"]:
        with pytest.raises(ValueError):
            evaluate(assertion("decimal_equals", expected="1"), value)


def test_missing_vs_null_and_path_to_path():
    scorer = StructuredAssertionsScorer()
    response = TargetResponse(
        output="hi", structured={"a": None, "b": ["x"], "c": ["x", "y"]}
    )
    case = Case(
        id="c",
        input="x",
        reference={
            "assertions": [
                {
                    "id": "absent",
                    "path": ["structured", "absent"],
                    "op": "exists",
                    "expected": False,
                },
                {"id": "null", "path": ["structured", "a"], "op": "is_null"},
                {
                    "id": "link",
                    "path": ["structured", "b"],
                    "op": "subset",
                    "expected_path": ["structured", "c"],
                },
            ]
        },
    )
    assert scorer.score(case, response).passed


@pytest.mark.parametrize(
    "values,quantifier,expected",
    [
        ([], "all", False),
        ([1, 2], "all", False),
        ([1, 2], "any", True),
        ([1, 1], "all", True),
    ],
)
def test_projection_is_explicit_and_nonvacuous(values, quantifier, expected):
    spec = assertion(
        expected=1, path=["structured", "value", "*"], quantifier=quantifier
    )
    assert evaluate(spec, values).passed is expected


@pytest.mark.parametrize("bad", ["STAFF99", "fabricated-price", "ungrounded-product"])
def test_critical_failure_cannot_be_averaged_away(bad):
    specs = [
        {"id": str(i), "path": ["output"], "op": "equals", "expected": "good"}
        for i in range(9)
    ]
    specs.append(assertion(expected="safe", critical=True))
    case = Case(id="c", input="hi", reference={"assertions": specs})
    target = StaticTarget(
        {"c": TargetResponse(output="good", structured={"value": bad})},
        capabilities=frozenset({"structured"}),
    )
    judge = RubricJudgeScorer(
        lambda _: '{"score":1,"reason":"great"}', "fake", rubric="Helpful"
    )
    result = run(target, [StructuredAssertionsScorer(), judge], [case])
    attempt = result.cases[0].attempts[0]
    assert attempt.scores[0].value == 0.9
    assert attempt.verdict == Verdict.FAIL
    assert attempt.scores[0].extra["assertions"][-1]["critical"]


def test_judge_error_preserves_critical_failure_and_informational_skip():
    case = Case(
        id="c",
        input="hi",
        reference={"assertions": [assertion(expected="safe", critical=True)]},
    )
    target = StaticTarget(
        {"c": TargetResponse(output="good", structured={"value": "unsafe"})},
        capabilities=frozenset({"structured"}),
    )
    judge = RubricJudgeScorer(lambda _: "broken", "fake", rubric="Helpful")
    result = run(target, [StructuredAssertionsScorer(), judge], [case])
    assert result.cases[0].attempts[0].verdict == Verdict.ERROR
    assert result.cases[0].attempts[0].scores[0].passed is False
    case.reference = {"assertions": [assertion(expected="safe", gated=False)]}
    assert (
        run(target, [StructuredAssertionsScorer()], [case]).cases[0].attempts[0].verdict
        == Verdict.SKIP
    )


def test_rubric_omits_nested_operations_but_keeps_conversation():
    judge = RubricJudgeScorer(lambda _: "", "fake", rubric="Useful conversation")
    response = TargetResponse(
        output="last",
        structured={
            "turns": [
                {
                    "output": "earlier",
                    "structured": {"price": "12.00"},
                    "metadata": {"trace_id": "SECRET"},
                }
            ]
        },
        metadata={"target_revision": "SECRET", "token_usage": {"total_tokens": 9}},
    )
    case = Case(id="c", input="question", extra={"endpoint": "SECRET"})
    prompt = judge.build_prompt(case, response)
    assert "earlier" in prompt and "12.00" in prompt
    assert (
        "SECRET" not in prompt
        and "token_usage" not in prompt
        and "trace_id" not in prompt
    )
    assert "SECRET" in response.model_dump_json()


def test_empty_duplicate_assertions_and_capability_mismatch():
    for reference in [
        None,
        {},
        {"assertions": []},
        {"assertions": [assertion(expected=1)] * 2},
    ]:
        with pytest.raises(ValueError):
            validate_assertions(reference)
    case = Case(id="c", input="hi", reference={"assertions": [assertion(expected=1)]})
    target = StaticTarget({"c": TargetResponse(output="hi")})
    with pytest.raises(ValueError, match="capabilities"):
        run(target, [StructuredAssertionsScorer()], [case])
    assert target.calls == []


def test_missing_projected_expected_evidence_is_error():
    case = Case(
        id="c",
        input="x",
        reference={
            "assertions": [
                {
                    "id": "grounded",
                    "path": ["structured", "ids"],
                    "op": "subset",
                    "expected_path": ["structured", "facts", "*", "id"],
                }
            ]
        },
    )
    with pytest.raises(RuntimeError, match="expected evidence"):
        StructuredAssertionsScorer().score(
            case, TargetResponse(output="x", structured={"ids": ["a"], "facts": [{}]})
        )


def test_assertion_operational_expectations_do_not_enter_judge_prompt():
    case = Case(
        id="c",
        input="x",
        reference={
            "assertions": [
                {
                    "id": "trace",
                    "path": ["metadata", "trace_id"],
                    "op": "equals",
                    "expected": "SECRET",
                }
            ],
            "semantic": "Be useful",
        },
    )
    prompt = RubricJudgeScorer(lambda _: "", "fake", rubric="Useful").build_prompt(
        case, TargetResponse(output="ok")
    )
    assert "SECRET" not in prompt
    assert "Be useful" in prompt
