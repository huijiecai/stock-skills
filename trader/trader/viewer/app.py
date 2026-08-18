"""viewer 后端:FastAPI 只读路由,把行级袋子里的轮日志/思考流/交易/预期文档组织成页面。

只读红线:这里只有 SELECT(复用 core 的读方法),不 import 任何交易代码路径。
启动:uv run python -m trader.viewer
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import markdown as md_lib
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from trader.core.db import _connect
from trader.core.documents import Documents
from trader.core.ledger import Account
from trader.core.promptver import default_prompt_versions
from trader.core.runs import default_runs
from trader.core.watchlist import Watchlists

_VDIR = Path(__file__).resolve().parent


def _md(text: str | None) -> str:
    """md → HTML(自家 agent 产出的文档,本地单用户工具)。"""
    return md_lib.markdown(text or "", extensions=["tables", "fenced_code"])

templates = Jinja2Templates(directory=str(_VDIR / "templates"))
_static_v = str(max(int(p.stat().st_mtime) for p in (_VDIR / "static").iterdir()))
templates.env.globals["static_v"] = _static_v

app = FastAPI(title="trader viewer(只读)")
app.mount("/static", StaticFiles(directory=str(_VDIR / "static")), name="static")

_MODES = ("live", "replay")


def _watch(mode: str) -> str:
    return f"watch_{mode if mode in _MODES else 'live'}"


def _tr(mode: str) -> str:
    return f"transcript_{mode if mode in _MODES else 'live'}"


# ── 工具函数 ────────────────────────────────────────────

def _iso(date: str) -> str:
    """YYYYMMDD → YYYY-MM-DD(fills.trade_time 是 ISO 格式)。"""
    return f"{date[:4]}-{date[4:6]}-{date[6:8]}" if len(date) == 8 else date


def _round_no(name: str) -> int:
    return int(name[1:]) if name.startswith("r") and name[1:].isdigit() else 0


def _watch_dates(mode: str = "live") -> list[str]:
    """有轮日志的交易日(降序),用于导航。"""
    dates = {d["trade_date"] for d in Documents().list(_watch(mode)) if d["trade_date"]}
    return sorted(dates, reverse=True)


def _transcript(date: str, n: int, mode: str = "live", bag: int = 0) -> dict[str, Any] | None:
    raw = Documents().get(_tr(mode), name=f"r{n}", trade_date=date, bag_id=bag)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001 —— 损坏的思考流显示为无
        return None


def _usage_sum(date: str, mode: str = "live", bag: int = 0) -> dict[str, int]:
    """当日全部轮次的 token 汇总(解析思考流文档头)。"""
    total = {"rounds": 0, "requests": 0, "input_tokens": 0, "output_tokens": 0}
    for d in Documents().list(_tr(mode), date, bag_id=bag):
        t = _transcript(date, _round_no(d["name"] or ""), mode, bag)
        if not t:
            continue
        u = t.get("usage") or {}
        total["rounds"] += 1
        for k in ("requests", "input_tokens", "output_tokens"):
            v = u.get(k)
            if isinstance(v, int):
                total[k] += v
    return total


def _steps(transcript: dict[str, Any]) -> list[dict[str, str]]:
    """把消息流(工具调用/返回/推理)拍平成展示步骤。"""
    steps: list[dict[str, str]] = []
    for msg in transcript.get("messages", []):
        for part in msg.get("parts", []):
            kind = part.get("part_kind", "")
            if kind == "user-prompt":
                steps.append({"kind": "prompt", "title": "📋 轮指令",
                              "body": str(part.get("content", ""))})
            elif kind == "text":
                steps.append({"kind": "text", "title": "💬 AI 推理/输出",
                              "body": str(part.get("content", ""))})
            elif kind == "tool-call":
                args = json.dumps(part.get("args", {}), ensure_ascii=False)
                steps.append({"kind": "call", "title": f"🔧 调用 {part.get('tool_name', '?')}",
                              "body": args})
            elif kind == "tool-return":
                content = part.get("content", "")
                body = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                steps.append({"kind": "ret", "title": f"← 返回 {part.get('tool_name', '?')}",
                              "body": body})
            elif kind == "retry-prompt":
                steps.append({"kind": "retry", "title": "⚠ 重试",
                              "body": str(part.get("content", ""))})
    return steps


def _text_all(t: dict) -> str:
    return "\n".join(str(p.get("content", "")) for m in t.get("messages", [])
                     for p in m.get("parts", []) if p.get("part_kind") == "text")


def _calls_tool(t: dict, name: str) -> bool:
    return any(p.get("part_kind") == "tool-call" and p.get("tool_name") == name
               for m in t.get("messages", []) for p in m.get("parts", []))


def _rule_stats(date: str, mode: str, bag: int = 0) -> dict:
    """规则执行统计:扫当日全部思考流(池评估覆盖/买点纪律/拒绝)。"""
    texts: dict[int, str] = {}
    for d in Documents().list(_tr(mode), date, bag_id=bag):
        r = _round_no(d["name"] or "")
        t = _transcript(date, r, mode, bag)
        if t:
            texts[r] = _text_all(t) or " "
    return {
        "pool": [r for r, t in texts.items() if _calls_tool(_transcript(date, r, mode, bag), "get_watchlist_quotes")],
        "discipline": [r for r, t in texts.items()
                       if any(k in t for k in ("不追", "等回踩", "等回调"))],
        "reject": [r for r, t in texts.items() if "拒绝" in t],
        "n": len(texts),
    }


def _fills_of(date: str, bag: int = 0) -> list[dict]:
    iso = _iso(date)
    return [f for f in Account().fills(bag)
            if (f.get("trade_time") or f.get("created_at", "")).startswith(iso)]


def _fail_flag_of(content: str) -> str:
    """从预期文档正文解析失效标志小节。"""
    try:
        part = content.split("## 失效标志", 1)[1]
        return part.split("##", 1)[0].strip()[:80]
    except Exception:  # noqa: BLE001
        return ""


def _expectation_rows(bag: int = 0) -> list[dict]:
    """预期库视图 = documents('expectation') + 各自选组(平台通用件上的约定层)。"""
    docs = Documents().list("expectation", bag_id=bag)
    wl = Watchlists()
    rows = []
    for d in docs:
        meta = d.get("meta") or {}
        content = Documents().get("expectation", name=d["name"], trade_date=d["trade_date"] or "",
                                  bag_id=bag) or ""
        members = wl.get(meta.get("watchlist") or d["name"], bag_id=bag)
        rows.append({
            "id": d["id"], "name": d["name"],
            "direction": meta.get("direction", ""), "event": meta.get("event", ""),
            "stage": meta.get("stage", "-"), "status": meta.get("status", "-"),
            "pool": [{"code": m["code"], "name": m["name"] or m["code"],
                      "role": (m.get("fields") or {}).get("role", "")} for m in members],
            "pool_count": len(members),
            "fail_flag": _fail_flag_of(content),
        })
    return rows


def _run_metrics(run: dict) -> dict:
    """一场的对比指标:优先读封场 metrics(§8),缺则现场由袋子数据算。"""
    if run.get("metrics"):
        m = run["metrics"]
        m.setdefault("stats", _rule_stats(run["trade_date"] or "", run["kind"], run.get("bag_id") or 0))
        return m
    bag = run.get("bag_id") or 0
    acct = Account()
    date = run["trade_date"] or ""
    fills = _fills_of(date, bag)
    cash = acct.cash(bag) / 100
    cost_value = sum(p["quantity"] * p["avg_cost"] for p in acct.positions(bag))
    usage = _usage_sum(date, run["kind"], bag)
    return {
        "cash": cash, "cost_value": cost_value, "asset": cash + cost_value,
        "initial": 100_000, "pnl": cash + cost_value - 100_000,
        "n_fills": len(fills), "fills": fills,
        "usage": usage, "stats": _rule_stats(date, run["kind"], bag),
    }


# ── 路由 ────────────────────────────────────────────────

@app.get("/")
def index():
    dates = _watch_dates("live")
    return RedirectResponse(f"/day/{dates[0]}" if dates else "/runs")


@app.get("/day/{date}")
def day(request: Request, date: str):
    docs = Documents()
    rounds = sorted(_round_no(d["name"] or "") for d in docs.list(_watch("live"), date))
    t_rounds = {_round_no(d["name"] or "") for d in docs.list(_tr("live"), date)}
    dates = _watch_dates("live")
    idx = dates.index(date) if date in dates else -1
    acct = Account()
    docs_meta = []
    for dt in ("premarket", "close"):
        hits = docs.list(dt, date)
        if hits:
            docs_meta.append({"type": dt, "id": hits[0]["id"], "size": hits[0]["size"]})
    return templates.TemplateResponse(request, "day.html", {
        "date": date, "mode": "live", "docs_meta": docs_meta,
        "stats": _rule_stats(date, "live"),
        "rounds": rounds, "t_rounds": t_rounds,
        "usage": _usage_sum(date, "live"),
        "cash": acct.cash() / 100,
        "positions": acct.positions(),
        "fills": _fills_of(date),
        "expectations": _expectation_rows(0),
        "prev_day": dates[idx + 1] if 0 <= idx < len(dates) - 1 else None,
        "next_day": dates[idx - 1] if idx > 0 else None,
        "qm": "",
        "dates": dates,
    })


@app.get("/round/{date}/{n}")
def round_detail(request: Request, date: str, n: int, mode: str = "live", run: int = 0):
    bag = 0
    if run:
        r = _run_or_404(run)
        bag = (r.get("bag_id") or 0) if r else 0
    log = Documents().get(_watch(mode), name=f"r{n}", trade_date=date, bag_id=bag)
    log_html = _md(log) if log else None
    transcript = _transcript(date, n, mode, bag)
    usage = (transcript or {}).get("usage") or {}
    return templates.TemplateResponse(request, "round.html", {
        "date": date, "n": n, "log_html": log_html, "mode": mode,
        "qm": (f"?mode={mode}&run={run}" if run else (f"?mode={mode}" if mode != "live" else "")),
        "steps": _steps(transcript) if transcript else [],
        "usage": usage,
        "has_transcript": transcript is not None,
    })


@app.get("/trades/{date}")
def trades(request: Request, date: str):
    return templates.TemplateResponse(request, "trades.html", {
        "date": date, "mode": "live", "qm": "",
        "fills": _fills_of(date),
    })


@app.get("/doc/{doc_type}/{date}")
def doc_detail(request: Request, doc_type: str, date: str):
    if doc_type not in ("premarket", "close", "research", "note"):
        return templates.TemplateResponse(request, "doc.html", {
            "doc_type": doc_type, "date": date, "content": None}, status_code=404)
    content = Documents().get(doc_type, trade_date=date)
    return templates.TemplateResponse(request, "doc.html", {
        "doc_type": doc_type, "date": date,
        "content_html": _md(content) if content else None})


# ── 档案袋(场次)───────────────────────────────────────

def _run_or_404(run_id: int):
    for r in default_runs().list():
        if r["id"] == run_id:
            return r
    return None


@app.get("/runs")
def runs_page(request: Request):
    return templates.TemplateResponse(request, "runs.html", {
        "runs": default_runs().list(),
    })


@app.get("/run/{run_id}")
def run_view(request: Request, run_id: int):
    run = _run_or_404(run_id)
    if run is None:
        return templates.TemplateResponse(request, "runs.html",
                                          {"runs": default_runs().list()}, status_code=404)
    bag = run.get("bag_id") or 0
    live = run["kind"] == "live"
    docs = Documents()
    date = run["trade_date"] or ""
    mode = "live" if live else "replay"
    doc_rows = docs.list(_watch(mode), date, bag_id=bag)
    rounds = sorted(_round_no(d["name"] or "") for d in doc_rows)
    t_rounds = {_round_no(d["name"] or "") for d in docs.list(_tr(mode), date, bag_id=bag)}
    acct = Account()
    return templates.TemplateResponse(request, "run.html", {
        "run": run, "date": date, "mode": mode,
        "rounds": rounds, "t_rounds": t_rounds,
        "usage": _usage_sum(date, mode, bag),
        "cash": acct.cash(bag) / 100,
        "positions": acct.positions(bag),
        "fills": _fills_of(date, bag),
        "expectations": _expectation_rows(bag),
        "stats": _rule_stats(date, mode, bag),
        "metrics": run.get("metrics") or {},
    })


@app.get("/compare")
def compare(request: Request, runs: str = ""):
    ids = [int(x) for x in runs.split(",") if x.strip().isdigit()][:2]
    all_runs = default_runs().list()
    picked = [r for r in all_runs if r["id"] in ids]
    if len(picked) < 2:
        return templates.TemplateResponse(request, "runs.html", {
            "runs": all_runs}, status_code=400)
    a, b = picked[0], picked[1]
    try:
        pv_a = json.loads(a["prompt_versions"] or "{}")
        pv_b = json.loads(b["prompt_versions"] or "{}")
    except Exception:  # noqa: BLE001
        pv_a, pv_b = {}, {}
    same_prompt, same_date = pv_a == pv_b, a["trade_date"] == b["trade_date"]
    same_start = (a.get("fingerprint") and a.get("fingerprint") == b.get("fingerprint"))
    if same_prompt and same_date:
        if a["kind"] != b["kind"]:
            verdict = ("同数据日同 prompt 的实盘 vs 模拟——同源复现测试:"
                       "差异来自实时/回放管线差与 LLM 随机性,衡量整条链路保真度")
            attr = "复现测试"
        else:
            verdict = "两场血统完全一致——没有单一变量,无可归因差异"
            attr = "⚠"
    elif same_prompt:
        verdict = f"同 prompt,不同数据日({a['trade_date']} vs {b['trade_date']})——差异归因:行情日"
        attr = "行情日"
    elif same_date:
        verdict = "同数据日同起点,prompt 不同——差异归因:prompt ✓ 干净对比"
        attr = "prompt"
    else:
        verdict = "prompt 与数据日都不同——归因不唯一,仅供参考"
        attr = "⚠ 不唯一"
    if same_start:
        verdict += ";起点指纹一致 ✓"
    return templates.TemplateResponse(request, "compare.html", {
        "a": a, "b": b, "ma": _run_metrics(a), "mb": _run_metrics(b),
        "pv_a": pv_a, "pv_b": pv_b,
        "same_prompt": same_prompt, "same_date": same_date,
        "verdict": verdict, "attr": attr,
    })


@app.get("/prompts")
def prompts(request: Request):
    return templates.TemplateResponse(request, "prompts.html", {
        "prompts": default_prompt_versions().versions(),
    })


@app.get("/prompt/{name}")
def prompt_history(request: Request, name: str):
    rows = default_prompt_versions().versions(name)
    return templates.TemplateResponse(request, "prompt_history.html", {
        "name": name, "rows": rows or [],
    })


@app.get("/prompt/{name}/diff/{v1}/{v2}")
def prompt_diff(request: Request, name: str, v1: int, v2: int):
    import difflib
    pv = default_prompt_versions()
    a, b = pv.get(name, v1), pv.get(name, v2)
    lines = []
    if a is not None and b is not None:
        for ln in difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=2,
                                       fromfile=f"{name} v{v1}", tofile=f"{name} v{v2}"):
            kind = ("hunk" if ln.startswith(("---", "+++", "@@")) else
                    "add" if ln.startswith("+") else
                    "del" if ln.startswith("-") else "ctx")
            lines.append({"kind": kind, "text": ln})
    return templates.TemplateResponse(request, "prompt_diff.html", {
        "name": name, "v1": v1, "v2": v2,
        "lines": lines, "found": a is not None and b is not None,
    })


@app.get("/prompt/{name}/{v}")
def prompt_version(request: Request, name: str, v: int):
    content = default_prompt_versions().get(name, v)
    return templates.TemplateResponse(request, "prompt_version.html", {
        "name": name, "v": v,
        "content_html": _md(content) if content else None,
    })


@app.get("/expectations")
def expectations(request: Request):
    return templates.TemplateResponse(request, "expectations.html", {
        "expectations": _expectation_rows(0),
        "now": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
