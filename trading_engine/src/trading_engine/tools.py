"""Tool functions for the trader tool gateway.

MarketDataTools wraps astock CLI for individual fetch-* operations.
BriefGenerator produces the minimal state summary for brain startup.
"""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from math import isclose
from typing import Any

from pydantic import ValidationError

from trading_engine.astock import AstockClient
from trading_engine.errors import LiveDataError, StorageError
from trading_engine.live import MARKET_INDICES
from trading_engine.models import LiveQuote
from trading_engine.paper_store import PaperStore
from trading_engine.replay import SHANGHAI_TZ
from trading_engine.storage import ReplayStore


class MarketDataTools:
    """Individual market data fetch operations wrapping astock CLI.

    In live mode (replay_date=None): calls astock live commands for real-time data.
    In replay mode (replay_date set): calls astock query commands for historical data.
    The brain calls the same methods regardless of mode.
    """

    def __init__(
        self,
        client: AstockClient,
        replay_date: str | None = None,
        replay_time: str | None = None,
    ) -> None:
        self.client = client
        self.replay_date = replay_date  # YYYYMMDD, None = live
        self.replay_time = replay_time  # HH:MM, only when replay_date is set

    @property
    def _is_replay(self) -> bool:
        return self.replay_date is not None

    # ------------------------------------------------------------------
    # fetch-index
    # ------------------------------------------------------------------

    def fetch_index(self) -> list[dict[str, Any]]:
        """Fetch index quotes for all tracked indices."""
        if self._is_replay:
            return self._fetch_index_replay()
        return self._fetch_index_live()

    def _fetch_index_live(self) -> list[dict[str, Any]]:
        rows = self.client.run_json("live", "index", *MARKET_INDICES)
        if not isinstance(rows, list):
            raise LiveDataError("astock live index returned a non-list payload")
        returned = {str(row.get("code", "")) for row in rows}
        if returned != set(MARKET_INDICES):
            missing = sorted(set(MARKET_INDICES) - returned)
            raise LiveDataError(f"astock live index missing: {', '.join(missing)}")
        result = []
        for row in rows:
            code = str(row["code"])
            result.append(
                {
                    "code": code,
                    "name": MARKET_INDICES[code],
                    "price": row["price"],
                    "pre_close": row["pre_close"],
                    "change_pct": row["change_pct"],
                    "amount": row["amount"],
                }
            )
        return result

    def _fetch_index_replay(self) -> list[dict[str, Any]]:
        """Fetch index quotes via ``astock replay index``.

        astock reconstructs from minute bars internally; trader just passes
        date and optional time.  Mirrors ``astock live index``.
        """
        args = ["replay", "index", self.replay_date]
        if self.replay_time:
            args.append(self.replay_time)
        rows = self.client.run_json(*args)
        if not isinstance(rows, list):
            raise LiveDataError("astock replay index returned a non-list payload")
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # fetch-block-rank
    # ------------------------------------------------------------------

    def fetch_block_rank(self, limit: int = 50) -> list[dict[str, Any]]:
        """Fetch block ranking by change_pct."""
        if self._is_replay:
            return self._fetch_block_rank_replay(limit)
        rows = self.client.run_json(
            "live", "block", "rank", "--limit", str(limit)
        )
        if not isinstance(rows, list):
            raise LiveDataError("astock live block rank returned a non-list payload")
        return [dict(row) for row in rows]

    def _fetch_block_rank_replay(self, limit: int) -> list[dict[str, Any]]:
        """Fetch block ranking via ``astock replay block rank``.

        With replay_time, returns minute-level ranking (block's own change_pct
        from minute bars).  Without, returns end-of-day ranking.
        """
        args = ["replay", "block", "rank", self.replay_date]
        if self.replay_time:
            args.append(self.replay_time)
        args.extend(["--limit", str(limit)])
        rows = self.client.run_json(*args)
        if not isinstance(rows, list):
            raise LiveDataError("astock replay block rank returned a non-list payload")
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # fetch-stock-quote
    # ------------------------------------------------------------------

    def fetch_stock_quote(self, codes: tuple[str, ...]) -> list[dict[str, Any]]:
        """Fetch stock quotes with validation."""
        if not codes:
            raise LiveDataError("at least one stock code is required")
        if self._is_replay:
            return self._fetch_stock_quote_replay(codes)
        return self._fetch_stock_quote_live(codes)

    def _fetch_stock_quote_live(self, codes: tuple[str, ...]) -> list[dict[str, Any]]:
        rows = self.client.run_json("live", "quote", *codes)
        if not isinstance(rows, list):
            raise LiveDataError("astock live quote returned a non-list payload")
        returned_codes = [str(row.get("code", "")) for row in rows]
        if len(returned_codes) != len(set(returned_codes)):
            raise LiveDataError("astock live quote returned duplicate stock codes")
        if set(returned_codes) != set(codes):
            missing = sorted(set(codes) - set(returned_codes))
            unexpected = sorted(set(returned_codes) - set(codes))
            raise LiveDataError(
                f"code mismatch: missing={','.join(missing) or 'none'} "
                f"unexpected={','.join(unexpected) or 'none'}"
            )
        rows_by_code = {str(row["code"]): row for row in rows}
        result = []
        for code in codes:
            try:
                quote = LiveQuote.model_validate(rows_by_code[code])
            except ValidationError as exc:
                raise LiveDataError(f"{code}: invalid quote: {exc}") from exc
            calculated_pct = (
                (quote.price - quote.pre_close) / quote.pre_close * 100
                if quote.pre_close
                else quote.change_pct
            )
            if quote.pre_close and not isclose(
                calculated_pct, quote.change_pct, abs_tol=0.02
            ):
                raise LiveDataError(
                    f"{code}: change_pct does not match price and pre_close"
                )
            result.append(quote.model_dump(mode="json"))
        return result

    def _fetch_stock_quote_replay(self, codes: tuple[str, ...]) -> list[dict[str, Any]]:
        """Fetch stock quotes via ``astock replay quote``.

        astock reconstructs from minute bars internally and auto-syncs
        if the stock's minute data is missing (within TDX window).
        """
        args = [
            "replay", "quote", ",".join(codes),
            self.replay_date,
        ]
        if self.replay_time:
            args.append(self.replay_time)
        rows = self.client.run_json(*args)
        if not isinstance(rows, list):
            raise LiveDataError("astock replay quote returned a non-list payload")
        result = []
        for row in rows:
            result.append(dict(row))
        return result

    # ------------------------------------------------------------------
    # fetch-block-members
    # ------------------------------------------------------------------

    def fetch_block_members(self, block_code: str) -> list[dict[str, Any]]:
        """Fetch member stocks of a block with their current/replay prices.

        Live mode: calls ``astock live block members`` for real-time quotes.
        Replay without time: calls ``astock query block members <date>`` for daily close.
        Replay with time: calls ``astock replay block members <date> <time>`` for minute-level.
        """
        if self._is_replay:
            return self._fetch_block_members_replay(block_code)
        rows = self.client.run_json("live", "block", "members", block_code)
        if not isinstance(rows, list):
            raise LiveDataError("astock live block members returned a non-list payload")
        return [dict(row) for row in rows]

    def _fetch_block_members_replay(self, block_code: str) -> list[dict[str, Any]]:
        """Fetch block members in replay mode.

        With replay_time, uses ``astock replay block members`` for minute-level prices.
        Without, uses ``astock query block members <date>`` for daily close.
        """
        if self.replay_time:
            args = ["replay", "block", "members", block_code, self.replay_date, self.replay_time]
        else:
            args = ["query", "block", "members", block_code, self.replay_date]
        rows = self.client.run_json(*args)
        if not isinstance(rows, list):
            raise LiveDataError("astock block members returned a non-list payload")
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # fetch-limit-list
    # ------------------------------------------------------------------

    def fetch_limit_list(
        self,
        date: str | None = None,
        side: str = "up",
        exclude_st: bool = False,
    ) -> list[dict[str, Any]]:
        """Fetch limit-up/down list with consecutive_days + concepts.

        In replay mode with replay_time, uses ``astock replay limit list``
        which annotates each stock with sealed/broken/pending status.
        """
        effective_date = date or self.replay_date
        if self._is_replay and self.replay_time and side == "up":
            args = ["replay", "limit", "list", self.replay_date, self.replay_time]
            if exclude_st:
                args.append("--exclude-st")
            rows = self.client.run_json(*args)
            if not isinstance(rows, list):
                raise LiveDataError("astock replay limit list returned a non-list payload")
            return [dict(row) for row in rows]
        # No replay_time or live mode: use query limit (daily terminal value)
        args = ["query", "limit"]
        if effective_date:
            args.append(effective_date)
        args.extend(["--side", side])
        if exclude_st:
            args.append("--exclude-st")
        rows = self.client.run_json(*args)
        if not isinstance(rows, list):
            raise LiveDataError("astock query limit returned a non-list payload")
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # fetch-limit-ladder
    # ------------------------------------------------------------------

    def fetch_limit_ladder(self) -> list[dict[str, Any]]:
        """Fetch limit-up ladder: stocks still at limit-up, by consecutive_days.

        In replay mode with replay_time, uses ``astock replay limit ladder``
        which only counts stocks currently sealed (封板中).
        """
        if self._is_replay and self.replay_time:
            args = ["replay", "limit", "ladder", self.replay_date, self.replay_time]
            rows = self.client.run_json(*args)
            if not isinstance(rows, list):
                raise LiveDataError("astock replay limit ladder returned a non-list payload")
            return [dict(row) for row in rows]
        args = ["query", "limit", "ladder"]
        if self.replay_date:
            args.append(self.replay_date)
        rows = self.client.run_json(*args)
        if not isinstance(rows, list):
            raise LiveDataError("astock query limit ladder returned a non-list payload")
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # fetch-market-scan
    # ------------------------------------------------------------------

    def fetch_market_scan(self) -> dict[str, Any]:
        """Fetch full market scan."""
        if self._is_replay:
            return self._fetch_market_scan_replay()
        return self._fetch_market_scan_live()

    def _fetch_market_scan_live(self) -> dict[str, Any]:
        market = self.client.run_json("live", "market")
        if not isinstance(market, dict):
            raise LiveDataError("astock live market returned a non-object payload")
        candidates = market.get("candidates")
        top_amount = market.get("top_amount")
        if not isinstance(candidates, list) or not isinstance(top_amount, list):
            raise LiveDataError("astock live market omitted candidates or top_amount")
        limit_up_codes = sorted(
            {
                str(row.get("code"))
                for row in candidates
                if isinstance(row, dict)
                and row.get("code")
                and row.get("limit_up") is True
            }
        )
        coverage_mode = market.get("coverage_mode")
        if coverage_mode == "all_main_board_snapshot":
            coverage_mode = "full_market"
        elif coverage_mode not in {"candidate_universe", "registered_universe"}:
            coverage_mode = "candidate_universe"
        return {
            "coverage_mode": coverage_mode,
            "universe_count": market.get("universe"),
            "scanned_count": market.get("scanned"),
            "missing_quote_count": market.get("missing_quotes"),
            "candidate_codes": sorted(
                {
                    str(row.get("code"))
                    for row in candidates
                    if isinstance(row, dict) and row.get("code")
                }
            ),
            "limit_up_codes": limit_up_codes,
            "candidates": candidates,
            "top_amount": top_amount,
        }

    def _fetch_market_scan_replay(self) -> dict[str, Any]:
        """Fetch market scan via ``astock replay market``.

        With replay_time, returns minute-level snapshot (only covers stocks
        with synced minute data).  Without, returns daily terminal snapshot.
        """
        args = ["replay", "market", self.replay_date]
        if self.replay_time:
            args.append(self.replay_time)
        market = self.client.run_json(*args)
        if not isinstance(market, dict):
            raise LiveDataError("astock replay market returned a non-object payload")

        top_amount_rows = self.client.run_json(
            "query", "stock", "--sort-by", "amount",
            "--date", self.replay_date, "--limit", "10",
        )
        top_pct_rows = self.client.run_json(
            "query", "stock", "--sort-by", "pct",
            "--date", self.replay_date, "--limit", "20",
        )
        limit_rows = self.client.run_json(
            "query", "limit", self.replay_date,
        )

        top_amount = [dict(row) for row in top_amount_rows] if isinstance(top_amount_rows, list) else []
        candidates = [dict(row) for row in top_pct_rows] if isinstance(top_pct_rows, list) else []
        limit_up = [dict(row) for row in limit_rows] if isinstance(limit_rows, list) else []
        limit_up_codes = sorted({str(row.get("code", "")) for row in limit_up if row.get("code")})

        return {
            "coverage_mode": "replay_minute" if self.replay_time else "replay_daily",
            "universe_count": market.get("total_stocks", 0),
            "scanned_count": market.get("total_stocks", 0),
            "missing_quote_count": 0,
            "up_count": market.get("up_count", 0),
            "down_count": market.get("down_count", 0),
            "flat_count": market.get("flat_count", 0),
            "limit_up_count": market.get("limit_up_count", 0),
            "total_amount": market.get("total_amount", 0),
            "index_price": market.get("index_price", 0),
            "index_change_pct": market.get("index_change_pct", 0),
            "candidate_codes": sorted({str(r.get("code", "")) for r in candidates if r.get("code")}),
            "limit_up_codes": limit_up_codes,
            "candidates": candidates,
            "top_amount": top_amount,
        }


class BriefGenerator:
    """Generates minimal state summary for brain startup.

    Does NOT pre-fetch market data. Brain calls fetch-* tools for quotes.
    """

    def __init__(
        self,
        store: ReplayStore,
        paper_store: PaperStore | None = None,
    ) -> None:
        self.store = store
        self.paper_store = paper_store

    def generate(self, account_name: str = "paper") -> dict[str, Any]:
        """Generate brief: timestamp, phase, account, positions, theses, pools, plans, trades."""
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
                p.quantity * p.average_cost for p in positions
            )
            positions_data = [
                {
                    "code": p.code,
                    "name": p.name,
                    "quantity": p.quantity,
                    "sellable": p.sellable_quantity,
                    "avg_cost": str(p.average_cost),
                    "bought_on": p.bought_on.isoformat(),
                }
                for p in positions
            ]
        except StorageError:
            positions_data = []
            position_cost = Decimal("0")

        theses = self.store.list_theses()
        active_theses = [
            {
                "key": t.key,
                "title": t.title,
                "status": t.status,
            }
            for t in theses
            if t.status in {"active", "watch"}
        ]

        pools = self.store.list_watch_pools()
        pool_data = [
            {
                "key": p.key,
                "name": p.name,
                "status": p.monitoring_status,
                "thesis_key": p.thesis_key,
            }
            for p in pools
        ]

        today = now.date()
        plans = self.store.list_trade_plans(today, ("active",))
        plan_data = [
            {
                "key": p.key,
                "action": p.action,
                "target_code": p.target_code,
                "target_name": p.target_name,
                "quantity": p.quantity,
                "priority": p.priority,
            }
            for p in plans
        ]

        recent_trades: list[dict[str, Any]] = []
        if self.paper_store is not None:
            try:
                fills = self.paper_store.list_fills(account_name)
                for fill in fills[-10:]:
                    recent_trades.append(
                        {
                            "code": fill.code,
                            "side": fill.side,
                            "quantity": fill.quantity,
                            "price": str(fill.price),
                            "notional": str(fill.notional),
                            "filled_at": fill.filled_at.isoformat()
                            if fill.filled_at
                            else None,
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
            "active_pools": pool_data,
            "today_plans": plan_data,
            "recent_trades": recent_trades,
        }


def _market_phase(now: datetime) -> str:
    """Determine market phase from current time (Shanghai timezone)."""
    t = now.time()
    if t < time(9, 30):
        return "pre_market"
    if t < time(11, 30):
        return "intraday_morning"
    if t < time(13, 0):
        return "midday_break"
    if t < time(15, 0):
        return "intraday_afternoon"
    return "post_close"
