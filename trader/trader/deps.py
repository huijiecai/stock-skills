"""运行时状态(交易系统阶段启用,现在不用)。

通用工具(get_indices/get_quote 等)用参数,RunContext[None],不依赖 Deps——
任何 agent 能直接复用,这是现在的方式。

等到做交易系统会话(运行环境固定 live/replay + 账户 + 14:50 权限)时,才引入 Deps:
把通用工具适配到运行环境(prepared 或薄包装,从 deps 取参数,而不是 AI 传)。
"""
from dataclasses import dataclass


@dataclass
class Deps:
    mode: str                # "live" | "replay"
    date: str = ""           # "20260812"(replay 用)
    time: str | None = None  # "10:30"(replay 用)
