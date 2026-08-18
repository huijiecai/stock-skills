"""昨日数据工具测试:get_market_summary(市场概览)+ get_top_amount(成交额前N)。

历史数据(query,值固定)→ 锁具体值抓回归。

docstring 统一格式:<场景>:<验证点>
"""
import textwrap

from trader.core import market

TOOL = "daily"


def _show(label: str, out: str):
    print("  → " + label + ":")
    print(textwrap.indent(out, "    "))


def test_market_summary_fixed():
    """市场概览:8/12 涨跌家数/涨停数锁定(4124涨/91涨停)。"""
    out = market.get_market_summary(ctx=None, date="20260812")
    _show("8/12 概览", out)
    assert "4124" in out     # 涨家数
    assert "涨停91" in out
    assert "2" in out and "亿" in out  # 成交额


def test_top_amount_fixed():
    """成交额前N:8/12 第一名中际旭创(284亿)。"""
    out = market.get_top_amount(ctx=None, date="20260812", limit=3)
    _show("8/12 成交额前3", out)
    assert "300308" in out
    assert "中际旭创" in out
    assert "284.1亿" in out  # 第一名成交额(8/12 固定值)


def test_format_market_summary_pure():
    """_format_market_summary 纯函数:假数据 → 一行概览。"""
    fake = {"date": "2026-08-12", "up_count": 100, "down_count": 50, "flat_count": 5,
            "limit_up_count": 10, "limit_down_count": 1, "total_amount": 1e11,
            "main_board_amount": 5e10, "growth_board_amount": 3e10, "star_board_amount": 2e10}
    out = market._format_market_summary(fake)
    _show("输出", out)
    assert "涨100/跌50/平5" in out
    assert "涨停10 跌停1" in out
