"""core·袋子上下文:进程级当前 bag_id / run_id(engine 注入,store 层读取)。

行级隔离的注入点(实现设计 §7/附录 13):store 方法的 bag_id 参数缺省时读这里,
engine 建场/开场时唯一设置——漏带参数不会串袋,默认值就是"当前袋子"。
"""
from contextvars import ContextVar

_bag_id: ContextVar[int] = ContextVar("bag_id", default=0)
_run_id: ContextVar[int | None] = ContextVar("run_id", default=None)


def set_context(bag_id: int, run_id: int | None = None) -> None:
    """engine 开场调用:本进程接下来的读写都属于这个袋子/这场。"""
    _bag_id.set(bag_id)
    _run_id.set(run_id)


def current_bag() -> int:
    return _bag_id.get()


def current_run() -> int | None:
    return _run_id.get()
