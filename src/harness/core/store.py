"""Persisting RunResults.

A run that isn't stored can't be compared, and comparison is the entire
value of an eval harness — a single run tells you almost nothing without
a baseline to read it against.

`Store` is a Protocol so the storage decision stays reversible: JSON files
are right for a laptop and a git-ignored directory, SQLite will be right
once there are enough runs to want trend queries, and the runner never
needs to know which it got.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol, runtime_checkable

from harness.core.errors import HarnessError
from harness.core.models import RunResult


class RunNotFoundError(HarnessError):
    """No stored run with that id."""


@runtime_checkable
class Store(Protocol):
    """Somewhere RunResults live."""

    def save(self, result: RunResult) -> str:
        """Persist a result; return a locator (path, uri, row id)."""
        ...

    def load(self, run_id: str) -> RunResult: ...

    def list_runs(self) -> list[str]: ...


class JsonRunStore:
    """One JSON file per run, named by run_id.

    Writes go to a temp file and are then os.replace'd, which is atomic on
    POSIX and Windows. A run killed mid-write leaves the previous file
    intact rather than a truncated one that fails to parse months later.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _path(self, run_id: str) -> Path:
        return self.root / f"{run_id}.json"

    def save(self, result: RunResult) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        destination = self._path(result.run_id)
        temporary = destination.with_suffix(".json.tmp")
        temporary.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        os.replace(temporary, destination)
        return str(destination)

    def load(self, run_id: str) -> RunResult:
        path = self._path(run_id)
        try:
            payload = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise RunNotFoundError(f"No run '{run_id}' in {self.root}") from exc
        return RunResult.model_validate_json(payload)

    def list_runs(self) -> list[str]:
        """Run ids present, newest first by file mtime."""
        if not self.root.is_dir():
            return []
        files = sorted(
            self.root.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return [p.stem for p in files]


__all__ = ["JsonRunStore", "RunNotFoundError", "Store"]
