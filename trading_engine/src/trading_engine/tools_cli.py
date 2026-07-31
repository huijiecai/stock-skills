"""CLI wiring for trader tools — brain-facing unified tool interface.

All commands output JSON by default (for brain consumption).
"""

from __future__ import annotations

import json
from typing import Any

import typer

from trading_engine.astock import AstockClient
from trading_engine.config import TraderSettings
from trading_engine.context_store import ContextStore
from trading_engine.errors import TradingEngineError
from trading_engine.paper_store import PaperStore
from trading_engine.storage import ReplayStore
from trading_engine.tools import BriefGenerator, MarketDataTools


tools_app = typer.Typer(
    name="tools",
    help="Unified tool interface for brain: fetch market data, get state, execute trades.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _print_json(data: Any) -> None:
    typer.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _settings() -> TraderSettings:
    return TraderSettings.load()


def _store() -> ReplayStore:
    return ReplayStore(_settings().data_dir / "trader.db")


def _paper_store() -> PaperStore:
    return PaperStore(_settings().data_dir / "trader.db")


def _context_store() -> ContextStore:
    return ContextStore(_settings().data_dir / "trader.db")


def _market_tools(
    replay_date: str | None = None,
    replay_time: str | None = None,
) -> MarketDataTools:
    return MarketDataTools(
        AstockClient(_settings().astock_binary, timeout_seconds=60),
        replay_date=replay_date,
        replay_time=replay_time,
    )


def _brief_generator() -> BriefGenerator:
    settings = _settings()
    database = settings.data_dir / "trader.db"
    return BriefGenerator(
        ReplayStore(database),
        PaperStore(database),
    )


# ---------------------------------------------------------------------------
# fetch-* tools: market data (wrapping astock)
# ---------------------------------------------------------------------------

@tools_app.command("fetch-index")
def fetch_index(
    replay_date: str | None = typer.Option(
        None, "--replay-date", help="Replay date YYYYMMDD. Omit for live mode."
    ),
    replay_time: str | None = typer.Option(
        None, "--replay-time", help="Replay time HH:MM. Only with --replay-date."
    ),
) -> None:
    """Fetch index quotes. Live mode by default, replay mode with --replay-date."""
    try:
        result = _market_tools(replay_date, replay_time).fetch_index()
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_json(result)


@tools_app.command("fetch-block-rank")
def fetch_block_rank(
    limit: int = typer.Option(50, "--limit", help="Number of blocks to return."),
    replay_date: str | None = typer.Option(
        None, "--replay-date", help="Replay date YYYYMMDD. Omit for live mode."
    ),
    replay_time: str | None = typer.Option(
        None, "--replay-time", help="Replay time HH:MM. Only with --replay-date."
    ),
) -> None:
    """Fetch block ranking. Live mode by default, replay with --replay-date."""
    try:
        result = _market_tools(replay_date, replay_time).fetch_block_rank(limit)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_json(result)


@tools_app.command("fetch-stock-quote")
def fetch_stock_quote(
    codes: list[str] = typer.Argument(..., help="Stock codes (6-digit)."),
    replay_date: str | None = typer.Option(
        None, "--replay-date", help="Replay date YYYYMMDD. Omit for live mode."
    ),
    replay_time: str | None = typer.Option(
        None, "--replay-time", help="Replay time HH:MM. Only with --replay-date."
    ),
) -> None:
    """Fetch stock quotes. Live mode by default, replay with --replay-date."""
    try:
        normalized = tuple(dict.fromkeys(c.strip() for c in codes))
        result = _market_tools(replay_date, replay_time).fetch_stock_quote(normalized)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_json(result)


@tools_app.command("fetch-block-members")
def fetch_block_members(
    block_code: str = typer.Argument(
        ..., help="Block code (6-digit, e.g. 880904). Use fetch-block-rank to find codes."
    ),
    replay_date: str | None = typer.Option(
        None, "--replay-date", help="Replay date YYYYMMDD. Omit for live mode."
    ),
    replay_time: str | None = typer.Option(
        None, "--replay-time", help="Replay time HH:MM. Only with --replay-date."
    ),
) -> None:
    """Fetch block members. Live mode by default, replay with --replay-date."""
    try:
        result = _market_tools(replay_date, replay_time).fetch_block_members(block_code)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_json(result)


@tools_app.command("fetch-limit-list")
def fetch_limit_list(
    date: str | None = typer.Option(
        None, "--date", help="Trading date YYYYMMDD. Defaults to latest or replay-date."
    ),
    side: str = typer.Option(
        "up", "--side", help="up=涨停, down=跌停."
    ),
    exclude_st: bool = typer.Option(
        False, "--exclude-st", help="Exclude ST stocks."
    ),
    replay_date: str | None = typer.Option(
        None, "--replay-date", help="Replay date YYYYMMDD. Omit for latest. Alias for --date."
    ),
    replay_time: str | None = typer.Option(
        None, "--replay-time", help="Replay time HH:MM. Only with --replay-date."
    ),
) -> None:
    """Fetch complete limit-up/down list with consecutive_days and concepts."""
    try:
        tools = _market_tools(replay_date, replay_time)
        result = tools.fetch_limit_list(date, side, exclude_st)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_json(result)


@tools_app.command("fetch-limit-ladder")
def fetch_limit_ladder(
    replay_date: str | None = typer.Option(
        None, "--replay-date", help="Replay date YYYYMMDD. Omit for latest."
    ),
    replay_time: str | None = typer.Option(
        None, "--replay-time", help="Replay time HH:MM. Only with --replay-date."
    ),
) -> None:
    """Fetch limit-up ladder. Latest by default, specific date with --replay-date."""
    try:
        result = _market_tools(replay_date, replay_time).fetch_limit_ladder()
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_json(result)


@tools_app.command("fetch-market-scan")
def fetch_market_scan(
    replay_date: str | None = typer.Option(
        None, "--replay-date", help="Replay date YYYYMMDD. Omit for live mode."
    ),
    replay_time: str | None = typer.Option(
        None, "--replay-time", help="Replay time HH:MM. Only with --replay-date."
    ),
) -> None:
    """Fetch full market scan. Live mode by default, replay with --replay-date."""
    try:
        result = _market_tools(replay_date, replay_time).fetch_market_scan()
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_json(result)


# ---------------------------------------------------------------------------
# get-* tools: state from SQLite
# ---------------------------------------------------------------------------

@tools_app.command("get-account")
def get_account(
    account_name: str = typer.Option("paper", "--account", help="Account name."),
) -> None:
    """Get account state from SQLite."""
    try:
        account = _store().get_account(account_name)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_json(account.model_dump(mode="json"))


@tools_app.command("get-positions")
def get_positions(
    account_name: str = typer.Option("paper", "--account", help="Account name."),
) -> None:
    """Get positions from SQLite."""
    try:
        positions = _store().list_positions(account_name)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_json([p.model_dump(mode="json") for p in positions])


@tools_app.command("get-theses")
def get_theses(
    active_only: bool = typer.Option(
        False, "--active-only", help="Only show active/watch theses."
    ),
) -> None:
    """Get theses from SQLite."""
    try:
        theses = _store().list_theses()
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if active_only:
        theses = tuple(t for t in theses if t.status in {"active", "watch"})
    _print_json([t.model_dump(mode="json") for t in theses])


@tools_app.command("get-pools")
def get_pools(
    status: str | None = typer.Option(
        None, "--status", help="Filter by monitoring status (active/dormant/archived)."
    ),
) -> None:
    """Get watch pools with members from SQLite."""
    try:
        store = _store()
        pools = store.list_watch_pools()
        if status is not None:
            pools = tuple(p for p in pools if p.monitoring_status == status)
        result = []
        for pool in pools:
            members = store.list_watch_pool_members(pool.key)
            result.append(
                {
                    **pool.model_dump(mode="json"),
                    "members": [m.model_dump(mode="json") for m in members],
                }
            )
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_json(result)


@tools_app.command("get-evidence")
def get_evidence(
    thesis_key: str | None = typer.Option(
        None, "--thesis", help="Filter by thesis key."
    ),
) -> None:
    """Get catalyst evidence from SQLite."""
    try:
        evidence = _context_store().list_evidence(
            (thesis_key,) if thesis_key else None
        )
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_json([e.model_dump(mode="json") for e in evidence])


@tools_app.command("get-risk")
def get_risk() -> None:
    """Get risk factors from SQLite."""
    try:
        factors = _store().list_risk_factors()
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_json([f.model_dump(mode="json") for f in factors])


@tools_app.command("get-plans")
def get_plans(
    trading_date: str | None = typer.Option(
        None, "--date", help="Filter by trading date (YYYY-MM-DD). Defaults to today."
    ),
    status: list[str] | None = typer.Option(
        None, "--status", help="Filter by plan status."
    ),
) -> None:
    """Get trade plans from SQLite."""
    try:
        from datetime import date
        parsed_date = date.fromisoformat(trading_date) if trading_date else None
        plans = _store().list_trade_plans(
            parsed_date,
            tuple(status) if status else None,
        )
    except (TradingEngineError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_json([p.model_dump(mode="json") for p in plans])


@tools_app.command("get-history")
def get_history(
    account_name: str = typer.Option("paper", "--account", help="Account name."),
) -> None:
    """Get recent order and fill history from SQLite."""
    try:
        store = _paper_store()
        orders = store.list_orders(account_name)
        fills = store.list_fills(account_name)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_json(
        {
            "orders": [o.model_dump(mode="json") for o in orders],
            "fills": [f.model_dump(mode="json") for f in fills],
        }
    )


@tools_app.command("audit")
def audit(
    account_name: str = typer.Option("paper", "--account", help="Account name."),
) -> None:
    """Audit account integrity from SQLite."""
    try:
        audit_result = _paper_store().audit_account(account_name)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_json(audit_result.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# brief: minimal entry point for brain
# ---------------------------------------------------------------------------

def brief_command(
    account_name: str = typer.Option("paper", "--account", help="Account name."),
) -> None:
    """Generate minimal state summary for brain startup.

    Does NOT pre-fetch market data. Call fetch-* tools for quotes.
    """
    try:
        result = _brief_generator().generate(account_name)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_json(result)
