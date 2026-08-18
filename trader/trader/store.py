"""存储层垫片:实现已全部在 core/,旧 import 路径继续可用(C1 起过渡,附录 9 记删除时机)。

- 账本 → core.ledger(documents/watchlist/promptver/runs/systems 同理)
- 预期库已数据化(C3):预期=documents(doc_type='expectation'),池=watchlists
"""
from trader.core.db import DATABASE_URL, _connect, schema_exists
from trader.core.documents import Documents
from trader.core.ledger import INITIAL_CASH, Account, AccountError
from trader.core.promptver import PromptVersions
from trader.core.runs import Runs
from trader.core.systems import Systems

# ── 默认单例(工具层共用,读写自动带当前袋子)────────────

_default: Account | None = None
_documents: Documents | None = None
_prompt_versions: PromptVersions | None = None


def default_account() -> Account:
    global _default
    if _default is None:
        _default = Account()
    return _default


def default_documents() -> Documents:
    global _documents
    if _documents is None:
        _documents = Documents()
    return _documents


def default_prompt_versions() -> PromptVersions:
    global _prompt_versions
    if _prompt_versions is None:
        _prompt_versions = PromptVersions()
    return _prompt_versions


def default_runs() -> Runs:
    from trader.core.runs import default_runs as _dr
    return _dr()
