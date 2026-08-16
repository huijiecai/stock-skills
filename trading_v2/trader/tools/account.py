"""账户查询工具(AI 调用):get_positions / get_account。

底层是 store.Account(SQLite);市值/浮盈需要实时价,调 tools/market 底层。
"""

from pydantic_ai import RunContext
from tabulate import tabulate

from trader.store import default_account
from trader.tools.market import _fetch_quotes, _tool_error_text


def get_positions(ctx: RunContext[None]) -> str:
    """查当前持仓(代码/名称/数量/可卖/成本/买入日)。"可卖"受 T+1 限制。"""
    data = default_account().positions()
    if not data:
        return "无持仓"
    rows = [[p["code"], p["name"] or "-", p["quantity"], p["sellable"],
             p["avg_cost"], p["bought_on"]] for p in data]
    return tabulate(rows, headers=["代码", "名称", "数量", "可卖", "成本", "买入日"],
                    tablefmt="plain", floatfmt=".2f")


def get_account(ctx: RunContext[None]) -> str:
    """查账户:现金/持仓市值/总资产/浮盈(市值按实时价,查不到用成本价)。"""
    acct = default_account()
    cash = acct.cash() / 100
    positions = acct.positions()
    market_value = 0.0
    if positions:
        quotes = _fetch_quotes("live", [p["code"] for p in positions])
        price_by = {q["code"]: q["price"] for q in quotes}
        for p in positions:
            market_value += p["quantity"] * price_by.get(p["code"], p["avg_cost"])
    cost = sum(p["quantity"] * p["avg_cost"] for p in positions)
    return (f"现金 ¥{cash:,.2f} | 持仓市值 ¥{market_value:,.2f} | "
            f"总资产 ¥{cash + market_value:,.2f} | 浮盈 {market_value - cost:+,.2f}")


# get_account 内部查实时行情,非交易日会失败 → 返回错误文本,不崩 run
get_account = _tool_error_text(get_account)


def get_trades(ctx: RunContext[None]) -> str:
    """查全部成交记录(含每笔的决策留痕:为什么买/卖、关联哪条预期)。复盘用。"""
    fills = default_account().fills()
    if not fills:
        return "无成交记录"
    rows = []
    for f in reversed(fills):  # 最新在前
        rows.append([
            f["id"], f["created_at"][:16], f["code"], f.get("name", ""), f["side"],
            f["quantity"], f["price_cents"] / 100,
            f"#{f['expectation_id']}" if f.get("expectation_id") else "-",
            (f.get("reason") or "-")[:45],
        ])
    return tabulate(rows, headers=["id", "时间", "代码", "名称", "方向", "数量", "价格", "预期", "决策依据"],
                    tablefmt="plain", floatfmt=".2f")
