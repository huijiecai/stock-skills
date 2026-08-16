"""文档库测试:Documents 通用 md 存储(save upsert / get / list / 查无)。

docstring 统一格式:<场景>:<验证点>
"""
import textwrap

from trader.store import Documents

TOOL = "documents"


def _docs(tmp_path):
    return Documents(db_path=tmp_path / "test.db")


def _show(label, out):
    print("  → " + label + ":")
    print(textwrap.indent(str(out), "    ")[:300])


def test_save_and_get(tmp_path):
    """保存/读取:盘前报告按 trade_date 存取。"""
    d = _docs(tmp_path)
    d.save("premarket", "# 盘前报告\n预案:存储池≥6/8买太极", trade_date="20260812")
    got = d.get("premarket", trade_date="20260812")
    _show("读取", got)
    assert "买太极" in got


def test_upsert_overwrite(tmp_path):
    """同键覆盖:同 type+name+date 再存 → 更新而非新增。"""
    d = _docs(tmp_path)
    d.save("premarket", "v1", trade_date="20260812")
    d.save("premarket", "v2 修订", trade_date="20260812")
    docs = d.list("premarket")
    _show("列表(应1条)", docs)
    assert len(docs) == 1
    assert "v2" in d.get("premarket", trade_date="20260812")


def test_different_keys_not_overwrite(tmp_path):
    """不同键不覆盖:不同 trade_date 各自独立。"""
    d = _docs(tmp_path)
    d.save("premarket", "周一报告", trade_date="20260810")
    d.save("premarket", "周二报告", trade_date="20260811")
    assert len(d.list("premarket")) == 2
    assert "周二" in d.get("premarket", trade_date="20260811")


def test_get_missing(tmp_path):
    """查无:返回 None(工具层转提示)。"""
    d = _docs(tmp_path)
    assert d.get("premarket", trade_date="20990101") is None


def test_research_doc_with_ref(tmp_path):
    """研究过程报告:ref_id 挂预期 id,list 可见关联。"""
    d = _docs(tmp_path)
    d.save("research", "光纤涨价研究过程:归因四行...", name="光纤", ref_id=2)
    rows = d.list("research")
    _show("列表", rows)
    assert rows[0]["ref_id"] == 2
    assert "归因四行" in d.get("research", name="光纤")
