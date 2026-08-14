"""看盘组合工具(AI 调用):scan_market 快扫。

每轮看盘的第一眼:指数 + 持仓报价(±2% 触发标警)+ 板块 top + 异动 top,一屏扫完。
异动按模式:实时(live)= 涨幅榜;回放(replay)= 涨停清单。
"""

from pydantic_ai import RunContext
from tabulate import tabulate

from trader.store import default_account
from trader.tools.market import (
    _fetch_block_rank,
    _fetch_candidates,
    _fetch_indices,
    _fetch_limit_up,
    _fetch_quotes,
    _format_block_rank,
    _format_candidates,
    _format_indices,
    _format_limit_up,
)


def scan_market(ctx: RunContext[None], mode: str = "live", date: str = "", time: str = "") -> str:
    """快扫:一轮看盘的第一眼。
    指数 + 持仓报价(当日±2% 触发标警⚠)+ 板块 top5 + 异动 top5。
    mode=live(实时,异动=涨幅榜)/replay(回放,异动=涨停清单,date 必填)。
    """
    t = time or None

    # ① 指数
    parts = ["【指数】", _format_indices(_fetch_indices(mode, date, t)), ""]

    # ② 持仓(当日 ±2% 是交易系统的巡检触发线 → 标 ⚠ 提醒 AI 该评估)
    positions = default_account().positions()
    parts.append("【持仓】")
    if positions:
        quotes = _fetch_quotes(mode, [p["code"] for p in positions], date, t)
        pos_by = {p["code"]: p for p in positions}
        rows = []
        for q in quotes:
            p = pos_by.get(q["code"])
            cost = p["avg_cost"] if p else 0.0
            chg = q["change_pct"]
            pnl = (q["price"] - cost) / cost * 100 if cost else 0.0
            rows.append([
                q["code"], q["name"] or q["code"], q["price"], cost,
                f"{chg:+.2f}%" + ("⚠" if abs(chg) >= 2 else ""),
                f"{pnl:+.2f}%",
            ])
        parts.append(tabulate(rows, headers=["代码", "名称", "现价", "成本", "当日", "浮盈"],
                              tablefmt="plain", floatfmt=".2f"))
    else:
        parts.append("空仓")
    parts.append("")

    # ③ 板块 top5
    parts.append("【板块 top5】")
    parts.append(_format_block_rank(_fetch_block_rank(mode, date, t, limit=5)))
    parts.append("")

    # ④ 异动 top5(实时=涨幅榜,回放=涨停清单)
    label = "涨幅榜" if mode == "live" else "涨停清单"
    parts.append(f"【异动 top5 · {label}】")
    if mode == "live":
        parts.append(_format_candidates(_fetch_candidates(limit=5)))
    else:
        data = _fetch_limit_up(date, t)
        parts.append(_format_limit_up(data[:5]))
        if len(data) > 5:
            parts.append(f"(共 {len(data)} 只触及涨停)")

    return "\n".join(parts)
