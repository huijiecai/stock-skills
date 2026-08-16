"""prompt 外置加载:prompts/ 目录下的 .md 文件,{var} 占位替换。

改 prompt 直接编辑 prompts/*.md,不用动代码。
"""

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load(name: str, **variables: str) -> str:
    """读 prompts/{name}.md;{var} 占位用 variables 替换。"""
    path = PROMPTS_DIR / f"{name}.md"
    text = path.read_text(encoding="utf-8")
    return text.format(**variables) if variables else text
