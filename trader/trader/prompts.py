"""prompt 外置加载:prompts/ 目录下的 .md 文件,{var} 占位替换。

改 prompt 直接编辑 prompts/*.md,不用动代码。
"""

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load(name: str, **variables: str) -> str:
    """读 prompts/{name}.md;{var} 占位用 variables 替换。
    占位符缺变量时给出明确报错(8/17 曾因 prompt 加了 {date} 而调用方没传,
    KeyError 裸抛烧掉三轮重试)。"""
    path = PROMPTS_DIR / f"{name}.md"
    text = path.read_text(encoding="utf-8")
    if not variables:
        return text
    try:
        return text.format(**variables)
    except KeyError as e:
        raise RuntimeError(
            f"prompt '{name}.md' 有占位符 {e} 但调用方没传"
            f"(传了:{sorted(variables)})——先停进程再改 prompt,或补齐调用方参数"
        ) from None
