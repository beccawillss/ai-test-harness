"""Shared test doubles.

Everything here is offline and deterministic. The harness's own suite must
never need a network, an API key, or a budget — see StaticTarget's
docstring in harness/targets/base.py.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from harness.core.models import (
    Score,
    ScorerKind,
    TargetResponse,
    TestCase,
    ToolCall,
)


class StubScorer:
    """A scorer with scripted behaviour and a call counter.

    `behaviour` receives the case and response and returns a value, or
    raises to simulate an infrastructure failure.
    """

    def __init__(
        self,
        name: str = "stub",
        *,
        kind: ScorerKind = ScorerKind.DETERMINISTIC,
        requires: frozenset[str] = frozenset(),
        behaviour: Callable[[TestCase, TargetResponse], float] | None = None,
        gates: bool = True,
        pass_threshold: float = 0.5,
    ) -> None:
        self._name = name
        self._kind = kind
        self._requires = requires
        self._behaviour = behaviour or (lambda case, response: 1.0)
        self._gates = gates
        self.pass_threshold = pass_threshold
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def kind(self) -> ScorerKind:
        return self._kind

    @property
    def requires(self) -> frozenset[str]:
        return self._requires

    def score(self, case: TestCase, response: TargetResponse) -> Score:
        self.calls.append(case.id)
        value = self._behaviour(case, response)
        return Score(
            name=self._name,
            kind=self._kind,
            value=value,
            passed=(value >= self.pass_threshold) if self._gates else None,
        )


class ClosingTarget:
    """A target holding a resource, to prove the runner releases it."""

    def __init__(self, *, fail_on_close: bool = False) -> None:
        self.closed = 0
        self.calls: list[str] = []
        self._fail_on_close = fail_on_close

    @property
    def name(self) -> str:
        return "closing"

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset()

    def invoke(self, case: TestCase) -> TargetResponse:
        self.calls.append(case.id)
        return TargetResponse(output="ok")

    def close(self) -> None:
        self.closed += 1
        if self._fail_on_close:
            raise RuntimeError("socket already gone")


class ExplodingTarget:
    """A target that always fails, like an adapter pointed at a dead host."""

    def __init__(self, exc: Exception | None = None) -> None:
        self._exc = exc or ConnectionError("connection refused")
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return "exploding"

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset()

    def invoke(self, case: TestCase) -> TargetResponse:
        self.calls.append(case.id)
        raise self._exc


@pytest.fixture
def cases() -> list[TestCase]:
    return [
        TestCase(id="c1", input="what is 2+2?", reference="4", tags=["smoke", "math"]),
        TestCase(id="c2", input="capital of France?", reference="Paris", tags=["geo"]),
    ]


@pytest.fixture
def responses() -> dict[str, TargetResponse]:
    return {
        "c1": TargetResponse(
            output="4",
            contexts=["arithmetic basics"],
            trajectory=[
                ToolCall(name="calculator", arguments={"expr": "2+2"}, result="4")
            ],
            cost_usd=0.01,
        ),
        "c2": TargetResponse(output="Paris", contexts=["france facts"], cost_usd=0.02),
    }
