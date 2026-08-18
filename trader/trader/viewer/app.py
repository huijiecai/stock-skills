"""viewer 后端:FastAPI 只读路由,把 SQLite 里的轮日志/思考流/交易/预期组织成页面。

只读红线:这里只有 SELECT(复用 store 的读方法),不 import 任何交易代码路径。
启动:uv run python -m trader.viewer
"""

import json
import markdown as md_lib
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from trader.store import (Account, Documents, default_account, default_documents,
                           default_expectations, default_prompt_versions, default_runs, schema_exists)

_VDIR = Path(__file__).resolve().parent


def _md(text: str | None) -> str:
    """md → HTML(自家 agent 产出的文档,本地单用户工具)。"""
    return md_lib.markdown(text or "", extensions=["tables", "fenced_code"])
templates = Jinja2Templates(directory=str(_VDIR / "templates"))

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
    dates = {d["trade_date"] for d in default_documents().list(_watch(mode)) if d["trade_date"]}
    return sorted(dates, reverse=True)


def _bag_docs(schema: str | None = None) -> Documents:
    return Documents(schema=schema) if schema else default_documents()


def _transcript(date: str, n: int, mode: str = "live", schema: str | None = None) -> dict[str, Any] | None:
    raw = _bag_docs(schema).get(_tr(mode), name=f"r{n}", trade_date=date)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001 —— 损坏的思考流显示为无
        return None


def _usage_sum(date: str, mode: str = "live") -> dict[str, int]:
    """当日全部轮次的 token 汇总(解析思考流文档头)。"""
    total = {"rounds": 0, "requests": 0, "input_tokens": 0, "output_tokens": 0}
    for d in default_documents().list(_tr(mode), date):
        t = _transcript(date, _round_no(d["name"] or ""), mode)
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


def _replay_account(date: str) -> Account | None:
    """回放账户(PG schema replay_{date});schema 不存在(没跑过回放)返回 None。"""
    return Account(schema=f"replay_{date}") if schema_exists(f"replay_{date}") else None


def _text_all(t: dict) -> str:
    return "\n".join(str(p.get("content", "")) for m in t.get("messages", [])
                      for p in m.get("parts", []) if p.get("part_kind") == "text")


def _calls_tool(t: dict, name: str) -> bool:
    return any(p.get("part_kind") == "tool-call" and p.get("tool_name") == name
               for m in t.get("messages", []) for p in m.get("parts", []))


def _usage_sum_schema(docs: Documents, date: str, tr_type: str) -> dict:
    total = {"rounds": 0, "requests": 0, "input_tokens": 0, "output_tokens": 0}
    for d in docs.list(tr_type, date):
        try:
            t = json.loads(docs.get(tr_type, name=d["name"], trade_date=date) or "")
        except Exception:  # noqa: BLE001
            continue
        u = t.get("usage") or {}
        total["rounds"] += 1
        for k in ("requests", "input_tokens", "output_tokens"):
            v = u.get(k)
            if isinstance(v, int):
                total[k] += v
    return total


def _rule_stats_schema(docs: Documents, date: str, tr_type: str) -> dict:
    """袋内规则执行统计(直接解析袋内思考流 JSON)。"""
    pool, discipline, reject = [], [], []
    n = 0
    for d in docs.list(tr_type, date):
        r = _round_no(d["name"] or "")
        try:
            t = json.loads(docs.get(tr_type, name=d["name"], trade_date=date) or "")
        except Exception:  # noqa: BLE001
            continue
        if not t:
            continue
        n += 1
        if _calls_tool(t, "get_pool_health"):
            pool.append(r)
        text = _text_all(t) or " "
        if any(k in text for k in ("不追", "等回踩", "等回调")):
            discipline.append(r)
        if "拒绝" in text:
            reject.append(r)
    return {"pool": pool, "discipline": discipline, "reject": reject, "n": n}


def _rule_stats(date: str, mode: str) -> dict:
    """规则执行统计:扫当日全部思考流(池评估覆盖/买点纪律/拒绝)。"""
    texts: dict[int, str] = {}
    for d in default_documents().list(_tr(mode), date):
        r = _round_no(d["name"] or "")
        t = _transcript(date, r, mode)
        if t:
            texts[r] = _text_all(t) or " "
    return {
        "pool": [r for r, t in texts.items() if _calls_tool(_transcript(date, r, mode), "get_pool_health")],
        "discipline": [r for r, t in texts.items()
                       if any(k in t for k in ("不追", "等回踩", "等回调"))],
        "reject": [r for r, t in texts.items() if "拒绝" in t],
        "n": len(texts),
    }


def _fills_of(date: str, mode: str = "live") -> list[dict]:
    iso = _iso(date)
    acct = _replay_account(date) if mode == "replay" else default_account()
    if acct is None:
        return []
    return [f for f in acct.fills()
            if (f.get("trade_time") or f.get("created_at", "")).startswith(iso)]


# ── 路由 ────────────────────────────────────────────────

@app.get("/")
def index(mode: str = "live"):
    dates = _watch_dates(mode)
    base = f"/day/{dates[0]}" if dates else "/day/00000000"
    return RedirectResponse(base + (f"?mode={mode}" if mode != "live" else ""))


@app.get("/day/{date}")
def day(request: Request, date: str, mode: str = "live"):
    docs = default_documents().list(_watch(mode), date)
    rounds = sorted(_round_no(d["name"] or "") for d in docs)          # 正序:r1 → rN
    t_rounds = {_round_no(d["name"] or "")                              # 有思考流的轮(可点开看全过程)
                for d in default_documents().list(_tr(mode), date)}
    dates = _watch_dates(mode)
    idx = dates.index(date) if date in dates else -1
    acct = _replay_account(date) if mode == "replay" else default_account()
    positions = acct.positions() if acct else []
    fills = _fills_of(date, mode)
    docs_store = default_documents()
    docs_meta = []
    for dt in ("premarket", "close"):
        hits = docs_store.list(dt, date)
        if hits:
            docs_meta.append({"type": dt, "id": hits[0]["id"], "size": hits[0]["size"]})
    return templates.TemplateResponse(request, "day.html", {
        "date": date, "mode": mode, "docs_meta": docs_meta,
        "stats": _rule_stats(date, mode),
        "rounds": rounds, "t_rounds": t_rounds,
        "usage": _usage_sum(date, mode),
        "cash": (acct.cash() / 100) if acct else 0.0,
        "positions": positions,
        "fills": fills,
        "expectations": default_expectations().get_all(),
        "prev_day": dates[idx + 1] if 0 <= idx < len(dates) - 1 else None,
        "next_day": dates[idx - 1] if idx > 0 else None,
        "qm": f"?mode={mode}" if mode != "live" else "",
        "dates": dates,
    })


@app.get("/round/{date}/{n}")
def round_detail(request: Request, date: str, n: int, mode: str = "live"):
    log = default_documents().get(_watch(mode), name=f"r{n}", trade_date=date)
    log_html = _md(log) if log else None
    transcript = _transcript(date, n, mode)
    usage = (transcript or {}).get("usage") or {}
    return templates.TemplateResponse(request, "round.html", {
        "date": date, "n": n, "log_html": log_html, "mode": mode,
        "qm": f"?mode={mode}" if mode != "live" else "",
        "steps": _steps(transcript) if transcript else [],
        "usage": usage,
        "has_transcript": transcript is not None,
    })


@app.get("/trades/{date}")
def trades(request: Request, date: str, mode: str = "live"):
    return templates.TemplateResponse(request, "trades.html", {
        "date": date, "mode": mode,
        "qm": f"?mode={mode}" if mode != "live" else "",
        "fills": _fills_of(date, mode),
    })


@app.get("/doc/{doc_type}/{date}")
def doc_detail(request: Request, doc_type: str, date: str):
    if doc_type not in ("premarket", "close", "research", "note"):
        return templates.TemplateResponse(request, "doc.html", {
            "doc_type": doc_type, "date": date, "content": None}, status_code=404)
    content = default_documents().get(doc_type, trade_date=date)
    return templates.TemplateResponse(request, "doc.html", {
        "doc_type": doc_type, "date": date,
        "content_html": _md(content) if content else None})


# ── prompt 版本库 ───────────────────────────────────────



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
    schema = run["schema_name"]
    live = run["kind"] == "live"
    docs = _bag_docs(schema)
    date = run["trade_date"] or ""
    watch = "watch_live" if live else "watch_replay"
    tr = "transcript_live" if live else "transcript_replay"
    doc_rows = docs.list(watch, date)
    rounds = sorted(_round_no(d["name"] or "") for d in doc_rows)
    acct = default_account() if live else Account(schema=schema)
    iso = _iso(date)
    fills = [f for f in acct.fills()
             if (f.get("trade_time") or f.get("created_at", "")).startswith(iso)]         if not live else _fills_of(date, "live")
    t_rounds = {_round_no(d["name"] or "") for d in docs.list(tr, date)}
    exps = (default_expectations() if live
            else __import__("trader.store", fromlist=["Expectations"]).Expectations(schema=schema))
    return templates.TemplateResponse(request, "run.html", {
        "run": run, "date": date, "mode": run["kind"],
        "rounds": rounds, "t_rounds": t_rounds,
        "usage": _usage_sum_schema(docs, date, tr),
        "cash": acct.cash() / 100,
        "positions": acct.positions(),
        "fills": fills,
        "expectations": exps.get_all(),
        "stats": _rule_stats_schema(docs, date, tr),
    })




def _run_metrics(run: dict) -> dict:
    """一场的对比指标(成本法):已实现盈亏/现金/持仓成本/交易/轮次/统计/token。"""
    live = run["kind"] == "live"
    schema = run["schema_name"]
    acct = default_account() if live else Account(schema=schema)
    docs = _bag_docs(schema)
    date = run["trade_date"] or ""
    tr_type = "transcript_live" if live else "transcript_replay"
    fills = _fills_of(date, "live") if live else [
        f for f in acct.fills()
        if (f.get("trade_time") or f.get("created_at", "")).startswith(_iso(date))]
    cash = acct.cash() / 100
    cost_value = sum(p["quantity"] * p["avg_cost"] for p in acct.positions())
    usage = _usage_sum_schema(docs, date, tr_type)
    stats = _rule_stats_schema(docs, date,
                               "watch_live" if live else "watch_replay")
    rounds = [d for d in docs.list("watch_live" if live else "watch_replay", date)]
    return {
        "cash": cash, "cost_value": cost_value,
        "asset": cash + cost_value, "initial": 100_000,
        "pnl": cash + cost_value - 100_000,
        "n_fills": len(fills), "fills": fills,
        "n_rounds": len(rounds), "usage": usage, "stats": stats,
    }


@app.get("/compare")
def compare(request: Request, runs: str = ""):
    ids = [int(x) for x in runs.split(",") if x.strip().isdigit()][:2]
    all_runs = default_runs().list()
    picked = [r for r in all_runs if r["id"] in ids]
    if len(picked) < 2:
        return templates.TemplateResponse(request, "runs.html", {
            "runs": all_runs}, status_code=400)
    a, b = picked[0], picked[1]
    import json as _json
    try:
        pv_a = _json.loads(a["prompt_versions"] or "{}")
        pv_b = _json.loads(b["prompt_versions"] or "{}")
    except Exception:  # noqa: BLE001
        pv_a, pv_b = {}, {}
    same_prompt, same_date = pv_a == pv_b, a["trade_date"] == b["trade_date"]
    if same_prompt and same_date:
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
    store = default_expectations()
    enriched = []
    for e in store.get_all():
        detail = store.get(e["id"]) or {}
        enriched.append({**e, "pool": detail.get("pool", [])})
    return templates.TemplateResponse(request, "expectations.html", {
        "expectations": enriched,
        "now": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
