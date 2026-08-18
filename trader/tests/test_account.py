"""Account 测试:模拟账户(SQLite,tmp 库,不碰真实数据)。

覆盖:初始化 / 买入(T+1锁/加权成本) / 卖出(可卖校验) / settle 解锁 / 现金不足。

docstring 统一格式:<场景>:<验证点>
"""
import pytest

from trader.store import Account, AccountError

TOOL = "account"


def _acct(request, initial=100_000_00):
    """每个测试独立 schema(t_<测试名>),互不污染。"""
    return Account(schema=f"t_{request.node.name[:40]}", initial_cash=initial)


# ── 初始化 ─────────────────────────────────────────────

def test_init_cash(request):
    """初始化:现金=初始资金,持仓为空。"""
    a = _acct(request)
    print(f"  → 现金 ¥{a.cash() / 100:,.2f},持仓 {a.positions()}")
    assert a.cash() == 100_000_00
    assert a.positions() == []


# ── 买入 ───────────────────────────────────────────────

def test_buy_first_day_locked(request):
    """首买:扣现金、建仓,当日 T+1 锁定(sellable=0)。"""
    a = _acct(request)
    r = a.buy("000021", 200, 40.00, on="2026-08-12")
    pos = a.position("000021")
    print(f"  → 买入结果 {r},持仓 {pos}")
    assert pos["quantity"] == 200
    assert pos["sellable"] == 0  # T+1 当日不可卖
    assert pos["avg_cost"] == 40.00
    assert a.cash() == 100_000_00 - 200 * 4000


def test_buy_add_weighted_cost(request):
    """加仓:成本加权,且重置 T+1(保守)。"""
    a = _acct(request)
    a.buy("000021", 100, 40.00, on="2026-08-11")
    a.settle("2026-08-12")  # 旧仓解锁
    a.buy("000021", 100, 60.00, on="2026-08-12")  # 加仓
    pos = a.position("000021")
    print(f"  → 加仓后 {pos}")
    assert pos["quantity"] == 200
    assert pos["avg_cost"] == 50.00  # (100*40 + 100*60)/200
    assert pos["sellable"] == 100  # 旧的100仍可卖,新100锁定


def test_buy_cash_insufficient(request):
    """现金不足:拒绝并保持状态不变。"""
    a = _acct(request, initial=5_000_00)  # ¥5,000
    with pytest.raises(AccountError, match="现金不足"):
        a.buy("000021", 200, 40.00)
    assert a.cash() == 5_000_00
    assert a.positions() == []


# ── 卖出 + T+1 ─────────────────────────────────────────

def test_sell_reject_before_settle(request):
    """T+1 锁定:当日买入卖不出(可卖不足拒绝)。"""
    a = _acct(request)
    a.buy("000021", 100, 40.00, on="2026-08-12")
    with pytest.raises(AccountError, match="可卖不足"):
        a.sell("000021", 100, 41.00)
    assert a.position("000021")["quantity"] == 100  # 持仓不变


def test_settle_unlock_then_sell(request):
    """settle 解锁:次日全可卖,卖出加现金、减仓。"""
    a = _acct(request)
    a.buy("000021", 100, 40.00, on="2026-08-12")
    n = a.settle("2026-08-13")  # 次日解锁
    assert n == 1
    r = a.sell("000021", 100, 50.00)
    print(f"  → 卖出结果 {r}")
    assert a.cash() == 100_000_00 - 100 * 4000 + 100 * 5000
    assert a.position("000021") is None  # 清仓


# ── 审计对账 ───────────────────────────────────────────

def test_fills_chain(request):
    """fills 链:cash_before 链式衔接(cash_after[i] == cash_before[i+1])。"""
    a = _acct(request)
    a.buy("000021", 100, 40.00, on="2026-08-11")
    a.settle("2026-08-12")
    a.sell("000021", 50, 50.00)
    fills = a.fills()
    print(f"  → {len(fills)} 笔 fill,现金链: {[f['cash_after_cents'] for f in fills]}")
    assert len(fills) == 2
    assert fills[0]["cash_after_cents"] == fills[1]["cash_before_cents"]  # 链式


def test_trade_with_reason(request):
    """决策留痕:买卖的 reason/名称/回放时点/run_id 归因落进 fills。"""
    a = _acct(request)
    a.buy("000021", 100, 40.00, on="2026-08-11", name="深科技",
          reason="#存储芯片-存货涨价 池 4/5 走强,放量领涨", run_id=7)
    a.settle("2026-08-12")
    a.sell("000021", 100, 45.00, reason="预期兑现(出口A)", trade_time="2026-08-12 10:30")
    fills = a.fills()
    print(f"  → 买:{fills[0]['reason']} | 卖:{fills[1]['reason']}")
    assert fills[0]["reason"] == "#存储芯片-存货涨价 池 4/5 走强,放量领涨"
    assert fills[0]["run_id"] == 7            # 成交→场次归因
    assert "expectation_id" not in fills[0]   # 老列已删(平台不绑系统概念)
    assert fills[0]["name"] == "深科技"
    assert fills[1]["trade_time"] == "2026-08-12 10:30"   # 交易时点=回放时点
    assert fills[1]["created_at"] != "2026-08-12 10:30"   # created_at=真实创建时刻
