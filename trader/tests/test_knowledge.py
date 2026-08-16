"""预期库测试:expectations + pool_members(SQLite,tmp 库,不碰真实数据)。

覆盖:写入(预期+池)/ 同方向多波 / 重复拒绝 / 阶段与失效更新 / core 过滤 / 统计。

docstring 统一格式:<场景>:<验证点>
"""
import textwrap

import pytest

from trader.store import Expectations

TOOL = "expectations"


def _exp(tmp_path):
    return Expectations(db_path=tmp_path / "test.db")


POOL = [
    {"code": "001309", "name": "德明利", "role": "core", "reason": "存储模组占营收70%,涨价直接增厚业绩"},
    {"code": "603986", "name": "兆易创新", "role": "core", "reason": "NOR+利基DRAM,存货收益"},
    {"code": "688083", "name": "长鑫科技", "role": "related", "reason": "产业链相关,存货弹性小"},
]


def _show(title, obj):
    print("  → " + title + ":")
    print(textwrap.indent(str(obj), "    "))


def test_add_and_get(tmp_path):
    """写入:预期+池,get 返回完整(池按 leader>core>related 排序)。"""
    e = _exp(tmp_path)
    eid = e.add("存储芯片", "存货涨价",
                "AI服务器需求带动利基存储供不应求,模组厂存货增值",
                "DRAM/NAND现货价与合约价",
                "涨价逻辑被充分定价,合约价见顶回落",
                "现货价持续回落或供给端大规模恢复",
                POOL)
    got = e.get(eid)
    _show("预期详情", got)
    assert got["direction"] == "存储芯片" and got["event"] == "存货涨价"
    assert got["stage"] == "observing" and got["status"] == "active"
    assert len(got["pool"]) == 3
    assert got["pool"][0]["role"] in ("core", "leader")


def test_same_direction_multiple_events(tmp_path):
    """同方向多波:存货涨价 + 2026年报业绩,两条独立预期。"""
    e = _exp(tmp_path)
    e.add("存储芯片", "存货涨价", "a", "b", "c", "d", POOL)
    e.add("存储芯片", "2026年报业绩", "业绩兑现存货收益", "年报披露", "年报落地", "业绩不及预期", POOL[:2])
    rows = e.get_all()
    _show("全部预期", [(r["direction"], r["event"], r["status"]) for r in rows])
    assert len(rows) == 2
    assert all(r["direction"] == "存储芯片" for r in rows)


def test_duplicate_rejected(tmp_path):
    """重复(方向+事件)拒绝写入。"""
    e = _exp(tmp_path)
    e.add("存储芯片", "存货涨价", "a", "b", "c", "d", POOL)
    with pytest.raises(ValueError, match="已存在"):
        e.add("存储芯片", "存货涨价", "a", "b", "c", "d", POOL)


def test_update_stage_and_invalid(tmp_path):
    """更新:阶段推进(confirmed);失效带原因(事前 fail_flag 之外的事后记录)。"""
    e = _exp(tmp_path)
    eid = e.add("存储芯片", "存货涨价", "a", "b", "c", "d", POOL)
    e.update(eid, stage="confirmed")
    assert e.get(eid)["stage"] == "confirmed"
    e.update(eid, status="invalid", invalid_reason="现货价未涨,涨价逻辑不成立")
    got = e.get(eid)
    _show("失效预期", (got["status"], got["invalid_reason"]))
    assert got["status"] == "invalid"
    assert "现货价" in got["invalid_reason"]


def test_invalid_stage_rejected(tmp_path):
    """非法 stage/status 拒绝(枚举校验)。"""
    e = _exp(tmp_path)
    eid = e.add("存储芯片", "存货涨价", "a", "b", "c", "d", POOL)
    with pytest.raises(ValueError, match="stage 非法"):
        e.update(eid, stage="boom")
    with pytest.raises(ValueError, match="status 非法"):
        e.update(eid, status="dead")


def test_pool_codes_core_filter(tmp_path):
    """池代码过滤:只取 leader+core(买入名单),related 排除。"""
    e = _exp(tmp_path)
    eid = e.add("存储芯片", "存货涨价", "a", "b", "c", "d",
                POOL + [{"code": "600667", "name": "太极实业", "role": "leader", "reason": "封测+模组,资金首选"}])
    assert len(e.pool_codes(eid)) == 4
    core = e.pool_codes(eid, roles=("leader", "core"))
    _show("核心池", core)
    assert "600667" in core and "001309" in core
    assert "688083" not in core  # related 被排除


def test_get_all_counts(tmp_path):
    """get_all 统计:核心/池数量(leader+core 算核心)。"""
    e = _exp(tmp_path)
    e.add("存储芯片", "存货涨价", "a", "b", "c", "d", POOL)
    row = e.get_all()[0]
    _show("统计", (row["core_count"], row["pool_count"]))
    assert row["core_count"] == 2 and row["pool_count"] == 3


def test_update_content_fields(tmp_path):
    """重新研究修正内容:update 支持 thesis/catalyst/兑现/失效 字段。"""
    e = _exp(tmp_path)
    eid = e.add("存储芯片", "存货涨价", "旧逻辑", "旧催化", "旧兑现", "旧失效", POOL)
    e.update(eid, thesis="新逻辑:Q2合约价再涨", catalyst="新催化:合约价数据")
    got = e.get(eid)
    _show("更新后", (got["thesis"], got["catalyst"], got["fulfill_flag"]))
    assert got["thesis"].startswith("新逻辑")
    assert got["catalyst"].startswith("新催化")
    assert got["fulfill_flag"] == "旧兑现"  # 未更新的字段不动


def test_pool_member_upsert(tmp_path):
    """池成员 upsert:同代码重复添加 → 更新 role/reason 而不是报错。"""
    e = _exp(tmp_path)
    eid = e.add("存储芯片", "存货涨价", "a", "b", "c", "d",
                [{"code": "001309", "name": "德明利", "role": "core", "reason": "初判"}])
    e.add_pool_member(eid, "001309", "德明利", role="leader", reason="重新研究后升级为龙头")
    got = e.get(eid)
    _show("upsert 后", got["pool"][0])
    assert len(got["pool"]) == 1  # 没有重复行
    assert got["pool"][0]["role"] == "leader"
    assert "升级为龙头" in got["pool"][0]["reason"]


def test_remove_pool_member(tmp_path):
    """剔除池成员:重新研究调整池。"""
    e = _exp(tmp_path)
    eid = e.add("存储芯片", "存货涨价", "a", "b", "c", "d", POOL)
    e.remove_pool_member(eid, "688083")  # 剔除 related
    codes = e.pool_codes(eid)
    _show("剔除后", codes)
    assert "688083" not in codes and len(codes) == 2
    with pytest.raises(ValueError, match="池成员不存在"):
        e.remove_pool_member(eid, "688083")  # 再剔报错
