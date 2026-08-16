"""账户查询工具(AI 调用):get_positions / get_account。

底层是 store.Account(SQLite);市值/浮盈需要实时价,调 tools/market 底层。
"""

from pydantic_ai import RunContext
from tabulate import tabulate

from trader.store import default_account
from trader.tools.market import _fetch_quotes, _tool_error_text


def get_positions(ctx: RunContext[None]) -> str:
    """查当前持仓(代码/数量/可卖/成本/买入日)。"可卖"受 T+1 限制。"""
    data = default_account().positions()
    if not data:
        return "无持仓"
    rows = [[p["code"], p["quantity"], p["sellable"], p["avg_cost"], p["bought_on"]] for p in data]
    return tabulate(rows, headers=["代码", "数量", "可卖", "成本", "买入日"],
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
