"""api·组合/场次/交易/文档/自选组端点(读为主 + 组合创建;发起场次走子进程)。"""
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from trader.api.deps import require_user
from trader.core.context import set_context
from trader.core.documents import default_documents
from trader.core.ledger import Wallet
from trader.core.portfolios import default_portfolios
from trader.core.runs import default_runs

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


class PortfolioIn(BaseModel):
    name: str
    type: str = "paper"          # main(实盘,仅管理员) | paper(模拟)
    system: str = "expectation"


@router.get("")
def list_portfolios(who: dict = Depends(require_user)):
    return default_portfolios().list(who["user"]["id"])


@router.post("")
def create_portfolio(body: PortfolioIn, who: dict = Depends(require_user)):
    from trader.core.systems import default_systems
    uid = who["user"]["id"]
    system_row = default_systems().get(body.system, user_id=uid)
    if system_row is None:
        raise HTTPException(404, f"系统不存在:{body.system}")
    if body.type == "main" and not who["user"].get("is_admin"):
        raise HTTPException(403, "实盘组合仅管理员可开(内测期)")
    pid = default_portfolios().create(uid, body.type, system_row["id"], body.name)
    return default_portfolios().get(pid)


@router.get("/{portfolio_id}/curve")
def portfolio_curve(portfolio_id: int, who: dict = Depends(require_user)):
    """组合净值曲线(双口径):
    - points: 成交时点权益(fills 折叠,持仓按最近成交价;末尾追加现价点)
    - daily: 日频净值——每个交易日收盘估值(今日按现价),资产页"每天的盈利"
    行情不可得时退最近已知价/成交价。返回 {initial, points, daily}。"""
    from datetime import datetime as _dt

    from trader.core.db import _connect
    from trader.core.market import _fetch_quotes
    row = default_portfolios().get(portfolio_id)
    if row is None or row["owner_user"] != who["user"]["id"]:
        raise HTTPException(404, "组合不存在(或不属于你)")
    with _connect() as conn:
        w = conn.execute(
            "SELECT cash_cents, initial_cents FROM wallets WHERE portfolio_id=%s",
            (portfolio_id,)).fetchone()
    if w is None:
        return {"initial": None, "points": [], "daily": []}
    fills = Wallet().fills(portfolio_id)
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
    返回 [{date, equity, pnl, pct, run_id}],pnl=较上一交易日(首日=相对初始资金)。"""
    from datetime import datetime as _dt
    from datetime import timedelta as _td

    from trader.core.market import _fetch_kline, _fetch_quotes

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
    # 日 K 数据滞后(本环境只到 08-18):近期缺口用市场概要逐日探(交易日返回
    # 日期/非交易日抛异常),从最后一条 K 线日起探,限 15 天防慢查询
    from trader.core.market import _fetch_market_summary
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


# ── 场次 ────────────────────────────────────────────────

runs_router = APIRouter(prefix="/runs", tags=["runs"])


class ReplayIn(BaseModel):
    system: str
    date: str
    tag: str = ""
    interval: int = 5
    max_rounds: int | None = None


@runs_router.get("")
def list_runs(kind: str = "", date: str = "", system: str = "", who: dict = Depends(require_user)):
    return default_runs().list(kind=kind or None, trade_date=date or None,
                               user_id=who["user"]["id"], system=system or None)


@runs_router.post("/replay")
def start_replay(body: ReplayIn, who: dict = Depends(require_user)):
    """发起一场模拟(子进程执行,架构=每会话一进程;多用户设计 §5-M2 的雏形)。"""
    uid = who["user"]["id"]
    cmd = ["uv", "run", "python", "-m", "trader.runner", "replay", body.date,
           "--user", str(uid), "--interval", str(body.interval), "--tag",
           body.tag or f"api-{uid}"]
    if body.max_rounds:
        cmd += ["--max-rounds", str(body.max_rounds)]
    log = Path("logs/api_runs.log")
    with log.open("ab") as f:
        subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, start_new_session=True,
                         env={**__import__("os").environ, "PYTHONUNBUFFERED": "1"})
    return {"started": True, "system": body.system, "date": body.date,
            "note": "子进程已拉起,轮询 GET /runs 看进度"}


@runs_router.get("/{run_id}")
def run_detail(run_id: int, who: dict = Depends(require_user)):
    for r in default_runs().list(user_id=who["user"]["id"]):
        if r["id"] == run_id:
            return r
    raise HTTPException(404, "场次不存在(或不属于你)")


def _contract_output_rows(run: dict, linked: list[dict], round_no: int | None = None) -> list[dict]:
    """新场按冻结的输出槽位认阶段产物;老场继续用 watch_* 兼容。"""
    contract = run.get("stage_contract") or {}
    slots = set((contract.get("outputs") or {}).keys())
    rows = [d for d in linked if d.get("relation") == "output"
            and d.get("slot") in slots and d.get("stage") == run.get("stage")]
    if round_no is not None:
        rows = [d for d in rows if d.get("round") == round_no]
    if rows:
        return rows
    rows = [d for d in linked if d["doc_type"].startswith("watch_")]
    return [d for d in rows if round_no is None or d.get("round") == round_no
            or (d.get("name") or "") == f"r{round_no}"]


@runs_router.get("/{run_id}/rounds")
def run_rounds(run_id: int, who: dict = Depends(require_user)):
    """轮次概览:编号列表 + 哪些有思考流。single 场次返回一条"输出"伪轮。"""
    run = next((r for r in default_runs().list(user_id=who["user"]["id"])
                if r["id"] == run_id), None)
    if run is None:
        raise HTTPException(404, "场次不存在")
    docs = default_documents()
    linked = docs.for_run(run_id)

    if run["kind"] == "single":
        # 单次分析:找 transcript_{stage} 和该日产出文档(报告)
        date = run["trade_date"] or ""
        portfolio = run["portfolio_id"]
        # transcript: doc_type 以 transcript_ 开头且 name 为空(非轮次)
        transcripts = [d for d in linked if d["doc_type"].startswith("transcript_")]
        # 产出文档:非 transcript/watch/chat 类,且在本场次时间范围内
        run_start = run.get("created_at", "")
        outputs = _contract_output_rows(run, linked)
        if not outputs:
            outputs = [d for d in linked if d["relation"] == "output"
                       and not d["doc_type"].startswith(("transcript_", "watch_", "chat", "coach"))]
        if not outputs:
            outputs = [d for d in docs.list(trade_date=date, portfolio_id=portfolio)
                       if not d["doc_type"].startswith(("transcript_", "watch_", "chat", "coach"))
                       and (d.get("updated_at") or "") >= run_start]
        return {"rounds": [{"n": 1, "has_transcript": bool(transcripts),
                            "single": True, "outputs": outputs}]}

    docs = default_documents()
    # 搜该袋该日的所有 watch_* 轮日志(不限死 watch_live/watch_replay,自定义 log_type 也能找到)
    all_docs = linked or docs.list(trade_date=run["trade_date"],
                                   portfolio_id=run["portfolio_id"])
    stage_outputs = _contract_output_rows(run, all_docs)
    logs = []
    for d in stage_outputs:
        name = d.get("name") or ""
        round_no = d.get("round") or (int(name[1:]) if name.startswith("r") and name[1:].isdigit() else 0)
        if not round_no:
            continue
        full = docs.get_for_run(run_id, d["id"])
        logs.append((round_no, (d.get("updated_at") or "")[11:16],
                     ((full or {}).get("content") or "")[:180]))
    logs.sort()
    ts = {int(d["name"][1:]): (d.get("updated_at") or "")[11:16] for d in all_docs
          if d["doc_type"].startswith("transcript_")
          and (d["name"] or "").startswith("r") and (d["name"] or "r")[1:].isdigit()}
    rounds = [{"n": n, "time": t, "summary": summary, "has_transcript": n in ts}
              for n, t, summary in logs]
    # 进行中轮:事件表最新轮无轮日志(round_start 已落,watch 还没写)→ 列表顶部可见
    if run["status"] == "running":
        from trader.core.events import default_events
        ev = default_events()
        rnd = ev.latest_round(run_id)
        if rnd and not any(n == rnd for n, _, _ in logs):
            start = next((s for s in ev.list(run_id, rnd) if s["kind"] == "round_start"), None)
            rounds.append({"n": rnd, "time": (start.get("created_at") or "")[11:16] if start else "",
                           "has_transcript": False, "in_progress": True})
    return {"rounds": rounds}


@runs_router.get("/{run_id}/rounds/{n}")
def run_round_detail(run_id: int, n: int, who: dict = Depends(require_user)):
    """单轮详情:轮日志(md)+ 思考流(拍平步骤)+ usage。
    single 场次:n=1 → 找 transcript_{stage} + 产出文档。"""
    import json
    run = next((r for r in default_runs().list(user_id=who["user"]["id"])
                if r["id"] == run_id), None)
    if run is None:
        raise HTTPException(404, "场次不存在")
    docs = default_documents()
    portfolio, date = run["portfolio_id"], run["trade_date"] or ""
    linked = [d for d in docs.for_run(run_id) if d.get("round") in (None, 0, n)]

    log, raw = None, None
    if run["kind"] == "single":
        # 找产出文档(报告)作为"轮日志":排除 chat/watch/transcript,限定本场次时间范围
        run_start = run.get("created_at", "")
        candidates = linked or docs.list(trade_date=date, portfolio_id=portfolio)
        output_rows = _contract_output_rows(run, candidates)
        for d in output_rows or candidates:
            if (not d["doc_type"].startswith(("transcript_", "watch_", "chat"))
                    and (d.get("updated_at") or "") >= run_start):
                log = (docs.get_for_run(run_id, d["id"]) or {}).get("content")
                break
        # 找 transcript(doc_type 以 transcript_ 开头,name 不以 r 开头,本场次时间范围)
        for d in candidates:
            if (d["doc_type"].startswith("transcript_") and not (d["name"] or "").startswith("r")
                    and (d.get("updated_at") or "") >= run_start):
                raw = docs.get(d["doc_type"], name=d["name"] or "",
                               trade_date=date, portfolio_id=portfolio)
                break
    else:
        # 搜该袋该日的 watch_* / transcript_*(不限死 live/replay)
        all_docs = linked or docs.list(trade_date=date, portfolio_id=portfolio)
        for d in _contract_output_rows(run, all_docs, n):
            log = (docs.get_for_run(run_id, d["id"]) or {}).get("content")
            break
        for d in all_docs:
            if d["doc_type"].startswith("transcript_") and (d["name"] or "") == f"r{n}":
                raw = docs.get(d["doc_type"], name=f"r{n}", trade_date=date, portfolio_id=portfolio)
                break
    steps, usage = [], {}
    if raw:
        t = json.loads(raw)
        usage = t.get("usage") or {}
        for msg in t.get("messages", []):
            for p in msg.get("parts", []):
                k = p.get("part_kind", "")
                if k == "user-prompt":
                    steps.append({"kind": "prompt", "body": str(p.get("content", ""))})
                elif k == "text":
                    steps.append({"kind": "text", "body": str(p.get("content", ""))})
                elif k == "tool-call":
                    steps.append({"kind": "call", "tool": p.get("tool_name", "?"),
                                  "args": p.get("args", {})})
                elif k == "tool-return":
                    c = p.get("content", "")
                    steps.append({"kind": "ret", "tool": p.get("tool_name", "?"),
                                  "body": c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)})
                elif k == "retry-prompt":
                    steps.append({"kind": "retry", "body": str(p.get("content", ""))})
    return {"n": n, "log_md": log, "steps": steps, "usage": usage}


@runs_router.get("/{run_id}/live")
def run_live_steps(run_id: int, who: dict = Depends(require_user)):
    """实时思考流:当前(最新)轮的事件步骤 + 进行中标记。前端 2 秒轮询。"""
    run = _own_run(run_id, who)
    from trader.core.events import default_events
    ev = default_events()
    rnd = ev.latest_round(run_id)
    if not rnd:
        return {"round": 0, "in_progress": False, "steps": []}
    steps = ev.list(run_id, rnd)
    return {"round": rnd,
            "in_progress": run["status"] == "running" and ev.round_open(run_id, rnd),
            "steps": steps}


@runs_router.post("/{run_id}/stop")
def run_stop(run_id: int, who: dict = Depends(require_user)):
    """优雅停止:置 stopping,engine 完成当前轮后封场退出。
    僵尸场(进程已死)停在 stopping,由 seal 强制收尾。"""
    run = _own_run(run_id, who)
    if run["status"] not in ("running", "stopping"):
        raise HTTPException(409, f"场次状态为 {run['status']},无需停止")
    default_runs().set_status(run_id, "stopping")
    return {"stopped": run_id, "status": "stopping",
            "note": "已请求停止;当前轮完成后自动封场(进程已死则需强制封存)"}


@runs_router.post("/{run_id}/seal")
def run_seal(run_id: int, who: dict = Depends(require_user)):
    """强制封存:清僵尸场(stopping 卡住/进程已死)。"""
    run = _own_run(run_id, who)
    if run["status"] == "sealed":
        raise HTTPException(409, "场次已封存")
    default_runs().seal(run_id)
    return {"sealed": run_id, "status": "sealed"}


def _own_run(run_id: int, who: dict) -> dict:
    run = next((r for r in default_runs().list(user_id=who["user"]["id"])
                if r["id"] == run_id), None)
    if run is None:
        raise HTTPException(404, "场次不存在(或不属于你)")
    return run


@runs_router.get("/{run_id}/trading")
def run_trading(run_id: int, who: dict = Depends(require_user)):
    """场次交易证据:钱包/持仓是组合当前状态，成交严格按 run_id 隔离。"""
    run = _own_run(run_id, who)
    portfolio = run["portfolio_id"]
    acct = Wallet()
    positions = acct.positions(portfolio)
    fills = [fill for fill in acct.fills(portfolio) if fill.get("run_id") == run_id]
    from trader.core.db import _connect
    with _connect() as conn:
        w = conn.execute(
            "SELECT cash_cents, initial_cents FROM wallets WHERE portfolio_id=%s",
            (portfolio,)).fetchone()
    return {
        "portfolio": portfolio,
        "cash": (w["cash_cents"] / 100) if w else None,
        "initial": (w["initial_cents"] / 100) if w else None,
        "positions": positions,
        "fills": fills,
    }


@runs_router.get("/{run_id}/documents")
def run_documents(run_id: int, who: dict = Depends(require_user)):
    """场次证据链中的文档输入/产出。老场无显式关联时返回空列表。"""
    _own_run(run_id, who)
    return default_documents().for_run(run_id)


@runs_router.get("/{run_id}/documents/{document_id}")
def run_document_content(run_id: int, document_id: int,
                         who: dict = Depends(require_user)):
    """Read evidence content in the run's bound portfolio, including experiments."""
    _own_run(run_id, who)
    row = default_documents().get_for_run(run_id, document_id)
    if row is None:
        raise HTTPException(404, "文档不属于该场次")
    return row


# ── 交易视图(当前账本)──────────────────────────────────

trading_router = APIRouter(prefix="/trading", tags=["trading"])


@trading_router.get("/account")
def account(who: dict = Depends(require_user)):
    acct = Wallet()
    portfolio = default_portfolios().default_for(who["user"]["id"])
    set_context(portfolio, None, who["user"]["id"])
    positions = acct.positions()
    cash = acct.cash()
    from trader.core.market import _fetch_quotes
    try:
        qs = _fetch_quotes("live", [p["code"] for p in positions]) if positions else []
        px = {q["code"]: q["price"] for q in qs}
    except Exception:  # noqa: BLE001
        px = {}
    mv = sum(p["quantity"] * px.get(p["code"], p["avg_cost"]) for p in positions)
    return {"cash": cash / 100, "market_value": mv,
            "asset": (cash / 100) + mv, "positions": positions}


@trading_router.get("/trades")
def trades(who: dict = Depends(require_user)):
    portfolio = default_portfolios().default_for(who["user"]["id"])
    return Wallet().fills(portfolio)


# ── 文档 ────────────────────────────────────────────────

docs_router = APIRouter(prefix="/docs", tags=["docs"])


def _system_portfolio(system: str, who: dict) -> int:
    """把系统工作台数据读绑定到该系统主组合，避免沿用用户的默认系统组合。"""
    if not system:
        return default_portfolios().default_for(who["user"]["id"])
    from trader.core.systems import default_systems
    uid = who["user"]["id"]
    row = default_systems().get(system, user_id=uid)
    if row is None:
        raise HTTPException(404, f"系统不存在:{system}")
    port = default_portfolios().main_of(uid, row["id"])
    if port is None:
        raise HTTPException(404, f"系统 {system} 还没有主组合")
    set_context(port["id"], None, uid)
    return port["id"]


@docs_router.get("")
def list_docs(doc_type: str = "", date: str = "", system: str = "",
              who: dict = Depends(require_user)):
    portfolio = _system_portfolio(system, who)
    return default_documents().list(doc_type or None, date or None, portfolio_id=portfolio)


@docs_router.get("/content")
def doc_content(doc_type: str, name: str = "", date: str = "",
                system: str = "",
                who: dict = Depends(require_user)):
    portfolio = _system_portfolio(system, who)
    c = default_documents().get(doc_type, name=name, trade_date=date,
                                portfolio_id=portfolio)
    if c is None:
        raise HTTPException(404, "文档不存在")
    return {"content": c}


# ── 自选组 ──────────────────────────────────────────────

watch_router = APIRouter(prefix="/watchlists", tags=["watchlists"])


@watch_router.get("")
def list_watchlists(system: str = "", who: dict = Depends(require_user)):
    from trader.core.watchlist import default_watchlists
    portfolio = _system_portfolio(system, who)
    return default_watchlists().list_all(portfolio_id=portfolio)


@watch_router.get("/{name}")
def watchlist_detail(name: str, as_of: str = "", system: str = "",
                     who: dict = Depends(require_user)):
    from trader.core.watchlist import default_watchlists
    portfolio = _system_portfolio(system, who)
    return default_watchlists().get(name, as_of=as_of, portfolio_id=portfolio)
