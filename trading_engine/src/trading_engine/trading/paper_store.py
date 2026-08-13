from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterator

from trading_engine.errors import StorageError
from trading_engine.trading.paper_models import (
    PaperAccountAudit,
    PaperDecisionEvent,
    PaperExecutionResult,
    PaperFill,
    PaperOrder,
    PaperOrderAudit,
    PaperPolicy,
    PaperRuleCheck,
)


class PaperStore:
    def __init__(self, database: Path) -> None:
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def find_execution(
        self, account_name: str, judgment_id: str
    ) -> PaperExecutionResult | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT paper_executions.id
                FROM paper_executions
                JOIN accounts ON accounts.id = paper_executions.account_id
                WHERE accounts.name = ? AND paper_executions.judgment_id = ?
                """,
                (account_name.strip(), judgment_id),
            ).fetchone()
        return self.get_execution(row["id"]) if row is not None else None

    def get_execution(self, execution_id: str) -> PaperExecutionResult:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT paper_executions.*, accounts.name AS account_name
                FROM paper_executions
                JOIN accounts ON accounts.id = paper_executions.account_id
                WHERE paper_executions.id = ?
                """,
                (execution_id,),
            ).fetchone()
            if row is None:
                raise StorageError(f"paper execution does not exist: {execution_id}")
            events = connection.execute(
                """
                SELECT * FROM paper_decision_events
                WHERE execution_id = ? ORDER BY proposal_index
                """,
                (execution_id,),
            ).fetchall()
            orders = connection.execute(
                """
                SELECT paper_orders.*, accounts.name AS account_name
                FROM paper_orders
                JOIN accounts ON accounts.id = paper_orders.account_id
                WHERE paper_orders.execution_id = ? ORDER BY proposal_index
                """,
                (execution_id,),
            ).fetchall()
            fills = connection.execute(
                """
                SELECT paper_fills.*, accounts.name AS account_name,
                       paper_orders.proposal_index
                FROM paper_fills
                JOIN accounts ON accounts.id = paper_fills.account_id
                JOIN paper_orders ON paper_orders.id = paper_fills.order_id
                WHERE paper_orders.execution_id = ?
                ORDER BY paper_orders.proposal_index
                """,
                (execution_id,),
            ).fetchall()
            check_rows = connection.execute(
                """
                SELECT paper_rule_checks.*
                FROM paper_rule_checks
                JOIN paper_orders ON paper_orders.id = paper_rule_checks.order_id
                WHERE paper_orders.execution_id = ?
                ORDER BY paper_orders.proposal_index, paper_rule_checks.ordinal
                """,
                (execution_id,),
            ).fetchall()

        checks: dict[str, list[PaperRuleCheck]] = {}
        for check_row in check_rows:
            checks.setdefault(check_row["order_id"], []).append(
                _check_from_row(check_row)
            )
        return PaperExecutionResult(
            id=row["id"],
            account_id=row["account_id"],
            account_name=row["account_name"],
            judgment_id=row["judgment_id"],
            context_id=row["context_id"],
            snapshot_id=row["snapshot_id"],
            policy=PaperPolicy.model_validate_json(row["policy_json"]),
            status=row["status"],
            events=tuple(_event_from_row(item) for item in events),
            orders=tuple(_order_from_row(item) for item in orders),
            fills=tuple(_fill_from_row(item) for item in fills),
            checks={key: tuple(value) for key, value in checks.items()},
            created_at=datetime.fromisoformat(row["created_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]),
        )

    def list_orders(self, account_name: str) -> tuple[PaperOrder, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT paper_orders.*, accounts.name AS account_name
                FROM paper_orders
                JOIN accounts ON accounts.id = paper_orders.account_id
                WHERE accounts.name = ?
                ORDER BY paper_orders.created_at, paper_orders.proposal_index
                """,
                (account_name.strip(),),
            ).fetchall()
        return tuple(_order_from_row(row) for row in rows)

    def list_fills(self, account_name: str) -> tuple[PaperFill, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT paper_fills.*, accounts.name AS account_name,
                       paper_orders.proposal_index,
                       paper_executions.created_at AS execution_created_at
                FROM paper_fills
                JOIN accounts ON accounts.id = paper_fills.account_id
                JOIN paper_orders ON paper_orders.id = paper_fills.order_id
                JOIN paper_executions
                  ON paper_executions.id = paper_orders.execution_id
                WHERE accounts.name = ?
                ORDER BY paper_executions.created_at, paper_orders.proposal_index
                """,
                (account_name.strip(),),
            ).fetchall()
        return tuple(_fill_from_row(row) for row in rows)

    def list_events(self, account_name: str) -> tuple[PaperDecisionEvent, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT paper_decision_events.*
                FROM paper_decision_events
                JOIN paper_executions
                  ON paper_executions.id = paper_decision_events.execution_id
                JOIN accounts ON accounts.id = paper_executions.account_id
                WHERE accounts.name = ?
                ORDER BY paper_executions.created_at,
                         paper_decision_events.proposal_index
                """,
                (account_name.strip(),),
            ).fetchall()
        return tuple(_event_from_row(row) for row in rows)

    def audit_order(self, order_id: str) -> PaperOrderAudit:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT paper_orders.*, accounts.name AS account_name
                FROM paper_orders
                JOIN accounts ON accounts.id = paper_orders.account_id
                WHERE paper_orders.id = ?
                """,
                (order_id,),
            ).fetchone()
            if row is None:
                raise StorageError(f"paper order does not exist: {order_id}")
            check_rows = connection.execute(
                """
                SELECT * FROM paper_rule_checks
                WHERE order_id = ? ORDER BY ordinal
                """,
                (order_id,),
            ).fetchall()
            fill_row = connection.execute(
                """
                SELECT paper_fills.*, accounts.name AS account_name
                FROM paper_fills
                JOIN accounts ON accounts.id = paper_fills.account_id
                WHERE paper_fills.order_id = ?
                """,
                (order_id,),
            ).fetchone()

        order = _order_from_row(row)
        checks = tuple(_check_from_row(item) for item in check_rows)
        fill = _fill_from_row(fill_row) if fill_row is not None else None
        issues = _order_issues(order, checks, fill)
        return PaperOrderAudit(
            order=order,
            checks=checks,
            fill=fill,
            valid=not issues,
            issues=issues,
        )

    def audit_account(self, account_name: str) -> PaperAccountAudit:
        orders = self.list_orders(account_name)
        fills = self.list_fills(account_name)
        issues: list[str] = []
        for order in orders:
            order_audit = self.audit_order(order.id)
            issues.extend(
                f"order:{order.id}:{issue}" for issue in order_audit.issues
            )

        for previous, current in zip(fills, fills[1:]):
            if previous.cash_after != current.cash_before:
                issues.append(
                    f"cash_chain:{previous.order_id}->{current.order_id}"
                )
        by_code: dict[str, list[PaperFill]] = {}
        for fill in fills:
            by_code.setdefault(fill.code, []).append(fill)
        for code, code_fills in by_code.items():
            for previous, current in zip(code_fills, code_fills[1:]):
                if (
                    previous.position_quantity_after
                    != current.position_quantity_before
                ):
                    issues.append(
                        f"position_chain:{code}:{previous.order_id}"
                        f"->{current.order_id}"
                    )

        with self._connect() as connection:
            account = connection.execute(
                "SELECT * FROM accounts WHERE name = ?", (account_name.strip(),)
            ).fetchone()
            if account is None:
                raise StorageError(f"account does not exist: {account_name.strip()}")
            positions = {
                row["code"]: row
                for row in connection.execute(
                    "SELECT * FROM positions WHERE account_id = ?",
                    (account["id"],),
                ).fetchall()
            }
        if fills and _cents(fills[-1].cash_after) != account["cash_cents"]:
            issues.append("current_cash_does_not_match_last_fill")
        for code, code_fills in by_code.items():
            expected = code_fills[-1].position_quantity_after
            actual = positions[code]["quantity"] if code in positions else 0
            if expected != actual:
                issues.append(f"current_position_mismatch:{code}")

        unique_issues = tuple(dict.fromkeys(issues))
        return PaperAccountAudit(
            account_id=account["id"],
            account_name=account["name"],
            orders=len(orders),
            fills=len(fills),
            valid=not unique_issues,
            issues=unique_issues,
        )

    def settle_positions(self, account_name: str, settlement_date: date) -> int:
        now = datetime.now().astimezone().isoformat()
        with self.transaction() as connection:
            account = connection.execute(
                "SELECT id FROM accounts WHERE name = ?", (account_name.strip(),)
            ).fetchone()
            if account is None:
                raise StorageError(f"account does not exist: {account_name.strip()}")
            cursor = connection.execute(
                """
                UPDATE positions
                SET sellable_quantity = quantity, updated_at = ?
                WHERE account_id = ? AND bought_on < ?
                  AND sellable_quantity != quantity
                """,
                (now, account["id"], settlement_date.isoformat()),
            )
            if cursor.rowcount:
                connection.execute(
                    "UPDATE accounts SET updated_at = ? WHERE id = ?",
                    (now, account["id"]),
                )
            return cursor.rowcount

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS paper_executions (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES accounts(id),
                    judgment_id TEXT NOT NULL REFERENCES judgments(id),
                    context_id TEXT NOT NULL REFERENCES context_snapshots(id),
                    snapshot_id TEXT NOT NULL,
                    policy_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status = 'completed'),
                    created_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    UNIQUE (account_id, judgment_id)
                );

                CREATE TABLE IF NOT EXISTS paper_orders (
                    id TEXT PRIMARY KEY,
                    execution_id TEXT NOT NULL REFERENCES paper_executions(id),
                    judgment_id TEXT NOT NULL REFERENCES judgments(id),
                    proposal_index INTEGER NOT NULL CHECK (proposal_index >= 0),
                    account_id TEXT NOT NULL REFERENCES accounts(id),
                    snapshot_id TEXT NOT NULL,
                    context_id TEXT NOT NULL REFERENCES context_snapshots(id),
                    code TEXT NOT NULL CHECK (
                        length(code) = 6 AND code NOT GLOB '*[^0-9]*'
                    ),
                    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
                    quantity INTEGER NOT NULL CHECK (quantity > 0),
                    price_cents INTEGER NOT NULL CHECK (price_cents > 0),
                    notional_cents INTEGER NOT NULL CHECK (notional_cents > 0),
                    trade_date TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('filled', 'rejected')),
                    rejection_reason TEXT,
                    proposal_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (account_id, judgment_id, proposal_index)
                );

                CREATE TABLE IF NOT EXISTS paper_rule_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT NOT NULL REFERENCES paper_orders(id),
                    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
                    rule_name TEXT NOT NULL,
                    passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
                    message TEXT NOT NULL,
                    UNIQUE (order_id, ordinal),
                    UNIQUE (order_id, rule_name)
                );

                CREATE TABLE IF NOT EXISTS paper_fills (
                    id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL UNIQUE REFERENCES paper_orders(id),
                    account_id TEXT NOT NULL REFERENCES accounts(id),
                    code TEXT NOT NULL,
                    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
                    quantity INTEGER NOT NULL CHECK (quantity > 0),
                    price_cents INTEGER NOT NULL CHECK (price_cents > 0),
                    notional_cents INTEGER NOT NULL CHECK (notional_cents > 0),
                    cash_before_cents INTEGER NOT NULL CHECK (cash_before_cents >= 0),
                    cash_after_cents INTEGER NOT NULL CHECK (cash_after_cents >= 0),
                    position_quantity_before INTEGER NOT NULL CHECK (
                        position_quantity_before >= 0
                    ),
                    position_quantity_after INTEGER NOT NULL CHECK (
                        position_quantity_after >= 0
                    ),
                    sellable_before INTEGER NOT NULL CHECK (sellable_before >= 0),
                    sellable_after INTEGER NOT NULL CHECK (sellable_after >= 0),
                    average_cost_before_cents INTEGER,
                    average_cost_after_cents INTEGER,
                    filled_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS paper_decision_events (
                    id TEXT PRIMARY KEY,
                    execution_id TEXT NOT NULL REFERENCES paper_executions(id),
                    judgment_id TEXT NOT NULL REFERENCES judgments(id),
                    proposal_index INTEGER NOT NULL CHECK (proposal_index >= 0),
                    code TEXT NOT NULL,
                    action TEXT NOT NULL CHECK (
                        action IN ('WAIT', 'RESEARCH', 'BUY', 'SELL')
                    ),
                    status TEXT NOT NULL CHECK (
                        status IN ('skipped', 'rejected', 'filled')
                    ),
                    trade_date TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    order_id TEXT REFERENCES paper_orders(id),
                    created_at TEXT NOT NULL,
                    UNIQUE (execution_id, proposal_index)
                );

                CREATE INDEX IF NOT EXISTS paper_orders_account_date
                    ON paper_orders(account_id, trade_date);
                CREATE INDEX IF NOT EXISTS paper_fills_account_code
                    ON paper_fills(account_id, code, filled_at);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _order_from_row(row: sqlite3.Row) -> PaperOrder:
    return PaperOrder(
        id=row["id"],
        execution_id=row["execution_id"],
        judgment_id=row["judgment_id"],
        proposal_index=row["proposal_index"],
        account_id=row["account_id"],
        account_name=row["account_name"],
        snapshot_id=row["snapshot_id"],
        context_id=row["context_id"],
        code=row["code"],
        side=row["side"],
        quantity=row["quantity"],
        price=_money(row["price_cents"]),
        notional=_money(row["notional_cents"]),
        trade_date=date.fromisoformat(row["trade_date"]),
        status=row["status"],
        rejection_reason=row["rejection_reason"],
        proposal_json=row["proposal_json"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _fill_from_row(row: sqlite3.Row) -> PaperFill:
    return PaperFill(
        id=row["id"],
        order_id=row["order_id"],
        account_id=row["account_id"],
        account_name=row["account_name"],
        code=row["code"],
        side=row["side"],
        quantity=row["quantity"],
        price=_money(row["price_cents"]),
        notional=_money(row["notional_cents"]),
        cash_before=_money(row["cash_before_cents"]),
        cash_after=_money(row["cash_after_cents"]),
        position_quantity_before=row["position_quantity_before"],
        position_quantity_after=row["position_quantity_after"],
        sellable_before=row["sellable_before"],
        sellable_after=row["sellable_after"],
        average_cost_before=(
            _money(row["average_cost_before_cents"])
            if row["average_cost_before_cents"] is not None
            else None
        ),
        average_cost_after=(
            _money(row["average_cost_after_cents"])
            if row["average_cost_after_cents"] is not None
            else None
        ),
        filled_at=datetime.fromisoformat(row["filled_at"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _event_from_row(row: sqlite3.Row) -> PaperDecisionEvent:
    return PaperDecisionEvent(
        id=row["id"],
        execution_id=row["execution_id"],
        judgment_id=row["judgment_id"],
        proposal_index=row["proposal_index"],
        code=row["code"],
        action=row["action"],
        status=row["status"],
        trade_date=date.fromisoformat(row["trade_date"]),
        reason=row["reason"],
        order_id=row["order_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _check_from_row(row: sqlite3.Row) -> PaperRuleCheck:
    return PaperRuleCheck(
        name=row["rule_name"],
        passed=bool(row["passed"]),
        message=row["message"],
    )


def _order_issues(
    order: PaperOrder,
    checks: tuple[PaperRuleCheck, ...],
    fill: PaperFill | None,
) -> tuple[str, ...]:
    issues: list[str] = []
    if not checks:
        issues.append("missing_rule_checks")
    if order.notional != order.price * order.quantity:
        issues.append("order_notional_mismatch")
    if order.status == "filled":
        if fill is None:
            issues.append("filled_order_missing_fill")
        if any(not check.passed for check in checks):
            issues.append("filled_order_has_failed_check")
    else:
        if fill is not None:
            issues.append("rejected_order_has_fill")
        if checks and all(check.passed for check in checks):
            issues.append("rejected_order_has_no_failed_check")
    if fill is not None:
        if (
            fill.code != order.code
            or fill.side != order.side
            or fill.quantity != order.quantity
            or fill.price != order.price
            or fill.notional != order.notional
        ):
            issues.append("fill_does_not_match_order")
        expected_cash = (
            fill.cash_before - fill.notional
            if fill.side == "BUY"
            else fill.cash_before + fill.notional
        )
        if expected_cash != fill.cash_after:
            issues.append("fill_cash_transition_mismatch")
        expected_quantity = (
            fill.position_quantity_before + fill.quantity
            if fill.side == "BUY"
            else fill.position_quantity_before - fill.quantity
        )
        if expected_quantity != fill.position_quantity_after:
            issues.append("fill_position_transition_mismatch")
    return tuple(issues)


def _money(cents: int) -> Decimal:
    return Decimal(cents) / 100


def _cents(value: Decimal) -> int:
    return int(value * 100)
