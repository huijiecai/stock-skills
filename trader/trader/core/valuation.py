"""core·估值服务(平台通用件):组合净值曲线/日频估值/封场指标的唯一实现。

"组合估值"只在这里算:API 资产页(曲线)与 engine(封场 metrics)共用同一套口径,
其他模块不得各自写 SQL/行情折叠重算(见 docs/企业级优化路线图.md T1.1)。
金额单位一律为分(int cents),展示层自行 /100。
"""
from datetime import datetime as _dt
from datetime import timedelta as _td

from trader.core.ledger import Wallet, default_wallet


def _acct(wallet: Wallet | None) -> Wallet:
    return wallet if wallet is not None else default_wallet()


def portfolio_curve(portfolio_id: int, wallet: Wallet | None = None) -> dict:
    """组合净值曲线(双口径):
    - points: 成交时点权益(fills 折叠,持仓按最近成交价;末尾追加现价点)
    - daily: 日频净值——每个交易日收盘估值(今日按现价),资产页"每天的盈利"
    行情不可得时退最近已知价/成交价。返回 {initial, points, daily}。"""
    from trader.core.market import _fetch_quotes

    acct = _acct(wallet)
    w = acct.balance(portfolio_id)
    if w is None:
        return {"initial": None, "points": [], "daily": []}
    fills = acct.fills(portfolio_id)
    equity, pos, last_px = w["initial_cents"], {}, {}
    points = [{"ts": "", "equity": w["initial_cents"], "run_id": None}]
    for f in fills:
        code, qty, px = f["code"], f["quantity"], f["price_cents"]
        if f["side"] == "BUY":
            equity -= qty * px
            pos[code] = pos.get(code, 0) + qty
        else:
            equity += qty * px
            pos[code] = pos.get(code, 0) - qty
        last_px[code] = px
        mark = equity + sum(q * last_px[c] for c, q in pos.items() if q > 0)
        points.append({"ts": f["trade_time"] or f["created_at"], "equity": mark,
                       "run_id": f.get("run_id")})
    holding = {c: q for c, q in pos.items() if q > 0}
    if holding and fills:
        try:
            qs = _fetch_quotes("live", list(holding))
            px_by = {q["code"]: round(q["price"] * 100) for q in qs if q.get("price")}
            if px_by:
                mark = equity + sum(q * px_by.get(c, last_px[c])
                                    for c, q in holding.items())
                points.append({"ts": _dt.now().isoformat(timespec="seconds"),
                               "equity": mark, "run_id": fills[-1].get("run_id")})
        except Exception:  # noqa: BLE001 —— 行情不可得则不追加,曲线保持成交价口径
            pass
    return {"initial": w["initial_cents"], "points": points,
            "daily": _daily_equity(fills, w["initial_cents"])}


def _daily_equity(fills: list[dict], initial: int) -> list[dict]:
    """日频净值:每交易日收盘 mark(今日按现价)——逐日展示盈亏,无成交日也在场。
    日历+收盘价取自各持有代码的日 K(合并日期补停牌缺口);单代码行情缺失不阻塞。
    返回 [{date, equity, pnl, pct, run_id}],pnl=较上一交易日(首日=相对初始资金)。

    前提与让步:日 K 同步可能滞后于真实日期,此时近期交易日缺口用市场概要逐日
    探测补齐(交易日返回日期/非交易日抛异常),从最后一条 K 线日起探,限 15 天防慢查询。
    """
    from trader.core.market import _fetch_kline, _fetch_market_summary, _fetch_quotes

    if not fills:
        return []
    fill_day = lambda f: (f.get("trade_time") or f["created_at"] or "")[:10]
    today = _dt.now().strftime("%Y-%m-%d")
    start = min(fill_day(f) for f in fills)
    span_days = (_dt.now() - _dt.fromisoformat(start)).days
    if span_days > 365:
        start = (_dt.now() - _td(days=365)).strftime("%Y-%m-%d")  # 只看近一年
    limit = min(260, span_days + 12)
    closes: dict[str, dict[str, int]] = {}       # code -> {iso: close_cents}
    cal: set[str] = set()
    for c in {f["code"] for f in fills if fill_day(f) >= start}:
        try:
            for k in _fetch_kline(c, limit=limit):
                d = str(k.get("trade_date", ""))[:10]
                if k.get("close") and start <= d <= today:
                    closes.setdefault(c, {})[d] = round(k["close"] * 100)
                    cal.add(d)
        except Exception:  # noqa: BLE001
            continue
    cal |= {fill_day(f) for f in fills if fill_day(f) <= today}   # 成交日必是交易日
    kline_last = max((d for m in closes.values() for d in m), default=None)
    probe = _dt.fromisoformat(kline_last or start)
    for _ in range(min(15, (_dt.now() - probe).days)):
        probe += _td(days=1)
        ds = probe.strftime("%Y-%m-%d")
        if ds > today or ds in cal or probe.weekday() >= 5:
            continue
        try:
            if _fetch_market_summary(ds.replace("-", "")).get("date"):
                cal.add(ds)
        except Exception:  # noqa: BLE001 —— 非交易日/无数据,跳过
            continue
    if _dt.now().weekday() < 5:
        cal.add(today)                    # 今日(盘中/收盘)也进序列;周末不加
    days = sorted(d for d in cal if start <= d <= today)
    px_now: dict[str, int] = {}
    try:
        qs = _fetch_quotes("live", sorted({f["code"] for f in fills}))
        px_now = {q["code"]: round(q["price"] * 100) for q in qs if q.get("price")}
    except Exception:  # noqa: BLE001
        px_now = {}

    by_day: dict[str, list[dict]] = {}
    for f in fills:
        by_day.setdefault(fill_day(f), []).append(f)

    def close_asof(c: str, d: str, last_fill_px: int) -> int | None:
        """d 日收盘价:当日 → 最近已知收盘 → 最近成交价。"""
        mp = closes.get(c) or {}
        if d in mp:
            return mp[d]
        known = [dd for dd in mp if dd <= d]
        if known:
            return mp[known[-1]]
        return last_fill_px or None

    cash, pos, last_px, out, prev = initial, {}, {}, [], initial
    run_of_day: dict[str, int] = {}
    for d in days:
        for f in by_day.get(d, []):
            q, px = f["quantity"], f["price_cents"]
            cash += q * px if f["side"] == "SELL" else -q * px
            pos[f["code"]] = pos.get(f["code"], 0) + (q if f["side"] == "BUY" else -q)
            last_px[f["code"]] = px
            if f.get("run_id"):
                run_of_day[d] = f["run_id"]
        mark = cash
        for c, q in pos.items():
            if q <= 0:
                continue
            px = (px_now.get(c) if d == today else None) or close_asof(c, d, last_px.get(c, 0))
            if px:
                mark += q * px
        out.append({"date": d, "equity": mark, "pnl": mark - prev,
                    "pct": round((mark - prev) / prev * 100, 2) if prev > 0 else 0.0,
                    "run_id": run_of_day.get(d)})
        prev = mark
    return out


def compute_metrics(portfolio_id: int, date: str, run_id: int | None = None,
                    mode: str = "replay", wallet: Wallet | None = None) -> dict:
    """封场自动算:本场收益/净值曲线最大回撤/胜率盈亏比/计数。

    run_id 给定时只归因本场成交——live/paper 写跨日复用的共享组合,不过滤会把
    整本历史算进本场(归因口径与 run 336 事故背景见 ADR-0002);回放一场一
    组合,过滤后与整组合同义。本场盈亏 = 本场卖出的已实现(认组合均价成本,
    继承的老底也算)+ 本场净买入期末仍持有的浮盈(期末价 − 本场成交均价);
    期初资产 = 期末资产 − 本场盈亏(单一组合时恰等于钱包初始资金)。
    mode 决定期末估值行情:live 场传 live(实时价,当日 replay 尚无数据),
    回放传 replay(当日收盘);行情取不到浮盈记 0,资产退成本。"""
    from trader.core.market import _fetch_quotes

    acct = _acct(wallet)
    all_fills = acct.fills(portfolio_id)
    is_run = (lambda f: True) if run_id is None else (lambda f: f.get("run_id") == run_id)
    fills = [f for f in all_fills if is_run(f)]
    wrow = acct.balance(portfolio_id)
    cash = wrow["cash_cents"] if wrow else 0

    # 期末估值:行情价优先,取不到退持仓成本(期末资产/现金是组合口径,整本持仓)
    positions = acct.positions(portfolio_id)
    px_by: dict[str, int] = {}
    try:
        if positions:
            qs = _fetch_quotes(mode, [p["code"] for p in positions], date)
            px_by = {q["code"]: round(q["price"] * 100) for q in qs if q.get("price")}
    except Exception:  # noqa: BLE001 —— 行情不可得时按成本
        px_by = {}
    cost_by = {p["code"]: round(p["avg_cost"] * 100) for p in positions}
    market_value = sum(p["quantity"] * (px_by.get(p["code"]) or cost_by.get(p["code"], 0))
                       for p in positions)
    asset = cash + market_value

    # 组合级均价台账(按 id 序折全部流水):本场的卖出认组合成本(继承老底),
    # 非本场成交只推台账不计盈亏;本场买入量/额单独记(浮盈按本场成交均价)
    book: dict[str, list[int]] = {}      # code -> [qty, total_cost_cents]
    realized: list[int] = []
    buys_qty: dict[str, int] = {}
    buys_cost: dict[str, int] = {}
    for f in all_fills:
        code, q, px = f["code"], f["quantity"], f["price_cents"]
        st = book.setdefault(code, [0, 0])
        if f["side"] == "BUY":
            st[0] += q
            st[1] += q * px
            if is_run(f):
                buys_qty[code] = buys_qty.get(code, 0) + q
                buys_cost[code] = buys_cost.get(code, 0) + q * px
        else:
            avg = st[1] // st[0] if st[0] else 0
            st[0] -= q
            st[1] -= q * avg
            if is_run(f):
                realized.append(q * px - q * avg)

    # 本场浮盈:净买入且期末仍持有 → 净量 × (期末价 − 本场成交均价);无行情记 0
    net: dict[str, int] = {}
    for f in fills:
        sign = 1 if f["side"] == "BUY" else -1
        net[f["code"]] = net.get(f["code"], 0) + sign * f["quantity"]
    unrealized = sum(q * (px_by[c] - round(buys_cost[c] / buys_qty[c]))
                     for c, q in net.items()
                     if q > 0 and buys_qty.get(c) and px_by.get(c))

    pnl = sum(realized) + unrealized
    initial = asset - pnl
    # 净值曲线(本场 fills 折叠,持仓按最近成交价估值,起点=期初资产)
    equity, curve, pos, last_px = initial, [], {}, {}
    for f in fills:
        code, q, px = f["code"], f["quantity"], f["price_cents"]
        if f["side"] == "BUY":
            equity -= q * px
            pos[code] = pos.get(code, 0) + q
        else:
            equity += q * px
            pos[code] = pos.get(code, 0) - q
        last_px[code] = px
        curve.append(equity + sum(hq * last_px[c] for c, hq in pos.items() if hq > 0))
    peak, max_dd = initial, 0.0
    for v in curve:
        peak = max(peak, v)
        if peak > 0:
            max_dd = max(max_dd, (peak - v) / peak)
    wins = [r for r in realized if r > 0]
    losses = [r for r in realized if r <= 0]
    return {
        "initial": initial / 100, "cash": cash / 100, "asset": asset / 100,
        "pnl": pnl / 100,
        "return_pct": round(pnl / initial * 100, 2) if initial > 0 else 0.0,
        "max_drawdown_pct": round(max_dd * 100, 2),
        "win_rate": round(len(wins) / len(realized) * 100, 1) if realized else None,
        "profit_factor": (round(sum(wins) / -sum(losses), 2)
                          if losses and sum(losses) < 0 else
                          (None if not wins else 999.0)),
        "n_fills": len(fills), "realized_trades": len(realized),
    }
