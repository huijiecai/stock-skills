"""core·袋子上下文:进程级当前 user_id / bag_id / run_id(engine 注入,store 层读取)。

行级多租户的注入点(多用户设计 §4-3):
- user_id:人和人看不见(知识/系统/prompt/账本的归属轴)
- bag_id:袋和袋不串(钱的隔离轴;bag 归属 ledger=持久 或 run=一次性)
engine 建场/开场时唯一设置——漏带参数不会串,默认值就是"当前用户/当前袋子"。
"""
from contextvars import ContextVar

_user_id: ContextVar[int] = ContextVar("user_id", default=0)
_bag_id: ContextVar[int] = ContextVar("bag_id", default=0)
_run_id: ContextVar[int | None] = ContextVar("run_id", default=None)


def set_context(bag_id: int, run_id: int | None = None, user_id: int = 0) -> None:
    """engine 开场调用:本进程接下来的读写都属于这个用户/袋子/这场。"""
    _user_id.set(user_id)
    _bag_id.set(bag_id)
    _run_id.set(run_id)


def current_user() -> int:
    return _user_id.get()


def current_bag() -> int:
    return _bag_id.get()


def current_run() -> int | None:
    return _run_id.get()
