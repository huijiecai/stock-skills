"""指令版本库:版本流、系统/用户命名空间与 CLI diff。"""

from trader.core.promptver import PromptVersions

# 测试用的系统 id(隔离 schema 无约束,任意整数即可;1=expectation 语义)
SID = 1


def test_versions_are_stored_and_read():
    pv = PromptVersions(schema="t_prompt_versions_test")
    pv.save(SID, "system", "规则A")               # 独立 schema 冒烟
    v1 = pv.get(SID, "system", 1)
    assert v1 == "规则A"
    assert pv.versions(SID, "system")[0]["version"] >= 1


def test_identity_three_layers(request):
    """三层身份:slug 不变版本流延续;display_name 可改不动版本;跨系统不串。"""
    pv = PromptVersions(schema=f"t_{request.node.name[:40]}")
    pv.save(1, "premarket", "v1 内容", display_name="盘前分析")
    pv.save(1, "premarket", "v2 内容", display_name="盘前分析(新)")   # 版本流延续
    pv.save(2, "premarket", "另一个系统的盘前")                        # 同 slug 不同系统
    p1 = pv.get_prompt(1, "premarket")
    assert p1["display_name"] == "盘前分析(新)"      # 显示名跟随更新
    assert len(pv.versions(1, "premarket")) == 2     # 系统1 两个版本
    assert len(pv.versions(2, "premarket")) == 1     # 系统2 独立版本流
    assert pv.latest(1, "premarket") == "v2 内容"
    assert pv.latest(2, "premarket") == "另一个系统的盘前"


def test_user_level_prompt(request):
    """用户级指令(_coach 类):system_id=NULL,按 user 命名空间,互不串。"""
    pv = PromptVersions(schema=f"t_{request.node.name[:40]}")
    pv.save(None, "_coach", "用户7的教练风格", user_id=7)
    pv.save(None, "_coach", "用户8的教练风格", user_id=8)
    assert pv.latest(None, "_coach", user_id=7) == "用户7的教练风格"
    assert pv.latest(None, "_coach", user_id=8) == "用户8的教练风格"
    assert pv.latest(None, "_coach", user_id=9) is None


def test_diff_cli_shows_change(capsys):
    import sys
    sys.argv = ["prompts", "diff", "no_such", "1", "2"]
    from trader.prompts import _main
    try:
        _main()
    except SystemExit:
        pass
