from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, InvalidOperation

import typer

from trading_engine import __version__
from trading_engine.market.astock import AstockClient
from trading_engine.config import TraderSettings
from trading_engine.market.context_cli import context_app, evidence_app
from trading_engine.market.context_store import ContextStore
from trading_engine.dates import parse_trading_date
from trading_engine.errors import PortfolioError, ReplayError, TradingEngineError
from trading_engine.market.live import LiveMarketData
from trading_engine.store.models import (
    AccountState,
    PositionState,
    RiskFactorState,
    ThesisState,
    TradePlanState,
    WatchPoolMember,
    WatchPoolState,
)
from trading_engine.trading.paper_cli import paper_app
from trading_engine.trading.paper_store import PaperStore
from trading_engine.brief import BriefGenerator
from trading_engine.market.replay import (
    ReplayEngine,
    ReplayMarketData,
    parse_clock_time,
)
from trading_engine.store.storage import ReplayStore
from trading_engine.engine.watch import watch_app


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
account_app = typer.Typer(help="Manage the engine's independent SQLite account.")
position_app = typer.Typer(help="Manage positions in the independent account.")
thesis_app = typer.Typer(help="Manage independent investment theses.")
pool_app = typer.Typer(help="Manage independent fixed watch pools.")
risk_app = typer.Typer(help="Manage independent portfolio risk factors.")
plan_app = typer.Typer(help="Manage structured daily if-then trade plans.")
app.add_typer(config_app, name="config")
app.add_typer(astock_app, name="astock")
app.add_typer(replay_app, name="replay")
app.add_typer(account_app, name="account")
app.add_typer(position_app, name="position")
app.add_typer(thesis_app, name="thesis")
app.add_typer(pool_app, name="pool")
app.add_typer(risk_app, name="risk")
app.add_typer(plan_app, name="plan")
app.add_typer(evidence_app, name="evidence")
app.add_typer(context_app, name="context")
app.add_typer(paper_app, name="paper")
app.add_typer(watch_app, name="watch")


@app.command("brief")
def brief(
    account_name: str = typer.Option(
        "paper", "--account", help="Account name."
    ),
) -> None:
    """Generate minimal state summary for brain startup.

    Does NOT fetch market data. Call astock directly for quotes.
    """
    try:
        settings = TraderSettings.load()
        database = settings.data_dir / "trader.db"
        result = BriefGenerator(
            ReplayStore(database), PaperStore(database)
        ).generate(account_name)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False, default=str))


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


@account_app.command("init")
def account_init(
    cash: str = typer.Option(..., "--cash", help="Current cash in CNY."),
    initial_cash: str | None = typer.Option(
        None,
        "--initial-cash",
        help="Initial capital in CNY; defaults to current cash.",
    ),
    name: str = typer.Option("paper", "--name", help="Account name."),
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
    name: str = typer.Option("paper", "--name", help="Account name."),
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
    name: str = typer.Option("paper", "--name", help="Account name."),
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
        "paper", "--account", help="Account name."
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
        "paper", "--account", help="Account name."
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
    thesis_type: str | None = typer.Option(
        None, "--type", help="continuous, event, or realtime."
    ),
    stage: str | None = typer.Option(
        None,
        "--stage",
        help="emerging, confirmed, accelerating, realizing, or ended.",
    ),
    catalyst_anchor: str | None = typer.Option(
        None, "--catalyst-anchor", help="Observable catalyst or data anchor."
    ),
    transmission_chain: str | None = typer.Option(
        None,
        "--transmission-chain",
        help="Shortest event-to-company benefit chain.",
    ),
    linkage_conclusion: str | None = typer.Option(
        None,
        "--linkage",
        help="company, sub_industry, end_demand, or unresolved.",
    ),
    confirmation_condition: str | None = typer.Option(
        None,
        "--confirmation",
        help="Market behavior that confirms the thesis for trading.",
    ),
    bet_pct: str | None = typer.Option(
        None,
        "--bet",
        help="Bet size as percentage of total assets (0-100).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Create or replace one thesis in the engine database."""
    try:
        thesis = _store().upsert_thesis(
            key,
            title,
            status,
            summary,
            realization,
            invalidation,
            thesis_type,
            stage,
            catalyst_anchor,
            transmission_chain,
            linkage_conclusion,
            confirmation_condition,
            _parse_decimal(bet_pct, "bet") if bet_pct is not None else None,
        )
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_theses((thesis,), json_output)


@thesis_app.command("list")
def thesis_list(
    active_only: bool = typer.Option(
        False, "--active-only", help="Only show active/watch theses."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """List theses stored by the independent engine."""
    try:
        theses = _store().list_theses()
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if active_only:
        theses = tuple(thesis for thesis in theses if thesis.status in {"active", "watch"})
    _print_theses(theses, json_output)


@thesis_app.command("link")
def thesis_link(
    key: str = typer.Option(..., "--key", help="Thesis key."),
    code: str = typer.Option(..., "--code", help="Position stock code."),
    account_name: str = typer.Option(
        "paper", "--account", help="Account name."
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
    monitoring_status: str | None = typer.Option(
        None,
        "--status",
        help="active, dormant, or archived. Overrides --active/--inactive.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Create or replace a fixed watch pool."""
    try:
        pool = _store().upsert_watch_pool(
            key, name, thesis_key, active, monitoring_status
        )
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
    relationship: str | None = typer.Option(
        None,
        "--relationship",
        help="direct, volume, adjacent, cost_pressure, or research.",
    ),
    causal_chain: str | None = typer.Option(
        None,
        "--causal-chain",
        help="Free-text causal transmission chain for this member.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Create or replace one member of a fixed watch pool."""
    try:
        member = _store().set_watch_pool_member(
            pool_key, code, role, tradable, relationship, causal_chain
        )
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(member.model_dump_json(indent=2))
    else:
        typer.echo(
            f"已保存固定池成员 {member.pool_key}/{member.code} "
            f"role={member.role} relationship={member.relationship} "
            f"tradable={str(member.tradable).lower()} "
            f"causal_chain={member.causal_chain or '-'}"
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


@pool_app.command("list")
def pool_list(
    status: str | None = typer.Option(
        None, "--status", help="Filter by active/dormant/archived status."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """List all fixed watch pools and their members."""
    try:
        store = _store()
        pools = store.list_watch_pools()
        if status is not None:
            pools = tuple(pool for pool in pools if pool.monitoring_status == status)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        result = [
            {
                **pool.model_dump(mode="json"),
                "members": [
                    member.model_dump(mode="json")
                    for member in store.list_watch_pool_members(pool.key)
                ],
            }
            for pool in pools
        ]
        typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        for pool in pools:
            members = store.list_watch_pool_members(pool.key)
            _print_watch_pool(pool, members, False)


@plan_app.command("set")
def plan_set(
    key: str = typer.Option(..., "--key", help="Stable ASCII plan key."),
    trading_date: str = typer.Option(
        ..., "--date", help="Trading date in YYYY-MM-DD format."
    ),
    thesis_key: str = typer.Option(..., "--thesis", help="Existing thesis key."),
    action: str = typer.Option(..., "--action", help="BUY or SELL."),
    code: str = typer.Option(..., "--code", help="Target stock code."),
    name: str = typer.Option(..., "--name", help="Target stock name."),
    quantity: int = typer.Option(..., "--quantity", help="100-share lot quantity."),
    priority: int = typer.Option(100, "--priority", help="Lower ranks first."),
    trigger: list[str] = typer.Option(
        ..., "--trigger", help="Repeat for every required trigger condition."
    ),
    ranking_notes: str = typer.Option(
        ..., "--ranking-notes", help="Account-ranking instructions."
    ),
    rationale: str = typer.Option(..., "--rationale", help="Plan rationale."),
    status: str = typer.Option("active", "--status", help="Plan status."),
    buy_point_type: str | None = typer.Option(
        None,
        "--buy-point",
        help="confirmation, first_board, or pullback for BUY plans.",
    ),
    exit_mode: str | None = typer.Option(
        None,
        "--exit-mode",
        help="expectation or trade_confirmation for SELL plans.",
    ),
    risk_factor_key: str | None = typer.Option(
        None, "--risk", help="Optional named shared-risk factor."
    ),
    observe: list[str] | None = typer.Option(
        None, "--observe", help="Repeat for observation checkpoints in HH:MM."
    ),
    required_observations: int = typer.Option(
        1, "--required-observations", help="Required matching checkpoints."
    ),
    guard: list[str] | None = typer.Option(
        None, "--guard", help="Repeat for mandatory guard conditions."
    ),
    cancel: list[str] | None = typer.Option(
        None, "--cancel", help="Repeat for conditions that cancel the plan."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Create or replace one structured daily if-then trade plan."""
    try:
        plan = _store().upsert_trade_plan(
            key=key,
            trading_date=_parse_iso_date(trading_date),
            thesis_key=thesis_key,
            action=action.upper(),
            target_code=code,
            target_name=name,
            quantity=quantity,
            priority=priority,
            trigger_conditions=tuple(trigger),
            ranking_notes=ranking_notes,
            rationale=rationale,
            status=status,
            buy_point_type=buy_point_type,
            exit_mode=exit_mode,
            risk_factor_key=risk_factor_key,
            observation_times=tuple(
                parse_clock_time(value) for value in (observe or [])
            ),
            required_observations=required_observations,
            guard_conditions=tuple(guard or []),
            cancel_conditions=tuple(cancel or []),
        )
    except (TradingEngineError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_trade_plans((plan,), json_output)


@plan_app.command("list")
def plan_list(
    trading_date: str | None = typer.Option(
        None, "--date", help="Optional date in YYYY-MM-DD format."
    ),
    status: list[str] | None = typer.Option(
        None, "--status", help="Repeat to filter plan statuses."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """List structured trade plans stored by the independent engine."""
    try:
        plans = _store().list_trade_plans(
            _parse_iso_date(trading_date) if trading_date else None,
            tuple(status) if status else None,
        )
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_trade_plans(plans, json_output)


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
        "paper", "--account", help="Account name."
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
        return parse_trading_date(value)
    except TradingEngineError as exc:
        raise ReplayError(str(exc)) from exc


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
    typer.echo(f"{'KEY':<24} {'状态':<12} {'下注%':>8} 标题")
    for thesis in theses:
        bet = f"{thesis.bet_pct:.2f}" if thesis.bet_pct is not None else "-"
        typer.echo(
            f"{thesis.key:<24} {thesis.status:<12} {bet:>8} {thesis.title}"
        )


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
        f"status={pool.monitoring_status} thesis={pool.thesis_key or '-'}"
    )
    typer.echo(f"{'代码':<8} {'角色':<10} {'关系':<16} {'可交易':<8} 传导链")
    for member in members:
        typer.echo(
            f"{member.code:<8} {member.role:<10} {member.relationship:<16} "
            f"{str(member.tradable).lower():<8} {member.causal_chain or '-'}"
        )


def _print_trade_plans(
    plans: tuple[TradePlanState, ...], json_output: bool
) -> None:
    if json_output:
        typer.echo(
            json.dumps(
                [plan.model_dump(mode="json") for plan in plans],
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    typer.echo("结构化交易预案")
    typer.echo(f"{'日期':<12} {'优先级':>6} {'动作':<6} {'代码':<8} {'数量':>8} KEY")
    for plan in plans:
        typer.echo(
            f"{plan.trading_date.isoformat():<12} {plan.priority:>6} "
            f"{plan.action:<6} {plan.target_code:<8} {plan.quantity:>8} "
            f"{plan.key}"
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
