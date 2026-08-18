"""core·快扫(平台通用件):一轮看盘的第一眼。

指数 + 持仓报价(±2% 标警)+ 【自选组快览】(全部自选组状态,反注意力漂移机制平台化)
+ 板块 top5 + 异动 top5。降级容忍:ClickHouse 不可用时分段降级 + 顶部警示,
不让整轮快扫失败,也禁止 AI 假装已完成市场感知(8/17 停机曾静默降级近 1 小时)。
"""
from pydantic_ai import RunContext
from tabulate import tabulate

from trader.core.ledger import default_account
from trader.core.market import (
    _fetch_block_rank,
    _fetch_candidates,
    _fetch_indices,
    _fetch_limit_up,
    _fetch_quotes,
    _format_block_rank,
    _format_candidates,
    _format_indices,
    _format_limit_up,
    _tool_error_text,
)
from trader.core.watchlist import default_watchlists


def scan_market(ctx: RunContext[None], mode: str = "live", date: str = "", time: str = "") -> str:
    """快扫:一轮看盘的第一眼。
    指数 + 持仓报价(当日±2% 触发标警⚠)+ 自选组快览 + 板块 top5 + 异动 top5。
    mode=live(实时,异动=涨幅榜)/replay(回放,异动=涨停清单,date 必填)。
    """
    t = time or None
    degraded: list[str] = []

    def _safe(label: str, fetch):
        try:
            return fetch()
        except Exception as e:  # noqa: BLE001 —— 单段失败不拖垮整轮快扫
            degraded.append(f"{label}不可用({str(e)[:60]})")
            return f"({label}数据不可用)"

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

    # ②-bis 自选组快览(盯防面板:每轮强制呈现全部自选组状态,不依赖 AI "记得去看")
    def _wl_brief():
        wls = default_watchlists()
        groups = [g["name"] for g in wls.list_all() if not g["name"].startswith("archived-")]
        if not groups:
            return "(无自选组)"
        members_by = {n: wls.get(n) for n in groups}
        codes = list(dict.fromkeys(m["code"] for ms in members_by.values() for m in ms))
        if not codes:
            return "(自选组均空)"
        q_by = {q["code"]: q for q in _fetch_quotes(mode, codes, date, t)}
        lines = []
        for n in groups:
            ms = members_by[n]
            ups = sum(1 for m in ms if q_by.get(m["code"], {}).get("change_pct", 0) > 0)
            top = max(ms, key=lambda m: q_by.get(m["code"], {}).get("change_pct", -99))
            tq = q_by.get(top["code"], {})
            mb = "·主板可买" if top["code"].startswith(("000", "001", "002", "003", "600", "601", "603", "605")) else ""
            chg = f"{tq.get('change_pct', 0):+.1f}%" if tq else "?"
            lines.append(f"{n} 池{ups}/{len(ms)}↑ 最强:{top['name'] or top['code']} {chg}{mb}")
        return "\n".join(lines)
    parts.append("【自选组快览】(全部自选组每轮自动呈现;走强/启动的→当轮深析)")
    parts.append(_safe("自选组快览", _wl_brief))
    parts.append("")

    # ③ 板块 top5
    parts.append("【板块 top5】")
    parts.append(_safe("板块排名", lambda: _format_block_rank(_fetch_block_rank(mode, date, t, limit=5))))
    parts.append("")

    # ④ 异动 top5(实时=涨幅榜,回放=涨停清单)
    label = "涨幅榜" if mode == "live" else "涨停清单"
    parts.append(f"【异动 top5 · {label}】")
    if mode == "live":
        parts.append(_safe("涨幅榜", lambda: _format_candidates(_fetch_candidates(limit=5))))
    else:
        data = _safe("涨停清单", lambda: _fetch_limit_up(date, t))
        if isinstance(data, list):
            parts.append(_format_limit_up(data[:5]))
            if len(data) > 5:
                parts.append(f"(共 {len(data)} 只触及涨停)")

    if degraded:
        parts.insert(0, "⚠ 数据通道降级:" + ";".join(degraded)
                     + "\n  → ②市场感知/④涨停异动本轮受限:输出里必须如实说明受限,"
                       "禁止假装已扫描;指数与自选组仍可用,持仓巡检照常执行。")
    return "\n".join(parts)


# astock 失败(如盘后调 live)返回错误文本给 AI,不崩 run
scan_market = _tool_error_text(scan_market)
