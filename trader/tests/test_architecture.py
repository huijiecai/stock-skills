"""架构红线护栏(源码静态扫描,不依赖 DB 状态)。

红线(企业级优化路线图 T1.1/T1.2):
- 数据访问收拢在 trader/core/ 存储层;api/ 等上层模块禁止出现
  _connect / psycopg / psycopg_pool——违者在这里爆,评审前先过不了 CI。
- core 内只有 store 可直连 DB;engine.py 是领域服务不是 store(T1.1 已清零),
  单独点名守住。
- 迁移脚本(scripts/)是一次性运维工具,不在红线内;测试自身直连 DB 也允许。

docstring 统一格式:<场景>:<验证点>
"""
import re
from pathlib import Path

TOOL = "arch"

_PKG = Path(__file__).resolve().parents[1] / "trader"  # trader 包根(非项目根)
_PATTERN = re.compile(r"(_connect\(|import psycopg\b|from psycopg\b|psycopg_pool)")


def _scan(path: Path) -> list[str]:
    rel = path.relative_to(_PKG.parent)
    return [f"{rel}:{n}: {line.strip()}"
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if _PATTERN.search(line)]


def test_no_direct_db_access_outside_core():
    """架构红线:core 之外的包内源码禁止 _connect/psycopg 直查 DB。"""
    bad = []
    for path in sorted(_PKG.rglob("*.py")):
        if "core" in path.relative_to(_PKG).parts or "__pycache__" in path.parts:
            continue  # trader/core/ 是存储层,直连 DB 合法(规则二单独守 engine)
        bad += _scan(path)
    assert not bad, "core 之外出现直查 DB(应收拢到 core 存储层):\n" + "\n".join(bad)
    print("  → trader/api 等上层模块零 _connect/psycopg 引用")


def test_engine_is_not_a_store():
    """架构红线:engine 是领域服务(T1.1 抽层对象),禁止重新长回 _connect/psycopg。"""
    bad = _scan(_PKG / "core" / "engine.py")
    assert not bad, "engine.py 重新直连 DB:\n" + "\n".join(bad)
    print("  → core/engine.py 零 _connect/psycopg 引用")
