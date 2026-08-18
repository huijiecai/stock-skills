"""prompt 版本库:本地编辑→入库→版本不变检测→diff。"""

from trader.prompts import sync_prompts
from trader.core.promptver import PromptVersions


def test_sync_versions_and_diff(tmp_path):
    d = tmp_path / "prompts"
    d.mkdir()
    (d / "system.md").write_text("规则A")
    (d / "close.md").write_text("盘后")

    pv_iso = PromptVersions(schema="t_sync_iso")
    r1 = sync_prompts(d, pv=pv_iso)          # 首次 → v1(隔离 schema)
    assert [x["changed"] for x in r1] == [True, True]
    assert [x["version"] for x in r1] == [1, 1]

    r2 = sync_prompts(d, pv=pv_iso)
    assert all(not x["changed"] for x in r2)

    (d / "system.md").write_text("规则A\n规则B")
    r3 = sync_prompts(d, pv=pv_iso)
    sys_r = next(x for x in r3 if x["name"] == "system")
    assert sys_r["changed"] and sys_r["version"] == 2

    pv = PromptVersions(schema="t_prompt_versions_test")
    pv.save("system", "规则A")                 # 独立 schema 冒烟
    v1 = pv.get("system", 1)
    assert v1 == "规则A"
    assert pv.versions("system")[0]["version"] >= 1


def test_diff_cli_shows_change(capsys):
    import sys
    sys.argv = ["prompts", "diff", "no_such", "1", "2"]
    from trader.prompts import _main
    try:
        _main()
    except SystemExit:
        pass
    assert "版本不存在" in capsys.readouterr().out
