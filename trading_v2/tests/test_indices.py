"""get_indices 测试:真实调 astock 查主流指数。

策略:
- live:值每天变 → 断言结构(数量/字段/顺序)
- replay:历史固定 → 锁具体值(抓回归,astock 数据改了会触发)

docstring 统一格式:<场景>:<验证点>
"""
from trader import market

TOOL = "get_indices"  # 本文件测试的工具(-s 输出 [工具名] 标签)

# 已 prepare 的历史回放日(数据固定)
REPLAY_DATE = "20260812"


# ── 底层 _fetch_indices ────────────────────────────────

def test_fetch_indices_live_structure():
    """live 模式:返回 5 个主流指数,字段完整、顺序=INDICES。"""
    data = market._fetch_indices("live")
    print("  → astock(live): " + market._format_indices(data))
    assert [d["code"] for d in data] == market.INDICES
    for d in data:
        assert set(d) == {"code", "name", "price", "pre_close", "change_pct", "amount"}
        assert d["price"] > 0
        assert isinstance(d["change_pct"], float)
        assert d["name"]


def test_fetch_indices_replay_with_time_fixed():
    """replay 带时间:8/12 10:30 历史值固定(锁回归)。"""
    data = market._fetch_indices("replay", REPLAY_DATE, "10:30")
    print("  → astock(8/12 10:30): " + market._format_indices(data))
    assert [d["code"] for d in data] == market.INDICES
    sh = next(d for d in data if d["code"] == "000001")
    assert sh["name"] == "上证指数"
    assert abs(sh["price"] - 3936.52) < 0.01


def test_fetch_indices_replay_no_time_is_close():
    """replay 不带时间:返回回放日(date)的收盘价。"""
    data = market._fetch_indices("replay", REPLAY_DATE)
    print("  → astock(8/12 收盘): " + market._format_indices(data))
    assert len(data) == 5
    sh = next(d for d in data if d["code"] == "000001")
    assert abs(sh["price"] - 3946.68) < 0.01


def test_fetch_indices_replay_filters_extra():
    """replay 归一化:过滤多余指数(深证700/中证500),只留 INDICES 5 个。"""
    data = market._fetch_indices("replay", REPLAY_DATE, "10:30")
    codes = [d["code"] for d in data]
    print("  → 归一化后 codes: " + ", ".join(codes))
    assert "399005" not in codes
    assert "399905" not in codes


# ── 纯函数 _format_indices(不调 astock)────────────────

def test_format_indices_pure():
    """_format_indices 纯函数:假数据 → '名字+价+涨跌%' 格式字符串。"""
    fake = [
        {"code": "000001", "name": "上证指数", "price": 3926.96, "change_pct": -0.5, "amount": 100},
    ]
    out = market._format_indices(fake)
    print("  → 输出: " + out)
    assert "上证指数" in out
    assert "3926.96" in out
    assert "-0.50%" in out


# ── 工具层 get_indices(参数 → 底层 → 格式化)──────────

def test_get_indices_tool_replay():
    """replay 传参:验证 参数→底层→格式化 完整链路。"""
    out = market.get_indices(ctx=None, mode="replay", date=REPLAY_DATE, time="10:30")
    print("  → astock(8/12 10:30): " + out)
    assert "3936.52" in out
