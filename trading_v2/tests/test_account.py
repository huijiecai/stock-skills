"""Account 测试:模拟账户(SQLite,tmp 库,不碰真实数据)。

覆盖:初始化 / 买入(T+1锁/加权成本) / 卖出(可卖校验) / settle 解锁 / 现金不足。

docstring 统一格式:<场景>:<验证点>
"""
import pytest

from trader.store import Account, AccountError

TOOL = "account"


def _acct(tmp_path, initial=100_000_00):
    return Account(db_path=tmp_path / "test.db", initial_cash=initial)


# ── 初始化 ─────────────────────────────────────────────

def test_init_cash(tmp_path):
    """初始化:现金=初始资金,持仓为空。"""
    a = _acct(tmp_path)
    print(f"  → 现金 ¥{a.cash() / 100:,.2f},持仓 {a.positions()}")
    assert a.cash() == 100_000_00
    assert a.positions() == []


# ── 买入 ───────────────────────────────────────────────

def test_buy_first_day_locked(tmp_path):
    """首买:扣现金、建仓,当日 T+1 锁定(sellable=0)。"""
    a = _acct(tmp_path)
    r = a.buy("000021", 200, 40.00, on="2026-08-12")
    pos = a.position("000021")
    print(f"  → 买入结果 {r},持仓 {pos}")
    assert pos["quantity"] == 200
    assert pos["sellable"] == 0  # T+1 当日不可卖
    assert pos["avg_cost"] == 40.00
    assert a.cash() == 100_000_00 - 200 * 4000


def test_buy_add_weighted_cost(tmp_path):
    """加仓:成本加权,且重置 T+1(保守)。"""
    a = _acct(tmp_path)
    a.buy("000021", 100, 40.00, on="2026-08-11")
    a.settle("2026-08-12")  # 旧仓解锁
    a.buy("000021", 100, 60.00, on="2026-08-12")  # 加仓
    pos = a.position("000021")
    print(f"  → 加仓后 {pos}")
    assert pos["quantity"] == 200
    assert pos["avg_cost"] == 50.00  # (100*40 + 100*60)/200
    assert pos["sellable"] == 100  # 旧的100仍可卖,新100锁定


def test_buy_cash_insufficient(tmp_path):
    """现金不足:拒绝并保持状态不变。"""
    a = _acct(tmp_path, initial=5_000_00)  # ¥5,000
    with pytest.raises(AccountError, match="现金不足"):
        a.buy("000021", 200, 40.00)
    assert a.cash() == 5_000_00
    assert a.positions() == []


# ── 卖出 + T+1 ─────────────────────────────────────────

def test_sell_reject_before_settle(tmp_path):
    """T+1 锁定:当日买入卖不出(可卖不足拒绝)。"""
    a = _acct(tmp_path)
    a.buy("000021", 100, 40.00, on="2026-08-12")
    with pytest.raises(AccountError, match="可卖不足"):
        a.sell("000021", 100, 41.00)
    assert a.position("000021")["quantity"] == 100  # 持仓不变


def test_settle_unlock_then_sell(tmp_path):
    """settle 解锁:次日全可卖,卖出加现金、减仓。"""
    a = _acct(tmp_path)
    a.buy("000021", 100, 40.00, on="2026-08-12")
    n = a.settle("2026-08-13")  # 次日解锁
    assert n == 1
    r = a.sell("000021", 100, 50.00)
    print(f"  → 卖出结果 {r}")
    assert a.cash() == 100_000_00 - 100 * 4000 + 100 * 5000
    assert a.position("000021") is None  # 清仓


# ── 审计对账 ───────────────────────────────────────────

def test_fills_chain(tmp_path):
    """fills 链:cash_before 链式衔接(cash_after[i] == cash_before[i+1])。"""
    a = _acct(tmp_path)
    a.buy("000021", 100, 40.00, on="2026-08-11")
    a.settle("2026-08-12")
    a.sell("000021", 50, 50.00)
    fills = a.fills()
    print(f"  → {len(fills)} 笔 fill,现金链: {[f['cash_after_cents'] for f in fills]}")
    assert len(fills) == 2
    assert fills[0]["cash_after_cents"] == fills[1]["cash_before_cents"]  # 链式


def test_trade_with_reason(tmp_path):
    """决策留痕:买卖的 reason/expectation_id/名称/回放时点 落进 fills。"""
    a = _acct(tmp_path)
    a.buy("000021", 100, 40.00, on="2026-08-11", name="深科技",
          reason="存储主线确认,放量领涨", expectation_id=4)
    a.settle("2026-08-12")
    a.sell("000021", 100, 45.00, reason="预期兑现(出口A)", expectation_id=4,
           trade_time="2026-08-12 10:30")
    fills = a.fills()
    print(f"  → 买:{fills[0]['reason']} | 卖:{fills[1]['reason']}")
    assert fills[0]["reason"] == "存储主线确认,放量领涨"
    assert fills[0]["expectation_id"] == 4
    assert fills[0]["name"] == "深科技"
    assert fills[1]["created_at"] == "2026-08-12 10:30"  # 回放时点替代真实时间
