"""第1.6步:理解 Toolset(工具集)和 filtered(动态隐藏)。

跑法:
  cd trading_v2
  ANTHROPIC_API_KEY=sk-xxx uv run python toolset_demo.py

这个文件展示:
1. Toolset = 把多个工具打包成一个箱子
2. filtered = 动态隐藏工具(模拟"14:50后不给出交易工具")

效果:
  第1轮(模拟盘中):AI 能看到 get_price + list_watchlist + trade 三个工具
  第2轮(模拟14:50后):trade 被隐藏,AI 只看到 get_price + list_watchlist
"""
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.messages import ToolCallPart, ToolReturnPart, TextPart


# ── Deps ────────────────────────────────────────────────
@dataclass
class MyDeps:
    watchlist: list[str]
    can_trade: bool       # 是否允许交易(模拟14:50限制)


# ── 工具1:查股价 ────────────────────────────────────────
def get_price(ctx: RunContext[MyDeps], code: str) -> str:
    """查某只股票的实时价格。"""
    import subprocess, json, os
    astock = os.path.join(os.path.dirname(__file__), "../astock/astock")
    result = subprocess.run([astock, "live", "quote", code, "--json"], capture_output=True, text=True)
    data = json.loads(result.stdout)
    if not data:
        return f"{code}: 查不到"
    q = data[0]
    return f"{q['code']} 现价{q['price']} 涨跌{q['change_pct']:+.2f}%"


# ── 工具2:查自选股 ──────────────────────────────────────
def list_watchlist(ctx: RunContext[MyDeps]) -> str:
    """查看当前自选股列表。"""
    return f"自选股: {', '.join(ctx.deps.watchlist)}"


# ── 工具3:下单(模拟) ───────────────────────────────────
def trade(ctx: RunContext[MyDeps], action: str, code: str, quantity: int) -> str:
    """下单交易。action=BUY/SELL, code=6位代码, quantity=股数。"""
    return f"✓ 成交 {action} {code} {quantity}股"


# ── 把工具打包成两个工具集 ──────────────────────────────
# 看盘工具集(get_price + list_watchlist)
看盘 = FunctionToolset()
看盘.add_function(get_price)
看盘.add_function(list_watchlist)

# 交易工具集(trade)——加 filtered:只在 can_trade=True 时可用
交易 = FunctionToolset()
交易.add_function(trade)
# filtered:每轮检查 ctx.deps.can_trade,False 就隐藏整个交易工具集
交易 = 交易.filtered(lambda ctx, tool: ctx.deps.can_trade)


# ── 建大脑 ──────────────────────────────────────────────
model = AnthropicModel(
    "deepseek-v4-flash",
    provider=AnthropicProvider(base_url="https://api.deepseek.com/anthropic"),
)
agent = Agent(
    model,
    system_prompt="你是A股交易助手。有查股价、查自选股、下单三个工具可用。",
    model_settings=ModelSettings({"anthropic_thinking": {"type": "disabled"}}, max_tokens=300),
    deps_type=MyDeps,
)

# 把两个工具集装到 agent 上(agent.toolset 需要工厂函数)
agent.toolset(lambda ctx: 看盘)
agent.toolset(lambda ctx: 交易)


def show_tools(result, prev_len=0):
    """打印 AI 调了什么工具。"""
    msgs = result.all_messages()[prev_len:]
    for msg in msgs:
        for part in getattr(msg, "parts", []):
            if isinstance(part, ToolCallPart):
                print(f"  🔧 AI 调用: {part.tool_name}({part.args})")
            elif isinstance(part, ToolReturnPart):
                print(f"  ← 返回: {str(part.content)[:60]}")


# ── 演示 ────────────────────────────────────────────────
if __name__ == "__main__":
    # 第1轮:模拟盘中(can_trade=True,trade 可用)
    print("=" * 55)
    print("第1轮:模拟盘中(can_trade=True)")
    print("  AI 应该能看到 get_price + list_watchlist + trade")
    print("=" * 55)
    deps1 = MyDeps(watchlist=["000021", "000636"], can_trade=True)
    r1 = agent.run_sync("查深科技(000021)价格,然后买入100股", deps=deps1)
    show_tools(r1)
    print(f"  AI: {r1.output[:100]}")

    print()
    # 第2轮:模拟14:50后(can_trade=False,trade 被隐藏)
    print("=" * 55)
    print("第2轮:模拟14:50后(can_trade=False)")
    print("  AI 应该看不到 trade 工具 —— 想买也买不了")
    print("=" * 55)
    deps2 = MyDeps(watchlist=["000021", "000636"], can_trade=False)
    r2 = agent.run_sync("查风华高科(000636)价格,然后买入100股", deps=deps2)
    show_tools(r2)
    print(f"  AI: {r2.output[:100]}")
