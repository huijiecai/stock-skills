"""api·对话:Run 结论澄清与 System 教练复盘。

两种对话严格分离：
- Run discussion 使用原 Stage 身份和冻结执行上下文，只澄清本场结论；
- System coach 使用独立教练人格，引用 Run/Prompt 来优化交易系统。
"""
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from trader.api.deps import require_user
from trader.core.context import set_context
from trader.core.documents import default_documents
from trader.core.portfolios import default_portfolios
from trader.core.runs import default_runs

router = APIRouter(prefix="/runs", tags=["discussion"])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


def _stage_output_docs(run: dict, docs) -> list[dict]:
    """本场阶段产物:新场认冻结槽位,老场兼容 watch_* 轮日志。"""
    linked = docs.for_run(run["id"])
    slots = set(((run.get("stage_contract") or {}).get("outputs") or {}).keys())
    rows = [d for d in linked if d.get("relation") == "output"
            and d.get("slot") in slots and d.get("stage") == run.get("stage")]
    if rows:
        return rows
    return [d for d in linked if d["doc_type"].startswith("watch_")]


def _prompt_cover(run: dict) -> dict[str, int]:
    """Parse the immutable prompt-version cover stored on a Run."""
    raw = run.get("prompt_versions") or {}
    if isinstance(raw, dict):
        return {str(k): int(v) for k, v in raw.items()}
    try:
        return {str(k): int(v) for k, v in json.loads(raw).items()}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _build_clarification_context(run: dict, user_id: int) -> str:
    """Fallback context for old Runs that do not have a persisted transcript."""
    docs = default_documents()
    parts = [
        "## 原运行边界\n"
        f"Run: #{run['id']}\n"
        f"Stage: {run.get('stage') or '-'}\n"
        f"模式: {run.get('kind') or '-'}\n"
        f"日期: {run.get('trade_date') or '-'}\n"
        f"时钟: {run.get('clock_date') or run.get('clock') or '-'}"
    ]

    instruction = str((run.get("run_inputs") or {}).get("instruction") or "").strip()
    if instruction:
        parts.append(f"## 本次运行请求\n{instruction}")

    # 原 Prompt 必须按 Run 冻结版本读取，不能拿后来修改过的最新版。
    from trader.core.promptver import default_prompt_versions
    pv = default_prompt_versions()
    versions = _prompt_cover(run)
    if versions:
        prompt_parts = []
        for pn, version in list(versions.items())[:3]:
            content = pv.get(run.get("system_id") or 1, pn, version, user_id=user_id)
            if content:
                prompt_parts.append(f"### {pn} v{version}\n{content[:5000]}")
        if prompt_parts:
            parts.append("## 原运行使用的 Prompt\n" + "\n\n".join(prompt_parts))

    # 上游输入和 Stage 输出都经 run_documents 的内容快照读取。
    linked = docs.for_run(run["id"])
    stage_outputs = _stage_output_docs(run, docs)
    inputs = []
    outputs = []
    for d in linked:
        if d["doc_type"].startswith(("transcript_", "watch_", "chat")):
            continue
        content = (docs.get_for_run(run["id"], d["id"]) or {}).get("content")
        if not content:
            continue
        block = f"### {d.get('slot') or d['name'] or d['doc_type']}\n{content[:5000]}"
        (inputs if d.get("relation") == "input" else outputs).append(block)
    if inputs:
        parts.append("## 原 Stage 输入\n" + "\n\n".join(inputs[:4]))
    if outputs:
        parts.append("## 原 Stage 输出\n" + "\n\n".join(outputs[:4]))

    # ③ Agent 各轮总结(轮日志,最近 10 轮截断)——复盘"它每轮怎么想的"
    watch = sorted([d for d in stage_outputs if d.get("round")
                    or ((d.get("name") or "").startswith("r")
                        and (d.get("name") or "r")[1:].isdigit())],
                   key=lambda d: d.get("round") or int(d["name"][1:]))
    if watch:
        seg = [f"### {d['name']}\n{((docs.get_for_run(run['id'], d['id']) or {}).get('content') or '')[:400]}"
               for d in watch[-10:]]
        parts.append("## Agent 各轮总结(最近10轮,每轮截断)\n" + "\n\n".join(seg))

    # ④ 工具调用明细:最近 8 轮 transcript 的 调用参数+返回内容——复盘"它看到了什么数据"
    #    (全局统计另外给;早于 8 轮的只有次数没有内容)
    transcripts = sorted(
        [d for d in linked if d["doc_type"].startswith("transcript_")
         and (d["name"] or "").startswith("r") and (d["name"] or "r")[1:].isdigit()],
        key=lambda d: int(d["name"][1:]))
    from collections import Counter
    all_calls: Counter = Counter()
    for d in transcripts:
        raw = (docs.get_for_run(run["id"], d["id"]) or {}).get("content")
        if not raw:
            continue
        try:
            for msg in json.loads(raw).get("messages", []):
                for p in msg.get("parts", []):
                    if p.get("part_kind") == "tool-call":
                        all_calls[p.get("tool_name", "?")] += 1
        except Exception:  # noqa: BLE001
            pass
    if all_calls:
        parts.append("## Agent 调用的工具(全天统计)\n"
                     + ", ".join(f"{k}×{v}" for k, v in all_calls.most_common(12)))

    budget = 8000   # 工具返回内容总预算(字符)
    segs = []
    for d in transcripts[-8:]:
        raw = (docs.get_for_run(run["id"], d["id"]) or {}).get("content")
        if not raw:
            continue
        try:
            t = json.loads(raw)
        except Exception:  # noqa: BLE001
            continue
        calls = {}
        lines = []
        for msg in t.get("messages", []):
            for p in msg.get("parts", []):
                k = p.get("part_kind", "")
                if k == "tool-call":
                    args = json.dumps(p.get("args", {}), ensure_ascii=False, default=str)
                    calls[p.get("tool_call_id")] = (p.get("tool_name", "?"), args[:120])
                elif k == "tool-return":
                    c = calls.get(p.get("tool_call_id"))
                    name_ = c[0] if c else p.get("tool_name", "?")
                    arg_ = c[1] if c else ""
                    body = p.get("content", "")
                    body = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, default=str)
                    lines.append(f"🔧 {name_}({arg_}) → {body[:600]}")
        if lines:
            segs.append(f"### 第{d['name'][1:]}轮 工具明细(返回截断)\n" + "\n".join(lines))
    if segs:
        joined = "\n\n".join(segs)
        parts.append("## 工具调用明细(最近8轮,含返回内容)\n" + joined[:budget])

    if not parts:
        parts.append("(本场次没有找到可分析的执行数据)")

    return ("以下是你刚才执行该 Stage 时留下的冻结上下文。请继续以原 Stage 的业务角色"
            "澄清结论，不要转为 Prompt 教练。\n\n" + "\n\n".join(parts))


# 人称与建议格式契约(硬前缀,版本库里的 _coach 只管风格,不能覆盖这两条)
_PERSONA = """你是一场 AI 交易系统执行的复盘教练。两条铁律:

【人称】"你"=用户(交易系统的主人,正在问话的人);跑盘执行的是用户的 AI agent,一律称"你的 agent"或"它"——绝不把用户当成执行者训话。例如:用户问"我今天空仓合理吗",你要回答"你的 agent 今天空仓,它的执行显示……"。

【建议格式】给 prompt 修改建议时,代码块必须输出**修改后的完整 prompt 全文**(在原文基础上改,不是只给片段);若只是补充新规则,输出完整原文+新内容。用户会把代码块整段保存为新版本。"""


# ── 教练工作台:多对话隔离,@引用随时注入,自动起标题 ───────

class CoachIn(BaseModel):
    message: str


class CoachArchiveIn(BaseModel):
    archived: bool = True


def _run_brief(run: dict, user_id: int) -> str:
    """单场精简档案:指标 + 所用 prompt 全文 + 最近几轮总结 + 工具返回。"""
    docs = default_documents()
    from trader.core.promptver import default_prompt_versions
    pv = default_prompt_versions()
    portfolio, date = run["portfolio_id"], run["trade_date"] or ""
    parts = [f"### 场次 #{run['id']} {run['slug']}({run['kind']}/{run.get('stage') or '-'} "
             f"{date} {run['status']})"]
    instruction = str((run.get("run_inputs") or {}).get("instruction") or "").strip()
    if instruction:
        parts.append(f"本次任务: {instruction}")
    if run.get("metrics"):
        m = run["metrics"]
        parts.append(f"指标: 收益{m.get('return_pct')}% 回撤{m.get('max_drawdown_pct')}% "
                     f"胜率{m.get('win_rate')}% {m.get('n_fills')}笔 平仓回合{m.get('realized_trades')}")
    versions = _prompt_cover(run)
    for pn, ver in list(versions.items())[:3]:
        content = pv.get(run.get("system_id") or 1, pn, ver, user_id=user_id)
        if content:
            parts.append(f"#### 它用的 prompt「{pn}」v{ver}:\n{content[:2500]}")
    linked = docs.for_run(run["id"])
    watch = sorted([d for d in _stage_output_docs(run, docs) if d.get("round")
                    or ((d.get("name") or "").startswith("r")
                        and (d.get("name") or "r")[1:].isdigit())],
                   key=lambda d: d.get("round") or int(d["name"][1:]))
    for d in watch[-3:]:
        c = (docs.get_for_run(run["id"], d["id"]) or {}).get("content")
        if c:
            parts.append(f"#### {d['name']} 轮总结:\n{c[:300]}")
    transcripts = sorted([d for d in linked if d["doc_type"].startswith("transcript_")
                          and (d["name"] or "").startswith("r") and (d["name"] or "r")[1:].isdigit()],
                         key=lambda d: int(d["name"][1:]))
    budget = 2500
    for d in transcripts[-3:]:
        raw = (docs.get_for_run(run["id"], d["id"]) or {}).get("content")
        if not raw:
            continue
        try:
            t = json.loads(raw)
        except Exception:  # noqa: BLE001
            continue
        calls, lines = {}, []
        for msg in t.get("messages", []):
            for p in msg.get("parts", []):
                k = p.get("part_kind", "")
                if k == "tool-call":
                    calls[p.get("tool_call_id")] = (p.get("tool_name", "?"),
                                                    json.dumps(p.get("args", {}), ensure_ascii=False, default=str)[:100])
                elif k == "tool-return":
                    c = calls.get(p.get("tool_call_id"))
                    body = p.get("content", "")
                    body = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, default=str)
                    lines.append(f"🔧 {(c[0] if c else '?')}({(c[1] if c else '')}) → {body[:400]}")
        if lines and budget > 0:
            seg = "\n".join(lines)[:budget]
            budget -= len(seg)
            parts.append(f"#### {d['name']} 工具返回(截断):\n{seg}")
    return "\n".join(parts)


def _prompt_brief(pn: str, system_id: int, user_id: int) -> str:
    from trader.core.promptver import default_prompt_versions
    c = default_prompt_versions().latest(system_id, pn, user_id=user_id)
    return f"#### 引用的 prompt「{pn}」(当前最新版全文,截断):\n{(c or '')[:3000]}"


def _parse_refs(text: str) -> tuple[list[int], list[str]]:
    """解析消息里的引用:@#场次id 与 @prompt:名字。"""
    run_ids = [int(x) for x in re.findall(r"@#(\d+)", text)]
    prompts = re.findall(r"@prompt:([A-Za-z0-9_\u4e00-\u9fff-]+)", text)
    return run_ids, prompts


def _coach_scope(system: str, who: dict) -> tuple[dict, int]:
    """Resolve a coach conversation to the selected system's main portfolio."""
    from trader.core.systems import default_systems

    uid = who["user"]["id"]
    system_row = default_systems().get(system, user_id=uid)
    if system_row is None:
        raise HTTPException(404, f"系统不存在:{system}")
    portfolio_id = default_portfolios().ensure_main(uid, system_row["id"])
    set_context(portfolio_id, None, uid)
    return system_row, portfolio_id


def _load_conv(docs, system: str, seq: int, portfolio_id: int) -> list:
    raw = docs.get("coach", name=f"{system}-{seq}", trade_date="",
                   portfolio_id=portfolio_id)
    if raw:
        try:
            return json.loads(raw).get("messages", [])
        except Exception:  # noqa: BLE001
            return []
    return []


def _save_conv(docs, system: str, seq: int, messages: list,
               portfolio_id: int) -> None:
    docs.save("coach", json.dumps({"messages": messages}, ensure_ascii=False),
              name=f"{system}-{seq}", trade_date="", portfolio_id=portfolio_id)


def _conversation_doc(docs, system: str, seq: int, portfolio_id: int) -> dict:
    target = f"{system}-{seq}"
    row = next((d for d in docs.list("coach", portfolio_id=portfolio_id)
                if d["name"] == target), None)
    if row is None:
        raise HTTPException(404, "教练对话不存在")
    return row


def _next_conversation_seq(docs, system: str, portfolio_id: int) -> int:
    seqs = []
    for row in docs.list("coach", portfolio_id=portfolio_id):
        if (row["name"] or "").startswith(f"{system}-"):
            try:
                seqs.append(int(row["name"].rsplit("-", 1)[1]))
            except (ValueError, IndexError):
                pass
    return (max(seqs) + 1) if seqs else 1


coach_router = APIRouter(prefix="/systems", tags=["coach"])


@coach_router.get("/{name}/coach/conversations")
def coach_list(name: str, archived: bool = False,
               who: dict = Depends(require_user)):
    """该系统的教练对话列表(新在前的 id/标题/时间)。"""
    _, portfolio_id = _coach_scope(name, who)
    docs = default_documents()
    out = []
    for d in docs.list("coach", portfolio_id=portfolio_id):
        if not (d["name"] or "").startswith(f"{name}-"):
            continue
        try:
            seq = int(d["name"].rsplit("-", 1)[1])
        except (ValueError, IndexError):
            continue
        if not _load_conv(docs, name, seq, portfolio_id):
            continue
        meta = d.get("meta") or {}
        if bool(meta.get("archived")) != archived:
            continue
        out.append({"id": seq, "title": meta.get("title") or d["name"],
                    "archived": bool(meta.get("archived")),
                    "updated_at": d.get("updated_at"), "size": d.get("size")})
    return sorted(out, key=lambda row: row["id"], reverse=True)


@coach_router.post("/{name}/coach/conversations")
def coach_new(name: str, who: dict = Depends(require_user)):
    """新开一个隔离的教练对话,返回对话 id。"""
    _, portfolio_id = _coach_scope(name, who)
    docs = default_documents()
    seq = _next_conversation_seq(docs, name, portfolio_id)
    _save_conv(docs, name, seq, [], portfolio_id)
    return {"id": seq}


@coach_router.get("/{name}/coach/conversations/{seq}")
def coach_get(name: str, seq: int, who: dict = Depends(require_user)):
    """读取某对话的消息。"""
    _, portfolio_id = _coach_scope(name, who)
    docs = default_documents()
    row = _conversation_doc(docs, name, seq, portfolio_id)
    return {"messages": _load_conv(docs, name, seq, portfolio_id),
            "archived": bool((row.get("meta") or {}).get("archived"))}


@coach_router.post("/{name}/coach/conversations/{seq}/archive")
def coach_archive(name: str, seq: int, body: CoachArchiveIn,
                  who: dict = Depends(require_user)):
    """Archive or restore a conversation without losing its history."""
    _, portfolio_id = _coach_scope(name, who)
    docs = default_documents()
    row = _conversation_doc(docs, name, seq, portfolio_id)
    docs.set_meta(row["id"], {"archived": body.archived})
    return {"id": seq, "archived": body.archived}


@coach_router.post("/{name}/coach/conversations/{seq}")
def coach_send(name: str, seq: int, body: CoachIn, who: dict = Depends(require_user)):
    """对话内发消息:解析 @#场次 / @prompt:名字 引用,新引用的档案注入本轮上下文。"""
    from pydantic_ai import Agent
    from pydantic_ai.settings import ModelSettings
    from trader.core.llm import build_model

    uid = who["user"]["id"]
    system_row, portfolio_id = _coach_scope(name, who)
    docs = default_documents()
    if seq == 0:
        seq = _next_conversation_seq(docs, name, portfolio_id)
        history = []
    else:
        row = _conversation_doc(docs, name, seq, portfolio_id)
        if (row.get("meta") or {}).get("archived"):
            raise HTTPException(409, "对话已归档，请先恢复后再继续")
        history = _load_conv(docs, name, seq, portfolio_id)

    # 解析引用;对比历史已注入的(<!--ref:...-->标记),只注入新引用
    run_ids, prompt_names = _parse_refs(body.message)
    injected = set()
    for h in history:
        if h["role"] == "user":
            for m in re.findall(r"<!--ref:([^>]+)-->", h["content"]):
                injected.add(m)
    briefs = []
    mine = {r["id"]: r for r in default_runs().list(system=name, user_id=uid)}
    for rid in dict.fromkeys(run_ids):          # 去重保序
        key = f"#{rid}"
        if key not in injected and rid in mine:
            briefs.append(f"<!--ref:{key}-->\n{_run_brief(mine[rid], uid)}")
    for pn in dict.fromkeys(prompt_names):
        key = f"prompt:{pn}"
        if key not in injected:
            briefs.append(f"<!--ref:{key}-->\n{_prompt_brief(pn, system_row['id'], uid)}")

    first = not history
    prefix = ""
    if first:
        prefix += ("<!--coach:v1-->\n背景:你在跟交易系统的主人讨论他的 AI agent 的执行与系统进化。"
                   "用户消息里的 @#场次id / @prompt:名字 是他显式引用的数据,档案已注入。\n\n")
    if briefs:
        prefix += "(以下为用户本轮新引用的数据档案)\n\n" + "\n\n---\n\n".join(briefs) + "\n\n"
    user_input = f"{prefix}用户: {body.message}" if prefix else body.message

    from trader.core.promptver import default_prompt_versions
    coach_style = default_prompt_versions().latest(None, "_coach", user_id=uid) \
        or "分析直接、结论先行、给可执行的具体修改。"
    agent = Agent(build_model(), system_prompt=_PERSONA + "\n" + coach_style,
                  model_settings=ModelSettings({"anthropic_thinking": {"type": "disabled"}},
                                               max_tokens=8000))
    from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart, TextPart
    msg_history = []
    for h in history:
        if h["role"] == "user":
            msg_history.append(ModelRequest(parts=[UserPromptPart(content=h["content"])]))
        else:
            msg_history.append(ModelResponse(parts=[TextPart(content=h["content"])]))

    result = agent.run_sync(user_input, message_history=msg_history if msg_history else None)
    reply = result.output

    history.append({"role": "user", "content": user_input})
    history.append({"role": "assistant", "content": reply})
    _save_conv(docs, name, seq, history, portfolio_id)

    # 首轮自动起标题(轻量小调用;失败退化用消息截断)
    title = None
    if first:
        try:
            t_agent = Agent(build_model(),
                            system_prompt="为下面的对话起一个不超过12字的中文标题,只输出标题本身。",
                            model_settings=ModelSettings(max_tokens=60))
            title = t_agent.run_sync(f"用户: {body.message[:120]}\n\n助手: {reply[:200]}").output.strip()
            title = re.sub(r'["\'\n]', "", title)[:16]
        except Exception:  # noqa: BLE001
            title = body.message[:12]
        for d in docs.list("coach", portfolio_id=portfolio_id):
            if d["name"] == f"{name}-{seq}":
                docs.set_meta(d["id"], {"title": title or body.message[:12], "system": name})
                break

    return {"id": seq, "reply": reply, "turn": len(history) // 2, "title": title}


_DISCUSSION_CONTRACT = """

【本场继续讨论】你正在延续已经执行完成的 Stage，而不是担任交易系统教练。
- 保持原 Stage 的业务角色、方法和结论口径，直接回答用户对本场结论的追问；
- 只依据消息历史中冻结的原运行上下文，不假装获取最新行情或运行后发生的数据；
- 不评价如何修改 Prompt，不输出 Prompt 优化建议；这属于独立的教练复盘；
- 不执行交易、不修改自选组、不保存或覆盖原 Stage 产物；
- 信息不足时明确指出原运行缺少哪项证据。原 Run 是不可变证据。
"""


def _frozen_system_prompt(run: dict, user_id: int) -> str:
    """Load the exact system-prompt version used by the original Run."""
    from trader.core.promptver import default_prompt_versions
    from trader.core.systems import default_systems

    versions = _prompt_cover(run)
    stage_prompt = str((run.get("stage_contract") or {}).get("prompt") or "")
    system_row = default_systems().get_by_id(run.get("system_id") or 0)
    current_name = str(((system_row or {}).get("manifest") or {}).get("system_prompt") or "")
    candidates = [current_name] + [name for name in versions if name != stage_prompt]
    pv = default_prompt_versions()
    for name in dict.fromkeys(filter(None, candidates)):
        version = versions.get(name)
        if version is None:
            continue
        content = pv.get(run.get("system_id") or 1, name, version, user_id=user_id)
        if content:
            return content
    return "你是该交易系统中负责执行当前 Stage 的分析 Agent。"


def _execution_context(run: dict) -> str:
    """Render the latest model transcript as provider-neutral frozen context."""
    docs = default_documents()
    rows = [d for d in docs.for_run(run["id"])
            if d["doc_type"].startswith("transcript_")]
    rows.sort(key=lambda d: (int(d.get("round") or 0), d.get("linked_at") or "", d["id"]))
    for row in reversed(rows):
        raw = (docs.get_for_run(run["id"], row["id"]) or {}).get("content")
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        blocks = []
        for message in payload.get("messages") or []:
            for part in message.get("parts") or []:
                kind = part.get("part_kind") or ""
                if kind == "user-prompt":
                    blocks.append(f"### 原 Stage 请求\n{part.get('content') or ''}")
                elif kind == "text":
                    blocks.append(f"### 原 Stage Agent 回答\n{part.get('content') or ''}")
                elif kind == "tool-call":
                    args = json.dumps(part.get("args") or {}, ensure_ascii=False, default=str)
                    blocks.append(f"### 原 Stage 工具调用: {part.get('tool_name') or '?'}\n{args}")
                elif kind == "tool-return":
                    content = part.get("content") or ""
                    if not isinstance(content, str):
                        content = json.dumps(content, ensure_ascii=False, default=str)
                    blocks.append(f"### 原 Stage 工具返回: {part.get('tool_name') or '?'}\n{content}")
        if blocks:
            rendered = "## 原运行 model transcript\n\n" + "\n\n".join(blocks)
            if len(rendered) > 60000:
                rendered = rendered[:30000] + "\n\n...(中段过长，平台截断)...\n\n" + rendered[-30000:]
            return rendered
    return ""


def _discussion_payload(run: dict) -> dict:
    docs = default_documents()
    raw = docs.get("chat", name=f"run-{run['id']}",
                   trade_date=run.get("trade_date") or "",
                   portfolio_id=run["portfolio_id"])
    if not raw:
        return {"messages": [], "model_messages": []}
    try:
        payload = json.loads(raw)
        return {
            "messages": payload.get("messages") or [],
            "model_messages": payload.get("model_messages") or [],
        }
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"messages": [], "model_messages": []}


def _discussion_anchor(run: dict) -> dict:
    return {
        "run_id": run["id"],
        "stage": run.get("stage") or "",
        "trade_date": run.get("trade_date") or "",
        "clock": run.get("clock") or "real",
        "mode": "frozen",
    }


@router.post("/{run_id}/chat")
def chat(run_id: int, body: ChatIn, who: dict = Depends(require_user)):
    """Continue the original Stage conversation against its frozen Run context."""
    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelMessagesTypeAdapter
    from pydantic_ai.settings import ModelSettings
    from trader.core.llm import build_model

    uid = who["user"]["id"]
    run = next((r for r in default_runs().list(user_id=uid) if r["id"] == run_id), None)
    if run is None:
        raise HTTPException(404, "场次不存在")
    question = body.message.strip()
    if not question:
        raise HTTPException(400, "追问内容不能为空")

    # Discussion belongs to the Run's portfolio but deliberately has no current
    # run_id: reading/saving chat must never mutate the sealed Run evidence.
    set_context(run["portfolio_id"], None, uid)
    payload = _discussion_payload(run)
    display_history = payload["messages"]
    try:
        model_history = ModelMessagesTypeAdapter.validate_python(payload["model_messages"])
    except (TypeError, ValueError):
        model_history = []

    user_input = question
    if not model_history:
        context = _execution_context(run) or _build_clarification_context(run, uid)
        legacy = ""
        if display_history:
            lines = [f"{('用户' if item.get('role') == 'user' else 'Stage Agent')}: "
                     f"{item.get('content') or ''}" for item in display_history]
            legacy = "\n\n## 已有追问历史\n" + "\n\n".join(lines)
        user_input = f"{context}{legacy}\n\n用户追问：{question}"

    agent = Agent(
        build_model(),
        system_prompt=_frozen_system_prompt(run, uid) + _DISCUSSION_CONTRACT,
        model_settings=ModelSettings({"anthropic_thinking": {"type": "disabled"}},
                                     max_tokens=4000),
    )
    result = agent.run_sync(user_input, message_history=model_history or None)
    reply = result.output
    display_history = [*display_history,
                       {"role": "user", "content": question},
                       {"role": "assistant", "content": reply}]
    model_messages = json.loads(ModelMessagesTypeAdapter.dump_json(result.all_messages()))
    default_documents().save(
        "chat",
        json.dumps({"messages": display_history, "model_messages": model_messages},
                   ensure_ascii=False),
        name=f"run-{run_id}", trade_date=run.get("trade_date") or "",
        ref_id=run_id, portfolio_id=run["portfolio_id"],
        meta={"purpose": "clarify", "context_mode": "frozen"},
    )
    return {"reply": reply, "turn": len(display_history) // 2,
            "anchor": _discussion_anchor(run)}


@router.get("/{run_id}/chat")
def get_chat(run_id: int, who: dict = Depends(require_user)):
    """Get the Run-scoped clarification history and its immutable anchor."""
    uid = who["user"]["id"]
    run = next((r for r in default_runs().list(user_id=uid) if r["id"] == run_id), None)
    if run is None:
        raise HTTPException(404, "场次不存在")
    set_context(run["portfolio_id"], None, uid)
    return {"messages": _discussion_payload(run)["messages"],
            "anchor": _discussion_anchor(run)}
