"""api·场次对话:跑完后跟 AI 讨论结果、优化 prompt。

教练 prompt(_coach)入版本库,用户可改默认行为。
对话持久化到 documents(doc_type='chat', ref_id=run_id),下次打开续聊。
"""
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from trader.api.deps import require_user
from trader.core.context import set_context
from trader.core.documents import default_documents
from trader.core.portfolios import default_portfolios
from trader.core.runs import default_runs

router = APIRouter(prefix="/runs", tags=["chat"])

# 上下文版本:升级(注入更多执行数据)后,旧对话续聊时自动补注入新版
_CTX_VERSION = "v2"


class ChatIn(BaseModel):
    message: str


def _build_context(run: dict, user_id: int) -> str:
    """构建首条注入:原 prompt + 执行结果摘要 + 工具调用摘要。"""
    docs = default_documents()
    portfolio, date = run["portfolio_id"], run["trade_date"] or ""
    parts = []

    # ① 原 prompt(从 runs.prompt_versions 知道用了哪些,取内容)
    from trader.core.promptver import default_prompt_versions
    pv = default_prompt_versions()
    try:
        versions = json.loads(run.get("prompt_versions") or "{}")
    except Exception:  # noqa: BLE001
        versions = {}
    prompt_names = list(versions.keys())
    if prompt_names:
        parts.append("## 用户使用的 prompt")
        for pn in prompt_names[:3]:  # 最多取 3 个(太多撑上下文)
            content = pv.latest(run.get("system_id") or 1, pn, user_id=user_id)
            if content:
                parts.append(f"### {pn}\n{content[:3000]}")  # 每个 prompt 截 3000 字

    # ② 执行产出(报告/轮日志摘要)
    outputs = []
    for d in docs.list(trade_date=date, portfolio_id=portfolio):
        if d["doc_type"].startswith(("transcript_", "watch_", "chat")):
            continue
        content = docs.get(d["doc_type"], name=d["name"] or "",
                           trade_date=date, portfolio_id=portfolio)
        if content:
            outputs.append(f"### 产出:{d['doc_type']}\n{content[:2000]}")
    if outputs:
        parts.append("## 执行产出(摘要)\n" + "\n\n".join(outputs[:2]))

    # ③ Agent 各轮总结(轮日志,最近 10 轮截断)——复盘"它每轮怎么想的"
    watch = sorted(
        [d for d in docs.list(trade_date=date, portfolio_id=portfolio)
         if d["doc_type"].startswith("watch_")
         and (d["name"] or "").startswith("r") and (d["name"] or "r")[1:].isdigit()],
        key=lambda d: int(d["name"][1:]))
    if watch:
        seg = [f"### {d['name']}\n{(docs.get(d['doc_type'], name=d['name'], trade_date=date, portfolio_id=portfolio) or '')[:400]}"
               for d in watch[-10:]]
        parts.append("## Agent 各轮总结(最近10轮,每轮截断)\n" + "\n\n".join(seg))

    # ④ 工具调用明细:最近 8 轮 transcript 的 调用参数+返回内容——复盘"它看到了什么数据"
    #    (全局统计另外给;早于 8 轮的只有次数没有内容)
    transcripts = sorted(
        [d for d in docs.list(trade_date=date, portfolio_id=portfolio)
         if d["doc_type"].startswith("transcript_")
         and (d["name"] or "").startswith("r") and (d["name"] or "r")[1:].isdigit()],
        key=lambda d: int(d["name"][1:]))
    from collections import Counter
    all_calls: Counter = Counter()
    for d in transcripts:
        raw = docs.get(d["doc_type"], name=d["name"], trade_date=date, portfolio_id=portfolio)
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
        raw = docs.get(d["doc_type"], name=d["name"], trade_date=date, portfolio_id=portfolio)
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

    return (f"<!--ctx:{_CTX_VERSION}-->\n"
            "以下是用户的 AI 交易 agent 刚才执行的场次数据(执行者是 agent,不是用户本人)。\n\n"
            + "\n\n".join(parts) +
            "\n\n---\n以上是背景。现在用户(交易系统的主人)来跟你讨论他的 agent 这次执行。")


# 人称与建议格式契约(硬前缀,版本库里的 _coach 只管风格,不能覆盖这两条)
_PERSONA = """你是一场 AI 交易系统执行的复盘教练。两条铁律:

【人称】"你"=用户(交易系统的主人,正在问话的人);跑盘执行的是用户的 AI agent,一律称"你的 agent"或"它"——绝不把用户当成执行者训话。例如:用户问"我今天空仓合理吗",你要回答"你的 agent 今天空仓,它的执行显示……"。

【建议格式】给 prompt 修改建议时,代码块必须输出**修改后的完整 prompt 全文**(在原文基础上改,不是只给片段);若只是补充新规则,输出完整原文+新内容。用户会把代码块整段保存为新版本。"""


# ── 教练工作台:多对话隔离,@引用随时注入,自动起标题 ───────

class CoachIn(BaseModel):
    message: str


def _run_brief(run: dict, user_id: int) -> str:
    """单场精简档案:指标 + 所用 prompt 全文 + 最近几轮总结 + 工具返回。"""
    docs = default_documents()
    from trader.core.promptver import default_prompt_versions
    pv = default_prompt_versions()
    portfolio, date = run["portfolio_id"], run["trade_date"] or ""
    parts = [f"### 场次 #{run['id']} {run['slug']}({run['kind']}/{run.get('stage') or '-'} "
             f"{date} {run['status']})"]
    if run.get("metrics"):
        m = run["metrics"]
        parts.append(f"指标: 收益{m.get('return_pct')}% 回撤{m.get('max_drawdown_pct')}% "
                     f"胜率{m.get('win_rate')}% {m.get('n_fills')}笔 平仓回合{m.get('realized_trades')}")
    try:
        versions = json.loads(run.get("prompt_versions") or "{}")
    except Exception:  # noqa: BLE001
        versions = {}
    for pn, ver in list(versions.items())[:3]:
        content = pv.get(run.get("system_id") or 1, pn, ver, user_id=user_id)
        if content:
            parts.append(f"#### 它用的 prompt「{pn}」v{ver}:\n{content[:2500]}")
    watch = sorted([d for d in docs.list(trade_date=date, portfolio_id=portfolio)
                    if d["doc_type"].startswith("watch_")
                    and (d["name"] or "").startswith("r") and (d["name"] or "r")[1:].isdigit()],
                   key=lambda d: int(d["name"][1:]))
    for d in watch[-3:]:
        c = docs.get(d["doc_type"], name=d["name"], trade_date=date, portfolio_id=portfolio)
        if c:
            parts.append(f"#### {d['name']} 轮总结:\n{c[:300]}")
    transcripts = sorted([d for d in docs.list(trade_date=date, portfolio_id=portfolio)
                          if d["doc_type"].startswith("transcript_")
                          and (d["name"] or "").startswith("r") and (d["name"] or "r")[1:].isdigit()],
                         key=lambda d: int(d["name"][1:]))
    budget = 2500
    for d in transcripts[-3:]:
        raw = docs.get(d["doc_type"], name=d["name"], trade_date=date, portfolio_id=portfolio)
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


def _load_conv(docs, system: str, seq: int) -> list:
    raw = docs.get("coach", name=f"{system}-{seq}", trade_date="")
    if raw:
        try:
            return json.loads(raw).get("messages", [])
        except Exception:  # noqa: BLE001
            return []
    return []


def _save_conv(docs, system: str, seq: int, messages: list) -> None:
    docs.save("coach", json.dumps({"messages": messages}, ensure_ascii=False),
              name=f"{system}-{seq}", trade_date="")


coach_router = APIRouter(prefix="/systems", tags=["coach"])


@coach_router.get("/{name}/coach/conversations")
def coach_list(name: str, who: dict = Depends(require_user)):
    """该系统的教练对话列表(新在前的 id/标题/时间)。"""
    set_context(default_portfolios().default_for(who["user"]["id"]), None, who["user"]["id"])
    out = []
    for d in default_documents().list("coach"):
        if not (d["name"] or "").startswith(f"{name}-"):
            continue
        try:
            seq = int(d["name"].rsplit("-", 1)[1])
        except (ValueError, IndexError):
            continue
        out.append({"id": seq, "title": (d.get("meta") or {}).get("title") or d["name"],
                    "updated_at": d.get("updated_at"), "size": d.get("size")})
    return out


@coach_router.post("/{name}/coach/conversations")
def coach_new(name: str, who: dict = Depends(require_user)):
    """新开一个隔离的教练对话,返回对话 id。"""
    uid = who["user"]["id"]
    set_context(default_portfolios().default_for(uid), None, uid)
    docs = default_documents()
    seqs = []
    for d in docs.list("coach"):
        if (d["name"] or "").startswith(f"{name}-"):
            try:
                seqs.append(int(d["name"].rsplit("-", 1)[1]))
            except (ValueError, IndexError):
                pass
    seq = (max(seqs) + 1) if seqs else 1
    _save_conv(docs, name, seq, [])
    return {"id": seq}


@coach_router.get("/{name}/coach/conversations/{seq}")
def coach_get(name: str, seq: int, who: dict = Depends(require_user)):
    """读取某对话的消息。"""
    set_context(default_portfolios().default_for(who["user"]["id"]), None, who["user"]["id"])
    return {"messages": _load_conv(default_documents(), name, seq)}


@coach_router.post("/{name}/coach/conversations/{seq}")
def coach_send(name: str, seq: int, body: CoachIn, who: dict = Depends(require_user)):
    """对话内发消息:解析 @#场次 / @prompt:名字 引用,新引用的档案注入本轮上下文。"""
    from pydantic_ai import Agent
    from pydantic_ai.settings import ModelSettings
    from trader.core.llm import build_model

    uid = who["user"]["id"]
    set_context(default_portfolios().default_for(uid), None, uid)
    from trader.core.systems import default_systems
    system_row = default_systems().get(name, user_id=uid)
    if system_row is None:
        from fastapi import HTTPException
        raise HTTPException(404, f"系统不存在:{name}")
    docs = default_documents()
    history = _load_conv(docs, name, seq)

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
    _save_conv(docs, name, seq, history)

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
        for d in docs.list("coach"):
            if d["name"] == f"{name}-{seq}":
                docs.set_meta(d["id"], {"title": title or body.message[:12], "system": name})
                break

    return {"reply": reply, "turn": len(history) // 2, "title": title}


@router.post("/{run_id}/chat")
def chat(run_id: int, body: ChatIn, who: dict = Depends(require_user)):
    """跟 AI 讨论某场次的执行结果。多轮对话,历史持久化。"""
    from pydantic_ai import Agent
    from pydantic_ai.settings import ModelSettings
    from trader.core.llm import build_model

    uid = who["user"]["id"]
    run = next((r for r in default_runs().list(user_id=uid) if r["id"] == run_id), None)
    if run is None:
        raise HTTPException(404, "场次不存在")

    set_context(default_portfolios().default_for(uid), None, uid)
    docs = default_documents()

    # 加载历史对话(doc_type='chat', name='run-{id}', trade_date=run 日期)
    chat_key = f"run-{run_id}"
    history_raw = docs.get("chat", name=chat_key, trade_date=run["trade_date"] or "")
    history = []
    if history_raw:
        try:
            history = json.loads(history_raw).get("messages", [])
        except Exception:  # noqa: BLE001
            history = []

    # 第一轮:注入执行上下文;续聊:上下文版本升级过则补注入(旧对话下一问即用上新数据)
    first_user = next((h for h in history if h["role"] == "user"), None)
    has_current_ctx = bool(first_user) and f"<!--ctx:{_CTX_VERSION}-->" in first_user["content"]
    if not history or not has_current_ctx:
        prefix = "" if not history else "(系统注:执行数据上下文已升级,以下是补充的完整执行数据,含工具调用返回。后续分析以此为准。)\n\n"
        context = _build_context(run, uid)
        user_input = f"{prefix}{context}\n\n用户: {body.message}"
        stored_user = user_input          # 带上下文入历史,保证后续轮次也能看到
    else:
        user_input = body.message
        stored_user = body.message

    # 调 LLM(教练 prompt:人称契约硬前缀 + 版本库 _coach 风格)
    from trader.core.promptver import default_prompt_versions
    coach_style = default_prompt_versions().latest(None, "_coach", user_id=uid) \
        or "分析直接、结论先行、给可执行的具体修改。"
    agent = Agent(build_model(), system_prompt=_PERSONA + "\n" + coach_style,
                  model_settings=ModelSettings({"anthropic_thinking": {"type": "disabled"}},
                                               max_tokens=8000))
    # 构建 message_history(把历史对话转为 ModelMessage 格式)
    from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart, TextPart
    msg_history = []
    for h in history:
        if h["role"] == "user":
            msg_history.append(ModelRequest(parts=[UserPromptPart(content=h["content"])]))
        else:
            msg_history.append(ModelResponse(parts=[TextPart(content=h["content"])]))

    result = agent.run_sync(user_input, message_history=msg_history if msg_history else None)
    reply = result.output

    # 持久化对话(用户消息存带上下文版,前端显示时剥离)
    history.append({"role": "user", "content": stored_user})
    history.append({"role": "assistant", "content": reply})
    docs.save("chat", json.dumps({"messages": history}, ensure_ascii=False),
              name=chat_key, trade_date=run["trade_date"] or "", ref_id=run_id)

    return {"reply": reply, "turn": len(history) // 2}


@router.get("/{run_id}/chat")
def get_chat(run_id: int, who: dict = Depends(require_user)):
    """获取某场次的讨论历史。"""
    uid = who["user"]["id"]
    run = next((r for r in default_runs().list(user_id=uid) if r["id"] == run_id), None)
    if run is None:
        raise HTTPException(404, "场次不存在")
    raw = default_documents().get("chat", name=f"run-{run_id}",
                                   trade_date=run["trade_date"] or "")
    if raw:
        return json.loads(raw)
    return {"messages": []}
