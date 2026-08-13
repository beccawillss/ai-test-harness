"""The Target Protocol: the harness's contract with any system-under-test.
 
Why a Protocol instead of an ABC: adapters shouldn't need to import or
inherit from the harness to satisfy the interface. Your RAG app can ship
its own adapter class that just *happens* to match this shape, and
`isinstance(obj, Target)` still works thanks to @runtime_checkable.
That keeps the dependency arrow pointing the right way - apps depend on
the harness only if they want to, never the reverse.
"""
 
from __future__ import annotations
 
from typing import Any, Protocol, runtime_checkable
 
from harness.core.models import TargetResponse, TestCase

@runtime_checkable
class Target(Protocol):
    """Anything the harness can evaluate.
 
    Contract:
    - `name` identifies the adapter in configs, results, and reports.
      Include a version if the system-under-test is versioned
      (e.g. "cap-rag@v3") — regression comparisons are meaningless
      without knowing exactly what was tested.
    - `capabilities` declares which optional TargetResponse fields this
      adapter populates ("contexts", "trajectory"). The runner checks a
      pack's requirements against this *before* executing anything, so a
      RAG pack pointed at a plain model adapter fails fast at config
      time, not with cryptic scorer errors halfway through a paid run.
    - `invoke` executes exactly one case and must be safe to call
      repeatedly: attempts for stability measurement, retries, and
      parallel execution all assume no shared mutable state between
      calls.
    - Raise exceptions freely; the runner catches them and records
      Verdict.ERROR. Do not swallow errors into fake responses.
    """

    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> set[str]: ...

    def invoke(self, case: TestCase) -> TargetResponse: ...


@runtime_checkable
class CloseableTarget(Target, Protocol):
    """Optional extension for adapters holding real resources
    (http sessions, sandboxes, browser contexts). The runner
    calls `close()` in a finally block if the adapter provides it.
    """

    def close(self) -> None: ...


def check_pack_compatibility(
    target: Target, required_capabilities: frozenset[str]
) -> list[str]:
    """Return the capabilities a pack needs that the target lacks.

    Called by the runner during config validation. An empty list means the pairing
    is valid. Kept here (not in the runner) so adapters can self-check in their own
    test suites.
    """
    return sorted(required_capabilities - target.capabilities)

class StaticTarget:
    """A canned response target for testing the harness itself.

    Feed it {case_id: TargetResponse} and it replays them. This 
    is the workhorse of the harness's own pytest suite: scorers, 
    the runner, regression comparison, and reporting can all be
    tested offline, deterministically, and for free.
    """

    def __init__(
        self,
        responses: dict[str, TargetResponse],
        name: str = "static",
        capabilities: frozenset[str] = frozenset(),
    ) -> None:
        self._responses = responses
        self._name = name
        self._capabilities = capabilities
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return self._name
    
    @property
    def capabilities(self) -> frozenset[str]:
        return self._capabilities
    
    def invoke(self, case: TestCase) -> TargetResponse:
        self.calls.append(case.id)
        try:
            return self._responses[case.id]
        except KeyError as exc:
            raise LookupError(
                f"StaticTarget has no canned response for case '{case.id}'"
            ) from exc

# Capability names used by the built-in packs. Plain strings by design -
# packs may define new ones without touching this file.
CAP_CONTEXTS = "contexts"      # populates TargetResponse.contexts (RAG)
CAP_TRAJECTORY = "trajectory"  # populates TargetResponse.trajectory (agents)
 
 
__all__ = [
    "Target",
    "CloseableTarget",
    "StaticTarget",
    "check_pack_compatibility",
    "CAP_CONTEXTS",
    "CAP_TRAJECTORY",
]