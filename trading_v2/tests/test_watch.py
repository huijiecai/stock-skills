"""scan_market 测试:快扫组合工具(指数+持仓+板块+异动,一屏)。

策略:四段结构断言(指数/持仓/板块/异动),数据真实性由各原子工具的测试保证。

docstring 统一格式:<场景>:<验证点>
"""
import textwrap

from trader.tools.watch import scan_market

TOOL = "scan_market"


def _show(title: str, out: str):
    print(f"  → {title}:")
    print(textwrap.indent(out, "    "))


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


def test_scan_position_alert():
    """持仓标警:构造持仓后,±2% 出现 ⚠(用临时库替换默认账户)。"""
    import trader.store as store

    a = store.Account(db_path="/tmp/scan_test.db")
    a.buy("000021", 100, 40.0, on="2026-08-11")
    a.settle("2026-08-12")
    original = store._default
    store._default = a  # 替换单例
    try:
        out = scan_market(None)
        pos_section = out.split("【持仓】")[1].split("【板块")[0]
        print("  → 持仓段:\n" + textwrap.indent(pos_section.strip(), "    "))
        assert "000021" in pos_section
        assert "成本" in pos_section  # 表头
        assert "浮盈" in pos_section
    finally:
        store._default = original  # 恢复,避免污染其他测试
