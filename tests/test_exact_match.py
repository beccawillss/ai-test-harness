"""Tests for deterministic exact-match scoring."""

from __future__ import annotations

import pytest

from harness.core.models import TargetResponse
from harness.core.models import TestCase as EvaluationCase
from harness.scorers.base import Scorer
from harness.scorers.exact_match import ExactMatchScorer


def test_exact_match_scorer_satisfies_protocol():
    assert isinstance(ExactMatchScorer(), Scorer)


def test_exact_match_passes_identical_output_and_reference():
    score = ExactMatchScorer().score(
        EvaluationCase(id="c1", input="What is 2+2?", reference="4"),
        TargetResponse(output="4"),
    )

    assert score.value == 1.0
    assert score.passed is True
    assert score.reason == "Output exactly matched the reference."


def test_exact_match_fails_different_output_and_reference():
    score = ExactMatchScorer().score(
        EvaluationCase(id="c1", input="What is 2+2?", reference="4"),
        TargetResponse(output="four"),
    )

    assert score.value == 0.0
    assert score.passed is False
    assert score.reason == "Output did not exactly match the reference."


@pytest.mark.parametrize("reference", [None, {"answer": "4"}])
def test_exact_match_requires_a_string_reference(reference):
    case = EvaluationCase(id="c1", input="What is 2+2?", reference=reference)

    with pytest.raises(ValueError, match="requires a string reference"):
        ExactMatchScorer().score(case, TargetResponse(output="4"))
