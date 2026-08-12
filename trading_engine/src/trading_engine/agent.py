"""Watch agent runtime: a ZCode-style autonomous agent loop for trading.

The agent carries session memory across the whole trading day:
- Open: load session context once (positions + thesis details + rules)
- Each heartbeat: feed the lightweight scan as an observation
- LLM (with full conversation history) decides: probe deeper, trade, or wait
- Tools (probe_pool / probe_stock / trade) are executed by the runtime,
  results flow back into the conversation as tool_result messages

This replaces the stateless ``analyze`` path for live/replay watching.
DeepSeek's Anthropic-compatible API with ``tools`` + ``thinking disabled``
powers the brain; the runtime owns the loop, memory, and side effects.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.settings import ModelSettings

from trading_engine.astock import AstockClient
from trading_engine.config import TraderSettings
from trading_engine.context import DecisionContextBuilder, extract_context_quotes
from trading_engine.context_store import ContextStore
from trading_engine.models import (
    JudgmentContext,
    JudgmentProposal,
    JudgmentReport,
    LiveQuote,
)
from trading_engine.paper import PaperBroker
from trading_engine.paper_store import PaperStore
from trading_engine.replay import ReplayMarketData, parse_clock_time, replay_time
from trading_engine.storage import ReplayStore

# Heartbeat timestamps: morning + afternoon sessions, every 5 minutes
HEARTBEAT_TIMES = [
    "09:31", "09:36", "09:41", "09:46", "09:51", "09:56",
    "10:01", "10:06", "10:11", "10:16", "10:21", "10:26", "10:31",
    "10:36", "10:41", "10:46", "10:51", "10:56",
    "11:01", "11:06", "11:11", "11:16", "11:21", "11:26",
    "13:01", "13:06", "13:11", "13:16", "13:21", "13:26", "13:31",
    "13:36", "13:41", "13:46", "13:51", "13:56",
    "14:01", "14:06", "14:11", "14:16", "14:21", "14:26", "14:31",
    "14:36", "14:41", "14:46", "14:51", "14:56",
]


@dataclass
class TradingDeps:
    """Dependencies injected into every agent tool call for one heartbeat.

    ``at`` and ``quote_by_code`` are refreshed each heartbeat by the runtime;
    tools that need a snapshot read it through ``_snapshot_at``.
    """
    store: ReplayStore
    context_store: ContextStore
    paper_store: PaperStore
    builder: DecisionContextBuilder
    settings: TraderSettings
    client: AstockClient
    account: str
    trading_date: date
    at: datetime


@dataclass
class WatchSession:
    """In-memory session state accumulated across the trading day."""
    trading_date: date
    account: str
    system_prompt: str = ""
    messages: list = field(default_factory=list)  # PydanticAI ModelMessage list
    heartbeats_seen: int = 0


def build_agent(
    system_prompt: str,
    register_strategy_tools,
    api_key: str | None = None,
    base_url: str | None = None,
) -> Agent[TradingDeps, str]:
    """Create the PydanticAI agent wired to DeepSeek (Anthropic-compatible).

    ``system_prompt`` and ``register_strategy_tools`` come from the loaded
    strategy package — the engine itself is strategy-agnostic. After the
    strategy registers its own tools (get_heartbeat / probe_pool / ...), the
    engine registers the two universal tools every strategy needs:
    ``probe_stock`` and ``trade`` (trade carries the market guardrails).
    """
    model = AnthropicModel(
        os.environ.get("TRADER_LLM_MODEL", "") or "deepseek-v4-flash",
        provider=AnthropicProvider(
            api_key=api_key or os.environ.get("TRADER_LLM_API_KEY", ""),
            base_url=(base_url or os.environ.get("TRADER_LLM_BASE_URL", "")
                      or "https://api.deepseek.com/anthropic"),
        ),
    )
    agent: Agent[TradingDeps, str] = Agent(
        model,
        system_prompt=system_prompt,
        output_type=str,
        model_settings=ModelSettings(
            {"anthropic_thinking": {"type": "disabled"}},
            max_tokens=1500,
        ),
    )

    # Strategy-specific tools (get_heartbeat, probe_pool, ...) — strategy knows
    # its own concepts (pools, theses); the engine does not.
    register_strategy_tools(agent)

    # Universal tools — every strategy needs to inspect a stock and to trade.
    @agent.tool
    def probe_stock(ctx: RunContext[TradingDeps], code: str) -> str:
        """查看某只股票的分钟路径(开高低现/反弹/回撤/破前收)。用于判断个股价格响应。"""
        d = ctx.deps
        codes = d.builder.required_live_codes(d.account, d.trading_date)
        if code not in codes:
            codes = tuple(sorted(set(codes) | {code}))
        provider = ReplayMarketData(d.client, d.trading_date, codes, include_discovery=True)
        quotes = extract_context_quotes(provider.snapshot(d.at))
        from trading_engine.watch import format_probe_code
        q = next((x for x in quotes if x.code == code), None)
        return f"{code}: 该时刻无报价" if q is None else format_probe_code(code, q)

    @agent.tool
    def trade(
        ctx: RunContext[TradingDeps],
        action: str,
        code: str,
        quantity: int,
        reason: str,
    ) -> str:
        """下单交易。仅在你完成深析、确定动作后调用。会被T+1/主板/整手/风险预算规则校验。"""
        d = ctx.deps
        return _do_trade(
            d.builder, d.store, d.settings, d.client, d.account, d.trading_date, d.at,
            d.context_store, d.paper_store,
            action=action, code=code, quantity=quantity, reason=reason,
        )

    return agent


def run_watch_session(
    trading_date: date,
    system_prompt: str,
    register_strategy_tools,
    account: str = "paper",
    api_key: str | None = None,
    base_url: str | None = None,
    times: list[str] | None = None,
    max_rounds: int | None = None,
    on_event: Any = None,
) -> WatchSession:
    """Run a full trading-day agent session. Returns the session record.

    ``system_prompt`` and ``register_strategy_tools`` come from the loaded
    strategy package — the engine stays strategy-agnostic. The agent itself
    decides each round whether to call ``get_heartbeat`` / ``probe_*`` / ``trade``;
    the runtime only advances the clock and carries conversation memory.

    ``on_event`` is an optional callback ``fn(str)`` for streaming progress.
    """
    settings = TraderSettings.load()
    database = settings.data_dir / "trader.db"
    store = ReplayStore(database)
    context_store = ContextStore(database)
    paper_store = PaperStore(database)
    builder = DecisionContextBuilder(store, context_store)

    session = WatchSession(trading_date=trading_date, account=account)
    if on_event:
        on_event(f"[开盘] {trading_date.isoformat()} 会话启动\n")

    heartbeat_times = times or HEARTBEAT_TIMES
    if max_rounds:
        heartbeat_times = heartbeat_times[:max_rounds]

    client = AstockClient(settings.astock_binary, timeout_seconds=60)
    agent = build_agent(
        system_prompt=system_prompt,
        register_strategy_tools=register_strategy_tools,
        api_key=api_key,
        base_url=base_url,
    )

    deps = TradingDeps(
        store=store, context_store=context_store, paper_store=paper_store,
        builder=builder, settings=settings, client=client,
        account=account, trading_date=trading_date, at=trading_date,
    )

    for index, hhmm in enumerate(heartbeat_times):
        clock = replay_time(trading_date, parse_clock_time(hhmm))
        deps.at = clock  # tools read the current heartbeat timestamp from here
        session.heartbeats_seen += 1
        if index == 0:
            # First round = open: load session context AND look at the market.
            prompt = (
                f"【开盘 {hhmm}】新交易日开始。请先调用 get_open_context 加载持仓+预期+池+预案,"
                f"再调用 get_heartbeat 查看开盘市场,然后开始判断。"
            )
        else:
            prompt = f"【新的一轮 {hhmm}】请调用 get_heartbeat 查看市场,然后判断。"
        prev_len = len(session.messages)
        result = agent.run_sync(
            prompt,
            deps=deps,
            message_history=session.messages,
        )
        session.messages = result.all_messages()
        # Tools called this round = the new messages added by this run
        new_messages = result.all_messages()[prev_len:]
        tools = _summarize_tool_calls(new_messages)
        conclusion = result.output.strip()[:300] if result.output else "(无结论)"
        label = "[开盘]" if index == 0 else f"[{hhmm}]"
        if on_event:
            tool_line = f"  🔧 {tools}\n" if tools else ""
            on_event(f"{label}\n{tool_line}{conclusion}\n")

    # Close summary
    if on_event:
        on_event(_close_summary(session, store, account))
    return session



def _do_trade(
    builder, store, settings, client, account, trading_date, at,
    context_store, paper_store,
    action: str, code: str, quantity: int, reason: str,
) -> str:
    """Execute a trade by building a fresh context + judgment at the current clock."""
    # 1. build a fresh decision context at the current clock
    codes = builder.required_live_codes(account, trading_date)
    provider = ReplayMarketData(client, trading_date, codes, include_discovery=True)
    snapshot = provider.snapshot(at)
    record = builder.build(snapshot, account)

    # 2. construct a one-proposal judgment (action/code/quantity)
    quotes = extract_context_quotes(snapshot)
    input_context = JudgmentContext(
        snapshot_id=record.context.market_snapshot_id,
        as_of=record.context.as_of,
        source=snapshot.source,
        quotes=tuple(
            LiveQuote(
                code=q.code, price=float(q.price), pre_close=float(q.pre_close),
                change_pct=float(q.change_pct), volume=q.volume, amount=float(q.amount),
                open=float(q.open), high=float(q.high), low=float(q.low),
            ) for q in quotes
        ),
        decision_context_id=record.id,
        decision_context_fingerprint=record.fingerprint,
        domain_context=record.context.model_dump(mode="json"),
        policy="watch-agent-v1",
    )
    # normalize action: non-BUY/SELL or invalid quantity -> degrade
    norm_action = action.upper() if action.upper() in {"BUY", "SELL"} else "WAIT"
    if norm_action == "WAIT" or quantity <= 0:
        return f"未执行: 动作无效或数量<=0 (action={action} qty={quantity})"
    proposal = JudgmentProposal(
        code=code, action=norm_action, quantity=quantity,
        confidence=0.7, reason=reason, evidence=("watch-agent",),
    )
    report = JudgmentReport(
        snapshot_id=input_context.snapshot_id,
        as_of=record.context.as_of,
        provider="watch-agent",
        model="deepseek-v4-flash",
        proposals=(proposal,),
        limitations=("watch-agent inline judgment",),
    )
    judgment = store.record_judgment(
        input_context.snapshot_id, input_context, report,
        "watch-agent", "deepseek-v4-flash", 1,
    )

    # 3. execute through PaperBroker (rule checks apply)
    broker = PaperBroker(store, context_store, paper_store)
    try:
        result = broker.execute_judgment(account, judgment.id)
    except Exception as exc:
        return f"执行失败: {exc}"

    # summarize fills/rejections
    filled = [f for f in result.events if f.status == "filled"]
    rejected = [f for f in result.events if f.status == "rejected"]
    parts = []
    for f in filled:
        parts.append(f"✓成交 {f.code} {f.action} {getattr(f, 'quantity', '?')}")
    for f in rejected:
        parts.append(f"✗拒 {f.code} {f.action}: {f.reason[:60]}")
    return "交易结果: " + " | ".join(parts) if parts else "交易结果: 无事件"


def _close_summary(session: WatchSession, store: ReplayStore, account: str) -> str:
    account_state = store.get_account(account)
    positions = store.list_positions(account)
    lines = [
        f"\n=== 收盘总结 ===",
        f"心跳轮数: {session.heartbeats_seen}",
        f"现金: ¥{account_state.cash:,.2f}",
        f"持仓: {len(positions)} 只",
    ]
    for p in positions:
        lines.append(f"  {p.code} {p.name} {p.quantity}股(可卖{p.sellable_quantity}) @{p.average_cost:.2f}")
    return "\n".join(lines)


def _summarize_tool_calls(messages: list) -> str:
    """Extract a one-line summary of tool calls from PydanticAI messages.

    Returns e.g. ``"get_heartbeat | probe_pool(创新药) | trade(SELL,603127,200)"``.
    Empty string if no tools were called.
    """
    parts: list[str] = []
    for msg in messages:
        for part in getattr(msg, "parts", []):
            if isinstance(part, ToolCallPart):
                args = part.args
                if isinstance(args, dict) and args:
                    arg_str = ",".join(str(v) for v in args.values())
                    parts.append(f"{part.tool_name}({arg_str})")
                else:
                    parts.append(part.tool_name)
    return " | ".join(parts)


def _fmt(value) -> str:
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
