"""SQLite persistence for complete evaluation results."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from harness.core.fingerprints import fingerprint
from harness.core.models import CaseResult, RunResult, Verdict
from harness.core.replay import ReplayResult


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

    def __init__(self, path: str | Path, *, read_only: bool = False) -> None:
        self.path = Path(path)
        self.read_only = read_only
        if read_only:
            # Opening checks existence/access without creating a directory or schema.
            with self._connect():
                pass
            return
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
        connection = (
            sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)
            if self.read_only
            else sqlite3.connect(self.path)
        )
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
        self._require_writable()
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
        return self.load_with_fingerprint(run_id)[0]

    def load_with_fingerprint(self, run_id: str) -> tuple[RunResult, str]:
        """Load and fingerprint the same stored JSON document in one read."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT result_json FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Run '{run_id}' was not found.")
        document = row["result_json"]
        return RunResult.model_validate_json(document), fingerprint(
            json.loads(document)
        )

    def _require_writable(self) -> None:
        if self.read_only:
            raise ValueError("Cannot write to a read-only result store")

    def save_replay(self, result: ReplayResult) -> None:
        """Insert a new replay; never overwrite a run or an existing replay."""
        self._require_writable()
        result = ReplayResult.model_validate_json(result.model_dump_json())
        try:
            with self._connect() as connection:
                # Lazy DDL leaves existing run-store initialization unchanged.
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS replays (
                        replay_id TEXT PRIMARY KEY, source_run_id TEXT NOT NULL,
                        source_case_id TEXT NOT NULL, source_attempt_index INTEGER NOT NULL,
                        response_hash TEXT NOT NULL, input_hash TEXT NOT NULL,
                        started_at TEXT NOT NULL, finished_at TEXT NOT NULL,
                        result_json TEXT NOT NULL
                    )
                """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS replays_source
                    ON replays(source_run_id, source_case_id, source_attempt_index)
                """)
                connection.execute(
                    """
                    INSERT INTO replays VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        result.replay_id,
                        result.input.source.run_id,
                        result.input.source.case_id,
                        result.input.source.attempt_index,
                        result.input.source.response_hash,
                        result.input.input_hash,
                        result.started_at.isoformat(),
                        result.finished_at.isoformat(),
                        result.model_dump_json(),
                    ),
                )
        except sqlite3.IntegrityError:
            raise ValueError("Replay ID is already stored") from None

    def load_replay(self, replay_id: str) -> ReplayResult:
        with self._connect() as connection:
            if not self._has_replays(connection):
                raise KeyError("Replay not found")
            row = connection.execute(
                "SELECT result_json FROM replays WHERE replay_id = ?", (replay_id,)
            ).fetchone()
        if row is None:
            raise KeyError("Replay not found")
        return ReplayResult.model_validate_json(row["result_json"])

    @staticmethod
    def _has_replays(connection: sqlite3.Connection) -> bool:
        return (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'replays'"
            ).fetchone()
            is not None
        )

    def list_replays(self) -> list[dict[str, str | int]]:
        """Share-safe lightweight provenance; never load prompts in a listing."""
        with self._connect() as connection:
            if not self._has_replays(connection):
                return []
            rows = connection.execute("""
                SELECT replay_id, source_run_id, source_case_id, source_attempt_index,
                    response_hash, input_hash, started_at, finished_at
                FROM replays ORDER BY started_at DESC, replay_id DESC
            """).fetchall()
        return [dict(row) for row in rows]

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
