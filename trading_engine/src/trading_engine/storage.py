from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from trading_engine.errors import StorageError
from trading_engine.models import ReplayRun


class ReplayStore:
    def __init__(self, database: Path) -> None:
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def create_run(
        self,
        trading_date: date,
        codes: tuple[str, ...],
        initial_time: datetime,
    ) -> ReplayRun:
        run_id = uuid4().hex
        now = datetime.now().astimezone()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    id, trading_date, codes_json, replay_time, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'running', ?, ?)
                """,
                (
                    run_id,
                    trading_date.isoformat(),
                    json.dumps(codes),
                    initial_time.isoformat(),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            connection.execute(
                """
                INSERT INTO checkpoints (run_id, replay_time, state_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    run_id,
                    initial_time.isoformat(),
                    json.dumps({"phase": "initialized"}),
                    now.isoformat(),
                ),
            )
        return self.get_run(run_id)

    def record_checkpoint(
        self,
        run_id: str,
        replay_time: datetime,
        state: dict[str, Any],
        status: str,
    ) -> ReplayRun:
        now = datetime.now().astimezone()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO checkpoints (
                        run_id, replay_time, state_json, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        replay_time.isoformat(),
                        json.dumps(state, ensure_ascii=False, sort_keys=True),
                        now.isoformat(),
                    ),
                )
                cursor = connection.execute(
                    """
                    UPDATE runs
                    SET replay_time = ?, status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (replay_time.isoformat(), status, now.isoformat(), run_id),
                )
                if cursor.rowcount != 1:
                    raise StorageError(f"replay run does not exist: {run_id}")
        except sqlite3.IntegrityError as exc:
            raise StorageError(
                f"checkpoint already exists for {run_id} at {replay_time.isoformat()}"
            ) from exc
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> ReplayRun:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise StorageError(f"replay run does not exist: {run_id}")
        return _run_from_row(row)

    def latest_run(self, statuses: Iterable[str] | None = None) -> ReplayRun | None:
        parameters: tuple[str, ...] = ()
        query = "SELECT * FROM runs"
        if statuses is not None:
            status_values = tuple(statuses)
            if not status_values:
                return None
            placeholders = ",".join("?" for _ in status_values)
            query += f" WHERE status IN ({placeholders})"
            parameters = status_values
        query += " ORDER BY created_at DESC LIMIT 1"

        with self._connect() as connection:
            row = connection.execute(query, parameters).fetchone()
        return _run_from_row(row) if row is not None else None

    def checkpoint_count(self, run_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM checkpoints WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return int(row["count"])

    def _initialize(self) -> None:
        with self._connect() as connection:
            existing_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(runs)").fetchall()
            }
            if "current_time" in existing_columns and "replay_time" not in existing_columns:
                connection.execute(
                    "ALTER TABLE runs RENAME COLUMN current_time TO replay_time"
                )
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    trading_date TEXT NOT NULL,
                    codes_json TEXT NOT NULL,
                    replay_time TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('running', 'paused', 'completed', 'failed')
                    ),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(id),
                    replay_time TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (run_id, replay_time)
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _run_from_row(row: sqlite3.Row) -> ReplayRun:
    return ReplayRun(
        id=row["id"],
        trading_date=date.fromisoformat(row["trading_date"]),
        codes=tuple(json.loads(row["codes_json"])),
        current_time=datetime.fromisoformat(row["replay_time"]),
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )
