from __future__ import annotations

import json
from datetime import date, datetime

import typer

from trading_engine import __version__
from trading_engine.astock import AstockClient
from trading_engine.config import TraderSettings
from trading_engine.errors import ReplayError, TradingEngineError
from trading_engine.live import LiveMarketData
from trading_engine.models import LiveQuote, LiveSnapshotRecord
from trading_engine.replay import (
    ReplayEngine,
    ReplayMarketData,
    parse_clock_time,
)
from trading_engine.storage import ReplayStore


app = typer.Typer(
    name="trader",
    help="Replay-first AI trading engine.",
    no_args_is_help=True,
    invoke_without_command=True,
)
config_app = typer.Typer(help="Inspect trading engine configuration.")
astock_app = typer.Typer(help="Inspect the astock market-data dependency.")
replay_app = typer.Typer(
    help="Run deterministic historical market replay.",
    invoke_without_command=True,
)
watch_app = typer.Typer(
    help="Capture validated real-time market snapshots in shadow mode.",
    invoke_without_command=True,
)
app.add_typer(config_app, name="config")
app.add_typer(astock_app, name="astock")
app.add_typer(replay_app, name="replay")
app.add_typer(watch_app, name="watch")


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show the trader version and exit.",
        is_eager=True,
    ),
) -> None:
    if version:
        typer.echo(f"trader {__version__}")
        raise typer.Exit()


@config_app.command("show")
def config_show() -> None:
    """Print resolved local paths without creating runtime data."""
    try:
        settings = TraderSettings.load()
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        json.dumps(
            {
                "repo_root": str(settings.repo_root),
                "astock_binary": str(settings.astock_binary),
                "data_dir": str(settings.data_dir),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


@astock_app.command("check")
def astock_check() -> None:
    """Verify that the configured astock binary can execute."""
    try:
        settings = TraderSettings.load()
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    health = AstockClient(settings.astock_binary).check()
    typer.echo(health.model_dump_json(indent=2))
    if not health.available:
        raise typer.Exit(code=1)


@replay_app.callback()
def replay_start(
    context: typer.Context,
    replay_date: str | None = typer.Option(
        None,
        "--date",
        help="Trading date in YYYYMMDD format.",
    ),
    until: str = typer.Option(
        "15:00",
        "--until",
        help="Last bar-close time to process in HH:MM format.",
    ),
    codes: list[str] | None = typer.Option(
        None,
        "--code",
        help="Stock code to load; repeat for multiple stocks.",
    ),
) -> None:
    if context.invoked_subcommand is not None:
        return
    if replay_date is None:
        typer.echo("--date is required when starting a replay", err=True)
        raise typer.Exit(code=2)
    try:
        engine = _replay_engine()
        run = engine.start(
            _parse_date(replay_date),
            _normalize_codes(codes or []),
            parse_clock_time(until),
        )
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(run.model_dump_json(indent=2))


@replay_app.command("resume")
def replay_resume(
    until: str = typer.Option(
        "15:00",
        "--until",
        help="Last bar-close time to process in HH:MM format.",
    ),
) -> None:
    """Resume the latest interrupted or paused replay."""
    try:
        run = _replay_engine().resume(parse_clock_time(until))
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(run.model_dump_json(indent=2))


@app.command("status")
def replay_status() -> None:
    """Show the latest persisted replay run."""
    try:
        run = _replay_engine().status()
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(run.model_dump_json(indent=2))


@watch_app.callback()
def watch_snapshot(
    context: typer.Context,
    codes: list[str] | None = typer.Option(
        None,
        "--code",
        help="Stock code to observe; repeat for multiple stocks.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print the persisted snapshot as JSON.",
    ),
) -> None:
    if context.invoked_subcommand is not None:
        return
    try:
        normalized_codes = _normalize_codes(codes or [])
        settings = TraderSettings.load()
        snapshot = LiveMarketData(
            AstockClient(settings.astock_binary), normalized_codes
        ).snapshot()
        record = ReplayStore(
            settings.data_dir / "trader.db"
        ).record_live_snapshot(snapshot)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_live_snapshot(record, json_output)


@watch_app.command("latest")
def watch_latest(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print the persisted snapshot as JSON.",
    ),
) -> None:
    """Show the latest persisted real-time shadow snapshot."""
    settings = TraderSettings.load()
    record = ReplayStore(
        settings.data_dir / "trader.db"
    ).latest_live_snapshot()
    if record is None:
        typer.echo("no live shadow snapshot exists", err=True)
        raise typer.Exit(code=1)
    _print_live_snapshot(record, json_output)


def _replay_engine() -> ReplayEngine:
    settings = TraderSettings.load()
    client = AstockClient(settings.astock_binary)
    store = ReplayStore(settings.data_dir / "trader.db")
    return ReplayEngine(
        store,
        lambda trading_date, codes: ReplayMarketData(
            client, trading_date, codes
        ),
    )


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError as exc:
        raise ReplayError("date must use YYYYMMDD format") from exc


def _normalize_codes(values: list[str]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(value.strip() for value in values))
    invalid = [code for code in normalized if len(code) != 6 or not code.isdigit()]
    if invalid:
        raise ReplayError(f"invalid stock code: {', '.join(invalid)}")
    return normalized


def _print_live_snapshot(
    record: LiveSnapshotRecord, json_output: bool
) -> None:
    if json_output:
        typer.echo(record.model_dump_json(indent=2))
        return

    snapshot = record.snapshot
    typer.echo(
        f"实时影子快照 {snapshot.as_of.strftime('%Y-%m-%d %H:%M:%S')} "
        f"id={record.id}"
    )
    typer.echo("模式：只读影子，不执行交易")
    typer.echo("")
    typer.echo(
        f"{'代码':<8} {'现价':>10} {'昨收':>10} "
        f"{'涨跌%':>9} {'成交额(亿)':>12}"
    )
    for raw_quote in snapshot.payload["quotes"]:
        quote = LiveQuote.model_validate(raw_quote)
        typer.echo(
            f"{quote.code:<8} {quote.price:>10.2f} {quote.pre_close:>10.2f} "
            f"{quote.change_pct:>+8.2f}% {quote.amount / 1e8:>12.2f}"
        )
