"""get_limit_up 测试:涨停清单(模拟看盘/replay,分钟级封板状态)。

策略:历史数据(replay limit list),值固定 → 锁结构 + 封板状态分布。

docstring 统一格式:<场景>:<验证点>
"""
import textwrap

from trader import market

TOOL = "get_limit_up"

REPLAY_DATE = "20260812"


def _show(label: str, out: str):
    print("  → " + label + ":")
    print(textwrap.indent(out, "    "))


# ── 底层 _fetch_limit_up ───────────────────────────────

def test_limit_up_with_time():
    """带 time:8/12 10:30 涨停清单,含封板状态(sealed/broken/pending)。"""
    data = market._fetch_limit_up(REPLAY_DATE, "10:30")
    _show(f"astock({REPLAY_DATE} 10:30 涨停)", market._format_limit_up(data))
    assert len(data) >= 10
    statuses = {r.get("status") for r in data}
    assert statuses <= {"sealed", "broken", "pending"}
    # 字段完整
    assert "consecutive_days" in data[0]
    assert "concepts" in data[0]
    assert "first_seal_time" in data[0]


def test_limit_up_no_time_close():
    """不带 time:8/12 收盘涨停清单(日线终值,全部 sealed)。"""
    data = market._fetch_limit_up(REPLAY_DATE)
    _show(f"astock({REPLAY_DATE} 收盘涨停)", market._format_limit_up(data[:5]) + ("\n... (共%d只)" % len(data) if len(data) > 5 else ""))
    assert len(data) >= 1


# ── 纯函数 _format_limit_up(不调 astock)───────────────

def test_format_limit_up_pure():
    """_format_limit_up:假数据 → 涨停清单表格。"""
    fake = [{"code": "600721", "name": "百花医药", "consecutive_days": 6, "change_pct": 10.04,
             "status": "sealed", "first_seal_time": "09:25", "replay_amount": 1840794624,
             "concepts": ["免疫治疗", "减肥药", "CXO概念"]}]
    out = market._format_limit_up(fake)
    _show("输出", out)
    assert "百花医药" in out
    assert "sealed" in out
    assert "免疫治疗" in out
