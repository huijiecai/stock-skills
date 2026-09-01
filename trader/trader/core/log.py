"""core·统一诊断日志(只输出控制台,不写文件——项目规约)。

入口:`log = get_logger(__name__)`,然后 log.info/warning(...)。
上下文字段自动注入,业务代码不用手传:
- run:engine 建场 set_context 的 run_id
- r:每轮 set_current_round 的轮号
- trace:API 请求的 traceId(信封中间件设置,与响应信封/X-Trace-Id 同值,对账用)

格式:08-24 15:00:01 I engine [run=457 r3 trace=ab12cd34] 消息
无上下文的记录自动省略 [] 段。级别用 TRADER_LOG_LEVEL 调(默认 INFO)。

边界:CLI 的数据输出(runner 列表/prompts diff/engine 的 AI 轮输出与分隔横幅)
是用户界面,保持 print 不走日志——诊断与界面的分界决策见 docs/adr/0013。
"""
import logging
import os
import sys
import threading
from contextvars import ContextVar

_trace_id: ContextVar[str] = ContextVar("log_trace_id", default="")

_config_lock = threading.Lock()
_configured = False


def set_trace_id(trace_id: str) -> None:
    """API 信封中间件调用:本请求接下来的日志都带这个 trace。

    BaseHTTPMiddleware 在 call_next 前设置 → ContextVar 随任务上下文复制
    传播到端点;中间件自身在响应阶段的日志也带同一 trace。
    """
    _trace_id.set(trace_id)


class _CurrentStderrHandler(logging.StreamHandler):
    """每次写入都取当前 sys.stderr(行为与 print 一致)。

    StreamHandler 会在创建时固化 sys.stderr 对象;pytest 等环境在测试间
    关闭/替换它,写入已关闭流会触发 logging 的 handleError——原始消息以
    Message/Arguments 形态混进新 stderr,既丢格式又污染输出。
    """

    @property
    def stream(self):
        return sys.stderr

    @stream.setter
    def stream(self, value):   # 父类 __init__ 的赋值直接忽略
        pass


class _ContextFilter(logging.Filter):
    """把运行上下文(run/round/trace)注入每条记录;无上下文自动省略字段。"""

    def filter(self, record: logging.LogRecord) -> bool:
        from trader.core.context import current_run   # 延迟导入防循环依赖
        from trader.core.events import current_round
        parts = []
        if run := current_run():
            parts.append(f"run={run}")
        if rnd := current_round():
            parts.append(f"r{rnd}")
        if trace := _trace_id.get():
            parts.append(f"trace={trace[:8]}")  # 32 位全量在对账时查信封,日志里 8 位够认
        record.ctx = f" [{' '.join(parts)}]" if parts else ""
        return True


def setup_logging(level: str | None = None) -> None:
    """进程级一次性配置(幂等,重复调用安全;get_logger 会自动调)。"""
    global _configured
    with _config_lock:
        if _configured:
            return
        handler = _CurrentStderrHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname).1s %(name)s%(ctx)s %(message)s",
            datefmt="%m-%d %H:%M:%S"))
        handler.addFilter(_ContextFilter())
        root = logging.getLogger("trader")
        root.addHandler(handler)
        root.setLevel((level or os.environ.get("TRADER_LOG_LEVEL") or "INFO").upper())
        root.propagate = False  # 不冒泡到 root,防 uvicorn 的 handler 重复输出
        _configured = True


def get_logger(name: str) -> logging.Logger:
    """取 trader 命名空间下的 logger。传 __name__ 或短名均可,统一归到 trader.<短名>。"""
    setup_logging()
    return logging.getLogger(f"trader.{name.rsplit('.', 1)[-1]}")
