"""行情工具垫片(C1):实现已拆去 trader.core.market,旧路径保留 re-export。

调用方(tools/account、tools/trading、tools/watch、runner、tests)无需改动。
"""

from trader.core.market import (
    ASTOCK,
    INDICES,
    INDICES_NAME,
    _astock,
    _fetch_block_members,
    _fetch_block_rank,
    _fetch_candidates,
    _fetch_indices,
    _fetch_kline,
    _fetch_limit_up,
    _fetch_market_summary,
    _fetch_quotes,
    _fetch_top_amount,
    _fmt_amount,
    _format_block_rank,
    _format_candidates,
    _format_indices,
    _format_kline,
    _format_limit_up,
    _format_market_summary,
    _format_quotes,
    _format_top_amount,
    _tool_error_text,
    get_block_members,
    get_block_rank,
    get_candidates,
    get_indices,
    get_kline,
    get_limit_up,
    get_market_summary,
    get_quotes,
    get_top_amount,
    is_trading_hours,
)

__all__ = [n for n in dir() if not n.startswith("__")]
