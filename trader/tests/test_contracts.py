"""Stage runtime contract model tests."""

from trader.core.contracts import StageSpec, normalize_manifest, stage_spec
from trader.core.context import ContextAssembler, RuntimeEnvelope, set_execution_mode
from trader.core.stageio import validate_stage_contracts
from trader.core.registry import capability_tools


def test_legacy_stage_fields_normalize_to_runtime_contract():
    spec = stage_spec("live", {
        "kind": "loop",
        "prompt": "market_observer",
        "interval": 5,
        "window": "09:35-15:05",
        "request_limit": 50,
        "inputs": {
            "opening_plan": {
                "from": "premarket.plan",
                "selector": "latest",
                "required": False,
            },
            "portfolio_snapshot": {"from": "premarket.plan", "selector": "latest",
                                    "required": False},
        },
        "outputs": {
            "decision": {"kind": "document", "doc_type": "watch_live"},
        },
    })

    assert isinstance(spec, StageSpec)
    assert spec.execution.mode == "loop"
    assert spec.execution.interval == 5
    assert spec.inputs["opening_plan"].source == "premarket.plan"
    assert spec.inputs["portfolio_snapshot"].kind == "artifact"
    assert spec.outputs["decision"].kind == "artifact"
    assert spec.contract()["version"] == 2
    assert "capabilities" not in spec.contract()


def test_manifest_normalization_adds_nested_execution_without_dropping_fields():
    raw = {
        "system_prompt": "system",
        "stages": {
            "open": {"kind": "single", "prompt": "open", "vars": ["date"]},
            "watch": {"kind": "loop", "prompt": "watch", "interval": 5},
        },
    }
    normalized = normalize_manifest(raw)

    assert normalized["contract_version"] == 2
    assert normalized["stages"]["open"]["execution"]["mode"] == "single"
    assert normalized["stages"]["watch"]["execution"]["interval"] == 5
    assert normalized["stages"]["open"]["vars"] == ["date"]
    assert raw["stages"]["watch"]["interval"] == 5


def test_runtime_context_rejects_runtime_observation_inputs():
    manifest = {"stages": {"observe": {
        "prompt": "observe",
        "inputs": {
            "indices": {"kind": "observation", "source": "runtime.indices",
                         "required": True},
            "settings": {"kind": "setting", "source": "system.settings",
                          "required": False},
        },
    }}}
    envelope = RuntimeEnvelope("demo", "observe", 7, 1, 2, "replay",
                               date="20260822", clock="10:35", round_no=3)
    errors = validate_stage_contracts(manifest)
    assert any("阶段输入只能引用阶段产物" in error for error in errors)


def test_stage_capabilities_are_not_part_of_the_user_contract():
    spec = stage_spec("observe", {"prompt": "observe", "capabilities": ["broker.secret"]})
    assert "capabilities" not in spec.contract()


def test_system_policy_controls_only_side_effects():
    manifest = {"policy": {"resource_write": False, "simulation_trading": True}}
    tools = capability_tools(manifest, execution_mode="replay")
    assert "get_quotes" in tools and "get_positions" in tools
    assert "save_watchlist" not in tools and "remove_watchlist_member" not in tools
    assert "execute" in tools
    assert "execute" not in capability_tools(manifest, execution_mode="real")


def test_manifest_policy_is_normalized_and_strict():
    normalized = normalize_manifest({"stages": {}, "policy": {"live_trading": True}})
    assert normalized["policy"] == {
        "web_search": False, "resource_write": False,
        "simulation_trading": True, "live_trading": True,
    }
    import pytest
    with pytest.raises(ValueError, match="必须是布尔值"):
        normalize_manifest({"stages": {}, "policy": {"live_trading": "yes"}})


def test_runtime_envelope_hides_platform_identity_from_prompt():
    envelope = RuntimeEnvelope("demo", "live", 7, 1, 2, "real",
                               date="20260822", clock="10:35", round_no=3)
    visible = envelope.to_dict()
    assert visible == {"mode": "real", "date": "20260822", "clock": "10:35", "round": 3}
    assert envelope.to_dict(internal=True)["portfolio_id"] == 2


def test_run_instruction_is_visible_and_preserved_as_evidence():
    manifest = {"stages": {"analyze": {"prompt": "analyze"}}}
    envelope = RuntimeEnvelope("demo", "analyze", 7, 1, 2, "real",
                               date="20260824")
    context = ContextAssembler().assemble(
        manifest, "analyze", {"date": "20260824"}, envelope,
        run_inputs={"instruction": "分析沪电股份（002463）今天走势的原因"},
    )

    rendered = context.render()
    assert "## 本次运行请求" in rendered
    assert "002463" in rendered
    assert "portfolio_id" not in rendered
    assert context.evidence()["run_inputs"]["instruction"].startswith("分析沪电股份")


def test_canonical_source_is_preserved_for_artifact_inputs():
    spec = stage_spec("close", {"prompt": "close", "inputs": {
        "plan": {"source": {"stage": "open", "output": "plan"}}
    }})
    assert spec.inputs["plan"].source == {"stage": "open", "output": "plan"}


def test_execute_cannot_cross_simulation_clock():
    from trader.tools.trading import execute
    set_execution_mode("replay", "20260822", "10:35")
    result = execute(ctx=None, action="BUY", code="000001", quantity=100,
                     reason="测试", mode="live", date="20260823")
    assert "回放日期已由平台绑定" in result
    set_execution_mode("real")
