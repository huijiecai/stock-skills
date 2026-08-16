"""大脑:建 Agent + 注册工具。不含任何业务逻辑。

跑法:
  cd trading_v2
  uv run python -m trader.agent     ← API key 在 .env 里,自动读

工具是通用的(RunContext[None] + 参数),任何 agent 能复用。
deps 是交易系统阶段才加的运行环境层,现在不引入。
"""
from pydantic_ai import Agent
from pydantic_ai.capabilities import NativeTool
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.native_tools import WebSearchTool
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.settings import ModelSettings

from trader.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from trader.prompts import load
from trader.tools.account import get_account, get_positions, get_trades
from trader.tools.docs import get_doc, list_docs, save_doc
from trader.tools.knowledge import add_expectation, add_pool_member, get_expectations, get_pool, remove_pool_member, update_expectation
from trader.tools.market import get_block_members, get_block_rank, get_candidates, get_indices, get_kline, get_limit_up, get_market_summary, get_quotes, get_top_amount
from trader.tools.trading import execute
from trader.tools.watch import get_pool_health, scan_market


# ── 建大脑 ──────────────────────────────────────────────
model = AnthropicModel(
    LLM_MODEL,
    provider=AnthropicProvider(api_key=LLM_API_KEY, base_url=LLM_BASE_URL),
)
agent = Agent(
    model,
    capabilities=[NativeTool(WebSearchTool(max_uses=3))],  # 联网搜索(server-side,和自定义工具混用)
    system_prompt=load("system"),  # prompts/system.md
    model_settings=ModelSettings({"anthropic_thinking": {"type": "disabled"}}, max_tokens=4000),
)

# 把工具装到 agent 上(工具实现都在 tools/ 各域文件里)
agent.tool(get_quotes)
agent.tool(get_indices)
agent.tool(get_kline)
agent.tool(get_block_rank)
agent.tool(get_block_members)
agent.tool(get_candidates)
agent.tool(get_limit_up)
agent.tool(get_positions)
agent.tool(get_account)
agent.tool(get_trades)
agent.tool(execute, retries=3)
agent.tool(scan_market)
agent.tool(get_pool_health)
agent.tool(get_expectations)
agent.tool(get_pool)
agent.tool(add_expectation, retries=3)
agent.tool(add_pool_member, retries=3)
agent.tool(remove_pool_member, retries=3)
agent.tool(update_expectation, retries=3)
agent.tool(get_market_summary)
agent.tool(get_top_amount)
agent.tool(save_doc, retries=3)
agent.tool(get_doc)
agent.tool(list_docs)


# ── 跑一轮 ──────────────────────────────────────────────
if __name__ == "__main__":
    result = agent.run_sync("现在大盘怎么样?查下主流指数。")

    # 打印 AI 这一轮的完整过程(每一步干了什么)
    from pydantic_ai.messages import ToolCallPart, ToolReturnPart, TextPart
    print("=" * 50)
    print("AI 内部过程:")
    print("=" * 50)
    for msg in result.all_messages():
        for part in getattr(msg, "parts", []):
            if isinstance(part, ToolCallPart):
                print(f"  🔧 AI 调用工具: {part.tool_name}({part.args})")
            elif isinstance(part, ToolReturnPart):
                print(f"  ← 工具返回: {str(part.content)[:80]}")
            elif isinstance(part, TextPart):
                print(f"  💬 AI 回答: {part.content[:80]}")
    print("=" * 50)
    print(f"最终输出: {result.output}")
