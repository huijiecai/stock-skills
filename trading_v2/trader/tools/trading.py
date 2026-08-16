"""交易工具(AI 调用):execute 下单。

规则校验(整手/主板)→ 按行情价成交(不收 AI 传价,防报假价)→ 更新账户。
T+1 / 现金不足由 store.Account 校验,拒绝时给出明确原因。

成交价:
- mode=live(默认):实时价
- mode=replay:回放时点的价(date/time 必传)——模拟看盘按当时行情成交,与行情工具一致
"""

from pydantic_ai import RunContext

from trader.store import AccountError, default_account
from trader.tools.market import _fetch_quotes, _tool_error_text

MAINBOARD = ("000", "001", "002", "003", "600", "601", "603", "605")


def execute(ctx: RunContext[None], action: str, code: str, quantity: int,
            mode: str = "live", date: str = "", time: str = "") -> str:
    """下单交易。action=BUY/SELL;quantity 股数(必须整手,100 的倍数)。
    只能沪深主板;价格按行情成交(AI 不传价):mode=live 实时价(默认),
    mode=replay 按回放时点价(date/time 必传,模拟看盘时用这个)。
    T+1/现金不足会拒绝并说明原因。
    """
    if action not in ("BUY", "SELL"):
        return f"拒绝:action 必须是 BUY 或 SELL,收到 {action}"
    if quantity <= 0 or quantity % 100 != 0:
        return f"拒绝:数量必须是整手(100 的倍数),收到 {quantity}"
    if not code.startswith(MAINBOARD):
        return f"拒绝:{code} 不是主板(只允许 000/001/002/003/600/601/603/605)"
    if mode == "replay" and not date:
        return "拒绝:replay 模式必须传 date(如 20260814)"

    # 按模式取成交价(live=实时,replay=回放时点)
    quotes = _fetch_quotes(mode, [code], date, time or None)
    if not quotes:
        return f"拒绝:查不到 {code} 行情(mode={mode} date={date} time={time})"
    price = quotes[0]["price"]
    name = quotes[0].get("name", "")

    acct = default_account()
    try:
        if action == "BUY":
            r = acct.buy(code, quantity, price, on=date or None)  # replay 时 T+1 按回放日算
        else:
            r = acct.sell(code, quantity, price)
    except AccountError as e:
        return f"拒绝:{e}"
    return (f"成交 {action} {code} {name} {quantity}股 @ ¥{price:.2f}"
            f"{'(回放 ' + date + ' ' + (time or '收盘') + ')' if mode == 'replay' else ''},"
            f"现金 ¥{r['cash_after']:,.2f},持仓 {r['position_after']}股")


# astock 失败(如非交易日调 live)返回错误文本给 AI,不崩 run
execute = _tool_error_text(execute)
