"""看盘组合工具垫片:scan_market 实现在 core.scan(平台通用件,自选组快览版)。

老 get_pool_health 已由通用 get_watchlist_quotes 替代(C3 预期系统数据化)。
"""
from trader.core.scan import scan_market

__all__ = ["scan_market"]
