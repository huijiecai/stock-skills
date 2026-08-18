"""core·LLM 工厂:agent 用的大脑(模型三件套在 .env,超时教训见 agent.py 史)。

http 客户端必须带超时:8/17 午休期间 socket 静默断开,无超时的阻塞读挂死过整个看盘循环。
"""
import httpx
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from trader.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL


def build_model() -> AnthropicModel:
    """构建模型实例(engine 每次 build_agent 用)。"""
    return AnthropicModel(
        LLM_MODEL,
        provider=AnthropicProvider(
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL,
            http_client=httpx.AsyncClient(
                timeout=httpx.Timeout(connect=15, read=300, write=30, pool=15)
            ),
        ),
    )
