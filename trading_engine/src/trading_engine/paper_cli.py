from __future__ import annotations

import json
from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal

import typer

from trading_engine.config import TraderSettings
from trading_engine.context_store import ContextStore
from trading_engine.errors import PaperTradingError, TradingEngineError
from trading_engine.paper import PaperBroker
from trading_engine.paper_models import (
    PaperDecisionEvent,
    PaperExecutionResult,
    PaperFill,
    PaperOrder,
)
from trading_engine.paper_reports import PaperReportGenerator
from trading_engine.paper_store import PaperStore
from trading_engine.storage import ReplayStore


paper_app = typer.Typer(help="Execute and audit transaction-safe paper trades.")


@paper_app.command("execute")
def paper_execute(
    judgment: str = typer.Option(
        "latest", "--judgment", help="Judgment ID or latest."
    ),
    account_name: str = typer.Option(
        "paper", "--account", help="Dedicated paper account name."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Execute one persisted full-context judgment through the Paper Broker."""
    try:
        store, context_store, paper_store, _ = _paper_dependencies()
        result = PaperBroker(store, context_store, paper_store).execute_judgment(
            account_name,
            None if judgment == "latest" else judgment,
        )
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_execution(result, json_output)


@paper_app.command("settle")
def paper_settle(
    settlement_date: str = typer.Option(
        ..., "--date", help="Settlement date in YYYY-MM-DD format."
    ),
    account_name: str = typer.Option(
        "paper", "--account", help="Dedicated paper account name."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Release prior-day holdings into the T+1 sellable balance."""
    try:
        _, _, paper_store, _ = _paper_dependencies()
        parsed_date = _parse_date(settlement_date)
        settled = paper_store.settle_positions(account_name, parsed_date)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    payload = {
        "account": account_name,
        "date": parsed_date.isoformat(),
        "positions_settled": settled,
    }
    if json_output:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        typer.echo(
            f"Paper T+1结算 account={account_name} date={parsed_date.isoformat()} "
            f"positions={settled}"
        )


@paper_app.command("orders")
def paper_orders(
    account_name: str = typer.Option(
        "paper", "--account", help="Dedicated paper account name."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """List persisted simulated orders, including rejected orders."""
    try:
        _, _, paper_store, _ = _paper_dependencies()
        orders = paper_store.list_orders(account_name)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_orders(orders, json_output)


@paper_app.command("fills")
def paper_fills(
    account_name: str = typer.Option(
        "paper", "--account", help="Dedicated paper account name."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """List persisted simulated fills."""
    try:
        _, _, paper_store, _ = _paper_dependencies()
        fills = paper_store.list_fills(account_name)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_fills(fills, json_output)


@paper_app.command("events")
def paper_events(
    account_name: str = typer.Option(
        "paper", "--account", help="Dedicated paper account name."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """List every consumed proposal, including non-trading decisions."""
    try:
        _, _, paper_store, _ = _paper_dependencies()
        events = paper_store.list_events(account_name)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_events(events, json_output)


@paper_app.command("audit")
def paper_audit(
    order_id: str | None = typer.Option(
        None, "--order", help="Optional order ID; defaults to account audit."
    ),
    account_name: str = typer.Option(
        "paper", "--account", help="Dedicated paper account name."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Independently reconcile one order or the complete paper account."""
    try:
        _, _, paper_store, _ = _paper_dependencies()
        audit = (
            paper_store.audit_order(order_id)
            if order_id is not None
            else paper_store.audit_account(account_name)
        )
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(audit.model_dump_json(indent=2))
    else:
        typer.echo(
            f"Paper审计 valid={str(audit.valid).lower()} "
            f"issues={len(audit.issues)}"
        )
        for issue in audit.issues:
            typer.echo(f"- {issue}")
    if not audit.valid:
        raise typer.Exit(code=1)


@paper_app.command("report")
def paper_report(
    report_date: str | None = typer.Option(
        None, "--date", help="Report date in YYYY-MM-DD; defaults to today."
    ),
    account_name: str = typer.Option(
        "paper", "--account", help="Dedicated paper account name."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Generate state, trade ledger, and daily shadow Markdown from SQLite."""
    try:
        store, _, paper_store, settings = _paper_dependencies()
        trading_date = (
            _parse_date(report_date)
            if report_date is not None
            else datetime.now().astimezone().date()
        )
        paths = PaperReportGenerator(
            store,
            paper_store,
            settings.data_dir / "reports",
        ).generate(account_name, trading_date)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(paths.model_dump_json(indent=2))
    else:
        typer.echo("Paper报告已生成")
        typer.echo(f"- state: {paths.state}")
        typer.echo(f"- trades: {paths.trades}")
        typer.echo(f"- daily: {paths.daily}")


@paper_app.command("history")
def paper_history(
    account_name: str = typer.Option(
        "paper", "--account", help="Dedicated paper account name."
    ),
    report_date: str | None = typer.Option(
        None, "--date", help="Filter to a single date in YYYY-MM-DD format."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Aggregate paper fills, events, and orders into a daily summary."""
    try:
        _, _, paper_store, _ = _paper_dependencies()
        fills = paper_store.list_fills(account_name)
        events = paper_store.list_events(account_name)
        orders = paper_store.list_orders(account_name)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    filter_date = _parse_date(report_date) if report_date is not None else None
    by_date: OrderedDict[str, dict] = OrderedDict()

    def _ensure(day: date) -> dict:
        key = day.isoformat()
        if key not in by_date:
            by_date[key] = {
                "date": key,
                "fills": 0,
                "orders": 0,
                "events": 0,
                "buy_amount": Decimal("0"),
                "sell_amount": Decimal("0"),
                "net_cash": Decimal("0"),
            }
        return by_date[key]

    for fill in fills:
        if filter_date is not None and fill.filled_at.date() != filter_date:
            continue
        entry = _ensure(fill.filled_at.date())
        entry["fills"] += 1
        if fill.side == "BUY":
            entry["buy_amount"] += fill.notional
            entry["net_cash"] -= fill.notional
        else:
            entry["sell_amount"] += fill.notional
            entry["net_cash"] += fill.notional

    for order in orders:
        if filter_date is not None and order.trade_date != filter_date:
            continue
        entry = _ensure(order.trade_date)
        entry["orders"] += 1

    for event in events:
        if filter_date is not None and event.trade_date != filter_date:
            continue
        entry = _ensure(event.trade_date)
        entry["events"] += 1

    summary = list(by_date.values())
    if json_output:
        for entry in summary:
            entry["buy_amount"] = str(entry["buy_amount"])
            entry["sell_amount"] = str(entry["sell_amount"])
            entry["net_cash"] = str(entry["net_cash"])
        typer.echo(json.dumps(summary, indent=2, ensure_ascii=False))
        return

    if not summary:
        typer.echo("无 Paper 交易历史")
        return

    typer.echo("Paper交易历史")
    typer.echo(
        f"{'日期':<12} {'成交':>6} {'订单':>6} {'事件':>6} "
        f"{'买入金额':>14} {'卖出金额':>14} {'净现金流':>14}"
    )
    for entry in summary:
        typer.echo(
            f"{entry['date']:<12} {entry['fills']:>6} {entry['orders']:>6} "
            f"{entry['events']:>6} "
            f"{entry['buy_amount']:>14,.2f} "
            f"{entry['sell_amount']:>14,.2f} "
            f"{entry['net_cash']:>14,.2f}"
        )


def _paper_dependencies(
    ) -> tuple[ReplayStore, ContextStore, PaperStore, TraderSettings]:
    settings = TraderSettings.load()
    database = settings.data_dir / "trader.db"
    store = ReplayStore(database)
    context_store = ContextStore(database)
    paper_store = PaperStore(database)
    return store, context_store, paper_store, settings


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise PaperTradingError("date must use YYYY-MM-DD format") from exc


def _print_execution(result: PaperExecutionResult, json_output: bool) -> None:
    if json_output:
        typer.echo(result.model_dump_json(indent=2))
        return
    typer.echo(
        f"Paper执行 id={result.id} judgment={result.judgment_id} "
        f"account={result.account_name}"
    )
    typer.echo(
        f"事件={len(result.events)} 订单={len(result.orders)} "
        f"成交={len(result.fills)}"
    )
    for event in result.events:
        typer.echo(
            f"- {event.code} {event.action} {event.status}: {event.reason}"
        )


def _print_orders(orders: tuple[PaperOrder, ...], json_output: bool) -> None:
    if json_output:
        typer.echo(
            json.dumps(
                [order.model_dump(mode="json") for order in orders],
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    typer.echo("Paper订单")
    typer.echo(f"{'代码':<8} {'方向':<6} {'数量':>8} {'价格':>10} {'状态':<10}")
    for order in orders:
        typer.echo(
            f"{order.code:<8} {order.side:<6} {order.quantity:>8} "
            f"{order.price:>10.2f} {order.status:<10}"
        )


def _print_fills(fills: tuple[PaperFill, ...], json_output: bool) -> None:
    if json_output:
        typer.echo(
            json.dumps(
                [fill.model_dump(mode="json") for fill in fills],
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    typer.echo("Paper成交")
    typer.echo(f"{'代码':<8} {'方向':<6} {'数量':>8} {'价格':>10} {'金额':>12}")
    for fill in fills:
        typer.echo(
            f"{fill.code:<8} {fill.side:<6} {fill.quantity:>8} "
            f"{fill.price:>10.2f} {fill.notional:>12.2f}"
        )


def _print_events(
    events: tuple[PaperDecisionEvent, ...], json_output: bool
) -> None:
    if json_output:
        typer.echo(
            json.dumps(
                [event.model_dump(mode="json") for event in events],
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    typer.echo("Paper决策事件")
    typer.echo(f"{'日期':<12} {'代码':<8} {'动作':<10} {'状态':<10} 理由")
    for event in events:
        typer.echo(
            f"{event.trade_date.isoformat():<12} {event.code:<8} "
            f"{event.action:<10} {event.status:<10} {event.reason}"
        )
