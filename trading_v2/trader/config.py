"""配置出口:全项目只从这读配置。

原则:
- 所有配置放 .env(项目本地文件,不进 git)
- 无默认值:模型三件套是必须配置,缺失当场报错,不静默运行
- 前缀是用途域(LLM_ = 这个 agent 用的 LLM 配置),不绑供应商
  换供应商只改 .env 的值,变量名和代码都不用动
"""
import os

from dotenv import load_dotenv

load_dotenv()  # 读项目根目录的 .env


def _require(name: str) -> str:
    """必须配置项:缺失当场报错,告诉用户去哪配。"""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"缺少配置 {name}:请在 trading_v2/.env 里配置(参考 .env.example)"
        )
    return value


# ── LLM(三件套强绑定,换供应商改 .env 的值,变量名不动)────
LLM_API_KEY = _require("LLM_API_KEY")
LLM_MODEL = _require("LLM_MODEL")
LLM_BASE_URL = _require("LLM_BASE_URL")
