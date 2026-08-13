"""The description of a run: what to execute and how, not what to execute it against.

`RunConfig` deliberately does not name the target or the pack. Those are
passed to the runner as objects, so there is exactly one source of truth
for their identity (`target.name`, `pack.name`) and no way for a config
file to disagree with what actually ran. A registry that resolves names
to objects can be layered on later without changing this model.

Stdlib + pydantic only — core stays dependency-free, so the YAML loader
lives outside it in harness/config_io.py.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from harness.core.models import ScorerKind


class RunMode(StrEnum):
    """What a run is for."""

    SCORE = "score"
    EXPLORE = "explore"
    """Execute the target and capture what comes back; run no scorers.

    For looking at a new adapter before paying to score with it: does it
    populate `contexts`? What does the trajectory actually contain? Every
    attempt is recorded as SKIP, so an explore run reports no pass rate
    rather than a misleading 0%.
    """


class RunConfig(BaseModel):
    """Everything about a run except the target, pack, and cases."""

    config_path: str = "<inline>"
    """Provenance, recorded into RunResult. "<inline>" when built in code."""

    dataset_path: str = "<inline>"
    """Provenance only — the runner is handed cases, it does not load them."""

    mode: RunMode = RunMode.SCORE
    attempts: int = Field(default=1, ge=1)
    """Executions per case. >1 measures stability; pass rates are the point."""

    concurrency: int = Field(default=1, ge=1)
    """Reserved. Values >1 raise NotImplementedError until parallel
    execution lands in its own change — see validate_run."""

    scorer_kinds: frozenset[ScorerKind] | None = None
    """Restrict the pack to these kinds. None runs everything;
    {ScorerKind.DETERMINISTIC} is the cheap PR smoke suite."""

    include_tags: list[str] = Field(default_factory=list)
    """Keep only cases carrying at least one of these tags. Empty = keep all."""

    exclude_tags: list[str] = Field(default_factory=list)
    """Drop cases carrying any of these tags. Applied before include_tags."""

    max_cases: int | None = Field(default=None, ge=1)
    """Truncate after filtering. For smoke runs against a large golden set."""

    model_versions: dict[str, str] = Field(default_factory=dict)
    """Pinned target model ids, merged into RunResult.model_versions. Judge
    models are discovered from the scorers themselves."""


__all__ = ["RunConfig", "RunMode"]
