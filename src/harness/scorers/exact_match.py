"""Deterministic exact-match scoring."""

from __future__ import annotations

from harness.core.models import Score, ScorerKind, TargetResponse, TestCase


class ExactMatchScorer:
    """Pass when the target output exactly equals a string reference."""

    name = "exact_match"
    kind = ScorerKind.DETERMINISTIC
    requires: frozenset[str] = frozenset()

    def score(self, case: TestCase, response: TargetResponse) -> Score:
        if not isinstance(case.reference, str):
            raise ValueError(  # noqa: TRY004 - invalid evaluator input is a run error
                f"ExactMatchScorer requires a string reference for case '{case.id}'."
            )

        passed = response.output == case.reference
        return Score(
            name=self.name,
            kind=self.kind,
            value=1.0 if passed else 0.0,
            passed=passed,
            reason=(
                "Output exactly matched the reference."
                if passed
                else "Output did not exactly match the reference."
            ),
        )


__all__ = ["ExactMatchScorer"]
