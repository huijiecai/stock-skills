"""scan_market 测试:快扫组合工具(指数+持仓+板块+异动,一屏)。

策略:四段结构断言(指数/持仓/板块/异动),数据真实性由各原子工具的测试保证。

docstring 统一格式:<场景>:<验证点>
"""
import textwrap

import pytest

from trader.tools.market import is_trading_hours
from trader.tools.watch import scan_market

TOOL = "scan_market"


def _show(title: str, out: str):
    print(f"  → {title}:")
    print(textwrap.indent(out, "    "))


@pytest.mark.skipif(not is_trading_hours(), reason="live 命令盘中专用,非交易时段跳过")
def test_scan_live():
    """live 快扫:四段齐全(指数/持仓/板块/异动=涨幅榜)。"""
    out = scan_market(None)
    _show("live 快扫", out)
    assert "【指数】" in out
    assert "【持仓】" in out
    assert "【板块 top5】" in out
    assert "【异动 top5 · 涨幅榜】" in out
    assert "上证指数" in out


def test_scan_replay():
    """replay 快扫:8/12 10:30,异动段=涨停清单(带总数)。"""
    out = scan_market(None, mode="replay", date="20260812", time="10:30")
    _show("replay 快扫(8/12 10:30)", out)
    assert "【指数】" in out
    assert "【持仓】" in out
    assert "【板块 top5】" in out
    assert "【异动 top5 · 涨停清单】" in out
    assert "3936.52" in out  # 上证 8/12 10:30 固定值(指数段透传)


@pytest.mark.skipif(not is_trading_hours(), reason="live 命令盘中专用,非交易时段跳过")
def test_scan_position_alert():
    """持仓标警:构造持仓后,±2% 出现 ⚠(用临时库替换默认账户)。"""
    import trader.core.ledger as ledger

    a = ledger.Account(schema="t_scan")
    a.buy("000021", 100, 40.0, on="2026-08-11")
    a.settle("2026-08-12")
    original = ledger._default
    ledger._default = a  # 替换单例(scan 读 ledger.default_account)
    try:
        out = scan_market(None)
        pos_section = out.split("【持仓】")[1].split("【板块")[0]
        print("  → 持仓段:\n" + textwrap.indent(pos_section.strip(), "    "))
        assert "000021" in pos_section
        assert "成本" in pos_section  # 表头
        assert "浮盈" in pos_section
    finally:
        ledger._default = original  # 恢复,避免污染其他测试


def test_scan_degraded_banner(monkeypatch):
    """数据通道降级:板块/异动挂掉时不崩整轮,顶部出⚠警示(8/17 ClickHouse 停机回归)。"""
    import trader.core.scan as scan_mod

    def _boom(*a, **k):
        raise RuntimeError("ping clickhouse: dial tcp 127.0.0.1:9000: connect: connection refused")

    monkeypatch.setattr(scan_mod, "_fetch_block_rank", _boom)
    monkeypatch.setattr(scan_mod, "_fetch_limit_up", _boom)
    out = scan_market(None, mode="replay", date="20260812", time="10:30")
    _show("降级快扫", out)
    assert out.startswith("⚠ 数据通道降级")
    assert "板块排名不可用" in out and "涨停清单不可用" in out
    assert "禁止假装已扫描" in out
    assert "【指数】" in out and "【持仓】" in out  # 其余段照常
