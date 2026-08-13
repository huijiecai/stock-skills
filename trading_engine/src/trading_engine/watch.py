"""Watch-mode commands: open (session context), heartbeat (light scan), probe (deep dive).

These three commands implement the layered watch protocol:
- ``watch open``      — load session context once at open (positions/theses/pools/plans/rules)
- ``watch heartbeat`` — per-round lightweight scan (index/positions/pool X-Y/limit-up detail)
- ``watch probe``     — on-demand deep dive (pool member detail / single-stock minute path)

The engine stays stateless: the caller (LLM or scheduler) holds the session
context from ``watch open`` and decides per heartbeat whether to probe.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import typer

from trading_engine.astock import AstockClient
from trading_engine.config import TraderSettings
from trading_engine.context import (
    MONITORED_POOL_STATUSES,
    DecisionContextBuilder,
    _pool_signals,
    extract_context_quotes,
)
from trading_engine.dates import parse_trading_date
from trading_engine.errors import TradingEngineError
from trading_engine.replay import ReplayMarketData, parse_clock_time, replay_time
from trading_engine.storage import ReplayStore

_SHANGHAI = ZoneInfo("Asia/Shanghai")

# Pool health threshold: a pool is "weak" (◆ marker) when up_count <= this fraction
# of quoted_count. Matches the spirit of §4.1 exit-B (≤2/5, ≤3/7, ≤4/8).
WEAK_POOL_FRACTION = 0.4

# Position §4.1 evaluation trigger line (absolute change_pct)
EVAL_LINE_PCT = Decimal("2")

watch_app = typer.Typer(help="Layered watch protocol: open / heartbeat / probe.")


# ---------------------------------------------------------------------- #
# watch open
# ---------------------------------------------------------------------- #

@watch_app.command("open")
def watch_open(
    account_name: str = typer.Option("paper", "--account", help="Account name."),
) -> None:
    """Load session context once at open (positions + theses + pools + plans + rules)."""
    try:
        settings = TraderSettings.load()
        store = ReplayStore(settings.data_dir / "trader.db")
        typer.echo(format_open(store, account_name))
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


def format_open(store: ReplayStore, account_name: str) -> str:
    """Render the session context a watcher carries in memory all day."""
    account = store.get_account(account_name)
    positions = store.list_positions(account_name)
    theses = {t.key: t for t in store.list_theses()}
    risk_factors = {r.key: r for r in store.list_risk_factors()}

    lines: list[str] = []
    lines.append(f"=== 看盘会话上下文 账户={account_name} ===")
    lines.append(
        f"现金=¥{account.cash:,.2f} 初始=¥{account.initial_cash:,.2f} "
        f"冷静期={'是' if account.cooldown else '否'}"
    )
    lines.append("")

    # Positions with thesis + risk
    lines.append(f"--- 持仓（{len(positions)}）---")
    for pos in positions:
        links = store.list_position_theses(account_name, pos.code)
        thesis_titles = "/".join(
            theses[lk.thesis_key].title for lk in links if lk.thesis_key in theses
        ) or "?"
        # risk factors for this position
        risk_links = store.list_position_risk_factors(account_name, pos.code)
        risk_names = "/".join(
            risk_factors[rl.risk_factor_key].name
            for rl in risk_links
            if rl.risk_factor_key in risk_factors
        )
        lines.append(
            f"  {pos.code} {pos.name} {pos.quantity}股(可卖{pos.sellable_quantity}) "
            f"@{pos.average_cost:.2f} 买入日{pos.bought_on} "
            f"[预期:{thesis_titles}]"
            + (f" [风险:{risk_names}]" if risk_names else "")
        )

    # Trade plans (active/triggered)
    lines.append("")
    plans = store.list_trade_plans(statuses=("active", "triggered"))
    lines.append(f"--- 盘前预案（{len(plans)}）---")
    for plan in plans:
        thesis_title = theses[plan.thesis_key].title if plan.thesis_key in theses else "?"
        action = plan.action.value if hasattr(plan.action, "value") else str(plan.action)
        lines.append(
            f"  {plan.key} {action} {plan.target_code} {plan.quantity}股 "
            f"[{thesis_title}]"
        )
        if plan.trigger_conditions:
            lines.append(f"    触发: {plan.trigger_conditions}")
        if plan.guard_conditions:
            lines.append(f"    守卫: {plan.guard_conditions}")

    # Watch pools overview (exclude the synthetic current_holdings pool)
    lines.append("")
    pools = [
        p for p in store.list_watch_pools()
        if p.monitoring_status in MONITORED_POOL_STATUSES and p.key != "current_holdings"
    ]
    lines.append(f"--- 主题池（{len(pools)}）---")
    for pool in pools:
        members = store.list_watch_pool_members(pool.key)
        tradable = sum(1 for m in members if m.tradable)
        lines.append(
            f"  {pool.key} {pool.name} 成员{len(members)}(主板可买{tradable})"
        )

    # Rules reminder (static — the watcher's mental model)
    lines.append("")
    lines.append("--- 规则（盘中判断依据）---")
    lines.append("  §4.1双出口: 出口A(预期兑现/结束/被否定→清仓) | 出口B(资金撤退≥2信号→减仓)")
    lines.append("  三维确认: 资金广度+价格响应+可验证依据 (买入资格)")
    lines.append("  硬约束: T+1 | 主板(000/001/002/003/600/601/603/605) | 整手100 | 14:50后不开新仓")
    lines.append("  分歧≠结束: 预期依据仍在验证→持有; 单一价格波动不独立触发卖出")
    return "\n".join(lines)


# ---------------------------------------------------------------------- #
# watch heartbeat
# ---------------------------------------------------------------------- #

@watch_app.command("heartbeat")
def watch_heartbeat(
    date_value: str = typer.Option(..., "--date", help="Trading date YYYYMMDD or YYYY-MM-DD."),
    until: str = typer.Option(..., "--until", help="Clock time HH:MM."),
    account_name: str = typer.Option("paper", "--account", help="Account name."),
) -> None:
    """Per-round lightweight scan. Answers: any signal this round?"""
    try:
        settings = TraderSettings.load()
        database = settings.data_dir / "trader.db"
        store = ReplayStore(database)
        builder = DecisionContextBuilder(store, None)  # type: ignore[arg-type]
        trading_date = parse_trading_date(date_value, "date")
        clock = replay_time(trading_date, parse_clock_time(until))
        typer.echo(format_heartbeat(builder, store, settings, account_name, trading_date, clock))
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


def format_heartbeat(
    builder: DecisionContextBuilder,
    store: ReplayStore,
    settings: TraderSettings,
    account_name: str,
    trading_date: date,
    at: datetime,
    *,
    live: bool = False,
) -> str:
    """Render one heartbeat: index + positions (with §4.1 markers) + pool X-Y + limit-up detail."""
    client = AstockClient(settings.astock_binary, timeout_seconds=60)
    codes = builder.required_live_codes(account_name, trading_date)
    if live:
        from trading_engine.live import LiveMarketData
        provider = LiveMarketData(client, codes, include_discovery=True)
    else:
        provider = ReplayMarketData(client, trading_date, codes, include_discovery=True)
    snapshot = provider.snapshot(at)

    discovery = snapshot.payload.get("market_discovery") or {}
    quotes = extract_context_quotes(snapshot)
    quote_by_code = {q.code: q for q in quotes}
    theses = {t.key: t for t in store.list_theses()}

    lines: list[str] = []
    shanghai = at.astimezone(_SHANGHAI) if at.tzinfo else at.replace(tzinfo=_SHANGHAI)
    lines.append(f"心跳 {shanghai.strftime('%H:%M')}")

    # ① Index (one line, 4 core indices + breadth)
    _render_heartbeat_index(lines, discovery)

    # ② Positions with thesis + §4.1 trigger marker
    positions = store.list_positions(account_name)
    lines.append("")
    lines.append(f"② 持仓（{len(positions)}）:")
    for pos in positions:
        quote = quote_by_code.get(pos.code)
        if quote is None:
            lines.append(f"  {pos.code} {pos.name} (无报价)")
            continue
        links = store.list_position_theses(account_name, pos.code)
        thesis_short = "/".join(
            theses[lk.thesis_key].title for lk in links if lk.thesis_key in theses
        ) or "?"
        flag = " ⚠触发§4.1" if abs(quote.change_pct) >= EVAL_LINE_PCT else ""
        lines.append(
            f"  {pos.code} {pos.name} {quote.price:.2f} {quote.change_pct:+.2f}%{flag} [{thesis_short}]"
        )

    # ③ Pool health (X/Y only, no member detail; ◆ if weak)
    lines.append("")
    lines.append("③ 池健康度:")
    pools = [
        p for p in store.list_watch_pools()
        if p.monitoring_status in MONITORED_POOL_STATUSES and p.key != "current_holdings"
    ]
    pool_metrics: list[str] = []
    for pool in pools:
        members = store.list_watch_pool_members(pool.key)
        _, metrics = _pool_signals(members, quote_by_code)
        weak = "◆" if (
            metrics.quoted_count > 0
            and Decimal(metrics.up_count) / Decimal(metrics.quoted_count) <= Decimal(str(WEAK_POOL_FRACTION))
        ) else ""
        pool_metrics.append(
            f"{pool.name} {metrics.up_count}/{metrics.quoted_count}{weak}"
        )
    lines.append("  " + " · ".join(pool_metrics))

    # ④ Limit-up detail (code/name/concepts/consecutive, mainboard first, top 10)
    _render_heartbeat_limits(lines, discovery)

    # Signal summary (mechanical: list what crossed lines, not a judgment)
    signals = _heartbeat_signals(positions, quote_by_code, pools, store, account_name)
    lines.append("")
    if signals:
        lines.append("信号: " + " | ".join(signals))
    else:
        lines.append("信号: 无")
    return "\n".join(lines)


def _render_heartbeat_index(lines: list[str], discovery: dict[str, Any]) -> None:
    indices = discovery.get("indices") or []
    if not indices:
        lines.append("① 指数: (无数据)")
        return
    short = {
        "上证指数": "上证", "深证成指": "深证", "科创50": "科创50",
        "创业板指": "创业板",
    }
    core = " ".join(
        f"{short.get(idx.get('name'), idx.get('name', ''))}{_fmt_pct(idx.get('change_pct'))}"
        for idx in indices[:4]
    )
    breadth = discovery.get("breadth") or {}
    limit_count = breadth.get("limit_up_count")
    if limit_count is None:
        detail = discovery.get("limit_up_detail") or []
        limit_count = len(detail)
    amount_yi = _to_float(breadth.get("total_amount")) / 1e8
    lines.append(f"① 指数: {core} | 涨停{limit_count}只 成交{amount_yi:.0f}亿")


def _render_heartbeat_limits(lines: list[str], discovery: dict[str, Any]) -> None:
    detail = discovery.get("limit_up_detail") or []
    if not detail:
        return
    # mainboard first, then by consecutive_days desc
    mainboard_prefixes = ("000", "001", "002", "003", "600", "601", "603", "605")
    sorted_detail = sorted(
        detail,
        key=lambda r: (0 if str(r.get("code", ""))[:3] in mainboard_prefixes else 1,
                       -int(r.get("consecutive_days", 1) or 1)),
    )
    lines.append("")
    lines.append("④ 涨停明细:")
    for row in sorted_detail[:10]:
        concepts = "/".join((row.get("concepts") or [])[:2]) or "-"
        days = row.get("consecutive_days", 1) or 1
        day_tag = f"{days}连板" if days > 1 else "首板"
        lines.append(
            f"  {row.get('code', '')} {row.get('name', '')} "
            f"{_fmt_pct(row.get('change_pct'))} {day_tag} [{concepts}]"
        )


def _heartbeat_signals(
    positions,
    quote_by_code: dict,
    pools,
    store: ReplayStore,
    account_name: str,
) -> list[str]:
    """Mechanical signal detection (no judgment). Lists what crossed trigger lines."""
    signals: list[str] = []
    theses_cache = {t.key: t for t in store.list_theses()}
    for pos in positions:
        quote = quote_by_code.get(pos.code)
        if quote is None:
            continue
        if abs(quote.change_pct) >= EVAL_LINE_PCT:
            links = store.list_position_theses(account_name, pos.code)
            thesis_short = "/".join(
                theses_cache[lk.thesis_key].title for lk in links if lk.thesis_key in theses_cache
            ) or "?"
            direction = "跌" if quote.change_pct < 0 else "涨"
            signals.append(
                f"{pos.name}{quote.change_pct:+.2f}%{direction}破线触发§4.1[{thesis_short}]"
            )
    # weak pools
    for pool in pools:
        members = store.list_watch_pool_members(pool.key)
        _, metrics = _pool_signals(members, quote_by_code)
        if (
            metrics.quoted_count > 0
            and Decimal(metrics.up_count) / Decimal(metrics.quoted_count) <= Decimal(str(WEAK_POOL_FRACTION))
        ):
            signals.append(f"{pool.name}池{metrics.up_count}/{metrics.quoted_count}连续走弱")
    return signals


# ---------------------------------------------------------------------- #
# watch probe
# ---------------------------------------------------------------------- #

@watch_app.command("probe")
def watch_probe(
    date_value: str = typer.Option(..., "--date", help="Trading date YYYYMMDD or YYYY-MM-DD."),
    until: str = typer.Option(..., "--until", help="Clock time HH:MM."),
    pool: str = typer.Option(None, "--pool", help="Pool key to inspect member detail."),
    code: str = typer.Option(None, "--code", help="Single stock code for minute path."),
    account_name: str = typer.Option("paper", "--account", help="Account name."),
) -> None:
    """On-demand deep dive: pool member detail or single-stock minute path."""
    if not pool and not code:
        typer.echo("probe requires --pool <key> or --code <6-digit>", err=True)
        raise typer.Exit(code=1)
    try:
        settings = TraderSettings.load()
        database = settings.data_dir / "trader.db"
        store = ReplayStore(database)
        builder = DecisionContextBuilder(store, None)  # type: ignore[arg-type]
        trading_date = parse_trading_date(date_value, "date")
        clock = replay_time(trading_date, parse_clock_time(until))
        client = AstockClient(settings.astock_binary, timeout_seconds=60)
        codes = builder.required_live_codes(account_name, trading_date)
        if code and code not in codes:
            codes = tuple(sorted(set(codes) | {code}))
        provider = ReplayMarketData(client, trading_date, codes, include_discovery=True)
        snapshot = provider.snapshot(clock)
        quotes = extract_context_quotes(snapshot)
        quote_by_code = {q.code: q for q in quotes}
        if pool:
            typer.echo(format_probe_pool(store, pool, quote_by_code))
        else:
            q = quote_by_code.get(code)
            if q is None:
                typer.echo(f"{code}: no quote at {until}", err=True)
                raise typer.Exit(code=1)
            typer.echo(format_probe_code(code, q))
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


def format_probe_pool(
    store: ReplayStore, pool_key: str, quote_by_code: dict
) -> str:
    """Render a pool's full member detail: who leads, who lags."""
    pool = next((p for p in store.list_watch_pools() if p.key == pool_key), None)
    if pool is None:
        return f"pool not found: {pool_key}"
    members = store.list_watch_pool_members(pool.key)
    signals, metrics = _pool_signals(members, quote_by_code)
    lines: list[str] = []
    lines.append(
        f"=== {pool.name} ({pool.key}) {metrics.up_count}涨{metrics.down_count}跌 "
        f"涨停{metrics.limit_up_count} 广度{metrics.breadth_pct:.0f}% ==="
    )
    # sort members by change_pct desc
    sorted_signals = sorted(signals, key=lambda s: s.change_pct, reverse=True)
    for sig in sorted_signals:
        star = "★涨停" if sig.is_limit_up else ("▲强势" if sig.is_strong else "")
        amount_yi = _to_float(sig.amount) / 1e8
        lines.append(
            f"  {sig.code} {sig.name or sig.code} {_fmt_pct(sig.change_pct)} "
            f"成交{amount_yi:.1f}亿{(' ' + star) if star else ''}"
        )
    return "\n".join(lines)


def format_probe_code(code: str, quote) -> str:
    """Render a single stock's snapshot for minute-path analysis."""
    amount_yi = _to_float(quote.amount) / 1e8
    lines = [
        f"=== {code} {getattr(quote, 'name', '') or code} ===",
        f"  现价{quote.price:.2f} 涨跌{_fmt_pct(quote.change_pct)}",
        f"  开{quote.open:.2f} 高{quote.high:.2f} 低{quote.low:.2f} 前收{quote.pre_close:.2f}",
        f"  成交{amount_yi:.1f}亿",
    ]
    # path context if available
    path = getattr(quote, "path", None)
    if path is not None:
        rebound = getattr(path, "rebound_from_low_pct", None)
        drawdown = getattr(path, "drawdown_from_high_pct", None)
        dipped = getattr(path, "dipped_below_pre_close", None)
        if rebound is not None:
            lines.append(f"  路径: 反弹{rebound:+.2f}% 回撤{drawdown:+.2f}% "
                         f"{'破前收' if dipped else '守前收'}")
    return "\n".join(lines)


# ---------------------------------------------------------------------- #
# helpers
# ---------------------------------------------------------------------- #

def _fmt_pct(value) -> str:
    if value is None:
        return "?"
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "?"


def _to_float(value) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------- #
# watch run — autonomous agent loop
# ---------------------------------------------------------------------- #

@watch_app.command("run")
def watch_run(
    date_value: str = typer.Option(..., "--date", help="Trading date YYYYMMDD or YYYY-MM-DD."),
    strategy: str = typer.Option(
        "expectation_driven", "--strategy",
        help="Strategy package under trading_engine.strategies (e.g. expectation_driven).",
    ),
    account_name: str = typer.Option("paper", "--account", help="Account name."),
    max_rounds: int = typer.Option(
        None, "--max-rounds", min=1,
        help="Limit to first N heartbeats (for testing).",
    ),
    live: bool = typer.Option(
        False, "--live",
        help="Live mode: use TDX real-time data (no ClickHouse sync needed).",
    ),
    verbose: bool = typer.Option(
        False, "--verbose",
        help="Print the full prompt sent to the LLM each round (debug).",
    ),
) -> None:
    """Run an autonomous agent watch session (open → heartbeats → probes → trades)."""
    try:
        import importlib

        from trading_engine.agent import run_watch_session

        # Load the strategy package: it must export SYSTEM_PROMPT + register_tools.
        strategy_mod = importlib.import_module(f"trading_engine.strategies.{strategy}")
        trading_date = parse_trading_date(date_value, "date")
        events: list[str] = []

        def on_event(msg: str) -> None:
            typer.echo(msg)
            events.append(msg)

        run_watch_session(
            trading_date=trading_date,
            system_prompt=strategy_mod.SYSTEM_PROMPT,
            register_strategy_tools=strategy_mod.register_tools,
            account=account_name,
            max_rounds=max_rounds,
            live=live,
            verbose=verbose,
            on_event=on_event,
        )
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

