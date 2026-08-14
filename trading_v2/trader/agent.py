"""大脑:建 Agent + 注册工具。不含任何业务逻辑。

跑法:
  cd trading_v2
  uv run python -m trader.agent     ← API key 在 .env 里,自动读

工具是通用的(RunContext[None] + 参数),任何 agent 能复用。
deps 是交易系统阶段才加的运行环境层,现在不引入。
"""
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.settings import ModelSettings

from trader.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from trader.tools.account import get_account, get_positions
from trader.tools.market import get_block_members, get_block_rank, get_candidates, get_indices, get_kline, get_limit_up, get_quotes
from trader.tools.trading import execute
from trader.tools.watch import scan_market


# ── 建大脑 ──────────────────────────────────────────────
model = AnthropicModel(
    LLM_MODEL,
    provider=AnthropicProvider(api_key=LLM_API_KEY, base_url=LLM_BASE_URL),
)
agent = Agent(
    model,
    system_prompt=(
        "你是A股看盘 agent。每轮会收到时间提示:先调 scan_market 快扫市场,"
        "然后判断——可用工具深查(get_kline/get_block_members 等),"
        "或 execute 交易(整手/主板/T+1 规则),或等待。输出简明判断,不啰嗦。"
    ),
    model_settings=ModelSettings({"anthropic_thinking": {"type": "disabled"}}, max_tokens=300),
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
agent.tool(execute)
agent.tool(scan_market)


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
