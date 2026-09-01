"""core·场次查询服务(平台通用件):轮次概览/单轮详情/实时思考流的组装查询。

API 路由只做归属校验与 HTTP 语义;"从文档与事件反推轮次"的组装逻辑全部在这里
(T1.1 收拢,见 docs/企业级优化路线图.md)。
"""
import json

from trader.core.documents import default_documents
from trader.core.events import default_events


def contract_output_rows(run: dict, linked: list[dict],
                         round_no: int | None = None) -> list[dict]:
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


def rounds_overview(run: dict) -> dict:
    """轮次概览:编号列表 + 哪些有思考流。single 场次返回一条"输出"伪轮。"""
    docs = default_documents()
    run_id = run["id"]
    linked = docs.for_run(run_id)

    if run["kind"] == "single":
        # 单次分析:找 transcript_{stage} 和该日产出文档(报告)
        date = run["trade_date"] or ""
        portfolio = run["portfolio_id"]
        # transcript: doc_type 以 transcript_ 开头且 name 为空(非轮次)
        transcripts = [d for d in linked if d["doc_type"].startswith("transcript_")]
        # 产出文档:非 transcript/watch/chat 类,且在本场次时间范围内
        run_start = run.get("created_at", "")
        outputs = contract_output_rows(run, linked)
        if not outputs:
            outputs = [d for d in linked if d["relation"] == "output"
                       and not d["doc_type"].startswith(("transcript_", "watch_", "chat", "coach"))]
        if not outputs:
            outputs = [d for d in docs.list(trade_date=date, portfolio_id=portfolio)
                       if not d["doc_type"].startswith(("transcript_", "watch_", "chat", "coach"))
                       and (d.get("updated_at") or "") >= run_start]
        return {"rounds": [{"n": 1, "has_transcript": bool(transcripts),
                            "single": True, "outputs": outputs}]}

    # 搜该袋该日的所有 watch_* 轮日志(不限死 watch_live/watch_replay,自定义 log_type 也能找到)
    all_docs = linked or docs.list(trade_date=run["trade_date"],
                                   portfolio_id=run["portfolio_id"])
    stage_outputs = contract_output_rows(run, all_docs)
    logs = []
    for d in stage_outputs:
        name = d.get("name") or ""
        round_no = d.get("round") or (int(name[1:]) if name.startswith("r")
                                      and name[1:].isdigit() else 0)
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
    # 失败轮可见性:轮日志只在成功时落库,连续失败会像"静默死掉"(8/25 DeepSeek
    # 断连 74 分钟,前端毫无感知)。把失败事件聚到对应轮次上——正常轮的零星
    # 失败(偶发重试后成功)不值得展示,只标发生过 2 次以上失败且无轮日志的轮。
    fails: dict[int, dict] = {}
    for ev in default_events().failure_runs(run_id):
        f = fails.setdefault(ev["round"], {"n": ev["round"], "failures": 0,
                                           "last": "", "last_at": ""})
        f["failures"] += 1
        f["last"] = ev["body"]
        f["last_at"] = (ev["created_at"] or "")[11:16]
    for n, f in fails.items():
        if n in ts or any(n == lg[0] for lg in logs):
            continue   # 该轮最终成功(有轮日志)→ 健康重试,不标
        if f["failures"] >= 2:
            rounds.append({"n": n, "time": f["last_at"],
                           "summary": f"连续失败 {f['failures']} 次,最后于 {f['last_at']}",
                           "has_transcript": False,
                           "failed": True, "failures": f["failures"],
                           "error": f["last"],
                           "in_progress": run["status"] == "running"
                           and n == default_events().latest_round(run_id)})
    rounds.sort(key=lambda x: x["n"])
    # 进行中轮:事件表最新轮无轮日志(round_start 已落,watch 还没写)→ 列表顶部可见;
    # 连续失败的最新轮已在上面标过(failed=True),不再重复一条
    if run["status"] == "running":
        ev = default_events()
        rnd = ev.latest_round(run_id)
        if rnd and not any(x["n"] == rnd for x in rounds):
            start = next((s for s in ev.list(run_id, rnd)
                          if s["kind"] == "round_start"), None)
            rounds.append({"n": rnd,
                           "time": (start.get("created_at") or "")[11:16] if start else "",
                           "has_transcript": False, "in_progress": True})
    return {"rounds": rounds}


def round_detail(run: dict, n: int) -> dict:
    """单轮详情:轮日志(md)+ 思考流(拍平步骤)+ usage。
    single 场次:n=1 → 找 transcript_{stage} + 产出文档。"""
    docs = default_documents()
    run_id = run["id"]
    portfolio, date = run["portfolio_id"], run["trade_date"] or ""
    linked = [d for d in docs.for_run(run_id) if d.get("round") in (None, 0, n)]

    log, raw = None, None
    if run["kind"] == "single":
        # 找产出文档(报告)作为"轮日志":排除 chat/watch/transcript,限定本场次时间范围
        run_start = run.get("created_at", "")
        candidates = linked or docs.list(trade_date=date, portfolio_id=portfolio)
        output_rows = contract_output_rows(run, candidates)
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
        for d in contract_output_rows(run, all_docs, n):
            log = (docs.get_for_run(run_id, d["id"]) or {}).get("content")
            break
        for d in all_docs:
            if d["doc_type"].startswith("transcript_") and (d["name"] or "") == f"r{n}":
                raw = docs.get(d["doc_type"], name=f"r{n}", trade_date=date,
                               portfolio_id=portfolio)
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
                                  "body": c if isinstance(c, str)
                                  else json.dumps(c, ensure_ascii=False)})
                elif k == "retry-prompt":
                    steps.append({"kind": "retry", "body": str(p.get("content", ""))})
    return {"n": n, "log_md": log, "steps": steps, "usage": usage}


def live_steps(run: dict) -> dict:
    """实时思考流:当前(最新)轮的事件步骤 + 进行中标记。前端 2 秒轮询。"""
    ev = default_events()
    rnd = ev.latest_round(run["id"])
    if not rnd:
        return {"round": 0, "in_progress": False, "steps": []}
    steps = ev.list(run["id"], rnd)
    return {"round": rnd,
            "in_progress": run["status"] == "running" and ev.round_open(run["id"], rnd),
            "steps": steps}
