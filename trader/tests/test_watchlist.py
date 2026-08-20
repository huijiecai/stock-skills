"""watchlist/systems 测试:平台通用件(自选组 + 系统注册表),tmp schema 隔离。

覆盖:建组/追加更新 / 剔除 / as_of 历史重建 / versions 事件流 / systems manifest。

docstring 统一格式:<场景>:<验证点>
"""
from trader.core.db import _connect
from trader.core.systems import default_systems, ensure_expectation_system
from trader.core.watchlist import Watchlists

TOOL = "watchlist"


def _wl(request):
    return Watchlists(schema=f"t_{request.node.name[:40]}")


def test_save_and_get(request):
    """建组与查询:成员带自由字段(role/reason),按 code 去重。"""
    w = _wl(request)
    w.save("exp37", [
        {"code": "002156", "name": "通富微电", "fields": {"role": "leader", "reason": "封测受益"}},
        {"code": "000021", "name": "深科技", "fields": {"role": "core", "reason": "模组占营收高"}},
    ])
    members = w.get("exp37")
    print(f"  → {len(members)} 个成员:{[m['code'] for m in members]}")
    assert len(members) == 2
    by_code = {m["code"]: m["fields"] for m in members}
    assert by_code["002156"]["role"] == "leader"
    assert by_code["000021"]["role"] == "core"


def test_upsert_and_remove(request):
    """追加更新与剔除:save 按 code upsert 不动未提及成员;remove 落事件。"""
    w = _wl(request)
    w.save("exp37", [{"code": "002156", "fields": {"role": "leader"}}])
    w.save("exp37", [{"code": "000021", "fields": {"role": "core"}}])       # 追加
    w.save("exp37", [{"code": "002156", "fields": {"role": "leader", "note": "重研更新"}}])  # 更新
    w.remove_member("exp37", "000021")                                        # 剔除
    members = w.get("exp37")
    print(f"  → 最终成员:{[(m['code'], m['fields']) for m in members]}")
    assert [m["code"] for m in members] == ["002156"]
    assert members[0]["fields"]["note"] == "重研更新"


def test_as_of_rebuild(request):
    """as_of 历史重建:剔除前的时点名单可回放(复盘关联的机器层)。"""
    w = _wl(request)
    w.save("exp37", [{"code": "002156", "fields": {"role": "leader"}},
                     {"code": "600667", "fields": {"role": "related"}}])
    w.remove_member("exp37", "600667")
    today = __import__("datetime").date.today().strftime("%Y%m%d")
    current = [m["code"] for m in w.get("exp37")]
    as_of = [m["code"] for m in w.get("exp37", as_of=today)]
    print(f"  → 当前:{current} | as_of {today}:{as_of}(同日全事件折叠)")
    assert current == ["002156"]
    assert as_of == ["002156"]  # 同日折叠包含当日全部事件(含剔除)


def test_versions_events(request):
    """versions 事件流:create/add/update/remove 逐条可审计。"""
    w = _wl(request)
    w.save("exp37", [{"code": "002156", "fields": {"role": "leader"}}])
    w.save("exp37", [{"code": "002156", "fields": {"role": "core"}}])
    w.remove_member("exp37", "002156")
    with _connect(w.schema) as conn:
        rows = conn.execute(
            "SELECT action, payload->>'code' AS code FROM versions"
            " WHERE subject_type='watchlist' ORDER BY id").fetchall()
    print(f"  → 事件流:{[(r['action'], r['code']) for r in rows]}")
    assert [(r["action"], r["code"]) for r in rows] == [
        ("create", None), ("add", "002156"), ("update", "002156"), ("remove", "002156")]


def test_systems_manifest():
    """系统注册表:expectation 行存在,五阶段可解析,工具白名单全部在注册表内。"""
    from trader.core.registry import TOOLS
    row = ensure_expectation_system()
    manifest = row["manifest"]
    stages = manifest["stages"]
    print(f"  → 系统 {row['slug']}:阶段 {list(stages)},工具 {len(manifest['tools'])} 个")
    assert set(stages) == {"premarket", "live", "replay", "close", "research"}
    missing = [t for t in manifest["tools"] if t not in TOOLS]
    assert not missing, f"manifest 引用了不存在的工具:{missing}"
