"""Packs: a named bundle of scorers, and the capabilities they imply."""

from __future__ import annotations

from conftest import StubScorer

from harness.core.models import ScorerKind
from harness.packs.base import Pack, SimplePack
from harness.targets.base import (
    CAP_CONTEXTS,
    CAP_TRAJECTORY,
    StaticTarget,
    check_pack_compatibility,
)


class TestSimplePack:
    def test_satisfies_the_pack_protocol(self):
        assert isinstance(SimplePack("demo", [StubScorer()]), Pack)

    def test_required_capabilities_is_the_union_of_its_scorers(self):
        pack = SimplePack(
            "rag+agent",
            [
                StubScorer(name="recall", requires=frozenset({CAP_CONTEXTS})),
                StubScorer(name="faithfulness", requires=frozenset({CAP_CONTEXTS})),
                StubScorer(name="tool_choice", requires=frozenset({CAP_TRAJECTORY})),
            ],
        )
        assert pack.required_capabilities == frozenset({CAP_CONTEXTS, CAP_TRAJECTORY})

    def test_pack_of_reference_free_scorers_requires_nothing(self):
        pack = SimplePack("smoke", [StubScorer(), StubScorer(name="other")])
        assert pack.required_capabilities == frozenset()

    def test_empty_pack_requires_nothing(self):
        assert SimplePack("empty", []).required_capabilities == frozenset()

    def test_scorers_keep_their_declared_order(self):
        pack = SimplePack(
            "ordered",
            [StubScorer(name="a"), StubScorer(name="b", kind=ScorerKind.JUDGED)],
        )
        assert [s.name for s in pack.scorers] == ["a", "b"]

    def test_adding_a_scorer_tightens_compatibility_automatically(self):
        """The derived union is why there is no second place to forget."""
        target = StaticTarget({}, capabilities=frozenset())
        before = SimplePack("demo", [StubScorer(name="a")])
        after = SimplePack(
            "demo",
            [
                StubScorer(name="a"),
                StubScorer(name="b", requires=frozenset({CAP_CONTEXTS})),
            ],
        )
        assert check_pack_compatibility(target, before.required_capabilities) == []
        assert check_pack_compatibility(target, after.required_capabilities) == [
            "contexts"
        ]

    def test_repr_names_the_pack_and_its_scorers(self):
        pack = SimplePack("rag", [StubScorer(name="recall")])
        assert "rag" in repr(pack) and "recall" in repr(pack)
