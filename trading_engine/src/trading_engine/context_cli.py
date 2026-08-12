from __future__ import annotations

import json
from datetime import datetime

import typer

from trading_engine.astock import AstockClient
from trading_engine.config import TraderSettings
from trading_engine.context import DecisionContextBuilder
from trading_engine.context_models import (
    CatalystEvidence,
    DecisionContextRecord,
    ReasoningRecord,
    ToolCallRecord,
)
from trading_engine.context_store import ContextStore
from trading_engine.dates import parse_trading_date
from trading_engine.errors import ContextError, StorageError, TradingEngineError
from trading_engine.live import LiveMarketData
from trading_engine.replay import (
    ReplayMarketData,
    parse_clock_time,
    replay_time,
)
from trading_engine.storage import ReplayStore


context_app = typer.Typer(help="Build auditable decision context snapshots.")
evidence_app = typer.Typer(help="Manage timestamped catalyst evidence.")
reasoning_app = typer.Typer(help="Manage LLM reasoning chains attached to contexts.")
tool_call_app = typer.Typer(help="Manage astock tool call records attached to contexts.")
context_app.add_typer(reasoning_app, name="reasoning")
context_app.add_typer(tool_call_app, name="tool-call")


@evidence_app.command("add")
def evidence_add(
    thesis_key: str = typer.Option(..., "--thesis", help="Existing thesis key."),
    kind: str = typer.Option(
        ..., "--kind", help="announcement, news, industry, policy, or other."
    ),
    source: str = typer.Option(..., "--source", help="Evidence source name."),
    published_at: str = typer.Option(
        ..., "--published-at", help="Publication time as timezone-aware ISO 8601."
    ),
    observed_at: str = typer.Option(
        ..., "--observed-at", help="First observation time as ISO 8601."
    ),
    summary: str = typer.Option(..., "--summary", help="Evidence summary."),
    stance: str = typer.Option(
        "neutral", "--stance", help="supports, contradicts, or neutral."
    ),
    reliability: str = typer.Option(
        "medium", "--reliability", help="low, medium, or high."
    ),
    source_url: str | None = typer.Option(
        None, "--url", help="Optional source URL."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Append one immutable catalyst evidence record."""
    try:
        _, context_store = _stores()
        evidence = context_store.add_evidence(
            thesis_key=thesis_key,
            kind=kind,
            source_name=source,
            published_at=_parse_aware_datetime(published_at),
            observed_at=_parse_aware_datetime(observed_at),
            summary=summary,
            stance=stance,
            reliability=reliability,
            source_url=source_url,
        )
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_evidence((evidence,), json_output)


@evidence_app.command("list")
def evidence_list(
    thesis_key: str | None = typer.Option(
        None, "--thesis", help="Optional thesis key filter."
    ),
    as_of: str | None = typer.Option(
        None, "--as-of", help="Only show evidence observable by this ISO time."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """List immutable evidence records from the engine database."""
    try:
        _, context_store = _stores()
        evidence = context_store.list_evidence(
            (thesis_key,) if thesis_key else None
        )
        if as_of is not None:
            cutoff = _parse_aware_datetime(as_of)
            evidence = tuple(
                item
                for item in evidence
                if item.published_at <= cutoff and item.observed_at <= cutoff
            )
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_evidence(evidence, json_output)


@context_app.command("capture")
def context_capture(
    account_name: str = typer.Option(
        "paper", "--account", help="Account name."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Capture all required live quotes and build one decision context."""
    try:
        settings = TraderSettings.load()
        store, context_store = _stores(settings)
        builder = DecisionContextBuilder(store, context_store)
        codes = builder.required_live_codes(account_name)
        snapshot = LiveMarketData(
            AstockClient(settings.astock_binary, timeout_seconds=60),
            codes,
            include_discovery=True,
        ).snapshot()
        record = builder.build(snapshot, account_name)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_context(record, json_output)


@context_app.command("replay")
def context_replay(
    replay_date: str = typer.Option(
        ..., "--date", help="Trading date in YYYY-MM-DD or YYYYMMDD format."
    ),
    until: str = typer.Option(..., "--until", help="Replay time in HH:MM format."),
    account_name: str = typer.Option(
        "paper", "--account", help="Account name."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Build the same context contract from a deterministic replay snapshot."""
    try:
        settings = TraderSettings.load()
        store, context_store = _stores(settings)
        builder = DecisionContextBuilder(store, context_store)
        trading_date = parse_trading_date(replay_date, "replay date")
        codes = builder.required_live_codes(account_name, trading_date)
        at = replay_time(trading_date, parse_clock_time(until))
        snapshot = ReplayMarketData(
            AstockClient(settings.astock_binary),
            trading_date,
            codes,
            include_discovery=True,
        ).snapshot(at)
        record = builder.build(snapshot, account_name)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_context(record, json_output)


@context_app.command("show")
def context_show(
    account_name: str = typer.Option(
        "paper", "--account", help="Account name."
    ),
    trading_date: str | None = typer.Option(
        None, "--date", help="Trading date in YYYY-MM-DD or YYYYMMDD format."
    ),
    until: str | None = typer.Option(
        None, "--until", help="Time in HH:MM format. Requires --date."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Show the latest persisted context, optionally filtered by date/time."""
    try:
        _, context_store = _stores()
        if trading_date is not None:
            parsed_date = parse_trading_date(trading_date, "trading date")
            record = context_store.get_context_by_date(
                account_name, parsed_date, until
            )
        else:
            record = context_store.latest_context(account_name)
        if record is None:
            raise ContextError("no decision context exists for this account")
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_context(record, json_output)


@reasoning_app.command("add")
def reasoning_add(
    context_id: str = typer.Option(
        ..., "--context", help="Decision context snapshot ID."
    ),
    observed: str = typer.Option(
        ..., "--observed", help="What the LLM saw (e.g. 'PCB板块排名第3，5只涨停')."
    ),
    hypothesis: str = typer.Option(
        ...,
        "--hypothesis",
        help="What the LLM hypothesized (e.g. 'AI硬件需求拉动PCB放量').",
    ),
    verified: str = typer.Option(
        ...,
        "--verified",
        help="What the LLM verified via astock (e.g. '沪电领涨8.5%，深南盘中跟进').",
    ),
    conclusion: str = typer.Option(
        ...,
        "--conclusion",
        help="Final conclusion (e.g. '三维确认，BUY 沪电 100股').",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Append one immutable LLM reasoning chain to a decision context."""
    try:
        _, context_store = _stores()
        record = context_store.add_reasoning(
            context_id=context_id,
            observed=observed,
            hypothesis=hypothesis,
            verified=verified,
            conclusion=conclusion,
        )
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_reasoning((record,), json_output, context_store)


@reasoning_app.command("list")
def reasoning_list(
    context_id: str | None = typer.Option(
        None, "--context", help="Optional context ID filter."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """List LLM reasoning chains from the engine database."""
    try:
        _, context_store = _stores()
        records = context_store.list_reasoning(context_id)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_reasoning(records, json_output, context_store)


@tool_call_app.command("add")
def tool_call_add(
    context_id: str = typer.Option(
        ..., "--context", help="Decision context snapshot ID."
    ),
    tool: str = typer.Option(
        ..., "--tool", help="Tool name (e.g. astock.live.block.rank)."
    ),
    arguments: str = typer.Option(
        ..., "--arguments", help="JSON-encoded call arguments."
    ),
    result: str = typer.Option(
        ..., "--result", help="JSON-encoded call result."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Append one immutable astock tool call record to a decision context."""
    try:
        _, context_store = _stores()
        record = context_store.add_tool_call(
            context_id=context_id,
            tool=tool,
            arguments=arguments,
            result=result,
        )
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_tool_calls((record,), json_output)


@tool_call_app.command("list")
def tool_call_list(
    context_id: str | None = typer.Option(
        None, "--context", help="Optional context ID filter."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """List astock tool call records from the engine database."""
    try:
        _, context_store = _stores()
        records = context_store.list_tool_calls(context_id)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_tool_calls(records, json_output)


def _stores(
    settings: TraderSettings | None = None,
) -> tuple[ReplayStore, ContextStore]:
    resolved = settings or TraderSettings.load()
    database = resolved.data_dir / "trader.db"
    store = ReplayStore(database)
    return store, ContextStore(database)


def _parse_aware_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContextError(f"invalid ISO datetime: {value}") from exc
    if parsed.tzinfo is None:
        raise ContextError("datetime must include a timezone offset")
    return parsed


def _print_evidence(
    evidence: tuple[CatalystEvidence, ...], json_output: bool
) -> None:
    if json_output:
        typer.echo(
            json.dumps(
                [item.model_dump(mode="json") for item in evidence],
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    typer.echo("催化证据")
    typer.echo(f"{'预期':<24} {'立场':<12} {'可靠性':<10} {'观察时间':<25} 摘要")
    for item in evidence:
        typer.echo(
            f"{item.thesis_key:<24} {item.stance:<12} "
            f"{item.reliability:<10} {item.observed_at.isoformat():<25} "
            f"{item.summary}"
        )


def format_context_text(record: DecisionContextRecord) -> str:
    """Render the L0 decision context as plain text (used by LLM providers)."""
    lines: list[str] = []
    context = record.context
    shanghai = context.as_of.astimezone()
    lines.append(f"决策上下文 {shanghai.strftime('%Y-%m-%d %H:%M')} id={record.id[:12]}")
    lines.append(
        f"账户=paper 现金=¥{context.account.cash:,.2f} "
        f"总资产=¥{context.total_assets:,.2f} 持仓={len(context.positions)} "
        f"当日成交={len(context.execution_history)}"
    )

    discovery = context.market_discovery

    # ① 指数 + 市场宽度
    if discovery is not None and discovery.indices:
        lines.append("")
        lines.append("--- ① 指数 ---")
        short_names = {
            "上证指数": "上证", "深证成指": "深证", "科创50": "科创50",
            "创业板指": "创业板", "沪深300": "沪深300", "深证700": "深证700",
            "中证500": "中证500", "中证1000": "中证1000", "上证50": "上证50",
        }
        index_parts = [
            f"{short_names.get(index.name, index.name)}{_fmt_pct(index.change_pct)}"
            for index in discovery.indices
        ]
        limit_note = ""
        if discovery.limit_up_codes:
            limit_note = f" | 封板涨停{len(discovery.limit_up_codes)}只"
        line1 = " ".join(index_parts[:4]) + limit_note
        lines.append(line1)
        if len(index_parts) > 4:
            lines.append("         " + " ".join(index_parts[4:]))

    # ② 持仓（每只价格/涨跌/浮盈）
    lines.append("")
    lines.append(f"--- ② 持仓（{len(context.positions)}）---")
    for item in context.positions:
        pos, quote = item.position, item.quote
        pct = f"{quote.change_pct:+.2f}%" if quote.change_pct is not None else "?"
        pnl = f"{item.pnl_pct:+.2f}%" if item.pnl_pct is not None else "?"
        flag = " ⚠>2%" if quote.change_pct is not None and abs(quote.change_pct) >= 2 else ""
        lines.append(
            f"  {pos.code} {_pad_display(pos.name, 8)} 现价{quote.price:.2f} "
            f"涨跌{pct} 浮盈{pnl} 市值¥{item.market_value:,.0f}{flag}"
        )

    # ③ 强势板块（concept TOP10 + style TOP5 + 涨停方向）
    if discovery is not None and discovery.sector_leaders:
        lines.append("")
        lines.append("--- ③ 强势板块 ---")
        concepts = [s for s in discovery.sector_leaders if s.block_type == "concept"]
        styles = [s for s in discovery.sector_leaders if s.block_type == "style"]
        for sector in concepts[:10]:
            star = "★" if _sector_touches_holdings(sector.name, context) else ""
            lines.append(
                f"  {_pad_display(sector.name, 16)}{_fmt_pct(sector.change_pct)} "
                f"涨停{sector.limit_up_count}{star}"
            )
        if styles:
            lines.append("  style:")
            lines.append(
                "  "
                + " ".join(f"{s.name}{_fmt_pct(s.change_pct)}" for s in styles[:5])
            )
        limit_dirs = sorted(
            (s for s in concepts if s.limit_up_count > 0),
            key=lambda s: s.limit_up_count,
            reverse=True,
        )[:4]
        if limit_dirs:
            lines.append(
                "  涨停方向: "
                + " ".join(f"{s.name}({s.limit_up_count}涨停)" for s in limit_dirs)
            )

    # ④ 主题池（每个持仓预期的健康度 + 成员明细）
    theme_pools = [
        pool for pool in context.pools if pool.pool.key != "current_holdings"
    ]
    if theme_pools:
        lines.append("")
        lines.append("--- ④ 主题池 ---")
        for pool in theme_pools:
            if pool.metrics is None:
                continue
            m = pool.metrics
            lines.append(
                f"{pool.pool.name}: {m.up_count}涨{m.down_count}跌 "
                f"涨停{m.limit_up_count} 广度{m.breadth_pct:.0f}% "
                f"领涨:{','.join(m.leader_codes[:3])}"
            )
            for signal in pool.member_signals:
                star = "★" if signal.is_limit_up else ("▲" if signal.is_strong else "")
                name = _pad_display(signal.name or signal.code, 8)
                amount_yi = float(signal.amount) / 1e8
                lines.append(
                    f"  {signal.code} {name} {_fmt_pct(signal.change_pct)} "
                    f"成交{amount_yi:.1f}亿{star}"
                )

    lines.append("")
    lines.append(
        f"ready_for_judgment={str(context.ready_for_judgment).lower()}"
        + (f" blockers={','.join(context.blockers)}" if context.blockers else "")
    )
    return "\n".join(lines)


def _print_context(record: DecisionContextRecord, json_output: bool) -> None:
    if json_output:
        typer.echo(record.model_dump_json(indent=2))
        return
    typer.echo(format_context_text(record))


def _fmt_pct(value) -> str:
    if value is None:
        return "?"
    return f"{value:+.2f}%"


def _pad_display(text: str, width: int) -> str:
    """Pad a string to a fixed terminal display width (CJK chars count 2)."""
    display = sum(2 if ord(char) > 127 else 1 for char in text)
    return text + " " * max(0, width - display)


def _display_width(text: str) -> int:
    return sum(2 if ord(char) > 127 else 1 for char in text)


def _sector_touches_holdings(
    sector_name: str, context: "DecisionContextRecord"
) -> bool:
    """True if a sector name overlaps one of the thesis titles held."""
    thesis_titles = {thesis.title for thesis in context.theses}
    for title in thesis_titles:
        if title and title in sector_name or sector_name in title:
            return True
    return False


def _print_reasoning(
    records: tuple[ReasoningRecord, ...],
    json_output: bool,
    context_store: ContextStore | None = None,
) -> None:
    if json_output:
        typer.echo(
            json.dumps(
                [item.model_dump(mode="json") for item in records],
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    # 每个上下文快照的节点时间（上海时区），用于按时间轴展示思维链
    from zoneinfo import ZoneInfo

    shanghai = ZoneInfo("Asia/Shanghai")
    as_of_by_context: dict[str, str] = {}
    if context_store is not None:
        for item in records:
            if item.context_id in as_of_by_context:
                continue
            try:
                record = context_store.get_context(item.context_id)
                as_of = record.context.as_of.astimezone(shanghai)
                as_of_by_context[item.context_id] = as_of.strftime("%m-%d %H:%M")
            except StorageError:
                as_of_by_context[item.context_id] = "?" * 11
    typer.echo("LLM推理链")
    typer.echo(
        f"{'时间':<12} {'上下文':<34} {'观察':<24} {'假设':<24} {'验证':<24} 结论"
    )
    for item in records:
        typer.echo(
            f"{as_of_by_context.get(item.context_id, '?' * 11):<12} "
            f"{item.context_id:<34} "
            f"{_truncate(item.observed, 22):<24} "
            f"{_truncate(item.hypothesis, 22):<24} "
            f"{_truncate(item.verified, 22):<24} "
            f"{item.conclusion}"
        )


def _truncate(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: width - 1] + "…"


def _print_tool_calls(
    records: tuple[ToolCallRecord, ...], json_output: bool
) -> None:
    if json_output:
        typer.echo(
            json.dumps(
                [item.model_dump(mode="json") for item in records],
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    typer.echo("工具调用记录")
    typer.echo(
        f"{'上下文':<34} {'工具':<28} {'参数':<24} 结果"
    )
    for item in records:
        typer.echo(
            f"{item.context_id:<34} "
            f"{_truncate(item.tool, 26):<28} "
            f"{_truncate(item.arguments, 22):<24} "
            f"{_truncate(item.result, 60)}"
        )
