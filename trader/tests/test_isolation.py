"""行级隔离铁律测试:模拟袋(bag≠0)的一切写入永不触碰正本(bag 0)。

附录 13 的测试兜底——store 层 bag_id 注入靠纪律,这条测试守住底线:
任何 store 方法漏带 bag 过滤、任何"默认袋子"解析错误,都会在这里爆。

docstring 统一格式:<场景>:<验证点>
"""
from trader.core.context import set_context
from trader.core.documents import Documents
from trader.core.ledger import Account

TOOL = "isolation"


def test_replay_bag_never_touches_live(request):
    """模拟袋写入隔离:bag 77 的钱包/成交/文档全落袋内,正本(bag 0)分毫不动。"""
    schema = f"t_{request.node.name[:40]}"
    acct, docs = Account(schema=schema), Documents(schema=schema)
    set_context(0, None)
    base_cash = acct.cash()
    base_fills = len(acct.fills())
    base_docs = len(docs.list())

    set_context(77, run_id=77)                      # 模拟袋上下文(engine 开场后的状态)
    acct.open_wallet(50_000_00, 100_000_00)         # 开局钱包
    acct.buy("000021", 100, 10.0, on="2026-08-18",
             name="深科技", reason="#测试预期 买入", run_id=77)
    docs.save("watch_replay", "r1 模拟轮日志", name="r1", trade_date="20260818")

    assert acct.cash() == 50_000_00 - 100 * 1000     # 袋内现金被扣
    assert len(acct.fills()) == base_fills + 1       # 成交落袋内
    assert acct.fills()[-1]["bag_id"] == 77 and acct.fills()[-1]["run_id"] == 77
    assert len(docs.list()) == base_docs + 1         # 文档落袋内

    set_context(0, None)                             # 切回正本核对:分毫未动
    assert acct.cash() == base_cash, "模拟袋买入动到了正本现金!"
    assert len(acct.fills()) == base_fills, "模拟袋成交泄漏到正本!"
    assert len(docs.list()) == base_docs, "模拟袋文档泄漏到正本!"
    print(f"  → bag77:现金 {49_000_00/100:,.0f}/1 成交/1 文档;bag0:原样({base_cash/100:,.0f}/{base_fills} 成交/{base_docs} 文档)")


def test_wallet_reopen_rejected(request):
    """钱包开局幂等拒绝:已开局的袋子再 open_wallet 报错,防误覆盖。"""
    from trader.core.ledger import AccountError
    import pytest

    acct = Account(schema=f"t_{request.node.name[:40]}")
    set_context(88, None)
    acct.open_wallet(100_000_00, 100_000_00)
    with pytest.raises(AccountError, match="已开局"):
        acct.open_wallet(100_000_00, 100_000_00)


def test_user_four_dimension_isolation(request):
    """M1 验收:用户 B 的四维世界(系统/prompt/知识/账本)与用户 A 完全隔离。"""
    from trader.core.documents import Documents
    from trader.core.identity import Identity
    from trader.core.ledger import Ledgers
    from trader.core.promptver import PromptVersions
    from trader.core.runs import Runs
    from trader.core.systems import Systems
    from trader.core.watchlist import Watchlists

    schema = f"t_{request.node.name[:40]}"
    idt, ledgers = Identity(schema=schema), Ledgers(schema=schema)
    docs, pv, runs, sysm = (Documents(schema=schema), PromptVersions(schema=schema),
                            Runs(schema=schema), Systems(schema=schema))
    a = idt.create_user("a@iso.test", "p")["id"]
    b = idt.create_user("b@iso.test", "p")["id"]
    la = ledgers.create(a, "A本", "live")
    lb = ledgers.create(b, "B本", "paper")

    # B 建自己的系统/prompt/知识/场次
    sysm.upsert("my-system", {"stages": {}}, user_id=b)
    pv.save("system", "B 的方法论", user_id=b)
    set_context(lb["bag_id"], None, b)
    docs.save("expectation", "B 的预期", meta={"status": "active"})
    Watchlists(schema=schema).save("B池", [{"code": "000001"}])
    runs.create("B-run", "replay", "20260818", {}, user_id=b)

    # 维度①系统:A 查不到 B 的系统
    assert sysm.get("my-system", user_id=a) is None and sysm.get("my-system", user_id=b) is not None
    # 维度②prompt:A 的 latest 拿不到 B 的版本
    assert pv.latest("system", user_id=a) is None and "B 的方法论" in pv.latest("system", user_id=b)
    # 维度③知识:A 的上下文里看不到 B 的文档/自选组
    set_context(la["bag_id"], None, a)
    assert all(d["name"] != "B 的预期" for d in docs.list("expectation"))
    assert not any(w["name"] == "B池" for w in Watchlists(schema=schema).list_all())
    # 维度④场次/账本:A 查不到 B 的场;账本各归各
    assert runs.get("B-run", user_id=a) is None and runs.get("B-run", user_id=b) is not None
    assert [x["name"] for x in ledgers.list(a)] == ["A本"] and \
           [x["name"] for x in ledgers.list(b)] == ["B本"]
    print(f"  → 四维隔离:user{a}(A本 bag{la['bag_id']}) 与 user{b}(B本 bag{lb['bag_id']}) 互不可见")
