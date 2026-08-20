"""core·执行上下文:进程级当前 user_id / portfolio_id / run_id(engine 注入,store 层读取)。

行级多租户的注入点:
- user_id:人和人看不见(知识/系统/prompt/组合的归属轴)
- portfolio_id:组合和组合不串(钱与知识的隔离轴;组合=实盘/模拟/实验)
engine 建场/开场时唯一设置——漏带参数不会串,默认值就是"当前用户/当前组合"。
"""
from contextvars import ContextVar

_user_id: ContextVar[int] = ContextVar("user_id", default=0)
_portfolio_id: ContextVar[int] = ContextVar("portfolio_id", default=0)
_run_id: ContextVar[int | None] = ContextVar("run_id", default=None)


def set_context(portfolio_id: int, run_id: int | None = None, user_id: int = 0) -> None:
    """engine 开场调用:本进程接下来的读写都属于这个用户/组合/这场。"""
    _user_id.set(user_id)
    _portfolio_id.set(portfolio_id)
    _run_id.set(run_id)


def current_user() -> int:
    return _user_id.get()


def current_portfolio() -> int:
    return _portfolio_id.get()


def current_run() -> int | None:
    return _run_id.get()
