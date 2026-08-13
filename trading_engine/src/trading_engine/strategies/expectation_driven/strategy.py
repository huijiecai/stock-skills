"""Expectation-driven intraday strategy: prompt + tool registration.

This is the trading-system layer. The engine (``trading_engine.engine.agent``) calls
``register_tools(agent)`` to attach this strategy's tools; it never imports
this module directly. ``SYSTEM_PROMPT`` is passed into ``build_agent`` as a
plain string.

Tools registered here are *strategy-specific*:
- ``get_open_context``: load session state (positions + theses + pools + plans)
- ``get_heartbeat``: per-round market scan (indices + positions + pool X/Y + limit-up detail)
- ``probe_pool``: deep-dive a pool's member detail

Universal tools (``probe_stock``, ``trade``) are registered by the engine.
"""

from __future__ import annotations

from pydantic_ai import Agent, RunContext

from trading_engine.engine.watch import format_open

from pathlib import Path

# The prompt lives in prompt.md (not hardcoded) so you can edit the
# trading-system rules without touching Python code.
_PROMPT_FILE = Path(__file__).parent / "prompt.md"
SYSTEM_PROMPT = _PROMPT_FILE.read_text(encoding="utf-8").strip()




def register_tools(agent: Agent) -> None:
    """Register expectation-driven strategy tools onto a PydanticAI agent.

    Called by the engine's ``build_agent`` after creating the agent; the engine
    then registers its own universal tools (probe_stock, trade). This function
    only adds the three strategy-specific tools.
    """

    def _snapshot(deps):
        """Build a market snapshot: Live (TDX real-time) or Replay (historical)."""
        from trading_engine.market.context import extract_context_quotes
        codes = deps.builder.required_live_codes(deps.account, deps.trading_date)
        if getattr(deps, "live", False):
            from trading_engine.market.live import LiveMarketData
            provider = LiveMarketData(deps.client, codes, include_discovery=True)
        else:
            from trading_engine.market.replay import ReplayMarketData
            provider = ReplayMarketData(
                deps.client, deps.trading_date, codes, include_discovery=True
            )
        return provider.snapshot(deps.at)

    @agent.tool
    def get_open_context(ctx: RunContext) -> str:
        """加载开盘会话上下文:持仓+预期(兑现/失效条件)+主题池+盘前预案+规则。开盘时调一次,整天对照。"""
        from trading_engine.engine.watch import format_open as _format_open
        d = ctx.deps
        return _format_open(d.store, d.account)

    @agent.tool
    def get_heartbeat(ctx: RunContext) -> str:
        """获取当轮市场快照(指数+持仓+池健康度X/Y+涨停明细)。每轮首先调用看盘。"""
        from trading_engine.engine.watch import format_heartbeat
        d = ctx.deps
        return format_heartbeat(
            d.builder, d.store, d.settings, d.account, d.trading_date, d.at,
            live=getattr(d, "live", False),
        )

    @agent.tool
    def probe_pool(ctx: RunContext, pool_key: str) -> str:
        """查看某主题池全部成员明细(谁领涨/谁掉队/成交额)。用于持仓触发§4.1或池突变时深析。"""
        from trading_engine.engine.watch import format_probe_pool
        from trading_engine.market.context import extract_context_quotes
        d = ctx.deps
        snapshot = _snapshot(d)
        quotes = extract_context_quotes(snapshot)
        return format_probe_pool(d.store, pool_key, {q.code: q for q in quotes})
