"""pytest 共享 fixture + 钩子。

每个测试的 -s 输出三要素:
  ▶ 测试 · <测什么>(docstring)
    → astock: <真实结果>(测试内 print)
    ✓ 通过 / ✗ 失败(用 makereport 钩子判断,不是 try/except)

注:try/except 包 yield 捕不到测试失败(pytest 不向 fixture teardown 传播测试异常),
必须用 pytest_runtest_makereport 钩子记录结果,fixture teardown 再读。
"""
import pytest


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    """记录每个阶段的 report,挂到 item 上供 fixture teardown 读取。"""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


@pytest.fixture(autouse=True)
def _log_test(request):
    doc = ""
    fn = request.node.function
    if fn.__doc__:
        doc = next((line.strip() for line in fn.__doc__.splitlines() if line.strip()), "")
    tool = getattr(request.module, "TOOL", "")
    label = f"[{tool}] · " if tool else ""
    print(f"\n▶ {label}{doc or request.node.name}")
    yield
    rep = getattr(request.node, "rep_call", None)
    status = "✗ 失败" if (rep is not None and not rep.passed) else "✓ 通过"
    print(f"  {status}")


@pytest.fixture(autouse=True)
def _reset_bag_context():
    """袋子上下文是进程环境态:每个测试前后复位到正本,防串袋污染后续测试。"""
    from trader.core.context import set_context
    set_context(0, None)
    yield
    set_context(0, None)


# ── PG 测试隔离:会话开始时清掉上轮遗留的 t_* schema ──
import psycopg
import pytest


@pytest.fixture(scope="session", autouse=True)
def _clean_test_schemas():
    from trader.core.db import DATABASE_URL
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        rows = conn.execute(
            "SELECT schema_name FROM information_schema.schemata"
            " WHERE schema_name LIKE 't\_%'").fetchall()
        for (name,) in rows:
            conn.execute(f'DROP SCHEMA "{name}" CASCADE')
    yield
