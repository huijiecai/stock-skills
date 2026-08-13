"""入口:加载 prompt → 建 agent → 跑心跳循环。

跑法:
  cd trading_v2
  ANTHROPIC_API_KEY=sk-xxx uv run python main.py
"""


def main():
    # TODO 积木6:
    # 1. 读 prompt.md(交易规则)
    # 2. 建 Agent(model, system_prompt, deps, tools)
    # 3. 心跳循环:每轮 AI 调 get_heartbeat → 判断 → 可能 trade
    # 4. message_history 累积记忆
    pass


if __name__ == "__main__":
    main()
