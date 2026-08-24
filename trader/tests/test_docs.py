"""文档库测试:Documents 通用 md 存储(save upsert / get / list / 查无)。

docstring 统一格式:<场景>:<验证点>
"""
import textwrap

from trader.core.documents import Documents

TOOL = "documents"


def _docs(request):
    return Documents(schema=f"t_{request.node.name[:40]}")


def _show(label, out):
    print("  → " + label + ":")
    print(textwrap.indent(str(out), "    ")[:300])


def test_save_and_get(request):
    """保存/读取:盘前报告按 trade_date 存取。"""
    d = _docs(request)
    d.save("premarket", "# 盘前报告\n预案:存储池≥6/8买太极", trade_date="20260812")
    got = d.get("premarket", trade_date="20260812")
    _show("读取", got)
    assert "买太极" in got


def test_upsert_overwrite(request):
    """同键覆盖:同 type+name+date 再存 → 更新而非新增。"""
    d = _docs(request)
    d.save("premarket", "v1", trade_date="20260812")
    d.save("premarket", "v2 修订", trade_date="20260812")
    docs = d.list("premarket")
    _show("列表(应1条)", docs)
    assert len(docs) == 1
    assert "v2" in d.get("premarket", trade_date="20260812")


def test_different_keys_not_overwrite(request):
    """不同键不覆盖:不同 trade_date 各自独立。"""
    d = _docs(request)
    d.save("premarket", "周一报告", trade_date="20260810")
    d.save("premarket", "周二报告", trade_date="20260811")
    assert len(d.list("premarket")) == 2
    assert "周二" in d.get("premarket", trade_date="20260811")


def test_get_missing(request):
    """查无:返回 None(工具层转提示)。"""
    d = _docs(request)
    assert d.get("premarket", trade_date="20990101") is None


def test_research_doc_with_ref(request):
    """研究过程报告:ref_id 挂预期 id,list 可见关联。"""
    d = _docs(request)
    d.save("research", "光纤涨价研究过程:归因四行...", name="光纤", ref_id=2)
    rows = d.list("research")
    _show("列表", rows)
    assert rows[0]["ref_id"] == 2
    assert "归因四行" in d.get("research", name="光纤")


def test_run_document_evidence(request):
    """证据关联:场次内保存记 output，随后读取同文档记 input。"""
    from trader.core.context import set_context
    d = _docs(request)
    set_context(77, 9001, 3)
    doc_id = d.save("research", "证据正文", name="存储")
    assert d.get("research", name="存储") == "证据正文"
    rows = d.for_run(9001)
    assert [(r["document_id"] if "document_id" in r else r["id"], r["relation"])
            for r in rows] == [(doc_id, "input"), (doc_id, "output")]
    linked = d.get_for_run(9001, doc_id)
    assert linked["content"] == "证据正文"
    assert d.get_for_run(9002, doc_id) is None


def test_run_document_stage_slots(request):
    """阶段槽位:自动工具边可被引擎补充为明确的输入来源和输出身份。"""
    from trader.core.context import set_context
    d = _docs(request)
    set_context(88, 9010, 3)
    doc_id = d.save("custom_plan", "计划正文", trade_date="20260821")
    d.link_run(doc_id, "output", stage="prepare", slot="plan")
    d.link_run(doc_id, "input", stage="observe", slot="opening_plan",
               source_stage="prepare", source_output="plan")
    rows = d.for_run(9010)
    output = next(r for r in rows if r["relation"] == "output")
    input_ = next(r for r in rows if r["relation"] == "input")
    assert (output["stage"], output["slot"]) == ("prepare", "plan")
    assert (input_["stage"], input_["slot"]) == ("observe", "opening_plan")
    assert (input_["source_stage"], input_["source_output"]) == ("prepare", "plan")


def test_run_document_keeps_content_snapshot(request):
    """场次证据快照:来源文档日后更新,旧场仍展示当时真正读到的正文。"""
    from trader.core.context import set_context
    d = _docs(request)
    set_context(91, 2001, 9)
    doc_id = d.save("plan", "第一版计划", trade_date="20260821")
    d.link_run(doc_id, "input", stage="observer", slot="plan",
               source_stage="morning", source_output="daily_plan")

    set_context(91, 2002, 9)
    d.save("plan", "第二版计划", trade_date="20260821")

    assert d.get_for_run(2001, doc_id)["content"] == "第一版计划"
    assert d.get_for_run(2002, doc_id)["content"] == "第二版计划"
