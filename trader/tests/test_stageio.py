"""阶段 I/O 契约测试:任意阶段名的产物发布、上游解析、最近轮次和血缘。"""
import pytest

from trader.core.context import set_context
from trader.core.documents import Documents
from trader.core.events import set_current_round
from trader.core.stageio import (load_stage_inputs, publish_stage_outputs, stage_contract,
                                 validate_stage_contracts)

TOOL = "stageio"


def _manifest():
    return {
        "stages": {
            "morning_brief": {
                "kind": "single",
                "prompt": "morning_brief",
                "outputs": {
                    "daily_plan": {
                        "kind": "document", "doc_type": "custom_plan",
                        "trade_date": "{date}", "label": "今日计划",
                    },
                },
            },
            "observer": {
                "kind": "loop",
                "prompt": "observer",
                "inputs": {
                    "plan": {"from": "morning_brief.daily_plan", "required": True},
                    "memory": {"from": "observer.decision", "selector": "previous",
                               "limit": 3, "required": False},
                },
                "outputs": {
                    "decision": {
                        "kind": "document", "doc_type": "custom_round",
                        "name": "r{rounds}", "trade_date": "{date}",
                    },
                },
            },
        },
    }


def test_generic_stage_outputs_feed_later_stage(request):
    """通用阶段名:上游 plan 和最近 3 轮由契约解析,不依赖 premarket/watch_*。"""
    docs = Documents(schema=f"t_{request.node.name[:40]}")
    manifest = _manifest()
    set_context(77, 1001, 9)
    set_current_round(0)
    publish_stage_outputs("morning_brief", manifest["stages"]["morning_brief"],
                          {"date": "20260821"}, "今天只在确认后交易", docs)
    for n in range(1, 5):
        set_current_round(n)
        publish_stage_outputs("observer", manifest["stages"]["observer"],
                              {"date": "20260821", "rounds": n}, f"第 {n} 轮判断", docs)

    set_context(77, 1002, 9)
    set_current_round(0)
    context = load_stage_inputs(manifest, "observer", {"date": "20260821"}, docs)
    assert "今天只在确认后交易" in context
    assert "第 1 轮判断" not in context
    assert all(f"第 {n} 轮判断" in context for n in (2, 3, 4))
    linked = [r for r in docs.for_run(1002) if r["relation"] == "input"]
    assert {r["slot"] for r in linked} == {"plan", "memory"}
    assert {r["source_stage"] for r in linked} == {"morning_brief", "observer"}
    assert stage_contract("observer", manifest["stages"]["observer"])["outputs"]["decision"]


def test_required_stage_input_blocks_execution(request):
    """必需输入缺失:引擎明确阻止执行,不把问题留给 Prompt 猜。"""
    docs = Documents(schema=f"t_{request.node.name[:40]}")
    set_context(78, 1003, 9)
    with pytest.raises(RuntimeError, match="缺少必需输入 plan"):
        load_stage_inputs(_manifest(), "observer", {"date": "20260821"}, docs)


def test_legacy_prompt_output_is_not_overwritten(request):
    """旧 Prompt 兼容:本轮已自行保存完整报告时,自动发布只补槽位不覆盖正文。"""
    docs = Documents(schema=f"t_{request.node.name[:40]}")
    manifest = _manifest()
    set_context(79, 1004, 9)
    set_current_round(0)
    doc_id = docs.save("custom_plan", "旧 Prompt 保存的完整报告", trade_date="20260821")
    published = publish_stage_outputs(
        "morning_brief", manifest["stages"]["morning_brief"],
        {"date": "20260821"}, "最终简短回复", docs,
    )
    assert published[0]["id"] == doc_id
    assert docs.get("custom_plan", trade_date="20260821") == "旧 Prompt 保存的完整报告"
    output = next(r for r in docs.for_run(1004) if r["relation"] == "output")
    assert (output["stage"], output["slot"]) == ("morning_brief", "daily_plan")


def test_stage_contract_validation():
    """保存边界:不存在的来源、无 doc_type 和非法 selector 会给出明确错误。"""
    manifest = _manifest()
    assert validate_stage_contracts(manifest) == []
    manifest["stages"]["observer"]["inputs"]["plan"]["from"] = "missing.plan"
    manifest["stages"]["observer"]["inputs"]["memory"]["selector"] = "random"
    manifest["stages"]["observer"]["outputs"]["decision"].pop("doc_type")
    errors = validate_stage_contracts(manifest)
    assert any("不存在" in e for e in errors)
    assert any("未知选择器" in e for e in errors)
    assert any("doc_type" in e for e in errors)
