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
