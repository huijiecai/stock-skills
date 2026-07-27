from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import typer

from trading_engine import __version__
from trading_engine.analysis import ReadOnlyAnalyzer
from trading_engine.astock import AstockClient
from trading_engine.config import TraderSettings
from trading_engine.context_cli import context_app, evidence_app
from trading_engine.context_store import ContextStore
from trading_engine.errors import PortfolioError, ReplayError, TradingEngineError
from trading_engine.live import LiveMarketData
from trading_engine.models import (
    AccountState,
    JudgmentRecord,
    LiveQuote,
    LiveSnapshotRecord,
    PositionState,
    RiskFactorState,
    ThesisState,
    WatchPoolMember,
    WatchPoolState,
)
from trading_engine.paper_cli import paper_app
from trading_engine.replay import (
    ReplayEngine,
    ReplayMarketData,
    parse_clock_time,
)
from trading_engine.storage import ReplayStore


app = typer.Typer(
    name="trader",
    help="Real-time-first AI trading engine with deterministic replay.",
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
analyze_app = typer.Typer(
    help="Generate auditable read-only judgments from persisted snapshots."
)
account_app = typer.Typer(help="Manage the engine's independent SQLite account.")
position_app = typer.Typer(help="Manage positions in the independent account.")
thesis_app = typer.Typer(help="Manage independent investment theses.")
pool_app = typer.Typer(help="Manage independent fixed watch pools.")
risk_app = typer.Typer(help="Manage independent portfolio risk factors.")
app.add_typer(config_app, name="config")
app.add_typer(astock_app, name="astock")
app.add_typer(replay_app, name="replay")
app.add_typer(watch_app, name="watch")
app.add_typer(analyze_app, name="analyze")
app.add_typer(account_app, name="account")
app.add_typer(position_app, name="position")
app.add_typer(thesis_app, name="thesis")
app.add_typer(pool_app, name="pool")
app.add_typer(risk_app, name="risk")
app.add_typer(evidence_app, name="evidence")
app.add_typer(context_app, name="context")
app.add_typer(paper_app, name="paper")


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


@analyze_app.command("latest")
def analyze_latest(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print the persisted judgment as JSON.",
    ),
    attempts: int = typer.Option(
        2,
        "--attempts",
        min=1,
        max=5,
        help="Maximum provider attempts before recording a failure.",
    ),
) -> None:
    """Analyze the latest real-time snapshot without executing trades."""
    try:
        settings = TraderSettings.load()
        store = ReplayStore(settings.data_dir / "trader.db")
        snapshot = store.latest_live_snapshot()
        if snapshot is None:
            raise TradingEngineError(
                "no live shadow snapshot exists; run `trader watch --code ...` first"
            )
        record = ReadOnlyAnalyzer(store, max_attempts=attempts).analyze(snapshot)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_judgment(record, json_output)
    if record.status == "failed":
        raise typer.Exit(code=1)


@analyze_app.command("show")
def analyze_show(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print the latest persisted judgment as JSON.",
    ),
) -> None:
    """Show the latest persisted judgment without running the provider."""
    try:
        settings = TraderSettings.load()
        record = ReplayStore(
            settings.data_dir / "trader.db"
        ).latest_judgment()
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if record is None:
        typer.echo("no read-only judgment exists", err=True)
        raise typer.Exit(code=1)
    _print_judgment(record, json_output)
    if record.status == "failed":
        raise typer.Exit(code=1)


@analyze_app.command("context")
def analyze_context(
    account_name: str = typer.Option(
        "default", "--account", help="Account name."
    ),
    attempts: int = typer.Option(
        2,
        "--attempts",
        min=1,
        max=5,
        help="Maximum provider attempts before recording a failure.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Analyze the latest complete decision context without executing trades."""
    try:
        settings = TraderSettings.load()
        database = settings.data_dir / "trader.db"
        store = ReplayStore(database)
        context_record = ContextStore(database).latest_context(account_name)
        if context_record is None:
            raise TradingEngineError(
                "no decision context exists; run `trader context capture` first"
            )
        market_record = store.get_market_snapshot(
            context_record.context.market_snapshot_id
        )
        record = ReadOnlyAnalyzer(store, max_attempts=attempts).analyze(
            market_record, context_record
        )
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_judgment(record, json_output)
    if record.status == "failed":
        raise typer.Exit(code=1)


@account_app.command("init")
def account_init(
    cash: str = typer.Option(..., "--cash", help="Current cash in CNY."),
    initial_cash: str | None = typer.Option(
        None,
        "--initial-cash",
        help="Initial capital in CNY; defaults to current cash.",
    ),
    name: str = typer.Option("default", "--name", help="Account name."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Create a new independent account in the engine database."""
    try:
        account = _store().create_account(
            name,
            _parse_money(initial_cash if initial_cash is not None else cash),
            _parse_money(cash),
        )
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_account(account, json_output)


@account_app.command("show")
def account_show(
    name: str = typer.Option("default", "--name", help="Account name."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Show account state stored in the engine database."""
    try:
        account = _store().get_account(name)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_account(account, json_output)


@account_app.command("update")
def account_update(
    name: str = typer.Option("default", "--name", help="Account name."),
    cash: str | None = typer.Option(None, "--cash", help="Current cash in CNY."),
    cooldown: bool | None = typer.Option(
        None,
        "--cooldown/--no-cooldown",
        help="Enable or disable the account cooldown flag.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Update explicit account state without calculating trades."""
    try:
        account = _store().update_account(
            name,
            _parse_money(cash) if cash is not None else None,
            cooldown,
        )
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_account(account, json_output)


@position_app.command("set")
def position_set(
    code: str = typer.Option(..., "--code", help="Six-digit stock code."),
    stock_name: str = typer.Option(..., "--name", help="Stock name."),
    quantity: int = typer.Option(..., "--quantity", min=1, help="Total shares."),
    sellable: int = typer.Option(
        ...,
        "--sellable",
        min=0,
        help="Shares currently sellable under T+1.",
    ),
    cost: str = typer.Option(..., "--cost", help="Average cost per share."),
    bought_on: str = typer.Option(
        ...,
        "--bought-on",
        help="Most recent position change date in YYYY-MM-DD format.",
    ),
    account_name: str = typer.Option(
        "default", "--account", help="Account name."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Create or replace one position in the independent account."""
    try:
        position = _store().upsert_position(
            account_name,
            code,
            stock_name,
            quantity,
            sellable,
            _parse_money(cost),
            _parse_iso_date(bought_on),
        )
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_positions((position,), json_output)


@position_app.command("list")
def position_list(
    account_name: str = typer.Option(
        "default", "--account", help="Account name."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """List positions stored in the independent account."""
    try:
        positions = _store().list_positions(account_name)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_positions(positions, json_output)


@thesis_app.command("set")
def thesis_set(
    key: str = typer.Option(..., "--key", help="Stable ASCII thesis key."),
    title: str = typer.Option(..., "--title", help="Human-readable title."),
    status: str = typer.Option(
        "draft",
        "--status",
        help="draft, active, watch, realized, invalidated, or archived.",
    ),
    summary: str = typer.Option(..., "--summary", help="Testable thesis summary."),
    realization: str = typer.Option(
        ..., "--realization", help="Condition that realizes the thesis."
    ),
    invalidation: str = typer.Option(
        ..., "--invalidation", help="Condition that invalidates the thesis."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Create or replace one thesis in the engine database."""
    try:
        thesis = _store().upsert_thesis(
            key, title, status, summary, realization, invalidation
        )
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_theses((thesis,), json_output)


@thesis_app.command("list")
def thesis_list(
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """List theses stored by the independent engine."""
    try:
        theses = _store().list_theses()
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_theses(theses, json_output)


@thesis_app.command("link")
def thesis_link(
    key: str = typer.Option(..., "--key", help="Thesis key."),
    code: str = typer.Option(..., "--code", help="Position stock code."),
    account_name: str = typer.Option(
        "default", "--account", help="Account name."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Link an existing position to an existing thesis."""
    try:
        link = _store().link_position_thesis(account_name, code, key)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(link.model_dump_json(indent=2))
    else:
        typer.echo(f"已关联持仓 {link.code} -> 预期 {link.thesis_key}")


@pool_app.command("set")
def pool_set(
    key: str = typer.Option(..., "--key", help="Stable ASCII pool key."),
    name: str = typer.Option(..., "--name", help="Human-readable pool name."),
    thesis_key: str | None = typer.Option(
        None, "--thesis", help="Optional existing thesis key."
    ),
    active: bool = typer.Option(
        True, "--active/--inactive", help="Set pool activity state."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Create or replace a fixed watch pool."""
    try:
        pool = _store().upsert_watch_pool(key, name, thesis_key, active)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_watch_pool(pool, (), json_output)


@pool_app.command("member")
def pool_member(
    pool_key: str = typer.Option(..., "--pool", help="Watch pool key."),
    code: str = typer.Option(..., "--code", help="Six-digit stock code."),
    role: str = typer.Option(
        "direct", "--role", help="Member role: direct or research."
    ),
    tradable: bool = typer.Option(
        True,
        "--tradable/--research-only",
        help="Whether the member is eligible for trading.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Create or replace one member of a fixed watch pool."""
    try:
        member = _store().set_watch_pool_member(
            pool_key, code, role, tradable
        )
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(member.model_dump_json(indent=2))
    else:
        typer.echo(
            f"已保存固定池成员 {member.pool_key}/{member.code} "
            f"role={member.role} tradable={str(member.tradable).lower()}"
        )


@pool_app.command("show")
def pool_show(
    key: str = typer.Option(..., "--key", help="Watch pool key."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Show one fixed watch pool and all registered members."""
    try:
        store = _store()
        pool = store.get_watch_pool(key)
        members = store.list_watch_pool_members(key)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_watch_pool(pool, members, json_output)


@risk_app.command("set")
def risk_set(
    key: str = typer.Option(..., "--key", help="Stable ASCII risk key."),
    name: str = typer.Option(..., "--name", help="Human-readable risk name."),
    max_exposure: str = typer.Option(
        ..., "--max-exposure", help="Maximum portfolio exposure percent."
    ),
    active: bool = typer.Option(
        True, "--active/--inactive", help="Set risk factor activity state."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Create or replace one portfolio risk factor."""
    try:
        factor = _store().upsert_risk_factor(
            key,
            name,
            _parse_decimal(max_exposure, "max-exposure"),
            active,
        )
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_risk_factors((factor,), json_output)


@risk_app.command("list")
def risk_list(
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """List risk factors stored by the independent engine."""
    try:
        factors = _store().list_risk_factors()
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_risk_factors(factors, json_output)


@risk_app.command("link")
def risk_link(
    key: str = typer.Option(..., "--key", help="Risk factor key."),
    code: str = typer.Option(..., "--code", help="Position stock code."),
    account_name: str = typer.Option(
        "default", "--account", help="Account name."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Link an existing position to an existing risk factor."""
    try:
        link = _store().link_position_risk_factor(account_name, code, key)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(link.model_dump_json(indent=2))
    else:
        typer.echo(f"已关联持仓 {link.code} -> 风险因子 {link.risk_factor_key}")


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


def _store() -> ReplayStore:
    settings = TraderSettings.load()
    return ReplayStore(settings.data_dir / "trader.db")


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError as exc:
        raise ReplayError("date must use YYYYMMDD format") from exc


def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise PortfolioError("bought-on must use YYYY-MM-DD format") from exc


def _parse_money(value: str) -> Decimal:
    return _parse_decimal(value, "money amount")


def _parse_decimal(value: str, label: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise PortfolioError(f"invalid {label}: {value}") from exc


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


def _print_judgment(record: JudgmentRecord, json_output: bool) -> None:
    if json_output:
        typer.echo(record.model_dump_json(indent=2))
        return
    typer.echo(
        f"只读判断 {record.created_at.strftime('%Y-%m-%d %H:%M:%S')} "
        f"id={record.id} snapshot={record.snapshot_id}"
    )
    typer.echo(
        f"状态：{record.status}  provider={record.provider} "
        f"model={record.model} attempts={record.attempts}"
    )
    if record.status == "failed":
        typer.echo(f"错误：{record.error}")
        return
    typer.echo("模式：只读提案，不执行交易")
    typer.echo("")
    typer.echo(f"{'代码':<8} {'动作':<10} {'置信度':>8}  理由")
    assert record.report is not None
    for proposal in record.report.proposals:
        typer.echo(
            f"{proposal.code:<8} {proposal.action:<10} "
            f"{proposal.confidence:>7.0%}  {proposal.reason}"
        )
    typer.echo("")
    typer.echo("限制：")
    for limitation in record.report.limitations:
        typer.echo(f"- {limitation}")


def _print_account(account: AccountState, json_output: bool) -> None:
    if json_output:
        typer.echo(account.model_dump_json(indent=2))
        return
    typer.echo(f"独立账户 {account.name}  id={account.id}")
    typer.echo(f"初始资金：¥{account.initial_cash:,.2f}")
    typer.echo(f"当前现金：¥{account.cash:,.2f}")
    typer.echo(f"冷静期：{'是' if account.cooldown else '否'}")


def _print_positions(
    positions: tuple[PositionState, ...], json_output: bool
) -> None:
    if json_output:
        typer.echo(
            json.dumps(
                [position.model_dump(mode="json") for position in positions],
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    typer.echo("独立账户持仓")
    typer.echo(
        f"{'代码':<8} {'名称':<10} {'数量':>8} {'可卖':>8} "
        f"{'成本':>10} {'买入日期':>12}"
    )
    for position in positions:
        typer.echo(
            f"{position.code:<8} {position.name:<10} {position.quantity:>8} "
            f"{position.sellable_quantity:>8} {position.average_cost:>10.2f} "
            f"{position.bought_on.isoformat():>12}"
        )


def _print_theses(
    theses: tuple[ThesisState, ...], json_output: bool
) -> None:
    if json_output:
        typer.echo(
            json.dumps(
                [thesis.model_dump(mode="json") for thesis in theses],
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    typer.echo("独立预期")
    typer.echo(f"{'KEY':<24} {'状态':<12} 标题")
    for thesis in theses:
        typer.echo(f"{thesis.key:<24} {thesis.status:<12} {thesis.title}")


def _print_watch_pool(
    pool: WatchPoolState,
    members: tuple[WatchPoolMember, ...],
    json_output: bool,
) -> None:
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "pool": pool.model_dump(mode="json"),
                    "members": [
                        member.model_dump(mode="json") for member in members
                    ],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    typer.echo(
        f"固定池 {pool.key}  name={pool.name} "
        f"active={str(pool.active).lower()} thesis={pool.thesis_key or '-'}"
    )
    typer.echo(f"{'代码':<8} {'角色':<10} {'可交易':<8}")
    for member in members:
        typer.echo(
            f"{member.code:<8} {member.role:<10} "
            f"{str(member.tradable).lower():<8}"
        )


def _print_risk_factors(
    factors: tuple[RiskFactorState, ...], json_output: bool
) -> None:
    if json_output:
        typer.echo(
            json.dumps(
                [factor.model_dump(mode="json") for factor in factors],
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    typer.echo("独立风险因子")
    typer.echo(f"{'KEY':<24} {'上限%':>10} {'启用':<8} 名称")
    for factor in factors:
        typer.echo(
            f"{factor.key:<24} {factor.max_exposure_pct:>10.2f} "
            f"{str(factor.active).lower():<8} {factor.name}"
        )
