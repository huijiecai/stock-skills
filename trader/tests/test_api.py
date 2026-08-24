"""api·平台服务测试:注册/登录/守门人/越权(TestClient,不经网络)。

docstring 统一格式:<场景>:<验证点>
"""
import pytest
from fastapi.testclient import TestClient

from trader.api.app import create_app

client = TestClient(create_app())
EMAIL = "api-test@test.io"


def _register_and_login():
    client.post("/auth/register", json={"email": EMAIL, "password": "pass-1"})
    r = client.post("/auth/login", json={"email": EMAIL, "password": "pass-1"})
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def test_healthz():
    """健康检查:免认证。"""
    assert client.get("/healthz").json() == {"ok": True}


def test_auth_flow():
    """认证流:注册→登录→me;错密码 401。"""
    h = _register_and_login()
    me = client.get("/auth/me", headers=h).json()["data"]
    assert me["email"] == EMAIL and me["is_admin"] is False
    assert client.post("/auth/login",
                       json={"email": EMAIL, "password": "wrong"}).status_code == 401


def test_gatekeeper():
    """守门人:无 token 401;伪 token 401。"""
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer fake"}).status_code == 401


def test_systems_namespace():
    """系统命名空间:能建能读自己的;别人的系统 404。"""
    h = _register_and_login()
    client.post("/systems", headers=h,
                json={"slug": "api-sys", "manifest": {"stages": {}, "tools": []}})
    names = [s["slug"] for s in client.get("/systems", headers=h).json()["data"]]
    assert "api-sys" in names and "expectation" not in names   # 看不到 user 0 的
    assert client.get("/systems/expectation", headers=h).status_code == 404


def test_workbench_data_routes_are_api_and_system_scoped():
    """工作台数据端点:/docs 不被 Swagger 抢占，且系统参数走所属主组合。"""
    h = _register_and_login()
    client.post("/systems", headers=h,
                json={"slug": "workspace-data", "manifest": {"stages": {}, "tools": []}})
    docs = client.get("/docs?system=workspace-data", headers=h)
    watchlists = client.get("/watchlists?system=workspace-data", headers=h)
    assert docs.status_code == 200 and docs.headers["content-type"].startswith("application/json")
    assert docs.json()["status"] == "SUCCESS" and isinstance(docs.json()["data"], list)
    assert watchlists.status_code == 200 and isinstance(watchlists.json()["data"], list)
    assert client.get("/api-docs").status_code == 200


def test_new_system_is_immediately_runnable():
    """冷启动:创建系统时即生成系统与阶段指令 v1，不要求先保存设置。"""
    h = _register_and_login()
    slug = "ready-on-create"
    client.post("/systems", headers=h, json={
        "slug": slug,
        "manifest": {
            "system_prompt": f"{slug}-system",
            "stages": {"open": {"kind": "single", "prompt": f"{slug}-open"}},
            "tools": [],
        },
    })
    prompts = client.get(f"/systems/{slug}/prompts", headers=h).json()["data"]
    assert {p["prompt"]: p["latest_version"] for p in prompts} == {
        f"{slug}-open": 1,
        f"{slug}-system": 1,
    }


def test_manifest_rejects_broken_stage_contract():
    """阶段配置保存:有效依赖可保存,引用不存在的输出返回 400 且不污染 manifest。"""
    import random
    h = _register_and_login()
    slug = f"contract-{random.randint(10**6, 10**7)}"
    valid = {"system_prompt": f"{slug}-system", "tools": [], "stages": {
        "prepare": {"kind": "single", "prompt": f"{slug}-prepare", "outputs": {
            "plan": {"kind": "document", "doc_type": "qa_plan", "trade_date": "{date}"},
        }},
        "observe": {"kind": "loop", "prompt": f"{slug}-observe", "inputs": {
            "opening": {"from": "prepare.plan", "selector": "latest", "required": True},
        }, "outputs": {
            "decision": {"kind": "document", "doc_type": "qa_round", "name": "r{rounds}"},
        }},
    }}
    assert client.post("/systems", headers=h, json={"slug": slug, "manifest": valid}).status_code == 200
    broken = {**valid, "stages": {**valid["stages"], "observe": {
        **valid["stages"]["observe"],
        "inputs": {"opening": {"from": "missing.plan", "selector": "latest"}},
    }}}
    res = client.put(f"/systems/{slug}/manifest", headers=h, json={"manifest": broken})
    assert res.status_code == 400 and "不存在" in res.json()["message"]
    saved = client.get(f"/systems/{slug}", headers=h).json()["data"]["manifest"]
    assert saved["stages"]["observe"]["inputs"]["opening"]["from"] == "prepare.plan"


def test_coach_conversations_are_system_scoped_and_send(monkeypatch):
    """教练闭环:首次会话可创建/发送/续读，且两个系统不会串对话。"""
    import random

    h = _register_and_login()
    suffix = random.randint(10**6, 10**7)
    systems = [f"coach-a-{suffix}", f"coach-b-{suffix}"]
    for slug in systems:
        client.post("/systems", headers=h, json={
            "slug": slug,
            "manifest": {
                "system_prompt": f"{slug}-system",
                "stages": {"open": {"kind": "single", "prompt": f"{slug}-open"}},
                "tools": [],
            },
        })

    assert client.get(
        f"/systems/{systems[0]}/coach/conversations", headers=h,
    ).json()["data"] == []

    class FakeResult:
        def __init__(self, output):
            self.output = output

    class FakeAgent:
        def __init__(self, *args, system_prompt="", **kwargs):
            self.system_prompt = system_prompt

        def run_sync(self, prompt, **kwargs):
            if self.system_prompt.startswith("为下面的对话起一个"):
                return FakeResult("仓位纪律")
            return FakeResult("结论：先验证硬约束。")

    monkeypatch.setattr("pydantic_ai.Agent", FakeAgent)
    monkeypatch.setattr("trader.core.llm.build_model", lambda: object())
    sent = client.post(
        f"/systems/{systems[0]}/coach/conversations/0",
        headers=h, json={"message": f"@prompt:{systems[0]}-open 检查这条指令"},
    )
    assert sent.status_code == 200
    assert sent.json()["data"]["reply"] == "结论：先验证硬约束。"
    first = {"id": sent.json()["data"]["id"]}
    second = client.post(f"/systems/{systems[1]}/coach/conversations", headers=h).json()["data"]
    assert first["id"] == 1 and second["id"] == 1
    assert client.get(
        f"/systems/{systems[1]}/coach/conversations", headers=h,
    ).json()["data"] == []

    a = client.get(f"/systems/{systems[0]}/coach/conversations/{first['id']}", headers=h).json()["data"]
    b = client.get(f"/systems/{systems[1]}/coach/conversations/{second['id']}", headers=h).json()["data"]
    assert [m["role"] for m in a["messages"]] == ["user", "assistant"]
    assert b["messages"] == []

    archived = client.post(
        f"/systems/{systems[0]}/coach/conversations/{first['id']}/archive",
        headers=h, json={"archived": True},
    )
    assert archived.json()["data"]["archived"] is True
    assert client.get(f"/systems/{systems[0]}/coach/conversations", headers=h).json()["data"] == []
    archived_rows = client.get(
        f"/systems/{systems[0]}/coach/conversations?archived=true", headers=h,
    ).json()["data"]
    assert archived_rows[0]["id"] == first["id"]
    assert client.post(
        f"/systems/{systems[0]}/coach/conversations/{first['id']}",
        headers=h, json={"message": "归档后不应继续"},
    ).status_code == 409

    client.post(
        f"/systems/{systems[0]}/coach/conversations/{first['id']}/archive",
        headers=h, json={"archived": False},
    )
    assert client.get(
        f"/systems/{systems[0]}/coach/conversations/{first['id']}", headers=h,
    ).status_code == 200


def test_run_discussion_restores_stage_context_without_coach(monkeypatch):
    """继续讨论:恢复原 transcript/冻结系统 Prompt，且不使用 Coach 人格。"""
    import json
    import random

    from pydantic_ai.messages import (ModelMessagesTypeAdapter, ModelRequest,
                                      ModelResponse, TextPart, UserPromptPart)
    from trader.core.context import set_context
    from trader.core.documents import default_documents
    from trader.core.portfolios import default_portfolios
    from trader.core.promptver import default_prompt_versions
    from trader.core.runs import default_runs
    from trader.core.systems import default_systems

    h = _register_and_login()
    uid = client.get("/auth/me", headers=h).json()["data"]["id"]
    slug = f"discuss-{random.randint(10**6, 10**7)}"
    system_prompt, stage_prompt = f"{slug}-system", f"{slug}-analyze"
    manifest = {
        "system_prompt": system_prompt,
        "stages": {"analyze": {"kind": "single", "prompt": stage_prompt}},
    }
    assert client.post("/systems", headers=h,
                       json={"slug": slug, "manifest": manifest}).status_code == 200
    system = default_systems().get(slug, uid)
    portfolio_id = default_portfolios().ensure_main(uid, system["id"])
    pv = default_prompt_versions()
    frozen_system = pv.save(system["id"], system_prompt, "你是冻结版行业分析 Agent。", uid)
    frozen_stage = pv.save(system["id"], stage_prompt, "分析目标并给出证据。", uid)
    run = default_runs().create(
        f"{slug}-run", "single", "20260824",
        {system_prompt: frozen_system["version"], stage_prompt: frozen_stage["version"]},
        system_id=system["id"], user_id=uid, stage="analyze",
        portfolio_id=portfolio_id,
        stage_contract={"prompt": stage_prompt, "inputs": {}, "outputs": {}},
        run_inputs={"instruction": "分析 PCB 板块"},
    )
    original_messages = [
        ModelRequest(parts=[UserPromptPart(content="本次运行请求：分析 PCB 板块")]),
        ModelResponse(parts=[TextPart(content="原结论：板块短期偏弱。")]),
    ]
    set_context(portfolio_id, run["id"], uid)
    default_documents().save(
        "transcript_analyze",
        json.dumps({"messages": json.loads(ModelMessagesTypeAdapter.dump_json(original_messages))},
                   ensure_ascii=False),
        trade_date="20260824",
    )
    default_runs().seal(run["id"])
    pv.save(system["id"], system_prompt, "这是运行结束后修改的最新版。", uid)

    captured = []

    class FakeResult:
        output = "偏弱主要来自量能与板块扩散不足。"

        def __init__(self, messages):
            self._messages = messages

        def all_messages(self):
            return self._messages

    class FakeAgent:
        def __init__(self, *args, system_prompt="", **kwargs):
            self.system_prompt = system_prompt

        def run_sync(self, prompt, message_history=None):
            history = list(message_history or [])
            captured.append((self.system_prompt, prompt, history))
            return FakeResult(history + [
                ModelRequest(parts=[UserPromptPart(content=prompt)]),
                ModelResponse(parts=[TextPart(content=FakeResult.output)]),
            ])

    monkeypatch.setattr("pydantic_ai.Agent", FakeAgent)
    monkeypatch.setattr("trader.core.llm.build_model", lambda: object())
    response = client.post(
        f"/runs/{run['id']}/chat", headers=h,
        json={"message": "为什么认为偏弱？"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["anchor"]["mode"] == "frozen"
    system_text, question, restored = captured[0]
    assert "冻结版行业分析 Agent" in system_text
    assert "运行结束后修改的最新版" not in system_text
    assert "本场继续讨论" in system_text and "复盘教练" not in system_text
    assert "用户追问：为什么认为偏弱？" in question
    assert "原结论：板块短期偏弱" in question
    assert restored == []

    followup = client.post(
        f"/runs/{run['id']}/chat", headers=h,
        json={"message": "哪条依据最弱？"},
    )
    assert followup.status_code == 200
    assert captured[1][1] == "哪条依据最弱？"  # 冻结上下文已在 model history，不重复注入
    restored_text = str(json.loads(ModelMessagesTypeAdapter.dump_json(captured[1][2])))
    assert "用户追问：为什么认为偏弱？" in restored_text
    assert "量能与板块扩散不足" in restored_text

    saved = client.get(f"/runs/{run['id']}/chat", headers=h).json()["data"]
    assert [m["role"] for m in saved["messages"]] == [
        "user", "assistant", "user", "assistant",
    ]
    assert saved["messages"][0]["content"] == "为什么认为偏弱？"
    # Discussion is attached to the Run by ref_id, not written into immutable run_documents.
    assert all(d["doc_type"] != "chat" for d in default_documents().for_run(run["id"]))


def test_cross_user_run_denied():
    """越权:读别人的场次 404(不泄露存在性)。"""
    h = _register_and_login()
    assert client.get("/runs/12", headers=h).status_code == 404


def test_portfolio_admin_gate():
    """组合管理员闸:普通用户开实盘(main)组合 403,模拟(paper)可以。"""
    import random
    h = _register_and_login()
    client.post("/systems", headers=h,
                json={"slug": "pf-gate-sys", "manifest": {"stages": {}, "tools": []}})
    name = f"L{random.randint(10**6, 10**7)}"   # 幂等:每次随机名
    assert client.post("/portfolios", headers=h,
                       json={"name": name, "type": "main",
                             "system": "pf-gate-sys"}).status_code == 403
    assert client.post("/portfolios", headers=h,
                       json={"name": name, "type": "paper",
                             "system": "pf-gate-sys"}).status_code == 200


def _make_system_with_stage(h, name, stage_def):
    client.post("/systems", headers=h,
                json={"slug": name, "manifest": {"stages": {stage_def.get("_n", "run"): stage_def},
                                                 "tools": []}})


def test_run_stop_seal_flow():
    """停止流转:running→stop→stopping;seal 强制封存;重复操作 409。"""
    import random
    from trader.core.runs import default_runs
    h = _register_and_login()
    uid = client.get("/auth/me", headers=h).json()["data"]["id"]
    rn = f"stopflow-{random.randint(10**6, 10**7)}"
    run = default_runs().create(rn, "replay", "20990101", {}, system_id=1,
                                user_id=uid, stage="run",
                                clock="simulated", clock_date="20990101", portfolio_id=999)
    rid = run["id"]
    assert client.post(f"/runs/{rid}/stop", headers=h).json()["data"]["status"] == "stopping"
    assert client.post(f"/runs/{rid}/stop", headers=h).status_code == 200   # 幂等
    assert client.post(f"/runs/{rid}/seal", headers=h).json()["data"]["status"] == "sealed"
    assert client.post(f"/runs/{rid}/seal", headers=h).status_code == 409   # 已封存
    assert client.post(f"/runs/{rid}/stop", headers=h).status_code == 409   # 已封存无需停止
    default_runs().delete(rn, uid)


def test_run_system_duplicate_guard():
    """重复触发硬拦:live 已在跑 409;replay 同名场 409;single 不拦(无 LLM,只验守卫层)。"""
    import random
    from datetime import datetime
    from trader.core.runs import default_runs
    h = _register_and_login()
    uid = client.get("/auth/me", headers=h).json()["data"]["id"]
    sn = f"guard-{random.randint(10**6, 10**7)}"
    client.post("/systems", headers=h, json={"slug": sn, "manifest": {"stages": {
        "live": {"kind": "loop", "prompt": f"{sn}-live"},
        "replay": {"kind": "loop", "prompt": f"{sn}-replay", "interval": 5},
    }, "tools": []}})
    from trader.core.systems import default_systems
    sn_id = default_systems().get(sn, user_id=uid)["id"]
    today = datetime.now().strftime("%Y%m%d")
    # live 今日已有 running 场 → 409
    default_runs().create(f"live-{today}", "live", today, {}, system_id=sn_id,
                          user_id=uid, stage="live")
    listed = client.get(f"/runs?system={sn}", headers=h).json()["data"]
    assert listed[0]["system_id"] == sn_id
    r = client.post(f"/systems/{sn}/run", headers=h, json={"date": today, "stage": "live"})
    assert r.status_code == 409 and "已在跑" in r.json()["message"]
    # 重演同日同名场(web- 前缀)→ 409
    date = "20990102"
    default_runs().create(f"{date}-web-{sn}", "replay", date, {}, system_id=sn_id,
                          user_id=uid, stage="replay", clock="simulated", clock_date=date)
    r = client.post(f"/systems/{sn}/run", headers=h,
                    json={"date": date, "stage": "replay", "clock": "simulated"})
    assert r.status_code == 409 and "重演场" in r.json()["message"]
    # 清理:live 今日场是用户命名空间下的 live-{today},名字带日期唯一,直接删
    default_runs().delete(f"live-{today}", uid)
    default_runs().delete(f"{date}-web-{sn}", uid)


def test_run_instruction_is_forwarded_to_engine(monkeypatch):
    """Web 发起的本次任务必须进入 Engine 子进程，而不是只停留在弹窗。"""
    import random
    import subprocess

    h = _register_and_login()
    sn = f"instruction-{random.randint(10**6, 10**7)}"
    _make_system_with_stage(h, sn, {
        "_n": "analyze", "kind": "single", "prompt": f"{sn}-analyze",
        "outputs": {"result": {"kind": "artifact"}},
    })
    spawned: list[list[str]] = []

    def fake_popen(cmd, **_kwargs):
        spawned.append(cmd)
        return object()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    instruction = "分析沪电股份（002463）今天走势的原因"
    response = client.post(
        f"/systems/{sn}/run", headers=h,
        json={"date": "20260824", "stage": "analyze", "instruction": instruction},
    )

    assert response.status_code == 200
    assert response.json()["data"]["run_inputs"] == {"instruction": instruction}
    assert len(spawned) == 1
    code = spawned[0][-1]
    assert repr(instruction) in code
    compile(code, "<run-instruction>", "exec")


def test_portfolio_curve_marks_live_price(monkeypatch):
    """曲线末点现价估值:持仓浮盈即时可见,不只按成交价 mark(资产页累计收益依据)。"""
    import random
    import trader.core.market as market
    from trader.core.ledger import Wallet, WalletError
    from trader.core.portfolios import Portfolios
    from trader.core.systems import Systems
    h = _register_and_login()
    uid = client.get("/auth/me", headers=h).json()["data"]["id"]
    sn = f"curve-{random.randint(10**6, 10**7)}"
    pid = Portfolios().create(uid, "paper", Systems().upsert(sn, {"stages": {}}, user_id=uid)["id"],
                              "曲线测试组合")
    try:
        Wallet().open_wallet(100_000_00, 100_000_00, portfolio_id=pid)
    except WalletError:
        pass
    Wallet().buy("000001", 100, 10.0, portfolio_id=pid)
    monkeypatch.setattr(market, "_fetch_quotes",
                        lambda mode, codes, date="", time=None:
                        [{"code": c, "price": 11.0} for c in codes])
    r = client.get(f"/portfolios/{pid}/curve", headers=h).json()["data"]
    assert len(r["points"]) == 3                              # 初始 + 成交 + 现价末点
    assert r["points"][1]["equity"] == 100_000_00             # 成交时点(按成交价)=初始
    assert r["points"][2]["equity"] == 100_000_00 + 100 * (1100 - 1000)  # 现价 11 元:+100 元浮盈
    Portfolios().delete(pid)


def test_stage_context_endpoint():
    """阶段变量契约:按阶段类型给出可用占位符,single 带 date 时派生变量算真值。"""
    import random
    h = _register_and_login()
    sn = f"ctx-{random.randint(10**6, 10**7)}"
    client.post("/systems", headers=h, json={"slug": sn, "manifest": {"stages": {
        "live": {"kind": "loop", "prompt": f"{sn}-live"},
        "replay": {"kind": "loop", "prompt": f"{sn}-replay", "interval": 5},
        "premarket": {"kind": "single", "prompt": f"{sn}-pre",
                      "vars": ["date", "prev", "weekday", "gap"]},
    }, "tools": []}})
    def ctx(stage, date=""):
        return client.get(f"/systems/{sn}/stages/{stage}/context",
                          params={"date": date} if date else {}, headers=h).json()["data"]
    # live 轮:rounds/now/date;replay 轮:rounds/date/clock(与引擎注入一致)
    assert [v["name"] for v in ctx("live")["vars"]] == ["rounds", "now", "date"]
    assert [v["name"] for v in ctx("replay")["vars"]] == ["rounds", "date", "clock"]
    # single:声明变量 + 派生;带 date 时派生算真值(20260824 周一,上一交易日 20260821)
    names = [v["name"] for v in ctx("premarket")["vars"]]
    assert set(names) == {"date", "prev", "weekday", "gap"}
    real = {v["name"]: v["value"] for v in ctx("premarket", date="20260824")["vars"]}
    assert real["prev"] == "20260821" and real["weekday"] == "周一" and real["gap"] == 3
    # 系统设定:无变量 + 说明
    sysctx = ctx("(system)")
    assert sysctx["vars"] == [] and "字面" in sysctx["note"]
    assert client.get(f"/systems/{sn}/stages/nope/context", headers=h).status_code == 404


def test_tools_catalog_and_call(monkeypatch):
    """工具目录与试运行:目录带签名/写标记;试运行挂测试账号(环境变量可配),
    越权组合 403,未知工具 404,参数错误 400;查持仓能查到测试账号数据。"""
    import random
    from trader.core.ledger import Wallet
    from trader.core.portfolios import Portfolios
    from trader.core.systems import Systems
    from trader.api import tools as tools_api
    h = _register_and_login()
    # 隔离测试账号:注册新用户 → 建组合 → 买入(绝不碰 user 0/3)
    from trader.core.identity import Identity
    uid = Identity().create_user(f"tooltest-{random.randint(10**6, 10**7)}@t.test", "p")["id"]
    monkeypatch.setenv(tools_api.TEST_USER_ENV, str(uid))
    sn = f"tt-{random.randint(10**5, 10**6)}"
    pid = Portfolios().create(uid, "paper", Systems().upsert(sn, {"stages": {}}, user_id=uid)["id"], "试运行组合")
    Wallet().open_wallet(100_000_00, 100_000_00, portfolio_id=pid)
    Wallet().buy("000021", 100, 10.0, portfolio_id=pid)

    cat = client.get("/tools", headers=h).json()["data"]
    by_name = {t["name"]: t for t in cat["tools"]}
    assert by_name["get_quotes"]["params"][0] == {"name": "codes", "type": "list[str]",
                                                  "required": True, "default": None}
    assert by_name["execute"]["write"] is True and by_name["get_account"]["write"] is False
    assert cat["test_user"]["id"] == uid
    assert any(p["id"] == pid and p["has_positions"] for p in cat["portfolios"])

    # 行情工具(与组合无关):真实调用返回非空字符串(具体内容随交易时段变化
    # ——盘前/收盘后行情源会拒绝,不断言具体标的,只断言调用管道通)
    r = client.post("/tools/get_quotes/call", headers=h,
                    json={"args": {"codes": ["000021"]}, "portfolio_id": pid})
    assert r.status_code == 200 and len(r.json()["data"]["output"]) > 10

    # 账户工具:挂测试账号组合,查到刚才买的持仓
    r = client.post("/tools/get_positions/call", headers=h, json={"portfolio_id": pid})
    assert r.status_code == 200 and "000021" in r.json()["data"]["output"]

    # 越权(不属于测试账号的组合)→ 403;未知工具 404;多余参数/缺必填 400
    assert client.post("/tools/get_positions/call", headers=h,
                       json={"portfolio_id": 0}).status_code == 403
    assert client.post("/tools/no_such/call", headers=h, json={}).status_code == 404
    assert client.post("/tools/get_quotes/call", headers=h,
                       json={"args": {"nope": 1}}).status_code == 400
    assert client.post("/tools/get_quotes/call", headers=h, json={}).status_code == 400
    Portfolios().delete(pid)
