"""api·组合/场次/交易/文档/自选组端点(读为主 + 组合创建;发起场次走子进程)。"""
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from trader.api.deps import require_user
from trader.core import queries, valuation
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
    """组合净值曲线:估值口径唯一实现在 core/valuation(与封场 metrics 同源)。"""
    row = default_portfolios().get(portfolio_id)
    if row is None or row["owner_user"] != who["user"]["id"]:
        raise HTTPException(404, "组合不存在(或不属于你)")
    return valuation.portfolio_curve(portfolio_id)



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
    return queries.rounds_overview(_own_run(run_id, who))


@runs_router.get("/{run_id}/rounds/{n}")
def run_round_detail(run_id: int, n: int, who: dict = Depends(require_user)):
    """单轮详情:轮日志(md)+ 思考流(拍平步骤)+ usage。
    single 场次:n=1 → 找 transcript_{stage} + 产出文档。"""
    return queries.round_detail(_own_run(run_id, who), n)


@runs_router.get("/{run_id}/live")
def run_live_steps(run_id: int, who: dict = Depends(require_user)):
    """实时思考流:当前(最新)轮的事件步骤 + 进行中标记。前端 2 秒轮询。"""
    return queries.live_steps(_own_run(run_id, who))


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
    w = acct.balance(portfolio)
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
