"""交易工具(AI 调用):execute 下单。

规则校验(整手/主板)→ 按行情价成交(不收 AI 传价,防报假价)→ 更新账户 + 决策留痕。
T+1 / 现金不足由 store.Account 校验,拒绝时给出明确原因。

决策留痕(交易系统硬规则:不留痕不许动账户):
- reason 必填:决策依据(基于哪条预期、什么信号触发,写清引用如"#37");卖出时写明出口(预期兑现A/资金确认消失B)
- 与预期的关联写在 reason 文本里(C1e 起去掉专用 expectation_id 参数——平台工具不绑定任何系统概念)

成交价:
- mode=live(默认):实时价
- mode=replay:回放时点的价(date/time 必传)——模拟看盘按当时行情成交,与行情工具一致
"""

from pydantic_ai import RunContext

from trader.store import AccountError, default_account
from trader.tools.market import _fetch_quotes, _tool_error_text

MAINBOARD = ("000", "001", "002", "003", "600", "601", "603", "605")

# 单票市值占成本法总资产上限(8/17 剑桥首笔 57.6% 无任何约束,故加硬闸)
MAX_POSITION_RATIO = 0.40


def _check_position_cap(acct, code: str, quantity: int, price: float) -> str | None:
    """买入后的单票占比 ≤40%(成本法总资产 = 现金 + 全部持仓按成本计)。越限返回拒绝原因。"""
    positions = acct.positions()
    total = acct.cash() / 100 + sum(p["quantity"] * p["avg_cost"] for p in positions)
    held_value = sum(p["quantity"] * p["avg_cost"] for p in positions if p["code"] == code)
    new_value = held_value + quantity * price
    if total > 0 and new_value / total > MAX_POSITION_RATIO:
        max_qty = int(total * MAX_POSITION_RATIO - held_value) // 100 * 100
        return (f"拒绝:买入后 {code} 占比 {new_value / total:.0%} 超过单票上限 40%"
                f"(总资产约 ¥{total:,.0f})。最多再买 {max_qty} 股;如需重仓,先在轮日志写明理由后分日建仓")
    return None


def execute(ctx: RunContext[None], action: str, code: str, quantity: int, reason: str,
            mode: str = "live", date: str = "", time: str = "") -> str:
    """下单交易。action=BUY/SELL;quantity 股数(必须整手)。
    reason 必填:决策依据(基于哪条预期/哪个判断——写清引用,如"#37 存储涨价,池 4/5 走强";
    卖出写明出口:预期兑现/资金确认消失)。
    mode=live 实时价(默认)/replay 按回放时点价(date/time 必传)。
    只能沪深主板;T+1/现金不足会拒绝并说明原因。
    """
    if action not in ("BUY", "SELL"):
        return f"拒绝:action 必须是 BUY 或 SELL,收到 {action}"
    if not reason or not reason.strip():
        return "拒绝:必须写决策依据(reason):基于哪条预期、什么信号触发。不留痕不许下单"
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
    trade_time = f"{date} {time}" if mode == "replay" else ""

    acct = default_account()
    try:
        if action == "BUY":
            cap_err = _check_position_cap(acct, code, quantity, price)
            if cap_err:
                return cap_err
            r = acct.buy(code, quantity, price, on=date or None, name=name,
                         reason=reason, trade_time=trade_time)  # replay 时 T+1 按回放日算
        else:
            r = acct.sell(code, quantity, price, reason=reason, trade_time=trade_time)
    except AccountError as e:
        return f"拒绝:{e}"
    tag = f"(回放 {date} {time or '收盘'})" if mode == "replay" else ""
    return (f"成交 {action} {code} {name} {quantity}股 @ ¥{price:.2f}{tag},"
            f"现金 ¥{r['cash_after']:,.2f},持仓 {r['position_after']}股。留痕:{reason[:50]}")


# astock 失败(如非交易日调 live)返回错误文本给 AI,不崩 run
execute = _tool_error_text(execute)
