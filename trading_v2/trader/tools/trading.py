"""交易工具(AI 调用):execute 下单。

规则校验(整手/主板)→ 按实时价成交(不收 AI 传价,防报假价)→ 更新账户。
T+1 / 现金不足由 store.Account 校验,拒绝时给出明确原因。
"""

from pydantic_ai import RunContext

from trader.store import AccountError, default_account
from trader.tools.market import _astock

MAINBOARD = ("000", "001", "002", "003", "600", "601", "603", "605")


def execute(ctx: RunContext[None], action: str, code: str, quantity: int) -> str:
    """下单交易。action=BUY/SELL;quantity 股数(必须整手,100 的倍数)。
    只能沪深主板;价格按实时行情成交;T+1/现金不足会拒绝并说明原因。
    """
    if action not in ("BUY", "SELL"):
        return f"拒绝:action 必须是 BUY 或 SELL,收到 {action}"
    if quantity <= 0 or quantity % 100 != 0:
        return f"拒绝:数量必须是整手(100 的倍数),收到 {quantity}"
    if not code.startswith(MAINBOARD):
        return f"拒绝:{code} 不是主板(只允许 000/001/002/003/600/601/603/605)"
    quotes = _astock("live", "quote", code)
    if not quotes:
        return f"拒绝:查不到 {code} 实时行情"
    price = quotes[0]["price"]
    name = quotes[0].get("name", "")
    acct = default_account()
    try:
        r = acct.buy(code, quantity, price) if action == "BUY" else acct.sell(code, quantity, price)
    except AccountError as e:
        return f"拒绝:{e}"
    return (f"成交 {action} {code} {name} {quantity}股 @ ¥{price:.2f},"
            f"现金 ¥{r['cash_after']:,.2f},持仓 {r['position_after']}股")
