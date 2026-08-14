"""get_candidates 测试:全市场异动候选(live market 涨幅/成交额/涨速榜)。

策略:实时数据(live market),值每天变 → 断言结构 + 排序/过滤行为。

docstring 统一格式:<场景>:<验证点>
"""
import textwrap

from trader.tools import market

TOOL = "get_candidates"


def _show(label: str, out: str):
    print("  → " + label + ":")
    print(textwrap.indent(out, "    "))


# ── 底层 _fetch_candidates ─────────────────────────────

def test_candidates_default():
    """默认涨幅榜:返回 top 个股,字段完整(涨跌/振幅/涨速/成交额/状态)。"""
    data = market._fetch_candidates(limit=5)
    _show("astock(live 涨幅榜)", market._format_candidates(data))
    assert len(data) >= 1
    assert "change_pct" in data[0]
    assert "state" in data[0]
    assert "amount" in data[0]


def test_candidates_state_limit_up():
    """state=limit-up:只返回涨停股(state=limit_up)。"""
    data = market._fetch_candidates(state="limit-up", limit=5)
    _show("astock(live 涨停)", market._format_candidates(data))
    assert len(data) >= 1
    assert all(c.get("state") == "limit_up" for c in data)


def test_candidates_sort_amount():
    """sort=amount:按成交额排序(放量股,非涨幅)。"""
    data = market._fetch_candidates(sort="amount", limit=5)
    _show("astock(live 成交额榜)", market._format_candidates(data))
    assert len(data) >= 1
    amounts = [c.get("amount", 0) for c in data]
    assert amounts == sorted(amounts, reverse=True)  # 降序


# ── 纯函数 _format_candidates(不调 astock)─────────────

def test_format_candidates_pure():
    """_format_candidates:假数据 → 异动候选表格。"""
    fake = [{"code": "300404", "name": "博济医药", "change_pct": 20.02, "amplitude_pct": 21.5,
             "rise_speed": 5.2, "amount": 820000000, "state": "limit_up"}]
    out = market._format_candidates(fake)
    _show("输出", out)
    assert "博济医药" in out
    assert "%" in out
    assert "limit_up" in out
