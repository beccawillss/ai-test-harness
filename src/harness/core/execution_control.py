"""Opt-in synchronous execution boundaries; no persistence or target policy."""

from __future__ import annotations

from typing import Protocol

from harness.core.models import (
    AttemptResult,
    RunResult,
    Score,
    TargetResponse,
    TestCase,
)


class ExecutionControlError(RuntimeError):
    """A control/evidence failure must escape ordinary target/scorer handling."""


class ExecutionControl(Protocol):
    def prepared(self, run: RunResult, cases: list[TestCase]) -> None: ...
    def reserve(self, case_id: str, index: int) -> None: ...
    def response_received(
        self, case_id: str, index: int, response: TargetResponse
    ) -> None: ...
    def scorer_recorded(
        self,
        case_id: str,
        index: int,
        name: str,
        score: Score | None,
        error: str | None,
    ) -> None: ...
    def attempt_completed(self, case_id: str, attempt: AttemptResult) -> bool:
        """Return whether dispatch may continue, after recording this attempt."""
        ...

    def run_assembled(self, run: RunResult) -> None: ...
