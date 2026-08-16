"""SQLite persistence for complete evaluation results."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from harness.core.models import CaseResult, RunResult, Verdict


@dataclass(frozen=True, slots=True)
class RunSummary:
    """Run-level metadata available without loading the full result."""

    run_id: str
    started_at: datetime
    finished_at: datetime | None
    target_name: str
    dataset_hash: str
    aggregate_pass_rate: float | None
    error_rate: float


class SQLiteResultStore:
    """Persist immutable RunResult documents in a local SQLite database."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    target_name TEXT NOT NULL,
                    dataset_hash TEXT NOT NULL,
                    aggregate_pass_rate REAL,
                    error_rate REAL NOT NULL,
                    result_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS runs_started_at
                ON runs(started_at DESC);
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def save(self, result: RunResult) -> None:
        """Store one completed run, rejecting duplicate run IDs."""
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO runs (
                        run_id,
                        started_at,
                        finished_at,
                        target_name,
                        dataset_hash,
                        aggregate_pass_rate,
                        error_rate,
                        result_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result.run_id,
                        result.started_at.isoformat(),
                        (
                            result.finished_at.isoformat()
                            if result.finished_at is not None
                            else None
                        ),
                        result.target_name,
                        result.dataset_hash,
                        result.aggregate_pass_rate,
                        result.error_rate,
                        result.model_dump_json(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Run '{result.run_id}' is already stored.") from exc

    def load(self, run_id: str) -> RunResult:
        """Load a complete run by ID."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT result_json FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Run '{run_id}' was not found.")
        return RunResult.model_validate_json(row["result_json"])

    def list_runs(self) -> list[RunSummary]:
        """List lightweight run summaries, newest first."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    run_id,
                    started_at,
                    finished_at,
                    target_name,
                    dataset_hash,
                    aggregate_pass_rate,
                    error_rate
                FROM runs
                ORDER BY started_at DESC, run_id DESC
                """
            ).fetchall()

        return [
            RunSummary(
                run_id=row["run_id"],
                started_at=datetime.fromisoformat(row["started_at"]),
                finished_at=(
                    datetime.fromisoformat(row["finished_at"])
                    if row["finished_at"] is not None
                    else None
                ),
                target_name=row["target_name"],
                dataset_hash=row["dataset_hash"],
                aggregate_pass_rate=row["aggregate_pass_rate"],
                error_rate=row["error_rate"],
            )
            for row in rows
        ]

    def problem_cases(self, run_id: str) -> list[CaseResult]:
        """Return cases containing a quality failure or infrastructure error."""
        result = self.load(run_id)
        return [
            case
            for case in result.cases
            if any(
                attempt.verdict in (Verdict.FAIL, Verdict.ERROR)
                for attempt in case.attempts
            )
        ]


__all__ = ["RunSummary", "SQLiteResultStore"]
