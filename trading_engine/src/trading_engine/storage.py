from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from trading_engine.errors import StorageError
from trading_engine.models import (
    AccountState,
    JudgmentContext,
    JudgmentRecord,
    JudgmentReport,
    LiveSnapshotRecord,
    MarketSnapshot,
    PositionState,
    ReplayRun,
)


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

    def record_live_snapshot(self, snapshot: MarketSnapshot) -> LiveSnapshotRecord:
        snapshot_id = uuid4().hex
        codes = [row["code"] for row in snapshot.payload.get("quotes", [])]
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO live_snapshots (
                    id, observed_at, codes_json, snapshot_json
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    snapshot.as_of.isoformat(),
                    json.dumps(codes),
                    snapshot.model_dump_json(),
                ),
            )
        return LiveSnapshotRecord(id=snapshot_id, snapshot=snapshot)

    def latest_live_snapshot(self) -> LiveSnapshotRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, snapshot_json
                FROM live_snapshots
                ORDER BY observed_at DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return LiveSnapshotRecord(
            id=row["id"],
            snapshot=MarketSnapshot.model_validate_json(row["snapshot_json"]),
        )

    def record_judgment(
        self,
        snapshot_id: str,
        context: JudgmentContext,
        report: JudgmentReport,
        provider: str,
        model: str,
        attempts: int,
    ) -> JudgmentRecord:
        judgment_id = uuid4().hex
        created_at = datetime.now().astimezone()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO judgments (
                    id, snapshot_id, provider, model, status, attempts,
                    input_json, output_json, error, created_at
                ) VALUES (?, ?, ?, ?, 'completed', ?, ?, ?, NULL, ?)
                """,
                (
                    judgment_id,
                    snapshot_id,
                    provider,
                    model,
                    attempts,
                    context.model_dump_json(),
                    report.model_dump_json(),
                    created_at.isoformat(),
                ),
            )
        return JudgmentRecord(
            id=judgment_id,
            snapshot_id=snapshot_id,
            provider=provider,
            model=model,
            status="completed",
            attempts=attempts,
            input_context=context,
            report=report,
            created_at=created_at,
        )

    def record_failed_judgment(
        self,
        snapshot_id: str,
        context: JudgmentContext,
        provider: str,
        model: str,
        attempts: int,
        error: str,
    ) -> JudgmentRecord:
        judgment_id = uuid4().hex
        created_at = datetime.now().astimezone()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO judgments (
                    id, snapshot_id, provider, model, status, attempts,
                    input_json, output_json, error, created_at
                ) VALUES (?, ?, ?, ?, 'failed', ?, ?, NULL, ?, ?)
                """,
                (
                    judgment_id,
                    snapshot_id,
                    provider,
                    model,
                    attempts,
                    context.model_dump_json(),
                    error,
                    created_at.isoformat(),
                ),
            )
        return JudgmentRecord(
            id=judgment_id,
            snapshot_id=snapshot_id,
            provider=provider,
            model=model,
            status="failed",
            attempts=attempts,
            input_context=context,
            error=error,
            created_at=created_at,
        )

    def latest_judgment(self) -> JudgmentRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM judgments
                ORDER BY created_at DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return JudgmentRecord(
            id=row["id"],
            snapshot_id=row["snapshot_id"],
            provider=row["provider"],
            model=row["model"],
            status=row["status"],
            attempts=row["attempts"],
            input_context=JudgmentContext.model_validate_json(row["input_json"]),
            report=(
                JudgmentReport.model_validate_json(row["output_json"])
                if row["output_json"]
                else None
            ),
            error=row["error"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def create_account(
        self,
        name: str,
        initial_cash: Decimal,
        cash: Decimal | None = None,
    ) -> AccountState:
        normalized_name = name.strip()
        if not normalized_name:
            raise StorageError("account name cannot be empty")
        initial_cash_cents = _money_to_cents(initial_cash, "initial_cash")
        cash_cents = _money_to_cents(
            initial_cash if cash is None else cash, "cash"
        )
        account_id = uuid4().hex
        now = datetime.now().astimezone()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO accounts (
                        id, name, initial_cash_cents, cash_cents, cooldown,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 0, ?, ?)
                    """,
                    (
                        account_id,
                        normalized_name,
                        initial_cash_cents,
                        cash_cents,
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise StorageError(f"account already exists: {normalized_name}") from exc
        return self.get_account(normalized_name)

    def get_account(self, name: str) -> AccountState:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM accounts WHERE name = ?", (name.strip(),)
            ).fetchone()
        if row is None:
            raise StorageError(f"account does not exist: {name.strip()}")
        return _account_from_row(row)

    def update_account(
        self,
        name: str,
        cash: Decimal | None = None,
        cooldown: bool | None = None,
    ) -> AccountState:
        if cash is None and cooldown is None:
            raise StorageError("account update requires --cash or a cooldown option")
        assignments = []
        parameters: list[Any] = []
        if cash is not None:
            assignments.append("cash_cents = ?")
            parameters.append(_money_to_cents(cash, "cash"))
        if cooldown is not None:
            assignments.append("cooldown = ?")
            parameters.append(int(cooldown))
        assignments.append("updated_at = ?")
        parameters.append(datetime.now().astimezone().isoformat())
        parameters.append(name.strip())
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE accounts SET {', '.join(assignments)} WHERE name = ?",
                parameters,
            )
            if cursor.rowcount != 1:
                raise StorageError(f"account does not exist: {name.strip()}")
        return self.get_account(name)

    def upsert_position(
        self,
        account_name: str,
        code: str,
        name: str,
        quantity: int,
        sellable_quantity: int,
        average_cost: Decimal,
        bought_on: date,
    ) -> PositionState:
        normalized_code = code.strip()
        normalized_name = name.strip()
        if len(normalized_code) != 6 or not normalized_code.isdigit():
            raise StorageError(f"invalid stock code: {normalized_code}")
        if not normalized_name:
            raise StorageError("position name cannot be empty")
        if quantity <= 0:
            raise StorageError("position quantity must be greater than zero")
        if sellable_quantity < 0 or sellable_quantity > quantity:
            raise StorageError(
                "sellable quantity must be between zero and total quantity"
            )
        average_cost_cents = _money_to_cents(
            average_cost, "average_cost", allow_zero=False
        )
        now = datetime.now().astimezone()
        with self._connect() as connection:
            account = connection.execute(
                "SELECT id FROM accounts WHERE name = ?", (account_name.strip(),)
            ).fetchone()
            if account is None:
                raise StorageError(f"account does not exist: {account_name.strip()}")
            connection.execute(
                """
                INSERT INTO positions (
                    account_id, code, name, quantity, sellable_quantity,
                    average_cost_cents, bought_on, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id, code) DO UPDATE SET
                    name = excluded.name,
                    quantity = excluded.quantity,
                    sellable_quantity = excluded.sellable_quantity,
                    average_cost_cents = excluded.average_cost_cents,
                    bought_on = excluded.bought_on,
                    updated_at = excluded.updated_at
                """,
                (
                    account["id"],
                    normalized_code,
                    normalized_name,
                    quantity,
                    sellable_quantity,
                    average_cost_cents,
                    bought_on.isoformat(),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
        return self.get_position(account_name, normalized_code)

    def get_position(self, account_name: str, code: str) -> PositionState:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT positions.*
                FROM positions
                JOIN accounts ON accounts.id = positions.account_id
                WHERE accounts.name = ? AND positions.code = ?
                """,
                (account_name.strip(), code.strip()),
            ).fetchone()
        if row is None:
            raise StorageError(
                f"position does not exist: {account_name.strip()}/{code.strip()}"
            )
        return _position_from_row(row)

    def list_positions(self, account_name: str) -> tuple[PositionState, ...]:
        account = self.get_account(account_name)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM positions
                WHERE account_id = ?
                ORDER BY code
                """,
                (account.id,),
            ).fetchall()
        return tuple(_position_from_row(row) for row in rows)

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

                CREATE TABLE IF NOT EXISTS live_snapshots (
                    id TEXT PRIMARY KEY,
                    observed_at TEXT NOT NULL,
                    codes_json TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS judgments (
                    id TEXT PRIMARY KEY,
                    snapshot_id TEXT NOT NULL REFERENCES live_snapshots(id),
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
                    attempts INTEGER NOT NULL CHECK (attempts >= 1),
                    input_json TEXT NOT NULL,
                    output_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    initial_cash_cents INTEGER NOT NULL CHECK (
                        initial_cash_cents >= 0
                    ),
                    cash_cents INTEGER NOT NULL CHECK (cash_cents >= 0),
                    cooldown INTEGER NOT NULL DEFAULT 0 CHECK (
                        cooldown IN (0, 1)
                    ),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS positions (
                    account_id TEXT NOT NULL REFERENCES accounts(id),
                    code TEXT NOT NULL CHECK (
                        length(code) = 6 AND code NOT GLOB '*[^0-9]*'
                    ),
                    name TEXT NOT NULL,
                    quantity INTEGER NOT NULL CHECK (quantity > 0),
                    sellable_quantity INTEGER NOT NULL CHECK (
                        sellable_quantity >= 0 AND sellable_quantity <= quantity
                    ),
                    average_cost_cents INTEGER NOT NULL CHECK (
                        average_cost_cents > 0
                    ),
                    bought_on TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (account_id, code)
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


def _money_to_cents(
    value: Decimal, field: str, allow_zero: bool = True
) -> int:
    if not value.is_finite():
        raise StorageError(f"{field} must be a finite amount")
    cents = value * 100
    if cents != cents.to_integral_value():
        raise StorageError(f"{field} must have at most two decimal places")
    result = int(cents)
    if result < 0 or (not allow_zero and result == 0):
        comparator = "non-negative" if allow_zero else "greater than zero"
        raise StorageError(f"{field} must be {comparator}")
    return result


def _account_from_row(row: sqlite3.Row) -> AccountState:
    return AccountState(
        id=row["id"],
        name=row["name"],
        initial_cash=Decimal(row["initial_cash_cents"]) / 100,
        cash=Decimal(row["cash_cents"]) / 100,
        cooldown=bool(row["cooldown"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _position_from_row(row: sqlite3.Row) -> PositionState:
    return PositionState(
        account_id=row["account_id"],
        code=row["code"],
        name=row["name"],
        quantity=row["quantity"],
        sellable_quantity=row["sellable_quantity"],
        average_cost=Decimal(row["average_cost_cents"]) / 100,
        bought_on=date.fromisoformat(row["bought_on"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )
