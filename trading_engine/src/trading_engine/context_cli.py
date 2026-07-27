from __future__ import annotations

import json
from datetime import datetime

import typer

from trading_engine.astock import AstockClient
from trading_engine.config import TraderSettings
from trading_engine.context import DecisionContextBuilder
from trading_engine.context_models import CatalystEvidence, DecisionContextRecord
from trading_engine.context_store import ContextStore
from trading_engine.errors import ContextError, TradingEngineError
from trading_engine.live import LiveMarketData
from trading_engine.replay import ReplayMarketData, SHANGHAI_TZ, parse_clock_time
from trading_engine.storage import ReplayStore


context_app = typer.Typer(help="Build auditable decision context snapshots.")
evidence_app = typer.Typer(help="Manage timestamped catalyst evidence.")


@evidence_app.command("add")
def evidence_add(
    thesis_key: str = typer.Option(..., "--thesis", help="Existing thesis key."),
    kind: str = typer.Option(
        ..., "--kind", help="announcement, news, industry, market, or other."
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
        "default", "--account", help="Account name."
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
            AstockClient(settings.astock_binary), codes
        ).snapshot()
        market_record = store.record_market_snapshot(snapshot)
        record = builder.build(market_record, account_name)
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_context(record, json_output)


@context_app.command("build")
def context_build(
    account_name: str = typer.Option(
        "default", "--account", help="Account name."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Build context from the latest persisted market snapshot."""
    try:
        store, context_store = _stores()
        market_record = store.latest_market_snapshot()
        if market_record is None:
            raise ContextError("no persisted market snapshot exists")
        record = DecisionContextBuilder(store, context_store).build(
            market_record, account_name
        )
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_context(record, json_output)


@context_app.command("replay")
def context_replay(
    replay_date: str = typer.Option(
        ..., "--date", help="Trading date in YYYYMMDD format."
    ),
    until: str = typer.Option(..., "--until", help="Replay time in HH:MM format."),
    account_name: str = typer.Option(
        "default", "--account", help="Account name."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Build the same context contract from a deterministic replay snapshot."""
    try:
        settings = TraderSettings.load()
        store, context_store = _stores(settings)
        builder = DecisionContextBuilder(store, context_store)
        codes = builder.required_live_codes(account_name)
        trading_date = datetime.strptime(replay_date, "%Y%m%d").date()
        replay_time = parse_clock_time(until)
        at = datetime.combine(trading_date, replay_time, tzinfo=SHANGHAI_TZ)
        snapshot = ReplayMarketData(
            AstockClient(settings.astock_binary), trading_date, codes
        ).snapshot(at)
        market_record = store.record_market_snapshot(snapshot)
        record = builder.build(market_record, account_name)
    except ValueError as exc:
        typer.echo("date must use YYYYMMDD format", err=True)
        raise typer.Exit(code=1) from exc
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_context(record, json_output)


@context_app.command("show")
def context_show(
    account_name: str = typer.Option(
        "default", "--account", help="Account name."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Show the latest persisted context without rebuilding it."""
    try:
        _, context_store = _stores()
        record = context_store.latest_context(account_name)
        if record is None:
            raise ContextError("no decision context exists for this account")
    except TradingEngineError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    _print_context(record, json_output)


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


def _print_context(record: DecisionContextRecord, json_output: bool) -> None:
    if json_output:
        typer.echo(record.model_dump_json(indent=2))
        return
    context = record.context
    typer.echo(
        f"决策上下文 {context.as_of.isoformat()} id={record.id} "
        f"market={context.market_snapshot_id}"
    )
    typer.echo(
        f"账户={context.account.name} 总资产=¥{context.total_assets:,.2f} "
        f"持仓={len(context.positions)} 预期={len(context.theses)} "
        f"固定池={len(context.pools)} 证据={len(context.evidence)}"
    )
    typer.echo(
        f"ready_for_judgment={str(context.ready_for_judgment).lower()} "
        f"excluded_future_evidence={context.excluded_future_evidence_count}"
    )
    for blocker in context.blockers:
        typer.echo(f"- BLOCKER {blocker}")
