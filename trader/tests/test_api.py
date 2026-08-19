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
                json={"name": "api-sys", "manifest": {"stages": {}, "tools": []}})
    names = [s["name"] for s in client.get("/systems", headers=h).json()["data"]]
    assert "api-sys" in names and "expectation" not in names   # 看不到 user 0 的
    assert client.get("/systems/expectation", headers=h).status_code == 404


def test_cross_user_run_denied():
    """越权:读别人的场次 404(不泄露存在性)。"""
    h = _register_and_login()
    assert client.get("/runs/12", headers=h).status_code == 404


def test_ledger_admin_gate():
    """账本管理员闸:普通用户开 live 账本 403,paper 可以。"""
    import random
    h = _register_and_login()
    name = f"L{random.randint(10**6, 10**7)}"   # 幂等:每次随机名
    assert client.post("/ledgers", headers=h,
                       json={"name": name, "kind": "live"}).status_code == 403
    assert client.post("/ledgers", headers=h,
                       json={"name": name, "kind": "paper"}).status_code == 200
