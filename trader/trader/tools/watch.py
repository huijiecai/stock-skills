"""看盘组合工具(AI 调用):scan_market 快扫。

每轮看盘的第一眼:指数 + 持仓报价(±2% 触发标警)+ 板块 top + 异动 top,一屏扫完。
异动按模式:实时(live)= 涨幅榜;回放(replay)= 涨停清单。
"""

from pydantic_ai import RunContext
from tabulate import tabulate

from trader.store import default_account, default_expectations
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
    _tool_error_text,
)


def get_pool_health(ctx: RunContext[None], expectation_id: int, mode: str = "live",
                    date: str = "", time: str = "") -> str:
    """池健康度:某预期的池成员报价 + X/Y 上涨统计。
    持仓巡检和卖出评估(出口B)必用——用预期自己的固定池,不是板块排名近似。
    对照 get_pool 里的失效标志(通常写了池阈值,如"池≤2/5")。
    """
    e = default_expectations().get(expectation_id)
    if e is None:
        return f"预期 {expectation_id} 不存在(先 get_expectations 查 id)"
    codes = [m["code"] for m in e["pool"]]
    if not codes:
        return f"#{expectation_id} {e['direction']}·{e['event']} 池为空"
    quotes = _fetch_quotes(mode, codes, date, time or None)
    up = sum(1 for q in quotes if q.get("change_pct", 0) > 0)
    rows = [[q["code"], q["name"] or q["code"], q["price"],
             f"{q['change_pct']:+.2f}%"] for q in quotes]
    table = tabulate(rows, headers=["代码", "名称", "现价", "涨跌"],
                     tablefmt="plain", floatfmt=".2f")
    return (f"#{expectation_id} {e['direction']}·{e['event']} [{e['stage']}/{e['status']}]\n"
            f"池健康度: {up}/{len(quotes)} 上涨\n"
            f"失效标志(对照): {e['fail_flag'][:70]}\n{table}")


# astock 失败(如盘后调 live)返回错误文本给 AI,不崩 run
get_pool_health = _tool_error_text(get_pool_health)


def scan_market(ctx: RunContext[None], mode: str = "live", date: str = "", time: str = "") -> str:
    """快扫:一轮看盘的第一眼。
    指数 + 持仓报价(当日±2% 触发标警⚠)+ 板块 top5 + 异动 top5。
    mode=live(实时,异动=涨幅榜)/replay(回放,异动=涨停清单,date 必填)。
    板块/异动依赖 ClickHouse:不可用时分段降级 + 顶部警示,不让整轮快扫失败,
    也禁止 AI 假装已完成市场感知(8/17 ClickHouse 停机曾静默降级近1小时)。
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

    # ②-bis 预期池快览(自选列表常驻:harness 每轮强制呈现全部 active 预期池状态,
    # 不依赖 AI "记得去看"——两次实测均因注意力漂移漏盯库内预期,故由工具层保证呈现)
    def _pool_brief():
        est = default_expectations()
        active = [e for e in est.get_all() if e["status"] == "active" and e["pool_count"] > 0]
        if not active:
            return "(无 active 预期)"
        pools = {e["id"]: est.get(e["id"])["pool"] for e in active}
        codes = list(dict.fromkeys(m["code"] for p in pools.values() for m in p))
        q_by = {q["code"]: q for q in _fetch_quotes(mode, codes, date, t)}
        lines = []
        for e in active:
            members = pools[e["id"]]
            ups = sum(1 for m in members if q_by.get(m["code"], {}).get("change_pct", 0) > 0)
            top = max(members, key=lambda m: q_by.get(m["code"], {}).get("change_pct", -99))
            tq = q_by.get(top["code"], {})
            mb = "·主板可买" if top["code"].startswith(("000", "001", "002", "003", "600", "601", "603", "605")) else ""
            chg = f"{tq.get('change_pct', 0):+.1f}%" if tq else "?"
            lines.append(f"#{e['id']} {e['direction']} 池{ups}/{len(members)}↑ "
                         f"最强:{top['name'] or top['code']} {chg}{mb}")
        return "\n".join(lines)
    parts.append("【预期池快览】(全部 active 预期,每轮自动呈现;走强/启动的→当轮深析)")
    parts.append(_safe("池快览", _pool_brief))
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
                       "禁止假装已扫描;指数与池健康度仍可用,持仓巡检照常执行。")
    return "\n".join(parts)


# astock 失败(如盘后调 live)返回错误文本给 AI,不崩 run
scan_market = _tool_error_text(scan_market)
