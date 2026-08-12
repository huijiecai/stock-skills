"""Minimal trading-state summary for the brain-facing brief command."""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from typing import Any

from trading_engine.errors import StorageError
from trading_engine.paper_store import PaperStore
from trading_engine.replay import SHANGHAI_TZ
from trading_engine.storage import ReplayStore


class BriefGenerator:
    """Generate a minimal trading-state summary without fetching market data."""

    def __init__(
        self,
        store: ReplayStore,
        paper_store: PaperStore | None = None,
    ) -> None:
        self.store = store
        self.paper_store = paper_store

    def generate(self, account_name: str = "paper") -> dict[str, Any]:
        now = datetime.now(SHANGHAI_TZ)

        try:
            account = self.store.get_account(account_name)
            account_data = {
                "name": account.name,
                "cash": str(account.cash),
                "initial_cash": str(account.initial_cash),
                "cooldown": account.cooldown,
            }
        except StorageError:
            account_data = {"name": account_name, "error": "account does not exist"}

        try:
            positions = self.store.list_positions(account_name)
            position_cost = sum(
                position.quantity * position.average_cost for position in positions
            )
            positions_data = [
                {
                    "code": position.code,
                    "name": position.name,
                    "quantity": position.quantity,
                    "sellable": position.sellable_quantity,
                    "avg_cost": str(position.average_cost),
                    "bought_on": position.bought_on.isoformat(),
                }
                for position in positions
            ]
        except StorageError:
            positions_data = []
            position_cost = Decimal("0")

        active_theses = [
            {
                "key": thesis.key,
                "title": thesis.title,
                "status": thesis.status,
                "bet_pct": str(thesis.bet_pct) if thesis.bet_pct is not None else None,
            }
            for thesis in self.store.list_theses()
            if thesis.status in {"active", "watch"}
        ]
        active_pools = [
            {
                "key": pool.key,
                "name": pool.name,
                "status": pool.monitoring_status,
                "thesis_key": pool.thesis_key,
            }
            for pool in self.store.list_watch_pools()
        ]
        today_plans = [
            {
                "key": plan.key,
                "action": plan.action,
                "target_code": plan.target_code,
                "target_name": plan.target_name,
                "quantity": plan.quantity,
                "priority": plan.priority,
            }
            for plan in self.store.list_trade_plans(now.date(), ("active",))
        ]

        recent_trades: list[dict[str, Any]] = []
        if self.paper_store is not None:
            try:
                for fill in self.paper_store.list_fills(account_name)[-10:]:
                    recent_trades.append(
                        {
                            "code": fill.code,
                            "side": fill.side,
                            "quantity": fill.quantity,
                            "price": str(fill.price),
                            "notional": str(fill.notional),
                            "filled_at": (
                                fill.filled_at.isoformat() if fill.filled_at else None
                            ),
                        }
                    )
            except StorageError:
                pass

        return {
            "timestamp": now.isoformat(),
            "market_phase": _market_phase(now),
            "account": account_data,
            "positions": positions_data,
            "position_cost_basis": str(position_cost),
            "active_theses": active_theses,
            "active_pools": active_pools,
            "today_plans": today_plans,
            "recent_trades": recent_trades,
        }


def _market_phase(now: datetime) -> str:
    current = now.time()
    if current < time(9, 30):
        return "pre_market"
    if current < time(11, 30):
        return "intraday_morning"
    if current < time(13, 0):
        return "midday_break"
    if current < time(15, 0):
        return "intraday_afternoon"
    return "post_close"
