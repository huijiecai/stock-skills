"""行级隔离铁律测试:实验组合(portfolio≠0)的一切写入永不触碰实盘组合(portfolio 0)。

store 层 portfolio_id 注入靠纪律,这条测试守住底线:
任何 store 方法漏带组合过滤、任何"默认组合"解析错误,都会在这里爆。

docstring 统一格式:<场景>:<验证点>
"""
from trader.core.context import set_context
from trader.core.documents import Documents
from trader.core.ledger import Wallet

TOOL = "isolation"


def test_experiment_portfolio_never_touches_main(request):
    """实验组合写入隔离:组合 77 的钱包/成交/文档全落组合内,实盘(组合 0)分毫不动。"""
    schema = f"t_{request.node.name[:40]}"
    acct, docs = Wallet(schema=schema), Documents(schema=schema)
    set_context(0, None)
    base_cash = acct.cash()
    base_fills = len(acct.fills())
    base_docs = len(docs.list())

    set_context(77, run_id=77)                      # 实验组合上下文(engine 开场后的状态)
    acct.open_wallet(50_000_00, 100_000_00)         # 开局钱包
    acct.buy("000021", 100, 10.0, on="2026-08-18",
             name="深科技", reason="#测试预期 买入", run_id=77)
    docs.save("watch_replay", "r1 模拟轮日志", name="r1", trade_date="20260818")

    assert acct.cash() == 50_000_00 - 100 * 1000     # 组合内现金被扣
    assert len(acct.fills()) == base_fills + 1       # 成交落组合内
    assert acct.fills()[-1]["portfolio_id"] == 77 and acct.fills()[-1]["run_id"] == 77
    assert len(docs.list()) == base_docs + 1         # 文档落组合内

    set_context(0, None)                             # 切回实盘核对:分毫未动
    assert acct.cash() == base_cash, "实验组合买入动到了实盘现金!"
    assert len(acct.fills()) == base_fills, "实验组合成交泄漏到实盘!"
    assert len(docs.list()) == base_docs, "实验组合文档泄漏到实盘!"
    print(f"  → 组合77:现金 {49_000_00/100:,.0f}/1 成交/1 文档;组合0:原样({base_cash/100:,.0f}/{base_fills} 成交/{base_docs} 文档)")


def test_wallet_reopen_rejected(request):
    """钱包开局幂等拒绝:已开局的组合再 open_wallet 报错,防误覆盖。"""
    from trader.core.ledger import WalletError
    import pytest

    acct = Wallet(schema=f"t_{request.node.name[:40]}")
    set_context(88, None)
    acct.open_wallet(100_000_00, 100_000_00)
    with pytest.raises(WalletError, match="已开局"):
        acct.open_wallet(100_000_00, 100_000_00)


def test_user_four_dimension_isolation(request):
    """M1 验收:用户 B 的四维世界(系统/指令/知识/组合)与用户 A 完全隔离。"""
    from trader.core.documents import Documents
    from trader.core.identity import Identity
    from trader.core.portfolios import Portfolios
    from trader.core.promptver import PromptVersions
    from trader.core.runs import Runs
    from trader.core.systems import Systems
    from trader.core.watchlist import Watchlists

    schema = f"t_{request.node.name[:40]}"
    idt, ports = Identity(schema=schema), Portfolios(schema=schema)
    docs, pv, runs, sysm = (Documents(schema=schema), PromptVersions(schema=schema),
                            Runs(schema=schema), Systems(schema=schema))
    a = idt.create_user("a@iso.test", "p")["id"]
    b = idt.create_user("b@iso.test", "p")["id"]
    sa = sysm.upsert("a-system", {"stages": {}}, user_id=a)
    sb = sysm.upsert("my-system", {"stages": {}}, user_id=b)
    pa = ports.create(a, "main", sa["id"], "A本")
    pb = ports.create(b, "paper", sb["id"], "B本")

    # B 建自己的指令/知识/场次(全部挂 B 的系统命名空间/组合)
    pv.save(sb["id"], "system", "B 的方法论")
    set_context(pb, None, b)
    docs.save("expectation", "B 的预期", meta={"status": "active"})
    Watchlists(schema=schema).save("B池", [{"code": "000001"}])
    runs.create("B-run", "replay", "20260818", {}, system_id=sb["id"],
                user_id=b, clock="simulated", clock_date="20260818", portfolio_id=pb)

    # 维度①系统:A 查不到 B 的系统
    assert sysm.get("my-system", user_id=a) is None and sysm.get("my-system", user_id=b) is not None
    # 维度②指令:A 系统的 latest 拿不到 B 系统的版本
    assert pv.latest(sa["id"], "system") is None and "B 的方法论" in pv.latest(sb["id"], "system")
    # 维度③知识:A 的上下文里看不到 B 的文档/自选组
    set_context(pa, None, a)
    assert all(d["name"] != "B 的预期" for d in docs.list("expectation"))
    assert not any(w["name"] == "B池" for w in Watchlists(schema=schema).list_all())
    # 维度④场次/组合:A 查不到 B 的场;组合各归各
    assert runs.get("B-run", user_id=a) is None and runs.get("B-run", user_id=b) is not None
    assert [x["name"] for x in ports.list(a)] == ["A本"] and \
           [x["name"] for x in ports.list(b)] == ["B本"]
    print(f"  → 四维隔离:user{a}(A本 组合{pa}) 与 user{b}(B本 组合{pb}) 互不可见")


def test_main_portfolio_unique_per_user_system(request):
    """实盘组合唯一性:同(用户×系统)第二个 main 被部分唯一索引拒绝;paper/实验不限。"""
    import psycopg
    import pytest

    from trader.core.identity import Identity
    from trader.core.portfolios import Portfolios
    from trader.core.systems import Systems

    schema = f"t_{request.node.name[:40]}"
    idt, sysm, ports = Identity(schema=schema), Systems(schema=schema), Portfolios(schema=schema)
    u = idt.create_user("u@iso.test", "p")["id"]
    sysrow = sysm.upsert("u-system", {"stages": {}}, user_id=u)
    first = ports.create(u, "main", sysrow["id"], "主组合")
    with pytest.raises(psycopg.errors.UniqueViolation, match="portfolios_main_unique"):
        ports.create(u, "main", sysrow["id"], "再来一个")
    ports.create(u, "paper", sysrow["id"], "模拟1")
    ports.create(u, "paper", sysrow["id"], "模拟2")   # paper 不限
    ports.create(u, "experiment", sysrow["id"])        # experiment 不限
    assert len([x for x in ports.list(u) if x["type"] == "main"]) == 1
    print(f"  → user{u} 系统{sysrow['id']}:实盘恰一个(组合{first}),paper/experiment 可多个")
