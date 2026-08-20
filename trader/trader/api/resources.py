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
    """组合净值曲线:按成交折叠权益(fills 时点,持仓按最近成交价估值),
    起点为初始资金。返回 {initial, points:[{ts, equity, run_id}]}。"""
    from trader.core.db import _connect
    row = default_portfolios().get(portfolio_id)
    if row is None or row["owner_user"] != who["user"]["id"]:
        raise HTTPException(404, "组合不存在(或不属于你)")
    with _connect() as conn:
        w = conn.execute(
            "SELECT cash_cents, initial_cents FROM wallets WHERE portfolio_id=%s",
            (portfolio_id,)).fetchone()
    if w is None:
        return {"initial": None, "points": []}
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
                       "run_id": f["run_id"]})
    return {"initial": w["initial_cents"], "points": points}


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


@runs_router.get("/{run_id}/rounds")
def run_rounds(run_id: int, who: dict = Depends(require_user)):
    """轮次概览:编号列表 + 哪些有思考流。single 场次返回一条"输出"伪轮。"""
    run = next((r for r in default_runs().list(user_id=who["user"]["id"])
                if r["id"] == run_id), None)
    if run is None:
        raise HTTPException(404, "场次不存在")
    docs = default_documents()

    if run["kind"] == "single":
        # 单次分析:找 transcript_{stage} 和该日产出文档(报告)
        date = run["trade_date"] or ""
        portfolio = run["portfolio_id"]
        # transcript: doc_type 以 transcript_ 开头且 name 为空(非轮次)
        transcripts = [d for d in docs.list(trade_date=date, portfolio_id=portfolio)
                       if d["doc_type"].startswith("transcript_") and not (d["name"] or "").startswith("r")]
        # 产出文档:非 transcript/watch/chat 类,且在本场次时间范围内
        run_start = run.get("created_at", "")
        outputs = [d for d in docs.list(trade_date=date, portfolio_id=portfolio)
                   if not d["doc_type"].startswith(("transcript_", "watch_", "chat"))
                   and (d.get("updated_at") or "") >= run_start]
        return {"rounds": [{"n": 1, "has_transcript": bool(transcripts),
                            "single": True, "outputs": outputs}]}

    docs = default_documents()
    # 搜该袋该日的所有 watch_* 轮日志(不限死 watch_live/watch_replay,自定义 log_type 也能找到)
    all_docs = docs.list(trade_date=run["trade_date"], portfolio_id=run["portfolio_id"])
    logs = [(int(d["name"][1:]), (d.get("updated_at") or "")[11:16])
            for d in all_docs
            if d["doc_type"].startswith("watch_")
            and (d["name"] or "").startswith("r") and (d["name"] or "r")[1:].isdigit()]
    logs.sort()
    ts = {int(d["name"][1:]): (d.get("updated_at") or "")[11:16] for d in all_docs
          if d["doc_type"].startswith("transcript_")
          and (d["name"] or "").startswith("r") and (d["name"] or "r")[1:].isdigit()}
    rounds = [{"n": n, "time": t, "has_transcript": n in ts} for n, t in logs]
    # 进行中轮:事件表最新轮无轮日志(round_start 已落,watch 还没写)→ 列表顶部可见
    if run["status"] == "running":
        from trader.core.events import default_events
        ev = default_events()
        rnd = ev.latest_round(run_id)
        if rnd and not any(n == rnd for n, _ in logs):
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

    log, raw = None, None
    if run["kind"] == "single":
        # 找产出文档(报告)作为"轮日志":排除 chat/watch/transcript,限定本场次时间范围
        run_start = run.get("created_at", "")
        for d in docs.list(trade_date=date, portfolio_id=portfolio):
            if (not d["doc_type"].startswith(("transcript_", "watch_", "chat"))
                    and (d.get("updated_at") or "") >= run_start):
                log = docs.get(d["doc_type"], name=d["name"] or "",
                               trade_date=date, portfolio_id=portfolio)
                break
        # 找 transcript(doc_type 以 transcript_ 开头,name 不以 r 开头,本场次时间范围)
        for d in docs.list(trade_date=date, portfolio_id=portfolio):
            if (d["doc_type"].startswith("transcript_") and not (d["name"] or "").startswith("r")
                    and (d.get("updated_at") or "") >= run_start):
                raw = docs.get(d["doc_type"], name=d["name"] or "",
                               trade_date=date, portfolio_id=portfolio)
                break
    else:
        # 搜该袋该日的 watch_* / transcript_*(不限死 live/replay)
        all_docs = docs.list(trade_date=date, portfolio_id=portfolio)
        for d in all_docs:
            if d["doc_type"].startswith("watch_") and (d["name"] or "") == f"r{n}":
                log = docs.get(d["doc_type"], name=f"r{n}", trade_date=date, portfolio_id=portfolio)
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
    """实验组合视图:该场次的现金/持仓/成交明细(按组合隔离)。"""
    run = _own_run(run_id, who)
    portfolio = run["portfolio_id"]
    acct = Wallet()
    positions = acct.positions(portfolio)
    fills = acct.fills(portfolio)
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


@docs_router.get("")
def list_docs(doc_type: str = "", date: str = "", who: dict = Depends(require_user)):
    return default_documents().list(doc_type or None, date or None)


@docs_router.get("/content")
def doc_content(doc_type: str, name: str = "", date: str = "",
                who: dict = Depends(require_user)):
    c = default_documents().get(doc_type, name=name, trade_date=date)
    if c is None:
        raise HTTPException(404, "文档不存在")
    return {"content": c}


# ── 自选组 ──────────────────────────────────────────────

watch_router = APIRouter(prefix="/watchlists", tags=["watchlists"])


@watch_router.get("")
def list_watchlists(who: dict = Depends(require_user)):
    from trader.core.watchlist import default_watchlists
    return default_watchlists().list_all()


@watch_router.get("/{name}")
def watchlist_detail(name: str, as_of: str = "", who: dict = Depends(require_user)):
    from trader.core.watchlist import default_watchlists
    return default_watchlists().get(name, as_of=as_of)
