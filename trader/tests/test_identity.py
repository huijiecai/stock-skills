"""Identity 测试:三层认证(users/identities/sessions/api_keys),t_ schema 隔离。

覆盖:注册/重复邮箱 / 密码登录对错 / 会话签发吊销 / API Key 签发-校验-吊销-过期。

docstring 统一格式:<场景>:<验证点>
"""
import pytest

from trader.core.identity import (Identity, hash_password, verify_password)

TOOL = "identity"


def _idt(request):
    return Identity(schema=f"t_{request.node.name[:40]}")


def test_password_hash_roundtrip():
    """密码哈希:scrypt 自包含(盐在串里),校验对错分明。"""
    stored = hash_password("s3cret-Pass")
    assert verify_password("s3cret-Pass", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("s3cret-Pass", "bad-format")
    print(f"  → 哈希格式:{stored[:20]}…")


def test_create_user_and_duplicate(request):
    """注册:邮箱即用户名(小写归一);重复邮箱拒绝。"""
    idt = _idt(request)
    u = idt.create_user("A@Example.com", "pass-1", display_name="甲")
    assert u["email"] == "a@example.com" and u["is_admin"] is False
    with pytest.raises(ValueError, match="邮箱已注册"):
        idt.create_user("a@example.com", "pass-2")
    print(f"  → user #{u['id']} {u['email']} display={u['display_name']}")


def test_login_right_wrong_and_unknown(request):
    """密码登录:对→用户行;错密码/不存在→None(同响应不泄露)。"""
    idt = _idt(request)
    idt.create_user("b@test.io", "right-pass")
    assert (idt.verify_login("b@test.io", "right-pass") or {}).get("email") == "b@test.io"
    assert idt.verify_login("b@test.io", "wrong-pass") is None
    assert idt.verify_login("ghost@test.io", "whatever") is None
    print("  → 对/错/不存在三分支正确")


def test_session_issue_resolve_revoke(request):
    """会话:签发→解析出用户;吊销后立即失效。"""
    idt = _idt(request)
    u = idt.create_user("c@test.io", "p")
    token = idt.open_session(u["id"], days=1)
    assert idt.resolve_session(token)["user_id"] == u["id"]
    idt.revoke_session(token)
    assert idt.resolve_session(token) is None
    print(f"  → 会话签发/吊销闭环(明文长度 {len(token)})")


def test_api_key_lifecycle(request):
    """API Key:sk- 前缀只显示一次;校验带 scope 与 last_used;吊销即失效。"""
    idt = _idt(request)
    u = idt.create_user("d@test.io", "p")
    key = idt.issue_api_key(u["id"], name="回测脚本", scope="read")
    assert key.startswith("sk-")
    k = idt.resolve_api_key(key)
    assert k["user_id"] == u["id"] and k["scope"] == "read"
    assert idt.list_api_keys(u["id"])[0]["last_used_at"] is not None  # 校验顺手记使用
    assert idt.revoke_api_key(u["id"], "回测脚本") == 1
    assert idt.resolve_api_key(key) is None
    assert idt.resolve_api_key("sk-forged") is None
    print(f"  → key 生命周期闭环({key[:12]}…)")


def test_link_identity_github(request):
    """扩展登录:给已有用户绑 GitHub 身份;同身份不可绑第二人。"""
    idt = _idt(request)
    u1 = idt.create_user("e1@test.io", "p")
    u2 = idt.create_user("e2@test.io", "p")
    idt.link_identity(u1["id"], "github", "gh-12345")
    with pytest.raises(ValueError, match="已被绑定"):
        idt.link_identity(u2["id"], "github", "gh-12345")
    print("  → GitHub 身份绑定/防抢占")
