from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import uuid4

from trading_engine.trading.paper_models import PaperReportPaths
from trading_engine.trading.paper_store import PaperStore
from trading_engine.store.storage import ReplayStore


class PaperReportGenerator:
    def __init__(
        self,
        store: ReplayStore,
        paper_store: PaperStore,
        report_root: Path,
    ) -> None:
        self.store = store
        self.paper_store = paper_store
        self.report_root = report_root

    def generate(
        self, account_name: str, trading_date: date
    ) -> PaperReportPaths:
        account = self.store.get_account(account_name)
        positions = self.store.list_positions(account_name)
        orders = self.paper_store.list_orders(account_name)
        fills = self.paper_store.list_fills(account_name)
        events = self.paper_store.list_events(account_name)
        audit = self.paper_store.audit_account(account_name)

        directory = self.report_root / _safe_component(account.name)
        state_path = directory / "state.md"
        trades_path = directory / "trades.md"
        daily_path = directory / f"{trading_date.isoformat()}-shadow.md"

        state_lines = [
            f"# Paper Account: {account.name}",
            "",
            f"- Account ID: `{account.id}`",
            f"- Initial cash: CNY {account.initial_cash:,.2f}",
            f"- Current cash: CNY {account.cash:,.2f}",
            f"- Cooldown: `{str(account.cooldown).lower()}`",
            f"- Updated at: `{account.updated_at.isoformat()}`",
            f"- Audit valid: `{str(audit.valid).lower()}`",
            "",
            "## Positions",
            "",
            "| Code | Name | Quantity | Sellable | Average cost | Bought on |",
            "|---|---|---:|---:|---:|---|",
        ]
        state_lines.extend(
            "| "
            f"{position.code} | {_escape(position.name)} | {position.quantity} | "
            f"{position.sellable_quantity} | {position.average_cost:.2f} | "
            f"{position.bought_on.isoformat()} |"
            for position in positions
        )
        if not positions:
            state_lines.append("| - | - | 0 | 0 | 0.00 | - |")

        trade_lines = [
            f"# Paper Trades: {account.name}",
            "",
            "| Time | Code | Side | Quantity | Price | Notional | Order |",
            "|---|---|---|---:|---:|---:|---|",
        ]
        trade_lines.extend(
            "| "
            f"{fill.filled_at.isoformat()} | {fill.code} | {fill.side} | "
            f"{fill.quantity} | {fill.price:.2f} | {fill.notional:.2f} | "
            f"`{fill.order_id}` |"
            for fill in fills
        )
        if not fills:
            trade_lines.append("| - | - | - | 0 | 0.00 | 0.00 | - |")

        day_events = tuple(
            event for event in events if event.trade_date == trading_date
        )
        day_orders = tuple(
            order for order in orders if order.trade_date == trading_date
        )
        day_fills = tuple(
            fill for fill in fills if fill.filled_at.date() == trading_date
        )
        daily_lines = [
            f"# Daily Paper Shadow Report: {trading_date.isoformat()}",
            "",
            f"- Account: `{account.name}`",
            f"- Decision events: {len(day_events)}",
            f"- Orders: {len(day_orders)}",
            f"- Fills: {len(day_fills)}",
            f"- Account audit valid: `{str(audit.valid).lower()}`",
            "",
            "## Decision Events",
            "",
            "| Code | Action | Status | Reason | Order |",
            "|---|---|---|---|---|",
        ]
        daily_lines.extend(
            "| "
            f"{event.code} | {event.action} | {event.status} | "
            f"{_escape(event.reason)} | `{event.order_id or '-'}` |"
            for event in day_events
        )
        if not day_events:
            daily_lines.append("| - | - | - | No decisions | - |")
        daily_lines.extend(
            (
                "",
                "## Orders",
                "",
                "| Code | Side | Quantity | Price | Status | Rejection |",
                "|---|---|---:|---:|---|---|",
            )
        )
        daily_lines.extend(
            "| "
            f"{order.code} | {order.side} | {order.quantity} | "
            f"{order.price:.2f} | {order.status} | "
            f"{_escape(order.rejection_reason or '-')} |"
            for order in day_orders
        )
        if not day_orders:
            daily_lines.append("| - | - | 0 | 0.00 | - | - |")
        if audit.issues:
            daily_lines.extend(("", "## Audit Issues", ""))
            daily_lines.extend(f"- `{issue}`" for issue in audit.issues)

        _atomic_write(state_path, "\n".join(state_lines) + "\n")
        _atomic_write(trades_path, "\n".join(trade_lines) + "\n")
        _atomic_write(daily_path, "\n".join(daily_lines) + "\n")
        return PaperReportPaths(
            state=str(state_path),
            trades=str(trades_path),
            daily=str(daily_path),
        )


def _safe_component(value: str) -> str:
    normalized = "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in value.strip()
    )
    return normalized or "account"


def _escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
