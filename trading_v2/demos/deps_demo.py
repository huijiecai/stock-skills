"""第1.5步:理解 Dependencies(依赖注入)。

跑法:
  cd trading_v2
  ANTHROPIC_API_KEY=sk-xxx uv run python deps_demo.py

这个文件展示 Deps 和 Tool 的区别:
- Tool(get_price):AI 调用的函数(AI 知道有这个工具)
- Deps(watchlist):工具内部用的数据(AI 不知道,但工具函数能访问)
"""
from dataclasses import dataclass
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.messages import ToolCallPart, ToolReturnPart, TextPart


# ── Deps:工具内部需要的数据(AI 看不到这个)──────────────
@dataclass
class MyDeps:
    """依赖:工具函数内部需要的数据。AI 不知道这个存在。"""
    watchlist: list[str]   # 自选股列表
    account_name: str      # 账户名


# ── 工具1:查股价(AI 调,内部不用 Deps)─────────────────
def get_price(ctx: RunContext[MyDeps], code: str) -> str:
    """查某只股票的实时价格。"""
    import subprocess, json, os
    astock = os.path.join(os.path.dirname(__file__), "../astock/astock")
    result = subprocess.run([astock, "live", "quote", code, "--json"], capture_output=True, text=True)
    data = json.loads(result.stdout)
    if not data:
        return f"{code}: 查不到"
    q = data[0]
    return f"{q['code']} {q.get('name','')} 现价{q['price']} 涨跌{q['change_pct']:+.2f}%"


# ── 工具2:查自选股(AI 调,内部用 Deps 拿 watchlist)───
def list_watchlist(ctx: RunContext[MyDeps]) -> str:
    """查看当前自选股列表。"""
    # ctx.deps 是注入的依赖 —— AI 不知道这个数据从哪来
    deps = ctx.deps
    return f"自选股({deps.account_name}): {', '.join(deps.watchlist)}"


# ── 建大脑 ──────────────────────────────────────────────
model = AnthropicModel(
    "deepseek-v4-flash",
    provider=AnthropicProvider(base_url="https://api.deepseek.com/anthropic"),
)
agent = Agent(
    model,
    system_prompt="你是A股助手。用户可以查股价(get_price)或查自选股(list_watchlist)。",
    model_settings=ModelSettings({"anthropic_thinking": {"type": "disabled"}}, max_tokens=300),
    deps_type=MyDeps,  # 告诉框架:工具的 ctx.deps 是 MyDeps 类型
)

agent.tool(get_price)
agent.tool(list_watchlist)


# ── 跑一轮 ──────────────────────────────────────────────
if __name__ == "__main__":
    # 注意:这里传 deps —— 工具函数内部通过 ctx.deps 访问
    deps = MyDeps(watchlist=["000021", "000636", "603127"], account_name="paper")

    print("=" * 50)
    print("第1轮:问自选股(AI 调 list_watchlist,工具用 deps 拿列表)")
    print("=" * 50)
    r1 = agent.run_sync("我的自选股有哪些?", deps=deps)
    for msg in r1.all_messages():
        for part in getattr(msg, "parts", []):
            if isinstance(part, ToolCallPart):
                print(f"  🔧 AI 调用: {part.tool_name}({part.args})")
            elif isinstance(part, ToolReturnPart):
                print(f"  ← 返回: {str(part.content)[:60]}")
    print(f"  AI 回答: {r1.output}")

    print()
    print("=" * 50)
    print("第2轮:查第一只自选股的价格(AI 先回忆自选股,再调 get_price)")
    print("=" * 50)
    r2 = agent.run_sync("查我第一只自选股的价格", deps=deps, message_history=r1.all_messages())
    for msg in r2.all_messages()[len(r1.all_messages()):]:
        for part in getattr(msg, "parts", []):
            if isinstance(part, ToolCallPart):
                print(f"  🔧 AI 调用: {part.tool_name}({part.args})")
            elif isinstance(part, ToolReturnPart):
                print(f"  ← 返回: {str(part.content)[:60]}")
    print(f"  AI 回答: {r2.output}")
