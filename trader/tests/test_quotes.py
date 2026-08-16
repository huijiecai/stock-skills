"""get_quotes 测试:真实调 astock 查多股报价(单股传 ["xxx"])。

docstring 统一格式:<场景>:<验证点>
"""
import textwrap

import pytest

from trader.tools.market import is_trading_hours
from trader.tools import market

TOOL = "get_quotes"
REPLAY_DATE = "20260812"


def _show(label: str, out: str):
    """打印工具输出:标签一行,多行表格缩进 4 空格。"""
    print("  → " + label + ":")
    print(textwrap.indent(out, "    "))


@pytest.mark.skipif(not is_trading_hours(), reason="live 命令盘中专用,非交易时段跳过")
def test_get_quotes_live_multi():
    """live 多股:全字段表格(代码/名称/现价/昨收/涨跌/成交额)。"""
    out = market.get_quotes(ctx=None, codes=["000021", "000636"])
    _show("astock(live 多股)", out)
    assert "深科技" in out
    assert "风华高科" in out


def test_get_quotes_replay_multi():
    """replay 多股:历史值固定,验证逗号分隔传参与归一化。"""
    out = market.get_quotes(ctx=None, codes=["000021", "000636"], mode="replay", date=REPLAY_DATE, time="10:30")
    _show("astock(8/12 10:30 多股)", out)
    assert "深科技" in out
    assert "40.22" in out  # 000021 8/12 10:30 固定值
