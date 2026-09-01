"""结构化日志测试(T1.4):上下文字段自动注入,无上下文自动省略。

docstring 统一格式:<场景>:<验证点>
"""
from trader.core.context import set_context
from trader.core.events import set_current_round
from trader.core.log import get_logger, set_trace_id

TOOL = "log"


def test_log_carries_run_round_trace(capsys):
    """上下文字段:engine 设了 run/round、API 设了 trace 后,日志行自动带上。"""
    set_context(7, 457, 0)
    set_current_round(3)
    set_trace_id("abcdef1234567890abcdef1234567890")
    get_logger("selftest").info("自检消息")
    err = capsys.readouterr().err
    print(f"  → 日志行:{err.strip()}")
    assert "run=457" in err and "r3" in err
    assert "trace=abcdef12" in err          # 截断 8 位
    assert "I trader.selftest" in err and "自检消息" in err


def test_log_without_context_omits_brackets(capsys):
    """无上下文:不打印空括号,日志行保持干净。"""
    get_logger("selftest").warning("裸消息")
    err = capsys.readouterr().err
    print(f"  → 日志行:{err.strip()}")
    assert "裸消息" in err and "[" not in err


def test_api_request_log_has_trace(capsys):
    """API 打通:一次请求的中间件留痕与响应信封同 trace。"""
    from fastapi.testclient import TestClient
    from trader.api.app import create_app
    client = TestClient(create_app())
    r = client.post("/auth/login", json={"email": "nobody@x.io", "password": "x"})
    trace = r.json()["traceId"]
    err = capsys.readouterr().err
    # 只认我们自己 logger 的行(stderr 里可能混入第三方/其他 handler 的输出)
    line = next((ln for ln in err.splitlines()
                 if "trader.api" in ln and "POST /auth/login" in ln), "")
    print(f"  → 请求留痕:{line} | 信封 traceId={trace[:8]}")
    assert line and f"trace={trace[:8]}" in line and "→ 401" in line
