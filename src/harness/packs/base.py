"""The Pack Protocol: a named bundle of scorers.

A pack is what makes a run comparable to another run. "The RAG pack at
v2" says more about a result than a list of metric names ever could, and
it gives the runner a single object to validate against a target before
anything executes.

Like Target and Scorer, this is a Protocol: a pack can be any object with
the right shape. `SimplePack` covers the common case.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from harness.scorers.base import Scorer


@runtime_checkable
class Pack(Protocol):
    """A named set of scorers plus the target capabilities they need.

    Contract:
    - `name` identifies the pack in configs, results, and reports.
    - `scorers` are applied to every attempt, in order.
    - `required_capabilities` is what the runner checks against the
      target's declared capabilities during validation. It is normally the
      union of the scorers' `requires`, which is what SimplePack computes.
    """

    @property
    def name(self) -> str: ...

    @property
    def scorers(self) -> Sequence[Scorer]: ...

    @property
    def required_capabilities(self) -> frozenset[str]: ...


class SimplePack:
    """A pack that is exactly its scorers.

    `required_capabilities` is derived — the union of every scorer's
    `requires` — so adding a scorer that needs `contexts` automatically
    tightens the target compatibility check with no second place to
    update and forget.
    """

    def __init__(self, name: str, scorers: Sequence[Scorer]) -> None:
        self._name = name
        self._scorers = list(scorers)

    @property
    def name(self) -> str:
        return self._name

    @property
    def scorers(self) -> Sequence[Scorer]:
        return self._scorers

    @property
    def required_capabilities(self) -> frozenset[str]:
        if not self._scorers:
            return frozenset()
        return frozenset().union(*(s.requires for s in self._scorers))

    def __repr__(self) -> str:
        names = ", ".join(s.name for s in self._scorers)
        return f"SimplePack(name={self._name!r}, scorers=[{names}])"


__all__ = ["Pack", "SimplePack"]
