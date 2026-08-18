"""core·能力注册表:manifest 里的工具名 → 可调用实现(实现设计 §3)。

代码=能力,PG=管理;engine 按名字解析。写操作类工具给 retries=3(LLM 传参偶发错可自愈)。
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
)

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
