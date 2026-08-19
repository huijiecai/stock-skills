"""api·账本/场次/交易/文档/自选组端点(读为主 + 账本创建;发起场次走子进程)。"""
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from trader.api.deps import require_user
from trader.core.context import set_context
from trader.core.documents import default_documents
from trader.core.ledger import Account, default_ledgers
from trader.core.runs import default_runs

router = APIRouter(prefix="/ledgers", tags=["ledgers"])


class LedgerIn(BaseModel):
    name: str
    kind: str = "paper"


@router.get("")
def list_ledgers(who: dict = Depends(require_user)):
    return default_ledgers().list(who["user"]["id"])


@router.post("")
def create_ledger(body: LedgerIn, who: dict = Depends(require_user)):
    if body.kind == "live" and not who["user"].get("is_admin"):
        raise HTTPException(403, "实盘账本仅管理员可开(内测期)")
    try:
        return default_ledgers().create(who["user"]["id"], body.name, body.kind)
    except ValueError as e:
        raise HTTPException(409, str(e))


# ── 场次 ────────────────────────────────────────────────

runs_router = APIRouter(prefix="/runs", tags=["runs"])


class ReplayIn(BaseModel):
    system: str
    date: str
    tag: str = ""
    interval: int = 5
    max_rounds: int | None = None


@runs_router.get("")
def list_runs(kind: str = "", date: str = "", who: dict = Depends(require_user)):
    return default_runs().list(kind=kind or None, trade_date=date or None,
                               user_id=who["user"]["id"])


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
        subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
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
        bag = run["bag_id"]
        # transcript: doc_type 以 transcript_ 开头且 name 为空(非轮次)
        transcripts = [d for d in docs.list(trade_date=date, bag_id=bag)
                       if d["doc_type"].startswith("transcript_") and not (d["name"] or "").startswith("r")]
        # 产出文档:非 transcript/watch 类
        outputs = [d for d in docs.list(trade_date=date, bag_id=bag)
                   if not d["doc_type"].startswith(("transcript_", "watch_"))]
        return {"rounds": [{"n": 1, "has_transcript": bool(transcripts),
                            "single": True, "outputs": outputs}]}

    mode = "live" if run["kind"] == "live" else "replay"
    docs = default_documents()
    logs = sorted((int(d["name"][1:]) for d in docs.list(f"watch_{mode}", run["trade_date"],
                                                          bag_id=run["bag_id"])
                   if d["name"].startswith("r") and d["name"][1:].isdigit()))
    ts = {int(d["name"][1:]) for d in docs.list(f"transcript_{mode}", run["trade_date"],
                                                bag_id=run["bag_id"])
          if d["name"].startswith("r") and d["name"][1:].isdigit()}
    return {"rounds": [{"n": n, "has_transcript": n in ts} for n in logs]}


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
    bag, date = run["bag_id"], run["trade_date"] or ""

    log, raw = None, None
    if run["kind"] == "single":
        # 找产出文档(报告)作为"轮日志"
        for d in docs.list(trade_date=date, bag_id=bag):
            if not d["doc_type"].startswith(("transcript_", "watch_")):
                log = docs.get(d["doc_type"], name=d["name"] or "",
                               trade_date=date, bag_id=bag)
                break
        # 找 transcript(doc_type 以 transcript_ 开头,name 不以 r 开头)
        for d in docs.list(trade_date=date, bag_id=bag):
            if d["doc_type"].startswith("transcript_") and not (d["name"] or "").startswith("r"):
                raw = docs.get(d["doc_type"], name=d["name"] or "",
                               trade_date=date, bag_id=bag)
                break
    else:
        mode = "live" if run["kind"] == "live" else "replay"
        log = docs.get(f"watch_{mode}", name=f"r{n}", trade_date=date, bag_id=bag)
        raw = docs.get(f"transcript_{mode}", name=f"r{n}", trade_date=date, bag_id=bag)
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


@runs_router.get("/{run_id}/trading")
def run_trading(run_id: int, who: dict = Depends(require_user)):
    """沙盒账本视图:该场次的现金/持仓/成交明细(按 bag 隔离)。"""
    run = next((r for r in default_runs().list(user_id=who["user"]["id"])
                if r["id"] == run_id), None)
    if run is None:
        raise HTTPException(404, "场次不存在")
    bag = run["bag_id"]
    acct = Account()
    positions = acct.positions(bag)
    fills = acct.fills(bag)
    from trader.core.db import _connect
    with _connect() as conn:
        w = conn.execute("SELECT cash_cents, initial_cents FROM wallets WHERE bag_id=%s",
                         (bag,)).fetchone()
    return {
        "bag": bag,
        "cash": (w["cash_cents"] / 100) if w else None,
        "initial": (w["initial_cents"] / 100) if w else None,
        "positions": positions,
        "fills": fills,
    }


# ── 交易视图(当前账本)──────────────────────────────────

trading_router = APIRouter(prefix="/trading", tags=["trading"])


@trading_router.get("/account")
def account(who: dict = Depends(require_user)):
    acct = Account()
    bag = default_ledgers().default_bag(who["user"]["id"])
    set_context(bag, None, who["user"]["id"])
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
    bag = default_ledgers().default_bag(who["user"]["id"])
    return Account().fills(bag)


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
