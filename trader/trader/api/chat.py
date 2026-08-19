"""api·场次对话:跑完后跟 AI 讨论结果、优化 prompt。

教练 prompt(_coach)入版本库,用户可改默认行为。
对话持久化到 documents(doc_type='chat', ref_id=run_id),下次打开续聊。
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from trader.api.deps import require_user
from trader.core.context import set_context
from trader.core.documents import default_documents
from trader.core.ledger import default_ledgers
from trader.core.runs import default_runs

router = APIRouter(prefix="/runs", tags=["chat"])


class ChatIn(BaseModel):
    message: str


def _build_context(run: dict, user_id: int) -> str:
    """构建首条注入:原 prompt + 执行结果摘要 + 工具调用摘要。"""
    docs = default_documents()
    bag, date = run["bag_id"], run["trade_date"] or ""
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
            content = pv.latest(pn, user_id)
            if content:
                parts.append(f"### {pn}\n{content[:3000]}")  # 每个 prompt 截 3000 字

    # ② 执行产出(报告/轮日志摘要)
    outputs = []
    for d in docs.list(trade_date=date, bag_id=bag):
        if d["doc_type"].startswith(("transcript_", "watch_", "chat")):
            continue
        content = docs.get(d["doc_type"], name=d["name"] or "",
                           trade_date=date, bag_id=bag)
        if content:
            outputs.append(f"### 产出:{d['doc_type']}\n{content[:2000]}")
    if outputs:
        parts.append("## 执行产出(摘要)\n" + "\n\n".join(outputs[:2]))

    # ③ 工具调用摘要(从 transcript 提取)
    for d in docs.list(trade_date=date, bag_id=bag):
        if not d["doc_type"].startswith("transcript_"):
            continue
        raw = docs.get(d["doc_type"], name=d["name"] or "", trade_date=date, bag_id=bag)
        if not raw:
            continue
        try:
            t = json.loads(raw)
            calls = []
            for msg in t.get("messages", []):
                for p in msg.get("parts", []):
                    if p.get("part_kind") == "tool-call":
                        calls.append(p.get("tool_name", "?"))
            if calls:
                from collections import Counter
                summary = ", ".join(f"{k}×{v}" for k, v in Counter(calls).most_common(10))
                parts.append(f"## AI 调用的工具\n{summary}")
                break  # 只取第一个 transcript
        except Exception:  # noqa: BLE001
            pass

    if not parts:
        parts.append("(本场次没有找到可分析的执行数据)")

    return ("以下是用户刚才执行的场次的完整上下文。\n\n" + "\n\n".join(parts) +
            "\n\n---\n以上是背景。现在用户来跟你讨论这次执行。")


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

    set_context(default_ledgers().default_bag(uid), None, uid)
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

    # 第一轮:注入执行上下文 + 用户消息
    is_first = not history
    if is_first:
        context = _build_context(run, uid)
        user_input = f"{context}\n\n用户: {body.message}"
    else:
        user_input = body.message

    # 调 LLM(教练 prompt)
    from trader.core.promptver import default_prompt_versions
    coach = default_prompt_versions().latest("_coach", uid) or "你是交易系统优化导师。"
    agent = Agent(build_model(), system_prompt=coach,
                  model_settings=ModelSettings({"anthropic_thinking": {"type": "disabled"}},
                                               max_tokens=4000))
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

    # 持久化对话
    history.append({"role": "user", "content": body.message})
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
