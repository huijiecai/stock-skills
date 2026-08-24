"""core·能力注册表:工具实现和用户可见能力的统一目录。

代码=能力实现,manifest=系统级安全策略。阶段不再配置工具白名单；
模型始终可以按 Prompt 需要读取领域数据，写操作由系统策略控制。
"""
from trader.core import market as _market
from trader.core.scan import scan_market
from trader.core.watchlist import (
    get_watchlist,
    get_watchlist_quotes,
    remove_watchlist_member,
    save_watchlist,
)
from trader.tools.account import get_account, get_positions, get_trades
from trader.tools.docs import get_doc, list_docs, save_doc, set_doc_meta
from trader.tools.trading import execute

_MARKET_TOOLS = (
    "get_quotes", "get_indices", "get_kline", "get_block_rank", "get_block_members",
    "get_candidates", "get_limit_up", "get_market_summary", "get_top_amount",
    "get_us_market",
)

# 工具分组(目录展示用;与 tools/__main__.py CLI 分组语义一致)
TOOL_GROUPS: dict[str, list[str]] = {
    "market": list(_MARKET_TOOLS),
    "scan": ["scan_market"],
    "account": ["get_positions", "get_account", "get_trades"],
    "trading": ["execute"],
    "docs": ["save_doc", "get_doc", "list_docs", "set_doc_meta"],
    "watchlist": ["save_watchlist", "get_watchlist", "get_watchlist_quotes",
                  "remove_watchlist_member"],
}

TOOLS: dict = {n: getattr(_market, n) for n in _MARKET_TOOLS}
TOOLS.update({
    "get_positions": get_positions,
    "get_account": get_account,
    "get_trades": get_trades,
    "execute": execute,
    "scan_market": scan_market,
    "save_doc": save_doc,
    "get_doc": get_doc,
    "list_docs": list_docs,
    "set_doc_meta": set_doc_meta,
    "save_watchlist": save_watchlist,
    "get_watchlist": get_watchlist,
    "get_watchlist_quotes": get_watchlist_quotes,
    "remove_watchlist_member": remove_watchlist_member,
})

# 写操作类:LLM 传参偶发错重试可自愈(对齐老 agent.py 的注册习惯)
WRITE_TOOLS = {"execute", "save_doc", "set_doc_meta", "save_watchlist",
               "remove_watchlist_member"}

DEFAULT_POLICY = {
    "web_search": False,
    "resource_write": False,
    "simulation_trading": True,
    "live_trading": False,
}

USER_VISIBLE_GROUPS = {"market", "scan", "account", "trading", "watchlist"}
USER_VISIBLE_TOOLS = tuple(
    name for group, names in TOOL_GROUPS.items() if group in USER_VISIBLE_GROUPS
    for name in names
)


def capability_tools(manifest: dict, stage_name: str | None = None,
                     execution_mode: str | None = None) -> tuple[str, ...]:
    """Return tools available under system policy and the run clock mode."""
    policy = {**DEFAULT_POLICY, **(manifest.get("policy") or {})}
    names = list(USER_VISIBLE_TOOLS)
    if not policy["resource_write"]:
        names = [n for n in names if n not in {"save_watchlist", "remove_watchlist_member"}]
    trading_allowed = (
        policy["simulation_trading"] if execution_mode in {"paper", "replay"}
        else policy["live_trading"] if execution_mode == "real"
        else policy["simulation_trading"] or policy["live_trading"]
    )
    if not trading_allowed:
        names = [n for n in names if n != "execute"]
    return tuple(dict.fromkeys(names))


def capability_enabled(manifest: dict, stage_name: str | None, capability: str) -> bool:
    """Whether a platform policy allows a capability."""
    policy = {**DEFAULT_POLICY, **(manifest.get("policy") or {})}
    if capability == "research.web_search":
        return bool(policy["web_search"])
    if capability == "resources.write":
        return bool(policy["resource_write"])
    if capability == "trading.virtual_execute":
        return bool(policy["simulation_trading"])
    return True
