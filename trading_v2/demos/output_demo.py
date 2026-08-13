"""第1.7步:理解 output_type(结构化输出)。

跑法:
  cd trading_v2
  ANTHROPIC_API_KEY=sk-xxx uv run python output_demo.py

这个文件展示 output_type:
- 默认:AI 返回文本(string),你要自己解析
- output_type:AI 返回 Pydantic 模型,框架自动校验+重试

效果:
  不用 output_type: AI 说"我觉得应该卖出深科技200股"  ← 文本,你要自己解析
  用 output_type:    AI 返回 Decision(action="SELL", code="000021", quantity=200)  ← 结构化,直接用
"""
from pydantic import BaseModel, Field
from typing import Literal
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.settings import ModelSettings


# ── 定义"决策"的结构 ────────────────────────────────────
class Decision(BaseModel):
    """AI 必须返回这个结构,不能随便说话。"""
    action: Literal["BUY", "SELL", "WAIT"]    # 只能是这三个值
    code: str = Field(description="6位股票代码")  # 必须有
    quantity: int = Field(description="股数,100的倍数")  # 必须有
    reason: str = Field(description="决策理由")  # 必须有


# ── 建大脑 ──────────────────────────────────────────────
model = AnthropicModel(
    "deepseek-v4-flash",
    provider=AnthropicProvider(base_url="https://api.deepseek.com/anthropic"),
)

# 方式1:默认(返回文本)
agent_text = Agent(
    model,
    system_prompt="你是A股交易员。用户给你市场信息,你做判断。",
    model_settings=ModelSettings({"anthropic_thinking": {"type": "disabled"}}, max_tokens=200),
)

# 方式2:output_type(返回结构化)
agent_structured = Agent(
    model,
    system_prompt="你是A股交易员。用户给你市场信息,你做判断。",
    output_type=Decision,  # ← 关键:要求 AI 返回 Decision 结构
    model_settings=ModelSettings({"anthropic_thinking": {"type": "disabled"}}, max_tokens=200),
)


# ── 演示 ────────────────────────────────────────────────
if __name__ == "__main__":
    market_info = "深科技(000021) 现价39.55 跌-1.98%,存储芯片板块全线下跌,资金撤退明显。"

    print("=" * 55)
    print("方式1:不用 output_type(AI 返回文本)")
    print("=" * 55)
    r1 = agent_text.run_sync(f"市场信息:{market_info}\n你判断怎么操作?")
    print(f"  AI 返回(文本): {r1.output}")
    print(f"  类型: {type(r1.output).__name__}")
    print(f"  问题: 你要自己从文字里解析'卖什么卖多少'")

    print()
    print("=" * 55)
    print("方式2:用 output_type=Decision(AI 返回结构化)")
    print("=" * 55)
    r2 = agent_structured.run_sync(f"市场信息:{market_info}\n你判断怎么操作?")
    decision = r2.output
    print(f"  AI 返回(Decision 对象):")
    print(f"    action   = {decision.action}     ← 直接用,不用解析")
    print(f"    code     = {decision.code}       ← 直接用")
    print(f"    quantity = {decision.quantity}    ← 直接用")
    print(f"    reason   = {decision.reason}")
    print(f"  类型: {type(decision).__name__}")
    print(f"  好处: 可以直接 if decision.action == 'SELL': 执行交易")
