"""板块工具测试:get_block_rank(板块排名)+ get_block_members(成分股)。

策略:
- live:值每天变 → 断言结构(字段、数量)
- replay:历史固定 → 锁结构

docstring 统一格式:<场景>:<验证点>
"""
import textwrap

import pytest

from trader.tools.market import is_trading_hours
from trader.tools import market

TOOL = "block"


def _show(label: str, out: str):
    """打印工具输出:标签一行,多行内容缩进 4 空格。"""
    print("  → " + label + ":")
    print(textwrap.indent(out, "    "))


# ── get_block_rank ─────────────────────────────────────

@pytest.mark.skipif(not is_trading_hours(), reason="live 命令盘中专用,非交易时段跳过")
def test_block_rank_live():
    """get_block_rank live:返回多板块,字段完整(涨跌/涨停/涨跌家数)。"""
    data = market._fetch_block_rank("live", limit=3)
    _show("astock(live 板块排名)", market._format_block_rank(data))
    assert len(data) >= 1
    assert "change_pct" in data[0]
    assert "limit_up_count" in data[0]
    assert "up_count" in data[0]


def test_block_rank_replay():
    """get_block_rank replay:8/12 10:30 历史板块排名(分钟级)。"""
    data = market._fetch_block_rank("replay", date="20260812", time="10:30", limit=3)
    _show("astock(8/12 10:30 板块排名)", market._format_block_rank(data))
    assert len(data) >= 1
    assert "change_pct" in data[0]


@pytest.mark.skipif(not is_trading_hours(), reason="live 命令盘中专用,非交易时段跳过")
def test_block_rank_filter_type():
    """get_block_rank 过滤:block_type=concept 只返回概念板块。"""
    data = market._fetch_block_rank("live", block_type="concept", limit=5)
    _show("astock(live 概念板块)", market._format_block_rank(data))
    types = {b.get("block_type") for b in data}
    assert types <= {"concept"}  # 过滤后只剩 concept


# ── get_block_members ──────────────────────────────────

@pytest.mark.skipif(not is_trading_hours(), reason="live 命令盘中专用,非交易时段跳过")
def test_block_members_live():
    """get_block_members live:880812 成分股,字段同 quotes。"""
    data = market._fetch_block_members("live", "880812", limit=3)
    _show("astock(live 880812 成分股)", market._format_quotes(data))
    assert len(data) >= 1
    assert "code" in data[0]
    assert "price" in data[0]


# ── 纯函数 _format_block_rank(不调 astock)────────────

def test_format_block_rank_pure():
    """_format_block_rank:假数据 → 板块排名表格(去现价/昨收,留涨跌/成交额/涨停/涨跌平/中位)。"""
    fake = [{"name": "昨日连板", "block_type": "style", "change_pct": 7.23, "amount": 17928169472,
             "limit_up_count": 1, "up_count": 13, "down_count": 60, "flat_count": 1,
             "median_change_pct": -2.28}]
    out = market._format_block_rank(fake)
    _show("输出", out)
    assert "昨日连板" in out
    assert "style" in out
    assert "13/60/1" in out  # 涨/跌/平
    assert "%" in out
