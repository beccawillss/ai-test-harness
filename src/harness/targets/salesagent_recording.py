"""Typed public HTTP evidence sink, injected into the Sales Agent adapter."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from harness.core.execution_control import ExecutionControlError


class SalesAgentRecorder:
    """Record already validated public evidence; never receives requests/headers."""

    def __init__(self, publish: Callable[[int, str, dict[str, Any]], None]) -> None:
        self._publish = publish

    def record(self, index: int, phase: str, evidence: dict[str, Any]) -> None:
        try:
            self._publish(index, phase, deepcopy(evidence))
        except ExecutionControlError:
            raise
        except Exception as exc:
            raise ExecutionControlError(
                "Sales Agent evidence publication failed"
            ) from exc
